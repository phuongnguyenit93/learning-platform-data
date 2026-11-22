# Nội suy thuộc tính trong tài nguyên và tránh xung đột với placeholder Spring

## 1. Mục tiêu

Khi build ứng dụng Spring Boot, các file trong `src/main/resources` có thể chứa cả **giá trị biết ở lúc build** (artifact version, tên sản phẩm, mã build) lẫn **biến chỉ có lúc ứng dụng chạy** (cổng HTTP, URL dịch vụ, cấu hình theo môi trường). Cả Maven, Gradle và Spring đều hỗ trợ thay thế placeholder; nếu cùng đọc ký hiệu `${...}` mà không phân biệt giai đoạn, một placeholder của Spring có thể bị thay quá sớm, biến mất hoặc làm build lỗi.

Sau bài này, bạn sẽ biết:

1. **Resource filtering/build-time interpolation** khác **Spring property placeholder/runtime resolution** ở điểm nào.
2. File nào được copy, được nội suy và nằm ở đâu sau `process-resources`, `processResources`, `jar` hoặc `bootJar`.
3. Tại sao Maven dùng `@...@` cho biến build và `${...}` cho Spring runtime; vai trò quan trọng của `<useDefaultDelimiters>false</useDefaultDelimiters>`.
4. Cách cấu hình filtering đúng khi dùng hoặc không dùng `spring-boot-starter-parent`, tránh xử lý nhầm file nhị phân và `src/test/resources`.
5. Cách làm tương ứng với Gradle: một cách **thay token chính xác** không chạm Spring placeholder và một cách dùng `expand()` cần escape.
6. Viết ví dụ chạy được với Spring Boot 4.1.2, Java 17, Maven và Gradle, cùng bài test kiểm tra tài nguyên đã lọc.
7. Chẩn đoán lỗi placeholder qua chuỗi **source → processed resource → packaged JAR → runtime Environment**.

**Kịch bản thực hành:** tại thời điểm build, version của project là `1.0.0`; ứng dụng runtime giữ `${APP_MESSAGE:Hello runtime}` và `${SERVER_PORT:8080}` để có thể đổi bằng biến môi trường mà **không rebuild JAR**.

## 2. Ba giai đoạn khác nhau

~~~text
[1] Mã nguồn trong repo
src/main/resources/application.properties
  app.build-version=@project.version@       <- token build-time
  app.message=${APP_MESSAGE:Hello runtime}  <- Spring placeholder runtime
  server.port=${SERVER_PORT:8080}

                 |
                 | Maven resources:resources / Gradle processResources
                 v

[2] Tài nguyên sau build
Maven:  target/classes/application.properties
Gradle: build/resources/main/application.properties
  app.build-version=1.0.0
  app.message=${APP_MESSAGE:Hello runtime}
  server.port=${SERVER_PORT:8080}

                 |
                 | Boot Maven repackage / Gradle bootJar
                 v

[3] Spring Boot executable JAR
BOOT-INF/classes/application.properties
  app.build-version=1.0.0
  app.message=${APP_MESSAGE:Hello runtime}
  server.port=${SERVER_PORT:8080}

                 |
                 | JVM + Spring Environment đọc cấu hình khi khởi động
                 v

Runtime:
  APP_MESSAGE không được đặt -> "Hello runtime"
  APP_MESSAGE=Hello production -> "Hello production"
  SERVER_PORT không được đặt -> 8080
~~~

Bảng phân biệt:

| Cơ chế | Khi nào? | Ai xử lý? | Ký hiệu thường gặp | Nguồn giá trị |
| --- | --- | --- | --- | --- |
| **Maven resource filtering** | `process-resources`, trước compile/package | `maven-resources-plugin` | `@project.version@`; mặc định còn hỗ trợ `${...}` nếu không tắt | POM/project properties, filter files, Maven user/system properties |
| **Gradle CopySpec/filter** | Task `processResources`, trước đóng gói | Gradle CopySpec hoặc filter reader | `@project.version@` khi tự định nghĩa token | `project.version` hoặc map token đã chọn |
| **Gradle `expand()`** | Khi `processResources` copy file | Groovy `SimpleTemplateEngine` | `${buildVersion}` và một số biểu thức template | Map truyền cho `expand` |
| **Spring property placeholder** | Khi Spring tải/resolve cấu hình lúc chạy | Spring `Environment`, property sources, binding | `${APP_MESSAGE:Hello runtime}`, `${server.port}` | Environment variables, system properties, command-line args, configuration files,... |
| **Spring Expression Language (SpEL)** | Tại điểm framework đánh giá expression thích hợp | Spring | `#{...}` | Context Spring và các đối tượng được phép |

**Không nhầm lẫn:** `@Value("${app.build-version}")` trong Java là một Spring placeholder *trong source Java*, không phải file resource. Maven Resources Plugin không scan và thay nội dung source Java theo cấu hình thông thường. Tính năng `@Value` chỉ được Spring áp dụng khi bean được tạo và giá trị cấu hình được phân giải.

## 3. Ví dụ đầu vào và đầu ra đúng

Tệp **`src/main/resources/application.properties`**:

~~~properties
spring.application.name=filter-demo
app.build-version=@project.version@
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

**Input của bước build:** file trên + Maven project version `1.0.0` (hoặc Gradle project version tương đương).

**Output mong muốn sau resource filtering:**

~~~properties
spring.application.name=filter-demo
app.build-version=1.0.0
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Chỉ **`@project.version@`** được thay; hai biểu thức `${...}` vẫn nguyên vẹn trong file được đóng gói. Khi chạy, Spring đọc các property sources và resolve:

- `${APP_MESSAGE:Hello runtime}`: lấy `APP_MESSAGE` trong môi trường nếu có; nếu không có, dùng chuỗi mặc định.
- `${SERVER_PORT:8080}`: lấy `SERVER_PORT` nếu được cung cấp và có giá trị phù hợp; nếu không, mặc định là `8080`.
- `app.build-version=1.0.0`: phiên bản do build ghi vào artifact. Đây là giá trị mặc định của cấu hình đóng gói; Spring vẫn có thể nhận giá trị được override bởi property source có ưu tiên cao hơn, ví dụ command line.

### Cú pháp default của Spring không phải Maven expression

Trong Spring, dấu hai chấm trong `${NAME:default}` là dấu phân cách giữa **tên property** và **giá trị fallback**. Đừng chuyển `${NAME:default}` thành token Maven/Groovy chỉ vì nó có dấu `$` và ngoặc nhọn.

Nếu chỉ có placeholder `${NAME}` không có default mà không tìm thấy `NAME` trong các property sources, điểm sử dụng có thể gây lỗi không resolve được placeholder; cách xử lý phụ thuộc cách truy cập giá trị. Dùng default có chủ đích, hoặc yêu cầu biến bắt buộc và kiểm tra tại startup.

## 4. Maven: vì sao cần đổi delimiter?

Apache Maven Resources Plugin có thể dùng cả hai kiểu token **`${name}`** và **`@name@`** khi filtering được bật với delimiter mặc định. Spring cũng dùng **`${...}`** nên có vùng ký hiệu trùng nhau:

~~~properties
# Source cần giữ cho Spring xử lý lúc chạy
spring.datasource.url=${DB_URL:jdbc:postgresql://localhost:5432/demo}
server.port=${SERVER_PORT:8080}
~~~

Nếu Maven được phép xem mọi `${...}` là build token, những biến trùng tên với Maven/project/system properties có thể bị thay bằng giá trị ở lúc build. Những biến không có lời giải phù hợp có thể không được thay; **không dựa vào việc token đang chưa được resolve để kết luận an toàn**. Một thay đổi property của CI hoặc corporate parent có thể gây khác biệt ở bản build sau.

**Giải pháp Maven thường dùng:** chuyển placeholder build sang **`@...@`** và vô hiệu hóa delimiter mặc định:

~~~xml
<configuration>
    <delimiters>
        <delimiter>@</delimiter>
    </delimiters>
    <useDefaultDelimiters>false</useDefaultDelimiters>
</configuration>
~~~

Ý nghĩa:

- `<delimiter>@</delimiter>`: token build có dạng `@project.version@`, `@project.artifactId@`, `@my.build.property@`.
- `<useDefaultDelimiters>false</useDefaultDelimiters>`: **không thêm** các delimiter mặc định, đặc biệt `${...}`, vào tập delimiter của filtering.
- Khi đó file resource được lọc có thể chứa cả token `@project.version@` và Spring placeholder `${APP_MESSAGE:...}` mà không xung đột với nhau.

Spring Boot starter parent đã có các mặc định resource filtering phù hợp cho `application.properties`/`application.yml` và các file profile tương ứng, dùng `@...@` để giảm xung đột. **Khi không dùng starter parent**, việc import BOM `spring-boot-dependencies` **không mang theo cấu hình Maven Resources Plugin**; bạn phải khai báo `<resources>` và plugin/delimiter theo nhu cầu.

### Chỉ khai báo delimiter chưa đủ

Maven không tự nội suy mọi file dưới `src/main/resources` trừ khi resource tương ứng được khai báo `<filtering>true</filtering>`. Thông thường, việc copy resources có thể vẫn xảy ra nhưng giữ nguyên byte của source file. Cần **cả hai**: xác định **file được lọc** và xác định **kiểu token được thay**.

## 5. Maven: cách chọn đúng file cần filtering

Không nên bật `<filtering>true</filtering>` trên toàn bộ cây resources rồi hy vọng không ảnh hưởng ảnh, font, file PDF, certificate, file compressed, template hoặc JSON chứa ký tự gần giống delimiter. Filtering chỉ nên áp dụng cho **file văn bản đã biết có token**. File khác phải được copy nguyên dạng.

Một cách rõ ràng trong `<build>`:

~~~xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>true</filtering>
        <includes>
            <include>application.properties</include>
        </includes>
    </resource>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
        <excludes>
            <exclude>application.properties</exclude>
        </excludes>
    </resource>
</resources>
~~~

Resource thứ nhất xử lý **chỉ** `application.properties`. Resource thứ hai copy các tệp còn lại **không filtering**. Hai phần loại trừ qua lại giúp không vô tình copy ghi đè lại `application.properties` đã lọc.

Nếu project sử dụng nhiều file cấu hình, cần mở rộng cặp `includes`/`excludes` theo đúng danh sách được dùng, ví dụ:

~~~xml
<include>application.properties</include>
<include>application-*.properties</include>
<include>application.yml</include>
<include>application-*.yml</include>
<include>application.yaml</include>
<include>application-*.yaml</include>
~~~

**Lưu ý:** đoạn thứ hai là danh sách mẫu cho cả hai tập pattern, không phải một `pom.xml` độc lập. Không nhất thiết phải lọc tất cả cấu hình profile; chỉ lọc những file thực sự chứa token build. Đừng dùng filtering cho file nhị phân. Maven có sẵn cơ chế bỏ qua một số đuôi ảnh và tùy chọn `nonFilteredFileExtensions`, nhưng **tách vùng được lọc và không lọc** vẫn giúp tránh việc nhầm định dạng.

### YAML và giá trị chứa ký tự đặc biệt

Trong YAML, token mang dấu `@` nên đặt trong chuỗi được quote, vì giá trị `@...@` không phải một scalar YAML an toàn khi đứng trần ở vị trí đầu:

~~~yaml
app:
  build-version: "@project.version@"
  message: "${APP_MESSAGE:Hello runtime}"
server:
  port: "${SERVER_PORT:8080}"
~~~

Output sau filtering là `build-version: "1.0.0"` và Spring placeholders vẫn ở dạng string. Khi Spring bind `server.port` sang số, giá trị đã resolve phải là số hợp lệ. Nếu nội suy build làm thay đổi YAML thành cú pháp không hợp lệ, build tool vẫn có thể copy thành công: cần parse/khởi động để kiểm chứng.

### Test resources là nhánh riêng

`src/main/resources` đi qua `process-resources`. `src/test/resources` đi qua `process-test-resources`; chúng có cấu hình `testResources` và goal riêng. Khi dùng Spring Boot starter parent, cấu hình mặc định chỉ lọc **production configuration**, không mặc nhiên lọc mọi test resource theo cùng cách.

Nếu test có `src/test/resources/application.properties` cùng tên, file test có thể che khuất file main trên test classpath, làm kiểm chứng resource filtering sai mục tiêu. Trong bài thực hành bên dưới **không tạo file test resource cùng tên**, để test đọc chính output từ `src/main/resources`.

## 6. Ví dụ Maven độc lập, không dùng starter parent

Chọn Java 17, Spring Boot 4.1.2, Maven 3.6.3+, JDK tương thích. Ví dụ chủ ý **không có `<parent>`**, nhằm chứng minh phần filtering cần cấu hình thủ công khi chỉ import Spring Boot BOM.

Cấu trúc:

~~~text
filter-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/FilterDemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/dev/example/FilteredResourceTest.java
~~~

### 6.1. `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>filter-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>4.1.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>application.properties</include>
                </includes>
            </resource>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
                <excludes>
                    <exclude>application.properties</exclude>
                </excludes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>4.1.2</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <phase>package</phase>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Cơ chế:

- Import BOM để phiên bản starter được quản lý; không dùng `spring-boot-starter-parent`.
- Maven Resources Plugin `3.5.0` chỉ lọc `application.properties` với delimiter `@`. `useDefaultDelimiters=false` bảo toàn biểu thức `${...}` cho Spring.
- `maven-compiler-plugin` biên dịch bằng cú pháp/API/bytecode theo `release=17`.
- Surefire `3.6.1` chạy JUnit Jupiter test của ví dụ.
- `maven-jar-plugin` tạo JAR thông thường, Boot Maven Plugin `repackage` tạo executable archive. Cấu hình build plugin độc lập với resource filtering; hai phần chỉ phối hợp trong lifecycle.
- Tệp khác, như `banner.txt` hoặc ảnh tĩnh ở `src/main/resources/static`, được copy ở resource thứ hai mà không bị nội suy.

### 6.2. `src/main/resources/application.properties`

~~~properties
spring.application.name=filter-demo
app.build-version=@project.version@
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Đây là **file đầu vào**. Không thay `@project.version@` thành `${project.version}` trong ví dụ Maven, vì việc đó làm lẫn namespace build và Spring.

### 6.3. `src/main/java/dev/example/FilterDemoApplication.java`

~~~java
package dev.example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FilterDemoApplication {
    @Value("${app.build-version}")
    private String buildVersion;

    @Value("${app.message}")
    private String message;

    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }

    @GetMapping("/info")
    public String info() {
        return "build=" + buildVersion + "; message=" + message;
    }
}
~~~

Khi Spring tạo bean controller, hai field được inject qua `@Value` theo Environment tại runtime. `@Value` ở đây là ví dụ ngắn; với nhiều property có cấu trúc phức tạp, dùng `@ConfigurationProperties` và validation phù hợp hơn. Các placeholder trong source Java không bị Maven Resources Plugin tự thay.

### 6.4. `src/test/java/dev/example/FilteredResourceTest.java`

~~~java
package dev.example;

import java.io.InputStreamReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class FilteredResourceTest {
    @Test
    void interpolatesBuildVersionButPreservesSpringPlaceholders()
            throws IOException {
        try (var input = getClass().getResourceAsStream("/application.properties")) {
            assertNotNull(input, "Missing processed application.properties");
            var properties = new Properties();
            properties.load(new InputStreamReader(input, StandardCharsets.UTF_8));

            assertEquals("1.0.0", properties.getProperty("app.build-version"));
            assertEquals("${APP_MESSAGE:Hello runtime}",
                    properties.getProperty("app.message"));
            assertEquals("${SERVER_PORT:8080}",
                    properties.getProperty("server.port"));
        }
    }
}
~~~

Test đọc **file đã copy vào test classpath**, không mở trực tiếp file source. Trong cấu trúc ví dụ không có `src/test/resources/application.properties` trùng tên, nên nó kiểm chứng đúng output resource filtering. Hai assertion về placeholder là điều kiện quan trọng: bản build phải giữ nguyên chuỗi cho Spring runtime.

### 6.5. Chạy từng bước và kiểm tra output

Tại thư mục có `pom.xml`:

~~~bash
mvn -version
mvn clean process-resources
~~~

Mở **`target/classes/application.properties`**. Nội dung kỳ vọng chính xác:

~~~properties
spring.application.name=filter-demo
app.build-version=1.0.0
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Bước tiếp theo:

~~~bash
mvn clean verify
java -jar target/filter-demo-1.0.0.jar
~~~

Tại terminal khác, khi server đã khởi động và môi trường chưa đặt `APP_MESSAGE` hoặc `SERVER_PORT`:

~~~bash
curl -fsS http://localhost:8080/info
~~~

**HTTP response body chính xác:**

~~~text
build=1.0.0; message=Hello runtime
~~~

Response body là chuỗi do controller trả về; không chứa newline do code. Log Spring Boot và Maven khác nhau theo hệ thống, nên không trình bày chúng là stdout cố định.

Nếu môi trường đặt `APP_MESSAGE=Hello production`, khởi động lại **cùng JAR** sẽ trả:

~~~text
build=1.0.0; message=Hello production
~~~

Điều này chứng minh **version** được điền tại build, còn **message** được resolve tại runtime. Có thể kiểm tra giá trị được override mà không chỉnh môi trường máy bằng:

~~~bash
java -jar target/filter-demo-1.0.0.jar --app.message="Changed at runtime"
~~~

Với lệnh trên, HTTP response body tương ứng là `build=1.0.0; message=Changed at runtime`. Nếu muốn đổi cổng, truyền `--server.port=8081` rồi gọi URL cổng 8081.

### 6.6. Sau khi repackage, file nằm ở đâu?

Trong `target/filter-demo-1.0.0.jar`, với executable JAR mặc định, tài nguyên được đặt tại:

~~~text
BOOT-INF/classes/application.properties
~~~

Có thể xem danh sách:

~~~bash
jar tf target/filter-demo-1.0.0.jar
~~~

Trên máy có `unzip` có thể đọc ngay file đã package:

~~~bash
unzip -p target/filter-demo-1.0.0.jar BOOT-INF/classes/application.properties
~~~

Nó phải có `app.build-version=1.0.0` và giữ nguyên hai `${...}`. Nếu `target/classes` đúng nhưng packaged JAR sai, cần kiểm tra archive nào đang được inspect, `repackage` và các bước copy/ghi đè resources sau đó.

## 7. Maven có starter parent: điều gì tự có, điều gì vẫn phải xem?

Khi POM có:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>
~~~

starter parent cung cấp mặc định **resource filtering** của các file application configuration và đặt token lọc theo kiểu `@...@` để tránh xung đột `${...}`. Vì vậy, trong project dùng parent, ví dụ:

~~~properties
app.build-version=@project.version@
app.port=${APP_PORT:8080}
~~~

thường không phải tự viết toàn bộ `resources` và `maven-resources-plugin` như POM độc lập ở mục 6. Nhưng **phải kiểm tra effective POM** nếu corporate parent, profile hoặc plugin configuration khác ghi đè defaults. Không suy luận rằng tất cả nội dung trong `src/main/resources` đều được filtering giống nhau.

Dùng:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn clean process-resources
~~~

Khi không dùng starter parent, cấu hình filter mặc định của parent **không được import qua BOM**. Nếu quên, bạn có thể thấy `app.build-version=@project.version@` vẫn còn nguyên trong `target/classes/application.properties` hoặc placeholder Spring bị thay sai vì Maven vẫn chấp nhận `${...}`.

**Vấn đề khác:** tùy chọn `spring-boot:run` với `addResources=true` có thể đặt `src/main/resources` trực tiếp trên classpath để hỗ trợ reload, đi vòng qua tài nguyên đã được Maven filtering. Khi chạy ứng dụng trong chế độ đó, giá trị từ file source có thể khác file được package. Xác minh đúng chế độ chạy; kiểm tra `target/classes` và JAR là bằng chứng của artifact thực sự.

## 8. Gradle: hiểu rõ nguy cơ của `expand()`

Gradle Java plugin tạo task `processResources`, thường copy `src/main/resources` sang `build/resources/main`. Mặc định việc copy không nhất thiết nội suy token trong nội dung. Bạn có thể dùng:

~~~groovy
tasks.named('processResources') {
    filesMatching('application.properties') {
        expand(buildVersion: project.version.toString())
    }
}
~~~

Khi đó Gradle `expand()` dùng **Groovy SimpleTemplateEngine**. File source cho cách này có thể là:

~~~properties
app.build-version=${buildVersion}
app.message=\${APP_MESSAGE:Hello runtime}
server.port=\${SERVER_PORT:8080}
~~~

Kết quả dự kiến sau copy:

~~~properties
app.build-version=1.0.0
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Trong **file đầu vào dùng `expand()`**, dấu `\` ngay trước `${...}` là phần **escape của Groovy template**, để biểu thức Spring không bị Gradle lấy làm template. Sau xử lý, ký tự escape này không còn trong file output. Đây là cú pháp của **cách dùng Gradle `expand()`**, không phải hướng dẫn chèn backslash trong mọi file Spring.

**Điểm cần nhớ:** nếu áp dụng `expand(project.properties)` trên mọi file thay vì scope một file và các key cụ thể, Spring `${...}` có thể bị Groovy đánh giá như expression, bị thay bằng giá trị không mong muốn hoặc gây lỗi vì biến không tồn tại/cú pháp không hợp lệ. Đây là một xung đột **cơ chế**, không được khắc phục bằng việc thay Java runtime.

Vì escape dễ bị quên trong dự án có nhiều property Spring, bài này ưu tiên một biến thể Gradle **thay đúng token `@project.version@` bằng phép thay chuỗi literal**.

## 9. Gradle: ví dụ tránh xung đột bằng thay token chính xác

Giữ nguyên `application.properties` và mã Java ở mục 6, tức là:

~~~properties
spring.application.name=filter-demo
app.build-version=@project.version@
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Dưới đây là cấu hình **Gradle Groovy DSL** dùng cùng convention `@project.version@` với Maven, chỉ thay chính token đó. Nó không gọi Groovy `expand()` nên các placeholder Spring `${...}` được giữ nguyên không cần escape.

**`settings.gradle`**

~~~groovy
rootProject.name = 'filter-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

def buildVersionForResources = project.version.toString()

tasks.named('processResources') {
    filteringCharset = 'UTF-8'
    inputs.property('resourceBuildVersion', buildVersionForResources)

    filesMatching('application.properties') {
        filter { String line ->
            line.replace('@project.version@', buildVersionForResources)
        }
    }
}
~~~

**Ý nghĩa từng đoạn:**

- `id 'java'` tạo `processResources`, `compileJava`, `test` và các task Java cơ bản.
- `id 'org.springframework.boot' version '4.1.2'` cung cấp `bootJar` để đóng gói executable Spring Boot JAR.
- `platform(SpringBootPlugin.BOM_COORDINATES)` nhập BOM đồng bộ với phiên bản plugin; starter không cần ghi version thủ công.
- `filteringCharset = 'UTF-8'` tránh phụ thuộc charset mặc định khi đọc/ghi text.
- `filesMatching('application.properties')` giới hạn filter vào **một file văn bản**; ảnh, binary và các file khác không bị thay.
- `filter { String line -> line.replace(...) }` chỉ thay đúng literal `@project.version@`, không hiểu `${...}` là template, không đánh giá expression của Spring.
- `inputs.property('resourceBuildVersion', ...)` khai báo version là input của task, để Gradle nhận biết thay đổi version và xử lý lại resources khi cần. Nếu tự phát triển các filter phức tạp, khai báo thêm input thực sự ảnh hưởng output.
- `tasks.named('test') { useJUnitPlatform() }` bật JUnit Platform cho test.

**Chạy khi project có Gradle Wrapper** với Gradle phù hợp với Spring Boot 4.1.2 (Gradle 8.14+ hoặc 9.x được hỗ trợ) và JDK 17 có sẵn:

~~~bash
./gradlew clean processResources
./gradlew test
./gradlew bootJar
java -jar build/libs/filter-demo-1.0.0.jar
~~~

Trên Windows: dùng `gradlew.bat`. Nếu không có Wrapper, dùng bản Gradle tương thích được cài sẵn. Không tự giả định mọi project đều đã có `gradlew`.

Tệp output sau `processResources` là:

~~~text
build/resources/main/application.properties
~~~

với nội dung:

~~~properties
spring.application.name=filter-demo
app.build-version=1.0.0
app.message=${APP_MESSAGE:Hello runtime}
server.port=${SERVER_PORT:8080}
~~~

Trong `bootJar`, tệp này được package vào `BOOT-INF/classes/application.properties`, còn bytecode/controller và dependency runtime được đóng gói theo layout Boot. Unit test `FilteredResourceTest` từ mục 6 cũng có thể dùng trong project Gradle, vì nó đọc file resource thông qua classpath thay vì gắn cứng đường dẫn Maven `target/classes`.

**Kiểm chứng HTTP** giống ví dụ Maven: chạy JAR rồi gọi `curl -fsS http://localhost:8080/info`, nhận `build=1.0.0; message=Hello runtime` nếu không có env override.

### Vì sao dùng `filter { String line -> ... }` thay vì Ant `ReplaceTokens`?

Gradle cũng cho phép dùng Ant filter `org.apache.tools.ant.filters.ReplaceTokens` để xử lý các token `@name@`. Nó phù hợp với nhiều dự án Gradle 8/9. Tuy nhiên tài liệu Gradle đã lưu ý cơ chế cung cấp Ant classes mặc định trong build script thay đổi từ Gradle 10. Phép biến đổi chuỗi qua filter closure của ví dụ **không cần phụ thuộc Ant** và chỉ thay token được chỉ định, thích hợp làm ví dụ rõ ràng.

Nếu hệ thống có **nhiều token**, nên quản lý map chính xác hoặc tách resource filter thành cơ chế có kiểm thử, tránh hàng loạt lệnh `replace` rời rạc và việc quên khai báo inputs tương ứng.

## 10. Maven, Gradle và Spring khác nhau ở đâu?

| Câu hỏi | Maven | Gradle | Spring Boot runtime |
| --- | --- | --- | --- |
| Tệp đầu vào | `src/main/resources` | `src/main/resources` | Classpath và các nguồn cấu hình bên ngoài |
| Bước xử lý | `resources:resources` ở `process-resources` | `processResources` | Spring `Environment` / config binding |
| Token bài học | `@project.version@` | `@project.version@` nếu dùng filter literal; `${buildVersion}` nếu dùng `expand` | `${APP_MESSAGE:default}` |
| Nguồn giá trị | POM, filter files, Maven properties | `project.version`, map explicit | Env vars, system props, args, YAML/properties,... |
| Output nhìn thấy | `target/classes/application.properties` | `build/resources/main/application.properties` | Giá trị được resolve khi ứng dụng chạy |
| Có chạm file source? | Không: copy sang target | Không: copy sang build | Không: resolve trong process |
| Dùng Spring placeholder trong resource? | Giữ nguyên khi tắt default delimiters | Giữ nguyên với filter literal; escape khi dùng `expand` | Phải resolve đúng hoặc dùng default có chủ đích |

**Một quy tắc thực dụng:** **build chỉ điền các giá trị gắn với artifact** như version và build ID; **runtime điền các giá trị gắn với môi trường** như host, port, secret hay URL dịch vụ. Điều này giúp một artifact chạy qua dev/test/staging/prod mà không phải xây lại theo mỗi môi trường.

## 11. Trường hợp profile và nhiều file application configuration

Dự án thực tế thường có:

~~~text
src/main/resources/
├── application.properties
├── application-dev.properties
├── application-prod.yml
├── static/logo.png
└── certificates/public.crt
~~~

Không nên bật filtering toàn bộ chỉ vì một file có `@project.version@`. Hãy lập danh sách các file **chứa token build** và giới hạn filter cho chúng; các file khác copy nguyên bản.

Với Maven, mẫu `includes` và `excludes` phải tương ứng. Nếu `application-prod.yml` cần nội suy, thêm pattern cho nó ở resource lọc và loại nó khỏi resource copy không lọc. Với Gradle, `filesMatching` có thể nhận nhiều Ant-style patterns để áp dụng cùng một filter chỉ cho các file cấu hình chọn lọc.

**Không trộn hai cơ chế:** `application-prod.yml` là một file cấu hình profile **được Spring lựa chọn tại runtime**, còn Maven/Gradle filtering xảy ra **trước runtime**. Tất cả file profile được lọc nếu đã nằm trong tập lọc của build, **không phải chỉ file profile đang active** khi chạy build, trừ khi bạn chủ động dùng cấu hình build khác.

Khi đặt `@project.version@` trong YAML, nên quote:

~~~yaml
app:
  build-version: "@project.version@"
  endpoint: "${API_ENDPOINT:https://example.org}"
~~~

Cấu hình trên vừa tránh cú pháp YAML không an toàn của token `@...@`, vừa giữ Spring placeholder để resolve theo environment khi chạy. Chỉ có output thực tế sau copy và chạy application mới chứng minh cả hai bước đúng.

## 12. Các lỗi thường gặp, nguyên nhân và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm chứng và sửa |
| --- | --- | --- |
| `@project.version@` vẫn nguyên ở `target/classes` | `<filtering>true</filtering>` chưa bật, file không nằm trong include, plugin cấu hình sai | Xem effective POM, `resources` và log `process-resources` |
| `${APP_MESSAGE:...}` bị thay tại build | Maven vẫn bật default delimiter `${...}` hoặc Gradle dùng `expand` trên file | Maven: `useDefaultDelimiters=false`; Gradle: token literal hoặc escape trong source dùng `expand` |
| Gradle `expand` báo biến không tồn tại | Groovy hiểu một Spring placeholder là template | Escape `\${...}` trước `expand` hoặc chuyển sang filter literal như ví dụ |
| Maven project có starter parent nhưng không lọc | Parent bị thay/overridden, resource pattern khác, plugin config ghi đè | Xem effective POM và output `target/classes` |
| Spring runtime báo Could not resolve placeholder | Biến runtime không có, tên sai, không có default, hoặc file được chọn không chứa property | Kiểm tra Env, command-line args, tên property và config files được load |
| JAR đang chạy có value cũ dù source đã đổi | Chạy JAR build cũ, cache, sai artifact hoặc tệp ngoài override | `clean` build lại có chủ đích, đọc file trong JAR và xác minh runtime config |
| `src/main/resources` đúng nhưng `target/classes` khác | Đó có thể là nội suy build bình thường, hoặc token bị replace nhầm | So source/output từng dòng; nhận biết đúng token build và runtime |
| Test thấy file application khác | `src/test/resources/application.properties` che khuất resource main | Xem test classpath, đổi tên test config hoặc kiểm tra rõ nguồn được đọc |
| YAML parse lỗi ở token `@project.version@` | Giá trị chứa `@` không được quote | Dùng `"@project.version@"` và xác nhận YAML sau filtering |
| File ảnh/font/JAR bị hỏng sau build | Áp dụng text filter cho resource nhị phân | Tách resources filtered/nonfiltered; chỉ lọc text |
| Runtime chạy được nhưng version trả về rỗng/sai | Token không được resolve hoặc runtime có config override | Kiểm tra processed file, file packaged rồi config priority |
| `spring-boot:run` có behavior khác `java -jar` | `addResources` hoặc chế độ run dùng raw source resources thay vì processed copy | Kiểm tra classpath của chế độ chạy và so với packaged artifact |
| Build xanh nhưng môi trường production sai | Build đã nhúng giá trị phụ thuộc môi trường, không chờ runtime | Chỉ bake metadata bất biến; runtime inject URLs, secrets, ports |
| Filter tiếng Việt bị lỗi ký tự | Charset nguồn khác charset resource filtering | Dùng UTF-8 thống nhất; Maven `encoding`, Gradle `filteringCharset` |
| Version thay đổi nhưng Gradle vẫn dùng output cache cũ | Custom filter thiếu khai báo version là input | Dùng `inputs.property` như ví dụ; kiểm tra `processResources` task outcome |
| Build dùng profile khác nhưng token cũ | Maven profile/filter file/properties không giống dự kiến | Kiểm tra `mvn help:effective-pom`, active profiles, các property build |

**Nguyên tắc điều tra:** kiểm tra theo trình tự **file source → output của resources task → nội dung resource trong JAR → giá trị Spring Environment**. Khi tìm ra điểm đầu tiên sai khác so với kỳ vọng, khoanh vùng lỗi chính xác hơn so với việc chỉ nhìn log cuối.

## 13. Checklist QA có thể tự động hóa

### Kiểm tra ở mức tài nguyên sau build

1. Sau `mvn clean process-resources` hoặc `./gradlew clean processResources`, file `application.properties` được tạo ở đúng thư mục đầu ra.
2. Các token build bắt buộc đã được nội suy, ví dụ `app.build-version=1.0.0`.
3. Không còn token `@project.version@` nếu nó là token bắt buộc phải thay trong file đó.
4. Spring placeholders trong file output vẫn nguyên: `${APP_MESSAGE:Hello runtime}`, `${SERVER_PORT:8080}`.
5. Mọi resource không yêu cầu filtering được copy nguyên byte, đặc biệt binary.
6. Source file trong git không bị thay đổi bởi quá trình build.

### Kiểm tra ở mức executable JAR

1. `mvn clean verify` hoặc `./gradlew clean build` chạy các task/test bắt buộc.
2. Đúng executable Spring Boot JAR được tạo; `jar tf` cho thấy `BOOT-INF/classes/application.properties`.
3. Nội dung file trong JAR khớp file sau `processResources`.
4. Chạy `java -jar` thành công trên JDK mục tiêu, route `/info` trả version từ build và message theo môi trường.
5. Thử một môi trường có `APP_MESSAGE` khác; message thay đổi **không cần rebuild artifact**.
6. Kiểm tra production config được cấp ở runtime và không lộ secrets trong JAR/log.

Có thể bổ sung một test tự động đọc `application.properties` từ classpath, giống `FilteredResourceTest`. Nó phát hiện regression của delimiter và file include khi POM hoặc build script thay đổi. Với CI có nhiều môi trường, không dùng version hard-code trong assertion dài hạn; có thể truyền build version kỳ vọng hoặc sinh metadata test riêng. Assertion trong ví dụ cố định `1.0.0` để dễ xác nhận tính đúng đắn của bài học.

### Phân biệt kiểm tra kỹ thuật và runtime

`mvn process-resources` chạy thành công chỉ chứng minh goal resource processing đã hoàn tất; nếu một token tên sai vẫn nguyên, Maven có thể không coi đó là lỗi. Vì vậy cần assertion về **nội dung output**, không chỉ exit code. Tương tự, Spring khởi động được không nhất thiết khẳng định một giá trị đến từ build-time: property source bên ngoài có thể ghi đè; hãy so sánh từng tầng.

## 14. Bài tập và đáp án

**Bài 1.** Một file có `app.version=@project.version@` và `server.port=${PORT:8080}`. Maven đã bật filtering với delimiter `@` nhưng chưa tắt default delimiter. Rủi ro là gì?

**Đáp án:** Maven vẫn có thể xem `${...}` là token build, dẫn tới thay quá sớm khi có thuộc tính trùng hoặc khác biệt theo môi trường build. Thêm `<useDefaultDelimiters>false</useDefaultDelimiters>`.

**Bài 2.** POM import `spring-boot-dependencies` nhưng không kế thừa starter parent. Có tự nhận resource filtering của parent không?

**Đáp án:** Không. BOM import quản lý dependency version, không import plugin configuration; phải khai báo `resources` và Maven Resources Plugin cho filtering.

**Bài 3.** `mvn clean process-resources` tạo file `target/classes/application.properties` có `app.build-version=1.0.0` nhưng `app.message=${APP_MESSAGE:Hello runtime}`. Có phải build chưa nội suy xong không?

**Đáp án:** Đó chính là output mong muốn. Biến build-time đã được thay; Spring placeholder cần giữ cho runtime.

**Bài 4.** Tại sao không nên dùng Gradle `expand(project.properties)` cho toàn bộ resources có `${...}`?

**Đáp án:** Vì `expand` dùng Groovy template có cùng cú pháp `${...}`, có thể đánh giá nhầm Spring placeholder. Hạn chế file/key được expand, escape Spring placeholder, hoặc dùng filter literal theo `@...@`.

**Bài 5.** Khi source YAML chứa `build-version: @project.version@` mà chưa được xử lý, có vấn đề gì?

**Đáp án:** Token bắt đầu bằng `@` có thể không hợp lệ trong YAML scalar chưa quote. Dùng `build-version: "@project.version@"`.

**Bài 6.** Tại sao cần xem `target/classes` hoặc `build/resources/main` mà không chỉ mở source file?

**Đáp án:** Source không bị build thay đổi; nội suy diễn ra khi copy, nên output mới cho thấy token nào đã được thay, giữ nguyên hoặc làm sai.

**Bài 7.** Unit test đọc `/application.properties` thấy version đúng nhưng test integration thấy runtime message khác. Có phải resource filtering sai không?

**Đáp án:** Chưa chắc. Spring runtime có thứ tự ưu tiên property sources, biến môi trường, system properties và command-line args; cần kiểm tra giá trị ở từng tầng.

**Bài 8.** Vì sao nên giữ JDBC URL, token bí mật, service endpoint và cổng trong runtime config thay vì điền từ CI vào JAR?

**Đáp án:** Tránh nhúng secrets và ràng buộc artifact vào một môi trường, tăng khả năng deploy cùng artifact qua nhiều môi trường và giảm rủi ro rò rỉ.

**Bài 9.** Gradle đổi `version='1.0.0'` thành `1.0.1`; vì sao ví dụ khai báo `inputs.property('resourceBuildVersion', ...)`?

**Đáp án:** Để task `processResources` nhận biết version ảnh hưởng đầu ra khi kiểm tra incremental build/build cache, không tái sử dụng output không phù hợp.

**Bài 10.** Trong Spring Boot app, `@Value("${app.build-version}")` được Maven thay ngay trong `.java` lúc `process-resources` không?

**Đáp án:** Không. Maven Resources Plugin xử lý các resource file đã khai báo; `@Value` được Spring resolve lúc tạo bean ở runtime.

## 15. Checklist khi áp dụng vào dự án thật

- [ ] Liệt kê rõ các **giá trị gắn với build** cần bake vào artifact (version, commit ID không bí mật).
- [ ] Liệt kê rõ các **giá trị runtime** cần giữ cho Spring Environment resolve.
- [ ] Dùng delimiter build tách khỏi Spring `${...}`, ưu tiên `@...@` trong Maven.
- [ ] Với Maven, cấu hình `<filtering>true</filtering>` đúng resource và `<useDefaultDelimiters>false</useDefaultDelimiters>` khi dùng `@`.
- [ ] Không cho text filtering chạy trên image, font, PDF, archive hoặc binary.
- [ ] Với YAML, quote các token `@...@` chưa được thay.
- [ ] Nếu không có starter parent, cấu hình resources/plugin rõ ràng; import BOM không đủ.
- [ ] Với Gradle, dùng filter token chính xác hoặc escape Spring placeholder khi dùng `expand()`.
- [ ] Đặt `filteringCharset=UTF-8` hoặc Maven `encoding=UTF-8` cho văn bản.
- [ ] Kiểm tra các file profile được hoặc không được lọc đúng ý định.
- [ ] Kiểm tra `src/test/resources` riêng và tránh test resource trùng tên che kết quả main.
- [ ] Test output sau resource processing và nội dung tệp bên trong executable JAR.
- [ ] Chạy smoke test ở runtime, xác nhận biến môi trường có thể thay kết quả không cần rebuild.
- [ ] Không bake secrets hoặc cấu hình production độc quyền vào artifact.
- [ ] Đối chiếu source, processed resources, JAR và Spring Environment khi debug.

**Ghi nhớ:** **Build-time token → Maven/Gradle thay khi copy resource; Spring placeholder → giữ nguyên để Spring resolve khi chạy.** Tách delimiter, giới hạn file được nội suy và kiểm tra output thực tế là ba việc quan trọng nhất để tránh xung đột.

## 16. Tài liệu tham khảo chính thức

1. [Spring Boot — Automatically Expand Properties at Build Time (Maven và Gradle)](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html#howto.properties-and-configuration.expand-properties)
2. [Spring Boot Maven Plugin — Using the Plugin; without the Parent POM](https://docs.spring.io/spring-boot/maven-plugin/using.html)
3. [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
4. [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
5. [Maven Resources Plugin — Filtering Binary Files](https://maven.apache.org/plugins/maven-resources-plugin/examples/binaries-filtering.html)
6. [Gradle — Working With Files: Filtering File Content](https://docs.gradle.org/current/userguide/working_with_files.html)
7. [Gradle — CopySpec API: expand, filesMatching, filter](https://docs.gradle.org/current/javadoc/org/gradle/api/file/CopySpec.html)
8. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
9. [Spring Boot 4.1.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
