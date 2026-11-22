# MessageHeaders và tính bất biến của metadata

Trong Spring Integration, một `Message<T>` mang **payload** (dữ liệu nghiệp vụ) và **headers** (metadata mô tả cách thông điệp cần được xử lý). Khi triển khai Enterprise Integration Patterns (EIP), các thành phần như Router, Filter, Transformer, Splitter, Aggregator và Gateway thường không cần biết toàn bộ cấu trúc payload; chúng có thể quyết định luồng xử lý dựa vào metadata. `MessageHeaders` cung cấp tập khóa–giá trị đó dưới giao diện gần với `Map<String, Object>`, nhưng có một quy tắc thiết kế quan trọng: **không thể sửa trực tiếp tập header của một message đã được tạo**.

Bài học thuộc chương **Message system** của module **SPRING_INTEGRATION_PATTERN**. Mục tiêu là hiểu cách metadata vận hành trong luồng thông điệp ít phụ thuộc, biết tạo message mới khi cần đổi headers, và tránh lỗi về tính nhất quán khi router, retry, error channel, splitter/aggregator hoặc nhiều consumer cùng xử lý thông điệp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt payload, metadata, `Message` và `MessageHeaders` trong Spring Messaging / Spring Integration.
2. Giải thích chính xác tính bất biến của cấu trúc headers và giới hạn của tính bất biến đó đối với **giá trị** header.
3. Đọc header chuẩn, header của Spring Integration và header nghiệp vụ bằng API phù hợp.
4. Sử dụng `MessageBuilder` để thêm, thay thế, loại bỏ hoặc sao chép headers khi tạo **message mới**.
5. Xử lý `id`, `timestamp`, `correlationId`, `sequenceNumber`, `replyChannel` và `errorChannel` đúng vai trò.
6. Thiết kế và kiểm thử luồng truyền metadata, tránh mất header hoặc chia sẻ tham chiếu mutable.

## 2. Message và MessageHeaders nằm ở đâu trong kiến trúc?

Abstraction cốt lõi thuộc module `spring-messaging`:

~~~java
package org.springframework.messaging;

public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

Với một đơn hàng, payload có thể chứa mã đơn, sản phẩm và giá trị; headers có thể chứa mã tenant, trace ID, độ ưu tiên hoặc đích phản hồi. Một message chỉ cung cấp getter cho payload và headers, không cung cấp setter để sửa thông điệp đã tồn tại.

~~~mermaid
flowchart LR
    A["Message&lt;Order&gt;"] --> B["Payload: Order"]
    A --> C["MessageHeaders"]
    C --> D["tenantId, traceId: metadata nghiệp vụ"]
    C --> E["id, timestamp: metadata hệ thống"]
    C --> F["replyChannel, errorChannel: điều khiển luồng"]
    A --> G["Channel / Handler / Router"]
~~~

Về mặt kiểu Java, `MessageHeaders` triển khai `Map<String, Object>`. Điều này cho phép đọc bằng `get`, `containsKey`, `entrySet`, ... nhưng **không** có nghĩa bạn được thay đổi tập khóa–giá trị sau khi message được khởi tạo.

Trong EIP, headers giúp:

- **Router** chọn nhánh xử lý theo `region`, `priority` hoặc `tenantId`.
- **Filter** cho phép hoặc loại một message dựa trên thuộc tính metadata.
- **Transformer** thay đổi payload hoặc tạo message mới, đồng thời quyết định giữ những headers nào.
- **Splitter / Aggregator** sử dụng thông tin tương quan và thứ tự để ghép nhóm.
- **Gateway** và **error flow** biết nơi nhận phản hồi hoặc xử lý lỗi.
- **Retry / logging / tracing** theo dõi lần xử lý và một luồng nghiệp vụ chạy qua nhiều bước.

## 3. Những header nào thường gặp?

### 3.1. Header chuẩn của Spring Messaging

Các hằng khóa nằm trong `org.springframework.messaging.MessageHeaders`:

| Header | Kiểu dữ liệu điển hình | Vai trò | Lưu ý sử dụng |
|---|---|---|---|
| `MessageHeaders.ID` | `UUID` | Định danh một **message instance** | Do framework sinh; không dùng thay mã đơn hàng hay correlation ID |
| `MessageHeaders.TIMESTAMP` | `Long` | Thời điểm tạo message, tính bằng epoch milliseconds | Không dùng làm khóa duy nhất; nhiều message có thể cùng timestamp |
| `MessageHeaders.REPLY_CHANNEL` | `String` hoặc `MessageChannel` | Điểm nhận reply trong trao đổi yêu cầu–phản hồi | Header điều khiển framework, tránh ghi đè tùy tiện |
| `MessageHeaders.ERROR_CHANNEL` | `String` hoặc `MessageChannel` | Kênh tiếp nhận lỗi | Có ý nghĩa trong xử lý lỗi của integration flow |
| `MessageHeaders.CONTENT_TYPE` | Giá trị phù hợp cơ chế chuyển đổi | Gợi ý loại nội dung cho converter hoặc adapter | Nội dung, cách biểu diễn tùy giao thức và adapter |

Có thể đọc nhanh các giá trị hệ thống:

~~~java
import java.util.UUID;
import org.springframework.messaging.Message;

void inspect(Message<?> message) {
    UUID id = message.getHeaders().getId();
    Long timestamp = message.getHeaders().getTimestamp();
    Object replyChannel = message.getHeaders().getReplyChannel();
    Object errorChannel = message.getHeaders().getErrorChannel();

    System.out.printf("id=%s, timestamp=%s%n", id, timestamp);
}
~~~

`id` và `timestamp` được quản lý như những header **read-only** trong cơ chế xây dựng message thông thường của Spring Integration. Khi nội dung message thay đổi và một message instance mới được tạo, ID mới thường được sinh; timestamp phản ánh thời điểm tạo mới. Không tự đặt hai header này bằng `setHeader` để cố giữ nguyên định danh.

### 3.2. Header của Spring Integration

Các hằng khóa đặc thù nằm trong `org.springframework.integration.IntegrationMessageHeaderAccessor`.

| Header | Vai trò khi dùng EIP |
|---|---|
| `CORRELATION_ID` | Nhóm các message cùng một chuỗi công việc, đặc biệt hữu ích cho Aggregator |
| `SEQUENCE_NUMBER` | Số thứ tự của message trong một nhóm được tách |
| `SEQUENCE_SIZE` | Số message dự kiến của nhóm, nếu biết |
| `PRIORITY` | Độ ưu tiên, được một số thành phần như `PriorityChannel` sử dụng |
| `EXPIRATION_DATE` | Metadata thời điểm hết hạn; tự nó không khiến framework loại message ở mọi nơi |
| `DUPLICATE_MESSAGE` | Dấu hiệu phát hiện bản tin trùng trong cơ chế idempotent receiver |
| `DELIVERY_ATTEMPT` | Thông tin số lần giao/xử lý trong một số adapter có retry |
| `ACKNOWLEDGMENT_CALLBACK` | Callback xác nhận/khước từ hoặc requeue theo adapter |

Cần phân biệt rõ: `id` là định danh **của một message**, còn `correlationId` có thể giữ ổn định qua **nhiều message** thuộc cùng giao dịch hoặc nhóm. Không nên giả định mọi adapter hay endpoint đều tự gắn mọi header ở bảng trên; nhiều header chỉ xuất hiện khi đã dùng thành phần có hỗ trợ.

`IntegrationMessageHeaderAccessor` cung cấp cách đọc có kiểu cho một số header:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

void inspectIntegrationHeaders(Message<?> message) {
    IntegrationMessageHeaderAccessor accessor =
            new IntegrationMessageHeaderAccessor(message);

    Object correlationId = accessor.getCorrelationId();
    int sequenceNumber = accessor.getSequenceNumber();
    int sequenceSize = accessor.getSequenceSize();

    System.out.printf("group=%s, part=%d/%d%n",
            correlationId, sequenceNumber, sequenceSize);
}
~~~

Khi một message không mang thông tin chuỗi, đừng tự suy ra rằng nó là phần tử duy nhất trong một nhóm. Hãy kiểm tra các header có liên quan hoặc hợp đồng của endpoint trước khi xử lý kết quả.

### 3.3. Header nghiệp vụ do ứng dụng quy định

Bạn cũng có thể dùng header tùy biến như `tenantId`, `region`, `schemaVersion`, `sourceSystem`, `traceId`. Nên đặt tên nhất quán, ghi rõ kiểu dữ liệu và quy tắc truyền qua các bước. Ví dụ, `tenantId` là `String` bất biến; `schemaVersion` có thể là `Integer`; `traceId` nên là một chuỗi an toàn để ghi log theo chính sách của hệ thống.

Không đưa secret, access token hoặc dữ liệu cá nhân nhạy cảm vào headers chỉ để tiện debug: nhiều hệ thống log toàn bộ message, kể cả metadata.

## 4. Tính bất biến của MessageHeaders: đúng đến đâu?

### 4.1. Bất biến về cấu trúc tập header

`MessageHeaders` có API đọc giống `Map`, nhưng những thao tác sửa tập header như `put`, `putAll`, `remove` hay `clear` ném `UnsupportedOperationException`.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder.withPayload("ORDER-1001")
        .setHeader("tenantId", "shop-a")
        .build();

// Đọc: hợp lệ
String tenantId = message.getHeaders().get("tenantId", String.class);

// Sửa trực tiếp: lỗi UnsupportedOperationException
message.getHeaders().put("tenantId", "shop-b");
~~~

Thông điệp không tự biến thành `shop-b` sau dòng cuối; thao tác sửa sẽ thất bại. Một component đang cầm message cũ vì thế không bị thay đổi **cấu trúc metadata** bởi việc component khác gọi `put` trên chính đối tượng `MessageHeaders` đó.

### 4.2. Không tự động bất biến sâu

**Bất biến của map không kéo theo bất biến của object được map tham chiếu.** Giá trị header và chính payload có thể là một `List`, `Map` hay object mutable. Nếu code khác còn giữ tham chiếu của object đó, việc sửa nội dung vẫn có thể quan sát được từ message.

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

List<String> tags = new ArrayList<>(List.of("urgent"));

Message<String> message = MessageBuilder.withPayload("ORDER-1001")
        .setHeader("tags", tags)
        .build();

tags.add("review"); // Hợp lệ với ArrayList; thay đổi cùng object được tham chiếu

System.out.println(message.getHeaders().get("tags"));
// Có thể nhìn thấy [urgent, review] vì giá trị header vẫn là mutable List.
~~~

Để metadata ổn định, hãy tạo bản sao không sửa được **trước khi đưa vào header**:

~~~java
List<String> mutableTags = new ArrayList<>(List.of("urgent"));
List<String> snapshot = List.copyOf(mutableTags);

Message<String> safe = MessageBuilder.withPayload("ORDER-1001")
        .setHeader("tags", snapshot)
        .build();

mutableTags.add("review"); // snapshot trong message vẫn chỉ có "urgent"
~~~

`List.copyOf` phù hợp khi các phần tử cũng đủ bất biến. Với cấu trúc lồng nhau, cần sao chép và khóa các object con; `Map.copyOf` hay `List.copyOf` không tự tạo bản sao sâu cho từng value. Quy tắc này đặc biệt quan trọng ở `PublishSubscribeChannel`, asynchronous channels, retry và những xử lý có thể chạy song song.

### 4.3. Phân biệt ba ý tưởng

| Điều cần hỏi | Kết luận |
|---|---|
| Có thể thêm/xóa khóa ngay trên `message.getHeaders()`? | Không, `MessageHeaders` chặn thao tác sửa |
| Có thể thay payload bằng setter trên `Message`? | Không có setter trên interface `Message`; cần tạo message khác khi đổi payload |
| Một object mutable nằm trong payload/header có thể bị sửa qua tham chiếu không? | Có thể; lập trình viên phải chọn dữ liệu bất biến, snapshot hoặc kiểm soát chia sẻ |

Tính bất biến ở đây là **hợp đồng của message và cấu trúc headers trong cách dùng thông thường**, không phải lời bảo đảm mọi object được tham chiếu bên trong đều bất biến. Spring Integration còn có `MutableMessage` cho những trường hợp chủ ý tối ưu với nội dung có thể thay đổi; bài này tập trung vào cách dùng mặc định với `GenericMessage` và `MessageBuilder`.

## 5. Tạo và thay đổi metadata đúng cách bằng MessageBuilder

Đối với message đang tồn tại, hãy xây dựng **message mới** có payload/headers mong muốn. Trong ví dụ tiếp theo, sử dụng `org.springframework.messaging.support.MessageBuilder` (API Spring Messaging; Spring Integration cũng có builder tương ứng trong gói `org.springframework.integration.support`).

### 5.1. Tạo một message có metadata nghiệp vụ

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> incoming = MessageBuilder.withPayload("ORDER-1001")
        .setHeader("tenantId", "shop-a")
        .setHeader("traceId", "trace-2026-001")
        .setHeader("region", "north")
        .setHeaderIfAbsent("sourceSystem", "checkout")
        .build();

String tenant = incoming.getHeaders().get("tenantId", String.class);
String region = incoming.getHeaders().get("region", String.class);
~~~

`setHeaderIfAbsent` chỉ đặt giá trị khi header đó chưa có; `setHeader` dùng để đặt hoặc cập nhật giá trị ở builder đang được cấu hình.

### 5.2. Đổi header bằng cách sinh message mới

~~~java
Message<String> routed = MessageBuilder.fromMessage(incoming)
        .setHeader("route", "orders.north")
        .removeHeader("debugFlag")
        .build();

// incoming không bị sửa
System.out.println(incoming.getHeaders().get("route")); // null
System.out.println(routed.getHeaders().get("route"));   // "orders.north"
System.out.println(routed.getHeaders().get("tenantId")); // "shop-a"
~~~

`fromMessage` tiện khi vẫn giữ payload gốc và muốn sửa một số header. Một message mới được tạo ra, do đó cùng payload không đồng nghĩa cùng message identity. Cũng lưu ý: nếu payload là object mutable, builder không mặc nhiên deep-copy payload.

### 5.3. Thay payload và sao chép những header cần thiết

~~~java
Message<String> normalized = MessageBuilder
        .withPayload(incoming.getPayload().trim().toUpperCase())
        .copyHeaders(incoming.getHeaders())
        .setHeader("normalized", true)
        .build();

Message<String> outbound = MessageBuilder
        .withPayload("ORDER-SUMMARY-1001")
        .setHeader("region", "central")
        .copyHeadersIfAbsent(incoming.getHeaders())
        .build();

// outbound.region vẫn là "central" vì copyHeadersIfAbsent không ghi đè.
~~~

Dùng `copyHeaders` khi muốn mang các giá trị sang message mới; dùng `copyHeadersIfAbsent` khi header do bước hiện tại đặt phải được ưu tiên. Trong cách xây dựng chuẩn của Spring Integration, `id` và `timestamp` là header read-only, được xử lý riêng; đừng dùng sao chép để cố ép ID message cũ lên message mới.

Nếu message băng qua ranh giới tin cậy (ví dụ từ HTTP vào internal queue), không nên tự động sao chép mọi header. Hãy chọn whitelist các header hợp lệ, có kiểu đúng và được phép đi tiếp.

### 5.4. Accessor khác với việc sửa MessageHeaders

`MessageHeaderAccessor` hỗ trợ một quy trình **chuẩn bị** metadata; trong khi `MessageHeaders` của message đã được phát hành thể hiện tập header dành cho việc đọc. Khi cần tạo/cập nhật message, ưu tiên `MessageBuilder` hoặc cấu hình `Header Enricher` / `Header Filter` trong luồng integration. Tránh dựa vào cơ chế internal hoặc ép kiểu để lách tính bất biến.

## 6. Metadata đi qua Router, Transformer, Splitter và Aggregator như thế nào?

Xét luồng xử lý đơn hàng:

~~~mermaid
flowchart LR
    A["Gateway / inbound adapter"] --> B["Enrich headers"]
    B --> C{"Router: region / priority"}
    C -->|fast| D["Fast lane"]
    C -->|normal| E["Normal lane"]
    D --> F["Transformer"]
    E --> F
    F --> G["Splitter"]
    G --> H["Aggregator"]
    H --> I["Outbound adapter"]
    F -.->|exception| J["errorChannel"]
~~~

Mỗi bước phải có hợp đồng rõ ràng về metadata nào sẽ có mặt ở đầu ra. Ví dụ:

| Thành phần | Header có thể dùng | Điều cần kiểm soát |
|---|---|---|
| Header Enricher | `sourceSystem`, `tenantId`, `traceId` | Chỉ bổ sung dữ liệu đã xác thực; tránh ghi đè metadata điều khiển |
| Router | `region`, `priority` | Xác định nhánh mặc định khi header thiếu/sai kiểu |
| Filter | `schemaVersion`, `tenantId` | Không tin mù quáng vào header do client bên ngoài gửi |
| Transformer | `traceId`, `tenantId` | Nắm rõ quy tắc propagate header khi trả payload khác với trả cả `Message` |
| Splitter | `correlationId`, `sequenceNumber`, `sequenceSize` | Cần tương quan nhất quán để nhóm các phần |
| Aggregator | `correlationId`, sequence metadata | Tránh nhóm nhầm hai giao dịch; có chiến lược timeout/expire |
| Gateway / error flow | `replyChannel`, `errorChannel` | Đảm bảo reply/error đến đúng nơi; không thay tùy tiện |
| Retry / observability | `deliveryAttempt`, `traceId` | Không cho rằng retry tạo ID nghiệp vụ mới; kiểm soát idempotency |

### 6.1. Ví dụ định tuyến theo header

Một phương thức Router trong Spring Integration có thể đọc trực tiếp header bằng annotation `@Header`:

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderRouter {

    @Router(inputChannel = "orders.toRoute")
    public String destination(@Header("region") String region) {
        return "north".equalsIgnoreCase(region)
                ? "orders.north"
                : "orders.other";
    }
}
~~~

Đây là ví dụ cho router dựa trên giá trị đã chuẩn hóa. Trước khi đưa vào luồng thật, cần xác định cách xử lý khi `region` thiếu, rỗng hoặc không hợp lệ; khi phù hợp, thêm validation hoặc kênh mặc định. Router chỉ đọc metadata để chọn channel và không cần thay đổi headers trực tiếp.

### 6.2. Transformer trả payload so với trả Message

Theo cơ chế truyền header của Spring Integration, nhiều endpoint tạo đầu ra sẽ mang theo header đầu vào theo mặc định. Với **Transformer**, có khác biệt cần chú ý:

- Nếu transformer chỉ trả **payload mới**, framework thông thường có thể truyền headers đầu vào sang message đầu ra.
- Nếu transformer trả về **cả một `Message` hoàn chỉnh**, code transformer chịu trách nhiệm xác định toàn bộ nội dung và headers của message đầu ra. Đừng giả định tất cả header cũ vẫn còn.
- Header có sẵn trong message đầu ra thường được ưu tiên; các endpoint cụ thể còn có cấu hình không truyền một số header.

Ví dụ chủ động sao chép metadata khi tự trả về `Message`:

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class OrderNormalizer {

    @Transformer(inputChannel = "orders.raw",
                 outputChannel = "orders.normalized")
    public Message<String> normalize(Message<String> input) {
        String cleaned = input.getPayload().strip().toUpperCase();

        return MessageBuilder.withPayload(cleaned)
                .copyHeaders(input.getHeaders())
                .setHeader("normalized", true)
                .build();
    }
}
~~~

Ở ví dụ này, không có thao tác sửa `input.getHeaders()`. Message trả về giữ những metadata được sao chép và thêm `normalized`, còn ID/timestamp được framework xử lý theo hợp đồng tạo message.

### 6.3. Correlation và sequence khi chia/gộp

Khi một đơn hàng được Splitter tách thành ba dòng hàng, các message con thường cần chung một correlation key, có sequence number khác nhau và sequence size phản ánh số phần. Aggregator dùng các thông tin này (hoặc correlation/release strategy đã cấu hình) để gộp đúng nhóm.

Ví dụ về **ý nghĩa metadata** (minh họa, không phải yêu cầu tự gắn thủ công mọi header):

| Message | Correlation ID | Sequence number | Sequence size |
|---|---|---:|---:|
| Dòng hàng A | `order-1001` | 1 | 3 |
| Dòng hàng B | `order-1001` | 2 | 3 |
| Dòng hàng C | `order-1001` | 3 | 3 |

Nếu tùy tiện thay correlation ID trong một nhánh, Aggregator có thể không gộp đủ. Ngược lại, lấy `MessageHeaders.ID` làm correlation key cho từng phần riêng biệt có thể khiến mỗi phần rơi vào một nhóm khác nhau. Một transaction ID / order ID nên được định nghĩa rõ từ đầu, đồng thời cấu hình timeout và chiến lược xử lý nhóm thiếu phần.

### 6.4. Reply, error và retry headers

`replyChannel` và `errorChannel` là metadata điều khiển luồng do framework hiểu. Chúng có thể là tên channel hoặc object `MessageChannel` phù hợp. Các cơ chế Gateway, asynchronous processing và error handling có thể phụ thuộc vào những giá trị này, nên tránh loại bỏ trong bước filter header nếu chưa kiểm chứng điều kiện phản hồi/lỗi.

`deliveryAttempt` trong một số ngữ cảnh là object `AtomicInteger`. Đây chính là ví dụ cho giới hạn của “header immutable”: **entry** trong map là read-only nhưng **object value** có thể thay đổi số đếm. Do đó không lấy việc `MessageHeaders` bất biến để kết luận retry counter hay mọi metadata khác không thể thay đổi.

## 7. Những lỗi thiết kế phổ biến

### Lỗi 1 — Sửa trực tiếp headers sau khi nhận message

~~~java
// Sai: MessageHeaders không cho thay cấu trúc sau khi tạo.
message.getHeaders().put("status", "processed");

// Đúng: tạo message mới có metadata mong muốn.
Message<String> processed = MessageBuilder.fromMessage(message)
        .setHeader("status", "processed")
        .build();
~~~

### Lỗi 2 — Dùng ID message như khóa nghiệp vụ xuyên suốt luồng

`MessageHeaders.ID` nhận diện message instance, nên có thể khác sau bước transform hoặc rebuild. Hãy dùng `orderId` trong payload, `businessCorrelationId` do ứng dụng định nghĩa, hoặc `correlationId` theo hợp đồng EIP. ID message vẫn hữu ích cho quan sát một lần phát sinh cụ thể.

### Lỗi 3 — Trộn thông tin routing với dữ liệu chưa xác thực

Một client gửi `tenantId=admin` hoặc `priority=999` không có nghĩa hệ thống nên tin và đưa message vào nhánh đặc quyền. Chuẩn hóa, xác thực và giới hạn header trước khi router/filter sử dụng; không để metadata bên ngoài ghi đè metadata nội bộ được kiểm soát.

### Lỗi 4 — Chia sẻ object mutable giữa nhiều consumer

Nếu hai consumer nhận cùng message nhưng một bên sửa `List` trong header hoặc một field của payload, bên còn lại có thể đọc trạng thái đã thay đổi. Dùng immutable DTO, record có các field bất biến, bản sao phòng vệ cho collections và thiết kế xử lý không mutate input.

### Lỗi 5 — Transformer tạo Message mới nhưng bỏ quên headers

Một transformer trả cả `Message` có thể làm mất `traceId`, `tenantId` hay correlation metadata nếu không chủ động sao chép. Lập hợp đồng header theo từng endpoint; thử nghiệm tình huống split–aggregate và lỗi để phát hiện header bị mất. Không copy tất cả theo thói quen nếu có header nhạy cảm hoặc chỉ hợp lệ ở một chặng.

### Lỗi 6 — Cho rằng metadata tự thực thi nghiệp vụ

Đặt `expirationDate` không đồng nghĩa mọi channel sẽ tự loại message hết hạn; đặt `priority` cũng không làm mọi channel sắp xếp theo độ ưu tiên. Metadata chỉ có hiệu lực khi một endpoint, channel, selector hoặc handler được cấu hình để diễn giải nó.

## 8. Kiểm thử hành vi bất biến và bảo toàn header

Các ví dụ sau dùng Java 17+ và JUnit Jupiter 5, minh họa kiểm thử ở mức API. Chúng độc lập với việc khởi động toàn bộ integration flow.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeadersTest {

    @Test
    void directHeaderMutationIsRejected() {
        Message<String> input = MessageBuilder.withPayload("ORDER-1001")
                .setHeader("tenantId", "shop-a")
                .build();

        assertThrows(UnsupportedOperationException.class,
                () -> input.getHeaders().put("tenantId", "shop-b"));

        assertEquals("shop-a", input.getHeaders().get("tenantId"));
    }

    @Test
    void buildingUpdatedMessageDoesNotModifyOriginal() {
        Message<String> original = MessageBuilder.withPayload("ORDER-1001")
                .setHeader("traceId", "trace-001")
                .build();

        Message<String> updated = MessageBuilder.fromMessage(original)
                .setHeader("route", "orders.fast")
                .build();

        assertNotSame(original, updated);
        assertNull(original.getHeaders().get("route"));
        assertEquals("orders.fast", updated.getHeaders().get("route"));
        assertEquals("trace-001", updated.getHeaders().get("traceId"));
    }

    @Test
    void mutableHeaderValueIsNotDeeplyFrozen() {
        List<String> tags = new ArrayList<>(List.of("urgent"));

        Message<String> input = MessageBuilder.withPayload("ORDER-1001")
                .setHeader("tags", tags)
                .build();

        tags.add("review");

        assertEquals(List.of("urgent", "review"),
                input.getHeaders().get("tags"));
    }

    @Test
    void copyingValueBeforePublishKeepsStableSnapshot() {
        List<String> tags = new ArrayList<>(List.of("urgent"));

        Message<String> input = MessageBuilder.withPayload("ORDER-1001")
                .setHeader("tags", List.copyOf(tags))
                .build();

        tags.add("review");

        assertEquals(List.of("urgent"), input.getHeaders().get("tags"));
    }
}
~~~

Với integration flow thực tế, cần thêm kiểm thử đi qua channel, transformer và router để xác minh metadata được truyền theo cấu hình của **chính endpoint đó**. Tránh viết assertion mong `timestamp` phải khác tuyệt đối giữa hai message tạo gần như đồng thời, vì hai thời điểm có thể trùng đến mili giây.

## 9. Bài thực hành: metadata ổn định trong luồng đơn hàng

Giả sử bạn xây dựng luồng `orders.inbound → orders.validate → orders.route → orders.process → orders.outbound`. Một request đến từ ứng dụng checkout mang payload đơn hàng và headers `tenantId`, `region`, `traceId`.

**Yêu cầu:**

1. Tạo message đầu vào với ba header trên và một payload chứa mã đơn.
2. Sau bước validate, thêm `validated=true` bằng cách tạo message mới; giữ `tenantId` và `traceId` của message trước đó.
3. Router chọn `orders.north` khi `region=north`, còn lại đến `orders.other`.
4. Ở bước chuẩn hóa payload, tạo message mới và bảo đảm `traceId` vẫn tồn tại.
5. Viết ba kiểm tra: sửa `getHeaders().put(...)` phải thất bại; message cũ không có `validated`; message sau normalize vẫn có `traceId`.
6. Thêm tình huống nâng cao: payload hoặc header chứa một collection mutable; chứng minh nguy cơ chia sẻ tham chiếu rồi sửa bằng snapshot bất biến.

**Gợi ý triển khai:**

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder.withPayload(" order-1001 ")
        .setHeader("tenantId", "shop-a")
        .setHeader("region", "north")
        .setHeader("traceId", "trace-001")
        .build();

Message<String> validated = MessageBuilder.fromMessage(input)
        .setHeader("validated", true)
        .build();

Message<String> normalized = MessageBuilder
        .withPayload(validated.getPayload().strip().toUpperCase())
        .copyHeaders(validated.getHeaders())
        .build();
~~~

Câu hỏi tự kiểm tra: **Vì sao `input` không có header `validated`, trong khi `validated` có? Vì sao ID của message không phải khóa thích hợp để gộp các dòng hàng của cùng một đơn? Nếu muốn bỏ `tenantId` khi gửi sang đối tác, bạn sẽ làm ở bước nào và kiểm thử điều gì?**

## 10. Checklist thiết kế khi đưa vào dự án

- Đã xác định header nghiệp vụ nào là bắt buộc, kiểu dữ liệu và nguồn tin cậy của chúng.
- Các handler coi message đầu vào là dữ liệu để đọc; thay đổi bằng builder hoặc cơ chế enrich/filter tương ứng.
- Giá trị header chia sẻ giữa các nhánh được chọn là immutable hoặc được sao chép phòng vệ.
- `id` và `timestamp` do framework quản lý; correlation ID nghiệp vụ được giữ theo hợp đồng riêng.
- Router/filter có đường xử lý khi metadata thiếu hoặc sai kiểu.
- Transformer trả cả `Message` đã chủ động quyết định sao chép headers nào.
- Splitter/Aggregator sử dụng khóa tương quan nhất quán và có chính sách cho nhóm thiếu phần.
- Header điều khiển reply/error không bị loại bỏ ngoài ý muốn.
- Log và tracing tránh lộ header nhạy cảm; quan sát được `traceId` xuyên các chặng cần thiết.
- Kiểm thử cả nhánh thông thường, nhánh lỗi, retry và trường hợp có nhiều consumer.

## 11. Tổng kết

`MessageHeaders` mang metadata giúp các Enterprise Integration Patterns phối hợp mà không buộc mọi component hiểu chi tiết payload. Tính bất biến **của cấu trúc headers** làm một message đã tạo có tập key–value ổn định trước các lời gọi sửa trực tiếp, nhờ vậy việc phân nhánh và truyền message dễ dự đoán hơn. Khi muốn đổi metadata hoặc payload, hãy tạo **message mới** bằng `MessageBuilder` và quy định rõ headers được sao chép.

Tuy nhiên, bản thân các object dùng làm giá trị header/payload có thể mutable. Muốn an toàn khi chạy đồng thời hoặc publish–subscribe, hãy chọn dữ liệu bất biến hoặc snapshot phòng vệ. Đồng thời, hãy phân biệt ID của message instance với correlation key của một giao dịch, và kiểm chứng cơ chế truyền header của từng endpoint (đặc biệt với Transformer và Splitter/Aggregator).

### Tài liệu tham khảo

- Spring Integration Reference — Message, Message Headers, Header Propagation và MessageBuilder: https://docs.spring.io/spring-integration/reference/message.html
- Spring Framework API — MessageHeaders: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html
- Spring Framework API — MessageBuilder: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html

