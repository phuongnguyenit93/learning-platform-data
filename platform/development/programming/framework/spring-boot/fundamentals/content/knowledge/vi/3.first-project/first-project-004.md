# Đọc cấu trúc dự án sinh ra từ Initializr

Khi tạo dự án Spring Boot đầu tiên bằng **Spring Initializr**, bạn nhận được một bộ khung có thể biên dịch và chạy ngay. Bộ khung này đã giải quyết nhiều công việc ban đầu: thiết lập công cụ build, khai báo Spring Boot và các dependency đã chọn, tạo điểm vào ứng dụng, chuẩn bị nơi đặt cấu hình và kiểm thử. Đọc đúng cấu trúc dự án giúp bạn biết **mỗi file có trách nhiệm gì, cần sửa file nào khi phát triển một tính năng và file nào do công cụ tạo ra**.

Bài học dùng dự án minh họa tên `demo`, ngôn ngữ **Java**, kiểu build **Gradle (Groovy DSL)**, packaging **JAR**, package gốc `com.example.demo`. Dự án Maven hoặc Gradle Kotlin DSL có một số file khác; phần tương ứng được giải thích riêng. Các file phụ thuộc vào lựa chọn trên Initializr và phiên bản Spring Boot, vì vậy cấu trúc thực tế của bạn có thể ngắn hoặc dài hơn ví dụ.

## 1. Spring Initializr tạo ra những gì?

[Spring Initializr](https://start.spring.io/) là công cụ khởi tạo dự án. Bạn chọn các thông tin cơ bản và dependency, rồi tải dự án về để mở trong IDE.

| Trường khi tạo dự án | Ví dụ | Tác động thường thấy đến bộ khung |
|---|---|---|
| **Project** | Gradle - Groovy / Gradle - Kotlin / Maven | Quyết định file cấu hình và wrapper của công cụ build. |
| **Language** | Java | Quyết định ngôn ngữ mã nguồn và phần mở rộng các file chính. |
| **Spring Boot** | Một phiên bản Boot được Initializr hỗ trợ | Quyết định phiên bản framework, plugin và dependency được quản lý. |
| **Group** | `com.example` | Thường dùng làm `group`/`groupId` của artifact và góp phần tạo package mặc định. |
| **Artifact** | `demo` | Tên artifact, tên thư mục/tệp đầu ra mặc định và thường là một phần của tên dự án. |
| **Name** | `demo` | Tên hiển thị của dự án; có thể ảnh hưởng đến tên root project tùy công cụ build. |
| **Description** | `Demo project for Spring Boot` | Metadata mô tả dự án. |
| **Package name** | `com.example.demo` | Package gốc và vị trí file Java được sinh ra. |
| **Packaging** | JAR | Xác định dạng artifact; lựa chọn WAR có cấu hình/điểm tích hợp khác. |
| **Java** | 17 hoặc 21, tùy phiên bản Boot | Đặt mục tiêu phiên bản Java/toolchain theo cấu hình dự án. |
| **Dependencies** | Spring Web, Validation, Spring Data JPA... | Thêm thư viện/starter tương ứng vào khai báo build; có thể tạo thêm thành phần cấu hình hoặc cấu trúc tài liệu liên quan. |

**Initializr tạo skeleton, không tạo sẵn toàn bộ ứng dụng nghiệp vụ.** Nếu chọn Spring Web, bạn có các thư viện để xây HTTP API, nhưng vẫn phải tự viết controller. Nếu chọn Spring Data JPA, bạn có nền tảng truy cập dữ liệu, nhưng không tự nhiên có entity và repository cho bài toán của mình.

## 2. Nhìn toàn bộ cây thư mục

Ví dụ dưới đây biểu diễn một dự án Gradle Java cơ bản. Một số thư mục như `static/`, `templates/` hoặc tệp `.gitignore` có thể có hoặc không tùy bộ khung; chúng được ghi chú là **tùy chọn** khi cần.

```text
demo/
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/
│   │   │       └── example/
│   │   │           └── demo/
│   │   │               └── DemoApplication.java
│   │   └── resources/
│   │       ├── application.properties
│   │       ├── static/             # Có thể chưa có hoặc đang trống
│   │       └── templates/          # Có thể chưa có hoặc đang trống
│   └── test/
│       └── java/
│           └── com/
│               └── example/
│                   └── demo/
│                       └── DemoApplicationTests.java
├── .gitattributes              # Nếu Initializr cung cấp
├── .gitignore                  # Nếu Initializr cung cấp
├── build.gradle
├── gradlew
├── gradlew.bat
├── settings.gradle
└── HELP.md                     # Nếu Initializr cung cấp
```

Nếu bạn chọn **Gradle Kotlin DSL**, hai file cấu hình thường đổi thành `build.gradle.kts` và `settings.gradle.kts`. Nếu chọn **Maven**, các file chính là `pom.xml`, `mvnw`, `mvnw.cmd` và thư mục `.mvn/wrapper/` thay cho phần tương ứng của Gradle; cây `src/main` và `src/test` vẫn có ý nghĩa tương tự.

Đừng coi hình cây là danh sách file bắt buộc ở mọi phiên bản Initializr. Hãy tìm **các điểm tựa** trước: file build ở thư mục gốc, `src/main/java`, `src/main/resources`, `src/test` và lớp có `main()`.

## 3. Bốn khu vực quan trọng nhất

Một cách đọc nhanh là nhóm file theo trách nhiệm:

| Khu vực | Trách nhiệm | Khi nào bạn thường chỉnh sửa? |
|---|---|---|
| **File build ở thư mục gốc** (`build.gradle`, `pom.xml`,...) | Định nghĩa plugin, dependency, Java target, build/test/packaging. | Khi thêm thư viện, đổi phiên bản, cấu hình task build. |
| **`src/main/java`** | Mã Java của ứng dụng. | Khi viết controller, service, cấu hình Java, model và logic nghiệp vụ. |
| **`src/main/resources`** | Tài nguyên đi kèm ứng dụng trên classpath. | Khi chỉnh cấu hình, thông báo, template, tài nguyên tĩnh hay các file tài nguyên cần dùng lúc chạy. |
| **`src/test`** | Mã kiểm thử và tài nguyên kiểm thử. | Khi viết unit test, integration test hoặc cấu hình riêng cho test. |

Các file `gradlew`, `gradlew.bat`, `mvnw` và `mvnw.cmd` là **wrapper** giúp gọi phiên bản công cụ build được cấu hình cho dự án. Chúng không thay thế mã ứng dụng và thông thường không phải nơi bạn thêm dependency.

## 4. Điểm vào ứng dụng: `DemoApplication.java`

Mở `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Từng phần có ý nghĩa riêng:

1. **`package com.example.demo;`** xác định namespace Java. Cấu trúc thư mục `com/example/demo` theo convention tương ứng với package này.
2. **`@SpringBootApplication`** là annotation trung tâm của ứng dụng Boot. Về mặt tác dụng chính, nó tập hợp khai báo cấu hình, kích hoạt auto-configuration và component scanning theo phạm vi mặc định.
3. **`main(String[] args)`** là điểm vào Java; đây là method mà Java launcher dùng để bắt đầu ứng dụng.
4. **`SpringApplication.run(...)`** khởi tạo ứng dụng Spring, tạo và làm mới `ApplicationContext`, cấu hình các thành phần và khởi động server khi dự án có web stack phù hợp.

Phương thức `main()` không trực tiếp xử lý HTTP request. Với ứng dụng web, request sẽ đi qua server và các thành phần Spring MVC/WebFlux do dependencies và cấu hình quyết định.

### Vì sao package của lớp main quan trọng?

Mặc định, Spring Boot dùng package chứa `@SpringBootApplication` làm gốc cho quá trình component scanning. Một bố cục thường phù hợp là:

```text
src/main/java/com/example/demo/
├── DemoApplication.java
├── controller/
│   └── GreetingController.java
├── service/
│   └── GreetingService.java
└── model/
    └── Greeting.java
```

Các lớp trong `com.example.demo.controller`, `com.example.demo.service` và các package con thường nằm trong phạm vi scanning. Nếu bạn đặt `GreetingService` trong package hoàn toàn khác, chẳng hạn `org.other.service`, Spring có thể không tự tìm được bean đó theo phạm vi scan mặc định. Khi ấy cần xem lại package placement hoặc cấu hình scanning rõ ràng, không vội kết luận annotation service bị lỗi.

Tên `controller`, `service`, `model` là convention để tổ chức code, **không phải thư mục được Initializr tạo sẵn hay tên package bắt buộc của Spring Boot**. Ứng dụng lớn có thể chọn cấu trúc theo tính năng hoặc domain.

### Một ví dụ thêm controller sau khi tạo project

Nếu đã chọn dependency hỗ trợ Spring MVC, bạn có thể tạo file `src/main/java/com/example/demo/controller/GreetingController.java`:

```java
package com.example.demo.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
```

Khi chạy ứng dụng có server HTTP và dùng cổng mặc định, bạn có thể thử `http://localhost:8080/hello`. Nếu project không chọn dependency web phù hợp, các annotation/controller hoặc embedded server có thể chưa sẵn sàng; điều đó được quyết định bởi file build, không phải chỉ bởi tên thư mục `controller`.

## 5. `src/main/resources`: tài nguyên và cấu hình

`resources` là nơi dành cho file không phải mã nguồn Java nhưng cần có trong classpath khi ứng dụng chạy. Các tài nguyên dưới `src/main/resources` thường được Gradle/Maven copy vào output lúc build.

### `application.properties` và `application.yml`

Initializr Java project thường có `src/main/resources/application.properties`, có thể ban đầu trống. Đây là nơi quen thuộc để cấu hình ứng dụng:

```properties
spring.application.name=demo
server.port=8081
logging.level.com.example.demo=DEBUG
```

Nếu dùng YAML, file có thể là `application.yml`:

```yaml
spring:
  application:
    name: demo
server:
  port: 8081
logging:
  level:
    com.example.demo: DEBUG
```

Hai đoạn minh họa **cùng một loại thông tin cấu hình**, không nhất thiết cùng tồn tại trong một project. Nên chọn cách quản lý rõ ràng để tránh cấu hình trùng và khó xác định giá trị hiệu lực. Cấu hình thực tế còn có thể đến từ command-line arguments, biến môi trường, Java system properties và các file profile-specific.

Các file như `application-dev.properties` hoặc `application-prod.yml` **không bắt buộc có sẵn**; bạn tạo thêm khi cần cấu hình cho từng môi trường. Đừng đặt mật khẩu, access token hoặc secret thật vào file cấu hình đưa lên repository. Có thể dùng placeholder được cấp giá trị từ môi trường lúc chạy, ví dụ:

```properties
app.api-key=${APP_API_KEY}
```

Ví dụ trên chỉ hữu ích nếu ứng dụng có thành phần đọc `app.api-key`, và biến môi trường `APP_API_KEY` được cấp đúng khi khởi chạy.

### `static/` và `templates/`

Hai thư mục này đôi khi được tạo sẵn hoặc được IDE hiển thị như vị trí quy ước:

- **`static/`**: thường dùng chứa CSS, JavaScript, hình ảnh và các file tĩnh để web framework phục vụ trực tiếp khi có cấu hình/dependency phù hợp.
- **`templates/`**: thường chứa template phía server, ví dụ Thymeleaf, khi dự án đã có template engine phù hợp.

Chỉ có thư mục `templates/` **không có nghĩa** Spring Boot sẽ tự render HTML. Bạn cần dependency template engine và controller trả về tên view tương ứng. Tương tự, thư mục `static/` không khiến một ứng dụng non-web tự tạo HTTP server.

### Tài nguyên khác có thể xuất hiện về sau

Bạn có thể tạo thêm `messages.properties` cho message bundles, file SQL migration, chứng chỉ, cấu hình logger hoặc dữ liệu mẫu tùy mục đích. Các thư mục này không phải bằng chứng rằng Initializr bắt buộc sinh ra toàn bộ chúng. Hãy phân biệt tài nguyên do **bạn thêm** với tài nguyên **skeleton ban đầu**.

## 6. File build Gradle: `build.gradle`

Với lựa chọn Gradle Groovy DSL, `build.gradle` là file khai báo cách build. Một cấu hình minh họa cho dự án Spring Boot sử dụng Spring MVC có thể có dạng:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **ví dụ cấu hình từ một thế hệ Spring Boot cụ thể**, không phải khẳng định Initializr hiện tại luôn tạo đúng các dòng hoặc phiên bản này. Khi làm việc với dự án thật, giữ các phiên bản tương thích mà Initializr đã sinh ra. Cách quản lý BOM/dependency và tên starter có thể thay đổi giữa các phiên bản Boot.

Các khối cấu hình cần biết:

| Khối | Ý nghĩa |
|---|---|
| `plugins` | Kích hoạt hỗ trợ Java và khả năng build/chạy/đóng gói ứng dụng Spring Boot. |
| `group`, `version` | Metadata định danh artifact. |
| `java.toolchain` | Yêu cầu toolchain Java được Gradle sử dụng theo cấu hình; khác với việc chỉ đọc `java -version` của shell. |
| `repositories` | Nguồn Gradle tìm dependency khi resolve. |
| `dependencies` | Các dependency được khai báo cho runtime, compile hoặc test theo configuration tương ứng. |
| `tasks.named('test')` | Tùy chỉnh task test, ví dụ sử dụng JUnit Platform. |

Các dependency như `implementation` thường được dùng cho mã ứng dụng; `testImplementation` dành cho test. Một **Spring Boot starter** gom những dependency thường đi cùng nhau để lập trình viên không phải tự kê từng thư viện nhỏ. Khi cần JSON HTTP, embedded server, validation hay database access, hãy xem loại starter nào đang được khai báo thay vì đoán theo tên file Java.

Ví dụ thêm một dependency có thể trông như sau:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Bạn nên đặt khai báo vào file build rồi chạy Gradle sync/refresh để IDE nhận dependency. Không copy JAR thủ công vào `src/main/java`.

### `settings.gradle`: danh tính và cấu trúc build

Ở dự án Gradle một module, nội dung thường đơn giản:

```groovy
rootProject.name = 'demo'
```

Trong một Gradle multi-project, file này còn có thể khai báo các subproject qua `include(...)`. **`settings.gradle` không phải nơi để viết controller hoặc khai báo cấu hình HTTP**. Nó mô tả cấu trúc build cấp cao.

### Gradle wrapper: `gradlew`, `gradlew.bat` và `gradle/wrapper/`

Wrapper cho phép chạy Gradle phù hợp với cấu hình project ngay cả khi máy chưa cài Gradle toàn cục. Nó gồm script khởi chạy theo hệ điều hành và các file wrapper hỗ trợ tải/khởi động Gradle distribution được chỉ định.

```bash
# Linux/macOS
./gradlew tasks
./gradlew test
./gradlew bootRun
./gradlew bootJar
```

```powershell
# Windows PowerShell
.\gradlew.bat tasks
.\gradlew.bat test
.\gradlew.bat bootRun
.\gradlew.bat bootJar
```

`tasks` liệt kê các task hữu dụng trong build; `test` chạy kiểm thử được cấu hình; `bootRun` chạy ứng dụng từ project; `bootJar` tạo executable JAR khi plugin Spring Boot và packaging thích hợp được dùng. Wrapper thường tải Gradle distribution trong lần sử dụng đầu, nên cần truy cập nguồn tải và thiết lập Java phù hợp.

Các file wrapper và cấu hình build **thường nên được version control cùng source** để người khác build cùng môi trường. Thư mục output như `build/` thường được ignore, vì đó là sản phẩm sinh ra từ mã nguồn.

## 7. Nếu chọn Maven thì đọc gì?

Với Maven, file chính ở thư mục gốc là `pom.xml` (*Project Object Model*). Một mô hình rút gọn:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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

Đây cũng là ví dụ để nhận biết vai trò các thẻ, không phải POM hoàn chỉnh của mọi bản Boot. Các thẻ `parent`, `dependencies`, `build/plugins` và `properties` tương ứng với metadata, dependency, plugin và cài đặt Java. Với Maven wrapper, các lệnh cơ bản là:

```bash
./mvnw test
./mvnw spring-boot:run
./mvnw package
```

Windows PowerShell dùng `./mvnw.cmd` hoặc `.\mvnw.cmd` thay cho `./mvnw`. Artifact Maven thường xuất hiện dưới `target/`, khác với `build/libs/` của Gradle.

**Điểm chung lớn hơn khác biệt:** cả Maven và Gradle đều phân chia mã chạy ở `src/main/java`, tài nguyên ở `src/main/resources`, test ở `src/test` và metadata/dependency ở file build. Bạn không cần học hai công cụ build cùng lúc để hiểu bộ khung Spring Boot đầu tiên.

## 8. `src/test`: bài kiểm thử sinh sẵn nói lên điều gì?

Initializr thường tạo lớp kiểm thử ở package tương ứng, ví dụ:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

Với test engine và dependency test phù hợp, `@SpringBootTest` yêu cầu khởi tạo Spring application context cho kiểm thử. Phương thức `contextLoads()` có thể có body rỗng: mục đích ban đầu là kiểm tra bối cảnh ứng dụng có khởi tạo thành công hay không. Đây **không phải bộ kiểm thử đầy đủ cho nghiệp vụ hay HTTP API**.

Khi thêm controller, service hoặc truy cập dữ liệu, bạn sẽ cần các test có assertion cụ thể để xác minh hành vi mong đợi. Bạn cũng có thể đặt file cấu hình test dưới `src/test/resources` nếu có nhu cầu; thư mục đó không nhất thiết được tạo trước.

Lưu ý: test khởi tạo toàn bộ context có thể thất bại khi thiếu database, biến môi trường hoặc service bên ngoài. Nếu test bỗng lỗi sau khi thêm dependency, cần kiểm tra cả auto-configuration và cấu hình test; không mặc định rằng `contextLoads()` đã viết sai.

## 9. Thư mục output xuất hiện sau khi build

Ngay sau khi giải nén Initializr project, thư mục `build/` hoặc `target/` có thể chưa tồn tại. Chúng được tạo khi chạy các task liên quan.

Với Gradle:

```text
demo/
└── build/                     # Xuất hiện sau khi chạy build
    ├── classes/               # Class đã biên dịch
    ├── resources/             # Tài nguyên đã xử lý/copy
    ├── reports/               # Báo cáo build/test khi có
    ├── test-results/          # Kết quả kiểm thử khi có
    └── libs/                  # JAR nếu task đóng gói được chạy
```

Với Maven, thư mục tương ứng thường tên `target/`. File JAR trong `build/libs` hoặc `target` là **artifact được xây từ source và dependency**, không phải chỗ để bạn sửa mã Java trực tiếp.

Một đường đi từ source đến ứng dụng chạy:

```text
src/main/java/*.java ── compile ──> .class
src/main/resources/* ────────────> resources trong artifact
dependencies từ build file ──────> classpath / thư viện đóng gói
                               │
                               ▼
                     executable JAR (nếu build JAR)
                               │
                               ▼
                         java -jar ...
                               │
                               ▼
                    Spring Boot application
```

Với Spring Boot executable JAR, thư viện dependency và `.class` thường được sắp vào cấu trúc đóng gói phục vụ Boot loader. Điều này khác với việc chỉ tạo một archive `.jar` thông thường của Java; chọn task `jar` hay `bootJar` có thể cho ra artifact có mục đích khác nhau.

## 10. Đọc `.gitignore`, `.gitattributes` và `HELP.md`

Đây là các file hỗ trợ workflow phát triển, không phải thành phần logic runtime:

- **`.gitignore`**: gợi ý Git bỏ qua output, cache hoặc file cục bộ nhất định. Ví dụ `build/` và `target/` thường không nên commit. Có `.gitignore` không đồng nghĩa mọi thứ trong project đã được commit.
- **`.gitattributes`**: quy định cách Git xử lý thuộc tính của file, chẳng hạn line endings hoặc text/binary, hữu ích khi làm việc đa nền tảng.
- **`HELP.md`**: tài liệu hướng dẫn được Initializr cung cấp trong một số cấu hình, thường chứa link tham khảo build tool, tài liệu Spring Boot hoặc các dependency đã chọn.

Nhiều IDE tạo thêm `.idea/`, `.project`, `.classpath`, `.settings/`, `.vscode/` hoặc metadata khác sau khi import. Đó thường là file của môi trường phát triển, **không nhất thiết là cấu trúc do Initializr gốc sinh ra**. Việc commit chúng tùy quy ước nhóm; điều cần phân biệt là nguồn gốc và trách nhiệm.

## 11. Một lượt đọc và chạy dự án mới nhận

Giả sử bạn vừa tải ZIP từ Initializr và giải nén vào thư mục `demo`. Trước khi viết controller đầu tiên, hãy làm theo thứ tự:

**Bước 1 — Xác định công cụ build.** Nếu có `build.gradle` hoặc `build.gradle.kts`, dự án dùng Gradle. Nếu có `pom.xml`, dự án dùng Maven. Đọc file đó để biết Java target, plugin và dependency đang có.

**Bước 2 — Tìm điểm vào Java.** Mở `src/main/java/.../DemoApplication.java`, nhìn package, `@SpringBootApplication` và lời gọi `SpringApplication.run(...)`. Ghi nhớ package gốc trước khi tạo thêm controller/service.

**Bước 3 — Kiểm tra cấu hình.** Mở `src/main/resources/application.properties` hoặc `application.yml`. Nếu trống, không có nghĩa ứng dụng thiếu cấu hình: Spring Boot có nhiều giá trị mặc định và auto-configuration tùy classpath.

**Bước 4 — Chạy kiểm thử.** Với Gradle wrapper:

```bash
./gradlew test
```

Hoặc với Maven wrapper:

```bash
./mvnw test
```

Nếu kiểm thử lỗi, đọc thông báo trong log và kết quả test để tìm nguyên nhân trước khi chỉnh project. Ở Windows, dùng script wrapper `.bat`/`.cmd` tương ứng.

**Bước 5 — Chạy ứng dụng trong chế độ phát triển.** Với Gradle:

```bash
./gradlew bootRun
```

Với Maven:

```bash
./mvnw spring-boot:run
```

Nếu có web starter thích hợp, console thường thông báo embedded server đã khởi động và cổng lắng nghe. Nếu không chọn web stack, ứng dụng có thể khởi tạo context rồi kết thúc mà **không có HTTP endpoint**; đó không nhất thiết là lỗi.

**Bước 6 — Build artifact.** Với Gradle:

```bash
./gradlew bootJar
```

Với Maven:

```bash
./mvnw package
```

Mở `build/libs/` hoặc `target/` để xem tên file JAR thật sự. Sau đó có thể chạy **đúng file executable JAR đã sinh ra**:

```bash
java -jar path/to/your-application.jar
```

Tên JAR có thể chứa `artifact`, `version` và classifier tùy cấu hình build. Không mặc định mọi bản build đều tên `demo.jar` hoặc mọi file `.jar` đều là executable JAR.

## 12. Những thay đổi đầu tiên nên đặt ở đâu?

| Bạn muốn làm gì? | Vị trí thường cần mở | Vì sao? |
|---|---|---|
| Thêm endpoint `GET /hello` | Tạo controller Java dưới package gốc. | Spring MVC đọc annotation mapping từ controller được đăng ký. |
| Thêm logic xử lý nghiệp vụ | Tạo service Java theo cấu trúc dự án. | Tách xử lý nghiệp vụ khỏi giao tiếp HTTP. |
| Đổi cổng server | `application.properties`/`application.yml` hoặc cấu hình từ môi trường. | Đây là runtime application property. |
| Thêm driver cơ sở dữ liệu | File build. | Driver là dependency cần được resolve. |
| Tạo trang HTML render phía server | `templates/`, controller và dependency template engine phù hợp. | Template cần công cụ render để tạo response. |
| Thêm CSS/JS tĩnh | `src/main/resources/static/` khi web stack hỗ trợ. | Đặt tài nguyên ở vị trí web static resources có thể được phục vụ. |
| Thêm test cho controller/service | `src/test/java`. | Tách test source khỏi code runtime. |
| Thay phiên bản Java target | Cấu hình toolchain/Java version trong file build. | Build tool chịu trách nhiệm biên dịch theo target. |
| Đổi tên project Gradle | Thường là `settings.gradle`/`settings.gradle.kts`. | File settings khai báo tên root project. |

Không nên sửa class đã biên dịch trong `build/classes`, hay file trong `build/libs`, rồi mong sửa đổi tồn tại sau lần build tiếp theo. Quy tắc cơ bản là **sửa source hoặc cấu hình gốc, sau đó build lại artifact**.

## 13. Những hiểu lầm thường gặp khi mới mở project

### “Có file `DemoApplication.java` là đã có REST API”

Chưa hẳn. File main khởi tạo ứng dụng. Để có API HTTP cần dependency web thích hợp, server đang chạy và controller/router khai báo endpoint. Nếu thử `/hello` mà nhận 404, hãy kiểm tra mapping và package scan trước khi nghi ngờ Initializr bị lỗi.

### “Thêm dependency bằng cách import class trong IDE”

`import` trong Java chỉ nói bạn muốn sử dụng một kiểu đã có thể truy cập trên compile classpath; nó không tải thư viện mới từ Maven Central. Phải khai báo dependency trong `build.gradle`/`pom.xml` và để build tool resolve, rồi IDE đồng bộ project.

### “Thư mục `resources` chỉ dành cho ảnh và HTML”

Không. Nó chứa nhiều loại tài nguyên trên runtime classpath, nổi bật là `application.properties`, `application.yml`, message bundles và tài nguyên cấu hình của framework. `static/` và `templates/` chỉ là hai khu vực có quy ước cụ thể cho ứng dụng web.

### “Ứng dụng đã chạy vì lệnh build thành công”

`build` hoặc `package` chứng tỏ đã hoàn thành các task của build trong lần chạy ấy, **không mặc định giữ ứng dụng đang phục vụ request**. Task `bootRun`, lệnh `java -jar` hoặc thao tác Run trong IDE mới trực tiếp khởi chạy ứng dụng. Cần phân biệt build-time với runtime.

### “Chạy bằng `bootRun` và `java -jar` luôn giống hệt nhau”

Cả hai chạy ứng dụng Java, nhưng có thể khác classpath, cách truyền tham số, môi trường, working directory và artifact đầu vào. Khi một cách chạy thành công, cách còn lại thất bại, hãy đối chiếu những yếu tố đó.

### “Đổi tên package là chỉ cần đổi tên thư mục”

Package Java nằm trong khai báo `package` của mỗi file; khi đổi phải cập nhật vị trí source, khai báo package, imports và những cấu hình/tham chiếu liên quan. Với Spring Boot còn phải xem phạm vi component scan. Hãy dùng tính năng **Refactor/Rename** trong IDE khi có thể.

### “Xóa wrapper đi vì máy đã có Gradle/Maven”

Wrapper giúp người khác và hệ thống CI sử dụng phiên bản công cụ build được project hướng dẫn, nên thường đáng giữ trong version control. Dùng Gradle/Maven toàn cục vẫn có thể được, nhưng không đảm bảo cùng phiên bản và hành vi tương thích với project.

## 14. Bài tập tự khám phá bộ khung Initializr

**Bài tập A — Dựng bản đồ file.** Tạo một project Java Gradle JAR với dependency Spring Web. Mở thư mục sau khi giải nén và ghi tên file thực tế tương ứng với bốn khu vực: file build, main Java, resources và test Java. Đánh dấu những thư mục trong ví dụ của bài **không có** ở project bạn tạo; điều đó giúp phân biệt tùy chọn với bắt buộc.

**Bài tập B — Dò tác động của dependency.** Tạo hai skeleton với cùng metadata, một cái có Spring Web, một cái không. So sánh **khai báo dependency trong file build**; sau đó chạy ứng dụng và quan sát sự khác biệt về HTTP server. Không cần tự chỉnh code framework để tạo ra sự khác biệt này.

**Bài tập C — Thêm endpoint đơn giản.** Tạo controller `/hello` dưới package con của lớp có `@SpringBootApplication`. Chạy ứng dụng, truy cập endpoint, sau đó đổi `server.port` trong file cấu hình và kiểm tra lại URL. Liên hệ ba phần đã sửa: source Java, file cấu hình và tiến trình đang chạy.

**Bài tập D — Quan sát artifact.** Chạy `bootJar` hoặc `package`, tìm JAR ở thư mục output của build tool tương ứng. So sánh cây thư mục **trước** và **sau** build; xác định file nào thuộc source, file nào là output có thể sinh lại.

## 15. Ghi nhớ để bắt đầu phát triển

Một project do Initializr tạo là **bản thiết kế thực thi được**, không chỉ là tập hợp các folder. File build nói *dự án cần gì để build*; `src/main/java` chứa *logic và điểm vào của ứng dụng*; `src/main/resources` giữ *cấu hình và tài nguyên lúc chạy*; `src/test` chứa *các phép kiểm tra hành vi*; wrapper giúp *những người khác chạy build theo cấu hình project*.

Khi gặp một file lạ, hãy xác định nó thuộc **source**, **runtime resource**, **build configuration**, **test** hay **generated output**. Cách phân loại đó đủ để đọc một bộ khung Initializr mới, chọn đúng nơi sửa đổi và phát triển Spring Boot mà không phụ thuộc vào việc IDE đang hiển thị những thư mục nào.
