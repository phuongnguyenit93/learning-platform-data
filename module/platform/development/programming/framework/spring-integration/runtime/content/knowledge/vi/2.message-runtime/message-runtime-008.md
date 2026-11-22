# Header propagation và header mapping

Trong Spring Integration, header là lớp metadata đi cùng payload để các endpoint phối hợp xử lý message. Header có thể chứa correlation ID, reply channel, error channel, content type, thông tin tenant, trace ID hoặc thuộc tính do adapter lấy từ giao thức bên ngoài.

Hai cơ chế thường bị nhầm lẫn là **header propagation** và **header mapping**:

- **Header propagation** là cách các message-producing endpoint giữ và chuyển tiếp header khi message đi qua các bước bên trong ứng dụng Spring Integration.
- **Header mapping** là cách adapter chuyển đổi giữa `MessageHeaders` của Spring và header/property của giao thức bên ngoài như HTTP, AMQP, JMS hoặc Kafka.

Nắm rõ hai cơ chế này giúp tránh mất metadata khi transform payload, tránh gửi nhầm header nội bộ ra ngoài, và giữ được thông tin cần thiết để correlation, request-reply, tracing và xử lý lỗi hoạt động đúng.

## 1. Header nằm ở đâu trong Message?

Một Spring message có hai thành phần:

- `payload`: dữ liệu nghiệp vụ mà consumer xử lý, ví dụ `Order`, JSON hoặc byte array.
- `headers`: metadata dạng cặp tên/giá trị, mô tả message và cách runtime hoặc adapter xử lý nó.

`MessageHeaders` triển khai `Map<String, Object>` nhưng bản thân map là read-only. Không thể gọi `put`, `remove` hoặc `clear` để thay đổi cấu trúc header sau khi message đã được tạo. Payload cũng không thể được thay thế trực tiếp trên message hiện có. Muốn thay đổi payload hoặc header, cần tạo message mới bằng `MessageBuilder` hoặc API tương ứng.

Một số header phổ biến:

| Header | Ý nghĩa |
|---|---|
| `id` | UUID nhận diện một message instance; framework quản lý |
| `timestamp` | Thời điểm tạo message; framework quản lý |
| `correlationId` | Khóa liên hệ các message cùng một công việc hoặc một nhóm |
| `sequenceNumber` | Vị trí của message trong sequence |
| `sequenceSize` | Số message dự kiến trong sequence |
| `replyChannel` | Nơi nhận reply khi flow dùng request-reply |
| `errorChannel` | Nơi nhận lỗi của message |
| `contentType` | Kiểu nội dung của payload, hữu ích khi chuyển đổi dữ liệu |
| `priority` | Mức ưu tiên, được một số channel như `PriorityChannel` sử dụng |

Spring Integration có các hằng số header trong `MessageHeaders`, `IntegrationMessageHeaderAccessor` và các lớp riêng theo adapter như `AmqpHeaders`, `JmsHeaders` hoặc `KafkaHeaders`. Dùng hằng số thay cho chuỗi tự gõ giúp tránh sai tên và làm rõ header thuộc framework hay giao thức nào.

`id` và `timestamp` là read-only. Khi message được tạo mới hoặc biến đổi, framework thường cấp ID và timestamp mới. Không dùng `id` làm mã đơn hàng hoặc mã nghiệp vụ cần ổn định xuyên nhiều lần gửi. Nếu cần định danh xuyên hệ thống, hãy tạo header riêng như `app.messageKey` hoặc `app.orderId`.

### Header map read-only không có nghĩa mọi giá trị đều bất biến

Map header không cho phép thay đổi cấu trúc, nhưng một giá trị được lưu trong header vẫn có thể là object mutable. Nếu cùng message được nhiều subscriber đọc, một object mutable được chia sẻ có thể bị sửa bởi consumer này và ảnh hưởng consumer khác.

Ưu tiên giá trị metadata bất biến và gọn nhẹ như `String`, `UUID`, `Long`, `Integer`, `Boolean`, `Instant` hoặc enum. Tránh đưa object chứa session, connection, entity quản lý bởi ORM hay cấu trúc mutable lớn vào header nếu không có lý do rõ ràng.

## 2. Header propagation bên trong message flow

Khi message đi qua một `MessageChannel`, channel chuyển tiếp message đến consumer. Nếu không có endpoint nào tạo message mới hoặc thay đổi metadata, các header vẫn nằm trên message đó.

Khi một endpoint xử lý message và phát message đầu ra, Spring Integration nhìn chung truyền các header đầu vào sang message đầu ra. Việc truyền này có một số quy tắc quan trọng:

1. Header đầu vào được sao chép sang message đầu ra nếu header đó chưa có ở message đầu ra.
2. Header mà handler chủ động đặt trên message đầu ra được giữ nguyên; giá trị đầu vào không ghi đè giá trị đã có.
3. Nếu transformer chỉ trả về payload mới, framework truyền tiếp header đầu vào.
4. Nếu transformer trả về một `Message` hoàn chỉnh, code của transformer chịu trách nhiệm tạo cả payload lẫn tập header mong muốn.
5. Một số endpoint có thể được cấu hình để bỏ qua một số header khi tạo message đầu ra.

Quy tắc này cho phép một bước xử lý thay đổi metadata mà không làm mất toàn bộ ngữ cảnh của request. Ví dụ, service activator có thể thêm `app.processedBy`, còn `correlationId` và `replyChannel` tiếp tục được giữ nếu không bị thay thế hoặc lọc bỏ.

### Transformer trả payload và transformer trả Message

Hai kiểu trả về sau có ý nghĩa khác nhau.

~~~java
// Trả payload mới: framework truyền tiếp các header đầu vào.
Order normalize(Order order) {
    return order.normalized();
}
~~~

~~~java
// Trả Message hoàn chỉnh: code phải chủ động quyết định header nào cần giữ.
Message<Order> normalize(Message<Order> input) {
    return MessageBuilder.withPayload(input.getPayload().normalized())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

Trong ví dụ thứ hai, `copyHeaders()` sao chép header từ message đầu vào sang message mới. `id` và `timestamp` là header read-only nên không được ghi đè theo cách thông thường; message mới có metadata nhận diện riêng. Nếu không cần giữ mọi header, hãy chọn lọc header cần thiết thay vì sao chép toàn bộ.

Điểm cần nhớ là trả về một `Message` hoàn chỉnh đồng nghĩa với việc code ứng dụng kiểm soát rõ ràng ngữ cảnh của message đầu ra. Nếu quên copy `correlationId`, `replyChannel` hoặc header định tuyến cần thiết, flow có thể vẫn chạy nhưng mất khả năng tương quan hoặc trả kết quả về đúng nơi.

## 3. Tạo và sao chép header bằng MessageBuilder

`MessageBuilder` là API thông dụng để tạo message mới từ payload hoặc từ message có sẵn. Các thao tác quan trọng:

| API | Hành vi |
|---|---|
| `MessageBuilder.fromMessage(message)` | Tạo builder từ message hiện có, giữ payload và header có thể sao chép |
| `MessageBuilder.withPayload(payload)` | Tạo builder với payload mới |
| `setHeader(name, value)` | Đặt hoặc thay giá trị header |
| `setHeaderIfAbsent(name, value)` | Chỉ đặt header nếu chưa có |
| `copyHeaders(map)` | Sao chép các header; giá trị trùng tên có thể bị ghi đè |
| `copyHeadersIfAbsent(map)` | Chỉ sao chép header mà builder chưa có |
| `removeHeader(name)` | Loại bỏ header khỏi message mới |
| `build()` | Tạo message từ builder |

Ví dụ thay payload nhưng vẫn giữ metadata, đồng thời đặt một header nguồn do bước hiện tại chịu trách nhiệm:

~~~java
Message<Order> toNextStep(Message<Order> input) {
    return MessageBuilder.withPayload(input.getPayload().normalized())
            .setHeader("app.source", "orders-flow")
            .copyHeadersIfAbsent(input.getHeaders())
            .build();
}
~~~

Ở đây `app.source` được đặt trước. `copyHeadersIfAbsent()` chỉ bổ sung các header còn thiếu nên không ghi đè giá trị `app.source` do bước hiện tại đặt. Những header khác như `correlationId` được giữ nếu có ở message đầu vào.

Nếu muốn ưu tiên giá trị từ message gốc, hãy sao chép trước rồi mới gọi `setHeader()`:

~~~java
Message<Order> toNextStep(Message<Order> input) {
    return MessageBuilder.withPayload(input.getPayload().normalized())
            .copyHeaders(input.getHeaders())
            .setHeader("app.source", "normalizer")
            .build();
}
~~~

Không sửa trực tiếp map trả về từ `message.getHeaders()`. Cách đó vi phạm hợp đồng read-only và có thể ném `UnsupportedOperationException`.

## 4. Bổ sung metadata bằng Header Enricher

Khi mục tiêu chỉ là thêm hoặc cập nhật metadata, không cần viết transformer chỉ để tạo message mới. Spring Integration cung cấp **Header Enricher**.

Header Enricher có thể đặt giá trị tĩnh, tham chiếu bean hoặc tính giá trị từ payload/header bằng expression. Java DSL hỗ trợ `.enrichHeaders(...)`.

~~~java
@Bean
IntegrationFlow enrichOrderHeaders() {
    return IntegrationFlow.from("orders.input")
            .enrichHeaders(headers -> headers
                    .header("app.source", "orders-api")
                    .headerExpression("app.region", "payload.region")
                    .headerExpression("app.receivedAt", "T(java.time.Instant).now()"))
            .channel("orders.normalized")
            .get();
}
~~~

Trong ví dụ:

- `app.source` đánh dấu nguồn tiếp nhận.
- `app.region` lấy thông tin vùng từ payload.
- `app.receivedAt` ghi thời điểm flow nhận message.

Header Enricher cũng có thể đặt các header framework có ý nghĩa đặc biệt như `replyChannel`, `errorChannel`, `correlationId` hoặc `priority`. Những header này ảnh hưởng trực tiếp đến cách message được định tuyến hoặc quản lý, vì vậy cần đặt đúng kiểu dữ liệu và đúng thời điểm.

Không nên tùy tiện thay `correlationId` ở giữa flow. Nếu một splitter đã tạo nhiều message thuộc cùng nhóm, đổi correlation ID có thể khiến aggregator không gom được các message đó.

## 5. Loại bỏ header bằng Header Filter

Một số header chỉ cần thiết trong một đoạn flow. Trước khi gửi message ra adapter hoặc sang một ranh giới tin cậy khác, hãy loại bỏ chúng bằng **Header Filter**.

Java DSL:

~~~java
@Bean
IntegrationFlow publishOrder() {
    return IntegrationFlow.from("orders.ready")
            .headerFilter("app.internalToken", "app.debugContext", "replyChannel")
            .channel("orders.external")
            .get();
}
~~~

Header Filter tạo message đầu ra không chứa các header được chỉ định. Nó hữu ích khi:

- Header chỉ phục vụ một endpoint nội bộ.
- Header chứa dữ liệu nhạy cảm không được gửi sang hệ thống khác.
- Một header từ inbound request có thể gây xung đột với metadata của outbound adapter.
- Không muốn header tạm thời xuất hiện trong message được lưu hoặc gửi đi.

Cần kiểm tra tác động trước khi lọc `replyChannel`, `errorChannel`, `correlationId` hoặc các header sequence. Nếu gateway hoặc endpoint phía sau vẫn cần chúng để trả reply, gửi lỗi hay gom nhóm, việc loại bỏ có thể làm hỏng semantics của flow.

## 6. Kiểm soát header được propagation

Trong trường hợp một endpoint tạo message đầu ra nhưng không muốn chuyển một số header từ đầu vào, Spring Integration hỗ trợ cấu hình danh sách header không được propagation.

`MessageProducingMessageHandler` cung cấp `setNotPropagatedHeaders()` và `addNotPropagatedHeaders()`. Java DSL cũng cung cấp tùy chọn `notPropagatedHeaders()` trên cấu hình endpoint; XML có thuộc tính `not-propagated-headers` cho service activator.

Ví dụ XML:

~~~xml
<int:service-activator
        input-channel="orders.input"
        ref="orderService"
        method="process"
        output-channel="orders.output"
        not-propagated-headers="app.secret*, app.internalContext"/>
~~~

Các pattern đơn giản có thể lọc theo tên header, ví dụ tiền tố hoặc hậu tố. Dùng `*` để chặn toàn bộ propagation sẽ khiến handler phải tự tạo mọi header cần thiết trên message đầu ra.

Có thể cấu hình danh sách header read-only toàn cục qua thuộc tính `readOnlyHeaders` trong `META-INF/spring.integration.properties` để kiểm soát hành vi sao chép của message builder mặc định. Đây là thiết lập ở phạm vi rộng; chỉ nên dùng khi chính sách áp dụng thực sự thống nhất cho toàn ứng dụng.

Lưu ý: cơ chế suppression dành cho endpoint tạo message mới. Nó không có tác dụng tương tự trên các endpoint không sửa message như bridge hoặc router, vì những endpoint đó không tạo message đầu ra theo cùng cơ chế.

## 7. Header mapping tại ranh giới adapter

Header propagation hoạt động trong mô hình message nội bộ. Khi message đi qua HTTP, AMQP, JMS hoặc Kafka, adapter phải chuyển đổi giữa hai mô hình metadata.

Đó là nhiệm vụ của **HeaderMapper**.

Có thể mô tả hai chiều như sau:

~~~mermaid
flowchart LR
    A["HTTP / AMQP / JMS / Kafka headers"] -->|"Inbound mapper"| B["Spring MessageHeaders"]
    B --> C["Message flow nội bộ"]
    C --> D["Spring MessageHeaders"]
    D -->|"Outbound mapper"| E["HTTP / AMQP / JMS / Kafka headers"]
~~~

Ở chiều inbound, mapper đọc header/property của giao thức và tạo các entry tương ứng trong `MessageHeaders`. Ở chiều outbound, mapper chọn các header của Spring message và ghi chúng vào đối tượng request/message của giao thức.

Với request-reply, một số mapper còn phân biệt tập header của request và tập header của reply. API `RequestReplyHeaderMapper` thể hiện điều này qua các thao tác:

- `toHeadersFromRequest(...)`: đọc header từ request bên ngoài thành map header Spring.
- `fromHeadersToRequest(...)`: ghi header Spring lên request bên ngoài.
- `toHeadersFromReply(...)`: đọc header từ reply bên ngoài.
- `fromHeadersToReply(...)`: ghi header Spring lên reply bên ngoài.

Không phải mọi mapper đều implement `RequestReplyHeaderMapper`. Kafka có strategy `KafkaHeaderMapper` riêng với các thao tác `fromHeaders(...)` và `toHeaders(...)`; vì vậy cần xem interface mà adapter cụ thể sử dụng thay vì giả định mọi giao thức có cùng API.

Các adapter thường đã cấu hình mapper mặc định theo giao thức. Khi cần kiểm soát rõ header nào được truyền, có thể cấu hình mapper riêng hoặc dùng các thuộc tính mapped header của adapter.

Header mapping không đồng nghĩa với payload conversion. Message converter hoặc transformer chuyển đổi body/payload; header mapper chuyển đổi metadata. Hai cơ chế có thể chạy trong cùng adapter nhưng giải quyết hai phần khác nhau của message.

## 8. Mapping HTTP headers

HTTP adapter và gateway sử dụng `DefaultHttpHeaderMapper` để ánh xạ HTTP request/response headers với Spring `MessageHeaders`.

Theo cấu hình mặc định, các HTTP standard headers được hỗ trợ mapping. Khi cần tùy chỉnh, có thể khai báo danh sách header hoặc wildcard. Khi cung cấp danh sách riêng, danh sách đó thay thế hành vi mặc định; nếu vẫn cần toàn bộ standard headers, dùng các pattern `HTTP_REQUEST_HEADERS` hoặc `HTTP_RESPONSE_HEADERS`.

Ví dụ outbound HTTP gateway:

~~~xml
<int-http:outbound-gateway
        id="partnerGateway"
        url="https://partner.example/orders"
        mapped-request-headers="HTTP_REQUEST_HEADERS, X-Trace-Id, X-Tenant-Id"
        mapped-response-headers="HTTP_RESPONSE_HEADERS, X-Partner-Request-Id"
        channel="partner.requests"/>
~~~

Trong ví dụ, gateway gửi các HTTP request headers chuẩn cùng hai metadata header được chọn; response mapping nhận các response headers chuẩn và request ID riêng của đối tác.

Có thể cấu hình `DefaultHttpHeaderMapper` độc lập rồi gắn mapper vào adapter bằng thuộc tính `header-mapper`. Việc chọn pattern phải dựa trên chiều mapping: request đi ra và response đi vào có thể cần hai tập header khác nhau.

Không giả định mọi `MessageHeaders` đều là HTTP header hợp lệ. HTTP header có quy tắc về tên và biểu diễn giá trị; object tùy ý trong Spring message có thể không thể chuyển thành header HTTP. Hãy chuyển metadata phức tạp thành chuỗi hoặc định dạng phù hợp trước khi mapping.

## 9. Mapping AMQP, JMS và Kafka

Các giao thức có mô hình header khác nhau. Cùng một header Spring có thể được biểu diễn bằng property chuẩn, user-defined property, byte array hoặc kiểu dữ liệu đã serialize tùy giao thức.

| Giao thức | Mapper thường gặp | Điểm cần chú ý |
|---|---|---|
| AMQP/RabbitMQ | `DefaultAmqpHeaderMapper` | Map các AMQP properties và user-defined headers theo rule của phiên bản; một số header `x-*` được xử lý đặc biệt để tránh gửi ngược metadata nhận vào |
| JMS | `DefaultJmsHeaderMapper` | Ánh xạ JMS standard properties và user properties; tên và kiểu giá trị phải tuân theo giới hạn của JMS |
| Kafka | `DefaultKafkaHeaderMapper` hoặc `JsonKafkaHeaderMapper` tùy phiên bản Spring Kafka; `SimpleKafkaHeaderMapper` cho mapping raw | Kafka native header có key và value dạng byte array; mapper JSON chuyển header object và metadata kiểu |

### AMQP

Các header chuẩn thường được biểu diễn bằng tên riêng như `amqp_correlationId`, `amqp_messageId`, `amqp_replyTo` và `contentType`. Dùng `AmqpHeaders` constants để tham chiếu các header adapter cung cấp.

Với user-defined headers, `DefaultAmqpHeaderMapper` hỗ trợ danh sách tên và pattern. Các pattern phủ rộng có thể khiến metadata nhận từ broker bị gửi ngược trở lại broker hoặc reply. Một số header `x-*` được loại khỏi mapping mặc định theo chiều nhất định; hành vi chính xác phụ thuộc phiên bản Spring Integration và cấu hình mapper.

Nếu cần chỉ gửi một tập metadata, hãy khai báo allow-list. Khi dùng wildcard, kiểm tra kỹ header nào đang đi vào từ broker và header nào được phép xuất hiện trên message gửi ra.

### JMS

JMS phân biệt các standard message properties với user properties. Mapper chuyển các thuộc tính JMS sang tên header Spring tương ứng. User properties của JMS có giới hạn về kiểu dữ liệu và tên hợp lệ; không thể giả định một object Java tùy ý trong `MessageHeaders` sẽ được gửi như một JMS property.

Khi tích hợp request-reply, cần hiểu cách `JMSCorrelationID`, `JMSReplyTo` và các header Spring tương ứng được ánh xạ. Nếu hai hệ thống dùng quy ước correlation khác nhau, hãy map rõ ràng thay vì dựa vào tên header trùng nhau một cách ngẫu nhiên.

### Kafka

Kafka native headers lưu value dưới dạng `byte[]`. Mapper JSON có tên `DefaultKafkaHeaderMapper` trong nhiều phiên bản Spring Kafka được Spring Integration sử dụng; tài liệu Spring Kafka mới hơn dùng tên `JsonKafkaHeaderMapper`. Mapper này có thể dùng Jackson để chuyển các kiểu header phong phú sang JSON. Metadata kiểu được ghi trong header đặc biệt `spring_json_header_types` để phía nhận có thể khôi phục kiểu phù hợp. `SimpleKafkaHeaderMapper` giữ header ở dạng raw `byte[]` và có thể cấu hình chuyển một số header thành chuỗi.

Không phải ứng dụng hoặc ngôn ngữ nào cũng hiểu metadata kiểu của Spring Kafka. Nếu producer và consumer khác công nghệ, ưu tiên header có hợp đồng đơn giản, chẳng hạn chuỗi UTF-8 hoặc số được biểu diễn theo quy ước chung.

Mapper hỗ trợ pattern để giới hạn header outbound. `id` và `timestamp` thường không nên gửi như header ứng dụng; đây là metadata nhận diện message của Spring và được framework quản lý. Khi cấu hình pattern riêng, hãy kiểm tra thứ tự include/exclude và quy tắc trusted type của mapper trước khi giải mã object từ nguồn không tin cậy. Với JSON mapper hiện hành, mặc định chỉ một số package phổ biến được tin cậy; nếu cần kiểu ứng dụng, hãy đăng ký đúng package cần thiết bằng `addTrustedPackages()`. Tránh tin cậy mọi package (`*`) khi nhận message từ nguồn không tin cậy, vì mapper có thể tạo object từ kiểu được mô tả trong metadata header.

## 10. replyChannel và errorChannel khi qua ranh giới serialization

`replyChannel` và `errorChannel` có thể chứa một `MessageChannel` object hoặc một tên channel dạng `String`.

Khi message chỉ đi qua các endpoint trong cùng application context, việc giữ tham chiếu channel có thể hoạt động bình thường. Nhưng nếu message được serialize vào message store hoặc gửi qua broker, object tham chiếu đến channel không thể được chuyển nguyên vẹn sang tiến trình khác.

Spring Integration cung cấp `HeaderChannelRegistry` và `DefaultHeaderChannelRegistry` để giải quyết trường hợp này. Registry chuyển tham chiếu channel thành một chuỗi định danh và giữ ánh xạ để có thể tìm lại channel khi reply hoặc error quay về. Header enricher có hỗ trợ `header-channels-to-string` trong XML; cơ chế tương đương có thể được thực hiện bằng expression gọi registry.

Registry có thời hạn lưu mapping. Giá trị mặc định được tài liệu Spring Integration mô tả là 60 giây; có thể cấu hình TTL/reaper phù hợp với thời gian tối đa mà reply có thể quay lại. Nếu mapping hết hạn trước khi reply đến, runtime không còn tìm được channel ban đầu.

Đối với giao tiếp giữa nhiều ứng dụng độc lập, không nên gửi một object `MessageChannel` nội bộ qua mạng và kỳ vọng tiến trình khác sử dụng được. Hãy dùng địa chỉ reply hoặc routing key mà hệ thống ngoài hiểu được, sau đó để adapter/gateway ánh xạ về channel nội bộ của ứng dụng nhận.

## 11. Header propagation không truyền ThreadLocal

Header nằm trong message nên có thể đi cùng message khi nó được gửi qua `ExecutorChannel`, queue hoặc endpoint khác. Nhưng các giá trị gắn với thread hiện tại không tự động trở thành message header.

Ví dụ:

- MDC của logging framework có thể biến mất khi handler chạy trên executor thread khác.
- `ThreadLocal` do ứng dụng tự quản lý không tự truyền theo message.
- Security context hoặc transaction context không tự được chuyển chỉ vì message có `correlationId`.
- Trace context cần cơ chế instrumentation/context propagation phù hợp, hoặc được biểu diễn và trích xuất qua các header trace chuẩn.

Nếu cần trace xuyên qua bất đồng bộ, hãy dùng Micrometer Observation/Tracing hoặc cơ chế context propagation tương ứng với stack của ứng dụng. Header trace có thể mang thông tin cần thiết, nhưng việc đặt header đơn thuần không đảm bảo MDC, security hoặc transaction context được phục hồi trên thread khác.

## 12. Serialization, persistence và tính tương thích

Khi message được lưu vào `MessageStore`, `QueueChannel` có store bền vững hoặc được chuyển qua broker, header phải phù hợp với cơ chế serialization và schema của đích.

Một header object có thể dùng tốt trong JVM nhưng không serialize được. Một class header tự định nghĩa có thể không tồn tại hoặc không tương thích phiên bản ở consumer khác. Vì vậy:

- Ưu tiên metadata dạng primitive, chuỗi, UUID, thời gian chuẩn hoặc cấu trúc có schema ổn định.
- Tránh đưa object runtime như `MessageChannel`, `ApplicationContext`, `Connection`, `Session` hoặc bean vào message header cần persistence.
- Với object phức tạp, định nghĩa cách serialize/deserialize và kiểm soát version schema.
- Đặt kích thước giới hạn cho header; metadata lớn làm tăng kích thước message, chi phí broker và thời gian serialize.
- Không dựa vào Java class name để trao đổi hợp đồng metadata giữa các ngôn ngữ hoặc dịch vụ độc lập.

Một message có thể serialize thành công nhưng vẫn không tương thích về ngữ nghĩa. Ví dụ, producer gửi `app.priority` dưới dạng chuỗi `"5"` trong khi consumer mong `Integer`; consumer có thể không parse được hoặc xử lý khác dự kiến. Hợp đồng header cần định nghĩa cả tên, kiểu, đơn vị, giá trị hợp lệ và ý nghĩa.

## 13. Bảo mật và ranh giới tin cậy

Header thường được dùng để điều khiển routing, tenant, retry, correlation hoặc quyền truy cập. Vì vậy, header nhận từ bên ngoài phải được xem là dữ liệu đầu vào chưa đáng tin cậy.

Một số nguyên tắc thực tế:

1. Chỉ map các header cần thiết bằng allow-list; tránh đưa toàn bộ header ngoài vào flow nếu không có mục đích.
2. Không forward `Authorization`, cookie, token hoặc dữ liệu cá nhân sang hệ thống khác nếu hợp đồng tích hợp không yêu cầu.
3. Không tin `tenantId`, `role`, `userId` hoặc `securityContext` do caller tự gửi. Xác thực và gắn metadata tin cậy tại biên ứng dụng.
4. Dùng namespace cho header nội bộ như `app.*` để tránh trùng tên với header framework hoặc adapter.
5. Xóa header nội bộ trước khi gửi qua adapter bằng Header Filter hoặc quy tắc mapper.
6. Không ghi toàn bộ headers vào log ở production. Redact token, cookie, dữ liệu định danh và thông tin nhạy cảm.

Header `correlationId` dùng để liên kết message, không phải bằng chứng xác thực. Tương tự, `replyChannel` và `errorChannel` có thể ảnh hưởng đến đường đi message; không để dữ liệu không tin cậy điều khiển channel nội bộ nếu không có kiểm soát.

## 14. Chẩn đoán khi header bị mất hoặc sai

Khi một downstream endpoint không nhận được metadata mong đợi, hãy xác định header biến mất ở ranh giới nào.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Header mất sau transformer | Transformer trả về `Message` hoàn chỉnh nhưng không copy header | Kiểm tra kiểu trả về; dùng payload return hoặc copy header có chọn lọc |
| Header cũ ghi đè giá trị mới | Thứ tự `copyHeaders()` và `setHeader()` không phù hợp | Dùng `copyHeadersIfAbsent()` hoặc đặt giá trị mới sau khi copy |
| Header nội bộ không xuất hiện ở broker | Outbound mapper không cho phép tên đó hoặc kiểu giá trị không hợp lệ | Kiểm tra allow-list, pattern và log mapping |
| Header từ broker không vào message | Inbound mapper loại tên đó hoặc converter không chuyển đổi được | Kiểm tra mapper, protocol properties và kiểu dữ liệu native |
| Reply không quay về gateway | `replyChannel` bị lọc, không serialize được hoặc registry mapping đã hết hạn | Kiểm tra header, HeaderChannelRegistry và TTL |
| Aggregator không gom được message | `correlationId` bị đổi hoặc mất trong flow | So sánh correlation key trên từng message và sequence headers |
| HTTP request thiếu metadata | Header pattern không khớp hoặc custom list đã thay default | Kiểm tra `mapped-request-headers` và `HTTP_REQUEST_HEADERS` |
| Trace ID mất khi chuyển executor | Chỉ dựa vào MDC/ThreadLocal | Kiểm tra tracing instrumentation/context propagation và message headers |

Một cách debug hiệu quả là ghi nhận danh sách tên header và kiểu dữ liệu tại các ranh giới quan trọng: sau inbound adapter, sau enricher/transformer, trước outbound adapter và sau inbound reply. Không log giá trị nhạy cảm. Dùng cùng một `correlationId` để nối các bản ghi.

### Kiểm thử mapping

Nên kiểm thử ít nhất bốn điều:

- Header cần thiết có mặt sau khi đi qua các endpoint nội bộ.
- Header đã được thay thế có giá trị mới như mong đợi.
- Header bị cấm không xuất hiện trên outbound native message.
- Header inbound được chuyển thành đúng tên và kiểu trong `MessageHeaders`.

Với adapter thật, kiểm thử integration nên xác nhận cả hai chiều inbound/outbound trên giao thức đích. Unit test chỉ kiểm tra `MessageBuilder` không đủ để chứng minh mapper và converter của adapter đang hoạt động đúng.

## 15. Ví dụ thiết kế metadata xuyên flow

Giả sử một API nhận đơn hàng, thêm trace và tenant metadata, chuẩn hóa payload rồi gửi sang HTTP partner. Thiết kế nên chia metadata theo nơi sở hữu:

- API gateway xác thực caller và tạo `app.tenantId` đáng tin cậy.
- Inbound adapter hoặc tracing instrumentation tạo trace context.
- Header Enricher bổ sung `app.source` và thời điểm nhận.
- Transformer thay payload nhưng giữ các header cần thiết.
- Outbound HTTP mapper chỉ chuyển các header đã được cho phép như `X-Trace-Id` và `X-Tenant-Id`.
- Header Filter xóa token nội bộ hoặc thông tin chỉ dùng trong JVM trước khi gửi ra ngoài.

~~~java
@Bean
IntegrationFlow partnerOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders.in")
            .enrichHeaders(h -> h
                    .header("app.source", "order-api")
                    .headerExpression("app.receivedAt", "T(java.time.Instant).now()"))
            .transform(Order.class, orderService::normalize)
            .headerFilter("app.internalToken", "app.debugContext")
            .channel("partner.http.requests")
            .get();
}
~~~

Trong flow này, transformer trả về payload `Order` đã chuẩn hóa. Theo quy tắc propagation, header đầu vào được chuyển tiếp sang message đầu ra nếu chưa có giá trị tương ứng. Trước khi message đến HTTP adapter, Header Filter loại bỏ metadata nội bộ không được phép phát ra ngoài. Mapper của HTTP adapter sau đó chỉ chuyển các header được cấu hình sang HTTP request.

Khi triển khai thực tế, cần bảo đảm HTTP adapter được cấu hình mapped request headers tương ứng. Việc có `app.tenantId` trong `MessageHeaders` không tự động có nghĩa HTTP request sẽ có `X-Tenant-Id`; cần một quy tắc mapping rõ ràng hoặc mapper tùy chỉnh để chuyển tên và giá trị.

## 16. Checklist thiết kế header

Trước khi đưa một flow vào vận hành, hãy kiểm tra:

- Mỗi header có mục đích rõ ràng và có một thành phần chịu trách nhiệm tạo giá trị không?
- Header nào là metadata của framework, header nào là metadata nghiệp vụ?
- Transformer nào trả payload và transformer nào trả message hoàn chỉnh?
- Khi tạo message mới, code có giữ đúng correlation, reply/error và routing headers không?
- Header nào được phép propagation qua service activator hoặc handler?
- Header nào phải bị lọc trước khi rời khỏi vùng tin cậy?
- Inbound/outbound mapper đã cấu hình đúng chiều và allow-list chưa?
- Kiểu dữ liệu header có tương thích với HTTP, AMQP, JMS, Kafka hoặc message store không?
- `replyChannel`/`errorChannel` có cần HeaderChannelRegistry và TTL có đủ dài không?
- Trace context có được truyền qua executor/broker theo cơ chế phù hợp không?
- Log và metrics có hỗ trợ chẩn đoán mà không làm lộ thông tin nhạy cảm không?

Một thiết kế header tốt giúp message mang đủ ngữ cảnh để flow điều phối chính xác, trong khi mỗi ranh giới adapter chỉ nhận đúng metadata mà giao thức và hệ thống đích cần.

## Tài liệu tham khảo

Các tài liệu chính thức dưới đây mô tả API và hành vi theo phiên bản Spring Integration/Spring Kafka tương ứng. Hãy đối chiếu phiên bản thực tế của ứng dụng trước khi áp dụng cấu hình cụ thể.

- [Spring Integration — Message và Header Propagation](https://docs.spring.io/spring-integration/reference/message.html)
- [Spring Integration — Content Enricher và Header Channel Registry](https://docs.spring.io/spring-integration/reference/content-enrichment.html)
- [Spring Integration — Message Transformation và Header Filter](https://docs.spring.io/spring-integration/reference/message-transformation.html)
- [Spring Integration — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html)
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html)
- [Spring Integration — Apache Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html)
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)

