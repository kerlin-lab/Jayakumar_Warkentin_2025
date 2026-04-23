#import dependencies
import numpy as np
import matplotlib.pyplot as plt
import scipy.io
import os
from scipy.optimize import curve_fit
from sklearn.metrics import r2_score


def calculate_charge_density(phaseProfile, spaceVector, wavelength, Length, g11, index0, range_start=None, range_end=None):
    """
    Converts phase profile to a focal length and computes charge density.

    Parameters:
        phaseProfile (numpy.ndarray): Phase profile (radians)
        spaceVector (numpy.ndarray): Vector representing physical space of the profile (m)
        wavelength (float): Wavelength of light used (m)
        Length (float): Interaction length of crystal (m)
        g11 (float): EO coefficient
        index0 (float): Index of refraction

    """
    
    # Convert spaceVector to meters
    spaceVector_m = spaceVector * 10**-3
    
    # Define a quadratic function for fitting
    def quadratic(x, a, b, c):
        #return a * x**2 + b * x + c
        return a*x**2 + b*x + c

    # If range values are specified, find the corresponding indices
    if range_start is not None:
        range_start_c = np.searchsorted(spaceVector, range_start)
    else:
        range_start_c = 0
        
    if range_end is not None:
        range_end_c = np.searchsorted(spaceVector, range_end)
    else:
        range_end_c = len(spaceVector)
    
    # Apply range if specified
    if range_start is not None and range_end is not None:
        spaceVector = spaceVector[range_start_c:range_end_c]
        spaceVector_m = spaceVector_m[range_start_c:range_end_c]
        phaseProfile = phaseProfile[range_start_c:range_end_c]

    # Fit the phaseProfile to a quadratic function
    popt_p, _ = curve_fit(quadratic, spaceVector.T, phaseProfile)
    popt, _ = curve_fit(quadratic, spaceVector_m.T, phaseProfile)

    # Extract the coefficients
    a_p, b_p, c_p = popt_p
    a, b, c = popt
    
    # Calculate the focal length
    focal = -np.pi / (a * wavelength)
    
    # Calculate the charge density
    chargeDensity = np.sqrt(1 / (Length * g11 * index0**3 * np.abs(focal)))
    
    # Return the results
    return focal, popt, popt_p, chargeDensity

#for characterizing thin charging crystals
def cd_1(matFilePath, save_path, cross_section, interaction_length, width,range_start, range_end):
    #get data from path
    data = scipy.io.loadmat(matFilePath)
    numericField = None

    #transpose and extract data
    for key in data:
        if isinstance(data[key], np.ndarray):
            numericField = data[key].T
            break

    #break if no data present
    if numericField is None:
        raise ValueError('No numeric field found in the structure.')

    #get number of rows and columns in data set
    rows, cols = numericField.shape

    #define constants
    wavelength = 970e-9
    index0 = 2.28
    g11 = 0.136
    interaction_length *= 1e-3
    
    #get phase profile slice in um and radians
    phaseProfile_um = numericField[round(rows / 2), :] - np.max(numericField[round(rows / 2), :])
    phaseProfile_rad = 2 * np.pi * phaseProfile_um / (wavelength * 1e6)
    N = len(phaseProfile_rad)
    
    #define spaceVector for plots
    crossSectionLength = cross_section * 1e-3
    spaceVector = np.linspace(0, crossSectionLength, N)
    spaceVector_mm = spaceVector * 1e3
    
    #generate figure space
    plt.figure(figsize=(20, 7))

    #generate title name from file name
    file_name = os.path.splitext(os.path.basename(matFilePath))[0]  # Extract file name without extension
    plt.suptitle(f'File: {file_name}', fontsize=14, fontweight='bold', y=1.05)  # Annotation above plots

    #phase profile in radians plot with fit
    plt.subplot(1, 3, 3)
    plt.plot(spaceVector_mm, phaseProfile_rad)
    focal, fq, fq_p, chargeDensity = calculate_charge_density(phaseProfile_rad, spaceVector_mm, wavelength, interaction_length, g11, index0,range_start,range_end)
    plt.plot(spaceVector_mm, np.polyval(fq_p, spaceVector_mm), label='Fit')
    plt.xlabel('Distance (mm)')
    plt.ylabel('Phase Retardation (Rad)')
    plt.title('Y Phase Slice (rad)')
    plt.legend()

    #calculate and display r^2 of fit
    r2=r2_score(np.polyval(fq_p, spaceVector_mm),phaseProfile_rad)
    # Display rms fit error
    plt.annotate(f'R^2 = {r2:.6f}', xy=(0,-3),xycoords='data', fontsize=10, bbox=dict(facecolor='white', alpha=0.8))

    #2D map of original data with charge density and focal length
    plt.subplot(1, 3, 1, aspect='auto')
    spaceVectorx = np.linspace(0, width * 1e-3, rows)
    limx = [np.min(spaceVector_mm), np.max(spaceVector_mm)]
    limy = [np.min(spaceVectorx * 1e3), np.max(spaceVectorx * 1e3)]
    plt.imshow(numericField, extent=(limx[0], limx[1], limy[0], limy[1]), aspect='auto', cmap='viridis_r')
    plt.colorbar()
    plt.xlabel('mm')
    plt.ylabel('mm')
    plt.title(f'Charge Density: {chargeDensity:.2f} C/m³ \n Focal Length: {abs(focal*1000):.2f} mm',horizontalalignment='center')

    #phase profile in um
    ySlice = numericField[round(rows / 2), :] - np.max(numericField[round(rows / 2), :])
    plt.subplot(1, 3, 2)
    plt.plot(spaceVector_mm, ySlice)
    plt.xlabel('Distance (mm)')
    plt.ylabel('Phase Retardation (um)')
    plt.title('Y Phase Slice (um)')

    # Save the plot if save_path is provided
    if save_path is not None:
        # Extract the base file name without extension from matFilePath
        file_name = os.path.splitext(os.path.basename(matFilePath))[0]
    
        # Append the directory and file name to the save_path
        save_path_with_name = os.path.join(os.path.dirname(save_path), file_name)
        
        plt.savefig(save_path_with_name, dpi=300, bbox_inches='tight')

    #show plot if desired. Suggest keeping supressed if running in a loop.    
    #plt.show()
    
    return focal, chargeDensity

# Example usage:
# fq, focal, chargeDensity, phaseProfile_um, phaseProfile_rad, spaceVector_mm, m_plot=cd_calc.cd_d1('path_to_matfile.mat','path_to_save' cross_section=1.20, interaction_length=4.00, width=3.15)

#for characterizing thick charging crystals
#see cd_1 for annotation
def cd_2 (matFilePath, save_path, cross_section, interaction_length, width):
    data = scipy.io.loadmat(matFilePath)
    numericField = None
    
    for key in data:
        if isinstance(data[key], np.ndarray):
            numericField = data[key].T
            break
    
    if numericField is None:
        raise ValueError('No numeric field found in the structure.')
    
    rows, cols = numericField.shape
    wavelength = 970e-9
    index0 = 2.28
    g11 = 0.136
    interaction_length *= 1e-3
    
    phaseProfile_um = -numericField[:, round(cols / 2)] - np.max(-numericField[:, round(cols / 2)])
    phaseProfile_rad = -2 * np.pi * phaseProfile_um / (wavelength * 1e6)
    N = len(phaseProfile_rad)
    
    crossSectionLength = cross_section * 1e-3
    spaceVector = np.linspace(0, crossSectionLength, N)
    spaceVector_mm = spaceVector * 1e3
    
    plt.figure(figsize=(20, 7))

    file_name = os.path.splitext(os.path.basename(matFilePath))[0]  # Extract file name without extension
    plt.suptitle(f'File: {file_name}', fontsize=14, fontweight='bold', y=1.05)  # Annotation above plots

    plt.subplot(1, 3, 3)
    plt.plot(spaceVector_mm, phaseProfile_rad)
    focal, fq, fq_p, chargeDensity = calculate_charge_density(phaseProfile_rad, spaceVector_mm, wavelength, interaction_length, g11, index0)
    plt.plot(spaceVector_mm, np.polyval(fq_p, spaceVector_mm), label='Fit')
    plt.xlabel('Distance (mm)')
    plt.ylabel('Phase Retardation (Rad)')
    plt.title('Y Phase Slice (rad)')
    plt.legend()
    plt.title(f'Charge Density: {chargeDensity:.2f} C/m³ \n Focal Length: {abs(focal*1000):.2f} mm',horizontalalignment='center')
    
    plt.subplot(1, 3, 1)
    spaceVectorx = np.linspace(0, width * 1e-3, rows)
    limx = [np.min(spaceVector_mm), np.max(spaceVector_mm)]
    limy = [np.min(spaceVectorx * 1e3), np.max(spaceVectorx * 1e3)]
    plt.imshow(numericField, extent=(limy[0], limy[1], limx[0], limx[1]), aspect='auto', cmap='viridis_r')
    plt.colorbar()
    plt.xlabel('mm')
    plt.ylabel('mm')
    plt.title('Original Image')
    
    ySlice = numericField[:, round(cols / 2)] - np.max(numericField[:, round(cols / 2)])
    plt.subplot(1, 3, 2)
    plt.plot(spaceVector_mm, ySlice)
    plt.xlabel('Distance (mm)')
    plt.ylabel('Phase Retardation (um)')
    plt.title('Y Phase Slice (um)')
    
    if save_path is not None:
        file_name = os.path.splitext(os.path.basename(matFilePath))[0]
    
        save_path_with_name = os.path.join(os.path.dirname(save_path), file_name)
        
        plt.savefig(save_path_with_name, dpi=300, bbox_inches='tight')    


    plt.show()
    
    return fq, focal, chargeDensity, phaseProfile_um, phaseProfile_rad
