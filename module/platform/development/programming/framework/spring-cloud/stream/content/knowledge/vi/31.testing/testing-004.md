# Đọc và kiểm tra kết quả bằng OutputDestination

Khi kiểm thử ứng dụng Spring Cloud Stream, ta thường cần gửi một message vào input binding, để function xử lý, rồi xác nhận message được phát ra ở output binding. **OutputDestination** là API của Spring Cloud Stream test binder dùng để đọc các message đầu ra đó trong test.

Test binder chạy trong JVM và mô phỏng destination bằng các channel của Spring Integration. Nó cho phép kiểm tra luồng function và binding mà không cần khởi động Kafka, RabbitMQ hay Pulsar. Test thường kết hợp ba thành phần:

- **InputDestination:** gửi message vào input destination để kích hoạt consumer hoặc function.
- **Ứng dụng Spring Cloud Stream:** nhận message, gọi Supplier/Function/Consumer và phát output nếu có.
- **OutputDestination:** lấy message từ output destination để kiểm tra payload và header.

OutputDestination đặc biệt hữu ích khi kiểm tra function có output, nhiều output binding hoặc message được gửi bằng StreamBridge. Nó giúp kiểm tra kết quả ở ranh giới binding thay vì chỉ gọi trực tiếp method Java.

## 1. Test binder và vị trí của OutputDestination

Trong ứng dụng thực tế, binder kết nối binding với Kafka topic, RabbitMQ exchange/queue hoặc Pulsar topic. Khi dùng test binder, các kết nối này được thay bằng một broker in-memory dựa trên Spring Integration.

~~~text
                  Test trong JVM
+----------------------------------------------------+
| InputDestination                                  |
|       |                                            |
|       v                                            |
| input binding                                      |
|       |                                            |
|       v                                            |
| Function / Consumer                                |
|       |                                            |
|       v                                            |
| output binding                                     |
|       |                                            |
|       v                                            |
| OutputDestination ---> Message để assertion       |
+----------------------------------------------------+

Không cần kết nối Kafka / RabbitMQ / Pulsar
~~~

OutputDestination nhận các message được ứng dụng gửi qua output binding. Test có thể kiểm tra:

- Có message được phát ra hay không.
- Payload có đúng nội dung và kiểu dữ liệu mong muốn không.
- Message có đúng output destination không.
- Header nghiệp vụ có được tạo hoặc giữ lại không.
- Nhiều message có được phát ra đúng số lượng và thứ tự mong muốn trong phạm vi test không.

Test binder không chạy broker thật. Nó không xác minh Kafka partition, RabbitMQ routing, Pulsar subscription, broker acknowledgement, serialization của binder cụ thể hay cấu hình retry/DLQ ở broker. Các hành vi đó cần integration test riêng với binder và broker tương ứng.

## 2. Thêm dependency cho test binder

Với Spring Cloud Stream hiện đại, dùng dependency `spring-cloud-stream-test-binder` trong scope test.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
}
~~~

Để dependency management của Spring Cloud BOM quản lý phiên bản, tránh tự ghim phiên bản test binder khác với phiên bản Spring Cloud Stream của ứng dụng.

Test binder thay thế binder middleware khi được nạp trong test context. Vì vậy không đặt dependency test binder ở runtime hoặc production classpath. Nếu test cần kết nối broker thật, cấu hình test riêng để dùng binder thật và broker thử nghiệm.

Các ví dụ dưới đây sử dụng JUnit Jupiter, AssertJ và Spring Boot Test.

## 3. Kích hoạt test binder bằng @EnableTestBinder

Test class cần khởi tạo Spring application context có test binder. Cách thông dụng là dùng `@SpringBootTest` kết hợp `@EnableTestBinder`.

Ví dụ ứng dụng có function chuyển chuỗi thành chữ hoa:

~~~java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TextApplication {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(classes = TextApplication.class)
@EnableTestBinder
class TextApplicationTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void convertsInputAndReadsOutput() {
        input.send(new GenericMessage<>(
            "hello".getBytes(StandardCharsets.UTF_8)
        ));

        Message<byte[]> result = output.receive();

        assertThat(result).isNotNull();
        assertThat(new String(
            result.getPayload(),
            StandardCharsets.UTF_8
        )).isEqualTo("HELLO");
    }
}
~~~

Luồng kiểm thử:

1. Spring khởi động application context và phát hiện function bean `uppercase`.
2. Test binder tạo input/output binding cho function.
3. InputDestination gửi payload `hello` vào input.
4. Spring Cloud Stream chuyển đổi payload phù hợp với kiểu đầu vào của function.
5. Function trả về `HELLO`.
6. Test binder đưa output message vào hàng đợi của output destination.
7. OutputDestination lấy message để test assertion.

Trong ví dụ này, output được đọc dưới dạng `Message<byte[]>`. Hãy giải mã bytes bằng charset tường minh như UTF-8 khi so sánh chuỗi. Không dùng charset mặc định của máy chạy test vì kết quả có thể khác giữa môi trường.

## 4. Binding name và destination name

Một điểm rất dễ gây lỗi là nhầm tên binding với tên destination.

Với function tên `uppercase`, Spring Cloud Stream tạo binding mặc định:

| Binding | Tên mặc định |
|---|---|
| Input | `uppercase-in-0` |
| Output | `uppercase-out-0` |

Nếu không khai báo destination riêng, tên destination thường trùng với binding name. Khi đó có thể gọi:

~~~java
input.send(message, "uppercase-in-0");
Message<byte[]> result =
    output.receive(1000, "uppercase-out-0");
~~~

Nếu cấu hình destination riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase

    stream:
      bindings:
        uppercase-in-0:
          destination: orders-to-normalize

        uppercase-out-0:
          destination: orders-normalized
~~~

Thì test gửi và nhận bằng tên destination đã ánh xạ:

~~~java
input.send(message, "orders-to-normalize");

Message<byte[]> result =
    output.receive(1000, "orders-normalized");
~~~

Ở đây `orders-to-normalize` và `orders-normalized` là destination; `uppercase-in-0` và `uppercase-out-0` là binding name. Khi đã đặt destination riêng, hãy dùng tên destination trong các overload có tham số tên của InputDestination và OutputDestination.

Quy tắc nhớ nhanh:

- Không cấu hình destination riêng: dùng tên binding mặc định.
- Có cấu hình destination riêng: dùng tên destination đã cấu hình.
- Nhiều output: luôn chỉ rõ output destination cần đọc.

## 5. Đọc output bằng receive()

OutputDestination cung cấp các cách đọc message:

~~~java
Message<byte[]> result = output.receive();
~~~

Đọc message từ output mặc định. Cách này tiện khi ứng dụng chỉ có một output binding.

~~~java
Message<byte[]> result =
    output.receive(1000, "orders-normalized");
~~~

Đọc từ destination được chỉ định và chờ tối đa khoảng thời gian timeout truyền vào. Đơn vị timeout là millisecond. Nếu không có message trong khoảng chờ, kết quả là `null`.

Luôn kiểm tra kết quả trước khi đọc payload:

~~~java
Message<byte[]> result =
    output.receive(1000, "orders-normalized");

assertThat(result)
    .as("ứng dụng phải phát một message tới orders-normalized")
    .isNotNull();

assertThat(result.getPayload())
    .isNotEmpty();
~~~

Không gọi `result.getPayload()` ngay khi chưa xác nhận result khác null. Nếu function không phát output hoặc test đọc nhầm destination, kết quả null sẽ gây NullPointerException và làm khó xác định nguyên nhân thật.

Mỗi lần receive lấy một message khỏi destination của test binder. Nếu function phát nhiều message, gọi receive tương ứng với số message cần kiểm tra. Không đọc cùng một message lần thứ hai rồi kỳ vọng nhận lại nó.

## 6. Kiểm tra payload và kiểu dữ liệu

OutputDestination trả về Message, nên assertion nên kiểm tra cả sự tồn tại của message và nội dung payload.

Với payload String:

~~~java
Message<byte[]> result =
    output.receive(1000, "uppercase-out-0");

assertThat(result).isNotNull();

String body = new String(
    result.getPayload(),
    StandardCharsets.UTF_8
);

assertThat(body).isEqualTo("HELLO");
~~~

Với payload JSON, có thể dùng Jackson ObjectMapper để đọc bytes thành DTO:

~~~java
public record OrderSummary(
    String orderId,
    String status,
    long total
) {}
~~~

~~~java
Message<byte[]> result =
    output.receive(1000, "order-summary-out-0");

assertThat(result).isNotNull();

OrderSummary summary = objectMapper.readValue(
    result.getPayload(),
    OrderSummary.class
);

assertThat(summary.orderId()).isEqualTo("order-1001");
assertThat(summary.status()).isEqualTo("ACCEPTED");
assertThat(summary.total()).isEqualTo(250_000L);
~~~

Đoạn test JSON giả định output converter của ứng dụng đã serialize DTO thành JSON. Nếu dùng native encoding hoặc custom Serde, cách biểu diễn payload có thể khác. Hãy kiểm tra đúng định dạng mà function/binding thực tế phát ra.

Không chỉ assert rằng message khác null. Một test có ý nghĩa cần kiểm tra giá trị nghiệp vụ quan trọng: ID, trạng thái, tổng tiền, loại event hoặc các trường bắt buộc.

## 7. Kiểm tra header của output message

Message trong Spring Cloud Stream gồm payload và headers. Khi logic nghiệp vụ tạo correlation ID, event type hoặc dấu vết xử lý, có thể kiểm tra chúng từ Message nhận được.

Ví dụ function nhận message, chuẩn hóa payload và thêm header:

~~~java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
public class OrderConfiguration {

    @Bean
    Function<Message<String>, Message<String>> normalizeOrder() {
        return input -> MessageBuilder
            .fromMessage(input)
            .setPayload(input.getPayload().trim().toUpperCase())
            .setHeader("processedBy", "order-normalizer")
            .build();
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(
    classes = OrderConfiguration.class,
    properties = {
        "spring.cloud.function.definition=normalizeOrder"
    }
)
@EnableTestBinder
class OrderHeaderTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void preservesCorrelationAndAddsProcessingHeader() {
        Message<byte[]> incoming = MessageBuilder
            .withPayload("  paid  ".getBytes(StandardCharsets.UTF_8))
            .setHeader(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.TEXT_PLAIN
            )
            .setHeader("correlationId", "corr-1001")
            .build();

        input.send(incoming, "normalizeOrder-in-0");

        Message<byte[]> result =
            output.receive(1000, "normalizeOrder-out-0");

        assertThat(result).isNotNull();
        assertThat(new String(
            result.getPayload(),
            StandardCharsets.UTF_8
        )).isEqualTo("PAID");

        assertThat(result.getHeaders().get("correlationId"))
            .isEqualTo("corr-1001");

        assertThat(result.getHeaders().get("processedBy"))
            .isEqualTo("order-normalizer");
    }
}
~~~

Header `contentType` giúp framework chọn cơ chế chuyển đổi phù hợp. Header `correlationId` được đưa vào message đầu vào để kiểm tra việc truyền ngữ cảnh. Header `processedBy` do function tạo ra.

Test binder chạy trong JVM nên phù hợp để xác nhận hành vi xử lý message của ứng dụng. Khi dùng Kafka, RabbitMQ hoặc Pulsar binder thật, việc header được truyền qua broker còn phụ thuộc header mapper và cấu hình của binder. Cần kiểm thử riêng nếu header là contract liên dịch vụ.

## 8. Nhiều output binding: chọn đúng destination khi đọc

Một ứng dụng có thể kích hoạt nhiều function trong cùng context. Mỗi function có input/output riêng.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextFunctions {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }

    @Bean
    Function<String, String> reverse() {
        return value -> new StringBuilder(value).reverse().toString();
    }
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase;reverse
~~~

Test:

~~~java
@Test
void readsTheExpectedOutputForEachFunction() {
    Message<byte[]> inputMessage = new GenericMessage<>(
        "Hello".getBytes(StandardCharsets.UTF_8)
    );

    input.send(inputMessage, "uppercase-in-0");
    input.send(inputMessage, "reverse-in-0");

    Message<byte[]> uppercaseResult =
        output.receive(1000, "uppercase-out-0");

    Message<byte[]> reverseResult =
        output.receive(1000, "reverse-out-0");

    assertThat(uppercaseResult).isNotNull();
    assertThat(reverseResult).isNotNull();

    assertThat(new String(
        uppercaseResult.getPayload(),
        StandardCharsets.UTF_8
    )).isEqualTo("HELLO");

    assertThat(new String(
        reverseResult.getPayload(),
        StandardCharsets.UTF_8
    )).isEqualTo("olleH");
}
~~~

Nếu chỉ gọi `output.receive()` trong test nhiều output, test có thể đọc message từ destination mặc định thay vì output mà bạn muốn kiểm tra. Gọi receive với tên destination rõ ràng giúp test không phụ thuộc thứ tự tạo binding.

Nếu cấu hình destination riêng cho function:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        uppercase-in-0:
          destination: text-input
        uppercase-out-0:
          destination: uppercase-result
~~~

Thì gọi:

~~~java
input.send(inputMessage, "text-input");

Message<byte[]> result =
    output.receive(1000, "uppercase-result");
~~~

Tên truyền vào receive phải là destination thực tế khi binding đã được ánh xạ sang destination khác.

## 9. Nhiều input của một function

Function có nhiều input, ví dụ BiFunction, tạo nhiều input binding:

~~~java
import java.util.function.BiFunction;

@Bean
BiFunction<String, String, String> combine() {
    return (left, right) -> left + ":" + right;
}
~~~

Binding mặc định:

- `combine-in-0`: input thứ nhất.
- `combine-in-1`: input thứ hai.
- `combine-out-0`: output.

Test gửi từng input vào đúng destination:

~~~java
input.send(
    new GenericMessage<>("order-1001".getBytes(StandardCharsets.UTF_8)),
    "combine-in-0"
);

input.send(
    new GenericMessage<>("PAID".getBytes(StandardCharsets.UTF_8)),
    "combine-in-1"
);

Message<byte[]> result =
    output.receive(1000, "combine-out-0");

assertThat(result).isNotNull();

assertThat(new String(
    result.getPayload(),
    StandardCharsets.UTF_8
)).isEqualTo("order-1001:PAID");
~~~

Function nhiều input có thể phụ thuộc vào thời điểm nhận message và cơ chế ghép dữ liệu. Ví dụ trên minh họa trường hợp đơn giản. Với các luồng cần đồng bộ theo key hoặc thời gian, hãy kiểm tra semantics join/aggregation của function hoặc binder cụ thể.

## 10. Kiểm tra nhiều message trên cùng output

Một function có thể phát nhiều output message cho một input, ví dụ Function trả về Flux hoặc Publisher. OutputDestination giữ từng message để test đọc lần lượt.

~~~java
import java.util.function.Function;

import reactor.core.publisher.Flux;

@Bean
Function<String, Flux<String>> splitWords() {
    return value -> Flux.fromArray(value.split(" "));
}
~~~

Test:

~~~java
input.send(new GenericMessage<>(
    "spring cloud stream".getBytes(StandardCharsets.UTF_8)
));

Message<byte[]> first =
    output.receive(1000, "splitWords-out-0");

Message<byte[]> second =
    output.receive(1000, "splitWords-out-0");

Message<byte[]> third =
    output.receive(1000, "splitWords-out-0");

assertThat(first).isNotNull();
assertThat(second).isNotNull();
assertThat(third).isNotNull();

assertThat(new String(first.getPayload(), StandardCharsets.UTF_8))
    .isEqualTo("spring");

assertThat(new String(second.getPayload(), StandardCharsets.UTF_8))
    .isEqualTo("cloud");

assertThat(new String(third.getPayload(), StandardCharsets.UTF_8))
    .isEqualTo("stream");
~~~

Nếu thứ tự message là yêu cầu nghiệp vụ, hãy assertion theo đúng thứ tự. Nếu binder hoặc topology cho phép xử lý song song và thứ tự không được bảo đảm, kiểm tra tập kết quả thay vì giả định thứ tự cố định.

Với reactive function, cần để ý subscription và thời điểm phát message. OutputDestination có timeout hữu hạn giúp test chờ message trong khoảng thời gian xác định thay vì đọc ngay khi xử lý bất đồng bộ chưa hoàn tất.

## 11. Consumer không có output thì kiểm tra thế nào?

Consumer có kiểu trả về void:

~~~java
@Bean
Consumer<OrderCreated> recordOrder(OrderService orderService) {
    return order -> orderService.record(order);
}
~~~

Consumer không tạo output binding. Vì vậy OutputDestination không có message để đọc chỉ vì Consumer đã chạy.

Với Consumer, nên kiểm tra side effect bằng mock hoặc fake dependency:

~~~java
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.verify;

import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
OrderService orderService;

@Test
void invokesOrderService() {
    input.send(orderMessage, "recordOrder-in-0");

    verify(orderService).record(
        argThat(order -> order.orderId().equals("order-1001"))
    );
}
~~~

Ví dụ giả định `OrderService`, `OrderCreated` và `orderMessage` đã được khai báo trong test fixture. `@MockitoBean` có trong Spring Framework 6.2 trở lên; với stack cũ hơn, dùng `@MockBean` của Spring Boot nếu phiên bản dự án còn hỗ trợ.

Nếu Consumer gọi StreamBridge để phát message sang một output destination khác, OutputDestination vẫn có thể kiểm tra message được gửi tới output đó. Khi đó cần khai báo hoặc định tuyến đúng output binding và đọc theo destination tương ứng.

## 12. Đọc output do StreamBridge gửi

StreamBridge dùng khi dữ liệu đầu vào đến từ một nguồn ngoài function binding hoặc khi ứng dụng muốn gửi message động tới output binding.

Ví dụ:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private final StreamBridge streamBridge;

    public NotificationPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String notification) {
        return streamBridge.send("notification-out-0", notification);
    }
}
~~~

Cấu hình output destination:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: notification-out-0

      bindings:
        notification-out-0:
          destination: notifications
~~~

Test gọi service hoặc gửi message qua StreamBridge, sau đó đọc output:

~~~java
@Test
void readsStreamBridgeOutput() {
    boolean sent = notificationPublisher.publish("order paid");

    assertThat(sent).isTrue();

    Message<byte[]> result =
        output.receive(1000, "notifications");

    assertThat(result).isNotNull();

    assertThat(new String(
        result.getPayload(),
        StandardCharsets.UTF_8
    )).isEqualTo("order paid");
}
~~~

Giá trị boolean từ StreamBridge cho biết việc gửi message vào output channel có thành công hay không. Nó không thay thế assertion trên message thực tế. Hãy kiểm tra cả kết quả gửi và nội dung nhận được.

Nếu dùng dynamic destination, test cần biết chính xác tên destination mà StreamBridge đã tạo hoặc được cấu hình. Không đọc một output name khác với tên mà code gửi tới.

## 13. Kiểm tra trường hợp không có output

Có những đường xử lý hợp lệ không phát message, ví dụ function lọc bỏ event không thỏa điều kiện.

~~~java
import java.util.function.Function;

import reactor.core.publisher.Flux;

@Bean
Function<String, Flux<String>> acceptPaidOrder() {
    return status -> "PAID".equals(status)
        ? Flux.just(status)
        : Flux.empty();
}
~~~

Với reactive output, `Flux.empty()` biểu thị không phát message. Test có thể xác nhận destination không nhận output:

~~~java
input.send(new GenericMessage<>(
    "CANCELLED".getBytes(StandardCharsets.UTF_8)
));

Message<byte[]> result =
    output.receive(100, "acceptPaidOrder-out-0");

assertThat(result).isNull();
~~~

Dùng timeout ngắn cho assertion không có message. Không dùng timeout dài không cần thiết vì test sẽ chậm. Cũng không coi timeout là bằng chứng duy nhất về logic: cần có assertion riêng chứng minh input đã được gửi và điều kiện lọc hoạt động đúng.

Nếu function ném exception, kết quả phụ thuộc error handling, retry và cấu hình binder. Không gộp trường hợp exception với trường hợp function chủ động không phát output.

## 14. Kiểm tra output khi xử lý bất đồng bộ

Một số ứng dụng xử lý message trên executor hoặc reactive pipeline. Khi đó input.send có thể hoàn tất trước khi output được phát.

Dùng timeout hữu hạn của OutputDestination:

~~~java
Message<byte[]> result =
    output.receive(5000, "orders-out");

assertThat(result)
    .as("output phải xuất hiện trong 5 giây")
    .isNotNull();
~~~

Timeout cần đủ cho pipeline test nhưng không quá dài để che giấu lỗi. Nếu test thường xuyên phải chờ hết timeout, hãy kiểm tra:

- Function có được kích hoạt trong `spring.cloud.function.definition` không.
- Input có gửi đúng destination không.
- Output có đọc đúng destination không.
- Có exception trong function không.
- Có executor hoặc scheduler nào chưa được kích hoạt không.
- Reactive pipeline có được subscribe không.
- Có dependency bất đồng bộ nào cần mock hoặc đồng bộ hóa không.

Không dùng `Thread.sleep` như cách đồng bộ mặc định. Chờ output bằng API có timeout thường dễ đọc và ổn định hơn. Nếu cần chờ nhiều side effect khác nhau, dùng Awaitility hoặc đồng bộ hóa theo điều kiện rõ ràng.

## 15. Kiểm tra content type và message conversion

Spring Cloud Stream có thể chuyển đổi payload dựa trên content type. Một message được gửi dưới dạng byte[] có thể được function nhận dưới dạng String hoặc DTO tùy header và converter.

Ví dụ gửi text/plain:

~~~java
Message<byte[]> message = MessageBuilder
    .withPayload("hello".getBytes(StandardCharsets.UTF_8))
    .setHeader(
        MessageHeaders.CONTENT_TYPE,
        MimeTypeUtils.TEXT_PLAIN
    )
    .build();

input.send(message, "text-input");
~~~

Nếu function nhận DTO JSON, gửi message có content type application/json và payload JSON:

~~~java
String json = """
    {
      "orderId": "order-1001",
      "status": "PAID"
    }
    """;

Message<byte[]> message = MessageBuilder
    .withPayload(json.getBytes(StandardCharsets.UTF_8))
    .setHeader(
        MessageHeaders.CONTENT_TYPE,
        MimeTypeUtils.APPLICATION_JSON
    )
    .build();

input.send(message, "orders-in");
~~~

Sau đó đọc output bytes và deserialize theo content type/DTO mà output function tạo ra.

Khi test lỗi conversion, hãy kiểm tra ba yếu tố riêng:

1. Kiểu Java mà function khai báo.
2. Payload thực tế được gửi vào InputDestination.
3. Header contentType của message.

Nếu một trong ba không khớp, lỗi có thể xuất hiện trước khi function được gọi. Điều đó khác với lỗi logic bên trong function.

## 16. Cô lập test và xử lý message còn tồn đọng

OutputDestination là bean gắn với test application context. Các message được giữ trong destination queue cho đến khi test đọc chúng hoặc context kết thúc.

Để test ổn định:

- Mỗi test nên gửi input và đọc hết output mà nó tạo ra.
- Không dùng chung output destination giữa các test mà không kiểm soát message còn lại.
- Đọc đúng destination khi có nhiều function.
- Không để test phụ thuộc vào thứ tự thực thi của các test method.
- Dùng application context riêng khi cấu hình binding của các test khác nhau đáng kể.
- Nếu một test phát nhiều message, đọc đủ số message hoặc xác nhận số lượng mong đợi.

Không dùng reflection để truy cập channel nội bộ của InputDestination/OutputDestination. API công khai đã hỗ trợ send/receive theo destination name. Truy cập field nội bộ làm test phụ thuộc implementation và dễ hỏng khi nâng phiên bản.

## 17. Test binder và integration test với broker thật

Test binder xác minh application flow trong JVM. Nó không thay thế kiểm thử tích hợp với broker thật.

| Nội dung | Test binder + OutputDestination | Integration test với broker |
|---|---|---|
| Function transformation | Có | Có |
| Input/output binding wiring ở mức test binder | Có | Có |
| Payload và header ở luồng trong JVM | Có | Có |
| Kafka partition và consumer group | Không | Có |
| Rabbit exchange, queue và routing key | Không | Có |
| Pulsar subscription type và backlog | Không | Có |
| Broker serialization và native header mapping | Không đầy đủ | Có |
| Retry/DLQ của binder cụ thể | Không xác minh đầy đủ | Có |
| Network, authentication và broker permissions | Không | Có |

Khi cần xác minh broker, tạo test riêng dùng Kafka Testcontainers/Embedded Kafka, RabbitMQ Testcontainers hoặc Pulsar Testcontainers. Dùng binder thật trong test context đó và gửi/nhận message qua broker thực.

Tài liệu Spring Cloud Stream lưu ý test binder hoạt động như in-JVM broker. Khi test binder nằm trên test classpath, nó được dùng cho mục đích test thay cho binder middleware. Vì vậy không nên kỳ vọng một test vừa dùng OutputDestination in-memory vừa xác minh message đã đi qua Kafka/RabbitMQ/Pulsar thật.

Một chiến lược kiểm thử hợp lý:

1. Unit test function logic trực tiếp với input/output Java.
2. Test binder test binding flow bằng InputDestination và OutputDestination.
3. Integration test với broker thật để xác minh cấu hình binder, serialization, partition/subscription, retry và acknowledgement.
4. End-to-end test cho luồng nghiệp vụ qua nhiều service nếu cần.

## 18. Những lỗi thường gặp khi dùng OutputDestination

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| OutputDestination là null | Test binder chưa được cấu hình hoặc dependency thiếu | Thêm test binder và bật @EnableTestBinder |
| InputDestination không có channel | Gửi sai tên destination hoặc function chưa được bind | Kiểm tra function definition và input destination |
| Output nhận null | Function không phát output, đọc quá sớm hoặc sai destination | Kiểm tra function và dùng receive có timeout |
| Đọc nhầm message | Có nhiều output nhưng dùng receive() mặc định | Chỉ rõ destination name |
| Payload là byte[] | Output binder trả message bytes | Decode UTF-8 hoặc deserialize theo content type |
| JSON không parse được | Payload hoặc content type không đúng | Kiểm tra bytes, contentType và converter |
| Header không xuất hiện | Function không tạo header hoặc header mapping khác nhau | Kiểm tra MessageBuilder và test binder; xác minh lại với broker thật |
| Test chạy qua nhưng Kafka không có message | Test binder chỉ chạy trong JVM | Viết integration test với Kafka binder thật |
| Mỗi test nhận message của test trước | Output còn message chưa đọc trong context dùng chung | Đọc hết output và cô lập context |
| Test chờ hết timeout | Function không được kích hoạt hoặc pipeline chưa phát output | Kiểm tra function definition, input/output name và exception |
| Nhiều replica test gây kết quả khó đoán | Test binder không mô phỏng đầy đủ broker concurrency | Dùng test broker thật cho concurrency và partition semantics |

## 19. Bài thực hành: kiểm tra luồng đơn hàng

Tạo function chuẩn hóa đơn hàng:

~~~java
public record Order(
    String orderId,
    String status,
    long total
) {}

@Bean
Function<Order, Order> normalizeOrder() {
    return order -> new Order(
        order.orderId().trim(),
        order.status().toUpperCase(),
        order.total()
    );
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder

    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders-raw

        normalizeOrder-out-0:
          destination: orders-normalized
~~~

Viết test theo các bước:

1. Khởi tạo Spring Boot test context với `@EnableTestBinder`.
2. Inject InputDestination và OutputDestination.
3. Tạo một JSON message có orderId chứa khoảng trắng và status viết thường.
4. Đặt content type là application/json.
5. Gửi message vào destination `orders-raw`.
6. Đọc output từ `orders-normalized` với timeout hữu hạn.
7. Assertion message không null.
8. Deserialize payload thành Order.
9. Kiểm tra orderId đã trim.
10. Kiểm tra status đã chuyển thành chữ hoa.
11. Kiểm tra total giữ nguyên.
12. Gửi thêm một input không hợp lệ và xác nhận hành vi function đúng theo chính sách đã thiết kế.
13. Thêm một output binding khác nếu function cần phát audit event; xác nhận từng output bằng destination riêng.
14. Viết integration test với broker thật nếu cần xác minh routing, partition hoặc acknowledgement.

Hoàn thành bài khi có thể giải thích vai trò của InputDestination và OutputDestination; phân biệt binding name với destination name; gửi input đúng nơi; đọc output đúng nơi; kiểm tra payload, header và nhiều message; xử lý timeout; và phân biệt test binder với integration test dùng broker thật.

## 20. Tài liệu tham khảo chính thức

- [Spring Cloud Stream 5.0 — Testing](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/spring_integration_test_binder.html) — test binder, @EnableTestBinder, InputDestination, OutputDestination và nhiều destination.
- [Spring Cloud Stream 5.0 — Reference Documentation](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream.html) — mô hình ứng dụng, function, binder và test cơ bản.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — functional bean, binding name và StreamBridge.
- [Spring Cloud Stream 5.0 — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/binding-properties.html) — destination, content type và cấu hình input/output binding.

