# Luồng phát và phân phối một event

Trong Spring Framework, event là một thông báo mô tả việc gì đó đã xảy ra trong ứng dụng. Thành phần phát event chỉ cần biết hợp đồng `ApplicationEventPublisher`; các listener đăng ký quan tâm đến loại event tương ứng sẽ nhận và xử lý thông báo. Cơ chế này giúp tách nơi phát sinh sự kiện khỏi các tác vụ phản ứng với sự kiện.

Ví dụ, `OrderService` hoàn tất việc tạo đơn hàng rồi phát `OrderCreatedEvent`. Những thành phần như gửi email, ghi audit hoặc cập nhật thống kê có thể lắng nghe event đó mà `OrderService` không cần gọi trực tiếp từng thành phần.

Sau bài học, bạn có thể:

- Mô tả đường đi của một event từ publisher đến các listener.
- Phân biệt `ApplicationEventPublisher`, `ApplicationEventMulticaster`, `ApplicationListener` và `@EventListener`.
- Giải thích cách Spring chọn listener phù hợp và hành vi đồng bộ mặc định.
- Nhận biết khi nào cần xử lý bất đồng bộ hoặc gắn listener với transaction.

## 1. Các thành phần trong mô hình phát event

| Thành phần | Vai trò |
|---|---|
| `ApplicationEventPublisher` | Hợp đồng để phát một event vào Spring application context. |
| `ApplicationContext` | Cung cấp `ApplicationEventPublisher` và quản lý vòng đời các listener là bean. |
| Event object | Mang thông tin về việc đã xảy ra, ví dụ mã đơn hàng và thời điểm tạo. |
| `ApplicationEventMulticaster` | Điều phối việc phân phối event đến các listener phù hợp. |
| `ApplicationListener<E>` | Listener triển khai interface để nhận event có kiểu `E`. |
| `@EventListener` | Đánh dấu một method của Spring bean là listener. |

### Publisher

`ApplicationEventPublisher` là điểm vào để phát event. Thông thường, service nhận publisher qua constructor injection:

~~~java
public class OrderService {
    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

`ApplicationContext` cung cấp hợp đồng publisher, vì vậy service không cần tự tìm hoặc gọi từng listener. Cách inject interface này cũng giúp service dễ kiểm thử hơn.

Có thể phát event bằng:

~~~java
publisher.publishEvent(event);
~~~

Phương thức `publishEvent(Object event)` cho phép phát một object bất kỳ. Nếu object chưa kế thừa `ApplicationEvent`, Spring bọc nó trong `PayloadApplicationEvent` trước khi phân phối. Cơ chế này hỗ trợ các event dạng POJO hoặc Java record, không bắt buộc tạo lớp kế thừa framework.

### Event object

Event nên mang dữ liệu cần thiết để listener hiểu việc gì đã xảy ra. Với event dạng POJO, có thể dùng record bất biến:

~~~java
public record OrderCreatedEvent(String orderId) {}
~~~

Một event kiểu cũ có thể kế thừa `ApplicationEvent`:

~~~java
public final class LegacyOrderCreatedEvent extends ApplicationEvent {
    private final String orderId;

    public LegacyOrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

`ApplicationEvent` lưu `source`, tức đối tượng phát sinh event. Với POJO event, hãy đưa các thông tin cần thiết trực tiếp vào payload. Nên ưu tiên dữ liệu bất biến và đủ dùng; tránh đưa một entity mutable lớn vào event nếu listener chỉ cần vài trường.

### Listener

Có hai cách phổ biến để đăng ký listener:

- Triển khai `ApplicationListener<E>` và cài đặt `onApplicationEvent(E event)`.
- Đánh dấu method trong một Spring bean bằng `@EventListener`.

Ví dụ với annotation:

~~~java
@Component
public class OrderCreatedListener {
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }
}
~~~

Bean phải được Spring quản lý để method được phát hiện. Trong lúc khởi tạo application context, Spring tìm các method có `@EventListener` và đăng ký chúng vào cơ chế phân phối event. Một bean có thể có nhiều listener method; nhiều bean cũng có thể cùng lắng nghe một loại event.

Cách triển khai interface vẫn hữu ích khi muốn biểu diễn listener bằng một bean chuyên biệt hoặc cần hợp đồng kiểu rõ ràng:

~~~java
public class AuditListener implements ApplicationListener<OrderCreatedEvent> {
    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Ghi nhận mã đơn hàng vào audit log.
    }
}
~~~

## 2. Luồng phát và phân phối một event

Khi một service gọi `publishEvent(event)`, Spring thực hiện luồng xử lý khái quát sau:

1. **Tạo event:** Thành phần nghiệp vụ tạo object chứa dữ liệu mô tả sự kiện, chẳng hạn `OrderCreatedEvent("ORD-1001")`.
2. **Phát event:** Service gọi `ApplicationEventPublisher.publishEvent(event)`. Service không cần biết có bao nhiêu listener đang đăng ký.
3. **Chuẩn hóa event:** Nếu object đã là `ApplicationEvent`, Spring sử dụng event đó. Nếu là object thông thường, Spring bọc object trong `PayloadApplicationEvent`.
4. **Chuyển đến multicaster:** Application context chuyển event cho `ApplicationEventMulticaster` để phân phối.
5. **Tìm listener phù hợp:** Multicaster chọn các listener có kiểu event tương thích. Listener cho một lớp cha hoặc interface có thể nhận event của lớp con phù hợp; Spring cũng hỗ trợ phân giải kiểu generic của listener.
6. **Gọi listener:** Mỗi listener phù hợp được gọi theo execution model đang cấu hình. Với cấu hình mặc định, listener chạy đồng bộ trên thread phát event.
7. **Lan truyền lên context cha:** Nếu context hiện tại có parent context, event được chuyển tiếp lên context cha để các listener ở đó cũng có thể nhận event phù hợp.

Sơ đồ rút gọn:

~~~mermaid
flowchart TD
    A["Service / Publisher"] --> B["publishEvent(event)"]
    B --> C["ApplicationContext"]
    C --> D["Chuẩn hóa event nếu cần"]
    D --> E["ApplicationEventMulticaster"]
    E --> F{"Tìm listener theo kiểu event"}
    F -->|Phù hợp| G["Listener A"]
    F -->|Phù hợp| H["Listener B"]
    F -->|Không có listener| I["Không có listener xử lý"]
    G --> J["Hoàn tất phân phối"]
    H --> J
~~~

Một event có thể được chuyển đến nhiều listener. Các listener được chọn dựa trên kiểu event và điều kiện đăng ký; Spring không gửi mọi event cho mọi bean trong context.

### Vai trò của ApplicationEventMulticaster

`ApplicationEventMulticaster` là thành phần điều phối việc gọi listener. Trong application context thông thường, Spring sử dụng `SimpleApplicationEventMulticaster` mặc định nếu ứng dụng không cung cấp bean multicaster riêng có tên `applicationEventMulticaster`.

Multicaster chịu trách nhiệm lấy danh sách listener phù hợp và gọi chúng. Nó không thay thế logic nghiệp vụ của listener, không lưu lịch sử event và cũng không tự tạo cơ chế retry bền vững.

## 3. Ví dụ chạy được với Spring Framework

Ví dụ dưới đây dùng Java 17 và Spring Context 6.2.0. Ứng dụng tạo một context, đăng ký service và listener, sau đó phát event khi tạo đơn hàng.

Cấu trúc thư mục:

~~~text
spring-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventsDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-events-demo</artifactId>
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
                    <mainClass>demo.ApplicationEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/ApplicationEventsDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderService.class).placeOrder("ORD-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }

    record OrderCreatedEvent(String orderId) {}

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void placeOrder(String orderId) {
            System.out.println("Saving order " + orderId);
            publisher.publishEvent(new OrderCreatedEvent(orderId));
            System.out.println("Publisher continues");
        }
    }

    static class OrderCreatedListener {

        @EventListener
        public void onOrderCreated(OrderCreatedEvent event) {
            System.out.println("Listener received: " + event.orderId());
        }
    }
}
~~~

Chạy tại thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Kết quả stdout:

~~~text
Saving order ORD-1001
Listener received: ORD-1001
Publisher continues
~~~

Dòng `Listener received` xuất hiện trước `Publisher continues` vì listener chạy đồng bộ theo cấu hình mặc định. Khi `publishEvent` gọi xong, listener đồng bộ đã xử lý xong trước khi service chạy câu lệnh tiếp theo.

Ví dụ dùng POJO record làm event, vì vậy không cần kế thừa `ApplicationEvent`. `OrderService` chỉ biết publisher và event type; nó không phụ thuộc vào `OrderCreatedListener`. Có thể thêm listener gửi email hoặc ghi audit mà không cần sửa luồng phát event của service.

## 4. Đồng bộ, thứ tự và bất đồng bộ

### Đồng bộ là mặc định

`SimpleApplicationEventMulticaster` gọi listener trực tiếp trên thread đang phát event nếu không cấu hình executor. Điều này có một số hệ quả:

- `publishEvent` thường chỉ trả về sau khi các listener đồng bộ hoàn tất.
- Listener chạy lâu sẽ kéo dài thời gian xử lý của publisher.
- Exception từ listener có thể truyền ngược về nơi gọi. Với cấu hình mặc định không có `ErrorHandler`, exception có thể làm dừng lượt phân phối trước khi các listener tiếp theo được gọi.

Vì vậy, listener đồng bộ nên thực hiện công việc ngắn, có thời gian xử lý dự đoán được và xử lý lỗi phù hợp với nghiệp vụ.

### Thứ tự listener

Có thể dùng `@Order` hoặc interface `Ordered` để chỉ định thứ tự listener. Giá trị order nhỏ hơn có độ ưu tiên cao hơn:

~~~java
@EventListener
@Order(1)
public void updateInventory(OrderCreatedEvent event) {
    // Xử lý trước.
}

@EventListener
@Order(2)
public void writeAuditLog(OrderCreatedEvent event) {
    // Xử lý sau.
}
~~~

Thứ tự này hữu ích khi các listener đồng bộ cần chạy theo một trình tự xác định. Nếu listener chạy bất đồng bộ, thứ tự được lên lịch không đồng nghĩa với thứ tự hoàn tất; các tác vụ có thể kết thúc theo thời gian khác nhau.

### Bất đồng bộ

Nếu một listener thực hiện tác vụ chậm như gửi email hoặc gọi dịch vụ bên ngoài, có thể cấu hình chạy bất đồng bộ. Một cách thường dùng là bật async processing và đánh dấu listener bằng `@Async`:

~~~java
@Configuration
@EnableAsync
class AsyncConfiguration {
}

@Component
class AsyncOrderListener {

    @Async
    @EventListener
    public void sendConfirmation(OrderCreatedEvent event) {
        // Gửi email hoặc thực hiện tác vụ tốn thời gian.
    }
}
~~~

Cần bật `@EnableAsync` trong cấu hình Spring và bảo đảm listener là Spring bean. Có thể cấu hình executor phù hợp để kiểm soát thread pool. Một lựa chọn khác là cung cấp `SimpleApplicationEventMulticaster` tùy chỉnh với task executor để điều phối listener qua executor.

Khi chạy bất đồng bộ:

- Publisher có thể tiếp tục trước khi listener hoàn tất.
- Không nên dựa vào thứ tự hoàn tất của các listener.
- Exception xảy ra trong thread xử lý bất đồng bộ không truyền ngược về thread đã gọi `publishEvent` như trường hợp đồng bộ.
- Cần quản lý executor, giới hạn hàng đợi, log và xử lý lỗi để tránh quá tải hoặc mất khả năng quan sát.

Chỉ bật async khi nghiệp vụ cho phép xử lý tách khỏi luồng phát event. Nếu tác vụ phải hoàn tất trước khi trả kết quả cho người gọi, hãy giữ xử lý đồng bộ hoặc dùng một cơ chế phối hợp kết quả rõ ràng.

## 5. Event và transaction

`@EventListener` thông thường được gọi tại thời điểm event được phát. Nếu publisher phát event bên trong một transaction, listener đồng bộ vẫn có thể chạy trước khi transaction commit. Nếu transaction rollback sau đó, các tác động mà listener đã thực hiện không tự động được hoàn tác.

Khi cần xử lý theo vòng đời transaction, dùng `@TransactionalEventListener`. Ví dụ:

~~~java
@Component
class OrderAfterCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterOrderCommitted(OrderCreatedEvent event) {
        // Chỉ thực hiện sau khi transaction commit thành công.
    }
}
~~~

`AFTER_COMMIT` là phase mặc định của `@TransactionalEventListener`. Listener kiểu này cần transaction đang hoạt động tại thời điểm phát event; nếu không có transaction, listener mặc định không được gọi, trừ khi bật `fallbackExecution = true`.

Các phase khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Chọn phase dựa trên thời điểm mà nghiệp vụ cần phản ứng. Annotation này thuộc Spring transaction support, vì vậy ứng dụng cần cấu hình transaction infrastructure và dependency tương ứng.

Lưu ý: `@TransactionalEventListener` không biến event thành thông điệp bền vững. Nếu tiến trình dừng đột ngột hoặc cần chuyển thông điệp giữa nhiều service, hãy cân nhắc transactional outbox hoặc message broker phù hợp.

## 6. Context cha và context con

Trong cấu trúc application context phân cấp, event được phát từ context con có thể được chuyển tiếp lên context cha. Vì vậy, listener ở context cha có thể nhận event do context con phát ra nếu kiểu event phù hợp.

Chiều ngược lại không tự động xảy ra: event được phát ở context cha không được phân phối xuống các context con. Khi thiết kế ứng dụng có nhiều context, cần xác định nơi đăng ký listener để tránh hiểu nhầm phạm vi nhận event.

## 7. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Hệ quả | Cách xử lý |
|---|---|---|
| Listener không phải Spring bean | Method có `@EventListener` không được đăng ký. | Đăng ký bean bằng component scanning hoặc `@Bean`. |
| Kiểu tham số listener không tương thích event | Listener không được chọn để nhận event. | Kiểm tra chính xác event type, superclass và generic type. |
| Nghĩ rằng phát event sẽ lưu lại lịch sử | Listener đăng ký sau không nhận lại event cũ. | Dùng persistence hoặc message broker nếu cần lưu và phát lại. |
| Nghĩ rằng mọi listener luôn chạy async | Công việc chậm vẫn chặn publisher trong cấu hình mặc định. | Cấu hình `@Async` hoặc task executor khi phù hợp. |
| Dùng listener async nhưng trông chờ exception truyền về publisher | Publisher không nhận được exception từ thread xử lý async. | Thiết lập cơ chế xử lý lỗi và logging cho async task. |
| Phát event trong transaction rồi gửi side effect ngay | Side effect có thể xảy ra dù transaction sau đó rollback. | Dùng `@TransactionalEventListener` với phase phù hợp. |
| Chia sẻ object mutable giữa nhiều listener | Listener có thể nhìn thấy dữ liệu đã bị listener khác thay đổi. | Ưu tiên event bất biến và chỉ chứa dữ liệu cần thiết. |
| Tạo chuỗi event lặp vô hạn | Listener phát event khác khiến luồng xử lý quay lại chính nó. | Xác định rõ điều kiện dừng và tránh vòng phụ thuộc giữa listener. |

## 8. Khi nào nên dùng application event?

Application event phù hợp khi một thành phần trong cùng ứng dụng cần thông báo một sự kiện nghiệp vụ cho nhiều thành phần khác mà không phụ thuộc trực tiếp vào chúng. Ví dụ:

- Đơn hàng được tạo: gửi thông báo, ghi audit, cập nhật thống kê.
- Người dùng đăng ký: khởi tạo hồ sơ phụ hoặc gửi email chào mừng.
- Tệp được xử lý xong: cập nhật trạng thái và phát thông báo cho thành phần liên quan.

Không nên xem application event như một message broker. Cơ chế này chủ yếu phục vụ giao tiếp trong cùng Spring application context; nó không mặc định cung cấp lưu trữ bền vững, retry, xác nhận giao nhận hoặc truyền thông điệp qua mạng.

## 9. Checklist kiểm tra luồng event

Khi triển khai một luồng event, hãy tự kiểm tra:

1. Event có tên và payload thể hiện rõ việc đã xảy ra không?
2. Publisher có nhận `ApplicationEventPublisher` qua dependency injection không?
3. Listener có được đăng ký thành Spring bean không?
4. Kiểu event mà listener nhận có khớp với object được phát không?
5. Công việc cần chạy đồng bộ hay có thể chạy bất đồng bộ?
6. Exception từ listener được ghi nhận và xử lý ở đâu?
7. Nếu event được phát trong transaction, listener cần chạy ở phase nào?
8. Có cần lưu event, retry hoặc truyền sang service khác không? Nếu có, application event đơn thuần có thể chưa đáp ứng yêu cầu.

Điểm cốt lõi của luồng này là publisher phát một object thông qua `ApplicationEventPublisher`; application context chuyển object đến `ApplicationEventMulticaster`; multicaster chọn listener theo kiểu event rồi gọi chúng theo cấu hình thực thi. Hiểu rõ bước chọn listener và chế độ đồng bộ/bất đồng bộ giúp dự đoán chính xác thứ tự xử lý, thời điểm exception xuất hiện và mối quan hệ giữa event với transaction.
