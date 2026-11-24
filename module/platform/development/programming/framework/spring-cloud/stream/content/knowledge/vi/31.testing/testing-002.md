# Thiết lập spring-cloud-stream-test-binder và @EnableTestBinder

Spring Cloud Stream cung cấp **Test Binder** để kiểm thử các function và binding trong JVM mà không cần chạy Kafka, RabbitMQ hoặc Pulsar. Test Binder dựa trên Spring Integration, cung cấp một môi trường message broker trong bộ nhớ để bài test gửi message vào input binding và nhận message từ output binding.

Để sử dụng, thêm dependency `spring-cloud-stream-test-binder` với scope `test`, sau đó bật hạ tầng kiểm thử bằng annotation `@EnableTestBinder` trên cấu hình Spring dùng trong test. Spring cung cấp `InputDestination` và `OutputDestination` để gửi/nhận message. Cách này phù hợp để kiểm tra logic xử lý, ánh xạ function và destination, payload, header cùng các luồng message cơ bản của module `SPRING_CLOUD_STREAM`.

Test Binder là một broker giả lập trong tiến trình. Nó giúp kiểm thử phần ứng dụng và Spring Cloud Stream binding, nhưng không thay thế kiểm thử tích hợp với broker thật khi cần xác minh giao thức, xác thực, partition, consumer group, transaction, retry hoặc DLQ đặc thù của Kafka, RabbitMQ hay Pulsar.

## 1. Test Binder nằm ở đâu trong mô hình Spring Cloud Stream?

Ứng dụng Spring Cloud Stream có phần xử lý nghiệp vụ được viết bằng `Supplier`, `Function` hoặc `Consumer`. Binder kết nối các input/output binding với hệ thống nhắn tin. Trong production, binder tương ứng có thể kết nối Kafka, RabbitMQ hoặc Pulsar. Trong test, Test Binder thay phần broker bên ngoài bằng message channels trong JVM.

```text
Production:

Kafka / RabbitMQ / Pulsar
          |
          v
     Real Binder
          |
          v
Input binding -> Function/Consumer -> Output binding

Test:

InputDestination
      |
      v
Spring Integration Test Binder (in-JVM)
      |
      v
Input binding -> Function/Consumer -> Output binding
                                      |
                                      v
                               OutputDestination
```

Test Binder giữ nguyên cách ứng dụng khai báo function và binding. Bài test có thể gửi message vào input, để function xử lý, rồi nhận message ở output. Không cần cài đặt broker hoặc mở cổng mạng để chạy các test này.

## 2. Thêm dependency `spring-cloud-stream-test-binder`

Dependency phải nằm trong cấu hình dành riêng cho test để không được đóng gói vào runtime artifact của ứng dụng.

### Maven

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
```

### Gradle Kotlin DSL

```kotlin
dependencies {
    testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
}
```

### Gradle Groovy DSL

```groovy
dependencies {
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
```

Không tự thêm version vào dependency nếu dự án đã dùng Spring Cloud BOM hoặc dependency management tương ứng. BOM cần quản lý phiên bản Spring Cloud Stream đồng bộ với Spring Boot và Spring Cloud release train. Nếu không dùng BOM, hãy chọn phiên bản test binder tương thích với phiên bản `spring-cloud-stream` trong dự án.

Các bài test cũng cần framework test như JUnit Jupiter và Spring Boot Test. Trong dự án Spring Boot, dependency thường dùng là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
```

`spring-boot-starter-test` cung cấp các thành phần kiểm thử Spring/JUnit/AssertJ/Mockito theo dependency management của dự án. Không cần thêm Kafka broker, RabbitMQ broker hoặc Pulsar broker chỉ để chạy một test sử dụng Test Binder.

## 3. Vai trò của `@EnableTestBinder`

`@EnableTestBinder` bật cấu hình Test Binder trong Spring ApplicationContext. Khi cấu hình này được nạp, Spring Cloud Stream có thể tạo các binding dùng Test Binder và cung cấp các bean kiểm thử như:

- `InputDestination`: gửi message vào input binding.
- `OutputDestination`: nhận message được phát ra từ output binding.

Annotation thường được đặt trên cấu hình ứng dụng dùng trong test. Có thể đặt nó trên test configuration hoặc application configuration được nạp bởi `@SpringBootTest`.

Ví dụ:

```java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTestBinder
class StreamTestApplication {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }
}
```

Trong ví dụ, `@EnableTestBinder` kích hoạt Test Binder cho context và function `uppercase` được đăng ký như một bean bình thường. Khi test gửi message vào input binding, function được gọi và kết quả được Test Binder giữ ở output destination.

Không đặt annotation vào một class không được nạp vào ApplicationContext rồi kỳ vọng Test Binder tự hoạt động. Cần xác nhận cấu hình có annotation thực sự là một phần của context được test khởi tạo.

## 4. Khởi tạo test bằng `@SpringBootTest`

`@SpringBootTest` tạo ApplicationContext gần với cách ứng dụng Spring Boot được khởi động. Chỉ định rõ class cấu hình giúp test dùng đúng function và Test Binder.

Ví dụ đầy đủ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

import java.util.function.Function;

@SpringBootTest(classes = StreamTestApplication.class)
class StreamBinderTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void transformsInputMessage() {
        input.send("hello".getBytes(StandardCharsets.UTF_8));

        Message<byte[]> result = output.receive(1_000L);

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("HELLO");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class StreamTestApplication {

        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase();
        }
    }
}
```

Các bước diễn ra:

1. `@SpringBootTest` khởi tạo context dùng `StreamTestApplication`.
2. `@EnableTestBinder` bật Test Binder trong context đó.
3. Spring Cloud Stream phát hiện function bean `uppercase` và tạo input/output binding tương ứng.
4. Test gửi bytes vào `InputDestination`.
5. Test Binder chuyển message đến function.
6. Function chuyển chuỗi thành chữ hoa.
7. Test Binder giữ message output để `OutputDestination` nhận lại.
8. Test xác minh payload nhận được.

Ví dụ dùng `receive(1_000L)` để chờ tối đa khoảng một giây. Nếu không có message trong khoảng thời gian đó, kết quả có thể là `null`; vì vậy nên kiểm tra `isNotNull()` trước khi đọc payload để lỗi test dễ hiểu.

## 5. Tên binding mặc định của functional model

Spring Cloud Stream tạo binding name từ tên function bean và vị trí input/output:

| Function bean | Binding | Vai trò |
|---|---|---|
| `uppercase` | `uppercase-in-0` | Input đầu tiên |
| `uppercase` | `uppercase-out-0` | Output đầu tiên |
| `enrichOrder` | `enrichOrder-in-0` | Tham số đầu tiên |
| `enrichOrder` | `enrichOrder-in-1` | Tham số thứ hai |
| `publishOrder` | `publishOrder-out-0` | Output của Supplier |
| `consumeOrder` | `consumeOrder-in-0` | Input của Consumer |

Test Binder sử dụng các binding này để định tuyến message. Nếu ứng dụng có một input và một output, có thể gọi `input.send(message)` và `output.receive()` mà không cần chỉ định tên. Khi có nhiều function hoặc nhiều binding, hãy chỉ định destination tường minh để tránh gửi nhầm luồng.

## 6. Chọn function bằng `spring.cloud.function.definition`

Nếu ứng dụng có nhiều bean `Supplier`, `Function` hoặc `Consumer`, hãy khai báo function cần kiểm thử bằng `spring.cloud.function.definition`.

Ví dụ:

```java
@SpringBootApplication
@EnableTestBinder
class MultiFunctionTestApplication {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }

    @Bean
    Function<String, String> reverse() {
        return value -> new StringBuilder(value).reverse().toString();
    }
}
```

Test context:

```java
@SpringBootTest(
    classes = MultiFunctionTestApplication.class,
    properties = "spring.cloud.function.definition=uppercase;reverse"
)
class MultiFunctionBinderTests {
    // inject InputDestination and OutputDestination
}
```

Khi chọn nhiều function, Spring Cloud Function cho phép khai báo danh sách function theo cú pháp definition. Nếu định nghĩa composition, hãy kiểm tra binding name được sinh ra cho pipeline đó và dùng đúng destination trong test.

## 7. Gửi message bằng `InputDestination`

`InputDestination` là điểm vào của message trong test. Một số cách gửi phổ biến:

```java
input.send("hello".getBytes(StandardCharsets.UTF_8));
```

Gửi một Spring `Message` có payload và header:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<byte[]> message = MessageBuilder
    .withPayload("hello".getBytes(StandardCharsets.UTF_8))
    .setHeader("correlationId", "corr-1001")
    .build();

input.send(message);
```

Gửi vào một destination cụ thể:

```java
input.send(message, "orders.input");
```

Tên truyền vào phải tương ứng với destination mà binding đang dùng. Nếu không khai báo `destination`, thường dùng binding name như `processOrder-in-0`. Nếu cấu hình:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.input
```

thì bài test gửi vào `orders.input`:

```java
input.send(message, "orders.input");
```

Không mặc định rằng tên binding và destination luôn giống nhau. Khi có mapping tùy chỉnh, sử dụng tên destination được cấu hình.

## 8. Nhận message bằng `OutputDestination`

`OutputDestination` giữ message được phát ra từ output binding để test có thể xác minh.

Nhận message từ output mặc định:

```java
Message<byte[]> result = output.receive(1_000L);
```

Nhận từ output cụ thể:

```java
Message<byte[]> result = output.receive(1_000L, "orders.output");
```

Nếu binding có destination:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-out-0:
          destination: orders.output
```

thì dùng tên `orders.output` khi nhận message. Với nhiều output, hãy chỉ định destination để không lấy nhầm message từ output khác.

Payload trả về thường được đọc dưới dạng `byte[]`. Chuyển bytes về kiểu dữ liệu cần kiểm tra bằng charset rõ ràng:

```java
String body = new String(result.getPayload(), StandardCharsets.UTF_8);
assertThat(body).isEqualTo("ORDER-1001");
```

Tránh dùng charset mặc định của máy vì kết quả có thể khác giữa các môi trường chạy test.

## 9. Cấu hình destination riêng trong test

Một function có thể đọc và ghi topic/destination có tên rõ ràng:

```yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: text.in
        uppercase-out-0:
          destination: text.out
```

Test:

```java
@Test
void usesConfiguredDestinations() {
    Message<byte[]> message = MessageBuilder
        .withPayload("hello".getBytes(StandardCharsets.UTF_8))
        .build();

    input.send(message, "text.in");

    Message<byte[]> result = output.receive(1_000L, "text.out");

    assertThat(result).isNotNull();
    assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
        .isEqualTo("HELLO");
}
```

Kỹ thuật này hữu ích khi tên destination của production không trùng tên binding mặc định hoặc khi test nhiều function trong cùng một context.

## 10. Kiểm thử nhiều function trong cùng test suite

Khi test nhiều function, mỗi function có input/output riêng. Hãy gửi và nhận theo đúng destination tương ứng.

```java
@Test
void testsTwoFunctions() {
    Message<byte[]> message = MessageBuilder
        .withPayload("Hello".getBytes(StandardCharsets.UTF_8))
        .build();

    input.send(message, "uppercase-in-0");
    input.send(message, "reverse-in-0");

    Message<byte[]> upper = output.receive(1_000L, "uppercase-out-0");
    Message<byte[]> reversed = output.receive(1_000L, "reverse-out-0");

    assertThat(new String(upper.getPayload(), StandardCharsets.UTF_8))
        .isEqualTo("HELLO");
    assertThat(new String(reversed.getPayload(), StandardCharsets.UTF_8))
        .isEqualTo("olleH");
}
```

Nếu các function được map sang destination riêng, thay tên binding bằng destination đã cấu hình. Không dựa vào thứ tự message trong một output dùng chung nếu ứng dụng thực tế có nhiều luồng độc lập.

## 11. Kiểm tra payload và header

Test Binder cho phép xác minh cả payload lẫn header của message. Điều này hữu ích với correlation ID, event type, content type hoặc metadata nghiệp vụ.

Ví dụ function nhận `Message<String>` và giữ header correlation:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<String>, Message<String>> annotateOrder() {
    return message -> MessageBuilder
        .withPayload(message.getPayload().toUpperCase())
        .copyHeaders(message.getHeaders())
        .setHeader("processed", true)
        .build();
}
```

Test:

```java
Message<String> inputMessage = MessageBuilder
    .withPayload("order-created")
    .setHeader("correlationId", "corr-2001")
    .build();

input.send(inputMessage);

Message<byte[]> result = output.receive(1_000L);

assertThat(result).isNotNull();
assertThat(result.getHeaders().get("correlationId"))
    .isEqualTo("corr-2001");
assertThat(result.getHeaders().get("processed"))
    .isEqualTo(true);
```

Khi kiểm thử header có kiểu hoặc nội dung cụ thể, hãy xác minh header thực tế sau quá trình message conversion. Không giả định mọi header nội bộ của framework đều được giữ nguyên qua mọi binder.

## 12. Kiểm thử Consumer không có output

`Consumer<T>` nhận message nhưng không trả về output binding. Test có thể xác minh tác động nghiệp vụ thông qua một bean collaborator hoặc trạng thái test.

Ví dụ:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTestBinder
class OrderConsumerTestApplication {

    @Bean
    OrderRecorder orderRecorder() {
        return new OrderRecorder();
    }

    @Bean
    Consumer<String> recordOrder(OrderRecorder recorder) {
        return recorder::record;
    }
}

class OrderRecorder {
    private final List<String> orders = new CopyOnWriteArrayList<>();

    void record(String orderId) {
        orders.add(orderId);
    }

    List<String> orders() {
        return List.copyOf(orders);
    }
}
```

Test gửi message vào `recordOrder-in-0`, sau đó xác minh `OrderRecorder` đã ghi nhận dữ liệu. Với xử lý bất đồng bộ, dùng cơ chế chờ có timeout thay vì gọi `Thread.sleep` với một khoảng thời gian cố định.

Consumer không có output thì `OutputDestination` không phải nơi để xác minh kết quả nghiệp vụ. Hãy kiểm tra collaborator, repository giả lập, event được phát tiếp hoặc trạng thái được cập nhật.

## 13. Kiểm thử Supplier phát message

`Supplier<T>` tạo dữ liệu và gửi ra output binding. Có thể dùng `OutputDestination` để nhận message do supplier phát ra.

Ví dụ supplier:

```java
@Bean
Supplier<String> publishHeartbeat() {
    return () -> "heartbeat";
}
```

Supplier thường được kích hoạt theo cơ chế polling của framework. Trong test, cần kiểm soát thời điểm phát message hoặc cấu hình poller để bài test ổn định. Không nên giả định message đã có ngay khi ApplicationContext vừa khởi động.

Với test cần xác minh output của supplier, chờ có timeout:

```java
Message<byte[]> result = output.receive(2_000L, "publishHeartbeat-out-0");
assertThat(result).isNotNull();
```

Nếu supplier tạo dữ liệu theo thời gian hoặc có side effect, hãy tách phần tạo dữ liệu thành collaborator có thể kiểm soát trong test. Điều này giúp test không phụ thuộc vào lịch poller hoặc thời gian thực.

## 14. Test Binder và `StreamBridge`

Ứng dụng có thể gửi message động bằng `StreamBridge` thay vì chỉ dựa vào output của một function bean. Khi Test Binder được bật, output destination vẫn có thể nhận message được gửi qua binding name hoặc destination đã cấu hình.

Ví dụ:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.stream.function.StreamBridge;

@Bean
ApplicationRunner publishEvent(StreamBridge streamBridge) {
    return args -> streamBridge.send("orders-out-0", "order-created");
}
```

Trong test, nhận message từ destination tương ứng:

```java
Message<byte[]> result = output.receive(1_000L, "orders-out-0");
assertThat(result).isNotNull();
```

Nếu dùng `StreamBridge.send` với tên binding đã map đến destination, hãy dùng đúng destination khi nhận. Với code gửi động, nên kiểm tra cả giá trị trả về của `send` và nội dung message nhận được.

## 15. `@EnableTestBinder` và cách tạo context thủ công

Phần lớn test Spring Boot chỉ cần `@SpringBootTest` cùng `@EnableTestBinder`. Khi cần tạo nhiều context độc lập hoặc truyền properties khác nhau cho từng test, có thể khởi động context thủ công bằng `SpringApplicationBuilder` và cấu hình Test Binder.

Ví dụ cấu hình function:

```java
@EnableAutoConfiguration
class UppercaseTestConfiguration {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }
}
```

Khởi tạo context bằng cấu hình đầy đủ của Test Binder:

```java
try (ConfigurableApplicationContext context = new SpringApplicationBuilder(
        TestChannelBinderConfiguration.getCompleteConfiguration(
            UppercaseTestConfiguration.class))
        .run("--spring.cloud.function.definition=uppercase")) {

    InputDestination input = context.getBean(InputDestination.class);
    OutputDestination output = context.getBean(OutputDestination.class);

    input.send("hello".getBytes(StandardCharsets.UTF_8));
    Message<byte[]> result = output.receive(1_000L);

    assertThat(result).isNotNull();
}
```

Đây là cách kiểm soát context ở mức thấp hơn. Khi dùng `@EnableTestBinder` theo kiểu Spring Boot test thông thường, không cần tự gọi `TestChannelBinderConfiguration.getCompleteConfiguration` thêm lần nữa. Chọn một cách khởi tạo context phù hợp để tránh đăng ký cấu hình test binder trùng lặp.

## 16. Phân biệt Test Binder hiện tại với test support cũ

Các phiên bản Spring Cloud Stream cũ từng cung cấp `spring-cloud-stream-test-support` và `TestSupportBinder`, thường được kiểm thử bằng `MessageCollector` và các channel kiểu cũ. Test Binder hiện tại dùng dependency:

```text
org.springframework.cloud:spring-cloud-stream-test-binder
```

và API `@EnableTestBinder`, `InputDestination`, `OutputDestination`.

| Thành phần | Test Binder hiện tại | Test support cũ |
|---|---|---|
| Dependency | `spring-cloud-stream-test-binder` | `spring-cloud-stream-test-support` |
| Cách kích hoạt | `@EnableTestBinder` hoặc cấu hình Test Binder tương ứng của phiên bản | Auto-configuration TestSupportBinder |
| API kiểm thử thường gặp | `InputDestination`, `OutputDestination` | `MessageCollector`, channel binding cũ |
| Mục tiêu | Kiểm thử functional model và binding qua Test Binder trong JVM | Hỗ trợ test mô hình channel/binding cũ |

Không trộn hướng dẫn của hai thế hệ trong cùng một bài test. Nếu dự án đang dùng Spring Cloud Stream phiên bản cũ, hãy xem đúng tài liệu của release train đó trước khi đổi dependency hoặc annotation. Khi nâng cấp, chuyển test sang API mới một cách có chủ đích và bỏ dependency cũ nếu không còn dùng.

## 17. Test Binder khi có binder Kafka/RabbitMQ/Pulsar trên classpath

Một ứng dụng production có thể khai báo binder thật như Kafka, RabbitMQ hoặc Pulsar. Test Binder được thêm với scope `test` để dùng trong test context. Hãy bảo đảm test đang khởi tạo Test Binder theo cấu hình đã chọn và không vô tình kết nối broker production.

Khi Test Binder nằm trên test classpath của một module, Spring Cloud Stream sẽ ưu tiên Test Binder cho các binding trong các test context dùng cấu hình đó. Không thể kỳ vọng một số test trong cùng module tự chuyển sang binder thật chỉ bằng cách đổi profile trong khi Test Binder vẫn hiện diện trên test classpath. Nếu cần chạy integration test với Kafka/RabbitMQ/Pulsar thật, tổ chức chúng trong module riêng hoặc cấu hình build riêng không đưa Test Binder vào test classpath của nhóm test đó.

Nếu ứng dụng có nhiều binder trên classpath, cần hiểu cơ chế binder selection của phiên bản Spring Cloud Stream đang dùng. Với test thông thường, bật `@EnableTestBinder` trên context kiểm thử và xác minh log/context đang dùng đúng Test Binder. Nếu cấu hình nhiều binder phức tạp, hãy tách test context để tránh cấu hình mặc định không rõ ràng.

## 18. Test Binder không thay thế broker integration test

Test Binder rất hữu ích để kiểm tra phần xử lý message trong ứng dụng, nhưng không thực hiện đầy đủ hành vi của broker thật.

| Nội dung | Test Binder | Cần broker thật để xác minh? |
|---|---|---|
| Function nhận và biến đổi payload | Có | Không bắt buộc |
| Function/Consumer được kích hoạt qua input binding | Có | Không bắt buộc |
| Output binding phát đúng payload/header ở mức framework | Có | Không bắt buộc |
| Destination mapping cơ bản | Có | Không bắt buộc |
| Kafka partition assignment và consumer group rebalance | Không mô phỏng semantics Kafka đầy đủ | Có |
| RabbitMQ exchange, queue, routing key và DLQ | Không mô phỏng topology RabbitMQ thật | Có |
| Pulsar tenant, namespace, subscription và partition | Không mô phỏng quản trị/broker Pulsar | Có |
| TLS, SASL, token, ACL và network failure | Không | Có môi trường tương thích |
| Transaction và delivery guarantee đặc thù broker | Không thể xác minh đầy đủ | Có |
| Broker retry, redelivery, dead-letter policy | Không thay thế được broker | Có |

Một chiến lược kiểm thử hợp lý gồm test logic/function với Test Binder và một số integration test với đúng binder/broker cần triển khai. Không coi việc test binder pass là bằng chứng Kafka, RabbitMQ hoặc Pulsar đã được cấu hình đúng.

## 19. Kiểm thử content type và message conversion

Spring Cloud Stream có thể chuyển đổi payload theo content type và cấu hình message converter. Test Binder cho phép kiểm tra hành vi chuyển đổi ở tầng Spring Cloud Stream.

Ví dụ cấu hình JSON:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.input
          content-type: application/json
        normalizeOrder-out-0:
          destination: orders.output
          content-type: application/json
```

Test có thể gửi JSON bytes và kiểm tra JSON output. Với payload JSON, hãy xác minh encoding UTF-8, cấu trúc field và kiểu dữ liệu. Nếu cần kiểm tra Serde của Kafka Streams hoặc schema registry, Test Binder thông thường không thay thế integration test của binder/Serde thật.

Không nhầm message conversion của Spring Cloud Stream với serializer/deserializer ở tầng Kafka hoặc schema encoding của Pulsar. Test Binder kiểm tra lớp framework mà nó chạy, không xác nhận mọi serializer của broker production.

## 20. Kiểm tra timeout và tính ổn định của test

Message processing có thể đồng bộ hoặc bất đồng bộ tùy function, executor, reactive pipeline và cấu hình. Để test ổn định:

- Dùng `receive(timeout)` với timeout hữu hạn.
- Kiểm tra message khác `null` trước khi truy cập payload.
- Tránh chờ vô hạn.
- Không dùng `Thread.sleep` dài để đoán lúc message xuất hiện.
- Nếu function phát nhiều message, nhận đúng số lượng và đúng destination.
- Không dùng chung một ApplicationContext có trạng thái message còn sót giữa các test mà không kiểm soát.
- Đặt tên destination tường minh khi có nhiều binding.

Nếu output không xuất hiện, kiểm tra function definition, binding name, destination, context có bật Test Binder và function có thực sự được kích hoạt hay không.

## 21. Các lỗi cấu hình thường gặp

| Lỗi | Triệu chứng | Cách khắc phục |
|---|---|---|
| Thiếu dependency test binder | Không có Test Binder hoặc không tạo được destination bean | Thêm `spring-cloud-stream-test-binder` với scope `test` |
| Dùng dependency cũ | Không tìm thấy `@EnableTestBinder` hoặc API destination mới | Dùng dependency đúng thế hệ Spring Cloud Stream |
| Quên `@EnableTestBinder` | Test context không bật Test Binder như mong muốn | Đặt annotation trên cấu hình thực sự được nạp |
| Test configuration không được import | Function bean không có trong context | Chỉ định đúng `classes` hoặc import configuration |
| Function không được chọn | Binding không được tạo hoặc function không chạy | Đặt `spring.cloud.function.definition` tường minh |
| Gửi nhầm binding/destination | Không có output hoặc nhận message từ luồng khác | Đối chiếu binding name và destination mapping |
| Dùng tên binding khi đã map destination | `InputDestination` không gửi đến input mong muốn | Gửi bằng tên destination đã cấu hình |
| Đọc sai output destination | `receive` trả về `null` | Dùng đúng destination của output binding |
| Thiếu timeout | Test treo hoặc lỗi khó chẩn đoán | Dùng `receive(timeout)` hữu hạn |
| Chạy test với broker thật ngoài ý muốn | Test cố kết nối Kafka/RabbitMQ/Pulsar | Kiểm tra test scope và Test Binder activation/context |
| Kỳ vọng Test Binder xác minh partition/DLQ | Test pass nhưng production broker vẫn có thể sai | Viết integration test với broker thật |
| Trộn `TestSupportBinder` cũ và Test Binder mới | Dependency/API không tương thích hoặc cấu hình khó hiểu | Chọn đúng thế hệ test API và loại dependency không dùng |

## 22. Checklist thiết lập Test Binder

Trước khi viết test:

1. Xác định phiên bản Spring Cloud Stream và Spring Boot tương thích.
2. Bảo đảm dependency management/BOM quản lý version nhất quán.
3. Thêm `spring-cloud-stream-test-binder` với scope `test`.
4. Thêm Spring Boot Test/JUnit nếu dự án chưa có.
5. Tạo test application/configuration có function bean cần kiểm tra.
6. Đặt `@EnableTestBinder` trên configuration được nạp trong test context.
7. Dùng `@SpringBootTest(classes = ...)` hoặc cách tạo context thủ công phù hợp.
8. Chọn function bằng `spring.cloud.function.definition` khi có nhiều function.
9. Inject `InputDestination` và `OutputDestination`.
10. Gửi message vào đúng input binding/destination.
11. Nhận output bằng timeout và đúng output destination.
12. Xác minh payload, header và kết quả nghiệp vụ.
13. Giữ test độc lập với broker bên ngoài.
14. Bổ sung integration test riêng khi cần xác minh semantics Kafka/RabbitMQ/Pulsar.

## 23. Ví dụ hoàn chỉnh: kiểm thử xử lý sự kiện đơn hàng

Ứng dụng nhận `OrderCreated`, chuẩn hóa mã đơn hàng rồi phát `OrderAccepted`.

```java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;

record OrderCreated(String eventId, String orderId) {}

record OrderAccepted(String eventId, String orderId, String status) {}

@SpringBootApplication
@EnableTestBinder
class OrderStreamTestApplication {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event -> new OrderAccepted(
            event.eventId(),
            event.orderId().trim().toUpperCase(),
            "ACCEPTED"
        );
    }
}
```

Cấu hình binding:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

Test gửi message JSON vào `orders.created`, sau đó đọc output từ `orders.accepted`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(classes = OrderStreamTestApplication.class)
class OrderStreamBinderTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void acceptsOrderAndPublishesEvent() {
        byte[] json = """
            {"eventId":"evt-1","orderId":" order-100 "}
            """.getBytes(StandardCharsets.UTF_8);

        input.send(MessageBuilder.withPayload(json).build(), "orders.created");

        Message<byte[]> result = output.receive(1_000L, "orders.accepted");

        assertThat(result).isNotNull();
        String body = new String(result.getPayload(), StandardCharsets.UTF_8);
        assertThat(body).contains("ORDER-100");
        assertThat(body).contains("ACCEPTED");
    }
}
```

Ví dụ minh họa cách ghép dependency, annotation, function bean, destination mapping và hai destination test. Trong dự án thực tế, hãy xác nhận Jackson/content-type converter được cấu hình tương ứng và dùng DTO/schema của ứng dụng. Nếu muốn kiểm tra JSON theo cấu trúc, deserialize kết quả về DTO hoặc dùng JSON assertion thay vì chỉ tìm chuỗi con.

## 24. Tự kiểm tra

- [ ] Thêm được `spring-cloud-stream-test-binder` với scope `test`.
- [ ] Giải thích được vì sao cần dependency management/BOM tương thích.
- [ ] Biết đặt `@EnableTestBinder` trên cấu hình được nạp trong test context.
- [ ] Giải thích được vai trò của `InputDestination` và `OutputDestination`.
- [ ] Khởi tạo được test bằng `@SpringBootTest`.
- [ ] Chọn được function bằng `spring.cloud.function.definition`.
- [ ] Gửi message vào binding mặc định và destination được cấu hình tường minh.
- [ ] Nhận message từ output bằng timeout và destination đúng.
- [ ] Kiểm tra được payload và header.
- [ ] Biết cách test nhiều function và consumer không có output.
- [ ] Phân biệt Test Binder hiện tại với `spring-cloud-stream-test-support` cũ.
- [ ] Giải thích được những hành vi broker mà Test Binder không mô phỏng.
- [ ] Xây dựng được integration test riêng cho Kafka, RabbitMQ hoặc Pulsar khi cần.

## Kết luận

Để thiết lập Spring Cloud Stream Test Binder, thêm `spring-cloud-stream-test-binder` trong scope `test` và bật `@EnableTestBinder` trên cấu hình được nạp bởi test context. `InputDestination` gửi message vào input binding; `OutputDestination` nhận message từ output binding. Kết hợp `@SpringBootTest`, `spring.cloud.function.definition` và destination mapping giúp kiểm thử function theo đúng luồng dữ liệu của ứng dụng mà không cần broker bên ngoài. Test Binder xác minh phần xử lý và binding ở trong JVM; các đặc tính broker như partition, consumer group, exchange/queue, subscription, retry/DLQ và giao nhận production cần được kiểm thử bổ sung với Kafka, RabbitMQ hoặc Pulsar thật.

## Tài liệu tham khảo

- Spring Cloud Stream 5.1 — Testing / Spring Integration Test Binder: https://docs.spring.io/spring-cloud-stream/reference/5.1/spring-cloud-stream/spring_integration_test_binder.html
- Spring Cloud Stream 5.0 — Testing: https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/spring_integration_test_binder.html
- Spring Cloud Stream — Reference Documentation: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream.html
