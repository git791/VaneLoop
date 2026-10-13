import json
import os

import yaml
from lightgbm import LGBMRegressor
from onnxmltools.convert.lightgbm.operator_converters.LightGbm import convert_lightgbm
from skl2onnx import convert_sklearn, update_registered_converter
from skl2onnx.common.data_types import FloatTensorType
from skl2onnx.common.shape_calculator import calculate_linear_regressor_output_shapes

# Register LightGBM regressor converter with skl2onnx
update_registered_converter(
    LGBMRegressor,
    "LightGbmLGBMRegressor",
    calculate_linear_regressor_output_shapes,
    convert_lightgbm,
)


def export_model_to_onnx(
    models: dict,
    scaler,
    feature_names: list[str],
    output_dir: str = "ml/artifacts",
    metrics: dict | None = None,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    initial_type = [("float_input", FloatTensorType([None, len(feature_names)]))]
    for q, model in models.items():
        onnx_model = convert_sklearn(
            model,
            initial_types=initial_type,
            target_opset={"": 14, "ai.onnx.ml": 2},
        )
        onnx_path = os.path.join(output_dir, f"model_{q}.onnx")
        with open(onnx_path, "wb") as f:
            f.write(onnx_model.SerializeToString())
        print(f"Exported ONNX model to {onnx_path}")

    # Save Scaler params
    scaler_data = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}
    with open(os.path.join(output_dir, "scaler.json"), "w") as f:
        json.dump(scaler_data, f, indent=2)

    # Save Feature list
    with open(os.path.join(output_dir, "features.yaml"), "w") as f:
        yaml.dump(feature_names, f)

    # Save Version metadata
    metadata = {
        "version": "1.0.0",
        "model": "LightGBM Quantile Regressor",
        "target": "RUL capped at 125",
        "windows": [5, 10, 30],
    }
    with open(os.path.join(output_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    if metrics is not None:
        with open(os.path.join(output_dir, "metrics.json"), "w") as f:
            json.dump(metrics, f, indent=2)

    print(f"Exported artifacts to {output_dir}")
