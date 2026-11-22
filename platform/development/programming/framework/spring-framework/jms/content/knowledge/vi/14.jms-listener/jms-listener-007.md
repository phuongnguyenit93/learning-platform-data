# Dùng placeholder và biểu thức cấu hình có kiểm soát trong @JmsListener

## 1. Bối cảnh: listener cần thay đổi cấu hình mà không sửa code

Trong ứng dụng Spring JMS, một method nhận message thường được khai báo bằng annotation:

~~~java
@JmsListener(destination = "orders.in")
public void handle(String payload) {
    // Xử lý một đơn hàng.
}
~~~

Code chạy được, nhưng các môi trường local, test, staging và production thường có destination khác nhau. Đôi khi broker phải lọc message theo loại sự kiện, tenant hoặc schema; hoặc số lượng consumer được thay đổi theo hạ tầng. Không nên sửa class Java mỗi lần đổi tên Queue hay mức concurrency.

`@JmsListener` hỗ trợ **các giá trị cấu hình được giải quyết lúc khởi động**:

- **Property placeholder**: `${app.jms.orders-queue}` lấy giá trị từ Spring Environment.
- **SpEL (Spring Expression Language)**: `#{@routingPolicy.ordersDestination()}` đánh giá biểu thức dựa trên bean được quản lý bởi Spring.
- **Listener container factory**: giữ cấu hình transaction, connection, converter, concurrency mặc định và recovery.
- **Bean/config validation**: kiểm tra tên destination, giá trị selector, số consumer và môi trường được phép trước khi dùng.

Ví dụ cấu hình qua properties:

~~~java
@JmsListener(
        id = "ordersListener",
        destination = "${app.jms.orders-queue}",
        selector = "${app.jms.order-selector}",
        concurrency = "${app.jms.listener-concurrency}")
public void onOrder(String body) {
    // Xử lý message phù hợp.
}
~~~

~~~properties
app.jms.orders-queue=orders.in
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
app.jms.listener-concurrency=1
~~~

Một bộ artifact Java có thể deploy nhiều nơi; các giá trị thực tế nằm trong cấu hình được kiểm soát của từng môi trường.

**Giới hạn quan trọng:** giá trị annotation được Spring giải quyết khi listener endpoint được phát hiện/đăng ký và container được tạo. Nó **không** tự được đánh giá cho từng message mới, cũng không tự đổi nếu file cấu hình bên ngoài bị sửa trong lúc ứng dụng đang chạy.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Biết thuộc tính nào của `@JmsListener` nên externalize.
2. Phân biệt `${...}` (property placeholder), `#{...}` (SpEL) và biểu thức JMS selector.
3. Dùng placeholder bắt buộc, default, profile/environment mà không vô tình nghe sai Queue.
4. Biết giới hạn của SpEL, validate đầu vào cấu hình và phòng tránh selector injection.
5. Viết ví dụ Java 17 + Spring Boot 3.x + ActiveMQ Artemis để kiểm chứng selector qua một listener thực.
6. Kiểm thử, giám sát và triển khai an toàn khi thay destination, selector hoặc concurrency.

## 2. Những thuộc tính của @JmsListener

Theo Javadoc Spring Framework 6.1, `@JmsListener` có một thuộc tính String bắt buộc `destination` và các thuộc tính String tùy chọn:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `destination` | Tên JMS destination, xử lý qua DestinationResolver của container | `${app.jms.orders-queue}` |
| `selector` | Biểu thức JMS message selector | `${app.jms.order-selector}` |
| `concurrency` | Giới hạn concurrent consumers của endpoint | `${app.jms.listener-concurrency}` |
| `id` | ID duy nhất của listener endpoint/container | `ordersListener` |
| `containerFactory` | Tên bean JmsListenerContainerFactory | `ordersContainerFactory` |
| `subscription` | Tên subscription (thường liên quan Topic/durable subscription) | `ordersEventsSubscription` |

`containerFactory` phải trỏ đến một bean có thực. Nếu không chỉ định, Spring thường tìm factory mặc định với tên `jmsListenerContainerFactory`, trừ khi đã cấu hình default khác. `subscription` không phải một cách tùy ý đặt tên Queue; nó thuộc mô hình subscription của Topic.

Ví dụ minh họa nhiều thuộc tính:

~~~java
@JmsListener(
        id = "ordersListener",
        destination = "${app.jms.orders-queue}",
        selector = "${app.jms.order-selector}",
        concurrency = "${app.jms.listener-concurrency}",
        containerFactory = "ordersContainerFactory")
public void receive(String body) {
    // ...
}
~~~

Đoạn này cần một bean tên `ordersContainerFactory`. Không dùng nó trong project mẫu phía dưới vì project mẫu tận dụng listener factory do Spring Boot cấu hình.

Những thứ **không phải** thuộc tính `@JmsListener`: broker URL, username/password, TLS, pool settings, converter, transaction manager, acknowledge mode, recovery backoff và resource lifecycle. Chúng thuộc `ConnectionFactory`, container factory, Spring Boot properties hoặc infrastructure beans.

~~~text
Spring Environment
  |
  +-- destination property ----+
  +-- selector property -------+----> @JmsListener endpoint
  +-- concurrency property ----+          |
  |                                       v
  +-- Artemis connection configuration  ListenerContainerFactory
                                          |
                                          v
                                    Listener container
                                          |
                                          v
                                    JMS provider/broker
                                          |
                                          v
                                      handler method
~~~

## 3. Placeholder: lấy String từ Spring Environment

Spring xử lý placeholder theo cú pháp `${property.name}`. Có thể khai báo fallback `${property.name:defaultValue}`.

~~~java
// Bắt buộc phải cấu hình property:
@JmsListener(destination = "${app.jms.orders-queue}")
public void handle(String body) { }
~~~

~~~java
// Có fallback dùng cho local demo:
@JmsListener(destination = "${app.jms.orders-queue:orders.demo}")
public void handleDemo(String body) { }
~~~

Đây là **hai phương án riêng**, không thêm cả hai vào cùng ứng dụng production nếu không cần hai consumer.

### 3.1. Khi nào nên dùng giá trị mặc định?

Fallback phù hợp bài học hoặc phần cấu hình không quan trọng. Nhưng với destination production, một fallback khó thấy có thể dẫn đến lỗi nguy hiểm: ứng dụng quên đặt property và âm thầm nghe `orders.demo` hoặc gửi dữ liệu sai môi trường.

**Khuyến nghị:** tên Queue/Topic, thông số tenant routing, thông tin xác thực và lựa chọn broker quan trọng nên có cấu hình bắt buộc được validate. Không thêm default chỉ để ứng dụng khởi động mà không có thông tin cần thiết.

### 3.2. @Value khác với placeholder trong annotation

Java không cho phép annotation dùng trực tiếp giá trị một field instance không phải constant expression:

~~~java
// KHÔNG HỢP LỆ nếu ordersQueue là biến runtime:
@JmsListener(destination = ordersQueue)
public void handle(String payload) { }
~~~

Nhưng String literal chứa placeholder lại hợp lệ ở Java source:

~~~java
@JmsListener(destination = "${app.jms.orders-queue}")
public void handle(String payload) { }
~~~

Lý do: Java compiler chỉ thấy một String literal, còn Spring resolve nội dung đó khi chạy ứng dụng. `@Value("${...}")` có thể inject giá trị vào field/constructor, nhưng không biến field runtime thành compile-time constant để truyền cho annotation.

### 3.3. Nguồn và thứ tự ưu tiên property

Trong Spring Boot, Spring Environment kết hợp các nguồn như:

- `application.properties` hoặc `application.yml`.
- File theo profile, ví dụ `application-dev.properties`.
- Environment variables do container/orchestrator cung cấp.
- Command-line arguments khi khởi động.
- Config sources khác do ứng dụng và deployment đăng ký.

Nguồn có độ ưu tiên cụ thể theo Boot version; không mặc định rằng một file luôn thắng mọi environment variable. Trong production, hãy quan sát **giá trị hiệu lực đã resolve** của những key không nhạy cảm lúc startup, thay vì tin vào một file cấu hình được mở bằng tay.

Ví dụ:

~~~properties
# application-dev.properties
app.jms.orders-queue=orders.dev.in
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
app.jms.listener-concurrency=1
~~~

~~~properties
# application-prod.properties
app.jms.orders-queue=orders.prod.in
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
app.jms.listener-concurrency=2-6
~~~

Hai block là **hai file khác nhau**, chỉ mô tả một chiến lược cấu hình theo profile. Không copy cả hai block trùng key vào cùng file rồi kỳ vọng Spring tự biết khi nào dùng giá trị nào.

## 4. SpEL: biểu thức được Spring đánh giá tại lúc đăng ký endpoint

SpEL sử dụng cú pháp `#{...}`. Với `@JmsListener`, ví dụ phổ biến là lấy tên Queue và selector từ một bean **do code ứng dụng kiểm soát**:

~~~java
@JmsListener(
        destination = "#{@ordersRouting.destination()}",
        selector = "#{@ordersRouting.selector()}")
public void handle(String body) {
    // ...
}
~~~

Bean tương ứng:

~~~java
import org.springframework.stereotype.Component;

@Component("ordersRouting")
public class OrdersRouting {
    public String destination() {
        return "orders.in";
    }

    public String selector() {
        return "eventType = 'order.created' AND region = 'VN'";
    }
}
~~~

Spring resolve hai expression để lấy String trước khi đăng ký container. Broker chỉ nhìn thấy tên destination và selector **sau khi resolve**.

Phân biệt:

| Dạng | Ai đánh giá | Khi nào |
| --- | --- | --- |
| `${app.jms.orders-queue}` | Spring Environment | Khi resolve cấu hình listener |
| `#{@ordersRouting.destination()}` | Spring SpEL/BeanFactory | Khi xử lý annotation |
| `region = 'VN' AND eventType = 'order.created'` | JMS provider | Khi consumer chọn message theo metadata |
| `$.region` | JSONPath parser, nếu ứng dụng có dùng | Không phải cơ chế JMS selector |
| `order.region().equals("VN")` | Java business code | Sau khi message được chuyển thành object |

**Không** viết:

~~~java
// SAI Ý TƯỞNG: Không có incoming "payload" ở thời điểm resolve annotation.
@JmsListener(
        destination = "orders.in",
        selector = "#{payload.region == 'VN'}")
public void handle(String payload) { }
~~~

Nếu muốn lọc theo region **từng message**, producer cần đặt JMS property `region` và listener dùng selector JMS `region = 'VN'`. Annotation SpEL không đọc payload của từng message trước khi broker giao message.

### 4.1. Khi nào thực sự cần SpEL?

SpEL có ích khi ứng dụng có một **config policy bean đáng tin cậy**, ví dụ:

- Chọn destination từ danh sách đã định nghĩa, kiểm tra naming convention.
- Tính selector từ allowlist tenant cố định theo một deployment.
- Đồng bộ tên Queue giữa listener và các bean hạ tầng.
- Cung cấp một giá trị cấu hình từ service đã validate/normalize lúc startup.

Với giá trị đơn giản đã có trong environment, dùng `${...}` thường ít phức tạp, dễ audit và dễ kiểm thử hơn.

### 4.2. Không cho người dùng bên ngoài định nghĩa SpEL

SpEL có thể truy cập bean và method tùy evaluation context. Đừng lấy một String từ HTTP request hoặc nguồn dữ liệu không tin cậy rồi đánh giá nó như một SpEL expression trong application context.

**Tốt:** biểu thức nằm trong source code được review; bean làm các phép lựa chọn giới hạn và trả String đã validate.

**Không tốt:** nhận toàn bộ expression như một tham số do client quyết định và cho phép nó truy cập BeanFactory hoặc class/method tùy ý.

SpEL không phải sandbox dành cho input tùy ý. Với những tham số thực sự cần động, dùng một cấu trúc dữ liệu đã validate, allowlist hoặc configuration object rõ ràng thay vì execution expression.

## 5. JMS selector: biểu thức khác SpEL

Sau khi resolve `selector`, container chuyển một String cho JMS provider. String này phải tuân theo **JMS message selector grammar** (tập con SQL-92).

Ví dụ:

~~~properties
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
~~~

Selector chọn message dựa trên **JMS headers và properties**, không truy vấn JSON body. Producer phải đặt đúng JMS properties:

~~~java
jmsTemplate.convertAndSend("orders.in", "ORDER|O-42", message -> {
    message.setStringProperty("eventType", "order.created");
    message.setStringProperty("region", "VN");
    return message;
});
~~~

Câu:

~~~sql
eventType = 'order.created' AND region = 'VN'
~~~

là JMS selector hợp lệ. Nhưng:

~~~sql
WHERE body.region = 'VN'
JSON_VALUE(body, '$.region') = 'VN'
~~~

không phải selector chuẩn JMS. Broker không tự deserialize JSON body để tìm `region`.

### 5.1. Giới hạn và kiểu property

- `setIntProperty("amount", 150)` tạo property số; `amount >= 100` là so sánh số.
- `setStringProperty("amount", "150")` tạo String; selector không tự ép nó thành số trong cùng biểu thức.
- Property không tồn tại làm nhiều so sánh thành `UNKNOWN`; chỉ kết quả `TRUE` mới match.
- `status <> 'CANCELLED'` không match message thiếu `status`; nếu muốn bao gồm message thiếu property, dùng `status IS NULL OR status <> 'CANCELLED'`.
- Giá trị String dùng dấu nháy đơn; escape một dấu nháy đơn bằng **hai dấu nháy đơn**.

**Không bao giờ** coi một selector hợp lệ về cú pháp là bằng chứng phân quyền tenant. JMS selector chỉ lọc delivery, còn broker ACL/destination isolation mới quyết định consumer được quyền truy cập dữ liệu gì.

### 5.2. Cẩn thận với selector dựng từ input động

Sai:

~~~java
String selector = "tenant = '" + tenantFromHttpRequest + "'";
~~~

Nếu client cung cấp dấu nháy đơn, toán tử hoặc ký tự đặc biệt, biểu thức có thể đổi logic hoặc invalid. Không chỉ có vấn đề syntax: client còn có thể chọn tenant không được phép.

Một builder tối thiểu cần allowlist:

~~~java
import java.util.Set;

public final class TenantSelectorPolicy {
    private static final Set<String> ALLOWED = Set.of("vn", "sg");

    public static String forTenant(String tenant) {
        if (!ALLOWED.contains(tenant)) {
            throw new IllegalArgumentException("Tenant not allowed");
        }
        return "eventType = 'order.created' AND tenant = '" + tenant + "'";
    }
}
~~~

Đây là class Java minh họa độc lập với project mẫu phía dưới. Chỉ cho phép `vn` hoặc `sg` nên không nhận chuỗi selector tùy ý. Khi cần String literal tự do, phải validate và escape nháy đơn theo grammar JMS, nhưng **quote escaping không thay thế authorization**.

Nếu tenant cần đổi cho mỗi incoming message, không thay SpEL annotation khi runtime; hãy thiết kế routing, selector theo consumer cố định hoặc một cơ chế subscription/endpoint registration riêng có lifecycle rõ.

## 6. Concurrency, containerFactory và lựa chọn Topic

Thuộc tính `concurrency` là String cấu hình giới hạn consumer theo khả năng của underlying container. Ví dụ:

~~~java
@JmsListener(
        destination = "${app.jms.orders-queue}",
        concurrency = "${app.jms.listener-concurrency}")
public void handle(String payload) { }
~~~

~~~properties
app.jms.listener-concurrency=2-6
~~~

Với `DefaultMessageListenerContainer`, có thể hiểu đây là một khoảng consumer tối thiểu/tối đa. Container khác có thể không hỗ trợ đầy đủ điều chỉnh động. Đừng hiểu `2-6` là Spring luôn tạo sáu thread, hoặc tự bảo đảm message ordering. Nhiều consumer trên Queue có thể xử lý song song và thay đổi thứ tự quan sát.

Nếu cấu hình concurrency ở `DefaultJmsListenerContainerFactory`:

~~~java
// Snippet trong @Configuration class:
@Bean
DefaultJmsListenerContainerFactory ordersContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-4");
    return factory;
}
~~~

Cần import `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean` và `org.springframework.jms.config.DefaultJmsListenerContainerFactory`. Annotation có `containerFactory = "ordersContainerFactory"` mới chọn bean này. `concurrency` trên annotation có thể override giá trị factory cho endpoint riêng.

Cân nhắc trước khi tăng concurrency:

- Connection/session/consumer của broker có đủ không?
- DB connection pool và external API rate limit có chịu tải được không?
- Handler singleton có dùng shared mutable state gây race condition không?
- Nghiệp vụ có đòi hỏi ordering theo một khóa không?
- Transaction rollback, redelivery và idempotency được thiết kế thế nào?

`subscription` liên quan Topic, không phải một Queue naming shortcut. Với durable Topic subscription, identity/client ID và selector cần được quản trị; đổi selector hoặc tên subscription có thể ảnh hưởng message còn tồn tại. Không dùng placeholder thay đổi ngẫu nhiên subscription ID mỗi lần deploy.

## 7. Startup-time và thay đổi runtime

Từ source của Spring `JmsListenerAnnotationBeanPostProcessor`, annotation attributes như `destination`, `selector`, `subscription`, `concurrency`, `containerFactory` và `id` được resolve trong quá trình đăng ký endpoint.

~~~text
Startup:
  Spring Environment / bean factory ready
    -> tìm @JmsListener
    -> resolve placeholder và SpEL
    -> đăng ký endpoint với destination/selector/concurrency cụ thể
    -> tạo listener container
    -> kết nối JMS provider và start consumer

Khi message tới:
  Broker áp JMS selector đã cấu hình
    -> gọi method nếu message phù hợp

Khi file cấu hình bị sửa trong lúc app chạy:
  Không tự sửa selector/Queue của consumer hiện hữu
~~~

Nếu cần đổi destination/selector/concurrency, thông thường triển khai config mới rồi restart/rolling update một cách có kiểm soát. Với endpoint registration động, cần API quản lý lifecycle chính thức và đồng bộ với broker; chỉ sửa file `application.properties` không tự tạo lại consumer.

### 7.1. Dùng id để quản lý listener

Với annotation:

~~~java
@JmsListener(
        id = "ordersListener",
        destination = "${app.jms.orders-queue}")
public void handle(String payload) { }
~~~

Bạn có thể tìm container qua `JmsListenerEndpointRegistry`:

~~~java
// Snippet trong bean đã được inject registry:
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
if (container != null) {
    container.stop();
}
~~~

Cần import `org.springframework.jms.config.JmsListenerEndpointRegistry` và `org.springframework.jms.listener.MessageListenerContainer`. `stop()` là quản lý lifecycle, **không** ép annotation resolve lại giá trị mới. Việc start sau stop sẽ dùng endpoint/container đã được cấu hình, trừ khi bạn thực hiện tái cấu hình hợp lệ.

### 7.2. autoStartup không phải thuộc tính annotation

Spring Boot có:

~~~properties
spring.jms.listener.auto-startup=true
~~~

để điều khiển mặc định container được auto-configuration quản lý. `@JmsListener` Spring Framework 6.1 không có thuộc tính String tên `autoStartup`. Nếu cần ngừng listener trong deployment, cấu hình autoStartup của factory hoặc điều khiển registry thích hợp; không tự thêm `autoStartup` vào annotation rồi mong Java biên dịch.

## 8. Dự án runnable: Spring Boot 3.3 + Artemis + @JmsListener với placeholder

Ví dụ gửi **hai message** vào Queue lab:

- `ORDER|O-42` có `eventType=order.created` và `region=VN`: listener nhận.
- `ORDER|O-43` có `eventType=order.created` và `region=US`: không match listener, vẫn có thể được consumer khác nhận.
- Một `CommandLineRunner` kiểm tra handler đã chạy, sau đó lấy message `US` bằng `JmsTemplate.receiveSelectedAndConvert`.

### 8.1. Khởi chạy broker lab

Cần Docker:

~~~bash
docker run --detach --rm --name artemis-listener-config -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Đợi broker sẵn sàng qua `docker logs artemis-listener-config`. Credential `demo/demo` chỉ dành cho local. Nếu broker không auto-create Queue, tạo Queue và phân quyền trước. Nên dùng Queue riêng hoặc xóa message cũ trong môi trường lab để đảm bảo kết quả.

### 8.2. Cấu trúc project

~~~text
jms-listener-config/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/
    ListenerConfigApplication.java
    FilteredOrderListener.java
    DemoPublisher.java
  src/test/java/demo/jms/
    FilteredOrderListenerTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-listener-config'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Version cố định để minh họa một bộ API nhất quán, không có nghĩa đây là bản maintenance mới nhất. Dùng JDK 17+, Gradle 8.x tương thích với plugin. Spring Boot 3 dùng `jakarta.jms`, không phải `javax.jms` cũ.

### 8.3. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=2s

app.jms.orders-queue=${JMS_DEMO_QUEUE:orders.listener.config.demo}
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
app.jms.listener-concurrency=1
~~~

Placeholder Spring thực tế có cú pháp bắt đầu bằng dấu dollar và ngoặc nhọn; những dòng trên dùng đúng cú pháp đó khi được lưu. `spring.jms.template.receive-timeout=2s` chỉ giới hạn **JmsTemplate synchronous receive**, không phải callback timeout của `@JmsListener`. Trong production, bỏ fallback `demo` cho username/password và dùng secret injection.

### 8.4. Main class

File `src/main/java/demo/jms/ListenerConfigApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ListenerConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(ListenerConfigApplication.class, args);
    }
}
~~~

`@EnableJms` bật xử lý method `@JmsListener`. Khi Artemis starter và connection configuration đầy đủ, Spring Boot có thể auto-configure `ConnectionFactory`, `JmsTemplate` và listener factory mặc định.

### 8.5. Listener có selector đọc từ properties

File `src/main/java/demo/jms/FilteredOrderListener.java`:

~~~java
package demo.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class FilteredOrderListener {

    private final CountDownLatch received = new CountDownLatch(1);
    private final AtomicReference<String> lastBody =
            new AtomicReference<>();

    @JmsListener(
            id = "ordersListener",
            destination = "${app.jms.orders-queue}",
            selector = "${app.jms.order-selector}",
            concurrency = "${app.jms.listener-concurrency}")
    public void onOrder(String body) {
        lastBody.set(body);
        System.out.println("MATCHED=" + body);
        received.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }

    public String lastBody() {
        return lastBody.get();
    }
}
~~~

Annotation khi resolve có giá trị:

~~~text
id          = ordersListener
destination = orders.listener.config.demo
selector    = eventType = 'order.created' AND region = 'VN'
concurrency = 1
~~~

`CountDownLatch` chỉ giúp chương trình demo biết handler được gọi. Nó không chứng minh broker ACK, DB commit hoặc đảm bảo exactly-once. Trong production, handler thường stateless và cần idempotency nếu một message có thể redeliver.

### 8.6. Producer và kiểm tra message không match

File `src/main/java/demo/jms/DemoPublisher.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class DemoPublisher implements CommandLineRunner {

    private final JmsTemplate template;
    private final FilteredOrderListener listener;
    private final String queue;

    public DemoPublisher(
            JmsTemplate template,
            FilteredOrderListener listener,
            @Value("${app.jms.orders-queue}") String queue) {
        this.template = template;
        this.listener = listener;
        this.queue = queue;
    }

    @Override
    public void run(String... args) throws Exception {
        template.convertAndSend(queue, "ORDER|O-42", message -> {
            message.setStringProperty("eventType", "order.created");
            message.setStringProperty("region", "VN");
            return message;
        });

        template.convertAndSend(queue, "ORDER|O-43", message -> {
            message.setStringProperty("eventType", "order.created");
            message.setStringProperty("region", "US");
            return message;
        });

        boolean invoked = listener.await(10, TimeUnit.SECONDS);
        System.out.println("HANDLER_INVOKED=" + invoked);

        Object remaining = template.receiveSelectedAndConvert(
                queue, "region = 'US'");
        System.out.println("OTHER_MESSAGE=" + remaining);
    }
}
~~~

Producer gửi Java String, Spring converter mặc định biến String thành JMS TextMessage. `eventType` và `region` là **JMS properties** được đặt riêng, không phải trường JSON body. Listener `ordersListener` chỉ match region `VN`, còn `receiveSelectedAndConvert` dùng selector riêng để lấy message region `US`.

Với Queue lab sạch, đây là ví dụ có thể tái hiện. Nếu broker có message cũ hoặc consumer khác tranh cùng Queue, kết quả có thể khác. Đặt biến môi trường `JMS_DEMO_QUEUE` thành tên Queue test mới cho mỗi lần chạy để giảm ảnh hưởng. Không sử dụng Queue production cho bài thực hành.

### 8.7. Chạy và stdout dự kiến

~~~bash
gradle test
gradle bootRun
~~~

Khi broker, credentials, ACL và Queue hợp lệ, ba dòng do chính code in ra:

~~~text
MATCHED=ORDER|O-42
HANDLER_INVOKED=true
OTHER_MESSAGE=ORDER|O-43
~~~

Các log startup Spring/Artemis/Gradle có thể xen kẽ. `HANDLER_INVOKED=true` được in sau khi listener gọi `CountDownLatch.countDown()`; nó không chứng minh JMS commit cuối cùng. Nếu không đủ điều kiện lab, có thể thấy timeout hoặc exception thay vì ba dòng trên.

Kết thúc:

~~~bash
docker stop artemis-listener-config
~~~

## 9. Unit test, context test và integration test

### 9.1. Unit test business method

File `src/test/java/demo/jms/FilteredOrderListenerTest.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FilteredOrderListenerTest {

    @Test
    void storesHandledMessage() throws InterruptedException {
        FilteredOrderListener listener =
                new FilteredOrderListener();

        listener.onOrder("ORDER|O-42");

        assertTrue(listener.await(100, TimeUnit.MILLISECONDS));
        assertEquals("ORDER|O-42", listener.lastBody());
    }
}
~~~

`gradle test` chạy test thuần Java mà không cần broker. Test xác minh handler nhưng **không** chứng minh annotation placeholder được resolve hoặc Artemis đánh giá selector đúng. Đó là trách nhiệm của integration test.

### 9.2. Kiểm tra registry sau khi context khởi động

Từ một Spring test/infrastructure đã inject `JmsListenerEndpointRegistry`:

~~~java
// Snippet bên trong test có import JUnit assertNotNull:
var container =
        registry.getListenerContainer("ordersListener");
assertNotNull(container);
~~~

Container tồn tại chưa chứng minh nó kết nối broker thành công. Phải kết hợp state/isRunning, broker consumer count và message match/non-match thật.

### 9.3. Test trên broker thật

Bộ integration test nên kiểm tra:

1. Property destination bắt buộc bị thiếu thì deployment báo lỗi cấu hình.
2. Placeholder được profile hoặc env override đúng với deployment.
3. Listener chỉ nhận message có `eventType=order.created` và `region=VN`.
4. Message có `region=US` không vào listener nhưng còn eligible cho consumer khác trong Queue.
5. Message thiếu `region` không match vì phép so sánh cho UNKNOWN.
6. Producer đặt sai kiểu property không được tự ép theo mong muốn.
7. Selector sai cú pháp bị broker/provider phát hiện; quan sát log/error phù hợp.
8. Giá trị concurrency vượt giới hạn được ngăn trong CI/config review.
9. Thay property trong runtime không được lầm tưởng đã đổi container.
10. Transaction rollback/redelivery và duplicate được xử lý theo chính sách nghiệp vụ.

Mockito không thực thi JMS selector engine. Để kiểm chứng selector phải dùng Artemis thật hoặc broker được tạo riêng qua Testcontainers; tránh test trên production.

## 10. Kiểm soát cấu hình: naming, allowlist và bảo mật

Property placeholder chỉ trả về String. Nó không tự validate Queue name, selector hoặc số consumer.

### 10.1. Kiểm tra destination bằng policy bean

Một phương án khi naming convention cố định:

~~~java
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component("safeOrdersRoute")
public class SafeOrdersRoute {

    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    private final String destination;

    public SafeOrdersRoute(
            @Value("${app.jms.orders-queue}") String destination) {
        if (!VALID.matcher(destination).matches()) {
            throw new IllegalArgumentException(
                    "Invalid destination configuration");
        }
        this.destination = destination;
    }

    public String destination() {
        return destination;
    }
}
~~~

Sau đó có thể dùng **một phương án thay thế** trong listener:

~~~java
@JmsListener(destination = "#{@safeOrdersRoute.destination()}")
public void onMessage(String payload) { }
~~~

Snippet này là alternative riêng, **không** thêm cùng lúc vào project lab nếu không muốn tạo listener thứ hai. Regex chỉ kiểm tra format, không thể biết Queue đã được ACL cho phép. Production vẫn phải kiểm tra destination ownership và broker permissions.

### 10.2. Không cho phép chọn containerFactory tùy ý

Nếu dùng:

~~~java
@JmsListener(
        destination = "${app.jms.orders-queue}",
        containerFactory = "ordersContainerFactory")
public void onOrder(String payload) { }
~~~

thì bean `ordersContainerFactory` phải tồn tại và có chính sách transaction/ACK/recovery phù hợp. Đừng nhận arbitrary bean name từ user ngoài ứng dụng để chọn loại listener container hoặc ngầm thay đổi transaction policy.

### 10.3. Secret management

Tên tài khoản, mật khẩu, key TLS không thuộc annotation:

~~~properties
spring.artemis.user=${JMS_BROKER_USER}
spring.artemis.password=${JMS_BROKER_PASSWORD}
~~~

Với production, property source phải được quản lý an toàn. Không in password khi log “resolved configuration”; không gửi secret qua headers/properties JMS hoặc embedded SpEL.

### 10.4. Không coi selector là ACL

Một selector như `tenant = 'vn'` chỉ lọc delivery cho consumer. Nếu service account được broker cấp quyền rộng, việc thay selector có thể làm lộ dữ liệu tenant khác. Cần quyền consume theo destination, phân tách tenant nếu cần và kiểm tra cấu hình trước deploy.

## 11. Những loại lỗi cần phân biệt

| Hiện tượng | Ranh giới lỗi | Cách xử lý |
| --- | --- | --- |
| Không resolve `${app.jms.orders-queue}` | Spring Environment/config | Khai báo property đúng, bỏ fallback nguy hiểm |
| SpEL bean/method không tồn tại | BeanFactory/SpEL | Sửa biểu thức/bean, test context |
| `containerFactory` sai tên | Spring bean registration | Dùng bean thật hoặc default factory |
| Selector sau resolve không parse được | JMS provider | Test grammar trên broker, kiểm tra quote |
| Selector hợp lệ nhưng không nhận message | JMS message metadata | Kiểm tra tên/kiểu property, null/UNKNOWN |
| Thay file config nhưng Queue không đổi | Container lifecycle | Restart/recreate endpoint có kiểm soát |
| Concurrency lớn làm tăng DB pressure | Resource/throughput | Đặt bounds, load test, tối ưu pool |
| Listener nhận data tenant khác | Authorization/routing | Kiểm tra ACL và selector policy |
| Handler ném exception | Business/transaction | Retry/DLQ/idempotency theo policy |
| Queue có backlog nhưng listener không xử lý | Selector quá hẹp hoặc consumer không chạy | Xem broker metrics, consumer count, DLQ |
| Unit test pass nhưng integration fail | Mock chưa kiểm tra broker | Chạy broker test, quan sát error root cause |

Một lỗi selector có thể phát sinh khi container tạo consumer và retry connection, chứ không nhất thiết luôn làm cả JVM process chết ngay. Do đó ngoài validation lúc startup, cần readiness/metrics và alert cho listener thực sự hoạt động.

## 12. Transaction và idempotency không do placeholder quyết định

`@JmsListener` nhận message qua container. Container factory/session transaction quyết định ACK/commit, không phải placeholder.

Nếu handler lưu DB rồi thất bại trước JMS ACK, message có thể được giao lại. Nếu tăng concurrency, handler có thể chạy nhiều thread. Vì vậy:

- Dùng business event ID ổn định để deduplicate.
- Đặt transaction boundary rõ với JMS và database.
- Không suy ra `@Transactional` của JPA tự tạo XA transaction với Artemis.
- Có retry có giới hạn, DLQ, alarm và xử lý poison message.
- Không thay selector lúc production mà không kiểm tra backlog cũ và consumer mới.

Ví dụ cấu hình factory có session transacted chỉ thuộc JMS local transaction; muốn phối hợp DB cần thiết kế riêng. Annotation placeholder không thay thế trách nhiệm này.

## 13. Vận hành và thay đổi cấu hình an toàn

Để thay `app.jms.orders-queue` hoặc `app.jms.order-selector` ở production:

1. Review cấu hình trong source control hoặc hệ thống cấu hình có kiểm soát.
2. Xác minh Queue đích tồn tại, account có quyền và schema property tương thích.
3. Kiểm tra selector chọn đúng loại event và loại trừ những message không mong muốn.
4. Kiểm tra concurrency với DB connection pool và handler thread safety.
5. Chạy integration tests có match, non-match, invalid property, redelivery.
6. Triển khai canary hoặc một phiên bản trước; giám sát backlog/consumer count.
7. Có rollback plan khi selector mới làm Queue tồn đọng message.
8. Không hứa một config update runtime tự thay đổi consumer đang chạy.
9. Với Topic durable, kiểm tra subscription identity và chính sách chuyển đổi.
10. Ghi log effective non-secret configuration (destination name, selector fingerprint/config version) ở mức cần thiết, không lộ thông tin nhạy cảm.

**Điểm quan trọng:** nếu chuyển listener sang Queue mới trong khi producer vẫn publish Queue cũ, ứng dụng có thể “healthy” nhưng không nhận event. Health checks cần bao gồm consumer registration và quan sát message delivery, không chỉ kiểm tra JVM startup.

## 14. Bài tập mở rộng

### Bài tập 1: môi trường staging

Tạo `application-staging.properties` dùng Queue `orders.staging.in`, selector cho `region='SG'` và concurrency `1`. Không đổi Java source. Verify trên broker test rằng message VN không vào listener staging.

### Bài tập 2: selector bị thiếu property

Gửi một TextMessage không có `region` nhưng có `eventType=order.created`. Xác minh không match `region = 'VN'`. Giải thích logic ba giá trị và viết một selector rõ ràng có `region IS NULL` nếu ứng dụng thật muốn nhận cả message thiếu region.

### Bài tập 3: SpEL policy bean

Viết `RoutingPolicy` có allowlist tên Queue. Dùng `@JmsListener(destination = "#{@routingPolicy.ordersQueue()}")`, test Spring context khi destination đúng format và khi cấu hình vi phạm policy.

### Bài tập 4: thay đổi concurrency

Chạy lần lượt `app.jms.listener-concurrency=1` và `2-4` trên Queue test có nhiều message. Quan sát số consumer/throughput và đảm bảo handler không lưu trạng thái message vào field dùng chung không đồng bộ.

### Bài tập 5: config drift

Cố ý deploy producer sang Queue `orders.v2` nhưng consumer còn nghe `orders.v1`. Viết checklist xác minh effective configuration, queue depth, ACL và rollout để phát hiện sai lệch trước khi production.

## 15. Câu hỏi tự kiểm tra

**1.** `${...}` và `#{...}` khác nhau thế nào?

Placeholder đọc giá trị từ Spring Environment; SpEL đánh giá biểu thức Spring, thường lấy String qua một bean được kiểm soát. Cả hai giải quyết cấu hình endpoint, không chạy theo từng message.

**2.** Có thể truyền field instance Java trực tiếp vào thuộc tính annotation không?

Không. Java annotation đòi constant expression; String literal chứa placeholder hoặc SpEL là cách để Spring resolve ở runtime.

**3.** `selector = "${app.jms.order-selector}"` có cho phép broker đọc JSON body không?

Không. Chuỗi sau khi resolve vẫn là JMS selector áp trên JMS headers/properties, không phải JSONPath.

**4.** Khi sửa `application.properties` trong lúc ứng dụng chạy, annotation có tự nhận giá trị mới không?

Không mặc định. Listener endpoint/container đã được cấu hình; cần restart hoặc tái đăng ký/reconfigure có kiểm soát.

**5.** Vì sao không nên lấy nguyên SpEL expression từ HTTP request?

Vì SpEL có thể gọi bean/method theo evaluation context; input không tin cậy có thể thay đổi logic và gây nguy cơ bảo mật.

**6.** `concurrency = "2-6"` có nghĩa là luôn sáu thread không?

Không. Đây là giới hạn theo container, actual concurrency phụ thuộc implementation và workload.

**7.** `id = "ordersListener"` dùng để làm gì?

Định danh endpoint/container cho `JmsListenerEndpointRegistry` và khả năng quản lý lifecycle.

**8.** Vì sao selector không đủ để cách ly tenant?

Nó chỉ lọc message được deliver; ACL và destination isolation mới là security boundary.

**9.** Giá trị fallback trong placeholder có rủi ro gì?

Production có thể âm thầm nghe Queue demo/sai nếu deployment thiếu property, thay vì báo lỗi sớm.

**10.** Unit test trực tiếp method listener có xác minh selector được Artemis thực thi không?

Không. Cần integration test với broker để xác minh property types và selector matching.

## 16. Tài liệu chính thức

- Spring Framework 6.1 — Javadoc `@JmsListener`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — Value annotations và placeholder: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html
- Spring Framework — Spring Expression Language: https://docs.spring.io/spring-framework/reference/core/expressions.html
- Spring Boot 3.3 — JMS support: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Jakarta Messaging 3.1 — Message selection: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html

**Tóm lại:** Dùng `${...}` cho các giá trị cấu hình đơn giản và được quản trị; dùng `#{...}` chỉ khi cần tính giá trị từ bean đáng tin cậy. Annotation được resolve khi đăng ký listener, còn JMS selector được broker áp lên từng message. Bảo đảm chất lượng bằng validation, ACL, concurrency limits, integration tests và deployment policy rõ ràng.
