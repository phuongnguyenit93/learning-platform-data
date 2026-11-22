# Đăng ký listener qua ConfigurableApplicationContext

Spring cho phép đăng ký một §ApplicationListener§ trực tiếp vào ApplicationContext bằng phương thức §ConfigurableApplicationContext.addApplicationListener(...)§. Cách này hữu ích khi listener được tạo động trong lúc cấu hình ứng dụng, khi cần nghe event trước khi context refresh, hoặc khi muốn thêm và gỡ một listener theo vòng đời của một context cụ thể.

Đây là hình thức đăng ký listener bằng code. Bạn cung cấp một object triển khai §ApplicationListener§, sau đó truyền object đó cho context. Spring sẽ đưa listener vào cơ chế phân phối event của context.

## 1. ConfigurableApplicationContext là gì?

§ApplicationContext§ là interface trung tâm của Spring container. Nó cung cấp khả năng lấy bean, đọc resource, phân giải message và phát application event. §ConfigurableApplicationContext§ mở rộng khả năng cấu hình vòng đời của context, trong đó có các thao tác như:

- §refresh()§: khởi tạo hoặc refresh context.
- §close()§: đóng context và giải phóng tài nguyên.
- §addApplicationListener(...)§: đăng ký thêm listener.
- §removeApplicationListener(...)§: gỡ listener đã đăng ký bằng phương thức tương ứng.

Bạn không tạo trực tiếp một instance của interface này. Thay vào đó, sử dụng implementation như §AnnotationConfigApplicationContext§, §GenericApplicationContext§ hoặc §ClassPathXmlApplicationContext§.

Ví dụ khai báo biến theo interface:

~~~java
ConfigurableApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class);
~~~

Cách viết này giúp code phụ thuộc vào contract cấu hình chung của Spring thay vì một implementation cụ thể.

## 2. Phương thức addApplicationListener(...)

API trong Spring Framework 6.2 có chữ ký:

~~~java
void addApplicationListener(ApplicationListener<?> listener);
~~~

Tham số là một object triển khai §ApplicationListener§. Interface này có kiểu generic §E extends ApplicationEvent§, vì vậy listener có thể khai báo rõ loại event mà nó xử lý.

Ví dụ:

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Đơn hàng mới: " + event.getOrderId());
    }
}
~~~

Khi đăng ký listener:

~~~java
context.addApplicationListener(new OrderCreatedListener());
~~~

Spring thêm object listener vào danh sách listener của context. Khi một event tương thích được publish, listener sẽ nhận event đó qua §onApplicationEvent(...)§.

Generic type giúp Spring lọc event theo kiểu. Listener nhận §OrderCreatedEvent§ sẽ không bị gọi cho một event không liên quan như §ContextClosedEvent§. Nhờ đó method xử lý có kiểu cụ thể và không cần ép kiểu thủ công.

## 3. Đăng ký trước khi refresh context

Nếu context chưa active, listener được thêm bằng §addApplicationListener(...)§ sẽ được áp dụng khi context refresh. Đây là cách phù hợp khi muốn nghe các context lifecycle event phát sinh trong quá trình khởi tạo.

Ví dụ:

~~~java
var context = new AnnotationConfigApplicationContext();

context.addApplicationListener(
        new ApplicationListener<ContextRefreshedEvent>() {
            @Override
            public void onApplicationEvent(ContextRefreshedEvent event) {
                System.out.println("Context đã refresh: "
                        + event.getApplicationContext().getId());
            }
        });

context.register(AppConfig.class);
context.refresh();
~~~

Trong ví dụ này:

1. Tạo context bằng constructor không tham số. Context chưa được refresh.
2. Đăng ký listener cho §ContextRefreshedEvent§.
3. Đăng ký lớp cấu hình.
4. Gọi §refresh()§. Spring tạo bean và phát event báo context đã refresh.
5. Listener đã được đăng ký trước đó nên nhận event.

Việc đăng ký trước refresh quan trọng nếu listener cần nhận các event được phát trong quá trình khởi tạo. Nếu đăng ký sau khi refresh, listener sẽ không nhận lại các event đã phát trước thời điểm đăng ký.

## 4. Đăng ký sau khi context đã active

Bạn cũng có thể thêm listener vào một context đang hoạt động:

~~~java
try (var context =
             new AnnotationConfigApplicationContext(AppConfig.class)) {

    OrderCreatedListener listener = new OrderCreatedListener();

    context.addApplicationListener(listener);

    context.publishEvent(new OrderCreatedEvent(context, "ORD-200"));
}
~~~

Constructor §AnnotationConfigApplicationContext(AppConfig.class)§ đã đăng ký cấu hình và refresh context. Vì vậy, lời gọi §addApplicationListener(...)§ xảy ra sau refresh.

Theo hợp đồng của §ConfigurableApplicationContext§, listener được thêm khi context đã active sẽ được đưa vào event multicaster hiện tại ngay lúc đó. Các event publish sau khi đăng ký có thể được listener nhận nếu kiểu event phù hợp.

Hai thời điểm đăng ký có thể tóm tắt như sau:

| Thời điểm gọi | Spring xử lý đăng ký |
|---|---|
| Trước khi context active | Lưu listener để áp dụng khi refresh |
| Sau khi context active | Thêm listener vào event multicaster đang hoạt động |

Hãy chọn thời điểm dựa trên event bạn cần nhận. Listener cần bắt §ContextRefreshedEvent§ phải được đăng ký trước khi gọi §refresh()§.

## 5. Ví dụ hoàn chỉnh với Java 17+ và Spring Framework 6.2

Ví dụ sau tạo một listener bằng Java, đăng ký trực tiếp với §ConfigurableApplicationContext§, sau đó phát event khi tạo đơn hàng.

**Cấu trúc dự án**

~~~text
spring-context-listener/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ListenerRegistrationDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-context-listener</artifactId>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ListenerRegistrationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ListenerRegistrationDemo.java**

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ListenerRegistrationDemo {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            OrderCreatedListener listener = new OrderCreatedListener();

            // Đăng ký listener trước khi context refresh.
            context.addApplicationListener(listener);

            // Đăng ký cấu hình và khởi tạo context.
            context.register(AppConfig.class);
            context.refresh();

            // Lấy service đã được Spring tạo và phát event.
            context.getBean(OrderService.class).createOrder("ORD-100");

            // Có thể gỡ listener nếu không cần nhận event nữa.
            context.removeApplicationListener(listener);
        }
    }

    @Configuration
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    public static class OrderCreatedEvent extends ApplicationEvent {

        private static final long serialVersionUID = 1L;

        private final String orderId;

        public OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static class OrderCreatedListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println("Listener nhận đơn hàng: "
                    + event.getOrderId());
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void createOrder(String orderId) {
            System.out.println("Phát event tạo đơn: " + orderId);
            publisher.publishEvent(new OrderCreatedEvent(this, orderId));
        }
    }
}
~~~

**Chạy chương trình**

Từ thư mục chứa §pom.xml§, chạy:

~~~bash
mvn -q compile exec:java
~~~

Output:

~~~text
Phát event tạo đơn: ORD-100
Listener nhận đơn hàng: ORD-100
~~~

**Giải thích luồng chạy**

1. Chương trình tạo §AnnotationConfigApplicationContext§ nhưng chưa refresh.
2. Tạo object §OrderCreatedListener§ và gọi §context.addApplicationListener(listener)§.
3. Đăng ký §AppConfig§, sau đó gọi §context.refresh()§.
4. Spring khởi tạo §OrderService§ và inject §ApplicationEventPublisher§.
5. Chương trình gọi §createOrder("ORD-100")§.
6. Service publish §OrderCreatedEvent§.
7. Event multicaster chọn listener có kiểu §OrderCreatedEvent§ và gọi §onApplicationEvent(...)§.
8. Chương trình gỡ listener bằng chính object đã đăng ký, rồi đóng context khi thoát khối §try§.

Listener trong ví dụ là một object Java được đăng ký trực tiếp. Nó không cần khai báo §@Component§ hoặc §@Bean§ để được event multicaster gọi.

## 6. Gỡ listener bằng removeApplicationListener(...)

Spring Framework 6.0 trở lên cung cấp phương thức:

~~~java
void removeApplicationListener(ApplicationListener<?> listener);
~~~

Phương thức này gỡ listener đã đăng ký bằng §addApplicationListener(...)§ khỏi context. Hãy giữ lại tham chiếu đến listener để có thể gỡ đúng object:

~~~java
OrderCreatedListener listener = new OrderCreatedListener();

context.addApplicationListener(listener);

// Khi không cần listener nữa:
context.removeApplicationListener(listener);
~~~

Không tạo một object listener mới khi muốn gỡ object cũ. Ví dụ sau không phải cách đáng tin cậy:

~~~java
context.addApplicationListener(new OrderCreatedListener());

// Một object khác được tạo ra ở đây:
context.removeApplicationListener(new OrderCreatedListener());
~~~

Hai lời gọi §new§ tạo hai instance khác nhau. Hãy giữ một biến tham chiếu và dùng lại instance đã đăng ký.

Việc gỡ listener có ích khi listener chỉ cần hoạt động trong một giai đoạn, chẳng hạn một plugin được bật/tắt hoặc một thành phần chạy theo vòng đời của một context. Khi context đóng, Spring cũng giải phóng các tài nguyên do context quản lý; không cần giữ listener hoạt động sau khi context đã đóng.

## 7. Khác biệt với đăng ký listener dưới dạng bean

Có nhiều cách để Spring biết một listener. Cần phân biệt đăng ký trực tiếp bằng context với listener được quản lý như bean.

| Cách đăng ký | Đối tượng cần cung cấp | Spring quản lý bean? |
|---|---|---|
| §context.addApplicationListener(listener)§ | Một instance §ApplicationListener§ | Không tự biến instance đó thành bean |
| Bean implements §ApplicationListener<E>§ | Bean được đăng ký trong context | Có |
| Method có §@EventListener§ | Method của một bean được quản lý | Có |

### Đăng ký trực tiếp

Với §addApplicationListener§, bạn chịu trách nhiệm tạo listener và truyền dependency cho nó. Spring dùng instance đó để phân phối event, nhưng lời gọi này không đăng ký object vào BeanFactory, không tự inject dependency, không tự áp dụng BeanPostProcessor và không tạo proxy cho listener.

Ví dụ nếu listener cần một service, có thể tạo nó với dependency đã lấy từ context:

~~~java
AuditService auditService = context.getBean(AuditService.class);
AuditListener listener = new AuditListener(auditService);

context.addApplicationListener(listener);
~~~

### Đăng ký dưới dạng bean

Một bean triển khai §ApplicationListener§ sẽ được ApplicationContext phát hiện và đăng ký trong quá trình refresh:

~~~java
@Component
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Xử lý event.
    }
}
~~~

Cách này phù hợp khi listener cần dependency injection, lifecycle callback, AOP proxy hoặc các tính năng quản lý bean khác.

### Dùng @EventListener

Nếu muốn xử lý event bằng method mà không triển khai interface, có thể dùng annotation:

~~~java
@Component
public class OrderNotificationHandler {

    @EventListener
    public void handle(OrderCreatedEvent event) {
        System.out.println("Thông báo đơn mới: " + event.getOrderId());
    }
}
~~~

Method phải thuộc một bean được Spring quản lý để Spring phát hiện và đăng ký. Bạn không thể truyền trực tiếp một object POJO chỉ có method §@EventListener§ vào §addApplicationListener§, vì phương thức đó yêu cầu một object triển khai §ApplicationListener§.

## 8. Kiểu event và payload object

§ApplicationListener<E>§ khai báo §E§ là một kiểu con của §ApplicationEvent§. Đây là cách phù hợp khi bạn muốn đăng ký một listener có kiểu event cụ thể.

Từ Spring 4.2, publisher cũng có thể phát một object Java thông thường mà không cần kế thừa §ApplicationEvent§. Hạ tầng Spring bọc object đó trong §PayloadApplicationEvent§.

Nếu muốn tạo listener cho payload mà vẫn đăng ký trực tiếp bằng §ApplicationListener§, Spring cung cấp factory §ApplicationListener.forPayload(...)§ từ Spring 5.3:

~~~java
ApplicationListener<PayloadApplicationEvent<String>> listener =
        ApplicationListener.forPayload(
                payload -> System.out.println("Payload: " + payload));

context.addApplicationListener(listener);
context.publishEvent("Hello Spring");
~~~

Khi publish chuỗi §"Hello Spring"§, listener nhận payload qua consumer. Nếu dùng cách này, import thêm:

~~~java
import org.springframework.context.PayloadApplicationEvent;
~~~

Với event nghiệp vụ có nhiều trường và hành vi riêng, một lớp event cụ thể thường dễ đọc hơn. Với payload đơn giản, §forPayload§ giúp tránh phải tự viết một lớp listener chỉ để lấy payload.

## 9. Thứ tự, đồng bộ và phạm vi nhận event

### Đồng bộ mặc định

Với event multicaster mặc định, listener thường chạy đồng bộ trong thread gọi §publishEvent(...)§. Publisher chờ listener hoàn tất trước khi tiếp tục. Tuy nhiên, §ConfigurableApplicationContext.addApplicationListener(...)§ chỉ đăng ký listener; cách thực thi còn phụ thuộc vào cấu hình §ApplicationEventMulticaster§ và listener.

Nếu context dùng executor cho multicaster hoặc listener hỗ trợ asynchronous execution, event có thể được xử lý trên thread khác. Khi đó, không giả định rằng mọi listener hoàn tất trước khi §publishEvent§ trả về.

### Phạm vi context

Listener được đăng ký trên một context thuộc về event multicaster của context đó. Trong ứng dụng có parent và child context, cần xác định context nào phát event và listener nào được đăng ký ở đâu. Event của child context có thể được truyền lên parent theo cơ chế phân cấp của ApplicationContext; event từ parent không tự động truyền xuống child.

### Listener nhận context lifecycle event

Các context event phổ biến gồm:

- §ContextRefreshedEvent§: context đã được refresh.
- §ContextStartedEvent§: context được yêu cầu start.
- §ContextStoppedEvent§: context được yêu cầu stop.
- §ContextClosedEvent§: context đang đóng.

Nếu muốn nghe một lifecycle event, khai báo đúng kiểu generic, ví dụ §ApplicationListener<ContextClosedEvent>§. Đăng ký listener trước refresh nếu cần nhận §ContextRefreshedEvent§.

## 10. Lỗi thường gặp

- **Dùng sai loại context:** §ApplicationContext§ chỉ cung cấp API đọc và phát event; §addApplicationListener§ thuộc §ConfigurableApplicationContext§. Hãy dùng implementation hỗ trợ interface cấu hình.
- **Đăng ký sau refresh nhưng mong nhận event cũ:** Listener chỉ nhận event kể từ khi được đăng ký.
- **Gọi refresh hai lần:** Một số context implementation chỉ cho phép refresh một lần. Với §AnnotationConfigApplicationContext§ dùng constructor nhận class cấu hình, context đã tự refresh; không gọi thêm §refresh()§.
- **Truyền object không triển khai ApplicationListener:** §addApplicationListener§ yêu cầu đúng kiểu listener. Với method annotation, đăng ký một bean có §@EventListener§.
- **Mong Spring tự inject dependency vào listener tạo bằng new:** Object được đăng ký trực tiếp không tự trở thành bean. Hãy truyền dependency qua constructor hoặc dùng listener bean.
- **Không giữ tham chiếu khi muốn gỡ listener:** Lưu instance vào biến và truyền chính instance đó cho §removeApplicationListener§.
- **Nhầm đăng ký listener với phát event:** §addApplicationListener§ chỉ đăng ký người nhận; publisher vẫn phải gọi §publishEvent(...)§.
- **Giả định listener luôn chạy đồng bộ:** Kiểm tra cấu hình multicaster và hỗ trợ async của listener trước khi dựa vào thứ tự hoàn tất.

## 11. Khi nào nên dùng cách này?

Dùng §ConfigurableApplicationContext.addApplicationListener(...)§ khi:

- Cần đăng ký listener trước refresh để nhận context lifecycle event.
- Listener được tạo động theo cấu hình hoặc theo vòng đời của một context.
- Một module hoặc plugin cần tự đăng ký và gỡ listener khi bật/tắt.
- Cần gắn một listener instance đã được tạo sẵn vào một context cụ thể.

Dùng listener bean hoặc §@EventListener§ khi listener là thành phần cố định của ứng dụng và cần Spring quản lý dependency, proxy, lifecycle hoặc transaction integration.

## 12. Checklist triển khai

Trước khi hoàn tất một listener đăng ký bằng code, kiểm tra:

1. Context implementation có hỗ trợ §ConfigurableApplicationContext§.
2. Listener triển khai §ApplicationListener<E>§ với đúng kiểu event.
3. Đăng ký trước hay sau refresh phù hợp với event cần nhận.
4. Listener đã được tạo với đầy đủ dependency cần thiết.
5. Event publisher thực sự phát event có kiểu tương thích.
6. Đã giữ tham chiếu listener nếu cần gỡ.
7. Đã kiểm tra cấu hình đồng bộ/bất đồng bộ và phạm vi parent/child context.
8. Context được đóng đúng cách khi không còn sử dụng.

## 13. Ghi nhớ

§ConfigurableApplicationContext.addApplicationListener(...)§ đăng ký một instance §ApplicationListener§ trực tiếp với context. Nếu gọi trước refresh, Spring áp dụng listener khi refresh; nếu context đã active, listener được thêm vào event multicaster hiện tại. Spring Framework 6.0+ cũng có §removeApplicationListener(...)§ để gỡ listener đã đăng ký.

Cách này rất phù hợp cho listener được tạo động hoặc cần theo dõi lifecycle của context. Nếu listener là một phần cố định của ứng dụng và cần dependency injection hoặc AOP, đăng ký nó thành bean thường dễ quản lý hơn.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2.0 — ConfigurableApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework 6.2.0 — ApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring Framework 6.2.0 — ApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
