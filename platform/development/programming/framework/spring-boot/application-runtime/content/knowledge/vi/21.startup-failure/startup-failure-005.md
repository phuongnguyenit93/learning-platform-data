# ApplicationFailedEvent và giới hạn những tài nguyên còn dùng được khi Spring Boot khởi động thất bại

## 1. Đặt vấn đề: khởi động thất bại không đồng nghĩa vẫn còn một container dùng được

Khi gọi `SpringApplication.run(...)`, Spring Boot đi qua nhiều bước: dựng `Environment`, tạo `ApplicationContext`, nạp bean definitions, refresh context, khởi tạo singleton, mở web server (nếu có), chạy `ApplicationRunner`/`CommandLineRunner` rồi mới công bố trạng thái sẵn sàng. Một exception ở bất kỳ bước quan trọng nào có thể khiến startup thất bại.

Spring Boot có sự kiện `org.springframework.boot.context.event.ApplicationFailedEvent` để **báo rằng một lần khởi động đã thất bại**. Một failure listener có thể lấy exception và ngữ cảnh phần nào về quá trình chạy. Nhưng tại thời điểm đó, không được giả định:

- `ApplicationContext` đã được tạo.
- `ApplicationContext` đã refresh thành công.
- Mọi `@Bean`/`@Component` đã được instantiate.
- `getBean(...)` sẽ trả về một service còn hoạt động.
- `DataSource`, HTTP client hoặc message broker có thể tiếp tục truy vấn.
- Executor có thể nhận task mới.
- Web server đã nhận traffic hoặc readiness đã `ACCEPTING_TRAFFIC`.
- Spring cleanup chưa bắt đầu hoặc chắc chắn sẽ chạy trọn vẹn.

**Quy tắc trọng tâm:** `ApplicationFailedEvent` phù hợp để **ghi nhận chẩn đoán khởi động thất bại**, không phải tín hiệu rằng listener có quyền thực thi thêm nghiệp vụ thông qua những tài nguyên còn sót lại trong context.

Bài học dành cho **Java 17+, Spring Boot 3.3.x và Spring Framework 6.1.x**; phân biệt listener sớm với Spring bean listener, các mức sẵn sàng của tài nguyên, cách cleanup an toàn, lỗi khi dùng `getBean` ở failure callback, và một chương trình Java 17+ chạy được mô phỏng cả lỗi xảy ra **trước khi có context** lẫn lỗi từ `ApplicationRunner` **sau khi context đã refresh**.

## 2. ApplicationFailedEvent là sự kiện gì?

`ApplicationFailedEvent` kế thừa `SpringApplicationEvent`. Theo API Spring Boot 3.3, nó được phát bởi `SpringApplication` khi **không thể hoàn tất quá trình startup**.

Các API cần biết:

```java
ApplicationFailedEvent event;

Throwable error = event.getException();

ConfigurableApplicationContext context =
        event.getApplicationContext();

SpringApplication application = event.getSpringApplication();

String[] args = event.getArgs();
```

Đây là **snippet chỉ minh họa API**, không phải một file độc lập; cần các imports từ Spring Boot/Spring Context. Trong một listener, `event` do Spring Boot truyền vào, không phải tự tạo.

| API | Dữ liệu | Điều cần lưu ý |
| --- | --- | --- |
| `getException()` | `Throwable` gây thất bại | Có thể là wrapper exception; đọc `getCause()` để tìm nguyên nhân gần gốc, nhưng không làm mất thông tin wrapper |
| `getApplicationContext()` | `ConfigurableApplicationContext` hoặc `null` | **Có thể null** nếu thất bại trước khi context được tạo; khác null cũng không chứng minh bean dùng được |
| `getSpringApplication()` | `SpringApplication` đang chạy | Là object cấu hình/khởi động, không phải bean container đã sẵn sàng |
| `getArgs()` | Mảng đối số lúc `run(...)` | Có thể chứa token, mật khẩu hoặc giá trị nhạy cảm; không log nguyên văn |
| `getTimestamp()` | Timestamp event kế thừa từ `ApplicationEvent` | Hữu ích cho chẩn đoán; không đồng nghĩa mốc readiness |

### 2.1. Phân biệt “có tham chiếu context” và “context còn hợp lệ”

Một tham chiếu kiểu `ConfigurableApplicationContext` là một **object Java**. Nó có thể tồn tại ngay cả khi:

- Chưa được refresh.
- Refresh bị hủy giữa chừng.
- Một phần singleton được tạo rồi gặp exception.
- Shutdown/cleanup đang diễn ra.
- Context đã đóng hoặc chưa từng trở thành active.

Vì vậy:

```java
if (event.getApplicationContext() != null) {
    // CHƯA đủ để bảo đảm có thể gọi getBean().
}
```

`context.isActive()` là một tín hiệu về lifecycle context, nhưng **không phải health check mọi bean/dependency** và không đủ để biến failure callback thành nơi tiếp tục hoạt động nghiệp vụ.

### 2.2. ApplicationFailedEvent không phải event báo mọi exception

`ApplicationFailedEvent` nói về **startup failure** trong một lần `SpringApplication.run(...)`. Nó không tự xuất hiện cho mọi trường hợp:

- Một HTTP request sau khi app ready trả 500.
- Một `@Async` task thất bại khi app đang chạy bình thường.
- Một message broker tạm mất kết nối sau startup.
- Một `@Scheduled` method ném exception.
- Một yêu cầu shutdown có chủ đích.
- Một code path nghiệp vụ trả kết quả validation fail.

Những lỗi runtime đó cần exception handling, task error handler, logs/metrics, readiness/liveness hoặc circuit breaker phù hợp; đừng lạm dụng `ApplicationFailedEvent` để giám sát mọi sự cố trong đời sống ứng dụng.

## 3. Các pha startup và mức độ đáng tin của tài nguyên

Sơ đồ đơn giản hóa Spring Boot 3.3:

```text
main()
  |
SpringApplication.run(args)
  |
  +-- ApplicationStartingEvent
  |      Environment chưa sẵn sàng
  |
  +-- ApplicationEnvironmentPreparedEvent
  |      Environment đã có; ApplicationContext chưa tạo
  |
  +-- ApplicationContextInitializedEvent
  |      context đã tạo/được chuẩn bị; chưa load bean definitions
  |
  +-- ApplicationPreparedEvent
  |      bean definitions đã load; chưa bắt đầu refresh
  |
  +-- ApplicationContext.refresh()
  |      tạo BeanFactory infrastructure, singleton beans
  |      web server/clients/pools có thể dần khởi tạo
  |
  +-- ApplicationStartedEvent
  |      refresh xong; runner chưa chạy
  |
  +-- LivenessState.CORRECT
  |
  +-- ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent
  |
  +-- ReadinessState.ACCEPTING_TRAFFIC
  |
  +-- run() trả về context

Nếu có exception trong các giai đoạn startup mà Boot xử lý:
       |
       +--> ApplicationFailedEvent
       +--> chẩn đoán lỗi + dọn dẹp context/tài nguyên (nếu có)
       +--> run() không trả về context thành công
```

Sơ đồ chỉ cho thấy **các mốc thiết yếu**, không bảo đảm failure event luôn được phát đúng một thời điểm vật lý như nhau so với mọi destroy callback tùy biến. Đối với tài nguyên còn dùng được, **pha thất bại quan trọng hơn sự hiện diện của một biến context**.

### 3.1. Thất bại trước khi context được tạo

Ví dụ:

- Cấu hình bootstrap lỗi trước `createApplicationContext()`.
- Không thể chuẩn bị một nguồn cấu hình quan trọng.
- Một initializer rất sớm thất bại.
- Chính strategy tạo context ném exception.

Khi đó `event.getApplicationContext()` **có thể null**. Không thể lấy bean `DataSource`, `Environment` thông qua context hoặc gọi `context.getBean(...)`. Listener chỉ nên dựa trên những dữ liệu sẵn có thật, như exception, thời gian, thông tin app không nhạy cảm và một logger/fallback console mà nó tự sở hữu.

### 3.2. Thất bại trong context refresh

Ví dụ: không tạo được bean, thiếu cấu hình, vòng phụ thuộc không hợp lệ, property binding lỗi, thiếu JDBC driver, hoặc embedded web server không bind được port.

Lúc này Boot đã có thể giữ reference `ApplicationContext`, nhưng context **chưa chắc active/usable**. Một số beans được tạo, số khác chưa; Spring có thể đang hủy những singleton đã tạo thành công trong cleanup. Không được thử “đọc vài bean quan trọng” từ failure listener để xác minh chúng sống hay không.

### 3.3. Thất bại trong ApplicationRunner/CommandLineRunner

Ở giai đoạn này context thường đã refresh, có thể đã phát `ApplicationStartedEvent` và `LivenessState.CORRECT`. Nhưng runner ném exception khiến startup **vẫn thất bại** trước khi Boot đạt `ApplicationReadyEvent` và readiness accepting mặc định.

Một failure listener có thể nhận tham chiếu context **khác null**. Tuy nhiên:

- Boot đang xử lý một lần startup thất bại và sẽ đóng context theo failure path.
- Các tài nguyên đang được dùng có thể bắt đầu dừng.
- Đừng bắt đầu một job mới chỉ vì `context.isActive()` tại một khoảnh khắc trả `true`.
- Không nên coi việc `LivenessState.CORRECT` từng xuất hiện là bằng chứng ứng dụng đã ready.

### 3.4. Sau khi ready, đây không còn là startup failure thông thường

Nếu một web service đã chạy và phục vụ traffic, rồi gặp lỗi trong request hay background task, lỗi đó **không tự chuyển thành ApplicationFailedEvent**. Cần phân loại runtime failure riêng. Với một lỗi nội bộ không thể phục hồi có thể dùng availability/liveness theo contract Boot; với dependency ngoài tạm hỏng cần retry/readiness/circuit breaker phù hợp.

## 4. Tại sao @Component hoặc @EventListener không đủ để bắt lỗi quá sớm?

Một listener được định nghĩa dưới dạng Spring bean:

```java
@Component
public class BeanFailureListener {

    @EventListener
    public void onFailed(ApplicationFailedEvent event) {
        System.err.println(event.getException().getClass().getName());
    }
}
```

Đây là **snippet minh họa**; cần imports `Component`, `EventListener` và `ApplicationFailedEvent`.

Nó chỉ có cơ hội hoạt động nếu bean listener đã được tạo và đăng ký đủ sớm. Nếu thất bại xảy ra **trước khi BeanFactory dựng bean listener**, bạn **không thể trông chờ** callback này được gọi.

Spring Boot hướng dẫn với những events cần bắt từ rất sớm: đăng ký listener trực tiếp với `SpringApplication.addListeners(...)` hoặc `SpringApplicationBuilder.listeners(...)` trước `run(...)`, hoặc khai báo listener được Boot nạp qua `META-INF/spring.factories`.

### 4.1. Cách đáng tin hơn: listener không phụ thuộc Spring beans

```java
SpringApplication application = new SpringApplication(MyApp.class);
application.addListeners(new SafeStartupFailureListener());
application.run(args);
```

Snippet này ở `main`, cần class `MyApp` và `SafeStartupFailureListener` thích hợp. Listener được tạo bằng Java constructor **trước khi Boot bắt đầu chạy**, không cần inject `DataSource`, repository hay `ApplicationContext`.

Với sự kiện thất bại có context `null`, listener này vẫn có thể xử lý vì nó không chờ một Spring bean. Phần demo runnable ở mục 9 dùng chính chiến lược này.

### 4.2. Đăng ký qua META-INF/spring.factories

Một library muốn listener tự được nạp cho những lần khởi động tương ứng có thể khai báo:

```properties
org.springframework.context.ApplicationListener=\
com.example.failure.SafeStartupFailureListener
```

Đây là snippet cho file `src/main/resources/META-INF/spring.factories`. Khi dùng hình thức này, class listener phải có constructor phù hợp để Spring Boot/SpringFactoriesLoader tạo mà không dựa vào một bean context đã khởi tạo. Class name/package phải khớp class thực tế.

Trong demo phần 9, ta dùng **`application.addListeners(...)`**, **không** cần thêm dòng `spring.factories` trên. Nếu đăng ký đồng thời hai đường cho cùng mục đích, có thể thấy xử lý trùng; cần kiểm tra registration thay vì quy hết cho event propagation.

### 4.3. Khi nào có thể dùng bean listener?

Một `@EventListener` trong bean hoàn toàn hữu ích cho những events **sau khi context đã refresh đủ**, nhưng **không phải cơ chế duy nhất hoặc đáng tin cho startup failure cực sớm**.

Khi bắt event để phục vụ telemetry sớm, thiết kế nó có mức dependency **tối thiểu**; tránh autowire service phức tạp chỉ để ghi nhận một exception mà chính service đó có thể là nguyên nhân không tạo được context.

## 5. Cách thiết kế failure listener an toàn

Một failure listener tốt nên làm những việc **không phụ thuộc tài nguyên có thể đã hỏng**:

1. Lấy `Throwable` từ event.
2. Ghi nhận **loại lỗi**, một số metadata đã được kiểm duyệt và thời gian.
3. Phân biệt context `null`/khác null nếu cần.
4. Có thể tìm root cause mà không làm rơi stack trace gốc.
5. Sử dụng logger hoặc một output channel còn hoạt động, không yêu cầu BeanFactory.
6. Kết thúc nhanh, không block startup failure handling.
7. Tránh ném exception mới từ chính listener.
8. Để Spring Boot thực hiện đường cleanup/reporting tiêu chuẩn.

Ngược lại, tránh:

- `context.getBean(OrderService.class).sendAlert()`.
- Mở mới `DataSource` để thử DB trong khi DB đang lỗi.
- Gửi HTTP báo cáo qua client singleton có thể đã đóng.
- Submit task vào `ThreadPoolTaskExecutor` mà Boot đang destroy.
- Gọi `context.refresh()` để “cứu” context lỗi.
- Gọi `System.exit` bên trong listener, cắt ngang cleanup.
- Ghi toàn bộ `event.getArgs()` nếu có thể chứa secrets.
- Chạy retry loop vô hạn hoặc network call không timeout.
- Làm biến mất exception thật bằng một exception thứ cấp do listener gây ra.

### 5.1. Vì sao không nên getBean dù context có tồn tại?

Khi startup fail, container có thể đang ở một trong các trạng thái:

```text
Context chưa tạo     -> không có getBean
Context chưa refresh -> BeanFactory chưa sẵn sàng
Context refresh fail -> một phần bean graph không hợp lệ
Context đang đóng    -> singleton có thể bị destroy
Context đã đóng      -> dùng bean là ngoài lifecycle
```

`context.isActive()` cũng không biến bean thành an toàn: state có thể đổi ngay sau khi check (**time-of-check/time-of-use race**). Và dù context active, một bean có thể chưa tạo được hoặc chính là nơi ném exception.

### 5.2. Logging phải chịu được “logging system chưa khởi tạo trọn”

Trong lỗi xảy ra rất sớm, cấu hình logging phức tạp chưa chắc đã hoàn tất. Một listener tối giản có thể dùng `System.err.println(...)` làm **fallback** nếu phù hợp yêu cầu vận hành. Với production, dùng logging infrastructure được tạo sớm **nhưng không cần context**, được cấu hình chống block và không phụ thuộc backend đang lỗi.

Không cam kết stdout/stderr luôn được ghi ra disk: container/log collector có thể lỗi hoặc bị kill cứng. Việc ghi lỗi quan trọng cần monitoring từ bên ngoài và phân tích nguyên nhân qua logs/stack trace/failure analyzers.

## 6. Exception và root cause: lấy thông tin có kiểm soát

Một lỗi bean có thể được bọc nhiều tầng:

```text
IllegalStateException: Failed to execute ApplicationRunner
    |
    +-- IllegalStateException: BUSINESS_STARTUP_PRECHECK_FAILED

BeanCreationException: Error creating bean
    |
    +-- BeanInstantiationException
             |
             +-- IllegalArgumentException: invalid required setting
```

`event.getException()` cho bạn exception mà Spring Boot báo. Có thể đi theo `getCause()` để tìm lỗi gần gốc:

```java
static Throwable rootCause(Throwable throwable) {
    Throwable current = throwable;
    int hops = 0;
    while (current.getCause() != null
            && current.getCause() != current
            && hops++ < 20) {
        current = current.getCause();
    }
    return current;
}
```

Đây là method Java độc lập có thể đặt trong listener class. Giới hạn số bước để tránh code lỗi hoặc cause chain kỳ lạ. **Không thay thế toàn bộ exception bằng root cause** khi phân tích; wrapper chứa bean name, initialization phase và stack trace rất hữu ích.

Trong production, hạn chế in raw exception message nếu nó chứa property values, JDBC URLs có credentials, file path nhạy cảm hoặc các đối số do người dùng cung cấp. Demo chỉ in message cố định do chính code mẫu tạo ra.

## 7. Hãy để Spring Boot báo lỗi startup theo cơ chế chuẩn

Spring Boot có cơ chế `FailureAnalyzer` và `FailureAnalysisReporter` để cung cấp thông báo dễ hiểu cho một số lỗi startup, ví dụ port đã bị chiếm hoặc lỗi cấu hình. Khi cần hiểu vì sao một bean không được tạo, có thể bật `--debug` hoặc logging của `ConditionEvaluationReportLoggingListener` để xem điều kiện auto-configuration.

**FailureAnalyzer** và **ApplicationFailedEvent listener** phục vụ mục đích khác nhau:

| Cơ chế | Mục đích chính | Có nên gọi bean nghiệp vụ ở đây? |
| --- | --- | --- |
| `ApplicationFailedEvent` | Thông báo có lỗi khi `SpringApplication` startup | Không mặc định, nhất là khi context null/chưa refresh |
| `FailureAnalyzer` | Biến một failure đã biết thành description/action dễ hiểu | Nên phân tích exception, không khởi động lại nghiệp vụ |
| `ConditionEvaluationReport` | Giải thích các điều kiện auto-configuration | Dùng để chẩn đoán, không phải sửa bean tại chỗ |
| `ApplicationRunner` | Thực hiện bước bắt buộc sau refresh, trước ready | Có thể dùng beans khi startup bình thường, nhưng nếu lỗi thì chạy qua failure path |
| `@PreDestroy`/`DisposableBean` | Cleanup tài nguyên đã được tạo theo lifecycle | Chỉ trong phạm vi owner/callback thực sự được gọi |
| `SmartLifecycle.stop(...)` | Phối hợp stop của component đang hoạt động | Thiết kế timeout/cancel và callback đúng contract |

Một failure listener **không nên cạnh tranh** với Boot để tự đóng cùng resources hoặc tự ném lỗi phụ, làm che mất nguyên nhân gốc.

### 7.1. Không biến listener thành “repair” mechanism

Nếu thiếu property thì sửa config và restart qua deployment/CI. Nếu DB không kết nối được, xác định đó là external dependency và policy startup. Nếu BeanFactory đã fail refresh, gọi `refresh()` lần nữa trên cùng object từ failure listener là một can thiệp nguy hiểm, không được bảo đảm có hiệu quả.

Tốt hơn: log nguyên nhân, để Boot rollback/close và cho orchestrator quyết định retry/restart theo chính sách.

## 8. Resource nào còn có thể dùng khi ApplicationFailedEvent phát?

Câu trả lời luôn là **phụ thuộc pha thất bại và ownership**; không nên khẳng định “tất cả đều chết” hoặc “context còn thì đều sống”.

| Resource | Lỗi rất sớm | Lỗi lúc refresh | Lỗi từ runner sau refresh | Cách xử lý an toàn |
| --- | --- | --- | --- | --- |
| `ApplicationContext` | Có thể `null` | Có thể khác null nhưng chưa active | Thường có context; chuẩn bị đóng | Đọc null-check; tránh `getBean` trong failure callback |
| `Environment` | Có thể chưa chuẩn bị xong | Có thể có | Thường đã có | Đừng giả định mọi property được resolve; không log secrets |
| Logger chuẩn JDK/console | Thường có thể thử | Có thể thử | Có thể thử | Ghi tối giản, không phụ thuộc BeanFactory |
| Spring-managed `DataSource` | Chưa chắc tồn tại | Có thể tạo một phần/đang destroy | Có thể tồn tại nhưng sắp destroy | Không dùng để tiếp tục query trong listener |
| HTTP client Spring bean | Chưa chắc tồn tại | Có thể chưa tạo hoặc đã hủy | Có thể vẫn giữ socket nhưng sắp đóng | Không gửi báo cáo bằng client này trong listener |
| Executor `TaskExecutor` | Chưa chắc tồn tại | Có thể chưa initialize | Có thể đang chặn nhận task mới | Không submit công việc mới |
| Embedded web server | Chưa tạo | Có thể khởi tạo dở | Có thể đã start | Không dựa vào HTTP endpoint để báo startup failure |
| ApplicationRunner/CommandLineRunner | Chưa chạy | Chưa chạy | Có thể đang ném lỗi | Đừng gọi runner lần hai trong listener |
| Một resource tự mở ngoài BeanFactory | Có thể có | Có thể có | Có thể có | Chính code tạo phải có exception-safe cleanup |

**Nguyên tắc:** nếu một tài nguyên không nằm trong Spring context hoặc chưa bàn giao ownership cho container, **Spring không thể cam kết cleanup nó** khi context startup thất bại.

## 9. Ví dụ Java 17+ chạy được: fail trước context và fail trong ApplicationRunner

Ví dụ dùng **Spring Boot 3.3.x + Java 17+**, non-web, không cần database, broker hay HTTP server. Nó minh họa ba đường:

1. Chạy bình thường: runner hoàn thành, context đóng có chủ đích.
2. Runner ném exception sau khi context refresh: `ApplicationFailedEvent` được báo, context có thể khác `null` và Boot đi vào failure cleanup.
3. `createApplicationContext()` ném exception trước khi có context: event nhận context `null`.

Listener được tạo bởi Java constructor trước `run`, **không dùng `@Component`**. Nó chỉ dùng exception và Boolean null-check, không gọi `getBean`.

### 9.1. Cấu trúc thư mục

```text
failure-event-lesson/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/failure/
    FailureEventLessonApplication.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'failure-event-lesson'
```

### 9.3. build.gradle (Groovy DSL)

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

Các lệnh `./gradlew` dưới đây giả định project có Gradle Wrapper; tạo dự án bằng Spring Initializr hoặc dùng một Gradle tương thích để tạo Wrapper nếu chưa có.

### 9.4. application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off

# Chế độ mặc định: startup thành công.
demo.fail-runner=false
```

Không phải thêm `demo.fail-before-context` vào file vì mẫu xác định chế độ này ở `main` qua đối số command-line, trước khi Spring tạo context.

### 9.5. FailureEventLessonApplication.java — file hoàn chỉnh

```java
package com.example.failure;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class FailureEventLessonApplication {

    public static void main(String[] args) {
        boolean failBeforeContext = Arrays.asList(args)
                .contains("--demo.fail-before-context=true");

        SpringApplication application;

        if (failBeforeContext) {
            // Demo: cố tình làm lỗi trước khi context được tạo.
            application = new SpringApplication(
                    FailureEventLessonApplication.class) {
                @Override
                protected ConfigurableApplicationContext
                        createApplicationContext() {
                    throw new IllegalStateException(
                            "SIMULATED_BEFORE_CONTEXT");
                }
            };
        } else {
            application = new SpringApplication(
                    FailureEventLessonApplication.class);
        }

        application.setWebApplicationType(WebApplicationType.NONE);

        // Đăng ký trước run; không phụ thuộc BeanFactory.
        application.addListeners(new SafeFailureListener());

        ConfigurableApplicationContext context = application.run(args);
        System.out.println("STARTUP_SUCCESS");

        // Chỉ chạy trong đường startup thành công.
        context.close();
    }

    @Bean(destroyMethod = "close")
    CloseMarker closeMarker() {
        return new CloseMarker();
    }

    @Bean
    ApplicationRunner demoRunner(CloseMarker marker,
                                 Environment environment) {
        return args -> {
            if (environment.getProperty(
                    "demo.fail-runner", Boolean.class, false)) {
                throw new IllegalStateException(
                        "SIMULATED_RUNNER_FAILURE");
            }

            System.out.println("RUNNER_OK");
        };
    }

    static final class CloseMarker implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("RESOURCE_CLOSED");
        }
    }

    static final class SafeFailureListener
            implements ApplicationListener<ApplicationFailedEvent> {

        @Override
        public void onApplicationEvent(ApplicationFailedEvent event) {
            Throwable root = rootCause(event.getException());

            System.out.println("FAILED_EVENT_RECEIVED");
            System.out.println("CONTEXT_PRESENT="
                    + (event.getApplicationContext() != null));
            System.out.println("ROOT_TYPE="
                    + root.getClass().getSimpleName());
            System.out.println("ROOT_MESSAGE=" + root.getMessage());

            // Không gọi context.getBean(), không gửi HTTP,
            // không dùng DataSource và không gọi System.exit().
        }

        private static Throwable rootCause(Throwable error) {
            Throwable current = error;
            int hops = 0;

            while (current.getCause() != null
                    && current.getCause() != current
                    && hops++ < 20) {
                current = current.getCause();
            }

            return current;
        }
    }
}
```

Đây là **một file Java độc lập trong project Spring Boot 3.3**. Tên public class khớp tên file, mọi inner classes đều có trong cùng file. Không có class giả hoặc helper chưa được định nghĩa.

**Tại sao code có ý nghĩa:**

- `SafeFailureListener` là object Java được register sớm; không inject Spring bean.
- `event.getApplicationContext() != null` chỉ được log, không được dùng làm giấy phép gọi `getBean`.
- `rootCause(...)` có giới hạn độ sâu và chỉ in **message do demo tự cố định**. Trong production, phải kiểm duyệt message từ lỗi thật.
- `CloseMarker` là bean có destroy callback; khi context thực sự đã tạo bean, đóng context sẽ gọi `close()` theo lifecycle.
- `demoRunner(...)` nhận `CloseMarker` làm dependency, nên resource được tạo ở đường khởi tạo normal/runner.
- Hai lỗi mô phỏng xảy ra ở **hai pha khác nhau**, chứng minh failure event không luôn có cùng mức khả dụng tài nguyên.
- `SpringApplication.run(args)` sẽ ném exception trong các chế độ fail; những dòng `STARTUP_SUCCESS` và `context.close()` trong `main` **không chạy** khi `run` không trả về.

### 9.6. Chạy trường hợp thành công

```bash
./gradlew bootRun
```

Windows CMD: `gradlew.bat bootRun`. PowerShell: `.\gradlew.bat bootRun`.

Trong đường chạy thành công, các dòng **do code demo tự in**, bỏ qua logs framework/Gradle:

```text
RUNNER_OK
STARTUP_SUCCESS
RESOURCE_CLOSED
```

Không có `FAILED_EVENT_RECEIVED` vì không có startup failure.

### 9.7. Lỗi từ ApplicationRunner

Chạy:

```bash
./gradlew bootRun --args="--demo.fail-runner=true"
```

Phần log bổ sung của Spring Boot/Gradle có thể nhiều. Các dấu hiệu do demo tự in trong đường thất bại bình thường bao gồm:

```text
FAILED_EVENT_RECEIVED
CONTEXT_PRESENT=true
ROOT_TYPE=IllegalStateException
ROOT_MESSAGE=SIMULATED_RUNNER_FAILURE
RESOURCE_CLOSED
```

**Giải thích:** Runner chạy sau refresh, nên Boot đã có context khi runner thất bại. Failure listener nhận thông tin lỗi, sau đó Spring Boot dọn context/bean đã tạo. Dòng `RESOURCE_CLOSED` phản ánh destroy callback của bean. Đừng khẳng định mọi resource đều có sẵn chỉ từ `CONTEXT_PRESENT=true`.

Trong công cụ thực tế, log startup failure và logs Gradle có thể xen vào các dấu hiệu, và hành vi shutdown tùy code thêm. Nếu chạy trong IDE/test, báo cáo chỉ nên dựa vào **các dấu hiệu tương ứng và contract**, không tuyệt đối hóa thứ tự mọi dòng từ framework.

### 9.8. Lỗi trước khi ApplicationContext được tạo

Chạy:

```bash
./gradlew bootRun --args="--demo.fail-before-context=true"
```

Vì `SpringApplication.createApplicationContext()` được override để ném lỗi **trước khi tạo context**, listener đã được đăng ký trước `run` vẫn có thể ghi:

```text
FAILED_EVENT_RECEIVED
CONTEXT_PRESENT=false
ROOT_TYPE=IllegalStateException
ROOT_MESSAGE=SIMULATED_BEFORE_CONTEXT
```

Không có `RESOURCE_CLOSED` cho `CloseMarker` vì bean chưa từng được tạo. Cũng không có `STARTUP_SUCCESS`.

**Điểm mấu chốt:** code kiểu `event.getApplicationContext().getBean(...)` sẽ ném `NullPointerException` ngay trong mode này, có thể che mất nguyên nhân gốc của startup failure.

### 9.9. Mã trả về của Gradle không phải mã nghiệp vụ

Khi `bootRun` chạy ứng dụng con và ứng dụng fail, Gradle thường đánh dấu task thất bại. Mã process exit của `gradlew` không nhất thiết giống một mã bạn tự thiết kế trong app. Đừng gán nghĩa nghiệp vụ cho một số exit code quan sát ngẫu nhiên khi đang học event. Nếu cần một hợp đồng exit status cho batch, phải thiết kế `ExitCodeGenerator`/exception mapping và kiểm thử `java -jar` trực tiếp.

## 10. Viết listener chỉ dùng dữ liệu đáng tin ở thời điểm thất bại

Một implementation production tối thiểu thường chỉ cần:

```java
public final class StartupFailureAudit
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();

        String type = failure.getClass().getName();
        boolean contextExists =
                event.getApplicationContext() != null;

        System.err.println("Startup failed: " + type
                + ", contextExists=" + contextExists);
    }
}
```

Đây là **class snippet** cần imports `ApplicationListener`, `ApplicationFailedEvent`. Để dùng như listener trước run, phải register bằng `SpringApplication.addListeners(new StartupFailureAudit())` hoặc hình thức early registration phù hợp.

Không cần:

```java
@Component
class WrongAudit {

    @Autowired
    DataSource dataSource;

    @EventListener
    void failed(ApplicationFailedEvent event) {
        // Đừng đòi hỏi DB trong callback lỗi startup.
        try (Connection c = dataSource.getConnection()) {
            // ...
        }
    }
}
```

Đây là **phản ví dụ minh họa**, imports/method chưa hoàn thiện. Nó vừa phụ thuộc bean chưa chắc đã được tạo, vừa cố truy cập DB là dependency có thể gây ra lỗi startup. Nếu resource vẫn tồn tại trong một lần chạy nhất định, đó không phải contract để bạn dựa vào ở mọi failure path.

### 10.1. Những metadata có thể log

Có thể log có kiểm soát:

- Class name của exception.
- Cause chain đã rút gọn.
- Tên ứng dụng/phiên bản từ hằng số hoặc system property không nhạy cảm.
- Startup attempt/correlation ID do launcher tạo.
- Context reference có hay không.
- Thời gian sự kiện.
- Một stage/cause category đã được chuẩn hóa.

Tránh log nguyên mảng `event.getArgs()` vì có thể chứa `--password=...`, API key hoặc URI bí mật. Không tự gọi `Environment.toString()` để in mọi property sources.

## 11. FailureAnalyzer và ConditionEvaluationReport khác listener ở điểm nào?

Spring Boot có nhiều `FailureAnalyzer` cho những lỗi phổ biến. Ví dụ khi port bị chiếm, Boot có thể in:

```text
APPLICATION FAILED TO START

Description:
Web server could not start because the configured port was in use.

Action:
Choose another port or stop the conflicting process.
```

Đây là **mẫu diễn giải nội dung**, không phải nguyên văn thông báo bắt buộc của mọi Boot 3.3 app. Tùy failure analyzer và phiên bản, wording thay đổi.

`FailureAnalyzer` có trách nhiệm tạo **một báo cáo lỗi có gợi ý**, còn `ApplicationFailedEvent` là một **tín hiệu lifecycle** chứa exception. Chúng không cạnh tranh nhau và không phải lý do để mở resource mới.

Với lỗi auto-configuration, bật:

```bash
java -jar build/libs/failure-event-lesson-0.0.1-SNAPSHOT.jar --debug
```

Lệnh này giả định JAR đã được build. Trong tình huống lỗi thực tế, `--debug` giúp đưa thêm thông tin điều kiện auto-configuration vào log; **không** biến BeanFactory lỗi thành context có thể phục hồi.

## 12. Cleanup nếu tài nguyên chưa được bàn giao cho Spring

Một lỗi dễ bị bỏ qua nằm trong factory method:

```java
@Bean
CloseableClient partnerClient() {
    CloseableClient client = openClient();
    validateFurtherConfiguration(); // Có thể throw.
    return client;
}
```

Đây là snippet mô tả vấn đề, `CloseableClient`, `openClient` và `validateFurtherConfiguration` là types/helpers do ứng dụng định nghĩa. Nếu exception ném **sau khi `openClient()` trả resource nhưng trước khi `@Bean` method return**, Spring chưa có bean instance được bàn giao để gọi `destroy()`. `ApplicationFailedEvent` listener cũng không nên tự tìm resource local này để đóng.

**Cách làm exception-safe:** validate trước khi mở tài nguyên; nếu cần có nhiều bước sau khi mở, giữ ownership local trong `try/catch`:

```java
@Bean(destroyMethod = "close")
CloseableClient partnerClient() {
    validateSettings();

    CloseableClient client = openClient();
    try {
        configureClient(client);
        return client; // Bàn giao ownership cho container.
    } catch (RuntimeException ex) {
        try {
            client.close();
        } catch (Exception cleanupError) {
            ex.addSuppressed(cleanupError);
        }
        throw ex;
    }
}
```

Đây là **snippet** với helpers `validateSettings`, `openClient`, `configureClient` và type `CloseableClient` do dự án định nghĩa; cần xử lý thêm checked exceptions theo API cụ thể. Ý nghĩa: trước khi bean được bàn giao cho Spring, **factory sở hữu resource** và phải dọn nếu thất bại. Sau khi factory return thành công, container quản lý vòng đời theo destroy callback.

### 12.1. Không chữa lỗi startup bằng cách đóng resources trong event listener

Nếu context refresh thất bại, Spring có cơ chế phá hủy những singleton đã tạo thành công. Gọi `context.getBeansOfType(DataSource.class)` trong `ApplicationFailedEvent` để tự đóng mọi DataSource vừa dễ ném lỗi, vừa có thể đóng trùng resources hoặc làm lộ side effects.

Với resource ngoài container, owner riêng phải cleanup; với resource Spring-managed, giữ đúng lifecycle của nó. Một listener chỉ nên ghi nhận thiếu cleanup nếu có bằng chứng đáng tin, không tự làm owner thứ hai.

## 13. Những loại tài nguyên thường gặp và rủi ro khi xử lý failure

### 13.1. DataSource/HikariCP

HikariCP có thể:

- Chưa được khởi tạo nếu startup fail sớm.
- Đang mở kết nối đầu tiên khi BeanFactory fail.
- Đã tạo pool nhưng Boot đang đóng context.
- Đã bị hủy trong cleanup của refresh failure.

Dù `event.getApplicationContext()!=null`, không dùng `context.getBean(DataSource.class).getConnection()` như “startup failure audit”. Nếu nguyên nhân chính là DB inaccessible, thao tác này gây thêm kết nối/timeout và che stack trace gốc.

### 13.2. HTTP client, Redis, Kafka

Client phụ thuộc network có thể đã tạo thread/socket hoặc chưa được tạo. Một request gửi webhook báo lỗi bằng chính HTTP client là bean đang hỏng có thể thất bại. Nếu buộc phải gửi incident telemetry khi startup fail, nên có cơ chế **ngoài Spring context** hoặc external supervisor/log collector và timeout chặt; không ép failure listener làm network call đồng bộ dài.

### 13.3. ThreadPoolTaskExecutor và scheduler

Executor/scheduler là những tài nguyên có worker thread, queue và shutdown lifecycle. Khi startup fail, chúng có thể chưa được tạo hoặc đang dừng. Không submit task “gửi email báo lỗi” qua pool chưa chắc còn nhận task.

Nếu code tự tạo `Executors.newFixedThreadPool(...)` ngoài container mà không shutdown, JVM có thể tiếp tục sống sau failure. Đây là lỗi ownership của code tạo pool; không phải do `ApplicationFailedEvent` “không đủ mạnh”.

### 13.4. Logging/metrics/tracing

Một số hệ thống logging và observation có thể được thiết lập rất sớm, nhưng exporters/appenders có thể phụ thuộc config/IO. Dùng chúng best effort; tránh biến việc gửi telemetry thành điều kiện phải hoàn thành trước khi tiến trình được phép kết thúc. Nếu cần audit đáng tin qua cả crash và kill cứng, phải có supervisor/container runtime và hạ tầng giám sát độc lập.

## 14. Ứng dụng web: context có thể tồn tại dù web server chưa dùng được

Một ứng dụng có thể fail khi:

- Bind port vì địa chỉ đã bị chiếm.
- Tạo Servlet web server nhưng một bean init khác fail.
- Initialize security filter chain bị lỗi.
- Refresh context bị hủy giữa chừng.
- Runner ném exception sau khi web server đã mở.

Do đó, việc context object tồn tại **không có nghĩa HTTP endpoints hoạt động**. Một failure listener **không** nên tự gọi `http://localhost:8080/health`, đặc biệt khi web server có thể chưa mở hoặc đã bắt đầu dừng.

### 14.1. Liveness/readiness ở startup failure

Theo Spring Boot 3.3, liveness được công bố `CORRECT` sau `ApplicationStartedEvent`, còn readiness `ACCEPTING_TRAFFIC` sau `ApplicationReadyEvent` và các runner.

Nếu runner fail:

```text
ApplicationStartedEvent
LivenessState.CORRECT
ApplicationRunner throws
ApplicationFailedEvent
ApplicationReadyEvent: không đạt theo đường thành công
ReadinessState.ACCEPTING_TRAFFIC: không công bố theo đường thành công
```

Điều này không mâu thuẫn. Liveness từng `CORRECT` vì context đã refresh, nhưng **cả lần startup vẫn thất bại** trước ready. Hạ tầng dựa trên process/container health có thể restart theo chính sách. Đừng cố ép readiness false trong failure listener bằng một bean `ApplicationAvailability` chưa chắc còn dùng được.

### 14.2. Nếu fail sau khi đã ready?

Một exception tại HTTP controller sau ready không tự sinh `ApplicationFailedEvent`. Đối với runtime hỏng không phục hồi, Boot có `AvailabilityChangeEvent<LivenessState>`/health probes; đối với lỗi recoverable, dùng error handling, retry, circuit breaker và readiness nếu thích hợp.

**Không chọn cơ chế chỉ vì tên có chữ “Failed”.** Đúng event phải phù hợp **giai đoạn lifecycle**.

## 15. Giới hạn của listener khi nhiều ApplicationContext

Spring Framework cho phép cây parent/child contexts. Một event phát trong context con có thể được truyền lên ancestor listeners theo cơ chế propagation. Khi nhiều `SpringApplication` instances ở một hierarchy, một listener ở parent có thể thấy nhiều sự kiện cùng type.

Với `ApplicationFailedEvent`, hãy quan sát:

- `event.getSpringApplication()` để phân biệt run nào phát sinh.
- `event.getApplicationContext()` có thể null, vì vậy không dùng phép so sánh context identity khi event chưa có context.
- Nếu một failure listener được đăng ký trong nhiều `SpringApplication`, tránh báo cáo trùng do registration/topology.
- Không dùng listener parent để đóng resource của parent chỉ vì một child startup fail.

Khi cần một báo cáo duy nhất cho nhiều startup attempts, hãy đặt một **correlation/attempt ID** từ launcher hoặc metric có policy de-duplication; đừng suy luận mọi event cùng tên là cùng một lỗi.

## 16. Đừng “giấu” exception của runner để tránh ApplicationFailedEvent

Một anti-pattern:

```java
@Bean
ApplicationRunner initializeEverything() {
    return args -> {
        try {
            loadMandatoryData();
        } catch (Exception ex) {
            System.err.println("Ignored");
        }
    };
}
```

Snippet trên cố tình thiếu helper `loadMandatoryData` để minh họa ý tưởng. Nếu dữ liệu đó **bắt buộc** cho hoạt động an toàn, nuốt exception khiến Boot tiếp tục tới ready dù app chưa sẵn sàng.

Lựa chọn đúng phụ thuộc tính chất dữ liệu:

- **Bắt buộc:** để runner fail-fast hoặc ném exception mô tả nguyên nhân, đẩy startup vào failure path.
- **Tùy chọn/recoverable:** có thể fallback, ghi metrics và tiếp tục với trạng thái chức năng hạn chế theo policy.
- **Dài nhưng bắt buộc:** runner đồng bộ với timeout phù hợp hoặc readiness gating được điều phối chính xác.
- **Cần retry qua process restart:** lưu trạng thái trong job store/durable queue, không chỉ vòng lặp nền trong context chưa ready.

`ApplicationFailedEvent` ghi nhận **kết quả failure path**, không thay thế quyết định “đây là lỗi startup hay runtime” của code nghiệp vụ.

## 17. Kiểm thử failure listener mà không phá vỡ test suite

### 17.1. Unit test chỉ truyền event

Một unit test có thể tự dựng `ApplicationFailedEvent` bằng constructor có `SpringApplication`, arguments, context có thể null và một `Throwable` mẫu, rồi gọi listener. Test rằng:

- Không có `NullPointerException` khi context null.
- Exception được nhận diện đúng.
- Listener không gọi `getBean`/network.
- Không in secrets trong args.
- Một lỗi trong formatter/logging không làm che exception gốc.

Đối với code production, nên tách logic chuẩn hóa dữ liệu lỗi khỏi thao tác ghi log để test dễ hơn.

### 17.2. Integration test lỗi trước context

Sử dụng cách mô phỏng `createApplicationContext()` ném exception như phần 9. Xác nhận listener **được đăng ký trước `run`** và in `CONTEXT_PRESENT=false`, trong khi bean destroy callback của context chưa tạo không chạy.

Một `@SpringBootTest` có shared TestContext cache không phù hợp để cố tình làm hỏng context chung một cách tùy tiện. Tạo `SpringApplication` riêng hoặc dùng **subprocess** để lỗi không làm ảnh hưởng các test khác.

### 17.3. Integration test lỗi trong runner

Chạy chương trình với `--demo.fail-runner=true` trong process con, kiểm tra:

- ApplicationFailedEvent được phát.
- Context reference có thể tồn tại.
- Root cause phản ánh lỗi trong runner.
- Không có `STARTUP_SUCCESS`.
- Các beans đã tạo được cleanup theo lifecycle.
- Không còn non-daemon threads hoặc connection pools do app tự tạo không quản lý.

Lưu ý: nếu bạn dùng `@SpringBootTest` với context caching, cố tình gọi `SpringApplication.exit` trên cached context có thể làm test kế tiếp lỗi. Dùng context/process sở hữu riêng.

### 17.4. Process-level test

Dùng `ProcessBuilder`/shell chạy `java -jar` và kiểm tra exit status thực, log và deadline. Với failure path không có `ExitCodeGenerator` tùy biến, đừng gán số status cụ thể cho mọi JVM/launcher; thông thường sẽ là nonzero nhưng giá trị cuối phụ thuộc đường failure và môi trường.

Nếu test dùng `Process.waitFor()`, đặt timeout và kill process con khi kẹt. Một executor tự tạo không shutdown có thể giữ child JVM sống dù Boot đã cleanup context.

## 18. Các lỗi thường gặp và cách sửa

| Lỗi/hiểu nhầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Luôn gọi `event.getApplicationContext().getBean(...)` | NPE trước context hoặc BeanFactory không hợp lệ | Null-check; không dựa vào bean trong failure handler |
| Context khác null ⇒ mọi bean an toàn | Thực tế có thể chưa refresh/đang destroy | Chỉ dùng event metadata và logger độc lập |
| Định nghĩa failure listener bằng `@Component` là đủ | Miss lỗi xảy ra trước khi bean được tạo | `SpringApplication.addListeners` hoặc `spring.factories` |
| Listener inject DataSource để gửi audit | Chính DB/pool có thể là nguyên nhân failure | Dùng logs/fallback ngoài container |
| Gọi remote webhook đồng bộ trong failure event | Treo startup failure handling, lỗi phụ | Có timeout và cơ chế monitoring ngoài process |
| Listener gọi `System.exit` | Cắt ngang cleanup/diagnostics | Để entrypoint/Boot failure path quyết định exit |
| Dựa vào `isActive()` để tiếp tục nghiệp vụ | Race và context không còn đảm bảo khỏe | Không mở work mới trên context thất bại |
| Ghi raw `getArgs()` | Rò secret/token/password | Redact và chỉ ghi metadata cần thiết |
| Failure event = mọi exception runtime | Bỏ sót request/background failures | Dùng đúng runtime error-handling |
| Context fail nhưng cố `refresh()` lại | State không còn rõ, side effects có thể lặp | Fix nguyên nhân, khởi động instance mới |
| @Bean factory mở client rồi throw | Resource chưa được bàn giao Spring để destroy | Validate trước, catch/finally close |
| Đóng mọi bean trong failed listener | Double-close hoặc lỗi từ BeanFactory | Để lifecycle owner chịu trách nhiệm cleanup |
| Runner bị catch/ignore lỗi bắt buộc | App có thể ready dù chưa an toàn | Fail-fast với lỗi critical |
| Coi liveness CORRECT là ready | Runner có thể fail sau context refresh | Phân biệt Liveness/Readiness |
| Lỗi startup trước logging init không có telemetry | Mất log sự cố | Fallback stderr, supervisor và external log collector |
| Listener tự tạo ExecutorService để báo lỗi | Rò thread khi app đã fail | Ghi synchronous nhỏ hoặc external monitor |
| Test giết JVM bằng System.exit | Kết thúc cả test suite | Tạo subprocess riêng |
| Dùng Spring ApplicationFailedEvent như health probe | Event chỉ xảy ra lúc startup failure | Liveness/readiness và health indicators |
| Một child fail khiến parent cleanup | Không phân biệt ownership/context | Filter nguồn, để parent owner giữ resource |
| Cam kết mọi @PreDestroy luôn chạy | SIGKILL/crash/timeout không đảm bảo | Checkpoint, idempotence và hạ tầng shutdown |
| Chỉ xem root exception, bỏ wrapper | Mất bean name/phase gây lỗi | Giữ full cause chain trong error diagnostics an toàn |

## 19. Checklist thiết kế listener và cleanup an toàn

1. Xác định failure event chỉ dành cho **startup**.
2. Đăng ký listener đủ sớm nếu cần bắt lỗi trước khi context có.
3. Tránh listener phụ thuộc Spring bean mà chính container có thể chưa tạo được.
4. Xử lý `event.getApplicationContext() == null`.
5. Context khác null vẫn không đảm bảo BeanFactory/beans có thể dùng.
6. Lấy `event.getException()`, giữ wrapper lẫn root cause khi chẩn đoán.
7. Không in secrets, raw args hoặc toàn bộ Environment.
8. Tránh network/database/broker calls trong failure listener.
9. Không gọi `System.exit` hoặc `SpringApplication.exit` từ failure listener.
10. Giữ handler nhanh, bounded và ít side effects.
11. Để Boot FailureAnalyzer ghi báo cáo lỗi tiêu chuẩn.
12. Tài nguyên mở trước khi @Bean return phải được factory cleanup nếu throw.
13. Tài nguyên Spring-managed cần destroy callbacks đúng ownership.
14. Nếu có producer/executor, thiết kế stop/await/cancel và deadline.
15. Nếu rollback không đầy đủ vì SIGKILL, có idempotence/checkpoint.
16. Phân biệt lỗi ở Environment, context creation, refresh và runner.
17. Không coi Liveness CORRECT là Readiness ACCEPTING_TRAFFIC.
18. Không nuốt exception critical trong runner chỉ để startup thành công.
19. Test early failure và runner failure ở các process/context cô lập.
20. Test listener không NPE khi context null.
21. Kiểm tra bean cleanup cho các resources thực sự được tạo.
22. Không dùng cached context để giả lập lỗi phá hủy chung của tests.
23. Quan sát threads/pools sau failure; không tạo unmanaged executors.
24. Ghi rõ ai chịu trách nhiệm cảnh báo vận hành và ai khởi động lại instance.

## 20. Câu hỏi tự kiểm tra

**1. ApplicationFailedEvent có được phát khi một HTTP request trả 500 sau startup không?**

Không mặc định. Nó báo lỗi của `SpringApplication` trong quá trình startup, không phải một global event cho mọi runtime exception.

**2. getApplicationContext() có luôn khác null không?**

Không. Nếu thất bại trước khi context được tạo, giá trị có thể `null`.

**3. Context khác null có cho phép gọi getBean(DataSource.class) để gửi log lỗi không?**

Không nên. Context có thể chưa refresh, refresh fail, đang đóng hoặc resource chính là nguyên nhân lỗi.

**4. @EventListener trong @Component có chắc nhận lỗi khi Environment loading thất bại không?**

Không. Bean có thể chưa được tạo. Đăng ký listener với `SpringApplication.addListeners` trước `run` nếu cần xử lý sớm.

**5. Khi ApplicationRunner ném exception, context có thể đã refresh không?**

Có. Runner chạy sau refresh nhưng trước ready; Boot có thể đã phát liveness CORRECT, song startup vẫn fail.

**6. Có nên khởi động lại một bean hỏng bằng context.refresh trong listener không?**

Không. Recovery từ một context startup fail không được bảo đảm; sửa nguyên nhân và startup lại theo owner.

**7. Có thể dùng @PreDestroy để cleanup tài nguyên ở mọi failure path không?**

Không. Nếu bean chưa từng được tạo hoặc resource chưa bàn giao cho container, callback không có instance để chạy. SIGKILL cũng không đảm bảo callback.

**8. FailureAnalyzer giải quyết việc gì?**

Tạo description/action cho lỗi startup, hỗ trợ chẩn đoán; không thay thế người sở hữu resource hoặc restart service.

**9. Nếu factory method tạo HTTP client rồi ném exception trước return, Spring có tự đóng client không?**

Không thể trông đợi. Bean instance chưa được bàn giao cho container; code factory cần cleanup resource đã mở.

**10. Vì sao không gửi webhook bằng Spring-managed HTTP client trong listener?**

Client có thể chưa tạo, không khỏe, đang đóng hoặc phụ thuộc vào chính service bị lỗi. Listener nên hạn chế side effects.

**11. Nếu muốn đo mã thoát thực của startup failure, nên thử thế nào?**

Chạy ứng dụng như **một process con** và kiểm tra exit status/log trong launcher thực, không gọi `System.exit` từ test JVM.

**12. Nếu startup thành công nhưng một @Scheduled job fail sau 10 phút, có ApplicationFailedEvent không?**

Không theo contract startup. Cần task error handling, metrics/tracing và availability theo mức nghiêm trọng.

## 21. Tóm tắt

```text
SpringApplication.run(...)
        |
        +-- Fail trước create context
        |       |
        |       +--> ApplicationFailedEvent
        |       +--> getApplicationContext() == null
        |       +--> Không có Spring beans để sử dụng
        |
        +-- Fail trong context.refresh()
        |       |
        |       +--> ApplicationFailedEvent
        |       +--> context có thể tồn tại, chưa ổn định
        |       +--> cleanup các resources được container quản lý
        |
        +-- Fail trong ApplicationRunner
                |
                +--> Context có thể đã refresh
                +--> ApplicationFailedEvent
                +--> Chưa đạt readiness thành công
                +--> Boot xử lý cleanup/failure reporting

Safe listener:
  Nhận exception + metadata được kiểm duyệt
  KHÔNG gọi getBean / không query DB / không submit task
  KHÔNG mở thêm tài nguyên hoặc chiếm quyền shutdown
```

**Quy tắc quan trọng nhất:** `ApplicationFailedEvent` cho biết **startup thất bại**, nhưng tài nguyên Spring còn khả dụng tới đâu phụ thuộc **giai đoạn failure** và **ownership/lifecycle**. Khi sự kiện xuất hiện, ưu tiên ghi nhận lỗi bằng một listener được đăng ký đủ sớm, không phụ thuộc BeanFactory. Tránh thử khôi phục hoặc dùng tiếp `ApplicationContext` đã thất bại. Để Spring Boot và các owners xử lý cleanup, và để hạ tầng khởi động lại ứng dụng theo chính sách phù hợp.

## Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplication: Startup Failure và FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationFailedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html)
- [Spring Boot 3.3 — SpringApplicationRunListener.failed API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html)
- [Spring Boot 3.3 — SpringApplication.createApplicationContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — ApplicationAvailability lifecycle](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework 6.1 — Bean creation, destruction và lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 6.1 — ApplicationContext events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
