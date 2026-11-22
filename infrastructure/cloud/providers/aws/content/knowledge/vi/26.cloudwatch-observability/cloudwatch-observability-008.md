# Dashboard theo dịch vụ và chỉ số nghiệp vụ

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của Amazon CloudWatch dashboards trong giám sát vận hành AWS và ứng dụng.
- Phân biệt dashboard kỹ thuật theo service với dashboard nghiệp vụ theo customer journey, transaction và KPI.
- Chọn golden signals: traffic, latency, errors và saturation; bổ sung availability, queue lag, dependency health và cost signals.
- Thiết kế metric namespace, dimensions, units, statistic, period và naming conventions để dashboard có thể mở rộng.
- Dùng CloudWatch metric widgets, alarm widgets, text widgets, metric math, SEARCH, Metrics Insights và dashboard variables.
- Xây dựng dashboard tổng quan, dashboard theo service, dashboard theo dependency và dashboard theo chỉ số nghiệp vụ.
- Thiết kế KPI từ business events, tránh cộng gộp sai do retry, duplicate events hoặc metric cardinality.
- Kết hợp CloudWatch metrics, logs, alarms, Application Signals và traces để điều tra sự cố.
- Theo dõi nhiều AWS accounts và Regions bằng cross-account observability và cross-account cross-Region dashboards.
- Quản lý dashboard bằng CloudFormation/IaC, kiểm soát quyền truy cập, chi phí và vòng đời.
- Xây dựng dashboard phục vụ SLO/error budget, release monitoring, incident response và capacity planning.
- Kiểm thử dashboard, chẩn đoán metric missing/stale, statistic sai, dimensions không khớp và biểu đồ gây hiểu nhầm.

**Bối cảnh module:** Bài thuộc chương **Quan sát với CloudWatch** trong CLOUD_PROVIDERS_AWS. Module bao phủ AWS Region/AZ, IAM, VPC, compute, storage, database, integration và serverless. Dashboard cần phản ánh sức khỏe của các thành phần này, đồng thời cho biết chúng tác động thế nào đến hoạt động kinh doanh.

> **Phạm vi:** Ví dụ dùng Amazon CloudWatch Metrics, Dashboards, Alarms, Logs Insights, Metrics Insights và Application Signals. Tên namespace, metric, service, Region và KPI là minh họa; metric availability/statistic có thể khác nhau theo AWS service và cấu hình telemetry. Kiểm tra tài liệu của service và account/Region trước khi triển khai.

## 1. Vì sao dashboard cần hai góc nhìn: service và business?

Một dashboard chỉ có CPU, memory và request count chưa đủ để biết khách hàng có đặt hàng được hay không. Ngược lại, dashboard chỉ có doanh thu/ngày không giúp on-call xác định API, database hay queue nào đang làm chậm giao dịch.

Một hệ thống quan sát tốt có hai lớp:

- **Service dashboard:** cho biết từng thành phần kỹ thuật có khỏe không, request đi qua đâu, lỗi và độ trễ phát sinh ở dependency nào.
- **Business dashboard:** cho biết customer journey và kết quả kinh doanh có diễn ra đúng không, ví dụ checkout success, payment authorization, order completion và revenue.

~~~mermaid
flowchart TD
    User[Customer journey] --> API[Orders API]
    API --> DB[(Orders database)]
    API --> Q[(SQS order events)]
    Q --> Worker[Order worker]
    Worker --> Pay[Payment provider]
    Worker --> S3[(S3 invoices)]
    API --> Tech[Service metrics / traces / logs]
    DB --> Tech
    Q --> Tech
    Worker --> Tech
    Pay --> Tech
    Tech --> ServiceDash[Service dashboard]
    User --> Events[Business events]
    Events --> BusinessDash[Business KPI dashboard]
    ServiceDash --> Ops[On-call / SRE]
    BusinessDash --> Product[Product / Operations]
~~~

Ví dụ API có latency bình thường nhưng tỷ lệ payment declined tăng mạnh. Dashboard kỹ thuật có thể vẫn xanh vì HTTP requests thành công; business dashboard phát hiện conversion giảm. Cũng có trường hợp payment success giảm do SQS consumer backlog tăng; hai dashboard bổ sung cho nhau để tìm nguyên nhân.

## 2. Bắt đầu từ câu hỏi vận hành, không bắt đầu từ danh sách metric

Trước khi thêm widget, xác định ai sẽ dùng dashboard và quyết định họ cần đưa ra.

| Người dùng | Câu hỏi | Dashboard nên có |
| --- | --- | --- |
| On-call engineer | Dịch vụ đang lỗi ở đâu? | Traffic, latency, errors, saturation, dependencies, alarms |
| Service owner | Release mới có làm giảm reliability không? | SLO, error budget, deploy markers, p95/p99, error rate |
| Product manager | Khách có hoàn tất checkout không? | Funnel, conversion, orders, payment success, revenue |
| Operations | Queue và batch có theo kịp không? | Queue age/depth, processing rate, retries, DLQ |
| Platform team | Hạ tầng có đủ capacity không? | CPU, memory, throttles, connections, quotas |
| Finance/FinOps | Workload nào đang tăng chi phí? | Usage, request volume, storage, cost signals |

Một dashboard nên trả lời một nhóm câu hỏi liên quan. Nếu nhồi tất cả metric của mọi service vào một màn hình, người xem khó phân biệt tín hiệu quan trọng với noise.

## 3. Golden signals cho từng service

Bốn golden signals thường dùng để đánh giá service:

1. **Traffic:** lượng request hoặc operation đi qua hệ thống.
2. **Latency:** thời gian xử lý; quan sát p50, p90, p95 hoặc p99 tùy use case.
3. **Errors:** tỷ lệ và số lượng request thất bại, bao gồm HTTP 5xx, exceptions, throttling và business failures.
4. **Saturation:** mức sử dụng tài nguyên hoặc giới hạn khiến service không thể nhận thêm tải.

Nên bổ sung availability/success rate, dependency latency/error rate, queue age/backlog, retry/throttle rate, resource capacity, connection pool và SLO/error budget.

### Metric mapping theo service AWS

| Thành phần | Traffic | Latency | Errors | Saturation / backlog |
| --- | --- | --- | --- | --- |
| API Gateway | Count | Latency, IntegrationLatency | 4XXError, 5XXError | Throttles, quota |
| Application Load Balancer | RequestCount | TargetResponseTime | HTTPCode_Target_5XX_Count, HTTPCode_ELB_5XX_Count | HealthyHostCount, TargetConnectionErrorCount |
| EC2 | NetworkIn/Out, disk I/O | EBS latency nếu có | StatusCheckFailed | CPUUtilization, CPU credit, memory từ agent |
| ECS | RunningTaskCount, task restarts | App request latency | Deployment/task failures | CPUUtilization, MemoryUtilization, desired vs running |
| EKS | Pod/request metrics qua Container Insights/Prometheus | API/service latency | Restarts, failed requests | CPU/memory, pending pods, node pressure |
| Lambda | Invocations | Duration | Errors, Throttles | ConcurrentExecutions, AsyncEventAge, IteratorAge theo event source |
| SQS | NumberOfMessagesSent/Received/Deleted | — | DLQ messages, oldest message age | ApproximateNumberOfMessagesVisible/NotVisible |
| DynamoDB | ConsumedRead/WriteCapacityUnits | SuccessfulRequestLatency | ThrottledRequests, SystemErrors | Consumed vs provisioned capacity |
| RDS/Aurora | DatabaseConnections, transactions nếu có | Read/WriteLatency | Deadlocks, failed connections, replica lag | CPUUtilization, FreeableMemory, FreeStorageSpace |
| S3 | AllRequests, GetRequests, PutRequests | FirstByteLatency, TotalRequestLatency khi bật request metrics | 4xx/5xx errors | ReplicationLatency nếu bật replication metrics |
| SNS | NumberOfMessagesPublished, NumberOfNotificationsDelivered | Delivery latency theo protocol | NumberOfNotificationsFailed | Subscription backlog ở downstream queues |

Không phải mọi metric đều có sẵn mặc định. Memory trên EC2 thường cần CloudWatch Agent; S3 request metrics phải được bật; ECS/EKS container metrics phụ thuộc Container Insights/Prometheus setup. Luôn kiểm tra namespace, dimensions và publishing interval thực tế.

## 4. Service dashboard và business dashboard khác nhau thế nào?

| Tiêu chí | Service dashboard | Business dashboard |
| --- | --- | --- |
| Đơn vị quan sát | Service/resource/API/dependency | Journey, transaction, order, customer action |
| Metric examples | p95 latency, 5xx, CPU, queue age | Checkout conversion, paid orders, revenue |
| Dimensions | Service, Region, AZ, environment, route | Product category, channel, market, payment method |
| Người dùng | SRE, developer, on-call | Product, operations, business owner |
| Tần suất | 1 phút hoặc gần realtime tùy metric | 1–5 phút, hourly hoặc daily |
| Hành động | Scale, rollback, failover, mitigate | Điều chỉnh funnel, payment routing, promotion, operations |

Không đưa user ID, order ID hoặc email làm metric dimensions. Định danh giao dịch chi tiết nên nằm ở logs/traces hoặc event store.

## 5. Thiết kế KPI nghiệp vụ từ business events

KPI cần được định nghĩa bằng event và công thức rõ ràng trước khi xuất metric.

~~~mermaid
flowchart LR
    Visit[Checkout started] --> Validate[Address validated]
    Validate --> Pay[Payment authorized]
    Pay --> Order[Order confirmed]
    Order --> Ship[Shipment created]
~~~

| KPI | Định nghĩa | Cách đo |
| --- | --- | --- |
| Checkout starts | Số checkout bắt đầu | Counter CheckoutStarted |
| Checkout completion | Checkout thành công / checkout bắt đầu | OrdersConfirmed / CheckoutStarted |
| Payment authorization success | Payment authorized / authorization attempts | PaymentsAuthorized / PaymentAttempts |
| Order completion time | Từ checkout start đến order confirmed | Histogram/timer hoặc event timestamps |
| Revenue | Tổng giá trị order đã paid | Sum theo currency, sau deduplication |
| Refund rate | Refund amount / paid amount | Sum theo cùng currency và window |
| Fulfillment lag | Từ order confirmed đến shipment created | Histogram/percentile |

### Định nghĩa denominator

Tỷ lệ không có ý nghĩa nếu không định nghĩa mẫu số. Payment success rate có thể tính trên attempts hoặc unique orders; checkout conversion có thể tính trên sessions, users hoặc checkout attempts; refund rate có thể theo số orders hoặc giá trị tiền.

Ghi rõ window, timezone, currency, inclusion/exclusion rules, cancellation/refund handling và cách xử lý retries. Không so sánh hai KPI nếu denominator khác nhau.

### Event schema

Một business event nên có event ID, event type, occurred_at, entity ID, schema version và business dimensions đã được chuẩn hóa.

~~~json
{
  "event_id": "evt-01JABC",
  "event_type": "order.confirmed",
  "occurred_at": "2026-11-20T03:15:00Z",
  "schema_version": 2,
  "market": "VN",
  "channel": "web",
  "currency": "VND",
  "amount_minor": 12500000
}
~~~

Không phát metric trực tiếp từ mỗi lần delivery của SQS nếu event có thể được giao lặp. Hãy deduplicate bằng event ID hoặc cập nhật metric từ nguồn dữ liệu có semantics idempotent.

## 6. Metric namespace, name và dimensions

CloudWatch custom metrics được nhóm theo namespace. Mỗi metric có tên và tập dimensions. Một metric identity gồm namespace, metric name và toàn bộ dimension set.

~~~text
Namespace: MyCompany/Commerce
Metric: OrdersConfirmed
Dimensions:
  Environment=prod
  Region=ap-southeast-1
  Channel=web
Unit: Count
~~~

| Thành phần | Quy tắc |
| --- | --- |
| Namespace | Tên tổ chức/domain, ví dụ MyCompany/Commerce |
| Metric name | Mô tả event/measurement, ví dụ OrdersConfirmed |
| Dimensions | Giá trị bounded như Environment, Channel, Market |
| Unit | Nhất quán: Count, Milliseconds, Bytes, Percent, None |
| Timestamp | Thời điểm event/measurement xảy ra |
| Storage resolution | Standard hoặc high-resolution theo nhu cầu |
| Period | Khoảng tổng hợp phù hợp publishing interval |

CloudWatch không tự coi metric có dimensions khác nhau là cùng một time series. OrdersConfirmed với Environment=prod khác metric cùng tên với Environment=dev. Mỗi dimension combination tạo một metric variant riêng và ảnh hưởng metric count/cost.

Không tạo dimension OrderId, UserId, RequestId, raw URL hoặc exception message. Những giá trị này tạo cardinality lớn, làm tăng chi phí và khó query.

## 7. Đo metric nghiệp vụ bằng Embedded Metric Format (EMF)

Embedded Metric Format cho phép ứng dụng/worker ghi structured JSON log chứa metric directives. CloudWatch Logs có thể trích xuất metric từ log event thành custom metrics.

Ví dụ EMF log:

~~~json
{
  "_aws": {
    "Timestamp": 1795144500000,
    "CloudWatchMetrics": [
      {
        "Namespace": "MyCompany/Commerce",
        "Dimensions": [["Environment", "Channel", "Currency"]],
        "Metrics": [
          {"Name": "OrdersConfirmed", "Unit": "Count"},
          {"Name": "RevenueMinor", "Unit": "None"}
        ]
      }
    ]
  },
  "Environment": "prod",
  "Channel": "web",
  "Currency": "VND",
  "OrdersConfirmed": 1,
  "RevenueMinor": 12500000
}
~~~

Ví dụ biểu diễn một order confirmed. Với revenue, cần bảo đảm:
- Chỉ emit một lần cho business transition đã được xác nhận;
- Deduplicate event trước khi cộng;
- Không cộng VND, USD và currency khác vào cùng total;
- Ghi rõ đơn vị amount_minor và currency;
- Chọn dimension phù hợp để không tạo quá nhiều time series.

EMF hữu ích cho metrics từ Lambda, ECS workers và log-based applications. Nếu dùng CloudWatch Agent/Fluent Bit, xác minh log pipeline chuyển nguyên JSON event và EMF parser được bật.

## 8. Statistic và period: hiểu đúng số đang hiển thị

| Statistic | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| Sum | Tổng giá trị trong period | Request count, events, bytes |
| Average | Giá trị trung bình | CPU utilization, average duration |
| Minimum/Maximum | Giá trị thấp/cao nhất | Capacity floor/peak |
| SampleCount | Số samples được publish | Kiểm tra volume measurements |
| p50/p90/p95/p99 | Percentile | Latency distribution khi metric hỗ trợ |

Một lỗi phổ biến là dùng Average cho counter rồi diễn giải thành tổng số orders. Counter thường cần Sum. Latency thường cần p95/p99 thay vì chỉ Average vì tail latency ảnh hưởng người dùng.

### Period và publishing interval

- Period phải phù hợp tần suất metric được publish.
- Standard-resolution metrics thường có granularity tối thiểu 1 phút.
- High-resolution custom metrics có thể được publish với resolution 1, 5, 10 hoặc 30 giây; việc truy vấn/hiển thị còn phụ thuộc widget/API và giới hạn tương ứng.
- Trong dashboard body, thuộc tính period của metric widget phải là bội số của 60 giây và tối thiểu 60 giây. Không suy ra rằng metric high-resolution sẽ luôn được dashboard graph hiển thị ở chu kỳ dưới một phút.
- Một số AWS service metrics chỉ publish theo chu kỳ 1 phút hoặc 5 phút.
- Period quá ngắn tạo gaps hoặc datapoints thiếu; period quá dài che khuất spikes và recovery time.

Khi so sánh nhiều metrics, bảo đảm statistic và period có ý nghĩa tương ứng. Không cộng Average của các instances để suy ra average toàn fleet nếu chưa cân trọng số theo request/sample count.

Percentiles cần dữ liệu distribution/raw samples phù hợp. Statistic sets thông thường có thể không đủ thông tin để tính percentile chính xác, ngoại trừ một số trường hợp đặc biệt như SampleCount=1 hoặc Min=Max.

## 9. Metric math cho KPI và service health

Metric math kết hợp nhiều time series để tạo một biểu đồ hoặc metric expression.

\[
ErrorRate(\%) = 100 \times \frac{5xx}{RequestCount}
\]

\[
PaymentSuccess(\%) = 100 \times \frac{Authorized}{Attempted}
\]

\[
RevenuePerOrder = \frac{RevenueSum}{OrdersConfirmedSum}
\]

Giả sử widget có m1 là HTTP 5xx Sum và m2 là RequestCount Sum. Expression:

~~~text
IF(m2 > 0, 100 * m1 / m2, 0)
~~~

Đặt label 5xx rate (%), format phần trăm và hiển thị cùng request volume. Khi denominator bằng 0, biểu đồ có thể trả 0 để tránh lỗi toán học, nhưng người xem phải phân biệt “không có traffic” với “service healthy”. Hiển thị traffic riêng và cấu hình no-data behavior cho alarms.

| Mục tiêu | Expression/ý tưởng |
| --- | --- |
| Success rate | 100 * success / attempts |
| Error rate | 100 * errors / requests |
| Request per second | requests_sum / PERIOD(requests) |
| Fleet total | SUM(METRICS()) với metric set phù hợp |
| Queue age | MAX(queue_age) |
| Capacity ratio | 100 * consumed / provisioned |
| Revenue per order | revenue_sum / orders_sum |

Metric math phải dùng metrics cùng đơn vị/aggregation semantics. Không cộng percent của từng instance để suy ra percent toàn fleet; hãy tổng hợp numerator và denominator trước rồi chia.

## 10. SEARCH và Metrics Insights cho dashboard động

Khi số service/resource tăng, tạo một metric widget cho mỗi resource sẽ khó quản lý.

### SEARCH expression

CloudWatch SEARCH tìm metrics theo namespace, metric name và dimensions. Ví dụ:

~~~text
SEARCH('{AWS/ApiGateway,ApiName} MetricName="Count"', 'Sum')
~~~

Có thể dùng search expression để tìm nhiều API names trong cùng namespace/dimension pattern. Search expression trả về nhiều time series; dashboard có thể hiển thị series mới khi metrics phù hợp được publish.

Giới hạn cần nhớ:
- SEARCH chỉ tìm metrics đã báo cáo data trong hai tuần gần đây;
- Query phải khớp namespace/dimension schema;
- Một graph có giới hạn số search expressions và time series;
- Query quá rộng khiến dashboard chậm và khó đọc;
- Không phải mọi expression đều dùng được trong mọi alarm context.

### Metrics Insights

Metrics Insights dùng SQL-like query để phân tích CloudWatch metrics theo dimensions, filter, grouping và aggregation.

Ví dụ tìm top 10 EC2 instances theo CPU:

~~~sql
SELECT AVG(CPUUtilization)
FROM SCHEMA("AWS/EC2", InstanceId)
GROUP BY InstanceId
ORDER BY AVG() DESC
LIMIT 10
~~~

Schema phải khớp dimensions của metric. Nếu metric không có dimension InstanceId như query yêu cầu, kết quả sẽ rỗng.

Metrics Insights phù hợp cho top-N resources theo CPU/latency/errors, so sánh workloads theo environment, tìm queue age/throttles cao và phân tích custom metrics theo channel/market.

Một query Metrics Insights có thể xử lý tối đa 10.000 metrics và trả tối đa 500 time series. Query visualization tối đa hai tuần dữ liệu; Metrics Insights không hỗ trợ high-resolution data dưới một phút. Dùng ORDER BY khi cần chọn top-N có chủ đích.

## 11. Dashboard widgets: chọn loại hiển thị đúng mục tiêu

CloudWatch dashboard body hỗ trợ các widget types sau:

| Widget type | Cách dùng |
| --- | --- |
| metric | Graph metrics, metric math, SEARCH và Metrics Insights |
| alarm | Một alarm kèm graph hoặc trạng thái nhiều alarms |
| log | CloudWatch Logs Insights query |
| text | Markdown, owner, hướng dẫn và runbook links |
| explorer | Metrics Explorer theo tags/resource properties |
| chart | Visualization/chart theo schema được hỗ trợ |

Metric graph có thể hiển thị line, stacked area, number, gauge, bar hoặc pie.

Không dùng pie chart cho hàng chục categories; không dùng gauge cho metric không có ngưỡng có ý nghĩa; không hiển thị quá nhiều line series cùng lúc.

### Layout gợi ý

1. Hàng đầu: KPI và alarm status;
2. Hàng hai: traffic, p95/p99 latency, error rate;
3. Hàng ba: saturation, dependency latency, queue backlog;
4. Hàng cuối: logs/traces links, deployment markers và runbooks.

## 12. Dashboard variables: một dashboard cho nhiều environments

Dashboard variables cho phép người xem thay dimension value mà không phải tạo bản sao dashboard cho dev/stage/prod hoặc nhiều service.

Có hai loại chính:

- **Property variable:** thay đổi giá trị của một JSON property trong dashboard, ví dụ region hoặc một metric dimension.
- **Pattern variable:** dùng regular expression để thay một phần hoặc toàn bộ JSON property.

Ví dụ biến có thể dùng cho Environment, FunctionName, InstanceId, Cluster hoặc Region tùy metric schema. Variable có thể lấy values từ metric property search hoặc danh sách được cấu hình.

Nguyên tắc:
- Đặt default value an toàn và hiển thị rõ scope đang xem;
- Không dùng một variable chung cho widgets có dimension schemas khác nhau;
- Kiểm tra mọi widget khi đổi variable;
- Giới hạn values và tránh query quá rộng;
- Với incident dashboard, không để filter vô tình ẩn service quan trọng.

Dashboard variable giúp tái sử dụng layout; nó không làm giảm chi phí custom metrics hoặc telemetry ingestion.

## 13. Dashboard body bằng JSON

CloudWatch dashboard được định nghĩa bằng JSON body. Có thể tạo qua console, AWS CLI, SDK hoặc CloudFormation.

Ví dụ dashboard có metric widgets và alarm widget:

~~~json
{
  "widgets": [
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Orders API request count and p95 latency",
        "view": "timeSeries",
        "region": "ap-southeast-1",
        "period": 60,
        "metrics": [
          ["AWS/ApiGateway", "Count", "ApiName", "orders-api", {"stat": "Sum", "id": "requests", "yAxis": "left"}],
          [".", "Latency", ".", ".", {"stat": "p95", "id": "latency", "yAxis": "right"}]
        ],
        "yAxis": {
          "left": {"label": "Requests"},
          "right": {"label": "Milliseconds"}
        },
        "annotations": {
          "horizontal": [
            {"label": "Latency objective", "value": 500, "yAxis": "right"}
          ]
        }
      }
    },
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Orders confirmed by channel",
        "view": "timeSeries",
        "region": "ap-southeast-1",
        "period": 300,
        "metrics": [
          ["MyCompany/Commerce", "OrdersConfirmed", "Environment", "prod", "Channel", "web", {"stat": "Sum", "id": "web"}],
          [".", ".", ".", ".", ".", "mobile", {"stat": "Sum", "id": "mobile"}]
        ]
      }
    },
    {
      "type": "alarm",
      "width": 12,
      "height": 4,
      "properties": {
        "alarms": [
          "arn:aws:cloudwatch:ap-southeast-1:111122223333:alarm:OrdersApiHighErrorRate"
        ]
      }
    }
  ]
}
~~~

Đây là cấu trúc minh họa; metric dimensions/statistics phải tồn tại trong account. Percentile latency cần metric data hỗ trợ percentile. Metric widget cần Region tường minh; với cross-account metrics có thể đặt accountId ở widget hoặc từng metric.

### Tạo dashboard bằng CLI

~~~bash
aws cloudwatch put-dashboard \
  --dashboard-name Orders-Operations \
  --dashboard-body file://dashboard.json
~~~

Dashboard CloudWatch là global trong account, không gắn một Region; từng metric widget chỉ định Region của metrics cần hiển thị. Một dashboard có thể kết hợp widgets từ nhiều Regions.

API PutDashboard thay toàn bộ body dashboard cùng tên. Nếu nhiều team cùng sửa một dashboard, một lần deploy có thể ghi đè thay đổi của team khác. Hãy quản lý ownership, code review và deployment serialization.

PutDashboard trả validation messages: warnings có thể cho biết dashboard đã được lưu nhưng một số elements không render; errors khiến operation thất bại. Pipeline phải kiểm tra cả response, không chỉ HTTP 200.

## 14. Quản lý dashboard bằng CloudFormation/IaC

Có thể quản lý dashboard như resource:

~~~yaml
Resources:
  OrdersOperationsDashboard:
    Type: AWS::CloudWatch::Dashboard
    Properties:
      DashboardName: Orders-Operations
      DashboardBody: |
        {
          "widgets": [
            {
              "type": "metric",
              "width": 12,
              "height": 6,
              "properties": {
                "title": "Orders API errors",
                "region": "ap-southeast-1",
                "period": 60,
                "metrics": [
                  ["AWS/ApiGateway", "5XXError", "ApiName", "orders-api", {"stat": "Sum"}]
                ]
              }
            }
          ]
        }
~~~

Ưu điểm:
- Dashboard được version control và review qua pull request;
- Thay đổi dashboard đi cùng release/service config;
- Có thể triển khai cùng stack/CI pipeline;
- Dễ tạo dashboard chuẩn hóa theo service/team;
- Có thể phân phối qua pipeline hoặc StackSets.

Validate JSON sau khi render template. Nếu dùng Fn::Sub, chú ý các placeholder pseudo parameter trong dashboard body vì chúng có thể bị CloudFormation diễn giải thành substitution.

## 15. Cross-account và cross-Region dashboards: phân biệt hai cơ chế

CloudWatch có hai cơ chế liên quan nhưng không đồng nhất.

**Cross-account observability qua OAM:**
- Tập trung metrics, logs, traces và Application Signals từ source accounts vào monitoring account;
- Hỗ trợ tìm kiếm/phân tích telemetry qua accounts trong cùng Region;
- Không tự biến OAM link thành khả năng cross-Region;
- Phù hợp với central observability trong một Region.

**Cross-account cross-Region dashboards/console:**
- Dashboard có thể hiển thị metrics từ nhiều accounts và Regions bằng accountId/region selectors;
- Có thể dùng cross-account cross-Region console integration;
- Tính năng console này không cung cấp cross-account cross-Region Logs visibility và không hỗ trợ tạo alarms trong monitoring account theo dõi metrics ở Region khác;
- Dùng khi cần một dashboard tổng quan trải qua nhiều Regions/accounts.

~~~mermaid
flowchart TD
    subgraph SameRegion[OAM cross-account trong một Region]
      S1[Source account A] --> OAM[OAM sink / links]
      S2[Source account B] --> OAM
      OAM --> M[Monitoring account]
      M --> T[Metrics / logs / traces / SLOs]
    end
    subgraph MultiRegion[Dashboard cross-account / cross-Region]
      R1[Account A / Region 1] --> D[Central dashboard]
      R2[Account B / Region 2] --> D
    end
~~~

Khi thiết kế dashboard trung tâm:
- Xác định monitoring account và source accounts;
- Chọn đúng cơ chế chia sẻ cho cùng Region hay nhiều Regions;
- Cấp IAM permissions cho viewers;
- Metric widgets phải dùng account/Region context đúng;
- Hiển thị account/Region trong title hoặc labels;
- Không chia sẻ logs/traces nhạy cảm ngoài phạm vi.

## 16. Alarms, anomaly detection và SLO trên dashboard

Dashboard nên giúp người xem thấy cả xu hướng lẫn trạng thái actionable.

### Alarm widget

Hiển thị trạng thái alarms quan trọng: API 5xx rate, p95 latency, queue oldest message age, Lambda errors/throttles, database connections/CPU/free storage và business checkout/payment success rate.

### Anomaly detection

CloudWatch anomaly detection tạo expected band dựa trên historical metric patterns. Có thể hiển thị band trên metric graph và tạo alarm dựa trên anomaly detection band.

Không áp dụng anomaly detection mù quáng cho metric có seasonality thay đổi mạnh, traffic thấp hoặc event hiếm. Kiểm tra training window, excluded time ranges và threshold behavior.

### SLO

SLO nên định nghĩa SLI, objective (ví dụ 99.9% successful requests trong rolling 30 days), measurement window, good/bad events, error budget và burn-rate alerting.

CloudWatch Application Signals hỗ trợ service-level objectives và service operations nếu được onboarding/configure. Dashboard có thể hiển thị metric/alarms liên quan và đặt link tới Application Signals service map/SLO view.

## 17. Dashboard theo service: ví dụ Orders API

Một service dashboard nên được chia thành vùng:

| Khu vực | Metrics |
| --- | --- |
| Health | Availability, 5xx rate, alarms, deployment status |
| Traffic | RequestCount, requests/sec, orders started |
| Latency | p50/p95/p99, integration latency |
| Saturation | CPU/memory, DB pool, thread pool |
| Dependencies | RDS latency, SQS send errors, payment API |
| Queue | Visible/NotVisible, oldest age, DLQ |
| Business | Checkout started, orders confirmed, payment success |

Dashboard cần dùng cùng time range khi so sánh service và dependencies. Thêm annotations/markers cho deployment, config change và incident windows để thấy sự tương quan thời gian.

Một p95 toàn service có thể che giấu một Region hoặc endpoint cụ thể bị lỗi. Nên có total traffic, breakdown theo Region, route template/operation, top dependencies và alarm state từng critical component.

Không group theo raw URL có ID; dùng route template như /orders/{id}.

## 18. Dashboard theo business: ví dụ checkout funnel

Business dashboard nên bắt đầu từ business events đã deduplicated.

| KPI | Metric | Statistic | Dimensions |
| --- | --- | --- | --- |
| Checkout started | CheckoutStarted | Sum | Environment, Channel, Market |
| Orders confirmed | OrdersConfirmed | Sum | Environment, Channel, Market |
| Payment attempts | PaymentAttempts | Sum | Environment, PaymentMethod |
| Payment authorized | PaymentsAuthorized | Sum | Environment, PaymentMethod |
| Refund amount | RefundAmountMinor | Sum | Environment, Currency |
| Fulfillment delay | FulfillmentLag | p95 | Environment, Market |

Các KPI tỷ lệ có thể tính bằng metric math. Revenue nên giữ theo currency hoặc normalize sang base currency với exchange-rate timestamp/source rõ ràng.

Dashboard nghiệp vụ nên hiển thị current period vs previous comparable period, hourly/daily trends, conversion funnel, payment success by method, revenue by currency/market, refund/cancellation rates, fulfillment backlog/lag và data freshness/last event timestamp.

Một metric có giá trị bằng 0 khác với metric không có data. Dashboard nên thể hiện rõ no data/stale data để product/operations không diễn giải thiếu event là không có hoạt động.

## 19. Kết hợp dashboards với Logs Insights và traces

Khi metric báo lỗi tăng, dashboard cần cung cấp đường dẫn tới logs/traces.

Workflow:
1. Chọn time range có spike;
2. Nhìn metric theo Region/service/route;
3. Mở alarm và xem threshold/reason;
4. Mở Logs Insights query cùng time window;
5. Lọc theo trace ID/request ID đã được kiểm soát;
6. Mở trace/service map để xem dependency latency;
7. Đối chiếu deployment marker và stack events.

Ví dụ Logs Insights query tìm lỗi ứng dụng:

~~~sql
fields @timestamp, @message, traceId, service, level
| filter level = "ERROR"
| sort @timestamp desc
| limit 100
~~~

Field names phụ thuộc structured log schema và ingestion pipeline. Nếu log là JSON, CloudWatch Logs Insights có thể tự discover fields; nếu không, dùng parse phù hợp format.

Dashboard log widget có thể chứa query đã lưu hoặc query trực tiếp. Giữ query scope/time range hợp lý để tránh query quá rộng trong incident.

## 20. Dashboard variables và cross-service drill-down

Dùng dashboard variables để đổi environment/service/Region và làm drill-down nhất quán.

Ví dụ:
- Dashboard overview có variable Environment;
- Link chuyển sang Orders-API-Detail;
- Dashboard chi tiết giữ cùng Environment, Region và time range;
- Alarm widget hiển thị alarms của service đang chọn.

Links nên giữ context và chỉ trỏ đến dashboard/log group được phép xem. Không nhúng credentials, signed URLs hoặc raw customer identifiers vào dashboard links.

## 21. Dashboard cho serverless và event-driven workloads

Serverless workload cần nhìn cả function execution và event delivery.

| Thành phần | Metrics quan trọng |
| --- | --- |
| Lambda | Invocations, Duration p95/p99, Errors, Throttles, ConcurrentExecutions, IteratorAge nếu stream |
| SQS | Visible/NotVisible, ApproximateAgeOfOldestMessage, Sent/Received/Deleted, DLQ |
| SNS | Published, Delivered, Failed notifications |
| EventBridge | Invocations, FailedInvocations, ThrottledRules, DLQ |
| Step Functions | ExecutionsStarted/Succeeded/Failed/TimedOut, ExecutionTime |
| API Gateway | Count, Latency, IntegrationLatency, 4XX/5XX, Throttles |

Đối với SQS → Lambda event source mapping, queue age và Lambda errors cần xem cùng nhau. Lambda Errors không cho biết toàn bộ messages bị retry; kiểm tra queue age, receive count, DLQ và event source mapping behavior.

Với Step Functions, phân biệt Standard và Express workflow metrics/logging semantics. Dashboard nên thể hiện failed/timed-out executions và execution duration, không chỉ executions started.

## 22. Dashboard cho database và storage

| Service | Metric cần theo dõi | Business impact |
| --- | --- | --- |
| RDS/Aurora | CPU, FreeableMemory, FreeStorageSpace, DatabaseConnections, Read/WriteLatency, replica lag | Checkout/API chậm, lỗi transaction |
| DynamoDB | ConsumedRead/WriteCapacity, ThrottledRequests, SuccessfulRequestLatency | Request retries, order lookup chậm |
| S3 | 4xx/5xx, request metrics, replication metrics, storage bytes | Upload/download fail, invoice chưa sẵn sàng |
| EBS | VolumeQueueLength, BurstBalance/IOPS, throughput | Database/application disk latency |
| EFS | PercentIOLimit, BurstCreditBalance, throughput | Shared file access chậm |

Metrics availability và names có thể thay đổi theo engine, storage class, feature và monitoring configuration. RDS Enhanced Monitoring/Database Insights cung cấp dữ liệu sâu hơn metrics cơ bản; S3 request metrics phải cấu hình filter.

## 23. Dashboard cho capacity, release và reliability

### Capacity dashboard

- ECS desired/running task count;
- EKS node/pod capacity và pending pods;
- Lambda concurrency/throttles;
- RDS connections/CPU/free storage;
- DynamoDB consumed/provisioned capacity;
- SQS oldest message age;
- EC2 CPU credits, network throughput, EBS queue.

### Release dashboard

- Deployment events/markers;
- Error rate trước/sau deploy;
- p95/p99 latency;
- Task/pod restarts;
- Rollback count;
- Business KPI delta;
- Alarm state và smoke test status.

### Reliability dashboard

- SLO attainment;
- Error budget remaining;
- Burn rate;
- Availability by Region;
- Dependency health;
- Incident count/MTTR;
- Data freshness.

Dashboard cần time range phù hợp. SLO 30 ngày không thể được đánh giá từ chart 1 giờ; release regression lại cần time window vài phút trước/sau deployment.

## 24. Thiết kế dashboard cho multi-Region resilience

Với ứng dụng multi-Region, dashboard phải phân biệt global experience và từng Region.

| Góc nhìn | Metrics |
| --- | --- |
| Global | Request count, success rate, latency theo traffic-weighted aggregation |
| Region A | API 5xx, p95, database lag, queue age |
| Region B | API 5xx, p95, database lag, queue age |
| Failover | Route/health check state, traffic shift, replication lag |
| Recovery | Backlog drain rate, data replication catch-up, error budget |

Không lấy average latency của các Regions mà không cân traffic. Một Region có ít requests nhưng latency rất cao có thể bị che khuất bởi Region lớn. Hiển thị từng Region và weighted/global aggregate riêng.

## 25. Dashboard sharing, IAM và dữ liệu nhạy cảm

CloudWatch dashboard có thể chia sẻ qua AWS Console hoặc public sharing tùy tính năng/quyền. Public dashboards có thể làm lộ thông tin vận hành, tên resource, traffic patterns và business KPIs.

Kiểm soát:
- cloudwatch:GetDashboard, cloudwatch:ListDashboards, cloudwatch:PutDashboard, cloudwatch:DeleteDashboards;
- Metrics/logs/traces permissions cần cho data được hiển thị;
- OAM sharing permissions cho cross-account observability;
- KMS/Logs access policy khi logs được query;
- Dashboard sharing policy và approved viewers;
- Không đưa customer PII, secrets hoặc private endpoint details vào text widgets.

Dashboard không tự tạo quyền truy cập data. Người xem phải có quyền cần thiết đối với metrics/logs/traces và source accounts.

## 26. Chi phí và hiệu năng dashboard

Dashboard metric widgets tiêu thụ API/query capacity và có thể hiển thị metrics từ nhiều accounts/Regions. Một số tính năng/query có pricing hoặc quota riêng.

Tối ưu:
- Hạn chế widgets và time series không cần thiết;
- Dùng SEARCH/Metrics Insights có filter/grouping cụ thể;
- Không query hàng trăm dimensions khi chỉ cần top-N;
- Chọn period phù hợp metric resolution;
- Giảm custom metric cardinality;
- Không bật detailed monitoring/request metrics nếu chưa có use case;
- Dùng dashboard variables để tái sử dụng layouts;
- Review dashboard usage và quota khi triển khai rộng.

Chi phí không chỉ nằm ở dashboard. Custom metrics, high-resolution metrics, alarms, logs ingestion/storage/query, Application Signals và traces có thể là phần lớn bill. Thiết kế metric trước khi phát ra có tác động dài hạn hơn việc giảm số widgets.

## 27. Dashboard deployment bằng AWS CLI và SDK

### AWS CLI

~~~bash
aws cloudwatch put-dashboard \
  --dashboard-name Orders-Operations \
  --dashboard-body file://dashboard.json

aws cloudwatch get-dashboard \
  --dashboard-name Orders-Operations

aws cloudwatch list-dashboards \
  --dashboard-name-prefix Orders
~~~

### AWS SDK for Java 2.x

~~~java
import software.amazon.awssdk.services.cloudwatch.CloudWatchClient;
import software.amazon.awssdk.services.cloudwatch.model.PutDashboardRequest;

public class DashboardPublisher {

    private final CloudWatchClient cloudWatch;

    public DashboardPublisher(CloudWatchClient cloudWatch) {
        this.cloudWatch = cloudWatch;
    }

    public void publish(String name, String dashboardBody) {
        cloudWatch.putDashboard(PutDashboardRequest.builder()
            .dashboardName(name)
            .dashboardBody(dashboardBody)
            .build());
    }
}
~~~

SDK/CLI identity cần quyền cloudwatch:PutDashboard. Để read back cần cloudwatch:GetDashboard; để list cần cloudwatch:ListDashboards.

PutDashboard thay nội dung dashboard cùng tên. Pipeline nên generate một dashboard body hoàn chỉnh, validate JSON và deploy một lần; không để nhiều writers cập nhật từng phần cạnh tranh.

## 28. Kiểm thử dashboard trước khi phát hành

Dashboard là một phần của vận hành, nên cần kiểm tra cùng IaC/service release.

Checklist:
- Dashboard JSON parse hợp lệ;
- Tất cả metric namespaces/names/dimensions tồn tại;
- Statistic và period phù hợp metric publishing interval;
- Metric math expressions tham chiếu đúng IDs;
- Variables đổi đúng mọi widgets;
- Cross-account/Region selector hiển thị đúng nguồn;
- Alarm widgets có ARN đúng;
- Logs Insights queries dùng đúng field names;
- Links mở đúng dashboard/runbook;
- Dashboard không lộ secrets/PII;
- Data freshness/no-data được thể hiện;
- Widget layout đọc được trên màn hình mục tiêu.

Một dashboard có thể được tạo thành công nhưng widgets vẫn rỗng do dimension mismatch, metric chưa publish, Region sai hoặc permissions thiếu. Kiểm tra dashboard trong account có telemetry thật và dùng test data trước production.

## 29. Troubleshooting dashboard

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Widget không có data | Namespace/name/dimensions sai hoặc metric chưa publish | Mở Metrics console, kiểm tra exact dimension set |
| Metric xuất hiện trễ | Publishing interval/ingestion delay | Tăng period/time range, kiểm tra emitter |
| Counter thấp bất thường | Dùng Average thay Sum hoặc event duplicate/lost | Chọn Sum và xác minh event pipeline |
| p95/p99 không có | Metric chỉ publish statistic set không hỗ trợ percentile | Publish raw samples/distribution phù hợp |
| Error rate thành 0 khi không có traffic | Expression IF denominator=0 trả 0 | Hiển thị request volume/no-data state riêng |
| SEARCH không tìm thấy metric | Không có recent datapoints hoặc schema filter sai | Kiểm tra namespace/dimensions/time range |
| Metrics Insights query rỗng | SCHEMA không khớp dimension schema | Kiểm tra metric schema và Region |
| Dashboard variable không lọc widget | Variable property/pattern sai | Kiểm tra variable source và metric dimensions |
| Cross-account widget rỗng | OAM link/sink hoặc sharing permissions thiếu | Xác minh source/monitoring account và sharing |
| Cross-Region widget sai | Widget region property không đúng | Đặt Region tường minh cho từng widget |
| Alarm widget không hiện | ARN sai hoặc viewer thiếu alarm permission | Kiểm tra account/Region/ARN và IAM |
| Logs widget rỗng | Query field names/time range sai | Test query trong Logs Insights trước |
| Dashboard ghi đè thay đổi của team khác | PutDashboard thay toàn bộ body | Single owner/pipeline, code review và serialization |
| Business revenue sai | Currency trộn, duplicate events hoặc refund semantics sai | Normalize currency, dedupe và xác định KPI contract |
| KPI stale nhưng chart vẫn hiển thị | Không có freshness metric/last event time | Thêm data freshness widget và alarm |
| Widget chậm hoặc nhiều series | SEARCH/query quá rộng, cardinality cao | Filter, top-N, giảm dimensions/time range |

### Quy trình điều tra

~~~text
1. Xác nhận dashboard name, account, Region và time range.
2. Mở một metric widget và kiểm tra namespace/name/dimension set.
3. Xác minh metric có datapoints mới trong Metrics console.
4. Kiểm tra statistic, period, unit và y-axis.
5. Kiểm tra metric math IDs/denominators.
6. Với SEARCH/Metrics Insights, chạy query riêng và thu hẹp filters.
7. Kiểm tra dashboard variables và account/Region context.
8. Xác minh IAM/OAM permissions cho data source.
9. Kiểm tra CloudWatch Logs Insights query/field extraction.
10. So sánh business event source, deduplication và freshness.
11. Đọc dashboard validation messages và API response.
12. Sửa dashboard source trong Git/IaC rồi redeploy.
~~~

## 30. Lab: xây dashboard cho Orders service và checkout KPIs

### Kịch bản

Một ứng dụng e-commerce chạy ở ap-southeast-1 gồm API Gateway, Orders API, SQS, Lambda worker, DynamoDB và payment provider. Team cần dashboard để on-call và product operations cùng sử dụng.

### Bước 1 — Chốt KPI contract

| KPI | Định nghĩa | Source |
| --- | --- | --- |
| Checkout starts | Số checkout_started events đã dedupe | EMF/business events |
| Orders confirmed | Số order_confirmed events | EMF |
| Payment success | authorized / attempted | EMF |
| Revenue | Tổng amount_minor theo VND | Paid order events |
| Queue lag | ApproximateAgeOfOldestMessage | SQS |
| API errors | 5xx / requests | API Gateway |
| API p95 | p95 Latency | API Gateway |

Ghi rõ event IDs, currency, time zone, event timestamp và deduplication rule. Không tính revenue bằng cách cộng mọi message delivery.

### Bước 2 — Tạo EMF log event

~~~json
{
  "_aws": {
    "Timestamp": 1795144500000,
    "CloudWatchMetrics": [
      {
        "Namespace": "MyCompany/Commerce",
        "Dimensions": [["Environment", "Channel", "Market"]],
        "Metrics": [
          {"Name": "OrdersConfirmed", "Unit": "Count"}
        ]
      }
    ]
  },
  "Environment": "prod",
  "Channel": "web",
  "Market": "VN",
  "OrdersConfirmed": 1
}
~~~

Đảm bảo log pipeline chuyển nguyên JSON event tới CloudWatch Logs và EMF parser xử lý thành custom metric.

### Bước 3 — Tạo dashboard JSON

Dùng JSON ví dụ ở mục 13, bổ sung widgets cho SQS queue age, Lambda errors, DynamoDB throttles và business counters. Đặt period theo publishing interval và dùng Sum cho counters.

### Bước 4 — Deploy

~~~bash
aws cloudwatch put-dashboard \
  --dashboard-name Orders-Operations \
  --dashboard-body file://dashboard.json
~~~

### Bước 5 — Kiểm tra

- Tạo test order;
- Xác minh một event OrdersConfirmed được ghi;
- Xác minh metric Sum tăng đúng một;
- Tạo lỗi payment trong sandbox;
- Kiểm tra payment success rate và SQS age;
- Tìm trace/log cùng time range;
- Xác minh dashboard không hiển thị PII;
- Chạy lại sau khi đổi variable Environment hoặc Region.

### Bước 6 — Viết runbook

Runbook nên chỉ rõ dashboard owner, KPI definition/source, critical alarms/thresholds, links tới Logs Insights/trace search, service dependencies, rollback/mitigation actions, escalation contacts và last validated time.

## 31. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — Service dashboard

Orders API có request count bình thường, nhưng p99 latency tăng và SQS oldest message age tăng.

**Yêu cầu:** Chọn widgets, dimensions và time ranges; giải thích cách xác định bottleneck ở API, downstream dependency hay consumer backlog.

### Bài tập 2 — Business KPI

Checkout starts = 1.000, orders confirmed = 720, payment attempts = 800, authorized = 760.

**Yêu cầu:** Tính checkout conversion và payment authorization success; giải thích vì sao hai tỷ lệ có denominator khác nhau và cần deduplicate event nào.

### Bài tập 3 — Metric math

Widget có 5xx Sum và RequestCount Sum.

**Yêu cầu:** Viết expression tính error rate, xử lý denominator bằng 0 và giải thích tại sao cần hiển thị request volume cùng tỷ lệ.

### Bài tập 4 — EMF

Worker xử lý SQS Standard queue và có at-least-once delivery. Mỗi lần nhận message đều emit OrdersConfirmed.

**Yêu cầu:** Giải thích vì sao metric bị double count; thiết kế event ID/deduplication và chỉ emit metric khi business state transition đã durable.

### Bài tập 5 — Multi-account dashboard

Tổ chức có tooling, dev, staging và production accounts ở hai Regions.

**Yêu cầu:** Thiết kế monitoring account, OAM links, cross-account cross-Region dashboard, IAM viewers và account/Region selectors; chỉ ra data access boundaries.

### Bài tập 6 — Change management

Hai teams cùng dùng PutDashboard để update dashboard Orders-Operations.

**Yêu cầu:** Giải thích vì sao một team có thể ghi đè team kia; đề xuất single owner, Git/IaC, code review và deployment serialization.

### Bài tập 7 — SLO

Orders API có objective 99.9% successful requests trong rolling 30 days.

**Yêu cầu:** Định nghĩa SLI good/bad events, error budget, burn-rate alerts và widgets cần hiển thị.

### Bài tập 8 — Metrics Insights

Bạn cần tìm top 10 EC2 instances theo CPU utilization trong production.

**Yêu cầu:** Viết Metrics Insights query, kiểm tra SCHEMA dimensions và giải thích giới hạn query khi metric thiếu InstanceId.

### Câu hỏi ngắn

1. **Service dashboard và business dashboard khác nhau thế nào?** Một bên theo dõi sức khỏe service; bên kia đo kết quả customer/business journey.
2. **Golden signals gồm gì?** Traffic, latency, errors và saturation.
3. **Counter nên dùng statistic nào?** Sum.
4. **Latency nên xem statistic nào?** p95/p99 cùng average khi phù hợp.
5. **CloudWatch metric identity gồm gì?** Namespace, metric name và toàn bộ dimension set.
6. **Dimension cardinality cao gây gì?** Tăng metric variants, chi phí và khó phân tích.
7. **EMF dùng làm gì?** Trích custom metrics từ structured CloudWatch Logs events.
8. **Có nên emit business counter mỗi lần SQS delivery không?** Không nếu message có thể được giao lặp; phải dedupe.
9. **Metric math dùng làm gì?** Kết hợp time series để tính KPI/rate/ratio.
10. **SEARCH có tìm metric chưa từng publish không?** Không; metric phải có data phù hợp.
11. **Metrics Insights dùng ngôn ngữ gì?** SQL-like query.
12. **Dashboard variables giúp gì?** Tái sử dụng dashboard cho nhiều dimensions/environments.
13. **PutDashboard append widget hay replace body?** Thay dashboard body cùng tên.
14. **CloudWatch dashboard có global theo account không?** Có; dashboard không gắn một Region, widgets chọn Region riêng.
15. **OAM cross-account observability hoạt động trong phạm vi nào?** Chia sẻ metrics/logs/traces và các telemetry hỗ trợ giữa accounts trong cùng Region.
16. **Cross-account cross-Region dashboards dùng khi nào?** Khi cần tổng hợp metrics từ nhiều accounts/Regions.
17. **No data có đồng nghĩa zero không?** Không.
18. **Anomaly detection có phù hợp mọi metric không?** Không; cần history/seasonality và threshold semantics phù hợp.
19. **SLO cần những thành phần nào?** SLI, objective, window, good/bad events và error budget.
20. **Dashboard có tự cấp quyền xem logs/metrics không?** Không; viewer cần permissions cho data sources.
21. **KPI revenue nhiều currencies xử lý thế nào?** Tách currency hoặc normalize theo FX source/time rõ ràng.

## 32. Checklist trước production

- [ ] Dashboard có owner, audience, purpose và runbook.
- [ ] Service dashboard hiển thị traffic, latency, errors, saturation và dependencies.
- [ ] Business dashboard có KPI contract, denominator, window, timezone và currency.
- [ ] Business events được deduplicate/idempotent trước khi emit counters.
- [ ] Metric namespace/name/dimensions/units được chuẩn hóa.
- [ ] Không dùng PII/high-cardinality identifiers làm dimensions.
- [ ] Counter dùng Sum; latency dùng percentile khi metric hỗ trợ.
- [ ] Period phù hợp metric publishing interval/resolution.
- [ ] Metric math xử lý no traffic/no data rõ ràng.
- [ ] SEARCH/Metrics Insights có filters và limits phù hợp.
- [ ] Dashboard variables được test trên mọi widgets.
- [ ] Account/Region context rõ cho cross-account/cross-Region views.
- [ ] Alarms/SLO/anomaly bands có threshold/owner/action rõ ràng.
- [ ] Logs Insights/traces links dùng đúng fields và permissions.
- [ ] Dashboard JSON được validate và quản lý qua Git/IaC.
- [ ] PutDashboard ownership được serialize, tránh lost updates.
- [ ] IAM/OAM/sharing policy chỉ cho viewers cần thiết.
- [ ] Không public-share dashboard có dữ liệu vận hành nhạy cảm.
- [ ] Custom metric, logs, alarms và query cost được theo dõi.
- [ ] Có freshness/no-data signal cho KPI quan trọng.
- [ ] Dashboard đã test với telemetry thật trong non-production.
- [ ] Có deployment markers, rollback/incident links và runbook.
- [ ] Cross-Region aggregates không che khuất Region có traffic thấp nhưng lỗi cao.

## 33. Tổng kết

Dashboard CloudWatch hiệu quả kết nối hai góc nhìn: **sức khỏe của từng service** và **kết quả nghiệp vụ mà người dùng nhận được**. Service dashboards tập trung vào golden signals, dependencies, saturation, queue backlog, alarms và SLO. Business dashboards tập trung vào event definitions, funnel, conversion, payment success, revenue, refunds và fulfillment.

Độ tin cậy của dashboard phụ thuộc chất lượng metric contract. Hãy chuẩn hóa namespace/dimensions/units, chọn statistic/period đúng, xử lý duplicate events, tách currencies và hiển thị freshness/no-data. Dùng metric math, SEARCH và Metrics Insights để tạo góc nhìn động; dùng variables để tái sử dụng layouts; dùng CloudFormation/IaC để version control dashboard.

Khi vận hành nhiều accounts/Regions, chọn đúng cơ chế CloudWatch OAM hoặc cross-account cross-Region dashboard. Kết hợp metrics với alarms, Logs Insights, traces và Application Signals để chuyển từ “có vấn đề” sang “vấn đề ở đâu và tác động tới KPI nào”. Bảo vệ dashboard data, kiểm soát cardinality/query cost và kiểm thử dashboard như một phần của release.

### Tài liệu chính thức

- [CloudWatch Dashboards](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Dashboards.html)
- [Dashboard body structure and widgets](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Dashboard-Body-Structure.html)
- [Dashboard variables](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_dashboard_variables.html)
- [Metric math](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html)
- [SEARCH expression](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/search-expression-syntax.html)
- [Metrics Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-metrics-insights.html)
- [Metrics Insights quotas](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-metrics-insights-limits.html)
- [Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)
- [CloudWatch cross-account observability](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Unified-Cross-Account.html)
- [Monitor across accounts and Regions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Cross-Account-Methods.html)
- [Cross-account cross-Region dashboards](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Dashboards.html#CloudWatch_Dashboards_CrossAccount)
- [CloudWatch alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html)
- [CloudWatch anomaly detection](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Anomaly_Detection.html)
- [CloudWatch Application Signals](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals.html)
- [CloudWatch dashboard CloudFormation resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudwatch-dashboard.html)
- [CloudWatch PutDashboard API](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutDashboard.html)

**Lưu ý vận hành:** AWS service metrics, custom metric dimensions, dashboard variables, Metrics Insights và cross-account features có giới hạn/availability riêng. Trước production, kiểm tra metric schema và permissions trong đúng account/Region; xác minh dashboard với telemetry thật và giữ KPI definitions trong version control.
