# Event mang quá nhiều dữ liệu

Event mang quá nhiều dữ liệu là anti-pattern trong đó publisher đưa gần như toàn bộ entity, request hoặc object graph vào payload, dù phần lớn listener chỉ cần một vài thông tin để phản ứng với sự kiện. Payload lớn làm tăng phụ thuộc giữa module, chi phí serialize/deserialize, dung lượng lưu trữ và truyền tải; nó còn có thể làm lộ dữ liệu nhạy cảm và khiến consumer xử lý dựa trên một snapshot cũ mà không nhận ra.

Trong Spring Modulith, application events giúp các module giao tiếp qua hợp đồng nghiệp vụ. `@ApplicationModuleListener` cho phép module nhận xử lý event bất đồng bộ sau commit; Event Publication Registry theo dõi publication đến transactional listener. Các cơ chế này không tự làm payload trở nên gọn hoặc an toàn. Thiết kế event cần chọn đúng dữ liệu mà consumer cần, giữ ý nghĩa tại thời điểm phát và giới hạn những gì đi qua ranh giới module.

## 1. Nhận diện anti-pattern

Một event thường bị phình to khi publisher:

- Đưa toàn bộ JPA entity hoặc aggregate vào constructor của event.
- Serialize nguyên request DTO từ REST API, bao gồm trường chỉ phục vụ giao diện.
- Gắn cả object graph như customer, address, payment, shipment, audit history và danh sách file đính kèm.
- Thêm trường “phòng khi consumer khác cần” dù chưa có use case cụ thể.
- Dùng một event chung cho mọi consumer với payload là superset của mọi nhu cầu.
- Nhúng nội dung file, ảnh, PDF hoặc dữ liệu nhị phân trực tiếp vào event.
- Đưa token, credential, dữ liệu cá nhân hoặc thông tin thanh toán vào payload.

Ví dụ, module Order phát `OrderPlaced` với toàn bộ đối tượng đơn hàng, hồ sơ khách hàng, địa chỉ, lịch sử trạng thái, dữ liệu thanh toán và ảnh sản phẩm. Trong khi đó, listener Inventory chỉ cần mã đơn và các dòng sản phẩm; listener Notification chỉ cần mã đơn và một số thông tin hiển thị đã được phép chia sẻ.

```java
// Anti-pattern: event mang entity graph và dữ liệu không liên quan.
public record OrderPlaced(
        Order order,
        Customer customer,
        Payment payment,
        List<Shipment> shipments,
        List<AuditEntry> history,
        byte[] invoicePdf
) {}
```

Event trên không thể hiện rõ hợp đồng mà consumer được phép sử dụng. Nó buộc listener hiểu cấu trúc nội bộ của nhiều aggregate/entity và có thể kéo theo lazy relationship, proxy persistence hoặc dữ liệu nhạy cảm.

## 2. Vì sao payload lớn gây hại?

| Hệ quả | Nguyên nhân | Tác động |
| --- | --- | --- |
| Coupling tăng | Consumer phụ thuộc vào nhiều field và cấu trúc entity nội bộ. | Thay đổi module nguồn có thể làm hỏng nhiều listener. |
| Chi phí xử lý cao | Serialize, deserialize, copy và cấp phát object lớn. | CPU, heap, GC và latency tăng. |
| Lưu trữ phình to | Payload được giữ trong publication store, broker, retry, DLQ hoặc archive tùy cấu hình. | Tăng dung lượng, backup và chi phí vận hành. |
| Rò rỉ dữ liệu | Event chứa nhiều trường hơn quyền cần thiết của consumer. | Tăng phạm vi ảnh hưởng khi log, broker hoặc consumer bị truy cập trái phép. |
| Dữ liệu lỗi thời | Snapshot lớn có thể cũ trước khi listener xử lý. | Consumer ghi đè dữ liệu mới hoặc quyết định dựa trên trạng thái không còn đúng. |
| Khó version hóa | Nhiều field và object lồng nhau tạo nhiều điểm phá vỡ contract. | Migration và replay phức tạp. |
| Giới hạn hạ tầng | Broker, HTTP bridge hoặc serializer có giới hạn kích thước message. | Publish thất bại, phân mảnh hoặc phải tăng cấu hình thiếu kiểm soát. |
| Kiểm thử khó | Fixture phải dựng nhiều object và quan hệ không liên quan. | Test dễ phụ thuộc implementation và khó đọc. |

Payload lớn không phải lúc nào cũng sai. Một event snapshot có thể cần nhiều dữ liệu để tái tạo đúng trạng thái tại thời điểm xảy ra. Vấn đề xuất hiện khi dữ liệu được đưa vào chỉ vì tiện, không có consumer cụ thể, hoặc không có giới hạn rõ về mục đích, quyền truy cập và retention.

## 3. Event là hợp đồng nghiệp vụ, không phải bản sao database

Event nên mô tả một sự kiện đã xảy ra và mang đủ thông tin để consumer thực hiện trách nhiệm đã xác định. Event không nên là bản dump của aggregate hoặc DTO của một endpoint.

Ví dụ một event gọn:

```java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        long orderVersion,
        Instant occurredAt,
        List<OrderLinePlaced> lines
) {}

public record OrderLinePlaced(
        UUID productId,
        int quantity
) {}
```

Event này mang mã định danh, version và dữ liệu dòng hàng cần thiết để listener Inventory giữ tồn kho. Nó không mang địa chỉ, token, lịch sử audit, ảnh sản phẩm hoặc entity Customer.

Trước khi thêm field, hãy trả lời:

1. Consumer nào cần field này?
2. Consumer dùng field để làm quyết định hoặc cập nhật nào?
3. Field có phải một phần của sự kiện tại thời điểm phát hay chỉ là dữ liệu có thể truy vấn sau?
4. Có thể dùng ID/reference thay cho object đầy đủ không?
5. Field có làm tăng quyền truy cập dữ liệu hoặc tạo rủi ro retention không?
6. Nếu bỏ field, consumer có thể hoàn thành trách nhiệm bằng hợp đồng công khai khác không?

Nếu không xác định được consumer và mục đích cụ thể, không nên thêm field vào event chỉ để dự phòng.

## 4. Chọn dữ liệu theo semantics của event

Có hai nhu cầu thường bị nhầm lẫn:

- Consumer cần biết *điều gì đã xảy ra* tại thời điểm event được tạo.
- Consumer cần biết *trạng thái hiện tại* của một đối tượng khi nó bắt đầu xử lý.

Hai nhu cầu này không giống nhau. Nếu event biểu diễn một fact lịch sử, payload nên giữ các giá trị cần thiết để diễn giải fact tại thời điểm xảy ra. Nếu consumer cần trạng thái hiện tại, nó có thể truy vấn API công khai của module sở hữu dữ liệu bằng reference.

Ví dụ, `OrderPlaced` có thể mang giá bán và số lượng tại thời điểm đặt hàng nếu Billing cần tính toán dựa trên snapshot đã chốt. Không nên chỉ truyền `orderId` rồi truy vấn giá hiện tại nếu giá sản phẩm có thể thay đổi sau đó. Ngược lại, listener gửi email có thể chỉ cần `orderId` và `customerReference`, sau đó gọi một API được bảo vệ để lấy thông tin liên hệ hiện tại.

| Nhu cầu | Dữ liệu phù hợp |
| --- | --- |
| Tái tạo fact tại thời điểm phát | Snapshot tối thiểu gồm các giá trị bất biến cần cho nghiệp vụ. |
| Đọc trạng thái mới nhất | Aggregate ID/reference và API/query công khai. |
| Giữ thứ tự thay đổi | Aggregate ID cùng aggregate version/sequence. |
| Chống xử lý trùng | Event ID ổn định. |
| Truy vết luồng | Correlation ID/causation ID ở mức metadata cần thiết. |
| Xử lý file lớn | Object reference có quyền truy cập riêng, checksum và metadata. |

## 5. Thay entity bằng event DTO rõ ràng

Không phát JPA entity trực tiếp. Entity thường chứa quan hệ hai chiều, lazy proxy, field persistence, trạng thái mutable và dữ liệu nội bộ. Serialize entity có thể vô tình tải thêm quan hệ hoặc làm payload thay đổi khi schema database thay đổi.

Thay vào đó, tạo record/DTO event riêng:

```java
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        BigDecimal totalAmount,
        String currency,
        Instant occurredAt
) {}
```

Publisher ánh xạ từ aggregate sang event contract:

```java
@Service
public class ConfirmOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public ConfirmOrderService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();
        orders.save(order);

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.getId(),
                order.getVersion(),
                order.getTotalAmount(),
                order.getCurrency(),
                clock.instant()
        ));
    }
}
```

Event DTO tạo ranh giới rõ: consumer chỉ thấy những field được công bố. Khi entity thêm quan hệ hoặc field nội bộ, contract không tự phình ra. Khi contract thay đổi, thay đổi đó được review và version hóa có chủ đích.

## 6. Tránh truyền dữ liệu nhạy cảm và dữ liệu không cần thiết

Payload càng lớn thì bề mặt dữ liệu càng rộng. Event có thể đi qua nhiều listener, publication persistence, broker, retry store, DLQ, log, trace và backup. Không nên đưa vào event các dữ liệu như password, access token, refresh token, private key, session cookie hoặc CVV.

Với thông tin cá nhân hoặc tài chính, chỉ truyền trường thực sự cần cho consumer được phép. Có thể dùng reference/token thay cho giá trị gốc, nhưng reference vẫn có thể là dữ liệu định danh nếu hệ thống liên kết ngược được.

Ví dụ, thay vì gửi email và địa chỉ giao hàng trong mọi event:

```java
public record ShipmentRequested(
        UUID eventId,
        UUID orderId,
        UUID deliveryProfileReference,
        Instant requestedAt
) {}
```

Module Shipping dùng service identity riêng để gọi API lấy phần thông tin giao hàng được phép. API phải xác thực consumer, kiểm tra quyền theo mục đích và ghi audit. Biết `deliveryProfileReference` không đồng nghĩa với có quyền đọc dữ liệu.

Nếu nghiệp vụ cần chính xác địa chỉ đã chốt tại thời điểm đặt hàng, event có thể chứa một snapshot tối thiểu đã được phê duyệt thay vì truy vấn trạng thái hiện tại. Quyết định này cần được ghi rõ trong contract.

## 7. Dùng reference thay cho object graph

Reference giúp event nhỏ và giảm phụ thuộc vào cấu trúc module sở hữu dữ liệu. Một reference tốt thường là ID ổn định hoặc opaque reference, không phải URL chứa credential hoặc signed URL có thời hạn dài.

| Truyền object đầy đủ | Truyền reference |
| --- | --- |
| Consumer nhận cả field không cần thiết. | Consumer chỉ biết định danh cần thiết. |
| Payload có thể stale và khó version hóa. | Consumer truy vấn dữ liệu theo contract hiện tại hoặc snapshot/version được yêu cầu. |
| Tăng dung lượng và phạm vi rò rỉ. | Payload nhỏ hơn, quyền truy cập được kiểm soát tại API. |
| Consumer phụ thuộc cấu trúc object nguồn. | Consumer phụ thuộc API công khai và chính sách authorization. |

Reference có trade-off: consumer cần gọi API khác và dữ liệu có thể đã thay đổi kể từ khi event phát. Nếu cần snapshot chính xác, truyền một tập field tối thiểu hoặc version tham chiếu để consumer lấy đúng phiên bản. Không dùng reference để né tránh quyết định về consistency.

## 8. Chia event theo mục đích consumer khi cần

Một event không nên trở thành superset của mọi nhu cầu chỉ vì có nhiều listener. Tuy nhiên, cũng không nên tạo một event riêng cho từng listener nếu chúng đều phản ứng với cùng một fact và dùng cùng contract.

Hãy phân biệt:

- **Domain event:** mô tả fact trong domain, được module nguồn công bố cho các module nội bộ có liên quan.
- **Integration event:** hợp đồng được thiết kế để truyền qua ranh giới process hoặc tổ chức khác.
- **Projection event/snapshot:** mang dữ liệu đã chọn để dựng một read model cụ thể.

Ví dụ `OrderConfirmed` là domain event với order ID, version, tổng tiền và currency. Khi gửi ra đối tác vận chuyển, tạo integration event `ShipmentRequested` chỉ chứa dữ liệu vận chuyển được phép. Không thêm email, dữ liệu thanh toán và audit history vào `OrderConfirmed` chỉ vì một integration consumer có thể muốn dùng.

Nếu hai consumer cần mức dữ liệu hoặc quyền truy cập rất khác nhau, hãy cân nhắc event chuyên biệt hoặc API reference. Cần bảo đảm event chuyên biệt vẫn phản ánh một fact/contract rõ ràng, có owner và chính sách versioning.

## 9. Xử lý payload lớn như file và dữ liệu nhị phân

Không nhúng ảnh, PDF, video hoặc blob lớn trực tiếp vào application event. Payload nhị phân làm tăng heap, chi phí serialize, thời gian truyền, kích thước publication store và khả năng vượt giới hạn broker.

Thay vào đó, lưu file trong object storage hoặc kho tài liệu phù hợp, sau đó phát reference và metadata tối thiểu:

```java
public record DocumentReady(
        UUID eventId,
        UUID documentId,
        String objectKey,
        String mediaType,
        long sizeBytes,
        String sha256,
        Instant createdAt
) {}
```

`objectKey` không nên là public URL hoặc chứa credential. Consumer dùng service identity để lấy file qua API/storage gateway có authorization. `sha256` giúp kiểm tra integrity; `sizeBytes` và `mediaType` cho phép consumer quyết định cách xử lý trước khi tải.

Quy trình lưu file và phát event cần xử lý consistency. Nếu file được lưu nhưng transaction nguồn rollback, có thể tạo object mồ côi. Nếu event commit nhưng upload chưa hoàn tất, consumer nhận reference không truy cập được. Có thể dùng trạng thái upload, outbox, cleanup job và một bước xác nhận file sẵn sàng trước khi phát `DocumentReady`.

Với file rất lớn, cân nhắc streaming/chunking ở giao thức chuyên dụng. Không chia một file thành hàng nghìn application event nhỏ nếu event bus không được thiết kế làm data transfer channel.

## 10. Giữ event bất biến và tránh dữ liệu mutable

Event nên là immutable fact. Nếu publisher phát một collection mutable rồi tiếp tục sửa collection đó, listener có thể quan sát nội dung khác nhau tùy thời điểm xử lý. Với listener bất đồng bộ, rủi ro này đặc biệt dễ xảy ra nếu payload giữ reference đến object mutable.

Nên dùng record và defensive copy:

```java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        List<OrderLinePlaced> lines
) {
    public OrderPlaced {
        lines = List.copyOf(lines);
    }
}
```

Các phần tử trong collection cũng nên bất biến. `List.copyOf` chỉ tạo collection không thể sửa; nếu phần tử là object mutable, consumer vẫn có thể nhìn thấy thay đổi từ object đó. Dùng value object/record bất biến cho nested data.

## 11. Giới hạn kích thước và độ sâu payload

Đặt giới hạn có chủ đích cho:

- Số phần tử tối đa trong collection.
- Độ sâu object graph.
- Kích thước chuỗi và trường metadata.
- Tổng số byte sau serialize.
- Kích thước file reference metadata.
- Số event phát sinh cho một thao tác nghiệp vụ.

Không chọn một ngưỡng tùy tiện rồi áp dụng cho mọi event. Xác định giới hạn dựa trên transport, serializer, database, broker, SLO và mức tiêu thụ memory. Với event nội bộ không serialize, payload vẫn có thể gây chi phí heap và GC; với publication persistence/externalization, cần tính cả kích thước serialized.

Có thể đo kích thước serialized trong test hoặc metric ở adapter, nhưng tránh ghi payload đầy đủ vào log để debug. Nếu vượt ngưỡng, cân nhắc thu nhỏ contract, chia nghiệp vụ thành các event có ý nghĩa hoặc chuyển dữ liệu lớn sang object storage.

## 12. Ảnh hưởng đến Event Publication Registry

Event Publication Registry theo dõi publication đến transactional listener. Tùy persistence adapter/cấu hình, dữ liệu event có thể được serialize và lưu cùng trạng thái publication. Vì vậy, payload quá lớn có thể làm tăng dung lượng database, backup, thời gian ghi/đọc và chi phí cleanup.

Không giả định registry chỉ lưu event ID và metadata nhỏ. Hãy xác minh persistence adapter và cách serialize trong phiên bản ứng dụng. Cũng không giả định mọi application event đều được lưu bền vững nếu ứng dụng không cấu hình persistence registry tương ứng.

Các nguyên tắc:

- Giữ event nhỏ trước khi publish.
- Không dùng registry làm kho file hoặc event store lịch sử.
- Theo dõi dung lượng và tuổi publication incomplete.
- Đặt retention/cleanup phù hợp với khả năng phục hồi.
- Không sửa trực tiếp bảng nội bộ để xóa payload lớn hoặc đánh dấu publication hoàn tất.

## 13. Ảnh hưởng đến broker và retry

Khi event được externalize, payload lớn làm tăng network throughput, disk usage, replication traffic và thời gian consumer deserialize. Broker có thể có giới hạn message size; tăng giới hạn chỉ để chấp nhận event phình to có thể gây áp lực lên toàn cluster.

Khi retry hoặc redelivery, cùng payload lớn có thể được đọc và truyền nhiều lần. DLQ cũng giữ lại payload, làm tăng dung lượng và mở rộng phạm vi truy cập dữ liệu. Với event có file reference, retry chỉ truyền metadata nhỏ; consumer tải file khi thực sự cần và theo quyền của nó.

Nếu broker message size gần giới hạn, kiểm tra serializer framing, header và compression. Compression giảm byte truyền trong một số trường hợp nhưng không loại bỏ coupling, chi phí giải nén, heap hoặc rủi ro dữ liệu nhạy cảm. Không coi compression là giải pháp thiết kế payload.

## 14. Consistency và dữ liệu thay đổi giữa publish và consume

Payload snapshot và reference tạo ra hai semantics khác nhau:

- Snapshot giữ giá trị tại thời điểm event xảy ra.
- Reference cho phép consumer lấy dữ liệu tại thời điểm xử lý.

Giả sử `OrderPlaced` được phát lúc giá sản phẩm là 100. Listener chạy sau vài phút khi giá hiện tại là 120. Nếu listener tính hóa đơn từ API giá hiện tại, nó có thể dùng sai giá so với giao dịch đã chốt. Trong trường hợp này, event cần mang giá và currency tại thời điểm đặt hàng hoặc reference đến snapshot/version bất biến.

Ngược lại, listener gửi thông báo có thể cần tên hiển thị hiện tại của khách hàng, nên truy vấn API theo reference là phù hợp. Contract cần mô tả rõ consumer đọc snapshot hay current state.

Không truyền toàn bộ object để tránh stale data; hãy chọn một trong hai semantics và truyền đúng lượng dữ liệu để thực hiện nó.

## 15. Versioning khi thu nhỏ hoặc tách payload

Loại bỏ field khỏi event có thể là breaking change nếu consumer đang sử dụng field đó. Thu nhỏ payload nên được thực hiện như một thay đổi contract có kế hoạch:

1. Liệt kê consumer và field đang được sử dụng.
2. Công bố API/reference hoặc event chuyên biệt thay thế.
3. Cập nhật consumer để không còn phụ thuộc field cũ.
4. Có thể giữ field cũ trong giai đoạn chuyển tiếp nếu contract cho phép.
5. Theo dõi consumer/version và lỗi deserialize.
6. Loại bỏ field sau khi mọi consumer và retry/replay window đã được xử lý.

Nếu thay đổi semantics hoặc xóa trường bắt buộc, tăng schema version hoặc tạo event type mới theo chính sách versioning. Không âm thầm xóa field rồi chờ consumer lỗi ở production.

## 16. Kiểm thử event payload

Kiểm thử nên xác nhận event chứa đúng dữ liệu cần thiết và không mang object graph ngoài ý muốn:

1. Event chỉ có các field thuộc contract đã công bố.
2. Không có JPA entity, Hibernate proxy hoặc collection lazy trong payload.
3. Không có password, token, credential, CVV hoặc dữ liệu cá nhân không cần thiết.
4. Collection có giới hạn hợp lý và nested value object bất biến.
5. Snapshot giữ đúng giá trị tại thời điểm nghiệp vụ xảy ra.
6. Reference trỏ đến API/resource được bảo vệ và consumer có quyền phù hợp.
7. Payload lớn/file dùng object storage reference và checksum.
8. Serialization/deserialization giữ đúng semantics và schema version.
9. Kích thước serialized nằm trong giới hạn được định nghĩa.
10. Retry/replay không yêu cầu event ID mới hoặc tạo side effect trùng.

Ví dụ unit test có thể capture event:

```java
@Test
void publishesMinimalOrderPlacedEvent() {
    UUID orderId = UUID.randomUUID();
    Order order = orderWithTwoLines(orderId);

    when(orders.findById(orderId)).thenReturn(Optional.of(order));

    service.place(orderId);

    ArgumentCaptor<OrderPlaced> captor =
            ArgumentCaptor.forClass(OrderPlaced.class);
    verify(events).publishEvent(captor.capture());

    OrderPlaced event = captor.getValue();
    assertThat(event.orderId()).isEqualTo(orderId);
    assertThat(event.lines()).hasSize(2);
    assertThat(event.lines()).allSatisfy(line -> {
        assertThat(line.productId()).isNotNull();
        assertThat(line.quantity()).isPositive();
    });
}
```

Test này minh họa kiểm tra hợp đồng ở cấp publisher. Có thể bổ sung contract test cho serializer và integration test cho broker khi event externalized. Không cần assert rằng event không có mọi field khác bằng reflection nếu contract test/record type đã thể hiện rõ schema; ưu tiên kiểm tra payload và hành vi mà consumer cần.

## 17. Quan sát kích thước và chất lượng payload

Các metric có thể theo dõi:

- Serialized payload size theo event type.
- Số event vượt ngưỡng cảnh báo.
- Thời gian serialize/deserialize.
- Publication persistence size hoặc dung lượng bảng registry theo adapter.
- Broker message size, throughput và consumer processing latency.
- Tỷ lệ lỗi deserialize và retry liên quan payload.

Metric tag chỉ nên dùng event type, schema version và outcome có cardinality thấp. Không dùng event ID, order ID hoặc customer ID làm nhãn. Không log toàn payload để đo kích thước; đo byte count tại serializer/adapter và ghi metadata cần thiết.

Khi payload size tăng đột biến sau deploy, kiểm tra thay đổi schema, nested relationship, collection growth và serializer configuration. So sánh phân vị p50/p95/p99 thay vì chỉ nhìn trung bình vì một số event có thể chứa collection lớn bất thường.

## 18. Checklist thiết kế event gọn

- [ ] Event mô tả một fact nghiệp vụ rõ ràng.
- [ ] Mỗi field có consumer và mục đích sử dụng cụ thể.
- [ ] Không truyền nguyên entity, request DTO hoặc object graph.
- [ ] Chọn rõ snapshot tại thời điểm phát hay reference đến current state.
- [ ] Giữ event ID, aggregate ID/version và timestamp cần thiết.
- [ ] Chỉ mang các value object tối thiểu, bất biến.
- [ ] Không đưa credential hoặc dữ liệu nhạy cảm không cần thiết vào payload.
- [ ] Dùng API/reference có authorization cho dữ liệu cần truy vấn thêm.
- [ ] File/blob lớn nằm trong object storage, event chỉ mang metadata/reference.
- [ ] Có giới hạn collection, độ sâu và serialized size.
- [ ] Event chuyên biệt được tạo khi consumer có mục đích/quyền khác nhau.
- [ ] Version hóa thay đổi contract và giữ khả năng đọc message cũ khi cần.
- [ ] Kiểm thử payload, serialization, kích thước và side effect khi retry.
- [ ] Quan sát payload size mà không log dữ liệu nhạy cảm.

Event mang quá nhiều dữ liệu làm ranh giới module mờ đi, tăng chi phí vận hành và mở rộng rủi ro bảo mật. Trong Spring Modulith, event DTO gọn giúp publisher công bố đúng fact nghiệp vụ, listener chỉ phụ thuộc vào hợp đồng cần thiết và Event Publication Registry/broker lưu trữ payload ở mức hợp lý. Hãy chọn snapshot khi consumer cần sự thật tại thời điểm phát, dùng reference khi cần trạng thái hiện tại, tách file lớn khỏi message và kiểm thử contract để mỗi event chỉ mang dữ liệu có mục đích rõ ràng.
