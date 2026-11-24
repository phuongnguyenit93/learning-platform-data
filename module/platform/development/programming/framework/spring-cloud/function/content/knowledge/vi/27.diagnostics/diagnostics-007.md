# Header định tuyến không có tác dụng với luồng phản ứng

## 1. Triệu chứng: routing header có mặt nhưng target không thay đổi

Một ứng dụng **Spring Cloud Function** có hai bộ xử lý:

~~~java
@Bean
public Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders() {
    return events -> events.map(this::processOrder);
}

@Bean
public Function<Flux<InvoiceEvent>, Flux<InvoiceResult>> processInvoices() {
    return events -> events.map(this::processInvoice);
}
~~~

Producer muốn chọn function theo từng message bằng header:

~~~text
spring.cloud.function.definition=processOrders
~~~

Hoặc dùng expression:

~~~text
spring.cloud.function.routing-expression=headers['eventType'] == 'ORDER'
    ? 'processOrders'
    : 'processInvoices'
~~~

Nhưng khi đầu vào là `Flux<?>` hoặc `Publisher<?>`, header routing trên từng message có thể không hoạt động như mong đợi. Các event mang header khác nhau vẫn đi vào cùng một reactive function, hoặc RoutingFunction không chọn target theo header của từng phần tử.

Đây thường không phải lỗi chính tả header. Nguyên nhân nằm ở **đơn vị công việc (unit of work)** của reactive function:

- Với imperative function như `Function<Message<OrderEvent>,OrderResult>`, framework gọi function một lần cho mỗi message. Router có một Message cụ thể để đọc header và chọn target.
- Với reactive function như `Function<Flux<Message<OrderEvent>>,Flux<OrderResult>>`, framework gọi function một lần để truyền vào publisher. Các phần tử chỉ được xử lý sau đó trong Reactor pipeline.
- RoutingFunction không được gọi lại cho từng phần tử trong publisher chỉ để xem header và chọn một function mới.
- Với reactive input, Spring Cloud Function yêu cầu routing instruction được cung cấp qua **application properties**; instruction đó chọn target cho toàn stream.

Bài thuộc chương **Chẩn đoán**, đề mục **“Header định tuyến không có tác dụng với luồng phản ứng”**, trong module **SPRING_CLOUD_FUNCTION**. Module học cách phát triển logic nghiệp vụ tái sử dụng bằng `Supplier`, `Function` và `Consumer`, tra cứu qua `FunctionCatalog`, chuyển đổi message và triển khai qua HTTP, sự kiện hoặc serverless.

**Câu hỏi chẩn đoán trung tâm:** function được gọi một lần cho từng message hay chỉ một lần với cả publisher?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt routing theo từng message với routing toàn reactive stream.
2. Giải thích vì sao header `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression` không route từng phần tử của `Flux`.
3. Hiểu vai trò và giới hạn của `MessageRoutingCallback`.
4. Cấu hình routing bằng application properties cho reactive function.
5. Phân biệt routing function với routing output destination của Spring Cloud Stream.
6. Chọn imperative routing hoặc tự phân nhánh bên trong Reactor pipeline.
7. Kiểm tra routing qua HTTP, Spring Cloud Stream, `FunctionCatalog` và serverless adapter.
8. Viết test xác minh từng event đi đúng nhánh và không bị bỏ sót.
9. Bảo vệ routing target bằng allowlist, authorization và kiểm soát SpEL.

## 2. Imperative và reactive có đơn vị công việc khác nhau

### 2.1. Imperative: một lần gọi tương ứng một message

~~~java
@Bean
Function<Message<OrderEvent>, OrderResult> processOrder() {
    return message -> process(message.getPayload());
}
~~~

Nếu adapter nhận ba message, function được gọi ba lần:

~~~text
Message A → processOrder(message A)
Message B → processOrder(message B)
Message C → processOrder(message C)
~~~

Mỗi lần gọi có một `Message<?>` cụ thể. RoutingFunction có thể đọc header của message đó để chọn target.

### 2.2. Reactive: một lần gọi nhận cả publisher

~~~java
@Bean
Function<Flux<Message<OrderEvent>>, Flux<OrderResult>> processOrders() {
    return messages -> messages.map(message ->
        process(message.getPayload())
    );
}
~~~

Adapter truyền một `Flux`:

~~~text
processOrders(publisher)
    ├─ Message A
    ├─ Message B
    └─ Message C
~~~

`processOrders` được gọi một lần để nhận publisher. Reactor xử lý các phần tử khi pipeline được subscribe. Nhiều `Message<?>` bên trong `Flux` không biến function thành nhiều invocation imperative.

### 2.3. Sơ đồ so sánh

~~~mermaid
flowchart TB
    subgraph IMP["Imperative function"]
      A["Message A + header A"] --> R["RoutingFunction"]
      B["Message B + header B"] --> R
      C["Message C + header C"] --> R
      R -->|A| FA["Function A"]
      R -->|B| FB["Function B"]
      R -->|C| FC["Function C"]
    end
    subgraph REACT["Reactive function"]
      P["Publisher / Flux"] --> RR["Một routing decision"]
      RR --> T["Một reactive target"]
      T --> PIPE["Reactor pipeline"]
      PIPE --> X["Message A"]
      PIPE --> Y["Message B"]
      PIPE --> Z["Message C"]
    end
~~~

Điểm khác biệt không phải header có tồn tại hay không. Điểm khác biệt là RoutingFunction nhận một Message hay một Publisher tại thời điểm chọn target.

## 3. Header vẫn có trong từng phần tử, nhưng built-in router không route từng item

Reactive function có thể nhận:

~~~java
Function<Flux<Message<OrderEvent>>, Flux<OrderResult>>
~~~

Mỗi `Message<OrderEvent>` vẫn có payload và headers. Bên trong business pipeline, bạn có thể đọc header:

~~~java
messages.map(message ->
    message.getHeaders().get("eventType", String.class)
);
~~~

Nhưng điều đó không có nghĩa RoutingFunction đã đọc header trước khi chọn function. Router nhận publisher như một đơn vị công việc; header của từng phần tử chỉ được nhìn thấy khi Reactor pipeline xử lý chúng.

| Câu hỏi | Reactive function |
| --- | --- |
| Đọc header của từng item trong `Flux<Message<T>>`? | **Có**, bên trong pipeline |
| Built-in RoutingFunction chọn function khác nhau cho từng item trong cùng publisher? | **Không** theo per-message routing của SCF reactive |
| Application property chọn function cho cả stream? | **Có** |
| Tự phân nhánh từng item bằng `flatMap`/`concatMap`? | **Có** |
| `MessageRoutingCallback` quyết định từng item của reactive publisher? | **Không** theo routing callback imperative |

Ví dụ producer có thể tạo message với header khác nhau:

~~~java
Message<OrderEvent> orderMessage =
    MessageBuilder.withPayload(orderEvent)
        .setHeader("spring.cloud.function.definition", "processOrders")
        .build();

Message<InvoiceEvent> invoiceMessage =
    MessageBuilder.withPayload(invoiceEvent)
        .setHeader("spring.cloud.function.definition", "processInvoices")
        .build();
~~~

Nếu adapter gộp chúng thành một publisher rồi gọi reactive function, header vẫn có thể nằm trên từng phần tử. SCF không gọi RoutingFunction riêng cho mỗi phần tử để đổi target.

## 4. Hai routing header chính

Spring Cloud Function hỗ trợ hai routing instruction:

~~~text
spring.cloud.function.definition
spring.cloud.function.routing-expression
~~~

### 4.1. Definition header

Header `spring.cloud.function.definition` chứa tên function hoặc composition:

~~~text
spring.cloud.function.definition=processOrders
~~~

Có thể chứa cả composition:

~~~text
spring.cloud.function.definition=normalizeOrder|processOrders
~~~

### 4.2. Routing-expression header

Header `spring.cloud.function.routing-expression` chứa SpEL expression cần trả về tên function/definition:

~~~text
spring.cloud.function.routing-expression=headers['eventType'] == 'ORDER'
    ? 'processOrders'
    : 'processInvoices'
~~~

Trong imperative routing, root object của expression là message đầu vào, nên expression có thể đọc payload và headers.

### 4.3. Header khác application property

| Nơi đặt instruction | Ví dụ | Phạm vi |
| --- | --- | --- |
| Message header | `spring.cloud.function.definition` | Một message imperative |
| Message header | `spring.cloud.function.routing-expression` | Expression trên message imperative |
| Application property | `spring.cloud.function.definition` | Chọn target ở cấp ứng dụng |
| Application property | `spring.cloud.function.routing-expression` | Expression routing ở cấp ứng dụng |

Với reactive input, hãy dùng application properties để chọn target cho toàn stream. Không chuyển header per-message thành property dùng chung rồi kỳ vọng từng item có target riêng.

## 5. Vì sao reactive routing chỉ dùng application properties?

Tài liệu Spring Cloud Function giải thích theo unit of work:

- Imperative function có unit of work là một `Message`.
- Reactive function có unit of work là toàn bộ `Publisher`/stream.
- Reactive function được invoke một lần để nhận publisher; Reactor xử lý các phần tử về sau.
- Router không thể dựa vào routing instruction của từng phần tử để chọn lại function trước mỗi invocation.
- Với reactive function, routing instruction phải đến từ application properties và áp dụng cho toàn stream.

~~~mermaid
sequenceDiagram
    participant A as Adapter
    participant R as RoutingFunction
    participant F as Reactive Function
    participant P as Reactor pipeline
    A->>R: Publisher (Flux<Message>)
    R->>R: Đọc application properties
    R->>F: Chọn một target cho stream
    F->>P: Truyền Publisher vào pipeline
    loop Mỗi phần tử được tiêu thụ
        P->>P: Xử lý Message và header của item
    end
~~~

Nếu application property chọn `processOrders`, cả publisher được chuyển tới function đó. Header eventType của một phần tử không làm router đổi target sang `processInvoices` ở phần tử tiếp theo.

## 6. Cấu hình đúng khi chọn một target cho toàn stream

Giả sử ứng dụng có reactive function xử lý đơn hàng:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders() {
    return events -> events.map(this::processOrder);
}
~~~

Cấu hình tường minh:

~~~properties
spring.cloud.function.definition=processOrders
~~~

Hoặc YAML:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
~~~

Deployment khác có thể chọn function khác:

~~~properties
spring.cloud.function.definition=processInvoices
~~~

### 6.1. Cấu hình theo profile

~~~yaml
spring:
  config:
    activate:
      on-profile: orders
  cloud:
    function:
      definition: processOrders
---
spring:
  config:
    activate:
      on-profile: invoices
  cloud:
    function:
      definition: processInvoices
~~~

Kích hoạt profile:

~~~bash
java -jar app.jar --spring.profiles.active=orders
~~~

Profile chọn target ở cấp ứng dụng. Cách này phù hợp khi mỗi instance/consumer group chuyên xử lý một loại stream.

### 6.2. Profile không phải per-message routing

Nếu một publisher chứa cả order và invoice, profile orders sẽ route toàn publisher tới `processOrders`. Nó không tự tách event invoice sang function khác. Nếu một instance cần xử lý nhiều loại event trong cùng stream, hãy phân nhánh bên trong reactive pipeline hoặc tách ingress/binding thành các stream riêng.

## 7. MessageRoutingCallback chỉ áp dụng imperative routing

`MessageRoutingCallback` là strategy xác định function đích từ một `Message<?>`:

~~~java
public interface MessageRoutingCallback {
    String routingResult(Message<?> message);
}
~~~

Ví dụ:

~~~java
@Bean
MessageRoutingCallback routeByEventType() {
    return new MessageRoutingCallback() {
        @Override
        public String routingResult(Message<?> message) {
            String type =
                message.getHeaders().get("eventType", String.class);

            return switch (type == null ? "" : type) {
                case "ORDER" -> "processOrder";
                case "INVOICE" -> "processInvoice";
                default -> throw new IllegalArgumentException(
                    "Unsupported eventType: " + type
                );
            };
        };
    };
}
~~~

Callback được router gọi với message cụ thể để quyết định target. Khi target là reactive function, SCF gọi function để chuyển publisher vào; callback không được gọi lại cho từng phần tử trong publisher.

### 7.1. Callback có thể ghi đè header trong imperative routing

Thứ tự ưu tiên theo tài liệu hiện hành:

1. `MessageRoutingCallback`.
2. Message headers nếu không có callback.
3. Application properties.

Nếu callback được đăng ký, header `spring.cloud.function.definition` có thể bị bỏ qua vì callback có ưu tiên cao hơn. Đây là nguyên nhân khác khiến header không có tác dụng trong ứng dụng imperative.

Thứ tự này không biến callback thành per-message routing cho reactive publisher. Reactive routing vẫn dùng application properties.

## 8. Definition header và routing-expression

Header tĩnh:

~~~java
Message<OrderEvent> message =
    MessageBuilder.withPayload(order)
        .setHeader(
            "spring.cloud.function.definition",
            "processOrder"
        )
        .build();
~~~

Header expression:

~~~java
Message<OrderEvent> message =
    MessageBuilder.withPayload(order)
        .setHeader(
            "spring.cloud.function.routing-expression",
            "headers['eventType'] == 'ORDER' ? 'processOrder' : 'processInvoice'"
        )
        .build();
~~~

Cả hai cách có thể route theo từng message khi đầu vào là imperative Message và adapter gửi message qua RoutingFunction.

Các header `eventType`, `tenantId`, `correlationId`, `traceId` hoặc `contentType` chỉ là metadata ứng dụng/transport, trừ khi routing logic được cấu hình để đọc chúng. Gửi `eventType=ORDER` không tự động chọn bean `processOrder`.

Không nhầm với header `spring.cloud.stream.sendto.destination`. Header này định tuyến **output message tới destination** của Spring Cloud Stream, không chọn function xử lý input.

## 9. Route từng event trong reactive stream bằng cách phân nhánh trong Flux

Nếu một stream chứa nhiều loại event và mỗi event cần một nhánh khác nhau, hãy viết logic phân nhánh bên trong reactive function.

~~~java
@Bean
Function<Flux<Message<InboundEvent>>, Flux<RoutedResult>> dispatchEvents(
        OrderHandler orderHandler,
        InvoiceHandler invoiceHandler) {

    return messages -> messages.concatMap(message -> {
        InboundEvent event = message.getPayload();
        String type =
            message.getHeaders().get("eventType", String.class);

        return switch (type == null ? "" : type) {
            case "ORDER" -> orderHandler.handle(event);
            case "INVOICE" -> invoiceHandler.handle(event);
            default -> Mono.error(
                new IllegalArgumentException(
                    "Unsupported eventType: " + type
                )
            );
        };
    });
}
~~~

Các service:

~~~java
public interface OrderHandler {
    Mono<RoutedResult> handle(InboundEvent event);
}

public interface InvoiceHandler {
    Mono<RoutedResult> handle(InboundEvent event);
}
~~~

DTO:

~~~java
public record InboundEvent(
    String eventId,
    String payload
) {}

public record RoutedResult(
    String eventId,
    String handler,
    String status
) {}
~~~

Đây là business-level dispatch bên trong stream:

- Reactive function được gọi một lần với publisher.
- Mỗi `Message` được đọc bên trong `concatMap`.
- Ứng dụng chọn handler dựa trên header của từng item.
- Kết quả được phát thành publisher output.
- FunctionCatalog không route lại từng event.

### 9.1. Chọn operator theo ordering/concurrency

- `concatMap` xử lý tuần tự và giữ thứ tự output theo input.
- `flatMap` cho phép inner publisher chạy đồng thời; output có thể không giữ thứ tự nguồn.
- `flatMapSequential` có thể thực hiện đồng thời nhưng giữ thứ tự phát, đổi lại cần buffering.

Nếu event cập nhật cùng một aggregate hoặc phải giữ thứ tự giao dịch, đừng đổi sang `flatMap` chỉ để tăng concurrency khi chưa có bảo đảm ordering.

### 9.2. Allowlist target

Ví dụ dùng switch trên các giá trị cố định. Đây là allowlist đơn giản. Không lấy tên class/function tùy ý từ header rồi dùng reflection hoặc SpEL tự do để gọi bất cứ bean nào trong context.

## 10. Route theo payload thay vì header

Nếu loại event đã nằm trong payload, có thể không cần metadata routing riêng:

~~~java
public record DomainEvent(
    String eventType,
    String eventId,
    String body
) {}
~~~

~~~java
@Bean
Function<Flux<DomainEvent>, Flux<RoutedResult>> dispatchByPayload(
        OrderHandler orderHandler,
        InvoiceHandler invoiceHandler) {

    return events -> events.concatMap(event ->
        switch (event.eventType()) {
            case "ORDER" -> orderHandler.handle(
                new InboundEvent(event.eventId(), event.body())
            );
            case "INVOICE" -> invoiceHandler.handle(
                new InboundEvent(event.eventId(), event.body())
            );
            default -> Mono.error(
                new IllegalArgumentException(
                    "Unsupported event type: " + event.eventType()
                )
            );
        }
    );
}
~~~

Ưu điểm:

- Routing data là một phần của schema event.
- Có thể serialize, validate và version hóa cùng payload.
- Không phụ thuộc adapter có propagate custom header hay không.
- Test đơn giản hơn với event object thuần.

Nhược điểm: payload có thể lặp metadata đã có trong envelope/message headers. Chọn một contract rõ ràng, tránh để header và payload mâu thuẫn.

## 11. Chia stream thành các nhánh reactive

Có thể dùng `filter`, `groupBy` hoặc các operator Reactor khác để chia stream.

~~~java
@Bean
Function<Flux<DomainEvent>, Flux<RoutedResult>> dispatchByType(
        OrderHandler orderHandler,
        InvoiceHandler invoiceHandler) {

    return events -> events
        .groupBy(DomainEvent::eventType)
        .flatMap(group ->
            switch (group.key()) {
                case "ORDER" ->
                    group.concatMap(event -> orderHandler.handle(
                        new InboundEvent(event.eventId(), event.body())
                    ));
                case "INVOICE" ->
                    group.concatMap(event -> invoiceHandler.handle(
                        new InboundEvent(event.eventId(), event.body())
                    ));
                default ->
                    group.flatMap(event ->
                        Mono.error(new IllegalArgumentException(
                            "Unsupported event type: " + group.key()
                        ))
                    );
            }
        );
}
~~~

`groupBy` có thể tạo nhiều group sống đồng thời; cần quan tâm lifecycle, backpressure và việc tiêu thụ từng group. Với số lượng key không giới hạn, không tạo group vô hạn mà không có chiến lược quản lý.

### 11.1. Cẩn thận khi filter cùng một publisher nhiều lần

Mẫu sau có thể trông đơn giản:

~~~java
Flux<RoutedResult> orders =
    events.filter(e -> "ORDER".equals(e.eventType()))
        .concatMap(orderHandler::handle);

Flux<RoutedResult> invoices =
    events.filter(e -> "INVOICE".equals(e.eventType()))
        .concatMap(invoiceHandler::handle);

return Flux.merge(orders, invoices);
~~~

Nhưng một `Flux` thường là nguồn cold; hai nhánh có thể subscribe upstream hai lần. Dùng thiết kế multicast/share phù hợp hoặc một operator phân nhánh duy nhất. Không copy mẫu này nguyên xi nếu nguồn có side effect hoặc chỉ đọc được một lần.

### 11.2. Khi cần output binding riêng

Spring Cloud Function hỗ trợ reactive function arity với nhiều input/output theo các kiểu tuple được hỗ trợ. Nếu yêu cầu là tách order và invoice thành hai output binding, cân nhắc function arity thay vì cố route từng item sang function bean bằng header.

Chọn theo mục tiêu: gọi service nội bộ, tạo hai publisher output hay gửi tới broker destination là ba yêu cầu khác nhau.

## 12. Spring Cloud Stream: bật RoutingFunction đúng cách

Spring Cloud Stream hỗ trợ event routing thông qua `RoutingFunction`. Để bật routing input qua function router:

~~~properties
spring.cloud.stream.function.routing.enabled=true
~~~

Khi bật, binding input của router có tên:

~~~text
functionRouter-in-0
~~~

Producer gửi message tới destination được bind cho `functionRouter-in-0`. Router có thể dùng `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression` trong message header hay application properties theo mô hình thực thi.

### 12.1. Imperative target: header từng message có tác dụng

~~~java
@Bean
Consumer<Integer> evenHandler() {
    return value -> log.info("EVEN: {}", value);
}

@Bean
Consumer<Integer> oddHandler() {
    return value -> log.info("ODD: {}", value);
}
~~~

Một message tới `functionRouter-in-0` có thể mang header:

~~~text
spring.cloud.function.routing-expression:
    payload % 2 == 0 ? 'evenHandler' : 'oddHandler'
~~~

Vì các consumer imperative nhận từng message, router có thể chọn `evenHandler` hoặc `oddHandler` theo từng event.

### 12.2. Reactive target: không dùng header để đổi target giữa các item

Nếu target là reactive function nhận `Flux<T>`, function được gọi một lần để nhận publisher. Routing instruction qua application property chọn target cho stream. Không kỳ vọng từng header trong publisher đổi target của RoutingFunction ở mỗi event.

### 12.3. Phân biệt các property

| Property | Tác dụng |
| --- | --- |
| `spring.cloud.stream.function.routing.enabled=true` | Bật event routing qua Stream RoutingFunction |
| `spring.cloud.function.definition` | Chỉ định function hoặc composition |
| `spring.cloud.function.routing-expression` | SpEL tạo function definition cần route |

`routing.enabled` bật cơ chế router trong Stream; nó không biến reactive routing thành per-message routing.

## 13. Spring Cloud Stream: routing TO khác routing FROM

Tài liệu Event Routing của Spring Cloud Stream phân biệt:

- **Routing TO Consumer:** chọn consumer/function xử lý message đến.
- **Routing FROM Consumer:** chọn destination nơi gửi message đầu ra.

### 13.1. Routing TO

Dùng RoutingFunction, header `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression`, hoặc application properties.

### 13.2. Routing FROM

Một function có thể trả `Message` chứa header:

~~~text
spring.cloud.stream.sendto.destination
~~~

Ví dụ:

~~~java
@Bean
Function<String, Message<String>> routeOutput() {
    return value -> MessageBuilder.withPayload(value)
        .setHeader(
            "spring.cloud.stream.sendto.destination",
            value.startsWith("order-") ? "orders-out" : "other-out"
        )
        .build();
}
~~~

Header này yêu cầu framework định tuyến **output message tới destination**. Nó không yêu cầu FunctionCatalog chọn function xử lý input.

Một ứng dụng reactive có thể không route từng event sang function khác bằng `spring.cloud.function.definition`, nhưng vẫn có thể cần gửi từng output message tới destination khác. Đây là hai bài toán riêng.

## 14. HTTP adapter: một request khác một publisher

Spring Cloud Function web adapter có thể chuyển HTTP headers thành message headers khi tạo message cho function. Với imperative function, header routing có thể được sử dụng để chọn target.

Nhưng nếu function đầu vào là reactive publisher, HTTP header:

~~~http
spring.cloud.function.definition: processOrders
~~~

không làm router đọc một header mới cho từng phần tử trong body stream. Application property là nguồn routing instruction dành cho reactive function.

### 14.1. Một HTTP request chứa nhiều event

Ví dụ request gửi một JSON array:

~~~json
[
  {"eventType":"ORDER","eventId":"E-1","body":"..."},
  {"eventType":"INVOICE","eventId":"E-2","body":"..."}
]
~~~

Adapter có thể chuyển request thành publisher hoặc payload collection tùy mapping và signature. Không mặc định mỗi phần tử array trở thành một invocation độc lập của RoutingFunction.

Nếu cần route từng item, xác nhận request binding tạo `Flux<Message<DomainEvent>>` hay `Flux<DomainEvent>`, rồi phân nhánh bên trong function.

### 14.2. Nhiều request độc lập khác nhiều event trong một publisher

Nếu mỗi HTTP request tạo một imperative invocation riêng, header của từng request có thể chọn target khác nhau. Nếu một request chứa reactive body stream, routing decision áp dụng cho stream đó.

Cần phân biệt **nhiều request độc lập** với **nhiều event trong một publisher**.

## 15. Serverless: event batch không tự động trở thành per-message routing

Serverless adapter có thể nhận một event đơn hoặc batch. Batch có thể được biểu diễn thành envelope hoặc collection tùy adapter/platform.

Các câu hỏi cần xác minh:

1. Handler nhận một event hay một batch?
2. Adapter gọi imperative function một lần cho từng record hay reactive function một lần với publisher?
3. Routing instruction nằm ở event envelope, message headers hay application properties?
4. Business function có nhận từng record như `Message<T>` không?
5. Retry áp dụng cho toàn batch hay từng record?
6. Nếu một record lỗi, các record còn lại có tiếp tục không?

Không suy từ tên nền tảng “serverless” rằng routing luôn theo từng event. Đơn vị công việc do adapter và function signature quyết định.

Nếu adapter đưa batch thành `Flux<Message<DomainEvent>>`, dùng reactive dispatcher như mục 9. Nếu adapter gọi function imperative từng record, có thể dùng `MessageRoutingCallback` hoặc routing headers. Kiểm tra đúng adapter/version trước khi chọn giải pháp.

## 16. Vì sao routing header có thể bị mất trước cả router?

Ngoài giới hạn reactive, header có thể không đến đúng ranh giới:

- Producer không gửi header.
- Broker/binder không propagate custom header theo cấu hình.
- HTTP adapter không copy header do mapping hoặc allowlist.
- Header bị đổi tên, ép kiểu hoặc bị loại bỏ.
- Function trước đó tạo Message mới nhưng không copy header cần thiết.
- Custom converter chỉ trả payload và không giữ metadata.
- Router không phải entry function thực sự được gọi.

### 16.1. Header không mặc định luôn được propagate

Nếu function nhận `Message<T>` và trả `Message<R>`, nó có thể copy headers có chọn lọc:

~~~java
@Bean
Function<Message<OrderEvent>, Message<NormalizedOrder>> normalize() {
    return message -> MessageBuilder
        .withPayload(normalizeOrder(message.getPayload()))
        .setHeader(
            "correlationId",
            message.getHeaders().get("correlationId")
        )
        .setHeader(
            "eventType",
            message.getHeaders().get("eventType")
        )
        .build();
}
~~~

Nếu trả `Message`, framework xử lý payload conversion theo contract nhưng không tự đảm bảo mọi input header được truyền sang output. Chỉ giữ những header cần thiết và hợp lệ cho bước tiếp theo.

### 16.2. Đừng copy routing header không cần thiết

Nếu message đã đi qua router, việc giữ lại `spring.cloud.function.definition` có thể khiến bước sau hoặc adapter khác hiểu nhầm rằng vẫn cần route theo instruction cũ. Chỉ propagate routing header nếu downstream contract thật sự yêu cầu.

### 16.3. Kiểm tra runtime headers

~~~java
messages.doOnNext(message ->
    log.debug(
        "eventId={}, eventType={}, routeHeader={}",
        message.getHeaders().get("eventId"),
        message.getHeaders().get("eventType"),
        message.getHeaders().get("spring.cloud.function.definition")
    )
);
~~~

Không log payload đầy đủ hoặc header chứa token/PII. Dùng ID đã được phép, tên header cần chẩn đoán và loại payload.

## 17. Routing expression và bảo mật

`spring.cloud.function.routing-expression` sử dụng SpEL để tạo function definition. Routing expression có thể thay đổi function được gọi, vì vậy phải kiểm soát nguồn dữ liệu.

### 17.1. Header từ bên ngoài là dữ liệu không tin cậy

Nếu HTTP client hoặc producer có thể đặt:

~~~text
spring.cloud.function.definition
spring.cloud.function.routing-expression
~~~

caller có thể thử chọn function ngoài phạm vi nghiệp vụ. Không để external caller tùy ý gọi function quản trị hoặc nội bộ.

### 17.2. SimpleEvaluationContext và application properties

Tài liệu SCF hiện hành phân biệt:

- Expression đến từ Message header được đánh giá bằng `SimpleEvaluationContext`, giới hạn khả năng thực thi so với SpEL context đầy đủ.
- Expression từ application property/system environment được đánh giá bằng `StandardEvaluationContext`.

Giới hạn context không thay thế authorization. Cần allowlist function target, bảo vệ actuator/config endpoints và giới hạn caller có thể gửi routing header.

### 17.3. Mapping an toàn

~~~java
@Bean
MessageRoutingCallback safeRouter() {
    Set<String> allowed = Set.of("processOrder", "processInvoice");

    return new MessageRoutingCallback() {
        @Override
        public String routingResult(Message<?> message) {
            String requested =
                message.getHeaders().get("target", String.class);

            if (!allowed.contains(requested)) {
                throw new IllegalArgumentException(
                    "Unsupported routing target: " + requested
                );
            }

            return requested;
        }
    };
}
~~~

Ví dụ minh họa allowlist tên function. Trong hệ thống thật, cần xác thực caller/capability trước khi cho phép target và không để header tự quyết định quyền truy cập.

Với reactive dispatch bên trong `Flux`, dùng switch/allowlist như mục 9, đồng thời kiểm tra quyền theo tenant/event nếu business rules yêu cầu.

## 18. Unroutable message: target không có trong catalog

Nếu router nhận definition không có trong `FunctionCatalog`, framework có thể ném exception cho message không route được.

Spring Cloud Function cung cấp strategy `DefaultMessageRoutingHandler` để xử lý message không route được. Default behavior được tài liệu mô tả là log và cho luồng tiếp tục, về thực tế có thể drop message không route được; ứng dụng có thể đăng ký implementation riêng.

~~~java
@Bean
DefaultMessageRoutingHandler routingFailureHandler() {
    return new DefaultMessageRoutingHandler() {
        @Override
        public void accept(Message<?> message) {
            log.warn(
                "Unroutable message eventId={}",
                message.getHeaders().get("eventId")
            );
            deadLetterPublisher.publish(message);
        }
    };
}
~~~

Đây là ví dụ định hướng; API/constructor/import cần đối chiếu version SCF đang dùng. Không dùng handler để âm thầm bỏ event nghiệp vụ quan trọng.

Ba tình huống cần phân biệt:

- **Unroutable:** router đã nhận routing instruction nhưng target không có hoặc không resolve được.
- **Reactive header không có tác dụng:** router không dùng header từng item làm routing instruction per-message cho publisher.
- **Header bị mất:** adapter/binder/function không truyền header tới đúng ranh giới.

## 19. Quy trình chẩn đoán theo thứ tự

~~~mermaid
flowchart TD
    START["Routing header không đổi target"] --> SIG{"Function input là Message hay Publisher?"}
    SIG -->|Message<T>| IMP["Imperative: kiểm tra RoutingFunction"]
    SIG -->|Flux/Publisher<T>| REACT["Reactive: header không route từng item"]
    IMP --> ENABLE{"Router/adapter đã bật và được gọi?"}
    ENABLE -->|Không| ROUTER["Bật routing hoặc gọi functionRouter"]
    ENABLE -->|Có| HEADER{"Header có tới router?"}
    HEADER -->|Không| PROP["Kiểm tra producer, binder, adapter, header propagation"]
    HEADER -->|Có| PRIORITY{"Có MessageRoutingCallback?"}
    PRIORITY -->|Có| CALLBACK["Callback ưu tiên hơn header"]
    PRIORITY -->|Không| TARGET["Kiểm tra definition, expression, target name"]
    REACT --> APP["Dùng application property cho toàn stream"]
    REACT --> BRANCH["Nếu cần từng item: phân nhánh trong Flux"]
    APP --> VERIFY["Test target thực tế"]
    BRANCH --> VERIFY
    ROUTER --> VERIFY
    PROP --> VERIFY
    CALLBACK --> VERIFY
    TARGET --> VERIFY
~~~

### 19.1. Checklist điều tra

1. Đọc chữ ký function thực tế: `Function<T,R>` hay `Function<Flux<T>,Flux<R>>`?
2. Xác định adapter gọi function một lần hay mỗi event.
3. Xác nhận request/message thực sự đi qua `functionRouter`.
4. Nếu imperative, kiểm tra header đặc biệt đúng tên và đúng kiểu.
5. Kiểm tra `MessageRoutingCallback` có được đăng ký không.
6. Kiểm tra callback có ưu tiên và ghi đè header không.
7. Kiểm tra header có đến router hay bị mất ở broker/adapter.
8. Nếu reactive, đọc application property hiệu lực.
9. Nếu cần route từng item, thêm logic branch trong reactive function.
10. Kiểm tra function target tồn tại trong catalog.
11. Kiểm tra SpEL expression trả đúng definition.
12. Kiểm tra security/allowlist và unroutable behavior.
13. Test một message imperative, rồi test một publisher có nhiều event.
14. Test output, error, ordering, backpressure và side effects.

## 20. Quan sát routing configuration hiệu lực

Cấu hình trong `application.yml` có thể bị profile, environment variable hoặc command-line argument ghi đè.

~~~java
@Component
class RoutingConfigurationInspector implements ApplicationRunner {

    private final Environment environment;
    private final FunctionCatalog catalog;

    RoutingConfigurationInspector(
            Environment environment,
            FunctionCatalog catalog) {
        this.environment = environment;
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("function.definition={}",
            environment.getProperty(
                "spring.cloud.function.definition", "<unset>"
            ));

        log.info("function.routing-expression={}",
            environment.getProperty(
                "spring.cloud.function.routing-expression", "<unset>"
            ));

        log.info("catalog.names={}", catalog.getNames(null));
    }
}
~~~

Chỉ bật inspector khi cần chẩn đoán hoặc dùng log level phù hợp. Không in toàn bộ environment vì có thể chứa secret.

### 20.1. Với Stream, kiểm tra routing enabled và binding

~~~properties
spring.cloud.stream.function.routing.enabled=true
~~~

Và xác minh input binding:

~~~text
functionRouter-in-0
~~~

Nếu app đang bind trực tiếp `processOrders-in-0`, message có thể đi thẳng tới reactive function và không đi qua RoutingFunction như bạn nghĩ.

## 21. Test imperative routing: header chọn target theo từng message

~~~java
@Bean
MessageRoutingCallback routeByType() {
    return new MessageRoutingCallback() {
        @Override
        public String routingResult(Message<?> message) {
            String type =
                message.getHeaders().get("eventType", String.class);

            return switch (type == null ? "" : type) {
                case "ORDER" -> "orderHandler";
                case "INVOICE" -> "invoiceHandler";
                default -> throw new IllegalArgumentException(
                    "Unsupported eventType: " + type
                );
            };
        }
    };
}

@Bean
Consumer<OrderEvent> orderHandler() {
    return event -> orderService.process(event);
}

@Bean
Consumer<InvoiceEvent> invoiceHandler() {
    return event -> invoiceService.process(event);
}
~~~

Đây là ví dụ imperative routing. Để test đầy đủ, cấu hình test cần gọi `functionRouter` với từng `Message<?>` riêng và xác minh handler tương ứng được gọi. Vì callback có ưu tiên cao hơn header/application property, test callback cũng phải xác nhận behavior đó.

Test hai message độc lập:

- Message A có `eventType=ORDER`.
- Message B có `eventType=INVOICE`.
- Gọi router riêng cho từng message.
- Xác minh A tới `orderHandler`, B tới `invoiceHandler`.

Đừng gộp A và B vào một `Flux` rồi dùng test này để kết luận reactive routing per-message hoạt động.

## 22. Test reactive dispatch: mỗi item đi đúng nhánh trong Flux

~~~java
class ReactiveDispatchTest {

    @Autowired
    @Qualifier("dispatchEvents")
    Function<Flux<Message<InboundEvent>>, Flux<RoutedResult>> dispatchEvents;

    @Test
    void routesEachMessageInsideTheStream() {
        InboundEvent order =
            new InboundEvent("E-1", "order body");

        InboundEvent invoice =
            new InboundEvent("E-2", "invoice body");

        Message<InboundEvent> orderMessage =
            MessageBuilder.withPayload(order)
                .setHeader("eventType", "ORDER")
                .build();

        Message<InboundEvent> invoiceMessage =
            MessageBuilder.withPayload(invoice)
                .setHeader("eventType", "INVOICE")
                .build();

        StepVerifier.create(
                dispatchEvents.apply(
                    Flux.just(orderMessage, invoiceMessage)
                )
            )
            .expectNextMatches(result ->
                result.eventId().equals("E-1")
                    && result.handler().equals("ORDER")
            )
            .expectNextMatches(result ->
                result.eventId().equals("E-2")
                    && result.handler().equals("INVOICE")
            )
            .verifyComplete();
    }
}
~~~

Test này chứng minh **logic dispatch bên trong Flux** dựa trên header từng item. Nó không kiểm tra built-in RoutingFunction và không chứng minh header có thể đổi reactive function target per-message.

### 22.1. Test event không được hỗ trợ

~~~java
StepVerifier.create(
        dispatchEvents.apply(Flux.just(unsupportedMessage))
    )
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
    )
    .verify();
~~~

Trong hệ thống thực tế, có thể chọn dead-letter/discard policy thay vì kết thúc cả stream. Chính sách phải được thiết kế rõ, nhất là khi một item lỗi có thể làm publisher terminate.

## 23. Test routing toàn stream bằng application properties

Để kiểm tra reactive routing của SCF, test phải cấu hình application property trước khi context được tạo:

~~~properties
spring.cloud.function.definition=processOrders
~~~

Sau đó gửi một publisher có nhiều event vào reactive function đã chọn. Kỳ vọng tất cả event của publisher được xử lý bởi target `processOrders`.

Nếu thay property thành:

~~~properties
spring.cloud.function.definition=processInvoices
~~~

toàn publisher được chuyển tới `processInvoices`.

Đây là routing **theo stream**, không phải routing theo từng message header.

Không thay property giữa các item. Application properties là cấu hình của application context/runtime, không phải metadata riêng cho từng item. Thay system property theo từng event tạo shared mutable state và race condition. Nếu cần nhiều target đồng thời, hãy phân nhánh trong pipeline hoặc tách stream/binding.

## 24. Test Spring Cloud Stream event routing

Với Spring Cloud Stream, test cần xác minh ba điều:

1. `spring.cloud.stream.function.routing.enabled=true` được bật khi muốn dùng `functionRouter`.
2. Input message đến binding `functionRouter-in-0`.
3. Routing instruction được cung cấp đúng cách theo loại target.

### 24.1. Imperative event routing

Gửi từng message riêng với header routing phù hợp và xác minh consumer tương ứng nhận event.

### 24.2. Reactive function

Nếu target là reactive function, cấu hình application property để chọn target toàn stream. Không gửi nhiều header khác nhau trong các item rồi mong RoutingFunction chọn lại target ở từng event.

### 24.3. Routing FROM

Nếu mục tiêu là đưa output của từng event đến broker destination khác nhau, kiểm tra `spring.cloud.stream.sendto.destination` và output binding semantics. Đó là route FROM, không phải chọn reactive function theo input header.

## 25. Test HTTP adapter: một request khác một publisher

Khi HTTP adapter chuyển header thành message header, test imperative endpoint có thể gửi:

~~~http
POST /functionRouter
Content-Type: application/json
spring.cloud.function.definition: processOrder
~~~

Tên path thực tế phụ thuộc web adapter configuration và function export. Đừng mặc định `/functionRouter` là path luôn được mở; xác minh route của ứng dụng.

Với reactive endpoint nhận body dạng stream:

- Routing target được chọn ở cấp stream theo application property.
- Header của từng record trong body không làm SCF chọn target mới cho record đó.
- Nếu cần per-record dispatch, hãy xử lý bên trong `Flux` như mục 9.

## 26. Test serverless adapter

Trong serverless, test cần tái hiện đúng input shape của runtime:

- Một invocation chứa một event.
- Một invocation chứa batch nhiều record.
- Một invocation tạo reactive publisher.
- Event envelope chứa body nested.
- Header routing được adapter map thành Spring Message header hay không.

Không kết luận per-message routing chỉ từ test một invocation/one event. Nếu runtime gửi batch, xác minh adapter có gọi imperative function từng record hay chuyển một publisher cho reactive function.

## 27. Những lỗi thường gặp và cách diễn giải

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| Header definition có trong log nhưng target không đổi | Reactive function nhận publisher | Chữ ký Flux/Publisher |
| routing-expression header bị bỏ qua | Reactive routing không dùng per-message header | Unit of work |
| Callback không chạy cho từng event | Function reactive | MessageRoutingCallback chỉ dùng imperative routing |
| Mọi item trong Flux vào cùng function | Routing property chọn toàn stream | Effective application properties |
| Header không xuất hiện trong Message | Adapter/binder không propagate | Log headers tại ingress |
| Router không được gọi | Input bind trực tiếp vào business function | Binding name/destination |
| Target không tồn tại | Definition typo hoặc bean không đăng ký | catalog.getNames(null) |
| Header route bị ghi đè | Callback có ưu tiên cao hơn trong imperative path | Callback bean |
| SpEL route không chọn target | Expression sai hoặc header value không đúng | Expression result/log |
| Message bị drop | Unroutable handler/default behavior | Routing handler và logs |
| Output tới sai topic | Nhầm route TO và route FROM | sendto.destination vs function routing |
| HTTP request không route | Header không được web adapter map hoặc route path sai | Web adapter config |
| Batch serverless chỉ chạy một target | Adapter chuyển cả batch thành publisher | Handler signature/event shape |

## 28. Những hiểu nhầm phổ biến

| Hiểu nhầm | Sự thật |
| --- | --- |
| “Có header spring.cloud.function.definition là luôn route theo từng event.” | Chỉ đúng cho imperative message routing; reactive route cả stream bằng application properties. |
| “Flux<Message<T>> không có headers.” | Từng phần tử có thể là Message; built-in router không dùng chúng để route từng item trong reactive stream. |
| “MessageRoutingCallback chạy một lần cho mỗi item trong Flux.” | Callback thuộc imperative routing. |
| “Bật spring.cloud.stream.function.routing.enabled là giải quyết reactive per-message routing.” | Nó bật RoutingFunction; không đổi unit of work reactive. |
| “definition header và property giống nhau.” | Header gắn với message; property là cấu hình cấp application. |
| “Đổi sang routing-expression thay definition sẽ route được.” | Cả hai đều không cung cấp per-message routing cho reactive function. |
| “Có thể đặt system property khác nhau cho từng item.” | Shared mutable config gây race condition; không phải thiết kế per-event routing. |
| “Nếu header nằm trong payload JSON thì router tự đọc được.” | Router vẫn nhận publisher; business function phải đọc payload trong stream. |
| “spring.cloud.stream.sendto.destination chọn function đích.” | Nó định tuyến output message tới destination. |
| “Routing và composition là một.” | Composition ghép các bước tuần tự; routing chọn target. |
| “Mỗi request HTTP đều là một item reactive.” | Một request có thể tạo publisher chứa nhiều item. |
| “Serverless luôn gọi function một lần cho từng record.” | Phụ thuộc handler/adapter và event batching. |
| “Không route được là do header sai tên.” | Có thể do reactive unit of work, callback precedence, adapter hoặc router không được gọi. |
| “Mọi expression header đều được đánh giá như application property.” | Header expression dùng evaluation context hạn chế hơn. |
| “Nếu target không có, message luôn bị reject.” | Có thể cấu hình DefaultMessageRoutingHandler để xử lý unroutable message, kể cả drop. |

## 29. Checklist chọn kiến trúc phù hợp

### 29.1. Nếu cần routing per-message

- [ ] Function/Consumer imperative nhận một `Message<T>` mỗi lần gọi.
- [ ] Message đi qua `functionRouter`.
- [ ] `spring.cloud.stream.function.routing.enabled` được bật nếu dùng Stream Event Routing.
- [ ] Header routing có đúng tên và giá trị.
- [ ] `MessageRoutingCallback` không ghi đè ngoài ý muốn.
- [ ] Target có trong FunctionCatalog.
- [ ] Routing target có allowlist và authorization.

### 29.2. Nếu cần routing toàn reactive stream

- [ ] Function signature nhận `Flux<T>`/`Publisher<T>`.
- [ ] `spring.cloud.function.definition` hoặc `routing-expression` được cấu hình ở application level.
- [ ] Profile/environment của instance chọn đúng target.
- [ ] Integration test xác minh toàn publisher đi vào target đã chọn.
- [ ] Không kỳ vọng header của từng item đổi target.

### 29.3. Nếu cần mỗi event trong Flux đi một nhánh

- [ ] Reactive function nhận `Flux<Message<T>>` nếu cần headers, hoặc payload DTO có event type.
- [ ] Branch logic được đặt bên trong `map`, `flatMap`, `concatMap` hoặc operator phù hợp.
- [ ] Các handler/service có input/output type rõ.
- [ ] Quy tắc ordering/concurrency được xác định.
- [ ] Event không hợp lệ có dead-letter/reject policy.
- [ ] Test bằng `StepVerifier` với nhiều loại event trong cùng publisher.
- [ ] Test adapter thật để xác nhận headers/payload đến đúng.

## 30. Câu hỏi tự đánh giá

1. Đơn vị công việc của imperative function là gì?
2. Đơn vị công việc của reactive function là gì?
3. Vì sao `Function<Flux<Message<T>>,Flux<R>>` không được route từng item bằng built-in routing header?
4. Header vẫn có thể được đọc ở đâu trong reactive function?
5. Hai header routing chính của Spring Cloud Function là gì?
6. `spring.cloud.function.definition` header khác application property cùng tên ở đâu?
7. `spring.cloud.function.routing-expression` có vai trò gì?
8. Vì sao `MessageRoutingCallback` phù hợp imperative routing?
9. Thứ tự ưu tiên giữa callback, message header và application property trong imperative routing là gì?
10. Với reactive function, nguồn routing instruction nào được sử dụng?
11. Bật `spring.cloud.stream.function.routing.enabled=true` có thay đổi giới hạn reactive không?
12. Binding input của RoutingFunction trong Spring Cloud Stream tên gì?
13. Làm sao route từng item trong Flux dựa trên `eventType` header?
14. `concatMap` và `flatMap` khác nhau thế nào về ordering/concurrency?
15. Vì sao không nên thay system property giữa các item để đổi target?
16. `spring.cloud.stream.sendto.destination` là route TO hay route FROM?
17. Một HTTP request chứa JSON array khác gì nhiều request imperative độc lập?
18. Adapter serverless có thể làm thay đổi đơn vị công việc ra sao?
19. Vì sao header có thể mất trước khi tới RoutingFunction?
20. `DefaultMessageRoutingHandler` giúp xử lý trường hợp nào?
21. Vì sao SpEL header expression vẫn cần allowlist/authorization?
22. Bạn sẽ viết test nào để chứng minh per-item dispatch trong Flux?
23. Bạn sẽ test gì để chứng minh application property chọn toàn stream?
24. Làm thế nào phân biệt routing không chạy do reactive semantics với router không được gọi?

## 31. Tài liệu tham khảo

- [Spring Cloud Function — Programming Model, Function Routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — phân biệt imperative và reactive unit of work, routing bằng Message headers, `MessageRoutingCallback`, application properties và thứ tự ưu tiên.
- [Spring Cloud Stream — Event Routing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html) — bật `spring.cloud.stream.function.routing.enabled`, binding `functionRouter-in-0`, routing TO Consumer, callback và routing FROM Consumer.
- [Spring Cloud Function — Function Catalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — cách functional beans được đăng ký và wrapper của FunctionCatalog.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — publisher lifecycle, operator, subscription, backpressure và xử lý stream.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` để kiểm tra reactive routing logic.
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — tên input/output binding theo function và router.

Các ví dụ dùng Java 17+, Spring Cloud Function 5.1.0 và Spring Cloud Stream 5.1.0 reference hiện hành. API/adapter cụ thể có thể khác theo BOM, binder và phiên bản đã triển khai; hãy kiểm tra chữ ký function và đường ingress thực tế trước khi kết luận.

**Ghi nhớ:** Routing header không route từng event bên trong reactive publisher vì reactive function được gọi một lần với **toàn bộ stream**. Header vẫn có thể nằm trong từng `Message` và được đọc trong Reactor pipeline, nhưng built-in `RoutingFunction` không chọn lại target theo từng item. Dùng application property để chọn **một target cho cả stream**; nếu cần từng event đi nhánh riêng, phân nhánh trong `Flux` bằng logic có kiểu rõ, hoặc dùng imperative function để mỗi message là một đơn vị routing. Phân biệt routing TO với `sendto.destination` route FROM, kiểm tra adapter/binding, và test nhiều event trong cùng publisher bằng `StepVerifier`.
