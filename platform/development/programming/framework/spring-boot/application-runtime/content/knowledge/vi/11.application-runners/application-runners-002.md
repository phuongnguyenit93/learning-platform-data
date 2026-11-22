# Thời điểm runner chạy so với refresh, started và ready trong Spring Boot

## 1. Kết luận trước khi đi vào chi tiết

Trong một lần khởi chạy `SpringApplication.run(...)` thành công, **`ApplicationRunner.run(...)` và `CommandLineRunner.run(...)` được Spring Boot gọi sau khi `ApplicationContext.refresh()` hoàn tất và sau `ApplicationStartedEvent`, nhưng trước `ApplicationReadyEvent`**.

Thứ tự cốt lõi:

~~~text
SpringApplication.run(args)
    |
    +-- Chuẩn bị Environment, ApplicationContext, bean definitions
    |
    +-- ApplicationContext.refresh()
    |      +-- Tạo/khởi tạo singleton thông thường
    |      +-- Tạo các bean có kiểu ApplicationRunner / CommandLineRunner
    |      +-- Chạy init callback (@PostConstruct, initMethod,...)
    |      +-- Hoàn tất refresh, phát ContextRefreshedEvent
    |
    +-- Log "Started ..." và phát ApplicationStartedEvent
    +-- LivenessState.CORRECT
    |
    +-- Gọi các runner theo thứ tự đã sắp xếp
    |      +-- ApplicationRunner.run(ApplicationArguments)
    |      +-- CommandLineRunner.run(String... args)
    |
    +-- Phát ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    |
    +-- SpringApplication.run(...) trả về context
~~~

Sơ đồ đã giản lược các bước bên trong `refresh()` và các sự kiện sớm. Những mốc chính nêu trên là hợp đồng được Spring Boot công bố trong tài liệu về `SpringApplication`. Đặc biệt:

- **Đã tạo bean runner** không có nghĩa **đã gọi phương thức `run()` của runner**. Bean có thể được tạo trong refresh, còn callback `run()` đến sau `ApplicationStartedEvent`.
- **`ApplicationStartedEvent` không phải `ApplicationReadyEvent`**. Tại Started, các runner chưa được gọi; tại Ready, các runner đồng bộ đã được gọi và hoàn tất thành công.
- **Web server đã mở cổng** không tự chứng minh runner chạy xong. Trong web app, cổng có thể đã sẵn sàng nhận kết nối trước khi Spring Boot công bố readiness.
- `ApplicationReadyEvent` được phát **trước** việc Boot công bố `ReadinessState.ACCEPTING_TRAFFIC`; event không đồng nghĩa toàn bộ tác vụ nền tùy biến đã kết thúc.

## 2. Thuật ngữ quan trọng

### 2.1. ApplicationContext.refresh()

`refresh()` thuộc vòng đời Spring Framework. Trong một Spring Boot application context thông thường, nó chuẩn bị BeanFactory, xử lý các factory post-processor, đăng ký bean post-processor, khởi tạo các singleton không lazy, kích hoạt lifecycle thích hợp và hoàn tất việc refresh context. Các bean singleton của runner thường được khởi tạo ở giai đoạn này, giống nhiều bean khác.

Một số mốc gắn với refresh:

- `ApplicationPreparedEvent` của Spring Boot xảy ra khi context đã được chuẩn bị nhưng **trước** refresh.
- `ContextRefreshedEvent` của Spring Framework được phát khi context hoàn tất refresh.
- `WebServerInitializedEvent` có thể xuất hiện trong giai đoạn refresh của một web application, khi web server đã khởi động.
- `ApplicationStartedEvent` của Spring Boot diễn ra **sau** khi refresh thành công.

Đừng nhầm `ContextRefreshedEvent` của Spring Framework với `ApplicationReadyEvent` của Spring Boot. Context được refresh chỉ cho biết container đã đạt mốc refresh; nó chưa nói các runner của Spring Boot đã thực thi.

### 2.2. ApplicationStartedEvent

`org.springframework.boot.context.event.ApplicationStartedEvent` là sự kiện Spring Boot được phát **khi context đã refresh nhưng trước khi bất kỳ application/command-line runner nào được gọi**.

Điều này có ý nghĩa thực hành: listener nhận Started có thể quan sát context và các bean đã được khởi tạo nhưng không thể dựa vào side effect từ `ApplicationRunner.run()` hay `CommandLineRunner.run()`, vì các callback đó chưa chạy trong đường startup bình thường.

`ApplicationStartedEvent` không nên được hiểu là “toàn ứng dụng sẵn sàng nhận traffic”. Nó chỉ đánh dấu mốc sau refresh, trước runner.

### 2.3. ApplicationReadyEvent

`org.springframework.boot.context.event.ApplicationReadyEvent` là sự kiện được phát sau khi Spring Boot đã gọi xong các runner. Trong đường startup thành công, sự kiện này được phát rất muộn để báo rằng ứng dụng đã hoàn tất quá trình khởi động do Boot quản lý.

Sau `ApplicationReadyEvent`, Spring Boot công bố trạng thái `ReadinessState.ACCEPTING_TRAFFIC` bằng một `AvailabilityChangeEvent` riêng. Vì vậy, nếu kiểm tra readiness bên trong một listener nhận chính `ApplicationReadyEvent`, cần nhớ **thời điểm công bố readiness accepting nằm sau event đó**. Khi `SpringApplication.run(...)` đã trả về thành công, quá trình công bố readiness của đường startup bình thường đã diễn ra.

### 2.4. ApplicationRunner và CommandLineRunner

Cả hai đều là interface trong package `org.springframework.boot`, được Spring Boot phát hiện dưới dạng **bean** của ApplicationContext rồi gọi một lần mỗi lần chạy SpringApplication theo đường startup thành công:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Hai đoạn trên là **bản minh họa chữ ký phương thức**, không phải định nghĩa interface cần chép lại vào dự án. Dùng interface có sẵn từ Spring Boot.

Điểm khác nhau chủ yếu là cách nhận đối số:

- `ApplicationRunner`: nhận `ApplicationArguments`; có thể dùng `getOptionNames()`, `containsOption(name)`, `getOptionValues(name)`, `getNonOptionArgs()`, `getSourceArgs()`.
- `CommandLineRunner`: nhận đối số gốc `String... args`, phù hợp với xử lý CLI trực tiếp hoặc code chỉ cần chuỗi đầu vào.

Về **thời điểm gọi**, cả hai thuộc **cùng pha runners** giữa Started và Ready. Không có quy tắc tổng quát “mọi ApplicationRunner phải chạy trước mọi CommandLineRunner”; khi có nhiều runner, thứ tự phụ thuộc cơ chế sắp xếp (`Ordered` / `@Order`), không chỉ phụ thuộc tên interface.

## 3. Chuỗi startup chi tiết và những gì đã sẵn sàng

| Giai đoạn | Bean thông thường đã được tạo? | `runner.run()` đã chạy? | Có thể kết luận gì? |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | Chưa có context hoàn chỉnh | Chưa | Lần chạy `SpringApplication` vừa bắt đầu |
| `ApplicationEnvironmentPreparedEvent` | Chưa có context chính | Chưa | Environment đã được chuẩn bị |
| `ApplicationContextInitializedEvent` | Context mới được khởi tạo sơ bộ | Chưa | Context đã được tạo và initializers đã chạy |
| `ApplicationPreparedEvent` | Definitions đã được nạp, chưa refresh | Chưa | Chuẩn bị gọi refresh |
| Trong `refresh()` | Các singleton cần thiết đang được tạo | Chưa được Boot gọi trong pha runner | Container đang thiết lập bean và lifecycle |
| `ContextRefreshedEvent` | Các singleton eager đã hoàn tất theo refresh | Chưa | Context refresh thành công |
| `ApplicationStartedEvent` | Context đã refresh | **Chưa** | Spring Boot đạt mốc Started |
| Trong pha `callRunners(...)` | Bean runner đã có để gọi | Đang chạy lần lượt | Startup vẫn chưa hoàn tất |
| `ApplicationReadyEvent` | Có | **Đã chạy thành công** | Boot phát mốc Ready |
| `ReadinessState.ACCEPTING_TRAFFIC` | Có | Đã chạy thành công | Boot công bố có thể nhận traffic |
| `SpringApplication.run(...)` trả về | Có | Đã chạy thành công | Caller trong `main()` có thể thực thi tiếp |

“Các singleton eager” không bao gồm bean `@Lazy` chưa được yêu cầu hoặc bean prototype chưa được tra cứu. Vì vậy **không được suy ra tất cả bean trong toàn ứng dụng đều đã được tạo** trước `ApplicationStartedEvent`; điều được bảo đảm là context đã hoàn tất refresh theo hợp đồng của nó.

### Tại sao runner được tạo trong refresh nhưng run() được gọi muộn hơn?

Spring Boot xem runner là **một loại bean có callback dành cho giai đoạn sau startup của container**. BeanFactory cần khởi tạo runner và inject dependency như những bean bình thường. Sau đó `SpringApplication` lấy các bean có kiểu `ApplicationRunner`/`CommandLineRunner` từ context và gọi phương thức `run(...)` trong pha riêng. Nhờ vậy:

1. Runner có thể inject service, repository, `Environment` hoặc `ApplicationAvailability` đã được chuẩn bị bởi container.
2. Runner không phải tự tạo dependency bằng `new` hoặc tự bootstrap một BeanFactory.
3. Phần việc đòi hỏi context đầy đủ được tách khỏi constructor, `@PostConstruct` và factory method.
4. Spring Boot có thể phát Started trước khi runner xử lý và Ready sau khi runner xử lý xong.

**Phân biệt rất quan trọng:** nếu trong constructor của runner có log `RUNNER_CONSTRUCTED`, log đó có thể xuất hiện **trong refresh**, nhưng log `RUNNER_EXECUTING` bên trong phương thức `run()` chỉ xuất hiện **sau ApplicationStartedEvent**.

## 4. Thứ tự với các callback khác

| Callback / event | Địa điểm điển hình | Quan hệ với runner.run() |
| --- | --- | --- |
| Constructor bean | Trong giai đoạn tạo bean | Trước runner nếu đó là bean eager đã tạo |
| `@Autowired` / constructor injection | Khi tạo và cấu hình bean | Trước runner |
| `@PostConstruct` | Khi init bean, trong refresh đối với eager singleton | Thường trước runner |
| `InitializingBean.afterPropertiesSet()` | Trong init bean | Trước runner đối với eager singleton |
| `@Bean(initMethod = "...")` | Trong init bean | Trước runner đối với eager singleton |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Sau khi tạo các singleton eager | Trước runner trong refresh bình thường |
| `SmartLifecycle.start()` khi auto-start | Trong lifecycle startup của context | Thường trước runner |
| `ContextRefreshedEvent` | Kết thúc refresh | Trước runner |
| `ApplicationStartedEvent` | Sau refresh | Trước runner |
| `ApplicationRunner.run()` và `CommandLineRunner.run()` | Pha runner của Boot | Mốc chính |
| `ApplicationReadyEvent` | Sau khi runners hoàn tất | Sau runner |
| `ReadinessState.ACCEPTING_TRAFFIC` | Sau Ready event | Sau runner |
| `ContextClosedEvent` | Khi context đóng | Thuộc shutdown, không phải mốc startup |

Các nhận định với bean eager là về **đường khởi động bình thường**. Bean lazy được tạo lần đầu về sau có thể thực hiện `@PostConstruct` muộn hơn runner; đó không phải vi phạm thứ tự startup. Listener sự kiện có thể được cấu hình bất đồng bộ, hoặc callback có thể tự tạo thread; vì thế thời điểm **bắt đầu callback** không bảo đảm rằng mọi công việc bất đồng bộ đã hoàn thành.

### Hai dòng log dễ gây hiểu nhầm

Log ví dụ:

~~~text
Tomcat started on port 8080 (http)
Started DemoApplication in 2.345 seconds
~~~

Đây là **minh họa định dạng log**, không phải stdout cố định của một phiên bản Spring Boot hay một chương trình cụ thể.

- Dòng “Tomcat started ...” cho biết web server nhúng đã đạt mốc startup. Server có thể đã mở cổng trong giai đoạn refresh.
- Dòng “Started ... in ... seconds” thường đánh dấu phần startup sau context refresh. Nó **không tự chứng minh runners đã kết thúc**; Spring Boot có thể còn phải gọi runner rồi mới phát Ready event.

Nếu runner chạy 20 giây, một số log server và “Started ...” có thể xuất hiện từ trước. Không nên dùng chuỗi log đó để quyết định instance đã có thể phục vụ nghiệp vụ hay chưa; dùng readiness probe hoặc event đúng mục đích.

## 5. Ví dụ hoàn chỉnh Java 17+ — quan sát refresh, started, runner, ready

Ví dụ dưới đây dùng Spring Boot **3.5.16** và Java 17+. Nó cố ý chạy không có web server (`WebApplicationType.NONE`) để không có log Tomcat làm nhiễu kết quả. Chương trình in các mốc có thứ tự và sử dụng `Ordered` để kiểm soát rõ runner nào được gọi trước. Nó không sử dụng `Thread.sleep` và không phụ thuộc database.

### 5.1. Cấu trúc thư mục

~~~text
runner-timing-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/runnertiming/
                └── RunnerTimingApplication.java
~~~

**Tệp `pom.xml`:**

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
    <artifactId>runner-timing-demo</artifactId>
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

Cần có JDK 17+ và Maven tương thích. Nếu dự án sử dụng nhánh Spring Boot khác, chọn đúng phiên bản phụ thuộc và import tương ứng. Ví dụ dùng `spring-boot-starter`, **không yêu cầu `spring-boot-starter-web`** vì không có HTTP endpoint.

### 5.2. Tệp Java có thể biên dịch

**Tệp `src/main/java/com/example/runnertiming/RunnerTimingApplication.java`:**

~~~java
package com.example.runnertiming;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;

@SpringBootApplication
public class RunnerTimingApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                RunnerTimingApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ApplicationAvailability availability = context.getBean(
                    ApplicationAvailability.class);
            System.out.println(
                    "08_RUN_RETURNED readiness="
                            + availability.getReadinessState());
        }
    }

    @Bean(initMethod = "initialize")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    TimelineObserver timelineObserver() {
        return new TimelineObserver();
    }

    @Bean
    FirstRunner firstRunner(DemoResource resource,
                            ApplicationAvailability availability) {
        return new FirstRunner(resource, availability);
    }

    @Bean
    SecondRunner secondRunner() {
        return new SecondRunner();
    }

    public static final class DemoResource {

        public DemoResource() {
            System.out.println("01_RESOURCE_CONSTRUCTOR");
        }

        public void initialize() {
            System.out.println("02_RESOURCE_INITIALIZED");
        }

        public String value() {
            return "ready";
        }
    }

    public static final class TimelineObserver {

        @EventListener
        public void onRefreshed(ContextRefreshedEvent event) {
            System.out.println("03_CONTEXT_REFRESHED");
        }

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            System.out.println("04_APPLICATION_STARTED");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            System.out.println("07_APPLICATION_READY");
        }
    }

    public static final class FirstRunner
            implements ApplicationRunner, Ordered {

        private final DemoResource resource;
        private final ApplicationAvailability availability;

        public FirstRunner(DemoResource resource,
                           ApplicationAvailability availability) {
            this.resource = resource;
            this.availability = availability;
        }

        @Override
        public int getOrder() {
            return 10;
        }

        @Override
        public void run(ApplicationArguments args) {
            System.out.println(
                    "05_APPLICATION_RUNNER readiness="
                            + availability.getReadinessState()
                            + " value=" + resource.value()
                            + " args=" + args.getSourceArgs().length);

            if (args.containsOption("fail")) {
                throw new IllegalStateException("runner-failed");
            }
        }
    }

    public static final class SecondRunner
            implements CommandLineRunner, Ordered {

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void run(String... args) {
            System.out.println(
                    "06_COMMAND_LINE_RUNNER args=" + args.length);
        }
    }
}
~~~

**Đây là chương trình đầy đủ** trong dự án Maven đã cho, không phải pseudocode. Các class phụ được khai báo bên trong một tệp để giảm cấu hình. `FirstRunner` và `SecondRunner` đều là bean do các phương thức `@Bean` tạo. `Ordered.getOrder()` trả 10 và 20; giá trị nhỏ hơn có độ ưu tiên gọi trước.

Các mốc `01_RESOURCE_CONSTRUCTOR` và `02_RESOURCE_INITIALIZED` xảy ra khi Spring tạo/khởi tạo `DemoResource`, **trong refresh**, trước khi Spring Boot chuyển sang pha gọi runner. `TimelineObserver` là bean listener: nó được đăng ký trong context và quan sát các event xảy ra sau refresh thích hợp.

`FirstRunner` nhận `ApplicationAvailability` và `DemoResource` qua dependency injection. Nó đọc `ReadinessState` **khi phương thức `run()` chạy**, không phải trong constructor. Khi Boot vẫn đang thực thi runners, trạng thái readiness mặc định là `REFUSING_TRAFFIC`. Nếu không truyền `--fail`, phương thức chỉ in marker rồi trả về thành công.

`main()` dùng `try`-with-resources để đóng context sau khi in marker cuối; việc đóng context là thao tác dọn dẹp của ví dụ CLI, không phải một phần của trình tự runner. Vì `TimelineObserver` không lắng nghe `ContextClosedEvent`, nó không tạo thêm dòng marker trong chương trình.

### 5.3. Chạy và so sánh output

Trong thư mục chứa `pom.xml`, chạy:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói rồi chạy JAR:

~~~bash
mvn package
java -jar target/runner-timing-demo-0.0.1-SNAPSHOT.jar
~~~

Chạy thành công với **không có tham số ứng dụng**, tám dòng **do chương trình tự in** có thứ tự:

~~~text
01_RESOURCE_CONSTRUCTOR
02_RESOURCE_INITIALIZED
03_CONTEXT_REFRESHED
04_APPLICATION_STARTED
05_APPLICATION_RUNNER readiness=REFUSING_TRAFFIC value=ready args=0
06_COMMAND_LINE_RUNNER args=0
07_APPLICATION_READY
08_RUN_RETURNED readiness=ACCEPTING_TRAFFIC
~~~

Banner, log Spring Boot hoặc thông điệp Maven có thể chen giữa; chỉ so sánh **thứ tự các marker trên**, không yêu cầu chúng nằm liền kề trong toàn bộ stdout. Ví dụ không dùng web server, vì vậy việc không có log `Tomcat started` là bình thường.

Dòng `05` đặc biệt có ý nghĩa: runner đã được gọi **sau Started** nhưng ứng dụng vẫn báo `REFUSING_TRAFFIC`. Dòng `08` được in sau khi `SpringApplication.run(...)` đã trả về thành công và readiness đã chuyển sang `ACCEPTING_TRAFFIC`. Hai dòng này xác nhận Started và Ready không phải một mốc.

Dòng `07_APPLICATION_READY` do listener của `ApplicationReadyEvent` in ra **trước lúc Boot công bố `ReadinessState.ACCEPTING_TRAFFIC`**. Không suy rằng readystate đã thay đổi ngay từ đầu phương thức listener đó.

### 5.4. Truyền đối số và kiểm tra thứ tự

Thử:

~~~bash
java -jar target/runner-timing-demo-0.0.1-SNAPSHOT.jar --sample=hello extra
~~~

Trong trường hợp này, `FirstRunner` in `args=2` (hai phần tử trong `getSourceArgs()`); `SecondRunner` in `args=2` (hai phần tử `String...`). Các mốc `01`–`08` vẫn đúng thứ tự. Nếu muốn phân tích option và non-option sâu hơn, `ApplicationArguments` còn có `containsOption("sample")`, `getOptionValues("sample")` và `getNonOptionArgs()`.

**Thử lỗi runner có chủ đích**:

~~~bash
java -jar target/runner-timing-demo-0.0.1-SNAPSHOT.jar --fail
~~~

`FirstRunner` sẽ ném `IllegalStateException("runner-failed")`. Khi đó `SpringApplication.run(...)` thất bại; `SecondRunner` phía sau không được gọi trong pipeline bình thường, `ApplicationReadyEvent` không được phát và dòng `08_RUN_RETURNED` không xuất hiện. Spring Boot có thể công bố `ApplicationFailedEvent` rồi thực hiện xử lý cleanup thích hợp.

Đường thất bại sẽ có thêm log exception/stack trace tùy môi trường, vì vậy **không coi toàn bộ stdout của lần chạy thất bại là một chuỗi cố định**. Điều quan trọng là đã có Started nhưng chưa có Ready; nó chứng minh `ApplicationStartedEvent` không bảo đảm mọi runner thành công.

## 6. Điều gì xảy ra khi có nhiều runner?

Một ứng dụng có thể khai báo nhiều `ApplicationRunner` và `CommandLineRunner`. Spring Boot thu thập những bean này, sắp xếp bằng cơ chế thứ tự của Spring rồi gọi lần lượt. Khi thứ tự có ý nghĩa nghiệp vụ, hãy dùng:

1. **`org.springframework.core.Ordered`**: implement `getOrder()` trong class runner.
2. **`org.springframework.core.annotation.Order`**: áp dụng trên loại runner phù hợp được Spring nhận diện.
3. **`PriorityOrdered`** nếu thực sự cần hợp đồng ưu tiên đặc biệt, đồng thời hiểu cách comparator sắp xếp.

**Thứ tự số nhỏ hơn được ưu tiên trước** trong cùng cơ chế sắp xếp. Ví dụ ở mục 5 dùng `Ordered`, nên không phụ thuộc vào thứ tự các phương thức `@Bean` được liệt kê trong file.

Một điều cần tránh: nhìn vào chữ `ApplicationRunner` và `CommandLineRunner` rồi cho rằng tất cả bean thuộc một loại luôn chạy trước loại kia. Chúng cùng tham gia cơ chế sắp xếp và gọi runner; **để có thứ tự xác định, hãy khai báo order rõ ràng**. Nếu có runner cùng mức order, không dựa vào vị trí tình cờ xuất hiện trong một lần chạy.

### Có nên sử dụng @DependsOn để kiểm soát thứ tự runner?

Không. `@DependsOn` chủ yếu yêu cầu bean dependency được khởi tạo trước bean phụ thuộc; nó **không thay thế** `Ordered` / `@Order` để quy định thứ tự gọi `run()`.

Ví dụ, `@DependsOn("prepareService")` trên runner có thể khiến `prepareService` được tạo sớm, nhưng không chứng minh rằng `run()` của một runner khác đã chạy xong. Hãy tách hai khái niệm:

- **Dependency graph**: thứ tự tạo bean và inject dependency.
- **Runner order**: thứ tự Spring Boot gọi các callback `run()` sau Started.

Nếu runner B thực sự phụ thuộc kết quả runner A, hãy tự làm rõ hợp đồng giữa chúng. Trong một số hệ thống, tốt hơn là tạo **một runner điều phối tuần tự** nhiều bước thay vì hai runner rời rạc với side effect ẩn trong shared state.

### Runner có chạy song song theo mặc định không?

Theo pipeline khởi động thông thường, Spring Boot **gọi runner lần lượt**, không tự tạo một luồng cho mỗi runner. Các runner có thể tự khởi chạy thread hoặc async task; những nhiệm vụ đó **không được Boot tự động chờ** chỉ vì chúng xuất phát từ runner. Vì vậy phải phân biệt *runner method return* với *work spawned by runner actually complete*.

Nếu runner A tạo background worker rồi trả về ngay, Spring Boot có thể gọi runner B và phát Ready mặc dù worker A còn đang chạy. Để đảm bảo readiness thực tế, cần đợi công việc thiết yếu hoàn thành hoặc phản ánh trạng thái vào readiness health.

## 7. Readiness, liveness và web server trong thời gian runner chạy

Spring Boot có `ApplicationAvailability` với hai nhóm trạng thái khác nhau:

- **`LivenessState`**: ứng dụng còn sống và có cần restart hay không (`CORRECT` hoặc `BROKEN`).
- **`ReadinessState`**: instance có nên nhận traffic mới hay không (`REFUSING_TRAFFIC` hoặc `ACCEPTING_TRAFFIC`).

Trong startup bình thường, `ApplicationStartedEvent` được theo sau bởi tín hiệu `LivenessState.CORRECT`. Sau khi runners thành công, `ApplicationReadyEvent` được theo sau bởi `ReadinessState.ACCEPTING_TRAFFIC`.

Do đó **liveness có thể tốt trong khi readiness vẫn từ chối traffic**, đặc biệt khi runner đang thực hiện bước khởi tạo bắt buộc.

### Một web server có thể mở cổng trước Ready

Với ứng dụng Servlet hoặc Reactive, web server được khởi tạo/khởi động trong quá trình refresh của web context. Trong một khoảng thời gian, cổng TCP có thể đã mở và HTTP endpoint có thể trả lời, nhưng runner chưa kết thúc. Điều này là lý do cần readiness probe trong môi trường Kubernetes/load balancer thay vì suy ra sẵn sàng chỉ từ log “server started”.

Để dùng probes Actuator ngoài Kubernetes (nơi chúng có thể không được bật tự động), có thể cấu hình trong dự án có `spring-boot-starter-actuator`:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Khi phù hợp, các endpoint là:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Khi runner chưa hoàn tất, readiness mặc định của Boot thường là `REFUSING_TRAFFIC` và readiness health có thể phản ánh `OUT_OF_SERVICE` / HTTP 503 theo mapping mặc định. Khi chạy xong và Boot công bố accepting, health có thể trả `UP` / HTTP 200, với điều kiện không có indicator bổ sung khiến trạng thái chung khác đi.

**Không nên** dùng một endpoint tùy ý luôn trả HTTP 200 làm readiness probe. Đồng thời, không đặt mọi dependency bên ngoài vào liveness: một lần gián đoạn database có khả năng tự hồi phục có thể phù hợp hơn với readiness so với việc restart pod liên tục.

### ApplicationReadyEvent có bảo đảm toàn bộ nghiệp vụ đã sẵn sàng?

Không tuyệt đối. `ApplicationReadyEvent` phản ánh việc Spring Boot đã hoàn tất **các runner do nó gọi** trong đường startup, không tự kiểm tra mọi kết nối và công việc nền mà ứng dụng tự tạo.

Ví dụ sai lầm về mặt ý tưởng:

~~~java
@Bean
ApplicationRunner prematureRunner() {
    return args -> {
        new Thread(this::loadRequiredCache).start();
        // run() trả về ngay trong khi cache vẫn đang tải.
    };
}
~~~

Đây là **đoạn minh họa không độc lập** (`loadRequiredCache` là method giả định). Spring Boot chỉ thấy `run()` đã trả về, nên có thể phát Ready quá sớm nếu cache bắt buộc cho mọi request.

Cách thiết kế phù hợp hơn tùy trường hợp:

- Nếu công việc là điều kiện bắt buộc trước khi nhận traffic, để runner **đợi hoàn thành có giới hạn thời gian** rồi mới trả về; khi thất bại, có chính sách fail startup hoặc xử lý lỗi rõ ràng.
- Nếu phải chạy bất đồng bộ, đưa trạng thái công việc bắt buộc vào readiness health hoặc một cơ chế điều khiển `ApplicationAvailability` phù hợp, bảo đảm Boot không mở traffic trước khi sẵn sàng hoặc có logic giữ readiness sau mốc Ready.
- Nếu bước xử lý chỉ là warming cache không thiết yếu, có thể chạy nền và chấp nhận traffic sớm, miễn chức năng có fallback đúng.

Lưu ý: Boot tự phát `ACCEPTING_TRAFFIC` sau Ready. Một lần công bố `REFUSING_TRAFFIC` quá sớm có thể bị mốc mặc định này ghi đè. Nếu điều khiển readiness tùy biến, phải quản lý rõ thứ tự và trạng thái sau Ready, không chỉ phát event một lần trong constructor của runner rồi hy vọng trạng thái tồn tại mãi.

## 8. Runner ném exception hoặc bị block thì sao?

### 8.1. Runner ném exception

`ApplicationRunner.run(...)` và `CommandLineRunner.run(...)` được phép `throws Exception`. Nếu một runner ném exception không được xử lý:

- `ApplicationStartedEvent` **đã có thể được phát**, bởi nó đến trước runner.
- Các runner sau trong pipeline thông thường **không tiếp tục chạy**.
- `ApplicationReadyEvent` **không được phát như đường khởi động thành công**.
- `SpringApplication.run(...)` thất bại và Spring Boot xử lý lỗi startup, có thể phát `ApplicationFailedEvent`; việc đóng context/resource phụ thuộc giai đoạn và cơ chế cleanup.

**Không** dựa vào `ApplicationStartedEvent` như dấu hiệu “đã hoàn thành khởi động thành công”. Nếu cần đánh giá lúc startup thực sự thành công, dùng `ApplicationReadyEvent`, readiness hoặc kết quả của `SpringApplication.run(...)`.

### 8.2. Runner chạy quá lâu

Một runner chặn trong 60 giây khiến toàn bộ `SpringApplication.run(...)` thường chưa thể kết thúc trong thời gian đó. Những rủi ro:

- Startup timeout ở môi trường điều phối.
- Readiness bị giữ từ chối lâu, rollout chậm hoặc pod chưa nhận traffic.
- Nếu chỉ nhìn log “Started ...”, người vận hành tưởng đã xong trong khi runner còn chặn.
- Exception/timeout ở dependency có thể khiến tiến trình không bao giờ tới Ready.

Nên thiết kế bước khởi tạo có **timeout, retry có giới hạn, cancellation và chính sách lỗi**. Nếu tác vụ không bắt buộc để tiếp nhận traffic, đừng buộc startup chờ vô hạn. Nếu cần warm-up dài, cân nhắc startup probe và readiness đúng với thực tế.

### 8.3. Runner vừa cần bean vừa muốn dùng một web server

Runner có thể inject `ApplicationContext`, service, `WebClient`, `JdbcTemplate` hoặc bean khác, miễn các dependency đã được định nghĩa. Nhưng **không nên coi việc web server đang lên là tín hiệu an toàn để tự gọi một HTTP endpoint nội bộ** nếu endpoint vẫn phụ thuộc trạng thái đang được runner khởi tạo. Tránh logic phụ thuộc vòng giữa runner và request mà runner đang chờ.

## 9. Chọn runner hay lifecycle hook nào cho bài toán?

| Nhu cầu | Điểm mở rộng phù hợp | Lý do |
| --- | --- | --- |
| Tùy biến bean definition trước khi tạo bean | `BeanFactoryPostProcessor` / `BeanDefinitionRegistryPostProcessor` | Làm việc với metadata trước init |
| Khởi tạo trạng thái bên trong một bean | Constructor, init method, `@PostConstruct` | Thuộc vòng đời của chính bean |
| Quan sát context refresh xong | `ContextRefreshedEvent` | Mốc container hoàn tất refresh |
| Làm một tác vụ khởi động có thể dùng service đã inject | `ApplicationRunner` / `CommandLineRunner` | Sau refresh, trước Ready |
| Quan sát mốc Boot Started | `ApplicationStartedEvent` | Không bao gồm runner |
| Thông báo ứng dụng hoàn tất startup do Boot quản lý | `ApplicationReadyEvent` | Sau runners |
| Xác định instance có nhận traffic không | Readiness probe / `ApplicationAvailability` | Mô tả khả năng phục vụ thực tế |
| Chạy công việc định kỳ hoặc job không được chặn startup | `@Scheduled`, queue consumer, worker được quản lý | Không lạm dụng runner để làm scheduler |
| Dọn dẹp bean khi ứng dụng đóng | `@PreDestroy`, `DisposableBean`, `SmartLifecycle` | Thuộc shutdown, không phải runner |
| Chạy batch CLI rồi thoát | Runner + quy trình exit phù hợp | Sử dụng context đã refresh cho xử lý batch |

Runner phù hợp cho một tác vụ **được gọi một lần khi SpringApplication khởi động**, không phải callback cho mỗi HTTP request hoặc cho mỗi lần `ApplicationContext.refresh()` được gọi thủ công trên mọi loại context. Cũng không có nghĩa runner được gọi lại mỗi khi Kubernetes probe chạm endpoint.

## 10. Những hiểu nhầm phổ biến

1. **“Tạo bean runner = runner đã chạy.”** Sai: constructor/`@PostConstruct` trong refresh, còn `run()` sau Started.
2. **“`ContextRefreshedEvent` = `ApplicationReadyEvent`.”** Sai: refresh trước runners, ready sau runners.
3. **“`ApplicationStartedEvent` cho biết runner đã hoàn tất.”** Sai: event này được phát **trước** khi gọi runner.
4. **“Cứ thấy `Started DemoApplication in ...` là sẵn sàng nhận traffic.”** Sai: runner có thể còn đang chạy hoặc thất bại.
5. **“ApplicationRunner luôn chạy trước CommandLineRunner.”** Sai: cả hai được sắp xếp theo cơ chế order; hãy dùng `Ordered` hoặc `@Order`.
6. **“`@DependsOn` đảm bảo thứ tự gọi run() giữa các runner.”** Sai: nó liên quan tới tạo bean, không phải pipeline gọi callback runner.
7. **“Runner bắt đầu một `CompletableFuture` rồi trả về thì Boot sẽ đợi future.”** Sai: Boot không tự đợi tác vụ nền ngoài phương thức `run()`.
8. **“Server mở cổng tức là `ApplicationReadyEvent` đã phát.”** Sai: server có thể lên trong refresh trước runners.
9. **“Liveness `CORRECT` đồng nghĩa readiness `ACCEPTING_TRAFFIC`.”** Sai: liveness và readiness là hai trạng thái khác nhau.
10. **“Một runner ném lỗi nhưng Ready vẫn sẽ tự xuất hiện.”** Sai trong đường khởi động thất bại; Spring Boot không tới ready thành công.
11. **“Mọi bean đều đã được khởi tạo ở Started.”** Không đúng với lazy hoặc prototype; Started phản ánh refresh hoàn tất theo hợp đồng, không phải force-create mọi bean.
12. **“Có thể lấy kết quả runner trong listener Started.”** Không, trừ khi dữ liệu đó đã được tạo từ một đường khác; runner của lần startup này còn chưa chạy.
13. **“Dùng `ApplicationReadyEvent` listener để làm tác vụ blocking dài là luôn hợp lý.”** Không nên mặc định; listener mặc định đồng bộ, có thể trì hoãn việc phát availability accepting và hoàn tất startup.
14. **“Run method chạy trước hết mọi init method.”** Sai với eager singleton; init thuộc refresh, runner thực thi sau.
15. **“Runner xử lý xong nghĩa là Internet chắc chắn truy cập được ứng dụng.”** Readiness ứng dụng không bảo đảm ingress, DNS, firewall hoặc hạ tầng bên ngoài đã thông suốt.

## 11. Câu hỏi kiểm tra kiến thức

**Câu hỏi 1:** `@PostConstruct` của một bean runner thường chạy trước hay sau `ApplicationStartedEvent`?

**Trả lời:** Với runner singleton eager được tạo bình thường khi refresh, `@PostConstruct` chạy trong init bean, tức **trước Started**. Nhưng `run()` của runner được Spring Boot gọi **sau Started**.

**Câu hỏi 2:** `ApplicationStartedEvent` đã phát, nhưng runner đang nạp dữ liệu trong 10 giây. Ứng dụng đã Ready chưa?

**Trả lời:** Chưa theo lifecycle Spring Boot. `ApplicationReadyEvent` đến sau khi runner kết thúc thành công; readiness mặc định vẫn từ chối traffic trong lúc runner thực thi.

**Câu hỏi 3:** Có hai runner, một `ApplicationRunner` order 100 và một `CommandLineRunner` order 10. Runner nào chạy trước?

**Trả lời:** Runner order 10 chạy trước trong pipeline được Spring Boot sắp xếp; thứ tự không được quyết định đơn thuần bằng tên interface.

**Câu hỏi 4:** Một runner tạo thread nền rồi trả về ngay, nhưng thread còn nạp dữ liệu quan trọng. `ApplicationReadyEvent` có bị trì hoãn tới khi thread xong không?

**Trả lời:** Không mặc nhiên. Spring Boot biết phương thức `run()` đã trả về; nếu nghiệp vụ cần chờ, runner phải đồng bộ hóa hợp lý hoặc quản lý readiness theo tình trạng thực tế.

**Câu hỏi 5:** Runner ném `IllegalStateException`. Có thể thấy `ApplicationStartedEvent` mà không có `ApplicationReadyEvent` không?

**Trả lời:** Có. Started xảy ra trước runner; Ready là mốc sau khi runners hoàn tất thành công. Đường lỗi thường dẫn tới `ApplicationFailedEvent`.

**Câu hỏi 6:** Có web server chạy nhưng liveness 200 và readiness 503 trong lúc runner làm việc. Có mâu thuẫn không?

**Trả lời:** Không. Server/process có thể sống và phục vụ probe, nhưng readiness chưa mở traffic nghiệp vụ. Hãy xem trạng thái runner và health group thay vì restart pod chỉ do readiness đang chờ hợp lệ.

**Câu hỏi 7:** Tại sao không nên thay `Ordered` bằng `@DependsOn` để xác định thứ tự gọi các runner?

**Trả lời:** `@DependsOn` tác động tới thứ tự khởi tạo bean, còn `Ordered`/`@Order` điều khiển thứ tự gọi callback `run()`. Đó là hai giai đoạn khác nhau.

## 12. Bài tập thực hành

### Bài tập A — xác minh ranh giới

Chạy ví dụ mục 5, ghi lại tám dòng marker theo thứ tự. Xác định dòng nào xảy ra trong refresh, dòng nào sau Started và dòng nào sau Ready. Thử in thêm log trong constructor của `FirstRunner` để thấy **bean runner được tạo trước khi `FirstRunner.run()` được gọi**.

### Bài tập B — đảo thứ tự runner

Đổi `FirstRunner.getOrder()` thành 30, `SecondRunner.getOrder()` giữ 20. Dự đoán thứ tự của các marker `05` và `06` rồi chạy kiểm tra. Lưu ý số ghi trong marker là nhãn cố định do bạn tự in, không phải chỉ số do Spring Boot tự đánh lại. Muốn output dễ đọc hơn, đổi nhãn sau khi đã xác nhận kết quả.

### Bài tập C — thất bại giữa các mốc

Chạy JAR với `--fail`. Đánh dấu các event và runner đã xảy ra trước exception. Giải thích vì sao thiếu `ApplicationReadyEvent` và `RUN_RETURNED`. Chọn một chính sách xử lý lỗi phù hợp với tác vụ khởi tạo thực: fail startup, retry có giới hạn hoặc bỏ qua khi không thiết yếu.

### Bài tập D — thử công việc bất đồng bộ

Thay công việc trong runner bằng một `CompletableFuture` khởi chạy tác vụ nền và trả về ngay. Quan sát Ready có thể xuất hiện trước khi tác vụ hoàn thành. Sau đó thử `future.get` hoặc `join` (có timeout/giới hạn phù hợp cho môi trường thực), giải thích sự khác nhau giữa *phương thức runner đã trả về* và *dữ liệu nghiệp vụ đã sẵn sàng*.

### Bài tập E — áp dụng cho ứng dụng web

Tạo một dự án có `spring-boot-starter-web` và `spring-boot-starter-actuator`, bật `management.endpoint.health.probes.enabled=true`. Trong runner, tạm tạo khoảng chờ có giới hạn chỉ để thử nghiệm. So sánh log server, `/actuator/health/liveness` và `/actuator/health/readiness` trước và sau runner. Không đưa đoạn sleep giả lập vào hệ thống production.

## 13. Tài liệu chính thức và ghi nhớ

Tài liệu Spring Boot cần đọc đúng phiên bản phụ thuộc của dự án:

- [Spring Boot 3.5 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): thứ tự Started → runners → Ready, availability events và hướng dẫn sử dụng runners.
- [Spring Boot 3.5 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationRunner.html): hợp đồng callback, `ApplicationArguments`, thứ tự `Ordered`/`@Order`.
- [Spring Boot 3.5 — CommandLineRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/CommandLineRunner.html): đối số `String...` và callback.
- [Spring Boot 3.5 — ApplicationStartedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html): được phát sau refresh và trước runners.
- [Spring Boot 3.5 — ApplicationReadyEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html): được phát sau khi startup đã đi qua runners.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability): liveness, readiness và hệ quả vận hành.

**Ghi nhớ cốt lõi:**

- **Refresh:** container chuẩn bị, tạo và khởi tạo các bean eager, bao gồm bean runner; cuối refresh có `ContextRefreshedEvent`.
- **Started:** `ApplicationStartedEvent` xảy ra **sau refresh nhưng trước mọi `runner.run()`**.
- **Runners:** `ApplicationRunner` và `CommandLineRunner` được Spring Boot gọi trong cùng pha, với thứ tự do `Ordered`/`@Order` điều khiển khi cần.
- **Ready:** `ApplicationReadyEvent` được phát sau khi runners kết thúc thành công; Boot tiếp tục công bố `ReadinessState.ACCEPTING_TRAFFIC`.
- **Không đánh đồng** log Started hoặc HTTP server đã mở cổng với ứng dụng đã ready; dùng readiness và các mốc lifecycle đúng.
- **Runner đồng bộ phải hoàn thành trước Ready**; tác vụ nền do runner tạo ra không mặc định được chờ. Nếu runner ném exception, startup có thể đã Started nhưng không tới Ready thành công.
