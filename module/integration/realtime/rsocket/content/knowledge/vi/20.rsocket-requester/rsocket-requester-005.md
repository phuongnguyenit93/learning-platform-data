# Nhận một kết quả bằng retrieveMono và nhiều kết quả bằng retrieveFlux

`RSocketRequester` là API phía client của Spring để gửi request tới route RSocket và chuyển payload phản hồi thành kiểu Java. Hai phương thức thường dùng để đọc kết quả là `retrieveMono(...)` và `retrieveFlux(...)`:

- `retrieveMono(...)` nhận một kết quả bất đồng bộ, biểu diễn bằng Reactor `Mono<T>`.
- `retrieveFlux(...)` nhận một luồng gồm không, một hoặc nhiều kết quả, biểu diễn bằng `Flux<T>`.

Việc chọn phương thức phụ thuộc vào interaction model mà server cung cấp. `request-response` thường đi cùng `retrieveMono`; `request-stream` và `request-channel` thường đi cùng `retrieveFlux`. Hai phương thức không chỉ khác kiểu trả về: chúng thể hiện cách client tiêu thụ dữ liệu, điều tiết nhu cầu và hủy một tương tác đang chạy.

## 1. RSocketRequester gửi request theo route

Một request qua `RSocketRequester` thường gồm ba bước:

1. Chọn route bằng `route(...)` để Spring đặt routing metadata vào request.
2. Gửi data bằng `data(...)`, có thể là DTO hoặc một publisher tùy interaction model.
3. Chọn cách nhận kết quả bằng `retrieveMono(...)`, `retrieveFlux(...)` hoặc `send()` nếu không cần phản hồi.

Ví dụ một request tìm đơn hàng:

```java
Mono<OrderView> order = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
```

`route("orders.find")` xác định handler phía server. `data(...)` cung cấp phần data của payload. `retrieveMono(OrderView.class)` yêu cầu Spring giải mã response thành `OrderView` và trả kết quả dưới dạng `Mono<OrderView>`.

`RSocketRequester` thường được tạo sau khi kết nối TCP hoặc WebSocket đã được thiết lập. Có thể giữ requester dùng chung cho nhiều request và để RSocket multiplex nhiều stream trên một kết nối.

## 2. retrieveMono: nhận tối đa một kết quả

`retrieveMono(Class<T>)` phù hợp khi một request cần một kết quả đơn, chẳng hạn đọc một bản ghi, tạo đơn hàng hoặc xác nhận thao tác. Kiểu trả về là `Mono<T>`:

```java
Mono<OrderView> findOrder(String orderId) {
    return requester
        .route("orders.find")
        .data(new FindOrderRequest(orderId))
        .retrieveMono(OrderView.class);
}
```

`Mono` là kiểu reactive biểu diễn tối đa một giá trị. Tuy nhiên, interaction `request-response` cần một payload phản hồi hoặc một tín hiệu lỗi. Vì vậy, nếu không tìm thấy dữ liệu, handler nên ánh xạ tình huống đó thành DTO trạng thái có cấu trúc hoặc lỗi theo hợp đồng RSocket; không dựa vào `Mono.empty()` như một phản hồi nghiệp vụ thông thường.

Ví dụ sử dụng kết quả trong một service khác:

```java
Mono<OrderSummary> summary(String orderId) {
    return findOrder(orderId)
        .map(order -> new OrderSummary(
            order.orderId(),
            order.status()
        ));
}
```

Không cần gọi `subscribe()` bên trong mỗi method service. Hãy trả `Mono` cho tầng gọi để toàn bộ chuỗi reactive giữ được lỗi, cancellation và context. Chỉ subscribe tại ranh giới thực thi phù hợp, ví dụ entry point của ứng dụng hoặc một consumer được quản lý.

## 3. retrieveFlux: nhận nhiều kết quả

`retrieveFlux(Class<T>)` phù hợp khi responder có thể phát nhiều payload theo thời gian. Ví dụ tìm tất cả đơn hàng của một khách hàng:

```java
Flux<OrderView> findOrders(String customerId) {
    return requester
        .route("orders.by-customer")
        .data(new FindOrdersRequest(customerId))
        .retrieveFlux(OrderView.class);
}
```

Mỗi payload phản hồi được decode thành một `OrderView` và phát thành một phần tử của `Flux<OrderView>`. Luồng có thể hoàn tất sau một số phần tử, hoàn tất mà không phát phần tử nào, hoặc kết thúc bằng lỗi.

`Flux` phù hợp với danh sách lớn, dữ liệu realtime hoặc kết quả được phát dần. Caller có thể xử lý từng phần tử khi nó tới thay vì chờ toàn bộ kết quả được gom vào một collection.

Ví dụ xử lý từng đơn hàng:

```java
findOrders("customer-01")
    .map(this::toOrderSummary)
    .doOnNext(this::publishSummary)
    .then();
```

Trong ứng dụng thực tế, hãy trả `Flux` về cho caller nếu caller cần kiểm soát thời điểm subscribe và cancellation. Nếu dùng `.collectList()`, toàn bộ phần tử sẽ được giữ trong bộ nhớ cho tới khi stream hoàn tất; chỉ làm vậy khi kích thước kết quả có giới hạn hợp lý.

## 4. Chọn Mono hay Flux theo interaction model

Hai kiểu trả về tương ứng với cách tương tác khác nhau:

| Interaction model | Dữ liệu client gửi | Phản hồi server | API requester thường dùng |
|---|---|---|---|
| `request-response` | Một payload | Tối đa một payload | `retrieveMono(...)` |
| `request-stream` | Một payload ban đầu | Nhiều payload theo thời gian | `retrieveFlux(...)` |
| `request-channel` | Một luồng payload | Một luồng payload phản hồi | `data(Publisher, Class).retrieveFlux(...)` |
| `fire-and-forget` | Một payload | Không có phản hồi nghiệp vụ | `send()` |

Không nên chọn `retrieveFlux` chỉ vì muốn “dùng reactive”. Nếu server chỉ trả một kết quả, `retrieveMono` thể hiện contract rõ hơn. Ngược lại, không dùng `retrieveMono` để đọc một stream có nhiều phần tử vì API cần giữ lại tất cả dữ liệu và vòng đời của luồng.

Spring xác định `request-stream` hay `request-channel` dựa trên cách cung cấp data đầu vào: data đơn tạo request-stream khi dùng `retrieveFlux`, còn publisher nhiều phần tử tạo request-channel. Nếu truyền publisher nhiều phần tử rồi gọi `retrieveMono`, Spring báo lỗi vì RSocket không có interaction model many-to-one tương ứng.

## 5. Ví dụ server request-response và request-stream

DTO dùng chung giữa client và server:

```java
public record FindOrderRequest(String orderId) {}

public record FindOrdersRequest(String customerId) {}

public record OrderView(
    String orderId,
    String customerId,
    String status
) {}
```

Server xử lý request-response:

```java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderView> find(@Payload FindOrderRequest request) {
        return orderService.findById(request.orderId());
    }

    @MessageMapping("orders.by-customer")
    public Flux<OrderView> byCustomer(
            @Payload FindOrdersRequest request) {
        return orderService.findByCustomer(request.customerId());
    }
}
```

Hai method đều dùng `@MessageMapping`, nhưng kiểu trả về thể hiện cardinality khác nhau. `Mono<OrderView>` trả một kết quả đơn; `Flux<OrderView>` phát các đơn hàng theo nhu cầu của subscriber. Client dùng route tương ứng và chọn `retrieveMono` hoặc `retrieveFlux` theo contract đó.

## 6. Nhận dữ liệu generic bằng ParameterizedTypeReference

Khi response là một kiểu generic như `ApiResponse<OrderView>` hoặc `PageResult<OrderView>`, chỉ truyền `Class<T>` có thể không giữ đủ thông tin generic do type erasure của Java. Spring cung cấp overload nhận `ParameterizedTypeReference<T>`:

```java
ParameterizedTypeReference<ApiResponse<OrderView>> responseType =
    new ParameterizedTypeReference<>() {};

Mono<ApiResponse<OrderView>> response = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(responseType);
```

Với một stream generic, có thể dùng overload `retrieveFlux(...)` tương ứng:

```java
ParameterizedTypeReference<EventEnvelope<OrderView>> eventType =
    new ParameterizedTypeReference<>() {};

Flux<EventEnvelope<OrderView>> events = requester
    .route("orders.events")
    .data(new OrderEventRequest("customer-01"))
    .retrieveFlux(eventType);
```

Codec vẫn phải hỗ trợ kiểu bên trong và MIME type phải tương thích. `ParameterizedTypeReference` giữ thông tin kiểu generic cho bước chuyển đổi; nó không tự bổ sung codec cho một kiểu dữ liệu mà ứng dụng chưa hỗ trợ.

## 7. request-stream: một request, nhiều response

Với `request-stream`, client gửi một payload mô tả yêu cầu ban đầu. Server có thể phát nhiều phần tử, ví dụ danh sách sự kiện hoặc trạng thái xử lý:

```java
@MessageMapping("orders.events")
public Flux<OrderEvent> events(@Payload OrderEventRequest request) {
    return orderService.watchEvents(request.customerId());
}
```

Client nhận từng sự kiện:

```java
Flux<OrderEvent> events = requester
    .route("orders.events")
    .data(new OrderEventRequest("customer-01"))
    .retrieveFlux(OrderEvent.class);
```

Luồng có thể tiếp tục trong thời gian dài. Caller cần xác định điều kiện dừng, chẳng hạn người dùng rời màn hình, subscription hết hạn hoặc đã nhận đủ dữ liệu cần thiết. Một `Flux` không tự hoàn tất chỉ vì client đã nhận được vài phần tử.

## 8. request-channel: gửi và nhận luồng đồng thời

`request-channel` dùng khi client cần gửi một luồng payload và đồng thời nhận một luồng phản hồi trên cùng tương tác. Với `RSocketRequester`, truyền publisher vào `data(...)` và chỉ định kiểu phần tử:

```java
Flux<PriceUpdate> updates = requester
    .route("prices.watch")
    .data(priceCommands, PriceCommand.class)
    .retrieveFlux(PriceUpdate.class);
```

Server nhận publisher đầu vào và trả publisher phản hồi:

```java
@MessageMapping("prices.watch")
public Flux<PriceUpdate> watch(@Payload Flux<PriceCommand> commands) {
    return commands.concatMap(command ->
        priceService.apply(command)
            .map(result -> new PriceUpdate(
                command.symbol(),
                result.currentPrice()
            ))
    );
}
```

Trong channel, client vừa phát `PriceCommand` vừa tiêu thụ `PriceUpdate`. `retrieveFlux` đại diện cho luồng phản hồi; publisher truyền vào `data(...)` đại diện cho luồng yêu cầu. Hai luồng có vòng đời liên quan: cancellation hoặc lỗi terminal có thể kết thúc toàn bộ channel.

Nếu cần xử lý song song, có thể dùng `flatMap` với concurrency được giới hạn. Nếu thứ tự lệnh có ý nghĩa, `concatMap` thường dễ dự đoán hơn. Không để một publisher đầu vào vô hạn tiếp tục phát dữ liệu sau khi phần nhận phản hồi đã bị hủy mà không có chính sách quản lý rõ ràng.

## 9. Backpressure: tiêu thụ theo nhu cầu

`Flux` tuân theo Reactive Streams. Subscriber yêu cầu số phần tử mà nó có thể xử lý; upstream phát dữ liệu theo nhu cầu đó. Trong RSocket streaming interaction, nhu cầu này được ánh xạ thành flow control ở cấp giao thức, giúp responder không phải gửi vô hạn dữ liệu vượt quá khả năng tiêu thụ của requester.

Ví dụ xử lý một số phần tử đầu tiên:

```java
Flux<OrderView> firstTen = requester
    .route("orders.by-customer")
    .data(new FindOrdersRequest("customer-01"))
    .retrieveFlux(OrderView.class)
    .take(10);
```

`take(10)` hoàn tất luồng sau mười phần tử và hủy subscription upstream. Đây là một cách giới hạn công việc mà caller cần nhận. Nếu dữ liệu có tốc độ cao, có thể dùng các operator như `limitRate`, `buffer` hoặc `onBackpressureBuffer` theo chính sách dung lượng cụ thể. Tránh buffer không giới hạn vì nó có thể biến áp lực ngược thành tăng bộ nhớ không kiểm soát.

Backpressure không thay thế giới hạn tài nguyên ở service. Handler vẫn cần giới hạn số truy vấn đồng thời, kích thước batch, queue và tốc độ phát dữ liệu từ nguồn ngoài RSocket.

## 10. Cancellation và vòng đời Flux

Khi caller hủy subscription, ví dụ bằng `take(n)`, timeout hoặc dispose, cancellation được truyền ngược qua pipeline reactive. Với streaming interaction, RSocket có thể gửi tín hiệu `CANCEL` để responder dừng công việc của stream tương ứng.

Ví dụ giới hạn thời gian chờ dữ liệu:

```java
Flux<OrderEvent> recentEvents = requester
    .route("orders.events")
    .data(new OrderEventRequest("customer-01"))
    .retrieveFlux(OrderEvent.class)
    .timeout(Duration.ofSeconds(30));
```

Timeout phát lỗi ở phía client và hủy subscription upstream. Server nên giải phóng tài nguyên gắn với stream khi nhận cancellation, ví dụ dừng listener, hủy truy vấn reactive hoặc ngừng polling. Nếu nguồn dữ liệu không hỗ trợ cancellation, handler cần có cơ chế dừng công việc phù hợp.

Đối với stream dài hạn, nên xác định rõ ai sở hữu subscription và thời điểm đóng. Tránh tạo subscription nền không có đường dừng hoặc tạo nhiều subscription trùng cho cùng một màn hình.

## 11. Xử lý lỗi từ retrieveMono và retrieveFlux

Lỗi của request được phát thành `onError` trong `Mono` hoặc `Flux`. Có thể xử lý lỗi ở caller bằng Reactor:

```java
Mono<OrderView> order = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class)
    .doOnError(error -> log.warn("Cannot load order", error))
    .onErrorResume(error -> isNotFoundSignal(error)
        ? loadFallbackOrder("ORD-1001")
        : Mono.error(error));
```

`doOnError` chỉ quan sát lỗi. `onErrorResume` thay thế luồng lỗi bằng một publisher khác. Trong ví dụ, `isNotFoundSignal` cần nhận diện mã lỗi ứng dụng theo hợp đồng lỗi đã thống nhất giữa hai peer; không giả định exception Java tùy chỉnh của server sẽ được truyền nguyên class sang client. `loadFallbackOrder` chỉ phù hợp nếu ứng dụng có dữ liệu dự phòng hợp lệ. Hãy truyền tiếp các lỗi hệ thống, lỗi xác thực và lỗi không xác định thay vì che giấu chúng.

Với `Flux`, lỗi terminal kết thúc toàn bộ stream. Nếu một phần tử lỗi nhưng stream vẫn cần tiếp tục, hãy biểu diễn trạng thái lỗi thành một phần tử dữ liệu hoặc xử lý lỗi bên trong publisher con trước khi trả về stream ngoài. Không thể tiếp tục phát phần tử sau khi một `Flux` đã phát `onError`.

Retry chỉ phù hợp với lỗi tạm thời và thao tác có thể lặp an toàn. Với thao tác ghi, hãy dùng idempotency key hoặc cơ chế đối soát trước khi retry vì client có thể mất phản hồi sau khi server đã thực hiện side effect.

## 12. Không nhầm retrieveMono/retrieveFlux với send

`RSocketRequester` còn có `send()` cho fire-and-forget. Phương thức này trả `Mono<Void>` cho biết thao tác gửi payload có thành công hay không; nó không xác nhận event đã được xử lý ở phía nhận và không trả payload nghiệp vụ:

```java
Mono<Void> publishMetric = requester
    .route("metrics.publish")
    .data(new MetricEvent("cpu", 0.72))
    .send();
```

Nếu caller cần biết server đã chấp nhận hoặc xử lý sự kiện, hãy thiết kế acknowledgement bằng `retrieveMono(Ack.class)` hoặc một interaction model có phản hồi. `send()` không tương đương `retrieveMono(Void.class)`; chúng biểu diễn các contract giao thức khác nhau.

## 13. Kiểm thử Mono và Flux bằng StepVerifier

`StepVerifier` giúp kiểm tra số phần tử, nội dung, lỗi và thời điểm hoàn tất mà không cần gọi `block()` trong test reactive.

Kiểm thử một kết quả:

```java
StepVerifier.create(
        requester.route("orders.find")
            .data(new FindOrderRequest("ORD-1001"))
            .retrieveMono(OrderView.class)
    )
    .assertNext(order -> {
        assertThat(order.orderId()).isEqualTo("ORD-1001");
        assertThat(order.status()).isEqualTo("CREATED");
    })
    .verifyComplete();
```

Kiểm thử nhiều kết quả:

```java
StepVerifier.create(
        requester.route("orders.by-customer")
            .data(new FindOrdersRequest("customer-01"))
            .retrieveFlux(OrderView.class)
    )
    .expectNextMatches(order -> order.customerId().equals("customer-01"))
    .expectNextCount(1)
    .verifyComplete();
```

Với stream dài hạn, dùng `thenCancel()` sau khi xác nhận các phần tử mong đợi để kiểm tra cancellation. Với request-channel, hãy kiểm tra cả số command đã gửi, acknowledgement nhận được, thứ tự và hành vi khi input publisher bị hủy hoặc phát lỗi.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `retrieveMono` không nhận được kiểu mong đợi | Response MIME type hoặc codec không tương thích | Đồng bộ data MIME type và encoder/decoder |
| `retrieveFlux` chỉ phát một phần tử | Server handler chỉ phát một giá trị hoặc hoàn tất sớm | Kiểm tra kiểu trả về và lifecycle publisher phía server |
| `retrieveMono` không phù hợp với nhiều kết quả | Đang gọi request-stream nhưng dùng API đơn | Dùng `retrieveFlux` |
| `retrieveFlux` không có phần tử | Server hoàn tất stream rỗng hoặc filter loại hết dữ liệu | Kiểm tra contract và điều kiện lọc |
| Request-channel không gửi được dữ liệu | Chưa truyền publisher hoặc thiếu element type | Dùng `.data(publisher, ElementType.class)` |
| Stream dừng với lỗi | Responder phát lỗi terminal hoặc kết nối bị đóng | Kiểm tra `onError`, log server và lifecycle kết nối |
| Bộ nhớ tăng theo thời gian | Gom toàn bộ Flux hoặc buffer không giới hạn | Xử lý từng phần tử, đặt giới hạn batch/buffer |
| Server tiếp tục làm việc sau khi client rời đi | Handler hoặc nguồn dữ liệu không phản ứng với cancellation | Propagate cancellation và đóng tài nguyên đúng cách |
| Gửi lặp thao tác ghi khi retry | Không có idempotency hoặc trạng thái đối soát | Dùng idempotency key và retry có phân loại |

## 15. Checklist chọn API

- [ ] Dùng `retrieveMono` khi server trả một kết quả đơn cho request-response.
- [ ] Dùng `retrieveFlux` khi server phát nhiều kết quả cho request-stream.
- [ ] Dùng `.data(publisher, ElementType.class).retrieveFlux(...)` cho request-channel.
- [ ] Dùng `send()` cho fire-and-forget khi không cần payload phản hồi.
- [ ] Chọn đúng DTO response và MIME type/codec.
- [ ] Dùng `ParameterizedTypeReference` khi cần giữ thông tin kiểu generic.
- [ ] Không gọi `subscribe()` lồng trong service nếu có thể compose và trả publisher.
- [ ] Đặt giới hạn tiêu thụ, buffer và concurrency cho stream lớn hoặc dài hạn.
- [ ] Xử lý cancellation và lỗi terminal rõ ràng.
- [ ] Chỉ retry lỗi tạm thời và bảo vệ thao tác ghi bằng idempotency.
- [ ] Kiểm thử số phần tử, thứ tự, lỗi và cancellation bằng `StepVerifier`.

`retrieveMono` và `retrieveFlux` giúp client thể hiện đúng số lượng kết quả mà một tương tác RSocket cung cấp. Dùng `Mono` cho phản hồi đơn, `Flux` cho luồng nhiều phần tử, và kết hợp publisher đầu vào với `retrieveFlux` khi cần request-channel. Khi contract, codec, backpressure, cancellation và xử lý lỗi được xác định rõ, client có thể tiêu thụ dữ liệu realtime mà vẫn kiểm soát được tài nguyên và vòng đời của từng stream.

## Tài liệu tham khảo

- [Spring Framework 6.1 — RSocketRequester.RetrieveSpec](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
- [Spring Framework 6.1 — RSocketRequester.RequestSpec](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
