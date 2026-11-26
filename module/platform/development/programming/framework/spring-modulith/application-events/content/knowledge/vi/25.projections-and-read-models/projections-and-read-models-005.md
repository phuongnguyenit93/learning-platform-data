# Projection bất đồng bộ

## Projection bất đồng bộ là gì?

Projection là quá trình chuyển dữ liệu nghiệp vụ hoặc sự kiện thành một cấu trúc được tối ưu cho truy vấn. Read model là mô hình dữ liệu mà phía đọc sử dụng để trả lời một loại câu hỏi cụ thể. Một projection có thể tạo ra read model cho màn hình danh sách đơn hàng, bảng tổng hợp doanh thu hoặc trang theo dõi trạng thái giao hàng.

Trong kiến trúc dùng application event, module ghi dữ liệu phát sự kiện sau khi nghiệp vụ được commit. Một listener nhận event và cập nhật read model. Khi listener chạy bất đồng bộ, transaction của lệnh ghi không phải chờ projection hoàn tất.

Ví dụ, Orders xác nhận đơn hàng và phát OrderConfirmed. Một listener cập nhật bảng dữ liệu dành cho màn hình quản trị. API xác nhận đơn hàng có thể trả kết quả sau khi transaction nghiệp vụ commit, trong khi read model được cập nhật ngay sau đó.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as Orders module
    participant DB as Write database
    participant Registry as Publication Registry
    participant Worker as Async projection listener
    participant ReadDB as Read model database

    Client->>Orders: confirmOrder()
    Orders->>DB: Update order
    Orders->>Registry: Publish OrderConfirmed
    Orders->>DB: Commit
    Orders-->>Client: Confirmation result
    Registry-->>Worker: Dispatch after commit
    Worker->>ReadDB: Update projection
    ReadDB-->>Worker: Commit projection
    Worker-->>Registry: Mark publication complete
~~~

Projection bất đồng bộ tạo ra **eventual consistency**: sau khi dữ liệu ghi được commit, read model có thể cần thêm một khoảng thời gian mới phản ánh thay đổi. Đây là đặc tính cần được thiết kế và truyền đạt rõ cho phía sử dụng.

## Vì sao nên cập nhật projection bất đồng bộ?

Tách cập nhật read model khỏi transaction ghi giúp giảm thời gian phản hồi của command và tránh để các truy vấn tổng hợp làm chậm nghiệp vụ chính.

Các lợi ích thường gặp:

- **Giảm coupling giữa write model và read model:** module ghi chỉ phát sự kiện nghiệp vụ; listener phụ trách cách biểu diễn dữ liệu cho truy vấn.
- **Giảm thời gian xử lý command:** command không cần đợi mọi projection hoàn thành nếu nghiệp vụ không yêu cầu đọc lại ngay lập tức.
- **Tối ưu truy vấn:** một read model có thể gom dữ liệu từ nhiều event hoặc nhiều module theo cấu trúc phù hợp với màn hình.
- **Mở rộng độc lập:** projection có thể được xử lý bởi worker hoặc executor có giới hạn tài nguyên riêng.
- **Khả năng phục hồi:** với transactional listener và publication registry được cấu hình bền vững, publication chưa hoàn tất có thể được phục hồi theo cơ chế của Spring Modulith.

Bất đồng bộ không tự động làm hệ thống nhanh hơn trong mọi tình huống. Nó chuyển một phần công việc sang thời điểm sau commit và tạo thêm yêu cầu về giám sát độ trễ, retry, idempotency và khả năng xử lý backlog.

## Phân biệt command, event, projection và read model

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Command | Yêu cầu thay đổi trạng thái nghiệp vụ | ConfirmOrder |
| Domain/application event | Ghi nhận điều đã xảy ra | OrderConfirmed |
| Projection handler | Chuyển event thành dữ liệu truy vấn | OrderSummaryProjection |
| Read model | Dữ liệu được tối ưu cho truy vấn | Bảng order_summary |

Command thường có kết quả đồng bộ: thành công, bị từ chối hoặc thất bại. Event mô tả sự thật đã được ghi nhận sau khi nghiệp vụ thành công. Projection handler tiêu thụ event và cập nhật cấu trúc đọc.

Không nên phát một event tên OrderConfirmationRequested rồi coi đó là bằng chứng đơn hàng đã xác nhận. Event dùng để cập nhật projection cần phản ánh trạng thái đã commit, ví dụ OrderConfirmed.

Read model có thể nằm trong cùng database với write model hoặc một database riêng. Tách database giúp tối ưu tải đọc và quyền truy cập, nhưng làm tăng yêu cầu về đồng bộ, vận hành và xử lý lỗi.

## Dùng listener bất đồng bộ trong Spring Modulith

Spring Modulith cung cấp annotation @ApplicationModuleListener để khai báo listener xử lý application event sau transaction phát event. Annotation này kết hợp cách xử lý bất đồng bộ, after-commit và transaction riêng cho listener theo semantics của framework.

Ví dụ event:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    long orderVersion,
    String orderNumber,
    String customerName,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

Publisher phát event bên trong transaction nghiệp vụ:

~~~java
@Service
@RequiredArgsConstructor
public class OrderConfirmationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();

        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            order.getId(),
            order.getVersion(),
            order.getNumber(),
            order.getCustomerName(),
            order.getTotal(),
            Instant.now()
        ));
    }
}
~~~

Listener cập nhật read model:

~~~java
@Component
@RequiredArgsConstructor
public class OrderSummaryProjection {

    private final OrderSummaryRepository summaries;

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        summaries.applyIfNewer(
            event.orderId(),
            event.orderVersion(),
            event.orderNumber(),
            event.customerName(),
            event.total(),
            event.occurredAt()
        );
    }
}
~~~

Đoạn code thể hiện ranh giới trách nhiệm:

- Publisher cập nhật write model và phát event trong cùng transaction.
- Listener được gọi sau khi transaction phát event commit.
- Listener xử lý trong transaction riêng, vì vậy lỗi projection không thể rollback đơn hàng đã commit.
- Listener chỉ kết thúc thành công khi cập nhật read model hoàn tất theo transaction của nó.

Nếu dùng @TransactionalEventListener(phase = AFTER_COMMIT) đơn thuần, listener được gọi sau commit nhưng không mặc nhiên chạy trên executor bất đồng bộ. Có thể kết hợp với cơ chế async phù hợp. @ApplicationModuleListener là lựa chọn tiện dụng khi muốn semantics bất đồng bộ và transaction listener theo Spring Modulith.

Cần cấu hình executor có giới hạn và phù hợp với tải. Không nên tạo thread mới cho mỗi event hoặc dùng executor không giới hạn khiến backlog chuyển thành tình trạng cạn tài nguyên.

## Transaction của publisher và listener

Hai transaction có mục tiêu khác nhau:

1. Transaction publisher ghi thay đổi nghiệp vụ và phát event.
2. Event Publication Registry ghi nhận publication cho transactional listener theo cơ chế framework.
3. Khi publisher commit, listener mới đủ điều kiện được thực thi.
4. Listener chạy trong transaction riêng để cập nhật read model.
5. Khi listener hoàn tất thành công, registry được thông báo publication đã hoàn tất.

Nếu transaction publisher rollback, listener after-commit không được xử lý event như một thay đổi đã commit. Nếu listener lỗi, transaction projection rollback; transaction nghiệp vụ trước đó vẫn đã commit.

Đây là lý do cần phân biệt lỗi command với lỗi projection. Người dùng có thể nhận xác nhận command thành công trong khi dashboard cập nhật chậm do listener đang retry.

Event Publication Registry theo dõi vòng đời publication của listener được quản lý. Để phục hồi sau khi tiến trình dừng, cần chọn implementation persistence và cấu hình transaction phù hợp. Nếu chỉ dùng trạng thái trong bộ nhớ, không thể dựa vào registry để bảo đảm publication còn tồn tại sau restart.

## Thiết kế read model cho một truy vấn cụ thể

Read model nên được thiết kế theo câu hỏi mà ứng dụng cần trả lời. Ví dụ, màn hình quản trị cần danh sách đơn hàng với trạng thái, tên khách hàng, tổng tiền và thời điểm xác nhận. Truy vấn này có thể không cần tải toàn bộ aggregate và các quan hệ phức tạp.

Một bảng projection minh họa:

~~~sql
CREATE TABLE order_summary (
    order_id UUID PRIMARY KEY,
    order_number VARCHAR(50) NOT NULL,
    customer_name VARCHAR(200) NOT NULL,
    total_amount DECIMAL(19, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    order_version BIGINT NOT NULL,
    confirmed_at TIMESTAMP NULL
);
~~~

Bảng có thể bổ sung index theo các truy vấn thực tế, ví dụ status và confirmed_at. Không nên thêm index tùy ý mà không đo query plan và tải ghi.

Read model có thể được cập nhật theo hai cách phổ biến:

- **Snapshot projection:** event mang đủ dữ liệu cần thiết để cập nhật một hàng read model.
- **Incremental projection:** handler áp dụng thay đổi nhỏ, ví dụ tăng tổng doanh thu hoặc đổi trạng thái.

Snapshot dễ áp dụng khi event chứa dữ liệu đủ dùng và có version. Incremental projection tiết kiệm payload nhưng nhạy cảm với duplicate, mất event hoặc sai thứ tự; cần có cơ chế phát hiện gap và xây dựng lại dữ liệu.

## Event cần mang dữ liệu gì?

Event nên chứa đủ thông tin để projection cập nhật mà không phải gọi ngược module phát event trong mọi lần xử lý.

Một event cho màn hình đơn hàng có thể mang:

- Event ID ổn định để nhận diện lần phát.
- Aggregate ID để xác định hàng read model.
- Aggregate version hoặc sequence để kiểm soát thứ tự.
- Các field cần thiết cho projection.
- Thời điểm nghiệp vụ xảy ra.
- Correlation ID hoặc causation ID nếu cần truy vết.

Không nên đưa toàn bộ entity ORM hoặc object graph vào event. Payload nên là hợp đồng dữ liệu có chủ đích, ổn định và không chứa thông tin bí mật không cần thiết.

Nếu event chỉ mang orderId rồi listener truy vấn write model để lấy trạng thái hiện tại, cần cân nhắc một vấn đề: event cũ có thể được xử lý sau event mới. Khi listener đọc trạng thái mới nhất, projection có thể bỏ qua trạng thái trung gian. Điều này phù hợp với projection chỉ cần trạng thái hiện tại, nhưng không phù hợp với báo cáo cần ghi nhận mọi chuyển trạng thái hoặc tính toán theo từng sự kiện.

Nếu projection cần lịch sử hoặc tính toán theo từng thay đổi, event nên chứa dữ liệu delta cần thiết và version để xử lý đúng thứ tự.

## Idempotency: xử lý event trùng an toàn

Listener bất đồng bộ có thể nhận lại cùng event khi có retry hoặc phục hồi. Projection phải được thiết kế để xử lý lặp mà không làm sai dữ liệu.

Với snapshot projection, có thể lưu version mới nhất đã áp dụng. Chỉ cập nhật khi version event lớn hơn version hiện tại.

Ví dụ SQL minh họa:

~~~sql
INSERT INTO order_summary (
    order_id,
    order_number,
    customer_name,
    total_amount,
    status,
    order_version,
    confirmed_at
)
VALUES (
    :orderId,
    :orderNumber,
    :customerName,
    :total,
    'CONFIRMED',
    :version,
    :occurredAt
)
ON CONFLICT (order_id) DO UPDATE
SET
    order_number = EXCLUDED.order_number,
    customer_name = EXCLUDED.customer_name,
    total_amount = EXCLUDED.total_amount,
    status = EXCLUDED.status,
    order_version = EXCLUDED.order_version,
    confirmed_at = EXCLUDED.confirmed_at
WHERE order_summary.order_version < EXCLUDED.order_version;
~~~

Đây là cú pháp minh họa theo PostgreSQL. Với database khác, dùng cơ chế upsert hoặc optimistic update tương đương. Điều kiện version ngăn event cũ ghi đè snapshot mới hơn.

Nếu cần chống trùng theo event ID, có thể thêm bảng processed_event với unique key. Việc kiểm tra và ghi dấu event đã xử lý phải cùng transaction với thay đổi read model. Nếu ghi dấu trước khi projection commit, lỗi có thể khiến event bị bỏ qua dù dữ liệu chưa được cập nhật.

Với incremental projection, lưu processed event ID hoặc sequence là rất quan trọng. Một event tăng tổng doanh thu nếu được áp dụng hai lần sẽ làm sai kết quả.

## Ordering và xử lý event đến sai thứ tự

Executor bất đồng bộ có thể xử lý nhiều event đồng thời. Ngay cả khi publisher phát event theo thứ tự, listener vẫn có thể hoàn tất theo thứ tự khác nhau do thời gian xử lý, retry hoặc tải hệ thống.

Ví dụ:

1. OrderPlaced có version 1.
2. OrderConfirmed có version 2.
3. Hai listener được thực thi song song.
4. Listener version 2 hoàn tất trước.
5. Listener version 1 hoàn tất sau và có nguy cơ ghi đè trạng thái mới nếu không kiểm tra version.

Các cách xử lý:

- Dùng aggregate version để từ chối cập nhật cũ.
- Dùng optimistic locking hoặc câu lệnh update có điều kiện.
- Tuần tự hóa xử lý theo aggregate nếu nghiệp vụ yêu cầu.
- Dùng partition key theo aggregate khi externalize sang Kafka.
- Với incremental projection, phát hiện sequence bị thiếu và đưa event vào trạng thái chờ.

Cùng một Kafka key có thể giữ event của aggregate trên cùng partition, nhưng chỉ trong luồng broker và theo partitioner. Nó không tự tuần tự hóa các listener async chạy trong một ứng dụng Spring Modulith. Nếu projection xử lý event nội bộ bằng executor, vẫn cần kiểm soát concurrency tại listener hoặc tầng lưu trữ.

## Eventual consistency và trải nghiệm người dùng

Khi command trả thành công, read model có thể chưa cập nhật. API truy vấn ngay sau đó có thể trả trạng thái cũ trong một khoảng ngắn.

Ứng dụng cần quyết định cách xử lý theo yêu cầu trải nghiệm:

- Trả về trạng thái command cùng resource ID để client biết nghiệp vụ đã được xác nhận.
- Hiển thị trạng thái “đang cập nhật” cho màn hình dựa trên projection.
- Cho phép client polling có backoff hoặc nhận thông báo khi read model đã cập nhật.
- Nếu command cần kết quả đọc ngay, trả về dữ liệu từ write model hoặc response của command thay vì phụ thuộc read model bất đồng bộ.
- Đặt SLA cho độ trễ projection và cảnh báo khi vượt ngưỡng.

Không nên dùng sleep cố định ở API để chờ projection. Cách đó làm tăng latency nhưng không bảo đảm read model đã sẵn sàng. Nếu một use case thật sự cần read-after-write nhất quán, cần thiết kế cơ chế đồng bộ rõ ràng cho use case đó.

## Projection tổng hợp từ nhiều module

Một read model có thể kết hợp dữ liệu từ nhiều nguồn. Ví dụ, màn hình fulfillment cần trạng thái đơn hàng từ Orders, trạng thái thanh toán từ Payments và thông tin vận chuyển từ Shipping.

Có thể dùng nhiều event handler cập nhật các phần của cùng read model, hoặc mỗi bounded context duy trì projection riêng rồi API tổng hợp dữ liệu. Lựa chọn phụ thuộc quyền sở hữu dữ liệu và mức độ nhất quán cần thiết.

Khi tổng hợp từ nhiều module:

- Không truy cập trực tiếp repository nội bộ của module khác.
- Trao đổi qua event contract đã công bố.
- Xác định field nào do module nào sở hữu.
- Thiết kế projection chịu được event đến lệch thời gian.
- Dùng version hoặc timestamp có ý nghĩa rõ ràng, tránh giả định clock giữa các hệ thống hoàn toàn đồng bộ.
- Xác định cách xử lý khi một nguồn tạm thời không phát event hoặc bị trễ.

Một read model tổng hợp có thể tạm thời chứa dữ liệu từ các thời điểm khác nhau. UI và API cần hiểu rằng trạng thái tổng hợp có thể eventual consistent theo từng nguồn.

## Rebuild projection

Read model thường có thể được xây dựng lại từ nguồn dữ liệu đáng tin cậy, nhưng khả năng này phải được thiết kế từ đầu.

Các nguồn rebuild có thể gồm:

- Event log hoặc topic có retention đủ dài.
- Snapshot dữ liệu write model.
- Export hoặc bản lưu trữ sự kiện.
- Một quy trình backfill riêng từ hệ thống nguồn.

Không phải Event Publication Registry nào cũng là event store đầy đủ để replay toàn bộ lịch sử. Registry theo dõi trạng thái publication của listener; khi publication hoàn tất, bản ghi có thể được dọn theo chính sách lưu trữ. Vì vậy, không nên dựa vào registry như nguồn lịch sử vô hạn cho việc rebuild.

Một quy trình rebuild an toàn thường:

1. Tạo bảng hoặc namespace projection mới.
2. Đọc lại dữ liệu nguồn hoặc event history từ một checkpoint xác định.
3. Áp dụng event theo thứ tự và version phù hợp.
4. Theo dõi số lượng, lỗi và độ trễ backfill.
5. Đối chiếu kết quả với nguồn dữ liệu.
6. Chuyển truy vấn sang projection mới khi đã xác nhận.
7. Giữ khả năng rollback trong thời gian chuyển đổi nếu cần.

Nếu projection được cập nhật đồng thời trong khi rebuild, cần xác định checkpoint và cách xử lý event mới để không bỏ sót hoặc áp dụng trùng. Có thể dùng dual-write có kiểm soát sang projection mới hoặc bắt đầu rebuild từ snapshot kèm offset/checkpoint.

## Retry và xử lý lỗi projection

Lỗi projection thường gồm:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Database read model mất kết nối | Retry có backoff |
| Lỗi dữ liệu | Event thiếu field bắt buộc | Ghi nhận lỗi và điều tra hợp đồng |
| Lỗi thứ tự | Version bị thiếu hoặc đến trễ | Chờ event còn thiếu hoặc backfill |
| Lỗi lập trình | Mapping sai hoặc invariant bị vi phạm | Sửa handler, replay có kiểm soát |
| Lỗi tài nguyên | Executor hoặc connection pool quá tải | Giới hạn concurrency và giảm backlog |

Với @ApplicationModuleListener, exception trong transaction listener làm transaction listener thất bại và publication chưa được đánh dấu hoàn tất. Cơ chế retry hoặc resubmission phụ thuộc cấu hình Event Publication Registry, event resubmission và phiên bản Spring Modulith. Cần thiết lập và kiểm thử chính sách phục hồi thực tế; không giả định mọi lỗi sẽ tự retry liên tục hoặc có backoff mặc định như broker.

Không để lỗi projection bị bỏ qua bằng cách bắt exception rồi chỉ ghi log nhưng vẫn trả về thành công. Nếu handler không cập nhật read model, publication có thể bị đánh dấu hoàn tất và hệ thống mất dấu công việc cần xử lý. Nếu lỗi được xem là không thể phục hồi, hãy ghi nhận rõ vào luồng xử lý lỗi hoặc cơ chế quarantine.

## Kiểm thử projection bất đồng bộ

Kiểm thử cần bao phủ cả dữ liệu, transaction, duplicate, ordering và độ trễ:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Publisher commit | Projection listener được gọi sau commit |
| Publisher rollback | Không tạo projection cho thay đổi chưa commit |
| Listener thành công | Read model phản ánh event |
| Listener lỗi | Transaction projection rollback và publication còn trạng thái có thể phục hồi theo cấu hình |
| Event trùng | Read model không bị áp dụng tác động hai lần |
| Event đến sai thứ tự | Version guard ngăn snapshot cũ ghi đè |
| Event bị thiếu | Hệ thống phát hiện gap hoặc có quy trình backfill |
| Executor quá tải | Backlog và độ trễ được quan sát |
| Rebuild | Projection mới đối chiếu đúng với nguồn |

Với listener bất đồng bộ, test không nên giả định projection đã cập nhật ngay khi command trả về. Dùng Awaitility hoặc cơ chế chờ có giới hạn để đợi điều kiện dữ liệu đạt trạng thái mong đợi. Tránh Thread.sleep cố định.

Cần kiểm tra transaction test. Một test được bọc trong transaction chưa commit có thể khiến listener after-commit không được kích hoạt. Hãy commit transaction trong test hoặc dùng cách kiểm thử phù hợp với semantics thực tế.

## Quan sát độ trễ và sức khỏe projection

Projection bất đồng bộ cần metric riêng. Những chỉ số hữu ích:

- Số publication đang pending hoặc incomplete.
- Tuổi của publication cũ nhất.
- Thời gian từ lúc event xảy ra đến khi read model được cập nhật.
- Số listener lỗi và số lần resubmission.
- Backlog executor và thời gian chờ trong queue.
- Tỷ lệ event bị duplicate hoặc bị bỏ qua do version cũ.
- Số event bị thiếu sequence hoặc đang chờ gap.
- Thời gian rebuild/backfill và tỷ lệ lỗi.

Dùng event ID, aggregate ID và correlation ID trong log hoặc trace để điều tra từng luồng. Tránh dùng ID có cardinality cao làm metric label.

Khi projection chậm, kiểm tra lần lượt publisher có commit và ghi publication không, executor có backlog không, listener có lỗi không, database read model có chậm không và có event nào bị retry liên tục không. Chỉ số “command thành công” không đủ để đánh giá sức khỏe projection.

## Quy trình thiết kế projection bất đồng bộ

Khi thêm một read model mới, hãy xác định:

1. Truy vấn nào cần được tối ưu và ai sở hữu read model?
2. Event nào phản ánh đúng thay đổi nghiệp vụ đã commit?
3. Event có đủ dữ liệu, event ID và aggregate version để cập nhật an toàn không?
4. Listener nên chạy bằng @ApplicationModuleListener hay một cơ chế async khác?
5. Publication Registry có persistence và chính sách phục hồi phù hợp không?
6. Projection có idempotent và chống event đến sai thứ tự không?
7. Người dùng sẽ thấy eventual consistency như thế nào?
8. Có nguồn dữ liệu và checkpoint để rebuild projection không?
9. Độ trễ, backlog, retry và lỗi projection được quan sát ra sao?

Projection bất đồng bộ giúp write model tập trung vào nghiệp vụ còn read model tập trung vào truy vấn. Khi event được phát sau commit, listener có transaction riêng, projection có idempotency và version guard, hệ thống có thể chấp nhận độ trễ có kiểm soát mà vẫn giữ dữ liệu đọc nhất quán theo quy tắc đã thiết kế.

## Tài liệu tham khảo

- Spring Modulith Reference — Working with Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Data JPA Reference — Locking: https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html
