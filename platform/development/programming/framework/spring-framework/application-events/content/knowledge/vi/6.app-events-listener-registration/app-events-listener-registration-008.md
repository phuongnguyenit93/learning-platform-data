# Listener trong cấu hình Java

## Mục tiêu

Sau bài này, bạn có thể đăng ký Application Listener bằng Java configuration, phân biệt listener bean triển khai ApplicationListener với phương thức dùng @EventListener, hiểu thời điểm Spring phát hiện và đăng ký listener, thêm listener bằng code khi cần, và lựa chọn cách cấu hình phù hợp cho từng tình huống.

## 1. Listener được cấu hình ở đâu trong Spring?

Spring Application Events cho phép publisher thông báo một sự việc và các listener phản ứng với sự việc đó. Để Spring có thể gọi listener, listener phải được đăng ký với ApplicationContext hoặc ApplicationEventMulticaster.

Trong ứng dụng dùng Java configuration, có ba cách phổ biến:

1. Khai báo một bean triển khai ApplicationListener bằng @Bean.
2. Khai báo phương thức @EventListener bên trong một bean được Spring quản lý, bao gồm cả lớp @Configuration.
3. Đăng ký listener trực tiếp bằng API của ConfigurableApplicationContext khi cần điều khiển thời điểm đăng ký bằng code.

Ba cách đều dùng cùng hạ tầng phân phối event của Spring. Khác biệt nằm ở cách định nghĩa listener, cách Spring phát hiện nó và thời điểm listener được đưa vào context.

Java configuration giúp khai báo listener ngay trong mã nguồn cấu hình, dễ tìm kiếm và kiểm tra dependency. Listener vẫn là một đối tượng do Spring quản lý; việc đặt khai báo trong lớp cấu hình không biến listener thành một cơ chế event riêng.

## 2. Cách 1: Khai báo ApplicationListener bằng @Bean

ApplicationListener là interface nhận một kiểu event cụ thể. Khi bean triển khai interface này được đăng ký trong ApplicationContext, Spring phát hiện và thêm nó vào danh sách listener.

Ví dụ, ứng dụng phát payload OrderPlaced. Vì OrderPlaced là record thông thường, Spring bọc payload trong PayloadApplicationEvent<OrderPlaced>. Listener triển khai ApplicationListener<PayloadApplicationEvent<OrderPlaced>> để nhận wrapper và đọc payload:

~~~java
@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @Bean
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }
}

@Order(1)
class OrderAuditListener
        implements ApplicationListener<PayloadApplicationEvent<OrderPlaced>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderPlaced> event) {

        OrderPlaced order = event.getPayload();

        System.out.println("Audit: " + order.orderId());
    }
}
~~~

Trong ví dụ:

- @Configuration đánh dấu lớp khai báo cấu hình.
- @Bean đăng ký một instance OrderAuditListener vào ApplicationContext.
- OrderAuditListener triển khai ApplicationListener với kiểu generic xác định rõ loại event wrapper.
- onApplicationEvent là điểm Spring gọi khi có event tương thích.
- @Order(1) xác định thứ tự tương đối của listener khi nhiều listener cùng nhận một event.

Nếu publisher phát một lớp kế thừa ApplicationEvent, listener có thể khai báo trực tiếp lớp event đó:

~~~java
@Bean
ApplicationListener<OrderPlacedEvent> orderPlacedListener() {
    return event -> System.out.println(event.getOrderId());
}
~~~

Ở đây OrderPlacedEvent phải kế thừa ApplicationEvent. ApplicationListener không nhận một POJO tùy ý làm generic event type; với payload thông thường, dùng PayloadApplicationEvent<T> hoặc @EventListener nhận trực tiếp payload.

### Giữ nguyên generic type trong khai báo @Bean

Nên khai báo kiểu trả về cụ thể, ví dụ:

~~~java
@Bean
ApplicationListener<PayloadApplicationEvent<OrderPlaced>> orderAuditListener() {
    return event -> System.out.println(event.getPayload().orderId());
}
~~~

Không nên khai báo kiểu trả về raw ApplicationListener hoặc ApplicationListener<?> nếu Spring cần suy luận chính xác event type từ generic signature. Kiểu generic cụ thể giúp Spring lọc event đúng hơn và giúp compiler kiểm tra kiểu ở thời điểm biên dịch.

Nếu cần dùng một class listener riêng, có thể khai báo class đó và trả về từ @Bean. Nếu logic ngắn, lambda cũng là lựa chọn phù hợp.

## 3. Cách 2: Dùng @EventListener trong bean cấu hình Java

@EventListener đánh dấu một phương thức là listener. Phương thức có thể nằm trong bất kỳ bean nào được Spring quản lý, bao gồm:

- Lớp @Component.
- Lớp @Service.
- Lớp @Configuration.
- Một object được tạo và đăng ký bằng phương thức @Bean.

Ví dụ, khai báo listener ngay trong lớp cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @EventListener
    @Order(1)
    void auditOrder(OrderPlaced order) {
        System.out.println("Audit: " + order.orderId());
    }

    @EventListener
    @Order(2)
    void sendConfirmation(OrderPlaced order) {
        System.out.println("Confirmation: " + order.orderId());
    }
}
~~~

Lớp EventConfiguration bản thân nó là một bean trong ApplicationContext. EventListenerMethodProcessor phát hiện các phương thức @EventListener trên bean này và đăng ký adapter tương ứng với ApplicationEventMulticaster.

Kiểu tham số của phương thức là event type mà listener muốn nhận. Với payload object, có thể nhận trực tiếp OrderPlaced. Nếu muốn đọc wrapper, khai báo PayloadApplicationEvent<OrderPlaced>:

~~~java
@EventListener
void inspectEnvelope(PayloadApplicationEvent<OrderPlaced> event) {
    System.out.println(event.getSource());
    System.out.println(event.getPayload().orderId());
}
~~~

Không cần tạo thêm một ApplicationListener class chỉ để nhận một payload đơn giản.

### Đặt listener trong bean được tạo bằng @Bean

Listener method không bắt buộc nằm trong chính lớp @Configuration. Có thể tách trách nhiệm thành class riêng rồi khai báo bean:

~~~java
@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @Bean
    OrderNotificationListener orderNotificationListener() {
        return new OrderNotificationListener();
    }
}

class OrderNotificationListener {

    @EventListener
    void notifyCustomer(OrderPlaced order) {
        System.out.println("Notify: " + order.orderId());
    }
}
~~~

Khi Spring tạo bean OrderNotificationListener, EventListenerMethodProcessor phát hiện phương thức có @EventListener và đăng ký nó. Cách này phù hợp khi listener có nhiều logic hoặc cần inject dependency riêng.

## 4. Spring phát hiện và đăng ký listener khi nào?

Cần hiểu lifecycle để tránh trường hợp đã viết listener nhưng Spring không gọi.

### ApplicationListener bean

Khi bean triển khai ApplicationListener được tạo và đăng ký trong context, Spring nhận diện nó và thêm vào cơ chế phân phối event. Annotation-based context như AnnotationConfigApplicationContext đã cài đặt hạ tầng cần thiết cho việc phát hiện listener bean.

### Phương thức @EventListener

Spring đăng ký phương thức @EventListener thông qua EventListenerMethodProcessor. Processor này tìm các bean và kiểm tra những phương thức được đánh dấu @EventListener, sau đó tạo ApplicationListener adapter để kết nối phương thức với multicaster.

Do đó, các điều kiện quan trọng là:

- Lớp chứa phương thức listener phải là bean của ApplicationContext.
- Phương thức phải được phát hiện bởi cơ chế xử lý annotation.
- Bean và processor phải được đăng ký trong context đang phát event.
- Listener phải được đăng ký trước khi event cần xử lý được publish.

Một đối tượng được tạo bằng toán tử new bên ngoài Spring không tự trở thành listener. Nếu tự tạo object, phải đăng ký nó bằng API tương ứng hoặc đưa object vào context dưới dạng bean.

### Vì sao listener trong lớp @Configuration hoạt động?

@Configuration là một dạng component được đăng ký thành bean. Vì vậy, các phương thức @EventListener trong lớp cấu hình cũng được EventListenerMethodProcessor phát hiện như phương thức trên các bean khác.

Đây là cách viết hợp lệ cho cấu hình nhỏ. Với ứng dụng lớn, có thể tách listener ra class riêng để lớp cấu hình chỉ giữ trách nhiệm khai báo bean và dependency.

## 5. Cách 3: Đăng ký listener trực tiếp bằng code

Khi cần đăng ký listener trước khi ApplicationContext refresh, hoặc cần lựa chọn listener dựa trên cấu hình runtime, có thể dùng ConfigurableApplicationContext.addApplicationListener(...).

Ví dụ:

~~~java
public class ProgrammaticListenerDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {

            ApplicationListener<PayloadApplicationEvent<OrderPlaced>> listener =
                    event -> System.out.println(
                            "Programmatic: "
                                    + event.getPayload().orderId());

            context.addApplicationListener(listener);
            context.register(EventConfiguration.class);
            context.refresh();

            context.publishEvent(
                    new OrderPlaced("DH-7201", new BigDecimal("72000")));
        }
    }
}
~~~

Ở đây:

1. Tạo context ở trạng thái chưa refresh.
2. Tạo ApplicationListener bằng code.
3. Gọi addApplicationListener để đăng ký listener.
4. Đăng ký lớp cấu hình và gọi refresh.
5. Publish event sau khi context đã khởi tạo xong.

Ưu điểm của cách này là có thể đăng ký listener trước khi refresh, kể cả các event xuất hiện trong quá trình khởi động context. Nó cũng hữu ích khi một ứng dụng tích hợp plugin hoặc module tùy chọn và cần quyết định listener nào được đăng ký ở runtime.

Cần phân biệt addApplicationListener với việc thêm bean listener. Listener đăng ký trực tiếp được quản lý bởi context dưới dạng listener instance, nhưng không tự trở thành bean có đầy đủ dependency injection, lifecycle callback hoặc proxy như một bean thông thường. Nếu listener cần dependency, thường nên dùng bean do Spring quản lý.

Không nên đăng ký cùng một listener vừa bằng @Bean vừa bằng addApplicationListener nếu không muốn nó được gọi hai lần.

## 6. So sánh ba cách đăng ký

| Cách | Cách khai báo | Khi phù hợp |
|---|---|---|
| ApplicationListener bean | @Bean trả về ApplicationListener<E> | Listener có kiểu event rõ, logic độc lập hoặc cần interface |
| @EventListener | Phương thức trên bean Spring | Listener gọn, xử lý payload trực tiếp, dễ gom theo nghiệp vụ |
| addApplicationListener | Đăng ký instance bằng code | Cần đăng ký trước refresh hoặc lựa chọn listener lúc runtime |

Một số nguyên tắc chọn lựa:

- Ưu tiên @EventListener cho phần lớn listener nghiệp vụ cần nhận payload.
- Dùng ApplicationListener khi muốn biểu diễn listener như một bean/interface độc lập hoặc cần thao tác trực tiếp với event wrapper.
- Dùng addApplicationListener cho yêu cầu lifecycle/runtime đặc biệt.
- Không trộn nhiều cách chỉ để tạo thêm lớp trung gian không cần thiết.

## 7. Thứ tự xử lý listener trong Java configuration

Nhiều listener có thể cùng nhận một event. Spring hỗ trợ @Order hoặc Ordered để xác định thứ tự tương đối.

Với phương thức @EventListener, đặt @Order trên phương thức:

~~~java
@EventListener
@Order(1)
void writeAudit(OrderPlaced order) {
    System.out.println("Audit");
}

@EventListener
@Order(2)
void sendEmail(OrderPlaced order) {
    System.out.println("Email");
}
~~~

Với ApplicationListener bean, có thể đặt @Order trên class:

~~~java
@Order(1)
class OrderAuditListener
        implements ApplicationListener<PayloadApplicationEvent<OrderPlaced>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderPlaced> event) {
        System.out.println("Audit");
    }
}
~~~

Giá trị order nhỏ hơn được ưu tiên trước. Nếu không chỉ định order, listener dùng mức ưu tiên mặc định.

Chỉ dựa vào thứ tự listener khi đó là yêu cầu rõ ràng. Nếu listener gửi email chỉ được phép chạy sau khi một bước nghiệp vụ khác hoàn thành và cần kết quả của bước đó, hãy cân nhắc điều phối các bước trong service. @Order không tạo transaction chung và cũng không bảo đảm xử lý nguyên tử.

## 8. Điều kiện, nhiều event type và return value

Java configuration kết hợp được với các khả năng của @EventListener.

### Nhiều event type

Khi một thao tác không cần dữ liệu riêng của event, có thể khai báo nhiều kiểu bằng classes:

~~~java
@EventListener(classes = {
        ContextRefreshedEvent.class,
        ContextStartedEvent.class
})
void onContextLifecycle() {
    System.out.println("Context lifecycle event");
}
~~~

Khi khai báo nhiều kiểu trong classes, phương thức không nhận tham số event. Nếu cần đọc dữ liệu event, hãy khai báo listener riêng cho từng kiểu hoặc dùng kiểu cha chung phù hợp.

### Điều kiện SpEL

Có thể dùng condition để lọc event instance sau khi kiểu event đã phù hợp:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
void notifyWebOrder(OrderPlaced order) {
    System.out.println("Web order: " + order.orderId());
}
~~~

Điều kiện trên chỉ chạy listener khi payload có channel là WEB. Dùng #a0 giúp tham chiếu tham số đầu tiên mà không phụ thuộc vào tên tham số có được giữ trong bytecode hay không.

Condition nên ngắn và chỉ mô tả điều kiện nhận event. Logic nghiệp vụ chính nên nằm trong thân phương thức.

### Return value tạo event tiếp theo

Phương thức @EventListener có thể trả về một object khác void. Spring publish giá trị trả về như một event mới:

~~~java
@EventListener
OrderAudited audit(OrderPlaced order) {
    return new OrderAudited(order.orderId());
}
~~~

Cách này tiện cho chuỗi event ngắn. Nếu phương thức chạy bất đồng bộ bằng @Async, giá trị trả về không được dùng để publish event tiếp theo; khi đó cần inject ApplicationEventPublisher và publish tường minh.

## 9. Ví dụ hoàn chỉnh với Java 17 và Spring Framework

Ví dụ dùng đồng thời hai hình thức Java configuration: một ApplicationListener được khai báo bằng @Bean và một phương thức @EventListener trong lớp @Configuration. Cả hai nhận cùng payload OrderPlaced.

### Cấu trúc dự án

~~~text
java-configured-listeners/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JavaConfiguredListenerDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>java-configured-listeners</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.JavaConfiguredListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### JavaConfiguredListenerDemo.java

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class JavaConfiguredListenerDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(EventConfiguration.class)) {

            context.publishEvent(
                    new OrderPlaced("DH-7201", new BigDecimal("72000")));
        }
    }
}

record OrderPlaced(String orderId, BigDecimal total) {
}

@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @Bean
    OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }

    @EventListener
    @Order(2)
    void sendConfirmation(OrderPlaced order) {
        System.out.println("Confirmation: " + order.orderId());
    }
}

@Order(1)
class OrderAuditListener
        implements ApplicationListener<PayloadApplicationEvent<OrderPlaced>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderPlaced> event) {

        OrderPlaced order = event.getPayload();

        System.out.println(
                "Audit: " + order.orderId()
                        + ", total=" + order.total().toPlainString());
    }
}
~~~

### Chạy chương trình

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Kết quả:

~~~text
Audit: DH-7201, total=72000
Confirmation: DH-7201
~~~

### Phân tích luồng chạy

1. AnnotationConfigApplicationContext nhận EventConfiguration và khởi tạo context.
2. Phương thức @Bean tạo OrderAuditListener. Spring đăng ký bean này như một ApplicationListener.
3. EventListenerMethodProcessor phát hiện phương thức sendConfirmation được đánh dấu @EventListener trong EventConfiguration.
4. Khi publishEvent nhận OrderPlaced, Spring bọc payload thành PayloadApplicationEvent<OrderPlaced>.
5. ApplicationEventMulticaster chọn cả OrderAuditListener và phương thức sendConfirmation vì hai listener đều phù hợp với payload OrderPlaced.
6. @Order(1) khiến audit chạy trước; @Order(2) khiến confirmation chạy sau.
7. Context được đóng sau khi xử lý xong nhờ try-with-resources.

Điều quan trọng là cả hai listener đều được cấu hình bằng Java và được Spring tự đăng ký. Publisher không cần gọi trực tiếp các phương thức listener.

## 10. Lỗi thường gặp và cách xử lý

### Khai báo listener nhưng không đăng ký bean

Một class có triển khai ApplicationListener nhưng không được đưa vào ApplicationContext sẽ không được context tự động gọi. Hãy đăng ký qua @Bean, component scan hoặc API đăng ký listener.

### Đặt @EventListener trên object không do Spring quản lý

Annotation không tự đăng ký một object được tạo bằng new. Phương thức chỉ được phát hiện khi object là bean trong context và EventListenerMethodProcessor xử lý bean đó.

### Làm mất generic type của ApplicationListener

Khai báo raw ApplicationListener hoặc kiểu trả về quá rộng có thể khiến Spring không suy luận được event type cụ thể. Giữ generic type trong khai báo @Bean và class listener.

### Đăng ký trùng listener

Nếu cùng một instance được thêm bằng addApplicationListener và đồng thời được đăng ký như bean, nó có thể bị gọi lặp. Chọn một cơ chế đăng ký phù hợp cho mỗi listener.

### Đăng ký listener quá muộn

Nếu event đã được publish trước khi listener được đăng ký, listener không tự nhận lại event cũ. Application Events mặc định không lưu lịch sử để phát lại. Với listener cần nhận event trong quá trình refresh, cân nhắc đăng ký trước refresh bằng addApplicationListener.

### Đưa nghiệp vụ vào lớp cấu hình

Lớp @Configuration nên tập trung vào cấu hình bean. Nếu listener có logic phức tạp, cần dependency hoặc cần kiểm thử riêng, hãy tách thành class listener và khai báo bằng @Bean. Việc tách này giúp cấu hình dễ đọc và listener có trách nhiệm rõ ràng.

### Mong đợi listener tự chạy bất đồng bộ

Java configuration chỉ quyết định cách đăng ký listener. Nó không tự biến listener thành async. Muốn xử lý bất đồng bộ, phải cấu hình @Async/@EnableAsync hoặc task executor cho ApplicationEventMulticaster và thiết kế cách quan sát lỗi, thread context, thứ tự phù hợp.

## 11. Ghi nhớ

Trong Java configuration, có thể đăng ký listener bằng @Bean trả về ApplicationListener, khai báo phương thức @EventListener trong bean cấu hình, hoặc gọi addApplicationListener khi cần đăng ký bằng code.

ApplicationListener phù hợp khi muốn một listener bean có event type rõ ràng. @EventListener phù hợp với phương thức nghiệp vụ nhận trực tiếp payload. addApplicationListener hữu ích khi cần đăng ký trước refresh hoặc dựa trên điều kiện runtime. Cả ba cách đều kết nối với ApplicationEventMulticaster của Spring.

Để listener hoạt động đúng, bean phải được đăng ký trong đúng ApplicationContext, generic type cần được giữ rõ ràng, và listener phải tồn tại trước khi event liên quan được publish. Dùng @Order khi cần thứ tự rõ ràng; dùng service orchestration khi các bước có phụ thuộc nghiệp vụ bắt buộc.

## Tài liệu tham khảo chính thức

- [ApplicationListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationListener.html)
- [EventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [EventListenerMethodProcessor — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html)
- [ConfigurableApplicationContext — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [ApplicationEventMulticaster — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
