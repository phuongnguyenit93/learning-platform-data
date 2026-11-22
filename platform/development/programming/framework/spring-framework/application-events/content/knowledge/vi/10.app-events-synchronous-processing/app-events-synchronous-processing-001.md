# Listener chạy trên thread của publisher trong Spring Application Events

## 1. Ý nghĩa của xử lý đồng bộ

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(event)` gửi một sự kiện vào cơ chế phân phối sự kiện của `ApplicationContext`. Với cấu hình mặc định của `SimpleApplicationEventMulticaster`, các listener đồng bộ được gọi **trực tiếp trên thread đang thực hiện lệnh `publishEvent(...)`**. Thread đó được gọi là **thread của publisher**.

Điểm cần nhớ:

- **Publisher** là đoạn mã phát sự kiện bằng `publishEvent`; publisher có thể là controller, service, một scheduled task, một message consumer hoặc một thread do ứng dụng tạo.
- **Listener** là callback nhận sự kiện, chẳng hạn một phương thức có `@EventListener` hoặc một bean triển khai `ApplicationListener`.
- **Đồng bộ** nghĩa là publisher đi vào listener và chờ callback hoàn thành trước khi tiếp tục sau `publishEvent`. Theo cấu hình mặc định, không có thread mới chỉ vì sử dụng Spring Events.
- **“Cùng thread với publisher” không có nghĩa luôn là thread `main`**. Nếu code phát sự kiện chạy trong thread HTTP request hoặc thread worker, listener đồng bộ chạy ngay trên chính thread đó.

Đây là hành vi mặc định phổ biến của Spring Application Events; `publishEvent` là cách chuyển sự kiện cho cơ chế xử lý, **không phải lời hứa rằng mọi cấu hình hay mọi loại listener đều chạy đồng bộ**. `@Async`, executor tùy chỉnh cho multicaster và các listener theo pha transaction có thể thay đổi thời điểm hoặc thread thực thi.

## 2. Luồng gọi trên một thread

Với các listener thông thường và multicaster đồng bộ mặc định, cấu trúc lời gọi cho **một** lần phát sự kiện có thể hình dung như sau:

~~~text
Thread P (đang gọi publishEvent)
  |
  +-- service gọi publisher.publishEvent(new OrderPlaced(...))
          |
          +-- ApplicationContext / ApplicationEventMulticaster
                  |
                  +-- Listener A: xử lý xong
                  |
                  +-- Listener B: xử lý xong
          |
  +-- publishEvent trả về
  |
  +-- service chạy câu lệnh tiếp theo
~~~

Các mũi gọi trên đều nằm trong **call stack của thread P** khi các listener được thực thi đồng bộ. Trong cùng lần phát một sự kiện, listener có `@Order` với giá trị thấp hơn có thể được gọi trước; nếu đều đồng bộ và chạy thành công thì callback trước hoàn tất trước khi callback sau bắt đầu.

Ví dụ: nếu listener A mất 150 ms và listener B mất 80 ms, phần thời gian thực thi tuần tự của chúng góp khoảng 230 ms vào độ trễ của lời gọi phát sự kiện, chưa kể overhead. Publisher không thể coi việc “phát xong” là tức thời khi có listener đồng bộ chạy lâu.

**Hệ quả:** Nếu listener ném exception chưa được xử lý, exception thường truyền về caller của `publishEvent`, và những listener sau có thể chưa được gọi. Việc cấu hình `ErrorHandler` cho multicaster có thể thay đổi cách xử lý lỗi. Không nên giả định tất cả listener luôn chạy xong trong mọi kịch bản lỗi.

## 3. Ví dụ Java 17+ có thể chạy: listener dùng đúng thread đã phát sự kiện

Ví dụ sử dụng **Spring Framework 6.2.x**, Java 17+ và Maven. Chúng ta lần lượt phát sự kiện từ thread được đặt tên `publisher-main` và một thread khác tên `publisher-worker`. Mỗi sự kiện được xử lý bởi hai listener đồng bộ, sau đó publisher mới in dòng `after publish`.

### 3.1. Cấu trúc dự án

~~~text
spring-sync-event/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SynchronousEventDemo.java
~~~

Tạo tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-sync-event</artifactId>
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

Tạo tệp `src/main/java/demo/SynchronousEventDemo.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class SynchronousEventDemo {

    // Payload thuần dữ liệu, không mang thread hoặc trạng thái có thể sửa.
    public record StockChanged(String sku) {}

    @Configuration
    public static class Config {
        @Bean
        public StockListeners stockListeners() {
            return new StockListeners();
        }
    }

    public static class StockListeners {

        @EventListener
        @Order(1)
        public void audit(StockChanged event) {
            log("listener-audit", event.sku());
        }

        @EventListener
        @Order(2)
        public void updateCache(StockChanged event) {
            log("listener-cache", event.sku());
        }
    }

    private static void log(String action, String sku) {
        System.out.printf(
                "%s | thread=%s | sku=%s%n",
                action,
                Thread.currentThread().getName(),
                sku
        );
    }

    private static void publish(
            AnnotationConfigApplicationContext context, String sku) {
        log("before publish", sku);
        context.publishEvent(new StockChanged(sku));
        log("after publish", sku);
    }

    public static void main(String[] args) throws InterruptedException {
        Thread.currentThread().setName("publisher-main");

        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            // Lần 1: publisher nằm trên thread chạy phương thức main.
            publish(context, "SKU-104");

            // Lần 2: publisher nằm trên một worker thread do ta tạo.
            Thread worker = new Thread(
                    () -> publish(context, "SKU-105"),
                    "publisher-worker"
            );
            worker.start();
            worker.join();
        }
    }
}
~~~

Chạy trong thư mục `spring-sync-event`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SynchronousEventDemo
~~~

Các dòng kết quả do chương trình tự in (không tính log Maven nếu môi trường có thêm log):

~~~text
before publish | thread=publisher-main | sku=SKU-104
listener-audit | thread=publisher-main | sku=SKU-104
listener-cache | thread=publisher-main | sku=SKU-104
after publish | thread=publisher-main | sku=SKU-104
before publish | thread=publisher-worker | sku=SKU-105
listener-audit | thread=publisher-worker | sku=SKU-105
listener-cache | thread=publisher-worker | sku=SKU-105
after publish | thread=publisher-worker | sku=SKU-105
~~~

### 3.2. Giải thích kết quả

1. Lần phát `SKU-104` diễn ra trên `publisher-main`; cả hai listener đều in cùng tên thread đó. Dòng `after publish` chỉ xuất hiện sau hai callback.
2. Lần phát `SKU-105` diễn ra trên `publisher-worker`; hai listener cũng chạy trên **worker thread này**, không quay về `publisher-main`.
3. `worker.join()` chỉ giúp main đợi worker xong để đóng Spring context an toàn trong ví dụ; **không phải cơ chế làm cho event listener chạy đồng bộ**.
4. `@Order(1)` và `@Order(2)` chủ yếu giúp minh họa thứ tự gọi khi có nhiều listener. Chúng **không tạo thread mới** và cũng không phải điều kiện để Spring chạy đồng bộ.
5. Chương trình không cấu hình executor cho event multicaster và không có `@Async`, nên hoạt động theo đường đi mặc định: gọi listener trực tiếp trên thread phát sự kiện.

Tên thread được dùng để quan sát trong log; trong ứng dụng thực tế, không sử dụng **tên thread** như một hợp đồng xác định thứ tự hay quyền truy cập dữ liệu. Một thread có thể được đổi tên, còn nhiều thread khác nhau có thể được đặt cùng tên.

## 4. Phân biệt thread publisher với thread của request và thread main

Trong ứng dụng Spring, “publisher thread” có nghĩa đơn giản là **thread đang chạy đoạn code gọi `publishEvent` tại thời điểm đó**. Các trường hợp thường gặp:

| Nơi gọi `publishEvent` | Thread publisher thực tế | Listener đồng bộ mặc định |
| --- | --- | --- |
| Trong `main` | Thread hiện tại chạy `main` | Chạy trên thread đó |
| Trong phương thức xử lý HTTP request (Spring MVC) | Thread đang phục vụ request | Chạy trên cùng request thread |
| Trong phương thức `@Scheduled` | Thread của scheduler đang thực thi phương thức | Chạy trên cùng scheduler thread |
| Trong `@Async` service method | Thread của executor đang chạy method | Chạy trên thread executor đó |
| Trong một Kafka/JMS consumer callback | Thread đang gọi callback (theo container) | Chạy trên thread callback đó |
| Trong một `new Thread(...)` | Thread ứng dụng vừa tạo | Chạy trên thread đó |

Không suy ra listener chạy trên main thread chỉ vì ứng dụng khởi tạo từ `main`. Cũng không suy ra listener là bất đồng bộ chỉ vì publisher chạy trong thread nền: có thể **toàn bộ lời gọi publish và listener vẫn đồng bộ tương đối với thread nền ấy**.

### Trong HTTP request

Giả sử một controller gọi service, service lưu dữ liệu rồi `publishEvent`; listener đồng bộ kiểm tra quyền, cập nhật chỉ mục hoặc gọi dịch vụ từ xa. Request thread sẽ chờ listener xử lý trước khi service tiếp tục. Vì vậy, listener đồng bộ có thể làm tăng response time, giữ tài nguyên request và làm giảm throughput nếu chạy chậm.

### Trong luồng nền

Nếu một scheduled job đang phát event từ một scheduler thread duy nhất, listener đồng bộ chạy lâu sẽ kéo dài chính lần chạy job đó. Điều này ảnh hưởng thời gian bắt đầu các nhiệm vụ kế tiếp tùy cấu hình scheduler. Tính đồng bộ của Spring Event không biến tác vụ thành hàng đợi bền vững hay tiến trình nền độc lập.

## 5. Vì sao listener mặc định chạy cùng thread?

`ApplicationContext` dùng `ApplicationEventMulticaster` để tìm và gọi các listener phù hợp. Với mặc định `SimpleApplicationEventMulticaster` **không có `TaskExecutor` bất đồng bộ**, mỗi listener đủ điều kiện được gọi ngay trong quá trình `multicastEvent`. Lời gọi này tiếp tục sử dụng call stack hiện hành nên không có bước chuyển giao sang thread khác.

Có thể hình dung (mã giả, không phải source nội bộ Spring):

~~~java
// MÃ GIẢ để hiểu cơ chế đồng bộ, không dùng nguyên đoạn này để build.
void publishEvent(Object event) {
    for (ApplicationListener<?> listener : matchingListeners(event)) {
        invokeSynchronously(listener, event);
    }
}
~~~

Hàm `invokeSynchronously` minh họa việc gọi callback thông thường. Thực tế Spring còn có đăng ký và lọc listener, sắp thứ tự, xử lý generic event types và chiến lược lỗi. Mấu chốt là không cần `Thread.start()` hoặc `Executor.execute(...)` trong đường đi mặc định đồng bộ.

Các annotation `@EventListener` giúp Spring nhận diện phương thức callback và tạo bộ thích ứng listener; riêng `@EventListener` **không tự kích hoạt async**.

## 6. Khi nào cùng thread không còn đúng?

### 6.1. `@Async` trên listener

Khi bật `@EnableAsync`, cấu hình executor và đánh dấu phương thức `@EventListener` bằng `@Async`, phần thân listener có thể được chuyển sang một thread của executor:

~~~java
// Chỉ là ví dụ cấu hình/annotation: cần @EnableAsync và executor phù hợp.
@Async("eventExecutor")
@EventListener
public void onStockChanged(StockChanged event) {
    // Có thể chạy trên thread khác với thread gọi publishEvent.
    sendNotification(event.sku());
}
~~~

Đây là **đoạn mã minh họa**, không phải tệp Java độc lập. Trong mô hình này, lời gọi `publishEvent` thường chỉ gửi task và không đợi phần thân listener kết thúc. Vì vậy, việc đọc ngay dữ liệu do listener async cập nhật có thể cho kết quả cũ. Exception trong listener `@Async void` không tự quay lại thread publisher theo cách exception đồng bộ.

### 6.2. Executor trên event multicaster

Ứng dụng có thể đăng ký bean `applicationEventMulticaster` dùng `SimpleApplicationEventMulticaster.setTaskExecutor(...)`. Các listener **hỗ trợ async execution** có thể được multicaster gửi vào executor và chạy ở thread khác. Một số listener có hợp đồng yêu cầu đồng bộ; không được cho rằng mọi listener đều bị chuyển sang executor chỉ vì multicaster có executor.

### 6.3. `@TransactionalEventListener`

`@TransactionalEventListener` có hành vi phụ thuộc phase giao dịch, mặc định là `AFTER_COMMIT`. Khi có transaction, lời gọi listener có thể bị **hoãn đến phase transaction tương ứng**, nên nó không chạy ngay tại lệnh `publishEvent` như một `@EventListener` thông thường. Nếu không có transaction, mặc định listener này có thể không được gọi (trừ khi bật `fallbackExecution`). Vì vậy, cần tách biệt **thời điểm thực thi** với vấn đề **chạy trên thread nào**.

### 6.4. Listener tự mở task nền

Một listener đồng bộ cũng có thể tự gọi `CompletableFuture.runAsync(...)`, gửi job sang executor, gọi broker hoặc trigger một HTTP request rồi trả về. Khi đó phần callback trực tiếp vẫn đồng bộ, nhưng **công việc con** có thể tiếp tục sau khi `publishEvent` trả về. Không nên suy luận rằng toàn bộ tác dụng phụ của listener đã hoàn tất chỉ từ việc callback trả về.

## 7. Hệ quả đối với hiệu năng, lỗi và transaction

### 7.1. Độ trễ và tài nguyên

Publisher phải chờ callback đồng bộ. Các listener xử lý CPU lâu, đọc ghi database, gọi HTTP hoặc giữ lock có thể làm chậm request, scheduled job hay consumer đang publish. Nếu cần tác vụ chạy lâu, cân nhắc async có kiểm soát hoặc hệ thống hàng đợi; lựa chọn dựa trên yêu cầu độ trễ, độ tin cậy và thứ tự nghiệp vụ.

Không chuyển mọi listener sang async chỉ vì muốn giảm latency. Async còn có chi phí hàng đợi, rủi ro task rejection, ngữ cảnh thread/transaction và việc theo dõi thất bại.

### 7.2. Exception truyền về publisher

Với listener đồng bộ thông thường và multicaster không có `ErrorHandler` tùy chỉnh, exception chưa được xử lý tại listener có thể làm `publishEvent` ném lỗi lên caller. Các listener được sắp sau listener lỗi có thể không được gọi trong lần multicast đó. Lưu ý `@Order` sắp thứ tự callback nhưng **không tự bảo đảm retry**, rollback hoặc tất cả listener sẽ được gọi khi có lỗi.

Nếu listener thực hiện side effect rồi ném exception, publisher nhận lỗi không có nghĩa side effect ấy tự được hoàn tác. Thiết kế retry/idempotency và phạm vi transaction dựa trên tài nguyên cụ thể.

### 7.3. Transaction và thread-local context

Nếu `publishEvent` xảy ra trong một transaction đang mở trên thread hiện tại và listener là `@EventListener` đồng bộ, listener có thể tham gia transaction hiện hành theo cách các thao tác dữ liệu của nó được cấu hình. Tuy nhiên, việc gọi listener đồng bộ **không tự tạo transaction** và không thay thế việc dùng `@Transactional` đúng chỗ.

Vì sử dụng cùng thread, các ngữ cảnh `ThreadLocal` đang có như MDC/tracing hoặc transaction-bound resources có thể sẵn có trong callback đồng bộ. Nếu chuyển sang `@Async`, các context đó **không mặc định tự truyền** sang thread khác; cần truyền ID rõ ràng hoặc dùng context propagation phù hợp.

`publishEvent` không phải hệ thống lưu trữ sự kiện bền vững. Nếu tiến trình dừng hoặc transaction rollback, đừng mặc định event sẽ được phát lại. Với sự kiện tích hợp liên dịch vụ cần độ tin cậy cao, cân nhắc transaction outbox và message broker theo yêu cầu.

## 8. Lỗi hiểu sai thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “Mỗi event được Spring xử lý trong một thread riêng.” | Không: `@EventListener` mặc định chạy ngay trên thread phát event. |
| “Chạy trên publisher thread nghĩa là luôn chạy trong thread `main`.” | Publisher có thể là request thread, scheduler, consumer hay executor thread. |
| “`publishEvent` luôn trả về ngay.” | Với listener đồng bộ, nó chờ xử lý; exception có thể ném lên caller. |
| “`@Order` tạo ra thread hoặc chạy song song.” | `@Order` chỉ sắp thứ tự gọi listener; không quyết định executor. |
| “Sau khi `publishEvent` trả về, toàn bộ side effect chắc chắn đã xong.” | Chỉ có thể nói các callback đồng bộ đã trả về bình thường; chúng có thể tạo tác vụ con async hoặc xử lý deferred. |
| “Listener đồng bộ mặc định chắc chắn commit transaction.” | Cần xét transaction của caller, propagation, exception, thời điểm commit; listener không tự commit. |
| “Listener `@TransactionalEventListener` giống hệt listener thường.” | Nó đăng ký xử lý theo phase transaction, nên thời điểm kích hoạt có thể khác. |

## 9. Cách kiểm thử đúng trong dự án thực

Để kiểm tra một listener cụ thể có thực sự chạy trên publisher thread hay không:

1. Đặt log **ngay trước `publishEvent`**, trong listener, và **ngay sau `publishEvent`**. In thread name, event ID, correlation ID; nếu cần kiểm chứng nghiêm ngặt có thể so sánh đối tượng `Thread.currentThread()` trong một test có kiểm soát.
2. Đảm bảo biết cấu hình thật: có `@EnableAsync` và `@Async` hay không, multicaster có `TaskExecutor` hay không, listener có deferred execution/transaction phase không.
3. Với listener đồng bộ, kiểm tra listener bắt đầu và kết thúc **trước** dòng sau `publishEvent`. Không dùng một vài lần log “tình cờ đúng” để kết luận hệ thống luôn bảo đảm thứ tự ở chế độ async.
4. Thử phát sự kiện từ hai publisher thread khác nhau; mỗi listener đồng bộ phải chạy trên thread của lần publish tương ứng, miễn là không có cấu hình/logic chuyển thread.
5. Thử listener ném exception trong môi trường test để xác định cách caller và các listener còn lại phản ứng. Không thực hiện thử lỗi này trên giao dịch thật không có kiểm soát.

Một kiểm thử tự động có thể lưu `Thread.currentThread()` ở publisher rồi so sánh bằng toán tử `==` với thread quan sát trong listener. Điều này mạnh hơn việc chỉ so sánh tên thread. Nếu test cần chờ hoàn thành của listener async, dùng `CountDownLatch` hoặc `CompletableFuture` có timeout; tránh dùng `Thread.sleep` để đoán lịch chạy.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một controller phát `OrderPlaced` khi đang xử lý HTTP request, và listener `@EventListener` không có async. Listener chạy trên thread nào?

**Đáp án:** Cùng thread đang gọi `publishEvent` từ request (trong cấu hình multicaster đồng bộ mặc định). Request bị giữ cho đến khi callback hoàn tất hoặc ném exception.

**Câu 2.** Service `@Async` gọi `publishEvent`, còn listener là đồng bộ. Listener có nhất thiết chạy trên request thread ban đầu không?

**Đáp án:** Không. Nó chạy đồng bộ **trên thread executor đang thực hiện service `@Async`**, bởi đó là publisher thread ở thời điểm gọi `publishEvent`.

**Câu 3.** Vì sao dòng sau `publishEvent` có thể xuất hiện trước log hoàn tất của listener khi bật `@Async`?

**Đáp án:** Publisher có thể gửi task lên executor và tiếp tục mà không đợi phần thân listener hoàn tất. Thứ tự thực thi thread không được ràng buộc bởi thứ tự gọi callback.

**Câu 4.** Nếu một listener đồng bộ ném `RuntimeException` chưa được xử lý, publisher chắc chắn vẫn đi tiếp sau `publishEvent`?

**Đáp án:** Không. Với multicaster đồng bộ mặc định và không có error handler tùy chỉnh, exception có thể truyền về caller. Caller cần có chiến lược xử lý lỗi/transaction phù hợp.

## 11. Ghi nhớ và tài liệu tham khảo

- Một listener Spring Event **đồng bộ mặc định chạy ngay trên thread đang gọi `publishEvent`**; publisher phải chờ callback trả về.
- “Publisher thread” là thread của nơi thực sự phát sự kiện, có thể là main, request, worker hoặc scheduler thread.
- `@Async`, executor trên multicaster, transaction-phase listener và tác vụ nền do listener tự tạo là các trường hợp cần xét riêng.
- Hành vi đồng bộ giúp dễ hiểu call stack, ngữ cảnh thread và exception, nhưng khiến độ trễ xử lý listener tác động trực tiếp lên publisher.

Tài liệu Spring Framework:

- Application Events, ApplicationEventPublisher, listener ordering và asynchronous listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- `SimpleApplicationEventMulticaster` và khả năng gắn `TaskExecutor`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Task Execution, Scheduling và `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
