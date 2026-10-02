import onnx
import onnxmltools
from skl2onnx import convert_sklearn, update_registered_converter
from skl2onnx.common.shape_calculator import calculate_linear_classifier_output_shapes
from onnxmltools.convert.lightgbm.operator_converters.LightGbm import convert_lightgbm
from skl2onnx.common.data_types import FloatTensorType
from lightgbm import LGBMRegressor
import numpy as np
import json
import yaml

# Register LightGBM converter with skl2onnx
update_registered_converter(
    LGBMRegressor, 'LightGbmLGBMRegressor',
    calculate_linear_classifier_output_shapes, convert_lightgbm,
    options={'nocl': [True, False], 'zipmap': [True, False, 'columns']}
)

def export_model_to_onnx(models, scaler, feature_names, output_dir="ml/artifacts"):
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    # We will export the p50 model as the main model for predictions. 
    # For a full implementation, we can export all three or use a custom PyTorch/ONNX graph.
    # Due to LightGBM ONNX constraints, we export them separately or just the p50 for now.
    
    model_p50 = models['p50']
    
    initial_type = [('float_input', FloatTensorType([None, len(feature_names)]))]
    onnx_model = convert_sklearn(model_p50, initial_types=initial_type, target_opset=12)
    
    onnx_path = os.path.join(output_dir, "model_p50.onnx")
    with open(onnx_path, "wb") as f:
        f.write(onnx_model.SerializeToString())
        
    print(f"Exported ONNX model to {onnx_path}")
    
    # Save Scaler params
    scaler_data = {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist()
    }
    with open(os.path.join(output_dir, "scaler.json"), "w") as f:
        json.dump(scaler_data, f)
        
    # Save Feature list
    with open(os.path.join(output_dir, "features.yaml"), "w") as f:
        yaml.dump(feature_names, f)
        
    # Save Version metadata
    metadata = {
        "version": "1.0.0",
        "model": "LightGBM Quantile Regressor",
        "target": "RUL capped at 125"
    }
    with open(os.path.join(output_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f)
        
    print(f"Exported artifacts to {output_dir}")
