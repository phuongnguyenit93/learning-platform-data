# Giới hạn định tuyến theo từng thông điệp với mô hình phản ứng

Spring Cloud Function có thể định tuyến một message đến function phù hợp dựa trên header hoặc biểu thức SpEL. Cơ chế này hoạt động theo từng message với function imperative như `Function<OrderEvent, Result>`. Tuy nhiên, khi dùng function reactive như `Function<Flux<OrderEvent>, Flux<Result>>`, đơn vị xử lý của function là toàn bộ Publisher. Framework gọi function một lần để chuyển `Flux` vào; Reactor xử lý các phần tử sau đó. Vì vậy, header của từng phần tử không thể yêu cầu Spring Cloud Function chọn một function bean khác cho riêng phần tử đó.

Giới hạn này không có nghĩa reactive stream không thể phân nhánh từng phần tử. Ứng dụng vẫn có thể dùng `filter`, `flatMap`, `groupBy` hoặc một bảng handler để định tuyến từng event bên trong pipeline Reactor. Điều cần phân biệt là **định tuyến function ở cấp FunctionCatalog** và **định tuyến dữ liệu ở bên trong reactive pipeline**. Chọn đúng tầng giúp tránh thiết kế sai, đồng thời giữ được backpressure, xử lý lỗi và thứ tự message theo yêu cầu.

## 1. Hai đơn vị xử lý khác nhau

Với function imperative, framework gọi hàm một lần cho mỗi message. Vì vậy, mỗi message có thể mang header chỉ định function đích:

```java
@Bean
Function<OrderEvent, ProcessingResult> processOrder() {
    return event -> orderService.process(event);
}
```

Với function reactive, framework gọi hàm để cung cấp một Publisher. Sau đó các operator của Reactor xử lý từng phần tử khi có subscription:

```java
@Bean
Function<Flux<OrderEvent>, Flux<ProcessingResult>> processOrders() {
    return events -> events.map(orderService::process);
}
```

| Đặc điểm | Function imperative | Function reactive |
|---|---|---|
| Chữ ký ví dụ | `Function<OrderEvent, Result>` | `Function<Flux<OrderEvent>, Flux<Result>>` |
| Số lần framework gọi hàm | Một lần cho mỗi message | Một lần để chuyển Publisher |
| Đơn vị công việc | Một message | Toàn bộ stream/Publisher |
| Định tuyến bằng header của từng message | Có thể | Không dùng để chọn function bean theo từng phần tử |
| Phân nhánh từng phần tử | Trong logic của hàm | Trong pipeline Reactor |
| Cấu hình route bằng application properties | Có | Có; route áp dụng cho toàn stream |

Đây là điểm cốt lõi của bài học. Reactive không phải là imperative được gọi nhanh hơn; lifecycle và ranh giới invocation khác nhau. Không thể giả định router sẽ được gọi lại cho từng `Message` bên trong `Flux`.

## 2. Định tuyến từng message với function imperative

Spring Cloud Function đăng ký `RoutingFunction` trong `FunctionCatalog` dưới tên `functionRouter`. Khi dùng routing, có thể chọn function đích qua một trong các cơ chế sau:

- Header `spring.cloud.function.definition`: tên một function hoặc một composition, ví dụ `validateOrder|processOrder`.
- Header `spring.cloud.function.routing-expression`: biểu thức SpEL trả về tên function/composition cần gọi.
- `MessageRoutingCallback`: bean chiến lược quyết định function definition từ message.
- Application properties: `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression`, áp dụng cho function được chọn ở cấp ứng dụng.

Ví dụ cấu hình kích hoạt router:

```yaml
spring:
  cloud:
    function:
      definition: functionRouter
```

Producer gửi message với function definition:

```java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader("spring.cloud.function.definition", "validateOrder|acceptOrder")
    .build();

streamBridge.send("orders-out-0", message);
```

Trong ví dụ, producer gửi qua output binding `orders-out-0`; consumer nhận message từ input binding tương ứng và router có thể chọn composition `validateOrder|acceptOrder` cho message đó. Cần cấu hình binding và đường gửi/nhận đúng với kiến trúc ứng dụng; ví dụ chỉ tập trung vào metadata định tuyến. Tên function phải tồn tại trong `FunctionCatalog` và các chữ ký phải ghép được với nhau.

Với biểu thức động, header `spring.cloud.function.routing-expression` có thể tham chiếu payload và headers của message:

```java
Message<OrderEvent> message = MessageBuilder
    .withPayload(event)
    .setHeader(
        "spring.cloud.function.routing-expression",
        "headers['eventType'] == 'ORDER_CREATED' ? 'createOrder' : 'cancelOrder'")
    .build();
```

Ở function imperative, biểu thức được đánh giá trên từng message nên có thể chọn function khác nhau theo `eventType`. Không đặt một chuỗi biểu thức tùy ý từ người dùng bên ngoài vào header. Hãy kiểm tra giá trị route theo danh sách cho phép và chỉ công bố những function được phép gọi.

## 3. Thứ tự ưu tiên của routing instruction

Khi nhiều cơ chế cùng cung cấp route, Spring Cloud Function áp dụng thứ tự ưu tiên cho function imperative:

1. `MessageRoutingCallback` có ưu tiên cao nhất.
2. Message headers được dùng nếu không có callback quyết định route.
3. Application properties là nguồn cấu hình tiếp theo và cũng là cơ chế dùng được với reactive function.

Nếu route trỏ đến function không tồn tại trong `FunctionCatalog`, message trở thành unroutable. Spring Cloud Function cung cấp `DefaultMessageRoutingHandler` để tùy biến hành vi; implementation mặc định ghi log rồi cho luồng tiếp tục, về thực tế message không định tuyến được sẽ bị bỏ qua. Nếu dữ liệu nghiệp vụ cần được bảo toàn, hãy đăng ký handler riêng để ghi nhận, chuyển sang luồng lỗi/DLQ hoặc từ chối có kiểm soát. Không dựa vào log mặc định như một cơ chế lưu giữ message.

## 4. Giới hạn routing header với reactive function

Giả sử input binding nhận một `Flux<Message<OrderEvent>>`. Mỗi message có header `spring.cloud.function.definition`:

```text
Message 1: spring.cloud.function.definition = createOrder
Message 2: spring.cloud.function.definition = cancelOrder
Message 3: spring.cloud.function.definition = createOrder
```

Với một function imperative, router có thể chọn `createOrder`, `cancelOrder`, rồi `createOrder` theo thứ tự từng message. Nhưng với một reactive function, Spring Cloud Function gọi function một lần để chuyển Publisher vào. Các header nằm trên từng phần tử của Publisher không được dùng để thay đổi function bean đích cho từng phần tử.

Nếu cung cấp `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression` dưới dạng application properties, route đó được áp dụng ở cấp function/stream. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: processOrders
```

`processOrders` được chọn cho toàn stream. Không thể kỳ vọng một message bên trong `Flux` đổi route của những message còn lại bằng cách đặt routing header riêng. Đây là hệ quả của unit of work: toàn Publisher là đầu vào của một lần invocation.

Nếu yêu cầu nghiệp vụ là mỗi event trong cùng một stream phải được xử lý bởi handler khác nhau, hãy đưa logic phân nhánh vào function reactive thay vì dựa vào `RoutingFunction` để đổi function bean cho từng phần tử.

## 5. Định tuyến từng phần tử bên trong Flux

Một cách phổ biến là dùng `flatMap` để tra cứu handler theo loại event. Function vẫn được gọi một lần với Publisher, nhưng operator xử lý và chọn handler cho từng message:

```java
public interface OrderEventHandler {
    Mono<ProcessingResult> handle(OrderEvent event);
}

@Bean
Function<Flux<Message<OrderEvent>>, Flux<Message<ProcessingResult>>> routeOrders(
        Map<String, OrderEventHandler> handlers) {

    return messages -> messages.flatMap(message -> {
        String eventType = message.getHeaders().get("eventType", String.class);
        OrderEventHandler handler = handlers.get(eventType);

        if (handler == null) {
            return Mono.error(new UnsupportedEventTypeException(eventType));
        }

        return handler.handle(message.getPayload())
            .map(result -> MessageBuilder.withPayload(result)
                .setHeader("correlationId", message.getHeaders().get("correlationId"))
                .setHeader("sourceEventId", message.getHeaders().get("eventId"))
                .build());
    });
}
```

Trong ví dụ:

- `routeOrders` nhận toàn bộ `Flux` trong một lần invocation.
- `flatMap` áp dụng logic cho từng `Message<OrderEvent>` khi phần tử đi qua pipeline.
- `eventType` chọn một handler từ map đã được đăng ký trong ứng dụng.
- Handler trả `Mono<ProcessingResult>` để tích hợp xử lý bất đồng bộ.
- Kết quả được bọc thành message mới và chỉ giữ lại metadata cần thiết.

Đây là định tuyến ở tầng dữ liệu trong Reactor, không phải Spring Cloud Function routing theo tên bean. Map handler nên được xây dựng từ các bean được phép gọi; không dùng tên class hoặc bean tùy ý lấy từ message để khởi tạo đối tượng hay gọi bất kỳ bean nào trong application context.

Nếu các handler là thao tác đồng bộ, tránh gọi trực tiếp tác vụ blocking trên Reactor event-loop. Hãy dùng API non-blocking hoặc cô lập công việc blocking bằng scheduler phù hợp. Nếu cần giữ thứ tự nghiêm ngặt theo từng message, xem xét `concatMap`; nếu cần song song nhưng vẫn giữ thứ tự phát kết quả, xem xét `flatMapSequential`.

## 6. Chọn operator theo yêu cầu định tuyến

| Operator | Hành vi | Khi phù hợp |
|---|---|---|
| `filter` | Giữ hoặc loại phần tử theo điều kiện | Chỉ cho event thỏa điều kiện đi tiếp |
| `map` | Biến đổi đồng bộ từng phần tử | Phân loại hoặc chuẩn hóa dữ liệu nhẹ |
| `flatMap` | Chuyển từng phần tử thành Publisher và hợp nhất kết quả, có thể chạy đồng thời | Gọi handler bất đồng bộ, chấp nhận thứ tự kết quả thay đổi |
| `concatMap` | Xử lý từng Publisher tuần tự | Cần giữ thứ tự xử lý đầu vào |
| `flatMapSequential` | Xử lý đồng thời nhưng phát kết quả theo thứ tự đầu vào | Cần thông lượng và thứ tự output ổn định |
| `groupBy` | Chia stream thành các nhóm theo khóa | Xử lý theo event type, tenant hoặc aggregate key |

Ví dụ lọc các event loại `ORDER_CREATED` trước khi chuyển đổi:

```java
@Bean
Function<Flux<Message<OrderEvent>>, Flux<OrderCreated>> onlyCreatedOrders() {
    return messages -> messages
        .filter(message -> "ORDER_CREATED".equals(
            message.getHeaders().get("eventType")))
        .map(Message::getPayload)
        .cast(OrderCreated.class);
}
```

`filter` loại các phần tử không phù hợp khỏi nhánh này. Nếu cần bảo toàn hoặc kiểm toán event bị loại, hãy gửi chúng sang nhánh khác hoặc ghi nhận lý do loại; đừng coi `filter` là DLQ tự động.

## 7. Tách nhiều luồng output từ một reactive function

Nếu mục tiêu là phân loại các event thành nhiều output binding, Spring Cloud Function hỗ trợ function arity cho reactive function. Ví dụ một function có thể trả tuple chứa hai `Flux`:

```java
@Bean
Function<Flux<IncomingEvent>, Tuple2<Flux<OrderEvent>, Flux<InvoiceEvent>>> splitEvents() {
    return events -> {
        // Tạo hai Publisher output theo cơ chế fan-out phù hợp với nguồn stream.
        Flux<OrderEvent> orders = orderStreamFrom(events);
        Flux<InvoiceEvent> invoices = invoiceStreamFrom(events);
        return Tuples.of(orders, invoices);
    };
}
```

Function arity cho reactive function cho phép framework suy ra số lượng input/output binding từ tuple. Với ví dụ trên, output binding lần lượt là `splitEvents-out-0` và `splitEvents-out-1`. Cấu hình destination tương ứng:

```yaml
spring:
  cloud:
    function:
      definition: splitEvents
    stream:
      bindings:
        splitEvents-out-0:
          destination: orders.events
        splitEvents-out-1:
          destination: invoices.events
```

Đây là khung minh họa chữ ký function arity; `orderStreamFrom` và `invoiceStreamFrom` đại diện cho logic phân nhánh của ứng dụng. Khi tạo hai output từ cùng một Publisher, phải thiết kế fan-out và subscription phù hợp để không vô tình subscribe nguồn không thể phát lại hai lần hoặc làm mất phần tử khi output subscriber khởi động lệch thời điểm. Function arity của Spring Cloud Function tập trung vào reactive function và các use case xử lý nhiều input/output stream; nó không biến routing header của từng phần tử thành lệnh chọn function bean.

Nếu mỗi event chỉ được gửi đến đúng một output, hãy bảo đảm logic phân loại là loại trừ lẫn nhau. Nếu hai nhánh cùng nhận một event, đó là fan-out có chủ đích và có thể tạo hai side effect. Cần kiểm thử số lượng message ở từng output và hành vi khi một nhánh lỗi.

## 8. Backpressure, concurrency và thứ tự

Định tuyến từng phần tử trong reactive stream cần giữ được khả năng điều tiết tốc độ. `flatMap` có thể xử lý nhiều handler đồng thời; nếu downstream chậm, cần giới hạn concurrency và prefetch theo năng lực hệ thống. Không tạo một lượng tác vụ không giới hạn cho mỗi message.

Chọn operator dựa trên semantics nghiệp vụ:

- Dùng `concatMap` khi các sự kiện của cùng aggregate phải xử lý đúng thứ tự và không được chạy đồng thời.
- Dùng `flatMapSequential` khi có thể xử lý song song nhưng output cần giữ thứ tự đầu vào.
- Dùng `flatMap` khi thứ tự output không quan trọng và cần tăng thông lượng; đặt giới hạn concurrency.
- Dùng `groupBy` khi cần gom event theo khóa, nhưng quản lý vòng đời group và số lượng group để tránh giữ quá nhiều tài nguyên.

Với Kafka, thứ tự trong một partition có ý nghĩa; song song hóa tùy tiện trong consumer có thể làm kết quả nghiệp vụ hoàn tất khác thứ tự đọc. Với RabbitMQ và Pulsar, thứ tự còn phụ thuộc queue/subscription và cách binder phân phối. Reactor operator không thể tự tạo bảo đảm thứ tự xuyên nhiều partition hoặc queue.

## 9. Xử lý event không có route và lỗi của một nhánh

Trong pipeline reactive, cần xác định rõ hành vi khi:

- Header `eventType` bị thiếu hoặc không hợp lệ.
- Không tìm thấy handler tương ứng.
- Handler trả về lỗi hoặc timeout.
- Một event không thuộc loại nào cần xử lý.
- Một nhánh output thất bại trong khi nhánh khác đã phát message.

Ví dụ chuyển lỗi của từng phần tử thành kết quả lỗi để các event khác vẫn tiếp tục:

```java
return messages.flatMap(message -> routeOne(message)
    .onErrorResume(error -> {
        log.warn("Cannot route eventId={}",
            message.getHeaders().get("eventId"), error);
        return publishToErrorFlow(message, error).then(Mono.empty());
    }));
```

`onErrorResume` đặt bên trong publisher của từng phần tử giúp cô lập lỗi theo event. Nếu để exception thoát ra ngoài pipeline, reactive sequence có thể kết thúc và hủy xử lý các phần tử còn lại. Chọn chính sách phù hợp: retry có giới hạn cho lỗi tạm thời, chuyển DLQ cho lỗi không thể xử lý, hoặc dừng toàn stream nếu tính nhất quán yêu cầu fail-fast.

Không chỉ log rồi bỏ event nếu nghiệp vụ cần bảo đảm giao nhận. Error flow cần giữ event ID, event type, correlation ID, nguồn binding và nguyên nhân; đồng thời tránh ghi payload nhạy cảm vào log.

## 10. Bảo vệ cơ chế routing

Routing header là dữ liệu đầu vào. Producer hoặc client có quyền publish có thể gửi giá trị header tùy ý. Vì vậy:

- Dùng allowlist các route/function được phép.
- Không cho client bên ngoài chọn trực tiếp tên bean bất kỳ trong ứng dụng.
- Xác thực producer và quyền publish ở broker.
- Không dùng routing để bỏ qua authorization của nghiệp vụ.
- Kiểm tra `eventType` và schema trước khi dispatch.
- Giới hạn các destination và output binding mà function có thể gửi đến.
- Bảo vệ các endpoint quản trị có thể thay đổi application properties hoặc function definition.

Spring Cloud Function đánh giá SpEL lấy từ message header trong `SimpleEvaluationContext` với khả năng bị giới hạn hơn so với expression cấu hình ở application property. Tuy vậy, vẫn phải coi route value là dữ liệu không đáng tin và giới hạn function đích. Expression đặt trong application properties có khả năng biểu đạt rộng hơn; bảo vệ nguồn cấu hình và endpoint quản trị có quyền thay đổi nó.

## 11. Kiểm thử routing với imperative và reactive

Nên có các kiểm thử phân biệt hai mô hình:

1. Với function imperative, gửi hai message có `spring.cloud.function.definition` khác nhau và xác nhận mỗi message đến đúng function.
2. Với routing expression imperative, kiểm tra các trường hợp header hợp lệ, thiếu và không nằm trong allowlist.
3. Với reactive function, cấu hình function route ở application properties và xác nhận toàn stream đi vào function đã chọn.
4. Gửi một `Flux` chứa nhiều `eventType` khác nhau và xác nhận router nội bộ chọn đúng handler cho từng phần tử.
5. Kiểm tra concurrency, thứ tự output và backpressure khi handler có thời gian xử lý khác nhau.
6. Làm một handler thất bại và xác nhận chính sách retry/DLQ hoặc cô lập lỗi theo từng event.
7. Gửi event type không hỗ trợ và xác nhận nó được quan sát, không bị bỏ qua ngoài ý muốn.
8. Kiểm thử với binder/broker thật để xác nhận header mapping, redelivery và acknowledgement theo cấu hình triển khai.

Test Binder hữu ích để kiểm tra function và binding trong phạm vi ứng dụng. Nó không thay thế integration test với Kafka, RabbitMQ hoặc Pulsar khi cần xác minh thứ tự partition, redelivery, DLQ và hành vi consumer thực tế.

## 12. Cách chọn mô hình định tuyến

| Yêu cầu | Cách tiếp cận |
|---|---|
| Mỗi message imperative chọn một function bean | `functionRouter` với `spring.cloud.function.definition` header hoặc routing-expression header |
| Chọn route imperative bằng logic Java | `MessageRoutingCallback` |
| Toàn bộ reactive stream dùng một function | `spring.cloud.function.definition` hoặc routing instruction ở application properties |
| Mỗi phần tử reactive chọn handler khác nhau | `Flux` operator và handler registry bên trong reactive function |
| Phân loại một stream thành nhiều output binding | Reactive function arity với `Tuple` chứa nhiều Publisher |
| Loại message không phù hợp | `filter` hoặc nhánh discard có metric/log/error policy rõ ràng |

Khi thiết kế routing cho Spring Cloud Stream, hãy xác định trước đơn vị công việc là một message hay toàn bộ Publisher. Dùng header routing khi function imperative cần chọn function theo từng message. Với reactive function, để application properties chọn function cho toàn stream và thực hiện phân nhánh từng event bằng Reactor operators hoặc handler registry. Cách phân chia này giữ đúng mô hình invocation của Spring Cloud Function, đồng thời cho phép kiểm soát rõ concurrency, thứ tự, lỗi và backpressure. Tên thuộc tính và chi tiết tích hợp có thể thay đổi theo release train; hãy đối chiếu tài liệu cùng phiên bản Spring Cloud Function/Spring Cloud Stream được quản lý trong dự án.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming model, Function Routing and Filtering](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Function Arity and reactive functions](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html#function-arity)
