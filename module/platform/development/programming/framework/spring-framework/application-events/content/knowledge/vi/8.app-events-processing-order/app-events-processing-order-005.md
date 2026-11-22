# Thứ tự không đảm bảo khi chạy bất đồng bộ trong Spring Application Events

## 1. Vấn đề cần hiểu

Khi một sự kiện được phát qua `ApplicationEventPublisher.publishEvent(...)`, Spring tìm các listener phù hợp để xử lý. Ở chế độ mặc định, `SimpleApplicationEventMulticaster` gọi listener **đồng bộ trên luồng phát sự kiện**. Với các listener đồng bộ của cùng một sự kiện, `@Order` có thể chỉ định listener nào được **gọi trước** (giá trị nhỏ có độ ưu tiên cao hơn).

Khi listener xử lý **bất đồng bộ**, thứ tự gọi/gửi công việc và thứ tự **bắt đầu hoặc hoàn tất công việc** là hai khái niệm khác nhau. Dù Spring gọi listener A có `@Order(1)` trước B có `@Order(2)`, A có thể mất nhiều thời gian hơn, chờ I/O hoặc chưa được cấp CPU, nên B có thể hoàn tất trước A. **Không được dùng `@Order` như cơ chế bảo đảm thứ tự hoàn tất của các listener bất đồng bộ.**

Ví dụ nghiệp vụ: một sự kiện `OrderPlaced` kích hoạt hai tác vụ gửi email xác nhận và cập nhật hệ thống báo cáo. Nếu chạy song song, hệ thống báo cáo có thể cập nhật xong trước khi email được gửi. Điều này có thể hoàn toàn chấp nhận được. Nhưng nếu tác vụ B bắt buộc sử dụng kết quả mà A tạo ra, thiết kế hai listener bất đồng bộ độc lập sẽ dễ gây race condition.

## 2. Ba loại thứ tự cần phân biệt

| Loại thứ tự | Câu hỏi | Với các listener `@Async` chạy trên nhiều thread |
| --- | --- | --- |
| Gọi/đưa task vào executor | Listener nào được Spring gọi để gửi task trước? | `@Order` giúp sắp xếp thứ tự gọi listener trong quá trình phát **một** sự kiện; nó không buộc các task chạy tuần tự. |
| Bắt đầu chạy | Thread thực sự bắt đầu thực hiện thân hàm listener nào trước? | Không có bảo đảm chung: phụ thuộc lịch chạy thread, executor, tải hệ thống và hàng đợi. |
| Hoàn tất và có hiệu lực nghiệp vụ | Listener nào lưu dữ liệu, gửi request hoặc kết thúc trước? | Không có bảo đảm chung: độ trễ I/O, retry, lock và lỗi có thể đảo thứ tự. |

Với **nhiều lần phát sự kiện**, ngay cả thứ tự các lệnh `publishEvent` trong ứng dụng cũng không tự tạo ra thứ tự xử lý toàn cục nếu có nhiều publisher/thread hoặc nhiều executor.

### Hai cách chạy bất đồng bộ phổ biến

1. **`@Async` trên phương thức `@EventListener`:** Spring đăng ký listener và khi listener được gọi, cơ chế proxy `@Async` gửi phần thân phương thức sang `TaskExecutor`. Cần bật `@EnableAsync` và có executor phù hợp. Nếu listener chỉ là `@EventListener` thông thường, mặc định nó đồng bộ.
2. **Executor cho toàn bộ event multicaster:** định nghĩa bean tên `applicationEventMulticaster` và cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)`. Khi ấy multicaster có thể phân phối các listener hỗ trợ async sang thread khác; một số listener yêu cầu xử lý đồng bộ vẫn có thể chạy trên thread phát sự kiện (phụ thuộc hợp đồng `supportsAsyncExecution` của listener).

Cả hai cách đều không mặc nhiên bảo đảm thứ tự **hoàn tất**. Không cần bật cả hai chỉ để làm một listener bất đồng bộ: hãy chọn cơ chế thực thi rõ ràng để tránh khó kiểm soát executor và ngữ cảnh.

## 3. Ví dụ Java 17+: `@Order(2)` hoàn tất trước `@Order(1)`

Ví dụ dưới đây sử dụng **Spring Framework 6.2.x**, Java 17+ và Maven. Hai listener nhận cùng một sự kiện và chạy trên executor hai thread. Listener A (`@Order(1)`) cố ý đợi tín hiệu từ main; B (`@Order(2)`) có thể hoàn tất trong khi A còn đợi. `CountDownLatch` giúp chứng minh kết quả một cách có kiểm soát, thay vì dựa vào `Thread.sleep` và xác suất chạy đua.

Tạo cấu trúc:

~~~text
async-event-order/
├── pom.xml
└── src/main/java/demo/AsyncOrderDemo.java
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-event-order</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/AsyncOrderDemo.java`:**

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncOrderDemo {
    public record OrderPlaced(String orderId) {}

    public static class Gates {
        final CountDownLatch aStarted = new CountDownLatch(1);
        final CountDownLatch releaseA = new CountDownLatch(1);
        final CountDownLatch aCompleted = new CountDownLatch(1);
        final CountDownLatch bCompleted = new CountDownLatch(1);
    }

    @Configuration
    @EnableAsync
    public static class Config {
        @Bean
        public Gates gates() {
            return new Gates();
        }

        @Bean("eventExecutor")
        public Executor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("event-");
            return executor; // Spring tự khởi tạo và đóng bean này
        }

        @Bean
        public Listeners listeners(Gates gates) {
            return new Listeners(gates);
        }
    }

    public static class Listeners {
        private final Gates gates;

        public Listeners(Gates gates) {
            this.gates = gates;
        }

        @Async("eventExecutor")
        @EventListener
        @Order(1)
        public void listenerA(OrderPlaced event) {
            gates.aStarted.countDown();
            try {
                gates.releaseA.await();
                System.out.println("A: hoan tat @Order(1)");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Listener A bi ngat", ex);
            } finally {
                gates.aCompleted.countDown();
            }
        }

        @Async("eventExecutor")
        @EventListener
        @Order(2)
        public void listenerB(OrderPlaced event) {
            System.out.println("B: hoan tat @Order(2)");
            gates.bCompleted.countDown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            Gates gates = context.getBean(Gates.class);

            try {
                context.publishEvent(new OrderPlaced("O-100"));

                boolean aStarted = gates.aStarted.await(5, TimeUnit.SECONDS);
                boolean bFinished = gates.bCompleted.await(5, TimeUnit.SECONDS);
                if (!aStarted || !bFinished) {
                    throw new IllegalStateException("Listener khong hoat dong dung han");
                }
                if (gates.aCompleted.getCount() != 1) {
                    throw new AssertionError("A khong con o trang thai cho");
                }

                System.out.println("Main: B da xong, A van dang cho");
            } finally {
                // Luon giai phong A, ke ca khi kiem tra bi loi.
                gates.releaseA.countDown();
            }

            if (!gates.aCompleted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("A khong ket thuc dung han");
            }
        }
    }
}
~~~

Lệnh chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncOrderDemo
~~~

Các dòng `stdout` chính của chương trình (thứ tự được các latch chủ động kiểm soát):

~~~text
B: hoan tat @Order(2)
Main: B da xong, A van dang cho
A: hoan tat @Order(1)
~~~

**Diễn giải:** B chỉ đếm `bCompleted` sau khi in xong. Main đợi B hoàn tất và kiểm tra A chưa hoàn tất; sau khi in kết luận, main mới mở `releaseA`. Vì thế ví dụ thể hiện một lịch chạy hợp lệ mà listener có độ ưu tiên gọi thấp hơn lại **hoàn tất trước**. Trong ứng dụng thực, delay đến từ CPU, network, database, retry hoặc tác vụ khác; không cần có latch thì hiện tượng đảo thứ tự vẫn có thể xảy ra.

> Lưu ý: mã này dùng latch để **minh họa và kiểm chứng**, không dùng latch chặn thread để “sửa” thứ tự trong ứng dụng production. Khi thiết kế production, cần biểu diễn phụ thuộc nghiệp vụ bằng luồng xử lý rõ ràng.

## 4. `@Order` bảo đảm điều gì và không bảo đảm điều gì?

Với cấu hình multicaster mặc định **đồng bộ**, listener `@Order(1)` được gọi trước `@Order(2)` khi cùng đủ điều kiện nhận một sự kiện; vì lần gọi trước chạy hết rồi mới gọi tiếp, thứ tự hoàn tất theo thứ tự gọi trong trường hợp các listener đều kết thúc bình thường. Một exception chưa được xử lý có thể ngăn listener sau chạy.

Với listener `@Async`, lần gọi mà multicaster nhìn thấy chủ yếu là việc gửi task đến executor. `@Order(1)` có thể được **submit** trước, nhưng A và B chạy trên những thread khác nhau. Do đó không được suy ra “A hoàn tất trước B” từ `@Order(1)` và `@Order(2)`.

Với multicaster cấu hình `TaskExecutor`, điều tương tự xảy ra: việc **lên lịch** listener có thể theo thứ tự, nhưng hoàn tất vẫn chịu chi phối bởi executor và thời gian xử lý. Ngoài ra, không mặc định mọi listener đều chấp nhận thực thi bất đồng bộ.

| Cấu hình | Có thể kỳ vọng thứ tự thực thi/hoàn tất? |
| --- | --- |
| Listener đồng bộ, multicaster mặc định, `@Order` khác nhau | Có, trong phạm vi một lần phát event, khi listener chạy thành công và không tự chuyển việc sang task khác. |
| Hai listener `@Async`, executor nhiều thread | Không: hoàn tất có thể đảo thứ tự. |
| Multicaster dùng executor nhiều thread | Không: các listener được phép async có thể chạy song song. |
| Một executor một thread cho các task liên quan | Các task thực sự vào cùng hàng đợi và được xử lý tuần tự; vẫn phải xét thứ tự task được gửi vào, nhiều publisher, retry, nhiều instance và tác dụng phụ ở hệ thống ngoài. |

## 5. Cách thiết kế khi nghiệp vụ cần đúng thứ tự

**Trường hợp A — Hai bước có phụ thuộc trực tiếp:** Gom chúng vào **một luồng điều phối** với thứ tự rõ ràng. Có thể chạy bất đồng bộ cả luồng, nhưng bên trong thực hiện A xong mới đến B:

~~~java
// Minh họa phần thân một listener; cần khai báo thành bean Spring
// và bật @EnableAsync nếu dùng @Async.
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    reserveInventory(event);  // Chạy xong hoặc thất bại rõ ràng
    chargePayment(event);     // Chỉ gọi sau khi bước trước hoàn tất
}
~~~

Đoạn trên là **mã minh họa**, không phải chương trình độc lập. Nếu bước A trả về `CompletableFuture`, có thể dùng `thenCompose` để liên kết bước B với việc A thành công; cần xử lý exception và retry trong chuỗi. Đối với tác vụ liên quan cơ sở dữ liệu và giao dịch, xác định thời điểm commit và chiến lược xử lý khi A thành công nhưng B thất bại.

**Trường hợp B — Cần tuần tự trên một hàng đợi:** Dùng executor một thread hoặc queue/consumer có thứ tự phù hợp. Điều này tuần tự hóa các task **được đưa vào đúng cùng executor/partition**, nhưng không tự bảo đảm thứ tự theo thời gian phát sinh giữa nhiều publisher hoặc nhiều instance. Tránh tự nhận “có thứ tự toàn cục” khi kiến trúc phân tán không thực sự có điều kiện đó.

**Trường hợp C — Các tác vụ độc lập:** Giữ xử lý song song; thiết kế listener **idempotent**, có retry phù hợp, khóa nghiệp vụ/sequence number hoặc kiểm tra version khi ghi dữ liệu chung. Nếu một event đến trễ, listener phải biết cách bỏ qua bản cập nhật cũ hoặc hòa giải trạng thái.

**Trường hợp D — Cần thứ tự xuyên dịch vụ:** Dùng quy trình có điều phối, hoặc message broker có khả năng thứ tự theo **một khóa nghiệp vụ** với consumer/partition thích hợp. Thứ tự enqueue, thứ tự consume và thứ tự commit vẫn cần được xác định riêng. Không dựa vào `@Order` của Spring để bảo đảm thứ tự giữa các service.

## 6. Rủi ro kỹ thuật thường bị bỏ sót

- **Không chờ kết quả bằng `publishEvent`:** Khi listener async, `publishEvent(...)` có thể trả về trước khi listener hoàn tất. Không đọc ngay kết quả từ database rồi giả định tác vụ đã chạy xong. Nếu cần chờ, hãy dùng cơ chế phản hồi/đồng bộ được thiết kế rõ ràng.
- **Exception:** Exception từ `@Async` listener trả về `void` không tự truyền về thread gọi `publishEvent`. Cần logging/metrics, `AsyncUncaughtExceptionHandler`, hoặc thiết kế kết quả và retry phù hợp. Exception của listener đồng bộ có ngữ nghĩa khác.
- **Transaction và thread context:** Async không tự mang theo transaction, `ThreadLocal`, request context hoặc logging MDC của publisher. `@TransactionalEventListener(phase = AFTER_COMMIT)` điều khiển *thời điểm* nhận sau commit, không tự bảo đảm thứ tự hoàn tất giữa những listener async. Nếu cần thông tin định danh/truy vết, truyền correlation ID trong event hoặc cấu hình context propagation có kiểm soát.
- **Giới hạn executor:** Pool và queue hữu hạn có thể bị nghẽn hoặc từ chối task khi tải cao. Thiết kế cách xử lý rejection, shutdown và giám sát độ trễ; đừng xem “đã phát event” đồng nghĩa “đã xử lý thành công”.
- **Event dạng mutable:** Không để nhiều listener ghi chung vào cùng một đối tượng mutable mà thiếu đồng bộ. Ưu tiên immutable event chứa dữ liệu đã chốt, ví dụ Java `record`.
- **Kiểm thử sai cách:** Một vài lần chạy cho ra A trước B không chứng minh hệ thống luôn đúng thứ tự. Dùng `CountDownLatch`, `CompletableFuture` và kiểm tra các trạng thái/điểm đồng bộ để tạo được kịch bản tranh chấp; tránh `Thread.sleep` làm “bằng chứng” bảo đảm thứ tự.

## 7. Checklist chọn chiến lược

1. Hai listener **có phụ thuộc dữ liệu** không? Nếu có, thiết kế chuỗi xử lý/điều phối thay vì dựa vào thứ tự các callback async.
2. Đang cần thứ tự **gọi**, **bắt đầu**, **hoàn tất**, hay **ghi bền vững**? Viết rõ yêu cầu bằng hợp đồng nghiệp vụ.
3. Có bao nhiêu executor, thread, publisher và instance? Một thread trong một process chưa giải quyết thứ tự trên toàn hệ thống.
4. Có timeout, lỗi, retry hoặc dữ liệu đến trễ không? Bổ sung idempotency, version/sequence và quan sát lỗi.
5. Kiểm thử đã chủ động mô phỏng B xong trước A, trễ network, nhiều publisher và shutdown chưa?

**Ghi nhớ:** `@Order` giúp sắp xếp việc **gọi listener**; `@Async` làm phần việc chạy ở thời điểm khác. Nếu thứ tự **hoàn tất** có ý nghĩa nghiệp vụ, hãy thể hiện phụ thuộc bằng luồng điều phối, hàng đợi có ràng buộc hoặc cơ chế phiên bản hóa thay vì trông đợi vào lịch chạy thread.

## Tài liệu chính thức

- Spring Framework — ApplicationContext, Asynchronous Listeners, Ordering Listeners, ApplicationEventMulticaster: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — Task Execution and Scheduling, `@Async`, executor và xử lý exception: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — Observability/Context Propagation với Application Events: https://docs.spring.io/spring-framework/reference/integration/observability.html
