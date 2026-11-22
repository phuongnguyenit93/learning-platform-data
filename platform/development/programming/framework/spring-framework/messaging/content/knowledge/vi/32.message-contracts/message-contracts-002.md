# Envelope gồm phiên bản, định danh, thời gian và dữ liệu

> Phạm vi: thiết kế hợp đồng thông điệp cho ứng dụng Spring Framework Messaging. Bài học tập trung vào một envelope có cấu trúc ổn định, mang thông tin để nhận diện và diễn giải thông điệp, đồng thời chứa payload nghiệp vụ có kiểu rõ ràng.

## 1. Envelope giải quyết vấn đề gì?

Một message thường đi qua nhiều thành phần: producer, channel, adapter, broker hoặc RSocket, rồi đến consumer. Các thành phần trung gian có thể định tuyến, lưu trữ, retry, ghi log hoặc chuyển tiếp message mà không cần hiểu toàn bộ dữ liệu nghiệp vụ.

Nếu mỗi producer tự chọn cấu trúc khác nhau, consumer phải đoán dữ liệu nào là phiên bản, định danh nào dùng để chống xử lý trùng, thời gian nào biểu thị lúc sự kiện xảy ra và phần nào là payload. Một envelope thống nhất đặt các thông tin chung vào cùng một cấu trúc:

- **Phiên bản hợp đồng** cho biết consumer phải diễn giải cấu trúc theo quy tắc nào.
- **Định danh thông điệp** xác định một message logic để trace, deduplicate và xử lý retry.
- **Thời gian** cho biết sự kiện xảy ra khi nào.
- **Dữ liệu (`data`)** chứa nội dung nghiệp vụ cụ thể.

Ví dụ một thông điệp `OrderCreated`:

~~~json
{
  "schemaVersion": 1,
  "messageId": "7e4a6e9a-6e2f-4e6b-9e8f-4b7e1e8c1001",
  "occurredAt": "2026-11-07T14:00:00Z",
  "data": {
    "orderId": "ORD-1001",
    "total": 125000.00
  }
}
~~~

Consumer có thể kiểm tra phiên bản, nhận diện message, đọc thời điểm xảy ra và sau đó giải mã `data` thành kiểu `OrderCreated`. Envelope không cần biết mọi thuộc tính của từng loại payload; nó chỉ định nghĩa phần hợp đồng chung.

## 2. Phân biệt Spring Message và envelope nghiệp vụ

Trong Spring Messaging, `Message<T>` là abstraction gồm hai phần:

- `payload`: đối tượng dữ liệu mà handler xử lý.
- `headers`: metadata dạng key-value, ví dụ ID, timestamp, content type, correlation hoặc thông tin transport.

Một Spring Message có thể được tạo bằng `MessageBuilder`:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1001", new BigDecimal("125000.00")))
    .setHeader("eventType", "com.example.order.created")
    .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
    .build();
~~~

`MessageHeaders` là cấu trúc bất biến sau khi message được tạo. Spring tự tạo các header `id` và `timestamp` cho từng message instance theo cơ chế mặc định; đây là metadata của đối tượng Spring Message. Khi tạo một message mới trong quá trình xử lý, ID và timestamp của instance mới có thể khác.

Envelope nghiệp vụ có mục đích khác. `schemaVersion`, `messageId` và `occurredAt` nằm trong payload để có thể được serialize, lưu trữ hoặc truyền sang hệ thống khác. Không nên dùng Spring `MessageHeaders.ID` làm định danh nghiệp vụ ổn định, hoặc dùng `MessageHeaders.TIMESTAMP` thay cho thời điểm sự kiện thực sự xảy ra.

| Thông tin | Spring Message header | Envelope nghiệp vụ |
|---|---|---|
| ID | ID của một Spring Message instance | ID ổn định của message logic qua các lần truyền và retry |
| Timestamp | Thời điểm tạo Spring Message instance | Thời điểm occurrence/sự kiện xảy ra |
| Content type | Gợi ý cách diễn giải payload trên transport | Có thể được mô tả trong hợp đồng serialize nếu consumer cần |
| Correlation | Metadata hỗ trợ liên kết luồng xử lý | Có thể được đưa vào envelope nếu phải tồn tại xuyên nhiều transport |
| Data | Payload của Spring Message | Trường `data` trong envelope |

Một header có thể bị adapter hoặc protocol binding lọc, đổi tên hoặc không chuyển tiếp. Nếu consumer ở một tiến trình khác bắt buộc phải có một giá trị để diễn giải nghiệp vụ, hãy đặt giá trị đó trong hợp đồng được serialize. Nếu giá trị chỉ phục vụ định tuyến hoặc xử lý nội bộ tại một hop, header thường phù hợp hơn. Tránh lưu cùng một giá trị ở cả header và envelope mà không quy định nơi nào là nguồn dữ liệu chuẩn.

## 3. Thiết kế bốn trường cốt lõi

### 3.1. Phiên bản: `schemaVersion`

Phiên bản cho biết cấu trúc envelope hoặc schema payload được diễn giải theo bộ quy tắc nào. Nên chọn tên rõ nghĩa như `schemaVersion` thay vì `version` nếu hệ thống có nhiều loại phiên bản khác nhau.

Một quy ước đơn giản là dùng số nguyên dương:

- `1`: hợp đồng ban đầu.
- `2`: phiên bản cấu trúc mới khi thay đổi không tương thích.
- Giá trị không tồn tại, bằng 0 hoặc nhỏ hơn 0 phải bị từ chối nếu hợp đồng yêu cầu trường này.

Cần phân biệt ba khái niệm:

1. **Envelope/schema version**: phiên bản cấu trúc thông điệp.
2. **Event type/version**: loại sự kiện và phiên bản ngữ nghĩa của loại sự kiện đó, ví dụ `order.created.v2`.
3. **Aggregate/entity version**: phiên bản trạng thái của một đơn hàng hoặc đối tượng nghiệp vụ, thường dùng cho optimistic locking và phát hiện cập nhật cũ.

Ba giá trị này có mục đích khác nhau. Không dùng `schemaVersion` để thay cho số thứ tự của đơn hàng, và không tăng schema version chỉ vì một đơn hàng thay đổi trạng thái.

Khi schema thay đổi, hãy thống nhất chính sách tương thích. Thêm trường tùy chọn có giá trị mặc định thường ít rủi ro hơn đổi kiểu hoặc đổi ý nghĩa trường hiện có. Tuy nhiên, consumer chỉ có thể bỏ qua trường lạ nếu JSON decoder hoặc schema validator được cấu hình cho phép. Với thay đổi phá vỡ tương thích, tạo phiên bản schema mới, triển khai consumer hỗ trợ phiên bản mới rồi mới chuyển producer; trong giai đoạn chuyển đổi có thể cần hỗ trợ đọc cả hai phiên bản.

Không tái sử dụng một tên trường cũ với ý nghĩa mới. Ví dụ, nếu `total` từng là tổng tiền trước thuế, đừng đổi nó thành tổng tiền sau thuế mà vẫn giữ nguyên schema version.

### 3.2. Định danh: `messageId`

`messageId` xác định một message logic. Producer nên tạo ID khi hình thành message và giữ nguyên ID đó qua các lần retry hoặc redelivery của cùng message.

UUID là lựa chọn phổ biến:

~~~java
UUID messageId = UUID.randomUUID();
~~~

Quy tắc quan trọng:

- Mỗi message logic mới nhận một ID mới.
- Khi gửi lại cùng message do timeout, mất ACK hoặc lỗi mạng, giữ nguyên ID.
- Không tạo lại ID ở mỗi lần retry; nếu làm vậy, consumer không thể nhận ra các bản gửi lại là cùng một message.
- ID cần duy nhất trong phạm vi producer hoặc nguồn phát. Nếu nhiều producer dùng chung một không gian ID, cần bảo đảm không va chạm hoặc thêm định danh source.
- ID không phải bí mật, token xác thực hay khóa phân quyền.

Consumer có thể dùng `messageId` làm khóa idempotency. Trước khi áp dụng tác dụng phụ, consumer kiểm tra message đã được xử lý chưa. Việc ghi nhận ID và cập nhật dữ liệu nghiệp vụ nên nằm trong cùng transaction hoặc cơ chế lưu trữ nguyên tử phù hợp; nếu chỉ ghi ID riêng rẽ, sự cố giữa hai thao tác vẫn có thể tạo trạng thái không nhất quán.

Deduplication không tự tạo ra bảo đảm exactly-once cho toàn hệ thống. Nó chỉ giúp consumer nhận diện và xử lý an toàn các lần giao lặp trong phạm vi lưu trữ và transaction mà ứng dụng kiểm soát.

### 3.3. Thời gian: `occurredAt`

`occurredAt` là thời điểm sự kiện xảy ra trong miền nghiệp vụ. Ví dụ, một đơn hàng được xác nhận lúc nào, một cảm biến ghi nhận nhiệt độ vượt ngưỡng lúc nào.

Trong Java, dùng `java.time.Instant` để biểu diễn một thời điểm trên timeline UTC:

~~~java
Instant occurredAt = Instant.now();
~~~

Khi serialize thành JSON, biểu diễn ISO 8601/RFC 3339 có múi giờ rõ ràng, thường dùng hậu tố `Z` cho UTC:

~~~text
2026-11-07T14:00:00Z
~~~

Không nhập nhằng các loại thời gian:

- `occurredAt`: lúc occurrence xảy ra ở nguồn.
- `publishedAt`: lúc producer phát message ra transport, nếu cần đo độ trễ publish.
- `receivedAt`: lúc consumer nhận message.
- `processedAt`: lúc consumer hoàn tất xử lý.

Không ghi thời điểm consumer nhận vào trường `occurredAt`, vì khi message bị trễ hoặc replay, thời điểm đó không còn phản ánh sự kiện gốc. Nếu cần đo độ trễ, giữ riêng các mốc thời gian.

Đồng hồ của các máy có thể lệch nhau. Timestamp hữu ích cho quan sát, truy vấn theo thời gian và ước lượng độ trễ, nhưng không nên là cơ chế duy nhất để sắp thứ tự tuyệt đối các sự kiện phân tán. Nếu cần thứ tự trong một aggregate, dùng sequence hoặc aggregate version; nếu cần thứ tự trong broker, dùng offset hoặc cơ chế thứ tự do transport cung cấp.

### 3.4. Dữ liệu: `data`

`data` là payload nghiệp vụ có kiểu cụ thể. Với một sự kiện tạo đơn hàng, payload có thể là `OrderCreated`; với một yêu cầu thanh toán, payload có thể là `PaymentRequested`.

Nên dùng DTO hoặc record chuyên biệt cho hợp đồng truyền qua mạng. Tránh gửi trực tiếp JPA entity hoặc object nội bộ vì chúng có thể chứa lazy relationship, proxy, trường nhạy cảm hoặc cấu trúc phụ thuộc vào persistence layer.

Một payload tốt có các đặc điểm:

- Chứa dữ liệu consumer cần để hiểu và xử lý message.
- Có tên trường, kiểu dữ liệu và đơn vị đo rõ ràng.
- Không phụ thuộc vào implementation class hoặc package nội bộ của producer.
- Không chứa mật khẩu, access token, secret hoặc dữ liệu cá nhân không cần thiết.
- Có giới hạn kích thước và được validate trước khi xử lý.
- Quy định rõ trường nào bắt buộc, trường nào có thể thiếu, và `null` có nghĩa gì.

Nếu payload thay đổi độc lập với envelope, có thể quản lý schema payload riêng hoặc dùng `dataSchema`/schema registry. Điều này giúp không phải thay đổi cấu trúc envelope chỉ vì một trường nghiệp vụ được thêm vào.

## 4. Định nghĩa envelope bằng Java record

Java 17 record phù hợp để mô hình hóa một hợp đồng dữ liệu bất biến:

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record Envelope<T>(
    int schemaVersion,
    UUID messageId,
    Instant occurredAt,
    T data
) {
    public Envelope {
        if (schemaVersion < 1) {
            throw new IllegalArgumentException("schemaVersion must be positive");
        }
        Objects.requireNonNull(messageId, "messageId must not be null");
        Objects.requireNonNull(occurredAt, "occurredAt must not be null");
        Objects.requireNonNull(data, "data must not be null");
    }
}
~~~

Generic type `T` cho phép tái sử dụng envelope với nhiều payload khác nhau mà vẫn giữ kiểu compile-time. Compact constructor kiểm tra invariant ngay lúc tạo đối tượng. Các kiểm tra này không thay thế việc validate JSON đầu vào: dữ liệu nhận từ mạng phải được deserialize thành đối tượng hợp lệ trước khi gọi business handler.

Ví dụ payload:

~~~java
import java.math.BigDecimal;

public record OrderCreated(
    String orderId,
    BigDecimal total
) {
    public OrderCreated {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (total == null || total.signum() < 0) {
            throw new IllegalArgumentException("total must be non-negative");
        }
    }
}
~~~

Khi tạo message trong producer, sinh ID và thời gian một lần tại ranh giới tạo message:

~~~java
Envelope<OrderCreated> envelope = new Envelope<>(
    1,
    UUID.randomUUID(),
    Instant.now(),
    new OrderCreated("ORD-1001", new BigDecimal("125000.00"))
);
~~~

Nếu cần retry việc gửi, giữ nguyên đối tượng envelope hoặc ít nhất giữ nguyên các trường ID và thời gian của nó. Không gọi lại factory để tạo một envelope mới cho cùng một message logic.

## 5. Đưa envelope vào Spring Messaging

Có thể đặt envelope làm payload của Spring Message và dùng headers cho metadata phục vụ routing hoặc transport:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<Envelope<OrderCreated>> message = MessageBuilder
    .withPayload(envelope)
    .setHeader("eventType", "com.example.order.created")
    .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
    .build();
~~~

Trong ví dụ này:

- `envelope.messageId()` là ID ổn định của message nghiệp vụ.
- `message.getHeaders().get(MessageHeaders.ID)` là ID của Spring Message instance.
- `envelope.occurredAt()` là thời điểm sự kiện xảy ra.
- `message.getHeaders().get(MessageHeaders.TIMESTAMP)` là timestamp do Spring gắn với message instance.
- `eventType` là header tùy chỉnh để định tuyến hoặc phân loại ở tầng messaging.
- `CONTENT_TYPE` mô tả loại payload cho tầng xử lý phù hợp.

Khi dùng RSocket requester, có thể gửi envelope như payload:

~~~java
Mono<Void> sendOrderCreated(
    RSocketRequester requester,
    Envelope<OrderCreated> envelope
) {
    return requester
        .route("events.order-created")
        .data(envelope)
        .send();
}
~~~

RSocket route xác định đích xử lý; envelope mang hợp đồng dữ liệu. Bộ encoder/decoder được cấu hình cho RSocket quyết định cách đối tượng được chuyển thành bytes và phục hồi ở phía nhận. Việc đặt object vào `Message` hoặc gọi `data(envelope)` không tự đảm bảo rằng mọi header nội bộ của Spring sẽ được serialize vào body. Hãy xác định rõ phần nào nằm trong body và phần nào được map sang metadata của transport.

## 6. Kiểm tra message trước khi xử lý

Consumer nên kiểm tra envelope ở ranh giới hệ thống, trước khi thực hiện side effect:

1. Kiểm tra JSON hoặc payload có deserialize được không.
2. Kiểm tra `schemaVersion` có được consumer hỗ trợ không.
3. Kiểm tra `messageId`, `occurredAt` và `data` có hiện diện và đúng kiểu không.
4. Kiểm tra các invariant nghiệp vụ của payload: ID hợp lệ, số tiền không âm, đơn vị đo được hỗ trợ.
5. Kiểm tra kích thước message và giới hạn tài nguyên.
6. Xác thực nguồn gửi bằng cơ chế bảo mật của transport hoặc ứng dụng; không tin `source` hay `messageId` chỉ vì chúng có mặt trong JSON.
7. Kiểm tra idempotency trước khi áp dụng tác dụng phụ.

Không nên dùng một schema version chưa được hỗ trợ rồi cố gắng diễn giải theo phiên bản gần nhất. Nếu không thể xử lý an toàn, trả lỗi có phân loại, đưa message vào dead-letter hoặc quy trình quarantine theo chính sách hệ thống, và giữ lại thông tin đủ để điều tra.

## 7. Correlation ID, causation ID và trace ID

Envelope bốn trường là nền tảng nhỏ gọn. Hệ thống lớn thường cần thêm metadata để liên kết nhiều message:

- **correlationId** liên kết một nhóm message thuộc cùng một workflow hoặc request gốc.
- **causationId** cho biết message hiện tại được tạo ra do message nào trước đó.
- **traceId** liên kết log, span và trace phân tán của một lần thực thi.

Các ID này không thay thế `messageId`. Một workflow có thể phát nhiều message khác nhau: mỗi message có `messageId` riêng nhưng cùng `correlationId`. Message được tạo từ một message khác có thể ghi `causationId` bằng ID của message nguồn.

Nếu các giá trị chỉ cần tồn tại trong một hop, Spring headers hoặc tracing context có thể phù hợp. Nếu chúng phải sống sót qua broker, outbox, lưu trữ hoặc replay, đưa chúng vào hợp đồng bền vững hoặc một chuẩn metadata đã thống nhất.

## 8. Tiến hóa schema mà không làm hỏng consumer

Hợp đồng thông điệp thường tồn tại lâu hơn một lần triển khai. Producer và consumer có thể được nâng cấp ở các thời điểm khác nhau, nên cần thiết kế tương thích.

Một chiến lược thực tế:

- Ưu tiên thêm trường tùy chọn, không đổi ý nghĩa trường hiện có.
- Chọn default rõ ràng cho trường mới khi consumer đọc message cũ.
- Chỉ yêu cầu consumer bỏ qua field chưa biết khi decoder/schema validator thực sự hỗ trợ hành vi đó.
- Không đổi kiểu dữ liệu từ số sang chuỗi hoặc ngược lại trong cùng một phiên bản.
- Không đổi đơn vị đo mà giữ nguyên tên trường; nếu cần đổi, đặt tên mới và chuyển đổi có chủ đích.
- Với thay đổi không tương thích, tạo schema version mới và hỗ trợ song song trong thời gian chuyển đổi.
- Lưu schema cùng ví dụ payload để producer và consumer có thể kiểm thử contract.

Ví dụ, thêm `currency` vào `OrderCreated` có thể tương thích nếu trường mới là tùy chọn và consumer cũ bỏ qua trường lạ. Đổi `total` từ số tiền đã bao gồm thuế thành số tiền chưa bao gồm thuế là thay đổi ngữ nghĩa; cần version hoặc field mới.

Không nhầm version của envelope với version của event type. Nếu có nhiều loại event, một hệ thống có thể dùng schema version riêng cho từng type hoặc quản lý schema qua registry. Hãy chọn một chiến lược nhất quán và ghi rõ nơi authoritative của version.

## 9. Liên hệ với CloudEvents

Nếu cần hợp đồng event có khả năng tương tác giữa nhiều nền tảng, hãy xem xét chuẩn CloudEvents. CloudEvents 1.0 định nghĩa các context attributes cốt lõi:

- `specversion`: phiên bản đặc tả CloudEvents, ví dụ `1.0`.
- `id`: định danh event.
- `source`: nguồn phát; cặp `source` + `id` xác định duy nhất event.
- `type`: loại occurrence được mô tả.
- `time`: thời điểm occurrence xảy ra, là trường tùy chọn.
- `data`: payload nghiệp vụ, là trường tùy chọn trong chuẩn.

Điểm cần chú ý: `specversion` là phiên bản đặc tả CloudEvents, không nhất thiết là version của schema nghiệp vụ trong `data`. CloudEvents còn có `datacontenttype` và `dataschema` để mô tả định dạng và schema của payload.

Envelope nội bộ với `schemaVersion`, `messageId`, `occurredAt`, `data` là một hợp đồng ứng dụng hợp lệ, nhưng không tự động trở thành CloudEvent. Nếu tuyên bố tuân thủ CloudEvents, phải đáp ứng đầy đủ các thuộc tính bắt buộc và quy tắc encoding của chuẩn.

## 10. Ví dụ Java 17 chạy được với Spring Messaging

Ví dụ này tạo một envelope, bọc nó trong Spring `Message`, rồi in các trường quan trọng. Các giá trị ID và thời gian nghiệp vụ được cố định để output có thể đối chiếu chính xác.

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>message-envelope-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**EnvelopeDemo.java**:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

public class EnvelopeDemo {

    record OrderCreated(String orderId, BigDecimal total) {}

    record Envelope<T>(
        int schemaVersion,
        UUID messageId,
        Instant occurredAt,
        T data
    ) {
        Envelope {
            if (schemaVersion < 1) {
                throw new IllegalArgumentException("schemaVersion must be positive");
            }
            Objects.requireNonNull(messageId, "messageId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            Objects.requireNonNull(data, "data");
        }
    }

    public static void main(String[] args) {
        Envelope<OrderCreated> envelope = new Envelope<>(
            1,
            UUID.fromString("7e4a6e9a-6e2f-4e6b-9e8f-4b7e1e8c1001"),
            Instant.parse("2026-11-07T14:00:00Z"),
            new OrderCreated("ORD-1001", new BigDecimal("125000.00"))
        );

        Message<Envelope<OrderCreated>> message = MessageBuilder
            .withPayload(envelope)
            .setHeader("eventType", "com.example.order.created")
            .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
            .build();

        System.out.println("schemaVersion = " + message.getPayload().schemaVersion());
        System.out.println("messageId = " + message.getPayload().messageId());
        System.out.println("occurredAt = " + message.getPayload().occurredAt());
        System.out.println("data = " + message.getPayload().data());
        System.out.println("springHeaderIdPresent = "
            + (message.getHeaders().get(MessageHeaders.ID) != null));
        System.out.println("eventType = " + message.getHeaders().get("eventType"));
        System.out.println("contentType = "
            + message.getHeaders().get(MessageHeaders.CONTENT_TYPE));
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` và `EnvelopeDemo.java`.

Linux/macOS:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=cp.txt
javac -cp "$(cat cp.txt)" EnvelopeDemo.java
java -cp ".:$(cat cp.txt)" EnvelopeDemo
~~~

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=cp.txt"
$cp = (Get-Content .\cp.txt -Raw).Trim()
javac -cp $cp .\EnvelopeDemo.java
java -cp ".;$cp" EnvelopeDemo
~~~

Output:

~~~text
schemaVersion = 1
messageId = 7e4a6e9a-6e2f-4e6b-9e8f-4b7e1e8c1001
occurredAt = 2026-11-07T14:00:00Z
data = OrderCreated[orderId=ORD-1001, total=125000.00]
springHeaderIdPresent = true
eventType = com.example.order.created
contentType = application/json
~~~

Chương trình minh họa việc tạo envelope và bọc bằng Spring Message trong bộ nhớ. JSON ở phần đầu là dạng wire representation minh họa; để gửi JSON thật, ứng dụng cần cấu hình encoder/decoder hoặc serializer tương ứng. Header `eventType` và `contentType` trong ví dụ là metadata của Spring Message, không tự động được chèn vào JSON body.

## 11. Lỗi thiết kế thường gặp

1. **Dùng Spring header ID làm message ID nghiệp vụ.** ID của Spring xác định message instance; tạo message mới có thể sinh ID khác. Hãy giữ ID logic trong envelope.
2. **Dùng thời điểm nhận thay cho thời điểm xảy ra.** Message trễ hoặc replay sẽ làm sai timeline. Giữ riêng `occurredAt`, `receivedAt` và `processedAt`.
3. **Tạo ID mới khi retry.** Consumer xem mỗi lần gửi lại là message mới và có thể thực hiện side effect lặp. Giữ ID của message logic.
4. **Coi timestamp là thứ tự tuyệt đối.** Đồng hồ giữa máy có thể lệch. Dùng sequence, aggregate version hoặc offset khi cần thứ tự đáng tin cậy.
5. **Dùng một version cho nhiều khái niệm.** Schema version, event type version và entity version có vòng đời khác nhau.
6. **Đổi ý nghĩa field mà không đổi hợp đồng.** Consumer có thể vẫn deserialize thành công nhưng xử lý sai dữ liệu.
7. **Đưa entity persistence trực tiếp vào data.** Proxy, quan hệ lazy và thay đổi schema database làm hợp đồng messaging dễ vỡ.
8. **Nhồi metadata không cần thiết vào envelope.** Chỉ thêm correlation, causation, source hoặc trace khi có yêu cầu xuyên hệ thống rõ ràng.
9. **Tin metadata do producer gửi mà không xác thực.** ID, timestamp và source do bên gửi kiểm soát; chúng không phải bằng chứng xác thực hay phân quyền.
10. **Cho rằng MessageBuilder sẽ tự serialize toàn bộ message.** Spring Message là abstraction trong ứng dụng; transport encoder và header mapper quyết định dữ liệu nào thực sự đi qua wire.

## 12. Checklist thiết kế hợp đồng

Trước khi công bố một message type, hãy xác nhận:

- [ ] Tên và ý nghĩa của `schemaVersion` được định nghĩa rõ.
- [ ] `messageId` duy nhất trong phạm vi nguồn phát và được giữ nguyên khi retry.
- [ ] `occurredAt` là thời điểm occurrence, dùng `Instant`/UTC và định dạng serialize thống nhất.
- [ ] `data` có DTO/record riêng, kiểu dữ liệu, đơn vị và quy tắc null rõ ràng.
- [ ] Consumer kiểm tra version, dữ liệu bắt buộc, kích thước và invariant nghiệp vụ.
- [ ] Có chính sách deduplication/idempotency gắn với transaction nghiệp vụ.
- [ ] Có quy tắc tương thích và kế hoạch chuyển đổi khi schema thay đổi.
- [ ] Phân biệt metadata của Spring Message với trường hợp đồng phải tồn tại xuyên transport.
- [ ] Nếu cần liên thông đa nền tảng, đánh giá việc áp dụng CloudEvents thay vì tự đặt một chuẩn nửa vời.

## Tài liệu tham khảo

- [Spring Framework Javadoc — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html): abstraction payload và headers.
- [Spring Framework Javadoc — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html): các header chuẩn như `ID`, `TIMESTAMP`, `CONTENT_TYPE`.
- [Spring Framework Javadoc — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html): tạo message và thiết lập header.
- [Spring Integration — Message](https://docs.spring.io/spring-integration/reference/message.html): ý nghĩa payload, header, ID và timestamp trong messaging.
- [CloudEvents Specification](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md): chuẩn hóa context attributes, định danh `source` + `id`, thời gian occurrence và event data.
