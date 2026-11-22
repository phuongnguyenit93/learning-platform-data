# Chạy ứng dụng khi phát triển bằng `spring-boot:run` và `bootRun`

## 1. Hai lệnh cùng mục tiêu, hai cơ chế build khác nhau

Khi phát triển ứng dụng Spring Boot, lập trình viên thường cần khởi động trực tiếp từ mã đã biên dịch, nhìn log, gọi endpoint, gắn debugger và sửa mã nhanh. Có hai cách tương ứng với công cụ build của dự án:

- **Maven:** `./mvnw spring-boot:run` gọi goal `run` của `spring-boot-maven-plugin`.
- **Gradle:** `./gradlew bootRun` gọi task `bootRun` được tạo bởi Spring Boot Gradle plugin khi kết hợp với Java plugin.

Cả hai chạy **ứng dụng từ classes/resources và runtime dependencies do build tool chuẩn bị**, thường chưa cần tạo executable JAR. Chúng dành cho **vòng lặp phát triển tại máy local**, khác với kiểm thử artifact đã đóng gói bằng `java -jar`.

Một lần `spring-boot:run` hay `bootRun` thành công cho biết ứng dụng có thể khởi động trên **development classpath** với các cấu hình đang áp dụng. Nó **không** tự chứng minh unit tests đã đạt, nội dung JAR đúng, môi trường production tương thích hoặc executable archive đã được tạo.

| Tiêu chí | Maven: `spring-boot:run` | Gradle: `bootRun` |
| --- | --- | --- |
| Bản chất | Goal của Spring Boot Maven Plugin. | Task loại `BootRun` kế thừa `JavaExec`. |
| Build definition | `pom.xml`. | `build.gradle` / `build.gradle.kts`. |
| Lệnh | `./mvnw spring-boot:run`. | `./gradlew bootRun`. |
| Runtime | JVM ứng dụng được Maven plugin fork; goal thường giữ terminal khi web app còn chạy. | `JavaExec` chạy JVM con; task thường giữ terminal khi web app còn chạy. |
| Classpath | Classes/resources và runtime dependencies Maven đã resolve. | Main source set runtime classpath. |
| Truyền Spring arguments | `-Dspring-boot.run.arguments="--server.port=18085"`. | `--args="--server.port=18085"`. |
| Chọn profile | `-Dspring-boot.run.profiles=dev`. | `--args="--spring.profiles.active=dev"`. |
| Tham số JVM | `-Dspring-boot.run.jvmArguments="..."`. | `jvmArgs(...)`, `systemProperty(...)`, `debugOptions`. |
| Main class | Plugin tự tìm hoặc cấu hình `mainClass`. | Task tự tìm hoặc cấu hình `bootRun.mainClass`. |
| Resource reload | DevTools, tùy chọn `addResources`. | DevTools, tùy chọn `sourceResources`. |
| Packaging | `mvn package` + Boot `repackage` là bước khác. | `bootJar`/`build` là bước khác. |

**Cách chọn:** dùng Wrapper mà repository đã chọn. Project Maven không cần có Gradle; project Gradle không cần có Maven. Bài viết dùng cùng một Java application để so sánh, nhưng mỗi build definition là một lựa chọn độc lập.

### 1.1. Ba tầng tham số cần phân biệt

~~~text
Shell / build-tool command
   |-- Maven -D... hoặc Gradle -P...    -> cấu hình build tool/plugin/task
   |-- plugin/task chuyển JVM arguments -> JVM ứng dụng: -Xmx, -Dfoo=bar, JDWP
   '-- plugin/task chuyển app arguments -> main(String[] args): --server.port, --spring.profiles.active
                                         |
                                     Spring Boot Environment
~~~

- **Build tool property** không mặc nhiên là Java system property của app.
- **JVM argument** ảnh hưởng tiến trình Java đang chạy ứng dụng, ví dụ heap, debug hoặc `-Ddemo.mode=local`.
- **Application argument** là chuỗi dành cho `main(String[] args)`; Spring Boot xử lý `--server.port` và `--spring.profiles.active` như configuration properties.
- **Environment variable** được JVM con kế thừa từ shell nếu có và Spring Boot có thể đọc như một property source.

Nhầm các tầng này là nguyên nhân phổ biến khiến thêm `-Dserver.port=18085` hoặc `-Pport=18085` nhưng server vẫn mở ở port khác.

## 2. Chuẩn bị đúng toolchain và mô hình thử nghiệm

Ví dụ sử dụng **Spring Boot 3.3.13 và Java 17** làm bộ phiên bản cố định để bài tập dễ tái lập. Đây chỉ là version minh họa, không phải khẳng định dòng mới nhất/còn hỗ trợ hiện tại. Khi dùng dự án thật, chọn phiên bản Spring Boot, Maven/Gradle và JDK đã được tổ chức hỗ trợ.

Yêu cầu:

1. Có Java entrypoint thật, gọi `SpringApplication.run(...)`.
2. Có Spring Boot build plugin và starter phù hợp. Plugin build và starter dependency phục vụ hai chức năng khác nhau.
3. Maven/Gradle Wrapper có trong source repository và chạy được.
4. JDK build và runtime tương thích với Spring Boot/version classfile.
5. Với Web, có một HTTP port còn trống (ví dụ **18085**); với app Batch/CLI, cần phép thử job/exit code thay HTTP.
6. Nếu app phụ thuộc DB, broker hoặc dịch vụ ngoài, môi trường local phải có các dependency đó hoặc test double phù hợp.

### 2.1. Cấu trúc mã chung

Trong dự án chọn **một trong hai** định dạng POM hoặc Gradle:

~~~text
dev-run-demo/
  pom.xml                       # Maven, nếu chọn Maven
  # hoặc:
  settings.gradle               # Gradle, nếu chọn Gradle
  build.gradle
  src/main/java/com/example/devrun/DevRunApplication.java
  src/test/java/com/example/devrun/DevRunApplicationTest.java
~~~

Với Maven cần `mvnw`/`mvnw.cmd` và `.mvn/wrapper/...`; với Gradle cần `gradlew`/`gradlew.bat` và `gradle/wrapper/...`. Wrapper là phần của dự án, không tự sinh từ `pom.xml` hay `build.gradle`.

File `src/main/java/com/example/devrun/DevRunApplication.java`:

~~~java
package com.example.devrun;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DevRunApplication {
    private final Environment environment;

    public DevRunApplication(Environment environment) {
        this.environment = environment;
    }

    public static void main(String[] args) {
        SpringApplication.run(DevRunApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/active-profiles")
    public String activeProfiles() {
        String[] active = environment.getActiveProfiles();
        return active.length == 0 ? "default" : String.join(",", active);
    }
}
~~~

Đây là **class Java hoàn chỉnh trong một project Spring Boot đã có dependency**, không phải file chạy trơ trọi bằng `javac` không có classpath. `@SpringBootApplication` thiết lập ứng dụng, `@RestController` công bố hai HTTP handlers. `/ping` trả body **`pong`**. `/active-profiles` đọc các active profile từ Spring `Environment`: nếu không có active profile trả chuỗi `default` theo logic handler; khi bật riêng profile `dev` sẽ trả `dev`.

File `src/test/java/com/example/devrun/DevRunApplicationTest.java`:

~~~java
package com.example.devrun;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DevRunApplicationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }
}
~~~

Test khởi tạo Spring test context và giả lập HTTP qua **MockMvc**: nó kiểm tra mapping/response **mà không mở port HTTP thật**. Bởi vậy cần thử thêm lệnh development run và gọi `curl` từ terminal khác.

## 3. Maven: POM hoàn chỉnh và cách gọi `spring-boot:run`

Với `spring-boot-starter-parent`, Maven được quản lý các dependency/plugin versions thích hợp. Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>dev-run-demo</artifactId>
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
~~~

Giải thích:

- Starter Web đưa Spring MVC/embedded web server vào runtime classpath; starter Test cung cấp công cụ JUnit/MockMvc ở test scope.
- Parent quản lý compatible dependency versions và nhiều mặc định plugin, bao gồm khả năng `repackage` khi plugin được khai báo.
- `spring-boot-maven-plugin` cung cấp goal `run`. Không có phase Maven tên `run`: gọi **`spring-boot:run`**, không gọi `mvn run`.
- Nếu công ty dùng corporate parent và **chỉ import BOM**, BOM chủ yếu quản lý dependency versions, **không tự khai báo Spring Boot Maven plugin**. Cần cấu hình plugin/version trong POM hoặc parent riêng.

### 3.1. Lệnh chạy và điều chỉnh cấu hình

~~~bash
# macOS/Linux; tại root ứng dụng có Maven Wrapper
./mvnw -version

# Chạy mặc định (Spring Boot Web thường dùng 8080 nếu chưa đặt khác)
./mvnw spring-boot:run

# Chọn HTTP port
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085"

# Bật profile dev bằng shortcut chuyên dụng
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev

# Vừa đổi port, vừa bật profile dev
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085 --spring.profiles.active=dev"
~~~

Chỉ chạy **một instance trên cùng port**. Mỗi dòng là một invocation thay thế; dừng lần trước rồi mới chạy lần sau. Trên Windows đổi `./mvnw` thành `mvnw.cmd`; cách escape quote có thể khác PowerShell/cmd, hãy kiểm tra chuỗi thực tế Maven nhận.

Sau log startup thành công, ở terminal thứ hai:

~~~bash
curl -i http://localhost:18085/ping
curl -i http://localhost:18085/active-profiles
~~~

Nếu chạy với `--spring.profiles.active=dev`, kỳ vọng HTTP 200 với body lần lượt **`pong`** và **`dev`**, giả sử không có active profile khác được thêm bởi cấu hình môi trường. Header HTTP, startup PID và thời gian không phải output cố định. Nếu app chạy port mặc định 8080, dùng 8080 trong URL.

### 3.2. Maven JVM arguments không phải Maven user properties

Spring Boot Maven Plugin chạy app ở **forked JVM**. Dùng:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-Xmx512m -Ddemo.mode=local"
~~~

Ở đây `spring-boot.run.jvmArguments` là Maven property được **plugin** đọc rồi truyền `-Xmx512m`, `-Ddemo.mode=local` cho JVM ứng dụng. Ngược lại:

~~~bash
./mvnw spring-boot:run -Ddemo.mode=local
~~~

`-Ddemo.mode=local` chỉ trực tiếp đến **Maven user properties**, không đảm bảo forked JVM app nhận giá trị ấy. Muốn đưa property vào app, dùng `spring-boot.run.jvmArguments`, cấu hình `systemPropertyVariables`, environment variables hoặc application args theo mục đích.

Chọn nhiều Spring profiles bằng `-Dspring-boot.run.profiles=dev,local` (dấu phẩy). Đừng nhầm `mvn -Pdev`: đây là **Maven build profile** và không tự kích hoạt `spring.profiles.active=dev` trừ khi POM chủ động ánh xạ nó.

### 3.3. Cấu hình goal qua POM

Mảnh sau có thể thêm **bên trong** `<plugin>` khai báo Spring Boot Maven plugin:

~~~xml
<configuration>
    <arguments>
        <argument>--server.port=18085</argument>
    </arguments>
    <profiles>
        <profile>dev</profile>
    </profiles>
    <jvmArguments>-Xmx512m</jvmArguments>
</configuration>
~~~

Đây là **configuration fragment**, không phải một `pom.xml` độc lập. Nó đặt default cho run goal trong dự án. Không mã hóa password hoặc secret trong POM. Với cấu hình môi trường thay đổi thường xuyên, có thể ưu tiên CLI/env thay vì commit port/profile cá nhân vào source.

## 4. Gradle: build script và cách gọi `bootRun`

Với Gradle Groovy DSL, `bootRun` là task subclass `JavaExec`; nó dùng **main source set runtime classpath**, có thể tự tìm class chứa `public static void main(String[])`. Plugin Boot cần được áp cùng Java plugin ở module ứng dụng.

`settings.gradle`:

~~~groovy
rootProject.name = 'dev-run-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Java plugin tạo compile/test source sets và task graph. Spring Boot plugin tạo `bootRun`/`bootJar`; dependency-management plugin phối hợp với Boot để quản lý version các starter. Java toolchain yêu cầu JDK 17 tương thích hoặc Gradle toolchain provisioning phù hợp. Task `bootRun` khác với task `run` của Gradle Application plugin.

### 4.1. Các lệnh Gradle

~~~bash
./gradlew --version
./gradlew tasks --all

# Chạy ứng dụng từ main classpath
./gradlew bootRun

# Đổi HTTP port
./gradlew bootRun --args="--server.port=18085"

# Bật profile dev
./gradlew bootRun --args="--spring.profiles.active=dev"

# Đổi cả port và profile
./gradlew bootRun --args="--server.port=18085 --spring.profiles.active=dev"
~~~

`--args` là option thuộc `JavaExec/BootRun`, không phải `spring-boot.run.arguments` của Maven. Gradle app dùng `gradlew.bat` trên Windows. Với PowerShell, dấu nháy cần được truyền đúng cho Gradle; quan sát startup log để xác nhận các args có hiệu lực.

Nếu có nhiều main class, thêm đoạn Groovy DSL:

~~~groovy
tasks.named('bootRun') {
    mainClass = 'com.example.devrun.DevRunApplication'
}
~~~

Hoặc đặt tại Spring Boot DSL để chia sẻ với các task hỗ trợ:

~~~groovy
springBoot {
    mainClass = 'com.example.devrun.DevRunApplication'
}
~~~

Đây là **hai cách lựa chọn**, không bắt buộc khai báo cùng lúc. Tên class là FQCN có package, không phải tên file có đuôi `.java`.

### 4.2. Cấu hình JVM app, property Gradle và Kotlin DSL

Trong `build.gradle`:

~~~groovy
tasks.named('bootRun') {
    jvmArgs '-Xmx512m'
    systemProperty 'demo.mode', (project.findProperty('demoMode') ?: 'local')
}
~~~

Sau đó:

~~~bash
./gradlew bootRun -PdemoMode=experimental
~~~

`-PdemoMode=experimental` trước hết là **Gradle project property**. Chính cấu hình `systemProperty` chuyển nó sang Java system property `demo.mode` của JVM app. Nếu không có đoạn map này, `-P...` không tự thành Spring property.

**Phân biệt với JVM Gradle:** `-Dorg.gradle.jvmargs=...` thường điều khiển Gradle daemon; nó không tự thay đổi `bootRun.jvmArgs`. Tương tự, Gradle `--debug` chỉ tăng log build; để debug **app JVM** dùng `bootRun --debug-jvm` (mục 8).

Với Kotlin DSL `build.gradle.kts`, mảnh tương đương:

~~~kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    mainClass.set("com.example.devrun.DevRunApplication")
    jvmArgs("-Xmx512m")
    systemProperty("demo.mode", "local")
}
~~~

Đây là **đoạn Kotlin DSL**, dùng khi project đã khai báo Boot/Java plugins trong `build.gradle.kts`. Không copy cú pháp Groovy `mainClass = '...'` nguyên xi vào file Kotlin.

## 5. Truyền Spring profile, port và biến môi trường

Cả hai công cụ đều chạy **cùng mã Spring Boot**. Vì thế sau khi đã truyền app arguments vào `main`, các quy tắc Spring `Environment` là chung.

| Tác vụ | Maven | Gradle |
| --- | --- | --- |
| Chạy app | `./mvnw spring-boot:run` | `./gradlew bootRun` |
| Chạy trên 18085 | `-Dspring-boot.run.arguments="--server.port=18085"` | `--args="--server.port=18085"` |
| Chọn dev | `-Dspring-boot.run.profiles=dev` | `--args="--spring.profiles.active=dev"` |
| Chọn dev,local | `-Dspring-boot.run.profiles=dev,local` | `--args="--spring.profiles.active=dev,local"` |
| JVM heap | `-Dspring-boot.run.jvmArguments="-Xmx512m"` | `bootRun { jvmArgs '-Xmx512m' }` |
| Main class | `-Dspring-boot.run.main-class=com.example.devrun.DevRunApplication` | `bootRun.mainClass` hoặc `springBoot.mainClass` |
| Xem tài liệu tool | `./mvnw spring-boot:help -Ddetail=true -Dgoal=run` | `./gradlew help --task bootRun` |

### 5.1. Dùng environment variables

Spring Boot thường ánh xạ `SERVER_PORT` tới `server.port` và `SPRING_PROFILES_ACTIVE` tới `spring.profiles.active`. Ví dụ macOS/Linux:

~~~bash
export SERVER_PORT=18085
export SPRING_PROFILES_ACTIVE=dev
./mvnw spring-boot:run
# Với một project Gradle khác: ./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
$env:SERVER_PORT = "18085"
$env:SPRING_PROFILES_ACTIVE = "dev"
.\mvnw.cmd spring-boot:run
# Với Gradle: .\gradlew.bat bootRun
~~~

Biến môi trường được shell truyền cho process con, nên có thể dùng cùng một cách cho Maven/Gradle. Nếu lại truyền `--server.port=18086` trong app arguments, Spring Boot thường ưu tiên command-line arguments hơn environment variables; app sẽ dùng giá trị được ưu tiên. Để debug cấu hình, hãy quan sát **port thực sự được log** và request đúng port.

Đừng đưa secret vào CLI hoặc commit chúng trong `application.yml` nếu có thể dùng biến môi trường/secret store phù hợp. Các profile dev, test, prod là **Spring profiles**; Maven `-Pdev` và Gradle `-Penv=dev` là hai cơ chế build khác, không tự bật Spring profile.

### 5.2. Khi app không có HTTP

Một Spring Batch job hoặc CLI app có thể chạy xong và **trả quyền điều khiển về terminal** rất nhanh. Đó không nhất thiết là lỗi của `run`/`bootRun`. Tiêu chí kiểm chứng khi đó là mã thoát, job execution status, record/output đúng hợp đồng, không phải có server tại port 8080.

## 6. Vòng lặp development: startup, kiểm tra, thay đổi, dừng

Quy trình thực hành nhất quán:

1. Mở terminal tại module ứng dụng và chạy **một lệnh** Maven hoặc Gradle.
2. Quan sát log: main class, active profiles, HTTP port, thông điệp khởi động thành công hoặc stack trace.
3. Dùng terminal khác gọi `curl`; đừng gõ request trong terminal đang giữ foreground app.
4. Khi cần thay đổi code, biên dịch hoặc để IDE cập nhật classpath; xem DevTools có phát hiện không.
5. Dừng lần chạy trước bằng **Ctrl+C** tại terminal chứa invocation. Đợi JVM app dừng và cổng trống trước khi chạy lại cùng port.
6. Khi sắp bàn giao, chạy **test + package + `java -jar` smoke test** riêng, không coi development run là cổng phát hành.

~~~bash
# Terminal 1 (Maven)
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085 --spring.profiles.active=dev"
# Hoặc terminal 1 (Gradle)
# ./gradlew bootRun --args="--server.port=18085 --spring.profiles.active=dev"
~~~

~~~bash
# Terminal 2, sau khi ứng dụng khởi động
curl -i http://localhost:18085/ping
curl -i http://localhost:18085/active-profiles
~~~

**Kỳ vọng:** `/ping` trả status 200 và body `pong`; `/active-profiles` trả `dev` nếu chỉ dev được bật. Header/content-length/status-line phụ thuộc HTTP stack; không cố sao chép một log/stdout cố định thành điều kiện đạt. Chạy test và lưu log thật nếu cần đánh giá.

### 6.1. Cách dừng đúng

- Cả hai lệnh development run thường giữ invocation khi server đang sống; **Ctrl+C** là cách dừng tương tác thông dụng.
- `spring-boot:stop` thuộc cặp `spring-boot:start`/`stop` phục vụ integration-test lifecycle với JMX; **không dùng làm “nút stop chung”** cho `spring-boot:run` hay Gradle `bootRun`.
- Nếu Ctrl+C không kết thúc, cần xác định đúng PID/port rồi cleanup có kiểm soát; không kill toàn bộ tiến trình `java` vì có thể làm mất IDE, build khác hoặc dịch vụ của đồng nghiệp.
- Với app có shutdown hooks/database connection, hãy xem log shutdown và không kết luận chỉ dựa trên việc terminal xuất hiện prompt.

## 7. DevTools, thay đổi Java class và reload tài nguyên

`spring-boot-devtools` cải thiện phát triển bằng cách nhận diện **classpath output thay đổi** rồi restart/refresh theo cấu hình. Nó **không tự biên dịch** tất cả file `.java` vừa được lưu; IDE/build phải sinh lại `.class` để cơ chế theo dõi nhận được thay đổi.

### 7.1. Maven DevTools

Thêm vào `pom.xml` trong `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Dùng dependency management của parent cho version. Khi classpath thay đổi, DevTools có thể restart ứng dụng. `optional` tránh thư viện DevTools bị kéo transitively khi thư viện này được dùng như dependency; Spring Boot repackage thông thường loại DevTools khỏi executable package theo mặc định. Vẫn nên kiểm tra archive thật khi cần.

Nếu muốn Maven run dùng trực tiếp source resources:

~~~xml
<!-- Mảnh thêm vào cấu hình spring-boot-maven-plugin -->
<configuration>
    <addResources>true</addResources>
</configuration>
~~~

**Trade-off:** resource source có thể phục vụ tức thì trong development, nhưng resource filtering có thể bị bỏ qua nên behavior không hoàn toàn giống bản packaged. Chỉ bật khi dự án thật sự cần.

### 7.2. Gradle DevTools

Thêm vào `dependencies` của `build.gradle`:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

`developmentOnly` được Boot Gradle plugin nhận cho dependency phát triển. Khi cần static resources nạp từ source path, có thể bổ sung:

~~~groovy
tasks.named('bootRun') {
    sourceResources sourceSets.main
}
~~~

Bật source resources có thể đổi cách `processResources` và filtering tác động tới môi trường chạy; cần kiểm chứng lại bằng `bootJar` khi đánh giá artifact. `devtools` không đồng nghĩa mọi thay đổi Java đều hot swap trực tiếp; khi IDE chưa compile class mới thì restart thường chưa có input.

### 7.3. Nếu DevTools không restart

Kiểm tra tuần tự: dependency đã hiện trên development classpath chưa → có thay đổi `.class`/resource output không → IDE có bật build/compile phù hợp không → có restart exclusion/trigger-file policy không → log DevTools nói gì. Với resource static, browser cache/template cache có thể che kết quả; đừng vội thay JVM hoặc plugin version.

## 8. Debug JVM chạy ứng dụng

Maven và Gradle đều có **process chạy build tool** và **process chạy Spring app**. Debug đúng mục tiêu phải attach vào **JVM ứng dụng**.

### 8.1. Maven JDWP

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005"
~~~

Ý nghĩa: `server=y` mở debug listener, `suspend=y` khiến JVM chờ debugger, `address=127.0.0.1:5005` giới hạn vào loopback. Tạo Remote JVM debug configuration của IDE với host `localhost`, port `5005`. Khi debugger attach xong main mới tiếp tục; không thấy HTTP server trước khi attach là hành vi mong đợi. Không mở cổng debug ra mạng công khai.

### 8.2. Gradle `--debug-jvm`

Vì `BootRun` kế thừa `JavaExec`:

~~~bash
./gradlew bootRun --debug-jvm
~~~

Gradle chạy JVM app ở debug mode, thường chờ attach trên port 5005 theo default. **Đừng nhầm** option trên với `-Dorg.gradle.debug=true`, vì option đó nhắm vào Gradle daemon/build process.

Khi cần đổi port hoặc trạng thái suspend, bổ sung trong `build.gradle`:

~~~groovy
tasks.named('bootRun') {
    debugOptions {
        enabled = true
        host = '127.0.0.1'
        port = 5006
        server = true
        suspend = true
    }
}
~~~

Chỉ bật rule debug lúc cần, không áp mặc định vào mọi workflow CI. Một ứng dụng đang suspend để chờ debugger chưa sẵn sàng nhận HTTP là hoàn toàn bình thường.

## 9. Vì sao `run`/`bootRun` khác `java -jar`?

Khi development run, ứng dụng dùng **exploded classes/resources và classpath do build tool dựng**. Khi packaged run, `java -jar` dùng **archive thực sự được tạo và phân phối**. Có thể có sai khác về resource filtering, manifest/launcher, dependency scope, working directory, active profile hoặc runtime JDK.

### 9.1. Maven: build và chạy artifact

~~~bash
# Chạy test độc lập
./mvnw test

# Chạy qua package/verify (parent + Boot plugin bind repackage)
./mvnw clean verify

# Tên JAR là ví dụ, phải dùng file thực tế trong target/
jar tf target/dev-run-demo-0.0.1-SNAPSHOT.jar
java -jar target/dev-run-demo-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

Executable Spring Boot JAR thường có `BOOT-INF/classes`, `BOOT-INF/lib`, launcher manifest phù hợp. Nếu `jar tf` không cho thấy cấu trúc này hoặc `java -jar` báo `no main manifest attribute`, kiểm tra `spring-boot-maven-plugin` goal `repackage` đã chạy và chọn đúng file JAR chưa.

### 9.2. Gradle: build và chạy artifact

~~~bash
./gradlew test
./gradlew clean build

# File path theo cấu hình ví dụ, xác nhận tên thật tại build/libs
jar tf build/libs/dev-run-demo-0.0.1-SNAPSHOT.jar
java -jar build/libs/dev-run-demo-0.0.1-SNAPSHOT.jar --server.port=18085
~~~

`bootJar` sinh executable Spring Boot archive; `jar` Java plugin có thể tạo plain JAR `*-plain.jar`. Chọn đúng executable JAR cho phép thử `java -jar`. Đừng chạy đồng thời development instance ở cùng port khi thử packaged JAR.

### 9.3. Hai nhóm cổng kiểm chứng

| Nhóm | Minh chứng | Không suy ra |
| --- | --- | --- |
| Development run | Startup log, HTTP/job smoke trên app classpath. | Artifact đóng gói đúng. |
| Test & packaging | Report Surefire/Gradle Test, exit code build, archive. | App chắc chắn chạy được tại runtime thực. |
| Packaged runtime | `java -jar`, đúng profile, status/body hoặc job output. | Hệ thống đã production ready khi thiếu bảo mật, quan sát, phục hồi... |

**Một `BUILD SUCCESS` và một log “Started” đều là bằng chứng cục bộ**, không đủ để kết luận mọi dependency hoặc use case được kiểm tra. Khi phát hành, giữ commit, JDK, build command, report, artifact name và checksum/digest.

## 10. Chạy trong repository nhiều module

Maven reactor hoặc Gradle multi-project có thể chứa module thư viện và module ứng dụng. **Chỉ module có entrypoint và Spring Boot plugin cần được chạy**.

### 10.1. Maven multi-module

~~~bash
# Giả sử service là module ứng dụng được liệt kê trong reactor
./mvnw -pl service spring-boot:run
~~~

Nếu `service` phụ thuộc library modules chưa được build/install ở local repository, chuẩn bị dependency modules theo quy trình reactor trước khi chạy. Tránh tự động gọi `-am spring-boot:run` rồi tưởng goal chỉ chạy ở module `service`: lựa chọn thêm library modules có thể khiến Maven cố chạy Boot goal ở nơi không có main class. Khi cần, dùng cấu hình skip/plugin executions chính xác cho module library.

### 10.2. Gradle multi-project

~~~bash
# Giả sử app module tên service
./gradlew :service:bootRun
~~~

Gradle task graph có thể build project dependencies theo nhu cầu. Nếu root không có `bootRun` nhưng module `service` có, cần gọi task path đúng. Không áp Spring Boot plugin vào mọi library module chỉ để tiện dùng một lệnh root.

### 10.3. Main class và classpath có nhiều lựa chọn

Khi Boot plugin không thể xác định duy nhất main class, khai báo FQCN tường minh: Maven `mainClass` hoặc Gradle `bootRun.mainClass`. Với Gradle 3.3 có thêm `bootTestRun` cho main ở test source set (nếu muốn scenario test đặc biệt). Maven `useTestClasspath` là tùy chọn khác nhưng **không mặc định**. Việc đưa test dependencies vào development runtime có thể che thiếu dependency production, nên chỉ bật khi hiểu lý do.

## 11. Các lỗi phổ biến và cách xác minh

| Triệu chứng | Nguyên nhân thường gặp | Bước xử lý |
| --- | --- | --- |
| Maven báo `Unknown lifecycle phase "run"`. | Gõ `mvn run` thay vì plugin goal. | Dùng `./mvnw spring-boot:run`. |
| `No plugin found for prefix 'spring-boot'`. | Thiếu plugin/không resolve được plugin prefix. | Kiểm tra `pom.xml`, repositories, Maven settings; dùng `spring-boot:help`. |
| Gradle `Task 'bootRun' not found`. | Không áp Boot plugin + Java plugin ở module gọi. | `./gradlew tasks --all` hoặc `:service:tasks --all`. |
| Gradle `Task 'run' not found`. | Nhầm với Application plugin task `run`. | Gọi đúng `bootRun`. |
| App báo `Port 8080 was already in use`. | Instance cũ còn sống, port khác đang bị chiếm. | Dừng đúng process, đổi `server.port`, dùng `curl` đúng port. |
| Maven `-Dserver.port=...` không tác dụng. | Maven property không tự tới app JVM. | Dùng `spring-boot.run.arguments` hoặc plugin JVM property config. |
| Gradle `-Pport=...` không tác dụng. | Project property không tự tới app. | Dùng `--args` hoặc map qua `systemProperty`/`args` trong `bootRun`. |
| `-Pdev` nhưng Spring không dùng dev. | Nhầm Maven build profile với Spring profile. | Dùng `spring-boot.run.profiles=dev`. |
| `bootRun` có nhiều main class, task fail. | Boot plugin không chọn được một entrypoint. | Đặt FQCN tại `mainClass`. |
| `curl` connection refused. | App chưa startup, sai port/path, đã exit, ở khác host. | Đọc startup log, kiểm tra port, active profile, route. |
| DevTools không restart khi đổi Java source. | Source chưa được compile thành classpath output. | Cấu hình IDE compile/build, xem DevTools logs. |
| Resource ở development khác artifact. | Bật `addResources`/`sourceResources` bỏ qua resource filtering. | Kiểm tra `processResources`, packaged archive và `java -jar`. |
| Lệnh debug không trả HTTP. | JVM đang `suspend=y` chờ debugger. | Attach IDE debugger đúng port, sau đó thử HTTP. |
| Chạy trong IDE/`bootRun` được, JAR fail. | Archive/launcher/runtime dependencies/Java target khác. | Chạy `bootJar`/`repackage`, `jar tf`, `java -jar`. |
| Gradle JVM tăng heap nhưng app vẫn OOM. | Đã chỉnh JVM Gradle daemon thay vì app. | Dùng `bootRun.jvmArgs`. |
| Root build chọn sai module/main. | Chạy goal/task ở aggregator hoặc library module. | Chọn `-pl service` hay `:service:bootRun`, kiểm tra entrypoint. |

### Trình tự chẩn đoán hữu ích

1. Xác định đúng **build tool** và plugin version.
2. Đọc **main class/module** được chọn.
3. Kiểm tra **port, profile, nguồn config** (CLI, environment, POM/Gradle, application files).
4. Xác định **JVM nào nhận** heap/system/debug arguments.
5. Đọc **exception nguyên nhân**, xem dependency/service ngoài có sẵn không.
6. Chạy request/job smoke thực tế.
7. Nếu cần bàn giao, chạy **test/package/binary smoke** riêng.

Không né lỗi bằng cách tắt test, bỏ security hay xoá ngẫu nhiên cache khi chưa biết lỗi xuất phát từ đâu.

## 12. Bài thực hành, bằng chứng và câu hỏi tự đánh giá

### Bài A — Maven

1. Dùng `pom.xml` mục 3 cùng hai file Java mục 2. Xác nhận `./mvnw -version` chạy với JDK tương thích.
2. Gọi `./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=18085 --spring.profiles.active=dev"`.
3. Ở terminal khác gọi `curl -i http://localhost:18085/ping` và `curl -i http://localhost:18085/active-profiles`.
4. Ghi status/body **thực tế**: kỳ vọng `200/pong` và `200/dev`. Ctrl+C để dừng.
5. Chạy `./mvnw test`; xem `target/surefire-reports` xác minh test JUnit đã được phát hiện.
6. Chạy `./mvnw clean package`, kiểm tra executable JAR và thử `java -jar` thật.

### Bài B — Gradle

1. Dùng `settings.gradle`/`build.gradle` mục 4 với cùng Java source/test. Xác nhận `./gradlew --version` và `./gradlew tasks --all` có `bootRun`.
2. Chạy `./gradlew bootRun --args="--server.port=18085 --spring.profiles.active=dev"`.
3. Thực hiện hai request như bài A, xem active profile và cổng đã đúng chưa.
4. Ctrl+C, chạy `./gradlew test`; đọc `build/test-results/test` hoặc `build/reports/tests/test`.
5. Chạy `./gradlew clean bootJar` rồi kiểm tra/chạy executable JAR trong `build/libs`.

### Bài C — so sánh câu lệnh sai/đúng

Thử với một port đang trống:

- Maven: so `-Dserver.port=18085` với `-Dspring-boot.run.arguments="--server.port=18085"`.
- Gradle: so `-Pport=18085` khi chưa cấu hình mapping với `--args="--server.port=18085"`.

Quan sát port **thực**, không chỉ nhìn câu lệnh. Nếu project đã có mapping riêng, mô tả mapping ấy thay vì kết luận `-P...` luôn vô hiệu.

### Checklist đạt bài

- [ ] Phân biệt Maven goal `spring-boot:run` và Gradle `bootRun` task/`JavaExec`.
- [ ] Chạy đúng Wrapper và chọn module ứng dụng có main class.
- [ ] Có Java 17+ project và endpoint kiểm chứng được.
- [ ] Truyền port/profile bằng đúng syntax Maven/Gradle.
- [ ] Giải thích build property ≠ JVM property ≠ app argument.
- [ ] Phân biệt Maven build profile và Spring profile.
- [ ] Điều chỉnh app JVM heap/debug, không nhầm vào JVM build daemon.
- [ ] Quan sát log, request và dừng chính instance đang chạy.
- [ ] Hiểu DevTools chỉ restart khi classpath output thay đổi.
- [ ] Không đánh đồng development run và packaged archive.
- [ ] Chạy test, build executable archive, và `java -jar` smoke riêng.
- [ ] Biết chẩn đoán port conflict, thiếu plugin, main class sai, và resource khác nhau.
- [ ] Với Batch/CLI, chọn job result/exit code thay cho HTTP smoke test.

**Tiêu chí hoàn tất:** nộp một bảng hai dòng Maven/Gradle có lệnh chạy, JDK/Wrapper, profile, HTTP port, response của `/ping` và `/active-profiles`, cách dừng, test report, artifact path và kết quả `java -jar`. Giải thích được vì sao hai lệnh tạo feedback nhanh trong development nhưng kiểm chứng phát hành phải thử artifact được đóng gói.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 Maven Plugin — Running your Application](https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html)
- [Spring Boot 3.3 Gradle Plugin — Running your Application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html)
- [Spring Boot — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Gradle — JavaExec API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)

Các lệnh và kết quả dự kiến được trình bày để thực hành; bài viết **không tuyên bố đã chạy Maven/Gradle hoặc quan sát log trên máy người học**. Hãy dùng cấu hình, phiên bản, source và artifact thật của dự án để xác minh.