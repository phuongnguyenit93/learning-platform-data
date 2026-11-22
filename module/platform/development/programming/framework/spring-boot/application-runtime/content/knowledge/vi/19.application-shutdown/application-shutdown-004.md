# Phân biệt context.stop với context.close trong Spring Boot

## 1. Kết luận quan trọng nhất

Trong Spring Boot, biến `ConfigurableApplicationContext context` thường được lấy từ `SpringApplication.run(...)`. Hai method `context.stop()` và `context.close()` **không đồng nghĩa**:

- **`context.stop()`:** phát tín hiệu **dừng các bean tham gia hợp đồng `Lifecycle`/`SmartLifecycle`** thông qua `LifecycleProcessor`. Context **vẫn tồn tại**, bean factory và các singleton thông thường **chưa bị hủy**. Có thể gọi `context.start()` để bắt đầu lại các component có hỗ trợ restart.
- **`context.close()`:** kết thúc **vòng đời của chính ApplicationContext**, công bố `ContextClosedEvent`, dừng các lifecycle component còn chạy, gọi destruction callback của các singleton do context sở hữu và giải phóng resource liên quan. Sau khi đóng, **không sử dụng cùng context như một runtime có thể start/refresh bình thường**.

Một quy tắc dễ nhớ:

~~~text
context.stop()  = tạm dừng vòng đời các Lifecycle beans
context.start() = kích hoạt lại các Lifecycle beans trong context vẫn sống
context.close() = kết thúc ApplicationContext và hủy tài nguyên được quản lý
~~~

**Đừng đồng nhất việc `Lifecycle` bean không chạy với việc Spring context đã đóng.** Một context đã `stop()` vẫn có thể báo `isActive() == true`. Ngược lại, sau `close()` thành công, `isActive() == false` và singleton đã được dọn theo contract.

Bài học thuộc nhóm **Dừng ứng dụng** của module Spring Boot Application Runtime. Mục tiêu là hiểu rõ API, sự kiện, độ bền tài nguyên, trường hợp sử dụng, lỗi phổ biến và thực hành Java 17+.

## 2. Đọc nhanh bằng bảng so sánh

| Câu hỏi | `context.stop()` | `context.close()` |
| --- | --- | --- |
| Ý định | Dừng các component tham gia lifecycle | Kết thúc context, shutdown và cleanup |
| API xuất phát | `Lifecycle.stop()` trên context | `ConfigurableApplicationContext.close()` |
| Điều phối trung tâm | `LifecycleProcessor.stop()` | `doClose()` và `LifecycleProcessor.onClose()` |
| Sự kiện chính | `ContextStoppedEvent` | `ContextClosedEvent` |
| Dừng `Lifecycle` beans đang chạy? | Có, theo processor/phase | Có, trong đường đóng context thông thường |
| Gọi `@PreDestroy` của singleton chỉ vì lệnh này? | **Không** | **Có**, khi hủy singleton tương ứng |
| Gọi `DisposableBean.destroy()` do lệnh này? | **Không** | **Có**, khi bean được hủy |
| Gọi `@Bean(destroyMethod = "close")` do lệnh này? | **Không** | **Có**, khi singleton thuộc container được destroy |
| BeanFactory có bị hủy? | Không | Có, theo quá trình đóng context |
| `context.isActive()` khi lệnh hoàn tất | Thường vẫn true nếu context đã refresh | False khi close hoàn tất |
| `context.isRunning()` khi lệnh hoàn tất | Thường false đối với LifecycleProcessor | Không nên coi context đã đóng là một runtime để gọi lifecycle |
| Có thể `context.start()` lại? | **Có**, nếu component hỗ trợ restart và context còn active | **Không** trên cùng context đã đóng |
| Có tạo lại toàn bộ bean? | Không | Không; phải tạo context mới cho một lần chạy mới |
| Có chạy lại `ApplicationRunner`? | Không | Không |
| Có phát lại `ApplicationReadyEvent` khi start lại? | Không tự động | Không |
| Cần dùng cho kết thúc tiến trình? | Không đủ | Là bước shutdown context, nhưng không tự bảo đảm JVM thoát |
| Thích hợp | Tạm dừng worker/consumer, điều khiển lifecycle có kiểm soát | Thoát ứng dụng, giải phóng resource, kết thúc integration test |

Bảng mô tả các implementation thông dụng dựa trên `AbstractApplicationContext` và `DefaultLifecycleProcessor` của Spring Framework. Một bean hoàn toàn tự chạy thread mà **không** implement `Lifecycle` có thể tiếp tục hoạt động sau `stop()`. Vì thế “context đã stop” không bảo đảm tất cả tác vụ nền hoặc mọi loại request đã dừng.

## 3. Các interface có liên quan

### 3.1. Lifecycle: start, stop, isRunning

Spring Framework khai báo `org.springframework.context.Lifecycle`, với ba method:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Đây là **trích chữ ký rút gọn để học API**, không phải interface cần tự định nghĩa lại. Bất kỳ bean Spring nào implement `Lifecycle` đều có thể được điều phối khi application context nhận tín hiệu start hoặc stop tường minh.

`isRunning()` là thông tin để lifecycle processor biết component có đang chạy không. Nó không thay cho việc theo dõi trạng thái resource thực, nhất là với tác vụ bất đồng bộ.

### 3.2. SmartLifecycle: tự khởi động và dừng theo phase

`org.springframework.context.SmartLifecycle` mở rộng `Lifecycle` và `Phased`. Nó bổ sung:

- `isAutoStartup()`: component có tự start khi context refresh hay không. Giá trị mặc định của SmartLifecycle là true.
- `getPhase()`: chọn phase; phase thấp start trước, phase cao stop trước, có xét quan hệ dependency.
- `stop(Runnable callback)`: thông báo hoàn tất khi component **đã dừng xong**; lifecycle processor có thể cần đợi callback trong shutdown.

Cần phân biệt `stop()` không tham số và `stop(Runnable)`. Một implementation SmartLifecycle bất đồng bộ phải bảo đảm callback không chạy trước khi tasks/connection đã được dừng theo hợp đồng. Không được gọi callback ngay sau `ExecutorService.shutdown()` nếu task vẫn đang chạy mà ứng dụng đòi graceful drain.

### 3.3. ConfigurableApplicationContext

`org.springframework.context.ConfigurableApplicationContext` mở rộng `ApplicationContext`, `Lifecycle` và `Closeable`. Vì vậy có các method `start()`, `stop()`, `isRunning()`, `close()`, đồng thời có `isActive()` và `isClosed()`.

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

context.stop();   // Dừng lifecycle components.
context.start();  // Cho phép khởi động lại khi context còn active.
context.close();  // Đóng context và hủy các singleton thuộc container.
~~~

Đây là **đoạn minh họa trong một chương trình Spring Boot**, cần một class `MyApplication` hợp lệ và import tương ứng, không phải file Java độc lập.

Một điểm quan trọng: `isRunning()` và `isActive()` trả lời **hai câu hỏi khác nhau**.

- `isRunning()`: lifecycle processor đang ở trạng thái chạy hay dừng.
- `isActive()`: context đã refresh ít nhất một lần và chưa được đóng hết vòng đời hay chưa.

Vì vậy sau `context.stop()` có thể là:

~~~text
context.isActive()  -> true
context.isRunning() -> false
~~~

Đó **không phải trạng thái mâu thuẫn**.

## 4. Điều gì xảy ra bên trong context.stop()?

Với `AbstractApplicationContext`, lời gọi `stop()` được chuyển cho lifecycle processor, rồi Spring phát `ContextStoppedEvent`. Với processor mặc định, các `Lifecycle` beans đang chạy nhận tín hiệu dừng theo phase/dependency.

~~~text
Code ứng dụng gọi context.stop()
   |
   +-- AbstractApplicationContext.stop()
   |     +-- getLifecycleProcessor().stop()
   |           +-- Dừng Lifecycle / SmartLifecycle đang chạy
   |           +-- Phối hợp phase và stop callback phù hợp
   |
   +-- publishEvent(ContextStoppedEvent)
   |
   v
Lệnh stop() trả về
   |
   +-- ApplicationContext vẫn active
   +-- BeanFactory còn sống
   +-- Singleton được quản lý vẫn tồn tại
   +-- @PreDestroy / destroyMethod không chạy chỉ vì stop
~~~

Đây là đường xử lý khái quát trong Spring Framework. Với callback stop bất đồng bộ, processor có thể chờ tới giới hạn phase timeout; việc method `stop()` trả về không bảo đảm mọi resource ngoài process đã được đóng nếu implementation không hoàn thành đúng contract.

### Điều gì không xảy ra?

`context.stop()` **không có nghĩa**:
- Xóa toàn bộ bean definition hoặc bean singleton.
- Tạo một BeanFactory khác.
- Gọi lại `@PostConstruct` của singleton khi start lại.
- Hủy connection pool theo `@PreDestroy`.
- Dừng bắt buộc mọi thread tự tạo ngoài Spring lifecycle.
- Đóng JVM hoặc thực hiện `System.exit`.
- Phát `ContextClosedEvent` theo đường stop thông thường.
- Phát lại các sự kiện startup của `SpringApplication.run`.
- Chuyển toàn bộ Spring Boot readiness/liveness sang một trạng thái cụ thể chỉ nhờ gọi method này.

Nếu một tài nguyên không implement `Lifecycle`, không được cho rằng nó tự dừng chỉ vì context đã nhận stop. Ví dụ, một thread được tạo thủ công trong constructor mà không đăng ký stop callback vẫn có thể chạy.

## 5. Điều gì xảy ra bên trong context.start() sau stop?

`context.start()` gọi `LifecycleProcessor.start()`, rồi phát `ContextStartedEvent`. Với những bean hỗ trợ restart, điều đó kích hoạt chúng chạy lại, nhưng **không làm mới ApplicationContext**.

~~~text
context.stop()  -> ContextStoppedEvent
     |
     | Bean singleton vẫn là các instance cũ
     | Context vẫn active
     |
context.start() -> LifecycleProcessor.start()
                -> ContextStartedEvent
     |
     +-- Lifecycle beans được start lại theo phase
     +-- @PostConstruct không chạy lại
     +-- ApplicationRunner.run() không chạy lại
     +-- ApplicationReadyEvent không tự phát lại
~~~

Điều này giải thích vì sao nên viết `SmartLifecycle.start()` và `SmartLifecycle.stop()` **idempotent**:
- Gọi start khi đã chạy phải không mở thêm consumer/socket trùng.
- Gọi stop khi đã dừng phải an toàn.
- Nếu component có hỗ trợ restart, một lần stop thành công rồi start lại có thể tạo một resource generation mới.
- Nếu thư viện không hỗ trợ khởi động lại sau close, component phải tạo object mới hoặc báo lỗi rõ ràng, không giả vờ rằng instance cũ sống lại.

### ContextStartedEvent khác ApplicationStartedEvent

Tên giống nhau nhưng cấp độ khác nhau:

| Sự kiện | Package | Khi nào |
| --- | --- | --- |
| `ContextStartedEvent` | Spring Framework: `org.springframework.context.event` | Khi gọi `ApplicationContext.start()` |
| `ContextStoppedEvent` | Spring Framework: `org.springframework.context.event` | Khi gọi `ApplicationContext.stop()` |
| `ContextRefreshedEvent` | Spring Framework: `org.springframework.context.event` | Khi context refresh xong |
| `ApplicationStartedEvent` | Spring Boot: `org.springframework.boot.context.event` | Trong `SpringApplication.run` sau refresh, trước runners |
| `ApplicationReadyEvent` | Spring Boot: `org.springframework.boot.context.event` | Trong `SpringApplication.run` sau runners thành công |

**Gọi `context.start()` không đồng nghĩa gọi lại `SpringApplication.run(...)`.** Do đó nó không tự tạo một chuỗi `ApplicationStartedEvent → runner → ApplicationReadyEvent` mới.

## 6. Điều gì xảy ra bên trong context.close()?

`close()` là đường kết thúc của `ApplicationContext`. Theo `AbstractApplicationContext.doClose()`, trong đường close thông thường:

~~~text
Yêu cầu context.close()
   |
   +-- Đánh dấu bắt đầu đóng context
   +-- Công bố ContextClosedEvent
   |     +-- Listener nhận được tín hiệu context đang đóng
   |
   +-- LifecycleProcessor.onClose()
   |     +-- Yêu cầu các Lifecycle / SmartLifecycle beans đang chạy dừng
   |     +-- Đợi callback dừng theo phase/timeout
   |
   +-- destroyBeans()
   |     +-- @PreDestroy
   |     +-- DisposableBean.destroy()
   |     +-- @Bean(destroyMethod = "close"/"shutdown"/...)
   |     +-- Cleanup các singleton do context sở hữu
   |
   +-- closeBeanFactory() và các bước onClose/finalize context
   |
   v
Đã đóng: context.isActive() == false
~~~

**Lưu ý lớn:** `ContextClosedEvent` được phát **khi context đang bắt đầu đóng**, trước khi tất cả singleton bị hủy. Vì vậy trong listener của `ContextClosedEvent`, bạn có thể vẫn nhìn thấy một worker đang RUNNING và resource chưa close. Chỉ đọc tên “Closed” rồi tưởng mọi connection đã đóng xong là sai.

Không có quy tắc rằng gọi `close()` sẽ tự phát thêm `ContextStoppedEvent`. Đường close có `LifecycleProcessor.onClose()` để dừng component, nhưng sự kiện tiêu biểu được công bố là `ContextClosedEvent`, không phải một lần gọi tường minh `context.stop()`.

### close() có cần được gọi sau stop() không?

Thông thường **không cần**. `context.close()` đã điều phối việc dừng các lifecycle bean đang chạy trước khi destroy singleton. Gọi `context.stop()` rồi `context.close()` có thể hữu ích nếu cần tách giai đoạn dừng nhận work khỏi giai đoạn giải phóng tài nguyên, nhưng không phải mẫu bắt buộc.

Nếu một component đã STOPPED trước đó, lifecycle processor thường không dừng lại resource đã ngừng. Destroy callbacks vẫn chạy khi đóng context để giải phóng tài nguyên thuộc bean.

### close() có gọi được hai lần không?

`ConfigurableApplicationContext.close()` được thiết kế có thể gọi nhiều lần; các lần sau khi đã đóng thường bị bỏ qua, không hủy singleton lại. Nhưng điều này **không cho phép sử dụng bean sau close**. Một object reference bạn giữ bên ngoài vẫn tồn tại trong heap, nhưng tài nguyên bên trong có thể đã đóng và bean không còn được container quản lý.

### Context đóng rồi có refresh/start lại được không?

Không nên và trong các context Boot thông thường **không được**. Spring Framework mô tả context đã đóng là cuối vòng đời, không thể restart/refresh. Nếu muốn chạy ứng dụng mới, cần tạo **một ApplicationContext mới** bằng `SpringApplication.run` hay cơ chế bootstrap tương ứng.

Đặc biệt, `GenericApplicationContext` cũng không hỗ trợ multiple refresh trên cùng instance ngay cả khi chưa close. Đừng suy từ việc một số triển khai Spring khác hỗ trợ hot refresh rồi áp dụng với mọi context.

## 7. Ví dụ chạy được Java 17+ / Spring Boot 3.5.16

Ta sẽ làm một chương trình không có web server để quan sát độc lập:

1. Khi refresh, một `SmartLifecycle` tự start.
2. `ApplicationStartedEvent`, runner và `ApplicationReadyEvent` xảy ra trong đường Spring Boot startup.
3. Gọi `context.stop()`: worker dừng, `ContextStoppedEvent` xuất hiện, nhưng resource singleton chưa bị destroy.
4. Gọi `context.start()`: worker start lại, `ContextStartedEvent` xuất hiện, **không** chạy lại runner.
5. Gọi `context.close()`: `ContextClosedEvent` đến trước lần stop cuối và trước destroy callback.
6. Sau close, context không active, worker ngừng, resource bị đóng.

Ví dụ dùng resource in-memory và in marker, không cần database hay HTTP port. Thứ tự marker có thể kiểm chứng trực tiếp, còn log framework có thể xen giữa.

### 7.1. Cấu trúc project

~~~text
stop-close-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/stopclose/
                └── StopVsCloseApplication.java
~~~

### 7.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>stop-close-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.5.16 đã được phát hành và có trên Maven Central. Đây là phiên bản minh họa để giữ API ổn định; nhánh 3.5.x đã hết hỗ trợ OSS, nên đối với production mới hãy ưu tiên nhánh Spring Boot còn được hỗ trợ và đối chiếu package/API tương ứng.

### 7.3. Tệp Java đầy đủ

Lưu thành `src/main/java/com/example/stopclose/StopVsCloseApplication.java`:

~~~java
package com.example.stopclose;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class StopVsCloseApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StopVsCloseApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);
        TrackedWorker worker = context.getBean(TrackedWorker.class);
        SharedResource resource = context.getBean(SharedResource.class);

        try (context) {
            System.out.println("07_BEFORE_STOP active="
                    + context.isActive()
                    + " running=" + worker.isRunning()
                    + " destroyed=" + resource.isClosed());

            context.stop();

            System.out.println("10_AFTER_STOP active="
                    + context.isActive()
                    + " running=" + worker.isRunning()
                    + " destroyed=" + resource.isClosed());

            context.start();

            System.out.println("13_AFTER_START active="
                    + context.isActive()
                    + " running=" + worker.isRunning()
                    + " destroyed=" + resource.isClosed());
        }

        // try-with-resources vừa đóng ApplicationContext.
        System.out.println("17_AFTER_CLOSE active="
                + context.isActive()
                + " running=" + worker.isRunning()
                + " destroyed=" + resource.isClosed());
    }

    @Bean(destroyMethod = "close")
    SharedResource sharedResource() {
        return new SharedResource();
    }

    @Bean
    TrackedWorker trackedWorker(SharedResource resource) {
        return new TrackedWorker(resource);
    }

    @Bean
    EventTimeline eventTimeline(
            TrackedWorker worker, SharedResource resource) {
        return new EventTimeline(worker, resource);
    }

    @Bean
    ApplicationRunner runner(
            TrackedWorker worker, SharedResource resource) {
        return args -> System.out.println("05_RUNNER running="
                + worker.isRunning()
                + " destroyed=" + resource.isClosed());
    }

    public static final class SharedResource implements AutoCloseable {
        private boolean closed;

        public SharedResource() {
            System.out.println("01_RESOURCE_CREATED");
        }

        public synchronized boolean isClosed() {
            return closed;
        }

        @Override
        public synchronized void close() {
            if (closed) {
                return;
            }
            closed = true;
            System.out.println("16_RESOURCE_DESTROYED");
        }
    }

    public static final class TrackedWorker implements SmartLifecycle {
        private final SharedResource resource;
        private boolean running;
        private int generation;

        public TrackedWorker(SharedResource resource) {
            this.resource = resource;
        }

        @Override
        public synchronized void start() {
            if (running) {
                return;
            }
            if (resource.isClosed()) {
                throw new IllegalStateException("resource destroyed");
            }
            running = true;
            generation++;
            System.out.println("WORKER_START generation=" + generation);
        }

        @Override
        public synchronized void stop() {
            if (!running) {
                return;
            }
            running = false;
            System.out.println("WORKER_STOP generation=" + generation);
        }

        @Override
        public void stop(Runnable callback) {
            // Trong demo, stop hoàn toàn đồng bộ và không có I/O.
            try {
                stop();
            } finally {
                callback.run();
            }
        }

        @Override
        public synchronized boolean isRunning() {
            return running;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }
    }

    public static final class EventTimeline {
        private final TrackedWorker worker;
        private final SharedResource resource;

        public EventTimeline(
                TrackedWorker worker, SharedResource resource) {
            this.worker = worker;
            this.resource = resource;
        }

        @EventListener
        public void refreshed(ContextRefreshedEvent event) {
            System.out.println("03_CONTEXT_REFRESHED");
        }

        @EventListener
        public void bootStarted(ApplicationStartedEvent event) {
            System.out.println("04_APPLICATION_STARTED");
        }

        @EventListener
        public void ready(ApplicationReadyEvent event) {
            System.out.println("06_APPLICATION_READY");
        }

        @EventListener
        public void stopped(ContextStoppedEvent event) {
            System.out.println("09_CONTEXT_STOPPED");
        }

        @EventListener
        public void started(ContextStartedEvent event) {
            System.out.println("12_CONTEXT_STARTED");
        }

        @EventListener
        public void closed(ContextClosedEvent event) {
            System.out.println("14_CONTEXT_CLOSED running="
                    + worker.isRunning()
                    + " destroyed=" + resource.isClosed());
        }
    }
}
~~~

**Điểm kỹ thuật của mã:**

- `SharedResource` là singleton với `@Bean(destroyMethod = "close")`. Spring context là owner của tài nguyên này; `stop()` không gọi destroy method.
- `TrackedWorker` implement `SmartLifecycle`, có `isAutoStartup() == true` nên Spring start nó trong refresh; `getPhase() == 100` là phase minh họa.
- `start()` và `stop()` xử lý no-op khi đã ở trạng thái tương ứng; chúng không mở hoặc đóng lại resource singleton.
- `stop(Runnable)` gọi callback khi stop đồng bộ đã trả về. Với resource bất đồng bộ, phải đợi dừng thật mới chạy callback.
- `EventTimeline` là bean Spring bình thường. `@EventListener` nhận các sự kiện được công bố ở những mốc tương ứng.
- `ApplicationRunner` chỉ được Boot gọi **một lần trong `SpringApplication.run`**; `context.start()` không khởi chạy runner lần thứ hai.
- `try (context)` hợp lệ từ Java 9 cho biến effectively final và tự gọi `close()`. Ta vẫn giữ reference `worker` và `resource` để xem trạng thái sau close; trong thực tế không dùng chúng để thực thi nghiệp vụ sau khi context đã đóng.

### 7.4. Lệnh chạy

Trong thư mục có `pom.xml`:

~~~bash
mvn package
java -jar target/stop-close-demo-0.0.1-SNAPSHOT.jar
~~~

Hoặc:

~~~bash
mvn spring-boot:run
~~~

Chỉ cần JDK 17+, Maven tương thích và dependency từ Maven Central. Không cần cấu hình `application.properties` hay mở cổng HTTP.

### 7.5. Kết quả mong đợi

Lọc các dòng **do mã ví dụ tự in**; Spring Boot banner và logs khác có thể xen giữa. Thứ tự kỳ vọng:

~~~text
01_RESOURCE_CREATED
WORKER_START generation=1
03_CONTEXT_REFRESHED
04_APPLICATION_STARTED
05_RUNNER running=true destroyed=false
06_APPLICATION_READY
07_BEFORE_STOP active=true running=true destroyed=false
WORKER_STOP generation=1
09_CONTEXT_STOPPED
10_AFTER_STOP active=true running=false destroyed=false
WORKER_START generation=2
12_CONTEXT_STARTED
13_AFTER_START active=true running=true destroyed=false
14_CONTEXT_CLOSED running=true destroyed=false
WORKER_STOP generation=2
16_RESOURCE_DESTROYED
17_AFTER_CLOSE active=false running=false destroyed=true
~~~

Thứ tự này đúng với chương trình minh họa và các listener đồng bộ. Nhãn số bỏ qua 02/08/11/15 vì bốn dòng đó in tên hành động có `generation`; số nhãn không phải API của Spring.

### 7.6. Diễn giải từng phần output

**Startup:**
1. `01_RESOURCE_CREATED`: container tạo singleton SharedResource, chưa đến lúc hủy.
2. `WORKER_START generation=1`: `DefaultLifecycleProcessor.onRefresh()` auto-start SmartLifecycle trong refresh.
3. `03_CONTEXT_REFRESHED`: context refresh hoàn tất.
4. `04_APPLICATION_STARTED`: Boot đã refresh xong, trước runners.
5. `05_RUNNER ...`: Runner chạy sau started; resource vẫn còn mở.
6. `06_APPLICATION_READY`: Runner thành công; Boot phát ready.

**Stop tường minh:**
7. `07_BEFORE_STOP`: context active, worker running, resource chưa destroy.
8. `WORKER_STOP generation=1`: `context.stop()` yêu cầu lifecycle bean dừng.
9. `09_CONTEXT_STOPPED`: sự kiện stop được công bố.
10. `10_AFTER_STOP active=true running=false destroyed=false`: **bằng chứng then chốt**: stop không phá context và không hủy singleton.

**Start lại:**
11. `WORKER_START generation=2`: worker khởi động lại sau stop.
12. `12_CONTEXT_STARTED`: framework phát sự kiện start context.
13. `13_AFTER_START ...`: cùng context vẫn active, cùng SharedResource vẫn chưa destroy; runner không chạy lại.

**Close:**
14. `14_CONTEXT_CLOSED running=true destroyed=false`: sự kiện đóng đến **trước** lúc lifecycle processor dừng worker và hủy resource.
15. `WORKER_STOP generation=2`: lifecycle processor dừng worker khi context đóng.
16. `16_RESOURCE_DESTROYED`: destroy method của singleton chạy sau bước dừng lifecycle.
17. `17_AFTER_CLOSE active=false running=false destroyed=true`: context đã kết thúc vòng đời.

Đặc biệt, trong đoạn close không có thêm `09_CONTEXT_STOPPED`; đó là vì `close()` dùng đường đóng riêng, không phải tự gọi `context.stop()` rồi phát cùng một event như lệnh stop tường minh.

## 8. So sánh bằng trạng thái của context và bean

Không nên đánh đồng ba phép hỏi:

~~~java
context.isActive();
context.isRunning();
worker.isRunning();
~~~

- `context.isActive()`: toàn context còn được xem là active hay không.
- `context.isRunning()`: trạng thái của `LifecycleProcessor` (đại diện cho lệnh lifecycle).
- `worker.isRunning()`: trạng thái **riêng** do một bean Lifecycle/SmartLifecycle báo.

Trong một ứng dụng có nhiều bean, `context.isRunning() == true` **không chứng minh mọi component đang chạy đúng nghiệp vụ**. Một bean có thể thất bại, không implement Lifecycle hoặc có state của riêng nó.

Một bảng diễn giải điển hình:

| Mốc | Context active | Lifecycle processor running | Worker running | Singleton destroyed |
| --- | --- | --- | --- | --- |
| Sau startup bình thường | true | thường true | true | false |
| Sau `context.stop()` | true | false | false | false |
| Sau `context.start()` | true | true | true | false |
| Khi nhận `ContextClosedEvent` | Đang trong quá trình đóng | Có thể còn đang running | Có thể còn running | Thường chưa |
| Sau `context.close()` trả về | false | Không còn lifecycle runtime để sử dụng | false nếu cleanup hoàn tất | true với singleton có destroy callback |

Trong demo, `EventTimeline.closed(...)` ghi `running=true` và `destroyed=false` khi nhận `ContextClosedEvent`, vì event được phát trước giai đoạn lifecycle stop và bean destruction. Không áp mặc định bảng này cho mọi context custom hoặc môi trường shutdown bất thường.

## 9. Sự kiện nào dùng cho mục đích nào?

| Sự kiện | Khi nào? | Có thể dùng để làm gì? |
| --- | --- | --- |
| `ContextRefreshedEvent` | Sau refresh context | Quan sát container đã được khởi tạo |
| `ContextStartedEvent` | Sau lệnh `context.start()` | Ghi nhận thao tác start lifecycle tường minh |
| `ContextStoppedEvent` | Sau lệnh `context.stop()` | Ghi nhận thao tác stop lifecycle tường minh |
| `ContextClosedEvent` | Khi context bắt đầu đóng | Theo dõi shutdown/đưa tín hiệu ngừng hoạt động |
| `ApplicationStartedEvent` | Spring Boot startup, sau refresh trước runner | Mốc bắt đầu app theo Boot, không phải restart lifecycle |
| `ApplicationReadyEvent` | Sau runners, lúc kết thúc startup do Boot quản lý | Quan sát Boot ready, không phải tương đương ContextStarted |
| `ApplicationFailedEvent` | Trong quá trình Spring Boot startup gặp lỗi | Quan sát thất bại khởi động, không có nghĩa close luôn phát |
| `AvailabilityChangeEvent` | Khi Boot/app công bố liveness/readiness | Báo trạng thái khả dụng độc lập với context start/stop |

Các event Spring Framework có thể được truyền trong một hierarchy context cha/con. Nếu listener ở parent context nhận event của child, cần kiểm tra `event.getApplicationContext()` trước khi kết luận context của listener đã stop/close.

### ContextStoppedEvent không thay thế ContextClosedEvent

Một listener chỉ lắng nghe `ContextStoppedEvent` có thể **không được gọi** khi JVM shutdown hook đóng context trực tiếp. Nếu tác vụ cần giải phóng resource của bean khi ứng dụng kết thúc, hãy dùng destruction callbacks như `@PreDestroy`, `DisposableBean`, configured destroy method và/hoặc `SmartLifecycle.stop(Runnable)`.

### ContextClosedEvent không có nghĩa đã dọn xong

Vì event đến sớm, listener nên làm những công việc ngắn như log, quan sát và chuyển trạng thái cần thiết, không giả định mọi kết nối đã đóng. Với resource được một bean sở hữu, cleanup cuối cùng nên nằm trong lifecycle/destroy callback của bean đó.

## 10. Có nên gọi context.stop() để tạm ngừng HTTP service?

**Không nên mặc định**. `context.stop()` là tín hiệu điều khiển Spring `Lifecycle` beans. Trong web application, một số thành phần máy chủ nhúng hoặc listener container cũng tham gia lifecycle và có thể bị dừng. Điều đó không giống một giao thức tạm dừng traffic **được thiết kế cho load balancer và Kubernetes**.

Để bảo trì/rolling deployment, thường cần các bước:

1. Chuyển instance sang trạng thái không nhận traffic mới theo cơ chế readiness.
2. Đợi routing/load balancer cập nhật và giảm request mới.
3. Cho các request đang xử lý hoàn thành trong thời hạn phù hợp.
4. Dừng consumer/worker theo lifecycle của chúng.
5. Khi muốn kết thúc tiến trình, gọi close theo đường shutdown bình thường.

Chỉ gọi `context.stop()` **không tự đảm bảo**:
- Kubelet đã rút pod khỏi Service endpoints.
- HTTP server tiếp tục phục vụ request hoặc đã dừng hoàn toàn; chi tiết phụ thuộc server/lifecycle.
- Tất cả request đang chạy đã hoàn thành.
- `ReadinessState` đã chuyển `REFUSING_TRAFFIC`.
- Spring Boot sẽ phát lại `ApplicationReadyEvent` khi `context.start()`.

Nếu muốn tạm dừng xử lý message nhưng giữ HTTP API quản trị sống, đôi khi nên **stop riêng listener container/consumer**, không stop toàn bộ context. Ví dụ dùng API lifecycle của Kafka listener container, JMS listener container hoặc một SmartLifecycle bean cụ thể, sau khi xác minh contract và những dependency liên quan.

### Liveness và readiness không phải context.isRunning

Trong Spring Boot, `ApplicationAvailability` duy trì `LivenessState` và `ReadinessState` dựa trên các sự kiện availability. Sử dụng Actuator probes nếu cần cung cấp tín hiệu chuẩn cho hệ thống điều phối. Không chỉ nhìn `context.isRunning()` để suy ra readiness thực tế.

Trong startup bình thường, Boot công bố:
- Sau `ApplicationStartedEvent`, liveness `CORRECT`.
- Sau runner và `ApplicationReadyEvent`, readiness `ACCEPTING_TRAFFIC`.

Một lệnh `context.stop()` tường minh **không phải một lần Spring Boot startup/shutdown hoàn chỉnh**, nên không được tự suy luận rằng nó luôn đảo các trạng thái availability giống một lifecycle chính thức của Boot. Nếu nghiệp vụ cần từ chối traffic khi tạm dừng, phải thiết kế việc công bố trạng thái readiness và điều phối routing phù hợp.

## 11. Graceful shutdown và context.close()

Với Spring Boot web application, graceful shutdown được thực hiện trong đường đóng `ApplicationContext` và phối hợp với phase dừng các `SmartLifecycle` beans. Ở Spring Boot 3.5, graceful shutdown là mặc định đối với các embedded server được hỗ trợ.

Cấu hình tham khảo:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

`server.shutdown=graceful` ghi rõ chế độ; `spring.lifecycle.timeout-per-shutdown-phase` giới hạn thời gian chờ theo phase. Một số phiên bản/triển khai có mặc định khác, vì vậy phải kiểm tra version và cấu hình thực tế. Hệ thống bên ngoài như Kubernetes còn có `terminationGracePeriodSeconds` và load balancer drain timeout riêng.

**Giới hạn cần nhớ:**
- Timeout phase **không cưỡng chế** mọi thread/network task dừng hoàn toàn.
- Khi JVM bị `SIGKILL` hoặc crash, shutdown hook có thể không chạy.
- Trong lúc server ngừng nhận request, readiness endpoint có thể **không trả response nào**, thay vì một JSON 503.
- Tác vụ xử lý lâu cần cancellation, timeout hoặc cơ chế checkpoint/retry phù hợp.
- Close context không tự đảm bảo các tác vụ bên ngoài JVM đã kết thúc.

### Dùng stop rồi close có lợi ở đâu?

Trong một quy trình shutdown nhiều bước, có thể chủ động stop một nhóm consumer sớm để ngừng nhận work rồi đóng context khi workload đã drain. Nhưng nếu gọi `context.stop()` cho toàn context, một số thành phần hạ tầng cần thiết cho việc drain (server, scheduler, listener...) cũng có thể bị dừng. Do đó hãy ưu tiên phối hợp **component-level lifecycle** nếu cần điều khiển có chọn lọc.

## 12. Đóng context, kết thúc JVM và SpringApplication.exit

Ba việc này khác nhau:

| Lệnh | Hành vi chính | JVM có tự kết thúc ngay không? |
| --- | --- | --- |
| `context.stop()` | Dừng lifecycle beans | Không |
| `context.close()` | Đóng ApplicationContext, destroy managed singleton | Không nhất thiết |
| `SpringApplication.exit(context)` | Tính exit code từ `ExitCodeGenerator` và thực hiện close context theo API Boot | Chưa tự gọi `System.exit(...)` |
| `System.exit(code)` | Yêu cầu JVM shutdown process, có thể chạy shutdown hooks | Có, nếu JVM thực thi đường shutdown |
| `Runtime.getRuntime().halt(code)` | Kết thúc JVM cưỡng bức | Bỏ qua shutdown hook, có nguy cơ mất dữ liệu |

Ví dụ ứng dụng CLI muốn đóng Spring context và trả mã lỗi cho hệ thống gọi:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

Đây là **đoạn minh họa, không độc lập**: cần class `MyApplication`. Chỉ dùng `System.exit` ở application entry point phù hợp, không gọi từ service tùy tiện hoặc thư viện.

Trong web server thông thường, nên để Spring Boot xử lý JVM shutdown hook và container orchestration thay vì phát `System.exit` từ một controller. Việc gọi exit là quyết định ở **cấp tiến trình**, rộng hơn nhiều so với stop/close của một context.

### Shutdown hook của Spring Boot

Spring Boot mặc định đăng ký shutdown hook để đóng context khi JVM kết thúc bình thường theo đường JVM hỗ trợ. Shutdown hook dẫn tới **close**, không phải một lệnh `context.stop()` độc lập cần khôi phục sau đó.

Tuy nhiên, không có bảo đảm shutdown hook chạy trong `kill -9`, mất điện hoặc JVM halt. Những tác vụ cần exactly-once bên ngoài process vẫn phải dựa trên transaction/idempotency/lease/retry độc lập.

## 13. Đừng bỏ qua quan hệ parent/child context

Một JVM có thể chứa nhiều `ApplicationContext`, ví dụ parent chia sẻ các service nền tảng và child đại diện cho module/web context.

Theo hợp đồng `ConfigurableApplicationContext.close()`, **đóng một context không tự gọi close của parent context**. Vì vậy:

- `child.close()` dọn các singleton do **child sở hữu**.
- Resource sống trong parent không nên bị child đóng nhầm.
- Parent có thể vẫn active khi child đã close.
- Listener ở parent có thể nhận event được truyền lên từ child; cần lọc theo `event.getApplicationContext()`.
- `child.stop()` là lệnh lifecycle của context đó, không nên xem như dừng toàn bộ hierarchy nếu không kiểm chứng cơ chế liên quan.

Ownership tài nguyên và giới hạn context là hai vấn đề quan trọng. Ví dụ, một child service được inject một pool do parent sở hữu thì không tự đóng pool khi child stop hoặc close, nếu parent còn phục vụ child khác.

### Một bean không nằm trong context có bị dừng?

Không tự động. Nếu tự tạo object bằng `new`, không đăng ký nó làm Spring bean và không nối với lifecycle processor, `context.stop()` hoặc `context.close()` không biết để gọi các method lifecycle của object đó. Code của bạn phải chuyển quyền sở hữu resource cho bean quản lý hoặc tự dọn đúng scope.

## 14. Lifecycle, destruction và resource ownership

Không phải mọi bean đều implement Lifecycle. Vì vậy phải chọn đúng điểm mở rộng:

| Trách nhiệm | Cơ chế thích hợp |
| --- | --- |
| Tạm dừng/khởi động lại một background worker | `Lifecycle` hoặc `SmartLifecycle` |
| Dừng consumer với phase/async completion | `SmartLifecycle.stop(Runnable)` |
| Đóng HTTP/JDBC pool được Spring sở hữu | `@Bean(destroyMethod=...)`, `@PreDestroy` hoặc `DisposableBean` |
| Đóng stream/response của một operation | `try-with-resources` tại operation |
| Báo mốc context đang đóng | `ContextClosedEvent` listener |
| Báo mốc context đã stop theo lệnh tường minh | `ContextStoppedEvent` listener |
| Thay đổi readiness cho hệ thống điều phối | `AvailabilityChangeEvent<ReadinessState>` và Actuator probe |
| Chạy việc một lần sau refresh | `ApplicationRunner` / `CommandLineRunner` |
| Hoàn tất startup và nhận traffic | `ApplicationReadyEvent` + readiness policy |

### Vì sao @PreDestroy không chạy ở stop?

`@PreDestroy` là callback **destruction** của bean, không phải stop của `Lifecycle`. `stop()` không hủy bean nên không gọi callback này. Spring vẫn giữ bean để có thể start lại.

Nếu bean đóng client trong `@PreDestroy`, điều đó phù hợp khi context kết thúc vòng đời; nhưng không tự làm client “tạm ngưng” mỗi khi context.stop(). Nếu nghiệp vụ muốn pause client/worker, cần API stop riêng.

### Vì sao close gọi cả stop và destroy?

Vì hai việc có mục đích khác nhau:
1. **Dừng hoạt động:** ngừng nhận work mới, chờ in-flight work hoặc release subscription.
2. **Giải phóng sở hữu:** đóng pool/client/file/socket, hủy singleton và kết thúc context.

Một consumer SmartLifecycle có thể dùng DataSource chung. Trong shutdown chuẩn, consumer cần ngừng hoạt động trước khi DataSource bị destroy. Spring phối hợp theo lifecycle phase và dependency; vẫn phải kiểm tra thực tế với các resource bất đồng bộ.

### Giới hạn singleton/prototype

Spring quản lý destruction của singleton thuộc container. Với prototype bean đã tạo rồi bàn giao, container không tự gọi destroy callback của từng prototype. Vì thế ngay cả `context.close()` cũng **không phải cơ chế đảm bảo cleanup của mọi prototype**. Owner của prototype resource vẫn phải dọn theo contract.

## 15. Lỗi hiểu sai thường gặp

**Sai 1 — “context.stop() đóng toàn bộ Spring Boot app.”** Không. Nó dừng Lifecycle beans, nhưng context và nhiều singleton vẫn tồn tại.

**Sai 2 — “context.stop() tự gọi @PreDestroy.”** Không. `@PreDestroy` thuộc bean destruction, thường xảy ra khi close.

**Sai 3 — “context.close() chỉ là stop mạnh hơn một chút, có thể start lại.”** Không. Đó là ranh giới kết thúc vòng đời context.

**Sai 4 — “close sẽ phát ContextStoppedEvent.”** Không mặc định. Close có `ContextClosedEvent`; lifecycle stop diễn ra bên trong đường close nhưng không đồng nhất với lệnh stop tường minh.

**Sai 5 — “ContextClosedEvent đến sau khi mọi resource đã close.”** Không. Event đến sớm, trước destroy singleton trong đường close chuẩn.

**Sai 6 — “ContextStartedEvent và ApplicationStartedEvent giống nhau.”** Không. Một cái từ `context.start()` của Framework, cái kia trong `SpringApplication.run` của Boot.

**Sai 7 — “context.start() chạy lại @PostConstruct và ApplicationRunner.”** Không. Start chỉ điều phối lifecycle beans, không refresh container hay gọi runner lần nữa.

**Sai 8 — “isActive() phải false sau stop().”** Không. Active nói về context còn sống, không nói lifecycle component có running không.

**Sai 9 — “isRunning() của context chứng minh mọi request và background job an toàn.”** Không. Nó chỉ là trạng thái lifecycle processor; thread ngoài framework hoặc workload async cần contract riêng.

**Sai 10 — “stop() đủ để Kubernetes ngừng gửi request.”** Không có đảm bảo đó; cần readiness probe và routing orchestration đúng.

**Sai 11 — “Đã close context tức JVM chắc chắn thoát.”** Không. Thread không daemon, context khác hoặc tài nguyên ngoài Spring vẫn có thể giữ process sống.

**Sai 12 — “Đã close context là mọi prototype được @PreDestroy.”** Không. Spring không tự destroy từng prototype đã bàn giao.

**Sai 13 — “Một SmartLifecycle phải có isAutoStartup=true để context.start() chạy nó.”** Không. isAutoStartup quyết định auto-start lúc refresh; explicit start có thể khởi động lifecycle component.

**Sai 14 — “Stop một lần rồi start lại luôn thành công với mọi resource.”** Không. Một thư viện có thể không cho restart sau khi client nội bộ đã đóng; cần generation mới hoặc policy rõ.

**Sai 15 — “Close context con luôn đóng context cha.”** Không. Parent có vòng đời độc lập, cần tránh đóng nhầm resource dùng chung.

## 16. Cách kiểm chứng trong ứng dụng thật

### 16.1. Tách log theo ba thứ

Khi debug nên log riêng:

~~~text
eventType      = ContextStoppedEvent / ContextClosedEvent / ContextStartedEvent
contextId      = event.getApplicationContext().getId()
contextActive  = context.isActive()
workerRunning  = worker.isRunning()
resourceClosed = resource.isClosed()
~~~

Đây là **khung dữ liệu minh họa**, không phải log tự động của Spring. Nếu có nhiều context, đừng suy từ một event ở child rằng parent đã đóng.

### 16.2. Đo shutdown thực tế

Với worker có in-flight tasks, nên đo:
- Lúc bắt đầu từ chối work mới.
- Số task còn xử lý.
- Thời gian chờ trong `SmartLifecycle.stop(Runnable)`.
- Lúc resource owner đóng pool/client.
- Timeout phase và callback dừng thực sự.
- Lúc context.close() trả về.

Nếu Spring chờ timeout, kiểm tra callback stop có được gọi sau khi resource hoàn tất không. Nếu stop báo done quá sớm, kiểm tra task executor còn thread sống sau close.

### 16.3. Test độc lập stop, start, close

Trên một test context tự tạo, có thể đặt những assertion:

~~~text
sau run():       isActive = true, workerRunning = true
sau stop():      isActive = true, workerRunning = false
                resourceDestroyed = false
sau start():     isActive = true, workerRunning = true
                resourceDestroyed = false
sau close():     isActive = false, workerRunning = false
                resourceDestroyed = true
~~~

Đó là expected behavior của một resource/worker được thiết kế như demo, không phải kết luận tuyệt đối cho mọi Spring bean.

### 16.4. Kiểm tra call counts

Một bean ManagedWorker nên có count:
- Auto-start trong refresh: 1.
- Stop tường minh: 1.
- Start lại: 2.
- Close context khi đang chạy: stop lần hai.

ApplicationRunner count chỉ bằng **một** vì không được gọi lại khi `context.start()`. Destroy method của singleton được gọi khi close, không chạy ở stop.

### 16.5. Test lỗi và shutdown bất thường

Kiểm thử thêm:
- Stop khi bean đã STOPPED: no-op và callback hợp lệ.
- Stop bất đồng bộ timeout: lifecycle processor đợi theo cấu hình, không treo vô hạn.
- Start khi resource đã bị destroy: phải fail rõ, không tạo trạng thái chạy giả.
- Close khi startup thất bại giữa chừng: có thể chỉ một phần bean tồn tại; không giả định event/stop đi theo happy path.
- SIGKILL: cleanup có thể không chạy; kiểm chứng cơ chế recovery ngoài JVM.
- Nhiều context: close child không đóng parent-owned resource.
- Web server: kiểm tra readiness và request in-flight, không chỉ trạng thái lifecycle.

## 17. Tình huống chọn stop hay close

### Tình huống A — Tạm dừng một message consumer

**Yêu cầu:** ngừng tiêu thụ message một lúc, rồi tiếp tục.

Nên điều khiển lifecycle của **message listener container/consumer cụ thể** nếu API hỗ trợ stop/start, tránh dừng toàn ApplicationContext. Nếu consumer là SmartLifecycle độc lập, có thể gọi `consumer.stop()` rồi `consumer.start()` theo contract, đồng thời giữ DB pool và HTTP API quản trị còn sống.

Dùng `context.stop()` chỉ khi bạn thực sự muốn dừng **toàn bộ** các lifecycle bean thuộc context và đã kiểm tra ảnh hưởng đến web server, scheduler và dependency.

### Tình huống B — Hoàn tất batch CLI rồi thoát

**Yêu cầu:** chạy job, sau đó đóng mọi resource ứng dụng.

Dùng try-with-resources trên `ConfigurableApplicationContext` hoặc `SpringApplication.exit(context)` theo hợp đồng. `context.stop()` đơn lẻ có thể để lại datasource, HTTP client và các singleton cần destroy.

### Tình huống C — Rolling deployment trên Kubernetes

**Yêu cầu:** không nhận request mới, cho request cũ hoàn thành rồi kết thúc pod.

Dùng readiness, graceful shutdown của web server, termination grace period và context close theo trình tự vận hành. Không dùng `context.stop()` như cách duy nhất để báo “pod unready”.

### Tình huống D — Tạm dừng background processing để bảo trì

**Yêu cầu:** dừng worker, nhưng các API truy vấn trạng thái vẫn chạy.

Dừng **bean worker** thay vì context, có policy cho start lại. Nếu dừng context, một số lifecycle bean khác có thể cũng stop, gây gián đoạn ngoài ý định.

### Tình huống E — Integration test tạo context thủ công

**Yêu cầu:** kiểm tra shutdown của bean.

`context.stop()` phù hợp để kiểm tra Lifecycle contract; `context.close()` để kiểm tra destroy callback và đảm bảo giải phóng context. Khi Spring TestContext sở hữu context cache, đừng tự đóng context trong mỗi test nếu framework cần dùng lại; dùng cơ chế test lifecycle được hỗ trợ.

### Tình huống F — Ứng dụng có parent/child contexts

**Yêu cầu:** tháo một module child mà không dừng tài nguyên parent dùng chung.

Dùng child.close() để giải phóng các bean thuộc child theo contract; không tự close parent pool. Nếu chỉ muốn pause lifecycle của module, child.stop() có thể phù hợp hơn nhưng cần kiểm tra dependency và bean nào thực sự được dừng.

## 18. Câu hỏi tự đánh giá

**Câu 1:** `context.stop()` có destroy singleton beans không?

**Trả lời:** Không. Nó phát tín hiệu dừng lifecycle, nhưng bean factory và singleton vẫn tồn tại.

**Câu 2:** Tại sao `context.isActive()` vẫn true sau stop()?

**Trả lời:** Vì stop không đóng context. isActive phản ánh context còn tồn tại sau refresh, không phải toàn bộ worker đang running.

**Câu 3:** `context.start()` sau stop có chạy lại `ApplicationRunner.run()`?

**Trả lời:** Không. Runner là một bước trong `SpringApplication.run`, không phải callback thuộc `LifecycleProcessor.start()`.

**Câu 4:** Event nào gắn với `context.start()`?

**Trả lời:** `ContextStartedEvent` của Spring Framework; không phải `ApplicationStartedEvent` của Spring Boot.

**Câu 5:** Event nào gắn với `context.close()`?

**Trả lời:** `ContextClosedEvent`. Nó được phát khi bắt đầu đóng, trước destroy singleton trong đường close thông thường.

**Câu 6:** Nếu gọi close khi worker đang chạy, có cần stop() trước không?

**Trả lời:** Không bắt buộc. Close đã điều phối lifecycle stop, nhưng nếu cần drain dài/tách giai đoạn, có thể điều phối sớm ở cấp component.

**Câu 7:** Vì sao không được gọi start sau close?

**Trả lời:** Context đã kết thúc vòng đời và bean factory/singleton có thể đã bị hủy; để khởi động lại ứng dụng cần tạo context mới.

**Câu 8:** Một bean không implement Lifecycle có tự stop khi context.stop() không?

**Trả lời:** Không tự động chỉ vì lệnh stop. Nó cần tham gia lifecycle hoặc được một component khác điều khiển.

**Câu 9:** `@PreDestroy` chạy khi stop hay close?

**Trả lời:** Destruction callback chạy khi bean được hủy, điển hình trong close context, không phải stop đơn thuần.

**Câu 10:** Context đã đóng thì JVM có chắc thoát không?

**Trả lời:** Không. Những non-daemon thread hoặc context khác có thể còn sống; `close()` không giống `System.exit`.

**Câu 11:** Gọi close có chắc nhận thêm ContextStoppedEvent không?

**Trả lời:** Không. Close dùng sự kiện ContextClosedEvent; lifecycle stop được thực hiện qua processor mà không cần một lần gọi stop() tường minh.

**Câu 12:** `isAutoStartup() == false` nghĩa là explicit context.start không chạy bean?

**Trả lời:** Không. Thuộc tính đó điều khiển auto-start khi refresh; explicit start có thể kích hoạt Lifecycle bean.

**Câu 13:** Tại sao `ContextClosedEvent` listener vẫn thấy worker running?

**Trả lời:** Vì event được phát trước lifecycle stop và singleton destruction trong đường đóng chuẩn.

**Câu 14:** Một prototype bean có chắc được destroy khi close không?

**Trả lời:** Không. Spring không tự quản lý destruction của prototype sau khi bàn giao; caller phải chịu trách nhiệm cleanup.

**Câu 15:** Dừng một consumer nhưng giữ API hoạt động nên làm gì?

**Trả lời:** Ưu tiên điều khiển lifecycle của consumer cụ thể, thay vì stop toàn context.

## 19. Bài tập thực hành

### Bài tập 1 — Chạy demo và kiểm chứng bảng so sánh

Chạy mã mục 7, đánh dấu:
- Mốc `context.stop()` và `ContextStoppedEvent`.
- Mốc `context.start()` và `ContextStartedEvent`.
- Mốc `ContextClosedEvent`, `WORKER_STOP` cuối và `RESOURCE_DESTROYED`.
- Giá trị `active/running/destroyed` sau mỗi thao tác.

Giải thích tại sao destroy chỉ xuất hiện khi context close, không xuất hiện khi stop.

### Bài tập 2 — Đổi isAutoStartup

Thay `TrackedWorker.isAutoStartup()` thành false. Dự đoán `worker.isRunning()` trong runner; tiếp đó thử gọi `context.start()` và kiểm tra worker có bắt đầu chạy không. Khi đổi, các dòng marker/expected stdout của ví dụ gốc sẽ khác, hãy ghi lại và giải thích.

### Bài tập 3 — Gọi stop hai lần

Trong `main`, thêm `context.stop()` lần thứ hai trước start. Kiểm tra worker không giải phóng resource trùng. Quan sát xem sự kiện ContextStoppedEvent có được công bố thêm lần nữa theo implementation context đang dùng không, phân biệt số event với số lượt resource stop thật.

### Bài tập 4 — Thêm bean chỉ có @PreDestroy

Tạo singleton `AuditSink` có `@PreDestroy` (Boot 3 dùng `jakarta.annotation.PreDestroy`). Log khi destroy. Kiểm tra stop không chạy callback hủy của bean thường, còn close có chạy.

### Bài tập 5 — Phân biệt với SpringApplication events

Đếm số lần `ApplicationStartedEvent`, `ApplicationReadyEvent` và `ContextStartedEvent`. Sau chuỗi stop → start, các event Boot có lặp lại không? Giải thích vì sao.

### Bài tập 6 — Quan sát parent/child

Tạo parent context giữ một resource và child context giữ consumer. Đóng child, xác minh resource parent vẫn chưa bị destroy. Khi đóng parent sau đó, mới giải phóng resource thuộc parent.

### Bài tập 7 — Thiết kế graceful stop

Thay worker in-memory bằng executor có in-flight task; triển khai `SmartLifecycle.stop(Runnable)` chỉ gọi callback khi task đã hoàn tất, có timeout. Kiểm chứng khi context.close() Spring đợi phase và đóng resource sau bước stop. Không đưa sleep giả vào production.

### Bài tập 8 — Kiểm tra readiness

Trong một web app có Actuator, so sánh `ApplicationAvailability`, `/actuator/health/readiness` và trạng thái `context.isRunning()` trước/sau một lời gọi stop được điều phối. Không suy đoán readiness từ stop: hãy đọc trạng thái thực, ghi nhận những bean/web server bị ảnh hưởng và chọn component-level stop nếu cần duy trì API.

## 20. Tài liệu chính thức

Tài liệu dưới đây dùng để kiểm tra hợp đồng của Spring Framework/Spring Boot. Đối với dependency khác version, hãy đối chiếu cùng nhánh thực tế:

- [Spring Framework 6.2 — Các sự kiện chuẩn của ApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): định nghĩa `ContextStartedEvent`, `ContextStoppedEvent`, `ContextClosedEvent` và khả năng restart một stopped context.
- [Spring Framework 6.2 — Lifecycle và shutdown callback](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): `Lifecycle`, `SmartLifecycle`, `LifecycleProcessor`, auto-start và destroy.
- [Spring Framework — ConfigurableApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): `start`, `stop`, `close`, `isActive` và chú ý vòng đời.
- [Spring Framework — AbstractApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `doClose`, `destroyBeans`, context lifecycle và event.
- [Spring Framework — DefaultLifecycleProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): điều phối phase của Lifecycle beans, start và stop.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): ApplicationStartedEvent, ApplicationReadyEvent, runners và availability.
- [Spring Boot 3.5 — Graceful shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): shutdown trong đường close context và timeout theo phase.
- [Spring Boot 3.5.16 được phát hành](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/): xác nhận version demo.

## 21. Checklist và tổng kết

Trước khi quyết định gọi `stop()` hay `close()`, hãy tự hỏi:

1. Tôi muốn **tạm dừng** hay **kết thúc hẳn** runtime?
2. Có cần **restart cùng bean/context** hay không?
3. Bean nào implement `Lifecycle`/`SmartLifecycle`, bean nào chỉ có destroy callback?
4. Nếu stop toàn context, HTTP server/scheduler/consumer nào có thể bị ảnh hưởng?
5. Resource nào phải **giữ sống** trong lúc tạm dừng, resource nào cần đóng khi kết thúc?
6. Có in-flight tasks cần graceful drain và callback dừng không?
7. Có readiness routing từ Kubernetes/load balancer cần điều phối riêng không?
8. Listener đang lắng nghe đúng `ContextStoppedEvent` hay `ContextClosedEvent`?
9. Context có parent/child không, ai sở hữu tài nguyên chia sẻ?
10. Có cơ chế xử lý startup error, forced shutdown và timeout không?

**Ghi nhớ cuối cùng:**

- `context.stop()` chỉ dừng lifecycle components, **không destroy singleton** và **không làm context hết active**.
- `context.start()` sau stop có thể start lại những component hỗ trợ restart, **không refresh container**, không chạy lại runners hoặc Spring Boot Ready event.
- `context.close()` là kết thúc vòng đời: phát `ContextClosedEvent`, dừng Lifecycle beans, **hủy singleton**, đóng BeanFactory/context.
- `ContextStoppedEvent`, `ContextStartedEvent` là event Framework của lệnh stop/start tường minh; khác `ApplicationStartedEvent` và `ApplicationReadyEvent` của Boot.
- `ContextClosedEvent` xuất hiện **trước** các destruction callback; không suy ra mọi resource đã đóng ngay trong event listener.
- Tạm dừng một workload nên cân nhắc điều khiển **bean cụ thể**; kết thúc ứng dụng nên dùng close/graceful shutdown đúng chuẩn.
- `stop()` không đồng nghĩa readiness, `close()` không đồng nghĩa chắc chắn JVM đã thoát; phải thiết kế orchestration và resource ownership riêng.
