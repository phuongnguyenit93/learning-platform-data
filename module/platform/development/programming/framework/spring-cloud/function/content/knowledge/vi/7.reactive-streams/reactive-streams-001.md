# Mono, Flux và chữ ký hàm phản ứng trong Spring Cloud Function

## 1. Vì sao Spring Cloud Function cần Mono và Flux?

Spring Cloud Function cho phép đóng gói logic nghiệp vụ thành các hàm Java như `Supplier`, `Function` và `Consumer`, rồi đưa chúng qua `FunctionCatalog` để các adapter gọi qua HTTP, hệ thống sự kiện hoặc môi trường serverless. Khi bài toán liên quan đến dữ liệu đến liên tục, I/O bất đồng bộ hoặc nhiều kết quả theo thời gian, các chữ ký phản ứng dùng `Mono` và `Flux` của Project Reactor giúp hàm mô tả **luồng xử lý** thay vì chờ từng thao tác hoàn tất.

Ví dụ, một hệ thống nhận sự kiện đơn hàng có thể kiểm tra từng đơn ngay khi xuất hiện, gọi dịch vụ kiểm tra rủi ro bất đồng bộ và phát kết quả về luồng đầu ra. Logic kiểm tra vẫn nằm trong bean `Function`; nguồn nhận và nơi phát thông điệp do adapter quyết định.

Điểm quan trọng: **một `Flux<T>` là một mô tả luồng các phần tử `T`, không phải một `List<T>` đã tải sẵn**. Một `Mono<T>` cũng là publisher, dù tối đa chỉ phát một giá trị. Việc dùng kiểu phản ứng không tự biến mã chặn luồng thành mã không chặn; tính chất đó phụ thuộc cả các thao tác bên trong hàm và thư viện I/O được sử dụng.

## 2. Nền tảng Reactor: Mono, Flux và tín hiệu luồng

Reactor triển khai quy tắc Reactive Streams thông qua `Publisher`, `Subscriber` và `Subscription`. Khi có subscriber, publisher có thể phát các tín hiệu:

- `onNext(value)`: có một phần tử mới;
- `onComplete()`: kết thúc bình thường;
- `onError(error)`: kết thúc do lỗi.

`onComplete` và `onError` là hai tín hiệu kết thúc loại trừ nhau. Sau tín hiệu kết thúc, publisher không phát thêm phần tử.

| Khái niệm | Số phần tử tối đa trong một lần đăng ký | Tình huống phù hợp |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 | Một kết quả tra cứu, phản hồi HTTP đơn lẻ, xác nhận hoàn tất |
| `Flux<T>` | 0 đến N | Dòng sự kiện, nhiều bản ghi, tập kết quả hoặc luồng liên tục |
| `Mono<Void>` | Không phát giá trị nghiệp vụ | Báo hoàn tất hoặc lỗi của một tác vụ bất đồng bộ |
| `Flux<Message<T>>` | 0 đến N thông điệp | Xử lý payload cùng metadata như correlation ID, header định tuyến |

Ví dụ Reactor cơ bản:

~~~java
Mono<String> customer = Mono.just("C-42");
Flux<String> orders = Flux.just("O-1", "O-2", "O-3");

Flux<String> oneAsFlux = customer.flux();
Mono<List<String>> allOrders = orders.collectList();
Mono<String> firstOrder = orders.next();
~~~

`collectList()` chỉ phù hợp khi luồng hữu hạn và kích thước được kiểm soát, vì nó phải giữ các phần tử trong bộ nhớ trước khi phát danh sách. Nếu dùng trên luồng vô hạn, `Mono<List<T>>` không bao giờ hoàn tất. `next()` lấy phần tử đầu tiên và hủy đăng ký đối với phần còn lại khi có thể.

**Không dùng `null` làm phần tử hoặc kết quả của `map`.** Reactor cấm `null` trong tín hiệu `onNext`. Hãy dùng `Mono.empty()` khi không có kết quả, hoặc các toán tử `filter`/`flatMap` khi cần bỏ phần tử.

### 2.1. Publisher thường chỉ chạy khi có subscription

Đa số publisher tạo bằng `just`, `fromIterable`, `map`, `flatMap` là *cold*: mỗi subscription có thể kích hoạt một lượt xử lý độc lập. Một nguồn hot, chẳng hạn nguồn nhận sự kiện qua `Sinks.Many`, có thể phát dữ liệu mà không đợi subscriber mới; subscriber đến muộn có thể không thấy các sự kiện cũ tùy cấu hình.

~~~java
Flux<Integer> pipeline = Flux.just(1, 2, 3)
    .map(x -> x * 10); // Mới mô tả phép biến đổi

// Khi subscriber đăng ký, pipeline mới phát 10, 20, 30.
pipeline.subscribe(System.out::println);
~~~

`subscribe()` trong ví dụ trên minh họa Reactor thuần. **Trong một bean `Function<Flux<T>, Flux<R>>` của Spring Cloud Function, thông thường hãy trả về publisher cho framework/adapter quản lý subscription**. Tự gọi `subscribe()` trong hàm dễ làm mất khả năng truyền lỗi, quản lý hủy và theo dõi thời điểm hoàn tất.

### 2.2. Backpressure và cancellation

Một subscriber có thể yêu cầu số lượng phần tử thông qua cơ chế `request(n)` thay vì nhận vô hạn; đây là *backpressure*. Subscriber cũng có thể hủy subscription khi không còn cần kết quả. Các toán tử Reactor tham gia truyền tín hiệu yêu cầu và hủy, nhưng toàn bộ hiệu quả còn tùy nguồn dữ liệu và adapter: một message broker, HTTP client hoặc hệ thống bên ngoài không nhất thiết điều tiết theo đúng từng tín hiệu `request(n)`.

Vì vậy, giới hạn đồng thời của tác vụ I/O bằng `flatMap(mapper, concurrency)` vẫn cần thiết để tránh có quá nhiều yêu cầu đang chạy. Không nên xem backpressure là cơ chế bảo đảm rằng mọi hàng đợi bên ngoài đều tự động bị giới hạn.

## 3. Chữ ký hàm phản ứng trong Spring Cloud Function

Trong lập trình đồng bộ, một hàm thường nhận và trả về giá trị trực tiếp:

~~~java
Function<String, String> normalize = text -> text.trim().toUpperCase();
~~~

Trong cách viết phản ứng, tham số và/hoặc kết quả có thể là publisher:

| Chữ ký | Ý nghĩa | Lưu ý về vòng đời |
| --- | --- | --- |
| `Function<Mono<T>, Mono<R>>` | Biến đổi một đầu vào bất đồng bộ thành tối đa một kết quả | Phù hợp khi hợp đồng adapter mang nghĩa một giá trị |
| `Function<Flux<T>, Flux<R>>` | Biến đổi luồng `T` thành luồng `R` | Có thể phát 0, 1 hoặc nhiều `R` cho mỗi `T` |
| `Function<Flux<T>, Mono<R>>` | Rút gọn/đúc kết một luồng thành tối đa một `R` | Thường chỉ phát kết quả sau khi luồng đầu vào hoàn tất |
| `Supplier<Flux<T>>` | Cung cấp một publisher làm nguồn dữ liệu | Số lần gọi supplier và subscription phụ thuộc adapter |
| `Supplier<Mono<T>>` | Cung cấp publisher tối đa một giá trị | Có thể rỗng hoặc thất bại |
| `Consumer<Flux<T>>` | Nhận publisher để thực hiện tác dụng phụ | Không trả publisher chứa tín hiệu hoàn tất/lỗi cho caller; cần quản lý subscription cẩn thận |
| `Function<Flux<T>, Mono<Void>>` | Thực hiện tác vụ bất đồng bộ trên luồng và trả tín hiệu hoàn tất | Hữu ích khi caller/adapter có thể chờ publisher hoàn tất |

`T` và `R` có thể là kiểu payload nghiệp vụ (`OrderEvent`, `Decision`), hoặc `Message<T>` để mang thông điệp và header. Chữ ký hàm cung cấp thông tin kiểu cho `FunctionCatalog` và cơ chế chuyển đổi dữ liệu, nhưng adapter cụ thể mới quyết định cách đóng gói từng lần gọi, subscription và đầu ra.

### 3.1. Ranh giới giữa “một phần tử” và “một luồng”

Hai hàm dưới đây có logic giống nhau ở mức phép biến đổi, nhưng mang hợp đồng khác nhau:

~~~java
Function<String, String> upperOne = String::toUpperCase;

Function<Flux<String>, Flux<String>> upperStream =
    source -> source.map(String::toUpperCase);
~~~

Với `upperOne`, caller truyền một `String` và nhận một `String`. Với `upperStream`, caller truyền một publisher; hàm có thể xử lý nhiều phần tử của **cùng một subscription**. Khi dùng adapter sự kiện có hỗ trợ luồng liên tục, không được giả định framework sẽ gọi lại lambda một lần cho mỗi message.

Mặt khác, `Mono` không đồng nghĩa với “chỉ một phần tử trong toàn bộ vòng đời ứng dụng”. Mỗi lần subscribe vào publisher cold có thể thực hiện lại thao tác. Muốn tránh phát trùng khi tích hợp broker, cần hợp đồng idempotency, checkpoint/acknowledgment và quản lý nguồn dữ liệu tương ứng.

### 3.2. Các ràng buộc kiểu khi composition

Một chuỗi `a|b` hợp lý khi đầu ra logic của `a` tương thích với đầu vào của `b`. Ví dụ:

~~~java
@Bean
Function<Flux<String>, Flux<String>> trimText() {
    return source -> source.map(String::trim);
}

@Bean
Function<Flux<String>, Flux<String>> markText() {
    return source -> source.map(value -> "checked:" + value);
}
~~~

Khai báo function definition cho adapter:

~~~properties
spring.cloud.function.definition=trimText|markText
~~~

Khi chuỗi được chọn, dữ liệu đi qua `trimText` rồi `markText`. Spring Cloud Function dùng `FunctionCatalog` để tra cứu, đóng gói và composition các function bean. Với tổ hợp phức tạp giữa kiểu đồng bộ, `Mono`, `Flux` hoặc `Message`, cần kiểm tra sự tương thích kiểu và hành vi thực tế trên phiên bản adapter đang dùng; không suy luận rằng mọi kết hợp đều duy trì nguyên trạng số lần gọi và message header.

## 4. Ví dụ hoàn chỉnh: kiểm tra dòng đơn hàng

Giả sử mỗi đơn hàng có mã và số tiền. Yêu cầu là đánh dấu đơn có số tiền dương là hợp lệ, đồng thời có một hàm độc lập tính tổng tiền của luồng hữu hạn.

Đây là cấu hình Spring độc lập với giao thức. Ví dụ dùng `record`, cần Java 17 trở lên, cùng các dependency Spring Cloud Function và Reactor tương ứng.

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderFunctions {

    public record OrderEvent(String orderId, long amount) { }
    public record Decision(String orderId, boolean accepted) { }

    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> checkOrders() {
        return orders -> orders.map(order ->
            new Decision(order.orderId(), order.amount() > 0)
        );
    }

    @Bean
    public Function<Mono<OrderEvent>, Mono<Decision>> checkOneOrder() {
        return oneOrder -> oneOrder.map(order ->
            new Decision(order.orderId(), order.amount() > 0)
        );
    }

    @Bean
    public Function<Flux<OrderEvent>, Mono<Long>> sumAmounts() {
        return orders -> orders
            .map(OrderEvent::amount)
            .reduce(0L, Long::sum);
    }
}
~~~

**Phân tích từng chữ ký:**

1. `checkOrders` nhận `Flux<OrderEvent>` và trả `Flux<Decision>`. `map` thực hiện phép biến đổi đồng bộ cho mỗi phần tử, giữ thứ tự và không tạo tác vụ I/O riêng.
2. `checkOneOrder` nhận `Mono<OrderEvent>`. Nếu đầu vào là `Mono.empty()` thì đầu ra cũng rỗng; lambda trong `map` không chạy.
3. `sumAmounts` dùng `reduce(0L, Long::sum)`. Chỉ khi đầu vào hoàn tất, nó mới phát một tổng; với luồng rỗng, tổng là `0L`. Trường hợp chuỗi sự kiện chạy liên tục không có `onComplete`, hàm này sẽ không phát tổng cuối.

Ví dụ dùng trực tiếp bean để quan sát:

~~~java
OrderFunctions config = new OrderFunctions();

Flux<OrderFunctions.OrderEvent> input = Flux.just(
    new OrderFunctions.OrderEvent("O-100", 120),
    new OrderFunctions.OrderEvent("O-101", 0)
);

Flux<OrderFunctions.Decision> checked =
    config.checkOrders().apply(input);

Mono<Long> total = config.sumAmounts().apply(
    Flux.just(
        new OrderFunctions.OrderEvent("O-100", 120),
        new OrderFunctions.OrderEvent("O-101", 0)
    )
);
~~~

`checked` mô tả hai kết quả `Decision("O-100", true)` và `Decision("O-101", false)`. `total` mô tả một kết quả `120L`. Cả hai chưa bắt buộc chạy cho đến khi có subscriber. Nếu hai hàm cùng dùng **một** publisher cold, mỗi subscription có thể đọc nguồn lại; trên nguồn hot hoặc nguồn có tác dụng phụ, chiến lược chia sẻ/replay phải được thiết kế riêng.

### 4.1. Cần tổng hợp định kỳ từ luồng không kết thúc?

Thay vì `reduce` toàn bộ luồng, có thể chia cửa sổ theo số lượng hoặc thời gian rồi tổng hợp từng cửa sổ:

~~~java
Function<Flux<Long>, Flux<Long>> sumInWindows = amounts ->
    amounts
        .windowTimeout(100, java.time.Duration.ofSeconds(5))
        .concatMap(window -> window.reduce(0L, Long::sum));
~~~

Mỗi cửa sổ được xử lý rồi phát tổng của chính cửa sổ đó. Kết quả vẫn là `Flux<Long>`, phù hợp với nguồn liên tục. Lựa chọn kích thước cửa sổ, hành vi cửa sổ rỗng và thời gian trễ phải dựa vào yêu cầu thực tế.

## 5. Supplier, Consumer và quyền sở hữu subscription

Ba mô hình Supplier–Function–Consumer vẫn giữ vai trò quen thuộc trong reactive programming, nhưng việc tạo và tiêu thụ publisher đòi hỏi xác định ai là subscriber cuối cùng.

### Supplier phát một luồng

~~~java
@Bean
Supplier<Flux<String>> pendingIds() {
    return () -> Flux.just("O-100", "O-101");
}
~~~

Mỗi lần gọi `get()` tạo một `Flux` cold mới. Nếu adapter gọi lại supplier hoặc subscribe lại, các ID trên có thể được phát lặp. Đây là mẫu minh họa; nguồn sự kiện thật cần cơ chế đọc/đánh dấu đã xử lý phù hợp.

Với nguồn liên tục:

~~~java
@Bean
Supplier<Flux<Long>> ticks() {
    return () -> Flux.interval(java.time.Duration.ofSeconds(1));
}
~~~

`Flux.interval` là luồng theo thời gian, cần được hủy khi ngừng xử lý. Tính năng tự kích hoạt supplier, lịch gọi và cách kết nối với broker/serverless thay đổi theo adapter; không nên coi một bean supplier là cơ chế lập lịch hoặc bảo đảm giao hàng độc lập.

### Consumer và tác vụ bất đồng bộ

`Consumer<Flux<T>>` trả về `void`, nên chữ ký này không biểu diễn trực tiếp việc xử lý bất đồng bộ đã hoàn thành hay thất bại. Với consumer reactive, phải hiểu rõ adapter có quản lý subscription hay consumer tự chịu trách nhiệm; gọi `subscribe()` thủ công mà không quản lý lỗi, hủy và vòng đời sẽ khiến tác vụ khó quan sát.

Khi đầu ra cần mô tả việc ghi dữ liệu đã hoàn tất, có thể chọn một hàm trả `Mono<Void>`. Giả sử `reactiveStore.save(order)` trả `Mono<?>`:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> persistOrders = orders ->
    orders
        .concatMap(order -> reactiveStore.save(order))
        .then();
~~~

`then()` bỏ qua giá trị ghi thành công và chỉ phát tín hiệu hoàn tất hoặc lỗi. Đây là mô hình hữu ích nếu adapter/caller hỗ trợ chờ kết quả của publisher. Không được nhầm một `Mono<Void>` đã tạo với một thao tác đã thực thi: publisher vẫn cần được subscribe.

## 6. Toán tử hay dùng trong hàm phản ứng

| Toán tử | Khi dùng | Bẫy thường gặp |
| --- | --- | --- |
| `map` | Biến đổi từng phần tử ngay trong pipeline | Dùng để gọi I/O blocking hoặc trả `Mono` lồng nhau |
| `flatMap` | Gọi tác vụ bất đồng bộ trả publisher | Có thể đổi thứ tự kết quả khi các tác vụ hoàn thành khác nhau |
| `concatMap` | Chạy lần lượt và giữ thứ tự | Tốc độ tối đa thấp hơn khi tác vụ chậm |
| `flatMapSequential` | Cho phép làm đồng thời nhưng phát theo thứ tự nguồn | Có thể phải giữ kết quả chờ các phần tử trước |
| `filter` | Loại phần tử không đạt điều kiện | Luồng không còn quan hệ 1–1 đầu vào/đầu ra |
| `onErrorResume` | Chuyển lỗi thành publisher thay thế | Xử lý ở ngoài cùng có thể kết thúc phần còn lại của luồng |
| `timeout` | Giới hạn thời gian chờ | Phải xác định chính sách khi hết hạn |
| `doOnNext` / `doOnError` | Gắn đo đạc, log, tracing | Không thay cho thao tác nghiệp vụ có kết quả bất đồng bộ |

### 6.1. `map` so với `flatMap`

Giả sử `fraudService.check(order)` trả `Mono<Decision>`:

~~~java
// Không đúng ý định nếu muốn Flux<Decision>:
Flux<Mono<Decision>> nested = orders.map(fraudService::check);

// Hợp đồng đầu ra phẳng, giới hạn tối đa 8 tác vụ đồng thời:
Flux<Decision> checked = orders.flatMap(
    fraudService::check,
    8
);
~~~

`flatMap` không cam kết giữ thứ tự đầu ra. Nếu đơn hàng phải được xử lý đúng thứ tự, dùng `concatMap(fraudService::check)`; nếu muốn đồng thời nhưng xuất kết quả theo thứ tự gốc, cân nhắc `flatMapSequential`.

### 6.2. Không chặn luồng xử lý

Những cách sau có thể làm nghẽn event loop hoặc thread xử lý:

~~~java
// Tránh trong logic phản ứng đang xử lý I/O:
return orders.map(order -> blockingJdbcRepository.find(order.orderId()));
// Tránh: mono.block(), Thread.sleep(...), CompletableFuture.get()...
~~~

Ưu tiên client/reactive repository trả `Mono` hoặc `Flux` và ghép bằng `flatMap`. Nếu tạm thời phải tích hợp một API chặn luồng, có thể cô lập nó trên scheduler dành cho blocking:

~~~java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyClient.loadCustomer(customerId)
    )
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

Cách này di chuyển thao tác chặn khỏi event loop, **không biến API blocking thành non-blocking**. Vẫn phải giới hạn mức đồng thời và đánh giá timeout, tải hệ thống, kết nối và hành vi hủy.

## 7. Xử lý lỗi trên từng phần tử và toàn luồng

Trong Reactive Streams, `onError` là tín hiệu **kết thúc** subscription. Một lỗi trong `map`, `flatMap` hoặc I/O có thể làm dừng toàn luồng nếu không được xử lý ở phạm vi phù hợp.

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> inspect =
    orders -> orders.flatMap(
        order -> fraudService.check(order)
            .timeout(java.time.Duration.ofSeconds(2))
            .onErrorResume(error -> Mono.just(
                new Decision(order.orderId(), false)
            )),
        8
    );
~~~

Ở đây mỗi tác vụ con tự xử lý lỗi, nên lỗi kiểm tra một đơn không nhất thiết làm kết thúc xử lý các đơn khác. **Đánh dấu `false` chỉ đúng nếu chính sách nghiệp vụ cho phép từ chối an toàn khi dịch vụ lỗi.** Nếu lỗi phải được báo đến caller, hãy để nó truyền thành `onError` hoặc biến thành một kết quả nghiệp vụ thể hiện rõ trạng thái chưa xác định.

Ngược lại:

~~~java
orders.flatMap(fraudService::check)
    .onErrorResume(error -> Flux.empty());
~~~

`onErrorResume` ngoài cùng thay thế phần luồng đã lỗi bằng publisher rỗng; nó không “bỏ qua lỗi và tiếp tục nhận các phần tử tương lai” từ subscription đã kết thúc. Không dùng `onErrorContinue` như giải pháp mặc định, vì phạm vi hỗ trợ phụ thuộc toán tử và dễ làm sai trạng thái.

Có thể phân loại lỗi bằng `onErrorResume(SpecificException.class, ...)`, bổ sung `retryWhen` cho lỗi tạm thời, nhưng chỉ retry khi thao tác có tính idempotent hoặc có cơ chế chống lặp.

## 8. Làm việc với Message và metadata

Khi hàm cần correlation ID, key phân vùng hoặc header định tuyến, dùng `Message<T>` của Spring Messaging thay vì chỉ lấy payload. Ví dụ biến đổi payload chuỗi và sao chép các header thích hợp:

~~~java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

Function<Flux<Message<String>>, Flux<Message<String>>> labelMessages =
    messages -> messages.map(message ->
        MessageBuilder
            .withPayload("checked:" + message.getPayload())
            .copyHeaders(message.getHeaders())
            .build()
    );
~~~

Các header do hệ thống quản lý như ID và timestamp có thể được xây lại; việc sao chép cũng không thay thế quy tắc của từng binder. Khi cần giữ quan hệ đầu vào/đầu ra, hãy xác định rõ các header nghiệp vụ nào bắt buộc (ví dụ `correlationId`) và kiểm tra qua adapter thật.

Nếu dùng `Flux<OrderEvent>` thay vì `Flux<Message<OrderEvent>>`, logic nghiệp vụ đơn giản hơn, nhưng thông tin envelope có thể không còn sẵn trong hàm. Đây là lựa chọn giữa hàm thuần payload và hàm có ý thức về message metadata.

## 9. FunctionCatalog, HTTP, sự kiện và serverless

Một bean `@Bean Function<Flux<OrderEvent>, Flux<Decision>>` vẫn là logic Java thuần. `FunctionCatalog` giúp tìm hàm theo tên, xử lý metadata kiểu, chuyển đổi phù hợp và thực hiện composition; adapter quyết định cách gọi hàm trong môi trường cụ thể.

~~~mermaid
flowchart LR
    HTTP[HTTP request] --> Adapter[Spring Cloud Function adapter]
    Event[Event source / broker] --> Adapter
    Serverless[Serverless trigger] --> Adapter
    Adapter --> Catalog[FunctionCatalog]
    Catalog --> Fn[Reactive Function]
    Fn --> Pub[Mono / Flux kết quả]
    Pub --> Adapter
~~~

Các điểm cần phân biệt:

- **Qua HTTP:** Một request có thể được adapter chuyển thành publisher đầu vào và publisher kết quả được chuyển thành HTTP response. Việc trả kết quả một lần, streaming, định dạng JSON hoặc SSE tùy adapter, headers và cấu hình web đang dùng. Không mặc định `Flux` sẽ luôn được đẩy ngay lập tức đến client theo từng phần tử.
- **Qua broker/sự kiện:** Binder quyết định cách subscribe, gửi thông điệp đầu ra và quản lý acknowledgment/retry. Một `Function<Flux<T>, Flux<R>>` có thể xử lý luồng liên tục và phát số lượng kết quả khác số message đầu vào. Cần kiểm tra cách binder đang sử dụng liên kết lỗi, backpressure, partition và metadata.
- **Qua serverless:** Runtime có thể kích hoạt hàm theo từng invocation và giới hạn thời gian thực thi. Một luồng vô hạn không phù hợp với mọi hình thức serverless; cần xác định giới hạn invocation, cách chờ kết quả và hành vi khi hết thời gian.

Khi module có nhiều bean, cấu hình `spring.cloud.function.definition` để adapter biết hàm nào được export/đưa vào binding. Đây cũng là điểm chọn chuỗi composition `functionA|functionB`. Đừng nhầm `definition` với việc tạo thêm một bean nghiệp vụ mới.

### 9.1. Vấn đề đặc biệt với reactive function

Với hàm phản ứng nhận `Flux`, khái niệm “một lời gọi hàm” và “một phần tử đi qua hàm” là hai việc khác nhau. Lambda có thể chỉ được gọi một lần để tạo pipeline cho publisher dài hạn; các phép `map`/`flatMap` bên trong chạy theo từng phần tử. Vì vậy:

- Không đặt khởi tạo trạng thái nghiệp vụ theo từng đơn hàng ở ngoài toán tử `map`/`flatMap`.
- Không dùng biến có thể thay đổi ở cấp bean để giữ dữ liệu của riêng một message, trừ khi đã thiết kế đồng bộ và phạm vi rõ ràng.
- Không giả định giao dịch, retry hoặc acknowledgment sẽ tự động là một lần cho mỗi phần tử chỉ vì hàm có kiểu `Flux`.

## 10. Kiểm thử hành vi phản ứng

`StepVerifier` từ thư viện `reactor-test` giúp kiểm tra tín hiệu, thứ tự, hoàn tất và lỗi mà không phải tự gọi `subscribe()` trong test. Với cấu hình `OrderFunctions` ở trên:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class OrderFunctionsTest {

    private final OrderFunctions functions = new OrderFunctions();

    @Test
    void checksEachOrder() {
        Flux<OrderFunctions.OrderEvent> input = Flux.just(
            new OrderFunctions.OrderEvent("O-100", 120),
            new OrderFunctions.OrderEvent("O-101", 0)
        );

        StepVerifier.create(functions.checkOrders().apply(input))
            .expectNext(
                new OrderFunctions.Decision("O-100", true),
                new OrderFunctions.Decision("O-101", false)
            )
            .verifyComplete();
    }

    @Test
    void sumsFiniteStream() {
        Flux<OrderFunctions.OrderEvent> input = Flux.just(
            new OrderFunctions.OrderEvent("O-100", 120),
            new OrderFunctions.OrderEvent("O-101", 0)
        );

        StepVerifier.create(functions.sumAmounts().apply(input))
            .expectNext(120L)
            .verifyComplete();
    }
}
~~~

Với hàm có I/O, nên kiểm thử cả trường hợp `Mono.empty()`, `Flux.empty()`, lỗi, timeout, hủy và thứ tự khi chạy đồng thời. Một bài test bean thuần xác nhận logic Reactor; để xác nhận chuyển đổi payload, việc chọn definition, định dạng HTTP hoặc giao nhận message, cần thêm integration test qua adapter/binder thực tế.

## 11. Lỗi thiết kế thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Hàm trả `Flux` nhưng không có kết quả | Chưa có subscription; hoặc đang chờ luồng kết thúc | Kiểm tra subscriber và xem có dùng toán tử tổng hợp như `reduce`/`collectList` trên luồng vô hạn không |
| Hàm trả `Flux<Mono<R>>` | Dùng `map` với lời gọi trả `Mono<R>` | Dùng `flatMap`/`concatMap` phù hợp |
| Xử lý chậm, nghẽn khi tăng tải | Dùng JDBC, `block()` hoặc API chặn trong pipeline | Thay bằng API reactive, hoặc cô lập blocking trên `boundedElastic` |
| Kết quả sai thứ tự | `flatMap` hoàn tất không theo thứ tự đầu vào | Cân nhắc `concatMap` hoặc `flatMapSequential` |
| Một lỗi làm dừng tất cả | `onError` kết thúc subscription | Xác định phạm vi xử lý lỗi ở từng tác vụ con hoặc chấp nhận dừng theo nghiệp vụ |
| Dữ liệu nguồn bị gửi lại | Publisher cold được subscribe nhiều lần hoặc supplier được gọi lại | Thiết kế idempotency, trạng thái nguồn và chính sách replay |
| Bộ nhớ tăng khi chạy luồng dài | `collectList`, buffer không giới hạn hoặc concurrency quá lớn | Tổng hợp theo cửa sổ, giới hạn đồng thời/dung lượng |
| Mất correlation ID | Chỉ biến đổi payload và bỏ envelope | Dùng `Message<T>` và bảo toàn header nghiệp vụ cần thiết |
| HTTP phản hồi không streaming như kỳ vọng | Khả năng stream phụ thuộc adapter và content negotiation | Kiểm tra adapter, media type và integration test |
| Tác vụ `Consumer` khó theo dõi lỗi | Subscription nội bộ tách rời caller | Quản lý subscription hoặc dùng hàm trả publisher hoàn tất khi thích hợp |

## 12. Câu hỏi tự kiểm tra

1. Vì sao `Function<Flux<Order>, Mono<Long>>` có thể không phát kết quả nếu nguồn sự kiện chạy vô hạn?
2. Khi gọi API trả `Mono<Decision>` cho mỗi `Order`, tại sao `map` và `flatMap` tạo ra hai kiểu đầu ra khác nhau?
3. Một lỗi bên trong `flatMap` tác động thế nào đến toàn bộ subscription? Đặt `onErrorResume` ở đâu nếu cần xử lý lỗi độc lập cho từng đơn?
4. Ai chịu trách nhiệm subscribe và cancel publisher khi hàm được gọi qua adapter Spring Cloud Function? Điều gì có thể xảy ra nếu bean tự `subscribe()`?
5. Cần kiểm thử thêm những gì trước khi dùng cùng một reactive function qua HTTP và event binder?

**Ghi nhớ:** `Mono` biểu diễn 0–1 phần tử, `Flux` biểu diễn 0–N phần tử; cả hai đều là publisher với tín hiệu hoàn tất/lỗi. Trong Spring Cloud Function, chữ ký reactive quyết định hợp đồng xử lý dữ liệu, trong khi `FunctionCatalog` và adapter quyết định cách logic đó được đưa vào giao thức gọi cụ thể. Viết pipeline trả publisher, xác định rõ ranh giới subscription, xử lý lỗi đúng phạm vi và kiểm thử hành vi của adapter là những bước cốt lõi để tái sử dụng cùng một hàm một cách tin cậy.
