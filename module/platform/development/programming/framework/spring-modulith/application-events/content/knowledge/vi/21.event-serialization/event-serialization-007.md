# Header và metadata

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi event được lưu, serialize hoặc chuyển qua một adapter tích hợp, hệ thống cần mang theo thông tin để nhận diện sự kiện, hiểu payload và liên kết nó với quy trình đã phát sinh.

**Payload** chứa dữ liệu nghiệp vụ của sự kiện. **Metadata** mô tả sự kiện và ngữ cảnh xử lý. Khi truyền qua một message transport, một phần metadata có thể được biểu diễn thành **headers**. Phân biệt ba khái niệm này giúp event dễ serialize, dễ tương thích giữa các phiên bản và dễ điều tra khi có lỗi.

## 1. Payload, metadata và header

Giả sử module Order công bố event OrderConfirmed khi một đơn hàng được xác nhận. Payload có thể chứa orderId, tổng tiền và thời điểm xác nhận. Metadata có thể chứa eventId, loại event, phiên bản schema, correlationId và causationId. Khi gửi message qua broker, adapter có thể đặt các giá trị metadata đó vào header của message.

| Thành phần | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Payload | Sự kiện nghiệp vụ mang dữ liệu gì? | orderId, amount, currency |
| Metadata | Đây là sự kiện nào, thuộc phiên bản nào và nằm trong quy trình nào? | eventId, eventType, schemaVersion, correlationId |
| Header | Transport mang thông tin điều khiển hoặc mô tả message ở đâu? | content-type, event-type, correlation-id |

Metadata là khái niệm về ngữ nghĩa; header là một cách biểu diễn metadata trong message transport. Metadata cũng có thể nằm trong một envelope JSON cùng payload. Không phải mọi application event của Spring đều có một header map chung.

## 2. Application event nội bộ không tự có header map

Spring cho phép publisher công bố một object thông qua ApplicationEventPublisher. Nếu event là một Java record, các field của record là dữ liệu mà listener nhận được. Spring không tự động biến mọi field thành message header.

Ví dụ:

~~~java
public record OrderConfirmed(
    UUID orderId,
    BigDecimal total,
    Instant confirmedAt
) {}
~~~

~~~java
@Service
@RequiredArgsConstructor
class OrderService {

    private final ApplicationEventPublisher events;

    @Transactional
    public void confirm(UUID orderId, BigDecimal total) {
        // Cập nhật đơn hàng trong transaction hiện tại.
        events.publishEvent(
            new OrderConfirmed(orderId, total, Instant.now())
        );
    }
}
~~~

Listener nhận đúng object event:

~~~java
@Component
class OrderAuditListener {

    @EventListener
    void on(OrderConfirmed event) {
        // Đọc event.orderId(), event.total() và event.confirmedAt().
    }
}
~~~

Trong mô hình này, các field của record là payload. Nếu listener cần eventId hoặc correlationId, ứng dụng phải đưa những giá trị đó vào một cấu trúc event/envelope hoặc cung cấp qua một cơ chế ngữ cảnh được thiết kế rõ ràng. Không nên giả định Spring tự thêm các header như Kafka hoặc Spring Messaging vào một record thông thường.

## 3. Những metadata thường cần có

Metadata nên nhỏ, ổn định và phục vụ một mục đích rõ ràng. Các trường phổ biến gồm:

| Trường | Mục đích | Quy tắc thiết kế |
| --- | --- | --- |
| eventId | Nhận diện một lần phát sinh event cụ thể. | Duy nhất và giữ nguyên khi retry cùng một event. |
| eventType | Cho biết ý nghĩa và loại payload. | Dùng tên logic ổn định, tránh phụ thuộc tên class Java. |
| schemaVersion | Xác định cấu trúc payload đang được dùng. | Tăng phiên bản khi có thay đổi hợp đồng cần phân biệt. |
| occurredAt | Thời điểm sự kiện xảy ra trong nghiệp vụ. | Dùng Instant hoặc thời gian UTC có múi giờ rõ ràng. |
| publishedAt | Thời điểm message được gửi vào transport. | Phân biệt với occurredAt; retry có thể làm thời điểm gửi thay đổi. |
| correlationId | Liên kết nhiều thao tác trong cùng một luồng nghiệp vụ. | Giữ nhất quán qua các bước của quy trình. |
| causationId | Chỉ ra command hoặc event trực tiếp gây ra event hiện tại. | Dùng để dựng quan hệ nguyên nhân-kết quả. |
| contentType | Mô tả định dạng payload. | Ví dụ application/json; cần thống nhất với serializer. |
| trace context | Nối trace giữa các thành phần. | Chỉ truyền theo chuẩn tracing đã chọn và chính sách propagation. |

Không phải event nào cũng cần tất cả trường trên. Chọn tập metadata tối thiểu đủ hỗ trợ định tuyến, tương thích, chống xử lý trùng và quan sát. Nếu một giá trị không được dùng để quyết định, kiểm tra, tương quan hoặc điều tra, hãy cân nhắc bỏ nó.

eventId và correlationId giải quyết hai bài toán khác nhau. eventId định danh một event cụ thể; correlationId liên kết nhiều event và command trong cùng một quy trình. Một saga có thể có nhiều eventId nhưng cùng correlationId. causationId chỉ ra nguyên nhân trực tiếp, giúp lần theo chuỗi event mà không phải suy luận từ timestamp.

## 4. Thiết kế event envelope

Khi event cần đi qua nhiều ranh giới hoặc được lưu dưới dạng JSON, một envelope tách metadata khỏi payload giúp hợp đồng dễ đọc:

~~~java
public record EventMetadata(
    String eventId,
    String eventType,
    int schemaVersion,
    Instant occurredAt,
    String correlationId,
    String causationId,
    String contentType
) {}

public record EventEnvelope<T>(
    EventMetadata metadata,
    T payload
) {}
~~~

Một message minh họa dưới dạng JSON:

~~~json
{
  "metadata": {
    "eventId": "9a2b1a5e-43a8-4d2e-9c51-0e8a12c1a100",
    "eventType": "sales.order-confirmed",
    "schemaVersion": 1,
    "occurredAt": "2026-11-25T12:30:00Z",
    "correlationId": "checkout-8d3c",
    "causationId": "confirm-order-91f2",
    "contentType": "application/json"
  },
  "payload": {
    "orderId": "ORD-2026-0042",
    "total": 1250000,
    "currency": "VND"
  }
}
~~~

Envelope không bắt buộc phải là một kiểu framework cụ thể. Ứng dụng có thể dùng record, class DTO hoặc một cấu trúc do adapter tích hợp tạo ra. Điều quan trọng là consumer biết rõ phần metadata nằm ở đâu, payload được diễn giải theo schema nào và trường nào bắt buộc.

Không đưa toàn bộ object domain hoặc entity JPA vào envelope. Entity có thể chứa quan hệ lazy, trạng thái nội bộ, dữ liệu nhạy cảm hoặc chi tiết thay đổi theo implementation. Hãy tạo event DTO có cấu trúc ổn định và chỉ chứa dữ liệu cần cho consumer.

## 5. Biểu diễn metadata thành Spring Message headers

Trong các luồng sử dụng Spring Messaging, message có payload và MessageHeaders. MessageBuilder cho phép tạo message và gắn metadata vào header:

~~~java
Message<OrderConfirmedPayload> message = MessageBuilder
    .withPayload(payload)
    .setHeader("event-type", "sales.order-confirmed")
    .setHeader("schema-version", "1")
    .setHeader("event-id", eventId.toString())
    .setHeader("correlation-id", correlationId)
    .setHeader("causation-id", causationId)
    .setHeader("content-type", "application/json")
    .build();
~~~

Đây là ví dụ tạo Spring Message; nó không có nghĩa ApplicationEventPublisher tự chuyển object event thành message có header hoặc tự gửi message đến broker. Adapter hoặc integration flow phải chịu trách nhiệm gửi message, serialize payload và ánh xạ header sang định dạng mà transport hỗ trợ.

Headers của message được thiết kế để đọc sau khi message được tạo; hãy xây dựng message mới khi cần thay đổi metadata. Khi chuyển qua broker, một số transport chỉ hỗ trợ kiểu header đơn giản hoặc byte array. Để tương thích đa ngôn ngữ, nên chuẩn hóa tên header, quy tắc chữ hoa/thường, kiểu giá trị và cách encode. Các giá trị chuỗi thường dễ trao đổi hơn object Java tùy biến.

Không ghi đè các header dành riêng cho framework hoặc adapter. Hãy có namespace rõ ràng cho header do ứng dụng sở hữu, ví dụ event-type, schema-version và correlation-id, đồng thời tài liệu hóa quy tắc đặt tên.

## 6. Header hỗ trợ xử lý và quan sát như thế nào?

Header có thể giúp adapter và consumer nhận diện loại event, chọn serializer, liên kết trace hoặc kiểm tra phiên bản trước khi giải mã payload. Metadata cũng giúp hệ thống ghi log nhất quán và tìm lại message khi cần điều tra.

Ví dụ, khi consumer nhận một message, trình tự xử lý có thể là:

1. Đọc event-type và schema-version.
2. Kiểm tra content-type có nằm trong định dạng được hỗ trợ không.
3. Chọn decoder tương ứng với event type và schema version.
4. Giải mã payload thành event DTO.
5. Dùng event-id để chống xử lý trùng và correlation-id để gắn log/trace.
6. Chuyển event vào handler nghiệp vụ sau khi xác minh dữ liệu cần thiết.

Không nên dùng header để thay thế validation payload. Một message có event-type hợp lệ vẫn có thể chứa orderId sai định dạng hoặc amount âm. Consumer phải xác thực dữ liệu nghiệp vụ trước khi thực hiện side effect.

Timestamp giúp sắp xếp và điều tra, nhưng không phải lúc nào cũng đảm bảo thứ tự nhân quả. Đồng hồ giữa các máy có thể lệch và message có thể đến trễ. Nếu nghiệp vụ yêu cầu thứ tự chặt chẽ, hãy dùng sequence/version theo aggregate hoặc partitioning key phù hợp; đừng suy ra thứ tự chỉ từ occurredAt.

## 7. Phân biệt metadata event với metadata của Publication Registry

Spring Modulith Event Publication Registry theo dõi việc giao event đến từng transactional listener. Registry lưu trạng thái publication, thời điểm công bố/hoàn tất và thông tin listener cần thiết để ứng dụng tìm publication chưa hoàn tất và recovery khi phù hợp.

Đây là metadata vận hành của quá trình giao event. Nó khác với metadata nghiệp vụ như eventId, eventType, schemaVersion, correlationId hoặc causationId. Không nên đưa trạng thái completed, tên bảng registry hay thông tin retry nội bộ vào payload nghiệp vụ để consumer sử dụng như hợp đồng.

Một event có thể có nhiều publication record, mỗi record ứng với một listener được theo dõi. Việc record của listener A hoàn tất không có nghĩa listener B đã hoàn tất. Metadata của registry phục vụ theo dõi delivery; metadata của event phục vụ nhận diện, diễn giải và liên kết sự kiện. Hai lớp có thể cùng tồn tại nhưng cần giữ đúng trách nhiệm.

## 8. Header và metadata khi externalize event

Khi event nội bộ được chuyển ra broker hoặc hệ thống khác, adapter externalization phải xác định metadata nào nằm trong payload envelope và metadata nào được ánh xạ thành transport header. Không phải mọi header nội bộ đều tự động được chuyển qua ranh giới tích hợp.

Một chính sách mapping nên xác định:

- Event type và schema version có được đặt trong header để consumer chọn decoder hay không.
- eventId, correlationId và causationId được truyền dưới dạng header, envelope hay cả hai theo một quy tắc nhất quán.
- Content type và encoding được khai báo như thế nào.
- Header nào được phép truyền qua biên, header nào phải loại bỏ.
- Các giá trị có thể chứa dữ liệu cá nhân hoặc bí mật được xử lý ra sao.

Với Spring Modulith event externalization, annotation và adapter cấu hình việc chuyển event ra ngoài; chi tiết mapping phụ thuộc integration được chọn và phiên bản thư viện. Hãy kiểm tra hợp đồng thực tế của adapter đang dùng và viết integration test cho message được phát ra. Không giả định mọi metadata trên object event sẽ tự trở thành broker header.

Destination, partition key và routing key là thông tin định tuyến của transport. Chúng có thể được biểu diễn bằng header hoặc thuộc tính riêng của broker, nhưng không đồng nghĩa với eventType hay correlationId. Giữ riêng ý nghĩa của từng trường để tránh consumer dùng nhầm metadata tương quan làm khóa phân vùng hoặc ngược lại.

## 9. Tương thích schema và thay đổi header

Event có thể tồn tại lâu hơn một lần triển khai ứng dụng: publication chưa hoàn tất có thể được recovery sau restart, broker có thể giữ message trong backlog và consumer có thể nâng cấp chậm hơn publisher. Vì vậy, schema version và quy tắc header phải được quản lý như hợp đồng.

Khi thêm một field payload tùy chọn, consumer cũ có thể bỏ qua field chưa biết nếu serializer và cấu hình cho phép. Khi đổi kiểu dữ liệu, đổi ý nghĩa field hoặc xóa field bắt buộc, cần đánh giá tương thích trước khi triển khai. Có thể hỗ trợ nhiều schema version trong thời gian chuyển tiếp hoặc phát event type/version mới.

Không nên dùng tên class Java đầy đủ làm event type công khai. Đổi package hoặc refactor class khi đó sẽ làm thay đổi hợp đồng ngoài ý muốn. Dùng tên logic ổn định như sales.order-confirmed và quản lý schemaVersion riêng.

Header cũng cần quy tắc tiến hóa. Consumer nên bỏ qua header tùy chọn chưa biết nếu hợp đồng cho phép; các header bắt buộc như event-type hoặc schema-version phải được kiểm tra. Không tái sử dụng tên header cũ với ý nghĩa mới. Ghi rõ kiểu dữ liệu, tính bắt buộc và giá trị mặc định trong tài liệu hợp đồng.

## 10. Bảo mật và dữ liệu nhạy cảm

Header thường xuất hiện trong log, broker console, tracing và công cụ quan sát. Không đưa access token, mật khẩu, session cookie, khóa bí mật hoặc toàn bộ thông tin cá nhân vào header. Header không phải nơi lưu dữ liệu bí mật.

Chỉ truyền thông tin định danh hoặc phân loại thật sự cần thiết. Nếu consumer cần dữ liệu cá nhân, cân nhắc truyền identifier để truy xuất qua API có xác thực thay vì sao chép dữ liệu vào mọi message. Khi có tenantId hoặc userId, consumer vẫn phải kiểm tra quyền truy cập và tính hợp lệ; không tin giá trị header như bằng chứng xác thực.

Danh sách header được phép truyền qua biên tích hợp nên là allowlist. Loại bỏ header nội bộ chứa thông tin hạ tầng, thông tin xác thực hoặc dữ liệu không dành cho consumer bên ngoài. Cần kiểm tra việc log header để tránh rò rỉ dữ liệu.

## 11. Kiểm thử serialization và metadata

Kiểm thử không chỉ xác minh payload deserialize được mà còn phải xác minh metadata được giữ nguyên hoặc ánh xạ đúng theo hợp đồng. Một số trường hợp nên bao phủ:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Serialize rồi deserialize | Payload giữ đúng giá trị và kiểu dữ liệu theo schema. |
| Metadata bắt buộc | eventId, eventType và schemaVersion được tạo và đọc đúng. |
| Tương quan | correlationId và causationId được giữ nguyên qua các bước. |
| Header mapping | Adapter ánh xạ đúng tên và kiểu header sang transport. |
| Header tùy chọn | Consumer xử lý được khi header tùy chọn vắng mặt. |
| Header không biết | Consumer bỏ qua hoặc từ chối theo chính sách đã công bố. |
| Schema cũ | Consumer hiện tại đọc được message cũ trong thời gian tương thích. |
| Schema không hỗ trợ | Message bị từ chối có kiểm soát và có log/metric phù hợp. |
| Retry | eventId không đổi khi cùng một event được gửi lại. |
| Bảo mật | Header không chứa secret hoặc dữ liệu nhạy cảm ngoài chính sách. |

Nên có test dùng JSON mẫu được lưu như fixture để bảo vệ hợp đồng giữa publisher và consumer. Integration test với adapter thật hoặc test container phù hợp sẽ xác minh những khác biệt mà unit test serializer không thể phát hiện, chẳng hạn giới hạn kiểu header hoặc cách broker encode giá trị.

## 12. Quan sát và xử lý message lỗi

Log của publisher, adapter và consumer nên có eventId, eventType, schemaVersion, correlationId và causationId khi các trường đó tồn tại. Nhờ vậy, người vận hành có thể lần theo một sự kiện qua nhiều module và hệ thống mà không cần ghi toàn bộ payload.

Các chỉ số hữu ích gồm số message theo eventType/schemaVersion, tỷ lệ lỗi deserialize, số message bị từ chối vì header thiếu hoặc không hợp lệ, độ trễ từ occurredAt đến lúc nhận, số lần retry và số message cần xử lý thủ công. Cần phân biệt lỗi giải mã (contract/format) với lỗi listener hoặc lỗi nghiệp vụ để chọn biện pháp khắc phục phù hợp.

Khi một message lỗi, lưu định danh và thông tin chẩn đoán đủ để điều tra; bảo vệ payload theo chính sách lưu trữ. Không sửa header hoặc payload trực tiếp trên broker để làm message chạy qua nếu chưa hiểu nguyên nhân. Sau khi sửa consumer hoặc schema compatibility, replay phải giữ eventId để cơ chế idempotency tiếp tục hoạt động.

## 13. Checklist thiết kế header và metadata

- Payload chỉ chứa dữ liệu nghiệp vụ cần thiết; metadata mô tả event và ngữ cảnh.
- Phân biệt metadata khái niệm với transport header.
- Application event nội bộ không bị giả định có header map tự động.
- eventId ổn định qua retry; correlationId và causationId có ý nghĩa riêng.
- eventType dùng tên logic ổn định; schemaVersion được quản lý rõ ràng.
- occurredAt và publishedAt được phân biệt; timestamp không thay thế cơ chế ordering.
- Header có tên, kiểu dữ liệu và chính sách propagation thống nhất.
- Adapter chịu trách nhiệm mapping metadata sang header; test xác minh mapping thực tế.
- Metadata nghiệp vụ được tách khỏi metadata vận hành của Event Publication Registry.
- Không đưa secret hoặc dữ liệu nhạy cảm vào header; áp dụng allowlist khi externalize.
- Consumer xác thực payload và xử lý schema/header không hỗ trợ có kiểm soát.
- Integration test bao phủ round-trip, compatibility, retry, mapping và bảo mật.

Header và metadata giúp event mang theo ngữ cảnh cần thiết để serialize, định tuyến qua adapter, tương quan và điều tra. Khi payload giữ đúng dữ liệu nghiệp vụ, metadata có hợp đồng ổn định và transport header được ánh xạ có chủ đích, các module có thể trao đổi event đáng tin cậy mà không phụ thuộc vào chi tiết nội bộ của nhau.
