# Đăng ký listener bằng @Bean

Trong Spring Framework, một event listener phải được đăng ký vào `ApplicationContext` thì mới nhận được event do context phát ra. Ngoài cách đánh dấu class bằng `@Component`, ta có thể khai báo listener bằng một phương thức `@Bean` trong class cấu hình. Spring tạo đối tượng, quản lý vòng đời bean và đưa listener vào cơ chế phân phối event.

Đăng ký bằng `@Bean` hữu ích khi listener đến từ thư viện bên ngoài, khi muốn khai báo thành phần tường minh trong cấu hình, khi cần inject dependency qua tham số factory method hoặc khi muốn bật/tắt listener theo profile và điều kiện cấu hình.

Có hai kiểu listener thường dùng:

- Bean triển khai `ApplicationListener<E>` để nhận event có kiểu `E`.
- Bean thông thường có một hoặc nhiều method được đánh dấu `@EventListener`.

Sau bài học, bạn có thể đăng ký cả hai kiểu bằng `@Bean`, hiểu cách Spring phát hiện chúng, kiểm soát thứ tự và điều kiện đăng ký, đồng thời tránh các lỗi về generic type, bean lifecycle và cấu hình.

## 1. @Bean đăng ký listener như thế nào?

`@Bean` đánh dấu một phương thức trong class cấu hình để Spring gọi và đăng ký giá trị trả về thành bean:

~~~java
@Configuration
public class EventConfiguration {

    @Bean
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }
}
~~~

Ở ví dụ này:

- `EventConfiguration` là class cấu hình được Spring xử lý.
- `orderAuditListener()` là factory method tạo listener.
- Giá trị trả về được đăng ký thành bean với tên mặc định `orderAuditListener`.
- Bean mặc định có scope singleton.
- Spring quản lý quá trình tạo bean và inject dependency nếu cần.

`@Bean` là cơ chế khai báo bean tổng quát, không phải annotation dành riêng cho event. Spring nhận diện listener dựa trên kiểu bean hoặc annotation trên method của bean đó.

Chỉ tạo một object bằng `new OrderAuditListener()` ở một nơi bất kỳ không tự động đăng ký object đó vào event system. Object cần được Spring quản lý trong context hoặc được đăng ký bằng một API listener tường minh khác.

## 2. Cách một: @Bean trả về ApplicationListener

Cách trực tiếp là tạo bean triển khai `ApplicationListener<E>`. Generic type `E` cho Spring biết listener quan tâm đến event nào.

~~~java
public record OrderCreatedEvent(String orderId) {}

public class OrderAuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Audit: " + event.orderId());
    }
}
~~~

Đăng ký class listener:

~~~java
@Configuration
public class EventConfiguration {

    @Bean
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }
}
~~~

Khi publisher phát `OrderCreatedEvent`, Spring chọn listener có kiểu event tương thích và gọi `onApplicationEvent`.

Nếu logic ngắn, có thể dùng lambda:

~~~java
@Bean
ApplicationListener<OrderCreatedEvent> orderAuditListener() {
    return event ->
        System.out.println("Audit: " + event.orderId());
}
~~~

Hãy giữ generic type cụ thể trong kiểu trả về, ví dụ `ApplicationListener<OrderCreatedEvent>`. Tránh raw type `ApplicationListener` vì framework có ít thông tin kiểu hơn để phân giải listener phù hợp.

Nếu listener cần dependency, hãy truyền dependency qua constructor:

~~~java
public class OrderAuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    private final AuditRepository repository;

    public OrderAuditListener(AuditRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        repository.record(event.orderId());
    }
}
~~~

Factory method có thể nhận bean phụ thuộc như tham số:

~~~java
@Bean
OrderAuditListener orderAuditListener(AuditRepository repository) {
    return new OrderAuditListener(repository);
}
~~~

Spring phân giải `AuditRepository` từ các bean trong context khi tạo listener. Cách này giữ dependency rõ ràng và không yêu cầu listener tự tra cứu container.

Dùng `ApplicationListener<E>` khi muốn một class chuyên biệt cho event, muốn hợp đồng kiểu rõ ràng hoặc cần triển khai thêm `Ordered` và các interface liên quan.

## 3. Cách hai: @Bean trả về bean có method @EventListener

Class listener không bắt buộc phải triển khai `ApplicationListener`. Một class thông thường có thể chứa method được đánh dấu `@EventListener`:

~~~java
public class OrderNotificationListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Notify: " + event.orderId());
    }
}
~~~

Đăng ký class đó thành bean:

~~~java
@Configuration
public class EventConfiguration {

    @Bean
    OrderNotificationListener orderNotificationListener() {
        return new OrderNotificationListener();
    }
}
~~~

Spring phát hiện method `@EventListener` trên các bean được quản lý và đăng ký adapter listener tương ứng. Khi event phù hợp được phát, adapter gọi method của bean. Class không cần implements `ApplicationListener`.

Có thể inject dependency qua constructor như các bean khác:

~~~java
public class OrderNotificationListener {

    private final NotificationService notificationService;

    public OrderNotificationListener(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        notificationService.sendOrderCreated(event.orderId());
    }
}
~~~

Factory method:

~~~java
@Bean
OrderNotificationListener orderNotificationListener(
        NotificationService notificationService) {
    return new OrderNotificationListener(notificationService);
}
~~~

Một bean có thể khai báo nhiều method `@EventListener` để xử lý các loại event khác nhau. Nên tách method hoặc class khi các tác vụ có trách nhiệm riêng biệt để cấu hình dễ đọc và kiểm thử.

Không đặt `@EventListener` lên chính factory method `@Bean` để mong Spring đăng ký giá trị trả về làm listener. `@EventListener` đánh dấu method xử lý event bên trong bean; factory method có nhiệm vụ tạo bean.

## 4. So sánh hai kiểu listener

| Tiêu chí | `ApplicationListener<E>` | Bean có `@EventListener` |
|---|---|---|
| Cách nhận event | `onApplicationEvent(E)` | Method có tham số event |
| Khai báo kiểu event | Generic type `E` | Kiểu tham số method |
| Cần implements interface | Có | Không |
| Một bean xử lý nhiều loại event | Có thể dùng nhiều listener hoặc cấu trúc phù hợp | Có thể khai báo nhiều method |
| Điều kiện SpEL | Không có annotation condition tích hợp tương đương | Có `condition` |
| Phù hợp | Listener class chuyên biệt, hợp đồng type rõ | Handler gọn, nhiều method |

Hai cách đều hợp lệ và có thể cùng tồn tại trong một context. Chọn một cách theo trách nhiệm của listener; không cần tạo cả hai cho cùng một tác vụ nếu không có lý do.

## 5. Tên bean, scope và vòng đời

Tên bean mặc định là tên phương thức `@Bean`:

~~~java
@Bean
OrderAuditListener orderAuditListener() {
    return new OrderAuditListener();
}
~~~

Bean có tên `orderAuditListener`. Có thể đặt tên tường minh:

~~~java
@Bean("orderAudit")
OrderAuditListener orderAuditListener() {
    return new OrderAuditListener();
}
~~~

Mặc định bean có scope singleton, tức một instance được quản lý trong context. Đây thường là lựa chọn phù hợp cho listener. Nếu listener giữ state mutable trong field, nhiều event có thể được xử lý trên cùng instance và tạo race condition khi xử lý đồng thời. Ưu tiên listener stateless, giữ dữ liệu của từng event trong biến cục bộ và để service chuyên trách quản lý state nghiệp vụ.

Có thể dùng dependency injection, lifecycle callback và các cơ chế bean khác. Tuy nhiên, tránh phát event nghiệp vụ từ constructor hoặc quá sớm trong quá trình khởi tạo context, khi các listener khác có thể chưa sẵn sàng. Hãy phát event sau khi context đã refresh và các bean cần thiết đã được đăng ký.

## 6. Điều kiện đăng ký listener

Một lợi ích của `@Bean` là có thể kết hợp với annotation cấu hình để quyết định listener có được tạo trong context hay không.

Ví dụ chỉ đăng ký listener ghi audit trong profile `production`:

~~~java
@Configuration
public class EventConfiguration {

    @Bean
    @Profile("production")
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }
}
~~~

Khi profile `production` được kích hoạt, bean được đăng ký. Nếu profile không hoạt động, factory method không tạo bean và listener đó không tham gia phân phối event.

`@Profile` có thể áp dụng cho từng phương thức `@Bean` hoặc class cấu hình. Trong Spring Boot, có thể dùng thêm `@ConditionalOnProperty` nếu dependency Spring Boot phù hợp được thêm vào. `@ConditionalOnProperty` thuộc Spring Boot, không thuộc Spring Framework Core.

## 7. Thứ tự xử lý listener

Nếu nhiều listener cùng nhận một event, có thể chỉ định thứ tự bằng `@Order` hoặc triển khai `Ordered`.

Với listener triển khai interface, đặt order trên class:

~~~java
@Order(1)
public class FirstOrderListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("First");
    }
}
~~~

Với listener method, đặt order trên method:

~~~java
public class SecondOrderListener {

    @EventListener
    @Order(2)
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Second");
    }
}
~~~

Các listener trên vẫn có thể được tạo bằng `@Bean`. Giá trị order nhỏ hơn được ưu tiên trước. Nếu không khai báo order, không nên dựa vào thứ tự khai báo factory method hoặc tên bean. Nếu listener chạy bất đồng bộ, thứ tự được lên lịch không đồng nghĩa với thứ tự hoàn tất.

## 8. ApplicationEventMulticaster và phát hiện listener

`ApplicationContext` sử dụng `ApplicationEventMulticaster` để điều phối việc phân phối event đến listener phù hợp. Trong cấu hình thông thường, Spring sử dụng `SimpleApplicationEventMulticaster` nếu ứng dụng không cung cấp multicaster riêng có tên `applicationEventMulticaster`.

Có hai cơ chế phát hiện listener cần phân biệt:

- Bean triển khai `ApplicationListener` được nhận diện theo interface và kiểu event generic.
- Method `@EventListener` trên bean được phát hiện bởi `EventListenerMethodProcessor`, sau đó Spring đăng ký adapter để multicaster gọi method.

Vì vậy, đăng ký bean bằng `@Bean` là điều kiện để listener được quản lý trong context; kiểu bean hoặc annotation method quyết định cách listener được nhận diện.

Với cấu hình annotation thông thường như `AnnotationConfigApplicationContext`, các processor cần thiết được đăng ký tự động. Nếu xây dựng container tùy biến ở mức thấp, phải bảo đảm annotation configuration processors được bật để `@EventListener` được xử lý.

## 9. Ví dụ hoàn chỉnh: đăng ký hai listener bằng @Bean

Ví dụ dưới đây đăng ký hai kiểu listener trong cùng configuration:

- `OrderAuditListener` triển khai `ApplicationListener<OrderCreatedEvent>`.
- `OrderNotificationListener` là bean thông thường có method `@EventListener`.

Ứng dụng dùng Java 17 và Spring Context 6.2.0.

Cấu trúc thư mục:

~~~text
bean-event-listener-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanEventListenerDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>bean-event-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BeanEventListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/BeanEventListenerDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class BeanEventListenerDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            service.create("ORD-3001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        OrderAuditListener orderAuditListener() {
            return new OrderAuditListener();
        }

        @Bean
        OrderNotificationListener orderNotificationListener() {
            return new OrderNotificationListener();
        }

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    record OrderCreatedEvent(String orderId) {}

    @Order(1)
    static class OrderAuditListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println("Audit listener: " + event.orderId());
        }
    }

    static class OrderNotificationListener {

        @EventListener
        @Order(2)
        public void onOrderCreated(OrderCreatedEvent event) {
            System.out.println(
                "Notification listener: " + event.orderId()
            );
        }
    }

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void create(String orderId) {
            System.out.println("Creating order: " + orderId);
            publisher.publishEvent(new OrderCreatedEvent(orderId));
            System.out.println("Service continues");
        }
    }
}
~~~

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Kết quả stdout:

~~~text
Creating order: ORD-3001
Audit listener: ORD-3001
Notification listener: ORD-3001
Service continues
~~~

Hai listener được tạo và đăng ký từ các factory method `@Bean`. Listener interface được gọi qua `onApplicationEvent`; listener annotation được gọi qua adapter do `@EventListener` tạo ra. Cả hai chạy đồng bộ và order được khai báo tường minh để xác định thứ tự.

## 10. Kiểm thử listener đăng ký bằng @Bean

Có thể kiểm tra bean được đăng ký trong context:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(AppConfig.class)) {
    OrderAuditListener listener =
        context.getBean(OrderAuditListener.class);

    assert listener != null;
}
~~~

Với logic nghiệp vụ quan trọng, nên kiểm thử listener riêng bằng cách gọi method hoặc `onApplicationEvent` trực tiếp và mock dependency. Kiểm thử tích hợp riêng có thể xác nhận factory method `@Bean` tạo listener và multicaster thực sự phân phối event.

Ví dụ listener có dependency:

~~~java
class OrderAuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    private final AuditRepository repository;

    OrderAuditListener(AuditRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        repository.record(event.orderId());
    }
}
~~~

Trong unit test, tạo listener với mock `AuditRepository` rồi gọi `onApplicationEvent` để xác nhận hành vi. Kiểm thử này không cần khởi động Spring context. Một integration test riêng xác nhận cấu hình bean và phân phối event.

## 11. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo listener bằng `new` nhưng không đăng ký thành bean | Context không tự phát hiện object đó. | Khai báo bằng `@Bean` hoặc cơ chế đăng ký listener phù hợp. |
| Đặt `@EventListener` trên factory method `@Bean` | Nhầm vai trò tạo bean với vai trò xử lý event. | Đặt annotation trên method xử lý bên trong bean. |
| Dùng raw `ApplicationListener` | Thiếu thông tin generic về event type. | Khai báo `ApplicationListener<SpecificEvent>`. |
| `@Bean` trả về kiểu quá tổng quát | Spring có thể thiếu thông tin kiểu khi phát hiện listener sớm. | Dùng kiểu trả về cụ thể hoặc generic đầy đủ. |
| Gọi trực tiếp factory method trong cấu hình `proxyBeanMethods = false` | Có thể tạo object mới ngoài vòng quản lý bean. | Để container inject dependency qua tham số method. |
| Listener giữ state mutable mà không đồng bộ | Nhiều event có thể tạo race condition. | Ưu tiên listener stateless hoặc đồng bộ state đúng cách. |
| Dựa vào thứ tự khai báo `@Bean` | Thứ tự xử lý không được bảo đảm theo giả định đó. | Dùng `@Order` hoặc `Ordered`. |
| Phát event quá sớm trong giai đoạn khởi tạo | Listener khác có thể chưa sẵn sàng. | Phát sau khi context refresh và bean cần thiết đã được đăng ký. |
| Nghĩ rằng `@Bean` tự làm listener bất đồng bộ | Listener mặc định vẫn có thể chạy đồng bộ. | Cấu hình async riêng khi phù hợp. |

## 12. Checklist đăng ký listener bằng @Bean

Trước khi hoàn tất cấu hình, hãy kiểm tra:

1. Factory method có nằm trong class cấu hình được Spring xử lý không?
2. Giá trị trả về có đúng là listener class hoặc bean chứa method `@EventListener` không?
3. Nếu triển khai `ApplicationListener`, generic event type có cụ thể không?
4. Nếu dùng `@EventListener`, method có nằm trên bean được quản lý không?
5. Dependency của listener đã được inject qua constructor hoặc factory method chưa?
6. Profile hoặc condition có đúng với môi trường triển khai không?
7. Có cần thứ tự xử lý bằng `@Order` không?
8. Listener có giữ state mutable hoặc chạy đồng thời không?
9. Listener cần chạy đồng bộ, bất đồng bộ hay đợi transaction commit?
10. Cấu hình đã được kiểm tra bằng context test hoặc integration test chưa?

Đăng ký listener bằng `@Bean` là cách tường minh để đưa event handler vào application context. Nếu cần hợp đồng listener rõ ràng, hãy tạo bean triển khai `ApplicationListener<E>`. Nếu muốn handler là class thông thường với một hoặc nhiều method, hãy tạo bean chứa `@EventListener`. Spring quản lý cả hai dạng và đưa chúng vào `ApplicationEventMulticaster`. Giữ generic type cụ thể, inject dependency rõ ràng, quản lý state an toàn và khai báo thứ tự khi cần sẽ giúp cấu hình listener dễ hiểu và ổn định.
