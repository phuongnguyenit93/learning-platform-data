# Đóng gói tài nguyên bên trong archive và xác định cấu hình cần cung cấp bên ngoài trong Spring Boot

## 1. Bài toán: cùng một ứng dụng, nhiều môi trường triển khai

Khi tạo **executable JAR** cho Spring Boot, hai nhóm dữ liệu rất dễ bị trộn lẫn:

- **Tài nguyên thuộc phiên bản ứng dụng:** file văn bản, mẫu thông báo, template, ảnh/logo, static assets, SQL migration, schema và một số cấu hình mặc định **không nhạy cảm**. Những file này thường được đóng trong archive để artifact đủ tự chứa và có thể tái lập.
- **Cấu hình phụ thuộc môi trường chạy:** database URL, host dịch vụ, port, active profile, feature flag vận hành, timeout theo hạ tầng, credential, private key hoặc token. Những giá trị này nên được cung cấp **bên ngoài archive** bởi môi trường triển khai hoặc hệ thống quản lý secret.

Mục tiêu tốt là **build một artifact đã kiểm thử và triển khai lại đúng artifact đó** ở dev, staging, production; chỉ thay configuration/secret theo môi trường. Đóng cứng password và host production vào executable JAR sẽ buộc build lại hoặc tạo nhiều JAR khác nhau, làm khó kiểm toán và rollback.

```text
Source repository
├── src/main/java/...
├── src/main/resources/
│   ├── application.properties        # default không nhạy cảm
│   ├── assets/banner.txt             # classpath resource
│   ├── static/welcome.txt            # static HTTP resource
│   ├── templates/...                 # nếu có template engine
│   └── db/migration/...              # migration nếu dùng Flyway
└── pom.xml / build.gradle.kts
          |
          v build
Executable Boot JAR (bất biến)
├── BOOT-INF/classes/...             # classes + resources
├── BOOT-INF/lib/...                 # runtime dependencies
└── Spring Boot loader
          |
          +----> runtime config ngoài JAR:
                  /opt/app/config/application.properties
                  environment variables / command-line args
                  ConfigMap / mounted Secret / configtree:
```

**Phân biệt hai câu hỏi:**

1. *File này là một thành phần của phiên bản phần mềm, hay là dữ liệu/secret riêng của môi trường?* → quyết định **đóng gói hay cấp ngoài**.
2. *Java và Spring Boot sẽ đọc file đó bằng cơ chế nào?* → **classpath resource** khác **file hệ thống** và khác **Spring Config Data**.

Bài thực hành dùng **Java 17 và Spring Boot 3.5.0** với Maven; sau đó có Gradle Kotlin DSL tương đương. Phiên bản này cố định để ví dụ nhất quán, không có nghĩa là Spring Boot bản mới nhất. Khi dùng phiên bản khác, đối chiếu tài liệu của bản đó.

## 2. Những loại tài nguyên thường gặp và nơi nên đặt

| Loại dữ liệu | Vị trí phát triển thường gặp | Đóng vào JAR? | Lý do |
| --- | --- | --- | --- |
| Template email HTML ổn định theo release | `src/main/resources/templates/mail/...` | Có | Gắn với mã ứng dụng và review trong Git |
| File thông báo, schema, mapping tĩnh | `src/main/resources/assets/...` | Có | Cần sẵn trên classpath ở mọi môi trường |
| Static CSS/JS/favicon cho web | `src/main/resources/static/...` | Có | Phiên bản frontend đi cùng backend |
| Flyway SQL migrations | `src/main/resources/db/migration/...` | Thường có | Đồng bộ schema migration với version ứng dụng |
| `application.properties` chứa default vô hại | `src/main/resources/application.properties` | Có | Cung cấp giá trị khởi động hợp lý |
| `application-prod.yml` **không có secret** | `src/main/resources/application-prod.yml` | Có thể | Default cho profile, vẫn cho phép override ngoài |
| Database URL/host theo môi trường | runtime file, env, secret config | Thường không | Thay theo môi trường mà không rebuild |
| API token, DB password, private key | secret manager, mounted secret | **Không** | Tránh lộ qua artifact/Git/registry/log |
| File upload của người dùng | persistent volume/object storage | Không | Dữ liệu thay đổi sau khi build |
| Log, cache, file tạm | filesystem/runtime storage | Không | Không thuộc bất biến của application build |
| Test fixture | `src/test/resources` | Không vào JAR production | Chỉ phục vụ test classpath |
| Trusted public CA certificate | classpath hay trust store được quản lý | Tùy chính sách | Public CA có thể đóng gói; private key phải bảo vệ |
| `.env` dev chứa token | local secret setup ngoài project resource | **Không** | File trong resource source set dễ bị đóng gói nhầm |

**Không mặc định mọi file `.properties` là cấu hình cần để bên ngoài.** Ví dụ `assets/mapping.properties` có thể là một data resource ổn định được đóng trong JAR. Ngược lại, file `application.properties` là cấu hình Spring có thể có cả default bên trong lẫn override bên ngoài: cùng định dạng, nhưng **nguồn và quyền ưu tiên** khác nhau.

**Không đặt secret dưới `src/main/resources/static` hoặc `public`.** Đây là vùng Spring MVC có thể phục vụ qua HTTP, nên rủi ro không chỉ nằm ở việc secret có trong JAR mà còn ở nguy cơ bị truy cập qua web.

## 3. Layout tài nguyên của Maven, Gradle và Spring Boot executable archive

### 3.1. Maven: `src/main/resources` → `target/classes`

Với Maven Java project chuẩn, tài nguyên production thường được xử lý ở phase `process-resources` bởi Maven Resources Plugin, từ:

```text
src/main/resources/application.properties
src/main/resources/assets/banner.txt
src/main/resources/static/welcome.txt
```

sang:

```text
target/classes/application.properties
target/classes/assets/banner.txt
target/classes/static/welcome.txt
```

Sau `maven-jar-plugin:jar`, những file đó nằm trong **JAR nguồn** tại root classpath. Với `spring-boot-maven-plugin:repackage`, executable Spring Boot JAR dùng bố cục:

```text
resource-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/resources/ResourceDemoApplication.class
│   │   ├── com/example/resources/InfoController.class
│   │   ├── application.properties
│   │   ├── assets/banner.txt
│   │   └── static/welcome.txt
│   └── lib/
│       ├── spring-boot-...jar
│       └── ...other-runtime-dependencies...
└── ...
```

Các dòng có `...` là sơ đồ mô tả, không phải danh sách tên JAR thực tế. **`BOOT-INF/classes` chính là classpath root của ứng dụng khi Boot Loader chạy**. Vì thế, code nên gọi resource với tên `assets/banner.txt`, **không** gọi `BOOT-INF/classes/assets/banner.txt`. Tiền tố `BOOT-INF/classes` là chi tiết packaging, được loader xử lý.

`BOOT-INF/lib` chứa nested JAR của thư viện runtime; nó không phải nơi mặc định chứa `src/main/resources` của project. Resources của dependency bên trong nested JAR vẫn có thể được classloader tìm tới theo classpath.

### 3.2. Gradle: `processResources` và `bootJar`

Với Gradle Java plugin, `src/main/resources` là resource source directory của source set `main`. Task `processResources` thường copy resource tới `build/resources/main`; task `classes` tổng hợp bytecode và resource. Spring Boot Gradle task `bootJar` lấy production classpath và dependency runtime để tạo executable archive, trong đó resources thường nằm dưới `BOOT-INF/classes`, tương tự Maven.

```text
Gradle project
  src/main/java          --> compileJava ------+
  src/main/resources     --> processResources -+--> classes --> bootJar
                                                           |
                                                           v
                                                   build/libs/app.jar
                                                   BOOT-INF/classes/*
                                                   BOOT-INF/lib/*
```

**`jar` và `bootJar` là hai task khác nhau:** `jar` của Java plugin tạo plain JAR nếu được chạy; `bootJar` tạo executable Boot archive. Dùng đúng file từ `build/libs` khi kiểm tra. Sự hiện diện của `src/main/resources` trong repository **không tự chứng minh file đã nằm trong artifact cuối**: source set tùy chỉnh, excludes, filtering và Gradle/Maven plugin configuration có thể thay đổi kết quả.

### 3.3. WAR khác JAR ở đâu?

Nếu dự án đóng gói executable WAR, classes/resources thường nằm dưới `WEB-INF/classes` và dependency dưới `WEB-INF/lib` hoặc `WEB-INF/lib-provided`, không phải `BOOT-INF/classes` như executable JAR. Ví dụ trong bài tập sử dụng `<packaging>jar</packaging>`; khi chuyển sang WAR phải đổi cả cách kiểm tra archive, không chỉ đổi extension.

## 4. Ví dụ Maven + Java 17: bundled resource và external config

Ta sẽ tạo một API có ba đặc điểm độc lập:

1. `GET /banner` đọc file **`assets/banner.txt` đóng trong JAR**.
2. `GET /values` đọc hai Spring configuration keys, cho phép **override bên ngoài**.
3. `GET /welcome.txt` được Spring MVC phục vụ từ `static/welcome.txt` nằm trong archive.

Sau đó giữ nguyên JAR và chạy hai cấu hình môi trường khác nhau để chứng minh **build một lần, cấu hình nhiều lần**.

### 4.1. Cấu trúc file

```text
resource-demo/
├── pom.xml
├── src/
│   └── main/
│       ├── java/com/example/resources/
│       │   └── ResourceDemoApplication.java
│       └── resources/
│           ├── application.properties
│           ├── assets/banner.txt
│           └── static/welcome.txt
├── runtime-config/
│   └── application.properties          # tạo để chạy, KHÔNG nằm trong resources
└── target/                              # Maven tạo
```

`runtime-config` là thư mục thử nghiệm ngoài source set chính, không được Maven tự đóng gói theo layout tiêu chuẩn. Với ứng dụng thực tế, file cấu hình runtime của staging/production có thể nằm ở `/etc/myapp` hoặc được CI/orchestrator mount, không nhất thiết tồn tại trong Git repository.

### 4.2. File `pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>resource-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>resource-demo</name>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

`spring-boot-starter-parent` quản lý version của starter, cấu hình compiler tương thích Java 17 và thiết lập execution `spring-boot:repackage`. Vì vậy `mvn clean package` sẽ đóng gói executable JAR mà không cần thêm execution mới. Không cần thêm plugin riêng cho mỗi resource đơn giản.

### 4.3. Java source hoàn chỉnh

**`src/main/java/com/example/resources/ResourceDemoApplication.java`:**

```java
package com.example.resources;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ResourceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceDemoApplication.class, args);
    }
}

@RestController
class InfoController {

    private final Environment environment;

    InfoController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/values")
    public String values() {
        String message = environment.getProperty("demo.message", "missing");
        String region = environment.getProperty("demo.region", "missing");
        return "message=" + message + ";region=" + region;
    }

    @GetMapping("/banner")
    public String banner() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("assets/banner.txt");

        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }
    }
}
```

Hai class cùng nằm trong một file Java: chỉ `ResourceDemoApplication` là `public`, còn `InfoController` là package-private nên hợp lệ trong Java 17. Spring Boot component scan bắt đầu từ package `com.example.resources` và tự phát hiện `InfoController`. `Environment` đọc cấu hình Spring theo precedence; `ClassPathResource` mở file *được đóng trong archive* bằng stream, nên chạy được cả từ IDE và executable JAR.

Nếu `assets/banner.txt` không có, `getInputStream()` có thể ném exception và `/banner` lỗi; đó là tín hiệu cho thấy **resource không được đóng gói đúng**, không phải mặc định Spring tự tạo file.

### 4.4. Ba file resource production

**`src/main/resources/application.properties`:**

```properties
spring.application.name=resource-demo
server.port=8080
demo.message=packaged
demo.region=local
```

**`src/main/resources/assets/banner.txt`:**

```text
BANNER_FROM_ARCHIVE
```

**`src/main/resources/static/welcome.txt`:**

```text
STATIC_OK
```

Các giá trị trong `application.properties` chỉ là default không nhạy cảm. `assets/banner.txt` là resource nội bộ được truy cập qua Java code; `static/welcome.txt` được Spring MVC tự phục vụ qua URL `/welcome.txt`. Nếu ứng dụng dùng servlet context path hoặc Spring MVC static-path-pattern khác, URL có thể thay đổi.

### 4.5. Build và chạy executable archive

Từ thư mục root chứa `pom.xml`:

```bash
java -version
mvn -version
mvn -B -ntp clean package
java -jar target/resource-demo-0.0.1-SNAPSHOT.jar
```

- Java 17 hoặc mới hơn được hỗ trợ bởi Spring Boot 3.5.0.
- `-B` chạy Maven batch, `-ntp` tắt log tiến độ download.
- `clean` xóa output cũ; `package` compile, test nếu có và repackage bằng Boot Maven Plugin.
- Nếu repository có Maven Wrapper, dùng `./mvnw -B -ntp clean package` hoặc `mvnw.cmd` trên Windows.

Khi ứng dụng đã chạy ở port 8080, mở terminal khác:

```bash
curl -fsS http://localhost:8080/values
curl -fsS http://localhost:8080/banner
curl -fsS http://localhost:8080/welcome.txt
```

**Response body chính xác theo từng request:**

| Request | Body |
| --- | --- |
| `GET /values` | `message=packaged;region=local` |
| `GET /banner` | `BANNER_FROM_ARCHIVE` |
| `GET /welcome.txt` | `STATIC_OK` |

File text trong ví dụ có thể có newline cuối file; code `/banner` dùng `strip()` nên body không có newline, còn static resource `/welcome.txt` thường giữ nguyên bytes của file. Lệnh `curl` không tự thêm newline. Dừng server bằng Ctrl+C trước khi chạy phiên cấu hình khác.

## 5. Inspect archive: chứng minh file nào thực sự đã được đóng gói

Sau khi build, kiểm tra:

```bash
jar tf target/resource-demo-0.0.1-SNAPSHOT.jar
```

Những entry quan trọng kỳ vọng:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/application.properties
BOOT-INF/classes/assets/banner.txt
BOOT-INF/classes/static/welcome.txt
BOOT-INF/classes/com/example/resources/ResourceDemoApplication.class
BOOT-INF/classes/com/example/resources/InfoController.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
```

Dấu `...` biểu diễn nhiều file runtime, không phải một entry literal. Lệnh lọc hữu ích trên Bash:

```bash
jar tf target/resource-demo-0.0.1-SNAPSHOT.jar |
  grep -E '^BOOT-INF/classes/(application.properties|assets/banner.txt|static/welcome.txt)$'
```

Kỳ vọng đúng ba đường dẫn:

```text
BOOT-INF/classes/application.properties
BOOT-INF/classes/assets/banner.txt
BOOT-INF/classes/static/welcome.txt
```

Trên Windows PowerShell dùng:

```powershell
jar tf target/resource-demo-0.0.1-SNAPSHOT.jar |
  Select-String '^BOOT-INF/classes/(application.properties|assets/banner.txt|static/welcome.txt)$'
```

**Khác biệt giữa xem file và xem classpath:** đường dẫn `BOOT-INF/classes/assets/banner.txt` trong ZIP không phải tên mà `new ClassPathResource(...)` nhận. Trong Java code, dùng `assets/banner.txt`. Spring Boot loader xây classpath tương ứng khi chạy executable JAR.

Nếu không có entry:
- Kiểm tra đúng vị trí `src/main/resources`, không phải `src/resources` hoặc `src/main/java/resources`.
- Kiểm tra `pom.xml` có source set/resource exclusion tùy chỉnh không.
- Kiểm tra lệnh đã build **đúng module** Maven/Gradle hay đang xem plain JAR.
- Chạy build sạch để loại output cũ, nhưng đừng xóa cache dependency toàn cục nếu lỗi là cấu hình resource path.

## 6. Cung cấp external application.properties mà không sửa JAR

Giữ nguyên `target/resource-demo-0.0.1-SNAPSHOT.jar` đã build. Tạo file **`runtime-config/application.properties`** trong project root:

```properties
server.port=9090
demo.message=external
demo.region=staging
```

Chạy từ project root:

```bash
java -jar target/resource-demo-0.0.1-SNAPSHOT.jar \
  --spring.config.additional-location=optional:file:./runtime-config/
```

**Điều kiện:**
- Đường dẫn tương đối `./runtime-config/` được giải quyết theo **current working directory của tiến trình Java**, không theo thư mục file JAR.
- Dấu `/` cuối quan trọng vì đây là **directory location**. Spring Boot sẽ tìm `application.properties`/`application.yml` và biến thể profile trong thư mục đó.
- `optional:` nghĩa là **thiếu thư mục/file không tự làm startup thất bại**. Với cấu hình/secrets bắt buộc của production, cân nhắc bỏ `optional:` để fail fast.
- `spring.config.additional-location` thêm nguồn mới vào các vị trí tìm config mặc định, cho phép external values ghi đè default đóng trong archive.

Khi server chạy port 9090:

```bash
curl -fsS http://localhost:9090/values
curl -fsS http://localhost:9090/banner
curl -fsS http://localhost:9090/welcome.txt
```

Response tương ứng:

| Endpoint | Body |
| --- | --- |
| `/values` | `message=external;region=staging` |
| `/banner` | `BANNER_FROM_ARCHIVE` |
| `/welcome.txt` | `STATIC_OK` |

**Kết luận từ ví dụ:** thay `demo.message`, `demo.region` và `server.port` **không thay đổi nội dung JAR**. Resource `banner.txt` và static file vẫn giống hệt vì là thành phần ứng dụng. Cùng một binary hoạt động ở môi trường khác nhờ runtime configuration.

### 6.1. Nguồn external config được Spring Boot tự tìm

Spring Boot còn có những vị trí config data mặc định, theo thứ tự khái quát:

- Classpath root: `classpath:/application.properties` hoặc YAML tương ứng.
- Classpath thư mục `/config`.
- Working directory của JVM: `file:./application.properties`.
- `file:./config/application.properties` và các thư mục con trực tiếp theo pattern mặc định.

File `./runtime-config/application.properties` trong ví dụ **không** thuộc những vị trí mặc định, nên dùng `spring.config.additional-location` tường minh. Ngược lại, nếu đặt một file `application.properties` cạnh JAR nhưng JVM được launch từ thư mục khác, nó có thể **không** được tìm thấy; hãy kiểm tra `user.dir`, systemd `WorkingDirectory` và working directory của container.

**`application.properties` bên ngoài thường có quyền ưu tiên cao hơn default trong JAR**, theo cơ chế Config Data. Tuy nhiên, Java system properties, biến môi trường OS và command-line args lại có thứ tự ưu tiên riêng; đừng xem external file luôn thắng mọi nguồn khác.

## 7. `spring.config.location`, `spring.config.additional-location` và `spring.config.import`

Ba khóa cùng xuất hiện trong bài toán nhưng có ý nghĩa khác nhau:

| Khóa | Chức năng | Rủi ro nếu dùng nhầm |
| --- | --- | --- |
| `spring.config.location` | **Thay thế các default search locations** bằng danh sách location mới | Làm biến mất default `application.properties` trong JAR khỏi config data được xét |
| `spring.config.additional-location` | **Bổ sung** location vào các default location, giá trị bổ sung có thể override | Nhầm working directory, thiếu file, xung đột precedence |
| `spring.config.import` | Nhập tài liệu config khác từ cấu hình được tải, hỗ trợ `file:`, `classpath:`, `configtree:` | Khai báo location bắt buộc không tồn tại gây startup fail; import nhầm path |

**Ví dụ chỉ bổ sung config bên ngoài:**

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/etc/resource-demo/
```

**Ví dụ thay toàn bộ các default locations:**

```bash
java -jar app.jar \
  --spring.config.location=file:/etc/resource-demo/application.properties
```

Với `spring.config.location`, không còn mặc định rằng mọi giá trị `application.properties` đóng trong JAR sẽ tiếp tục được đọc. Nếu external file chỉ chứa một phần khóa, các khóa default không được tìm nữa có thể thành `missing` hoặc nhận default khác. Với nhu cầu “thêm override bên ngoài nhưng vẫn giữ default trong archive”, **ưu tiên `spring.config.additional-location`**.

**Ví dụ import thêm config từ file hiện có:**

```properties
# Có thể đặt trong application.properties được Spring Boot đọc
spring.config.import=optional:file:./runtime-config/feature-flags.properties
```

`optional:` bỏ lỗi thiếu file location; không nên dùng cho cấu hình bắt buộc. `spring.config.location` và `spring.config.additional-location` được đọc **rất sớm** để tìm config, nên nên truyền qua environment, JVM system property **trước `-jar`**, hoặc application CLI argument **sau `-jar`**; không dựa vào một file mà Spring chưa biết đường để tìm nó.

### 7.1. Nguồn cấu hình có ưu tiên nào?

Trong tình huống Spring Boot runtime điển hình, xét cùng key `demo.message`:

```text
--demo.message=cli              (application command-line argument)
          >
-Ddemo.message=jvm              (Java system property của app JVM)
          >
DEMO_MESSAGE=env                (OS environment variable)
          >
runtime-config/application.properties
          >
classpath:/application.properties
```

Sơ đồ này **lược bỏ các PropertySources khác**: `SPRING_APPLICATION_JSON`, test properties, JNDI, DevTools settings, programmatic defaults, `@PropertySource`. Khi phân tích sự cố, kiểm tra bảng precedence chính thức theo version, không dùng sơ đồ rút gọn làm luật cho tất cả trường hợp.

Ví dụ trên Linux/macOS, với external file ở mục 6:

```bash
DEMO_MESSAGE=from-env java \
  -jar target/resource-demo-0.0.1-SNAPSHOT.jar \
  --spring.config.additional-location=optional:file:./runtime-config/
```

Endpoint `/values` ở port 9090 sẽ trả:

```text
message=from-env;region=staging
```

Nếu lại thêm `--demo.message=from-cli` vào cuối lệnh, message thành `from-cli`. Nếu dùng JVM property `-Ddemo.message=from-jvm`, phải đặt **trước `-jar`**. Tất cả ví dụ đều chạy **mỗi lần một JVM**, dừng phiên cũ để tránh port conflict.

### 7.2. Profile-specific files

Mỗi môi trường có thể chọn profile:

```bash
java -jar target/resource-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=staging \
  --spring.config.additional-location=optional:file:./runtime-config/
```

Khi profile `staging` được active, Spring Boot còn xét `application-staging.properties` / `application-staging.yml` trong các location phù hợp. Profile-specific config thường override non-profile config theo quy tắc Config Data. **Không tự gán mặc định `spring.profiles.active=prod` trong file profile-specific**; activation nên do runtime/CLI/env quyết định. Tránh các tổ hợp profile phức tạp không có test vì thứ tự location group/profiles có thể ảnh hưởng kết quả.

### 7.3. Đặt tên external file rõ ràng

Nếu tổ chức không dùng tên `application.properties`, ví dụ `company.properties`, có thể truyền `--spring.config.name=company` hoặc location trỏ **đúng file**. Nhưng khi đổi config name, hành vi tìm file default thay đổi; cần test đầy đủ. Đối với một service có cấu hình tách dev/prod, file `application-{profile}.properties` hoặc `spring.config.import` thường dễ theo dõi hơn việc sửa `spring.config.name` không cần thiết.

## 8. Secrets: tại sao phải cấp ngoài archive?

Archive JAR là file ZIP có thể đọc/giải nén dễ dàng. Nếu file `src/main/resources/application.properties` chứa:

```properties
# Ví dụ PHẢI TRÁNH: không lưu password thật trong resource
spring.datasource.password=hardcoded-password
```

thì password sẽ nằm trong `BOOT-INF/classes/application.properties` của artifact, có thể lan qua Git history, CI artifact store, registry, backup hoặc máy nhận JAR. Ngay cả khi repository source private, điều đó không thay thế secret management.

**Thực hành khuyến nghị:**

- Trong `application.properties` đóng gói, chỉ dùng default không nhạy cảm và tên khóa cần thiết.
- Với giá trị bắt buộc, dùng Spring placeholder không có fallback vô hại làm che thiếu secret, ví dụ `spring.datasource.password=${DB_PASSWORD}` khi triển khai thực sự sử dụng datasource.
- Nếu secret manager cấp environment variable, xác nhận nó chỉ vào **process ứng dụng** và không bị echo trên log.
- Với Kubernetes/Docker, cân nhắc **volume-mounted secrets** và `configtree:` để tránh truyền giá trị secret qua CLI/args hiển thị trong process listing.
- Dùng quyền đọc tối thiểu, rotation, tránh ghi secret trong startup log, exception hoặc Actuator `/env` và `/configprops` output.
- Nếu secret đã từng vào Git hoặc artifact store, phải đánh giá lộ lọt và **xoay vòng**; xóa một file ở commit sau không làm secret biến mất khỏi lịch sử.
- Có thể dùng encryption-at-rest và secret store theo tổ chức, nhưng việc mã hóa không có nghĩa app không thể truy cập secret sau giải mã.

### 8.1. Configuration tree: một file là một property

Spring Boot Config Data hỗ trợ `configtree:`. Giả sử hệ thống mount:

```text
/run/secrets/
├── demo.api-key            # nội dung: secret thực tế, không đưa vào bài
└── demo.partner-token      # nội dung: secret thực tế, không đưa vào bài
```

Bên trong **external `application.properties`** của môi trường đó:

```properties
spring.config.import=configtree:/run/secrets/
```

Spring Boot đưa tên file thành khóa, ví dụ `demo.api-key` hoặc `demo.partner-token`. Giá trị file được đọc theo cơ chế config tree; app có thể inject qua `Environment` hoặc `@ConfigurationProperties`. Nếu mount không tồn tại và không có `optional:`, startup fail, thường đúng với secret bắt buộc. Với local dev mà secret chỉ tùy chọn, có thể dùng `optional:configtree:/run/secrets/`.

**Chú ý:** ConfigMap và Secret trong Kubernetes có thể được mount dạng file hoặc đưa vào environment variable. `configtree:` là cơ chế **đọc file** chứ không phải cơ chế mã hóa dữ liệu. Quyền truy cập Kubernetes RBAC, volume permissions và secret lifecycle vẫn phải được tổ chức quản lý.

### 8.2. Không dùng `src/main/resources` cho dữ liệu phát sinh sau deployment

File upload, chứng từ, log, report và ảnh người dùng phải nằm trong durable storage (object storage, database, persistent volume). Application JAR **không phải thư mục ghi có thể cập nhật**. Khi chạy `java -jar`, resource nằm trong ZIP; lệnh ghi `FileOutputStream` vào `BOOT-INF/classes/...` không phải thao tác filesystem thông thường và có thể fail/không có ý nghĩa.

Nếu cần đọc mẫu mặc định và ghi một bản copy do người dùng chỉnh sửa, hãy:

1. Mở **classpath resource** bằng `getInputStream()`.
2. Copy bytes sang thư mục dữ liệu bên ngoài đã cấu hình, có quyền ghi.
3. Từ đó đọc/ghi **file ngoài archive** như dữ liệu runtime; không thay JAR.
4. Định nghĩa chiến lược migrate/backup và phân quyền file phù hợp.

## 9. Đọc classpath resource đúng cách trong Java 17+

### 9.1. Dùng InputStream thay cho File

Ví dụ ở mục 4 sử dụng:

```java
new ClassPathResource("assets/banner.txt").getInputStream()
```

Đây là cách đọc khi resource được đóng trong executable JAR hoặc nằm trên classpath khi chạy IDE.

**Không làm vậy một cách mặc định:**

```java
File file = new ClassPathResource("assets/banner.txt").getFile();
```

`getFile()` chỉ dùng được khi resource thực sự có dạng file trên filesystem. Trong executable JAR, resource nằm **trong archive**, không phải một file vật lý riêng; lời gọi có thể ném exception. Tương tự:

```java
Path path = Paths.get(
    getClass().getResource("/assets/banner.txt").toURI()
);
```

không phải cách dùng portable với nested Boot JAR; URI có thể dùng scheme `jar:` hoặc cơ chế loader khác, không chuyển được thành `Path` của default filesystem provider như khi chạy IDE.

**Cách Java thuần không cần Spring resource abstraction:**

```java
try (InputStream stream =
        ResourceDemoApplication.class.getResourceAsStream(
                "/assets/banner.txt")) {
    if (stream == null) {
        throw new IllegalStateException("Missing assets/banner.txt");
    }
    String data = new String(stream.readAllBytes(),
            StandardCharsets.UTF_8);
    System.out.println(data.strip());
}
```

Đây là **đoạn Java bên trong class/method đã có import** `InputStream` và `StandardCharsets` như ở mục 4, không phải chương trình `.java` độc lập. Nó cho thấy cách resource được tìm bằng classpath; dùng `getResourceAsStream` hoặc Spring `Resource` đều phù hợp.

### 9.2. Khi resource cần là file ngoài

Đọc file ngoài filesystem bằng `FileSystemResource` hoặc Java NIO:

```java
Path external = Path.of("/etc/resource-demo/policy.json");
String policy = Files.readString(external, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa cần import `java.nio.file.Path`, `Files` và `StandardCharsets`, cũng cần đường dẫn thật cùng quyền đọc. Đừng gán một đường dẫn file tuyệt đối là portable giữa Windows, container và VM. Với cấu hình đơn giản dạng properties/YAML, **để Spring Config Data tự nạp** thay vì tự viết parser Java; với tài liệu dữ liệu khác, đọc qua filesystem API thích hợp.

### 9.3. Template và static content

- `src/main/resources/templates` chứa template được xử lý bởi engine đã cấu hình (Thymeleaf, FreeMarker...), **không tự phục vụ file nguyên văn** nếu không có engine/controller phù hợp.
- `src/main/resources/static`, `public`, `resources` hoặc `META-INF/resources` là các vị trí Spring Boot thường phục vụ **static HTTP content**. File `static/welcome.txt` ở demo được truy cập như `/welcome.txt`.
- `src/main/resources/assets` là thư mục thông thường trong classpath. Nó **không tự trở thành URL `/assets/...`** trừ khi map resource handlers hoặc viết controller.
- `src/test/resources` phục vụ unit/integration tests, được đưa vào **test classpath**, không phải executable production JAR theo build chuẩn.

Không đưa secret, file nội bộ cần bảo vệ hoặc backup của user vào các static resource directories. Static files có thể được truy cập mà không qua endpoint controller tùy cấu hình bảo mật của ứng dụng.

## 10. Maven resource filtering: chỉ biến đổi file có chủ đích

**Resource filtering** là thay placeholder bằng thông tin build tại phase `process-resources`. Đây là việc khác với **runtime Spring Environment**.

Khi dùng `spring-boot-starter-parent`, Spring Boot cấu hình cách filter `application.properties`/`application.yml` thích hợp, thường dùng cú pháp `@..@` để tránh xung đột với placeholder runtime `${...}` của Spring.

Ví dụ thêm vào **`src/main/resources/application.properties`**:

```properties
app.build-version=@project.version@
app.runtime-host=${SERVICE_HOST:localhost}
```

Sau `mvn clean package` với POM mẫu:

- `@project.version@` được Maven Resources Plugin filter thành `0.0.1-SNAPSHOT` trong resource đã xử lý.
- `${SERVICE_HOST:localhost}` là **Spring property placeholder**: Spring giải quyết từ environment lúc ứng dụng chạy; Maven starter-parent convention dùng `@...@` để tránh thay nhầm chuỗi đó.

Đây là giá trị build-time **không nhạy cảm** nên có thể nhúng trong JAR; `SERVICE_HOST` là runtime configuration. Nếu muốn CI ghi build number, Git revision hay timestamp vào artifact, phải có chiến lược kiểm chứng và reproducible build; không nhúng secret hoặc thời gian thay đổi không kiểm soát vào mọi resource.

### 10.1. Khi project không dùng Spring Boot starter parent

Nếu chỉ import Spring Boot BOM mà không kế thừa starter parent, cấu hình filtering, plugin goals và resource processing không nhất thiết được thêm tự động. Cần khai báo Maven Resources Plugin và `<resources>` với delimiter, version phù hợp với corporate parent và quy tắc build. Ví dụ **đoạn trong POM**, chưa phải POM hoàn chỉnh:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-resources-plugin</artifactId>
            <version>3.3.1</version>
            <configuration>
                <delimiters>
                    <delimiter>@</delimiter>
                </delimiters>
                <useDefaultDelimiters>false</useDefaultDelimiters>
            </configuration>
        </plugin>
    </plugins>
</build>
```

**Quan trọng:** áp dụng `<filtering>true</filtering>` cho **toàn bộ** `src/main/resources` như trên có thể không phù hợp khi chứa image, font, certificate, PDF hoặc file binary. Maven Resources Plugin có danh sách loại binary/non-filtered extensions mặc định và tùy chỉnh, nhưng an toàn nhất là **phân tách filtered text resources và non-filtered binary resources bằng `<resource>`/`<includes>`** theo thiết kế dự án. Không dùng ví dụ này nguyên trạng nếu resource directory có file binary cần giữ byte-for-byte.

Với starter parent đã có convention filtering, **không tự thêm lại block `<resources>` chung** nếu không có nhu cầu. Override có thể vô tình làm mất cấu hình lọc của parent. Kiểm tra `mvn help:effective-pom` và output thực tế `target/classes` khi tùy chỉnh.

### 10.2. Không nhầm Maven filtering với Spring placeholder

| Cú pháp | Thời điểm thay | Ví dụ |
| --- | --- | --- |
| `@project.version@` | Maven `process-resources` nếu filtering bật | Version artifact, build metadata |
| `${SERVICE_HOST:localhost}` | Spring Boot runtime property resolution | Host theo môi trường |
| `--server.port=9090` | Spring Boot runtime CLI property | Port theo môi trường |
| `SPRING_PROFILES_ACTIVE=prod` | Environment của process ứng dụng | Chọn profile |
| `-Ddemo.region=prod` trước `-jar` | Java system property của app JVM | Override runtime |

Khi Maven build log báo filter chưa thay placeholder, kiểm tra file thuộc resource filter set nào, có dùng starter parent hay không, cú pháp delimiter và lệnh `mvn process-resources`. Khi Spring Boot đọc placeholder bị lỗi vì thiếu environment, đó là **runtime configuration**, không nên sửa bằng cách filter secret ngay vào JAR.

## 11. Gradle Kotlin DSL: build cùng cấu trúc tài nguyên

Nếu project dùng Gradle thay Maven, giữ nguyên Java source và `src/main/resources` ở mục 4; thay `pom.xml` bằng hai file:

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "resource-demo"
```

**`build.gradle.kts`:**

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

Dùng Gradle Wrapper tương thích với Spring Boot plugin, từ project root:

```bash
./gradlew clean bootJar
java -jar build/libs/resource-demo-0.0.1-SNAPSHOT.jar
```

Trên Windows dùng `gradlew.bat`. Nếu repo chưa có wrapper, tạo bằng bản Gradle phù hợp và version được project kiểm soát. `bootJar` tạo executable JAR; path `build/libs` phụ thuộc tên project, version và archive customizations. `processResources` copy `src/main/resources` vào `build/resources/main` rồi được đưa vào archive trong `BOOT-INF/classes`.

### 11.1. Chỉ filter file text riêng thay vì toàn bộ resources

Giả sử muốn có build metadata độc lập ở file:

**`src/main/resources/build-info.properties`:**

```properties
app.build.version=${buildVersion}
```

Đây là **placeholder của Gradle template expansion**, không phải Spring runtime property. Trong `build.gradle.kts`, thêm:

```kotlin
import org.gradle.language.jvm.tasks.ProcessResources

val buildVersionForResources = version.toString()

tasks.named<ProcessResources>("processResources") {
    filesMatching("build-info.properties") {
        expand(mapOf("buildVersion" to buildVersionForResources))
    }
}
```

Sau `./gradlew processResources`, `build/resources/main/build-info.properties` chứa:

```properties
app.build.version=0.0.1-SNAPSHOT
```

Dùng `filesMatching("build-info.properties")` để tránh áp dụng template engine lên các file binary hoặc `application.properties` có Spring placeholder `${...}`. Phương thức `expand` của Gradle dựa trên template expansion và có thể xử lý `${name}`, **dễ xung đột với Spring property placeholders** nếu áp dụng tràn lan. Không sử dụng `expand(project.properties)` trên tất cả resources khi bạn muốn giữ mọi runtime placeholder nguyên bản.

Nếu project có custom resource source directories, cấu hình `sourceSets.main.resources` theo Gradle Java plugin, rồi kiểm tra output thực tế. Không dùng `from("src/main/resources")` thêm lần nữa vào `bootJar` khi `processResources` đã bao gồm chúng, vì có thể gây duplicate paths hoặc phá quy tắc packaging.

## 12. Docker: cùng image, khác mounted config

Mô hình container tốt thường là: build JAR đã test → copy JAR vào image → cấu hình môi trường qua env/volume/secret của deployment.

**Dockerfile** cho Maven artifact mẫu:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/resource-demo-0.0.1-SNAPSHOT.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Build:

```bash
mvn -B -ntp clean package
docker build -t resource-demo:dev .
```

Chạy image với **chính `runtime-config/application.properties`** của mục 6 được mount chỉ đọc:

```bash
docker run --rm \
  -p 127.0.0.1:9090:9090 \
  -v "$PWD/runtime-config:/config:ro" \
  resource-demo:dev \
  --spring.config.additional-location=optional:file:/config/
```

Lệnh trên áp dụng cho Bash/Linux/macOS với Docker có quyền bind mount thư mục project. Trên Windows PowerShell, điều chỉnh đường dẫn host và cách nối dòng. Trong container, **working directory là `/app`**, còn file ngoài JAR được mount tại **`/config/application.properties`**. Option `--spring.config.additional-location=...` là argument gửi vào Spring application **sau** executable image entrypoint, không thay JAR.

Sau khi chạy, `curl -fsS http://localhost:9090/values` cho response:

```text
message=external;region=staging
```

Vì `-p 127.0.0.1:9090:9090` chỉ publish loopback trên host cho bài tập dev, máy khác không tự truy cập được port này. Production deployment cần network/routing policy riêng, không copy host-binding của ví dụ như mặc định.

**Cần lưu ý:** Dockerfile `EXPOSE 8080` chỉ là metadata; nó không ép Spring Boot phải nghe 8080. External file đổi `server.port=9090`, vì vậy Docker `-p` map vào **container port 9090** mới đúng. Không cần rebuild image chỉ vì đổi port, miễn là routing container được cập nhật.

Nếu image không cần mount thêm file, có thể chạy cùng JAR với runtime env:

```bash
docker run --rm \
  -p 127.0.0.1:8080:8080 \
  -e DEMO_MESSAGE=container \
  resource-demo:dev
```

Khi `demo.region` vẫn là `local` trong packaged config, `/values` sẽ trả `message=container;region=local`. Để chạy production, các giá trị như token/DB password phải đến từ cơ chế secret phù hợp, không nhúng bằng lệnh `docker build --build-arg` để ghi vào artifact.

## 13. Kubernetes: ConfigMap, Secret và Config Data

Kubernetes có hai nhóm dữ liệu phù hợp với nguyên tắc trong bài:

- **ConfigMap:** cấu hình không nhạy cảm; có thể mount file `application.properties` vào container hoặc inject environment values.
- **Secret:** giá trị nhạy cảm (không xem đối tượng Secret tự nó là giải pháp bảo mật hoàn chỉnh); thường mount file có quyền đọc được kiểm soát, hoặc inject env theo chính sách.

Một ví dụ **đoạn trong Kubernetes Deployment**, không phải YAML Deployment độc lập:

```yaml
containers:
  - name: app
    image: registry.example.org/resource-demo:release-1
    args:
      - "--spring.config.additional-location=file:/config/"
    volumeMounts:
      - name: app-config
        mountPath: /config
        readOnly: true
      - name: app-secret
        mountPath: /run/secrets
        readOnly: true
volumes:
  - name: app-config
    configMap:
      name: resource-demo-config
  - name: app-secret
    secret:
      secretName: resource-demo-secret
```

Đoạn này giả định image đã có `ENTRYPOINT ["java","-jar","/app/app.jar"]` như Dockerfile, ConfigMap chứa key **`application.properties`** và Kubernetes Secret được cấp đúng namespace/RBAC. `registry.example.org` và tên resource là tên minh họa, phải thay bằng hạ tầng thật. Nếu cấu hình bắt buộc mà volume không mount, `spring.config.additional-location=file:/config/` (không `optional:`) giúp ứng dụng fail fast.

Để import secret ở dạng từng file, trong **external `/config/application.properties`** có thể khai báo:

```properties
spring.config.import=configtree:/run/secrets/
```

Ví dụ file được mount tại `/run/secrets/demo.api-key` trở thành property `demo.api-key`. Không đưa khóa thực vào mẫu tài liệu, log hoặc error page. Khi Secret được cập nhật, Kubernetes có thể cập nhật volume nhưng **ứng dụng không mặc định tự reload Spring Environment**, vì Config Data thông thường được nạp lúc startup; cần rollout/restart hoặc một cơ chế refresh được thiết kế và kiểm thử.

**Một image cho nhiều namespace:** thay ConfigMap/Secret/runtime env và deployment settings, không rebuild JAR riêng cho từng namespace. Tuy nhiên bảo đảm **đúng version cấu hình** đi cùng image; một config không tương thích vẫn làm app lỗi dù binary không đổi.

## 14. Tùy biến loại resource nào được đưa vào archive

Đôi khi project chứa file nguồn không nên publish: large test fixture, file dev-local, sample credentials, dữ liệu sample hoặc bộ ảnh chỉ cho tài liệu. **Đưa chúng ngoài `src/main/resources`** là giải pháp đầu tiên. Nếu cần custom packaging, dùng includes/excludes có chủ đích.

### 14.1. Maven: resources blocks và exclusions

Trong Maven POM, `<build><resources>` cho phép khai báo resource directories, filtering và include/exclude patterns. Ví dụ:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>dev-only/**</exclude>
                <exclude>private/**</exclude>
            </excludes>
        </resource>
    </resources>
</build>
```

**Đây là đoạn minh họa, không nên dán nguyên vào POM có starter parent mà không kiểm tra effect.** Nó thay đổi resource processing và có thể làm mất filtering convention ở `application.properties` mà parent cung cấp. Với dự án thật, ưu tiên dời file ra ngoài resource source set; nếu cần exclusions, ghép chính xác với effective POM và test artifact. Cấm secret vào Git/CI input ngay từ đầu vẫn quan trọng hơn việc dựa vào một rule exclude cuối cùng.

### 14.2. Gradle: `processResources` exclude

Trong `build.gradle.kts`:

```kotlin
import org.gradle.language.jvm.tasks.ProcessResources

tasks.named<ProcessResources>("processResources") {
    exclude("dev-only/**", "private/**")
}
```

Đây là **đoạn bổ sung**, giả định Java plugin đã áp dụng. Files bị exclude sẽ không được copy vào output resource main thông thường. Nếu cùng lúc dùng snippet `processResources` filtering ở mục 11.1, ghép các cấu hình vào cùng task hoặc bảo đảm chúng không xung đột.

**Giới hạn:** exclusions chỉ kiểm soát những file theo path match trong task đó. Tệp nhạy cảm có thể bị đưa vào artifact từ cách khác (custom task `from(...)`, dependency JAR, Docker build context, generated resources). Vì vậy phải kiểm tra **artifact cuối cùng**, không chỉ tin `build.gradle.kts` hoặc `pom.xml`.

### 14.3. Generated resources

Nếu build tạo version metadata/schema, đặt generator và output dưới build directory (`target/generated-resources` hoặc `build/generated/resources`), đăng ký với Maven/Gradle resource phase rồi khai báo inputs/outputs của task. Tránh ghi ngược file generated vào `src/main/resources` khi không thật sự muốn commit nó. Với Gradle, khai báo generator output bằng task/provider để build cache và task graph nhận biết dependency; không dùng đường dẫn tạo file bằng tay mà không gắn `processResources` đúng cách.

## 15. Kiểm tra đóng gói và external config trong CI/CD

Một pipeline chỉ xác nhận `mvn package` thành công vẫn có thể tạo JAR thiếu template, chứa nhầm secret hoặc chạy sai runtime configuration. Tối thiểu cần các lớp QA sau:

### 15.1. Kiểm tra archive contents

Bash:

```bash
set -e
mvn -B -ntp clean verify

JAR=target/resource-demo-0.0.1-SNAPSHOT.jar
test -f "$JAR"

jar tf "$JAR" |
  grep -q '^BOOT-INF/classes/assets/banner.txt$'

jar tf "$JAR" |
  grep -q '^BOOT-INF/classes/application.properties$'

jar tf "$JAR" |
  grep -q '^BOOT-INF/classes/static/welcome.txt$'
```

Đây là script Bash, cần `grep`/`test` và Maven; không phải YAML pipeline hoàn chỉnh. Với Gradle, thay build bằng `./gradlew clean build bootJar` và đường dẫn JAR tương ứng. Các check xác minh **sự hiện diện**, không thay thế việc scan nội dung nhạy cảm.

### 15.2. Kiểm tra resource/secret không phù hợp

Ví dụ một bước rà soát tên file trong archive:

```bash
jar tf target/resource-demo-0.0.1-SNAPSHOT.jar |
  grep -Ei '(^|/)(\.env|id_rsa|secret|private-key|.*\.pem|.*\.p12)(/|$)' || true
```

Kết quả có thể là **false positive** (ví dụ một thư viện hợp lệ có chữ “secret” trong tên file) hoặc **false negative** (secret có tên `config.json`). Không xem việc grep không ra gì là đủ chứng minh không có secret. Dùng secret scanner/SBOM/CI policy phù hợp, đồng thời kiểm tra Docker build context, generated files và nested dependency JAR khi cần. Đừng log nội dung secret lên CI chỉ để chứng minh nó có mặt/không có mặt.

### 15.3. Chạy smoke tests với default và external config

- Khởi chạy artifact không có external file, xác minh `/values` trả `message=packaged;region=local` và `/banner` trả `BANNER_FROM_ARCHIVE`.
- Dừng JVM, chạy **cùng artifact** với `--spring.config.additional-location=optional:file:./runtime-config/`, xác minh `/values` trả `message=external;region=staging` ở port 9090.
- Chạy một phiên với `DEMO_MESSAGE=from-env` để kiểm tra config precedence.
- Kiểm tra response code, startup logs và failure behavior khi external config bắt buộc bị thiếu.
- Tính checksum artifact trước và sau các lần thử nếu cần bảo đảm binary không đổi (`sha256sum` trên Linux, `Get-FileHash` trên PowerShell).

Smoke tests có thể tự động bằng script khởi động process riêng, chờ readiness/HTTP response, assert body và terminate trong finally/trap. Tránh dùng `sleep 5` làm điều kiện chắc chắn ứng dụng đã sẵn sàng; thời gian startup thay đổi theo CI.

### 15.4. Phân biệt build-time và run-time trong quy trình phát hành

```text
Build (CI):
  checkout source + dependencies
  -> test
  -> processResources
  -> executable JAR
  -> inspect / scan / checksum
  -> publish immutable artifact

Deploy (CD):
  chọn đúng artifact digest
  -> cấp ConfigMap / file config / env / secret
  -> start JVM với runtime args
  -> kiểm tra readiness / smoke test
  -> rollout / rollback theo release
```

Giá trị **build-time** như `project.version` có thể nằm trong file resource filtered, vì nó gắn với artifact version. Giá trị **runtime** như `spring.datasource.url` hoặc secret không nên đi qua Maven/Gradle filtering khi build image. Tách biệt hai giai đoạn giúp tránh “một JAR cho mỗi môi trường” không cần thiết.

## 16. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `ClassPathResource("assets/banner.txt")` không tìm thấy | File không nằm ở `src/main/resources/assets`, bị exclude, hoặc build nhầm module | `jar tf` tìm `BOOT-INF/classes/assets/banner.txt` |
| Chạy IDE đọc resource được nhưng `java -jar` lỗi | Dùng `getFile()`/`Path` trên resource trong archive | Chuyển sang `getInputStream()` / Spring `Resource` |
| `java -jar` lấy default thay vì external values | External file không được tìm thấy, sai working directory hoặc thiếu additional-location | Kiểm tra location/path/filename, startup config logs |
| Dùng `spring.config.location` làm mất default trong JAR | Thuộc tính thay thế search locations mặc định | Dùng `spring.config.additional-location` để bổ sung |
| `application.properties` bị override không như mong muốn | Environment hoặc CLI có ưu tiên cao hơn file | Đối chiếu `DEMO_MESSAGE`, `-Ddemo.message`, `--demo.message` |
| `application-prod.yml` không được dùng | Chưa active `prod`, profile/location sai | Kiểm tra `spring.profiles.active` và file name |
| `ConfigDataLocationNotFoundException` | External location bắt buộc không tồn tại | Cấp file/volume thật hoặc dùng `optional:` khi thực sự được phép thiếu |
| Docker dùng 9090 nhưng host map 8080 | External `server.port` đã đổi trong container | Map đúng cổng ứng dụng thật và host port |
| Maven resource placeholder `@project.version@` không được thay | Filtering bị tắt/override hoặc không dùng starter parent | Kiểm tra `target/classes` và effective POM |
| Spring placeholder `${SERVICE_HOST}` bị Maven xử lý sai | Filtering dùng delimiter mặc định `${...}` trùng Spring | Dùng convention `@..@` hoặc resource filtering cấu hình phù hợp |
| Gradle `expand` gây lỗi trên `application.properties` | Template expansion đọc nhầm Spring `${...}` | Chỉ filter file build metadata riêng, không filter all resources |
| Tệp binary/resource bị hỏng sau build | Filtering chuyển đổi byte trên ảnh/cert/font/JAR | Tắt filtering với binary resources, so sánh checksum |
| `/welcome.txt` trả 404 dù JAR có file | Sai thư mục static, custom MVC mapping/security/context path | Kiểm tra `static/` và Spring MVC resource handler config |
| App chạy được nhưng thiếu uploaded files sau restart | Ghi dữ liệu vào container ephemeral hoặc nhầm classpath archive | Dùng volume/object storage cho runtime data |
| ConfigMap/Secret cập nhật nhưng app không đổi | Spring Config Data đã nạp lúc startup, không tự refresh | Triển khai restart/rollout hoặc dùng refresh mechanism được thiết kế |
| Secret xuất hiện trong JAR | Đặt dưới `src/main/resources`, filtering hoặc generated resources | Di chuyển secret ra runtime, rotate secret và tăng CI scanning |
| Spring Boot JAR không có `BOOT-INF/classes` | Đang xem plain JAR, sai plugin hoặc chưa repackage/bootJar | Kiểm tra Boot plugin, artifact path và manifest |
| Resource đường dẫn tuyệt đối chạy ở dev nhưng fail CI | Máy/OS/container có filesystem khác | Cấp external path ở deploy và kiểm tra mount/permissions |

### Quy trình xử lý theo thứ tự

1. Xác định **đây là resource của phiên bản hay runtime configuration**. Nếu là resource ổn định, kiểm tra artifact; nếu là environment-specific, kiểm tra nguồn config bên ngoài.
2. Xác minh đúng artifact path, Maven/Gradle module, Java version và file source.
3. Với resource trong JAR: tìm entry qua `jar tf`, đọc bằng classpath InputStream, không dùng file path của IDE.
4. Với external `application.properties`: kiểm tra working directory, file URI, dấu `/` với directory, `optional:` và quyền đọc.
5. Kiểm tra profile, vị trí default/extra/import, cùng các nguồn có ưu tiên cao hơn.
6. Với container: kiểm tra mount path **bên trong container**, cổng ứng dụng thực tế, UID/permissions và rollout.
7. Với giá trị nhạy cảm: không in giá trị để debug; chỉ log tên khóa/trạng thái present nếu được phép, kiểm tra secret injection ngoài log.
8. Rebuild/restart theo đúng loại thay đổi; đổi external runtime file thường cần **restart/reload cấu hình**, nhưng không cần build JAR mới.
9. Chạy smoke test để xác nhận các giá trị và các tài nguyên đáp ứng hành vi mong đợi.

## 17. Những ngộ nhận cần tránh

1. **“Đặt file trong `src/main/resources` nghĩa là nó tự có thể sửa sau deploy.”** Sai: trong executable JAR, nó là nội dung archive bất biến.
2. **“`BOOT-INF/classes` là tên phải đưa vào `ClassPathResource`.”** Sai: classpath root đã là `BOOT-INF/classes`.
3. **“Mọi file `application.properties` phải ở ngoài JAR.”** Không: default không nhạy cảm có thể nằm trong JAR, external config ghi đè theo môi trường.
4. **“Đổi database password chỉ cần sửa JAR.”** Không: nên cấp từ secret manager/env/file mount và rotate theo deployment.
5. **“`spring.config.location` và `spring.config.additional-location` giống nhau.”** Không: một cái thay default locations, cái kia bổ sung.
6. **“External file cạnh JAR luôn được Spring Boot tìm.”** Không bảo đảm: Spring xét working directory và các location cấu hình, không chỉ vị trí file JAR.
7. **“`getFile()` luôn đọc được classpath resource.”** Không khi resource nằm trong archive/nested JAR.
8. **“Đặt secret trong `static` an toàn vì file ở trong JAR.”** Ngược lại: static content có thể được phục vụ qua HTTP.
9. **“Maven/Gradle filtering chỉ thay version.”** Không: cấu hình sai có thể sửa nhầm placeholders hoặc làm hỏng binary files.
10. **“Resource filtering và Spring property placeholder đều hoạt động ở startup.”** Sai: Maven/Gradle filtering là build-time; Spring placeholders là runtime.
11. **“Chỉ cần grep tên file là chắc chắn không có secret.”** Không: tên file có thể vô hại hoặc secret nằm trong file tên bình thường.
12. **“ConfigMap/Secret mount mới là Spring tự reload ngay.”** Không có bảo đảm; mặc định Config Data nạp lúc startup.
13. **“Mọi profile-specific file nên chứa credentials.”** Không: profile file đóng trong archive vẫn phân phối cùng JAR.
14. **“Đổi external config làm thay đổi checksum artifact.”** Không: nếu chỉ sửa external file mà giữ JAR, checksum JAR không đổi.
15. **“Executable JAR chứa cả Java runtime.”** Không: JAR thông thường của Spring Boot vẫn cần JVM được hỗ trợ; native image/OCI image là loại packaging khác.

## 18. Checklist trước khi phát hành

- **Resource classification:** định danh file nào phải đi theo code và file nào là runtime config/secret/data.
- **Production resources:** chỉ đặt default không nhạy cảm, assets, templates, schema/migration cần thiết trong `src/main/resources`.
- **Archive verification:** kiểm tra `BOOT-INF/classes`, `BOOT-INF/lib`, filename chính xác, filtered content và classpath lookup bằng InputStream.
- **Runtime config:** xác định file location, working directory, active profile, precedence và fail-fast đối với config/secret bắt buộc.
- **Build tool:** Maven `process-resources` + `repackage` hoặc Gradle `processResources` + `bootJar`, dùng phiên bản plugin/JDK tương thích.
- **Filtering:** chỉ filter những text files đã chọn, tránh xung đột Spring placeholders và tránh binary corruption.
- **Secret hygiene:** không có password, token, private key trong Git/JAR/image layers/log; dùng secret manager, RBAC, file permissions và rotation.
- **Deployment layout:** cấp volume/config ngoài JAR với read-only khi hợp lý; không ghi dữ liệu runtime vào archive.
- **Test:** smoke test default + override + profile/port, đồng thời thử thiếu config bắt buộc để xác nhận hành vi fail.
- **Reproducibility:** ghi nhận checksum/JAR digest, version external config, release metadata và rollback plan.

## 19. Tài liệu chính thức

- Spring Boot – [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): PropertySources, config data, default locations, `spring.config.location`, `spring.config.additional-location`, `spring.config.import` và `configtree:`.
- Spring Boot – [Properties and Configuration](https://docs.spring.io/spring-boot/3.5/how-to/properties-and-configuration.html): Maven `@..@` filtering, Gradle `expand` và các xung đột placeholder.
- Spring Boot – [Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): static resources trong `/static`, `/public`, `/resources` và `/META-INF/resources`.
- Spring Boot – [Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html): `BOOT-INF/classes`, `BOOT-INF/lib` và Boot Loader.
- Spring Boot Maven Plugin – [Using the Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html): starter parent và `repackage`.
- Gradle – [The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): source sets, `processResources` và output resources.
- Gradle – [Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): filtering/processing resources và packaging.
- Spring Framework – [Resource Interface](https://docs.spring.io/spring-framework/reference/core/resources.html): `Resource`, `ClassPathResource` và `getInputStream()`.

**Kết luận:** tài nguyên **thuộc phiên bản ứng dụng** được đóng trong executable JAR và truy cập qua classpath; configuration **thuộc môi trường** cần được cung cấp ngoài JAR qua Spring Config Data, environment, CLI hoặc secret volume. Maven/Gradle xử lý `src/main/resources` ở build-time, còn Spring Boot quyết định các giá trị runtime khi start. Phân tách đúng giúp có **một artifact bất biến**, dễ kiểm tra, bảo mật và triển khai nhất quán giữa dev, staging và production.