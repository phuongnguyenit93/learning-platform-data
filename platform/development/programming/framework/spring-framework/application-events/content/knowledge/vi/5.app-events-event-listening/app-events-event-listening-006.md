# Một phương thức nhận nhiều kiểu event

## 1. Khi nào cần một listener cho nhiều event?

Trong một ứng dụng Spring, nhiều loại sự kiện có thể cần kích hoạt cùng một phản ứng. Ví dụ, khi đơn hàng được tạo hoặc bị hủy, hệ thống đều cần ghi một dòng audit; khi tồn kho xuống thấp hoặc thanh toán thất bại, hệ thống đều cần phát cảnh báo vận hành.

Có thể viết một listener riêng cho từng loại event, nhưng nếu phần xử lý giống nhau thì mã sẽ bị lặp. Spring hỗ trợ một phương thức @EventListener nhận nhiều kiểu event. Có hai cách thiết kế thường gặp:

- Dùng một kiểu cha chung làm kiểu tham số của phương thức. Listener nhận được các event thuộc lớp con và có thể đọc dữ liệu từ event.
- Khai báo nhiều lớp event trực tiếp trong thuộc tính classes của @EventListener. Với nhiều lớp event, phương thức phải không có tham số; cách này phù hợp khi mọi event chỉ cần kích hoạt cùng một hành động chung.

Nên chọn cách dựa trên việc phần xử lý có cần đọc payload hay không và các event có quan hệ kiểu với nhau hay không.

## 2. Cách 1: Nhận kiểu cha chung của các event

Nếu các event có quan hệ kế thừa, hãy tạo một lớp cơ sở chứa dữ liệu chung. Phương thức listener nhận lớp cơ sở đó; Spring sẽ gọi phương thức cho các event có kiểu cụ thể kế thừa lớp cơ sở.

Ví dụ, OrderCreatedEvent và OrderCancelledEvent đều là một loại OrderEvent. Cả hai cùng mang orderId, vì vậy listener có thể xử lý chúng qua một tham số OrderEvent:

~~~java
import org.springframework.context.ApplicationEvent;

import java.util.Objects;

public abstract class OrderEvent extends ApplicationEvent {
    private final String orderId;

    protected OrderEvent(Object source, String orderId) {
        super(Objects.requireNonNull(source, "source"));
        this.orderId = Objects.requireNonNull(orderId, "orderId");
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Hai event cụ thể kế thừa lớp cơ sở:

~~~java
public final class OrderCreatedEvent extends OrderEvent {
    public OrderCreatedEvent(Object source, String orderId) {
        super(source, orderId);
    }
}

public final class OrderCancelledEvent extends OrderEvent {
    public OrderCancelledEvent(Object source, String orderId) {
        super(source, orderId);
    }
}
~~~

Listener chỉ cần một phương thức:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {
    @EventListener
    public void handle(OrderEvent event) {
        System.out.println(
            event.getClass().getSimpleName()
                + " for order " + event.getOrderId()
        );
    }
}
~~~

Khi Spring nhận OrderCreatedEvent hoặc OrderCancelledEvent, kiểu thực tế của event đều tương thích với tham số OrderEvent, nên cùng phương thức handle(...) được gọi. Phương thức có thể đọc dữ liệu chung qua getOrderId() và kiểm tra kiểu cụ thể khi thật sự cần hành vi khác nhau.

Có thể dùng một interface chung nếu thiết kế event phù hợp với interface đó. Tuy nhiên, nếu các event cần chia sẻ trạng thái hoặc constructor chung, một lớp cơ sở trừu tượng thường dễ diễn đạt hơn. Với event kế thừa ApplicationEvent, lớp cơ sở cũng có thể gom phần xử lý source và dữ liệu dùng chung.

Cách này thích hợp khi:

- Các event có cùng ý nghĩa ở mức domain hoặc có chung một hợp đồng dữ liệu.
- Listener cần đọc payload của event.
- Có thể biểu diễn quan hệ giữa các event bằng lớp cha hoặc interface.
- Muốn compiler kiểm tra kiểu dữ liệu, tránh ép kiểu thủ công.

Không nên tạo một lớp cha quá rộng chỉ để gom các event không liên quan. Kiểu cha nên phản ánh một khái niệm thật sự có ý nghĩa trong domain.

## 3. Cách 2: Khai báo nhiều kiểu bằng classes

Nếu các event không có kiểu cha chung phù hợp nhưng đều cần kích hoạt cùng một hành động, có thể liệt kê các lớp event trong thuộc tính classes:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OperationsNotifier {
    @EventListener(classes = {
        InventoryLowEvent.class,
        PaymentFailedEvent.class
    })
    public void notifyOperations() {
        System.out.println("An operational event was received");
    }
}
~~~

Trong ví dụ, InventoryLowEvent và PaymentFailedEvent có thể là hai kiểu dữ liệu độc lập. Khi một trong hai kiểu được publish, Spring đều gọi notifyOperations().

Thuộc tính value là alias của classes, vì vậy có thể viết ngắn:

~~~java
@EventListener({
    InventoryLowEvent.class,
    PaymentFailedEvent.class
})
public void notifyOperations() {
    // Phản ứng chung cho cả hai loại event.
}
~~~

Hai cách viết có cùng ý nghĩa. Dùng classes giúp người đọc hiểu rõ đây là danh sách kiểu event được phương thức xử lý.

**Quy tắc chữ ký phương thức trong Spring Framework 6.2:** nếu classes chỉ có một kiểu, phương thức có thể nhận một tham số tương ứng; nếu classes chứa nhiều kiểu, phương thức không được khai báo tham số. Spring cần danh sách kiểu trên annotation để xác định event nào kích hoạt phương thức, vì vậy không thể dùng một tham số có kiểu không tương thích với tất cả các event độc lập đó.

Do phương thức không nhận event làm tham số, nó phù hợp khi chỉ cần thực hiện một hành động chung, chẳng hạn xóa cache, tăng metric hoặc gửi tín hiệu đánh thức một quy trình. Nếu cần đọc dữ liệu riêng của từng event, hãy dùng kiểu cha chung như cách 1 hoặc tách thành các phương thức listener riêng.

## 4. So sánh hai cách

| Tiêu chí | Kiểu cha chung | Thuộc tính classes |
|---|---|---|
| Quan hệ giữa event | Có chung lớp cha hoặc interface | Có thể hoàn toàn độc lập |
| Tham số listener | Nhận kiểu cha chung | Nhiều kiểu: không có tham số |
| Truy cập payload | Có thể đọc dữ liệu qua kiểu cha | Không nhận payload qua tham số |
| Hành vi phù hợp | Xử lý dựa trên dữ liệu hoặc phân biệt subtype | Một hành động giống nhau cho mọi event |
| Khả năng kiểm tra kiểu | Kiểm tra bằng hệ thống kiểu Java | Khai báo từng kiểu bằng class literal |

Không có cách nào luôn tốt hơn. Hãy dùng kiểu cha chung khi event có chung hợp đồng dữ liệu. Dùng classes khi các event độc lập nhưng cùng kích hoạt một phản ứng không cần payload.

Nếu một phương thức cần nhận nhiều event độc lập và vẫn cần dữ liệu của từng event, không nên cố gắng ép nhiều kiểu không liên quan vào một tham số. Hãy tạo một abstraction chung có ý nghĩa hoặc dùng nhiều listener method có tham số rõ ràng.

## 5. Ví dụ hoàn chỉnh có thể chạy

Ví dụ dưới đây dùng Java 17 và Spring Framework 6.2.0. Chương trình minh họa cả hai cách:

- OrderAuditListener nhận OrderEvent, là kiểu cha của OrderCreatedEvent và OrderCancelledEvent.
- OperationsNotifier khai báo hai payload event độc lập bằng classes và không nhận tham số.

Tạo file src/main/java/demo/MultiEventListenerDemo.java:

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

import java.util.Objects;

public class MultiEventListenerDemo {
    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.publishEvent(
                new OrderCreatedEvent("order-service", "ORD-1001")
            );
            context.publishEvent(
                new OrderCancelledEvent("order-service", "ORD-1002")
            );

            context.publishEvent(new InventoryLowEvent("SKU-7"));
            context.publishEvent(new PaymentFailedEvent("PAY-9"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        OrderAuditListener orderAuditListener() {
            return new OrderAuditListener();
        }

        @Bean
        OperationsNotifier operationsNotifier() {
            return new OperationsNotifier();
        }
    }

    public abstract static class OrderEvent extends ApplicationEvent {
        private final String orderId;

        protected OrderEvent(Object source, String orderId) {
            super(Objects.requireNonNull(source, "source"));
            this.orderId = Objects.requireNonNull(orderId, "orderId");
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static final class OrderCreatedEvent extends OrderEvent {
        public OrderCreatedEvent(Object source, String orderId) {
            super(source, orderId);
        }
    }

    public static final class OrderCancelledEvent extends OrderEvent {
        public OrderCancelledEvent(Object source, String orderId) {
            super(source, orderId);
        }
    }

    public record InventoryLowEvent(String sku) {
    }

    public record PaymentFailedEvent(String paymentId) {
    }

    static class OrderAuditListener {
        @EventListener
        public void handle(OrderEvent event) {
            System.out.println(
                event.getClass().getSimpleName()
                    + " for order " + event.getOrderId()
            );
        }
    }

    static class OperationsNotifier {
        @EventListener(classes = {
            InventoryLowEvent.class,
            PaymentFailedEvent.class
        })
        public void notifyOperations() {
            System.out.println("An operational event was received");
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
    <artifactId>multi-event-listener-demo</artifactId>
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
                    <mainClass>demo.MultiEventListenerDemo</mainClass>
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

Stdout dự kiến:

~~~text
OrderCreatedEvent for order ORD-1001
OrderCancelledEvent for order ORD-1002
An operational event was received
An operational event was received
~~~

Giải thích kết quả:

1. ApplicationContext đăng ký hai bean listener trong AppConfig.
2. OrderCreatedEvent được phát. Kiểu này kế thừa OrderEvent, nên OrderAuditListener.handle(OrderEvent) được gọi.
3. OrderCancelledEvent cũng kế thừa OrderEvent, nên cùng phương thức handle(...) được gọi lần thứ hai.
4. InventoryLowEvent được phát. Kiểu này nằm trong danh sách classes, nên OperationsNotifier.notifyOperations() được gọi.
5. PaymentFailedEvent cũng nằm trong danh sách classes, nên cùng phương thức notifyOperations() được gọi thêm lần nữa.
6. Các listener chạy đồng bộ theo cấu hình mặc định, nên thứ tự stdout tương ứng với thứ tự publishEvent trong main.

## 6. Kết hợp điều kiện SpEL

Có thể bổ sung thuộc tính condition để lọc event theo biểu thức Spring Expression Language. Với listener có một tham số, có thể dùng thuộc tính của event làm điều kiện:

~~~java
@EventListener(condition = "#root.args[0].orderId.startsWith('ORD-')")
public void handle(OrderEvent event) {
    System.out.println("Accepted order " + event.getOrderId());
}
~~~

Điều kiện được đánh giá khi event phù hợp với kiểu listener. Nếu biểu thức trả về false, phương thức không được gọi. Ngoài biến tham số, SpEL còn cung cấp #root.event để truy cập event thực tế và #root.args để truy cập các tham số của phương thức.

Với listener khai báo nhiều lớp trong classes, phương thức không có tham số theo quy tắc ở trên. Có thể dùng #root.event trong condition để lọc theo thông tin event, nhưng nếu phần thân phương thức cần xử lý payload khác nhau thì kiểu cha chung hoặc listener riêng thường dễ đọc hơn.

Không nên dùng condition để thay thế một mô hình kiểu dữ liệu rõ ràng. Nếu nhiều event có quy tắc xử lý khác nhau đáng kể, tách handler sẽ giúp code dễ bảo trì và kiểm thử.

## 7. Thứ tự, bất đồng bộ và lỗi

Nếu nhiều listener cùng nhận một event, có thể dùng @Order để xác định thứ tự ưu tiên khi chúng được gọi đồng bộ:

~~~java
@EventListener
@Order(1)
public void updateCache(OrderEvent event) {
    // Cập nhật cache trước.
}

@EventListener
@Order(2)
public void writeAudit(OrderEvent event) {
    // Ghi audit sau.
}
~~~

Chỉ nên dựa vào thứ tự này khi đó thực sự là yêu cầu của thiết kế. Nếu bước sau phụ thuộc kết quả bước trước, một service điều phối rõ ràng thường dễ hiểu hơn.

Có thể dùng @Async để xử lý listener ở executor khác khi đã bật @EnableAsync. Khi listener chạy bất đồng bộ, publisher không chờ xử lý hoàn tất; exception của listener không lan ngược về lời gọi publishEvent. Các listener bất đồng bộ cũng không nên dựa vào @Order để bảo đảm thứ tự hoàn tất.

Mặc định, listener đồng bộ được gọi trên thread phát event. Exception từ listener có thể ảnh hưởng tới lời gọi publishEvent nếu không có ErrorHandler xử lý. Vì vậy, nếu một phương thức nhận nhiều event và thực hiện cùng một hành động, cần bảo đảm hành động đó an toàn cho từng event và lỗi được xử lý theo chính sách mong muốn.

Application Events là cơ chế nội bộ của một ApplicationContext. Việc một phương thức nhận nhiều event không làm cơ chế này trở thành message broker: Spring không tự cung cấp persistence, retry hoặc giao nhận bền vững giữa nhiều tiến trình.

## 8. Lỗi thường gặp

- Khai báo nhiều lớp trong classes nhưng vẫn để một tham số: không hợp lệ trong Spring Framework 6.2. Hãy bỏ tham số hoặc chuyển sang kiểu cha chung.
- Dùng classes với các kiểu không liên quan rồi cố ép kiểu trong method: method không có tham số theo quy tắc multi-class, nên hãy dùng listener riêng nếu cần payload.
- Chọn kiểu cha quá rộng như ApplicationEvent: listener có thể nhận nhiều event của framework ngoài event nghiệp vụ dự định. Tạo một lớp cha domain cụ thể để giới hạn phạm vi.
- Quên rằng payload object cũng là event: từ Spring 4.2, có thể publish object bất kỳ; Spring bọc payload trong PayloadApplicationEvent.
- Listener không được gọi: kiểm tra bean có thuộc đúng ApplicationContext và kiểu event có khớp với phương thức hoặc danh sách classes hay không.
- Gộp event chỉ vì chúng cùng tên gọi hoặc cùng package: chỉ gộp khi chúng thật sự có chung hành vi hoặc hợp đồng dữ liệu.
- Cho rằng nhiều listener chạy bất đồng bộ: mặc định event listener chạy đồng bộ. Cần cấu hình async riêng khi có yêu cầu.

## 9. Quy trình lựa chọn

1. Liệt kê các kiểu event cần kích hoạt cùng phản ứng.
2. Kiểm tra xem chúng có chung một lớp cha hoặc interface mang ý nghĩa domain hay không.
3. Nếu có và cần đọc payload, dùng một tham số kiểu cha chung.
4. Nếu các kiểu độc lập và handler không cần payload, khai báo chúng trong @EventListener(classes = {...}) và dùng phương thức không tham số.
5. Nếu cần xử lý dữ liệu khác nhau, dùng kiểu cha chung phù hợp hoặc tách thành nhiều phương thức listener.
6. Kiểm thử từng loại event để bảo đảm tất cả đều kích hoạt đúng hành vi và không có event ngoài phạm vi.

Một phương thức listener nên gộp nhiều event khi chúng thực sự có cùng phản ứng. Chọn đúng kiểu cha chung hoặc danh sách classes sẽ giúp Spring phân phối event rõ ràng, đồng thời giữ chữ ký phương thức phù hợp với dữ liệu mà handler cần.