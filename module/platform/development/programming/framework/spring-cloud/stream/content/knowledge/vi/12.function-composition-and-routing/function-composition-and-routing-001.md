# Ghép hàm bằng toán tử | và khai báo nhiều hàm bằng dấu ;

Spring Cloud Stream cho phép ứng dụng khai báo các bean hàm theo mô hình Supplier, Function và Consumer. Khi một ứng dụng có nhiều bước xử lý, ta có thể ghép các Function thành một pipeline bằng toán tử |. Khi cần kích hoạt nhiều hàm độc lập trong cùng ứng dụng, ta liệt kê tên các hàm bằng dấu ; trong thuộc tính spring.cloud.function.definition.

Hai cách khai báo này giải quyết hai nhu cầu khác nhau. Ghép hàm tạo thành một chuỗi xử lý logic: đầu ra của hàm trước trở thành đầu vào của hàm sau. Liệt kê bằng dấu chấm phẩy đăng ký nhiều hàm riêng biệt; mỗi hàm có thể có binding, destination và consumer group riêng. Hiểu rõ khác biệt này giúp tránh tạo thêm topic không cần thiết hoặc vô tình biến các tác vụ độc lập thành một chuỗi xử lý.

## 1. Từ các bean hàm đến function definition

Spring Cloud Function nhận diện các bean có kiểu Supplier<T>, Function<T, R> hoặc Consumer<T>. Spring Cloud Stream dùng các bean này làm điểm vào và điểm ra của luồng thông điệp:

- Supplier tạo dữ liệu và có đầu ra.
- Function nhận dữ liệu, biến đổi dữ liệu và trả về kết quả.
- Consumer nhận dữ liệu và kết thúc luồng xử lý, không có đầu ra.

Ví dụ một Function độc lập:

~~~java
import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<String, String> normalizeOrder() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Khi chỉ có một bean hàm phù hợp, framework có thể tự phát hiện hàm đó. Khi ứng dụng có nhiều bean hàm, nên khai báo rõ hàm nào cần được kích hoạt bằng:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
~~~

Thuộc tính definition là danh sách tên bean hàm hoặc biểu thức ghép hàm. Spring Cloud Stream dựa vào định nghĩa này để tạo các binding tương ứng. Tên bean phải khớp với tên trong cấu hình; tên method có phân biệt chữ hoa và chữ thường.

## 2. Ghép Function bằng toán tử |

Toán tử | biểu diễn phép ghép hàm theo thứ tự từ trái sang phải. Với định nghĩa parseOrder|validateOrder|createEvent, dữ liệu đi qua parseOrder trước, kết quả được chuyển vào validateOrder, sau đó kết quả của bước xác thực được đưa vào createEvent.

~~~mermaid
flowchart LR
    I["Input binding"] --> A["parseOrder"]
    A -->|"OrderDraft"| B["validateOrder"]
    B -->|"ValidatedOrder"| C["createEvent"]
    C --> O["Output binding"]
~~~

Các hàm trung gian được gọi trong cùng pipeline của ứng dụng. Spring Cloud Stream chỉ cần binding ở đầu vào của hàm ghép và đầu ra của hàm ghép. Mỗi dấu | không tự tạo một topic hoặc queue trung gian.

### 2.1. Điều kiện tương thích kiểu dữ liệu

Kiểu đầu ra của một bước phải tương thích với kiểu đầu vào của bước tiếp theo. Nếu hàm thứ nhất có kiểu Function<A, B>, hàm thứ hai phải nhận được B hoặc một kiểu mà B có thể chuyển đổi sang.

Ví dụ:

~~~java
public record OrderDraft(String orderId, String customerId, int quantity) {}

public record ValidatedOrder(
    String orderId,
    String customerId,
    int quantity
) {}

public record OrderAccepted(
    String orderId,
    String customerId,
    int quantity,
    String status
) {}
~~~

Khai báo ba bước xử lý:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderPipeline {

    @Bean
    Function<String, OrderDraft> parseOrder() {
        return raw -> {
            String[] fields = raw.split(",");
            return new OrderDraft(
                fields[0].trim(),
                fields[1].trim(),
                Integer.parseInt(fields[2].trim())
            );
        };
    }

    @Bean
    Function<OrderDraft, ValidatedOrder> validateOrder() {
        return order -> {
            if (order.orderId().isBlank()
                    || order.customerId().isBlank()
                    || order.quantity() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            return new ValidatedOrder(
                order.orderId(),
                order.customerId(),
                order.quantity()
            );
        };
    }

    @Bean
    Function<ValidatedOrder, OrderAccepted> createEvent() {
        return order -> new OrderAccepted(
            order.orderId(),
            order.customerId(),
            order.quantity(),
            "ACCEPTED"
        );
    }
}
~~~

Ba kiểu liên kết với nhau:

| Bước | Kiểu đầu vào | Kiểu đầu ra |
|---|---|---|
| parseOrder | String | OrderDraft |
| validateOrder | OrderDraft | ValidatedOrder |
| createEvent | ValidatedOrder | OrderAccepted |

Định nghĩa pipeline:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|createEvent"
~~~

Thứ tự trong chuỗi có ý nghĩa. Nếu đổi thành validateOrder|parseOrder|createEvent, kiểu đầu vào và đầu ra không còn khớp với hợp đồng đã khai báo. Hãy thiết kế kiểu dữ liệu trung gian trước khi ghép các hàm để lỗi tương thích được phát hiện sớm.

### 2.2. Binding của một hàm đã ghép

Giả sử định nghĩa là parseOrder|validateOrder|createEvent, pipeline nhận dữ liệu từ một input binding và phát kết quả cuối cùng qua một output binding. Tên binding được suy ra từ function definition đã ghép:

- parseOrder|validateOrder|createEvent-in-0
- parseOrder|validateOrder|createEvent-out-0

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|createEvent"
    stream:
      bindings:
        "parseOrder|validateOrder|createEvent-in-0":
          destination: orders.raw
          group: order-pipeline
          content-type: text/plain
        "parseOrder|validateOrder|createEvent-out-0":
          destination: orders.accepted
          content-type: application/json
~~~

Tên binding chứa dấu |, vì vậy nên đặt trong dấu nháy kép ở YAML để thể hiện rõ đây là một khóa cấu hình. Destination orders.raw là nơi nhận dữ liệu ban đầu; orders.accepted nhận kết quả sau toàn bộ pipeline.

Nếu muốn dùng tên binding ngắn hơn, có thể ánh xạ tên binding ngầm định qua spring.cloud.stream.function.bindings, rồi cấu hình destination bằng tên alias. Việc ánh xạ không thay đổi thứ tự ghép hàm; nó chỉ đổi tên cổng logic được dùng trong cấu hình binding.

### 2.3. Xác định biên của pipeline

Khi ghép các hàm, hãy xác định rõ điểm nào nhận thông điệp từ bên ngoài và điểm nào trả kết quả ra ngoài. Với chuỗi chỉ gồm Function, hàm đầu tiên cung cấp input và hàm cuối cùng cung cấp output. Nếu thiết kế có Supplier làm nguồn phát hoặc Consumer làm bước kết thúc, chữ ký tổng thể sẽ thay đổi tương ứng: Supplier không cần input binding, còn Consumer không tạo output binding.

Supplier imperative cần cơ chế poller để tạo dữ liệu theo lịch; Consumer kết thúc xử lý mà không phát kết quả. Các thành phần này vẫn tuân theo quy tắc kiểu dữ liệu giữa các bước. Khi kết hợp nhiều loại hàm trong một definition, hãy kiểm tra log khởi động để xác nhận function được tạo cùng các binding biên như dự kiến.

## 3. Khai báo nhiều hàm độc lập bằng dấu ;

Dấu ; phân tách các function definition độc lập. Nó không nối đầu ra của hàm trước vào đầu vào của hàm sau. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder;publishMetrics"
~~~

Framework kích hoạt hai bean riêng:

- validateOrder nhận và xử lý luồng đơn hàng.
- publishMetrics nhận và xử lý luồng số liệu.

Mỗi hàm có binding riêng. Nếu cả hai là Function, mỗi hàm có input và output binding riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder;publishMetrics"
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.submitted
          group: order-validation
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
        publishMetrics-in-0:
          destination: metrics.events
          group: metrics-publisher
          content-type: application/json
        publishMetrics-out-0:
          destination: metrics.published
          content-type: application/json
~~~

Sơ đồ luồng:

~~~mermaid
flowchart LR
    A[("orders.submitted")] --> B["validateOrder"]
    B --> C[("orders.validated")]
    D[("metrics.events")] --> E["publishMetrics"]
    E --> F[("metrics.published")]
~~~

Hai hàm không gọi nhau chỉ vì chúng được liệt kê cùng một thuộc tính. Chúng hoạt động như hai luồng logic độc lập trong cùng ứng dụng. Nếu validateOrder phát ra orders.validated và publishMetrics cần xử lý kết quả đó, hãy cấu hình input destination của publishMetrics trỏ tới destination thích hợp hoặc thiết kế một pipeline composition nếu hai bước phải chạy trực tiếp nối tiếp trong cùng lần xử lý.

### 3.1. Nhiều kiểu hàm trong cùng definition

Danh sách có thể gồm các kiểu hàm khác nhau. Ví dụ một Function xử lý đơn hàng và một Consumer ghi nhận thông báo:

~~~java
@Bean
Function<OrderDraft, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(
        order.orderId(),
        order.customerId(),
        order.quantity(),
        "ACCEPTED"
    );
}

@Bean
Consumer<MetricSnapshot> recordMetric() {
    return snapshot -> metricsRepository.save(snapshot);
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: "acceptOrder;recordMetric"
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.validated
          group: order-acceptance
        acceptOrder-out-0:
          destination: orders.accepted
        recordMetric-in-0:
          destination: metrics.snapshots
          group: metrics-recorder
~~~

acceptOrder có input và output binding. recordMetric chỉ có input binding vì Consumer không trả kết quả. Không khai báo recordMetric-out-0 nếu Consumer không tạo đầu ra.

### 3.2. Kết hợp composition và danh sách độc lập

Một definition có thể chứa nhiều phần tử, trong đó mỗi phần tử có thể là một pipeline ghép. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|createEvent;recordMetric"
~~~

Ý nghĩa:

1. parseOrder|validateOrder|createEvent là một pipeline gồm ba bước chạy theo thứ tự.
2. recordMetric là một hàm độc lập trong cùng ứng dụng.

Dấu | được xử lý bên trong một function definition; dấu ; tách các definition ở cấp danh sách. Cách đọc này giúp tránh nhầm một chuỗi dài thành các hàm độc lập hoặc ngược lại.

## 4. Phân biệt composition với kết nối qua broker

Composition và kết nối qua destination đều có thể tạo ra chuỗi xử lý, nhưng cơ chế vận hành khác nhau:

| Đặc điểm | Function composition (|) | Nối các dịch vụ qua broker |
|---|---|---|
| Ranh giới | Các hàm trong cùng pipeline của một ứng dụng | Các binding và dịch vụ có thể triển khai riêng |
| Truyền dữ liệu | Giá trị Java được chuyển từ hàm này sang hàm kế tiếp | Thông điệp được gửi và nhận qua broker |
| Topic/queue trung gian | Không tự tạo | Có destination ở các điểm giao tiếp |
| Khả năng triển khai độc lập | Các bước composition đi cùng một ứng dụng | Producer và consumer có thể triển khai độc lập |
| Lỗi giữa các bước | Lỗi truyền trong cùng lần gọi pipeline | Có thể có retry, xác nhận và DLQ ở ranh giới thông điệp |

Chọn composition khi các bước là một quy trình xử lý logic cần thay đổi và triển khai cùng nhau. Chọn giao tiếp qua broker khi cần tách dịch vụ, lưu giữ thông điệp, cho phép nhiều consumer độc lập hoặc cần mở rộng từng phần riêng.

Không nên ghép tất cả bước vào một pipeline dài nếu các bước cần được triển khai độc lập hoặc có chính sách retry khác nhau. Ngược lại, không cần tạo topic cho mỗi phép biến đổi nhỏ nếu chúng chỉ là các bước thuần trong cùng một quy trình.

## 5. Xử lý lỗi trong pipeline

Nếu một Function ở giữa pipeline ném exception, lần xử lý của pipeline thất bại và exception được truyền ra lớp tích hợp. Các bước sau đó không tiếp tục với kết quả không hợp lệ. Cơ chế retry hoặc xử lý lỗi được áp dụng tại ranh giới binding và phụ thuộc cấu hình Spring Cloud Stream cùng binder.

Ví dụ, nếu validateOrder từ chối đơn hàng bằng exception:

~~~java
@Bean
Function<OrderDraft, ValidatedOrder> validateOrder() {
    return order -> {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return new ValidatedOrder(
            order.orderId(),
            order.customerId(),
            order.quantity()
        );
    };
}
~~~

createEvent không được gọi cho thông điệp thất bại. Nếu input binding cấu hình retry, framework có thể gọi lại toàn bộ pipeline cho thông điệp đó. Vì vậy, các bước đã chạy trước khi xảy ra lỗi nên tránh tác động không thể lặp an toàn. Nếu cần ghi database hoặc gọi dịch vụ ngoài, hãy thiết kế idempotency và ranh giới transaction phù hợp.

Trong composition, các bước trung gian không có binding riêng để cấu hình retry độc lập. Nếu một bước cần chính sách giao nhận, thời gian chờ hoặc DLQ riêng, hãy cân nhắc tách bước đó thành một consumer/producer độc lập qua broker.

## 6. Kiểm tra function definition và binding khi khởi động

Khi có nhiều bean hàm, lỗi thường gặp là khai báo thiếu tên hoặc sai cú pháp trong spring.cloud.function.definition.

| Cấu hình | Ý nghĩa |
|---|---|
| normalizeOrder | Kích hoạt một hàm |
| parseOrder|validateOrder | Ghép hai hàm theo thứ tự |
| validateOrder;publishMetrics | Kích hoạt hai hàm độc lập |
| parseOrder|validateOrder;publishMetrics | Một pipeline ghép và một hàm độc lập |

Các lỗi nên kiểm tra:

- Tên trong definition không khớp tên bean.
- Một bean không được đăng ký do thiếu cấu hình hoặc component scan.
- Kiểu đầu ra của hàm trước không tương thích với kiểu đầu vào của hàm sau.
- Dùng ; khi muốn ghép hàm hoặc dùng | khi muốn kích hoạt độc lập.
- Cấu hình binding theo tên bean đơn lẻ trong khi thực tế đang dùng tên composition.
- Khai báo output binding cho Consumer hoặc bỏ sót input binding của Function.

Đặt log ở mức phù hợp cho Spring Cloud Function và Spring Cloud Stream để xem function nào được chọn, binding nào được tạo và binder nào được sử dụng. Khi chạy production, không để DEBUG rộng kéo dài vì log có thể tăng nhanh và chứa metadata vận hành.

## 7. Kiểm thử composition và nhiều function

Nên kiểm thử từng Function trực tiếp trước, sau đó kiểm tra cách chúng được ghép và kết nối với binding.

### 7.1. Unit test từng bước

Ví dụ kiểm thử validateOrder:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ValidateOrderTest {

    @Test
    void keepsValidOrderData() {
        var function = new OrderPipeline().validateOrder();
        var result = function.apply(
            new OrderDraft("order-501", "customer-8", 2)
        );

        assertEquals("order-501", result.orderId());
        assertEquals("customer-8", result.customerId());
        assertEquals(2, result.quantity());
    }
}
~~~

Unit test giúp xác minh quy tắc của từng bước mà không cần khởi động broker.

### 7.2. Test Binder cho pipeline

Spring Cloud Stream Test Binder cho phép kiểm tra input và output binding trong ứng dụng mà không cần broker thật. Với composition, gửi payload vào input binding của pipeline và xác minh kết quả cuối cùng tại output binding.

Kịch bản kiểm thử nên xác minh:

1. Payload đầu vào được chuyển đổi sang kiểu mà hàm đầu tiên mong đợi.
2. Các bước chạy đúng thứ tự và truyền đúng kiểu dữ liệu.
3. Output cuối cùng được phát ra đúng binding.
4. Trường hợp lỗi ở bước giữa không tạo output hợp lệ.
5. Với nhiều definition độc lập, thông điệp gửi vào binding của hàm này không bị xử lý nhầm bởi hàm khác.

Test Binder không mô phỏng đầy đủ partition, consumer group, rebalance hoặc xác nhận riêng của broker. Dùng integration test với Kafka, RabbitMQ hoặc Pulsar khi cần xác minh những đặc tính đó.

## 8. Quy trình lựa chọn cú pháp

Trước khi khai báo spring.cloud.function.definition, hãy xác định quan hệ giữa các bước:

1. Nếu kết quả của bước A phải trở thành đầu vào trực tiếp của bước B trong cùng quy trình, dùng A|B.
2. Nếu A và B xử lý hai luồng riêng, dùng A;B.
3. Nếu có nhiều bước tuần tự và một tác vụ độc lập, dùng A|B|C;D.
4. Kiểm tra kiểu dữ liệu giữa từng cặp hàm trong pipeline.
5. Xác định input/output binding ở biên của từng definition.
6. Đặt destination và group cho mỗi binding theo nhu cầu tiêu thụ.
7. Kiểm thử từng hàm, pipeline và các binding độc lập.
8. Kiểm tra log khởi động để xác nhận function definition và binding đã được tạo như mong đợi.

Một ví dụ tổng hợp:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|createEvent;recordMetric"
    stream:
      bindings:
        "parseOrder|validateOrder|createEvent-in-0":
          destination: orders.raw
          group: order-pipeline
        "parseOrder|validateOrder|createEvent-out-0":
          destination: orders.accepted
        recordMetric-in-0:
          destination: metrics.snapshots
          group: metrics-recorder
~~~

Pipeline đơn hàng nhận dữ liệu thô, kiểm tra và tạo sự kiện đã chấp nhận. Hàm recordMetric đọc một luồng số liệu độc lập. Mỗi luồng có destination và group riêng, còn các bước trong pipeline chia sẻ một lần xử lý logic.

## 9. Những điểm cần nhớ

- | ghép các hàm theo thứ tự từ trái sang phải.
- Kiểu đầu ra của bước trước phải tương thích với kiểu đầu vào của bước sau.
- Một pipeline ghép có binding ở biên; các bước giữa không tự tạo destination.
- ; phân tách nhiều function definition độc lập.
- Mỗi function độc lập có thể có input/output binding riêng tùy kiểu Supplier, Function hoặc Consumer.
- Composition không thay thế broker khi cần tách dịch vụ hoặc có chính sách giao nhận độc lập.
- Lỗi ở một bước có thể làm thất bại cả lần gọi pipeline; thiết kế tác động bên ngoài theo hướng idempotent.

## Tài liệu tham khảo chính thức

- [Spring Cloud Function - Function Composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): mô hình hàm và cách ghép function.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html): function definition, binding và tích hợp broker.
- [Spring Cloud Stream - Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): cách các functional bean được kết nối với input và output binding.
