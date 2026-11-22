# ApplicationStartedEvent: sự kiện sau khi refresh context, trước khi gọi các runner

## 1. Hiểu đúng thời điểm ApplicationStartedEvent

**ApplicationStartedEvent** là một sự kiện vòng đời do **Spring Boot** phát trong quá trình **SpringApplication.run(...)**. Nó cho biết **ApplicationContext đã refresh thành công**, nhưng **chưa có ApplicationRunner hoặc CommandLineRunner nào được SpringApplication gọi** trong giai đoạn runner của lần khởi động đó.

Đây là một ranh giới rất quan trọng:

- **Context đã refresh:** Spring đã hoàn thành bước refresh của ApplicationContext; những singleton không lazy thông thường đã được khởi tạo và các callback khởi tạo bean tương ứng đã chạy.
- **Các runner chưa chạy:** mọi tác vụ nạp cache, kiểm tra dependency, khởi tạo dữ liệu hoặc xác minh điều kiện startup được triển khai trong ApplicationRunner/CommandLineRunner vẫn còn ở phía sau.
- **Chưa thể kết luận ready:** việc phát ApplicationStartedEvent **không có nghĩa** service đã hoàn tất toàn bộ startup và sẵn sàng nhận request.
- **Không đồng nghĩa toàn bộ bean đã được tạo:** bean lazy vẫn có thể chưa khởi tạo. Những hoạt động bất đồng bộ, tác vụ nền hoặc kết nối bên ngoài cũng không được bảo đảm hoàn thành chỉ vì context đã refresh.

Sự kiện này được thiết kế để **quan sát mốc context đã bắt đầu hoạt động**, đo thời gian khởi động đến mốc started, ghi telemetry nhẹ hoặc triển khai hook cần một context đã refresh. Nếu cần hoàn thành nghiệp vụ bắt buộc **trước khi ứng dụng sẵn sàng**, Spring Boot khuyến nghị dùng runner thay vì đặt công việc nặng vào listener.

**Câu ghi nhớ:** *ApplicationStartedEvent = context refresh xong; các runner chưa được gọi. ApplicationReadyEvent = các runner đã chạy thành công; chuẩn bị công bố readiness.*

## 2. ApplicationStartedEvent nằm ở đâu trong chuỗi khởi động?

Với một lần khởi động Spring Boot thành công, thứ tự sự kiện chính là:

| Thứ tự | Sự kiện/mốc | Ý nghĩa |
| --- | --- | --- |
| 1 | ApplicationStartingEvent | Bắt đầu SpringApplication.run, trước phần lớn công việc bootstrap |
| 2 | ApplicationEnvironmentPreparedEvent | Environment đã được chuẩn bị; context chưa được tạo |
| 3 | ApplicationContextInitializedEvent | Context đã được tạo và các ApplicationContextInitializer đã chạy |
| 4 | ApplicationPreparedEvent | Các bean definitions đã được nạp; chuẩn bị refresh |
| 5 | Refresh ApplicationContext | Spring khởi tạo bean, xử lý dependency, lifecycle và hạ tầng phù hợp |
| 6 | **ApplicationStartedEvent** | **Refresh thành công; chưa gọi runner** |
| 7 | AvailabilityChangeEvent: LivenessState.CORRECT | Spring Boot công bố ứng dụng được coi là live |
| 8 | ApplicationRunner và CommandLineRunner | Thực hiện các tác vụ startup được đăng ký dưới dạng runner bean |
| 9 | ApplicationReadyEvent | Các runner hoàn tất theo nhánh thành công |
| 10 | AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC | Spring Boot công bố instance có thể nhận traffic |
| 11 | SpringApplication.run(...) trả về | Bên gọi nhận được ConfigurableApplicationContext |

Sơ đồ:

~~~text
ApplicationStartingEvent
        |
ApplicationEnvironmentPreparedEvent
        |
ApplicationContextInitializedEvent
        |
ApplicationPreparedEvent
        |
  refresh ApplicationContext
        |
        v
APPLICATION_STARTED_EVENT
        |
LivenessState.CORRECT
        |
ApplicationRunner / CommandLineRunner
        |
APPLICATION_READY_EVENT
        |
ReadinessState.ACCEPTING_TRAFFIC
        |
SpringApplication.run(...) returns
~~~

Sơ đồ được rút gọn để tập trung vào mốc started/runner/ready. **ContextRefreshedEvent** và **WebServerInitializedEvent** có thể xuất hiện trong quá trình refresh, trước ApplicationStartedEvent; thứ tự chi tiết của một số hoạt động nội bộ phụ thuộc loại context và web stack.

**Điểm không thể hoán đổi:** ApplicationStartedEvent phát sau refresh nhưng trước việc gọi các runner. Không dùng @Order để chuyển ApplicationReadyEvent lên trước runner hay chuyển runner lên trước ApplicationStartedEvent. Đó là thứ tự vòng đời của SpringApplication, không phải thứ tự của các bean tùy ý.

## 3. So sánh ApplicationStartedEvent với các mốc gần nó

| Mốc | Context đã refresh? | Runner đã chạy? | Ý nghĩa thực tế |
| --- | --- | --- | --- |
| @PostConstruct trên singleton không lazy | Chưa chắc; thường đang trong refresh | Chưa | Một bean vừa được inject và đang init |
| ContextRefreshedEvent | Có | Chưa trong luồng khởi động thông thường | Framework thông báo context đã refresh |
| **ApplicationStartedEvent** | **Có** | **Chưa** | **Mốc Spring Boot started** |
| ApplicationRunner/CommandLineRunner | Có | Đang thực hiện | Tác vụ cấp ứng dụng có thể dùng các service của context |
| ApplicationReadyEvent | Có | Đã hoàn tất theo nhánh thành công | Mốc ready của SpringApplication |
| ReadinessState.ACCEPTING_TRAFFIC | Có | Đã hoàn tất theo nhánh thành công | Trạng thái Spring Boot phục vụ readiness/health |

**ContextRefreshedEvent** là sự kiện của Spring Framework. **ApplicationStartedEvent** là sự kiện bổ sung của Spring Boot, xuất hiện ở mốc do SpringApplication điều phối sau refresh. Một lần chạy có thể có nhiều context, parent/child hierarchy hoặc quá trình refresh bổ sung; vì vậy không lấy số lần nhận event làm số lần khởi động toàn JVM khi không xét context nào phát.

**ApplicationStartedEvent không đồng nghĩa ApplicationReadyEvent.** Ví dụ web server đã bind cổng và một bean nhận ApplicationStartedEvent, nhưng runner vẫn đang nạp cache. Nếu load balancer định tuyến ngay khi TCP port mở mà không dùng readiness, request có thể đến trước khi dữ liệu cần thiết sẵn sàng.

## 4. Thông tin có trong ApplicationStartedEvent

Trong Spring Boot 3.x, lớp:

~~~java
org.springframework.boot.context.event.ApplicationStartedEvent
~~~

kế thừa **SpringApplicationEvent**. Những API hữu ích:

- **event.getApplicationContext()** trả về ConfigurableApplicationContext gắn với lần khởi động. Ở mốc này context đã refresh; tuy nhiên runner chưa chạy.
- **event.getTimeTaken()** trả về **Duration** đo thời gian SpringApplication mất để đến mốc started, hoặc **null** nếu thông tin không xác định được. Khi log nên kiểm tra null.
- **event.getSpringApplication()** và **event.getArgs()** được kế thừa từ SpringApplicationEvent; giúp biết SpringApplication và raw arguments liên quan.
- **event.getTimestamp()** là timestamp event của Spring; đây không phải một metric đo riêng thời gian runner.

Ví dụ listener dạng bean:

~~~java
@Component
class StartedLogger {
    @EventListener
    void whenStarted(ApplicationStartedEvent event) {
        Duration duration = event.getTimeTaken();
        System.out.println("Context refreshed");
        if (duration != null) {
            System.out.println("Startup so far (ms): " + duration.toMillis());
        }
    }
}
~~~

Đây là **đoạn minh họa**, cần import **java.time.Duration**, **org.springframework.stereotype.Component**, **org.springframework.context.event.EventListener**, **org.springframework.boot.context.event.ApplicationStartedEvent** và đặt trong project Spring Boot. Không nên so sánh một giá trị Duration cố định trên những máy khác nhau, vì nó biến động theo môi trường.

**Quan trọng:** thời gian tại ApplicationStartedEvent **chưa tính toàn bộ công việc runner**. Để đo mốc hoàn tất startup, xem ApplicationReadyEvent và quan sát thời gian end-to-end; để đo riêng tác vụ runner, dùng Timer/metric chuyên biệt xung quanh runner thay vì suy diễn từ thời gian started.

## 5. Đăng ký listener để nhận ApplicationStartedEvent

### 5.1. Dùng @EventListener trên Spring bean

Vì ApplicationStartedEvent xảy ra **sau refresh**, các listener bean thường đã được Spring tìm và đăng ký. Đây là cách gọn nhất khi code thuộc chính ứng dụng:

~~~java
@Component
class StartupObserver {

    @EventListener(ApplicationStartedEvent.class)
    public void onStarted() {
        System.out.println("ApplicationStartedEvent received");
    }
}
~~~

Nếu method nhận tham số ApplicationStartedEvent, có thể viết **@EventListener** không cần chỉ định class; Spring suy ra loại sự kiện từ tham số.

Các yếu tố cần chú ý:

- Class phải được component scan hoặc đăng ký bean đúng cách.
- Import **org.springframework.context.event.EventListener** và **org.springframework.boot.context.event.ApplicationStartedEvent**.
- Nếu viết method với event parameter, bạn có thể lấy ApplicationContext/Duration/args.
- Listener chạy theo event multicaster. Với cấu hình mặc định, quá trình gọi listener là **đồng bộ** trên thread phát sự kiện; đừng đặt thao tác network dài hay tác vụ bất định trong handler.

### 5.2. Đăng ký sớm bằng SpringApplication.addListeners(...)

Một ứng dụng có thể đăng ký **ApplicationListener<ApplicationStartedEvent>** trực tiếp vào SpringApplication:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners((ApplicationListener<ApplicationStartedEvent>) event ->
        System.out.println("started"));
app.run(args);
~~~

Đây là đoạn minh họa đặt trong main, với **MyApplication** là tên thay cho lớp cấu hình thực tế. Import ApplicationListener và ApplicationStartedEvent phù hợp. Cách này hữu ích cho thư viện hạ tầng hoặc khi muốn đăng ký listener trước khi khởi động. Một **ApplicationListener** có thể được đăng ký qua **META-INF/spring.factories** với key **org.springframework.context.ApplicationListener** nếu thư viện phải tự nạp từ classpath.

**Không nhầm ApplicationListener với SpringApplicationRunListener:** SpringApplicationRunListener là SPI cấp thấp có nhiều callback bắt đầu từ rất sớm và đăng ký bằng key riêng; ApplicationStartedEvent ở đây là một event, xử lý bởi listener của hệ thống event Spring. Với tác vụ nghiệp vụ thông thường, @EventListener hoặc runner dễ bảo trì hơn.

### 5.3. Các sự kiện sớm không thể phụ thuộc bean listener

**ApplicationStartingEvent** và **ApplicationEnvironmentPreparedEvent** xuất hiện trước khi bean của ApplicationContext sẵn sàng; để nghe các mốc sớm đó cần đăng ký listener từ trước qua addListeners, SpringApplicationBuilder hoặc spring.factories. Nhưng **ApplicationStartedEvent được phát sau refresh**, vì thế **@EventListener bean** phù hợp cho mốc này.

## 6. Ví dụ hoàn chỉnh Java 17+/Spring Boot 3.x

Ví dụ sau cố ý dùng cả **@PostConstruct**, **ApplicationStartedEvent**, **ApplicationRunner**, **CommandLineRunner** và **ApplicationReadyEvent** để nhìn thấy mốc nào đến trước mốc nào. Có thêm một nhánh lỗi để chứng minh ready không xuất hiện nếu runner fail.

### 6.1. Cấu trúc dự án

Tạo project Gradle Spring Boot 3.3.x, Java 17, với các tệp:

~~~text
started-event-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          StartedEventDemo.java
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'started-event-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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

Ví dụ sử dụng Gradle tương thích với Spring Boot 3.3 và JDK 17+. Nếu project đã có wrapper, dùng wrapper; nếu không, cần cài Gradle phiên bản phù hợp để chạy lệnh **gradle bootRun**. Dependencies/plugin phải có sẵn trong cache hoặc tải từ repository cấu hình.

### 6.2. Source Java hoàn chỉnh

Tệp **src/main/java/demo/StartedEventDemo.java**:

~~~java
package demo;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class StartedEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartedEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_AFTER_RUN");
        }
    }
}

@Component
class StartupState {
    private boolean started;
    private boolean workDone;

    @PostConstruct
    void initialize() {
        System.out.println("BEAN_INIT");
    }

    void markStarted() {
        started = true;
    }

    boolean isStarted() {
        return started;
    }

    void markWorkDone() {
        workDone = true;
    }

    boolean isWorkDone() {
        return workDone;
    }
}

@Component
class LifecycleObserver {
    private final StartupState state;

    LifecycleObserver(StartupState state) {
        this.state = state;
    }

    @EventListener
    public void afterContextRefresh(ApplicationStartedEvent event) {
        if (!event.getApplicationContext().isActive()) {
            throw new IllegalStateException("Context must be active");
        }
        state.markStarted();
        System.out.println("EVENT_STARTED");
    }

    @EventListener
    public void afterRunners(ApplicationReadyEvent event) {
        if (!state.isWorkDone()) {
            throw new IllegalStateException("Startup work must be completed");
        }
        System.out.println("EVENT_READY");
    }
}

@Component
@Order(10)
class WarmupRunner implements ApplicationRunner {
    private final StartupState state;

    WarmupRunner(StartupState state) {
        this.state = state;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!state.isStarted()) {
            throw new IllegalStateException("Started event not observed");
        }

        System.out.println("RUNNER_APPLICATION");

        if (args.containsOption("fail-runner")) {
            throw new IllegalStateException("Demo startup failure");
        }

        state.markWorkDone();
    }
}

@Component
@Order(20)
class FinalRunner implements CommandLineRunner {
    private final StartupState state;

    FinalRunner(StartupState state) {
        this.state = state;
    }

    @Override
    public void run(String... args) {
        if (!state.isWorkDone()) {
            throw new IllegalStateException("Warmup not complete");
        }
        System.out.println("RUNNER_COMMAND_LINE");
    }
}
~~~

**Những điểm bảo đảm:**

1. **StartupState** là singleton non-lazy thông thường; @PostConstruct in **BEAN_INIT** khi bean được tạo trong refresh.
2. **LifecycleObserver** nhận **ApplicationStartedEvent**, xác minh context đã active, đánh dấu **started=true** rồi in **EVENT_STARTED**.
3. **WarmupRunner** phải thấy cờ started trước khi làm việc; nếu listener chưa được gọi theo đúng thứ tự thì runner ném exception.
4. **@Order(10)** và **@Order(20)** sắp xếp hai runner; ApplicationRunner và CommandLineRunner tham gia cùng giai đoạn startup runners.
5. **LifecycleObserver** nhận **ApplicationReadyEvent** sau khi cả hai runner hoàn tất, kiểm tra workDone rồi in **EVENT_READY**.
6. Khi **app.run(args)** trả về thành công, main in **MAIN_AFTER_RUN**; khối try-with-resources sau đó đóng context.

### 6.3. Chạy và quan sát stdout

Với Gradle wrapper của project, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Các dòng **do chính source Java ví dụ in ra**, theo thứ tự, là:

~~~text
BEAN_INIT
EVENT_STARTED
RUNNER_APPLICATION
RUNNER_COMMAND_LINE
EVENT_READY
MAIN_AFTER_RUN
~~~

Spring Boot và Gradle có thể in log bổ sung tùy cấu hình; khối này không khẳng định toàn bộ stdout chỉ có sáu dòng. Điều quan trọng là **EVENT_STARTED xuất hiện trước cả hai RUNNER**, còn **EVENT_READY xuất hiện sau cả hai RUNNER**.

**Tại sao không cần sleep hoặc Thread.sleep để tạo thứ tự?** Vì đó là hợp đồng vòng đời SpringApplication. Ngay khi ApplicationStartedEvent được phát và listener mặc định xử lý đồng bộ xong, SpringApplication mới tiếp tục đến giai đoạn runner. Thời gian chạy của từng bước có thể thay đổi, nhưng trình tự mốc không phụ thuộc máy nhanh hay chậm.

### 6.4. Kiểm tra nhánh runner thất bại

Chạy:

~~~bash
./gradlew bootRun --args="--fail-runner"
~~~

Lần này, các dòng do source in ra trước khi exception được ném gồm:

~~~text
BEAN_INIT
EVENT_STARTED
RUNNER_APPLICATION
~~~

Sau đó WarmupRunner ném **IllegalStateException("Demo startup failure")**. Các dòng **RUNNER_COMMAND_LINE**, **EVENT_READY** và **MAIN_AFTER_RUN** không xuất hiện theo đường startup thành công. Spring Boot xử lý lỗi startup; Gradle có thể in stack trace và thông báo bootRun thất bại.

Điều này chứng minh một mốc **started** thành công **không đảm bảo** cả quá trình startup thành công. Nó cũng cho thấy **ApplicationReadyEvent** là mốc có ý nghĩa khác: các runner đã trở về thành công.

## 7. Sự kiện này liên quan thế nào đến liveness và readiness?

Spring Boot cung cấp các trạng thái **ApplicationAvailability** cho việc vận hành và probe.

- **LivenessState.CORRECT:** Spring Boot công bố trạng thái liveness ngay sau ApplicationStartedEvent trên đường startup bình thường. Nó phản ánh rằng context đã refresh thành công và ứng dụng được coi là live.
- **ReadinessState.ACCEPTING_TRAFFIC:** được công bố sau ApplicationReadyEvent, tức sau khi startup runners được gọi và hoàn tất theo đường thành công.
- Trước khi runner xong, **đừng suy luận readiness là ACCEPTING_TRAFFIC** chỉ vì đã thấy ApplicationStartedEvent hoặc web server đã lắng nghe cổng.

Dòng thời gian gọn:

~~~text
Context refreshed
      |
ApplicationStartedEvent
      |
LivenessState.CORRECT
      |
Runners (co the mat nhieu thoi gian)
      |
ApplicationReadyEvent
      |
ReadinessState.ACCEPTING_TRAFFIC
~~~

**Liveness khác readiness.** Một instance có thể “sống” (context hoạt động) nhưng chưa đủ dữ liệu/cache để phục vụ request. Trong Kubernetes, nên phối hợp startup/readiness/liveness probe phù hợp, dùng Actuator readiness khi đã cấu hình hỗ trợ và bảo đảm bên điều phối không gửi traffic quá sớm.

**Không nên gắn liveness vào trạng thái dependency bên ngoài** như database hoặc API từ xa mà không phân tích tác dụng: một dependency dùng chung lỗi có thể khiến nhiều Pod restart cùng lúc, tạo hiệu ứng dây chuyền. Readiness hoặc health có thể phản ánh khả năng phục vụ theo hợp đồng ứng dụng.

## 8. Nên xử lý công việc gì trong ApplicationStartedEvent?

### Phù hợp

- Ghi log mốc context đã refresh.
- Phát metric hoặc tracing nhẹ về startup.
- Quan sát cấu hình context, bean definition hoặc kết quả refresh ở mức chỉ đọc.
- Đo Duration từ ApplicationStartedEvent.getTimeTaken() khi muốn có **thời gian đến mốc started**, lưu ý giá trị có thể null.
- Theo dõi vòng đời trong các công cụ monitoring/diagnostics.

### Nên chuyển sang runner

- Nạp cache bắt buộc trước khi ứng dụng nhận traffic.
- Xác minh một số dependency quan trọng qua service được inject.
- Kiểm tra/sửa dữ liệu khởi tạo với transaction và idempotency.
- Xử lý tham số CLI để quyết định startup task.
- Chạy một thao tác có thể thất bại và cần được xem là lỗi startup trước ready.

Spring Boot khuyến nghị công việc startup thực sự nên thực hiện bằng **ApplicationRunner hoặc CommandLineRunner**, không đặt trong callback khởi tạo bean hoặc listener dài. Dù có thể làm việc đó trong @EventListener(ApplicationStartedEvent.class), cách ấy khiến mục đích của event và trách nhiệm business bị trộn, khó kiểm soát thứ tự và thời gian chờ.

### Nên chọn cơ chế khác

- **@PostConstruct/initMethod** cho khởi tạo state nhỏ gắn với chính bean.
- **SmartLifecycle** cho consumer/background component cần start/stop rõ ràng.
- **@Scheduled** cho công việc định kỳ sau khi service đã chạy.
- **ApplicationReadyEvent** cho ghi nhận sự kiện/metric nhẹ sau runner, không phải một tác vụ bắt buộc phải chạy trước ready.
- **Flyway/Liquibase** cho migration schema có phiên bản, thay vì tự viết runner sửa schema theo cách khó kiểm soát.

## 9. Xử lý lỗi khi listener hoặc runner ném exception

| Điểm phát sinh lỗi | Hệ quả thường gặp |
| --- | --- |
| Bean @PostConstruct ném exception trong refresh | Context refresh thất bại; không tới ApplicationStartedEvent |
| Listener đồng bộ xử lý ApplicationStartedEvent ném exception | SpringApplication có thể rẽ sang startup failure trước khi runner được gọi |
| ApplicationRunner/CommandLineRunner ném exception | ApplicationStartedEvent đã có thể xảy ra; ApplicationReadyEvent không phát theo đường thành công |
| Listener ApplicationReadyEvent ném exception | Startup có thể rẽ sang failure handling ngay giai đoạn ready; không nên dùng listener này cho nghiệp vụ nặng |
| Một tác vụ @Async được khởi động từ listener rồi lỗi sau đó | Lỗi không tự động trở thành exception đồng bộ của SpringApplication.run(...); phải có giám sát và xử lý riêng |
| Request HTTP lỗi sau khi ứng dụng đã ready | Đây là lỗi runtime, không mặc nhiên là startup failure |

**Điểm cần làm rõ về đồng bộ:** mặc định Spring Framework sử dụng cơ chế phát sự kiện đồng bộ, nên listener chạy trong luồng gửi sự kiện; vì vậy lỗi listener đồng bộ có thể ảnh hưởng trực tiếp đến startup. Nếu listener được đánh dấu **@Async**, hoặc multicaster được cấu hình chạy bất đồng bộ, việc *phát event* vẫn diễn ra theo mốc lifecycle nhưng **thời điểm hoàn tất xử lý trong listener có thể muộn hơn runner**. Khi đó không được dùng một callback async để bảo đảm runner đợi xong việc.

**Không nên nuốt lỗi bắt buộc:** nếu warm up bắt buộc mà runner chỉ catch rồi log, ứng dụng có thể tiếp tục phát ApplicationReadyEvent dù dữ liệu chưa hợp lệ. Ngược lại, một metric exporter tạm thời lỗi không nhất thiết phải làm cả service fail; nên có timeout và cơ chế cách ly lỗi cho quan sát.

**Dọn dẹp:** khi SpringApplication gặp lỗi startup, nó xử lý lỗi và đóng ApplicationContext nếu đã có; những resource đã đăng ký lifecycle của bean được dọn theo khả năng của container. Nhưng file, message, API call và dữ liệu ngoài context không tự hoàn tác; nếu runner có tác dụng phụ thì cần transaction, compensation, idempotency và rollback phù hợp.

## 10. Lưu ý về thứ tự listener, thứ tự runner và nhiều context

### @Order của listener không thay thế @Order của runner

Một ứng dụng có thể có nhiều listener nhận ApplicationStartedEvent. **@Order/Ordered** có thể điều khiển thứ tự giữa các listener cùng nhận event. Cùng lúc đó, **ApplicationRunner** và **CommandLineRunner** được sắp thứ tự theo cơ chế **@Order/Ordered của các runner bean**. Hai thứ tự đó là hai nhóm riêng:

~~~text
ApplicationStartedEvent
  Listener A (order 10)
  Listener B (order 20)
       |
  Runner X (order 10)
  Runner Y (order 20)
       |
ApplicationReadyEvent
~~~

Không thể đặt @Order(-1000) cho một runner rồi mong nó chạy trước ApplicationStartedEvent. Mốc lifecycle luôn có thứ tự của nó. Nếu các runner có cùng order, tránh dựa vào thứ tự phát hiện bean hoặc tên lớp để đưa ra logic nghiệp vụ bắt buộc.

### Parent/child ApplicationContext và event bubbling

Spring Framework có thể chuyển sự kiện từ **child context** lên các **parent context**. Khi ứng dụng có nhiều SpringApplication/context hierarchy, một listener có thể nhận nhiều sự kiện cùng loại từ những context khác nhau. Để giới hạn việc xử lý:

~~~java
if (event.getApplicationContext() != myApplicationContext) {
    return;
}
~~~

Đây là đoạn minh họa trong listener, cần có **myApplicationContext** được inject/quản lý phù hợp. So sánh theo **identity của context** thay vì mặc định “một JVM chỉ có một ApplicationStartedEvent”. Với hầu hết ứng dụng Boot một context, logic này không cần thiết.

### Không nhầm event với dòng log “Started ...”

Log “Started ... in ... seconds” của Spring Boot và ApplicationStartedEvent đều liên quan giai đoạn context refresh, nhưng không dùng string log làm API điều phối nghiệp vụ. Format log có thể thay đổi do version, logging config và thời điểm framework in log. Muốn phản ứng theo lifecycle, hãy dùng event hoặc runner đúng contract.

## 11. Những nhầm lẫn thường gặp

**1. “ApplicationStartedEvent nghĩa là mọi runner đã chạy.”** Sai. Nó xuất hiện **trước** runner.

**2. “ApplicationStartedEvent nghĩa là ứng dụng sẵn sàng nhận HTTP traffic.”** Sai. Runner và ReadinessState.ACCEPTING_TRAFFIC còn ở phía sau.

**3. “Chỉ cần web server đã bind port là có thể gửi request nghiệp vụ.”** Chưa đủ. Có thể đang preload cache, chạy validation hoặc seeding trong runner.

**4. “Event xảy ra trước khi ApplicationContext được tạo.”** Sai. ApplicationStartedEvent xuất hiện **sau** refresh; các event rất sớm là ApplicationStartingEvent và ApplicationEnvironmentPreparedEvent.

**5. “Mọi @PostConstruct đều đã chạy khi started được phát.”** Không hoàn toàn. Singleton không lazy bình thường được tạo trong refresh, nhưng bean lazy có thể chưa khởi tạo.

**6. “getTimeTaken() của started là tổng startup time đến ready.”** Sai. Nó đo thời gian đến mốc started, không bao gồm toàn bộ thời gian runner; giá trị còn có thể null.

**7. “@Order của runner có thể đổi thứ tự sự kiện started/ready.”** Sai. Nó chỉ sắp thứ tự các runner.

**8. “Listener @Async vẫn hoàn tất trước runner vì event được phát trước.”** Không chắc. Phát event trước khác với listener async xử lý xong trước.

**9. “Nếu listener Started đã in log thì startup chắc chắn không thể fail.”** Sai. Runner tiếp theo vẫn có thể ném exception và ngăn nhánh ready.

**10. “ApplicationReadyEvent tương tự ApplicationStartedEvent.”** Sai. Chúng bảo đảm những mốc khác nhau; chỉ Ready đến sau runner.

**11. “Một context hierarchy chỉ phát đúng một event Started.”** Không nên giả định. Spring có thể có parent/child context và cơ chế event propagation; lọc theo context nếu cần.

**12. “Muốn chạy database migration thì đặt ngay vào listener Started.”** Không nên. Dùng Flyway/Liquibase hoặc cơ chế startup được thiết kế cho migration, có transaction/version và điều phối nhiều instance.

## 12. Checklist thiết kế và vận hành

Trước khi dùng ApplicationStartedEvent, kiểm tra:

1. **Mục tiêu:** đây là quan sát mốc started hay một công việc khởi động bắt buộc?
2. **Context:** listener có cần bean không? Nếu dùng @EventListener, bean đã được đăng ký và scope có phù hợp không?
3. **Runner:** những runner nào có thể chạy sau event, có cần chờ nhau bằng @Order hoặc dependency rõ ràng không?
4. **Readiness:** hệ thống nhận traffic bằng điều kiện gì, có đợi Ready/health probe phù hợp không?
5. **Đồng bộ:** listener chạy mặc định đồng bộ hay đã bật @Async/multicaster async?
6. **Exception:** lỗi listener/runner cần fail startup hay chỉ ghi cảnh báo? Có đang vô tình nuốt lỗi quan trọng không?
7. **Thời gian:** thao tác trong listener có làm tăng startup latency? Nên đo Duration của started hay ready, hay metric runner riêng?
8. **Resource:** nếu runner hoặc listener mở kết nối/file/thread, ai chịu trách nhiệm đóng khi lỗi?
9. **Multi-instance:** runner có được chạy lại khi Pod restart hoặc scale-out không, đã idempotent chưa?
10. **Kiểm thử:** đã thử nhánh runner fail và xác nhận ApplicationReadyEvent không xảy ra theo đường thành công chưa?

Một quyết định tốt thường là **listener ApplicationStartedEvent cho tín hiệu “refresh xong”**, **runner cho “việc bắt buộc trước ready”**, và **ApplicationReadyEvent/availability cho “đã hoàn tất startup và có thể phục vụ”**.

## 13. Câu hỏi tự kiểm tra

**Câu 1. ApplicationStartedEvent xảy ra trước hay sau ApplicationContext.refresh()?**  
Sau khi context đã refresh thành công.

**Câu 2. ApplicationStartedEvent xảy ra trước hay sau ApplicationRunner?**  
Trước các runner được SpringApplication gọi.

**Câu 3. Vì sao không thể coi ApplicationStartedEvent là readiness?**  
Vì runner có thể đang chạy, đang lỗi hoặc chưa bắt đầu; ReadinessState.ACCEPTING_TRAFFIC được công bố ở mốc muộn hơn.

**Câu 4. Một @EventListener(ApplicationStartedEvent.class) có thể inject service bean không?**  
Có, nếu nó nằm trong một bean đã được Spring quản lý trong context đã refresh. Vẫn cần xét bean lazy và tác dụng phụ startup.

**Câu 5. Nếu runner ném exception sau ApplicationStartedEvent, ApplicationReadyEvent có xảy ra không?**  
Không trong nhánh khởi động thành công. SpringApplication xử lý startup failure.

**Câu 6. Nếu listener Started khởi động một CompletableFuture rồi trả về ngay, runner có đợi Future không?**  
Không tự động. Cần thiết kế chờ kết quả/timeout hoặc chuyển công việc bắt buộc sang runner đồng bộ.

**Câu 7. @Order(10) của CommandLineRunner có giúp nó chạy trước listener Started order(20) không?**  
Không. @Order không đổi thứ tự lifecycle event và runner.

**Câu 8. getTimeTaken() trong ApplicationStartedEvent đo cả runner chưa?**  
Không. Nó mô tả thời gian đến mốc started; có thể null.

**Câu 9. Nếu context có parent và child, tại sao một listener nhận nhiều Started event?**  
Do nhiều context/lần SpringApplication và event có thể được chuyển lên parent; cần xét source context.

**Câu 10. Muốn ghi metric nhẹ ngay sau refresh, nên dùng gì?**  
Listener ApplicationStartedEvent với công việc ngắn, không blocking và không phụ thuộc vào runner đã hoàn tất.

**Ghi nhớ cuối cùng:** **ApplicationStartedEvent nằm chính xác giữa “context refresh thành công” và “chạy các ApplicationRunner/CommandLineRunner”**. Nó hữu ích để quan sát startup nhưng **chưa bảo đảm ứng dụng ready**. Hãy chọn runner cho việc phải hoàn tất trước khi nhận traffic, và dùng ApplicationReadyEvent/readiness cho tín hiệu ứng dụng đã qua startup thành công.

### Tài liệu tham khảo

- [Spring Boot — SpringApplication: Application Events and Listeners, Availability, Runners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 3.3 API — ApplicationStartedEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
- [Spring Boot 3.3 API — ApplicationReadyEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
- [Spring Boot 3.3 API — ApplicationRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Framework — Application Events and EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
