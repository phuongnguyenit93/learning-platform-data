# Header bị mất, bị sao chép ngoài ý muốn hoặc bổ sung thất bại

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt payload, Spring `Message`, `MessageHeaders` và header native của giao thức.
2. Giải thích vì sao custom header biến mất khi tạo `Message` mới, đổi payload hoặc đi qua function composition.
3. Dùng `MessageBuilder.fromMessage`, `copyHeaders`, `copyHeadersIfAbsent`, `setHeader`, `setHeaderIfAbsent` và `removeHeader` đúng mục đích.
4. Nhận biết các header hệ thống như `id`, `timestamp`, `contentType`, `replyChannel`, `errorChannel` và giới hạn chỉnh sửa/truyền chúng.
5. Chẩn đoán header không được map qua HTTP, Kafka, RabbitMQ hoặc adapter serverless; phân biệt Spring headers với native transport headers.
6. Bổ sung header có kiểm soát bằng function chuyên trách, tránh sao chép credential, header nội bộ hoặc metadata không phù hợp sang ranh giới tin cậy khác.
7. Thiết kế kiểm thử cho ba trường hợp: header được giữ, header bị ghi đè ngoài ý muốn và header enrichment thất bại.
8. Dùng log/trace để xác định chính xác bước làm mất header mà không ghi toàn bộ giá trị nhạy cảm.

## 1. Vì sao header quan trọng trong Spring Cloud Function?

Spring Cloud Function cho phép đóng gói logic nghiệp vụ bằng `Supplier`, `Function` và `Consumer`, tra cứu qua `FunctionCatalog`, composition và chuyển đổi thông điệp. Cùng một function có thể được gọi từ HTTP, sự kiện hoặc môi trường serverless.

Một `Message<T>` của Spring Messaging có hai phần:

- **Payload:** dữ liệu nghiệp vụ, ví dụ `Order`, `String`, JSON hoặc một event.
- **Headers:** metadata đi kèm, ví dụ `businessCorrelationId`, `contentType`, `replyChannel`, `id`, `timestamp` hoặc header do broker cung cấp.

Ví dụ một message:

~~~text
Message<Order>
  payload:
    orderId = 1024
    amount = 250000
  headers:
    businessCorrelationId = flow-72
    contentType = application/json
    id = UUID do Spring quản lý
    timestamp = thời điểm tạo message
~~~

Payload có thể vẫn đúng nhưng header bị mất. Điều này thường làm hỏng các chức năng phụ thuộc metadata:

- Không còn correlation ID để nối log giữa producer và consumer.
- Router không nhận được thông tin chọn function.
- Converter không biết payload được biểu diễn theo content type nào.
- Reply channel hoặc error channel không còn đúng trong luồng nội bộ.
- Consumer không đọc được custom metadata đã được producer gửi.

Header cũng có thể bị **sao chép ngoài ý muốn**. Ví dụ một function copy toàn bộ header của HTTP request sang message Kafka, vô tình mang theo `Authorization`, cookie hoặc header nội bộ. Do đó, chẩn đoán header cần trả lời hai câu hỏi: *header nào phải được giữ?* và *header nào không được đi tiếp?*

~~~mermaid
flowchart LR
    A["HTTP / Broker input"] --> B["Spring Message"]
    B --> C["Function A"]
    C --> D["Message mới"]
    D --> E["Function B / Composition"]
    E --> F["Output / Broker"]
    H["Custom headers"] -. "cần mapping/copy có chủ đích" .-> C
    H -. "kiểm tra sau mỗi boundary" .-> D
    H -. "allowlist trước khi publish" .-> F
~~~

## 2. Phân biệt bốn lớp metadata

Không phải mọi thứ được gọi là “header” đều là cùng một cấu trúc.

| Lớp | Ví dụ | Ai quản lý? |
| --- | --- | --- |
| Spring `MessageHeaders` | `businessCorrelationId`, `contentType`, `id` | Spring Messaging và ứng dụng |
| HTTP headers | `X-Correlation-Id`, `Content-Type`, `Authorization` | HTTP client/server và adapter |
| Broker/native headers | Kafka record headers, RabbitMQ properties/headers | Broker, binder và header mapper |
| Function routing metadata | Definition/routing expression theo cấu hình và phiên bản | Spring Cloud Function/router |

Một HTTP header chỉ đến được `MessageHeaders` nếu adapter hoặc code ứng dụng map nó vào message. Một Spring custom header chỉ đến được Kafka/RabbitMQ nếu binder/header mapper hỗ trợ và cấu hình cho phép truyền. Việc hai lớp cùng chứa một chuỗi tên không có nghĩa framework tự động chuyển giá trị giữa chúng.

### Header name và kiểu dữ liệu

- HTTP header names không phân biệt chữ hoa/chữ thường theo quy tắc HTTP; Spring `MessageHeaders` là map với tên key cụ thể. Khi ứng dụng tự map, hãy dùng một quy ước nhất quán, ví dụ `businessCorrelationId`.
- Broker header có thể chỉ hỗ trợ một số kiểu dữ liệu hoặc biểu diễn dạng byte array; object Java tùy ý không chắc serialize được.
- Header value có thể bị chuyển thành `String`, `byte[]` hoặc kiểu khác khi qua transport. Consumer cần biết hợp đồng kiểu dữ liệu.
- `contentType` ảnh hưởng đến message conversion; sai hoặc mất content type có thể tạo lỗi deserialize dù payload vẫn được gửi.

## 3. MessageHeaders: immutable và các header hệ thống

`MessageHeaders` là cấu trúc map bất biến ở giao diện public. Không thể lấy map từ `message.getHeaders()` rồi sửa trực tiếp:

~~~java
message.getHeaders().put("businessCorrelationId", "flow-72");
~~~

Đoạn trên không phải cách cập nhật header hợp lệ; map headers được bảo vệ khỏi sửa trực tiếp. Hãy tạo message mới bằng `MessageBuilder` hoặc dùng API accessor phù hợp.

### Các header cần nhận diện

| Header | Vai trò | Lưu ý |
| --- | --- | --- |
| `id` | Định danh Spring Message | Do framework quản lý; không tự gán tùy ý |
| `timestamp` | Thời điểm tạo message | Header hệ thống, không dùng làm business timestamp |
| `contentType` | Gợi ý/định dạng nội dung cho converter | Cần nhất quán với payload thực |
| `replyChannel` | Kênh trả lời trong một số luồng Spring Messaging/Integration | Thường là đối tượng nội bộ, không phải metadata để serialize qua broker |
| `errorChannel` | Kênh lỗi nội bộ | Không copy sang transport như một custom string header |
| `businessCorrelationId` | Liên kết workflow do ứng dụng định nghĩa | Cần hợp đồng tạo, validate và truyền rõ |
| `sourceMessageId` | Tham chiếu message nguồn do ứng dụng định nghĩa | Khác `MessageHeaders.ID` của message hiện tại |

`id` và `timestamp` là các header được Spring quản lý và không nên cố ghi đè bằng `setHeader`. Khi tạo message mới, hãy để framework xử lý chúng. Chi tiết việc một API builder giữ hay tạo lại giá trị hệ thống có thể phụ thuộc cách tạo message và phiên bản; **không dùng ID/timestamp làm bằng chứng rằng toàn bộ custom headers đã được bảo toàn**.

## 4. Tạo message mới có thể làm mất header

Đây là nguyên nhân phổ biến nhất:

~~~java
Message<String> input = ...;

Message<String> output = MessageBuilder
        .withPayload(input.getPayload().toUpperCase(java.util.Locale.ROOT))
        .build();
~~~

`MessageBuilder.withPayload(...)` bắt đầu tạo một message mới. Nếu không copy/set headers, custom headers từ `input` không có trong builder.

Ví dụ đầu vào:

~~~text
payload = "hello"
businessCorrelationId = flow-72
tenantTier = standard
~~~

Sau đoạn code trên, output có payload `HELLO` nhưng không có `businessCorrelationId` và `tenantTier`.

### Giữ headers khi thay payload

~~~java
import java.util.Locale;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> transform(Message<String> input) {
    String output = input.getPayload()
            .trim()
            .toUpperCase(Locale.ROOT);

    return MessageBuilder.withPayload(output)
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

`copyHeaders(...)` sao chép các header có thể copy vào builder theo quy tắc của Spring Messaging. Những header hệ thống read-only như `id` và `timestamp` được Spring kiểm soát; không nên dựa vào thao tác copy để tự điều khiển chúng.

### Giữ một tập header được chọn

Trong nhiều ứng dụng, không nên copy tất cả headers. Hãy tạo allowlist:

~~~java
import java.util.Map;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> transformWithAllowedHeaders(Message<String> input) {
    Set<String> allowed = Set.of(
            "businessCorrelationId",
            "tenantTier",
            "contentType");

    Map<String, Object> selected = input.getHeaders().entrySet().stream()
            .filter(entry -> allowed.contains(entry.getKey()))
            .collect(Collectors.toMap(
                    Map.Entry::getKey,
                    Map.Entry::getValue));

    String output = input.getPayload().trim()
            .toUpperCase(Locale.ROOT);

    return MessageBuilder.withPayload(output)
            .copyHeaders(selected)
            .build();
}
~~~

Ví dụ này minh họa **copy theo allowlist**. Hãy xác định rõ có nên truyền `contentType` cũ sau khi payload đã đổi kiểu hay không. Nếu payload output có kiểu/format khác, hãy đặt content type đúng với output.

## 5. MessageBuilder: chọn đúng thao tác

Spring cung cấp các thao tác builder có ngữ nghĩa khác nhau.

| API | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `withPayload(payload)` | Bắt đầu message mới từ payload | Tạo output mới |
| `fromMessage(message)` | Tạo builder từ message hiện có | Giữ payload/headers rồi sửa một số header |
| `setHeader(name, value)` | Đặt hoặc thay giá trị header | Muốn giá trị mới thắng |
| `setHeaderIfAbsent(name, value)` | Chỉ đặt nếu header chưa có | Muốn giữ giá trị nguồn nếu đã tồn tại |
| `copyHeaders(map)` | Copy header vào builder; giá trị copy có thể thay giá trị đã có theo quy tắc API | Muốn source map ghi đè các key trùng |
| `copyHeadersIfAbsent(map)` | Chỉ copy key builder chưa có | Muốn giá trị đã đặt trên builder được ưu tiên |
| `removeHeader(name)` | Xóa một header | Loại metadata không còn phù hợp |
| `removeHeaders(patterns...)` | Xóa các header khớp pattern | Dọn một nhóm header theo quy tắc tên |
| `build()` | Tạo `Message` từ payload và headers đã cấu hình | Kết thúc biến đổi |

### `fromMessage`: thay một header nhưng giữ payload

~~~java
Message<String> enrich(Message<String> input) {
    return MessageBuilder.fromMessage(input)
            .setHeader("processingStage", "validated")
            .build();
}
~~~

Đây là lựa chọn rõ ràng khi payload không đổi và chỉ cần thêm/cập nhật metadata.

### `copyHeaders` có thể ghi đè giá trị

~~~java
import java.util.Map;

Message<String> output = MessageBuilder.withPayload("HELLO")
        .setHeader("businessCorrelationId", "flow-output")
        .copyHeaders(Map.of("businessCorrelationId", "flow-input"))
        .build();
~~~

Khi copy map sau khi đã đặt header cùng tên, giá trị từ map có thể thay giá trị đang có. Nếu muốn giữ `flow-output`, dùng `copyHeadersIfAbsent` hoặc đặt header mới **sau** thao tác copy.

### `copyHeadersIfAbsent` giữ giá trị đã có

~~~java
import java.util.Map;

Message<String> output = MessageBuilder.withPayload("HELLO")
        .setHeader("businessCorrelationId", "flow-output")
        .copyHeadersIfAbsent(Map.of(
                "businessCorrelationId", "flow-input",
                "sourceSystem", "order-api"))
        .build();
~~~

Kết quả mong đợi:

~~~text
businessCorrelationId = flow-output
sourceSystem = order-api
~~~

### `setHeaderIfAbsent` không phải phép merge map

~~~java
Message<String> output = MessageBuilder.fromMessage(input)
        .setHeaderIfAbsent("businessCorrelationId", "generated-flow")
        .build();
~~~

Nếu input đã có `businessCorrelationId`, giá trị cũ được giữ. Nếu không có, builder đặt giá trị mặc định. Hãy kiểm tra xem header rỗng/null được xử lý như thế nào trong hợp đồng của ứng dụng; nếu muốn thay giá trị null/không hợp lệ, hãy validate trước rồi dùng `setHeader`.

### Null và xóa header

Trong API builder, `setHeader(name, null)` có semantics loại bỏ header tương ứng. Để code dễ đọc và ít nhầm, có thể dùng `removeHeader(name)`:

~~~java
Message<String> output = MessageBuilder.fromMessage(input)
        .removeHeader("temporaryRoutingHint")
        .build();
~~~

Không dùng giá trị chuỗi `"null"` để biểu diễn header không tồn tại; đó là một giá trị thật và có thể gây lỗi ở consumer.

## 6. Thêm header bằng một function chuyên trách

Một function enrichment có thể bổ sung metadata mà không gắn nghiệp vụ với HTTP hoặc broker:

~~~java
import java.util.UUID;
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Function<Message<String>, Message<String>> addProcessingMetadata =
        input -> MessageBuilder.fromMessage(input)
                .setHeader("processingStage", "normalized")
                .setHeaderIfAbsent(
                        "businessCorrelationId",
                        UUID.randomUUID().toString())
                .build();
~~~

Function này chỉ sinh correlation ID khi header chưa có. Trong production, hãy xác định rõ ai có quyền cấp ID và có nên tin ID do nguồn ngoài gửi hay không; validate giá trị trước khi dùng.

### Thay payload và enrichment trong cùng function

~~~java
Function<Message<String>, Message<String>> normalizeAndEnrich =
        input -> {
            String output = input.getPayload().trim()
                    .toUpperCase(Locale.ROOT);

            return MessageBuilder.withPayload(output)
                    .copyHeadersIfAbsent(input.getHeaders())
                    .setHeader("processingStage", "normalized")
                    .build();
        };
~~~

Function này:

1. Đọc payload đầu vào.
2. Tạo payload mới.
3. Copy headers nguồn chưa có trong builder.
4. Ghi `processingStage=normalized` để stage hiện tại thắng.

Nếu `contentType` cũ mô tả payload đầu vào nhưng output đổi định dạng, hãy cập nhật content type hoặc bỏ header đó để adapter chọn converter đúng. Giữ mọi header một cách máy móc không phải lúc nào cũng đúng.

## 7. Header trong function composition

Spring Cloud Function hỗ trợ composition, ví dụ:

~~~properties
spring.cloud.function.definition=normalize|addProcessingMetadata|saveResult
~~~

Mỗi function nhận output của bước trước. Với các function làm việc trên `Message`, cần quyết định rõ mỗi bước nhận và trả:

- `Message<T>` nếu cần đọc/ghi metadata.
- `T` nếu chỉ xử lý payload và không cần header.

### Một function trả payload thuần có thể làm mất metadata ở mức hợp đồng

~~~java
Function<Message<String>, String> extractPayload =
        message -> message.getPayload().trim();
~~~

Function này cố ý chỉ trả `String`. Khi bước kế tiếp nhận một payload thuần, nó không thể đọc custom headers từ `Message` đầu vào nếu adapter/framework không còn giữ chúng ở một context riêng.

Nếu các bước sau cần headers, có hai cách:

1. Để các function ở ranh giới đó nhận/trả `Message`.
2. Truyền metadata cần thiết qua một kiểu dữ liệu nghiệp vụ rõ ràng, thay vì dựa vào header ẩn.

### Composition với Message rõ ràng

~~~java
Function<Message<String>, Message<String>> normalize =
        message -> MessageBuilder.withPayload(
                        message.getPayload().trim()
                                .toUpperCase(Locale.ROOT))
                .copyHeaders(message.getHeaders())
                .setHeader("processingStage", "normalized")
                .build();

Function<Message<String>, Message<String>> markReady =
        message -> MessageBuilder.fromMessage(message)
                .setHeader("processingStage", "ready")
                .build();

Function<Message<String>, Message<String>> chain =
        normalize.andThen(markReady);
~~~

Đây là composition Java thuần, giúp nhìn rõ kiểu đầu vào/đầu ra. Với catalog composition, adapter và function invocation wrapper của Spring Cloud Function, cần kiểm tra kiểu function và quy tắc message wrapping theo phiên bản đang dùng. **Không suy ra rằng mọi custom header luôn tự động được bảo toàn qua mọi kiểu composition**, nhất là khi một bước trả payload thuần hoặc chuyển đổi message.

## 8. Phân biệt header nghiệp vụ, header routing và header nội bộ

Không nên copy tất cả header vì chúng có thể phục vụ các mục đích khác nhau.

| Nhóm | Ví dụ | Chính sách |
| --- | --- | --- |
| Nghiệp vụ | `businessCorrelationId`, `eventType`, `tenantTier` | Giữ theo allowlist/hợp đồng |
| Conversion | `contentType`, schema/version metadata | Giữ hoặc cập nhật theo payload |
| Routing | Function definition/routing expression theo cấu hình | Chỉ truyền ở nơi cần routing; validate allowlist |
| Observability | Trace context, baggage, correlation metadata | Để propagator/adapter xử lý; không tự sao chép mù quáng |
| Nội bộ Spring | `replyChannel`, `errorChannel` | Không mặc định serialize/publish qua broker |
| Bảo mật | Authorization, cookie, credential, session | Không copy sang message/broker/log trừ khi có thiết kế bảo mật rõ ràng |
| Broker native | Partition/offset, delivery metadata | Đọc ở adapter; không giả định là custom Spring header có thể gửi ngược lại |

### Vì sao copy all có thể nguy hiểm?

Ví dụ một HTTP request có:

~~~text
Authorization: Bearer <token>
Cookie: SESSION=<session>
X-Correlation-Id: flow-72
X-Tenant-Tier: standard
~~~

Nếu adapter đưa tất cả vào `MessageHeaders` rồi function gọi `copyHeaders(...)` trước khi publish Kafka, token/session có thể bị chuyển sang broker và tồn tại lâu hơn request ban đầu.

Nên chọn:

~~~text
businessCorrelationId
tenantTier
contentType (nếu còn đúng với output)
~~~

Không truyền:

~~~text
Authorization
Cookie
session
replyChannel
errorChannel
~~~

Việc truyền trace context cần tuân theo cơ chế propagation của tracer và binder; không thay thế bằng cách tự copy một chuỗi `traceparent` tùy tiện.

## 9. Header bị mất khi đi qua HTTP

HTTP headers và Spring `MessageHeaders` là hai cấu trúc khác nhau. Một adapter có thể:

- Chuyển một số HTTP headers vào Spring message.
- Chuẩn hóa hoặc đổi tên header.
- Chỉ chuyển các header được allowlist.
- Bỏ header không hỗ trợ hoặc không an toàn.
- Đưa metadata vào một cấu trúc riêng thay vì `MessageHeaders`.

Nếu cần bảo đảm mapping, hãy thực hiện tường minh tại controller/filter/adapter do ứng dụng kiểm soát:

~~~java
import java.util.regex.Pattern;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> toMessage(String body, HttpHeaders httpHeaders) {
    String correlationId =
            httpHeaders.getFirst("X-Correlation-Id");

    MessageBuilder<String> builder = MessageBuilder.withPayload(body);
    if (correlationId != null
            && Pattern.matches("[A-Za-z0-9._-]{1,64}", correlationId)) {
        builder.setHeader("businessCorrelationId", correlationId);
    }

    builder.setHeader("source", "http");
    return builder.build();
}
~~~

Ví dụ này chỉ chuyển một header đã chọn, có kiểm tra chiều dài/ký tự. Tùy API contract, nếu header không hợp lệ có thể trả 400 thay vì bỏ qua; không ghi nguyên văn giá trị sai vào log.

### Chẩn đoán HTTP mapping

1. Kiểm tra request thực tế có gửi header không.
2. Kiểm tra tên header sau khi HTTP framework parse.
3. Kiểm tra controller/filter có map header vào `MessageBuilder` không.
4. Kiểm tra `Message` ngay trước function.
5. Kiểm tra output `Message` sau function.
6. Nếu output đúng nhưng downstream mất, kiểm tra response adapter/HTTP client.

Đừng chỉ nhìn request trong browser/curl rồi kết luận function đã nhận được header.

## 10. Header bị mất khi đi qua Spring Cloud Stream/broker

Spring Cloud Stream tạo abstraction `Message` cho binding, nhưng việc chuyển custom headers xuống broker phụ thuộc binder, header mapper, serialization và cấu hình.

### Các nguyên nhân phổ biến

- Binder hoặc transport không hỗ trợ header mode mong muốn.
- Header mapper chỉ cho phép một số key/type.
- Giá trị custom header không serialize được hoặc có kiểu không được hỗ trợ.
- Header bị đặt vào native headers nhưng consumer đang đọc Spring headers (hoặc ngược lại).
- Producer/consumer dùng tên header hoặc kiểu dữ liệu không thống nhất.
- Message converter thay payload/content type nhưng custom metadata không được map như kỳ vọng.
- Header bị giới hạn kích thước bởi broker hoặc adapter.

### Kafka

Kafka record có native headers dạng key/value byte arrays. Spring Cloud Stream Kafka binder có thể map Spring message headers sang Kafka headers theo cấu hình và mapper của phiên bản. Một header `String` ở producer có thể được biểu diễn thành bytes trong record; consumer cần decode đúng.

Không giả định mọi object Java đều tự serialize. Ưu tiên giá trị đơn giản, có hợp đồng rõ như `String`, số hoặc byte array và xác minh mapper thực tế. Metadata broker như topic, partition, offset là thông tin transport; không coi chúng là custom business headers.

### RabbitMQ

RabbitMQ có AMQP properties/headers. Header type và mapping phụ thuộc client/binder. Kiểu không được hỗ trợ, kích thước lớn hoặc metadata đặc thù có thể gây lỗi chuyển đổi hoặc bị bỏ qua. Kiểm tra message trên broker và message mà consumer nhận, không chỉ message object trước publish.

### Header mode và cấu hình binder

Một số binder có cấu hình header mode/mapper riêng; không có một cấu hình duy nhất áp dụng cho Kafka, RabbitMQ, SQS và mọi binder. Đọc đúng tài liệu binder đang sử dụng và kiểm tra:

- Header mapping mode có bật không?
- Custom header có nằm trong danh sách được map không?
- Có native encoding/decoding không?
- Có giới hạn type/size không?
- Producer và consumer có cùng quy ước key/type không?

Nếu binder có chế độ không truyền headers, payload có thể đến nguyên vẹn trong khi custom headers biến mất. Đây là lỗi mapping/configuration, không phải lỗi `MessageBuilder`.

## 11. Routing header và metadata điều khiển function

Function routing có thể dựa trên definition, routing expression, callback hoặc adapter-specific metadata. Header điều khiển routing cần được phân biệt với header nghiệp vụ:

- Chỉ nhận route nằm trong allowlist.
- Xác định adapter/binder có chuyển đúng header tới router hay không.
- Không copy routing hint sang topic khác nếu consumer đích không được phép dùng nó.
- Không dùng tên route do client gửi làm metric label hoặc log không giới hạn.
- Khi function đã được chọn, có thể loại bỏ routing hint tạm thời nếu downstream không còn cần.

Ví dụ dọn routing hint sau khi đã chọn đích:

~~~java
Message<String> routed = MessageBuilder.fromMessage(input)
        .removeHeader("temporaryRoutingHint")
        .setHeader("processingStage", "routed")
        .build();
~~~

Tên `temporaryRoutingHint` ở đây là custom header do ứng dụng quy ước. Không xóa header hệ thống của Spring hoặc header routing mà framework còn cần trước khi quyết định route đã hoàn tất.

### Lỗi route không đồng nghĩa header bị mất

Nếu router không chọn được function, hãy phân biệt:

1. Header không tồn tại trong message.
2. Header tồn tại nhưng tên/key không đúng hợp đồng.
3. Header tồn tại nhưng value rỗng/sai kiểu/không hợp lệ.
4. Header hợp lệ nhưng function definition không đăng ký trong catalog.
5. Routing expression/callback ném exception.

Log trạng thái key và một reason code hữu hạn để chẩn đoán; không ghi toàn bộ header map hoặc expression do client cung cấp.

## 12. Header enrichment thất bại vì kiểu, null hoặc converter

Không phải lỗi bổ sung header nào cũng do builder. Một số tình huống xuất hiện ở bước chuyển đổi hoặc serialize:

| Triệu chứng | Nguyên nhân |
| --- | --- |
| Header được đặt nhưng mất sau publish | Header mapper bỏ key/type |
| Header thành chuỗi thay vì object | Transport/mapper encode value thành text |
| Header không deserialize được | Consumer mong kiểu khác producer gửi |
| Header không xuất hiện khi value null | Builder hoặc mapper loại bỏ giá trị null |
| Header có nhưng function không đọc được | Key khác tên, sai casing/convention hoặc accessor đọc nhầm lớp |
| Payload conversion lỗi sau enrichment | `contentType` không khớp payload |
| Header không truyền được qua broker | Giá trị quá lớn hoặc kiểu không hỗ trợ |

### Dùng kiểu header đơn giản

Với metadata liên service, ưu tiên:

- String ngắn, có format rõ cho correlation ID/event type.
- Boolean hoặc số nguyên khi hợp đồng transport hỗ trợ.
- Byte array khi cần định dạng nhị phân có version.

Tránh đưa trực tiếp object tùy ý, Spring channel object, `HttpServletRequest`, exception hoặc domain aggregate vào header. Header là metadata nhỏ, không phải nơi chứa payload thứ hai.

### Kiểm tra kiểu trước và sau boundary

Ở producer:

~~~java
Object value = message.getHeaders().get("businessCorrelationId");
log.debug("correlation header present={}, type={}",
        value != null,
        value == null ? "absent" : value.getClass().getSimpleName());
~~~

Ở consumer, thực hiện cùng phép kiểm tra. Chỉ ghi tên kiểu và trạng thái có/không; không log giá trị nếu header có thể chứa dữ liệu nhạy cảm.

Nếu producer có `String` nhưng consumer nhận `byte[]`, mapper đã chuyển kiểu. Hãy decode theo hợp đồng thay vì cast trực tiếp:

~~~java
String correlationId;
if (value instanceof String text) {
    correlationId = text;
}
else if (value instanceof byte[] bytes) {
    correlationId = new String(
            bytes, java.nio.charset.StandardCharsets.UTF_8);
}
else {
    throw new IllegalArgumentException(
            "Unsupported correlation header type");
}
~~~

Ví dụ dùng pattern matching cho `instanceof`, cần Java 16 trở lên; với Java cũ hơn, dùng `instanceof` và cast tường minh.

## 13. Kiểm tra header tại từng ranh giới

Để tìm đúng bước làm mất header, hãy quan sát message tại các điểm:

~~~text
1. HTTP/broker ingress
2. Message sau adapter/converter
3. Đầu vào function A
4. Đầu ra function A
5. Đầu vào function B
6. Message trước publish
7. Native record/header trên broker
8. Message sau consumer adapter
~~~

Tạo một bảng so sánh:

| Ranh giới | businessCorrelationId | contentType | source |
| --- | --- | --- | --- |
| HTTP ingress | Có | text/plain | Chưa có |
| Message đầu vào | Có | text/plain | http |
| Sau normalize | Có | text/plain | http |
| Trước Kafka publish | Có | text/plain | http |
| Sau Kafka consume | Có/không tùy mapper | text/plain/bytes | http |

Nếu header mất lần đầu ở ranh giới 6→7, hãy kiểm tra binder/header mapper. Nếu đã mất ở 3→4, kiểm tra function code. Không thay đổi toàn bộ pipeline trước khi biết boundary nào làm thay đổi dữ liệu.

### Log tên header, không log tất cả giá trị

Có thể ghi:

~~~java
log.debug("message headers present={}",
        message.getHeaders().keySet());
~~~

`keySet()` vẫn có thể tiết lộ tên header nội bộ; dùng ở môi trường debug có kiểm soát. Tránh:

~~~java
log.debug("headers={}", message.getHeaders());
~~~

Vì giá trị có thể chứa token, cookie, PII, reply/error channel hoặc dữ liệu nghiệp vụ. Nếu cần kiểm tra một custom header, log trạng thái có/không hoặc một ID đã validate:

~~~java
boolean hasCorrelationId = message.getHeaders()
        .containsKey("businessCorrelationId");
log.debug("business correlation header present={}", hasCorrelationId);
~~~

## 14. Kiểm thử việc giữ, ghi đè và bổ sung header

### 14.1. Header được giữ khi thay payload

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeaderPropagationTest {

    @Test
    void keepsBusinessHeadersWhenPayloadChanges() {
        Message<String> input = MessageBuilder.withPayload(" hello ")
                .setHeader("businessCorrelationId", "flow-72")
                .setHeader("source", "http")
                .build();

        String transformed = input.getPayload()
                .trim()
                .toUpperCase(Locale.ROOT);

        Message<String> output = MessageBuilder
                .withPayload(transformed)
                .copyHeaders(input.getHeaders())
                .build();

        assertEquals("HELLO", output.getPayload());
        assertEquals("flow-72",
                output.getHeaders().get("businessCorrelationId"));
        assertEquals("http", output.getHeaders().get("source"));
        assertNotNull(output.getHeaders().getId());
    }
}
~~~

Test xác nhận custom headers được copy khi ứng dụng chủ động yêu cầu. Không dùng test này để kết luận ID của input/output phải giống hoặc khác nhau; ID là header hệ thống được framework quản lý.

### 14.2. `copyHeaders` ghi đè, `copyHeadersIfAbsent` giữ giá trị builder

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeaderPrecedenceTest {

    @Test
    void copyHeadersCanReplaceAnExistingValue() {
        Message<String> output = MessageBuilder.withPayload("result")
                .setHeader("businessCorrelationId", "flow-output")
                .copyHeaders(Map.of(
                        "businessCorrelationId", "flow-input"))
                .build();

        assertEquals("flow-input",
                output.getHeaders().get("businessCorrelationId"));
    }

    @Test
    void copyHeadersIfAbsentKeepsTheBuilderValue() {
        Message<String> output = MessageBuilder.withPayload("result")
                .setHeader("businessCorrelationId", "flow-output")
                .copyHeadersIfAbsent(Map.of(
                        "businessCorrelationId", "flow-input",
                        "source", "http"))
                .build();

        assertEquals("flow-output",
                output.getHeaders().get("businessCorrelationId"));
        assertEquals("http", output.getHeaders().get("source"));
    }
}
~~~

Hai test này mô tả precedence của builder. Hãy dùng chúng khi một header “tự đổi giá trị” dù code vẫn gọi `setHeader` đúng tên.

### 14.3. Xóa header tạm thời

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeaderRemovalTest {

    @Test
    void removesTemporaryRoutingHeader() {
        Message<String> input = MessageBuilder.withPayload("hello")
                .setHeader("temporaryRoutingHint", "normalize")
                .build();

        Message<String> output = MessageBuilder.fromMessage(input)
                .removeHeader("temporaryRoutingHint")
                .build();

        assertFalse(output.getHeaders()
                .containsKey("temporaryRoutingHint"));
    }
}
~~~

### 14.4. Kiểm thử header mapping qua binder

Unit test với `MessageBuilder` chỉ kiểm tra logic trong JVM. Nó không xác nhận header được serialize qua Kafka/RabbitMQ. Với Spring Cloud Stream, nên có integration test dùng test binder hoặc broker test phù hợp:

1. Gửi message có custom header đã allowlist.
2. Nhận message ở consumer function.
3. Xác nhận payload và header có đúng kiểu/giá trị.
4. Thử header type không hỗ trợ hoặc header bị loại theo mapper.
5. Kiểm tra header nhạy cảm không xuất hiện ở consumer.

Test binder có thể mô phỏng một số semantics của binding nhưng không thay thế kiểm thử native header mapping với broker thật khi vấn đề nằm ở serialization/transport.

## 15. Checklist chẩn đoán

~~~text
1. Header thuộc HTTP, Spring MessageHeaders hay native broker metadata?
2. Adapter có map header vào Message không?
3. Header name và type có đúng hợp đồng không?
4. MessageHeaders có bị sửa trực tiếp thay vì dùng builder không?
5. Function có tạo Message mới bằng withPayload mà quên copy headers không?
6. Có bước trả payload thuần thay vì Message không?
7. copyHeaders có ghi đè giá trị đã đặt trước đó không?
8. setHeaderIfAbsent có giữ lại giá trị cũ ngoài ý muốn không?
9. setHeader(name, null) hoặc removeHeader có xóa key không?
10. Header có phải id/timestamp/replyChannel/errorChannel không?
11. contentType còn đúng với payload sau conversion không?
12. Binder/header mapper có hỗ trợ key, type, size và header mode không?
13. Native headers có được decode thành Spring MessageHeaders ở consumer không?
14. Header có chứa credential/PII cần loại bỏ trước publish không?
15. Integration test đã đi qua đúng adapter/broker production chưa?
~~~

## 16. Bảng chẩn đoán nhanh

| Triệu chứng | Điểm kiểm tra đầu tiên |
| --- | --- |
| Header có ở ingress, mất sau function | Tìm `withPayload(...).build()` không copy headers |
| Header còn ở function A, mất ở B | Kiểm tra output type của A và input type của B |
| Header còn trước publish, mất sau consume | Kiểm tra binder, native header mapping và serialization |
| Header bị thay bằng giá trị khác | Kiểm tra thứ tự `setHeader`, `copyHeaders`, `copyHeadersIfAbsent` |
| Header không thêm được | Kiểm tra immutable headers, read-only key, null value và tên key |
| Header routing bị bỏ | Kiểm tra adapter mapping và routing contract của phiên bản |
| `contentType` sai | Kiểm tra payload representation và message converter |
| `replyChannel`/`errorChannel` mất qua broker | Xác nhận đó là header nội bộ không được serialize mặc định |
| Header có trong broker dạng bytes | Kiểm tra mapper/decode type tại consumer |
| Header bí mật xuất hiện ở downstream | Kiểm tra copy-all và allowlist trước publish |

## 17. Bài tập thực hành

1. Tạo `Message<String>` có `businessCorrelationId`, `source` và `contentType`. Thay payload bằng `withPayload(...).build()` rồi quan sát header nào còn.
2. Sửa function để giữ một allowlist header bằng `copyHeaders`. Giải thích vì sao không nên copy toàn bộ headers qua broker.
3. Viết hai function `normalize` và `addMetadata`, cả hai nhận/trả `Message<String>`. Ghép bằng `andThen` và xác nhận header được giữ.
4. Thay function đầu tiên bằng `Function<Message<String>, String>`. Giải thích vì sao bước sau không còn đọc trực tiếp custom headers từ payload thuần.
5. Viết test so sánh `copyHeaders` và `copyHeadersIfAbsent` khi cùng một key đã tồn tại.
6. Dùng `setHeaderIfAbsent` để tạo correlation ID mặc định; sau đó thử input đã có ID hợp lệ và ID rỗng.
7. Xóa một routing hint bằng `removeHeader`. Kiểm tra message đầu vào không bị thay đổi.
8. Thử đặt `id` và `timestamp` bằng builder. Giải thích vì sao không nên dùng các header hệ thống làm business metadata.
9. Tạo controller nhận `X-Correlation-Id`, validate và map thành `businessCorrelationId`. Kiểm thử header thiếu, hợp lệ và chứa ký tự xuống dòng.
10. Publish message có custom header qua Kafka/RabbitMQ test environment. Kiểm tra raw native header và message ở consumer.
11. Thay đổi `contentType` sau khi payload được chuyển từ JSON string sang plain text. Quan sát converter ở consumer.
12. Tạo một header chứa token giả. Chứng minh allowlist ngăn token đi từ HTTP message sang broker.
13. Log `message.getHeaders().keySet()` ở các boundary để tìm điểm header biến mất; bảo đảm không log toàn bộ giá trị.
14. Thiết kế runbook cho lỗi “header có trước publish nhưng mất sau consume”, liệt kê binder, mapper, native header và serialization cần kiểm tra.

## Ghi nhớ

- `Message<T>` gồm payload và `MessageHeaders`; payload có thể đúng trong khi custom headers đã mất.
- `MessageHeaders` không sửa trực tiếp được. Dùng `MessageBuilder` để tạo message mới hoặc thay metadata.
- `withPayload(...).build()` không tự bảo đảm custom headers từ message đầu vào được giữ; cần `copyHeaders`, `copyHeadersIfAbsent` hoặc allowlist.
- `copyHeaders` và `copyHeadersIfAbsent` có precedence khác nhau. Thứ tự gọi builder có thể khiến header bị ghi đè ngoài ý muốn.
- `id`/`timestamp` là header hệ thống; `replyChannel`/`errorChannel` thường là metadata nội bộ. Không xem chúng như business headers để truyền qua broker.
- Function composition chỉ giữ metadata khi kiểu và cách biến đổi message được thiết kế đúng. Một bước trả payload thuần có thể làm custom headers không còn trong output contract.
- HTTP headers, Spring `MessageHeaders` và native broker headers là các lớp khác nhau; cần mapping, serialization và decoding phù hợp.
- `contentType` phải mô tả payload hiện tại. Copy header cũ sau khi đổi representation có thể làm converter lỗi.
- Copy headers theo allowlist trước ranh giới tin cậy; tránh phát tán Authorization, cookie, credential, PII và header nội bộ.
- Kiểm tra header ở từng boundary bằng test; unit test builder không thay thế integration test qua binder/broker thật.

### Tài liệu tham khảo chính thức

- [Spring Framework — Message Abstraction](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Framework Javadoc — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework Javadoc — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework Javadoc — MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Cloud Function — Programming Model và Function Composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Function Routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/routing.html)
- [Spring Cloud Stream — Message Conversion](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-message-handling.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
