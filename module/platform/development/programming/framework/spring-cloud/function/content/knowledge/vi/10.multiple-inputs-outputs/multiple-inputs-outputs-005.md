# Phân biệt nhiều đầu ra với một đầu ra chứa Collection

## 1. Vì sao dễ nhầm “nhiều kết quả” với “nhiều đầu ra”?

Trong **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được viết thành các bean `Supplier`, `Function` và `Consumer` để có thể tái sử dụng qua nhiều môi trường. `FunctionCatalog` giúp đăng ký, tìm kiếm, chuẩn hóa, composition và chuyển đổi thông điệp; HTTP, Spring Cloud Stream hoặc adapter serverless quyết định cách đưa dữ liệu đến hàm và xử lý kết quả.

Ở chương **Nhiều đầu vào/ra**, một câu hỏi cần trả lời trước khi thiết kế hàm là: **hàm cần tạo nhiều dữ liệu, hay cần tạo nhiều cổng đầu ra độc lập?**

Ví dụ, sau khi nhận một đơn hàng, hệ thống có thể:

- Tạo **ba dòng hóa đơn** và trả chúng dưới dạng `List<InvoiceLine>`.
- Phát **ba thông điệp sự kiện** lên cùng một topic.
- Gửi đơn hàng hợp lệ đến topic `orders.accepted`, đơn hàng bị từ chối đến topic `orders.rejected`.

Ba yêu cầu này không có cùng hợp đồng đầu ra. Hai yêu cầu đầu có thể được thực hiện với **một output binding**; yêu cầu cuối thường cần **hai output binding**. Nếu nhầm lẫn, ứng dụng có thể gửi đúng số bản ghi nhưng sai đích, hoặc tưởng một HTTP response chứa mảng là hai luồng sự kiện riêng biệt.

## 2. Ba đại lượng phải tách bạch

Đừng đếm số phần tử trong kiểu trả về rồi kết luận có từng ấy output binding. Hãy xét **ba tầng**:

| Đại lượng | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Số cổng đầu ra** (*output arity*) | Có bao nhiêu luồng/đích logic độc lập? | `routeOrders-out-0` và `routeOrders-out-1` = **2 cổng** |
| **Số thông điệp phát ra** (*message count*) | Có bao nhiêu bản tin được phát trên mỗi cổng? | Một cổng `audit-out-0` phát 3 message |
| **Số phần tử trong payload** (*collection size*) | Một thông điệp/giá trị trả về chứa bao nhiêu phần tử? | JSON array `["A", "B", "C"]` chứa 3 phần tử |

Để thấy rõ khác biệt:

~~~text
A. Một output chứa Collection

request ──> Function<Order, List<Line>>
                           |
                           └── out-0 ──> [Line-1, Line-2, Line-3]
                                         1 kết quả chứa 3 phần tử

B. Một output phát nhiều thông điệp

request ──> Function<String, List<Message<String>>>
                           |
                           └── out-0 ──> message A
                                      ├─> message B
                                      └─> message C
                                         3 thông điệp cùng một đích

C. Nhiều output độc lập

Flux<Order> ──> Function<Flux<Order>, Tuple2<Flux<Order>, Flux<Order>>>
                           |
                           ├── out-0 ──> orders.accepted
                           └── out-1 ──> orders.rejected
                                         2 đích/binding riêng
~~~

Số phần tử, số thông điệp và số cổng **có thể khác nhau**. Một cổng có thể phát hàng triệu message; một message có thể chứa hàng nghìn phần tử; một hàm có thể có nhiều cổng, mỗi cổng lại phát nhiều message.

> **Quy tắc đọc chữ ký:** Trong trường hợp hàm reactive nhiều cổng được Spring Cloud Function/Spring Cloud Stream hỗ trợ, `TupleN<Flux<...>>` là cách biểu diễn nhiều cổng. `List`, `Set`, `Collection` hay `Flux` chứa nhiều phần tử **không tự làm tăng số output binding**.

## 3. Một hàm trả về Collection: một giá trị kết quả

Giả sử đơn hàng có nhiều mã sản phẩm (SKU). Hàm tạo danh sách các dòng mô tả:

~~~java
import java.util.List;
import java.util.function.Function;

public class OrderLogic {

    public record Order(String id, List<String> skus, boolean priority) {}

    public static Function<Order, List<String>> lineLabels() {
        return order -> order.skus().stream()
                .map(sku -> order.id() + ":" + sku)
                .toList();
    }
}
~~~

Sử dụng:

~~~java
OrderLogic.Order order = new OrderLogic.Order(
        "O-101", List.of("SKU-A", "SKU-B", "SKU-C"), false);

List<String> result = OrderLogic.lineLabels().apply(order);
// ["O-101:SKU-A", "O-101:SKU-B", "O-101:SKU-C"]
~~~

Phương thức `apply` được gọi với **một** đối tượng `Order` và trả về **một** đối tượng `List<String>`. Danh sách có ba phần tử nhưng hợp đồng hàm ở tầng Java vẫn là **1 giá trị vào → 1 giá trị ra**.

Khi được trả qua HTTP với JSON serialization phù hợp, kết quả có thể được biểu diễn như một **mảng JSON trong một response**:

~~~json
[
  "O-101:SKU-A",
  "O-101:SKU-B",
  "O-101:SKU-C"
]
~~~

Đây là **một response chứa ba phần tử**, không phải ba HTTP endpoint hay ba response độc lập. Cách adapter thực hiện serialize/unwrap Collection phụ thuộc cấu hình và môi trường gọi; riêng chữ ký `Function<Order, List<String>>` không yêu cầu framework tạo thêm cổng.

Nếu hàm trả về một `Set<String>`, số phần tử có thể nhỏ hơn số mục nhập do loại trùng; nếu trả về `Map<String, Result>`, dữ liệu có nhiều entry. Tuy nhiên, **kích thước Collection luôn độc lập với số cổng đầu ra**.

### 3.1. Collection là một giá trị; Flux là một publisher

So sánh:

~~~java
Function<Order, List<String>> makeLabels;

Function<Flux<Order>, Flux<String>> emitLabels;

Function<Flux<Order>, Flux<List<String>>> emitLabelBatches;
~~~

| Chữ ký | Cách hiểu |
| --- | --- |
| `Function<Order, List<String>>` | Mỗi lần gọi hàm trả một `List` |
| `Function<Flux<Order>, Flux<String>>` | Một luồng đầu ra, phát từng `String` |
| `Function<Flux<Order>, Flux<List<String>>>` | Một luồng đầu ra, mỗi phần tử phát ra lại là một `List<String>` |

Trong cả ba trường hợp, **chỉ có một cổng đầu ra logic**. Riêng với reactive code, mỗi tín hiệu `onNext` của `Flux<List<String>>` chứa một danh sách; không thể mặc nhiên coi các phần tử nằm bên trong danh sách là các output binding.

Ví dụ biến một đơn hàng thành nhiều tín hiệu `onNext` trên **một** `Flux`:

~~~java
import reactor.core.publisher.Flux;

Function<Flux<OrderLogic.Order>, Flux<String>> emitLabels =
        orders -> orders.flatMapIterable(order ->
                order.skus().stream()
                        .map(sku -> order.id() + ":" + sku)
                        .toList());
~~~

Nếu đầu vào gồm một đơn có ba SKU, `emitLabels` phát ba chuỗi liên tiếp trên **cùng một đầu ra**. Khi kết nối bằng Spring Cloud Stream với adapter/binder tương ứng, từng phần tử của luồng có thể được gửi dưới dạng message riêng trên cùng output binding. Đó là **mở rộng số sự kiện**, không phải tăng *arity*.

## 4. Trường hợp đặc biệt trong Spring Cloud Stream: List<Message<T>>

Spring Cloud Stream có tính năng **batch producer**: khi một hàm trả về `List<Message<T>>`, binder có thể gửi **từng `Message` trong danh sách thành một thông điệp riêng** đến **cùng một output destination**. Tài liệu Spring Cloud Stream minh họa trực tiếp trường hợp này.

Ví dụ tạo ba thông báo kiểm toán từ một mã đơn:

~~~java
import java.util.List;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class AuditBatchConfiguration {

    @Bean
    public Function<String, List<Message<String>>> emitAuditEvents() {
        return id -> List.of(
                MessageBuilder.withPayload("RECEIVED:" + id)
                        .setHeader("eventType", "received").build(),
                MessageBuilder.withPayload("VALIDATED:" + id)
                        .setHeader("eventType", "validated").build(),
                MessageBuilder.withPayload("QUEUED:" + id)
                        .setHeader("eventType", "queued").build());
    }
}
~~~

Nếu đầu vào là `"O-101"`, danh sách trả về có ba `Message<String>`. Trong cơ chế batch producer nói trên, kết quả là:

~~~text
                         ┌─> "RECEIVED:O-101"
emitAuditEvents-out-0 ────┼─> "VALIDATED:O-101"   (cùng một destination)
                         └─> "QUEUED:O-101"

Số output binding: 1
Số message phát ra: 3
~~~

Ví dụ `application.yml` dùng cho **một hàm** `emitAuditEvents`:

~~~yaml
spring:
  cloud:
    function:
      definition: emitAuditEvents
    stream:
      bindings:
        emitAuditEvents-in-0:
          destination: orders.audit.requested
        emitAuditEvents-out-0:
          destination: orders.audit.events
~~~

Ba message cùng đi tới `orders.audit.events` qua **một binding** tên `emitAuditEvents-out-0`. Chúng **không** được tự động gửi lần lượt tới `-out-0`, `-out-1`, `-out-2`.

**Điểm cần giới hạn chính xác:** Cơ chế tách từng `Message` trong `List<Message<T>>` là hành vi được mô tả cho **batch producer của Spring Cloud Stream**. Không nên suy rằng **mọi** adapter HTTP/serverless, hoặc **mọi** Collection như `List<String>`, `Set<String>`, `List<Order>` đều bắt buộc phát từng phần tử thành message riêng. Đó là hành vi phụ thuộc cách adapter xử lý kiểu trả về.

Khi trả về một Collection rỗng, số message thực tế có thể bằng không dù output binding vẫn tồn tại. Khi trả về danh sách dài, số message có thể lớn nhưng số binding không đổi.

### 4.1. “Batch consumer” có làm tăng số input binding không?

Không. Spring Cloud Stream còn hỗ trợ **batch consumer** đối với binder có khả năng cung cấp batch và khi bật cấu hình batch mode:

~~~java
@Bean
public Function<List<String>, Integer> countBatch() {
    return List::size;
}
~~~

Ví dụ kích hoạt cho binding đầu vào:

~~~yaml
spring:
  cloud:
    function:
      definition: countBatch
    stream:
      bindings:
        countBatch-in-0:
          destination: orders.in
          consumer:
            batch-mode: true
        countBatch-out-0:
          destination: orders.count
~~~

`List<String>` ở **đầu vào** biểu diễn một batch nhiều payload nhưng vẫn chỉ có **một input binding**, `countBatch-in-0`. Tùy binder, các header theo từng message trong batch có cách tổ chức riêng; cần đọc tài liệu binder khi sử dụng metadata.

Batch producer/consumer và nhiều input/output binding giải quyết **hai trục thiết kế khác nhau**: batch là cách nhóm/phân rã **message** trên một cổng; binding là điểm nối của **luồng** với bên ngoài.

## 5. Nhiều đầu ra thật sự: Tuple2<Flux<A>, Flux<B>>

Nếu yêu cầu là một nhóm sự kiện đi tới topic `orders.priority`, còn nhóm khác đi tới topic `orders.standard`, chỉ trả về `List<Order>` là chưa biểu diễn được hai đích độc lập.

Ta khai báo một **reactive function** trả về tuple có hai publisher:

~~~java
import java.util.List;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class OrderRoutingConfiguration {

    public record Order(String id, List<String> skus, boolean priority) {}

    @Bean
    public Function<Flux<Order>, Tuple2<Flux<Order>, Flux<Order>>>
            routeOrders() {
        return source -> {
            // Hai nhánh dùng chung upstream sau khi cả hai subscribe.
            Flux<Order> shared = source.publish().autoConnect(2);

            Flux<Order> priorityOrders = shared.filter(Order::priority);
            Flux<Order> standardOrders =
                    shared.filter(order -> !order.priority());

            return Tuples.of(priorityOrders, standardOrders);
        };
    }
}
~~~

`Tuple2` ở đây có hai thành phần `Flux<Order>`. Spring Cloud Function nhận diện **function arity 1 → 2** trong ngữ cảnh reactive, từ đó Spring Cloud Stream có thể tạo và sử dụng hai output binding:

| Binding | Thành phần tuple | Ý nghĩa |
| --- | --- | --- |
| `routeOrders-in-0` | `Flux<Order> source` | Luồng đơn hàng đến |
| `routeOrders-out-0` | `Tuple2.getT1()` | Luồng đơn ưu tiên |
| `routeOrders-out-1` | `Tuple2.getT2()` | Luồng đơn thông thường |

Cấu hình `application.yml` riêng cho hàm `routeOrders`:

~~~yaml
spring:
  cloud:
    function:
      definition: routeOrders
    stream:
      bindings:
        routeOrders-in-0:
          destination: orders.received
        routeOrders-out-0:
          destination: orders.priority
        routeOrders-out-1:
          destination: orders.standard
~~~

~~~text
orders.received
      |
      v
 routeOrders
      |
      +-- getT1() --> routeOrders-out-0 --> orders.priority
      |
      +-- getT2() --> routeOrders-out-1 --> orders.standard
~~~

Với các đơn đầu vào:

~~~java
new OrderRoutingConfiguration.Order("O-101", List.of("A"), true);
new OrderRoutingConfiguration.Order("O-102", List.of("B", "C"), false);
new OrderRoutingConfiguration.Order("O-103", List.of("D"), true);
~~~

Nhánh `out-0` phát **hai** đơn `O-101`, `O-103`. Nhánh `out-1` phát **một** đơn `O-102`. Tổng số sự kiện là ba nhưng **số binding là hai**, được khai báo bởi `Tuple2<Flux<Order>, Flux<Order>>`. Danh sách SKU nằm **bên trong** từng `Order` không ảnh hưởng đến số cổng.

### 5.1. Vì sao cần chú ý subscription?

Với `Flux` là nguồn lạnh (*cold publisher*), nếu viết:

~~~java
Flux<Order> priority = source.filter(Order::priority);
Flux<Order> standard = source.filter(order -> !order.priority());
return Tuples.of(priority, standard);
~~~

hai output khi được subscribe có thể tạo **hai subscription độc lập** đến `source`, dẫn đến chạy lại truy vấn, tác dụng phụ lặp hoặc nhận hai lần dữ liệu.

`source.publish().autoConnect(2)` tạo một nguồn được chia sẻ, chỉ kết nối upstream sau khi đã có **hai subscriber**. Mẫu này phù hợp khi adapter subscribe **cả hai output**. Nếu chỉ một output được subscribe, nguồn sẽ **chưa** kết nối và có thể không phát dữ liệu. Khi xây dựng hệ thống thực tế, cần cân nhắc vòng đời subscriber, backpressure và tác động khi một nhánh chậm hoặc lỗi.

Nếu mục tiêu là **một thông điệp được gửi sang cả hai đích**, hai nhánh có thể cùng dùng `shared` mà không cần hai điều kiện `filter` loại trừ nhau:

~~~java
Flux<Order> primary = shared;
Flux<Order> audit = shared;
return Tuples.of(primary, audit);
~~~

Khi ấy mọi sự kiện có thể được phát qua **hai binding**. Tuy nhiên, hai destination độc lập không mặc nhiên tạo giao dịch nguyên tử giữa các broker hay bảo đảm cả hai đích nhận thành công cùng lúc.

## 6. So sánh các chữ ký dễ gây hiểu sai

| Chữ ký Java | Số output binding logic | Số phần tử/message có thể phát |
| --- | ---: | --- |
| `Function<Order, List<Line>>` | 1 | Một giá trị `List` chứa nhiều `Line`; adapter quyết định cách truyền |
| `Function<String, List<Message<String>>>` | 1 | Spring Cloud Stream batch producer có thể gửi từng `Message` trên cùng binding |
| `Function<Flux<Order>, Flux<Line>>` | 1 | Nhiều `Line` dưới dạng nhiều tín hiệu `onNext` trên một luồng |
| `Function<Flux<Order>, Flux<List<Line>>>` | 1 | Nhiều `List` được phát trên cùng luồng |
| `Function<Flux<Order>, Flux<Tuple2<A, B>>>` | 1 | Mỗi phần tử trên một luồng là một tuple giá trị |
| `Function<Flux<Order>, Tuple2<Flux<A>, Flux<B>>>` | **2** | Hai luồng độc lập, mỗi luồng có thể phát 0..N phần tử |
| `Function<Flux<Order>, Tuple3<Flux<A>, Flux<B>, Flux<C>>>` | **3** | Ba luồng độc lập |
| `Function<Order, Tuple2<A, B>>` | 1 trong mô hình trả về một giá trị | Trả một đối tượng tuple; **không mặc nhiên** là reactive multi-output |

**Hai hình dạng khác nhau ở vị trí `Flux`:**

~~~java
// MỘT luồng, mỗi phần tử là một cặp.
Flux<Tuple2<String, Integer>>

// HAI luồng, mỗi luồng mang một kiểu phần tử.
Tuple2<Flux<String>, Flux<Integer>>
~~~

Đặc biệt, `Tuple2<List<A>, List<B>>` vẫn chỉ là **một tuple chứa hai danh sách** ở mức giá trị Java. Đừng suy hai output binding chỉ vì một đối tượng chứa hai field hoặc hai Collection. Hỗ trợ function arity nhiều binding trong Spring Cloud Function được định nghĩa cho **reactive functions với tuple các `Flux`**, và mức hỗ trợ tùy adapter.

## 7. Kiểm thử: số phần tử khác số đầu ra

Ta có thể xác minh cả hai mô hình trước khi nối broker.

### 7.1. Kiểm thử Collection được trả về như một giá trị

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderLogicTest {

    @Test
    void createsOneListWithThreeItems() {
        var order = new OrderLogic.Order(
                "O-101", List.of("A", "B", "C"), true);

        List<String> labels = OrderLogic.lineLabels().apply(order);

        assertEquals(3, labels.size());
        assertEquals(
                List.of("O-101:A", "O-101:B", "O-101:C"),
                labels);
    }
}
~~~

Kết quả có ba phần tử `String`, nhưng `OrderLogic.lineLabels()` vẫn là `Function<Order, List<String>>` với **một giá trị trả về**.

### 7.2. Kiểm thử hai nhánh reactive

Ví dụ dùng JUnit 5 cùng `reactor-test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;

class OrderRoutingConfigurationTest {

    @Test
    void sendsOrdersToTwoIndependentOutputs() {
        var first = new OrderRoutingConfiguration.Order(
                "O-101", List.of("A"), true);
        var second = new OrderRoutingConfiguration.Order(
                "O-102", List.of("B", "C"), false);
        var third = new OrderRoutingConfiguration.Order(
                "O-103", List.of("D"), true);

        var function = new OrderRoutingConfiguration().routeOrders();
        Tuple2<Flux<OrderRoutingConfiguration.Order>,
                Flux<OrderRoutingConfiguration.Order>> outputs =
                function.apply(Flux.just(first, second, third));

        // Hai nhánh được subscribe đồng thời để autoConnect(2) hoạt động.
        StepVerifier.create(Mono.zip(
                        outputs.getT1()
                                .map(OrderRoutingConfiguration.Order::id)
                                .collectList(),
                        outputs.getT2()
                                .map(OrderRoutingConfiguration.Order::id)
                                .collectList()))
                .assertNext(groups -> {
                    assertEquals(
                            List.of("O-101", "O-103"), groups.getT1());
                    assertEquals(
                            List.of("O-102"), groups.getT2());
                })
                .verifyComplete();
    }
}
~~~

Kiểm thử cho thấy **hai publisher đầu ra**; tổng cộng chúng phát ba đơn nhưng số cổng là hai. `Mono.zip` dùng để **thu thập đồng thời kết quả của hai nhánh trong kiểm thử**, không tạo thêm binding. `collectList()` chỉ nên dùng với nguồn hữu hạn trong kiểm thử; một stream sản xuất liên tục có thể không bao giờ hoàn tất.

### 7.3. Kiểm thử batch producer một đầu ra

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

class AuditBatchConfigurationTest {

    @Test
    void returnsThreeMessagesForTheSameOutput() {
        List<Message<String>> messages =
                new AuditBatchConfiguration()
                        .emitAuditEvents().apply("O-101");

        assertEquals(3, messages.size());
        assertEquals("RECEIVED:O-101", messages.get(0).getPayload());
        assertEquals("VALIDATED:O-101", messages.get(1).getPayload());
        assertEquals("QUEUED:O-101", messages.get(2).getPayload());
    }
}
~~~

Kiểm thử này xác nhận hàm tạo **ba `Message`**. Để xác nhận cách binder gửi từng message đến **một destination**, cần kiểm thử tích hợp với Spring Cloud Stream/binder thích hợp. Không nên coi unit test Java là bằng chứng đã cấu hình topic hoặc đã giao message thành công.

## 8. Chọn thiết kế theo yêu cầu thực tế

| Yêu cầu | Mô hình gợi ý |
| --- | --- |
| Trả một danh sách kết quả cho người gọi HTTP | `Function<I, List<O>>`; adapter serialize như một response phù hợp |
| Phát nhiều sự kiện trên cùng một topic từ một luồng | `Function<Flux<I>, Flux<O>>`, dùng `flatMap`/`flatMapIterable` khi cần |
| Từ một input tạo nhiều `Message` đến **cùng** destination | `Function<I, List<Message<O>>>` với Spring Cloud Stream batch producer |
| Đưa kết quả đến hai topic khác nhau | Reactive `Function<Flux<I>, Tuple2<Flux<A>, Flux<B>>>` |
| Đưa kết quả đến ba topic khác nhau | Reactive `Function<Flux<I>, Tuple3<Flux<A>, Flux<B>, Flux<C>>>` |
| Đích thay đổi động theo từng message | Cân nhắc routing/`StreamBridge` theo khả năng Spring Cloud Stream |
| Mỗi lần nhận một batch message cần xử lý theo danh sách | `Function<List<I>, O>` với batch consumer do binder hỗ trợ |

### Bốn lỗi phổ biến

1. **Đếm phần tử Collection thành số cổng.** `List` có 20 mục vẫn có thể là một giá trị kết quả của một hàm.
2. **Nhầm nhiều message cùng binding với nhiều destination.** Spring Cloud Stream batch producer có thể gửi mỗi `Message` riêng, nhưng tên output vẫn là `functionName-out-0`.
3. **Đổi `Flux<Tuple2<A, B>>` thành `Tuple2<Flux<A>, Flux<B>>` mà không đánh giá ý nghĩa.** Kiểu đầu mô tả một luồng các cặp; kiểu sau biểu diễn hai luồng có thể cần subscribe và xử lý backpressure riêng.
4. **Giả định mọi adapter hiểu tuple reactive như Spring Cloud Stream.** HTTP/serverless có thể có mô hình request-response khác. Khả năng ánh xạ nhiều binding phải được xác nhận theo adapter.

### Kết nối với FunctionCatalog và composition

`FunctionCatalog` có thể tìm bean theo tên, chuẩn hóa chữ ký, hỗ trợ chuyển đổi kiểu/thông điệp và composition giữa các hàm có kiểu tương thích. Nhưng:

- Ghép `a|b` là **gọi tuần tự** đầu ra của `a` sang đầu vào của `b`; nó không tự biến một `List` thành nhiều output binding.
- Có nhiều phần tử trong `List` không có nghĩa hệ thống tự cấu hình nhiều binder destination.
- Với nhiều đầu ra thực sự, cấu trúc reactive `TupleN<Flux<...>>` và cấu hình binding là một phần của **hợp đồng tích hợp**, không chỉ là chi tiết dữ liệu.

Sự phân biệt này giúp cùng logic nghiệp vụ có thể được tái sử dụng qua HTTP, sự kiện hoặc serverless mà vẫn mô tả chính xác **giá trị trả về**, **số thông điệp** và **đích nhận** của từng môi trường.

## 9. Bài tập tự kiểm tra

**Câu 1.** Hàm `Function<String, List<String>>` trả về danh sách 100 chuỗi. Có tự động tạo 100 output binding không?

**Đáp án:** Không. Đây là một kết quả kiểu `List<String>`. Cách 100 phần tử được truyền/serialize tùy adapter; số binding không được suy từ độ dài danh sách.

**Câu 2.** Trong Spring Cloud Stream, hàm `Function<String, List<Message<String>>>` trả về hai message và được cấu hình `-out-0` trỏ tới `audit.events`. Có bao nhiêu output binding?

**Đáp án:** **Một** output binding, `-out-0`. Batch producer có thể gửi **hai message riêng** đến cùng `audit.events`.

**Câu 3.** Hàm `Function<Flux<Order>, Tuple2<Flux<Accepted>, Flux<Rejected>>>` có số đầu ra bao nhiêu?

**Đáp án:** **Hai** output binding, tương ứng `-out-0` và `-out-1` khi adapter hỗ trợ mô hình function arity reactive.

**Câu 4.** `Function<Flux<Order>, Flux<List<Line>>>` phát 50 danh sách trên một `Flux`. Có bao nhiêu output binding? Có bao nhiêu tín hiệu `onNext` được phát?

**Đáp án:** **Một** output binding; có **50** tín hiệu `onNext`, mỗi tín hiệu mang một `List<Line>`. Tổng số phần tử `Line` trong 50 danh sách có thể lớn hơn 50.

**Câu 5.** Cần gửi một sự kiện sang hai topic `orders.main` và `orders.audit`. Trả `List<Message<Order>>` với hai message có đủ để tạo hai binding không?

**Đáp án:** Không. Cần thiết kế định tuyến đến hai destination độc lập: ví dụ hai đầu ra `Tuple2<Flux<Order>, Flux<Order>>` trong Spring Cloud Stream, hoặc một cơ chế dynamic routing được hỗ trợ. Hai phần tử trong một `List<Message<Order>>` theo batch producer vẫn thuộc **một output binding**.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model, Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages (Batch Producers, Batch Consumers)](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Functional binding, binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
