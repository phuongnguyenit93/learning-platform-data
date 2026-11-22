# Đánh giá chi phí, khả năng quan sát và ràng buộc nền tảng

## Mục tiêu học tập

Kiến trúc **serverless** giúp đội phát triển tập trung vào logic ứng dụng trong khi nhà cung cấp cloud quản lý phần lớn hạ tầng thực thi. Tuy vậy, “không quản lý máy chủ” không có nghĩa là không có chi phí vận hành, không cần quan sát hay có thể triển khai ứng dụng ở mọi nền tảng mà không thay đổi.

Trong thiết kế **Cloud Architecture**, lựa chọn serverless phải được đánh giá bằng dữ liệu workload, mô hình tính phí, yêu cầu vận hành, giới hạn nền tảng và các tiêu chí chất lượng. Bài học này tập trung vào ba góc nhìn cần đánh giá trước và trong khi vận hành: **chi phí (cost), khả năng quan sát (observability), và ràng buộc nền tảng (platform constraints)**.

Sau bài học, bạn có thể:

- Phân rã chi phí serverless theo request, thời gian thực thi, tài nguyên, lưu trữ, mạng, log, event và dịch vụ phụ trợ.
- Tính chi phí trên một giao dịch nghiệp vụ thành công, so sánh serverless với compute chạy thường trực và đánh giá độ nhạy theo tải.
- Thiết kế metrics, logs, traces, correlation ID, cảnh báo và dashboard để quan sát một luồng xử lý phân tán.
- Nhận diện cold start, timeout, concurrency, quota, giới hạn runtime, payload, networking và các đặc tính riêng của dịch vụ.
- Đánh giá mức độ phụ thuộc vào dịch vụ managed, khả năng di chuyển và chi phí thoát nền tảng.
- Xây dựng kịch bản chất lượng, TCO, ADR và kế hoạch kiểm thử dựa trên các nguyên tắc Well-Architected.

## 1. Serverless không có nghĩa là không có chi phí và vận hành

Serverless thường cung cấp compute theo event hoặc request. Nhà cung cấp chịu trách nhiệm vận hành host, runtime infrastructure và một phần khả năng mở rộng. Đội ứng dụng vẫn phải chịu trách nhiệm về:

- Mã ứng dụng, dependency, cấu hình và phiên bản runtime.
- Danh tính, quyền truy cập, secret, dữ liệu và phân vùng tenant.
- Hiệu năng, giới hạn concurrency, quota và hành vi khi phụ thuộc bị lỗi.
- Log, metrics, traces, cảnh báo, điều tra và ứng phó sự cố.
- Dung lượng queue, retry, DLQ, retention, backup và khả năng phục hồi.
- Chi phí sử dụng, ngân sách, egress, lưu log và các dịch vụ được gọi.

Một hàm có thể chỉ chạy 100 ms nhưng tạo ra nhiều log, gọi database nhiều lần, phát event và truyền dữ liệu lớn. Chi phí thực tế không chỉ nằm trong dòng compute của function. Ngược lại, một ứng dụng ít chạy có thể hưởng lợi từ mô hình trả theo mức sử dụng, miễn là phí nền tảng, network và observability không chiếm phần lớn tổng TCO.

**Quy tắc:** Đánh giá serverless theo toàn bộ đường đi nghiệp vụ và chi phí toàn hệ thống, không chỉ theo giá một lần invocation.

## 2. Phân rã mô hình chi phí serverless

### 2.1. Những thành phần thường tạo ra chi phí

| Thành phần | Cách chi phí có thể phát sinh | Câu hỏi cần làm rõ |
| --- | --- | --- |
| Invocation/request | Số lần gọi function hoặc số request | Retry có tính thêm invocation không? |
| Compute duration | Thời gian thực thi nhân với memory/CPU hoặc cấu hình tài nguyên | Thời lượng có bao gồm thời gian chờ I/O không? |
| Provisioned/minimum capacity | Giữ sẵn instance/concurrency để giảm cold start | Có cần năng lực luôn sẵn sàng hay không? |
| API gateway/edge | Request, kết nối, dữ liệu xử lý, rule và WAF | Có bao nhiêu request bị gọi lại hoặc không hợp lệ? |
| Event bus/queue | Số operation, message size, delivery, retention và polling | Message có bị phát lại hoặc gửi nhiều subscriber? |
| Database/cache | Request, read/write unit, storage, throughput, connection và replication | Function fan-out có tạo quá nhiều query? |
| Object storage | Storage, PUT/GET, lifecycle, retrieval và replication | Job lưu dữ liệu tạm có được dọn đúng hạn? |
| Network/egress | Lưu lượng ra Internet, cross-region, cross-zone hoặc private endpoint | Dữ liệu đi đâu, qua bao nhiêu hop? |
| Observability | Log ingest, indexing, retention, query, metric và trace | Debug level có phát sinh dữ liệu quá mức? |
| Security/governance | KMS, secret manager, policy evaluation, audit và scanning | Có gọi dịch vụ quản lý ở mỗi request? |
| Support/operations | Gói hỗ trợ, đội trực, kỹ năng và công cụ | Chi phí vận hành có được phân bổ vào TCO? |

Giá và đơn vị tính khác nhau theo từng dịch vụ, region, cấu hình và hợp đồng. Khi lập dự toán, dùng bảng giá hiện hành và kiểm tra các điều kiện tính phí cụ thể của nền tảng. Các phép tính trong bài là ví dụ minh họa, không phải báo giá.

### 2.2. Chi phí compute theo request và duration

Một cách mô hình hóa đơn giản:

~~~text
Compute cost
  ≈ invocation count × invocation price
  + billable compute duration × configured resource price
  + minimum/provisioned capacity cost (nếu có)
~~~

Cần phân biệt thời gian nghiệp vụ với thời gian bị tính phí. Một function có thể chờ network hoặc database nhưng vẫn đang trong khoảng thực thi được tính phí. Nếu code thực hiện nhiều lời gọi tuần tự, billable duration có thể tăng mà không làm tăng năng lực xử lý hữu ích.

Giả sử một function xử lý 2 triệu invocation trong tháng. Thời gian tính phí trung bình là 250 ms, cấu hình tài nguyên tương đương 1 đơn vị compute trong ví dụ. Tổng thời gian thực thi:

~~~text
2.000.000 × 0,25 giây = 500.000 giây
                         ≈ 138,9 giờ
~~~

Phép tính chỉ cho biết tổng duration trước khi áp dụng đơn giá và quy tắc làm tròn của dịch vụ. Nó chưa tính invocation fee, request đến API gateway, database, logs, network, queue và retry.

### 2.3. Đừng bỏ qua chi phí của lời gọi phụ thuộc

Một function có thể gọi database nhiều lần hoặc phát sinh một chuỗi event. Ví dụ một request API tạo booking dẫn tới:

1. Một invocation API handler.
2. Hai hoặc ba lần truy vấn database.
3. Một lần ghi outbox hoặc phát message.
4. Một invocation notification worker.
5. Một lần gửi email qua nhà cung cấp ngoài.
6. Nhiều log/trace và metric.

Nếu chỉ tính function đầu tiên, dự toán sẽ thiếu đáng kể. Hãy dùng **cost per business transaction** để chia tổng chi phí toàn tuyến cho số giao dịch thành công.

## 3. Xây dựng mô hình chi phí trên một đơn vị nghiệp vụ

### 3.1. Cost per successful transaction

~~~text
Cost per successful transaction
  = Total cost of the workload in the measurement period
    / Number of successful business transactions
~~~

Ví dụ minh họa, hệ thống đặt chỗ có các chi phí theo tháng:

| Hạng mục | Chi phí giả định (triệu VND/tháng) |
| --- | ---: |
| Function compute + invocation | 18 |
| API gateway và edge | 12 |
| Database và cache | 35 |
| Queue/event bus | 6 |
| Object storage | 4 |
| Network và egress | 8 |
| Logs, metrics, traces | 10 |
| Security, KMS, secrets và audit | 5 |
| **Tổng** | **98** |

Nếu tháng đó có 700.000 booking thành công:

~~~text
98.000.000 / 700.000 = 140 VND / booking thành công
~~~

Đây mới là chi phí workload theo phạm vi đã liệt kê. Chưa bao gồm nhân lực phát triển/vận hành, hỗ trợ thương mại, chi phí nền tảng dùng chung hoặc chi phí di chuyển nếu chưa được phân bổ. Khi so sánh với container/VM, phải dùng cùng phạm vi chi phí và cùng số booking thành công.

### 3.2. Đưa chi phí thất bại và retry vào phép tính

Giả sử có 1 triệu job được yêu cầu nhưng chỉ 980.000 job hoàn tất nghiệp vụ. 20.000 job còn lại lỗi, phải retry, đưa DLQ hoặc thao tác thủ công. Tổng bill vẫn phát sinh từ compute, queue, network và log của cả lần lỗi.

Không dùng tổng số invocation làm mẫu số của cost per transaction. Mẫu số nên là **kết quả nghiệp vụ hợp lệ**. Đồng thời, dashboard cần theo dõi cost per attempt để nhận diện retry bất thường.

Một chỉ số hữu ích:

~~~text
Retry overhead
  = Cost of retry attempts / Total processing cost
~~~

Nếu tỷ lệ này tăng đột ngột, có thể downstream đang không ổn định, timeout quá ngắn, idempotency khiến công việc lặp hoặc message bị poison. Tối ưu mã nguồn thôi chưa chắc giải quyết được nguyên nhân.

### 3.3. Phân bổ chi phí dùng chung

Một nền tảng có thể dùng chung API gateway, log workspace, KMS, network hub hoặc database cho nhiều workload. Hãy phân bổ chi phí theo driver phù hợp:

- Request count hoặc compute duration cho API/function platform.
- Log bytes cho ingestion và retention.
- Data transferred cho network/egress.
- Storage bytes và request cho object/database storage.
- Số tenant, workload hoặc key operations cho một số dịch vụ dùng chung.

Cần tránh phân bổ tùy tiện dẫn đến workload nhỏ bị gánh phần lớn chi phí chung. Tag, label và account/project boundary giúp truy vết chi phí tốt hơn.

## 4. So sánh serverless với compute chạy thường trực

### 4.1. Ví dụ các dạng workload

| Đặc tính workload | Mô hình có thể phù hợp để đánh giá |
| --- | --- |
| Lưu lượng hiếm, tăng đột biến, xử lý ngắn | Event-driven function |
| Traffic đều suốt ngày, cần latency ổn định | Container/VM hoặc serverless có capacity giữ sẵn |
| Job nền ngắn, có thể retry và chia nhỏ | Function hoặc worker event-driven |
| Job dài, cần nhiều RAM/CPU hoặc runtime đặc biệt | Container job, batch service hoặc compute chuyên dụng |
| Kết nối dài, protocol đặc biệt, stateful process | Container/VM hoặc dịch vụ hỗ trợ rõ đặc tính đó |
| Batch rất lớn theo lịch | Managed batch, container job hoặc worker cluster |

Serverless có thể giảm phần compute nhàn rỗi nhưng có thể tốn hơn khi tải đều, duration dài, memory cao hoặc cần provisioned capacity. Container/VM có thể tận dụng tài nguyên lâu dài nhưng đòi hỏi đội ngũ quản trị capacity, patching, scaling và resilience.

### 4.2. Mô hình hòa vốn minh họa

Giả sử so sánh hai phương án cùng đáp ứng một SLO:

- Serverless: chi phí theo request và duration, tăng theo số giao dịch.
- Container: có chi phí năng lực tối thiểu mỗi tháng và một phần chi phí tăng theo tải.
- Chi phí database, network, logs và security giống nhau trong ví dụ nên tạm loại khỏi phép so sánh.
- Chưa tính chi phí chuyển đổi và nhân lực để giữ phép tính đơn giản.

| Mức tải | Serverless (triệu VND/tháng) | Container (triệu VND/tháng) |
| --- | ---: | ---: |
| 100.000 giao dịch | 8 | 24 |
| 500.000 giao dịch | 20 | 27 |
| 1.000.000 giao dịch | 38 | 31 |
| 2.000.000 giao dịch | 74 | 42 |

Đây là dữ liệu giả định để minh họa rằng hai mô hình có thể đổi vị trí khi khối lượng tăng. Không thể suy ra ngưỡng hòa vốn chung cho mọi dịch vụ. Mỗi workload có function duration, memory, concurrency, database ratio và pattern traffic khác nhau.

### 4.3. Tính cả chi phí vận hành

Chi phí compute thấp hơn chưa chắc làm tổng TCO thấp hơn. Container cần patching, capacity planning, deployment, cluster upgrades, node lifecycle, scaling và on-call. Serverless giảm một phần công việc hạ tầng nhưng tăng yêu cầu hiểu quota, event semantics, distributed tracing, cold start và cách tính phí theo từng dịch vụ.

Hãy ước lượng **TCO**:

~~~text
TCO
  = Infrastructure and managed-service charges
  + Network and data transfer
  + Observability and security
  + Engineering and operational effort
  + Support, migration and exit cost allocation
  - Discounts / credits that are actually applicable
~~~

Chi phí nhân lực nên dựa trên giờ làm thực tế hoặc phân bổ hợp lý, không được mặc định bằng 0 chỉ vì nền tảng managed.

## 5. Phân tích độ nhạy: tải, duration và retry

Mô hình chi phí cần ít nhất ba kịch bản: thấp, kỳ vọng và đỉnh. Đối với function, các biến chính gồm:

- Số invocation/job.
- Thời gian thực thi trung bình và phân bố tail.
- Memory/CPU hoặc cấu hình tài nguyên.
- Concurrency và provisioned capacity.
- Tỷ lệ retry, failure và DLQ.
- Tỷ lệ request cache hit so với database call.
- Kích thước request/response/message và egress.
- Tần suất log, trace sampling và retention.

Ví dụ nếu duration tăng từ 200 ms lên 800 ms do downstream chậm, compute duration có thể tăng khoảng bốn lần với cùng số invocation (trước khi xét làm tròn và cấu hình cụ thể). Điều này thường là tín hiệu cần điều tra latency của dependency chứ không chỉ tối ưu mã trong function.

Một cách mô hình hóa:

~~~text
Monthly execution seconds
  = invocation count × average billable duration

Estimated peak concurrency
  ≈ arrival rate per second × average execution time in seconds
~~~

Đây là ước lượng theo mô hình Little's Law trong điều kiện tải ổn định. Đỉnh thực tế còn phụ thuộc burst, phân phối duration, giới hạn concurrency và cơ chế scale. Không dùng con số trung bình để cấp capacity cho một đợt spike ngắn mà không kiểm thử.

## 6. Chi phí observability có thể trở thành khoản đáng kể

Log và trace là thiết yếu cho chẩn đoán, nhưng việc ghi mọi request ở mức debug, lưu mọi payload và thu thập trace 100% trong thời gian dài có thể làm hóa đơn tăng mạnh.

Các biện pháp quản trị:

- Dùng structured logs với field rõ và tránh log payload không cần thiết.
- Quy định retention theo loại log và yêu cầu audit.
- Sampling trace có chọn lọc; giữ tỷ lệ cao hơn với lỗi và giao dịch quan trọng.
- Giảm cardinality của labels/metric; không tạo metric label theo từng user ID hoặc request ID.
- Dùng log level phù hợp theo môi trường.
- Tách audit log cần lưu giữ khỏi debug log ngắn hạn.
- Theo dõi chi phí observability theo workload/team/tenant.
- Có quota và cảnh báo ingest để một lỗi logging loop không làm tăng phí không kiểm soát.

Không được giảm log bằng cách xóa bằng chứng bảo mật hoặc audit bắt buộc. Tối ưu phải theo mục đích dữ liệu và chính sách lưu giữ.

## 7. Khả năng quan sát serverless: metrics, logs, traces

### 7.1. Vì sao quan sát serverless khó hơn một process đơn?

Trong mô hình event-driven, một hành trình nghiệp vụ có thể đi qua API gateway, function A, queue, function B, database và dịch vụ bên ngoài. Mỗi function là invocation độc lập; log theo từng tiến trình không tự nối được toàn hành trình.

Một trace lý tưởng:

~~~mermaid
flowchart LR
    CLIENT["Client"] --> GW["API Gateway"]
    GW --> F1["Function: create order"]
    F1 --> DB[("Order DB")]
    F1 --> Q[("Queue")]
    Q --> F2["Function: notification"]
    F2 --> EXT["Email provider"]
    F1 -. trace context .-> Q
    Q -. trace context .-> F2
~~~

Cần truyền correlation/trace context qua event/message và các lời gọi ngoài. Đặt một ID nghiệp vụ như orderId giúp người vận hành tra cứu; trace ID giúp hệ thống tracing nối spans của cùng một lần thực thi; hai ID có vai trò khác nhau.

### 7.2. Metrics: đo sức khỏe và kết quả

| Nhóm metric | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Invocation | Request count, invocation count, throttles | Lưu lượng và mức giới hạn |
| Duration | Average, p95/p99, max duration | Thời gian thực thi, nguy cơ timeout |
| Errors | Error count, failure rate, timeout rate | Chất lượng xử lý |
| Concurrency | Concurrent executions, reserved/provisioned capacity | Sức ép tài nguyên và giới hạn |
| Cold start | Cold-start count/duration (nếu nền tảng xuất metric) | Tác động khi instance khởi tạo |
| Queue | Depth, oldest message age, DLQ count | Backlog và độ trễ xử lý bất đồng bộ |
| Database | Connections, throttling, latency, capacity | Phụ thuộc dữ liệu |
| Business | Orders completed, payment success, report completed | Kết quả mà người dùng quan tâm |
| Cost | Cost per successful transaction, log bytes, egress | Hiệu quả kinh tế |

Metrics hạ tầng không thay thế metrics nghiệp vụ. Function có error rate 0% nhưng có thể trả thành công với kết quả sai hoặc ghi đơn ở trạng thái không mong muốn. Cần metric xác nhận **đơn hoàn tất hợp lệ**.

### 7.3. Logs: sự kiện có ngữ cảnh

Log nên có cấu trúc nhất quán, ví dụ:

~~~json
{
  "timestamp": "2026-11-18T02:04:05Z",
  "level": "ERROR",
  "service": "booking-worker",
  "function_version": "42",
  "invocation_id": "invoke-7f1a",
  "correlation_id": "corr-8e1c",
  "order_id": "order-1842",
  "tenant_id": "tenant-12",
  "event": "inventory_reservation_failed",
  "error_type": "DownstreamTimeout",
  "retry_attempt": 2
}
~~~

Đây là cấu trúc minh họa. Tránh ghi access token, secret, dữ liệu thanh toán hoặc toàn bộ thông tin cá nhân. Nếu tenant ID hoặc order ID có thể nhận dạng cá nhân trong bối cảnh cụ thể, cần áp dụng policy bảo vệ phù hợp.

Nên phân biệt log của ứng dụng, log nền tảng, audit log và access log. Mỗi loại có mục đích, quyền truy cập và thời gian lưu khác nhau.

### 7.4. Tracing: nối các bước phân tán

Một distributed trace gồm các span có parent/child relationship. Trace context cần được truyền qua HTTP header và message metadata. Nếu message queue hoặc trigger không tự truyền W3C Trace Context, ứng dụng có thể đưa context cần thiết vào message attribute theo cách an toàn.

Trace giúp xác định thời gian ở function, database, queue, external call và thời gian chờ. Nhưng tracing không lưu giữ mọi sự kiện nghiệp vụ vô thời hạn; cần kết hợp log và audit có retention phù hợp.

Khi sampling, hãy cân nhắc:

- Head sampling theo tỷ lệ cho traffic bình thường.
- Tail sampling giữ trace có lỗi, latency cao hoặc thuộc loại giao dịch quan trọng.
- Sampling nhất quán giữa các service để tránh trace bị thiếu đoạn.
- Bảo vệ dữ liệu nhạy cảm và giới hạn chi phí collector/backend.

## 8. Dashboard và cảnh báo theo hành trình nghiệp vụ

Một dashboard hiệu quả nên trả lời bốn câu hỏi:

1. **Người dùng có hoàn tất giao dịch không?** Booking success rate, payment confirmation, p95/p99.
2. **Hệ thống đang nghẽn ở đâu?** Function duration, throttling, DB latency, queue age, external dependency.
3. **Có tác vụ nào bị bỏ sót hoặc trì hoãn?** Job age, DLQ, schedule missed, retry rate.
4. **Chi phí tăng vì đâu?** Invocation, duration, network, DB operations, log ingestion và chi phí mỗi giao dịch.

Cảnh báo cần dựa trên tác động hoặc hành vi bất thường có thể hành động. Ví dụ:

- Tỷ lệ booking hợp lệ thành công thấp hơn SLO trong cửa sổ đã định.
- API p99 vượt ngưỡng kéo dài.
- Function throttled liên tục hoặc tỷ lệ timeout tăng.
- Tuổi message cũ nhất vượt thời hạn nghiệp vụ.
- DLQ xuất hiện message mới hoặc tăng nhanh.
- Không có báo cáo đúng lịch.
- Chi phí hoặc log ingest tăng vượt baseline/budget.
- Database connection/concurrency đạt ngưỡng sắp gây lỗi dây chuyền.

Tránh alert trên mọi invocation lỗi đơn lẻ nếu nó tạo nhiễu. Dùng cửa sổ đánh giá, điều kiện duy trì và cảnh báo theo mức độ nghiêm trọng; có runbook và người chịu trách nhiệm cho mỗi alert.

## 9. Những ràng buộc nền tảng cần đánh giá

Serverless có nhiều giới hạn khác nhau theo từng dịch vụ. Một thiết kế phải đọc tài liệu và quota hiện hành của nền tảng đích, kiểm thử với cấu hình thực tế và ghi lại giới hạn quan trọng. Không thể giả định mọi FaaS có cùng giới hạn runtime hay semantics.

### 9.1. Thời gian thực thi và loại công việc

Một function có thể bị giới hạn thời gian chạy tối đa. Job vượt giới hạn cần chia thành bước nhỏ, orchestration, queue hoặc dùng container/batch phù hợp. Timeout không đồng nghĩa side effect chưa xảy ra; retry vẫn có thể giao công việc lại.

Các câu hỏi:

- Thời gian chạy tối đa của invocation là bao nhiêu?
- Có hỗ trợ job dài hoặc execution bất đồng bộ không?
- Khi bị timeout, platform có thể hủy process ngay hay chỉ dừng theo policy?
- Có graceful shutdown và checkpoint không?
- Workload cần CPU/GPU, memory hoặc thư viện hệ điều hành nào?

### 9.2. Cold start và latency

Cold start là thời gian khởi tạo môi trường thực thi trước khi xử lý invocation. Nó có thể chịu ảnh hưởng bởi runtime, kích thước artifact, dependency, VPC/network initialization, concurrency spike và cấu hình nền tảng.

Các cách giảm tác động:

- Giảm dependency và kích thước package.
- Khởi tạo SDK/client hiệu quả, tái sử dụng execution environment khi nền tảng cho phép.
- Dùng provisioned/minimum concurrency nếu lợi ích latency đáng chi phí.
- Tách tác vụ nặng khỏi synchronous request path.
- Đo p95/p99 với cả tải đều và burst; không dựa vào một lần gọi warm.

Giữ sẵn capacity có thể giảm cold start nhưng phát sinh chi phí kể cả khi traffic thấp. Quyết định dựa trên SLO latency và giá trị nghiệp vụ.

### 9.3. Concurrency, throttling và quota

Concurrency là số execution đồng thời. Giới hạn có thể ở cấp account, function, region hoặc dịch vụ downstream. Burst traffic có thể khiến platform scale nhanh hơn khả năng database hoặc API bên ngoài chịu tải.

Cần:

- Reserved/concurrency limit hoặc cơ chế tương đương cho workload quan trọng.
- Giới hạn concurrency ở consumer và kết nối DB.
- Queue buffering và backpressure cho công việc có thể chờ.
- Rate limit tới payment, ERP và external API.
- Capacity plan cho burst, cold start và quota tăng.
- Test quota exhaustion để xem phản hồi, retry và cảnh báo.

Autoscaling không phải vô hạn. Nếu nhiều function tăng concurrency cùng lúc, database có thể hết connection trước khi compute gặp giới hạn.

### 9.4. Payload, event và storage tạm

Nền tảng thường giới hạn kích thước request/response, event, environment variables hoặc message. Dữ liệu lớn nên lưu trong object storage/database và truyền reference/key, thay vì đóng gói vào event.

Filesystem cục bộ thường có tính tạm thời và có thể biến mất khi environment bị thay thế. Không lưu trạng thái job, khóa idempotency hoặc file cần tồn tại lâu dài tại thư mục tạm mà không có cơ chế persist.

### 9.5. Runtime, ngôn ngữ và dependency

Nền tảng có thể chỉ hỗ trợ một tập runtime/phiên bản, thời gian hỗ trợ và cách cài binary khác nhau. Một package dùng thư viện native, extension, font hoặc executable có thể hoạt động trong local container nhưng thất bại trong runtime serverless.

Đánh giá:

- Runtime/ABI và vòng đời phiên bản.
- Kích thước deploy artifact/layer.
- Dependency native và kiến trúc CPU (x86/ARM).
- Cách kiểm thử tương đồng giữa local, CI và production.
- Quy trình nâng cấp runtime và xử lý end-of-support.

### 9.6. Networking và kết nối riêng

Function đặt trong private network có thể truy cập database private, nhưng cấu hình network có thể ảnh hưởng cold start, throughput, IP capacity và NAT/egress cost. Một số nền tảng có mô hình kết nối VPC riêng, endpoint hoặc giới hạn số interface/connection.

Cần kiểm tra:

- Có cần outbound Internet không? Có thể dùng private endpoint?
- Source IP/egress IP có cố định cần allowlist không?
- Có hỗ trợ kết nối lâu dài tới database hay phải quản lý pool?
- DNS resolution trong private zone có đúng không?
- Security group/firewall và route có đủ cả hai chiều?
- Egress, NAT và cross-zone traffic được tính phí như thế nào?

Không mở toàn bộ subnet cho function chỉ để giải quyết lỗi kết nối. Xác định đúng đích, port, identity và luồng cần truy cập.

### 9.7. Storage, state và kết nối dài hạn

Function thường phù hợp với execution stateless. State nên đặt ở database, object storage, cache, queue hoặc state store phù hợp. Nếu workload cần WebSocket lâu dài, long-running session, process nền liên tục hoặc connection pool ổn định, cần chọn dịch vụ hỗ trợ rõ đặc điểm đó; có thể dùng managed gateway/service kết hợp compute khác.

Không để mỗi invocation tạo mới quá nhiều database connection. Tái sử dụng client khi environment được giữ lại có thể giảm overhead, nhưng phải xử lý connection hết hạn và không dựa vào việc environment luôn sống.

### 9.8. Quan sát, debug và giới hạn môi trường

Runtime managed có thể giới hạn quyền truy cập host, debugger, file system, process và network. Log có thể được gửi bất đồng bộ; timestamp, cold start và invocation ID cần được dùng đúng khi ghép sự kiện.

Cần thử khả năng:

- Correlate request và message giữa các function.
- Capture timeout, throttling và platform-level error.
- Debug lỗi chỉ xuất hiện khi scale concurrency.
- Truy xuất audit/config changes theo quyền.
- Xuất metric/log sang hệ thống quan sát chung mà không phát sinh chi phí không kiểm soát.

## 10. Ràng buộc theo nhà cung cấp và vendor lock-in

### 10.1. Nơi lock-in thường xuất hiện

Lock-in không chỉ nằm ở cú pháp function handler. Nó có thể xuất hiện trong:

- Event trigger, event filtering và delivery semantics.
- IAM policy, role assumption và danh tính service-to-service.
- Managed workflow, state machine và cách retry.
- Database, query API, indexing và transaction semantics.
- API gateway, authorizer, routing và WAF integration.
- Object storage event, lifecycle và notification.
- VPC integration, private endpoints và network policy.
- Logging/metrics/tracing và cách truy vấn dữ liệu.
- Deployment package, runtime, layer và secret format.

Dùng giao diện HTTP, JSON, SQL hoặc container không tự làm toàn bộ ứng dụng portable. Khác biệt semantics của event, timeout, retry, transaction và IAM vẫn có thể tạo lock-in.

### 10.2. Đánh giá mức phụ thuộc có chủ đích

Có thể lập bảng dependency register:

| Thành phần | Dịch vụ/chuẩn đang dùng | Mức ảnh hưởng nếu chuyển | Cách giảm rủi ro |
| --- | --- | --- | --- |
| Compute | FaaS runtime cụ thể | Phải chuyển handler, runtime, packaging và timeout model | Domain logic độc lập; adapter ở biên |
| Event | Event bus managed | Chuyển rule, routing và delivery semantics | Event contract rõ, schema versioning |
| Workflow | Managed state machine | Chuyển orchestration, retry và state | Tách business state; tài liệu hóa workflow |
| Data | Managed database | Export schema/data, đổi query/consistency | Backup/export test, ownership và data contract |
| Identity | IAM riêng provider | Viết lại role/policy, trust và auth flow | Federation/standard protocol nơi phù hợp |
| Observability | Logging/tracing vendor | Di chuyển dashboard, alert, retention và query | OpenTelemetry, log schema, export path |
| Network | VPC endpoint và private routing | Thay IP/routing/security configuration | IP plan, IaC module theo interface |

Mục tiêu không phải loại bỏ mọi lock-in. Dịch vụ đặc thù có thể giảm đáng kể công sức vận hành và cải thiện độ tin cậy. Cần biết lock-in nằm ở đâu, lợi ích hiện tại là gì, và chi phí thoát nền tảng khi có lý do chuyển.

### 10.3. Mức độ portability

Có thể chia khả năng chuyển đổi thành ba mức:

1. **Code portability:** có thể build và chạy logic trong runtime khác với thay đổi nhỏ.
2. **Operational portability:** có thể triển khai, cấp quyền, quan sát, scale và xử lý sự cố trên môi trường khác.
3. **Data and workflow portability:** có thể di chuyển dữ liệu, event semantics, state và khôi phục lịch sử công việc.

Một container chạy được ở hai cloud chỉ chứng minh một phần code/runtime portability; không chứng minh IAM, managed database, event trigger và DR có thể chuyển nguyên trạng.

## 11. Thiết kế abstraction vừa đủ

### 11.1. Đặt ranh giới tại dependency dễ thay đổi

Ứng dụng Java có thể định nghĩa interface cho thao tác nghiệp vụ, rồi triển khai bằng adapter cụ thể:

~~~java
public interface InvoicePublisher {
    PublishResult publish(InvoiceEvent event);
}

public final class BillingUseCase {
    private final InvoicePublisher publisher;

    public BillingUseCase(InvoicePublisher publisher) {
        this.publisher = publisher;
    }

    public void execute(InvoiceEvent event) {
        publisher.publish(event);
    }
}
~~~

Adapter có thể dùng managed event service hiện tại, còn logic nghiệp vụ không phải import SDK cụ thể. Tuy nhiên, abstraction chỉ nên che các khác biệt mà ứng dụng thực sự cần thay thế. Đừng tạo một lớp wrapper tổng quát bao trùm mọi chức năng cloud rồi làm mất các tính năng quan trọng của nền tảng.

### 11.2. Giữ contract và semantics rõ

- Schema event có version và quy tắc tương thích.
- Định nghĩa ordering, duplicate, retry, retention và failure semantics.
- Không truyền object của SDK qua domain/application.
- Tách business state khỏi workflow execution metadata.
- Thiết kế idempotency theo business key.
- Có integration test với adapter và contract test cho producer/consumer.

Một interface chung không thể che giấu được việc một queue chỉ đảm bảo ordering theo partition, còn hệ khác không. Khi abstraction bỏ qua semantics, lỗi thường chỉ xuất hiện lúc di chuyển hoặc chịu tải thật.

### 11.3. Kiểm tra khả năng thoát bằng thử nghiệm

Một kế hoạch portability chỉ có giá trị nếu đã thử:

1. Build ứng dụng trong pipeline thay thế.
2. Deploy một workload nhỏ trên nền tảng đích.
3. Cấp IAM, network, secret và observability.
4. Replay một tập event dữ liệu thử.
5. Export/restore database và xác minh tính toàn vẹn.
6. Chạy load/failure test.
7. Đo chi phí, thời gian và phần mã phải thay đổi.

Có thể kiểm tra một lát cắt nhỏ mỗi quý hoặc khi thay đổi nền tảng lớn, thay vì đợi đến khi quyết định di chuyển toàn hệ thống mới phát hiện phụ thuộc.

## 12. Kịch bản chất lượng và SLO cho serverless

Một kịch bản chất lượng cần nêu nguồn tác động, stimulus, môi trường, thành phần, phản hồi và thước đo. Các ngưỡng dưới đây chỉ là **ví dụ học tập**.

| Mã | Tình huống | Phản hồi kỳ vọng | Thước đo minh họa |
| --- | --- | --- | --- |
| QA-COST-01 | Lưu lượng tăng 5 lần trong đợt khuyến mãi | Compute mở rộng nhưng không tạo chi phí bất thường hoặc quá tải DB | Cost per successful booking trong budget; DB connections dưới giới hạn |
| QA-OBS-01 | Một message đi qua API, queue và hai function | Người trực truy vết được toàn hành trình | 99% message hợp lệ có correlation ID; trace tìm được qua các bước |
| QA-LAT-01 | Function nhận burst sau thời gian idle | Hệ thống giữ độ trễ trong mục tiêu | p95/p99 toàn request path dưới ngưỡng trong load test |
| QA-REL-01 | Function timeout sau khi side effect đã xảy ra | Retry không tạo giao dịch trùng | Không có booking/payment duplicate trong bộ kiểm thử |
| QA-PLAT-01 | Quota concurrency đạt giới hạn | Hệ thống backpressure, không mất message | Throttle được cảnh báo; oldest message age trong giới hạn |
| QA-EXIT-01 | Cần chuyển một chức năng event-driven sang runtime khác | Dữ liệu/contract có thể export và xử lý lại | Prototype hoàn tất trong thời hạn/chi phí đã chấp nhận |
| QA-SEC-01 | Function tenant A cố đọc dữ liệu tenant B | Từ chối và audit | 100% ca trái phép trong bộ test bị chặn |

SLO cần chỉ rõ điểm đo và cửa sổ quan sát. p95 của function duration không bằng p95 end-to-end của API vì chưa tính API gateway, queue, database và downstream.

## 13. Một dashboard serverless nên có gì?

Một dashboard theo workload nên có các vùng:

| Vùng | Nội dung |
| --- | --- |
| Business outcome | Số booking/payment thành công, tỷ lệ hoàn tất, lỗi nghiệp vụ |
| Request path | Request rate, p50/p95/p99, HTTP error, timeout |
| Function health | Invocation, duration, error, throttle, concurrency, cold-start indicators |
| Async processing | Queue depth, oldest age, retry, DLQ, job duration |
| Dependencies | DB connection/latency, external API error, network/egress |
| Observability health | Log ingest, dropped traces, collector/backend error |
| Cost | Cost by function, service, tenant/workload, cost per successful transaction |
| Governance | Runtime version, deprecated version, policy violation, quota utilization |

Có thể tổ chức một dashboard tổng quan cấp sản phẩm, sau đó liên kết tới dashboard function, event pipeline, database và cost. Người trực phải bắt đầu từ câu hỏi **người dùng đang gặp vấn đề gì**, không phải từ danh sách hàng chục metric platform.

## 14. Quản lý chi phí và guardrail

### 14.1. Budget, alert và anomaly detection

Đặt ngân sách theo workload, môi trường hoặc team. Cảnh báo ở nhiều ngưỡng trước khi vượt ngân sách; nhận diện tăng bất thường của invocation, duration, egress, DB operations và log ingest.

Cần có hành động cụ thể khi cảnh báo: giảm log level debug, giới hạn traffic không quan trọng, dừng test load không được phê duyệt, giảm concurrency hoặc chuyển workload sang chế độ suy giảm. Không tự động tắt một function thanh toán/đặt đơn quan trọng chỉ vì một threshold tài chính không có phân tích rủi ro.

### 14.2. Cost allocation và tagging

Áp dụng tag/label thống nhất như application, environment, team, owner, cost-center và data-classification. Tách account/project cho production, staging và development khi phù hợp; dùng budgets/quota để ngăn test workload gây chi phí production-like không kiểm soát.

Chi phí log và egress thường bị bỏ quên vì không nằm trên dòng compute. Đặt dashboard theo từng cost category và theo dõi biến động so với lượng giao dịch.

### 14.3. Tối ưu đúng chỗ

Một số cách tối ưu:

- Giảm số invocation không cần thiết bằng batch/bulk API khi nghiệp vụ cho phép.
- Tránh fan-out function cho từng bản ghi nhỏ nếu có thể gom nhóm.
- Đưa tác vụ không cần phản hồi tức thì sang queue.
- Dùng cache có TTL/invalidation đúng để giảm database calls.
- Điều chỉnh memory/CPU theo benchmark, không chỉ chọn cấu hình nhỏ nhất.
- Giảm dependency/package size khi cold start là vấn đề đã đo được.
- Chọn log retention/sampling theo mục đích.
- Dọn object tạm, DLQ và dữ liệu job theo lifecycle.
- Chống retry storm và giới hạn downstream concurrency.

Tối ưu phải giữ SLO, tính đúng đắn và security; một thay đổi làm giá giảm nhưng gây double booking hoặc mất audit không phải tối ưu chấp nhận được.

## 15. Rủi ro vận hành và phương án phản ứng

| Rủi ro | Triệu chứng | Biện pháp |
| --- | --- | --- |
| Cold start tăng | p95/p99 tăng sau idle hoặc burst | Benchmark, provisioned capacity nếu đáng chi phí, giảm package |
| Concurrency spike | Throttling, database hết connection | Concurrency cap, queue, backpressure |
| Timeout và retry storm | Invocation tăng, downstream chậm, backlog lớn | Timeout budget, backoff/jitter, DLQ, circuit breaker |
| Log bùng nổ | Chi phí ingest tăng, dashboard chậm | Sampling/log level/retention và alert |
| Event duplicate | Side effect lặp | Idempotency và unique business key |
| Quota thiếu | Deploy/invocation bị từ chối | Capacity forecast, quota alert/request và graceful degradation |
| Runtime end-of-support | Không thể cập nhật hoặc có rủi ro bảo mật | Inventory runtime, lịch nâng cấp và test tương thích |
| Vendor service thay đổi | Trigger/permission/behavior đổi | IaC review, contract test, release note review |
| Khó điều tra xuyên function | Không nối được log của một giao dịch | Correlation ID, trace propagation và structured logs |
| Chi phí egress bất ngờ | Bill tăng khi gọi cross-region/provider | Data-flow map, egress dashboard và placement review |

## 16. Case study: nền tảng đặt phòng serverless

### 16.1. Bối cảnh

Một công ty triển khai API đặt phòng theo mô hình serverless. Người dùng gọi API qua gateway; function xác thực, kiểm tra dữ liệu và ghi booking; event được đưa vào queue để gửi email và cập nhật hệ thống phân tích.

Yêu cầu giả định:

- 300.000 booking thành công/tháng.
- p95 API tạo booking không quá 500 ms trong tải mục tiêu.
- Email được thử gửi trong vòng 2 phút sau khi booking xác nhận.
- Retry không tạo booking hoặc email trùng.
- Chi phí nền tảng thuộc ngân sách đã được phê duyệt.
- Người trực có thể truy vết một booking qua API, queue, worker và email provider.

### 16.2. Kiến trúc và quan sát

~~~mermaid
flowchart LR
    USER["Web / Mobile"] --> GW["API Gateway"]
    GW --> F1["Booking Function"]
    F1 --> DB[("Booking DB")]
    F1 --> OUTBOX["Outbox / Event"]
    OUTBOX --> Q[("Queue")]
    Q --> F2["Notification Function"]
    F2 --> EMAIL["Email provider"]
    GW -. metrics / trace .-> OBS["Observability"]
    F1 -. logs / trace .-> OBS
    F2 -. logs / trace .-> OBS
    DB -. metrics .-> OBS
    Q -. queue age / DLQ .-> OBS
~~~

Mỗi booking lưu correlation ID, còn job notification có job/event ID riêng. Trace context được truyền qua message metadata; business ID dùng để truy vấn trạng thái nghiệp vụ.

### 16.3. Mô hình chi phí mẫu

Giả sử 300.000 booking/tháng có chi phí giả định:

| Thành phần | Triệu VND/tháng |
| --- | ---: |
| Booking function + gateway | 22 |
| Database/cache | 28 |
| Queue/event + notification function | 10 |
| Network/egress | 5 |
| Logs/metrics/traces | 8 |
| Security/KMS/audit | 4 |
| **Tổng** | **77** |

~~~text
Cost per successful booking
  = 77.000.000 / 300.000
  ≈ 257 VND / booking
~~~

Nếu lượng booking giảm một nửa, compute có thể giảm nhưng database minimum capacity, provisioned concurrency, log retention và các phí nền tảng cố định có thể không giảm tương ứng. Nếu traffic tăng năm lần, cần xem quota, concurrency và downstream DB; chi phí không nhất thiết chỉ tăng tuyến tính theo function invocation.

### 16.4. Các phát hiện qua dashboard

Giả sử dashboard cho thấy booking API vẫn trả thành công nhưng oldest queue message age tăng từ 20 giây lên 4 phút. Điều đó cho thấy trải nghiệm đặt booking chưa nhất thiết lỗi, nhưng thông báo đang trễ và SLO notification sắp vi phạm.

Đội vận hành kiểm tra notification function duration, throttles, email provider latency và concurrency. Nếu downstream rate limit là nguyên nhân, tăng worker ngay có thể làm tình hình xấu thêm. Cần giữ concurrency trong quota, backoff có jitter, theo dõi retry và làm rõ trạng thái email trong job store.

### 16.5. Kiểm tra ràng buộc nền tảng

Trước production, đội thử:

- Burst traffic và cold start với artifact thật.
- Quota/concurrency ở region dự định triển khai.
- Timeout khi database/email provider phản hồi chậm.
- Database connection sau nhiều invocation đồng thời.
- Payload/message size ở luồng report.
- Log/trace context sau queue trigger.
- Runtime upgrade trong staging.
- Export dữ liệu và dựng một prototype worker ở môi trường thay thế.

Kết quả thử nghiệm cung cấp căn cứ quyết định có cần provisioned capacity, worker container cho job dài hoặc phương án giảm lock-in ở một số thành phần không.

## 17. Checklist đánh giá nền tảng serverless

### Chi phí

- [ ] Đã tính invocation, duration, memory/CPU và capacity giữ sẵn.
- [ ] Đã tính database, queue, object storage, API gateway, egress và private networking.
- [ ] Đã tính log/trace ingest, retention, security và audit.
- [ ] Đã tính retry, failure, DLQ, replay và thao tác thủ công.
- [ ] Có cost per successful transaction và kịch bản tải thấp/kỳ vọng/đỉnh.
- [ ] Có budget, tag/label, cost allocation và cảnh báo bất thường.

### Khả năng quan sát

- [ ] Có SLI/SLO ở cấp nghiệp vụ và request path.
- [ ] Có structured logs, correlation ID và trace propagation qua event.
- [ ] Có metrics invocation, duration, throttle, concurrency, cold start indicator.
- [ ] Có queue depth, oldest age, retry, DLQ và expected-run monitor.
- [ ] Có dashboard, alert, runbook và người sở hữu.
- [ ] Có kiểm soát cardinality, sampling, retention và dữ liệu nhạy cảm.

### Ràng buộc nền tảng

- [ ] Đã kiểm tra runtime, thời gian thực thi, memory/CPU và artifact size.
- [ ] Đã kiểm tra cold start, concurrency, timeout, payload và quota.
- [ ] Đã kiểm tra VPC/private networking, DNS, egress và DB connections.
- [ ] Đã kiểm tra filesystem tạm, state, connection lifecycle và graceful shutdown.
- [ ] Đã kiểm tra event delivery, ordering, retry, retention và trigger semantics.
- [ ] Có lịch nâng cấp runtime và quy trình xử lý deprecation.
- [ ] Có dependency register, ADR và thử nghiệm portability/exit.
- [ ] Có test tải, fault injection, security và restore trước production.

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi đánh giá serverless |
| --- | --- |
| **Operational Excellence** | Đội ngũ có theo dõi job/request xuyên function, runbook, IaC và quy trình nâng cấp runtime không? |
| **Security** | Function có quyền tối thiểu, secret protection, tenant isolation và audit phù hợp không? |
| **Reliability** | Retry, idempotency, DLQ, timeout, quota và dependency failure đã được kiểm thử chưa? |
| **Performance Efficiency** | Cold start, concurrency, memory, network và database có đáp ứng p95/p99 ở tải thực không? |
| **Cost Optimization** | Chi phí toàn tuyến và mỗi giao dịch có nằm trong ngân sách ở mọi kịch bản tải không? |
| **Sustainability** | Có giảm compute nhàn rỗi, log không cần thiết, xử lý lặp và truyền dữ liệu thừa không? |

## 19. Bài tập thực hành

Một dịch vụ quản lý hóa đơn dự kiến chạy serverless. Mỗi tháng có 2 triệu yêu cầu tạo hóa đơn; cuối tháng có batch đối soát lớn. API phải trả xác nhận trong 700 ms p95; hóa đơn PDF được tạo trong nền và sẵn sàng tải trong 3 phút; người vận hành phải truy vết được một hóa đơn qua API, queue và worker. Ngân sách có giới hạn và tổ chức có khả năng chuyển nền tảng trong tương lai.

Hãy thực hiện:

1. Phân rã chi phí compute, gateway, database, object storage, queue, network, observability và security.
2. Lập cost per successful invoice với ba kịch bản volume; tính cả retry và hóa đơn thất bại.
3. So sánh function event-driven với container worker chạy thường trực cho bước tạo PDF.
4. Thiết kế dashboard metrics/logs/traces có correlation ID từ API qua queue đến worker.
5. Xác định các cảnh báo về p95, throttling, oldest message age, DLQ, cost spike và missed batch.
6. Lập danh sách platform constraints: timeout, payload, runtime, memory, concurrency, quota, filesystem và network.
7. Chỉ ra ba vị trí vendor lock-in lớn nhất; đề xuất abstraction nào có ích và abstraction nào gây dư thừa.
8. Thiết kế một thử nghiệm chuyển một worker sang runtime/container khác, gồm dữ liệu, IAM, network, observability và load test.
9. Viết ADR lựa chọn phương án, chỉ số đo, rủi ro tồn dư và điều kiện xem xét lại.

**Gợi ý tự đánh giá:** Một phương án đạt yêu cầu khi không chỉ nêu giá function hoặc hứa “serverless tự scale”, mà giải thích được toàn bộ cost path, khả năng truy vết, quota và giới hạn của dịch vụ, cùng bằng chứng thử nghiệm.

## Kết luận

Serverless có thể giảm công sức quản lý máy chủ và phù hợp với workload event-driven, bursty hoặc có mức sử dụng không đều. Giá trị đó chỉ được chứng minh khi **TCO toàn tuyến** phù hợp, đội ngũ có thể quan sát hành trình nghiệp vụ và những giới hạn nền tảng không phá vỡ SLO.

Hãy đo chi phí trên giao dịch thành công, quản trị log/trace theo mục tiêu, kiểm soát concurrency và quota, hiểu semantics của event/retry, và ghi nhận các phụ thuộc nhà cung cấp. Khi cần portability, hãy thử export, deploy và vận hành một lát cắt thực tế thay vì chỉ dựa vào interface chung hoặc tuyên bố container hóa. Quyết định cuối cùng cần cân bằng độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành theo tinh thần Well-Architected.
