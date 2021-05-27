from collections import OrderedDict
import numpy as np
import os
from hazel.atmosphere import General_atmosphere
from hazel.util import i0_allen
from hazel.codes import sir_code
from hazel.hsra import hsra_continuum
from hazel.io import Generic_SIR_file
import scipy.interpolate as interp
from hazel.exceptions import NumericalErrorSIR
from hazel.transforms import transformed_to_physical, jacobian_transformation
import copy


__all__ = ['SIR_atmosphere']

# sir_parameters = OrderedDict.fromkeys('T B thetaB phiB v')

class SIR_atmosphere(General_atmosphere):
    def __init__(self, working_mode, name=''):
        
        super().__init__('photosphere', name=name)

        self.ff = 1.0        
        self.macroturbulence = np.zeros(1)
        self.working_mode = working_mode
        
        self.parameters['T'] = None
        self.parameters['vmic'] = None
        self.parameters['v'] = None
        self.parameters['Bx'] = None
        self.parameters['By'] = None
        self.parameters['Bz'] = None
        self.parameters['ff'] = None
        self.parameters['vmac'] = None

        self.nodes_location['T'] = None
        self.nodes_location['vmic'] = None
        self.nodes_location['v'] = None
        self.nodes_location['Bx'] = None
        self.nodes_location['By'] = None
        self.nodes_location['Bz'] = None
        self.nodes_location['ff'] = None
        self.nodes_location['vmac'] = None

        self.n_nodes['T'] = 0
        self.n_nodes['vmic'] = 0
        self.n_nodes['v'] = 0
        self.n_nodes['Bx'] = 0
        self.n_nodes['By'] = 0
        self.n_nodes['Bz'] = 0
        self.n_nodes['ff'] = 0
        self.n_nodes['vmac'] = 0

        self.nodes['T'] = 0
        self.nodes['vmic'] = 0
        self.nodes['v'] = 0
        self.nodes['Bx'] = 0
        self.nodes['By'] = 0
        self.nodes['Bz'] = 0
        self.nodes['ff'] = 0
        self.nodes['vmac'] = 0

        self.rf_analytical = OrderedDict()
        self.rf_analytical['T'] = None
        self.rf_analytical['vmic'] = None
        self.rf_analytical['v'] = None
        self.rf_analytical['Bx'] = None
        self.rf_analytical['By'] = None
        self.rf_analytical['Bz'] = None
        self.rf_analytical['ff'] = None
        self.rf_analytical['vmac'] = None

        self.ranges['T'] = None
        self.ranges['vmic'] = None
        self.ranges['v'] = None
        self.ranges['Bx'] = None
        self.ranges['By'] = None
        self.ranges['Bz'] = None
        self.ranges['ff'] = None
        self.ranges['vmac'] = None

        self.cycles['T'] = None
        self.cycles['vmic'] = None
        self.cycles['v'] = None
        self.cycles['Bx'] = None
        self.cycles['By'] = None
        self.cycles['Bz'] = None
        self.cycles['ff'] = None
        self.cycles['vmac'] = None

        self.epsilon['T'] = 0.01
        self.epsilon['vmic'] = 0.01
        self.epsilon['v'] = 0.01
        self.epsilon['Bx'] = 0.01
        self.epsilon['By'] = 0.01
        self.epsilon['Bz'] = 0.01
        self.epsilon['ff'] = 0.01
        self.epsilon['vmac'] = 0.01

        self.regularization['T'] = None
        self.regularization['vmic'] = None
        self.regularization['v'] = None
        self.regularization['Bx'] = None
        self.regularization['By'] = None
        self.regularization['Bz'] = None
        self.regularization['ff'] = None
        self.regularization['vmac'] = None
        
    def list_lines(self):
        """
        List the lines available in SIR for synthesis
            
        """
        f = open('LINEAS', 'r')
        lines = f.readlines()
        f.close()

        print("Available lines:")
        for l in lines[:-1]:
            print(l[:-1])

    def add_active_line(self, lines, spectrum, wvl_range):
        """
        Add an active lines in this atmosphere
        
        Parameters
        ----------
        lines : str
            Line to activate
        spectrum : Spectrum
            Spectrum object
        wvl_range : float
            Vector containing wavelength range over which to synthesize this line
        
        Returns
        -------
        None
    
        """
        
        self.lines = lines
        self.wvl_range_lambda = wvl_range

        ind_low = (np.abs(spectrum.wavelength_axis - wvl_range[0])).argmin()
        ind_top = (np.abs(spectrum.wavelength_axis - wvl_range[1])).argmin()

        self.spectrum = spectrum
        self.wvl_axis = spectrum.wavelength_axis[ind_low:ind_top+1]
        self.wvl_range = np.array([ind_low, ind_top+1])
        
    def interpolate_nodes(self, log_tau, reference, nodes):
        """
        Generate a model atmosphere by interpolating the defined nodes. The interpolation
        order depends on the number of nodes.
        
        Parameters
        ----------
        log_tau : float
            Vector of log optical depth at 500 nm
        reference : float
            Vector with the reference atmosphere to which the nodes are added
        nodes : float
            List with the position of the nodes

        Returns
        -------
        real
            Vector with the interpolated atmosphere
    
        """
        n_nodes = len(nodes)
        n_depth = len(log_tau)

        if (n_nodes == 0):
            return reference, 0
        
        if (n_nodes == 1):
            return reference + nodes[0], log_tau[n_depth//2]
        
        if (n_nodes == 2):
            pos = np.linspace(0, n_depth-1, n_nodes+2, dtype=int)[1:-1]
            f = interp.interp1d(log_tau[pos], nodes, 'linear', bounds_error=False, fill_value='extrapolate')
            return reference + f(log_tau), log_tau[pos]

        if (n_nodes == 3):
            pos = np.linspace(0, n_depth-1, n_nodes+2, dtype=int)[1:-1]
            f = interp.interp1d(log_tau[pos], nodes, 'quadratic', bounds_error=False, fill_value='extrapolate')
            return reference + f(log_tau), log_tau[pos]

        if (n_nodes > 3):
            pos = np.linspace(n_depth-1, 0, n_nodes+2, dtype=int)[1:-1]
            f = interp.PchipInterpolator(log_tau[pos], nodes, extrapolate=True)            
            return reference + f(log_tau), log_tau[pos]

    def interpolate_nodes_rf(self, log_tau, reference, nodes, lower, upper):
        """
        Generate a model atmosphere by interpolating the defined nodes. The interpolation
        order depends on the number of nodes.
        
        Parameters
        ----------
        log_tau : float
            Vector of log optical depth at 500 nm
        reference : float
            Vector with the reference atmosphere to which the nodes are added
        nodes : float
            List with the position of the nodes

        Returns
        -------
        real
            Vector with the interpolated atmosphere
    
        """
        n_nodes = len(nodes)
        n_depth = len(log_tau)

        if (n_nodes == 0):
            return np.zeros(n_depth)
        
        if (n_nodes == 1):
            rf = np.zeros((n_nodes, n_depth))

            tmp0 = reference + nodes[0]

            # Add the Jacobian to each height
            jacobian = jacobian_transformation(tmp0, lower, upper)

            rf[0,:] = 1.0 * jacobian
            return rf
        
        if (n_nodes == 2):
            rf = np.zeros((n_nodes, n_depth))

            pos = np.linspace(0, n_depth-1, n_nodes+2, dtype=int)[1:-1]
            f = interp.interp1d(log_tau[pos], nodes, 'linear', bounds_error=False, fill_value='extrapolate')

            tmp0 = reference + f(log_tau)

            jacobian = jacobian_transformation(tmp0, lower, upper)

            delta = 1e-3

            for i in range(n_nodes):
                tmp_nodes = np.copy(nodes)
                tmp_nodes[i] += delta
                f = interp.interp1d(log_tau[pos], tmp_nodes, 'linear', bounds_error=False, fill_value='extrapolate')

                tmp1 = reference + f(log_tau)

                rf[i,:] = (tmp1 - tmp0) / delta * jacobian
            
            return rf

        if (n_nodes == 3):
            rf = np.zeros((n_nodes, n_depth))

            pos = np.linspace(0, n_depth-1, n_nodes+2, dtype=int)[1:-1]
            f = interp.interp1d(log_tau[pos], nodes, 'quadratic', bounds_error=False, fill_value='extrapolate')
            tmp0 = reference + f(log_tau)

            jacobian = jacobian_transformation(tmp0, lower, upper)

            delta = 1e-3

            for i in range(n_nodes):
                tmp_nodes = np.copy(nodes)
                tmp_nodes[i] += delta
                f = interp.interp1d(log_tau[pos], tmp_nodes, 'quadratic', bounds_error=False, fill_value='extrapolate')

                tmp1 = reference + f(log_tau)

                rf[i,:] = (tmp1 - tmp0) / delta * jacobian
            
            return rf

        if (n_nodes > 3):
            rf = np.zeros((n_nodes, n_depth))

            pos = np.linspace(n_depth-1, 0, n_nodes+2, dtype=int)[1:-1]
            f = interp.PchipInterpolator(log_tau[pos], nodes, extrapolate=True)

            tmp0 = reference + f(log_tau)

            jacobian = jacobian_transformation(tmp0, lower, upper)

            delta = 1e-3

            for i in range(n_nodes):
                tmp_nodes = np.copy(nodes)
                tmp_nodes[i] += delta
                f = interp.PchipInterpolator(log_tau[pos], tmp_nodes, extrapolate=True)

                tmp1 = reference + f(log_tau)

                rf[i,:] = (tmp1 - tmp0) / delta * jacobian
            
            return rf

    def load_reference_model(self, model_file, verbose):
        """
        Load a reference model or a model for every pixel for synthesis/inversion

        Parameters
        ----------
        model_file : str
            String with the name of the file. Extensions can currently be "1d" or "h5"
        verbose : bool
            Verbosity

        Returns
        -------
        None
        """
        extension = os.path.splitext(model_file)[1][1:]
        if (extension == '1d'):
            if (verbose >= 1):
                self.logger.info('    * Reading 1D model {0} as reference'.format(model_file))
            self.model_type = '1d'
            self.model_filename = model_file
        
        if (extension == 'h5'):
            if (verbose >= 1):
                self.logger.info('    * Reading 3D model {0} as reference'.format(model_file))
            self.model_type = '3d'
                        

        self.model_handler = Generic_SIR_file(model_file)
        self.model_handler.open()
        out, ff, vmac = self.model_handler.read(pixel=0)
        self.model_handler.close()

        self.set_parameters(out, ff, vmac)
        
        self.init_reference(check_borders=True)
                        
    def set_parameters(self, model, ff, vmac):
        """
        Set the parameters of the current model to those passed as argument

        Parameters
        ----------
        model_in : float
            Array with the model        
        ff : float
            Value of the filling factor
        vmac : float
            Value of the macroturbulent velocity

        Returns
        -------
        None
        """
        
        self.log_tau = model[:,0]
        self.parameters['T'] = model[:,1]
        self.parameters['vmic'] = model[:,3]
        self.parameters['v'] = model[:,4]
        self.parameters['Bx'] = model[:,5]
        self.parameters['By'] = model[:,6]
        self.parameters['Bz'] = model[:,7]

        if (np.min(model[:,2]) > 0.0):
            self.Pe = model[:,2]
        else:
            self.Pe = -np.ones(len(self.log_tau))
            self.Pe[-1] = 1.11634e-1        
        
        self.parameters['ff'] = ff
        self.parameters['vmac'] = vmac

        # Check that parameters are inside borders by clipping inside the interval with a border of 1e-8
        if (self.working_mode == 'inversion'):
            for k, v in self.parameters.items():                
                self.parameters[k] = np.clip(v, self.ranges[k][0] + 1e-8, self.ranges[k][1] - 1e-8)
                

    def get_parameters(self):                
        """
        Get the curent parameters as a model

        Parameters
        ----------
        None

        Returns
        -------
        model: a 6xN photspheric model
        """
        
        model = np.zeros((len(self.log_tau),8))
        model[:,0] = self.log_tau
        model[:,1] = self.parameters['T']
        model[:,2] = self.Pe
        model[:,3] = self.parameters['vmic']
        model[:,4] = self.parameters['v']
        model[:,5] = self.parameters['Bx']
        model[:,6] = self.parameters['By']
        model[:,7] = self.parameters['Bz']

        return model        

    def nodes_to_model(self):
        """
        Transform from nodes to model
        
        Parameters
        ----------
        None
                                
        Returns
        -------
        None
        """        
        for k, v in self.nodes.items():
            if (self.n_nodes[k] > 0):                
                self.parameters[k], self.nodes_location[k] = self.interpolate_nodes(self.log_tau, self.reference[k], self.nodes[k])
            else:
                self.parameters[k] = self.reference[k]
                    
    def model_to_nodes(self):
        """
        Transform from model to nodes
        
        Parameters
        ----------
        None
                                
        Returns
        -------
        None        
        """

        pass

        # for k, v in self.parameters.items():
            # if (k is not 'log_tau'):

        # self.interpolate_nodes(self.parameters['log_tau'], self.reference['T'], [1000])
        # stop()
        # for k, v in self.parameters.items():
            # if (k is not 'log_tau'):
                
    def print_parameters(self, first=False, error=False):
        for k, v in self.nodes.items():
            if (self.n_nodes[k] > 0):
                if (k != 'ff'):
                    lower = self.ranges[k][0] #- self.eps_borders
                    upper = self.ranges[k][1] #+ self.eps_borders
                    nodes = transformed_to_physical(v, lower, upper)            
                    self.logger.info('{0} -> {1}'.format(k, nodes))
            
    def synthesize(self, stokes_in, returnRF=False):
        """
        Carry out the synthesis and returns the Stokes parameters and the response 
        functions to all physical variables at all depths
        
        Parameters
        ----------
        stokes_in : float
            An array of size [4 x nLambda] with the input Stokes parameter. It is irrelevant in this case
            because we assume that all SIR atmospheres have the Planck function as boundary.
                
        returnRF : bool, optional
            Return response functions
        
        Returns
        -------
        
        stokes : float
            Stokes parameters, with the first index containing the wavelength displacement and the remaining
                                    containing I, Q, U and V. Size (5,nLambda)
        rf: float (optional)
            Response functions to T, Pe, vmic, B, v, theta, phi, all of size (4,nLambda,nDepth), plus the RF to macroturbulence of size (4,nLambda)
                            It is not returned if returnRF=False
        """

        if (self.working_mode == 'inversion'):
            self.nodes_to_model()
            self.to_physical()
        
        if (returnRF):
            stokes, rf, error = sir_code.synthRF(self.index, self.n_lambda, self.log_tau, self.parameters['T'], 
                self.Pe, 1e5*self.parameters['vmic'], 1e5*self.parameters['v'], self.parameters['Bx'], self.parameters['By'], 
                self.parameters['Bz'], self.parameters['vmac'])

            if (error == 1):
                raise NumericalErrorSIR()

            B = np.sqrt(self.parameters['Bx']**2 + self.parameters['By']**2 + self.parameters['Bz']**2)
            
            thetaB = np.arccos(self.parameters['Bz'] / B)
            thetaB[B == 0] = 0.0

            phiB = np.arctan2(self.parameters['By'], self.parameters['Bx'])

            # rfn = np.zeros((150, 73))
            # pars = copy.deepcopy(self.parameters)
            # for pos in range(73):
            #     ind_sto = 0

            #     self.parameters = copy.deepcopy(pars)

            #     delta = 5e-4*self.parameters['T'][pos]
            #     self.parameters['T'][pos] += delta

            #     stokes2, rf2, error = sir_code.synthRF(self.index, self.n_lambda, self.log_tau, self.parameters['T'], 
            #         self.Pe, 1e5*self.parameters['vmic'], 1e5*self.parameters['v'], self.parameters['Bx'], self.parameters['By'], 
            #         self.parameters['Bz'], self.parameters['vmac'])
            #     error = 0

            #     rfn[:, pos] = (stokes2[ind_sto+1,:]-stokes[ind_sto+1,:])/delta

            # breakpoint()

            # import matplotlib.pyplot as pl
            # pl.plot(rfn[:, 40], '-o', label='numerical')

            self.rf_analytical['T'] = rf[0]+rf[1]       #OK
            self.rf_analytical['vmic'] = 1e5*rf[6]   #OK
            self.rf_analytical['v'] = 1e5*rf[3]      #OK

            # Transform SIR RFs into response functions to Bx, By and Bz.
            # To this end, we have:
            # [RF_B ]   [dBxdB     dBydB    dBzdB ][RF_Bx]
            # [RF_th] = [dBxdthB  dBydthB  dBzdthB][RF_By] 
            # [RF_ph]   [dBxdphB  dBydphB  dBzdphB][RF_Bz]
            # and then invert the Jacobian

            RFB = rf[2]
            RFt = rf[4]
            RFp = rf[5]

            self.rf_analytical['Bx'] = RFB * np.sin(thetaB) * np.cos(phiB) + \
                                        RFt * np.cos(thetaB) * np.cos(phiB) / B - \
                                        RFp * np.sin(phiB) / (B * np.sin(thetaB))
            self.rf_analytical['By'] = RFB * np.sin(thetaB) * np.sin(phiB) + \
                                        RFt * np.cos(thetaB) * np.sin(phiB) / B + \
                                        RFp * np.cos(phiB) / (B * np.sin(thetaB))
            self.rf_analytical['Bz'] = RFB * np.cos(thetaB) - RFt * np.sin(thetaB) / B

            self.rf_analytical['vmac'] = rf[7][:, :, None]

            # pl.plot(self.rf_analytical['T'][ind_sto,:,pos], label='analytical')
            # pl.legend()
            # pl.show()

            # import matplotlib.pyplot as pl
            # f, ax = pl.subplots(nrows=3, ncols=3, figsize=(10,10))
            # ax = ax.flatten()
            # for i in range(9):
            #     ax[i].plot(np.log(self.rf_analytical['T'][0,i*10,:]), color=f'C{i}')
            #     ax[i].plot(np.log(rfn[i*10,:]), 'o', color=f'C{i}')
            # pl.show()

            i0 = i0_allen(np.mean(self.wvl_axis), self.spectrum.mu)

            for k, v in self.nodes.items():
                if (k != 'vmac'):
                    if (self.n_nodes[k] > 0):
                        lower = self.ranges[k][0]
                        upper = self.ranges[k][1]
                        rf = self.interpolate_nodes_rf(self.log_tau, self.reference[k], self.nodes[k], lower, upper)

                        # import matplotlib.pyplot as pl
                        # f, ax = pl.subplots(nrows=3, ncols=3, figsize=(10,10))
                        # ax = ax.flatten()
                        # for i in range(9):
                        #     ax[i].plot(rfn[i*10,:] / self.rf_analytical['T'][0,i*10,:], color=f'C{i}')
                        #     ax[i].set_ylim([0,2])
                        # pl.show()
                        # print(k)
                        # breakpoint()

                        self.rf_analytical[k] = np.einsum('ijk,lk->ijl', self.rf_analytical[k], rf) * i0

            return self.parameters['ff'] * stokes[1:,:] * i0, self.rf_analytical, error
        else:                       
            stokes, error = sir_code.synth(self.index, self.n_lambda, self.log_tau, self.parameters['T'], 
                self.Pe, 1e5*self.parameters['vmic'], 1e5*self.parameters['v'], self.parameters['Bx'], self.parameters['By'], 
                self.parameters['Bz'], self.parameters['vmac'])

            if (error == 1):
                raise NumericalErrorSIR()

            return self.parameters['ff'] * stokes[1:,:] * i0_allen(np.mean(self.wvl_axis), self.spectrum.mu), error #hsra_continuum(np.mean(self.wvl_axis)), error