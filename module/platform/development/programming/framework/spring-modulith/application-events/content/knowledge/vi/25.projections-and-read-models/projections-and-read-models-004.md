# Cập nhật projection

Projection là cấu trúc dữ liệu được tối ưu cho một cách đọc cụ thể. Trong kiến trúc hướng sự kiện, projection được cập nhật bằng cách nhận các event mô tả thay đổi nghiệp vụ rồi áp dụng chúng vào read model. Cách tổ chức này giúp module đọc truy vấn dữ liệu theo nhu cầu mà không phải truy cập trực tiếp entity hoặc repository nội bộ của module sở hữu nghiệp vụ.

Với Spring Modulith, application events tạo ranh giới giao tiếp giữa các module trong cùng ứng dụng. Một module phát event sau khi thay đổi nghiệp vụ; module sở hữu projection đăng ký listener để cập nhật dữ liệu đọc của mình. Listener cần xử lý transaction, duplicate, thứ tự và lỗi một cách rõ ràng vì read model có thể chậm hơn nguồn dữ liệu và phải có khả năng phục hồi.

Bài này trình bày cách thiết kế projection, triển khai listener cập nhật read model, giữ tính nhất quán khi event được giao lại hoặc đến sai thứ tự, rebuild projection và kiểm thử luồng cập nhật.

## 1. Projection và read model

Một write model được thiết kế để bảo vệ quy tắc nghiệp vụ và quản lý trạng thái aggregate. Read model được thiết kế để trả lời truy vấn nhanh, thường tổng hợp dữ liệu từ một hoặc nhiều nguồn.

Ví dụ, module Order sở hữu aggregate đơn hàng. Màn hình quản trị cần hiển thị danh sách đơn hàng với tên khách hàng, số dòng hàng, tổng tiền và trạng thái thanh toán. Thay vì để màn hình truy vấn trực tiếp nhiều aggregate và module khác, hệ thống có thể duy trì một projection order_summary:

~~~text
OrderPlaced       ─┐
OrderLineAdded     ├──> OrderSummaryProjection
OrderPaid         ─┤
OrderCancelled    ─┘             |
                                v
                         order_summary
                                |
                                v
                         Query / REST API
~~~

Read model có thể là bảng quan hệ, document, cache hoặc chỉ mục tìm kiếm. Điều quan trọng là nó có nguồn dữ liệu và quy tắc cập nhật xác định. Projection thường có thể được tái tạo từ event history hoặc nguồn dữ liệu chuẩn nếu thiết kế lưu trữ cho phép.

Một projection không nhất thiết là bản sao đầy đủ của aggregate. Chỉ lưu trường cần cho truy vấn. Nếu có nhiều kiểu truy vấn khác nhau, có thể tạo nhiều projection độc lập thay vì một bảng khổng lồ phục vụ mọi màn hình.

## 2. Luồng cập nhật projection với Spring Modulith

Trong ứng dụng Spring Modulith, module nguồn publish application event sau khi thay đổi nghiệp vụ. Module đọc đăng ký listener nhận event đó. Ranh giới module giúp module nguồn không phải biết projection được lưu ở đâu hoặc truy vấn như thế nào.

Ví dụ luồng:

~~~mermaid
sequenceDiagram
    participant O as Order module
    participant DB as Database
    participant R as Publication Registry
    participant P as Projection listener
    participant Q as Query API

    O->>DB: Lưu thay đổi Order
    O->>R: Publish OrderPlaced
    R->>DB: Ghi publication cùng transaction
    DB-->>O: Commit
    R->>P: Giao event sau commit
    P->>DB: Cập nhật order_summary
    P-->>R: Listener hoàn tất
    R->>DB: Đánh dấu publication hoàn tất
    Q->>DB: Đọc order_summary
    DB-->>Q: Read model
~~~

Event Publication Registry của Spring Modulith có thể theo dõi publication tới từng listener và giúp phục hồi publication chưa hoàn tất khi cấu hình persistence phù hợp. Listener hoàn tất thành công thì publication được đánh dấu hoàn tất; listener thất bại có thể được resubmit.

Publication registry không thay thế projection store. Registry theo dõi việc giao event tới listener; projection store chứa dữ liệu đọc do listener xây dựng. Hai phần có vòng đời và mục đích khác nhau.

### 2.1. Thiết kế event theo thay đổi nghiệp vụ

Event nên mô tả sự kiện đã xảy ra, ví dụ OrderPlaced, OrderPaid hoặc OrderCancelled. Tránh đặt tên event theo thao tác truy vấn hoặc command như GetOrderSummary.

Event cần có định danh ổn định và dữ liệu đủ để projection cập nhật mà không phải đọc ngược trạng thái mutable từ aggregate. Ví dụ:

~~~java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        long orderVersion,
        UUID customerId,
        String customerName,
        BigDecimal total,
        Instant occurredAt
) {}
~~~

Việc đưa customerName vào event hay chỉ gửi customerId phụ thuộc hợp đồng nghiệp vụ. Nếu projection cần tên tại thời điểm đặt hàng, event nên mang snapshot có ý nghĩa đó. Nếu tên cần luôn phản ánh giá trị hiện tại, projection cần nhận thêm event cập nhật hồ sơ khách hàng hoặc truy vấn nguồn dữ liệu có kiểm soát.

Event là hợp đồng giữa các module. Chỉ công bố dữ liệu cần thiết, dùng kiểu bất biến và tránh phụ thuộc entity JPA hoặc lazy association.

### 2.2. Publish trong transaction nghiệp vụ

Event cần được publish trong cùng transaction với thay đổi nghiệp vụ để listener không xử lý một thay đổi đã rollback. Với publication registry được cấu hình đúng, bản ghi publication cũng tham gia transaction này.

~~~java
@Service
@RequiredArgsConstructor
class PlaceOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    @Transactional
    public UUID place(PlaceOrderCommand command) {
        Order order = Order.place(command);

        orders.save(order);

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                order.getId(),
                order.version(),
                command.customerId(),
                command.customerName(),
                order.total(),
                clock.instant()
        ));

        return order.getId();
    }
}
~~~

Phương thức phải thực sự chạy trong transaction do Spring quản lý. Hãy lưu ý proxy transaction và self-invocation khi thiết kế đường gọi service.

## 3. Listener cập nhật projection

Một listener thuộc module sở hữu read model có thể dùng @ApplicationModuleListener để nhận event sau khi transaction nguồn commit. Annotation này hỗ trợ xử lý bất đồng bộ và transaction riêng cho listener theo semantics của Spring Modulith.

Ví dụ:

~~~java
@Component
@RequiredArgsConstructor
class OrderSummaryProjectionListener {

    private final OrderSummaryProjectionRepository projections;

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        OrderSummary summary = OrderSummary.from(event);
        projections.insert(summary);
    }
}
~~~

Với event cập nhật tiếp theo, listener áp dụng thay đổi tương ứng:

~~~java
@ApplicationModuleListener
void on(OrderPaid event) {
    projections.markPaid(
            event.orderId(),
            event.orderVersion(),
            event.paidAt()
    );
}
~~~

Nếu dùng @TransactionalEventListener(phase = AFTER_COMMIT) thay cho @ApplicationModuleListener, cần tự xác định rõ việc thực thi bất đồng bộ và transaction riêng nếu projection cần transaction. Không giả định listener có transaction chỉ vì nó chạy sau commit.

### 3.1. Giữ transaction cập nhật projection ngắn

Một lần xử lý event nên cập nhật projection và ghi nhận event đã xử lý trong cùng transaction database. Tránh gọi network dài bên trong transaction projection. Nếu projection cần dữ liệu từ hệ thống khác, cân nhắc đưa dữ liệu cần thiết vào event hoặc tạo bước enrichment có timeout và retry riêng.

Ví dụ repository có thể dùng câu lệnh upsert phù hợp với database để tạo hoặc cập nhật một hàng projection. Với JPA, có thể đọc entity projection rồi cập nhật; với khối lượng lớn, JDBC batch hoặc câu lệnh upsert có thể hiệu quả hơn.

Hãy chọn cách ghi dựa trên yêu cầu concurrency và hiệu năng. Điều quan trọng là update projection và checkpoint/idempotency record phải commit cùng nhau.

## 4. Idempotency: xử lý event trùng an toàn

Event có thể được giao nhiều lần. Listener có thể hoàn tất transaction projection rồi ứng dụng dừng trước khi publication được đánh dấu hoàn tất; khi phục hồi, event có thể được resubmit. Broker/outbox cũng có thể giao lại message sau timeout.

Nếu listener cộng dồn giá trị mà không deduplicate, cùng một event có thể làm tổng tiền hoặc số lượng tăng hai lần.

Một bảng inbox/processed event có thể lưu event ID đã xử lý:

~~~sql
CREATE TABLE projection_processed_event (
    projection_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (projection_name, event_id)
);
~~~

Listener đăng ký event ID trước khi áp dụng projection:

~~~java
@Transactional
public void apply(OrderPlaced event) {
    boolean firstDelivery = processedEvents.tryRegister(
            "order-summary",
            event.eventId()
    );

    if (!firstDelivery) {
        return;
    }

    projections.insert(OrderSummary.from(event));
}
~~~

tryRegister phải dựa trên unique constraint và thao tác insert nguyên tử. Nếu event ID đã tồn tại, listener bỏ qua side effect. Ghi nhận event ID và cập nhật projection phải cùng transaction:

- Nếu transaction rollback, cả event ID và projection update cùng rollback.
- Nếu transaction commit, lần giao lại sẽ thấy event ID và không áp dụng lần nữa.

Không tách ghi dedupe sang một transaction độc lập. Nếu dedupe commit trước nhưng projection update rollback, event sẽ bị bỏ qua ở lần giao sau dù projection chưa được cập nhật.

Nếu có nhiều projection, mỗi projection cần namespace dedupe riêng. Cùng một event có thể được áp dụng một lần cho order-summary và một lần cho customer-order-count.

## 5. Thứ tự event và aggregate version

Idempotency ngăn xử lý trùng nhưng không tự giải quyết event đến sai thứ tự. Ví dụ OrderPaid có thể tới trước OrderPlaced do listener bất đồng bộ, retry hoặc nhiều đường giao event.

Nếu projection cần áp dụng đầy đủ chuỗi thay đổi, event nên mang aggregate version hoặc sequence tăng đơn điệu. Projection lưu version cuối đã áp dụng:

~~~text
order_id | status | total | version
---------+--------+-------+--------
A-101    | PAID   | 120.0 | 4
~~~

Khi nhận event:

- event.version <= projection.version: event cũ hoặc trùng; bỏ qua theo chính sách.
- event.version == projection.version + 1: có thể áp dụng tiếp.
- event.version > projection.version + 1: phát hiện gap; chưa áp dụng event cho tới khi xử lý được khoảng thiếu.

Ví dụ:

~~~java
@Transactional
public void apply(OrderEvent event) {
    OrderSummary summary = projections.findForUpdate(event.orderId())
            .orElseGet(() -> OrderSummary.empty(event.orderId()));

    if (event.orderVersion() <= summary.version()) {
        return;
    }

    if (event.orderVersion() != summary.version() + 1) {
        throw new ProjectionVersionGapException(
                event.orderId(),
                summary.version(),
                event.orderVersion()
        );
    }

    summary.apply(event);
    projections.save(summary);
}
~~~

Ví dụ giả định mọi version đều phát event cho projection. Nếu projection chỉ nhận một tập event đã lọc, sequence của aggregate có thể có khoảng trống hợp lệ. Khi đó cần một projection sequence riêng hoặc quy tắc version phù hợp với tập event được tiêu thụ.

Không dùng timestamp làm thứ tự duy nhất nếu aggregate có version đáng tin cậy. Hai event có thể có cùng timestamp; đồng hồ giữa các node có thể lệch.

### 5.1. Xử lý event gap

Khi phát hiện gap, có một số lựa chọn:

- Để listener thất bại có kiểm soát để publication được retry sau khi event còn thiếu được xử lý.
- Lưu event vào inbox chờ theo aggregate, rồi áp dụng khi đủ sequence.
- Đọc lại event thiếu từ nguồn lưu trữ lịch sử.
- Rebuild projection của aggregate bị ảnh hưởng từ snapshot/event history.

Không nên âm thầm bỏ qua gap rồi tiếp tục. Projection có thể trông hợp lệ nhưng chứa trạng thái sai.

## 6. Cập nhật projection khi có concurrency

Nhiều listener hoặc nhiều instance ứng dụng có thể cập nhật projection cùng lúc. Nếu hai transaction cùng đọc version 3 rồi cùng ghi version 4, một update có thể ghi đè update còn lại.

Một số chiến lược:

**Optimistic locking:** lưu version và dùng @Version hoặc điều kiện update theo version. Nếu update thất bại do conflict, retry sau khi đọc lại.

**Pessimistic locking:** khóa hàng projection theo aggregate khi áp dụng event. Cách này giúp tuần tự hóa update nhưng có thể giảm throughput và cần tránh transaction dài.

**Atomic update:** dùng câu lệnh update/upsert có điều kiện version trong database. Ví dụ:

~~~sql
UPDATE order_summary
SET status = :status,
    version = :new_version
WHERE order_id = :order_id
  AND version = :expected_version;
~~~

Nếu số hàng cập nhật bằng 0, cần phân biệt projection chưa tồn tại, event cũ hay version gap. Không xem mọi trường hợp update 0 hàng là thành công.

**Partition/serialization theo aggregate:** nếu luồng vận chuyển hỗ trợ ordering key, các event cùng aggregate có thể được xử lý tuần tự. Tuy nhiên, application listener nội bộ chạy bất đồng bộ không tự có bảo đảm partition như broker; vẫn cần cơ chế version hoặc lock ở projection.

Chọn chiến lược theo số lượng aggregate, tốc độ event và yêu cầu nhất quán. Không khóa toàn bộ bảng chỉ để đảm bảo thứ tự cho một aggregate.

## 7. Projection và eventual consistency

Với listener bất đồng bộ, transaction nguồn có thể commit trước khi projection được cập nhật. Trong khoảng thời gian đó, query đọc model cũ. Đây là eventual consistency.

API và giao diện cần phản ánh điều này. Nếu người dùng vừa tạo đơn hàng rồi ngay lập tức truy vấn danh sách, projection có thể chưa chứa đơn hàng mới. Một số cách xử lý:

- Trả về dữ liệu xác nhận từ command response và không phụ thuộc read model ngay lập tức.
- Trả về trạng thái pending hoặc projection version để client có thể refresh.
- Dùng correlation ID hoặc aggregate version để query chờ tới khi projection bắt kịp một mốc cần thiết.
- Với một số truy vấn quan trọng, đọc trực tiếp write model có kiểm soát trong thời gian chờ.

Không nên biến mọi query thành synchronous wait cho projection; điều đó làm mất lợi ích của xử lý bất đồng bộ và có thể tạo tải lớn.

Một read model nên công bố độ trễ kỳ vọng và có metric đo thời gian từ event occurredAt tới projection updatedAt. Khi độ trễ vượt ngưỡng, cần cảnh báo.

## 8. Projection cho nhiều kiểu truy vấn

Một aggregate có thể phục vụ nhiều read model:

- order_summary cho danh sách và trạng thái đơn hàng.
- order_detail cho màn hình chi tiết.
- customer_order_stats cho số đơn và tổng chi tiêu.
- daily_sales cho báo cáo theo ngày.

Mỗi projection có schema và listener riêng, phù hợp với truy vấn cụ thể. Cách này giúp tránh một bảng đa năng với nhiều join và điều kiện phức tạp.

Không nên để module nguồn biết projection nào đang tồn tại. Module nguồn chỉ publish event hợp đồng ổn định. Module đọc tự đăng ký listener và sở hữu dữ liệu đọc của mình.

Khi một projection cần dữ liệu từ nhiều module, có thể kết hợp các event từ các nguồn. Hãy xác định rõ cách xử lý khi event tới không đồng thời và khi dữ liệu nguồn thay đổi độc lập. Ví dụ projection đơn hàng có tên khách hàng phải quyết định giữ tên tại thời điểm đặt hàng hay luôn hiển thị tên mới nhất.

## 9. Rebuild và version hóa projection

Projection có thể cần dựng lại khi schema thay đổi, logic tính toán có bug hoặc dữ liệu bị sai. Rebuild từ event history nên được thực hiện như một quy trình riêng.

Một cách an toàn là tạo projection generation mới:

1. Tạo bảng hoặc namespace projection mới, ví dụ order_summary_v2.
2. Chọn một mốc sequence hoặc snapshot nhất quán.
3. Đọc event lịch sử từ mốc đó theo thứ tự cần thiết.
4. Áp dụng event vào generation mới với dedupe/checkpoint riêng.
5. Theo dõi số lượng event, sequence gap và lỗi.
6. Catch up event mới phát sinh sau mốc snapshot.
7. Đối chiếu invariant và chuyển query sang generation mới.
8. Giữ generation cũ trong khoảng thời gian rollback đã định.

Không dùng chung bảng processed event của generation cũ nếu nó khiến toàn bộ event lịch sử bị coi là đã xử lý. Mỗi generation cần namespace idempotency/checkpoint riêng.

Nếu nguồn là Event Publication Registry, cần nhớ registry không mặc nhiên lưu toàn bộ lịch sử event đã hoàn tất. Hãy dùng event store, outbox archive hoặc nguồn snapshot/history phù hợp. Trước khi rebuild, xác minh retention và schema version của dữ liệu nguồn.

## 10. Retry và phục hồi listener

Khi listener lỗi do database tạm thời không sẵn sàng hoặc dependency bị timeout, publication có thể còn chưa hoàn tất. Spring Modulith cung cấp IncompleteEventPublications để truy vấn và resubmit các publication chưa hoàn tất theo API của phiên bản đang dùng.

Không nên resubmit vô hạn mà không phân loại lỗi. Lỗi tạm thời có thể retry với backoff; lỗi schema hoặc dữ liệu không hợp lệ cần quarantine và điều tra. Listener phải idempotent để retry không nhân đôi kết quả.

Với projection event được externalize qua broker, consumer cần retry có giới hạn, dead-letter/quarantine và cơ chế replay phù hợp. Event bị lỗi cần lưu event ID, aggregate ID, version, projection name và nguyên nhân để truy vết.

Khi một projection cần xử lý lại một event đã hoàn tất trước đó, đó là replay lịch sử chứ không phải resubmit publication chưa hoàn tất. Hãy chọn đúng nguồn lưu trữ và luồng replay riêng.

## 11. Quan sát trạng thái projection

Một projection vận hành tốt cần cho biết nó đang cập nhật tới đâu và có bỏ lỡ event hay không.

Metric nên có:

- Số event nhận, áp dụng, bỏ qua do duplicate và thất bại.
- Projection lag: thời gian từ event occurredAt tới lúc projection cập nhật.
- Aggregate version gap và số event đang chờ sequence.
- Số publication chưa hoàn tất theo listener.
- Số lần retry, số event quarantine và tuổi event lỗi lâu nhất.
- Thời gian xử lý theo projection/event type.
- Tiến độ rebuild theo generation, batch và checkpoint.

Log nên gắn eventId, aggregateId, aggregateVersion, projectionName, correlationId và generation. Tránh log toàn bộ payload hoặc dữ liệu nhạy cảm. Khi có lỗi, cần xác định được event nào không áp dụng được và projection nào bị ảnh hưởng.

Dashboard nên phân biệt event đã nhận, event đã áp dụng, event bị dedupe và event đang chờ. Tổng số message broker đã ack không thể thay thế số event đã được projection commit.

## 12. Kiểm thử cập nhật projection

Unit test hữu ích để xác minh mapping từ event sang read model và quy tắc tính toán. Integration test cần kiểm tra transaction, unique constraint, version, persistence và phục hồi.

| Kịch bản | Điều cần xác minh |
|---|---|
| OrderPlaced hợp lệ | Projection được tạo với dữ liệu đúng |
| OrderPaid tiếp theo | Trạng thái và version được cập nhật |
| Cùng event giao hai lần | Projection chỉ thay đổi một lần |
| Hai event cùng aggregate đến sai thứ tự | Gap được phát hiện và không làm sai projection |
| Hai event cập nhật đồng thời | Optimistic/pessimistic locking ngăn mất update |
| Transaction projection rollback | Dedupe record và projection update cùng rollback |
| Listener ném exception | Publication còn chưa hoàn tất và có thể phục hồi |
| Ứng dụng restart | Publication/checkpoint bền vững cho phép tiếp tục |
| Projection generation mới | Có thể rebuild độc lập với generation cũ |
| Event schema cũ | Mapping/upcaster xử lý hoặc từ chối có kiểm soát |
| Event tới trễ | Projection áp dụng theo version hoặc chính sách đã định |
| Rebuild đang chạy | Query vẫn dùng generation ổn định cho tới khi cutover |

Nếu test method tự mở transaction và rollback ở cuối, listener AFTER_COMMIT có thể không chạy. Hãy chủ động commit transaction trong test hoặc dùng test harness phù hợp để xác minh đúng pha commit. Với listener bất đồng bộ, chờ điều kiện hoàn tất bằng latch/awaitility hoặc cơ chế đồng bộ có kiểm soát, không dùng sleep cố định.

Một integration test quan trọng là chứng minh projection update và processed event record cùng commit hoặc cùng rollback. Đây là điều kiện để deduplication thực sự bảo vệ dữ liệu đọc.

## 13. Lỗi thiết kế thường gặp

**Để query module đọc trực tiếp repository của module nguồn.** Điều này làm tăng phụ thuộc và có thể vượt ranh giới module. Tạo read model do module đọc sở hữu.

**Dùng entity làm event payload.** Entity có lazy association và cấu trúc persistence không ổn định. Dùng event DTO bất biến.

**Coi listener completion là broker acknowledgement.** Publication nội bộ và message ngoài tiến trình là hai ranh giới khác nhau.

**Không có idempotency.** Retry hoặc resubmit có thể cộng dồn dữ liệu nhiều lần. Dùng event ID với unique constraint trong cùng transaction.

**Không kiểm tra version.** Event đến sai thứ tự có thể ghi đè trạng thái mới. Lưu aggregate version và xử lý gap rõ ràng.

**Nuốt exception rồi để publication hoàn tất.** Registry có thể không biết projection chưa được cập nhật. Chỉ bắt lỗi khi đã xử lý thành công hoặc chuyển sang trạng thái lỗi được theo dõi.

**Rebuild đè trực tiếp projection đang phục vụ query.** Người dùng có thể đọc dữ liệu nửa cũ nửa mới. Dùng generation mới và cutover có kiểm soát.

**Dùng registry làm event store.** Publication registry phục vụ theo dõi giao listener, không mặc nhiên là lịch sử event đầy đủ. Cần nguồn lịch sử phù hợp cho replay dài hạn.

**Không đo projection lag.** Hệ thống có thể âm thầm chậm cập nhật. Theo dõi độ trễ, gap và publication chưa hoàn tất.

## 14. Quy trình thiết kế projection

Khi thêm read model mới trong một module Spring Modulith, có thể đi theo các bước:

1. Xác định truy vấn và dữ liệu tối thiểu cần trả về.
2. Chọn event nghiệp vụ làm nguồn cập nhật.
3. Thiết kế event contract với event ID, aggregate ID và version phù hợp.
4. Đặt projection trong module sở hữu truy vấn.
5. Publish event trong transaction nghiệp vụ và cấu hình listener sau commit.
6. Cập nhật projection cùng dedupe/checkpoint trong transaction.
7. Xác định chính sách ordering, concurrency và event gap.
8. Thiết kế eventual consistency và cách API phản ánh projection lag.
9. Chuẩn bị nguồn history và quy trình rebuild/replay.
10. Kiểm thử duplicate, rollback, restart, concurrency và cutover.

Projection là dữ liệu đọc được xây dựng từ các sự kiện nghiệp vụ. Với Spring Modulith, application events giúp module nguồn và module đọc giao tiếp qua hợp đồng ổn định; Event Publication Registry hỗ trợ theo dõi listener chưa hoàn tất. Khi listener idempotent, kiểm tra version, cập nhật read model trong transaction và có quy trình rebuild riêng, projection có thể phục hồi sau lỗi và đáp ứng truy vấn mà không làm các module phụ thuộc chặt vào nhau.
