# Mặc định thực thi đồng bộ và ảnh hưởng của listener chạy lâu trong Spring Boot

## 1. Vì sao một listener “nhỏ” có thể làm chậm cả ứng dụng?

Trong Spring Boot, **application event** là cơ chế phát thông báo đến các thành phần quan tâm thông qua **ApplicationEventPublisher** và **ApplicationListener/@EventListener**. Mặc định, Spring Framework dùng **SimpleApplicationEventMulticaster** và gọi các listener **đồng bộ trong chính thread đã phát sự kiện**.

Điều này có nghĩa là lời gọi **publishEvent(...)** thông thường chưa trả về ngay: nó phải đợi các listener đồng bộ phù hợp được gọi xong. Một listener chậm có thể khiến request HTTP chậm, giữ transaction lâu, cản những listener xếp sau, hoặc trì hoãn các giai đoạn trong **SpringApplication.run(...)**.

Ví dụ khái niệm:

~~~text
Thread của publisher
    |
    | publishEvent(OrderCreated)
    |
    +--> Listener A: 20 ms
    |
    +--> Listener B: 3.000 ms (gọi API ngoài)
    |
    +--> Listener C: 10 ms
    |
    | publishEvent(...) trả về
    v
Publisher tiếp tục xử lý
~~~

Tổng thời gian publishEvent trong tình huống này có thể lớn hơn **3.030 ms**, còn tùy overhead và scheduler. Không có worker thread riêng cho từng listener nếu bạn chưa cấu hình cơ chế bất đồng bộ.

**Cần phân biệt:** “event” trong Spring Framework là **thông báo trong tiến trình ứng dụng**, không tự động là Kafka message, queue bền vững, giao dịch tách biệt hoặc task chạy nền.

## 2. Cơ chế thực thi mặc định

Khi một bean có tham chiếu đến **ApplicationEventPublisher**:

~~~java
publisher.publishEvent(new OrderCreated("O-42"));
~~~

Spring tiếp nhận event, tìm các **ApplicationListener** hoặc method **@EventListener** phù hợp, rồi chuyển qua **ApplicationEventMulticaster**. Với cấu hình mặc định, SimpleApplicationEventMulticaster không được gán task executor bất đồng bộ. Vì vậy:

1. Publisher gọi **publishEvent(...)** trên thread hiện tại.
2. Multicaster tìm các listener phù hợp kiểu sự kiện; Spring hỗ trợ cả đối tượng event tự định nghĩa (payload event), không nhất thiết phải kế thừa ApplicationEvent.
3. Listener thứ nhất chạy xong trước khi publisher đi tiếp tới listener thứ hai trong mô hình đồng bộ mặc định.
4. Nếu tất cả listener hoàn tất bình thường, lời gọi publishEvent mới trả về.
5. Nếu listener đồng bộ ném exception không được xử lý, **mặc định exception lan ngược tới publisher**, có thể làm dừng việc gọi các listener còn lại trong lần multicast hiện tại.

**Cùng thread** kéo theo các hệ quả cần nắm:

- Thời gian chạy listener nằm trên đường thực thi của caller (request thread, runner thread, thread của scheduler hoặc thread bootstrap).
- ThreadLocal, logging MDC, context transaction của publisher có thể tiếp tục hiện diện trong listener đồng bộ, theo phạm vi và cấu hình tương ứng.
- Listener không có hợp đồng “khởi chạy ngầm”: muốn xử lý bất đồng bộ phải cấu hình rõ ràng.
- **@Order/Ordered** có thể điều khiển thứ tự gọi các listener cùng loại sự kiện, nhưng không khắc phục một listener blocking và không biến chúng thành song song.

Trong Spring Framework 6.1+, **ApplicationListener.supportsAsyncExecution()** còn cho phép một số listener tuyên bố **phải chạy trong thread gốc**. Điều này đặc biệt đáng lưu ý khi cấu hình global multicaster với executor: không phải mọi listener đều phù hợp để đưa sang thread khác.

## 3. Listener chạy lâu gây ảnh hưởng ở đâu?

| Nguồn phát event | Một listener chậm làm gì? | Hệ quả thực tế |
| --- | --- | --- |
| Controller/service xử lý HTTP request | Giữ thread xử lý request trong lúc publishEvent chưa trả về | Tăng response latency, request timeout, giảm khả năng phục vụ khi tải cao |
| Service trong @Transactional | Kéo dài luồng transaction nếu event được phát khi transaction đang mở | Giữ connection/lock lâu hơn, tăng nguy cơ chờ khóa |
| ApplicationStartedEvent | Giữ luồng khởi động sau refresh nhưng trước khi các runner được gọi | Trì hoãn ApplicationRunner/CommandLineRunner và readiness |
| ApplicationReadyEvent | Trì hoãn việc xử lý hết event và các bước tiếp theo trong chuỗi startup | Thời gian đến ReadinessState.ACCEPTING_TRAFFIC tăng |
| ContextRefreshedEvent | Có thể giữ luồng refresh context | Startup chậm, dễ gặp timeout với startup probe |
| Job scheduler hoặc message consumer | Giữ thread của scheduler/consumer | Tăng độ trễ xử lý event tiếp theo, backlog hoặc ảnh hưởng polling |
| Shutdown-related lifecycle event | Làm chậm luồng đóng ứng dụng | Chậm giải phóng tài nguyên, có thể vượt giới hạn shutdown |

**Giải thích một tình huống thường gặp:** service phát OrderCreatedEvent trong một HTTP request rồi listener gửi email bằng HTTP client đồng bộ. Nếu phía email phản hồi chậm, thread đang xử lý đơn hàng phải chờ theo. Tăng số thread server chỉ giúp đến một giới hạn; nếu mọi request đều giữ thread lâu, hệ thống vẫn có thể quá tải.

**Quan hệ với transaction:** nếu publishEvent nằm trong method giao dịch đang hoạt động và listener chạy đồng bộ ngay lúc publish, cả hai dùng cùng thread. Việc phát event **không tự tạo transaction mới** hoặc tự commit dữ liệu; listener chạy tại thời điểm đó có thể quan sát trạng thái chưa commit của transaction hiện tại, tùy cách truy cập dữ liệu.

Không đồng nhất **@TransactionalEventListener** với **@EventListener**: TransactionalEventListener có cơ chế ràng buộc theo pha giao dịch như AFTER_COMMIT; đó là contract khác với listener thông thường được gọi ngay khi publish.

## 4. Listener chạy lâu ảnh hưởng trực tiếp chuỗi khởi động

Spring Boot phát các sự kiện vòng đời trong quá trình **SpringApplication.run(...)**. Những mốc đáng quan tâm:

~~~text
... refresh ApplicationContext
          |
          v
ApplicationStartedEvent
          |
LivenessState.CORRECT
          |
ApplicationRunner / CommandLineRunner
          |
ApplicationReadyEvent
          |
ReadinessState.ACCEPTING_TRAFFIC
          |
SpringApplication.run(...) returns
~~~

Các listener mặc định của những event trên được gọi **đồng bộ**. Do đó:

- Một listener **ApplicationStartedEvent** chờ remote API lâu có thể làm runner chưa được gọi, dù ApplicationContext đã refresh.
- Một listener **ApplicationReadyEvent** chạy lâu làm trì hoãn hoàn tất việc publish sự kiện ready và chuyển readiness trong đường khởi động thông thường.
- Spring Boot **khuyến nghị không đặt tác vụ dài trong event listener startup**. Nếu một tác vụ là điều kiện để ứng dụng sẵn sàng, **ApplicationRunner/CommandLineRunner** thường là điểm mở rộng phù hợp hơn: mục đích rõ ràng, có thể xếp thứ tự và việc ném exception có thể làm startup thất bại thay vì công bố ready sai.
- Việc web server đã bind port hoặc log “Started ...” xuất hiện không chứng minh các runner đã hoàn tất hay instance đã ready.

Lưu ý: runner cũng được gọi đồng bộ trong startup theo thiết kế và **có thể kéo dài startup** nếu nó làm việc lâu. Chuyển từ listener sang runner không làm tác vụ tự nhanh hơn; lợi ích là **đặt đúng trách nhiệm và điểm điều phối trước ready**, có khả năng cấu hình timeout, giám sát và fail-fast rõ ràng.

## 5. Ví dụ chạy được: listener chậm giữ publisher trên cùng thread

Ví dụ này dùng **Java 17+** và **Spring Boot 3.x**, mô phỏng một runner phát sự kiện InventoryChecked; một listener đồng bộ “chậm” xử lý trước listener audit. Toàn bộ source nằm trong **một tệp Java** để dễ kiểm tra.

### 5.1. Cấu trúc dự án

~~~text
sync-listener-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          SynchronousEventDemo.java
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'sync-listener-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Spring Boot 3.3.x yêu cầu Java 17+. Project cần Gradle và plugin tương thích, cùng khả năng tải dependencies từ Maven Central hoặc cache local. Bài học tập trung vào behavior của event, không cần HTTP server.

### 5.2. Source Java

Tệp **src/main/java/example/SynchronousEventDemo.java**:

~~~java
package example;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class SynchronousEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                SynchronousEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_AFTER_RUN");
        }
    }
}

record InventoryChecked(String sku, boolean failListener) {
}

@Component
class EventProducer implements ApplicationRunner {
    private final ApplicationEventPublisher publisher;

    EventProducer(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("PUBLISH_BEFORE");
        publisher.publishEvent(new InventoryChecked(
                "SKU-42", args.containsOption("fail-listener")));
        System.out.println("PUBLISH_AFTER");
    }
}

@Component
class SlowInventoryListener {

    @EventListener
    @Order(10)
    public void onInventoryChecked(InventoryChecked event) {
        System.out.println("SLOW_START");

        if (event.failListener()) {
            throw new IllegalStateException("Listener failed");
        }

        try {
            Thread.sleep(400);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }

        System.out.println("SLOW_END");
    }
}

@Component
class AuditInventoryListener {

    @EventListener
    @Order(20)
    public void audit(InventoryChecked event) {
        System.out.println("AUDIT");
    }
}

@Component
class ReadySignal {

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("APPLICATION_READY");
    }
}
~~~

**Các điểm cần hiểu trong code:**

1. **InventoryChecked** là Java record thuần, không cần kế thừa ApplicationEvent. Spring Framework có thể bọc event payload để phân phối đến method **@EventListener** có tham số tương ứng.
2. **EventProducer** là **ApplicationRunner**, được Spring Boot gọi sau context refresh và trước ApplicationReadyEvent.
3. **@Order(10)** trên SlowInventoryListener khiến method này được gọi trước **@Order(20)** trên AuditInventoryListener đối với cùng event trong cấu hình đồng bộ mặc định.
4. **Thread.sleep(400)** chỉ là mô phỏng một external call chậm. Code production phải dùng timeout/I/O thật sự có kiểm soát; không dùng sleep như chiến lược xử lý event.
5. **PUBLISH_AFTER** chỉ có thể in sau khi **publishEvent(...) trả về**, nghĩa là sau các listener đồng bộ đã hoàn tất.
6. Main đóng ApplicationContext sau khi run(...) trả về thành công. Với một web service lâu dài, **không đóng context sau mỗi request**.

### 5.3. Chạy và quan sát

Nếu project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Các dòng **do code ví dụ tự in** xuất hiện theo thứ tự:

~~~text
PUBLISH_BEFORE
SLOW_START
SLOW_END
AUDIT
PUBLISH_AFTER
APPLICATION_READY
MAIN_AFTER_RUN
~~~

Log Spring Boot/Gradle có thể xuất hiện xen giữa; khối trên không mô tả toàn bộ console. **Không có stdout về số mili-giây cố định** vì Thread.sleep và scheduler thực tế có độ dao động.

Điểm quan trọng: mặc dù sự kiện được “phát”, **PUBLISH_AFTER không xuất hiện ngay sau PUBLISH_BEFORE**. Publisher đã chờ listener chậm và audit chạy xong. Nếu listener chậm thực hiện network I/O 10 giây trong request thực, toàn bộ request có thể phải chờ gần 10 giây cộng với các bước còn lại.

### 5.4. Nhánh lỗi của listener đồng bộ

Thử kích hoạt exception trong listener:

~~~bash
./gradlew bootRun --args="--fail-listener"
~~~

Những dòng do source in ra trước exception là:

~~~text
PUBLISH_BEFORE
SLOW_START
~~~

Sau đó SlowInventoryListener ném **IllegalStateException("Listener failed")**. Với cấu hình mặc định **không có ErrorHandler nuốt lỗi**, exception đi ngược lên publishEvent(...), khiến ApplicationRunner thất bại; Spring Boot xử lý lỗi startup. Vì listener đã fail trước khi multicaster chuyển sang audit, **AUDIT**, **PUBLISH_AFTER**, **APPLICATION_READY** và **MAIN_AFTER_RUN** không xuất hiện theo nhánh thành công. Framework/Gradle có thể in stack trace và trạng thái build fail.

**Ý nghĩa:** lỗi listener đồng bộ không chỉ là log của một component độc lập; nó có thể làm caller fail. Khi event phát trong HTTP service, exception có thể làm request thất bại; khi phát từ startup runner, nó có thể làm ứng dụng không đạt trạng thái ready.

## 6. Cách nhận diện listener chậm và đo độ trễ

### Đo từ phía publisher

Bọc phép đo quanh publishEvent(...):

~~~java
long startedAt = System.nanoTime();
publisher.publishEvent(new InventoryChecked("SKU-42", false));
long elapsedMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt);
System.out.println("publishEvent took " + elapsedMillis + " ms");
~~~

Đây là **đoạn minh họa**, đặt trong một method đã inject **ApplicationEventPublisher publisher**. Giá trị đo là tổng thời gian lời gọi publishEvent, bao gồm việc tìm, gọi các listener đồng bộ và chi phí liên quan; **không** tự cho biết listener nào chậm.

### Đo từng listener

Với event quan trọng, có thể:

- Ghi **timer metric** cho từng handler và tổng thời gian publishEvent, tránh chèn ID khách hàng/đơn hàng làm label cardinality quá cao.
- Thu thập trace/span khi đủ ngữ cảnh; với event chạy đồng bộ trên cùng thread, MDC/ThreadLocal thường được kế thừa trong phạm vi phù hợp.
- Log thời điểm bắt đầu/kết thúc những listener có external I/O, giới hạn khối lượng log.
- Đặt timeout cho HTTP client, JDBC, file/network calls và hệ thống ngoài để tránh giữ thread vô hạn.
- Xem thread dump khi ứng dụng bị “treo” lúc startup hoặc API latency tăng: thread đang ở **ApplicationEventMulticaster** và handler nào bị blocking?
- Phân biệt **chậm vì listener** với **chậm vì code của publisher trước/sau publishEvent**.

Không dùng log “đã phát event” làm bằng chứng event đã xử lý thành công nếu hệ thống có listener async; cần đo trạng thái hoàn tất ở chính consumer.

## 7. Giải pháp 1: giữ listener đồng bộ nhưng làm cho ngắn và có giới hạn

Đồng bộ **không mặc nhiên là xấu**. Nó hữu ích nếu cần:

- Caller thấy ngay exception và có thể fail transaction/request một cách rõ ràng.
- Các thao tác ngắn hoàn thành trước khi luồng chính tiếp tục.
- Xác minh invariant nhanh và nhất quán ngay trong transaction, nếu được thiết kế cẩn thận.
- Dễ hiểu thứ tự, dễ debug, ít overhead scheduling.

Cách cải thiện:

1. Chỉ giữ **validation hoặc xử lý ngắn** trong listener; tránh I/O bên ngoài kéo dài.
2. Thiết lập **timeout rõ ràng**, số lần retry hữu hạn và fallback khi phụ thuộc không quan trọng.
3. Không phát lại event vô hạn hoặc tạo vòng phát event đệ quy.
4. Nếu tác vụ thuộc điều kiện startup bắt buộc, **chuyển sang runner** để thể hiện trách nhiệm rõ ràng, vẫn có timeout và fail-fast.
5. Nếu là thông báo hậu giao dịch như email, audit không bắt buộc, cân nhắc mô hình **transactional outbox + worker/queue**, không bắt request chờ hệ thống bên ngoài.

Ví dụ: đối với đơn hàng, kiểm tra chính sách nghiệp vụ trước khi commit có thể nên là bước đồng bộ của service, thay vì email notification trong cùng thread/transaction.

## 8. Giải pháp 2: chuyển một listener cụ thể sang @Async

Nếu handler **không cần hoàn thành trước khi publisher tiếp tục**, Spring hỗ trợ **@Async** cho phương thức **@EventListener**. Cần bật **@EnableAsync** và cấu hình executor phù hợp. Khi đó method có thể chạy trên thread khác.

### 8.1. Cấu hình executor có giới hạn

Ví dụ sau là **cấu hình thay thế để minh họa async**, không phải một phần của project đồng bộ ở mục 5. Nếu muốn thử, thêm các lớp vào project có record InventoryChecked và **gỡ/điều chỉnh các listener đồng bộ hiện tại** để tránh nhận event trùng.

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncEventConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Executor có giới hạn nhằm kiểm soát số thread và hàng đợi. **CorePoolSize=2, MaxPoolSize=4 và QueueCapacity=100** chỉ là giá trị minh họa; cần đo lưu lượng thực tế. Khi queue đầy và executor từ chối nhận thêm, publisher có thể thấy lỗi task rejection ngay ở bước submit; async không loại bỏ mọi hình thức blocking hoặc failure.

Listener async tương ứng:

~~~java
package example;

import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class AsyncInventoryListener {

    @Async("eventExecutor")
    @EventListener
    public void onInventoryChecked(InventoryChecked event) {
        System.out.println("ASYNC_START");
        // Thuc hien cong viec doc lap, co timeout va xu ly loi rieng.
        System.out.println("ASYNC_DONE");
    }
}
~~~

Trong triển khai thật, handler phải thực hiện công việc cụ thể và có logging/metric. Đây là lớp mẫu dùng cùng record **InventoryChecked** ở mục 5. Nếu giữ cả đồng bộ và async listeners, **cả hai sẽ nhận event**, nên không dùng output của mục 5 để dự đoán thứ tự hoàn tất mới.

### 8.2. Điều gì thay đổi khi dùng @Async?

| Khía cạnh | @EventListener mặc định | @Async + @EventListener |
| --- | --- | --- |
| Thread xử lý | Thread publisher | Thread từ async executor nếu submit thành công |
| Publisher có chờ handler xong? | Có | Không, chỉ chờ tới khi công việc được schedule |
| Thứ tự hoàn tất giữa nhiều handler | Có thể theo thứ tự gọi đồng bộ | Không bảo đảm thứ tự hoàn tất |
| Exception từ handler | Thường lan về publisher | Không lan ngược về publisher sau khi task đã chạy |
| Transaction/thread-local context | Có thể dùng cùng thread/context của publisher | Không tự được chuyển sang thread khác |
| Completion barrier của startup | Có thể cản startup tới khi xử lý xong | Không tự bảo đảm công việc xong trước ApplicationReadyEvent |
| Shutdown | Theo luồng hiện tại | Phải cấu hình executor/task lifecycle phù hợp |

**@EnableAsync là bắt buộc** để dùng async method infrastructure theo cơ chế chuẩn. Một bean không được Spring quản lý hoặc lời gọi tự thân **this.method()** có thể bỏ qua AOP proxy, khiến @Async không có tác dụng như mong đợi.

**Exception async:** với phương thức @Async trả void, exception xảy ra bên trong task **không được truyền về caller publishEvent(...)**. Spring sử dụng AsyncUncaughtExceptionHandler/ghi log phù hợp; nếu lỗi quan trọng, cần handler, retry, dead-letter hoặc trạng thái công việc riêng. Đừng xem “publisher không báo lỗi” là bằng chứng email/job đã hoàn tất.

**ThreadLocal/MDC/transaction:** thread worker không tự động mang toàn bộ security context, transaction và MDC của publisher. Nếu cần thông tin liên quan, truyền dữ liệu cần thiết trong event, dùng TaskDecorator/context propagation phù hợp và xác định transaction boundary cho task.

**Thứ tự:** @Order điều khiển thứ tự **đăng ký/gọi hoặc schedule listener** trong những tình huống phù hợp, nhưng với async không thể dùng nó để cam kết **listener A hoàn thành trước listener B**. Nếu công việc có dependency, hãy điều phối rõ bằng service/workflow hoặc xử lý tuần tự có kiểm soát.

## 9. Giải pháp 3: cấu hình ApplicationEventMulticaster với executor

Một cách khác là cấu hình **global ApplicationEventMulticaster** có executor. Cơ chế này ảnh hưởng **nhiều listener trên toàn context**, nên phải cân nhắc kỹ hơn so với đặt @Async trên một method.

Trong Spring Framework, đặt bean với tên đặc biệt **applicationEventMulticaster** (hằng số **AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME**) để context sử dụng nó.

Ví dụ cấu hình minh họa:

~~~java
@Configuration
class MulticasterConfiguration {

    @Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor) {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        multicaster.setErrorHandler(error ->
                System.err.println("Event handler error: " + error));
        return multicaster;
    }
}
~~~

Đoạn này **không phải file Java độc lập**; cần các import tương ứng từ **org.springframework.context.annotation**, **org.springframework.context.support.AbstractApplicationContext**, **org.springframework.context.event.SimpleApplicationEventMulticaster**, **org.springframework.beans.factory.annotation.Qualifier** và **ThreadPoolTaskExecutor**. Có thể dùng executor như cấu hình ở mục 8. **Không nên kích hoạt cả global async multicaster và @Async trên từng method nếu chưa hiểu cơ chế double-scheduling và quản lý executor**.

Cần nắm những giới hạn:

- **Global change:** các listener có khả năng chạy async sẽ thay đổi thread, thời điểm xử lý, error propagation và khả năng quan sát. Các listener cho startup event cũng có thể bị ảnh hưởng, do đó không được dựa vào việc một listener async hoàn tất trước startup runner.
- **supportsAsyncExecution():** trong Spring Framework 6.1+, một số ApplicationListener yêu cầu chạy trên publisher thread, chẳng hạn listener ràng buộc transaction. Global multicaster **không đồng nghĩa toàn bộ listener đều async**.
- **ErrorHandler:** cấu hình ở trên **log rồi không ném lại**, là quyết định ngăn lỗi đồng bộ lan lên caller. Chỉ dùng khi có chính sách xử lý lỗi phù hợp; nếu callback quan trọng fail, việc nuốt lỗi có thể tạo trạng thái không nhất quán.
- **Task rejection:** một executor có thể từ chối scheduling, phụ thuộc cấu hình multicaster và hành vi framework; không giả định có queue vô hạn hoặc không bao giờ rơi về luồng caller.
- **Không có durability:** chuyển listener sang executor trong RAM vẫn không tạo queue bền vững. Nếu JVM chết trước khi xử lý, task có thể mất.

Với một hoặc hai handler gửi thông báo độc lập, **@Async theo từng listener** hoặc hàng đợi/outbox thường dễ kiểm soát hơn. Global multicaster chỉ phù hợp nếu hiểu đầy đủ yêu cầu của các listener/framework events trong cả ứng dụng.

## 10. Error handling trong listener đồng bộ và bất đồng bộ

### Listener đồng bộ

Mặc định, **SimpleApplicationEventMulticaster** không có ErrorHandler nên exception từ một listener không được xử lý sẽ dừng đường multicast hiện tại và truyền về publisher. Ví dụ:

~~~java
@EventListener
void onInventoryChecked(InventoryChecked event) {
    throw new IllegalStateException("Audit unavailable");
}
~~~

Đây là method minh họa trong một Spring bean. Nếu caller đang trong **@Transactional**, exception runtime có thể khiến transaction rollback theo quy tắc transaction đã cấu hình, **nếu** exception lan qua transaction boundary. Tuy nhiên những tác dụng phụ bên ngoài transaction (API đã gọi, email đã gửi) không tự được hoàn tác.

Có thể catch exception cục bộ trong listener khi lỗi được phép bỏ qua, nhưng phải log và metric đủ để điều tra. Đừng catch toàn bộ Throwable rồi trả về “success” nếu handler là điều kiện bắt buộc để request/startup đúng đắn.

### Listener bất đồng bộ

Khi task đã submit và bắt đầu chạy trên thread khác, caller không nhận trực tiếp exception của handler. Vì vậy cần:

- Giám sát **async handler failures**, backlog, queue saturation, retry count và task age.
- Chọn cách retry idempotent, timeout và ngưỡng từ bỏ phù hợp.
- Xác định thứ tự/khả năng trùng lặp nếu có nhiều task liên quan tới cùng một entity.
- Không trông cậy transaction của publisher tự mở sang task thread.
- Định nghĩa shutdown: chờ đến hạn cho task quan trọng hoặc dùng queue bền vững nếu không được phép mất dữ liệu.

**Đặc biệt:** dùng ApplicationReadyEvent với listener @Async không biến công việc async thành điều kiện ready. Event có thể đã được phát và readiness được công bố trước khi task hoàn thành.

## 11. TransactionalEventListener khác @EventListener thường ở điểm nào?

**@TransactionalEventListener** cho phép phản ứng theo **pha transaction** (BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION). Pha mặc định là **AFTER_COMMIT**. Đây là công cụ để đồng bộ thời điểm phản ứng với transaction, không đơn giản là một biến thể của event async.

Ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreated event) {
    // Chi phan ung khi transaction co ket qua commit phu hop.
}
~~~

Đoạn trên là **mã minh họa**, chưa phải một lớp độc lập; cần các import của **org.springframework.transaction.event** và OrderCreated là kiểu event nghiệp vụ do ứng dụng định nghĩa. Khi không có transaction đang hoạt động, listener loại này **mặc định không được gọi**, trừ khi cấu hình **fallbackExecution=true**.

Trong Spring Framework 6.1+, các listener cần ràng buộc transaction có thể tuyên bố không hỗ trợ chạy async bởi multicaster, do chúng phải đồng bộ với thread/context giao dịch. **Không dùng global executor để mặc định “đẩy mọi TransactionalEventListener sang background”**.

Ngay cả ở pha AFTER_COMMIT, nếu gửi email/network call lâu trong callback đồng bộ, thread hoàn tất transaction vẫn có thể bị giữ. Với tích hợp quan trọng, mô hình outbox lưu một sự kiện bền vững cùng giao dịch và worker riêng gửi đi thường là lựa chọn đáng tin cậy hơn.

## 12. Chọn giải pháp theo tình huống

| Tình huống | Hướng thiết kế | Lý do |
| --- | --- | --- |
| Validate nhẹ ngay khi nghiệp vụ phát event | Đồng bộ, ngắn và fail rõ | Cần caller biết kết quả |
| Ghi metric hoặc log đơn giản | Đồng bộ và tối giản; hoặc collector phù hợp | Tác vụ nhỏ không cần thread riêng |
| Gửi email thông báo sau khi đơn hàng đã commit | Outbox/queue hoặc async listener nếu chấp nhận mất khi process chết | Không giữ request chờ email, kiểm soát retry |
| Warm up cache bắt buộc trước service ready | ApplicationRunner/CommandLineRunner có timeout | Công việc thuộc startup barrier rõ ràng |
| Event bên trong HTTP request gọi API bên thứ ba hàng giây | Tách xử lý và timeout/queue | Tránh chiếm request thread |
| Cần phản ứng sau transaction commit | @TransactionalEventListener(AFTER_COMMIT), cân nhắc outbox | Ràng buộc thời điểm với commit |
| Listener phục vụ audit bắt buộc không được mất | Outbox + durable messaging + idempotent consumer | @Async trong RAM không bền vững |
| CPU task nền lớn | Executor giới hạn hoặc hệ thống job phù hợp | Tránh nghẽn request/thread pool |
| Muốn mọi listener tự chạy background | Không đổi global multicaster vội; đánh giá từng listener | Lifecycle/transaction/error semantics có thể thay đổi |
| Consumer cần chạy liên tục và có lifecycle start/stop | SmartLifecycle/consumer container | Runner/event listener không tự quản lý vòng đời này |

**Tham số tối thiểu cần thiết kế với async:** max concurrency, queue capacity, policy khi queue đầy, timeout công việc, retry/backoff, idempotency, error reporting, shutdown deadline, trace correlation và bảo mật dữ liệu event.

## 13. Những lỗi rất thường gặp

**1. Cho rằng publishEvent luôn bất đồng bộ.** Sai. Mặc định listener chạy **đồng bộ** trong thread publisher.

**2. Dùng listener để gọi API bên ngoài không timeout.** Thread đang xử lý HTTP/runner có thể bị giữ vô thời hạn; dễ dẫn tới request timeout và thiếu thread.

**3. Đặt warm up nặng vào ApplicationStartedEvent.** Started xảy ra trước runner; listener chậm trì hoãn chuỗi khởi động. Chuyển sang runner nếu warm up phải hoàn thành trước ready.

**4. Đặt công việc dài vào ApplicationReadyEvent.** Event listener đồng bộ có thể trì hoãn readiness; dùng event để thông báo nhẹ, không thay thế job infrastructure.

**5. Thêm @Async nhưng quên @EnableAsync.** Annotation đơn lẻ không bảo đảm method chạy trên thread khác khi async processing chưa được bật.

**6. Tự gọi this.someAsyncMethod() từ chính bean.** Self-invocation có thể bỏ qua proxy, khiến @Async không hoạt động.

**7. Coi @Order là bảo đảm thứ tự hoàn tất trong async.** @Order có thể tác động thứ tự gọi/schedule, nhưng async task hoàn tất không theo thứ tự chắc chắn.

**8. Nghĩ exception async sẽ tự rollback transaction phía publisher.** Task chạy thread khác và lỗi thường không truyền ngược; cần transaction boundary và reporting riêng.

**9. Cấu hình global multicaster async mà không kiểm kê listener nhạy cảm.** Có thể ảnh hưởng startup event, transaction, security/logging context và kỳ vọng xử lý đồng bộ.

**10. Dùng queue executor vô hạn.** Lúc tải tăng, backlog ngốn bộ nhớ và latency, có thể làm JVM OOM; cần bounded queue, metrics và policy đầy.

**11. Nuốt exception của listener bắt buộc.** Publisher vẫn tiếp tục dù invariant chưa đạt; phân loại lỗi critical vs best-effort.

**12. Tin rằng @Async bảo đảm gửi message/email khi JVM tắt.** Async executor trong RAM không có durability; dùng outbox/broker khi tác vụ không được phép mất.

**13. Quên idempotency khi retry.** Event có thể được xử lý lại, gửi trùng email hoặc cập nhật trùng trạng thái; phải có khóa/idempotency key phù hợp.

**14. Bỏ qua backpressure.** Producer nhanh hơn consumer lâu dài sẽ làm đầy queue; async chỉ chuyển nơi nghẽn, không loại bỏ giới hạn năng lực.

**15. Đo mỗi thời gian controller mà không phân rã listener.** Khó biết bottleneck đến từ HTTP client, event handler hay xử lý chính; cần metric theo giai đoạn.

## 14. Checklist kiểm thử

1. **Bài test đồng bộ:** phát event từ một thread, xác minh publisher chỉ trở lại sau khi listener kết thúc. Ví dụ mục 5 minh họa bằng chuỗi PUBLISH_BEFORE → SLOW_* → AUDIT → PUBLISH_AFTER.
2. **Bài test ngoại lệ:** cho listener ném exception, xác minh hành vi publisher và listener xếp sau; không coi audit đã chạy nếu trước đó exception cắt ngang multicast.
3. **Bài test startup:** tạo listener Started/Ready có kiểm soát, xác nhận tác vụ dài làm trì hoãn mốc tương ứng; tránh sleep kéo dài trong CI thật.
4. **Bài test async:** dùng CountDownLatch hoặc CompletableFuture để đợi task hoàn tất theo điều kiện, **không** khẳng định thứ tự stdout giữa thread.
5. **Bài test tải:** thử lượng event cao và external I/O chậm, kiểm tra queue, memory, thread pool utilization và task rejection.
6. **Bài test shutdown:** dừng service khi còn task, xác minh policy chờ/ủy quyền xử lý không mất tác vụ quan trọng.
7. **Bài test transaction:** thử commit, rollback, AFTER_COMMIT và async context; không nhầm event đã phát với transaction đã commit.
8. **Quan sát vận hành:** log correlation ID thích hợp, timer theo listener, số lỗi/retry và tuổi của pending tasks.

Nếu test dùng **Spring Boot 3.x/Java 17+**, cần bảo đảm một lần kiểm thử không tình cờ chạy cả implementation synchronous và asynchronous của cùng nghiệp vụ rồi coi đó là thứ tự mặc định.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một controller gọi publishEvent và có listener mất 2 giây. Controller có thể trả response ngay không?  
**Trả lời:** Mặc định không; caller chờ xử lý listener đồng bộ hoàn tất, trừ khi code đã thiết kế async theo cách khác.

**Câu 2.** Có hai listener @Order(10) và @Order(20). Listener 10 chặn 5 giây. Listener 20 có được gọi ngay không?  
**Trả lời:** Với multicaster đồng bộ mặc định, listener 20 thường phải đợi listener 10 kết thúc trước khi được gọi.

**Câu 3.** Listener đồng bộ ném RuntimeException. Publisher có biết không?  
**Trả lời:** Có thể nhận exception được lan ngược về publisher theo cấu hình mặc định không có ErrorHandler nuốt lỗi.

**Câu 4.** Listener ApplicationStartedEvent chạy lâu ảnh hưởng thế nào?  
**Trả lời:** Nó có thể chặn luồng khởi động sau refresh và trì hoãn runner cùng readiness.

**Câu 5.** Đặt @Async trên listener có đủ để chạy async?  
**Trả lời:** Cần bật @EnableAsync và bảo đảm listener là bean chịu quản lý AOP phù hợp, với executor khả dụng.

**Câu 6.** Nếu listener @Async lỗi sau khi publisher đã trả về, exception có tự lan về publisher không?  
**Trả lời:** Không. Cần AsyncUncaughtExceptionHandler/logging/monitoring và chính sách xử lý thất bại riêng.

**Câu 7.** Task executor async có tự tạo transaction và copy MDC từ request không?  
**Trả lời:** Không tự động; cần cấu hình transaction, context propagation và thực hiện thiết kế phù hợp.

**Câu 8.** Global multicaster có executor khiến mọi listener đều chạy async?  
**Trả lời:** Không nhất thiết; trong Spring 6.1+ các listener không hỗ trợ async có thể vẫn phải chạy trong thread gốc.

**Câu 9.** Event nội bộ với @Async có thay được Kafka hoặc transactional outbox cho audit không được mất?  
**Trả lời:** Không. Async trong bộ nhớ không bảo đảm lưu bền vững hoặc gửi lại nếu JVM gặp sự cố.

**Câu 10.** Tác vụ warm up bắt buộc trước khi ready nên dùng gì?  
**Trả lời:** Runner có timeout/fail-fast phù hợp, không chạy async rồi công bố ready sớm.

**Ghi nhớ:** **Listener Spring mặc định chạy đồng bộ trên thread phát sự kiện.** Listener chậm làm chậm publisher và có thể ảnh hưởng request, transaction hoặc chuỗi khởi động. Hãy giữ synchronous listener ngắn, có timeout; dùng **runner** cho công việc bắt buộc lúc startup; dùng **@Async/executor** chỉ khi chấp nhận và xử lý các thay đổi về transaction, exception, ordering, shutdown; dùng **queue/outbox bền vững** khi không được phép mất event.

### Tài liệu tham khảo

- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Framework 6.1 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Observability Support for Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html)
