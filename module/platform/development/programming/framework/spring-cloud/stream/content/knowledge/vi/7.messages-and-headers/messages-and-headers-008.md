# Giới hạn kích thước header và tránh truyền dữ liệu nhạy cảm

Trong Spring Cloud Stream, message thường gồm payload và headers. Payload mang dữ liệu nghiệp vụ; headers mang metadata giúp định tuyến, truy vết, diễn giải hoặc xử lý message, chẳng hạn event ID, correlation ID, schema version và thông tin tracing. Vì header được truyền cùng message qua binder và broker, nó cũng tiêu thụ dung lượng, chịu giới hạn của transport và có thể xuất hiện trong log, dead-letter queue hoặc công cụ vận hành.

Một header lớn có thể làm tăng kích thước message, gây lỗi publish/consume hoặc làm giảm thông lượng. Header chứa mật khẩu, access token, cookie, thông tin định danh cá nhân hay dữ liệu thanh toán còn tạo thêm rủi ro lộ lọt. Thiết kế tốt là chỉ gửi metadata nhỏ, có mục đích rõ ràng, giới hạn danh sách header được phép và kiểm tra kích thước trước khi đưa message vào binding.

## 1. Header dùng để làm gì?

Spring Messaging biểu diễn message bằng `Message<T>`, trong đó `T` là kiểu payload và `MessageHeaders` là tập metadata. Ví dụ:

```java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1001", 250_000))
    .setHeader("eventId", "evt-7f23")
    .setHeader("correlationId", "corr-91ab")
    .setHeader("schemaVersion", "1")
    .build();
```

Payload là `OrderCreated`; các giá trị `eventId`, `correlationId` và `schemaVersion` là metadata. Chúng giúp consumer chống xử lý lặp, liên kết các message trong một luồng xử lý và chọn cách diễn giải schema. Nếu consumer chỉ cần dữ liệu đơn hàng, có thể nhận payload trực tiếp; khi cần metadata, hàm có thể nhận `Message<OrderCreated>`.

Header nên trả lời một câu hỏi kỹ thuật cụ thể:

| Metadata | Mục đích | Lưu ý |
|---|---|---|
| `eventId` | Nhận diện duy nhất một sự kiện | Dùng làm khóa idempotency; không chứa thông tin cá nhân |
| `correlationId` | Liên kết các bước trong một yêu cầu hoặc quy trình | Dùng giá trị khó đoán hoặc opaque nếu có thể liên hệ đến người dùng |
| `schemaVersion` | Xác định phiên bản cấu trúc payload | Thống nhất quy ước với producer và consumer |
| `traceparent` | Truyền ngữ cảnh distributed tracing theo chuẩn W3C | Chỉ truyền đúng định dạng và chính sách tracing của hệ thống |
| `contentType` | Mô tả định dạng nội dung | Thường do framework/binder quản lý; tránh tự đặt giá trị mâu thuẫn |

Không dùng header để sao chép toàn bộ payload, nhúng một đối tượng lớn dưới dạng JSON, hoặc truyền trạng thái nghiệp vụ dài. Nếu consumer cần nhiều dữ liệu để xử lý, đặt dữ liệu trong payload có schema rõ ràng hoặc lưu dữ liệu ở hệ thống phù hợp rồi truyền một tham chiếu ổn định.

## 2. Header cũng bị giới hạn kích thước

Không có một giới hạn kích thước header duy nhất áp dụng cho mọi ứng dụng Spring Cloud Stream. Giới hạn thực tế phụ thuộc vào nhiều lớp:

1. **Ứng dụng:** chính sách kích thước do nhóm phát triển đặt ra, kiểu dữ liệu và số lượng header mà ứng dụng cho phép.
2. **Spring Messaging và binder:** cách mapper chuyển `MessageHeaders` thành metadata của broker, header nào được giữ lại, đổi kiểu hoặc bỏ qua.
3. **Client và giao thức:** giới hạn request, frame, record hoặc metadata mà client có thể tạo và gửi.
4. **Broker và destination:** giới hạn message, cấu hình topic/queue, chính sách lưu trữ và replication.
5. **Consumer và công cụ trung gian:** giới hạn khi đọc, chuyển tiếp, ghi log, tracing hoặc chuyển message vào DLQ.

Kích thước header thường được tính cùng overhead của message. Tên header, giá trị, kiểu mã hóa, metadata do framework thêm vào và cấu trúc giao thức đều có thể làm tăng kích thước thực tế. Vì vậy, tổng số byte của các chuỗi header ở phía ứng dụng chỉ là một ước lượng, không phải phép đo chính xác kích thước message trên wire.

### Khác biệt giữa các broker

| Broker | Cách header/metadata được mang theo | Giới hạn cần kiểm tra |
|---|---|---|
| Kafka | Record headers có tên và giá trị dạng byte; header nằm trong record được gửi trong request/batch | Kích thước request của producer, giới hạn kích thước record/message của broker/topic và giới hạn fetch của consumer |
| RabbitMQ | Message properties chứa headers dưới dạng AMQP field table | Kiểu dữ liệu field table được hỗ trợ, kích thước frame, giới hạn message và cấu hình broker/client |
| Pulsar | Message properties là các cặp key/value được lưu trong metadata của message | Giới hạn kích thước message của client/broker và overhead metadata khi serialize |

Kafka, RabbitMQ và Pulsar không có cùng cách mã hóa header. Cùng một tập `MessageHeaders` có thể được ánh xạ khác nhau khi đi qua từng binder. Một header có kiểu Java tùy biến hoặc giá trị quá dài có thể được xử lý ở một binder nhưng bị chuyển đổi, bỏ qua hoặc từ chối ở binder khác. Khi hỗ trợ nhiều broker, hãy chọn tập header giao nhau nhỏ và kiểm thử từng binder.

Không nên áp dụng một con số mặc định của broker cho mọi môi trường. Hãy tra cấu hình client và broker đang triển khai, đồng thời tính đến các thành phần trung gian. Ví dụ, với Kafka cần xem giới hạn request/record và fetch; với RabbitMQ cần xem AMQP frame và message properties; với Pulsar cần xem giới hạn message cùng metadata. Tăng giới hạn broker chỉ để cho phép header phình to thường che giấu vấn đề thiết kế và làm tăng chi phí bộ nhớ, mạng, lưu trữ.

## 3. Đặt ngân sách header ở tầng ứng dụng

Ngay cả khi broker cho phép message lớn, ứng dụng vẫn nên đặt ngân sách nhỏ hơn giới hạn hạ tầng. Ngân sách giúp phát hiện lỗi sớm, giữ metadata nhất quán giữa các broker và ngăn một service vô tình đưa dữ liệu lớn vào header.

Một chính sách minh họa có thể quy định:

- Chỉ cho phép một danh sách header đã được duyệt.
- Giới hạn số header tùy chỉnh, ví dụ tối đa 8 trường.
- Giới hạn tổng byte của tên và giá trị, ví dụ 4 KiB cho metadata tùy chỉnh.
- Giới hạn riêng cho từng giá trị, ví dụ 1 KiB.
- Chỉ dùng kiểu đơn giản, có quy ước chuyển đổi rõ ràng như `String`, số hoặc boolean.
- Từ chối giá trị rỗng bất thường, giá trị quá dài và header không nằm trong allowlist.

Các con số trên là ngân sách ví dụ của ứng dụng, không phải giới hạn mặc định của Spring Cloud Stream hay broker. Hãy chọn mức thấp hơn giới hạn nhỏ nhất của các broker và thành phần trung gian mà hệ thống thực sự dùng, đồng thời để lại khoảng trống cho metadata do framework và giao thức thêm vào.

Đo kích thước chuỗi theo byte UTF-8 thay vì số ký tự Java. Một chuỗi có ký tự tiếng Việt hoặc emoji có thể chiếm nhiều byte hơn số ký tự hiển thị:

```java
int byteLength = value.getBytes(StandardCharsets.UTF_8).length;
```

Không dùng `String.length()` để kết luận kích thước dữ liệu sẽ truyền qua broker. Với giá trị `byte[]`, tính trực tiếp độ dài mảng; với kiểu phức tạp, phải biết chính xác serializer và định dạng mã hóa trước khi ước lượng.

## 4. Allowlist và kiểm tra header trước khi gửi

Một allowlist xác định rõ những metadata được phép đi qua ranh giới dịch vụ. Ví dụ sau chỉ chấp nhận bốn header dạng chuỗi và giới hạn tổng dung lượng tùy chỉnh ở mức 4 KiB:

```java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Set;

public final class SafeHeaders {
    private static final Set<String> ALLOWED = Set.of(
        "eventId",
        "correlationId",
        "schemaVersion",
        "traceparent"
    );

    private static final int MAX_HEADER_COUNT = 8;
    private static final int MAX_HEADER_BYTES = 4 * 1024;
    private static final int MAX_VALUE_BYTES = 1024;

    private SafeHeaders() {}

    public static Map<String, String> validate(Map<String, String> input) {
        if (input.size() > MAX_HEADER_COUNT) {
            throw new IllegalArgumentException("Too many message headers");
        }

        int totalBytes = 0;
        for (Map.Entry<String, String> entry : input.entrySet()) {
            String name = entry.getKey();
            String value = entry.getValue();

            if (!ALLOWED.contains(name)) {
                throw new IllegalArgumentException("Header is not allowed: " + name);
            }
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Header value is required: " + name);
            }

            int nameBytes = name.getBytes(StandardCharsets.UTF_8).length;
            int valueBytes = value.getBytes(StandardCharsets.UTF_8).length;
            if (valueBytes > MAX_VALUE_BYTES) {
                throw new IllegalArgumentException("Header value is too large: " + name);
            }
            totalBytes += nameBytes + valueBytes;
        }

        if (totalBytes > MAX_HEADER_BYTES) {
            throw new IllegalArgumentException("Message headers exceed the application budget");
        }
        return Map.copyOf(input);
    }
}
```

Khi tạo message, chỉ sao chép các header đã qua kiểm tra:

```java
Map<String, String> metadata = Map.of(
    "eventId", event.eventId(),
    "correlationId", correlationId,
    "schemaVersion", "1"
);

Map<String, String> safeMetadata = SafeHeaders.validate(metadata);

Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .copyHeaders(safeMetadata)
    .build();
```

Ví dụ này kiểm tra header tùy chỉnh ở ranh giới producer. Trong ứng dụng thực tế, cần thống nhất allowlist giữa các service và kiểm tra cả các header do framework, tracing agent hoặc binder tự thêm. Nếu cần header mở rộng theo từng nghiệp vụ, cập nhật schema/allowlist có kiểm soát thay vì cho phép mọi header tùy ý.

## 5. Chỉ truyền metadata cần thiết

Một header nên nhỏ, ổn định và có mục đích rõ. Các giá trị phù hợp thường là ID kỹ thuật, phiên bản schema, loại sự kiện hoặc ngữ cảnh tracing. Tránh các nội dung sau:

| Không nên truyền trong header | Vì sao rủi ro | Cách xử lý phù hợp hơn |
|---|---|---|
| Mật khẩu, API key, access token, refresh token | Có thể bị sao chép vào broker, DLQ, log hoặc hệ thống tracing | Dùng secret manager và danh tính dịch vụ; xác thực ở kênh kết nối |
| Session cookie hoặc toàn bộ HTTP Authorization | Có thể cấp quyền ngoài phạm vi dự kiến và bị phát lại | Không chuyển tiếp credential của request; tạo danh tính/ủy quyền phù hợp cho service-to-service |
| Họ tên, email, số điện thoại, địa chỉ, mã định danh cá nhân | Metadata có thể bị nhiều thành phần quan sát và lưu giữ lâu | Dùng ID nội bộ hoặc tham chiếu opaque nếu consumer cần tra cứu |
| Số thẻ, dữ liệu thanh toán hoặc thông tin tài chính | Tăng phạm vi dữ liệu nhạy cảm phải bảo vệ và kiểm soát truy cập | Truyền token/tham chiếu thanh toán đã được thiết kế an toàn |
| Toàn bộ đối tượng người dùng hoặc đơn hàng | Làm header lớn, khó tương thích và trùng lặp payload | Đặt dữ liệu nghiệp vụ trong payload có schema |
| Stack trace, nội dung exception hoặc dữ liệu debug | Có thể tiết lộ đường dẫn, tên lớp, SQL, dữ liệu request hoặc bí mật | Gửi mã lỗi ngắn và correlation ID; lưu chi tiết trong hệ thống log được kiểm soát |

Không coi header là vùng riêng tư chỉ vì nó không hiển thị trong payload. Broker operator, consumer có quyền đọc, công cụ quản trị, dead-letter queue, connector, log và tracing có thể nhìn thấy metadata. TLS bảo vệ dữ liệu trên đường truyền nhưng không tự loại bỏ rủi ro khi dữ liệu đã được broker lưu trữ hoặc khi người có quyền truy cập xem message.

Nếu consumer cần thông tin nhạy cảm để xử lý, hãy đánh giá liệu có thể tra cứu từ hệ thống có kiểm soát truy cập bằng một ID hay không. Nếu bắt buộc phải truyền dữ liệu nhạy cảm, đặt nó trong payload theo schema và chính sách bảo vệ phù hợp, giới hạn quyền đọc, mã hóa theo yêu cầu và thiết lập retention. Không dùng header như một kênh bí mật thay thế cho cơ chế bảo mật.

## 6. Header không phải bằng chứng xác thực

Producer có thể tạo hoặc sửa nhiều header. Vì vậy, consumer không nên tin một header như `userRole`, `isAdmin`, `authenticatedUser` hoặc `tenantId` chỉ vì nó đến từ broker. Một producer bị xâm nhập hoặc một client có quyền publish có thể giả mạo metadata đó.

Nếu header ảnh hưởng đến quyết định phân quyền, consumer phải xác thực nguồn gốc và tính toàn vẹn của thông tin bằng cơ chế phù hợp. Thông thường nên dựa trên danh tính dịch vụ được xác thực, chữ ký/claim đã xác minh hoặc tra cứu từ nguồn tin cậy. Header có thể mang correlation ID hoặc tham chiếu định danh, nhưng không tự chứng minh người gửi có quyền thực hiện hành động.

Với tenant context, chỉ truyền mã tenant khi thật sự cần và bảo đảm consumer xác minh producer được phép phát sự kiện cho tenant đó. Không lấy giá trị tenant từ header chưa xác thực để truy cập dữ liệu của tenant khác.

## 7. Lọc header khi đi qua binder

Spring Cloud Stream chuyển message của ứng dụng qua binder. Binder và header mapper quyết định header nào được ánh xạ sang metadata native của broker, header nào được chuyển đổi kiểu và header nào bị loại. Một số transport có cơ chế header native; một số cấu hình có thể đóng gói header theo cách riêng. Không nên giả định mọi header tùy chỉnh đều được bảo toàn nguyên trạng khi đổi binder.

Các nguyên tắc cấu hình:

- Ưu tiên allowlist ở ranh giới ứng dụng trước khi gọi `StreamBridge` hoặc trả message từ function.
- Dùng khả năng header mapping/pattern của binder để chỉ chuyển các header cần thiết, theo tài liệu của đúng phiên bản binder.
- Không bật chế độ truyền tất cả header chỉ để giữ lại một trường metadata.
- Tránh chuyển tiếp các header nội bộ của HTTP, framework hoặc bảo mật nếu consumer không cần.
- Kiểm tra các header được framework tự sinh như ID và timestamp; chỉ giữ hoặc chuyển tiếp chúng khi có ý nghĩa với luồng nghiệp vụ.
- Khi chuyển từ Kafka sang RabbitMQ hoặc Pulsar, kiểm tra lại tên, kiểu dữ liệu, kích thước và quy tắc lọc header.

Ví dụ, một function có thể giữ lại correlation ID và thay event type:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        OrderAccepted accepted = new OrderAccepted(order.orderId(), order.total());

        return MessageBuilder.withPayload(accepted)
            .setHeader("eventId", UUID.randomUUID().toString())
            .setHeader("correlationId", input.getHeaders().get("correlationId"))
            .setHeader("schemaVersion", "1")
            .setHeader("eventType", "OrderAccepted")
            .build();
    };
}
```

Ví dụ minh họa việc tạo metadata mới theo allowlist. Trước khi dùng, cần xác thực giá trị correlation ID đầu vào, xử lý trường hợp thiếu/null và bảo đảm header mapper của binder cho phép đúng các tên header này. Không dùng `copyHeaders` toàn bộ một cách mặc định nếu input có thể chứa header không đáng tin hoặc thông tin không nên phát tán.

## 8. Tránh lộ dữ liệu qua log, retry và DLQ

Header có thể được ghi cùng message trong log ứng dụng, log broker hoặc công cụ quan sát. Khi log toàn bộ `Message`, `MessageHeaders` hoặc đối tượng request, ứng dụng có thể vô tình ghi token và dữ liệu cá nhân. Nên log một tập trường cho phép, ví dụ event ID, event type, binding name và correlation ID đã được đánh giá về quyền riêng tư.

Ví dụ log có kiểm soát:

```java
log.info("Received event: eventId={}, binding={}, type={}",
    eventId, bindingName, eventType);
```

Tránh:

```java
log.info("Received message: {}", message);
```

Khi message được retry hoặc chuyển vào DLQ, header thường được giữ lại hoặc sao chép theo hành vi của binder. Vì vậy, dữ liệu nhạy cảm trong header có thể tồn tại lâu hơn dự kiến và xuất hiện trong quy trình phát lại. Trước khi bật DLQ hoặc republish, kiểm tra header được giữ, bổ sung và ghi log như thế nào. Chính sách retention của topic/queue và DLQ cũng là một phần của chính sách dữ liệu.

Không đưa stack trace hoặc toàn bộ exception message vào header để hỗ trợ debug. Dùng mã lỗi ngắn, event ID và correlation ID để tìm chi tiết trong hệ thống log có phân quyền, giới hạn retention và cơ chế che dữ liệu.

## 9. Kiểm thử giới hạn và chính sách header

Kiểm thử nên xác nhận cả dữ liệu hợp lệ và các trường hợp bị từ chối:

- Gửi message với tập header tối thiểu và xác nhận consumer nhận đúng metadata cần thiết.
- Gửi header có giá trị nhiều byte UTF-8, chẳng hạn tiếng Việt hoặc emoji, để kiểm tra cách tính dung lượng.
- Gửi một giá trị vượt giới hạn riêng hoặc tổng header vượt ngân sách; xác nhận producer từ chối trước khi publish.
- Gửi tên header không nằm trong allowlist và xác nhận nó không được chuyển tiếp.
- Thử giá trị có kiểu không được hỗ trợ và xác nhận mapper xử lý theo chính sách đã định.
- Kiểm tra header sau khi message đi qua từng binder thực tế; xác nhận tên, kiểu, giá trị và thứ tự xử lý không bị hiểu sai.
- Kiểm tra log, retry và DLQ để bảo đảm không có token, cookie hoặc dữ liệu cá nhân ngoài dự kiến.
- Kiểm thử với kích thước payload gần giới hạn broker, vì header và overhead cũng góp vào tổng kích thước message.

Test binder hữu ích để kiểm tra logic message trong phạm vi ứng dụng, nhưng không thay thế kiểm thử với Kafka, RabbitMQ hoặc Pulsar thật khi cần xác nhận giới hạn giao thức, header mapping, kích thước record/frame/metadata và hành vi DLQ. Nên có integration test riêng cho mỗi binder được triển khai.

## 10. Checklist thiết kế header an toàn

- [ ] Mỗi header có mục đích cụ thể và consumer thực sự cần nó.
- [ ] Header chỉ chứa metadata nhỏ; dữ liệu nghiệp vụ nằm trong payload có schema.
- [ ] Có allowlist tên header và kiểu giá trị được chấp nhận.
- [ ] Đã giới hạn số header, kích thước từng giá trị và tổng byte UTF-8 ở tầng ứng dụng.
- [ ] Ngân sách ứng dụng thấp hơn giới hạn thực tế của broker, client và thành phần trung gian.
- [ ] Không truyền mật khẩu, token, cookie, thông tin cá nhân hoặc dữ liệu thanh toán trong header.
- [ ] Header không được dùng làm bằng chứng xác thực hoặc phân quyền nếu chưa xác minh nguồn gốc.
- [ ] Binder header mapper chỉ chuyển tiếp các trường cần thiết.
- [ ] Log, retry, DLQ và tracing không làm lộ metadata nhạy cảm.
- [ ] Đã kiểm thử kích thước và header mapping với từng broker được sử dụng.

Header nhỏ và được kiểm soát giúp message dễ tương thích giữa binder, giảm overhead và an toàn hơn khi đi qua broker, log, retry và DLQ. Hãy coi mọi metadata được publish là dữ liệu có thể được nhiều thành phần trong hệ thống quan sát, rồi chỉ truyền những gì thực sự cần cho việc xử lý sự kiện.
