# Vai trò của FailureAnalysisReporter trong trình bày kết quả lỗi khởi động

## 1. Vì sao cần một bước riêng để trình bày lỗi?

Khi Spring Boot khởi động thất bại, nguyên nhân gốc có thể nằm sâu trong một chuỗi exception: không bind được cổng mạng, cấu hình không hợp lệ, thiếu bean, vòng phụ thuộc hoặc một `ApplicationRunner` ném lỗi. Nếu chỉ nhìn toàn bộ stack trace, người vận hành có thể không biết **điều gì cần sửa trước**.

Spring Boot 3.3.x có cơ chế **failure diagnostics** để chuyển một số lỗi khởi động thành thông báo dễ hiểu. Cơ chế này gồm ba thành phần với trách nhiệm khác nhau:

- **`FailureAnalyzer`:** xem xét một `Throwable`, nhận diện loại lỗi mà nó hiểu và tạo bản phân tích, hoặc trả `null` nếu không phân tích được.
- **`FailureAnalysis`:** đối tượng dữ liệu biểu diễn kết quả phân tích, chứa `description`, `action` và `cause`.
- **`FailureAnalysisReporter`:** nhận `FailureAnalysis` đã có và **trình bày** cho người dùng/vận hành, chẳng hạn log ra một khối “APPLICATION FAILED TO START” hoặc chuyển thành bản ghi chẩn đoán có cấu trúc.

**`FailureAnalysisReporter` không phải nơi quyết định nguyên nhân gốc.** Nó là bước **presentation/reporting** sau bước phân tích. Phân tách này cho phép một analyzer mô tả được tình huống kỹ thuật, còn những reporter khác nhau hiển thị cho developer console, log aggregator hoặc một kênh giám sát tùy nhu cầu.

Ví dụ thông điệp quen thuộc trong Spring Boot:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Embedded web server could not start because a required port was in use.

Action:

Free the port or configure the application to use another port.
```

Các dòng trên là **mẫu minh họa cách trình bày**, không phải bản chép lại message của một phiên bản Tomcat cụ thể. Nó nhấn mạnh cấu trúc hai phần:

1. **Description:** mô tả điều gì không đúng.
2. **Action:** gợi ý bước khắc phục có thể thực hiện.

Nguyên nhân kỹ thuật đầy đủ vẫn tồn tại trong `Throwable`/stack trace. Reporter giúp người đọc nhìn thấy thông điệp ngắn gọn trước; nó **không làm cho exception biến mất hoặc biến startup thất bại thành thành công**.

Bài áp dụng cho **Spring Boot 3.3.13 / Spring Framework 6.1.x / Java 17+**. Đặc biệt, cách đăng ký custom reporter trong giai đoạn startup failure được trình bày bằng `META-INF/spring.factories`, không phụ thuộc giả định rằng toàn bộ `ApplicationContext` đã khởi tạo xong.

## 2. Ba thành phần và API chính xác

### 2.1. FailureAnalyzer: phân tích lỗi

Interface thuộc `org.springframework.boot.diagnostics`:

```java
public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
```

Đây là **chữ ký rút gọn từ API**, không khai báo lại interface này trong mã ứng dụng. Method có thể trả `null` nếu analyzer không xử lý được exception. Trong một số lỗi, exception hữu ích nằm trong `getCause()`, nên analyzer có thể kiểm tra causal chain.

Ví dụ: một `MissingEndpointException` bị `ApplicationRunner` ném ra; Spring Boot có thể bọc nó trong exception khác khi báo runner thực thi thất bại. Analyzer chuyên biệt nên tìm loại exception cần xử lý **bên trong causal chain**, thay vì chỉ kiểm tra class của Throwable lớp ngoài.

### 2.2. FailureAnalysis: dữ liệu đã phân tích

Class `org.springframework.boot.diagnostics.FailureAnalysis` có constructor:

```java
new FailureAnalysis(description, action, cause)
```

và các accessor:

```java
String description = analysis.getDescription();
String action = analysis.getAction();
Throwable cause = analysis.getCause();
```

Những dòng trên là **snippet minh họa**, cần một biến `analysis` và import tương ứng. Ba trường có ý nghĩa:

| Trường | Nội dung nên có | Tránh |
| --- | --- | --- |
| `description` | Mô tả tình trạng thất bại, điều kiện nào không được đáp ứng | Chỉ viết “Unknown error”, sao chép cả stack trace |
| `action` | Bước sửa cụ thể: property cần đặt, port cần đổi, dependency cần thêm | Lời khuyên chung chung “fix code”, hướng dẫn nguy hiểm |
| `cause` | `Throwable` thật để truy vết gốc | Tạo exception giả làm mất bối cảnh hoặc xóa root cause |

`getAction()` có thể trả `null` nếu không có hành động cụ thể. Reporter phải xử lý trường hợp này hợp lệ, không được giả định mọi analysis có action.

### 2.3. FailureAnalysisReporter: trình bày analysis

Interface Spring Boot 3.3.13:

```java
package org.springframework.boot.diagnostics;

@FunctionalInterface
public interface FailureAnalysisReporter {
    void report(FailureAnalysis analysis);
}
```

Đây là **trích cấu trúc API dùng để giải thích**, không tự tạo lại interface. Method duy nhất `report` trả `void`: reporter chỉ nhận bản phân tích và báo cho người dùng. Nó **không trả mã exit**, **không quyết định “handled/not handled” bằng boolean**, và **không được gọi để thay đổi trạng thái readiness**.

Một reporter có thể xuất:

- Bản log dễ đọc với `description` và `action`.
- Một sự kiện telemetry có cấu trúc (nếu cơ sở hạ tầng log đã sẵn sàng).
- Một file chẩn đoán tạm thời có giới hạn, theo chính sách bảo mật.
- Một định dạng riêng cho công cụ hỗ trợ nội bộ.

Trong production, nên ưu tiên ghi qua logger và không đặt logic I/O dài hoặc dễ thất bại vào đường báo lỗi khởi động.

### 2.4. Bảng trách nhiệm

| Thành phần | Input | Output | Ai sở hữu việc? |
| --- | --- | --- | --- |
| `FailureAnalyzer.analyze(Throwable)` | Exception từ startup | `FailureAnalysis` hoặc `null` | Nhận diện lỗi, diễn giải nguyên nhân |
| `FailureAnalysis` | Description, action, cause | Dữ liệu chẩn đoán | Không tự log hoặc sửa lỗi |
| `FailureAnalysisReporter.report(...)` | Một `FailureAnalysis` | Side effect trình bày | Định dạng/hiển thị bản phân tích |
| `LoggingFailureAnalysisReporter` | Một `FailureAnalysis` | Thông điệp thông qua logging | Reporter mặc định của Spring Boot |
| `SpringBootExceptionReporter` | `Throwable` từ SpringApplication startup | `boolean` báo đã report hay chưa | Extension point rộng hơn, **khác** `FailureAnalysisReporter` |
| `ApplicationFailedEvent` listener | Sự kiện Boot startup failure | Phản ứng với event | Event notification, không tự tạo `FailureAnalysis` |

Hai interface có chữ “Reporter” không tương đương. Đặc biệt, `SpringBootExceptionReporter` ở tầng rộng hơn được loader khởi tạo với `ConfigurableApplicationContext`; **không copy yêu cầu constructor đó sang `FailureAnalysisReporter`**. Reporter của ví dụ bên dưới được khai báo public no-arg constructor để loader tạo ở đường chẩn đoán.

## 3. Luồng xử lý lỗi khởi động

Sơ đồ dễ học:

```text
SpringApplication.run(...)
    |
    +--> lỗi khi prepare/refresh context hoặc chạy runner
    |
    +--> SpringApplication xử lý startup failure
             |
             +--> cơ chế SpringBootExceptionReporter
             |      |
             |      +--> FailureAnalyzers (tích hợp Boot)
             |              |
             |              +--> duyệt các FailureAnalyzer
             |              |      +--> không hiểu lỗi -> null
             |              |      +--> hiểu lỗi -> FailureAnalysis
             |              |
             |              +--> reporter(s) nhận FailureAnalysis
             |                     +--> LoggingFailureAnalysisReporter
             |                     +--> reporter tùy chỉnh nếu đăng ký
             |
             +--> các bước báo lỗi/notification/cleanup thích hợp
             +--> exception không được coi là startup thành công
```

Sơ đồ mô tả **vai trò** của các khối, không cam kết thứ tự chi tiết giữa tất cả startup failure hooks, shutdown callbacks và loggers trong mọi loại lỗi. Vào thời điểm startup thất bại, có thể context chưa tồn tại đầy đủ, hệ thống logging chưa cấu hình xong hoặc ngoại lệ quá nghiêm trọng khiến không phải cơ chế nào cũng chạy.

**Điều kiện tiên quyết để reporter nhận một `FailureAnalysis`: có analyzer tương ứng phân tích được lỗi.** Nếu không analyzer nào tạo được analysis, reporter chuyên nhận `FailureAnalysis` không có bản phân tích phù hợp để trình bày. Khi đó xem stack trace và condition evaluation report để điều tra.

### 3.1. Chỉ xử lý lỗi xảy ra trong startup?

`FailureAnalysisReporter` thuộc đường **startup failure diagnostics của Spring Boot**. Nó không phải một `@ControllerAdvice` và không tự được gọi khi:

- Một HTTP request trả 500 sau khi ứng dụng đã ready.
- Một `@Scheduled` method ném exception trong giờ chạy bình thường.
- Một `@Async` task nền hoàn thành lỗi khi startup đã xong.
- Một câu lệnh nghiệp vụ báo “không tìm thấy khách hàng” trong request hợp lệ.
- Một message consumer thất bại sau nhiều giờ hoạt động.

Các trường hợp runtime cần cơ chế xử lý lỗi, log, retry, metrics, circuit breaker hoặc HTTP exception mapping phù hợp riêng.

### 3.2. Analyzer trả null khác reporter không ghi log

Nếu một `FailureAnalyzer` trả `null`, đó là **“analyzer này không đưa ra phân tích”**. Nếu analyzer khác trả analysis nhưng reporter không phát thông điệp, nguyên nhân có thể là cấu hình logging, cách đăng ký reporter, exception trong reporter hoặc việc quan sát sai kênh stdout/stderr.

Hai vấn đề khác tầng. Khi debug, cần xác minh từng chặng:

```text
Exception thực tế?
    -> Có analyzer xử lý đúng Throwable?
    -> Có FailureAnalysis không null?
    -> Reporter có được loader tạo?
    -> report(analysis) có được gọi?
    -> Log output có được nhìn thấy ở đúng mức/kênh?
```

Không vội viết lại analyzer chỉ vì log không xuất hiện; cũng không vội sửa reporter khi analyzer chưa bao giờ tạo ra result.

## 4. Reporter mặc định: LoggingFailureAnalysisReporter

Spring Boot có `org.springframework.boot.diagnostics.LoggingFailureAnalysisReporter`, implement `FailureAnalysisReporter`. Đây là reporter thường thấy khi ứng dụng in khối:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

<phần mô tả lỗi>

Action:

<hành động đề xuất>
```

Khối trên là **mẫu định dạng**, các mục trong dấu ngoặc nhọn là vị trí diễn giải chứ không phải message chính xác từ một analyzer thực. Reporter mặc định dùng hệ thống logging để hiển thị. `Description` lấy từ `FailureAnalysis.getDescription()`; `Action` lấy từ `getAction()` nếu có nội dung.

Trong implementation thông thường, reporter log bản phân tích ở mức **ERROR**; thông tin exception/cause chi tiết có thể được log ở **DEBUG**. Vì vậy:

- Mức log quá cao hoặc logger bị tắt có thể làm thông điệp không xuất hiện như kỳ vọng.
- Bản report ở ERROR có thể ngắn gọn hơn full stack trace, đó là chủ đích hướng dẫn sửa lỗi.
- Bật DEBUG có thể bổ sung thông tin để điều tra nhưng không tự sửa cấu hình sai.
- Nội dung `description`/`action` phụ thuộc analyzer đã tạo analysis, không phụ thuộc tên reporter.

**Không cần tự viết reporter** chỉ để có banner lỗi dễ hiểu tiêu chuẩn. Phần lớn ứng dụng dùng reporter mặc định; custom reporter hữu ích khi có yêu cầu **presentation/telemetry** riêng.

### 4.1. Cải thiện thông điệp bằng cách nào?

Nếu message mơ hồ vì **description/action** chưa rõ, thường cần cải thiện **`FailureAnalyzer`**. Đổi reporter chỉ thay cách trình bày, không tự bổ sung kiến thức domain vào analysis.

Ví dụ:

```text
Description:
A required configuration property for the payment connector is missing.

Action:
Set PAYMENT_ENDPOINT in the deployment environment, then restart.
```

Đây là **ví dụ nội dung** không đòi hỏi viết một custom reporter; một analyzer có thể tạo chính xác các string tương ứng và reporter mặc định trình bày chúng.

### 4.2. Tài liệu Boot ghi “FailureAnalyzer beans” có nghĩa phải @Component?

Không nên lấy cách diễn đạt ở trang overview để suy rằng chỉ thêm `@Component` là quy trình đăng ký plugin startup diagnostics đầy đủ. **Cách đăng ký document chính thức cho custom FailureAnalyzer** trong Boot 3.3 là dùng `META-INF/spring.factories`. Với `FailureAnalysisReporter` tùy chỉnh cũng nên dùng extension point của `SpringFactoriesLoader`, vì lỗi có thể xảy ra khi context chưa hoàn tất. Phần 6 cho ví dụ cụ thể.

## 5. Khi nào cần custom FailureAnalysisReporter?

Reporter tùy chỉnh thích hợp nếu **bản phân tích đã đúng**, nhưng nơi tiêu thụ cần định dạng/kênh khác:

1. Một môi trường cần thông điệp lỗi dạng một dòng để bộ thu log có thể gắn job ID.
2. Một runtime muốn in prefix cố định để phân biệt diagnostics của thư viện với log nghiệp vụ.
3. Một nền tảng hỗ trợ nội bộ muốn đóng gói `cause type`, `description` và `action` thành một record có cấu trúc.
4. Một công cụ kiểm thử cần xác nhận analysis đã đến bước presentation, không chỉ kiểm tra analyzer unit test.
5. Một thư viện starter cần quy ước hiển thị thống nhất cho lỗi cấu hình của chính thư viện.

Nhưng custom reporter cũng có giới hạn:

- **Không thể sửa lỗi bind port, config, thiếu bean**; nó chỉ báo.
- **Không nên chủ động gọi `System.exit`, `context.close` hoặc retry startup** trong `report`. Boot đang thực hiện failure handling.
- **Không được phụ thuộc vào request-scoped beans** hoặc network service bắt buộc, vì context có thể chưa initialized.
- **Không nên mở kết nối network không timeout** để gửi lỗi; hệ thống ngoài có thể chính là nguyên nhân startup fail.
- **Không được xuất secret** qua `description`, `action`, `getCause().getMessage()`.
- **Không bảo đảm có analysis** cho mọi JVM crash, classpath error hoặc lỗi quá sớm.

Bài tiếp theo dùng một reporter ghi xuống `System.err` để minh họa trực quan, **không phải khuyến nghị production bỏ logger**. Trong ứng dụng thật, ưu tiên hệ thống logging và telemetry có giới hạn thời gian, kiểm thử bằng đúng launcher mà bạn triển khai.


## 6. Ví dụ chạy được: custom analyzer + custom reporter trên Spring Boot 3.3.13

Mục tiêu: tự tạo lỗi thiếu property `demo.remote.endpoint` trong một `ApplicationRunner`; để Boot chạy bước phân tích và gọi reporter đã đăng ký. Từ đó quan sát **sự khác nhau giữa analysis (dữ liệu)** và **reporting (presentation)**.

Ví dụ sử dụng **Java 17+**, **Spring Boot 3.3.13**, **Gradle** và **non-web application**. Không gọi API ngoài, không cần database và không mở cổng mạng. Thiếu property sẽ gây startup failure có chủ đích; cung cấp property sẽ chạy thành công, **không gọi reporter**.

### 6.1. Cấu trúc thư mục

```text
diagnostics-lab/
├── build.gradle
├── settings.gradle
└── src/
    └── main/
        ├── java/com/example/failure/
        │   ├── DiagnosticsDemoApplication.java
        │   ├── MissingEndpointException.java
        │   ├── MissingEndpointFailureAnalyzer.java
        │   └── ConsoleFailureAnalysisReporter.java
        └── resources/
            ├── application.properties
            └── META-INF/
                └── spring.factories
```

Đường dẫn và tên public class phải khớp **chính xác**. File `spring.factories` phải nằm trong **`src/main/resources/META-INF/`** để được đóng gói vào classpath, không phải ở root project.

### 6.2. build.gradle

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'diagnostics-lab'
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR

# Cố tình KHÔNG khai báo demo.remote.endpoint ở đây.
```

### 6.3. Application và nguồn lỗi có kiểm soát

Tạo file **`src/main/java/com/example/failure/DiagnosticsDemoApplication.java`**:

```java
package com.example.failure;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DiagnosticsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner checkRequiredEndpoint(
            @Value("${demo.remote.endpoint:}") String endpoint) {

        return args -> {
            if (endpoint.isBlank()) {
                throw new MissingEndpointException("demo.remote.endpoint");
            }
            System.out.println("RUNNER OK: endpoint property is present");
        };
    }
}
```

Vì `@Value("${demo.remote.endpoint:}")` có **default rỗng**, ứng dụng khởi tạo bean bình thường khi thiếu property rồi runner chủ động throw. Đây là cách tạo lỗi **sau refresh** nhưng **trước `ApplicationReadyEvent`**, đủ đơn giản để lần theo causal chain. Chúng ta cố ý không đưa URL có credential vào stdout.

Tạo **`src/main/java/com/example/failure/MissingEndpointException.java`**:

```java
package com.example.failure;

public final class MissingEndpointException extends RuntimeException {

    private final String propertyName;

    public MissingEndpointException(String propertyName) {
        super("Required configuration is missing: " + propertyName);
        this.propertyName = propertyName;
    }

    public String getPropertyName() {
        return propertyName;
    }
}
```

Class này chỉ mô tả **lỗi miền cấu hình**. Nó không tự implement reporter/analyzer và không có logic log.

### 6.4. FailureAnalyzer: tạo FailureAnalysis

Tạo **`src/main/java/com/example/failure/MissingEndpointFailureAnalyzer.java`**:

```java
package com.example.failure;

import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalyzer;

public final class MissingEndpointFailureAnalyzer
        implements FailureAnalyzer {

    public MissingEndpointFailureAnalyzer() {
    }

    @Override
    public FailureAnalysis analyze(Throwable failure) {
        // SpringApplication có thể bọc exception gốc từ runner.
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {

            if (current instanceof MissingEndpointException missing) {
                String name = missing.getPropertyName();

                return new FailureAnalysis(
                        "Required configuration '" + name
                                + "' is missing or blank.",
                        "Set --" + name
                                + "=https://example.invalid/api"
                                + " (or environment DEMO_REMOTE_ENDPOINT).",
                        missing);
            }
        }

        // Không phải lỗi của chúng ta: nhường analyzer khác.
        return null;
    }
}
```

**Các điểm quan trọng:**

- `analyze(Throwable)` là method của `FailureAnalyzer`, không phải method của reporter.
- Duyệt `current.getCause()` giúp tìm exception ngay cả khi Spring bọc exception từ `ApplicationRunner`.
- `new FailureAnalysis(description, action, missing)` giữ loại exception gốc làm `cause`.
- `return null` khi không khớp là lựa chọn đúng: để những analyzer khác có cơ hội xử lý lỗi khác.
- Reporter **không cần lặp lại logic tìm cause và sinh action**; nó đọc dữ liệu analysis đã tạo.

### 6.5. FailureAnalysisReporter: trình bày analysis

Tạo **`src/main/java/com/example/failure/ConsoleFailureAnalysisReporter.java`**:

```java
package com.example.failure;

import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalysisReporter;

public final class ConsoleFailureAnalysisReporter
        implements FailureAnalysisReporter {

    public ConsoleFailureAnalysisReporter() {
    }

    @Override
    public void report(FailureAnalysis analysis) {
        System.err.println(
                "[CUSTOM REPORTER] description=" + analysis.getDescription());

        if (analysis.getAction() != null) {
            System.err.println(
                    "[CUSTOM REPORTER] action=" + analysis.getAction());
        }

        Throwable cause = analysis.getCause();
        System.err.println(
                "[CUSTOM REPORTER] cause="
                        + (cause == null
                                ? "unknown"
                                : cause.getClass().getSimpleName()));
    }
}
```

Đây là reporter **đúng vai trò presentation**:

- Không tìm kiếm `MissingEndpointException` hay phân loại business error.
- Không throw exception mới khi status là thất bại.
- Không gọi lại `SpringApplication.run(...)`.
- Không gọi `System.exit(...)`.
- Không thay đổi `application.properties`.
- Chỉ lấy `description`/`action`/`cause` từ `FailureAnalysis` và in với prefix dễ nhận biết.

Dùng `System.err` trong demo vì dễ chứng minh output khi startup thất bại; ứng dụng thực thường nên dùng logger/cấu trúc telemetry nhưng phải tính trường hợp logger chưa hoàn chỉnh.

### 6.6. META-INF/spring.factories: đăng ký cả hai extension points

Tạo **`src/main/resources/META-INF/spring.factories`** với nguyên văn:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failure.MissingEndpointFailureAnalyzer
org.springframework.boot.diagnostics.FailureAnalysisReporter=com.example.failure.ConsoleFailureAnalysisReporter
```

**Không đặt file này trong thư mục Java package.** Đây là metadata classpath dành cho `SpringFactoriesLoader`. Spring Boot có sẵn những implementation và danh sách factories trong các JAR của framework; tài nguyên metadata của ứng dụng được loader xem xét cùng các tài nguyên có sẵn.

Hệ quả thực tế:

1. Khi startup thất bại, Spring Boot có thể load `MissingEndpointFailureAnalyzer` từ classpath.
2. Analyzer tạo `FailureAnalysis` nếu causal chain chứa `MissingEndpointException`.
3. `ConsoleFailureAnalysisReporter` được load và nhận result.
4. `LoggingFailureAnalysisReporter` mặc định của Spring Boot cũng có thể báo cùng failure analysis qua logging.
5. App không cần `@Component` trên hai class để chúng được phát hiện; cả hai có public no-arg constructor, phù hợp cho ví dụ loader.

**Điểm đặc biệt quan trọng:** `FailureAnalysisReporter` ở pha startup failure **không nên phụ thuộc vào việc @Autowired một bean đã tồn tại**. Lỗi có thể xảy ra trước khi container chuẩn bị xong. Thiết kế reporter ít dependency, có thể được tạo từ classpath metadata, giúp hoạt động trong nhiều tình huống hơn.

### 6.7. Build executable JAR

Windows PowerShell:

```powershell
.\gradlew.bat bootJar
```

macOS/Linux:

```bash
./gradlew bootJar
```

Nếu môi trường có Gradle Wrapper được tạo và Java toolchain 17, output thường là:

```text
build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar
```

Dùng `jar tf build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar` để kiểm tra đã có `BOOT-INF/classes/META-INF/spring.factories` khi đóng gói bằng Boot executable JAR. Nếu metadata không được đưa vào classpath, custom reporter/analyzer sẽ không được load ở runtime.

### 6.8. Chạy đường lỗi

```bash
java -jar build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar
```

Do `demo.remote.endpoint` không có trong properties, runner throw `MissingEndpointException`. Boot xử lý startup failure và có cơ hội gọi analyzer/reporter được đăng ký.

Các dòng do **custom reporter** in xuống stderr, khi reporter được loader gọi:

```text
[CUSTOM REPORTER] description=Required configuration 'demo.remote.endpoint' is missing or blank.
[CUSTOM REPORTER] action=Set --demo.remote.endpoint=https://example.invalid/api (or environment DEMO_REMOTE_ENDPOINT).
[CUSTOM REPORTER] cause=MissingEndpointException
```

Các dòng có prefix `[CUSTOM REPORTER]` ở trên là **phần đầu ra riêng của class demo**. Spring Boot còn có thể in khối `APPLICATION FAILED TO START` từ reporter mặc định và những dòng log lỗi khác. **Thứ tự giữa phần stderr của custom reporter và output logging không nên được assert tuyệt đối**, vì cấu hình logging và cách thu thập stdout/stderr khác nhau giữa launcher/IDE/CI.

Trong đường lỗi này:

- `RUNNER OK: ...` **không xuất hiện**.
- Không có đường startup thành công tới `ApplicationReadyEvent`.
- `SpringApplication.run(...)` không return context bình thường cho `main`.
- Java process thường kết thúc với trạng thái thất bại khi exception không được xử lý. Kiểm tra **mã thoát thực tế** từ launcher, không đoán rằng custom reporter tự đặt một mã số cụ thể.

### 6.9. Chạy đường thành công

Cung cấp property hợp lệ (mẫu URL không thực hiện network I/O):

```bash
java -jar build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar --demo.remote.endpoint=https://example.invalid/api
```

Với cấu hình non-web, logging root ERROR và không có thành phần bổ sung khác, **dòng do app chủ động in ra**:

```text
RUNNER OK: endpoint property is present
```

App không ném exception, vì thế custom failure analyzer/reporter **không được gọi cho một startup failure**. Đối với non-web CLI mẫu không có resource non-daemon khác giữ JVM sống, process sẽ kết thúc bình thường sau khi startup path hoàn tất. URL chỉ làm input kiểm thử, không được dùng để gọi HTTP.

### 6.10. PowerShell và Bash kiểm tra status

Bash:

```bash
java -jar build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar
code=$?
echo "Java process exit status: $code"
```

PowerShell:

```powershell
java -jar build/libs/diagnostics-lab-0.0.1-SNAPSHOT.jar
$LASTEXITCODE
```

**Không cố định stdout là “1” cho tất cả wrapper/launcher.** Đường báo lỗi tùy exception handling, config và cách shell/Gradle/IDE đóng gói process. Muốn xác nhận exit status, chạy `java -jar` trực tiếp hoặc test process con.

Vì `FailureAnalysisReporter.report(...)` trả `void`, reporter không phải nơi map exit code. Nếu cần chính sách riêng về mã thoát, nghiên cứu `ExitCodeGenerator`, `ExitCodeExceptionMapper` và cơ chế shutdown riêng, không gộp vào logic format báo lỗi.


## 7. Thiết kế reporter tốt cho hệ thống thật

### 7.1. Nội dung nên tập trung vào người sửa lỗi

Thông điệp tốt thường trả lời bốn câu hỏi:

1. **Điều gì sai?** Ví dụ thiếu `demo.remote.endpoint`.
2. **Lỗi xảy ra ở giai đoạn nào?** Configuration binding, bean construction, context refresh, runner...
3. **Hệ quả là gì?** Không thể khởi động ứng dụng hoặc không đạt ready.
4. **Làm gì tiếp theo?** Đặt property có tên chính xác, kiểm tra secret manager/ConfigMap, đổi port hoặc bổ sung bean cần thiết.

`FailureAnalysisReporter` có thể định dạng message, nhưng **`FailureAnalyzer` phải cung cấp description/action có chất lượng**. Không giải quyết bằng cách gửi mọi exception message nguyên văn sang một hệ thống cảnh báo, vì nhiều exception không đủ ngữ cảnh và có thể chứa bí mật.

### 7.2. Tối thiểu và chịu lỗi tốt

Reporter là một **đường lỗi của đường lỗi**: nó chạy khi startup đã thất bại. Vì thế nên hạn chế dependency:

- Có constructor đơn giản, tránh gọi network trong constructor.
- Không chờ database, broker hoặc bean đang bị lỗi.
- Không tạo scheduler/executor vô hạn chỉ để báo failure.
- Không throw một exception mới từ `report` trong những tình huống có thể tránh; bắt lỗi của kênh xuất nếu cần.
- Giới hạn thời gian nếu phải flush logs/telemetry.
- Dự phòng kênh báo lỗi tối giản khi logging chưa được khởi tạo đầy đủ.
- Giữ message ngắn và hành động được, kèm correlation ID không nhạy cảm khi đã có.
- Thử trên giai đoạn lỗi **trước refresh** và **sau refresh** nếu yêu cầu báo lỗi phải bao phủ cả hai.

### 7.3. Bảo mật: không dump bí mật

`FailureAnalysis` có thể chứa exception từ binding/config. Raw `Throwable.getMessage()` hoặc nested cause đôi lúc chứa:

- URL có username/password.
- Secret token, API key, database credentials.
- Chuỗi kết nối hoặc query kèm dữ liệu nhạy cảm.
- Thông tin định danh không phù hợp cho log chung.

Đừng mặc định serialize toàn bộ `Throwable` sang JSON rồi gửi đi. Nên viết analyzer sinh một **description đã lọc dữ liệu nhạy cảm**, chỉ nêu tên property hoặc loại resource, và một action an toàn. Reporter cần giới hạn kích thước log, dùng policy redaction và tránh lặp output ở nhiều kênh không có kiểm soát.

Một output đủ dùng:

```text
description=Required property 'demo.remote.endpoint' is missing.
action=Provide demo.remote.endpoint in trusted configuration.
causeType=MissingEndpointException
```

Khối này không cần in giá trị endpoint, token hoặc request payload để người vận hành biết bước khắc phục.

### 7.4. Đồng bộ hóa với log aggregator và alert

Nếu cần routing/alert, thiết kế các trường ổn định:

| Trường gợi ý | Ví dụ | Mục đích |
| --- | --- | --- |
| `eventType` | `startup_failure` | Phân loại khác runtime 500 |
| `application` | `billing-service` | Tìm component gặp vấn đề |
| `phase` | `application_runner` | Khoanh vùng giai đoạn |
| `causeType` | `MissingEndpointException` | Gom các lỗi cùng loại |
| `description` | Thiếu property bắt buộc | Người đọc hiểu nhanh |
| `action` | Cấp cấu hình hợp lệ | Hướng xử lý |
| `instanceId` | ID không nhạy cảm | Liên kết logs |
| `timestamp` | Thời gian UTC chuẩn | Đồng bộ với deployment event |

Đây là **bảng schema gợi ý**, không phải các field được Spring tự truyền vào `FailureAnalysisReporter`. Interface thực tế chỉ nhận `FailureAnalysis`. Muốn có metadata về environment, instance và build, reporter phải lấy từ nguồn an toàn còn sẵn có; không giả định `ApplicationContext` đã đầy đủ.

### 7.5. Vì sao không tự gửi notification HTTP từ reporter?

Trong startup failure, lỗi có thể chính là không phân giải được DNS, credentials hỏng hoặc downstream API không kết nối được. Nếu reporter cũng gọi downstream API mà không timeout, hệ thống có thể “đóng băng khi đang báo lỗi”.

Khuyến nghị: reporter phát một log có cấu trúc tới stderr/logger, để **log collector bên ngoài** phân phối tới alert platform. Nếu bắt buộc gửi trực tiếp, phải có timeouts ngắn, best-effort failure handling và không làm che root startup error.

## 8. Sự khác biệt với các extension points liên quan

### 8.1. FailureAnalysisReporter và ApplicationFailedEvent

`ApplicationFailedEvent` được Spring Boot phát trong đường startup failure để các listener có cơ hội biết rằng khởi động thất bại. Nó không tự chứa một `FailureAnalysis` sẵn có do analyzer tùy chỉnh tạo ra để reporter trình bày.

`FailureAnalysisReporter` nhận `FailureAnalysis`, còn `ApplicationFailedEvent` listener nhận **sự kiện chứa failure/context khi có**. Nếu cần phản ứng rộng hơn với một startup failure, event listener có thể phù hợp; nếu cần **presentation của một analysis đã được tạo**, dùng reporter.

Lưu ý về thứ tự: Đừng đặt correctness logic phụ thuộc vào thứ tự log của listener với reporter trong mọi startup failure phase. Khi context chưa tạo xong, bean listener trong context có thể chưa tồn tại.

### 8.2. FailureAnalysisReporter và SpringBootExceptionReporter

`SpringBootExceptionReporter` có method:

```java
boolean reportException(Throwable failure);
```

Nó là callback cấp `SpringApplication` cho lỗi startup, có input là `Throwable` và giá trị return thể hiện việc đã báo hay chưa. `FailureAnalysisReporter` thì là interface **trình bày đối tượng FailureAnalysis đã phân tích**:

```java
void report(FailureAnalysis analysis);
```

Hai interface dùng khác tên `spring.factories` key, khác kiểu input và khác khái niệm “handled”. Trong Spring Boot, cơ chế `FailureAnalyzers` đóng vai trò `SpringBootExceptionReporter` để kích hoạt pipeline analyzer/reporter.

**Không implement `FailureAnalysisReporter` với method `reportException(Throwable)`**; method cần override chính xác là `report(FailureAnalysis)`. Cũng không yêu cầu constructor có `ConfigurableApplicationContext` ở custom `FailureAnalysisReporter` trong ví dụ này; đó là yêu cầu của loại reporter cấp `SpringBootExceptionReporter`.

### 8.3. FailureAnalysisReporter và ExitCodeGenerator

| API | Vai trò |
| --- | --- |
| `FailureAnalysisReporter` | Hiển thị một kết quả phân tích |
| `ExitCodeGenerator` | Đề xuất mã exit từ bean/exception trong đường tương ứng |
| `ExitCodeExceptionMapper` | Ánh xạ exception sang mã exit |
| `System.exit(int)` | Yêu cầu JVM kết thúc với mã truyền cho OS |

Custom reporter không biến startup failure thành exit 0 hay đặt code 7 chỉ vì message nêu “severity=critical”. Việc hiển thị thông điệp và việc xác định exit status phải là hai trách nhiệm riêng.

### 8.4. FailureAnalysisReporter và ControllerAdvice

`@ControllerAdvice`/`@ExceptionHandler` xử lý exception trong ngữ cảnh HTTP request sau khi ứng dụng chạy. Nó không phải công cụ chính để báo lỗi tạo bean, binding hoặc runner trong startup. Ngược lại, `FailureAnalysisReporter` không tự biến một lỗi HTTP 500 thành JSON response cho client.

### 8.5. FailureAnalysisReporter và ConditionEvaluationReport

Khi một lỗi startup không có analyzer thích hợp, Spring Boot gợi ý xem **conditions evaluation report** để hiểu tại sao auto-configuration được áp dụng hoặc bị bỏ qua. Có thể bật `--debug` với `java -jar` hoặc cấu hình logger `ConditionEvaluationReportLoggingListener` phù hợp.

`ConditionEvaluationReport` là dữ liệu chẩn đoán điều kiện cấu hình, không phải output mà `FailureAnalysisReporter` mặc định luôn chứa. Đừng hi vọng reporter sẽ tự tạo analysis cho mọi auto-config decision. Đây là **công cụ điều tra bổ sung**, không thay thế analyzer/reporter.

## 9. Các tình huống thực tế

### 9.1. Không bind được cổng 8080

- **Cause:** thường là exception khi embedded server cố bind port đã sử dụng.
- **Analyzer:** Boot có các built-in failure analyzers cho những lỗi cấu hình/startup phổ biến.
- **FailureAnalysis:** mô tả cổng bị chiếm và hướng khắc phục.
- **Reporter:** logging mặc định hiển thị banner lỗi với `Description` và `Action`.

**Không cần custom reporter** nếu banner đã đủ rõ. Nếu hệ thống thu log yêu cầu trường `port`/`service`, có thể cân nhắc custom presentation hoặc structured log bên ngoài.

### 9.2. Thiếu bean quan trọng

- Root failure có thể liên quan dependency injection/`NoSuchBeanDefinitionException`.
- Analyzer phù hợp có thể mô tả loại bean cần thiết và cách thêm bean/configuration.
- Reporter hiển thị mô tả đó; nó **không thể đăng ký bean mới để cứu startup**.

Với lỗi injection phức tạp, action cần tránh khuyên “bật @ComponentScan toàn project” một cách vô tội vạ. Phải căn cứ đúng scope/auto-configuration.

### 9.3. Configuration property không hợp lệ

- Analyzer nhận diện property sai, constraint binding không đạt hoặc validation failure.
- Action nên nêu **tên key**, expected format/range và nguồn cấu hình cần cập nhật.
- Reporter đưa nội dung đó tới console/log.
- Không in giá trị credential trong lỗi; sanitize descriptions ở analyzer.

Ví dụ bài mục 6 thuộc nhóm này, nhưng dùng một exception domain và runner để dễ thấy causal chain.

### 9.4. Lỗi không có analyzer

Một thư viện thứ ba ném một runtime exception chưa được analyzer nào nhận diện.

- Không có analysis cụ thể để reporter tùy chỉnh trình bày.
- Boot vẫn có đường log startup failure chung; có thể xem root stacktrace và điều kiện auto-config.
- Nếu lỗi thường xảy ra và có action rõ ràng, thêm một `FailureAnalyzer` chuyên biệt trước khi nghĩ tới reporter tùy chỉnh.

### 9.5. Logging bị cấu hình sai

Analyzer đã tạo result, reporter mặc định được gọi nhưng app không hiển thị như kỳ vọng. Kiểm tra:

- Mức logger `org.springframework.boot.diagnostics.LoggingFailureAnalysisReporter`.
- Hệ thống log appender, stdout/stderr routing, ANSI và redirection.
- Có log collector lấy đúng stream không?
- Có custom reporter trùng lặp output hoặc ném exception không?
- Có startup error quá sớm khiến logging/loader chưa sẵn sàng không?

Đừng kết luận “Boot không phân tích được” chỉ dựa vào việc một log collector không thấy dòng banner.

## 10. Kiểm thử analyzer và reporter

### 10.1. Unit test analyzer bằng causal chain

Tạo file **`src/test/java/com/example/failure/MissingEndpointFailureAnalyzerTest.java`**:

```java
package com.example.failure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.junit.jupiter.api.Assertions.*;

class MissingEndpointFailureAnalyzerTest {

    @Test
    void findsCauseEvenWhenRunnerWrapsIt() {
        var analyzer = new MissingEndpointFailureAnalyzer();

        var root = new MissingEndpointException("demo.remote.endpoint");
        var wrapper = new IllegalStateException(
                "Failed to execute ApplicationRunner", root);

        FailureAnalysis analysis = analyzer.analyze(wrapper);

        assertNotNull(analysis);
        assertSame(root, analysis.getCause());
        assertTrue(analysis.getDescription().contains(
                "demo.remote.endpoint"));
        assertTrue(analysis.getAction().contains(
                "--demo.remote.endpoint="));
    }

    @Test
    void ignoresUnrelatedFailures() {
        var analyzer = new MissingEndpointFailureAnalyzer();

        FailureAnalysis analysis = analyzer.analyze(
                new IllegalArgumentException("unrelated"));

        assertNull(analysis);
    }
}
```

Đây là **test JUnit 5 đầy đủ** dùng dependency `spring-boot-starter-test` đã khai báo trong `build.gradle`. Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu cấu hình đúng, hai unit tests kiểm tra được:

- Analyzer tìm đúng exception dù có wrapper.
- `cause` giữ instance root exception.
- `description/action` chứa thông tin cần thiết.
- Lỗi khác loại trả `null`.

**Chúng không chứng minh `spring.factories` được đóng gói và reporter được gọi trong startup.** Việc đó phải kiểm bằng integration/process test.

### 10.2. Kiểm thử reporter độc lập

Có thể tạo một `FailureAnalysis` với data mẫu rồi gọi:

```java
var analysis = new FailureAnalysis(
        "Required configuration is missing.",
        "Set a trusted configuration value.",
        new IllegalStateException("sample"));

new ConsoleFailureAnalysisReporter().report(analysis);
```

Đây là **snippet thử nghiệm**, cần import `FailureAnalysis` và class reporter từ ví dụ. Nó chứng minh method có thể format ba trường, nhưng vẫn chưa chứng minh loader và SpringApplication startup failure.

Để assert output trong unit test, có thể capture `System.err`, nhưng phải **khôi phục stream trong finally** hoặc dùng cơ chế output capture của test framework, tránh làm nhiễu tests chạy song song.

### 10.3. Integration test bằng process riêng

Chạy `java -jar` với **không có property**; assert:

- Process startup thất bại trong tình huống có kiểm soát.
- Stderr/log chứa marker `[CUSTOM REPORTER] description=...`.
- Có `cause=MissingEndpointException`.
- Không xuất hiện message `RUNNER OK`.
- Exit status phù hợp đường thất bại theo launcher thực.

Sau đó chạy với `--demo.remote.endpoint=https://example.invalid/api`; assert:

- Runner in `RUNNER OK: endpoint property is present`.
- Không có marker `[CUSTOM REPORTER]` từ startup failure.
- Process hoàn tất bình thường.

Điều này kiểm chứng cả phân tích, báo cáo và metadata `META-INF/spring.factories`. Nếu dùng Gradle `bootRun`, mã exit của Gradle wrapper có thể khác process con; test đáng tin nhất cho process status là `java -jar` trực tiếp hoặc `ProcessBuilder` với executable JAR.

### 10.4. Khi thêm custom reporter, default còn hoạt động không?

Đúng key `spring.factories` của ứng dụng đăng ký một implementation **bổ sung**. Spring Boot JAR vẫn chứa metadata đăng ký `LoggingFailureAnalysisReporter`. Vì vậy ở cấu hình mặc định, bạn có thể thấy **cả custom marker và thông báo mặc định**.

Đừng viết test assert “có đúng duy nhất ba dòng stderr”: bản log mặc định có thể thêm banner, timestamps hoặc stacktrace; tập trung vào markers ổn định của reporter tùy chỉnh. Nếu muốn bỏ mặc định hoặc thay thế format, phải thiết kế rõ cơ chế kênh log phù hợp và kiểm chứng cả trường hợp reporter không tải được, thay vì dựa vào thứ tự khởi tạo ngẫu nhiên.

## 11. Checklist khi custom reporter không chạy

1. **Lỗi có thực sự xảy ra trong `SpringApplication.run(...)`?** Runtime exception sau khi ready không thuộc cùng cơ chế.
2. **Có analyzer trả `FailureAnalysis`?** Nếu không, reporter có thể không có result để nhận.
3. **Exception cần xử lý nằm ở wrapper hay root cause?** Duyệt causal chain, không chỉ top-level Throwable class.
4. **Analyzer trả `null` đúng/nhầm?** Với lỗi domain cần xử lý, `return null` vô tình sẽ nhường analyzer khác hoặc khiến thiếu analysis.
5. **Đã đăng ký key đúng?** `org.springframework.boot.diagnostics.FailureAnalyzer` và `org.springframework.boot.diagnostics.FailureAnalysisReporter`.
6. **Đường file đúng?** `src/main/resources/META-INF/spring.factories`, không phải Java package root.
7. **Fully qualified class name đúng?** Package, tên class public và chính tả.
8. **Constructor phù hợp?** Với demo, public no-arg constructor; tránh inject bean cần context.
9. **Metadata đã vào JAR?** Kiểm `BOOT-INF/classes/META-INF/spring.factories` trong executable JAR.
10. **App có tùy biến `SpringApplication` hoặc loader/classpath?** Thử bằng launcher thật, kiểm tra dependency đang có trong JAR.
11. **Reporter có log nhưng sai stream?** Kiểm `System.err`, logging levels, collector và redirect.
12. **Có nhiều reporters?** Không giả định thứ tự hoặc số dòng cố định khi framework reporter mặc định cũng hoạt động.
13. **Exception có quá sớm/khó phục hồi?** Một số failure xảy ra trước lúc pipeline có thể chạy.
14. **Description/action chứa secret?** Sanitize trước khi gửi sang kênh chung.
15. **Reporter có block network/throw exception?** Đường báo lỗi phải nhanh, ít dependency và best-effort.
16. **Có đang kiểm một request lỗi 500?** Dùng HTTP exception handling, không dùng startup reporter.
17. **Có nhầm với ExitCodeGenerator?** Reporter không tự quyết định mã process.
18. **Có dùng `@Component` mà quên `spring.factories`?** Startup diagnostics là plugin qua classpath metadata trong ví dụ này.

## 12. Những nhầm lẫn thường gặp

| Nhận định hoặc triệu chứng | Vì sao sai? | Phản ứng đúng |
| --- | --- | --- |
| “Reporter tự đi tìm root cause” | Tách trách nhiệm analyzer và reporter | Analyzer sinh result; reporter hiển thị |
| “FailureAnalysis là một Throwable” | Nó là đối tượng dữ liệu chứa description/action/cause | Sử dụng accessor đúng |
| “Report trả true nếu đã xử lý lỗi” | `FailureAnalysisReporter.report` trả `void` | Không nhầm `SpringBootExceptionReporter` |
| “Thêm @Component là đủ để reporter luôn chạy” | Startup context có thể chưa hoàn chỉnh | Đăng ký `META-INF/spring.factories` |
| “Reporter thay thế mọi stack trace” | Nó là thông báo bổ sung/format thuận tiện | Xem root cause, log DEBUG khi cần |
| “Reporter fix được port bị chiếm” | Không thay được cấu hình/hạ tầng | Người vận hành thực hiện action |
| “Mọi startup failure đều có FailureAnalysis” | Analyzer có thể trả null hoặc pipeline chưa chạy | Fallback stacktrace/conditions report |
| “Default reporter chỉ log INFO” | `LoggingFailureAnalysisReporter` thường log banner ở ERROR | Kiểm logging level và appender |
| “Action luôn có string” | `FailureAnalysis.getAction()` có thể null | Kiểm null/blank |
| “Cứ in cause.getMessage() là đủ” | Thiếu action và có nguy cơ lộ dữ liệu | Mô tả an toàn, có hướng sửa |
| “Reporter của ta xóa default reporter” | Factory discovery có thể nạp cả hai | Chuẩn bị cho output bổ sung |
| “Dòng stderr luôn xuất hiện đúng thứ tự với logging” | Kênh ghi và flush khác nhau | Assert markers không assert toàn bộ order |
| “ApplicationFailedEvent là FailureAnalysisReporter” | Event notification khác step presentation | Chọn đúng hook |
| “Runtime @Async failure cũng tự gọi reporter” | Đây là startup diagnostics | Theo dõi Future/AsyncUncaughtExceptionHandler |
| “Reporter tự đặt exit code” | API `report` trả void | Dùng cơ chế exit code riêng |
| “Đăng ký reporter mà không có analyzer vẫn luôn thấy output” | Cần `FailureAnalysis` phù hợp | Kiểm analyzer/causal chain |
| “Bật --debug có nghĩa mọi nguyên nhân đều được sửa” | Debug chỉ tăng thông tin chẩn đoán | Đọc điều kiện và thay đổi cấu hình |
| “Có thể gọi REST API không timeout trong reporter” | Lỗi startup có thể do network | Ưu tiên logger hoặc best-effort có timeout |
| “Nên ghi mọi secret để dễ debug” | Log aggregation lan truyền dữ liệu nhạy cảm | Chỉ log type/key, không log value nhạy cảm |

## 13. Câu hỏi tự đánh giá

**Câu 1.** `FailureAnalyzer` và `FailureAnalysisReporter` khác nhau thế nào?

**Đáp:** Analyzer nhận Throwable, tạo `FailureAnalysis` hoặc null; reporter nhận `FailureAnalysis` và trình bày kết quả, không quyết định lỗi thuộc loại gì.

**Câu 2.** Một `FailureAnalysis` chứa những thành phần nào?

**Đáp:** `description`, `action` có thể null, và `cause` là Throwable tương ứng.

**Câu 3.** Method chính của `FailureAnalysisReporter` là gì, trả kiểu gì?

**Đáp:** `void report(FailureAnalysis analysis)`.

**Câu 4.** Reporter mặc định tên gì?

**Đáp:** `LoggingFailureAnalysisReporter`, ghi phân tích qua logging, thường có khối `APPLICATION FAILED TO START`.

**Câu 5.** Một analyzer không hiểu exception cần làm gì?

**Đáp:** Trả `null` để nhường cơ hội cho analyzer khác, không bịa action hoặc luôn nhận mọi Throwable.

**Câu 6.** Vì sao nên duyệt `Throwable.getCause()`?

**Đáp:** Spring có thể wrap lỗi từ bean initialization/runner, trong khi exception domain hữu ích nằm ở một cấp bên trong.

**Câu 7.** Đăng ký analyzer/reporter tùy chỉnh trong ví dụ bằng file nào?

**Đáp:** `src/main/resources/META-INF/spring.factories` với hai key full-qualified `FailureAnalyzer` và `FailureAnalysisReporter`.

**Câu 8.** Tại sao không chỉ đặt `@Component` trên reporter?

**Đáp:** Startup failure có thể xuất hiện khi context chưa tạo hoàn chỉnh; cơ chế discovery qua classpath factory metadata thích hợp hơn cho extension point này.

**Câu 9.** Nếu analyzer tạo result nhưng app vẫn exit thất bại, đó có phải lỗi reporter không?

**Đáp:** Không. Mục tiêu của reporter là **báo một startup failure đang có**, không làm ứng dụng khởi động thành công.

**Câu 10.** Nếu một HTTP request trả 500 sau khi app ready, reporter này có tự chạy?

**Đáp:** Không. Dùng `@ControllerAdvice`/exception handler, observability và runtime error reporting phù hợp.

**Câu 11.** Nếu reporter chỉ ghi sang network alerting API mà API ấy down, điều gì nguy hiểm?

**Đáp:** Có thể block/che nguyên nhân lỗi gốc trong lúc đang thất bại khởi động. Nên hạn chế I/O, timeout và dùng log collector ngoài.

**Câu 12.** `ApplicationFailedEvent` có giống `FailureAnalysis` không?

**Đáp:** Không. Event mô tả startup failure, còn `FailureAnalysis` là kết quả được analyzer tạo nhằm trình bày cho người dùng.

**Câu 13.** Bản custom reporter của ví dụ có nên chứa logic `System.exit(2)`?

**Đáp:** Không. Nó chỉ hiển thị analysis. Định nghĩa exit code là trách nhiệm của cơ chế khác và launcher cần kiểm chứng.

**Câu 14.** Khi không có analyzer hỗ trợ, cách debug tiếp?

**Đáp:** Xem exception/root stacktrace, bật `--debug`/condition evaluation report trong phạm vi phù hợp, kiểm tra cấu hình và viết analyzer chuyên biệt nếu lỗi lặp lại.

## 14. Ghi nhớ và tài liệu chính thức

### 14.1. Ghi nhớ năm ý

1. **`FailureAnalyzer` = phân tích Throwable; `FailureAnalysis` = dữ liệu kết quả; `FailureAnalysisReporter` = trình bày dữ liệu.**
2. Reporter có API chính xác **`void report(FailureAnalysis analysis)`**. Nó không sửa lỗi, không tạo context, không đặt exit code.
3. Reporter mặc định **`LoggingFailureAnalysisReporter`** thường log một đoạn `Description / Action` có tiêu đề `APPLICATION FAILED TO START`.
4. Custom analyzer/reporter cho startup nên được đăng ký bằng **`META-INF/spring.factories`**, có class/constructor phù hợp và ít phụ thuộc vào context.
5. Một report tốt phải **đúng, hành động được, không lộ secret**; việc startup thất bại vẫn cần được xử lý bằng cấu hình/code/hạ tầng thực tế.

### 14.2. Liên kết tham khảo

- [Spring Boot 3.3.13 — FailureAnalysisReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysisReporter.html), chữ ký `report(FailureAnalysis)`.
- [Spring Boot 3.3.13 — FailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html), `analyze(Throwable)` và contract trả `null`.
- [Spring Boot 3.3.13 — FailureAnalysis API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html), `description/action/cause`.
- [Spring Boot 3.3.13 — LoggingFailureAnalysisReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/LoggingFailureAnalysisReporter.html), reporter mặc định ghi log.
- [Spring Boot 3.3.13 — SpringApplication / Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), failure analysis và condition evaluation report.
- [Spring Boot 3.3.13 — SpringBootExceptionReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringBootExceptionReporter.html), extension point cấp startup exception.
- [Spring Boot 3.3.13 — How-to: Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/how-to/application.html), đăng ký qua `META-INF/spring.factories`.

**Kết luận:** Nếu ứng dụng thất bại khi startup, `FailureAnalysisReporter` là cầu nối giữa **kết quả phân tích nguyên nhân** và **thông điệp con người có thể đọc, hiểu và hành động**. Muốn cải thiện chất lượng chẩn đoán, hãy làm rõ nguyên nhân ở analyzer, làm rõ hành động ở analysis, rồi dùng reporter trình bày an toàn, nhất quán và không làm xấu thêm đường xử lý lỗi vốn đã mong manh.
