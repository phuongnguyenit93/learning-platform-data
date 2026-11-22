# Phân biệt khởi tạo bean với bắt đầu hoạt động của thành phần

## 1. Hai câu nói nghe giống nhau nhưng khác vòng đời

Khi Spring Boot tạo một bean, người học thường nghĩ rằng “bean đã khởi tạo” đồng nghĩa “thành phần đã bắt đầu chạy”. Điều đó **không đúng** đối với những thành phần có vòng đời hoạt động riêng như consumer nhận message, bộ lập lịch riêng, kết nối streaming, watcher, listener trên socket, worker thread hoặc một connector cần start/stop.

Cần tách ba ý:

1. **Bean được tạo và initialized**: Spring gọi constructor/factory method, gắn dependency và chạy initialization callbacks phù hợp, chẳng hạn `@PostConstruct`, `InitializingBean.afterPropertiesSet()` hoặc custom init method.
2. **Thành phần bắt đầu hoạt động (start)**: một đối tượng có contract `Lifecycle`/`SmartLifecycle` chuyển sang trạng thái running; có thể bắt đầu polling, đăng ký consumer, kích hoạt một background process hoặc khởi động một resource đang chờ.
3. **Ứng dụng hoàn tất startup (ready)**: Spring Boot chạy xong refresh context, phát `ApplicationStartedEvent`, gọi các runner, phát `ApplicationReadyEvent`, rồi công bố readiness phù hợp.

**Khởi tạo object không tự mang nghĩa một dịch vụ nền đã hoạt động.** Ngược lại, nếu một method `@PostConstruct` tự gọi `start`, đó là **hành vi do người lập trình chủ động viết**, không phải hai phase của Spring đương nhiên trùng nhau.

Điểm mở rộng chính của bài là **`SmartLifecycle`**: Spring Framework dùng nó để quản lý bắt đầu/dừng những thành phần có lifecycle vận hành khi `ApplicationContext` refresh/close. Bài áp dụng cho **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**.

> **Ghi nhớ:** “bean initialized” trả lời *đối tượng đã được container thiết lập chưa?*; “component started” trả lời *nó đã được yêu cầu chạy chưa?*; “application ready” trả lời *toàn ứng dụng đã qua các bước startup bắt buộc chưa?*.

## 2. Bean initialization: phần thiết lập đối tượng

Quá trình khởi tạo một bean singleton điển hình:

```text
Bean definition được tìm thấy
    |
    +--> Tạo instance: constructor / @Bean factory method
    +--> Tiêm dependency vào constructor/field/setter
    +--> Một số Aware callbacks và BeanPostProcessor
    +--> @PostConstruct
    +--> InitializingBean.afterPropertiesSet()
    +--> custom init-method (nếu cấu hình)
    +--> BeanPostProcessor sau initialization
    |
    +--> Bean sẵn sàng được cung cấp cho các bean khác
```

Thứ tự chi tiết có thể chịu ảnh hưởng BeanPostProcessor, proxy, factory bean và dependency graph. Ý nghĩa chung là: **initialization hoàn thiện cấu hình của instance**. Nó có thể xác minh các điều kiện nội bộ, chuẩn hóa giá trị, tạo cấu trúc dữ liệu tại chỗ, chứ không tự động kích hoạt một quy trình vận hành kéo dài.

Một bean đơn giản:

```java
@Component
class RuleCache {

    private Map<String, String> rules;

    @PostConstruct
    void initialize() {
        rules = Map.of("level", "basic");
    }

    String find(String key) {
        return rules.get(key);
    }
}
```

Đây là **đoạn minh họa**, cần import `Map`, `Component` và `PostConstruct`. Sau initialization, `RuleCache` đã dùng được; nhưng nó không có một “worker” cần start hoặc stop. Không phải bean nào cũng cần `SmartLifecycle`.

### 2.1. @PostConstruct có tự chạy lần thứ hai khi context.start() không?

**Không.** `@PostConstruct` thuộc quá trình **initialization của instance**. `context.start()` là tín hiệu lifecycle chạy cho các thành phần `Lifecycle` đủ điều kiện, không tạo lại toàn bộ bean và không lặp lại `@PostConstruct` một cách mặc định.

### 2.2. Initialized không bảo đảm dependency xa đã “ready”

Một bean có thể được khởi tạo thành công khi hệ thống ngoài vẫn chưa kết nối, khi worker nhận message chưa được bật, hoặc khi một runner chưa preload xong dữ liệu. Injection thành công chỉ có nghĩa dependency theo **bean object graph** đã được giải quyết theo cơ chế Spring; nó không tự chứng minh tất cả những dependency đó đã bắt đầu chạy và sẵn sàng làm việc nghiệp vụ.

Đây là lý do quan trọng để phân biệt **cấu hình object** với **kích hoạt operation**.

## 3. Lifecycle và SmartLifecycle là những contract nào?

Spring Framework định nghĩa interface `Lifecycle`:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Đây là chữ ký rút gọn để học, không phải code cần khai báo lại trong ứng dụng. Các method mô tả khả năng bắt đầu/dừng và kiểm tra trạng thái running của một thành phần.

`SmartLifecycle` mở rộng `Lifecycle` và `Phased` để hỗ trợ:

- **`isAutoStartup()`**: có tự start vào lúc context refresh không?
- **`getPhase()`**: điều phối thứ tự start/stop so với những lifecycle components khác.
- **`stop(Runnable callback)`**: hỗ trợ quá trình dừng bất đồng bộ; container chờ callback hoàn tất theo timeout/phase.

Mô hình API:

```java
public interface SmartLifecycle extends Lifecycle, Phased {
    default boolean isAutoStartup() {
        return true;
    }

    default int getPhase() {
        return DEFAULT_PHASE;
    }

    default void stop(Runnable callback) {
        stop();
        callback.run();
    }
}
```

Đây là **mã giải thích hợp đồng chính**, không phải bản sao đầy đủ để tạo lại interface Spring. API trong Spring 6.1 mặc định:

- `isAutoStartup()` trả **`true`**.
- `DEFAULT_PHASE` là **`Integer.MAX_VALUE`** (mức rất muộn khi startup, rất sớm khi shutdown tương đối với phase nhỏ hơn).
- `stop(Runnable)` mặc định gọi `stop()` rồi callback; triển khai có dừng bất đồng bộ nên override cách phù hợp.
- `getPhase()` là phần của `Phased`, được `SmartLifecycle` cung cấp default.

**Điểm dễ nhầm:** `Lifecycle` thông thường **không tự được start chỉ vì context refresh**, còn `SmartLifecycle` với `isAutoStartup() == true` được `LifecycleProcessor` tự start trong quá trình refresh.

## 4. SmartLifecycle nằm ở đâu trong SpringApplication?

Timeline rút gọn cho Boot 3.3:

```text
SpringApplication.run(args)
    |
    +--> chuẩn bị Environment và ApplicationContext
    +--> load bean definitions
    +--> refresh(context)
    |       +--> tạo/wire non-lazy singleton
    |       +--> @PostConstruct / init methods của bean
    |       +--> finishRefresh / LifecycleProcessor.onRefresh()
    |                +--> tự start SmartLifecycle isAutoStartup=true
    |                +--> xử lý startup phase và depends-on
    |       +--> ContextRefreshedEvent
    |
    +--> ApplicationStartedEvent
    +--> công bố LivenessState.CORRECT
    +--> ApplicationRunner / CommandLineRunner
    +--> ApplicationReadyEvent
    +--> công bố ReadinessState.ACCEPTING_TRAFFIC
    +--> SpringApplication.run(...) return

Khi đóng context theo đường bình thường:
    |
    +--> LifecycleProcessor.onClose()
    |       +--> stop SmartLifecycle đang running
    |       +--> chạy shutdown phase theo thứ tự ngược
    |       +--> đợi stop(Runnable callback) trong giới hạn timeout
    +--> @PreDestroy / DisposableBean / destroyMethod cho bean phù hợp
    +--> đóng context
```

**Kết luận về thứ tự:** Với một bean singleton `SmartLifecycle` tự start, Spring hoàn tất **initialization callback** của bean đó trước khi gọi `start()` của nó. `start()` thường xảy ra **trong context refresh**, tức **trước** `ApplicationStartedEvent` và trước runner.

Không nên suy rộng rằng mọi bean lazy trong toàn bộ ứng dụng đều được tạo xong trước mọi `start()`; đó là hình ảnh đơn giản về non-lazy singleton và các thành phần được refresh xử lý. Với custom scopes, lazy initialization hoặc lifecycle processor tùy biến, thời điểm tạo những bean khác có thể khác.

### 4.1. Đừng đánh đồng start() với ApplicationStartedEvent

Mặc dù cùng chữ “start”, đây là hai sự kiện khác bản chất:

| Cơ chế | Thực hiện trên | Mốc bình thường | Ai chịu trách nhiệm |
| --- | --- | --- | --- |
| `@PostConstruct` | Một instance bean được Spring quản lý | Khi bean được initialized | Bean container / post-processor |
| `SmartLifecycle.start()` | Một lifecycle component | Trong refresh nếu auto-start, hoặc gọi start thủ công | `LifecycleProcessor` hoặc caller |
| `ApplicationStartedEvent` | Toàn SpringApplication | Sau refresh, **trước runner** | Spring Boot |
| `ApplicationRunner.run()` | Một startup task bean | Sau started event | Spring Boot |
| `ApplicationReadyEvent` | Toàn SpringApplication | Sau khi runner hoàn tất thành công | Spring Boot |
| `@PreDestroy` | Destruction của bean phù hợp | Khi bean bị destroy | Bean container |

Một `SmartLifecycle.start()` trả về không chứng minh toàn hệ thống đã ready. Nếu nó chỉ kích hoạt thread nền rồi return ngay, readiness của Boot không tự chờ thread đó hoạt động đầy đủ.

### 4.2. start() không phải là constructor thứ hai

Không gọi `start()` để sửa logic chưa hoàn thành của constructor. Nên phân chia:

- **Constructor / dependency injection:** nhận dependency bắt buộc.
- **@PostConstruct:** kiểm tra/chuẩn hóa và chuẩn bị state nhanh, không thực hiện I/O dài không cần thiết.
- **start:** thực hiện chuyển trạng thái active, bắt đầu tiêu thụ/đăng ký/subscribe resource.
- **stop:** ngừng nhận công việc, đóng hoặc giải phóng phần resource thuộc ownership của component.
- **@PreDestroy:** cleanup cuối cùng; đừng coi nó thay cho stop có phase và phối hợp shutdown.


## 5. Ví dụ Java 17+ chạy được: initialized trước start, started trước runner

Mục tiêu thí nghiệm là quan sát **một** `SmartLifecycle` bean, không có logic network, để thấy chính xác các mốc. Code chủ động in rõ constructor, `@PostConstruct`, `start()`, started event, runner, ready event, `stop(Runnable)` và `@PreDestroy`.

### 5.1. Cấu hình dự án Gradle

Tạo project với Gradle Wrapper, Java 17+ và Spring Boot 3.3.13. File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
```

File `settings.gradle`:

```groovy
rootProject.name = 'smart-lifecycle-lab'
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Chọn non-web mode để tiến trình tự kết thúc sau khi `try-with-resources` đóng context. Đây là bài minh họa lifecycle; không cần web server hoặc database.

### 5.2. Mã Java hoàn chỉnh

Tạo file `src/main/java/com/example/lifecycle/LifecycleStagesApplication.java`:

```java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class LifecycleStagesApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(LifecycleStagesApplication.class, args)) {

            DemoWorker worker = context.getBean(DemoWorker.class);
            System.out.println("07 main: running=" + worker.isRunning());
        }
    }

    @Bean
    DemoWorker demoWorker() {
        return new DemoWorker();
    }

    @Bean
    ApplicationRunner checkWorker(DemoWorker worker) {
        return args -> System.out.println(
                "05 runner: running=" + worker.isRunning());
    }

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("04 ApplicationStartedEvent");
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("06 ApplicationReadyEvent");
    }

    static final class DemoWorker implements SmartLifecycle {
        private volatile boolean running;

        DemoWorker() {
            System.out.println("01 constructor");
        }

        @PostConstruct
        public void initialize() {
            System.out.println("02 @PostConstruct");
        }

        @Override
        public void start() {
            if (running) {
                return;
            }
            running = true;
            System.out.println("03 SmartLifecycle.start");
        }

        @Override
        public void stop() {
            if (!running) {
                return;
            }
            running = false;
            System.out.println("08 SmartLifecycle.stop");
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                // Quan trọng: báo cho LifecycleProcessor rằng stop đã xong.
                callback.run();
            }
        }

        @Override
        public boolean isRunning() {
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

        @PreDestroy
        public void cleanup() {
            System.out.println("09 @PreDestroy");
        }
    }
}
```

**Đây là file Java đầy đủ và nhất quán**: class chứa `main`, bean factory, runner, event listeners và class triển khai `SmartLifecycle` nằm trong một tệp. Các annotation `jakarta.annotation` được Spring Boot starter hỗ trợ.

Trong chương trình:

- `DemoWorker` được tạo bởi phương thức `@Bean`; constructor chạy trước `@PostConstruct`.
- `SmartLifecycle` tự start trong refresh vì `isAutoStartup()` trả `true`.
- `getPhase() == 100` là mức phase của worker. Vì chỉ có **một worker do mã bài tạo ra**, số phase ở đây không làm thay đổi thứ tự stdout; nó minh họa nơi khai báo thứ tự khi có nhiều component.
- `ApplicationStartedEvent` xảy ra sau refresh; runner nhìn thấy `worker.isRunning() == true`.
- `ApplicationReadyEvent` xảy ra sau runner.
- `try-with-resources` đóng context khi rời khối. Spring gọi `stop(Runnable)` rồi destruction callback của bean.
- `@PreDestroy` không phải cùng callback với `stop()`. Nó in một dòng riêng để làm rõ hai pha.

### 5.3. Lệnh chạy

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Các dòng **do chính mã Java in ra**, với cấu hình như trên:

```text
01 constructor
02 @PostConstruct
03 SmartLifecycle.start
04 ApplicationStartedEvent
05 runner: running=true
06 ApplicationReadyEvent
07 main: running=true
08 SmartLifecycle.stop
09 @PreDestroy
```

Gradle và runtime có thể có log riêng; chỉ đối chiếu các dòng có số đầu của chương trình. Đây là **timeline của ví dụ non-web**, không phải khẳng định mọi listener/bean do auto-configuration đăng ký đều in log theo cùng mốc.

Nếu dòng `02` xuất hiện mà dòng `03` không có, chưa thể kết luận component đã chạy. Nếu có dòng `03` nhưng runner chưa hoàn tất, không thể kết luận ứng dụng đã ready. Nếu shutdown có dòng `08`, callback `stop` đã được xử lý; `09` chứng tỏ destruction của bean vẫn là một bước riêng.

### 5.4. Chuyển từ auto-start sang manual start

Đổi implementation:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

Đây là **thay đổi một method trong file trên**, không phải một file Java độc lập. Với thay đổi này, context vẫn tạo/initialize bean khi nó cần, nhưng `LifecycleProcessor.onRefresh()` **không tự gọi `DemoWorker.start()`**. Runner sẽ thấy `running=false`, trừ khi code khác chủ động start nó.

Để bật thủ công **sau khi `SpringApplication.run` trả về**, gọi:

```java
DemoWorker worker = context.getBean(DemoWorker.class);
worker.start(); // hoặc context.start() nếu muốn bật các Lifecycle beans phù hợp
```

Lưu ý rất quan trọng: trong thí nghiệm vừa đổi, runner đã chạy **trước** `main` tiếp tục nhận context; nếu runner yêu cầu component phải active thì manual start trong `main` là **quá muộn**. Khi đó cần tổ chức bootstrap khác hoặc chọn `isAutoStartup=true`.

### 5.5. Nếu start() throw thì sao?

Giả sử thay nội dung `start()` thành:

```java
@Override
public void start() {
    throw new IllegalStateException("Cannot start the worker");
}
```

Đây là **đoạn thay thế minh họa**. Vì `SmartLifecycle.start()` chạy trong refresh, ngoại lệ thoát ra có thể làm **context refresh thất bại** và Boot đi vào startup failure. Khi ấy `ApplicationStartedEvent`, runner và `ApplicationReadyEvent` **không phải mốc đã đi qua** theo chuỗi thành công.

Như vậy lỗi trong `start()` và lỗi trong `ApplicationRunner.run()` có vị trí khác: runner lỗi sau refresh, còn start lỗi có thể khiến refresh chưa hoàn thành. Với cả hai, không được âm thầm che lỗi của điều kiện bắt buộc.

### 5.6. Có thể restart component mà không tạo lại bean?

Khi context còn hoạt động và component hỗ trợ start/stop lặp lại đúng cách, có thể làm:

```java
DemoWorker worker = context.getBean(DemoWorker.class);
worker.stop();
worker.start();
```

Đây là **đoạn minh họa** trong nơi đã có `context` và `DemoWorker`. Không có lần gọi `@PostConstruct` thứ hai: vẫn là một instance đã initialized trước đó. Trạng thái `running` thay đổi qua `stop()/start()`, minh họa độc lập giữa **object creation** và **runtime activation**.

Nếu component mở resource không thể mở lại, start/stop thủ công có thể không hỗ trợ restart; việc này phải được thiết kế rõ. Đừng gọi `start()` khi context đã `close()`.


## 6. Thứ tự khởi tạo bean không phải thứ tự phase

Một trong những ngộ nhận lớn nhất: “`getPhase() = -100` làm bean ấy được **tạo trước** các bean có phase `10`”. **Không.**

`getPhase()` được `LifecycleProcessor` dùng để **điều phối start/stop** các lifecycle components. Nó **không thay thế** constructor injection, bean dependencies, component scanning, `@DependsOn` hoặc thứ tự bean initialization.

Giả sử ta có hai worker (đây là **đoạn class minh họa**, không phải file độc lập):

```java
class DatabaseConnector implements SmartLifecycle {
    @Override public int getPhase() { return 100; }

    // Các method start, stop, isRunning... phải triển khai đầy đủ.
}

class MessageConsumer implements SmartLifecycle {
    @Override public int getPhase() { return 200; }

    // Các method start, stop, isRunning... phải triển khai đầy đủ.
}
```

Nếu cả hai là lifecycle bean auto-start trong cùng context, theo ordering thông thường:

```text
START: DatabaseConnector(100) -> MessageConsumer(200)
STOP : MessageConsumer(200)   -> DatabaseConnector(100)
```

Điều này có ý nghĩa nếu consumer cần connector **đang hoạt động** trước khi subscribe. Ngược lại, dừng consumer trước giúp không phát sinh thêm request tới connector đang shutdown.

**Nhưng:** trước khi gọi `start`, cả hai bean có thể đã được tạo/initialized theo dependency graph và pre-instantiation của singleton. Không được dùng `phase` để phán đoán log constructor hoặc `@PostConstruct` chạy trước/sau.

### 6.1. Giá trị phase: thấp start trước, cao stop trước

| Phase | Startup | Shutdown |
| --- | --- | --- |
| `-100` | Sớm hơn 0 | Muộn hơn 0 |
| `0` | Sau -100, trước 100 | Sau 100, trước -100 |
| `100` | Sau 0, trước 200 | Trước 0, sau 200 |
| `200` | Sau 100 | Trước 100 |
| `Integer.MAX_VALUE` | Thường rất muộn | Thường rất sớm |

Trong Spring Framework 6.1:

- `SmartLifecycle.DEFAULT_PHASE == Integer.MAX_VALUE`.
- Các `Lifecycle` thông thường (không triển khai `SmartLifecycle`) được xử lý với **phase 0** trong việc điều phối chung.
- Không nên tự dùng `Integer.MIN_VALUE` hoặc `MAX_VALUE` nếu không có lý do vì các thành phần framework có thể sử dụng những mức đặc biệt.
- Những bean **cùng phase** không có thứ tự tương đối được cam kết; không viết code phụ thuộc vào thứ tự tình cờ thấy trong log.

**Đây không phải `@Order`.** `@Order` thường áp dụng để sắp listener, runner, collection injection hoặc các extension points khác. `SmartLifecycle` dùng `getPhase()` cho phase start/stop.

### 6.2. @DependsOn có thể ưu tiên hơn getPhase

Spring Framework quy định quan hệ dependency tường minh `depends-on` có ưu tiên trong lifecycle order: **bean phụ thuộc được start sau dependency, và stop trước dependency**, ngay cả khi phase khai báo mâu thuẫn.

Ví dụ ý tưởng:

```java
@Bean("source")
SourceWorker source() {
    return new SourceWorker();
}

@Bean("consumer")
@DependsOn("source")
ConsumerWorker consumer() {
    return new ConsumerWorker();
}
```

Đoạn này chỉ minh họa bean methods, cần định nghĩa hai class và import `@Bean`/`@DependsOn`. Nếu `ConsumerWorker` depends-on `SourceWorker`, Spring phải bảo đảm mối quan hệ lifecycle theo thứ tự phụ thuộc; `getPhase()` không nên được dùng để phá constraint ấy.

Tốt nhất là **thể hiện dependency rõ ràng** khi consumer thật sự cần source. Khi không có dependency bean tường minh mà chỉ có thứ tự start nghiệp vụ, dùng phase một cách cẩn thận.

### 6.3. Không giả định cùng phase có một trật tự ổn định

Nếu hai consumer đều phase 100, thứ tự chạy trong cùng phase **không phải contract có thể dựa vào**. Nó có thể phụ thuộc số lượng bean, thứ tự registration hoặc thay đổi version.

Khi một consumer nhất thiết chờ consumer khác bắt đầu, nên tách phase hoặc dependency, và quan trọng hơn là **xác minh nó đã thực sự sẵn sàng**, không chỉ đã được gọi `start()`.

### 6.4. @Lazy không ngăn chắc SmartLifecycle auto-start

`SmartLifecycle` tham gia cơ chế auto-start trong refresh. `LifecycleProcessor` có thể phải lấy bean để gọi `isAutoStartup()/start()`, nên flag `@Lazy` có **tác dụng hạn chế** đối với bean SmartLifecycle. Tài liệu Spring Framework nói rõ SmartLifecycle bean thường vẫn được initialize trong startup.

Nếu muốn tránh tự kích hoạt một thành phần, hãy đặt `isAutoStartup() == false` và **xem lại cách bean được khởi tạo/tiêu thụ**, thay vì chỉ thêm `@Lazy` rồi mong worker không chạy.

## 7. stop(), stop(Runnable) và @PreDestroy không giống nhau

### 7.1. Những tình huống gọi stop

- `context.stop()`: thông báo dừng lifecycle components trong context **mà không destroy toàn bộ bean**; có thể `context.start()` lại nếu context còn hợp lệ.
- `context.close()`: thực hiện đóng context; lifecycle processor dừng các thành phần running rồi Spring xử lý destruction callback của bean phù hợp.
- Direct `worker.stop()`: gọi trực tiếp trên object; bạn chịu trách nhiệm bảo đảm component và những dependency khác không bị dừng sai thứ tự.
- `@PreDestroy`: callback destruction khi bean bị destroy; **không tự tương đương** với một lệnh `stop()` có phase đúng.

Với `SmartLifecycle`, khi `DefaultLifecycleProcessor` thực hiện graceful stop, nó sử dụng **`stop(Runnable callback)`**, không phải nhất thiết gọi trực tiếp no-argument `stop()`. Nếu bạn override `stop(Runnable)`, hãy gọi logic stop thật và báo hoàn tất đúng cách.

### 7.2. Vì sao phải gọi callback.run()?

Một component có thể cần dừng bất đồng bộ: gửi tín hiệu đóng queue, chờ consumer ack, drain inflight messages, rồi mới release connection. Spring chờ `stop(Runnable callback)` thông báo đã dừng, trong giới hạn timeout của phase.

Mẫu đúng về trách nhiệm callback:

```java
@Override
public void stop(Runnable callback) {
    workerExecutor.execute(() -> {
        try {
            stopReceivingNewTasks();
            awaitInFlightTasks();
            releaseOwnedResources();
        } finally {
            running = false;
            callback.run();
        }
    });
}
```

Đoạn này **chỉ minh họa**, cần các field/method `workerExecutor`, `running`, `stopReceivingNewTasks` và các method còn lại; không phải class chạy độc lập. Trong code thật, cần xử lý cả trường hợp `workerExecutor.execute(...)` bị reject: nếu không schedule được, bạn vẫn phải xử lý cleanup/failure và **hoàn tất callback đúng một lần**. Không gọi `callback.run()` ngay lúc mới submit task nếu stop chưa xong.

**Không gọi callback** khiến lifecycle processor chờ cho đến khi hết timeout của phase, làm shutdown chậm hoặc không hoàn tất sạch. **Gọi callback quá sớm** khiến container tin component đã ngừng trong khi task vẫn hoạt động, có thể làm dependency của nó bị đóng trước.

### 7.3. Timeout cho mỗi shutdown phase

Spring Framework 6.1 `DefaultLifecycleProcessor` có timeout theo shutdown phase (mặc định **30 giây** trong API này). Spring Boot 3.3 có thể cấu hình:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Đây là **thời gian chờ cho phase**, không phải timeout tuyệt đối bảo đảm toàn bộ tiến trình kết thúc trong 20 giây. Nếu có nhiều phase, container hoặc hệ điều phối có thêm giới hạn, tổng thời gian shutdown có thể khác.

Trong Kubernetes, cần phối hợp thời gian này với `terminationGracePeriodSeconds`, reverse proxy và ngưỡng của queue/consumer. `SIGKILL`/crash không cho Java cơ hội hoàn tất graceful callbacks.

### 7.4. Destruction callback riêng sau stop

Với bean singleton bình thường, `@PreDestroy`/`DisposableBean.destroy()`/custom destroy method hoạt động khi container thực sự destroy bean, không phải mỗi lần `context.stop()`. Trong shutdown có kiểm soát, lifecycle stop thường trước bean destruction. Tuy nhiên trong một số **startup failure hoặc refresh failure**, không thể bảo đảm mọi stop notification chạy theo trình tự thông thường; destruction callbacks có thể vẫn được xử lý để cleanup phần tài nguyên đã tạo.

Một bean prototype **không tự được Spring gọi destruction callback khi context đóng** chỉ vì class của nó triển khai `SmartLifecycle`. Các component cần quản lý lifecycle tập trung thường nên được đăng ký **singleton** và có owner rõ ràng.

## 8. isAutoStartup(), manual start và trạng thái running

### 8.1. Ý nghĩa isAutoStartup

- `true` (mặc định): lifecycle processor sẽ auto-start component trong refresh, theo phase/depends-on.
- `false`: không auto-start chỉ vì refresh; component được thiết kế để bật theo tín hiệu rõ ràng sau đó.
- Việc bean **được created/initialized** không đồng nghĩa `isRunning() == true`. 

`isRunning()` phải phản ánh trạng thái thực tế do implementation quản lý.

Nếu một hệ thống có tính năng chỉ hoạt động khi người vận hành bật, `isAutoStartup=false` là một lựa chọn, nhưng phải có nơi rõ ràng gọi `start()` khi đủ điều kiện.

### 8.2. start() phải có hợp đồng idempotent

Trong implementation thực tế:

```java
@Override
public synchronized void start() {
    if (running) {
        return;
    }
    connect();
    beginConsuming();
    running = true;
}
```

Đây là **mẫu minh họa**, cần `running`/`connect`/`beginConsuming` được định nghĩa. Không nên đánh `running=true` quá sớm nếu `connect()` có thể throw: startup monitor sẽ hiểu sai state. Nếu `beginConsuming()` là async, `start()` return không bảo đảm consumer đã ready; cần bổ sung cơ chế chờ/ack/readiness.

Trong multi-threaded component, `volatile` hoặc cơ chế đồng bộ thích hợp là cần thiết cho state. `isRunning()` không nên trả một boolean tùy tiện không liên quan tới khả năng hoạt động thực sự.

### 8.3. stop() cũng phải chịu được gọi lại

Stop có thể được yêu cầu từ context, caller hoặc shutdown hook. Implementation nên cân nhắc:

- Nếu đã dừng thì không đóng resource lần hai một cách không an toàn.
- Nếu đang stopping, phối hợp các lời gọi và callback thay vì báo dừng giả.
- Không để một exception cleanup khiến callback không được gọi.
- Không thực hiện chờ vô hạn khi dependency không phản hồi.
- Không release resource **đi mượn** từ bean khác khi component không phải owner.

Một lifecycle component chứa network handle cần được thiết kế để đóng đúng thứ tự: ngừng nhận task mới, xử lý inflight trong thời hạn, hủy đăng ký consumer, release resource sở hữu, đánh state và báo callback.

## 9. Khi nào dùng @PostConstruct, SmartLifecycle hay ApplicationRunner?

| Nhu cầu | Điểm mở rộng thường phù hợp | Lý do |
| --- | --- | --- |
| Kiểm tra/chuẩn hóa fields, tạo cache thuần trong RAM | Constructor / `@PostConstruct` | Gắn với việc bean initialized |
| Bật một consumer/poller khi context refresh | `SmartLifecycle` | Có start/stop, phase, auto-start, callback shutdown |
| Điều phối nhiều worker cần start theo thứ tự | `SmartLifecycle.getPhase()` + dependency | Phase tăng khi start, giảm khi stop |
| Worker chỉ bật khi nhận lệnh của user/admin | `SmartLifecycle(isAutoStartup=false)` hoặc API riêng | Không tự active tại refresh |
| Kiểm tra điều kiện bắt buộc sau khi các bean đã được tạo | `ApplicationRunner`/`CommandLineRunner` | Chạy sau refresh, trước ready |
| Cần trigger khi Boot startup hoàn tất | `ApplicationReadyEvent` | Sự kiện ứng dụng đã qua runner thành công |
| Gắn destroy operation khi singleton bị giải phóng | `@PreDestroy` hoặc `@Bean(destroyMethod=...)` | Cleanup bean, không phải phase start/stop |
| Phơi bày readiness chính xác khi worker nền chưa sẵn sàng | `ApplicationAvailability`/readiness health | Start return không chứng minh background initialization xong |
| Điều phối nghiệp vụ nhiều bước có rollback/retry | Service/workflow rõ ràng | phase không thay thế transaction orchestration |

### 9.1. Chọn SmartLifecycle cho worker có vận hành lâu dài

Ví dụ đối tượng:

```text
MessageConsumer bean
    |
    +--> @PostConstruct: validate queue name, prepare options
    +--> start: subscribe vào broker / begin polling
    +--> isRunning: phản ánh trạng thái consumer
    +--> stop(callback): pause intake, drain inflight, unsubscribe
    +--> @PreDestroy: release tài nguyên cuối nếu còn
```

Đây là nơi `SmartLifecycle` phát huy tác dụng: bật/dừng đi cùng vòng đời context và có thể điều phối theo dependency. Cần tránh chạy một consumer vô hạn ngay trong constructor hoặc `@PostConstruct` rồi khiến quá trình tạo bean treo.

### 9.2. Chọn runner cho bootstrap một lần

Một `ApplicationRunner` phù hợp khi cần load dữ liệu tham chiếu bắt buộc hoặc xác minh điều kiện sau refresh trước readiness. Nó **không có contract stop/restart riêng**. Nếu runner bật một background service và để nó chạy suốt vòng đời ứng dụng, nên hỏi liệu service đó có cần `SmartLifecycle` để được dừng đúng lúc hay không.

### 9.3. Chọn event khi chỉ cần quan sát một mốc

`ApplicationStartedEvent` và `ApplicationReadyEvent` là event của `SpringApplication`, không phải lệnh cấp thấp để bật/dừng từng component. Chúng phù hợp cho telemetry/notification nhẹ, không thay thế dependency lifecycle ordering.

## 10. Liveness/readiness liên quan gì tới SmartLifecycle?

Trong Boot 3.3.x, sau refresh và việc tự start các `SmartLifecycle` phù hợp, Boot phát `ApplicationStartedEvent`; sau đó runner được gọi; readiness accepting được công bố sau `ApplicationReadyEvent`.

**Nhưng:** một implementation `start()` chỉ submit task sang executor rồi return, trong khi task thực tế chưa kết nối broker. Spring có thể cho rằng phase start đã hoàn thành, và Boot vẫn đi tới ready sau runner. **Không được nhầm “start() method returned” với “service đã phục vụ đúng”.**

Nếu sự sẵn sàng thực sự phụ thuộc worker nền:

- Thiết kế `start()` chờ một readiness signal có deadline khi phù hợp; fail-fast nếu không đạt điều kiện bắt buộc.
- Hoặc dùng một runner chờ kết quả startup worker trước ready.
- Hoặc dùng readiness health/state phản ánh điều kiện thực tế, tránh đưa traffic vào instance chưa thể phục vụ.
- Đưa lỗi async vào metrics/log/alert và có cơ chế thu hồi readiness khi worker mất khả năng hoạt động sau startup.
- Không đánh liveness BROKEN chỉ vì dependency bên ngoài tạm hỏng nếu restart không giải quyết được sự cố.

**Phase không phải readiness gate**. Nó chỉ điều phối thứ tự lời gọi start/stop giữa components.

## 11. Lỗi thường gặp và cách kiểm tra

| Triệu chứng / nhận định | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| “Có `@PostConstruct` là worker đang chạy” | Init không tự kích hoạt `SmartLifecycle.start` | Kiểm tra `start()` và `isRunning()` |
| “`ApplicationStartedEvent` chính là callback của component” | Event Boot sau refresh, không phải method start trên bean | Phân biệt ba tầng bean/component/application |
| “`getPhase(-100)` khiến constructor bean chạy đầu tiên” | Phase sắp start/stop, không sắp initialization | Dùng dependency graph và bean lifecycle đúng |
| “`@Order(10)` điều phối SmartLifecycle phase” | Nhầm `@Order` với `SmartLifecycle.getPhase` | Override `getPhase()` cho start/stop |
| “Hai worker cùng phase chắc chạy theo tên bean” | Tie không bảo đảm order | Dùng phase/dependency rõ ràng |
| “`SmartLifecycle` mặc định phase 0” | Mặc định của `SmartLifecycle` là `Integer.MAX_VALUE` | Chủ động override phase theo thiết kế |
| “`@Lazy` chắc chặn SmartLifecycle tự tạo” | LifecycleProcessor có thể khởi tạo để auto-start | Cân nhắc `isAutoStartup=false` |
| “`isAutoStartup=false` nhưng runner vẫn thấy worker active” | Có code khác gọi `start()` | Kiểm tra log/caller và state |
| “Dùng `@PreDestroy` thay `stop(Runnable)` là đủ” | Mất phase coordination và cơ chế thông báo dừng async | Implement stop đúng contract |
| “`stop(Runnable)` không cần callback” | LifecycleProcessor có thể chờ timeout | Gọi callback sau khi stop hoàn tất |
| “Gọi callback ngay sau submit shutdown job là xong” | Job có thể chưa dừng thật | Báo callback khi worker đã stop |
| “Context.stop() giống context.close()” | stop không destroy bean, close có destruction | Chọn thao tác theo vòng đời |
| “SmartLifecycle.start() return là app ready” | Runner và async warmup có thể chưa hoàn tất | Theo dõi ready/readiness |
| “Bean start fail, Boot vẫn luôn phát ApplicationStartedEvent” | Lỗi start trong refresh có thể abort startup | Xem stacktrace phần refresh và ApplicationFailedEvent |
| “stop callback luôn chạy cả khi JVM bị SIGKILL” | Không có cơ hội graceful shutdown | Thiết kế timeout và recovery |
| “Prototype SmartLifecycle được Spring tự destroy khi context close” | Prototype không được container theo dõi destruction như singleton | Dùng singleton cho long-running component hoặc owner riêng |

### 11.1. Checklist debug thời điểm component thực sự active

1. Ghi log constructor/`@PostConstruct`/`start()`/`stop(Runnable)`/`@PreDestroy` với tên bean/component.
2. Đọc `isAutoStartup()` và `getPhase()` của component.
3. Kiểm tra `@DependsOn`/dependency graph nếu phase không cho thứ tự mong đợi.
4. Kiểm tra có `@Lazy`, scope hoặc bean factory tùy biến làm thay đổi việc bean được tạo không.
5. Đối chiếu với `ContextRefreshedEvent`, `ApplicationStartedEvent`, runner và `ApplicationReadyEvent`.
6. Khi dừng, đo xem `stop(Runnable)` có thực sự gọi callback hay đang chờ timeout.
7. Nếu có background thread, đo chính xác state và readiness signal thay vì chỉ dựa vào một boolean đặt sớm.
8. Nếu lỗi trong `start()`, tìm root cause của refresh/startup failure, không chỉ wrapper exception.
9. Nếu dùng web application, quan sát readiness health group và thời điểm cổng bắt đầu nhận traffic.
10. Nếu có shutdown không sạch, kiểm tra thời gian chờ per-phase, resource ownership và hành vi của executor.
11. Không đưa token, password hoặc payload nhạy cảm vào log lifecycle.

## 12. Tự kiểm tra

**Câu 1.** `@PostConstruct` chạy nghĩa là `SmartLifecycle.start()` cũng đã chạy?

**Đáp:** Không. Initialization và startup của component là hai pha khác nhau. Nếu auto-start bật, `start()` được gọi sau initialization trong refresh.

**Câu 2.** Khi Spring Boot phát `ApplicationStartedEvent`, các auto-start `SmartLifecycle` thường đã được gọi chưa?

**Đáp:** Có, theo chuỗi refresh thành công thông thường. Nhưng điều đó không bảo đảm task async được chúng khởi tạo đã thực sự ready nếu `start()` return quá sớm.

**Câu 3.** `getPhase() = -100` có làm constructor của bean chạy trước những bean phase 100?

**Đáp:** Không. Phase điều phối start/stop, không phải bean initialization order.

**Câu 4.** Nếu A phase 10 và B phase 20, cùng auto-start, startup/shutdown theo thứ tự nào?

**Đáp:** Startup A rồi B; shutdown B rồi A, trừ quan hệ dependency tường minh cần được ưu tiên.

**Câu 5.** `SmartLifecycle` không override `isAutoStartup()` và `getPhase()` thì mặc định gì?

**Đáp:** `isAutoStartup() == true` và `getPhase() == Integer.MAX_VALUE` trong Spring Framework 6.1.

**Câu 6.** Nếu `isAutoStartup() == false`, context refresh có tự gọi `start()` không?

**Đáp:** Không, theo contract auto-start. Bean vẫn có thể được tạo/initialized; caller có thể start thủ công hoặc sử dụng context lifecycle.

**Câu 7.** `stop(Runnable)` báo callback trước khi việc dừng async hoàn tất có nguy hiểm không?

**Đáp:** Có. Container có thể dừng dependency trước khi worker ngừng sử dụng nó. Cần callback đúng lúc đã dừng.

**Câu 8.** Vì sao không chỉ dùng `@PreDestroy` để điều phối stop nhiều consumer?

**Đáp:** `@PreDestroy` là destruction callback, không cung cấp phase/start-stop protocol và async callback coordination của `SmartLifecycle`.

**Câu 9.** `context.stop()` có khiến Spring gọi lại `@PostConstruct` khi `context.start()` không?

**Đáp:** Không. Đây là thay đổi runtime state trên những instance còn tồn tại; không phải tạo bean lại.

**Câu 10.** Nếu `start()` ném exception, có thể ApplicationStartedEvent và runner vẫn chạy tiếp như startup thành công không?

**Đáp:** Không nên kỳ vọng. Lỗi trong auto-start của refresh có thể làm refresh fail, khiến Boot xử lý startup failure trước các mốc started/runner/ready.

**Câu 11.** Vì sao dùng `@Lazy` không đủ để ngăn một SmartLifecycle auto-start?

**Đáp:** LifecycleProcessor có thể phải khởi tạo nó để quyết định và thực hiện auto-start; default `isAutoStartup() == true` mới là yếu tố phù hợp để xét.

## 13. Ghi nhớ và nguồn tham khảo

- **Initialization:** constructor/injection/`@PostConstruct`/init methods chuẩn bị **bean object**.
- **Runtime start:** `SmartLifecycle.start()` kích hoạt **thành phần**, thường trong refresh nếu auto-start.
- **Boot started/ready:** các **mốc cấp ứng dụng** sau refresh và sau runner, không đồng nhất với từng component.
- **Thứ tự:** `getPhase()` số nhỏ start sớm; shutdown theo thứ tự ngược. `depends-on` tường minh có thể ưu tiên hơn phase. Không dùng `@Order` để suy ra phase.
- **Mặc định Spring 6.1:** `SmartLifecycle.isAutoStartup() == true` và phase mặc định `Integer.MAX_VALUE`.
- **Dừng sạch:** `stop(Runnable)` phải báo callback **sau khi** component dừng thực tế; destruction callback như `@PreDestroy` là bước khác.
- **Async readiness:** `start()` return không tự chứng minh công việc nền đã sẵn sàng. Cần timeout, readiness state và error handling phù hợp.

Tài liệu chính thức:

- [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html), đặc biệt `DEFAULT_PHASE`, `isAutoStartup()` và `stop(Runnable)`.
- [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html), `onRefresh()`, `onClose()`, thứ tự phase và timeout.
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html), phần lifecycle callbacks và SmartLifecycle.
- [Spring Boot 3.3 — SpringApplication and Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), phân biệt started/runner/ready.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html), `server.shutdown` và `spring.lifecycle.timeout-per-shutdown-phase`.

Trong thực hành, khi hỏi một worker “đã khởi động chưa?”, hãy xác định đang hỏi **bean đã initialized**, **SmartLifecycle.isRunning()**, **nhiệm vụ nền thật sự ready** hay **toàn SpringApplication đã qua ready**. Bốn điều này có thể được quan sát ở các mốc khác nhau.
