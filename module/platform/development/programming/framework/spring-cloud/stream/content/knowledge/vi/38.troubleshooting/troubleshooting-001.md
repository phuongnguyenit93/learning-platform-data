# Ứng dụng khởi động nhưng hàm không được liên kết

Một ứng dụng Spring Boot có thể khởi động thành công nhưng function không đọc hoặc ghi message qua broker. Nguyên nhân thường không nằm ở logic xử lý message mà ở một bước trước đó: bean function chưa được tạo, Spring Cloud Function chưa chọn đúng bean, Spring Cloud Stream chưa tạo binding, hoặc binding đã tạo nhưng chưa kết nối được destination.

Cần tách ba trạng thái:

1. **Function bean tồn tại:** Spring ApplicationContext đã đăng ký bean Supplier, Function hoặc Consumer.
2. **Function được chọn:** Spring Cloud Function biết bean nào được dùng làm message handler.
3. **Binding hoạt động:** Spring Cloud Stream đã nối input/output của function với destination thông qua binder.

Một ứng dụng có thể đạt trạng thái thứ nhất nhưng chưa đạt hai trạng thái còn lại. Một binding cũng có thể tồn tại nhưng không nhận message do destination, group, quyền broker hoặc cấu hình serializer sai. Bài học này cung cấp quy trình kiểm tra từ bean discovery đến broker để tìm đúng tầng đang lỗi.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt function bean, function definition, binding và destination.
- Kiểm tra bean có được Spring component scan và đăng ký vào ApplicationContext hay không.
- Chọn đúng function bằng spring.cloud.function.definition.
- Nhận biết lỗi khi có nhiều Supplier/Function/Consumer trong cùng ứng dụng.
- Suy ra binding name từ tên function và loại chữ ký.
- Cấu hình destination, group, binder và binding alias đúng tên.
- Phân biệt Supplier, Function, Consumer và chữ ký reactive.
- Kiểm tra binder dependency, provisioning, credentials và kết nối broker.
- Dùng startup logs, Actuator bindings và Test Binder để khoanh vùng lỗi.
- Thực hiện quy trình chẩn đoán có thứ tự và xác nhận bằng integration test.

## 1. Hiểu đúng các thành phần cần được liên kết

Trong Spring Cloud Stream, function là code xử lý dữ liệu; binding là cầu nối giữa function và hệ thống messaging; destination là topic, queue hoặc exchange ở broker; binder là implementation giao tiếp với broker.

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["Function bean"]
    B --> C["spring.cloud.function.definition"]
    C --> D["Spring Cloud Stream binding"]
    D --> E["Binder implementation"]
    E --> F["Kafka topic / RabbitMQ exchange-queue / Pulsar topic"]
    F --> G["Message delivery"]
    G --> H["Function invocation"]
~~~

Một function có thể tồn tại mà không được chọn. Một function được chọn có thể chưa có binder phù hợp. Một binding có thể được tạo nhưng ở trạng thái STOPPED hoặc không thể kết nối tới broker.

Vì vậy, khi ứng dụng khởi động nhưng không có message, không nên kết luận ngay rằng function không chạy. Trước hết hãy xác định tầng cuối cùng đã hoạt động.

## 2. Kiểm tra function bean có được đăng ký hay không

Spring Cloud Stream sử dụng Spring Cloud Function. Các bean có kiểu functional được nhận diện gồm:

- java.util.function.Supplier: tạo message đầu ra.
- java.util.function.Function: nhận message đầu vào và tạo message đầu ra.
- java.util.function.Consumer: nhận message đầu vào và không có đầu ra.

Ví dụ một function đơn giản:

~~~java
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderStreamApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderStreamApplication.class, args);
    }

    @Bean
    public Function<String, String> normalizeOrder() {
        return value -> value.trim().toUpperCase();
    }
}
~~~

Tên function bean trong ví dụ là normalizeOrder, được lấy từ tên phương thức @Bean. Spring Cloud Stream có thể dùng bean này làm message handler khi functional model được bật và function được chọn.

### Những nguyên nhân khiến bean không xuất hiện

**Cấu hình không nằm trong component scan**

Spring Boot mặc định scan package chứa class có @SpringBootApplication và các package con. Nếu lớp cấu hình khai báo function nằm ngoài phạm vi đó, bean method có thể không được đăng ký.

Ví dụ:

~~~text
com.acme.orders
  OrderStreamApplication.java
  functions/
    OrderFunctions.java

com.acme.shared
  SharedFunctionConfiguration.java
~~~

Nếu SharedFunctionConfiguration nằm ngoài package tree được scan, cần đưa nó vào phạm vi scan hoặc import cấu hình một cách rõ ràng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.boot.autoconfigure.SpringBootApplication;

import java.util.function.Consumer;

@Configuration
class SharedFunctionConfiguration {

    @Bean
    Consumer<String> auditOrder() {
        return value -> System.out.println("Audit: " + value);
    }
}

@SpringBootApplication
@Import(SharedFunctionConfiguration.class)
class OrderStreamApplication {
}
~~~

Không mở rộng component scan toàn bộ classpath một cách tùy tiện. Hãy xác định package chứa cấu hình function và đưa đúng package đó vào ApplicationContext.

**Bean bị điều kiện hóa**

Các annotation như @Profile, @ConditionalOnProperty, @ConditionalOnClass hoặc @ConditionalOnBean có thể khiến bean chỉ được tạo trong một môi trường nhất định.

~~~java
@Bean
@Profile("messaging")
Function<String, String> normalizeOrder() {
    return String::trim;
}
~~~

Nếu profile messaging không được kích hoạt, bean này không tồn tại. Kiểm tra active profiles, environment variables và property sources thực tế của môi trường chạy.

**Tên bean khác với tên được cấu hình**

~~~java
@Bean("normalize")
Function<String, String> normalizeOrder() {
    return String::trim;
}
~~~

Tên bean ở đây là normalize. Nếu cấu hình function definition trỏ tới normalizeOrder, Spring Cloud Function sẽ không tìm đúng bean theo tên đó. Tên bean được đặt tường minh trong @Bean có hiệu lực.

Tên bean có phân biệt chữ hoa/chữ thường. Hãy kiểm tra chính xác tên được đăng ký và tên trong cấu hình.

**Khai báo sai kiểu function**

Đảm bảo bean thực sự có kiểu Supplier, Function hoặc Consumer. Một service method thông thường không tự trở thành function chỉ vì nó có tham số hoặc trả về dữ liệu.

Nên khai báo generic type cụ thể:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return orderService::accept;
}
~~~

Tránh raw type như Function hoặc Consumer nếu không cần thiết. Generic type giúp framework xác định kiểu payload và chọn cơ chế conversion phù hợp.

### Kiểm tra bean từ ApplicationContext

Có thể thêm một probe tạm thời trong môi trường phát triển để xem functional beans đã được đăng ký:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class FunctionBeanProbe {

    private static final Logger log =
        LoggerFactory.getLogger(FunctionBeanProbe.class);

    @Bean
    ApplicationRunner reportFunctions(ApplicationContext context) {
        return args -> {
            log.info("Supplier beans: {}",
                context.getBeansOfType(Supplier.class).keySet());
            log.info("Function beans: {}",
                context.getBeansOfType(Function.class).keySet());
            log.info("Consumer beans: {}",
                context.getBeansOfType(Consumer.class).keySet());
        };
    }
}
~~~

Probe này chỉ xác nhận bean có mặt trong ApplicationContext. Nó chưa chứng minh function đã được Spring Cloud Stream chọn hoặc binding đã hoạt động. Sau khi chẩn đoán, bỏ probe nếu không còn cần thiết.

## 3. Chọn đúng function bằng spring.cloud.function.definition

Nếu ứng dụng chỉ có một functional bean, Spring Cloud Stream có thể tự phát hiện và liên kết bean đó. Tuy nhiên, tài liệu Spring khuyến nghị khai báo rõ spring.cloud.function.definition để tránh tự động phát hiện nhầm bean hoặc thay đổi hành vi khi ứng dụng phát triển.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
~~~

Một lỗi phổ biến là cấu hình nhầm property thành spring.cloud.stream.function.definition. Property dùng để chọn functional bean là:

~~~text
spring.cloud.function.definition
~~~

### Khi có nhiều function bean

Giả sử ứng dụng có hai function độc lập:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}

@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

Khi có nhiều functional beans, phải chỉ rõ function nào cần bind. Nếu muốn bind cả hai function độc lập, dùng dấu chấm phẩy:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase;reverse
~~~

Khi đó, mỗi function có bộ binding riêng:

- uppercase-in-0 và uppercase-out-0.
- reverse-in-0 và reverse-out-0.

### Phân biệt nhiều function độc lập và composition

Dấu chấm phẩy chọn nhiều function độc lập. Dấu pipe ghép nhiều function thành một pipeline:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|enrichOrder|validateOrder
~~~

Trong ví dụ, message đi lần lượt qua normalizeOrder, enrichOrder và validateOrder. Function được ghép phải có kiểu đầu ra tương thích với kiểu đầu vào của function tiếp theo.

Nếu chỉ muốn một function chạy độc lập, không đưa tên function khác vào definition. Nếu muốn ghép function, dùng pipe và kiểm tra đúng thứ tự xử lý.

### Auto-discovery bị tắt

Spring Cloud Stream có property:

~~~yaml
spring:
  cloud:
    stream:
      function:
        autodetect: false
~~~

Khi đặt false, cơ chế tự động phát hiện function bị tắt. Nếu không có function definition phù hợp hoặc binding được tạo tường minh, ứng dụng có thể khởi động mà không có function nào được liên kết.

Hãy tìm property này trong application.yml, profile-specific configuration, command-line arguments và environment variables. Một giá trị từ môi trường triển khai có thể ghi đè cấu hình trong file.

## 4. Kiểm tra chữ ký function và hướng message

Một function không có binding đầu vào/đầu ra tương ứng có thể khiến người vận hành tưởng rằng nó chưa được liên kết.

| Kiểu bean | Binding mặc định | Hướng hoạt động |
|---|---|---|
| Supplier<T> | supplierName-out-0 | Chỉ phát message |
| Consumer<T> | consumerName-in-0 | Chỉ nhận message |
| Function<T, R> | functionName-in-0 và functionName-out-0 | Nhận rồi phát message |

Ví dụ Consumer:

~~~java
@Bean
Consumer<OrderCreated> auditOrder() {
    return event -> auditService.record(event);
}
~~~

Consumer chỉ có input. Không có output binding là hành vi đúng.

Ví dụ Supplier:

~~~java
@Bean
Supplier<OrderCreated> orderSource() {
    return () -> orderService.nextPendingOrder();
}
~~~

Supplier chỉ có output. Nó không chờ một message từ input topic.

Ví dụ Function:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return orderService::accept;
}
~~~

Function có cả input và output.

### Supplier không phải listener

Supplier không tự subscribe vào destination. Supplier imperative được gọi bởi poller mặc định, thông thường mỗi giây một lần. Có thể điều chỉnh poller:

~~~yaml
spring:
  integration:
    poller:
      fixed-delay: 2000
      initial-delay: 500
~~~

Nếu dùng per-binding polling configuration, có thể cấu hình theo output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderSource-out-0:
          producer:
            poller:
              fixed-delay: 2000
~~~

Reactive Supplier trả về Flux liên tục thường được gọi một lần để tạo stream. Nếu Supplier trả về một Flux hữu hạn nhưng cần được gọi định kỳ, dùng @PollableBean theo hướng dẫn của phiên bản Spring Cloud Stream đang chạy.

Nếu ứng dụng có Supplier nhưng đang chờ message ở input topic, thiết kế chữ ký đang không đúng mục tiêu. Hãy dùng Function hoặc Consumer cho luồng nhận message.

### Reactive function có vòng đời khác imperative function

Với Function<Flux<T>, Flux<R>>, framework gọi function để thiết lập pipeline reactive. Sau đó Reactor xử lý các item trong stream. Không nên chờ phương thức apply được gọi lại một lần cho từng message.

Ví dụ:

~~~java
@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> acceptOrders() {
    return events -> events.map(orderService::accept);
}
~~~

Nếu dùng Consumer<Flux<T>>, ứng dụng phải bảo đảm subscription được tạo đúng. Với nhiều trường hợp, tài liệu Spring Cloud Stream khuyến nghị dùng Function<Flux<T>, Mono<Void>> để biểu diễn hoàn tất xử lý reactive rõ ràng:

~~~java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> auditOrders() {
    return events -> events
        .doOnNext(auditService::record)
        .then();
}
~~~

Một reactive function chỉ được gọi một lần khi pipeline khởi tạo không đồng nghĩa function không được liên kết. Hãy kiểm tra subscription, signal và kết quả xử lý bên trong stream.

## 5. Xác định binding name chính xác

Trong functional model, binding name được tạo từ tên function bean:

- Input: functionName-in-index.
- Output: functionName-out-index.

Với function có một input và một output, index mặc định là 0.

Ví dụ:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return orderService::accept;
}
~~~

Binding name:

~~~text
acceptOrder-in-0
acceptOrder-out-0
~~~

Tên binding không nhất thiết là tên topic, queue hoặc exchange. Binding name là tên nội bộ để cấu hình; destination là tên tài nguyên bên ngoài.

Cấu hình đúng:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: billing-service
        acceptOrder-out-0:
          destination: orders.accepted
~~~

Một lỗi rất thường gặp là viết:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders.created:
          destination: orders.created
~~~

Trong ví dụ sai, orders.created được dùng làm binding name nhưng function thực tế sinh ra acceptOrder-in-0. Hai tên này không tự liên kết với nhau.

### Function có nhiều input hoặc output

Với nhiều input/output, index tăng theo thứ tự:

- processOrder-in-0.
- processOrder-in-1.
- processOrder-out-0.
- processOrder-out-1.

Hãy kiểm tra chữ ký function và binding names tương ứng. Không tự đổi index hoặc suy ra binding name từ destination.

### Binding alias

Có thể đổi binding name mặc định sang tên mô tả hơn bằng:

~~~yaml
spring:
  cloud:
    stream:
      function:
        bindings:
          acceptOrder-in-0: ordersInput
          acceptOrder-out-0: ordersOutput
      bindings:
        ordersInput:
          destination: orders.created
          group: billing-service
        ordersOutput:
          destination: orders.accepted
~~~

Sau khi khai báo alias, các cấu hình binding tiếp theo phải sử dụng alias ordersInput và ordersOutput. Nếu vẫn cấu hình destination dưới acceptOrder-in-0, ứng dụng có thể đọc cấu hình ở binding khác với binding thực tế.

Khi cần tìm quan hệ giữa tên alias và function, kiểm tra property spring.cloud.stream.function.bindings cùng tên bean function.

## 6. Kiểm tra binder và destination

Function có thể được chọn đúng nhưng không tạo được kết nối tới broker nếu binder không có trên classpath hoặc cấu hình binder sai.

Spring Cloud Stream tự phát hiện binder implementation có trên classpath. Ví dụ, ứng dụng dùng Kafka cần dependency Kafka binder; ứng dụng dùng RabbitMQ cần dependency RabbitMQ binder.

Ví dụ Maven cho Kafka binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>
~~~

Ví dụ Maven cho RabbitMQ binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
</dependency>
~~~

Nếu chỉ có spring-cloud-stream core mà không có binder implementation tương ứng, function có thể hiện diện nhưng không có binder phù hợp để kết nối tới broker. Kiểm tra dependency runtime của artifact được đóng gói, không chỉ dependency trong IDE.

### Một binder trên classpath

Nếu chỉ có một binder implementation, framework có thể tự chọn binder đó. Tuy nhiên, vẫn nên xác nhận binder đúng với môi trường đang chạy.

### Nhiều binder trên classpath

Nếu có nhiều binder, chỉ định binder mặc định hoặc binder cho từng binding:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
      bindings:
        acceptOrder-in-0:
          binder: kafka
          destination: orders.created
          group: billing-service
        acceptOrder-out-0:
          binder: rabbit
          destination: orders.accepted
~~~

Nếu cấu hình nhiều binder nhưng tên binder không tồn tại hoặc không khớp cấu hình đăng ký, binding sẽ không dùng được. Kiểm tra cả binder name và binder type.

### Destination và quyền broker

Nếu binding đã được tạo nhưng không nhận hoặc gửi message, kiểm tra:

- Destination có đúng tên topic, queue hoặc exchange không?
- Broker có đúng địa chỉ và port không?
- Credentials có quyền read/write hoặc quyền khai báo tài nguyên không?
- Topic/queue có tồn tại nếu tự động provisioning bị tắt không?
- Namespace/tenant/topic của Pulsar có đúng không?
- Exchange và queue RabbitMQ có binding/routing key phù hợp không?
- Kafka consumer group có đang đọc đúng topic và offset không?

Destination có thể mặc định lấy từ binding name nếu không cấu hình. Trong production, khai báo destination rõ ràng giúp tránh phụ thuộc vào tên mặc định.

Group chỉ áp dụng cho input binding. Không khai báo group thường tạo anonymous consumer tùy binder; điều này không có nghĩa function chưa được bind. Group ảnh hưởng tới định danh và phân phối message, không phải tên function.

## 7. Phân biệt function binding với StreamBridge

Không phải mọi ứng dụng Spring Cloud Stream đều cần một Supplier hoặc Function bean.

Nếu nguồn dữ liệu đến từ REST endpoint, scheduler hoặc hệ thống bên ngoài, có thể dùng StreamBridge để gửi message:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final StreamBridge streamBridge;

    OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderCreated event) {
        return streamBridge.send("ordersOutput", event);
    }
}
~~~

Trong trường hợp này, không cần một Supplier bean chỉ để tạo output. StreamBridge có thể tạo dynamic output binding khi send lần đầu.

Nếu muốn tạo output binding ngay khi ứng dụng khởi động, khai báo:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: ordersOutput
      bindings:
        ordersOutput:
          destination: orders.created
~~~

Binding được tạo tường minh không dùng hậu tố -out-0 vì nó không được sinh từ một function bean.

Khi điều tra, hãy xác định ứng dụng đang dùng functional binding hay explicit/dynamic binding. Nếu chỉ tìm function bean trong một ứng dụng dùng StreamBridge, có thể kết luận nhầm rằng thiếu function là lỗi.

## 8. Bật log để quan sát quá trình discovery và binding

Khi cấu hình không rõ ràng, tăng log level có mục tiêu:

~~~yaml
logging:
  level:
    org.springframework.cloud.function: DEBUG
    org.springframework.cloud.stream: DEBUG
    org.springframework.integration: DEBUG
    org.springframework.messaging: DEBUG
~~~

Các nhóm log này giúp kiểm tra:
- Function nào được đăng ký.
- Function definition nào được chọn.
- Binding name nào được tạo.
- Binder nào được dùng.
- Destination nào được cấu hình.
- Lỗi kết nối hoặc provisioning.
- Message conversion và channel lifecycle.

Đừng bật DEBUG toàn bộ ứng dụng trong production nếu không cần thiết. Log chi tiết có thể tạo lượng dữ liệu lớn và để lộ thông tin cấu hình nhạy cảm. Chỉ bật trong thời gian chẩn đoán, sau đó trả log level về mức phù hợp.

### Dấu hiệu cần tìm

| Dấu hiệu | Diễn giải |
|---|---|
| Function bean không xuất hiện trong ApplicationContext | Lỗi component scan, profile hoặc điều kiện tạo bean |
| Có nhiều function nhưng definition không rõ | Framework chưa biết function nào cần bind |
| Không có binding name mong đợi | Function chưa được chọn hoặc chữ ký không tạo hướng binding đó |
| Binding tồn tại nhưng binder lỗi | Dependency, binder selection hoặc cấu hình kết nối |
| Binding ở trạng thái STOPPED | Binding đã tạo nhưng lifecycle chưa chạy |
| Binding RUNNING nhưng không có message | Kiểm tra destination, group, offset, routing và producer |
| Message nhận được nhưng function không tạo output | Consumer/function logic, exception, conversion hoặc function là Consumer |
| Supplier binding tồn tại nhưng không phát message | Poller, Supplier trả null/empty hoặc reactive stream không được trigger như dự kiến |

## 9. Dùng Actuator để xem binding thực tế

Spring Cloud Stream hỗ trợ endpoint Actuator để xem và điều khiển binding lifecycle.

Cần có Spring Boot Actuator và web dependency phù hợp, sau đó expose endpoint bindings:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

Xem toàn bộ binding:

~~~text
GET /actuator/bindings
~~~

Xem một binding:

~~~text
GET /actuator/bindings/acceptOrder-in-0
~~~

Endpoint có thể cho biết tên binding, hướng input/output, group và trạng thái lifecycle tùy binder. Nếu binding không xuất hiện, quay lại kiểm tra function discovery, function definition và binding naming.

Nếu binding xuất hiện nhưng STOPPED, kiểm tra cấu hình lifecycle và nguyên nhân binding chưa khởi động. Với Kafka Streams binder, có thể cấu hình auto-startup cho consumer binding để chủ động khởi động processor; đây là tình huống đặc thù, không áp dụng như một lời giải chung cho mọi binder.

Endpoint bindings có khả năng điều khiển trạng thái binding. Chỉ expose trong management network được bảo vệ và giới hạn quyền truy cập. Không mở endpoint điều khiển này ra Internet công cộng.

## 10. Kiểm thử function và binding bằng Test Binder

Spring Integration Test Binder cho phép kiểm thử function và binding trong JVM mà không cần broker thật.

Thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ kiểm thử function:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = OrderStreamTests.TestApplication.class,
    properties = "spring.cloud.function.definition=normalizeOrder"
)
class OrderStreamTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void normalizeOrderIsBound() {
        input.send(new GenericMessage<byte[]>(
            "  order-1001  ".getBytes(StandardCharsets.UTF_8)));

        Message<byte[]> result = output.receive();

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("ORDER-1001");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {

        @Bean
        Function<String, String> normalizeOrder() {
            return value -> value.trim().toUpperCase();
        }
    }
}
~~~

Trong test thực tế, cấu hình input/output và payload phải khớp với function được kiểm thử. Nếu có nhiều function, truyền spring.cloud.function.definition trong test để kiểm tra chính xác function được chọn.

Với nhiều binding, InputDestination.send và OutputDestination.receive có overload cho phép chỉ định binding name. Điều này hữu ích để phát hiện sai tên binding hoặc alias.

Test Binder giúp xác nhận:
- Bean function có thể được chọn.
- Binding input/output được tạo.
- Message có thể đi qua function.
- Conversion và logic function hoạt động trong môi trường test.

Test Binder không xác nhận broker thật có topic/queue, credentials, TLS, network hoặc provisioning đúng. Sau khi test binder pass, vẫn cần integration test với Kafka, RabbitMQ hoặc Pulsar tương ứng.

## 11. Quy trình chẩn đoán theo thứ tự

Khi ứng dụng khởi động nhưng function không được liên kết, thực hiện theo trình tự sau:

1. **Xác nhận bean:** kiểm tra ApplicationContext có Supplier, Function hoặc Consumer mong đợi không.
2. **Xác nhận tên bean:** đối chiếu tên method @Bean, tên được khai báo tường minh và function definition.
3. **Xác nhận selection:** đặt spring.cloud.function.definition rõ ràng; kiểm tra có nhiều function hoặc autodetect=false không.
4. **Xác nhận chữ ký:** kiểm tra Supplier/Function/Consumer và hướng input/output.
5. **Xác nhận binding name:** suy ra tên -in-0 và -out-0 từ bean name; kiểm tra alias.
6. **Xác nhận binder:** kiểm tra binder dependency có trong runtime classpath và binder name có hợp lệ không.
7. **Xác nhận destination:** kiểm tra topic, queue, exchange, namespace, group và quyền truy cập.
8. **Xác nhận lifecycle:** xem binding có xuất hiện và đang RUNNING không.
9. **Xác nhận message path:** gửi một message thử và theo dõi log/trace qua function.
10. **Xác nhận broker thật:** chạy integration test với binder production.

~~~mermaid
flowchart TD
    A["Ứng dụng đã khởi động"] --> B{"Function bean có tồn tại?"}
    B -->|Không| C["Kiểm tra component scan, profile, @Bean"]
    B -->|Có| D{"Function được chọn?"}
    D -->|Không| E["Kiểm tra spring.cloud.function.definition và autodetect"]
    D -->|Có| F{"Binding xuất hiện?"}
    F -->|Không| G["Kiểm tra chữ ký và binding name/alias"]
    F -->|Có| H{"Binder và destination hoạt động?"}
    H -->|Không| I["Kiểm tra binder dependency, cấu hình, quyền và provisioning"]
    H -->|Có| J{"Binding RUNNING và có message?"}
    J -->|Không| K["Kiểm tra lifecycle, group, topic, offset và routing"]
    J -->|Có| L["Kiểm tra conversion, function exception và output"]
~~~

Không thay nhiều property cùng lúc. Sau mỗi bước, ghi lại trạng thái bean, function definition, binding name, binder và destination. Cách này giúp biết chính xác thay đổi nào đã khôi phục liên kết.

## 12. Các tình huống lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ứng dụng chạy nhưng không có function bean | Cấu hình nằm ngoài component scan | Di chuyển hoặc import cấu hình đúng cách |
| Có function bean nhưng không có binding | Nhiều function và thiếu definition | Chỉ định spring.cloud.function.definition |
| Chỉ một function nhưng không được auto-bind | autodetect bị tắt | Đặt definition hoặc bật lại auto-discovery |
| Function definition không tìm thấy bean | Sai tên hoặc khác chữ hoa/thường | Dùng đúng bean name |
| Consumer có binding nhưng chờ output | Consumer không có output | Dùng Function nếu cần trả message |
| Supplier không nhận message đầu vào | Supplier chỉ là source | Chuyển sang Function/Consumer nếu cần input |
| Function có input nhưng không có output | Function thực tế được khai báo Consumer | Sửa kiểu bean nếu cần phát output |
| Không thấy binding theo destination name | Nhầm destination với binding name | Dùng functionName-in-0/out-0 rồi map destination |
| Đổi alias nhưng cấu hình cũ vẫn còn | Các property vẫn dùng binding name cũ | Chuyển tất cả property sang alias |
| Function có nhiều input/output nhưng sai luồng | Dùng sai index | Kiểm tra thứ tự tham số và binding index |
| Binder không được tìm thấy | Thiếu binder dependency runtime | Thêm binder phù hợp và kiểm tra packaged artifact |
| Multi-binder chọn sai | Thiếu default-binder hoặc binder trên binding | Chỉ định binder rõ ràng |
| Binding tạo nhưng không kết nối broker | Credentials, TLS, network hoặc endpoint sai | Kiểm tra broker connection và permissions |
| Binding RUNNING nhưng không nhận message | Sai destination, group, offset hoặc routing | Kiểm tra broker-side message flow |
| Supplier không phát dữ liệu | Poller không chạy hoặc Supplier trả null | Kiểm tra poller, output binding và giá trị trả về |
| Reactive Supplier chỉ chạy một lần | Reactive stream được tạo một lần | Kiểm tra stream subscription; dùng @PollableBean nếu cần polling hữu hạn |
| Reactive Consumer không xử lý | Flux chưa được subscribe | Dùng Function<Flux<T>, Mono<Void>> hoặc subscription phù hợp |
| Test Binder pass nhưng production fail | Khác biệt broker/provisioning/security | Chạy integration test với broker thật |
| Actuator không có bindings | Thiếu Actuator/web hoặc chưa expose endpoint | Thêm dependency và exposure property |

## 13. Bài thực hành: khôi phục function acceptOrder

Tình huống: ứng dụng Order Stream khởi động thành công nhưng không có message đi từ topic orders.created qua function acceptOrder tới orders.accepted.

1. Xác nhận OrderStreamApplication là class Spring Boot chính.
2. Kiểm tra OrderFunctions nằm trong package được scan.
3. Xác nhận bean tên acceptOrder có kiểu Function<OrderCreated, OrderAccepted>.
4. Đặt spring.cloud.function.definition=acceptOrder.
5. Kiểm tra không có spring.cloud.stream.function.autodetect=false làm vô hiệu cơ chế cần dùng.
6. Kiểm tra binding names acceptOrder-in-0 và acceptOrder-out-0.
7. Cấu hình destination orders.created và orders.accepted.
8. Kiểm tra Kafka binder dependency và cấu hình brokers.
9. Kiểm tra group billing-service và quyền đọc topic.
10. Bật DEBUG cho Spring Cloud Function và Spring Cloud Stream.
11. Mở Actuator bindings và xác nhận hai binding tồn tại, trạng thái RUNNING.
12. Dùng Test Binder gửi OrderCreated và xác nhận OrderAccepted được phát.
13. Chạy integration test với Kafka thật.
14. Kiểm tra offset, consumer group, serialization và broker-side topic.
15. Tắt DEBUG và thu hẹp Actuator exposure sau khi hoàn tất.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Bean registration | acceptOrder xuất hiện trong ApplicationContext |
| Function selection | definition trỏ đúng acceptOrder |
| Function signature | Function có input và output phù hợp |
| Binding names | acceptOrder-in-0 và acceptOrder-out-0 |
| Destinations | orders.created và orders.accepted |
| Binder | Kafka binder có trong runtime classpath |
| Consumer group | billing-service được cấu hình đúng |
| Lifecycle | Hai binding xuất hiện và RUNNING |
| Test Binder | Message đi qua function thành công |
| Broker integration | Message thật được nhận và phát |
| Logs | Không còn lỗi discovery, binding hoặc provisioning |
| Security | Actuator bindings được bảo vệ và không public |

## Kết luận

Khi ứng dụng Spring Cloud Stream khởi động nhưng function không được liên kết, hãy kiểm tra theo ba tầng: bean có tồn tại, function có được chọn và binding có hoạt động. Tên function, property spring.cloud.function.definition, chữ ký Supplier/Function/Consumer và quy tắc đặt binding name quyết định framework có thể tạo đúng liên kết hay không.

Sau đó kiểm tra binder dependency, destination, group, quyền broker và binding lifecycle. Test Binder giúp xác nhận function/binding trong JVM; integration test với broker thật xác nhận toàn bộ đường truyền. Khi tách rõ từng tầng, bạn sẽ tránh thay cấu hình broker để chữa lỗi bean discovery hoặc sửa function trong khi binding thực tế đã hoạt động.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0 – Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream – Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream – Bindings](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/bindings.html)
- [Spring Cloud Stream – Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream – Explicit Binding Creation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/explicit-binding-creation.html)
- [Spring Cloud Stream – Testing with Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream – Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring Cloud Function – Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)

