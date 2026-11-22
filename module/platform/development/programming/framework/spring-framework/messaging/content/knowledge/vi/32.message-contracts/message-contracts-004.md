# Quy ước tên destination, route và schema

Trong hệ thống messaging, tên gọi là một phần của hợp đồng giao tiếp. Producer cần biết gửi message đến đâu; consumer cần biết đăng ký nhận ở đâu; cả hai phía cần hiểu payload có cấu trúc và ý nghĩa gì. Nếu destination, route và schema được đặt tên tùy tiện, hệ thống sẽ khó theo dõi, khó nâng cấp và dễ phát sinh lỗi khi nhiều service cùng phát triển.

Trong Spring, các khái niệm này có liên quan nhưng không đồng nhất:

- **Destination** là địa chỉ đích của message trong một cơ chế messaging hoặc broker, chẳng hạn STOMP destination hay JMS queue/topic.
- **Route** là tên định tuyến của một request RSocket. Route được truyền trong routing metadata và được Spring ánh xạ đến handler.
- **Schema** mô tả cấu trúc và ý nghĩa của payload: trường, kiểu dữ liệu, quy tắc null, đơn vị đo, định dạng thời gian và quy tắc tiến hóa.

Một nguyên tắc quan trọng: destination hoặc route quyết định message đi đâu; schema quyết định message chứa dữ liệu gì. Đổi tên một route không tự động đổi schema, và đổi DTO Java không tự động thay đổi destination của broker.

## 1. Phân biệt destination, route và schema trong Spring

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| STOMP destination | Địa chỉ để client gửi hoặc subscribe qua WebSocket/STOMP | /app/orders/submit, /topic/orders/created |
| JMS destination | Tên queue hoặc topic do broker/provider quản lý | orders.commands.submit.v1 |
| RSocket route | Khóa định tuyến request đến một responder | orders.submit.v1 |
| Payload schema | Hợp đồng dữ liệu được serialize trong message | OrderSubmitRequestV1, OrderSubmittedEventV1 |

### STOMP destination

Trong Spring WebSocket support, destination bắt đầu bằng application prefix được định tuyến đến các method có @MessageMapping. Destination bắt đầu bằng broker prefix được chuyển đến message broker để xử lý subscription và phân phối message.

Một cấu hình thường gặp:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Với cấu hình trên, client gửi đến /app/orders/submit sẽ được định tuyến đến handler ứng với /orders/submit. Client có thể subscribe /topic/orders/created để nhận sự kiện. Prefix /app là quy ước của ứng dụng; /topic và /queue là quy ước phân biệt cách sử dụng destination.

Lưu ý: với simple broker tích hợp, /topic và /queue không tự tạo ra ngữ nghĩa broker đặc biệt. Chúng chủ yếu là quy ước để phân biệt pub-sub và point-to-point. Khi dùng broker bên ngoài, cần kiểm tra semantics và quy tắc đặt tên mà broker đó hỗ trợ.

### JMS destination

Trong JMS, destination thường là một Queue hoặc Topic được cấu hình trong broker. Queue thường phục vụ mô hình point-to-point; Topic thường phục vụ publish-subscribe. Tên destination phải nhất quán với cấu hình thực tế của broker và listener container.

Ví dụ:

~~~java
@Component
class OrderMessageConsumer {

    @JmsListener(destination = "orders.events.created.v1")
    void onOrderCreated(OrderCreatedEventV1 event) {
        orderProjection.update(event);
    }
}
~~~

Producer có thể gửi đến destination bằng JmsTemplate:

~~~java
jmsTemplate.convertAndSend(
    "orders.commands.submit.v1",
    command
);
~~~

Tên queue/topic không tự quyết định semantics. Loại destination, subscription mode, durability, acknowledgement và cấu hình listener container mới xác định cách message được phân phối và xác nhận.

### RSocket route

RSocket sử dụng route trong metadata để chọn handler. Spring cho phép khai báo route bằng @MessageMapping và requester chỉ định route bằng RSocketRequester.

~~~java
@Controller
class OrderRSocketController {

    @MessageMapping("orders.submit.v1")
    Mono<OrderReceipt> submit(OrderSubmitRequestV1 request) {
        return orderService.submit(request);
    }
}
~~~

Requester gọi route tương ứng:

~~~java
Mono<OrderReceipt> response = requester
    .route("orders.submit.v1")
    .data(request)
    .retrieveMono(OrderReceipt.class);
~~~

Route RSocket có thể phân cấp và mặc định dùng dấu chấm làm dấu phân cách. Route không phải URL path; không nên tự thêm slash đầu chuỗi hoặc áp dụng quy tắc URL encoding cho route. Nếu dùng route matcher tùy chỉnh, requester và responder phải tuân theo cùng hợp đồng định tuyến.

## 2. Quy tắc đặt tên chung

Nên thống nhất quy tắc trong toàn bộ bounded context hoặc hệ thống, sau đó ánh xạ sang cú pháp riêng của từng transport.

### Dùng tên mô tả domain và mục đích

Tên nên trả lời được ba câu hỏi: message thuộc domain nào, nói về đối tượng nào và phục vụ hành động hay sự kiện gì?

Ví dụ:

- orders.submit: yêu cầu tạo đơn hàng.
- orders.cancel: yêu cầu hủy đơn hàng.
- orders.events.created: sự kiện đơn hàng đã được tạo.
- orders.events.cancelled: sự kiện đơn hàng đã bị hủy.
- inventory.reserve: yêu cầu giữ tồn kho.
- inventory.events.reserved: sự kiện tồn kho đã được giữ.

Tránh tên quá chung chung như message, data, update, process, event hoặc topic1. Các tên này không thể hiện rõ nghiệp vụ và dễ bị tái sử dụng cho những hợp đồng không liên quan.

### Phân biệt command, query và event

Dùng động từ mệnh lệnh cho command, tên hành động truy vấn cho query và thì quá khứ cho event.

| Loại message | Cách đặt tên | Ví dụ |
|---|---|---|
| Command | Động từ + đối tượng | SubmitOrder, CancelOrder |
| Query | Get/Find/List + đối tượng | GetOrder, FindOrders |
| Event | Đối tượng + hành động đã xảy ra | OrderSubmitted, OrderCancelled |
| Response | Đối tượng kết quả | OrderReceipt, OrderView |

Command biểu thị ý định cần thực hiện; event biểu thị sự kiện đã xảy ra. Không đặt tên event như một command vì consumer có thể hiểu nhầm một thông báo sự kiện thành yêu cầu thực thi.

### Chuẩn hóa chữ và dấu phân cách

Một quy ước thực tế:

- Tên destination và route dùng chữ thường ASCII.
- Dùng dấu chấm để phân cấp các route hoặc destination theo phong cách messaging.
- Với STOMP, dùng slash để tạo namespace destination dạng path nếu ứng dụng đã chọn quy ước đó.
- Không trộn dấu chấm, gạch dưới, gạch ngang và slash một cách tùy tiện trong cùng một namespace.
- Không dùng dấu cách, dấu tiếng Việt, ký tự điều khiển hoặc tên viết tắt khó hiểu.
- Không thay đổi chữ hoa/chữ thường giữa producer và consumer.

Ví dụ cùng một ý nghĩa có thể được biểu diễn theo từng transport:

| Mục đích | STOMP | RSocket | JMS |
|---|---|---|---|
| Gửi command tạo đơn | /app/orders/submit | orders.submit.v1 | orders.commands.submit.v1 |
| Nhận event tạo đơn | /topic/orders/created | orders.events.created.v1 | orders.events.created.v1 |
| Nhận thông báo riêng | /user/queue/notifications | notifications.user | notifications.user |

Đây là ví dụ quy ước của ứng dụng, không phải tên bắt buộc của Spring. Cần chọn một kiểu nhất quán và kiểm tra khả năng hỗ trợ của broker hoặc route matcher.

### Tránh đưa dữ liệu biến đổi vào tên

Không dùng order ID, email, access token, số điện thoại hoặc dữ liệu cá nhân làm một phần tên destination cố định. Với route có biến, chỉ đưa định danh cần thiết và không nhạy cảm vào route pattern; dữ liệu nghiệp vụ đầy đủ vẫn nên nằm trong payload hoặc metadata đã được kiểm soát.

Ví dụ route pattern RSocket:

~~~java
@MessageMapping("orders.{orderId}.status")
Mono<OrderStatus> status(@DestinationVariable String orderId) {
    return orderService.findStatus(orderId);
}
~~~

Requester có thể gọi route cụ thể như orders.O-100.status. Cần xác thực và phân quyền dựa trên principal và chính sách truy cập; biết tên route không đồng nghĩa với được phép gọi route đó.

Không nhúng môi trường dev, test hoặc prod vào tên hợp đồng trong code nếu hạ tầng có thể tách môi trường bằng cấu hình broker, namespace hoặc account. Nếu cần phân vùng theo tenant, phải xác định rõ quy tắc phân quyền và giới hạn truy cập.

## 3. Đặt tên theo semantics của destination

Tên nên thể hiện cách message được sử dụng, nhưng không thay thế cấu hình semantics của transport.

### Queue cho công việc cần xử lý

Một queue thường đại diện cho công việc mà một consumer trong nhóm cạnh tranh sẽ xử lý. Có thể dùng hậu tố hoặc namespace commands:

- orders.commands.submit.v1
- billing.commands.capture-payment.v1
- inventory.commands.reserve.v1

Nếu có retry hoặc dead-letter destination, nên đặt tên theo cùng namespace:

- orders.commands.submit.v1.retry
- orders.commands.submit.v1.dlq

Các tên retry và DLQ phải khớp với cấu hình thực tế của broker. Không tạo destination chỉ bằng cách đặt tên; cần cấu hình binding, policy, TTL, dead-letter routing và quyền truy cập tương ứng.

### Topic cho sự kiện cần phân phối

Topic thường dùng khi nhiều subscriber cần nhận cùng một loại sự kiện. Có thể dùng namespace events:

- orders.events.created.v1
- orders.events.cancelled.v1
- payments.events.captured.v1

Tên event nên thể hiện điều đã xảy ra. Consumer có thể đăng ký theo từng event hoặc pattern nếu broker hỗ trợ.

### Destination dành cho người dùng

Spring STOMP hỗ trợ user destination với prefix /user/. Ví dụ client subscribe /user/queue/notifications để nhận thông báo riêng cho phiên hoặc người dùng đã xác thực. Spring chuyển destination logic này thành destination nội bộ phù hợp với session.

Không tự nối username vào destination rồi cho client tùy ý subscribe. Hãy dùng cơ chế user destination và bảo đảm danh tính người dùng được xác thực ở server.

## 4. Quy ước đặt tên route RSocket

RSocket route là tên logic để requester và responder thống nhất điểm vào của một request. Một route thường có cấu trúc:

**domain.action.version**

Ví dụ:

- orders.submit.v1
- orders.cancel.v1
- orders.find-by-id.v1
- inventory.reserve.v1
- pricing.calculate.v1

Một số nguyên tắc:

1. Dùng tên ổn định, ngắn và mô tả đúng capability của handler.
2. Giữ cùng thứ tự namespace giữa các route trong một domain.
3. Dùng một quy ước thống nhất cho tên hành động, ví dụ submit, cancel, find-by-id.
4. Chỉ đưa version vào route khi cần phân biệt hợp đồng không tương thích.
5. Tránh tạo route trùng tên cho các handler có semantics khác nhau.
6. Không dùng tên class Java làm route một cách ngầm định; route là hợp đồng wire-level và nên được khai báo rõ ràng.

Spring hỗ trợ route pattern và @DestinationVariable. Ví dụ:

~~~java
@Controller
class OrderStatusController {

    @MessageMapping("orders.{orderId}.status")
    Mono<OrderStatusV1> status(
            @DestinationVariable String orderId) {
        return orderService.findStatus(orderId);
    }
}
~~~

Không nên thay đổi route chỉ vì đổi tên package, class hoặc method Java. Có thể refactor implementation nội bộ mà vẫn giữ route công khai ổn định.

## 5. Quy ước đặt tên schema và DTO

Schema là hợp đồng của payload. Tên schema cần ổn định qua các lần refactor code và mô tả rõ loại message cùng phiên bản hợp đồng.

Một quy ước dễ đọc:

- Command: OrderSubmitRequestV1 hoặc SubmitOrderCommandV1.
- Event: OrderCreatedEventV1 hoặc OrderSubmittedEventV1.
- Query: GetOrderQueryV1.
- Response: OrderReceiptV1 hoặc OrderViewV1.

Nên dùng cùng một quy tắc cho toàn bộ domain. Hậu tố Command, Event, Query và Response giúp phân biệt mục đích của payload ngay khi đọc code.

Ví dụ:

~~~java
public record SubmitOrderCommandV1(
    String orderId,
    String customerId,
    BigDecimal total,
    String currency
) {}

public record OrderCreatedEventV1(
    String eventId,
    String orderId,
    Instant occurredAt,
    BigDecimal total,
    String currency
) {}

public record OrderReceiptV1(
    String orderId,
    String status
) {}
~~~

Tên Java class có thể thay đổi khi refactor. Nếu schema được chia sẻ giữa nhiều ngôn ngữ hoặc nhiều service, hãy định nghĩa một schema ID ổn định độc lập với package Java.

Ví dụ ID logic:

- com.acme.orders.SubmitOrderCommand.v1
- com.acme.orders.OrderCreatedEvent.v1

Ví dụ tên file JSON Schema:

- orders.submit-order-command.v1.schema.json
- orders.order-created-event.v1.schema.json

Với Protobuf, có thể đưa version major vào package:

~~~proto
syntax = "proto3";

package acme.orders.v1;

message OrderCreatedEvent {
  string event_id = 1;
  string order_id = 2;
  string occurred_at = 3;
  string currency = 4;
}
~~~

Không tái sử dụng field number đã xóa trong Protobuf. Đánh dấu field number và tên cũ là reserved để tránh một payload mới bị diễn giải nhầm theo schema cũ.

## 6. Đặt tên và mô tả field trong schema

Tên field cũng là một phần của hợp đồng. Một field tốt cần có tên dễ hiểu và ngữ nghĩa ổn định.

Nên:

- Dùng camelCase cho field JSON nếu đó là convention đã thống nhất.
- Dùng tên thể hiện ý nghĩa nghiệp vụ, ví dụ orderId, occurredAt, currency.
- Phân biệt ID của message với ID của aggregate: eventId khác orderId.
- Dùng timestamp có timezone hoặc quy ước UTC rõ ràng, ví dụ ISO-8601.
- Ghi rõ đơn vị của số đo hoặc tiền tệ. Không dùng amount nếu chưa quy định currency và scale.
- Quy định field bắt buộc, nullable, default và miền giá trị.
- Tránh tên mơ hồ như value, type, statusCode nếu không có ngữ cảnh rõ ràng.

Ví dụ payload:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "O-100",
  "occurredAt": "2026-11-07T10:30:00Z",
  "total": 125000,
  "currency": "VND"
}
~~~

Trong hợp đồng này, occurredAt là thời điểm sự kiện xảy ra, total là số tiền theo đơn vị nhỏ nhất hay đơn vị tiền chính phải được quy định rõ trong tài liệu schema. Currency dùng mã ISO 4217 nếu nghiệp vụ cần biểu diễn tiền tệ. Không dựa vào tên field để suy luận những quy tắc chưa được ghi rõ.

Không tái sử dụng một field cho nhiều ý nghĩa theo từng phiên bản. Ví dụ status không nên mang lúc là trạng thái đơn hàng, lúc là mã lỗi và lúc là trạng thái thanh toán.

## 7. Versioning destination, route và schema

Versioning giúp hai phía cùng tồn tại trong thời gian triển khai không đồng bộ. Tuy nhiên, version cần có chính sách rõ ràng để tránh tạo quá nhiều tên gần giống nhau.

### Khi nào cần version mới?

Thường cần major version mới khi:

- Xóa hoặc đổi tên field mà consumer cũ cần.
- Đổi kiểu dữ liệu hoặc format biểu diễn theo cách không tương thích.
- Đổi ý nghĩa nghiệp vụ của field.
- Thay đổi required/nullability khiến payload cũ không còn hợp lệ.
- Đổi interaction model hoặc semantics của request.
- Đổi cách xác thực hoặc ý nghĩa của route theo cách phá vỡ client hiện hữu.

Thường không cần đổi major version khi chỉ thêm field optional mà cả producer và consumer đã được thiết kế để chịu được thay đổi đó. Tuy nhiên, phải kiểm tra cấu hình serializer/deserializer thực tế và chính sách schema compatibility của hệ thống.

### Chọn một nguồn version có thẩm quyền

Có thể version trong route, destination, schema ID hoặc header metadata. Không nên version ở nhiều nơi mà không quy định quan hệ giữa chúng.

Ví dụ:

- Route: orders.submit.v1
- Schema ID: com.acme.orders.SubmitOrderCommand.v1

Nếu version route và schema cùng xuất hiện, chúng phải khớp theo hợp đồng đã công bố. Tránh route v1 nhưng payload lại dùng schema v2 mà không có quy tắc chuyển đổi rõ ràng.

Nếu route ổn định và schema được quản lý bằng schema registry, có thể giữ route không version và khai báo schema ID/version trong metadata hoặc header. Đây là quyết định kiến trúc; Spring Framework không tự cung cấp một schema registry chung cho mọi loại payload.

### Quy trình nâng cấp

1. Công bố schema mới và kiểm tra tương thích với schema cũ.
2. Triển khai consumer có thể đọc phiên bản cũ và mới nếu cần giai đoạn chuyển tiếp.
3. Đưa route hoặc destination mới vào hoạt động nếu đó là breaking change.
4. Nâng cấp producer theo từng đợt.
5. Theo dõi traffic trên tên cũ và tên mới.
6. Ngừng tên cũ sau khi không còn consumer sử dụng và đã hết thời gian hỗ trợ.

Không xóa route hoặc destination cũ ngay khi producer mới vừa được phát hành. Trong hệ thống phân tán, các client có thể nâng cấp vào thời điểm khác nhau.

## 8. Message headers và metadata

Payload schema mô tả dữ liệu nghiệp vụ. Một số thông tin phục vụ vận hành và định tuyến phù hợp hơn với message headers hoặc metadata:

- messageId: định danh duy nhất của message.
- correlationId: liên kết các message trong cùng một luồng nghiệp vụ.
- causationId: xác định message gây ra message hiện tại.
- schemaId hoặc schemaVersion: xác định schema dùng để giải mã.
- contentType: mô tả định dạng payload.
- occurredAt: thời điểm nghiệp vụ xảy ra, nếu đó là một phần của event.
- trace context: thông tin nối distributed trace.

Ví dụ tạo Spring Message:

~~~java
Message<OrderCreatedEventV1> message = MessageBuilder
    .withPayload(event)
    .setHeader("schemaId", "com.acme.orders.OrderCreatedEvent.v1")
    .setHeader("correlationId", correlationId)
    .build();
~~~

Spring Message có payload và headers. Transport adapter có thể ánh xạ một phần header sang STOMP headers, JMS properties hoặc RSocket metadata. Không giả định mọi header đều được truyền nguyên vẹn qua mọi transport; hãy kiểm tra mapping và giới hạn của adapter.

Không đưa access token, mật khẩu hoặc dữ liệu cá nhân nhạy cảm vào destination, route hoặc header tùy tiện. Metadata cũng cần được bảo vệ và lọc theo chính sách logging.

## 9. Kiểm thử hợp đồng và quy tắc đặt tên

Tên hợp đồng chỉ hữu ích nếu được kiểm tra và duy trì nhất quán. Nên có contract test ở producer và consumer.

Các kiểm tra nên bao gồm:

1. **Destination/route tồn tại:** producer gửi đến đúng destination hoặc route đã công bố.
2. **Mapping đúng:** STOMP application prefix dẫn đến đúng @MessageMapping; RSocket route ánh xạ đúng responder.
3. **Broker semantics đúng:** queue/topic, subscription, durability, retry và DLQ khớp với cấu hình broker.
4. **Schema serialization:** payload được serialize và deserialize bằng đúng codec.
5. **Schema compatibility:** payload của phiên bản trước vẫn được consumer mới đọc nếu hợp đồng cam kết backward compatibility.
6. **Field semantics:** null, field thiếu, enum mới, timestamp, decimal và đơn vị đo được xử lý đúng.
7. **Security:** client không thể subscribe hoặc gọi route chỉ bằng cách đoán tên; quyền truy cập được kiểm tra ở server.
8. **Deprecation:** metric xác nhận không còn traffic trên destination hoặc route cũ trước khi loại bỏ.

Nên lưu payload mẫu cho mỗi schema version và dùng chúng trong CI. Nếu sử dụng JSON Schema, Avro hoặc Protobuf cùng schema registry, hãy bật kiểm tra compatibility theo chính sách đã chọn. Việc đăng ký schema và enforcement là trách nhiệm của công cụ/schema registry tương ứng, không phải tự động có sẵn chỉ vì ứng dụng dùng Spring Messaging.

## 10. Những lỗi đặt tên thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng cùng tên cho command và event | Consumer khó phân biệt ý định và sự kiện đã xảy ra | Dùng namespace commands và events |
| Dùng một destination cho nhiều loại payload không liên quan | Consumer phải đoán schema hoặc kiểm tra type tùy tiện | Tách destination theo loại message |
| Dùng route RSocket như URL path | Nhầm quy tắc separator và URL decoding | Theo quy tắc route matcher của RSocket |
| Tùy tiện đổi chữ hoa/chữ thường | Producer và consumer không khớp tên | Chuẩn hóa lowercase |
| Đổi tên Java class làm đổi schema wire-level | Refactor nội bộ gây breaking change | Dùng schema ID ổn định |
| Version mọi thay đổi nhỏ | Tạo nhiều route và schema khó quản lý | Chỉ major version khi breaking change |
| Version route và schema không đồng bộ | Client gửi đúng route nhưng payload sai phiên bản | Định nghĩa một nguồn version có thẩm quyền |
| Đặt PII hoặc token trong route | Rò rỉ dữ liệu qua log và metric | Dùng ID không nhạy cảm và metadata bảo mật |
| Giả định /topic luôn là pub-sub | Semantics thực tế có thể phụ thuộc broker | Kiểm tra cấu hình broker |
| Xóa destination cũ quá sớm | Client chưa nâng cấp bị lỗi | Có giai đoạn deprecation và đo traffic |

## 11. Checklist trước khi công bố hợp đồng

- [ ] Tên destination hoặc route mô tả rõ domain và mục đích.
- [ ] Command, query và event được phân biệt.
- [ ] Quy ước chữ thường, separator và namespace được thống nhất.
- [ ] STOMP destination, JMS destination và RSocket route không bị nhầm lẫn.
- [ ] Queue/topic semantics được xác định bằng cấu hình broker.
- [ ] Schema ID ổn định, độc lập với tên class Java.
- [ ] Field có kiểu, nullability, đơn vị và ý nghĩa rõ ràng.
- [ ] Version chỉ tăng khi cần thiết và có chính sách tương thích.
- [ ] Route version và schema version không mâu thuẫn.
- [ ] Headers/metadata được dùng cho correlation, schema ID và tracing phù hợp.
- [ ] Có contract test và payload fixture trong CI.
- [ ] Có kế hoạch deprecation và số liệu xác nhận trước khi xóa tên cũ.
- [ ] Có kiểm tra xác thực và phân quyền tại server.

## 12. Tài liệu tham khảo

- [Spring Framework Reference: Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html) — application destination prefix, broker prefix và cấu hình STOMP.
- [Spring Framework Reference: Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html) — cách destination được ánh xạ đến @MessageMapping và broker.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — routing metadata, route matcher, RSocketRequester và annotated responders.
- [Spring Framework Reference: JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html) — JmsTemplate, listener và tích hợp JMS.
- [JSON Schema](https://json-schema.org/learn/getting-started-step-by-step) — mô tả và kiểm tra cấu trúc payload JSON.
- [Protocol Buffers: Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating) — quy tắc tiến hóa schema và field number.
