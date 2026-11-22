# Chạy từ main, IDE, bootRun hoặc lệnh tương ứng của Maven

Một ứng dụng Spring Boot có thể được khởi động theo nhiều cách: gọi trực tiếp phương thức `main(...)`, nhấn **Run** trong IDE, chạy tác vụ **`bootRun`** của Gradle hoặc dùng **`spring-boot:run`** của Maven. Các cách này nhìn khác nhau ở thao tác bên ngoài nhưng thường dẫn tới cùng một điểm bắt đầu: **`SpringApplication.run(...)`** khởi tạo Spring application context.

Việc phân biệt các cách chạy giúp bạn xử lý những tình huống thực tế: chạy nhanh khi phát triển, đặt breakpoint để debug, truyền profile và tham số dòng lệnh, chọn đúng module trong project nhiều module, hoặc lý giải vì sao chạy từ IDE thành công nhưng chạy JAR lại lỗi.

**Mục tiêu của bài học:**

- Hiểu vai trò của lớp có `main` và annotation `@SpringBootApplication`.
- Chạy ứng dụng từ Java `main` và từ IDE.
- Chạy bằng Gradle `bootRun` hoặc Maven `spring-boot:run`.
- Truyền application arguments, JVM options, environment variables và Spring profiles đúng cách.
- Phân biệt chạy trực tiếp từ classpath với chạy bản đóng gói bằng `java -jar`.
- Chẩn đoán lỗi thiếu main class, sai module, thiếu dependency, port bị chiếm hoặc khác biệt working directory.

Các ví dụ dùng Spring Boot với Java và một web endpoint nhỏ. Tên task, plugin configuration và hành vi mặc định có thể khác giữa các dòng Spring Boot, Gradle hoặc Maven; khi áp dụng cần dùng các phiên bản tương thích do dự án quản lý.

## 1. Một ứng dụng Spring Boot khởi động từ đâu?

Điểm vào Java thông thường là phương thức:

```java
public static void main(String[] args)
```

Trong Spring Boot, phương thức này thường gọi:

```java
SpringApplication.run(OrdersApplication.class, args);
```

Ví dụ hoàn chỉnh:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Thành phần cần hiểu:

| Thành phần | Vai trò |
|---|---|
| `OrdersApplication` | Lớp bootstrap của ứng dụng |
| `main(String[] args)` | Điểm vào do Java launcher hoặc công cụ chạy gọi |
| `@SpringBootApplication` | Kết hợp cấu hình Spring Boot, auto-configuration và component scanning |
| `SpringApplication.run(...)` | Chuẩn bị environment, tạo/refresh context và hoàn tất startup |
| `args` | Application arguments được truyền cho Spring Boot |
| `ApplicationContext` | Container quản lý bean và vòng đời ứng dụng |

Chú ý: `@SpringBootApplication` không phải tên bắt buộc của class. Bạn có thể đặt `CatalogApplication`, `BillingServer` hoặc tên khác. Điều quan trọng là package, annotations, classpath và logic bootstrap được cấu hình nhất quán.

## 2. SpringApplication.run(...) làm những gì?

Khi Java gọi `main`, Spring Boot tiếp tục thực hiện nhiều bước. Ở mức khái quát:

```text
Java launcher / IDE / Gradle / Maven
                 │
                 ▼
        main(String[] args)
                 │
                 ▼
       SpringApplication.run(...)
                 │
                 ▼
       Chuẩn bị Environment
       (properties, profiles, args)
                 │
                 ▼
       Chọn ApplicationContext
       NONE / SERVLET / REACTIVE
                 │
                 ▼
         Đăng ký cấu hình
         và bean definitions
                 │
                 ▼
      Refresh ApplicationContext
      khởi tạo các bean cần thiết
                 │
                 ▼
     Khởi động server nếu là web app
                 │
                 ▼
      ApplicationRunner và
      CommandLineRunner
                 │
                 ▼
       ApplicationReadyEvent
                 │
                 ▼
       Ứng dụng chạy bình thường
```

Các mốc trên được giản lược để học tư duy khởi động. Chi tiết lifecycle và event timing có thể thay đổi theo ngữ cảnh web/non-web.

**Điểm mấu chốt:** Gradle hay Maven không thay thế `SpringApplication`. Chúng chuẩn bị classpath, compiler/runtime và gọi ứng dụng theo cấu hình; Spring Boot vẫn thực hiện quá trình tạo Spring context.

## 3. Một project Spring Boot tối thiểu

Giả sử cấu trúc ứng dụng:

```text
orders-service/
├── build.gradle               # Nếu dùng Gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── pom.xml                    # Nếu dùng Maven, thay cho Gradle files
├── mvnw
├── mvnw.cmd
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/orders/
    │   │       ├── OrdersApplication.java
    │   │       └── GreetingController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/
```

Một project thật thường **chọn Gradle hoặc Maven**, không nhất thiết có cả hai. Sơ đồ gộp các tên file để bạn nhận diện chúng khi làm việc với từng build tool.

Controller để xác nhận ứng dụng đã phục vụ HTTP:

```java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello Spring Boot";
    }
}
```

Cấu hình:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: orders-service

server:
  port: 8080
```

Ví dụ này cần Spring MVC/Servlet web starter tương thích với phiên bản Boot. Nếu project chỉ có starter nền tảng, ứng dụng có thể chạy như non-web application và không tạo HTTP endpoint.

Khi server sẵn sàng, có thể kiểm tra:

```bash
curl http://localhost:8080/hello
```

Dự kiến phần body:

```text
Hello Spring Boot
```

Nếu chạy bằng profile hoặc port khác, phải thay URL kiểm tra tương ứng.

## 4. Chạy trực tiếp từ main(String[] args)

Cách cơ bản nhất là chạy phương thức `main` của một Java class. Thao tác có thể được thực hiện bởi IDE, build tool hoặc Java launcher với classpath đã được chuẩn bị đầy đủ.

Ví dụ:

```java
@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Giả sử ứng dụng nhận đối số:

```text
--spring.profiles.active=dev
--server.port=8081
```

`args` trong `main` sẽ chứa hai chuỗi tương ứng nếu chúng được truyền dưới dạng application arguments.

Có thể lưu đối tượng context:

```java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(OrdersApplication.class, args);

    // Không cần thao tác gì thêm với context trong web app đơn giản.
}
```

Cần import `ConfigurableApplicationContext` từ Spring. Đối với web service thông thường, bạn chỉ cần gọi `SpringApplication.run(...)` mà không cần giữ reference này.

### 4.1. Không tự tạo service bằng new trong main

Không nên làm:

```java
public static void main(String[] args) {
    OrderService service = new OrderService();
    service.run();
}
```

nếu `OrderService` phụ thuộc Spring bean injection, transaction, configuration hoặc các proxy do container quản lý. Object tự tạo bằng `new` không tự tham gia lifecycle của Spring.

Nếu cần thực thi một tác vụ sau khi context khởi động, hãy cân nhắc `CommandLineRunner` hoặc `ApplicationRunner` dưới dạng Spring bean.

```java
@Component
public class StartupNotice implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Startup arguments: " + args.length);
    }
}
```

Runner được Spring Boot gọi trong giai đoạn startup, với các application arguments đã được truyền vào `SpringApplication.run`.

## 5. Chạy từ IDE: IntelliJ IDEA, Eclipse và VS Code

IDE thường nhận diện một Java class có `main` và cung cấp thao tác Run/Debug. Cách đặt nút và tên menu có thể khác giữa IDE hoặc extension, nhưng các thành phần cấu hình về bản chất tương tự.

Quy trình thường gặp:

1. Mở project ở thư mục chứa `pom.xml` hoặc `build.gradle`.
2. Để IDE import/sync dependency và chọn đúng JDK.
3. Mở lớp `OrdersApplication`.
4. Chạy phương thức `main(String[] args)` qua nút Run.
5. Quan sát startup log ở Run console.
6. Truy cập endpoint kiểm tra nếu đây là ứng dụng web.

IDE có thể biên dịch các Java classes vào output directory rồi chạy Java launcher với classpath do hệ thống project model tạo. Nó không bắt buộc build JAR trước.

### 5.1. Các trường thường thấy trong Run Configuration

| Trường | Dùng cho | Ví dụ |
|---|---|---|
| Main class | Lớp chứa điểm vào | `com.example.orders.OrdersApplication` |
| Module/classpath | Chọn source set và dependencies | Module `orders-service` |
| JDK/JRE | Java runtime của tiến trình | JDK được dự án hỗ trợ |
| Program arguments | Truyền vào `main(String[] args)` | `--spring.profiles.active=dev` |
| VM options | JVM flags và system properties | `-Xmx512m -Duser.timezone=UTC` |
| Environment variables | Biến môi trường của tiến trình | `SPRING_PROFILES_ACTIVE=dev` |
| Working directory | Vị trí resolve relative paths | Thư mục root của module |

Không nên nhầm ba nhóm đầu vào:

- **Program arguments** đi vào `main` rồi tới `SpringApplication.run`.
- **VM options** được JVM xử lý, ví dụ `-Xmx` và `-Dkey=value`.
- **Environment variables** có sẵn qua `System.getenv(...)` và có thể được Spring Boot đưa vào `Environment`.

### 5.2. Run và Debug khác gì?

Chạy **Run** thường khởi động bình thường. Chạy **Debug** cho phép IDE attach debugger, đặt breakpoint và quan sát variables/thread/stack.

Ví dụ đặt breakpoint trong:

```java
@GetMapping("/hello")
public String hello() {
    return "Hello Spring Boot";
}
```

Breakpoint này sẽ bị dừng khi HTTP request đến endpoint và method được thực thi, không nhất thiết khi server vừa khởi động.

Nếu breakpoint trong `main` không trúng, cần kiểm tra IDE đang chạy đúng main class và debug configuration chứ không phải một test hoặc ứng dụng khác.

### 5.3. IDE có thể dùng build tool để chạy

Một số IDE cho phép delegate việc build/run sang Gradle hoặc Maven. Khi bật tùy chọn đó, nút Run trong IDE có thể gọi task/goal của build tool thay vì dùng Java launch trực tiếp do IDE quản lý.

Vì vậy, “Run từ IDE” là thao tác của người phát triển, không phải một cơ chế runtime hoàn toàn tách biệt. Khi behavior khác dự kiến, kiểm tra IDE đang dùng **IDE runner** hay **Gradle/Maven delegated run**.

## 6. Gradle bootRun là gì?

Nếu project áp dụng Spring Boot Gradle plugin và các plugin cần thiết, Gradle cung cấp task **`bootRun`** để chạy Spring Boot application từ classpath của project.

Trong project sử dụng Gradle wrapper, từ thư mục chứa `gradlew`:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Trong những project dùng Kotlin DSL, tên file thường là `build.gradle.kts` thay vì `build.gradle`, nhưng task vẫn là `bootRun` khi plugin được cấu hình.

`bootRun` thường là một task dựa trên `JavaExec`: nó khởi chạy ứng dụng với **runtime classpath** gồm classes/resources và dependencies cần thiết.

**Không cần tạo executable JAR trước khi gọi `bootRun`.** Gradle sẽ xử lý các task prerequisites cần thiết như compile/process resources theo cấu hình dự án.

## 7. Gradle build.gradle tối thiểu cho ví dụ

Một cấu hình Gradle Groovy DSL mang tính minh họa:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

**Lưu ý:** số version và yêu cầu Java trong đoạn này là ví dụ về một tổ hợp cho dòng Boot 3.x, không phải khuyến nghị chọn version mới nhất hay version bắt buộc cho mọi project. Trong dự án thực tế, dùng plugin/dependency versions đang được quản lý và tương thích với runtime của bạn.

Nếu build đã được tạo bởi Spring Initializr, thường không cần viết lại toàn bộ cấu hình này. Bạn chỉ cần xác định module áp dụng Spring Boot plugin và chạy task đúng nơi.

### 7.1. Vì sao task bootRun có thể không tồn tại?

Ví dụ lỗi:

```text
Task 'bootRun' not found in root project
```

Nguyên nhân thường gặp:

- Chạy từ project/module không áp dụng Spring Boot Gradle plugin.
- Dự án chỉ dùng Maven.
- Multi-module build: root project là aggregator, còn ứng dụng nằm ở subproject.
- Plugin chưa được áp dụng hoặc cấu hình build lỗi trước khi task được tạo.
- Gõ sai tên task hoặc chọn sai Gradle project.

Hãy kiểm tra file build và module chạy, thay vì cố chạy `bootRun` ở mọi thư mục.

## 8. Truyền application arguments cho bootRun

Một nhu cầu phổ biến là bật profile và đổi port:

```bash
./gradlew bootRun --args="--spring.profiles.active=dev --server.port=8081"
```

Với Windows PowerShell:

```powershell
.\gradlew.bat bootRun '--args=--spring.profiles.active=dev --server.port=8081'
```

Trong ví dụ này, phần sau `--args` là **application arguments** được Gradle chuyển tới `main(String[] args)`, không phải arguments của Gradle build itself.

Sự khác nhau:

```text
./gradlew bootRun
    │      │
    │      └── Gradle task
    └── Gradle launcher

--args="--spring.profiles.active=dev --server.port=8081"
    │
    └── Args cho chương trình được bootRun khởi chạy
```

Về mặt ý nghĩa, ứng dụng Spring Boot có thể nhận:

```text
args[0] = --spring.profiles.active=dev
args[1] = --server.port=8081
```

**Chú ý quoting:** cách shell phân tích dấu nháy khác nhau giữa Bash, PowerShell và CMD. Nếu Gradle báo lỗi option hoặc chương trình nhận một chuỗi gộp ngoài dự kiến, kiểm tra dấu quote theo shell đang dùng.

### 8.1. Cấu hình arguments trực tiếp trong build script

Groovy DSL:

```groovy
tasks.named('bootRun') {
    args '--spring.profiles.active=dev'
    args '--server.port=8081'
}
```

Cách này hữu ích cho cấu hình phát triển cố định. Tuy nhiên, không nên hard-code production secrets hoặc deployment-specific settings trong repository.

Nếu muốn arguments linh hoạt theo môi trường, có thể truyền từ terminal hoặc CI runner.

## 9. Truyền JVM arguments cho bootRun

Cần phân biệt JVM arguments với application arguments. Ví dụ:

- `-Xmx512m`: giới hạn heap JVM.
- `-Duser.timezone=UTC`: system property của JVM.
- `--server.port=8081`: Spring Boot application argument.

Trong Gradle Groovy DSL, có thể cấu hình JVM options cho task:

```groovy
tasks.named('bootRun') {
    jvmArgs '-Xmx512m', '-Duser.timezone=UTC'
}
```

Các options này áp dụng cho JVM chạy ứng dụng trong task, không phải các option tùy ý cho Gradle daemon.

Ngược lại, việc đặt một `-D...` khi gọi Gradle launcher có thể tạo system property cho **Gradle process** hoặc task configuration, không đồng nghĩa chắc chắn property đó được truyền sang JVM của ứng dụng được fork/chạy. Hãy cấu hình qua cơ chế `bootRun` hỗ trợ khi mục tiêu là JVM của ứng dụng.

Thực tế cần kiểm tra:

1. Option được đặt cho Java process nào?
2. Spring Boot nhận nó từ `System.getProperty` hay `args`?
3. Run configuration có dùng Gradle daemon với JVM riêng không?

## 10. Chạy Gradle từ project nhiều module

Ví dụ:

```text
workspace/
├── settings.gradle
├── build.gradle
├── common-domain/
│   └── build.gradle
├── orders-app/
│   └── build.gradle
└── billing-app/
    └── build.gradle
```

Trong đó `orders-app` và `billing-app` là executable Spring Boot modules, còn `common-domain` là thư viện.

Từ root project, có thể chạy:

```bash
./gradlew :orders-app:bootRun
```

Hoặc:

```bash
./gradlew :billing-app:bootRun --args="--spring.profiles.active=dev"
```

Dấu `:` trong tên task chỉ đường dẫn subproject theo Gradle project path.

Đừng dùng:

```bash
./gradlew bootRun
```

rồi mặc định project sẽ chọn ứng dụng bạn muốn, vì root project có thể không có task `bootRun` hoặc task resolution không phù hợp với multi-module setup.

### 10.1. Main class trong module có nhiều entry point

Nếu cùng một module có nhiều classes chứa `main`, Boot Gradle plugin có thể không xác định được main class duy nhất theo cách tự động.

Có thể cấu hình tường minh, ví dụ Groovy DSL:

```groovy
springBoot {
    mainClass = 'com.example.orders.OrdersApplication'
}
```

Hoặc với task:

```groovy
tasks.named('bootRun') {
    mainClass = 'com.example.orders.OrdersApplication'
}
```

Các DSL properties có thể khác theo plugin/version; hãy đối chiếu API của version dự án.

Nếu cần nhiều chế độ chạy độc lập (ví dụ server và migration tool), cân nhắc tạo task JavaExec riêng hoặc module riêng, thay vì phụ thuộc vào suy luận main class thiếu rõ ràng.

## 11. Maven spring-boot:run là gì?

Với dự án Maven có Spring Boot Maven plugin được cấu hình phù hợp, goal:

```bash
mvn spring-boot:run
```

cho phép chạy ứng dụng mà không cần tự đóng gói executable JAR trước.

Nếu dự án có Maven wrapper:

```bash
./mvnw spring-boot:run
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Maven thực hiện các bước cần thiết theo lifecycle/plugin configuration để có compiled classes, resources và dependencies phù hợp khi chạy. Lệnh `spring-boot:run` là một **Maven plugin goal**, không phải câu lệnh riêng của Java launcher.

Hãy chạy ở module chứa Maven plugin và application main class, hoặc chọn đúng module với Maven reactor options.

## 12. pom.xml ví dụ cho Spring Boot Maven plugin

Một cấu hình `pom.xml` minh họa:

```xml
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
    <artifactId>orders-service</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

Đây chỉ là ví dụ cấu trúc với dòng Boot 3.x, không có ý khẳng định bản này là phiên bản mới nhất. Một số dự án kế thừa parent hoặc sử dụng BOM/pluginManagement riêng; cách khai báo plugin và version sẽ khác.

Trong môi trường có Maven wrapper, thường ưu tiên `mvnw` để dùng Maven version dự án chỉ định, tương tự `gradlew` của Gradle.

### Maven khác Gradle ở điểm nào?

- Gradle sử dụng **task** như `bootRun`.
- Maven sử dụng **plugin goal** như `spring-boot:run`.
- Cả hai có thể chạy application trực tiếp từ compiled output/classpath.
- Cả hai vẫn đưa execution đến điểm vào `main` hoặc main class do build configuration chọn.
- Cả hai có thể chọn profiles, properties và JVM arguments theo cơ chế riêng.

Đừng cố dùng `./gradlew bootRun` trong một Maven-only project hoặc `mvn spring-boot:run` trong một Gradle-only project.

## 13. Truyền arguments cho Maven spring-boot:run

Maven Spring Boot plugin hỗ trợ plugin property cho application arguments trong các phiên bản phù hợp:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=dev --server.port=8081"
```

Trong Windows PowerShell, có thể cần điều chỉnh quoting để một `-D...` được Maven nhận đúng:

```powershell
.\mvnw.cmd spring-boot:run '-Dspring-boot.run.arguments=--spring.profiles.active=dev --server.port=8081'
```

Với cả hai ví dụ, ý định là truyền hai **application arguments** cho Spring Boot:

```text
--spring.profiles.active=dev
--server.port=8081
```

Cách shell xử lý quote rất quan trọng vì `-Dspring-boot.run.arguments` là một argument Maven chứa nhiều phần. Nếu ứng dụng không nhận đúng, hãy kiểm tra cách Maven plugin báo arguments hoặc thử một option đơn giản trước.

### 13.1. Tham số Maven cho profile Spring

Plugin còn có property chuyên cho Spring profiles, ví dụ:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

Tùy version và cấu hình, bạn cũng có thể dùng `spring-boot.run.arguments` như đã thấy.

**Không nhầm Maven profile với Spring profile.**

```bash
./mvnw -Pdevelopment spring-boot:run
```

`-Pdevelopment` là cách kích hoạt **Maven build profile** tên `development`. Nó không tự có nghĩa Spring Boot sẽ active profile `dev`, trừ khi project cấu hình ánh xạ/biến chuyển tương ứng.

| Điều cần thay đổi | Cơ chế |
|---|---|
| Spring Boot runtime profile | `--spring.profiles.active=dev` hoặc plugin property `spring-boot.run.profiles` |
| Maven build profile | `mvn -PprofileName ...` |
| Gradle build configuration | Gradle script/project properties/task configuration |
| JVM system property | `-Dname=value` cho JVM app qua plugin/task phù hợp |

## 14. JVM arguments với Maven plugin

Ví dụ cần đặt heap size cho JVM của ứng dụng:

```bash
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-Xmx512m -Duser.timezone=UTC"
```

Property `spring-boot.run.jvmArguments` hướng tới JVM arguments của ứng dụng do Maven Spring Boot plugin chạy trong phiên bản hỗ trợ.

Phải phân biệt:

```bash
mvn -Duser.timezone=UTC spring-boot:run
```

với:

```bash
mvn spring-boot:run -Dspring-boot.run.jvmArguments="-Duser.timezone=UTC"
```

Câu lệnh đầu dùng Maven `-D` để đặt user property trong build context; nó không nhất thiết tương đương một JVM system property trên process ứng dụng. Câu lệnh thứ hai có ý định chuyển option đó vào JVM của ứng dụng.

Trong Windows shell, cú pháp dấu nháy có thể cần điều chỉnh.

Nếu bạn cần environment variable của process ứng dụng, có thể đặt biến trong shell trước khi gọi Maven wrapper hoặc dùng tính năng plugin cấu hình environment variables khi version hỗ trợ.

## 15. Maven multi-module: chọn đúng module

Ví dụ:

```text
shop-parent/
├── pom.xml
├── shop-common/
│   └── pom.xml
├── orders-api/
│   └── pom.xml
└── billing-api/
    └── pom.xml
```

Nếu `orders-api` là Spring Boot application module, có thể chọn module bằng Maven reactor:

```bash
./mvnw -pl orders-api -am spring-boot:run
```

Trong thực tế, lệnh này có thể yêu cầu điều chỉnh dựa trên cách plugin goal chạy trong reactor và các module phụ thuộc. `-pl` chọn project, `-am` bao gồm các module liên quan, nhưng nếu goal `spring-boot:run` chạy trên các library module không có main class, có thể gây lỗi.

Một cách khác là cài/build dependency modules trước theo workflow dự án, sau đó chạy plugin goal trong riêng module ứng dụng:

```bash
cd orders-api
../mvnw spring-boot:run
```

Cách chọn module phải phù hợp build structure. Đừng mặc định plugin goal nên chạy trên mọi module, đặc biệt khi parent chỉ là `pom` aggregator hoặc common module là thư viện.

### 15.1. Nhiều main classes với Maven

Khi Maven plugin không suy luận được main class phù hợp, có thể khai báo tường minh:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.orders.OrdersApplication</mainClass>
    </configuration>
</plugin>
```

Nếu project có plugin configuration từ parent, nên chỉnh ở đúng module để không ảnh hưởng sibling modules.

## 16. Bảng so sánh bốn cách chạy chính

| Cách chạy | Ai chuẩn bị classpath? | Thường dùng khi | Cần đóng gói JAR trước? |
|---|---|---|---|
| Gọi `main` qua IDE | IDE/project model | Viết code, debug nhanh | Không |
| IDE delegated run | Gradle/Maven được IDE gọi | Muốn behavior theo build tool | Không bắt buộc |
| Gradle `bootRun` | Gradle + Spring Boot plugin | Dev chạy từ terminal/CI thử nghiệm | Không |
| Maven `spring-boot:run` | Maven + Spring Boot plugin | Dev chạy từ terminal/Maven workflow | Không |
| `java -jar` | Java launcher đọc executable JAR đã build | Chạy artifact đã đóng gói | Có |

Trong bốn cách dev đầu, code/classes/resources thường đến từ output directory và dependency classpath được công cụ quản lý. Cách thứ năm sử dụng một artifact đã được đóng gói.

**Không nên dùng “không cần build gì” để mô tả `bootRun` hoặc `spring-boot:run`.** Build tool vẫn có thể compile classes và xử lý resources theo dependency graph; điều không bắt buộc là tạo executable archive trước khi chạy.

## 17. Khác biệt giữa bootRun và java -jar

Hai lệnh:

```bash
./gradlew bootRun
```

và:

```bash
java -jar build/libs/orders-service-0.0.1-SNAPSHOT.jar
```

không giống nhau về hình thức chạy.

### bootRun

- Thường dùng classes/resources từ build output.
- Sử dụng runtime classpath do Gradle tạo.
- Thuận tiện khi đang sửa code thường xuyên.
- Có thể kết hợp IDE hoặc DevTools để tăng tốc vòng lặp phát triển.
- Không kiểm chứng được mọi vấn đề chỉ xảy ra khi đóng gói executable JAR.

### java -jar

- Chạy archive đã build.
- Phụ thuộc cách JAR được đóng gói, manifest và Spring Boot loader.
- Phản ánh gần hơn hành vi artifact được triển khai.
- Không tự lấy code Java mới nhất nếu JAR chưa được rebuild.
- Có thể bộc lộ lỗi resource path, packaging hoặc thiếu dependency mà cách dev run chưa gặp.

Nếu ứng dụng chỉ hoạt động với `bootRun` nhưng lỗi khi `java -jar`, hãy điều tra packaging, resources và classpath thay vì kết luận Spring Boot startup logic khác nhau hoàn toàn.

## 18. Tạo và chạy executable JAR

Với Gradle Spring Boot plugin, task đóng gói executable archive thường là:

```bash
./gradlew bootJar
```

Sau đó chạy JAR thực tế được tạo:

```bash
java -jar build/libs/orders-service-0.0.1-SNAPSHOT.jar
```

Với Maven Spring Boot plugin, workflow thông thường:

```bash
./mvnw package
```

Sau đó:

```bash
java -jar target/orders-service-0.0.1-SNAPSHOT.jar
```

Tên file ví dụ phụ thuộc `artifactId`, `version` và build configuration. Không nên copy nguyên tên nếu project tạo một artifact khác.

Một JAR có thể chỉ là **plain library JAR** không có Spring Boot executable layout/launcher phù hợp. `java -jar` yêu cầu archive có manifest/main entry hợp lệ. Đừng giả định mọi `jar` được tạo ra đều là Spring Boot executable JAR.

Nếu `java -jar` báo không có main manifest attribute hoặc không tìm được main class, cần kiểm tra artifact được tạo bởi task/plugin nào.

## 19. “Chạy từ source” không có nghĩa bỏ qua dependency

Chạy trực tiếp phương thức `main` yêu cầu classpath đầy đủ:

- Classes compile từ `src/main/java`.
- Resources từ `src/main/resources`.
- Spring Boot libraries.
- Dependencies của starter/service/client theo runtime scope.
- Logging implementation được dùng.
- Các module project mà app phụ thuộc.

Chỉ chạy:

```bash
java com.example.orders.OrdersApplication
```

khi không cấu hình classpath thường không đủ với ứng dụng Spring Boot thực tế.

IDE và build tools thuận tiện vì chúng **lắp classpath** cho bạn.

Bảng nguồn phổ biến:

| Source | Khi chạy từ IDE/bootRun/Maven | Khi chạy executable JAR |
|---|---|---|
| `src/main/java` | Compile thành `.class` trong output dir | Classes nằm trong archive |
| `src/main/resources` | Resources trên runtime classpath | Resources được đóng gói vào archive |
| Runtime dependencies | Các JAR trên classpath của process | Được bundle hoặc được loader quản lý theo packaging |
| `src/test/java` | Thường không thuộc runtime app chính | Không đóng vào executable app thông thường |
| `src/test/resources` | Thường không thuộc runtime app chính | Không đóng vào executable app thông thường |

Nếu có dependencies ở scope không phù hợp (test-only, provided, optional), behavior runtime có thể khác giữa build, IDE và JAR. Hãy kiểm tra dependency scopes và packaging thay vì tự chép JAR thủ công.

## 20. Vai trò của working directory

Một lỗi phổ biến: chạy từ IDE đọc được file, chạy từ terminal thì không; hoặc ngược lại.

Giả sử code:

```java
Path path = Path.of("data/input.csv");
List<String> lines = Files.readAllLines(path);
```

Đường dẫn tương đối `data/input.csv` được resolve dựa trên **current working directory của Java process**.

Các môi trường có thể chọn working directory khác nhau:

- IDE thường có default dựa trên project/module, nhưng có thể cấu hình.
- Gradle task có cấu hình working directory riêng.
- Maven plugin chạy trong ngữ cảnh project/module.
- `java -jar` chạy từ thư mục mà người vận hành đứng khi gọi lệnh, trừ khi process manager thay đổi.
- Container có `WORKDIR` hoặc current directory riêng.

Vì vậy, không nên viết code nghiệp vụ với giả định working directory luôn là root source project.

### 20.1. Resource trên classpath khác file trên disk

Khi cần đọc một resource được đóng gói trong `src/main/resources`, nên sử dụng classpath resource API.

Ví dụ:

```java
try (InputStream input = getClass()
        .getResourceAsStream("/templates/email.html")) {

    if (input == null) {
        throw new IllegalStateException("Missing email template");
    }

    // Đọc nội dung input stream.
}
```

Cách này có thể hoạt động cả từ output directory và trong executable JAR, miễn resource được đóng gói đúng.

Ngược lại:

```java
new File("src/main/resources/templates/email.html")
```

phụ thuộc source tree còn tồn tại tại runtime. Khi deploy JAR, đường dẫn `src/main/resources` có thể hoàn toàn không có trên máy chạy.

Phân biệt rõ **resource bundled trong artifact** với **external file được cung cấp ngoài ứng dụng**.

## 21. Profile và property khi chạy ở mỗi môi trường

Đặt `spring.profiles.active` có thể dùng các con đường khác nhau.

### IDE

Trong **Program arguments**:

```text
--spring.profiles.active=dev
```

Hoặc trong **Environment variables**:

```text
SPRING_PROFILES_ACTIVE=dev
```

### Gradle

```bash
./gradlew bootRun --args="--spring.profiles.active=dev"
```

### Maven

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

### Executable JAR

```bash
java -jar app.jar --spring.profiles.active=dev
```

Các cách này đều hướng tới việc Spring Boot nhận được active profile tương ứng. Nhưng **đường truyền** từ launcher đến ứng dụng là khác nhau.

Nếu cùng lúc cấu hình profile ở environment, application.yml, command line hoặc plugin args, thứ tự ưu tiên các property sources sẽ quyết định giá trị cuối cùng. Khi profile khác kỳ vọng, kiểm tra cả nguồn cấu hình khởi chạy và log startup.

## 22. Application arguments, JVM options và environment variables

Đây là ba khái niệm thường xuyên bị trộn lẫn:

| Loại | Ví dụ | Ai xử lý trước? | Spring Boot tiếp cận qua |
|---|---|---|---|
| Application arguments | `--server.port=8081` | `main(String[] args)`/SpringApplication | Command-line property source, runners |
| JVM system property | `-Duser.timezone=UTC` | Java launcher/JVM | `System.getProperty`, Environment |
| JVM memory flag | `-Xmx512m` | JVM | Runtime JVM configuration |
| Environment variable | `SPRING_PROFILES_ACTIVE=dev` | OS process environment | `System.getenv`, Environment |

Ví dụ chạy executable JAR:

```bash
java -Xmx512m -Duser.timezone=UTC -jar app.jar --server.port=8081
```

Cú pháp vị trí có ý nghĩa:

- `-Xmx512m` và `-Duser.timezone=UTC` đứng trước `-jar` là JVM options.
- `--server.port=8081` đứng sau tên archive là application argument.

Khi dùng Gradle/Maven, đừng gắn mọi option vào một trường rồi mong công cụ tự hiểu. `bootRun` và `spring-boot:run` cung cấp cách truyền mỗi nhóm riêng.

## 23. Trường hợp chạy non-web application

Không phải Spring Boot application nào cũng mở HTTP port. Nếu dùng Spring Boot để chạy batch/CLI/worker, có thể chọn non-web application:

```java
@SpringBootApplication
public class ImportApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ImportApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

Một runner có thể làm việc:

```java
@Component
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Import job arguments: " + args.length);
    }
}
```

Với cấu hình NONE, ứng dụng không tạo embedded web server của Boot. Bạn vẫn có Spring container, dependency injection và runners.

Dù chạy bằng IDE, `bootRun` hay `spring-boot:run`, loại web application là quyết định của ứng dụng/classpath/configuration, không phải do riêng build tool luôn áp đặt.

Nếu một app chỉ có Spring Boot starter nền tảng mà không có web stack, Boot thường suy luận non-web mode; không nên đợi endpoint trên port 8080 nếu project không có server runtime phù hợp.

## 24. Spring Boot DevTools trong quá trình phát triển

`spring-boot-devtools` có thể hỗ trợ vòng lặp phát triển như restart khi classpath thay đổi và một số cấu hình development tiện lợi.

Ví dụ Gradle:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

Ví dụ Maven với dependency tùy chọn trong những dự án phù hợp:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

DevTools có ích khi:

- Chạy từ IDE.
- Chạy từ compiled classes qua Gradle/Maven.
- Bạn thường xuyên chỉnh code rồi compile.
- Ứng dụng cần restart nhanh khi classpath thay đổi.

**Không nên hiểu DevTools là tự động hot-swap mọi source change.** Thay đổi source phải được IDE hoặc build process biên dịch thành class/resource thay đổi trên classpath để cơ chế restart có thể phát hiện.

Ngoài ra, behavior restart còn phụ thuộc cách chạy app và cấu hình classloader. DevTools không phải giải pháp thay thế build/redeploy cho executable artifact production.

## 25. Chạy và dừng ứng dụng

Khi chạy một Spring Boot web service từ terminal:

```bash
./gradlew bootRun
```

terminal thường giữ tiến trình chạy cho đến khi server dừng.

Có thể gửi tín hiệu dừng theo môi trường, ví dụ **Ctrl+C** trong terminal. IDE có nút Stop hoặc Terminate. Cách dừng từ IDE, shell, systemd và container có thể khác nhau về tín hiệu và thời hạn chờ.

Nếu dừng **graceful**, Spring có cơ hội thực hiện shutdown lifecycle: đóng application context, dừng web server, giải phóng resource và chạy destroy callbacks theo cấu hình.

Nếu bị force kill hoặc JVM crash, không thể bảo đảm toàn bộ cleanup logic chạy.

### 25.1. Không mở hai instance vô tình trên cùng port

Nếu một instance đang giữ port 8080 rồi bạn chạy instance thứ hai cùng cấu hình, có thể xuất hiện lỗi:

```text
Port 8080 was already in use
```

Các cách xử lý:

1. Dừng instance cũ đang chạy trong IDE/terminal.
2. Chọn port khác khi cần chạy song song.
3. Kiểm tra process đang chiếm port trên hệ điều hành.
4. Đảm bảo không có cả IDE Run và `bootRun` chạy cùng app mà bạn không nhận ra.

Đổi port:

```bash
./gradlew bootRun --args="--server.port=8081"
```

hoặc trong Maven/JAR theo cơ chế arguments tương ứng.

## 26. Phân biệt process chạy app và process của build tool

Khi dùng IDE, Gradle hoặc Maven, có thể xuất hiện nhiều Java processes:

- IDE process.
- Gradle daemon.
- Maven launcher/plugin process.
- JVM chạy Spring Boot application.
- Test worker processes nếu build đồng thời kiểm thử.

Không phải mọi command-line option Java đều ảnh hưởng tất cả các process trên.

Ví dụ trong Gradle, một tùy chọn cho Gradle daemon có thể khác với một `jvmArgs` cho `bootRun`. Với Maven plugin, property `spring-boot.run.jvmArguments` hướng tới JVM của ứng dụng.

Điều này quan trọng khi:

- Kiểm tra heap bằng `-Xmx`.
- Attach debugger.
- Tính timeout hoặc memory usage.
- Đọc environment variables.
- Dừng tiến trình đúng.
- Phân biệt log của Gradle/Maven và log của Spring Boot.

Nếu hành vi không giống nhau giữa IDE và terminal, hãy xác định **tiến trình Java nào thực sự chạy main class**.

## 27. Chạy với remote debugger

IDE Debug thường tự cấu hình debugger. Nhưng đôi khi bạn muốn debug JVM được khởi chạy qua build tool hoặc một executable JAR.

Ví dụ JVM option JDWP phổ biến cho môi trường **local development**:

```text
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005
```

Với Java phiên bản hỗ trợ cú pháp trên, option cho phép debugger kết nối tới cổng 5005 trên loopback.

Với executable JAR:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
```

Với Gradle/Maven, cần truyền JDWP option qua cơ chế JVM arguments của application process; không phải qua application arguments.

Lưu ý an toàn:

- Không mở remote debugger công khai trên interface mạng production.
- Chỉ bind vào localhost hoặc dùng tunnel/controls đã được quản lý.
- Debugger có quyền quan sát/thay đổi execution, nên coi nó là giao diện vận hành nhạy cảm.
- Kiểm tra port 5005 chưa bị chiếm.

Với nhu cầu debug thông thường khi phát triển, nút **Debug** của IDE vẫn là cách ít cấu hình hơn.

## 28. Chạy từ IDE nhưng không thấy ứng dụng khởi động

Các nguyên nhân điển hình:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có nút Run ở main | IDE chưa import đúng project/JDK hoặc method signature không chuẩn | Sync project, kiểm tra `public static void main(String[] args)` |
| Lỗi ClassNotFound | Sai main class, module/classpath hoặc compile chưa thành công | Kiểm tra Run Configuration và output |
| NoClassDefFoundError | Runtime classpath thiếu dependency | Reimport Gradle/Maven, kiểm tra dependency scope |
| Bean không được scan | Main application nằm sai package hoặc cấu hình scan thiếu | Kiểm tra package hierarchy và `@SpringBootApplication` |
| Không có web server log | Không có web starter hoặc application type là NONE | Kiểm tra classpath và `spring.main.web-application-type` |
| Dừng ngay sau startup | Non-web app không có worker/thread giữ process | Kiểm tra runner và lifecycle |
| Breakpoint không trúng | Chạy Run thay vì Debug hoặc debugger attach sai process | Chọn Debug đúng main class |
| Config khác terminal | Program args/profile/working dir/env variables khác | So sánh Run Configuration |
| Port bị chiếm | Một instance khác đang chạy | Dừng process cũ hoặc đổi port |

### 28.1. Không nhìn thấy “Started ...” không luôn là lỗi

Một số ứng dụng không có logging đầy đủ, startup fail sớm, hoặc thông báo log bị lọc theo level. Hãy nhìn exit code/exception và trạng thái process, không suy luận chỉ từ một dòng log thiếu.

Nếu ứng dụng là batch job, nó có thể hoàn thành rồi thoát bình thường mà không mở web server.

## 29. bootRun lỗi: các nguyên nhân thường gặp

| Lỗi hoặc hiện tượng | Gợi ý xử lý |
|---|---|
| `Task 'bootRun' not found` | Kiểm tra Spring Boot Gradle plugin và project/subproject path |
| `Could not find or load main class` | Kiểm tra `mainClass`, package và classpath |
| `Unable to find a single main class` | Chỉ định main class tường minh |
| Lỗi dependency resolution | Kiểm tra repositories/network/dependency constraints và version |
| Java version không tương thích | Xem Gradle toolchain, `java -version` và Java compatibility của Boot |
| `--args` không có tác dụng | Kiểm tra quoting và task được chạy |
| Spring profile khác mong muốn | Kiểm tra args/env/IDE override và property source precedence |
| Build tool không thấy module | Kiểm tra `settings.gradle` và project path |
| Ứng dụng chạy nhưng exit ngay | Xác định non-web vs web app và job lifecycle |
| Build succeeded nhưng app báo startup failed | Phân biệt lỗi compilation với lỗi tạo Spring context |

### 29.1. Gradle wrapper và JDK

`gradlew` giúp dự án sử dụng Gradle distribution đã chỉ định trong wrapper. Tuy nhiên wrapper không tự chọn đúng JDK cho toàn bộ trường hợp.

Một số thứ cần phân biệt:

- JDK chạy Gradle daemon.
- JDK dùng làm Java toolchain biên dịch.
- JVM thực sự dùng để chạy `bootRun`.
- Java version mà Spring Boot phiên bản dự án yêu cầu.

Nếu Java version không tương thích, kiểm tra project build configuration và logs, không chỉ cài thêm một JDK mà chưa chọn nó ở IDE/build tool.

## 30. spring-boot:run lỗi: các nguyên nhân thường gặp

| Lỗi hoặc hiện tượng | Gợi ý xử lý |
|---|---|
| `No plugin found for prefix 'spring-boot'` | Kiểm tra Maven Spring Boot plugin được khai báo/resolve phù hợp |
| `Unable to find a suitable main class` | Kiểm tra module và plugin `mainClass` |
| `ClassNotFoundException` | Compile output hoặc runtime dependencies thiếu |
| Plugin chạy trên parent/library module | Chọn đúng application module trong Maven reactor |
| `-Pdev` không đổi Spring profile | Maven profile và Spring profile là hai cơ chế khác nhau |
| `spring-boot.run.arguments` bị tách sai | Kiểm tra quoting trong shell |
| JVM options không có tác dụng | Dùng đúng plugin JVM arguments, không chỉ Maven user property |
| Dependencies không tìm thấy | Kiểm tra Maven repositories, settings và network |
| Port đã được sử dụng | Dừng process cũ hoặc truyền `--server.port` khác |
| Main hoạt động trong IDE nhưng Maven fail | So sánh compiler settings, resources, dependency scopes và plugin config |

Có thể xem cấu hình Maven hiệu lực bằng các công cụ Maven phù hợp khi chẩn đoán, nhưng đừng vội thay đổi toàn bộ POM chỉ vì IDE Run thành công.

## 31. Các khác biệt dễ gây nhầm giữa IDE, Gradle, Maven và JAR

### 31.1. “IDE Run thành công nên JAR chắc chắn chạy được”

Không được bảo đảm. IDE classpath có thể chứa resources hoặc dependencies mà packaging chưa đưa vào executable archive, và working directory cũng khác.

### 31.2. “bootRun chỉ là alias của java -jar”

Không đúng. `bootRun` thường chạy compiled classes/resources trên runtime classpath của Gradle, trong khi `java -jar` chạy archive đã đóng gói.

### 31.3. “mvn spring-boot:run cũng là build production artifact”

Không đúng. Nó chạy ứng dụng từ Maven project context; muốn tạo distribution artifact thường dùng workflow package/repackage phù hợp.

### 31.4. “Tôi đặt -Dserver.port=8081 ở mọi nơi sẽ giống nhau”

Không nhất thiết. Phải biết `-D` được xử lý bởi JVM app, Gradle/Maven launcher hay plugin. `--server.port=8081` là application argument khi được truyền đúng tới Spring Boot.

### 31.5. “spring.profiles.active=dev trong YAML giống mọi Run Configuration”

Giá trị hiệu lực phụ thuộc property source precedence. IDE program args hoặc environment có thể override YAML. Dùng một nguồn quyết định rõ ràng cho môi trường chạy.

### 31.6. “Dùng Maven -Pdev chắc chắn kích hoạt Spring profile dev”

Không tự động. `-P` là Maven build profile, trừ khi dự án cấu hình kết nối rõ giữa Maven profile và Spring runtime profile.

### 31.7. “Chạy từ IDE có nghĩa mọi breakpoint trong code đều trúng”

Cần chạy đúng Debug configuration, đúng code path và đúng JVM/process. Với async code, breakpoint có thể được chạm ở thread khác hoặc sau thời điểm request.

### 31.8. “Tệp trong src/main/resources luôn đọc được bằng File path”

Không phải sau khi đóng gói JAR. Dùng classpath resource abstraction cho resources được bundle; dùng external filesystem path cho file thực sự nằm ngoài artifact.

## 32. Một quy trình thực tế cho developer

Giả sử bạn mới clone một Spring Boot service và muốn chạy, debug, rồi tạo artifact.

**Giai đoạn 1 — Hiểu project**

1. Xác định project dùng Gradle hay Maven.
2. Tìm application main class.
3. Kiểm tra JDK/Java version được yêu cầu.
4. Xem project là single-module hay multi-module.
5. Xác định web starter và external services cần cấu hình.
6. Kiểm tra `application.yml` và file profile-specific.

**Giai đoạn 2 — Chạy để phát triển**

Nếu dùng IDE, import project và chạy main class với profile dev.

Nếu dùng Gradle:

```bash
./gradlew bootRun --args="--spring.profiles.active=dev"
```

Nếu dùng Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

Đảm bảo không có hai instance vô tình dùng cùng port.

**Giai đoạn 3 — Quan sát và debug**

Kiểm tra startup log, profile active, port, context creation và health endpoint nếu app cung cấp. Đặt breakpoint ở controller/service để xác nhận luồng xử lý.

**Giai đoạn 4 — Kiểm tra packaging**

Với Gradle:

```bash
./gradlew bootJar
```

Với Maven:

```bash
./mvnw package
```

Sau đó kiểm tra đúng artifact bằng `java -jar` ở một working directory có chủ đích, không phụ thuộc source tree.

**Giai đoạn 5 — So sánh runtime behavior**

Nếu có khác biệt, so sánh:

- Main class.
- Profiles/properties.
- Java runtime.
- Runtime dependencies.
- Packaged resources.
- Working directory.
- Environment variables.
- External service endpoints.

Đây là cách tìm nguyên nhân có hệ thống thay vì sửa ngẫu nhiên nhiều cấu hình cùng lúc.

## 33. Bài tập thực hành

### Bài tập A — Chạy từ main

Tạo ứng dụng Spring Boot có `OrdersApplication` và `GreetingController`. Chạy method `main` từ IDE. Gọi `GET /hello` và xác nhận body response.

### Bài tập B — Program arguments

Trong IDE Run Configuration, đặt:

```text
--spring.profiles.active=dev --server.port=8081
```

Chạy lại và truy cập `http://localhost:8081/hello`. Kiểm tra log xác nhận profile active.

### Bài tập C — VM options

Thiết lập VM option:

```text
-Duser.timezone=UTC
```

Viết một `CommandLineRunner` in `System.getProperty("user.timezone")` và so sánh với việc đặt cùng tên dưới dạng program argument.

### Bài tập D — Gradle bootRun

Nếu project dùng Gradle, chạy:

```bash
./gradlew bootRun
```

Sau đó chạy:

```bash
./gradlew bootRun --args="--server.port=8082"
```

Quan sát app startup và port. Giải thích vì sao không cần tạo JAR trước khi chạy task.

### Bài tập E — Maven spring-boot:run

Nếu project dùng Maven, chạy:

```bash
./mvnw spring-boot:run
```

Sau đó thử:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=8083"
```

So sánh với Gradle về cách truyền args.

### Bài tập F — Multi-module

Tạo root project có module thư viện `common` và module ứng dụng `web-app`. Chạy đúng module bằng Gradle project task path hoặc Maven reactor/module directory. Giải thích vì sao root project không nhất thiết có runnable main class.

### Bài tập G — Working directory và resource

Đặt file `sample.txt` trong `src/main/resources` và file `input.csv` bên ngoài application. Đọc file thứ nhất qua classpath resource API, file thứ hai qua filesystem path. Chạy từ IDE và từ JAR để quan sát khác biệt.

### Bài tập H — DevTools

Thêm DevTools theo cấu hình phát triển của project. Bật compile/build khi sửa code trong IDE, quan sát cơ chế restart nếu được hỗ trợ. Giải thích vì sao sửa source mà không compile có thể không kích hoạt restart.

### Bài tập I — Hai instance cùng port

Chạy ứng dụng từ IDE rồi chạy thêm `bootRun` hoặc `spring-boot:run` với port mặc định. Quan sát lỗi nếu port đã được chiếm; sau đó truyền port khác cho instance thứ hai.

### Bài tập J — Chạy executable JAR

Đóng gói ứng dụng bằng build tool và chạy:

```bash
java -jar <ten-artifact-thuc-te>.jar --spring.profiles.active=dev
```

Chú ý đây là lệnh mẫu: thay tên artifact thực tế và không nhập nguyên dấu ngoặc nhọn. So sánh working directory, resource loading và cấu hình với lần chạy `bootRun`.

## 34. Bảng chọn nhanh cách chạy

| Mục tiêu | Cách thường thuận tiện |
|---|---|
| Chạy nhanh sau khi sửa code Java | IDE Run |
| Đặt breakpoint và xem biến | IDE Debug |
| Chạy project Gradle theo build configuration | `./gradlew bootRun` |
| Chạy project Maven theo build configuration | `./mvnw spring-boot:run` |
| Chạy một subproject Gradle | `./gradlew :module:bootRun` |
| Chạy application trong Maven multi-module | Chọn đúng module và gọi `spring-boot:run` |
| Truyền Spring profile khi dùng Gradle | `bootRun --args="--spring.profiles.active=dev"` |
| Truyền Spring profile khi dùng Maven | `-Dspring-boot.run.profiles=dev` |
| Đặt JVM heap cho ứng dụng | VM options hoặc cấu hình JVM args của task/plugin |
| Chạy artifact giống hình thức triển khai | Build executable JAR rồi `java -jar` |
| Đọc resource đóng gói trong JAR | Classpath resource API |
| Chạy một batch/worker không có HTTP server | Spring Boot main với WebApplicationType phù hợp |

## 35. Ghi nhớ

1. **`main(String[] args)` là điểm vào Java**, còn `SpringApplication.run(...)` khởi tạo Spring Boot application context.
2. IDE Run/Debug, Gradle `bootRun` và Maven `spring-boot:run` thường chạy cùng main application nhưng khác cách chuẩn bị classpath và cấu hình process.
3. **IDE Run** thuận tiện để phát triển và debug; cần chọn đúng module, main class, JDK, arguments và working directory.
4. **Gradle `bootRun`** chạy ứng dụng trực tiếp từ output classes/resources và runtime dependencies, không bắt buộc đóng gói executable JAR.
5. **Maven `spring-boot:run`** là goal của Spring Boot Maven plugin, cũng thường được dùng để chạy trong giai đoạn phát triển.
6. `--args` của Gradle và `spring-boot.run.arguments` của Maven đưa **application arguments** tới Spring Boot.
7. `spring-boot.run.profiles` dành cho Spring runtime profile, còn Maven `-P` là Maven build profile.
8. **VM/JVM options khác program arguments**: `-Xmx` và `-D...` cần hướng tới JVM app, còn `--server.port=...` là application argument.
9. Multi-module project đòi hỏi chọn đúng module có main class và Spring Boot plugin; không phải mọi module thư viện đều có task/goal runnable.
10. **`bootRun` và `spring-boot:run` không hoàn toàn giống `java -jar`**: JAR đã đóng gói có resource layout và runtime packaging riêng.
11. Relative file paths phụ thuộc working directory; classpath resources phải được đọc theo cơ chế resource phù hợp.
12. DevTools hỗ trợ vòng lặp phát triển nhưng không tự hot-reload mọi source change khi chưa biên dịch.
13. Một web service có thể lỗi khi port đã bị tiến trình khác chiếm; batch/non-web app có thể hoàn thành rồi tự thoát.
14. Khi Debug không hoạt động, kiểm tra đúng JVM/main class/code path, không chỉ breakpoint.
15. Khi startup behavior khác giữa IDE, Gradle, Maven và JAR, hãy so sánh Java version, dependencies, profiles, property sources, resources và working directory.

**Tư duy cốt lõi:** các lệnh **Run main**, **IDE Run**, **`bootRun`** và **`spring-boot:run`** là những con đường khác nhau để chuẩn bị và khởi chạy **cùng một ứng dụng Spring Boot**. Hiểu công cụ nào chuẩn bị classpath, công cụ nào truyền tham số và JVM nào thực thi `main` sẽ giúp bạn chạy, debug và đóng gói ứng dụng một cách chủ động, nhất quán.
