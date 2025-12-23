The following Zemax models were used in the optimization of distances between optics, minimization of
clipping and prediction of expected resolvable spots in ReLOAD.

ReLOAD
- Full unfolded physically constrained ReLOAD-only Zemax file

ReLOAD_w_imaging_relay
- Full unfolded physically constrained ReLOAD with Imaging relay used in multipass spots

ReLOAD_w_spots
- Full unfolded physically constrained ReLOAD with single 1:1 imaging relay to diagnose expected spots

Files named "d#_determination" were used to determine ideal distances for collimation and conjugation
of a 920 nm beam independently, before these distances were ultimately input into ReLOAD.zmx 
See "Latest_distances_in_ReLOAD.pptx" for a diagram of what each distance is.

The only distance that was determined empirically using the Zemax mdoel to minimize clipping was d3. 
This distance was modified in the first instance of itself in the unfolded model with pickup solves 
on subsequent clone surfaces such that clipping could be minimized in a physically constrained way.
