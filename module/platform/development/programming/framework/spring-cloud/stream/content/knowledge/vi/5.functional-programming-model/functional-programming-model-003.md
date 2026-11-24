# Chọn hàm hoạt động bằng spring.cloud.function.definition

Trong ứng dụng Spring Cloud Stream, một project có thể khai báo nhiều bean hàm để xử lý những luồng sự kiện khác nhau. Thuộc tính `spring.cloud.function.definition` cho Spring Cloud Function biết bean nào cần được kích hoạt và đưa vào mô hình binding của Spring Cloud Stream.

Thuộc tính này chọn hàm theo tên bean. Nó không tự tạo bean, không quyết định broker, cũng không đặt tên topic, exchange hay queue. Sau khi chọn hàm, ta vẫn cấu hình các input/output binding tương ứng trong `spring.cloud.stream.bindings`.

## 1. Vì sao cần chọn hàm?

Spring Cloud Stream hỗ trợ ba kiểu hàm chính:

| Kiểu bean | Vai trò | Binding mặc định |
|---|---|---|
| `Supplier<T>` | Tạo và phát dữ liệu | `<beanName>-out-0` |
| `Function<T, R>` | Nhận dữ liệu, xử lý và trả kết quả | `<beanName>-in-0`, `<beanName>-out-0` |
| `Consumer<T>` | Nhận và xử lý dữ liệu, không trả output | `<beanName>-in-0` |

Tên binding được hình thành từ tên bean và vị trí cổng vào/ra. Ví dụ, bean tên `validateOrder` có input binding `validateOrder-in-0` và output binding `validateOrder-out-0`.

Nếu ứng dụng chỉ có một bean hàm phù hợp, framework thường có thể tự phát hiện và kích hoạt hàm đó. Khi ứng dụng có nhiều bean Supplier, Function hoặc Consumer, việc khai báo rõ `spring.cloud.function.definition` giúp xác định chính xác hàm nào tham gia xử lý. Điều này cũng làm cấu hình dễ đọc và ổn định hơn khi project phát triển.

Hãy phân biệt ba việc:

1. Khai báo bean hàm để chứa logic nghiệp vụ.
2. Chọn một hoặc nhiều bean bằng `spring.cloud.function.definition`.
3. Ánh xạ binding được tạo ra tới destination bằng `spring.cloud.stream.bindings`.

## 2. Tên trong definition được lấy từ đâu?

Tên hàm trong definition là tên bean Spring. Với phương thức `@Bean`, tên phương thức là tên bean mặc định:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BasicOrderFunctionConfiguration {

    @Bean
    Function<String, String> normalizeOrder() {
        return value -> value.trim();
    }

}
~~~

Trong ví dụ này, tên bean là `normalizeOrder`, vì vậy có thể chọn bằng:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
~~~

Nếu đặt tên bean tường minh, definition phải dùng tên đó:

~~~java
import org.springframework.context.annotation.Bean;

@Bean("normalize")
Function<String, String> normalizeOrder() {
    return value -> value.trim();
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: normalize
~~~

Tên class Java, tên destination hoặc tên binding không thay thế cho tên bean trong thuộc tính definition. Khi ứng dụng không kích hoạt hàm như mong đợi, hãy kiểm tra chính xác tên bean trong Spring ApplicationContext trước.

## 3. Chọn một hàm duy nhất

Với một function xử lý đơn hàng, khai báo:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SingleOrderFunctionConfiguration {

    @Bean
    Function<String, String> validateOrder() {
        return order -> {
            if (order == null || order.isBlank()) {
                throw new IllegalArgumentException("Order must not be blank");
            }
            return order.trim();
        };
    }
}
~~~

Cấu hình đầy đủ trong `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder

    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.raw
          group: order-validator
          content-type: text/plain

        validateOrder-out-0:
          destination: orders.validated
          content-type: text/plain
~~~

Ứng dụng sẽ nhận dữ liệu từ destination `orders.raw`, đưa payload qua function `validateOrder`, rồi gửi kết quả tới `orders.validated`. Thuộc tính definition chỉ chọn function; hai destination và consumer group được thiết lập ở phần binding.

Nếu đổi tên phương thức bean từ `validateOrder` thành `checkOrder`, cần cập nhật cả definition và các binding tương ứng thành `checkOrder-in-0`, `checkOrder-out-0`. Việc chỉ đổi một nơi có thể làm ứng dụng không tìm thấy hàm hoặc không áp dụng cấu hình binding mong muốn.

## 4. Kích hoạt nhiều hàm độc lập bằng dấu chấm phẩy

Dùng dấu chấm phẩy (`;`) để chọn nhiều hàm độc lập trong cùng ứng dụng. Các hàm được kích hoạt riêng, mỗi hàm có binding riêng theo tên bean.

Ví dụ khai báo bốn bean:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;
import java.time.Instant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IndependentOrderFunctions {

    @Bean
    Function<String, String> normalizeOrder() {
        return value -> value.trim();
    }

    @Bean
    Function<String, String> maskOrder() {
        return value -> value.replaceAll("\\d", "*");
    }

    @Bean
    Consumer<String> auditOrder() {
        return value -> System.out.println("Audit order: " + value);
    }

    @Bean
    Supplier<String> heartbeat() {
        return () -> Instant.now().toString();
    }
}
~~~

Chọn cả bốn bean:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder;maskOrder;auditOrder;heartbeat"

    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizer
          content-type: text/plain
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: text/plain

        maskOrder-in-0:
          destination: orders.to-mask
          group: order-masker
          content-type: text/plain
        maskOrder-out-0:
          destination: orders.masked
          content-type: text/plain

        auditOrder-in-0:
          destination: orders.audit
          group: order-auditor
          content-type: text/plain

        heartbeat-out-0:
          destination: system.heartbeat
          content-type: text/plain
~~~

Các binding trên hoạt động độc lập:

- `normalizeOrder` nhận dữ liệu từ `orders.raw` và phát kết quả tới `orders.normalized`.
- `maskOrder` nhận dữ liệu từ `orders.to-mask` và phát kết quả tới `orders.masked`.
- `auditOrder` nhận dữ liệu từ `orders.audit` và thực hiện tác vụ audit, không có output binding.
- `heartbeat` được poller gọi và phát thời điểm hiện tại tới `system.heartbeat` qua output binding.

Supplier được gọi lặp theo chu kỳ poller khi ứng dụng hoạt động, vì vậy ví dụ heartbeat sẽ phát nhiều timestamp. Với nguồn sự kiện thực tế, cần xác định chu kỳ phát và bảo đảm mỗi lần polling không lặp lại một thao tác nghiệp vụ chỉ được phép thực hiện một lần.

Dấu chấm phẩy không chuyển output của hàm trước thành input của hàm sau. Nó chỉ yêu cầu framework kích hoạt nhiều hàm riêng biệt. Nếu mục tiêu là nối các bước xử lý thành một luồng liên tiếp, dùng composition bằng dấu gạch đứng (`|`).

## 5. Kết hợp các hàm bằng dấu gạch đứng

Dùng dấu `|` để ghép các hàm tương thích kiểu dữ liệu thành một function tổng hợp. Output của hàm đứng trước trở thành input của hàm đứng sau.

Ví dụ:

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderPipelineFunctions {

    @Bean
    Function<String, String> trimOrder() {
        return value -> value.trim();
    }

    @Bean
    Function<String, String> uppercaseOrder() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimOrder|uppercaseOrder"

    stream:
      bindings:
        "trimOrder|uppercaseOrder-in-0":
          destination: orders.raw
          group: order-transformer
          content-type: text/plain

        "trimOrder|uppercaseOrder-out-0":
          destination: orders.normalized
          content-type: text/plain
~~~

Với message đầu vào:

~~~text
  order-created  
~~~

Hàm `trimOrder` loại bỏ khoảng trắng ở hai đầu. Kết quả được chuyển thẳng tới `uppercaseOrder`, sau đó output binding gửi chuỗi `ORDER-CREATED` tới destination `orders.normalized`.

Binding của function tổng hợp sử dụng tên composition, theo dạng `trimOrder|uppercaseOrder-in-0` và `trimOrder|uppercaseOrder-out-0`. Khi đặt tên key YAML có dấu `|`, nên đặt toàn bộ key trong dấu nháy kép để cấu hình dễ đọc và tránh nhầm lẫn với cú pháp YAML.

Các hàm được ghép phải có kiểu đầu ra và đầu vào tương thích. Ví dụ `Function<String, Integer>` có thể nối với `Function<Integer, Long>`; không thể nối trực tiếp với `Function<Order, String>` nếu không có bước chuyển đổi phù hợp.

Composition cũng có thể kết thúc bằng Consumer để xử lý kết quả mà không phát output, hoặc bắt đầu bằng Supplier khi cần tạo dữ liệu rồi chuyển qua các bước Function. Dù composition có nhiều bước, từ góc nhìn binding nó vẫn là một function tổng hợp với các cổng vào/ra tương ứng.

## 6. Kết hợp nhiều nhóm: độc lập và composition

Có thể kết hợp hai cách trong một definition. Dấu `|` ghép các hàm trong cùng một pipeline; dấu `;` tách các nhóm function độc lập.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimOrder|uppercaseOrder;auditOrder"

    stream:
      bindings:
        "trimOrder|uppercaseOrder-in-0":
          destination: orders.raw
          group: order-transformer
          content-type: text/plain
        "trimOrder|uppercaseOrder-out-0":
          destination: orders.normalized
          content-type: text/plain
        auditOrder-in-0:
          destination: orders.audit
          group: order-auditor
          content-type: text/plain
~~~

Ở đây, `trimOrder|uppercaseOrder` là một pipeline nhận từ `orders.raw` và phát tới `orders.normalized`. `auditOrder` là function độc lập nhận từ `orders.audit`. Cả hai nhóm đều được kích hoạt trong cùng ứng dụng.

Nên đặt tên bean thể hiện rõ nhiệm vụ và giữ cấu trúc definition dễ đọc. Khi một chuỗi composition dài, hãy chia logic thành các function nhỏ có kiểu đầu vào/đầu ra rõ ràng. Điều này giúp kiểm thử từng bước và xác định lỗi dễ hơn.

## 7. Phân biệt definition với binding và destination

Ba lớp cấu hình thường bị nhầm lẫn:

| Thành phần | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Function bean | Logic xử lý nằm ở đâu? | `normalizeOrder()` |
| `spring.cloud.function.definition` | Bean nào được kích hoạt? | `normalizeOrder` |
| `spring.cloud.stream.bindings` | Cổng input/output nối với destination nào? | `normalizeOrder-in-0.destination: orders.raw` |
| Binder | Kết nối tới middleware nào? | Kafka, RabbitMQ hoặc Pulsar binder |

Ví dụ, cùng function `normalizeOrder` có thể được ánh xạ tới topic Kafka trong môi trường local và một destination RabbitMQ trong môi trường thử nghiệm bằng cách thay binder cùng cấu hình kết nối. Logic function và tên bean vẫn có thể giữ nguyên.

Không đặt tên topic vào `spring.cloud.function.definition`. Ví dụ `definition: orders.raw` chỉ đúng nếu trong Spring context thật sự có bean hàm tên `orders.raw`, điều thường không phải mục đích mong muốn.

## 8. Cấu hình theo profile và biến môi trường

Có thể dùng cùng một function definition trong nhiều môi trường, nhưng thay destination, group hoặc broker theo profile.

Ví dụ file `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder

    stream:
      bindings:
        normalizeOrder-in-0:
          destination: ${ORDERS_INPUT:orders.raw}
          group: ${ORDERS_GROUP:order-normalizer}
          content-type: text/plain
        normalizeOrder-out-0:
          destination: ${ORDERS_OUTPUT:orders.normalized}
          content-type: text/plain
~~~

Có thể ghi đè biến môi trường khi chạy ứng dụng:

~~~bash
ORDERS_INPUT=orders.incoming ORDERS_OUTPUT=orders.cleaned ./mvnw spring-boot:run
~~~

Với PowerShell:

~~~powershell
$env:ORDERS_INPUT = "orders.incoming"
$env:ORDERS_OUTPUT = "orders.cleaned"
.\mvnw.cmd spring-boot:run
~~~

Tên biến môi trường tương ứng với property definition là `SPRING_CLOUD_FUNCTION_DEFINITION`. Ví dụ có thể chọn function khác khi triển khai bằng cấu hình môi trường:

~~~bash
SPRING_CLOUD_FUNCTION_DEFINITION=normalizeOrder ./mvnw spring-boot:run
~~~

Khi sử dụng profile, kiểm tra giá trị cuối cùng sau khi Spring Boot hợp nhất `application.yml`, file profile, biến môi trường và tham số dòng lệnh. Một profile có thể vô tình ghi đè definition, khiến ứng dụng kích hoạt hàm khác với dự kiến.

## 9. Kiểm tra hàm nào thực sự được kích hoạt

Khi ứng dụng khởi động, đọc log của Spring Cloud Function và Spring Cloud Stream để kiểm tra function được phát hiện, function được chọn và các binding được tạo. Tùy phiên bản và mức log, nội dung log có thể khác nhau.

Có thể bật log chi tiết trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.cloud.function: DEBUG
    org.springframework.cloud.stream: DEBUG
~~~

Sau khi khởi động, đối chiếu các điểm sau:

1. Tên bean trong definition có tồn tại trong Spring ApplicationContext.
2. Function được chọn có đúng loại Supplier, Function hoặc Consumer theo mục đích.
3. Tên binding được tạo có khớp key cấu hình trong `spring.cloud.stream.bindings`.
4. Input binding trỏ tới đúng destination và consumer group.
5. Output binding có destination và content type phù hợp.
6. Binder được chọn và kết nối đúng broker.

Nếu có actuator và endpoint phù hợp được bật, có thể dùng thông tin binding/health để hỗ trợ kiểm tra trạng thái. Không nên bật endpoint quản trị nhạy cảm công khai chỉ để gỡ lỗi.

## 10. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không tìm thấy function theo definition | Sai tên bean, bean chưa được component scan hoặc chưa được tạo | Kiểm tra tên phương thức `@Bean`, tên `@Component` và package scan |
| Ứng dụng có nhiều function nhưng chỉ một luồng hoạt động | Definition chỉ chọn một function hoặc các function chưa được phân tách đúng | Dùng `;` cho nhiều function độc lập |
| Output của hàm trước không đi vào hàm sau | Dùng `;` thay vì composition | Dùng `functionA|functionB` nếu kiểu dữ liệu tương thích |
| Composition không khởi tạo được | Output type và input type của hai bước không tương thích | Kiểm tra generic và kiểu payload thực tế của từng function |
| Không tìm thấy binding | Key binding không khớp tên hàm hoặc tên composition | Kiểm tra hậu tố `-in-0`, `-out-0` và tên bean |
| Hàm được chọn đúng nhưng không nhận message | Destination, group, binder hoặc broker chưa đúng | Kiểm tra cấu hình `spring.cloud.stream.bindings` và log binder |
| Local chạy đúng nhưng staging chọn hàm khác | Profile hoặc biến môi trường ghi đè definition | Kiểm tra cấu hình hiệu lực khi khởi động |
| Consumer không có output | Bean là Consumer nên chỉ có input binding | Kiểm tra mục tiêu xử lý; Consumer không tạo output binding |

Một số quy tắc giúp tránh lỗi:

- Dùng đúng `spring.cloud.function.definition`, không đặt nhầm thành `spring.cloud.stream.function.definition`.
- Dùng tên bean chính xác, bao gồm cả tên khai báo tường minh trong `@Bean("...")`.
- Dùng `;` khi cần kích hoạt nhiều hàm độc lập.
- Dùng `|` khi muốn ghép output của hàm trước với input của hàm sau.
- Cập nhật binding khi đổi tên bean hoặc đổi tên composition.
- Kiểm tra cấu hình hiệu lực của profile và biến môi trường trước khi kết luận function không hoạt động.

## 11. Kiểm thử lựa chọn và composition

Có thể kiểm thử từng bean như logic Java thông thường:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class IndependentOrderFunctionsTest {

    @Test
    void normalizeOrderRemovesSurroundingSpaces() {
        IndependentOrderFunctions functions = new IndependentOrderFunctions();
        assertEquals("order-100", functions.normalizeOrder().apply("  order-100  "));
    }
}
~~~

Đối với luồng Spring Cloud Stream, dùng test binder để kiểm tra binding đầu vào và đầu ra mà không cần broker thật. Với function composition, gửi message vào input binding của composition rồi xác nhận kết quả tại output binding của composition.

Một kế hoạch kiểm thử nên bao gồm:

- Chạy ứng dụng với một function duy nhất và xác nhận đúng input/output binding.
- Chạy với nhiều function được phân tách bằng dấu chấm phẩy; xác nhận mỗi function có binding riêng.
- Chạy composition bằng dấu `|`; xác nhận thứ tự thực thi và kết quả cuối.
- Thử kiểu dữ liệu không tương thích trong quá trình phát triển để phát hiện lỗi wiring sớm.
- Khởi động bằng profile khác nhau và xác nhận definition cuối cùng đúng như cấu hình dự kiến.
- Chạy integration test với broker thật để xác nhận destination, group và hành vi giao nhận.

Test binder có thể chứng minh ứng dụng đã nối function với binding theo cấu hình. Nó không thay thế kiểm thử broker thật cho partition, rebalance, acknowledgment, retry, transaction hoặc DLQ.

## 12. Trình tự thực hành và tiêu chí hoàn thành

| Bước | Thực hành | Kết quả cần đạt |
|---|---|---|
| 1. Khai báo bean | Tạo một Supplier, một Function và một Consumer | Biết tên bean Spring và kiểu hàm |
| 2. Chọn một hàm | Đặt `spring.cloud.function.definition` bằng tên bean | Chỉ đúng function được kích hoạt |
| 3. Chọn nhiều hàm | Phân tách tên bằng dấu chấm phẩy | Các function hoạt động độc lập với binding riêng |
| 4. Composition | Ghép hai Function bằng dấu `|` | Output bước trước trở thành input bước sau |
| 5. Ánh xạ binding | Cấu hình destination, group và content type | Message đi đúng destination |
| 6. Kiểm thử | Dùng unit test, test binder và broker thật | Phân biệt lỗi logic, lỗi wiring và lỗi broker |
| 7. Triển khai | Kiểm tra profile và biến môi trường | Môi trường chạy kích hoạt đúng function |

Hoàn thành bài khi có thể giải thích và tự cấu hình được ba trường hợp: một function duy nhất, nhiều function độc lập và một pipeline gồm nhiều function. Người học cũng cần xác định được binding name được sinh ra từ tên bean hoặc composition, rồi ánh xạ binding đó tới destination phù hợp.

## 13. Tài liệu tham khảo chính thức

- [Spring Cloud Function — Function Catalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — mô hình hàm và đăng ký function bean.
- [Spring Cloud Function — Function Composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html#function-composition) — cách kết hợp các function.
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — tên binding phát sinh từ Supplier, Function và Consumer.
- [Spring Cloud Stream — Programming model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — tích hợp mô hình hàm với binding và binder.
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — cấu hình destination, group và content type.
- [Spring Boot — Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — cấu hình theo profile, biến môi trường và tham số dòng lệnh.

