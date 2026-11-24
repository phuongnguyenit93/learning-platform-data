# Quy tắc tên `<function>-in-<index>` và `<function>-out-<index>`

Trong mô hình lập trình hàm của Spring Cloud Stream, mỗi hàm `Supplier`, `Function` hoặc `Consumer` có thể được nối với hệ thống nhắn tin thông qua các binding đầu vào và đầu ra. Spring Cloud Stream đặt tên binding theo tên bean hàm và vị trí của cổng dữ liệu. Quy tắc chuẩn có dạng `<function>-in-<index>` cho đầu vào và `<function>-out-<index>` cho đầu ra.

Hiểu đúng quy tắc này giúp cấu hình `destination`, `group`, `content-type`, retry hoặc các thuộc tính riêng của binder vào đúng binding. Tên binding là định danh logic trong ứng dụng; nó không phải tên topic, queue, exchange hay subscription trên broker.

## 1. Cấu trúc tên binding

Tên binding theo mô hình hàm gồm ba phần:

| Phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `<function>` | Tên bean hàm được Spring đăng ký trong application context | `processOrder` |
| `in` hoặc `out` | Hướng dữ liệu so với hàm | `in` là dữ liệu đi vào hàm; `out` là dữ liệu đi ra hàm |
| `<index>` | Chỉ số của cổng đầu vào hoặc đầu ra, bắt đầu từ `0` | `0`, `1`, `2` |

Vì vậy:

- `processOrder-in-0` là cổng đầu vào thứ nhất của hàm `processOrder`.
- `processOrder-out-0` là cổng đầu ra thứ nhất của hàm `processOrder`.
- `processOrder-in-1` là cổng đầu vào thứ hai nếu hàm có nhiều đầu vào được hỗ trợ.
- `processOrder-out-1` là cổng đầu ra thứ hai nếu hàm có nhiều đầu ra được hỗ trợ.

Chỉ số là số thứ tự cổng, đánh số từ 0. Nó không biểu thị số thứ tự message, partition của Kafka, consumer instance hay vị trí của phần tử trong một payload.

Tên `<function>` lấy từ tên bean hàm mà Spring nhận diện. Với khai báo `@Bean` thông thường, đó thường là tên phương thức tạo bean. Nếu bean được đặt tên tường minh, cần dùng tên bean thực tế đó trong `spring.cloud.function.definition` và tên binding tương ứng.

## 2. Tên binding của Supplier, Function và Consumer

Mỗi loại hàm có số lượng hướng dữ liệu khác nhau. Quy tắc tên binding phản ánh chính xác hướng đó.

| Kiểu hàm | Đầu vào | Đầu ra |
| --- | --- | --- |
| `Supplier<T>` | Không có binding đầu vào | `<function>-out-0` |
| `Function<T, R>` | `<function>-in-0` | `<function>-out-0` |
| `Consumer<T>` | `<function>-in-0` | Không có binding đầu ra |

### Supplier: chỉ có đầu ra

`Supplier` tạo dữ liệu và phát dữ liệu ra broker. Ví dụ:

```java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class EventSources {

    @Bean
    public Supplier<String> orderEvents() {
        return () -> "ORDER_CREATED";
    }
}
```

Tên binding đầu ra được tạo theo tên bean:

```text
orderEvents-out-0
```

Không có `orderEvents-in-0`, vì `Supplier` không nhận message từ broker qua tham số đầu vào. Với `Supplier<Flux<T>>`, đầu ra vẫn là cổng `orderEvents-out-0`; việc trả về một luồng nhiều phần tử không tự tạo thêm nhiều binding.

### Function: có đầu vào và đầu ra

`Function` nhận dữ liệu, xử lý rồi trả về kết quả. Ví dụ:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderProcessors {

    @Bean
    public Function<String, String> normalizeOrder() {
        return orderId -> orderId.trim().toUpperCase();
    }
}
```

Hai binding tương ứng là:

```text
normalizeOrder-in-0
normalizeOrder-out-0
```

Message từ destination của binding đầu vào được chuyển tới hàm `normalizeOrder`. Giá trị trả về của hàm được gửi qua binding đầu ra tới destination đã cấu hình.

### Consumer: chỉ có đầu vào

`Consumer` nhận message và thực hiện hành động, không trả về dữ liệu để phát qua binding đầu ra:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderListeners {

    @Bean
    public Consumer<String> recordOrder() {
        return orderId -> System.out.println("Received: " + orderId);
    }
}
```

Tên binding là:

```text
recordOrder-in-0
```

Không có `recordOrder-out-0`. Nếu cần phát một message mới sau khi xử lý, hãy dùng `Function` trả về dữ liệu hoặc một cơ chế gửi message phù hợp với thiết kế ứng dụng.

## 3. Cấu hình binding bằng tên mặc định

Thông thường, nên giữ tên binding mặc định do Spring Cloud Stream tạo ra. Khi đó, cấu hình từng binding nằm dưới `spring.cloud.stream.bindings` với khóa chính là tên binding.

Ví dụ, hàm `normalizeOrder` đọc từ `orders.raw` và phát kết quả tới `orders.normalized`:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizer
          content-type: application/json
          consumer:
            max-attempts: 3
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/json
```

Trong ví dụ này:

- `spring.cloud.function.definition` chọn bean hàm cần kích hoạt.
- `normalizeOrder-in-0` cấu hình cổng nhận dữ liệu của hàm.
- `destination: orders.raw` là tài nguyên đầu vào trên broker.
- `group: order-normalizer` xác định nhóm tiêu thụ cho binding đầu vào; ý nghĩa cụ thể được binder ánh xạ theo broker.
- `normalizeOrder-out-0` cấu hình cổng phát dữ liệu của hàm.
- `destination: orders.normalized` là tài nguyên nhận kết quả.
- `content-type` khai báo định dạng payload để framework thực hiện chuyển đổi.

Tên binding và tên destination có thể khác nhau. Khi đổi destination từ `orders.raw` sang `orders.submitted`, tên binding `normalizeOrder-in-0` vẫn giữ nguyên. Tên binding chỉ thay đổi khi thay đổi tên bean hàm, cấu trúc cổng hoặc quy tắc ánh xạ tên.

## 4. Vì sao index bắt đầu từ 0?

Index đánh số các cổng của cùng một hàm theo thứ tự. Cổng đầu tiên luôn dùng `0`, cổng thứ hai dùng `1` và tiếp tục tăng. Quy tắc này áp dụng riêng cho đầu vào và đầu ra.

Ví dụ về mặt quy ước:

| Cổng | Tên |
| --- | --- |
| Đầu vào thứ nhất | `aggregate-in-0` |
| Đầu vào thứ hai | `aggregate-in-1` |
| Đầu ra thứ nhất | `aggregate-out-0` |
| Đầu ra thứ hai | `aggregate-out-1` |

Một hàm có một đầu vào và hai đầu ra sẽ có một binding `in-0`, cùng hai binding `out-0` và `out-1`. Một hàm có hai đầu vào và một đầu ra sẽ có hai binding `in-0`, `in-1` và một binding `out-0`. Số lượng binding thực tế phụ thuộc chữ ký hàm và kiểu dữ liệu mà phiên bản Spring Cloud Function/Spring Cloud Stream hỗ trợ.

Trong các hàm xử lý luồng nhiều đầu vào hoặc nhiều đầu ra, Spring Cloud Stream có thể dùng các cấu trúc tuple để biểu diễn nhiều cổng. Ví dụ minh họa một hàm nhận hai luồng và phát một luồng:

```java
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JoinFunctions {

    @Bean
    public Function<Tuple2<Flux<String>, Flux<String>>, Flux<String>> mergeEvents() {
        return inputs -> Flux.merge(inputs.getT1(), inputs.getT2());
    }
}
```

Với chữ ký hai đầu vào và một đầu ra này, các cổng có tên theo quy ước:

```text
mergeEvents-in-0
mergeEvents-in-1
mergeEvents-out-0
```

Ví dụ tuple cho thấy index xác định vị trí cổng trong cấu trúc hàm. Cách hỗ trợ kiểu tuple, reactive type và chữ ký nhiều cổng cần được đối chiếu với phiên bản Spring Cloud Stream/Spring Cloud Function của dự án. Không nên tự tăng index chỉ vì message có nhiều trường hoặc một luồng có nhiều phần tử.

## 5. Tên hàm và lựa chọn hàm được kích hoạt

Ứng dụng có thể khai báo nhiều bean hàm, nhưng Spring Cloud Stream cần biết hàm nào được kết nối với binder. Thuộc tính `spring.cloud.function.definition` chọn hàm hoặc biểu thức composition sẽ được kích hoạt.

Ví dụ có hai bean:

```java
@Bean
public Function<String, String> normalizeOrder() {
    return value -> value.trim().toUpperCase();
}

@Bean
public Consumer<String> auditOrder() {
    return value -> System.out.println("Audit: " + value);
}
```

Nếu chỉ chọn `normalizeOrder`, binding của hàm đó là `normalizeOrder-in-0` và `normalizeOrder-out-0`. Nếu chọn `auditOrder`, binding là `auditOrder-in-0`. Bean có trong application context không có nghĩa mọi bean tự động được nối với broker; việc chọn hàm phải rõ ràng.

Khi cần kích hoạt nhiều hàm độc lập, có thể liệt kê các định nghĩa theo cú pháp mà Spring Cloud Function hỗ trợ, thường dùng dấu `;` để phân tách. Mỗi hàm vẫn có tên binding dựa trên tên riêng của nó. Hãy kiểm tra cấu hình definition của phiên bản đang dùng, đặc biệt khi trộn hàm độc lập và hàm composition.

## 6. Tên binding khi kết hợp nhiều hàm

Spring Cloud Function cho phép kết hợp các hàm tương thích thành một pipeline. Ví dụ, `uppercase` chuyển chuỗi thành chữ hoa và `addPrefix` thêm tiền tố. Có thể chọn pipeline bằng:

```yaml
spring:
  cloud:
    function:
      definition: uppercase|addPrefix
```

Với một hàm composition có một đầu vào và một đầu ra, tên binding được tạo theo tên định nghĩa kết hợp:

```text
uppercase|addPrefix-in-0
uppercase|addPrefix-out-0
```

Ví dụ cấu hình đầy đủ:

```yaml
spring:
  cloud:
    function:
      definition: uppercase|addPrefix
    stream:
      bindings:
        "uppercase|addPrefix-in-0":
          destination: orders.raw
        "uppercase|addPrefix-out-0":
          destination: orders.display
```

Khi viết YAML, đặt tên có ký tự `|` trong dấu nháy để thể hiện rõ đó là khóa chuỗi. Nếu pipeline có nhiều đầu vào hoặc đầu ra, index tiếp tục đánh số theo cổng của hàm kết hợp. Các hàm thành phần phải có kiểu đầu ra và đầu vào tương thích để có thể nối với nhau.

Không nhầm tên pipeline với tên destination. `uppercase|addPrefix-in-0` là binding đầu vào của pipeline; `orders.raw` là destination được binding đó sử dụng.

## 7. Đổi tên binding mặc định bằng alias

Spring Cloud Stream cho phép ánh xạ tên binding mặc định sang một tên tùy chỉnh. Cấu hình này hữu ích khi muốn dùng tên ngắn, tên theo quy ước nội bộ hoặc tên ổn định cho một cấu hình bên ngoài.

Ví dụ, ánh xạ binding `normalizeOrder-in-0` sang alias `ordersInput`, và `normalizeOrder-out-0` sang `ordersOutput`:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      function:
        bindings:
          normalizeOrder-in-0: ordersInput
          normalizeOrder-out-0: ordersOutput
```

Sau khi ánh xạ, cấu hình thuộc tính binding dùng alias:

```yaml
spring:
  cloud:
    stream:
      bindings:
        ordersInput:
          destination: orders.raw
          group: order-normalizer
        ordersOutput:
          destination: orders.normalized
```

Tên đầy đủ của thuộc tính ánh xạ là `spring.cloud.stream.function.bindings`. Khi dùng alias, mọi cấu hình thuộc tính binding cần tham chiếu nhất quán tên alias tương ứng. Điều này có thể khiến người đọc phải lần ngược từ alias về tên hàm, vì vậy nên giữ tên mặc định nếu không có nhu cầu cụ thể.

Alias chỉ thay đổi tên binding được dùng trong cấu hình. Nó không đổi tên bean hàm và cũng không tự đổi destination trên broker. Việc đổi tên topic, exchange hay queue vẫn được thực hiện bằng thuộc tính `destination` hoặc cấu hình tài nguyên broker tương ứng.

## 8. Phân biệt binding name với các tên khác

Trong một cấu hình Spring Cloud Stream có nhiều loại tên cùng xuất hiện. Cần xác định đúng vai trò để tránh đặt nhầm thuộc tính:

| Giá trị | Ví dụ | Vai trò |
| --- | --- | --- |
| Tên bean hàm | `normalizeOrder` | Chọn hàm trong application context |
| Binding đầu vào | `normalizeOrder-in-0` | Định danh cổng nhận dữ liệu của hàm |
| Binding đầu ra | `normalizeOrder-out-0` | Định danh cổng phát dữ liệu của hàm |
| Destination | `orders.raw` | Tên tài nguyên logic trên broker |
| Consumer group | `order-normalizer` | Nhóm consumer/subscription theo cách binder ánh xạ |
| Binder type | `kafka` | Loại implementation kết nối với broker |
| Binder instance | `kafka-east` | Cấu hình kết nối cụ thể được binding tham chiếu |

Ví dụ, `normalizeOrder-in-0` có thể đọc từ destination `orders.raw` bằng binder instance `kafka-east` và consumer group `order-normalizer`. Mỗi giá trị phục vụ một mục đích riêng. Không dùng tên group làm tên binding hoặc tên destination nếu không có lý do kiến trúc rõ ràng.

## 9. Cách tìm và xử lý lỗi tên binding

Nếu ứng dụng không tạo được binding hoặc không nhận message, hãy kiểm tra lần lượt:

1. **Tên bean:** bean hàm có được đăng ký không? Tên trong `spring.cloud.function.definition` có khớp với tên bean không?
2. **Loại hàm:** hàm là `Supplier`, `Function` hay `Consumer`? Hướng binding có đúng với kiểu hàm không?
3. **Tên mặc định:** khóa cấu hình có dùng đúng `<function>-in-<index>` hoặc `<function>-out-<index>` không? Index có bắt đầu từ 0 không?
4. **Số cổng:** chữ ký hàm có thực sự cung cấp nhiều đầu vào hoặc đầu ra không? Các tuple hoặc kiểu dữ liệu có được phiên bản đang dùng hỗ trợ không?
5. **Composition:** nếu dùng `|`, định nghĩa pipeline có đúng thứ tự và các kiểu hàm có tương thích không? Khóa YAML có được đặt trong dấu nháy khi cần không?
6. **Alias:** nếu đổi tên binding, cấu hình ánh xạ có đúng và các thuộc tính binding có dùng alias sau ánh xạ không?
7. **Destination và binder:** binding có trỏ tới đúng destination, binder instance và thông tin kết nối không?

Khi cần quan sát cấu hình hiệu lực, có thể bật log chi tiết trong môi trường phát triển:

```yaml
logging:
  level:
    org.springframework.cloud.stream: DEBUG
    org.springframework.cloud.function: DEBUG
```

Đọc log để tìm tên binding được tạo, quá trình chọn binder và lỗi bind destination. Với ứng dụng dùng Actuator, endpoint `bindings` có thể cung cấp trạng thái binding nếu endpoint này được bật và expose phù hợp. Không expose thông tin quản trị ra môi trường công khai nếu chưa có kiểm soát truy cập.

## 10. Thực hành: xác định tên binding trước khi cấu hình broker

Với mỗi hàm, có thể lập bảng cổng dữ liệu trước khi viết `application.yml`:

| Bean hàm | Loại | Binding đầu vào | Binding đầu ra |
| --- | --- | --- | --- |
| `orderEvents` | `Supplier<String>` | — | `orderEvents-out-0` |
| `normalizeOrder` | `Function<String, String>` | `normalizeOrder-in-0` | `normalizeOrder-out-0` |
| `recordOrder` | `Consumer<String>` | `recordOrder-in-0` | — |
| `mergeEvents` | Hàm hai đầu vào, một đầu ra | `mergeEvents-in-0`, `mergeEvents-in-1` | `mergeEvents-out-0` |

Sau khi xác định tên binding, mới gắn từng binding với destination, group, content type và binder phù hợp. Cách làm này giúp phát hiện sớm lỗi sai tên hoặc sai hướng trước khi điều tra kết nối broker.

## Kết luận

Trong mô hình hàm của Spring Cloud Stream, tên binding được tạo từ tên bean hàm, hướng dữ liệu và index bắt đầu từ 0. `Supplier` có binding đầu ra, `Consumer` có binding đầu vào, còn `Function` thường có cả hai. Hàm nhiều cổng và hàm composition mở rộng tên theo cùng quy tắc. Giữ tên mặc định giúp cấu hình dễ đọc; nếu dùng alias, cần ánh xạ và tham chiếu alias nhất quán. Khi phân biệt binding name với destination, group và binder, việc cấu hình cũng như chẩn đoán luồng sự kiện sẽ rõ ràng hơn.
