# Exception từ listener đồng bộ trong Spring Framework Application Events

## 1. Điều gì xảy ra khi một listener đồng bộ ném exception?

Khi mã nghiệp vụ gọi `ApplicationEventPublisher.publishEvent(event)`, Spring Framework chuyển sự kiện tới `ApplicationEventMulticaster` để tìm và gọi các listener phù hợp. Với cấu hình mặc định của `SimpleApplicationEventMulticaster`, các listener chạy **đồng bộ trên chính luồng gọi `publishEvent(...)`**. Vì thế lỗi xảy ra bên trong listener có thể ảnh hưởng trực tiếp đến bên phát sự kiện.

**Quy tắc cốt lõi:** Nếu một listener đồng bộ ném ngoại lệ và multicaster không có `ErrorHandler`, ngoại lệ đó được truyền ngược tới lời gọi `publishEvent(...)`. Lượt phân phối hiện tại dừng tại listener gây lỗi; các listener đứng sau chưa được gọi sẽ không được thực thi trong lượt đó.

Đây là hành vi mặc định của `SimpleApplicationEventMulticaster`, không phải cam kết áp dụng cho mọi triển khai multicaster tùy chỉnh hay cho các listener bất đồng bộ.

~~~text
Service / Controller (luồng T)
    |
    | publishEvent(OrderCreated)
    v
ApplicationEventMulticaster (vẫn trên luồng T)
    |
    +-- Listener A: xử lý xong
    |
    +-- Listener B: throw IllegalStateException
    |        |
    |        +-- không có ErrorHandler: ném ngoại lệ ra ngoài
    |
    X-- Listener C: chưa được gọi
    |
    v
publishEvent(...) ném ngoại lệ về Service / Controller
~~~

Không nên nhầm việc **ngừng gọi các listener tiếp theo** với việc **hoàn tác những listener đã chạy**. Nếu Listener A đã ghi file, gọi dịch vụ ngoài hoặc gửi email, exception của Listener B không tự đảo ngược các tác dụng đó.

## 2. Đường đi của exception và tác động tới bên phát

Trong trường hợp thông thường, chuỗi lời gọi đồng bộ có dạng:

1. Thành phần phát gọi `publishEvent(event)`.
2. `ApplicationContext` chuyển sự kiện sang multicaster của context.
3. Multicaster xác định các listener thích hợp và gọi từng listener.
4. Một listener ném `RuntimeException`, ví dụ `IllegalStateException`.
5. Không có handler bắt và xử lý lỗi, nên exception lan ra từ listener, qua multicaster và `publishEvent(...)`.
6. Mã gọi `publishEvent(...)` có thể bắt exception bằng `try/catch` hoặc để nó tiếp tục lan lên lớp gọi phía trên.

Hệ quả có thể quan sát:

- `publishEvent(...)` **không trả về bình thường** khi exception được truyền ra; các câu lệnh nằm sau lời gọi trong cùng khối `try` có thể bị bỏ qua.
- Những listener đã được gọi **trước** listener lỗi vẫn đã thực thi; những listener đứng **sau** listener lỗi chưa được gọi trong lượt phát đó.
- Bên phát có thể bắt exception, ghi log, chuyển thành kết quả nghiệp vụ hoặc để cơ chế giao dịch xử lý theo quy tắc của nó.
- Spring Application Events không mặc nhiên có retry, hàng đợi bền vững hay cơ chế tự động phát lại listener vừa lỗi.

**Thứ tự listener quan trọng trong thử nghiệm.** Có thể dùng `@Order` trên phương thức `@EventListener` hoặc `Ordered` trên `ApplicationListener` để điều chỉnh thứ tự gọi khi thực thi đồng bộ. Nếu không đặt thứ tự rõ ràng, đừng dựa vào trật tự ngẫu nhiên để bảo đảm tính đúng đắn của nghiệp vụ.

## 3. Ví dụ Java 17+: so sánh lỗi mặc định và ErrorHandler

Ví dụ bên dưới dùng Spring Framework 6.2.9, Java 17+ và Maven. Hai lượt phát sự kiện dùng cùng cặp listener: listener đầu tiên cố ý ném exception; listener thứ hai chỉ in một dòng để kiểm tra nó có được gọi hay không.

Tạo hai tệp:

~~~text
listener-exception-demo/
├── pom.xml
└── src/main/java/ListenerExceptionDemo.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>listener-exception-demo</artifactId>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung `src/main/java/ListenerExceptionDemo.java`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.annotation.Order;

public class ListenerExceptionDemo {

    public record TaskQueued(String id) {}

    public static void main(String[] args) {
        System.out.println("=== Mặc định: không có ErrorHandler ===");

        try (var context =
                     new AnnotationConfigApplicationContext(DefaultConfig.class)) {
            try {
                context.publishEvent(new TaskQueued("T-1"));
                System.out.println("Publisher: phát xong T-1");
            } catch (IllegalStateException ex) {
                System.out.println("Publisher: bắt lỗi " + ex.getMessage());
            }
        }

        System.out.println("=== Có ErrorHandler bỏ qua lỗi ===");

        try (var context =
                     new AnnotationConfigApplicationContext(HandledConfig.class)) {
            context.publishEvent(new TaskQueued("T-2"));
            System.out.println("Publisher: phát xong T-2");
        }
    }

    public static class Listeners {
        @EventListener
        @Order(10)
        public void first(TaskQueued event) {
            System.out.println("Listener 1: " + event.id());
            throw new IllegalStateException("không xử lý được " + event.id());
        }

        @EventListener
        @Order(20)
        public void second(TaskQueued event) {
            System.out.println("Listener 2: " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DefaultConfig {
        @Bean
        public Listeners listeners() {
            return new Listeners();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(DefaultConfig.class)
    public static class HandledConfig {
        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster() {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();
            multicaster.setErrorHandler(error ->
                    System.out.println("ErrorHandler: " + error.getMessage()));
            return multicaster;
        }
    }
}
~~~

Từ thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ListenerExceptionDemo
~~~

Các dòng do chương trình in ra stdout, bỏ qua thông báo riêng của công cụ chạy:

~~~text
=== Mặc định: không có ErrorHandler ===
Listener 1: T-1
Publisher: bắt lỗi không xử lý được T-1
=== Có ErrorHandler bỏ qua lỗi ===
Listener 1: T-2
ErrorHandler: không xử lý được T-2
Listener 2: T-2
Publisher: phát xong T-2
~~~

**Lượt T-1:** `publishEvent(...)` gọi listener 1. Listener 1 ném `IllegalStateException`. Vì không có `ErrorHandler`, exception đến khối `catch` của bên phát; listener 2 không chạy. Dòng “Publisher: phát xong T-1” không xuất hiện.

**Lượt T-2:** `HandledConfig` khai báo bean đặc biệt có tên chính xác `applicationEventMulticaster`. Multicaster này có `ErrorHandler` in lỗi rồi **trả về bình thường**. Do exception đã được handler hấp thụ, multicaster tiếp tục gọi listener 2. `publishEvent(...)` kết thúc bình thường nên in dòng “Publisher: phát xong T-2”.

Trong cả hai trường hợp, **việc gọi listener vẫn đồng bộ**. `setErrorHandler(...)` không tự biến xử lý thành bất đồng bộ. Một lỗi được bỏ qua chỉ làm thay đổi cách xử lý ngoại lệ và việc tiếp tục phân phối.

## 4. Ba cách xử lý exception: để lan truyền, bắt cục bộ, hoặc ErrorHandler

### Cách 1 — Để ngoại lệ truyền về publisher

Dùng cấu hình mặc định và để listener ném một `RuntimeException` khi công việc thất bại:

~~~java
@EventListener
public void validatePayment(PaymentAccepted event) {
    if (!isValid(event)) {
        throw new IllegalStateException("Dữ liệu thanh toán không hợp lệ");
    }
}
~~~

*Đây là mã minh họa đặt trong bean hiện có; `PaymentAccepted` và `isValid` là các thành phần nghiệp vụ cần định nghĩa, không phải chương trình độc lập.*

Hướng này thích hợp khi việc listener thất bại phải khiến luồng nghiệp vụ phát sự kiện thất bại. Tuy nhiên, cần hiểu rằng `publishEvent(...)` lúc này có thể ném exception và ngừng phân phối tới các listener còn lại.

### Cách 2 — Listener tự bắt lỗi mà có thể phục hồi

~~~java
@EventListener
public void updateSearchIndex(ProductChanged event) {
    try {
        searchIndex.update(event.id());
    } catch (SearchBackendUnavailableException ex) {
        logger.warn("Chưa cập nhật chỉ mục cho {}", event.id(), ex);
        // Ghi nhận để retry bằng cơ chế riêng nếu nghiệp vụ cần.
    }
}
~~~

*Đây là mã minh họa với các phụ thuộc nghiệp vụ `searchIndex`, `logger`, `ProductChanged` và `SearchBackendUnavailableException` đã tồn tại.*

Vì method không ném lỗi ra ngoài, multicaster có thể gọi listener tiếp theo. Nhưng việc `publishEvent(...)` trả về bình thường **không chứng minh** rằng cập nhật chỉ mục đã thành công. Nếu nhiệm vụ bắt buộc, cần cơ chế lưu lỗi/retry hoặc chuyển lỗi tới bên phát theo thiết kế.

### Cách 3 — Đặt ErrorHandler ở multicaster

`SimpleApplicationEventMulticaster.setErrorHandler(...)` nhận một `org.springframework.util.ErrorHandler`. Handler được gọi khi listener ném lỗi trong lúc multicaster gọi listener đó. Hai lựa chọn phổ biến:

- **Ghi nhận rồi không ném tiếp:** handler trả về bình thường; lượt phân phối tiếp tục với listener sau.
- **Ghi nhận rồi ném lại:** exception tiếp tục lan ra; với lời gọi đồng bộ, lượt phân phối dừng và bên phát nhận lỗi.

Spring cũng cung cấp các handler tiện dụng như `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` và `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER`. Phải lựa chọn dựa vào ý nghĩa nghiệp vụ, thay vì mặc định nuốt mọi lỗi.

**Phạm vi:** `ErrorHandler` cấu hình trên multicaster xử lý lỗi phát sinh khi multicaster *gọi listener*. Nó không bắt mọi exception tùy ý trong toàn ứng dụng, không thay thế `@ControllerAdvice` và không tự thực hiện rollback hay retry.

## 5. Checked exception, RuntimeException và Error

### RuntimeException

Khi phương thức listener ném `IllegalArgumentException`, `IllegalStateException` hoặc một `RuntimeException` khác, lời gọi `@EventListener` đồng bộ thường truyền lỗi runtime đó ra ngoài tới publisher (trừ khi listener hoặc multicaster đã xử lý).

Đây là trường hợp được minh họa bằng chương trình chạy ở phần trên.

### Checked exception

Một phương thức `@EventListener` có thể khai báo `throws IOException` hoặc loại checked exception khác. Tuy nhiên API phát sự kiện không khai báo những checked exception tùy ý. Theo Javadoc `@EventListener`, khi một phương thức listener có checked exception, Spring bọc nó trong `java.lang.reflect.UndeclaredThrowableException` trước khi chuyển lỗi ra ngoài.

Ví dụ minh họa (không phải chương trình độc lập):

~~~java
@EventListener
public void importFile(FileImported event) throws java.io.IOException {
    throw new java.io.IOException("Không đọc được tệp");
}
~~~

Ở publisher, không thể giả định một lời gọi `publishEvent(...)` trực tiếp ném `IOException`; cần xử lý ngoại lệ runtime tương ứng và tìm nguyên nhân gốc (`getCause()`) nếu cần. Không bắt `Exception` rồi bỏ qua toàn bộ lỗi chỉ để giữ luồng chạy.

### Error

`Error`, ví dụ lỗi nghiêm trọng của JVM, thuộc nhánh `Throwable` nhưng không phải `Exception`. `SimpleApplicationEventMulticaster` khi có `ErrorHandler` sẽ đưa `Throwable` bắt được tới handler. Điều đó **không** có nghĩa ứng dụng nên cố nuốt lỗi nghiêm trọng: các lỗi kiểu này thường không an toàn để phục hồi.

## 6. Exception của listener đồng bộ và @Transactional

Một tác động quan trọng xuất hiện khi bên phát nằm trong phương thức `@Transactional`. Nếu sự kiện được phát ngay **bên trong** phương thức giao dịch, listener đồng bộ mặc định cũng chạy trong cùng luồng khi giao dịch còn đang hoạt động.

~~~text
@Transactional serviceMethod()
    |
    | thay đổi dữ liệu trong giao dịch
    |
    | publishEvent(event)
    |      |
    |      +-- synchronous listener ném RuntimeException
    |
    +-- ngoại lệ tiếp tục thoát khỏi serviceMethod()
           |
           +-- TransactionInterceptor áp dụng quy tắc rollback
~~~

Với mặc định của Spring Transaction Management, `@Transactional` đánh dấu rollback khi `RuntimeException` hoặc `Error` thoát khỏi lời gọi phương thức được quản lý giao dịch. Vì vậy, **ngoại lệ runtime từ listener đồng bộ có thể khiến giao dịch của bên phát rollback**, nếu ngoại lệ tiếp tục lan qua ranh giới phương thức giao dịch.

Cần tách rõ bốn trường hợp:

| Tình huống | Hệ quả thường gặp |
| --- | --- |
| Listener ném `RuntimeException`; không ai bắt; lỗi thoát qua proxy `@Transactional` | Giao dịch được đánh dấu rollback theo quy tắc mặc định. |
| Publisher bắt lỗi trong phương thức rồi tiếp tục bình thường | Không tự động rollback chỉ vì trước đó có listener ném lỗi; kết quả còn tùy trạng thái giao dịch và cấu hình. |
| `ErrorHandler` hấp thụ lỗi và trả về bình thường | Bên phát thường không nhận ngoại lệ; không thể xem đó là lý do tự động rollback. |
| Listener đã gọi API ngoài hoặc ghi vào tài nguyên không tham gia transaction | Rollback cơ sở dữ liệu không tự hoàn tác tác dụng bên ngoài. |

Ví dụ, nếu nghiệp vụ đã gọi hệ thống giao hàng rồi listener sau ném lỗi, rollback bản ghi SQL **không** có nghĩa lệnh gọi bên ngoài bị hủy. Đó là lý do cần thiết kế ranh giới giao dịch và hành động phụ một cách chủ động.

**Không nhầm với `@TransactionalEventListener`.** Cơ chế này gắn xử lý với pha giao dịch như `AFTER_COMMIT` và có quy tắc riêng; lỗi xảy ra sau khi commit không thể đảo ngược giao dịch đã commit. Đây là một kiểu listener khác với ví dụ `@EventListener` đồng bộ chạy ngay tại `publishEvent(...)`.

## 7. Nên xử lý ở đâu?

| Nhu cầu | Lựa chọn cân nhắc |
| --- | --- |
| Listener thực hiện một bước bắt buộc để nghiệp vụ thành công | Để lỗi lan truyền hoặc gọi trực tiếp thành phần bắt buộc khi cần kết quả rõ ràng. |
| Listener chỉ tạo log/thống kê phụ trợ | Bắt lỗi trong listener hoặc dùng `ErrorHandler` có ghi nhận lỗi, tùy phạm vi muốn áp dụng. |
| Một listener lỗi nhưng các listener khác vẫn phải chạy | Dùng `ErrorHandler` không ném lại, hoặc tự bắt lỗi ở listener; phải có nơi quan sát thất bại. |
| Cần retry, bảo đảm giao sự kiện, hoặc xử lý giữa nhiều tiến trình | Dùng hàng đợi, outbox hoặc cơ chế lưu công việc bền vững phù hợp; Application Events mặc định không cung cấp các bảo đảm đó. |
| Chỉ muốn giảm thời gian chờ của publisher | Xem `@Async` hoặc executor, nhưng phải thay đổi cách xử lý lỗi và bối cảnh luồng; đó là chủ đề khác với exception đồng bộ. |

Hãy quyết định dựa vào câu hỏi: *“Nếu công việc listener thất bại, thao tác gốc có còn được coi là thành công không?”* Câu trả lời xác định có nên để lỗi lan về publisher, bắt lỗi tại listener, hay hấp thụ lỗi tại multicaster.

## 8. Những hiểu nhầm cần tránh

1. **“Exception trong listener chỉ được ghi log.”** Sai với mặc định: exception chưa xử lý được truyền về publisher và dừng lượt phân phối.
2. **“Một listener lỗi thì mọi listener trước đó được rollback.”** Sai: không có hoàn tác tự động toàn bộ side effect; chỉ các tài nguyên thực sự nằm trong transaction phù hợp mới có thể rollback theo quy tắc của transaction.
3. **“Bắt exception trong publisher bảo đảm trạng thái đã an toàn.”** Chưa chắc: các listener trước đó có thể đã tạo thay đổi không thể hoàn tác, và listener còn lại có thể chưa chạy.
4. **“Cấu hình ErrorHandler luôn làm publisher thất bại.”** Chỉ khi handler ném lại lỗi (hoặc chính handler phát sinh lỗi). Handler trả về bình thường cho phép multicaster tiếp tục.
5. **“Dùng `@Order` khiến toàn bộ listener được gọi dù có lỗi.”** Sai: `@Order` chỉ điều chỉnh thứ tự; nó không giải quyết ngoại lệ.
6. **“Listener đồng bộ giống listener có `@Async`.”** Sai: ngoại lệ từ phương thức `@Async` thường được xử lý trong luồng bất đồng bộ và không truyền trực tiếp về publisher như ví dụ đồng bộ.

## 9. Bài tập tự kiểm tra

**Tình huống A.** Ba listener được gọi theo thứ tự A → B → C. A chạy thành công; B ném `IllegalStateException`; multicaster giữ mặc định. Listener nào đã chạy và ai nhận lỗi?

**Đáp án:** A và B đã được gọi; C chưa được gọi. Ngoại lệ từ B truyền tới lời gọi `publishEvent(...)` của bên phát nếu không có nơi xử lý trung gian.

**Tình huống B.** Cũng ba listener như trên, nhưng cấu hình một `ErrorHandler` ghi log rồi trả về bình thường. Điều gì thay đổi?

**Đáp án:** Sau khi xử lý ngoại lệ của B, multicaster tiếp tục gọi C. Bên phát có thể thấy `publishEvent(...)` kết thúc bình thường mặc dù B thất bại; vì vậy cần log/metric hoặc cơ chế khôi phục lỗi riêng.

**Tình huống C.** Bên phát chạy trong `@Transactional`, còn listener B ném `RuntimeException`. Có chắc chắn mọi tác dụng phụ được rollback không?

**Đáp án:** Không. Với lỗi thoát qua proxy và quy tắc rollback mặc định, giao dịch cơ sở dữ liệu liên quan có thể rollback. Tác dụng phụ ngoài transaction (email, HTTP, file, dịch vụ khác) không tự được hoàn tác; việc bắt lỗi hoặc cấu hình handler cũng có thể thay đổi kết quả giao dịch.

## Tài liệu tham khảo

- [Spring Framework 6.2.9 — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): mặc định gọi đồng bộ, `setErrorHandler`, cách lỗi lan truyền và dừng phân phối.
- [Spring Framework — @EventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html): exception từ phương thức listener và việc bọc checked exception.
- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): cơ chế phát và xử lý sự kiện trong context.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): quy tắc rollback mặc định của `@Transactional`.
