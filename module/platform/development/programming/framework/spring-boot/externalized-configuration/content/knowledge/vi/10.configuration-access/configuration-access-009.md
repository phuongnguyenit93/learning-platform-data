# Thời điểm tiêm giá trị và lý do trường `static` không phù hợp trong Spring Boot

## 1. Vấn đề: cấu hình đã có, nhưng tại sao biến vẫn là `null`?

Trong ứng dụng Spring Boot, bạn có thể khai báo cấu hình như sau:

```yaml
# src/main/resources/application.yaml
demo:
  display-name: "Configuration Lab"
```

và đọc nó trong một Spring bean:

```java
@Component
public class ExampleService {

    @Value("${demo.display-name}")
    private String displayName;

    public void print() {
        System.out.println(displayName);
    }
}
```

Khi Spring quản lý và khởi tạo `ExampleService` theo cách thông thường, trường `displayName` được tiêm trước khi bean hoàn tất giai đoạn khởi tạo. Tuy nhiên, nếu bạn **đọc trường đó trong constructor** thì thường vẫn thấy `null`; còn nếu đặt annotation trên một **trường `static`**, bạn có thể thấy nó **không được tiêm** dù cấu hình hoàn toàn hợp lệ.

Đây không phải lỗi tìm file cấu hình. Nó là sự nhầm lẫn giữa:

1. **Thời điểm Spring Boot tải nguồn cấu hình** vào `Environment`.
2. **Thời điểm Spring tạo đối tượng bean và tiêm dependency** vào đối tượng.
3. **Vòng đời của một trường instance** so với **trường `static` thuộc về lớp Java**.
4. **Thời điểm mã của bạn thử đọc giá trị**.

Bài học thuộc nhóm **Truy cập cấu hình** của Spring Boot Externalized Configuration. Mục tiêu là hiểu bản chất vòng đời thay vì chỉ sửa một dòng annotation để chương trình hết báo `null`.

Sau bài này, bạn có thể:

- Mô tả chuỗi từ `application.yaml` đến `Environment`, `@Value`, `@ConfigurationProperties` và bean đang chạy.
- Phân biệt đọc trường `@Value` trong constructor với trong `@PostConstruct`, `ApplicationRunner` và phương thức nghiệp vụ.
- Dùng **constructor injection** để nhận cấu hình có sẵn ngay lúc constructor được gọi.
- Giải thích vì sao `@Value` trên trường `static` không phải một cách tiêm cấu hình được Spring hỗ trợ.
- Chọn cách truy cập cấu hình phù hợp cho `static` utility, singleton service và ứng dụng có nhiều `ApplicationContext`.
- Nhận diện nguyên nhân của giá trị `null`, lỗi placeholder, `new` thủ công và các trường hợp cấu hình không tự cập nhật khi file thay đổi.
- Viết và chạy một ứng dụng Java 21 / Spring Boot 3.3.x để quan sát thứ tự các mốc khởi tạo.

**Giới hạn:** ví dụ dùng dữ liệu giả lập không nhạy cảm. Đây là ứng dụng console, không cần database hay HTTP server.

## 2. Hai dòng thời gian cần phân biệt

### 2.1. Nguồn cấu hình được chuẩn bị ở giai đoạn sớm

Spring Boot chuẩn bị `Environment` và xử lý **Config Data** trước khi khởi tạo hầu hết các bean ứng dụng thông thường. Các nguồn cấu hình có thể bao gồm:

- `application.properties`, `application.yaml` và các file profile-specific.
- File bên ngoài JAR hoặc nguồn bổ sung qua `spring.config.import`.
- Biến môi trường của tiến trình.
- Java system properties.
- Đối số dòng lệnh.
- Các nguồn khác do ứng dụng hoặc thư viện tích hợp vào quá trình khởi động.

Các nguồn có **độ ưu tiên** khác nhau. Khi bạn yêu cầu `demo.display-name`, Spring trả giá trị có hiệu lực theo cơ chế phân giải và độ ưu tiên của các nguồn.

Điều này không có nghĩa mọi class Java đều tự nhiên đọc được giá trị đó từ một trường chưa được Spring tiêm. Dù `Environment` đã sẵn sàng, **bean instance** vẫn phải trải qua quá trình tạo và tiêm dependency.

### 2.2. Bean trải qua nhiều mốc khởi tạo

Với một Spring bean thông thường dùng field injection:

```text
Spring Boot khởi động
         |
         v
Chuẩn bị Environment, nạp Config Data
         |
         v
Tạo ApplicationContext, đăng ký bean definitions
         |
         v
Chọn bean cần khởi tạo
         |
         v
GỌI CONSTRUCTOR  --------------------+
         |                           |
         |                           +--> Trường @Value instance
         |                                chưa được field-inject
         v
Tiêm các dependency/trường @Value instance
         |
         v
Khởi tạo bean, chạy @PostConstruct
         |
         v
Bean sẵn sàng được sử dụng trong context
         |
         v
ApplicationRunner / CommandLineRunner
         |
         v
Các lời gọi nghiệp vụ sau khi ứng dụng khởi động
```

Sơ đồ là mô hình khái niệm cho các bean đơn giản. Spring còn có nhiều bước như `BeanPostProcessor`, callback `Aware`, initialization method, proxy, bean lazy và scope khác nhau. Các bước bổ sung không làm thay đổi nguyên tắc chính: **constructor chạy trước khi Spring gán các trường `@Value` của chính instance đó**.

Đối với **constructor injection**, thứ tự trong constructor lại khác:

```text
Environment đã có giá trị
          |
          v
Spring giải quyết tham số @Value hoặc dependency
          |
          v
Gọi constructor với tham số đã được chuẩn bị
          |
          v
Gán vào trường final của instance
          |
          v
@PostConstruct và các giai đoạn sử dụng bean
```

Vì vậy, nếu cần cấu hình ngay trong constructor, hãy **nhận nó qua tham số constructor**, thay vì trông chờ Spring đã gán một trường `@Value` trước khi constructor chạy.

## 3. Field injection: có giá trị sau constructor

Ví dụ:

```java
package dev.example.timing;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class FieldProbe {

    @Value("${demo.display-name:unnamed}")
    private String displayName;

    public FieldProbe() {
        System.out.println("FieldProbe constructor: " + displayName);
    }

    @PostConstruct
    void afterInjection() {
        System.out.println("FieldProbe @PostConstruct: " + displayName);
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Khi Spring tạo `FieldProbe`, thứ tự logic là:

1. Java phân bổ và khởi tạo instance.
2. Constructor chạy. Vì chưa có thao tác field injection, `displayName` vẫn là giá trị Java mặc định của `String`, thường là `null`.
3. Sau constructor, bộ xử lý injection của Spring phân giải `${demo.display-name:unnamed}` qua `Environment`, rồi gán trường instance.
4. Callback `@PostConstruct` được gọi trong quá trình khởi tạo bean; khi đó có thể đọc trường vừa được tiêm.
5. Phương thức `getDisplayName()` đọc giá trị trên bean đã được khởi tạo.

Nếu YAML chứa `demo.display-name: Configuration Lab`, hai mốc đáng quan sát là:

```text
FieldProbe constructor: null
FieldProbe @PostConstruct: Configuration Lab
```

**Không nên dùng `displayName` để thiết lập logic quan trọng ngay trong constructor của ví dụ trên**. Nếu cần nó ngay lúc tạo object, hãy dùng constructor injection.

### 3.1. `@PostConstruct` là thời điểm nào?

`@PostConstruct` là callback khởi tạo được xử lý sau khi các dependency instance thông thường đã được inject nhưng trước khi bean hoàn tất việc khởi tạo. Nó phù hợp cho logic cấu hình nhỏ cần chạy một lần sau injection.

Ví dụ:

```java
@PostConstruct
void initialize() {
    if (displayName == null || displayName.isBlank()) {
        throw new IllegalStateException("demo.display-name is blank");
    }
}
```

Tuy nhiên, việc kiểm tra cấu hình quy mô lớn nên dùng `@ConfigurationProperties` cùng validation thay vì viết hàng loạt đoạn kiểm tra thủ công trong `@PostConstruct`.

Trong Spring Boot 3.x, import `@PostConstruct` là:

```java
import jakarta.annotation.PostConstruct;
```

không phải `javax.annotation.PostConstruct` của hệ API cũ.

### 3.2. Đừng coi thứ tự `println` giữa các bean là tuyệt đối

Với nhiều bean không có dependency ràng buộc với nhau, thứ tự tạo bean cụ thể có thể khác nhau. Bạn có thể thấy log constructor của bean A xen giữa callback của bean B. Hãy kiểm tra **thứ tự các mốc của từng bean**, không dùng thứ tự toàn bộ log làm hợp đồng kiến trúc.

Nếu logic phải chạy **sau khi application context đã khởi động**, dùng `ApplicationRunner` hoặc `CommandLineRunner`. Nếu logic phải xảy ra ngay lúc tạo bean, dùng constructor hoặc callback phù hợp. Không nên thêm annotation chỉ nhằm ép thứ tự log trông đẹp hơn.

## 4. Constructor injection: cấu hình đã có ngay khi gọi constructor

Giải pháp ưu tiên khi service cần một hoặc nhiều giá trị cấu hình là truyền qua constructor:

```java
package dev.example.timing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ConstructorProbe {

    private final String displayName;

    public ConstructorProbe(
            @Value("${demo.display-name:unnamed}") String displayName) {
        this.displayName = displayName;
        System.out.println("ConstructorProbe constructor: " + displayName);
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Spring phân giải tham số `@Value` trước khi gọi constructor. Khi constructor chạy, `displayName` đã là đối số do Spring cấp.

Ưu điểm:

- Dependency được khai báo **tường minh** trong chữ ký constructor.
- Trường có thể là `final`.
- Instance luôn nhận giá trị khi được tạo đúng cách.
- Unit test có thể khởi tạo trực tiếp bằng dữ liệu rõ ràng:
  
  ```java
  ConstructorProbe probe = new ConstructorProbe("test-value");
  ```

- Không cần đợi đến `@PostConstruct` mới có thể dùng cấu hình.
- Giảm khả năng vô tình dùng một trường chưa được tiêm trong constructor.

Lưu ý khi unit test tạo bean thủ công: bạn phải **truyền giá trị thật vào constructor**. Java không tự xử lý annotation `@Value` khi gọi `new`.

### 4.1. Cách tương tự với `Environment`

Một bean cũng có thể nhận `Environment` qua constructor:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class EnvironmentProbe {

    private final Environment environment;

    public EnvironmentProbe(Environment environment) {
        this.environment = environment;

        String label = environment.getProperty(
                "demo.display-name", "unnamed");

        System.out.println("constructor via Environment: " + label);
    }

    public String currentDisplayName() {
        return environment.getProperty(
                "demo.display-name", "unnamed");
    }
}
```

`Environment` là dependency hợp lệ của Spring. Lời gọi `getProperty()` cho phép truy cập property theo tên vào thời điểm phương thức chạy. Đó là cách khác với việc lưu kết quả của `@Value` vào một trường.

Dù `Environment` có thể được hỏi lại nhiều lần, **sửa file `application.yaml` ngoài tiến trình không mặc nhiên làm Environment tải lại Config Data**. Với cấu hình thông thường, giá trị file được nạp khi khởi động; thay đổi động cần cơ chế cập nhật có chủ đích.

## 5. Vì sao trường `static` không phù hợp với `@Value`?

Hãy xét:

```java
package dev.example.timing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StaticProbe {

    @Value("${demo.display-name:unnamed}")
    private static String displayName;

    public static String currentValue() {
        return displayName;
    }
}
```

Đoạn mã trông giống cách field injection bình thường, nhưng `displayName` là **trường static**. Nó thuộc về **class `StaticProbe`**, không thuộc về từng instance bean.

Trong cơ chế injection chuẩn của Spring, `@Value` và `@Autowired` trên static field **không được xử lý như field dependency injection hợp lệ của bean instance**. Bộ xử lý injection có thể bỏ qua trường static và ghi log cảnh báo. Do đó, `StaticProbe.currentValue()` thường trả `null` nếu không có mã Java khác tự gán trường đó.

Phân biệt:

```text
Instance field:  objectA.displayName
                 objectB.displayName

Static field:    StaticProbe.displayName
                 ^ một vùng trạng thái thuộc class,
                   chia sẻ giữa các instance và context
```

Spring quản lý **bean instances**. Đối với `@Value` trên instance field, Spring có một object cụ thể để gán giá trị trong vòng đời của bean đó. Với static field, giá trị không gắn với một instance, khiến cơ chế injection theo vòng đời bean không phù hợp.

### 5.1. Tại sao việc có `@Component` vẫn không cứu được static field?

`@Component` giúp Spring phát hiện và tạo một **bean instance** thuộc class đó. Annotation này không biến các trường `static` thành instance fields.

```java
@Component
public class StaticProbe {
    @Value("${demo.display-name}")
    private static String displayName;
}
```

Spring có thể tạo `StaticProbe` thành công, nhưng điều đó **không bảo đảm** trường static được gán. Nếu mã khác tình cờ gán giá trị cho trường static, bạn còn có thể hiểu nhầm rằng annotation đã hoạt động.

### 5.2. `static` khởi tạo lúc nào?

Class Java có thể được nạp và khởi tạo theo nhu cầu của JVM, độc lập với thời điểm Spring tạo bean. Static initializer chạy trong quá trình khởi tạo class:

```java
public class StaticExample {

    static {
        System.out.println("class initialization");
    }
}
```

Bạn không thể mặc định rằng một static initializer có thể truy cập Spring application context đang sẵn sàng hoặc những property đã được phân giải cho bean. Thứ tự class loading có thể phụ thuộc lần đầu class được tham chiếu.

Một lời gọi như:

```java
String label = StaticProbe.currentValue();
```

thực hiện trên class, không tự yêu cầu Spring xây dựng bean hay giải quyết placeholder trong static field.

### 5.3. `static final` càng không phải một nguồn cấu hình runtime

Ví dụ:

```java
public static final String DISPLAY_NAME = "hard-coded";
```

Đây là giá trị cố định theo mã nguồn Java. Nếu bạn cần thay đổi theo profile hoặc biến môi trường thì một hằng số `static final` không phải lựa chọn phù hợp.

Một số người thử:

```java
@Value("${demo.display-name}")
private static final String DISPLAY_NAME = null;
```

Điều này không biến constant thành property từ Spring. Không nên dựa vào reflection hay việc sửa trường `final` để tiêm cấu hình. Nếu giá trị thuộc về runtime, nó phải được lấy thông qua một bean hoặc dependency được thiết kế cho runtime.

### 5.4. Static gây vấn đề gì ngoài chuyện không được inject?

Ngay cả khi bạn tự viết mã gán một static field từ instance callback, việc đó vẫn có rủi ro:

1. **Nhiều `ApplicationContext`:** hai context khác nhau có thể cần hai bộ cấu hình, nhưng cùng dùng chung một static field của JVM.
2. **Kiểm thử:** test chạy trước có thể để lại trạng thái cho test chạy sau.
3. **Vòng đời:** khi context đóng, trạng thái static không tự được xóa theo vòng đời bean.
4. **Khởi tạo:** code có thể đọc static trước khi bean gán giá trị.
5. **Đồng thời:** nhiều thread có thể đọc/ghi cùng static field, dẫn đến vấn đề visibility hoặc tranh chấp.
6. **Khó thay thế:** không thể dễ dàng mock hoặc cấp cấu hình riêng cho từng instance.
7. **Khó hiểu nguồn gốc:** không biết context nào và thời điểm nào đã quyết định giá trị hiện có.

Vì vậy, tránh chia sẻ **cấu hình thay đổi theo môi trường** qua biến static mutable.

## 6. Nếu một phương thức `static` thật sự cần cấu hình thì làm sao?

Một phương thức static không thể trực tiếp đọc instance field như cách phương thức instance làm. Nhưng nó có thể **nhận giá trị cần thiết làm tham số**:

```java
public final class LabelFormatter {

    private LabelFormatter() {
    }

    public static String format(String prefix, String message) {
        return prefix + ": " + message;
    }
}
```

Service có cấu hình được tiêm bình thường:

```java
import org.springframework.stereotype.Service;

@Service
public class LabelService {

    private final ConstructorProbe configuration;

    public LabelService(ConstructorProbe configuration) {
        this.configuration = configuration;
    }

    public String format(String message) {
        return LabelFormatter.format(
                configuration.getDisplayName(), message);
    }
}
```

Ưu điểm: phương thức static vẫn là một utility **không giữ trạng thái**, còn việc tìm cấu hình thuộc về Spring bean. Bạn có thể unit test formatter bằng hai tham số mà không cần tạo Spring context.

Nếu muốn utility biết cấu hình một cách tự nhiên mà không truyền nhiều tham số ở mỗi lời gọi, hãy chuyển utility thành một **bean instance**:

```java
import org.springframework.stereotype.Component;

@Component
public class MessageFormatter {

    private final String prefix;

    public MessageFormatter(
            @Value("${demo.display-name:unnamed}") String prefix) {
        this.prefix = prefix;
    }

    public String format(String message) {
        return prefix + ": " + message;
    }
}
```

Bây giờ các bean khác nhận `MessageFormatter` qua constructor. Cách này giữ cấu hình đúng với vòng đời của application context và dễ thay thế trong test.

## 7. `@ConfigurationProperties`: lựa chọn cho một nhóm cấu hình

`@Value` thích hợp cho một hoặc một vài giá trị. Khi nhiều trường cùng thuộc một nhóm, Spring Boot khuyến nghị sử dụng `@ConfigurationProperties`.

Ví dụ:

```yaml
demo:
  display-name: "Configuration Lab"
  retry-delay: 2s
  enabled: true
```

Record Java:

```java
package dev.example.timing;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String displayName,
        Duration retryDelay,
        boolean enabled
) {}
```

Bật quét cấu hình:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class InjectionTimingApplication {
    public static void main(String[] args) {
        SpringApplication.run(InjectionTimingApplication.class, args);
    }
}
```

Một service nhận cả record:

```java
import org.springframework.stereotype.Service;

@Service
public class DemoService {

    private final DemoProperties settings;

    public DemoService(DemoProperties settings) {
        this.settings = settings;
    }

    public String describe() {
        return settings.displayName()
                + " / delay=" + settings.retryDelay()
                + " / enabled=" + settings.enabled();
    }
}
```

Lợi ích:

- Nhóm các property liên quan thành một **hợp đồng có kiểu**.
- Cấu hình có thể chuyển đổi thành `Duration`, số, boolean, URI và nhiều kiểu khác.
- Phần lớn các bean không cần biết tên property dạng chuỗi.
- Hợp với validation cấu hình và IDE metadata khi bổ sung cấu hình build phù hợp.
- Không cần dùng static field để “truy cập ở mọi nơi”: nhiều service có thể nhận cùng bean cấu hình do Spring quản lý.

Record `DemoProperties` là một instance bean. Nó **không phải static global object** dù nó có thể được inject vào nhiều service trong cùng context.

### 7.1. `@ConfigurationProperties` khác `@Value` ở thời điểm nào?

Với cả hai cách, các giá trị được cung cấp cho bean **trong quá trình Spring khởi tạo và cấu hình bean**, không phải chỉ vì JVM đã nạp class.

- Tham số constructor có `@Value` được giải quyết trước khi gọi constructor.
- Field instance có `@Value` được gán sau constructor.
- Bean `@ConfigurationProperties` được tạo và binding theo cơ chế configuration properties của Spring Boot; các bean tiêu thụ nhận nó qua constructor sau khi dependency được chuẩn bị.

Điểm quan trọng là **cách khai báo dependency**, không phải việc chuyển từ `@Value` sang `@ConfigurationProperties` sẽ cho phép tiêm vào static field.

## 8. Ứng dụng thực hành: Injection Timing Observer

Ta dựng một project có thể chạy để so sánh bốn cách tiếp cận:

1. Field injection trên instance.
2. Constructor injection.
3. `@Value` đặt nhầm trên static field.
4. Typed binding bằng `@ConfigurationProperties`.

Chương trình in thông tin vào console và kết thúc. Không cần tạo HTTP endpoint, vì vậy không có rủi ro vô tình đưa giá trị cấu hình lên một API công khai.

### 8.1. Cấu trúc project

```text
injection-timing/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/timing/
    │   │   ├── InjectionTimingApplication.java
    │   │   ├── DemoProperties.java
    │   │   ├── FieldProbe.java
    │   │   ├── ConstructorProbe.java
    │   │   ├── StaticProbe.java
    │   │   └── ReportRunner.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/timing/
            └── InjectionTimingTest.java
```

Tạo bộ khung bằng Spring Initializr với Java 21, Gradle và một bản Spring Boot 3.3.x. Các file `gradlew` và `gradlew.bat` do Gradle Wrapper sinh ra, không cần chép tay nội dung của chúng.

`settings.gradle`:

```groovy
rootProject.name = 'injection-timing'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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

Nếu ứng dụng đang ở trong repository có convention plugin hoặc version catalog, sử dụng hệ thống quản lý phụ thuộc của repository. Bản mẫu này dùng dependency tối thiểu cho ứng dụng console.

### 8.2. File cấu hình nền

`src/main/resources/application.yaml`:

```yaml
spring:
  main:
    web-application-type: none

demo:
  display-name: "from-application-yaml"
  retry-delay: 2s
  enabled: true
```

Đặt `web-application-type: none` để sau khi runner hoàn thành, ứng dụng không giữ một web server sống trong nền.

File `src/main/resources/application-dev.yaml`:

```yaml
demo:
  display-name: "from-dev-profile"
  retry-delay: 500ms
```

Để ý file `dev` không cần khai báo lại `demo.enabled`. Nếu profile `dev` được kích hoạt, các giá trị từ cấu hình nền và file theo profile được kết hợp; `demo.enabled` vẫn có thể đến từ file nền.

### 8.3. Main class

`src/main/java/dev/example/timing/InjectionTimingApplication.java`:

```java
package dev.example.timing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class InjectionTimingApplication {

    public static void main(String[] args) {
        SpringApplication.run(InjectionTimingApplication.class, args);
    }
}
```

### 8.4. Record binding có kiểu

`src/main/java/dev/example/timing/DemoProperties.java`:

```java
package dev.example.timing;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String displayName,
        Duration retryDelay,
        boolean enabled
) {}
```

Trong YAML, tên property canonical là `display-name`, `retry-delay`, còn trong Java chúng được binding vào record components dạng camelCase.

### 8.5. FieldProbe: constructor và `@PostConstruct`

`src/main/java/dev/example/timing/FieldProbe.java`:

```java
package dev.example.timing;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class FieldProbe {

    @Value("${demo.display-name:unnamed}")
    private String displayName;

    public FieldProbe() {
        System.out.println("FIELD constructor = "
                + show(displayName));
    }

    @PostConstruct
    void afterInjection() {
        System.out.println("FIELD @PostConstruct = "
                + show(displayName));
    }

    public String displayName() {
        return displayName;
    }

    private static String show(String value) {
        return value == null ? "<null>" : value;
    }
}
```

Đây là nơi bạn nhìn thấy hai giai đoạn của **cùng một bean instance**: trước field injection và sau field injection.

### 8.6. ConstructorProbe: có giá trị khi tạo instance

`src/main/java/dev/example/timing/ConstructorProbe.java`:

```java
package dev.example.timing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ConstructorProbe {

    private final String displayName;

    public ConstructorProbe(
            @Value("${demo.display-name:unnamed}") String displayName) {
        this.displayName = displayName;
        System.out.println("CTOR constructor = " + displayName);
    }

    public String displayName() {
        return displayName;
    }
}
```

Spring giải quyết tham số rồi mới gọi constructor. Trường instance `final` được gán đúng lúc tạo object, thay vì đợi Spring inject một trường sau đó.

### 8.7. StaticProbe: ví dụ cố tình đặt sai annotation

`src/main/java/dev/example/timing/StaticProbe.java`:

```java
package dev.example.timing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StaticProbe {

    @Value("${demo.display-name:unnamed}")
    private static String displayName;

    public static String displayName() {
        return displayName;
    }
}
```

Đây là **ví dụ phản diện** để quan sát: annotation `@Value` không được tiêm vào static field bằng quy trình standard bean injection. Không dùng mẫu này trong code production.

### 8.8. ReportRunner: đọc các bean sau khởi tạo

`src/main/java/dev/example/timing/ReportRunner.java`:

```java
package dev.example.timing;

import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ReportRunner implements ApplicationRunner {

    private final Environment environment;
    private final FieldProbe fieldProbe;
    private final ConstructorProbe constructorProbe;
    private final DemoProperties demo;

    public ReportRunner(
            Environment environment,
            FieldProbe fieldProbe,
            ConstructorProbe constructorProbe,
            DemoProperties demo) {
        this.environment = environment;
        this.fieldProbe = fieldProbe;
        this.constructorProbe = constructorProbe;
        this.demo = demo;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println("=== INJECTION TIMING REPORT ===");
        System.out.println("activeProfiles = "
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("Environment demo.display-name = "
                + environment.getProperty("demo.display-name"));
        System.out.println("fieldProbe.displayName = "
                + fieldProbe.displayName());
        System.out.println("constructorProbe.displayName = "
                + constructorProbe.displayName());
        System.out.println("DemoProperties.displayName = "
                + demo.displayName());
        System.out.println("DemoProperties.retryDelay = "
                + demo.retryDelay());
        System.out.println("DemoProperties.enabled = "
                + demo.enabled());
        System.out.println("StaticProbe.displayName = "
                + (StaticProbe.displayName() == null
                        ? "<null>" : StaticProbe.displayName()));
    }
}
```

`ApplicationRunner.run` được gọi sau khi application context đã được khởi động. Trong bài lab, các bean cần dùng đã được chuẩn bị và tiêm trước khi runner in báo cáo.

Phần `StaticProbe` được gọi qua tên class để nhấn mạnh đây là static method. Việc gọi method này **không** yêu cầu Spring phải tiêm giá trị cho static field.

## 9. Chạy thử lần 1: dùng giá trị từ `application.yaml`

Từ thư mục gốc project:

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Những dòng quan trọng cần xuất hiện, không bắt buộc theo thứ tự tuyệt đối giữa các bean khác nhau:

```text
FIELD constructor = <null>
FIELD @PostConstruct = from-application-yaml
CTOR constructor = from-application-yaml
=== INJECTION TIMING REPORT ===
activeProfiles = []
Environment demo.display-name = from-application-yaml
fieldProbe.displayName = from-application-yaml
constructorProbe.displayName = from-application-yaml
DemoProperties.displayName = from-application-yaml
DemoProperties.retryDelay = PT2S
DemoProperties.enabled = true
StaticProbe.displayName = <null>
```

`PT2S` là cách Java `Duration` biểu diễn khoảng thời gian 2 giây. Một số dòng Spring có thể hiển thị cảnh báo về annotation trên static field. Đó là một tín hiệu bổ sung, nhưng điều cần quan sát là **field instance có giá trị sau injection; trường static không tự có giá trị**.

### 9.1. Điều gì xảy ra nếu không có `demo.display-name`?

Trong ví dụ, các trường `@Value` có fallback:

```java
@Value("${demo.display-name:unnamed}")
```

Nếu property không được giải quyết từ các nguồn có hiệu lực, Spring sử dụng chuỗi `unnamed` cho các điểm injection đó. Tuy nhiên, record `DemoProperties` không tự nhận fallback của `@Value`; nó được binding theo cấu hình mà binder nhìn thấy. Do đó có thể có sự khác biệt giữa field/constructor và record nếu bạn xóa thuộc tính mà không bổ sung default/validation riêng cho `@ConfigurationProperties`.

Đây không phải lỗi timing mà là **hai cơ chế khai báo default khác nhau**. Khi bài thực hành yêu cầu so sánh timing, giữ property có mặt để không trộn vấn đề fallback vào cùng một phép thử.

## 10. Chạy thử lần 2: profile `dev`

File `application-dev.yaml` chỉ được nạp theo profile khi `dev` hoạt động. Chạy:

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Giá trị mong đợi:

```text
FIELD constructor = <null>
FIELD @PostConstruct = from-dev-profile
CTOR constructor = from-dev-profile
activeProfiles = [dev]
Environment demo.display-name = from-dev-profile
fieldProbe.displayName = from-dev-profile
constructorProbe.displayName = from-dev-profile
DemoProperties.displayName = from-dev-profile
DemoProperties.retryDelay = PT0.5S
DemoProperties.enabled = true
StaticProbe.displayName = <null>
```

Các nguồn đã đổi giá trị hiệu lực, nhưng **thứ tự field injection không đổi**. Constructor của `FieldProbe` vẫn chạy trước khi trường instance được tiêm; constructor của `ConstructorProbe` vẫn nhận giá trị qua tham số; static field vẫn không được tiêm.

Điểm cần rút ra: profile quyết định **giá trị** nào được chọn, không biến annotation `@Value` trên static field thành hợp lệ.

## 11. Chạy thử lần 3: đối số CLI ghi đè

Thử:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --demo.display-name=from-cli'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev --demo.display-name=from-cli"
```

Kỳ vọng:

```text
FIELD constructor = <null>
FIELD @PostConstruct = from-cli
CTOR constructor = from-cli
Environment demo.display-name = from-cli
DemoProperties.displayName = from-cli
StaticProbe.displayName = <null>
```

Trong trường hợp thông thường, đối số CLI có độ ưu tiên cao hơn file Config Data. Một lần nữa, giá trị thay đổi theo nguồn cấu hình, nhưng timing và khả năng tiêm vào static không thay đổi.

Bạn cũng có thể build JAR:

macOS/Linux:

```bash
./gradlew bootJar
java -jar build/libs/injection-timing-0.0.1-SNAPSHOT.jar \
  --demo.display-name=from-jar-cli
```

PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build\libs\injection-timing-0.0.1-SNAPSHOT.jar --demo.display-name=from-jar-cli
```

Với cách chạy JAR, tham số sau tên JAR được chuyển vào Spring Boot. Nếu dự án đổi version hoặc tên artifact, sử dụng đường dẫn JAR thực tế trong `build/libs`.

## 12. Vì sao `new` thủ công làm `@Value` không hoạt động?

Spring chỉ tiêm dependency cho những object được xử lý bởi cơ chế quản lý bean của nó. Xét:

```java
FieldProbe manual = new FieldProbe();
System.out.println(manual.displayName());
```

Lệnh trên gọi constructor Java thông thường. Nó **không** đăng ký object thành bean hoặc chạy `BeanPostProcessor` để gán trường `@Value`. Vì vậy `manual.displayName()` có thể vẫn là `null`.

Còn khi lấy bean từ Spring:

```java
FieldProbe managed = applicationContext.getBean(FieldProbe.class);
System.out.println(managed.displayName());
```

trường instance đã được tiêm trong quá trình tạo bean.

Một tình huống phổ biến:

```java
@Service
public class OrderService {
    public void process() {
        EmailHelper helper = new EmailHelper();
        helper.send();
    }
}
```

Nếu `EmailHelper` trông chờ field injection:

```java
@Component
public class EmailHelper {
    @Value("${mail.from-address}")
    private String fromAddress;
}
```

thì `new EmailHelper()` tạo ra một object ngoài Spring; annotation trên class không khiến instance đó tự được tiêm.

Cách sửa: nhận `EmailHelper` qua constructor của `OrderService`, hoặc truyền các tham số cần thiết cho object được tạo thủ công. Trong thiết kế có nhiều object cần tạo động, cân nhắc dùng bean factory được quản lý hoặc tách phần logic không cần Spring ra khỏi phần lấy cấu hình.

## 13. Unit test và integration test: cách quan sát có kiểm soát

### 13.1. Unit test cho constructor injection

Vì `ConstructorProbe` nhận một chuỗi cụ thể trong constructor, bạn không cần Spring context để unit test hành vi giữ cấu hình:

```java
package dev.example.timing;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ConstructorProbeUnitTest {

    @Test
    void storesPassedConfiguration() {
        ConstructorProbe probe = new ConstructorProbe("from-test");

        assertEquals("from-test", probe.displayName());
    }
}
```

Test này kiểm tra hợp đồng của class Java. Nó **không** chứng minh Spring có thể đọc `application.yaml`, vì không chạy quá trình phân giải property của Spring.

### 13.2. Integration test cho binding trong Spring context

`src/test/java/dev/example/timing/InjectionTimingTest.java`:

```java
package dev.example.timing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.display-name=from-spring-test",
        "demo.retry-delay=3s",
        "demo.enabled=false"
})
class InjectionTimingTest {

    @Autowired
    private FieldProbe fieldProbe;

    @Autowired
    private ConstructorProbe constructorProbe;

    @Autowired
    private DemoProperties demo;

    @Test
    void injectsInstancePropertiesAndBindsConfiguration() {
        assertEquals("from-spring-test", fieldProbe.displayName());
        assertEquals("from-spring-test", constructorProbe.displayName());
        assertEquals("from-spring-test", demo.displayName());
        assertEquals(java.time.Duration.ofSeconds(3),
                demo.retryDelay());
        assertEquals(false, demo.enabled());
        assertNull(StaticProbe.displayName());
    }
}
```

Chạy:

macOS/Linux:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Spring test context đưa thuộc tính thử nghiệm vào `Environment`. Các bean instance nhận giá trị tương ứng; trường static trong ví dụ vẫn không được xử lý bằng `@Value`.

Khi chạy nhiều test trong cùng JVM, static state có thể bị ảnh hưởng nếu một phần code khác từng gán vào trường đó. Vì vậy, ví dụ test này cố ý **không có bất kỳ setter hoặc callback nào gán static**. Trong ứng dụng thực, không nên dựa vào một static property để chia sẻ trạng thái giữa các test.

### 13.3. Không lạm dụng test dựa trên thứ tự log

Kiểm thử tốt nên assert **giá trị có sẵn ở thời điểm sử dụng phù hợp**, thay vì assert thứ tự exact của các dòng `System.out`. Nếu một test thật sự cần quan sát lifecycle, hãy ghi lại sự kiện cho một bean cụ thể và kiểm tra quan hệ “constructor trước callback”, nhưng tránh ràng buộc vào thứ tự khởi tạo các bean độc lập.

## 14. Nếu rất cần cấp giá trị cho mã legacy `static`?

Đôi khi thư viện hoặc lớp cũ có API static không thể sửa ngay:

```java
LegacyGlobalClient.configure("some value");
```

Một cách cầu nối có thể là tạo **một Spring bean instance** nhận giá trị qua constructor rồi gọi API static trong một callback khởi tạo:

```java
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class LegacyClientInitializer {

    private final String endpoint;

    public LegacyClientInitializer(
            @Value("${legacy.endpoint}") String endpoint) {
        this.endpoint = endpoint;
    }

    @PostConstruct
    void configureLegacyClient() {
        LegacyGlobalClient.configure(endpoint);
    }
}
```

Điều này **không phải static injection**. Spring tiêm vào instance `LegacyClientInitializer`, sau đó bạn chủ động gọi một API static do hệ thống legacy sở hữu.

Rủi ro vẫn tồn tại:

- `LegacyGlobalClient` có thể được gọi trước callback khởi tạo.
- Hai Spring contexts có thể cấu hình cùng một global client khác nhau.
- Test chạy song song hoặc ứng dụng nhiều tenant có thể tranh chấp global state.
- Khi đóng context, ứng dụng cần xác định có phải reset trạng thái global không.
- Nếu thư viện có API tạo client instance riêng, nên chuyển sang client instance.

Vì thế, cầu nối chỉ nên là **giải pháp tạm cho hệ thống legacy có ràng buộc rõ**, không phải mẫu để làm cho `@Value` hoạt động trên static field.

### 14.1. Vì sao setter instance gán sang static không phải giải pháp bền vững?

Bạn có thể gặp đoạn mã:

```java
@Component
public class LegacyStaticHolder {

    private static String value;

    @Value("${demo.display-name}")
    public void setValue(String configured) {
        value = configured;
    }

    public static String getValue() {
        return value;
    }
}
```

Phương thức instance được Spring gọi là chỗ tiêm giá trị, còn việc gán `value` là do code của bạn làm. Điều này có thể chạy trong một ứng dụng đơn giản, nhưng không sửa được các vấn đề **vòng đời, đa context, test isolation và đồng thời** của static state.

Hãy coi nó là một workaround có giới hạn, không phải hình thức constructor/field injection được khuyến nghị.

## 15. So sánh các phương án truy cập cấu hình

| Cách dùng | Thời điểm có giá trị | Có dùng được trong constructor? | Khuyến nghị |
| --- | --- | --- | --- |
| Field instance `@Value` | Sau khi constructor được gọi, trong quá trình tiêm bean | **Không** đọc trực tiếp field trước injection | Dùng cho trường hợp đơn giản, tránh constructor phụ thuộc field |
| Constructor parameter `@Value` | Khi Spring gọi constructor | **Có**, qua tham số | Tốt cho vài khóa cấu hình |
| Bean `@ConfigurationProperties` | Được tạo và binding trong lifecycle của context | **Có**, khi inject bean vào service khác | Tốt cho nhóm khóa có kiểu |
| Inject `Environment` qua constructor | Khi Spring cung cấp dependency | **Có**, tra cứu qua `getProperty()` | Dùng khi cần truy cập có chủ đích theo tên |
| Static field `@Value` | Không có injection chuẩn | Không | **Không dùng** |
| Static utility nhận tham số | Khi caller truyền tham số | Có, do caller quyết định | Tốt cho hàm thuần không giữ trạng thái |
| Static global được gán qua callback | Tùy callback và thứ tự sử dụng | Không an toàn nếu đọc sớm | Chỉ cân nhắc cho legacy có kiểm soát |

Lưu ý: “có giá trị trong constructor” ở đây nghĩa là **Spring cung cấp dependency qua constructor**. Nó không có nghĩa một field `@Value` khác trong cùng class đã được inject trước constructor.

## 16. Những hiểu nhầm thường gặp

### 16.1. “Environment đã load rồi thì constructor phải thấy field `@Value` chứ?”

Sai. Có hai giai đoạn khác nhau. Environment có thể đã có property, nhưng field instance vẫn là giá trị Java mặc định cho tới khi bước injection chạy. Đưa property vào **tham số constructor** để sử dụng ngay.

### 16.2. “Tôi dùng `@Component`, nhưng trường static vẫn null”

`@Component` biến class thành ứng viên bean instance; nó không thay đổi quy tắc Java về static fields. Spring chuẩn không hỗ trợ field injection theo cách này. Thay bằng instance field, constructor injection hoặc `@ConfigurationProperties`.

### 16.3. “`@Autowired` trên static cũng nên hoạt động như `@Value`?”

Cả hai không phải cách được hỗ trợ để tiêm vào static fields. Đổi từ `@Value` sang `@Autowired` không giải quyết vấn đề vòng đời hoặc ownership.

### 16.4. “Tôi gọi `new` nhưng annotation trên class vẫn còn đó”

Annotation chỉ là metadata. Một object tạo bằng `new` ngoài Spring không mặc định đi qua bean lifecycle. Nếu cần Spring inject, để Spring tạo object hoặc có một quy trình quản lý rõ ràng.

### 16.5. “Thêm `@PostConstruct` vào method static là được?”

Không. Callback vòng đời theo bean instance không phải API chung để Spring gọi mọi static method đã gắn annotation. Hãy đặt callback trên một **instance bean** và để nó làm công việc cần thiết, không dùng static callback như thay thế cơ chế injection.

### 16.6. “Trường static đã được gán bởi test trước, vậy code của tôi đúng”

Có thể đây là trạng thái rò rỉ giữa test/context. Static field sống theo class trong JVM, không theo một Spring context. Test isolation là một lý do quan trọng để tránh thiết kế này.

### 16.7. “Biến `@Value` có giá trị `null` nghĩa là property source bị bỏ qua”

Có nhiều khả năng khác: object không do Spring tạo, field đang bị đọc quá sớm, annotation nằm trên static field, property thiếu mà có fallback, profile/location sai, hoặc có nguồn ưu tiên cao hơn. Chẩn đoán theo từng bước, không kết luận chỉ dựa trên một `null`.

### 16.8. “Sửa file YAML là `@Value` cập nhật ngay”

Không mặc định. Bean thường được tạo và tiêm theo snapshot cấu hình tại thời điểm khởi động. File bên ngoài không tự động refresh một field đã được gán. Các cơ chế dynamic refresh tồn tại trong một số hệ thống, nhưng phải được cấu hình và kiểm thử riêng.

### 16.9. “Ứng dụng có nhiều instance thì singleton bean cũng chính là static”

Không giống nhau. Spring singleton thông thường là một bean instance duy nhất **trong một application context**. Static field thuộc về class trong JVM, nên có thể bị dùng chung bởi nhiều context trong cùng JVM. Đây là sự khác biệt quan trọng khi chạy integration tests, các context con hoặc ứng dụng nhúng.

## 17. Quy trình xử lý lỗi `@Value` không nhận giá trị

Nếu thấy đoạn mã:

```java
@Value("${demo.display-name}")
private String displayName;
```

nhưng khi chạy lại nhận `null`, làm lần lượt:

**Bước 1 — Xác định object có phải Spring bean không.** Tìm nơi tạo object. Nếu có `new SomeService()` trong mã, instance đó không tự được Spring tiêm.

**Bước 2 — Xem field có `static` không.** Nếu có, bỏ thiết kế static field injection. Chuyển sang constructor parameter hoặc `@ConfigurationProperties` trong một bean.

**Bước 3 — Xem bạn đọc giá trị ở đâu.** Nếu trong constructor nhưng field được `@Value` trực tiếp, quá sớm. Dùng constructor injection hoặc chỉ đọc trường sau khi Spring hoàn tất injection.

**Bước 4 — Xác định property canonical.** Với `demo.display-name`, trong placeholder nên dùng đúng dạng kebab-case: `${demo.display-name}`.

**Bước 5 — Kiểm tra nguồn cấu hình thực tế.** File `application.yaml` có được đóng gói và nạp không? Profile có đang bật đúng không? Working directory có thay đổi không? Có import hoặc location bổ sung không?

**Bước 6 — Kiểm tra ưu tiên nguồn.** Biến môi trường, system property hoặc CLI có thể ghi đè file. Giá trị hiệu lực không nhất thiết đến từ nơi bạn vừa sửa.

**Bước 7 — Kiểm tra fallback hoặc lỗi chưa giải quyết placeholder.** `${demo.display-name:unnamed}` có fallback; `${demo.display-name}` có thể khiến việc tạo bean thất bại nếu không giải quyết được. Những tình huống này khác với static field không được inject.

**Bước 8 — Thử với một giá trị giả lập.** Tạm dùng `--demo.display-name=probe-value`, chạy tiến trình mới và so sánh giữa `Environment`, constructor injection và field injection sau khởi tạo.

**Bước 9 — Phân biệt lỗi lifecycle và lỗi dữ liệu.** Nếu `Environment` có `probe-value` và constructor injection đúng, nhưng static field `null`, đó là vấn đề cơ chế injection, không phải file thiếu.

**Bước 10 — Thêm test và sửa thiết kế.** Khi một service dùng config quan trọng, nhận bean cấu hình qua constructor và có integration test kiểm tra hợp đồng binding.

Không nên tạm bật các endpoint chẩn đoán công khai hoặc log toàn bộ `Environment` để xem một giá trị. Trong production, việc này có thể làm lộ secret, token hoặc credential.

## 18. Bài tập thực hành thêm

### Bài tập A — Dự đoán thứ tự mốc của một bean

Đọc code:

```java
@Component
public class OrderProbe {

    @Value("${demo.display-name}")
    private String name;

    public OrderProbe() {
        System.out.println("constructor: " + name);
    }

    @PostConstruct
    void initialized() {
        System.out.println("postConstruct: " + name);
    }
}
```

Với property tồn tại và bean do Spring tạo, dự đoán hai dòng in ra. Giải thích dựa trên **thứ tự constructor và field injection**, không dựa trên việc Spring đã đọc YAML lúc nào.

### Bài tập B — Sửa một class đang dùng static

Đầu vào:

```java
@Component
public class UrlHelper {
    @Value("${remote.base-url}")
    private static String baseUrl;

    public static String resource(String id) {
        return baseUrl + "/resources/" + id;
    }
}
```

Yêu cầu: viết lại thành một Spring bean có `final String baseUrl` được tiêm qua constructor, method `resource(String id)` là instance method, và các service khác sử dụng nó bằng constructor injection.

Gợi ý: đừng cố tạo static setter để giữ nguyên mọi lời gọi cũ nếu bạn có thể refactor sang dependency instance.

### Bài tập C — Kiểm thử giá trị theo profile

Thêm:

```yaml
# application-staging.yaml
demo:
  display-name: "from-staging"
```

Chạy cùng JAR với `--spring.profiles.active=staging`, sau đó với `--demo.display-name=forced-value`. Ghi lại ba giá trị sau:

- `Environment.getProperty("demo.display-name")`.
- `ConstructorProbe.displayName()`.
- `StaticProbe.displayName()`.

Giải thích vì sao hai giá trị đầu thay đổi cùng nguồn ưu tiên nhưng giá trị static vẫn không được inject.

### Bài tập D — So sánh `Environment` và giá trị lưu ở bean

Một service giữ:

```java
private final String initialName;
private final Environment environment;

public DemoConsumer(
        @Value("${demo.display-name}") String initialName,
        Environment environment) {
    this.initialName = initialName;
    this.environment = environment;
}
```

Hãy giải thích khác nhau giữa `initialName` và `environment.getProperty("demo.display-name")` về **thời điểm đọc**. Trong cấu hình thông thường không có refresh, cả hai thường thấy cùng giá trị khi khởi động, nhưng một hệ thống có cập nhật property sources có thể yêu cầu xem lại chiến lược refresh của các bean giữ giá trị đã inject.

### Bài tập E — Tìm thiết kế phù hợp cho utility

Có ba cách gọi formatter:

1. `static format(String message)` đọc một static field cấu hình.
2. `static format(String prefix, String message)` nhận tham số rõ ràng.
3. `formatter.format(String message)` dùng một bean cấu hình bằng constructor.

Hãy chọn phương án cho: một thư viện Java thuần không cần Spring, một Spring service dùng cùng prefix trên nhiều đường nghiệp vụ, và một lớp legacy chưa thể sửa API. Nêu lý do và rủi ro của lựa chọn.

## 19. Câu hỏi tự kiểm tra và gợi ý

**Câu 1.** Spring Boot tải `application.yaml` trước khi tạo bean, vậy tại sao field `@Value` trong constructor vẫn có thể là `null`?

**Câu 2.** Trong một bean, thời điểm nào phù hợp để đọc field `@Value` instance sau khi injection: constructor hay `@PostConstruct`?

**Câu 3.** Nếu cần dùng ngay giá trị cấu hình trong constructor, nên chuyển sang cách khai báo nào?

**Câu 4.** Trường `private static String name` thuộc về instance hay class? Vì sao điều đó quan trọng với injection?

**Câu 5.** Một class có `@Component` nhưng được gọi bằng `new` tại một nơi khác. Object do `new` có tự được inject không?

**Câu 6.** Vì sao `@ConfigurationProperties` không phải cách để đưa trực tiếp giá trị vào một static field?

**Câu 7.** Tại sao không nên dùng một static holder chia sẻ cấu hình giữa nhiều Spring test context?

**Câu 8.** Thay file YAML rồi đọc lại `@Value` có tự nhận giá trị mới ngay trong tiến trình đang chạy không?

**Câu 9.** Cần phân biệt điều gì giữa việc một source được nạp và việc một field đã được inject?

**Câu 10.** Nếu một phương thức static thực sự chỉ định dạng chuỗi theo cấu hình, cách nào giúp nó không cần giữ global state?

**Gợi ý đáp án:**

1. Vì constructor chạy trước giai đoạn field injection của bean instance.
2. `@PostConstruct` hoặc các lời gọi sau khi bean đã được khởi tạo.
3. Dùng tham số constructor với `@Value` hoặc inject bean `@ConfigurationProperties`.
4. Thuộc về class; Spring field injection chuẩn nhắm vào bean instance.
5. Không; cần Spring quản lý instance hoặc truyền dependency bằng cách khác.
6. `@ConfigurationProperties` là cơ chế tạo và binding **bean instance**, không phải static injection.
7. Các context có thể chia sẻ một static field, làm rò trạng thái và gây lỗi thứ tự test.
8. Không mặc định; cấu hình cơ bản được nạp và inject lúc khởi động.
9. Source nằm trong `Environment` không đồng nghĩa một object bất kỳ đã qua lifecycle injection.
10. Dùng static method nhận tham số, hoặc chuyển formatter thành bean instance.

## 20. Áp dụng trong dự án thực tế

Một quy ước đơn giản cho service Spring Boot:

- **Giá trị đơn:** constructor parameter với `@Value("${service.some-key}")` nếu bài toán nhỏ.
- **Nhiều giá trị có liên quan:** `@ConfigurationProperties` và inject bean cấu hình qua constructor.
- **Không đọc một field-injected property trong constructor.**
- **Không đặt `@Value` hoặc `@Autowired` trực tiếp trên static field** và coi đó là dependency injection.
- **Không tự `new` object** nếu object đó cần Spring quản lý, trừ khi đã truyền đầy đủ dependency vào constructor.
- **Static utility nên stateless**, nhận cấu hình hoặc dữ liệu cần thiết qua tham số.
- **Mọi giá trị runtime cần có vòng đời rõ ràng**, gắn với context và được kiểm thử dưới profile/nguồn ưu tiên quan trọng.
- **Không in cấu hình nhạy cảm ra log**, kể cả trong callback `@PostConstruct` hoặc runner.

Khi một property không có mặt ở đúng nơi bạn mong đợi, hãy tự hỏi:

```text
1. Environment đã có giá trị hiệu lực chưa?
2. Đối tượng này có phải Spring bean không?
3. Tôi đang đọc trước hay sau injection?
4. Trường là instance hay static?
5. Có nguồn ưu tiên cao hơn hoặc fallback làm thay đổi kết quả không?
```

Nếu trả lời năm câu này theo thứ tự, bạn sẽ phân biệt được lỗi **nguồn cấu hình**, lỗi **thời điểm injection** và lỗi **thiết kế Java static**. Đó là nền tảng để truy cập cấu hình an toàn và nhất quán trong Spring Boot.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): giá trị cấu hình từ các nguồn, thứ tự ưu tiên và cách truy cập bằng `@Value`, `Environment`, `@ConfigurationProperties`.
- [Spring Framework — Using `@Value`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html): cách tham số và trường của bean nhận giá trị.
- [Spring Framework — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): xử lý dependency injection cho bean instances.
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): các callback khởi tạo, trong đó có `@PostConstruct`.