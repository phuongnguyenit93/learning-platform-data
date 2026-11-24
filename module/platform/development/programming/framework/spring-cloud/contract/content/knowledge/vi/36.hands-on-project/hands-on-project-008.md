# Kích hoạt messaging stub và kiểm chứng mã consumer

## Mục tiêu dự án

**Spring Cloud Contract** giúp producer và consumer thỏa thuận hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Từ hợp đồng, công cụ sinh kiểm thử phía producer, tạo stub artifact để consumer sử dụng qua **Stub Runner**, và đưa các kiểm tra vào CI để phát hiện thay đổi API không tương thích.

Dự án thực hành này xây dựng hai service nhỏ:

- **Order Service (producer):** khi đơn hàng chuyển sang trạng thái thanh toán thành công, phát message `ORDER_PAID` đến destination `orders.events`.
- **Shipping Service (consumer):** nhận message, tạo shipment cho đơn hàng và bảo đảm xử lý lặp không tạo shipment trùng.

Bạn sẽ hoàn thành toàn bộ luồng:

~~~text
Order Service
  -> producer message contract
  -> generated producer test
  -> stub artifact

Shipping Service
  -> Stub Runner tải stub
  -> StubTrigger kích hoạt message theo label
  -> message binding gọi consumer code
  -> assertions kiểm tra shipment được tạo
~~~

Sau dự án, bạn có thể:

1. Viết message contract mô tả destination, headers và payload.
2. Dùng `triggeredBy` để generated producer test kích hoạt logic phát message thật.
3. Sinh và cài stub artifact có classifier `stubs`.
4. Dùng `@AutoConfigureStubRunner` và `StubTrigger` để phát message stub trong consumer test.
5. Kiểm chứng consumer code bằng trạng thái nghiệp vụ và repository, không chỉ xác nhận stub được kích hoạt.
6. Kiểm tra idempotency, message headers, schema và lỗi cấu hình destination.
7. Tích hợp producer verification, stub packaging và consumer tests vào CI.

**Điểm cần phân biệt xuyên suốt:** `triggeredBy` ở producer test gọi phương thức kích hoạt ứng dụng producer; `StubTrigger.trigger(label)` ở consumer test phát message từ stub để kiểm tra consumer. Hai cơ chế có vai trò khác nhau.

## 1. Kịch bản nghiệp vụ

Một đơn hàng có thể chuyển từ `PENDING` sang `PAID`. Khi thanh toán thành công, Order Service phát sự kiện:

~~~json
{
  "eventId": "EVT-ORD-1001-PAID",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "amount": 125000,
  "currency": "VND"
}
~~~

Shipping Service nhận event và tạo shipment ở trạng thái `READY_FOR_PICKUP`.

### Luồng nghiệp vụ

~~~mermaid
sequenceDiagram
    participant API as Order Service
    participant DB as Order DB
    participant PUB as Message Publisher
    participant BUS as orders.events
    participant SH as Shipping Consumer
    participant SDB as Shipping DB

    API->>DB: Đọc đơn ORD-1001
    API->>DB: Chuyển trạng thái PAID
    API->>PUB: Publish ORDER_PAID
    PUB->>BUS: Event JSON + headers
    BUS->>SH: Gửi message
    SH->>SDB: Tạo shipment
    SH-->>BUS: Xử lý thành công
~~~

Trong bài thực hành, message contract xác minh output của producer. Stub Runner phát một message mẫu để consumer test đi qua **message binding và handler thực tế** của Shipping Service.

**Contract test không tự chứng minh broker production bảo đảm exactly-once hoặc ordering.** Ta sẽ dùng test binder/messaging adapter phù hợp để kiểm tra consumer code, và nêu rõ phần nào cần integration test với broker thật.

## 2. Kiến trúc và cấu trúc project

Có thể đặt hai service trong một Maven multi-module project:

~~~text
messaging-contract-lab/
├── pom.xml
├── order-service/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/orders/
│       │   ├── OrderApplication.java
│       │   ├── OrderApplicationService.java
│       │   ├── OrderEventPublisher.java
│       │   └── StreamOrderEventPublisher.java
│       └── test/
│           ├── java/com/example/orders/contract/
│           │   └── OrderMessageContractBase.java
│           └── resources/contracts/orders/
│               └── order-paid.yml
└── shipping-service/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/shipping/
        │   ├── ShippingApplication.java
        │   ├── OrderPaidEvent.java
        │   ├── OrderPaidConsumer.java
        │   ├── ShippingService.java
        │   └── ShipmentRepository.java
        ├── test/java/com/example/shipping/
        │   └── OrderPaidConsumerContractTest.java
        └── test/resources/
            └── application-test.yml
~~~

Tên packages và các classes là lựa chọn của dự án mẫu. Trong dự án thật, cần tuân theo package, module boundaries và naming conventions hiện có.

### Vai trò các thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| `order-paid.yml` | Thỏa thuận message `ORDER_PAID` |
| `OrderMessageContractBase` | Chuẩn bị fixture và cung cấp phương thức `triggeredBy` |
| `OrderApplicationService` | Thực hiện chuyển trạng thái đơn hàng |
| `StreamOrderEventPublisher` | Gửi event qua Spring Cloud Stream |
| Contract Verifier | Sinh và chạy producer message tests |
| Stub JAR | Đóng gói message stub và label |
| `StubTrigger` | Kích hoạt message stub phía consumer |
| `OrderPaidConsumer` | Nhận event qua binding |
| `ShippingService` | Thực hiện nghiệp vụ tạo shipment |
| Consumer contract test | Kiểm tra handler và trạng thái shipment |

## 3. Chuẩn bị toolchain và dependencies

Dùng một bộ Spring Boot, Spring Cloud release train, Spring Cloud Contract và JDK đã được đối chiếu theo compatibility matrix của dự án. Không tự chọn các version độc lập chỉ vì chúng là bản mới nhất.

Trong cả hai modules, nên quản lý Spring dependencies qua parent/BOM phù hợp. **Contract Maven plugin version được khai báo riêng**; Spring Cloud BOM không tự quản lý plugin trong `build.plugins`.

### Producer dependencies

POM của `order-service` cần những thành phần tương ứng với:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Test binder là lựa chọn phù hợp khi ứng dụng dùng Spring Cloud Stream và version Contract Verifier/message verifier được cấu hình tương thích. Nếu dự án dùng Spring Integration, Kafka/RabbitMQ adapter hoặc messaging framework khác, hãy chọn integration tương ứng.

Plugin Maven minh họa:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>CONTRACT_PLUGIN_VERSION_DA_XAC_MINH</version>
      <extensions>true</extensions>
      <configuration>
        <baseClassForTests>
          com.example.orders.contract.OrderMessageContractBase
        </baseClassForTests>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`CONTRACT_PLUGIN_VERSION_DA_XAC_MINH` là placeholder, phải thay bằng version phù hợp với Contract libraries và build tool của dự án. Không copy nguyên placeholder để build.

### Consumer dependencies

POM của `shipping-service` cần:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

`spring-cloud-starter-contract-stub-runner` cung cấp tích hợp Stub Runner. `spring-cloud-stream-test-binder` giúp chạy consumer binding trong test mà không cần kết nối broker dùng chung. Cần xác nhận adapter/message verifier tương ứng với line Spring Cloud Contract đang sử dụng.

## 4. Bước 1 — Viết message contract

Tạo file:

`order-service/src/test/resources/contracts/orders/order-paid.yml`

~~~yaml
description: "Đơn hàng đã thanh toán phát sự kiện ORDER_PAID"
label: order_paid

input:
  triggeredBy: markOrderAsPaid()

outputMessage:
  sentTo: orders.events
  headers:
    contentType: application/json
  body:
    eventId: EVT-ORD-1001-PAID
    eventType: ORDER_PAID
    orderId: ORD-1001
    amount: 125000
    currency: VND
~~~

### Đọc hợp đồng

- `label: order_paid` là nhãn dùng để định danh message stub có thể được kích hoạt phía consumer.
- `input.triggeredBy` yêu cầu generated producer test gọi phương thức `markOrderAsPaid()` trong base test.
- `outputMessage.sentTo` mô tả logical destination mà producer phát message tới.
- `headers.contentType` xác định payload được mô tả là JSON.
- `body` là payload event với ID, event type, order ID, amount và currency.

### Contract không mô tả mọi chi tiết broker

`orders.events` là destination trong giao diện messaging. Contract không tự định nghĩa Kafka partition, consumer group, retention, retry, DLQ hoặc delivery guarantee. Các yêu cầu đó cần cấu hình và test ở lớp messaging/integration tương ứng.

### Kiểu dữ liệu phải rõ ràng

Trong body:

- `eventId`, `eventType`, `orderId`, `currency` là strings.
- `amount` là JSON number.
- `contentType` là message header, không phải một field payload.

Không quote `125000` thành `"125000"` nếu consumer schema yêu cầu number.

## 5. Bước 2 — Xây producer application service

Định nghĩa event:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderPaidEvent(
    String eventId,
    String eventType,
    String orderId,
    BigDecimal amount,
    String currency
) {}
~~~

Định nghĩa publisher interface để tách business logic khỏi transport:

~~~java
package com.example.orders;

public interface OrderEventPublisher {
    void publish(OrderPaidEvent event);
}
~~~

Application service thực hiện nghiệp vụ:

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OrderEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OrderEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void markOrderAsPaid(String orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found")
            );

        order.markPaid();
        orderRepository.save(order);

        OrderPaidEvent event = new OrderPaidEvent(
            "EVT-" + orderId + "-PAID",
            "ORDER_PAID",
            order.getId(),
            order.getAmount(),
            order.getCurrency()
        );

        eventPublisher.publish(event);
    }
}
~~~

`OrderRepository` và `Order` là domain/repository classes của ví dụ. Cần bảo đảm fixture có order `ORD-1001` với amount `125000` và currency `VND` trước khi trigger.

### Vì sao tách publisher interface?

- Business service không phụ thuộc trực tiếp vào một broker cụ thể.
- Có thể thay adapter theo môi trường.
- Contract test vẫn gọi **application service thật**.
- Producer message verifier quan sát output qua messaging integration đã cấu hình.

Không mock `OrderApplicationService` hoặc thay toàn bộ publisher bằng một mock chỉ trả về thành công nếu mục tiêu là kiểm chứng producer phát message theo contract.

## 6. Bước 3 — Cấu hình output binding của producer

Một adapter dùng Spring Cloud Stream `StreamBridge` có thể trông như sau:

~~~java
package com.example.orders;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;
import org.springframework.util.MimeTypeUtils;

@Component
public class StreamOrderEventPublisher implements OrderEventPublisher {

    private final StreamBridge streamBridge;

    public StreamOrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Override
    public void publish(OrderPaidEvent event) {
        Message<OrderPaidEvent> message =
            MessageBuilder.withPayload(event)
                .setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.APPLICATION_JSON
                )
                .build();

        boolean sent = streamBridge.send(
            "orderPaid-out-0",
            message
        );

        if (!sent) {
            throw new IllegalStateException(
                "Cannot publish ORDER_PAID event"
            );
        }
    }
}
~~~

Tên binding `orderPaid-out-0` phải khớp với cấu hình output binding. Đây là ví dụ Spring Cloud Stream; cách khởi tạo binding và binder cụ thể cần điều chỉnh theo phiên bản framework.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orderPaid-out-0
      bindings:
        orderPaid-out-0:
          destination: orders.events
          content-type: application/json
~~~

Nếu sử dụng một binder production như Kafka hoặc RabbitMQ, cấu hình binder riêng cho môi trường chạy. Producer contract tests cần dùng **test binder/message verifier** phù hợp, tránh gửi event kiểm thử tới broker production.

### Đối chiếu destination

| Vị trí | Giá trị |
| --- | --- |
| Contract `outputMessage.sentTo` | `orders.events` |
| StreamBridge binding name | `orderPaid-out-0` |
| Output binding destination | `orders.events` |
| Message verifier test destination | Destination được adapter cấu hình từ contract |
| Consumer input destination | `orders.events` |

Binding name và destination có thể khác nhau. **Destination là tên kênh mà producer và consumer phải thống nhất**.

## 7. Bước 4 — Viết producer message base test

Tạo:

`order-service/src/test/java/com/example/orders/contract/OrderMessageContractBase.java`

~~~java
package com.example.orders.contract;

import com.example.orders.OrderApplicationService;
import com.example.orders.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public abstract class OrderMessageContractBase {

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private OrderApplicationService orderApplicationService;

    @BeforeEach
    void prepareOrderFixture() {
        orderRepository.deleteAll();
        orderRepository.save(
            OrderFixture.paidTransitionCandidate(
                "ORD-1001",
                125000,
                "VND"
            )
        );
    }

    public void markOrderAsPaid() {
        orderApplicationService.markOrderAsPaid("ORD-1001");
    }
}
~~~

`OrderFixture` là fixture factory minh họa. Trong dự án thật, cần dùng test database riêng, fixture đúng schema và cách cleanup an toàn. Đơn hàng seed phải ở trạng thái có thể chuyển sang `PAID`, ví dụ `PENDING`.

### Phương thức triggeredBy phải có thể truy cập

Generated producer test cần gọi được `markOrderAsPaid()`. Do đó:

- Method phải có đúng tên trong contract.
- Method phải có signature mà generated test có thể gọi.
- Base class mapping phải trỏ đúng class.
- Test lifecycle phải chuẩn bị fixture trước khi trigger.
- Method phải kích hoạt **application behavior thật**.

Nếu test báo `NoSuchMethodError` hoặc `cannot find symbol`, hãy xem generated source và base class mapping trước khi sửa message body.

### Vì sao không gọi publisher trực tiếp?

Nếu base method gọi thẳng `eventPublisher.publish(new OrderPaidEvent(...))`, test có thể chỉ xác minh khả năng gửi một payload đã hardcode. Gọi `OrderApplicationService.markOrderAsPaid` sẽ đi qua nghiệp vụ đổi trạng thái và tạo event, giúp phát hiện producer quên publish hoặc tạo dữ liệu sai.

## 8. Bước 5 — Chạy producer contract verification

Trong thư mục `order-service`, chạy:

~~~bash
./mvnw clean verify
~~~

Khi plugin/lifecycle được cấu hình đúng, Contract Verifier sẽ:

1. Phát hiện `order-paid.yml`.
2. Sinh producer message test.
3. Khởi tạo Spring test context.
4. Chuẩn bị fixture qua base test.
5. Gọi `markOrderAsPaid()`.
6. Quan sát message producer phát ra.
7. Kiểm tra destination, headers và body theo contract.
8. Ghi test report.

### Những điều phải xác nhận

- Contract được discover đúng.
- Generated test source thực sự tồn tại.
- Generated test kế thừa `OrderMessageContractBase`.
- `markOrderAsPaid()` được gọi.
- Message output được capture bởi test messaging integration.
- Destination `orders.events` đúng.
- Header content type là JSON.
- Payload có đúng field và type.
- Generated producer test PASS, không bị skip.

**`BUILD SUCCESS` với 0 generated tests không phải producer verification thành công.**

### Nếu producer test FAIL

Kiểm tra theo thứ tự:

1. Fixture có đúng trạng thái ban đầu không?
2. `markOrderAsPaid()` có chạy application service không?
3. Business service có publish event không?
4. Output binding có gửi tới đúng destination không?
5. Test binder/message verifier có capture đúng channel không?
6. Event serializer có tạo JSON với đúng field/types không?
7. Contract có mô tả đúng behavior đã thỏa thuận không?

Không sửa contract để che một event bị thiếu hoặc field producer phát sai.

## 9. Bước 6 — Đóng gói và cài stub artifact

Sau khi producer verification PASS, cài artifact vào Maven local repository:

~~~bash
./mvnw clean install
~~~

Trong cách đóng gói thông dụng, producer build sẽ tạo một stub artifact với classifier `stubs`. Ví dụ tọa độ:

~~~text
groupId:    com.example.orders
artifactId: order-service
version:    2.5.0
classifier: stubs
type:       jar
~~~

Tên file thường có dạng:

~~~text
order-service-2.5.0-stubs.jar
~~~

Vị trí Maven local repository theo mặc định thường là:

~~~text
~/.m2/repository/com/example/orders/order-service/2.5.0/
~~~

Đường dẫn thực có thể khác nếu Maven dùng `localRepository` riêng hoặc cấu hình CI. Trên Windows, Maven local repository thường nằm dưới thư mục người dùng trong `.m2/repository`.

### Kiểm tra artifact

Xác minh:

- Stub JAR tồn tại.
- Classifier là `stubs`.
- Artifact version là `2.5.0` như consumer test khai báo.
- JAR chứa mapping/metadata/message stub cần thiết.
- Contract label `order_paid` được sinh đúng.
- Artifact được tạo từ contract revision và producer commit đã verified.

**Không chỉ kiểm tra file JAR có tồn tại.** Một artifact rỗng hoặc sinh từ revision cũ không chứng minh consumer sẽ nhận đúng message.

### Phân biệt các version

| Giá trị | Ý nghĩa |
| --- | --- |
| `2.5.0` trong GAV | Version Order Service |
| `stubs` | Classifier của stub artifact |
| Spring Cloud Contract plugin version | Version công cụ sinh tests/stubs |
| `order_paid` | Label của message stub |
| `orders.events` | Destination message |

## 10. Bước 7 — Xây consumer event model

Trong `shipping-service`, định nghĩa DTO:

~~~java
package com.example.shipping;

import java.math.BigDecimal;

public record OrderPaidEvent(
    String eventId,
    String eventType,
    String orderId,
    BigDecimal amount,
    String currency
) {}
~~~

DTO consumer phải phản ánh payload mà consumer cần xử lý. Không nhất thiết copy toàn bộ class Java từ producer; **giao tiếp dựa trên schema/message**, không dựa trên việc chia sẻ domain class nội bộ.

### Kiểm tra schema assumptions

Consumer có thể cần:

- `eventId` để deduplicate.
- `eventType` để định tuyến nghiệp vụ.
- `orderId` để tạo shipment.
- `amount` và `currency` nếu quy trình vận chuyển cần kiểm tra giá trị.
- Header correlation/tracing nếu hệ thống yêu cầu.

Nếu consumer không dùng một field, không cần biến field đó thành dependency nghiệp vụ chỉ vì nó xuất hiện trong DTO.

## 11. Bước 8 — Viết consumer service và idempotency

Một consumer nên xử lý message theo nghiệp vụ, ví dụ:

~~~java
package com.example.shipping;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ShippingService {

    private final ShipmentRepository shipmentRepository;

    public ShippingService(ShipmentRepository shipmentRepository) {
        this.shipmentRepository = shipmentRepository;
    }

    @Transactional
    public void handleOrderPaid(OrderPaidEvent event) {
        if (!"ORDER_PAID".equals(event.eventType())) {
            throw new IllegalArgumentException("Unexpected event type");
        }

        if (shipmentRepository.existsByEventId(event.eventId())) {
            return;
        }

        Shipment shipment = Shipment.readyForPickup(
            event.eventId(),
            event.orderId(),
            event.amount(),
            event.currency()
        );

        shipmentRepository.save(shipment);
    }
}
~~~

`ShipmentRepository` cần hỗ trợ `existsByEventId` và lưu shipment. Trong hệ thống thật, idempotency nên được bảo vệ bằng **unique constraint/transaction strategy** phù hợp để tránh race condition khi hai bản sao event đến đồng thời.

### Vì sao idempotency thuộc project này?

Message delivery có thể lặp lại tùy broker, retry và failure window. Consumer không nên tạo hai shipment chỉ vì cùng một event được gửi lại. Contract test giúp xác minh consumer xử lý payload, còn idempotency cần được thể hiện trong **consumer code và assertions**.

## 12. Bước 9 — Kết nối consumer bằng Spring Cloud Stream

Khai báo functional consumer:

~~~java
package com.example.shipping;

import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderPaidConsumer {

    @Bean
    Consumer<OrderPaidEvent> orderPaid(ShippingService shippingService) {
        return shippingService::handleOrderPaid;
    }
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPaid
    stream:
      bindings:
        orderPaid-in-0:
          destination: orders.events
          content-type: application/json
~~~

Spring Cloud Stream sử dụng function definition `orderPaid` và binding input `orderPaid-in-0` theo quy ước functional binding. Destination phải trùng logical destination trong contract.

### Test profile

Trong consumer contract test, cấu hình binder phù hợp để message stub được đưa vào binding mà không cần broker production. Nếu dùng Spring Cloud Stream, dependency test binder và message verifier integration phải tương thích với phiên bản Spring Cloud Contract/Stream đã chọn.

Không tự tạo một Kafka/RabbitMQ production connection chỉ để chạy test stub nếu mục tiêu là kiểm chứng handler logic trong môi trường cô lập.

## 13. Bước 10 — Viết consumer contract test bằng Stub Runner

Đây là phần trọng tâm của dự án.

~~~java
package com.example.shipping;

import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:2.5.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderPaidConsumerContractTest {

    @Autowired
    private StubTrigger stubTrigger;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @BeforeEach
    void cleanTestData() {
        shipmentRepository.deleteAll();
    }

    @Test
    void createsShipmentWhenOrderPaidStubIsTriggered() {
        boolean triggered = stubTrigger.trigger("order_paid");

        assertThat(triggered).isTrue();

        await()
            .atMost(Duration.ofSeconds(5))
            .untilAsserted(() ->
                assertThat(
                    shipmentRepository.findByOrderId("ORD-1001")
                ).isPresent()
            );

        Shipment shipment =
            shipmentRepository.findByOrderId("ORD-1001").orElseThrow();

        assertThat(shipment.getStatus()).isEqualTo("READY_FOR_PICKUP");
        assertThat(shipment.getEventId())
            .isEqualTo("EVT-ORD-1001-PAID");
    }
}
~~~

Ví dụ giả định:

- Consumer dùng Spring Cloud Stream functional binding và message verifier/test binder tương thích.
- Repository là test repository hoặc database test cô lập.
- Stub artifact `order-service:2.5.0:stubs` đã được cài trong Maven local repository.
- Label `order_paid` đúng với label của contract producer.
- Consumer handler xử lý message bất đồng bộ, vì vậy dùng Awaitility với timeout hữu hạn.

Tên package/API và cấu hình messaging có thể cần điều chỉnh theo release train đang dùng. Hãy kiểm tra generated test và integration adapter thực tế.

### Đọc test từng bước

1. `@SpringBootTest` khởi tạo Shipping Service.
2. `@AutoConfigureStubRunner` tải stub artifact của Order Service.
3. `StubTrigger` được inject.
4. `trigger("order_paid")` yêu cầu Stub Runner phát message có label đó.
5. Message được chuyển đến destination `orders.events`.
6. Spring Cloud Stream binding `orderPaid-in-0` chuyển message tới function `orderPaid`.
7. Function gọi `ShippingService.handleOrderPaid`.
8. Repository ghi shipment.
9. Assertion kiểm tra trạng thái và event ID đã được lưu.

**`assertThat(triggered).isTrue()` chỉ xác nhận việc kích hoạt stub thành công theo API của StubTrigger. Nó không thay thế assertion nghiệp vụ ở repository.**

## 14. Producer triggeredBy khác consumer StubTrigger

Hai bước này dễ bị nhầm:

| Cơ chế | Phía chạy | Tác dụng |
| --- | --- | --- |
| `input.triggeredBy: markOrderAsPaid()` | Producer generated test | Gọi application service để producer phát message thật và được verifier kiểm tra |
| `StubTrigger.trigger("order_paid")` | Consumer test | Kích hoạt message mẫu từ stub artifact để consumer xử lý |

~~~mermaid
flowchart TD
    A["Producer contract input.triggeredBy"] --> B["OrderMessageContractBase"]
    B --> C["OrderApplicationService"]
    C --> D["Publisher thật + test message verifier"]
    D --> E["Producer output được verify"]
    F["Consumer StubTrigger.trigger(label)"] --> G["Message stub trong artifact"]
    G --> H["Destination orders.events"]
    H --> I["Shipping consumer code"]
    I --> J["Shipment repository assertions"]
~~~

Nếu producer generated test chỉ gọi `StubTrigger`, nó không chứng minh producer phát event. Nếu consumer test gọi trực tiếp `ShippingService.handleOrderPaid`, nó không chứng minh message stub có thể kích hoạt binding và chuyển payload tới consumer.

**Project cần cả hai đường bằng chứng** để xác minh producer contract và consumer integration.

## 15. Bước 11 — Kiểm tra idempotency bằng cách trigger lặp

Có thể bổ sung test:

~~~java
@Test
void duplicateOrderPaidMessageDoesNotCreateDuplicateShipment() {
    assertThat(stubTrigger.trigger("order_paid")).isTrue();
    assertThat(stubTrigger.trigger("order_paid")).isTrue();

    await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
            assertThat(
                shipmentRepository.findAllByOrderId("ORD-1001")
            ).hasSize(1)
        );
}
~~~

Test này giả định cùng stub label có thể được trigger nhiều lần và consumer xử lý event ID lặp. Nếu message verifier/binder hoặc test configuration không hỗ trợ phát lặp theo cách trên, hãy sử dụng integration test phù hợp để phát cùng payload hai lần.

### Điều cần chứng minh

- Cùng `eventId` không tạo shipment mới.
- Record hiện tại vẫn giữ trạng thái hợp lệ.
- Handler không làm mất dữ liệu do retry.
- Có unique constraint/transaction handling phù hợp nếu consumer chạy song song.

Một test gọi handler hai lần trực tiếp có thể bổ sung cho unit test, nhưng **StubTrigger test** vẫn cần kiểm tra đường messaging.

## 16. Bước 12 — Kiểm tra consumer behavior, không chỉ DTO mapping

Một consumer test yếu:

~~~java
assertThat(stubTrigger.trigger("order_paid")).isTrue();
~~~

Test đó chỉ xác minh label có thể được kích hoạt. Nó chưa chứng minh:

- Consumer function đã nhận message.
- JSON được deserialize thành `OrderPaidEvent`.
- Handler được gọi.
- Shipment được lưu đúng.
- Event ID được xử lý idempotent.
- Consumer không bỏ qua hoặc làm sai event type.

Consumer test đầy đủ nên kiểm tra **kết quả quan sát được** của code consumer, ví dụ repository state, outgoing command, status transition hoặc domain event tiếp theo.

### Assertion theo business outcome

| Assertion | Giá trị |
| --- | --- |
| Trigger trả `true` | Stub label được kích hoạt |
| Shipment tồn tại | Consumer handler đã tạo record |
| Shipment order ID đúng | Payload được đọc đúng field |
| Event ID đúng | Message metadata/payload được xử lý đúng |
| Status đúng | Consumer business logic chạy đúng |
| Duplicate không tạo record thứ hai | Idempotency behavior được bảo vệ |

Nếu handler chạy bất đồng bộ, dùng Awaitility hoặc cơ chế đồng bộ phù hợp với adapter; tránh `Thread.sleep` cố định.

## 17. Bước 13 — Cấu hình test application

Một `application-test.yml` minh họa:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPaid
    stream:
      bindings:
        orderPaid-in-0:
          destination: orders.events
          content-type: application/json
~~~

Dependency test binder đã được khai báo ở consumer module. Cách tự động chọn binder và message verifier có thể phụ thuộc version, test configuration và các binder dependencies khác.

### Kiểm tra profile

- Test không dùng broker production.
- Destination là `orders.events`.
- Consumer function definition đúng `orderPaid`.
- Input binding đúng `orderPaid-in-0`.
- Message content type là JSON.
- Không có profile khác ghi đè binding destination.
- Không có consumer group/topic dùng chung gây tác động ngoài ý muốn.

Nếu dự án có nhiều binder, cần cấu hình binder cụ thể cho binding hoặc test profile để message từ Stub Runner đến đúng adapter.

## 18. Bước 14 — Chạy toàn bộ lab theo thứ tự

Giả sử hai modules đã được tạo dưới root `messaging-contract-lab`.

### Chạy producer

Trong thư mục `order-service`:

~~~bash
./mvnw clean verify
./mvnw clean install
~~~

Lệnh đầu sinh và chạy producer contract tests. Lệnh sau thực hiện lifecycle cài artifact vào local repository; tùy cấu hình plugin, tests cũng sẽ được chạy lại.

Sau đó kiểm tra stub artifact `order-service-2.5.0-stubs.jar` trong Maven local repository.

### Chạy consumer

Trong thư mục `shipping-service`:

~~~bash
./mvnw clean test
~~~

Stub Runner ở `StubsMode.LOCAL` tìm artifact đã cài. Consumer test trigger `order_paid` và xác minh shipment được tạo.

### Nếu dùng remote artifact repository

Khi publish vào Maven repository dùng chung:

- Cài artifact vào repository nội bộ bằng pipeline release có quyền.
- Chuyển consumer Stub Runner sang `StubsMode.REMOTE`.
- Cấu hình `repositoryRoot` và credentials qua secret store.
- Không nhúng username/password vào source code hoặc test report.
- Ghi GAV, repository và checksum của artifact đã resolve.

Đừng dùng `REMOTE` khi chưa publish artifact; đừng dùng `LOCAL` trong CI nếu local Maven repository không được chuẩn bị đúng.

## 19. Kết quả mong đợi

<badge color="success">Kết quả mục tiêu</badge>

| Bước | Kết quả |
| --- | --- |
| Producer contract discovery | Tìm thấy `order-paid.yml` |
| Generated producer test | Được sinh và thực thi |
| Producer trigger | `markOrderAsPaid()` được gọi |
| Producer message verification | Destination/header/body PASS |
| Stub packaging | Có `order-service:2.5.0:stubs` |
| Consumer Stub Runner | Resolve đúng artifact |
| Stub trigger | `trigger("order_paid")` trả `true` |
| Consumer message handler | Nhận và xử lý event |
| Business assertion | Shipment `ORD-1001` được tạo |
| Idempotency test | Trigger lặp không tạo shipment trùng |

Đây là **kết quả cần đạt của bài tập**, không phải xác nhận project mẫu đã được build trong workspace.

## 20. Chẩn đoán lỗi trong project

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Producer generated test không tìm thấy `markOrderAsPaid()` | Sai base class mapping hoặc method visibility/name | Đọc generated test và plugin configuration |
| Producer test PASS nhưng không có message | Publisher không được gọi hoặc verifier chưa capture output | Xem application service, binder và message verifier |
| Producer test không tìm thấy destination | `sentTo` khác output binding destination | So contract và StreamBridge/binding config |
| Stub JAR không xuất hiện | Plugin chưa chạy packaging goal hoặc producer build chưa install | Xem Maven plugin logs và attached artifacts |
| Consumer không resolve stub | Sai GAV/version/classifier hoặc chưa install/publish | Kiểm tra local repository/remote repository |
| `StubTrigger` trả `false` | Label không tồn tại hoặc stub không chứa message label | So `label` trong contract với artifact |
| Trigger thành công nhưng consumer không nhận | Destination/binder/binding mismatch | Kiểm tra message verifier, binding và test binder |
| Consumer nhận nhưng JSON conversion lỗi | Header content type/serializer/DTO mismatch | Xem message headers và payload type |
| Shipment không xuất hiện | Handler không được gọi hoặc business validation fail | Xem consumer logs và repository state |
| Consumer test timeout | Async processing, binder hoặc handler lỗi | Kiểm tra logs, timeout, binding lifecycle |
| Hai shipment được tạo | Chưa có idempotency/unique constraint | Kiểm tra event ID và transaction strategy |
| Test chạy local nhưng CI FAIL | Khác dependency versions, artifact cache hoặc binder config | Ghi resolved versions và stub checksum |

### Phân biệt trigger thất bại và handler thất bại

- Nếu `stubTrigger.trigger(label)` trả `false`, kiểm tra **stub artifact và label** trước.
- Nếu trigger trả `true` nhưng không có shipment, kiểm tra **destination, binding, deserialization và consumer handler**.
- Nếu shipment được tạo nhưng dữ liệu sai, kiểm tra **payload schema và business mapping**.

Không đổi consumer code để chữa một stub artifact cũ hoặc sai label.

## 21. Kiểm tra nội dung stub artifact

Khi consumer không tìm thấy label hoặc message, cần xác minh producer đã đóng gói đúng artifact.

Những điều cần kiểm tra:

1. Artifact có đúng groupId/artifactId/version/classifier không?
2. Contract revision có phải revision producer đã verify?
3. Stub JAR có message mappings/resources không?
4. Label `order_paid` có trong stub metadata không?
5. Destination `orders.events` có đúng không?
6. Consumer có resolve đúng artifact thay vì cache cũ không?

Một release record nên ghi:

~~~yaml
producer:
  service: order-service
  version: "2.5.0"
  sourceCommit: "PRODUCER_COMMIT_THUC_TE"
contract:
  path: "contracts/orders/order-paid.yml"
  revision: "CONTRACT_REVISION_THUC_TE"
stub:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  sha256: "CHECKSUM_DO_CI_TINH"
consumer:
  service: shipping-service
  version: "1.4.0"
  resolvedStub: "com.example.orders:order-service:2.5.0:stubs"
~~~

Các giá trị commit/checksum là placeholders. CI phải lấy từ source và file artifact thật.

## 22. Nâng cấp bài tập: thêm event version và consumer validation

Mở rộng contract bằng field:

~~~yaml
body:
  eventId: EVT-ORD-1001-PAID
  eventType: ORDER_PAID
  schemaVersion: 1
  orderId: ORD-1001
  amount: 125000
  currency: VND
~~~

Consumer DTO thêm `schemaVersion` và kiểm tra:

- Version có thuộc tập consumer hỗ trợ không?
- Event type có đúng `ORDER_PAID` không?
- Amount có hợp lệ và currency được hỗ trợ không?
- Missing field khác explicit null như thế nào?
- Consumer cũ có bỏ qua field mới hay strict deserialization fail?

**Thêm field vào event không mặc định luôn tương thích.** Consumer cũ với strict parser có thể từ chối unknown properties. Hãy chạy consumer versions còn được hỗ trợ với stub mới.

## 23. Nâng cấp bài tập: negative case và event không hợp lệ

Có thể viết unit tests cho `ShippingService`:

~~~java
@Test
void rejectsUnexpectedEventType() {
    OrderPaidEvent event = new OrderPaidEvent(
        "EVT-1001",
        "ORDER_CANCELLED",
        "ORD-1001",
        new BigDecimal("125000"),
        "VND"
    );

    assertThatThrownBy(() ->
        shippingService.handleOrderPaid(event)
    ).isInstanceOf(IllegalArgumentException.class);
}
~~~

Test này kiểm tra business validation trực tiếp. Để xác minh end-to-end messaging, cần có contract/stub scenario phù hợp cho event đó hoặc test integration message adapter.

Không dùng một message stub hợp lệ rồi thay đổi event trong consumer assertion; hãy tạo fixture/scenario tách biệt để dễ hiểu và tái lập.

## 24. Nâng cấp bài tập: correlation và tracing headers

Khi hệ thống cần correlation ID, contract có thể thêm:

~~~yaml
outputMessage:
  sentTo: orders.events
  headers:
    contentType: application/json
    correlationId: CORR-ORD-1001
  body:
    eventId: EVT-ORD-1001-PAID
    eventType: ORDER_PAID
    orderId: ORD-1001
    amount: 125000
    currency: VND
~~~

Consumer có thể dùng header cho tracing/logging, nhưng cần phân biệt:

- **Message header** được truyền theo adapter.
- **Payload field** là dữ liệu trong body.
- **Trace context** có thể được tạo/propagate bởi framework instrumentation.

Không mặc định header trong contract được tự động chuyển thành MDC hoặc trace span. Nếu đây là acceptance criterion, viết consumer test/observability test phù hợp.

## 25. Tích hợp CI cho cả producer và consumer

~~~mermaid
flowchart TD
    A["Commit contract + producer code"] --> B["Producer CI"]
    B --> C["Generated message contract tests"]
    C --> D{"Producer output PASS?"}
    D -->|Không| X["BLOCK"]
    D -->|Có| E["Package stub artifact"]
    E --> F["GAV + checksum + provenance"]
    F --> G["Publish/Install stub"]
    G --> H["Consumer CI resolves exact stub"]
    H --> I["StubTrigger fires message"]
    I --> J["Consumer handler + business assertions"]
    J --> K{"Required consumer tests PASS?"}
    K -->|Không| X
    K -->|Có| L["Release evidence"]
~~~

### Producer CI gate

- Contract file được phát hiện.
- Generated producer tests được sinh và chạy.
- `triggeredBy` gọi application service thật.
- Message destination, headers và body đúng.
- Không có test bắt buộc bị skip.
- Stub artifact được tạo từ cùng contract revision.
- Artifact checksum/provenance được ghi.

### Consumer CI gate

- Stub Runner resolve đúng GAV/classifier/version.
- Message label được tìm thấy.
- `StubTrigger` phát message qua adapter test.
- Consumer binding nhận message.
- Handler tạo trạng thái nghiệp vụ đúng.
- Negative/idempotency tests PASS.
- Logs không lộ secrets hoặc dữ liệu nhạy cảm.

### Không coi hai gate là một

Producer CI PASS không chứng minh consumer code đã được kiểm tra. Consumer test PASS với stub cũ không chứng minh producer mới tương thích. Cả hai cần cùng **contract revision và stub artifact identity**.

## 26. Tiêu chí nghiệm thu dự án

| ID | Tiêu chí | Bằng chứng |
| --- | --- | --- |
| AC-01 | Message contract có label và destination rõ | `order-paid.yml` |
| AC-02 | Producer test kích hoạt service thật qua `triggeredBy` | Generated source/test report |
| AC-03 | Producer phát message đúng destination | Message verifier report |
| AC-04 | Headers và body khớp contract | Producer contract assertions |
| AC-05 | Stub artifact có classifier `stubs` | GAV và JAR |
| AC-06 | Consumer tải đúng artifact | Stub Runner resolved ID/version |
| AC-07 | `StubTrigger` kích hoạt label `order_paid` | Trigger result |
| AC-08 | Consumer function nhận payload JSON | Handler execution/evidence |
| AC-09 | Shipment được tạo đúng order/status | Repository assertions |
| AC-10 | Duplicate event không tạo shipment trùng | Idempotency test |
| AC-11 | Producer và consumer reports gắn với đúng revisions | CI metadata |
| AC-12 | Không dùng broker/credentials production trong contract tests | Test environment configuration |

**AC-07 không thay AC-08/AC-09.** Trigger thành công không có nghĩa consumer đã xử lý đúng message.

## 27. Bài tập mở rộng

### Bài tập A — Message label không khớp

Contract dùng `label: order_paid` nhưng test gọi `stubTrigger.trigger("paid_order")`.

**Yêu cầu:** dự đoán kết quả và cách kiểm tra artifact.

**Gợi ý:** label phải khớp; xem stub artifact chứa label nào và dùng đúng tên.

### Bài tập B — Destination lệch

Contract gửi `orders.events` nhưng consumer binding lắng nghe `order.events`.

**Yêu cầu:** vì sao trigger có thể thành công mà shipment không được tạo?

**Gợi ý:** stub được kích hoạt nhưng message đến destination khác binding; so `sentTo` và binding destination.

### Bài tập C — Producer trigger chỉ gửi payload hardcode

Base test gọi publisher trực tiếp với JSON mẫu, bỏ qua application service.

**Yêu cầu:** producer test còn chứng minh điều gì và bỏ sót điều gì?

**Gợi ý:** chỉ chứng minh đường publisher; không kiểm tra nghiệp vụ chuyển trạng thái và quyết định phát event.

### Bài tập D — Consumer gọi service trực tiếp

Consumer integration test gọi `shippingService.handleOrderPaid(event)` thay vì StubTrigger.

**Yêu cầu:** test này có chứng minh Stub Runner message delivery không?

**Gợi ý:** không; đó là service/unit test. Giữ nó như test bổ sung và thêm StubTrigger integration test.

### Bài tập E — Message body number/string

Contract quy định `amount` là number nhưng consumer DTO nhận `String`.

**Yêu cầu:** cần điều tra ở đâu?

**Gợi ý:** raw message payload, serializer/content type, DTO type và coercion; không nới contract tùy tiện.

### Bài tập F — Duplicate event

Hai lần trigger cùng label tạo hai shipment.

**Yêu cầu:** đề xuất cách bảo vệ idempotency.

**Gợi ý:** event ID, unique constraint, transaction/atomic insert và test lặp.

### Bài tập G — Consumer không nhận do test binder

StubTrigger trả true nhưng binding không được khởi tạo.

**Yêu cầu:** kiểm tra những gì?

**Gợi ý:** binder dependency, function definition, binding name, destination và message verifier adapter.

### Bài tập H — Stub cũ

Consumer test PASS với Order Service 2.4.0, trong khi producer đang chuẩn bị phát hành 2.5.0.

**Yêu cầu:** cần thay đổi gì trước khi kết luận tương thích?

**Gợi ý:** producer verify 2.5.0, package/publish đúng stub, consumer resolve 2.5.0 và chạy lại.

### Bài tập I — Broker production bị dùng nhầm

Test profile vô tình lấy Kafka bootstrap server từ environment dùng chung.

**Yêu cầu:** cách giảm rủi ro?

**Gợi ý:** test binder hoặc broker test cô lập, credentials test-only, egress restrictions và fail-fast config validation.

### Bài tập J — Thêm schemaVersion

Producer thêm `schemaVersion: 2`, consumer cũ dùng strict JSON deserializer.

**Yêu cầu:** thay đổi additive có thể breaking không? Cần test versions nào?

**Gợi ý:** có thể breaking; chạy các consumer versions còn hỗ trợ với stub mới và lập migration strategy.

## 28. Checklist hoàn thành lab

### Contract và producer

- [ ] `order-paid.yml` có label `order_paid`.
- [ ] `outputMessage.sentTo` là `orders.events`.
- [ ] Header content type là JSON.
- [ ] Body field/type rõ ràng.
- [ ] `triggeredBy` gọi đúng phương thức base test.
- [ ] Base test seed fixture trong môi trường cô lập.
- [ ] Producer application service thật thực hiện chuyển trạng thái và publish event.
- [ ] Generated producer message test được sinh và chạy PASS.
- [ ] Producer test xác minh destination, headers và payload.
- [ ] Không có generated tests bắt buộc bị skip.

### Stub artifact

- [ ] Stub JAR được đóng gói.
- [ ] Classifier là `stubs`.
- [ ] GAV/version đúng producer release.
- [ ] Artifact chứa message stub và label đúng.
- [ ] Contract revision, producer commit và checksum được ghi.
- [ ] Consumer test dùng đúng artifact, không phải cache/version cũ.

### Consumer

- [ ] `StubTrigger` được inject từ Stub Runner.
- [ ] `trigger("order_paid")` trả thành công.
- [ ] Consumer binding lắng nghe `orders.events`.
- [ ] JSON được deserialize đúng DTO.
- [ ] Handler nghiệp vụ được thực thi.
- [ ] Shipment được tạo đúng order/event ID/status.
- [ ] Duplicate event được xử lý idempotent.
- [ ] Consumer test kiểm tra business outcome, không chỉ trigger result.
- [ ] Không gọi service method trực tiếp thay thế đường messaging trong integration test.

### CI và an toàn

- [ ] Boot/Cloud/Contract plugin versions là tổ hợp đã xác minh.
- [ ] Test binder/broker đúng cấu hình, không dùng production destination.
- [ ] Async assertions có timeout hữu hạn.
- [ ] Test data và cleanup có phạm vi.
- [ ] Không log secrets/PII.
- [ ] Producer và consumer reports có thể truy vết.
- [ ] Release gate phân biệt producer verification và consumer verification.
- [ ] Giới hạn của test binder so với broker thật được ghi rõ.

## Kết luận

Dự án **Kích hoạt messaging stub và kiểm chứng mã consumer** hoàn thành khi hai phía có bằng chứng độc lập nhưng liên kết bằng cùng một message contract. Ở phía producer, generated test dùng `triggeredBy` để chạy application service và xác minh message thật được phát ra đúng destination, headers và body. Ở phía consumer, Stub Runner tải stub artifact, `StubTrigger` kích hoạt message theo label, message đi qua binding và gọi consumer code; assertions kiểm tra **shipment thực sự được tạo và xử lý lặp an toàn**.

**Ghi nhớ:** *Producer triggeredBy xác minh producer phát message; consumer StubTrigger kích hoạt message stub; business assertions mới chứng minh consumer xử lý đúng. Đừng dừng ở việc stub được kích hoạt thành công.*
