# CloudWatch namespace, dimension, statistic và period

> **Chương:** Quan sát với CloudWatch  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua hạ tầng Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Amazon CloudWatch Metrics là nền tảng dữ liệu time-series cho khả năng quan sát AWS workloads. Để đọc đúng một biểu đồ hoặc thiết kế metric custom, cần hiểu bốn khái niệm liên kết với nhau:

- **Namespace** xác định vùng tên chứa metrics;
- **Dimension** xác định biến thể/đối tượng mà metric mô tả;
- **Statistic** quy định cách tổng hợp các điểm dữ liệu;
- **Period** quy định khoảng thời gian dùng để tổng hợp.

Bài học đi từ danh tính metric đến cách publish/query, chọn statistic cho từng loại dữ liệu, chọn period theo độ phân giải và retention, rồi đưa các quyết định đó vào dashboard và alarm.

Sau bài học, bạn có thể:

1. Xác định một CloudWatch metric bằng namespace, metric name và dimension set.
2. Thiết kế namespace custom dễ quản lý, tránh trộn lẫn metrics của nhiều ứng dụng.
3. Chọn dimensions ổn định, hữu ích và kiểm soát cardinality.
4. Phân biệt standard resolution và high resolution.
5. Chọn Sum, SampleCount, Average, Minimum, Maximum và percentile theo ý nghĩa dữ liệu.
6. Giải thích statistic set và giới hạn khi truy vấn percentile.
7. Chọn period phù hợp với metric resolution, truy vấn và thời gian lưu trữ.
8. Publish custom metrics bằng AWS CLI và AWS SDK for Java 2.x.
9. Truy vấn metrics bằng GetMetricData, metric math và CloudWatch console.
10. Tránh các lỗi phổ biến khi xây dựng alarms, dashboards và thống kê.

## 1. Mô hình dữ liệu CloudWatch Metrics

### 1.1. Metric là một chuỗi dữ liệu theo thời gian

Metric là tập hợp các data points được publish theo timestamp. Ví dụ, ứng dụng checkout có thể gửi thời gian xử lý đơn hàng, số đơn tạo thành công và số lần gọi payment provider thất bại.

Một data point thường gồm:

- Namespace;
- Metric name;
- Zero hoặc nhiều dimensions;
- Timestamp;
- Value hoặc statistic set;
- Unit tùy chọn;
- Storage resolution đối với custom metric.

CloudWatch metrics có phạm vi Region. Metric được publish ở ap-southeast-1 không tự xuất hiện trong ap-southeast-2; muốn quan sát nhiều Regions phải truy vấn từng Region hoặc dùng metric math/cross-account observability theo kiến trúc phù hợp.

### 1.2. Danh tính của một metric

Có thể ghi nhớ danh tính metric như sau:

~~~text
Metric identity
  = AWS account + Region
  + Namespace
  + MetricName
  + exact Dimension set
~~~

Account và Region xác định phạm vi CloudWatch đang lưu metric. Trong phạm vi đó, namespace, metric name và tổ hợp dimensions định danh time series. Unit không phải dimension; các data points có unit khác nhau được CloudWatch xử lý thành các luồng thống kê riêng.

Ví dụ:

~~~text
Account: 111122223333
Region: ap-southeast-1
Namespace: Acme/Checkout
MetricName: RequestLatency
Dimensions:
  Environment = production
  Operation   = CreateOrder
Unit: Milliseconds
~~~

Một metric khác có Environment=staging hoặc Operation=Refund là một time series riêng, dù namespace và metric name giống nhau.

### 1.3. Bốn khái niệm không thay thế nhau

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Namespace | Metric thuộc hệ thống/nhóm nào? | Acme/Checkout |
| Dimension | Metric mô tả đối tượng/nhóm nào? | Environment=production |
| Statistic | Tổng hợp các samples ra sao? | Average, Sum, p95 |
| Period | Tổng hợp trong khoảng bao lâu? | 60 giây |

Một cấu hình query có thể chọn đúng metric nhưng vẫn cho kết quả gây hiểu nhầm nếu statistic hoặc period không phù hợp. Ví dụ, Sum của CPU utilization không có ý nghĩa giống Average; Average latency một phút có thể che khuất request chậm trong khoảng thời gian ngắn.

### 1.4. AWS metrics và custom metrics

AWS services publish metrics trong namespace của dịch vụ, thường theo dạng AWS/Service, ví dụ:

- AWS/EC2;
- AWS/Lambda;
- AWS/RDS;
- AWS/SQS;
- AWS/ApplicationELB.

Custom metrics do ứng dụng, agent hoặc pipeline telemetry publish. Bạn tự thiết kế namespace, metric name, dimensions, unit và resolution. Một custom metric không tự động xuất hiện chỉ vì ứng dụng có log; cần publish qua PutMetricData, CloudWatch Agent, Embedded Metric Format (EMF) hoặc integration phù hợp.

## 2. Namespace: phân vùng metrics theo hệ thống

### 2.1. Namespace là gì?

Namespace là container logic cho các metrics. Metrics ở namespace khác nhau được cô lập để các ứng dụng không vô tình trộn thống kê vào cùng một nhóm.

CloudWatch không có namespace mặc định. Mỗi data point publish phải có namespace. Tên namespace tối đa 255 ký tự và dùng ký tự ASCII hợp lệ.

AWS thường đặt tên namespace theo mẫu AWS/<service>. Với custom metrics, nên dùng prefix của tổ chức hoặc sản phẩm, ví dụ:

~~~text
Acme/Checkout
Acme/Payments
Acme/Inventory
Acme/Platform/API
~~~

Không đặt custom namespace bắt đầu bằng AWS/, vì vùng tên này dành cho metrics do AWS services publish.

### 2.2. Quy tắc đặt namespace

Một namespace tốt nên:

- Gắn với bounded context hoặc hệ thống có ownership rõ;
- Có naming convention ổn định qua môi trường;
- Không chứa timestamp, request ID hoặc giá trị thay đổi theo từng deploy;
- Không tạo một namespace mới cho mỗi instance/container;
- Được ghi lại trong dashboard, runbook và metric catalog.

Có thể đưa môi trường vào dimension (Environment=production) để cùng namespace phục vụ nhiều môi trường. Nếu môi trường có ownership, retention hoặc quyền truy cập khác hẳn, tổ chức cũng có thể tách namespace; cần chọn một convention nhất quán.

### 2.3. Namespace không phải Region

Namespace không gom metrics xuyên Region. Acme/Checkout trong Singapore và Acme/Checkout trong Sydney vẫn là dữ liệu ở hai Region khác nhau. Khi điều tra incident, hãy xác nhận Region trước khi kết luận metric bị thiếu.

### 2.4. Vòng đời metric

Metrics không có thao tác xóa trực tiếp như xóa một file. Nếu metric không được publish thêm, dữ liệu cũ tự hết hạn theo retention; metric không có data points mới trong 15 tháng sẽ tự hết hạn.

Metric không có data point mới trong hai tuần có thể không xuất hiện trong danh sách của console hoặc kết quả ListMetrics. Nếu cần truy vấn metric cũ, hãy dùng GetMetricData hoặc GetMetricStatistics với đúng namespace, name và dimensions.

## 3. Dimension: định danh biến thể của metric

### 3.1. Dimension là name/value pair

Dimension là cặp tên/giá trị mô tả metric. Ví dụ:

~~~text
Environment = production
Service     = checkout
Operation   = CreateOrder
AvailabilityZone = ap-southeast-1a
InstanceId  = i-0123456789abcdef0
~~~

AWS services thường gắn dimensions như InstanceId, LoadBalancer, TargetGroup, FunctionName hoặc QueueName. Khi truy vấn, dimensions giúp chọn đúng đối tượng.

Một metric có thể có tối đa **30 dimensions**. Tuy nhiên, giới hạn tối đa không phải mục tiêu thiết kế. Mỗi dimension value combination tạo một metric identity riêng, do đó thêm dimension làm tăng số time series cần quản lý và có thể tăng chi phí custom metrics.

### 3.2. Dimension set chính xác là một phần của identity

Giả sử publisher gửi hai metrics:

~~~text
RequestLatency
  Environment=production

RequestLatency
  Environment=production, Operation=CreateOrder
~~~

Đây là hai metric identities riêng. Với custom metrics, CloudWatch không tự tổng hợp biến thể có hai dimensions thành metric chỉ có một dimension. Nếu chỉ publish tổ hợp Environment + Operation, query với riêng Environment sẽ không tự tạo ra tổng latency của tất cả operations.

Muốn có cả hai góc nhìn, có thể:

- Publish thêm metric tổng hợp chỉ có Environment;
- Query từng time series rồi dùng metric math;
- Dùng metric math SEARCH để tìm nhiều metric phù hợp;
- Thiết kế dimension set ngay từ đầu theo dashboard và alarm cần hỗ trợ.

Một số AWS service metrics có hỗ trợ aggregate qua dimensions, nhưng không nên suy rộng behavior đó cho custom metrics.

### 3.3. Dimension combination tạo metric mới

Ví dụ, các tổ hợp sau là bốn time series:

~~~text
Service=checkout, Environment=production
Service=checkout, Environment=staging
Service=payment,  Environment=production
Service=payment,  Environment=staging
~~~

Nếu thêm CustomerId có hàng triệu giá trị, số time series có thể tăng rất nhanh. Đây là cardinality explosion: metric catalog khó quản lý, truy vấn và dashboard khó tổng hợp, đồng thời chi phí có thể tăng mạnh.

### 3.4. Chọn dimensions có giá trị vận hành

Dimensions tốt thường trả lời câu hỏi vận hành:

| Dimension | Giá trị ví dụ | Dùng để |
|---|---|---|
| Environment | production | Tách prod/staging |
| Service | checkout | So sánh service |
| Operation | CreateOrder | Xác định endpoint/operation lỗi |
| Region | ap-southeast-1 | Chỉ dùng nếu muốn đưa Region thành dimension custom |
| InstanceId | i-... | Phân tích từng instance |

Tránh dimensions có giá trị gần như duy nhất cho mỗi event:

- Request ID;
- Trace ID;
- User ID;
- Email;
- Session ID;
- Timestamp;
- URL path chứa dynamic ID như /orders/12345.

Các giá trị này phù hợp hơn với structured logs hoặc traces. Metrics dùng để tổng hợp theo nhóm ổn định; logs/traces dùng để điều tra từng request.

### 3.5. Dimension không phải tag filter tự động

Resource tags không tự động trở thành dimensions của mọi metric. Muốn lọc metric theo tag, cần metric integration hỗ trợ (ví dụ Metrics Explorer với resource tags) hoặc publish dimensions tương ứng.

Đừng giả định thêm tag Team=Payments vào EC2 sẽ tự tạo dimension Team trong mọi metric AWS/EC2. Kiểm tra dimensions thực tế do service publish và tính năng CloudWatch đang sử dụng.

### 3.6. Account, Region và dimension trong cross-account observability

Metric được lưu trong account/Region nơi publish. Với cross-account observability, monitoring account có thể quan sát metrics từ source accounts qua cơ chế liên kết; account source có thể được thể hiện trong kết quả/nhãn truy vấn.

Không cần tự nhét account ID vào dimensions chỉ để phân biệt metrics nếu kiến trúc CloudWatch đã giữ account context. Chỉ thêm dimension Account khi đó thực sự là một thuộc tính nghiệp vụ của custom metric và cần query theo dimension.

## 4. Unit và timestamp

### 4.1. Unit mô tả ý nghĩa của value

Unit thường dùng:

- Count;
- Count/Second;
- Milliseconds;
- Seconds;
- Bytes;
- Bytes/Second;
- Percent.

CloudWatch không tự đổi Milliseconds thành Seconds, cũng không đổi Bytes thành Megabytes. Unit giúp người đọc hiểu dữ liệu và được dùng để tách các luồng dữ liệu có unit khác nhau.

Nếu không chỉ định unit khi publish custom metric, CloudWatch gán unit là None. Việc ghi unit trong metric catalog và publisher giúp tránh nhầm lẫn giữa các team.

Nếu cùng metric identity có data points được publish với unit không nhất quán, query có thể trả nhiều data streams hoặc không có dữ liệu khi lọc sai unit. Hãy chọn một unit canonical cho metric và giữ ổn định.

### 4.2. Unit không thay thế metric name

Không nên publish một metric Latency lúc tính bằng milliseconds, lúc tính bằng seconds rồi mong CloudWatch tự chuẩn hóa. Tên metric và unit phải có ý nghĩa nhất quán. Có thể dùng tên rõ ràng như RequestLatency cùng unit Milliseconds, hoặc RequestLatencySeconds cùng unit Seconds.

### 4.3. Timestamp và UTC

Mỗi data point có timestamp. Nếu không gửi timestamp, CloudWatch gán thời điểm nhận dữ liệu. AWS khuyến nghị dùng UTC; thời gian query và alarm cũng được xử lý theo UTC.

Với custom metrics, timestamp có thể tối đa hai tuần trong quá khứ và hai giờ trong tương lai. Timestamp quá lệch so với thời gian hiện tại có thể khiến alarm ở trạng thái INSUFFICIENT_DATA hoặc thông báo chậm.

Không dùng local timezone tùy tiện trong producer. Đồng bộ clock trên hosts/containers và chuẩn hóa event time trước khi publish.

## 5. Resolution: standard và high resolution

### 5.1. Standard resolution

Phần lớn metrics do AWS services publish là standard resolution với granularity một phút. Standard custom metrics cũng là lựa chọn mặc định khi publish metric mà không chỉ định high resolution.

Standard resolution phù hợp cho:

- CPU utilization, network throughput;
- Queue depth;
- Request counts theo phút;
- Error rate theo phút;
- Business metrics không cần phản ứng dưới một phút.

### 5.2. High resolution

Custom metric có thể được publish với StorageResolution=1 để lưu ở độ phân giải một giây. High-resolution metrics hỗ trợ quan sát hoạt động dưới một phút, hữu ích cho spike ngắn, queue processing burst hoặc latency của service có traffic cao.

Ví dụ:

~~~json
{
  "MetricName": "RequestLatency",
  "Value": 245.7,
  "Unit": "Milliseconds",
  "StorageResolution": 1
}
~~~

Nếu bỏ StorageResolution hoặc dùng giá trị 60, metric được lưu ở standard resolution. High resolution không tự làm ứng dụng tốt hơn; chỉ chọn khi độ trễ quan sát thực sự cần thiết.

### 5.3. Period query theo resolution

Với standard metrics, period tối thiểu là 60 giây và phải là bội số của 60.

Với high-resolution metrics, có thể truy vấn ở các period ngắn như 1, 5, 10, 30 giây và các bội số của 60 giây. API MetricStat cũng liệt kê period 20 giây cho high-resolution data. Alarm high-resolution có thể dùng period 10 hoặc 30 giây; alarm thông thường dùng period là bội số của 60 giây.

Nếu chọn period 10 giây cho metric standard, CloudWatch không thể tạo dữ liệu 10 giây thực sự từ samples chỉ có độ phân giải một phút.

### 5.4. High resolution ảnh hưởng chi phí

High-resolution metrics hữu ích khi cần phản ứng nhanh, nhưng publish dày hơn có thể tăng số API requests và chi phí custom metrics. High-resolution alarms 10/30 giây cũng có mức phí cao hơn alarm chuẩn.

Hãy bắt đầu bằng standard resolution. Chỉ nâng lên high resolution cho những metrics có yêu cầu rõ ràng về phát hiện spike hoặc latency dưới phút; ghi lại lý do và chủ sở hữu metric.

## 6. Statistic: CloudWatch tổng hợp data points thế nào?

### 6.1. Năm statistic cơ bản

CloudWatch cung cấp các statistic cơ bản:

| Statistic | Ý nghĩa |
|---|---|
| SampleCount | Số data points/samples trong period |
| Sum | Tổng giá trị của các samples |
| Average | Sum / SampleCount |
| Minimum | Giá trị nhỏ nhất trong period |
| Maximum | Giá trị lớn nhất trong period |

Ví dụ một period có bốn latency samples: 100, 120, 130 và 450 milliseconds.

- SampleCount = 4;
- Sum = 800;
- Average = 200;
- Minimum = 100;
- Maximum = 450.

Average mô tả trung bình, nhưng không cho biết tail latency. Maximum cho thấy điểm cao nhất nhưng dễ bị chi phối bởi một outlier. Chọn statistic theo câu hỏi bạn muốn trả lời.

### 6.2. Chọn statistic theo kiểu metric

| Loại metric | Statistic thường dùng | Lý do |
|---|---|---|
| Counter: orders created | Sum | Tổng số events trong period |
| Request count | Sum | Tổng request |
| Request latency | Average, p95, p99, Maximum | Trung bình và tail latency |
| CPU utilization | Average, Maximum | Tải trung bình và peak |
| Queue depth | Average, Maximum | Mức backlog và đỉnh backlog |
| Batch size | Average, Maximum, SampleCount | Kích thước và số lần batch |
| Error count | Sum | Tổng lỗi trong period |

Với counter, Sum thường có ý nghĩa hơn Average. Với gauge như CPU utilization, Average/Maximum thường hữu ích hơn Sum. Với latency, p95/p99 giúp nhận diện trải nghiệm của nhóm request chậm.

### 6.3. Average có thể che khuất tail latency

Giả sử trong một phút có hàng nghìn request nhanh và một nhóm nhỏ request rất chậm. Average có thể vẫn thấp dù một số khách hàng phải chờ lâu.

- Average trả lời: thời gian trung bình là bao nhiêu?
- p95 trả lời: 95% samples có giá trị thấp hơn hoặc bằng mức nào theo percentile calculation?
- p99 tập trung vào phần tail nghiêm trọng hơn.
- Maximum cho biết sample cao nhất trong period.

Đừng dùng một statistic duy nhất cho mọi mục đích. Dashboard có thể hiển thị Average và p95; alarm có thể dùng p95 hoặc error count tùy SLO.

### 6.4. Percentile và extended statistics

CloudWatch hỗ trợ percentile như p50, p90, p95, p99 và các extended statistics khác. Percentile giúp nhìn phân phối dữ liệu thay vì chỉ một giá trị trung bình.

Một số statistic mở rộng khác gồm trimmed mean (tm99), interquartile mean (IQM), winsorized mean (WM), trimmed count (TC), trimmed sum (TS) và percentile rank (PR). Chúng có thể hữu ích khi phân tích latency distributions hoặc histogram-like buckets.

Không phải mọi AWS service metric đều hỗ trợ percentile. Với custom metrics, percentile yêu cầu raw, unsummarized samples và không hỗ trợ metric có giá trị âm.

### 6.5. Statistic set

Khi số lượng samples lớn, publisher có thể gửi một statistic set thay vì từng raw data point. Statistic set gồm:

- Minimum;
- Maximum;
- Sum;
- SampleCount.

Ví dụ trong một phút, ứng dụng đo 100 request latency samples. Có thể publish min, max, sum và sample count của phút đó để truy vấn Average, Minimum, Maximum và SampleCount.

**Giới hạn quan trọng:** CloudWatch chỉ có thể tính percentile từ statistic set trong các trường hợp đặc biệt:

1. SampleCount=1 và Min, Max, Sum đều bằng nhau; hoặc
2. Min=Max và Sum=Min × SampleCount.

Nếu cần p95/p99 của latency, publish raw samples (hoặc dùng pipeline telemetry có hỗ trợ distribution phù hợp); đừng chỉ gửi statistic set đã gộp.

### 6.6. Unit và statistic aggregation

CloudWatch tổng hợp data points theo namespace, metric name, dimension set, unit và period. Nếu cùng metric identity nhưng các data points được gửi với unit khác nhau, chúng được tổng hợp thành các data streams riêng.

CloudWatch không tự convert unit trong lúc tính Average, Sum hoặc percentile. Hãy thống nhất unit ở producer và query.

## 7. Period: khoảng thời gian tổng hợp

### 7.1. Period là gì?

Period là độ dài khoảng thời gian mà CloudWatch dùng để tính statistic. Period được tính bằng giây.

Ví dụ, nếu period là 60 giây:

- Sum là tổng samples trong mỗi phút;
- Average là trung bình samples trong mỗi phút;
- Maximum là giá trị lớn nhất trong mỗi phút;
- p95 là percentile của samples trong mỗi phút.

Nếu period là 300 giây, mỗi statistic đại diện cho một khoảng năm phút. Period dài hơn làm biểu đồ mượt hơn nhưng có thể che spike ngắn.

### 7.2. Period hợp lệ

Với standard-resolution metrics, period phải ít nhất 60 giây và là bội số của 60: 60, 120, 300, 600, 3600,...

Với high-resolution metrics, có thể dùng các period dưới một phút được API hỗ trợ (1, 5, 10, 20, 30 giây) và các bội số của 60. Chọn period khớp với storage resolution và API/console/Alarm đang sử dụng.

### 7.3. Timestamp của statistic là đầu period

CloudWatch gắn timestamp cho statistic bằng thời điểm bắt đầu period. Ví dụ, statistic tổng hợp từ 10:00 đến 10:05 được gắn timestamp 10:00.

Trong khi period chưa kết thúc, statistic của bucket hiện tại có thể tiếp tục thay đổi khi samples mới được ghi nhận. Đừng coi giá trị ở bucket đang mở là kết quả cuối cùng của cả period.

### 7.4. Chọn period theo câu hỏi

| Câu hỏi | Period gợi ý |
|---|---|
| Spike latency vài giây có ảnh hưởng người dùng? | 1–10 giây nếu high resolution phù hợp |
| API error rate theo phút? | 60 giây |
| Xu hướng traffic trong 30 phút? | 300 giây |
| Báo cáo vận hành theo giờ? | 3600 giây |
| Điều tra lịch sử dài hạn? | Theo retention và resolution còn khả dụng |

Period không phải sampling interval của producer. Producer có thể publish nhiều samples trong một phút; CloudWatch sẽ tổng hợp theo period được query.

### 7.5. Period và alarm evaluation

CloudWatch alarm dùng period để tính một data point đánh giá. EvaluationPeriods xác định số period trong evaluation window; DatapointsToAlarm xác định có bao nhiêu điểm trong window phải breach để alarm chuyển trạng thái.

Ví dụ Period=60, EvaluationPeriods=5, DatapointsToAlarm=3 có nghĩa alarm đánh giá năm period một phút gần nhất và cần ba điểm vi phạm để chuyển sang ALARM theo evaluation semantics.

Chọn period và evaluation window theo SLO. Period ngắn phát hiện nhanh hơn nhưng dễ phản ứng với nhiễu; period dài ổn định hơn nhưng tăng detection latency.

## 8. Retention, rollup và truy vấn dữ liệu lịch sử

### 8.1. CloudWatch lưu metrics theo resolution

CloudWatch giữ metric data theo các khoảng thời gian sau:

| Resolution của data point | Thời gian lưu ở resolution đó |
|---|---:|
| Dưới 60 giây (high resolution) | 3 giờ |
| 60 giây (1 phút) | 15 ngày |
| 300 giây (5 phút) | 63 ngày |
| 3600 giây (1 giờ) | 455 ngày (15 tháng) |

Dữ liệu cũ không biến mất ngay sau mốc đầu tiên; CloudWatch roll up thành độ phân giải thô hơn. Ví dụ, dữ liệu 1 phút sau 15 ngày có thể truy vấn ở resolution 5 phút; sau 63 ngày, dữ liệu được tổng hợp ở resolution 1 giờ.

### 8.2. Period phải phù hợp tuổi dữ liệu

Khi query metrics lịch sử, period tối thiểu phụ thuộc thời điểm StartTime:

| Tuổi của StartTime | Period cần dùng |
|---|---|
| Trong 3 giờ gần nhất | Có thể dùng sub-minute nếu metric high resolution |
| Từ 3 giờ đến 15 ngày | Bội số của 60 giây |
| Từ 15 đến 63 ngày | Bội số của 300 giây |
| Trên 63 ngày | Bội số của 3600 giây |

Ví dụ, query p95 trong 30 ngày qua với period 60 giây sẽ không trả dữ liệu theo resolution mong muốn cho toàn bộ khoảng thời gian. Cần dùng period 300 giây cho khoảng 15–63 ngày trước, hoặc chia query thành các time ranges với period tương ứng.

### 8.3. Metric cũ không xuất hiện trong ListMetrics

Metric không có data point mới trong hai tuần có thể không hiển thị trong CloudWatch console Browse hoặc kết quả ListMetrics. Điều đó không có nghĩa metric và dữ liệu đã bị xóa.

Nếu biết namespace, metric name và dimension set, hãy query trực tiếp bằng GetMetricData hoặc GetMetricStatistics với time range phù hợp.

### 8.4. Period và chi phí/trải nghiệm quan sát

Period nhỏ tạo nhiều data points và có thể tăng chi phí hiển thị/alarms hoặc khối lượng dữ liệu query. Period lớn giảm độ chi tiết và có thể làm mất dấu spike ngắn. Hãy chọn period dựa trên:

- Thời gian phản ứng mong muốn;
- Resolution thực tế của metric;
- SLO và alerting window;
- Retention của dữ liệu;
- Chi phí custom metrics và alarms;
- Khả năng điều tra sau incident.

## 9. Publish custom metrics bằng AWS CLI

### 9.1. Tạo metric data file

Ví dụ ứng dụng checkout publish request latency cho môi trường production và operation CreateOrder. Tạo file metric-data.json:

~~~json
[
  {
    "MetricName": "RequestLatency",
    "Dimensions": [
      {
        "Name": "Environment",
        "Value": "production"
      },
      {
        "Name": "Operation",
        "Value": "CreateOrder"
      }
    ],
    "Value": 245.7,
    "Unit": "Milliseconds",
    "StorageResolution": 1
  },
  {
    "MetricName": "OrdersCreated",
    "Dimensions": [
      {
        "Name": "Environment",
        "Value": "production"
      }
    ],
    "Value": 1,
    "Unit": "Count"
  }
]
~~~

Hai metrics có dimension sets khác nhau và mang ý nghĩa khác nhau:

- RequestLatency là latency sample; high resolution được bật bằng StorageResolution=1;
- OrdersCreated là counter event; dùng standard resolution và Sum khi truy vấn.

### 9.2. Gửi dữ liệu lên namespace

~~~bash
aws cloudwatch put-metric-data \
  --namespace Acme/Checkout \
  --metric-data file://metric-data.json \
  --region ap-southeast-1
~~~

Lệnh này publish hai metrics vào namespace Acme/Checkout trong Region ap-southeast-1. Nếu ứng dụng chạy trong AWS, cấp IAM role có quyền cloudwatch:PutMetricData và giới hạn namespace bằng condition phù hợp khi thiết kế policy.

Không đưa access key vào script hoặc source code. Dùng workload identity/role và AWS SDK credential provider chain.

### 9.3. Lưu ý về timestamp

Nếu không cung cấp Timestamp, CloudWatch dùng thời điểm nhận data point. Với publisher gửi dữ liệu trễ hoặc batch replay, cần cân nhắc timestamp gốc và giới hạn thời gian cho phép. Dùng UTC để tránh nhầm lẫn khi dashboard/alarm đánh giá theo thời gian.

## 10. Publish custom metrics bằng AWS SDK for Java 2.x

### 10.1. Gửi một raw data point

Ví dụ Java:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.cloudwatch.CloudWatchClient;
import software.amazon.awssdk.services.cloudwatch.model.Dimension;
import software.amazon.awssdk.services.cloudwatch.model.MetricDatum;
import software.amazon.awssdk.services.cloudwatch.model.PutMetricDataRequest;
import software.amazon.awssdk.services.cloudwatch.model.StandardUnit;

public class CheckoutMetricsPublisher {

    private final CloudWatchClient cloudWatch;

    public CheckoutMetricsPublisher() {
        this.cloudWatch = CloudWatchClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }

    public void publishRequestLatency(double latencyMillis) {
        Dimension environment = Dimension.builder()
            .name("Environment")
            .value("production")
            .build();

        Dimension operation = Dimension.builder()
            .name("Operation")
            .value("CreateOrder")
            .build();

        MetricDatum datum = MetricDatum.builder()
            .metricName("RequestLatency")
            .dimensions(environment, operation)
            .value(latencyMillis)
            .unit(StandardUnit.MILLISECONDS)
            .storageResolution(1)
            .build();

        PutMetricDataRequest request = PutMetricDataRequest.builder()
            .namespace("Acme/Checkout")
            .metricData(datum)
            .build();

        cloudWatch.putMetricData(request);
    }

    public void close() {
        cloudWatch.close();
    }
}
~~~

Ví dụ sử dụng AWS SDK for Java 2.x. Trong ứng dụng Spring Boot, nên quản lý CloudWatchClient như một singleton bean và đóng client khi application context shutdown; không tạo client mới cho từng request.

### 10.2. Chọn dimensions ổn định

Dimensions trong ví dụ gồm Environment và Operation. Nếu đưa OrderId hoặc RequestId vào dimensions, mỗi request có thể tạo metric identity mới, khiến cardinality tăng mạnh.

Hãy để ID duy nhất trong logs/traces, nơi chúng phù hợp hơn để tìm một request cụ thể.

### 10.3. Gửi statistic set khi cần pre-aggregate

Ví dụ publish dữ liệu latency đã tổng hợp cho một batch:

~~~java
import software.amazon.awssdk.services.cloudwatch.model.StatisticSet;

StatisticSet minuteStatistics = StatisticSet.builder()
    .minimum(8.0)
    .maximum(420.0)
    .sum(3100.0)
    .sampleCount(100.0)
    .build();

MetricDatum batchDatum = MetricDatum.builder()
    .metricName("RequestLatency")
    .dimensions(environment, operation)
    .unit(StandardUnit.MILLISECONDS)
    .statisticValues(minuteStatistics)
    .build();

PutMetricDataRequest batchRequest = PutMetricDataRequest.builder()
    .namespace("Acme/Checkout")
    .metricData(batchDatum)
    .build();

cloudWatch.putMetricData(batchRequest);
~~~

Với statistic set trên, Average là 31 milliseconds. Tuy nhiên, không thể khôi phục p95/p99 của 100 samples chỉ từ min/max/sum/count vì thông tin phân phối đã bị mất.

Nếu dashboard hoặc alarm cần tail latency, hãy publish raw samples hoặc dùng telemetry pipeline hỗ trợ distribution/histogram với semantics phù hợp.

## 11. Query metrics bằng GetMetricData và metric math

### 11.1. Query một metric với dimensions chính xác

Tạo file metric-data-queries.json:

~~~json
[
  {
    "Id": "latency",
    "MetricStat": {
      "Metric": {
        "Namespace": "Acme/Checkout",
        "MetricName": "RequestLatency",
        "Dimensions": [
          {
            "Name": "Environment",
            "Value": "production"
          },
          {
            "Name": "Operation",
            "Value": "CreateOrder"
          }
        ]
      },
      "Period": 60,
      "Stat": "p95"
    },
    "ReturnData": true
  }
]
~~~

Chạy truy vấn:

~~~bash
aws cloudwatch get-metric-data \
  --metric-data-queries file://metric-data-queries.json \
  --start-time 2026-11-20T03:00:00Z \
  --end-time 2026-11-20T04:00:00Z \
  --region ap-southeast-1
~~~

Thời gian trong ví dụ là UTC; điều chỉnh start/end theo thời gian incident cần điều tra. Query phải dùng đúng namespace, metric name và dimension set đã publish. Nếu bỏ một dimension custom, bạn có thể truy vấn một metric identity khác chưa từng được tạo.

### 11.2. GetMetricData và GetMetricStatistics

GetMetricData phù hợp khi cần lấy nhiều metrics, dùng metric math hoặc phân trang kết quả. GetMetricStatistics là API đơn giản hơn cho một metric identity và một statistic request.

Dùng GetMetricData cho dashboard/query hiện đại, đặc biệt khi cần kết hợp nhiều series. Dù dùng API nào, hãy chỉ định period phù hợp resolution và retention.

### 11.3. Metric math tính rate

Giả sử metric OrdersCreated publish số lượng orders dưới dạng counter theo từng data point. Query với Sum cho một period 60 giây sẽ trả tổng orders trong phút đó.

Có thể dùng metric math để tính orders mỗi giây:

~~~text
m1 = OrdersCreated, Statistic=Sum, Period=60
expression = m1 / PERIOD(m1)
~~~

PERIOD(m1) trả period tính bằng giây. Nếu m1 là tổng orders trong 60 giây, biểu thức trả count/second.

Với error rate, có thể tính:

~~~text
100 * errors / requests
~~~

Trong production, cần xử lý mẫu số bằng zero/missing data, bảo đảm hai metrics có cùng period, dimension scope và timestamp alignment. Nếu requests và errors dùng dimension sets khác nhau, phép chia có thể không đại diện đúng cùng traffic cohort.

### 11.4. Metric math không tự tạo dữ liệu gốc bị thiếu

Metric math có thể kết hợp các time series đã tồn tại, nhưng không tự biến một dimension set chưa từng publish thành metric gốc. Dùng SEARCH để tìm nhiều time series phù hợp hoặc publish metric tổng hợp riêng khi cần một góc nhìn ổn định cho alarms.

### 11.5. Xem metric trong CloudWatch console

Trong CloudWatch console:

1. Mở Metrics / All metrics;
2. Chọn namespace;
3. Chọn metric name/dimension combination;
4. Chọn statistic và period;
5. Đưa metric vào graph hoặc tạo alarm.

Console nhóm metrics theo namespace và dimension combinations. Nếu không thấy metric, xác minh account, Region, namespace, dimension values và thời gian data point trước khi kết luận publisher lỗi.

## 12. Chọn statistic và period cho dashboard/alarm

### 12.1. Dashboard nên hiển thị nhiều góc nhìn

Ví dụ dashboard cho checkout:

| Widget | Metric | Statistic | Period |
|---|---|---|---:|
| Request volume | Requests | Sum | 60 giây |
| Order throughput | OrdersCreated | Sum | 60 giây |
| Latency trend | RequestLatency | Average | 60 giây |
| Tail latency | RequestLatency | p95, p99 | 60 giây |
| Peak latency | RequestLatency | Maximum | 60 giây |
| Error volume | RequestErrors | Sum | 60 giây |

Đặt tên widget thể hiện statistic và unit. Một graph có nhiều metrics với unit khác nhau có thể gây khó đọc; tách trục hoặc widget khi cần.

### 12.2. Alarm cần statistic, period và evaluation window

Khi tạo alarm, quyết định:

- Metric identity;
- Statistic hoặc extended statistic;
- Period;
- Threshold và comparison operator;
- EvaluationPeriods;
- DatapointsToAlarm;
- TreatMissingData;
- Alarm action/notification.

Ví dụ, alarm p95 latency lớn hơn 800 milliseconds trong 3/5 period một phút. Điều này yêu cầu metric publish raw latency samples đủ để CloudWatch tính percentile.

### 12.3. Missing data không đồng nghĩa zero

Metric có thể không có data point vì không có traffic, publisher lỗi, permission bị deny hoặc service không phát metric. TreatMissingData có các lựa chọn như breaching, notBreaching, ignore và missing.

Ví dụ:

- Heartbeat metric không xuất hiện có thể là outage; có thể xem missing như breaching;
- Request count không xuất hiện khi không có traffic có thể là bình thường;
- Nếu publisher ngừng hoạt động, alarm có thể cần riêng một heartbeat/agent health metric.

Không tự động coi missing data là zero cho mọi metric.

### 12.4. Alarm period và high-resolution metric

High-resolution metric không bắt buộc mọi alarm phải dùng 10 giây. Nếu SLO cho phép phát hiện theo phút, regular alarm với period là bội số 60 vẫn có thể phù hợp. Dùng 10/30 giây khi detection latency cần thiết và chấp nhận chi phí cao hơn.

### 12.5. Statistic cần khớp với ý nghĩa threshold

Không đặt alarm CPU utilization bằng Sum nếu threshold được thiết kế cho phần trăm CPU. Không đặt request count bằng Average nếu mục tiêu là tổng số requests. Không dùng Average latency làm proxy cho p99 SLO.

Metric name, unit, statistic, period và threshold cần được review như một bộ cấu hình thống nhất.

## 13. Thiết kế metric catalog và kiểm soát cardinality/chi phí

### 13.1. Metric catalog

Với mỗi custom metric, ghi lại:

| Trường | Ví dụ |
|---|---|
| Namespace | Acme/Checkout |
| Metric name | RequestLatency |
| Description | Thời gian xử lý request checkout |
| Unit | Milliseconds |
| Resolution | Standard hoặc high |
| Dimensions | Environment, Operation |
| Owner | Checkout team |
| Publish source | Spring Boot worker |
| Dashboard/alarm | Checkout SLO dashboard |
| Retention/usage | Theo CloudWatch metric retention |

Catalog giúp teams không publish nhiều metrics gần giống nhau với tên/unit/dimension khác nhau.

### 13.2. Cardinality và cost

Custom metrics thường được tính phí theo số metrics/metric identities được publish và các tính năng liên quan. Dimension combinations có thể làm số metric identities tăng nhanh; high-resolution publishing và high-resolution alarms cũng ảnh hưởng chi phí.

Để kiểm soát:

- Dùng dimension values có cardinality thấp và ổn định;
- Không dùng user/request/trace IDs làm dimensions;
- Không tạo metric name hoặc namespace theo từng deployment;
- Xem lại metric catalog định kỳ;
- Tắt publisher không còn cần thiết;
- Đo số metrics mới phát sinh khi thêm dimension;
- Dùng logs/traces cho dữ liệu có độ chi tiết cao.

### 13.3. Không publish cùng một metric từ nhiều nơi với ý nghĩa khác nhau

CloudWatch hợp nhất data points có cùng namespace, metric name và dimensions từ nhiều nguồn thành cùng metric. Đây là tính năng hữu ích khi nhiều instances cùng publish một service metric, nhưng nguy hiểm nếu hai publishers dùng cùng identity mà khác unit hoặc semantics.

Đặt ownership và naming convention rõ. Nếu hai hệ thống đo những đại lượng khác nhau, dùng namespace, metric name hoặc dimensions riêng để tránh trộn dữ liệu.

## 14. Troubleshooting metrics

### 14.1. Không tìm thấy metric trong console

Kiểm tra:

1. Account và Region hiện tại;
2. Namespace và metric name chính xác;
3. Dimension names/values và tổ hợp dimensions đã publish;
4. Data point timestamp có nằm trong time range không;
5. Metric có data point mới trong hai tuần không;
6. Publisher có quyền cloudwatch:PutMetricData không;
7. Unit có bị publish không nhất quán không.

Metric cũ có thể không xuất hiện trong Browse/ListMetrics nhưng vẫn query được trực tiếp bằng GetMetricData/GetMetricStatistics.

### 14.2. Query trả null hoặc không có datapoints

Nguyên nhân thường gặp:

- Sai namespace hoặc metric name;
- Thiếu hoặc thừa dimension;
- Unit filter không khớp;
- Region sai;
- StartTime/EndTime không chứa timestamp data point;
- Period không phù hợp resolution hoặc tuổi dữ liệu;
- Metric đã roll up sang resolution thô hơn;
- Timestamp nằm ngoài giới hạn publish.

Hãy thử query không chỉ định Unit để xem dữ liệu thuộc unit nào; sau đó chuẩn hóa producer.

### 14.3. Percentile không xuất hiện

Kiểm tra:

- Metric có hỗ trợ percentile không;
- Custom metric có publish raw data points không;
- Có dùng statistic set không;
- Giá trị metric có âm không;
- Statistic set có thỏa một trong hai điều kiện đặc biệt để percentile khả dụng không.

Nếu chỉ publish Min/Max/Sum/SampleCount của một batch samples, CloudWatch không thể tái dựng phân phối ban đầu để tính p95/p99.

### 14.4. Period dưới một phút không trả dữ liệu

Xác minh metric được publish với StorageResolution=1. Standard resolution chỉ hỗ trợ period từ 60 giây và bội số của 60. Kiểm tra cả tuổi của StartTime; dữ liệu cũ hơn ba giờ không còn truy vấn ở sub-minute period.

### 14.5. Average khác kỳ vọng

Kiểm tra samples có cùng metric identity/unit hay không, SampleCount có đúng không, period có đang gộp nhiều data points không và publisher có gửi statistic set đúng Min/Max/Sum/SampleCount không.

Nếu nhiều instances publish cùng identity, CloudWatch tổng hợp chúng thành một metric. Nếu muốn xem từng instance, thêm dimension ổn định như InstanceId hoặc dùng metrics do AWS service publish theo resource dimensions.

### 14.6. Alarm ở trạng thái INSUFFICIENT_DATA

Kiểm tra period/evaluation window, missing data behavior, timestamp UTC, publisher health và metric identity. Một custom metric có timestamp lệch nhiều so với thời gian hiện tại có thể không phù hợp với alarm đang đánh giá theo UTC hiện tại.

## 15. Case study: CloudWatch metrics cho checkout service

### 15.1. Bối cảnh

Một ứng dụng Spring Boot checkout chạy trên nhiều ECS tasks ở ap-southeast-1. Đội vận hành cần:

- Đo số đơn hàng được tạo;
- Theo dõi request latency;
- Phát hiện tail latency vượt SLO;
- Phân biệt production và staging;
- Không tạo hàng triệu metrics theo từng order/request;
- Điều tra được incident trong 15 phút gần nhất và xu hướng theo ngày.

### 15.2. Metric design

| Namespace | Metric name | Dimensions | Unit | Resolution |
|---|---|---|---|---|
| Acme/Checkout | OrdersCreated | Environment | Count | Standard |
| Acme/Checkout | RequestLatency | Environment, Operation | Milliseconds | High |
| Acme/Checkout | RequestErrors | Environment, Operation, ErrorClass | Count | Standard |
| Acme/Checkout | PaymentProviderLatency | Environment, Provider | Milliseconds | High |

Không đưa OrderId, CustomerId, RequestId hoặc TraceId vào dimensions. Các ID này nằm trong structured logs/traces và correlation context.

### 15.3. Dashboard và alarm

Dashboard:

- OrdersCreated: Sum/60s;
- RequestErrors: Sum/60s;
- RequestLatency: Average, p95, p99/60s;
- PaymentProviderLatency: p95/60s;
- Queue backlog: metric AWS/SQS với đúng queue dimensions.

Alarm:

- p95 RequestLatency vượt SLO trong nhiều evaluation periods;
- RequestErrors Sum vượt ngưỡng;
- Heartbeat của publisher bị missing;
- Queue age/backlog vượt ngưỡng xử lý.

### 15.4. Điều tra incident

Khi khách hàng báo checkout chậm:

1. Chọn Region và production environment;
2. Xem RequestLatency p95/p99 trong period một phút;
3. So sánh theo Operation;
4. Kiểm tra PaymentProviderLatency;
5. Đối chiếu RequestErrors và OrdersCreated;
6. Dùng logs/traces để tìm request IDs/trace IDs cụ thể;
7. Kiểm tra dữ liệu có bị thiếu do publisher, dimension hoặc timestamp sai không.

Metrics cho biết nhóm hành vi nào đang bất thường; logs/traces giúp tìm request cụ thể gây ra bất thường đó.

## 16. Câu hỏi tự kiểm tra

1. Namespace dùng để làm gì?
2. Một CloudWatch metric được định danh bởi những trường nào?
3. Vì sao cùng namespace và metric name nhưng khác dimension set là metric riêng?
4. CloudWatch có tự aggregate custom metrics qua dimension sets không?
5. Một metric có thể có tối đa bao nhiêu dimensions?
6. Vì sao không nên đưa RequestId hoặc UserId vào dimensions?
7. AWS service metrics thường dùng namespace theo quy ước nào?
8. Custom namespace có nên bắt đầu bằng AWS/ không?
9. Unit có phải dimension không?
10. CloudWatch có tự đổi milliseconds thành seconds không?
11. Standard resolution có granularity mặc định bao nhiêu?
12. StorageResolution=1 có ý nghĩa gì?
13. Period nào phù hợp với standard-resolution metrics?
14. SampleCount và Sum khác nhau thế nào?
15. Khi nào dùng Average cho gauge?
16. Vì sao Average latency có thể che khuất tail latency?
17. p95 và p99 cho biết điều gì?
18. Statistic set chứa những trường nào?
19. Vì sao statistic set thường không đủ để tính p95/p99?
20. Period là gì và được tính bằng đơn vị nào?
21. Vì sao timestamp của statistic là đầu period?
22. Dữ liệu high resolution dưới 60 giây được giữ bao lâu?
23. Vì sao metric cũ có thể không xuất hiện trong ListMetrics?
24. GetMetricData có ưu điểm gì so với GetMetricStatistics?
25. Missing data có luôn tương đương zero không?

## 17. Đáp án gợi ý

1. Namespace phân vùng và cô lập metrics theo ứng dụng/dịch vụ.
2. Account, Region, namespace, metric name và dimension set.
3. Dimension set là một phần của metric identity.
4. Không; custom metrics không tự aggregate qua dimension combinations.
5. 30 dimensions.
6. Cardinality tăng nhanh, gây khó quản lý và tăng chi phí.
7. AWS/<service>, ví dụ AWS/EC2.
8. Không; prefix AWS/ dành cho AWS service namespaces.
9. Không; unit là thuộc tính của data point và các unit khác nhau được aggregate riêng.
10. Không; CloudWatch không tự convert unit.
11. Một phút.
12. Publish custom metric ở high resolution, lưu dữ liệu với granularity một giây.
13. Từ 60 giây và là bội số của 60.
14. SampleCount là số samples; Sum là tổng giá trị samples.
15. Khi đo gauge như CPU utilization hoặc queue depth.
16. Một nhóm nhỏ request rất chậm có thể không làm Average tăng đáng kể.
17. Ngưỡng mà 95% hoặc 99% samples nằm thấp hơn/theo percentile definition.
18. Minimum, Maximum, Sum và SampleCount.
19. Statistic set đã mất phân phối raw samples.
20. Khoảng tổng hợp statistic, tính bằng giây.
21. CloudWatch gắn statistic với thời điểm bắt đầu bucket.
22. Ba giờ.
23. Metric không có data point mới trong hai tuần có thể bị ẩn khỏi Browse/ListMetrics.
24. Hỗ trợ nhiều metrics, metric math và pagination.
25. Không; missing có thể do không có traffic hoặc publisher/permission failure.

## 18. Checklist thiết kế CloudWatch metrics

### Metric identity và namespace

- [ ] Namespace có ownership rõ và naming convention ổn định.
- [ ] Metric name mô tả đại lượng được đo.
- [ ] Region/account context đã được xác định.
- [ ] Dimension set phù hợp với dashboard, alarm và query.
- [ ] Không dùng dimensions có cardinality cao như request/user/trace IDs.
- [ ] Các publishers dùng cùng metric identity có cùng semantics và unit.

### Statistic, unit và period

- [ ] Unit được chọn nhất quán và không phụ thuộc conversion ngầm.
- [ ] Counter dùng Sum khi cần tổng số events.
- [ ] Gauge dùng Average/Minimum/Maximum phù hợp câu hỏi.
- [ ] Latency SLO có percentile nếu cần tail behavior.
- [ ] Statistic set chỉ dùng khi không cần phân phối raw để tính percentile.
- [ ] Period khớp standard/high resolution.
- [ ] Period query phù hợp tuổi dữ liệu và retention rollup.
- [ ] Timestamp dùng UTC và được đồng bộ clock.

### Publish, query và operations

- [ ] Producer có IAM permission cloudwatch:PutMetricData theo least privilege.
- [ ] Custom metric publisher được kiểm soát cardinality và chi phí.
- [ ] Query dùng đúng namespace, metric name và dimension combinations.
- [ ] Dashboard hiển thị rõ statistic, period và unit.
- [ ] Alarm có evaluation window và missing data behavior có chủ đích.
- [ ] Có logs/traces để điều tra event/request cụ thể.
- [ ] Có metric catalog, owner và runbook cho metrics quan trọng.

**Kết quả mong đợi:** bạn có thể thiết kế CloudWatch metric identities đúng, chọn dimensions có kiểm soát, publish và truy vấn custom metrics, chọn statistic/period đúng với ý nghĩa dữ liệu, và xây dựng dashboard/alarms không gây hiểu nhầm.

## Tài liệu AWS chính thức

- [CloudWatch metrics concepts](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html)
- [CloudWatch statistics definitions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Statistics-definitions.html)
- [MetricStat API reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_MetricStat.html)
- [PutMetricData API reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_PutMetricData.html)
- [GetMetricData API reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricData.html)
- [GetMetricStatistics API reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricStatistics.html)
- [View available metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/viewing_metrics_with_cloudwatch.html)
- [High-resolution metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/publishingMetrics.html)
- [Metric math](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html)
- [CloudWatch alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html)
- [AWS SDK for Java 2.x CloudWatch examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-cloudwatch.html)

> **Lưu ý áp dụng:** Namespace, metric names, dimensions, account IDs, Region, timestamps và values trong bài là ví dụ đào tạo. Trước khi publish hoặc tạo alarm production, xác minh metric identity, unit, resolution, retention, IAM permissions và cost/cardinality. Không dùng metrics thay thế logs/traces khi cần điều tra một request cụ thể.
