# ApplicationEventPublisherAware

## 1. ApplicationEventPublisherAware là gì?

ApplicationEventPublisherAware là một interface thuộc package org.springframework.context. Một bean triển khai interface này sẽ được Spring thông báo về ApplicationEventPublisher của ApplicationContext đang quản lý bean đó thông qua callback setApplicationEventPublisher(...).

ApplicationEventPublisher là abstraction dùng để phát sự kiện trong Spring. Sau khi nhận publisher, bean có thể gọi publishEvent(...) mà không cần giữ tham chiếu tới toàn bộ ApplicationContext hoặc biết listener nào sẽ nhận sự kiện.

Interface này thuộc nhóm các callback Aware của Spring. Những interface Aware cho phép container cung cấp một số dịch vụ hoặc thông tin môi trường cho bean trong quá trình khởi tạo. Ví dụ, BeanNameAware nhận tên bean, BeanFactoryAware nhận BeanFactory, còn ApplicationEventPublisherAware nhận publisher dùng để phát application event.

Khai báo rút gọn:

~~~java
package org.springframework.context;

public interface ApplicationEventPublisherAware extends Aware {
    void setApplicationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher
    );
}
~~~

Trong ứng dụng thông thường, ApplicationEventPublisher thường được inject trực tiếp qua constructor. ApplicationEventPublisherAware là một cách nhận publisher thông qua lifecycle callback, phù hợp với các thành phần cần tích hợp với cơ chế Aware hoặc cần tương thích với thiết kế bean đã tồn tại.

## 2. Spring gọi callback khi nào?

Khi ApplicationContext tạo bean, Spring thực hiện các bước khởi tạo và chuẩn bị bean trước khi bean sẵn sàng phục vụ ứng dụng. Trong quá trình đó, ApplicationContextAwareProcessor kiểm tra các interface Aware mà bean triển khai.

Đối với ApplicationEventPublisherAware, Spring gọi setApplicationEventPublisher(...) và truyền publisher gắn với context đang quản lý bean. Callback được thực hiện sau khi các thuộc tính bean thông thường đã được thiết lập và trước các initialization callback như InitializingBean.afterPropertiesSet() hoặc custom init-method.

Có thể hình dung trình tự liên quan như sau:

1. Spring tạo instance của bean.
2. Spring inject các dependency và thiết lập các bean property.
3. Spring gọi các callback Aware thích hợp, trong đó có setApplicationEventPublisher(...).
4. Spring chạy các bước khởi tạo như @PostConstruct, afterPropertiesSet() và custom init-method theo lifecycle.
5. Bean hoàn tất quá trình khởi tạo và được đưa vào sử dụng.

Thứ tự cụ thể giữa các cơ chế xử lý bean còn phụ thuộc vào các BeanPostProcessor và cấu hình của ứng dụng. Điểm cần nhớ là publisher được cung cấp trong giai đoạn khởi tạo của bean, trước khi các initialization callback cần dùng tới nó.

Callback không được tự động gọi khi tạo object bằng toán tử new. Bean phải được ApplicationContext quản lý để cơ chế Aware của context thực hiện việc cấp publisher. Nếu tự tạo instance trong unit test, cần gọi callback thủ công hoặc truyền publisher qua một constructor khác theo thiết kế kiểm thử.

## 3. Cách triển khai interface

Một lớp triển khai ApplicationEventPublisherAware phải định nghĩa setApplicationEventPublisher(...). Thông thường, lớp lưu publisher vào một field để các phương thức khác sử dụng:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;

import java.util.Objects;

public class OrderEventPublisher implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher eventPublisher;

    @Override
    public void setApplicationEventPublisher(
            ApplicationEventPublisher applicationEventPublisher) {
        this.eventPublisher =
            Objects.requireNonNull(applicationEventPublisher);
    }

    public void publishOrderCreated(String orderId) {
        if (eventPublisher == null) {
            throw new IllegalStateException(
                "ApplicationEventPublisher has not been initialized"
            );
        }

        eventPublisher.publishEvent(new OrderCreated(orderId));
    }

    public record OrderCreated(String orderId) {
        public OrderCreated {
            Objects.requireNonNull(orderId, "orderId");
        }
    }
}
~~~

Một số điểm trong ví dụ:

- Lớp triển khai interface phải khai báo đúng chữ ký setApplicationEventPublisher(ApplicationEventPublisher).
- Dùng @Override để compiler kiểm tra phương thức có khớp với interface.
- Field giữ publisher thường là private để chỉ bean sử dụng nó.
- Kiểm tra null giúp phát hiện trường hợp bean chưa được container cấp publisher, đặc biệt khi object bị tạo ngoài Spring.
- Phương thức nghiệp vụ gọi publishEvent(...) để phát một event có kiểu rõ ràng.

Không cần gọi setApplicationEventPublisher(...) từ code ứng dụng khi bean được quản lý đúng bởi ApplicationContext. Đây là callback do container thực hiện.

## 4. Đăng ký bean và sử dụng publisher

Bean triển khai ApplicationEventPublisherAware phải được đăng ký trong ApplicationContext, chẳng hạn bằng @Component, @Bean hoặc cấu hình component scan. Sau khi context khởi tạo bean, publisher đã được gán và phương thức nghiệp vụ có thể sử dụng.

Ví dụ cấu hình Java:

~~~java
@Configuration
public class EventConfiguration {
    @Bean
    public OrderEventPublisher orderEventPublisher() {
        return new OrderEventPublisher();
    }
}
~~~

Sau khi context refresh hoàn tất, có thể lấy bean và gọi:

~~~java
OrderEventPublisher publisher =
    applicationContext.getBean(OrderEventPublisher.class);

publisher.publishOrderCreated("ORD-1001");
~~~

Spring phân phối event tới các listener tương ứng trong context. Bean phát sự kiện không cần gọi trực tiếp listener, cũng không cần biết có bao nhiêu listener đang đăng ký.

Nếu bean được khai báo bằng @Component, hãy bảo đảm package của nó nằm trong phạm vi component scan. Nếu khai báo bằng @Bean, phương thức factory phải thuộc cấu hình được nạp vào context. Chỉ thêm implements ApplicationEventPublisherAware vào một class không đủ để Spring biết và quản lý class đó.

## 5. Kết hợp với @EventListener

Một listener có thể nhận event bằng phương thức gắn @EventListener:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    @EventListener
    public void handle(OrderEventPublisher.OrderCreated event) {
        System.out.println("Created: " + event.orderId());
    }
}
~~~

Khi OrderEventPublisher gọi publishEvent(new OrderCreated(...)), Spring tìm listener có tham số tương thích với kiểu event. Trong ví dụ, listener nhận trực tiếp record OrderCreated.

Bean listener cũng phải được đăng ký trong cùng ApplicationContext hoặc trong một context có quan hệ phân cấp phù hợp. Nếu listener không được gọi, hãy kiểm tra bean registration, component scan, kiểu tham số và context nơi publisher được cấp.

ApplicationEventPublisherAware chỉ giải quyết việc nhận publisher. Nó không tự đăng ký listener và không thay đổi cách Spring chọn listener. Việc lắng nghe vẫn dựa trên @EventListener, ApplicationListener hoặc cơ chế đăng ký listener tương ứng.

## 6. ApplicationEventPublisherAware và constructor injection

Có hai cách phổ biến để bean nhận ApplicationEventPublisher:

| Tiêu chí | ApplicationEventPublisherAware | Constructor injection |
|---|---|---|
| Cơ chế | Spring gọi lifecycle callback | Spring truyền dependency vào constructor |
| Thời điểm nhận | Trong quá trình khởi tạo bean | Khi tạo instance |
| Field | Thường được gán qua setter callback | Có thể khai báo final |
| Dependency | Thể hiện qua interface Aware | Hiển thị trực tiếp trong constructor |
| Kiểm thử đơn vị | Cần gọi callback hoặc chuẩn bị context | Truyền fake/mock ngay khi tạo object |
| Phù hợp | Infrastructure, tích hợp lifecycle, code tương thích Aware | Service và component nghiệp vụ thông thường |

Ví dụ constructor injection:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void createOrder(String orderId) {
        eventPublisher.publishEvent(new OrderCreated(orderId));
    }

    public record OrderCreated(String orderId) {
    }
}
~~~

Với code ứng dụng mới, constructor injection thường là lựa chọn dễ hiểu hơn: dependency được khai báo ngay trong constructor, field có thể final và object không thể được tạo ở trạng thái thiếu publisher thông qua constructor thông thường.

ApplicationEventPublisherAware hữu ích khi một thành phần được thiết kế quanh các callback Aware, khi cần tích hợp với infrastructure của Spring hoặc khi duy trì một abstraction bean đã dùng cơ chế callback. Không nên triển khai interface này chỉ để thay thế constructor injection trong mọi service, vì dependency publisher trở nên ít hiển thị hơn trong API constructor.

Hai cách đều nhận publisher do ApplicationContext cung cấp. Khác biệt nằm ở cách dependency được truyền và cách bean thể hiện vòng đời của mình.

## 7. Kiểm thử bean triển khai Aware

Khi kiểm thử bằng ApplicationContext thật, hãy đăng ký bean và để Spring gọi callback như trong môi trường chạy thực tế. Đây là cách phù hợp để kiểm tra cả việc cấp publisher lẫn việc event được listener nhận.

Với unit test không khởi tạo Spring, có thể truyền một publisher giả bằng cách gọi callback trực tiếp. Ví dụ:

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;

import java.util.ArrayList;
import java.util.List;

public class OrderEventPublisherTest {
    public static void main(String[] args) {
        List<Object> publishedEvents = new ArrayList<>();

        ApplicationEventPublisher fakePublisher =
            event -> publishedEvents.add(event);

        OrderEventPublisher publisher = new OrderEventPublisher();
        publisher.setApplicationEventPublisher(fakePublisher);
        publisher.publishOrderCreated("ORD-TEST");

        if (publishedEvents.size() != 1) {
            throw new AssertionError("Expected exactly one event");
        }

        OrderEventPublisher.OrderCreated event =
            (OrderEventPublisher.OrderCreated) publishedEvents.get(0);

        if (!"ORD-TEST".equals(event.orderId())) {
            throw new AssertionError("Unexpected order id");
        }

        System.out.println("PASS: one OrderCreated event was published");
    }
}
~~~

Publisher giả trong ví dụ lưu event vào list để test kiểm tra số lượng và payload. Trong dự án dùng JUnit hoặc Mockito, có thể thay bằng assertion và verify tương ứng.

Unit test gọi callback trực tiếp kiểm tra logic của bean sau khi được cấp publisher; nó không kiểm tra ApplicationContextAwareProcessor có tự động gọi callback hay không. Muốn kiểm tra lifecycle thực tế, hãy bổ sung một kiểm thử tích hợp tạo context và lấy bean từ context.

## 8. Ví dụ hoàn chỉnh có thể chạy

Ví dụ dùng Java 17 và Spring Framework 6.2.0. OrderEventPublisher triển khai ApplicationEventPublisherAware, nhận publisher khi ApplicationContext khởi tạo bean, rồi phát một record. Listener nhận event bằng @EventListener.

Tạo file src/main/java/demo/AwarePublisherDemo.java:

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

import java.util.Objects;

public class AwarePublisherDemo {
    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderEventPublisher.class)
                .publishOrderCreated("ORD-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        OrderEventPublisher orderEventPublisher() {
            return new OrderEventPublisher();
        }

        @Bean
        OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }

    public record OrderCreated(String orderId) {
        public OrderCreated {
            Objects.requireNonNull(orderId, "orderId");
        }
    }

    static class OrderEventPublisher
            implements ApplicationEventPublisherAware {
        private ApplicationEventPublisher eventPublisher;

        @Override
        public void setApplicationEventPublisher(
                ApplicationEventPublisher applicationEventPublisher) {
            this.eventPublisher =
                Objects.requireNonNull(applicationEventPublisher);
        }

        public void publishOrderCreated(String orderId) {
            if (eventPublisher == null) {
                throw new IllegalStateException(
                    "ApplicationEventPublisher has not been initialized"
                );
            }
            eventPublisher.publishEvent(new OrderCreated(orderId));
        }
    }

    static class OrderCreatedListener {
        @EventListener
        public void handle(OrderCreated event) {
            System.out.println("Received event for " + event.orderId());
        }
    }
}
~~~

Tạo file pom.xml tại thư mục gốc:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>aware-publisher-demo</artifactId>
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
                    <mainClass>demo.AwarePublisherDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Stdout dự kiến:

~~~text
Received event for ORD-1001
~~~

Luồng chạy:

1. AnnotationConfigApplicationContext nạp AppConfig.
2. Spring tạo OrderEventPublisher và OrderCreatedListener.
3. Trong quá trình khởi tạo OrderEventPublisher, ApplicationContextAwareProcessor gọi setApplicationEventPublisher(...).
4. Publisher được gán vào field eventPublisher.
5. Sau khi context refresh hoàn tất, main lấy bean và gọi publishOrderCreated(...).
6. Bean gọi publishEvent(new OrderCreated(...)).
7. Listener nhận event đồng bộ và in mã đơn hàng.
8. try-with-resources đóng context.

## 9. Lỗi thường gặp và cách xử lý

- Callback không được gọi: kiểm tra object có được tạo và quản lý bởi ApplicationContext hay không. Object tạo bằng new không tự nhận callback.
- eventPublisher vẫn null: kiểm tra phương thức callback có được triển khai đúng chữ ký và bean có được quản lý bởi context hay không. Không gọi phương thức nghiệp vụ trước khi bean hoàn tất khởi tạo.
- Listener không nhận event: kiểm tra listener có phải bean, có thuộc context phù hợp và tham số @EventListener có tương thích với event hay không.
- Triển khai Aware nhưng vẫn inject ApplicationContext: nếu chỉ cần phát event, giữ ApplicationEventPublisher là đủ; không cần phụ thuộc vào API rộng hơn.
- Dùng callback để che giấu dependency: với service nghiệp vụ mới, constructor injection thường làm dependency rõ ràng hơn.
- Tạo event mutable rồi sửa sau khi phát: listener có thể quan sát dữ liệu đã thay đổi. Dùng record, final field và dữ liệu bất biến.
- Cho rằng event được lưu và phát lại: ApplicationEventPublisher không cung cấp persistence hoặc retry. Dùng message broker hoặc outbox khi cần bảo đảm giao nhận.
- Gọi callback nhiều lần trong code nghiệp vụ: đây là trách nhiệm lifecycle của container. Không dùng callback như một phương thức cấu hình thông thường.

## 10. Quy trình áp dụng

1. Xác định bean thực sự cần nhận ApplicationEventPublisher qua lifecycle callback.
2. Đảm bảo bean được đăng ký trong ApplicationContext.
3. Triển khai ApplicationEventPublisherAware và setApplicationEventPublisher(...) đúng chữ ký.
4. Lưu publisher trong field riêng và kiểm tra đầu vào.
5. Chỉ gọi publishEvent sau khi bean đã hoàn tất khởi tạo và nghiệp vụ đạt trạng thái cần thông báo.
6. Đăng ký listener bằng @EventListener hoặc ApplicationListener.
7. Kiểm thử cả callback trong ApplicationContext thật và logic phát event bằng publisher giả.

ApplicationEventPublisherAware là cầu nối giữa lifecycle của bean và cơ chế phát sự kiện của Spring. Khi dùng đúng nơi, interface này giúp một thành phần nhận publisher từ context mà không cần tự tìm listener. Với service thông thường, constructor injection vẫn là lựa chọn rõ ràng hơn vì dependency được thể hiện ngay khi tạo object.