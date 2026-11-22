# Phạm vi Spring Boot 3.3 và kiến thức Java, IoC cần chuẩn bị

## 1. Học bài này để làm gì?

Một ứng dụng thường phải chạy ở nhiều nơi: máy lập trình, môi trường kiểm thử, máy chủ thật và hệ thống triển khai tự động. Mã nguồn có thể giống nhau, nhưng địa chỉ cơ sở dữ liệu, cổng mạng, thời gian chờ, mức ghi log và thông tin xác thực có thể khác nhau. Nếu mọi giá trị đều được viết cố định trong mã Java, mỗi lần chuyển môi trường lại có nguy cơ phải sửa mã, đóng gói và phát hành lại.

**Externalized Configuration** (cấu hình tách khỏi mã ứng dụng) là cách Spring Boot tiếp nhận các giá trị từ nhiều nguồn bên ngoài lớp Java, chọn giá trị có hiệu lực theo quy tắc ưu tiên và cung cấp chúng cho các thành phần đang chạy. Bài này giới thiệu phạm vi kiến thức cần học trong **Spring Boot 3.3** và chuẩn bị nền tảng **Java, IoC, DI** để hiểu cơ chế ấy.

Sau bài này, bạn cần hình dung được:

- Tại sao cùng một tệp JAR có thể chạy với cấu hình khác nhau ở các môi trường.
- Sự khác nhau giữa **nguồn cấu hình**, **giá trị cấu hình**, **đối tượng cấu hình** và **Spring bean sử dụng cấu hình**.
- Những phần của Java và Spring IoC phải nắm trước khi dùng `@Value`, `Environment` hay `@ConfigurationProperties`.
- Cách chạy một ví dụ nhỏ để quan sát việc cấu hình được đọc, ghi đè và đưa vào bean.

Đây là bài định hướng. Những quy tắc chuyên sâu như thứ tự đầy đủ của mọi nguồn cấu hình, nhập thêm tệp, cấu hình nhiều tài liệu YAML và cách xử lý các tình huống triển khai phức tạp sẽ được tìm hiểu kỹ hơn ở những bài riêng.

## 2. Phạm vi phiên bản: Spring Boot 3.3

Các ví dụ và cách giải thích trong tài liệu lấy **Spring Boot 3.3.x** làm mốc. Khi tự thực hành, chọn một bản vá thuộc nhánh 3.3 và giữ phiên bản các thư viện theo cơ chế quản lý phụ thuộc của Spring Boot.

| Thành phần | Giả định trong bài | Ý nghĩa khi thực hành |
| --- | --- | --- |
| Spring Boot | Nhánh 3.3.x | Sử dụng cơ chế cấu hình và liên kết thuộc tính của Spring Boot 3.3. |
| Java | **Java 17 trở lên** | Java 17 là mức tối thiểu của Spring Boot 3.3; ví dụ dùng cú pháp có trong Java 17. |
| Spring Framework | Nền tảng IoC và `ApplicationContext` đi kèm Spring Boot 3.3 | Spring tạo và quản lý bean, sau đó đưa cấu hình vào bean cần sử dụng. |
| Cách đóng gói | Ứng dụng Spring Boot chạy bằng JAR hoặc từ công cụ build | Cho phép thay đổi đối số dòng lệnh và biến môi trường khi khởi động. |
| Cú pháp cấu hình | `.properties`, `.yaml`/`.yml` | Hai cách biểu diễn dữ liệu cấu hình phổ biến; không cần học một định dạng riêng của Java. |
| API liên quan | `Environment`, `@Value`, `@ConfigurationProperties` | Ba điểm tiếp cận thường gặp để đọc hay sử dụng cấu hình. |

Spring Boot 3 dùng hệ sinh thái **Jakarta** cho các API đã chuyển từ `javax.*`. Ví dụ, khi kiểm tra hợp lệ đối tượng cấu hình bằng Bean Validation, các annotation như `@NotBlank` nằm trong `jakarta.validation.constraints`, không phải `javax.validation.constraints`. Đây là điểm cần lưu ý khi đọc ví dụ cũ dành cho Spring Boot 2.

**Trong phạm vi học phần Externalized Configuration**, cần nắm:

1. Nguồn dữ liệu: `application.properties`, `application.yml`, tệp theo profile, biến môi trường, thuộc tính JVM và đối số dòng lệnh.
2. Cách Spring Boot hợp nhất nguồn thành các thuộc tính có thể tra cứu và cách nguồn ưu tiên cao ghi đè nguồn thấp.
3. Cách đặt tên khóa, chuyển kiểu, giá trị mặc định và liên kết nhóm khóa vào lớp Java.
4. Vai trò của profile, kiểm tra hợp lệ cấu hình và cách phân biệt cấu hình thông thường với bí mật.
5. Cách kiểm tra giá trị thực sự được ứng dụng sử dụng khi khởi động.

**Ngoài phạm vi nhập môn này** là việc vận hành máy chủ cấu hình từ xa, tự động phân phối bí mật bằng hạ tầng chuyên dụng, điều phối cấu hình Kubernetes, cơ chế làm mới bean khi cấu hình thay đổi và xây dựng bộ tải cấu hình tùy biến. Các chủ đề ấy liên quan nhưng không cần để hiểu mô hình cơ bản của Spring Boot.

## 3. Mô hình tư duy: cấu hình đi từ đâu đến đâu?

Hãy tách bốn khái niệm:

- **Nguồn cấu hình (property source):** nơi chứa cặp khóa và giá trị, chẳng hạn tệp, biến môi trường hoặc tham số khởi động.
- **Khóa cấu hình (property key):** tên logic như `app.greeting`, `server.port`, `logging.level.root`.
- **Môi trường cấu hình (`Environment`):** giao diện của Spring giúp tra cứu giá trị có hiệu lực theo các nguồn đã được sắp xếp.
- **Bean nhận cấu hình:** đối tượng do Spring quản lý, có thể nhận một giá trị qua `@Value` hoặc nhận cả nhóm giá trị qua `@ConfigurationProperties`.

Đường đi khái quát:

```text
application.properties / application.yml
application-dev.properties
biến môi trường / thuộc tính JVM / đối số khởi động
                  |
                  v
         Các PropertySource
                  |
                  v
       Spring Environment
                  |
          +-------+------------------+
          |                          |
          v                          v
  @Value / Environment     Binder + @ConfigurationProperties
          |                          |
          v                          v
    giá trị riêng lẻ       đối tượng cấu hình có kiểu Java
          |                          |
          +------------+-------------+
                       |
                       v
             bean được Spring quản lý
                       |
                       v
              hành vi của ứng dụng
```

Ví dụ khóa `app.limit=5` trong tệp có thể bị ghi đè bởi biến môi trường tương ứng hoặc tham số `--app.limit=8`. `Environment` nhìn thấy giá trị có hiệu lực; Spring Boot có thể chuyển chuỗi `"8"` thành `int` khi liên kết với đối tượng Java.

**Cấu hình không phải là bean.** Tệp `.properties` chỉ chứa dữ liệu. Bean là đối tượng Java được Spring tạo và quản lý. `@ConfigurationProperties` là cầu nối biến một nhóm giá trị thành một đối tượng có kiểu, rồi IoC/DI đưa đối tượng ấy đến nơi cần dùng.

## 4. Kiến thức Java nên có trước

### 4.1. Lớp, đối tượng, phương thức và hàm tạo

Cần đọc được một lớp Java, hiểu tham số hàm tạo, trường dữ liệu, quyền truy cập và cách gọi phương thức. DI thường truyền phụ thuộc qua **hàm tạo (constructor)**; nếu chưa hiểu cách tạo đối tượng bằng `new`, bạn sẽ khó thấy Spring đã thay phần việc nào.

```java
public final class GreetingService {
    private final String greeting;

    public GreetingService(String greeting) {
        this.greeting = greeting;
    }

    public String message(String name) {
        return greeting + ", " + name;
    }
}

// Java thông thường: người gọi tự tạo và truyền tham số.
GreetingService service = new GreetingService("Xin chào");
System.out.println(service.message("An"));
```

Trong Spring, nguyên tắc truyền phụ thuộc vẫn như vậy; khác biệt là `ApplicationContext` có thể phụ trách tạo và nối các đối tượng.

### 4.2. Kiểu dữ liệu và chuyển kiểu

Nên quen với `String`, `int`, `long`, `boolean`, số thực, `enum`, `List`, `Map` và các kiểu ngày giờ thường gặp như `Duration`. Nhiều nguồn cấu hình lưu giá trị dưới dạng văn bản; Spring Boot phải chuyển chúng sang kiểu mà chương trình yêu cầu.

| Giá trị cấu hình | Kiểu Java thường dùng | Cần hiểu |
| --- | --- | --- |
| `app.name=checkout` | `String` | Chuỗi văn bản và cách dùng trong mã. |
| `app.limit=5` | `int` hoặc `Integer` | Chuyển sang số nguyên; đầu vào không hợp lệ có thể làm khởi động thất bại. |
| `app.enabled=true` | `boolean` | Giá trị bật/tắt. |
| `app.timeout=3s` | `Duration` | Thời lượng có đơn vị; tránh nhầm giây với mili giây. |
| `app.mode=FAST` | `enum` | Tập lựa chọn có giới hạn, cần tên hợp lệ. |

Không được mặc định rằng mọi chuỗi bất kỳ đều chuyển được sang kiểu Java mong muốn. Một giá trị sai kiểu có thể gây lỗi liên kết cấu hình ngay khi tạo bean.

### 4.3. Tính bất biến và `record`

Spring Boot 3.3 làm việc thuận tiện với **record** của Java để biểu diễn dữ liệu cấu hình bất biến.

```java
public record RetryPolicy(int maxAttempts, Duration delay) {
}
```

`record` tạo hàm tạo, các phương thức truy cập `maxAttempts()` và `delay()`, cùng các phương thức cơ bản cho dữ liệu. Khi liên kết cấu hình qua hàm tạo, Spring Boot cung cấp giá trị lúc tạo đối tượng; mã sử dụng không phải gán lại từng trường.

Cần phân biệt `record` Java với một bean Spring: bản thân khai báo `record` chưa tự đăng ký nó vào `ApplicationContext`.

### 4.4. Annotation, package và phụ thuộc thư viện

Bạn cần nhận biết cú pháp `@Something`, hiểu `import` và biết một annotation thường chỉ có ý nghĩa khi có thư viện hoặc cơ chế xử lý tương ứng. Ví dụ `@ConfigurationProperties` thuộc Spring Boot; `@Bean` thuộc Spring Framework; `@NotBlank` thuộc Jakarta Validation.

Nên biết cách chọn Java 17, tạo dự án qua Spring Initializr, thêm dependency với Maven/Gradle và đọc lỗi khởi động trong console. Không cần thành thạo các tính năng Java nâng cao trước khi học cấu hình.

## 5. Kiến thức IoC và DI phải hiểu

### 5.1. IoC là gì?

**Inversion of Control (đảo ngược quyền điều khiển, IoC)** là cách chương trình giao việc tạo, kết nối và quản lý vòng đời các đối tượng cần thiết cho một bộ chứa. Trong ứng dụng Spring, bộ chứa này được tiếp cận qua `ApplicationContext`.

Thay vì tự viết `new GreetingService(...)` ở mọi nơi, bạn có thể khai báo một thành phần để Spring tạo bean và cấp cho thành phần khác.

### 5.2. DI là gì?

**Dependency Injection (tiêm phụ thuộc, DI)** là cách đưa những đối tượng hoặc giá trị mà một thành phần cần vào thành phần ấy. Một hình thức dễ đọc là tiêm qua hàm tạo:

```java
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {
    private final MessageFormatter formatter;

    public WelcomeService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public String welcome(String name) {
        return formatter.format(name);
    }
}
```

Đoạn mã trên giả định `MessageFormatter` đã được đăng ký thành một Spring bean. Spring tìm bean tương ứng và truyền vào `WelcomeService` khi tạo nó. Nếu không có bean phù hợp, ứng dụng có thể báo lỗi trong quá trình khởi động.

Điểm cốt lõi cần nhớ: **DI giải quyết ai cung cấp phụ thuộc; Externalized Configuration giải quyết giá trị cấu hình được lấy từ đâu và chọn như thế nào.** Hai cơ chế gặp nhau khi bean phụ thuộc vào một đối tượng cấu hình.

### 5.3. Bean được đăng ký theo cách nào?

- `@Component`, `@Service`, `@Repository` đánh dấu các loại thành phần có thể được quét và tạo thành bean.
- `@Configuration` cùng `@Bean` cho phép khai báo cách tạo bean rõ ràng.
- `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` cho phép đăng ký các lớp cấu hình kiểu `@ConfigurationProperties` theo đúng cơ chế của Spring Boot.

**Không nên nhầm `@Configuration` với `@ConfigurationProperties`.** `@Configuration` thường khai báo các phương thức tạo bean; `@ConfigurationProperties` mô tả cách liên kết một nhóm thuộc tính vào đối tượng Java.

## 6. Ví dụ nhỏ: cùng mã Java, nhiều cấu hình

Ví dụ dưới đây chỉ cần ứng dụng Spring Boot 3.3.x, Java 17 và dependency nền tảng `spring-boot-starter`. Dùng Spring Initializr hoặc dự án Spring Boot có sẵn, đặt các lớp trong cùng package `example.configdemo`. Khi đóng gói, thay `app.jar` bằng đường dẫn JAR thực tế.

**Bước 1 — khai báo nguồn cấu hình.**

`src/main/resources/application.properties`:

```properties
app.greeting=Xin chào từ tệp
app.limit=3
```

**Bước 2 — tạo đối tượng cấu hình có kiểu.**

`AppSettings.java`:

```java
package example.configdemo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppSettings(String greeting, int limit) {
}
```

Các khóa `app.greeting` và `app.limit` tương ứng với hai thành phần của record. Spring Boot dùng cơ chế liên kết qua hàm tạo để tạo `AppSettings`. Với record có một hàm tạo chính như trên, không cần thêm `@ConstructorBinding`.

**Bước 3 — đăng ký đối tượng cấu hình và sử dụng bằng DI.**

`ConfigDemoApplication.java`:

```java
package example.configdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showSettings(AppSettings settings) {
        return args -> System.out.printf(
            "Greeting=%s; limit=%d%n",
            settings.greeting(),
            settings.limit()
        );
    }
}
```

`@ConfigurationPropertiesScan` giúp Spring Boot tìm và đăng ký `AppSettings`. Khi tạo `ApplicationRunner`, Spring đưa bean `AppSettings` vào tham số `showSettings(...)`. Đó là DI: đoạn mã không tự đọc tệp và không tự gọi `new AppSettings(...)`.

Chạy ứng dụng với cấu hình mặc định sẽ in:

```text
Greeting=Xin chào từ tệp; limit=3
```

**Bước 4 — thử ghi đè từ đối số khởi động.**

```bash
java -jar app.jar --app.greeting="Xin chào từ dòng lệnh" --app.limit=7
```

Kết quả mong đợi:

```text
Greeting=Xin chào từ dòng lệnh; limit=7
```

Tệp `application.properties` không thay đổi. Đối số dòng lệnh được Spring Boot đưa vào nguồn cấu hình có độ ưu tiên cao hơn giá trị trong tệp ở tình huống này.

**Bước 5 — thử biến môi trường.**

Trên Bash:

```bash
APP_GREETING="Xin chào từ biến môi trường" java -jar app.jar
```

Trên PowerShell:

```powershell
$env:APP_GREETING = "Xin chào từ biến môi trường"
java -jar app.jar
```

Khi không có đối số `--app.greeting` ghi đè, giá trị lời chào lấy từ biến môi trường. `app.limit` tiếp tục là `3` từ tệp. Với cách đặt tên linh hoạt của Spring Boot (relaxed binding), `APP_GREETING` có thể tương ứng với khóa `app.greeting`.

Nếu thử nhiều lần trên cùng terminal, hãy lưu ý biến môi trường đã đặt có thể tiếp tục ảnh hưởng đến các lần chạy sau. Bạn cần bỏ biến đó hoặc mở terminal sạch để so sánh đúng.

## 7. Profile và thứ tự ưu tiên: những gì cần biết ở mức nhập môn

**Profile** (hồ sơ môi trường) cho phép chọn nhóm cấu hình phù hợp với hoàn cảnh chạy. Ví dụ tạo thêm `src/main/resources/application-dev.properties`:

```properties
app.greeting=Xin chào từ profile dev
```

Sau đó chạy:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Nếu không có nguồn ưu tiên cao hơn đặt `app.greeting`, Spring Boot lấy lời chào trong tệp dành cho profile `dev`; `app.limit` vẫn có thể lấy từ tệp chung. Bạn có thể thay `dev` bằng tên profile khác do dự án quy ước.

Trong ví dụ thông thường này, khi **cùng một khóa** xuất hiện ở nhiều nơi, có thể hình dung thứ tự ưu tiên từ cao xuống thấp như sau:

```text
Đối số ứng dụng: --app.greeting=...
          >
Biến môi trường: APP_GREETING
          >
Tệp của profile đang hoạt động: application-dev.properties
          >
Tệp chung: application.properties
```

Đây là **lược đồ thực hành**, không phải bảng thứ tự đầy đủ của mọi `PropertySource` mà Spring Boot hỗ trợ. Còn có cấu hình kiểm thử, thuộc tính JVM, JSON cấu hình, nguồn nhập thêm và các trường hợp nhiều tệp/nhiều vị trí. Khi cần giải thích một giá trị bất ngờ, phải xét **tất cả nguồn thực tế đang tham gia**, thay vì chỉ nhìn một tệp.

Một số phân biệt cần nắm ngay:

- **Tên khóa và giá trị** là hai việc khác nhau: `app.greeting` là khóa; câu chào cụ thể là giá trị.
- **Profile không đồng nghĩa với biến môi trường hệ điều hành.** Profile là cơ chế của Spring; bạn có thể kích hoạt nó bằng `spring.profiles.active` từ một nguồn cấu hình phù hợp.
- **Biến môi trường** do tiến trình kế thừa lúc khởi động. Sửa biến hoặc sửa tệp trên đĩa không đồng nghĩa với việc bean đang chạy tự được tạo lại hay tự cập nhật.
- **Thứ tự ưu tiên quyết định giá trị có hiệu lực** khi nhiều nguồn cung cấp cùng khóa; không có nghĩa toàn bộ nội dung từ nguồn thấp bị loại bỏ.

## 8. Khi nào dùng `@Value`, `Environment`, `@ConfigurationProperties`?

Ba lựa chọn cùng tham gia sử dụng cấu hình nhưng có mục đích khác nhau.

| Cách tiếp cận | Dùng khi nào | Điểm cần chú ý |
| --- | --- | --- |
| `@Value("${app.greeting}")` | Cần tiêm một giá trị nhỏ, độc lập vào bean | Khóa được tham chiếu trực tiếp; nhiều giá trị rời rạc có thể khó quản lý. |
| `Environment#getProperty("app.greeting")` | Cần tra cứu giá trị tại một vị trí cụ thể trong mã hoặc công cụ chẩn đoán | Mã sử dụng phải biết tên khóa; kết quả có thể là `null` nếu không tồn tại. |
| `@ConfigurationProperties(prefix = "app")` | Có một nhóm cấu hình thuộc cùng chức năng | Liên kết vào kiểu Java, phù hợp với record, chuyển kiểu và kiểm tra hợp lệ. |

Ví dụ đơn giản với `@Value`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingLabel {
    private final String greeting;

    public GreetingLabel(@Value("${app.greeting:Chào bạn}") String greeting) {
        this.greeting = greeting;
    }

    public String text() {
        return greeting;
    }
}
```

Trong biểu thức `${app.greeting:Chào bạn}`, phần sau dấu `:` là giá trị dự phòng nếu không tìm thấy khóa. Đây là cú pháp placeholder được Spring xử lý, không phải cú pháp đọc thuộc tính của Java.

Với nhiều cấu hình cùng một chức năng, ví dụ thời gian chờ, số lần thử lại, URL dịch vụ và cờ bật/tắt, `@ConfigurationProperties` thường rõ ràng hơn vì gom chúng vào một đối tượng có kiểu. Không cần dùng cả ba cách cho cùng một thuộc tính nếu không có lý do cụ thể.

## 9. Kiểm tra hợp lệ và xử lý cấu hình thiếu

Cấu hình là dữ liệu đầu vào của ứng dụng. Một số giá trị tuy chuyển được sang kiểu Java nhưng không phù hợp về mặt nghiệp vụ, chẳng hạn số lần thử lại bằng `0` hoặc lời chào rỗng. Có thể đặt ràng buộc cho đối tượng cấu hình.

Nếu thêm dependency `spring-boot-starter-validation`, thay `AppSettings` ở ví dụ bằng:

```java
package example.configdemo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppSettings(
    @NotBlank String greeting,
    @Min(1) int limit
) {
}
```

Khi Spring Boot liên kết và kiểm tra cấu hình, một giá trị vi phạm ràng buộc sẽ làm ứng dụng báo lỗi thay vì tiếp tục chạy với cấu hình không phù hợp. Nếu không có thư viện Bean Validation tương ứng, không nên giả định rằng chỉ thêm annotation là đủ để mọi ràng buộc được thực thi.

Ba tình huống cần phân biệt khi đọc lỗi:

1. **Thiếu khóa:** không tìm thấy giá trị và cũng không có mặc định phù hợp.
2. **Sai kiểu:** ví dụ `app.limit=abc` trong khi trường Java là `int`.
3. **Sai quy tắc hợp lệ:** ví dụ `app.limit=0` với `@Min(1)`.

Thông báo lỗi thường chỉ ra tên khóa hoặc vị trí liên kết cấu hình. Hãy kiểm tra **khóa thực tế**, **nguồn đang thắng theo thứ tự ưu tiên** và **kiểu/ràng buộc của Java**.

## 10. Những nhầm lẫn thường gặp trước khi học sâu

**Nhầm 1 — Tệp `application.properties` là nguồn duy nhất.** Nó chỉ là một nguồn trong số nhiều nguồn mà Spring Boot hỗ trợ. Giá trị bạn đọc trong tệp chưa chắc là giá trị cuối cùng khi chạy.

**Nhầm 2 — Đặt `@ConfigurationProperties` là đủ để có bean.** Bạn còn cần đăng ký lớp cấu hình qua `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc cơ chế đăng ký phù hợp. Trong ví dụ này ta dùng `@ConfigurationPropertiesScan`.

**Nhầm 3 — IoC tự hiểu mọi khóa tùy ý.** Spring chỉ có thể liên kết đúng khi tên khóa, tiền tố cấu hình, kiểu dữ liệu và cách đăng ký bean phù hợp. Sai một trong các điểm này có thể tạo ra giá trị thiếu hoặc lỗi khởi động.

**Nhầm 4 — Có thể dùng cú pháp ví dụ Spring Boot 2 mà không kiểm tra.** Hãy chú ý mức Java, thay đổi `javax` sang `jakarta` và cách dùng constructor binding trên Spring Boot 3.3. Với record chỉ có một hàm tạo, không cần tự thêm `@ConstructorBinding` để dùng liên kết qua hàm tạo.

**Nhầm 5 — Biến môi trường luôn an toàn cho bí mật.** Biến môi trường thường thuận tiện để triển khai, nhưng có thể bị lộ qua cấu hình hạ tầng, log hoặc công cụ kiểm tra tiến trình. Không đưa mật khẩu, khóa truy cập hay mã thông báo thật vào ví dụ, tệp cam kết lên Git hoặc log. Ở môi trường thật, chọn cách quản lý bí mật phù hợp với hạ tầng.

**Nhầm 6 — Thay đổi tệp sẽ tự cập nhật đối tượng cấu hình đang chạy.** Trong ứng dụng Spring Boot thông thường, các bean cấu hình được tạo trong quá trình khởi động. Muốn làm mới động phải có cơ chế được thiết kế riêng; không nên mặc định có khả năng này.

**Nhầm 7 — Dùng profile để giấu bí mật.** Profile giúp chọn cấu hình theo bối cảnh, không phải cơ chế mã hóa hay quản lý bí mật.

## 11. Bài thực hành tự kiểm tra nền tảng

Hãy thực hiện lần lượt trên ứng dụng `ConfigDemoApplication`:

1. Khởi động chỉ với `application.properties`; dự đoán và ghi lại hai giá trị được in ra.
2. Đặt `APP_GREETING` rồi khởi động lại; xác định giá trị nào đổi và giá trị nào giữ nguyên.
3. Giữ biến môi trường, thêm `--app.greeting=...` khi khởi động; giải thích vì sao giá trị từ đối số được chọn.
4. Tạo `application-dev.properties`, bật profile `dev` và quan sát kết quả khi **không** có biến môi trường hoặc đối số ghi đè lời chào.
5. Đổi `app.limit=abc`; nhận diện đây là lỗi chuyển kiểu.
6. Bổ sung Bean Validation, đổi `app.limit=0`; nhận diện đây là lỗi ràng buộc.
7. Mở lại mã Java và chỉ ra: nơi đọc nguồn cấu hình, nơi tạo `AppSettings`, nơi DI đưa `AppSettings` vào `ApplicationRunner`.

Bạn đã có nền tảng để học các bài tiếp theo khi tự trả lời được:

- Vì sao cùng một JAR có thể nhận cấu hình khác nhau mà không sửa mã Java?
- `Environment`, `PropertySource`, `@ConfigurationProperties` và Spring bean có vai trò gì khác nhau?
- `record` và hàm tạo giúp biểu diễn cấu hình bất biến như thế nào?
- Khi cùng một khóa xuất hiện ở nhiều nguồn, phải tìm nguyên nhân của giá trị cuối cùng ở đâu?
- Phần nào thuộc Java, phần nào thuộc IoC/DI và phần nào thuộc cơ chế Externalized Configuration của Spring Boot?

Từ nền tảng này, có thể đi sâu theo trình tự: **nguồn cấu hình → thứ tự ưu tiên → profile → liên kết kiểu dữ liệu → kiểm tra hợp lệ → vận hành an toàn**. Chuỗi học đó kết nối kiến thức Java với cách Spring Boot 3.3 sử dụng cấu hình trong một ứng dụng thực tế.
