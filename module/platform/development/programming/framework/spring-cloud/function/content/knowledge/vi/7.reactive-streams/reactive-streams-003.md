# Supplier<Flux<T>> với luồng hữu hạn và luồng liên tục

## 1. Bối cảnh: một Supplier có thể phát bao nhiêu dữ liệu?

Trong **Spring Cloud Function**, `Supplier<T>` đại diện cho nguồn cung cấp dữ liệu: không nhận đối số khi gọi `get()`, nhưng tạo ra một kết quả. Thay `T` bằng `Flux<T>` của Project Reactor, ta có một nguồn trả **publisher** phát 0, 1 hoặc nhiều phần tử theo thời gian.

~~~java
Supplier<Flux<String>> ids =
    () -> Flux.just("ORD-101", "ORD-102", "ORD-103");
~~~

Lần gọi `ids.get()` trả một `Flux<String>`. Với ví dụ trên, Flux là nguồn *cold*: các phần tử chỉ được phát khi có subscriber. `Supplier.get()` không được gọi một lần cho mỗi ID. Cả ba ID nằm trong cùng một publisher.

Điều cần phân biệt là **chữ ký `Supplier<Flux<T>>` không quyết định luồng có kết thúc hay không**:

- **Luồng hữu hạn** phát một số lượng phần tử xác định (hoặc có thể hữu hạn nhưng chưa biết trước), sau đó phát `onComplete`; ví dụ danh sách đơn hàng cần đồng bộ một lần.
- **Luồng liên tục** có thể phát sự kiện mãi cho đến khi bị hủy, nguồn đóng hoặc xảy ra lỗi; ví dụ số liệu cảm biến, heartbeat, thay đổi trạng thái đơn hàng.

Cả hai đều có thể dùng cùng kiểu `Supplier<Flux<T>>`. Sự khác nhau nằm ở **nguồn publisher, cơ chế subscription, tín hiệu kết thúc và cách adapter vận hành**.

Spring Cloud Function cho phép đóng gói logic này độc lập với cách gọi. `FunctionCatalog` dùng để tra cứu và composition function; các adapter có thể đưa chức năng qua HTTP, sự kiện hoặc serverless. Tuy nhiên, mỗi adapter lại quyết định lúc nào gọi `get()`, lúc nào subscribe, cách chuyển mỗi `onNext` thành thông điệp và khi nào hủy subscription.

### Kết quả mong đợi sau bài học

Sau khi học, bạn sẽ biết cách:

1. Viết `Supplier<Flux<T>>` cho một tập hữu hạn và một nguồn phát liên tục.
2. Phân biệt `get()`, `subscribe()`, `onNext` và `onComplete`.
3. Phân biệt nguồn **cold/hot** với luồng **hữu hạn/liên tục**, hai cặp khái niệm độc lập nhau.
4. Chọn cách triển khai khi cần phát một lô dữ liệu, poll định kỳ hoặc đẩy sự kiện theo thời gian thực.
5. Đánh giá vòng đời, backpressure, retry, dữ liệu lặp và đặc điểm HTTP, event binder, serverless.
6. Kiểm thử các nguồn thời gian bằng `StepVerifier.withVirtualTime`.

## 2. Ôn lại hợp đồng của Supplier và Flux

### 2.1. Supplier<T> và Supplier<Flux<T>>

Java định nghĩa `Supplier<T>` với một phương thức duy nhất:

~~~java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
~~~

Ta có thể dùng ba cách trả dữ liệu:

| Chữ ký | Một lần gọi `get()` trả về | Trường hợp phù hợp |
| --- | --- | --- |
| `Supplier<Order>` | Một đối tượng `Order` | Cung cấp một giá trị tại thời điểm được gọi |
| `Supplier<Mono<Order>>` | Publisher có tối đa một `Order` mỗi subscription | Một kết quả bất đồng bộ, có thể không tìm thấy |
| `Supplier<Flux<Order>>` | Publisher phát 0 đến N `Order` mỗi subscription | Danh sách, lô dữ liệu, luồng sự kiện liên tục |

Ví dụ:

~~~java
Supplier<String> single = () -> "ORD-101";

Supplier<Mono<String>> oneAsync =
    () -> Mono.just("ORD-101");

Supplier<Flux<String>> manyAsync =
    () -> Flux.just("ORD-101", "ORD-102");
~~~

`Flux` không buộc dữ liệu chạy song song, không tự xử lý I/O không chặn và không có nghĩa toàn bộ dữ liệu đã nằm trong bộ nhớ. Nó biểu diễn dòng tín hiệu mà caller hoặc adapter phải tiêu thụ bằng subscription.

### 2.2. Các tín hiệu quyết định vòng đời

Một publisher phát các tín hiệu:

- `onSubscribe`: subscription được thiết lập.
- `onNext(value)`: một phần tử mới được phát.
- `onComplete`: kết thúc bình thường, không phát thêm phần tử.
- `onError(error)`: kết thúc do lỗi; không còn `onComplete` sau đó.

Subscriber có thể yêu cầu dữ liệu qua `request(n)` (*backpressure*) và hủy bằng `cancel()`. Khi hủy, publisher không còn bắt buộc tiếp tục phát dữ liệu cho subscriber đó.

~~~mermaid
flowchart TD
    G["Supplier.get()"] --> P["Flux<T>"]
    P --> S["Subscriber đăng ký"]
    S --> N["onNext(T)"]
    N --> D{"Nguồn còn hoạt động?"}
    D -->|Có phần tử mới| N
    D -->|Kết thúc bình thường| C["onComplete"]
    D -->|Có lỗi| E["onError"]
    S -->|Hủy đăng ký| X["cancel"]
~~~

**Ba bộ đếm khác nhau:** một lần `get()` có thể tạo publisher, một lần `subscribe()` có thể tiêu thụ publisher đó, và mỗi subscription có thể dẫn đến nhiều lần `onNext`. Không suy ra số lần gọi `get()` từ số message được phát.

## 3. Supplier trả luồng hữu hạn

Luồng hữu hạn phù hợp với **khởi tạo dữ liệu**, **xuất một đợt bản ghi**, **đẩy danh sách nhiệm vụ cần chạy** hoặc **đọc một trang kết quả**. Ví dụ một lần cung cấp ba đơn hàng:

~~~java
import java.util.function.Supplier;
import reactor.core.publisher.Flux;

Supplier<Flux<String>> initialOrders =
    () -> Flux.just("ORD-101", "ORD-102", "ORD-103");
~~~

Một subscription vào publisher cold này nhận lần lượt ba `onNext` và một `onComplete`. `get()` không trả `List<String>` đã xử lý xong; nó trả `Flux<String>` mô tả chuỗi dữ liệu.

### 3.1. Một số cách tạo luồng hữu hạn

~~~java
// Tập giá trị đã biết:
Flux<String> fromValues = Flux.just("A", "B", "C");

// Dãy số hữu hạn:
Flux<Integer> fromRange = Flux.range(1, 5);

// Nguồn Iterable, lấy iterator khi được subscribe:
Flux<String> fromIterable =
    Flux.fromIterable(java.util.List.of("A", "B", "C"));

// Luồng rỗng: không có onNext nhưng có onComplete.
Flux<String> empty = Flux.empty();

// Dòng theo thời gian nhưng dừng sau ba phần tử:
Flux<Long> firstThreeTicks =
    Flux.interval(java.time.Duration.ofSeconds(1)).take(3);
~~~

`take(3)` làm đầu ra **hữu hạn**, dù nguồn `Flux.interval` có khả năng phát tiếp không giới hạn. Sau khi nhận đủ ba phần tử, `take` hủy đăng ký nguồn và hoàn tất publisher kết quả.

### 3.2. Muốn đọc dữ liệu mới khi subscribe?

Hai cách viết sau có khác biệt về thời điểm truy xuất:

~~~java
// Gọi loadPending() ngay khi get() tạo Flux:
Supplier<Flux<Order>> eagerAtGet =
    () -> Flux.fromIterable(loadPending());

// Chỉ gọi loadPending() cho mỗi subscription:
Supplier<Flux<Order>> deferredToSubscribe =
    () -> Flux.defer(
        () -> Flux.fromIterable(loadPending())
    );
~~~

Ở đây `Order` và `loadPending()` là đối tượng/hàm giả định. `Flux.defer` tạo publisher từ factory cho mỗi subscription. Nó hữu ích khi cần dữ liệu mới tại thời điểm tiêu thụ hoặc khi muốn cô lập thao tác tạo nguồn; nhưng nếu `loadPending()` là truy vấn blocking, chạy nó trực tiếp trong callback `defer` vẫn **có thể chặn thread đang subscribe**. Hãy ưu tiên repository reactive hoặc di chuyển nguồn blocking lên scheduler phù hợp như `boundedElastic` trong khi chuyển đổi dần.

Với nguồn cold, subscribe hai lần có thể đọc dữ liệu và chạy tác dụng phụ hai lần. Việc lặp là cơ chế Reactor bình thường; trong tích hợp broker, cần bổ sung **idempotency** nếu cùng đơn hàng không được tạo hai lần.

## 4. Supplier trả luồng liên tục

Một nguồn liên tục có thể phát nhiều sự kiện theo thời gian và không tự kết thúc trong điều kiện bình thường. Ví dụ heartbeat mỗi giây:

~~~java
import java.time.Duration;
import java.util.function.Supplier;
import reactor.core.publisher.Flux;

Supplier<Flux<Long>> heartbeat =
    () -> Flux.interval(Duration.ofSeconds(1));
~~~

`Flux.interval(Duration.ofSeconds(1))` phát `0L` sau khoảng một giây kể từ lúc subscription, rồi `1L`, `2L`,... theo chu kỳ. Mỗi subscription vào publisher này thường có bộ đếm và lịch phát riêng, nên nguồn này là **cold theo từng subscription**, dù có thể chạy liên tục.

Nguồn sẽ không tự `onComplete`; nó dừng khi subscription bị hủy, có lỗi (chẳng hạn không đáp ứng yêu cầu backpressure của `Flux.interval`), hoặc vòng đời ứng dụng kết thúc. Không nên dùng `Flux.interval` để phát bản ghi nghiệp vụ cần lưu bền vững: tick được tạo trong bộ nhớ, không được khôi phục mặc định sau restart.

### 4.1. Mỗi phần tử có thể là một sự kiện nghiệp vụ

~~~java
record SensorEvent(String sensorId, long sequence) {}

Supplier<Flux<SensorEvent>> sensorEvents =
    () -> Flux.interval(Duration.ofSeconds(2))
        .map(sequence -> new SensorEvent("sensor-01", sequence));
~~~

Trong ví dụ này:

1. `sensorEvents.get()` tạo mô tả luồng.
2. Một subscription tạo lịch phát cho nguồn `interval`.
3. Mỗi tick chạy `map` và phát một `SensorEvent`.
4. Việc phát tiếp diễn trong khi subscription hoạt động.

Một nguồn sự kiện thực tế có thể lấy dữ liệu từ Kafka, RabbitMQ, WebSocket hoặc API reactive. Khi đó thời điểm nhận, tốc độ phát, khả năng replay, dữ liệu bị mất và quản lý kết nối do thư viện nguồn và adapter phối hợp quyết định.

### 4.2. Luồng liên tục không nhất thiết có phần tử đều đặn

`Flux.never()` cũng là publisher không hoàn tất, nhưng **không phát phần tử nào**. Một nguồn SSE/WebSocket có thể im lặng nhiều giờ rồi mới phát dữ liệu. Vì vậy, “luồng liên tục” mô tả khả năng **duy trì subscription**, không cam kết luôn có dữ liệu hay một tốc độ phát cố định.

## 5. Ví dụ Spring Cloud Function hoàn chỉnh

Cấu hình dưới đây tạo hai bean `Supplier<Flux<T>>`: một nguồn phát **hai đơn hàng rồi hoàn tất** và một nguồn heartbeat **duy trì đến khi bị hủy**. Ví dụ dùng Java 17+ (do có `record`), Spring Cloud Function và Project Reactor.

~~~java
package demo.functions;

import java.time.Duration;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class OrderSuppliers {

    public record OrderEvent(String orderId, long amountCents) { }

    @Bean
    public Supplier<Flux<OrderEvent>> initialOrders() {
        return () -> Flux.just(
            new OrderEvent("ORD-101", 12_000),
            new OrderEvent("ORD-102", 8_500)
        );
    }

    @Bean
    public Supplier<Flux<Long>> heartbeat() {
        return () -> Flux.interval(Duration.ofSeconds(1));
    }
}
~~~

Hai bean cùng có kiểu `Supplier<Flux<...>>`, nhưng hợp đồng kết thúc khác nhau:

| Tiêu chí | `initialOrders` | `heartbeat` |
| --- | --- | --- |
| Số phần tử từ một subscription | 2 | Không có giới hạn hữu hạn cố định |
| Nguồn | `Flux.just` | `Flux.interval` |
| Tín hiệu kết thúc bình thường | `onComplete` sau phần tử thứ hai | Không tự phát `onComplete` nếu không bị giới hạn |
| Thời điểm phát | Theo nhu cầu của subscriber | Theo lịch mỗi giây |
| Dữ liệu sau restart | Hai đơn có thể được phát lại nếu nguồn được gọi/subscribe lại | Bộ đếm tick mới bắt đầu theo subscription mới |
| Để ngừng tiêu thụ | Luồng tự hoàn tất | Cần `cancel`, hủy adapter hoặc giới hạn bằng toán tử như `take` |
| Rủi ro đặc thù | Tạo lại tác dụng phụ nếu phát trùng đơn | Thiếu backpressure, nguồn không dừng, thời gian sống quá dài |

### 5.1. Truy xuất và biến đổi qua FunctionCatalog

`FunctionCatalog` cho phép ứng dụng tìm hàm theo tên và thực hiện composition. Giả sử ta muốn giữ lại các đơn có số tiền dương:

~~~java
@Bean
public java.util.function.Function<
        Flux<OrderEvent>, Flux<OrderEvent>> positiveOrders() {
    return orders -> orders.filter(order -> order.amountCents() > 0);
}
~~~

Bean `positiveOrders` được thêm vào cùng cấu hình chứa `OrderEvent`. Khi adapter hỗ trợ composition của Spring Cloud Function, definition có thể ghép supplier và function:

~~~properties
spring.cloud.function.definition=initialOrders|positiveOrders
~~~

Ở mức logic, `initialOrders` phát `Flux<OrderEvent>` và `positiveOrders` nhận chính luồng đó để lọc. Toán tử `filter` chạy theo từng phần tử, không làm `initialOrders.get()` chạy lại cho mỗi đơn.

Cần kiểm tra tên binding và hợp đồng output của **composition đã chọn** ở adapter đang dùng. Chỉ khai báo definition không tự khởi động broker, HTTP server hay lịch phát: những việc đó thuộc môi trường triển khai.

## 6. Ai gọi Supplier? Ai subscribe? Ai nhận từng phần tử?

Ba bước này thường ở ba nơi khác nhau:

~~~mermaid
flowchart LR
    A["Application / adapter"] -->|get()| S["Supplier<Flux<T>>"]
    S -->|trả về| F["Flux<T>"]
    A -->|subscribe| F
    F -->|onNext T1| O["Subscriber / adapter"]
    F -->|onNext T2| O
    F -->|onComplete hoặc onError| O
    O --> R["HTTP response / event output"]
~~~

- **Spring Cloud Function Core:** Bean `Supplier` là một hàm Java; bản thân nó không tạo scheduler, broker hay tự subscribe vô điều kiện. Caller hoặc adapter kích hoạt.
- **Spring Cloud Stream:** Với cách tích hợp supplier reactive được hỗ trợ, framework thường gọi supplier để lấy `Flux` rồi giữ subscription xử lý dữ liệu phát ra. Không nên giả định mô hình polling của supplier imperative được áp dụng nguyên xi cho `Supplier<Flux<T>>`.
- **HTTP adapter:** Một request có thể kích hoạt function và tiêu thụ publisher trong phạm vi request. Việc chuyển `Flux` thành một phản hồi JSON hữu hạn hay streaming phụ thuộc adapter, media type, cấu hình và khả năng client.
- **Serverless adapter:** Một invocation thường có giới hạn thời gian. Một `Flux` không kết thúc có thể không phù hợp nếu runtime cần đợi kết quả hoặc đóng invocation.

**Không gọi `subscribe()` thủ công bên trong một supplier chỉ để “đẩy dữ liệu đi”.** Hãy trả publisher cho adapter quản lý subscription, lỗi và cancellation. Tự subscribe bên trong làm phát sinh một subscription riêng, dễ khiến dữ liệu chạy trước khi caller sẵn sàng hoặc tách lỗi khỏi cơ chế quản lý của adapter.

## 7. Triển khai qua Spring Cloud Stream: luồng hữu hạn và liên tục

Khi ứng dụng có Spring Cloud Stream cùng binder tương ứng, một supplier có thể là nguồn cho một output binding. Ví dụ **chọn riêng `heartbeat`**:

~~~properties
spring.cloud.function.definition=heartbeat
spring.cloud.stream.bindings.heartbeat-out-0.destination=heartbeat-events
~~~

Giá trị `heartbeat-out-0` là tên binding output theo quy ước chức năng ở trường hợp bean đơn. Đích `heartbeat-events` là tên logic tùy binder ánh xạ tới broker. Cần cài dependency binder, cấu hình kết nối và serialization đúng với môi trường; riêng các property trên không tạo broker.

Nếu chỉ muốn xuất **lô đơn hàng hữu hạn**, có thể chuyển sang:

~~~properties
spring.cloud.function.definition=initialOrders
spring.cloud.stream.bindings.initialOrders-out-0.destination=initial-orders
~~~

Chỉ chọn một definition trong ví dụ cấu hình; các snippet này là **hai lựa chọn độc lập**.

### 7.1. Khác biệt quan trọng về lịch gọi

Với supplier imperative `Supplier<T>`, một số tích hợp Spring Cloud Stream dùng poller để gọi `get()` theo chu kỳ. Với **reactive supplier `Supplier<Flux<T>>`**, cách xử lý thông thường là kích hoạt supplier để lấy publisher và subscribe vào publisher đó, rồi nhận dữ liệu từ pipeline reactive. Vì thế:

- `Flux.just(a, b)` phát `a` và `b`, sau đó hoàn tất; đừng mong binder mặc định gọi lại `get()` mỗi giây để phát cả lô lần nữa.
- `Flux.interval(...)` có thể tiếp tục phát các tick trong một subscription dài hạn; không cần poller gọi lại `get()` cho mỗi tick.
- Nếu cần lặp lại lô dữ liệu định kỳ, hãy **mô tả việc lặp theo thời gian ngay trong publisher** hoặc dùng cơ chế scheduler riêng được thiết kế rõ ràng.
- Trên restart, reconnect hoặc khi retry được cấu hình, có thể hình thành subscription mới. Vì thế không nên giả định “tối đa một lần gửi” chỉ vì bên trong là reactive supplier.

Hành vi gọi, quản lý lifecycle, backpressure và truyền lỗi cuối cùng phụ thuộc **phiên bản framework, binder và cấu hình đang chạy**. Nên xác minh bằng integration test với broker thật khi yêu cầu giao hàng có ý nghĩa nghiệp vụ.

### 7.2. Luồng hữu hạn chạy xong thì chuyện gì xảy ra?

Khi `initialOrders` hoàn tất bình thường, publisher báo `onComplete`. Không còn dữ liệu mới từ subscription đó. Điều này **không đồng nghĩa ứng dụng Spring Boot tự dừng** hoặc binding nhất thiết được tái khởi tạo. Nếu chức năng là “đẩy dữ liệu một lần lúc startup”, cần thiết kế số lần phát, điều kiện khởi động lại, cơ chế đánh dấu đã gửi và khả năng đẩy trùng.

### 7.3. Luồng liên tục khi đóng ứng dụng

Nguồn `heartbeat` sẽ tiếp tục tạo tick khi subscription còn sống. Adapter cần hủy subscription lúc ngừng binding hoặc đóng ứng dụng để giải phóng scheduler, kết nối và tài nguyên. Nếu luồng dùng TCP, WebSocket hoặc một SDK ngoại vi, cần biết cơ chế đóng tài nguyên của publisher, không chỉ mong JVM dừng là đủ.

## 8. Cần phát lại lô dữ liệu định kỳ: cách thiết kế rõ ràng

Một nhầm lẫn phổ biến là dùng supplier hữu hạn và mong adapter “tự động gọi lại”. Nếu mục tiêu là **mỗi 30 giây đọc danh sách đơn cần xử lý**, hãy biểu diễn trigger ngay trong Flux. Ví dụ sau là mô hình, trong đó `repository.findPending()` trả về `Flux<OrderEvent>` từ API không chặn:

~~~java
@Bean
public Supplier<Flux<OrderEvent>> pendingOrdersEvery30Seconds() {
    return () -> Flux.interval(
            Duration.ZERO,
            Duration.ofSeconds(30)
        )
        .concatMap(tick -> repository.findPending());
}
~~~

Đoạn trên là **phác thảo tích hợp**; `repository` là dependency của ứng dụng, cần được inject và cài đặt. `Duration.ZERO` cho tick đầu khi subscribe, rồi chờ 30 giây giữa các tick. `concatMap` đảm bảo các đợt truy vấn không được subscribe đồng thời theo thứ tự; nếu truy vấn chậm, tick có thể tồn đọng, vì vậy phải thiết kế giới hạn tải, timeout và lỗi.

Nếu muốn minh họa một chu kỳ **có thể chạy độc lập, không cần repository**, dùng một danh sách cố định:

~~~java
Supplier<Flux<String>> demoEvery30Seconds =
    () -> Flux.interval(Duration.ZERO, Duration.ofSeconds(30))
        .concatMap(tick -> Flux.just("ORD-101", "ORD-102"));
~~~

Mỗi lần tick lại phát đúng hai ID trên. Đây là công cụ kiểm thử nhịp phát, **không phải nguồn sự kiện nghiệp vụ chính xác một lần**. Nếu nguồn là database, broker hoặc API, phải có khóa idempotency/checkpoint để không xử lý trùng.

### 8.1. Vì sao không dùng repeat() vô điều kiện?

~~~java
Supplier<Flux<String>> problematic =
    () -> Flux.just("ORD-101", "ORD-102").repeat();
~~~

`repeat()` đăng ký lại sau mỗi `onComplete`. Với publisher hữu hạn phát ngay, đoạn này có thể lặp rất nhanh, tạo CPU load và gửi trùng bản ghi liên tục. Khi cần lặp có kiểm soát, dùng trigger theo thời gian, timer, scheduler hoặc toán tử delay phù hợp với yêu cầu.

### 8.2. Lỗi tại một lần poll không nên mặc nhiên giết cả luồng

Nếu truy vấn thất bại trong `concatMap`, lỗi chưa xử lý sẽ trở thành `onError` của toàn bộ output. Một chính sách bỏ qua chu kỳ poll bị lỗi (chỉ phù hợp khi nghiệp vụ chấp nhận) có thể đặt **trong** inner publisher:

~~~java
Supplier<Flux<OrderEvent>> resilientPoll = () ->
    Flux.interval(Duration.ZERO, Duration.ofSeconds(30))
        .concatMap(tick ->
            repository.findPending()
                .onErrorResume(error -> {
                    log.warn("Poll failed at tick {}", tick, error);
                    return Flux.empty();
                })
        );
~~~

`log` và `repository` là dependency giả định; callback nằm trong mỗi lần truy vấn. Nếu lỗi phải ngăn tiếp tục vì nguy cơ mất dữ liệu hoặc phá vỡ thứ tự, đừng chuyển nó thành `Flux.empty()` mà hãy truyền lỗi đến cơ chế xử lý của hệ thống.

## 9. Luồng hữu hạn, luồng vô hạn và cold/hot là hai trục khác nhau

**Hữu hạn/liên tục** nói về khả năng hoàn tất. **Cold/hot** nói về mối quan hệ giữa nguồn phát và subscription. Không thể suy ra thuộc tính thứ hai từ thuộc tính thứ nhất.

| Ví dụ | Hữu hạn hay liên tục? | Cold hay hot? | Hành vi đáng nhớ |
| --- | --- | --- | --- |
| `Flux.just("A", "B")` | Hữu hạn | Cold | Mỗi subscription có thể phát lại A, B |
| `Flux.range(1, 100)` | Hữu hạn | Cold | Mỗi subscription chạy lại dãy |
| `Flux.interval(Duration.ofSeconds(1))` | Liên tục | Cold theo subscription | Mỗi subscriber có lịch đếm riêng |
| `Flux.interval(...).take(5)` | Hữu hạn | Cold theo subscription | Phát năm tick rồi hoàn tất |
| `Sinks.Many<T>.asFlux()` với nguồn push | Phụ thuộc cách nguồn dừng | Thường hot | Subscriber đến muộn có thể lỡ dữ liệu trước đó |
| Publisher đã dùng `cache()` | Tùy nguồn gốc | Có thể replay dữ liệu đã lưu | Cần cân nhắc bộ nhớ, lịch sử và thời điểm subscription |

### 9.1. Minh họa nguồn hot với Sinks

Một nguồn push vào `Sinks.Many` có thể được dùng làm đầu vào cho supplier:

~~~java
import java.util.function.Supplier;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

Sinks.Many<String> sink =
    Sinks.many().multicast().directBestEffort();

Supplier<Flux<String>> liveEvents = sink::asFlux;

// Ở nơi nhận sự kiện bên ngoài:
Sinks.EmitResult emitted = sink.tryEmitNext("ORD-201");
if (emitted.isFailure()) {
    // Ghi nhận lỗi / quyết định xử lý lại hoặc đưa vào hàng đợi.
}
~~~

`directBestEffort` không phải hàng đợi bền vững và không bảo đảm replay. Với multicast, người subscribe muộn không nhận các sự kiện đã phát trước đó; khi không có nhu cầu đủ hoặc không có subscriber, `tryEmitNext` có thể thất bại. Phần mềm thực tế phải kiểm tra `EmitResult` và quyết định retry/buffer/drop theo hợp đồng nghiệp vụ.

Vì vậy, nguồn hot không nhất thiết tốt hơn nguồn cold. Chọn kiểu nguồn dựa trên yêu cầu **replay, tính bền vững, số subscriber và chính sách khi quá tải**.

## 10. Backpressure và áp lực tài nguyên

Reactive Streams cho phép downstream yêu cầu số lượng dữ liệu bằng `request(n)`. Điều này quan trọng với `Supplier<Flux<T>>` vì nguồn có thể phát nhanh hơn tốc độ xử lý hoặc tốc độ broker gửi đi.

### 10.1. Với nguồn hữu hạn

Nếu nguồn phát một triệu bản ghi:

~~~java
Supplier<Flux<Integer>> oneMillion =
    () -> Flux.range(1, 1_000_000);
~~~

`Flux.range` có thể phát theo nhu cầu subscriber mà không cần tạo một `List` một triệu phần tử trước. Nhưng nếu thêm `collectList()`, toàn bộ dữ liệu có thể được giữ trong bộ nhớ. Nếu thêm `flatMap` gọi I/O với concurrency quá lớn, số tác vụ đang hoạt động có thể vượt khả năng hệ thống.

### 10.2. Với nguồn liên tục

`Flux.interval` là nguồn thời gian: nếu downstream không theo kịp và không có yêu cầu phần tử, nó có thể báo lỗi tràn yêu cầu (*overflow*) thay vì tự giảm tốc vô hạn. Các toán tử sau có các đánh đổi riêng:

| Cách ứng phó | Điều gì xảy ra? | Phù hợp khi |
| --- | --- | --- |
| `onBackpressureDrop()` | Bỏ phần tử khi downstream không thể nhận | Telemetry cho phép mất mẫu |
| `onBackpressureLatest()` | Giữ giá trị gần nhất thay cho các giá trị cũ | Cập nhật trạng thái hiện thời |
| `onBackpressureBuffer(capacity)` | Giữ phần tử tạm trong buffer hữu hạn | Cho phép tăng vọt ngắn hạn với dung lượng có giới hạn |
| Hạn chế concurrency/nhịp phát | Giảm số tác vụ đang chạy hoặc giảm tốc nguồn | Dữ liệu nghiệp vụ cần ưu tiên tính toàn vẹn |
| Đưa vào broker/hàng đợi bền vững | Tách tốc độ producer và consumer với chính sách lưu giữ | Message không được phép mất |

Không áp dụng `onBackpressureDrop` cho đơn hàng, thanh toán hoặc tác vụ bắt buộc xử lý đủ, trừ khi có cơ chế khác đảm bảo khôi phục dữ liệu. `onBackpressureBuffer()` không giới hạn cũng có nguy cơ hết bộ nhớ. Tín hiệu backpressure bên trong Reactor không tự bảo đảm broker hoặc API bên ngoài tuân theo cùng một giới hạn.

### 10.3. Giám sát và hủy subscription

Có thể quan sát các mốc vòng đời:

~~~java
Supplier<Flux<Long>> observed = () ->
    Flux.interval(Duration.ofSeconds(1))
        .doOnSubscribe(subscription ->
            System.out.println("heartbeat subscribed"))
        .doOnNext(tick ->
            System.out.println("tick=" + tick))
        .doFinally(signal ->
            System.out.println("finished by " + signal));
~~~

`doFinally` có thể nhận `CANCEL` khi subscriber hủy, `ON_COMPLETE` khi hoàn tất, hoặc `ON_ERROR` khi lỗi. Tác dụng phụ ở đây chỉ minh họa quan sát; môi trường production nên dùng logging/metrics với giới hạn tốc độ ghi log.

## 11. Lỗi, retry và bảo đảm giao hàng

Nếu publisher trong supplier phát `onError`, subscription hiện tại kết thúc. Hãy phân biệt **khởi động lại publisher** với **gửi lại dữ liệu nghiệp vụ**:

~~~java
Supplier<Flux<String>> retrying =
    () -> fetchFromRemoteSource()
        .retry(2);
~~~

`fetchFromRemoteSource()` là factory/nguồn giả định trả `Flux<String>`. `retry(2)` cho phép retry tối đa hai lần sau lỗi theo semantics của Reactor, bằng cách đăng ký lại upstream. Nếu nguồn đã phát vài phần tử trước khi lỗi, các phần tử đó **có thể được phát lại** khi subscription mới bắt đầu. Hãy thiết kế nguồn và consumer idempotent hoặc có cơ chế resume/checkpoint phù hợp.

Đối với nguồn liên tục, retry không giới hạn có thể tạo vòng khôi phục liên tục khi hệ thống bên ngoài lỗi. Cần backoff, giới hạn retry, quan sát và xác định khi nào phải báo thất bại lên adapter.

### 11.1. Bảo đảm message không đến từ kiểu Flux

`Supplier<Flux<T>>` tự nó **không** bảo đảm exactly-once, ít nhất một lần, thứ tự bền vững hoặc acknowledgment. Những yếu tố đó phụ thuộc binder, transaction, thiết kế producer/consumer và hệ thống bên ngoài. Khi nguồn hữu hạn phát lại sau restart, hệ thống đích có thể nhận trùng. Khi nguồn hot bị ngắt, sự kiện có thể mất nếu không có cơ chế lưu trữ/replay.

Đối với sự kiện quan trọng, xác định rõ khóa idempotency (ví dụ `eventId`), vị trí checkpoint, retry, dead-letter handling và chính sách khôi phục khi ứng dụng ngừng giữa chừng.

## 12. Message<T> và metadata cho từng sự kiện

Khi nguồn cần phát header như correlation ID hoặc loại sự kiện, `Supplier<Flux<Message<T>>>` giúp gắn metadata **trên từng phần tử**:

~~~java
import java.time.Duration;
import java.util.function.Supplier;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

Supplier<Flux<Message<Long>>> heartbeatMessages = () ->
    Flux.interval(Duration.ofSeconds(1))
        .map(sequence ->
            MessageBuilder.withPayload(sequence)
                .setHeader("eventType", "HEARTBEAT")
                .setHeader("source", "inventory-service")
                .build()
        );
~~~

`Message<Long>` chứa payload và header của từng tick. Khi adapter chuyển thành message broker, header nào được truyền nguyên vẹn, định dạng dữ liệu và cách ánh xạ metadata phụ thuộc binder/serialization. `Flux<Message<T>>` **không** có nghĩa cả Flux là một message duy nhất; trong cấu hình binder hỗ trợ, các phần tử có thể được chuyển thành các message riêng.

Nếu một function downstream dùng `Flux<Message<T>>` để lọc/biến đổi, cần bảo toàn những header nghiệp vụ quan trọng. Khi composition gom N phần tử thành một kết quả, phải quy định cụ thể metadata nào cần giữ hoặc tổng hợp.

## 13. Kiểm thử nguồn hữu hạn và nguồn liên tục

Trong kiểm thử Reactor, `StepVerifier` giúp xác nhận phần tử, tín hiệu hoàn tất và lỗi. Ví dụ sau dùng đúng class `OrderSuppliers` ở mục 5 và dependency `reactor-test` cùng JUnit 5.

### 13.1. Kiểm thử luồng hữu hạn kết thúc

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class OrderSuppliersTest {

    private final OrderSuppliers suppliers = new OrderSuppliers();

    @Test
    void initialOrdersEmitsTwoThenCompletes() {
        StepVerifier.create(suppliers.initialOrders().get())
            .expectNext(
                new OrderSuppliers.OrderEvent("ORD-101", 12_000),
                new OrderSuppliers.OrderEvent("ORD-102", 8_500)
            )
            .verifyComplete();
    }
}
~~~

`verifyComplete()` xác nhận sau hai phần tử có `onComplete` và không có `onError`.

### 13.2. Kiểm thử luồng liên tục bằng thời gian ảo

Không cần đợi thật ba giây để test heartbeat. `StepVerifier.withVirtualTime` thay scheduler thời gian bằng bộ lập lịch mô phỏng, miễn publisher được tạo **bên trong** supplier factory truyền cho StepVerifier:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class HeartbeatTest {

    @Test
    void heartbeatCanBeLimitedToThreeTicks() {
        OrderSuppliers suppliers = new OrderSuppliers();

        StepVerifier.withVirtualTime(
                () -> suppliers.heartbeat().get().take(3)
            )
            .thenAwait(Duration.ofSeconds(3))
            .expectNext(0L, 1L, 2L)
            .verifyComplete();
    }
}
~~~

`take(3)` làm publisher được test hoàn tất sau ba tick bằng cách hủy upstream. **Không kết luận** rằng `heartbeat` tự phát `onComplete` sau ba giây; nếu bỏ `take`, nó được thiết kế tiếp tục phát.

### 13.3. Đếm get(), subscription và phần tử

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicInteger getCalls = new AtomicInteger();
AtomicInteger subscriptions = new AtomicInteger();
AtomicInteger items = new AtomicInteger();

Supplier<Flux<String>> feed = () -> {
    getCalls.incrementAndGet();

    return Flux.just("A", "B")
        .doOnSubscribe(s -> subscriptions.incrementAndGet())
        .doOnNext(value -> items.incrementAndGet());
};

Flux<String> result = feed.get();
// getCalls=1; subscriptions=0; items=0

StepVerifier.create(result)
    .expectNext("A", "B")
    .verifyComplete();
// getCalls=1; subscriptions=1; items=2

StepVerifier.create(result)
    .expectNext("A", "B")
    .verifyComplete();
// getCalls=1; subscriptions=2; items=4
~~~

Với nguồn cold này, hai subscriptions phát lại `A` và `B` nhưng không làm `feed.get()` chạy lại. Nếu gọi `feed.get()` lần nữa, `getCalls` mới tăng. Trên nguồn hot hoặc publisher chia sẻ, kết quả số lần phát có thể khác.

### 13.4. Những integration test cần có

Unit test Reactor chỉ kiểm tra publisher. Trước khi dùng một supplier qua adapter thực tế, hãy kiểm tra thêm: liệu definition đã chọn đúng bean chưa; output binding có đúng destination không; luồng hữu hạn hoàn tất có được subscribe lại ngoài ý muốn không; luồng liên tục có dừng khi shutdown không; binder phản ứng thế nào khi broker chậm, lỗi, khởi động lại; và hệ thống có phát trùng/mất thông điệp hay không.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Diễn giải chính xác |
| --- | --- |
| “Một `Supplier<Flux<T>>` phát đúng một giá trị.” | Một `get()` trả một **publisher**; publisher có thể phát 0 đến N giá trị. |
| “`Flux` luôn là luồng vô hạn.” | `Flux.just`, `range`, `empty` hoặc `take` đều có thể hữu hạn. |
| “Luồng liên tục chắc chắn là hot.” | `Flux.interval` thường là cold theo subscription, dù không tự kết thúc. |
| “Gọi `get()` tức là các phần tử đã được gửi.” | Với publisher cold, các phần tử được phát khi có subscription và nhu cầu downstream. |
| “`Supplier<Flux<T>>` được gọi lại cho mỗi message.” | Adapter reactive thường subscribe một publisher; mỗi `onNext` mới là một phần tử được xử lý. |
| “Luồng hữu hạn sẽ luôn được poll lại khi hoàn tất.” | Không có bảo đảm như vậy; cần kiểm tra adapter và thiết kế lịch tái phát rõ ràng. |
| “`repeat()` là cách tốt để poll.” | Repeat một luồng hoàn tất tức thì có thể tạo vòng lặp rất nhanh và gửi trùng dữ liệu. |
| “Backpressure bảo đảm broker không bao giờ quá tải.” | Khả năng điều tiết phải được hỗ trợ qua toàn bộ pipeline và adapter. |
| “`Flux.interval` phù hợp cho mọi sự kiện quan trọng.” | Tick trong bộ nhớ không có độ bền và cơ chế replay như một event log. |
| “`retry` không ảnh hưởng số lần xử lý dữ liệu.” | Đăng ký lại nguồn có thể phát lại phần tử đã phát trước lỗi. |
| “Serverless có thể đợi luồng vô hạn hoàn tất.” | Runtime có giới hạn invocation; cần thiết kế bounded processing hoặc streaming được hỗ trợ. |

## 15. Lựa chọn thiết kế theo yêu cầu nghiệp vụ

| Yêu cầu | Hướng triển khai nên cân nhắc |
| --- | --- |
| Phát một tập dữ liệu cố định | `Supplier<Flux<T>>` với `Flux.just` / `fromIterable`, phát `onComplete` |
| Truy vấn reactive lấy một lô dữ liệu | Trả publisher từ repository reactive; kiểm soát phân trang và tái phát |
| Cập nhật định kỳ | `Flux.interval` hoặc scheduler → `concatMap` vào nguồn dữ liệu; giới hạn lỗi/tải |
| Phát telemetry có thể bỏ mẫu | Nguồn liên tục và chính sách backpressure phù hợp |
| Phát đơn hàng/sự kiện phải bền vững | Event broker/outbox/checkpoint và idempotency; không dựa vào timer bộ nhớ |
| Một kết quả bất đồng bộ mỗi invocation | Có thể dùng `Supplier<Mono<T>>` |
| Dùng cùng một logic qua HTTP và event binder | Kiểm tra vòng đời subscription, loại response/binding và cơ chế chuyển đổi |
| Thực thi trong invocation serverless ngắn | Ưu tiên nguồn có giới hạn hoặc cắt luồng theo ranh giới thời gian/số lượng |

Một thiết kế tốt phải trả lời được: **Nguồn lấy dữ liệu từ đâu? Khi nào adapter gọi `get()`? Ai subscribe? Điều kiện nào làm luồng hoàn tất hoặc bị hủy? Có được phép phát lại/mất phần tử không?** Chữ ký `Supplier<Flux<T>>` là điểm khởi đầu của hợp đồng dữ liệu, không tự giải quyết những câu hỏi vận hành đó.

## 16. Câu hỏi tự đánh giá

1. `Supplier<Flux<String>>` trả `Flux.just("A","B")`. Nếu caller gọi `get()` một lần rồi subscribe hai lần vào cùng publisher cold, `get()` chạy mấy lần? Các phần tử được phát bao nhiêu lần?
2. Vì sao `Flux.interval(Duration.ofSeconds(1))` được gọi là luồng liên tục nhưng vẫn có thể là nguồn cold?
3. Luồng `Flux.interval(...).take(5)` có còn là luồng liên tục ở đầu ra không? Subscriber hủy upstream khi nào?
4. Trong Spring Cloud Stream, vì sao không nên trông đợi `Supplier<Flux<Order>>` với `Flux.just(...)` sẽ tự phát lại cùng lô mỗi giây?
5. Khi cần đọc 100 đơn hàng mới mỗi 30 giây, bạn sẽ thiết kế trigger và pipeline thế nào để không gửi trùng hoặc tạo nhiều truy vấn đồng thời?
6. Tại sao `retry(2)` trên một nguồn phát được ba message rồi lỗi có thể dẫn đến message trùng?
7. Với một heartbeat chạy liên tục, làm thế nào dùng thời gian ảo để kiểm thử ba tick mà không đợi thật và không để test treo?
8. Một supplier phát `Flux<Message<T>>` cần lưu ý gì về headers khi qua binder hoặc qua function composition?

**Ghi nhớ:** `Supplier<Flux<T>>` mô tả một nguồn trả **publisher**, còn số phần tử, thời gian phát và việc kết thúc phụ thuộc publisher. `Flux.just(...)` là ví dụ hữu hạn; `Flux.interval(...)` là ví dụ liên tục. Để triển khai an toàn trong Spring Cloud Function, hãy tách rõ lần gọi `get()`, vòng đời subscription, chính sách tái phát và cách adapter đưa từng phần tử ra HTTP, sự kiện hoặc môi trường serverless.
