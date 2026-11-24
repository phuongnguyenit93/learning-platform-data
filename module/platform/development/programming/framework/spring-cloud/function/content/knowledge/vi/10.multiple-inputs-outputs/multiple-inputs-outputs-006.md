# Thông tin kiểu và chỉ số từng đầu vào đầu ra

## 1. Bài toán: biết đúng cổng nào nhận và phát kiểu dữ liệu nào

Trong **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), các bean `Supplier`, `Function` và `Consumer` biểu diễn logic nghiệp vụ có thể tái sử dụng mà không phụ thuộc vào giao thức gọi. `FunctionCatalog` cho phép tra cứu hàm, hỗ trợ chuẩn hóa chữ ký, composition và chuyển đổi thông điệp. Các adapter phù hợp sẽ kết nối hàm với HTTP, hệ thống sự kiện hoặc nền tảng serverless.

Trong chương **Nhiều đầu vào/ra**, một hàm có thể nhận hai luồng độc lập và phát hai luồng kết quả. Khi đó, cần trả lời **hai câu hỏi tách biệt**:

1. **Chỉ số (index):** cổng đầu vào/đầu ra đang xét là cổng thứ mấy, và nó tương ứng với thành phần nào của tuple?
2. **Thông tin kiểu (type information):** các phần tử đi qua cổng đó mang kiểu Java nào, và adapter nên chuyển đổi payload ra sao?

Giả sử một dịch vụ nhận sự kiện tạo đơn hàng và xác nhận thanh toán, rồi phát hai dòng kết quả riêng:

~~~text
orders.created ──> input 0 ──┐
                            │
                            ├── mapChannels ──> output 0 ──> orders.indexed
                            │
payments.confirmed -> input 1 ┘          └─────> output 1 ──> payments.indexed

input 0: OrderCreated            output 0: OrderIndex
input 1: PaymentConfirmed        output 1: PaymentIndex
~~~

Một cấu hình sai chỉ số có thể khiến JSON thanh toán được đưa vào cổng chờ `OrderCreated`. Một chữ ký khai báo kiểu không chính xác có thể làm framework không xác định được cách chuyển đổi dữ liệu. Vì vậy, **thứ tự cổng và kiểu payload là một phần của hợp đồng tích hợp**.

## 2. Hai hệ đánh số cần phân biệt

### 2.1. Tên binding dùng chỉ số bắt đầu từ 0

Trong **Spring Cloud Stream** với mô hình functional binding, tên mặc định có quy tắc:

~~~text
<functionName>-in-<index>
<functionName>-out-<index>
~~~

Trong đó:

- `functionName` là tên hàm/bean được bind, ví dụ `mapChannels`.
- `in` hoặc `out` xác định chiều dữ liệu.
- `index` đánh số **từ 0** riêng cho các cổng đầu vào và riêng cho các cổng đầu ra.

Ví dụ:

| Tên binding | Ý nghĩa |
| --- | --- |
| `mapChannels-in-0` | Cổng đầu vào thứ nhất |
| `mapChannels-in-1` | Cổng đầu vào thứ hai |
| `mapChannels-out-0` | Cổng đầu ra thứ nhất |
| `mapChannels-out-1` | Cổng đầu ra thứ hai |

Hàm thông thường chỉ có một đầu vào và một đầu ra vẫn dùng hậu tố `-in-0`, `-out-0`. Không phải cứ xuất hiện hậu tố `-0` là hàm có nhiều cổng. Ngược lại, **`-out-1` không phải output đầu tiên**, mà là output thứ **hai**.

### 2.2. Reactor Tuple dùng tên accessor từ T1

Project Reactor cung cấp `Tuple2<A, B>`, `Tuple3<A, B, C>`... trong package `reactor.util.function`. Các phương thức truy cập là `getT1()`, `getT2()`, `getT3()`..., tức **bắt đầu từ 1**.

Khi mỗi thành phần tuple là một `Flux` trong hàm reactive nhiều cổng, mối quan hệ là:

| Vị trí trong tuple | Phương thức Reactor | Index của binding | Binding ví dụ |
| --- | --- | ---: | --- |
| Thành phần thứ nhất | `getT1()` | 0 | `mapChannels-in-0` hoặc `mapChannels-out-0` |
| Thành phần thứ hai | `getT2()` | 1 | `mapChannels-in-1` hoặc `mapChannels-out-1` |
| Thành phần thứ ba | `getT3()` | 2 | `example-in-2` hoặc `example-out-2` |

**Quy tắc nhớ:** `getT(n)` tương ứng binding index `n - 1`; đếm theo đúng thứ tự phần tử khai báo trong `TupleN`. Không có accessor `getT0()`.

~~~java
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

Tuple2<Flux<String>, Flux<Integer>> sources = Tuples.of(
        Flux.just("ORDER-101"),   // getT1() -> input index 0
        Flux.just(100_000));      // getT2() -> input index 1

Flux<String> first = sources.getT1();
Flux<Integer> second = sources.getT2();
~~~

Tên `orders`, `payments`, `first` hay `second` trong code giúp con người đọc; framework xác định vị trí cổng dựa vào **cấu trúc kiểu và thứ tự thành phần**. Nếu thay đổi thứ tự trong tuple, ý nghĩa của binding tương ứng cũng thay đổi.

> Đừng nhầm index của **binding** với index của **phần tử trong danh sách**, index của **partition broker**, hay các chỉ số được viết trong header. Chúng phục vụ các mục đích khác nhau.

## 3. Thông tin kiểu tồn tại ở những tầng nào?

Xét chữ ký:

~~~java
Function<
    Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
    Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>
>
~~~

Có nhiều lớp kiểu lồng nhau:

| Tầng | Ví dụ | Nó nói lên điều gì? |
| --- | --- | --- |
| Interface hàm | `Function<I, O>` | Có đầu vào và đầu ra |
| Container nhiều cổng | `Tuple2<..., ...>` | Hai thành phần ở mỗi phía |
| Publisher | `Flux<T>` | Mỗi cổng truyền một chuỗi các phần tử `T` |
| Kiểu payload cụ thể | `OrderCreated`, `PaymentConfirmed` | Framework và logic mong chờ dữ liệu có cấu trúc nào |
| Thông điệp (nếu có) | `Message<T>` | Payload `T` đi kèm headers và metadata |

Bằng cách khai báo đầy đủ generic, mỗi cổng có một kiểu riêng. Cùng là input, nhưng input 0 có thể mang `OrderCreated` còn input 1 mang `PaymentConfirmed`; không cần ép tất cả sang `Object`.

### 3.1. Vì sao không dùng Collection hoặc Object[] để biểu diễn các cổng?

~~~java
List<Flux<Object>> sources;             // Không thể hiện rõ kiểu mỗi vị trí.
Object[] outputs;                       // Kích thước và kiểu không rõ ở chữ ký.
Tuple2<Flux<String>, Flux<Long>> ports; // Hai cổng, mỗi cổng có kiểu cụ thể.
~~~

`List<Flux<Object>>` có thể chứa nhiều luồng nhưng thông tin kiểu của phần tử ở từng vị trí bị làm chung thành `Object`. Đặc biệt, kích thước của một danh sách có thể thay đổi ở runtime. `Tuple2<Flux<String>, Flux<Long>>` lại thể hiện được **số lượng cố định và kiểu từng cổng ngay trong chữ ký** — dữ liệu giúp framework hiểu function arity và chọn chuyển đổi payload phù hợp.

Java có *type erasure*, vì thế không thể lấy đầy đủ generic chỉ bằng cách kiểm tra một đối tượng `Flux` đang chạy. Spring thường suy kiểu từ **khai báo method/bean** và metadata của chữ ký hàm. Vì vậy nên giữ generic cụ thể ngay ở kiểu trả về của phương thức `@Bean`, thay vì dùng `Function` kiểu raw hoặc ép tất cả đầu vào thành `Object`.

### 3.2. Số phần tử và số cổng không liên quan trực tiếp

`Flux<OrderCreated>` có thể phát 0, 1 hoặc hàng nghìn bản ghi mà vẫn chỉ là **một cổng**. `Flux<List<OrderCreated>>` cũng là một cổng, nhưng mỗi phần tử phát ra là một danh sách. Ngược lại, `Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>` là hai cổng độc lập dù tại một thời điểm mỗi luồng đang trống.

**Số cổng** do hợp đồng kiểu reactive quyết định; **số message** và **số phần tử payload** do luồng dữ liệu, adapter và nghiệp vụ quyết định.

## 4. Ví dụ hoàn chỉnh: 2 đầu vào có kiểu khác nhau, 2 đầu ra có kiểu khác nhau

Ví dụ sau dùng **Java 17+** (`record`), Spring Cloud Function và Project Reactor. Hai đầu vào đi qua hai nhánh xử lý độc lập: đơn hàng được chuyển thành chỉ mục đơn, còn thanh toán được chuyển thành bản tóm tắt thanh toán.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class MultiPortTypeConfiguration {

    public record OrderCreated(String orderId, long totalVnd) {}

    public record PaymentConfirmed(String orderId, long paidVnd) {}

    public record OrderIndex(String orderId, long totalVnd) {}

    public record PaymentIndex(String orderId, boolean hasPayment) {}

    @Bean
    public Function<
            Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
            Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>
    > mapChannels() {
        return sources -> {
            // getT1() là cổng input index 0: OrderCreated.
            Flux<OrderCreated> orders = sources.getT1();

            // getT2() là cổng input index 1: PaymentConfirmed.
            Flux<PaymentConfirmed> payments = sources.getT2();

            Flux<OrderIndex> orderIndexes =
                    orders.map(order -> new OrderIndex(
                            order.orderId(), order.totalVnd()));

            Flux<PaymentIndex> paymentIndexes =
                    payments.map(payment -> new PaymentIndex(
                            payment.orderId(), payment.paidVnd() > 0));

            // Thành phần thứ nhất -> output 0, thứ hai -> output 1.
            return Tuples.of(orderIndexes, paymentIndexes);
        };
    }
}
~~~

Hãy đọc chữ ký dưới dạng **hợp đồng bốn cổng**:

| Chiều | Index binding | Thành phần Java | Kiểu payload | Ví dụ |
| --- | ---: | --- | --- | --- |
| Input | 0 | `sources.getT1()` | `OrderCreated` | `{"orderId":"O-101","totalVnd":250000}` |
| Input | 1 | `sources.getT2()` | `PaymentConfirmed` | `{"orderId":"O-101","paidVnd":250000}` |
| Output | 0 | `result.getT1()` | `OrderIndex` | `{"orderId":"O-101","totalVnd":250000}` |
| Output | 1 | `result.getT2()` | `PaymentIndex` | `{"orderId":"O-101","hasPayment":true}` |

Ví dụ này **không** thực hiện phép ghép đơn hàng với thanh toán theo khóa. Một message ở input 0 tạo một `OrderIndex`; một message ở input 1 tạo một `PaymentIndex`. Đó là thiết kế nghiệp vụ của ví dụ, **không phải quy tắc rằng input index 0 luôn phải đi tới output index 0**. Một hàm khác hoàn toàn có thể gộp hai đầu vào thành một luồng hoặc phân nhánh từng nguồn sang nhiều đầu ra.

## 5. Ánh xạ kiểu và chỉ số vào Spring Cloud Stream

Với bean `mapChannels`, Spring Cloud Stream theo quy ước mặc định có:

~~~text
                           Java bean: mapChannels
                         ┌──────────────────────────┐
orders.created ─────────►│ mapChannels-in-0          │
OrderCreated              │  sources.getT1()         │
                         │                          │
payments.confirmed ─────►│ mapChannels-in-1          │
PaymentConfirmed          │  sources.getT2()         │
                         │                          │
orders.indexed ◄─────────│ mapChannels-out-0         │
OrderIndex                │  result.getT1()          │
                         │                          │
payments.indexed ◄───────│ mapChannels-out-1         │
PaymentIndex              │  result.getT2()          │
                         └──────────────────────────┘
~~~

Tương ứng, có thể cấu hình `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: mapChannels
    stream:
      bindings:
        mapChannels-in-0:
          destination: orders.created
          content-type: application/json
        mapChannels-in-1:
          destination: payments.confirmed
          content-type: application/json
        mapChannels-out-0:
          destination: orders.indexed
          content-type: application/json
        mapChannels-out-1:
          destination: payments.indexed
          content-type: application/json
~~~

Chữ ký generic cho framework thông tin về **kiểu payload mục tiêu**; `content-type` bổ sung ngữ cảnh về **định dạng dữ liệu trên đường truyền**. Hai input có thể cùng dùng `application/json` nhưng **kiểu POJO phải được xác định riêng**: cổng 0 cần `OrderCreated`, cổng 1 cần `PaymentConfirmed`.

Cần có các dependency phù hợp cho Spring Cloud Function, Spring Cloud Stream, Reactor và **binder** đến messaging system được sử dụng. Khai báo bean hoặc đặt `destination` trong YAML không tự tạo một message broker.

### 5.1. Đổi tên binding có đổi chỉ số của Tuple không?

Spring Cloud Stream hỗ trợ khai báo tên binding dễ đọc thông qua `spring.cloud.stream.function.bindings`. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: mapChannels
    stream:
      function:
        bindings:
          mapChannels-in-0: incomingOrders
          mapChannels-out-0: indexedOrders
      bindings:
        incomingOrders:
          destination: orders.created
        indexedOrders:
          destination: orders.indexed
~~~

Đoạn này chỉ minh họa **hai mapping đã đổi tên**; nếu dùng cho ứng dụng hoàn chỉnh, vẫn phải bổ sung cấu hình cho `mapChannels-in-1` và `mapChannels-out-1` theo nhu cầu.

Việc đổi tên **không** làm `getT1()` chuyển sang thành phần thứ hai. Mapping chỉ ảnh hưởng cách đặt tên/cấu hình binding. Nó có thể khiến cấu hình khó truy vết hơn, vì vậy quy ước tên mặc định thường rõ ràng hơn khi không có yêu cầu đặc biệt.

## 6. Kiểu Java và content type phối hợp như thế nào?

Trong Spring Cloud Function, chuyển đổi đầu vào thường dựa trên **hai nguồn thông tin**:

1. **Target type**: kiểu Java khai báo trong chữ ký hàm, như `OrderCreated` hoặc `PaymentConfirmed`.
2. **Content type**: thông tin định dạng ở message header hoặc cấu hình binding, như `application/json` hay `text/plain`.

Ví dụ, nội dung nhận ở `mapChannels-in-0` là:

~~~json
{"orderId":"O-101","totalVnd":250000}
~~~

Khi payload đến dưới dạng byte hoặc chuỗi JSON, bộ chuyển đổi phù hợp có thể tạo một `OrderCreated` cho input 0. Nếu gửi chuỗi `"O-101"` với `text/plain` đến cổng yêu cầu `OrderCreated`, không thể giả định framework sẽ tự suy ra `totalVnd`; một converter có thể không chuyển đổi được và gây lỗi.

Đặt `content-type: application/json` **không đủ** để xác định một trong nhiều lớp Java tùy ý. Chính kiểu đích trong chữ ký hàm là thông tin thiết yếu; content type chỉ giúp chọn cách giải mã/serialize.

| Tình huống | Cách hiểu |
| --- | --- |
| Input 0: `application/json` + `OrderCreated` | JSON cần tương thích cấu trúc `OrderCreated` |
| Input 1: `application/json` + `PaymentConfirmed` | JSON cần tương thích cấu trúc `PaymentConfirmed` |
| Output 0: `OrderIndex` + `application/json` | Có thể serialize kết quả thành JSON theo converter được cấu hình |
| Output 1: `PaymentIndex` + `application/json` | Serialize một payload khác trên một binding khác |
| Input khai báo raw `Flux<Object>` | Mất thông tin đích cụ thể, chuyển đổi có thể không cho kết quả mong muốn |
| Header hoặc cấu hình `content-type` sai | Chọn converter không phù hợp hoặc lỗi chuyển đổi |

Chi tiết ưu tiên giữa message header, cấu hình binding và cơ chế chuyển đổi có thể phụ thuộc phiên bản Spring Cloud Function/Stream, binder và cách adapter tạo `Message`. Khi lỗi, nên kiểm tra **payload thực tế, content type và chữ ký Java của đúng cổng** thay vì chỉ sửa tên topic.

### 6.1. Message<T> thêm metadata, không tạo thêm input

Hàm có thể muốn đọc header `correlationId` hoặc thông tin truy vết:

~~~java
import org.springframework.messaging.Message;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;

// Hai input binding; mỗi message có payload và headers riêng.
Function<
    Tuple2<
        Flux<Message<OrderCreated>>,
        Flux<Message<PaymentConfirmed>>
    >,
    Flux<String>
> auditMessages;
~~~

Ở đây, input 0 là `Message<OrderCreated>`, input 1 là `Message<PaymentConfirmed>`. Bọc trong `Message<T>` **không** tăng số binding: payload và headers cùng thuộc một message trên một cổng. `auditMessages` là minh họa chữ ký; phần thân hàm cần được triển khai để sử dụng.

Với header cần giữ qua nhiều bước biến đổi, hãy thao tác rõ ràng trên `Message<T>` và xây dựng message đầu ra với header phù hợp. Không giả định mọi header tự động được sao chép qua mọi phép chuyển kiểu hoặc mọi adapter.

### 6.2. Type erasure và khai báo bean

Khi làm việc với generic và lambda:

~~~java
// Nên làm: phương thức @Bean nêu đủ generic ở hai phía.
@Bean
public Function<Flux<String>, Flux<Long>> parseNumbers() {
    return texts -> texts.map(Long::parseLong);
}
~~~

Tránh viết:

~~~java
// Hạn chế: kiểu raw khiến framework không có hợp đồng payload rõ ràng.
@Bean
@SuppressWarnings({"rawtypes", "unchecked"})
public Function rawFunction() {
    return value -> value;
}
~~~

Khi type information bị mất, converter có thể không biết nên tạo `OrderCreated`, `Long` hay một kiểu đích khác. Khai báo tường minh kiểu generic ở public bean method giúp cả trình biên dịch, `FunctionCatalog` và adapter có cơ sở xác định hợp đồng.

## 7. Không suy diễn kiểu hoặc cổng từ tên biến

Các cặp sau có thể có vẻ giống nhau khi đọc lướt:

~~~java
// Một input chứa các cặp dữ liệu.
Function<Flux<Tuple2<OrderCreated, PaymentConfirmed>>, Flux<String>>

// Hai input độc lập.
Function<
    Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>,
    Flux<String>>
~~~

Ở chữ ký đầu, **mỗi phần tử** của một `Flux` là một cặp sự kiện đã được ghép, chỉ có **một input**. Ở chữ ký sau, có **hai input** độc lập; hàm phải tự quyết định dùng `merge`, `zip`, `join` hoặc cơ chế tương quan khác. Chữ ký không tự ghép đơn và thanh toán theo `orderId`.

Tương tự, hai kiểu trả về:

~~~java
Flux<Tuple2<OrderIndex, PaymentIndex>>
Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>
~~~

lần lượt là **một luồng các cặp** và **hai luồng riêng**. Đặt tên biến `firstOutput` hay `secondOutput` không thay đổi số cổng; **cấu trúc generic** mới là yếu tố quyết định.

### 7.1. Khi thêm một input mới

Giả sử ban đầu hàm dùng:

~~~java
Tuple2<Flux<OrderCreated>, Flux<PaymentConfirmed>>
~~~

Sau này hệ thống bổ sung luồng cập nhật kho:

~~~java
Tuple3<
    Flux<OrderCreated>,
    Flux<PaymentConfirmed>,
    Flux<InventoryUpdated>>
~~~

Khi thêm `InventoryUpdated` ở **cuối** tuple, các binding cũ vẫn có chỉ số `0` và `1`, còn input mới là `-in-2`. Nhưng nếu chèn `InventoryUpdated` vào giữa, các cổng sau nó sẽ **đổi chỉ số**. Cần cập nhật đồng bộ chữ ký, cách gọi `getTn()`, cấu hình binding và kiểm thử.

Quy tắc chung: **thứ tự tuple là một phần của cấu hình public** trong ứng dụng dùng Spring Cloud Stream; thay đổi vị trí có thể gây lỗi mapping ngay cả khi code vẫn biên dịch.

## 8. Kiểm thử thứ tự cổng và kiểu kết quả

Unit test sau dùng JUnit 5 và `reactor-test` để kiểm tra hàm `mapChannels` trực tiếp. Nó không cần broker, vì chỉ xác minh logic Java và thứ tự tuple.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuples;

class MultiPortTypeConfigurationTest {

    @Test
    void preservesInputAndOutputTypesByTuplePosition() {
        var configuration = new MultiPortTypeConfiguration();

        var result = configuration.mapChannels().apply(Tuples.of(
                Flux.just(new MultiPortTypeConfiguration.OrderCreated(
                        "O-101", 250_000L)),
                Flux.just(new MultiPortTypeConfiguration.PaymentConfirmed(
                        "O-101", 250_000L))));

        // Lấy dữ liệu của cả hai output độc lập.
        StepVerifier.create(Mono.zip(
                        result.getT1().collectList(),
                        result.getT2().collectList()))
                .assertNext(outputs -> {
                    assertEquals(
                            List.of(new MultiPortTypeConfiguration.OrderIndex(
                                    "O-101", 250_000L)),
                            outputs.getT1());
                    assertEquals(
                            List.of(new MultiPortTypeConfiguration.PaymentIndex(
                                    "O-101", true)),
                            outputs.getT2());
                })
                .verifyComplete();
    }
}
~~~

Test này chứng minh **output tuple thành phần thứ nhất** chứa `OrderIndex` và **thành phần thứ hai** chứa `PaymentIndex`, đồng thời kiểm tra dữ liệu từ hai input được xử lý đúng nhánh. Nó chưa chứng minh topic/queue ngoài hệ thống đã được nối đúng.

Để xác minh cấu hình binding và chuyển đổi payload thật, cần thêm **integration test** với Spring Cloud Stream Test Binder hoặc binder thích hợp:

1. Gửi JSON `OrderCreated` vào destination của `mapChannels-in-0`.
2. Gửi JSON `PaymentConfirmed` vào destination của `mapChannels-in-1`.
3. Đọc kết quả trên destination ứng với `mapChannels-out-0` và `mapChannels-out-1`.
4. Kiểm tra kiểu nội dung, content type, số message, header quan trọng và thông điệp không bị đổi cổng.

`collectList()` phù hợp với nguồn `Flux.just(...)` hữu hạn trong unit test; với luồng message broker không kết thúc, không nên gom tất cả phần tử vào bộ nhớ để chờ hoàn thành.

## 9. Phát hiện lỗi sai chỉ số và sai kiểu

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Dữ liệu thanh toán vào nhánh đơn hàng | `-in-0` / `-in-1` ánh xạ sai destination | Đối chiếu `getT1()` và `getT2()` với bảng binding |
| Output có payload đúng nhưng đến nhầm topic | Thứ tự `Tuples.of(...)` bị đảo | Kiểm tra output 0 ↔ `getT1()`; output 1 ↔ `getT2()` |
| Lỗi deserialization JSON | Payload không khớp POJO đích hoặc content type không phù hợp | Kiểm tra JSON, schema, generic từng input và `content-type` |
| Một cổng không nhận thông điệp | Sai tên binding, destination, binder hoặc group | Kiểm tra `definition`, tên `-in-n` và cấu hình binder |
| Framework xử lý như `Object`/`Map` thay vì POJO mong muốn | Bean khai báo raw/generic quá rộng | Khai báo type cụ thể tại `@Bean` method |
| Lỗi khi thay đổi Tuple2 thành Tuple3 | Đã thêm/chèn thành phần nhưng chưa cập nhật các chỉ số | Kiểm tra đủ `-in-0`, `-in-1`, `-in-2`, accessor và unit test |
| Hai input có cùng `application/json` nhưng kết quả đổi kiểu lạ | Nhầm định dạng dữ liệu với kiểu Java mục tiêu | Dùng đúng generic `OrderCreated`/`PaymentConfirmed` theo từng cổng |

**Điểm cần nhớ về giao thức:** Spring Cloud Function tách logic khỏi cách gọi. Spring Cloud Stream định nghĩa output/input *binding* và cách định tuyến đến topic/queue, trong khi HTTP thường có mô hình request/response. Không nên suy rằng một tuple có hai `Flux` sẽ tự tạo hai HTTP endpoint hoặc hai response. Khả năng triển khai hàm nhiều cổng tùy vào adapter và cấu hình của môi trường.

**Điểm cần nhớ về composition:** ghép `a|b` nối đầu ra của `a` với đầu vào của `b` theo hợp đồng tương thích. Composition có thể làm thay đổi tên binding/kiểu hợp đồng nhìn từ bên ngoài; cần đánh giá trên **hàm được bind sau composition** thay vì suy tên từ từng bean bên trong. Bản thân composition không tự sửa thứ tự các thành phần tuple theo tên biến.

## 10. Bài tập tự kiểm tra

**Câu 1.** Hàm sau có bao nhiêu cổng vào/ra, và input `-in-1` mang kiểu gì?

~~~java
Function<
    Tuple3<Flux<String>, Flux<Long>, Flux<Boolean>>,
    Tuple2<Flux<Integer>, Flux<String>>>
~~~

**Đáp án:** Có **3 đầu vào, 2 đầu ra**. `-in-1` là đầu vào thứ hai, tương ứng `getT2()`, mang payload `Long`. Output `-out-0` mang `Integer`; output `-out-1` mang `String`.

**Câu 2.** Nếu bean `mapChannels` trả `Tuples.of(paymentIndexes, orderIndexes)`, nhưng các output binding vẫn như trong YAML ở trên, điều gì xảy ra?

**Đáp án:** Hai output bị **đảo thứ tự**. Với chữ ký generic trả về vẫn là `Tuple2<Flux<OrderIndex>, Flux<PaymentIndex>>`, đoạn code đó còn **không biên dịch đúng kiểu** (nếu không ép kiểu không an toàn). Nếu sửa chữ ký cho khớp nhưng không sửa binding, dữ liệu sẽ đến sai destination.

**Câu 3.** Hai cổng đều cấu hình `content-type: application/json`. Có thể đưa JSON của `PaymentConfirmed` đến input 0 và tự tin converter sẽ biến nó thành `OrderCreated` không?

**Đáp án:** Không. `application/json` chỉ xác định định dạng; input 0 vẫn yêu cầu cấu trúc `OrderCreated`. JSON phải đáp ứng hợp đồng của kiểu đó; thiếu/sai field có thể gây lỗi hoặc dữ liệu không hợp lệ tùy converter và validation.

**Câu 4.** `Flux<Tuple2<A, B>>` có hai output binding vì `Tuple2` chứa hai thành phần?

**Đáp án:** Không. Đây là **một Flux** phát các cặp `A` và `B`, tức một cổng đầu ra logic. Muốn hai cổng reactive riêng cần một cấu trúc như `Tuple2<Flux<A>, Flux<B>>` và adapter hỗ trợ function arity.

**Câu 5.** Nếu cần giữ header `correlationId` trên các sự kiện đã xử lý, có cần thêm một input binding cho header không?

**Đáp án:** Không. Dùng `Message<T>` để truy cập payload và headers trong cùng một thông điệp, xử lý hoặc sao chép header sang message kết quả khi cần.

## Tài liệu tham khảo

- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Functions with multiple input and output arguments](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function — Programming model và Type conversion](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Project Reactor — Tuple2 API](https://projectreactor.io/docs/core/release/api/reactor/util/function/Tuple2.html)
