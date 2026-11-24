# Luồng chuẩn hóa dữ liệu với Supplier, Function và Consumer

Trong hệ thống xử lý sự kiện, dữ liệu đầu vào thường đến từ nhiều nguồn và không thống nhất về cách viết, kiểu dữ liệu hoặc quy ước nghiệp vụ. Một service có thể nhận tên khách hàng thừa khoảng trắng, mã quốc gia viết thường, tiền dưới dạng chuỗi và mã tiền tệ không đồng nhất. Nếu mỗi consumer tự chuẩn hóa theo cách riêng, các service dễ tạo ra kết quả khác nhau.

Spring Cloud Stream cung cấp mô hình hàm để tách luồng xử lý thành ba vai trò:

- **Supplier** tạo hoặc lấy sự kiện từ nguồn.
- **Function** biến đổi và chuẩn hóa sự kiện.
- **Consumer** nhận kết quả để ghi nhận hoặc thực hiện nghiệp vụ tiếp theo.

Bài thực hành xây dựng pipeline đơn hàng qua broker. Supplier phát dữ liệu thô vào topic `orders.raw`; Function kiểm tra và chuẩn hóa rồi phát sang `orders.normalized`; Consumer nhận dữ liệu đã chuẩn hóa. Mỗi hàm có binding riêng, nên có thể quan sát, mở rộng và kiểm thử từng chặng.

## 1. Mục tiêu và kiến trúc

Sau bài thực hành, người học có thể tạo ba loại function bean, khai báo function độc lập, ánh xạ binding tới destination, cấu hình Kafka binder, chuẩn hóa dữ liệu, kiểm thử và quan sát luồng message.

~~~mermaid
flowchart LR
    A["Supplier<br/>orderSource"] -->|"orders.raw"| B["Kafka topic<br/>orders.raw"]
    B --> C["Function<br/>normalizeOrder"]
    C -->|"orders.normalized"| D["Kafka topic<br/>orders.normalized"]
    D --> E["Consumer<br/>consumeOrder"]
    E --> F["Log / Database / downstream"]
~~~

Hai topic là hai ranh giới dữ liệu. Bài học chạy cả ba hàm trong một ứng dụng để dễ thực hành; khi vận hành, mỗi vai trò có thể được tách thành service riêng mà không phải thay đổi hợp đồng message.

## 2. Thiết kế dữ liệu

Đầu vào mẫu:

~~~json
{
  "eventId": "evt-order-001",
  "orderId": "order-101",
  "customerName": "  Nguyen   Van An ",
  "email": " AN@example.com ",
  "country": "vn",
  "amount": "125000.00",
  "currency": "vnd"
}
~~~

Function cần trim và gộp khoảng trắng tên, chuyển email về chữ thường, chuyển mã quốc gia thành hai chữ in hoa, parse số tiền và chuẩn hóa mã tiền tệ thành ba chữ in hoa.

Đầu ra mong đợi:

~~~json
{
  "eventId": "evt-order-001",
  "orderId": "order-101",
  "customerName": "Nguyen Van An",
  "email": "an@example.com",
  "countryCode": "VN",
  "amount": 125000.00,
  "currency": "VND"
}
~~~

Giữ nguyên `eventId` và `orderId` để đối chiếu các chặng. Dùng `BigDecimal` cho tiền thay vì `double` vì số dấu phẩy động nhị phân có thể biểu diễn sai giá trị thập phân. Quy định scale/rounding theo từng loại tiền trong nghiệp vụ thật.

## 3. Project và dependency

Tạo ứng dụng Spring Boot có Spring Cloud Stream và Kafka binder. Quản lý version bằng Spring Boot parent và Spring Cloud BOM tương thích; chọn release train theo bảng tương thích chính thức.

Ví dụ dependency Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>SPRING_CLOUD_COMPATIBLE_RELEASE</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream-test-binder</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Thay `SPRING_CLOUD_COMPATIBLE_RELEASE` bằng release train tương thích với Spring Boot đang dùng. Nếu parent project đã import BOM thì không import một BOM khác phiên bản trong module con.

Cấu trúc tối thiểu:

~~~text
src/main/java/com/example/orders/
  OrderNormalizationApplication.java
  OrderFunctions.java
  RawOrder.java
  NormalizedOrder.java
src/main/resources/application.yml
src/test/java/com/example/orders/OrderNormalizationTest.java
~~~

## 4. Khai báo DTO

`RawOrder.java`:

~~~java
package com.example.orders;

public record RawOrder(
        String eventId,
        String orderId,
        String customerName,
        String email,
        String country,
        String amount,
        String currency) {
}
~~~

`NormalizedOrder.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record NormalizedOrder(
        String eventId,
        String orderId,
        String customerName,
        String email,
        String countryCode,
        BigDecimal amount,
        String currency) {
}
~~~

Record phù hợp với DTO bất biến. Spring Boot/Jackson hiện đại hỗ trợ Java record khi dependency và version tương thích. Nếu dùng serializer/schema native khác, phải cấu hình schema tương ứng thay vì giả định JSON converter xử lý mọi định dạng.

## 5. Tạo Supplier, Function và Consumer

Tạo `OrderFunctions.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderFunctions {

    private static final Logger log =
            LoggerFactory.getLogger(OrderFunctions.class);

    @Bean
    Supplier<RawOrder> orderSource() {
        List<RawOrder> sampleOrders = List.of(
                new RawOrder("evt-order-001", "order-101",
                        "  Nguyen   Van An ", " AN@example.com ",
                        "vn", "125000.00", "vnd"),
                new RawOrder("evt-order-002", "order-102",
                        "Tran Thi Binh", "binh@example.com",
                        "sg", "89.90", "sgd"),
                new RawOrder("evt-order-003", "order-103",
                        "  Le   Minh Cuong", "CUONG@example.com",
                        "us", "42.50", "usd"));

        Iterator<RawOrder> iterator = sampleOrders.iterator();
        return () -> iterator.hasNext() ? iterator.next() : null;
    }

    @Bean
    Function<RawOrder, NormalizedOrder> normalizeOrder() {
        return raw -> {
            String eventId = required(raw.eventId(), "eventId");
            String orderId = required(raw.orderId(), "orderId");
            String customerName = required(
                    raw.customerName(), "customerName")
                    .replaceAll("\\s+", " ");
            String email = required(raw.email(), "email")
                    .toLowerCase(Locale.ROOT);
            String countryCode = required(raw.country(), "country")
                    .toUpperCase(Locale.ROOT);
            String currency = required(raw.currency(), "currency")
                    .toUpperCase(Locale.ROOT);

            if (!email.matches("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")) {
                throw new IllegalArgumentException("Invalid email");
            }
            if (!countryCode.matches("[A-Z]{2}")) {
                throw new IllegalArgumentException("Invalid country code");
            }
            if (!currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid currency code");
            }

            BigDecimal amount;
            try {
                amount = new BigDecimal(required(raw.amount(), "amount"));
            }
            catch (NumberFormatException ex) {
                throw new IllegalArgumentException("Invalid amount", ex);
            }
            if (amount.signum() < 0) {
                throw new IllegalArgumentException(
                        "Amount must not be negative");
            }

            return new NormalizedOrder(
                    eventId, orderId, customerName, email,
                    countryCode, amount, currency);
        };
    }

    @Bean
    Consumer<NormalizedOrder> consumeOrder() {
        return order -> log.info(
                "Order normalized eventId={}, orderId={}, country={}, currency={}",
                order.eventId(), order.orderId(),
                order.countryCode(), order.currency());
    }

    private static String required(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value.strip();
    }
}
~~~

### Supplier tạo dữ liệu

`orderSource()` trả về `Supplier<RawOrder>`. Spring Cloud Stream dùng poller để gọi supplier định kỳ. Ví dụ đọc lần lượt ba record và trả `null` khi hết dữ liệu; lần gọi trả `null` không phát message.

Supplier chỉ là nguồn mẫu. Production có thể đọc từ API, bảng outbox, file hoặc hệ thống khác. Nếu nguồn có trạng thái, cần thiết kế checkpoint/ack để không đánh dấu dữ liệu đã lấy trước khi bảo đảm publish theo hợp đồng.

**Lưu ý khi scale:** mỗi instance của ví dụ tạo danh sách và iterator riêng, nên hai instance sẽ phát hai bản sao của cùng ba sự kiện. Production cần cơ chế chia việc/lease, cursor dùng chung hoặc outbox để nhiều instance không phát trùng ngoài ý muốn.

### Function chuẩn hóa dữ liệu

`normalizeOrder()` nhận `RawOrder` và trả `NormalizedOrder`. Function kiểm tra ID bắt buộc, chuẩn hóa tên/email, xác thực định dạng mã quốc gia/tiền tệ và parse số tiền. Nó không gọi database hoặc broker trực tiếp, nhờ đó logic có thể unit test và tái sử dụng.

Regex email chỉ là kiểm tra cú pháp cơ bản, không thay thế xác thực địa chỉ. Ứng dụng thật nên dùng danh mục quốc gia/tiền tệ và quy tắc nghiệp vụ tương ứng.

### Consumer nhận kết quả

`consumeOrder()` ghi log các trường cần thiết và không ghi email/PII. Production có thể thay log sink bằng repository, API hoặc service nghiệp vụ. Nên lưu `eventId` với unique constraint hoặc inbox table để chống xử lý trùng khi message được giao lại.

## 6. Khởi tạo ứng dụng

`OrderNormalizationApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderNormalizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                OrderNormalizationApplication.class, args);
    }
}
~~~

Không cần viết Kafka adapter thủ công. Binder tạo các binding từ function bean và cấu hình.

## 7. Function definition và binding

Tạo `application.yml`:

~~~yaml
spring:
  application:
    name: order-normalization
  cloud:
    function:
      definition: orderSource;normalizeOrder;consumeOrder
    stream:
      poller:
        fixed-delay: 2000
      bindings:
        orderSource-out-0:
          destination: orders.raw
          content-type: application/json
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizers
          content-type: application/json
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/json
        consumeOrder-in-0:
          destination: orders.normalized
          group: order-sinks
          content-type: application/json
      kafka:
        binder:
          brokers: localhost:9092
        bindings:
          orderSource-out-0:
            producer:
              message-key-expression: payload.orderId
          normalizeOrder-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

### Vì sao dùng dấu chấm phẩy?

`spring.cloud.function.definition` dùng dấu chấm phẩy để kích hoạt nhiều function độc lập trong cùng application context:

~~~text
orderSource;normalizeOrder;consumeOrder
~~~

Đây không phải composition. Ba bean được bind độc lập:

| Function bean | Kiểu | Binding |
|---|---|---|
| `orderSource` | `Supplier<RawOrder>` | `orderSource-out-0` |
| `normalizeOrder` | `Function<RawOrder, NormalizedOrder>` | `normalizeOrder-in-0`, `normalizeOrder-out-0` |
| `consumeOrder` | `Consumer<NormalizedOrder>` | `consumeOrder-in-0` |

Dấu gạch đứng (`|`) biểu diễn function composition, trong đó output của function trước nối vào input function sau. Bài này dùng destination riêng để quan sát message qua broker và scale từng chặng độc lập.

### Ý nghĩa binding

| Binding | Hướng | Destination | Group | Vai trò |
|---|---|---|---|---|
| `orderSource-out-0` | Output | `orders.raw` | — | Supplier phát dữ liệu thô |
| `normalizeOrder-in-0` | Input | `orders.raw` | `order-normalizers` | Function đọc dữ liệu thô |
| `normalizeOrder-out-0` | Output | `orders.normalized` | — | Function phát dữ liệu chuẩn hóa |
| `consumeOrder-in-0` | Input | `orders.normalized` | `order-sinks` | Consumer nhận kết quả |

Hai binding input có group tường minh. Với Kafka, group xác định consumer group và offset độc lập. Không nên dựa vào anonymous/ephemeral group cho service cần lưu tiến độ.

`content-type: application/json` cho biết payload được trao đổi theo JSON. Khi dùng native encoding/decoding hoặc schema riêng, cần cấu hình serializer/deserializer tương ứng; JSON converter có thể không tham gia đường đi native.

### Partition key

Hai output binding dùng `payload.orderId` làm Kafka record key. Các sự kiện của cùng đơn hàng có thể đi cùng partition để giữ thứ tự theo đơn hàng; những đơn hàng khác nhau có thể được phân tán. Nếu nghiệp vụ cần thứ tự theo tài khoản hoặc tenant, hãy chọn key theo aggregate thực sự cần tuần tự hóa.

## 8. Chuẩn bị Kafka broker

Chạy Kafka local hoặc dùng cluster phát triển được cấp quyền. Ví dụ tạo topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic orders.raw \
  --partitions 3 \
  --replication-factor 1

kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic orders.normalized \
  --partitions 3 \
  --replication-factor 1
~~~

Replication factor 1 phù hợp cho broker đơn local, không phải cấu hình độ bền production. Trong production, topic, partition, replication, retention và ACL nên được provision qua quy trình hạ tầng. Kafka binder có thể tự provision topic nếu broker cho phép; bài này tạo topic tường minh để kiểm tra destination và quyền.

## 9. Chạy và quan sát từng chặng

Khởi động ứng dụng sau khi Kafka sẵn sàng. Supplier poll mỗi hai giây và phát ba record:

~~~text
orderSource -> orders.raw
normalizeOrder <- orders.raw
normalizeOrder -> orders.normalized
consumeOrder <- orders.normalized
~~~

Đọc raw topic bằng group chẩn đoán riêng:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.raw \
  --group diag-orders-raw \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
~~~

Đọc normalized topic:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.normalized \
  --group diag-orders-normalized \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
~~~

Consumer chẩn đoán dùng group khác với `order-normalizers` và `order-sinks`, nên không lấy partition assignment của ứng dụng. Kiểm tra key là order ID và payload đã có các trường chuẩn hóa.

Log consumer mong đợi:

~~~text
Order normalized eventId=evt-order-001, orderId=order-101, country=VN, currency=VND
Order normalized eventId=evt-order-002, orderId=order-102, country=SG, currency=SGD
Order normalized eventId=evt-order-003, orderId=order-103, country=US, currency=USD
~~~

Không yêu cầu partition ID cụ thể vì mapping phụ thuộc số partition và partitioner. Điều cần xác nhận là cùng order ID được dùng làm key và record được đọc từ đúng topic.

## 10. Quan sát binding và consumer group

Thêm Actuator:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,bindings
~~~

Endpoint có thể kiểm tra:

~~~http
GET /actuator/health
GET /actuator/bindings
GET /actuator/bindings/normalizeOrder-in-0
GET /actuator/bindings/consumeOrder-in-0
~~~

Endpoint bindings giúp biết binding có đang chạy không. Nó cũng có thao tác lifecycle; không gửi lệnh START/STOP ở production chỉ để thử nghiệm vì có thể gây rebalance hoặc thay đổi trạng thái tiêu thụ.

Kiểm tra group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-normalizers

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-sinks
~~~

Đối chiếu partition assignment, current offset, log end offset và lag. Nếu raw topic tăng nhưng group normalizer không có member, kiểm tra function definition, input binding và broker connection. Nếu normalized topic có dữ liệu nhưng sink không xử lý, kiểm tra binding consumer cuối.

## 11. Kiểm tra dữ liệu không hợp lệ

Thử gửi record có amount sai:

~~~json
{
  "eventId": "evt-order-invalid",
  "orderId": "order-invalid",
  "customerName": "Test User",
  "email": "test@example.com",
  "country": "vn",
  "amount": "not-a-number",
  "currency": "vnd"
}
~~~

Function ném `IllegalArgumentException` khi parse số tiền. Đây là lỗi dữ liệu, không nên âm thầm chuyển thành 0 hoặc bỏ qua message mà không ghi nhận.

| Loại lỗi | Hành động gợi ý |
|---|---|
| Lỗi tạm thời khi gọi downstream | Retry có giới hạn và backoff |
| Broker tạm mất kết nối | Recovery theo binder |
| Payload sai schema hoặc thiếu trường bắt buộc | DLT/DLQ hoặc quarantine |
| Lỗi nghiệp vụ không thể retry | Ghi nhận từ chối với event ID và nguyên nhân |
| Consumer xử lý xong nhưng ACK thất bại | Cho phép redelivery và bảo vệ side effect bằng idempotency |

Spring Cloud Stream có error handling chung và các binder có cấu hình retry/DLQ riêng. Tên property, điều kiện partition của DLT và cách chuyển header phụ thuộc binder/version. Không bật retry vô hạn cho lỗi dữ liệu cố định vì poison message có thể chiếm tài nguyên và làm tăng lag.

## 12. Unit test cho Function

`normalizeOrder()` là hàm Java thuần nên có thể kiểm thử không cần broker.

`OrderNormalizationTest.java`:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

class OrderNormalizationTest {

    private final Function<RawOrder, NormalizedOrder> normalizer =
            new OrderFunctions().normalizeOrder();

    @Test
    void normalizesOrderFields() {
        RawOrder raw = new RawOrder(
                "evt-101", "order-101",
                "  Nguyen   Van An ", " AN@example.com ",
                "vn", "125000.00", "vnd");

        NormalizedOrder result = normalizer.apply(raw);

        assertThat(result.eventId()).isEqualTo("evt-101");
        assertThat(result.orderId()).isEqualTo("order-101");
        assertThat(result.customerName()).isEqualTo("Nguyen Van An");
        assertThat(result.email()).isEqualTo("an@example.com");
        assertThat(result.countryCode()).isEqualTo("VN");
        assertThat(result.amount()).isEqualByComparingTo("125000.00");
        assertThat(result.currency()).isEqualTo("VND");
    }

    @Test
    void rejectsInvalidAmount() {
        RawOrder raw = new RawOrder(
                "evt-102", "order-102", "Test User",
                "test@example.com", "vn", "invalid", "vnd");

        assertThatThrownBy(() -> normalizer.apply(raw))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid amount");
    }

    @Test
    void rejectsMissingOrderId() {
        RawOrder raw = new RawOrder(
                "evt-103", " ", "Test User",
                "test@example.com", "vn", "10.00", "vnd");

        assertThatThrownBy(() -> normalizer.apply(raw))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("orderId is required");
    }
}
~~~

Unit test xác nhận logic chuẩn hóa và validation. Nó chưa kiểm tra JSON serialization, binding name, Kafka key, broker acknowledgment hoặc consumer group.

## 13. Test Binder và kiểm thử broker thật

Spring Cloud Stream Test Binder cho phép kiểm tra function và binding trong JVM mà không khởi động Kafka. Test context có thể bật `@EnableTestBinder`, gửi message vào `InputDestination` và nhận message từ `OutputDestination`.

Luồng test cho `normalizeOrder`:

1. Chỉ kích hoạt function `normalizeOrder` trong test context.
2. Gửi `RawOrder` vào binding `normalizeOrder-in-0`.
3. Nhận output từ `normalizeOrder-out-0`.
4. Assert payload, content type và header cần thiết.
5. Gửi record sai để xác nhận error handling.

Test Binder xác nhận wiring và conversion ở mức Spring Cloud Stream. Nó không xác minh Kafka native key/partition, Rabbit exchange routing, publisher confirms hoặc Pulsar subscription.

Một integration test dùng Testcontainers nên khởi động Kafka thật, cấu hình broker URL qua `@DynamicPropertySource`, gửi event có ID duy nhất và chờ consumer outcome với timeout có giới hạn. Kiểm tra đúng topic, key, payload chuẩn hóa, consumer group và side effect cuối. Tránh dùng `Thread.sleep` cố định làm bằng chứng message đã xử lý.

## 14. Idempotency và side effect

Trong bài mẫu, Consumer chỉ ghi log. Khi ghi database, broker thường cung cấp at-least-once delivery: cùng message có thể được giao lại nếu consumer crash sau khi commit DB nhưng trước khi ACK/offset commit.

Mẫu xử lý minh họa:

~~~java
@Transactional
public void handle(NormalizedOrder order) {
    if (processedEventRepository.existsByEventId(order.eventId())) {
        return;
    }
    orderRepository.save(toEntity(order));
    processedEventRepository.save(new ProcessedEvent(order.eventId()));
}
~~~

`processed_event.event_id` cần unique constraint để hai lần xử lý đồng thời không cùng ghi thành công. Kiểm tra duplicate và ghi side effect phải nằm trong cùng transaction hoặc cơ chế atomic tương đương; cần xử lý unique-constraint race theo database thực tế.

Không khẳng định Kafka, RabbitMQ hay Pulsar tự bảo đảm exactly-once cho mọi side effect ngoài broker. Với luồng DB → broker, transactional outbox giúp ghi dữ liệu nghiệp vụ và ý định phát event trong cùng database transaction; publisher riêng gửi outbox tới broker.

## 15. Mở rộng thành nhiều instance

~~~mermaid
flowchart TB
    S["Source service<br/>Supplier"] --> R["Kafka: orders.raw"]
    R --> F["Normalizer group<br/>Function"]
    F --> N["Kafka: orders.normalized"]
    N --> C["Sink group<br/>Consumer"]
~~~

- Supplier chỉ scale an toàn nếu nguồn chia việc được giữa các instance hoặc dùng outbox/lease/checkpoint chung.
- Function consumer group có thể có nhiều instance; Kafka phân phối partition giữa các member trong cùng group.
- Số consumer xử lý song song bị giới hạn bởi số partition được gán.
- Consumer cuối scale độc lập với normalizer nếu topic normalized có đủ partition.
- Mỗi group có offset riêng; hai group khác nhau đều có thể đọc cùng topic.

Nếu topic có ba partition và group chạy sáu consumer instance, ít nhất ba instance không có partition để xử lý tại một thời điểm. Tăng consumer vượt partition count không tự tăng throughput.

## 16. Chuyển sang RabbitMQ hoặc Pulsar

Mô hình function và binding name có thể giữ nguyên khi thay binder, nhưng semantics của broker khác nhau:

| Thành phần | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Destination | Topic | Exchange/queue do binder ánh xạ | Topic |
| Group | Consumer group và offset | Queue/group topology | Subscription |
| Phân phối | Topic partitions | Routing key, queue và consumer | Partitioned topic, subscription type |
| Thứ tự | Trong một partition | Phụ thuộc queue, consumer, prefetch và requeue | Phụ thuộc key, partition và subscription type |
| Quan sát giao nhận | Record metadata, offset, lag | Publisher confirms/returns, ready/unacked | Message ID, backlog, redelivery |

Với RabbitMQ, kiểm tra exchange, queue và binding key; publisher confirm ACK không tự chứng minh message được route vào queue. Với Pulsar, kiểm tra tenant/namespace/topic, subscription name, subscription type và cursor. Khi thay binder, phải chạy integration test với broker thật tương ứng.

## 17. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Supplier không phát dữ liệu | Definition thiếu supplier hoặc poller chưa hoạt động | Kiểm tra function definition, poller và log startup |
| Raw topic không có record | Sai output binding, broker connection hoặc producer lỗi | Kiểm tra orderSource-out-0, destination và producer errors |
| Raw topic có record nhưng Function không chạy | Input binding dừng, group sai hoặc không có assignment | Kiểm tra normalizeOrder-in-0, group và lag |
| Function báo lỗi conversion | Content type/JSON/schema không khớp | Kiểm tra application/json, DTO và serializer |
| Normalized topic không có record | Function ném exception hoặc output binding sai | Kiểm tra validation errors, retry/DLT và normalizeOrder-out-0 |
| Consumer cuối không log | Group/binding sai hoặc message chưa tới normalized topic | Đọc topic và kiểm tra consumeOrder-in-0 |
| Message xử lý lặp | Redelivery hoặc nhiều Supplier instance phát cùng mẫu | Dùng event ID và idempotent sink |
| Consumer lag tăng | Xử lý chậm, ít partition hoặc downstream nghẽn | Đo lag từng partition, latency và tài nguyên |
| Test Binder pass nhưng Kafka không có record | Test chỉ chạy trong JVM | Chạy real-broker integration test |

Khi chẩn đoán, lần theo event ID từ raw topic sang normalized topic và log Consumer. Đừng kết luận broker đã nhận chỉ vì `StreamBridge.send()` trả về `true`; local handoff và broker acknowledgment là các mốc khác nhau.

## 18. Bài tập mở rộng và tiêu chí nghiệm thu

Bài tập:

1. Thêm `sourceSystem` vào RawOrder và NormalizedOrder.
2. Chuẩn hóa số điện thoại theo mã quốc gia nhưng không ghi số điện thoại vào log.
3. Tạo validator riêng và viết test cho email, country code, currency code và amount.
4. Tạo record sai schema; quan sát retry và DLT/DLQ.
5. Thay log Consumer bằng repository có unique constraint trên eventId.
6. Chạy hai normalizer instance và quan sát consumer group assignment.
7. Tăng partition count trong môi trường thử nghiệm, đo lag và phân phối key.
8. Viết integration test xác nhận cùng orderId dùng cùng Kafka record key.
9. Thay Kafka binder bằng RabbitMQ hoặc Pulsar binder và ghi lại khác biệt topology.
10. Tách Supplier, Function và Consumer thành ba ứng dụng, giữ nguyên message contract.

Checklist nghiệm thu:

- [ ] Ứng dụng khởi động và phát hiện đủ ba function bean.
- [ ] Function definition liệt kê ba function độc lập bằng dấu chấm phẩy.
- [ ] Supplier phát RawOrder vào orders.raw.
- [ ] Function validate và tạo NormalizedOrder.
- [ ] Function phát kết quả vào orders.normalized.
- [ ] Consumer nhận kết quả và log event ID/order ID.
- [ ] Content type nhất quán ở các binding.
- [ ] Kafka record key được đặt theo orderId.
- [ ] Consumer group của hai input binding được khai báo tường minh.
- [ ] Unit test xác nhận chuẩn hóa và validation lỗi.
- [ ] Test Binder không bị nhầm là bằng chứng broker thật.
- [ ] Integration test xác nhận đường đi qua broker.
- [ ] Retry/DLT/DLQ có giới hạn và có thể quan sát.
- [ ] Sink có idempotency nếu side effect không được phép lặp.
- [ ] Supplier không phát trùng ngoài ý muốn khi scale.

## Kết luận

Luồng chuẩn hóa dữ liệu thể hiện cách tổ chức ứng dụng Spring Cloud Stream quanh các hàm độc lập. Supplier tạo dữ liệu đầu vào, Function tập trung vào validation và chuyển đổi thuần, Consumer tiếp nhận kết quả để tạo side effect. Binding kết nối các hàm với destination và consumer group; binder đảm nhiệm giao tiếp với Kafka hoặc broker khác. Khi tách rõ trách nhiệm, giữ hợp đồng payload/key ổn định, kiểm thử qua broker thật và thiết kế idempotency cho consumer, pipeline có thể mở rộng thành nhiều service mà vẫn dễ quan sát và vận hành.

## Tài liệu tham khảo

- [Spring Cloud Stream — Programming Model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — RabbitMQ Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
