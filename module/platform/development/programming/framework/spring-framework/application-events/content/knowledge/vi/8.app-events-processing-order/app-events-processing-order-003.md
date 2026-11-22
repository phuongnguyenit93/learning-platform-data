# Thứ tự giữa nhiều listener cùng event trong Spring Framework

Khi một event được phát qua `ApplicationEventPublisher.publishEvent(...)`, có thể có nhiều listener cùng quan tâm tới kiểu event đó. Ví dụ, sau sự kiện xuất hóa đơn, ứng dụng cần ghi nhật ký, cập nhật chỉ số thống kê và gửi thông báo. Spring có cơ chế xác định **thứ tự gọi listener**; tuy nhiên, phải phân biệt thứ tự **được gọi** với thứ tự **hoàn tất**, đặc biệt khi có xử lý bất đồng bộ hoặc listener gắn với giao dịch.

## 1. Spring chọn và gọi các listener như thế nào?

Với `ApplicationContext` thông thường, cơ chế mặc định dùng `SimpleApplicationEventMulticaster`:

1. Khi nhận một event, Spring chọn những listener phù hợp với **kiểu event** và điều kiện áp dụng (nếu có).
2. Danh sách listener được sắp xếp theo độ ưu tiên mà Spring nhận biết.
3. Theo cấu hình mặc định, Spring **gọi tuần tự, đồng bộ trên thread phát event**. Phương thức `publishEvent(...)` thường chỉ trở về sau khi các listener đồng bộ đã chạy xong.
4. Nếu cấu hình `@Async` hoặc một executor bất đồng bộ cho multicaster, việc listener hoàn tất theo thứ tự nào là một câu chuyện khác.

`@Order` là công cụ phù hợp nếu cần kiểm soát thứ tự *gọi* các listener độc lập đối với cùng event trong cơ chế đồng bộ. Nó không xác định thứ tự tạo bean, không sắp xếp các lần phát event khác nhau và không tự tạo ra một quy trình nghiệp vụ có bảo đảm giao dịch.

## 2. Quy tắc của `@Order`

Đặt `@Order` **trên từng phương thức có `@EventListener`**. Giá trị số **càng nhỏ thì ưu tiên càng cao**, được gọi trước trong danh sách listener tương ứng.

| Khai báo | Ý nghĩa trong cùng lượt phát event đồng bộ |
| --- | --- |
| `@Order(-10)` | Trước `@Order(0)` và `@Order(10)` |
| `@Order(0)` | Trước `@Order(10)` |
| `@Order(10)` | Sau các listener có giá trị nhỏ hơn |
| Không khai báo `@Order` | Mặc định tương đương ưu tiên thấp nhất, `Ordered.LOWEST_PRECEDENCE` (`Integer.MAX_VALUE`) |

Giá trị không bắt buộc liên tiếp: `@Order(10)`, `@Order(100)` và `@Order(1000)` vẫn được sắp xếp theo thứ tự đó. Có thể dùng các hằng `Ordered.HIGHEST_PRECEDENCE` và `Ordered.LOWEST_PRECEDENCE`, nhưng nên dùng những giá trị dễ đọc để nhóm phát triển hiểu ý đồ.

**Hai listener có cùng giá trị `@Order` (hoặc cùng không khai báo) không có thứ tự tương đối được Spring cam kết.** Đừng dựa vào thứ tự phương thức xuất hiện trong mã, tên phương thức, thứ tự quét package, thứ tự khởi tạo bean hay kết quả quan sát được trong một lần chạy. Nếu thứ tự giữa A và B quan trọng, hãy cho chúng hai giá trị ưu tiên khác nhau.

## 3. Ví dụ đầy đủ có thể chạy bằng Java 17+

Ví dụ không cần Spring Boot, chỉ cần `spring-context`. Tạo dự án Maven với cấu trúc:

```text
event-order-demo/
├── pom.xml
└── src/main/java/ListenerOrderDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>ListenerOrderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/ListenerOrderDemo.java`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class ListenerOrderDemo {

    public record InvoiceIssued(String invoiceId) {}

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(InvoiceListeners.class);
            context.refresh();

            context.publishEvent(new InvoiceIssued("INV-42"));
        }
    }

    public static class InvoiceListeners {

        @EventListener
        @Order(30)
        public void notifyCustomer(InvoiceIssued event) {
            System.out.println("3. notify " + event.invoiceId());
        }

        @EventListener
        @Order(10)
        public void recordAudit(InvoiceIssued event) {
            System.out.println("1. audit " + event.invoiceId());
        }

        @EventListener
        @Order(20)
        public void updateAnalytics(InvoiceIssued event) {
            System.out.println("2. analytics " + event.invoiceId());
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml` (cần JDK 17+ và Maven):

```bash
mvn -q compile exec:java
```

Ba dòng do các listener in ra, theo đúng thứ tự, là:

```text
1. audit INV-42
2. analytics INV-42
3. notify INV-42
```

Phương thức `notifyCustomer` được **khai báo trước** trong lớp nhưng chạy **sau cùng** vì `@Order(30)`. `recordAudit` chạy trước vì `@Order(10)`, tiếp theo là `updateAnalytics` với `@Order(20)`. Record `InvoiceIssued` không cần kế thừa `ApplicationEvent`: Spring hỗ trợ phát object thông thường qua `publishEvent(Object)` và listener có thể nhận đúng kiểu payload.

Lưu ý ví dụ chỉ in thông báo để quan sát thứ tự. Trong hệ thống thật, không nên coi `@Order` là bảo đảm cho các bước nghiệp vụ phụ thuộc nhau (ví dụ, bắt buộc lưu hóa đơn thành công rồi mới được gửi tiền).

## 4. Nếu dùng interface `ApplicationListener` thay cho `@EventListener`

Một bean triển khai `ApplicationListener<E>` có thể khai báo thứ tự qua interface `Ordered`, bằng cách trả về độ ưu tiên từ `getOrder()`. Ví dụ sau là **đoạn minh họa**, giả định `InvoiceIssuedEvent` là một lớp kế thừa `ApplicationEvent` và listener được đăng ký làm Spring bean:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public final class AuditListener
        implements ApplicationListener<InvoiceIssuedEvent>, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void onApplicationEvent(InvoiceIssuedEvent event) {
        // Xử lý event tương ứng.
    }
}
```

Với cách này, `getOrder()` đóng vai trò tương ứng với `@Order(10)`. Sự khác biệt kiểu dữ liệu cần nhớ: `ApplicationListener<E>` yêu cầu `E extends ApplicationEvent`, trong khi phương thức đánh dấu `@EventListener` có thể nhận một payload object thông thường như record ở ví dụ trên.

Khi dùng `@EventListener`, hãy đặt `@Order` trực tiếp trên **phương thức listener**, để tránh hiểu nhầm `@Order` của lớp dùng cho mục đích khác (chẳng hạn sắp xếp bean khi inject danh sách) sẽ quyết định thứ tự từng phương thức.

## 5. Trường hợp không thể suy ra thứ tự hoàn tất từ `@Order`

### 5.1. Listener chạy bất đồng bộ

Ví dụ:

```java
@Async
@EventListener
@Order(10)
public void writeAudit(InvoiceIssued event) {
    // Có thể chạy trên thread của executor.
}

@EventListener
@Order(20)
public void updateMetrics(InvoiceIssued event) {
    // Có thể hoàn tất trước writeAudit.
}
```

Đoạn trên chỉ minh họa phương thức listener; để `@Async` có hiệu lực cần bật xử lý bất đồng bộ, ví dụ `@EnableAsync`, và cấu hình executor phù hợp. Spring có thể **gọi/sắp lịch** listener có `@Order(10)` trước, nhưng phần xử lý trong thread khác có thể hoàn tất sau listener có `@Order(20)`. Tương tự, nếu cấu hình executor cho `SimpleApplicationEventMulticaster`, thứ tự sắp xếp trước khi gửi việc vào executor không đồng nghĩa với thứ tự các tác vụ bắt đầu hoặc kết thúc.

Do đó, `@Order` không phải cơ chế bảo đảm happens-before giữa hai tác vụ bất đồng bộ, không biến các listener thành hàng đợi tuần tự và không bảo đảm thứ tự trong một hệ thống phân tán. Nếu B chỉ được phép chạy sau khi A thành công, cần phối hợp rõ ràng bằng lời gọi trực tiếp, pipeline được kiểm soát, `CompletableFuture` được nối bước, hoặc một hệ thống hàng đợi/workflow có ngữ nghĩa thứ tự phù hợp.

### 5.2. Listener gắn với transaction

`@TransactionalEventListener` có các pha như `BEFORE_COMMIT`, `AFTER_COMMIT` (mặc định), `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Thời điểm callback chịu sự chi phối của **pha giao dịch**; `@Order` có thể ưu tiên các transactional listener trong cùng giai đoạn phù hợp, nhưng không ép listener `AFTER_COMMIT` chạy trước logic đang xử lý event trong transaction chỉ vì mang số nhỏ hơn.

Không nên so sánh thứ tự chỉ bằng `@Order` khi một số listener là `@EventListener` thông thường còn số khác là `@TransactionalEventListener`. Nếu không có transaction đang hoạt động, transactional listener thông thường không được gọi, trừ khi cấu hình `fallbackExecution = true`.

### 5.3. Lỗi của listener đồng bộ

Với cấu hình mặc định, nếu một listener đồng bộ ném exception, `SimpleApplicationEventMulticaster` không có `ErrorHandler` để nuốt lỗi: lỗi được chuyển ngược tới bên phát event và việc dispatch hiện tại bị dừng. Vì vậy, một listener `@Order(10)` lỗi có thể khiến listener `@Order(20)` **không được gọi**. Không suy ra rằng mọi listener đều chạy chỉ vì chúng đã được đăng ký.

Muốn xử lý lỗi độc lập thì phải thiết kế cách bắt/ghi nhận lỗi hoặc cấu hình `ErrorHandler` một cách có chủ đích, cân nhắc tác động lên tính đúng đắn của nghiệp vụ.

### 5.4. Event lồng nhau và nhiều lần phát event

Nếu listener A đang chạy mà lại phát một event B mới, trong cơ chế đồng bộ các listener của B có thể chạy ngay trong lời gọi lồng nhau, trước khi Spring quay lại listener tiếp theo của event A. `@Order` chỉ sắp thứ tự các listener áp dụng cho **một lượt dispatch tương ứng**, không tạo ra thứ tự toàn cục giữa nhiều event.

## 6. Khi nào nên dùng và cách kiểm thử

Nên dùng `@Order` nếu có nhiều listener đồng bộ **tương đối độc lập** cần thứ tự quan sát được, chẳng hạn một listener thêm ngữ cảnh log trước khi các listener theo dõi khác chạy. Nếu một thao tác phụ thuộc vào kết quả thành công của thao tác trước, hãy mô hình hóa điều đó bằng một service điều phối tường minh và truyền kết quả giữa các bước; event listener thích hợp hơn cho phản ứng phụ, thông báo và mở rộng không cần gắn chặt vào luồng chính.

Khi kiểm thử thứ tự, khởi tạo Spring context với các listener, phát **một event xác định**, thu tên callback vào danh sách và so sánh với danh sách mong đợi. Bài kiểm thử phải dùng dispatch đồng bộ nếu đang xác nhận `@Order`. Có thể thử thay đổi thứ tự khai báo phương thức và vẫn mong kết quả theo giá trị `@Order`. Đối với listener bất đồng bộ, kiểm thử bằng công cụ đồng bộ hóa/latch nếu cần kiểm tra sự kiện hoàn tất; đừng dùng độ trễ `Thread.sleep` để khẳng định thứ tự.

Những lỗi thường gặp:

- Hiểu ngược ưu tiên: **số nhỏ hơn chạy trước**, không phải số lớn.
- Gán cùng một giá trị cho các listener mà lại kỳ vọng một thứ tự cố định.
- Đặt `@Order` trên lớp rồi mặc nhiên cho rằng tất cả phương thức `@EventListener` bên trong sẽ có đúng thứ tự như mong muốn.
- Nhầm thứ tự listener với thứ tự khởi tạo bean hoặc thứ tự các sự kiện.
- Áp dụng kết luận của dispatch đồng bộ cho `@Async`, multicaster chạy trên executor hoặc transactional listener.
- Dùng `@Order` làm bảo đảm cho chuỗi nghiệp vụ bắt buộc thành công, hoặc quên rằng exception ở listener trước có thể ngăn listener sau được gọi.

## Tài liệu tham khảo

- [Spring Framework Reference – Application Events và Ordering Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Javadoc – `@EventListener`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html)
- [Javadoc – `Ordered` và thứ tự khi cùng giá trị](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html)
- [Javadoc – `SimpleApplicationEventMulticaster`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Javadoc – `@TransactionalEventListener`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
