# FailureAnalyzer, FailureAnalysis và mô tả hành động khắc phục

Khi **Spring Boot không khởi động được**, một stack trace dài có thể chứa hàng chục lớp exception như `BeanCreationException`, `BeanInstantiationException` và lỗi gốc ở sâu bên trong. Người vận hành cần trả lời nhanh hơn ba câu hỏi: **điều gì sai**, **vì sao sai**, và **phải sửa ở đâu/bằng thao tác nào**. Spring Boot hỗ trợ biến một số lỗi khởi động thành bản chẩn đoán dễ hiểu thông qua `FailureAnalyzer` và `FailureAnalysis`.

Ví dụ một ứng dụng không thể mở cổng vì cổng đã bị tiến trình khác chiếm dụng. Thay vì yêu cầu đọc toàn bộ stack trace, Spring Boot có thể trình bày:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Web server failed to start because a configured port is already in use.

Action:

Stop the process using that port, or configure another server.port.
~~~

**Đây là mẫu minh họa về bố cục, không phải bản sao chính xác từng chữ từ một phiên bản server.** Thông điệp thực phụ thuộc nguyên nhân, analyzer và phiên bản Spring Boot.

Bài học thuộc module **Spring Boot Application Runtime**, nhóm **Lỗi khởi động**, dùng **Spring Boot 3.3.x / Spring Framework 6.1 / Java 17+**. Trọng tâm là cơ chế **phân tích lỗi startup**, cách tạo **FailureAnalysis có hành động khắc phục cụ thể**, đăng ký analyzer đúng giai đoạn bootstrap và kiểm tra kết quả bằng một dự án có thể chạy được.

## 1. Bài toán: stack trace không tự là hướng dẫn khắc phục

Một lỗi Spring khi tạo bean có thể được bọc nhiều lớp:

~~~text
SpringApplication.run(...)
  |
  +-- ApplicationContext.refresh()
       |
       +-- Tạo bean demoGuard
            |
            +-- BeanCreationException
                 |
                 +-- BeanInstantiationException
                      |
                      +-- MissingTargetException
                           "Required setting demo.target is missing"
~~~

Nếu chỉ xem dòng đầu, người đọc có thể tưởng “Spring tạo bean thất bại” là nguyên nhân đủ để sửa. Nhưng nguyên nhân nghiệp vụ thực tế là **thuộc tính bắt buộc `demo.target` chưa được cung cấp**.

Một bản phân tích có ích nên trả lời:

| Thành phần | Ví dụ | Câu hỏi được giải đáp |
| --- | --- | --- |
| **Description** | `Required configuration 'demo.target' is missing or blank.` | Điều gì sai? |
| **Action** | `Set --demo.target=local before restarting the application.` | Phải làm gì để sửa? |
| **Cause** | `MissingTargetException` | Exception nào thực sự dẫn đến phân tích? |

Lợi ích không nằm ở việc “che giấu” stack trace, mà ở việc thêm một **tầng diễn giải ngắn, đúng ngữ cảnh và có thể hành động**. Khi cần điều tra sâu, log và nguyên nhân gốc vẫn quan trọng.

## 2. Ba vai trò tách biệt: Analyzer, Analysis, Reporter

| Thành phần | Package Spring Boot 3.3 | Trách nhiệm |
| --- | --- | --- |
| `FailureAnalyzer` | `org.springframework.boot.diagnostics` | Nhận một `Throwable` khởi động và quyết định có phân tích được hay không |
| `FailureAnalysis` | `org.springframework.boot.diagnostics` | Mang dữ liệu `description`, `action`, `cause` |
| `FailureAnalysisReporter` | `org.springframework.boot.diagnostics` | Hiển thị/ghi nhận một `FailureAnalysis` đã được tạo |
| `LoggingFailureAnalysisReporter` | `org.springframework.boot.diagnostics` | Reporter mặc định ghi phần phân tích vào log |
| `AbstractFailureAnalyzer<T>` | `org.springframework.boot.diagnostics` | Lớp cơ sở tiện ích tìm exception thuộc kiểu `T` trong chuỗi cause |

Tư duy phân tầng:

~~~text
Lỗi startup
    |
    v
Throwable (có thể bị bọc nhiều tầng)
    |
    v
FailureAnalyzer / AbstractFailureAnalyzer
    |                  |
    | phân tích được   | không nhận diện
    v                  v
FailureAnalysis       null
    |                  |
    v                  v
FailureAnalysisReporter   Analyzer khác / log lỗi thông thường
    |
    v
Description + Action trong log startup
~~~

`FailureAnalyzer` **không chịu trách nhiệm sửa lỗi**. Nó chỉ nhận diện và diễn giải. `FailureAnalysis` là **dữ liệu chẩn đoán**, không phải exception mới hay lệnh để khởi động lại. `FailureAnalysisReporter` chịu trách nhiệm trình bày dữ liệu ra nơi quan sát.

## 3. Hợp đồng của `FailureAnalyzer`

Giao diện cơ bản có dạng:

~~~java
public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
~~~

Đây là **chữ ký API rút gọn** của `org.springframework.boot.diagnostics.FailureAnalyzer`, không phải source file cần thêm vào ứng dụng.

Hợp đồng quan trọng:

- Trả về một `FailureAnalysis` khi analyzer **hiểu và có hướng xử lý phù hợp** cho exception.
- Trả về `null` nếu lỗi **không thuộc phạm vi** hoặc thông tin không đủ để phân tích có ý nghĩa.
- **Không** biến `null` thành “lỗi đã được xử lý thành công”. Spring Boot có thể xét các analyzer khác hoặc dùng cơ chế log lỗi còn lại.
- Không nuốt exception khởi động để ứng dụng tiếp tục chạy khi trạng thái chưa hợp lệ.
- Không thực hiện tác động phụ nguy hiểm (xóa file, đổi cấu hình, sửa DB, tự restart) chỉ để tạo thông điệp.

Nếu tự triển khai giao diện, có thể cần duyệt chuỗi `Throwable.getCause()` vì lỗi thực bị Spring bọc. Cách gọn hơn cho đa số tình huống là kế thừa `AbstractFailureAnalyzer<T>`.

## 4. `AbstractFailureAnalyzer<T>` tìm đúng kiểu exception

Spring Boot cung cấp lớp cơ sở:

~~~java
public abstract class AbstractFailureAnalyzer<T extends Throwable>
        implements FailureAnalyzer {

    protected abstract FailureAnalysis analyze(
            Throwable rootFailure, T cause);
}
~~~

Đây là **mô tả rút gọn phần mở rộng cần triển khai**; lớp thật còn có method khác, bao gồm việc phân tích toàn bộ `Throwable` và tìm `cause` phù hợp.

Ý nghĩa hai tham số:

- `rootFailure`: exception ngoài cùng mà Spring Boot chuyển vào quá trình phân tích.
- `cause`: exception kiểu `T` được nhận ra trong chuỗi nguyên nhân; thường gần điều kiện lỗi mà analyzer muốn xử lý.

Ví dụ exception gốc nằm sâu:

~~~text
ApplicationContextException
  -> BeanCreationException
       -> BeanInstantiationException
            -> MissingTargetException
~~~

Với:

~~~java
public final class MissingTargetFailureAnalyzer
        extends AbstractFailureAnalyzer<MissingTargetException> {
    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, MissingTargetException cause) {
        // ...
    }
}
~~~

Spring Boot giúp gọi phương thức protected khi chuỗi lỗi có `MissingTargetException`. Bạn không cần tự viết vòng lặp duyệt `getCause()` trong trường hợp này.

Nếu không thể đưa ra khuyến nghị đáng tin (ví dụ nhận đúng exception type nhưng thiếu dữ liệu cần thiết), analyzer **có thể trả `null`** để analyzer khác có cơ hội xử lý. Đừng tự trả một hành động khắc phục mơ hồ hoặc sai chỉ để luôn có báo cáo.

## 5. `FailureAnalysis` chứa những gì?

Spring Boot 3.3 có constructor:

~~~java
new FailureAnalysis(description, action, cause)
~~~

Và các phương thức:

~~~java
analysis.getDescription();
analysis.getAction();
analysis.getCause();
~~~

Trong đó:

| Trường | Ý nghĩa | Nội dung nên có |
| --- | --- | --- |
| `description` | Mô tả tình trạng thất bại bằng ngôn ngữ người vận hành hiểu | Tên cấu hình/bean/điều kiện sai, nêu chính xác và có ngữ cảnh |
| `action` | Các bước khắc phục cụ thể | Đổi property nào, kiểm tra file nào, chạy lệnh nào, xác nhận kết quả ra sao |
| `cause` | Exception liên quan đến phân tích | Cung cấp ngữ cảnh kỹ thuật, hữu ích cho log/điều tra sâu |

Một `FailureAnalysis` có thể được tạo như sau:

~~~java
FailureAnalysis analysis = new FailureAnalysis(
        "Required setting 'demo.target' is missing or blank.",
        "Set --demo.target=local and restart the application.",
        cause);
~~~

Đây là đoạn **bên trong phương thức Java** với biến `cause` kiểu `Throwable` và import `FailureAnalysis`. Nó không phải một chương trình độc lập.

**Hành động khắc phục không được chỉ viết** “Check configuration” hay “Contact support” trong mọi tình huống. Người đọc đã biết lỗi, họ cần biết **chính xác vị trí và thao tác tiếp theo**. Tài liệu nên hướng đến mô tả đúng nguyên nhân, ít gây hiểu lầm và không lộ bí mật.

### Description khác Action ở điểm nào?

Description trả lời **“đang sai điều gì?”**. Action trả lời **“để sửa, làm thao tác nào tiếp theo?”**.

Ví dụ:

~~~text
Description:
Property 'demo.target' is required but was not supplied.

Action:
Add --demo.target=local to the application arguments,
or define demo.target in application.properties,
then launch the application again.
~~~

Description không chỉ lặp lại class name `MissingTargetException`. Action không chỉ yêu cầu đọc lại stack trace.

## 6. Khi nào Spring Boot chạy failure analysis?

Với đường khởi động thất bại của `SpringApplication.run(...)`, quá trình có thể tóm tắt:

~~~text
main()
   |
   v
SpringApplication.run(args)
   |
   +-- Environment / context creation
   |
   +-- Bean definitions / refresh context
   |       |
   |       +-- xảy ra exception
   |
   v
Xử lý failure trong SpringApplication
   |
   +-- Thông báo lỗi và dọn dẹp context khi có thể
   |
   +-- Tải/áp dụng các FailureAnalyzer phù hợp
   |       |
   |       +-- FailureAnalysis(description, action, cause)
   |
   +-- FailureAnalysisReporter ghi phân tích
   |
   v
run(...) không hoàn tất bình thường; ứng dụng không đạt ready
~~~

Sơ đồ là **mô hình khái niệm**, không mô tả từng lời gọi nội bộ theo thứ tự tuyệt đối của mọi exception. Giai đoạn lỗi có thể xảy ra **trước khi context hoặc BeanFactory hoàn chỉnh**.

Quan trọng:

- Failure analysis là **cơ chế chẩn đoán lỗi khi ứng dụng khởi động**.
- Nó **không** tự động biến mọi exception xảy ra nhiều giờ sau startup thành thông điệp `APPLICATION FAILED TO START`.
- Nó **không** thay thế `@ControllerAdvice` hay `@ExceptionHandler` để trả lỗi HTTP của một request.
- Nó **không** tự động sửa cấu hình, retry startup, hoặc làm ứng dụng tiếp tục chạy sau lỗi nghiêm trọng.
- Nó **không** bảo đảm luôn có một analyzer phù hợp; với lỗi lạ, Spring Boot vẫn phải cung cấp log để điều tra.

### Các ví dụ được Spring Boot hỗ trợ sẵn

Spring Boot có các failure analyzers dựng sẵn cho nhiều kiểu lỗi, trong đó có **cổng web server bị chiếm**, lỗi binding/validation một số thuộc tính cấu hình, và những tình huống liên quan đến context/bean. Không cần tự viết analyzer cho lỗi đã có thông báo đầy đủ và hành động khắc phục rõ.

Hãy đọc nội dung **Description/Action đã xuất hiện trước** khi quyết định thêm một analyzer riêng. Viết custom analyzer cho từng exception Java chung chung dễ tạo thông báo chẩn đoán sai.

## 7. Đăng ký analyzer tùy biến qua `META-INF/spring.factories`

Một điểm dễ sai: analyzer được cần đến **ngay cả khi application context không tạo xong**. Vì vậy, theo hướng dẫn Spring Boot, **chỉ gắn `@Component` cho một lớp `FailureAnalyzer` không phải cách đăng ký đáng tin cậy cho đường bootstrap failure**.

Cách chính thức cho Spring Boot 3.3 là tạo:

~~~text
src/main/resources/META-INF/spring.factories
~~~

với key:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failure.MissingTargetFailureAnalyzer
~~~

Lưu ý:

- Key phải là **`org.springframework.boot.diagnostics.FailureAnalyzer`**, không phải `FailureAnalysis` hay `FailureAnalysisReporter`.
- Value phải là **tên class đầy đủ**, gồm package, và class phải nằm trên runtime classpath.
- Đường resource phải là **`META-INF/spring.factories`**, khác với `application.properties` hoặc metadata auto-configuration `AutoConfiguration.imports`.
- Cơ chế bootstrap dùng Spring factories loader để phát hiện implementation từ các JAR và resource trên classpath.
- Lớp analyzer phải tạo được trong giai đoạn lỗi; thiết kế đơn giản nhất là class `public` có constructor không tham số, không cần phụ thuộc vào bean nghiệp vụ.
- Nếu khai báo nhiều analyzers trong cùng file `spring.factories`, có thể dùng danh sách các class đầy đủ phân cách bằng dấu phẩy; không tạo nhiều key giống nhau rồi trông chờ mọi giá trị chắc chắn được giữ.

Một thư viện starter cũng có thể đóng gói analyzer và `spring.factories` để **các ứng dụng sử dụng thư viện có chẩn đoán phù hợp**, nhưng analyzer cần chỉ nhận các exception thuộc ngữ cảnh của thư viện, tránh chiếm quyền xử lý lỗi không liên quan.

### Spring Boot 3.x đã bỏ `spring.factories` chưa?

**Chưa bỏ cho `FailureAnalyzer`.** Trong Spring Boot 3.3, danh sách **auto-configuration** đã có metadata chuyên biệt `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, nhưng custom `FailureAnalyzer` vẫn được đăng ký theo **`META-INF/spring.factories`**. Đừng lẫn hai cơ chế.

## 8. Ví dụ hoàn chỉnh: thiếu cấu hình thì có Description và Action

Ta xây dựng một **Spring Boot CLI** cần thuộc tính bắt buộc `demo.target`. Không cung cấp hoặc cung cấp chuỗi rỗng thì context không khởi động được. Analyzer riêng biến `MissingTargetException` thành thông báo hướng dẫn sửa cụ thể. Khi truyền cấu hình hợp lệ, ứng dụng chạy và in dấu mốc thành công.

Ví dụ dùng **Java 17, Spring Boot 3.3.13 và Gradle**, không cần web server hoặc database. Nó minh họa **failure do khởi tạo bean trong refresh**, tức là lỗi xảy ra đúng đường mà Spring Boot có thể phân tích.

### 8.1. Cấu trúc dự án

~~~text
failure-analysis-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/failure/
    │   │   ├── FailureAnalysisDemoApplication.java
    │   │   ├── MissingTargetException.java
    │   │   └── MissingTargetFailureAnalyzer.java
    │   └── resources/META-INF/spring.factories
    └── test/java/com/example/failure/
        └── MissingTargetFailureAnalyzerTest.java
~~~

**Ba lớp Java nguồn chính có package giống nhau**; tệp `spring.factories` tham chiếu đúng tên lớp analyzer.

### 8.2. Gradle cấu hình đúng dependency versions

`settings.gradle`:

~~~groovy
rootProject.name = 'failure-analysis-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    // Dùng Gradle native BOM để quản lý phiên bản Spring Boot starters.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Vì các starter được khai báo **không có version**, cần BOM như trên hoặc một cơ chế quản lý dependencies tương đương. Plugin `org.springframework.boot` **một mình không nên được hiểu là đủ thay thế toàn bộ khai báo dependency management**.

Môi trường: JDK 17+ và Gradle tương thích Spring Boot 3.3. Ví dụ dùng Java 17 để dễ chạy trên nhiều môi trường và không phụ thuộc web starter.

### 8.3. Exception riêng có ngữ nghĩa rõ

Tệp `src/main/java/com/example/failure/MissingTargetException.java`:

~~~java
package com.example.failure;

public final class MissingTargetException extends IllegalStateException {

    private final String propertyName;

    public MissingTargetException(String propertyName) {
        super("Missing required configuration: " + propertyName);
        this.propertyName = propertyName;
    }

    public String getPropertyName() {
        return this.propertyName;
    }
}
~~~

Vì là `IllegalStateException` tùy biến, nó có stack trace bình thường nhưng còn cung cấp **tên thuộc tính bị thiếu** cho analyzer. Không đưa **giá trị secret** hoặc token vào exception message.

Ở hệ thống thật, nên thiết kế một exception type có ý nghĩa rõ, không tạo một analyzer chung cho mọi `IllegalStateException` vì quá rộng.

### 8.4. Ứng dụng tạo bean cần thuộc tính `demo.target`

Tệp `src/main/java/com/example/failure/FailureAnalysisDemoApplication.java`:

~~~java
package com.example.failure;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class FailureAnalysisDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(FailureAnalysisDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }

    @Bean
    DemoTarget demoTarget(Environment environment) {
        String value = environment.getProperty("demo.target");

        if (value == null || value.isBlank()) {
            throw new MissingTargetException("demo.target");
        }

        return new DemoTarget(value);
    }

    @Bean
    ApplicationRunner showTarget(DemoTarget target) {
        return args -> System.out.println("STARTUP_OK target=" + target.value());
    }

    record DemoTarget(String value) {
    }
}
~~~

Giải thích:

1. `@SpringBootApplication` kích hoạt Spring Boot auto-configuration và component/bean definition processing.
2. `WebApplicationType.NONE` chọn kiểu ứng dụng console, không có web server.
3. `@Bean demoTarget(...)` tạo singleton thông thường **trong lúc refresh context** khi global lazy chưa bật.
4. Nếu `demo.target` trống hoặc không có, method **ném `MissingTargetException`**. Spring có thể bọc exception trong một hoặc nhiều lớp lỗi tạo bean.
5. Nếu hợp lệ, bean `DemoTarget` được tạo; `ApplicationRunner` in dòng thành công.
6. Không có `try/catch` ở `main` để nuốt lỗi startup hoặc tự in thêm một thông báo sai.
7. `String.isBlank()` và `record` đều có trên Java 17.

**Giới hạn của ví dụ:** property `demo.target` là khóa minh họa; không có tích hợp thật tới URL/dịch vụ bên ngoài. Trong ứng dụng thực, validate định dạng/khả năng kết nối ở giai đoạn phù hợp và không log secret.

**Chú ý lazy:** Nếu bật `spring.main.lazy-initialization=true`, một bean có thể không được tạo ngay. Ví dụ còn có `ApplicationRunner` cần bean `DemoTarget` nên nó thường vẫn được yêu cầu trước mốc ready. Khi kiểm thử lỗi trong startup, giữ global lazy ở mặc định `false` để quan sát chắc chắn tình huống bean fail trong refresh.

### 8.5. Analyzer tìm exception trong cause chain

Tệp `src/main/java/com/example/failure/MissingTargetFailureAnalyzer.java`:

~~~java
package com.example.failure;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class MissingTargetFailureAnalyzer
        extends AbstractFailureAnalyzer<MissingTargetException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, MissingTargetException cause) {

        String property = cause.getPropertyName();

        String description =
                "Required configuration '" + property + "' is missing or blank.";

        String action =
                "Set --" + property + "=local when starting the application, "
                + "or add " + property + "=local to application.properties. "
                + "Then restart the application.";

        return new FailureAnalysis(description, action, cause);
    }
}
~~~

**Đây là một class hoàn chỉnh** và phù hợp hợp đồng generic của `AbstractFailureAnalyzer`:

- Chỉ xử lý lỗi có `MissingTargetException` trong chuỗi cause.
- Dùng property name để tạo nội dung cụ thể.
- `description` nêu chính xác tình trạng.
- `action` đưa ra **hai cách sửa** có thể làm ngay: command-line argument hoặc file cấu hình.
- `cause` giữ exception chuyên biệt đã được nhận diện trong `FailureAnalysis`.
- Không truy cập `ApplicationContext`, không inject bean và không làm I/O trong analyzer.

Mặc dù chữ ký có tham số `rootFailure`, bài demo không cần nó để giải thích vì đã có `cause` phù hợp. `AbstractFailureAnalyzer` vẫn tìm `cause` từ exception ngoài cùng do Spring Boot chuyển vào.

Nếu analyzer cần xử lý một exception chung có nhiều tình huống, hãy kiểm tra điều kiện cụ thể và trả `null` cho trường hợp không đủ dữ liệu, tránh khuyến nghị sai.

### 8.6. Đăng ký bằng `spring.factories`

Tạo tệp `src/main/resources/META-INF/spring.factories` chứa **đúng một dòng**:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failure.MissingTargetFailureAnalyzer
~~~

Phải bảo đảm tệp resource nằm đúng thư mục `META-INF` trong runtime classpath. Với Gradle Java plugin thông thường, nội dung trong `src/main/resources` được đóng gói như resource.

**Không** thay bằng:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=com.example.failure.MissingTargetFailureAnalyzer
~~~

vì analyzer không phải lớp auto-configuration. Cũng không dùng tệp `AutoConfiguration.imports` để khai báo analyzer.

### 8.7. Unit test hành vi của analyzer

Tệp `src/test/java/com/example/failure/MissingTargetFailureAnalyzerTest.java`:

~~~java
package com.example.failure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MissingTargetFailureAnalyzerTest {

    private final MissingTargetFailureAnalyzer analyzer =
            new MissingTargetFailureAnalyzer();

    @Test
    void recognizesNestedCauseAndSuppliesAction() {
        MissingTargetException cause =
                new MissingTargetException("demo.target");
        Throwable wrapper = new IllegalStateException(
                "Bean creation failed", cause);

        FailureAnalysis analysis = analyzer.analyze(wrapper);

        assertNotNull(analysis);
        assertTrue(analysis.getDescription().contains("demo.target"));
        assertTrue(analysis.getAction().contains("--demo.target=local"));
        assertSame(cause, analysis.getCause());
    }

    @Test
    void ignoresUnrelatedExceptions() {
        FailureAnalysis analysis = analyzer.analyze(
                new IllegalArgumentException("Unrelated failure"));
        assertNull(analysis);
    }
}
~~~

Test thứ nhất xác nhận **cause nằm trong exception bọc** vẫn được nhận ra; test thứ hai xác nhận analyzer không chiếm lỗi không liên quan. Test này trực tiếp gọi analyzer chứ **không tự kiểm tra đường nạp `spring.factories` hoặc banner startup đầy đủ**. Vì thế còn cần thử bằng executable JAR.

### 8.8. Build

Trong thư mục dự án có Gradle Wrapper phù hợp:

~~~bash
./gradlew clean test bootJar
~~~

Trên PowerShell Windows:

~~~powershell
.\gradlew.bat clean test bootJar
~~~

Khi chưa có wrapper nhưng đã cài Gradle phù hợp:

~~~bash
gradle clean test bootJar
~~~

Với `rootProject.name` và `version` của ví dụ, tên JAR thường là:

~~~text
build/libs/failure-analysis-demo-1.0.0.jar
~~~

Nếu dự án thay đổi tên artifact/classifier, hãy dùng file được build thực tế.

### 8.9. Chạy nhánh thất bại

Mở một tiến trình Java mới, **không truyền `demo.target`**:

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar
~~~

Trên nhánh lỗi do thiếu cấu hình và khi analyzer được nạp đúng, log nên có **phần nội dung** tương đương:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Required configuration 'demo.target' is missing or blank.

Action:

Set --demo.target=local when starting the application, or add
demo.target=local to application.properties. Then restart the application.
~~~

Bản trên là **trích phần chẩn đoán kỳ vọng**, không phải cam kết toàn bộ stdout/stderr và line wrapping. Reporter có thể thêm timestamp/logger name, các dòng log khác và formatting riêng. Ý nghĩa cần kiểm chứng là **Description/Action chứa đúng key và hành động**.

Ứng dụng **không in** `STARTUP_OK` trên đường thiếu cấu hình. `SpringApplication.run` không hoàn tất bình thường. Quá trình chạy executable JAR theo đường thất bại thường có **exit code khác 0**, nhưng phải kiểm chứng thực tế ở JVM được khởi chạy; đừng đọc mã của Gradle wrapper rồi giả định là mã của Java.

### 8.10. Chạy nhánh thành công

Một tiến trình Java mới với property hợp lệ:

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar --demo.target=local
~~~

Các marker do **chính demo** in:

~~~text
STARTUP_OK target=local
~~~

Không còn `MissingTargetException` cho trường hợp này và không có lý do để analyzer phát Description/Action. Logger Spring Boot có thể in thêm các dòng thông thường. Trong ứng dụng CLI không có web server hay non-daemon worker khác, JVM có thể kết thúc sau khi chạy xong runner; nếu dùng ứng dụng web lâu dài, tiến trình thường tiếp tục chạy để phục vụ request.

### 8.11. Chạy thử định dạng rỗng

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar --demo.target=
~~~

Giá trị `""` rỗng sẽ bị `String.isBlank()` coi là không hợp lệ, nên analyzer được kích hoạt. Cần kiểm tra cấu hình thực tế không có nguồn property khác được ưu tiên hoặc không vô tình bật global lazy làm thay đổi mốc tạo bean.

## 9. Cách viết Description có giá trị

Description nên đạt ba tiêu chí:

1. **Đúng hiện tượng:** nêu điều kiện quan sát được mà code xác nhận.
2. **Đủ ngữ cảnh:** ghi tên property/bean/port/file/config source có liên quan.
3. **Không giả định quá mức:** nếu chỉ biết kết nối thất bại, đừng kết luận chắc chắn “mật khẩu sai”.

So sánh:

| Chưa tốt | Tốt hơn |
| --- | --- |
| “Bean creation failed” | “Bean 'paymentClient' could not start because required property 'payment.endpoint' is missing.” |
| “Database down” | “Database connection could not be established with the configured endpoint.” |
| “Bad value” | “The value of 'worker.parallelism' must be greater than zero.” |
| “An error occurred” | “The configured HTTP port could not be bound by the embedded server.” |

Đối với các trường hợp code có thể xác định chính xác, Description phải **rõ hơn loại exception framework**. Nhưng khi chưa biết nguyên nhân ngoài hệ thống, sử dụng ngôn ngữ thận trọng như “không kết nối được” và để log giữ nguyên exception kỹ thuật.

### Có nên đưa raw `Exception.getMessage()` trực tiếp vào Description?

Có thể hữu ích trong trường hợp rõ ràng, nhưng phải kiểm tra **dữ liệu nhạy cảm**, format khó đọc và sự ổn định. Một số driver đưa connection string, username, path hoặc chi tiết request vào message. Không ghi credential, token hoặc toàn bộ connection URL vào báo cáo startup chỉ để tạo thông tin khắc phục.

## 10. Cách viết Action thật sự có thể thực hiện

Một hành động khắc phục hữu ích trả lời các câu hỏi:

- **Thay đổi cái gì?** Ví dụ `demo.target`, `server.port`, secret key, dependency.
- **Thay ở đâu?** `application.properties`, biến môi trường, CLI argument, ConfigMap/Secret, cấu hình deploy.
- **Giá trị hoặc tiêu chí hợp lệ là gì?** Ví dụ “non-empty”, port chưa dùng, URL đúng định dạng.
- **Kiểm tra bằng cách nào?** Khởi chạy lại, xem readiness/startup log, kiểm tra binding hoặc connection.
- **Nếu vẫn lỗi thì xem đâu?** Nơi có stack trace/condition report phù hợp.

Ví dụ với property:

~~~text
Action:
Set demo.target to a non-blank value using
--demo.target=local or application.properties,
then restart and verify the startup succeeds.
~~~

Ví dụ với port bị chiếm:

~~~text
Action:
Find the process that occupies the configured server.port,
stop that process if appropriate, or assign an unused port,
then restart the application.
~~~

Ví dụ với file bắt buộc không có:

~~~text
Action:
Ensure the specified configuration file exists and is readable
inside the running container; verify its mount path and permissions,
then restart the application.
~~~

**Không** viết Action đề xuất xóa database, nới quyền truy cập tùy tiện, tắt bảo mật hoặc chia sẻ password vào log. Chẩn đoán phải dẫn tới thao tác an toàn và đúng quyền.

## 11. Vì sao analyzer đôi khi không chạy?

Những nguyên nhân thường gặp nhất:

| Hiện tượng | Khả năng xảy ra | Cách kiểm tra |
| --- | --- | --- |
| Chỉ thấy stack trace mặc dù có class analyzer | Resource `spring.factories` không nằm trên runtime classpath | Kiểm tra đường dẫn và nội dung JAR |
| Analyzer không được tạo | Sai tên fully qualified class, constructor không phù hợp | Kiểm tra package, class visibility, dependency |
| Analyzer tồn tại nhưng không match | Exception thực tế không chứa kiểu `T` trong cause chain | Kiểm tra root cause và unit test |
| `analyze(...)` trả `null` | Điều kiện xử lý không đạt hoặc cố ý chuyển cho analyzer khác | Kiểm tra nhánh logic |
| Dùng `@Component` thay vì `spring.factories` | Context có thể thất bại trước khi bean được tạo | Đăng ký theo cơ chế bootstrap |
| Dùng `AutoConfiguration.imports` | Nhầm key auto-configuration với analyzer | Dùng key `org.springframework.boot.diagnostics.FailureAnalyzer` |
| Có nhiều analyzers liên quan | Analyzer khác có thể được xét trước | Thu hẹp phạm vi exception và kiểm tra ordering |
| Lỗi xảy ra **sau startup** | Không đi qua failure handling của `SpringApplication.run` | Sử dụng logging, `@ControllerAdvice`, metrics phù hợp |
| Không có Description/Action trong log | Cấu hình logging/reporting không hiển thị hoặc không có analyzer phù hợp | Xem log startup, reporter, level và cause |
| Chỉ kiểm tra `bootRun` exit status | Gradle có thể trả mã riêng | Chạy executable JAR trực tiếp |

Không tự đổi tất cả exception sang một lớp chung chỉ để analyzer “match” nhiều hơn. Analyzer nên có **trách nhiệm hẹp**, match bằng cause rõ ràng và không gây chẩn đoán sai.

### Kiểm tra resource đã được đóng gói

Sau `./gradlew bootJar`:

~~~bash
jar tf build/libs/failure-analysis-demo-1.0.0.jar
~~~

Trong executable Spring Boot JAR, resource của ứng dụng thường xuất hiện với logical path:

~~~text
BOOT-INF/classes/META-INF/spring.factories
~~~

Nếu analyzer nằm trong JAR thư viện phụ thuộc, resource có thể nằm trong một JAR ở `BOOT-INF/lib`. Việc thấy resource chỉ chứng minh **nó đã được đóng gói**, chưa chứng minh class được tải, constructor thành công hoặc exception match. Phải thử cả đường startup thất bại và thành công.

## 12. Kiểm tra thực tế bằng shell và CI

### Bash: ghi log và bảo toàn exit code

Không nên tự động kết luận “có thông điệp Action” đồng nghĩa shell đã nhận mã lỗi. Hãy chạy executable JAR rồi đọc status:

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar > fail.log 2>&1
status=$?
printf 'JAVA_EXIT=%s\n' "$status"
~~~

Trên đường startup thất bại, status **thường khác 0**. Đối chiếu thêm log:

~~~bash
grep -F "APPLICATION FAILED TO START" fail.log
grep -F "demo.target" fail.log
grep -F "Action:" fail.log
~~~

Các lệnh `grep` là phép kiểm tra thủ công ở môi trường test, không phải toàn bộ script CI chống lỗi. Nếu đang bật `set -e`, hãy đặt lệnh Java trong `if`/`else` để non-zero không làm script thoát trước khi ghi kết quả.

### PowerShell

~~~powershell
java -jar .\build\libs\failure-analysis-demo-1.0.0.jar
$code = $LASTEXITCODE
Write-Output "JAVA_EXIT=$code"
~~~

`$LASTEXITCODE` là mã từ native executable; khác với `$?` Boolean của PowerShell. Khi đo lỗi startup, kiểm tra log console/redirect tương ứng.

### CI nên xác nhận cả hai đường

Một smoke test CI tốt kiểm tra:

1. **Không có `demo.target`** → JAR trả non-zero và log có đúng Description/Action.
2. **Có `--demo.target=local`** → JAR chạy thành công và có `STARTUP_OK target=local`.
3. **Tệp `spring.factories`** thực sự được đóng gói đúng vị trí.
4. Thông điệp không in secret hoặc dữ liệu nhạy cảm.
5. Thay đổi code/config gây lỗi mới không khiến analyzer biến thành một thông báo chung chung.

Đừng buộc so sánh **toàn bộ stdout/stderr chính xác từng byte**: timestamp, version, logger và stack trace có thể khác. Kiểm chứng các mốc và nội dung quan trọng; vẫn giữ nguyên log thô phục vụ điều tra.

## 13. `FailureAnalysisReporter` dùng khi nào?

`FailureAnalyzer` **phân tích**, còn `FailureAnalysisReporter` **báo cáo**. Giao diện:

~~~java
public interface FailureAnalysisReporter {
    void report(FailureAnalysis analysis);
}
~~~

Đây là chữ ký rút gọn; Spring Boot có `LoggingFailureAnalysisReporter` thực hiện việc ghi log tiêu chuẩn.

Thông thường **không cần viết reporter riêng**. Chỉ nên thêm khi có yêu cầu rõ như:

- Ghi một sự kiện chẩn đoán vào hệ thống giám sát độc lập, với dữ liệu đã lọc.
- Chuẩn hóa format cho môi trường container hoặc công cụ vận hành.
- Gắn mã sự cố nội bộ vào thông điệp có kiểm soát.

Nếu thật sự cần reporter riêng, hãy nhớ nó chạy trong **tình huống khởi động thất bại**, nên không được dựa vào một Spring bean/HTTP client/queue listener mà context có thể chưa tạo. Reporter không nên tự sửa lỗi, tự tạo ứng dụng mới hoặc làm failure path ném thêm exception.

### Reporter tùy biến là một ví dụ về phần mở rộng khác

~~~java
package com.example.failure;

import org.springframework.boot.diagnostics.FailureAnalysis;
import org.springframework.boot.diagnostics.FailureAnalysisReporter;

public final class CompactFailureReporter
        implements FailureAnalysisReporter {

    @Override
    public void report(FailureAnalysis analysis) {
        System.err.println("BOOT_FAILURE: " + analysis.getDescription());
        System.err.println("REMEDIATION: " + analysis.getAction());
    }
}
~~~

Đây là **class minh họa tùy chọn**, không phải file bắt buộc trong dự án phần 8. Nếu muốn dùng, cần cấu hình đăng ký reporter theo tài liệu Spring Boot tương ứng và đảm bảo nó không ghi thông tin nhạy cảm; **không mặc định cho rằng chỉ tạo class là Boot tự tìm ra**.

Thêm reporter có thể dẫn tới nhiều đầu ra nếu reporter log mặc định cũng hoạt động. Vì vậy, trước khi thêm hãy cân nhắc liệu một failure analysis tốt qua logging mặc định đã đủ nhu cầu hay chưa.

## 14. `FailureAnalyzer` khác `@ControllerAdvice` và `ApplicationFailedEvent`

| Cơ chế | Phạm vi | Phù hợp khi |
| --- | --- | --- |
| `FailureAnalyzer` | Phân tích Throwable khi `SpringApplication` startup thất bại | Muốn Description/Action hữu ích lúc ứng dụng không lên được |
| `FailureAnalysis` | Dữ liệu phân tích | Truyền mô tả, khắc phục và cause tới reporter |
| `FailureAnalysisReporter` | Trình bày kết quả phân tích | Cần log hoặc báo cáo lỗi bootstrap |
| `ApplicationFailedEvent` | Sự kiện Spring Boot phát khi khởi động thất bại | Listener cần quan sát sự kiện failure, dọn thông tin bootstrap phù hợp |
| `@ControllerAdvice` / `@ExceptionHandler` | Lỗi xử lý HTTP request trong context đang hoạt động | Trả response phù hợp cho API client |
| `ConditionEvaluationReport` | Thông tin vì sao điều kiện auto-configuration match/không match | Điều tra auto-configuration và bean |
| `ExitCodeGenerator` / `ExitCodeExceptionMapper` | Quy định exit status của tiến trình khi áp dụng | Shell/Job/CI cần mã thành công/thất bại |

Một analyzer **không phải cơ chế retry**, không thay thế logging thông thường và không quyết định tự động mã thoát riêng cho mọi lỗi. Nếu ứng dụng cần mã lỗi cụ thể cho shell, đó là **một hợp đồng khác** với các API exit-code.

## 15. Điều tra khi không analyzer nào nhận diện được lỗi

Nếu không có analyzer phù hợp, cách xử lý đúng là tiếp tục **điều tra bằng exception chain và dữ liệu điều kiện của Spring Boot**.

Trong môi trường debug, có thể chạy:

~~~bash
java -jar build/libs/failure-analysis-demo-1.0.0.jar --debug
~~~

`--debug` có thể khiến Spring Boot in thêm thông tin liên quan đến **ConditionEvaluationReport**, bao gồm vì sao một số auto-configuration có hoặc không được áp dụng. Nó **không tự tạo một FailureAnalyzer cho mọi lỗi** và không chắc giải thích được lỗi trong code nghiệp vụ.

Đối với ứng dụng đã khởi động thành công và có Actuator với endpoint phù hợp, `/actuator/conditions` hỗ trợ xem điều kiện cấu hình. Nhưng khi ứng dụng **không lên được**, đừng trông chờ gọi endpoint HTTP của chính ứng dụng đã fail.

Các bước điều tra:

1. Xác định failure xảy ra trước hay trong `ApplicationContext.refresh()`.
2. Tìm exception ngoài cùng và các `Caused by` lồng nhau.
3. Xác định bean/property/port/resource liên quan.
4. Kiểm tra có analyzer mặc định đã báo Action phù hợp không.
5. Nếu đây là lỗi riêng của thư viện/ứng dụng và lặp lại thường xuyên, tạo custom exception + analyzer **hẹp**.
6. Kiểm tra hành động khắc phục trên môi trường thử nghiệm và cập nhật runbook.
7. Không xóa stack trace/exception cause chỉ vì đã có banner phân tích.

## 16. Analyzer có thể nhận `Environment` hoặc `BeanFactory` không?

Theo tài liệu Spring Boot về custom failure analyzer, nếu cần thông tin từ `Environment` hoặc `BeanFactory`, implementation có thể khai báo chúng như **constructor arguments** để cơ chế nạp analyzer sử dụng khi khả dụng.

Nhưng cần lưu ý:

- Failure có thể xảy ra **trước** khi một `BeanFactory` hoàn thiện hoặc context hoạt động.
- Không giả định mọi bean nghiệp vụ đều được tạo thành công để inject vào analyzer.
- Không tạo kết nối DB, gọi REST API hoặc truy cập secrets trong constructor analyzer.
- Nếu có thể xây dựng Description/Action chỉ từ **exception type và dữ liệu an toàn trong exception**, giải pháp đó thường đơn giản và bền vững hơn.

Ví dụ của bài chỉ có constructor không tham số nên không phụ thuộc trạng thái context. Điều này giúp analyzer xử lý lỗi tạo bean mà không vô tình gây thêm lỗi bootstrap.

## 17. Thứ tự nhiều analyzers và nguyên tắc trả `null`

Một ứng dụng có thể có analyzers sẵn của Spring Boot, analyzers từ starter và analyzers của code nội bộ.

Nếu một analyzer nhận diện lỗi quá rộng, nó có thể đưa ra khuyến nghị sai hoặc chiếm cơ hội chẩn đoán chi tiết hơn từ analyzer khác. Vì vậy:

- Chọn exception type **chuyên biệt**, ví dụ `MissingTargetException` thay vì mọi `RuntimeException`.
- Trả `null` khi dữ liệu chưa đủ để đưa ra Action chính xác.
- Khi thứ tự lựa chọn quan trọng, đối chiếu khả năng dùng cơ chế ordering theo API và version đang chạy; không dựa vào thứ tự các tệp JAR trên classpath.
- Không yêu cầu tất cả analyzers cùng “tạo một chuỗi Action” rồi mặc định framework sẽ tự ghép các thông điệp. Thực tế cần xác định **một phân tích hữu ích** cho lỗi đang xảy ra.
- Unit test analyzer độc lập và smoke test **đường khởi động thật** để phát hiện xung đột với analyzer khác.

Đừng lạm dụng `FailureAnalyzer` làm công cụ bắt mọi exception chung của ứng dụng. Cấu trúc chẩn đoán phải phản ánh điều kiện lỗi **đã được chứng minh**.

## 18. Tương tác với lazy initialization

Nếu đặt:

~~~properties
spring.main.lazy-initialization=true
~~~

một số bean có thể chỉ được tạo khi được gọi lần đầu **sau startup**. Lúc đó, lỗi bean tạo muộn **có thể không đi qua đường `SpringApplication.run` failure**, nên custom failure analyzer sẽ không tự hiển thị banner startup như khi lỗi xuất hiện lúc refresh.

Vì vậy, nếu một bean **bắt buộc đúng trước khi nhận traffic**, nên:

- Đánh dấu bean quan trọng non-lazy nếu cần.
- Đảm bảo startup check/runner chạm tới bean quan trọng trước readiness, phù hợp kiến trúc.
- Viết integration test kích hoạt cả đường first-use, không chỉ xác nhận context đã mở.
- Dùng logging và xử lý lỗi runtime phù hợp cho lỗi xảy ra sau khi ứng dụng đã sẵn sàng.

Không nên coi `FailureAnalyzer` là cách làm lỗi của một bean lazy luôn “dễ hiểu” tại mọi thời điểm vòng đời.

## 19. Bảo mật thông tin trong Description và Action

Một thông điệp startup có thể được thu thập bởi:

- Console log và hệ thống gom log.
- CI/CD và bản ghi thất bại khi deploy.
- Docker/Kubernetes logs.
- Monitoring, alert và ticket sự cố.

Do đó, không đưa vào Description/Action:

- Mật khẩu, API token, private key hoặc toàn bộ URL có credential.
- Giá trị raw của một property nhạy cảm.
- Full request body, dữ liệu khách hàng hoặc payload cá nhân.
- Stack trace bị cắt rồi dán toàn bộ vào một trường “Action”.

Thay vì “Password `secret123` is invalid”, nên viết “Configured credentials for datasource could not be validated; inspect the secret source and verify permissions.” Chỉ log **tên property hoặc loại tài nguyên cần kiểm tra**; không log giá trị secret.

Nếu thông tin nội bộ đặc biệt nhạy cảm, xem xét phân quyền đọc log/alert. Analyzer là công cụ **hỗ trợ điều tra**, không phải lý do bỏ qua các nguyên tắc bảo vệ log.

## 20. Danh sách kiểm tra khi thêm FailureAnalyzer vào thư viện

| Nội dung QA | Cần xác minh |
| --- | --- |
| Exception chuyên biệt | Có kiểu lỗi cụ thể, không match mọi exception |
| Description | Nêu chính xác điều kiện thất bại |
| Action | Có ít nhất một thao tác khắc phục khả thi |
| Cause | Giữ exception liên quan, không nuốt root cause |
| Scope | Chỉ xử lý lỗi startup phù hợp |
| Đăng ký | `META-INF/spring.factories` có key đúng |
| Classpath | Class và resource đều nằm trong artifact |
| Constructor | Không phụ thuộc bean chưa tạo |
| Null behavior | Lỗi không liên quan trả `null` |
| Build | Spring Boot version, BOM và Java tương thích |
| Unit test | Kiểm match cause lồng và lỗi không match |
| Smoke test | Chạy `java -jar` cả fail và success |
| Log | Không lộ secrets, mô tả dễ đọc |
| Exit status | Kiểm bằng shell, không chỉ đọc banner |
| Rollout | Có runbook nêu nơi sửa cấu hình và quyền thao tác |

**Đặc biệt:** thử **bản JAR đóng gói thật**, không chỉ classpath của IDE. Nhiều lỗi “analyzer không chạy” đến từ resource `spring.factories` không được đóng gói khi build/shading, hoặc tên package class không khớp.

## 21. Các lỗi thực hành phổ biến

**1. Chỉ gắn `@Component` cho analyzer.** Spring context có thể đã thất bại trước khi bean analyzer được tạo. Dùng `META-INF/spring.factories` cho đường bootstrap.

**2. Đặt analyzer vào `AutoConfiguration.imports`.** Đây là metadata khác mục đích; analyzer phải đăng ký bằng key `org.springframework.boot.diagnostics.FailureAnalyzer`.

**3. Dùng `FailureAnalysis` như exception để throw.** Nó là đối tượng dữ liệu; hãy throw exception chuyên biệt ở nơi lỗi xảy ra và phân tích exception trong analyzer.

**4. Không kiểm tra cause lồng nhau.** `BeanCreationException` thường bọc exception gốc. `AbstractFailureAnalyzer<T>` giúp tìm kiểu `T`.

**5. Luôn trả phân tích dù không match.** Có thể làm mất cơ hội chẩn đoán đúng; khi không đủ cơ sở, trả `null`.

**6. Action chỉ viết “Check logs”.** Đây không phải hướng khắc phục cụ thể. Nêu property, file, endpoint hoặc thao tác phù hợp.

**7. Thực hiện sửa lỗi ngay trong analyzer.** Phân tích không phải remediation engine. Tránh thay file, tạo kết nối hoặc gửi yêu cầu mạng.

**8. Nhìn thấy banner rồi coi ứng dụng đã tự phục hồi.** Khi bootstrap thất bại, context thường không hoạt động; banner chỉ giải thích.

**9. Cho rằng mọi exception runtime đều được analyzer xử lý.** Cơ chế này gắn với failure khi SpringApplication startup, không thay thế web exception handlers.

**10. So sánh chính xác toàn bộ log.** Timestamp, đường dẫn stack trace, logger và line wrapping thay đổi; test nội dung thiết yếu.

**11. Giả định lỗi đã phân tích sẽ tự trả một exit code tùy biến.** Phân tích và process exit là hai hợp đồng khác nhau; kiểm tra bằng executable JAR.

**12. Lấy `/actuator/conditions` từ chính ứng dụng đã fail.** App có thể chưa mở server. Dùng log/debug condition report trong quá trình khởi động.

**13. Đưa credentials vào Description.** Log startup có thể được chia sẻ rộng; chỉ nêu key/nguồn cần kiểm tra.

**14. Không kiểm thử nhánh success.** Analyzer đúng nhưng cấu hình hợp lệ vẫn fail do logic sai; cần chạy cả hai hướng.

**15. Thiếu Gradle dependency management.** Starter không có version mà không khai báo BOM/plugin quản lý phiên bản có thể làm build fail trước khi Spring Boot chạy; khi đó FailureAnalyzer không có cơ hội xử lý.

## 22. Câu hỏi tự kiểm tra

1. **`FailureAnalyzer` làm gì?** Nhận Throwable startup và có thể trả `FailureAnalysis` dễ hiểu.
2. **`FailureAnalysis` có ba thành phần nào?** Description, Action và Cause.
3. **`FailureAnalysisReporter` làm gì?** Trình bày/ghi nhận kết quả phân tích.
4. **`LoggingFailureAnalysisReporter` có vai trò gì?** Ghi failure analysis vào log.
5. **`FailureAnalyzer.analyze(...)` trả gì khi không xử lý được?** `null`.
6. **Vì sao dùng `AbstractFailureAnalyzer<MissingTargetException>`?** Để tìm kiểu exception chuyên biệt trong chuỗi cause.
7. **`rootFailure` khác `cause` ở đâu?** Root failure là exception ngoài cùng, cause là kiểu `T` đã được tìm thấy.
8. **Nên đăng ký custom analyzer ở đâu trong Spring Boot 3.3?** `META-INF/spring.factories`.
9. **Key để đăng ký là gì?** `org.springframework.boot.diagnostics.FailureAnalyzer`.
10. **Có thể chỉ dùng `@Component` cho lỗi xảy ra trước refresh không?** Không đáng tin cậy.
11. **`AutoConfiguration.imports` có dùng thay `spring.factories` để đăng ký analyzer không?** Không.
12. **Description khác Action thế nào?** Description nêu điều gì sai, Action nêu phải làm gì để sửa.
13. **Action “Check your configuration” đã đủ cụ thể chưa?** Thường chưa; cần chỉ rõ thuộc tính và cách sửa.
14. **FailureAnalyzer có tự sửa file cấu hình không?** Không; chỉ phân tích.
15. **Lỗi request HTTP `500` có tự hiện banner startup analysis không?** Không.
16. **Analyzer có chạy trên mọi bean lazy được tạo sau startup không?** Không tự động, vì có thể ngoài đường failure của `run()`.
17. **Muốn biết vì sao auto-configuration không match nên dùng gì?** ConditionEvaluationReport, thường qua `--debug` hoặc Actuator khi app hoạt động.
18. **Unit test analyzer có chứng minh tệp `spring.factories` đã được đóng gói đúng không?** Không, cần smoke test executable JAR.
19. **Nếu app thiếu `demo.target` trong ví dụ, có dòng `STARTUP_OK` không?** Không; bean fail trong refresh.
20. **Cung cấp `--demo.target=local` thì chuyện gì xảy ra?** Bean tạo thành công và runner in marker success.
21. **FailureAnalysis có đồng nghĩa shell nhận mã tùy biến không?** Không; kiểm tra exit status riêng.
22. **Nếu một exception message có token, có nên copy thẳng vào Description không?** Không; bảo vệ dữ liệu nhạy cảm.
23. **Khi nào không cần viết analyzer tùy biến?** Khi analyzer sẵn có đã cho mô tả và cách khắc phục đủ tốt.
24. **Vì sao cần giữ analyzer đơn giản?** Nó chạy khi bootstrap đã lỗi, context có thể không sẵn và lỗi trong analyzer có thể làm chẩn đoán tệ hơn.

**Kết luận:** Trong Spring Boot 3.3, `FailureAnalyzer` nhận lỗi khởi động, `AbstractFailureAnalyzer<T>` giúp tìm đúng exception trong chuỗi cause, `FailureAnalysis` mang **Description + Action + Cause**, và `FailureAnalysisReporter` trình bày kết quả. Đăng ký custom analyzer qua **`META-INF/spring.factories`**, dùng exception chuyên biệt, viết hành động khắc phục cụ thể, giữ thông tin nhạy cảm ngoài log và **kiểm chứng bằng cả unit test lẫn executable JAR thất bại/thành công**. Một thông điệp startup tốt giúp người vận hành biết **nên sửa cái gì ngay tiếp theo**, mà không che mất nguyên nhân kỹ thuật cần điều tra.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — **SpringApplication: Startup Failure**: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — **How-to: Create Your Own FailureAnalyzer**: https://docs.spring.io/spring-boot/3.3/how-to/application.html
- Spring Boot 3.3.13 — **FailureAnalyzer API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html
- Spring Boot 3.3.13 — **AbstractFailureAnalyzer API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/AbstractFailureAnalyzer.html
- Spring Boot 3.3.13 — **FailureAnalysis API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html
- Spring Boot 3.3.13 — **FailureAnalysisReporter API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysisReporter.html
- Spring Boot 3.3.13 — **LoggingFailureAnalysisReporter API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/LoggingFailureAnalysisReporter.html
- Spring Boot 3.3 — **Gradle Plugin Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
