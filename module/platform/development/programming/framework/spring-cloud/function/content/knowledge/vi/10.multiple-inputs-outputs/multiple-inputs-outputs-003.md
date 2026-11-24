# Tách một luồng thành nhiều đầu ra

## 1. Khi nào cần tách một luồng dữ liệu?

Trong **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được đóng gói thành các bean `Supplier`, `Function` và `Consumer`. Nhờ đó, một hàm có thể được `FunctionCatalog` quản lý, tham gia composition, được hỗ trợ chuyển đổi thông điệp và được tích hợp với HTTP, hệ thống sự kiện hoặc môi trường serverless thông qua adapter thích hợp.

Một nhu cầu phổ biến trong hệ thống xử lý sự kiện là **đưa các sự kiện đi vào cùng một luồng sang các đầu ra khác nhau**. Ví dụ, mọi đơn hàng đi vào topic `orders.received`, nhưng:

- Đơn hàng từ **1.000.000 VND trở lên** phải chuyển đến `orders.priority` để được ưu tiên xử lý.
- Đơn hàng **dưới 1.000.000 VND** chuyển đến `orders.standard`.

Hàm cần nhận **một luồng đầu vào** và tạo **hai luồng đầu ra** với đích riêng. Đây là bài toán *scatter*, *split* hoặc *fan-out* tùy cách phân phối sự kiện.

~~~text
                                      ┌─► orders.priority ─► Xử lý ưu tiên
orders.received ─► splitOrders ───────┤
                                      └─► orders.standard ─► Xử lý thông thường
                    1 đầu vào                 2 đầu ra
~~~

Ở đây, **hai đầu ra** nghĩa là hai cổng/binding độc lập. Điều này khác với một cổng phát nhiều phần tử: `Flux<Order>` có thể phát hàng triệu đơn hàng nhưng vẫn chỉ biểu diễn **một luồng**.

Sau bài học, bạn có thể:

1. Phân biệt *phân loại độc quyền* và *sao chép sự kiện* khi tách luồng.
2. Khai báo một bean `Function<Flux<T>, Tuple2<Flux<A>, Flux<B>>>`.
3. Chia sẻ một nguồn `Flux` để các nhánh không vô tình subscribe nguồn nhiều lần.
4. Ánh xạ từng đầu ra thành binding riêng trong Spring Cloud Stream.
5. Kiểm thử cả hai nhánh, bao gồm dữ liệu biên và số lần subscribe nguồn.

## 2. Hai kiểu tách luồng cần phân biệt

Cùng một chữ ký hàm có thể đáp ứng hai yêu cầu nghiệp vụ rất khác:

| Kiểu phân phối | Cách hoạt động | Ví dụ |
| --- | --- | --- |
| **Phân loại** (*partition*) | Mỗi sự kiện thuộc **một** nhánh theo quy tắc; các nhánh không chồng lấn nếu điều kiện bổ sung cho nhau | Đơn giá trị cao → ưu tiên; còn lại → thông thường |
| **Sao chép/phát nhiều nơi** (*broadcast/fan-out*) | Cùng một sự kiện có thể đi đến **nhiều** nhánh | Một đơn hàng → hệ thống xử lý và hệ thống giám sát |

Về kỹ thuật, cả hai có thể có chữ ký `Function<Flux<Order>, Tuple2<Flux<...>, Flux<...>>>`. **Chữ ký chỉ xác định số đầu ra; logic trong các nhánh mới quyết định sự kiện nào xuất hiện ở đâu.**

Khi phân loại, hãy làm rõ ba trường hợp:

- **Thiếu:** Có sự kiện nào không đi vào nhánh nào không? Điều này có được phép không?
- **Chồng lấn:** Có sự kiện nào xuất hiện ở cả hai nhánh không? Nếu có, đó là yêu cầu hay lỗi?
- **Biên:** Với điều kiện `total >= 1_000_000`, đơn có tổng tiền đúng `1_000_000` thuộc nhóm nào?

Một thiết kế dễ kiểm tra sử dụng hai điều kiện đối nhau: `>=` và `<`. Khi ấy, mọi giá trị số hợp lệ sẽ được phân vào đúng một nhánh.

## 3. Chữ ký hàm biểu diễn hai đầu ra

Với Spring Cloud Function, mô hình nhiều cổng dựa trên **reactive function arity**, trong đó `Flux` biểu diễn các luồng còn `TupleN` của Project Reactor biểu diễn số cổng và kiểu của từng cổng:

~~~java
Function<Flux<Order>, Tuple2<Flux<Order>, Flux<Order>>>
~~~

Đọc từ trong ra ngoài:

- `Flux<Order>` bên trái: **một** luồng đầu vào gồm các `Order`.
- `Tuple2<..., ...>` bên phải: kết quả chứa **hai** thành phần.
- Thành phần thứ nhất `getT1()`: luồng đầu ra số **0**.
- Thành phần thứ hai `getT2()`: luồng đầu ra số **1**.

`Tuple2` được tạo bằng `Tuples.of(first, second)` trong package `reactor.util.function`. Hai thành phần không nhất thiết cùng kiểu. Ví dụ, nếu cần xuất hai kiểu payload khác nhau, hợp đồng có thể là:

~~~java
Function<Flux<Order>, Tuple2<Flux<PriorityOrder>, Flux<StandardOrder>>>
~~~

Spring Cloud Function dùng thông tin **số lượng** và **kiểu** của thành phần tuple để hỗ trợ nhận diện các cổng trong trường hợp reactive; Spring Cloud Stream có thể ánh xạ những cổng đó thành các binding tương ứng. Cơ chế function arity nhiều đầu ra này được thiết kế cho **reactive functions**.

**Không nhầm các kiểu sau:**

| Kiểu trả về | Ý nghĩa |
| --- | --- |
| `Flux<Order>` | Một đầu ra, có nhiều đơn hàng |
| `Flux<List<Order>>` | Một đầu ra, mỗi phần tử là một danh sách |
| `Flux<Tuple2<A, B>>` | Một đầu ra, mỗi phần tử là một cặp giá trị |
| `Tuple2<Flux<A>, Flux<B>>` | **Hai đầu ra** là hai publisher độc lập |
| `Tuple2<A, B>` | Hai giá trị Java; tự nó **không** tạo hai output binding của một reactive function |

## 4. Ví dụ hoàn chỉnh: phân loại đơn hàng thành hai luồng

Ví dụ sau dùng **Java 17+** (để khai báo `record`). `Order` gồm mã đơn và tổng tiền VND, không bao gồm logic kết nối đến Kafka hoặc RabbitMQ. Quy tắc phân loại được viết trong một Spring bean:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class OrderRoutingConfig {

    public record Order(String id, long totalVnd) {
    }

    @Bean
    public Function<Flux<Order>, Tuple2<Flux<Order>, Flux<Order>>>
            splitOrders() {

        return input -> {
            // Cả hai nhánh dùng cùng một subscription đến input.
            // Nguồn chỉ được kết nối khi cả hai nhánh đã subscribe.
            Flux<Order> shared = input.publish().autoConnect(2);

            Flux<Order> priority = shared
                    .filter(order -> order.totalVnd() >= 1_000_000L);

            Flux<Order> standard = shared
                    .filter(order -> order.totalVnd() < 1_000_000L);

            // Thứ tự ở đây quyết định chỉ số các output binding.
            return Tuples.of(priority, standard);
        };
    }
}
~~~

Ví dụ dữ liệu:

| Đơn hàng đầu vào | Tổng tiền | Nhánh phát ra |
| --- | ---: | --- |
| `O-101` | 1.500.000 VND | `priority` → output 0 |
| `O-102` | 230.000 VND | `standard` → output 1 |
| `O-103` | 1.000.000 VND | `priority` → output 0 |
| `O-104` | 999.999 VND | `standard` → output 1 |

Điểm cần hiểu ở từng thao tác:

1. `input` là nguồn dữ liệu, chưa nhất thiết phát phần tử ngay lúc phương thức `apply` được gọi.
2. `publish().autoConnect(2)` tạo một luồng **được chia sẻ** và đợi đủ **hai subscriber** trước khi subscribe đến nguồn.
3. Hai nhánh `filter` nhận các phần tử từ cùng nguồn chia sẻ; mỗi nhánh chỉ phát các phần tử thỏa điều kiện.
4. `Tuples.of(priority, standard)` trả về hai luồng với thứ tự cố định. Framework/adapter quyết định cách subscribe vào từng luồng và gửi đến đích tương ứng.

Ví dụ cố ý xử lý mọi giá trị `long` theo quy tắc so sánh. Trong ứng dụng thực tế, nếu tổng tiền âm hoặc thiếu dữ liệu là không hợp lệ, hãy bổ sung validation và một chính sách xử lý riêng, chẳng hạn loại bỏ có ghi nhận hoặc thêm nhánh lỗi theo yêu cầu nghiệp vụ.

## 5. Ánh xạ hai luồng thành hai output binding

`FunctionCatalog` giúp Spring Cloud Function nhận diện và truy xuất bean `splitOrders`. Khi dùng **Spring Cloud Stream**, mô hình `1 → 2` ở trên có các tên binding mặc định:

| Binding | Thành phần trong hàm | Nơi gửi/nhận ví dụ |
| --- | --- | --- |
| `splitOrders-in-0` | `Flux<Order> input` | `orders.received` |
| `splitOrders-out-0` | `Tuple2.getT1()` – `priority` | `orders.priority` |
| `splitOrders-out-1` | `Tuple2.getT2()` – `standard` | `orders.standard` |

Cấu hình `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: splitOrders
    stream:
      bindings:
        splitOrders-in-0:
          destination: orders.received
          content-type: application/json
        splitOrders-out-0:
          destination: orders.priority
          content-type: application/json
        splitOrders-out-1:
          destination: orders.standard
          content-type: application/json
~~~

Cấu hình trên giả định ứng dụng đã có các dependency phù hợp, bao gồm Spring Cloud Function, Spring Cloud Stream và **binder** cho hệ thống messaging được chọn. Một bean `Function` không tự tạo broker; cấu hình `destination` chỉ phát huy tác dụng khi adapter/binder thực sự được khởi tạo.

**Đừng đảo thứ tự tuple khi sửa code.** Nếu thay `return Tuples.of(priority, standard)` thành `Tuples.of(standard, priority)` nhưng giữ YAML, dữ liệu sẽ được gửi nhầm đích dù ứng dụng vẫn có thể khởi động. Nên xác định rõ hợp đồng của từng chỉ số và kiểm thử với cấu hình binding.

Mỗi output binding có thể đặt chính sách chuyển đổi thông điệp, producer, partitioning hoặc xử lý lỗi theo khả năng của binder. Vì hai đầu ra có thể có **kiểu payload khác nhau**, thông tin generic bên trong `Tuple2` rất có ích khi framework chuyển đổi dữ liệu.

## 6. Vì sao chia một Flux thành hai nhánh cần quản lý subscription?

Đây là phần quan trọng nhất khi thực hiện split bằng reactive code.

### 6.1. Cách viết dễ gây subscribe nguồn hai lần

Đoạn dưới tạo hai nhánh trực tiếp từ `input`:

~~~java
Flux<Order> priority = input
        .filter(order -> order.totalVnd() >= 1_000_000L);
Flux<Order> standard = input
        .filter(order -> order.totalVnd() < 1_000_000L);

return Tuples.of(priority, standard);
~~~

Với **cold publisher**, mỗi lần subscribe vào một nhánh có thể subscribe lại đến `input`. Điều này có thể gây:

- Chạy lại truy vấn, yêu cầu HTTP hoặc công việc tạo nguồn dữ liệu.
- Gây tác dụng phụ lặp như ghi nhận sự kiện hai lần.
- Xử lý hai lượt dữ liệu khác nhau nếu nguồn thay đổi giữa các lần subscribe.

Hai subscription độc lập đôi khi là điều mong muốn. Nhưng nếu mục tiêu là **một lần đọc nguồn rồi phân phối sang hai nhánh**, cần kết nối chung như trong ví dụ `publish().autoConnect(2)`.

### 6.2. Tại sao `publish().autoConnect(2)` phù hợp với ví dụ?

~~~text
                subscribe nhánh A
                         │
                         ▼
               ┌───────────────────┐
input ─────────┤ publish()         ├──► priority.filter(...)
               │ autoConnect(2)    │
               └───────────────────┘
                         │
                         ▼
                subscribe nhánh B ──► standard.filter(...)

Khi đủ cả hai subscriber → bắt đầu kết nối đến input.
~~~

- `publish()` tạo `ConnectableFlux` chia sẻ dữ liệu từ nguồn.
- `autoConnect(2)` kết nối đến nguồn sau khi đã có **hai lượt đăng ký nhận dữ liệu**.
- Với các subscriber đã hiện diện tại thời điểm kết nối, cả hai nhánh có cơ hội quan sát cùng dòng sự kiện; `filter` quyết định nhánh nào được phát từng phần tử.

**Giả định bắt buộc của mẫu này:** cả hai output đều được subscribe. Nếu chỉ lấy nhánh ưu tiên bằng `getT1().collectList().block()`, nguồn **không kết nối** do còn thiếu subscriber thứ hai. Vì vậy, một bài kiểm thử chạy lần lượt từng nhánh dễ bị chờ vô hạn.

`autoConnect(2)` không tự ngắt kết nối khi chỉ còn một subscriber. Nếu vòng đời ứng dụng yêu cầu kết nối lại khi số subscriber giảm, `refCount(2)` là một cơ chế khác cần đánh giá. Cách chọn phụ thuộc vào vòng đời subscription của adapter.

### 6.3. Backpressure và nhánh xử lý chậm

`publish()` xét đến yêu cầu nhận dữ liệu (*demand*) của các subscriber. Nếu một nhánh chậm hoặc không có nhu cầu nhận thêm, việc yêu cầu dữ liệu từ nguồn chung có thể bị hạn chế; nhánh kia có thể bị ảnh hưởng theo. Đây là kết quả của **chia sẻ cùng một nguồn có backpressure**, không phải lỗi của `filter`.

Khi hai hệ thống nhận sự kiện có tốc độ rất khác nhau, cần xác định kỳ vọng về độ trễ, bộ đệm, phân luồng qua broker, retry và chính sách xử lý khi một đích gặp sự cố. Không nên vội thêm `onBackpressureBuffer()` không giới hạn hoặc `cache()` cho luồng vô hạn, vì chúng có thể làm tăng bộ nhớ không kiểm soát.

### 6.4. Các lựa chọn thường bị nhầm

| Cách làm | Hành vi cần chú ý |
| --- | --- |
| `input.filter(...), input.filter(...)` | Với cold publisher có thể subscribe upstream hai lần |
| `input.share()` | Thông thường kết nối khi có subscriber đầu tiên; subscriber đến muộn có thể bỏ lỡ dữ liệu |
| `input.publish().autoConnect(2)` | Đợi cả hai subscriber; chia sẻ nguồn nhưng hai nhánh phụ thuộc vào nhau về backpressure |
| `input.publish().refCount(2)` | Kết nối khi đủ subscriber và có thể ngắt khi số subscriber không còn đủ |
| `input.cache()` | Phát lại dữ liệu đã ghi nhớ; phải cân nhắc bộ nhớ với luồng dài hoặc không kết thúc |
| `input.groupBy(key)` | Tạo các nhóm `GroupedFlux` theo khóa; **không** tự tạo output binding mới cho mỗi khóa |

## 7. Kiểm thử cả hai output trong một lần subscribe

Có thể kiểm thử logic `splitOrders` ngay trong bộ kiểm thử Java, không cần broker. Ví dụ dùng **JUnit 5** và **reactor-test**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuple2;

class OrderRoutingConfigTest {

    @Test
    void routesOrdersAndSubscribesSourceOnce() {
        var first = new OrderRoutingConfig.Order("O-101", 1_500_000L);
        var second = new OrderRoutingConfig.Order("O-102", 230_000L);
        var boundary = new OrderRoutingConfig.Order("O-103", 1_000_000L);

        AtomicInteger upstreamSubscriptions = new AtomicInteger();
        Flux<OrderRoutingConfig.Order> source = Flux
                .just(first, second, boundary)
                .doOnSubscribe(s -> upstreamSubscriptions.incrementAndGet());

        Tuple2<
                Flux<OrderRoutingConfig.Order>,
                Flux<OrderRoutingConfig.Order>
        > outputs = new OrderRoutingConfig().splitOrders().apply(source);

        // Mono.zip đăng ký vào cả hai nhánh, đủ điều kiện autoConnect(2).
        Mono<
                Tuple2<List<String>, List<String>>
        > groupedIds = Mono.zip(
                outputs.getT1().map(OrderRoutingConfig.Order::id).collectList(),
                outputs.getT2().map(OrderRoutingConfig.Order::id).collectList());

        StepVerifier.create(groupedIds)
                .assertNext(groups -> {
                    assertEquals(List.of("O-101", "O-103"), groups.getT1());
                    assertEquals(List.of("O-102"), groups.getT2());
                })
                .verifyComplete();

        assertEquals(1, upstreamSubscriptions.get());
    }
}
~~~

Kiểm thử xác nhận **ba thuộc tính khác nhau**:

1. **Đúng phân loại:** hai đơn giá trị cao, bao gồm giá trị đúng ngưỡng, đến output 0; đơn còn lại đến output 1.
2. **Cả hai nhánh được subscribe:** `Mono.zip` kết hợp việc thu thập của hai nhánh, vì vậy nguồn chung có thể kết nối.
3. **Nguồn chỉ subscribe một lần:** bộ đếm `upstreamSubscriptions` được tăng khi publisher đầu vào có subscription.

Chỉ nên dùng `collectList()` với nguồn **hữu hạn** như `Flux.just(...)` trong kiểm thử. Nếu ứng dụng chạy liên tục trên một topic, luồng thông thường không hoàn tất và `collectList()` sẽ chờ hoặc tích lũy dữ liệu mãi. Trong production, thông điệp được xử lý theo từng lần phát của `Flux`.

## 8. Khi muốn gửi một sự kiện ra cả hai đầu ra

Trong trường hợp cần một kênh cho nghiệp vụ và một kênh cho giám sát, hai nhánh **không loại trừ nhau**:

~~~java
@Bean
public Function<Flux<OrderRoutingConfig.Order>,
        Tuple2<Flux<OrderRoutingConfig.Order>, Flux<String>>>
        processAndAudit() {

    return input -> {
        Flux<OrderRoutingConfig.Order> shared =
                input.publish().autoConnect(2);

        Flux<OrderRoutingConfig.Order> processing = shared;
        Flux<String> audit = shared.map(order ->
                "ORDER_RECEIVED:" + order.id());

        return Tuples.of(processing, audit);
    };
}
~~~

Lúc này cùng một đơn hàng có thể xuất hiện dưới dạng **hai payload khác nhau**:

- `processAndAudit-out-0` phát `Order` để xử lý nghiệp vụ.
- `processAndAudit-out-1` phát `String` phục vụ kiểm toán/giám sát.

Điều này vẫn là **một nguồn đầu vào, hai đầu ra**. Để kiểm thử cách nhân bản sự kiện, cần subscribe cả hai output và xác nhận số phần tử mỗi nhánh. Nếu yêu cầu đảm bảo giao nhận đến hai destination trong các tình huống lỗi khác nhau, cần xem thêm bảo đảm giao hàng của binder và chiến lược retry; việc trả hai `Flux` tự nó không cung cấp giao dịch nguyên tử trên hai broker destination.

## 9. Các lưu ý khi triển khai thực tế

### 9.1. Xử lý lỗi

Reactive function thường thiết lập pipeline một lần, sau đó các bản ghi được xử lý khi `Flux` phát sự kiện. Lỗi xảy ra ở giữa pipeline được phát dưới dạng tín hiệu `onError`; không thể mặc nhiên trông đợi cơ chế retry của hàm imperative áp dụng cho từng phần tử trong luồng reactive.

Với đơn hàng không hợp lệ, cần quyết định rõ có bỏ qua, phát vào nhánh lỗi, ghi log, gửi đến dead-letter destination hay dừng cả luồng. Có thể cân nhắc xử lý lỗi ở mức phần tử, ví dụ tách validation và tạo mô hình kết quả `Valid/Invalid` trước khi phân nhánh, thay vì để một exception ngoài dự kiến kết thúc subscription.

### 9.2. Payload, headers và chuyển đổi thông điệp

Trong Spring Cloud Stream, mỗi output binding có thể có `content-type` và cấu hình chuyển đổi tương ứng. Nếu logic cần giữ các header như correlation ID hoặc trace ID, có thể dùng payload `Message<Order>` hoặc xây dựng lại `Message<?>` có header mong muốn. Khi biến đổi từ `Order` thành `String`, **không giả định** mọi header của thông điệp ban đầu sẽ tự động được sao chép.

Hợp đồng trả về `Tuple2<Flux<A>, Flux<B>>` cho phép Spring Cloud Function cung cấp thông tin kiểu theo từng đầu ra. Dữ liệu thực tế vẫn phải tương thích với cấu hình chuyển đổi, serializer và schema của hệ thống giao tiếp.

### 9.3. Số đầu ra là cố định tại hợp đồng hàm

`Tuple2` nghĩa là hai đầu ra **được khai báo trước**. Nếu yêu cầu tạo một topic mới cho từng mã khách hàng phát sinh trong thời gian chạy, một tuple cố định không mô tả được số output tăng động. Khi cần đích động, có thể cân nhắc chức năng routing hoặc `StreamBridge` của Spring Cloud Stream với chính sách quản trị destination phù hợp.

### 9.4. Composition và khả năng tái sử dụng

Trong cùng ứng dụng, có thể tái sử dụng các predicate/logic phân loại độc lập với broker. `FunctionCatalog` hỗ trợ tìm và composition các functional bean tương thích kiểu; tuy nhiên dấu `|` trong `spring.cloud.function.definition` biểu diễn **ghép tuần tự**, không phải tự động nhân một đầu vào thành nhiều binding. Nếu mục tiêu là hai destination, hãy thể hiện rõ hai luồng đầu ra và cấu hình chúng bằng adapter hỗ trợ nhiều cổng.

HTTP hoặc môi trường serverless có thể gọi lại logic phân loại, nhưng **không mặc nhiên hỗ trợ tuple reactive như hai HTTP response hoặc hai endpoint**. Khả năng ánh xạ đa cổng tùy adapter. Spring Cloud Stream là ngữ cảnh tự nhiên để áp dụng ví dụ này vào các luồng sự kiện.

## 10. Checklist thiết kế và bài tập tự kiểm tra

Trước khi đưa một hàm tách luồng vào hệ thống, hãy kiểm tra:

- [ ] Đã xác định rõ mỗi bản ghi nên xuất hiện ở một nhánh hay nhiều nhánh.
- [ ] Chữ ký `Function<Flux<T>, TupleN<Flux<...>>>` mô tả đúng số cổng và kiểu payload.
- [ ] Thứ tự `Tuples.of(...)` khớp với các binding `-out-0`, `-out-1`.
- [ ] Cả hai output được subscribe và việc chia sẻ nguồn phù hợp với vòng đời adapter.
- [ ] Các điều kiện biên, bản ghi không hợp lệ và trường hợp một nhánh không có phần tử đã được xét.
- [ ] Backpressure, lỗi, retry và bảo đảm gửi thông điệp được cân nhắc ở mức hệ thống.
- [ ] Có kiểm thử xác nhận phân loại đúng, không nhân đôi tác dụng phụ do subscribe lại nguồn.

### Bài tập 1: Nhận diện đầu ra

Hàm sau tạo bao nhiêu output binding theo mô hình nhiều cổng của Spring Cloud Function?

~~~java
Function<Flux<Integer>, Tuple2<Flux<Integer>, Flux<String>>>
~~~

**Đáp án:** **Hai** output binding. Thành phần `getT1()` phát `Integer`, thành phần `getT2()` phát `String`. Một đầu vào `Flux<Integer>` có một input binding.

### Bài tập 2: Tìm lỗi trong phân nhánh

Cho một nguồn chỉ phát đúng một sự kiện rồi kết thúc:

~~~java
Flux<Integer> shared = Flux.just(1, 2, 3)
        .publish()
        .autoConnect(2);

Flux<Integer> odd = shared.filter(n -> n % 2 != 0);
Flux<Integer> even = shared.filter(n -> n % 2 == 0);

odd.collectList().block(); // Gọi một mình
~~~

**Điều gì xảy ra?** Chỉ có một subscriber cho `shared` nên chưa đạt ngưỡng `autoConnect(2)`. Vì nguồn chưa kết nối, thao tác `block()` có thể chờ mãi. Cần subscribe đồng thời cả hai nhánh, ví dụ bằng `Mono.zip(odd.collectList(), even.collectList())` đối với nguồn hữu hạn.

### Bài tập 3: Phân biệt split và broadcast

Thay hai điều kiện `filter` ở ví dụ đơn hàng bằng hai phép `map` khác nhau trên cùng `shared`, rồi trả `Tuples.of(first, second)`. Khi cả hai output được subscribe, mỗi sự kiện hợp lệ có thể được phát bao nhiêu lần qua toàn bộ các đầu ra?

**Đáp án:** Có thể phát **hai bản biểu diễn** của sự kiện: một ở output 0 và một ở output 1. Đây là fan-out/broadcast ở mức dữ liệu đầu ra, khác với phân loại mỗi sự kiện chỉ vào một nhánh.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model, Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Functions with multiple input and output arguments](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Reactor Core — Broadcasting to Multiple Subscribers with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html)
- [Reactor Core — Flux, một chuỗi bất đồng bộ 0 đến N phần tử](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html)
