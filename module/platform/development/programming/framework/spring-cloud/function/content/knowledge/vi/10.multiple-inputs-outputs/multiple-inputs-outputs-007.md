# Ánh xạ chỉ số sang binding của Spring Cloud Stream

## 1. Vì sao cần ánh xạ chỉ số?

Trong **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), nghiệp vụ được viết dưới dạng `Supplier`, `Function` hoặc `Consumer`. Các bean này có thể được tìm qua `FunctionCatalog`, kết hợp bằng composition và nhận dữ liệu đã chuyển đổi kiểu, nhờ đó logic có thể tái sử dụng qua HTTP, sự kiện hoặc môi trường serverless tùy adapter.

Khi triển khai với **Spring Cloud Stream**, framework nối các đầu vào và đầu ra của hàm với hệ thống messaging thông qua những đối tượng gọi là **binding**. Một hàm có thể chỉ có một đầu vào/đầu ra, nhưng cũng có thể có **nhiều cổng** khi dùng reactive function với `TupleN<Flux<...>>`. Khi đó, framework cần một quy tắc nhất quán để xác định **cổng thứ nhất**, **cổng thứ hai**... được cấu hình tới destination nào.

Ví dụ, dịch vụ tiếp nhận:

- Sự kiện tạo đơn hàng từ topic `orders.created`.
- Sự kiện xác nhận thanh toán từ topic `payments.confirmed`.

Dịch vụ phát:

- Chỉ mục đơn hàng tới topic `orders.indexed`.
- Chỉ mục thanh toán tới topic `payments.indexed`.

~~~text
                  indexEvents
               ┌─────────────────┐
orders.created ───► in-0         out-0 ───► orders.indexed
               │                 │
payments.confirmed ► in-1       out-1 ───► payments.indexed
               └─────────────────┘
~~~

Để ứng dụng hoạt động đúng, chúng ta phải hiểu:

1. **Chỉ số cổng** được gán như thế nào.
2. **Binding name** được tạo từ tên hàm và chỉ số ra sao.
3. **Destination** trên broker được chỉ định cho từng binding như thế nào.
4. Thứ tự các phần tử `Tuple2`/`Tuple3` liên hệ thế nào với `-in-0`, `-in-1`, `-out-0`, `-out-1`.

> **Phạm vi:** Bài này nói về functional binding của **Spring Cloud Stream**. Không nên suy rằng cùng một tuple reactive sẽ tự tạo nhiều endpoint HTTP hoặc nhiều kết quả serverless; cách ánh xạ phụ thuộc adapter.

## 2. Phân biệt tên hàm, tên binding và destination

Đây là ba khái niệm có liên hệ nhưng không đồng nhất:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Tên function/bean** | `indexEvents` | Tên hàm được Spring đăng ký và chọn để bind |
| **Tên binding** | `indexEvents-in-0` | Định danh cổng bên trong cấu hình Spring Cloud Stream |
| **Destination** | `orders.created` | Topic, queue, exchange hoặc đích vật lý/logic do binder quản lý |

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: indexEvents
    stream:
      bindings:
        indexEvents-in-0:
          destination: orders.created
~~~

`spring.cloud.function.definition` cho biết hàm nào được kích hoạt trong cấu hình messaging. `indexEvents-in-0` là tên **binding**; `orders.created` là tên **destination**. Một thay đổi tên topic không nhất thiết phải đổi tên bean hoặc đổi chỉ số của cổng.

Nếu không chỉ định `destination`, Spring Cloud Stream mặc định sử dụng **tên binding** làm destination. Cách mặc định này có thể khiến ứng dụng nối nhầm một topic có tên như `indexEvents-in-0`; vì vậy nên cấu hình rõ destination trong các ví dụ nghiệp vụ.

### Binding không phải một bản ghi hay một trường dữ liệu

Một binding có thể truyền **nhiều message** theo thời gian. Một message lại có thể mang payload là `List<T>` hoặc một object có nhiều thuộc tính. **Chỉ số binding** đếm số **cổng**, không đếm message, số trường trong payload hay partition của broker.

## 3. Quy tắc đặt tên binding mặc định

Spring Cloud Stream sử dụng quy tắc cho mô hình functional:

~~~text
<functionName>-in-<index>
<functionName>-out-<index>
~~~

Trong đó `index` là số nguyên bắt đầu từ **0**, đếm riêng cho chiều input và output. Với hàm tên `indexEvents`:

| Cổng logic | Binding mặc định | Chỉ số |
| --- | --- | ---: |
| Input thứ nhất | `indexEvents-in-0` | 0 |
| Input thứ hai | `indexEvents-in-1` | 1 |
| Output thứ nhất | `indexEvents-out-0` | 0 |
| Output thứ hai | `indexEvents-out-1` | 1 |

Chú ý hai điều:

- Hậu tố `-0` **không** có nghĩa cổng bị vô hiệu hay mang giá trị số 0. Nó chỉ là chỉ số **cổng đầu tiên**.
- Input và output có **hai dãy chỉ số riêng**. Có `-in-1` không đồng nghĩa phải có `-out-1`; số lượng cổng ở hai phía có thể khác nhau.

### Với Supplier, Function và Consumer thông thường

| Bean | Hợp đồng | Binding mặc định |
| --- | --- | --- |
| `Supplier<O> create()` | Không có input, có một output | `create-out-0` |
| `Function<I, O> convert()` | Một input, một output | `convert-in-0`, `convert-out-0` |
| `Consumer<I> record()` | Một input, không có output trả về | `record-in-0` |

Các ví dụ này giả định Spring Cloud Stream đang bind các bean tương ứng. Tần suất gọi `Supplier`, việc tạo output message từ `Consumer` và cách xử lý lỗi chịu quy tắc của adapter/binder; bản thân tên binding chỉ diễn tả **đường đi logic của dữ liệu**.

## 4. Từ vị trí Tuple của Reactor đến chỉ số binding

Với reactive function nhiều cổng, **Spring Cloud Function** dùng kiểu `TupleN` của **Project Reactor**, trong đó từng thành phần là một `Flux`. Chữ ký ví dụ:

~~~java
Function<
    Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
    Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>>
~~~

Ý nghĩa:

- `Tuple2` ở phía **input** chứa **hai luồng đầu vào**.
- `Tuple2` ở phía **output** chứa **hai luồng đầu ra**.
- Mỗi `Flux<T>` thể hiện kiểu payload của một cổng.

**Điểm dễ nhầm nhất** là Reactor đặt tên accessor theo `getT1()`, `getT2()` (đếm **từ 1**), còn binding dùng chỉ số từ **0**.

| Vị trí tuple | Accessor Reactor | Input binding | Output binding |
| --- | --- | --- | --- |
| Thành phần thứ nhất | `getT1()` | `indexEvents-in-0` | `indexEvents-out-0` |
| Thành phần thứ hai | `getT2()` | `indexEvents-in-1` | `indexEvents-out-1` |
| Thành phần thứ ba, nếu là `Tuple3` | `getT3()` | `other-in-2` | `other-out-2` |

**Quy tắc:** thành phần `getTn()` tương ứng chỉ số binding `n - 1`, với mỗi phía input/output được xét độc lập.

~~~java
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

Tuple2<Flux<String>, Flux<Long>> inputs = Tuples.of(
        Flux.just("ORDER-101"), // T1 -> in-0
        Flux.just(250_000L));   // T2 -> in-1

Flux<String> orders = inputs.getT1();
Flux<Long> payments = inputs.getT2();
~~~

Thứ tự `Tuples.of(...)` ở **đầu ra** cũng có ý nghĩa tương tự: thành phần đầu tiên được ánh xạ tới `-out-0`, thành phần thứ hai tới `-out-1`.

### Không đồng nhất thứ tự binding với quy tắc nghiệp vụ

Một hàm có thể gộp input 0 và input 1 thành **một** output 0. Một hàm khác có thể lấy **một** input 0 rồi phân loại thành output 0 và output 1. Thứ tự cổng **không** áp đặt quy tắc “input 0 phải tạo output 0”; đó chỉ là cách minh họa của một số bài toán.

## 5. Ví dụ Java hoàn chỉnh: hai input và hai output

Ví dụ dưới đây dùng **Java 17+** (`record`), Spring Cloud Function, Spring Cloud Stream và Reactor. Hai nguồn có kiểu payload khác nhau; hàm tạo hai luồng kết quả độc lập:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class EventIndexConfiguration {

    public record OrderCreated(String orderId, long totalVnd) {}

    public record PaymentConfirmed(String orderId, long paidVnd) {}

    public record OrderIndex(String orderId, long totalVnd) {}

    public record PaymentIndex(String orderId, boolean paid) {}

    @Bean
    public Function<
            Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
            Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>>
            indexEvents() {
        return inputs -> {
            // Input thứ nhất: indexEvents-in-0.
            Flux<OrderCreated> orders = inputs.getT1();

            // Input thứ hai: indexEvents-in-1.
            Flux<PaymentConfirmed> payments = inputs.getT2();

            Flux<OrderIndex> orderIndexes = orders.map(order ->
                    new OrderIndex(order.orderId(), order.totalVnd()));

            Flux<PaymentIndex> paymentIndexes = payments.map(payment ->
                    new PaymentIndex(
                            payment.orderId(), payment.paidVnd() > 0));

            // T1 -> indexEvents-out-0, T2 -> indexEvents-out-1.
            return Tuples.of(orderIndexes, paymentIndexes);
        };
    }
}
~~~

Đọc hợp đồng cụ thể:

| Vị trí | Tên binding | Kiểu payload |
| --- | --- | --- |
| `inputs.getT1()` | `indexEvents-in-0` | `OrderCreated` |
| `inputs.getT2()` | `indexEvents-in-1` | `PaymentConfirmed` |
| Thành phần đầu tiên của `Tuples.of(...)` | `indexEvents-out-0` | `OrderIndex` |
| Thành phần thứ hai của `Tuples.of(...)` | `indexEvents-out-1` | `PaymentIndex` |

Hàm này **không** ghép một đơn hàng với một thanh toán; từng luồng được biến đổi riêng. Nếu nghiệp vụ là đối soát hai nguồn theo `orderId`, phải viết thêm logic đồng bộ/tương quan phù hợp, ví dụ windowed join hoặc lưu trạng thái theo khóa. Việc có hai input không làm framework tự ghép hai message có cùng vị trí hay cùng mã.

## 6. Cấu hình từng cổng đến từng destination

Với bean `indexEvents` trên, có thể dùng cấu hình `application.yml` sau:

~~~yaml
spring:
  cloud:
    function:
      definition: indexEvents
    stream:
      bindings:
        indexEvents-in-0:
          destination: orders.created
          group: event-indexer
          content-type: application/json
        indexEvents-in-1:
          destination: payments.confirmed
          group: event-indexer
          content-type: application/json
        indexEvents-out-0:
          destination: orders.indexed
          content-type: application/json
        indexEvents-out-1:
          destination: payments.indexed
          content-type: application/json
~~~

Mỗi key dưới `spring.cloud.stream.bindings` là **tên binding**; thuộc tính `destination` phía dưới mới là **đích trên broker**. Thuộc tính `group` áp dụng cho **consumer/input binding**, không áp dụng cho output producer. Ở ví dụ này, cả hai cổng input dùng tên group `event-indexer` nhưng mỗi cổng kết nối tới **một destination riêng**; chúng không bị gộp thành một input.

Để chạy với Kafka hoặc RabbitMQ, dự án cần có Spring Cloud Stream và **binder** tương ứng, cấu hình kết nối đến broker và những dependency thích hợp. Cấu hình trên minh họa hợp đồng binding, không tự triển khai hay tạo broker vật lý.

### Tại sao cần khai báo content-type?

`OrderCreated` và `PaymentConfirmed` đều có thể được truyền dưới dạng `application/json` nhưng là **hai kiểu Java khác nhau**. Framework dùng thông tin generic của từng `Flux<T>` cùng metadata chuyển đổi thông điệp để xử lý payload thích hợp.

Ví dụ JSON trên `orders.created`:

~~~json
{"orderId":"O-101","totalVnd":500000}
~~~

JSON trên `payments.confirmed`:

~~~json
{"orderId":"O-101","paidVnd":500000}
~~~

Đổi nhầm hai `destination` khiến payload ở input 0 không tương thích `OrderCreated` hoặc gây dữ liệu thiếu/sai; cùng `content-type: application/json` **không** làm các kiểu Java hoán đổi được. Nếu gửi `Message<T>`, hãy cân nhắc cả header và payload, vì header không tạo thêm cổng mới.

## 7. Nhìn nhanh các mô hình nhiều đầu vào/ra

Số binding được suy từ **arity** của hàm, không suy từ số bản ghi đi qua một `Flux`:

| Chữ ký hàm reactive | Input bindings | Output bindings |
| --- | --- | --- |
| `Function<Flux<A>, Flux<B>>` | `f-in-0` | `f-out-0` |
| `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` | `f-in-0`, `f-in-1` | `f-out-0` |
| `Function<Flux<A>, Tuple2<Flux<B>, Flux<C>>>` | `f-in-0` | `f-out-0`, `f-out-1` |
| `Function<Tuple2<Flux<A>, Flux<B>>, Tuple2<Flux<C>, Flux<D>>>` | `f-in-0`, `f-in-1` | `f-out-0`, `f-out-1` |
| `Function<Tuple3<Flux<A>, Flux<B>, Flux<C>>, Flux<D>>` | `f-in-0`, `f-in-1`, `f-in-2` | `f-out-0` |

Ở bảng này, tên bean giả định là `f`. Việc `Flux<A>` phát 1 hay 100.000 phần tử **không** thay đổi số binding.

### Ví dụ 2 → 1: hợp nhất nhiều nguồn

~~~java
@Bean
public Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>
        mergeEvents() {
    return sources -> Flux.merge(
            sources.getT1().map(id -> "ORDER:" + id),
            sources.getT2().map(id -> "PAYMENT:" + id));
}
~~~

Cổng logic là `mergeEvents-in-0`, `mergeEvents-in-1` và `mergeEvents-out-0`. `Flux.merge` trộn các phần tử thành một luồng nhưng **không** tự ghép theo khóa nghiệp vụ.

### Ví dụ 1 → 2: phân nhánh theo quy tắc

~~~java
@Bean
public Function<Flux<String>, Tuple2<Flux<String>, Flux<String>>>
        splitEvents() {
    return input -> {
        Flux<String> shared = input.publish().autoConnect(2);
        Flux<String> orders = shared.filter(s -> s.startsWith("ORDER:"));
        Flux<String> other = shared.filter(s -> !s.startsWith("ORDER:"));
        return Tuples.of(orders, other);
    };
}
~~~

Cổng logic là `splitEvents-in-0`, `splitEvents-out-0` và `splitEvents-out-1`. Ví dụ này giả định **cả hai output đều có subscriber** để `autoConnect(2)` kết nối tới nguồn; khi một output không được subscribe, nguồn có thể chưa chạy. Cần đánh giá subscription/backpressure của các nhánh theo binder và ứng dụng.

Hai đoạn trên là **ví dụ hàm độc lập**: chỉ chọn `mergeEvents` hoặc `splitEvents` trong `spring.cloud.function.definition` khi triển khai. Nếu ứng dụng có nhiều bean có thể được bind, phải khai báo rõ hàm cần kích hoạt.

## 8. Đổi tên binding mà vẫn giữ đúng chỉ số

Spring Cloud Stream có thể **đổi tên binding** mặc định thành một tên dễ hiểu qua thuộc tính:

~~~properties
spring.cloud.stream.function.bindings.<implicit-binding-name>=<new-binding-name>
~~~

Ví dụ đổi hai trong số bốn binding của `indexEvents`:

~~~yaml
spring:
  cloud:
    function:
      definition: indexEvents
    stream:
      function:
        bindings:
          indexEvents-in-0: incomingOrders
          indexEvents-out-1: outgoingPayments
      bindings:
        incomingOrders:
          destination: orders.created
        indexEvents-in-1:
          destination: payments.confirmed
        indexEvents-out-0:
          destination: orders.indexed
        outgoingPayments:
          destination: payments.indexed
~~~

**Cách diễn giải:**

- `indexEvents-in-0` vẫn là cổng input index 0, nhưng tên binding dùng để cấu hình là `incomingOrders`.
- `indexEvents-out-1` vẫn là cổng output index 1, nhưng tên binding dùng để cấu hình là `outgoingPayments`.
- Hai binding chưa đổi tên vẫn dùng `indexEvents-in-1` và `indexEvents-out-0`.
- `getT1()`, `getT2()` trong Java **không đổi vị trí** vì đổi tên binding chỉ là ánh xạ tên.

Khi đã đổi tên, mọi thuộc tính trong `spring.cloud.stream.bindings` (như `destination`, `group`, `content-type`) của cổng đó cần dùng **tên mới**. Nếu tiếp tục cấu hình `indexEvents-in-0.destination` sau khi đổi thành `incomingOrders`, thuộc tính đó không còn được áp dụng cho binding mong muốn.

Tài liệu Spring Cloud Stream khuyến nghị cân nhắc sự cần thiết của việc đổi tên: nó giúp tên có ý nghĩa nghiệp vụ nhưng bổ sung thêm một bước ánh xạ. Với các ứng dụng không cần tương thích tên cũ, **giữ tên mặc định** thường dễ lần theo cấu hình hơn.

### Binding name khác destination name

Giả sử hai môi trường dùng cùng bean và binding `indexEvents-in-0` nhưng topic khác nhau:

~~~yaml
# Môi trường phát triển
spring:
  cloud:
    stream:
      bindings:
        indexEvents-in-0:
          destination: dev.orders.created
~~~

~~~yaml
# Môi trường production: cấu hình riêng thay thế
spring:
  cloud:
    stream:
      bindings:
        indexEvents-in-0:
          destination: prod.orders.created
~~~

Binding index vẫn là **0** và Java vẫn dùng `getT1()`. Chỉ có đích cụ thể do binder kết nối thay đổi. Hai khối YAML này là **hai lựa chọn cấu hình ở hai môi trường**, không phải hai đoạn cần nối liên tiếp vào cùng một tệp.

## 9. Các trường hợp đặc biệt về tên binding

### 9.1. Định nghĩa nhiều hàm hoặc composition

`spring.cloud.function.definition` có thể chọn hàm cần bind. Với nhiều bean, việc khai báo rõ tên giúp tránh chọn nhầm. Khi dùng composition, chẳng hạn:

~~~properties
spring.cloud.function.definition=normalizeOrder|enrichOrder
~~~

hãy dựa vào **tên binding của hàm đã composition mà Spring Cloud Stream thực tế tạo ra**. Đừng mặc nhiên kết luận các binding thuộc về từng bean riêng lẻ vẫn tồn tại như khi từng hàm được bind độc lập. Composition là **ghép tuần tự kết quả** và có thể thay đổi hợp đồng I/O nhìn từ bên ngoài.

### 9.2. Explicit binding được khai báo mà không gắn trực tiếp với hàm

Spring Cloud Stream cũng có cơ chế tạo **binding tường minh** hoặc gửi dữ liệu bằng `StreamBridge`. Các binding đó có thể có tên không theo khuôn `functionName-in-0`/`functionName-out-0`, vì chúng không phải các binding suy ra trực tiếp từ chữ ký của một functional bean.

Do vậy, quy tắc đánh chỉ số trong bài này áp dụng cho **functional bindings do framework tạo từ một hàm**. Khi gặp một tên như `auditEvents` trong cấu hình `spring.cloud.stream.output-bindings` hay `StreamBridge.send("auditEvents", ...)`, hãy xem nó là một cơ chế binding khác và đối chiếu cấu hình tương ứng.

### 9.3. Không nhầm với Kafka Streams Binder

Kafka Streams Binder có thêm các kiểu `KStream`, `KTable` và những cách khai báo hàm khác. Dù có các quy tắc đặt tên binding tương tự, ví dụ trong bài này được viết cho **Spring Cloud Function reactive `Flux` cùng Spring Cloud Stream messaging binder**. Khi chuyển sang Kafka Streams API, cần kiểm tra chữ ký và quy ước riêng của binder đó.

## 10. Kiểm thử thứ tự cổng và cấu hình

Một unit test có thể xác nhận rằng tuple đầu vào được đọc theo đúng thứ tự và tuple đầu ra cũng giữ đúng thứ tự. Ví dụ dùng **JUnit 5** và `reactor-test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuples;

class EventIndexConfigurationTest {

    @Test
    void keepsTheTwoInputAndOutputPositions() {
        var function = new EventIndexConfiguration().indexEvents();

        var outputs = function.apply(Tuples.of(
                Flux.just(new EventIndexConfiguration.OrderCreated(
                        "O-101", 500_000L)),
                Flux.just(new EventIndexConfiguration.PaymentConfirmed(
                        "O-101", 500_000L))));

        StepVerifier.create(Mono.zip(
                        outputs.getT1().collectList(),
                        outputs.getT2().collectList()))
                .assertNext(both -> {
                    assertEquals(
                            List.of(new EventIndexConfiguration.OrderIndex(
                                    "O-101", 500_000L)),
                            both.getT1());
                    assertEquals(
                            List.of(new EventIndexConfiguration.PaymentIndex(
                                    "O-101", true)),
                            both.getT2());
                })
                .verifyComplete();
    }
}
~~~

Test này chỉ xác nhận **logic Java và thứ tự tuple**. Muốn khẳng định topic/queue được nối đúng, cần kiểm thử tích hợp với **Spring Cloud Stream Test Binder** hoặc binder messaging đã cấu hình. Khi đó:

1. Gửi thông điệp `OrderCreated` vào binding tương ứng `indexEvents-in-0` và `PaymentConfirmed` vào `indexEvents-in-1`.
2. Nhận kết quả từ `indexEvents-out-0` và `indexEvents-out-1`.
3. Kiểm tra nội dung, kiểu payload và việc mỗi kết quả đi đúng destination.
4. Lặp lại khi có cấu hình đổi tên binding để chắc chắn các thuộc tính đang dùng tên mới.

Chỉ dùng `collectList()` cho dữ liệu thử nghiệm **hữu hạn** như `Flux.just(...)`. Với topic chạy liên tục, một luồng `Flux` không nhất thiết hoàn thành và `collectList()` có thể giữ dữ liệu trong bộ nhớ vô thời hạn.

### Quan sát binding đang chạy

Nếu dự án bật Actuator và endpoint `bindings` của Spring Cloud Stream theo cấu hình phù hợp, có thể kiểm tra các binding đang được quản lý. Việc endpoint có sẵn, được expose và những thao tác được hỗ trợ phụ thuộc phiên bản và cấu hình bảo mật; không được suy rằng nó luôn bật.

Khi chẩn đoán tại runtime, ưu tiên đối chiếu **đúng bốn thông tin**: tên bean được chọn, tên binding, destination thực tế và kiểu payload. Chỉ xem tên topic mà bỏ qua mapping sẽ dễ che giấu lỗi chỉ số.

## 11. Các lỗi cấu hình phổ biến

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Message thanh toán bị đưa vào nhánh đơn hàng | Đảo `destination` của `-in-0` và `-in-1` | Đối chiếu kiểu `getT1()`/`getT2()` với binding |
| Payload của output 0 xuất hiện trên topic của output 1 | Đảo thứ tự trong `Tuples.of(...)` hoặc cấu hình output | Kiểm tra output `getT1()` ↔ `-out-0` |
| Không nhận message nhưng ứng dụng vẫn khởi động | `definition` sai, destination sai hoặc binder không kết nối | Kiểm tra bean được chọn, binding name, broker và logs |
| Đổi tên binding nhưng thay đổi destination không có hiệu lực | Tiếp tục cấu hình thuộc tính dưới tên binding cũ | Sau `function.bindings`, dùng tên binding mới dưới `bindings` |
| Có `-in-1` nhưng không có `-out-1` | Hàm có hai đầu vào, một đầu ra | Đây có thể là hợp đồng đúng của hàm 2 → 1 |
| `Flux<List<T>>` phát nhiều phần tử, tưởng có nhiều output | Nhầm số phần tử với số cổng | Số cổng dựa trên arity, không trên số phần tử |
| Thêm `Tuple3` rồi thấy hai nguồn cũ bị đổi chỗ | Chèn phần tử tuple vào giữa và quên cập nhật binding | Xem lại thứ tự `getT1()`, `getT2()`, `getT3()` |
| Hai input cùng `application/json` nhưng deserialization sai | Kiểu Java ở cổng không tương thích payload | Kiểm tra generic `Flux<T>` của chính input đó |

## 12. Bài tập tự kiểm tra

**Câu 1.** Bean tên `combine` có chữ ký:

~~~java
Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>
~~~

Có bao nhiêu binding, tên mặc định là gì?

**Đáp án:** Ba binding: `combine-in-0`, `combine-in-1` và `combine-out-0`. Input 0 có payload `String`; input 1 có payload `Long`. Chỉ có một output.

**Câu 2.** Hàm `route` trả `Tuple3<Flux<A>, Flux<B>, Flux<C>>`. Thành phần `getT3()` tương ứng output nào?

**Đáp án:** `route-out-2`, vì binding index bắt đầu từ 0, còn `getTn()` bắt đầu từ 1.

**Câu 3.** Sau khi cấu hình:

~~~properties
spring.cloud.stream.function.bindings.route-out-1=failedOrders
spring.cloud.stream.bindings.failedOrders.destination=orders.failed
~~~

Output index 1 của hàm `route` sẽ có tên binding nào và đi đến destination nào?

**Đáp án:** Tên binding đang dùng để cấu hình là `failedOrders`; destination là `orders.failed`. Index vẫn là 1, tương ứng thành phần `getT2()` trong tuple đầu ra.

**Câu 4.** Nếu không cấu hình `destination` cho `route-in-0`, Spring Cloud Stream mặc định dùng tên destination nào?

**Đáp án:** Tên binding `route-in-0`. Đây là lý do nên cấu hình rõ destination trong ứng dụng có quy ước tên topic riêng.

**Câu 5.** Một `Function<Flux<Order>, Tuple2<Flux<Accepted>, Flux<Rejected>>>` phát 10.000 `Accepted` và 50 `Rejected`. Có bao nhiêu output binding?

**Đáp án:** **Hai**: `-out-0` và `-out-1`. Số message mỗi nhánh không làm thay đổi số binding.

## Tài liệu tham khảo

- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding and binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-names.html)
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Producing and consuming messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming model và Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Project Reactor — Tuple2 API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuple2.html)
