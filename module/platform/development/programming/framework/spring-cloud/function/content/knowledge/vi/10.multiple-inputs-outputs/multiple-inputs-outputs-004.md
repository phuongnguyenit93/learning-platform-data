# Kết hợp nhiều đầu vào và đồng bộ dữ liệu

## 1. Bài toán: nhiều nguồn phát sự kiện theo nhịp riêng

Trong **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), một nghiệp vụ có thể được đóng gói thành `Supplier`, `Function` hoặc `Consumer` và đăng ký trong Spring. `FunctionCatalog` giúp tìm và chuẩn hóa các hàm, hỗ trợ composition và chuyển đổi thông điệp; adapter phù hợp có thể gọi logic qua HTTP, hệ thống sự kiện hoặc môi trường serverless.

Khi hệ thống chỉ có một luồng đầu vào, ta thường dùng `Function<Flux<A>, Flux<B>>`. Với các nghiệp vụ như **đối soát đơn hàng và thanh toán**, dữ liệu lại đến từ **hai nguồn độc lập**:

- `orders.created` phát `OrderCreated` sau khi đơn hàng được tạo.
- `payments.confirmed` phát `PaymentConfirmed` sau khi giao dịch thanh toán được xác nhận.

Thanh toán có thể đến trước hoặc sau thông điệp tạo đơn, một nguồn có thể nhanh hơn nguồn còn lại, và một trong hai nguồn có thể phát thông điệp trùng hoặc thiếu. Vì vậy, thao tác **kết hợp nhiều đầu vào** phải trả lời không chỉ câu hỏi “có bao nhiêu cổng?”, mà còn cả **“kết hợp bản ghi nào, khi nào phát kết quả, và chờ trong bao lâu?”**.

~~~text
orders.created ────────> [ input 0 ] ┐
                                    ├── reconcileOrders ──> [ output 0 ] ──> orders.reconciled
payments.confirmed ────> [ input 1 ] ┘
                           |
              Quy tắc ghép theo orderId
              và khoảng thời gian cho phép
~~~

**Mục tiêu học tập:**

1. Diễn giải đúng hàm nhiều đầu vào bằng `Tuple2<Flux<...>, Flux<...>>`.
2. Chọn được giữa `merge`, `zip`, `combineLatest`, `concat` và `join`.
3. Hiểu sự khác biệt giữa **đồng bộ theo thứ tự**, **giá trị mới nhất**, **khóa nghiệp vụ** và **thời gian**.
4. Viết một reactive function kết hợp đơn hàng và thanh toán, ánh xạ các input binding qua Spring Cloud Stream.
5. Nhận diện trường hợp dữ liệu đến muộn, trùng lặp, không khớp hoặc cần lưu trạng thái bền vững.

## 2. Biểu diễn hai nguồn độc lập bằng Tuple của Reactor

Spring Cloud Function hỗ trợ *function arity* cho reactive functions, dùng `TupleN` từ **Project Reactor** để mô tả số cổng cùng kiểu dữ liệu từng cổng. Ví dụ:

~~~java
Function<
    Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
    Flux<Reconciliation>
>
~~~

Chữ ký này có **2 cổng đầu vào và 1 cổng đầu ra**:

| Thành phần | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `input.getT1()` | `Flux<OrderCreated>` | Luồng tạo đơn hàng, input 0 |
| `input.getT2()` | `Flux<PaymentConfirmed>` | Luồng xác nhận thanh toán, input 1 |
| Giá trị trả về | `Flux<Reconciliation>` | Kết quả đối soát, output 0 |

Mặc dù phương thức `Function.apply(...)` chỉ nhận **một đối tượng Java** là `Tuple2`, đối tượng này chứa **hai publisher** mà adapter có thể nối với hai nguồn sự kiện độc lập.

**Phân biệt hai cách sử dụng tuple:**

~~~java
// Hai luồng độc lập -> mô hình nhiều cổng đầu vào.
Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>> sources;

// Một luồng gồm các cặp đã ghép -> một cổng đầu ra.
Flux<Tuple2<OrderCreated, PaymentConfirmed>> pairs;
~~~

`Tuple2<Flux<A>, Flux<B>>` **không tự ghép** các bản ghi `A` và `B` với nhau. Nó chỉ giữ hai luồng. Quy tắc kết hợp phải do toán tử Reactor trong thân hàm quyết định.

Hỗ trợ arity nhiều cổng của Spring Cloud Function tập trung vào **reactive functions**; việc viết `Function<A, Tuple2<B, C>>` ở dạng imperative không mặc nhiên tạo hai output binding. Việc ánh xạ các cổng đến topic/queue là nhiệm vụ của adapter, điển hình là **Spring Cloud Stream**, chứ không phải bản thân `Tuple2` tự tạo ra.

## 3. “Đồng bộ dữ liệu” có thể mang nhiều ý nghĩa

Hai luồng cùng phát những bản ghi không có nghĩa hai bản ghi đứng cạnh nhau thuộc cùng một nghiệp vụ. Trước khi chọn toán tử, hãy phân biệt:

| Cách kết hợp | Quy tắc ghép | Khi nào có kết quả? | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `Flux.merge(a, b)` | Không ghép cặp; trộn phần tử từ hai nguồn thành một luồng | Khi một nguồn phát phần tử | Gom sự kiện về kênh chung |
| `Flux.concat(a, b)` | Không ghép cặp; xử lý `a` trước rồi mới đến `b` | Theo thứ tự nguồn đã khai báo | Nối các nguồn **hữu hạn** theo thứ tự |
| `Flux.zip(a, b)` | Ghép **phần tử thứ i** của `a` với phần tử thứ i của `b` | Khi cả hai đã có phần tử cho vị trí đó | Hai nguồn được đảm bảo căn chỉnh theo vị trí |
| `Flux.combineLatest(a, b, fn)` | Dùng **giá trị mới nhất** từ mỗi nguồn | Sau khi cả hai có giá trị đầu tiên, mỗi lần một nguồn cập nhật | Kết hợp trạng thái, cấu hình, chỉ số mới nhất |
| `a.join(b, leftEnd, rightEnd, fn)` | Ghép các phần tử **có cửa sổ tồn tại chồng lấn** | Khi có cặp nằm trong các cửa sổ chồng lấn | Tương quan sự kiện trong một khoảng thời gian |

Không toán tử nào trong bảng tự hiểu `orderId` của đơn hàng và thanh toán. **Khóa nghiệp vụ** phải được kiểm tra trong logic. Nếu cần đảm bảo nhất quán qua sự cố, khởi động lại và dữ liệu trễ nhiều giờ, một phép ghép thuần reactive trong bộ nhớ có thể chưa đủ.

### 3.1. Kết hợp theo vị trí: `zip`

Giả sử hai nguồn đã được chuẩn bị để phần tử ở cùng vị trí đại diện cho cùng một phép đo:

~~~java
Flux<String> stations = Flux.just("HN", "HCM", "DN");
Flux<Integer> readings = Flux.just(28, 32, 30);

Flux<String> reports = Flux.zip(
        stations,
        readings,
        (station, temperature) -> station + "=" + temperature);

// Dữ liệu đầu ra: "HN=28", "HCM=32", "DN=30".
~~~

`zip` chờ cả hai nguồn có phần tử ở một vị trí rồi mới tạo kết quả. Nếu một nguồn phát chậm, kết quả của vị trí tiếp theo phải chờ nguồn đó. Khi không còn khả năng tạo thêm cặp vì một nguồn đã hoàn tất, `zip` kết thúc; các phần tử dư ở nguồn còn lại không tạo ra kết quả.

Nhưng **thứ tự phát không phải khóa nghiệp vụ**. Ví dụ:

~~~text
orders:   O-101, O-102
payments: O-102, O-101

zip theo vị trí:
          (O-101, O-102)  <- sai orderId
          (O-102, O-101)  <- sai orderId
~~~

Vì vậy, không dùng `zip` để đối soát đơn hàng theo `orderId` nếu hai nguồn có thể đến đảo thứ tự, thiếu hoặc lặp thông điệp.

### 3.2. Kết hợp theo trạng thái mới nhất: `combineLatest`

Một hệ thống giám sát có luồng nhiệt độ và luồng ngưỡng cảnh báo thay đổi theo thời gian. Nghiệp vụ cần so sánh **nhiệt độ mới nhất** với **ngưỡng mới nhất**, không ghép một-một theo vị trí:

~~~java
Flux<Double> temperatures = Flux.just(28.0, 29.0);
Flux<Double> thresholds = Flux.just(30.0, 27.0);

Flux<String> alerts = Flux.combineLatest(
        temperatures,
        thresholds,
        (temperature, threshold) ->
                temperature >= threshold ? "ALERT" : "NORMAL");
~~~

Toán tử chỉ bắt đầu phát sau khi **mỗi nguồn đã có ít nhất một giá trị**. Sau đó, khi một nguồn cập nhật, nó kết hợp với giá trị gần nhất đã quan sát ở nguồn kia. Một giá trị có thể tham gia **nhiều kết quả** và các giá trị trung gian có thể không đều được dùng nếu nguồn phát quá nhanh.

`combineLatest` phù hợp để kết hợp trạng thái; nó **không ghép thanh toán với đúng đơn hàng**. Ghép các nguồn theo snapshot mới nhất có thể tạo cặp sai nếu nhiều mã đơn hàng xen kẽ nhau.

### 3.3. Chỉ hợp nhất sự kiện: `merge`

~~~java
Flux<String> allEvents = Flux.merge(
        orders.map(order -> "ORDER:" + order.id()),
        payments.map(payment -> "PAYMENT:" + payment.orderId()));
~~~

`merge` phát các phần tử của cả hai nguồn trên cùng một luồng, **không** tạo cặp và không bảo đảm thứ tự tổng thể giữa hai nguồn. Nếu cần xử lý theo khóa sau khi hợp nhất, phải triển khai một bước xử lý có trạng thái hoặc dùng công cụ stream processing thích hợp.

`concat` cũng nối dữ liệu thành một luồng nhưng chỉ subscribe nguồn sau khi nguồn trước hoàn tất. Do đó `concat` không phù hợp để kết hợp hai topic thường xuyên phát sự kiện mà **không bao giờ kết thúc**: nguồn thứ hai có thể không được subscribe.

## 4. Bài toán đối soát theo khóa và thời gian

Giả sử mỗi đơn hàng có:

~~~text
OrderCreated(id, totalVnd)
~~~

và mỗi thanh toán có:

~~~text
PaymentConfirmed(orderId, paidVnd)
~~~

Ta muốn phát một `Reconciliation` khi có **một đơn và một thanh toán cùng mã** được quan sát trong **khoảng tương quan tối đa 30 giây**.

Hai điều kiện cần xem xét độc lập:

1. **Khóa:** `order.id()` phải bằng `payment.orderId()`.
2. **Thời gian:** hai sự kiện phải đến trong khoảng cho phép để còn cùng tồn tại trong cửa sổ ghép.

~~~text
Thời gian nhận sự kiện (minh họa)

orders:    O-101 ───────────────── O-102 ───────────>
           |<--------- 30s ------->|

payments:       P(O-101) ───────────────── P(O-102) ─>

Kết quả: O-101 có thể ghép khi cửa sổ còn mở.
         O-102 chỉ ghép nếu thanh toán xuất hiện kịp thời.
~~~

Trong Reactor, `Flux.join(...)` tạo cặp khi các **cửa sổ hoạt động của hai phần tử chồng lấn**. Cửa sổ được đóng bằng một publisher do chương trình chỉ định. Nếu dùng `Mono.delay(Duration.ofSeconds(30))`, khoảng thời gian được đo bằng đồng hồ/scheduler khi pipeline thực thi, **không tự suy ra từ timestamp nghiệp vụ trong payload**.

## 5. Ví dụ hoàn chỉnh: hai đầu vào, một luồng kết quả

Ví dụ dùng **Java 17+** với `record`, Spring Cloud Function và Project Reactor. Các kiểu dữ liệu được khai báo ngay trong lớp cấu hình để có thể chạy riêng trong một ứng dụng Spring Boot đã cấu hình dependency phù hợp.

~~~java
import java.time.Duration;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.function.Tuple2;

@Configuration
public class ReconcileConfiguration {

    public record OrderCreated(String id, long totalVnd) {}

    public record PaymentConfirmed(String orderId, long paidVnd) {}

    public record Reconciliation(
            String orderId,
            long totalVnd,
            long paidVnd,
            boolean amountMatches) {}

    private record Candidate(
            OrderCreated order,
            PaymentConfirmed payment) {}

    @Bean
    public Function<
            Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
            Flux<Reconciliation>> reconcileOrders() {

        return sources -> {
            Flux<OrderCreated> orders = sources.getT1();
            Flux<PaymentConfirmed> payments = sources.getT2();

            return orders
                    .join(
                            payments,
                            // Thời gian giữ mỗi đơn hàng để chờ thanh toán.
                            order -> Mono.delay(Duration.ofSeconds(30)),
                            // Thời gian giữ mỗi thanh toán để chờ đơn hàng.
                            payment -> Mono.delay(Duration.ofSeconds(30)),
                            Candidate::new)
                    // join ghép mọi cặp có cửa sổ chồng lấn;
                    // chỉ giữ cặp cùng khóa nghiệp vụ.
                    .filter(candidate -> candidate.order().id()
                            .equals(candidate.payment().orderId()))
                    .map(candidate -> {
                        OrderCreated order = candidate.order();
                        PaymentConfirmed payment = candidate.payment();

                        return new Reconciliation(
                                order.id(),
                                order.totalVnd(),
                                payment.paidVnd(),
                                order.totalVnd() == payment.paidVnd());
                    });
        };
    }
}
~~~

**Giải thích:**

1. `sources.getT1()` là luồng tạo đơn hàng, `sources.getT2()` là luồng thanh toán.
2. `join` quan sát cả hai nguồn và tạo các cặp ứng viên nếu cửa sổ của chúng chồng lấn.
3. `Candidate::new` giữ tham chiếu đến một đơn và một thanh toán.
4. `filter` kiểm tra **cùng `orderId`**, loại những cặp chỉ trùng thời gian nhưng khác mã.
5. `map` tạo kết quả, phân biệt **đã tìm được cặp** với **số tiền có khớp hay không**.

Ví dụ đầu vào:

| Nguồn | Thông điệp | Tổng tiền |
| --- | --- | ---: |
| Đơn hàng | `OrderCreated("O-101", 500000)` | 500.000 |
| Đơn hàng | `OrderCreated("O-102", 900000)` | 900.000 |
| Thanh toán | `PaymentConfirmed("O-102", 900000)` | 900.000 |
| Thanh toán | `PaymentConfirmed("O-101", 450000)` | 450.000 |

Nếu các sự kiện đến trong các cửa sổ chồng lấn:

- Kết quả `O-101`: `amountMatches = false`.
- Kết quả `O-102`: `amountMatches = true`.

Dù thanh toán `O-102` đến **trước** thanh toán `O-101`, hai bản ghi vẫn được đối chiếu theo **mã nghiệp vụ**, không theo vị trí trong từng nguồn.

### Giới hạn của ví dụ

Đây là **mô hình học tập về kết hợp hai luồng trong bộ nhớ**:

- Cửa sổ dùng `Mono.delay` đo thời gian **khi xử lý**, không phải *event time* trích từ trường thời gian của dữ liệu.
- `join` có thể tạo **nhiều cặp** nếu nhiều sự kiện cùng khóa xuất hiện trong các cửa sổ chồng lấn (ví dụ thanh toán bị gửi lại). Việc `filter` theo khóa không tự loại bản ghi trùng.
- `join` trước hết xét các cặp có cửa sổ chồng lấn, sau đó mới lọc theo khóa; khi lưu lượng và số bản ghi đang giữ cao, số cặp ứng viên và chi phí tính toán có thể tăng đáng kể.
- Không có kết quả với đơn hàng chưa nhận thanh toán hoặc nhận quá muộn: việc **không phát kết quả** khác với việc chủ động phát kết quả `TIMEOUT`.
- Trạng thái cửa sổ nằm trong tiến trình. Khởi động lại ứng dụng, hủy subscription hoặc lỗi pipeline có thể làm mất tương quan đang chờ.

Trong sản phẩm thật, cần quy định chính sách timeout, dữ liệu đến muộn, idempotency, độ bền trạng thái và trách nhiệm bù trừ. Khi cần bảo đảm chặt chẽ, có thể dùng bộ xử lý luồng có **state store, window và cơ chế khôi phục**, hoặc lưu trạng thái theo `orderId` trong cơ sở dữ liệu cùng các quy tắc cập nhật nhất quán.

## 6. Ánh xạ hai cổng vào với Spring Cloud Stream

Spring Cloud Stream là một adapter phổ biến để nối reactive function với hệ thống messaging. Với bean `reconcileOrders`, tên binding mặc định là:

| Binding | Nguồn hoặc đích | Kiểu dữ liệu logic |
| --- | --- | --- |
| `reconcileOrders-in-0` | `orders.created` | `OrderCreated` |
| `reconcileOrders-in-1` | `payments.confirmed` | `PaymentConfirmed` |
| `reconcileOrders-out-0` | `orders.reconciled` | `Reconciliation` |

Cấu hình `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: reconcileOrders
    stream:
      bindings:
        reconcileOrders-in-0:
          destination: orders.created
          content-type: application/json
        reconcileOrders-in-1:
          destination: payments.confirmed
          content-type: application/json
        reconcileOrders-out-0:
          destination: orders.reconciled
          content-type: application/json
~~~

**Cách đọc tên binding:** `-in-0` ứng với `getT1()`, `-in-1` ứng với `getT2()`, `-out-0` là luồng `Flux<Reconciliation>` trả về. Tên bean trong `definition` phải khớp với bean đã đăng ký.

Cấu hình này cần dependency **Spring Cloud Stream** và binder tương ứng (Kafka, RabbitMQ hoặc hệ thống hỗ trợ khác), bên cạnh Spring Cloud Function/Reactor. Bean `Function` không tự tạo broker hoặc topic. Tùy binder, cần thiết lập kết nối, serializer/content type, quyền truy cập và cơ chế xử lý lỗi theo môi trường triển khai.

### Kiểu thông điệp và metadata

Mỗi cổng có kiểu payload riêng nên khâu chuyển đổi JSON phải tạo được đúng kiểu Java tương ứng. Chẳng hạn, một JSON gửi vào `reconcileOrders-in-1` cần các trường phù hợp với `PaymentConfirmed`, không phải cấu trúc `OrderCreated`.

Nếu cần các header như `correlationId`, thời điểm nguồn tạo sự kiện hoặc trace ID, hãy thiết kế rõ cách giữ chúng khi hàm chuyển đổi đầu vào thành kết quả. Header của thông điệp đầu vào **không mặc nhiên** được giữ nguyên trong mọi đầu ra của hàm; có thể dùng `Message<T>` và thao tác sao chép/chọn lọc header theo yêu cầu.

## 7. Kiểm thử đồng bộ dữ liệu và thứ tự không đồng nhất

Vì nghiệp vụ nằm trong functional bean, ta có thể kiểm thử logic **không cần khởi tạo broker**. Ví dụ với JUnit 5 và `reactor-test`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Comparator;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.util.function.Tuples;

class ReconcileConfigurationTest {

    @Test
    void matchesByOrderIdEvenWhenPaymentsArriveInReverseOrder() {
        var config = new ReconcileConfiguration();

        var orders = Flux.just(
                new ReconcileConfiguration.OrderCreated("O-101", 500_000L),
                new ReconcileConfiguration.OrderCreated("O-102", 900_000L));

        var payments = Flux.just(
                new ReconcileConfiguration.PaymentConfirmed("O-102", 900_000L),
                new ReconcileConfiguration.PaymentConfirmed("O-101", 450_000L));

        var result = config.reconcileOrders()
                .apply(Tuples.of(orders, payments))
                // Ví dụ có đúng hai cặp hợp lệ: kết thúc ngay sau hai kết quả.
                .take(2)
                .sort(Comparator.comparing(
                        ReconcileConfiguration.Reconciliation::orderId));

        StepVerifier.create(result)
                .expectNext(
                        new ReconcileConfiguration.Reconciliation(
                                "O-101", 500_000L, 450_000L, false),
                        new ReconcileConfiguration.Reconciliation(
                                "O-102", 900_000L, 900_000L, true))
                .verifyComplete();
    }
}
~~~

`take(2)` được dùng để kiểm tra **hai cặp mong đợi trên nguồn hữu hạn** và hủy pipeline sau khi đủ hai kết quả, tránh phải chờ các cửa sổ 30 giây kết thúc. `sort` giúp kiểm tra kết quả không phụ thuộc thứ tự các cặp mà `join` phát ra; `join` không cam kết thứ tự khi nhiều cặp chồng lấn.

Trong bộ kiểm thử đầy đủ, cần bổ sung các trường hợp sau:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Thanh toán đến trước đơn | Vẫn ghép được nếu còn nằm trong cửa sổ |
| Hai nguồn khác tốc độ | Pipeline không giả định phần tử thứ `i` của hai nguồn là cùng giao dịch |
| Thanh toán đến sau khi cửa sổ đóng | Không ghép; cơ chế timeout/bù trừ riêng hoạt động theo thiết kế |
| Thanh toán hoặc đơn hàng bị lặp | Kết quả không bị ghi nhận trùng nhờ chính sách idempotency |
| Sai hoặc thiếu `orderId` | Không có kết quả đối soát hợp lệ; có chính sách ghi nhận lỗi |
| Một nguồn ngừng hoặc phát lỗi | Xác định cách xử lý chờ, retry, hủy hoặc khôi phục subscription |
| Nhiều mã đơn chồng lấn | Chỉ ghép cặp cùng mã, không có cross-match |

Đối với các trường hợp phụ thuộc vào thời gian, hãy dùng **virtual time** của Reactor trong kiểm thử và thiết kế thời điểm phát sự kiện rõ ràng. Tránh kiểm thử bằng `Thread.sleep(...)` vì chậm và dễ sai lệch.

## 8. Đồng bộ theo thời gian xử lý và theo thời gian sự kiện

Hai cách hiểu thời gian dẫn đến hành vi rất khác:

**Processing time (thời gian xử lý):** thời điểm ứng dụng nhận hoặc thực thi operator. `Mono.delay(Duration.ofSeconds(30))` trong ví dụ sử dụng loại thời gian này. Nếu một payment được tạo lúc 10:00 nhưng đến ứng dụng lúc 10:05, cửa sổ vẫn tính từ thời điểm pipeline quan sát sự kiện.

**Event time (thời gian sự kiện):** thời điểm nghiệp vụ được ghi vào payload hoặc metadata ở nguồn phát. Nếu hệ thống phải ghép các giao dịch có timestamp nghiệp vụ cách nhau tối đa 30 giây, cần so sánh timestamp và xử lý *out-of-order*, *watermark*, giới hạn trễ, cùng các chính sách cửa sổ.

~~~text
Nguồn A tạo O-101 lúc 10:00:00 ──────> ứng dụng nhận lúc 10:00:01
Nguồn B tạo P-101 lúc 10:00:20 ──────> ứng dụng nhận lúc 10:05:00

Chênh lệch event time:      20 giây
Chênh lệch processing time: gần 5 phút
~~~

Ví dụ này có thể được coi là “cùng cửa sổ 30 giây” theo event time, nhưng **không** nằm trong cửa sổ xử lý 30 giây của `join` dùng `Mono.delay`. Reactor `join` không tự tạo watermark hoặc state store bền vững. Nếu yêu cầu là xử lý event time và dữ liệu đến muộn trên topic chạy liên tục, hãy xem xét cơ chế windowed join trong Kafka Streams/stream processor phù hợp, hoặc xây dựng quy tắc lưu trạng thái có thời hạn theo khóa trong cơ sở dữ liệu.

## 9. Các giới hạn vận hành khi ghép nhiều luồng

### 9.1. Trạng thái chờ và giới hạn bộ nhớ

Mỗi sự kiện có thể còn nằm trong cửa sổ trong một thời gian. Với tốc độ sự kiện lớn, giữ dữ liệu để chờ cặp tương ứng sẽ tiêu thụ bộ nhớ. Cần quyết định:

- Cửa sổ tối đa bao lâu và số bản ghi có thể đồng thời chờ?
- Cần giữ bao nhiêu bản ghi mỗi khóa?
- Sau timeout, dữ liệu bị loại bỏ, được gửi vào luồng lỗi hay lưu để điều tra?
- Khi tốc độ nguồn tăng đột biến, hệ thống giới hạn bộ nhớ và áp dụng backpressure ra sao?

Không dùng `collectList()`, `cache()` không giới hạn hoặc một `Map` lưu mọi sự kiện mãi mãi cho một stream liên tục. Những cách này có thể tăng bộ nhớ vô hạn nếu không quản lý vòng đời và TTL.

### 9.2. Lặp thông điệp và idempotency

Nhiều hệ thống messaging hỗ trợ mô hình giao nhận **ít nhất một lần** (*at least once*), vì vậy cùng thông điệp có thể được gửi lại. Với hai nguồn, việc gửi lại có thể khiến một đơn ghép với nhiều payment hoặc ngược lại. Nên dùng event ID/giao dịch ID và chính sách deduplication/unique constraint tại nơi ghi nhận kết quả; không coi `filter` theo `orderId` là đủ.

### 9.3. Lỗi ở một nhánh và vòng đời subscription

`join` subscribe cả hai nguồn để quan sát sự kiện đồng thời. Một lỗi không được xử lý từ một nguồn có thể kết thúc cả pipeline; cần quyết định chiến lược retry hoặc xử lý lỗi theo adapter/binder và logic Reactor. Với reactive function, xử lý lỗi xảy ra trong chuỗi publisher, có thể không giống cơ chế retry theo từng invocation của một hàm imperative.

### 9.4. Thứ tự, backpressure và scaling

Không giả định có **thứ tự toàn cục** giữa các partition, topic hoặc dịch vụ phát thông điệp. Nếu scale thành nhiều instance, hai sự kiện cùng khóa có thể đến **hai instance khác nhau**, làm phép ghép trong bộ nhớ không tìm thấy cặp. Thiết kế partition key/affinity hoặc lưu trạng thái chia sẻ/bền vững là một phần của giải pháp.

Backpressure giúp các subscriber điều tiết tốc độ trong phạm vi pipeline reactive nhưng không tự giải quyết lưu trữ bền vững, phân tán trạng thái hay bảo đảm không mất thông điệp khi broker/instance sự cố.

## 10. Cách chọn giải pháp theo yêu cầu nghiệp vụ

| Yêu cầu | Cách tiếp cận tham khảo |
| --- | --- |
| Gộp nhiều sự kiện thành một feed, không cần ghép cặp | `merge` |
| Nối hai nguồn hữu hạn, giữ thứ tự nguồn trước rồi đến nguồn sau | `concat` |
| Ghép từng phần tử theo vị trí khi hai nguồn đã căn chỉnh | `zip` |
| Theo dõi kết quả từ các giá trị mới nhất của nhiều nguồn | `combineLatest` |
| Ghép sự kiện có cửa sổ thời gian chồng lấn | `join`, kết hợp kiểm tra khóa nếu cần |
| Ghép theo `orderId` có timeout, retry, duplicate, dữ liệu trễ và yêu cầu khôi phục trạng thái | Stream processor/state store hoặc database có chiến lược đối soát rõ ràng |

Với Spring Cloud Function, lựa chọn trên nằm trong **phần thân hàm**; chữ ký `Function<Tuple2<Flux<A>, Flux<B>>, Flux<R>>` cho phép giữ hợp đồng **2 đầu vào → 1 đầu ra**. `FunctionCatalog` và adapter hỗ trợ cách đăng ký, tìm hàm, chuyển đổi thông điệp và kết nối các nguồn. Composition qua ký hiệu `|` là **ghép hàm tuần tự**, không phải cơ chế tự động đồng bộ hai nguồn độc lập.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Hai topic đơn hàng và thanh toán phát đúng số lượng phần tử nhưng có thể đảo thứ tự. Có nên dùng `Flux.zip` để đối soát không?

**Trả lời:** Không. `zip` ghép theo vị trí, không kiểm tra khóa `orderId`. Cần cách ghép theo khóa, có chính sách thời gian và dữ liệu đến muộn.

**Câu 2.** Hàm `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` có bao nhiêu input binding trong Spring Cloud Stream, nếu tên bean là `combineEvents`?

**Trả lời:** Hai input binding: `combineEvents-in-0` và `combineEvents-in-1`. Có một output binding: `combineEvents-out-0`.

**Câu 3.** Vì sao `Flux.combineLatest` không phù hợp để ghép từng giao dịch thanh toán với đơn hàng?

**Trả lời:** Nó lấy giá trị mới nhất từ mỗi nguồn, có thể dùng một giá trị nhiều lần và không biết khóa nghiệp vụ. Hai giá trị mới nhất chưa chắc thuộc cùng giao dịch.

**Câu 4.** Vì sao kết hợp bằng `join` + `Mono.delay(30 giây)` chưa đáp ứng yêu cầu đối soát giao dịch được tạo cách nhau tối đa 30 giây theo timestamp trong payload?

**Trả lời:** Cửa sổ của ví dụ đo **thời gian pipeline xử lý**, không đo timestamp của sự kiện. Dữ liệu phát trễ hoặc đến sai thứ tự cần cơ chế event-time, watermark hoặc trạng thái chờ theo khóa.

**Câu 5.** Nếu thanh toán xuất hiện nhưng đơn hàng chưa đến cho tới sau khi cửa sổ hết hạn, liệu hàm trên có tự phát `TIMEOUT`?

**Trả lời:** Không. Hàm chỉ phát `Reconciliation` cho những cặp thỏa điều kiện; phát kết quả timeout hay cảnh báo thiếu sự kiện cần được thiết kế riêng.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model, Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Functional binding và multiple inputs/outputs](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Project Reactor — Flux API: zip, merge, combineLatest và join](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Reactive operators: Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html)
