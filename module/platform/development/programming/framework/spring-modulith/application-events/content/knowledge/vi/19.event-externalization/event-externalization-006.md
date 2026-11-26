# Externalization và boundary

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp với nhau mà không cần phụ thuộc trực tiếp vào implementation của module khác. Khi một sự kiện cần được gửi ra message broker, một ứng dụng khác hoặc một hệ thống bên ngoài, ta thực hiện *event externalization*. Đây là bước đưa sự kiện qua ranh giới của ứng dụng.

Externalization liên quan trực tiếp đến hai loại ranh giới. Ranh giới module xác định phần nào của mô hình nghiệp vụ được phép chia sẻ bên trong ứng dụng Spring Modulith. Ranh giới hệ thống xác định dữ liệu và hành vi nào được công bố cho consumer bên ngoài. Một thiết kế tốt giữ hai ranh giới này rõ ràng: module sở hữu nghiệp vụ quyết định điều gì đã xảy ra, còn integration contract mô tả thông tin mà hệ thống khác được phép biết.

## 1. Externalization là gì?

Application event thường bắt đầu như một thông điệp nội bộ trong cùng ứng dụng. Ví dụ, module Order phát **OrderConfirmed** sau khi đơn hàng được xác nhận. Module Inventory có thể lắng nghe sự kiện để giữ hàng; module Notification có thể lắng nghe để gửi thông báo. Các module này giao tiếp thông qua hợp đồng event thay vì gọi trực tiếp service hoặc repository của nhau.

Khi một đối tác, một ứng dụng khác hoặc một dịch vụ độc lập cũng cần biết đơn hàng đã được xác nhận, sự kiện phải vượt qua ranh giới tiến trình. Externalization chuyển event nội bộ thành thông điệp có thể được gửi qua một kênh tích hợp như Kafka, AMQP hoặc một adapter messaging khác.

Externalization không đơn thuần là gửi một object Java ra ngoài. Nó là quyết định công bố một phần thông tin nghiệp vụ dưới dạng hợp đồng có thể được consumer độc lập sử dụng. Hợp đồng này cần ổn định, có ý nghĩa với consumer và không phụ thuộc vào cấu trúc triển khai bên trong module phát.

Có thể hình dung luồng như sau:

~~~mermaid
flowchart LR
    A["Order module"] --> B["Application event"]
    B --> C["Externalization boundary"]
    C --> D["Messaging adapter"]
    D --> E["Broker / transport"]
    E --> F["External consumer"]
    F --> G["Consumer model / ACL"]
~~~

Module Order vẫn sở hữu quy tắc xác nhận đơn hàng. Adapter externalization chịu trách nhiệm chuyển hợp đồng đã chọn thành thông điệp trên transport. Consumer bên ngoài tiếp nhận thông điệp và ánh xạ nó vào mô hình riêng của consumer.

## 2. Phân biệt domain event, application event và integration event

Ba khái niệm này có thể cùng mô tả một điều đã xảy ra, nhưng phục vụ các phạm vi khác nhau.

| Loại event | Phạm vi | Mục đích |
|---|---|---|
| Domain event | Bên trong mô hình nghiệp vụ | Diễn đạt một sự kiện có ý nghĩa với domain model |
| Application event nội bộ | Giữa các thành phần hoặc module trong ứng dụng | Kích hoạt xử lý trong cùng ứng dụng |
| Integration event | Qua ranh giới ứng dụng hoặc tổ chức | Công bố một hợp đồng ổn định cho consumer độc lập |

Một domain event có thể chứa kiểu dữ liệu, value object hoặc thông tin chỉ có ý nghĩa trong module sở hữu nó. Những chi tiết đó thường không phù hợp để trở thành payload công khai. Integration event cần được thiết kế riêng theo nhu cầu trao đổi thông tin.

Ví dụ, **OrderAggregateConfirmed** có thể là domain event nội bộ chứa tham chiếu tới aggregate hoặc các chi tiết phục vụ quy tắc của Order. **OrderConfirmedIntegrationEvent** có thể chỉ chứa mã đơn hàng, thời điểm xác nhận, tổng tiền, đơn vị tiền tệ và mã phiên bản hợp đồng. Consumer không cần biết aggregate được lưu thế nào hoặc module Order sử dụng repository nào.

Không phải mọi application event đều cần externalize. Chỉ công bố những sự kiện có ý nghĩa ngoài ứng dụng và có consumer thực sự cần chúng. Nếu một event chỉ phục vụ cập nhật cache nội bộ hoặc điều phối một bước private của module, đưa nó ra broker sẽ làm lộ chi tiết triển khai và tạo thêm hợp đồng phải duy trì.

## 3. Thiết kế boundary trước khi chọn transport

Trước khi cấu hình Kafka, AMQP hay một broker khác, hãy xác định rõ ranh giới công bố.

**Module phát sở hữu ý nghĩa nghiệp vụ.** Module Order quyết định thế nào là đơn hàng đã xác nhận và thời điểm sự kiện đó xảy ra. Consumer không được gọi ngược vào repository nội bộ của Order để diễn giải event.

**Integration contract sở hữu hình dạng dữ liệu công khai.** Payload nên là DTO bất biến, chứa kiểu dữ liệu ổn định và không kéo theo object graph của persistence. Tránh gửi entity JPA, Hibernate proxy, repository, service hoặc class nội bộ của module.

**Consumer sở hữu mô hình tiếp nhận.** Consumer có thể ánh xạ integration event vào model riêng thông qua adapter hoặc anti-corruption layer (ACL). Consumer không nên buộc phải dùng lại entity hoặc class nội bộ của module phát.

**Transport là chi tiết tích hợp.** Topic, exchange, queue, routing key, serializer và credential thuộc cấu hình adapter hoặc hạ tầng. Không để consumer phụ thuộc vào tên class Java hay package nội bộ của module phát.

Ranh giới module và ranh giới hệ thống có quan hệ nhưng không đồng nhất. Một event có thể hợp lệ để chia sẻ giữa hai module trong cùng ứng dụng, nhưng không phù hợp để công bố cho đối tác. Ngược lại, một integration event cần được thiết kế theo hợp đồng bên ngoài ngay cả khi nó được tạo ra từ một module nội bộ.

## 4. Tạo integration event ổn định

Một integration event nên diễn đạt một sự kiện đã xảy ra, thường dùng tên ở thì quá khứ như **OrderConfirmed**, **PaymentCaptured** hoặc **ShipmentDispatched**. Tránh đặt tên theo lệnh như **ConfirmOrder**, vì lệnh yêu cầu consumer thực hiện một hành động; event thông báo một kết quả đã xảy ra.

Ví dụ một hợp đồng xác nhận đơn hàng:

~~~java
public record OrderConfirmedIntegrationEvent(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    int schemaVersion,
    BigDecimal total,
    String currency
) {}
~~~

Các trường có mục đích cụ thể:

- **eventId** định danh duy nhất một lần phát event, hỗ trợ deduplication và idempotency.
- **orderId** xác định aggregate nghiệp vụ liên quan.
- **occurredAt** biểu diễn thời điểm nghiệp vụ xảy ra theo UTC.
- **schemaVersion** giúp consumer nhận biết phiên bản payload.
- **total** và **currency** truyền dữ liệu mà consumer cần, không buộc consumer truy vấn module Order.

Tùy quy trình, có thể bổ sung **correlationId**, **causationId**, **tenantId** hoặc mã trace. Chỉ thêm trường khi có nhu cầu tích hợp rõ ràng. Không đưa toàn bộ aggregate vào event chỉ vì nó đang có sẵn trong bộ nhớ.

Mã định danh event cần ổn định qua các lần retry. Không tạo eventId mới cho mỗi lần gửi lại cùng một sự kiện. Nếu event được tạo từ một thay đổi nghiệp vụ, hãy tạo ID tại thời điểm tạo event và lưu cùng publication để mọi lần giao lại đều dùng cùng định danh.

## 5. Externalize event bằng Spring Modulith

Spring Modulith cung cấp annotation **@Externalized** để đánh dấu application event cần được externalize. Annotation này mô tả đích externalization; adapter được cấu hình trong ứng dụng sẽ ánh xạ đích đó sang cơ chế gửi cụ thể.

Ví dụ:

~~~java
import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmedIntegrationEvent(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    int schemaVersion,
    BigDecimal total,
    String currency
) {}
~~~

Giá trị **"orders"** là định danh đích externalization trong ví dụ. Cấu hình adapter sẽ quyết định nó tương ứng với topic, exchange hoặc đích messaging nào. Không nên mặc định rằng tên này tự động tạo topic hay queue trên broker; hạ tầng và adapter phải được cấu hình tương ứng.

Module Order phát event trong transaction thực hiện thay đổi nghiệp vụ:

~~~java
@Service
class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();
        orders.save(order);

        events.publishEvent(new OrderConfirmedIntegrationEvent(
            UUID.randomUUID(),
            order.getId(),
            clock.instant(),
            1,
            order.total(),
            order.currency()
        ));
    }
}
~~~

Đây là ví dụ minh họa ở tầng application service. Trong hệ thống thực tế, integration event có thể được tạo bằng cách ánh xạ từ domain event hoặc từ kết quả của use case. Điều quan trọng là việc tạo event và ghi nhận publication phải tham gia đúng ranh giới transaction mà ứng dụng thiết kế.

Để externalization hoạt động, ứng dụng cần dependency và cấu hình phù hợp với phiên bản Spring Modulith, cơ chế lưu publication và messaging adapter đang dùng. **@Externalized** xác định event cần công bố; annotation tự nó không thay thế broker, serializer, schema, credential hoặc cấu hình kết nối. Hãy kiểm tra tài liệu của adapter được chọn để cấu hình các thành phần đó đúng phiên bản.

## 6. Giữ ranh giới qua adapter và anti-corruption layer

Một adapter outbound chuyển integration event sang định dạng và transport của hệ thống bên ngoài. Adapter có thể chịu trách nhiệm chọn destination, serialize payload, thêm header, thiết lập key phân vùng và gửi thông điệp.

Ở chiều nhận, consumer nên có inbound adapter để xác thực envelope, kiểm tra phiên bản, xử lý trùng và chuyển dữ liệu sang use case nội bộ. Nếu mô hình của consumer khác mô hình của producer, ACL sẽ thực hiện ánh xạ và bảo vệ domain model của consumer khỏi khái niệm hoặc quy tắc của producer.

~~~mermaid
flowchart TB
    subgraph Producer["Producer application"]
        A["Order domain"] --> B["Integration event DTO"]
        B --> C["Externalization adapter"]
    end
    C --> D["Broker"]
    subgraph Consumer["Consumer application"]
        D --> E["Inbound adapter"]
        E --> F["Schema validation / deduplication"]
        F --> G["Anti-corruption layer"]
        G --> H["Consumer use case"]
    end
~~~

Cách tổ chức này tạo ra hai hợp đồng rõ ràng: hợp đồng event mà producer cam kết công bố và mô hình nội bộ mà consumer tự quản lý. Consumer có thể thay đổi cách lưu dữ liệu hoặc cách tổ chức module mà không yêu cầu producer thay đổi theo, miễn là integration contract vẫn tương thích.

Không nên chia sẻ cùng một Java library chứa toàn bộ model của producer cho mọi consumer. Cách đó dễ tạo coupling ở compile time và khiến thay đổi nội bộ lan sang hệ thống khác. Nếu cần schema dùng chung, hãy quản lý schema như một contract có version và quy trình tương thích độc lập với implementation của module phát.

## 7. Versioning và khả năng tương thích

Một integration event có thể tồn tại lâu hơn phiên bản ứng dụng đã phát ra nó. Broker có thể giữ message, consumer có thể triển khai chậm hơn producer và nhiều phiên bản consumer có thể cùng hoạt động trong một giai đoạn nâng cấp. Vì vậy, thay đổi schema cần có chiến lược tương thích.

Một số nguyên tắc hữu ích:

- Ưu tiên bổ sung field tùy chọn có default hợp lý khi consumer cũ có thể bỏ qua field lạ.
- Không đổi ý nghĩa của field hiện có dù vẫn giữ nguyên tên và kiểu.
- Không đổi kiểu dữ liệu hoặc xóa field đang được consumer sử dụng mà không có kế hoạch chuyển đổi.
- Dùng schema version khi thay đổi cấu trúc hoặc ngữ nghĩa cần được consumer nhận biết.
- Duy trì thời gian chuyển tiếp để producer và consumer triển khai theo nhịp riêng.
- Có thể tạo event contract mới khi thay đổi không tương thích, thay vì sửa âm thầm hợp đồng cũ.

Ví dụ, nếu bổ sung thông tin vận chuyển vào **OrderConfirmedIntegrationEvent**, consumer cũ có thể bỏ qua field mới nếu schema và serializer cho phép. Nhưng nếu đổi **total** từ tổng tiền trước thuế thành tổng tiền sau thuế, đó là thay đổi ngữ nghĩa và cần được công bố rõ ràng.

Không nên dựa vào tên class Java làm định danh schema công khai. Dùng event type ổn định và version rõ ràng trong metadata hoặc schema registry nếu hệ thống sử dụng. Việc đổi package hoặc refactor tên class không nên buộc consumer bên ngoài phải đổi theo.

## 8. Độ tin cậy, transaction và duplicate delivery

Transaction cơ sở dữ liệu của producer không thể bao trùm transaction của broker và mọi hệ thống consumer. Sau khi transaction nghiệp vụ commit, việc gửi thông điệp có thể thất bại do broker không khả dụng, mạng gián đoạn hoặc ứng dụng dừng. Đây là lý do cần theo dõi publication và có khả năng phục hồi.

Spring Modulith Event Publication Registry có thể theo dõi publication cần externalize và trạng thái hoàn tất của chúng. Để phục hồi sau khi process dừng, registry cần được cấu hình với cơ chế lưu trữ bền vững phù hợp. Cách lưu publication phải tham gia transaction cùng thay đổi nghiệp vụ để không tạo ra khoảng trống giữa việc commit dữ liệu và việc ghi nhận event cần gửi.

Luồng khái quát:

1. Use case cập nhật trạng thái nghiệp vụ trong transaction.
2. Application event được phát và publication cần externalize được ghi nhận.
3. Transaction commit.
4. Externalization adapter gửi thông điệp tới transport.
5. Khi adapter xác nhận việc gửi theo cơ chế của nó, publication được đánh dấu hoàn tất.
6. Nếu gửi thất bại, publication còn dang dở có thể được xem xét gửi lại theo chính sách phục hồi.

Publication hoàn tất chỉ thể hiện trạng thái của bước externalization theo adapter. Nó không chứng minh consumer đã hoàn thành nghiệp vụ của họ. Nếu producer cần biết consumer đã xử lý thành công, cần một acknowledgement event, callback hoặc quy trình đối soát riêng.

Một message có thể được gửi lại khi hệ thống không chắc lần gửi trước đã thành công hay chưa. Vì vậy, consumer cần idempotent. Dùng **eventId** làm khóa chống trùng; lưu dấu đã xử lý trong cùng transaction với thay đổi nghiệp vụ của consumer. Nếu consumer gọi API ngoài, truyền cùng idempotency key qua các lần thử khi API hỗ trợ.

~~~sql
CREATE TABLE consumed_event (
    event_id UUID PRIMARY KEY,
    consumed_at TIMESTAMP NOT NULL
);
~~~

Bảng trên là minh họa cho inbox/deduplication ở consumer. Khi xử lý message, consumer ghi **eventId** vào bảng và cập nhật dữ liệu nghiệp vụ trong cùng transaction. Nếu eventId đã tồn tại, consumer nhận biết message đã được xử lý và kết thúc mà không lặp lại tác dụng phụ. Cách xử lý xung đột cụ thể tùy thuộc hệ quản trị cơ sở dữ liệu.

Không nên hứa hẹn exactly-once end-to-end chỉ vì có publication registry hoặc broker hỗ trợ giao nhận. Độ tin cậy thực tế đến từ publication bền vững, retry có kiểm soát, consumer idempotent và khả năng đối soát.

## 9. Ordering, partitioning và correlation

Không phải mọi integration event đều cần thứ tự toàn cục. Nếu consumer cần xử lý các thay đổi của cùng một đơn hàng theo đúng thứ tự, hãy xác định ordering key, thường là **orderId**, và cấu hình partition hoặc routing key phù hợp với broker.

Ordering có giới hạn theo phạm vi mà transport hỗ trợ. Hai event thuộc hai aggregate khác nhau có thể được xử lý song song. Retry hoặc nhiều consumer cũng có thể làm thay đổi thời điểm hoàn tất. Vì vậy, consumer nên kiểm tra phiên bản hoặc sequence của aggregate nếu nghiệp vụ không cho phép áp dụng event cũ sau event mới.

**correlationId** giúp liên kết nhiều event của cùng một quy trình; **causationId** cho biết event hoặc command nào đã dẫn đến event hiện tại. Kết hợp các trường này với trace context giúp theo dõi một giao dịch nghiệp vụ xuyên qua nhiều ứng dụng.

Nếu event chỉ mang trạng thái mới nhất của một aggregate, consumer có thể thiết kế xử lý theo kiểu cập nhật projection và bỏ qua phiên bản cũ. Nếu event biểu diễn một hành động không thể bỏ qua như ghi nhận thanh toán, consumer cần lưu và xử lý từng event theo định danh riêng.

## 10. Bảo mật và quyền công bố dữ liệu

Externalization mở rộng phạm vi dữ liệu ra khỏi tiến trình sở hữu nó. Trước khi công bố, cần xác định consumer nào được phép nhận dữ liệu và mục đích sử dụng của họ.

- Chỉ gửi field cần thiết cho use case của consumer.
- Không gửi mật khẩu, token, secret, thông tin xác thực hoặc dữ liệu nhạy cảm không cần thiết.
- Xác định cách xử lý dữ liệu cá nhân, thời hạn lưu trữ và yêu cầu xóa theo chính sách của tổ chức.
- Dùng TLS và cơ chế xác thực phù hợp cho kết nối broker.
- Phân quyền publish/subscribe theo topic, exchange hoặc destination.
- Không đặt thông tin bí mật trong routing key, header hoặc log.
- Kiểm tra tenant hoặc phạm vi dữ liệu khi ứng dụng phục vụ nhiều khách hàng.
- Có quy trình thay đổi credential và thu hồi quyền truy cập.

Một integration event là dữ liệu được công bố theo hợp đồng. Khi đã gửi ra ngoài, producer không thể giả định rằng mọi consumer sẽ xóa bản sao ngay khi producer thay đổi hoặc xóa dữ liệu nội bộ. Vì vậy, hãy cân nhắc kỹ payload và chính sách lưu trữ trước khi phát event.

## 11. Quan sát và xử lý sự cố

Cần theo dõi cả trạng thái externalization và trạng thái tiêu thụ ở phía consumer. Producer nên quan sát số publication chưa hoàn tất, tuổi publication lâu nhất, số lần retry, tỷ lệ gửi thành công, thời gian gửi và lỗi theo destination. Consumer nên quan sát lag, số message lỗi, số lần xử lý trùng, thời gian xử lý và số message chuyển sang dead-letter queue nếu broker hỗ trợ.

Log có cấu trúc nên mang theo **eventId**, event type, schema version, aggregate ID, destination, correlation ID và mã lỗi. Tránh ghi toàn bộ payload nếu payload có dữ liệu nhạy cảm. Trace nên nối được từ thao tác nghiệp vụ ở producer đến lần gửi và lần nhận ở consumer.

Khi publication bị kẹt, quy trình vận hành cần giúp xác định:

1. Transaction nghiệp vụ đã commit chưa?
2. Publication có được ghi vào registry bền vững không?
3. Adapter có thể kết nối broker và serialize payload không?
4. Broker có nhận message không?
5. Consumer có nhận message và xử lý được không?
6. Lỗi nằm ở producer, transport hay consumer?

Chỉ retry sau khi xác định nguyên nhân và điều kiện an toàn. Retry có backoff, jitter và giới hạn giúp giảm áp lực lên broker hoặc dịch vụ đang gặp sự cố. Publication vượt giới hạn cần được cảnh báo và chuyển sang xử lý có kiểm soát. Không xóa publication chưa hoàn tất chỉ để làm sạch dashboard nếu chưa xác định được trạng thái nghiệp vụ và khả năng giao event.

## 12. Kiểm thử boundary và integration contract

Kiểm thử externalization cần xác minh hợp đồng công khai và hành vi qua ranh giới. Unit test cho domain logic không đủ để chứng minh event được serialize đúng hoặc consumer có thể hiểu payload.

Các nhóm kiểm thử nên cân nhắc:

1. **Domain/application test:** xác nhận use case chỉ phát integration event khi điều kiện nghiệp vụ thành công.
2. **Rollback test:** khi transaction rollback, không để lại publication đã commit cho thay đổi chưa xảy ra.
3. **Externalization test:** xác nhận event được đánh dấu externalized và ánh xạ đến destination mong đợi.
4. **Serialization test:** xác nhận payload, header, event type và schema version đúng contract.
5. **Compatibility test:** xác nhận consumer hiện tại đọc được phiên bản event producer phát ra.
6. **Failure/retry test:** broker tạm thời không khả dụng, publication còn có thể phục hồi sau khi dịch vụ hoạt động lại.
7. **Duplicate test:** gửi cùng eventId nhiều lần nhưng consumer không lặp tác dụng phụ.
8. **Security test:** xác nhận producer chỉ gửi tới destination được cấp quyền và payload không chứa field bị cấm.
9. **End-to-end test:** kiểm tra luồng từ use case producer đến inbound adapter của consumer trong môi trường tích hợp.

Consumer-driven contract test có thể giúp producer biết những field và ngữ nghĩa nào consumer đang phụ thuộc. Tuy nhiên, contract test không thay thế kiểm thử khả năng phục hồi của broker hoặc kiểm thử transaction của publication registry.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Externalize mọi application event | Lộ chi tiết nội bộ và tăng coupling | Chỉ công bố event có ý nghĩa tích hợp |
| Gửi trực tiếp entity JPA | Payload gắn với persistence và khó version | Dùng integration DTO riêng |
| Consumer dùng class nội bộ của producer | Thay đổi module lan sang hệ thống khác | Consumer ánh xạ qua inbound adapter/ACL |
| Đổi schema mà không thông báo | Consumer cũ lỗi hoặc hiểu sai dữ liệu | Versioning và kiểm tra tương thích |
| Giả định gửi một lần duy nhất | Tác dụng phụ bị lặp khi retry | Dùng eventId và idempotent consumer |
| Coi publication completed là consumer completed | Mất khả năng quan sát tiến trình downstream | Dùng acknowledgement hoặc đối soát riêng |
| Không có lưu trữ publication bền vững | Mất khả năng phục hồi sau restart | Cấu hình registry persistence phù hợp |
| Đưa dữ liệu nhạy cảm vào payload | Mở rộng phạm vi rò rỉ dữ liệu | Data minimization và phân quyền |

## 14. Quy trình thiết kế externalization

Khi cần đưa một event qua ranh giới hệ thống, có thể thực hiện theo trình tự:

1. Xác định consumer và quyết định nghiệp vụ nào họ cần biết.
2. Xác định event thuộc domain nội bộ, application nội bộ hay integration contract.
3. Thiết kế integration DTO độc lập với entity và package nội bộ.
4. Chốt event type, eventId, schema version, thời điểm và correlation metadata.
5. Đánh dấu event cần externalize bằng **@Externalized** và cấu hình adapter cho destination tương ứng.
6. Cấu hình publication registry bền vững, transaction và kết nối transport.
7. Thiết kế inbound adapter, ACL, deduplication và xử lý lỗi ở consumer.
8. Xác định versioning, security, retention, retry và quy trình vận hành.
9. Kiểm thử contract, serialization, rollback, duplicate delivery và phục hồi sau lỗi.

Externalization trong Spring Modulith là cách đưa application events qua ranh giới ứng dụng với một hợp đồng có chủ đích. Khi module phát giữ quyền sở hữu nghiệp vụ, integration event chỉ công bố dữ liệu cần thiết, adapter cô lập transport và consumer bảo vệ mô hình riêng, hệ thống có thể tích hợp với bên ngoài mà vẫn giữ được ranh giới module và khả năng thay đổi độc lập.

