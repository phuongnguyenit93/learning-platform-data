# Dùng phương thức run tĩnh và đối tượng SpringApplication tùy biến

## Mục tiêu

Trong Spring Boot, lớp `org.springframework.boot.SpringApplication` khởi động ứng dụng từ phương thức `main(String[] args)`. Có hai cách sử dụng phổ biến:

- **Gọi tĩnh:** `SpringApplication.run(RuntimeApplication.class, args)`. Đây là cách ngắn gọn, thích hợp cho phần lớn ứng dụng.
- **Tạo đối tượng:** `new SpringApplication(RuntimeApplication.class)`, cấu hình đối tượng rồi gọi `application.run(args)`. Cách này phù hợp khi cần tác động đến quá trình khởi động bằng Java.

Cả hai cách đều chạy cơ chế bootstrap của Spring Boot. Điểm khác nhau chính là khả năng **thiết lập các tùy chọn của đối tượng SpringApplication trước khi gọi run**; tạo đối tượng không có nghĩa là tự triển khai lại Spring container.

## 1. SpringApplication thực hiện những gì?

Khi `run(...)` được gọi, Spring Boot sử dụng các nguồn cấu hình (primary sources) được cung cấp, chuẩn bị `Environment`, nhận đối số dòng lệnh, lựa chọn loại `ApplicationContext` thích hợp, tải cấu hình và bean, áp dụng auto-configuration, làm mới context, rồi chạy các bean `ApplicationRunner` và `CommandLineRunner` nếu có. Khi ứng dụng web được cấu hình đúng và có thư viện web phù hợp, quá trình khởi động còn tạo web server nhúng.

`@SpringBootApplication` thường đặt trên lớp khởi động; annotation này kết hợp cấu hình Spring, kích hoạt auto-configuration và quét component bắt đầu từ package chứa lớp đó. Vì vậy nên đặt lớp chính ở package gốc của ứng dụng.

Cần phân biệt:

- **`run` tĩnh** nhận lớp cấu hình chính và `args`: `SpringApplication.run(RuntimeApplication.class, args)`.
- **`run` của đối tượng** nhận `args` vì lớp nguồn đã được truyền vào constructor: `application.run(args)`.
- Cả hai đều trả về `ConfigurableApplicationContext`. Có thể dùng context để truy cập bean hoặc đóng ứng dụng có chủ đích; không nên đóng context ngay sau `run` nếu muốn một web server tiếp tục hoạt động.

## 2. Ví dụ chạy được: gọi phương thức run tĩnh

Ví dụ sử dụng **Java 21, Spring Boot 3.3.13 và Gradle**. Dự án chỉ dùng `spring-boot-starter` nên là ứng dụng không có web server; sau khi chạy `CommandLineRunner`, tiến trình có thể kết thúc bình thường.

Cấu trúc thư mục:

~~~text
spring-application-run-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runtime/RuntimeApplication.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'spring-application-run-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.runtime.RuntimeApplication'
}
~~~

Tệp `src/main/java/com/example/runtime/RuntimeApplication.java`:

~~~java
package com.example.runtime;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class RuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeApplication.class, args);
    }

    @Bean
    CommandLineRunner printMode(Environment environment) {
        return args -> System.out.println(
                "app.mode=" + environment.getProperty("app.mode", "basic"));
    }
}
~~~

Giải thích:

1. `RuntimeApplication.class` là nguồn cấu hình chính mà Spring Boot sử dụng để tìm cấu hình và bean. Tham số này **không phải** đối tượng được tạo bằng `new RuntimeApplication()`.
2. `args` chuyển đối số khi chạy chương trình vào cơ chế xử lý của Spring Boot. Ví dụ đối số `--app.mode=from-cli` có thể trở thành một property trong `Environment`.
3. `@Bean` khai báo một `CommandLineRunner`; Spring Boot gọi runner khi context đã khởi tạo xong.
4. `environment.getProperty("app.mode", "basic")` dùng giá trị `basic` khi chưa có property `app.mode`.

Tại thư mục dự án, sử dụng Gradle đã cài hoặc Gradle Wrapper (nếu dự án có tệp wrapper):

~~~bash
gradle bootRun
gradle bootRun --args="--app.mode=from-cli"
~~~

Trên Windows, khi đã có Gradle Wrapper, có thể thay `gradle` bằng `.\gradlew.bat`.

Dòng **do mã ứng dụng tự in ra**, bỏ qua các dòng log Spring Boot có thể khác giữa các máy:

~~~text
app.mode=basic
~~~

Với lệnh thứ hai, dòng ứng dụng in ra là:

~~~text
app.mode=from-cli
~~~

Ví dụ này không sử dụng `spring-boot-starter-web`, nên **không có địa chỉ HTTP hoặc cổng 8080** để truy cập. Thêm web starter chỉ khi bài toán thực sự yêu cầu ứng dụng web.

## 3. Tùy biến bằng một đối tượng SpringApplication

Giữ nguyên `settings.gradle` và `build.gradle`. **Thay toàn bộ nội dung** tệp `RuntimeApplication.java` bằng phiên bản dưới đây:

~~~java
package com.example.runtime;

import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class RuntimeApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(RuntimeApplication.class);

        application.setBannerMode(Banner.Mode.OFF);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setDefaultProperties(
                Map.<String, Object>of("app.mode", "custom-default"));
        application.setAdditionalProfiles("demo");

        application.run(args);
    }

    @Bean
    CommandLineRunner printMode(Environment environment) {
        return args -> System.out.println(
                "app.mode=" + environment.getProperty("app.mode", "basic"));
    }
}
~~~

Giải thích từng cấu hình:

| Lệnh | Tác dụng |
| --- | --- |
| `new SpringApplication(RuntimeApplication.class)` | Tạo đối tượng bootstrap với cùng nguồn cấu hình như ví dụ tĩnh. |
| `setBannerMode(Banner.Mode.OFF)` | Tắt banner ASCII của Spring Boot. Không có nghĩa là tắt toàn bộ logging. |
| `setWebApplicationType(WebApplicationType.NONE)` | Buộc khởi chạy theo kiểu non-web; không tạo embedded HTTP server ngay cả khi classpath có thư viện web. |
| `setDefaultProperties(...)` | Khai báo các property mặc định có độ ưu tiên thấp; cấu hình từ nguồn ưu tiên cao hơn, chẳng hạn đối số dòng lệnh, có thể ghi đè. |
| `setAdditionalProfiles("demo")` | Bổ sung profile `demo` vào các profile đang có, thay vì thay thế hoàn toàn chúng. |
| `application.run(args)` | Bắt đầu bootstrap bằng những thiết lập vừa cấu hình. |

Chạy lại:

~~~bash
gradle bootRun
gradle bootRun --args="--app.mode=from-cli"
~~~

Dòng do `CommandLineRunner` tự in tương ứng:

~~~text
app.mode=custom-default
~~~

và khi truyền đối số:

~~~text
app.mode=from-cli
~~~

Như vậy `setDefaultProperties` thiết lập giá trị dự phòng, còn `--app.mode=from-cli` cho thấy cấu hình dòng lệnh có thể ghi đè giá trị mặc định. Profile `demo` chỉ có tác dụng cấu hình bổ sung khi ứng dụng khai báo các bean theo profile hoặc có tệp như `application-demo.properties`.

**Lưu ý:** Để hai lệnh trên dùng đúng phiên bản nào, chỉ giữ **một** nội dung cho tệp `RuntimeApplication.java` tại một thời điểm. Hai đoạn ví dụ minh họa hai lựa chọn cho cùng một ứng dụng, không yêu cầu khởi chạy cả hai context.

## 4. Chọn run tĩnh hay đối tượng tùy biến?

| Tiêu chí | `SpringApplication.run(...)` tĩnh | `new SpringApplication(...).run(...)` |
| --- | --- | --- |
| Số bước trong `main` | Ít, dễ đọc | Nhiều bước vì có cấu hình trước khi chạy |
| Nguồn cấu hình chính | Truyền vào `run` | Truyền vào constructor |
| Tính năng Spring Boot | Bootstrap, auto-configuration, DI, runners | Cùng những tính năng đó |
| Tùy biến bằng Java trước bootstrap | Không có chỗ cấu hình một instance riêng trong lời gọi ngắn gọn | Thiết lập banner, loại ứng dụng, profile, default properties, listeners, initializers... |
| Trường hợp thường dùng | REST API hoặc service với cấu hình tiêu chuẩn | Chương trình batch/CLI, launcher riêng hoặc cấu hình khởi động đặc thù |

Việc dùng lời gọi tĩnh **không ngăn** cấu hình Spring Boot bằng `application.properties`, `application.yml`, biến môi trường hay đối số dòng lệnh. Chỉ chuyển sang dạng đối tượng khi thật sự cần điều khiển bootstrap bằng code.

Một số tùy chọn hữu ích khác trên đối tượng `SpringApplication`:

- `setLogStartupInfo(false)`: tắt các thông tin khởi động do SpringApplication ghi, nhưng không tắt mọi log ứng dụng hoặc lỗi.
- `setLazyInitialization(true)`: trì hoãn khởi tạo nhiều bean đến khi được dùng; có thể giảm thời gian startup nhưng khiến lỗi cấu hình xuất hiện muộn hơn.
- `addInitializers(...)` và `addListeners(...)`: tích hợp logic khởi tạo context và lắng nghe sự kiện phù hợp với lifecycle. Chỉ sử dụng khi có nhu cầu cụ thể và hiểu thời điểm callback được gọi.

Nếu muốn cấu hình nhiều tầng context hoặc thích cú pháp fluent, Spring Boot còn có `SpringApplicationBuilder`. Đây là một công cụ bổ sung, không phải bước bắt buộc cho hai cách khởi chạy trên.

## 5. Lỗi thường gặp và cách kiểm tra

**1. Bỏ quên args**

~~~java
SpringApplication.run(RuntimeApplication.class);
~~~

Lời gọi này có thể khởi động ứng dụng, nhưng không chuyển đối số `String[] args` từ `main`. Khi cần hỗ trợ `--spring.profiles.active=dev` hoặc các option khác do người chạy truyền vào, hãy dùng `SpringApplication.run(RuntimeApplication.class, args)` hoặc `application.run(args)`.

**2. Truyền sai tham số cho run của đối tượng**

~~~java
SpringApplication app = new SpringApplication(RuntimeApplication.class);
app.run(args); // Đúng: nguồn đã được cung cấp khi tạo app.
~~~

Không nhầm `app.run(args)` với chữ ký của phương thức `run` tĩnh.

**3. Vô tình tạo hai ApplicationContext**

~~~java
SpringApplication.run(RuntimeApplication.class, args);
new SpringApplication(RuntimeApplication.class).run(args);
~~~

Đây là **hai lần khởi động**, không phải "tăng cường" cho lần đầu. Nó có thể dẫn đến tạo bean hai lần, chạy runner hai lần hoặc tranh chấp cổng HTTP. Hãy chọn **một** trong hai cách cho một lần khởi chạy.

**4. Nghĩ rằng tắt banner là tắt log**

`Banner.Mode.OFF` chỉ tắt banner. Nếu cần điều chỉnh log, dùng cấu hình logging phù hợp. Không che lỗi khởi động chỉ để làm output ngắn.

**5. Bật non-web cho ứng dụng cần HTTP**

`WebApplicationType.NONE` phù hợp với CLI/batch. Đối với REST API dùng Spring MVC hoặc WebFlux, để Spring Boot suy luận loại ứng dụng từ classpath hoặc chọn loại tương thích; nếu đặt `NONE`, HTTP server sẽ không khởi động.

**6. Bỏ qua cơ chế ưu tiên cấu hình**

`setDefaultProperties` không khóa giá trị. Thử hai lệnh trong ví dụ để tự kiểm tra mức ưu tiên. Tránh coi default property là nguồn giữ bí mật; thông tin nhạy cảm nên nằm ở cơ chế quản lý cấu hình/secret phù hợp.

**7. Đóng context quá sớm**

Nếu giữ giá trị trả về của `run`, ví dụ `ConfigurableApplicationContext context = application.run(args)`, đừng gọi `context.close()` ngay sau đó trong ứng dụng web đang cần phục vụ request. Đóng context có chủ đích phù hợp hơn với công cụ hoặc tác vụ ngắn hạn.

## 6. Tự thực hành

1. Chạy phiên bản tĩnh; xác nhận runner in `app.mode=basic`.
2. Truyền `--app.mode=from-cli`; giải thích vì sao runner thấy giá trị mới.
3. Đổi sang phiên bản đối tượng; xác nhận banner biến mất và giá trị mặc định là `custom-default`.
4. Thử truyền `--app.mode=from-cli` cho phiên bản đối tượng; kiểm chứng rằng default property có thể bị ghi đè.
5. Nếu xây REST API về sau, bỏ `WebApplicationType.NONE` và bổ sung web starter phù hợp; kiểm tra server được khởi động bởi context web.

**Ghi nhớ:** `SpringApplication.run(Main.class, args)` là đường ngắn phổ biến; `new SpringApplication(Main.class)` + cấu hình + `run(args)` dùng khi cần quyền kiểm soát bootstrap rõ ràng. Hai cách tuân theo cùng vòng đời khởi chạy Spring Boot.

## Tài liệu tham khảo

- Spring Boot 3.3.13 Reference — SpringApplication: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 API — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
