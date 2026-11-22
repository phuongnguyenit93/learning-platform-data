# Dùng @EventListener cho listener được quản lý như bean trong Spring Boot

## 1. Mục tiêu: phản ứng với sự kiện bằng một Spring bean thông thường

Trong Spring Boot, một lớp dịch vụ có thể **phát sự kiện** khi một hành động xảy ra, ví dụ đơn hàng được tạo, báo cáo hoàn tất hoặc trạng thái ứng dụng thay đổi. Thành phần khác sẽ **lắng nghe** và thực hiện nhiệm vụ liên quan mà không buộc bên phát sự kiện gọi trực tiếp từng bên nhận.

**@EventListener** là annotation của Spring Framework, dùng để đánh dấu **một phương thức trên bean do ApplicationContext quản lý** là phương thức nhận sự kiện. Không bắt buộc lớp phải implements **ApplicationListener**; kiểu tham số của phương thức thông thường xác định kiểu sự kiện mà nó muốn xử lý.

Ví dụ đơn giản trong một ứng dụng đã có cấu hình component scanning:

~~~java
@Component
class AuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        System.out.println("Audit: " + event.orderId());
    }
}
~~~

Đây là **snippet**, giả định có kiểu **OrderPlaced** với accessor **orderId()** và các import **@Component**, **@EventListener**. Spring đăng ký method này vì **AuditListener là một bean**. Khi code khác gọi **ApplicationEventPublisher.publishEvent(new OrderPlaced(...))**, Spring chuyển sự kiện đến method phù hợp.

**Các ý cần ghi nhớ ngay:**

- **@EventListener nằm trên method**, không phải trên lớp; lớp chứa method phải được quản lý như một Spring bean.
- **@Component**, **@Service**, **@Configuration** hoặc một **@Bean** factory method đều có thể tạo bean chứa listener, miễn bean thực sự có trong ApplicationContext.
- **@EventListener** không tự biến một đối tượng được tạo bằng **new** thành Spring bean.
- Theo mặc định, listener nhận sự kiện **đồng bộ trên thread phát sự kiện**; không có queue bền vững, retry tự động hay cam kết giao nhận như hệ thống messaging.
- Listener dạng bean thích hợp cho những sự kiện được phát **sau khi context đủ điều kiện đăng ký listener**. Nó **không phải cách nhận các sự kiện SpringApplication rất sớm** trước khi context được tạo.

Bài dùng **Spring Boot 3.3.x, Spring Framework 6.1 và Java 17+** làm mốc.

## 2. Các thành phần liên quan và cách chúng phối hợp

Có bốn thành phần cơ bản:

1. **Event**: một đối tượng Java mô tả điều vừa xảy ra. Trong Spring Framework hiện đại, event có thể là một object/record bất kỳ; **không bắt buộc extends ApplicationEvent**.
2. **ApplicationEventPublisher**: interface cho phép bean phát sự kiện bằng **publishEvent(Object event)**.
3. **ApplicationEventMulticaster**: hạ tầng phân phối sự kiện tới các listener tương ứng. Trong context thông thường, Spring dùng **SimpleApplicationEventMulticaster** với hành vi đồng bộ mặc định.
4. **Bean chứa @EventListener**: một bean mà method của nó được Spring phát hiện và đăng ký làm listener.

~~~text
OrderService / ApplicationRunner
     |
     | publishEvent(new OrderPlaced(...))
     v
ApplicationEventPublisher
     |
     v
ApplicationEventMulticaster
     |
     +--> Bean AuditListener
     |       @EventListener onOrderPlaced(...)
     |
     +--> Bean NotificationListener
     |       @EventListener(condition = "...")
     |
     +--> Bean MetricsListener
             @EventListener onOrderPlaced(...)
~~~

**Một lần publish có thể gọi nhiều listener**. Bên phát không cần biết số lượng hoặc tên của bên nhận. Với mặc định đồng bộ, các listener được gọi trong luồng publish và **publishEvent(...) thường chỉ trả về sau khi các callback đồng bộ hoàn tất**.

### 2.1. Event nên mang gì?

Một event nghiệp vụ nên diễn đạt **sự kiện đã xảy ra**, có dữ liệu tối thiểu đủ để listener xử lý:

~~~java
public record OrderPlaced(String orderId, int priority) {
}
~~~

Record phù hợp cho sự kiện bất biến nhỏ. Nếu cần truy xuất dữ liệu lớn hoặc nhạy cảm, có thể đưa **ID** thay vì cả entity JPA hoặc bí mật vào payload. Tránh truyền object đang bị mutate đồng thời, đặc biệt khi chuyển sang listener bất đồng bộ.

Sự kiện **không cần kế thừa ApplicationEvent**:

~~~java
publisher.publishEvent(new OrderPlaced("ORD-100", 5));
~~~

Khi publish một object không kế thừa ApplicationEvent, Spring có thể bọc nó bằng **PayloadApplicationEvent** trong tầng multicaster; method **@EventListener** vẫn có thể nhận **OrderPlaced** trực tiếp nhờ cơ chế nhận diện payload.

### 2.2. @EventListener khác ApplicationListener như thế nào?

| Tiêu chí | @EventListener | ApplicationListener<E> |
| --- | --- | --- |
| Khai báo | Annotation trên **method** của bean | Interface trên **class/object** |
| Chọn loại sự kiện | Kiểu tham số hoặc **classes/value** | Tham số generic **E** |
| Lọc theo dữ liệu | Hỗ trợ **condition** (SpEL) | Tự viết điều kiện trong code |
| Phát event kế tiếp | Có thể **trả về** event/collection khi đồng bộ | Thường gọi publisher trực tiếp |
| Phù hợp làm bean thông thường | Có | Có |
| Nhận sự kiện rất sớm trước context | **Không** nếu chỉ là method trên bean | Có thể, **nếu được đăng ký trực tiếp trước run** |

**ApplicationListener** không tự động có lợi thế nhận sự kiện sớm nếu nó cũng chỉ được tạo như một bean bình thường. Yếu tố quyết định là **listener đã được đăng ký trước lúc sự kiện phát hay chưa**, không chỉ là tên interface.

## 3. Điều kiện để Spring phát hiện method @EventListener

Hãy kiểm tra cả ba phần:

**Một — Bean phải thuộc context.** Ví dụ:

~~~java
@Component
class OrderEventHandler {

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Xử lý sự kiện.
    }
}
~~~

Nếu lớp nằm ngoài vùng **@ComponentScan**, không có **@Import**, cũng không được khai báo qua **@Bean**, thì method sẽ không được phát hiện. Đối tượng **new OrderEventHandler()** được tạo thủ công bên ngoài Spring cũng không được đăng ký tự động.

**Hai — Method phải có chữ ký phù hợp.** Cách phổ biến nhất là một tham số kiểu event và trả về **void**:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    // ...
}
~~~

Nếu muốn một method nhận **nhiều loại sự kiện** và **không có tham số**, có thể khai báo lớp sự kiện trên annotation:

~~~java
@EventListener({
    ContextRefreshedEvent.class,
    ContextClosedEvent.class
})
public void onContextLifecycle() {
    // Không có tham số vì method nhận nhiều loại event.
}
~~~

Đây là **snippet** cần import của Spring; nó chỉ minh họa cú pháp. Khi method không có tham số, phải khai báo loại event trên annotation. Khi method có đúng một tham số, Spring thường suy ra loại event từ tham số đó.

**Ba — Bean phải được khởi tạo/đăng ký ở giai đoạn thích hợp.** Spring xử lý các method **@EventListener** trong lifecycle container, với hạ tầng **EventListenerMethodProcessor** và adapter phương thức. Đừng chủ động đánh dấu bean listener là **@Lazy** nếu muốn chắc chắn nó đã được đăng ký để nhận sự kiện: tài liệu Spring Framework khuyến cáo không tạo các listener dạng này thành lazy bean.

Với bean dùng AOP/proxy, nên giữ method listener có thể gọi qua proxy được tạo ra (ví dụ public method thuộc interface khi dùng JDK dynamic proxy, hoặc cấu hình proxy phù hợp). Nếu method chỉ tồn tại trên implementation mà proxy interface không bộc lộ nó, Spring có thể không gọi được method qua proxy; kiểm tra thông báo lỗi và kiểu proxy trước khi xử lý.

### 3.1. Không nhầm @EventListener với @Bean

**@Bean** dùng để tạo/đăng ký bean. **@EventListener** dùng để đăng ký **phương thức xử lý event của bean đã được tạo**. Có thể dùng cả hai qua các phần khác nhau:

~~~java
@Configuration(proxyBeanMethods = false)
class ListenerConfiguration {

    @Bean
    OrderEventHandler orderEventHandler() {
        return new OrderEventHandler();
    }
}
~~~

Method **orderEventHandler()** tạo bean; còn **OrderEventHandler.onOrderPlaced(...)** có **@EventListener** mới là event callback. Không cần ghi **@EventListener** lên factory method **@Bean**.

## 4. Ví dụ chạy được: bean listener nhận event, lọc và phát event tiếp theo

Ví dụ này cố ý dùng **ứng dụng không có HTTP server** để stdout dễ quan sát, nhưng cơ chế **@EventListener** giống nhau trong ứng dụng Spring MVC hay WebFlux.

### 4.1. Chuẩn bị project

Yêu cầu **Java 17+**, Maven 3.9+ (hoặc Maven Wrapper), Spring Boot 3.3.x. Tạo project có dependency **spring-boot-starter** và package **com.example.events**. Một **pom.xml** tối thiểu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>managed-events-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

Đặt ứng dụng vào **src/main/java/com/example/events/ManagedEventsApplication.java**:

~~~java
package com.example.events;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ManagedEventsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ManagedEventsApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }

    public record OrderPlaced(String orderId, int priority) {
    }

    public record ImportantOrder(String orderId) {
    }

    @Bean
    ApplicationRunner publishSampleOrders(ApplicationEventPublisher publisher) {
        return args -> {
            System.out.println("RUNNER | publish normal");
            publisher.publishEvent(new OrderPlaced("ORD-100", 1));

            System.out.println("RUNNER | publish important");
            publisher.publishEvent(new OrderPlaced("ORD-200", 9));

            System.out.println("RUNNER | finished");
        };
    }

    @Component
    static class OrderEventHandlers {

        @EventListener
        @Order(10)
        public void logEveryOrder(OrderPlaced event) {
            System.out.println("LOG | " + event.orderId());
        }

        @EventListener(condition = "#a0.priority() >= 5")
        @Order(20)
        public ImportantOrder handleHighPriorityOrder(OrderPlaced event) {
            System.out.println("FILTER | " + event.orderId());
            return new ImportantOrder(event.orderId());
        }

        @EventListener
        public void handleImportantOrder(ImportantOrder event) {
            System.out.println("FOLLOWUP | " + event.orderId());
        }
    }
}
~~~

Chạy với Maven từ thư mục chứa **pom.xml**:

~~~bash
mvn -q spring-boot:run
~~~

Nếu dự án có Maven Wrapper, có thể dùng:

~~~bash
./mvnw -q spring-boot:run
~~~

PowerShell trên Windows với Maven Wrapper:

~~~powershell
.\mvnw.cmd -q spring-boot:run
~~~

**Những dòng do chương trình tự in, theo thứ tự kỳ vọng** khi dùng multicaster đồng bộ mặc định:

~~~text
RUNNER | publish normal
LOG | ORD-100
RUNNER | publish important
LOG | ORD-200
FILTER | ORD-200
FOLLOWUP | ORD-200
RUNNER | finished
MAIN | active=true
~~~

Log/framework/build tool có thể xen giữa các dòng trên. **Đây là thứ tự các dòng ứng dụng tự in**, không phải cam kết rằng toàn bộ stdout chỉ chứa tám dòng.

### 4.2. Phân tích từng bước

1. **SpringApplication.run(...)** tạo và refresh ApplicationContext, hoàn tất đăng ký các listener bean.
2. Spring gọi bean **ApplicationRunner** sau khi refresh. Runner phát **OrderPlaced("ORD-100", 1)**.
3. Listener **logEveryOrder** nhận mọi **OrderPlaced**, in **LOG | ORD-100**. Listener có điều kiện **priority >= 5** không chạy với đơn hàng này.
4. Runner phát **OrderPlaced("ORD-200", 9)**. Listener **logEveryOrder** chạy trước do **@Order(10)** nhỏ hơn **@Order(20)**.
5. Listener lọc chạy với priority 9, in dòng **FILTER**, trả về object **ImportantOrder**.
6. Spring coi giá trị trả về của method **@EventListener đồng bộ** như **một event mới**, phát lại qua multicaster; method **handleImportantOrder** nhận event này và in dòng **FOLLOWUP**.
7. **publishEvent** thứ hai hoàn tất, runner in **RUNNER | finished**. Sau khi **run(...)** trả về, main in **MAIN | active=true**.
8. **try-with-resources** đóng context khi kết thúc ví dụ CLI. Không dùng pattern này để đóng ứng dụng web ngay sau khi khởi chạy nếu cần phục vụ HTTP lâu dài.

Để ví dụ dễ dự đoán, các event ở đây là **Java record** bất biến, không dùng thread pool và không sử dụng transaction. Khi bật async hoặc thêm transaction listener, thứ tự và thời điểm tác động có thể thay đổi.

### 4.3. Tại sao nested @Component vẫn được Spring quản lý?

**OrderEventHandlers** là lớp **static nested** có **@Component** trong package được ứng dụng quét, nên Spring có thể đăng ký nó như một bean. Điều đó khác với một inner class không static cần instance của lớp ngoài.

Nếu tách OrderEventHandlers thành **OrderEventHandlers.java** riêng với **@Component**, kết quả chức năng vẫn tương tự. Trong ứng dụng thật, tách lớp theo trách nhiệm thường giúp code rõ và dễ unit test hơn.

## 5. Chữ ký @EventListener và cách chọn event

### 5.1. Nhận một event qua tham số

Cách rõ ràng và nên ưu tiên:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Xử lý một event.
}
~~~

Spring dựa trên kiểu tham số **OrderPlaced** để chọn listener. Event có thể là một lớp, record hoặc kiểu kế thừa **ApplicationEvent**.

### 5.2. Một method nhận nhiều loại event

Nếu một method muốn nhận **ContextRefreshedEvent** và **ContextClosedEvent**, có thể khai báo:

~~~java
@EventListener({
    ContextRefreshedEvent.class,
    ContextClosedEvent.class
})
public void onContextChange() {
    // Method không có tham số.
}
~~~

Có thể dùng method với một tham số kiểu chung phù hợp, nhưng khi nội dung xử lý thực sự khác nhau thì **hai method riêng** dễ bảo trì hơn.

### 5.3. Lọc với condition của @EventListener

**condition** là một biểu thức **SpEL** được Spring đánh giá trước khi gọi method. Nếu biểu thức trả về true, listener thực thi:

~~~java
@EventListener(condition = "#a0.priority() >= 5")
public void onImportantOrder(OrderPlaced event) {
    // Chỉ xử lý khi priority >= 5.
}
~~~

Ở đây **#a0** là tham số thứ nhất của method callback. Dùng **#a0** hoặc **#p0** giúp tránh phụ thuộc việc compiler có lưu tên tham số hay không. Trong một số điều kiện có thể dùng **#event** nếu method parameter name được giữ và Spring có thể resolve tên; không nên dựa vào cách này mà bỏ qua cấu hình compiler.

Một cú pháp tương đương dùng mảng arguments:

~~~java
@EventListener(condition = "#root.args[0].priority() >= 5")
public void onImportantOrder(OrderPlaced event) {
    // ...
}
~~~

Nếu dùng method trên record, **priority()** là accessor Java thực sự, không cần suy đoán về tên field. Với event khác, hãy viết biểu thức phù hợp các getter/method có thật.

**Đừng biến SpEL thành nơi làm nghiệp vụ phức tạp.** Điều kiện đơn giản như type, trạng thái hoặc ngưỡng phù hợp; kiểm tra nghiệp vụ nhiều nhánh nên nằm trong method/service được test bằng Java.

### 5.4. Event subtype và generic

Listener theo kiểu event thường nhận các event tương thích với type đã đăng ký. Với event generic như **EntityCreatedEvent<T>**, muốn filter chính xác theo **T** phải bảo đảm runtime còn cung cấp thông tin kiểu: dùng một subclass cụ thể hoặc **ResolvableTypeProvider** khi cần. Chỉ tạo **new EntityCreatedEvent<Person>(...)** không bảo đảm framework luôn giữ được tham số generic do **type erasure**.

Đây là vấn đề nâng cao khi xây dựng hệ thống event generic. Với code nghiệp vụ đơn giản, đặt tên event theo hành động rõ ràng (**CustomerRegistered**, **InvoicePaid**) thường dễ hiểu và dễ kiểm thử hơn.

## 6. Phương thức trả về event và giới hạn của cơ chế này

Trong ví dụ, method:

~~~java
@EventListener
public ImportantOrder handleHighPriorityOrder(OrderPlaced event) {
    return new ImportantOrder(event.orderId());
}
~~~

không chỉ xử lý event ban đầu mà còn **phát tiếp một event** bằng giá trị trả về. Với listener đồng bộ, Spring hỗ trợ trả về:

- **Một object**: object đó được publish làm event.
- **Collection** hoặc **array**: mỗi phần tử được xem là một event để publish.
- **void**: không phát event tiếp theo bằng cơ chế return.

Nếu method chỉ cần thực thi side effect và không có event mới có ý nghĩa, hãy dùng **void**. Không trả về một giá trị dữ liệu thông thường với kỳ vọng đó là “kết quả xử lý” được gửi riêng cho publisher: Spring có thể hiểu nó là một **event khác**, gây phản ứng không mong muốn.

**Đặc biệt: method @EventListener được thực thi bất đồng bộ bằng @Async không được phát event thông qua giá trị trả về.** Nếu cần phát event tiếp theo từ async listener, inject **ApplicationEventPublisher** và gọi **publishEvent(...)** rõ ràng.

Không nên tạo chu trình không có điều kiện dừng: event A sinh B, B lại sinh A liên tục. Với multicaster đồng bộ, chu trình này có thể gây đệ quy và tràn stack.

## 7. Mặc định đồng bộ: ý nghĩa cho hiệu năng và lỗi

Với **SimpleApplicationEventMulticaster** mặc định, callback đồng bộ chạy **trong thread gọi publishEvent**. Điều đó có nghĩa:

- Nếu listener xử lý mất 500 ms, bên publish có thể phải chờ trong thời gian đó.
- Listener làm việc trong cùng thread, nên có thể thấy thread-bound context như transaction hiện hữu, nhưng không được suy luận rằng mọi event tự động có transaction.
- Exception của một listener đồng bộ có thể **lan ngược về bên gọi publishEvent(...)** và chặn các bước xử lý tiếp theo. Nếu event được publish trong **ApplicationRunner**, exception không xử lý có thể làm **SpringApplication.run(...)** thất bại.
- Mỗi context có multicaster riêng; parent/child context có thể khiến sự kiện từ child được chuyển lên ancestor, cần quan sát trường hợp nhận event nhiều lần.

**Không coi @EventListener là queue background theo mặc định.** Chỉ thêm annotation không làm callback tự chuyển sang thread riêng.

### 7.1. Thứ tự giữa các listener dùng @Order

Nếu hai listener cùng nhận loại event và cần xác định thứ tự dispatch, dùng **@Order** trên method:

~~~java
@EventListener
@Order(10)
public void first(OrderPlaced event) {
    // ...
}

@EventListener
@Order(20)
public void second(OrderPlaced event) {
    // ...
}
~~~

Giá trị **nhỏ hơn** thường được gọi **trước**. Đừng phụ thuộc thứ tự tên method hay vị trí khai báo trong Java source file.

Khi listener đã chạy bất đồng bộ, **@Order** không đảm bảo một công việc sẽ **hoàn tất** trước công việc khác. Nếu B cần kết quả chắc chắn của A, hãy thể hiện dependency qua API, chain rõ ràng hoặc chuỗi công việc có quản lý, thay vì trông chờ vào thứ tự hoàn tất của hai listener async.

### 7.2. Sử dụng event cho thông báo chứ không cho kết quả cần chờ

Ví dụ OrderService cần **kết quả tính thuế** để xác nhận đơn hàng thì gọi thẳng **TaxService.calculate(...)** phù hợp hơn. Nếu cần báo cho bộ phận phân tích “đơn hàng đã được chấp nhận”, một event **OrderAccepted** có thể giúp giảm coupling.

Event nội bộ phù hợp cho **thông báo trong cùng ứng dụng/context**; nó không phải lời hứa giao hàng bền vững hay transaction phân tán.

## 8. @Async cùng @EventListener: khác gì và khi nào nên dùng?

Khi listener làm việc tốn thời gian nhưng không cần chặn bên publish, có thể sử dụng **@Async** trên method và **@EnableAsync** trên cấu hình của ứng dụng:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncEventsConfiguration {
}
~~~

~~~java
@Component
class EmailNotificationListener {

    @Async
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Ví dụ: gửi notification I/O, cần timeout/retry phù hợp.
    }
}
~~~

Hai đoạn là **snippets** trong ứng dụng đã có **OrderPlaced** và các import **@Configuration**, **@EnableAsync**, **@Async**, **@Component**, **@EventListener**. Spring cần thiết lập async infrastructure và executor phù hợp; trong dự án production, nên cấu hình **ThreadPoolTaskExecutor** có giới hạn queue, số thread, tên thread, chính sách từ chối và shutdown.

Các giới hạn quan trọng:

1. Listener **@Async** có thể chạy trên thread khác; **publishEvent** không mặc nhiên chờ callback hoàn tất.
2. Exception từ async listener **không truyền thẳng** về publisher; cần logging, **AsyncUncaughtExceptionHandler** và chiến lược retry/giám sát tương ứng.
3. **Không publish event tiếp theo bằng giá trị return** của async listener; dùng **ApplicationEventPublisher.publishEvent**.
4. Các dữ liệu dựa trên **ThreadLocal** (như transaction thread-bound, security context hoặc MDC) **không tự được chuyển** sang thread khác trong mọi cấu hình.
5. **@Order** chỉ hỗ trợ thứ tự gọi/dispatch ở mức thích hợp, không cung cấp thứ tự hoàn thành giữa các tác vụ chạy song song.
6. Chỉ nên dùng async khi side effect không phải điều kiện bắt buộc trước khi thao tác nghiệp vụ được xem là thành công.

**Không thêm @EnableAsync vào ví dụ chính ở mục 4**, vì mục tiêu ở đó là in một thứ tự đồng bộ dễ quan sát.

## 9. @EventListener và transaction: khi nào dùng @TransactionalEventListener?

Giả sử một service đang chạy trong **@Transactional** và phát **OrderPlaced**. Nếu listener thông thường gửi email ngay lập tức, email có thể được gửi **trước khi transaction commit**. Nếu transaction rollback sau đó, khách hàng đã nhận thông báo về đơn hàng thực tế chưa được lưu thành công.

Spring hỗ trợ **@TransactionalEventListener** để ràng buộc event callback vào một giai đoạn transaction.

~~~java
@Component
class OrderConfirmationListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderPlaced event) {
        // Chỉ xử lý khi transaction liên quan commit thành công.
    }
}
~~~

Đây là snippet, cần các import **@TransactionalEventListener**, **TransactionPhase**, **@Component** và lớp **OrderPlaced**. Các phase thường dùng:

| Phase | Thời điểm |
| --- | --- |
| **BEFORE_COMMIT** | Ngay trước khi commit |
| **AFTER_COMMIT** | Sau commit thành công (**mặc định**) |
| **AFTER_ROLLBACK** | Sau rollback |
| **AFTER_COMPLETION** | Sau khi transaction kết thúc, bất kể commit/rollback |

**Mặc định, nếu không có transaction đang hoạt động**, **@TransactionalEventListener** **không gọi callback**. Muốn xử lý cả khi không có transaction, có thể khai báo **fallbackExecution = true**, nhưng phải hiểu rằng lúc ấy không còn bảo đảm “chỉ sau commit”.

Một số lưu ý quan trọng:

- **@EventListener** thường được gọi khi event phát; **@TransactionalEventListener** được gắn với phase của transaction.
- Không nên gắn cả hai annotation vào cùng method với hy vọng nhận hai luồng callback độc lập; hãy chọn đúng semantics.
- Một listener **AFTER_COMMIT** có thể vẫn nhìn thấy tài nguyên transaction cũ, nhưng **ghi dữ liệu mới không tự được commit như một transaction mới**. Nếu phải ghi DB độc lập sau commit, xem xét dịch vụ với **REQUIRES_NEW** và ranh giới transaction rõ ràng.
- Trong ứng dụng reactive, transaction context không dựa vào ThreadLocal như imperative transaction; Spring Framework 6.1 cung cấp cơ chế tương ứng qua Reactor context/event source. Cần dùng đúng API thay vì giả định listener reactive làm việc giống hệt thread-bound transaction.
- **AFTER_COMMIT không bảo đảm thông báo ra hệ thống khác được giao bền vững**. Nếu cần giao hàng an toàn khi ứng dụng crash giữa commit và publish/consume, cân nhắc **transactional outbox** và message broker.

Nếu ví dụ ở mục 4 không mở transaction, thay **@EventListener** bằng **@TransactionalEventListener** theo mặc định sẽ khiến callback bị bỏ qua; đó là hành vi đúng theo semantics của annotation.

## 10. Vì sao @EventListener của bean không bắt được các sự kiện SpringApplication rất sớm?

Một lỗi phổ biến là viết:

~~~java
@Component
class EarlyBootListener {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        System.out.println("Application starting");
    }
}
~~~

**Không nên kỳ vọng method này nhận ApplicationStartingEvent của chính lần chạy**, vì sự kiện được phát trước khi ApplicationContext tồn tại và trước khi bean listener được tạo/đăng ký. Tương tự, **ApplicationEnvironmentPreparedEvent** và **ApplicationContextInitializedEvent** nằm trong bootstrap sớm.

Spring Boot khuyến nghị **đăng ký listener từ trước khi run** đối với những event sớm:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationStartingEvent>) event -> {
    System.out.println("Early startup event");
});
app.run(args);
~~~

Đây là snippet giả định có **MyApplication** và import **SpringApplication**, **ApplicationListener**, **ApplicationStartingEvent**. Listener được tạo/đăng ký trước run, không dựa vào bean discovery.

Nếu cần listener sớm tự động cho một thư viện, Spring Boot còn hỗ trợ khai báo trong **META-INF/spring.factories** dưới key **org.springframework.context.ApplicationListener**.

### 10.1. Event nào phù hợp để dùng @EventListener dạng bean?

Các event phát **sau khi context được refresh** thường phù hợp, ví dụ:

- **ApplicationStartedEvent**: Spring Boot đã refresh context, trước khi runner chạy.
- **ApplicationReadyEvent**: sau khi runner hoàn tất, ứng dụng gần hoàn tất quy trình startup.
- **ContextRefreshedEvent**, **ContextClosedEvent**: sự kiện vòng đời của ApplicationContext, cần chú ý thứ tự xử lý/hierarchy.
- **Custom domain event** do bean phát sau khi app vận hành.
- **AvailabilityChangeEvent**: sự kiện thay đổi trạng thái availability; có thể dùng listener bean để quan sát nếu đảm bảo đăng ký đúng lúc.

**ApplicationPreparedEvent** phát trước refresh nên không nên coi là sự kiện mà một listener dạng bean thông thường chắc chắn nhận. **ApplicationFailedEvent** có thể xảy ra rất sớm, trước khi context/bean listener sẵn sàng; với nhu cầu bắt lỗi bootstrap mọi giai đoạn, cần listener đăng ký sớm thay vì chỉ @EventListener bean.

### 10.2. Parent/child context và nhận event lặp

Trong hệ thống có **hierarchy ApplicationContext**, một sự kiện được publish ở child context có thể được chuyển tới listener ở parent. Nếu listener ở parent thực hiện side effect, nó có thể nhận nhiều event cùng kiểu từ các context khác nhau.

Đối với event kế thừa **ApplicationContextEvent**, method có thể kiểm tra **event.getApplicationContext()** so với context được inject để chỉ xử lý event của context đích. Đối với custom payload event, có thể kèm định danh nguồn/context trong payload nếu yêu cầu là phân biệt nguồn. Không giả định listener chỉ chạy một lần trên toàn JVM.

## 11. Kiểm thử listener được quản lý như bean

Có hai cấp độ cần phân biệt:

- **Unit test**: gọi trực tiếp logic Java bên trong handler để kiểm tra biến đổi, validation, quyết định nghiệp vụ.
- **Context/integration test**: tạo một Spring context thật, đăng ký bean và publish event để xác nhận Spring phát hiện **@EventListener**, lọc đúng kiểu và gọi callback.

Kiểm thử thứ hai đặc biệt hữu ích vì **new OrderEventHandlers().handle...** sẽ chạy được Java method nhưng **không chứng minh Spring đã đăng ký nó làm listener**.

### 11.1. Một context test tối thiểu với JUnit 5

Khi project có **spring-boot-starter-test**, tạo file **src/test/java/com/example/events/BeanEventListenerTest.java**:

~~~java
package com.example.events;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BeanEventListenerTest {

    record DemoEvent(String code) {
    }

    static class Recorder {
        final List<String> received = new ArrayList<>();
    }

    static class RecordingListener {
        private final Recorder recorder;

        RecordingListener(Recorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        public void onEvent(DemoEvent event) {
            recorder.received.add(event.code());
        }
    }

    @Test
    void managedBeanReceivesPublishedEvent() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(Recorder.class);
            context.registerBean(RecordingListener.class);
            context.refresh();

            context.publishEvent(new DemoEvent("EVT-1"));

            assertEquals(
                    List.of("EVT-1"),
                    context.getBean(Recorder.class).received);
        }
    }
}
~~~

Để chạy test, bổ sung dependency **spring-boot-starter-test** với scope **test** vào **pom.xml** của mục 4:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Chạy:

~~~bash
mvn test
~~~

Test **không cần khởi động HTTP server**. **AnnotationConfigApplicationContext** đăng ký infrastructure annotation/event processing, nhận **RecordingListener** làm bean rồi publish **DemoEvent**. Nếu method được Spring phát hiện, **Recorder.received** chứa đúng mã **EVT-1**.

**Không cần @Component trên RecordingListener trong test này** vì **registerBean(RecordingListener.class)** đã trực tiếp đăng ký bean vào context. Trong ứng dụng thật, bạn thường dùng **@ComponentScan**, **@Bean** hoặc import configuration thay cho đăng ký programmatic như vậy.

### 11.2. Test lọc condition và thứ tự

Đối với listener có **condition**, test nên publish ít nhất hai event:

~~~text
Event priority=1 -> listener không chạy
Event priority=9 -> listener chạy đúng một lần
~~~

Đối với **@Order**, test nên record một danh sách các callback trong **cùng context/multicaster đồng bộ** và assert thứ tự. Đừng viết test dựa trên thời gian thread sleep hoặc đòi thứ tự hoàn tất của các async callback.

Đối với **@TransactionalEventListener**, test cần có transaction thực tế và phân biệt commit/rollback. Đừng chỉ publish event trong context không có transaction rồi kết luận listener bị lỗi.

### 11.3. Vì sao test unit không đủ?

Một unit test kiểu:

~~~java
OrderEventHandlers handler = new OrderEventHandlers();
handler.logEveryOrder(new OrderPlaced("ORD-1", 1));
~~~

chỉ chứng minh **Java method chạy**. Nó không kiểm tra component scanning, EventListenerMethodProcessor, condition SpEL, async proxy, thứ tự event hoặc event type matching. Hãy dùng context test khi những đặc tính framework đó là điều bạn cần bảo đảm.

## 12. Những lỗi thường gặp và cách khắc phục

### 12.1. Listener không được gọi dù có @EventListener

Kiểm tra lớp có phải Spring bean không, có nằm trong component scan không, có bị điều kiện cấu hình loại khỏi context không và bean có bị lazy không. Với method trên proxy, kiểm tra proxy có thể gọi method hay không. Đảm bảo event **được publish vào đúng ApplicationContext** mà listener đã đăng ký.

### 12.2. Tạo listener bằng new thay vì đăng ký bean

**new AuditListener()** tạo Java object nhưng không tự thêm nó vào context. Đưa class vào component scan, cấu hình **@Bean** hoặc đăng ký qua cơ chế Spring hỗ trợ.

### 12.3. Cố nhận ApplicationEnvironmentPreparedEvent bằng @EventListener

Sự kiện này đến **trước khi context tạo**; dùng **SpringApplication.addListeners(...)**, builder listeners hoặc **spring.factories**. Không đợi Spring quét bean rồi yêu cầu framework phát lại event bootstrap đã qua.

### 12.4. Publish sự kiện rồi tưởng listener chạy background

Mặc định listener **đồng bộ**. Nếu làm I/O lâu trong listener, bên publisher có thể bị block. Dùng cơ chế async thích hợp chỉ khi nghiệp vụ cho phép; thêm timeout, queue limit, logging và error handling cho production.

### 12.5. Exception trong listener làm hỏng thao tác chính

Trong chế độ đồng bộ, exception có thể lan về publisher. Một email notification thất bại không nhất thiết nên làm transaction tạo đơn hàng thất bại. Phân biệt điều kiện bắt buộc và side effect tùy chọn; chọn transaction phase, async hoặc messaging/outbox khi cần.

### 12.6. Lọc bằng SpEL nhưng method luôn bị bỏ qua hoặc lỗi expression

Kiểm tra accessor/property có thật, kiểu trả về, cú pháp dấu nháy và cách tham chiếu tham số. **#a0** thường ổn định hơn tên tham số nếu project không giữ thông tin **-parameters**. Một lỗi SpEL có thể khiến đường xử lý event phát sinh exception.

### 12.7. Cần thứ tự nhưng không khai báo rõ

Hai listener không có **@Order** không nên dựa vào vị trí trong file hoặc thứ tự bean registration. Khai báo thứ tự khi có nhu cầu thật sự, và xác minh bằng context test.

### 12.8. Dùng return value trong @Async listener để phát tiếp event

Cơ chế tự publish giá trị trả về **không hỗ trợ cho async listener**. Inject **ApplicationEventPublisher**, gọi **publishEvent(...)** tường minh, và chịu trách nhiệm kiểm soát exception/retry.

### 12.9. @TransactionalEventListener không chạy khi không có transaction

Đây là hành vi mặc định vì không có phase commit/rollback để ràng buộc. Nếu muốn luôn nhận event, cân nhắc listener thông thường hoặc **fallbackExecution=true** với ý nghĩa nghiệp vụ rõ ràng.

### 12.10. Listener bị gọi nhiều lần trong hệ thống nhiều context

Sự kiện từ child context có thể lan tới parent. Nếu xử lý event mang side effect, lọc đúng nguồn, bảo đảm idempotence và cân nhắc việc một cùng loại event được publish từ nhiều nơi.

### 12.11. Lẫn event nội bộ với message broker

Spring **ApplicationEventPublisher** là phương tiện giao tiếp **trong cùng ứng dụng/context**, không tự có durable queue, consumer group, dead-letter, exactly-once hay giao nhận qua nhiều service. Nếu cần giao hàng qua tiến trình khác hoặc chống mất event khi crash, dùng messaging/outbox phù hợp.

### 12.12. Listener làm quá nhiều việc

Khi một method vừa truy cập database, vừa gửi HTTP, vừa cache và cập nhật nhiều hệ thống, nó khó test và khó xử lý failure. Giữ method **@EventListener** như adapter mỏng; chuyển logic phức tạp sang service có hợp đồng rõ ràng, giới hạn side effect và phân biệt task cần đồng bộ với task có thể trì hoãn.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Một object được tạo bằng **new OrderEventHandlers()**, chứa method **@EventListener**, có tự nhận event của Spring không?

**Đáp án:** Không. Object phải được quản lý/đăng ký với ApplicationContext và method phải được phát hiện để trở thành listener.

**Câu 2.** Có bắt buộc custom event extends **ApplicationEvent** không?

**Đáp án:** Không. Spring hỗ trợ publish object/record thông thường làm event; framework có thể dùng PayloadApplicationEvent ở tầng hạ tầng.

**Câu 3.** Một method **@EventListener** trả về **ImportantOrder** trong chế độ đồng bộ. Giá trị đó có ý nghĩa gì?

**Đáp án:** Nó được Spring publish như một event tiếp theo, để listener khác có thể xử lý.

**Câu 4.** Muốn chỉ xử lý OrderPlaced có priority từ 5 trở lên, điều kiện nào không lệ thuộc tên tham số khi biên dịch?

**Đáp án:** **@EventListener(condition = "#a0.priority() >= 5")**, với **#a0** là đối số đầu tiên.

**Câu 5.** Một listener có **@Order(10)** và listener khác có **@Order(20)**. Thứ tự hoàn thành có luôn được bảo đảm nếu cả hai dùng **@Async**?

**Đáp án:** Không. @Order hỗ trợ thứ tự dispatch nhưng không bảo đảm lịch trình và thời gian hoàn thành của các tác vụ chạy song song.

**Câu 6.** Có nên dùng @EventListener của một @Component để nhận **ApplicationStartingEvent** của lần chạy đầu tiên?

**Đáp án:** Không. Event xảy ra trước khi context và bean listener tồn tại. Đăng ký listener trước run bằng SpringApplication hoặc cơ chế bootstrap thích hợp.

**Câu 7.** Tại sao một listener gọi external API lâu có thể làm publishEvent chậm?

**Đáp án:** Vì multicaster mặc định gọi listener đồng bộ trong thread bên publish; publishEvent chờ callback hoàn tất.

**Câu 8.** **@TransactionalEventListener** mặc định chạy khi nào?

**Đáp án:** Sau khi transaction liên quan commit thành công (**AFTER_COMMIT**). Nếu không có transaction thì mặc định không chạy.

**Câu 9.** Unit test gọi trực tiếp Java method của handler có kiểm tra được Spring đã đăng ký @EventListener không?

**Đáp án:** Không. Cần context/integration test tạo bean rồi publish event qua Spring để xác minh registration và dispatch.

**Câu 10.** Nếu gửi sự kiện nội bộ khi một đơn hàng được tạo, event có tự được lưu bền vững để chạy lại sau crash không?

**Đáp án:** Không. ApplicationEventPublisher mặc định là cơ chế in-process; muốn bảo đảm giao nhận bền vững cần kiến trúc messaging/outbox phù hợp.

## 14. Tổng kết và tài liệu tham khảo

**@EventListener là cách khai báo listener gọn trên method của một Spring-managed bean.** Spring phát hiện method, chọn event theo kiểu tham số/annotation, có thể lọc với SpEL, sắp xếp dispatch bằng @Order và publish event kế tiếp từ giá trị trả về ở chế độ đồng bộ. Kỹ thuật này đặc biệt phù hợp cho domain event nội bộ và những Spring application event đến khi bean listener đã được đăng ký.

Nhớ phân biệt **event sớm trước ApplicationContext** với **event sau refresh**; hiểu **mặc định đồng bộ**, giới hạn **@Async**, semantics **@TransactionalEventListener**, phạm vi context và ranh giới giữa event nội bộ với message broker. Listener càng ít phụ thuộc không cần thiết, càng dễ kiểm thử và vận hành.

Tài liệu chính thức:

- Spring Framework — Application Events, Annotation-based Event Listeners, Asynchronous Listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework 6.1 — @EventListener API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.1 — ApplicationEventPublisher API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Boot 3.3 — SpringApplication, Application Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html