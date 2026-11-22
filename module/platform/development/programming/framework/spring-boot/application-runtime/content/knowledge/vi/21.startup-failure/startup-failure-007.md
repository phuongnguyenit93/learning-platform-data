# Viết AbstractFailureAnalyzer và đăng ký qua META-INF/spring.factories trong Spring Boot

## 1. Mục tiêu: biến lỗi startup khó đọc thành hướng xử lý rõ ràng

Khi khởi động ứng dụng Spring Boot, một exception có thể bị bao nhiều lớp:

```text
SpringApplication.run(...)
  -> ApplicationContext.refresh()
     -> BeanCreationException
        -> BeanInstantiationException
           -> MissingWarehouseEndpointException
              "Required property warehouse.endpoint is missing"
```

Người mới vận hành đôi khi chỉ thấy một stack trace dài, không biết **thiếu property nào, phải cấu hình ở đâu và phải làm gì tiếp theo**. Spring Boot cung cấp **`FailureAnalyzer`** để dịch một **kiểu lỗi khởi động đã được nhận diện** thành một `FailureAnalysis` có:

- **Description:** giải thích ngắn gọn điều kiện gây lỗi, bằng ngôn ngữ dành cho người vận hành.
- **Action:** gợi ý thao tác sửa cụ thể, có thể làm được ngay.
- **Cause:** exception liên quan, dùng để giữ thông tin kỹ thuật và phục vụ chẩn đoán.

Một banner quen thuộc khi startup thất bại:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

A required configuration property for WarehouseGateway is missing:
warehouse.endpoint

Action:

Configure warehouse.endpoint in application.properties or supply
--warehouse.endpoint=https://example.invalid/api
```

Đây là **đoạn mô phỏng thông điệp mong đợi**. Cách xuống dòng, mức log, màu ANSI và những dòng xung quanh có thể khác theo phiên bản, logger và môi trường chạy. Nội dung do analyzer cung cấp sẽ thể hiện trong khu vực Description/Action khi reporter tương ứng xử lý lỗi.

**Chủ đề trực tiếp của bài:** tạo một class kế thừa `AbstractFailureAnalyzer<T>`, triển khai đúng phương thức `analyze(Throwable rootFailure, T cause)`, rồi khai báo tên class đầy đủ trong `src/main/resources/META-INF/spring.factories` bằng khóa **`org.springframework.boot.diagnostics.FailureAnalyzer`**.

Không cần tạo controller, không cần thêm một endpoint REST và **không cần `@Component` cho analyzer**. Đây là cơ chế chẩn đoán **bootstrap/startup**, được Spring Boot phát hiện bằng factory registration.

## 2. FailureAnalyzer đứng ở đâu trong vòng đời khởi động?

Luồng xử lý điển hình khi startup thất bại:

```text
JVM gọi main(String[] args)
           |
           v
SpringApplication.run(args)
           |
Chuẩn bị Environment, tạo ApplicationContext
           |
Load cấu hình / đăng ký bean definitions
           |
refresh() -> tạo bean hoặc chạy initialization
           |
      Exception xảy ra
           |
           v
Spring Boot xử lý startup failure
           |
Tìm các FailureAnalyzer đã đăng ký từ
META-INF/spring.factories
           |
  +--------+----------------------------+
  |                                     |
  v                                     v
Analyzer nhận diện lỗi                Không nhận diện
  |                                     |
  v                                     v
Trả FailureAnalysis                Trả null
  |                                     |
  +--------> Một analyzer phù hợp có kết quả
                      |
                      v
     FailureAnalysisReporter hiển thị
        Description / Action
                      |
                      v
     Startup thất bại, context được cleanup
     theo cơ chế lỗi khởi động của Boot
```

Sơ đồ được rút gọn để học. Boot có nhiều `FailureAnalyzer` tích hợp, quá trình báo lỗi còn liên quan logging, exception reporters và cleanup của context. **Analyzer không phải một cơ chế “bắt hết mọi lỗi rồi cho ứng dụng tiếp tục chạy”**. Nó được gọi trong quá trình **xử lý một startup failure đã xảy ra**.

### Những điều cần phân biệt

1. `FailureAnalyzer` tạo **thông tin chẩn đoán**, không tự sửa property hoặc tự tạo bean bị thiếu.
2. `FailureAnalysisReporter` chịu trách nhiệm **báo cáo kết quả phân tích**; mặc định Boot có reporter ghi log.
3. `AbstractFailureAnalyzer<T>` là **base class tiện ích** cho analyzer muốn nhận diện một kiểu `Throwable` cụ thể trong chuỗi cause.
4. `ApplicationFailedEvent` là sự kiện liên quan tới lần khởi động thất bại. Listener sự kiện có mục đích khác với việc xây Description/Action.
5. `@ControllerAdvice` / `@ExceptionHandler` áp dụng cho xử lý exception trong luồng ứng dụng Web sau khi đã chạy, **không phải cách chính để giải thích BeanCreationException lúc startup**.
6. `try/catch` ngoài `SpringApplication.run` có thể xử lý/lưu thông tin riêng nhưng không thay thế cơ chế registry `FailureAnalyzer` của Boot.

Điều quan trọng nhất là **khởi động vẫn thất bại** sau khi analyzer báo lỗi. Nếu thiếu cấu hình bắt buộc, việc in một thông điệp đẹp không làm ứng dụng sẵn sàng phục vụ traffic.

## 3. Ba khái niệm API: FailureAnalyzer, AbstractFailureAnalyzer và FailureAnalysis

### 3.1. FailureAnalyzer là một interface

Chữ ký cốt lõi:

```java
package org.springframework.boot.diagnostics;

// Sơ đồ API rút gọn để giải thích, không khai báo lại trong project:
@FunctionalInterface
public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
```

Một analyzer có thể trả:

- **`new FailureAnalysis(description, action, cause)`** khi đủ thông tin để giải thích chính xác.
- **`null`** khi không thể phân tích hoặc không áp dụng cho exception đó. Spring Boot có thể thử analyzer khác.

Không nên tạo một `FailureAnalysis` chung chung cho mọi exception. Nếu bạn bắt nhầm lỗi, message nghiệp vụ có thể che chẩn đoán chính xác hơn của Spring Boot.

### 3.2. AbstractFailureAnalyzer<T extends Throwable> giúp lọc theo kiểu lỗi

Thay vì tự duyệt `Throwable.getCause()` nhiều lần, có thể kế thừa:

```java
public final class MyFailureAnalyzer
        extends AbstractFailureAnalyzer<MyDomainException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, MyDomainException cause) {
        // Tạo Description, Action, Cause thích hợp.
    }
}
```

Đây là **khung minh họa**, chưa có class `MyDomainException` hoặc imports.

Chữ ký **phải đúng**:

```java
protected FailureAnalysis analyze(Throwable rootFailure, T cause)
```

`rootFailure` là throwable ban đầu được đưa tới analyzer (thường là exception lớn trong quá trình bootstrap). `cause` là throwable **đúng kiểu generic T** mà base class tìm thấy trong chuỗi nguyên nhân. Nếu một `BeanCreationException` chứa một `MissingWarehouseEndpointException` ở dưới, bạn nhận được `cause` đã được bóc đúng kiểu.

Base class chịu trách nhiệm gọi phương thức này **khi tìm được kiểu exception phù hợp**. Bạn không override `analyze(Throwable failure)` của interface chỉ để làm lại quá trình duyệt cause nếu không cần.

### 3.3. FailureAnalysis là dữ liệu báo cáo

Constructor của Spring Boot 3.3:

```java
new FailureAnalysis(
        "Mo ta nguyen nhan startup fail",
        "Hanh dong nguoi van hanh can lam",
        cause
);
```

Đây là đoạn sử dụng API, cần import `org.springframework.boot.diagnostics.FailureAnalysis` và biến `cause` thực tế.

| Tham số | Ý nghĩa | Lưu ý |
|---|---|---|
| `description` | Điều gì sai, ở thành phần nào | Nêu đúng key/resource, tránh mô tả mơ hồ |
| `action` | Các bước sửa cụ thể | Nêu tên property, file/CLI, điều kiện hợp lệ |
| `cause` | Exception gốc liên quan | Giữ được đường truy nguyên, không tạo exception giả |
| Giá trị trả về `null` | Analyzer từ chối xử lý | Cho analyzer khác cơ hội phân tích |

Đừng chỉ trả `new FailureAnalysis(cause.toString(), "Contact admin", cause)` nếu bạn có thể nói **property nào đang thiếu** và **cách truyền giá trị**. Giá trị học tập của analyzer nằm ở việc biến một lỗi phức tạp thành một hành động rõ ràng, không phải sao chép nguyên stack trace.

## 4. Tại sao nên tạo exception nghiệp vụ riêng?

Có hai lựa chọn:

**Lựa chọn A — bắt một exception từ framework**, ví dụ `BeanCreationException` hoặc `IllegalArgumentException`. Cách này tiện khi có một lỗi rất đặc thù, nhưng dễ bắt quá rộng: ứng dụng có thể có hàng chục lỗi `IllegalArgumentException` khác nhau.

**Lựa chọn B — tạo exception chuyên biệt**, ví dụ `MissingWarehouseEndpointException`. Đây là cách bài thực hành sử dụng.

```java
public final class MissingWarehouseEndpointException
        extends RuntimeException {

    private final String propertyName;

    public MissingWarehouseEndpointException(String propertyName) {
        super("Required property is missing: " + propertyName);
        this.propertyName = propertyName;
    }

    public String getPropertyName() {
        return propertyName;
    }
}
```

Đoạn trên là nội dung của **một class Java**; trong project có package và đường dẫn file riêng ở phần 7.

Khi một bean cần property bắt buộc, nó ném exception chuyên biệt. Spring có thể bọc nó trong `BeanInstantiationException` hoặc `BeanCreationException`, nhưng `AbstractFailureAnalyzer<MissingWarehouseEndpointException>` có thể tìm thấy đối tượng đúng kiểu trong chuỗi cause.

**Lợi ích:**

- Analyzer chỉ xử lý trường hợp nó hiểu rõ.
- Description/Action có thể nhận tên property được lưu trong exception, không phải parse text của stack trace.
- Có thể unit test analyzer mà không cần khởi động Spring context.
- Không đè lên thông báo từ các analyzer có sẵn của Boot khi lỗi không liên quan.
- Có đường mở rộng cho nhiều thuộc tính/tình huống cùng loại nếu contract được thiết kế tường minh.

Không đưa mật khẩu hoặc access token vào message/field của exception. Nếu exception chứa giá trị bí mật, reporter hoặc stack trace khác có thể làm lộ nó.

## 5. Quy tắc đăng ký qua spring.factories

### 5.1. Đúng vị trí file

Đặt file trong **runtime classpath**:

```text
src/main/resources/META-INF/spring.factories
```

Không nhầm với:

```text
src/main/java/META-INF/spring.factories
src/test/resources/META-INF/spring.factories
application.properties
spring.properties
```

`src/test/resources` có thể chỉ phục vụ test runtime; nếu muốn analyzer hoạt động khi chạy JAR thật, cần đặt registration vào **main resources** hoặc trong một dependency JAR có resource tương ứng.

Khi Gradle build, file resources được đưa vào classpath; khi đóng Spring Boot fat JAR, trong JAR chính có thể thấy entry:

```text
BOOT-INF/classes/META-INF/spring.factories
```

### 5.2. Đúng key và tên class

Một dòng hợp lệ:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

**Bên trái** là tên đầy đủ của interface extension point, cố định theo Spring Boot; **bên phải** là tên class fully qualified của implementation trong ví dụ.

Cách viết nhiều analyzer:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.first.FirstFailureAnalyzer,\
com.example.second.SecondFailureAnalyzer
```

Dấu `\` cuối dòng trong Java properties cho phép nối dòng; dấu phẩy phân cách nhiều implementation. **Trong project đầy đủ ở phần 7**, ta chỉ đăng ký một analyzer trên **một dòng**, tránh vấn đề line continuation và sai whitespace.

**Không viết**:

```properties
# Sai: key không phải tên interface chuẩn của Boot
FailureAnalyzer=com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

**Không dùng**:

```properties
# Sai cho mục đích này: là tên extension point auto-configuration
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

### 5.3. spring.factories khác cơ chế import auto-configuration

Spring Boot 3.x dùng đường đăng ký auto-configuration thông qua:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nhưng **điều đó không thay thế đăng ký `FailureAnalyzer`**. Với custom failure analyzer trong Spring Boot 3.3, tiếp tục dùng:

```text
META-INF/spring.factories
org.springframework.boot.diagnostics.FailureAnalyzer=...
```

Chuyển file custom analyzer sang `AutoConfiguration.imports` có thể làm bạn không được gọi trong giai đoạn failure analysis. Đây là hai nhóm extension points khác nhau: Boot auto-configuration thông thường được import vào bean context, còn failure analyzer được nạp để **chẩn đoán lỗi khi context có thể chưa được khởi tạo thành công**.

### 5.4. Có cần @Component hoặc @Bean trên analyzer không?

**Không.** Một analyzer được khai báo trong `spring.factories` có thể được khởi tạo bằng cơ chế factory loading của Spring Boot mà không cần Spring component scan.

`@Component` trên class analyzer **không phải cách đăng ký thay thế đáng tin** cho giai đoạn này; khi context không refresh thành công, việc tạo bean thông thường có thể chưa hoàn tất. Trong ví dụ, analyzer **không có `@Component`** và **không có phương thức `@Bean`**.

Analyzer cần là implementation có thể được loader khởi tạo. Cách đơn giản nhất là **public concrete class có public no-argument constructor**. Nếu không khai báo constructor nào, một public class Java có constructor mặc định với visibility của class; trong demo ta viết constructor tường minh hoặc để public class bình thường không định nghĩa constructor.

## 6. Hai kiểu lỗi nên và không nên xử lý

### 6.1. Lỗi có tính chẩn đoán cao

Ví dụ:

- Tên property bắt buộc `warehouse.endpoint` chưa có.
- Hai cờ nghiệp vụ xung đột nhau và có thể đề xuất bỏ một cờ.
- Một file schema nội bộ có phiên bản không được hỗ trợ, có action nâng cấp cụ thể.
- Một loại custom startup validation exception có field mô tả điều kiện bị vi phạm.
- Cấu hình URL của dịch vụ nội bộ không hợp lệ theo hợp đồng đã công bố.

Đặc điểm chung: **analyzer có thông tin đủ cụ thể** để viết action không gây hiểu lầm.

### 6.2. Lỗi không nên bắt quá rộng

Không viết một analyzer như sau:

```java
public final class CatchEverythingAnalyzer
        extends AbstractFailureAnalyzer<RuntimeException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, RuntimeException cause) {
        return new FailureAnalysis(
                "Application failed due to a runtime exception.",
                "Check configuration.",
                cause);
    }
}
```

Đây là **mã anti-pattern minh họa**. Vì `RuntimeException` bao trùm rất nhiều lỗi, analyzer có thể nhận các exception không thuộc phạm vi bạn hiểu, che bản phân tích sẵn có của Boot. Thay bằng một exception chuyên biệt và chỉ trả `FailureAnalysis` khi có action đáng tin.

Một analyzer chuyên biệt vẫn có thể trả `null` nếu chính kiểu lỗi đó có những trường hợp không đủ dữ liệu, ví dụ property name rỗng hoặc thông tin nguyên nhân bị thiếu. Điều này cho analyzer khác cơ hội xử lý.

## 7. Project chạy được: Spring Boot 3.3.5, Java 17 và Gradle

Dự án này sử dụng tên package:

```text
com.example.failureanalysis
```

Kịch bản khởi động:

- Nếu **thiếu** `warehouse.endpoint`, Spring tạo bean `WarehouseGateway` không thành công, ném `MissingWarehouseEndpointException`; Boot nạp custom analyzer và in Description/Action.
- Nếu cung cấp `warehouse.endpoint`, bean được tạo bình thường, `ApplicationRunner` in một dòng minh chứng ứng dụng qua giai đoạn khởi động.
- Không gọi URL thật. Ví dụ chỉ **lưu và hiển thị giá trị cấu hình**, tránh phụ thuộc mạng.

### 7.1. Cấu trúc thư mục

```text
failure-analyzer-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/failureanalysis/
    │   │   ├── FailureAnalyzerDemoApplication.java
    │   │   ├── MissingWarehouseEndpointException.java
    │   │   └── MissingWarehouseEndpointFailureAnalyzer.java
    │   └── resources/
    │       ├── application.properties
    │       └── META-INF/
    │           └── spring.factories
    └── test/
        └── java/com/example/failureanalysis/
            └── MissingWarehouseEndpointFailureAnalyzerTest.java
```

Các class/package/đường dẫn trong ví dụ phải **khớp tuyệt đối**. Nếu bạn đổi package, phải sửa cả `spring.factories` và package trong source files.

### 7.2. settings.gradle

**`settings.gradle`**:

```groovy
rootProject.name = 'failure-analyzer-demo'
```

### 7.3. build.gradle

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3 dùng Java 17+. `spring-boot-starter` là đủ cho demo non-web này. `spring-boot-starter-test` chứa JUnit Jupiter và công cụ test cần thiết. Nếu project chưa có Gradle Wrapper, cần tạo bằng Gradle tương thích hoặc lấy skeleton từ Spring Initializr trước khi chạy `./gradlew`; file `build.gradle` tự nó không tạo Wrapper.

### 7.4. application.properties

**`src/main/resources/application.properties`**:

```properties
spring.application.name=failure-analyzer-demo

# Cố ý KHÔNG đặt warehouse.endpoint ở đây để thử startup failure.
```

Đừng tự động thêm endpoint vào file lúc mới bắt đầu, vì như vậy bạn sẽ không thấy nhánh lỗi. Ở phần chạy thành công sẽ truyền property qua dòng lệnh.

### 7.5. Exception nghiệp vụ

**`src/main/java/com/example/failureanalysis/MissingWarehouseEndpointException.java`**:

```java
package com.example.failureanalysis;

public final class MissingWarehouseEndpointException
        extends RuntimeException {

    private final String propertyName;

    public MissingWarehouseEndpointException(String propertyName) {
        super("Required property is missing: " + propertyName);
        this.propertyName = propertyName;
    }

    public String getPropertyName() {
        return propertyName;
    }
}
```

Exception này có tên và field rõ nghĩa. Việc ném nó từ quá trình dựng bean sẽ làm bootstrap thất bại. Nên tránh đặt các giá trị bí mật vào message exception; ở đây chỉ dùng **tên property**.

### 7.6. Application và bean bắt buộc cấu hình

**`src/main/java/com/example/failureanalysis/FailureAnalyzerDemoApplication.java`**:

```java
package com.example.failureanalysis;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class FailureAnalyzerDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(FailureAnalyzerDemoApplication.class);

        // Demo không dùng HTTP server.
        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    WarehouseGateway warehouseGateway(Environment environment) {
        String endpoint =
                environment.getProperty("warehouse.endpoint");

        if (endpoint == null || endpoint.isBlank()) {
            throw new MissingWarehouseEndpointException(
                    "warehouse.endpoint");
        }

        return new WarehouseGateway(endpoint);
    }

    @Bean
    ApplicationRunner printConfiguredGateway(
            WarehouseGateway gateway) {
        return arguments -> System.out.println(
                "READY: warehouse.endpoint = " + gateway.endpoint());
    }

    public record WarehouseGateway(String endpoint) {
    }
}
```

**Giải thích từng đoạn:**

1. `@SpringBootApplication` tạo điểm vào cho component scan và auto-configuration trong project.
2. `WebApplicationType.NONE` giúp không cần server và không có lỗi port 8080 làm nhiễu ví dụ.
3. `@Bean WarehouseGateway` buộc Spring tạo một singleton trong quá trình refresh context mặc định (không bật global lazy).
4. `Environment.getProperty("warehouse.endpoint")` đọc cấu hình hiệu lực. Nó có thể đến từ file, biến môi trường, Java system property hoặc option CLI theo thứ tự ưu tiên của Boot.
5. Nếu property không tồn tại hoặc rỗng, bean factory **ném custom exception**. Spring sẽ có thể bọc nó bằng một hoặc nhiều exception liên quan bean creation.
6. Nếu property có giá trị, trả một Java `record`; record chứa đúng một field endpoint dùng ở ví dụ.
7. `ApplicationRunner` được gọi **sau khi context refresh**. Nó chỉ chạy khi quá trình khởi động tới được giai đoạn runner. Trong kịch bản thiếu property, runner **không in `READY`**.
8. Ví dụ dùng URL như một chuỗi, **không tạo HTTP client** và không gửi request; một endpoint giả có thể dùng để kiểm thử.
9. Class `WarehouseGateway` đặt bên trong lớp ứng dụng để số file ít, còn exception và analyzer là hai class public ở hai file riêng.

**Ranh giới:** nếu bật `spring.main.lazy-initialization=true` và không có bean eager nào yêu cầu `WarehouseGateway` trước mốc Ready, thời điểm lỗi có thể thay đổi. Bài thực hành giữ mặc định non-lazy để bảo đảm một startup failure được quan sát.

### 7.7. AbstractFailureAnalyzer chuyên biệt

**`src/main/java/com/example/failureanalysis/MissingWarehouseEndpointFailureAnalyzer.java`**:

```java
package com.example.failureanalysis;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class MissingWarehouseEndpointFailureAnalyzer
        extends AbstractFailureAnalyzer<MissingWarehouseEndpointException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            MissingWarehouseEndpointException cause) {

        String propertyName = cause.getPropertyName();

        if (propertyName == null || propertyName.isBlank()) {
            return null;
        }

        String description =
                "A required configuration property for "
                + "WarehouseGateway is missing: " + propertyName;

        String action =
                "Configure " + propertyName
                + " in application.properties or supply "
                + "--" + propertyName
                + "=https://example.invalid/api";

        return new FailureAnalysis(description, action, cause);
    }
}
```

**Phân tích kỹ thuật:**

- Class **không có `@Component`** và **không có `@Bean`**. Nó được phát hiện qua `spring.factories`.
- `AbstractFailureAnalyzer<MissingWarehouseEndpointException>` làm rõ **loại exception cần tìm**.
- `@Override` khai báo đúng overload có **hai tham số**; nếu nhầm chữ ký, compiler sẽ báo method không override được.
- `rootFailure` là exception gốc được gửi tới analyzer. Ví dụ không cần trực tiếp in toàn bộ nó; người vận hành chỉ cần property name và action.
- `cause` chứa exception chính xác cần xử lý, có field `propertyName`.
- Nếu property name không hợp lệ, trả `null` để tránh báo một action sai. Đây là cách **không chiếm quyền** xử lý khi thông tin không đủ.
- `new FailureAnalysis(description, action, cause)` giữ một throwable liên quan làm cause.
- Không cố tự động sửa hoặc tạo property mới trong analyzer; startup đã thất bại và không nên có side effect mới.
- Không log toàn bộ `Environment` trong analyzer; cấu hình có thể chứa secrets.

### 7.8. Đăng ký ở META-INF/spring.factories

**`src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

**Đây là bước bắt buộc của bài.** Nếu thiếu file, sai đường dẫn, sai key hoặc sai tên class, Boot có thể không nạp analyzer tùy biến dù class Java đã được compile thành công.

Khi build:

```text
src/main/resources/META-INF/spring.factories
    -> build/resources/main/META-INF/spring.factories
    -> BOOT-INF/classes/META-INF/spring.factories trong bootJar
```

Kiểm tra nội dung file ở main resources, không chỉ kiểm tra tên `MissingWarehouseEndpointFailureAnalyzer` có xuất hiện trong IDE.

## 8. Chạy và kiểm chứng hai nhánh

### 8.1. Nhánh thất bại — thiếu property

Trên Linux/macOS:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu không có một nguồn cấu hình ngoài nào cung cấp `warehouse.endpoint`, Spring không thể tạo `WarehouseGateway`. Console nên có một phân tích tương tự:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

A required configuration property for WarehouseGateway is missing:
warehouse.endpoint

Action:

Configure warehouse.endpoint in application.properties or supply
--warehouse.endpoint=https://example.invalid/api
```

Lưu ý đây là **minh họa cấu trúc message**, không phải cam kết mọi dòng log có đúng cách xuống hàng này. Gradle `bootRun` có thể báo task thất bại và tiến trình Java có exit code không thành công; đó là **kết quả mong đợi cho ca kiểm thử thiếu cấu hình**, không phải analyzer đã bị lỗi.

**Không có dòng `READY: warehouse.endpoint = ...`** trong kịch bản này, vì context chưa refresh thành công để gọi runner.

### 8.2. Nhánh thành công — truyền property CLI

Linux/macOS:

```bash
./gradlew bootRun --args='--warehouse.endpoint=https://example.invalid/api'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--warehouse.endpoint=https://example.invalid/api"
```

Bỏ qua log Spring/Gradle, dòng do runner in:

```text
READY: warehouse.endpoint = https://example.invalid/api
```

Ở nhánh này:

1. Option CLI được đưa vào `Environment` theo mặc định của Spring Boot.
2. Bean factory thấy property không rỗng và tạo `WarehouseGateway`.
3. Không có exception cần custom analyzer xử lý.
4. Runner được gọi và in message thành công.
5. Vì là ứng dụng non-web không có background non-daemon worker riêng, chương trình thường kết thúc sau giai đoạn khởi động/runner.

Không dùng số dòng log, màu banner hay thời gian startup cố định làm assertion cứng.

### 8.3. Chạy JAR đóng gói

Build:

```bash
./gradlew bootJar
```

Không truyền property:

```bash
java -jar build/libs/failure-analyzer-demo-0.0.1-SNAPSHOT.jar
```

Truyền property:

```bash
java -jar build/libs/failure-analyzer-demo-0.0.1-SNAPSHOT.jar --warehouse.endpoint=https://example.invalid/api
```

Giá trị ở đây là URL thuộc `example.invalid`, dành cho tài liệu và **không được chương trình kết nối tới**. Với ứng dụng thật, đừng biến việc “property có mặt” thành bằng chứng endpoint thực sự reachable; cần thêm validation/health check phù hợp.

### 8.4. Kiểm tra resource đã được đóng gói

Sau `bootJar`:

Linux/macOS:

```bash
jar tf build/libs/failure-analyzer-demo-0.0.1-SNAPSHOT.jar | grep 'META-INF/spring.factories'
```

Windows PowerShell:

```powershell
jar tf build/libs/failure-analyzer-demo-0.0.1-SNAPSHOT.jar | Select-String 'META-INF/spring.factories'
```

Bạn cần thấy:

```text
BOOT-INF/classes/META-INF/spring.factories
```

Nếu không có entry, kiểm tra `src/main/resources`, cấu hình processResources và lệnh build. Nếu entry có nhưng analyzer vẫn không hoạt động, kiểm tra **nội dung file** và tên class chứ không chỉ đường dẫn.

## 9. Unit test cho analyzer không cần khởi động ApplicationContext

**`src/test/java/com/example/failureanalysis/MissingWarehouseEndpointFailureAnalyzerTest.java`**:

```java
package com.example.failureanalysis;

import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MissingWarehouseEndpointFailureAnalyzerTest {

    private final MissingWarehouseEndpointFailureAnalyzer analyzer =
            new MissingWarehouseEndpointFailureAnalyzer();

    @Test
    void recognizesCauseInsideWrapper() {
        MissingWarehouseEndpointException cause =
                new MissingWarehouseEndpointException(
                        "warehouse.endpoint");

        Throwable wrapped = new IllegalStateException(
                "Bean creation failed", cause);

        FailureAnalysis analysis = analyzer.analyze(wrapped);

        assertNotNull(analysis);
        assertTrue(analysis.getDescription()
                .contains("warehouse.endpoint"));
        assertTrue(analysis.getAction()
                .contains("--warehouse.endpoint="));
        assertSame(cause, analysis.getCause());
    }

    @Test
    void doesNotClaimUnrelatedFailure() {
        FailureAnalysis analysis =
                analyzer.analyze(new IllegalArgumentException(
                        "Some other startup problem"));

        assertNull(analysis);
    }

    @Test
    void missingPropertyNameDoesNotProduceMisleadingAdvice() {
        MissingWarehouseEndpointException cause =
                new MissingWarehouseEndpointException("");

        FailureAnalysis analysis = analyzer.analyze(cause);

        assertNull(analysis);
    }
}
```

Trong test đầu:

- `rootFailure` là `IllegalStateException`, không phải custom exception.
- Base class tìm đúng `MissingWarehouseEndpointException` trong cause chain.
- Test kiểm tra description và action chứa property name, và `getCause()` chính là exception đã tìm được.
- Test thứ hai xác nhận analyzer **không nhận lỗi ngoài phạm vi**.
- Test thứ ba xác nhận nhánh `return null` khi property name rỗng.

Đây là unit test **trực tiếp** cho class analyzer; nó **không kiểm chứng việc `spring.factories` được load**. Muốn xác minh wiring, phải có một test tích hợp hoặc chạy ứng dụng thật theo phần 8 để xem banner startup.

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu cấu hình project đúng, các test trên phải pass. Không nên khẳng định unit test một mình chứng minh factory registration đã hoạt động.

## 10. Kiểm tra đăng ký spring.factories trong test

Một cách kiểm tra registry nhẹ hơn việc khởi chạy toàn bộ app là dùng `SpringFactoriesLoader` của Spring Framework. Ví dụ trong một test phù hợp:

```java
List<FailureAnalyzer> analyzers =
        SpringFactoriesLoader.loadFactories(
                FailureAnalyzer.class,
                getClass().getClassLoader());

boolean found = analyzers.stream().anyMatch(
        analyzer -> analyzer instanceof
                MissingWarehouseEndpointFailureAnalyzer);

assertTrue(found);
```

Đây là **snippet tích hợp** cần imports `java.util.List`, `SpringFactoriesLoader` và `FailureAnalyzer`, đặt trong method test JUnit. Với Spring Boot 3.3/Spring Framework 6.1, `SpringFactoriesLoader.loadFactories` cho phép đọc các implementation có thể được tạo bằng constructor phù hợp.

Lưu ý: `FailureAnalyzer` do Boot nạp có thể có những constructor/phụ thuộc đặc biệt; test nạp **toàn bộ analyzer từ classpath** bằng cách này có thể không tương đương hoàn toàn với cơ chế mà `FailureAnalyzers` của Boot dùng khi truyền `BeanFactory` hoặc `Environment`. Để kiểm tra chắc chắn registration của *một analyzer cụ thể*, có thể xem resource `META-INF/spring.factories`, sử dụng helper registry đúng của phiên bản hoặc thực hiện kiểm thử startup end-to-end.

**Đừng gắn nhãn một test “integration”** nếu nó chỉ new một analyzer trong Java mà không kiểm tra factory registration.

## 11. Analyzer không có Spring bean thông thường: các hệ quả

### 11.1. Tại sao không injection bằng @Autowired như service?

Analyzer có thể cần hoạt động **khi context bị lỗi trong quá trình tạo**. Không nên mặc định `@Autowired` field/setter được xử lý như một bean thông thường. Đặc biệt, field injection kiểu:

```java
@Autowired
private Environment environment;
```

bên trong một class chỉ được `spring.factories` nạp có thể không được xử lý theo đường bean lifecycle tiêu chuẩn, khiến dependency là `null`.

Với bài này, analyzer chỉ cần field có trong exception, nên **không cần access Environment**.

Tài liệu Spring Boot nêu rằng nếu thực sự cần `BeanFactory` hoặc `Environment` trong một `FailureAnalyzer`, có thể khai báo **constructor arguments** thích hợp để cơ chế nạp analyzer của Boot cấp chúng khi khả dụng. Tuy nhiên trong startup failure rất sớm, context/Environment có thể chưa đầy đủ. Chỉ đọc tối thiểu, xử lý thiếu dependency và tránh gọi bean/service có thể chính là nguyên nhân failure.

### 11.2. Đừng dùng analyzer để sửa hệ thống

Không nên:

- Ghi lại `application.properties` khi analyzer phát hiện thiếu property.
- Tạo DB schema, gọi API bên ngoài hoặc retry network trong `analyze`.
- Khởi tạo service phụ thuộc vào context đã fail.
- Swallow exception rồi trả thành công cho process.
- In toàn bộ `Environment` hoặc secret values.

Analyzer tốt nên **nhẹ, xác định, không có side effect quan trọng**, và nêu action rõ. Đây là công cụ **giải thích vì sao boot không thành công**, không phải workflow remediation tự động.

### 11.3. Không bắt nguồn lỗi quá rộng

Nếu custom analyzer mở rộng `AbstractFailureAnalyzer<Exception>` hoặc `<RuntimeException>` mà luôn trả `FailureAnalysis`, nó có thể báo sai đối với lỗi khác.

Nên đặt một exception chuyên biệt như `MissingWarehouseEndpointException` hoặc kiểm tra đủ điều kiện trước khi trả về analysis. Khi không chắc, **`return null`**. Điều này đặc biệt quan trọng vì nhiều bean initialization failures bị bọc trong các runtime exceptions thông thường của Spring.

## 12. Phân biệt failure analyzer và các cơ chế liên quan

| Cơ chế | Chạy khi nào | Dùng cho | Không phải |
|---|---|---|---|
| `FailureAnalyzer` | Trong xử lý startup failure khi Boot xét các analyzer | Tạo Description/Action có nguyên nhân rõ | Exception handler REST |
| `AbstractFailureAnalyzer<T>` | Base class của analyzer chuyên biệt | Tìm cause theo kiểu T, giảm code lặp | Bean tự sửa cấu hình |
| `FailureAnalysisReporter` | Báo kết quả `FailureAnalysis` | In log/báo cáo theo định dạng riêng | Nơi phát hiện nguyên nhân gốc |
| `ApplicationFailedEvent` | Khi `SpringApplication` khởi động thất bại | Listener phản ứng tới thất bại startup | Tự sinh Description/Action như analyzer |
| `ApplicationRunner` | Sau context refresh, trước Ready | Tác vụ startup khi bean đã có | Phân tích lỗi trước khi context sẵn sàng |
| `@PostConstruct` | Trong init một bean | Chuẩn bị/validate trạng thái bean | Chỗ sửa tất cả startup failures |
| `@ConfigurationProperties` validation | Trong quá trình binding/validation property | Phát hiện cấu hình sai kiểu, thiếu, vi phạm ràng buộc | Tự làm custom domain analyzer nếu không có logic riêng |
| `@ExceptionHandler` / `@ControllerAdvice` | Trong xử lý request Web | Trả response khi request lỗi | Bắt BeanCreationException lúc `run` fail |
| `ConditionEvaluationReport` | Dữ liệu điều kiện auto-configuration | Chẩn đoán tại sao auto-config được chọn/bỏ qua | Luôn xác định lỗi nghiệp vụ thiếu property |

Nếu bạn chỉ cần báo một property chuẩn của Spring Boot sai kiểu, có thể analyzer tích hợp đã đủ. Custom analyzer có ích khi lỗi **có semantics nghiệp vụ riêng** và cần thông báo rõ action mà framework không thể suy đoán.

## 13. Tình huống cause được bọc nhiều lần

Một startup failure thường có chain:

```text
IllegalStateException
  -> BeanCreationException
       -> BeanInstantiationException
            -> MissingWarehouseEndpointException
```

Generic của analyzer **không bắt buộc custom exception là exception ngoài cùng**. `AbstractFailureAnalyzer<T>` dùng cause-chain lookup để tìm throwable phù hợp. Đây là lý do unit test `new IllegalStateException("...", cause)` ở phần 9 có ý nghĩa.

### Nhưng có giới hạn

- Nếu lỗi bị **nuốt** và không có exception nào lan tới startup failure handler, analyzer không được gọi.
- Nếu custom exception chỉ xuất hiện trong log nhưng **không nằm trong cause chain** của throwable được báo, `AbstractFailureAnalyzer<CustomException>` sẽ không tự tìm trong log đó.
- Nếu exception bị lưu làm **suppressed exception** nhưng không nối bằng `getCause()`, đừng mặc định base class tìm nó.
- Nếu một analyzer khác tạo `FailureAnalysis` trước và Boot quyết định dùng kết quả đó, message của custom analyzer có thể không được chọn để báo.
- Nếu lỗi xảy ra **sau startup thành công** trong một background task hoặc request, failure analyzer không phải cơ chế bắt lỗi runtime đó.

Khi cần nhận diện nhiều loại lỗi khác nhau không có quan hệ generic gọn, có thể triển khai trực tiếp `FailureAnalyzer` và tự kiểm tra `Throwable` một cách có giới hạn; không ép mọi logic vào một generic type quá rộng.

## 14. Vì sao analyzer đã compile nhưng vẫn không được gọi?

Khi thấy startup failure quen thuộc nhưng **không có custom Description/Action**, hãy kiểm tra theo thứ tự:

### 14.1. Sai đường dẫn resource

Cần:

```text
src/main/resources/META-INF/spring.factories
```

Không phải `src/main/java/META-INF`. Với fat JAR, kiểm tra `BOOT-INF/classes/META-INF/spring.factories`. Nếu dùng Gradle multi-module, file phải ở **module được đưa vào runtime classpath** của ứng dụng.

### 14.2. Sai key

`spring.factories` phải dùng:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=com.example.failureanalysis.MissingWarehouseEndpointFailureAnalyzer
```

Không rút gọn `FailureAnalyzer=...`, không thay bằng `FailureAnalysisReporter=...`, không chuyển sang `AutoConfiguration.imports`.

### 14.3. Sai package hoặc tên class

`spring.factories` dùng **fully qualified class name**. Nếu package Java là `com.example.failureanalysis` nhưng file ghi `com.example.failureAnalysis`, class loader sẽ không tìm đúng class (phân biệt hoa/thường trong tên package).

### 14.4. Analyzer không thể được khởi tạo

Class phải concrete, accessible, có constructor phù hợp và tất cả dependencies cần thiết có trên classpath. Nếu constructor đòi một service không tồn tại trong giai đoạn startup failure, analyzer có thể không được tạo.

**Cách đơn giản và đáng tin nhất cho bài đầu:** public class, không có constructor parameters, không có Spring bean dependencies.

### 14.5. Sai kiểu generic

`AbstractFailureAnalyzer<MissingWarehouseEndpointException>` chỉ kích hoạt khi cause chain có exception kiểu đó. Nếu bean ném `IllegalArgumentException` thuần và không có custom exception, method hai tham số không được gọi.

Đừng “sửa” bằng cách thay generic thành `RuntimeException` rồi trả analysis cho mọi lỗi.

### 14.6. Exception không tới startup handler

Nếu mã xử lý:

```java
try {
    validateConfig();
} catch (MissingWarehouseEndpointException ex) {
    log.warn("Invalid config; continuing", ex);
}
```

thì startup có thể tiếp tục bình thường. Không có failure để analyzer diễn giải. Đây là **pseudocode minh họa** cần các method/fields `validateConfig` và `log` thật. Khi cấu hình bắt buộc, hãy chủ động để startup fail với exception rõ ràng.

### 14.7. Lỗi phát sinh quá muộn

Nếu chỉ throw exception trong endpoint khi request đầu tiên tới, đó là **runtime failure**, không còn nằm trong chuỗi xử lý startup của `SpringApplication.run(...)`. Với requirement fail-fast, đảm bảo validation xảy ra trong giai đoạn khởi tạo cần thiết, hoặc trong runner trước Ready.

### 14.8. Analyzer trả null

Ngay cả khi cause type đúng, method của bạn có thể trả `null` khi không có đủ dữ liệu. Hãy kiểm tra điều kiện branch và unit tests. `return null` là hành vi hợp lệ, nhưng bạn cần biết tại sao nó xảy ra.

### 14.9. Reporter hoặc logging khác dự kiến

Boot có `LoggingFailureAnalysisReporter` tích hợp. Tùy log configuration, cách in hoặc nơi ghi có thể không giống stdout ở ví dụ. Kiểm tra cả stderr/log file/công cụ thu thập log. Không ghi cứng test phụ thuộc ANSI colors.

### 14.10. Một analyzer khác xử lý exception

Boot có nhiều built-in analyzers. Nếu bạn cố nhận một exception chung như `BeanCreationException`, một analyzer tích hợp có thể báo thông tin thay bạn. Dùng custom exception domain-specific và không xử lý quá rộng để giảm xung đột.

### 14.11. Resource bị đè khi đóng gói nhiều thư viện

Nhiều JAR có `META-INF/spring.factories` riêng; cơ chế loader có thể đọc nhiều resources trong classpath. Nhưng nếu quá trình build tạo một **shaded/uber JAR không theo chuẩn Boot** và merge resources sai, một `spring.factories` có thể bị ghi đè. Hãy kiểm tra classpath thực tế của artifact chạy, không chỉ file gốc trong source.

### 14.12. Multi-module chọn nhầm artifact

Một module định nghĩa analyzer có thể compile và test pass, nhưng ứng dụng chạy một JAR khác không chứa module đó. Kiểm tra dependency graph của runtime và nội dung đóng gói cuối cùng.

## 15. Test registration và end-to-end startup failure

Các lớp kiểm thử nên được tách:

| Mức test | Cần làm | Chứng minh được |
|---|---|---|
| Unit test analyzer | Gọi `analyzer.analyze(exception)` | Logic phân tích, Description/Action, trả null |
| Resource test | Kiểm tra `META-INF/spring.factories` và tên class | Registration file có mặt và key đúng |
| Startup integration | Khởi chạy app thiếu property, kiểm tra banner/action và exit status | Boot phát hiện analyzer trong quá trình failure |
| Success integration | Khởi chạy có property hợp lệ, kiểm tra runner | Không bắt nhầm lỗi/không chặn startup hợp lệ |
| Packaged JAR smoke test | Chạy `java -jar` trên artifact thật | Resources/classes được đóng gói đúng |
| Negative test | Ném lỗi không liên quan, kiểm tra analyzer không chiếm quyền | Tránh báo sai với type không thuộc phạm vi |

### Quy tắc test output

**Không nên assert toàn bộ console output bằng một chuỗi dài nguyên văn** vì log có thể có timestamp, màu, banner, stack trace, Gradle task progress hoặc các thông báo từ analyzers tích hợp. Nên assert theo tiêu chí:

- Có header `APPLICATION FAILED TO START` khi reporter hiển thị analysis.
- Có `warehouse.endpoint` trong Description.
- Có `--warehouse.endpoint=` trong Action.
- Không có `READY: warehouse.endpoint` khi thiếu property.
- Process/application thực sự thất bại, không bị swallowed.
- Với property hợp lệ, có dòng `READY: warehouse.endpoint = ...` và exit bình thường.

Với unit test, kiểm tra trực tiếp getter của `FailureAnalysis` như trong phần 9 sẽ nhanh, ít fragile và không cần logging.

### Test bền vững hơn cho multi-module

Khi module analyzer là một thư viện dùng chung, nên có integration test tạo app tối giản sử dụng library đó mà **không khai báo thủ công analyzer**. Nếu khi startup failure vẫn có Description/Action riêng, bạn xác nhận `META-INF/spring.factories` của library thật sự được nạp qua classpath.

## 16. FailureAnalyzer có nên đọc Environment hoặc BeanFactory?

Một analyzer rất sớm có thể muốn biết active profile, tên application hoặc property đã cấu hình. Tuy nhiên, phải phân biệt:

- `Environment` có thể đã chuẩn bị ở các giai đoạn nhất định nhưng không phải mọi startup failure đều xảy ra sau cùng một mốc.
- `BeanFactory` có thể chưa hoàn chỉnh hoặc chính nó đang trong trạng thái lỗi.
- Gọi thêm bean/service để “lấy thông tin” có thể sinh một failure khác và che nguyên nhân gốc.

Tài liệu Boot cho phép cơ chế constructor injection đặc thù cho `FailureAnalyzer` với `BeanFactory`/`Environment` khi phù hợp. Nếu không thật sự cần, **lưu thông tin cần phân tích ngay trong custom exception** như `propertyName` ở ví dụ. Cách này giúp analyzer hoạt động ngay cả khi context không sẵn sàng cho dependency injection thông thường.

Đối với property là bí mật, chỉ lưu key name, code trạng thái hoặc mô tả đã kiểm soát trong exception; không đưa credential value vào FailureAnalysis.

## 17. Thực hành mở rộng

### Bài A — tự viết lại class analyzer

Không sao chép analyzer mẫu một cách máy móc. Viết `AbstractFailureAnalyzer<MissingWarehouseEndpointException>`, định nghĩa Description ngắn hơn 200 ký tự và Action gồm ít nhất một cách sửa qua `application.properties` hoặc CLI. Bảo đảm vẫn có `return null` khi không đủ thông tin.

### Bài B — sai tên spring.factories

Thử đổi file thành `spring-factories.properties` trong một nhánh thực hành, chạy ứng dụng thiếu config, quan sát mất custom Description/Action; sau đó khôi phục đúng `META-INF/spring.factories`.

### Bài C — sai key registry

Thử đổi `org.springframework.boot.diagnostics.FailureAnalyzer` thành `FailureAnalyzer`, build lại và chạy ca lỗi. Giải thích vì sao class vẫn compile nhưng loader không nạp qua đúng extension point.

### Bài D — sai package class

Thử sửa ký tự hoa/thường trong fully qualified class name ở `spring.factories`, quan sát dấu hiệu class-loading/registration failure rồi khôi phục. Với hệ thống production, sai registration phải được CI/test phát hiện trước release.

### Bài E — startup thành công

Chạy `--warehouse.endpoint=https://example.invalid/api`, chứng minh `WarehouseGateway` được tạo, runner in `READY`, không có FailureAnalysis custom nào phải báo.

### Bài F — trả null với lỗi không phù hợp

Trong unit test, gọi analyzer với `new IllegalArgumentException("different")`. Kỳ vọng `null`. Giải thích vì sao không nên trả một action generic cho exception không liên quan.

### Bài G — exception bị bọc hai tầng

Dùng `new IllegalStateException("outer", new RuntimeException("middle", new MissingWarehouseEndpointException("warehouse.endpoint")))`. Kiểm tra base class vẫn tìm đúng cause type, không bắt buộc exception là root.

### Bài H — dùng file thay CLI

Thêm `warehouse.endpoint=https://example.invalid/api` vào `application.properties`, chạy không có `--warehouse.endpoint`. Analyzer không có việc để làm. Sau đó xóa dòng này để khôi phục kịch bản fail.

### Bài I — thử configuration error có ý nghĩa nghiệp vụ khác

Tạo `UnsupportedWarehouseProtocolException` với field `protocol`, ném khi endpoint bắt đầu bằng giao thức không được phép, viết analyzer riêng để hướng dẫn dùng `https`. Đừng bắt mọi `IllegalArgumentException` bằng một action về endpoint.

### Bài J — đăng ký nhiều analyzer

Thêm hai analyzer chuyên biệt vào `spring.factories` với cú pháp properties và dấu phẩy. Đảm bảo chúng nhận những exception khác nhau; test không có analyzer nào nhận bừa lỗi của analyzer còn lại.

### Bài K — đóng gói thư viện analyzer

Chuyển custom exception/analyzer thành module library (giữ resource `spring.factories`), khai báo module dependency từ app. Build Boot JAR, xác nhận analysis xuất hiện khi startup fail mà không phải sao chép registration vào app.

### Bài L — giữ thông tin bảo mật

Giả định ứng dụng thiếu `warehouse.api-token`. Analyzer chỉ in **tên key** và hướng dẫn thêm qua secrets management, không log token value, không in toàn `Environment`.

### Câu hỏi tự kiểm tra

1. `FailureAnalyzer` dùng để khôi phục ứng dụng sau lỗi hay để diễn giải lỗi startup?
2. `AbstractFailureAnalyzer<T>` giúp tìm điều gì trong chuỗi cause?
3. Chữ ký phương thức bạn cần override trong subclass là gì?
4. Khi nào analyzer nên trả `null`?
5. Vì sao `@Component` không thay thế được registration qua `spring.factories`?
6. Đường dẫn resource và tên key đầy đủ để đăng ký analyzer là gì?
7. Có phải `AutoConfiguration.imports` dùng để đăng ký FailureAnalyzer trong Spring Boot 3.3 không?
8. `FailureAnalysis` chứa những phần thông tin nào?
9. Nếu exception của bạn bị bọc trong `BeanCreationException`, cách nào giúp analyzer vẫn nhận diện?
10. Có cách test nào chứng minh logic analyze đúng nhưng **chưa chứng minh** wiring factory đúng?
11. Trong demo, vì sao không có dòng READY khi thiếu endpoint?
12. Vì sao không nên in giá trị API token trong Description/Action?

## 18. Những lỗi kỹ thuật thường gặp khi viết analyzer

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| IDE compile thành công nhưng startup không hiện custom analysis | Thiếu `spring.factories` hoặc sai classpath | Kiểm tra file main resources và nội dung bootJar |
| `@Component` analyzer không chạy khi refresh fail | Analyzer không được nạp như extension bootstrap | Đăng ký bằng `org.springframework.boot.diagnostics.FailureAnalyzer` |
| Method override báo lỗi compile | Nhầm `analyze(Throwable)` với overload `analyze(Throwable,T)` | Dùng đúng protected override với hai tham số |
| Analyzer không được gọi | Cause chain không có loại exception T | Tạo exception domain-specific và bảo toàn cause khi wrap |
| Analyzer được gọi nhưng không ra banner | Method trả `null` hoặc reporter/logging khác | Test branch, xem logging/reporter |
| ClassNotFoundException khi loading factories | Sai package, tên class, thiếu dependency runtime | Đồng bộ fully qualified name và kiểm tra artifact |
| Test new analyzer pass nhưng app không nạp | Chưa kiểm tra registration | Thêm resource và startup integration test |
| Analyzer xử lý nhầm lỗi port/database | Generic quá rộng như `RuntimeException` | Thu hẹp exception type và conditions |
| Action khó hiểu | Chỉ chép lại `cause.getMessage()` | Nêu property, nơi cấu hình, bước sửa cụ thể |
| FailureAnalysis làm lộ secrets | In object config hoặc token value | Chỉ in tên khóa và thông tin an toàn |
| Analyzer tạo thêm lỗi | Gọi service/BeanFactory chưa sẵn sàng | Giữ analyzer side-effect-free |
| Đưa file vào `AutoConfiguration.imports` | Nhầm cơ chế auto-config với factory registration | Dùng `META-INF/spring.factories` |
| Startup fail nhưng analyzer không hiện | Exception bị nuốt hoặc xảy ra sau startup | Xác định đúng thời điểm và đường propagation |
| Test toàn log thất bại trên máy khác | ANSI/timestamp/Gradle khác nhau | Assert theo phần nội dung ổn định |
| Có hai analyzer cùng xử lý một exception | Phạm vi chồng lấn, thứ tự xử lý không như ý | Chọn exception chuyên biệt, phân biệt điều kiện |
| Chạy trong JAR khác | Multi-module dependency/resource không đúng | Kiểm tra runtime classpath và packaged JAR |

## 19. Checklist trước khi đưa vào project thật

- [ ] Có loại exception đủ đặc thù, chứa thông tin an toàn để chẩn đoán.
- [ ] Có class public kế thừa `AbstractFailureAnalyzer<CustomException>`.
- [ ] Override chính xác `protected FailureAnalysis analyze(Throwable rootFailure, CustomException cause)`.
- [ ] Description nêu rõ lỗi và thành phần bị ảnh hưởng.
- [ ] Action đưa ra hướng sửa khả thi, không chứa bí mật.
- [ ] Nếu không đủ thông tin, trả `null`, không báo sai.
- [ ] Không gọi service/DB/network trong analyzer.
- [ ] `META-INF/spring.factories` nằm trong main runtime resources.
- [ ] Registration key là `org.springframework.boot.diagnostics.FailureAnalyzer`.
- [ ] Tên implementation trong file là fully qualified class name chính xác.
- [ ] Analyzer có constructor phù hợp để factory loader khởi tạo.
- [ ] Đã test lỗi trực tiếp, lỗi bị wrap và lỗi không liên quan.
- [ ] Đã chạy ít nhất một startup failure thật để kiểm tra banner.
- [ ] Đã chạy startup thành công để bảo đảm không bắt nhầm.
- [ ] Đã kiểm tra packaged bootJar giữ `spring.factories`.
- [ ] Đã phân biệt FailureAnalyzer với ControllerAdvice/ExceptionHandler runtime.
- [ ] Đã kiểm tra lỗi được ném trước Ready nếu muốn startup fail-fast.
- [ ] Đã xử lý bảo mật: không đưa secrets vào logs/action.
- [ ] Đã nêu fallback cho trường hợp không phân tích được và hỗ trợ điều tra stack trace.

## 20. Tổng kết

**`AbstractFailureAnalyzer` không sửa startup failure; nó làm lỗi startup trở nên có thể hiểu và có thể hành động.** Để thêm một analyzer trong Spring Boot 3.3:

1. Xác định **loại exception cụ thể** muốn diễn giải, tốt nhất mang dữ liệu lỗi an toàn.
2. Viết một class `extends AbstractFailureAnalyzer<YourException>`.
3. Override `analyze(Throwable rootFailure, YourException cause)` để trả `FailureAnalysis(description, action, cause)`, hoặc `null` khi không đủ cơ sở.
4. Đăng ký class dưới khóa `org.springframework.boot.diagnostics.FailureAnalyzer` trong `src/main/resources/META-INF/spring.factories`.
5. Tạo startup failure thật, kiểm tra Description/Action, sau đó khởi chạy với cấu hình hợp lệ để xác nhận đường thành công.

Đây là **cơ chế extension bootstrap** độc lập với Spring MVC controller và cơ chế import auto-configuration. Bài học quan trọng không chỉ là syntax, mà còn là **chọn phạm vi lỗi đủ hẹp, báo hành động đúng và không làm phát sinh side effect mới trong lúc ứng dụng đang thất bại**.

### Tài liệu tham khảo chính thức

- Spring Boot — *Create Your Own FailureAnalyzer*: https://docs.spring.io/spring-boot/3.3/how-to/application.html
- Spring Boot 3.3 — `AbstractFailureAnalyzer` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/AbstractFailureAnalyzer.html
- Spring Boot 3.3 — `FailureAnalyzer` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html
- Spring Boot 3.3 — `FailureAnalysis` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html
- Spring Boot 3.3 — `SpringApplication` và Startup Failure: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework — `SpringFactoriesLoader` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html