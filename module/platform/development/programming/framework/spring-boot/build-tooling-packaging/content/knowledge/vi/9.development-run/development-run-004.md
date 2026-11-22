# Truyền Spring profile, biến môi trường và thư mục làm việc khi chạy

## 1. Mục tiêu và bối cảnh

Khi phát triển một ứng dụng Spring Boot, bạn thường chạy **cùng một mã nguồn** trong nhiều ngữ cảnh: máy cá nhân, integration environment, CI hoặc production. Những ngữ cảnh này khác nhau về database URL, cổng HTTP, logging, đường dẫn dữ liệu và dịch vụ bên ngoài. Thay vì sửa Java source mỗi lần chạy, Spring Boot cho phép cấu hình thông qua **Spring profiles**, **OS environment variables**, **JVM system properties**, **application arguments** và **các tệp cấu hình theo thư mục**.

Bài học tập trung vào việc **truyền đúng cấu hình cho tiến trình ứng dụng tại thời điểm chạy**, cả khi dùng `java -jar`, `spring-boot:run`, Gradle `bootRun` hay nút Run trong IDE. Đặc biệt, **working directory** (thư mục làm việc) ảnh hưởng cách Java và Spring Boot giải quyết đường dẫn tương đối.

Sau bài này, bạn có thể:

- Bật một hoặc nhiều Spring profiles bằng `--spring.profiles.active=...`, `SPRING_PROFILES_ACTIVE` và JVM `-Dspring.profiles.active=...`.
- Phân biệt **Spring profile**, **Maven build profile** và **Gradle project property**.
- Truyền OS env vars riêng cho Bash/zsh, Windows PowerShell, Command Prompt và cấu hình IDE.
- Truyền đúng application arguments khác với JVM options và thuộc tính của Maven/Gradle launcher.
- Chỉ định working directory thực sự của JVM ứng dụng, hiểu `user.dir`, `Path.of(".")` và file paths `file:./...`.
- Chạy ứng dụng bằng Maven/Gradle mà profile/env/working directory truyền **đến JVM fork của ứng dụng**, không chỉ JVM build tool.
- Nhận biết thứ tự ưu tiên giữa file `application.properties`, file theo profile, OS environment, Java system properties và CLI arguments.
- Kiểm tra cấu hình bằng code/log an toàn và chẩn đoán lỗi không load đúng profile/file.

**Giả định:** Java 17+, Spring Boot 3.5.x; ví dụ POM dùng Spring Boot **3.5.16** chỉ như một bản phát hành cụ thể để thực hành, không có nghĩa mọi dự án đều phải dùng đúng version này. Project thực tế cần dùng phiên bản được nhóm phát triển chấp thuận và đọc tài liệu tương ứng.

## 2. Phân biệt bốn lớp: profile, OS env, JVM và cwd

### 2.1. Spring profile

**Profile** là một nhãn ngữ cảnh như `dev`, `test`, `prod`, `local`. Khi profile `dev` đang active, Spring Boot sẽ xét các cấu hình dành cho nó, ví dụ `application-dev.properties`, và bean được gắn `@Profile("dev")` nếu có.

Ví dụ:

~~~properties
# application.properties — cấu hình chung
demo.message=base
~~~

~~~properties
# application-dev.properties — được xét khi profile dev active
demo.message=development
~~~

**Tên profile không đồng nghĩa tên môi trường bắt buộc:** `dev` hay `prod` chỉ có ý nghĩa theo file/bean và convention mà project định nghĩa. Bật `prod` không tự biến một ứng dụng thiếu cấu hình thành production-ready.

### 2.2. OS environment variable

Biến môi trường là cặp tên/giá trị thuộc môi trường của **tiến trình hệ điều hành**. Ví dụ:

~~~text
SPRING_PROFILES_ACTIVE=dev
DEMO_MESSAGE=from-env
~~~

Spring Boot dùng relaxed binding để diễn giải `SPRING_PROFILES_ACTIVE` thành `spring.profiles.active` và `DEMO_MESSAGE` thành `demo.message` khi property được đọc qua `Environment` hoặc bind với `@ConfigurationProperties`. Một biến được đặt trong shell **sau khi** tiến trình đã khởi động không tự cập nhật môi trường tiến trình Java đang chạy.

Các môi trường CI, IDE, container và process manager cũng có cơ chế khai báo env vars riêng. Đừng chỉ đặt env vars ở một terminal khác rồi kỳ vọng Java process của IDE tự nhận chúng.

### 2.3. JVM system property và application argument

**Java system property** được JVM xử lý bằng `-Dkey=value` trước tên main class hoặc `-jar`:

~~~bash
java -Dspring.profiles.active=dev -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

**Application argument** được truyền cho chương trình sau tên archive:

~~~bash
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
~~~

Trong ứng dụng gọi `SpringApplication.run(..., args)` và chưa vô hiệu hóa command-line properties, Spring Boot đọc các đối số bắt đầu bằng `--` thành cấu hình trong `Environment`. Hai cách có thể cùng kích hoạt profile, nhưng **vị trí trên command line và cơ chế ưu tiên khác nhau**.

Không viết nhầm:

~~~bash
# Sai: đặt -D phía sau -jar và đường dẫn archive; JVM không coi nó
# là system property của launcher theo cách dùng chuẩn.
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar -Dspring.profiles.active=dev
~~~

Đoạn cuối chỉ là ví dụ lỗi cú pháp truyền JVM option; Spring Boot cũng không tự coi `-Dspring.profiles.active=dev` là cấu hình ứng dụng tương đương đối số `--spring.profiles.active=dev`.

### 2.4. Working directory

**Working directory / cwd** là thư mục mà hệ điều hành gắn cho **tiến trình Java** tại thời điểm chạy. Nó ảnh hưởng các đường dẫn tương đối như:

- `Path.of("data/input.csv")` hoặc `new File("data/input.csv")`.
- Spring Boot external config tìm trong `./application.properties` và `./config/`.
- `file:./secrets/local.properties`, `file:./config/` và đường dẫn do code nội bộ quy định.
- Một số thư viện ghi logs/temp files dựa trên relative path.

Cwd **không mặc nhiên là thư mục chứa file JAR**, không nhất thiết là repository root, cũng không phải nơi chứa `pom.xml` nếu build tool/IDE đã cấu hình khác.

## 3. Bảng so sánh các cách truyền cấu hình

| Cơ chế | Ví dụ | Ai đọc? | Dùng khi |
| --- | --- | --- | --- |
| Profile qua application argument | `--spring.profiles.active=dev` | Spring Boot app | Chọn profile ở một lần chạy |
| Profile qua OS env | `SPRING_PROFILES_ACTIVE=dev` | Spring Boot app | CI, container, shell, IDE |
| Profile qua JVM system property | `-Dspring.profiles.active=dev` | JVM app → Spring Environment | Khi điều khiển JVM options |
| Cấu hình ứng dụng khác qua env | `DEMO_MESSAGE=hello` | Spring Environment/binder | Thay giá trị không sửa file |
| Cấu hình qua CLI | `--demo.message=hello` | Spring Boot command-line property source | Override tại từng invocation |
| Working directory | `cd /workspace/run` trước `java -jar ...` | OS/JVM và thư viện sử dụng relative paths | Điều khiển `./config/`, `data/` |
| Maven run profile shortcut | `-Dspring-boot.run.profiles=dev` | Maven Spring Boot Plugin → app | Khi chạy `spring-boot:run` |
| Gradle bootRun application args | `--args='--spring.profiles.active=dev'` | Gradle BootRun task → app | Khi chạy `bootRun` |

**Lưu ý tên gần giống:** `spring-boot.run.profiles` là **Maven plugin user property**, không phải Spring Environment property. `spring.profiles.active` là **Spring Boot application property**. Còn `-Pdev` của Maven chọn Maven build profile tên `dev`; nó không tự kích hoạt Spring profile `dev`.

## 4. Mô hình cấu hình theo profile và quy tắc ưu tiên

Giả sử project có ba file dưới `src/main/resources/`:

~~~text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
~~~

Nội dung:

~~~properties
# application.properties
spring.application.name=launch-context-lab
demo.message=base
~~~

~~~properties
# application-dev.properties
demo.message=development
~~~

~~~properties
# application-prod.properties
demo.message=production
~~~

Khi không có active profile nào, `demo.message` bằng `base`. Khi bật `dev`, cấu hình từ `application-dev.properties` sẽ override giá trị chung thành `development`, trừ khi một nguồn cấu hình có độ ưu tiên cao hơn override nó.

### 4.1. Thứ tự ưu tiên thường gặp

Trong một ứng dụng Spring Boot bình thường, với cùng một khóa, các nguồn dưới đây thường có ưu tiên tăng dần:

~~~text
application.properties / application-{profile}.properties
                  <
OS environment variable
                  <
Java system property (-D...)
                  <
Spring Boot command-line option (--key=value)
~~~

Ví dụ app đọc `demo.message`:

- `application-dev.properties` có `development`.
- OS env `DEMO_MESSAGE=from-env` → giá trị được app đọc là `from-env`.
- Nếu JVM app còn có `-Ddemo.message=from-jvm` → `from-jvm` thắng env.
- Nếu thêm application argument `--demo.message=from-cli` → `from-cli` thắng các nguồn ở trên.

Đây là **thứ tự rút gọn cho các nguồn minh họa**. Spring Boot còn các nguồn khác như `SPRING_APPLICATION_JSON`, servlet config, test property sources, `@DynamicPropertySource` và cấu hình devtools; ngoài ra ứng dụng có thể chủ động thay đổi cách xử lý command-line options. Khi có tranh chấp phức tạp, xem danh sách `PropertySources` thực tế thay vì áp dụng bảng trên cho mọi tình huống.

### 4.2. Nhiều profiles và default profile

Có thể bật nhiều profile:

~~~text
spring.profiles.active=dev,local
~~~

Spring Boot xét các file phù hợp như `application-dev.properties` và `application-local.properties`. Với các giá trị cùng khóa, **profile sau có thể ghi đè profile trước** theo quy tắc config data và location groups, vì vậy thứ tự `dev,local` có thể quan trọng.

Nếu **không có active profile**, Spring dùng default profile (mặc định tên `default`). File `application-default.properties` có thể được xét khi đó. Trong Java, `environment.getActiveProfiles()` có thể trả mảng rỗng dù `default` profile đang được dùng: **active profiles** và **default profiles** là hai tập khái niệm khác nhau.

### 4.3. Không đặt spring.profiles.active sai chỗ

`spring.profiles.active`, `spring.profiles.default` và `spring.profiles.group.*` **chỉ được đặt trong tài liệu cấu hình không phụ thuộc profile**. Không đưa `spring.profiles.active=prod` vào `application-dev.properties`, cũng không đặt trong một YAML document đã gắn `spring.config.activate.on-profile`. Spring Boot có thể báo lỗi cấu hình vì việc này tạo vòng tự kích hoạt không hợp lệ.

Cần thêm profile cộng dồn trong file thường? Dùng `spring.profiles.include` hoặc profile groups theo hướng dẫn chính thức. Cũng phải đặt chúng trong tài liệu không có điều kiện profile. Không mặc định ghép `spring.profiles.active` từ hai nguồn: bản ở property source ưu tiên cao hơn thường **thay thế** giá trị thấp hơn, chứ không tự cộng chuỗi.

## 5. Ví dụ Spring Boot Maven độc lập có thể chạy

Ví dụ dưới đây không yêu cầu web server hay database; ứng dụng chỉ in **active profiles, một cấu hình demo và working directory**, nên bạn có thể kiểm chứng trực tiếp trong terminal.

### 5.1. Cấu trúc project

~~~text
launch-context-lab/
├── pom.xml
├── mvnw                       # Nếu tạo bằng Spring Initializr/Maven Wrapper
├── mvnw.cmd
└── src/
    └── main/
        ├── java/com/example/launchcontext/
        │   └── LaunchContextApplication.java
        └── resources/
            ├── application.properties
            ├── application-dev.properties
            └── application-prod.properties
~~~

### 5.2. File pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>launch-context-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

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

Dùng starter parent giúp quản lý dependency/plugin versions và binding `repackage`. Dự án có corporate parent riêng có thể import Spring Boot BOM và cấu hình plugin tương đương, nhưng **đó là quyết định build riêng**, không ảnh hưởng cú pháp profile/env/working directory của ứng dụng.

### 5.3. File LaunchContextApplication.java

Tạo `src/main/java/com/example/launchcontext/LaunchContextApplication.java`:

~~~java
package com.example.launchcontext;

import java.nio.file.Path;
import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LaunchContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(LaunchContextApplication.class, args);
    }

    @Bean
    ApplicationRunner printLaunchContext(Environment environment) {
        return args -> {
            System.out.println("activeProfiles="
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("demo.message="
                    + environment.getProperty("demo.message", "<unset>"));
            System.out.println("workingDirectory="
                    + Path.of("").toAbsolutePath().normalize());
            System.out.println("exampleRelativeFile="
                    + Path.of("data", "input.txt").toAbsolutePath().normalize());
        };
    }
}
~~~

Đây là class Java 17+ hoàn chỉnh cho Maven project đã cấu hình Spring Boot starter. `@SpringBootApplication` khởi tạo context; `ApplicationRunner` chạy sau khi context đã được dựng xong. Code **không đòi hỏi file `data/input.txt` tồn tại**: chỉ in đường dẫn tuyệt đối mà đường dẫn tương đối đó sẽ được giải quyết. Vì vậy có thể thử thay cwd mà không cần chuẩn bị file.

`Environment.getActiveProfiles()` trả **danh sách active profiles**, còn `Environment.getProperty("demo.message")` trả giá trị cuối cùng theo ưu tiên các property sources. Code không đọc mật khẩu hay in toàn bộ `System.getenv()`, tránh lộ thông tin nhạy cảm.

### 5.4. Các tệp cấu hình

~~~properties
# src/main/resources/application.properties
spring.application.name=launch-context-lab
demo.message=base
~~~

~~~properties
# src/main/resources/application-dev.properties
demo.message=development
~~~

~~~properties
# src/main/resources/application-prod.properties
demo.message=production
~~~

### 5.5. Build bằng Maven

Linux/macOS, với Maven Wrapper được sinh từ Spring Initializr:

~~~bash
./mvnw clean package
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
~~~

Nếu bạn tạo project thủ công và **không có Wrapper**, thay lệnh bằng `mvn clean package` với Maven đã cài và JDK phù hợp. Cả hai cách đều cần repository access trong lần đầu khi dependencies chưa cache. Artifact executable theo POM mẫu:

~~~text
target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Từ đây các ví dụ chạy `java -jar` là chạy **JVM ứng dụng trực tiếp** (khác với chạy qua plugin). Khi dùng Spring Boot Maven Plugin để repackage, file có thể chạy bằng `java -jar`.

## 6. Chạy java -jar với Spring profile và application arguments

### 6.1. Linux/macOS — command-line arguments

~~~bash
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev
~~~

Các dòng đáng quan sát do `ApplicationRunner` in (chỉ nêu phần có thể dự đoán):

~~~text
activeProfiles=[dev]
demo.message=development
~~~

Các dòng `workingDirectory=...` và `exampleRelativeFile=...` là **đường dẫn máy đang chạy**, không có giá trị chung cho mọi môi trường. Log khởi động của Spring Boot có thể xen kẽ, không nên yêu cầu stdout toàn bộ giống hệt ví dụ.

Đặt cả một cấu hình trực tiếp từ CLI:

~~~bash
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev --demo.message=from-cli
~~~

Kết quả runner ở hai dòng liên quan:

~~~text
activeProfiles=[dev]
demo.message=from-cli
~~~

### 6.2. Windows PowerShell

~~~powershell
java -jar .\target\launch-context-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
~~~

Muốn thêm đối số thứ hai, đặt sau đường dẫn JAR:

~~~powershell
java -jar .\target\launch-context-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev --demo.message=from-cli
~~~

Tên file JAR phải đúng với artifact thực tế. Nếu Maven POM version hoặc cấu hình archive name khác, dùng tên thật trong `target/`.

### 6.3. Java system property (-D) phải đứng trước -jar

Linux/macOS:

~~~bash
java -Dspring.profiles.active=prod \
  -Ddemo.message=from-jvm \
  -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
java "-Dspring.profiles.active=prod" "-Ddemo.message=from-jvm" -jar .\target\launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Dòng runner:

~~~text
activeProfiles=[prod]
demo.message=from-jvm
~~~

Một lệnh có thể chứa cả JVM property và application arguments; khi cùng tên `demo.message`, Spring Boot CLI option `--demo.message=...` thường có ưu tiên cao hơn `-Ddemo.message=...`.

**Cần phân biệt:** `-Dspring.profiles.active=dev` đặt trước `-jar` là JVM option. `--spring.profiles.active=dev` đặt **sau** JAR là application argument mà Spring Boot xử lý.

## 7. Truyền environment variables từ terminal

### 7.1. Linux/macOS — chỉ cho một lần chạy

~~~bash
SPRING_PROFILES_ACTIVE=dev DEMO_MESSAGE=from-env \
  java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Đây là cú pháp gán biến môi trường **chỉ cho tiến trình lệnh được gọi** qua shell POSIX. Nếu ba file config ở mục 5 không bị nguồn khác override, các dòng runner là:

~~~text
activeProfiles=[dev]
demo.message=from-env
~~~

Có thể `export` để các tiến trình được shell tạo ra tiếp theo kế thừa:

~~~bash
export SPRING_PROFILES_ACTIVE=dev
export DEMO_MESSAGE=from-export
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Sau khi thực hành, tránh vô tình ảnh hưởng lệnh khác trong cùng shell:

~~~bash
unset SPRING_PROFILES_ACTIVE DEMO_MESSAGE
~~~

`export` chỉ tác động vào shell hiện tại và tiến trình con; nó **không cập nhật toàn bộ hệ thống**, các terminal đã mở khác hoặc IDE chạy từ một process khác.

### 7.2. Windows PowerShell

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DEMO_MESSAGE = "from-powershell"
java -jar .\target\launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Các process do PowerShell này khởi chạy có thể nhận biến. Xóa các biến tạm khỏi môi trường shell sau khi dùng:

~~~powershell
Remove-Item Env:\SPRING_PROFILES_ACTIVE
Remove-Item Env:\DEMO_MESSAGE
~~~

`$env:NAME` khác biến PowerShell thông thường `$NAME`. Cú pháp Unix `export NAME=value` **không chạy như vậy trong PowerShell**.

### 7.3. Windows Command Prompt (cmd.exe)

~~~bat
set SPRING_PROFILES_ACTIVE=dev
set DEMO_MESSAGE=from-cmd
java -jar target\launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Xóa biến sau khi thử:

~~~bat
set SPRING_PROFILES_ACTIVE=
set DEMO_MESSAGE=
~~~

Trong CMD, lệnh `set NAME=value` khác `setx`. `setx` lưu cho các process/terminal **tương lai** và **không cập nhật cmd.exe hiện tại**, nên không dùng nó thay cho `set` khi chỉ thử một lần chạy.

### 7.4. Mapping tên biến sang Spring property

Spring Boot relaxed binding hỗ trợ biến môi trường chuẩn hóa từ property name: thay dấu chấm bằng dấu gạch dưới, **bỏ dấu gạch nối**, rồi viết hoa. Ví dụ:

| Spring property (canonical) | OS env variable |
| --- | --- |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `demo.message` | `DEMO_MESSAGE` |
| `server.port` | `SERVER_PORT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `my.service[0].other` | `MY_SERVICE_0_OTHER` |

Không tự thêm underscore để thay mọi dấu `-` khi dùng `@ConfigurationProperties`: theo quy tắc canonical, dấu gạch nối được **bỏ đi**. Một số Spring property có aliases/biến thể riêng, nhưng nên theo quy tắc được công bố để tránh khó chẩn đoán.

### 7.5. Biến môi trường chỉ ở parent process

Mỗi process nhận một snapshot của môi trường khi nó được khởi tạo. Nếu ứng dụng đã chạy, bạn mở terminal khác rồi gõ `export SPRING_PROFILES_ACTIVE=prod` thì ứng dụng đang chạy **không tự đổi profile**. Thông thường phải dừng/khởi động lại ứng dụng. Spring profiles được xác định khi context khởi tạo, không phải nút chuyển runtime environment.

## 8. Chạy qua Maven spring-boot:run

Khi dùng Maven, `spring-boot:run` biên dịch/chạy ứng dụng trong quá trình phát triển. Spring Boot Maven Plugin có các tham số **riêng** để chuyển cấu hình đến tiến trình ứng dụng.

### 8.1. Cách chuẩn truyền profile qua Maven plugin

Linux/macOS (tại module chứa Spring Boot app):

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=dev"
~~~

**`-Dspring-boot.run.profiles=dev` là một tham số cho Maven plugin**, sau đó plugin chuyển profile vào app. Không nhầm với `-Dspring.profiles.active=dev` đặt trên dòng Maven: lệnh sau chủ yếu là system property của **Maven JVM**, không được đảm bảo truyền đúng sang JVM fork chạy ứng dụng.

Để bật nhiều profiles:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev,local
~~~

Nếu project không có `application-local.properties` vẫn có thể bật profile `local`; việc nó tác động thế nào phụ thuộc cấu hình/beans thực tế.

### 8.2. Truyền application arguments qua Maven

~~~bash
./mvnw spring-boot:run \
  "-Dspring-boot.run.arguments=--spring.profiles.active=dev --demo.message=from-maven-args"
~~~

Trong Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.arguments=--spring.profiles.active=dev --demo.message=from-maven-args"
~~~

Plugin nhận chuỗi arguments, tách theo cú pháp của nó rồi truyền cho ứng dụng. Dùng dấu nháy để phần có khoảng trắng được gửi thành **một Maven -D property**, không bị shell chia thành nhiều Maven goals. Nếu giá trị app argument có dấu cách hoặc quotes lồng nhau, thử một đối số đơn giản trước và tham khảo quy tắc quoting của plugin/shell tương ứng.

### 8.3. Truyền JVM arguments cho JVM ứng dụng

~~~bash
./mvnw spring-boot:run \
  "-Dspring-boot.run.jvmArguments=-Dspring.profiles.active=dev -Ddemo.message=from-jvm"
~~~

`spring-boot.run.jvmArguments` truyền JVM flags cho tiến trình Java mà plugin fork. Lệnh này khác với truyền `-Dspring.profiles.active` trực tiếp vào **Maven launcher**.

### 8.4. Truyền OS env vào Maven và app

~~~bash
SPRING_PROFILES_ACTIVE=dev DEMO_MESSAGE=from-env ./mvnw spring-boot:run
~~~

Maven process được tạo với các biến môi trường này và `spring-boot:run` thường fork process con kế thừa environment. Có thể khai báo env **riêng cho app** trong cấu hình plugin nếu cần đặt giá trị một cách ổn định.

Ví dụ đoạn trong `pom.xml`, đặt vào phần `<plugin>` của `spring-boot-maven-plugin`:

~~~xml
<configuration>
    <environmentVariables>
        <DEMO_MESSAGE>from-plugin-env</DEMO_MESSAGE>
    </environmentVariables>
    <workingDirectory>${project.basedir}/run-data</workingDirectory>
</configuration>
~~~

Đây là **đoạn XML**, không phải POM hoàn chỉnh. Thư mục `run-data` phải tồn tại trước khi chạy, nếu không việc khởi tạo process có thể thất bại. Config plugin có thể ghi đè env của parent process nếu cùng tên. **Không hard-code mật khẩu hoặc token vào `pom.xml`**; dùng secret management/CI injection phù hợp.

### 8.5. Đổi working directory khi dùng Maven plugin

Spring Boot Maven Plugin hỗ trợ user property `spring-boot.run.workingDirectory`. Trên Linux/macOS, ví dụ thư mục đã được tạo:

~~~bash
mkdir -p run-data
./mvnw spring-boot:run \
  "-Dspring-boot.run.workingDirectory=${PWD}/run-data"
~~~

Lưu ý: dòng trên dùng biểu thức `${PWD}` trong shell POSIX, khác với Maven property `${project.basedir}` nằm trong POM. Phần đặt trong **nháy kép** của bash/zsh sẽ được shell nội suy trước khi truyền cho Maven. Nếu cần đường dẫn tuyệt đối chắc chắn, có thể dùng `pwd` rồi truyền giá trị thực tế thay vì phụ thuộc shell environment.

Ở Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\run-data | Out-Null
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.workingDirectory=$((Resolve-Path .\run-data).Path)"
~~~

Bản thân Maven plugin đặt **workingDirectory** cho tiến trình application run. Nếu không cấu hình, theo tài liệu plugin, mặc định dùng **basedir của Maven project/module**; đó có thể khác cwd mà bạn đang đứng ở repository root của một multi-module build.

**Tách biệt quan trọng:** lệnh `cd ..` đổi current directory của shell trước khi chạy Maven; plugin có thể tiếp tục chọn module basedir làm cwd của app. Muốn nhất quán hãy dùng user property `spring-boot.run.workingDirectory` hoặc cấu hình plugin.

### 8.6. Cách dùng tương đương trong multi-module Maven

Giả sử repository có module `service` chứa Spring Boot main class:

~~~bash
./mvnw -pl service spring-boot:run -Dspring-boot.run.profiles=dev
~~~

`-pl` chọn module; project build phải có cấu hình plugin và dependencies đã sẵn sàng. Với dependencies nội bộ chưa được build/cài vào local repo, trước tiên thực thi build reactor phù hợp. Plugin run sẽ dựa vào module thực sự được chọn, không tự chạy mọi main class trong toàn repo.

## 9. Chạy qua Gradle bootRun

Spring Boot Gradle Plugin tạo task `bootRun` khi dùng Java plugin. `bootRun` kế thừa hành vi JavaExec: **application args**, **JVM system props**, **environment variables** và **workingDir** đều có thể được thiết lập cho tiến trình ứng dụng.

### 9.1. Truyền application arguments

Linux/macOS:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=dev'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun "--args=--spring.profiles.active=dev"
~~~

Thêm property khác trong cùng arguments string:

~~~bash
./gradlew bootRun \
  --args='--spring.profiles.active=dev --demo.message=from-gradle-args'
~~~

Đây là **arguments của Java ứng dụng**, không phải các option JVM của Gradle process. `--args` là cơ chế của Gradle JavaExec được Spring Boot Gradle Plugin sử dụng.

### 9.2. Truyền env variables qua terminal

Linux/macOS:

~~~bash
SPRING_PROFILES_ACTIVE=dev DEMO_MESSAGE=from-env ./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DEMO_MESSAGE = "from-env"
.\gradlew.bat bootRun
~~~

Task JavaExec mặc định dùng environment của build process, và có thể thêm/ghi đè giá trị riêng bằng `environment(...)`. Khi Gradle daemon/build tool đã chạy từ trước, vẫn phải kiểm tra môi trường thực tế mà `bootRun` nhận; nếu gặp khác biệt local/IDE/CI, thiết lập rõ trong task configuration.

### 9.3. Cấu hình Gradle Groovy DSL

Trong `build.gradle` của **module ứng dụng Spring Boot**, ví dụ:

~~~groovy
tasks.named('bootRun') {
    systemProperty 'spring.profiles.active', 'dev'
    environment 'DEMO_MESSAGE', 'from-gradle-task'
    workingDir = file('run-data')
}
~~~

Thư mục `run-data` phải tồn tại; ví dụ tạo trước bằng `mkdir -p run-data` trên Linux/macOS hoặc tạo bằng File Explorer/PowerShell trên Windows. `workingDir = file('run-data')` đặt cwd của **JVM ứng dụng**, mặc định JavaExec dùng project directory nếu không cấu hình.

### 9.4. Cấu hình Gradle Kotlin DSL

Trong `build.gradle.kts`:

~~~kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    systemProperty("spring.profiles.active", "dev")
    environment("DEMO_MESSAGE", "from-gradle-task")
    workingDir = file("run-data")
}
~~~

Đây là đoạn **Gradle build configuration**, không phải chương trình Kotlin độc lập. Bảo đảm đã áp dụng Spring Boot Gradle plugin để task `bootRun` thực sự tồn tại.

### 9.5. Gradle project property khác Spring property

Lệnh:

~~~bash
./gradlew bootRun -Pmode=dev
~~~

chỉ đặt **Gradle project property** tên `mode`. Nó **không tự** kích hoạt Spring profile. Nếu chủ động nối Gradle property vào JVM application, có thể cấu hình:

~~~groovy
tasks.named('bootRun') {
    systemProperty 'spring.profiles.active', findProperty('mode') ?: 'dev'
}
~~~

Khi đó `-Pmode=prod` mới có tác dụng thông qua cấu hình Gradle trên. Nếu task đã gán `systemProperty('spring.profiles.active','dev')` nhưng bạn truyền thêm CLI app args `--spring.profiles.active=prod`, Spring Boot command-line property source thường có ưu tiên cao hơn JVM property, nên app lấy `prod`.

### 9.6. Gradle và Maven launcher -D không tự chuyển cho app

Với lệnh build tool:

~~~bash
# Không dùng các lệnh dưới đây làm cách chuẩn để set profile app:
./gradlew bootRun -Dspring.profiles.active=dev
./mvnw spring-boot:run -Dspring.profiles.active=dev
~~~

`-D` ở vị trí này được công cụ build diễn giải như system property của **Gradle/Maven launcher**. Vì `bootRun`/`spring-boot:run` có cơ chế fork/process riêng, không nên mặc định nó tương đương `java -D... -jar ...`. Hãy dùng `--args`, task `systemProperty`, hoặc Maven plugin `spring-boot.run.profiles` / `spring-boot.run.jvmArguments`.

## 10. Chạy trong IDE: working directory, VM options, environment

Các IDE như IntelliJ IDEA, Eclipse/STS hoặc VS Code với Java/Spring extensions có giao diện cấu hình khác nhau, nhưng ý nghĩa chung của **Run Configuration** gồm:

- **Main class:** lớp `@SpringBootApplication` có `public static void main`.
- **Program arguments:** các chuỗi đưa vào `String[] args`, ví dụ `--spring.profiles.active=dev --demo.message=from-ide`.
- **VM options / JVM arguments:** ví dụ `-Dspring.profiles.active=dev -Dfile.encoding=UTF-8`.
- **Environment variables:** ví dụ `SPRING_PROFILES_ACTIVE=dev` và `DEMO_MESSAGE=from-ide-env`.
- **Working directory:** chọn thư mục project/module/run-data nơi các relative files và `./config/` được tìm kiếm.
- **Module/classpath/JDK:** phải chọn đúng module và JDK tương thích, không nhầm với Gradle/Maven import JDK hoặc IDE runtime JDK.

Điều quan trọng là mở **đúng Run Configuration của tiến trình Spring Boot**, không chỉ thiết lập Maven/Gradle Runner VM options trong IDE. Một IDE có thể chạy qua Spring Boot Run Configuration, qua Gradle task hoặc qua Maven plugin; mỗi đường chạy dùng cơ chế truyền args/env/cwd tương ứng.

### Ví dụ đối chiếu

Trong Run Configuration của ứng dụng:

~~~text
Program arguments: --spring.profiles.active=dev
VM options:        -Ddemo.message=from-ide-jvm
Environment:       DEMO_MESSAGE=from-ide-env
Working directory: /absolute/path/to/launch-context-lab/run-data
~~~

Với `application-dev.properties`, application runner sẽ in profile `[dev]` và `demo.message=from-ide-jvm` (JVM property thắng env; không có `--demo.message` để ghi đè), trong khi đường dẫn cwd chỉ đến `run-data` đã chọn. Nếu đặt `--demo.message=from-cli` trong Program arguments, giá trị đổi thành `from-cli`.

Đừng commit Run Configuration chứa secrets/plaintext credentials vào repository dùng chung. Nếu team chia sẻ run config, lưu tên biến hoặc external references; secret value nên được cấp qua cơ chế an toàn của local/CI.

## 11. Working directory và cách Spring Boot tìm config

### 11.1. Thư mục JAR khác working directory

Giả sử file thực thi nằm tại:

~~~text
/workspace/launch-context-lab/target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

Bạn tạo một thư mục chạy riêng và đặt file cấu hình ngoài JAR:

~~~text
/workspace/run-local/
├── application.properties
├── config/
│   └── application-dev.properties
└── data/
    └── input.txt
~~~

Trên Linux/macOS:

~~~bash
cd /workspace/run-local
java -jar /workspace/launch-context-lab/target/launch-context-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev
~~~

Khi đó working directory là **`/workspace/run-local`**, không phải thư mục `target` của JAR. `Path.of("data/input.txt")` được giải quyết dưới `/workspace/run-local/data`. Spring Boot có thể tìm cấu hình ngoài JAR tại `./application.properties` và `./config/application-dev.properties` theo quy tắc default config locations.

Nếu giá trị `demo.message` ở external config khác file đóng trong JAR, file external theo profile có thể override giá trị bên trong JAR, trừ nguồn ưu tiên cao hơn như OS env/JVM/CLI.

**Lưu ý:** trên Windows không dùng nguyên đường dẫn POSIX ở ví dụ; hãy dùng đường dẫn thư mục Windows thật và quote nếu có dấu cách.

### 11.2. Cách Java xác nhận cwd

Java API:

~~~java
Path workDir = Path.of("").toAbsolutePath().normalize();
System.out.println(workDir);
~~~

Đây là **đoạn Java nằm trong class/method** (không phải file Java đầy đủ độc lập); class mẫu ở mục 5 đã có code hoàn chỉnh. `System.getProperty("user.dir")` thường phản ánh directory của JVM khi khởi tạo, nhưng **không dùng `-Duser.dir=...` để thay thế hành động đổi cwd thực sự của tiến trình**. Thay working directory qua shell `cd`, IDE Run Configuration hoặc option/task build tool tương ứng.

`classpath:application.properties` lại là tài nguyên trên Java classpath (thường bên trong JAR), không phải đường dẫn filesystem tương đối theo cwd. Đừng nhầm `classpath:...` với `file:./...`.

### 11.3. Các vị trí tìm kiếm cấu hình mặc định

Spring Boot tìm `application.properties`/`application.yaml` ở một số vị trí classpath và filesystem, trong đó có:

- Classpath root và `classpath:/config/`.
- Current working directory `./`.
- Thư mục `./config/`.
- Các thư mục con trực tiếp dưới `./config/` (wildcard locations) theo quy tắc config data.

Khi một profile được bật, Spring Boot còn xét biến thể `application-{profile}.properties`/`.yaml`. **External profile-specific config có thể override packaged base config**; thứ tự cụ thể còn phụ thuộc location groups và nhiều config sources. Không phỏng đoán chỉ vì “file gần JAR nhất”.

### 11.4. Chỉ định đường dẫn config ngoài

Có hai thuộc tính quan trọng, được đọc **rất sớm lúc khởi động**:

- `spring.config.location`: **thay thế** các default search locations.
- `spring.config.additional-location`: **bổ sung** locations ngoài các default locations.

Ví dụ thêm thư mục config ngoài trong Linux/macOS:

~~~bash
java -jar /absolute/path/app.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=optional:file:/workspace/run-local/custom-config/
~~~

`/absolute/path/app.jar` ở đây là **đường dẫn minh họa**, phải thay bằng artifact có thật. Dấu `/` ở cuối location dạng thư mục quan trọng để Boot ghép đúng tên `application*.properties`. Prefix `optional:` cho phép thiếu directory mà không coi là lỗi; **không dùng `optional:` nếu việc thiếu config phải làm ứng dụng fail-fast**.

Một ví dụ tương đối gắn với cwd:

~~~bash
java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar \
  --spring.config.additional-location=optional:file:./local-config/ \
  --spring.profiles.active=dev
~~~

Lệnh thứ hai giả định bạn đứng tại root có `target/...jar` và có thể có `./local-config/`. Nếu bạn đổi cwd, đường dẫn JAR và `./local-config/` đều được giải quyết lại theo cwd mới. Không sửa source code để khắc phục khi nguyên nhân chỉ là working dir.

Với env:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:./local-config/ \
  SPRING_PROFILES_ACTIVE=dev \
  java -jar target/launch-context-lab-0.0.1-SNAPSHOT.jar
~~~

**Không đưa `spring.config.location` hay `spring.config.additional-location` vào chính profile-specific file mong đợi được load nhờ nó**. Vì Boot cần xác định location sớm, hãy cấp bằng OS env, JVM system property hoặc command-line arguments lúc khởi động.

## 12. Ma trận kiểm tra kết quả cấu hình

Xét file mẫu `application.properties` và `application-dev.properties` ở mục 5, không có external config khác và command-line properties vẫn bật.

| Tình huống chạy | Active profiles | `demo.message` mà app đọc |
| --- | --- | --- |
| Không truyền profile/env | `[]` (mảng active rỗng) | `base` |
| CLI `--spring.profiles.active=dev` | `[dev]` | `development` |
| Env `SPRING_PROFILES_ACTIVE=dev` | `[dev]` | `development` |
| Env `SPRING_PROFILES_ACTIVE=dev` + `DEMO_MESSAGE=from-env` | `[dev]` | `from-env` |
| JVM app `-Dspring.profiles.active=prod` | `[prod]` | `production` |
| Env `DEMO_MESSAGE=from-env` + JVM app `-Ddemo.message=from-jvm` | Theo profile hiện có | `from-jvm` |
| JVM app `-Ddemo.message=from-jvm` + CLI `--demo.message=from-cli` | Theo profile hiện có | `from-cli` |
| CLI `--spring.profiles.active=dev,prod` | `[dev, prod]` | `production` khi cùng khóa và đúng điều kiện location group |

Bảng giả định ứng dụng không có property sources bổ sung/override trong test hoặc SpringApplication customization. Dòng nhiều profile minh họa quy tắc “profile sau thắng” trong trường hợp config locations thông thường. Nếu external files/`spring.config.import` được dùng, thứ tự có thể phức tạp hơn.

### 12.1. Kiểm chứng bằng code thay vì đoán

Trong ứng dụng mẫu:

~~~java
environment.getActiveProfiles();
environment.getProperty("demo.message");
Path.of("").toAbsolutePath().normalize();
~~~

là ba quan sát có giá trị để tách:
1. **Profile nào thực sự active?**
2. **Spring property nào được resolve cuối cùng?**
3. **JVM app đang chạy ở thư mục nào?**

Nếu muốn xem nguồn nào đặt một property trong môi trường phát triển, có thể bật actuator `env` endpoint một cách **có kiểm soát** và kiểm tra origin/property sources. **Không công khai actuator env endpoint hoặc log toàn bộ environment trên production**: chúng có thể chứa thông tin nhạy cảm dù một số giá trị đã được mask.

## 13. Bảo mật và vận hành an toàn

Environment variables thuận tiện nhưng **không tự bảo mật**. Giá trị có thể lộ trong log, crash reports, debugging tools, process inspection hoặc chính sách quản lý môi trường. Đặc biệt, command-line options có thể nằm trong shell history và hiển thị qua danh sách process.

Khuyến nghị:

- Dùng ví dụ phi nhạy cảm như `DEMO_MESSAGE` để học và kiểm thử.
- Dùng secret manager, credential store hoặc CI secret injection cho database passwords/API tokens, không commit chúng trong `pom.xml`, `build.gradle`, `application-prod.properties` hoặc IDE Run Configuration chia sẻ.
- Phân biệt `@Profile("prod")` với cơ chế bảo mật: profile chỉ điều kiện hóa config/beans, **không chứng minh** ứng dụng an toàn khi triển khai.
- Tránh đặt môi trường `prod` làm mặc định khi chạy local; dùng cấu hình phát triển an toàn và validate external dependencies.
- Nếu cần lưu config ngoài JAR, giới hạn quyền filesystem và bảo đảm working directory đáng tin. Đường dẫn tương đối có thể bị thay đổi khi startup script/process manager dùng cwd khác.
- Ghi profile/cwd và các property **không nhạy cảm** để debug, thay vì dump `System.getenv()` hoặc toàn bộ Spring `Environment`.

## 14. Troubleshooting: lỗi theo profile, env và working directory

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `application-dev.properties` không được load | `dev` chưa active hoặc file sai tên/path | In `getActiveProfiles()`, kiểm tra `src/main/resources` và JAR |
| Đặt `SPRING_PROFILES_ACTIVE` nhưng vẫn chạy `prod` | CLI/JVM property có độ ưu tiên cao hơn; env đặt sai process | Kiểm tra arguments, JVM options và môi trường của process app |
| Maven `-Dspring.profiles.active=dev` không có tác dụng | Đặt property lên Maven launcher, app chạy fork | Dùng `-Dspring-boot.run.profiles=dev` hoặc plugin `jvmArguments` |
| Gradle `-Dspring.profiles.active=dev` không có tác dụng | Gradle JVM != BootRun app JVM | Dùng `bootRun --args` hoặc task `systemProperty` |
| Spring profile khác Maven profile | Nhầm `mvn -Pdev` với `spring.profiles.active` | Xem Maven POM profiles và truyền Spring profile rõ ràng |
| IDE hiển thị dev nhưng terminal chạy base | Run Configuration chỉ áp dụng cho IDE | Đưa flags/env vào lệnh terminal hoặc tập trung cấu hình launch |
| IDE không thấy env vars vừa `export` | IDE khởi chạy từ process khác và không thừa hưởng shell mới | Khai báo env trong IDE Run Configuration hoặc khởi động IDE từ môi trường phù hợp |
| `FileNotFoundException` với `data/input.txt` | Cwd khác dự đoán | In `Path.of("").toAbsolutePath()`, chọn working directory đúng |
| `spring.config.location` làm biến mất config đóng trong JAR | Property này thay thế default locations | Dùng `spring.config.additional-location` nếu muốn bổ sung |
| Boot báo `ConfigDataLocationNotFoundException` | Location bắt buộc không tồn tại | Kiểm tra path/cwd; dùng `optional:` chỉ nếu được phép thiếu |
| Env `DEMO_MESSAGE` được đặt nhưng demo.message không đổi | Shell syntax sai, value bị nguồn ưu tiên cao override hoặc process khác | Kiểm tra process env, CLI/JVM property và output Spring |
| Windows lệnh `export` không chạy | Shell là PowerShell/CMD | Dùng `$env:VAR` hoặc `set VAR=value` |
| Maven/Gradle không tìm thấy module/main class | Chạy sai module/root hoặc plugin chưa cấu hình | Xác nhận working dir build, module, main class, plugin |
| Bật `dev,prod` mà value khác kỳ vọng | Nhiều profile, external locations, location groups | Kiểm tra thứ tự profiles và property-source origins |
| Đổi `SPRING_PROFILES_ACTIVE` khi app đang chạy không đổi hành vi | OS env nhận lúc process start; context đã khởi tạo | Khởi động lại tiến trình với cấu hình mới |
| `-Duser.dir=/path` không giúp tìm relative file | Không đổi OS-level cwd đáng tin cậy | Dùng `cd`, IDE working directory hoặc plugin/task workingDir |

### Quy trình chẩn đoán ngắn

**Bước 1 — Xác định đường chạy:** `java -jar`, Maven plugin, Gradle task hay IDE? Mỗi cách có cách truyền arguments/JVM options khác nhau.

**Bước 2 — Kiểm tra app thực nhận gì:** In `Environment.getActiveProfiles()`, một giá trị cấu hình mẫu và `Path.of("").toAbsolutePath()`. Không chỉ nhìn flags ở lệnh build.

**Bước 3 — Kiểm tra property sources:** Nếu giá trị sai nhưng profile đúng, rà CLI → JVM app `-D` → OS env → external config → packaged config. Chú ý `spring.config.import`, external location và nhiều profiles.

**Bước 4 — Kiểm tra filesystem:** In cwd, xác minh file có tồn tại ở đường dẫn **tính từ cwd của app**, không chỉ cwd của terminal đang mở sau đó.

**Bước 5 — So sánh local/CI:** đối chiếu JDK, version Spring Boot plugin, shell, working dir, biến môi trường, quyền đọc file và deploy conventions. Không sửa source để che một lỗi launch configuration.

## 15. Bài tập luyện tập

**Bài 1 — Profile cơ bản:** Build project mục 5 rồi chạy với `--spring.profiles.active=dev`. Xác minh `activeProfiles=[dev]` và `demo.message=development`. Đổi thành `prod`, dự đoán `demo.message=production`.

**Bài 2 — Env thắng file:** Trong Bash/PowerShell, đặt `SPRING_PROFILES_ACTIVE=dev` và `DEMO_MESSAGE=from-env` trước khi chạy JAR. Ghi lại hai dòng output; giải thích vì sao không còn `development` dù dev profile active.

**Bài 3 — So sánh JVM và CLI:** Chạy `java -Ddemo.message=from-jvm -jar ... --demo.message=from-cli`. Dự đoán giá trị cuối cùng, giải thích thứ tự ưu tiên. Nhớ rằng JVM `-D` phải đứng trước `-jar`.

**Bài 4 — Working directory:** Tạo thư mục `run-data`, chạy ứng dụng từ đó bằng **đường dẫn tuyệt đối** đến JAR. Quan sát `exampleRelativeFile` thay đổi thế nào. Chứng minh JAR path và working directory là hai điều độc lập.

**Bài 5 — Maven plugin:** Chạy `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev` tại project root. Thử `spring-boot.run.workingDirectory` rồi quan sát cwd. Không đặt system property chỉ ở Maven launcher rồi cho rằng app tự nhận.

**Bài 6 — Gradle plugin:** Trong một Spring Boot Gradle project tương đương, dùng `bootRun --args='--spring.profiles.active=dev'`. Sau đó khai báo task `environment` và `workingDir`, so sánh với chạy bằng IDE.

**Bài 7 — External config:** Tạo `run-data/config/application-dev.properties` chứa `demo.message=external-dev`, chạy JAR với cwd là `run-data`, không thêm CLI/JVM/env override cùng key. Xác minh giá trị external override packaged config. Nếu thêm `--demo.message=explicit`, xác minh CLI thắng.

## 16. Checklist trước khi chốt cấu hình chạy

- [ ] Đã chọn đúng cách chạy: JAR, Maven plugin, Gradle task hay IDE.
- [ ] Đã truyền Spring profile **cho application**, không nhầm với build tool profile/property.
- [ ] Đã đặt `-D...` ở đúng JVM (trước `-jar` nếu chạy Java trực tiếp).
- [ ] Đã dùng đúng cú pháp env cho Bash/zsh, PowerShell hoặc CMD.
- [ ] Đã xác nhận Java process thực nhận env vars; không dựa vào một terminal/IDE khác.
- [ ] Đã xác định working directory thực tế và mọi relative path quan trọng.
- [ ] Đã phân biệt `spring.config.location` (thay thế) với `spring.config.additional-location` (bổ sung).
- [ ] Đã kiểm tra thứ tự ưu tiên CLI/JVM/env/file và nhiều profiles.
- [ ] Không đưa `spring.profiles.active` vào profile-specific document.
- [ ] Không hard-code hoặc in secrets trong log/config được commit.
- [ ] Khi có lỗi, đã kiểm tra output `activeProfiles`, `demo.message` và `workingDirectory` của app.

## 17. Tài liệu chính thức

- Spring Boot 3.5 — Profiles: https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html
- Spring Boot 3.5 — Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot Maven Plugin — Running Your Application: https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html
- Spring Boot Gradle Plugin — Running Your Application: https://docs.spring.io/spring-boot/3.5/gradle-plugin/running.html
- Gradle JavaExec — workingDir, environment, args, systemProperty: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html
- Spring Boot 3.5 — Running Your Application: https://docs.spring.io/spring-boot/3.5/reference/using/running-your-application.html

**Ghi nhớ cốt lõi:** Spring profile là cấu hình **của Spring Boot application**; OS environment, JVM system properties và CLI options là **các đường truyền giá trị**; working directory là **thuộc tính của tiến trình chạy**. Khi phát triển, hãy chứng minh ứng dụng nhận profile/env/cwd nào bằng log quan sát được và hành vi thực tế, thay vì chỉ nhìn câu lệnh chạy ở Maven, Gradle hoặc IDE.