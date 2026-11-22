# Amazon SageMaker và vòng đời huấn luyện, triển khai mô hình

Đưa một mô hình machine learning từ notebook lên production đòi hỏi nhiều công việc hơn việc gọi hàm fit. Nhóm phát triển phải chuẩn bị và kiểm soát dữ liệu, tạo môi trường huấn luyện lặp lại được, đánh giá mô hình trên tập dữ liệu phù hợp, quản lý phiên bản, triển khai an toàn, theo dõi chất lượng dự đoán và lên kế hoạch huấn luyện lại khi dữ liệu hoặc nhu cầu nghiệp vụ thay đổi.

**Amazon SageMaker AI** cung cấp môi trường và các dịch vụ được quản lý để thực hiện những bước này. SageMaker AI có thể chạy data processing jobs, training jobs, hyperparameter tuning, workflow pipelines, Model Registry và các lựa chọn inference như real-time endpoint, serverless, asynchronous hoặc batch transform. Các thành phần có thể kết hợp với Amazon S3, AWS IAM, AWS KMS, Amazon ECR, Amazon CloudWatch, AWS Step Functions và những dịch vụ dữ liệu khác.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, SageMaker AI giúp người học thiết kế và triển khai ứng dụng machine learning an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. Bài học tập trung vào vòng đời end-to-end, cách chọn job và kiểu deployment, cách quản lý model artifacts, quyền truy cập, promotion và vận hành mô hình sau khi phát hành.

## 1. Amazon SageMaker AI giải quyết vấn đề gì?

Một dự án ML thường cần nhiều môi trường và nhóm phối hợp:

- Data engineer thu thập, làm sạch, biến đổi và kiểm tra dữ liệu.
- Data scientist thử nghiệm thuật toán, feature và hyperparameter.
- ML engineer đóng gói training/inference code, quản lý model artifact và triển khai.
- Platform engineer quản lý IAM, network, compute, logging, quota và chi phí.
- Model owner theo dõi chất lượng, drift, bias, SLO và phê duyệt phiên bản.

Nếu mỗi nhóm tự xây dựng script, máy chủ và quy trình phát hành riêng, việc tái lập kết quả, kiểm soát quyền và truy tìm nguyên nhân lỗi sẽ khó khăn. SageMaker AI cung cấp các job type và API quản lý vòng đời trên hạ tầng AWS, giúp tách code ML khỏi việc tự vận hành toàn bộ compute.

SageMaker AI không tự bảo đảm mô hình chính xác hoặc không thiên lệch. Nhóm ML vẫn phải xác định mục tiêu, chất lượng dữ liệu, metric đánh giá, ngưỡng chấp nhận, kiểm soát rủi ro và quy trình phê duyệt.

## 2. Bản đồ vòng đời machine learning

Một quy trình phổ biến gồm các giai đoạn:

~~~mermaid
flowchart TD
    A[Business objective and data] --> B[Explore and validate data]
    B --> C[Processing and feature engineering]
    C --> D[Training job]
    D --> E[Evaluation and tuning]
    E --> F{Meets acceptance criteria?}
    F -->|No| C
    F -->|Yes| G[Model Registry]
    G --> H[Approval]
    H --> I[Deployment]
    I --> J[Inference traffic]
    J --> K[Metrics, logs and quality signals]
    K --> L{Drift or quality regression?}
    L -->|Yes| C
    L -->|No| J
~~~

| Giai đoạn | Câu hỏi cần trả lời | Thành phần SageMaker AI thường dùng |
|---|---|---|
| Khám phá dữ liệu | Dữ liệu có đúng, đủ và đại diện không? | Studio, notebooks, Data Wrangler, Processing |
| Feature engineering | Feature được tạo và tái sử dụng ra sao? | Processing, Feature Store |
| Huấn luyện | Chạy thuật toán nào, trên compute nào? | Training jobs |
| Tối ưu | Hyperparameter nào cho kết quả tốt? | Automatic Model Tuning |
| Tự động hóa | Làm sao chạy lại pipeline có kiểm soát? | SageMaker Pipelines |
| Quản lý phiên bản | Model nào đã được đánh giá và duyệt? | Model Registry |
| Triển khai | Online hay offline inference? | Endpoints, Batch Transform |
| Vận hành | Model có còn đáp ứng SLO và chất lượng? | CloudWatch, logging, monitoring workflow |

Không phải dự án nào cũng cần mọi thành phần. Một mô hình batch nhỏ có thể chỉ cần Processing, Training và Batch Transform. Một dịch vụ dự đoán trực tuyến quan trọng có thể cần Pipelines, Model Registry, endpoint deployment guardrails, autoscaling và giám sát chuyên sâu.

## 3. Các khái niệm và thành phần chính

| Thành phần | Vai trò |
|---|---|
| SageMaker Studio | Môi trường làm việc cho data scientist và ML engineer |
| Processing job | Chạy tiền xử lý, feature engineering, đánh giá và script tùy chỉnh |
| Training job | Huấn luyện mô hình trên compute do SageMaker AI quản lý |
| Hyperparameter tuning job | Tạo nhiều training jobs để tìm cấu hình tốt |
| Feature Store | Lưu và phục vụ feature cho training và inference |
| Pipelines | Điều phối các bước ML thành workflow có thể chạy lại |
| Model Registry | Quản lý model package groups, versions và approval status |
| Model | Định nghĩa model artifact và container dùng để inference |
| Endpoint | Cung cấp API inference được quản lý |
| Batch Transform | Chạy inference trên dataset mà không cần endpoint luôn hoạt động |

Tên giao diện có thể thay đổi giữa SageMaker Studio và Studio Classic; API và SDK cũng có phiên bản riêng. Khi triển khai, kiểm tra tài liệu theo experience và SDK version đang sử dụng.

## 4. Xác định bài toán và metric trước khi huấn luyện

Trước khi tạo training job, cần xác định:

1. Bài toán là classification, regression, ranking, forecasting, clustering hay generative AI.
2. Đơn vị dự đoán là gì: giao dịch, khách hàng, phiên truy cập hay khoảng thời gian.
3. Metric chính là gì: precision, recall, F1, ROC-AUC, PR-AUC, RMSE, MAE, latency hoặc business metric.
4. Ngưỡng tối thiểu để được đưa vào production.
5. Chi phí của false positive và false negative.
6. Ràng buộc latency, throughput, explainability, fairness và dữ liệu nhạy cảm.

Accuracy có thể gây hiểu lầm khi lớp dương rất hiếm. Ví dụ, hệ thống phát hiện gian lận có 1% giao dịch gian lận; mô hình luôn dự đoán "không gian lận" vẫn đạt 99% accuracy nhưng không phát hiện được giao dịch cần xử lý. Chọn metric phải phù hợp với hậu quả nghiệp vụ.

## 5. Chuẩn bị dữ liệu và tránh data leakage

Chất lượng mô hình bị giới hạn bởi chất lượng dữ liệu và cách tạo tập train/validation/test.

- Kiểm tra schema, kiểu dữ liệu, null, duplicate, outlier và giá trị bất hợp lệ.
- Chuẩn hóa timezone, đơn vị đo, encoding và quy tắc xử lý categorical features.
- Xác định label, thời điểm label có sẵn và độ trễ cập nhật.
- Chia train/validation/test theo thời gian hoặc entity phù hợp với cách mô hình được dùng.
- Lưu version của dataset, code preprocessing và feature definitions.
- Kiểm tra phân phối giữa các tập và các nhóm nghiệp vụ quan trọng.

Data leakage xảy ra khi training data chứa thông tin mà hệ thống thực tế chưa thể biết tại thời điểm dự đoán. Ví dụ, dự đoán khách hàng rời bỏ trong 30 ngày nhưng dùng một cột được cập nhật sau khi khách hàng đã rời bỏ. Mô hình có thể đạt điểm rất cao trong validation nhưng thất bại trong production.

Với dữ liệu chuỗi thời gian, dùng time-based split và point-in-time feature retrieval. Với nhiều bản ghi cho cùng một khách hàng, cần cân nhắc group split để các bản ghi của cùng entity không rò rỉ giữa train và test.

## 6. SageMaker Processing cho tiền xử lý và đánh giá

SageMaker Processing chạy script hoặc container trên hạ tầng được quản lý. Khi job bắt đầu, SageMaker AI cấp compute, đưa input vào container, chạy lệnh và ghi output tới Amazon S3. Sau khi job hoàn tất, compute được giải phóng.

Các use case:

- Làm sạch dữ liệu và xử lý missing values.
- Feature engineering và chuẩn hóa.
- Chia train/validation/test.
- Tính thống kê dữ liệu và kiểm tra chất lượng.
- Đánh giá model artifact trên tập holdout.
- Tạo báo cáo và dữ liệu đầu vào cho bước đăng ký model.

Processing có thể dùng built-in processing container hoặc custom Docker image. Input thường lấy từ S3; có thể kết hợp Athena hoặc Redshift làm nguồn theo cấu hình hỗ trợ.

~~~mermaid
flowchart LR
    A[Amazon S3 input] --> B[SageMaker Processing job]
    C[Processing container] --> B
    B --> D[Cleaned data]
    B --> E[Feature datasets]
    B --> F[Evaluation reports]
    D --> G[Training job]
~~~

Processing job không phải một notebook kernel tồn tại liên tục. Nó là job có cấu hình compute, input/output, role và command rõ ràng, phù hợp cho bước tiền xử lý lặp lại trong pipeline.

## 7. Feature engineering và Amazon SageMaker Feature Store

Feature là các thuộc tính đầu vào mà mô hình sử dụng để dự đoán. Nếu training pipeline và inference application tự tính feature theo hai cách khác nhau, có thể xảy ra training-serving skew.

SageMaker Feature Store cung cấp feature groups để lưu, khám phá, tái sử dụng và phục vụ feature.

| Store | Mục đích | Đặc điểm |
|---|---|---|
| Online store | Real-time inference | Lưu bản ghi mới nhất theo record identifier, truy xuất độ trễ thấp |
| Offline store | Training, exploration, batch inference | Lưu lịch sử feature trên S3, hỗ trợ truy vấn phân tích |
| Online + Offline | Dùng chung feature cho training và serving | Hai store được đồng bộ theo cấu hình hỗ trợ |

Feature group có record identifier và event time. Event time giúp xác định feature nào có hiệu lực tại thời điểm của một quan sát, hỗ trợ point-in-time correct training data.

Lưu ý:

- Online store thường chỉ giữ giá trị mới nhất, phục vụ lookup nhanh qua API.
- Offline store giữ lịch sử và thường lưu dữ liệu dưới dạng Parquet trên S3.
- Có thể ingest feature theo batch hoặc streaming qua API như PutRecord.
- Feature group có thể cấu hình online, offline hoặc cả hai.
- Online store loại InMemory hiện không hỗ trợ cấu hình online+offline replication; cần kiểm tra storage type trước khi thiết kế.

Không chọn Feature Store chỉ vì mọi mô hình đều cần một feature database. Với pipeline nhỏ, bảng curated trong S3 có thể đủ. Feature Store hữu ích khi cần tái sử dụng feature, nhất quán train/serve, online lookup và governance tập trung.

## 8. Tạo và cấu hình Training Job

SageMaker Training job chạy thuật toán trong container trên instance do dịch vụ cấp. Người dùng chỉ định:

- Algorithm/container image.
- Hyperparameters.
- Input channels và vị trí dữ liệu.
- Compute instance type và số lượng instance.
- EBS volume, encryption và network configuration.
- IAM execution role.
- Output S3 path cho model artifacts.
- Stopping condition và metric definitions.

Khi job hoàn tất, SageMaker AI lưu model artifacts vào S3 location đã chỉ định. Artifact này có thể được dùng để tạo SageMaker Model và deploy lên endpoint hoặc dùng ngoài SageMaker nếu runtime tương thích.

### Ba lựa chọn container

| Cách huấn luyện | Đặc điểm | Khi phù hợp |
|---|---|---|
| Built-in algorithm | AWS cung cấp algorithm và container | Bài toán phổ biến, muốn giảm công việc đóng gói |
| Framework container | Dùng PyTorch, TensorFlow, XGBoost hoặc framework hỗ trợ | Cần kiểm soát training code và thư viện |
| Custom container | Tự đóng gói image trên ECR | Framework, dependency hoặc runtime đặc thù |

### Training container paths

SageMaker Training Toolkit sử dụng các thư mục chuẩn bên trong container, ví dụ:

- /opt/ml/input/data/<channel>: dữ liệu input channel.
- /opt/ml/model: nơi ghi model artifacts cuối cùng.
- /opt/ml/checkpoints: nơi lưu checkpoint.
- /opt/ml/input/config/hyperparameters.json: hyperparameters được truyền vào job.
- /opt/ml/output: output và thông tin trạng thái của container.

Code training cần ghi model vào vị trí đúng để SageMaker AI đóng gói và upload artifact. Với custom container, phải kiểm thử contract về environment, signal kết thúc, checkpoint và output path.

## 9. Ví dụ tạo Training Job bằng boto3

Ví dụ dưới đây minh họa cấu trúc API CreateTrainingJob. Thay account, Region, image URI, role, S3 path, hyperparameter và instance type bằng giá trị đã được phê duyệt trong môi trường thực tế.

~~~python
import boto3

sm = boto3.client("sagemaker", region_name="ap-southeast-1")

response = sm.create_training_job(
    TrainingJobName="churn-xgboost-2026-11-20",
    RoleArn="arn:aws:iam::111122223333:role/SageMakerTrainingRole",
    AlgorithmSpecification={
        "TrainingImage": (
            "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/"
            "my-xgboost-training:1"
        ),
        "TrainingInputMode": "File",
    },
    InputDataConfig=[
        {
            "ChannelName": "train",
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": "s3://ml-data/churn/train/",
                    "S3DataDistributionType": "FullyReplicated",
                }
            },
            "ContentType": "text/csv",
        },
        {
            "ChannelName": "validation",
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": "s3://ml-data/churn/validation/",
                    "S3DataDistributionType": "FullyReplicated",
                }
            },
            "ContentType": "text/csv",
        },
    ],
    OutputDataConfig={
        "S3OutputPath": "s3://ml-artifacts/churn/training/",
        "KmsKeyId": "arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555",
    },
    ResourceConfig={
        "InstanceType": "ml.m5.xlarge",
        "InstanceCount": 1,
        "VolumeSizeInGB": 50,
    },
    HyperParameters={
        "objective": "binary:logistic",
        "num_round": "200",
        "max_depth": "6",
        "eta": "0.1",
    },
    StoppingCondition={"MaxRuntimeInSeconds": 3600},
)

print(response["TrainingJobArn"])
~~~

Ví dụ dùng custom image URI minh họa; với built-in algorithm hoặc framework container, lấy image URI tương ứng từ tài liệu SageMaker AI cho Region và version. Không hard-code credential trong script; dùng execution role và cấu hình bảo mật của job.

## 10. Distributed training

Khi dữ liệu hoặc mô hình lớn, một instance có thể không đủ compute hoặc memory. SageMaker AI hỗ trợ distributed training cho nhiều framework.

- **Data parallelism:** chia mini-batch/dữ liệu cho nhiều worker; mỗi worker có bản sao mô hình và đồng bộ gradient.
- **Model parallelism:** chia các phần của mô hình giữa nhiều worker khi một model không vừa bộ nhớ một accelerator hoặc cần phân phối phép tính.

Có thể kết hợp hai cách cho mô hình lớn. Hiệu quả phụ thuộc interconnect, framework, batch size, communication overhead và khả năng cân bằng tải.

Không tăng số GPU chỉ vì job chạy lâu. Trước tiên đo GPU utilization, data loading, CPU, network, memory và thời gian đồng bộ. Nếu GPU chờ đọc dữ liệu, tăng GPU count có thể làm chi phí tăng mà throughput không cải thiện.

## 11. Hyperparameter tuning với Automatic Model Tuning

Hyperparameters là các tham số được chọn trước hoặc trong quá trình huấn luyện, ví dụ learning rate, tree depth, regularization, batch size hoặc số epoch. Automatic Model Tuning (AMT) tạo nhiều training jobs với các cấu hình khác nhau và chọn cấu hình tốt nhất theo objective metric.

| Strategy | Đặc điểm | Khi phù hợp |
|---|---|---|
| Random | Thử các điểm ngẫu nhiên trong search space | Baseline đơn giản, không gian lớn |
| Bayesian | Dùng kết quả trước đó để chọn cấu hình tiếp theo | Training job tốn thời gian, cần khai thác kết quả đã biết |
| Hyperband | Phân bổ tài nguyên động, dừng cấu hình kém sớm | Thuật toán có metric trung gian theo epoch/iteration |
| Grid | Thử tổ hợp giá trị categorical đã khai báo | Search space nhỏ, rời rạc |

Trước khi tuning, phải có training job chạy thành công, xác định search space hợp lý và objective metric có ý nghĩa. Tuning không tự bảo đảm tìm được nghiệm tối ưu toàn cục; kết quả còn phụ thuộc dữ liệu, thuật toán và phạm vi tìm kiếm.

Đặt giới hạn số training jobs song song, tổng số jobs, thời gian và chi phí. Dùng early stopping hoặc completion criteria khi phù hợp để tránh tiêu thụ compute cho các cấu hình kém.

## 12. Checkpoint và Managed Spot Training

Checkpoint lưu trạng thái trung gian của mô hình trong quá trình huấn luyện. Khi job bị gián đoạn, có thể khôi phục từ checkpoint thay vì chạy lại từ đầu.

SageMaker AI có thể đồng bộ checkpoint từ thư mục local của training container lên S3 và đưa checkpoint đã lưu về container khi job khởi động lại.

Managed Spot Training sử dụng EC2 Spot capacity cho training job để giảm chi phí. Tuy nhiên:

- Spot instance có thể bị thu hồi, khiến job phải chờ hoặc khởi động lại.
- Checkpoint cần được cấu hình để tiếp tục từ trạng thái gần nhất.
- Managed Spot Training không tự fallback sang On-Demand nếu Spot capacity không có.
- MaxWaitTimeInSeconds phải lớn hơn MaxRuntimeInSeconds.
- TrainingTimeInSeconds có thể bao gồm cả thời gian chờ và gián đoạn; BillableTimeInSeconds phản ánh thời gian tính phí theo cơ chế dịch vụ.

Managed Spot phù hợp với training job có thể chịu gián đoạn và có checkpoint tốt. Với job cần hoàn tất đúng deadline hoặc không thể resume, On-Demand có thể phù hợp hơn.

## 13. Đánh giá mô hình và chọn candidate

Training loss thấp không đồng nghĩa mô hình tổng quát tốt. Cần đánh giá trên validation và test set không bị rò rỉ.

1. Tính metric theo đúng bài toán và business objective.
2. So sánh với baseline và model đang chạy.
3. Kiểm tra performance theo từng segment hoặc nhóm người dùng.
4. Kiểm tra calibration và threshold nếu quyết định dựa trên xác suất.
5. Đánh giá latency, memory footprint và chi phí inference.
6. Lưu báo cáo, dataset version, code version, hyperparameters và artifact URI.

Với classification, có thể xem confusion matrix, precision, recall, F1, ROC-AUC và PR-AUC. Với regression, xem MAE, RMSE, residual distribution và sai số theo segment. Với forecasting, dùng split theo thời gian và metric phù hợp với scale dữ liệu.

Không chọn model chỉ theo một metric tổng thể nếu model có thể gây hại không đồng đều giữa các nhóm hoặc trong các trường hợp hiếm nhưng quan trọng.

## 14. SageMaker Pipelines để tự động hóa workflow

SageMaker Pipelines là dịch vụ điều phối workflow ML. Pipeline được biểu diễn thành DAG gồm các step và dependency. Mỗi step có thể gọi Processing, Training, Tuning, Transform, Model registration, condition hoặc các hành động được hỗ trợ.

~~~mermaid
flowchart TD
    A[Parameters: dataset URI, model config] --> B[Processing: validate and split]
    B --> C[Training]
    C --> D[Evaluation Processing]
    D --> E{Metric meets threshold?}
    E -->|No| F[Fail / stop]
    E -->|Yes| G[Register model]
    G --> H[Approval]
    H --> I[Deployment pipeline]
~~~

Pipeline giúp chuẩn hóa cách chạy và tạo lineage giữa input, job, output và model package. Có thể dùng SDK, API hoặc giao diện Studio để định nghĩa workflow.

### Step caching

SageMaker Pipelines hỗ trợ caching cho một số loại step như Processing, Training, Tuning và Transform. Caching tắt mặc định và phải bật tường minh. Khi signature của step khớp với một lần chạy thành công trước đó trong thời hạn cache, pipeline có thể dùng lại output thay vì chạy lại step.

Chỉ cache khi input và configuration thực sự đại diện cho cùng phép tính. Nếu dữ liệu thay đổi nhưng URI không đổi hoặc dependency bên ngoài không được đưa vào cache key, kết quả cũ có thể bị tái sử dụng sai. Dùng immutable dataset version hoặc manifest để đảm bảo tính tái lập.

## 15. Model Registry và quản lý phiên bản

SageMaker Model Registry là kho quản lý model packages theo nhóm và version. Model package lưu thông tin model artifact, inference specification, metadata và approval status.

- **Model package group:** nhóm các version của cùng một model/product.
- **Model package version:** một model được đăng ký trong group, có version tăng dần.
- **Approval status:** trạng thái phê duyệt, thường gồm PendingManualApproval, Approved hoặc Rejected.
- **Model metadata:** metric, dataset reference, training job, inference image và thông tin bổ sung.

Quy trình mẫu:

1. Training job tạo model artifact trên S3.
2. Evaluation job kiểm tra metric và tạo báo cáo.
3. Pipeline đăng ký model package vào Model Registry.
4. Model owner xem xét metric, lineage và risk.
5. Model package được Approved hoặc Rejected.
6. Deployment pipeline chỉ chọn model package đủ điều kiện.

Model Registry giúp trả lời model nào đang chạy, được tạo từ dữ liệu nào và ai đã phê duyệt. Nó không tự động chứng minh model tốt; tiêu chí phê duyệt phải do tổ chức xác định.

## 16. Đóng gói model để inference

Để deploy, cần có model artifact và inference container tương thích. SageMaker Model thường tham chiếu:

- Model artifact URI trên S3.
- Inference container image URI trong Amazon ECR hoặc image được dịch vụ hỗ trợ.
- Execution role cho model/container.
- VPC, KMS và network isolation nếu cần.
- Environment variables hoặc cấu hình runtime.

Với framework container, cần bảo đảm thư viện inference tương thích với model artifact. Với custom container, container phải triển khai inference server và đáp ứng contract của SageMaker AI, ví dụ nhận request trên endpoint nội bộ theo chuẩn hosting.

Không đưa credential, API key hoặc secret vào image hoặc model artifact. Dùng IAM role, AWS Secrets Manager hoặc cơ chế secret injection được phê duyệt.

### Ví dụ tạo model và endpoint bằng boto3

Sau khi training job hoàn tất, lấy S3 model artifact URI từ kết quả DescribeTrainingJob. Ví dụ dưới đây minh họa các bước tạo SageMaker Model, endpoint configuration và endpoint:

~~~python
import boto3

sm = boto3.client("sagemaker", region_name="ap-southeast-1")

model_name = "churn-model-v1"
endpoint_config_name = "churn-endpoint-config-v1"
endpoint_name = "churn-endpoint"

sm.create_model(
    ModelName=model_name,
    ExecutionRoleArn="arn:aws:iam::111122223333:role/SageMakerInferenceRole",
    PrimaryContainer={
        "Image": (
            "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/"
            "my-xgboost-inference:1"
        ),
        "ModelDataUrl": (
            "s3://ml-artifacts/churn/training/model.tar.gz"
        ),
    },
)

sm.create_endpoint_config(
    EndpointConfigName=endpoint_config_name,
    ProductionVariants=[
        {
            "VariantName": "AllTraffic",
            "ModelName": model_name,
            "InitialInstanceCount": 2,
            "InstanceType": "ml.m5.xlarge",
            "InitialVariantWeight": 1.0,
        }
    ],
)

sm.create_endpoint(
    EndpointName=endpoint_name,
    EndpointConfigName=endpoint_config_name,
)

sm.get_waiter("endpoint_in_service").wait(
    EndpointName=endpoint_name
)
~~~

Khi endpoint ở trạng thái InService, ứng dụng có thể gửi request bằng SageMaker Runtime:

~~~python
runtime = boto3.client("sagemaker-runtime", region_name="ap-southeast-1")

response = runtime.invoke_endpoint(
    EndpointName="churn-endpoint",
    ContentType="application/json",
    Accept="application/json",
    Body=b'{"instances":[[0.2, 12, 3, 450.0]]}',
)

print(response["Body"].read().decode("utf-8"))
~~~

Payload chỉ là ví dụ. Schema và ContentType phải khớp inference container; không gửi dữ liệu production nhạy cảm vào endpoint thử nghiệm. Trong môi trường production, quản lý endpoint name, model version, instance count và network settings bằng IaC hoặc deployment pipeline.

## 17. Chọn hình thức inference

SageMaker AI cung cấp bốn lựa chọn inference phổ biến:

| Hình thức | Đặc điểm | Use case |
|---|---|---|
| Real-time endpoint | Endpoint luôn sẵn sàng, độ trễ thấp, autoscaling | API tương tác, dự đoán cho request trực tuyến |
| Serverless Inference | Tự quản lý capacity, tính phí theo compute sử dụng, có thể cold start | Traffic không đều, có thời gian idle |
| Asynchronous Inference | Queue request, xử lý payload lớn hoặc thời gian dài, trả kết quả qua S3/notification | Phân tích ảnh/tài liệu, tác vụ near-real-time lâu |
| Batch Transform | Chạy inference trên dataset lớn theo job, không cần endpoint liên tục | Scoring hàng triệu bản ghi theo lịch |

Giới hạn payload/thời gian tham khảo theo tài liệu hiện hành:

| Hình thức | Payload tối đa tham khảo | Thời gian xử lý |
|---|---:|---|
| Real-time | 25 MB | 60 giây với response thông thường; streaming response có giới hạn riêng |
| Serverless | 4 MB | 60 giây |
| Asynchronous | 1 GB | Tối đa khoảng 1 giờ |
| Batch Transform | Dataset lớn, có thể hàng GB | Job có thể chạy nhiều giờ hoặc nhiều ngày |

Giới hạn có thể thay đổi theo container, loại endpoint, Region và quota. Kiểm tra API/service quotas trước khi thiết kế payload lớn hoặc thời gian xử lý dài.

### Cách chọn nhanh

- Cần latency thấp và traffic ổn định: Real-time.
- Traffic thưa, chấp nhận cold start: Serverless.
- Request lớn hoặc xử lý lâu, chấp nhận queue: Asynchronous.
- Có sẵn dataset và không cần response trực tiếp: Batch Transform.

## 18. Real-time endpoint và autoscaling

Real-time endpoint gồm model, endpoint configuration và endpoint. Endpoint configuration xác định production variants, instance type/count, model, accelerator hoặc inference configuration phù hợp.

Khi tạo endpoint, SageMaker AI cấp compute và khởi chạy inference container. Ứng dụng gọi endpoint qua API như InvokeEndpoint.

### Autoscaling

Application Auto Scaling có thể điều chỉnh số instance của production variant dựa trên metric. Target tracking thường là lựa chọn dễ vận hành: chọn metric và target value, dịch vụ tự tạo CloudWatch alarms và điều chỉnh capacity.

Metric phổ biến là InvocationsPerInstance. Nếu target quá cao, instance có thể quá tải trước khi scale-out hoàn tất; nếu target quá thấp, hệ thống có thể duy trì capacity dư thừa. Cần kiểm tra:

- Request rate và concurrency.
- Model loading/cold start time.
- CPU/GPU/memory utilization.
- Invocation latency p50/p95/p99.
- Scale-out time và cooldown.
- Min/max instance count.

Autoscaling không thay thế capacity test. Cần load test với burst, payload thực tế và failure scenario.

## 19. Asynchronous Inference và Batch Transform

### Asynchronous Inference

Asynchronous endpoint nhận request, đưa vào queue và xử lý sau. Client không cần giữ kết nối mở trong toàn bộ thời gian model chạy. Output được lưu vào S3; có thể cấu hình SNS notification để thông báo kết quả.

Có thể scale endpoint về zero khi không có request chờ xử lý, giúp giảm chi phí cho workload không liên tục. Tuy nhiên, request sẽ phải chờ endpoint scale lên khi có traffic mới.

### Batch Transform

Batch Transform tạo job để chạy inference trên dữ liệu được lưu trong S3. Job đọc input, phân phối dữ liệu cho instance và ghi kết quả ra S3.

Batch Transform phù hợp với scoring theo lịch, backfill, đánh giá trên tập lớn và xử lý offline. Không cần duy trì endpoint sau khi job kết thúc.

Không dùng Batch Transform nếu ứng dụng cần trả kết quả cho từng request tương tác ngay lập tức; khi đó hãy xem real-time hoặc asynchronous endpoint.

## 20. Deployment guardrails: Blue/Green, Canary và Linear

Khi cập nhật model hoặc container của endpoint production, cần giới hạn ảnh hưởng nếu phiên bản mới bị lỗi.

Blue/Green deployment tạo fleet mới (green) song song với fleet cũ (blue), sau đó chuyển traffic theo chiến lược đã chọn. Có thể cấu hình CloudWatch alarms và baking period; nếu alarm vi phạm, SageMaker AI tự rollback về fleet cũ.

| Chiến lược | Cách chuyển traffic | Đặc điểm |
|---|---|---|
| All at once | Chuyển toàn bộ traffic trong một bước | Nhanh, blast radius lớn |
| Canary | Chuyển một phần nhỏ trước, quan sát rồi chuyển phần còn lại | Giới hạn rủi ro trong giai đoạn thử |
| Linear | Chuyển theo nhiều bước với tỷ lệ tăng dần | Kiểm soát chi tiết hơn, kéo dài rollout |
| Rolling | Thay instance theo từng batch | Giảm nhu cầu capacity bổ sung so với blue/green đầy đủ |

~~~mermaid
flowchart TD
    A[Old model: Blue 100%] --> B[Deploy Green fleet]
    B --> C[Shift small canary traffic]
    C --> D[CloudWatch alarms and baking period]
    D --> E{Healthy?}
    E -->|Yes| F[Shift more traffic]
    F --> G[Green receives 100%]
    E -->|No| H[Auto rollback to Blue]
~~~

Canary/linear blue-green thường giữ hai fleet hoạt động trong giai đoạn rollout, nên có thể phát sinh chi phí capacity song song. Rolling deployment giảm overhead capacity nhưng vẫn cần baking period, alarm và rollback strategy.

Không phải mọi endpoint configuration đều hỗ trợ mọi deployment guardrail. Kiểm tra danh sách exclusions và prerequisites trước khi chọn chiến lược.

## 21. Shadow testing và kiểm thử trước phát hành

Shadow testing triển khai phiên bản mới song song với phiên bản hiện tại và gửi bản sao request production tới model mới. Response của shadow variant được ghi lại để so sánh nhưng không thay response trả cho user.

Shadow testing phù hợp khi:

- Muốn so sánh model mới trên traffic thật.
- Không muốn model mới ảnh hưởng kết quả người dùng.
- Cần kiểm tra latency, error, resource usage và output distribution.

Shadow test không tự chứng minh model tốt hơn. Cần có metric đánh giá, cách liên kết prediction với ground truth và quy trình phân tích kết quả.

Trước khi phát hành, kiểm tra cả model quality và serving quality: schema, payload, error handling, timeout, retry, concurrency, autoscaling, logging và security.

## 22. Monitoring endpoint bằng Amazon CloudWatch

CloudWatch thu thập metrics và logs cho SageMaker AI. Một số metric endpoint thường dùng:

| Nhóm | Metric/Signal | Ý nghĩa |
|---|---|---|
| Traffic | Invocations | Số request inference |
| Error | Invocation4XXErrors, Invocation5XXErrors | Lỗi client hoặc server |
| Latency | ModelLatency, OverheadLatency | Thời gian xử lý model và overhead endpoint |
| Capacity | CPUUtilization, MemoryUtilization, GPUUtilization | Mức sử dụng tài nguyên |
| Scaling | InvocationsPerInstance | Tải trên mỗi instance |
| Async | ApproximateBacklogSize, backlog age | Queue đang tồn đọng và thời gian chờ |
| Cost | Instance hours, invocation/compute usage | Mức tiêu thụ tài nguyên và chi phí |

Tạo CloudWatch alarms cho latency p95/p99, 5xx rate, throttling, backlog age và utilization. Chọn ngưỡng theo SLO và baseline của workload; không dùng một threshold chung cho mọi model.

CloudWatch metrics giúp phát hiện sự cố hạ tầng và serving. Chúng không tự cho biết prediction còn chính xác hay không.

## 23. Theo dõi chất lượng, drift và bias

Sau khi deploy, phân phối dữ liệu production có thể khác training data. Khái niệm cần phân biệt:

- **Data drift:** phân phối input/features thay đổi.
- **Concept drift:** quan hệ giữa feature và target thay đổi theo thời gian.
- **Model quality degradation:** metric dự đoán thực tế giảm khi có ground truth.
- **Bias/fairness issue:** hiệu năng hoặc tác động không công bằng giữa các nhóm.
- **Feature attribution drift:** lý do mô hình đưa ra dự đoán thay đổi đáng kể.

Để đo model quality, cần thu thập prediction và liên kết với ground truth sau khi label có sẵn. Chỉ quan sát input distribution không đủ để khẳng định accuracy đã giảm.

### Lưu ý về Model Monitor và Clarify

Theo tài liệu AWS hiện hành, Amazon SageMaker Model Monitor và Amazon SageMaker Clarify không còn mở cho khách hàng mới; khách hàng hiện hữu có thể tiếp tục sử dụng. Vì vậy, không mặc định hai dịch vụ này là lựa chọn có thể bật mới trong mọi account.

Với account đã có quyền sử dụng, Model Monitor có thể theo dõi data quality, model quality, bias drift và feature attribution drift. Clarify cung cấp phân tích fairness, bias và explainability như SHAP.

AWS công bố hướng thay thế cho các use case monitoring/clarify gồm các monitoring solutions mã nguồn mở do AWS phát hành, standardized bias metrics, thư viện SHAP, SageMaker AI MLflow, CloudWatch, QuickSight và Amazon Bedrock Evaluations. Cần lựa chọn thành phần theo loại mô hình và nhu cầu; Bedrock Evaluations phù hợp cho các use case generative AI, không phải thay thế trực tiếp mọi metric cho mô hình tabular truyền thống.

Nếu account không đủ điều kiện dùng Model Monitor/Clarify, có thể xây dựng pipeline riêng:

1. Capture input, output, timestamp và model version theo chính sách privacy.
2. Lưu prediction và ground truth ở S3.
3. Chạy Processing job hoặc workflow Spark để tính drift và quality metrics.
4. Ghi metric vào CloudWatch.
5. Tạo alarm và notification qua SNS/EventBridge.
6. Tạo ticket hoặc trigger retraining workflow có phê duyệt.

## 24. Quản lý model lifecycle và retraining

Một model không nên được retrain chỉ vì đã đến một ngày cố định nếu dữ liệu và chất lượng chưa được đánh giá. Ngược lại, không nên chờ đến khi user khiếu nại mới phát hiện model đã drift.

Thiết kế trigger retraining dựa trên:

- Lịch định kỳ phù hợp với tốc độ thay đổi dữ liệu.
- Data drift vượt ngưỡng.
- Model quality giảm khi ground truth đã có.
- Business rule hoặc sản phẩm thay đổi.
- Dataset mới đủ lớn và đã được kiểm tra chất lượng.
- Model version mới vượt baseline theo acceptance criteria.

Pipeline retraining nên chạy qua các bước validate data, train, evaluate, register, approve và deploy. Không tự động promote model chỉ vì training job thành công.

## 25. Bảo mật và quản lý quyền

SageMaker AI xử lý dữ liệu, model artifacts và inference request, vì vậy cần bảo vệ nhiều lớp:

- IAM execution role: cấp quyền tối thiểu cho S3, ECR, KMS, CloudWatch và các dịch vụ cần thiết.
- S3: bucket/prefix riêng cho input, output, artifacts và logs; bật encryption và block public access.
- KMS: dùng customer managed key khi cần kiểm soát key policy, rotation và audit.
- VPC: chạy job/endpoint trong private subnet khi yêu cầu; cấu hình security group và VPC endpoints.
- Network isolation: dùng khi training/inference container không cần outbound network; dependency phải được đóng gói sẵn.
- ECR: kiểm soát quyền pull image, scan image và version container.
- Secrets: không nhúng credential vào notebook, source code, environment file hoặc model artifact.
- Data access: giới hạn người dùng có quyền đọc dữ liệu train, label, prediction và model artifacts.

Với VPC mode, kiểm tra đường đi tới S3, ECR, CloudWatch, STS và dịch vụ phụ trợ. Nếu bật network isolation, container không thể gọi dịch vụ bên ngoài; thiết kế input/output và dependency phải phù hợp.

## 26. Reproducibility, lineage và audit

Để tái lập một model version, cần lưu tối thiểu:

- Dataset version hoặc immutable S3 URI/manifest.
- Code commit và container image digest/tag.
- Training job ARN và cấu hình compute.
- Hyperparameters, random seed và framework version.
- Feature definitions và preprocessing version.
- Evaluation metrics, reports và acceptance threshold.
- Model artifact URI và Model Registry package ARN.
- Approval history, deployment configuration và endpoint version.

Không dùng một S3 prefix có thể bị ghi đè làm định danh dataset duy nhất. Dùng versioning, manifest, timestamp hoặc data catalog để truy vết chính xác input đã dùng.

## 27. Tối ưu chi phí training và inference

Chi phí ML gồm training compute, tuning jobs, endpoint uptime, storage, data transfer, Feature Store, logs và monitoring.

### Training

- Dùng instance phù hợp với CPU/GPU/memory profile.
- Dùng Managed Spot Training khi job có checkpoint và chịu gián đoạn.
- Giới hạn tuning parallelism và số trial.
- Bật step caching cho pipeline step có input bất biến.
- Dừng job khi vượt runtime hoặc không còn hữu ích.
- Xóa artifact tạm theo retention sau khi đã bảo đảm audit/reproducibility.

### Inference

- Dùng Serverless hoặc Asynchronous cho traffic gián đoạn nếu latency phù hợp.
- Dùng Batch Transform thay endpoint luôn bật cho scoring theo lịch.
- Autoscale real-time endpoint theo metric phù hợp.
- Chọn instance type dựa trên latency/throughput benchmark.
- Dùng multi-model hoặc inference components khi kiến trúc và yêu cầu cô lập cho phép.
- Giám sát idle capacity và endpoint không còn traffic.

### Storage và dữ liệu

- Quản lý lifecycle của training data, model artifacts và capture logs.
- Không lưu prediction payload nhạy cảm lâu hơn chính sách cho phép.
- Theo dõi online Feature Store capacity và offline S3 storage.
- Cân nhắc chi phí KMS, data transfer và CloudWatch logs/metrics.

Không chọn phương án rẻ nhất theo giá mỗi giờ nếu nó làm tăng thời gian xử lý, retry, timeout hoặc vi phạm SLO. So sánh cost per successful prediction hoặc cost per training run đạt chất lượng.

## 28. Ví dụ end-to-end: dự đoán khách hàng rời bỏ

Một công ty dịch vụ muốn dự đoán khách hàng có khả năng rời bỏ trong 30 ngày tới để đội chăm sóc khách hàng can thiệp.

### Thiết kế

1. Dữ liệu giao dịch và tương tác được lưu trong S3.
2. Processing job kiểm tra dữ liệu, tạo feature và chia train/validation/test theo thời gian.
3. Feature Store lưu feature dùng chung cho training và online inference nếu cần.
4. Training job huấn luyện XGBoost hoặc framework phù hợp.
5. AMT tìm hyperparameter theo PR-AUC hoặc metric đã xác định.
6. Processing job đánh giá threshold, precision/recall theo segment và tạo báo cáo.
7. Pipeline đăng ký model package vào Model Registry.
8. Model owner kiểm tra và phê duyệt.
9. Deploy real-time endpoint nếu ứng dụng cần dự đoán khi user tương tác; dùng batch transform nếu chạy danh sách khách hàng mỗi đêm.
10. CloudWatch theo dõi latency, errors, utilization và invocation rate.
11. Pipeline định kỳ đánh giá data drift và model quality khi ground truth đã có.
12. Nếu candidate mới vượt tiêu chí, tạo model package version mới và đi qua approval/deployment guardrails.

~~~mermaid
flowchart TB
    A[CRM / Billing / App events] --> B[Amazon S3]
    B --> C[SageMaker Processing]
    C --> D[Feature Store]
    C --> E[SageMaker Training]
    E --> F[Automatic Model Tuning]
    F --> G[Evaluation Processing]
    G --> H[Model Registry]
    H --> I[Approval gate]
    I --> J[Real-time Endpoint or Batch Transform]
    D --> J
    J --> K[Application / CRM]
    J --> L[CloudWatch metrics and logs]
    L --> M[Monitoring and retraining workflow]
    M --> C
~~~

### Quyết định deployment

Nếu CRM cần dự đoán ngay khi nhân viên mở hồ sơ khách hàng, real-time endpoint có thể phù hợp. Nếu hệ thống chỉ cần danh sách khách hàng rủi ro mỗi sáng, Batch Transform có thể giảm chi phí so với endpoint luôn bật. Quyết định phải dựa trên latency, freshness, volume, concurrency và chi phí vận hành.

## 29. Troubleshooting thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Training job Failed | Sai image, role, input path, hyperparameter hoặc container exit code | Kiểm tra DescribeTrainingJob, CloudWatch Logs và container output |
| Job không đọc được S3 | Execution role thiếu quyền, bucket/KMS policy chặn hoặc VPC endpoint sai | Kiểm tra IAM, bucket policy, key policy và route |
| Training job hết thời gian | Instance nhỏ, data loading chậm hoặc deadlock | Profiling CPU/GPU/I/O, tăng runtime hợp lý và tối ưu pipeline |
| GPU utilization thấp | Data loader hoặc network là bottleneck | Tối ưu input pipeline, prefetch và batch size |
| Managed Spot job chờ lâu | Không có Spot capacity phù hợp | Tăng MaxWaitTime, mở rộng instance options hoặc dùng On-Demand |
| Model artifact không được tạo | Training code ghi sai path | Ghi artifact vào /opt/ml/model và kiểm tra container contract |
| Endpoint tạo thất bại | Image/instance không tương thích, role hoặc quota thiếu | Kiểm tra endpoint events, model container logs và service quota |
| Endpoint latency tăng | Model load, payload lớn, CPU/GPU thiếu hoặc concurrency cao | Đo ModelLatency/OverheadLatency và load test |
| 5xx tăng sau deploy | Container lỗi, dependency hoặc model version regression | Xem logs, rollback qua deployment guardrail |
| Autoscaling không hoạt động | Metric/resource dimension sai hoặc policy chưa gắn variant | Kiểm tra Application Auto Scaling target và CloudWatch alarms |
| Batch Transform lỗi | Input format, output path hoặc container transform contract sai | Kiểm tra job logs, manifest và content type |
| Model Registry không được approve | Thiếu quyền hoặc approval workflow chưa hoàn tất | Kiểm tra Model Package Group permissions và trạng thái package |
| Feature Store online/offline lệch | Event time, ingestion hoặc cấu hình store sai | Kiểm tra record identifier, event time và ingestion status |
| Drift alarm liên tục | Baseline không đại diện hoặc mùa vụ | Xem lại baseline, segment và cửa sổ giám sát |

## 30. Checklist trước khi đưa model vào production

- [ ] Business objective, target label và metric được định nghĩa.
- [ ] Dataset có version và được kiểm tra chất lượng.
- [ ] Train/validation/test split tránh data leakage.
- [ ] Feature engineering có thể tái lập giữa training và inference.
- [ ] Training job dùng execution role least privilege.
- [ ] Model artifacts được mã hóa và lưu ở S3 path có version.
- [ ] Hyperparameter tuning có giới hạn chi phí và stopping criteria.
- [ ] Checkpoint được cấu hình nếu dùng Managed Spot Training.
- [ ] Evaluation báo cáo metric tổng thể và theo segment.
- [ ] Model package được đăng ký vào Model Registry.
- [ ] Có approval gate trước khi deploy.
- [ ] Inference option phù hợp latency, payload, volume và traffic pattern.
- [ ] Endpoint có autoscaling và CloudWatch alarms phù hợp.
- [ ] Deployment có canary/blue-green/rolling strategy và rollback plan khi cần.
- [ ] IAM, KMS, VPC, S3, ECR và logging được bảo vệ.
- [ ] Data capture và monitoring tuân thủ privacy/retention policy.
- [ ] Có kế hoạch đo drift và model quality bằng công cụ được account hỗ trợ.
- [ ] Có trigger và quy trình retraining được phê duyệt.
- [ ] Đã đo cost per successful inference hoặc cost per model release.
- [ ] Có runbook cho endpoint failure, rollback và model retirement.

## 31. Ghi nhớ

Amazon SageMaker AI cung cấp các thành phần để quản lý vòng đời ML: Processing chuẩn bị dữ liệu, Training huấn luyện mô hình, Automatic Model Tuning tìm hyperparameter, Pipelines tự động hóa workflow, Feature Store quản lý feature, Model Registry quản lý version và approval, còn các inference options phục vụ real-time, serverless, asynchronous hoặc batch.

Triển khai production cần chọn inference option theo latency và traffic; dùng deployment guardrails, autoscaling và CloudWatch để bảo vệ availability; quản lý IAM, KMS, VPC và S3 để bảo vệ dữ liệu/model. Model quality cần được đánh giá trên ground truth và theo từng nhóm, không chỉ dựa vào training metric hoặc endpoint health.

Lưu ý trạng thái availability hiện hành của các dịch vụ monitoring: SageMaker Model Monitor và SageMaker Clarify không mở cho khách hàng mới. Hãy xác nhận quyền sử dụng và chọn giải pháp monitoring phù hợp, có thể kết hợp CloudWatch, MLflow, SHAP và các reference solutions do AWS công bố.

Một vòng đời ML tốt có thể tái lập, truy vết, phê duyệt, triển khai an toàn, quan sát được và có quy trình cập nhật khi dữ liệu hoặc yêu cầu nghiệp vụ thay đổi.

## Tài liệu tham khảo

- [Overview of Machine Learning with Amazon SageMaker AI](https://docs.aws.amazon.com/sagemaker/latest/dg/how-it-works-mlconcepts.html)
- [Data Transformation Workloads with SageMaker Processing](https://docs.aws.amazon.com/sagemaker/latest/dg/processing-job.html)
- [Create a Training Job](https://docs.aws.amazon.com/sagemaker/latest/dg/how-it-works-training.html)
- [CreateTrainingJob API](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_CreateTrainingJob.html)
- [How SageMaker AI Provides Training Information to Containers](https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-training-algo-running-container.html)
- [Distributed Training in SageMaker AI](https://docs.aws.amazon.com/sagemaker/latest/dg/distributed-training.html)
- [Automatic Model Tuning](https://docs.aws.amazon.com/sagemaker/latest/dg/automatic-model-tuning.html)
- [Managed Spot Training](https://docs.aws.amazon.com/sagemaker/latest/dg/model-managed-spot-training.html)
- [Checkpoints in SageMaker AI](https://docs.aws.amazon.com/sagemaker/latest/dg/model-checkpoints.html)
- [Feature Store Concepts](https://docs.aws.amazon.com/sagemaker/latest/dg/feature-store-concepts.html)
- [Feature Store Online and Offline Stores](https://docs.aws.amazon.com/sagemaker/latest/dg/feature-store.html)
- [SageMaker Pipelines](https://docs.aws.amazon.com/sagemaker/latest/dg/pipelines.html)
- [Pipeline Steps](https://docs.aws.amazon.com/sagemaker/latest/dg/build-and-manage-steps.html)
- [Pipeline Step Caching](https://docs.aws.amazon.com/sagemaker/latest/dg/pipelines-caching.html)
- [Model Registry Models, Versions, and Groups](https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry-models.html)
- [Deploy Models for Inference](https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model.html)
- [Inference Options](https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model-options.html)
- [Supported Inference Features](https://docs.aws.amazon.com/sagemaker/latest/dg/model-deploy-feature-matrix.html)
- [Endpoint Auto Scaling](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling-policy.html)
- [Deployment Guardrails](https://docs.aws.amazon.com/sagemaker/latest/dg/deployment-guardrails.html)
- [Blue/Green Deployments](https://docs.aws.amazon.com/sagemaker/latest/dg/deployment-guardrails-blue-green.html)
- [Rolling Deployments](https://docs.aws.amazon.com/sagemaker/latest/dg/deployment-guardrails-rolling.html)
- [Amazon SageMaker AI Metrics in CloudWatch](https://docs.aws.amazon.com/sagemaker/latest/dg/monitoring-cloudwatch.html)
- [SageMaker Model Monitor Availability](https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor.html)
- [SageMaker Clarify Availability Change](https://docs.aws.amazon.com/sagemaker/latest/dg/clarify-availability-change.html)
