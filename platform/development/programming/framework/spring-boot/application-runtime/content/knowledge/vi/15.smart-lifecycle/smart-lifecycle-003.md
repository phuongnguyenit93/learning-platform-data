# SmartLifecycle và cơ chế tự khởi động khi ApplicationContext refresh

**Module:** Spring Boot Application Runtime → **SmartLifecycle**. Bài học giải thích cách Spring Framework dùng `LifecycleProcessor` để tự động gọi `SmartLifecycle.start()` trong quá trình `ApplicationContext.refresh()`, khác biệt giữa khởi tạo bean và khởi chạy tài nguyên, quy tắc `isAutoStartup()`/`getPhase()`, việc dừng bằng `stop(Runnable)`, và cách kiểm tra thứ tự bằng ứng dụng Spring Boot thực thi được.

**Môi trường ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Spring MVC, Maven. Khi dùng Spring Boot 4.x hoặc Spring Framework 7, phải đối chiếu API và cấu hình theo phiên bản thực tế. Toàn bộ code minh họa lifecycle nằm trong một dự án chạy local; không mở consumer, broker hoặc tài nguyên sản xuất thật.

## 1. Mục tiêu học

Sau khi hoàn thành, người học có thể:

1. Phân biệt **bean đã được tạo**, **bean đã hoàn tất initialization**, **lifecycle component đang running** và **ứng dụng đã ready**.
2. Giải thích mối liên hệ `Lifecycle` → `SmartLifecycle` → `LifecycleProcessor` → `DefaultLifecycleProcessor`.
3. Chỉ ra callback `LifecycleProcessor.onRefresh()` xảy ra cuối quá trình refresh, **trước** `ContextRefreshedEvent`, và tự khởi động các `SmartLifecycle` đủ điều kiện.
4. Biết `SmartLifecycle.isAutoStartup()` mặc định trả **true**; `SmartLifecycle.getPhase()` mặc định trả **Integer.MAX_VALUE** trong Spring Framework 6.2.
5. Dự đoán thứ tự start theo phase **nhỏ trước**, stop **lớn trước**, cùng tác động của `depends-on`.
6. Implement đúng `start()`, `stop()`, `isRunning()` và `stop(Runnable callback)`; không làm mất callback shutdown.
7. Thấy một component `isAutoStartup=false` đã là bean nhưng chưa running sau refresh, và có thể start thủ công về sau.
8. Đọc log, HTTP trạng thái, stack trace startup failure và shutdown evidence.
9. Biết vì sao `@Lazy` không phải cơ chế đáng tin để ngăn auto-startup của `SmartLifecycle`.
10. Chọn đúng hook cho background worker: `@PostConstruct`, `SmartInitializingSingleton`, `SmartLifecycle`, runner và `ApplicationReadyEvent`.

**Ý chính:** `SmartLifecycle` được thiết kế cho một **thành phần Spring-managed có vòng đời start/stop**, nhất là consumer, scheduler, listener, connector hoặc worker. `isAutoStartup()=true` khiến Spring cố khởi chạy component tại context refresh; nó **không** có nghĩa constructor được gọi lần nữa, không cần gọi `SpringApplication.run()` lần hai, và không đồng nghĩa mọi dependency bên ngoài đã khỏe.

## 2. Hợp đồng API: Lifecycle và SmartLifecycle

### 2.1. Lifecycle cơ bản

Spring Framework cung cấp:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Đây là biểu diễn **rút gọn hợp đồng interface** trong tài liệu, không phải file source để thêm vào project. Bean implement `Lifecycle` có thể tham gia các lệnh start/stop khi context được yêu cầu start/stop. Nhưng một `Lifecycle` thông thường **không tự khởi động chỉ vì context vừa refresh** theo mặc định. Muốn Spring tự bắt đầu component trong pha refresh, dùng `SmartLifecycle`.

### 2.2. SmartLifecycle

`org.springframework.context.SmartLifecycle` mở rộng `Lifecycle` và `Phased`. Các method quan trọng:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
    int getPhase();
}
~~~

Đây cũng là **biểu diễn tài liệu**, không nên chép thành interface trùng tên của framework. Trong Spring Framework 6.2, `SmartLifecycle` đã có default methods cho `isAutoStartup()`, `getPhase()` và `stop(Runnable)`. Bạn vẫn phải triển khai `start()`, `stop()` và `isRunning()` do `Lifecycle` yêu cầu.

Bảng hợp đồng:

| API | Ý nghĩa | Hành vi cần lưu ý |
|---|---|---|
| `start()` | Bắt đầu tài nguyên/process của component | Nên idempotent, không mở trùng worker |
| `stop()` | Dừng component (đường gọi trực tiếp) | Có thể dùng khi vận hành/manual stop |
| `isRunning()` | Trả trạng thái running hiện hành | Phải phản ánh việc start/stop, không chỉ bean tồn tại |
| `isAutoStartup()` | Cho phép tự start khi context refresh | Default **true** cho `SmartLifecycle` |
| `getPhase()` | Ưu tiên theo phase | Default **Integer.MAX_VALUE**; phase thấp start trước |
| `stop(Runnable)` | Dừng dưới sự điều phối của lifecycle processor | **Phải gọi `callback.run()` sau khi dừng xong** |

**Điểm đặc biệt:** Khi đóng context, `DefaultLifecycleProcessor` sử dụng `stop(Runnable)` cho `SmartLifecycle`; đừng chỉ override `stop()` rồi giả định processor nhất định gọi nó nếu bạn đã override `stop(Runnable)` nhưng quên delegate. Default implementation của `stop(Runnable)` có thể gọi `stop()` rồi callback, nhưng khi shutdown bất đồng bộ cần tự cài đặt đúng.

### 2.3. LifecycleProcessor là ai?

`org.springframework.context.LifecycleProcessor` mở rộng `Lifecycle` và thêm hai method:

~~~java
public interface LifecycleProcessor extends Lifecycle {
    void onRefresh();
    void onClose();
}
~~~

Framework cung cấp implementation `DefaultLifecycleProcessor` để điều phối các bean lifecycle. Một context chuẩn tạo/dùng processor thích hợp trong quá trình refresh. `onRefresh()` cho component được tự start; `onClose()` điều phối dừng khi context đóng. Cùng processor này cũng cung cấp xử lý khi `ConfigurableApplicationContext.start()` hoặc `stop()` được gọi trực tiếp.

Trong app Spring Boot bình thường, **không cần tự cài `LifecycleProcessor`**, không cần tự gọi `onRefresh()` và không cần gọi `start()` của mọi auto-start component từ `main()`.

## 3. SmartLifecycle tự khởi động vào thời điểm nào?

Chuỗi chính của Spring Boot với một web context:

~~~text
main(args)
  |
  v
SpringApplication.run(args)
  |
  +-- chuẩn bị Environment và ApplicationContext
  +-- nạp bean definitions
  +-- ApplicationContext.refresh()
  |    |
  |    +-- BeanFactoryPostProcessor/BeanPostProcessor
  |    +-- tạo các singleton không lazy
  |    |    +-- constructor, inject dependencies
  |    |    +-- @PostConstruct / init methods
  |    |
  |    +-- finishRefresh()
  |         |
  |         +-- LifecycleProcessor.onRefresh()
  |         |    +-- tìm lifecycle beans
  |         |    +-- auto-start SmartLifecycle theo phase
  |         |    +-- gọi start() cho bean đủ điều kiện
  |         |
  |         +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent
  +-- các ApplicationRunner/CommandLineRunner
  +-- ApplicationReadyEvent
  +-- trạng thái readiness chuyển ACCEPTING_TRAFFIC
  v
ứng dụng hoạt động
~~~

**Thời điểm then chốt:** Khi `DefaultLifecycleProcessor.onRefresh()` được thực thi, giai đoạn pre-instantiation singleton thông thường đã hoàn tất. Processor tự khởi động các `SmartLifecycle` có `isAutoStartup()` trả true (và xử lý dependencies liên quan). Đối với một context được refresh thành công, các callback `start()` đồng bộ trong ví dụ hoàn tất **trước** `ContextRefreshedEvent`. Mốc startup của Boot như `ApplicationStartedEvent` và runner đến sau.

Đừng nhầm:

- **Constructor chạy** ⇒ object tồn tại; chưa chắc worker đã hoạt động.
- **`@PostConstruct` chạy** ⇒ bean hoàn tất khâu init của chính mình; chưa chắc `start()` được gọi.
- **`start()` đã chạy** ⇒ lifecycle component được yêu cầu khởi chạy và thường trở thành running; chưa chắc toàn application ready.
- **`ContextRefreshedEvent` đến** ⇒ refresh hoàn thành; còn Boot runners và ready.
- **`ApplicationReadyEvent` đến** ⇒ Boot đã đi đến mốc ready; trạng thái readiness được công bố sau mốc này trong luồng chuẩn.

Đối với ứng dụng có bean lazy, nhiều context, cơ chế asynchronous startup tùy chỉnh hoặc dependency đặc thù, thời điểm một số bean được tạo có thể khác; nên tin vào hợp đồng callback và log trực tiếp, không suy từ thứ tự scan class.

## 4. isAutoStartup(): điều kiện tự start, không phải điều kiện tạo bean

`isAutoStartup()` cho biết Spring nên tự gọi `start()` của component ở phase refresh hay không.

| Tình huống | Bean có thể đã được tạo? | Auto start tại refresh? |
|---|---|---|
| `SmartLifecycle`, mặc định `isAutoStartup()=true` | Có | Có |
| `SmartLifecycle` override `isAutoStartup()=false` | Có | Không tự start nếu độc lập, không bị dependency lifecycle khác đòi start |
| `Lifecycle` thường, không phải Smart | Có | Không theo quy tắc auto startup của Smart |
| `SmartLifecycle` được gọi `start()` thủ công sau refresh | Có | Manual start, không phải auto-start |
| Bean không đăng ký vào Spring container | Có thể do `new` bên ngoài | Không do `LifecycleProcessor` quản lý |
| Singleton `@Lazy` implement `SmartLifecycle` | Có thể vẫn bị tạo trong lúc lifecycle discovery | Không nên dùng lazy làm công tắc tắt auto-startup |

Quan trọng: `isAutoStartup=false` không phải “không thể chạy”. Nó chỉ ngăn tự khởi động trong lượt refresh. Một lời gọi `start()` trực tiếp, `context.start()` hay sự phụ thuộc lifecycle theo cơ chế processor vẫn có thể khiến component running, tùy cấu hình. Tương tự, `isAutoStartup=true` không bảo đảm container gọi `start()` nhiều lần mỗi khi ai đọc bean; nó là quyết định của processor tại pha lifecycle phù hợp.

**Cảnh báo về @Lazy:** Javadoc `SmartLifecycle` chỉ rõ lazy-init flag **có ảnh hưởng rất hạn chế** vì lifecycle processor có thể chủ động tạo bean để phát hiện/tự khởi chạy. Nếu một consumer cần tắt theo cấu hình, dùng `isAutoStartup()` hoặc `@ConditionalOnProperty` hợp lý; đừng chỉ đánh dấu `@Lazy` rồi kỳ vọng nó không khởi động.

## 5. Phase quyết định thứ tự start/stop

`SmartLifecycle` đồng thời là `Phased`: `getPhase()` trả một số nguyên biểu thị phase. Các phase được sắp xếp:

- **Khi start:** phase **nhỏ hơn** trước, phase **lớn hơn** sau.
- **Khi stop:** thứ tự **đảo ngược**, phase **lớn hơn** trước, phase **nhỏ hơn** sau.
- Phase âm thường cho hạ tầng nên mở sớm và đóng muộn; phase dương thường dành cho những thành phần dựa vào hạ tầng.
- Default của **`SmartLifecycle` là `Integer.MAX_VALUE`**, trong khi các bean implement **`Lifecycle` thông thường** được processor coi có phase **0** nếu không có cách biểu diễn phase riêng.
- Có thể lấy giá trị từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE`; không tự chọn phase cực trị nếu có các web/server/infrastructure components khác cần thứ tự riêng.

Ví dụ hai component độc lập, `foundation` pha -100 và `consumer` pha +100:

~~~text
Refresh:
LAB_START foundation phase=-100
LAB_START consumer phase=100

Shutdown:
LAB_STOP consumer phase=100
LAB_STOP foundation phase=-100
~~~

Thứ tự chính xác giữa **hai bean cùng phase** không nên được dùng làm cam kết nghiệp vụ; nếu chúng phụ thuộc nhau, biểu đạt dependency rõ ràng. Spring cũng tôn trọng **depends-on**: bean phụ thuộc sẽ được start **sau** dependency và stop **trước** dependency, kể cả khi phải xét thêm phase ordering. Không dùng phase để thay thế mọi dependency thực trong hệ thống.

**Cẩn thận với giá trị mặc định:** Nếu để `SmartLifecycle.getPhase()` mặc định là `Integer.MAX_VALUE`, bean có xu hướng khởi động rất muộn và dừng rất sớm so với phase 0. Trong một app web, Spring Boot còn có web server và infrastructure lifecycle components có phase riêng. Đừng kết luận app listener sẽ luôn start trước server chỉ vì nó implement `SmartLifecycle`; cần xem phase thực tế từng component.

## 6. Project hoàn chỉnh Java 17 / Spring Boot 3.5

### 6.1. Tạo bằng Spring Initializr

Tạo Maven project:

- Group: `com.example`
- Artifact: `smart-lifecycle-lab`
- Package: `com.example.smartlifecycle`
- Java: **17**
- Spring Boot: **3.5.x**
- Dependencies: **Spring Web**
- Packaging: **Jar**

Giữ `pom.xml`, Maven Wrapper và versions từ Spring Initializr. Tạo các file:

~~~text
smart-lifecycle-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/smartlifecycle/
    SmartLifecycleLabApplication.java
    DemoLifecycle.java
    LifecycleConfiguration.java
    LifecycleController.java
  src/main/resources/application.properties
~~~

Mỗi `public class` phải ở file trùng tên, cùng package. Khi biên dịch dùng `./mvnw`/`./mvnw.cmd` với dependencies từ Maven; gọi `javac` từng file khi chưa có Spring classpath sẽ thất bại. Cả bốn file Java ở dưới là **mã đầy đủ**, không phải pseudocode.

### 6.2. Main class: đối chiếu event với start()

File `src/main/java/com/example/smartlifecycle/SmartLifecycleLabApplication.java`:

~~~java
package com.example.smartlifecycle;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class SmartLifecycleLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SmartLifecycleLabApplication.class, args);
    }

    @Bean
    ApplicationRunner markerRunner() {
        return args -> System.out.println("LAB_RUNNER_DONE");
    }

    @EventListener(ContextRefreshedEvent.class)
    public void contextRefreshed() {
        System.out.println("LAB_CONTEXT_REFRESHED");
    }

    @EventListener(ApplicationStartedEvent.class)
    public void started() {
        System.out.println("LAB_APPLICATION_STARTED");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void ready() {
        System.out.println("LAB_APPLICATION_READY");
    }
}
~~~

`@EventListener` methods được Spring phát hiện vì main class đồng thời là configuration bean do `@SpringBootApplication`. Chúng chỉ in mốc, không điều khiển start. Runner được Boot gọi sau khi context refresh thành công; nếu một `SmartLifecycle.start()` ném lỗi trong refresh, runner và ready event không đến được ở luồng mặc định.

### 6.3. DemoLifecycle: implement đầy đủ và an toàn cho lab

File `src/main/java/com/example/smartlifecycle/DemoLifecycle.java`:

~~~java
package com.example.smartlifecycle;

import java.util.concurrent.atomic.AtomicBoolean;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.context.SmartLifecycle;

public final class DemoLifecycle implements SmartLifecycle {

    private final String name;
    private final int phase;
    private final boolean autoStartup;
    private final boolean failOnStart;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public DemoLifecycle(
            String name,
            int phase,
            boolean autoStartup,
            boolean failOnStart) {
        this.name = name;
        this.phase = phase;
        this.autoStartup = autoStartup;
        this.failOnStart = failOnStart;
        System.out.println("LAB_CONSTRUCT " + name);
    }

    @PostConstruct
    public void initialize() {
        System.out.println("LAB_POST_CONSTRUCT " + name);
    }

    @Override
    public boolean isAutoStartup() {
        return autoStartup;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public void start() {
        if (running.get()) {
            return;
        }

        if (failOnStart) {
            System.out.println("LAB_START_FAILURE " + name);
            throw new IllegalStateException(
                    "LAB_INTENTIONAL_START_FAILURE_" + name);
        }

        if (running.compareAndSet(false, true)) {
            System.out.println("LAB_START " + name
                    + " phase=" + phase);
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("LAB_STOP " + name
                    + " phase=" + phase);
        }
    }

    @Override
    public void stop(Runnable callback) {
        // Demo dung tai nguyen dong bo, khong co I/O async.
        stop();
        callback.run();
    }

    @PreDestroy
    public void destroy() {
        System.out.println("LAB_PRE_DESTROY " + name);
    }
}
~~~

**Giải thích theo dòng xử lý:**

1. Constructor và `@PostConstruct` cho biết bean **đã được tạo/khởi tạo**, không cho biết nó đã running.
2. `isAutoStartup()` trả giá trị riêng từng bean, có thể dùng false để component do người vận hành start thủ công.
3. `getPhase()` trả phase để processor sắp xếp.
4. `AtomicBoolean.compareAndSet(...)` giúp demo không in `LAB_START` lần hai khi start lặp trên cùng instance. Đây chỉ là guard trong JVM, không thay thế kiểm soát consumer ngoài hoặc cluster.
5. `stop()` chuyển running về false và in marker. Nó chỉ làm việc nội bộ, **không có thao tác network/resource thật** nên xử lý đồng bộ là đủ.
6. `stop(Runnable callback)` gọi `stop()` rồi `callback.run()` **sau khi dừng xong**. Không quên callback, nếu không shutdown phase có thể chờ đến timeout.
7. `@PreDestroy` thuộc giai đoạn bean destruction, xảy ra sau lifecycle stop thông thường khi đóng context; nó **khác** `stop()`.
8. `failOnStart` tạo nhánh lỗi có chủ đích để quan sát startup failure; mặc định false.

**Giới hạn thực tế:** Phương thức start/stop trên chỉ đổi một flag, vì thế `isRunning()` phản ánh chính xác state của **demo**. Một connector thật chỉ nên báo running khi đã thực sự start thành công; nếu `start()` fire-and-forget một task bất đồng bộ, flag true ngay có thể là quá sớm. Hãy thiết kế lock, state transition, timeouts và failure handling theo tài nguyên thực tế.

### 6.4. Tạo 3 beans: hai auto, một manual

File `src/main/java/com/example/smartlifecycle/LifecycleConfiguration.java`:

~~~java
package com.example.smartlifecycle;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LifecycleConfiguration {

    @Bean("foundation")
    DemoLifecycle foundation(
            @Value("${lab.fail.foundation:false}") boolean fail) {
        return new DemoLifecycle(
                "foundation", -100, true, fail);
    }

    @Bean("consumer")
    DemoLifecycle consumer() {
        return new DemoLifecycle(
                "consumer", 100, true, false);
    }

    @Bean("manualJob")
    DemoLifecycle manualJob() {
        return new DemoLifecycle(
                "manualJob", 200, false, false);
    }
}
~~~

- `foundation`: auto-start, phase **-100**, chạy trước consumer.
- `consumer`: auto-start, phase **+100**, chạy sau foundation.
- `manualJob`: `isAutoStartup()=false`, phase **+200**, **được tạo bean nhưng không tự start** trong lượt refresh bình thường. Sau đó endpoint lab cho phép gọi thủ công.
- `lab.fail.foundation`: khi true làm `foundation.start()` ném lỗi trong refresh; phục vụ thí nghiệm, không phải cờ cho sản phẩm.
- Cả ba beans được quản lý bởi Spring. Vì các `@Bean` trả type `DemoLifecycle implements SmartLifecycle`, processor có đủ thông tin để đưa chúng vào lifecycle orchestration.

`@Configuration(proxyBeanMethods = false)` thích hợp vì ba factory methods không gọi lẫn nhau; Spring vẫn đăng ký các bean definitions thông thường.

### 6.5. Controller kiểm tra state và start/stop thủ công

File `src/main/java/com/example/smartlifecycle/LifecycleController.java`:

~~~java
package com.example.smartlifecycle;

import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LifecycleController {

    private final DemoLifecycle foundation;
    private final DemoLifecycle consumer;
    private final DemoLifecycle manualJob;

    public LifecycleController(
            @Qualifier("foundation") DemoLifecycle foundation,
            @Qualifier("consumer") DemoLifecycle consumer,
            @Qualifier("manualJob") DemoLifecycle manualJob) {
        this.foundation = foundation;
        this.consumer = consumer;
        this.manualJob = manualJob;
    }

    @GetMapping("/lab/lifecycle")
    public Map<String, State> status() {
        return Map.of(
                "foundation", snapshot(foundation),
                "consumer", snapshot(consumer),
                "manualJob", snapshot(manualJob));
    }

    @PostMapping("/lab/manual/start")
    public State startManual() {
        manualJob.start();
        return snapshot(manualJob);
    }

    @PostMapping("/lab/manual/stop")
    public State stopManual() {
        manualJob.stop();
        return snapshot(manualJob);
    }

    private static State snapshot(DemoLifecycle component) {
        return new State(
                component.isRunning(),
                component.isAutoStartup(),
                component.getPhase());
    }

    public record State(boolean running,
                        boolean autoStartup,
                        int phase) {
    }
}
~~~

Controller chỉ trả snapshot và start/stop **manualJob** để lab có bằng chứng. Hai auto-start beans không được expose endpoint tùy ý start/stop. `@Qualifier` làm rõ bean nào được inject vì có ba beans cùng type `DemoLifecycle`; nếu bỏ qualifier, Spring có thể không resolve được dependency một cách an toàn hoặc chọn dựa vào parameter name thay vì quy tắc rõ ràng.

**Không deploy public:** Endpoint POST cho phép tác động lifecycle; nếu giữ trong dự án thật phải có authentication, authorization, kiểm soát quyền vận hành và điều kiện concurrency. Bài học chỉ dùng local, không có các tài nguyên nhạy cảm.

### 6.6. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=smart-lifecycle-lab
server.address=127.0.0.1
server.port=8080
lab.fail.foundation=false
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

`server.address=127.0.0.1` chỉ để giới hạn lab tại localhost. Trong container/Kubernetes, network binding phải theo kiến trúc thực tế. `spring.lifecycle.timeout-per-shutdown-phase=20s` làm rõ budget theo phase lúc shutdown. Spring Boot 3.5 có graceful shutdown mặc định cho embedded web servers hỗ trợ; nếu dự án đã override `server.shutdown=immediate` hoặc dùng bản khác, hãy kiểm tra chính sách hiện hành.

## 7. Thí nghiệm A — Auto-start khi refresh

### 7.1. Chạy Maven Wrapper

Trên Linux/macOS, tại thư mục project:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

JDK phải là Java 17 hoặc phiên bản mà project đã cấu hình hợp lệ. Nếu cổng 8080 đang bị process khác sử dụng, dừng process cũ trước khi chạy, hoặc đổi `server.port` trong lab và cập nhật lệnh curl.

### 7.2. Quan sát log theo milestone

Một trình tự **rút gọn hợp lệ** của các marker:

~~~text
LAB_CONSTRUCT foundation
LAB_POST_CONSTRUCT foundation
LAB_CONSTRUCT consumer
LAB_POST_CONSTRUCT consumer
LAB_CONSTRUCT manualJob
LAB_POST_CONSTRUCT manualJob
LAB_START foundation phase=-100
LAB_START consumer phase=100
LAB_CONTEXT_REFRESHED
LAB_APPLICATION_STARTED
LAB_RUNNER_DONE
LAB_APPLICATION_READY
~~~

**Giới hạn của output:** Không bảo đảm các constructor/PostConstruct được in theo thứ tự đúng từng dòng như trên giữa ba bean độc lập; chúng có thể hoán đổi theo dependency graph và bean factory ordering. Các marker Spring/Tomcat khác còn xen vào. Điều **phải đúng trong lab với một refresh thành công**:

1. Cả ba bean được tạo và PostConstruct chạy ở giai đoạn bean initialization.
2. `LAB_START foundation` **trước** `LAB_START consumer` theo phase -100 và +100.
3. Cả hai marker start xuất hiện **trước `LAB_CONTEXT_REFRESHED`**.
4. `LAB_CONTEXT_REFRESHED` trước `LAB_APPLICATION_STARTED`, sau đó runner rồi ready.
5. **Không xuất hiện `LAB_START manualJob` trong startup** vì `isAutoStartup()=false` (và không có lifecycle bean khác phụ thuộc vào nó để auto-start).

Đây là bằng chứng phân biệt **đã tạo bean** với **đã start**: manualJob có constructor và init marker nhưng `isRunning()` vẫn false.

### 7.3. Kiểm chứng bằng HTTP

Mở terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/lab/lifecycle
~~~

Kỳ vọng HTTP 200 và JSON tương đương:

~~~json
{
  "foundation": {
    "running": true,
    "autoStartup": true,
    "phase": -100
  },
  "consumer": {
    "running": true,
    "autoStartup": true,
    "phase": 100
  },
  "manualJob": {
    "running": false,
    "autoStartup": false,
    "phase": 200
  }
}
~~~

Thứ tự các khóa Map/JSON không được coi là contract; chỉ so sánh đúng các fields. Controller trả kết quả khi Boot đã startup; nó là bằng chứng độc lập với log rằng hai beans đang running và bean manual chưa chạy.

Trên PowerShell, nếu `curl` là alias, dùng `curl.exe -i http://127.0.0.1:8080/lab/lifecycle` để có output curl chuẩn.

## 8. Thí nghiệm B — isAutoStartup=false không cấm start thủ công

Sau khi `GET /lab/lifecycle` cho thấy `manualJob.running=false`, gọi:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/manual/start
~~~

Kỳ vọng body tương đương:

~~~json
{"running":true,"autoStartup":false,"phase":200}
~~~

Console có:

~~~text
LAB_START manualJob phase=200
~~~

Đây là **lời gọi trực tiếp** `manualJob.start()` từ controller sau startup, không phải framework tự chạy thêm một lượt `LifecycleProcessor.onRefresh()`. Dòng `autoStartup=false` vẫn giữ nguyên vì property đó chỉ nói **có được auto-start lúc refresh hay không**; `isRunning()` giờ true vì đã start thủ công.

Gọi POST start lần thứ hai:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/manual/start
~~~

Với implementation dùng CAS trong lab, không xuất hiện marker `LAB_START manualJob` thêm lần nữa và response vẫn `running=true`. Đó là tính idempotent của `start()` do **chính ta thiết kế**, không phải lời đảm bảo rằng mọi third-party `SmartLifecycle` đều an toàn nếu gọi trùng.

Tiếp tục:

~~~bash
curl -i -X POST http://127.0.0.1:8080/lab/manual/stop
curl -i http://127.0.0.1:8080/lab/lifecycle
~~~

Kỳ vọng `manualJob.running=false` và log:

~~~text
LAB_STOP manualJob phase=200
~~~

Nếu muốn thấy manualJob được dừng tự động bởi lifecycle processor khi đóng context, hãy **start nó lần nữa rồi giữ running** đến lúc dừng app (phần kế tiếp). Một component autoStartup=false nhưng **đang running** vẫn thuộc tập lifecycle cần stop khi context đóng.

### 8.1. So sánh gọi start trực tiếp và context.start()

- `manualJob.start()` chỉ tác động một object do code gọi; không chạy tuần tự toàn bộ phases của context.
- `ConfigurableApplicationContext.start()` ủy quyền cho lifecycle processor điều phối **các lifecycle beans**; có thể bao gồm cả những bean không auto-start khi refresh. Cẩn thận vì đây là thao tác cấp context, không nên gọi từ một controller public.
- `LifecycleProcessor.onRefresh()` là callback đặc biệt của giai đoạn refresh; Spring tự gọi, không phải endpoint vận hành.
- `SpringApplication.run()` tạo/refresh context cho một lượt khởi động; **không** được gọi lại chỉ để start một job đang tạm dừng.

## 9. Thí nghiệm C — Stop theo phase và callback

Đảm bảo manualJob **đang running** bằng POST start, rồi dừng tiến trình ứng dụng bằng Ctrl+C trong terminal chạy JAR hoặc Spring Boot Maven plugin. Trên môi trường hỗ trợ, SIGTERM hợp lệ cũng kích hoạt shutdown hooks.

Kỳ vọng các marker stop quan trọng của ba bean:

~~~text
LAB_STOP manualJob phase=200
LAB_STOP consumer phase=100
LAB_STOP foundation phase=-100
~~~

Đây là **thứ tự tương đối theo phase giữa ba component trong lab**. Các event Spring/Boot và web server shutdown logs có thể xen kẽ; không dùng nguyên toàn bộ stdout làm phép so khớp byte-for-byte. `@PreDestroy` cho mỗi bean được gọi ở quá trình destruction sau lifecycle stop thông thường; thứ tự giữa các marker destroy riêng không nhất thiết trùng thứ tự phase.

Nếu manualJob đang **stopped** tại lúc context đóng, sẽ không có marker stop thứ hai cho nó; đó là kết quả đúng của `isRunning()`. Không khẳng định framework thiếu callback chỉ vì không nhìn thấy `LAB_STOP manualJob` khi nó chưa running.

### 9.1. Vì sao stop(Runnable callback) rất quan trọng?

Trong Spring Framework, `DefaultLifecycleProcessor` có thể dừng các beans trong cùng phase và chờ callback xác nhận khi từng bean hoàn tất. Với một task bất đồng bộ, `stop(Runnable)` cho phép process dừng asynchronous rồi báo đã xong:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            // Dung consumer, ngung nhan job moi,
            // xu ly in-flight work theo deadline.
            shutdownConsumerSynchronously();
        } finally {
            callback.run();
        }
    });
}
~~~

Đây là **snippet minh họa**, cần `executor` phù hợp và định nghĩa `shutdownConsumerSynchronously()`; không đặt trực tiếp vào project mẫu khi chưa có các tài nguyên đó. Callback được gọi trong `finally` khi công việc dừng đã được **thử hoàn tất hoặc thất bại**, tránh chặn lifecycle processor vô hạn do quên báo. Trong hệ thống production, cũng cần ghi nhận lỗi, trạng thái failed-to-stop và policy timeout; `callback.run()` không tự chứng minh đã giải phóng mọi resource.

**Lỗi rất nguy hiểm:** Implement `stop(Runnable)` nhưng chỉ gọi `stop()` rồi **quên `callback.run()`**. Processor sẽ tiếp tục đợi phase shutdown cho tới timeout. Điều này có thể khiến Pod chết do hết `terminationGracePeriodSeconds` dù nghiệp vụ đã dừng xong.

Không gọi callback **trước** khi hoàn tất shutdown thực sự; nếu callback đến sớm, Spring có thể dừng dependency khác trong lúc component còn xử lý in-flight messages.

### 9.2. Timeout shutdown phase

Spring Boot có property:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Timeout này giới hạn khoảng chờ **mỗi phase shutdown** trong quá trình lifecycle processing; không phải deadline toàn bộ container, không phải thời gian tối đa cho mỗi request, và không đồng nghĩa với Kubernetes `terminationGracePeriodSeconds`. Nếu có nhiều phase, tổng thời gian shutdown có thể dài hơn một phase timeout.

Spring Framework 6.2 cho phép `DefaultLifecycleProcessor` cấu hình timeout riêng cho những phase cụ thể. Trong lab không cần override processor; property Boot ở trên là đủ để thể hiện một cấu hình vận hành phổ biến. Với hệ thống thực, đo thời gian dừng consumer, commit offsets/acks, drain worker và graceful server trước khi chọn giá trị.

### 9.3. Tương tác với graceful shutdown web server

Trong Spring Boot 3.5, graceful shutdown được bật mặc định với các embedded web servers được hỗ trợ. Quá trình này xảy ra khi đóng context, ở phase sớm trong thứ tự stop (tương ứng phase cao), nhằm không nhận request mới trong khi cho in-flight requests kết thúc theo timeout. Vì vậy:

- Không dùng phase quá cao cho worker nếu kỳ vọng server vẫn còn nhận request trong suốt lúc stop.
- Không suy rằng `SmartLifecycle.stop()` của một bean tương đương `context.close()` hoặc tự chặn HTTP.
- Khi context shutdown, Spring điều phối web server và các lifecycle components theo phase/dependency.
- SIGKILL hoặc JVM `halt` không bảo đảm stop callback hay `@PreDestroy` được gọi.

## 10. Thí nghiệm D — Lỗi trong start() chặn refresh

Dừng app bình thường, đóng gói JAR:

~~~bash
./mvnw clean package
java -jar target/smart-lifecycle-lab-0.0.1-SNAPSHOT.jar --lab.fail.foundation=true
~~~

Windows dùng `./mvnw.cmd clean package` trước khi chạy. Tên JAR chỉ là tên mặc định nếu artifact/version khớp `smart-lifecycle-lab` và `0.0.1-SNAPSHOT`; nếu version khác, lấy tên thật trong thư mục `target/`.

Vì `foundation` có `isAutoStartup=true` và phase -100, `DefaultLifecycleProcessor.onRefresh()` sẽ gọi `foundation.start()` trong refresh. Khi `failOnStart=true`, console có marker:

~~~text
LAB_START_FAILURE foundation
~~~

Và stack trace chứa:

~~~text
LAB_INTENTIONAL_START_FAILURE_foundation
~~~

Kết quả dự kiến:

1. Ba bean có thể đã được tạo và chạy `@PostConstruct`, nhưng **không** có nghĩa context refresh thành công.
2. `foundation.start()` ném lỗi, startup thất bại tại pha lifecycle.
3. Không xuất hiện `LAB_CONTEXT_REFRESHED`, `LAB_APPLICATION_STARTED`, `LAB_RUNNER_DONE` hoặc `LAB_APPLICATION_READY` trong **lượt startup lỗi này**.
4. `LAB_START consumer` thường không xuất hiện vì phase trước đã thất bại; Spring có thể bắt đầu cleanup những thành phần đã tạo.
5. Process trả về exit status thất bại; không coi app đã ready dù log có một phần thông tin embedded server.

Đây không phải lỗi constructor hoặc `@PostConstruct`. Stack trace phải được đọc đến root cause trong `start()`. Đừng tự gán nguyên nhân cho port/network khi thông báo thực là marker fail chủ ý.

Để phục hồi, chạy lại **không truyền** `--lab.fail.foundation=true` hoặc truyền `--lab.fail.foundation=false`. Không bỏ `SmartLifecycle`, không ném exception ra ngoài tùy ý trong production nếu lỗi external là tạm thời và có policy degraded operation hợp lệ.

## 11. Chọn hook đúng mục đích

| Hook/API | Khi nào chạy | Hợp cho | Không hợp cho |
|---|---|---|---|
| Constructor | Khi Spring tạo object | Nhận dependency, thiết lập invariant | Start thread dùng lâu dài mà chưa có cơ chế stop |
| `@PostConstruct` | Khi **chính bean** đã được inject | Kiểm tra cấu hình nhẹ | Chạy task dài, mở subscriber cần dừng |
| `InitializingBean.afterPropertiesSet()` | Init callback riêng của bean | Setup phụ thuộc property của bean | Đợi toàn bộ singleton và web server ready |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Sau giai đoạn pre-instantiation singleton thường | Xây registry từ các singleton đã có | Quản lý cặp start/stop, stop callback |
| `SmartLifecycle.start()/stop(...)` | Khi LifecycleProcessor auto-start refresh hoặc được start/stop chủ động | Consumer, scheduler, worker, connector có vòng đời | Thay thế business request/transaction semantics |
| `ContextRefreshedEvent` | Sau lifecycle `onRefresh()` của context | Biết context đã refresh | Giả định runners đã hoàn tất |
| `ApplicationRunner` / `CommandLineRunner` | Sau refresh, trước ready | Tác vụ hậu context cần hoàn tất trước ready | Cặp start/stop dài hạn tự quản |
| `ApplicationReadyEvent` | Sau runners | Ghi nhận Boot hoàn tất startup | Khởi động công việc bắt buộc trước ready nhưng không có readiness policy |
| `@PreDestroy` | Khi bean bị destroy | Cleanup cuối, release resources | Điều phối phase shutdown chuyên nghiệp |

### 11.1. SmartLifecycle vs SmartInitializingSingleton

Hai interface thường bị nhầm vì đều bắt đầu bằng “Smart” và diễn ra quanh bootstrap:

- `SmartInitializingSingleton` có một method `afterSingletonsInstantiated()` sau singleton pre-instantiation; phù hợp validation/registry trong giai đoạn init.
- `SmartLifecycle` có `start()`, `stop()` và running state; được `LifecycleProcessor` quản lý khi refresh, context start/stop và close.
- `SmartInitializingSingleton` không có phase hay shutdown callback; `SmartLifecycle` hỗ trợ phase và bất đồng bộ stop.
- Nếu cần cả build registry lẫn consumer worker, có thể dùng các bean riêng để tách trách nhiệm hoặc kết hợp có kiểm soát, nhưng không cần implement tất cả interfaces cho một tác vụ nhỏ.

### 11.2. @Scheduled có giống SmartLifecycle không?

`@Scheduled` khai báo một tác vụ được kích hoạt theo lịch khi scheduling infrastructure được bật (ví dụ `@EnableScheduling`); nó không phải lời gọi `start()` tùy ý của một `SmartLifecycle` do bạn viết. Scheduler/task executor của Spring có lifecycle riêng và phase riêng. Nếu worker cần tạm dừng, drain, thay đổi kết nối hoặc phối hợp ngoại lệ, xem lifecycle của scheduler hoặc consumer đang dùng thay vì trộn thủ công nhiều mechanism không hiểu phase.

### 11.3. Consumer và message broker thật

Với RabbitMQ/Kafka/JMS, framework hoặc thư viện thường cung cấp listener container implement `SmartLifecycle` hoặc cơ chế tương đương. **Ưu tiên cấu hình chính container đó** (autoStartup, phase, concurrency, ack, pause/resume, shutdown timeout) thay vì tự viết một `SmartLifecycle` bọc lại rồi gọi start/stop của container lần nữa. Nếu cùng resource có hai owners, nguy cơ double start hoặc double stop tăng.

## 12. Mẫu vận hành production: thiết kế state machine rõ ràng

Một `SmartLifecycle` thật nên có các trạng thái phân biệt:

~~~text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                   |
                   +-> FAILED
~~~

`isRunning()` thường nên true khi thành phần đã bắt đầu thực sự có khả năng làm việc; nhưng semantics cụ thể phụ thuộc loại resource. Có một số nguyên tắc:

1. **start idempotent:** gọi lặp không spawn trùng thread/consumer; nếu đang STARTING, xử lý rõ chờ/ignore/error.
2. **stop idempotent:** gọi stop khi không running không làm phát sinh lỗi; dừng nhiều lần không double-close tài nguyên.
3. **Tránh deadlock:** không chặn start chờ một bean hoặc callback vốn chỉ hoạt động sau `ContextRefreshedEvent`. Vì start nằm **trước** event, chờ vô hạn sẽ treo refresh.
4. **Timeout:** mọi thao tác network có giới hạn thời gian, có chính sách retry; không giữ startup ở phase -100 vô thời hạn.
5. **Failure semantics:** nếu không thể start, quyết định throw để fail startup hay duy trì degraded mode theo chính sách readiness; không luôn báo running=true dù kết nối chưa có.
6. **Phụ thuộc:** start hạ tầng trước worker, stop worker trước hạ tầng; dùng phase và dependency rõ ràng.
7. **Resource cleanup:** stop phải ngừng nhận việc mới và xử lý/đánh dấu việc đang chạy; `@PreDestroy` là lớp cleanup cuối, không thay phase coordinator.
8. **Callback termination:** khi được gọi `stop(Runnable)`, callback phải đến sau shutdown completion hoặc best-effort cleanup có log lỗi.
9. **Observability:** ghi event start_requested, started, stop_requested, stopped, failure và duration; không log secrets.
10. **Multi-replica:** `SmartLifecycle` điều phối **trong một context/process**, không bảo đảm consumer chỉ có một instance trên toàn cluster; muốn singleton toàn cụm dùng leader election, broker consumer group, distributed lock hoặc cơ chế phù hợp.

Một thread background được tự tạo nên được quản lý bằng executor có lifecycle và shutdown policy; không dùng `new Thread(...).start()` trong constructor rồi bỏ quên cleanup.

## 13. Tình huống đặc biệt và hiểu sai thường gặp

### 13.1. “Bean được tạo rồi thì start cũng đã chạy”

**Sai.** `manualJob` trong lab có constructor và `@PostConstruct`, nhưng `isRunning=false` đến khi gọi POST start. Bean initialization và lifecycle startup là hai khái niệm khác nhau.

### 13.2. “SmartLifecycle auto-start sau ApplicationReadyEvent”

**Sai trong flow mặc định.** `LifecycleProcessor.onRefresh()` được gọi **trước `ContextRefreshedEvent`**, mà Boot started/runner/ready đến sau. Thế nên không viết `start()` theo cách chờ một `ApplicationReadyEvent` được xử lý trước đó nếu listener ready phải chạy trên cùng startup thread.

### 13.3. “isAutoStartup=false nghĩa là không bao giờ chạy”

**Sai.** Nó chỉ tắt tự start lúc refresh. Code có thể gọi `start()` trực tiếp hoặc lifecycle processor có thể start trong các trường hợp khác, bao gồm explicit context start/dependency lifecycle.

### 13.4. “@Lazy chắc chắn ngăn SmartLifecycle được tạo khi refresh”

**Sai.** Javadoc nêu lazy-init có ảnh hưởng giới hạn, do processor phát hiện lifecycle beans để quản lý start/stop. Muốn tắt theo profile/property, dùng conditional registration hoặc isAutoStartup.

### 13.5. “Không override getPhase thì phase=0”

**Sai cho `SmartLifecycle` hiện đại.** Default là `Integer.MAX_VALUE`, khác với phase 0 thường dùng cho `Lifecycle` thông thường. Nếu muốn thứ tự phụ thuộc rõ ràng, override phase.

### 13.6. “Bean phase càng cao thì start càng sớm”

**Sai.** Khi start: số nhỏ trước. Khi stop: số lớn trước. Nhưng relationship `depends-on` có thể ưu tiên dependency lên trước dependent khi start.

### 13.7. “Chỉ cần override stop() là đủ dù stop(Runnable) không gọi callback”

**Sai.** Nếu bạn override `stop(Runnable)`, processor dùng nó và cần callback sau khi stop hoàn tất; quên callback có thể trì hoãn shutdown đến timeout.

### 13.8. “Stop callback luôn đồng nghĩa đóng mọi resource thành công”

**Không chắc.** Callback là tín hiệu hoàn tất pha xử lý dừng đối với processor. Nếu có exception hoặc timeout trong hạ tầng ngoài, phải log state/cleanup, đánh giá retry và deadline; không biến callback thành bằng chứng mù quáng của business success.

### 13.9. “Gọi context.refresh() lần nữa sẽ start lại job”

**Không nên.** `SpringApplication` đã điều phối refresh. Một số context không cho refresh lại; cách đúng là dùng `start()` của component hoặc `context.start()` nếu semantics phù hợp, không dùng refresh để làm operation.

### 13.10. “Một SmartLifecycle bảo đảm chỉ một consumer trên toàn hệ thống”

**Sai.** Mỗi replica/JVM/ApplicationContext có thể tạo và auto-start một instance riêng. Muốn chỉ một consumer cho toàn cụm cần cơ chế phối hợp ngoài process, không phải `getPhase()`.

## 14. Bảng chẩn đoán lỗi

| Triệu chứng | Giả thuyết cần kiểm | Bước xác minh |
|---|---|---|
| Không thấy `LAB_START foundation` | Bean không được đăng ký, `isAutoStartup=false`, refresh lỗi trước onRefresh | Kiểm bean definitions, log lỗi và property |
| Bean có PostConstruct nhưng chưa running | Auto-start bị tắt hoặc chưa đến onRefresh | Đọc `isAutoStartup()`, phase, event markers |
| `start()` chạy nhưng không thấy `ContextRefreshedEvent` | Một component phase sau ném exception hoặc start đang treo | Đọc stack trace, phase gần nhất, timeout |
| Manual job tự chạy ngoài dự kiến | Có bean Lifecycle khác phụ thuộc hoặc app gọi context.start() | Xem dependency, calls `start()`, logs |
| Thứ tự start ngược kỳ vọng | `getPhase()` sai; dependency override; quan sát nhầm instance | Ghi phase và identity mỗi bean |
| Shutdown đợi hết timeout | `stop(Runnable)` không callback, callback quá muộn hoặc task không dừng | Ghi phase stop begin/end/callback; đo timeout |
| `stop()` không được gọi trên SmartLifecycle | Processor gọi `stop(Runnable)`; custom method không delegate | Đọc implementation `stop(Runnable)` |
| Consumer vẫn nhận job khi app closing | Stop phase, race, broker ack/pause chưa đúng | Xem order vs infrastructure, in-flight policy |
| Startup fail tại `start()` | Kết nối resource lỗi hoặc exception trong component | Root `Caused by`, property, marker |
| Bean `@Lazy` vẫn được tạo sớm | LifecycleProcessor cần phát hiện SmartLifecycle | Dùng `isAutoStartup=false` / conditional |
| Ready có rồi nhưng consumer không running | Component tắt auto-start hoặc fail nhưng lỗi bị nuốt | So API `isRunning()` với business health/readiness |
| Spring Boot stop chậm hơn một phase timeout | Nhiều phases và non-lifecycle shutdown work | Đo từng phase và toàn termination budget |
| Hai listeners/consumers chạy trên hai replica | Auto-start per context, không phải cluster singleton | Kiểm pod count, broker group, coordinator |
| HTTP test không gọi được `/lab/lifecycle` | Port bị chiếm, bind loopback/container, path sai | Đọc log port, server.address, curl |
| Dùng SIGKILL mà không có stop marker | Process bị kill cưỡng bức | Thử Ctrl+C/SIGTERM, không suy ra bug lifecycle |

## 15. Bài tập có tiêu chí nghiệm thu

### Bài tập A — Xác nhận auto start tại refresh

Chạy app mặc định và ghi các marker `LAB_START foundation phase=-100`, `LAB_START consumer phase=100`, `LAB_CONTEXT_REFRESHED`. Kết luận khi thứ tự khớp: component được tự start trong refresh **trước** khi context phát refresh event.

### Bài tập B — isAutoStartup=false

Dùng `GET /lab/lifecycle` cho thấy `manualJob.running=false` trong khi bean đã có constructor marker. Gọi `POST /lab/manual/start`, thấy running=true. Gọi `POST /lab/manual/stop`, thấy running=false. Nhắc lại POST start để kiểm idempotency.

### Bài tập C — Phase và stop callback

Đảm bảo cả ba component running, dừng JVM bằng phương pháp graceful. So thứ tự `LAB_STOP manualJob` → `LAB_STOP consumer` → `LAB_STOP foundation`. Đọc `stop(Runnable)` và xác định tại sao callback cần gọi sau `stop()` trong demo.

### Bài tập D — Lỗi start trong refresh

Chạy JAR với `--lab.fail.foundation=true`. Xác nhận root message `LAB_INTENTIONAL_START_FAILURE_foundation` và không có ready. Giải thích vì sao đã chạy `@PostConstruct` không đồng nghĩa hoàn tất refresh. Khôi phục property để startup thành công.

### Bài tập E — Đổi phase

Trong bản copy lab, thử đổi `foundation.getPhase()` từ -100 lên 300 (bằng cách thay đối số tạo bean) và giữ `consumer.getPhase()=100`. Ghi thứ tự start mới nếu hai bean độc lập: consumer phase=100 trước foundation phase=300. Phân tích tại sao đặt foundation sau consumer là nguy hiểm **nếu consumer thực sự phụ thuộc hạ tầng đó**, và sửa thiết kế bằng phase/depends-on hợp lệ.

### Bài tập F — Thiết kế một worker production

Mô tả một background consumer có start/stop và callback bất đồng bộ. Viết checklist: mở kết nối, đăng ký handler, xác nhận running, ngừng nhận message mới, hoàn tất/rollback in-flight work theo timeout, đóng connection, gọi callback, cập nhật readiness. Không cần viết broker thật nếu chưa có môi trường/credentials; điều quan trọng là hợp đồng và bằng chứng.

### Bảng tổng hợp kỳ vọng

| Bài thực hành | Điều kiện | Bằng chứng | Bài học |
|---|---|---|---|
| Normal startup | 2 auto + 1 manual | 2 START trước refreshed, manual running=false | Auto-start có điều kiện |
| Manual lifecycle | POST manual start/stop | running true rồi false | isAutoStartup không cấm manual |
| Graceful stop | 3 running | Stop theo phase 200,100,-100 | Stop đảo chiều start |
| Startup failure | fail.foundation=true | Start failure, không ready | Start là một phần refresh |
| Phase inversion | Đổi phase explicit | Đảo thứ tự START | Phase là hợp đồng ordering |
| Lazy bean | Xét interface/Javadoc | Lazy flag không đủ để tắt auto start | Dùng đúng control |

## 16. Checklist hoàn thành

- [ ] Trình bày được các method `Lifecycle` và `SmartLifecycle`.
- [ ] Biết `LifecycleProcessor.onRefresh()` tự start `SmartLifecycle` khi context refresh.
- [ ] Biết default `isAutoStartup=true`, default phase `Integer.MAX_VALUE` (Framework 6.2).
- [ ] Phân biệt việc bean được tạo/`@PostConstruct` với việc running.
- [ ] Thấy 2 auto beans start theo phase -100 rồi +100 trước `ContextRefreshedEvent`.
- [ ] Thấy manualJob được tạo nhưng không tự start khi `isAutoStartup=false`.
- [ ] Gọi được HTTP endpoints để đọc và thay đổi state manualJob.
- [ ] Biết quy tắc stop phase lớn trước phase nhỏ, có tính đến `depends-on`.
- [ ] Hiểu ý nghĩa `stop(Runnable callback)` và hậu quả quên callback.
- [ ] Hiểu vì sao `@Lazy` không chắc tắt lifecycle auto-start.
- [ ] Phân biệt `SmartInitializingSingleton`, `@PostConstruct`, runner và `SmartLifecycle`.
- [ ] Gây được lỗi `start()` có chủ đích và phân tích startup failure.
- [ ] Nêu được giới hạn của phase shutdown timeout và graceful web server stop.
- [ ] Không dùng `SmartLifecycle` như cluster-wide singleton hoặc business transaction guard.

## 17. Tài liệu chính thức

1. Spring Framework 6.2 — `SmartLifecycle` Javadoc, mặc định auto-start/phase, stop callback: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
2. Spring Framework 6.2 — Bean lifecycle, startup/shutdown callbacks và phase: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
3. Spring Framework 6.2 — `DefaultLifecycleProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
4. Spring Framework 6.2 — `LifecycleProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/LifecycleProcessor.html
5. Spring Boot 3.5 — Application lifecycle and events: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
6. Spring Boot 3.5 — Graceful shutdown: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html

**Tổng kết:** Khi `ApplicationContext` refresh, `LifecycleProcessor` tự khởi động những `SmartLifecycle` cần auto-start, theo phase và dependency; quá trình đó hoàn tất trước refresh event trong luồng chuẩn. `isAutoStartup` quyết định việc tự start, `isRunning` phản ánh state, còn `stop(Runnable)` là hợp đồng dừng có callback. Hãy dùng một demo có đủ bean auto/manual và đo cả log lẫn HTTP state trước khi áp dụng cơ chế này vào consumer/worker thật.