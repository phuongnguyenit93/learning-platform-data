# Dùng FunctionFlowBuilder trong luồng Spring Integration

## 1. Bài toán thực hành

Trong **Spring Cloud Function** (**SPRING_CLOUD_FUNCTION**), ta đóng gói logic nghiệp vụ thành **Supplier**, **Function** và **Consumer** để có thể tái sử dụng qua nhiều môi trường gọi. **FunctionCatalog** đăng ký và tra cứu các functional bean; Spring Integration cung cấp các message channel, endpoint và Enterprise Integration Patterns để kết nối những bước xử lý thành một luồng.

Trong bài này, ta xây dựng một luồng nhận lệnh xử lý đơn hàng:

1. Một message đi vào channel **ordersInput**.
2. **wireTap** gửi một bản sao message thô sang channel quan sát.
3. **normalizeOrder** chuẩn hóa mã đơn.
4. **validateOrder** kiểm tra dữ liệu.
5. **calculateTotal** tính tổng tiền.
6. **storeOrder** nhận kết quả và ghi vào một hàng đợi quan sát trong lab.

Ta sẽ dùng **FunctionFlowBuilder** để kết nối các functional bean theo tên trong **FunctionCatalog**:

~~~text
Message<OrderCommand>
       |
       v
  ordersInput
       |
       +-----------------------> rawOrdersChannel
       |                           (wireTap)
       v
 normalizeOrder
       |
       v
 validateOrder
       |
       v
 calculateTotal
       |
       v
   storeOrder
       |
       v
 BlockingQueue<PricedOrder>
~~~

**Mục tiêu:** hiểu cách Spring Cloud Function và Spring Integration DSL phối hợp với nhau, thực hành các thao tác **from**, **fromSupplier**, **apply** và **accept**, đồng thời kiểm thử một IntegrationFlow chạy thật trong Spring context.

Sau bài này, bạn có thể:

- Giải thích vai trò của **FunctionFlowBuilder** và **FunctionFlowDefinition**.
- Tra cứu Supplier, Function và Consumer bằng tên từ FunctionCatalog.
- Tạo IntegrationFlow từ một message channel.
- Kết hợp nhiều function bằng apply và composition.
- Kết thúc flow bằng Consumer qua accept.
- Dùng wireTap để quan sát message mà không thay đổi payload của nhánh chính.
- Phân biệt DirectChannel và QueueChannel.
- Kiểm thử flow bằng Spring Boot Test và FunctionCatalog.
- Dùng fromSupplier cùng poller khi cần tạo message theo lịch.

## 2. FunctionFlowBuilder là gì?

Spring Integration cung cấp DSL để khai báo một **IntegrationFlow** bằng các endpoint như transform, filter, handle, route, wireTap, log và channel. Spring Cloud Function bổ sung module **spring-cloud-function-integration** để DSL này tra cứu các functional bean qua **FunctionCatalog**.

Từ Spring Cloud Function **4.0.3**, module tích hợp cung cấp **FunctionFlowBuilder**. Spring tự động cấu hình builder và kết nối nó với FunctionCatalog. Ta có thể inject builder vào một phương thức @Bean để khai báo IntegrationFlow.

Các thao tác chính:

| API | Vai trò |
| --- | --- |
| **from(channelName)** | Bắt đầu flow từ một Spring Integration channel |
| **fromSupplier(supplierName)** | Tra cứu Supplier trong FunctionCatalog để làm nguồn |
| **apply(functionName)** | Tra cứu Function và thêm nó vào flow |
| **accept(consumerName)** | Tra cứu Consumer và thêm nó làm bước nhận cuối |
| **wireTap(channelName)** | Gửi bản sao message sang một channel phụ |
| **log(level)** | Thêm endpoint ghi log |

FunctionFlowBuilder trả về một định nghĩa flow có hỗ trợ DSL của Spring Integration. Khi gọi **apply("normalizeOrder")**, builder tra cứu function có tên đó trong FunctionCatalog; ta không phải tự inject bean rồi viết một service activator thủ công.

### 2.1. FunctionFlowBuilder và IntegrationFlowBuilder

Hai khái niệm có quan hệ nhưng vai trò khác nhau:

- **IntegrationFlowBuilder** là DSL tổng quát của Spring Integration để khai báo message flow.
- **FunctionFlowBuilder** bổ sung điểm vào và các toán tử tra cứu functional bean qua FunctionCatalog.
- **FunctionFlowDefinition** là phần mở rộng của IntegrationFlow DSL, cung cấp apply và accept.

Nhờ vậy, ta có thể xen kẽ function của Spring Cloud Function với endpoint chuẩn của Spring Integration:

~~~java
return functionFlowBuilder
        .from("ordersInput")
        .wireTap("rawOrdersChannel")
        .apply("normalizeOrder")
        .apply("calculateTotal")
        .log(LoggingHandler.Level.INFO)
        .accept("storeOrder");
~~~

Đây là một flow duy nhất. Các function được tìm theo tên trong catalog, còn wireTap và log là endpoint của Spring Integration.

### 2.2. Khi nào nên dùng FunctionFlowBuilder?

Dùng FunctionFlowBuilder khi:

- Ứng dụng đã khai báo logic dưới dạng functional bean.
- Muốn lắp ghép các function theo tên, có thể dùng cả composition.
- Muốn tận dụng message channel, poller, wireTap, router hoặc các Enterprise Integration Patterns.
- Muốn tích hợp các function được cung cấp bởi thư viện hoặc auto-configuration khác.

Nếu một flow chỉ dùng các endpoint Spring Integration thông thường và không cần tra cứu function trong FunctionCatalog, IntegrationFlow DSL chuẩn cũng phù hợp. FunctionFlowBuilder hữu ích khi muốn kết nối hai mô hình này.

## 3. Chuẩn bị dự án Maven

Lab dùng **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0** và **Spring Cloud 2025.0.0**. BOM Spring Cloud quản lý version cho các module Spring Cloud Function. Với dự án mới, hãy chọn release train tương thích với Spring Boot đang dùng và cập nhật bản vá được hỗ trợ.

Tạo thư mục:

~~~text
function-flow-builder-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/flowlab/
    │   │   ├── FlowLabApplication.java
    │   │   ├── OrderCommand.java
    │   │   ├── NormalizedOrder.java
    │   │   ├── PricedOrder.java
    │   │   ├── OrderFunctions.java
    │   │   └── OrderIntegrationConfiguration.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/flowlab/
            ├── OrderFunctionsTest.java
            └── OrderIntegrationFlowTest.java
~~~

Tất cả lớp Java dùng package **com.example.flowlab**.

### 3.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>function-flow-builder-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>function-flow-builder-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
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
            <artifactId>spring-cloud-function-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-integration</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-integration</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Vai trò dependency:

| Artifact | Vai trò |
| --- | --- |
| **spring-cloud-function-context** | FunctionCatalog và functional bean |
| **spring-cloud-function-integration** | FunctionFlowBuilder và auto-configuration tích hợp |
| **spring-boot-starter-integration** | Spring Integration channels, endpoints và Java DSL |
| **spring-boot-starter-test** | JUnit 5, Spring Boot Test và assertion |

Module **spring-cloud-function-integration** đã kéo các dependency Spring Integration cần thiết theo dependency graph của nó. Ta khai báo starter integration trực tiếp trong ví dụ để thể hiện rõ ứng dụng dùng Spring Integration DSL.

## 4. Tạo model đơn hàng

### 4.1. OrderCommand.java

~~~java
package com.example.flowlab;

public record OrderCommand(
        String orderId,
        int quantity,
        long unitPriceVnd) {
}
~~~

Đây là payload đầu vào do hệ thống upstream gửi vào channel.

### 4.2. NormalizedOrder.java

~~~java
package com.example.flowlab;

public record NormalizedOrder(
        String orderId,
        int quantity,
        long unitPriceVnd) {
}
~~~

Kiểu trung gian sau khi chuẩn hóa mã đơn.

### 4.3. PricedOrder.java

~~~java
package com.example.flowlab;

public record PricedOrder(
        String orderId,
        int quantity,
        long unitPriceVnd,
        long totalVnd,
        String status) {
}
~~~

Kiểu kết quả được consumer cuối nhận. Tách kiểu theo từng bước giúp chữ ký generic của các function thể hiện hợp đồng dữ liệu.

## 5. Khai báo functional bean

Tạo **OrderFunctions.java**:

~~~java
package com.example.flowlab;

import java.util.Locale;
import java.util.concurrent.BlockingQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderFunctions {

    @Bean
    public Function<OrderCommand, NormalizedOrder> normalizeOrder() {
        return command -> {
            if (command == null) {
                throw new IllegalArgumentException(
                        "order command is required");
            }
            if (command.orderId() == null
                    || command.orderId().isBlank()) {
                throw new IllegalArgumentException(
                        "orderId is required");
            }

            return new NormalizedOrder(
                    command.orderId().trim().toUpperCase(Locale.ROOT),
                    command.quantity(),
                    command.unitPriceVnd());
        };
    }

    @Bean
    public Function<NormalizedOrder, NormalizedOrder> validateOrder() {
        return order -> {
            if (order.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (order.unitPriceVnd() <= 0) {
                throw new IllegalArgumentException(
                        "unitPriceVnd must be positive");
            }
            return order;
        };
    }

    @Bean
    public Function<NormalizedOrder, PricedOrder> calculateTotal() {
        return order -> {
            long total = Math.multiplyExact(
                    order.unitPriceVnd(),
                    order.quantity());

            return new PricedOrder(
                    order.orderId(),
                    order.quantity(),
                    order.unitPriceVnd(),
                    total,
                    "ACCEPTED");
        };
    }

    @Bean
    public Consumer<PricedOrder> storeOrder(
            BlockingQueue<PricedOrder> processedOrders) {
        return processedOrders::add;
    }
}
~~~

Các bean:

| Bean | Chữ ký | Trách nhiệm |
| --- | --- | --- |
| **normalizeOrder** | Function<OrderCommand, NormalizedOrder> | Chuẩn hóa mã đơn |
| **validateOrder** | Function<NormalizedOrder, NormalizedOrder> | Kiểm tra số lượng và đơn giá |
| **calculateTotal** | Function<NormalizedOrder, PricedOrder> | Tính tổng tiền và tạo kết quả |
| **storeOrder** | Consumer<PricedOrder> | Nhận kết quả cuối và ghi vào queue quan sát |

### 5.1. Vì sao Consumer ở cuối flow?

Consumer nhận payload nhưng không trả về payload mới. Do đó, **accept("storeOrder")** là điểm kết thúc phù hợp cho flow này.

Nếu cần tiếp tục xử lý sau khi lưu, hãy thiết kế một function trả về kết quả hoặc phát một message sang channel khác. Không kỳ vọng Consumer trả lại PricedOrder để nối thêm một bước apply.

### 5.2. Kiểm soát overflow

Phép nhân số lượng và đơn giá dùng **Math.multiplyExact**. Nếu kết quả vượt giới hạn kiểu long, Java ném ArithmeticException thay vì âm thầm trả số bị overflow.

Trong ứng dụng thực, cần xác định rõ đơn vị tiền, giới hạn quantity và mức giá tối đa. Lab dùng số nguyên VND để tập trung vào luồng tích hợp.

## 6. Cấu hình Spring Integration channels

Tạo **OrderIntegrationConfiguration.java**:

~~~java
package com.example.flowlab;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.cloud.function.context.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class OrderIntegrationConfiguration {

    @Bean
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel rawOrdersChannel() {
        return new QueueChannel();
    }

    @Bean
    public BlockingQueue<PricedOrder> processedOrders() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    public IntegrationFlow orderProcessingFlow(
            FunctionFlowBuilder functionFlowBuilder) {

        return functionFlowBuilder
                .from("ordersInput")
                .wireTap("rawOrdersChannel")
                .apply("normalizeOrder|validateOrder")
                .apply("calculateTotal")
                .accept("storeOrder");
    }
}
~~~

### 6.1. Phân tích cấu hình flow

**from("ordersInput")**

Spring Integration bắt đầu nhận message từ bean channel có tên **ordersInput**. Đây là DirectChannel nên message được chuyển đồng bộ tới subscriber của flow trong thread gửi message.

**wireTap("rawOrdersChannel")**

WireTap gửi một bản sao message sang channel phụ để quan sát hoặc audit. Nhánh chính vẫn tiếp tục xử lý payload gốc.

**apply("normalizeOrder|validateOrder")**

FunctionFlowBuilder tra cứu composition trong FunctionCatalog. Output của normalizeOrder là NormalizedOrder, đúng kiểu input của validateOrder. Hai function được kết hợp thành một bước.

**apply("calculateTotal")**

Tra cứu function tính tổng tiền và nối nó sau composition trước đó.

**accept("storeOrder")**

Tra cứu Consumer trong catalog và kết thúc flow bằng consumer này.

### 6.2. Tại sao tên function phải đúng?

Các tên trong apply và accept là tên bean functional đã đăng ký:

~~~text
normalizeOrder
validateOrder
calculateTotal
storeOrder
~~~

FunctionFlowBuilder dùng FunctionCatalog để tra cứu. Nếu tên sai, bean không có trong catalog hoặc chữ ký kiểu không tương thích, flow không thể được tạo/khởi động đúng.

### 6.3. Tại sao dùng composition trong apply?

FunctionCatalog hỗ trợ composition theo tên. Biểu thức:

~~~text
normalizeOrder|validateOrder
~~~

có nghĩa output của normalizeOrder được chuyển thành input của validateOrder. Dấu pipe là composition của Spring Cloud Function, không phải dấu phân cách các channel.

Có thể viết thành hai lần apply:

~~~java
.apply("normalizeOrder")
.apply("validateOrder")
~~~

Hai cách đều thể hiện cùng thứ tự nghiệp vụ. Composition giúp nhóm các bước function thành một định nghĩa khi cần tái sử dụng.

## 7. Khởi tạo Spring Boot

Tạo **FlowLabApplication.java**:

~~~java
package com.example.flowlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlowLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlowLabApplication.class, args);
    }
}
~~~

Tạo **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: function-flow-builder-lab
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

Ta tra cứu function theo tên cụ thể trong flow nên không cần cấu hình **spring.cloud.function.definition** cho bài lab. Thuộc tính này thường được dùng khi một adapter khác như Spring Cloud Stream cần chọn function/composition để bind.

## 8. Kiểm thử function độc lập

Tạo **OrderFunctionsTest.java**:

~~~java
package com.example.flowlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderFunctionsTest {

    private final OrderFunctions functions = new OrderFunctions();

    @Test
    void normalizesOrderId() {
        NormalizedOrder result = functions.normalizeOrder().apply(
                new OrderCommand(" o-801 ", 2, 150_000L));

        assertEquals(
                new NormalizedOrder("O-801", 2, 150_000L),
                result);
    }

    @Test
    void validatesQuantity() {
        NormalizedOrder invalid =
                new NormalizedOrder("O-802", 0, 100L);

        assertThrows(
                IllegalArgumentException.class,
                () -> functions.validateOrder().apply(invalid));
    }

    @Test
    void calculatesTotal() {
        PricedOrder result = functions.calculateTotal().apply(
                new NormalizedOrder("O-803", 3, 250_000L));

        assertEquals(
                new PricedOrder(
                        "O-803", 3, 250_000L, 750_000L, "ACCEPTED"),
                result);
    }

    @Test
    void detectsAmountOverflow() {
        NormalizedOrder tooLarge =
                new NormalizedOrder("O-804", 2, Long.MAX_VALUE);

        assertThrows(
                ArithmeticException.class,
                () -> functions.calculateTotal().apply(tooLarge));
    }

    @Test
    void catalogStyleCompositionHasCompatibleTypes() {
        Function<OrderCommand, NormalizedOrder> normalize =
                functions.normalizeOrder();
        Function<NormalizedOrder, NormalizedOrder> validate =
                functions.validateOrder();

        NormalizedOrder result =
                normalize.andThen(validate).apply(
                        new OrderCommand(" o-805 ", 1, 50_000L));

        assertEquals("O-805", result.orderId());
    }
}
~~~

Các unit test xác minh từng function và tương thích kiểu giữa hai bước đầu. Chúng chưa kiểm tra FunctionCatalog hoặc IntegrationFlow.

## 9. Kiểm thử FunctionCatalog và IntegrationFlow

Tạo **OrderIntegrationFlowTest.java**:

~~~java
package com.example.flowlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(classes = FlowLabApplication.class)
class OrderIntegrationFlowTest {

    @Autowired
    private FunctionCatalog functionCatalog;

    @Autowired
    private DirectChannel ordersInput;

    @Autowired
    private QueueChannel rawOrdersChannel;

    @Autowired
    private BlockingQueue<PricedOrder> processedOrders;

    @BeforeEach
    void clearQueues() {
        processedOrders.clear();
        while (rawOrdersChannel.receive(0) != null) {
            // Xóa message quan sát còn lại từ test trước.
        }
    }

    @Test
    void functionsAreRegisteredInCatalog() {
        Function<OrderCommand, NormalizedOrder> normalize =
                functionCatalog.lookup("normalizeOrder");
        Function<NormalizedOrder, NormalizedOrder> validate =
                functionCatalog.lookup("validateOrder");
        Function<NormalizedOrder, PricedOrder> calculate =
                functionCatalog.lookup("calculateTotal");

        assertNotNull(normalize);
        assertNotNull(validate);
        assertNotNull(calculate);
    }

    @Test
    void catalogCanResolveFunctionComposition() {
        Function<OrderCommand, NormalizedOrder> normalizeAndValidate =
                functionCatalog.lookup("normalizeOrder|validateOrder");

        assertNotNull(normalizeAndValidate);

        NormalizedOrder result = normalizeAndValidate.apply(
                new OrderCommand(" o-901 ", 2, 100_000L));

        assertEquals(
                new NormalizedOrder("O-901", 2, 100_000L),
                result);
    }

    @Test
    void integrationFlowAppliesFunctionsAndAcceptsConsumer()
            throws InterruptedException {

        OrderCommand command =
                new OrderCommand(" o-902 ", 3, 250_000L);

        Message<OrderCommand> message = MessageBuilder
                .withPayload(command)
                .setHeader("correlationId", "corr-902")
                .build();

        assertTrue(ordersInput.send(message));

        PricedOrder result = processedOrders.poll(
                1, TimeUnit.SECONDS);

        assertNotNull(result);
        assertEquals(
                new PricedOrder(
                        "O-902", 3, 250_000L, 750_000L, "ACCEPTED"),
                result);

        Message<?> tapped = rawOrdersChannel.receive(1_000);
        assertNotNull(tapped);
        assertEquals(command, tapped.getPayload());
        assertEquals(
                "corr-902",
                tapped.getHeaders().get("correlationId"));
    }

    @Test
    void invalidOrderDoesNotReachTheConsumer() {
        OrderCommand invalid =
                new OrderCommand("O-903", 0, 250_000L);

        Message<OrderCommand> message =
                MessageBuilder.withPayload(invalid).build();

        assertThrows(
                RuntimeException.class,
                () -> ordersInput.send(message));

        assertTrue(processedOrders.isEmpty());
    }
}
~~~

### 9.1. Test đang chứng minh điều gì?

| Test | Điều được xác minh |
| --- | --- |
| **functionsAreRegisteredInCatalog** | Các functional bean được đăng ký trong FunctionCatalog |
| **catalogCanResolveFunctionComposition** | Catalog tra cứu được composition bằng dấu pipe |
| **integrationFlowAppliesFunctionsAndAcceptsConsumer** | Message đi từ channel qua function chain và tới Consumer |
| **invalidOrderDoesNotReachTheConsumer** | Validation lỗi làm dừng flow trước consumer cuối |

Test flow dùng **DirectChannel** để gửi message đồng bộ. Khi send trả về, các endpoint synchronous đã xử lý message hoặc ném exception. Consumer cuối ghi PricedOrder vào BlockingQueue để test có thể đọc kết quả.

### 9.2. Kiểm tra wireTap

Test lấy message từ **rawOrdersChannel** và xác nhận:

- Payload vẫn là OrderCommand ban đầu.
- Header correlationId được giữ trong nhánh quan sát.
- Nhánh chính vẫn tiếp tục normalize, validate và calculate.

WireTap không thay thế nhánh chính. Nếu channel quan sát bị đầy hoặc không được tiêu thụ, cần thiết kế capacity và chính sách xử lý phù hợp với yêu cầu vận hành.

### 9.3. Vì sao test exception dùng RuntimeException?

Spring Integration có thể bọc exception từ endpoint trong một exception của tầng messaging. Vì vậy, test flow có thể kiểm tra nhóm RuntimeException để xác nhận message thất bại. Unit test của validateOrder vẫn kiểm tra chính xác IllegalArgumentException ở tầng nghiệp vụ.

## 10. DirectChannel và QueueChannel

Spring Integration dùng channel để kết nối producer và consumer. Hai channel trong lab có semantics khác nhau:

| Đặc điểm | DirectChannel | QueueChannel |
| --- | --- | --- |
| Kiểu | SubscribableChannel | PollableChannel |
| Gửi message | Gọi subscriber trong thread gửi | Đưa message vào hàng đợi |
| Xử lý | Thường đồng bộ | Consumer nhận message bằng receive/poller |
| Phù hợp | Điểm vào flow cần xử lý ngay | Buffer, quan sát hoặc tách nhịp producer/consumer |
| Trong lab | ordersInput | rawOrdersChannel |

### 10.1. DirectChannel

DirectChannel chuyển message tới subscriber trong cùng luồng gọi. Nó hữu ích khi muốn kiểm thử flow đơn giản bằng cách gọi send và kiểm tra kết quả ngay sau đó.

Trong production, xử lý đồng bộ có thể khiến thời gian send phụ thuộc thời gian xử lý downstream. Nếu cần tách tải hoặc chạy bất đồng bộ, hãy cân nhắc ExecutorChannel hoặc broker adapter và cấu hình concurrency phù hợp.

### 10.2. QueueChannel

QueueChannel lưu message trong bộ nhớ để consumer nhận sau. Trong lab, nó được dùng làm nhánh wireTap để quan sát input.

QueueChannel không tự biến thành message broker bền vững. Message trong queue bộ nhớ không có durability sau khi process dừng; muốn lưu bền hoặc phân phối giữa instance, cần broker/adapter phù hợp.

## 11. Dùng fromSupplier để tạo nguồn message

FunctionFlowBuilder còn có **fromSupplier** để tra cứu một Supplier từ FunctionCatalog. Đây là lựa chọn khi flow bắt đầu từ nguồn do ứng dụng tạo thay vì channel nhận message.

Ví dụ khai báo Supplier:

~~~java
import java.util.function.Supplier;

@Bean
public Supplier<OrderCommand> demoOrderSupplier() {
    return () -> new OrderCommand(
            "O-DEMO",
            2,
            125_000L);
}
~~~

Có thể tạo flow được kích hoạt bởi poller:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.integration.dsl.Pollers;

@Bean
@Profile("polling-demo")
public IntegrationFlow supplierOrderFlow(
        FunctionFlowBuilder functionFlowBuilder) {

    return functionFlowBuilder
            .fromSupplier(
                    "demoOrderSupplier",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(5_000)))
            .apply("normalizeOrder|validateOrder")
            .apply("calculateTotal")
            .accept("storeOrder");
}
~~~

Flow này gọi Supplier theo chu kỳ 5 giây. Nó dùng cùng các function và consumer như flow nhận channel. Profile **polling-demo** giúp chỉ bật flow định kỳ khi chủ động yêu cầu:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=polling-demo
~~~

Không bật profile này trong test flow chính vì poller sẽ tự phát sinh đơn mẫu theo lịch và làm thay đổi trạng thái queue.

### 11.1. Poller có ý nghĩa gì?

Supplier không có input channel để tự nhận message. Poller là cơ chế kích hoạt MessageSource/Supplier theo lịch. Tùy nguồn:

- Dùng fixedDelay để chạy sau một khoảng chờ tính từ lần poll trước.
- Dùng fixedRate khi muốn lịch phát theo chu kỳ cố định.
- Dùng trigger riêng nếu lịch phức tạp.

Supplier tạo dữ liệu; poller quyết định khi nào gọi Supplier. Đây là hai trách nhiệm khác nhau.

### 11.2. Supplier vô hạn và nguồn hữu hạn

Supplier thông thường có thể trả về một giá trị ở mỗi lần gọi. Với Supplier reactive như Supplier<Flux<T>>, nó có thể biểu diễn một stream. Khi Supplier trả stream hữu hạn và cần poll lại, phải xem xét cơ chế poller và semantics của framework; không giả định Spring Cloud Function tự poll lại mọi reactive Supplier.

## 12. Dùng IntegrationFlow DSL ngoài apply/accept

FunctionFlowBuilder vẫn cho phép sử dụng các endpoint Spring Integration chuẩn.

### 12.1. Thêm log

~~~java
import org.springframework.integration.handler.LoggingHandler;

return functionFlowBuilder
        .from("ordersInput")
        .apply("normalizeOrder|validateOrder")
        .log(LoggingHandler.Level.INFO)
        .apply("calculateTotal")
        .accept("storeOrder");
~~~

Log endpoint giúp quan sát message flow. Trong production, chỉ log metadata cần thiết; tránh log toàn bộ payload nếu chứa dữ liệu nhạy cảm.

### 12.2. Thêm transform

Nếu cần biến đổi dữ liệu phụ không nằm trong functional bean, có thể dùng transform:

~~~java
return functionFlowBuilder
        .from("ordersInput")
        .apply("normalizeOrder|validateOrder")
        .<NormalizedOrder, String>transform(
                order -> order.orderId() + ":" + order.quantity())
        .accept("storeOrderSummary");
~~~

Ở ví dụ này, phải có Consumer **storeOrderSummary** nhận String. Kiểu output của transform phải tương thích với kiểu input của Consumer cuối.

### 12.3. Thêm filter

Có thể dùng filter để bỏ qua message không đáp ứng điều kiện:

~~~java
import org.springframework.integration.core.MessageSelector;

return functionFlowBuilder
        .from("ordersInput")
        .filter((MessageSelector) message ->
                message.getHeaders().containsKey("correlationId"))
        .apply("normalizeOrder|validateOrder")
        .apply("calculateTotal")
        .accept("storeOrder");
~~~

Filter kiểm tra message/header trước khi vào function. Nếu message bị loại, nó không đi tiếp nhánh chính; cần xác định rõ có cần discard channel hoặc audit nhánh bị loại hay không.

### 12.4. Composition trong accept

FunctionFlowDefinition.accept cũng dùng FunctionCatalog, vì vậy có thể truyền composition kết thúc bằng Consumer:

~~~java
return functionFlowBuilder
        .from("ordersInput")
        .accept("normalizeOrder|validateOrder|calculateTotal|storeOrder");
~~~

FunctionCatalog tra cứu cả chuỗi như một definition và kết thúc bằng Consumer. Tuy nhiên, trong flow dài, các lần apply riêng giúp nhìn thấy rõ điểm tích hợp với wireTap, filter, log hoặc router ở giữa.

## 13. Kiểm soát lỗi trong IntegrationFlow

Trong lab, validation ném IllegalArgumentException khi quantity hoặc unit price không hợp lệ. Exception có thể được bọc ở tầng Spring Integration messaging.

Một flow production cần quyết định:

- Message lỗi có làm dừng flow hiện tại không?
- Có gửi message lỗi sang error channel không?
- Có retry với lỗi tạm thời không?
- Lỗi dữ liệu vĩnh viễn có chuyển sang quarantine/dead-letter không?
- Consumer cuối có được gọi nếu bước trước lỗi không?

### 13.1. Error channel

Spring Integration hỗ trợ error channel để chuyển lỗi của message flow tới endpoint xử lý lỗi. Có thể khai báo một channel lỗi và subscriber để log/ghi nhận metadata:

~~~java
@Bean
public QueueChannel orderErrors() {
    return new QueueChannel();
}
~~~

Khi cấu hình error handling, cần nối lỗi của flow/endpoint tới channel phù hợp bằng cơ chế của Spring Integration hoặc error channel toàn cục. Không chỉ tạo một QueueChannel rồi giả định mọi exception tự động được chuyển vào đó.

### 13.2. Không retry mọi lỗi

Ví dụ:

| Lỗi | Chính sách thường cân nhắc |
| --- | --- |
| Thiếu orderId | Từ chối, không retry |
| Quantity âm | Từ chối, không retry |
| Database tạm mất kết nối | Retry có giới hạn |
| Hết thời gian gọi dịch vụ | Retry theo timeout/backoff |
| Schema không đọc được | Quarantine/DLQ, kiểm tra producer |
| Consumer nhận duplicate | Idempotency |

Retry vô hạn có thể giữ message lỗi trong flow, làm tắc các message hợp lệ. Cần đặt giới hạn số lần retry, backoff và nơi lưu message thất bại.

### 13.3. Consumer có side effect

Consumer **storeOrder** trong lab chỉ ghi vào BlockingQueue. Nếu thay bằng database hoặc API ngoài:

- Xác định transaction boundary.
- Dùng idempotency key để chống xử lý trùng.
- Không giả định wireTap và nhánh chính là một transaction atomic.
- Nếu flow có nhiều side effect, cân nhắc outbox hoặc saga.

## 14. FunctionFlowBuilder và FunctionCatalog

FunctionFlowBuilder sử dụng FunctionCatalog để tra cứu function theo tên. Vì vậy, các functional bean phải có tên ổn định và kiểu đầu vào/đầu ra tương thích.

### 14.1. Lookup function trực tiếp

~~~java
Function<NormalizedOrder, PricedOrder> calculate =
        functionCatalog.lookup("calculateTotal");
~~~

### 14.2. Lookup composition

~~~java
Function<OrderCommand, NormalizedOrder> normalizeAndValidate =
        functionCatalog.lookup("normalizeOrder|validateOrder");
~~~

### 14.3. Lookup Consumer

~~~java
Consumer<PricedOrder> store =
        functionCatalog.lookup("storeOrder");
~~~

Flow DSL thực hiện các lookup này thay ta. Test catalog trực tiếp hữu ích khi cần xác định bean đã đăng ký đúng trước khi điều tra endpoint.

### 14.4. FunctionCatalog có wrapper

FunctionCatalog có thể trả về function đã được framework instrument để hỗ trợ type conversion, composition và các tính năng khác. Vì vậy, khi gọi function qua catalog, nên kiểm tra hành vi và kiểu dữ liệu thay vì so sánh class implementation với bean gốc.

## 15. Phân biệt FunctionFlowBuilder với composition cấu hình

Có hai cách kết hợp function:

| Cách | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| Composition trong FunctionCatalog | normalizeOrder\|validateOrder\|calculateTotal | Muốn một định nghĩa function tổng hợp |
| FunctionFlowBuilder DSL | from → wireTap → apply → log → apply → accept | Cần trộn function với channel, endpoint và EIP |

Composition thuần tập trung vào nối input/output giữa các function. FunctionFlowBuilder cho phép đặt các endpoint Spring Integration giữa các bước.

Ví dụ:

~~~java
return functionFlowBuilder
        .from("ordersInput")
        .wireTap("rawOrdersChannel")
        .apply("normalizeOrder|validateOrder")
        .log(LoggingHandler.Level.INFO)
        .apply("calculateTotal")
        .accept("storeOrder");
~~~

Ở đây, wireTap và log không phải function nghiệp vụ; chúng là endpoint của integration flow.

## 16. Chạy và kiểm thử dự án

Trong thư mục **function-flow-builder-lab**, chạy:

~~~bash
java -version
mvn -version
mvn test
~~~

Các test cần pass:

| Nhóm | Kết quả |
| --- | --- |
| OrderFunctionsTest | Chuẩn hóa, validate, tính tiền và phát hiện overflow |
| FunctionCatalog test | Tra cứu function và composition thành công |
| IntegrationFlow test | Message qua channel đến Consumer cuối |
| WireTap test | Nhánh quan sát nhận payload/header gốc |
| Negative test | Dữ liệu sai không tới Consumer |

Nếu muốn quan sát log khi chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Ứng dụng không tự phát đơn hàng ở chế độ mặc định. Flow chờ message được gửi vào **ordersInput**. Để gửi message từ code hoặc một adapter khác, dùng channel/gateway hoặc thêm inbound adapter tương ứng.

## 17. Bài tập mở rộng

### Bài A — Thêm function enrichCustomer

Tạo Function<NormalizedOrder, EnrichedOrder> enrichCustomer để bổ sung nhóm khách hàng hoặc thông tin khách.

**Yêu cầu:**

- Thêm record EnrichedOrder.
- Đăng ký function bean.
- Chèn apply("enrichCustomer") trước calculateTotal.
- Kiểm tra kiểu output/input của các stage tương thích.

### Bài B — Thêm Consumer audit

Tạo Consumer<PricedOrder> auditOrder để ghi nhận mã đơn và tổng tiền vào BlockingQueue riêng.

**Yêu cầu:** dùng wireTap hoặc một nhánh channel riêng nếu muốn audit độc lập với consumer chính. Phân tích điều gì xảy ra nếu audit bị lỗi.

### Bài C — Dùng fromSupplier

Tạo Supplier<OrderCommand> demoOrderSupplier và flow polling mỗi 10 giây.

**Yêu cầu:** chỉ bật flow bằng profile riêng; kiểm tra Supplier tạo message và flow dùng lại composition normalizeOrder|validateOrder.

### Bài D — Thêm filter theo header

Chỉ cho message có header sourceSystem bằng PARTNER-A đi vào function chain.

**Yêu cầu:** test message được chấp nhận và bị loại; xác định cách quan sát message bị loại.

### Bài E — Thêm router theo loại đơn

Tạo router hoặc channel riêng cho đơn ưu tiên và đơn thường.

**Yêu cầu:** mô tả cách phân luồng bằng Spring Integration router, tên channel và Consumer đích. Không đặt logic định tuyến transport vào function tính tiền.

### Bài F — Chuyển từ QueueChannel sang broker

Thay nguồn DirectChannel bằng inbound adapter RabbitMQ hoặc Kafka.

**Yêu cầu:** giữ nguyên các functional bean; kiểm thử header mapping, retry, DLQ và idempotency qua broker.

## 18. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không inject được FunctionFlowBuilder | Thiếu spring-cloud-function-integration hoặc auto-configuration không chạy | Kiểm tra dependency và Spring context |
| FunctionFlowBuilder không tìm thấy function | Sai tên bean hoặc bean không phải functional bean | Kiểm tra @Bean và FunctionCatalog |
| apply composition báo lỗi kiểu | Output function trước không tương thích input function sau | Kiểm tra generic từng stage |
| accept không tìm thấy consumer | Tên consumer sai hoặc chưa được đăng ký | Kiểm tra catalog lookup |
| Flow không nhận message | Sai channel name hoặc channel bean chưa được tạo | Kiểm tra from("ordersInput") và tên bean |
| QueueChannel không phát message | Không có poller/consumer nhận queue | Phân biệt QueueChannel với DirectChannel |
| DirectChannel send bị chặn lâu | Downstream xử lý đồng bộ và chậm | Cân nhắc ExecutorChannel hoặc tách broker |
| WireTap không có dữ liệu | Sai channel name hoặc channel không phải bean | Kiểm tra rawOrdersChannel |
| Consumer nhận sai payload type | Kiểu generic không tương thích hoặc converter không phù hợp | Kiểm tra chữ ký Function/Consumer |
| Poller tạo message quá thường xuyên | fixedDelay/fixedRate không phù hợp | Điều chỉnh poller và giới hạn concurrency |
| Test bị nhiễu bởi Supplier định kỳ | Polling flow chạy trong test context | Dùng @Profile hoặc @ConditionalOnProperty |
| FunctionCatalog lookup trả null | Function chưa đăng ký hoặc bị loại khỏi catalog | Kiểm tra bean name và ineligible definitions |
| Exception không vào error channel mong muốn | Chưa cấu hình error handling cho endpoint/flow | Cấu hình error channel và test riêng |
| Audit chạy nhưng xử lý chính lỗi | WireTap là nhánh độc lập, không phải transaction | Thiết kế idempotency và error policy |

### 18.1. Trình tự debug

1. Kiểm tra JDK và Maven.
2. Xác nhận module spring-cloud-function-integration có trong classpath.
3. Xác nhận Spring tạo FunctionFlowBuilder.
4. Lookup từng functional bean qua FunctionCatalog.
5. Lookup composition để kiểm tra type compatibility.
6. Kiểm tra channel bean và tên truyền vào from/wireTap.
7. Gửi message trực tiếp qua DirectChannel.
8. Quan sát kết quả ở Consumer queue và QueueChannel wireTap.
9. Sau cùng mới thêm poller, inbound adapter hoặc broker.

## 19. Tiêu chí hoàn thành

| Tiêu chí | Minh chứng |
| --- | --- |
| Có FunctionFlowBuilder | Spring context inject builder thành công |
| Functional beans | normalizeOrder, validateOrder, calculateTotal và storeOrder |
| FunctionCatalog | Lookup function và composition theo tên |
| IntegrationFlow | from channel, apply function và accept consumer |
| Enterprise Integration Pattern | wireTap quan sát message thô |
| Channel semantics | Phân biệt DirectChannel và QueueChannel |
| Supplier source | Hiểu fromSupplier và poller |
| Error handling | Dữ liệu lỗi không đến consumer cuối |
| Kiểm thử | Unit test và Spring Boot IntegrationFlow test |
| Hiểu giới hạn | QueueChannel là bộ nhớ, không phải broker bền vững |

**Tóm tắt:** FunctionFlowBuilder là cầu nối giữa FunctionCatalog của Spring Cloud Function và IntegrationFlow DSL của Spring Integration. Dùng from hoặc fromSupplier để tạo điểm vào, apply để tra cứu và nối Function, accept để kết thúc bằng Consumer. Có thể xen kẽ wireTap, log, filter và các endpoint khác của Spring Integration để tạo một luồng message có cấu trúc, trong khi logic nghiệp vụ vẫn nằm trong các functional bean có thể tái sử dụng.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Module nào cung cấp FunctionFlowBuilder?

**Đáp án:** spring-cloud-function-integration.

**Câu 2.** FunctionFlowBuilder lấy Function và Consumer từ đâu?

**Đáp án:** Từ FunctionCatalog theo tên definition được truyền vào apply hoặc accept.

**Câu 3.** from("ordersInput") bắt đầu flow từ đâu?

**Đáp án:** Từ Spring Integration channel có tên ordersInput.

**Câu 4.** fromSupplier khác from như thế nào?

**Đáp án:** from bắt đầu từ channel/message source đã khai báo; fromSupplier tra cứu Supplier trong FunctionCatalog và dùng nó làm nguồn, thường kết hợp poller.

**Câu 5.** apply("normalizeOrder|validateOrder") có ý nghĩa gì?

**Đáp án:** Tra cứu composition gồm hai function; output của normalizeOrder là input của validateOrder.

**Câu 6.** accept("storeOrder") có trả payload tiếp theo cho flow không?

**Đáp án:** Không. Consumer nhận payload và không trả kết quả, vì vậy đây thường là bước cuối.

**Câu 7.** wireTap có thay đổi payload của nhánh chính không?

**Đáp án:** Không. Nó gửi một bản sao message sang channel phụ để quan sát.

**Câu 8.** DirectChannel khác QueueChannel ở điểm nào?

**Đáp án:** DirectChannel gọi subscriber đồng bộ trong thread gửi; QueueChannel lưu message trong hàng đợi để consumer nhận sau.

**Câu 9.** QueueChannel có bảo đảm message tồn tại sau khi ứng dụng khởi động lại không?

**Đáp án:** Không. Đây là queue trong bộ nhớ; cần broker hoặc persistence adapter nếu cần durability.

## Tài liệu tham khảo

- [Spring Cloud Function 4.3 — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/4.3/spring-integration.html)
- [Spring Cloud Function — Programming Model và FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/4.3/spring-cloud-function/programming-model.html)
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration — Wire Tap](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
- [Spring Integration — Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Java 17 — Supplier, Function và Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
