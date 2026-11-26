# Rebuild projection

Trong kiến trúc hướng sự kiện, projection là cấu trúc dữ liệu được xây dựng từ các sự kiện nghiệp vụ để phục vụ truy vấn. Read model có thể là một bảng tổng hợp, một bản ghi trạng thái theo aggregate, một chỉ mục tìm kiếm hoặc một view tối ưu cho màn hình. Khi projection sai dữ liệu, thay đổi cách tính hoặc cần bổ sung trường mới, ứng dụng phải có cách xây dựng lại projection một cách có kiểm soát.

Rebuild projection là quá trình tạo lại read model từ một nguồn dữ liệu có thẩm quyền, sau đó đưa phiên bản mới vào phục vụ truy vấn. Với Spring Modulith, application events và listener giúp cập nhật projection theo thay đổi nghiệp vụ. Để rebuild đáng tin cậy, cần xác định nguồn lịch sử có thể phát lại, kiểm soát thứ tự và tính lặp an toàn, đồng thời tách quá trình xây dựng khỏi thời điểm chuyển read model sang sử dụng.

## 1. Projection và read model là gì?

Projection là kết quả của việc áp dụng một hoặc nhiều sự kiện lên cấu trúc dữ liệu phục vụ truy vấn. Ví dụ, module Orders phát các event như OrderPlaced, OrderPaid và OrderCancelled. Một projection có thể tổng hợp trạng thái hiện tại của đơn hàng để màn hình đọc nhanh mà không cần truy vấn nhiều aggregate hoặc join phức tạp.

~~~text
Command / nghiệp vụ
       |
       v
Aggregate cập nhật trạng thái
       |
       v
Application event
       |
       +--------------------------+
       |                          |
       v                          v
Listener nội bộ             Externalization
       |                          |
       v                          v
Read model / projection       Hệ thống khác
       |
       v
Query API / màn hình
~~~

Projection thường có các đặc điểm:

- Được suy ra từ dữ liệu nghiệp vụ hoặc event.
- Có cấu trúc phù hợp với truy vấn cụ thể.
- Có thể xóa và tạo lại nếu nguồn dữ liệu đủ để tái dựng.
- Có thể trễ hơn trạng thái ghi do listener xử lý bất đồng bộ.
- Có thể có nhiều projection khác nhau từ cùng một tập event.

Read model là mô hình dữ liệu được thiết kế để đọc. Projection là quá trình hoặc kết quả chiếu dữ liệu vào mô hình đó. Trong nhiều ứng dụng, hai từ được dùng gần như đồng nghĩa, nhưng nên phân biệt khi thiết kế: read model là cấu trúc truy vấn; projection handler là thành phần cập nhật cấu trúc đó.

## 2. Khi nào cần rebuild?

Rebuild hữu ích khi:

- Logic tính projection đã thay đổi hoặc có bug làm sai dữ liệu.
- Read model cần thêm trường mới hoặc đổi cấu trúc.
- Cần tạo lại chỉ mục tìm kiếm hoặc bảng tổng hợp sau sự cố.
- Một tập dữ liệu bị xóa nhầm hoặc không còn nhất quán với nguồn nghiệp vụ.
- Cần chuyển sang schema mới mà không thể migration trực tiếp một cách an toàn.
- Cần kiểm chứng rằng projection hiện tại có thể tái tạo từ nguồn dữ liệu được lưu giữ.

Không nên rebuild chỉ vì một vài record bị trễ nếu listener bình thường có thể tự xử lý phần publication incomplete. Rebuild toàn bộ có thể tiêu tốn tài nguyên, làm tăng tải database và tạo ra rủi ro khi thay read model đang được query.

Trước khi chọn rebuild, xác định phạm vi: một aggregate, một tenant, một partition, một loại projection hay toàn bộ read model. Phạm vi càng nhỏ thì thời gian và ảnh hưởng vận hành thường càng thấp.

## 3. Chọn nguồn dữ liệu có thể rebuild

Rebuild chỉ đúng khi có nguồn dữ liệu đủ để tái dựng kết quả. Có ba nguồn thường gặp:

| Nguồn | Cách sử dụng | Giới hạn cần hiểu |
|---|---|---|
| Dữ liệu ghi hiện tại (source of truth) | Đọc aggregate hoặc bảng nghiệp vụ hiện tại rồi tính read model mới | Chỉ khôi phục trạng thái hiện tại; không tái tạo được mọi trạng thái lịch sử nếu nguồn không lưu lịch sử |
| Event store hoặc event log có lưu lịch sử | Phát lại event theo thứ tự để tái dựng projection | Cần retention, schema cũ có thể phải upcast và thứ tự phải được xác định |
| Snapshot kết hợp event còn lại | Khôi phục snapshot tại một checkpoint rồi áp dụng event sau checkpoint | Cần checkpoint nhất quán và biết chính xác event nào đã được bao gồm |

Một nguồn rất quan trọng cần phân biệt là **Spring Modulith Event Publication Registry**. Registry theo dõi publication của application event tới listener, đặc biệt là trạng thái đã hoàn tất hoặc còn incomplete để phục hồi việc giao event. Nó không mặc định là event store chứa toàn bộ lịch sử nghiệp vụ và không nên được xem là nguồn để replay tất cả event từ đầu. Những publication đã hoàn tất thường không phải một kho lưu lịch sử đầy đủ để rebuild.

Tương tự, Kafka topic chỉ là nguồn replay được trong giới hạn dữ liệu còn giữ trên topic hoặc được lưu trữ ở nơi khác. Nếu retention đã xóa record cũ, không thể giả định topic vẫn có đủ lịch sử để tái dựng projection. Trước khi chọn Kafka làm nguồn rebuild, cần xác nhận retention, compaction, consumer offset và chính sách lưu trữ archive.

Nếu chỉ có bảng nghiệp vụ hiện tại, rebuild phải đọc từ bảng đó hoặc từ API nguồn có thẩm quyền. Nếu cần dựng lại lịch sử, cần event store, audit log hoặc archive có đủ event. Không thể suy ra các trạng thái trung gian đã mất từ một snapshot hiện tại.

## 4. Thiết kế projection handler có thể chạy lại

Listener cập nhật projection nên idempotent hoặc có cơ chế bảo vệ khỏi event trùng. Một ví dụ handler:

~~~java
@Component
class OrderSummaryProjection {

    private final OrderSummaryRepository summaries;
    private final ProcessedEventRepository processedEvents;

    OrderSummaryProjection(
            OrderSummaryRepository summaries,
            ProcessedEventRepository processedEvents) {
        this.summaries = summaries;
        this.processedEvents = processedEvents;
    }

    @ApplicationModuleListener
    @Transactional
    void on(OrderPaid event) {
        if (processedEvents.exists(event.eventId())) {
            return;
        }

        summaries.markPaid(
            event.orderId(),
            event.paidAt(),
            event.amount()
        );

        processedEvents.record(event.eventId());
    }
}
~~~

Đây là ví dụ minh họa với repository do ứng dụng định nghĩa. Việc cập nhật projection và ghi event ID đã xử lý cần nằm trong cùng transaction nếu cùng database. Nếu process dừng giữa hai thao tác, transaction rollback giúp tránh trạng thái một phần.

Với event biểu diễn thay đổi trạng thái, handler nên có thể áp dụng cùng event nhiều lần mà không nhân đôi kết quả. Ví dụ, cập nhật trạng thái thành PAID theo event ID có thể an toàn hơn tăng một counter mỗi lần nhận event. Nếu projection cần cộng dồn số tiền, phải có deduplication hoặc version check để cùng event không được cộng hai lần.

Có thể dùng version của aggregate để bỏ qua event cũ hoặc phát hiện event đến sai thứ tự:

~~~java
if (event.aggregateVersion() <= current.version()) {
    return;
}

if (event.aggregateVersion() != current.version() + 1) {
    throw new OutOfOrderEventException(event.aggregateId());
}

projection.apply(event);
~~~

Quy tắc này chỉ phù hợp khi event contract có aggregate version liên tục và projection cần xử lý mọi phiên bản theo thứ tự. Nếu event được phép bỏ qua hoặc gộp, cần xác định semantics khác thay vì áp dụng một kiểm tra version chung cho mọi loại projection.

## 5. Tách projection đang chạy khỏi projection đang rebuild

Không nên xóa bảng đang phục vụ query rồi rebuild trực tiếp nếu ứng dụng cần tiếp tục phục vụ người dùng. Cách an toàn hơn là tạo một generation mới của projection, xây dựng và xác minh riêng, sau đó chuyển query sang generation mới.

Ví dụ schema:

~~~sql
CREATE TABLE order_summary_projection (
    generation_id VARCHAR(40) NOT NULL,
    order_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(19, 4) NOT NULL,
    last_event_version BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (generation_id, order_id)
);

CREATE TABLE projection_generation (
    projection_name VARCHAR(100) PRIMARY KEY,
    active_generation VARCHAR(40) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Ứng dụng query read model qua generation đang active. Khi rebuild, worker ghi vào generation mới, ví dụ **g2026-11-rebuild-02**. Generation cũ vẫn phục vụ query cho tới khi generation mới được xác minh và chuyển đổi.

~~~text
                    +------------------------+
Query API --------->| Active generation: g01 |
                    +------------------------+
                               |
                               v
                       Projection table

Rebuild worker ---->| New generation: g02   |
                    +------------------------+
                               |
                               v
                       Projection table

Verify g02
    |
    v
Switch active generation to g02
    |
    v
Query API reads g02
~~~

Bản ghi active generation là con trỏ điều khiển. Chuyển con trỏ trong một transaction ngắn giúp toàn bộ query mới dùng generation mới theo cùng một quy tắc. Nếu ứng dụng cache generation ID, cần có cơ chế invalidation hoặc thời hạn cache phù hợp để các instance không tiếp tục đọc generation cũ quá lâu.

Không xóa generation cũ ngay sau cutover. Giữ nó trong khoảng thời gian rollback đã thống nhất, rồi dọn dẹp khi chắc chắn không còn query hoặc worker nào sử dụng.

## 6. Rebuild từ nguồn dữ liệu hiện tại

Nếu nguồn có thẩm quyền là các bảng nghiệp vụ hiện tại, rebuild có thể đọc theo từng trang, chuyển đổi từng record thành read model và ghi vào generation mới.

Ví dụ pseudo-code:

~~~java
void rebuildFromCurrentState(String generationId) {
    UUID cursor = null;

    while (true) {
        List<OrderState> page =
            orderRepository.findNextPage(cursor, 500);

        if (page.isEmpty()) {
            break;
        }

        List<OrderSummary> summaries = page.stream()
            .map(order -> projectionMapper.toSummary(generationId, order))
            .toList();

        projectionRepository.upsertAll(summaries);
        cursor = page.getLast().id();
    }
}
~~~

Đây là ví dụ thuật toán; API phân trang và phương thức getLast() tùy phiên bản Java/repository. Trong triển khai thực tế, dùng keyset pagination với một thứ tự ổn định, ví dụ theo ID hoặc cặp khóa đã chọn. Tránh offset pagination trên tập dữ liệu thay đổi lớn vì record có thể bị bỏ qua hoặc đọc lặp khi dữ liệu thêm/xóa giữa các trang.

Nếu nguồn thay đổi trong khi rebuild, snapshot đọc ban đầu có thể không đại diện cho một thời điểm nhất quán. Có thể dùng một trong các cách:

- Đọc từ snapshot database nhất quán nếu database hỗ trợ và thời gian rebuild cho phép.
- Ghi nhận checkpoint hoặc watermark tại thời điểm bắt đầu, rồi áp dụng các thay đổi phát sinh sau checkpoint.
- Chạy rebuild generation mới song song với listener cập nhật live, sau đó catch up phần chênh lệch trước cutover.

Không giả định rằng chỉ đọc hết các trang là đủ nếu nghiệp vụ vẫn tiếp tục ghi dữ liệu trong lúc rebuild.

## 7. Rebuild bằng event replay

Nếu có event store hoặc log đầy đủ, projection có thể được dựng lại bằng cách phát lại event theo đúng thứ tự cần thiết. Mỗi event được deserialize theo schema tương ứng, chuyển đổi nếu contract đã tiến hóa, rồi áp dụng vào projection mới.

Một quy trình replay tổng quát:

1. Chọn checkpoint hoặc vị trí bắt đầu.
2. Tạo generation mới và lưu metadata của lần rebuild.
3. Đọc event theo thứ tự đã xác định, thường theo aggregate hoặc stream.
4. Deserialize và upcast event cũ nếu schema thay đổi.
5. Áp dụng event vào projection generation mới.
6. Ghi checkpoint định kỳ để có thể tiếp tục sau khi worker dừng.
7. Xác minh số lượng, tổng hợp và các invariant nghiệp vụ.
8. Catch up event mới phát sinh sau watermark.
9. Chuyển active generation sau khi đã đồng bộ.

~~~text
Event store / retained log
          |
          v
   Read from checkpoint
          |
          v
   Deserialize / upcast
          |
          v
   Apply projection handler
          |
          v
   New projection generation
          |
          v
   Validate and catch up
          |
          v
       Cutover
~~~

Không phát lại event tùy tiện từ một Kafka consumer group đang phục vụ production nếu việc thay đổi offset có thể ảnh hưởng consumer hiện tại. Dùng consumer group riêng cho rebuild, hoặc công cụ replay được thiết kế riêng. Offset của group rebuild phải độc lập với group phục vụ live traffic.

Khi replay từ log phân vùng, cần xác định thứ tự. Kafka bảo đảm thứ tự trong một partition, không bảo đảm thứ tự toàn cục giữa nhiều partition. Nếu projection tổng hợp nhiều aggregate, có thể xử lý song song theo partition hoặc aggregate khi phép cập nhật không phụ thuộc thứ tự toàn cục. Nếu projection cần thứ tự toàn cục, nguồn phải cung cấp sequence hoặc cơ chế ordering có thẩm quyền.

## 8. Đồng bộ event mới trong lúc rebuild

Một vấn đề khó là event mới vẫn tiếp tục phát sinh trong lúc generation mới đang rebuild. Nếu bỏ qua event mới, generation mới sẽ cũ ngay khi hoàn thành. Nếu vừa replay lịch sử vừa nhận live event mà không có checkpoint, cùng event có thể được áp dụng hai lần hoặc sai thứ tự.

Một chiến lược phổ biến là dùng watermark:

- Ghi lại vị trí hoặc sequence **W** tại thời điểm bắt đầu rebuild.
- Rebuild lịch sử đến đúng W vào generation mới.
- Trong thời gian đó, lưu hoặc tiêu thụ các event sau W vào một vùng catch-up.
- Sau khi replay xong, áp dụng phần event sau W theo thứ tự.
- Khi catch-up đã gần bằng live stream, tạm dừng hoặc khóa ngắn việc chuyển đổi theo cơ chế đã chọn.
- Xác minh generation mới đã bắt kịp rồi chuyển active pointer.

~~~text
Live event stream:  ... e101 e102 e103 e104 e105 e106 ...
                         |                    |
                         W                    |
                         |                    |
Rebuild history --------+---- replay to W     |
Catch-up buffer ------------------ e104 e105 e106
                                      |
                                      v
                                Apply in order
                                      |
                                      v
                                  Cutover
~~~

Watermark phải thuộc cùng một thứ tự có thể xác định. Với Kafka, có thể dùng offset theo từng partition, tạo thành vector watermark thay vì một số duy nhất. Với event store theo aggregate, có thể dùng stream version của từng aggregate. Không cộng hoặc so sánh offset của các partition khác nhau như thể chúng là một sequence toàn cục.

Cần ngăn event bị áp dụng hai lần ở ranh giới W. Có thể dùng inbox/event ID hoặc lưu checkpoint cùng generation. Khi một event xuất hiện trong cả replay và catch-up, cơ chế deduplication phải loại bỏ lần áp dụng lặp mà không bỏ mất event mới.

## 9. Kiểm tra tính nhất quán trước cutover

Một generation mới chỉ nên được kích hoạt sau khi có bằng chứng nó đúng. Tùy projection, kiểm tra có thể gồm:

- Số lượng record theo trạng thái hoặc nhóm nghiệp vụ.
- Tổng số tiền, số lượng item hoặc các aggregate quan trọng.
- Không có khóa trùng hoặc record thiếu trường bắt buộc.
- Version hoặc watermark của generation đã đạt mức yêu cầu.
- Không còn event lỗi đang chờ xử lý mà chưa có quyết định.
- Các query mẫu trả về kết quả phù hợp với nguồn có thẩm quyền.
- So sánh generation cũ và mới để hiểu những khác biệt có chủ ý.

Không nhất thiết mọi giá trị của projection mới phải giống projection cũ. Nếu mục tiêu rebuild là sửa bug hoặc thay đổi logic tính toán, khác biệt có thể là điều mong đợi. Khi đó, cần định nghĩa invariant mới và phân loại sai khác đã biết trước khi cutover.

Một bảng metadata rebuild có thể lưu trạng thái:

~~~sql
CREATE TABLE projection_rebuild_run (
    rebuild_id VARCHAR(40) PRIMARY KEY,
    projection_name VARCHAR(100) NOT NULL,
    generation_id VARCHAR(40) NOT NULL,
    source_checkpoint VARCHAR(300),
    status VARCHAR(30) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);
~~~

Các trạng thái có thể gồm **STARTED**, **REPLAYING**, **CATCHING_UP**, **VALIDATING**, **READY**, **ACTIVE**, **FAILED**. Metadata giúp vận hành biết rebuild nào đang chạy, nguồn nào đã đọc tới đâu và có thể tiếp tục hay cần khởi tạo lại.

## 10. Cutover và rollback

Cutover là thời điểm query chuyển từ generation cũ sang generation mới. Chọn thời điểm sau khi generation mới đã được xác minh và bắt kịp live traffic.

Một quy trình cutover có thể gồm:

1. Đảm bảo generation mới đã hoàn thành replay và catch-up.
2. Kiểm tra listener live đang cập nhật đúng generation hoặc cả hai generation theo chiến lược đã chọn.
3. Chặn hoặc điều phối các cập nhật đồng thời trong cửa sổ chuyển đổi nếu cần.
4. Cập nhật active generation trong transaction ngắn.
5. Xác minh các instance query đã đọc generation mới.
6. Theo dõi lỗi truy vấn, độ trễ và sai khác sau cutover.
7. Giữ generation cũ để rollback trong thời hạn đã xác định.

Nếu rollback, chuyển active pointer về generation cũ. Tuy nhiên, generation cũ có thể không còn nhận event sau cutover. Trước khi chuyển ngược, cần xác định cách cập nhật nó tới trạng thái hiện tại: tiếp tục dual-write, replay phần event sau checkpoint hoặc rebuild lại. Chuyển pointer về dữ liệu cũ mà không catch up có thể khiến read model lùi trạng thái.

Không xóa generation cũ trước khi hết thời hạn rollback và xác nhận không còn reader đang sử dụng nó.

## 11. Phục hồi khi rebuild thất bại

Rebuild có thể thất bại do lỗi dữ liệu, schema không tương thích, database quá tải, event poison hoặc worker bị dừng. Cần xác định cách tiếp tục:

- Lưu checkpoint định kỳ và chỉ tiếp tục từ checkpoint nếu thao tác apply idempotent.
- Ghi lại event lỗi, vị trí nguồn và nguyên nhân để có thể điều tra.
- Giới hạn tốc độ đọc/ghi để không gây ảnh hưởng tới workload production.
- Dùng lease hoặc khóa để tránh hai worker cùng rebuild một generation.
- Cho phép hủy generation lỗi và tạo generation mới mà không ảnh hưởng active generation.
- Chỉ đánh dấu READY sau khi hoàn tất replay, catch-up và validation.

Nếu một event không thể deserialize, không bỏ qua im lặng. Xác định đó là lỗi contract, dữ liệu hỏng hay phiên bản schema chưa được hỗ trợ. Có thể upcast event cũ sang model nội bộ mới hoặc đưa event lỗi vào quarantine với audit. Việc bỏ qua event có thể khiến projection không còn đúng với nghiệp vụ.

## 12. Quan sát rebuild và kiểm soát tải

Một rebuild kéo dài cần metric và log để biết tiến độ cũng như tác động tới hệ thống:

| Chỉ số | Ý nghĩa |
|---|---|
| Rebuild progress | Số record đã xử lý so với tổng hoặc checkpoint |
| Source checkpoint | Vị trí đã đọc trong database/event log/Kafka |
| Catch-up lag | Khoảng cách giữa generation mới và live stream |
| Processing rate | Số event/record xử lý mỗi giây |
| Failure count | Số record lỗi hoặc retry |
| Projection write latency | Tác động của rebuild lên database |
| Active generation | Generation hiện đang phục vụ query |
| Rebuild duration | Thời gian từ lúc bắt đầu đến READY/ACTIVE |

Log nên có rebuild ID, projection name, generation ID, source checkpoint, event ID, aggregate ID và nguyên nhân lỗi. Tránh ghi toàn bộ payload nhạy cảm.

Giới hạn concurrency và batch size để rebuild không chiếm hết connection pool hoặc I/O của ứng dụng. Với projection lớn, có thể chạy worker riêng hoặc lịch bảo trì. Theo dõi query latency của read API trong suốt quá trình để phát hiện tác động tới người dùng.

## 13. Kiểm thử rebuild projection

Một bộ kiểm thử hữu ích nên xác minh:

1. Tạo một chuỗi event mẫu và xác nhận projection sau khi áp dụng tuần tự.
2. Áp dụng lại cùng event và xác nhận kết quả không đổi nếu handler được thiết kế idempotent.
3. Rebuild generation mới từ nguồn lịch sử và so sánh với kết quả mong đợi.
4. Dừng worker giữa chừng rồi tiếp tục từ checkpoint mà không mất hoặc nhân đôi dữ liệu.
5. Phát event mới trong lúc rebuild và xác nhận catch-up không bỏ sót hoặc áp dụng trùng.
6. Kiểm tra event cũ cần upcast vẫn tạo projection đúng.
7. Mô phỏng event lỗi và xác nhận lỗi được ghi nhận, không bị bỏ qua âm thầm.
8. Kiểm tra cutover chuyển query sang generation mới và rollback không đưa dữ liệu lùi trạng thái.
9. Xác nhận active generation vẫn phục vụ query khi generation mới thất bại.
10. Kiểm tra rebuild có giới hạn tải và không làm read API vượt ngưỡng latency.

Dùng clock, source fixture và checkpoint giả trong unit test để kiểm soát thời gian và thứ tự. Integration test cần xác minh transaction, persistence, event listener và cách generation được chuyển đổi.

## 14. Checklist trước khi rebuild production

Trước khi bắt đầu, cần trả lời:

- Projection nào cần rebuild và phạm vi dữ liệu là bao nhiêu?
- Nguồn có thẩm quyền là bảng hiện tại, event store, Kafka retention hay archive?
- Nguồn đó có đủ lịch sử và giữ được thứ tự cần thiết không?
- Event schema cũ được deserialize/upcast như thế nào?
- Generation mới được tách khỏi generation đang active ra sao?
- Watermark/checkpoint được định nghĩa theo sequence hoặc offset nào?
- Event mới trong lúc rebuild được catch-up bằng cách nào?
- Handler có idempotent và có deduplicate event không?
- Validation nào là điều kiện READY?
- Cutover, rollback và thời hạn giữ generation cũ được thực hiện thế nào?
- Ai theo dõi tiến độ, lỗi, tải database và backlog?

Rebuild projection là một quy trình dữ liệu có nguồn, checkpoint và điểm chuyển đổi rõ ràng. Khi dùng nguồn lịch sử phù hợp, tách generation mới, xử lý event lặp an toàn, catch up live changes và xác minh trước cutover, read model có thể được tái tạo mà vẫn duy trì khả năng phục vụ truy vấn của ứng dụng Spring Modulith.

