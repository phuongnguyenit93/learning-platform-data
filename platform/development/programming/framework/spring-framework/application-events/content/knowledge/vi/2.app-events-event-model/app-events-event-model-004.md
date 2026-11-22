# Quan hệ giữa ApplicationContext và event bus

Trong Spring Framework, **ApplicationContext** vừa là container quản lý bean và vòng đời ứng dụng, vừa là điểm công bố application event. Một service có thể phát sự kiện thông qua **ApplicationEventPublisher** mà không cần biết có bao nhiêu listener đang lắng nghe. Phần điều phối sự kiện được thực hiện bên trong context thông qua **ApplicationEventMulticaster**.

Trong bài này, “event bus” là cách gọi mô tả cơ chế phát và phân phối sự kiện nội bộ của Spring. Nó không phải một message broker độc lập như Kafka hay RabbitMQ.

## 1. Các thành phần và mối quan hệ

### ApplicationContext

**ApplicationContext** là interface trung tâm của Spring container. Ngoài khả năng tra cứu bean, quản lý tài nguyên, message source và vòng đời context, interface này còn kế thừa **ApplicationEventPublisher**. Vì vậy, một ApplicationContext có thể nhận lời gọi publish event và chuyển sự kiện tới hệ thống listener.

Một ứng dụng thường có một context chính; ứng dụng web có thể có context gốc và context con. Mỗi context có hạ tầng event riêng, có thể liên hệ với context cha theo quy tắc phân cấp.

### ApplicationEventPublisher

**ApplicationEventPublisher** là hợp đồng công bố sự kiện. Code nghiệp vụ chỉ cần phụ thuộc vào interface này:

- Gọi publishEvent(event) để thông báo một sự kiện đã xảy ra.
- Không cần tìm listener, gọi listener trực tiếp hoặc biết listener nằm ở module nào.
- Có thể phát một đối tượng sự kiện kế thừa ApplicationEvent hoặc một đối tượng Java thông thường.

Nên inject ApplicationEventPublisher vào service thay vì inject toàn bộ ApplicationContext nếu service chỉ cần phát event. Cách này giảm phụ thuộc vào container và làm ý định của code rõ ràng hơn.

### ApplicationEventMulticaster

**ApplicationEventMulticaster** là thành phần phân phối event tới các listener đã đăng ký trong context. Nó chịu trách nhiệm lựa chọn listener phù hợp với kiểu sự kiện và gọi listener.

Nếu ứng dụng không khai báo bean tên **applicationEventMulticaster**, Spring tạo một **SimpleApplicationEventMulticaster** mặc định cho context. Ứng dụng có thể tự khai báo bean cùng tên để cấu hình cách phân phối, chẳng hạn cung cấp task executor hoặc error handler.

Multicaster là phần thực hiện việc dispatch. Publisher là API để gửi event; ApplicationContext kết nối API đó với multicaster.

### Event và listener

**Event** là dữ liệu mô tả một điều đã xảy ra, ví dụ đơn hàng đã được tạo hoặc hồ sơ đã được duyệt. Event nên có tên thể hiện sự kiện trong quá khứ và dữ liệu cần thiết để listener xử lý.

Có hai cách phổ biến để đăng ký listener:

- **ApplicationListener**: triển khai interface và xử lý một loại ApplicationEvent. Đây là cách dùng quen thuộc trong các ứng dụng hoặc API Spring cũ.
- **@EventListener**: đánh dấu một phương thức trong bean Spring. Kiểu tham số của phương thức cho biết loại event mà phương thức nhận.

Từ Spring Framework 4.2, có thể publish một POJO thông thường mà không cần kế thừa ApplicationEvent. Khi publish một object thông thường, Spring biểu diễn nó bằng PayloadApplicationEvent ở tầng event; listener có thể khai báo trực tiếp kiểu payload cần nhận.

## 2. Luồng phát và phân phối event

Luồng xử lý cơ bản:

1. Một bean nghiệp vụ gọi ApplicationEventPublisher.publishEvent(event).
2. ApplicationContext tiếp nhận event và chuyển yêu cầu tới ApplicationEventMulticaster của chính context đó.
3. Multicaster tìm các listener phù hợp với kiểu event.
4. Các listener được gọi theo cơ chế thực thi đã cấu hình.
5. Mỗi listener tự thực hiện phản ứng của mình; publisher không cần gọi trực tiếp từng listener.

Ví dụ, OrderService phát OrderCreated. Một listener có thể gửi email, listener khác có thể cập nhật chỉ số hoặc ghi audit. OrderService chỉ chịu trách nhiệm công bố sự kiện đơn hàng đã được tạo.

### Đăng ký listener trong vòng đời context

Khi context được refresh, Spring khởi tạo event multicaster và đăng ký các listener. Các bean triển khai ApplicationListener được nhận diện trong quá trình này. Với phương thức có @EventListener, Spring dùng bộ xử lý annotation để phát hiện phương thức và đăng ký adapter tương ứng với multicaster.

Do đó, một class có @EventListener nhưng không được tạo thành bean trong context sẽ không tự động nhận event. Listener phải thuộc phạm vi quản lý của Spring, ví dụ được khai báo bằng @Bean hoặc được component scan phát hiện.

### Kiểu event và điều kiện nhận

Listener chỉ nhận những event tương thích với kiểu mà nó khai báo. Với @EventListener, kiểu tham số của phương thức là căn cứ quan trọng để Spring xác định event cần chuyển tới. Có thể dùng thuộc tính condition của @EventListener để lọc thêm bằng biểu thức SpEL khi cần.

Nếu nhiều listener cùng nhận một event, Spring gọi từng listener đã đăng ký. Có thể dùng @Order hoặc interface Ordered để chỉ định thứ tự khi thứ tự xử lý thực sự có ý nghĩa. Không nên dựa vào thứ tự ngẫu nhiên hoặc thứ tự đăng ký tình cờ.

## 3. Đồng bộ, bất đồng bộ và xử lý lỗi

### Mặc định là đồng bộ

**SimpleApplicationEventMulticaster mặc định gọi listener đồng bộ trên thread đang publish event.** Điều này có một số hệ quả:

- Lệnh publishEvent chỉ hoàn tất sau khi các listener đồng bộ được gọi xong.
- Listener chạy lâu sẽ làm chậm luồng nghiệp vụ phát event.
- Listener có thể đọc được dữ liệu nằm trong cùng execution context, nhưng cũng có thể làm tăng độ trễ của request.
- Ngoại lệ từ listener có thể truyền ngược về nơi publish event nếu không có error handler xử lý.

Vì vậy, không nên giả định rằng chỉ cần publish event là tác vụ đã chạy nền. Event trong Spring mặc định không tự tạo thread mới.

### Cấu hình bất đồng bộ

Có thể cấu hình executor cho bean SimpleApplicationEventMulticaster tên applicationEventMulticaster bằng setTaskExecutor, hoặc dùng cơ chế @Async cho listener và bật xử lý async tương ứng. Khi chuyển sang bất đồng bộ, cần cân nhắc:

- Listener có thể chạy trên thread khác và hoàn tất sau khi publisher đã trả về.
- Thứ tự hoàn tất giữa các listener không còn là thứ tự đồng bộ ban đầu.
- Dữ liệu dùng chung phải an toàn khi truy cập đồng thời.
- Ngoại lệ trong tác vụ async cần được quan sát và xử lý riêng; caller thường không nhận trực tiếp ngoại lệ đó.
- Không truyền các đối tượng phụ thuộc vào request thread hoặc transaction thread sang executor nếu chúng không an toàn khi dùng ở thread khác.

Chỉ bật async khi có lý do về độ trễ hoặc tải xử lý. Nếu cần kết quả listener trước khi tiếp tục nghiệp vụ, xử lý đồng bộ hoặc gọi service trực tiếp thường phù hợp hơn.

### Event gắn với transaction

Nếu listener chỉ được chạy khi transaction đã commit hoặc rollback, có thể dùng **@TransactionalEventListener**. Mặc định, listener này gắn với phase AFTER_COMMIT. Nó hữu ích khi cần phản ứng sau khi dữ liệu đã được commit, ví dụ gửi thông báo sau khi tạo đơn hàng thành công.

Cần có transaction đang hoạt động tại thời điểm publish event để listener được gắn với transaction đó. Nếu muốn listener vẫn chạy khi không có transaction, có thể cân nhắc fallbackExecution, nhưng chỉ bật khi hành vi đó đúng với nghiệp vụ. @TransactionalEventListener không biến event nội bộ thành thông điệp bền vững; nó vẫn thuộc cơ chế event trong process.

## 4. Ví dụ chạy được với Java 17 và Spring Framework

Ví dụ dưới đây tạo một ApplicationContext, inject ApplicationEventPublisher vào OrderService và đăng ký listener bằng @EventListener. Event là record Java thông thường, không kế thừa ApplicationEvent.

### Cấu trúc thư mục

~~~text
application-event-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventDemo.java
~~~

### pom.xml

Ví dụ dùng Spring Framework 6.2.0 và Java 17. Dependency spring-context cung cấp ApplicationContext, annotation cấu hình và event infrastructure.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-event-demo</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### ApplicationEventDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationEventDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService orderService = context.getBean(OrderService.class);
            orderService.placeOrder("DH-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void placeOrder(String orderId) {
            System.out.println("Đã tạo đơn hàng: " + orderId);
            publisher.publishEvent(new OrderCreated(orderId));
        }
    }

    public record OrderCreated(String orderId) {
    }

    public static class OrderCreatedListener {

        @EventListener
        public void onOrderCreated(OrderCreated event) {
            System.out.println("Nhận OrderCreated: " + event.orderId());
        }
    }
}
~~~

### Biên dịch và chạy

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ApplicationEventDemo
~~~

Kết quả stdout:

~~~text
Đã tạo đơn hàng: DH-1001
Nhận OrderCreated: DH-1001
~~~

Dòng đầu tiên được in trong OrderService. Sau đó publishEvent chuyển OrderCreated qua context tới listener. Vì multicaster mặc định đồng bộ, listener chạy ngay trong luồng gọi placeOrder và in dòng thứ hai trước khi phương thức kết thúc.

Điểm cần quan sát trong ví dụ:

- OrderService chỉ phụ thuộc vào ApplicationEventPublisher.
- AppConfig tạo OrderService và listener thành bean trong cùng context.
- OrderCreated là record bất biến, chỉ chứa mã đơn hàng cần cho listener.
- OrderCreatedListener không được OrderService gọi trực tiếp; Spring tìm và gọi phương thức @EventListener.
- Đóng context bằng try-with-resources giúp kết thúc vòng đời context rõ ràng.

## 5. Quan hệ giữa context cha và context con

ApplicationContext hỗ trợ cấu trúc phân cấp. Khi một context con publish event, event được multicaster của context con xử lý và Spring cũng chuyển tiếp event lên context cha. Chiều truyền này đi từ con lên cha; event được publish ở context cha không tự động truyền xuống các context con.

Điều này hữu ích trong ứng dụng có nhiều context, nhưng cũng cần tránh đăng ký listener ở cả cha và con nếu cùng một event có thể khiến một xử lý bị thực hiện hai lần. Khi thiết kế listener, hãy xác định bean thuộc context nào và event được phát từ context nào.

## 6. Khi nào nên dùng event bus của Spring?

Phù hợp khi các thành phần trong cùng một ứng dụng cần phản ứng với một sự kiện mà không muốn publisher phụ thuộc trực tiếp vào từng thành phần nhận. Ví dụ:

- Sau khi tạo đơn hàng, gửi email xác nhận và ghi audit.
- Sau khi cập nhật hồ sơ, làm mới một cache nội bộ.
- Sau khi hoàn tất một thao tác nghiệp vụ, cập nhật số liệu hoặc phát thông báo trong ứng dụng.
- Tách các phản ứng phụ khỏi luồng chính để module nghiệp vụ ít phụ thuộc lẫn nhau hơn.

Không nên xem event bus của ApplicationContext như hệ thống truyền thông điệp phân tán. Event nội bộ không tự được lưu bền vững, không có lịch sử để replay sau khi ứng dụng khởi động lại và không tự bảo đảm giao nhận giữa nhiều process hoặc service. Nếu nghiệp vụ yêu cầu retry, lưu trữ, replay, consumer độc lập hoặc truyền tin giữa service, hãy dùng message broker phù hợp và cân nhắc Transactional Outbox để đồng bộ việc commit dữ liệu với việc phát thông điệp.

## 7. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Inject ApplicationContext chỉ để publish event | Service phụ thuộc vào container rộng hơn nhu cầu | Inject ApplicationEventPublisher |
| Nghĩ listener mặc định chạy nền | Request vẫn phải chờ listener hoàn tất | Cấu hình async có chủ đích nếu phù hợp |
| Dùng event nội bộ thay cho broker | Không có độ bền và bảo đảm giao nhận phân tán | Dùng broker/outbox khi cần giao tiếp giữa process |
| Listener không phải bean Spring | Phương thức @EventListener không được đăng ký | Khai báo bean hoặc component scan |
| Event chứa entity mutable hoặc quá nhiều dữ liệu | Listener có thể phụ thuộc trạng thái thay đổi và khó kiểm soát | Ưu tiên event bất biến, chứa ID và dữ liệu cần thiết |
| Listener thực hiện tác vụ chậm trong luồng đồng bộ | Tăng độ trễ của nơi publish event | Đánh giá async hoặc tách tác vụ |
| Không xử lý ngoại lệ listener | Lỗi phụ có thể ảnh hưởng luồng phát event | Xác định chính sách error handling và logging |
| Dùng @TransactionalEventListener nhưng publish ngoài transaction | Listener theo phase transaction có thể không được gọi | Kiểm tra transaction boundary hoặc cấu hình fallbackExecution khi đúng nghiệp vụ |

## 8. Cách chọn API

| Nhu cầu | Cách dùng |
|---|---|
| Công bố event từ service | Inject ApplicationEventPublisher và gọi publishEvent |
| Xử lý event bằng một phương thức gọn | Dùng @EventListener trên bean |
| Tích hợp theo interface listener truyền thống | Triển khai ApplicationListener cho loại ApplicationEvent phù hợp |
| Chỉ xử lý sau khi transaction commit | Dùng @TransactionalEventListener với phase thích hợp |
| Cần dispatch async | Cấu hình executor cho multicaster hoặc dùng @Async đúng cách |
| Cần giao nhận bền vững giữa service | Dùng broker và thiết kế bảo đảm dữ liệu, chẳng hạn Transactional Outbox |

Quan hệ cốt lõi là: **ApplicationContext cung cấp khả năng publish event; ApplicationEventPublisher là hợp đồng mà code nghiệp vụ sử dụng; ApplicationEventMulticaster phân phối event; listener là các bean nhận và xử lý event.** Nhờ tách publisher khỏi listener, các module trong cùng ứng dụng có thể phối hợp qua sự kiện mà không cần biết chi tiết triển khai của nhau.