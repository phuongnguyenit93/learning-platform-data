# Starter Spring Boot tập hợp phụ thuộc như thế nào?

Trong dự án Spring Boot, một dòng dependency như `spring-boot-starter-web` có thể mang theo hàng loạt thư viện để xây dựng ứng dụng HTTP: Spring MVC, Spring Core, JSON serialization, logging và máy chủ Servlet nhúng. **Starter không tải “toàn bộ Spring”**. Nó khai báo một nhóm phụ thuộc được chọn cho một mục đích; Maven hoặc Gradle giải đồ thị phụ thuộc bắc cầu rồi đưa những thành phần phù hợp lên classpath.

Bài này giải thích đúng vai trò của **starter**, **BOM (Bill of Materials)**, **dependency management**, **transitive dependency**, **auto-configuration** và **đóng gói ứng dụng**, để khi thêm một starter bạn biết chính xác điều gì xảy ra và cách tự kiểm chứng. Các ví dụ cấu hình dùng **Spring Boot 3.3.5 và Java 17** để minh họa một phiên bản nhất quán. Với phiên bản Spring Boot khác, cần xem đồ thị phụ thuộc thực tế vì thành phần và phiên bản có thể thay đổi.

## 1. Starter là gì?

**Spring Boot starter** là một dependency “điểm vào” có tên `spring-boot-starter-*`, được thiết kế để tập hợp các thư viện thường cần cho một chức năng. Phần lớn starter chính thức là artifact Maven/Gradle chứa metadata khai báo dependency, không phải ứng dụng hoặc một framework riêng.

Ví dụ mục đích của một số starter:

| Starter | Nhóm công việc | Một số phụ thuộc đi kèm theo quy ước Spring Boot 3.x |
| --- | --- | --- |
| `spring-boot-starter` | Nền tảng Boot | Cơ sở Spring Boot, auto-configuration và logging mặc định |
| `spring-boot-starter-web` | HTTP REST/Servlet MVC | Web MVC, Jackson JSON, Tomcat nhúng theo mặc định |
| `spring-boot-starter-webflux` | Reactive HTTP/WebFlux | Spring WebFlux, Reactor và Reactor Netty theo mặc định |
| `spring-boot-starter-data-jpa` | ORM/JPA | Spring Data JPA, Hibernate ORM, giao dịch và JDBC liên quan |
| `spring-boot-starter-jdbc` | JDBC/DataSource | Spring JDBC, transaction và connection pool mặc định |
| `spring-boot-starter-security` | Bảo mật Spring Security | Thư viện Security và tích hợp cấu hình mặc định |
| `spring-boot-starter-test` | Kiểm thử | Spring Test, JUnit Jupiter, AssertJ, Mockito và các thư viện test liên quan |
| `spring-boot-starter-actuator` | Quan sát/vận hành | Spring Boot Actuator và hạ tầng endpoint vận hành |

Danh sách trên tóm tắt **vai trò**, không phải danh sách chính xác mọi JAR. Ví dụ `spring-boot-starter-data-jpa` giúp đưa hạ tầng JPA vào classpath nhưng **không tự tạo một cơ sở dữ liệu** hoặc thêm driver PostgreSQL/MySQL tùy ý. Muốn kết nối cơ sở dữ liệu cụ thể, bạn còn cần driver, URL và credential phù hợp.

Điều đáng nhớ:

1. **Starter khai báo dependency** để build tool biết cần những artifact nào.
2. **Build tool tải và giải dependency graph**, chọn phiên bản dựa trên cấu hình quản lý version và quy tắc giải xung đột.
3. **Spring Boot auto-configuration kiểm tra classpath và điều kiện runtime** để cấu hình bean phù hợp.
4. **Packaging plugin** xây dựng artifact chạy thật từ các class và dependency được phép đi vào runtime.

Đây là bốn cơ chế liên quan nhưng khác nhau. Thêm một starter làm thay đổi dependency graph; nó không bảo đảm mọi bean hoặc mọi dịch vụ bên ngoài tự hoạt động.

## 2. Từ một dòng starter đến đồ thị dependency bắc cầu

Xét dependency trực tiếp của ứng dụng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Trong Gradle, `implementation` bổ sung một **dependency trực tiếp** của source set chính. Gradle đọc metadata của artifact `spring-boot-starter-web`; metadata này khai báo những dependency khác. Gradle tiếp tục đọc metadata của chúng cho tới khi giải xong tập dependency cần thiết.

Ví dụ **sơ đồ khái niệm** của Spring Boot 3.x (đã rút gọn, không thay thế kết quả `dependencies` của phiên bản thực tế):

```text
Ứng dụng
└── spring-boot-starter-web                    (trực tiếp)
    ├── spring-boot-starter                    (bắc cầu)
    │   ├── spring-boot
    │   ├── spring-boot-autoconfigure
    │   └── spring-boot-starter-logging
    ├── spring-boot-starter-json               (bắc cầu)
    │   └── các thư viện Jackson liên quan
    ├── spring-boot-starter-tomcat             (bắc cầu, mặc định)
    │   └── thư viện Tomcat nhúng
    ├── spring-web
    └── spring-webmvc
```

Mỗi artifact có tọa độ Maven gồm **`groupId:artifactId:version`**. Ví dụ `org.springframework.boot:spring-boot-starter-web:3.3.5`. Trong dự án có dependency management, bạn thường không ghi version ở từng dòng vì phiên bản đã được quản lý tập trung.

**Trực tiếp và bắc cầu:**
- **Trực tiếp:** khai báo trong `build.gradle` / `pom.xml` của ứng dụng.
- **Bắc cầu (transitive):** được khai báo bởi một dependency khác và được build tool đưa vào khi giải graph.
- **Dependency trùng:** nhiều nhánh có thể cùng cần một thư viện; công cụ build chọn một phiên bản cuối cùng theo cơ chế giải version của nó.
- **Scope/configuration:** quyết định dependency có mặt khi compile, test, runtime hay package.

Không suy diễn rằng “starter A luôn chứa đúng N JAR”. Số lượng artifact phụ thuộc phiên bản, platform/BOM, exclusions, các thư viện khác và quy tắc conflict resolution.

## 3. BOM quản lý phiên bản, starter quản lý thành phần

Đây là hai vai trò dễ bị nhầm lẫn nhất.

**Starter trả lời: “Để làm việc này, cần nhóm thư viện nào?”** Nó cung cấp các cạnh trong đồ thị dependency.

**BOM trả lời: “Các thư viện trong tập được quản lý nên dùng phiên bản nào?”** BOM là một POM có `dependencyManagement` khai báo phiên bản của nhiều artifact tương thích với một dòng Spring Boot. BOM **không tự thêm** tất cả các artifact vào ứng dụng. Chỉ khi một artifact thực sự được yêu cầu bởi dependency trực tiếp/bắc cầu, quy tắc quản lý version mới có tác dụng trong quá trình giải dependency.

Ví dụ mô hình:

```text
                          spring-boot-dependencies BOM
                         ┌──────────────────────────────┐
                         │ quản lý version cho          │
                         │ Spring, Jackson, Tomcat...   │
                         └──────────────────────────────┘
                                        |
                                        v
Ứng dụng --yêu cầu--> spring-boot-starter-web --yêu cầu--> spring-webmvc
                                                 \-------> Tomcat, Jackson...
                                        |
                                 Maven/Gradle resolve
                                        |
                                        v
                     Runtime classpath với version được chọn
```

Trong cùng một dự án, nếu bạn thêm `spring-boot-starter-web` và `spring-boot-starter-data-jpa`, cả hai có thể cần những thành phần Spring Core. Build tool **giải một dependency graph chung**; không sao chép hai bản hoàn toàn độc lập của cùng một thư viện chỉ vì có hai starter.

BOM giúp các dependency được Spring Boot kiểm thử cùng nhau dùng các phiên bản tương thích. Tuy nhiên, nó không bảo đảm toàn bộ graph luôn đúng ý bạn: version khai báo tường minh, platform/constraint bổ sung, BOM khác, exclusion và quy tắc conflict resolution có thể ảnh hưởng kết quả. **Hãy xem phiên bản đã resolve, không chỉ đọc các dòng dependency đã khai báo.**

## 4. Maven: parent và BOM hoạt động ra sao?

### 4.1. Cách phổ biến với Spring Boot parent

Ví dụ `pom.xml` tối thiểu cho một ứng dụng REST dùng Spring Boot 3.3.5 và Java 17:

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
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>starter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Ở đây:
- `spring-boot-starter-parent` kế thừa dependency management từ `spring-boot-dependencies` cùng version và cung cấp nhiều mặc định Maven/plugin hữu ích.
- `spring-boot-starter-web` không cần ghi `<version>`: phiên bản được quản lý theo parent.
- `spring-boot-starter-test` có `<scope>test</scope>`: dùng để biên dịch/chạy test và không được đưa vào runtime artifact thông thường.
- `spring-boot-maven-plugin` hỗ trợ tái đóng gói thành executable JAR khi build theo cấu hình Spring Boot Maven plugin.

**Nếu dự án phải dùng parent POM khác**, có thể import `org.springframework.boot:spring-boot-dependencies` với `<type>pom</type>` và `<scope>import</scope>` trong `dependencyManagement`. Ví dụ đoạn cấu hình đặt **bên trong `<project>`**, đồng thời giữ `<parent>` hiện có:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Import BOM **quản lý version của dependency** nhưng **không kế thừa toàn bộ cấu hình plugin và property** của Spring Boot parent. Nếu không dùng parent, bạn phải tự cấu hình các Maven plugin cần thiết, ví dụ version/cách chạy `spring-boot-maven-plugin` theo setup của dự án.

Maven dùng một dependency mediation graph với quy tắc phiên bản và `dependencyManagement` của Maven; BOM import không giống việc khai báo tất cả dependency thành dependency trực tiếp.

### 4.2. Quan sát Maven dependency tree

Từ thư mục dự án có `pom.xml`:

```bash
# Với Maven Wrapper đã được tạo
./mvnw dependency:tree

# Chỉ quan tâm dependency liên quan Spring
./mvnw dependency:tree -Dincludes=org.springframework.boot:*
```

Trong PowerShell dùng `.\mvnw.cmd dependency:tree`; khi dùng filter có ký tự `*`, nên đặt tham số lọc trong dấu nháy phù hợp với shell. Kết quả hiển thị đường đi trực tiếp/bắc cầu, group, artifact, version và scope. Bạn cũng có thể dùng `./mvnw help:effective-pom` để quan sát POM sau kế thừa/merge, nhưng **effective POM không thay thế cây dependency thực tế**.

## 5. Gradle: starter, dependency-management plugin và Gradle platform

Ví dụ `build.gradle` (Groovy DSL) tương thích Spring Boot 3.3.5:

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở cấu hình này, khi Spring Boot Gradle plugin được áp dụng cùng `io.spring.dependency-management`, Boot plugin sử dụng dependency management của BOM `spring-boot-dependencies` khớp với version Boot plugin. `implementation` dùng cho mã chính, còn `testImplementation` thêm thư viện test. Không cần thêm version cho hai starter trên.

**Gradle cũng có cơ chế BOM/platform gốc**. Nếu không áp dụng plugin `io.spring.dependency-management`, bạn có thể khai báo rõ BOM:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là **đoạn thay thế riêng cho khối `dependencies`**, dùng trong build đã có `java`, repository và các plugin/cấu hình phù hợp. Khi dùng Gradle native platform, đặt platform ở **configuration cần quản lý** (ở ví dụ là main và test); không mặc nhiên hiểu mọi configuration riêng sẽ nhận BOM. Đừng trộn hai cơ chế quản lý phiên bản khi không có nhu cầu rõ ràng, vì hành vi override/ràng buộc version có thể trở nên khó đọc.

### 5.1. Xem graph và phiên bản đã chọn trong Gradle

```bash
# Mọi dependency được resolve cho runtime classpath
./gradlew dependencies --configuration runtimeClasspath

# Tại sao spring-webmvc được chọn ở version này?
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath

# Graph dùng khi biên dịch/chạy test
./gradlew dependencies --configuration testRuntimeClasspath
```

Trên Windows, dùng `.\gradlew.bat` thay cho `./gradlew`. `dependencyInsight` giúp thấy đường kéo dependency vào và các lý do chọn version. Ví dụ nhiều library yêu cầu phiên bản khác nhau của `jackson-databind`, lệnh `dependencyInsight --dependency jackson-databind --configuration runtimeClasspath` hữu ích hơn việc đoán version từ tên starter.

**Chú ý về Gradle conflicts:** Gradle mặc định ưu tiên phiên bản cao nhất trong các version được yêu cầu tương thích với quy tắc/constraint đang áp dụng; Maven có cơ chế mediation khác. Constraint, `enforcedPlatform`, resolution strategy và plugin quản lý dependency có thể thay đổi kết quả. Không áp dụng máy móc quy tắc của Maven để giải thích Gradle hoặc ngược lại.

## 6. Starter cung cấp thư viện, auto-configuration quyết định cấu hình runtime

Một starter chứa metadata dependency; **auto-configuration** chủ yếu được thực hiện bởi các lớp Spring Boot (đặc biệt ở `spring-boot-autoconfigure` và những auto-configuration được module liên quan cung cấp).

Sau khi `@SpringBootApplication` khởi động ứng dụng, cơ chế auto-configuration xem xét các điều kiện, ví dụ:
- **`@ConditionalOnClass`**: thư viện/class cần thiết có xuất hiện trên classpath không?
- **`@ConditionalOnMissingBean`**: ứng dụng đã khai báo bean để thay thế mặc định chưa?
- **`@ConditionalOnProperty`**: tính năng có bật bằng cấu hình không?
- **Loại ứng dụng**: đang chạy Servlet web, reactive web hay ứng dụng không phải web?

Ví dụ có `spring-boot-starter-web` trong Boot 3.x, các lớp Spring MVC và Tomcat nhúng có trên runtime classpath; nếu ứng dụng chạy theo mô hình Servlet và các điều kiện cấu hình thỏa mãn, Spring Boot có thể tự tạo web server, DispatcherServlet và nhiều bean tích hợp. **Có thư viện trên classpath là điều kiện đầu vào, không phải bảo đảm vô điều kiện mọi bean sẽ được tạo**.

Để tự xem lý do một auto-configuration được áp dụng hoặc bỏ qua, với ứng dụng đang chạy thử có thể bật `--debug` khi khởi động hoặc đặt `debug=true` trong cấu hình test/dev. Spring Boot sẽ in **Conditions Evaluation Report**; kiểm tra từng điều kiện matched/unmatched thay vì dựa vào suy đoán từ graph dependency. Không mặc định bật debug ở môi trường production nếu log quá chi tiết.

## 7. Ví dụ hoàn chỉnh: một starter tạo được ứng dụng HTTP

Dùng một trong hai cấu hình Maven/Gradle ở trên. Tạo `src/main/java/com/example/starterdemo/StarterDemoApplication.java`:

```java
package com.example.starterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class StarterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StarterDemoApplication.class, args);
    }
}

@RestController
class HelloController {

    @GetMapping("/hello")
    String hello() {
        return "Hello from Spring Boot";
    }
}
```

Đây là một tệp Java hợp lệ trên Java 17+: lớp public có tên trùng `StarterDemoApplication.java`; `HelloController` là lớp package-private trong cùng tệp. Spring Boot component scan từ package `com.example.starterdemo` và nhận diện controller này.

Chạy ứng dụng bằng một trong hai lệnh (dự án cần có Wrapper tương ứng):

```bash
# Dự án Gradle:
./gradlew bootRun

# Hoặc dự án Maven:
./mvnw spring-boot:run
```

Trên Windows, dùng `.\gradlew.bat bootRun` hoặc `.\mvnw.cmd spring-boot:run`. Sau khi ứng dụng khởi động thành công ở cấu hình mặc định, gửi yêu cầu HTTP:

```bash
curl -s http://localhost:8080/hello
```

Phần **nội dung response** mong đợi là:

```text
Hello from Spring Boot
```

Tùy shell và cách hiển thị, công cụ có thể thêm lời nhắc/dấu xuống dòng; body endpoint là chính xác chuỗi trên. Nếu port 8080 bận hoặc `server.port` đã thay đổi, dùng cổng thực tế. Lệnh `curl` chỉ chứng minh endpoint trả lời, không tự chứng minh toàn bộ graph đúng; cần thêm `dependencies`/`dependency:tree` để kiểm tra thành phần và version.

Diễn giải cơ chế theo thứ tự:

1. `spring-boot-starter-web` mang các dependency Spring MVC, Servlet server và các thư viện hỗ trợ lên classpath.
2. BOM/dependency management giúp giải các version thuộc nhóm tương thích.
3. Java compiler tìm thấy `SpringApplication`, `@RestController` và `@GetMapping` từ những thư viện đã resolve.
4. Khi chạy, Spring Boot đọc classpath, áp dụng auto-configuration, tạo web server/DispatcherServlet nếu các điều kiện thỏa mãn.
5. HTTP `GET /hello` được Spring MVC chuyển đến `HelloController.hello()`.
6. Khi đóng gói executable JAR, plugin đưa class của ứng dụng và runtime dependencies vào artifact theo cấu trúc Spring Boot.

**Nếu bỏ `spring-boot-starter-web` và không thay bằng dependency web tương đương**, các import `org.springframework.web.bind.annotation.*` không còn được bảo đảm tồn tại khi compile. Nếu chỉ thêm các thư viện web bằng tay, ứng dụng có thể vẫn chạy, nhưng bạn phải hiểu và duy trì đủ các thành phần cùng version cần thiết. Đó là lợi ích thực tế của starter.

## 8. Khi thêm nhiều starter: chia sẻ thư viện, không nhân đôi module

Ví dụ ứng dụng vừa phục vụ HTTP vừa sử dụng JPA:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Ở đây:
- `starter-web` đưa hạ tầng web vào graph.
- `starter-data-jpa` đưa Spring Data JPA, Hibernate và các thành phần JDBC/giao dịch liên quan.
- `runtimeOnly 'org.postgresql:postgresql'` thêm driver PostgreSQL lúc chạy; nó không nhất thiết phải có trên compile classpath của mã ứng dụng nếu bạn chỉ dùng các API chuẩn như `DataSource`.
- `starter-test` dành cho test.
- Dependency được yêu cầu bởi nhiều nhánh, ví dụ một số thành phần Spring Framework, sẽ được resolve theo version chọn cuối cùng chứ không cần khai báo lặp cho từng starter.

Để chạy thật bạn vẫn phải cấu hình datasource/credentials và có cơ sở dữ liệu đang hoạt động. Chỉ thêm `starter-data-jpa` có thể khiến khởi động thất bại nếu không có DataSource/driver/cấu hình hợp lệ. Lỗi này phản ánh điều kiện cấu hình chưa đầy đủ, **không chứng minh rằng starter bị hỏng**.

Đừng thêm `spring-boot-starter-web` lẫn `spring-boot-starter-webflux` chỉ để “lấy đủ tính năng”: trong Spring Boot 3.x, khi cả Spring MVC và WebFlux có mặt, Boot thường ưu tiên ứng dụng kiểu Spring MVC trừ khi cấu hình khác. Chọn Servlet hoặc reactive dựa trên mô hình kiến trúc đã định; dùng WebClient riêng không nhất thiết đòi chuyển toàn bộ ứng dụng sang reactive server.

## 9. Tùy chỉnh: exclusion và thay thế thành phần mặc định

Starter là **lựa chọn mặc định có chủ đích**, nhưng không bắt buộc dùng mọi thành phần mà nó kéo vào.

Ví dụ thay Tomcat mặc định bằng Jetty khi sử dụng `spring-boot-starter-web` với Boot 3.3.x.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

Maven (trong `<dependencies>`):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

**Chỉ là ví dụ thay thế server; không cần làm việc này với project dùng Tomcat bình thường.** Sau thay đổi, chạy test và xem dependency tree/runtimeClasspath để chắc Tomcat không được đưa vào theo một đường dependency khác. Gradle exclusion trên một nhánh hoặc Maven exclusion trên một dependency không bảo đảm artifact bị loại bỏ nếu một nhánh khác vẫn yêu cầu nó.

Nếu một thư viện cần version khác version BOM quản lý, hãy xác định nguyên nhân thật: yêu cầu tính năng, CVE, thay đổi API, hoặc xung đột với thư viện thứ ba. Ưu tiên nâng **phiên bản Spring Boot** lên bản được bảo trì phù hợp và kiểm thử tương thích trước khi ghim riêng một transitive dependency. Version override có thể làm mất tính đồng bộ mà BOM đã cung cấp.

Đặc biệt, **không dùng exclusion để che lỗi** nếu không hiểu thư viện đó làm gì. Bỏ một artifact có thể khiến ứng dụng biên dịch được nhưng runtime gặp `ClassNotFoundException`, `NoClassDefFoundError`, lỗi tạo bean hoặc tính năng bị mất.

## 10. Starter ảnh hưởng đến phạm vi compile, test, runtime và packaging ra sao?

Trong Spring Boot, build tool giải các configuration/scope cho từng giai đoạn:

| Nhu cầu | Gradle thường dùng | Maven thường dùng | Hệ quả chính |
| --- | --- | --- | --- |
| Thư viện ứng dụng dùng khi compile và chạy | `implementation` | `compile` (mặc định) | Phục vụ main code và thường được mang vào runtime artifact |
| Thư viện chỉ cần lúc chạy, như JDBC driver | `runtimeOnly` | `runtime` | Có trên runtime classpath |
| Công cụ/chỉ dùng cho test | `testImplementation` / `testRuntimeOnly` | `test` | Không có trong executable JAR mặc định |
| Thư viện chỉ cần lúc compile | `compileOnly` | `provided` *không tương đương hoàn toàn* | Phụ thuộc build tool/cách triển khai; cần xem runtime classpath cụ thể |

Ví dụ `spring-boot-starter-test` phải được đặt ở test scope/configuration. Nếu khai báo nhầm `implementation` hoặc Maven compile scope, bạn làm tăng diện tích dependency production và có thể vô tình đưa thư viện test vào gói chạy.

Với **Spring Boot executable JAR** mặc định, plugin thường đóng gói class/resource ứng dụng dưới `BOOT-INF/classes/` và runtime dependency JAR dưới `BOOT-INF/lib/`. `src/test/java` và `src/test/resources` không phải nội dung deploy thông thường. Một BOM chỉ quản lý version, bản thân BOM không trở thành một nhóm thư viện JAR cần ship.

Kiểm tra:

```bash
# Gradle:
./gradlew clean test bootJar
./gradlew dependencies --configuration runtimeClasspath

# Maven:
./mvnw clean package
./mvnw dependency:tree
```

Sau đó dùng `jar tf <duong-dan-file-jar>` để liệt kê nội dung JAR **đã được tạo thực tế**. Với Gradle, artifact thường ở `build/libs/`; với Maven, thường ở `target/`. Đường dẫn và tên file tùy project. Đừng lấy `jar tf` để suy đoán compile/test configuration: nó chỉ kiểm tra artifact thành phẩm.

## 11. Khi nào tạo starter riêng?

Trong dự án nhiều module, tổ chức đôi khi tạo “starter nội bộ” để gom một nhóm dependency và auto-configuration chung cho nhiều ứng dụng. Cần phân biệt hai artifact:

- **Thư viện/auto-configuration:** chứa code tự cấu hình, ví dụ các `@AutoConfiguration` được đăng ký bằng metadata phù hợp với phiên bản Spring Boot.
- **Starter:** khai báo dependency tới auto-configuration đó và các thư viện cần thiết, tạo điểm nhập đơn giản cho các ứng dụng.

Không bắt buộc mọi ứng dụng đều cần starter nội bộ. Nếu một module chỉ là thư viện dùng chung, dependency bình thường có thể đủ. Tạo starter có ý nghĩa khi nhiều consumer cần cùng tập thành phần, cùng cấu hình mặc định và cần quản lý phối hợp version. Phải có kiểm thử runtime với classpath thực tế để tránh vô tình kích hoạt bean ngoài mong muốn.

Với module mới học Spring Boot, hãy hiểu **starter chính thức** và dependency tree trước; tự tạo starter là bước thiết kế build/autoconfiguration nâng cao.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn / lỗi | Giải thích đúng và cách kiểm tra |
| --- | --- |
| “Thêm starter là tự tải mọi thư viện Spring.” | Chỉ những dependency reachable từ graph được tải; dùng dependency tree để xem rõ. |
| “BOM thêm tất cả JAR vào project.” | BOM cung cấp quy tắc version, không tự yêu cầu từng artifact. |
| “Starter và auto-configuration là cùng một thứ.” | Starter khai báo dependency; auto-configuration là code Spring Boot đánh giá điều kiện khi chạy. |
| “Có `starter-data-jpa` sẽ tự có PostgreSQL và database.” | Cần driver và cấu hình/instance DB tương ứng; xem runtime classpath và datasource properties. |
| “Không ghi version thì hệ thống tự chọn version mới nhất.” | Parent/BOM/dependency management/platform quyết định hoặc ràng buộc version. Phải xem version resolve thực tế. |
| “Chỉ cần exclude là JAR biến mất hoàn toàn.” | Dependency khác có thể kéo lại; kiểm tra toàn graph. |
| “Starter test đặt ở `implementation` không ảnh hưởng gì.” | Có thể làm test dependencies rò vào runtime/packaging; dùng test configuration/scope. |
| “Cùng starter thì trên mọi dự án luôn có cùng số JAR.” | Còn phụ thuộc phiên bản Boot, scope, exclusions, các starter khác và conflict resolution. |
| “Nâng một JAR bắc cầu là luôn an toàn.” | Có thể phá tương thích do BOM đồng bộ; đánh giá với test, runtime và tài liệu version mục tiêu. |
| “Build thành công nghĩa là Spring tạo đủ bean.” | Build xác nhận compile/package; điều kiện auto-configuration và môi trường runtime quyết định bean được tạo. |

## 13. Quy trình xác minh mỗi lần thêm starter

1. **Xác định năng lực thật sự cần:** REST Servlet, WebFlux, JPA, JDBC, Security, Actuator hay kiểm thử.
2. **Chọn starter tối thiểu:** thêm dependency trực tiếp với đúng scope/configuration.
3. **Đồng bộ version qua một chiến lược rõ ràng:** Spring Boot parent/BOM cho Maven; dependency-management plugin hoặc Gradle platform cho Gradle.
4. **Xem dependency tree đã resolve:** kiểm tra thư viện, version, nhánh kéo vào và các conflict.
5. **Xem các điều kiện runtime:** nếu bean/web server không có hoặc cấu hình khác dự kiến, bật condition report trong môi trường phát triển.
6. **Chạy test và package:** xác nhận tính năng thật hoạt động, không chỉ dependency được download.
7. **Kiểm tra artifact:** không đóng gói nhầm thư viện test; loại bỏ dependency thừa một cách có kiểm chứng.
8. **Khi nâng phiên bản:** review thay đổi starter/BOM, chạy lại dependency tree, test và xác nhận tương thích runtime.

### Ghi nhớ

**Starter = tập hợp “cần thư viện gì”; BOM = quản lý “dùng version nào”; Maven/Gradle = giải graph và dựng classpath; Spring Boot auto-configuration = quyết định “khởi tạo bean nào khi chạy”; packaging = chọn “những gì đi vào artifact triển khai”.** Hiểu năm lớp này giúp bạn kiểm soát dependency rõ ràng thay vì coi một dòng `spring-boot-starter-*` như một hộp đen.