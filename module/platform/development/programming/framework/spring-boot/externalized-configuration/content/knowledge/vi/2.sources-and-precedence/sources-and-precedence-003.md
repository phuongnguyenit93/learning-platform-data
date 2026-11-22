# Cấu hình mặc định bằng `SpringApplication.setDefaultProperties`

Trong Spring Boot, cùng một thuộc tính có thể được khai báo ở nhiều nguồn: mã Java lúc khởi động, `application.properties`/`application.yml`, biến môi trường, Java system properties hoặc tham số dòng lệnh. `SpringApplication.setDefaultProperties(...)` giúp ứng dụng có **giá trị dự phòng chung** mà các nguồn cấu hình bên ngoài vẫn có thể ghi đè.

Bài học sử dụng Spring Boot 3.3.x và Java 21. Trọng tâm là cách khai báo, thời điểm áp dụng và thứ tự ưu tiên của giá trị mặc định.

## 1. `setDefaultProperties` làm gì?

`SpringApplication` cung cấp hai overload:

~~~java
void setDefaultProperties(Map<String, Object> defaultProperties);
void setDefaultProperties(Properties defaultProperties);
~~~

Các cặp khóa/giá trị được thêm vào Spring `Environment` dưới nguồn cấu hình tên `defaultProperties`. Đây là **nguồn có độ ưu tiên thấp nhất** trong thứ tự cấu hình thông thường của Spring Boot. Nếu một nguồn có ưu tiên cao hơn cung cấp cùng khóa, giá trị ở nguồn đó được sử dụng.

Ví dụ, khi cấu hình mặc định là `server.port=8081` nhưng `application.properties` chứa `server.port=8082`, ứng dụng web chạy trên cổng `8082`. Nếu tiếp tục khởi động với `--server.port=9090` thì cổng hiệu lực là `9090`.

Điểm cốt lõi:

- Giá trị mặc định chỉ được dùng khi chưa có giá trị cùng khóa từ nguồn ưu tiên cao hơn.
- Các giá trị này được cung cấp trước khi ứng dụng khởi động; chúng không sửa file cấu hình trên đĩa.
- Có thể đọc chúng qua `Environment`, inject bằng `@Value` hoặc bind qua `@ConfigurationProperties` như các cấu hình Spring khác.
- Không nên dùng chúng để áp đặt cấu hình riêng của production hay nhúng thông tin bí mật.

## 2. Ví dụ chạy được: khai báo trước `run(args)`

Giả sử một ứng dụng Spring Boot có `spring-boot-starter` và `spring-boot-starter-web` trong dependencies. Tạo lớp khởi động:

~~~java
package com.example.configdemo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ConfigDemoApplication.class);

        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("spring.application.name", "config-demo");
        defaults.put("server.port", 8081);
        defaults.put("demo.message", "Xin chào từ defaultProperties");
        defaults.put("demo.retry-count", 3);

        // Phải thiết lập trước khi SpringApplication.run được gọi.
        application.setDefaultProperties(defaults);
        application.run(args);
    }

    @Bean
    ApplicationRunner showEffectiveConfiguration(Environment environment) {
        return args -> {
            System.out.println("demo.message = "
                    + environment.getProperty("demo.message"));
            System.out.println("demo.retry-count = "
                    + environment.getProperty("demo.retry-count", Integer.class));
            System.out.println("server.port = "
                    + environment.getProperty("server.port", Integer.class));
        };
    }
}
~~~

Khi không khai báo thêm các khóa trên ở nguồn khác, chương trình in ra nội dung tương tự:

~~~text
demo.message = Xin chào từ defaultProperties
demo.retry-count = 3
server.port = 8081
~~~

`Environment.getProperty("demo.retry-count", Integer.class)` minh họa việc đọc theo kiểu dữ liệu; trong ví dụ này giá trị `3` được đặt vào `Map` dưới dạng số nguyên. Với ứng dụng không chạy web server, thuộc tính `server.port` vẫn có thể nằm trong `Environment` nhưng không tự tạo ra cổng lắng nghe.

**Vì sao phải tạo đối tượng `SpringApplication`?** Cách gọi nhanh `SpringApplication.run(ConfigDemoApplication.class, args)` chạy ứng dụng ngay. Muốn thiết lập giá trị mặc định trước thời điểm khởi động, hãy khởi tạo `SpringApplication`, cấu hình nó, rồi mới gọi `application.run(args)`.

## 3. So sánh giá trị mặc định với cấu hình bên ngoài

Giữ nguyên chương trình Java ở mục 2. Tạo file `src/main/resources/application.properties`:

~~~properties
demo.message=Xin chào từ application.properties
server.port=8082
~~~

Khi khởi động thông thường, hai khóa trong file ghi đè giá trị từ `setDefaultProperties`; `demo.retry-count` không có trong file nên vẫn nhận giá trị `3` từ mã Java:

~~~text
demo.message = Xin chào từ application.properties
demo.retry-count = 3
server.port = 8082
~~~

Sau đó chạy bản JAR với tham số dòng lệnh (thay `config-demo.jar` bằng tên JAR thực tế):

~~~bash
java -jar config-demo.jar --demo.message="Xin chào từ CLI" --server.port=9090
~~~

Khi ấy:

~~~text
demo.message = Xin chào từ CLI
demo.retry-count = 3
server.port = 9090
~~~

Bảng sau mô tả thứ tự ưu tiên **đối với cùng một khóa** trong những nguồn phổ biến của Spring Boot 3.3; nguồn ở dòng dưới ghi đè nguồn ở dòng trên:

| Nguồn cấu hình | Ví dụ | Vai trò |
| --- | --- | --- |
| Default properties | `application.setDefaultProperties(...)` | Giá trị dự phòng thấp nhất |
| Config data | `application.properties`, `application.yml`, file theo profile | Cấu hình ứng dụng và môi trường |
| Biến môi trường hệ điều hành | `DEMO_MESSAGE` | Cấu hình lúc triển khai |
| Java system properties | `-Ddemo.message=...` | Tham số của JVM |
| Tham số dòng lệnh | `--demo.message=...` | Ghi đè tại lần chạy |

Đây là bảng rút gọn, không phải toàn bộ danh sách `PropertySource`. Spring Boot còn hỗ trợ `@PropertySource`, `SPRING_APPLICATION_JSON`, thuộc tính do test cung cấp và một số nguồn khác. Các nguồn test như `@TestPropertySource` có thể có ưu tiên còn cao hơn tham số dòng lệnh. Trong các nguồn liệt kê ở bảng, `setDefaultProperties` luôn ở vị trí dự phòng.

### Cùng một khóa trong nhiều nguồn

Giả sử:

~~~text
setDefaultProperties    demo.message = "A"
application.properties  demo.message = "B"
biến môi trường         DEMO_MESSAGE = "C"
tham số dòng lệnh       --demo.message=D
~~~

Giá trị hiệu lực là `D`. Nếu bỏ tham số dòng lệnh, kết quả là `C`; bỏ tiếp biến môi trường, kết quả là `B`; chỉ khi không nguồn ưu tiên cao hơn nào khai báo khóa đó thì `A` mới được dùng.

Lưu ý: xử lý thuộc tính trong Spring Boot có thêm quy tắc bind tên và cấu hình theo profile. Trong ví dụ này, `DEMO_MESSAGE` là dạng biến môi trường của khóa `demo.message`.

## 4. Đọc cấu hình ở nơi sử dụng

### Qua `Environment`

Đây là cách trực tiếp để quan sát giá trị **đã được phân giải sau khi xét ưu tiên**:

~~~java
@Component
class MessagePrinter {

    private final Environment environment;

    MessagePrinter(Environment environment) {
        this.environment = environment;
    }

    String currentMessage() {
        return environment.getProperty("demo.message");
    }

    int retryCount() {
        return environment.getRequiredProperty("demo.retry-count", Integer.class);
    }
}
~~~

Cần import `org.springframework.stereotype.Component` và `org.springframework.core.env.Environment`. `getRequiredProperty` báo lỗi khi khóa bắt buộc vắng mặt; còn `getProperty` có thể trả `null` nếu không tìm thấy.

### Qua `@Value`

Một bean cũng có thể nhận cùng giá trị hiệu lực:

~~~java
@Component
class MessageService {

    @Value("${demo.message}")
    private String message;

    String message() {
        return message;
    }
}
~~~

Import `org.springframework.beans.factory.annotation.Value` và `org.springframework.stereotype.Component`. Placeholder `${demo.message}` lấy giá trị từ `Environment`; khi file hoặc tham số dòng lệnh ghi đè, bean nhận giá trị sau ghi đè.

### Qua `@ConfigurationProperties`

Với nhiều khóa liên quan, nên bind thành một đối tượng cấu hình có kiểu:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoSettings(String message, int retryCount) {
}
~~~

Đăng ký lớp bằng `@ConfigurationPropertiesScan` ở application class hoặc `@EnableConfigurationProperties(DemoSettings.class)`. Khi đó `demo.retry-count` được bind vào `retryCount`; các giá trị ban đầu có thể đến từ `setDefaultProperties` và được ghi đè bởi các nguồn khác. Cách này phù hợp hơn việc rải nhiều `@Value` khi cấu hình tăng dần.

## 5. Dùng overload `Properties`

Nếu đầu vào đang là đối tượng `java.util.Properties`, có thể truyền trực tiếp:

~~~java
SpringApplication application = new SpringApplication(ConfigDemoApplication.class);

Properties defaults = new Properties();
defaults.setProperty("demo.message", "Giá trị mặc định");
defaults.setProperty("demo.retry-count", "3");

application.setDefaultProperties(defaults);
application.run(args);
~~~

Import `java.util.Properties`. Đây là **cách thay thế** cho đoạn dùng `Map`, không phải một lệnh cần gọi thêm trong cùng ví dụ. `Properties` lưu giá trị chuỗi; Spring có cơ chế chuyển đổi khi bind sang kiểu đích phù hợp.

Khi giá trị được xây dựng ngay trong mã Java, `Map<String, Object>` thường dễ đọc và cho phép truyền số, boolean cùng chuỗi. Khi đã có một tập `Properties`, overload thứ hai tránh bước chuyển đổi thủ công.

## 6. Khi nào nên áp dụng?

**Giá trị dự phòng cho ứng dụng:** đặt tên ứng dụng, tùy chọn nghiệp vụ có giá trị an toàn hoặc giới hạn thử lại mặc định. Môi trường triển khai có thể chỉnh bằng file hoặc biến môi trường.

**Khởi động một chương trình dùng chung:** nhiều launcher có thể tạo `SpringApplication` và gán bộ mặc định tương ứng, trong khi vẫn chấp nhận cấu hình từ người vận hành.

**Giảm lặp cấu hình tùy chọn:** thay vì buộc mọi môi trường phải khai báo `demo.retry-count`, có thể đưa giá trị mặc định vào một chỗ. Tuy nhiên, đối với các thuộc tính cấu hình nghiệp vụ thông thường, khai báo trong `application.yml` thường dễ theo dõi và điều chỉnh hơn.

Ví dụ các giá trị chung:

~~~java
Map<String, Object> defaults = Map.of(
        "demo.retry-count", 3,
        "demo.feature-enabled", false,
        "demo.batch-size", 100
);
application.setDefaultProperties(defaults);
~~~

Chỉ dùng các mặc định phù hợp với môi trường thực tế. Các khóa nhạy cảm như mật khẩu, token, khóa API phải được cấp từ hệ thống quản lý secrets hoặc nguồn cấu hình triển khai thích hợp.

## 7. Phân biệt với các cơ chế dễ nhầm

| Cơ chế | Ý nghĩa |
| --- | --- |
| `setDefaultProperties(...)` | Thêm giá trị dự phòng vào `Environment` ở ưu tiên thấp |
| `application.properties` / `application.yml` | Lưu cấu hình theo file, có thể tách theo profile hoặc vị trí triển khai |
| `@Value("${demo.message:Fallback}")` | Cung cấp fallback riêng cho **một placeholder** khi phân giải nó |
| `@ConfigurationProperties` | Bind nhiều khóa thành object có kiểu; tự nó không định nghĩa thứ tự ưu tiên |
| `SpringApplicationBuilder.properties(...)` | API builder để thiết lập default properties khi xây dựng ứng dụng |
| `setAdditionalProfiles(...)` | Bổ sung profile đang hoạt động; không phải API khai báo các cặp khóa/giá trị mặc định |

Ví dụ, `@Value("${demo.message:Fallback}")` chỉ cung cấp fallback tại vị trí inject đó. Ngược lại, đặt `demo.message` bằng `setDefaultProperties` khiến giá trị tồn tại trong `Environment` và có thể được các thành phần khác cùng sử dụng.

## 8. Lỗi thường gặp và cách xác định nguyên nhân

**Đặt mặc định sau `run(args)`.** Lúc đó quá trình tạo `Environment`, bind bean và cấu hình ứng dụng đã diễn ra. Hãy gọi `setDefaultProperties` trên đối tượng `SpringApplication` **trước** `run`.

**Nhầm default là giá trị buộc phải dùng.** Nếu `application.yml` hoặc tham số khởi động có cùng khóa, giá trị mặc định bị ghi đè theo thiết kế. Muốn tìm nguồn hiệu lực, hãy kiểm tra các nguồn đang cung cấp khóa, thay vì sửa giá trị trong `Map` nhiều lần.

**Khác tên khóa.** Ví dụ `demo.retry-count` và `demo.retryCount` có thể được xử lý theo quy tắc relaxed binding khi dùng `@ConfigurationProperties`, nhưng nên viết tên chuẩn dạng chữ thường, dấu gạch ngang cho khóa nhiều từ. Kiểm tra chính xác tên khi dùng `Environment.getProperty` hoặc placeholder.

**Giả định mọi tham số CLI đều có hiệu lực.** Thông thường Spring Boot đưa các tham số `--key=value` vào `Environment`, nhưng ứng dụng có thể tắt cơ chế này bằng `setAddCommandLineProperties(false)`. Khi đó ví dụ ghi đè qua CLI không còn áp dụng.

**Dùng fallback để che thiếu cấu hình bắt buộc.** Nếu ứng dụng không thể chạy an toàn khi thiếu endpoint hoặc secret, nên xác thực sự hiện diện của cấu hình thay vì cung cấp mặc định giả. `setDefaultProperties` thích hợp với giá trị dự phòng thực sự hợp lệ.

**Chẩn đoán theo file đơn lẻ.** Giá trị đọc từ file chưa chắc là giá trị hiệu lực. Có thể dùng `Environment` để in giá trị cuối cùng, hoặc endpoint Actuator `env`/`configprops` nếu ứng dụng đã bật, bảo vệ và cấp quyền phù hợp.

## 9. Bài thực hành

1. Chạy ứng dụng ở mục 2, giữ `application.properties` không có ba khóa `demo.message`, `demo.retry-count`, `server.port`. Quan sát các giá trị mặc định.
2. Khai báo `demo.retry-count=5` trong `application.properties`; kiểm tra `Environment` trả về `5` nhưng các khóa khác không đổi.
3. Chạy với `--demo.retry-count=8`; kiểm tra tham số CLI ghi đè giá trị ở file và mặc định.
4. Chuyển dòng `demo.message` trong file sang `application-dev.properties` và khởi động với `--spring.profiles.active=dev`; kiểm tra giá trị theo profile.
5. Bỏ tất cả các ghi đè và xác nhận chương trình quay lại giá trị đặt trong `setDefaultProperties`.

Nếu có hai nguồn khai báo cùng một khóa mà kết quả khác dự đoán, hãy xác định thứ tự ưu tiên của chúng và kiểm tra profile cùng các tham số khởi động.

## Ghi nhớ

`SpringApplication.setDefaultProperties` là điểm khai báo **giá trị mặc định cho toàn bộ ứng dụng trước khi chạy**. Nó giúp ứng dụng có fallback nhất quán, đồng thời tôn trọng cấu hình ở file, biến môi trường và tham số dòng lệnh. Khả năng ghi đè này là chủ đích của cơ chế externalized configuration trong Spring Boot.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
