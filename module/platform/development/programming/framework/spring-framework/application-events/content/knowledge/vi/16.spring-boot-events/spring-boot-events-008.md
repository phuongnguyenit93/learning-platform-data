# ApplicationFailedEvent trong Spring Boot application events

## 1. ApplicationFailedEvent là gì?

**ApplicationFailedEvent** là một **Spring Boot application event** được **SpringApplication** phát khi quá trình **khởi động ứng dụng** thất bại vì exception. Kiểu đầy đủ là **org.springframework.boot.context.event.ApplicationFailedEvent**, kế thừa **SpringApplicationEvent**.

Mục đích chính của sự kiện là cho phép một thành phần được đăng ký đủ sớm **quan sát lỗi startup**, ghi thông tin chẩn đoán hoặc phát tín hiệu thất bại ngắn gọn trước khi tiến trình thoát hay startup được báo lỗi lên caller. Ví dụ: khởi tạo ApplicationContext gặp lỗi bean, binding cấu hình thất bại, không thể mở cổng web server hoặc **CommandLineRunner** ném exception trong lúc SpringApplication.run(...) vẫn đang thực hiện startup.

Các điểm cần nhớ:

- **Sự kiện gắn với startup do SpringApplication điều phối**. Nó không phải sự kiện chung cho mọi exception xảy ra bất kỳ lúc nào trong JVM.
- Listener có thể đọc nguyên nhân qua **event.getException()**.
- **event.getApplicationContext() có thể trả về null** nếu lỗi xảy ra trước khi context được tạo; khi khác null, context cũng có thể **chưa refresh thành công hoặc đang được đóng**.
- Listener phải được **đăng ký sớm**, vì Spring Boot có thể lỗi trước khi các bean và phương thức **@EventListener** được khởi tạo.
- Sự kiện giúp quan sát lỗi; **không tự khởi động lại ứng dụng, rollback mọi side effect hoặc bảo đảm gửi cảnh báo bền vững**.

Một hệ thống production thường đã có logging khởi động của Spring Boot và error output. ApplicationFailedEvent hữu ích khi cần một **tín hiệu có cấu trúc** cho giám sát, phân loại lỗi hoặc một bước cleanup đơn giản bên ngoài cơ chế bean thông thường.

## 2. ApplicationFailedEvent xuất hiện ở giai đoạn nào của startup?

**SpringApplication.run(...)** thực hiện các bước: tạo và chuẩn bị environment, tạo ApplicationContext, nạp bean definitions, refresh context, chạy các runner và hoàn tất việc đánh dấu ứng dụng sẵn sàng. Nếu một exception khiến quy trình đó không hoàn tất bình thường, Spring Boot có thể phát **ApplicationFailedEvent** qua đường xử lý startup failure.

Một chuỗi startup thành công điển hình:

~~~text
SpringApplication.run(...)
    |
    v
ApplicationStartingEvent
    |
    v
ApplicationEnvironmentPreparedEvent
    |
    v
ApplicationContextInitializedEvent
    |
    v
ApplicationPreparedEvent
    |
    v
Context refresh
    |
    v
ApplicationStartedEvent
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
ApplicationReadyEvent
    |
    v
ReadinessState.ACCEPTING_TRAFFIC
~~~

Nếu có lỗi ở các bước startup phù hợp, nhánh thất bại thay thế việc hoàn tất bình thường:

~~~text
SpringApplication.run(...)
    |
    +-- lỗi chuẩn bị environment/context
    |       hoặc refresh bean/server
    |       hoặc gọi runner
    |
    v
SpringApplication xử lý startup failure
    |
    +-- thông báo ApplicationFailedEvent đến listener đã đăng ký
    +-- ghi nhận/phân tích lỗi và dọn dẹp context khi cần
    +-- ném lỗi ra cho caller / startup kết thúc thất bại
~~~

**Không hiểu danh sách sự kiện như một lời hứa rằng ApplicationFailedEvent luôn xảy ra trước ApplicationStartedEvent.** Nếu một **CommandLineRunner** hoặc **ApplicationRunner** ném lỗi, context đã refresh và **ApplicationStartedEvent** có thể đã phát trước đó; **ApplicationReadyEvent** thì chưa đến. Ngược lại, nếu lỗi phát sinh rất sớm, ApplicationContext chưa tồn tại.

Nếu ứng dụng đã sẵn sàng phục vụ rồi mới gặp exception trong request HTTP, scheduled job hoặc consumer, **ApplicationFailedEvent thường không được Spring Boot tự phát lại**. Lỗi vận hành sau startup thuộc cơ chế exception handling, logging, metrics, health/availability và giám sát riêng.

## 3. Dữ liệu mà listener có thể đọc

Các API quan trọng của **ApplicationFailedEvent**:

| API | Ý nghĩa | Cách dùng an toàn |
| --- | --- | --- |
| **getException()** | **Throwable** gây startup failure | Ghi class lỗi, message, cause chain/stack trace có kiểm soát; tránh lộ thông tin nhạy cảm |
| **getApplicationContext()** | **ConfigurableApplicationContext** đang được tạo, hoặc **null** | Luôn kiểm tra null; không giả định context đã refresh |
| **getSpringApplication()** | **SpringApplication** liên quan lần chạy | Dùng để nhận diện nguồn startup trong công cụ hạ tầng nếu thật sự cần |
| **getArgs()** | Mảng command-line arguments đã truyền lúc run | Có thể chứa token/mật khẩu; không log nguyên văn theo mặc định |
| **getTimestamp()** | Thời điểm tạo event từ lớp ApplicationEvent | Hữu ích cho timestamp, nhưng không thay trace/metric chuẩn |

Ví dụ trích xuất lỗi với kiểm tra null:

~~~java
@Override
public void onApplicationEvent(ApplicationFailedEvent event) {
    Throwable error = event.getException();
    ConfigurableApplicationContext context = event.getApplicationContext();

    String contextId = context != null ? context.getId() : "<not-created>";
    System.err.println("Startup failed in " + contextId
            + " with " + error.getClass().getSimpleName());
}
~~~

Đây là **method minh họa** đặt trong một class implements **ApplicationListener<ApplicationFailedEvent>**, với import của Spring tương ứng. Không nên từ listener thất bại gọi **context.getBean(...)** bừa bãi: BeanFactory có thể mới khởi tạo một phần hoặc đã bước vào cleanup.

Khi phân tích nguyên nhân thực, exception bọc ngoài có thể là **BeanCreationException**, **UnsatisfiedDependencyException**, lỗi port hoặc lỗi runner. Có thể xem **getCause()** nhiều tầng, nhưng không chỉ dựa vào **getMessage()** để phân loại vì message và wrapper có thể thay đổi theo phiên bản/nhánh code.

## 4. Đăng ký listener đủ sớm: điểm quan trọng nhất

### 4.1. Đăng ký bằng SpringApplication.addListeners(...)

Cách rõ ràng nhất là tạo **SpringApplication** và thêm listener **trước khi gọi run(...)**:

~~~java
SpringApplication application = new SpringApplication(MyBootApplication.class);
application.addListeners(new StartupFailureListener());
application.run(args);
~~~

Đây là **đoạn minh họa**; cần có các class tương ứng. **StartupFailureListener** nên triển khai **ApplicationListener<ApplicationFailedEvent>** để Spring xác định loại event.

Ưu điểm:

- Listener có sẵn trước các bước tạo context và refresh bean.
- Có thể quan sát thất bại ngay cả khi **@Component**/**@Bean** không bao giờ được tạo.
- Không buộc listener phụ thuộc dependency injection trong một context đang lỗi.
- Mỗi instance SpringApplication có danh sách listeners rõ ràng.

Một số thư viện có thể sử dụng **SpringApplicationBuilder.listeners(...)**, hoặc đăng ký qua cơ chế startup mở rộng của framework. Điều cần bảo toàn vẫn là **listener được thêm trước khi run**.

### 4.2. Đăng ký qua META-INF/spring.factories

Khi muốn một listener hạ tầng được tự động áp dụng cho các ứng dụng sử dụng một thư viện, Spring Boot hỗ trợ cấu hình **META-INF/spring.factories**. Ví dụ nội dung file:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.startup.StartupFailureListener
~~~

**StartupFailureListener** trong thư viện cần là class có thể khởi tạo phù hợp và implements **ApplicationListener<ApplicationFailedEvent>**. Dòng trên là cấu hình minh họa với class được giả định tồn tại; không phải một dự án hoàn chỉnh.

Đối với một ứng dụng nhỏ, **addListeners(...)** thường dễ quan sát hơn. Đối với starter/thư viện muốn bắt lỗi rất sớm mà không phụ thuộc cách người dùng gọi SpringApplication.run(...), **spring.factories** có thể phù hợp. Đừng nhầm cơ chế đăng ký listener này với việc tự động đăng ký cấu hình bằng các import auto-configuration mới hơn.

### 4.3. Vì sao chỉ dùng @EventListener trong @Component không đáng tin cho startup failure?

Ví dụ sau hợp lệ về mặt method listener khi bean đã tồn tại:

~~~java
@Component
class LateFailureObserver {
    @EventListener
    public void on(ApplicationFailedEvent event) {
        // Chỉ có cơ hội chạy nếu listener bean đã được đăng ký đúng lúc.
    }
}
~~~

Nhưng **đây không phải giải pháp bảo đảm bắt mọi lỗi startup**. Nếu failure xảy ra trước khi Spring tạo context, nạp bean definitions hoặc hoàn tất đăng ký event listener adapter, bean chưa thể nhận event. Ngay cả khi context đã từng tồn tại, listener bean có thể bị ảnh hưởng bởi lỗi refresh/cleanup.

**Quy tắc:** listener giám sát thất bại lúc khởi động nên được đăng ký ở **SpringApplication-level** trước **run(...)**. Các bean **@EventListener** thông thường phù hợp hơn cho event sau khi context đã được thiết lập thành công.

## 5. Ví dụ Java 17+ chạy độc lập: cố ý làm startup thất bại

Ví dụ sau sử dụng **Spring Boot 3.5.8** và **Java 17+**. Nó tạo một **SpringApplication** dạng non-web, gắn listener trước **run(...)** và thêm **ApplicationContextInitializer** cố ý ném exception. Cách gây lỗi này giúp ví dụ ổn định mà không cần database hoặc web server.

Cấu trúc:

~~~text
startup-failure-demo/
  build.gradle
  src/main/java/demo/FailedStartupDemo.java
~~~

Nội dung **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter:3.5.8'
}

application {
    mainClass = 'demo.FailedStartupDemo'
}
~~~

Nội dung **src/main/java/demo/FailedStartupDemo.java**:

~~~java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class FailedStartupDemo {

    static final class StartupFailureListener
            implements ApplicationListener<ApplicationFailedEvent> {

        @Override
        public void onApplicationEvent(ApplicationFailedEvent event) {
            Throwable error = event.getException();
            System.out.println("event: " + error.getClass().getSimpleName());
            System.out.println("message: " + error.getMessage());
            System.out.println("context-created: "
                    + (event.getApplicationContext() != null));
        }
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(FailedStartupDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Đăng ký listener TRƯỚC khi khởi chạy SpringApplication.
        application.addListeners(new StartupFailureListener());

        // Cố ý thất bại sau khi context được tạo,
        // nhưng trước khi context được refresh thành công.
        application.addInitializers(context -> {
            throw new IllegalStateException("demo-bootstrap-failed");
        });

        try {
            application.run(args);
        } catch (IllegalStateException ex) {
            System.out.println("caller: " + ex.getMessage());
        }
    }
}
~~~

Từ thư mục **startup-failure-demo**, với JDK 17+ và Gradle 8.x:

~~~bash
gradle --console=plain -q run
~~~

**Các dòng do chương trình tự in ra**, theo thứ tự (Spring Boot cũng có thể ghi thêm log lỗi tùy cấu hình logging):

~~~text
event: IllegalStateException
message: demo-bootstrap-failed
context-created: true
caller: demo-bootstrap-failed
~~~

Diễn giải:

1. **StartupFailureListener** được đưa vào SpringApplication trước **run(...)**.
2. SpringApplication tạo context; khi gọi **ApplicationContextInitializer**, initializer ném **IllegalStateException** có message **demo-bootstrap-failed**.
3. SpringApplication đi vào đường xử lý startup failure và phát **ApplicationFailedEvent**; listener đọc **getException()** và thấy context **khác null** trong tình huống này vì context đã được tạo.
4. Lỗi gốc tiếp tục được ném cho caller. Khối **catch** trong **main(...)** cố ý bắt lỗi để minh họa rằng event **không nuốt** exception; chương trình demo có thể kết thúc bình thường vì main đã bắt exception.
5. Trong một ứng dụng thật không có catch tương tự, **run(...)** không trả về một context sẵn sàng sau lỗi. Không biến catch thành hành vi tuyên bố “startup thành công”.

Điểm quan trọng về QA: ví dụ này tạo lỗi ở **initializer** nên listener được đăng ký đủ sớm, **context-present** là true theo đường đi cụ thể. Khi lỗi sớm hơn giai đoạn tạo context, **getApplicationContext()** có thể null. Khi lỗi ở runner, wrapper exception và dữ liệu ngữ cảnh có thể khác; không sao chép cứng output này để đoán mọi lỗi Boot.

**Không khuyến khích dùng System.out cho production alert.** Đây là công cụ dạy lifecycle. Trong production, dùng logger/sink được khởi tạo sớm hoặc cơ chế giám sát quá trình triển khai, kèm timeout và xử lý lỗi của chính listener.

## 6. Tình huống getApplicationContext() null và khác null

| Nơi failure xảy ra | Context đã có chưa? | Cách phản ứng |
| --- | --- | --- |
| Tại những bước cực sớm trước khi context được tạo | **Có thể null** | Chỉ dựa vào exception và hạ tầng logging độc lập |
| Trong lúc chuẩn bị/refresh context | Thường đã tạo nhưng **chưa sẵn sàng** | Có thể nhận ID nếu an toàn; tránh tra cứu thêm bean |
| Khi tạo bean/datasource hoặc khởi động web server | Context có thể tồn tại ở trạng thái lỗi | Dùng exception/cause chain để tìm nguyên nhân; không tiếp tục sử dụng context |
| Khi chạy ApplicationRunner/CommandLineRunner | Context thường đã refresh | Lỗi vẫn thuộc startup; Boot xử lý failure và cleanup, không phải “ready” |
| Trong request HTTP sau khi app đã ready | Không phải đường startup failure thông thường | Dùng xử lý lỗi runtime, metrics, tracing và health/availability |

**Nullable không đồng nghĩa rằng mỗi loại lỗi luôn tạo một giá trị cố định.** Nhiều bước khởi động chứa xử lý phụ và extension points; phải coi context là có thể null và luôn kiểm tra trạng thái trước khi truy cập.

## 7. Liên hệ với ApplicationStartedEvent và ApplicationReadyEvent

Một hiểu nhầm phổ biến: nếu thấy **ApplicationStartedEvent** thì startup chắc chắn thành công. Điều đó không đúng.

- **ApplicationStartedEvent** được phát **sau khi context refresh**, nhưng **trước khi** chạy các runner.
- **ApplicationReadyEvent** được phát muộn hơn, **sau các ApplicationRunner/CommandLineRunner** khi quá trình startup bình thường đã hoàn tất.
- **ApplicationFailedEvent** báo một nhánh **startup bị lỗi**, kể cả lỗi trong runner, do đó nó có thể đến **sau ApplicationStartedEvent** ở một số kịch bản.
- **AvailabilityChangeEvent** và readiness/liveness phản ánh trạng thái phục vụ của ứng dụng; chúng có vai trò khác với sự kiện lỗi startup.

Ví dụ:

~~~text
context refresh thành công
    |
    v
ApplicationStartedEvent
    |
    v
CommandLineRunner chạy
    |
    +--> ném IllegalStateException
              |
              v
        ApplicationFailedEvent
              |
              v
      không có ApplicationReadyEvent
~~~

Nếu cần đánh dấu “ứng dụng có thể nhận lưu lượng”, đừng chỉ dựa vào context đã được tạo hoặc **ApplicationStartedEvent**. Theo dõi readiness/health chính thức của nền tảng và trường hợp startup thất bại.

## 8. Phân biệt ApplicationFailedEvent với lỗi runtime

**ApplicationFailedEvent** là một quan sát của **SpringApplication.run(...)**. Nó không tự phát cho mọi exception bị ném từ:

- **@RestController** khi ứng dụng đã phục vụ request.
- **@Scheduled** task chạy sau lúc ứng dụng ready.
- **@Async** method báo exception trên executor.
- Kafka/RabbitMQ/JMS listener đang tiêu thụ message sau startup.
- Một thread do ứng dụng tự quản lý gặp lỗi sau khi SpringApplication.run đã hoàn tất.

Với lỗi runtime, nên dùng cơ chế đúng lớp: **@ControllerAdvice**, error handler của messaging listener, **AsyncUncaughtExceptionHandler**, retry/dead-letter, logging, tracing, metrics và health/availability. Cố tự publish **new ApplicationFailedEvent(...)** để đại diện cho một lỗi runtime có thể làm sai ngữ nghĩa lifecycle của Spring Boot.

**Ngoại lệ có thể xảy ra trong các callback startup** như **ApplicationRunner** hoặc **CommandLineRunner** vẫn là lỗi startup nếu nó làm **SpringApplication.run(...)** thất bại.

## 9. ApplicationFailedEvent và FailureAnalyzer khác nhau như thế nào?

Spring Boot có **FailureAnalyzer** và các cơ chế **FailureAnalysisReporter** để diễn giải một số loại startup exception thành thông báo dễ hiểu như “cổng đã được dùng” kèm hướng sửa.

| Cơ chế | Mục đích chính | Khi nào dùng? |
| --- | --- | --- |
| **ApplicationFailedEvent listener** | Quan sát sự kiện startup thất bại và exception, tích hợp telemetry/giám sát | Khi cần một hook chung cho lỗi startup |
| **FailureAnalyzer** | Nhận diện loại exception cụ thể, tạo **description** và **action** rõ ràng | Khi xây thư viện/starter muốn người dùng thấy chỉ dẫn sửa lỗi |
| **FailureAnalysisReporter** | Trình bày kết quả phân tích lỗi | Khi cần tùy biến cách xuất báo cáo |
| **Logging/exception propagation** | Giữ stack trace và trạng thái startup thất bại | Phải được duy trì ngay cả khi custom listener tồn tại |

Ví dụ: Nếu một cấu hình thư viện thiếu property, **FailureAnalyzer** thường phù hợp để nói “cần cấu hình property X” và cách sửa. Nếu muốn gửi metric **startup.failure** với nhãn deployment/version, một listener đăng ký sớm phù hợp.

Không để custom listener che lấp thông báo lỗi gốc. Listener nên chạy nhanh, không ném thêm lỗi trừ khi thật sự có hợp đồng rõ, và không phụ thuộc vào những bean có thể đã thất bại.

## 10. Chính sách logging, bảo mật và độ tin cậy

### 10.1. Chỉ ghi thông tin cần thiết

Thông tin nên ghi:

- Timestamp và môi trường triển khai (từ cấu hình logging độc lập, nếu có).
- Class/loại exception và cause gốc đã được kiểm tra.
- Mã lỗi/nhóm lỗi có số lượng nhãn giới hạn.
- Phiên bản build, instance ID và correlation ID phù hợp.

Tránh log **toàn bộ event.getArgs()** hoặc giá trị các environment properties vì command-line arguments có thể chứa mật khẩu, token, URL có credential hoặc thông tin người dùng. Stack trace cũng có thể chứa đường dẫn hoặc dữ liệu nội bộ; áp dụng chính sách redact phù hợp.

### 10.2. Không gọi BeanFactory trong context lỗi một cách tùy tiện

Tại startup failure, bean factory có thể đang ở trạng thái tạo dở hoặc shutdown. Một listener chỉ tồn tại để ghi log không nên gọi **getBean(...)**, yêu cầu transaction manager mở giao dịch mới hay gửi sự kiện phụ thuộc vào bean vừa gây lỗi.

Nếu cần xuất cảnh báo, dùng một dependency độc lập với ApplicationContext; đặt timeout ngắn, tránh retry vô hạn và dự liệu cả sink giám sát bị lỗi.

### 10.3. Listener không thể bảo đảm báo động luôn đến nơi

Quá trình khởi động có thể bị **SIGKILL**, native crash, OOM cực sớm hoặc hệ thống ngắt trước khi SpringApplication phát event. Ngay cả khi listener chạy, ứng dụng vẫn có thể tắt trước khi một tác vụ async kịp gửi dữ liệu.

Đối với SLO và hoạt động vận hành, hãy kết hợp:

- Exit status của process/container.
- Log startup và stderr từ runtime.
- Readiness/health probes và chính sách restart của orchestrator.
- Startup failure metrics/alerts do nền tảng giám sát thu thập.
- Listener như một tín hiệu bổ sung, không phải nguồn duy nhất.

### 10.4. Listener cũng có thể thất bại

Nếu listener ném exception trong khi xử lý một **ApplicationFailedEvent**, Spring Boot vẫn đang ở nhánh failure. Lỗi thứ cấp có thể làm nhiễu thông tin chẩn đoán; vì vậy cần code listener đơn giản, bắt các lỗi có thể dự đoán và bảo toàn exception chính.

Không nên dùng listener để quyết định “tiếp tục khởi động bất chấp lỗi” khi **SpringApplication.run(...)** đã thất bại. Đó là vấn đề về cơ chế startup, cấu hình ứng dụng và chiến lược phục hồi, không phải quyết định của event listener.

## 11. Các phương án đăng ký và hạn chế

| Phương án | Có sẵn trước khi tạo context? | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **application.addListeners(new FailureListener())** trước **run** | Có | Rõ ràng trong entrypoint, không phụ thuộc bean | Cần kiểm soát entrypoint |
| **SpringApplicationBuilder.listeners(...)** | Có nếu cấu hình trước **run** | Hợp với builder hoặc context hierarchy | Cần biết chính xác builder nào sở hữu listener |
| **META-INF/spring.factories** với khóa **ApplicationListener** | Được framework nạp sớm trong bootstrap thông thường | Phù hợp thư viện/starter dùng chung | Cần quản lý classpath, tránh đăng ký trùng |
| **@Bean / @Component + @EventListener** | Không thể bảo đảm | Tốt cho event sau khi context sẵn sàng | Có thể không tồn tại khi startup thất bại |
| **@Async @EventListener** | Không đảm bảo và có rủi ro shutdown | Có thể dùng cho một số việc không critical khác | Không thích hợp làm hook bắt lỗi startup đáng tin |

Trong context hierarchy, event phát từ child có thể được chuyển lên parent, tạo nguy cơ xử lý trùng. Trường hợp có nhiều SpringApplication, nên phân biệt nguồn bằng **event.getSpringApplication()** hoặc ngữ cảnh đã được kiểm tra; không tự tạo một biến toàn cục ghi nhận “đã lỗi” rồi bỏ qua mọi lần chạy khác nhau.

## 12. Kịch bản kiểm thử có giá trị

Khi kiểm thử ApplicationFailedEvent, ưu tiên **dùng SpringApplication thật** thay vì chỉ gọi trực tiếp **onApplicationEvent(...)**:

1. **Lỗi ở ApplicationContextInitializer:** giống ví dụ mục 5. Đăng ký listener trước run; xác nhận listener được gọi, exception đúng và context có thể tồn tại nhưng chưa refresh.
2. **Lỗi rất sớm:** tạo lỗi khi chuẩn bị environment/context theo một extension point được kiểm soát; xác nhận code luôn xử lý **getApplicationContext() == null** an toàn, nếu extension point đó xảy ra trước khi context được tạo.
3. **Lỗi tạo bean:** một bean ném exception trong initialization; xác nhận listener đã đăng ký từ startup vẫn nhận failure và không cố gọi bean lỗi.
4. **Lỗi CommandLineRunner:** runner cố ý ném lỗi; xác nhận có thể đã nhận **ApplicationStartedEvent**, sau đó nhận failure, nhưng **ApplicationReadyEvent** không được phát theo đường thành công.
5. **Startup thành công:** listener failure không được gọi; application có thể phát **ApplicationReadyEvent** theo luồng bình thường.
6. **Lỗi request sau startup:** exception runtime không tự tạo **ApplicationFailedEvent**.
7. **Lỗi tại listener:** giả lập sink ghi log/metric lỗi; xác nhận lỗi thứ cấp không che nguyên nhân startup ban đầu.
8. **Thông tin nhạy cảm:** chạy với args mô phỏng token; xác nhận listener không in nguyên args.
9. **Khởi động lặp nhiều lần trong test:** mỗi SpringApplication có listener phù hợp, không nhân đôi hook ngoài ý muốn.

Đối với integration test, có thể dùng **SpringApplication** với **WebApplicationType.NONE** để tránh mở cổng và giảm biến động môi trường. Với failure cụ thể, kiểm tra **exception chain** thay vì so sánh toàn bộ log hoặc message từ một implementation mà phiên bản mới có thể thay đổi.

Nếu muốn unit test logic phân loại lỗi, tạo **ApplicationFailedEvent** và gọi trực tiếp listener; cách đó **không thay thế** integration test xác nhận sự kiện thực sự được Spring Boot phát khi startup thất bại.

## 13. Các lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ khai báo **@EventListener** trong một bean thông thường | Không bắt được lỗi xảy ra trước lúc bean được tạo | Đăng ký **ApplicationListener<ApplicationFailedEvent>** trước run |
| Giả định **getApplicationContext()** luôn khác null | NullPointerException đúng lúc đang ghi nhận lỗi | Kiểm tra null trước mọi truy cập |
| Gọi bean/repository khi context refresh thất bại | Gây lỗi mới hoặc phụ thuộc tài nguyên không còn hợp lệ | Listener phụ thuộc tối thiểu, dùng logging độc lập |
| Xem ApplicationFailedEvent là exception handler runtime | Bỏ sót lỗi request/job sau startup | Dùng các handler/telemetry đúng lớp runtime |
| Cho rằng ApplicationStartedEvent đảm bảo ready | Runner vẫn có thể lỗi | Dùng ApplicationReadyEvent/readiness đúng lúc |
| Đưa gửi cảnh báo bắt buộc sang **@Async** | JVM có thể thoát trước khi task chạy | Dùng output độc lập hoặc telemetry do platform thu thập |
| Tự publish ApplicationFailedEvent cho bất kỳ lỗi nào | Làm nhiễu startup lifecycle | Giữ event cho startup; lỗi runtime theo quy trình riêng |
| Nuốt exception startup trong listener | Caller không nhận được trạng thái thất bại đúng | Giữ nguyên failure propagation; listener chỉ quan sát |
| Log toàn bộ args/environment | Rò rỉ thông tin nhạy cảm | Redact, whitelist trường log |
| Không phân biệt nhiều context/application | Alert hoặc metric trùng | Gắn identity và kiểm soát registration |
| Dùng listener để retry toàn bộ ứng dụng ngay lập tức | Vòng lặp startup lỗi khó kiểm soát | Đặt chính sách restart/backoff ở orchestration layer |

## 14. Checklist thiết kế một failure listener

Trước khi viết listener, trả lời:

- **Nó có được đăng ký trước khi SpringApplication.run(...) chưa?**
- **Nó có xử lý được trường hợp context null và context chưa refresh không?**
- **Nó chỉ đọc exception/metadata an toàn và không phụ thuộc bean lỗi chứ?**
- **Nó có phân biệt startup failure với runtime failure không?**
- **Nó có tránh log token, password, toàn bộ command-line args không?**
- **Nó có timeout, logging fallback và không giữ startup bị lỗi quá lâu không?**
- **Hệ thống còn có exit-code/probe/log để phát hiện lỗi khi event không xuất hiện không?**
- **Đã kiểm thử initializer failure, bean failure, runner failure và startup thành công chưa?**

**Nguyên tắc ghi nhớ:** **ApplicationFailedEvent** là tín hiệu Spring Boot đưa ra khi **SpringApplication không thể hoàn tất startup**. Đăng ký listener **trước run**, đọc **getException()**, kiểm tra null của **getApplicationContext()**, ghi nhận dữ liệu chẩn đoán an toàn và để failure tiếp tục đi theo đường xử lý lỗi bình thường của Spring Boot.

### Tài liệu chính thức

- Spring Boot 3.5 Reference, *SpringApplication — Application Events and Listeners*: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 Javadoc, *ApplicationFailedEvent*: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html
- Spring Boot 3.5 Javadoc, *SpringApplication*: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot Reference, *Application Availability*: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability
- Spring Boot 3.5 Reference, *Startup Failure and FailureAnalyzer*: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.startup-failure
