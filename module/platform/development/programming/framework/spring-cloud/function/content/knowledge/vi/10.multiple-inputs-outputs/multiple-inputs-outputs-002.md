# Biểu diễn nhiều luồng bằng Tuple của Reactor

## 1. Bài toán: một hàm làm việc với nhiều luồng dữ liệu

Trong **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), chúng ta xây dựng logic nghiệp vụ thành các bean `Supplier`, `Function` hoặc `Consumer` để có thể tái sử dụng độc lập với giao thức gọi. `FunctionCatalog` quản lý việc tra cứu hàm, hỗ trợ composition và chuyển đổi thông điệp; các adapter có thể đưa cùng logic đến HTTP, message broker hoặc môi trường serverless.

Với một hàm `Function<String, String>` thông thường, việc xác định đầu vào và đầu ra khá đơn giản. Nhưng hệ thống xử lý sự kiện thường có những yêu cầu phức tạp hơn:

- **Gộp luồng:** nhận sự kiện đơn hàng từ một topic và hóa đơn từ một topic khác, rồi phát chung một luồng để thống kê.
- **Tách luồng:** nhận một luồng sự kiện lẫn lộn, rồi phát sự kiện đơn hàng sang một đích và các sự kiện khác sang đích còn lại.
- **Xử lý nhiều nguồn, nhiều đích:** nhận đồng thời các luồng khác kiểu và trả kết quả qua nhiều luồng độc lập.

Các bài toán này cần mô tả cả **số lượng cổng dữ liệu** lẫn **kiểu dữ liệu ở mỗi cổng**. Spring Cloud Function sử dụng các kiểu `Tuple` của **Project Reactor** để biểu diễn điều đó cho *reactive functions*.

Mục tiêu của bài: hiểu `Tuple2`/`Tuple3`, đọc đúng chữ ký `TupleN<Flux<...>>`, xây dựng hàm gộp hoặc phân nhánh luồng, và biết các cổng này được Spring Cloud Stream ánh xạ thành binding như thế nào.

## 2. Tuple trong Project Reactor là gì?

**Tuple** là cấu trúc giữ một số phần tử **cố định**, mỗi phần tử có kiểu dữ liệu riêng. Project Reactor cung cấp các lớp trong package `reactor.util.function`:

| Kiểu | Số thành phần | Truy cập |
| --- | ---: | --- |
| `Tuple2<A, B>` | 2 | `getT1()`, `getT2()` |
| `Tuple3<A, B, C>` | 3 | `getT1()`, `getT2()`, `getT3()` |
| `Tuple4<A, B, C, D>` | 4 | `getT1()` đến `getT4()` |
| `Tuple5` đến `Tuple8` | 5 đến 8 | `getT1()` đến vị trí tương ứng |

Dùng `Tuples.of(...)` để tạo tuple:

~~~java
import reactor.util.function.Tuple2;
import reactor.util.function.Tuple3;
import reactor.util.function.Tuples;

Tuple2<String, Integer> pair = Tuples.of("ORDER-42", 3);

String orderId = pair.getT1();  // "ORDER-42"
Integer itemCount = pair.getT2(); // 3

Tuple3<String, Integer, Boolean> triple =
        Tuples.of("ORDER-42", 3, true);

Boolean paid = triple.getT3();  // true
~~~

Trong ví dụ, `Tuple2<String, Integer>` có **hai giá trị**. Kiểu trả về của `getT1()` được biết là `String` và `getT2()` là `Integer` nên chương trình không cần ép kiểu thủ công. Những tuple này không cho phép thành phần `null` và không có phương thức thay đổi trực tiếp từng vị trí sau khi tạo.

Tuple không tự động là luồng reactive: `Tuple2<String, Integer>` chỉ giữ hai giá trị bình thường. Khi từng thành phần là `Flux<T>`, tuple giữ **tham chiếu đến nhiều publisher/luồng**:

~~~java
import reactor.core.publisher.Flux;

Flux<String> orders = Flux.just("O-1", "O-2");
Flux<Long> invoices = Flux.just(101L, 102L);

Tuple2<Flux<String>, Flux<Long>> sources =
        Tuples.of(orders, invoices);

Flux<String> firstStream = sources.getT1();
Flux<Long> secondStream = sources.getT2();
~~~

Điểm mấu chốt: `sources` là **một đối tượng Java** gồm **hai luồng**; nó không chứa ngay các bản ghi đã được tiêu thụ. Các phần tử bên trong mỗi `Flux` được phát ra khi có subscription, tuân theo vòng đời reactive của publisher.

## 3. Phân biệt ba hình dạng dễ nhầm

Ba kiểu sau trông giống nhau nhưng thể hiện các hợp đồng hoàn toàn khác:

| Kiểu | Ý nghĩa |
| --- | --- |
| `Tuple2<Order, Invoice>` | Một tuple gồm **hai đối tượng** dữ liệu |
| `Flux<Tuple2<Order, Invoice>>` | **Một luồng** mà mỗi phần tử là **một cặp** đơn hàng/hóa đơn |
| `Tuple2<Flux<Order>, Flux<Invoice>>` | **Hai luồng độc lập**, luồng thứ nhất chứa đơn hàng và luồng thứ hai chứa hóa đơn |

Hãy quan sát vị trí của `Flux`:

~~~text
Flux<Tuple2<Order, Invoice>>
  └─ một luồng
       ├─ (Order #1, Invoice #1)
       ├─ (Order #2, Invoice #2)
       └─ ...

Tuple2<Flux<Order>, Flux<Invoice>>
  ├─ luồng thứ nhất: Order #1, Order #2, ...
  └─ luồng thứ hai: Invoice #A, Invoice #B, ...
~~~

Đặc biệt, `Flux.zip(orderFlux, invoiceFlux)` tạo một **`Flux<Tuple2<Order, Invoice>>`**, tức từng cặp phần tử được ghép lại trong **một luồng**. Ngược lại, `Tuples.of(orderFlux, invoiceFlux)` tạo **`Tuple2<Flux<Order>, Flux<Invoice>>`** để giữ hai luồng tách biệt. `zip` ghép theo thứ tự phát phần tử, **không** tự đối chiếu theo mã đơn hàng; nếu các luồng không cân bằng, có thể còn phần tử không được ghép khi một bên kết thúc.

Một `List<Flux<?>>` có thể mang nhiều publisher nhưng không cho framework biết trước chính xác số lượng và kiểu cụ thể của từng vị trí qua kiểu generic. `TupleN` thể hiện số lượng (*arity*) và kiểu của các thành phần ngay trên chữ ký, qua đó giúp Spring Cloud Function / Spring Cloud Stream suy ra các cổng cùng thông tin chuyển đổi dữ liệu.

## 4. Cách đọc `TupleN<Flux<...>>` trong chữ ký hàm

Spring Cloud Function nhận diện các dạng *function arity* cho hàm reactive, trong đó mỗi `Flux<?>` nằm trong tuple tương ứng với một cổng logic:

| Chữ ký hàm | Cổng vào | Cổng ra | Cách hiểu |
| --- | ---: | ---: | --- |
| `Function<Flux<A>, Flux<B>>` | 1 | 1 | Biến đổi một luồng |
| `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` | 2 | 1 | Gộp hai nguồn vào một luồng |
| `Function<Flux<A>, Tuple2<Flux<B>, Flux<C>>>` | 1 | 2 | Chia một nguồn thành hai luồng |
| `Function<Tuple2<Flux<A>, Flux<B>>, Tuple2<Flux<C>, Flux<D>>>` | 2 | 2 | Hai nguồn vào, hai luồng ra |
| `Function<Tuple3<Flux<A>, Flux<B>, Flux<C>>, Flux<D>>` | 3 | 1 | Ba nguồn vào, một luồng ra |

Ví dụ: `Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>` chỉ có **một tham số Java** ở phương thức `apply`, nhưng tham số là một tuple gồm hai `Flux`. Vì thế, ở tầng tích hợp Spring Cloud Stream, hàm được diễn giải là **hai input binding và một output binding**.

Lưu ý giới hạn: cơ chế nhiều cổng `TupleN` được thiết kế cho **reactive functions** mà các nhánh mang `Flux`. Viết `Function<A, Tuple2<B, C>>` thông thường **không mặc nhiên** tạo hai output binding, và viết hai phần tử trong một `List` cũng không tạo hai cổng. Adapter HTTP hoặc serverless không nhất thiết ánh xạ nhiều cổng như Spring Cloud Stream.

## 5. Ví dụ 2 đầu vào, 1 đầu ra: gộp sự kiện

Một dịch vụ nhận sự kiện đơn hàng dạng `String` và mã hóa đơn dạng `Long`. Ta muốn đưa chúng về cùng một luồng chuỗi, nhưng vẫn phân biệt nguồn:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;

@Configuration
public class GatherConfiguration {

    @Bean
    public Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>
            gatherEvents() {
        return sources -> {
            Flux<String> orders = sources.getT1()
                    .map(id -> "ORDER:" + id);

            Flux<String> invoices = sources.getT2()
                    .map(id -> "INVOICE:" + id);

            return Flux.merge(orders, invoices);
        };
    }
}
~~~

Giải thích theo từng bước:

1. `sources.getT1()` là **luồng thứ nhất**, mang payload `String`.
2. `sources.getT2()` là **luồng thứ hai**, mang payload `Long`.
3. Mỗi nhánh chuyển bản ghi thành chuỗi có nhãn để biết xuất xứ.
4. `Flux.merge(orders, invoices)` phát dữ liệu của cả hai nguồn lên **một luồng đầu ra**.

~~~text
orders-topic   ──> [ gatherEvents-in-0 ] ──┐
                                          ├── gatherEvents ──> [ gatherEvents-out-0 ] ──> events-topic
invoices-topic ──> [ gatherEvents-in-1 ] ──┘
~~~

Khi triển khai bằng **Spring Cloud Stream** với binder phù hợp, cấu hình `application.yml` có thể là:

~~~yaml
spring:
  cloud:
    function:
      definition: gatherEvents
    stream:
      bindings:
        gatherEvents-in-0:
          destination: orders-topic
        gatherEvents-in-1:
          destination: invoices-topic
        gatherEvents-out-0:
          destination: events-topic
~~~

Hậu tố `-in-0` ứng với `getT1()`, `-in-1` ứng với `getT2()`. Hậu tố `-out-0` là một luồng đầu ra duy nhất. `Flux.merge` **không bảo đảm thứ tự tổng thể giữa hai nguồn** và **không ghép đơn hàng với hóa đơn cùng khóa**. Bài toán đối soát theo mã cần thêm logic tương quan, thường phải tính đến thứ tự, độ trễ, bộ nhớ và thời hạn chờ sự kiện.

## 6. Ví dụ 1 đầu vào, 2 đầu ra: phân luồng sự kiện

Một luồng chứa nhiều loại bản ghi như `ORDER:101`, `AUDIT:login`, `ORDER:102`. Ta muốn tách riêng sự kiện đơn hàng và các sự kiện còn lại:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class RouteConfiguration {

    @Bean
    public Function<Flux<String>, Tuple2<Flux<String>, Flux<String>>>
            routeEvents() {
        return source -> {
            // Chờ đủ 2 subscriber rồi chia sẻ cùng một nguồn.
            Flux<String> shared = source.publish().autoConnect(2);

            Flux<String> orderEvents = shared
                    .filter(event -> event.startsWith("ORDER:"));

            Flux<String> otherEvents = shared
                    .filter(event -> !event.startsWith("ORDER:"));

            return Tuples.of(orderEvents, otherEvents);
        };
    }
}
~~~

`Tuples.of(orderEvents, otherEvents)` tạo một **tuple có hai thành phần `Flux<String>`**, từ đó khai báo hai đầu ra độc lập. Thứ tự trong tuple rất quan trọng:

- `getT1()`, tức `orderEvents`, tương ứng `routeEvents-out-0`.
- `getT2()`, tức `otherEvents`, tương ứng `routeEvents-out-1`.

~~~text
events-topic ──> [ routeEvents-in-0 ] ──> routeEvents
                                           ├── [ routeEvents-out-0 ] ──> orders-topic
                                           └── [ routeEvents-out-1 ] ──> others-topic
~~~

Cấu hình Spring Cloud Stream tương ứng (ví dụ **riêng**, độc lập với `gatherEvents`):

~~~yaml
spring:
  cloud:
    function:
      definition: routeEvents
    stream:
      bindings:
        routeEvents-in-0:
          destination: events-topic
        routeEvents-out-0:
          destination: orders-topic
        routeEvents-out-1:
          destination: others-topic
~~~

Với đầu vào `ORDER:101`, `AUDIT:login`, `ORDER:102`, nhánh `out-0` phát hai sự kiện `ORDER`; nhánh `out-1` phát sự kiện `AUDIT`. **Tạo hai output binding không đồng nghĩa gửi mọi bản ghi ra cả hai output**: dữ liệu thực sự được phát trên mỗi nhánh do logic reactive quyết định.

### Tại sao dùng `publish().autoConnect(2)`?

Thông thường `Flux` là *cold publisher*: mỗi lần subscribe có thể kích hoạt lại nguồn. Nếu tạo hai nhánh bằng `source.filter(...)` riêng biệt và cả hai nhánh được subscribe, nguồn có thể bị subscribe **hai lần**; khi nguồn chứa thao tác tốn tài nguyên hoặc tác dụng phụ, đây là vấn đề.

`publish()` chuyển nguồn thành một luồng được chia sẻ; `autoConnect(2)` chỉ kết nối với nguồn khi **cả hai nhánh** đã có subscriber. Do đó các nhánh cùng quan sát nguồn đã được kết nối. Đổi lại, nếu chỉ một nhánh được subscribe, không đủ ngưỡng 2 thì nguồn **chưa phát**. Đây là điều kiện cần nhớ khi kiểm thử hoặc thay đổi cấu hình các output binding.

Trong ví dụ này, cả hai output cần được sử dụng. Với hệ thống thực tế, phải kiểm tra cả cách xử lý lỗi, tốc độ tiêu thụ từng nhánh và cơ chế backpressure; tùy binder, không phải mọi khả năng reactive đều được hỗ trợ xuyên suốt đến broker.

## 7. Kiểm tra phân luồng khi chưa có message broker

Vì `routeEvents` chỉ phụ thuộc `Flux` và `Tuple2`, ta có thể kiểm thử logic trực tiếp mà không cần Kafka hoặc RabbitMQ. Ví dụ dùng JUnit 5 và `reactor-test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;

class RouteConfigurationTest {

    @Test
    void separatesOrdersFromOtherEvents() {
        var function = new RouteConfiguration().routeEvents();

        Tuple2<Flux<String>, Flux<String>> outputs =
                function.apply(Flux.just(
                        "ORDER:101", "AUDIT:login", "ORDER:102"));

        // Mono.zip subscribe cả hai nhánh; autoConnect(2) mới kết nối.
        StepVerifier.create(Mono.zip(
                        outputs.getT1().collectList(),
                        outputs.getT2().collectList()))
                .assertNext(actual -> {
                    assertEquals(
                            List.of("ORDER:101", "ORDER:102"),
                            actual.getT1());
                    assertEquals(
                            List.of("AUDIT:login"),
                            actual.getT2());
                })
                .verifyComplete();
    }
}
~~~

Điểm đáng chú ý là `Mono.zip(...)` **subscribe đồng thời vào hai nhánh** (mỗi nhánh gom phần tử bằng `collectList()`). Nếu viết kiểm thử theo kiểu gọi `outputs.getT1().collectList().block()` trước, nhánh thứ hai chưa được subscribe nên ví dụ sử dụng `autoConnect(2)` có thể bị treo. `collectList()` chỉ thích hợp ở đây vì nguồn kiểm thử hữu hạn; không nên dùng nó để gom một luồng production không kết thúc.

## 8. Mở rộng sang Tuple3 và nhiều cổng hơn

`Tuple3` hoạt động tương tự `Tuple2`. Ví dụ, hàm trộn ba luồng cùng kiểu:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple3;

@Bean
public Function<Tuple3<Flux<String>, Flux<String>, Flux<String>>,
        Flux<String>> mergeThreeSources() {
    return sources -> Flux.merge(
            sources.getT1().map(value -> "A:" + value),
            sources.getT2().map(value -> "B:" + value),
            sources.getT3().map(value -> "C:" + value));
}
~~~

Hàm này có ba input binding: `mergeThreeSources-in-0`, `mergeThreeSources-in-1`, `mergeThreeSources-in-2`; và một output binding: `mergeThreeSources-out-0`.

Nếu cần **2 → 2**, chữ ký có thể là:

~~~java
Function<
    Tuple2<Flux<OrderEvent>, Flux<InvoiceEvent>>,
    Tuple2<Flux<AcceptedEvent>, Flux<RejectedEvent>>
>
~~~

Chữ ký chỉ mô tả cấu trúc của các cổng; để hàm hoạt động, phần thân vẫn phải định nghĩa cách nhận sự kiện từ hai đầu vào và cách phát `AcceptedEvent` / `RejectedEvent` ra hai đầu ra. Không có quy tắc tự động ghép input thứ nhất với output thứ nhất.

## 9. Tuple và các khái niệm liên quan: tránh nhầm lẫn

| Thành phần | Vai trò | Điều không nên suy diễn |
| --- | --- | --- |
| `Tuple2<Flux<A>, Flux<B>>` | Giữ hai luồng có kiểu rõ ràng | Không đồng nghĩa ghép từng `A` với từng `B` |
| `Flux<Tuple2<A, B>>` | Một luồng phát các cặp dữ liệu | Không tạo hai output binding |
| `Tuples.of(a, b)` | Tạo tuple cố định gồm `a` và `b` | Không tự subscribe hoặc thực thi publisher |
| `Flux.merge(a, b)` | Hợp nhất dữ liệu hai publisher thành một publisher | Không join theo khóa, không bảo đảm xen kẽ theo thứ tự cố định |
| `Flux.zip(a, b)` | Ghép các phần tử theo vị trí thành từng tuple | Không đối soát theo mã nghiệp vụ |
| `publish().autoConnect(2)` | Chia sẻ nguồn sau khi đủ hai subscriber | Không hoạt động nếu chỉ một subscriber xuất hiện |
| `FunctionCatalog` | Tra cứu, chuẩn hóa functional beans, composition, chuyển đổi | Không tự sinh topic/queue vật lý |
| Spring Cloud Stream binder | Ánh xạ binding đến destination messaging | Không phải tính năng có sẵn trong mọi adapter HTTP/serverless |

### Lỗi phổ biến và cách xử lý

1. **Đảo vị trí tuple:** `getT1()` là chỉ số binding **0**, không phải 1. Cấu hình sai thứ tự có thể làm đầu vào bị chuyển đổi sai kiểu hoặc gửi dữ liệu nhầm đích.
2. **Dùng tuple chứa bản ghi thay vì tuple chứa `Flux`:** `Tuple2<Order, Invoice>` không thể được coi như hai luồng có binding độc lập trong cơ chế arity này.
3. **Dùng `zip` trong bài toán chỉ muốn gộp sự kiện:** `zip` cần phần tử của các nguồn để tạo cặp, còn `merge` thích hợp để hợp nhất sự kiện mà không cần ghép cặp.
4. **Tạo hai nhánh reactive nhưng bỏ qua subscription:** Mỗi output có subscriber riêng; cách chia sẻ nguồn quyết định hai nhánh có nhận đúng dữ liệu hay không.
5. **Dùng xử lý lỗi theo tư duy hàm imperative:** Với reactive function, adapter thường gọi hàm để thiết lập pipeline rồi các phần tử chạy trong `Flux`. Cần xử lý lỗi trong chuỗi reactive (ví dụ `onErrorResume`, retry phù hợp), không mặc định kỳ vọng cơ chế retry trên từng lần gọi hàm imperative áp dụng y hệt.
6. **Nhầm nhiều cổng với nhiều phần tử:** `Flux<String>` có thể phát rất nhiều chuỗi trên **một** cổng, còn `Tuple2<Flux<String>, Flux<String>>` là **hai** cổng.

## 10. Gắn kết với kiến trúc Spring Cloud Function

Khi định nghĩa functional bean, **chữ ký Java** là hợp đồng nghiệp vụ. `FunctionCatalog` cho phép tìm hàm theo tên và cung cấp khả năng composition/chuyển đổi thông điệp; cách gọi hàm được quyết định bởi **adapter**.

- Với **Spring Cloud Stream**, tuple của các `Flux` giúp hệ thống xác định số input/output binding. Thứ tự các thành phần tuple ánh xạ thành `-in-0`, `-in-1`, `-out-0`, `-out-1`...
- Với **HTTP**, adapter web thường xử lý một request và một response theo cơ chế riêng. Không nên xem tuple hai luồng là hai HTTP endpoint chỉ vì chữ ký có `Tuple2`.
- Với **serverless**, cơ chế ánh xạ sự kiện và kết quả do adapter của nền tảng quyết định; cần kiểm tra chữ ký được hỗ trợ.

Spring Cloud Stream cần có binder thích hợp để kết nối thực tế với topic/queue. Việc khai báo `TupleN` hoặc bean `Function` đơn thuần không tạo ra broker hay tự cấu hình các destination. Khi message chứa header và content type, kiểu của mỗi thành phần `Flux<T>` còn giúp framework biết kiểu payload mong đợi để thực hiện chuyển đổi phù hợp; dữ liệu không đúng kiểu hoặc schema vẫn cần được xử lý.

**Tự kiểm tra:** Giả sử một hàm có chữ ký:

~~~java
Function<
    Tuple2<Flux<String>, Flux<Long>>,
    Tuple3<Flux<String>, Flux<Integer>, Flux<Boolean>>
>
~~~

Hãy tự trả lời trước khi xem gợi ý: có bao nhiêu cổng vào và ra? Các tên binding mặc định nếu bean tên `dispatch` là gì? `getT2()` của tuple đầu ra có kiểu nào?

**Đáp án:** Có **2 cổng vào, 3 cổng ra**. Input binding là `dispatch-in-0`, `dispatch-in-1`; output binding là `dispatch-out-0`, `dispatch-out-1`, `dispatch-out-2`. Thành phần `getT2()` của tuple đầu ra có kiểu `Flux<Integer>`. Số lượng phần tử phát trên mỗi luồng tùy logic triển khai, không bị cố định bởi số thành phần tuple.

### Tài liệu tham khảo

- [Spring Cloud Function — Programming model, Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Functions with multiple input and output arguments](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Project Reactor — API của `Tuples`](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuples.html)
- [Project Reactor — API của `Tuple2`](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuple2.html)
