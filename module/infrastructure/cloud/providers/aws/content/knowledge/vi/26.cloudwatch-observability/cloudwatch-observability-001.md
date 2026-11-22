# Metrics, logs, traces và chiến lược quan sát AWS

> **Chương:** Quan sát với CloudWatch  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua hạ tầng Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt monitoring với observability và giải thích vai trò của metrics, logs, traces.
2. Mô tả CloudWatch namespaces, metrics, dimensions, timestamps, resolution và statistics.
3. Chọn metrics AWS có sẵn, custom metrics, CloudWatch Agent và OpenTelemetry metrics.
4. Tạo dashboards, metric math, Metrics Insights và alarms phù hợp với service-level objectives (SLOs).
5. Thu thập logs có cấu trúc, thiết lập log groups/streams, retention, encryption và truy vấn bằng Logs Insights.
6. Chuyển log events thành metrics, phân phối logs qua subscription filters và tập trung dữ liệu đa account.
7. Thiết kế distributed tracing bằng OpenTelemetry/AWS Distro for OpenTelemetry (ADOT) và hiểu vai trò của AWS X-Ray.
8. Dùng CloudWatch Application Signals, Application Map, Synthetics và RUM để quan sát service và trải nghiệm người dùng.
9. Liên kết metrics, logs, traces bằng trace ID, request ID, service name và resource attributes.
10. Xây dựng chiến lược observability dựa trên SLI/SLO, alerting, incident response, security và cost control.

## 1. Observability giải quyết bài toán gì?

Một ứng dụng có thể chạy trên Amazon ECS, Lambda, EC2, EKS, RDS, SQS và nhiều dịch vụ AWS khác. Khi khách hàng báo request chậm, đội vận hành cần biết:

- Request chậm ở API gateway, application code, database hay downstream service?
- Tỷ lệ lỗi tăng ở endpoint nào, Region nào, phiên bản nào?
- Lỗi bắt đầu sau deployment hay do dependency đang throttling?
- Có bao nhiêu người dùng bị ảnh hưởng và mức độ ảnh hưởng kéo dài bao lâu?
- Cần rollback, scale out, chuyển traffic hay xử lý dữ liệu lỗi?

**Monitoring** theo dõi các tín hiệu đã xác định trước và cảnh báo khi chúng vượt ngưỡng. **Observability** giúp suy luận trạng thái nội tại của hệ thống từ telemetry mà hệ thống phát ra, kể cả khi vấn đề chưa được dự đoán trước.

Trong thực tế, monitoring là một phần của observability. CloudWatch cung cấp nền tảng thu thập, lưu trữ, truy vấn, trực quan hóa và cảnh báo trên telemetry của workloads AWS.

### 1.1. Ba loại telemetry chính

| Loại | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Metrics** | Điều gì đang thay đổi? Mức độ và xu hướng ra sao? | CPU 85%, p95 latency 900 ms, 30 lỗi/phút, queue backlog 2.000 messages. |
| **Logs** | Sự kiện cụ thể nào đã xảy ra? | Request bị AccessDenied, SQL timeout, validation failure, deployment started. |
| **Traces** | Một request đi qua những thành phần nào và mất thời gian ở đâu? | API → Orders service → RDS → Payment service; database call mất 700 ms. |

Ba loại telemetry bổ sung cho nhau:

- Metric cho biết thời điểm và phạm vi sự cố.
- Log cung cấp chi tiết event và ngữ cảnh.
- Trace thể hiện đường đi và thời gian của một request qua nhiều services.

Một dashboard chỉ có CPU metrics không thể giải thích query nào gây chậm. Một log riêng lẻ có thể cho thấy SQL timeout nhưng không cho biết dependency nào làm request tổng thể bị chậm. Trace giúp đặt các events vào cùng request path.

### 1.2. CloudWatch trong hệ sinh thái AWS

Amazon CloudWatch là dịch vụ quan sát và giám sát cho AWS resources, applications và workloads. Các nhóm khả năng chính:

| Thành phần | Vai trò |
| --- | --- |
| CloudWatch Metrics | Thu thập AWS service metrics và custom metrics. |
| CloudWatch Alarms | Đánh giá metrics/expressions và thực hiện actions khi trạng thái thay đổi. |
| CloudWatch Dashboards | Tổng hợp metrics, alarms, logs và widgets. |
| CloudWatch Logs | Thu thập, lưu trữ, bảo vệ và truy vấn log events. |
| Logs Insights | Truy vấn và phân tích log data. |
| CloudWatch Agent | Thu thập guest OS metrics, logs và một số telemetry từ EC2/on-premises. |
| Container Insights | Quan sát containerized workloads và cluster resources. |
| Lambda Insights | Thu thập telemetry chuyên sâu cho Lambda functions. |
| Application Signals | Quan sát service health, dependencies, operations và SLOs. |
| CloudWatch Application Map | Hiển thị topology và health của services/dependencies. |
| CloudWatch Synthetics | Chạy canaries kiểm tra endpoint/user journey theo lịch. |
| CloudWatch RUM | Thu thập real-user monitoring data từ browser sessions. |

CloudWatch tích hợp với CloudTrail, X-Ray, AWS Distro for OpenTelemetry, Amazon SNS, EventBridge, Systems Manager và nhiều AWS services khác.

## 2. Kiến trúc observability cho một ứng dụng AWS

Ví dụ hệ thống Orders có public API, application service chạy trên ECS, database RDS và queue SQS cho công việc bất đồng bộ.

~~~mermaid
flowchart TB
    USER["Web / Mobile client"] --> API["API Gateway / Load Balancer"]
    API --> ORDERS["Orders service on ECS"]
    ORDERS --> DB["Amazon RDS"]
    ORDERS --> Q["Amazon SQS"]
    Q --> WORKER["Invoice worker"]
    ORDERS -. metrics .-> CW["Amazon CloudWatch"]
    WORKER -. metrics .-> CW
    DB -. AWS service metrics .-> CW
    API -. access logs .-> LOGS["CloudWatch Logs"]
    ORDERS -. structured logs .-> LOGS
    WORKER -. structured logs .-> LOGS
    ORDERS -. OpenTelemetry traces .-> XRAY["AWS X-Ray / Application Signals"]
    WORKER -. OpenTelemetry traces .-> XRAY
    CW --> DASH["Dashboards / Alarms / SLOs"]
    LOGS --> INSIGHTS["Logs Insights / Metric filters"]
    XRAY --> MAP["Application Map / Trace details"]
    DASH --> ONCALL["On-call / Incident response"]
    INSIGHTS --> ONCALL
    MAP --> ONCALL
~~~

Một request tạo ra nhiều telemetry signals:

1. API/load balancer ghi access log và latency/status metrics.
2. Orders service ghi application metrics như request count, error count và duration.
3. Structured logs chứa request ID, trace ID, route và outcome.
4. OpenTelemetry instrumentation tạo spans cho inbound request, database call và downstream HTTP call.
5. RDS/SQS/ECS phát AWS service metrics như database connections, queue depth và CPU.
6. CloudWatch alarms phát cảnh báo; Application Signals/trace map giúp tìm service hoặc dependency gây ảnh hưởng.

### 2.1. Data plane và control plane

Phân biệt hai lớp khi thiết kế:

- **Telemetry data plane:** ứng dụng/agent gửi metrics, logs, traces; CloudWatch tiếp nhận và lưu trữ.
- **Observability control plane:** dashboards, alarms, log retention, sampling, filters, IAM policies và service-level objectives được cấu hình để quản lý cách dữ liệu được dùng.

Một agent chạy tốt không có nghĩa dashboard và alarms đã được thiết kế đúng. Ngược lại, alarm không có dữ liệu đầu vào sẽ không phản ánh trạng thái thật của workload.

### 2.2. Chọn tín hiệu theo câu hỏi vận hành

| Câu hỏi | Tín hiệu phù hợp |
| --- | --- |
| CPU/memory có gần cạn không? | EC2/ECS/Container Insights metrics. |
| Queue backlog có tăng không? | SQS ApproximateNumberOfMessagesVisible và age of oldest message. |
| Tỷ lệ HTTP 5xx có tăng không? | Load balancer/API metrics và application error metrics. |
| Endpoint nào đang chậm? | Application latency metrics, Logs Insights và traces. |
| Database call nào chậm? | Distributed trace, database logs/metrics và Performance Insights khi phù hợp. |
| Một deployment ảnh hưởng service nào? | Deployment events, metrics, traces, application map và version tags. |
| Có người dùng thật bị ảnh hưởng không? | CloudWatch RUM, service metrics và SLO attainment. |

## 3. CloudWatch Metrics: các khái niệm nền tảng

Metric là một chuỗi dữ liệu có tên, namespace, dimensions, timestamps và values. CloudWatch lưu các datapoints theo thời gian để người dùng truy vấn, tạo biểu đồ và đánh giá alarms.

### 3.1. Namespace, metric name và dimensions

- **Namespace:** vùng tên nhóm metrics, ví dụ AWS/EC2, AWS/ECS, AWS/SQS hoặc namespace custom như Orders/Production.
- **Metric name:** tên chuỗi số liệu, ví dụ CPUUtilization, ApproximateNumberOfMessagesVisible hoặc RequestLatency.
- **Dimension:** cặp tên/giá trị dùng để định danh resource hoặc phân loại metric, ví dụ InstanceId=i-..., QueueName=orders-queue.
- **Timestamp:** thời điểm datapoint được ghi nhận.
- **Value:** giá trị đo được.
- **Unit:** đơn vị như Percent, Count, Milliseconds, Bytes hoặc Seconds.

Ví dụ:

| Thuộc tính | Giá trị |
| --- | --- |
| Namespace | AWS/EC2 |
| Metric name | CPUUtilization |
| Dimension | InstanceId = i-0123456789abcdef0 |
| Timestamp | 2026-11-20T04:00:00Z |
| Value | 42.5 |
| Unit | Percent |

CloudWatch coi mỗi tổ hợp namespace, metric name và dimensions là một metric riêng. Nếu publish RequestCount với Service=orders,Environment=prod và một datapoint khác với Service=orders,Environment=staging, đó là hai metric time series.

**Cardinality** tăng khi có nhiều dimension combinations. Tránh dùng user ID, session ID, order ID, request ID hoặc trace ID làm metric dimensions. Những identifiers có số lượng lớn nên nằm trong logs/traces. Dùng dimensions có tập giá trị hữu hạn như Service, Environment, Region, Operation hoặc StatusClass.

### 3.2. AWS service metrics và custom metrics

AWS services tự publish nhiều metrics vào các namespaces tương ứng. Ví dụ:

| Namespace | Metric | Ý nghĩa |
| --- | --- | --- |
| AWS/EC2 | CPUUtilization | CPU utilization của EC2 instance. |
| AWS/ECS | CPUUtilization, MemoryUtilization | Mức sử dụng CPU/memory của ECS cluster/service tùy dimensions. |
| AWS/ApplicationELB | RequestCount, TargetResponseTime, HTTPCode_Target_5XX_Count | Lưu lượng, latency và lỗi của Application Load Balancer. |
| AWS/SQS | ApproximateNumberOfMessagesVisible, ApproximateAgeOfOldestMessage | Backlog và tuổi message. |
| AWS/RDS | DatabaseConnections, CPUUtilization, FreeStorageSpace | Kết nối, CPU và dung lượng storage của database. |
| AWS/Lambda | Invocations, Errors, Duration, Throttles | Lượt gọi, lỗi, thời gian thực thi và throttling. |

Custom metrics phù hợp với những gì AWS service không thể tự biết, ví dụ:

- Số orders được thanh toán thành công.
- Số invoice thất bại do business validation.
- Thời gian xử lý một bước nghiệp vụ.
- Số lần retry từ một downstream provider.
- Tỷ lệ request hoàn thành theo business outcome.

Không tạo custom metric chỉ để lặp lại metric AWS service đã có. Dùng namespace riêng để phân biệt application metrics với metrics do AWS service phát.

### 3.3. Statistics và aggregation

CloudWatch có thể tổng hợp datapoints theo period và statistic:

| Statistic | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| Average | Trung bình. | CPU, memory, latency trung bình khi cần xu hướng tổng quát. |
| Sum | Tổng các giá trị. | Số requests/errors/events trong một period. |
| Minimum | Giá trị nhỏ nhất. | Dung lượng thấp nhất, số lượng thấp nhất. |
| Maximum | Giá trị lớn nhất. | CPU peak, queue backlog peak, latency peak. |
| SampleCount | Số datapoints/samples được tổng hợp. | Kiểm tra volume quan sát. |
| p50 / p90 / p95 / p99 | Percentile. | Phân tích latency distribution và tail latency. |

Average có thể che giấu outliers. Ví dụ 99 requests mất 100 ms và một request mất 10 giây có thể cho average vẫn thấp nhưng p99 rất cao. Với latency user-facing, theo dõi p95/p99 bên cạnh average.

Không phải mọi metric đều hỗ trợ percentile. Percentile cần dữ liệu raw phù hợp; nếu chỉ gửi statistic set đã tổng hợp, percentile có thể không tính được trong nhiều trường hợp.

### 3.4. Period và metric resolution

Period là khoảng thời gian CloudWatch gom datapoints để trả statistic hoặc đánh giá alarm.

- AWS service metrics thường có standard resolution, phổ biến ở granularity 1 phút hoặc cao hơn tùy service.
- Custom metrics có thể dùng standard resolution hoặc high resolution.
- High-resolution custom metric có thể được publish với StorageResolution=1; datapoints có granularity 1 giây.
- Khi đọc high-resolution metrics, các period hỗ trợ gồm 1, 5, 10, 30 giây hoặc bội số của 60 giây.
- High-resolution alarms có thể dùng period 10, 20 hoặc 30 giây theo giới hạn alarm.

High resolution giảm độ trễ phát hiện nhưng tăng số datapoints, API calls/chi phí và lượng noise. Chỉ bật khi workload cần phản ứng dưới phút và có hành động vận hành tương ứng.

### 3.5. Metric retention

CloudWatch giữ datapoints theo độ phân giải và thời gian như sau:

| Độ phân giải/period | Thời gian lưu |
| --- | --- |
| High-resolution dưới 60 giây | 3 giờ |
| 1 phút | 15 ngày |
| 5 phút | 63 ngày |
| 1 giờ | 455 ngày (15 tháng) |

Khi dữ liệu cũ hơn, CloudWatch aggregate sang period thô hơn. Vì vậy, không thể giả định dữ liệu 1 giây sẽ còn truy vấn được sau nhiều ngày. Nếu cần lưu lịch sử dài hạn ở độ chi tiết riêng, thiết kế export/streaming hoặc hệ thống analytics phù hợp.

### 3.6. Dimensions phải nhất quán

Khi query metric, phải chỉ định đúng dimension combination đã publish. CloudWatch không tự aggregate custom metrics bằng cách bỏ một dimension tùy ý. Nếu cần tổng hợp theo service hoặc environment, hãy publish time series tương ứng, dùng metric math/Metrics Insights phù hợp hoặc thiết kế metric schema từ đầu.

Đừng thêm dimension ngẫu nhiên mỗi lần publish. Điều đó có thể tạo time series mới và làm dashboard/alarm truy vấn metric cũ không thấy datapoints mới.

## 4. Thu thập metrics từ AWS resources và workloads

### 4.1. Metrics có sẵn từ AWS services

Nhiều AWS services tự gửi metrics tới CloudWatch mà không cần cài agent. Tuy nhiên, số metrics và tần suất publish phụ thuộc service, resource type và monitoring mode.

Ví dụ, EC2 có basic monitoring; detailed monitoring có thể tăng tần suất metrics. Những metrics như memory usage bên trong guest OS không tự có trong EC2 default metrics vì hypervisor không thể biết mức memory sử dụng bên trong operating system.

Trước khi cài agent, kiểm tra namespace, dimensions và monitoring mode của AWS service.

### 4.2. CloudWatch Agent

Unified CloudWatch Agent thu thập:

- Guest OS metrics như memory, disk, swap, process và network theo cấu hình.
- Logs từ file trên EC2 và on-premises servers.
- Custom metrics qua StatsD/collectd khi được cấu hình.
- Traces từ OpenTelemetry hoặc X-Ray instrumentation trong các cấu hình agent hỗ trợ.

Agent dùng được trên Linux và Windows Server. Metrics do agent publish thường vào namespace CWAgent nếu không đổi namespace. Logs được gửi tới CloudWatch Logs.

### 4.3. Ví dụ cấu hình CloudWatch Agent

Ví dụ JSON cho Linux EC2, thu thập memory/disk metrics và một application log:

~~~json
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "cwagent"
  },
  "metrics": {
    "namespace": "CWAgent",
    "append_dimensions": {
      "InstanceId": "${aws:InstanceId}"
    },
    "metrics_collected": {
      "mem": {
        "measurement": [
          "mem_used_percent"
        ],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": [
          "used_percent"
        ],
        "resources": [
          "/"
        ],
        "metrics_collection_interval": 60
      }
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/orders/application.log",
            "log_group_name": "/orders/prod/application",
            "log_stream_name": "{instance_id}",
            "timezone": "UTC"
          }
        ]
      }
    }
  }
}
~~~

Đây là config minh họa. Trước khi dùng, kiểm tra OS, file paths, agent version, permissions và các options của CloudWatch Agent. Cấp IAM role cho instance với quyền tối thiểu cần thiết để publish metrics và logs. Không đặt access keys trong file agent config.

### 4.4. Cài đặt và điều khiển agent

CloudWatch Agent có thể được cài bằng package manager, SSM Distributor hoặc cơ chế deployment của tổ chức. Sau khi cài, có thể fetch config từ Parameter Store và khởi động agent:

~~~bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c ssm:AmazonCloudWatch-linux \
  -s
~~~

Tên SSM parameter trong ví dụ phải tồn tại và chứa agent configuration. -m ec2 xác định môi trường EC2; với on-premises, cấu hình mode/credentials phù hợp. Dùng Systems Manager State Manager/Distributor để quản lý agent fleet nhất quán thay vì SSH cài thủ công từng instance.

### 4.5. Container Insights và Lambda Insights

- **Container Insights** thu thập và tổng hợp telemetry từ container workloads, bao gồm cluster/service/task/pod/container metrics tùy nền tảng và cấu hình.
- **Lambda Insights** bổ sung system-level metrics và diagnostic data cho Lambda execution environments.
- Cần kiểm tra IAM permissions, agent/extension version, cluster configuration và chi phí ingestion/custom metrics.

Không bật mọi telemetry chỉ vì có thể. Chọn metrics trả lời câu hỏi về saturation, errors, latency và capacity.

## 5. Custom metrics và OpenTelemetry metrics

### 5.1. Khi nào cần custom metric?

Một custom metric nên đại diện cho tín hiệu vận hành có ý nghĩa, có owner và có cách phản ứng rõ ràng.

Ví dụ:

| Metric | Dimensions nên dùng | Mục đích |
| --- | --- | --- |
| OrdersAccepted | Service, Environment, Region | Theo dõi throughput nghiệp vụ. |
| PaymentFailures | Provider, Environment, FailureClass | Phát hiện payment provider lỗi. |
| InvoiceProcessingDuration | Service, Environment, Operation | Theo dõi thời gian xử lý. |
| OutboxBacklog | Service, Environment | Phát hiện event publisher bị nghẽn. |
| CacheHitRate | Service, Environment, CacheName | Đánh giá hiệu quả cache. |

Dùng dimensions ổn định và có số lượng tổ hợp được kiểm soát. Nếu cần phân tích theo order ID, customer ID hoặc trace ID, ghi các giá trị đó trong log/trace rồi truy vấn theo correlation ID.

### 5.2. Publish custom metric bằng AWS CLI

Ví dụ publish số lượng orders được chấp nhận trong một phút:

~~~bash
aws cloudwatch put-metric-data \
  --namespace Orders/Production \
  --metric-data '[{"MetricName":"OrdersAccepted","Dimensions":[{"Name":"Service","Value":"orders-api"},{"Name":"Environment","Value":"prod"}],"Timestamp":"2026-11-20T04:00:00Z","Value":42,"Unit":"Count"}]' \
  --region ap-southeast-1
~~~

Ví dụ high-resolution metric:

~~~bash
aws cloudwatch put-metric-data \
  --namespace Orders/Production \
  --metric-data '[{"MetricName":"RequestLatency","Dimensions":[{"Name":"Service","Value":"orders-api"}],"Value":125,"Unit":"Milliseconds","StorageResolution":1}]' \
  --region ap-southeast-1
~~~

Các giá trị thời gian, Region, namespace và dimension trong ví dụ là minh họa. IAM principal cần quyền cloudwatch:PutMetricData; có thể giới hạn namespace bằng condition phù hợp trong IAM policy. Không gọi PutMetricData cho từng request nếu volume cao mà không tính batch/aggregation và chi phí.

### 5.3. Embedded Metric Format (EMF)

Embedded Metric Format cho phép ứng dụng ghi một JSON log event chứa metric definitions và dimensions. CloudWatch Logs nhận event, sau đó trích xuất metric datapoints từ log.

Ví dụ EMF event:

~~~json
{
  "_aws": {
    "Timestamp": 1795147200000,
    "CloudWatchMetrics": [
      {
        "Namespace": "Orders/Production",
        "Dimensions": [
          ["Service", "Environment"]
        ],
        "Metrics": [
          {
            "Name": "OrdersAccepted",
            "Unit": "Count"
          },
          {
            "Name": "ProcessingLatency",
            "Unit": "Milliseconds"
          }
        ]
      }
    ]
  },
  "Service": "orders-api",
  "Environment": "prod",
  "OrdersAccepted": 1,
  "ProcessingLatency": 84
}
~~~

EMF phù hợp khi ứng dụng đã phát structured logs và muốn tạo metrics mà không phải gọi CloudWatch API trực tiếp ở mỗi business operation. CloudWatch trích metric từ log event theo cấu trúc EMF. EMF không thay thế log schema, log retention hoặc cost controls; các log events vẫn được ingest/lưu theo cấu hình log group.

### 5.4. OpenTelemetry metrics

OpenTelemetry định nghĩa API/SDK và data model chung để instrument applications. Metrics từ OpenTelemetry thường có attributes/labels thay cho CloudWatch dimensions truyền thống.

CloudWatch hỗ trợ OpenTelemetry metrics qua OTLP endpoints và truy vấn bằng PromQL trong các khả năng tương ứng. Cần phân biệt:

- Metrics do AWS service publish thường hiển thị theo namespace/metric/dimensions.
- Custom CloudWatch metrics có namespace và dimensions.
- OpenTelemetry metrics được nhận qua OTLP có labels và được query bằng PromQL; không dùng cùng mental model namespace/dimensions truyền thống.

Chọn một telemetry pipeline có owner rõ ràng. Tránh publish cùng một metric từ CloudWatch Agent, EMF và OpenTelemetry collector mà không có quy ước, vì có thể tạo dữ liệu trùng hoặc dashboard khó hiểu.

## 6. Truy vấn và phân tích metrics

### 6.1. Metrics Explorer và dashboards

Metrics Explorer giúp tìm metrics theo namespace, dimensions, resource tags và filter. Khi thiết kế dashboard, nhóm widgets theo câu hỏi vận hành:

- Golden signals của service: traffic, errors, latency, saturation.
- Health của dependencies: RDS, SQS, DynamoDB, downstream APIs.
- Capacity: CPU, memory, disk, connection pools, queue depth.
- Deployment: version, desired/running tasks, deployment events.
- Business outcomes: orders accepted, payment success, invoice completion.

Không đưa mọi metric có thể tìm được lên một dashboard. Mỗi widget cần trả lời một câu hỏi cụ thể và có người sử dụng.

### 6.2. Metric math

Metric math tạo time series mới bằng cách kết hợp metrics. Ví dụ tính error rate:

~~~text
errorRate = IF(requestCount > 0, 100 * errorCount / requestCount, 0)
~~~

Một biểu đồ error rate có ý nghĩa hơn số lượng errors đơn lẻ khi traffic thay đổi. Có thể dùng metric math trong graph và tạo alarm trên expression trả về một time series.

Metric math cần thống nhất period, dimensions và statistic giữa các input metrics. Khi denominator bằng 0, xử lý rõ ràng để không tạo kết quả không mong muốn.

### 6.3. Metrics Insights

CloudWatch Metrics Insights cho phép truy vấn metrics bằng SQL-like syntax. Ví dụ tìm CPU trung bình theo EC2 instance:

~~~sql
SELECT AVG(CPUUtilization)
FROM SCHEMA("AWS/EC2", InstanceId)
GROUP BY InstanceId
ORDER BY AVG() DESC
LIMIT 20
~~~

Ví dụ tìm SQS queues có backlog lớn:

~~~sql
SELECT MAX(ApproximateNumberOfMessagesVisible)
FROM SCHEMA("AWS/SQS", QueueName)
GROUP BY QueueName
ORDER BY MAX() DESC
LIMIT 20
~~~

Metrics Insights hữu ích khi có nhiều resources và không muốn tạo widget/metric query thủ công cho từng resource. Query có thể aggregate theo dimensions và lọc theo namespace/schema. Khi tạo alarms từ Metrics Insights, hiểu rõ query trả một hay nhiều time series và semantics của alarm contributors.

### 6.4. Search expressions và alarms

CloudWatch metric search expressions có thể tìm nhiều time series cho biểu đồ, nhưng không phải mọi expression đều được hỗ trợ làm alarm. Không tạo alarm trên SEARCH expression. Với alarm cần aggregate nhiều time series, cân nhắc Metrics Insights alarm hoặc metric math expression phù hợp.

### 6.5. Dashboards cho nhiều environments/accounts

Một dashboard vận hành nên thể hiện rõ:

- Account, Region, environment và service đang xem.
- Time range, timezone và period.
- Deployment marker hoặc annotation nếu có.
- Link tới alarm, log group, trace map và runbook.
- Metric dimensions đủ để xác định resource bị ảnh hưởng.

CloudWatch cross-account observability có thể giúp monitoring account xem telemetry được chia sẻ từ source accounts thông qua CloudWatch Observability Access Manager (OAM). Thiết kế sink/link, organization scope và IAM permissions theo mô hình multi-account của tổ chức.

## 7. CloudWatch Alarms: phát hiện vấn đề và kích hoạt hành động

Alarm đánh giá một metric hoặc expression theo period, threshold và evaluation settings. Alarm có ba trạng thái chính:

| Trạng thái | Ý nghĩa |
| --- | --- |
| OK | Dữ liệu đang nằm trong ngưỡng bình thường. |
| ALARM | Điều kiện vi phạm đã được xác nhận theo evaluation settings. |
| INSUFFICIENT_DATA | Chưa có đủ dữ liệu để xác định trạng thái. |

Alarm không tự sửa hệ thống. Nó có thể gửi notification qua SNS, kích hoạt EC2 actions, Auto Scaling actions hoặc các tích hợp automation được cấu hình.

### 7.1. Period, EvaluationPeriods và DatapointsToAlarm

- **Period:** khoảng thời gian tạo một datapoint cho lần đánh giá.
- **EvaluationPeriods (N):** số datapoints gần nhất được xét.
- **DatapointsToAlarm (M):** số datapoints trong N phải vi phạm threshold để alarm chuyển ALARM.

Ví dụ 2 out of 3: Period 60 giây, EvaluationPeriods 3, DatapointsToAlarm 2. Alarm chuyển ALARM khi ít nhất 2 trong 3 datapoints gần nhất vi phạm threshold; không bắt buộc chúng phải liên tiếp.

M out of N giúp tránh alert vì một spike đơn lẻ nhưng vẫn phát hiện sự cố kéo dài. Chọn M/N dựa trên SLO, tốc độ metric publish và thời gian phản ứng cần thiết.

### 7.2. Ví dụ CloudFormation alarm cho SQS backlog

~~~yaml
Resources:
  OrdersBacklogAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmDescription: Orders queue backlog is above the operating threshold
      Namespace: AWS/SQS
      MetricName: ApproximateNumberOfMessagesVisible
      Dimensions:
        - Name: QueueName
          Value: !GetAtt OrdersQueue.QueueName
      Statistic: Maximum
      Period: 60
      EvaluationPeriods: 3
      DatapointsToAlarm: 2
      Threshold: 100
      ComparisonOperator: GreaterThanThreshold
      TreatMissingData: notBreaching
      AlarmActions:
        - !Ref OperationsTopic
      OKActions:
        - !Ref OperationsTopic
~~~

Queue và SNS topic trong ví dụ phải được khai báo hoặc truyền từ stack khác. Ngưỡng 100 là giá trị minh họa; chọn threshold theo backlog capacity, consumer throughput và business processing deadline.

### 7.3. Missing data

Không phải metric nào cũng phát datapoint liên tục. CloudWatch cho phép cấu hình cách xử lý missing data:

| Giá trị | Hành vi |
| --- | --- |
| breaching | Coi datapoint thiếu là vi phạm threshold. |
| notBreaching | Coi datapoint thiếu là không vi phạm. |
| ignore | Giữ nguyên alarm state hiện tại. |
| missing | Nếu không có đủ datapoints, alarm có thể chuyển INSUFFICIENT_DATA. |

Chọn theo ý nghĩa metric:

- Metric heartbeat hoặc metric phải luôn được phát: missing data có thể biểu thị agent/service chết; cân nhắc breaching.
- Metric chỉ phát khi có event lỗi: không có datapoint thường là không có lỗi; cân nhắc notBreaching.
- Metric phát gián đoạn theo thiết kế: cân nhắc ignore/missing và hiểu evaluation range.

Cấu hình sai missing-data behavior có thể gây false alarms hoặc che giấu telemetry pipeline bị hỏng.

### 7.4. Anomaly detection

CloudWatch anomaly detection dùng mô hình để tạo expected band từ lịch sử metric. Alarm có thể so sánh actual metric với band thay vì threshold tĩnh.

Phù hợp với traffic/latency có chu kỳ ngày trong tuần, giờ trong ngày hoặc mùa vụ. Tuy nhiên, anomaly không tự hiểu business impact. Traffic tăng vào campaign có thể bình thường; traffic giảm đột ngột có thể quan trọng hơn một spike CPU. Kết hợp anomaly alarms với SLO/business signals và lịch deployment.

### 7.5. Composite alarms và giảm alert noise

Composite alarm kết hợp trạng thái của các alarms khác bằng logic AND/OR/NOT. Ví dụ chỉ gửi incident khi error rate cao và latency đồng thời vượt SLO, hoặc khi nhiều instances cùng unhealthy.

Composite alarms giúp giảm notification storm, nhưng không được dùng để che mất các failure signals độc lập. Giữ metric alarms gốc để điều tra và xây composite alarm theo service impact.

### 7.6. Alarm actions và notification routing

Một alarm có thể gửi SNS notification khi state chuyển đổi. SNS có thể fan-out tới email, incident tooling hoặc Lambda handler theo integration được phê duyệt.

- Chỉ gửi page tới on-call khi có user/business impact hoặc nguy cơ vượt SLO.
- Warning/capacity signals có thể tạo ticket hoặc gửi channel thông báo.
- Thêm runbook URL, service name, environment, Region, alarm name và dashboard link vào alarm description/notification.
- Định nghĩa ai nhận alert, ai chịu trách nhiệm và escalation khi không có acknowledgement.
- Kiểm tra alarm action sau khi thay topic/role/permissions.

### 7.7. Một alarm tốt phải có hành động

Không tạo alarm chỉ vì có thể đo một metric. Mỗi alarm nên trả lời:

1. Điều kiện nào được xem là bất thường?
2. Nó phản ánh user impact, capacity risk hay telemetry pipeline failure?
3. Ai nhận notification?
4. Người nhận cần kiểm tra dashboard/log/trace nào?
5. Có hành động an toàn nào như rollback, scale, failover hoặc disable feature?
6. Khi nào alarm được đóng hoặc chuyển thành post-incident action?

## 8. CloudWatch Logs: log groups, streams và events

CloudWatch Logs nhận, lưu trữ và truy vấn log events từ AWS services, applications, containers và servers.

### 8.1. Log group, log stream và log event

| Thành phần | Vai trò |
| --- | --- |
| Log group | Nhóm logs theo ứng dụng, service, environment hoặc nguồn phát. |
| Log stream | Dòng events từ một instance, container, function execution source hoặc nguồn log cụ thể. |
| Log event | Một bản ghi gồm timestamp và message. |

Ví dụ cách đặt tên log groups:

- /orders/prod/application
- /orders/prod/access
- /orders/prod/worker
- /payments/prod/application
- /aws/lambda/orders-handler

Tên log group có thể trở thành một phần của operational contract. Đặt tên nhất quán để truy vấn, retention, IAM, subscription filters và cost allocation dễ quản lý.

### 8.2. Retention và log class

Nếu không đặt retention policy, log events có thể được lưu vô thời hạn. Đặt retention theo mục đích, yêu cầu audit, compliance và ngân sách.

CloudWatch Logs có các log classes với bộ tính năng và chi phí khác nhau:

- **Standard:** phù hợp khi cần đầy đủ tính năng tương tác như metric filters, subscription filters, Live Tail, field indexing và nhiều khả năng phân tích.
- **Essentials (formerly Infrequent Access):** hướng tới lưu trữ và truy vấn logs với bộ tính năng được giới hạn hơn so với Standard.
- **Delivery:** dùng cho một số luồng delivery logs tới Amazon S3 hoặc Amazon Data Firehose; log events trong class này được giữ trong CloudWatch Logs trong 2 ngày và thời gian lưu này là cố định.

Trước khi chọn log class, kiểm tra feature matrix hiện hành. Một số khả năng như metric filters, subscription filters, Live Tail hoặc field indexing chỉ có ở Standard. Log class không thể tùy ý đổi qua lại sau khi tạo log group; hãy xác định nhu cầu trước khi triển khai.

### 8.3. Encryption và access control

CloudWatch Logs mã hóa dữ liệu at rest theo mặc định. Có thể cấu hình customer managed KMS key cho log group khi cần kiểm soát key policy/audit.

IAM nên giới hạn:

- Ai được tạo log groups/streams.
- Ai được PutLogEvents.
- Ai được đọc, filter, query hoặc export logs.
- Ai được tạo subscription filters và thay đổi retention/KMS key.
- Ai được xem logs thuộc environment chứa dữ liệu nhạy cảm.

Không cho mọi developer quyền đọc toàn bộ production logs nếu không cần. Tách quyền vận hành, quyền audit và quyền quản trị retention.

### 8.4. Structured logging

Logs nên có cấu trúc JSON để dễ parse và truy vấn. Một event mẫu:

~~~json
{
  "timestamp": "2026-11-20T04:10:12.341Z",
  "level": "ERROR",
  "service": "orders-api",
  "environment": "prod",
  "version": "2026.11.20.3",
  "operation": "CreateOrder",
  "request_id": "req-7c91",
  "trace_id": "1-673e0a24-7d4c9a1234567890abcdef12",
  "duration_ms": 842,
  "error_code": "PAYMENT_PROVIDER_TIMEOUT",
  "message": "Payment provider did not respond before deadline"
}
~~~

Nên có fields thống nhất:

- Timestamp theo UTC.
- Level/severity.
- Service, environment, Region và version.
- Operation/route hoặc event type.
- Request ID và trace ID.
- Duration/status/error code.
- Resource identifier khi cần và được phép.

Structured logs giúp Logs Insights lọc theo field mà không phải parse chuỗi tự do. Không log raw authorization headers, cookies, passwords, tokens, payment data hoặc toàn bộ request bodies chứa PII.

### 8.5. Log level và noise

- DEBUG: chi tiết phục vụ development/diagnostics, thường không bật đại trà production.
- INFO: lifecycle events và business milestones quan trọng.
- WARN: tình huống bất thường có thể tự phục hồi hoặc cần theo dõi.
- ERROR: operation thất bại hoặc cần điều tra.
- FATAL/CRITICAL: lỗi khiến process/service không thể tiếp tục hoạt động bình thường.

Đừng ghi stack trace lặp đi lặp lại cho một lỗi được retry hàng nghìn lần. Dùng sampling/rate limiting phù hợp và metric đếm lỗi để vẫn giữ khả năng phát hiện vấn đề.

## 9. Thu thập logs từ AWS workloads

### 9.1. Lambda

Lambda có thể gửi execution logs tới CloudWatch Logs khi execution role có permissions phù hợp. Log group mặc định thường theo dạng /aws/lambda/function-name. Có thể cấu hình log group, log format, application/system log levels và retention theo nhu cầu.

Không giả định log group đã tồn tại chỉ vì function deploy thành công. Kiểm tra role, log group, Region, retention và log format. Với function quan trọng, tạo log group/retention bằng IaC để kiểm soát vòng đời.

### 9.2. ECS và container workloads

Với ECS, có thể dùng awslogs log driver để gửi stdout/stderr của containers tới CloudWatch Logs. Task execution role cần quyền phù hợp để tạo log stream và gửi log events nếu log group chưa được tạo sẵn.

Ví dụ task definition fragment:

~~~json
{
  "logConfiguration": {
    "logDriver": "awslogs",
    "options": {
      "awslogs-group": "/orders/prod/application",
      "awslogs-region": "ap-southeast-1",
      "awslogs-stream-prefix": "orders"
    }
  }
}
~~~

Tạo log group trước bằng IaC, đặt retention/KMS/log class và permissions rõ ràng. Với EKS/Kubernetes, dùng Fluent Bit/CloudWatch agent hoặc OpenTelemetry Collector theo pipeline đã chọn.

### 9.3. EC2 và on-premises

CloudWatch Agent có thể tail file logs từ Linux/Windows servers. Cấu hình cần xác định file path, log group, stream naming, timestamp format và timezone. Khi logrotate đổi file, kiểm tra agent có tiếp tục theo dõi đúng file mới hay không.

### 9.4. AWS service logs

Nhiều AWS services có thể gửi service/access logs tới CloudWatch Logs, S3 hoặc Firehose tùy dịch vụ và cấu hình. Ví dụ API Gateway, VPC Flow Logs, Route 53 Resolver query logs và một số database/application logs.

Chọn destination theo mục đích:

- CloudWatch Logs: truy vấn và vận hành gần thời gian thực.
- S3: lưu trữ dài hạn, lifecycle, data lake và analytics.
- Firehose: delivery/transform/route logs tới destinations được hỗ trợ.
- OpenSearch: tìm kiếm/phân tích chuyên sâu khi workload cần chức năng đó.

Không bật access logs với mọi fields mặc định. Chỉ ghi những thông tin cần thiết, che/redact dữ liệu nhạy cảm và kiểm soát chi phí ingestion.

## 10. Logs Insights: truy vấn log events

CloudWatch Logs Insights cung cấp ngôn ngữ truy vấn để lọc, parse, aggregate và trực quan hóa logs.

### 10.1. Tìm ERROR gần đây

~~~text
fields @timestamp, level, service, message, trace_id
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
~~~

### 10.2. Đếm lỗi theo khoảng 5 phút

~~~text
filter level = "ERROR"
| stats count(*) as errorCount by bin(5m)
~~~

### 10.3. Tìm latency cao

~~~text
fields @timestamp, service, operation, duration_ms, trace_id
| filter duration_ms >= 1000
| sort duration_ms desc
| limit 100
~~~

### 10.4. Tìm một trace ID

~~~text
fields @timestamp, @logStream, service, operation, message
| filter trace_id = "1-673e0a24-7d4c9a1234567890abcdef12"
| sort @timestamp asc
| limit 200
~~~

### 10.5. Parse log text không có JSON fields

Nếu logs là text format:

~~~text
fields @timestamp, @message
| parse @message "requestId=* status=* durationMs=*" as requestId, status, durationMs
| filter status = "500"
| sort @timestamp desc
| limit 50
~~~

Cấu trúc parse pattern phải khớp log format thực tế. Với ứng dụng mới, structured JSON thường dễ vận hành hơn regex/glob parsing.

### 10.6. Query syntax thường dùng

| Command | Tác dụng |
| --- | --- |
| fields | Chọn fields và tạo calculated fields. |
| filter | Lọc log events theo điều kiện. |
| parse | Trích xuất fields từ chuỗi. |
| stats | Aggregate bằng count/sum/avg/max/min/percentile. |
| sort | Sắp xếp kết quả. |
| limit | Giới hạn số rows trả về. |
| dedup | Loại các kết quả trùng theo fields. |
| pattern | Nhóm logs có cấu trúc lặp lại. |
| diff | So sánh logs giữa hai khoảng thời gian. |
| unnest | Mở rộng list thành nhiều records. |

### 10.7. Tối ưu chi phí query

Logs Insights tính phí dựa trên lượng dữ liệu được scan theo pricing hiện hành. Để giảm scan:

- Chọn đúng log groups, không query toàn account nếu không cần.
- Chọn time range ngắn nhất có thể.
- Lọc sớm theo fields có ích.
- Dùng field indexes khi log class và query hỗ trợ.
- Tránh refresh dashboard query quá thường xuyên.
- Hủy query đang chạy khi không còn cần.
- Dùng log class phù hợp với tính năng cần thiết.

Lưu query dùng lại cho runbooks. Đặt tên theo service/purpose, ví dụ orders/errors-by-operation hoặc payments/latency-outliers.

## 11. Metric filters và subscription filters

### 11.1. Metric filters: biến logs thành metrics

Metric filter đếm các log events khớp filter pattern và publish một CloudWatch metric. Ví dụ đếm application errors trong JSON logs:

~~~yaml
Resources:
  ApplicationLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /orders/prod/application
      RetentionInDays: 30

  ApplicationErrorMetric:
    Type: AWS::Logs::MetricFilter
    Properties:
      LogGroupName: !Ref ApplicationLogGroup
      FilterPattern: '{ $.level = "ERROR" }'
      MetricTransformations:
        - MetricNamespace: Orders/Production
          MetricName: ApplicationErrors
          MetricValue: "1"
          DefaultValue: 0
~~~

Mỗi event match sẽ đóng góp giá trị metric theo MetricValue. DefaultValue có thể giúp tạo zero datapoint khi không có event match trong một số cấu hình, nhưng cần hiểu semantics khi filter dùng dimensions và các giới hạn của metric filter.

Metric filters phù hợp với các log patterns đơn giản, ví dụ ERROR count, authentication failure hoặc validation failures. Với business metrics quan trọng, instrument trực tiếp ở application layer hoặc dùng EMF để schema rõ ràng hơn.

### 11.2. Filter pattern

Filter patterns hỗ trợ matching trên unstructured, JSON và space-delimited logs. Ví dụ:

~~~text
ERROR
~~~

~~~text
{ $.level = "ERROR" && $.service = "orders-api" }
~~~

~~~text
[host, ident, authuser, timestamp, request, status_code = 5*, bytes]
~~~

Test filter pattern với log samples trước khi triển khai. Một pattern quá rộng có thể tạo metric sai và tăng ingestion/alert noise.

### 11.3. Subscription filters: chuyển logs sang hệ thống khác

Subscription filters route log events tới destinations được hỗ trợ như:

- AWS Lambda.
- Amazon Kinesis Data Streams.
- Amazon Data Firehose.
- Một số destination cross-account/partner integration theo cấu hình.

Use cases:

- Centralize security/audit logs.
- Gửi logs tới SIEM.
- Transform/filter rồi lưu S3.
- Stream application events tới analytics pipeline.

Subscription filter không phải cơ chế archive duy nhất. Với yêu cầu lưu trữ dài hạn, dùng export/Firehose/S3 lifecycle theo retention và compliance policy.

### 11.4. Cross-account log centralization

Trong multi-account AWS Organization, có thể tổ chức log archive account hoặc monitoring account. CloudWatch Observability Access Manager (OAM) hỗ trợ chia sẻ telemetry giữa source accounts và monitoring account qua sink/link; CloudWatch Logs cũng có cơ chế centralization/subscription phù hợp với kiến trúc.

Thiết kế rõ:

- Account nào sở hữu logs.
- Account nào được đọc/search.
- Log groups nào được share.
- Region nào là nguồn/đích.
- KMS key policies và IAM roles.
- Retention và data residency requirements.
- Cách xử lý khi organization member account rời khỏi phạm vi.

Không cấp quyền đọc tất cả logs toàn organization nếu chỉ cần share metrics hoặc một nhóm log groups cụ thể.

## 12. Distributed tracing với AWS X-Ray và OpenTelemetry

Distributed tracing theo dõi một request xuyên qua nhiều services và dependencies. Một trace chứa nhiều spans; mỗi span đại diện một operation như HTTP server request, database query, message publish hoặc downstream call.

### 12.1. Trace, span và context propagation

| Thành phần | Ý nghĩa |
| --- | --- |
| Trace ID | Định danh toàn bộ request path. |
| Span ID | Định danh một operation trong trace. |
| Parent Span ID | Liên kết span con với span cha. |
| Trace attributes | Metadata như service, operation, HTTP route, database system. |
| Events | Sự kiện xảy ra trong khoảng thời gian của span. |
| Status | Kết quả của operation, ví dụ OK hoặc ERROR. |

Ví dụ trace path:

~~~mermaid
flowchart LR
    CLIENT["Client request"] --> API["API Gateway span"]
    API --> ORDER["Orders API span"]
    ORDER --> DB["RDS query span"]
    ORDER --> PAY["Payment HTTP span"]
    ORDER --> QUEUE["SQS publish span"]
~~~

Context propagation truyền trace context qua HTTP headers hoặc message metadata để downstream service tiếp tục cùng trace. OpenTelemetry hỗ trợ W3C Trace Context; AWS X-Ray cũng có trace header riêng trong một số integrations. Khi tích hợp nhiều libraries/services, cấu hình propagators nhất quán để không tạo trace rời rạc.

### 12.2. Instrumentation

Có ba cách chính:

- **Automatic instrumentation:** agent/library tự tạo spans cho framework, HTTP clients, database drivers và runtime được hỗ trợ.
- **Manual instrumentation:** developer tạo spans cho business operations mà auto instrumentation không hiểu, ví dụ CalculateShipping hoặc AuthorizePayment.
- **Infrastructure/service instrumentation:** AWS services và gateways phát trace context/telemetry theo integration hỗ trợ.

Không instrument mọi function nhỏ. Tập trung vào request boundaries, downstream dependencies, database calls, message processing và các business steps cần điều tra.

### 12.3. AWS Distro for OpenTelemetry (ADOT)

ADOT là bản phân phối AWS hỗ trợ OpenTelemetry, gồm SDK/auto-instrumentation và Collector components. Dùng OTel API/SDK trong application, rồi export traces/metrics theo pipeline được cấu hình.

Một pipeline tracing có thể gồm:

1. Instrument application bằng OTel SDK/agent.
2. Propagate trace context qua inbound/outbound requests.
3. Gửi OTLP telemetry tới Collector/CloudWatch Agent hoặc endpoint phù hợp.
4. Collector batch, enrich attributes, filter và export.
5. Xem trace trong AWS X-Ray/CloudWatch integrations.

Collector có thể chạy sidecar, daemonset, gateway hoặc agent tùy kiến trúc. Chọn topology dựa trên throughput, failure isolation, network path, retry/buffering và operational ownership.

### 12.4. AWS X-Ray và lộ trình OpenTelemetry

AWS X-Ray lưu trữ và phân tích trace data, hỗ trợ trace details, trace map và tích hợp với CloudWatch. X-Ray vẫn là một backend/điểm quan sát hữu ích cho distributed traces.

**Lưu ý vòng đời SDK:** AWS X-Ray SDKs và daemon đã vào maintenance mode từ **25-02-2026**; từ thời điểm đó AWS giới hạn release chủ yếu cho security fixes. AWS công bố discontinuation of support cho X-Ray SDKs/daemon vào **25-02-2027**. Với ứng dụng mới, ưu tiên OpenTelemetry/ADOT; với hệ thống legacy, lập kế hoạch migration trước mốc end of support. Backend X-Ray tiếp tục có thể nhận traces từ các instrumentation paths được hỗ trợ.

Không nhầm maintenance của X-Ray SDK/daemon với việc CloudWatch/X-Ray trace backend ngừng hoạt động. Thay đổi cần thực hiện chủ yếu ở instrumentation/collection pipeline của ứng dụng.

### 12.5. Sampling và trace volume

Tracing có thể tạo lượng dữ liệu lớn. Sampling quyết định request nào được ghi trace đầy đủ.

- **Head sampling:** quyết định sớm khi bắt đầu trace, đơn giản và giảm overhead.
- **Tail sampling:** quyết định sau khi collector đã quan sát một phần/toàn bộ trace, có thể ưu tiên errors/slow traces nhưng cần collector giữ/buffer trace data.
- **Parent-based sampling:** tôn trọng sampling decision được truyền từ upstream.
- **Consistent sampling:** giữ quyết định nhất quán giữa services để trace không bị đứt đoạn.

Nếu mỗi service tự sampling độc lập, trace có thể chỉ còn một vài spans. Thiết kế propagation/sampling ở ranh giới service. Với traffic thấp hoặc incident quan trọng, có thể tăng sampling tạm thời theo policy và kiểm soát chi phí.

### 12.6. Không đưa dữ liệu nhạy cảm vào spans

Không thêm passwords, access tokens, authorization headers, session cookies, payment details hoặc PII không cần thiết vào span attributes/events. Trace data thường được chia sẻ rộng cho developer/on-call; bảo vệ nó như production logs.

## 13. CloudWatch Application Signals và application map

Application Signals giúp quan sát health của applications/services và dependencies, xây dựng service-level indicators và SLOs. Khi được instrument/configure, CloudWatch có thể hiển thị service operations, dependency relationships, latency/error metrics và liên kết tới traces.

### 13.1. Application Map

Application Map hiển thị topology gồm clients, canaries, services và dependencies. Operator có thể drill down từ nhóm ứng dụng tới từng service/dependency và xem health/related metrics.

Application Map hiện thay thế giao diện Service Map cũ trong CloudWatch Application Signals. X-Ray Trace Map là chế độ xem trace topology riêng, tập trung vào trace data và request paths.

### 13.2. Service operations và golden signals

Application Signals tập trung vào các tín hiệu vận hành quan trọng như:

- Latency: thời gian xử lý request/operation.
- Availability: tỷ lệ operation thành công theo định nghĩa.
- Errors/faults: request lỗi do service hoặc dependency.
- Dependencies: services/resources mà operation phụ thuộc.

Dùng các metrics này để đánh giá service health theo từng operation. Một service có average latency tốt vẫn có thể có một route p99 rất cao; phân tích theo operation và dependency.

### 13.3. Service Level Objectives

CloudWatch hỗ trợ SLOs dựa trên CloudWatch metrics/metric math và Application Signals. SLO định nghĩa mục tiêu reliability trong một evaluation interval.

Hai cách đánh giá thường gặp:

- **Period-based SLO:** mỗi period được đánh giá đạt/không đạt theo threshold.
- **Request-based SLO:** đánh giá tỷ lệ requests tốt trên tổng requests theo good/bad events.

Ví dụ availability SLO: ít nhất 99,9% requests trong rolling window phải thành công. Latency SLO: ít nhất 99% requests hoàn tất trong 500 ms. Các ngưỡng chỉ là ví dụ; chọn dựa trên user expectations và business requirements.

### 13.4. Synthetics và RUM

| Công cụ | Góc nhìn | Ví dụ |
| --- | --- | --- |
| CloudWatch Synthetics | Synthetic monitoring: canary chủ động chạy test theo lịch. | Mỗi phút đăng nhập, tìm kiếm sản phẩm và thêm item vào cart. |
| CloudWatch RUM | Real User Monitoring: dữ liệu từ browser sessions thực tế. | Page load time, JavaScript errors, client-side latency theo browser/region. |

Synthetics kiểm tra journey có kiểm soát kể cả khi chưa có traffic thật. RUM cho biết trải nghiệm thực tế của người dùng. Kết hợp hai loại để phân biệt endpoint đang hoạt động trong synthetic test với trải nghiệm thực tế bị lỗi do browser/network.

### 13.5. Chọn công cụ theo loại workload

- ECS/EKS: Container Insights, CloudWatch Agent/ADOT, Application Signals và traces.
- Lambda: CloudWatch Logs/metrics, Lambda Insights, Application Signals và traces.
- EC2/on-premises: CloudWatch Agent cho guest metrics/logs; OTel/ADOT cho application traces.
- Web application: RUM, Synthetics, API/load balancer metrics và backend traces.
- Serverless event flows: metrics của SQS/EventBridge/Lambda, structured logs và trace context qua event payload/headers theo integration hỗ trợ.

Không phải mọi runtime/service đều có cùng mức automatic instrumentation. Kiểm tra support matrix, agent versions, permissions và cách trace context đi qua async boundaries.

## 14. Liên kết metrics, logs và traces

Correlation là điều biến nhiều telemetry sources thành một công cụ điều tra thống nhất.

### 14.1. Dùng identifiers có chủ đích

| Identifier | Mục đích | Nơi lưu |
| --- | --- | --- |
| trace_id | Liên kết spans của cùng request. | Traces và structured logs. |
| span_id | Nhận diện operation cụ thể. | Traces và logs khi cần. |
| request_id | Định danh request ở API/application boundary. | Access/application logs, response header nếu phù hợp. |
| correlation_id | Liên kết một business workflow qua async events. | Message attributes/payload, logs và spans. |
| deployment_version | Xác định release đang xử lý request. | Metrics dimensions có cardinality kiểm soát, logs, trace resource attributes. |

Trace ID và request ID không nên trở thành dimensions của custom metrics vì cardinality cao. Dùng chúng để truy vấn logs/traces.

### 14.2. Correlation trong async processing

Một request có thể publish SQS message rồi kết thúc HTTP response; worker xử lý sau đó. Trace context cần được inject/extract qua message metadata theo propagator/instrumentation tương thích.

Nếu không thể giữ một trace xuyên suốt, dùng business correlation ID ổn định để nối workflow và tạo span link/trace link khi phù hợp. Không tạo trace ID giả hoặc tái sử dụng request ID như một span ID.

### 14.3. Điều tra từ alarm tới trace

Quy trình thực tế:

1. Alarm báo p95 latency hoặc error rate vượt SLO.
2. Dashboard xác định service, operation, Region và thời điểm.
3. Logs Insights lọc ERROR trong cùng time range, lấy trace ID và request ID.
4. Mở trace để xem span nào chiếm nhiều thời gian hoặc trả lỗi.
5. Kiểm tra downstream metrics/logs của database, queue hoặc dependency.
6. So sánh deployment version và thay đổi cấu hình.
7. Ghi nhận root cause, mitigation và follow-up action.

Một dashboard/notification hữu ích nên có link hoặc thông tin đủ để người trực mở đúng log group, time range và trace.

## 15. Chiến lược observability: SLI, SLO và golden signals

Observability có giá trị khi telemetry được gắn với user impact và quyết định vận hành. Không bắt đầu bằng câu hỏi "có thể thu thập metric nào?" mà bắt đầu từ "người dùng cần hệ thống hoạt động như thế nào?".

### 15.1. SLI, SLO và SLA

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| SLI | Service Level Indicator: phép đo reliability/performance. | Tỷ lệ requests thành công, p95 latency. |
| SLO | Service Level Objective: mục tiêu cho SLI trong một cửa sổ thời gian. | 99,9% requests thành công trong 30 ngày. |
| SLA | Service Level Agreement: cam kết dịch vụ với khách hàng, thường có điều khoản và hậu quả nếu vi phạm. | Cam kết availability và service credits. |

SLO thường nên có ngưỡng nội bộ nghiêm ngặt hơn SLA để team còn thời gian khắc phục trước khi vi phạm cam kết.

### 15.2. Định nghĩa SLI có denominator rõ ràng

Ví dụ availability SLI:

\[
Availability = \frac{Good\ Requests}{Valid\ Requests} \times 100\%
\]

Latency SLI:

\[
Latency\ Compliance = \frac{Requests\ under\ threshold}{Valid\ Requests} \times 100\%
\]

Nếu chỉ đếm errors mà không biết tổng requests, không thể phân biệt 20 errors trên 100 requests với 20 errors trên 1 triệu requests. Luôn xác định numerator, denominator, excluded traffic và evaluation window.

### 15.3. Golden signals

Bốn golden signals thường dùng cho service:

1. **Latency:** thời gian phục vụ requests, thường theo p50/p95/p99.
2. **Traffic:** số requests/operations trong một đơn vị thời gian.
3. **Errors:** tỷ lệ hoặc số lượng requests thất bại.
4. **Saturation:** mức độ cạn tài nguyên như CPU, memory, connections, queue capacity hoặc thread pools.

Với infrastructure, mô hình USE cũng hữu ích:

- Utilization: tài nguyên được sử dụng bao nhiêu.
- Saturation: có bao nhiêu công việc chờ vì thiếu tài nguyên.
- Errors: có lỗi do resource/dependency hay không.

### 15.4. Error budget

Error budget là phần không đạt SLO mà service có thể chịu trong evaluation window. Ví dụ SLO availability 99,9% cho phép tối đa 0,1% valid requests thất bại trong cửa sổ đó.

Khi error budget bị tiêu thụ nhanh:

- Ưu tiên reliability work và giảm rủi ro deployment.
- Hạn chế thay đổi không cần thiết.
- Kiểm tra dependency, capacity và failure patterns.
- Đánh giá rollout/canary/rollback policy.

Error budget biến SLO thành công cụ ra quyết định giữa feature velocity và reliability.

### 15.5. Alert theo user impact

Ưu tiên cảnh báo theo thứ tự:

- User-facing symptoms: availability, latency, error rate, failed transactions.
- Critical dependencies: database unavailable, queue age vượt deadline, downstream provider failure.
- Capacity risks: disk gần đầy, connection pool cạn, memory pressure kéo dài.
- Telemetry pipeline failures: agent stopped, log ingestion gap, trace export errors.

Không page on-call cho mọi spike CPU hoặc mọi warning log. Một alert nên có severity, owner, runbook và hành động rõ ràng.

### 15.6. Multi-window alerting và burn rate

SLO burn rate cho biết error budget đang bị tiêu thụ nhanh đến mức nào. Một cửa sổ ngắn phát hiện sự cố nghiêm trọng nhanh; cửa sổ dài tránh page vì spike ngắn.

Có thể thiết kế cặp alert nhanh/chậm:

- Fast burn: error budget tiêu thụ nhanh trong vài phút, cần page.
- Slow burn: reliability suy giảm kéo dài trong vài giờ, tạo ticket hoặc cảnh báo có mức ưu tiên thấp hơn.

CloudWatch SLO/alarms có thể hỗ trợ theo dõi attainment và burn-rate signals tùy cách cấu hình. Định nghĩa chính xác window, threshold, paging policy và response time trong runbook.

## 16. Dashboard và runbook cho vận hành

### 16.1. Service overview dashboard

Một dashboard overview cho Orders API có thể chia thành các hàng:

| Khu vực | Widgets nên có |
| --- | --- |
| User impact | Availability SLI, error rate, p95/p99 latency, request rate. |
| Application | CPU/memory, task count, duration, throttles, process health. |
| Dependencies | RDS connections/latency, SQS backlog/age, downstream API errors. |
| Deployment | Current version, deployment events, desired/running tasks. |
| Observability health | Agent status, log ingestion, missing metrics, trace volume/sampling. |

Dashboard nên có biến thể theo environment/Region hoặc dùng resource tags/filters để người vận hành tìm đúng workload.

### 16.2. Dashboard cho dependency

Dashboard dependency giúp xác định lỗi nằm ở service hay thành phần phía sau:

- RDS: CPU, free storage, database connections, read/write latency, replica lag nếu có.
- SQS: visible/not visible messages, oldest message age, empty receives, DLQ depth.
- Lambda: invocations, errors, duration, throttles, concurrent executions.
- Load balancer: request count, target response time, 4xx/5xx, healthy host count.
- Downstream HTTP provider: request rate, error rate, timeout, retry count.

Không so sánh metrics có statistic/period/dimensions khác nhau mà không ghi rõ. Dashboard nên hiển thị units và time range.

### 16.3. Runbook gắn với alarm

Một runbook cho alarm HighOrdersErrorRate nên có:

1. Xác định environment, Region, deployment version và thời điểm bắt đầu.
2. Mở dashboard service và kiểm tra availability/latency/error rate.
3. Dùng Logs Insights lọc ERROR theo time range và trace ID.
4. Mở traces để xác định span/dependency gây lỗi.
5. Kiểm tra dependency metrics, CloudTrail/deployment events và recent config changes.
6. Chọn mitigation: rollback, scale, disable feature, failover hoặc rate limit theo playbook đã phê duyệt.
7. Xác nhận SLI phục hồi và alarm trở về OK.
8. Ghi incident timeline, root cause và preventive actions.

Runbook không nên chứa secrets hoặc hướng dẫn thay đổi production không có guardrails. Link tới dashboards, logs query và service ownership.

### 16.4. Incident timeline

Khi xảy ra incident, thống nhất timezone UTC và ghi lại:

- Thời điểm alert đầu tiên.
- Thời điểm user impact bắt đầu/kết thúc.
- Deployment/config change gần nhất.
- Detection, acknowledgement và mitigation time.
- Root cause và contributing factors.
- SLI/SLO impact và error budget consumed.
- Follow-up tasks có owner/due date.

Dữ liệu này giúp cải thiện alert thresholds, detection coverage và operational readiness.

## 17. Kiến trúc tham chiếu: quan sát Orders trên ECS, RDS và SQS

~~~mermaid
flowchart TB
    subgraph APP["Workload account"]
      ECS["ECS Orders service"]
      RDS["RDS"]
      SQS["SQS + DLQ"]
      AGENT["CloudWatch Agent / ADOT Collector"]
      ECS --> RDS
      ECS --> SQS
      ECS --> AGENT
      RDS -. service metrics .-> CW
      SQS -. service metrics .-> CW
      ECS -. structured logs .-> LOGS
      AGENT -. host/container telemetry .-> CW
      AGENT -. logs/traces .-> LOGS
      AGENT -. traces .-> XRAY
    end
    subgraph OBS["Monitoring account"]
      CW["CloudWatch Metrics / Alarms"]
      LOGS["CloudWatch Logs"]
      XRAY["X-Ray / Application Signals"]
      DASH["Dashboards / SLOs / Application Map"]
      CW --> DASH
      LOGS --> DASH
      XRAY --> DASH
      DASH --> ONCALL["On-call / Incident tools"]
    end
~~~

Một triển khai multi-account có thể dùng OAM links để chia sẻ metrics/logs/traces phù hợp từ workload accounts tới monitoring account. Nếu dùng log subscriptions/Firehose, bảo đảm delivery role, destination policy, encryption và retry behavior đúng.

### 17.1. Luồng dữ liệu

- ECS task role cấp quyền ứng dụng gọi AWS APIs; task execution role cấp quyền lấy image/log configuration và gửi logs theo cấu hình ECS.
- CloudWatch Agent/ADOT Collector có IAM role riêng, giới hạn quyền publish metrics/logs/traces cần thiết.
- CloudWatch alarms theo dõi service SLOs và infrastructure saturation.
- Structured logs chứa trace ID và deployment version.
- Trace spans mô tả database query, SQS publish và downstream calls.
- Application Signals/App Map hiển thị service/dependency health.
- Monitoring account tổng hợp dashboards, alarms và incident integrations.

Tách application role và telemetry agent role để một thành phần không có quyền vượt quá nhu cầu.

### 17.2. Những câu hỏi cần trả lời trước khi go-live

- Có metric nào đo request rate, errors, p95/p99 và saturation?
- Có log groups với retention/KMS/log class đúng policy?
- Có trace context propagation qua synchronous và asynchronous calls?
- Có SLO và alarm cho các journeys quan trọng?
- Có dashboard và runbook cho mỗi page-level alarm?
- Có thể truy cập telemetry từ monitoring account mà không cấp quyền quá rộng?
- Có test alert routing, missing data và agent failure?
- Có dự toán ingestion, retention, query, metrics và trace costs?

## 18. Bảo mật, quyền truy cập và quản trị dữ liệu telemetry

### 18.1. Least privilege cho telemetry

Phân biệt permissions theo vai trò:

- Application/agent publisher: PutMetricData, PutLogEvents và trace write APIs cần thiết.
- Operator: đọc metrics/logs/traces, xem alarms/dashboards.
- Observability administrator: tạo log groups, retention, metric filters, dashboards, alarms và OAM links.
- Security/audit: truy cập dữ liệu theo phạm vi audit được phê duyệt, có audit trail.

Không cấp CloudWatchFullAccess hoặc LogsFullAccess cho mọi workload role nếu chỉ cần publish một namespace/log group.

### 18.2. Secrets và PII trong logs/traces

Telemetry có thể vô tình chứa dữ liệu nhạy cảm:

- Authorization headers, cookies, API tokens.
- Password, connection strings, database query parameters.
- Email, phone, address, customer identifiers.
- Payment details hoặc health/personal data.

Thiết kế logging schema theo allowlist fields; redact trước khi emit; dùng CloudWatch Logs data protection/masking khi phù hợp. Kiểm tra cả exception messages và third-party SDK logs.

### 18.3. Encryption và key management

- CloudWatch metrics được quản lý bởi dịch vụ; log groups có encryption at rest mặc định.
- Với CloudWatch Logs, có thể dùng customer managed KMS key cho log groups theo yêu cầu.
- Xem xét KMS key policy, rotation, grants và quyền decrypt của consumers.
- Với cross-account destinations, kiểm tra cả source IAM policy và destination resource policy.
- Không xóa KMS key còn được dùng để giải mã logs đã lưu.

### 18.4. CloudTrail và audit

CloudTrail ghi lại nhiều control-plane API calls như tạo alarm, thay đổi retention, subscription filters, log groups, dashboards và OAM configuration. Dùng CloudTrail để audit ai thay đổi observability controls và khi nào.

CloudTrail event history không thay application logs hoặc distributed traces. Nó cho biết AWS API/control-plane actions; logs/traces mô tả hoạt động bên trong application request path.

### 18.5. Data residency và retention

Xác định Region nơi telemetry được lưu, nơi dữ liệu được share/replicate và yêu cầu pháp lý/contract. Retention phải theo data classification và audit policy. Không giữ mọi debug logs vô thời hạn nếu không có lý do; cũng không xóa audit logs sớm hơn policy.

## 19. Chi phí và tối ưu telemetry

Observability có chi phí ingestion, storage, query, custom metrics, alarms, dashboards, traces, canaries và data transfer. Chi phí thay đổi theo Region, volume, retention, resolution và pricing model hiện hành.

### 19.1. Các cost drivers

| Thành phần | Yếu tố ảnh hưởng chi phí |
| --- | --- |
| Metrics | Số custom metrics/time series, dimensions, high-resolution datapoints, API usage. |
| Alarms | Số metric alarms, high-resolution alarms, composite alarms và loại query. |
| Dashboards | Số dashboards, widgets và refresh frequency. |
| Logs | Data ingestion, storage volume, retention, log class, query scan và subscriptions. |
| Traces | Trace ingestion, sampling rate, storage/analysis và downstream integrations. |
| Application Signals | Service/operation telemetry, metrics, traces và SLO usage theo pricing. |
| Synthetics | Số canary runs, runtime và artifacts. |
| RUM | Số user sessions/events được thu thập. |
| Agents/Collectors | Compute resources, network transfer và telemetry volume. |

### 19.2. Giảm chi phí metrics

- Giới hạn dimensions và cardinality.
- Không tạo custom metrics trùng AWS service metrics.
- Chọn standard resolution trừ khi cần phát hiện dưới phút.
- Batch/aggregate metrics khi phù hợp thay vì gửi datapoint cho mọi event.
- Dọn metrics không còn được dùng; kiểm tra dashboard/alarms trước khi xóa.
- Dùng metric math/Metrics Insights để tổng hợp khi phù hợp, tránh tạo hàng loạt time series chỉ để làm dashboard.

### 19.3. Giảm chi phí logs

- Chọn log levels phù hợp production; hạn chế DEBUG.
- Redact/transform và loại bỏ fields không cần trước khi ingest.
- Đặt retention theo data classification.
- Chọn log class theo tính năng cần thiết.
- Dùng subscription/Firehose/S3 cho archive dài hạn khi phù hợp.
- Giới hạn Logs Insights time range và log groups.
- Tránh dashboard refresh liên tục làm query scan lặp lại.
- Kiểm tra log duplication do cả application stdout và agent file tail cùng gửi một nội dung.

### 19.4. Giảm chi phí traces

- Sampling theo traffic/risk; ưu tiên errors/slow traces nếu pipeline hỗ trợ tail sampling.
- Không capture payload/body lớn hoặc attributes không cần.
- Giới hạn span events và high-cardinality attributes.
- Chỉ instrument dependencies quan trọng.
- Theo dõi collector queue/retry và export failures để không tăng chi phí vô ích.

### 19.5. Cost ownership

Gắn tags/metadata vào log groups, dashboards, canaries và workloads khi resource hỗ trợ. Gán owner cho namespace, log group và alarm. Định kỳ rà soát:

- Telemetry nào đang được ingest nhưng không có dashboard/query/alert consumer?
- Có log group nào retention vô thời hạn mà không cần thiết?
- Có custom metrics tăng cardinality bất thường?
- Có trace sampling rate quá cao so với giá trị điều tra?
- Có canary chạy quá thường xuyên hoặc test flow tốn kém?
- Có alarms trùng lặp hoặc không có owner?

Không giảm sampling/retention một cách mù quáng trong incident hoặc khi đang cần evidence cho security investigation.

## 20. AWS CLI và thao tác vận hành thường dùng

Các lệnh sau là ví dụ truy vấn/kiểm tra trạng thái. Thay account, Region, resource IDs và time range bằng giá trị của môi trường thực tế.

### 20.1. Liệt kê metrics theo namespace

~~~bash
aws cloudwatch list-metrics \
  --namespace AWS/SQS \
  --region ap-southeast-1
~~~

ListMetrics không đảm bảo hiển thị mọi metric nếu metric không có datapoints gần đây hoặc chưa được publish trong phạm vi truy vấn. Khi biết dimensions, dùng metric explorer/API phù hợp.

### 20.2. Lấy statistics của EC2 CPU

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-0123456789abcdef0 \
  --start-time 2026-11-20T03:00:00Z \
  --end-time 2026-11-20T04:00:00Z \
  --period 300 \
  --statistics Average Maximum \
  --region ap-southeast-1
~~~

Start/end time dùng UTC và period phải phù hợp resolution/retention. Kết quả datapoints có thể không theo thứ tự thời gian; sắp xếp trước khi phân tích.

### 20.3. Kiểm tra alarms

~~~bash
aws cloudwatch describe-alarms \
  --state-value ALARM \
  --region ap-southeast-1
~~~

~~~bash
aws cloudwatch describe-alarms \
  --alarm-names OrdersBacklogAlarm \
  --region ap-southeast-1
~~~

Đọc StateReason, metric dimensions, threshold, evaluation periods, treat missing data và actions.

### 20.4. Liệt kê log groups

~~~bash
aws logs describe-log-groups \
  --log-group-name-prefix /orders/prod \
  --region ap-southeast-1
~~~

Kiểm tra retentionInDays, storedBytes, logGroupClass và kmsKeyId theo response. Nếu retention không được đặt, dữ liệu có thể tiếp tục lưu cho tới khi bị xóa thủ công.

### 20.5. Chạy Logs Insights query

StartQuery nhận epoch seconds cho start/end time:

~~~bash
aws logs start-query \
  --log-group-names /orders/prod/application \
  --start-time 1795143600 \
  --end-time 1795147200 \
  --query-string 'fields @timestamp, level, message, trace_id | filter level = "ERROR" | sort @timestamp desc | limit 50' \
  --region ap-southeast-1
~~~

Lệnh trả queryId. Lấy kết quả bằng:

~~~bash
aws logs get-query-results \
  --query-id QUERY-ID \
  --region ap-southeast-1
~~~

Query có thể ở trạng thái Scheduled/Running/Complete/Failed/Cancelled. Không poll liên tục; đợi theo khoảng hợp lý và giới hạn time range để giảm scan.

### 20.6. Kiểm tra X-Ray traces

Dùng CloudWatch console Trace Map hoặc X-Ray trace views để lọc theo service, time range, error/fault và latency. CLI/API có thể lấy trace summaries/details theo quyền và thời gian; trace data có thể được sample nên không phải mọi request đều xuất hiện.

## 21. Kiểm thử observability trước production

### 21.1. Unit và component tests

Kiểm tra application instrumentation/logging ở mức code:

- Mỗi request có correlation/request ID hợp lệ.
- Logs có timestamp, severity, service, environment và trace ID theo schema.
- Không log secrets/PII trong success/error paths.
- Error handling ghi đúng status/error code.
- Custom metrics có namespace/name/dimensions thống nhất.
- Instrumentation không tạo span trùng hoặc làm mất context khi gọi downstream.

### 21.2. Integration tests

Trong sandbox AWS:

1. Deploy workload và CloudWatch Agent/ADOT Collector bằng IaC.
2. Gửi synthetic traffic có request IDs xác định.
3. Xác nhận metrics xuất hiện với đúng namespace/dimensions/units.
4. Xác nhận logs vào đúng log group/stream, retention và KMS policy.
5. Query logs bằng Logs Insights và tìm được trace ID.
6. Xác nhận traces chứa inbound span và downstream spans.
7. Tạo alarm test threshold thấp trong sandbox và xác nhận SNS routing.
8. Dừng agent/collector có kiểm soát để kiểm tra telemetry health alerts.
9. Kiểm tra dashboard và runbook link.
10. Đo ingestion/query volume và ước lượng chi phí.

### 21.3. Failure-path tests

- IAM role thiếu PutMetricData hoặc PutLogEvents.
- CloudWatch Agent không lấy được SSM config.
- Log group sai Region hoặc retention không được set.
- Subscription destination policy deny delivery.
- Collector mất network hoặc exporter throttled.
- Trace context bị đứt qua async message.
- Metric không có datapoints và alarm xử lý missing data sai.
- Logs Insights query scan quá rộng.
- KMS key policy chặn đọc logs.
- RUM/Synthetics canary báo false positive do test dependency không ổn định.

Test cả application failure lẫn telemetry pipeline failure. Một hệ thống có thể đang lỗi nhưng không ai biết nếu telemetry collector cũng bị hỏng.

## 22. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Monitoring và observability là một.” | Monitoring cảnh báo trên signals đã biết; observability hỗ trợ suy luận trạng thái nội tại từ telemetry. |
| “Metric, log và trace thay thế được nhau.” | Metrics cho xu hướng, logs cho events, traces cho request path và timing. |
| “CPU EC2 cho biết memory usage trong OS.” | Guest memory thường cần CloudWatch Agent hoặc telemetry khác. |
| “Dimensions càng nhiều càng tốt.” | Cardinality cao làm tăng time series/chi phí và khiến query/alarm khó quản lý. |
| “Average latency đủ để biết trải nghiệm.” | p95/p99 cho thấy tail latency và outliers. |
| “High-resolution metrics nên bật cho mọi thứ.” | Chỉ dùng khi cần phát hiện dưới phút và có hành động tương ứng. |
| “Metric retention luôn giữ 1-second datapoints lâu dài.” | High-resolution data dưới 60 giây chỉ giữ 3 giờ trước khi aggregate. |
| “Không có datapoint nghĩa là hệ thống khỏe.” | Có thể metric không phát, agent chết hoặc telemetry bị mất; missing-data policy phải phù hợp. |
| “Alarm chỉ cần threshold.” | Cần period, M/N, missing-data behavior, owner và runbook. |
| “Mọi alarm đều nên page on-call.” | Page cho user impact/risk thực; các warning khác có thể tạo ticket. |
| “Logs lưu vô thời hạn là tốt.” | Cần retention theo audit, privacy và cost. |
| “Chỉ cần grep log text.” | Structured JSON và Logs Insights giúp lọc/aggregate/correlate hiệu quả hơn. |
| “Logs Insights query càng rộng càng dễ điều tra.” | Chọn đúng log groups và time range để giảm scan/cost. |
| “Metric filter thay được mọi application metric.” | Metric filter phù hợp patterns đơn giản; business metrics nên instrument/EMF rõ ràng. |
| “Subscription filter là archive đầy đủ.” | Subscription delivery và long-term archive là hai yêu cầu khác nhau. |
| “Trace ID nên là metric dimension.” | Trace ID cardinality cao; để trong logs/traces. |
| “Mỗi service tự sampling là được.” | Sampling độc lập có thể làm trace bị đứt; cần propagation/sampling strategy chung. |
| “X-Ray SDK vẫn là lựa chọn tốt nhất cho app mới.” | X-Ray SDK/daemon đang maintenance và end support 25-02-2027; ưu tiên OpenTelemetry/ADOT. |
| “Application Map và X-Ray Trace Map là cùng một view.” | Application Map tập trung service/dependency health; Trace Map tập trung trace topology. |
| “RUM và Synthetics giống nhau.” | RUM quan sát real user sessions; Synthetics chủ động chạy canary tests. |
| “CloudWatch Agent thay thế mọi instrumentation.” | Agent thu thập telemetry; application vẫn cần instrumentation/log schema/trace context. |
| “Dashboard nhiều widgets nghĩa là observability tốt.” | Dashboard phải trả lời câu hỏi vận hành và hỗ trợ quyết định. |
| “SLO là SLA.” | SLO là mục tiêu nội bộ/operational objective; SLA là cam kết dịch vụ với khách hàng. |
| “CloudTrail thay application logs.” | CloudTrail ghi AWS API/control-plane activity; application logs/traces mô tả request execution. |
| “Telemetry không chứa dữ liệu nhạy cảm.” | Logs/traces có thể vô tình chứa tokens, PII và payloads; cần redaction/access controls. |

## 23. Bài tập thực hành có đáp án gợi ý

### Bài tập 1 — Chọn metric cho Orders API

**Đề:** Team chỉ theo dõi CPUUtilization nhưng khách hàng báo checkout chậm.

**Đáp án:** Bổ sung request rate, error rate, p95/p99 latency và dependency latency. Theo dõi RDS query time, connection count, SQS backlog/age và traces để xác định bottleneck.

### Bài tập 2 — Custom metric dimensions

**Đề:** Developer muốn publish PaymentLatency với dimensions OrderId và CustomerId.

**Đáp án:** Không dùng các IDs có cardinality lớn làm dimensions. Dùng Service, Environment, Provider, Operation; ghi OrderId/CustomerId trong structured logs/traces nếu được phép và có chính sách privacy.

### Bài tập 3 — EC2 memory usage

**Đề:** Dashboard chỉ có CPUUtilization và team muốn biết memory pressure trong Linux instance.

**Đáp án:** Cài unified CloudWatch Agent với IAM role phù hợp, cấu hình memory measurements và namespace/dimensions nhất quán. Không kỳ vọng EC2 default metrics cung cấp guest memory.

### Bài tập 4 — High-resolution metrics

**Đề:** Một workload cần phát hiện saturation trong vòng 10 giây.

**Đáp án:** Cân nhắc custom high-resolution metrics và high-resolution alarm với period phù hợp. Đánh giá datapoint volume, cost, sampling và khả năng phản ứng của on-call trước khi bật.

### Bài tập 5 — Average latency thấp nhưng khách hàng vẫn phàn nàn

**Đề:** Average latency là 120 ms nhưng nhiều request có thể mất 4 giây.

**Đáp án:** Xem p95/p99, phân nhóm theo operation/Region/version và dùng traces để tìm tail latency. Average không đại diện đầy đủ cho trải nghiệm.

### Bài tập 6 — Alarm chuyển INSUFFICIENT_DATA

**Đề:** Alarm queue age không có datapoints trong khoảng đánh giá.

**Đáp án:** Xác định metric có phát liên tục hay chỉ khi có event, kiểm tra queue/Region/dimensions và agent/service telemetry. Chọn treat missing data phù hợp; không tự động coi missing là healthy.

### Bài tập 7 — Queue backlog tăng nhưng CPU worker thấp

**Đề:** SQS backlog tăng, worker CPU thấp.

**Đáp án:** Kiểm tra worker concurrency, message visibility, permissions, downstream throttling, poison messages và consumer errors. CPU thấp có thể do worker đang chờ dependency hoặc không nhận được messages.

### Bài tập 8 — Tìm lỗi theo trace ID

**Đề:** Customer support cung cấp request ID; operator cần xem toàn bộ request path.

**Đáp án:** Tìm structured logs theo request ID, lấy trace ID, mở trace và kiểm tra spans/dependencies. Không biến request ID thành metric dimension.

### Bài tập 9 — Logs Insights query scan quá nhiều

**Đề:** Query ERROR trên mọi log groups trong 30 ngày rất chậm và tốn chi phí.

**Đáp án:** Chọn đúng service log groups, thu hẹp time range, lọc sớm theo level/service, dùng field indexes khi được hỗ trợ và lưu query runbook.

### Bài tập 10 — Log group lưu vô thời hạn

**Đề:** Log group application có retention chưa được đặt.

**Đáp án:** Xác định audit/data classification policy, chọn retention, encryption/KMS và export archive nếu cần. Quản lý log group bằng IaC để retention không phụ thuộc thao tác console.

### Bài tập 11 — Chuyển ERROR logs thành alarm

**Đề:** Team muốn cảnh báo khi application ghi nhiều JSON logs có level ERROR.

**Đáp án:** Có thể tạo metric filter trên Standard log group với pattern JSON level=ERROR, publish metric và tạo alarm. Với business errors, cân nhắc instrument custom metric/EMF để phân biệt error classes.

### Bài tập 12 — Trace bị đứt ở SQS worker

**Đề:** API trace kết thúc sau SendMessage; worker trace không liên kết với API request.

**Đáp án:** Kiểm tra trace context propagation qua message metadata, OTel propagator và consumer extraction. Nếu async workflow không phù hợp một parent-child trace đơn, dùng correlation ID/span links theo semantics.

### Bài tập 13 — X-Ray SDK cũ

**Đề:** Java service đang dùng X-Ray SDK/daemon và cần nâng cấp trong năm 2026.

**Đáp án:** Lập kế hoạch migration sang OpenTelemetry/ADOT. X-Ray SDK/daemon đã vào maintenance từ 25-02-2026 và support kết thúc 25-02-2027; kiểm tra instrumentation, context propagation, collector và trace backend.

### Bài tập 14 — RUM hay Synthetics?

**Đề:** Team cần biết checkout page có hoạt động và người dùng thật có gặp lỗi JavaScript không.

**Đáp án:** Dùng Synthetics để chạy scripted journey theo lịch; dùng RUM để quan sát browser sessions thật. Kết hợp backend metrics/traces để nối client impact với service failures.

### Bài tập 15 — Page alert quá nhiều

**Đề:** On-call nhận hàng trăm alerts CPU spike ngắn nhưng không có user impact.

**Đáp án:** Chuyển sang symptom/SLO-based alarms, dùng M out of N, composite alarms hoặc anomaly detection khi phù hợp. Tách warning khỏi page-level alert và viết runbook cho từng alarm.

### Bài tập 16 — Tập trung logs nhiều accounts

**Đề:** Một organization có 20 workload accounts và một monitoring account.

**Đáp án:** Thiết kế OAM sink/link hoặc log centralization/subscription theo use case. Giới hạn source accounts, Regions, log groups, IAM/KMS policies và retention. Không chia sẻ toàn bộ logs nếu monitoring team chỉ cần một phần telemetry.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Observability khác monitoring ở điểm nào?  
**Đáp án:** Monitoring theo dõi signals đã xác định và cảnh báo; observability giúp suy luận trạng thái nội tại từ telemetry.

**Câu 2.** Ba loại telemetry chính là gì?  
**Đáp án:** Metrics, logs và traces.

**Câu 3.** Metrics trả lời câu hỏi gì?  
**Đáp án:** Điều gì đang thay đổi, mức độ và xu hướng ra sao.

**Câu 4.** Logs trả lời câu hỏi gì?  
**Đáp án:** Sự kiện cụ thể nào đã xảy ra.

**Câu 5.** Distributed trace thể hiện điều gì?  
**Đáp án:** Đường đi của request qua services/dependencies và thời gian của từng operation.

**Câu 6.** CloudWatch namespace dùng để làm gì?  
**Đáp án:** Nhóm metrics theo AWS service hoặc custom metric domain.

**Câu 7.** Dimension là gì?  
**Đáp án:** Cặp tên/giá trị định danh resource hoặc phân loại metric time series.

**Câu 8.** Vì sao không dùng OrderId làm metric dimension?  
**Đáp án:** Cardinality lớn tạo nhiều time series và tăng chi phí/độ phức tạp.

**Câu 9.** Percentile p99 dùng để làm gì?  
**Đáp án:** Đánh giá tail latency; 99% datapoints/requests nằm dưới percentile đó theo cách metric được định nghĩa.

**Câu 10.** High-resolution custom metric dùng StorageResolution nào?  
**Đáp án:** 1.

**Câu 11.** High-resolution datapoints dưới 60 giây được giữ bao lâu trước khi aggregate?  
**Đáp án:** 3 giờ.

**Câu 12.** AWS EC2 default metrics có guest memory usage không?  
**Đáp án:** Không; thường cần CloudWatch Agent hoặc telemetry khác.

**Câu 13.** CloudWatch Agent thu thập những gì?  
**Đáp án:** Guest OS metrics, file logs và một số telemetry/trace sources theo cấu hình.

**Câu 14.** EMF là gì?  
**Đáp án:** Embedded Metric Format; JSON log events có cấu trúc để CloudWatch trích metrics.

**Câu 15.** Logs được tổ chức theo cấu trúc nào?  
**Đáp án:** Log groups, log streams và log events.

**Câu 16.** Nếu không đặt log retention, điều gì có thể xảy ra?  
**Đáp án:** Log events có thể được lưu vô thời hạn.

**Câu 17.** Logs Insights dùng để làm gì?  
**Đáp án:** Truy vấn, lọc, parse, aggregate và trực quan hóa log data.

**Câu 18.** Metric filter khác Logs Insights query thế nào?  
**Đáp án:** Metric filter biến events khớp pattern thành metric datapoints; Logs Insights query phân tích log records theo truy vấn.

**Câu 19.** Subscription filter dùng để làm gì?  
**Đáp án:** Chuyển log events tới destinations như Lambda, Kinesis Data Streams hoặc Firehose.

**Câu 20.** CloudWatch alarm có những trạng thái nào?  
**Đáp án:** OK, ALARM và INSUFFICIENT_DATA.

**Câu 21.** EvaluationPeriods và DatapointsToAlarm biểu thị gì?  
**Đáp án:** N là số periods được xét; M là số datapoints trong N phải vi phạm để alarm chuyển ALARM.

**Câu 22.** TreatMissingData có những lựa chọn nào?  
**Đáp án:** breaching, notBreaching, ignore và missing.

**Câu 23.** Composite alarm có tác dụng gì?  
**Đáp án:** Kết hợp trạng thái các alarms để giảm noise và chỉ cảnh báo khi điều kiện tổng hợp thỏa mãn.

**Câu 24.** Metric math dùng để làm gì?  
**Đáp án:** Kết hợp/biến đổi metric time series, ví dụ tính error rate.

**Câu 25.** Metrics Insights là gì?  
**Đáp án:** Ngôn ngữ truy vấn SQL-like để truy vấn và aggregate CloudWatch metrics.

**Câu 26.** Trace và span khác nhau thế nào?  
**Đáp án:** Trace là toàn bộ request path; span là một operation trong trace.

**Câu 27.** Trace context propagation có tác dụng gì?  
**Đáp án:** Truyền trace identity/parent context qua services để các spans liên kết cùng request.

**Câu 28.** ADOT là gì?  
**Đáp án:** AWS Distro for OpenTelemetry, bản phân phối AWS hỗ trợ OpenTelemetry SDK/Collector.

**Câu 29.** X-Ray SDK/daemon vào maintenance mode khi nào?  
**Đáp án:** Ngày 25-02-2026.

**Câu 30.** AWS công bố end of support X-Ray SDK/daemon vào ngày nào?  
**Đáp án:** Ngày 25-02-2027.

**Câu 31.** Application Signals giúp gì?  
**Đáp án:** Quan sát service operations, dependencies, health metrics và SLOs.

**Câu 32.** Application Map khác X-Ray Trace Map thế nào?  
**Đáp án:** Application Map tập trung topology/health services và dependencies; Trace Map tập trung topology được suy ra từ trace data.

**Câu 33.** RUM khác Synthetics thế nào?  
**Đáp án:** RUM thu thập dữ liệu từ real user sessions; Synthetics chạy canary tests chủ động theo lịch.

**Câu 34.** SLI và SLO khác nhau thế nào?  
**Đáp án:** SLI là phép đo; SLO là mục tiêu cho phép đo đó trong một evaluation window.

**Câu 35.** Vì sao alert nên gắn với runbook?  
**Đáp án:** Để người trực biết impact, nơi điều tra, hành động an toàn và cách xác nhận phục hồi.

## 25. Checklist production và tài liệu tham khảo

### 25.1. Checklist trước production

1. Xác định service owners, critical user journeys và business impact.
2. Định nghĩa SLI/SLO cho availability, latency và các workflows quan trọng.
3. Có golden signals: traffic, errors, latency và saturation.
4. Metrics có namespace, metric names, units và dimensions ổn định.
5. Không đưa high-cardinality identifiers vào metric dimensions.
6. CloudWatch Agent/ADOT Collector có IAM role least privilege và config được quản lý bằng code.
7. Log groups có naming, class, retention, encryption/KMS và access policies rõ ràng.
8. Application logs có structured schema, UTC timestamps, request ID và trace ID.
9. Secrets/PII được redact trước khi emit; data protection/masking được bật khi phù hợp.
10. Logs Insights queries có time range/log groups giới hạn và được lưu trong runbooks.
11. Metric filters/EMF/custom metrics không tạo duplicate signals.
12. Traces propagate context qua synchronous và asynchronous boundaries.
13. OpenTelemetry/ADOT được ưu tiên cho instrumentation mới; có migration plan cho X-Ray SDK/daemon legacy.
14. Application Signals/SLO/Application Map được bật cho services được hỗ trợ.
15. Alarms có period, M/N, missing-data treatment, severity, owner và action rõ ràng.
16. Composite alarms/anomaly detection được dùng để giảm noise khi phù hợp.
17. Dashboards thể hiện user impact, dependencies, deployments và observability health.
18. RUM/Synthetics được chọn theo câu hỏi về real users và proactive journey checks.
19. Cross-account sharing/OAM links có source scope, destination policy và KMS/IAM review.
20. CloudTrail/audit logs ghi nhận thay đổi observability controls.
21. Test agent failure, missing metrics, log delivery, trace propagation và alarm routing.
22. Ước lượng metrics/logs/traces/SLOs/RUM/Synthetics/query costs theo Region.
23. Có runbook, escalation, incident timeline và post-incident review.
24. Review retention, data residency và privacy requirements định kỳ.

### 25.2. Kết luận

CloudWatch cung cấp nền tảng để quan sát AWS workloads qua metrics, logs, traces, alarms, dashboards và application-level signals. Metrics giúp phát hiện xu hướng và mức độ ảnh hưởng; logs giải thích sự kiện cụ thể; traces nối các bước xử lý của một request qua nhiều services.

Một chiến lược observability hiệu quả bắt đầu từ user journeys và SLOs, chọn telemetry có cardinality/retention hợp lý, liên kết dữ liệu bằng trace/request IDs, cảnh báo theo impact và cung cấp runbook cho on-call. Cùng với IAM least privilege, redaction, KMS, multi-account governance và cost controls, CloudWatch giúp đội ngũ vận hành phát hiện, điều tra và khôi phục sự cố có hệ thống.

### 25.3. Tài liệu AWS chính thức

- [Amazon CloudWatch User Guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html) — tổng quan CloudWatch, metrics, alarms và dashboards.
- [CloudWatch metrics concepts](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html) — namespaces, dimensions, resolution và statistics.
- [CloudWatch GetMetricData and retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricData.html) — metric query và retention theo độ phân giải.
- [CloudWatch alarms evaluation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarm-evaluation.html) — Period, EvaluationPeriods, DatapointsToAlarm và high-resolution alarms.
- [Treating missing data](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarms-and-missing-data.html) — cách alarm xử lý datapoints bị thiếu.
- [Metric math alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Create-alarm-on-metric-math-expression.html) — tạo alarm trên metric math expression.
- [CloudWatch Agent](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html) — thu thập metrics, logs và traces.
- [CloudWatch Logs getting started](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_GettingStarted.html) — log groups, streams và agent.
- [CloudWatch Logs Insights query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html) — query language, commands và cost tips.
- [CloudWatch Logs log classes](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatch_Logs_Log_Classes.html) — tính năng theo log class.
- [Metric filter syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/FilterAndPatternSyntaxForMetricFilters.html) — chuyển logs thành metrics.
- [CloudWatch Application Map](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ServiceMap.html) — service/dependency topology và health.
- [CloudWatch Application Signals SLOs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html) — SLO configuration và attainment.
- [CloudWatch and X-Ray integration](https://docs.aws.amazon.com/xray/latest/devguide/xray-services-cloudwatch.html) — trace correlation, RUM và Application Signals.
- [Instrument applications with ADOT or X-Ray](https://docs.aws.amazon.com/xray/latest/devguide/xray-instrumenting-your-app.html) — instrumentation options.
- [X-Ray SDK and Daemon support timeline](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html) — maintenance và end-of-support timeline.
- [CloudWatch X-Ray trace map](https://docs.aws.amazon.com/xray/latest/devguide/xray-console-servicemap.html) — phân tích request paths và dependencies.
