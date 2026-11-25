# TubeBEND: attribution and licence

The files in `data/tubebend/derived/` are derived from the **TubeBEND**
dataset, the "Rotary Tube Bending Process Dataset", by:

- Zeyneddin Oz
- Jonas Knoche
- Alireza Yazdani
- Bernd Engel
- Kristof Van Laerhoven

It is published on Zenodo:
- Record: https://zenodo.org/records/18458823
- DOI: 10.5281/zenodo.18458823
- Concept DOI: 10.5281/zenodo.16614080

**Licence: Creative Commons Attribution 4.0 International (CC BY 4.0)**,
https://creativecommons.org/licenses/by/4.0/

The authors acknowledge DFG funding, Project-ID 520256321.

## What was changed

`runs.csv` is not the original data. It holds one row per valid bending run.
- **Runs dropped:** the three runs the authors record as failed (1 and 48: "Connection to machine failed"; 166: "Collision during program start").
- **Setup values:** copied from `bending_setups`.
- **Measured bend angle:** computed here. A circle is fitted to each 2 mm scan slice of both straight legs, and an axis through the circle centres. Springback = 47° − that angle.
- **Ovality and collapse:** maxima from the arc key-characteristics table.
- **Signal features:** peak, mean, impulse, rise time and end value, from the force sensors (100 Hz) and machine torques (20 Hz) during the bend window.

`signal_examples.json` holds downsampled force traces of runs 2, 100 and 250. The models in `artifacts/springback/` were trained on `runs.csv`.

The raw 797 MB pickle is not redistributed. `python -m pipeforge.springback_ml.download` fetches it from Zenodo and checks its md5.

## Please cite

```bibtex
@article{oz2025tubebend,
  title   = {TubeBEND: A Real-World Dataset for Geometry Prediction in Rotary Draw Bending},
  author  = {Oz, Zeyneddin and Knoche, Jonas and Yazdani, Alireza and Engel, Bernd and Van Laerhoven, Kristof},
  journal = {arXiv preprint arXiv:2509.10272},
  year    = {2025}
}
```

The authors' loader code (github.com/zeyneddinoz/tubebend) has no licence, so none of it is used here. The loader in `pipeforge/springback_ml/load.py` is written from scratch, with a restricted unpickler.
