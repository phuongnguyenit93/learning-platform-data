# Độ trễ dữ liệu

## Độ trễ dữ liệu trong projection là gì?

Trong kiến trúc dùng application event, dữ liệu ghi và dữ liệu đọc có thể được cập nhật ở hai thời điểm khác nhau. Module Orders commit trạng thái đơn hàng trước; sau đó một listener nhận OrderConfirmed và cập nhật read model cho màn hình quản trị.

Khoảng thời gian từ lúc thay đổi nghiệp vụ được ghi nhận đến khi read model phản ánh thay đổi được gọi là **độ trễ projection** (*projection lag*). Trong thời gian đó, command có thể đã thành công nhưng truy vấn vẫn trả dữ liệu cũ.

Ví dụ:

1. Lúc 10:00:00, đơn hàng được xác nhận và transaction Orders commit.
2. Lúc 10:00:00.150, listener bắt đầu xử lý event.
3. Lúc 10:00:00.420, projection commit dữ liệu mới.
4. Truy vấn sau 10:00:00.420 nhìn thấy trạng thái mới.

Trong ví dụ, độ trễ từ lúc commit nghiệp vụ đến lúc read model cập nhật là khoảng 420 ms. Con số này chỉ là minh họa; hệ thống thực tế cần đo theo tải và yêu cầu nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as Write model
    participant R as Publication Registry
    participant L as Async projection listener
    participant P as Read model
    participant Q as Query API

    C->>W: Confirm order
    W->>W: Commit transaction
    W-->>C: Command succeeded
    R->>L: Dispatch event after commit
    L->>P: Apply projection
    P-->>L: Commit read model
    Q->>P: Query order summary
    P-->>Q: Return updated data
~~~

Độ trễ là hệ quả tự nhiên của eventual consistency. Mục tiêu vận hành không nhất thiết là làm độ trễ bằng zero; mục tiêu là giữ độ trễ trong giới hạn mà use case có thể chấp nhận và phát hiện sớm khi hệ thống vượt giới hạn đó.

## Phân biệt các loại độ trễ

Một con số duy nhất có thể che khuất vị trí gây chậm. Nên tách luồng thành các khoảng đo:

| Khoảng đo | Cách hiểu |
|---|---|
| Commit-to-dispatch | Từ lúc transaction nghiệp vụ commit đến lúc listener bắt đầu |
| Queue wait | Thời gian event chờ trong executor hoặc hàng đợi trước khi được xử lý |
| Handler duration | Thời gian listener thực hiện logic projection |
| Projection commit | Thời điểm transaction read model commit thành công |
| Query latency | Thời gian API hoặc database trả lời truy vấn |
| End-to-end freshness lag | Từ lúc event được ghi nhận đến lúc read model có thể trả dữ liệu mới |

Ví dụ, handler chỉ mất 20 ms nhưng event phải chờ 8 giây trong executor. Tối ưu câu SQL của projection sẽ không giải quyết nguyên nhân chính; cần xử lý backlog hoặc năng lực xử lý bất đồng bộ.

Cũng cần phân biệt projection lag với replication lag của database. Projection lag nói về việc read model chưa được cập nhật từ event. Replication lag nói về độ trễ đồng bộ giữa primary và replica. Một truy vấn có thể chậm do cả hai nguyên nhân cùng lúc.

## Đo độ trễ từ event đến read model

Một event có thể mang các trường phục vụ đo lường:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    long aggregateVersion,
    Instant occurredAt,
    Instant publishedAt,
    String correlationId
) {}
~~~

Trong đó:

- occurredAt là thời điểm nghiệp vụ xảy ra, có thể đến từ domain clock.
- publishedAt là thời điểm publisher tạo hoặc phát event.
- eventId nhận diện lần phát event.
- aggregateVersion giúp xác định thứ tự thay đổi của một aggregate.
- correlationId liên kết log và trace của cùng một yêu cầu.

Projection có thể ghi lại thời điểm đã áp dụng:

~~~java
public record ProjectionCheckpoint(
    UUID orderId,
    long appliedVersion,
    Instant appliedAt,
    UUID lastEventId
) {}
~~~

Với các mốc thời gian được đo trên cùng nguồn clock đáng tin cậy:

- Publish-to-start = handlerStartedAt - publishedAt.
- Handler duration = handlerFinishedAt - handlerStartedAt.
- Event-to-projection = appliedAt - publishedAt.
- Business-to-projection = appliedAt - occurredAt, nếu occurredAt và appliedAt có cùng quy ước thời gian.

Nếu publisher và projection chạy ở các máy khác nhau, đồng hồ hệ thống có thể lệch. Đo chênh lệch timestamp trực tiếp khi chưa đồng bộ clock có thể tạo số âm hoặc sai lệch. Nên đồng bộ thời gian hạ tầng, dùng trace để đo duration qua các span, hoặc lưu timestamp từ cùng một nguồn database khi cần so sánh chính xác.

Không dùng thời điểm truy vấn hiện tại trừ thời điểm nghiệp vụ xảy ra làm thước đo duy nhất nếu event có thể được replay hoặc backfill. Khi replay lịch sử, event cũ có occurredAt từ nhiều ngày trước nhưng vừa được áp dụng vào projection; đó là thời gian lịch sử, không phải thời gian chờ xử lý hiện tại. Cần lưu cả event time và processing time.

## Đo theo percentile và freshness SLO

Độ trễ thường có phân bố lệch: phần lớn event được xử lý nhanh nhưng một nhóm nhỏ có thể chờ rất lâu do retry, lock hoặc dependency chậm.

Vì vậy, theo dõi nhiều percentile:

- p50 cho trải nghiệm điển hình.
- p95 cho phần lớn request/event chậm.
- p99 để phát hiện đuôi phân bố và sự cố hiếm.
- Max hoặc tuổi của publication cũ nhất để phát hiện công việc bị treo lâu.

Ví dụ một mục tiêu vận hành minh họa:

| Chỉ số | Mục tiêu ví dụ |
|---|---|
| Projection lag p50 | Dưới 300 ms |
| Projection lag p95 | Dưới 2 giây |
| Projection lag p99 | Dưới 10 giây |
| Publication pending lâu nhất | Dưới 30 giây |
| Tỷ lệ projection thành công | Trên 99.9% |

Các ngưỡng trên chỉ là ví dụ để minh họa cách đặt mục tiêu, không phải mặc định phù hợp cho mọi ứng dụng. Hãy xác định SLO theo nhu cầu người dùng, lưu lượng, chi phí và mức độ quan trọng của dữ liệu.

Một SLO cần định nghĩa rõ:

- Bắt đầu đo từ mốc nào: transaction commit hay event publish?
- Kết thúc đo khi handler bắt đầu hay read model commit?
- Áp dụng cho event loại nào và read model nào?
- Loại trừ hay tính cả replay/backfill?
- Cửa sổ đánh giá là bao lâu?
- Hành động nào xảy ra khi vi phạm?

Nếu không thống nhất mốc bắt đầu và kết thúc, hai dashboard có thể đưa ra con số khác nhau dù cùng quan sát một pipeline.

## Những nguyên nhân làm projection chậm

### Executor hoặc worker thiếu năng lực

Listener bất đồng bộ thường chạy qua executor. Nếu số worker nhỏ hơn nhu cầu xử lý kéo dài, event phải chờ trong hàng đợi. Executor có queue không giới hạn có thể làm bộ nhớ tăng liên tục khi producer phát nhanh hơn consumer.

Nên đặt giới hạn:

- Số thread tối đa.
- Kích thước queue.
- Chính sách từ chối hoặc backpressure khi queue đầy.
- Tên thread để trace log dễ hơn.
- Thời gian chờ và thời gian thực thi.
- Quy tắc shutdown để công việc đang chạy được xử lý an toàn.

Không tăng số thread vô hạn để giảm queue wait. Listener có thể cùng truy cập database, cache hoặc API có giới hạn connection và throughput. Concurrency quá cao có thể khiến dependency nghẽn hơn.

### Handler hoặc truy vấn read model chậm

Projection có thể chậm vì truy vấn thiếu index, cập nhật nhiều bảng, lock contention hoặc gọi dịch vụ bên ngoài trong transaction.

Nên:

- Chỉ cập nhật các field cần thiết cho read model.
- Dùng batch khi nhiều event có thể được gom an toàn.
- Tạo index theo truy vấn thực tế và kiểm tra query plan.
- Tránh gọi HTTP hoặc thực hiện tác vụ dài bên trong transaction projection nếu có thể.
- Giữ transaction ngắn và giới hạn lượng dữ liệu được đọc/ghi.

### Backlog tăng nhanh hơn tốc độ xử lý

Gọi λ là tốc độ event đến và μ là tốc độ xử lý thành công. Nếu trong một khoảng thời gian dài λ lớn hơn μ, backlog sẽ tăng. Khi backlog đã tăng, dù tốc độ đến trở lại bình thường, hệ thống vẫn cần thời gian để xử lý phần tồn đọng.

Ví dụ:

| Đại lượng | Giá trị |
|---|---:|
| Event đến | 500 event/giây |
| Khả năng xử lý | 400 event/giây |
| Backlog tăng | 100 event/giây |
| Backlog sau 10 phút | Khoảng 60.000 event |

Đây là phép tính lý tưởng hóa, chưa tính retry, batching và biến động tải. Nó cho thấy chỉ nhìn thời gian xử lý trung bình của một event là chưa đủ; cần đo cả tốc độ đến, tốc độ hoàn tất và backlog.

### Retry kéo dài thời gian chờ

Event lỗi tạm thời có thể được retry nhiều lần. Một event retry liên tục sẽ có tuổi lớn dù handler mỗi lần chỉ chạy trong thời gian ngắn.

Cần theo dõi:

- Số lần resubmission hoặc retry.
- Nhóm exception gây retry.
- Tuổi publication chưa hoàn tất.
- Tỷ lệ retry thành công.
- Thời gian chờ giữa các lần thử.
- Số event bị lỗi lặp lại theo cùng một nguyên nhân.

Backoff giúp dependency phục hồi, nhưng làm tăng thời gian event hoàn tất. Với lỗi dữ liệu không thể tự phục hồi, retry lặp lại chỉ kéo dài độ trễ; cần quy trình phân loại và xử lý lỗi phù hợp.

### Lock contention và transaction kéo dài

Nhiều listener cùng cập nhật một hàng tổng hợp có thể tranh chấp lock. Một projection dùng một bản ghi global counter có thể trở thành điểm nghẽn khi tải tăng.

Có thể giảm tranh chấp bằng cách phân vùng dữ liệu, cập nhật theo aggregate, gom batch hoặc thiết kế read model sao cho các worker ít ghi cùng một hàng. Khi cần tính tổng, cân nhắc lưu các phần tổng hợp theo khóa rồi tính kết quả cuối ở bước đọc.

### Dependency bên ngoài không ổn định

Nếu listener gọi API thanh toán, dịch vụ khách hàng hoặc hệ thống tìm kiếm trong lúc cập nhật projection, thời gian phản hồi của dependency có thể chi phối toàn bộ pipeline.

Nên tách tác vụ ngoài database khỏi transaction read model, đặt timeout, bulkhead và retry có giới hạn. Nếu cần kết quả của dependency để xây dựng projection, có thể phát một event hoặc tạo một bước workflow riêng để trạng thái chờ được thể hiện rõ.

## Độ trễ trong Spring Modulith

Với Spring Modulith, @ApplicationModuleListener là cách khai báo listener bất đồng bộ được gọi sau transaction phát event commit và chạy trong transaction riêng theo semantics của framework.

Luồng cơ bản:

1. Publisher cập nhật write model và phát application event trong transaction.
2. Event Publication Registry ghi nhận publication cho listener được theo dõi.
3. Transaction publisher commit.
4. Listener được dispatch bất đồng bộ.
5. Listener cập nhật read model trong transaction riêng.
6. Khi listener hoàn tất, publication được đánh dấu hoàn tất.

Thời gian giữa bước 3 và 4 chịu ảnh hưởng của executor và thời điểm dispatch. Thời gian giữa bước 4 và 6 phụ thuộc handler, database và dependency.

Event Publication Registry hữu ích để quan sát publication chưa hoàn tất và hỗ trợ phục hồi theo cấu hình persistence. Tuy nhiên, registry không tự cung cấp mọi metric về executor queue, query latency hoặc độ tươi của dữ liệu. Cần bổ sung metric ở handler và read model để có bức tranh đầy đủ.

Nếu dùng @TransactionalEventListener(phase = AFTER_COMMIT) mà không có cơ chế async, listener có thể chạy đồng bộ trong luồng phát event sau commit. Trong trường hợp đó, thời gian phản hồi của caller có thể bao gồm thời gian listener. Cần chọn annotation và executor theo mục tiêu latency thực tế.

Để có khả năng phục hồi publication sau khi tiến trình dừng, cấu hình persistent Event Publication Registry và transaction manager đúng. Implementation in-memory không thể giữ trạng thái publication qua restart.

## Độ tươi dữ liệu và cách phản hồi API

API command và API query có thể phản ánh hai thời điểm khác nhau. Ví dụ, POST /orders/{id}/confirm trả thành công ngay khi transaction Orders commit. GET /order-summaries/{id} có thể vẫn trả trạng thái PENDING trong một khoảng ngắn.

Hãy chọn hợp đồng API rõ ràng:

- Command trả trạng thái nghiệp vụ đã commit và resource ID.
- Read API trả dữ liệu projection cùng timestamp hoặc version đã áp dụng nếu client cần biết độ tươi.
- UI có thể hiển thị nhãn “Đang cập nhật” khi read model chưa đạt version mong đợi.
- Client polling nên dùng backoff và timeout, tránh gọi liên tục.
- Với use case cần read-your-writes, command response có thể chứa snapshot phù hợp hoặc query có thể tạm thời đọc write model.

Có thể trả một trường freshness metadata như:

~~~json
{
  "orderId": "7c5a...",
  "status": "CONFIRMED",
  "projectionVersion": 12,
  "projectedAt": "2026-11-25T10:00:00Z"
}
~~~

Client có thể so sánh projectionVersion với version do command trả về. Khi version đọc nhỏ hơn version mong đợi, UI biết projection còn trễ mà không cần đoán dựa trên thời gian.

Không nên buộc mọi truy vấn chuyển sang write model chỉ để loại bỏ độ trễ. Điều đó có thể phá mục tiêu tách tải đọc/ghi và làm tăng tải lên aggregate repository. Chỉ dùng đường đọc đồng bộ cho những use case có yêu cầu nhất quán rõ ràng.

## Watermark và checkpoint của projection

Một projection có thể lưu version hoặc checkpoint mới nhất đã áp dụng. Điều này giúp biết read model đã xử lý đến đâu.

Ví dụ bảng checkpoint:

~~~sql
CREATE TABLE projection_checkpoint (
    projection_name VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    applied_version BIGINT NOT NULL,
    last_event_id UUID NOT NULL,
    applied_at TIMESTAMP NOT NULL,
    PRIMARY KEY (projection_name, aggregate_id)
);
~~~

Khi nhận event version mới, handler chỉ cập nhật projection nếu version lớn hơn checkpoint hiện tại. Nếu event đến có version nhảy từ 10 lên 12, có thể version 11 đang bị thiếu hoặc được xử lý ở nơi khác. Tùy nghiệp vụ, handler có thể:

- Chấp nhận snapshot version 12 nếu event mang đầy đủ trạng thái.
- Đưa event vào hàng chờ chờ version 11 nếu cần áp dụng delta theo thứ tự.
- Ghi nhận gap để backfill hoặc điều tra.
- Không cập nhật projection và để publication chưa hoàn tất theo cơ chế retry phù hợp.

Watermark của từng aggregate khác với offset của Kafka partition. Nếu projection tiêu thụ nhiều partition hoặc nhiều nguồn event, checkpoint phải thể hiện đúng phạm vi thứ tự mà hệ thống bảo đảm.

## Batch và cập nhật projection theo lô

Batching có thể tăng throughput khi nhiều event cập nhật cùng loại read model. Thay vì mở transaction cho từng event, worker có thể gom một nhóm nhỏ rồi ghi nhiều hàng trong một transaction.

Lợi ích:

- Giảm số lần round trip database.
- Tận dụng bulk insert hoặc update.
- Giảm overhead transaction khi tải lớn.

Rủi ro:

- Một record lỗi có thể làm rollback cả batch.
- Event có thể chờ lâu hơn để đủ batch size.
- Cần xác định cách đánh dấu publication của từng event.
- Ordering theo aggregate có thể phức tạp khi batch chứa nhiều event cùng aggregate.
- Kích thước batch quá lớn làm transaction dài và lock nhiều.

Chọn batch size và thời gian chờ tối đa dựa trên SLO. Không để event chờ mãi chỉ vì batch chưa đầy. Với các event quan trọng cần độ trễ thấp, xử lý riêng hoặc dùng batch nhỏ.

## Backpressure và điều chỉnh năng lực xử lý

Khi backlog tăng, cần tìm nguyên nhân trước khi tăng concurrency. Có thể điều chỉnh:

- Số worker và giới hạn queue của executor.
- Số consumer hoặc partition nếu projection chạy từ Kafka.
- Batch size và thời gian flush.
- Connection pool và transaction timeout.
- Query plan, index và cách ghi read model.
- Tốc độ phát event hoặc mức tải command nếu có thể điều tiết.

Một hệ thống ổn định cần có khả năng xử lý trung bình cao hơn tốc độ event đến trong điều kiện tải dự kiến, đồng thời còn headroom cho burst và retry. Nếu xử lý chỉ vừa bằng tốc độ đến, backlog khó giảm sau một đợt tăng tải.

Nếu queue đầy, cần chính sách rõ: từ chối dispatch để retry sau, áp dụng backpressure, giới hạn producer hoặc đưa công việc sang durable queue. Không âm thầm bỏ event để giữ độ trễ thấp; mất dữ liệu không phải là cách giải quyết backlog.

## Kiểm thử độ trễ và độ tươi dữ liệu

Kiểm thử projection nên xác nhận cả tính đúng đắn lẫn thời gian đáp ứng theo điều kiện tải.

| Loại kiểm thử | Điều cần đo hoặc xác nhận |
|---|---|
| Unit test handler | Mapping event thành read model đúng |
| Transaction test | Listener chỉ chạy sau commit; rollback không tạo projection |
| Idempotency test | Duplicate không làm sai dữ liệu |
| Ordering test | Version cũ không ghi đè snapshot mới |
| Integration test | Publication registry và listener phối hợp đúng |
| Load test | Throughput, queue wait, handler duration và p95/p99 lag |
| Recovery test | Publication chưa hoàn tất được phục hồi sau restart theo cấu hình |
| Backfill test | Projection bắt kịp dữ liệu trong thời gian dự kiến |

Đo latency dưới tải thực tế hoặc tải mô phỏng gần production. Một bài test chỉ phát vài chục event không thể chứng minh pipeline ổn định khi có burst lớn.

Với listener bất đồng bộ, dùng cơ chế chờ có giới hạn để xác nhận read model đạt version mong đợi. Tránh sleep cố định. Test transaction phải commit đúng thời điểm để kích hoạt listener after-commit.

## Quan sát và cảnh báo

Một dashboard độ trễ projection nên kết hợp metric từ ứng dụng, registry, executor và database:

- Projection lag p50, p95, p99 theo projection name.
- Số publication incomplete và tuổi publication cũ nhất.
- Executor active thread, queue size và task rejection.
- Handler duration và số lần lỗi.
- Event arrival rate và projection completion rate.
- Backlog hoặc consumer lag nếu có broker.
- Database connection usage, lock wait và query duration.
- Version gap và số event bị bỏ qua vì version cũ.

Đặt cảnh báo theo SLO, ví dụ p95 vượt ngưỡng trong một cửa sổ liên tục hoặc publication cũ nhất vượt giới hạn. Một event đơn lẻ chậm không nhất thiết cần cảnh báo khẩn cấp; xu hướng backlog tăng và độ trễ kéo dài mới cho thấy năng lực xử lý không theo kịp.

Không đưa event ID hoặc aggregate ID làm metric label vì cardinality không giới hạn. Dùng chúng trong log và trace có kiểm soát. Tránh ghi payload nhạy cảm vào log.

## Quy trình xử lý khi projection bị trễ

Khi độ trễ vượt SLO:

1. Xác định projection nào bị trễ và phạm vi event bị ảnh hưởng.
2. So sánh tốc độ event đến với tốc độ projection hoàn tất.
3. Kiểm tra tuổi publication incomplete và lỗi listener.
4. Kiểm tra executor queue, task rejection và concurrency.
5. Kiểm tra thời gian handler, database lock, connection pool và dependency ngoài.
6. Phân loại retry lặp, event sai thứ tự hoặc gap version.
7. Chọn biện pháp: tối ưu handler, tăng worker có giới hạn, giảm tải, batch hoặc backfill.
8. Xác nhận backlog giảm và p95/p99 quay về SLO.
9. Ghi lại nguyên nhân và cập nhật capacity plan nếu tải tăng thường xuyên.

Không xóa publication incomplete hoặc bỏ qua event để làm dashboard giảm số liệu. Cần xử lý nguyên nhân và xác nhận read model đã bắt kịp nguồn.

## Quy trình thiết kế độ trễ dữ liệu

Khi thiết kế một projection mới, hãy trả lời:

1. Read model được phép trễ tối đa bao lâu?
2. Đo độ trễ từ transaction commit, event publish hay một mốc nghiệp vụ nào?
3. Event có timestamp, event ID và aggregate version phù hợp không?
4. Listener chạy bằng executor nào và giới hạn queue ra sao?
5. Handler có transaction ngắn, idempotent và chống event cũ không?
6. Retry, resubmission và lỗi không thể phục hồi được xử lý thế nào?
7. Client nhận biết read model đã cập nhật đến version nào?
8. Có checkpoint và nguồn dữ liệu để backfill/rebuild không?
9. Metric, dashboard và cảnh báo nào chứng minh projection đang đáp ứng SLO?

Độ trễ dữ liệu là một thuộc tính cần quản lý của kiến trúc event-driven. Khi đo đúng từng chặng, đặt SLO theo nhu cầu, kiểm soát backlog và bảo vệ projection bằng version cùng idempotency, hệ thống có thể tận dụng xử lý bất đồng bộ mà vẫn cung cấp dữ liệu đọc đủ mới và có thể dự đoán.

## Tài liệu tham khảo

- Spring Modulith Reference — Working with Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Boot Reference — Task Execution and Scheduling: https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html
