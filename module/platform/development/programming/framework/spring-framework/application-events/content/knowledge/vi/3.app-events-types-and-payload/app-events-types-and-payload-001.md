# ApplicationEvent và lớp con tùy biến

## 1. Application Events trong Spring

Application Events là cơ chế publish/subscribe nội bộ của Spring. Một thành phần phát ra sự kiện để thông báo rằng một việc đã xảy ra; những thành phần khác đăng ký lắng nghe và phản ứng với sự kiện đó. Bên phát không cần gọi trực tiếp từng listener, vì vậy các phần của ứng dụng ít phụ thuộc vào nhau hơn.

Trong Spring, ApplicationContext cũng triển khai ApplicationEventPublisher. Khi gọi publishEvent(...), sự kiện được chuyển tới cơ chế ApplicationEventMulticaster của context hiện tại, rồi được phân phối tới các listener phù hợp, chẳng hạn bean có phương thức gắn @EventListener hoặc lớp triển khai ApplicationListener.

Đây là cơ chế sự kiện trong cùng ứng dụng và cùng tiến trình. Nó không tự tạo hàng đợi bền vững, không gửi sự kiện sang tiến trình khác và không thay thế message broker như RabbitMQ hay Kafka.

## 2. ApplicationEvent là gì?

ApplicationEvent là lớp cơ sở trừu tượng của Spring, kế thừa java.util.EventObject. Lớp này cung cấp hai thông tin chính:

- source: đối tượng phát ra sự kiện. Có thể lấy qua getSource(). Giá trị source phải khác null.
- timestamp: thời điểm đối tượng sự kiện được khởi tạo, lấy qua getTimestamp() và biểu diễn bằng mili giây kể từ Unix epoch.

Một sự kiện tùy biến có thể kế thừa ApplicationEvent để mang dữ liệu nghiệp vụ có kiểu rõ ràng. Ví dụ, OrderCreatedEvent biểu diễn việc một đơn hàng đã được tạo và mang theo mã đơn cùng tổng tiền.

Tên sự kiện thường diễn tả một việc đã xảy ra, dùng thì quá khứ như OrderCreatedEvent, UserRegisteredEvent hoặc PaymentCompletedEvent. Event nên là dữ liệu mô tả sự kiện; phần xử lý nghiệp vụ thuộc về publisher hoặc listener.

Lưu ý: timestamp của ApplicationEvent là thời điểm tạo đối tượng event. Nếu nghiệp vụ cần thời điểm xảy ra chính xác theo domain, hãy truyền riêng một trường Instant occurredAt thay vì dùng timestamp thay thế cho thời gian nghiệp vụ.

## 3. Tạo lớp sự kiện tùy biến

Một lớp con thường có các đặc điểm:

1. Kế thừa ApplicationEvent.
2. Gọi super(source) trong constructor để khởi tạo nguồn sự kiện.
3. Khai báo các trường chứa dữ liệu cần thiết cho listener.
4. Giữ dữ liệu bất biến sau khi tạo event; dùng final và kiểm tra đầu vào.
5. Chỉ đưa vào event những dữ liệu listener cần. Tránh giữ tham chiếu tới toàn bộ ApplicationContext, service hoặc một object mutable lớn nếu không cần thiết.

Ví dụ dưới đây tạo event chứa mã đơn hàng và tổng tiền:

~~~java
import org.springframework.context.ApplicationEvent;

import java.math.BigDecimal;
import java.util.Objects;

public final class OrderCreatedEvent extends ApplicationEvent {
    private final String orderId;
    private final BigDecimal total;

    public OrderCreatedEvent(Object source, String orderId, BigDecimal total) {
        super(Objects.requireNonNull(source, "source"));
        this.orderId = Objects.requireNonNull(orderId, "orderId");
        this.total = Objects.requireNonNull(total, "total");
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Trong ví dụ, source là đối tượng phát sự kiện, còn orderId và total là payload nghiệp vụ. Việc dùng final giúp listener nhận được một snapshot ổn định của dữ liệu tại thời điểm event được tạo. Với collection, nên tạo bản sao bất biến, chẳng hạn List.copyOf(...), thay vì giữ một collection có thể bị thay đổi từ bên ngoài.

Không nên đưa các hành động như gửi email hoặc cập nhật database vào constructor của event. Constructor chỉ nên tạo dữ liệu sự kiện; listener mới thực hiện phản ứng tương ứng.

## 4. Phát sự kiện bằng ApplicationEventPublisher

Thành phần phát sự kiện có thể nhận ApplicationEventPublisher qua constructor injection. Khi nghiệp vụ đã đạt tới thời điểm cần thông báo, publisher gọi publishEvent(event):

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;

@Service
public class OrderService {
    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void createOrder(String orderId, BigDecimal total) {
        // Thực hiện kiểm tra và lưu đơn hàng tại đây.
        eventPublisher.publishEvent(
            new OrderCreatedEvent(this, orderId, total)
        );
    }
}
~~~

Dùng this làm source là một quy ước phổ biến khi service phát event. Nếu listener không cần biết publisher cụ thể, vẫn có thể dùng một source có ý nghĩa phù hợp với thiết kế. Không truyền null.

Nên phát event sau khi thao tác nghiệp vụ đã đạt tới trạng thái mà tên event mô tả. Ví dụ, chỉ phát OrderCreatedEvent sau khi đơn hàng đã được tạo thành công. Nếu phát quá sớm, listener có thể hành động dựa trên dữ liệu chưa tồn tại hoặc thao tác sau đó thất bại.

ApplicationEventPublisher là abstraction; service không cần phụ thuộc vào một implementation cụ thể của ApplicationContext. Điều này cũng giúp kiểm thử service bằng một publisher giả hoặc mock.

## 5. Lắng nghe sự kiện

Cách phổ biến là khai báo một bean Spring có phương thức gắn @EventListener. Kiểu tham số cho biết loại event mà phương thức nhận:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    @EventListener
    public void handle(OrderCreatedEvent event) {
        System.out.println(
            "Order " + event.getOrderId()
                + " created; total=" + event.getTotal()
        );
    }
}
~~~

Bean chứa listener phải được đăng ký trong ApplicationContext, ví dụ qua component scan, @Bean hoặc registerBean. Một phương thức Java thông thường không tự trở thành listener nếu đối tượng của nó không được Spring quản lý và xử lý annotation.

Spring chọn listener dựa trên kiểu event. Listener nhận một lớp cha có thể nhận cả các event thuộc lớp con tương ứng. Ví dụ, listener nhận ApplicationEvent có phạm vi rất rộng và có thể nhận nhiều event của framework lẫn event nghiệp vụ. Nên dùng kiểu event cụ thể để tránh xử lý nhầm sự kiện.

Ngoài @EventListener, có thể triển khai ApplicationListener<OrderCreatedEvent> và định nghĩa onApplicationEvent(...). Cách này thể hiện rõ quan hệ kiểu ở cấp lớp; @EventListener thường gọn hơn khi một bean cần lắng nghe nhiều loại event.

Nếu nhiều listener cần thứ tự gọi xác định, có thể dùng @Order. Tuy vậy, nên tránh để kết quả nghiệp vụ phụ thuộc vào thứ tự listener; khi các bước có quan hệ phụ thuộc, hãy điều phối chúng rõ ràng trong một service.

## 6. Ví dụ hoàn chỉnh có thể chạy

Ví dụ sau dùng Java 17 và Spring Framework 6.2.0. Chương trình tạo ApplicationContext, đăng ký listener, refresh context rồi phát một OrderCreatedEvent.

Tạo file src/main/java/demo/ApplicationEventDemo.java:

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;

import java.math.BigDecimal;
import java.util.Objects;

public class ApplicationEventDemo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(OrderCreatedListener.class);
            context.refresh();

            context.publishEvent(new OrderCreatedEvent(
                "order-service",
                "ORD-1001",
                new BigDecimal("125.50")
            ));
        }
    }

    public static final class OrderCreatedEvent extends ApplicationEvent {
        private final String orderId;
        private final BigDecimal total;

        public OrderCreatedEvent(
                Object source, String orderId, BigDecimal total) {
            super(Objects.requireNonNull(source, "source"));
            this.orderId = Objects.requireNonNull(orderId, "orderId");
            this.total = Objects.requireNonNull(total, "total");
        }

        public String getOrderId() {
            return orderId;
        }

        public BigDecimal getTotal() {
            return total;
        }
    }

    public static class OrderCreatedListener {
        @EventListener
        public void handle(OrderCreatedEvent event) {
            System.out.println(
                "Order " + event.getOrderId()
                    + " created; total=" + event.getTotal()
            );
        }
    }
}
~~~

Tạo file pom.xml ở thư mục gốc dự án:

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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ApplicationEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy tại thư mục có pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Kết quả stdout:

~~~text
Order ORD-1001 created; total=125.50
~~~

Luồng chạy:

1. AnnotationConfigApplicationContext được tạo.
2. OrderCreatedListener được đăng ký làm bean.
3. refresh() hoàn tất quá trình khởi tạo context và đăng ký xử lý @EventListener.
4. publishEvent(...) phát OrderCreatedEvent.
5. Listener có tham số OrderCreatedEvent được gọi và in mã đơn cùng tổng tiền.
6. try-with-resources đóng context khi chương trình kết thúc.

## 7. ApplicationEvent và payload object

Từ Spring Framework 4.2, publishEvent(...) nhận được cả đối tượng bất kỳ, không bắt buộc mọi event phải kế thừa ApplicationEvent. Với một object thông thường, Spring bọc nó trong PayloadApplicationEvent để đưa vào cơ chế phân phối sự kiện.

Ví dụ, nếu chỉ cần truyền dữ liệu đơn giản, có thể định nghĩa một record:

~~~java
import java.math.BigDecimal;

public record OrderCreatedPayload(String orderId, BigDecimal total) {
}
~~~

Publisher có thể gọi publishEvent(new OrderCreatedPayload(...)); listener có thể nhận trực tiếp OrderCreatedPayload làm tham số của phương thức @EventListener.

Nên chọn cách phù hợp với nhu cầu:

- Kế thừa ApplicationEvent khi cần một kiểu event tường minh, cần dùng source hoặc timestamp do lớp cơ sở cung cấp, hoặc muốn xây dựng hệ phân cấp event riêng.
- Dùng payload object hoặc record khi event chủ yếu là dữ liệu và không cần kế thừa ApplicationEvent. Cách này giảm mã constructor/getter và phù hợp với DTO bất biến.

Không cần kế thừa ApplicationEvent chỉ vì muốn Spring nhận diện một object là event. Điều quan trọng là publisher và listener thống nhất về kiểu dữ liệu và ý nghĩa của event.

## 8. Đồng bộ, bất đồng bộ và transaction

Mặc định, listener được gọi đồng bộ trên luồng phát sự kiện. Vì vậy, publishEvent(...) thường chỉ hoàn tất sau khi các listener đồng bộ đã xử lý xong. Listener chậm có thể làm chậm thao tác gọi publisher; exception từ listener cũng có thể ảnh hưởng tới lời gọi phát event nếu không cấu hình xử lý lỗi riêng.

Có thể chạy listener bất đồng bộ bằng @Async và bật @EnableAsync trong cấu hình Spring. Khi đó cần cấu hình executor, theo dõi lỗi ở luồng nền và tránh giả định rằng listener đã hoàn tất ngay sau publishEvent(...). Xử lý bất đồng bộ cũng làm thay đổi ngữ cảnh thread và cách truyền dữ liệu gắn với thread.

Khi listener cần đọc dữ liệu đã commit trong database, hãy cân nhắc @TransactionalEventListener. Mặc định, listener này chạy ở phase AFTER_COMMIT, tức sau khi transaction commit thành công. Nó cũng hỗ trợ các phase như BEFORE_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION. Nếu không có transaction đang hoạt động, listener mặc định không được gọi; chỉ bật fallbackExecution khi hành vi đó thực sự phù hợp.

Application Events không phải cơ chế lưu trữ sự kiện bền vững. Nếu ứng dụng dừng trước khi listener xử lý, Spring không tự lưu event để phát lại sau khi khởi động. Với yêu cầu retry, đảm bảo giao nhận hoặc giao tiếp giữa nhiều tiến trình, hãy dùng giải pháp messaging phù hợp; có thể kết hợp transactional outbox khi cần đồng bộ việc ghi database với việc phát message.

## 9. Lỗi thường gặp và cách tránh

- Quên gọi super(source): constructor của lớp cơ sở cần source hợp lệ. Hãy truyền một đối tượng có ý nghĩa và không null.
- Đưa quá ít dữ liệu vào event: listener phải gọi ngược publisher để lấy thông tin có thể làm tăng phụ thuộc. Hãy đưa các dữ liệu cần thiết vào event, nhưng tránh mang theo cả object graph lớn.
- Dùng payload mutable: listener này có thể làm thay đổi dữ liệu mà listener khác nhận được. Ưu tiên final field, record và bản sao bất biến của collection.
- Đặt tên event theo hành động tương lai: tên như SendEmailEvent dễ mô tả một lệnh hơn là sự kiện đã xảy ra. Dùng tên thể hiện sự thật đã xảy ra, chẳng hạn UserRegisteredEvent.
- Cho rằng event luôn bất đồng bộ: mặc định là đồng bộ. Muốn xử lý nền phải cấu hình async rõ ràng.
- Phát event trước khi transaction commit: listener có thể chạy khi dữ liệu chưa commit. Dùng @TransactionalEventListener với phase phù hợp nếu cần đồng bộ theo transaction.
- Dùng listener nhận ApplicationEvent cho mọi việc: kiểu quá rộng có thể bắt cả event hệ thống. Chọn lớp event cụ thể.
- Coi event nội bộ như message broker: event không tự có persistence, retry, consumer group hoặc bảo đảm giao nhận qua mạng.

## 10. Quy trình áp dụng

1. Xác định sự kiện nghiệp vụ đã xảy ra và thời điểm chính xác cần phát.
2. Tạo lớp event bất biến; kế thừa ApplicationEvent nếu cần source, timestamp hoặc hệ phân cấp kiểu.
3. Inject ApplicationEventPublisher vào thành phần phát sự kiện.
4. Đăng ký listener thành bean Spring và nhận đúng kiểu event.
5. Quyết định listener chạy đồng bộ, bất đồng bộ hay theo transaction.
6. Kiểm thử cả trường hợp event được phát, listener nhận đúng dữ liệu và lỗi listener được xử lý theo thiết kế.

Một event tốt mô tả rõ một sự thật đã xảy ra, chứa dữ liệu vừa đủ và không tự thực hiện hành động. Khi publisher và listener tuân theo quy ước đó, ApplicationEvent giúp tách các thành phần trong ứng dụng Spring mà vẫn giữ luồng xử lý dễ hiểu.