# Listener trong cấu hình XML hoặc legacy

Spring Framework hỗ trợ đăng ký application event listener bằng nhiều cách. Trong các ứng dụng XML truyền thống hoặc code Spring đời cũ, cách phổ biến là khai báo một bean triển khai **ApplicationListener<E>** trong file cấu hình XML. ApplicationContext tự phát hiện bean này và đăng ký nó với hệ thống phân phối event.

Cách làm này vẫn hoạt động trong các ứng dụng Spring hiện đại. Điểm cốt lõi là listener phải thuộc phạm vi quản lý của ApplicationContext, event phải có kiểu tương thích với listener và publisher phải gửi event tới đúng context.

## 1. Listener kiểu legacy là gì?

Trước khi có annotation @EventListener, cách tiêu chuẩn để lắng nghe application event trong Spring là triển khai interface **ApplicationListener<E>**:

~~~java
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {

    void onApplicationEvent(E event);
}
~~~

Generic E phải là ApplicationEvent hoặc một lớp con. Spring gọi onApplicationEvent(event) khi có event tương thích được publish trong context.

Ví dụ:

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Received order: " + event.getOrderId());
    }
}
~~~

Cách này thường được gọi là listener kiểu interface hoặc listener legacy vì nó đã tồn tại từ các phiên bản Spring cũ, trước khi @EventListener được giới thiệu. Interface vẫn được hỗ trợ và phù hợp khi cần một class thể hiện rõ hợp đồng nhận event.

Với Java có generic, nên khai báo kiểu cụ thể như ApplicationListener<OrderCreatedEvent>. Code cũ có thể gặp raw type ApplicationListener, nhưng raw type làm mất thông tin kiểu và khiến việc lọc event kém rõ ràng. Khi bảo trì, hãy chuyển dần sang generic cụ thể nếu tương thích với API đang dùng.

## 2. Đăng ký ApplicationListener bằng XML

Nếu ứng dụng dùng XML bean configuration, hãy khai báo listener như một bean bình thường. Spring ApplicationContext tự phát hiện các bean triển khai ApplicationListener trong quá trình refresh và đăng ký chúng với ApplicationEventMulticaster.

Ví dụ applicationContext.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderCreatedListener"
          class="demo.OrderCreatedListener"/>

    <bean id="orderService"
          class="demo.OrderService"/>
</beans>
~~~

Hai bean được khai báo trực tiếp bằng tên class. Không cần một thẻ listener riêng cho ApplicationListener. Trong lúc context khởi tạo, Spring nhận ra bean nào triển khai interface và đăng ký bean đó làm listener.

XML cũng có thể cấu hình dependency, constructor argument, property, scope hoặc alias như với bean khác. Ví dụ listener cần repository thì khai báo repository và inject bằng constructor hoặc property theo cách cấu hình hiện có.

### Vòng đời đăng ký

Luồng xử lý thường diễn ra như sau:

1. GenericXmlApplicationContext đọc file XML và tạo bean definitions.
2. Context khởi tạo các bean và các infrastructure processor cần thiết.
3. Spring phát hiện bean triển khai ApplicationListener và đăng ký listener với context.
4. Khi context được refresh hoàn tất, các listener đã đăng ký sẵn sàng nhận event.
5. Publisher gọi publishEvent(event); ApplicationEventMulticaster chọn listener tương thích và gọi onApplicationEvent(event).

Vì vậy, listener được khai báo trong XML vẫn tham gia cùng event bus nội bộ với listener khai báo bằng @Component hoặc @Bean. Cách đăng ký bean khác nhau, còn cơ chế dispatch vẫn do ApplicationContext và multicaster quản lý.

## 3. Tạo event theo kiểu legacy

ApplicationListener<E> nhận một kiểu kế thừa ApplicationEvent. Một event tùy chỉnh có thể chứa dữ liệu cần cho listener:

~~~java
import org.springframework.context.ApplicationEvent;

public class OrderCreatedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Source là đối tượng phát sinh event. Trong ví dụ, đó có thể là OrderService. Field orderId chứa dữ liệu nghiệp vụ mà listener cần.

Event nên mô tả một điều đã xảy ra, ví dụ OrderCreatedEvent hoặc PaymentCompletedEvent. Dùng tên thể hiện sự kiện trong quá khứ giúp listener hiểu ý nghĩa của thông báo. Nên giữ dữ liệu event ổn định sau khi publish; với payload có collection hoặc object mutable, hãy cân nhắc defensive copy và thiết kế immutable.

### Phân biệt ApplicationEvent và POJO payload

Từ Spring Framework 4.2, ApplicationEventPublisher cũng hỗ trợ publish một POJO hoặc record thông thường. Spring bọc payload trong PayloadApplicationEvent. Tuy nhiên, ApplicationListener<E> vẫn có ràng buộc E extends ApplicationEvent.

Nếu muốn tiếp tục dùng interface cho payload POJO, listener có thể nhận wrapper:

~~~java
public class OrderPayloadListener
        implements ApplicationListener<PayloadApplicationEvent<OrderCreated>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderCreated> event) {
        OrderCreated payload = event.getPayload();
        System.out.println(payload.orderId());
    }
}
~~~

Nếu muốn method nhận trực tiếp OrderCreated, @EventListener thường ngắn hơn. Khi duy trì code legacy dùng ApplicationListener<OrderCreatedEvent>, cách an toàn và quen thuộc nhất vẫn là event class kế thừa ApplicationEvent.

## 4. Publish event từ bean legacy

Bean XML có thể phát event bằng cách nhận ApplicationEventPublisher. Với bean truyền thống không dùng constructor injection hoặc không có cách inject publisher qua cấu hình, interface **ApplicationEventPublisherAware** là một lựa chọn tương thích.

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;

public class OrderService implements ApplicationEventPublisherAware {

    private ApplicationEventPublisher publisher;

    @Override
    public void setApplicationEventPublisher(
            ApplicationEventPublisher eventPublisher) {
        this.publisher = eventPublisher;
    }

    public void createOrder(String orderId) {
        publisher.publishEvent(new OrderCreatedEvent(this, orderId));
    }
}
~~~

Khi Spring tạo bean, cơ chế aware callback cung cấp publisher gắn với ApplicationContext quản lý bean. Sau đó service có thể gọi publishEvent mà không cần biết listener cụ thể nào sẽ nhận event.

Một cách cũ khác là implement ApplicationContextAware rồi gọi applicationContext.publishEvent(...). Tuy nhiên, nếu bean chỉ cần công bố event, ApplicationEventPublisherAware diễn đạt dependency hẹp và rõ hơn. Chỉ dùng ApplicationContextAware khi bean thật sự cần các API khác của context.

Với code mới, constructor injection thường dễ kiểm thử hơn:

~~~java
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

Có thể dùng constructor injection trong XML bằng constructor argument nếu publisher được cung cấp rõ ràng qua cấu hình. ApplicationEventPublisherAware hữu ích khi tương thích với cấu trúc bean legacy đã có.

## 5. XML bean kết hợp với annotation listener

Một ứng dụng có thể khai báo bean bằng XML nhưng vẫn muốn dùng @EventListener trên phương thức. Khi đó cần bật annotation processing bằng namespace context:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean id="orderListener"
          class="demo.OrderAnnotationListener"/>
</beans>
~~~

Class có thể khai báo:

~~~java
public class OrderAnnotationListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Received: " + event.getOrderId());
    }
}
~~~

<context:annotation-config/> đăng ký các annotation post-processors cần thiết cho cấu hình annotation trong những bean đã được khai báo. Nó không tự quét package để tìm bean. Nếu muốn component scan, dùng context:component-scan với base-package phù hợp.

Phân biệt hai việc:

- Khai báo bean trong XML làm cho object thuộc ApplicationContext.
- Annotation processing phát hiện và đăng ký phương thức @EventListener trên bean đó.

Nếu bean đã triển khai ApplicationListener, context có thể đăng ký theo interface mà không cần context:annotation-config chỉ vì listener dùng interface.

## 6. Cấu hình event multicaster trong XML

Mỗi ApplicationContext có ApplicationEventMulticaster để phân phối event. Nếu không khai báo bean tùy chỉnh, Spring sử dụng SimpleApplicationEventMulticaster mặc định.

Có thể khai báo bean với tên quy ước applicationEventMulticaster để tùy chỉnh cách dispatch:

~~~xml
<bean id="applicationEventMulticaster"
      class="org.springframework.context.event.SimpleApplicationEventMulticaster"/>
~~~

Khi cần xử lý bất đồng bộ, có thể cung cấp executor cho multicaster. Ví dụ dưới đây minh họa cách nối một ThreadPoolTaskExecutor:

~~~xml
<bean id="applicationEventExecutor"
      class="org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor">
    <property name="corePoolSize" value="2"/>
    <property name="maxPoolSize" value="4"/>
    <property name="queueCapacity" value="100"/>
    <property name="threadNamePrefix" value="app-event-"/>
</bean>

<bean id="applicationEventMulticaster"
      class="org.springframework.context.event.SimpleApplicationEventMulticaster">
    <property name="taskExecutor" ref="applicationEventExecutor"/>
</bean>
~~~

Đây là cấu hình tùy chọn. Với dispatch mặc định, listener chạy đồng bộ trên thread publish event. Khi dùng executor, listener có thể chạy trên thread khác; publisher không nhất thiết chờ listener hoàn tất. Cần xem xét thread safety, thứ tự hoàn tất và xử lý ngoại lệ. Không nên bật async chỉ vì event được gọi là event bus.

Nếu cần error handler, có thể cấu hình thuộc tính errorHandler của SimpleApplicationEventMulticaster bằng một bean triển khai ErrorHandler. Hãy xác định rõ chính sách logging, retry hoặc bỏ qua lỗi; event multicaster nội bộ không tự cung cấp cơ chế lưu bền vững và retry như message broker.

## 7. Ví dụ hoàn chỉnh với XML và Java 17

Ví dụ sau sử dụng XML để đăng ký OrderService và OrderCreatedListener. OrderService lấy publisher qua ApplicationEventPublisherAware, tạo một event kế thừa ApplicationEvent và publish. Listener triển khai ApplicationListener<OrderCreatedEvent>.

### Cấu trúc thư mục

~~~text
legacy-xml-event-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LegacyXmlEventDemo.java
        └── resources/
            └── applicationContext.xml
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>legacy-xml-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.0</spring.version>
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
                <configuration>
                    <release>17</release>
                </configuration>
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

### applicationContext.xml

Đặt file tại src/main/resources/applicationContext.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderService"
          class="demo.LegacyXmlEventDemo$OrderService"/>

    <bean id="orderCreatedListener"
          class="demo.LegacyXmlEventDemo$OrderCreatedListener"/>
</beans>
~~~

XML khai báo hai bean. OrderCreatedListener tự được ApplicationContext nhận diện vì class triển khai ApplicationListener. Không cần khai báo thêm một listener registry riêng.

### LegacyXmlEventDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationEventPublisherAware;
import org.springframework.context.ApplicationListener;
import org.springframework.context.support.GenericXmlApplicationContext;

public class LegacyXmlEventDemo {

    public static void main(String[] args) {
        try (var context = new GenericXmlApplicationContext(
                "classpath:applicationContext.xml")) {

            OrderService service =
                    context.getBean("orderService", OrderService.class);

            service.createOrder("ORD-2001");
        }
    }

    public static class OrderCreatedEvent extends ApplicationEvent {

        private final String orderId;

        public OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static class OrderService
            implements ApplicationEventPublisherAware {

        private ApplicationEventPublisher publisher;

        @Override
        public void setApplicationEventPublisher(
                ApplicationEventPublisher eventPublisher) {
            this.publisher = eventPublisher;
        }

        public void createOrder(String orderId) {
            System.out.println("Created order: " + orderId);
            publisher.publishEvent(
                    new OrderCreatedEvent(this, orderId));
        }
    }

    public static class OrderCreatedListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println(
                    "Received OrderCreatedEvent: " + event.getOrderId());
        }
    }
}
~~~

### Biên dịch và chạy

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.LegacyXmlEventDemo
~~~

Kết quả stdout:

~~~text
Created order: ORD-2001
Received OrderCreatedEvent: ORD-2001
~~~

Giải thích:

1. GenericXmlApplicationContext đọc applicationContext.xml và tạo hai bean.
2. Khi tạo OrderService, Spring gọi setApplicationEventPublisher và cung cấp publisher của context.
3. Context nhận diện OrderCreatedListener vì bean triển khai ApplicationListener<OrderCreatedEvent>.
4. main lấy OrderService và gọi createOrder.
5. Service publish OrderCreatedEvent.
6. SimpleApplicationEventMulticaster mặc định phân phối event đồng bộ tới OrderCreatedListener.
7. Listener nhận kiểu OrderCreatedEvent trực tiếp và in mã đơn hàng.

Các class lồng nhau được khai báo static để XML có thể tham chiếu bằng tên nhị phân với dấu $. Trong dự án thực tế, thường đặt event, service và listener thành các class riêng để cấu trúc package rõ ràng hơn.

## 8. Thứ tự listener, lỗi và transaction

### Thứ tự thực thi

Nếu nhiều ApplicationListener cùng nhận một event, có thể dùng Ordered hoặc @Order để xác định thứ tự ưu tiên. Giá trị order nhỏ hơn có độ ưu tiên cao hơn trong dispatch có sắp xếp.

~~~java
@Order(1)
public class AuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Ghi audit.
    }
}
~~~

Chỉ dùng thứ tự khi nghiệp vụ thực sự phụ thuộc vào nó. Nếu listener độc lập, không nên tạo phụ thuộc vào thứ tự gọi tình cờ.

### Ngoại lệ và async

Với SimpleApplicationEventMulticaster mặc định, listener chạy đồng bộ. Ngoại lệ từ listener có thể truyền ngược về lời gọi publishEvent nếu không có ErrorHandler xử lý. Listener chậm cũng làm tăng thời gian của luồng publisher.

Khi cấu hình executor, listener có thể chạy bất đồng bộ. Publisher có thể tiếp tục trước khi listener hoàn tất; thứ tự hoàn tất không còn được bảo đảm giống dispatch đồng bộ. Cần logging và xử lý lỗi riêng cho tác vụ async.

### Transaction-aware listener

ApplicationListener thông thường không tự gắn callback với transaction phase. Nếu chỉ muốn xử lý sau khi transaction commit, dùng @TransactionalEventListener với phase AFTER_COMMIT khi phù hợp. Cách này có thể dùng trên bean XML nếu annotation processing đã được bật. Cần có transaction đang hoạt động tại thời điểm publish để listener được gắn với transaction đó.

Application event là cơ chế nội bộ trong process. Nếu yêu cầu retry, replay, lưu bền vững hoặc giao tiếp giữa service, hãy dùng message broker và thiết kế lưu trữ phù hợp thay vì coi XML listener là một hàng đợi bền vững.

## 9. Khi nào nên giữ XML hoặc chuyển sang annotation?

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Ứng dụng hiện có cấu hình XML ổn định | Tiếp tục khai báo listener bean trong XML |
| Cần tương thích với class listener interface cũ | Giữ ApplicationListener<E> |
| Muốn xử lý event bằng phương thức và nhận POJO trực tiếp | Dùng @EventListener |
| Bean đã khai báo bằng XML nhưng muốn dùng @EventListener | Bật context:annotation-config |
| Muốn phát event từ bean legacy | Dùng ApplicationEventPublisherAware |
| Code mới có thể thiết kế dependency rõ ràng | Ưu tiên constructor injection với ApplicationEventPublisher |
| Cần xử lý event sau transaction commit | Dùng @TransactionalEventListener với transaction phù hợp |

Không cần chuyển toàn bộ cấu hình XML sang annotation chỉ để dùng application event. Các bean XML, listener interface và listener annotation có thể cùng tồn tại trong một context nếu cấu hình annotation processing đúng.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Listener không được gọi | Class chưa được khai báo thành bean trong context | Thêm bean definition hoặc component scan |
| XML bean triển khai interface nhưng không nhận event | Bean thuộc context khác với context publish hoặc event type không tương thích | Kiểm tra context quản lý bean và kiểu event |
| Dùng raw ApplicationListener | Mất thông tin generic và khó lọc event | Dùng ApplicationListener<OrderCreatedEvent> |
| Dùng POJO làm generic E | E phải kế thừa ApplicationEvent | Dùng PayloadApplicationEvent<Payload> hoặc @EventListener |
| @EventListener trên XML bean không hoạt động | Chưa bật annotation processing | Thêm context:annotation-config hoặc component scan |
| Gọi publisher trước khi context sẵn sàng | Listener có thể chưa đăng ký đầy đủ | Publish từ luồng nghiệp vụ sau khi context refresh |
| Dùng ApplicationContextAware chỉ để publish | Dependency rộng hơn nhu cầu | Dùng ApplicationEventPublisherAware |
| Nghĩ listener mặc định chạy nền | SimpleApplicationEventMulticaster mặc định đồng bộ | Cấu hình executor khi có lý do |
| Dùng application event như broker | Không có persistence/retry liên process mặc định | Dùng broker phù hợp |

## 11. Checklist khi bảo trì ứng dụng XML/legacy

- Xác định file XML nào tạo ApplicationContext đang quản lý publisher và listener.
- Kiểm tra listener được khai báo thành bean và triển khai ApplicationListener với kiểu cụ thể.
- Xác định event kế thừa ApplicationEvent và chứa dữ liệu cần thiết.
- Dùng ApplicationEventPublisherAware nếu bean legacy cần lấy publisher từ context.
- Tránh publish event trong constructor hoặc trước khi context refresh hoàn tất.
- Nếu dùng @EventListener trên XML bean, bật annotation processing.
- Kiểm tra multicaster có được tùy chỉnh executor hoặc error handler hay không.
- Kiểm thử event được publish đúng context và listener nhận đúng kiểu.
- Giữ nguyên cấu hình XML cũ nếu nó vẫn đáp ứng yêu cầu; chuyển sang annotation theo từng phần khi có lợi ích rõ ràng.

**ApplicationListener<E> trong XML/legacy vẫn là một cách đăng ký listener được Spring hỗ trợ.** Chỉ cần khai báo listener thành bean trong ApplicationContext, dùng event type tương thích và publish qua context, cơ chế multicaster sẽ phân phối event như với các listener đăng ký bằng annotation hoặc Java configuration.