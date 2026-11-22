# Tổ chức resource và cấu hình để chạy nhất quán từ IDE và JAR

Trong dự án Spring Boot đầu tiên, một ứng dụng có thể đọc được tệp khi chạy bằng nút **Run** trong IDE, nhưng báo không tìm thấy tệp sau khi được đóng gói thành JAR. Có trường hợp `application.yml` hoạt động trong IDE nhưng cấu hình khác đi khi chạy bằng `java -jar`; cũng có trường hợp ứng dụng ghi file thành công nhưng không tìm thấy file vừa tạo.

Những tình huống này thường liên quan đến cách tổ chức mã nguồn và ba khái niệm riêng biệt: **resource được đóng gói trên classpath**, **cấu hình được Spring Boot nạp từ nhiều nguồn**, và **đường dẫn filesystem phụ thuộc môi trường chạy**. Mục tiêu của bài học thuộc nhóm **Tổ chức mã nguồn** là thiết kế một ứng dụng Spring Boot sao cho những gì thuộc artifact hoạt động giống nhau trong IDE và JAR, còn những gì thuộc môi trường được cấu hình rõ ràng.

## 1. Bốn khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Resource nguồn | Tệp đặt trong cấu trúc dự án để build tool copy vào runtime output | `src/main/resources/messages/welcome.txt` |
| Classpath resource | Tệp được tìm bằng tên tương đối với classpath root | `classpath:messages/welcome.txt` |
| External file | Tệp tồn tại trên filesystem, bên ngoài artifact ứng dụng | `/etc/demo/application.yml`, `C:/demo/data/report.txt` |
| Working directory | Thư mục hiện hành của tiến trình JVM, dùng làm gốc cho đường dẫn tương đối | `./config`, `./data` |

Xét hai cách viết:

```text
classpath:messages/welcome.txt
./messages/welcome.txt
```

Dòng đầu tiên yêu cầu tìm resource bằng class loader; nơi chứa vật lý có thể là một thư mục output trong IDE hoặc mục nằm bên trong JAR. Dòng thứ hai trỏ đến một **tệp trên filesystem**, tương đối với working directory. Nó không được tự động đổi thành đường dẫn vào JAR.

Câu hỏi quyết định cách tổ chức là: **tệp này được phát hành cùng phiên bản ứng dụng, hay cần được thay đổi độc lập với phiên bản ứng dụng?**

- Tệp đi cùng bản build và chủ yếu chỉ đọc: đặt trong `src/main/resources`.
- Dữ liệu phát sinh, file người dùng tải lên hoặc cấu hình của môi trường triển khai: lưu hoặc cung cấp bên ngoài JAR.
- Java code cần đọc resource đóng gói: sử dụng classpath API.
- Java code cần ghi file: sử dụng filesystem API với thư mục lưu trữ được cấu hình.

## 2. Cấu trúc dự án Spring Boot dễ duy trì

Cấu trúc thường gặp với Maven hoặc Gradle:

```text
demo/
├── build.gradle                  # Hoặc pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/demo/
│   │   │       ├── DemoApplication.java
│   │   │       ├── config/AppProperties.java
│   │   │       ├── service/WelcomeTextService.java
│   │   │       └── web/WelcomeController.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-dev.yml
│   │       ├── application-prod.yml
│   │       ├── messages/
│   │       │   └── welcome.txt
│   │       ├── static/
│   │       │   └── css/site.css
│   │       └── templates/
│   │           └── home.html
│   └── test/
│       ├── java/
│       └── resources/
│           └── application-test.yml
└── README.md
```

**`src/main/java`** chứa mã nguồn Java với package phù hợp. **`src/main/resources`** chứa tài nguyên được đưa lên runtime classpath. **`src/test/resources`** phục vụ các bài test, thông thường không được đưa vào artifact chạy production.

### 2.1. Vì sao không đặt dữ liệu cần ghi vào `src/main/resources`?

Một lỗi thường gặp là dùng thư mục nguồn làm thư mục lưu ảnh upload:

```java
Path uploadDir = Path.of("src/main/resources/static/uploads");
```

Đường dẫn này chỉ có ý nghĩa khi ứng dụng được chạy tại một nơi còn tồn tại source tree. Sau khi phát hành JAR, người vận hành có thể không có thư mục `src`. Ngay cả khi có, viết vào source tree không làm thay đổi resource đã đóng gói bên trong artifact đang chạy.

Tài nguyên đóng gói phù hợp với template, cấu hình mặc định, văn bản mẫu và tài sản tĩnh. File upload, cache, báo cáo tạo ra hoặc tệp thay đổi theo người dùng phải được lưu bên ngoài.

### 2.2. Output của build tool có thể khác source tree

Với Gradle Java plugin, một output phổ biến là:

```text
build/
├── classes/java/main/
│   └── com/example/demo/...
└── resources/main/
    ├── application.yml
    └── messages/welcome.txt
```

Với Maven, các lớp đã biên dịch và resource thường xuất hiện dưới `target/classes/`. IDE có thể tạo thư mục output riêng hoặc ủy quyền việc build cho Maven/Gradle.

Điểm chung là resource được đặt trên **runtime classpath**. Mã ứng dụng không nên hard-code tên của thư mục output cụ thể.

## 3. Resource nằm ở đâu khi đóng gói Spring Boot executable JAR?

Một executable JAR theo cách đóng gói thường gặp của Spring Boot có dạng:

```text
demo.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/demo/DemoApplication.class
    │   ├── application.yml
    │   ├── application-dev.yml
    │   ├── messages/welcome.txt
    │   ├── static/css/site.css
    │   └── templates/home.html
    └── lib/
        ├── spring-boot-....jar
        └── ...các thư viện khác...
```

Trong kiểu JAR này, `BOOT-INF/classes/` chứa lớp và resource của ứng dụng, còn `BOOT-INF/lib/` chứa các dependency JAR. Spring Boot launcher khởi tạo cơ chế nạp lớp phù hợp để lớp và resource có thể được tìm qua classpath.

Mặc dù resource nằm dưới `BOOT-INF/classes/messages/welcome.txt`, Java code vẫn truy cập nó bằng tên logic:

```text
messages/welcome.txt
```

**Không** thêm `BOOT-INF/classes` vào tên truyền cho `ClassPathResource`. Đó là chi tiết tổ chức artifact, không phải một phần của khóa resource.

### 3.1. Cách đọc trực tiếp từ thư mục nguồn dễ gây lỗi

Đoạn mã sau có thể chạy khi IDE sử dụng thư mục gốc dự án làm working directory:

```java
Path path = Path.of("src/main/resources/messages/welcome.txt");
String message = Files.readString(path);
```

Sau khi triển khai:

```bash
cd /opt/demo
java -jar demo.jar
```

ứng dụng sẽ tìm `/opt/demo/src/main/resources/messages/welcome.txt` trên filesystem. Không có lý do để tệp đó luôn tồn tại. Nó đã được đóng gói vào JAR, chứ không nằm dưới source tree ở môi trường chạy.

Vì vậy, **đừng dùng đường dẫn `src/main/resources` để đọc resource ở runtime**.

## 4. Đọc resource đóng gói bằng Spring `Resource`

Spring cung cấp `org.springframework.core.io.Resource` và `ClassPathResource`. Cách đọc qua `InputStream` tương thích với cả resource nằm ở thư mục output và resource nằm bên trong JAR.

`src/main/resources/messages/welcome.txt`:

```text
Chào mừng bạn đến với Spring Boot!
```

`src/main/java/com/example/demo/service/WelcomeTextService.java`:

```java
package com.example.demo.service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

@Service
public class WelcomeTextService {

    public String readWelcomeText() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("messages/welcome.txt");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
```

`ClassPathResource` biểu diễn resource theo **tên trên classpath**. `getInputStream()` đọc nội dung dù tệp được phát hành trong JAR. Với tài nguyên lớn, có thể đọc từng phần từ luồng thay vì dùng `readAllBytes()`.

### 4.1. Inject resource qua cấu hình Spring

Một controller có thể nhận resource trực tiếp:

```java
package com.example.demo.web;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WelcomeController {

    private final Resource welcomeResource;

    public WelcomeController(
            @Value("classpath:messages/welcome.txt")
            Resource welcomeResource
    ) {
        this.welcomeResource = welcomeResource;
    }

    @GetMapping("/welcome")
    public String welcome() throws IOException {
        try (InputStream input = welcomeResource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

Trong ví dụ có `spring-boot-starter-web` và cổng mặc định, endpoint `GET http://localhost:8080/welcome` trả về nội dung tệp.

Nếu muốn thay vị trí resource qua cấu hình:

```yaml
app:
  welcome-resource: classpath:messages/welcome.txt
```

Sửa constructor thành:

```java
public WelcomeController(
        @Value("${app.welcome-resource}") Resource welcomeResource
) {
    this.welcomeResource = welcomeResource;
}
```

Nhờ vậy, nơi chứa resource được thể hiện trong cấu hình, còn code vẫn dùng chung `Resource#getInputStream()`.

### 4.2. Không ép classpath resource thành `File`

Cách này có rủi ro:

```java
Resource resource = new ClassPathResource("messages/welcome.txt");
File file = resource.getFile(); // Có thể thất bại khi resource nằm trong JAR
```

Trong IDE, resource thường là tệp thật ở thư mục output, vì thế `getFile()` có thể thành công. Trong JAR, resource có thể không biểu diễn được dưới dạng một `java.io.File` riêng lẻ.

Sử dụng:

```java
try (InputStream input = resource.getInputStream()) {
    // Đọc nội dung tại đây.
}
```

Nếu API của thư viện bên ngoài bắt buộc nhận `File`, cân nhắc API nhận `InputStream` trước. Nếu thực sự cần một file vật lý, có thể trích resource ra **tệp tạm bên ngoài JAR**, sử dụng nó rồi dọn dẹp theo vòng đời phù hợp.

### 4.3. Đọc qua Java `ClassLoader` khi không cần Spring API

Ví dụ:

```java
try (InputStream input = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream("messages/welcome.txt")) {

    if (input == null) {
        throw new IllegalStateException(
                "Không tìm thấy messages/welcome.txt"
        );
    }

    String text = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8
    );
    System.out.println(text);
}
```

Lưu ý phân biệt API:

- `ClassLoader#getResourceAsStream("messages/welcome.txt")` tìm theo đường dẫn từ classpath root, không bắt đầu bằng dấu `/`.
- `SomeClass.class.getResourceAsStream("welcome.txt")` có thể tìm tương đối với package của lớp đó.
- `SomeClass.class.getResourceAsStream("/messages/welcome.txt")` tìm từ classpath root.

Việc dùng một quy ước nhất quán giúp tránh lỗi chỉ do dấu `/` đầu đường dẫn.

## 5. Tổ chức cấu hình qua `application.yml` và profile

Tệp cấu hình mặc định thường đặt tại:

```text
src/main/resources/application.yml
```

Ví dụ:

```yaml
spring:
  application:
    name: resource-demo

server:
  port: ${APP_PORT:8080}

app:
  greeting: "Xin chào từ cấu hình chung"
  welcome-resource: classpath:messages/welcome.txt
  data-directory: ${APP_DATA_DIRECTORY:./var/data}
```

Đây là các dạng giá trị khác nhau:

- `spring.application.name` đặt tên ứng dụng.
- `server.port` có thể được lấy từ biến môi trường `APP_PORT`, nếu không có thì dùng `8080`.
- `app.greeting` là thuộc tính riêng của ứng dụng.
- `app.welcome-resource` tham chiếu resource đóng gói.
- `app.data-directory` mô tả thư mục ghi dữ liệu trên filesystem.

Điểm cần chú ý là `./var/data` vẫn tương đối theo **working directory**, dù giá trị đó được viết trong `application.yml`. Việc dùng file cấu hình không tự làm đường dẫn này thành tuyệt đối.

### 5.1. Profile cho các môi trường khác nhau

`src/main/resources/application-dev.yml`:

```yaml
app:
  greeting: "Xin chào từ môi trường phát triển"
```

`src/main/resources/application-prod.yml`:

```yaml
app:
  greeting: "Xin chào từ môi trường triển khai"
  data-directory: ${APP_DATA_DIRECTORY}
```

Khi kích hoạt profile `dev`, Spring Boot áp dụng cấu hình dành cho profile đó theo quy tắc config data; trong tình huống thông thường, `app.greeting` của `application-dev.yml` ghi đè giá trị từ `application.yml`. Các thuộc tính không được định nghĩa lại tiếp tục lấy giá trị từ nguồn cấu hình có hiệu lực tương ứng.

Giá trị `${APP_DATA_DIRECTORY}` không có fallback. Điều này phù hợp khi production bắt buộc cấu hình thư mục lưu trữ rõ ràng; nếu property được resolve mà biến không có, ứng dụng có thể thất bại vì thiếu cấu hình.

Một JAR có thể chứa đồng thời `application.yml`, `application-dev.yml` và `application-prod.yml`. Profile thường được chọn **khi chạy**, không cần build một JAR khác chỉ để đổi lời chào, cổng hay thư mục dữ liệu.

### 5.2. Kích hoạt profile

Từ dòng lệnh:

```bash
java -jar demo.jar --spring.profiles.active=dev
```

Qua biến môi trường trên Linux/macOS:

```bash
export SPRING_PROFILES_ACTIVE=dev
java -jar demo.jar
```

Trên Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar demo.jar
```

Trong IDE, đặt `SPRING_PROFILES_ACTIVE=dev` tại mục **Environment variables**, hoặc đặt `--spring.profiles.active=dev` tại **Program arguments** của Run Configuration.

Không nên đặt `spring.profiles.active: dev` trong chính `application-dev.yml`: Spring Boot có các quy tắc hạn chế thuộc tính kích hoạt profile trong tài liệu chỉ được nạp khi profile đã active. Hãy chọn profile qua cấu hình khởi chạy hoặc nguồn cấu hình phù hợp.

## 6. Độ ưu tiên cấu hình: vì sao JAR nhận giá trị khác?

Spring Boot hỗ trợ *externalized configuration*: cùng một property có thể được khai báo ở file đóng gói, file ngoài JAR, biến môi trường, Java system property hoặc command-line argument.

Ví dụ trong JAR:

```yaml
server:
  port: 8080
```

Nhưng khi chạy:

```bash
java -jar demo.jar --server.port=9090
```

thì ứng dụng thường dùng cổng `9090` vì command-line argument có ưu tiên cao hơn config data.

| Nguồn | Ví dụ | Thường sử dụng cho |
|---|---|---|
| Config đóng gói | `classpath:/application.yml` | Giá trị mặc định và quy ước chung |
| Config file bên ngoài | `./config/application.yml` | Giá trị phụ thuộc nơi triển khai |
| Biến môi trường | `SERVER_PORT=9090` | Container, hệ điều hành, CI/CD |
| Java system property | `-Dserver.port=9090` | Tham số JVM |
| Command-line argument | `--server.port=9090` | Ghi đè trực tiếp khi launch |

Trong thứ tự thường gặp, command-line arguments có ưu tiên cao hơn Java system properties, environment variables và config data; Java system properties thường cao hơn environment variables. Spring Boot còn nhiều PropertySource khác và những quy tắc riêng cho profile, test và config location, nên khi có xung đột cần kiểm tra cấu hình chạy thực tế.

### 6.1. Đặt biến môi trường cho thuộc tính riêng

Theo quy tắc relaxed binding chuẩn từ canonical property name sang tên biến môi trường, dấu chấm chuyển thành dấu gạch dưới, dấu gạch nối bị loại bỏ và tên chuyển thành chữ hoa. Vì vậy:

```text
app.data-directory  ->  APP_DATADIRECTORY
```

Nếu muốn sử dụng tên dễ đọc hơn `APP_DATA_DIRECTORY`, bạn có thể viết placeholder rõ ràng:

```yaml
app:
  data-directory: ${APP_DATA_DIRECTORY:./var/data}
```

Khi đó Spring dùng giá trị biến môi trường được tham chiếu trong placeholder, không cần dựa vào giả định rằng mọi cách đặt dấu gạch dưới đều được relaxed binding diễn giải giống nhau.

### 6.2. Chọn `@Value` hay `@ConfigurationProperties`?

Với một giá trị đơn giản, có thể dùng:

```java
@Value("${app.greeting}")
private String greeting;
```

Khi có nhiều thuộc tính liên quan, `@ConfigurationProperties` tạo một kiểu dữ liệu thống nhất:

```java
package com.example.demo.config;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String greeting,
        Path dataDirectory
) {
}
```

Bật scanning trong lớp main:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Sau đó inject cấu hình vào một bean:

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class StoragePathService {

    private final AppProperties properties;

    public StoragePathService(AppProperties properties) {
        this.properties = properties;
    }

    public Path directory() {
        return properties.dataDirectory();
    }
}
```

Spring Boot có thể bind chuỗi thành các kiểu như `Path`. Tuy nhiên, việc bind thành công không có nghĩa thư mục đã tồn tại hoặc có quyền ghi. Việc tạo và kiểm soát thư mục vẫn là trách nhiệm của phần thao tác filesystem.

## 7. Đọc resource đóng gói và ghi dữ liệu là hai luồng riêng

Giả sử ứng dụng cần đọc một mẫu báo cáo và ghi một báo cáo mới:

```text
Mẫu báo cáo:
  src/main/resources/templates/report-template.txt
  -> classpath resource, chỉ đọc

Báo cáo xuất ra:
  /var/lib/resource-demo/reports/report.txt
  -> filesystem bên ngoài JAR, cần quyền ghi
```

Ví dụ dịch vụ ghi báo cáo:

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final AppProperties properties;

    public ReportService(AppProperties properties) {
        this.properties = properties;
    }

    public Path writeReport(String content) throws IOException {
        Path directory = properties.dataDirectory();
        Files.createDirectories(directory);

        Path output = directory.resolve("report.txt");
        Files.writeString(output, content, StandardCharsets.UTF_8);
        return output;
    }
}
```

Ví dụ dùng tên cố định `report.txt` để tập trung vào cách tổ chức file. Ứng dụng thật cần thêm quy tắc về tên file, ghi đồng thời, ghi đè và phân quyền.

Để mọi cách chạy đều ghi vào cùng nơi, cấu hình một đường dẫn tuyệt đối cho môi trường.

Linux/macOS:

```bash
export APP_DATA_DIRECTORY=/var/lib/resource-demo
java -jar demo.jar --spring.profiles.active=prod
```

Windows PowerShell:

```powershell
$env:APP_DATA_DIRECTORY = 'C:\resource-demo\data'
java -jar demo.jar --spring.profiles.active=prod
```

Tài khoản chạy ứng dụng phải có quyền tạo và ghi trong thư mục được chọn. Với container, thư mục dữ liệu cần được gắn với volume hoặc một dịch vụ lưu trữ bền vững nếu muốn giữ dữ liệu qua các lần triển khai.

## 8. So sánh cách chạy từ IDE, Gradle/Maven và JAR

| Cách khởi chạy | Cách thiết lập classpath | Cần chú ý |
|---|---|---|
| Run Main trong IDE | IDE hoặc build tool được IDE ủy quyền | Working directory, profile, environment variables và VM/program arguments |
| Gradle `bootRun` | Gradle cùng Spring Boot plugin | Dependencies/runtime classpath và các args |
| Maven `spring-boot:run` | Maven cùng Spring Boot Maven Plugin | Profile, Maven plugin arguments và môi trường |
| `java -jar demo.jar` | Spring Boot launcher trong executable JAR | JAR thực tế, arguments, cấu hình ngoài và working directory |

Classpath có thể được xây dựng từ output directories khi chạy IDE hoặc build tool, và từ các mục lồng bên trong JAR khi chạy artifact. Nếu code chỉ tham chiếu `classpath:messages/welcome.txt` thì sự khác biệt vật lý này đã được class loader xử lý.

### 8.1. Chạy cùng profile với Gradle Wrapper

Linux/macOS:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Build artifact:

```bash
./gradlew bootJar
```

Chạy JAR tạo ra:

```bash
java -jar build/libs/demo.jar --spring.profiles.active=dev
```

Tên `demo.jar` là ví dụ. Thư mục `build/libs` thường là output mặc định của Gradle, nhưng tên và vị trí artifact phụ thuộc cấu hình project.

### 8.2. Chạy cùng profile với Maven Wrapper

Linux/macOS:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=dev
./mvnw package
java -jar target/demo.jar --spring.profiles.active=dev
```

Các lệnh chỉ áp dụng nếu dự án có Maven Wrapper, Spring Boot Maven Plugin và artifact thực thi được tạo qua cấu hình đóng gói thích hợp. Tên `demo.jar` cần thay bằng artifact thật.

### 8.3. Working directory ảnh hưởng đến đường dẫn tương đối

Nếu ứng dụng gọi:

```java
Path path = Path.of("./var/data/report.txt");
```

Thư mục hiện hành `/home/me/projects/demo` dẫn tới:

```text
/home/me/projects/demo/var/data/report.txt
```

Nhưng chạy JAR từ `/opt/demo` dẫn tới:

```text
/opt/demo/var/data/report.txt
```

Đây là hai nơi lưu khác nhau dù bytecode và cấu hình tương đối không đổi.

Có hai chiến lược phù hợp:

1. Cố định working directory trong IDE, script khởi chạy, service manager hoặc container.
2. Cấp đường dẫn dữ liệu tuyệt đối qua biến môi trường/config cho từng môi trường.

Để quan sát working directory:

```java
System.out.println(
        Path.of("").toAbsolutePath().normalize()
);
```

Cách này hữu ích khi chẩn đoán, nhưng không nên dùng đường dẫn của máy cá nhân làm mặc định cố định trong business code.

## 9. Cấu hình bên ngoài JAR và quy tắc tìm config

Ngoài cấu hình đóng gói, Spring Boot có thể nạp config data từ filesystem. Một bố cục triển khai dễ hiểu:

```text
/opt/resource-demo/
├── demo.jar
├── config/
│   └── application.yml
└── data/
```

Nếu khởi chạy tại `/opt/resource-demo`, Spring Boot với các vị trí tìm config mặc định thông thường có thể đọc `./config/application.yml`. Đây là một vị trí **tương đối với working directory**, khác với `classpath:/application.yml`.

Bạn cũng có thể chỉ định vị trí:

```bash
java -jar demo.jar \
  --spring.config.additional-location=optional:file:./config/
```

Trên PowerShell, dùng một dòng:

```powershell
java -jar demo.jar --spring.config.additional-location=optional:file:./config/
```

Lưu ý:

- `spring.config.additional-location` **bổ sung** địa điểm tìm cấu hình, phù hợp khi muốn giữ các vị trí mặc định.
- `spring.config.location` có thể **thay thế** các vị trí mặc định; sử dụng khi bạn chủ động muốn kiểm soát toàn bộ nguồn config data.
- `optional:` chỉ giúp bỏ qua địa điểm không tồn tại; nếu ứng dụng thiếu một property bắt buộc, nó vẫn có thể không khởi động.
- `file:./config/` dùng filesystem; `classpath:/config/` dùng classpath.
- Với config location là thư mục, hãy giữ dấu `/` cuối theo cú pháp location của Spring Boot.

Nếu working directory có thể thay đổi, dùng vị trí tuyệt đối:

```bash
java -jar /opt/resource-demo/demo.jar \
  --spring.config.additional-location=optional:file:/etc/resource-demo/
```

Spring Boot còn có `spring.config.import`:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"
```

Cơ chế này hữu ích để nhập thêm nguồn cấu hình, với quy tắc ưu tiên riêng. Đường dẫn tương đối trong import vẫn cần được hiểu theo semantics của Spring Boot và môi trường chạy; không nên suy đoán là luôn tương đối với source tree.

### 9.1. Đừng nhúng bí mật vào resource đóng gói

Không nên commit mật khẩu, API key hay token vào `application.yml`:

```yaml
# Ví dụ không nên dùng cho cấu hình thật
app:
  api-key: "real-secret-value"
```

Dùng nguồn secret phù hợp với hệ thống triển khai, hoặc tham chiếu giá trị được cấp qua môi trường:

```yaml
app:
  api-key: ${APP_API_KEY}
```

Tránh in secret ra log khi đang kiểm tra cấu hình. File ngoài JAR và environment variable cũng cần được bảo vệ bằng quyền truy cập phù hợp.

## 10. `static` và `templates` trong ứng dụng web

Ngoài resource được code tự đọc, Spring Boot web có những quy ước về resource phục vụ HTTP.

### 10.1. Static assets

Ví dụ:

```text
src/main/resources/static/
├── css/site.css
├── js/app.js
└── images/logo.svg
```

Trong ứng dụng Spring MVC thông thường, các file này được phục vụ qua URL:

```text
GET /css/site.css
GET /js/app.js
GET /images/logo.svg
```

Tên thư mục `static` thường không có trong URL public. Spring Boot có các vị trí static mặc định trên classpath, trong đó có `/static`, `/public`, `/resources` và `/META-INF/resources`; quy tắc này có thể được thay bằng cấu hình riêng của project.

Nếu assets hoạt động trong IDE nhưng JAR trả 404, cần xem artifact có chứa chúng không, URL có đúng không, và cấu hình static resource handling có bị thay đổi không.

### 10.2. Template cho template engine

Ví dụ đặt:

```text
src/main/resources/templates/home.html
```

Khi có template engine được cấu hình phù hợp, chẳng hạn Thymeleaf, một MVC controller có thể trả về tên view:

```java
package com.example.demo.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class HomeController {

    @GetMapping("/")
    public String home() {
        return "home";
    }
}
```

Template engine thường tìm `classpath:/templates/home.html` theo các quy ước đã được cấu hình. Khác với `@RestController`, `@Controller` trong ví dụ này trả tên view thay vì ghi trực tiếp chuỗi `home` vào HTTP response.

Nếu thiếu starter của template engine hoặc file template, ứng dụng vẫn có thể khởi động nhưng thất bại khi render request. Lỗi này cần được phân biệt với thiếu resource lúc khởi chạy.

### 10.3. Static asset khác với nội dung do người dùng tải lên

`src/main/resources/static` phù hợp cho CSS, JavaScript và ảnh đi theo bản phát hành. Ảnh upload mới nên được lưu ngoài JAR hoặc vào dịch vụ lưu trữ thích hợp. Nếu cần phục vụ ảnh upload qua HTTP, cần một cơ chế trả file từ storage cùng chính sách quyền truy cập phù hợp.

## 11. Ví dụ end-to-end: một ứng dụng, hai cách chạy

Hãy ghép các phần thành ví dụ Spring Boot nhỏ. Giả định project đã cấu hình plugin Spring Boot, Java phù hợp và dependency `spring-boot-starter-web`.

### 11.1. Resource và cấu hình

`src/main/resources/messages/welcome.txt`:

```text
Đây là resource được đóng gói cùng ứng dụng.
```

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: resource-demo

app:
  greeting: "Xin chào"
  data-directory: ${APP_DATA_DIRECTORY:./var/data}
```

`src/main/resources/application-dev.yml`:

```yaml
app:
  greeting: "Xin chào từ profile dev"
```

### 11.2. Bind cấu hình

`src/main/java/com/example/demo/config/AppProperties.java`:

```java
package com.example.demo.config;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(String greeting, Path dataDirectory) {
}
```

`src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 11.3. Endpoint trả cả cấu hình và resource

`src/main/java/com/example/demo/web/WelcomeController.java`:

```java
package com.example.demo.web;

import com.example.demo.config.AppProperties;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WelcomeController {

    private final AppProperties properties;
    private final Resource welcomeText;

    public WelcomeController(
            AppProperties properties,
            @Value("classpath:messages/welcome.txt") Resource welcomeText
    ) {
        this.properties = properties;
        this.welcomeText = welcomeText;
    }

    @GetMapping("/welcome")
    public String welcome() throws IOException {
        try (InputStream input = welcomeText.getInputStream()) {
            String text = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );

            return properties.greeting() + "\n" + text;
        }
    }
}
```

Trong IDE, chọn main class `com.example.demo.DemoApplication` và Program argument `--spring.profiles.active=dev`. Khi chạy thành công, `GET /welcome` trả nội dung gồm lời chào từ profile dev và văn bản của resource.

Với Gradle:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
./gradlew bootJar
java -jar build/libs/demo.jar --spring.profiles.active=dev
```

Ở Windows PowerShell, thay lệnh wrapper bằng `.\gradlew.bat` và dùng cú pháp argument tương ứng. Đổi `demo.jar` thành tên thật của artifact.

Kết quả đọc resource và lựa chọn cấu hình profile có cùng nguyên tắc ở cả hai cách chạy. Nếu chạy JAR từ thư mục khác, resource đóng gói vẫn đọc được; chỉ những đường dẫn filesystem tương đối, ví dụ `./var/data`, mới thay đổi nơi được resolve.

## 12. Chẩn đoán khi IDE chạy được nhưng JAR lỗi

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `NoSuchFileException: src/main/resources/...` | Code dùng source path ở runtime | Dùng classpath resource nếu là dữ liệu đóng gói |
| `FileNotFoundException` khi gọi `Resource#getFile()` | Resource không phải file thật trong JAR | Dùng `getInputStream()` hoặc trích tệp tạm nếu cần |
| `ClassPathResource ... does not exist` | Sai tên hoặc resource không được đóng gói | Kiểm tra nguồn và nội dung artifact |
| `application-dev.yml` không có tác dụng | Profile chưa active hoặc property bị ghi đè | Kiểm tra program args, env và external config |
| JAR sử dụng sai cổng | Nguồn cấu hình khác ghi đè `server.port` | Kiểm tra command-line, system properties, env, config |
| File ghi thành công nhưng ở nơi khác | Working directory khác | In đường dẫn tuyệt đối sau resolve; cấu hình absolute path |
| `Permission denied` khi lưu báo cáo | Thư mục dữ liệu không cho phép ghi | Kiểm tra quyền truy cập và volume |
| CSS/JS trả 404 | Sai vị trí trong `static`, sai URL hoặc thiếu trong JAR | Xem nội dung JAR và static path config |
| Template không render | Template engine thiếu hoặc không tìm được template | Kiểm tra dependency, controller và `templates` |
| Chạy được trên Windows nhưng sai trên Linux | Khác biệt chữ hoa/thường hoặc đường dẫn | Dùng đúng tên resource; dùng `/` trong tên classpath |

### 12.1. Kiểm tra nội dung JAR

Sau khi build:

```bash
jar --list --file build/libs/demo.jar
```

Tìm các mục:

```text
BOOT-INF/classes/application.yml
BOOT-INF/classes/application-dev.yml
BOOT-INF/classes/messages/welcome.txt
```

Trên Windows PowerShell:

```powershell
jar --list --file build/libs/demo.jar | Select-String 'BOOT-INF/classes'
```

Nếu resource thiếu trong JAR, kiểm tra vị trí tệp ở `src/main/resources` và cấu hình copy resources của build tool. Nếu resource có trong JAR, kiểm tra tên truyền cho `ClassPathResource`, cách mở resource và class loader được sử dụng.

### 12.2. Quan sát đường dẫn runtime

Khi điều tra, có thể in ra những thông tin không nhạy cảm:

```java
System.out.println("Working dir: " +
        Path.of("").toAbsolutePath().normalize());

System.out.println("Data dir: " +
        properties.dataDirectory().toAbsolutePath().normalize());

Resource resource = new ClassPathResource("messages/welcome.txt");
System.out.println("Welcome resource exists: " + resource.exists());
```

Nếu `properties.dataDirectory()` là đường dẫn tương đối, cách in này cho biết nó được hiểu thành đường dẫn tuyệt đối nào. Không in toàn bộ property sources hoặc biến môi trường khi chúng có thể chứa secret.

### 12.3. Một quy trình điều tra ngắn gọn

```text
Tệp nguồn có nằm đúng trong src/main/resources?
                    │
                    ▼
Build output / JAR có chứa resource?
                    │
                    ▼
Code đọc từ classpath hay từ filesystem?
                    │
                    ▼
Profile và property source có đúng như dự kiến?
                    │
                    ▼
Nếu ghi dữ liệu: nơi lưu và quyền filesystem có đúng?
```

Chọn bước kiểm tra phù hợp với lỗi. Nếu `ClassPathResource` báo không tồn tại, việc đổi cổng HTTP không giải quyết được. Nếu file upload không thể ghi vì permission, việc copy lại resource vào JAR cũng không làm thư mục lưu bên ngoài có quyền ghi.

## 13. Quy tắc tổ chức và bài thực hành

Các quy ước hữu ích khi bắt đầu dự án:

1. Đặt resource chỉ đọc, đi theo bản build, vào `src/main/resources` và truy cập theo **classpath**.
2. Đặt file do chương trình tạo hoặc người dùng cung cấp bên ngoài JAR; dùng `Path` và một property để chỉ thư mục lưu.
3. Giữ `application.yml` làm mặc định không nhạy cảm; dùng profile, config ngoài hoặc environment variable cho sự khác biệt giữa các môi trường.
4. Ghi rõ working directory trong Run Configuration hoặc script khởi chạy nếu có dùng đường dẫn tương đối.
5. Sử dụng đúng chữ hoa/thường trong tên resource, dấu `/` cho tên đường dẫn classpath và encoding rõ ràng như UTF-8 khi đọc văn bản.
6. Không hard-code đường dẫn cá nhân như `C:\Users\someone\Desktop\...` hoặc `/home/someone/projects/...` vào logic ứng dụng.
7. Dùng `jar --list --file` để kiểm tra thứ thực sự được phát hành khi nghi ngờ lỗi đóng gói resource.

### Bài luyện tập A: Resource không phụ thuộc source tree

Tạo `src/main/resources/messages/welcome.txt`, thêm endpoint đọc bằng `Resource#getInputStream()` và chạy bằng IDE. Build JAR rồi chạy `java -jar` từ thư mục khác source tree. So sánh kết quả endpoint. Thay tạm thành `Path.of("src/main/resources/messages/welcome.txt")` để quan sát vì sao cách đọc filesystem không ổn định, rồi khôi phục cách đọc classpath.

### Bài luyện tập B: Một JAR, nhiều profile

Tạo `application.yml` và `application-dev.yml` với hai giá trị `app.greeting`. Chạy cùng một artifact với và không với `--spring.profiles.active=dev`. Giải thích nguồn cấu hình nào quyết định phản hồi của endpoint.

### Bài luyện tập C: Đường dẫn ghi file theo môi trường

Cấu hình `app.data-directory=./var/data`, quan sát thư mục output khi chạy từ hai working directory. Sau đó cung cấp `APP_DATA_DIRECTORY` bằng đường dẫn tuyệt đối và kiểm tra file được ghi về nơi đã chỉ định. Việc này cho thấy resource đóng gói và dữ liệu runtime có vòng đời riêng.

### Bài luyện tập D: Kiểm tra artifact

Dùng `jar --list --file <ten-jar>` để tìm `BOOT-INF/classes/messages/welcome.txt` và `BOOT-INF/classes/application.yml`. Nếu thiếu, kiểm tra đúng tệp nguồn và cơ chế đóng gói trước khi thay đổi Java code.

Sau các bài tập, bạn cần phân biệt được một đường dẫn dùng classpath hay filesystem, hiểu vì sao cùng một tệp `application.yml` có thể bị cấu hình runtime ghi đè, và tổ chức mã nguồn sao cho **resource đi cùng bản build** còn **cấu hình, dữ liệu và quyền filesystem** được xác định rõ khi triển khai. Đây là nền tảng để ứng dụng Spring Boot vận hành nhất quán từ IDE đến executable JAR.
