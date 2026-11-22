# ApplicationEventPublisherAware và lựa chọn tiêm hợp đồng hẹp trong Spring Framework

## Mục tiêu

Trong Spring Core Container, một bean đôi khi cần sử dụng dịch vụ do chính `ApplicationContext` cung cấp. Với yêu cầu **phát sự kiện nội bộ**, không nhất thiết đưa cả `ApplicationContext` vào code nghiệp vụ. Spring cung cấp interface **`ApplicationEventPublisher`** chỉ có trách nhiệm phát sự kiện, và callback **`ApplicationEventPublisherAware`** để container cấp publisher cho bean sau khi tạo.

Bài học thuộc nhóm **Callback Aware** và tập trung vào hai vấn đề liên quan trực tiếp:

1. Spring nhận diện, gọi `ApplicationEventPublisherAware.setApplicationEventPublisher(...)` vào thời điểm nào và vì sao callback này hoạt động.
2. Vì sao nên **phụ thuộc vào hợp đồng hẹp `ApplicationEventPublisher`** (thường qua constructor injection) thay vì đưa toàn bộ `ApplicationContext`/`ApplicationContextAware` vào service chỉ cần phát sự kiện.

Khi hoàn thành, bạn sẽ có thể viết cả cách Aware callback và constructor injection, phát/nhận sự kiện với `@EventListener`, phân biệt synchronous/async dispatch, thử unit test không cần khởi động context, đồng thời nhận ra các giới hạn quan trọng của event bus nội bộ Spring.

## 1. Bức tranh tổng thể: bean cần một phần năng lực của context

`ApplicationContext` mở rộng các API thuộc container và có nhiều chức năng: truy xuất bean, phát sự kiện, đọc message, đọc resource, quản lý vòng đời, v.v. Nhưng một service phát sự kiện nghiệp vụ thường chỉ cần:

~~~java
publisher.publishEvent(event);
~~~

Nếu service phụ thuộc trực tiếp vào `ApplicationContext`, service có thể gọi thêm `getBean(...)`, tra tài nguyên hoặc điều khiển container ngoài nhu cầu ban đầu. Điều này làm dependency rộng và khiến unit test phải mô phỏng nhiều khả năng không cần thiết.

Spring cung cấp hợp đồng hẹp:

~~~java
package org.springframework.context;

@FunctionalInterface
public interface ApplicationEventPublisher {
    void publishEvent(Object event);

    // Overload dành cho ApplicationEvent được khai báo trong API thực tế.
    // default void publishEvent(ApplicationEvent event) ...
}
~~~

Đây là **bản mô tả API giản lược**, không phải mã nguồn cần tạo trong ứng dụng. Import thực tế là:

~~~java
import org.springframework.context.ApplicationEventPublisher;
~~~

`ApplicationContext` kế thừa `ApplicationEventPublisher`, nên một context chính nó có thể đóng vai trò publisher. Điều đó không có nghĩa service phải tham chiếu context qua kiểu `ApplicationContext`. Nó có thể chỉ biết interface publisher.

~~~text
                     Spring ApplicationContext
                              |
                 implements ApplicationEventPublisher
                              |
                +-------------+--------------+
                |                            |
    ApplicationEventPublisherAware     Constructor injection
    setApplicationEventPublisher(...)  (ApplicationEventPublisher)
                |                            |
                +-------------+--------------+
                              |
                              v
                         Service bean
                              |
                        publishEvent(...)
                              |
                              v
                     ApplicationEventMulticaster
                              |
                              v
                    @EventListener / listener
~~~

**Phạm vi của `ApplicationEventPublisher`:** đây là API phát **Spring application events** bên trong hệ thống eventing của context. Nó không phải message broker durable như Kafka, không phải HTTP publisher và không tự đảm bảo event được lưu trên disk hoặc chuyển sang một máy khác.

## 2. Callback Aware là gì?

Spring định nghĩa marker interface `org.springframework.beans.factory.Aware`. Các interface chuyên biệt của nó giúp bean yêu cầu một object thuộc hạ tầng container thông qua callback. Ví dụ:

| Interface | Tham số Spring cung cấp | Khi thích hợp |
| --- | --- | --- |
| `BeanNameAware` | Tên bean trong BeanFactory | Infrastructure cần biết tên bean |
| `BeanFactoryAware` | `BeanFactory` | Thành phần hạ tầng thực sự cần factory |
| `ApplicationContextAware` | `ApplicationContext` | Framework integration cần nhiều API context |
| `ApplicationEventPublisherAware` | `ApplicationEventPublisher` | Bean cần phát application events |
| `MessageSourceAware` | `MessageSource` | Bean cần giải quyết message/i18n |
| `ResourceLoaderAware` | `ResourceLoader` | Bean chỉ cần tải tài nguyên |

Có thể thấy `ApplicationEventPublisherAware` nói rất rõ **nhu cầu nhận publisher**, trong khi `ApplicationContextAware` trao một dependency rộng hơn nhiều.

### 2.1. Giao diện ApplicationEventPublisherAware

Chữ ký:

~~~java
package org.springframework.context;

public interface ApplicationEventPublisherAware
        extends org.springframework.beans.factory.Aware {

    void setApplicationEventPublisher(
            ApplicationEventPublisher applicationEventPublisher);
}
~~~

Đây là **bản trích hình thức API để giải thích**, không phải file Java cần tạo trong project.

Để sử dụng:

~~~java
import java.util.Objects;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;

public class AuditPublisher implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher publisher;

    @Override
    public void setApplicationEventPublisher(
            ApplicationEventPublisher publisher) {
        this.publisher = Objects.requireNonNull(publisher);
    }

    public void audit(String action) {
        publisher.publishEvent(new AuditOccurred(action));
    }
}
~~~

`AuditOccurred` là kiểu sự kiện do ứng dụng khai báo (ví dụ record ở mục 6). Đây là **snippet minh họa phụ thuộc vào một event type riêng**, chưa phải một chương trình biên dịch độc lập.

Ở đây Spring gọi setter **một cách tự động** khi `AuditPublisher` là Spring-managed bean trong một `ApplicationContext` có processor tương ứng. Không cần tự gọi `setApplicationEventPublisher(...)` trong code nghiệp vụ.

### 2.2. Thời điểm container gọi callback

Chu trình đơn giản hóa:

~~~text
BeanDefinition được đăng ký
    |
    v
Constructor/factory method tạo bean instance
    |
    v
Populate các dependency/property bình thường
    |
    v
ApplicationContextAwareProcessor xử lý các callback Aware hỗ trợ
    |
    +--> ApplicationEventPublisherAware.setApplicationEventPublisher(...)
    |
    +--> ApplicationContextAware.setApplicationContext(...) nếu bean có implement
    |
    v
Initialization callbacks (@PostConstruct, InitializingBean, init-method)
    |
    v
Bean sẵn sàng sử dụng
~~~

Theo Javadoc, `setApplicationEventPublisher(...)` được gọi **sau bước population của thuộc tính thông thường nhưng trước initialization callbacks**, và trước `ApplicationContextAware.setApplicationContext(...)` nếu cùng một bean implement cả hai. Không nên biến thứ tự callback thành một cơ chế phối hợp nghiệp vụ; nó là hợp đồng lifecycle của container.

**Lưu ý quan trọng:** publisher được truyền thường chính là context hiện hành, nhưng được cung cấp thông qua **kiểu interface hẹp**. Nếu bạn ép kiểu về `ApplicationContext` chỉ để lấy thêm beans, bạn đã đánh mất mục tiêu thiết kế của hợp đồng hẹp.

### 2.3. Ai thật sự gọi callback?

Bean chỉ implement interface chưa có tác dụng khi được tạo bằng `new`. `ApplicationContextAwareProcessor` là thành phần Spring đảm nhận các callback hạ tầng liên quan đến application context, publisher, resource loader và message source.

Khi bạn:

~~~java
AuditPublisher audit = new AuditPublisher();
audit.audit("created");
~~~

không có container nào gọi setter, nên `publisher` sẽ là `null` và lời gọi bị lỗi. Với mã chạy ngoài Spring, bạn phải cung cấp publisher thật/fake thủ công hoặc chuyển sang constructor injection.

## 3. Vì sao ApplicationEventPublisher là hợp đồng hẹp?

So sánh:

~~~java
// Dependency rộng: có quyền truy cập nhiều API container.
class LegacyService {
    private final ApplicationContext context;

    LegacyService(ApplicationContext context) {
        this.context = context;
    }

    void complete(String id) {
        context.publishEvent(new Completed(id));
    }
}
~~~

~~~java
// Dependency hẹp: service chỉ có API phát sự kiện.
class FocusedService {
    private final ApplicationEventPublisher publisher;

    FocusedService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void complete(String id) {
        publisher.publishEvent(new Completed(id));
    }
}
~~~

Hai đoạn trên là **mã minh họa**, yêu cầu import Spring tương ứng và event type `Completed`. Trong việc phát sự kiện, hành vi tương tự; nhưng chữ ký constructor thứ hai nói đúng năng lực service cần.

Điểm lợi:

- **Giảm phụ thuộc vào container API rộng:** service không có `getBean()`, `getEnvironment()` hoặc resource loading chỉ vì nó muốn phát event.
- **Dễ đọc trách nhiệm:** nhìn vào constructor đã biết object dùng để làm gì.
- **Dễ unit test:** chỉ cần một implementation `ApplicationEventPublisher` ghi lại các event.
- **Tránh service locator:** không kéo thêm bean theo tên/kiểu vào giữa method.
- **Thay thế implementation dễ hơn:** có thể dùng fake publisher hoặc adapter khác mà service không cần toàn context.
- **Rõ ràng về thời điểm có dependency:** constructor injection tạo service cùng với dependency hợp lệ; không có giai đoạn instance đã được tạo nhưng field publisher chưa được điền.

Từ “hợp đồng hẹp” ở đây chỉ **surface API mà consumer có thể gọi**, không khẳng định implementation nội bộ của context chỉ biết phát event.

## 4. Hai cách nhận publisher: Aware callback và constructor injection

### 4.1. Aware: container chèn publisher sau khi tạo bean

~~~java
@Component
public class PaymentService implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher publisher;

    @Override
    public void setApplicationEventPublisher(ApplicationEventPublisher publisher) {
        this.publisher = Objects.requireNonNull(publisher);
    }

    public void confirm(String paymentId) {
        publisher.publishEvent(new PaymentConfirmed(paymentId));
    }
}
~~~

Đoạn này minh họa một Spring-managed component cần import `@Component`, `Objects` và các interface Spring. Event `PaymentConfirmed` do ứng dụng định nghĩa.

**Ưu điểm:** tương thích kiểu cấu hình/extension API phụ thuộc Aware, framework tự cung cấp publisher mà không cần thay constructor.

**Hạn chế:** phụ thuộc được chèn sau constructor, field không thể là `final`, object chưa dùng được đầy đủ khi bị tạo trực tiếp bằng `new`; người đọc ít thấy dependency hơn khi nhìn constructor.

### 4.2. Constructor injection: biểu diễn dependency rõ ràng

~~~java
@Component
public class PaymentService {
    private final ApplicationEventPublisher publisher;

    public PaymentService(ApplicationEventPublisher publisher) {
        this.publisher = Objects.requireNonNull(publisher);
    }

    public void confirm(String paymentId) {
        publisher.publishEvent(new PaymentConfirmed(paymentId));
    }
}
~~~

Đây là phương án **thường nên chọn cho application/service code mới**. Spring có thể resolve `ApplicationEventPublisher` khi constructor injection vì context cung cấp dependency hạ tầng tương ứng. Một constructor duy nhất không nhất thiết phải có `@Autowired` trong cấu hình Spring hiện đại.

**Không cần triển khai cả hai** cho cùng mục đích. Nếu đã constructor-inject `ApplicationEventPublisher`, thường không cần implement `ApplicationEventPublisherAware`; ngược lại, khi một framework class buộc dùng Aware hoặc lifecycle wiring, callback Aware hoàn toàn hợp lệ.

### 4.3. Tiêm hợp đồng hẹp khác với chuyển hết context qua constructor

~~~java
public class OverpoweredService {
    private final ApplicationContext context;

    public OverpoweredService(ApplicationContext context) {
        this.context = context;
    }
}
~~~

Dù đã dùng constructor injection, loại dependency ở đây vẫn là **toàn ApplicationContext**. Kỹ thuật inject không tự đảm bảo API hẹp: cần chọn **đúng kiểu hợp đồng**.

### 4.4. Khi nào ApplicationContextAware thực sự hợp lý?

Một integration component có thể cần đăng ký tự động dựa trên thông tin context, lấy resource, biết bean names hay làm framework bootstrap. Nếu nhiệm vụ **thực sự** đòi API rộng, `ApplicationContextAware` có thể hợp lý. Vấn đề là lạm dụng nó trong business service chỉ để `publishEvent`.

Đừng xem `ApplicationContextAware` là cách “lấy tất cả bean bất cứ lúc nào” thay cho dependency injection; điều đó giấu quan hệ phụ thuộc, tăng rủi ro circular dependency và làm unit test khó hơn.

## 5. Phát sự kiện: ApplicationEvent và payload object

`ApplicationEventPublisher` có các overload:

~~~java
publisher.publishEvent(new OrderSubmittedEvent(source, orderId));
publisher.publishEvent(new OrderSubmitted(orderId));
~~~

Đây là **snippet minh họa**. Dòng đầu dùng class extends `ApplicationEvent`, dòng sau dùng object tùy ý (`record` chẳng hạn) được Spring hỗ trợ từ 4.2.

### 5.1. Class extends ApplicationEvent

~~~java
import org.springframework.context.ApplicationEvent;

public final class OrderSubmittedEvent extends ApplicationEvent {
    private final String orderId;

    public OrderSubmittedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String orderId() {
        return orderId;
    }
}
~~~

Đây là Java class hợp lệ có thể đặt ở `OrderSubmittedEvent.java` trong cùng package với code nhận sự kiện. `source` trong constructor phải không null; event có thêm dữ liệu nghiệp vụ riêng qua `orderId`. Việc kế thừa `ApplicationEvent` phù hợp khi cần tích hợp kiểu listener interface cổ điển `ApplicationListener<OrderSubmittedEvent>`.

### 5.2. Payload event bằng record Java 17

~~~java
public record OrderSubmitted(String orderId) {}
~~~

Đây là một Java record hợp lệ độc lập trong file `OrderSubmitted.java` (khi ở default package) hoặc trong package đã chọn. Nó **không extends `ApplicationEvent`**, nhưng Spring có thể publish record đó thông qua `publishEvent(Object)`. Spring sẽ bọc payload trong `PayloadApplicationEvent` cho infrastructure routing.

Listener dùng `@EventListener` có thể khai báo trực tiếp:

~~~java
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    System.out.println("received " + event.orderId());
}
~~~

Đây là method minh họa nằm trong Spring-managed bean. Annotation `@EventListener` thuộc `org.springframework.context.event.EventListener`. Spring chọn listener theo event type; bạn không phải unwrap `PayloadApplicationEvent` trong một handler kiểu trên.

**Không nhầm event object với message durable:** record chỉ là cấu trúc dữ liệu Java. Event dispatch của ApplicationContext không tự persist record vào database, Kafka, outbox hay filesystem.

## 6. Ví dụ hoàn chỉnh Java 17: Aware và constructor injection cùng phát event

Ví dụ sử dụng **Spring Framework 6.2.9**, không cần Spring Boot hoặc Servlet. Chương trình cố ý dùng **cùng một event record** để so sánh cách chèn publisher, còn `@EventListener` in thông báo nhận sự kiện.

### 6.1. Cây thư mục

~~~text
publisher-aware-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── PublisherAwareDemo.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>publisher-aware-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. src/main/java/demo/PublisherAwareDemo.java

~~~java
package demo;

import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class PublisherAwareDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("context ready");

            context.getBean(AwareOrderService.class).submit("A-1");
            context.getBean(ConstructorOrderService.class).submit("B-2");
        }
    }

    // Một payload event thuần Java, không cần extends ApplicationEvent.
    public record OrderSubmitted(String origin, String orderId) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public AwareOrderService awareOrderService() {
            return new AwareOrderService();
        }

        @Bean
        public ConstructorOrderService constructorOrderService(
                ApplicationEventPublisher publisher) {
            return new ConstructorOrderService(publisher);
        }

        @Bean
        public OrderAuditListener orderAuditListener() {
            return new OrderAuditListener();
        }
    }

    public static class AwareOrderService
            implements ApplicationEventPublisherAware {

        private ApplicationEventPublisher publisher;

        @Override
        public void setApplicationEventPublisher(
                ApplicationEventPublisher publisher) {
            this.publisher = Objects.requireNonNull(publisher);
            System.out.println("aware callback");
        }

        public void submit(String orderId) {
            publisher.publishEvent(new OrderSubmitted("aware", orderId));
            System.out.println("aware publish returned");
        }
    }

    public static class ConstructorOrderService {
        private final ApplicationEventPublisher publisher;

        public ConstructorOrderService(ApplicationEventPublisher publisher) {
            this.publisher = Objects.requireNonNull(publisher);
        }

        public void submit(String orderId) {
            publisher.publishEvent(new OrderSubmitted("constructor", orderId));
            System.out.println("constructor publish returned");
        }
    }

    public static class OrderAuditListener {

        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            System.out.println(
                    "listener " + event.origin() + "/" + event.orderId());
        }
    }
}
~~~

### 6.4. Chạy chương trình

Từ thư mục `publisher-aware-demo`, bảo đảm Java 17+ và Maven sẵn có:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.PublisherAwareDemo
~~~

Với cấu hình mặc định của `AnnotationConfigApplicationContext`, stdout của **chương trình** (không tính log từ Maven/SLF4J nếu môi trường có) là:

~~~text
aware callback
context ready
listener aware/A-1
aware publish returned
listener constructor/B-2
constructor publish returned
~~~

### 6.5. Giải thích chính xác từng dòng

1. `aware callback` được in **khi Spring tạo bean `AwareOrderService`**, sau factory method `@Bean` trả instance và trước khi initialization hoàn tất. Bạn không gọi setter trong `main`.
2. `context ready` xuất hiện sau `new AnnotationConfigApplicationContext(AppConfig.class)` đã refresh xong, các bean thường được khởi tạo và `@EventListener` được đăng ký.
3. `AwareOrderService.submit("A-1")` gọi `publisher.publishEvent(...)`. Listener nhận record payload, in `listener aware/A-1`.
4. Vì multicaster mặc định **đồng bộ**, listener hoàn tất trước khi `publishEvent` trở về; tiếp đó in `aware publish returned`.
5. `ConstructorOrderService` dùng publisher nhận từ constructor, không implement Aware. Sự kiện `B-2` đi qua cùng event bus của context, listener in `listener constructor/B-2` rồi method in `constructor publish returned`.

Một số quan sát:

- `ApplicationEventPublisherAware` không phải event listener. Nó chỉ giúp bean **nhận đối tượng publisher**. Bean lắng nghe event là `OrderAuditListener`, nhờ `@EventListener`.
- Dùng `ApplicationEventPublisher` trong `@Bean` factory method là **tiêm interface hẹp qua dependency resolution**; không cần đăng ký một publisher bean mới bằng tay.
- Cùng một payload type được phát từ hai service khác nhau. Listener phân biệt bằng field `origin` do ví dụ tự định nghĩa, không phải Spring tự thêm thông tin nguồn.
- `OrderSubmitted` là record nested static, tên Java hợp lệ ở `PublisherAwareDemo.OrderSubmitted`. Các class của ví dụ nằm trong một file như cây thư mục, nên không cần tạo nhiều file riêng.
- Không cần Spring Boot để dùng `ApplicationEventPublisherAware`, miễn object là bean được đăng ký trong một `ApplicationContext` cấu hình đúng.

## 7. Callback Aware có thay thế dependency injection không?

**Không.** `ApplicationEventPublisherAware` là một kiểu **container-managed callback injection**: container gọi method sau khi đã tạo bean instance. Constructor injection là cách khác để khai báo dependency.

So sánh theo tiêu chí:

| Tiêu chí | `ApplicationEventPublisherAware` | Constructor injection `ApplicationEventPublisher` |
| --- | --- | --- |
| Nơi khai báo dependency | Implement interface và setter | Constructor parameter |
| Thời điểm nhận | Sau instantiate/property population, trước init | Trong constructor |
| Có thể dùng `final` field | Không theo setter thuần | Có |
| Bean tạo bằng `new` hoạt động ngay? | Không, cần gọi setter thủ công | Có, nếu caller truyền publisher |
| Độ rõ ràng khi đọc constructor | Không thấy publisher trong chữ ký | Rõ ràng |
| Độ phụ thuộc vào Spring lifecycle callback | Có | Không cần Aware callback |
| API được tiếp cận nếu giữ đúng type | Chỉ `ApplicationEventPublisher` | Chỉ `ApplicationEventPublisher` |
| Phù hợp ứng dụng mới | Khi contract Aware có ý nghĩa | Thường ưu tiên |
| Phù hợp với framework/extension bean | Rất hữu ích | Cũng có thể phù hợp nếu framework hỗ trợ |

Một bean vẫn có thể implement Aware để đáp ứng extension point mà nó tham gia. Tốt nhất chọn **một nguồn cấp dependency chính** cho mỗi publisher, tránh tình trạng constructor truyền publisher A nhưng setter Aware ghi đè publisher B khiến behavior khó đoán.

## 8. Unit test hợp đồng hẹp mà không chạy Spring context

Vì `ApplicationEventPublisher` là một functional interface, có thể dùng lambda để ghi lại event thay vì khởi tạo Spring container. Ví dụ **Java 17 + Spring API**, mô tả cách kiểm tra `ConstructorOrderService`:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.context.ApplicationEventPublisher;

// Đoạn code trong một method test, không phải file standalone.
List<Object> published = new ArrayList<>();
ApplicationEventPublisher fakePublisher = published::add;

PublisherAwareDemo.ConstructorOrderService service =
        new PublisherAwareDemo.ConstructorOrderService(fakePublisher);

service.submit("T-1");

if (published.size() != 1) {
    throw new AssertionError("Expected exactly one event");
}

Object event = published.get(0);
if (!(event instanceof PublisherAwareDemo.OrderSubmitted submitted)) {
    throw new AssertionError("Wrong event type");
}
if (!submitted.orderId().equals("T-1")) {
    throw new AssertionError("Wrong order id");
}
~~~

Đoạn này là **logic test minh họa**, không phải file với class/main và không cần chạy JUnit riêng để hiểu nguyên tắc. Vì `service.submit` cũng in một dòng, khi chạy đoạn test có side effect trên stdout; assert kiểm tra danh sách sự kiện độc lập với việc có listener thực hay không.

Kiểm tra tương tự cho Aware:

~~~java
List<Object> published = new ArrayList<>();
ApplicationEventPublisher fakePublisher = published::add;

PublisherAwareDemo.AwareOrderService service =
        new PublisherAwareDemo.AwareOrderService();

service.setApplicationEventPublisher(fakePublisher);
service.submit("T-2");

// Kiểm tra published chứa một OrderSubmitted(origin="aware", orderId="T-2").
~~~

Ở trường hợp thứ hai, test **phải tự gọi setter** vì không có Spring-managed lifecycle. Đó là khác biệt về ergonomics giữa Aware và constructor injection, dù cả hai đều có thể test bằng fake publisher.

### Điều test trên chứng minh và không chứng minh

Nó chứng minh service **gọi publisher với đúng payload**. Nó chưa chứng minh Spring đăng ký listener hay sự kiện được dispatch qua multicaster. Để kiểm tra end-to-end, tạo `AnnotationConfigApplicationContext` như ví dụ mục 6, hoặc Spring integration test với listener/test event recorder phù hợp.

Nếu business service trực tiếp phụ thuộc `ApplicationContext`, việc tạo fake chỉ cần `publishEvent` sẽ phức tạp hơn vì bạn phải mock interface rộng hoặc tạo context thật. Đây là một lý do quan trọng để chọn dependency hẹp.

## 9. Publish và receive: hợp đồng của publisher không quy định thực thi synchronous hay asynchronous

`ApplicationEventPublisher.publishEvent(...)` có nghĩa **bàn giao một event cho infrastructure phát sự kiện**. Interface không cam kết mọi listener sẽ chạy đồng bộ, bất đồng bộ hoặc lập tức. Chính `ApplicationEventMulticaster` và cấu hình listener quyết định.

### 9.1. Mặc định synchronous

Với `SimpleApplicationEventMulticaster` mặc định của Spring context, không cấu hình task executor bất đồng bộ, listeners thông thường được gọi **trong thread của publisher**. Khi đó:

~~~text
service.submit()
    |
    +-- publisher.publishEvent(event)
    |      |
    |      +-- listener1.onEvent(event)  (chạy và trả về)
    |      +-- listener2.onEvent(event)  (chạy và trả về)
    |
    +-- publishEvent() trả về
    |
    +-- service tiếp tục
~~~

Do đó ví dụ mục 6 có thứ tự stdout ổn định. Nếu một listener ném RuntimeException và multicaster không có error handler thay thế, exception có thể propagate tới người gọi `publishEvent` và ngăn listener tiếp theo chạy. Không dùng `publishEvent` như “fire-and-forget chắc chắn không bao giờ lỗi”.

### 9.2. Khi cấu hình async

Các lựa chọn thường gặp:

- Listener riêng đặt `@Async` cùng cấu hình `@EnableAsync` và executor hợp lệ.
- Cấu hình bean `applicationEventMulticaster` với `SimpleApplicationEventMulticaster.setTaskExecutor(...)`.
- Tách side effect lớn sang queue/event broker khi cần bền vững hay retry ngoài process.

Với async, publish có thể trả về trước khi listener hoàn tất. Exceptions từ `@Async void` listener không tự propagate về caller; phải dùng error handling/observability thích hợp. ThreadLocal như security context, transaction context, MDC không tự chuyển qua thread worker khi không có propagation strategy.

Lựa chọn constructor injection hay Aware **không làm event trở thành async**. Đó là trách nhiệm của infrastructure nhận event.

### 9.3. Events và transaction

Nếu một listener synchronous được gọi trong thread publisher, nó có thể thấy transaction context hiện tại, nếu transaction đã active. Nhưng điều đó không có nghĩa event được lưu sau commit.

Với side effect cần thực thi sau transaction commit, có thể dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` trong module Spring Transaction phù hợp, hoặc transactional outbox để có độ bền cao hơn. Theo mặc định, `@TransactionalEventListener` không có transaction thì không chạy (trừ khi cấu hình `fallbackExecution = true`).

Nói “event đã publish” không đồng nghĩa “transaction đã commit”, “listener khác chắc chắn thành công”, hoặc “message đã được gửi đi qua mạng”.

## 10. Sự kiện có thể phát từ đâu và ai nhận?

Bean phát event cần thuộc một `ApplicationContext` đang hoạt động, hoặc được truyền một implementation `ApplicationEventPublisher` phù hợp. Bean nhận event thông thường cũng được **đăng ký cùng context** qua `@Component`, `@Bean` hoặc listener registration.

Ví dụ annotation listener:

~~~java
@Component
public class ShippingListener {

    @EventListener
    public void afterOrderSubmitted(OrderSubmitted event) {
        // Đọc dữ liệu của event và thực hiện hành động mong muốn.
    }
}
~~~

Đây là snippet trong cùng package/import hợp lệ và giả định có kiểu `OrderSubmitted`. Nếu dùng nested record của ví dụ mục 6 từ class khác, viết `PublisherAwareDemo.OrderSubmitted` hoặc import nested type.

Các điều kiện thường bị bỏ sót:

1. **Listener phải là bean** và Spring cần phát hiện `@EventListener` trong quá trình tạo/refresh context.
2. Event type phải khớp argument của listener. Một listener cho `InvoiceGenerated` không tự nhận `OrderSubmitted`.
3. Đừng publish nghiệp vụ từ **constructor bean** khi hệ thống listeners chưa được đăng ký đầy đủ.
4. `@PostConstruct` cũng có thể quá sớm cho việc phát event nghiệp vụ, vì lifecycle initialization chưa đồng nghĩa context đã hoàn tất listener registration. Nếu thật sự cần event sau context startup, chọn hook phù hợp như `ContextRefreshedEvent` (Core) hoặc `ApplicationReadyEvent` (Spring Boot) theo mục tiêu.
5. `ApplicationEventPublisherAware` chỉ cung cấp publisher; nó không tự động đăng ký object thành listener nếu không có `@EventListener`/`ApplicationListener`.
6. Một hierarchy của parent/child contexts có thể ảnh hưởng nơi listener được đăng ký và propagation: event publish từ child context có thể được truyền lên parent; không mặc nhiên phát ngược từ parent xuống mọi child.
7. Lazy listeners có thể không được đăng ký như mong đợi nếu hạ tầng không khởi tạo chúng theo đường dẫn phù hợp. Tránh áp dụng `@Lazy` lên event listener mà chưa hiểu lifecycle.

### @EventListener so với ApplicationListener

Hai lựa chọn nhận event:

~~~java
@Component
class ModernListener {
    @EventListener
    public void receive(OrderSubmitted event) {
        // Handler được Spring phát hiện qua annotation.
    }
}
~~~

~~~java
@Component
class ClassicListener
        implements ApplicationListener<OrderSubmittedEvent> {

    @Override
    public void onApplicationEvent(OrderSubmittedEvent event) {
        // Handler type-safe cho class extends ApplicationEvent.
    }
}
~~~

Đây là snippets cần import `Component`, `EventListener`, `ApplicationListener` và event types tương ứng. `ClassicListener` phải nhận type extends `ApplicationEvent`, trong khi phương án `@EventListener` có thể nhận **payload record** như `OrderSubmitted`. Không ghi `ApplicationListener<OrderSubmitted>` nếu `OrderSubmitted` chỉ là record thường; generic contract của `ApplicationListener` yêu cầu `ApplicationEvent`.

## 11. Có nên tạo interface ứng dụng còn hẹp hơn publisher không?

`ApplicationEventPublisher` đã khá hẹp so với `ApplicationContext`, nhưng nó vẫn là **Spring API** và cho phép publish bất kỳ `Object` nào. Nếu domain/application layer cần độc lập Spring hoặc chỉ được phát một loại sự kiện, có thể định nghĩa **port** riêng:

~~~java
public interface OrderEventSink {
    void submitted(String orderId);
}
~~~

Service nghiệp vụ phụ thuộc `OrderEventSink`:

~~~java
public final class CheckoutUseCase {
    private final OrderEventSink events;

    public CheckoutUseCase(OrderEventSink events) {
        this.events = events;
    }

    public void checkout(String orderId) {
        // Thực hiện logic của use case.
        events.submitted(orderId);
    }
}
~~~

Spring adapter:

~~~java
@Component
public class SpringOrderEventSink implements OrderEventSink {
    private final ApplicationEventPublisher publisher;

    public SpringOrderEventSink(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void submitted(String orderId) {
        publisher.publishEvent(new OrderSubmitted(orderId));
    }
}
~~~

Đây là **bộ snippets kiến trúc**, mỗi public type cần file và package/import thích hợp, và `OrderSubmitted` phải có constructor/record phù hợp. Không phải một dự án chạy độc lập; ví dụ runnable ở mục 6 dùng trực tiếp Spring publisher.

Thiết kế adapter có ý nghĩa khi hệ thống cần ranh giới rõ giữa domain và framework hoặc có nhiều backend (Spring event, broker, test fake). Đừng thêm abstraction riêng khi chỉ có một service nhỏ và interface `ApplicationEventPublisher` đã đáp ứng tốt nhu cầu; chi phí abstraction cũng cần tương xứng.

## 12. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `publisher` null khi gọi method | Class implement Aware nhưng được tạo bằng `new`, Spring chưa gọi setter | Đăng ký thành Spring bean hoặc inject publisher qua constructor |
| Setter `setApplicationEventPublisher` không được gọi | Bean không thuộc ApplicationContext đúng hoặc Aware processing không được áp dụng | Kiểm tra bean registration, lifecycle processors và context |
| Code chỉ cần publish nhưng implements `ApplicationContextAware` | Dependency rộng và service locator không cần thiết | Đổi thành constructor injection `ApplicationEventPublisher` hoặc `ApplicationEventPublisherAware` |
| Listener không nhận event | Listener không là Spring bean, context khác, sai event type | Đăng ký đúng context và kiểm tra type/filter |
| Event được publish trong constructor nhưng không thấy listener | Context chưa hoàn tất infrastructure/listener registration | Phát sau context ready và khi nghiệp vụ phát sinh |
| Runtime exception trong listener làm service gọi publisher lỗi | Mặc định dispatch đồng bộ, không cấu hình handler | Thiết kế error handling hoặc tách việc dài hạn sang async/broker |
| `publishEvent` trả về nhưng listener chưa xong | Đã cấu hình async listener/multicaster | Không giả định synchronous sau khi tùy biến infrastructure |
| ThreadLocal/transaction/security context biến mất ở listener | Listener chạy trên thread khác | Dùng propagation strategy hoặc truyền dữ liệu cần thiết trong payload |
| Method `@EventListener` không hoạt động | Method/class không được Spring quản lý hoặc type không khớp | Kiểm tra component scanning, `@Bean` registration, event types |
| `ApplicationListener<OrderSubmitted>` không compile | Payload record không extends `ApplicationEvent` | Dùng `@EventListener` với payload hoặc tạo event extends `ApplicationEvent` |
| Event sau DB update nhưng bên nhận đọc dữ liệu chưa commit | Publish bên trong transaction, listener synchronous hoặc sai phase | Dùng `@TransactionalEventListener` phù hợp, hiểu commit/rollback semantics |
| Event “mất” khi ứng dụng crash | Spring application events không phải durable queue | Dùng outbox/message broker với durability/retry khi cần |
| Inject `ApplicationEventPublisher` không có bean do mình khai báo | Nhầm dependency nội bộ của context với user-defined bean | Trong context thông thường, Spring resolve publisher qua infrastructure; không cần `@Bean` publisher riêng |
| Test phải khởi động toàn Spring chỉ để kiểm tra payload | Service phụ thuộc `ApplicationContext`/lifecycle callback rộng | Inject interface hẹp và fake publisher trong unit test |

### Các bước điều tra ngắn gọn

1. Có bean definition của publisher/consumer trong **ApplicationContext** cần thiết không?
2. Nếu dùng Aware: setter đã được Spring gọi **trước khi method nghiệp vụ chạy** chưa?
3. Nếu dùng constructor: dependency `ApplicationEventPublisher` đã được resolve không?
4. Sự kiện là `ApplicationEvent` hay payload object? Listener đang nhận đúng type không?
5. Listener có được phát hiện/đăng ký không? Có `@Lazy`, event filter/condition hoặc hierarchy không?
6. Multicaster đang synchronous hay asynchronous? Exception handling của listener ra sao?
7. Việc nghiệp vụ mong đợi phụ thuộc transaction commit/durability không? Nếu có, Spring in-process event có thể chưa đủ.

## 13. Checklist thiết kế và kiểm thử

- [ ] Nếu chỉ cần phát sự kiện, khai báo dependency kiểu **`ApplicationEventPublisher`** thay vì `ApplicationContext`.
- [ ] Ưu tiên **constructor injection** cho code ứng dụng mới; chỉ implement `ApplicationEventPublisherAware` khi callback/lifecycle extension có lý do.
- [ ] Bean Aware được **ApplicationContext quản lý**, không tự tạo rồi kỳ vọng callback chạy.
- [ ] Không phát event nghiệp vụ trong constructor khi listeners chưa sẵn sàng.
- [ ] Event payload chỉ chứa dữ liệu cần thiết, không giữ mutable entity/session/request object sống ngoài ngữ cảnh.
- [ ] Listener được đăng ký thành Spring bean và nhận đúng type.
- [ ] Thử cả dispatch mặc định synchronous và thay đổi sang async nếu ứng dụng có cấu hình.
- [ ] Không giả định event là durable hoặc gắn với commit.
- [ ] Với transaction side effects, cân nhắc `@TransactionalEventListener` hoặc outbox.
- [ ] Unit test publisher bằng fake/lambda; integration test để xác thực listener registration và dispatch.
- [ ] Đừng ép kiểu publisher về `ApplicationContext` chỉ để gọi `getBean`.
- [ ] Với nhiều contexts, kiểm tra context đang sở hữu publisher/listeners.

## 14. Câu hỏi tự kiểm tra

**Câu 1. Bean implement `ApplicationEventPublisherAware` được Spring cấp thông tin gì?**  
Một đối tượng `ApplicationEventPublisher` thông qua `setApplicationEventPublisher(...)`. Với cấu hình thông thường, đó chính là context đang chứa bean nhưng được nhìn qua interface hẹp.

**Câu 2. Callback được gọi trước hay sau constructor và `@PostConstruct`?**  
Nó được gọi sau tạo instance/population của các property bình thường và trước initialization callback như `@PostConstruct`.

**Câu 3. Vì sao không nên dùng `ApplicationContextAware` chỉ để phát event?**  
Vì nó trao API rộng không cần thiết, che giấu dependency và khuyến khích service locator. `ApplicationEventPublisher` diễn đạt đúng năng lực mà service cần.

**Câu 4. Khi đã inject `ApplicationEventPublisher` qua constructor, có phải implement Aware nữa không?**  
Không. Constructor injection đã cung cấp dependency; Aware callback là một cơ chế thay thế.

**Câu 5. Một record Java 17 có thể được publish dù không extends `ApplicationEvent` không?**  
Có. Spring hỗ trợ payload objects; framework bọc chúng bằng `PayloadApplicationEvent`. `@EventListener` có thể nhận payload type tương ứng.

**Câu 6. `ApplicationEventPublisherAware` có giúp bean trở thành listener không?**  
Không. Nó chỉ cung cấp publisher. Để nhận event, cần `@EventListener` hoặc `ApplicationListener` cùng registration phù hợp.

**Câu 7. Khi publisher.publishEvent(...) trả về, listener đã hoàn tất chắc chắn chưa?**  
Không phải theo interface contract. Với multicaster mặc định synchronous thường đã hoàn tất, nhưng cấu hình async có thể khiến listener còn chạy sau khi publish trả về.

**Câu 8. Có thể unit test service mà không cần context không?**  
Có, nhất là service nhận `ApplicationEventPublisher` qua constructor. Dùng fake publisher/lambda để lưu payload và assert; khi dùng Aware phải set publisher thủ công.

**Câu 9. Vì sao không dùng Spring in-process events thay thế hoàn toàn broker durable?**  
Vì nó không tự lưu event bền vững, không tự chuyển qua JVM và không đảm bảo retry/acknowledgement nếu process crash.

**Câu 10. Vì sao publish event ở `@PostConstruct` có thể gây nhầm lẫn?**  
Vì việc một bean đã initialize chưa bảo đảm toàn bộ event listener infrastructure đã hoàn tất registration. Event nghiệp vụ nên phát khi context đã sẵn sàng và có trigger thực tế.

## Tài liệu tham khảo chính thức

- Spring Framework Reference — [Other Aware Interfaces / Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).
- Spring Framework Reference — [ApplicationContext: Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html).
- Spring Framework Javadoc 6.2 — [ApplicationEventPublisherAware](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisherAware.html).
- Spring Framework Javadoc 6.2 — [ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html).
- Spring Framework Javadoc 6.2 — [ApplicationContextAwareProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/ApplicationContextAwareProcessor.html).
- Spring Framework Javadoc 6.2 — [EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html).
