# Một listener nhận nhiều loại event

Trong Spring Framework, publisher gửi một event qua `ApplicationEventPublisher.publishEvent(...)`. ApplicationContext chuyển event đến những listener có kiểu tương thích. Vì vậy, một listener có thể xử lý nhiều lớp event trong cùng một luồng nghiệp vụ, miễn là ta khai báo kiểu nhận phù hợp.

Bài này tập trung vào hai cách thường dùng với `@EventListener`:

- Khai báo tham số bằng một interface hoặc lớp cha chung. Đây là lựa chọn phù hợp khi các event có cùng một ý nghĩa nghiệp vụ và cần đọc dữ liệu của từng event.
- Liệt kê nhiều lớp event bằng thuộc tính `classes`. Cách này phù hợp khi các event cần chạy cùng một hành động và method không cần nhận payload.

Từ Spring Framework 4.2, event có thể là một object Java thông thường; lớp event không bắt buộc phải kế thừa `ApplicationEvent`. Spring tự bọc payload khi cần.

## 1. Spring xác định event mà listener nhận như thế nào?

Một method được đánh dấu `@EventListener` sẽ trở thành listener khi bean chứa method đó được đăng ký trong ApplicationContext. Với Java configuration hoặc component scanning, Spring tự đăng ký bộ xử lý annotation để phát hiện các method này.

Khi không khai báo `classes`, Spring suy ra kiểu event từ tham số duy nhất của method. Listener được gọi khi kiểu event được publish tương thích với kiểu tham số. Quan hệ kế thừa và triển khai interface đều có ý nghĩa:

- Tham số là một lớp cha: nhận được instance của lớp đó và các lớp con.
- Tham số là một interface: nhận được các object có class triển khai interface đó.
- Tham số càng cụ thể thì listener càng hẹp; tham số quá tổng quát như `Object` có thể khiến method nhận rất nhiều event.

Mỗi lần publisher phát một event phù hợp, Spring gọi method một lần với event tương ứng. Listener không nhận một danh sách event và cũng không tự gom nhiều lần publish thành một batch.

## 2. Cách 1 — Dùng interface hoặc lớp cha chung

Đây thường là cách rõ ràng nhất khi nhiều event thuộc cùng một nhóm nghiệp vụ. Ta định nghĩa một contract nhỏ chứa thông tin chung, sau đó cho các event cụ thể triển khai contract đó.

Ví dụ, cả event tạo đơn và hủy đơn đều có mã đơn hàng:

~~~java
public interface OrderEvent {
    String orderId();
}

public record OrderPlaced(String orderId) implements OrderEvent {
}

public record OrderCancelled(String orderId, String reason) implements OrderEvent {
}
~~~

Listener chỉ cần khai báo tham số là `OrderEvent`:

~~~java
@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderEvent(OrderEvent event) {
        if (event instanceof OrderPlaced placed) {
            System.out.println("Đã tạo đơn " + placed.orderId());
        } else if (event instanceof OrderCancelled cancelled) {
            System.out.println("Đã hủy đơn " + cancelled.orderId()
                    + ": " + cancelled.reason());
        }
    }
}
~~~

Khi publisher gửi `OrderPlaced` hoặc `OrderCancelled`, cả hai đều tương thích với `OrderEvent`, nên cùng đi vào một method. Nhờ `instanceof`, method vẫn có thể xử lý dữ liệu riêng của từng loại event.

Có thể dùng abstract class thay cho interface nếu các event thật sự cần chia sẻ trạng thái hoặc hành vi. Không nên tạo một lớp cha chỉ để gom các event không liên quan; contract chung nên phản ánh một khái niệm nghiệp vụ có thật.

## 3. Ví dụ hoàn chỉnh với Java 17+

Ví dụ sau dùng Spring Framework 6.2.0, Java 17 và Maven. Toàn bộ chương trình nằm trong một file để dễ chạy thử.

**Cấu trúc file**

~~~text
spring-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventsDemo.java
~~~

**pom.xml**

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
                <configuration>
                    <release>17</release>
                </configuration>
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

**src/main/java/demo/ApplicationEventsDemo.java**

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class ApplicationEventsDemo {

    @Bean
    public OrderAuditListener orderAuditListener() {
        return new OrderAuditListener();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(ApplicationEventsDemo.class)) {
            context.publishEvent(new OrderPlaced("ORD-100"));
            context.publishEvent(
                    new OrderCancelled("ORD-200", "Khách yêu cầu hủy"));
        }
    }

    public interface OrderEvent {
        String orderId();
    }

    public record OrderPlaced(String orderId) implements OrderEvent {
    }

    public record OrderCancelled(String orderId, String reason)
            implements OrderEvent {
    }

    public static class OrderAuditListener {

        @EventListener
        public void onOrderEvent(OrderEvent event) {
            if (event instanceof OrderPlaced placed) {
                System.out.println("Đã tạo đơn " + placed.orderId());
            } else if (event instanceof OrderCancelled cancelled) {
                System.out.println("Đã hủy đơn " + cancelled.orderId()
                        + ": " + cancelled.reason());
            }
        }
    }
}
~~~

**Chạy chương trình**

Từ thư mục có `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do listener in ra:

~~~text
Đã tạo đơn ORD-100
Đã hủy đơn ORD-200: Khách yêu cầu hủy
~~~

**Diễn biến**

1. Spring tạo ApplicationContext và đăng ký bean `OrderAuditListener`.
2. Bộ xử lý `@EventListener` phát hiện method `onOrderEvent(OrderEvent)`.
3. Publisher gửi một `OrderPlaced`. Vì record này triển khai `OrderEvent`, method được gọi và nhánh `OrderPlaced` chạy.
4. Publisher gửi một `OrderCancelled`. Cùng method được gọi lần nữa, lần này nhánh `OrderCancelled` chạy.
5. Context đóng sau khi hai lần publish hoàn tất.

Các record đóng vai trò payload event bất biến. Chúng không cần kế thừa `ApplicationEvent`; `AnnotationConfigApplicationContext.publishEvent(Object)` hỗ trợ object thông thường.

## 4. Cách 2 — Liệt kê nhiều event bằng thuộc tính classes

Nếu nhiều loại event cần kích hoạt cùng một hành động và method không cần đọc payload, có thể khai báo danh sách event ngay trên annotation:

~~~java
@EventListener(classes = {
    ContextStartedEvent.class,
    ContextRefreshedEvent.class
})
public void onContextLifecycleChange() {
    System.out.println("ApplicationContext đã thay đổi trạng thái");
}
~~~

Ở đây, một method được đăng ký cho cả `ContextStartedEvent` và `ContextRefreshedEvent`. Method không có tham số nên chỉ thực hiện được phần xử lý chung; nó không biết loại event cụ thể nào đã kích hoạt lần gọi đó.

Trong Spring Framework 6.2, khi `classes` chứa nhiều hơn một loại event, method phải không khai báo tham số. Nếu chỉ khai báo một class trong `classes`, method có thể nhận một tham số event. Thuộc tính `value` là alias của `classes`, vì vậy `@EventListener({A.class, B.class})` có ý nghĩa tương đương với `@EventListener(classes = {A.class, B.class})`.

Nếu cần đọc payload và phân nhánh theo loại event, hãy ưu tiên cách 1: dùng một tham số là interface hoặc lớp cha chung. Nếu các event không có contract chung hợp lý, hãy viết các method listener riêng để mỗi method nhận đúng kiểu dữ liệu của nó.

## 5. Chọn cách phù hợp

| Tình huống | Cách nên dùng | Lý do |
|---|---|---|
| Các event có chung dữ liệu hoặc hành vi nghiệp vụ | Tham số là interface/lớp cha chung | Một method nhận được payload và vẫn kiểm tra được loại cụ thể |
| Nhiều event cần chạy cùng một hành động, không cần payload | `@EventListener(classes = {...})` | Khai báo danh sách event tập trung |
| Các event không liên quan và cần xử lý dữ liệu khác nhau | Nhiều method listener riêng | Kiểu tham số rõ ràng, ít ép kiểu và dễ bảo trì |
| Chỉ muốn nhận một nhánh cụ thể trong hệ phân cấp event | Tham số là kiểu cụ thể | Giới hạn phạm vi event được nhận |

## 6. Thứ tự xử lý và xử lý bất đồng bộ

Mặc định, event listener của ApplicationContext chạy đồng bộ trong thread gọi `publishEvent(...)`. Publisher chỉ tiếp tục sau khi các listener đồng bộ xử lý xong. Vì vậy, không nên đặt tác vụ dài như gọi dịch vụ bên ngoài hoặc xử lý tệp lớn trong listener đồng bộ nếu việc đó làm chậm luồng chính.

Có thể kết hợp `@Async` với `@EventListener` và bật `@EnableAsync` để xử lý bất đồng bộ. Khi đó cần lưu ý:

- Exception từ listener bất đồng bộ không được ném ngược về thread gọi publisher.
- Method listener bất đồng bộ không thể phát event tiếp theo bằng cách trả về object; hãy inject `ApplicationEventPublisher` và gọi `publishEvent(...)` rõ ràng.
- Không giả định ThreadLocal hoặc logging context tự được truyền sang thread khác.

Nếu có nhiều listener cùng nhận một event và cần thứ tự gọi, có thể dùng `@Order` trên các method listener. Thứ tự chỉ có ý nghĩa giữa các listener cùng xử lý event phù hợp.

## 7. Lỗi thường gặp

- **Dùng kiểu tham số quá hẹp:** Method nhận `OrderPlaced` sẽ không nhận `OrderCancelled`. Dùng contract chung nếu muốn gom hai loại.
- **Dùng `Object` làm tham số cho tiện:** Cách này làm listener nhận quá nhiều loại event và buộc phải kiểm tra kiểu ở mọi nhánh. Chỉ dùng khi thực sự cần một bộ xử lý tổng quát.
- **Khai báo nhiều class trong `classes` nhưng vẫn thêm tham số:** Với Spring Framework 6.2, danh sách có nhiều hơn một class yêu cầu method không có tham số.
- **Đăng ký listener ngoài Spring container:** Một object được tạo bằng `new OrderAuditListener()` và không đăng ký thành bean sẽ không được bộ xử lý annotation tự động phát hiện.
- **Nghĩ rằng một lần publish truyền nhiều event:** Mỗi lần gọi `publishEvent` gửi một event; method có thể được gọi nhiều lần, mỗi lần với một event phù hợp.
- **Đưa xử lý nặng vào listener đồng bộ:** Việc đó kéo dài thời gian của luồng publisher. Chỉ bật bất đồng bộ khi đã xác định rõ yêu cầu về thread, lỗi và thứ tự xử lý.

## 8. Ghi nhớ

Một listener method có thể nhận nhiều lớp event thông qua kiểu tham số chung. Hãy dùng interface hoặc lớp cha để mô tả nhóm event có cùng ý nghĩa nghiệp vụ; đây là cách giữ được payload và tính an toàn kiểu.

Dùng `@EventListener(classes = {...})` khi nhiều event cần kích hoạt cùng một xử lý không cần tham số. Với Spring Framework 6.2, method liệt kê nhiều event trong `classes` phải không có tham số.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2.0 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2.0 — ApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationListener.html)
