# Ảnh hưởng của Event Multicaster đến thread trong Spring Framework

## 1. Event multicaster đứng ở đâu trong luồng phát sự kiện?

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(event)` phát sự kiện để các `ApplicationListener` hoặc phương thức `@EventListener` phù hợp được nhận. `ApplicationEventMulticaster` đảm nhận việc tìm listener và **gọi hoặc lập lịch thực thi** các listener đó. Triển khai thường dùng trong `ApplicationContext` là `SimpleApplicationEventMulticaster`.

Mối quan hệ cơ bản:

```text
Publisher (luồng đang chạy)
    |
    | publishEvent(event)
    v
ApplicationEventMulticaster
    |
    +-- xác định listener phù hợp
    +-- chọn cách thực thi listener
          |
          +-- đồng bộ: gọi listener ngay trong luồng publisher
          |
          +-- bất đồng bộ: gửi listener vào Executor, nếu listener hỗ trợ
```

Điểm quan trọng là **việc phát sự kiện không mặc nhiên tạo thread mới**. Thread mà listener sử dụng phụ thuộc vào cách cấu hình multicaster, khả năng chạy bất đồng bộ của listener, và đôi khi cả `@Async` trên phương thức listener.

Các thuật ngữ cần tách biệt:

- **Publisher thread**: luồng gọi `publishEvent(...)` (ví dụ thread xử lý HTTP request, worker của scheduler hoặc thread của một tác vụ).
- **Listener thread**: luồng thực sự thực thi nội dung listener.
- **Executor/TaskExecutor**: thành phần nhận các công việc và quyết định chúng được chạy ngay hay được giao cho worker thread. Có executor đồng bộ và executor dùng thread pool.
- **Thread context**: dữ liệu gắn với một luồng qua `ThreadLocal` hoặc cơ chế tương tự, ví dụ transaction đang gắn với luồng, logging MDC, security context hoặc request attributes.
- **Completion**: thời điểm listener xử lý xong; khác với thời điểm công việc được gửi thành công vào executor.

## 2. Cấu hình mặc định: listener chạy trong thread của publisher

Với `SimpleApplicationEventMulticaster` mặc định, chưa cấu hình executor bất đồng bộ, Spring gọi listener ngay trong thread phát sự kiện. Cách hoạt động tương đương sử dụng `SyncTaskExecutor`.

```text
publisher-thread
    |-- thực hiện code nghiệp vụ
    |-- publishEvent(E)
    |     |-- listener A chạy và kết thúc
    |     |-- listener B chạy và kết thúc
    |     +-- return
    +-- tiếp tục sau publishEvent(E)
```

Hệ quả:

1. **Không có chuyển thread do multicaster**: `Thread.currentThread()` ở listener là cùng đối tượng `Thread` với publisher, khi listener thực sự chạy đồng bộ.
2. **Publisher chờ listener**: nếu listener chạy 500 ms và listener tiếp theo chạy 300 ms, lời gọi phát sự kiện phải chờ cả hai trong đường đi đồng bộ bình thường. Độ trễ bị cộng vào request/job đang phát sự kiện.
3. **Có thể truy cập thread context đang hoạt động**: nếu publisher đang ở trong transaction được gắn theo thread, listener đồng bộ thường ở cùng transaction context. Không nên nhầm đây là cam kết dữ liệu đã commit.
4. **Ngoại lệ có thể truyền ngược**: nếu listener đồng bộ ném lỗi chưa được xử lý và multicaster không có `ErrorHandler` phù hợp, ngoại lệ lan đến publisher và ngắt vòng gọi listener hiện tại.
5. **Không có thứ tự toàn cục giữa nhiều publisher**: hai thread cùng phát event đồng thời có thể chạy hai chuỗi listener song song. "Đồng bộ" chỉ mô tả quan hệ giữa mỗi lần phát sự kiện và các listener của chính lần đó.

Ví dụ, một HTTP request gọi `publishEvent` trong thread `http-nio-...` thì listener đồng bộ cũng chạy ngay trong thread request đó. Một listener gọi API bên ngoài chậm sẽ khiến thời gian phản hồi HTTP tăng tương ứng.

## 3. Cấu hình multicaster với TaskExecutor: có thể chuyển listener sang worker thread

`SimpleApplicationEventMulticaster.setTaskExecutor(Executor)` cho phép thay cách chạy listener. Nếu cấu hình một executor thực thi bất đồng bộ (ví dụ `ThreadPoolTaskExecutor` hoặc `ExecutorService` dùng thread pool), multicaster thông thường **submit công việc** rồi tiếp tục. Worker thread sẽ thực thi logic listener sau đó.

```text
publisher-thread                          event-worker-1
    |                                          |
    |-- publishEvent(E)                        |
    |     |-- executor.execute(listener A) ----+----> listener A
    |     |-- executor.execute(listener B) -----|----> ...
    |     +-- return                            |
    +-- tiếp tục nghiệp vụ                      +-- listener hoàn thành về sau
```

Vì thread pool phụ thuộc lịch trình CPU và tải thực tế, listener có thể bắt đầu **trước hoặc sau** khi `publishEvent` trả về. Điều được bảo đảm bởi cơ chế lập lịch là multicaster không chủ động chờ tất cả tác vụ async hoàn tất; không được đoán một thứ tự log cố định nếu không có đồng bộ bổ sung.

Một điểm rất quan trọng trong Spring Framework 6.1 trở lên: multicaster kiểm tra `ApplicationListener.supportsAsyncExecution()`. Nếu listener trả về `false`, Spring **gọi listener đó ngay trong publisher thread**, dù multicaster có executor. Ví dụ tiêu biểu là `TransactionalApplicationListener`, vốn cần đăng ký đồng bộ hóa giao dịch trong thread thích hợp. Vì vậy, câu nói "cấu hình executor thì mọi listener đều chạy trên thread pool" là sai.

Việc gọi `setTaskExecutor(...)` cũng không tự tạo concurrency: nếu truyền một executor đồng bộ, listener vẫn chạy trong thread gọi. Quan sát **loại executor và hành vi thực thi**, thay vì chỉ nhìn sự tồn tại của cấu hình executor.

## 4. Ví dụ Java 17 hoàn chỉnh: so sánh cùng thread và worker thread

Ví dụ dùng Spring Framework 6.2.x, một ứng dụng Java không cần Spring Boot. Nó tạo hai `ApplicationContext` độc lập:

- Context đầu dùng multicaster mặc định: listener chạy trên cùng publisher thread.
- Context sau khai báo bean tên chính xác `applicationEventMulticaster`, gắn executor một thread tên `event-worker`: listener chuyển sang worker thread.
- `CountDownLatch` được dùng **chỉ để tạo kết quả minh họa xác định**. Listener async đợi tín hiệu từ publisher, nên có thể kiểm chứng rằng `publishEvent` đã trả về trước khi listener in kết quả. Trong ứng dụng thật, không nên cố tình chặn listener chỉ để kiểm chứng concurrency.

Cấu trúc:

```text
event-thread-demo/
├── pom.xml
└── src/main/java/demo/EventThreadDemo.java
```

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-thread-demo</artifactId>
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
                    <mainClass>demo.EventThreadDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/EventThreadDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public class EventThreadDemo {

    public record TicketCreated(String code) {}

    private static Thread publisherThread;

    public static class SyncListener {
        @EventListener
        public void onTicket(TicketCreated event) {
            boolean sameThread = Thread.currentThread() == publisherThread;
            System.out.println("sync listener, same publisher thread: " + sameThread);
            System.out.println("sync event: " + event.code());
        }
    }

    public static class AsyncListener {
        static final CountDownLatch release = new CountDownLatch(1);
        static final CountDownLatch finished = new CountDownLatch(1);

        @EventListener
        public void onTicket(TicketCreated event) {
            try {
                release.await();
                boolean sameThread = Thread.currentThread() == publisherThread;
                System.out.println("async listener, same publisher thread: " + sameThread);
                System.out.println("async worker: " + Thread.currentThread().getName());
                System.out.println("async event: " + event.code());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SyncConfiguration {
        @Bean
        SyncListener syncListener() {
            return new SyncListener();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AsyncConfiguration {
        @Bean
        AsyncListener asyncListener() {
            return new AsyncListener();
        }

        @Bean(destroyMethod = "shutdown")
        ExecutorService eventExecutor() {
            return Executors.newSingleThreadExecutor(
                    task -> new Thread(task, "event-worker"));
        }

        @Bean(name = "applicationEventMulticaster")
        SimpleApplicationEventMulticaster applicationEventMulticaster(
                ExecutorService eventExecutor) {
            var multicaster = new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(eventExecutor);
            return multicaster;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        publisherThread = Thread.currentThread();

        System.out.println("=== default ===");
        try (var sync = new AnnotationConfigApplicationContext(
                SyncConfiguration.class)) {
            System.out.println("publisher: before");
            sync.publishEvent(new TicketCreated("T-1"));
            System.out.println("publisher: after");
        }

        System.out.println("=== with executor ===");
        try (var async = new AnnotationConfigApplicationContext(
                AsyncConfiguration.class)) {
            System.out.println("publisher: before");
            async.publishEvent(new TicketCreated("T-2"));
            System.out.println("publisher: after");

            AsyncListener.release.countDown();
            if (!AsyncListener.finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Async listener timed out");
            }
        }
    }
}
```

Chạy từ thư mục `event-thread-demo`, khi đã có JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Đầu ra do các lệnh `System.out.println` tạo ra:

```text
=== default ===
publisher: before
sync listener, same publisher thread: true
sync event: T-1
publisher: after
=== with executor ===
publisher: before
publisher: after
async listener, same publisher thread: false
async worker: event-worker
async event: T-2
```

Tại sao kết quả đáng tin?

1. Listener đồng bộ so sánh trực tiếp đối tượng `Thread` với `publisherThread` nên không phụ thuộc tên thread do Maven hay chương trình khởi chạy gán.
2. Executor riêng tạo thread tên `event-worker`. Async listener chỉ in sau khi publisher gọi `release.countDown()`, mà publisher chỉ làm vậy **sau khi in** `publisher: after`.
3. `finished.await(...)` giúp chương trình chờ kết quả để không kết thúc trước khi listener xử lý xong. Đây là cơ chế chờ **do ví dụ tự tạo**, không phải hành vi chờ mặc định của multicaster async.
4. `@Bean(destroyMethod = "shutdown")` yêu cầu Spring đóng executor khi context đóng; chương trình chờ listener hoàn thành trước khi thoát khối `try`.

Ví dụ dùng `newSingleThreadExecutor` nhằm làm rõ **khác thread**, không nhằm biểu diễn cấu hình hiệu năng lý tưởng. Với pool nhiều thread, các listener có thể chạy song song; với một worker, chúng được xếp hàng trong executor nhưng publisher vẫn có thể tiếp tục.

## 5. So sánh các cách cấu hình và ảnh hưởng tới thread

| Cách đăng ký listener / cấu hình | Luồng thực thi listener | `publishEvent` chờ listener? | Lưu ý |
| --- | --- | --- | --- |
| Multicaster mặc định + `@EventListener` thông thường | Cùng thread với publisher | Có, trong đường đi bình thường | Không cần `@EnableAsync` |
| Multicaster có executor đồng bộ như `SyncTaskExecutor` | Cùng thread với publisher | Có | Có `setTaskExecutor` nhưng vẫn không đổi thread |
| Multicaster có `ThreadPoolTaskExecutor` + listener hỗ trợ async | Worker thread trong pool | Không chờ xử lý xong | Việc submit/scheduling vẫn có chi phí và có thể bị từ chối |
| Multicaster mặc định + `@Async` trên `@EventListener`, đã bật async | Thread của executor phục vụ `@Async` | Không chờ phần thân listener | Chỉ listener được đánh dấu chịu ảnh hưởng |
| Multicaster async + `@Async` trên phương thức listener | Có thể có hai lớp giao tác lập lịch async | Không nên trông đợi đồng bộ | Khó suy luận thứ tự và context; chỉ kết hợp khi có lý do rõ ràng |
| Multicaster async + listener `supportsAsyncExecution() == false` | Gọi listener trong publisher thread | Chờ phần gọi đồng bộ đó | Ví dụ listener đồng bộ hóa transaction |

Bảng nói về **hành vi thông thường** khi executor nhận công việc. Một số đường đi như executor từ chối công việc, listener tự tạo thread, hoặc framework extension riêng có thể làm hành vi thực tế khác; khi điều tra phải xem implementation và cấu hình đang chạy.

### `@Async` khác gì với executor của multicaster?

- `setTaskExecutor` là chính sách **phân phối sự kiện ở multicaster**, thường tác động lên các listener hỗ trợ async của ứng dụng.
- `@Async` là cơ chế đánh dấu **một phương thức** chạy bất đồng bộ thông qua hỗ trợ Spring async, thường cần `@EnableAsync` và executor tương ứng. Một phương thức `@EventListener` có `@Async` có thể chuyển sang worker thread ngay cả khi multicaster vẫn gọi đồng bộ phương thức adapter của listener.
- Với listener chạy theo `@Async`, ngoại lệ không tự truyền về phía phát sự kiện; cần xử lý qua chính sách xử lý ngoại lệ phù hợp, chẳng hạn `AsyncUncaughtExceptionHandler` cho phương thức async trả về `void`.
- Nếu chỉ cần một listener nhẹ chạy nền, `@Async` có thể đủ. Nếu muốn một chính sách nhất quán cho nhiều listener, cân nhắc executor của multicaster và xác định ngoại lệ/các listener bắt buộc phải ở thread gốc.

Đoạn minh họa sau **không phải chương trình độc lập**, vì còn cần cấu hình Spring bean và một executor phù hợp:

```java
@EnableAsync
@Configuration
class AsyncSupport {
}

@Component
class MailEventListener {
    @Async
    @EventListener
    public void onMailQueued(MailQueued event) {
        // Công việc có thể chạy trên executor của @Async.
    }
}
```

Các import, bean `MailQueued` và cấu hình ứng dụng được lược để tập trung vào tương tác giữa `@Async` và multicaster; dùng ví dụ hoàn chỉnh ở mục 4 để tự chạy.

## 6. ThreadLocal, transaction, SecurityContext và logging context

Khi listener chuyển sang thread khác, **dữ liệu gắn với publisher thread không tự chuyển theo**. Điều này ảnh hưởng trực tiếp tới tính đúng đắn và khả năng quan sát ứng dụng:

| Loại context | Đồng bộ cùng thread | Async sang thread khác |
| --- | --- | --- |
| Transaction liên kết với thread | Listener thông thường có thể tham gia ngữ cảnh transaction đang mở | Không tự kế thừa transaction thread-bound |
| MDC / trace logging lưu qua `ThreadLocal` | Thường thấy cùng correlation ID | Có thể mất correlation ID nếu không truyền context |
| Spring Security `SecurityContextHolder` theo chế độ mặc định | Thấy security context của thread hiện tại | Không nên giả định worker có cùng authentication |
| `RequestContextHolder` | Có thể thấy request attributes đã được bind | Không tự bảo đảm tồn tại trên worker |
| ThreadLocal do ứng dụng tự định nghĩa | Cùng đối tượng được lưu trong thread đó | Worker có giá trị riêng hoặc không có giá trị |

**Không chia sẻ trực tiếp transaction giữa hai thread chỉ bằng cách sao chép `ThreadLocal`.** Transaction còn liên quan tài nguyên và ranh giới quản lý; với công việc async cần chủ động định nghĩa transaction mới tại worker nếu cần, đồng thời cân nhắc tính nhất quán sau commit. `ContextPropagatingTaskDecorator` và các cơ chế context propagation hữu ích cho tracing/MDC nhưng không thay thế quản lý transaction.

Ví dụ ứng dụng gửi email sau khi lưu bản ghi: nếu listener async khởi chạy ngay khi bản ghi chưa commit, worker có thể đọc dữ liệu chưa xuất hiện trong transaction riêng hoặc gửi email trước khi transaction của publisher rollback. Để chỉ bắt đầu sau commit, xem `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` hoặc một cơ chế outbox bền vững nếu yêu cầu giao nhận tin cậy. **Dùng multicaster async không tạo bảo đảm after-commit**.

### Ngoại lệ quan trọng: TransactionalApplicationListener

Các listener đồng bộ hóa transaction thường khai báo `supportsAsyncExecution() == false`. Vì vậy multicaster cần gọi phần đăng ký đồng bộ hóa transaction trong publisher thread. Nếu listener dùng `@TransactionalEventListener` với pha `AFTER_COMMIT`, callback nghiệp vụ diễn ra vào thời điểm sau commit (thông thường trên luồng thực thi transaction), chứ không phải bị multicaster tự động đẩy toàn bộ sang executor.

Khi không có transaction đang hoạt động, `@TransactionalEventListener` mặc định không thực thi listener; có thể cấu hình `fallbackExecution = true` khi nghiệp vụ yêu cầu. Đây là quy tắc về transaction, độc lập với việc multicaster có pool hay không.

## 7. Thứ tự xử lý, lỗi và hiệu năng khi có thread pool

### Thứ tự và thời điểm hoàn tất

Với multicaster đồng bộ, từng listener phù hợp được gọi lần lượt trong cùng lần phát sự kiện. `@Order` có thể sắp xếp thứ tự gọi. Khi sử dụng pool bất đồng bộ, việc multicaster submit listener theo thứ tự ưu tiên **không đồng nghĩa** listener bắt đầu hoặc kết thúc theo thứ tự đó: worker A có thể chạy lâu hơn worker B; scheduler và độ dài queue cũng ảnh hưởng.

Ngay cả trong trường hợp một worker đơn, hai publisher phát event đồng thời vẫn có thể đan xen các lần submit. Nếu nghiệp vụ thực sự đòi chuỗi bước A → B → C và rollback thống nhất, gọi trực tiếp qua một service điều phối thường rõ ràng và dễ kiểm soát hơn.

### Lỗi khác nhau ở hai chế độ

- **Đồng bộ mặc định**: ngoại lệ không được xử lý trong listener có thể truyền tới publisher, khiến lời gọi `publishEvent` thất bại.
- **Async qua executor**: lỗi xảy ra trong worker thường không thể được publisher bắt bằng `try/catch` quanh `publishEvent` sau khi submit thành công. Cần logging, `ErrorHandler`, retry và giám sát kết quả ở nơi xử lý async.
- **Executor từ chối task**: bản triển khai `SimpleApplicationEventMulticaster` của Spring 6.2 có nhánh xử lý `RejectedExecutionException` bằng cách gọi listener cục bộ. Vì vậy một tác vụ dự kiến chạy nền **có thể thực thi trên publisher thread** ở tình huống executor từ chối. Đừng xây dựng logic an toàn nghiệp vụ dựa trên giả định thread name luôn cố định.

### Hiệu năng, tải và tài nguyên

Chuyển listener nặng sang executor giúp publisher giảm thời gian bị giữ bởi listener, nhưng không làm công việc biến mất. Nếu số lượng sự kiện tăng nhanh hơn tốc độ tiêu thụ, queue có thể đầy, latency của listener tăng hoặc tác vụ bị từ chối. Cần chọn pool/queue có giới hạn, theo dõi số task đang chạy, độ trễ queue, lỗi, retry, và chính sách shutdown. Việc chạy async chỉ có nghĩa "xử lý ở thời điểm và ngữ cảnh khác"; **không phải cam kết bền vững rằng sự kiện sẽ được xử lý ngay cả khi process dừng**. Với yêu cầu giao nhận đảm bảo sau sự cố, cân nhắc transaction outbox và message broker thay cho event in-process thuần túy.

## 8. Chẩn đoán thực tế

Khi muốn tìm nguyên nhân listener chạy trên thread nào hoặc vì sao response bị chậm, có thể kiểm tra theo thứ tự:

1. Log ở cả publisher và listener: `Thread.currentThread().getName()`, event ID, timestamp và trace ID. Nếu cần chứng minh đúng **cùng đối tượng thread**, so sánh trực tiếp `Thread.currentThread() == publishingThread` trong ví dụ kiểm soát được.
2. Xác nhận bean `applicationEventMulticaster` đang hoạt động. Spring sử dụng đúng tên bean này để thay multicaster của context. Kiểm tra có gọi `setTaskExecutor` không và executor thực tế đồng bộ hay dùng pool.
3. Phân biệt listener được gọi bằng `@EventListener`, `ApplicationListener`, `@Async` hay `@TransactionalEventListener`. Với Spring 6.1+, chú ý `supportsAsyncExecution()`.
4. Kiểm tra `ThreadLocal`/MDC/SecurityContext/transaction tại nơi cần dùng. Nếu chạy khác thread, chỉ truyền những context an toàn và cần thiết qua cơ chế chính thức.
5. Đừng suy luận từ một lần in log rằng `publishEvent` luôn trả về trước listener: hai thread chạy đồng thời và thời điểm log phụ thuộc scheduler.
6. Khi publisher bị giữ lâu, đo thời gian của listener đồng bộ; khi listener bị trễ dù publisher nhanh, đo queue/pool saturation và số job đang chờ.
7. Tách chính sách retry và xử lý lỗi async khỏi `try/catch` quanh publisher. Đặt timeout và idempotency cho tác vụ có side effect.

### Câu hỏi tự kiểm tra

1. **Mặc định `@EventListener` chạy trên thread nào?** — Trong thread gọi `publishEvent`, trừ khi cơ chế khác như `@Async` can thiệp.
2. **Chỉ cần thêm `setTaskExecutor` là mọi listener chạy nền?** — Không. Executor có thể đồng bộ, và `supportsAsyncExecution() == false` giữ một số listener trong thread phát sự kiện.
3. **Publisher có chờ listener đã submit vào thread pool hoàn thành?** — Không theo mặc định; phần submit có thể hoàn tất trước phần xử lý. Muốn chờ phải có cơ chế riêng.
4. **Có thể dùng ngay transaction thread-bound từ publisher trong worker không?** — Không; cần thiết kế transaction riêng, thời điểm sau commit và cách truyền context phù hợp.
5. **Có `@Order` thì các listener async sẽ luôn kết thúc đúng thứ tự?** — Không.
6. **Muốn sự kiện được xử lý dù process chết thì dùng multicaster thread pool có đủ?** — Không; đó vẫn là cơ chế trong cùng tiến trình, cần cơ chế lưu trữ và giao nhận bền vững nếu nghiệp vụ đòi hỏi.

## Tài liệu tham khảo

- [Spring Framework — Application Events / Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Observability, Application Events and Thread Context](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
