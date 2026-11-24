# Thiết kế hàm theo nghiệp vụ và lựa chọn kích thước đơn vị xử lý

Serverless function thường được triển khai nhanh, tự động mở rộng và tính phí theo lần gọi hoặc tài nguyên-thời gian. Nhưng nếu chia ứng dụng thành quá nhiều function nhỏ, hệ thống có thể phát sinh nhiều lần gọi mạng, khó theo dõi giao dịch và tăng chi phí điều phối. Nếu gom quá nhiều nghiệp vụ vào một function lớn, code trở nên khó kiểm thử, thời gian thực thi dài, quyền truy cập rộng và một lỗi có thể ảnh hưởng nhiều luồng nghiệp vụ.

Thiết kế tốt bắt đầu từ **năng lực nghiệp vụ** mà hệ thống cần cung cấp, sau đó chọn ranh giới function, loại trigger và kích thước đơn vị công việc phù hợp. Một function nên có trách nhiệm rõ, đầu vào/đầu ra ổn định và giới hạn tài nguyên có thể đo được. Đơn vị xử lý có thể là một request, một bản ghi, một tài liệu, một message, một batch hoặc một partition; chọn sai kích thước sẽ làm tăng overhead, độ trễ, retry hoặc nguy cơ vượt giới hạn nền tảng.

Bài học này trình bày cách phân rã nghiệp vụ thành function, cách chọn kích thước công việc và cấu hình compute, cách tổ chức orchestration, trạng thái, lỗi và bảo mật, cùng ví dụ thực tế để cân bằng khả năng bảo trì, hiệu năng, độ tin cậy và chi phí.

## 1. Hai quyết định thiết kế cần tách biệt

Khi thiết kế serverless, có hai câu hỏi khác nhau:

1. **Function chịu trách nhiệm nghiệp vụ nào?** Đây là ranh giới chức năng và quyền sở hữu logic.
2. **Mỗi invocation xử lý bao nhiêu công việc?** Đây là kích thước đơn vị xử lý ở runtime.

Ví dụ, một function có trách nhiệm tạo thumbnail ảnh. Ranh giới nghiệp vụ là "tạo thumbnail". Nhưng một invocation có thể xử lý một ảnh, một batch 10 ảnh hoặc một message đại diện cho một lô ảnh. Không cần tạo function mới chỉ vì muốn đổi batch size.

### Ranh giới nghiệp vụ

Ranh giới này xác định:
- Function làm nhiệm vụ gì.
- Sự kiện hoặc request nào kích hoạt nó.
- Dữ liệu đầu vào và đầu ra.
- Quyền truy cập cần thiết.
- Các side effect được phép.
- Ai sở hữu và thay đổi logic.
- Điều kiện thành công, thất bại và retry.

### Kích thước đơn vị xử lý

Kích thước đơn vị xử lý xác định:
- Một invocation xử lý một hay nhiều item.
- Kích thước payload và working set.
- Thời gian thực thi dự kiến.
- Số lượng I/O và lời gọi dependency.
- Bộ nhớ, CPU và ephemeral storage cần dùng.
- Mức độ song song và số invocation đồng thời.
- Phạm vi công việc bị retry khi có lỗi.

Hai quyết định có liên quan nhưng không thay thế nhau. Một function có ranh giới nghiệp vụ tốt vẫn có thể chọn batch quá lớn; một batch nhỏ không sửa được function có trách nhiệm nghiệp vụ lẫn lộn.

## 2. Bắt đầu từ năng lực nghiệp vụ

Năng lực nghiệp vụ mô tả một khả năng mà tổ chức hoặc sản phẩm cần cung cấp, chẳng hạn:
- Nhận đơn hàng.
- Xác nhận thanh toán.
- Kiểm tra tồn kho.
- Gửi thông báo.
- Xử lý tài liệu.
- Tạo báo cáo.
- Cập nhật trạng thái giao hàng.

Một function nên phục vụ một bước nghiệp vụ có ý nghĩa và có thể diễn đạt rõ bằng động từ cùng đối tượng. Ví dụ: `validate-order`, `reserve-inventory`, `generate-thumbnail` hoặc `send-invoice-notification`.

Không nhất thiết mỗi năng lực nghiệp vụ chỉ có một function. Một năng lực lớn có thể được triển khai bằng nhiều function cộng với workflow điều phối. Ngược lại, một function có thể chứa nhiều thao tác kỹ thuật nhỏ nếu chúng cùng phục vụ một trách nhiệm và cần hoàn tất như một đơn vị.

### Dùng câu hỏi để xác định ranh giới

Với mỗi function dự kiến, hãy trả lời:

- Nếu function thất bại, nghiệp vụ nào cần thử lại?
- Nếu thay đổi quy tắc nghiệp vụ, có cần triển khai function khác không?
- Function có cần quyền truy cập dữ liệu của nhiều domain không?
- Đầu vào có ổn định và có thể version không?
- Kết quả có thể được kiểm tra độc lập không?
- Có thể chạy function nhiều lần mà không gây tác động lặp không?
- Có một nhóm hoặc service owner rõ ràng chịu trách nhiệm không?

Nếu một function vừa xác nhận đơn hàng, trừ tồn kho, tính phí, tạo vận đơn và gửi email, một lỗi email có thể khiến caller retry toàn bộ giao dịch. Những bước này có failure mode và consistency khác nhau; thường nên tách thành các bước nghiệp vụ có ranh giới rõ và điều phối bằng workflow hoặc event.

## 3. Cohesion, coupling và kích thước function

### Cohesion

Cohesion là mức độ các phần bên trong cùng phục vụ một mục đích. Function có cohesion cao thường:
- Có một lý do chính để thay đổi.
- Có đầu vào/đầu ra tương đối nhỏ và rõ.
- Có quyền truy cập giới hạn.
- Có thể kiểm thử theo một kết quả nghiệp vụ.
- Có thể quan sát bằng một tập metric và log nhất quán.

### Coupling

Coupling là mức phụ thuộc giữa các function hoặc domain. Một function gọi trực tiếp nhiều function khác có thể tạo chuỗi phụ thuộc đồng bộ, làm tăng latency và failure propagation.

Giảm coupling bằng:
- Event contract có version.
- API contract ổn định.
- Durable queue hoặc event bus.
- Workflow orchestration khi cần trạng thái và nhánh điều kiện.
- Idempotency và retry có kiểm soát.
- Không chia sẻ database table nội bộ giữa các domain nếu có thể dùng contract.

### Tránh hai cực đoan

| Thiết kế | Vấn đề |
|---|---|
| Một function xử lý toàn bộ hệ thống | Khó kiểm thử, quyền rộng, deploy ảnh hưởng nhiều nghiệp vụ, timeout và memory lớn |
| Một function cho từng dòng lệnh hoặc thao tác nhỏ | Quá nhiều network hop, orchestration phức tạp, logging và cost tăng |
| Function theo bước nghiệp vụ rõ | Dễ sở hữu, kiểm thử và retry theo kết quả; vẫn cần kiểm soát contract và state |

Không có số dòng code hoặc số function tối ưu chung. Chọn kích thước dựa trên trách nhiệm nghiệp vụ, boundary giao dịch, failure isolation và chi phí giao tiếp.

## 4. Chọn kiểu kiến trúc: request-driven, event-driven hay workflow

### Request-driven function

Function được gọi trực tiếp qua HTTP/API hoặc SDK. Phù hợp khi caller cần phản hồi ngay.

Ví dụ:
- Tra cứu thông tin.
- Kiểm tra dữ liệu đầu vào.
- Tạo yêu cầu xử lý và trả job ID.
- Một thao tác ngắn có kết quả tức thời.

Cần đặt deadline, timeout và response contract. Không nên giữ một request đồng bộ mở trong thời gian dài nếu công việc có thể chạy nền.

### Event-driven function

Function được kích hoạt bởi event từ object storage, queue, stream, database change feed hoặc event bus.

Phù hợp khi:
- Producer không cần chờ consumer hoàn tất.
- Có thể retry độc lập.
- Workload đến theo burst.
- Cần hấp thụ tải bằng queue.
- Các domain cần tách rời thời điểm triển khai.

Event cần có event ID, schema version, source, timestamp và correlation ID khi phù hợp.

### Workflow orchestration

Khi một nghiệp vụ có nhiều bước, nhánh điều kiện, retry, timeout, compensation hoặc chờ người dùng, dùng workflow engine hoặc state machine để điều phối.

Ví dụ:

~~~mermaid
flowchart TD
    A["Nhận đơn hàng"] --> B["Validate order"]
    B --> C{"Hợp lệ?"}
    C -->|Không| X["Trả lỗi nghiệp vụ"]
    C -->|Có| D["Reserve inventory"]
    D --> E{"Đã giữ hàng?"}
    E -->|Không| Y["Thông báo hết hàng"]
    E -->|Có| F["Authorize payment"]
    F --> G{"Thanh toán thành công?"}
    G -->|Không| H["Release inventory"]
    G -->|Có| I["Confirm order"]
    I --> J["Publish order-confirmed event"]
    J --> K["Notification function"]
~~~

Mỗi bước có thể là function riêng hoặc một hoạt động được quản lý. Workflow lưu trạng thái và quyết định bước tiếp theo. Không nên dùng chuỗi function gọi nhau đồng bộ như một state machine tự chế nếu nghiệp vụ cần theo dõi trạng thái lâu dài.

## 5. Function granularity theo transaction boundary

Một function nên giữ các thao tác cần hoàn thành cùng nhau trong một transaction boundary nếu chúng cùng nằm trong một hệ thống dữ liệu hỗ trợ transaction phù hợp.

Ví dụ, cập nhật trạng thái đơn hàng và ghi outbox event có thể nằm trong cùng một database transaction. Function sau đó phát event từ outbox. Điều này tránh tình huống database commit thành công nhưng publish event thất bại.

Ngược lại, không nên cố tạo một transaction phân tán qua database, payment provider và email service nếu các hệ thống không hỗ trợ transaction chung. Dùng saga hoặc workflow với compensation.

### Câu hỏi quyết định

- Các thao tác có phải all-or-nothing không?
- Chúng có cùng một database transaction không?
- Nếu một thao tác lỗi, có thể rollback hay phải compensation?
- Có thể chấp nhận eventual consistency không?
- Có cần retry từng bước hay retry toàn bộ nghiệp vụ?
- Người dùng có cần biết trạng thái tiến trình không?

### Ví dụ

Tạo đơn hàng có thể gồm:
1. Validate dữ liệu.
2. Ghi đơn hàng ở trạng thái pending.
3. Ghi event vào outbox trong cùng transaction.
4. Worker xử lý giữ hàng.
5. Function thanh toán.
6. Workflow xác nhận hoặc hủy đơn.

Mỗi bước có trạng thái rõ và có thể retry theo chính sách. Không giữ một invocation chạy xuyên suốt nhiều phút để chờ mọi dependency.

## 6. Chọn đơn vị công việc: một item, batch hay partition

Đây là quyết định ảnh hưởng trực tiếp đến thời gian chạy, memory, concurrency và retry.

### Một item mỗi invocation

Mỗi invocation xử lý một đối tượng độc lập:
- Một ảnh.
- Một tài liệu.
- Một đơn hàng.
- Một message.
- Một bản ghi thay đổi.

Ưu điểm:
- Failure isolation tốt.
- Retry chỉ tác động một item.
- Dễ phân bổ log, metric và idempotency key.
- Có thể xử lý song song nhiều item.

Hạn chế:
- Tăng số invocation.
- Tăng overhead khởi tạo hoặc điều phối.
- Có thể tăng số lần gọi database/API.
- Tạo áp lực concurrency lớn khi burst.

Phù hợp khi item có thời gian xử lý lớn, payload độc lập hoặc yêu cầu retry chính xác.

### Batch nhiều item mỗi invocation

Một invocation nhận và xử lý nhiều item:
- Một batch message từ queue.
- Một nhóm file nhỏ.
- Một trang dữ liệu.
- Một tập bản ghi theo partition.

Ưu điểm:
- Giảm số invocation.
- Tái sử dụng kết nối và dữ liệu cấu hình.
- Có thể amortize startup và dependency overhead.
- Tăng throughput nếu xử lý item có thể gom nhóm.

Hạn chế:
- Payload và memory lớn hơn.
- Thời gian chạy dài hơn.
- Một item lỗi có thể ảnh hưởng batch nếu không có partial failure handling.
- Retry toàn batch có thể xử lý lại item đã thành công.
- Một batch quá lớn có thể vượt timeout hoặc memory.

Batch cần có giới hạn theo số item, tổng byte, thời gian dự kiến và khả năng retry.

### Partition

Partition chia một tập dữ liệu lớn thành các phần có thể xử lý độc lập, thường theo key, tenant, shard hoặc khoảng thời gian.

Phù hợp khi:
- Dữ liệu lớn.
- Cần giữ ordering theo key.
- Có thể xử lý song song giữa các partition.
- Cần checkpoint hoặc tiếp tục từ vị trí đã xử lý.

Partition cần thiết kế key distribution để tránh hot partition. Nếu một tenant tạo 80% tải, chia theo tenant có thể không đủ cân bằng.

### So sánh

| Đơn vị | Throughput | Failure isolation | Overhead | Rủi ro chính |
|---|---|---|---|---|
| Một item | Có thể cao nhờ parallelism | Tốt | Invocation nhiều | Concurrency spike |
| Batch nhỏ | Tốt cho item nhẹ | Trung bình/tốt nếu có partial failure | Thấp hơn | Retry item |
| Batch lớn | Có thể giảm overhead nhưng tăng latency | Thấp hơn | Thấp theo item | Timeout, memory, retry blast radius |
| Partition | Tốt với dữ liệu lớn | Theo partition | Điều phối/checkpoint phức tạp hơn | Hot partition và ordering |

## 7. Cách chọn batch size có cơ sở

Không chọn batch size chỉ để giảm invocation count. Hãy đo thời gian và bộ nhớ theo kích thước batch.

Gọi:
- \(B\) là số item trong một batch.
- \(t_0\) là overhead cố định của invocation.
- \(t_i\) là thời gian xử lý trung bình một item.
- \(t_{total}\) là thời gian dự kiến của batch.

Một ước lượng đơn giản:

\[
t_{total} \approx t_0 + B \times t_i
\]

Nếu mỗi item có thời gian biến động, dùng p95 hoặc p99 thay vì average để tránh batch thường xuyên vượt timeout.

Ví dụ:
- Overhead invocation: 150 ms.
- Thời gian xử lý mỗi item: 40 ms.
- Batch 10 item: khoảng 550 ms.
- Batch 100 item: khoảng 4,15 giây.

Đây là mô hình tuyến tính minh họa. Thực tế có thể có batch API, connection reuse, cache, contention và xử lý song song khiến thời gian không tuyến tính.

### Chọn theo timeout budget

Nếu timeout tối đa là \(T_{max}\), không đặt batch dự kiến sát giới hạn. Cần chừa:
- Thời gian lấy input.
- Thời gian xử lý.
- Thời gian ghi output/checkpoint.
- Network jitter và dependency latency.
- Serialization và cleanup.
- Margin cho item chậm hoặc retry nội bộ.

Có thể đặt mục tiêu p95 batch duration nhỏ hơn một tỷ lệ an toàn của timeout, sau đó kiểm chứng bằng load test. Tỷ lệ cụ thể phụ thuộc biến động workload và khả năng retry.

### Chọn theo memory budget

Một ước lượng:

\[
Memory_{batch} \approx Memory_{base} +
B \times Memory_{perItem} + Memory_{overhead}
\]

Cần đo working set thực tế. Nếu function tải toàn bộ batch vào RAM rồi giữ cả input, intermediate object và output, peak memory có thể lớn hơn nhiều so với kích thước payload.

Có thể xử lý streaming hoặc từng chunk thay vì giữ toàn bộ batch trong memory.

### Chọn theo retry blast radius

Nếu một item lỗi làm retry toàn batch, batch càng lớn thì công việc bị lặp càng nhiều. Partial batch response, checkpoint hoặc lưu trạng thái theo item giúp giảm phạm vi retry.

Nếu nền tảng không hỗ trợ partial failure, cần cân nhắc batch nhỏ hoặc tách item độc lập.

## 8. Chọn memory, CPU và kích thước runtime

Trong nhiều dịch vụ function, memory configuration có thể đồng thời ảnh hưởng CPU allocation, network capability hoặc giới hạn runtime. Quan hệ cụ thể phụ thuộc provider và loại function.

### Memory sizing

Chọn memory theo:
- Baseline runtime và framework.
- Input payload.
- Working set và intermediate data.
- Native library overhead.
- Serialization/deserialization.
- Concurrency bên trong một invocation.
- Buffer cho network và file.
- Peak memory trong batch.

Không chọn memory theo average. Đo peak hoặc percentile cao trong tải đại diện, bao gồm batch lớn nhất được phép.

### CPU sizing

Một số nền tảng gắn CPU với mức memory; một số cho cấu hình riêng hoặc dùng loại compute khác. Cần kiểm tra:
- CPU allocation thực tế.
- Thời gian CPU-bound.
- Single-thread performance.
- Parallelism trong invocation.
- CPU throttling hoặc quota.
- Tác động của tăng memory lên duration.

Nếu tăng memory làm CPU allocation tăng, invocation có thể chạy nhanh hơn và tổng compute duration giảm. Nhưng chi phí mỗi invocation có thể tăng hoặc giảm tùy meter. Benchmark cả duration và cost.

### Ephemeral storage

Function có thể có vùng lưu trữ tạm cho file tải xuống, unzip, scratch data hoặc model cache. Cần:
- Tính peak disk usage.
- Xóa file tạm sau xử lý.
- Không dùng ephemeral disk làm nơi lưu trạng thái bền vững.
- Kiểm tra encryption và lifecycle.
- Tránh ghi file lớn khi có thể stream.

### Runtime và cold start

Runtime, package size, dependency initialization và network access có thể ảnh hưởng cold start. Function lớn với nhiều dependency thường có thời gian khởi động và deploy lớn hơn.

Tối ưu bằng:
- Chỉ đóng gói dependency cần thiết.
- Lazy-load thành phần ít dùng nếu phù hợp.
- Reuse connection/client trong execution environment khi runtime cho phép.
- Giảm công việc ở initialization path.
- Dùng provisioned/warm capacity khi SLO yêu cầu và chi phí phù hợp.

Không chuyển logic sang một function cực nhỏ chỉ để giảm cold start nếu điều đó tạo nhiều network hop và state handoff.

## 9. Concurrency và throughput

Concurrency là số invocation đang chạy đồng thời. Nó ảnh hưởng throughput, downstream load và tổng chi phí.

Một ước lượng theo Little's Law:

\[
Concurrency \approx ArrivalRate \times AverageDuration
\]

Ví dụ, function nhận 40 event/giây và duration trung bình 0,5 giây:

\[
Concurrency \approx 40 \times 0.5 = 20
\]

Đây là concurrency trung bình trong trạng thái ổn định. Peak, duration tail và burst có thể cần capacity cao hơn.

### Giới hạn concurrency

Cần kiểm soát:
- Account/project quota.
- Function-level reserved/max concurrency.
- Event source mapping concurrency.
- Queue/stream partition concurrency.
- Downstream connection limit.
- Database capacity.
- API rate limit.
- CPU/memory và storage.

Nếu function scale nhanh hơn database, hệ thống có thể chuyển bottleneck từ compute sang database. Dùng semaphore, connection pool, rate limiter hoặc queue để giới hạn tải downstream.

### Batch size và concurrency tương tác

Batch lớn giảm invocation count nhưng mỗi invocation có thể chiếm memory lâu hơn. Concurrency thấp có thể làm backlog tăng. Batch nhỏ với concurrency quá cao có thể tạo nhiều connection và request nhỏ.

Cần benchmark theo ma trận batch size × concurrency, không tuning từng tham số riêng lẻ.

## 10. Thiết kế input và output contract

Một function tốt có contract rõ ràng và version được.

### Input contract

Nên chứa:
- Event ID hoặc request ID.
- Schema version.
- Business entity ID.
- Event type.
- Timestamp.
- Correlation/trace ID.
- Payload hoặc reference tới payload.
- Tenant/context cần thiết.
- Deadline hoặc expiration nếu có.

Với payload lớn, thường nên truyền object reference thay vì nhúng toàn bộ nội dung vào event. Function tải dữ liệu từ object storage theo quyền tối thiểu.

### Output contract

Cần xác định:
- Business result.
- Status.
- Error code có cấu trúc.
- Resource ID hoặc artifact reference.
- Version.
- Correlation ID.
- Retryability hoặc failure category khi phù hợp.

Không trả stack trace, secret hoặc dữ liệu nhạy cảm cho caller. Error message nên đủ để xử lý nhưng không tiết lộ nội bộ.

### Versioning

Khi thay schema:
- Thêm field mới theo hướng backward-compatible khi có thể.
- Không đổi ý nghĩa field cũ mà không version.
- Consumer phải xử lý version không hỗ trợ.
- Có thời gian chạy song song giữa producer/consumer cũ và mới.
- Kiểm thử event cũ còn tồn trong queue hoặc replay.

## 11. State, idempotency và side effects

Function thường stateless giữa các invocation. Không giả định biến global hoặc file tạm được giữ lâu dài hoặc luôn thuộc cùng execution environment.

### State ở bên ngoài

Dùng database, durable object storage, workflow state hoặc queue để lưu trạng thái cần tồn tại qua invocation.

Không lưu trạng thái nghiệp vụ duy nhất trong memory của function. Instance có thể bị thu hồi, scale về zero hoặc nhận event khác.

### Idempotency

Event có thể được giao lại vì timeout, lỗi mạng hoặc acknowledgment thất bại. Function nên có khả năng xử lý cùng event nhiều lần mà không tạo side effect trùng.

Một mẫu đơn giản:
1. Nhận event ID hoặc idempotency key.
2. Kiểm tra record đã được xử lý chưa.
3. Ghi trạng thái processing theo transaction/conditional write.
4. Thực hiện side effect.
5. Ghi kết quả và trạng thái completed.
6. Nếu lỗi, xác định có thể retry hay cần reconciliation.

Chỉ kiểm tra "đã thấy ID" rồi thực hiện side effect sau đó có thể tạo race condition nếu hai invocation chạy song song. Cần conditional write, unique constraint hoặc lock/lease phù hợp.

### Outbox pattern

Nếu một transaction vừa ghi database vừa cần phát event, có thể ghi business data và outbox record trong cùng transaction. Một publisher đọc outbox và gửi event. Consumer vẫn cần idempotency vì message có thể được phát hoặc nhận nhiều lần.

### Side effect không thể rollback

Gửi email, charge payment hoặc gọi API bên ngoài có thể không thể hoàn tác. Dùng:
- Idempotency key.
- Provider transaction reference.
- State machine.
- Compensation action.
- Reconciliation job.
- Audit trail.

Không retry vô hạn một side effect mà không biết lần trước đã thành công hay chưa.

## 12. Đồng bộ hay bất đồng bộ?

### Xử lý đồng bộ

Dùng khi:
- Công việc ngắn.
- Caller cần kết quả ngay.
- Dependency có latency dự đoán được.
- Tổng thời gian nằm trong timeout budget.

Trả lỗi rõ ràng khi không thể hoàn tất. Không giữ request chờ tác vụ dài có thể được xử lý qua queue.

### Xử lý bất đồng bộ

Dùng khi:
- Công việc dài hoặc biến động.
- Có burst.
- Có thể chấp nhận eventual consistency.
- Cần retry và dead-letter.
- Caller chỉ cần job ID hoặc trạng thái.

Một API có thể nhận request, lưu job và trả HTTP 202 cùng job ID. Worker xử lý phía sau; caller truy vấn trạng thái hoặc nhận callback/event.

### Workflow

Dùng workflow khi có nhiều bước, nhánh, retry, timeout hoặc compensation. Workflow nên quản lý state và deadline; function chỉ thực hiện một hoạt động nghiệp vụ có thể kiểm tra.

## 13. Ví dụ: xử lý ảnh và chọn kích thước đơn vị

Một dịch vụ nhận ảnh từ người dùng và tạo thumbnail, preview và metadata.

### Ranh giới nghiệp vụ

Có thể có các function:
- Validate upload metadata.
- Scan file.
- Generate image derivatives.
- Update asset metadata.
- Publish asset-ready event.

Không nhất thiết mỗi định dạng thumbnail là một function riêng. Một function generate derivatives có thể tạo nhiều kích thước từ cùng ảnh nếu chúng có cùng dependency và failure boundary.

### Đơn vị xử lý

Lựa chọn A: một invocation cho mỗi ảnh.
- Dễ retry một ảnh.
- Dễ đo duration và cost/ảnh.
- Tốt khi ảnh lớn và thời gian xử lý biến động.
- Nhiều invocation khi upload hàng loạt.

Lựa chọn B: batch 10 ảnh.
- Giảm overhead nếu ảnh nhỏ.
- Reuse decoder/configuration.
- Cần xử lý partial failure.
- Một ảnh rất lớn có thể làm batch chậm hoặc hết memory.

Lựa chọn C: một invocation xử lý toàn bộ thư mục.
- Có thể tạo payload và memory lớn.
- Timeout dài.
- Retry phạm vi rộng.
- Không phù hợp nếu thư mục có kích thước không giới hạn.

Có thể chọn một ảnh mỗi message cho ảnh lớn và batch nhỏ cho ảnh thumbnail nhẹ. Đây là quyết định theo profile dữ liệu, không phải quy tắc cố định.

### Kiểm soát tài nguyên

Đo:
- Kích thước file p50/p95/p99.
- Peak memory khi decode.
- CPU time theo pixel và định dạng.
- Ephemeral disk khi unzip hoặc tạo nhiều derivative.
- Duration.
- Số retry.
- Cost per accepted image.

Giới hạn pixel dimensions và file size để tránh decompression bomb hoặc payload gây cạn tài nguyên. Kiểm tra content type thực tế thay vì chỉ tin extension.

## 14. Ví dụ: workflow đặt hàng

Một workflow đặt hàng có thể chia theo bước:
- Validate order.
- Reserve inventory.
- Authorize payment.
- Confirm order.
- Send notification.

Mỗi function xử lý một bước và nhận event chứa order ID cùng version. Workflow lưu trạng thái hiện tại.

### Tại sao không gom tất cả?

Nếu email provider lỗi, không nên charge payment lần nữa chỉ vì toàn bộ function timeout. Nếu inventory đã được reserve nhưng payment thất bại, cần release inventory qua compensation. Mỗi bước có retry và timeout riêng.

### Tại sao không tách quá nhỏ?

Nếu mỗi lần đọc field hoặc đổi trạng thái đều là một function invocation, hệ thống tăng số network hop, IAM policy, log và orchestration. Gộp các thao tác thuần nội bộ cùng transaction boundary thường hợp lý hơn.

### State transition

| Trạng thái | Hành động tiếp theo | Nếu lỗi |
|---|---|---|
| RECEIVED | Validate | Trả lỗi nghiệp vụ |
| VALIDATED | Reserve inventory | Retry hoặc đánh dấu unavailable |
| RESERVED | Authorize payment | Retry có idempotency |
| PAID | Confirm order | Reconcile nếu commit chưa rõ |
| CONFIRMED | Publish event | Outbox retry |
| NOTIFIED | Hoàn tất | Notification có thể retry riêng |

Các trạng thái phải được lưu bền vững. Workflow cần có timeout tổng và chính sách xử lý trạng thái treo.

## 15. Ví dụ: chọn batch size cho queue consumer

Giả sử queue nhận 600 message/giây. Mỗi message cần trung bình 20 ms CPU và 80 ms I/O. Function có giới hạn thời gian đủ dài cho batch vừa phải.

### Một message mỗi invocation

Nếu mỗi invocation xử lý 100 ms, concurrency trung bình ước lượng:

\[
600 \times 0.1 = 60
\]

Số invocation lớn, nhưng retry và isolation rõ. Nếu dependency có connection limit thấp, cần giới hạn concurrency.

### Batch 10 message

Nếu overhead mỗi invocation là 50 ms và mỗi item mất 100 ms tuần tự:

\[
t_{batch} \approx 50ms + 10 \times 100ms = 1.05s
\]

Số batch đến trung bình là 60 batch/giây. Với duration 1,05 giây:

\[
Concurrency \approx 60 \times 1.05 = 63
\]

Batch giảm invocation rate nhưng không tự giảm concurrency nếu mỗi batch chạy lâu hơn tương ứng. Nếu function xử lý item song song, duration có thể giảm nhưng CPU, memory và dependency load tăng.

### Cần thử nghiệm

Đo batch size 1, 5, 10 và 20 cùng nhiều mức concurrency. So sánh:
- Throughput.
- Queue age/backlog.
- p95/p99 duration.
- Memory peak.
- Dependency connection wait.
- Partial failure và retry.
- Cost per successfully processed message.

Chọn cấu hình đạt SLO và giới hạn dependency với headroom, không chọn batch lớn nhất.

## 16. Giới hạn nền tảng ảnh hưởng tới thiết kế

Mỗi provider có giới hạn riêng về:
- Maximum execution duration.
- Memory range.
- CPU allocation.
- Ephemeral storage.
- Payload/request/response size.
- Concurrent executions.
- Invocation rate.
- Environment variables.
- Deployment package size.
- Number of layers/extensions.
- Event source batch size.
- Retry age/count.
- Network access và VPC configuration.

Không hard-code một con số giới hạn chung cho mọi provider. Đọc tài liệu dịch vụ và region đang dùng, sau đó lưu giới hạn như một phần của architecture decision record.

### Thiết kế trong giới hạn

- Chia job dài thành nhiều bước/checkpoint.
- Đưa payload lớn vào object storage và truyền reference.
- Giới hạn batch size.
- Dùng queue để điều tiết burst.
- Dùng workflow cho tiến trình dài.
- Giữ state bên ngoài function.
- Chọn memory/CPU theo benchmark.
- Giới hạn concurrency theo downstream.
- Dùng durable storage cho kết quả và checkpoint.

### Workload vượt mô hình function

Cân nhắc container job, managed batch hoặc long-running service khi:
- Công việc cần chạy dài vượt timeout.
- Cần process liên tục hoặc giữ kết nối lâu.
- Cần GPU/driver tùy chỉnh không được function platform hỗ trợ.
- Payload/working set vượt giới hạn.
- Cần filesystem hoặc runtime đặc biệt.
- Workload có tải liên tục khiến serverless không còn lợi thế chi phí.
- Cần kiểm soát scheduling hoặc host-level behavior sâu.

## 17. Bảo mật theo ranh giới nghiệp vụ

Function nên có quyền tối thiểu cho đúng nhiệm vụ.

Ví dụ:
- Validate-order chỉ cần đọc catalog và ghi validation result.
- Reserve-inventory cần cập nhật inventory nhưng không cần quyền gửi email.
- Notification chỉ cần đọc event và gửi thông báo, không cần quyền sửa payment.
- Image processor chỉ cần đọc object đầu vào và ghi prefix output được phép.

### Tách quyền

Dùng execution role/service identity riêng theo function hoặc nhóm function có cùng trách nhiệm. Không dùng một role quản trị chung cho toàn bộ workflow.

### Input validation

- Xác thực schema và version.
- Kiểm tra tenant/owner.
- Giới hạn payload size.
- Kiểm tra file content và MIME thực tế.
- Không tin metadata từ client.
- Chống replay hoặc duplicate nếu nghiệp vụ yêu cầu.
- Validate path/object key để tránh truy cập ngoài phạm vi.

### Secret và dữ liệu nhạy cảm

Không nhúng secret vào code hoặc image. Dùng secret manager hoặc workload identity, rotation và quyền truy cập có giới hạn. Tránh ghi PII, token hoặc payload nhạy cảm vào log.

### Network boundary

Nếu function truy cập private database hoặc service, kiểm tra subnet, security group/firewall, NAT và connection exhaustion. Đưa function vào VPC/private network có thể ảnh hưởng cold start, egress và route tùy nền tảng.

## 18. Observability theo function và đơn vị công việc

Cần theo dõi cả function-level và item-level.

### Metric function

- Invocation count.
- Duration p50/p95/p99.
- Error và timeout.
- Throttles.
- Concurrent executions.
- Cold start.
- Memory peak hoặc memory used.
- Retry count.
- Cost hoặc resource-time.

### Metric đơn vị công việc

- Items received.
- Items succeeded/failed.
- Partial batch failures.
- Item processing duration.
- Payload size.
- Retry per item.
- Dead-letter count.
- Queue age/backlog.
- Cost per accepted item.

### Correlation

Dùng:
- Request ID.
- Event ID.
- Business entity ID.
- Workflow execution ID.
- Correlation/trace ID.
- Function version.
- Schema version.

Không dùng business ID có cardinality cao làm metric label nếu hệ thống metrics không hỗ trợ cardinality lớn. Đưa ID vào structured log hoặc trace attribute phù hợp.

### Phân biệt function success và business success

Invocation có thể trả status thành công nhưng chỉ xử lý được 8/10 item. Cần metric partial success để không đánh giá quá cao chất lượng.

Tương tự, function có thể trả lỗi vì downstream timeout dù side effect đã commit. Cần idempotency và reconciliation để xác định kết quả thực.

## 19. Đo hiệu quả và chi phí của kích thước đơn vị

Cost model đơn giản cho một invocation:

\[
C_{invocation} =
C_{request} + C_{resourceTime} + C_{network} + C_{dependency}
\]

Tùy nền tảng, request và resource-time có thể là meter riêng hoặc đã gộp. Dependency cost có thể được ghi nhận ở service khác.

Cost per successful item:

\[
C_{item} =
\frac{TotalAllocatedCost}
{SuccessfulItems}
\]

Nếu batch có retry, phải tính cả invocation và resource-time bị lặp. Một batch lớn có thể giảm request overhead nhưng tăng retry waste.

### Ví dụ trade-off

| Cấu hình | Invocation/tháng | Duration trung bình | Retry waste | Kết quả |
|---|---:|---:|---:|---|
| Batch 1 | Cao | Ngắn | Thấp theo item | Dễ retry, overhead lớn |
| Batch 10 | Trung bình | Vừa | Có thể cần partial failure | Thường cân bằng |
| Batch 100 | Thấp | Dài | Cao nếu retry cả batch | Rủi ro timeout và memory |

Bảng chỉ minh họa xu hướng; số liệu thực tế phụ thuộc workload. Cần đo cost per successful item cùng latency, backlog và failure rate.

### Không tối ưu chỉ theo số invocation

Giảm invocation count không có nghĩa tổng cost giảm nếu:
- Duration tăng nhiều.
- Memory cần tăng.
- Batch retry làm lặp nhiều item.
- Queue age tăng và cần thêm capacity.
- Downstream phải scale lên.
- Function timeout và job bị bỏ dở.

Tối ưu theo kết quả hoàn thành và SLO.

## 20. Kiểm thử thiết kế function

Trước production, cần kiểm thử:
- Contract test cho input/output.
- Unit test logic nghiệp vụ.
- Integration test với database/queue/storage.
- Idempotency test khi cùng event đến nhiều lần.
- Concurrency test khi duplicate event đồng thời.
- Partial batch failure test.
- Timeout và cancellation test.
- Payload boundary test.
- Memory/CPU/load test.
- Retry storm và downstream throttling test.
- Workflow compensation test.
- Replay event cũ và schema compatibility test.

### Test theo kích thước dữ liệu

Dùng dữ liệu:
- Nhỏ nhất.
- Median.
- p95.
- p99.
- Lớn nhất được phép.
- Dữ liệu lỗi hoặc malformed.
- Dữ liệu chứa nhiều record/field bất thường.

Kiểm tra memory peak và duration theo phân phối, không chỉ một sample.

### Chaos/failure test

Giả lập:
- Database chậm.
- API bên ngoài timeout.
- Queue redelivery.
- Storage throttling.
- Function bị terminate.
- Credential hết hạn.
- Workflow step chạy lâu.
- Một item lỗi giữa batch.

Xác minh state không bị sai, side effect không trùng và retry có giới hạn.

## 21. Quy trình thiết kế function và chọn kích thước

1. **Mô tả nghiệp vụ:** viết capability và kết quả mong đợi.
2. **Xác định trigger:** HTTP, event, queue, stream, schedule hoặc workflow.
3. **Xác định boundary:** transaction, side effect và owner.
4. **Định nghĩa contract:** schema, version, identity và correlation.
5. **Chọn đơn vị công việc:** item, batch, partition hoặc workflow step.
6. **Đo profile:** payload size, CPU time, memory, I/O và duration.
7. **Chọn resource size:** memory, CPU, ephemeral storage và timeout.
8. **Chọn concurrency:** theo arrival rate, duration và downstream capacity.
9. **Thiết kế retry:** idempotency, partial failure, DLQ và compensation.
10. **Thiết kế state:** database, object storage, workflow hoặc durable queue.
11. **Giới hạn bảo mật:** execution identity và quyền tối thiểu.
12. **Benchmark:** ma trận batch size × concurrency × resource size.
13. **Đo unit cost:** cost per successful business output.
14. **Triển khai canary:** theo dõi SLO, error, backlog và cost.
15. **Rà soát:** điều chỉnh khi payload, demand hoặc dependency thay đổi.

## 22. Ma trận lựa chọn nhanh

| Đặc điểm workload | Đơn vị xử lý khởi điểm | Kiểu điều phối | Điểm cần chú ý |
|---|---|---|---|
| API ngắn, cần phản hồi ngay | Một request | Synchronous | Deadline và response latency |
| Ảnh lớn hoặc file độc lập | Một file | Queue/event | Memory, ephemeral disk và retry |
| Record nhỏ, độc lập | Batch nhỏ | Queue/stream | Partial failure và concurrency |
| Stream có ordering theo key | Partition/key | Stream consumer | Partition count và hot key |
| Nghiệp vụ nhiều bước | Một bước nghiệp vụ mỗi function | Workflow | State, compensation và timeout tổng |
| Batch dài | Chunk/checkpoint | Batch orchestrator | Resume, retry và storage |
| Tác vụ CPU nặng | Một task có giới hạn | Queue/worker | CPU allocation và execution limit |
| GPU hoặc runtime đặc biệt | Job/container nếu function không hỗ trợ | Batch/platform scheduler | Driver, device và cost |
| Công việc cần chạy liên tục | Worker service | Container/service | Idle cost và lifecycle |

Các giá trị khởi điểm phải được xác nhận bằng benchmark và tài liệu giới hạn của nền tảng.

## 23. Những anti-pattern thường gặp

### Function quá lớn

Một function thực hiện nhiều domain và side effect:
- Quyền IAM rộng.
- Khó deploy độc lập.
- Timeout chung cho nhiều nghiệp vụ.
- Retry có thể lặp side effect.
- Khó xác định owner và unit cost.

Tách theo business capability và transaction boundary.

### Function quá nhỏ

Mỗi thao tác kỹ thuật đều là invocation:
- Network hop và orchestration tăng.
- Log/trace phân tán.
- Cost request tăng.
- Khó giữ transaction.
- Failure surface lớn hơn.

Gộp các thao tác thuần nội bộ có cùng lifecycle và failure boundary.

### Batch không giới hạn

Không giới hạn số item hoặc payload bytes:
- Memory tăng bất ngờ.
- Timeout.
- Retry toàn batch.
- Queue age và tail latency tăng.

Giới hạn theo item count, byte size và expected duration.

### Dùng global memory làm state nghiệp vụ

Execution environment có thể bị tái sử dụng nhưng không có bảo đảm luôn tồn tại hoặc được gọi lại đúng instance. Dùng external durable state.

### Retry toàn bộ nghiệp vụ

Nếu một bước cuối thất bại, chạy lại tất cả side effect có thể gây duplicate. Retry theo step và dùng idempotency.

### Không kiểm soát concurrency

Function scale nhanh có thể làm database/API bị quá tải. Đặt concurrency cap và backpressure.

### Tối ưu cost mà bỏ qua SLO

Batch lớn có thể giảm request charge nhưng tăng p99 và retry. Đánh giá cost per successful on-time result.

## 24. Checklist trước production

### Nghiệp vụ và ranh giới
- [ ] Function có trách nhiệm nghiệp vụ rõ.
- [ ] Đã xác định transaction boundary và side effect.
- [ ] Đầu vào/đầu ra có schema và version.
- [ ] Có owner và quyền truy cập tối thiểu.
- [ ] Workflow dùng orchestration khi có nhiều bước/trạng thái.

### Đơn vị xử lý và tài nguyên
- [ ] Đã chọn item, batch, partition hoặc workflow step.
- [ ] Batch có giới hạn item count và payload bytes.
- [ ] Đã đo duration p95/p99 và memory peak.
- [ ] Memory/CPU/ephemeral storage phù hợp.
- [ ] Có headroom so với timeout và platform limit.
- [ ] Concurrency phù hợp arrival rate và dependency.
- [ ] Đã thử tải burst và payload lớn.

### Độ tin cậy
- [ ] Có idempotency và deduplication.
- [ ] Có partial batch failure handling khi cần.
- [ ] Retry có giới hạn, backoff và jitter.
- [ ] Có DLQ hoặc cơ chế quarantine.
- [ ] Side effect có compensation/reconciliation.
- [ ] State được lưu bền vững ngoài execution environment.
- [ ] Có deadline và cancellation rõ.

### Vận hành và chi phí
- [ ] Có metric invocation và item-level outcome.
- [ ] Có correlation ID và structured logs.
- [ ] Có dashboard duration, error, throttle, concurrency và backlog.
- [ ] Cost per successful item/request được đo.
- [ ] Có budget/usage alert và owner.
- [ ] Đã benchmark batch size × concurrency × resource size.
- [ ] Có canary, rollback và runbook.

## Kết luận

Thiết kế serverless function nên bắt đầu từ năng lực nghiệp vụ và ranh giới transaction, sau đó mới quyết định mỗi invocation xử lý một item, batch hay partition. Function có cohesion cao, contract rõ và quyền tối thiểu giúp giảm coupling và dễ kiểm thử. Kích thước đơn vị xử lý cần được chọn dựa trên payload, thời gian chạy, memory peak, CPU, concurrency, retry blast radius và giới hạn nền tảng. Batch lớn có thể giảm overhead nhưng tăng timeout, memory và phạm vi retry; batch nhỏ tăng isolation nhưng tạo nhiều invocation và có thể gây concurrency spike. Đo đồng thời SLO, throughput, queue age, partial failure và cost per successful business output giúp chọn cấu hình phù hợp với workload thực tế.
