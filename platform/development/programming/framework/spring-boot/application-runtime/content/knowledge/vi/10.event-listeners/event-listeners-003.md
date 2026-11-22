# Đăng ký listener sớm bằng SpringApplication.addListeners

## 1. Vấn đề: listener được tạo sau sự kiện thì không thể nhận sự kiện đó

Trong Spring Boot, sự kiện ứng dụng (`ApplicationEvent`) giúp quan sát các giai đoạn bootstrap và phản ứng khi một mốc quan trọng diễn ra. Tuy nhiên, không phải sự kiện nào cũng được phát **sau khi Spring đã tạo `ApplicationContext` và các bean**.

Ví dụ, `ApplicationStartingEvent` được phát rất sớm trong `SpringApplication.run(...)`, trước cả việc chuẩn bị `Environment`. Nếu bạn chỉ viết một bean nhận sự kiện:

```java
@Component
public class TooLateListener {

    @EventListener(ApplicationStartingEvent.class)
    public void onStarting() {
        System.out.println("Starting");
    }
}
```

thì method này **không nhận được `ApplicationStartingEvent` của lần khởi động hiện tại**, bởi bean và cơ chế xử lý `@EventListener` chưa được tạo/đăng ký vào lúc sự kiện đó xảy ra.

Muốn theo dõi các sự kiện rất sớm, hãy đăng ký `ApplicationListener` **trực tiếp trên đối tượng `SpringApplication` trước khi gọi `run(args)`**:

```java
SpringApplication application = new SpringApplication(MyApplication.class);

application.addListeners(
        (ApplicationListener<ApplicationStartingEvent>) event ->
                System.out.println("Ứng dụng bắt đầu bootstrap"));

application.run(args);
```

Đây là **đoạn tích hợp minh họa**: `MyApplication` là lớp cấu hình/khởi động của project, phải import `SpringApplication`, `ApplicationListener` và `ApplicationStartingEvent` phù hợp. Ví dụ hoàn chỉnh có thể chạy nằm ở phần 6.

**Quy tắc quan trọng:** chọn listener phù hợp với **thời điểm sự kiện được phát** và **tài nguyên thực sự tồn tại** ở thời điểm đó. `addListeners(...)` giải quyết chuyện đăng ký sớm; nó **không khiến `ApplicationContext` hoặc service nghiệp vụ xuất hiện sớm hơn**.

## 2. addListeners(...) thực sự làm gì?

API trong `org.springframework.boot.SpringApplication`:

```java
public void addListeners(ApplicationListener<?>... listeners);
```

Phương thức này nhận **một hoặc nhiều** implementation của `org.springframework.context.ApplicationListener<?>` (varargs) và thêm chúng vào các listener mà `SpringApplication` sẽ sử dụng trong quá trình khởi động, đồng thời đăng ký với `ApplicationContext` khi context được tạo.

Ba điều cần phân biệt:

1. **Đăng ký listener**, không phải phát sự kiện. Sự kiện chỉ được phát khi `SpringApplication.run(...)` đi tới giai đoạn tương ứng.
2. **Thêm listener**, không phải thay toàn bộ danh sách. Phương thức `setListeners(Collection<? extends ApplicationListener<?>>)` có ý nghĩa thiết lập/tái đặt tập listener; tránh thay danh sách vô tình làm mất các listener khác.
3. **Đăng ký với `SpringApplication`**, không có nghĩa đối tượng listener do Spring **tạo như một bean và được dependency injection**. Listener bạn tự `new` có thể nhận sự kiện sớm, nhưng không thể mặc nhiên dùng `@Autowired` trên nó để lấy service chưa tồn tại.

Ví dụ thêm nhiều listener thuộc các kiểu sự kiện khác nhau:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

ApplicationListener<ApplicationStartingEvent> starting =
        event -> System.out.println("starting");

ApplicationListener<ApplicationReadyEvent> ready =
        event -> System.out.println("ready");

app.addListeners(starting, ready);
app.run(args);
```

Đây là **mã minh họa để ghép vào `main`**; cần import và lớp nguồn thực tế. Vì varargs có dạng `ApplicationListener<?>...`, các listener typed khác nhau có thể nằm trong cùng một lời gọi.

**Thời điểm bắt buộc:** gọi `addListeners` **trước `run`** nếu cần nhận các sự kiện bootstrap đầu tiên. Nếu gọi sau khi `run` đã trả về thì các sự kiện sớm của lần khởi động ấy đã xảy ra; thêm một listener vào đối tượng `SpringApplication` lúc đó **không phát lại** lịch sử sự kiện.

## 3. Các sự kiện Spring Boot và tài nguyên có tại mỗi mốc

Spring Boot 3.3 công bố những sự kiện quan trọng theo thứ tự sau trong quá trình `SpringApplication.run(...)`:

| Thứ tự | Sự kiện | Tài nguyên/tình trạng | Listener nên làm gì |
|---|---|---|---|
| 1 | `ApplicationStartingEvent` | Mới bắt đầu; `Environment` và `ApplicationContext` chưa được chuẩn bị | Ghi dấu mốc rất sớm, đọc arguments, thiết lập việc quan sát bootstrap phù hợp |
| 2 | `ApplicationEnvironmentPreparedEvent` | Đã có `ConfigurableEnvironment`, context chưa tạo | Quan sát/tác động môi trường với nhận thức về thứ tự listener và property sources |
| 3 | `ApplicationContextInitializedEvent` | Context đã tạo và initializers đã chạy; các bean definitions ứng dụng chưa tải | Quan sát trạng thái context ban đầu |
| 4 | `ApplicationPreparedEvent` | Bean definitions chính đã tải, context chưa `refresh` | Chẩn đoán trước khi refresh, không dựa vào singleton nghiệp vụ đã khởi tạo |
| 5 | `ApplicationStartedEvent` | Context đã refresh, runner chưa được gọi | Quan sát mốc started và các bean đã khởi tạo thông thường |
| 6 | `AvailabilityChangeEvent` với `LivenessState.CORRECT` | Thông báo ứng dụng được coi là live | Quan sát liveness khi cần |
| 7 | `ApplicationRunner` / `CommandLineRunner` | Các runner được thực thi, đây **không phải** ApplicationEvent | Thực hiện công việc khởi tạo cần hoàn thành trước ready |
| 8 | `ApplicationReadyEvent` | Các runner đã được gọi/hoàn tất thành công | Quan sát mốc hoàn tất chuỗi startup |
| 9 | `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC` | Thông báo trạng thái ready mặc định | Quan sát readiness |

`ApplicationFailedEvent` được phát **khi khởi động gặp exception**; nó không phải một mốc thành công bắt buộc chạy cuối chuỗi. Nếu thất bại xảy ra quá sớm, `ApplicationContext` của sự kiện này **có thể bằng `null`**.

Ngoài những sự kiện trong bảng còn có sự kiện Spring Framework `ContextRefreshedEvent` và, với ứng dụng Web phù hợp, `WebServerInitializedEvent`. Các sự kiện này xảy ra trong giai đoạn context được làm mới, không nên nhầm chúng với `ApplicationReadyEvent`.

Có hai mốc được người học hay nhầm:

- **`ApplicationStartedEvent`:** context đã refresh, nhưng `ApplicationRunner` và `CommandLineRunner` chưa chạy.
- **`ApplicationReadyEvent`:** phát sau các runner; đây là mốc muộn hơn. Với quy trình mặc định, thay đổi readiness sang `ACCEPTING_TRAFFIC` được phát ngay sau sự kiện Ready.

Đăng ký listener sớm bằng `addListeners(...)` có thể giúp một listener phù hợp quan sát **cả sự kiện sớm lẫn muộn**. Nó không biến các sự kiện đó thành callback có cùng điều kiện tài nguyên.

### Mốc sớm nhất không có ApplicationContext

`ApplicationStartingEvent` chứa các thông tin bootstrap như `SpringApplication` và `String[] args`, nhưng **không** cung cấp một context ứng dụng đã refresh. Đừng gọi `event.getApplicationContext()` trên sự kiện không có phương thức đó, và đừng tự tạo service nghiệp vụ chỉ để chạy logic khởi tạo ở đây.

Ở `ApplicationEnvironmentPreparedEvent`, bạn đã có:

```java
ConfigurableEnvironment env = event.getEnvironment();
```

Tuy nhiên, khi một listener nhận sự kiện này, mức độ hoàn tất của từng property source còn phụ thuộc thứ tự các listener và bộ xử lý môi trường. Đặc biệt, đừng suy đoán rằng mọi cấu hình ngoại vi đã được tải đúng thứ tự ở một listener bất kỳ chỉ dựa trên tên của sự kiện. Nếu cần **thêm nguồn cấu hình sớm để ảnh hưởng quá trình tạo bean**, `EnvironmentPostProcessor` thường thể hiện nhiệm vụ rõ hơn.

## 4. Cách đăng ký typed listener chuẩn và an toàn

### Cách A — lambda với một loại sự kiện

Khi chỉ cần một sự kiện, lambda ngắn và có kiểu rõ ràng:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

ApplicationListener<ApplicationStartingEvent> listener = event -> {
    System.out.println("Số đối số: " + event.getArgs().length);
};

app.addListeners(listener);
app.run(args);
```

`getArgs()` thuộc `SpringApplicationEvent` và trả về các arguments dùng cho lần chạy. Điều này **không** có nghĩa đã có `ApplicationArguments` bean; ở giai đoạn Starting chưa có bean được quản lý bằng context.

Cũng có thể truyền listener được ép kiểu vào thẳng `addListeners`:

```java
app.addListeners(
        (ApplicationListener<ApplicationStartingEvent>) event -> {
            System.out.println("Starting: " + event.getArgs().length);
        });
```

Giữ đúng generic `ApplicationListener<ApplicationStartingEvent>`. Nếu dùng lambda không có kiểu đích rõ ràng, Java có thể không suy luận được kiểu sự kiện như bạn mong đợi.

### Cách B — một lớp listener tách riêng

Phù hợp khi cần xử lý lỗi, nhiều công đoạn và có unit test:

```java
package com.example.listener;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartingTraceListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Bootstrap args: " + event.getArgs().length);
    }
}
```

Đăng ký trong `main`:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new StartingTraceListener());
app.run(args);
```

Lớp `StartingTraceListener` có thể được tạo bằng constructor Java thông thường, không cần `@Component`. Nó chạy ở giai đoạn rất sớm nên **không nên phụ thuộc vào service Spring hoặc database đã được tạo**.

### Cách C — nhiều loại sự kiện với ApplicationListener<ApplicationEvent>

Một listener có thể triển khai `ApplicationListener<ApplicationEvent>` rồi phân loại sự kiện bằng `instanceof`. Cách này rất hữu ích khi muốn in **một timeline** từ Starting tới Ready trong cùng một lần chạy. Vì nhận nhiều kiểu Spring `ApplicationEvent`, nó có thể được gọi với cả những sự kiện không liên quan; chỉ xử lý các kiểu cần thiết và bỏ qua phần còn lại.

Lưu ý: `ApplicationListener<ApplicationEvent>` khác `ApplicationListener<ApplicationStartingEvent>`. Loại thứ nhất nhận phạm vi rộng; loại thứ hai chỉ thích hợp cho một sự kiện. Không dùng generic rộng tùy tiện nếu mục tiêu chỉ là một callback hẹp.

## 5. Vì sao listener khai báo bằng @Bean/@Component/@EventListener thường quá muộn?

Ví dụ:

```java
@Component
public class StartingListenerBean {

    @EventListener(ApplicationStartingEvent.class)
    public void tooLate() {
        System.out.println("Không xuất hiện trong khởi động bình thường");
    }
}
```

Spring chỉ tìm thấy bean và đăng ký các method `@EventListener` trong quá trình tạo/refresh context. Đến lúc đó `ApplicationStartingEvent` đã được phát từ trước. Spring **không lưu lịch sử mọi startup event để tự phát lại** cho listener vừa xuất hiện.

Điều tương tự áp dụng với bean `ApplicationListener<ApplicationEnvironmentPreparedEvent>`:

```java
@Bean
ApplicationListener<ApplicationEnvironmentPreparedEvent> environmentListener() {
    return event ->
            System.out.println("Đã quan sát environment");
}
```

Bean `ApplicationListener` này sẽ được tạo **sau** sự kiện EnvironmentPrepared của lần bootstrap hiện tại, nên nó không phải cách đăng ký đủ sớm cho sự kiện ấy.

**Nhưng không nên kết luận bean listener là vô dụng.** Với `ApplicationReadyEvent` hoặc những sự kiện sau khi context đã refresh, bean listener hoặc method `@EventListener` rất phù hợp và còn được hưởng dependency injection.

Bảng chọn nhanh:

| Nhu cầu | Cách đăng ký nên ưu tiên | Vì sao? |
|---|---|---|
| Quan sát `ApplicationStartingEvent` | `SpringApplication.addListeners(...)` trước `run` | Bean chưa tồn tại |
| Quan sát `ApplicationEnvironmentPreparedEvent` | `addListeners(...)`, builder hoặc `spring.factories` | Context chưa tạo |
| Quan sát các mốc khởi tạo context rất sớm | `addListeners(...)` | Đăng ký trước quá trình refresh |
| Dùng service trong sự kiện `ApplicationReadyEvent` | Bean `@EventListener` / listener bean | Context và service đã được tạo |
| Bắt lỗi startup, kể cả lỗi trước khi context tạo | Listener đăng ký sớm cho `ApplicationFailedEvent` | Không giả định có bean |
| Chạy tác vụ nghiệp vụ phải xong trước ready | `ApplicationRunner` hoặc `CommandLineRunner` | Có thể dùng service và phản ánh mốc ready |
| Chỉnh sửa property source trước bootstrap | `EnvironmentPostProcessor` | Chuyên trách xử lý Environment |

Một listener đăng ký bằng tay vẫn có thể nhận Ready. Tuy nhiên, nếu mục đích cần truy cập một repository/service Spring tại Ready, việc dùng listener bean thường dễ quản lý hơn vì có constructor injection chuẩn.

## 6. Ví dụ hoàn chỉnh Java 17+ / Spring Boot 3.3: theo dõi các sự kiện trước và sau context

Bài thực hành dưới đây thực sự dùng `SpringApplication.addListeners(...)` **trước `run`**, quan sát thứ tự các sự kiện, so sánh với một method `@EventListener` trên bean và thử một nhánh startup thất bại. Không cần HTTP server, database hay dependency ngoài Spring Boot starter.

### 6.1. Cấu trúc dự án

```text
early-listener-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/earlylistener/
    ├── EarlyListenerApplication.java
    └── BootTimelineListener.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'early-listener-demo'
```

**`build.gradle`** (Gradle Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

Ví dụ hướng tới Spring Boot **3.3.x** và Java 17+. Nếu bạn đã có project Spring Boot, giữ các phiên bản dependency/plugin được dự án quản lý. Để chạy `./gradlew`/`gradlew.bat` cần một Gradle Wrapper có sẵn (ví dụ project tạo bằng Spring Initializr); các file Wrapper không tự xuất hiện chỉ vì viết `build.gradle`.

### 6.2. Listener đăng ký sớm, nhận nhiều loại sự kiện

**`src/main/java/com/example/earlylistener/BootTimelineListener.java`:**

```java
package com.example.earlylistener;

import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class BootTimelineListener
        implements ApplicationListener<ApplicationEvent> {

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            System.out.println("00. ApplicationStartingEvent");
        } else if (event instanceof ApplicationEnvironmentPreparedEvent e) {
            System.out.println("01. Environment available = "
                    + (e.getEnvironment() != null));
        } else if (event instanceof ApplicationContextInitializedEvent e) {
            System.out.println("02. Context initialized = "
                    + (e.getApplicationContext() != null));
        } else if (event instanceof ApplicationPreparedEvent) {
            System.out.println("03. ApplicationPreparedEvent");
        } else if (event instanceof ApplicationStartedEvent) {
            System.out.println("04. ApplicationStartedEvent");
        } else if (event instanceof ApplicationReadyEvent) {
            System.out.println("06. ApplicationReadyEvent (early listener)");
        } else if (event instanceof ApplicationFailedEvent e) {
            System.out.println("FAIL. ApplicationFailedEvent: "
                    + e.getException().getClass().getSimpleName());
            System.out.println("FAIL. Context exists = "
                    + (e.getApplicationContext() != null));
        }
    }
}
```

Các nhánh `instanceof` có biến mẫu `e` là cú pháp Java 17 hợp lệ. Listener chỉ in thông báo; nó **không gọi `getBean` và không cần DI** ở giai đoạn bootstrap. Nếu gặp một `ApplicationEvent` khác, phương thức không in gì. Riêng nhánh Failed đọc exception từ `getException()`, kiểm tra context qua `null` trước khi dùng: nếu lỗi rất sớm, context có thể chưa được tạo.

### 6.3. SpringApplication đăng ký listener trước khi run

**`src/main/java/com/example/earlylistener/EarlyListenerApplication.java`:**

```java
package com.example.earlylistener;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class EarlyListenerApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EarlyListenerApplication.class);

        // Chọn ứng dụng non-web để thực hành không mở cổng HTTP.
        application.setWebApplicationType(WebApplicationType.NONE);

        // Điểm then chốt: phải đăng ký TRƯỚC application.run(args).
        application.addListeners(new BootTimelineListener());

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // Lúc này runner và ApplicationReadyEvent đã được xử lý.
        }
    }

    @Bean
    ApplicationRunner startupTask() {
        return arguments -> {
            System.out.println("05. ApplicationRunner");

            if (arguments.containsOption("demo.fail")) {
                throw new IllegalStateException("demo startup failure");
            }
        };
    }

    // Method nằm trong bean nên chỉ bắt được event giai đoạn muộn.
    @EventListener(ApplicationReadyEvent.class)
    public void readyFromBean() {
        System.out.println("06. ApplicationReadyEvent (@EventListener bean)");
    }
}
```

Đoạn `@EventListener(ApplicationReadyEvent.class)` thuộc bean cấu hình ứng dụng, được Spring phát hiện khi context khởi tạo. Listener đăng ký sớm và method bean **cùng có thể** nhận Ready, nhưng thứ tự tương đối giữa **hai callback cùng loại sự kiện** không được bài này mặc định cố định.

Lý do dùng `try-with-resources`: trong demo non-web, nó đóng context ngay sau `run` để dọn tài nguyên. Với server Web thực tế, không nên tự đóng context ngay sau startup nếu mục tiêu là tiếp tục phục vụ HTTP.

### 6.4. Chạy ví dụ

Linux/macOS trong thư mục đã có Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Các dòng **do mã ví dụ tự in** sẽ xuất hiện theo trình tự nhóm mốc sau (Spring Boot/Gradle có thể in thêm banner và log ở giữa):

```text
00. ApplicationStartingEvent
01. Environment available = true
02. Context initialized = true
03. ApplicationPreparedEvent
04. ApplicationStartedEvent
05. ApplicationRunner
06. ApplicationReadyEvent (early listener)
06. ApplicationReadyEvent (@EventListener bean)
```

**Ngoại lệ về thứ tự hai dòng cuối:** vì hai listener xử lý **cùng `ApplicationReadyEvent`**, hai dòng bắt đầu bằng `06.` có thể xuất hiện theo thứ tự ngược. Dữ liệu có tính xác định ở đây là chuỗi **Starting → EnvironmentPrepared → ContextInitialized → Prepared → Started → Runner → Ready**; không phải thứ tự ưu tiên giữa hai callback cùng sự kiện.

Tại sao kết quả minh chứng `addListeners` đăng ký đủ sớm?

- Dòng **00** và **01** được in khi context chưa tồn tại, nên một bean listener mới tạo ở pha refresh không thể là nguồn phát hai dòng đó.
- Dòng **02** chứng minh đã có `ConfigurableApplicationContext` nhưng lúc này chưa nạp hết bean definitions.
- Dòng **04** chạy trước runner; dòng **05** là runner; dòng **06** chỉ xuất hiện sau runner hoàn tất.
- Hai dòng Ready cho thấy listener được gắn từ `SpringApplication` **tiếp tục hoạt động ở pha muộn**, song song với listener theo cơ chế bean.

### 6.5. Thử khởi động thất bại

Vì ví dụ chứa `ApplicationRunner` có nhánh lỗi, có thể chạy:

```bash
./gradlew bootRun --args='--demo.fail'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.fail"
```

Trong tình huống này:

- Các sự kiện Starting, EnvironmentPrepared, ContextInitialized, Prepared và Started vẫn đã xảy ra trước khi runner chạy.
- Runner in `05. ApplicationRunner` rồi ném `IllegalStateException`.
- Spring Boot phát `ApplicationFailedEvent`; listener gắn sớm có thể ghi nhận lỗi và context đang tồn tại hay chưa.
- **Không có `ApplicationReadyEvent` của lần chạy thất bại đó**, vì runner chưa hoàn tất thành công.
- Tác vụ Gradle `bootRun` thường báo build/task thất bại do JVM ứng dụng kết thúc không thành công. Đọc stack trace gốc để biết nguyên nhân thực sự.

Một đoạn log của listener trong nhánh lỗi có thể trông như:

```text
04. ApplicationStartedEvent
05. ApplicationRunner
FAIL. ApplicationFailedEvent: IllegalStateException
FAIL. Context exists = true
```

Log trên minh họa điều quan trọng trong **trường hợp lỗi có chủ ý trong runner**; các dòng khác, thời điểm log và cách Spring báo ngoại lệ phụ thuộc môi trường. Nếu lỗi xảy ra sớm hơn cả lúc tạo context, `FAIL. Context exists` có thể là `false`.

**Đừng dựa vào listener Failed để chắc chắn có quyền dùng repository, data source hoặc dịch vụ từ context.** Cơ chế bắt lỗi bootstrap phải xử lý được cả trường hợp bean chưa được khởi tạo.

## 7. Phân biệt addListeners với những cách đăng ký listener khác

### 7.1. SpringApplicationBuilder.listeners(...)

Khi dùng builder, có thể đăng ký sớm tương đương:

```java
new SpringApplicationBuilder(EarlyListenerApplication.class)
        .web(WebApplicationType.NONE)
        .listeners(new BootTimelineListener())
        .run(args);
```

Đây là một **phương án bootstrap thay thế**, không nên chạy đồng thời với `main` của ví dụ phần 6. Cần import `org.springframework.boot.builder.SpringApplicationBuilder`, `WebApplicationType` và lớp listener. Builder tiện khi cần chuỗi cấu hình fluent hoặc cấu trúc parent/child contexts.

### 7.2. META-INF/spring.factories để tự động đăng ký

Nếu bạn phát triển một thư viện cần theo dõi sự kiện bootstrap của **mọi ứng dụng** sử dụng nó, không thể yêu cầu tất cả ứng dụng gọi `addListeners(...)` trong `main`. Spring Boot 3.3 hỗ trợ cơ chế đăng ký listener bằng `spring.factories`.

Đặt **`src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.context.ApplicationListener=com.example.earlylistener.BootTimelineListener
```

Vì `BootTimelineListener` trong ví dụ có constructor mặc định không đối số, nó có thể được Spring Boot tạo khi tải cơ chế listener từ factories. Khi thử cách này, **bỏ dòng `application.addListeners(new BootTimelineListener())`** để không đăng ký cùng chức năng từ hai đường và gây nhiễu kết quả.

Một thư viện thực tế phải đảm bảo class listener và resource `META-INF/spring.factories` được đóng gói trong JAR. Đây là **cơ chế mở rộng Spring Boot qua classpath**, không có nghĩa `@ComponentScan` có thể phát hiện mọi listener sớm. Trong Spring Boot 3.3, khóa cho `ApplicationListener` vẫn là `org.springframework.context.ApplicationListener`.

### 7.3. @Component, @Bean và @EventListener

Những cơ chế dựa trên Spring bean vẫn là lựa chọn tự nhiên **khi sự kiện đến sau khi context khởi tạo**:

```java
@Component
public class ReadyNotification {

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("Application ready");
    }
}
```

Đây là **lớp minh họa riêng**, cần import `Component`, `EventListener`, `ApplicationReadyEvent` và đặt trong package được quét. Nó khác listener bootstrap ở chỗ Spring có thể dùng DI trong bean.

Nếu chỉ muốn xử lý `ApplicationReadyEvent` bằng một service đã được Spring tiêm, bean listener thường đơn giản hơn tự tạo listener trong `main` rồi tìm cách lấy service trước thời điểm phù hợp.

### 7.4. addListeners và addInitializers không phải cùng một loại hook

`SpringApplication.addInitializers(...)` nhận `ApplicationContextInitializer<?>`, dùng để tùy biến context **sau khi context được tạo nhưng trước refresh**. `addListeners(...)` nhận `ApplicationListener<?>`, dùng để **nghe sự kiện** ở nhiều mốc.

So sánh:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

app.addInitializers(context ->
        System.out.println("Initializer: context đã tồn tại"));

app.addListeners(
        (ApplicationListener<ApplicationStartingEvent>) event ->
                System.out.println("Listener: context chưa tồn tại"));

app.run(args);
```

Đây là mã tích hợp, chưa phải project độc lập; cần import và lớp nguồn thích hợp. Sự khác nhau là *đối tượng đầu vào* và *vòng đời*: initializer dùng context, còn listener Starting không thể dùng context.

Nếu cần thay đổi property sources rất sớm, cân nhắc `EnvironmentPostProcessor`; nếu cần tạo bean definitions, cân nhắc context initializer hoặc registry post-processor phù hợp. Listener không phải giải pháp chung cho mọi hình thức can thiệp.

## 8. Listener bootstrap có được Dependency Injection không?

Một tình huống dễ gây ngộ nhận:

```java
public class WrongEarlyListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Autowired
    private PaymentService paymentService;

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        paymentService.pay();  // Dễ null hoặc không hợp lệ!
    }
}
```

Đoạn này chỉ minh họa **cách dùng sai**, không phải ví dụ cần chạy: `PaymentService`, `@Autowired` và các import không được cung cấp. Vấn đề không chỉ là có annotation `@Autowired`; ngay cả khi sau này bạn tự tạo instance, **tại thời điểm Starting chưa có bean PaymentService được container khởi tạo**. Listener bạn tạo bằng `new WrongEarlyListener()` cũng không tự trở thành bean do Spring quản lý.

Cách thiết kế tốt hơn là **chia trách nhiệm**:

- **Listener sớm:** ghi metadata khởi động, arguments, hoặc xử lý thông tin nền tảng độc lập với bean.
- **EnvironmentPostProcessor / initializer:** cấu hình môi trường/context bằng API chuyên dụng, đúng mốc.
- **ApplicationRunner hoặc bean @EventListener(ApplicationReadyEvent.class):** dùng service đã được tiêm phụ thuộc để thực hiện nghiệp vụ ở mốc muộn.

Nếu cần truyền dữ liệu không phụ thuộc Spring từ main vào listener sớm, dùng constructor injection **bằng Java thuần**:

```java
public final class BootstrapTagListener
        implements ApplicationListener<ApplicationStartingEvent> {

    private final String tag;

    public BootstrapTagListener(String tag) {
        this.tag = tag;
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Bootstrap tag: " + tag);
    }
}
```

Sau đó:

```java
app.addListeners(new BootstrapTagListener("batch-worker"));
```

Hai đoạn là mã minh họa cần import Spring; dữ liệu `tag` do `main` cung cấp ở thời điểm tạo listener, **không phải Spring bean được tiêm từ context**.

## 9. Listener được gọi ở thread nào? Có nên dùng để làm việc nặng?

Spring Boot nói chung phát các sự kiện startup đến listeners bằng cơ chế Spring Framework; trong cấu hình mặc định, callback thường chạy **đồng bộ trên luồng phát sự kiện** (thường là luồng khởi động). Điều này ảnh hưởng trực tiếp đến hiệu năng và độ an toàn.

Nếu callback Starting thực hiện:

```java
Thread.sleep(10_000);
```

thì công việc bootstrap tiếp theo có thể bị giữ lại khoảng 10 giây. Đoạn này **chỉ minh họa tác động của thao tác chặn**, không phải lời khuyên chạy `sleep` trong listener; nếu dùng trong Java thật phải xử lý `InterruptedException`.

Những việc không nên làm trong listener sớm:

- Gọi HTTP/database một cách đồng bộ mà không có timeout, khiến hệ thống chậm hoặc treo từ lúc chưa có logging đầy đủ.
- Dùng `@Autowired` để lấy service khi context chưa tồn tại.
- Dựa vào `Environment` hoặc bean ở mốc `ApplicationStartingEvent`.
- Lấy một listener làm worker nền, tự tạo thread không được quản lý và bỏ qua xử lý shutdown/error.
- Ném exception như cơ chế điều hướng bình thường mà không rõ tác động đến tiến trình khởi động.

Khi việc **phải hoàn thành trước khi ứng dụng ready**, `ApplicationRunner`/`CommandLineRunner` thường có ranh giới rõ hơn và sử dụng service an toàn hơn. Khi công việc cần thực thi **sau khi ready**, chọn hook và cơ chế async/scheduling phù hợp với yêu cầu. Dù dùng loại nào, cần quản lý timeout và tính lặp lại của công việc.

### Dùng System.out ở giai đoạn rất sớm có gì khác dùng logger?

`ApplicationStartingEvent` xảy ra trước khi logging ứng dụng được cấu hình đầy đủ. `System.out.println` trong bài thực hành cho phép người học nhìn thấy dấu mốc một cách đơn giản. Ở ứng dụng thực tế, nếu cần log bootstrap rất sớm, hãy dùng cơ chế logging phù hợp với Spring Boot hoặc chiến lược deferred logging được hỗ trợ, tránh mặc định cho rằng mọi logger đã hoạt động theo cấu hình cuối cùng ngay từ Starting.

Cũng đừng ghi secrets, token, password hay toàn bộ nội dung CLI arguments vào log. `event.getArgs()` có thể chứa thông tin nhạy cảm trong một số cách triển khai; ví dụ của bài chỉ in **số lượng** đối số.

## 10. Thứ tự listener, trùng lặp và ứng dụng nhiều context

### 10.1. Thứ tự giữa các sự kiện khác thứ tự giữa các listener

Spring Boot bảo đảm thứ tự **mốc sự kiện lifecycle** theo đường đi startup chuẩn. Nhưng nếu có **nhiều listeners cùng loại sự kiện**, thứ tự callback của chúng có thể phụ thuộc vào mức ưu tiên `Ordered`, `@Order`, cơ chế đăng ký và hạ tầng phát sự kiện.

Một listener tự viết có thể triển khai `Ordered`:

```java
public final class FirstStartingListener
        implements ApplicationListener<ApplicationStartingEvent>, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Early observer");
    }
}
```

Đây là lớp minh họa cần import `ApplicationListener`, `Ordered` và `ApplicationStartingEvent`. `HIGHEST_PRECEDENCE` đặt mức ưu tiên rất cao so với các listener khác trong cùng cơ chế sắp xếp, nhưng **không** làm cho `ApplicationReadyEvent` xảy ra trước `ApplicationStartedEvent`. Cũng không nên chọn thứ tự cao nhất một cách tùy tiện rồi vô tình chạy trước hạ tầng Spring Boot cần thiết.

### 10.2. Tránh đăng ký cùng logic qua nhiều cơ chế

Giả sử vừa gọi:

```java
app.addListeners(new BootTimelineListener());
```

vừa khai báo cùng lớp trong `META-INF/spring.factories`. Khi đó có nguy cơ tạo **hai instance listener riêng** và nhận log hoặc xử lý lặp. Không nên dựa vào tập hợp listener để suy luận rằng hai instance khác nhau được tự hợp nhất theo class.

Nếu một action có side effect, lặp hai lần có thể gây lỗi. Chọn một đường đăng ký phù hợp hoặc thiết kế callback idempotent khi cần.

### 10.3. Parent/child ApplicationContext

Trong cấu trúc `SpringApplicationBuilder.parent(...).child(...)` hoặc hệ thống có nhiều context, một sự kiện có thể được **publish hoặc propagate** từ child lên ancestor. Listener có thể nhận **nhiều sự kiện cùng loại**, thậm chí một số mốc phát ra từ nhiều context.

Không nên dùng một listener để suy luận “đời ứng dụng chỉ có đúng một ApplicationReadyEvent” trong mọi kiến trúc. Nếu listener xử lý một context cụ thể, có thể đối chiếu `event.getApplicationContext()` với context mong muốn **trên những loại sự kiện thực sự có phương thức đó**. Với `ApplicationStartingEvent`, context chưa có, nên phép so sánh đó không áp dụng.

Điều này cũng liên quan đến hot restart trong môi trường phát triển: mỗi lần khởi động là một vòng đời mới, không phải hệ thống phát lại cùng sự kiện cho listener cũ trong mọi trường hợp.

## 11. Những lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Cách sửa/kiểm chứng |
|---|---|---|
| Listener `@EventListener(ApplicationStartingEvent.class)` không in gì | Bean được tạo sau khi Starting đã phát | Đăng ký với `SpringApplication.addListeners(...)` trước `run` hoặc dùng `spring.factories` |
| `ApplicationListener<ApplicationEnvironmentPreparedEvent>` khai báo bằng `@Bean` không hoạt động | Bean chưa tồn tại khi event đến | Chuyển sang đăng ký sớm qua bootstrap |
| Có listener nhưng không nhận được sự kiện đầu tiên | `addListeners(...)` gọi muộn, hoặc event generic không đúng | Đưa đăng ký lên trước `run`; kiểm tra type listener |
| Listener báo thiếu bean hoặc `NullPointerException` | Cố dùng service/context quá sớm hoặc tự `new` nhưng kỳ vọng `@Autowired` | Giữ callback sớm độc lập với bean, chuyển nghiệp vụ qua runner/ready |
| Cố gọi `getApplicationContext()` trong Starting | Loại event không cung cấp context | Dùng đúng API của từng event, không ép kiểu sai |
| Xử lý Failed nhưng `getApplicationContext()` là null | Lỗi xảy ra trước khi context được tạo | Viết nhánh null-safe, dùng exception để chẩn đoán |
| Log sự kiện xuất hiện hai lần | Đăng ký ở main và factories, hoặc nhiều context | Kiểm tra mọi đường đăng ký, classloader/context và propagation |
| Thứ tự in log giữa hai listener khác nhau qua lần chạy | Có nhiều callback cùng event, thứ tự đăng ký/ưu tiên khác nhau | Dùng `Ordered` khi thật sự cần và kiểm tra theo chính context |
| Listener chậm khiến startup chậm | Callback đồng bộ có thao tác I/O hoặc `sleep` | Giảm tác vụ tại bootstrap, dùng runner/service thích hợp |
| Listener ném exception và ứng dụng không chạy | Exception không được xử lý trong đường bootstrap | Đọc stack trace, chỉ fail-fast khi có lý do rõ |
| Không nhận Ready sau Started | Runner ném exception hoặc chưa kết thúc | Kiểm tra `ApplicationRunner`/`CommandLineRunner` và lỗi startup |
| Event listener trông như không chạy | Spring Boot logging chưa thiết lập hoặc mức log bị lọc | Đặt dấu mốc kiểm chứng phù hợp, xem cấu hình logging và thời điểm |
| Dùng `setListeners(...)` rồi mất listener khác | Đã thay thay vì thêm tập listeners | Dùng `addListeners(...)` hoặc quản lý tập cấu hình cẩn thận |

Quy trình xử lý ngắn:

1. **Xác định loại sự kiện**: Starting, EnvironmentPrepared, Initialized, Prepared, Started, Ready hay Failed.
2. **Xác định lúc listener được đăng ký**: trước `run` hay sau khi bean được tạo?
3. **Xác định dữ liệu mà callback truy cập**: args, Environment, context, bean hay hệ thống ready.
4. **Xác định phạm vi đăng ký**: một lần qua main, factories, builder, bean, hay nhiều context.
5. **Kiểm tra exception và log**: một lỗi callback sớm có thể làm bootstrap thất bại; không coi việc thiếu log Ready là chứng minh listener sai.
6. **Kiểm tra phiên bản API và import**: dùng đúng `ApplicationStartingEvent` của Spring Boot hiện đại, không lấy ví dụ sự kiện startup từ các phiên bản Spring Boot rất cũ.

## 12. Thực hành theo từng bước

Dùng project `early-listener-demo` ở phần 6, giữ nguyên mã ban đầu trước mỗi thử nghiệm.

**Bài 1 — xác nhận đăng ký sớm.** Chạy nguyên bản. Xác nhận có các mốc `00, 01, 02, 03` trước `04` và `05`. Giải thích tại sao những mốc đầu không thể do một bean `@EventListener` mới tạo trong context quan sát được.

**Bài 2 — chuyển listener sang bean.** Bỏ `application.addListeners(new BootTimelineListener())` và thử khai báo `@Bean BootTimelineListener` trong lớp `@SpringBootApplication`. Quan sát không còn các mốc sớm do listener này in; nhưng nó vẫn có thể nhận sự kiện muộn sau khi bean được tạo. Không nhầm hiện tượng đó với việc `BeanPostProcessor` làm “mất” event.

**Bài 3 — chỉ bắt một sự kiện.** Viết `ApplicationListener<ApplicationStartingEvent>` dạng lambda và đăng ký bằng `addListeners(...)`. So sánh số callback được gọi với implementation rộng `ApplicationListener<ApplicationEvent>` của bài chính.

**Bài 4 — đưa callback vào đường factories.** Tạo `META-INF/spring.factories` theo phần 7. Bỏ đường đăng ký bằng main rồi chạy lại, xác nhận các sự kiện sớm vẫn được log. Giải thích ưu điểm với code thư viện.

**Bài 5 — kiểm tra lỗi startup.** Chạy `bootRun --args='--demo.fail'`. Xác nhận có `ApplicationFailedEvent` và không có `ApplicationReadyEvent`. Giải thích tại sao listener bắt Failed phải xử lý context có thể null ở những lỗi xảy ra sớm hơn runner.

**Bài 6 — kiểm tra công việc dài trong runner.** Thêm một thao tác chờ có kiểm soát trong runner; quan sát Ready đến sau khi runner kết thúc. Cần xử lý interruption nếu dùng `Thread.sleep`. Không chuyển việc chờ dài sang Starting chỉ để thấy dòng log chạy đầu tiên.

**Bài 7 — kiểm tra việc đăng ký trùng.** Thử đăng ký một listener qua cả factories và main trên một bản test; quan sát callback có thể chạy nhiều lần. Khôi phục một đường đăng ký trước khi đưa vào sản xuất.

### Câu hỏi tự kiểm tra

1. Vì sao `@EventListener(ApplicationStartingEvent.class)` trên bean không thấy Starting của lần chạy hiện tại?
2. `addListeners(...)` phải được gọi **trước mốc nào**?
3. `ApplicationStartingEvent` cho phép dùng `Environment` hoặc service đã `@Autowired` chưa?
4. Khác nhau giữa `addListeners(...)` và `addInitializers(...)` là gì?
5. Tại sao `ApplicationStartedEvent` không đồng nghĩa `ApplicationReadyEvent`?
6. Nếu runner ném exception, listener sớm có thể nhận sự kiện nào và vì sao không nhận Ready?
7. Khi nào nên chọn `META-INF/spring.factories` thay vì sửa `main` của từng ứng dụng?
8. Vì sao listener xử lý bootstrap không nên mặc định thực hiện network I/O kéo dài?

Khi có thể trả lời và chứng minh những câu này bằng dự án thực hành, bạn đã biết **đăng ký listener đủ sớm**, **chọn dữ liệu đúng với giai đoạn** và **tránh nhầm listener ứng dụng với bean chưa tồn tại**.

## Tài liệu chính thức

- Spring Boot 3.3, `SpringApplication` JavaDoc, các phương thức `addListeners`, `getListeners`, `setListeners`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3, SpringApplication Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `ApplicationStartingEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartingEvent.html
- Spring Boot 3.3, `ApplicationEnvironmentPreparedEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
- Spring Boot 3.3, `ApplicationFailedEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html

**Kết luận:** `SpringApplication.addListeners(...)` cho phép gắn `ApplicationListener` **trước khi context ra đời**, vì vậy listener có thể quan sát các sự kiện đầu tiên mà `@Bean` hay `@EventListener` không thể bắt kịp trong vòng đời thông thường. Đổi lại, callback sớm chỉ được phép dựa vào dữ liệu thực sự sẵn có; không phải một điểm để truy cập bean Spring, chạy logic nghiệp vụ tùy ý hoặc làm chậm bootstrap không kiểm soát.