# Thứ tự trong xử lý đồng bộ — Spring Framework Application Events

## 1. Xử lý đồng bộ nghĩa là gì?

Spring Framework cho phép một thành phần phát sự kiện bằng `ApplicationEventPublisher.publishEvent(...)` và nhiều listener nhận sự kiện đó. Với cấu hình mặc định của `ApplicationContext`, bộ phân phối sự kiện là `SimpleApplicationEventMulticaster`; các listener thông thường được gọi **đồng bộ trên luồng đã phát sự kiện**.

Giả sử có ba listener cùng quan tâm đến sự kiện `InvoiceIssued`. Trong một lần gọi `publishEvent(event)`:

1. Spring xác định những listener phù hợp với kiểu sự kiện.
2. Spring sắp xếp các listener theo mức ưu tiên được khai báo.
3. Spring gọi từng listener đồng bộ, lần lượt; một listener hoàn thành thì mới chuyển sang listener kế tiếp.
4. Khi mọi listener đã được gọi và hoàn thành bình thường, `publishEvent(...)` mới trả quyền điều khiển cho mã phát sự kiện.

Minh họa:

```text
Luồng phát sự kiện
  |
  +-- log("before")
  +-- publishEvent(invoiceIssued)
        |
        +-- listener ưu tiên 10: xử lý xong
        +-- listener ưu tiên 20: xử lý xong
        +-- listener ưu tiên 30: xử lý xong
        |
        +-- trả về
  +-- log("after")
```

Nhờ cơ chế này, mã sau `publishEvent(...)` quan sát được việc **các listener đồng bộ đã thực thi xong**, miễn là không có lỗi chặn luồng và không dùng cơ chế bất đồng bộ. Thời gian thực thi listener cũng cộng trực tiếp vào độ trễ của lời gọi phát sự kiện.

## 2. Cấu hình thứ tự bằng `@Order`

Với phương thức được đánh dấu `@EventListener`, đặt `@Order` trực tiếp trên phương thức để xác định mức ưu tiên. **Số nhỏ hơn chạy trước**; giá trị âm cũng hợp lệ.

| Khai báo | Ý nghĩa tương đối |
| --- | --- |
| `@Order(-10)` | Chạy trước các listener có thứ tự 0, 10, 20... |
| `@Order(0)` | Chạy trước `@Order(10)` |
| `@Order(10)` | Chạy trước `@Order(20)` |
| `@Order(20)` | Chạy sau `@Order(10)` |
| Không khai báo thứ tự | Mặc định có mức ưu tiên thấp, tương đương `Ordered.LOWEST_PRECEDENCE` |

Các quy tắc cần phân biệt:

- `@Order` quyết định **thứ tự gọi các listener cùng được lựa chọn cho một lần phát sự kiện**, không quyết định thứ tự tạo bean, thứ tự phát các sự kiện độc lập hay thứ tự công việc ở các luồng khác nhau.
- Listener có cùng giá trị `@Order` (hoặc đều không khai báo) **không nên được giả định có thứ tự tương đối ổn định**. Nếu cần thứ tự xác định, hãy cho chúng các giá trị khác nhau hoặc gọi chúng tường minh từ một dịch vụ điều phối.
- Với listener viết theo giao diện `ApplicationListener<E>`, có thể triển khai `org.springframework.core.Ordered` và trả về giá trị từ `getOrder()`. Với listener dạng phương thức `@EventListener`, khai báo `@Order` trên chính phương thức là cách ngắn gọn, rõ ràng.
- Số trong `@Order` là **độ ưu tiên**, không phải số thứ tự bước nghiệp vụ bất biến. Có thể để khoảng như 10, 20, 30 để dễ bổ sung listener mới, nhưng đừng biến việc sắp thứ tự listener thành quy trình nghiệp vụ nhiều bước bắt buộc.

## 3. Ví dụ hoàn chỉnh chạy bằng Java 17 và Spring Framework

Ví dụ sau có ba phương thức `@EventListener` thuộc cùng một bean. Chúng được viết theo thứ tự 30, 10, 20 trong mã nguồn, nhưng khi phát sự kiện vẫn chạy theo **10 → 20 → 30**.

Cấu trúc dự án Maven:

```text
spring-sync-event-order/
├── pom.xml
└── src/main/java/demo/SyncEventOrderDemo.java
```

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-sync-event-order</artifactId>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SyncEventOrderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/SyncEventOrderDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class SyncEventOrderDemo {

    public record InvoiceIssued(String invoiceId) {}

    @Configuration(proxyBeanMethods = false)
    public static class InvoiceListeners {

        @EventListener
        @Order(30)
        public void notifyCustomer(InvoiceIssued event) {
            System.out.println("listener 30: notify " + event.invoiceId());
        }

        @EventListener
        @Order(10)
        public void validate(InvoiceIssued event) {
            System.out.println("listener 10: validate " + event.invoiceId());
        }

        @EventListener
        @Order(20)
        public void audit(InvoiceIssued event) {
            System.out.println("listener 20: audit " + event.invoiceId());
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(InvoiceListeners.class)) {
            System.out.println("publisher: before");
            context.publishEvent(new InvoiceIssued("INV-42"));
            System.out.println("publisher: after");
        }
    }
}
```

Từ thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Đầu ra từ các lệnh `System.out.println` trong chương trình:

```text
publisher: before
listener 10: validate INV-42
listener 20: audit INV-42
listener 30: notify INV-42
publisher: after
```

Tại sao có kết quả này?

- `new AnnotationConfigApplicationContext(InvoiceListeners.class)` đăng ký bean cấu hình và cơ chế phát/nhận sự kiện của Spring.
- `context.publishEvent(new InvoiceIssued(...))` phát một đối tượng Java thông thường; Spring hỗ trợ sự kiện payload nên không bắt buộc lớp sự kiện kế thừa `ApplicationEvent`.
- Ba phương thức có tham số `InvoiceIssued` đều là listener phù hợp. `@Order` được áp dụng khi Spring sắp xếp chúng, dù thứ tự khai báo các phương thức trong tệp khác nhau.
- `publisher: after` chỉ xuất hiện khi ba listener đồng bộ đã hoàn tất; ví dụ không bật `@Async` hay cung cấp một `TaskExecutor` bất đồng bộ cho multicaster.

Nếu viết bằng Spring Boot, ý tưởng vẫn giống nhau: đặt các `@EventListener` trong Spring-managed bean (ví dụ `@Component`) và phát qua `ApplicationEventPublisher` được inject.

## 4. Những tình huống ảnh hưởng đến thứ tự quan sát được

### 4.1. Một listener ném ngoại lệ

Theo cấu hình mặc định của `SimpleApplicationEventMulticaster`, nếu listener đồng bộ ném một ngoại lệ không được xử lý, ngoại lệ truyền ngược về mã gọi `publishEvent(...)` và quá trình phân phối sự kiện hiện tại bị dừng tại đó. Chẳng hạn, listener `@Order(10)` ném `IllegalStateException` thì listener `@Order(20)` và `@Order(30)` có thể chưa được gọi, còn lệnh sau `publishEvent(...)` sẽ không chạy trừ khi phía phát bắt được ngoại lệ.

Có thể cấu hình `ErrorHandler` cho multicaster để xử lý lỗi theo chính sách khác, nhưng chính sách đó phải được thiết kế tường minh. **`@Order` không bảo đảm rằng mọi listener đều chạy thành công.**

### 4.2. Listener lại phát một sự kiện khác

Listener đồng bộ có thể gọi tiếp `publishEvent(childEvent)`. Khi đó, việc phân phối sự kiện con xảy ra lồng trong lời gọi hiện tại. Ví dụ:

```text
Sự kiện A:
  listener A-10 bắt đầu
    publishEvent(B)
      listener B-10 chạy
    B hoàn tất
  listener A-10 kết thúc
  listener A-20 chạy
```

Thứ tự trên không vi phạm `@Order`: mỗi lần phát sự kiện có tập listener và thứ tự riêng. Không có một hàng đợi toàn cục tự động gom mọi sự kiện lại để sắp xếp theo `@Order`.

### 4.3. Chuyển sang xử lý bất đồng bộ

Bảo đảm "listener trước hoàn thành rồi listener sau mới chạy" **không còn áp dụng** nếu phương thức `@EventListener` dùng `@Async` (với hỗ trợ async được bật), hoặc ứng dụng cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)` với executor bất đồng bộ cho những listener được phép chạy async.

`@Order` lúc này không phải cơ chế chờ hoàn thành tác vụ: thời điểm listener bắt đầu, kết thúc và thứ tự ghi log có thể khác thứ tự ưu tiên. Nếu cần các bước chạy tuần tự thực sự, giữ phần đó trong luồng đồng bộ hoặc xây dựng cơ chế điều phối phù hợp.

### 4.4. Có nhiều luồng cùng phát sự kiện

"Đồng bộ" được hiểu **trong phạm vi một lần gọi `publishEvent(...)` của từng luồng**. Hai luồng đồng thời phát hai sự kiện có thể khiến log của các listener xen kẽ nhau. `@Order` không khóa các luồng phát sự kiện, không tuần tự hóa các event độc lập và không đảm bảo thứ tự toàn cục giữa các publisher.

### 4.5. Sự kiện nằm trong giao dịch

Listener đồng bộ bình thường chạy trong luồng phát sự kiện, nên nếu publisher đang có transaction theo thread thì listener có thể chạy khi transaction đó **chưa commit**. Việc listener chạy trước trong `@Order` không đồng nghĩa thay đổi dữ liệu đã commit, và tác dụng phụ ngoài cơ sở dữ liệu (gửi email, gọi API ngoài...) không tự được rollback.

`@TransactionalEventListener` có ngữ nghĩa khác: theo mặc định listener được gắn với giai đoạn `AFTER_COMMIT` của giao dịch, thay vì nhất thiết chạy ngay trong chuỗi listener thông thường tại thời điểm `publishEvent(...)`. Nếu yêu cầu là "chỉ xử lý sau commit", hãy chọn cơ chế theo pha giao dịch; `@Order` một mình không thể thay thế ranh giới transaction.

## 5. Cách áp dụng trong ứng dụng

- **Dùng `@Order` khi** nhiều listener độc lập cần một mức ưu tiên rõ ràng trong cùng lần phát sự kiện, ví dụ ghi dấu theo dõi trước một bước bổ sung thông tin. Chọn các mức khác nhau và ghi rõ lý do của thứ tự.
- **Gọi trực tiếp qua một service điều phối khi** bước sau bắt buộc sử dụng kết quả bước trước, khi phải bảo đảm tất cả bước chạy thành công hoặc cần rollback nhất quán. Lúc đó các lời gọi tuần tự tường minh, giao dịch và quy tắc xử lý lỗi thường dễ kiểm soát hơn.
- **Giữ listener đồng bộ ngắn gọn** vì `publishEvent(...)` phải chờ chúng. Công việc có thể chậm, có retry hoặc gọi hệ thống ngoài nên có chính sách riêng về bất đồng bộ, giao dịch và độ tin cậy.
- **Khi thứ tự không như mong đợi**, kiểm tra listener thực sự có nhận đúng kiểu event không; `@Order` có được gắn lên đúng phương thức `@EventListener` không; có giá trị trùng nhau không; có `@Async`/executor bất đồng bộ không; có ngoại lệ ở listener chạy trước hoặc sự kiện lồng nhau không. Đừng suy luận thứ tự từ tên bean hay vị trí khai báo phương thức.

## 6. Tự kiểm tra kiến thức

1. Với ba listener `@Order(50)`, `@Order(-5)` và `@Order(0)` cùng nhận một event và đều chạy đồng bộ thành công, thứ tự là **-5 → 0 → 50**.
2. Sau khi `publishEvent(...)` trả về bình thường trong ví dụ đồng bộ, các listener phù hợp đã hoàn tất. Nếu một listener ném ngoại lệ không được xử lý, câu khẳng định ấy không còn áp dụng cho toàn bộ tập listener.
3. Hai listener cùng `@Order(10)` **không tạo ra một quy tắc nghiệp vụ xác định** về ai chạy trước.
4. `@Order` **không** khiến hai lần phát event từ hai luồng khác nhau phải nối đuôi nhau, và **không** biến callback async thành xử lý tuần tự.
5. Nếu muốn logic sau khi transaction commit, phải xét `@TransactionalEventListener` và pha transaction, thay vì chỉ đổi con số trong `@Order`.

## Tài liệu Spring Framework

- [ApplicationContext: Application Events, Ordering Listeners, Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [`SimpleApplicationEventMulticaster` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
