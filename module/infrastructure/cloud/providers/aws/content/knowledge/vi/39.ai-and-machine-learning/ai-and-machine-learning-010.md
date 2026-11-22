# Lựa chọn inference endpoint, batch và chiến lược mở rộng

## Mục tiêu học tập

Sau khi huấn luyện hoặc chọn một mô hình machine learning, hệ thống cần cung cấp cách gọi mô hình phù hợp với ứng dụng. Có mô hình cần phản hồi trong vài chục mili giây để hỗ trợ quyết định trực tuyến; có mô hình xử lý ảnh, video hoặc tài liệu lớn trong nhiều phút; có mô hình chỉ cần chạy trên hàng triệu bản ghi theo lịch ban đêm. Dùng cùng một kiểu endpoint cho tất cả trường hợp thường dẫn đến chi phí cao, độ trễ không đạt yêu cầu hoặc tài nguyên bị bỏ phí.

Trong hệ sinh thái AWS, Amazon SageMaker AI cung cấp nhiều cách triển khai inference: real-time endpoint, serverless endpoint, asynchronous endpoint và Batch Transform. Các endpoint còn có thể dùng autoscaling, inference components, multi-model hosting và deployment guardrails. Với foundation model được quản lý, Amazon Bedrock có on-demand inference, Provisioned Throughput, batch inference và cross-Region inference profile. Mỗi lựa chọn giải quyết một kiểu workload khác nhau.

Bài học thuộc chương **AI và machine learning** của module CLOUD_PROVIDERS_AWS. Nội dung giúp người học lựa chọn cách phục vụ mô hình, thiết kế capacity và scale theo tải, bảo vệ endpoint khi cập nhật model, đo hiệu năng và kiểm soát chi phí.

Sau bài học, người học có thể:

- Phân biệt inference trực tuyến, asynchronous inference và batch inference.
- Chọn real-time, serverless, asynchronous hoặc Batch Transform trên SageMaker AI.
- Phân biệt SageMaker Batch Transform với Amazon Bedrock batch inference.
- Xác định khi nào nên dùng Bedrock on-demand, Provisioned Throughput hoặc inference profile.
- Tính sơ bộ throughput, concurrency, queue backlog và capacity dự phòng.
- Thiết kế horizontal scaling, vertical scaling, scale-to-zero và provisioned concurrency.
- Chọn instance CPU, GPU hoặc accelerator dựa trên model và benchmark.
- Dùng Inference Recommender và load test để tìm cấu hình phù hợp.
- Triển khai model theo blue/green, canary hoặc linear traffic shifting.
- Theo dõi latency, invocation, throttling, queue, error rate và chi phí.
- Thiết kế IAM, VPC, S3 và KMS permissions cho luồng inference.
- Xây dựng runbook và checklist production readiness.

## 1. Inference là giai đoạn phục vụ dự đoán

Training tạo ra model artifact hoặc model được đăng ký. Inference đưa model đó vào ứng dụng để nhận input và trả prediction.

Một luồng inference thường có các bước:

1. Ứng dụng tạo request chứa dữ liệu đầu vào.
2. API hoặc SDK gửi request tới model endpoint hay inference service.
3. Runtime kiểm tra quyền, nhận request và chuyển dữ liệu tới model container hoặc model provider.
4. Model thực hiện preprocessing, forward pass và postprocessing.
5. Kết quả được trả trực tiếp, ghi vào S3 hoặc gửi tới callback/notification.
6. Hệ thống ghi metrics, logs và traces để theo dõi chất lượng vận hành.

Inference architecture cần trả lời bốn câu hỏi:

- **Latency:** kết quả phải có trong bao lâu?
- **Traffic:** request đến đều, theo burst hay theo lịch?
- **Payload và compute:** dữ liệu nhỏ hay lớn, model chạy vài mili giây hay nhiều phút?
- **Cost:** cần giữ capacity sẵn sàng hay có thể chờ tài nguyên rảnh?

Không có một kiểu triển khai tối ưu cho mọi workload. Cần bắt đầu từ SLO và đặc điểm traffic rồi mới chọn endpoint.

## 2. Phân biệt online, asynchronous và batch inference

| Kiểu xử lý | Cách gửi | Cách nhận kết quả | Ví dụ |
|---|---|---|---|
| Online synchronous | Một request tới endpoint | Trả prediction trong cùng request | Phân loại giao dịch khi checkout |
| Asynchronous | Gửi request vào queue | Nhận output location hoặc notification sau | OCR tài liệu, phân tích ảnh/video |
| Batch | Gửi tập dữ liệu đã chuẩn bị | Output được ghi thành tập file | Chấm điểm toàn bộ khách hàng mỗi đêm |

Online inference phù hợp khi ứng dụng cần quyết định ngay. Asynchronous inference phù hợp khi một request vẫn cần kết quả riêng nhưng thời gian xử lý dài hoặc payload lớn. Batch inference phù hợp khi nhiều bản ghi có thể xử lý độc lập và người dùng không cần phản hồi tức thời.

Một pipeline có thể kết hợp cả ba. Ví dụ, API dùng real-time endpoint cho giao dịch mới, asynchronous endpoint xử lý tài liệu đính kèm và Batch Transform tính lại score cho toàn bộ khách hàng vào ban đêm.

## 3. Bốn lựa chọn inference trên SageMaker AI

SageMaker AI cung cấp bốn lựa chọn hosting chính:

| Lựa chọn | Payload tham khảo | Thời gian xử lý tham khảo | Traffic phù hợp |
|---|---:|---:|---|
| Real-Time Inference | Tối đa 25 MB | 60 giây với response thường; streaming có thể đến 8 phút | Liên tục, cần latency thấp và ổn định |
| Serverless Inference | Tối đa 4 MB | Tối đa 60 giây | Không đều, có idle period, chấp nhận cold start hoặc dùng provisioned concurrency |
| Asynchronous Inference | Tối đa 1 GB | Tối đa 60 phút | Request riêng lẻ nhưng có thể chờ queue |
| Batch Transform | Dataset có thể ở mức GB và job có thể kéo dài nhiều giờ/ngày | Theo thời gian chạy job | Offline, nhiều record có sẵn |

Các giới hạn trên là giới hạn dịch vụ được công bố, không phải mục tiêu latency của ứng dụng. Kích thước payload thực tế, model, container và Region có thể ảnh hưởng khả năng sử dụng. Hãy kiểm tra quota và feature compatibility trước khi thiết kế.

## 4. Real-Time Inference: endpoint đồng bộ

Real-Time Inference tạo endpoint REST được quản lý và giữ compute instance sẵn sàng nhận request. Đây là lựa chọn thường dùng cho API cần latency thấp hoặc throughput cao với traffic tương đối ổn định.

Đặc điểm:

- Endpoint tồn tại liên tục và có một hoặc nhiều instance.
- Ứng dụng gọi API InvokeEndpoint và nhận response đồng bộ.
- Có thể chọn instance type CPU, GPU hoặc accelerator phù hợp model.
- Hỗ trợ autoscaling theo traffic.
- Có thể triển khai nhiều production variants để kiểm soát traffic giữa các model.
- Có thể bật data capture và enhanced metrics theo feature được hỗ trợ.

Ví dụ: ứng dụng thanh toán gửi feature của giao dịch tới model fraud detection. API cần nhận score trước khi quyết định cho phép hoặc yêu cầu xác minh thêm. Nếu endpoint không sẵn sàng hoặc latency vượt SLO, checkout có thể bị chậm.

### 4.1. Gọi real-time endpoint bằng Boto3

~~~python
import json
import boto3

runtime = boto3.client("sagemaker-runtime", region_name="ap-southeast-1")

payload = {
    "transaction_amount": 1250000,
    "merchant_category": "electronics",
    "account_age_days": 420
}

response = runtime.invoke_endpoint(
    EndpointName="fraud-detection-prod",
    ContentType="application/json",
    Accept="application/json",
    Body=json.dumps(payload).encode("utf-8")
)

result = json.loads(response["Body"].read())
print(result)
~~~

Role của ứng dụng cần quyền sagemaker:InvokeEndpoint trên endpoint ARN. Nếu dùng streaming response, API và client phải hỗ trợ đúng streaming protocol. Không gửi dữ liệu bí mật trong log debug của request/response.

### 4.2. Khi nào real-time không phù hợp?

Không nên giữ real-time endpoint chỉ để chạy một lần mỗi ngày. Endpoint phải duy trì compute capacity và có thể tốn tiền trong cả thời gian không có request. Với payload lớn hoặc inference kéo dài, request đồng bộ có thể timeout hoặc giữ connection quá lâu. Khi ứng dụng có thể nhận kết quả sau, asynchronous hoặc batch thường hợp lý hơn.

## 5. Serverless Inference: scale theo request

Serverless Inference loại bỏ việc người vận hành chọn và quản lý số lượng instance. SageMaker AI tự cung cấp compute khi có request và tính phí theo thời gian xử lý cùng tài nguyên được cấp phát.

Phù hợp khi:

- Traffic không liên tục hoặc có khoảng nghỉ dài.
- Model và container nằm trong giới hạn serverless.
- Payload nhỏ, tối đa 4 MB theo giới hạn hiện hành.
- Request có thể hoàn thành trong tối đa 60 giây.
- Ứng dụng chấp nhận latency thay đổi do cold start, hoặc cần cấu hình provisioned concurrency.

Các tham số chính:

| Tham số | Ý nghĩa |
|---|---|
| MemorySizeInMB | Bộ nhớ cấp cho endpoint; các mức 1, 2, 3, 4, 5 hoặc 6 GiB |
| MaxConcurrency | Số invocation đồng thời tối đa cho endpoint; giới hạn hiện hành tối đa 200 |
| ProvisionedConcurrency | Số concurrency được chuẩn bị trước để giảm cold start; không được lớn hơn MaxConcurrency |

On-demand serverless tự mở rộng khi có traffic và thu hẹp khi ít request. Nếu cần latency ổn định hơn trong khung giờ cao điểm, có thể cấp Provisioned Concurrency và autoscale phần concurrency đó theo lịch hoặc metric.

### 5.1. Ví dụ cấu hình serverless

~~~python
import boto3

sm = boto3.client("sagemaker", region_name="ap-southeast-1")

response = sm.create_endpoint_config(
    EndpointConfigName="sentiment-serverless-config",
    ProductionVariants=[
        {
            "VariantName": "AllTraffic",
            "ModelName": "sentiment-model",
            "ServerlessConfig": {
                "MemorySizeInMB": 4096,
                "MaxConcurrency": 40,
                "ProvisionedConcurrency": 5
            }
        }
    ]
)

print(response["EndpointConfigArn"])
~~~

Ví dụ chỉ minh họa cấu trúc API. Model phải được tạo trước; sau đó tạo endpoint từ endpoint configuration. Cần kiểm tra quota serverless theo Region, model/container compatibility và concurrency quota cấp account.

### 5.2. Cold start và Provisioned Concurrency

Khi endpoint không có capacity sẵn sàng, SageMaker cần khởi tạo compute và container trước khi xử lý request. Thời gian khởi động này có thể làm p95/p99 latency tăng. Provisioned Concurrency giữ sẵn một lượng concurrency để giảm tác động đó, nhưng phát sinh chi phí kể cả khi không sử dụng.

Không đặt Provisioned Concurrency bằng peak concurrency nếu peak chỉ xảy ra trong vài phút. Dùng traffic profile và lịch hoạt động để xác định mức nền, sau đó autoscale phần concurrency dự phòng.

## 6. Asynchronous Inference: queue request và trả kết quả sau

Asynchronous Inference nhận request, đưa request vào queue và xử lý khi endpoint có capacity. Kết quả được ghi vào Amazon S3; ứng dụng có thể dùng SNS notification hoặc kiểm tra output location để lấy kết quả.

Phù hợp khi:

- Payload lớn, tối đa 1 GB.
- Một request có thể cần đến 60 phút để xử lý.
- Ứng dụng không yêu cầu phản hồi trong cùng HTTP call.
- Traffic có thể burst và có thể queue.
- Có thể scale endpoint xuống 0 instance khi queue trống.

Luồng điển hình:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant API as SageMaker Runtime
    participant Q as Async Queue
    participant EP as Endpoint instances
    participant S3 as Amazon S3
    participant SNS as SNS notification
    App->>API: InvokeEndpointAsync (S3 input)
    API->>Q: Enqueue request
    API-->>App: OutputLocation / InferenceId
    Q->>EP: Deliver request when capacity is ready
    EP->>S3: Write inference result
    EP->>SNS: Notify completion (optional)
    SNS-->>App: Result is ready
    App->>S3: Read output object
~~~

Request thường trỏ đến input object trong S3. Output path có thể được cấu hình theo endpoint. Có thể đặt request TTL để giới hạn thời gian chờ trong queue và invocation timeout để giới hạn thời gian xử lý.

### 6.1. Gửi asynchronous request

~~~python
import boto3

runtime = boto3.client("sagemaker-runtime", region_name="ap-southeast-1")

response = runtime.invoke_endpoint_async(
    EndpointName="document-ocr-async",
    InputLocation="s3://ml-input-prod/ocr/job-2026-11-20/document-001.pdf",
    ContentType="application/pdf",
    Accept="application/json",
    InvocationTimeoutSeconds=3600,
    RequestTTLSeconds=21600
)

print(response["InferenceId"])
print(response["OutputLocation"])
~~~

Role gọi runtime cần quyền sagemaker:InvokeEndpointAsync. Execution role của endpoint cần đọc input object và ghi output object vào S3. Nếu dùng SNS notification, cần quyền publish phù hợp và topic policy cho phép endpoint gửi thông báo.

### 6.2. Queue backlog và scale-to-zero

Async endpoint có thể scale instance count xuống 0 khi không có request. Điều này tiết kiệm chi phí compute idle, nhưng request mới phải chờ endpoint scale lên.

Các metric quan trọng:

- ApproximateBacklogSize: số request đang chờ hoặc đang được xử lý.
- ApproximateBacklogSizePerInstance: backlog chia cho số instance hiện có.
- ApproximateAgeOfOldestRequest: tuổi của request lâu nhất trong queue.
- HasBacklogWithoutCapacity: bằng 1 khi có request nhưng endpoint không có instance.

Để scale từ 0, cần policy phản ứng khi backlog xuất hiện mà capacity bằng 0. Nếu chỉ đặt target tracking trên backlog per instance, phép chia có thể không đủ để khởi động endpoint từ 0. AWS có hướng dẫn riêng cho policy scale-up từ zero.

Scale-to-zero có thể làm giảm chi phí nhưng tăng thời gian hoàn tất request đầu tiên. Nếu SLO cho phép chờ, đây là lựa chọn tốt; nếu cần phản hồi nhanh, giữ minimum capacity hoặc chọn real-time endpoint.

## 7. Batch Transform: xử lý tập dữ liệu offline

Batch Transform chạy inference trên dữ liệu đã lưu trong S3 mà không cần tạo endpoint tồn tại liên tục. SageMaker khởi chạy compute instance cho job, đọc input, phân phối công việc và ghi output về S3.

Phù hợp khi:

- Có tập dữ liệu lớn đã chuẩn bị trước.
- Kết quả không cần trả về ngay cho từng request.
- Muốn tính score định kỳ hoặc backfill lịch sử.
- Muốn chạy preprocessing/inference theo job rồi giải phóng compute.

Ví dụ: mỗi đêm hệ thống tính propensity score cho 15 triệu khách hàng. Kết quả được ghi thành file S3 để downstream analytics và campaign system sử dụng.

### 7.1. Luồng Batch Transform

1. Chuẩn bị input file trong S3.
2. Chọn SageMaker model đã tạo.
3. Chọn instance type và số lượng instance.
4. Cấu hình input content type, split strategy và batch strategy.
5. Tạo Transform Job.
6. SageMaker phân phối input objects/records tới compute instance.
7. Model container xử lý dữ liệu.
8. Output được ghi về S3 theo file tương ứng.
9. Job kết thúc và compute được giải phóng.

Batch Transform không cung cấp endpoint để ứng dụng gọi liên tục. Nếu ứng dụng cần gửi từng request khi request đến, chọn real-time, serverless hoặc asynchronous.

### 7.2. Tạo Batch Transform job bằng Boto3

~~~python
import boto3

sm = boto3.client("sagemaker", region_name="ap-southeast-1")

response = sm.create_transform_job(
    TransformJobName="customer-score-20261120",
    ModelName="customer-propensity-model",
    TransformInput={
        "DataSource": {
            "S3DataSource": {
                "S3DataType": "S3Prefix",
                "S3Uri": "s3://ml-input-prod/customer-features/2026-11-20/"
            }
        },
        "ContentType": "text/csv",
        "SplitType": "Line",
        "CompressionType": "None"
    },
    TransformOutput={
        "S3OutputPath": "s3://ml-output-prod/customer-score/2026-11-20/",
        "Accept": "text/csv",
        "AssembleWith": "Line"
    },
    TransformResources={
        "InstanceType": "ml.m5.2xlarge",
        "InstanceCount": 4
    },
    BatchStrategy="MultiRecord",
    MaxConcurrentTransforms=4,
    MaxPayloadInMB=6
)

print(response["TransformJobArn"])
~~~

Ví dụ minh họa. Model container phải hỗ trợ định dạng input/output đã chọn. Các tham số payload và concurrent transform phải tuân theo giới hạn API; MaxPayloadInMB không được vượt 100 MB và tích của MaxConcurrentTransforms với MaxPayloadInMB cũng không được vượt 100 MB.

### 7.3. Chia dữ liệu để tận dụng nhiều instance

SageMaker phân phối S3 objects cho các instance. Nếu input có nhiều file, các instance có thể xử lý các object khác nhau song song. Nếu chỉ có một file lớn và cách chia input không cho phép phân phối đủ tốt, một số instance có thể nhàn rỗi.

Hãy phân vùng dữ liệu thành nhiều file hợp lý, chọn SplitType phù hợp và kiểm tra khả năng xử lý record của model container. CSV có embedded newline cần được xử lý đặc biệt vì Batch Transform không hỗ trợ loại CSV đó với SplitType=Line.

MaxConcurrentTransforms, BatchStrategy và MaxPayloadInMB điều chỉnh số record trong một request tới container. Tăng concurrency không luôn làm job nhanh hơn: container có thể nghẽn CPU, memory hoặc GPU, đồng thời tăng kích thước request có thể gây timeout hoặc lỗi payload.

## 8. Amazon Bedrock: chọn on-demand, provisioned hoặc batch

Nếu ứng dụng dùng foundation model được Amazon Bedrock quản lý, không cần tự tạo SageMaker endpoint cho model đó. Có thể gọi Bedrock Runtime API và chọn phương thức capacity phù hợp.

| Phương thức Bedrock | Phù hợp khi | Đặc điểm |
|---|---|---|
| On-Demand inference | Traffic thay đổi, muốn trả theo usage | Gọi model theo quota và capacity của model/Region |
| Provisioned Throughput | Workload lớn, ổn định, cần throughput được cấp trước | Mua model units theo thời hạn và model hỗ trợ |
| Batch inference | Nhiều prompt có thể xử lý bất đồng bộ | Input/output đặt trong S3; job chạy khi có capacity |
| Cross-Region inference profile | Có thể cho phép request được xử lý ở Region khác trong profile | Dịch vụ định tuyến request qua các Region được hỗ trợ |

Bedrock batch inference không hỗ trợ provisioned models theo tài liệu hiện hành. Batch job xử lý prompt từ file trong S3 và lưu kết quả trong S3; thời gian hoàn tất phụ thuộc model và capacity. Không giả định batch job có thời hạn hoàn tất giống một HTTP request.

Cross-Region inference profile có thể tăng khả năng đáp ứng capacity và mở rộng vùng xử lý, nhưng phải kiểm tra yêu cầu data residency, Region được profile hỗ trợ và chính sách dữ liệu của tổ chức. Nếu dữ liệu phải ở trong một Region cụ thể, không chọn profile định tuyến xuyên Region.

SageMaker Batch Transform và Bedrock batch inference đều là job offline, nhưng khác model hosting và API. Chọn đúng service theo nơi model được quản lý.

## 9. Bảng quyết định chọn inference option

| Nhu cầu | Lựa chọn khởi đầu | Lý do |
|---|---|---|
| API cần phản hồi nhanh, traffic ổn định | SageMaker Real-Time | Endpoint luôn sẵn sàng và chọn được instance |
| Traffic nhỏ, không đều, model gọn | SageMaker Serverless | Không quản lý instance và giảm chi phí idle |
| Traffic burst, request có thể chờ, payload lớn | SageMaker Asynchronous | Queue, output S3, scale-to-zero |
| Tính score cho hàng triệu record theo lịch | SageMaker Batch Transform | Job offline, không giữ endpoint |
| Gọi foundation model Bedrock theo request | Bedrock On-Demand | Không tự host model |
| Foundation model có throughput ổn định và cao | Bedrock Provisioned Throughput | Capacity được cấp theo model units |
| Tập prompt lớn, không cần response ngay | Bedrock Batch Inference | Xử lý bất đồng bộ qua S3 |
| Muốn phục vụ nhiều model nhỏ trên hạ tầng chung | SageMaker Multi-Model hoặc Inference Components | Tăng utilization và giảm endpoint riêng lẻ |
| Model update cần hạn chế blast radius | SageMaker deployment guardrails | Canary/linear, baking và auto-rollback |

Đây là lựa chọn ban đầu. Benchmark bằng dữ liệu thật, traffic profile và SLO trước khi chốt kiến trúc.

## 10. Hiểu throughput, latency và concurrency

Ba chỉ số thường bị nhầm:

- **Latency:** thời gian xử lý một request.
- **Throughput:** số request có thể hoàn tất trong một đơn vị thời gian.
- **Concurrency:** số request đang được xử lý đồng thời.

Một endpoint có thể có latency thấp khi chỉ có một request nhưng latency tăng mạnh khi concurrency cao. Throughput cao không đảm bảo p99 latency thấp nếu queue tăng.

Định luật Little cho hệ thống ổn định:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\) là số request trung bình đang ở trong hệ thống.
- \(\lambda\) là tốc độ request trung bình (request/giây).
- \(W\) là thời gian trung bình request nằm trong hệ thống (giây).

Ví dụ, hệ thống nhận 50 request/giây và thời gian xử lý trung bình là 0,2 giây:

\[
L = 50 \times 0,2 = 10
\]

Trung bình có khoảng 10 request đang xử lý. Nếu latency tăng lên 1 giây ở cùng arrival rate, concurrency trung bình tăng lên 50. Đây là lý do cần đo cả queue và latency thay vì chỉ xem invocation count.

## 11. Ước lượng capacity trước khi scale

Một phép ước lượng sơ bộ:

\[
RequiredInstances \approx
\left\lceil \frac{PeakRPS}{SafeRPSPerInstance} \right\rceil
\]

Giả sử benchmark cho thấy một instance xử lý an toàn 25 request/giây ở p95 latency đạt SLO. Peak traffic là 180 request/giây:

\[
RequiredInstances = \left\lceil \frac{180}{25} \right\rceil = 8
\]

Nếu cần dự phòng một instance cho lỗi hoặc scale event, có thể đặt minimum capacity cao hơn mức lý thuyết. Con số cuối cùng phải được kiểm chứng bằng load test, vì request size, batch size, model architecture và concurrency ảnh hưởng throughput.

Không dùng throughput tối đa trong một benchmark ngắn làm capacity production. Hãy kiểm tra sustained load, burst, cold start, model warmup và thời gian scale-out.

## 12. Horizontal scaling và vertical scaling

**Horizontal scaling** tăng số instance để phân phối request. **Vertical scaling** đổi sang instance lớn hơn hoặc có accelerator mạnh hơn.

| Tiêu chí | Horizontal scaling | Vertical scaling |
|---|---|---|
| Cách làm | Tăng/giảm instance count | Đổi instance type hoặc accelerator |
| Khả năng chịu lỗi | Nhiều instance có thể tăng redundancy | Phụ thuộc ít instance lớn |
| Giới hạn | Model phải chạy được trên mỗi instance; cần đủ quota | Kích thước instance và quota |
| Thời gian thay đổi | Autoscaling có thể tự điều chỉnh | Đổi cấu hình thường cần update endpoint |
| Phù hợp | Traffic tăng theo request rate | Model không vừa memory hoặc cần GPU mạnh hơn |

Một model lớn có thể không vừa RAM/GPU memory của instance nhỏ. Tăng số instance không giải quyết được nếu một bản sao model không thể load vào một instance. Khi đó cần vertical scaling, model sharding/parallelism hoặc inference architecture hỗ trợ model phân tán.

## 13. Autoscaling cho real-time endpoint

SageMaker AI hỗ trợ target tracking và step scaling cho production variant. Target tracking thường là lựa chọn dễ vận hành: chọn metric và target, Application Auto Scaling tạo alarm và điều chỉnh instance count để đưa metric về gần target.

Metric phổ biến:

- InvocationsPerInstance: số invocation trên mỗi instance trong khoảng thời gian.
- CPU/GPU utilization hoặc custom metric nếu cần theo dõi tài nguyên.
- Metric ứng dụng như queue depth hoặc concurrent requests nếu có custom publishing.

Ví dụ tư duy: nếu một instance benchmark an toàn ở khoảng 70 invocation/phút, có thể đặt target ban đầu thấp hơn để giữ headroom. Sau load test, điều chỉnh target theo latency và error rate.

### 13.1. Đăng ký endpoint variant làm scalable target

~~~bash
aws application-autoscaling register-scalable-target \
  --service-namespace sagemaker \
  --resource-id endpoint/fraud-detection-prod/variant/AllTraffic \
  --scalable-dimension sagemaker:variant:DesiredInstanceCount \
  --min-capacity 2 \
  --max-capacity 12
~~~

### 13.2. Tạo target tracking policy

Tạo file scaling-policy.json:

~~~json
{
  "TargetValue": 70.0,
  "PredefinedMetricSpecification": {
    "PredefinedMetricType": "SageMakerVariantInvocationsPerInstance"
  },
  "ScaleInCooldown": 300,
  "ScaleOutCooldown": 60
}
~~~

Áp dụng policy:

~~~bash
aws application-autoscaling put-scaling-policy \
  --policy-name fraud-endpoint-target-tracking \
  --policy-type TargetTrackingScaling \
  --service-namespace sagemaker \
  --resource-id endpoint/fraud-detection-prod/variant/AllTraffic \
  --scalable-dimension sagemaker:variant:DesiredInstanceCount \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
~~~

Các con số trong ví dụ chỉ là giá trị khởi đầu. InvocationsPerInstance được đo theo period của metric; phải xác minh target cùng đơn vị trong CloudWatch và benchmark. MinCapacity nên đủ để đáp ứng baseline traffic và thời gian scale-out.

Scale-out cooldown thường ngắn hơn scale-in cooldown. Scale-in chậm giúp tránh giảm capacity ngay sau một burst ngắn. Không đặt min capacity bằng 0 cho real-time endpoint theo cách suy diễn từ async endpoint; lựa chọn hosting và scalable dimension phải hỗ trợ hành vi đó.

## 14. Autoscaling cho asynchronous endpoint

Async endpoint có queue, vì vậy scaling policy nên phản ánh backlog và tuổi request. Chỉ nhìn invocation rate có thể bỏ sót trường hợp request đến theo burst và đang chờ lâu.

Metric thường dùng:

- ApproximateBacklogSizePerInstance cho target tracking.
- ApproximateAgeOfOldestRequest để theo dõi SLO queue wait.
- HasBacklogWithoutCapacity để phát hiện backlog khi instance count bằng 0.
- CPU/GPU utilization để đánh giá instance đã bão hòa hay chưa.

Ví dụ target tracking policy:

~~~json
{
  "TargetValue": 5.0,
  "CustomizedMetricSpecification": {
    "MetricName": "ApproximateBacklogSizePerInstance",
    "Namespace": "AWS/SageMaker",
    "Dimensions": [
      {
        "Name": "EndpointName",
        "Value": "document-ocr-async"
      }
    ],
    "Statistic": "Average"
  },
  "ScaleOutCooldown": 60,
  "ScaleInCooldown": 300
}
~~~

Target 5 có nghĩa là nhóm vận hành muốn duy trì khoảng 5 request backlog trên mỗi instance theo metric được chọn. Đây không phải số request/giây. Điều chỉnh theo thời gian xử lý trung bình và queue wait SLO.

Khi scale-to-zero, tạo thêm policy scale-out từ zero dựa trên HasBacklogWithoutCapacity. Nếu không có policy này, endpoint có thể chờ metric backlog-per-instance hợp lệ trước khi khởi động capacity.

## 15. Autoscale Provisioned Concurrency cho serverless

On-demand Serverless Inference tự scale compute theo traffic. Nếu đã cấu hình Provisioned Concurrency, có thể dùng Application Auto Scaling để tăng/giảm số concurrency được chuẩn bị trước.

Scalable dimension là sagemaker:variant:DesiredProvisionedConcurrency.

Resource ID theo endpoint và variant có dạng endpoint/endpoint-name/variant/variant-name.

Ví dụ đăng ký scalable target:

~~~bash
aws application-autoscaling register-scalable-target \
  --service-namespace sagemaker \
  --resource-id endpoint/sentiment-serverless/variant/AllTraffic \
  --scalable-dimension sagemaker:variant:DesiredProvisionedConcurrency \
  --min-capacity 2 \
  --max-capacity 20
~~~

Sau đó tạo target tracking hoặc scheduled scaling. Provisioned concurrency cần ít nhất 1 và không vượt MaxConcurrency. Có thể đặt lịch tăng capacity trước giờ cao điểm, giảm sau giờ làm việc để cân bằng latency và chi phí.

## 16. Batch scaling: tăng tốc job theo dữ liệu

Batch Transform không scale giống một endpoint. Người vận hành chọn số instance khi tạo job, sau đó điều chỉnh parallelism và cách chia input.

Các đòn bẩy:

- Tăng InstanceCount nếu có đủ S3 objects hoặc partition để phân phối.
- Chọn instance type mạnh hơn khi mỗi record cần nhiều CPU/GPU memory.
- Tăng MaxConcurrentTransforms khi container xử lý được nhiều request song song.
- Chọn BatchStrategy=MultiRecord nếu model nhận nhiều record trong một invocation.
- Tối ưu MaxPayloadInMB trong giới hạn API và memory của container.
- Chia input thành nhiều file hợp lý để tránh một instance xử lý toàn bộ workload trong khi các instance khác nhàn rỗi.

Tăng instance count có thể không cải thiện job nếu input chỉ có một object khó chia hoặc model container bị nghẽn tại một bottleneck khác. Luôn đo tổng thời gian, utilization, số file và output throughput.

## 17. Chọn instance và tối ưu model

Chọn instance theo bottleneck thực tế:

| Loại workload | Tài nguyên cần xem |
|---|---|
| Tabular model nhỏ, preprocessing nhẹ | CPU, memory và network |
| Computer vision hoặc deep learning | GPU memory, GPU utilization, batch size |
| Model cần accelerator chuyên dụng | AWS Inferentia/Trainium inference support theo framework và serving stack |
| Embedding và vector generation | CPU/GPU, memory, batch throughput |
| LLM lớn | GPU memory, tensor parallelism, token throughput, concurrency và context length |

Trước khi đổi instance type, kiểm tra:

- Model artifact có vừa memory không?
- Model có load time dài không?
- Có hỗ trợ precision thấp hơn như FP16/BF16/INT8 không?
- Batch size có tăng throughput mà vẫn đạt latency không?
- CPU preprocessing hoặc serialization có trở thành bottleneck không?
- Có cần tối ưu container hoặc compile model không?

Không phải model nào cũng nhanh hơn khi dùng GPU. Với model nhỏ hoặc request rất ngắn, overhead truyền dữ liệu lên GPU có thể làm latency tăng. Benchmark trên đúng instance và payload đại diện.

## 18. Multi-Model Endpoint, Multi-Container và Inference Components

Khi có nhiều model, không nhất thiết tạo một endpoint độc lập cho mỗi model.

| Cách triển khai | Khi phù hợp | Trade-off |
|---|---|---|
| Single-model endpoint | Một model có traffic lớn hoặc yêu cầu isolation | Dễ dự báo tài nguyên nhưng có thể dư capacity |
| Multi-Model Endpoint (MME) | Nhiều model cùng framework/container, traffic từng model thấp | Tiết kiệm instance nhưng có thể có model loading/cache behavior |
| Multi-Container Endpoint | Nhiều model cần container/framework khác nhau | Linh hoạt nhưng cấu hình và tài nguyên phức tạp |
| Serial inference pipeline | Cần preprocessing/model/postprocessing theo chuỗi | Tập trung pipeline nhưng thêm bước xử lý |
| Inference Components | Nhiều model chia sẻ hạ tầng và cần quản lý resource/copies độc lập | Điều phối resource chi tiết, cần theo dõi capacity |

Inference Components cho phép gắn model với endpoint và chỉ định CPU, GPU, memory cùng số bản sao. Có thể scale từng component độc lập, cập nhật model riêng và dùng chung hạ tầng endpoint. Một số component có thể scale copies xuống 0 để nhường tài nguyên cho component khác.

Không chọn MME chỉ vì có nhiều file model. Cần xem framework được hỗ trợ, model size, tần suất gọi, thời gian load model, memory cache và latency khi model được tải lại.

## 19. Deployment guardrails: cập nhật model an toàn

Cập nhật model có thể làm latency tăng, prediction quality giảm hoặc gây lỗi container. SageMaker AI deployment guardrails hỗ trợ blue/green và rolling deployments cho real-time và asynchronous endpoints theo feature compatibility.

Trong blue/green deployment:

- **Blue fleet** là phiên bản đang phục vụ.
- **Green fleet** là fleet mới chứa model hoặc cấu hình mới.
- SageMaker tạo green fleet, chuyển traffic theo policy và theo dõi CloudWatch alarms trong baking period.
- Nếu alarm kích hoạt, dịch vụ có thể tự rollback về blue fleet.

Ba kiểu traffic shifting:

| Kiểu | Cách chuyển traffic | Phù hợp |
|---|---|---|
| All at once | Chuyển toàn bộ một lần | Update nhanh, chấp nhận blast radius lớn hơn |
| Canary | Chuyển một phần nhỏ trước, quan sát rồi chuyển phần còn lại | Cân bằng rủi ro và thời gian |
| Linear | Chuyển theo nhiều bước đều nhau | Muốn kiểm tra tăng dần với blast radius nhỏ |

Ví dụ linear có thể chuyển 20% traffic mỗi bước và chờ baking period 5 phút. Các con số cần căn cứ traffic volume và khả năng phát hiện lỗi. Canary với traffic quá nhỏ có thể không đủ sample để đánh giá model.

### 19.1. CloudWatch alarms cho auto-rollback

Tạo alarm theo các tín hiệu:

- Model latency p95/p99 vượt SLO.
- Invocation 5xx hoặc model container error tăng.
- Throttling tăng.
- CPU/GPU hoặc memory pressure bất thường.
- Business metric như tỷ lệ fraud false positive hoặc classification drift nếu có pipeline đánh giá.

Alarm nên so sánh green fleet với baseline hoặc ngưỡng đã xác định. Không chỉ dựa trên CPU vì model có thể trả prediction sai dù hạ tầng khỏe.

Blue/green nhiều bước và baking period có thể giữ cả hai fleet đồng thời, làm tăng chi phí trong thời gian deployment. Cần tính capacity và budget cho khoảng thời gian overlap.

## 20. Canary, shadow và A/B testing khác nhau

Ba kỹ thuật giúp đánh giá model mới nhưng mục tiêu khác nhau:

- **Canary deployment:** một phần traffic thật được chuyển sang model mới; kết quả có thể ảnh hưởng người dùng.
- **Shadow deployment:** request được sao chép sang model mới để đo lường, nhưng response mới không được dùng cho người dùng.
- **A/B testing:** người dùng hoặc request được phân nhóm có chủ đích để so sánh kết quả và business metrics.

SageMaker production variants có thể phân phối traffic giữa các variant. Với shadow testing, cần bảo đảm model shadow không tạo side effect như gửi email, charge payment hoặc thay đổi trạng thái nghiệp vụ.

A/B test cần randomization và thời gian đủ dài để tránh kết luận từ sample bias. Canary là kỹ thuật giảm rủi ro deployment, không thay thế đánh giá thống kê về model quality.

## 21. Quan sát endpoint bằng CloudWatch

Metrics giúp phát hiện endpoint quá tải, model lỗi hoặc scale không theo kịp traffic.

Các metric quan trọng:

| Metric | Ý nghĩa | Dùng để |
|---|---|---|
| Invocations | Số request gọi endpoint | Đo traffic |
| InvocationsPerInstance | Invocation trung bình trên instance | Target tracking |
| ModelLatency | Thời gian model container xử lý | Theo dõi latency của model |
| OverheadLatency | Overhead từ SageMaker ngoài model processing | Phân biệt model chậm với service/network overhead |
| Invocation4XXErrors | Request lỗi phía client | Kiểm tra payload, auth, endpoint usage |
| Invocation5XXErrors | Request lỗi phía server/container | Điều tra model server và runtime |
| InvocationModelErrors | Lỗi phát sinh từ model container | Kiểm tra inference code |
| InvocationThrottles | Request bị throttled | Kiểm tra concurrency/capacity |
| CPUUtilization / GPUUtilization | Mức dùng tài nguyên | Phát hiện compute saturation |
| MemoryUtilization / GPUMemoryUtilization | Mức dùng memory | Phát hiện thiếu memory hoặc model loading pressure |

Một số metric có dimension EndpointName, VariantName hoặc InstanceId tùy loại. Chọn đúng dimension khi tạo dashboard và alarm. Metric cấp endpoint có thể che giấu một instance đang nóng hơn các instance khác.

### 21.1. Theo dõi p95 và p99

Average latency có thể tốt dù một nhóm nhỏ request bị chậm. Với ứng dụng tương tác, p95 và p99 thường có ý nghĩa hơn average.

Ví dụ SLO:

- p95 latency dưới 250 ms.
- p99 latency dưới 600 ms.
- Error rate dưới 0,1%.
- Throttling bằng 0 trong giờ hoạt động bình thường.

Các giá trị là ví dụ. Đặt SLO theo trải nghiệm người dùng và đo end-to-end latency ở phía ứng dụng, vì metric model latency không bao gồm toàn bộ API gateway, network và client processing.

## 22. Theo dõi model quality sau deployment

Endpoint có thể khỏe về hạ tầng nhưng prediction quality suy giảm vì input distribution thay đổi. Cần theo dõi cả vận hành và chất lượng model.

Một số cách:

- Data capture để lưu một phần request/response theo cấu hình.
- SageMaker Model Monitor để kiểm tra data quality, model quality, bias hoặc drift theo use case được hỗ trợ.
- Ghi business outcome sau khi có ground truth.
- So sánh prediction distribution theo phiên bản model.
- Theo dõi feature missing rate, out-of-range values và schema mismatch.
- Dùng trace ID để liên kết prediction với request và kết quả nghiệp vụ.

Không lưu toàn bộ payload nhạy cảm chỉ để quan sát model. Áp dụng sampling, masking và retention. Nếu ground truth đến chậm, thiết kế pipeline đánh giá offline thay vì kết luận quality từ prediction ngay lúc inference.

## 23. Capacity planning và load testing

Trước production, load test phải mô phỏng workload thật:

1. Dùng payload đại diện và phân bố kích thước request thực tế.
2. Tăng virtual users hoặc request rate theo từng bước.
3. Đo throughput, p50/p95/p99 latency, error và throttling.
4. Quan sát CPU, GPU, memory, queue và model loading.
5. Kiểm tra sustained load trong thời gian đủ dài.
6. Thử burst traffic và scale-out/scale-in.
7. Kiểm tra cold start nếu dùng serverless hoặc async scale-to-zero.
8. Lặp lại trên instance type hoặc endpoint mode khác.

Amazon SageMaker Inference Recommender có thể tự động benchmark model trên các cấu hình real-time hoặc serverless được hỗ trợ. Kết quả giúp chọn instance type, instance count, container parameters, memory và concurrency. Đây là công cụ tham khảo; phải dùng sample data đại diện và xác nhận lại với traffic production.

### 23.1. Đừng chỉ benchmark một request

Một request thành công chỉ chứng minh model chạy được. Production cần biết:

- Model load mất bao lâu?
- Khi 10, 50 hoặc 200 request đồng thời thì latency thay đổi ra sao?
- Khi instance scale out, request có bị queue/throttle không?
- Khi traffic giảm, capacity scale-in có làm latency xấu ở burst tiếp theo không?
- Khi model container restart, endpoint có phục hồi đúng không?
- Khi một instance lỗi, phần còn lại có chịu được tải không?

Lưu kết quả benchmark cùng model version, container image digest, instance type, region, payload distribution và endpoint configuration để có thể so sánh về sau.

## 24. Chiến lược giảm chi phí inference

Chi phí phụ thuộc hosting mode, instance type, thời gian compute, traffic, model size, data transfer, storage và logging.

| Biện pháp | Tác động |
|---|---|
| Dùng Serverless cho traffic gián đoạn | Giảm compute idle |
| Dùng Async và scale-to-zero | Không giữ instance khi queue trống |
| Dùng Batch Transform cho workload offline | Tránh endpoint liên tục |
| Right-size instance | Tránh overprovisioning |
| Autoscaling theo metric đã benchmark | Theo sát demand |
| Multi-model/inference components | Tăng utilization của hạ tầng dùng chung |
| Quantization/compile/optimized container | Giảm compute cần cho mỗi inference |
| Batch request khi model hỗ trợ | Tăng throughput trên mỗi compute |
| Giảm payload và preprocessing dư thừa | Giảm latency và overhead |
| Theo dõi data capture/log retention | Kiểm soát storage và logging cost |

Không tối ưu chi phí bằng cách giảm capacity dưới mức SLO. Nếu endpoint thường xuyên throttle, request retry có thể làm traffic tăng thêm và khiến tổng chi phí cao hơn.

## 25. Bảo mật luồng inference

Inference endpoint thường xử lý dữ liệu nghiệp vụ hoặc dữ liệu cá nhân. Bảo mật cần áp dụng cho cả model artifact, request, output và quyền quản trị.

### 25.1. IAM roles tách theo trách nhiệm

Có thể tách:

- **Training/deployment role:** đọc model artifact và tạo model/endpoint.
- **Endpoint execution role:** đọc model artifact từ S3, lấy image từ ECR và dùng các resource cần thiết.
- **Application invoke role:** chỉ gọi sagemaker:InvokeEndpoint hoặc sagemaker:InvokeEndpointAsync trên endpoint cụ thể.
- **Batch job role:** đọc input S3 và ghi output S3.
- **Operations role:** xem metrics, logs và trạng thái endpoint; quyền update/delete được kiểm soát riêng.

Không cấp sagemaker:* cho ứng dụng chỉ cần inference. Với Bedrock, giới hạn bedrock:InvokeModel hoặc bedrock:InvokeModelWithResponseStream theo model/resource và cấp quyền batch job riêng khi cần.

### 25.2. VPC, PrivateLink và mã hóa

Real-time endpoint có thể được cấu hình VPC access để kiểm soát network interface và kết nối tới resource private. Có thể dùng AWS PrivateLink cho kết nối private tới SageMaker API/runtime khi kiến trúc hỗ trợ.

Bảo vệ:

- Model artifact trong S3 bằng bucket policy và KMS.
- Request/response bằng TLS.
- Endpoint network bằng VPC, security group và endpoint policy phù hợp.
- CloudWatch logs và data capture bằng encryption và retention.
- Secret dùng trong container bằng AWS Secrets Manager hoặc Systems Manager Parameter Store.
- Model artifact và container image bằng versioning, scanning và approval.

Không ghi payload hoặc prediction nhạy cảm vào application logs nếu không có lý do và retention policy rõ ràng.

## 26. Quản lý request, retry và idempotency

Khi endpoint timeout hoặc trả lỗi, client có thể retry. Nhưng retry không phải lúc nào cũng an toàn.

- Với inference thuần, retry thường không làm thay đổi trạng thái nghiệp vụ, nhưng có thể tăng tải và chi phí.
- Với model service có side effect, cần idempotency key hoặc tách inference khỏi side effect.
- Với async, dùng InferenceId/request ID để liên kết input, output và notification.
- Với batch, lưu TransformJobName và input manifest để có thể truy vết, retry hoặc chạy lại.
- Dùng exponential backoff với jitter cho lỗi throttling/transient.
- Không retry vô hạn các lỗi 4xx do payload hoặc permission.
- Đặt timeout client lớn hơn timeout model có chủ đích nhưng vẫn nằm trong SLO.

Với queue, phải có cơ chế xử lý request hết TTL, output thất bại và notification bị trễ. Không coi việc nhận HTTP response ban đầu là bằng chứng inference đã hoàn tất.

## 27. Xử lý lỗi và throttling

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| ModelNotReadyException | Model chưa sẵn sàng hoặc container đang khởi động | Kiểm tra endpoint status, model load và health check |
| ModelError | Inference container lỗi | Kiểm tra model server, payload và container logs |
| ValidationError | Request sai định dạng hoặc vượt giới hạn | Kiểm tra ContentType, payload size và schema |
| ThrottlingException | Vượt concurrency/quota/capacity | Giảm burst, retry có backoff hoặc tăng capacity |
| p99 latency tăng | Queue, cold start, GPU saturation hoặc model load | Đối chiếu ModelLatency, OverheadLatency và utilization |
| Async backlog tăng | Arrival rate cao hơn processing rate | Scale out, tối ưu model hoặc tăng TTL/SLO phù hợp |
| Batch job chậm | Ít input file, instance idle hoặc batch size không phù hợp | Phân vùng dữ liệu, benchmark instance và concurrency |
| Endpoint update thất bại | Quota, image/model incompatibility hoặc deployment config | Kiểm tra endpoint events, service quota và model logs |
| 5xx tăng sau model update | Regression model/container | Dùng alarm và auto-rollback; so sánh blue/green metrics |
| S3 output không có | Execution role thiếu quyền hoặc job chưa hoàn tất | Kiểm tra role, bucket policy, KMS và job status |

Khi xử lý lỗi, lưu request ID, endpoint name, model version, variant, timestamp và error code. Tránh log nguyên payload nếu dữ liệu có thể nhạy cảm.

## 28. Case study: lựa chọn ba kiểu inference cho nền tảng thương mại điện tử

Một nền tảng thương mại điện tử có ba use case:

**A. Fraud detection khi checkout**

- Cần score trong 150 ms ở p95.
- Traffic ổn định trong giờ hoạt động và tăng mạnh vào campaign.
- Chọn SageMaker Real-Time endpoint.
- Đặt minimum instance để duy trì baseline, autoscale theo InvocationsPerInstance.
- Dùng canary deployment khi cập nhật model.
- Alarm theo p95 latency, 5xx và throttling.

**B. OCR hóa đơn và chứng từ**

- File PDF/image có thể lớn, inference mất 20–90 giây.
- Người dùng có thể chờ notification.
- Chọn SageMaker Asynchronous Inference.
- Input/output lưu trong S3; SNS thông báo khi hoàn tất.
- Autoscale theo backlog và age of oldest request.
- Scale-to-zero khi queue trống nếu SLO cho phép.

**C. Customer propensity score**

- Mỗi đêm cần tính score cho 12 triệu khách hàng.
- Kết quả dùng vào ngày hôm sau.
- Chọn SageMaker Batch Transform.
- Partition input thành nhiều file; chọn instance count và MaxConcurrentTransforms theo benchmark.
- Output ghi S3, sau đó Glue/Athena hoặc downstream service sử dụng.

Nếu fraud detection chuyển sang foundation model được quản lý trên Bedrock, đánh giá On-Demand hoặc Provisioned Throughput theo token throughput và quota; nếu cần chấm điểm hàng triệu prompt offline, xem Bedrock batch inference thay cho tự host endpoint.

Ba use case dùng ba kiểu inference khác nhau nhưng có thể chia sẻ IAM governance, model registry, CI/CD, CloudWatch dashboards và quy trình review model.

## 29. Lab: so sánh real-time, async và batch

Thực hiện trong account lab hoặc môi trường đã được phê duyệt. Dùng model nhỏ và dữ liệu giả lập; không cần triển khai production.

### Bước 1: Chuẩn bị model và role

- Chọn model artifact có sẵn trong S3.
- Tạo execution role có quyền đọc artifact.
- Chuẩn bị input S3 và output S3.
- Xác nhận KMS key policy nếu bucket mã hóa bằng customer managed key.

### Bước 2: Tạo real-time endpoint

1. Tạo SageMaker Model.
2. Tạo EndpointConfig với instance type phù hợp.
3. Tạo endpoint.
4. Chờ endpoint ở trạng thái InService.
5. Gọi InvokeEndpoint với payload nhỏ.
6. Ghi lại p50/p95 latency và invocation error.

### Bước 3: Tạo asynchronous endpoint

1. Tạo endpoint configuration với AsyncInferenceConfig.
2. Cấu hình S3 output path và optional SNS topic.
3. Tạo endpoint.
4. Gửi request bằng InvokeEndpointAsync trỏ tới input S3.
5. Ghi lại InferenceId và output location.
6. Kiểm tra kết quả sau khi job hoàn tất.
7. Quan sát backlog metrics.

### Bước 4: Chạy Batch Transform

1. Tạo TransformJob với input S3 prefix.
2. Chọn instance type và instance count.
3. Chọn SplitType và BatchStrategy phù hợp.
4. Chạy job và theo dõi trạng thái.
5. Kiểm tra output file trong S3.
6. So sánh thời gian hoàn thành và cost estimate với endpoint.

### Bước 5: So sánh

Ghi nhận:

- Request latency hoặc job completion time.
- Throughput.
- Instance utilization.
- Số lỗi và retry.
- Chi phí compute ước tính.
- Công sức vận hành và khả năng đáp ứng SLO.

### Bước 6: Dọn dẹp

Xóa endpoint, endpoint configuration, model và tài nguyên lab không còn cần. Dừng hoặc xóa các job thử nghiệm theo quy trình account. Giữ output nếu cần phục vụ bài tập và không chứa dữ liệu thật.

## 30. Checklist trước khi đưa inference vào production

### Lựa chọn kiến trúc

- [ ] Đã phân loại workload online, asynchronous hay batch.
- [ ] Đã đặt SLO latency, throughput, availability và queue wait.
- [ ] Đã xác nhận payload size và processing timeout.
- [ ] Đã so sánh SageMaker và Bedrock theo nơi model được host.
- [ ] Đã kiểm tra feature compatibility và Region/quota.

### Capacity và scaling

- [ ] Instance type được chọn bằng benchmark.
- [ ] Có headroom cho peak traffic và instance failure.
- [ ] Autoscaling metric phản ánh bottleneck thực tế.
- [ ] Min/max capacity và cooldown đã được kiểm thử.
- [ ] Async scale-to-zero có policy scale-up từ zero.
- [ ] Serverless concurrency và Provisioned Concurrency phù hợp traffic profile.
- [ ] Batch input được phân vùng để tận dụng parallelism.
- [ ] Load test gồm sustained load, burst và cold start.

### Deployment và monitoring

- [ ] Model version và container image có thể truy vết.
- [ ] Có canary/blue-green hoặc rollback plan.
- [ ] CloudWatch alarms theo dõi latency, error, throttling và utilization.
- [ ] Có log, trace và request ID để điều tra.
- [ ] Model quality/drift được theo dõi theo use case.
- [ ] Retry, timeout, idempotency và queue TTL được định nghĩa.

### Security và cost

- [ ] Application invoke role có quyền tối thiểu.
- [ ] Execution role chỉ đọc/ghi S3 resource cần thiết.
- [ ] Request, artifact, output và logs được mã hóa.
- [ ] VPC/PrivateLink được dùng khi yêu cầu network isolation.
- [ ] Payload nhạy cảm được masking và retention phù hợp.
- [ ] Cost allocation tag và budget alert đã được thiết lập.
- [ ] Có lịch review capacity, model quality và chi phí.

## 31. Bài tập tự kiểm tra

### Câu 1

Khi nào nên chọn SageMaker Real-Time Inference?

**Đáp án:** Khi ứng dụng cần phản hồi đồng bộ với latency thấp/ổn định và traffic đủ liên tục để duy trì endpoint.

### Câu 2

Serverless Inference phù hợp với loại traffic nào?

**Đáp án:** Traffic gián đoạn hoặc khó dự đoán, payload nhỏ và thời gian xử lý nằm trong giới hạn serverless; cần xem xét cold start.

### Câu 3

Serverless Inference có thể cấu hình Provisioned Concurrency không?

**Đáp án:** Có. Provisioned Concurrency giữ sẵn concurrency để giảm cold start và có thể autoscale; giá trị không được vượt MaxConcurrency.

### Câu 4

SageMaker Asynchronous Inference hỗ trợ payload và processing time tối đa tham khảo bao nhiêu?

**Đáp án:** Tối đa 1 GB payload và tối đa 60 phút xử lý theo giới hạn dịch vụ hiện hành.

### Câu 5

Vì sao Async Inference phù hợp với OCR tài liệu lớn?

**Đáp án:** Request có thể được queue, xử lý lâu, input/output qua S3 và ứng dụng nhận kết quả sau.

### Câu 6

Batch Transform có cần endpoint tồn tại liên tục không?

**Đáp án:** Không. SageMaker tạo compute cho Transform Job và giải phóng sau khi job hoàn tất.

### Câu 7

Tại sao Batch Transform có thể không tận dụng hết nhiều instance nếu chỉ có một input file?

**Đáp án:** Việc phân phối phụ thuộc S3 objects và cách split. Một input object có thể khiến chỉ một instance xử lý trong khi instance khác nhàn rỗi.

### Câu 8

Khác biệt chính giữa SageMaker Batch Transform và Bedrock batch inference là gì?

**Đáp án:** Batch Transform chạy model do SageMaker hosting quản lý; Bedrock batch inference gửi nhiều prompt tới foundation model được Bedrock hỗ trợ, dùng S3 input/output.

### Câu 9

Bedrock batch inference có hỗ trợ provisioned models không?

**Đáp án:** Không theo tài liệu hiện hành.

### Câu 10

Target tracking autoscaling cho real-time endpoint thường dùng metric nào?

**Đáp án:** InvocationsPerInstance là metric predefined thường dùng; target cần được chọn qua benchmark.

### Câu 11

Metric nào hữu ích để autoscale asynchronous endpoint?

**Đáp án:** ApproximateBacklogSizePerInstance; có thể theo dõi thêm ApproximateAgeOfOldestRequest và HasBacklogWithoutCapacity.

### Câu 12

Vì sao async endpoint cần policy scale-up từ zero?

**Đáp án:** Khi instance count bằng 0, backlog-per-instance có thể không đủ để khởi động capacity; HasBacklogWithoutCapacity cho biết có request nhưng không có instance.

### Câu 13

Sự khác nhau giữa horizontal và vertical scaling là gì?

**Đáp án:** Horizontal tăng số instance; vertical đổi sang instance lớn hơn hoặc accelerator mạnh hơn.

### Câu 14

Khi nào nên dùng inference components?

**Đáp án:** Khi nhiều model cần chia sẻ endpoint infrastructure nhưng cần resource allocation, copy count và lifecycle độc lập.

### Câu 15

Blue/green canary deployment giảm rủi ro như thế nào?

**Đáp án:** Chỉ chuyển một phần traffic sang green fleet trước, quan sát bằng CloudWatch alarms trong baking period rồi mới chuyển phần còn lại; có thể auto-rollback.

### Câu 16

Vì sao p95/p99 latency hữu ích hơn average latency cho API tương tác?

**Đáp án:** Average có thể che giấu một nhóm request chậm; p95/p99 phản ánh trải nghiệm của các request ở đuôi phân phối.

### Câu 17

Nếu throughput tăng nhưng queue backlog cũng tăng, hệ thống đang gặp vấn đề gì?

**Đáp án:** Arrival rate có thể vẫn lớn hơn processing rate hoặc capacity chưa scale kịp; cần xem queue age, instance utilization và scaling policy.

### Câu 18

Inference Recommender giúp ích gì?

**Đáp án:** Tự động load test và so sánh cấu hình instance/endpoint để gợi ý hiệu năng và chi phí phù hợp.

### Câu 19

Vì sao không nên retry vô hạn khi endpoint throttling?

**Đáp án:** Retry làm tăng traffic và tải, có thể tạo vòng lặp quá tải; cần exponential backoff, jitter và capacity/quota review.

### Câu 20

Một workload chạy mỗi đêm trên 10 triệu bản ghi, kết quả dùng sáng hôm sau. Lựa chọn nào thường phù hợp?

**Đáp án:** Batch Transform hoặc Bedrock batch inference tùy loại model và nơi model được host; không cần giữ endpoint online cả ngày.

## 32. Tài liệu tham khảo chính thức

- [Inference options in Amazon SageMaker AI](https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model-options.html)
- [Deploy models for inference](https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model.html)
- [Real-Time Inference](https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints.html)
- [Serverless Inference](https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html)
- [Create a serverless endpoint configuration](https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints-create-config.html)
- [Automatically scale Provisioned Concurrency for a serverless endpoint](https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints-autoscale.html)
- [Asynchronous Inference](https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference.html)
- [Autoscale an asynchronous endpoint](https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference-autoscale.html)
- [Alarms and logs for asynchronous endpoints](https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference-monitor.html)
- [Batch Transform](https://docs.aws.amazon.com/sagemaker/latest/dg/batch-transform.html)
- [Automatic scaling of SageMaker AI models](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling.html)
- [Auto scaling policy overview](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling-policy.html)
- [Inference Recommender](https://docs.aws.amazon.com/sagemaker/latest/dg/inference-recommender.html)
- [Inference cost optimization best practices](https://docs.aws.amazon.com/sagemaker/latest/dg/inference-cost-optimization.html)
- [Advanced endpoint options](https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model-advanced.html)
- [Inference components and real-time model hosting](https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints-deploy-models.html)
- [Deployment guardrails](https://docs.aws.amazon.com/sagemaker/latest/dg/deployment-guardrails.html)
- [Blue/green deployments](https://docs.aws.amazon.com/sagemaker/latest/dg/deployment-guardrails-blue-green.html)
- [Process multiple prompts with Bedrock batch inference](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html)
- [Amazon Bedrock capacity and performance](https://docs.aws.amazon.com/bedrock/latest/userguide/capacity-limits-cost-optimization.html)
- [Amazon Bedrock scaling and throughput best practices](https://docs.aws.amazon.com/bedrock/latest/userguide/scaling-throughput-best-practices.html)

Giới hạn payload, timeout, quota, feature compatibility và giá có thể thay đổi theo Region, instance type, model và phiên bản dịch vụ. Trước khi triển khai, đối chiếu tài liệu hiện hành, chạy benchmark với workload đại diện và kiểm tra quota của account.

