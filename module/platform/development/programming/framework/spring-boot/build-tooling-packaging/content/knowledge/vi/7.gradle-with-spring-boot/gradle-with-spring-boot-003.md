# Áp dụng plugin org.springframework.boot cùng java hoặc war

## Mục tiêu bài học

Trong Gradle, `org.springframework.boot` là plugin bổ sung khả năng **chạy** và **đóng gói ứng dụng Spring Boot**. Tuy nhiên, chỉ áp dụng plugin đó chưa tạo đầy đủ một dự án Java hay WAR: nó cần kết hợp với plugin ngôn ngữ/đóng gói thích hợp. Đề bài này tập trung vào hai tổ hợp quan trọng:

- `org.springframework.boot` + `java`: biên dịch Java, chạy kiểm thử, chạy ứng dụng bằng `bootRun` và đóng gói **executable JAR** bằng `bootJar`.
- `org.springframework.boot` + `war`: dùng mô hình ứng dụng web Servlet, đóng gói **executable WAR** bằng `bootWar`, có thể chuẩn bị cho triển khai vào servlet container ngoài.

Sau bài học, bạn có thể xác định plugin nào tạo task nào, đọc đúng `build.gradle`/`build.gradle.kts`, xây dựng một ứng dụng Java Spring Boot tối thiểu bằng hai cách, hiểu `providedRuntime`, kiểm tra JAR/WAR thực tế và sửa những lỗi thường gặp khi chuyển từ JAR sang WAR.

**Giới hạn ví dụ:** các tệp build dưới đây ghim `Spring Boot 3.3.13` và `io.spring.dependency-management 1.1.7` để minh họa một tổ hợp cụ thể đã phát hành, cùng Java 21 và Gradle 8.x phù hợp. Đây không phải chỉ định phiên bản cho dự án khác. Spring Boot 4.x có thay đổi ở một số starter và yêu cầu công cụ; khi dùng phiên bản khác phải kiểm tra tài liệu **đúng phiên bản của dự án**. Đừng chép phiên bản từ ví dụ lên dự án đang hoạt động mà chưa kiểm tra tương thích.

## 1. Mỗi plugin đóng góp phần nào cho dự án?

Ba plugin thường được nhắc cùng nhau nhưng **không có vai trò giống nhau**:

| Plugin | Cung cấp những gì? | Có tự tạo Spring Boot executable archive không? |
| --- | --- | --- |
| `java` (Gradle core) | `sourceSets`, `compileJava`, `processResources`, `classes`, `test`, `jar`, vòng đời `assemble`/`build`, các classpath Java | Không; `jar` thông thường chỉ đóng gói class/resources |
| `war` (Gradle core) | Mở rộng Java, thêm `war`, cấu trúc `src/main/webapp`, `providedCompile` và `providedRuntime` | Không; task `war` tạo WAR thông thường |
| `org.springframework.boot` | Phản ứng với plugin Java/WAR, bổ sung `bootRun`, `bootJar` hoặc `bootWar` cùng các tác vụ/thiết lập dành cho Boot | Có, **khi kết hợp với plugin thích hợp** |
| `io.spring.dependency-management` (tùy chọn) | Quản lý phiên bản thư viện theo BOM, có thể dùng `spring-boot-dependencies` tương ứng với plugin Boot | Không; quản lý dependency, không đóng gói |

**Quan hệ cốt lõi:**

```text
plugins { id 'org.springframework.boot' ... }
        |
        +-- áp dụng cùng java
        |       +-- compileJava / test / jar (Gradle)
        |       +-- bootRun / bootJar (Spring Boot)
        |       \-- assemble -> bootJar
        |
        \-- áp dụng cùng war
                +-- war tự áp dụng java
                +-- compileJava / test / war (Gradle)
                +-- bootWar (Spring Boot)
                \-- assemble -> bootWar
```

Sơ đồ nêu **các tác vụ được bổ sung/đăng ký chính**, không phải toàn bộ DAG của mọi bản Gradle/Spring Boot. Vì `war` dựa trên `java`, khi kết hợp với Boot có thể vẫn thấy `bootJar` và những task Java. Hãy kiểm tra task graph của chính dự án, rồi gọi rõ `bootWar` khi muốn sản phẩm WAR. Đừng kết luận "áp dụng war chắc chắn xóa bootJar".

### "Áp dụng plugin" khác "khai báo nhưng chưa áp dụng"

```groovy
plugins {
    id 'org.springframework.boot' version '3.3.13'
    id 'java'
}
```

Hai plugin được **áp dụng cho project hiện tại**. Trái lại:

```groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
}
```

`apply false` chỉ khai báo plugin/phiên bản để có thể áp dụng nơi khác; **không tạo** `bootJar` cho project hiện tại. Điều này hữu ích ở root của Gradle multi-project, nơi module thư viện có thể chỉ dùng `java-library` còn module ứng dụng mới cần Spring Boot plugin.

Áp dụng Spring Boot plugin **một mình** có rất ít tác động. Nó không tự suy luận "dự án này phải là Java JAR hoặc WAR" nếu chưa có plugin nền tương ứng.

## 2. Tổ hợp `org.springframework.boot` + `java`: executable JAR

### Ví dụ `build.gradle` (Groovy DSL) đầy đủ

Giả sử tạo một dự án Gradle Groovy DSL với `settings.gradle`:

```groovy
rootProject.name = 'demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **cấu hình Java Spring Boot 3.3.x có thể dùng trong dự án** nếu Gradle Wrapper, JDK và mạng/kho thư viện đáp ứng yêu cầu. Dự án cần có mã ứng dụng (phần 5); chỉ có build script không tạo sẵn controller hay lớp `main`.

Giải thích từng phần:

1. `id 'java'` áp dụng quy ước biên dịch, source set `main/test` và tạo các task cơ bản của Gradle.
2. `id 'org.springframework.boot' version '3.3.13'` áp dụng Spring Boot Gradle plugin cho **project này**. Khi thấy `java`, Boot tạo `bootJar` và `bootRun`.
3. `io.spring.dependency-management` giúp quản lý version dựa trên `spring-boot-dependencies` BOM; ở mô hình này có thể không ghi version trên các starter được quản lý. Plugin này **khác** Spring Boot plugin và cần được áp dụng hoặc dùng cơ chế `platform(...)` của Gradle thay thế.
4. `toolchain` yêu cầu Java 21 cho các tác vụ Java theo cấu hình; không bảo đảm máy đang chạy Gradle bằng đúng JDK đó nếu Gradle daemon được cấu hình riêng.
5. `implementation`, `testImplementation`, `testRuntimeOnly` chỉ rõ dependency cho mã chính và test. JUnit Platform cần được cấu hình cho task `test` như trong ví dụ.
6. `rootProject.name` ảnh hưởng tên archive mặc định cùng `version`; tên file có thể thay đổi nếu dự án cấu hình `archiveBaseName` hay `archiveVersion`.

Trong Gradle **Kotlin DSL**, cách áp dụng ba plugin tương đương:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}
```

Đây là **trích đoạn** của `build.gradle.kts`: phần `group`, `version`, `java`, `repositories`, `dependencies` và `tasks.test` cũng cần được khai báo tương đương nếu bạn tạo toàn bộ dự án từ đầu. Không trộn cú pháp Groovy như `id 'java'` vào file `.gradle.kts`.

### Task nào được tạo khi có `java`?

| Task | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `compileJava` | Biên dịch mã Java của source set `main` | Do Gradle Java plugin tạo, không phải riêng Boot |
| `processResources` / `classes` | Xử lý tài nguyên, tập hợp class biên dịch | Thường là bước phụ thuộc của task đóng gói |
| `test` | Chạy kiểm thử (nếu cấu hình và có test) | Thuộc Java plugin; Spring Boot test starter cung cấp thư viện kiểm thử |
| `jar` | JAR **thông thường**, không tự đóng gói toàn bộ runtime dependency | Với Boot phiên bản hiện đại thường mang classifier `plain` |
| `bootJar` | JAR thực thi có mã ứng dụng và runtime dependency | Do Spring Boot plugin thêm khi `java` được áp dụng |
| `bootRun` | Chạy Spring Boot từ main source set và runtime classpath | Dùng khi phát triển, không bắt buộc tạo JAR trước |
| `assemble` / `build` | Vòng đời đóng gói / kiểm tra + đóng gói | Boot nối `bootJar` vào `assemble`; `build` còn chạy `check`/`test` |

Với Spring Boot 3.3, **`bootJar` không đồng nghĩa task `jar`**. Mặc định các task có thể tạo cả archive Boot và archive thường, nên người dùng có thể nhìn thấy thêm `-plain.jar`. Đừng nhầm `-plain.jar` là executable Boot JAR.

### Tại sao `bootJar` chạy được bằng `java -jar`?

Một executable Boot JAR thông thường tổ chức nội dung gần như:

```text
demo-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/demo/DemoApplication.class
│   │   └── com/example/demo/HelloController.class
│   └── lib/
│       └── ... runtime dependency jars ...
└── org/springframework/boot/loader/...
```

Cây là **minh họa**, danh sách tệp thật tùy phiên bản và dependency. Boot cung cấp launcher, manifest và classpath cho các JAR lồng bên trong. JAR thường chỉ có class/resources của project; nếu gọi `java -jar` lên `-plain.jar` thì có thể thiếu `Main-Class` hoặc các dependency cần để khởi động.

Bạn có thể kiểm tra bằng `jar tf` (công cụ của JDK) sau build:

```bash
./gradlew bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

Đường dẫn có thể khác nếu bạn thay `rootProject.name`/`version`/classifier. Tên file phải được lấy từ **đầu ra thực tế trong `build/libs`**, không được phỏng đoán khi chạy ở dự án khác.

## 3. Tổ hợp `org.springframework.boot` + `war`: executable WAR

### Khi nào chọn WAR?

Chọn WAR khi ứng dụng web **Servlet** cần triển khai vào servlet container ngoài như Tomcat phù hợp, hoặc khi quy trình triển khai yêu cầu một file `.war`. Nếu chỉ cần một dịch vụ Spring Boot chạy độc lập, executable JAR thường đơn giản hơn vì ứng dụng tự mang theo embedded server tương ứng.

**WAR triển khai lên servlet container ngoài là một yêu cầu khác với chỉ đổi đuôi JAR thành WAR.** Bạn cần cả cấu hình Gradle, class khởi tạo Servlet và dependency runtime đúng.

### Ví dụ `build.gradle` cho WAR (Groovy DSL) đầy đủ

Tệp `settings.gradle` vẫn có thể là `rootProject.name = 'demo'`. Tệp build:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Chủ ý của ví dụ:**

- `id 'war'` áp dụng **Gradle War plugin**, đồng thời áp dụng Java plugin ngầm. Không bắt buộc liệt kê cả `id 'java'`, dù dự án có thể làm thế nếu cần quy ước riêng.
- Spring Boot plugin thấy `war` thì tạo `bootWar`; nó có thể thấy `java` mà `war` đã kéo vào và tạo thêm những task dành cho Java.
- `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` thích hợp cho **Spring Boot 3.3.x** khi chuẩn bị WAR cho servlet container ngoài. Các dòng Spring Boot khác có thể thay đổi tên starter/runtime; dùng tọa độ phù hợp phiên bản thực.
- `providedRuntime` giữ dependency cần trong lúc chạy và kiểm thử nhưng không đặt chúng vào `WEB-INF/lib` dành cho container bên ngoài. Spring Boot executable WAR xếp chúng vào `WEB-INF/lib-provided` để vẫn có thể chạy qua `java -jar`.
- `testImplementation` và `testRuntimeOnly` phục vụ kiểm thử; không tự biến thành thư viện runtime của ứng dụng.
- WAR này dành cho Spring MVC/Servlet. **Ứng dụng thuần WebFlux dùng mô hình reactive Netty không được hỗ trợ theo lối WAR truyền thống** trong hướng dẫn Spring Boot.

Với Kotlin DSL, phần áp dụng plugin và dependency WAR tương ứng là:

```kotlin
plugins {
    war
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

Đây là **trích đoạn Kotlin DSL**, không phải toàn bộ tệp: khi dựng một dự án hoàn chỉnh vẫn cần `group`, `version`, `java toolchain`, `repositories` và cấu hình test tương ứng. Không sử dụng cú pháp Groovy `providedRuntime '...'` trong `build.gradle.kts`.

### Tác vụ `war` và `bootWar` khác nhau

| Task | Nguồn | Kết quả |
| --- | --- | --- |
| `war` | Gradle War plugin | WAR thông thường theo chuẩn ứng dụng web Java |
| `bootWar` | Spring Boot plugin khi `war` đã được áp dụng | **Executable Boot WAR** với launcher và layout phù hợp |
| `jar` | Gradle Java plugin (được `war` áp dụng) | JAR thông thường nếu task được chạy và không bị điều chỉnh |
| `bootJar` | Spring Boot plugin kết hợp Java plugin | Có thể hiện diện vì `war` cũng áp dụng Java; kiểm tra task graph trước khi quyết định vô hiệu hóa |

Một WAR thông thường tổ chức `WEB-INF/classes`, `WEB-INF/lib` và tài nguyên web. `bootWar` tạo executable WAR có thêm thành phần cho phép `java -jar` và `WEB-INF/lib-provided` khi dùng `providedRuntime`.

```text
demo-0.0.1-SNAPSHOT.war
├── META-INF/
├── WEB-INF/
│   ├── classes/
│   │   ├── com/example/demo/DemoApplication.class
│   │   └── com/example/demo/HelloController.class
│   ├── lib/
│   │   └── ... application runtime jars ...
│   └── lib-provided/
│       └── ... embedded servlet container runtime jars ...
└── org/springframework/boot/loader/...
```

Đây là **cấu trúc khái niệm**; các tệp cụ thể phụ thuộc dependency và Spring Boot version. Thư mục `WEB-INF/lib-provided` giúp ngăn container ngoài tải trùng những JAR mà nó tự cung cấp, trong khi executable WAR vẫn có thể dùng chúng khi chạy bằng `java -jar`.

### Vì sao không dùng `compileOnly` thay `providedRuntime`?

`compileOnly` chỉ đưa thư viện vào compile classpath; nó **không đưa thư viện vào runtime/test runtime classpath** theo cùng cơ chế của WAR plugin. Khi một ứng dụng web cần embedded servlet container trong các bài kiểm thử tích hợp, cấu hình này có thể gây lỗi tải context/khởi tạo web server. `providedRuntime` được thiết kế cho dependency được **container ngoài cung cấp lúc triển khai**, đồng thời Spring Boot biết cách đặt vào `WEB-INF/lib-provided` của executable WAR.

Không đưa nhầm tất cả dependency của ứng dụng vào `providedRuntime`: những thư viện ứng dụng thật sự cần mà container không cấp phải tiếp tục nằm trong `WEB-INF/lib` qua `implementation`/runtime dependency.

## 4. Khi deploy WAR ra container ngoài, phải có `SpringBootServletInitializer`

Lớp `main` dùng `SpringApplication.run` giúp chạy trực tiếp. Khi container ngoài khởi động ứng dụng từ WAR, nó cần con đường khởi tạo Spring thông qua cơ chế Servlet. Spring Boot cung cấp `SpringBootServletInitializer` cho trường hợp này.

Tạo `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(DemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**Đây là lớp Java hoàn chỉnh trong dự án Spring Boot đã khai báo dependency**, biên dịch qua `./gradlew classes` hoặc `./gradlew build`. Không thể dùng `javac DemoApplication.java` đơn lẻ khi chưa cung cấp Spring Boot dependencies trên classpath.

- `@SpringBootApplication` đánh dấu cấu hình gốc/khởi động và hỗ trợ component scanning.
- `main` dùng khi khởi động độc lập (`bootRun`, `java -jar`).
- `configure(SpringApplicationBuilder)` được sử dụng khi deploy WAR và servlet container ngoài khởi tạo ứng dụng qua `SpringBootServletInitializer`.
- `DemoApplication.class` chỉ định nguồn cấu hình cho cả hai cách chạy; tên package/lớp trong đường dẫn phải khớp tên bạn khai báo.

Để thấy kết quả HTTP có thể kiểm chứng, tạo `src/main/java/com/example/demo/HelloController.java`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
```

Với `spring-boot-starter-web` của Boot 3.3.x, hai lớp trên tạo ứng dụng Servlet Spring MVC có một endpoint `GET /hello`. Nếu chạy độc lập với cổng mặc định và không cấu hình context path khác, truy cập `http://localhost:8080/hello` có nội dung phản hồi chính xác:

```text
Hello from Spring Boot
```

Đây là **phản hồi từ controller trong ví dụ**, không phải toàn bộ stdout/log của Gradle hoặc Spring Boot. Khi triển khai WAR lên Tomcat ngoài, URL phụ thuộc **context path do container chọn** (ví dụ `/demo/hello`), cổng và cài đặt container; không mặc định giống `/hello` ở cách chạy độc lập.

**Lưu ý:** lớp `DemoApplication` với `SpringBootServletInitializer` vẫn có thể dùng cho cả executable JAR lẫn WAR. Việc kế thừa initializer có vai trò chủ yếu khi **deploy WAR ra servlet container ngoài**, không bắt buộc cho ứng dụng JAR thuần.

### Kiểm thử khởi động ngữ cảnh

Tạo `src/test/java/com/example/demo/DemoApplicationTests.java`:

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

Lệnh `./gradlew test` sẽ chạy test theo cấu hình ở build script. `contextLoads` kiểm tra việc khởi tạo Spring application context, **không tự kiểm tra mọi endpoint hay luồng nghiệp vụ**. Có `providedRuntime` đúng giúp tránh thiếu servlet runtime trên test classpath khi dùng WAR.

## 5. Chạy, đóng gói và kiểm tra đầu ra

### Chạy bằng Wrapper và xem task thực tế

Đứng tại thư mục gốc có `gradlew` và build script:

```bash
# Kiểm tra phiên bản Gradle Wrapper, không phải phiên bản Spring Boot
./gradlew --version

# Xem các task có sẵn sau khi áp dụng plugin
./gradlew tasks --all

# Xem mô tả task
./gradlew help --task bootJar
./gradlew help --task bootWar

# Xem những task Gradle dự định chạy mà chưa thực thi
./gradlew build --dry-run
```

Nếu chỉ áp dụng `java`, lệnh `help --task bootWar` có thể báo không thấy task. Nếu áp dụng `war`, hãy xem danh sách task thực tế vì `war` áp dụng Java và một số task JAR có thể cùng tồn tại.

Lệnh thực thi cho **dự án JAR**:

```bash
./gradlew clean test
./gradlew bootRun
# Ở cửa sổ terminal riêng, sau khi ứng dụng chạy:
curl http://localhost:8080/hello
# Đóng ứng dụng bằng Ctrl+C, sau đó:
./gradlew bootJar
```

Nếu đang chạy `bootRun` trong terminal hiện tại, nó chặn terminal cho đến khi ứng dụng dừng; `curl` trong ví dụ cần terminal khác. Nếu cổng 8080 đã được ứng dụng khác dùng hoặc project cấu hình cổng khác, hãy đọc log và cấu hình thay vì khẳng định endpoint luôn ở cổng 8080.

Lệnh thực thi cho **dự án WAR**:

```bash
./gradlew clean test
./gradlew bootWar
jar tf build/libs/demo-0.0.1-SNAPSHOT.war
java -jar build/libs/demo-0.0.1-SNAPSHOT.war
```

Dòng `java -jar` dành cho **executable WAR do Spring Boot tạo**. WAR thường sinh bằng task `war` không nhất thiết chạy được theo cách này. Tên archive minh họa dựa trên `rootProject.name=demo` và `version=0.0.1-SNAPSHOT`; kiểm tra tên file thật tại `build/libs`.

Trên Windows PowerShell, chạy tương ứng:

```powershell
.\gradlew.bat clean test
.\gradlew.bat bootJar
.\gradlew.bat bootWar
jar tf .\build\libs\demo-0.0.1-SNAPSHOT.war
java -jar .\build\libs\demo-0.0.1-SNAPSHOT.war
```

Chỉ gọi `bootJar` hoặc `bootWar` tương ứng với sản phẩm muốn thử. Các tác vụ này **không đòi** dự án phải luôn có cả hai loại sản phẩm.

### Mức độ kiểm chứng: task tồn tại, build thành công và chạy được

Phân biệt:

1. `./gradlew tasks --all` thấy `bootWar`: chứng tỏ task đã được đăng ký trong mô hình Gradle, chưa chứng minh cấu hình WAR hoạt động khi thực thi.
2. `./gradlew bootWar` báo thành công và có `build/libs/*.war`: chứng tỏ đóng gói hoàn thành, chưa chứng minh triển khai lên container ngoài thành công.
3. `jar tf` thấy `WEB-INF/classes`, `WEB-INF/lib` và (khi có provided runtime) `WEB-INF/lib-provided`: chứng minh bố cục archive thực tế.
4. `java -jar ...war` chạy được và endpoint phản hồi: kiểm chứng executable WAR theo chế độ nhúng.
5. Deploy WAR lên container **Servlet tương thích** và gọi endpoint qua context path được container cấp: mới chứng minh được trường hợp triển khai truyền thống.

Log Gradle/Spring Boot khác nhau theo Java, dependency, cấu hình và môi trường. Đừng chép một dòng `BUILD SUCCESSFUL` mô phỏng làm bằng chứng nếu chưa chạy build thực.

### Hai archive cùng xuất hiện trong `build/libs`

Khi có Spring Boot plugin, archive do `bootJar`/`bootWar` tạo thường không có classifier; archive thông thường do `jar`/`war` có thể mang hậu tố `-plain.jar` hoặc `-plain.war`. Điều này là **quy ước của các phiên bản plugin hiện đại**, không phải lỗi build hay yêu cầu phải xóa một trong hai.

Đọc `jar tf`, tên task tạo file và classifier trước khi chọn artifact mang đi chạy/triển khai. Không tự đổi đuôi tên file. Nếu chỉ muốn sản phẩm Boot và biết rõ nhu cầu xuất bản, có thể cấu hình tắt task plain, ví dụ:

```groovy
tasks.named('jar') {
    enabled = false
}
```

Đây là **trích đoạn tùy chọn của Groovy DSL**, chỉ dùng khi đã xem phụ thuộc task, yêu cầu xuất bản/library và native image. Không nên vô hiệu hóa `jar` tùy tiện: một số quy trình tạo native image hoặc publication cần JAR thường. Với dự án WAR, việc vô hiệu hóa `bootJar` hoặc `war` cũng cần đánh giá kỹ tương tác `assemble` và các tác vụ khác trước khi sửa.

## 6. Chuyển một ứng dụng từ JAR sang WAR đúng cách

Giả sử ứng dụng Spring MVC đang dùng `java` và tạo executable JAR. Khi chuyển sang WAR cho Tomcat ngoài, làm theo trình tự:

1. **Xác nhận mục đích triển khai:** đích đến là container Servlet tương thích với phiên bản Spring Boot/Jakarta API của ứng dụng. Nếu hệ thống chạy WebFlux thuần trên Netty, đừng áp dụng công thức WAR Servlet này.
2. **Thay `id 'java'` bằng `id 'war'`** trong `plugins` (hoặc áp dụng `war` bên cạnh Java nếu project có lý do riêng). Giữ Spring Boot plugin và cơ chế quản lý dependency phù hợp.
3. **Thêm `providedRuntime` cho embedded servlet container** đúng theo dòng Spring Boot. Với ví dụ 3.3.x đang dùng Tomcat: `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'`.
4. **Cho lớp ứng dụng kế thừa `SpringBootServletInitializer`** và override `configure(...)` như mã ở phần 4, đồng thời giữ `main` cho chế độ chạy độc lập.
5. **Chạy `./gradlew test` rồi `./gradlew bootWar`**, kiểm tra `build/libs`, `jar tf` và bố cục `WEB-INF/lib-provided`.
6. **Thử chạy executable WAR** bằng `java -jar`, sau đó thử **deploy WAR trên container ngoài** và kiểm tra endpoint với context path thực tế.
7. **Kiểm tra task và artifact CI dùng**: script triển khai phải lấy `*.war` từ task `bootWar`, không lấy nhầm `-plain.war` hoặc `-plain.jar`.
8. **Cập nhật hướng dẫn vận hành**: cổng, context path, môi trường cấu hình và runtime servlet container ngoài có thể khác mô hình embedded.

Trong lần chuyển đổi này, mã controller `HelloController` không cần thay đổi chỉ vì JAR thành WAR; thay đổi quan trọng nằm ở **plugin, cách đóng gói, starter servlet và điểm khởi tạo cho container ngoài**.

## 7. Những quan hệ và giới hạn dễ hiểu nhầm

### Spring Boot plugin có tự quản lý tất cả dependency không?

**Không nên suy luận chỉ từ `id 'org.springframework.boot'`.** Theo tài liệu, Spring Boot Gradle plugin có thể kết hợp:

- `io.spring.dependency-management`: khi plugin này được áp dụng cùng Spring Boot plugin, BOM `spring-boot-dependencies` tương ứng được import tự động, giúp bỏ version trên các dependency do BOM quản lý.
- **Gradle native BOM**: khai báo `platform(...)` hoặc `enforcedPlatform(...)` bằng tọa độ BOM phù hợp. `platform` cung cấp các constraint/khuyến nghị; thuật toán resolution còn có thể chọn phiên bản khác khi có yêu cầu phù hợp. `enforcedPlatform` ép hơn và cần thận trọng.

Ví dụ **trích đoạn** Groovy DSL dùng native BOM nếu không dùng `io.spring.dependency-management`:

```groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Đây là cơ chế quản lý phiên bản dependency, **không tự tạo `bootJar`/`bootWar`**. Muốn biết phiên bản cuối cùng của một thư viện, dùng `./gradlew dependencies --configuration runtimeClasspath` và `./gradlew dependencyInsight --dependency ... --configuration runtimeClasspath` thay vì chỉ nhìn BOM.

### Spring Boot plugin version khác Gradle version

`id 'org.springframework.boot' version '3.3.13'` ghim **phiên bản plugin Spring Boot**. Còn `gradle/wrapper/gradle-wrapper.properties`, dòng `distributionUrl`, ghim **bản Gradle** thực thi. `java.toolchain` chỉ **Java language version cho compilation/test tasks thích hợp**. Chúng phải tương thích nhưng không thể thay thế nhau.

Spring Boot 3.3.13 yêu cầu Java 17+ và hỗ trợ Gradle 7.5+ thuộc dòng 7.x hoặc Gradle 8.x theo tài liệu phiên bản đó. Gradle 8.5 có thể chạy trên Java 21. Điều này giải thích ví dụ Java 21/Gradle 8.5 ở đây; dự án thực tế dùng bản khác phải kiểm tra điều kiện tương thích của chính nó.

### Đổi sang `war` không tự triển khai lên container

Task `bootWar` đóng gói một archive. Việc chạy trong servlet container ngoài còn phụ thuộc:

- Mức hỗ trợ Servlet/Jakarta tương thích của container đích.
- Lớp `SpringBootServletInitializer` và cấu hình khởi tạo hợp lệ.
- Phân loại đúng embedded container là `providedRuntime` để tránh xung đột thư viện.
- Tên/context path của WAR, tài nguyên môi trường, cấu hình bảo mật, cổng và logging của container.
- Kiểm tra thực tế trên cùng loại container và cấu hình được triển khai.

Không nên suy từ việc `./gradlew bootWar` thành công rằng file WAR chắc chắn chạy trên bất kỳ bản Tomcat nào.

### Khi nào chỉ dùng `java-library`?

Nếu module chỉ chứa một thư viện Java dùng chung, không có ứng dụng `main` cần chạy, plugin `java-library` và JAR thông thường thường phù hợp hơn. Không áp dụng `org.springframework.boot` cho mọi module trong repository chỉ để có cùng version dependency; quản lý BOM có thể tách biệt khỏi việc áp dụng Boot plugin. Khi module không có lớp `main`, `bootJar` có thể không xác định được entry point và fail nếu cố đóng gói thành executable app.

## 8. Bảng so sánh nhanh JAR và WAR

| Tiêu chí | Boot + `java` | Boot + `war` |
| --- | --- | --- |
| Gradle plugin nền | `java` | `war` (ngầm có `java`) |
| Archive thực thi chính | `bootJar` | `bootWar` |
| Archive thông thường | `jar` | `war` |
| Đuôi sản phẩm | `.jar` | `.war` |
| Đường dẫn build mặc định | `build/libs/` | `build/libs/` |
| Lớp ứng dụng | `BOOT-INF/classes` | `WEB-INF/classes` |
| Thư viện runtime | `BOOT-INF/lib` | `WEB-INF/lib` |
| Embedded servlet runtime "provided" | Thường không tách riêng | `WEB-INF/lib-provided` khi dùng `providedRuntime` |
| Chạy bằng `java -jar` | Có, với Boot executable JAR | Có, với Boot executable WAR |
| Deploy servlet container ngoài | Không theo mô hình WAR truyền thống | Có thể, khi thỏa điều kiện Servlet/initializer/dependency |
| Có nên chọn mặc định cho microservice độc lập? | Thường phù hợp và đơn giản | Dùng khi có nhu cầu WAR/Servlet container ngoài |

**Không có kiểu "WAR tốt hơn JAR" về mọi mặt.** Chọn loại archive theo mô hình vận hành; plugin nền quyết định cấu trúc và tác vụ, còn Spring Boot plugin tạo khả năng thực thi tương ứng.

## 9. Lỗi thường gặp và cách tự chẩn đoán

| Hiện tượng | Nguyên nhân hay gặp | Cách xác minh hoặc xử lý |
| --- | --- | --- |
| `Task 'bootJar' not found` | Spring Boot plugin chưa được áp dụng hoặc thiếu `java`/plugin nền tương ứng | Xem `plugins`, `apply false`, đúng module, chạy `tasks --all` |
| `Task 'bootWar' not found` | Chỉ áp dụng `java`, chưa áp dụng Gradle `war` | Thêm `id 'war'` vào module ứng dụng, chạy lại Gradle import |
| `bootJar` không tìm được main class | Dự án chưa có `main(String[])` hoặc task đang chạy ở module thư viện | Thêm lớp chính, xem package/mainClass, chọn đúng project |
| Có `bootWar` nhưng không deploy được | Thiếu `SpringBootServletInitializer`, container ngoài không tương thích, sai classpath | Kiểm tra `configure`, WAR layout, server logs và Servlet compatibility |
| `NoClassDefFoundError` khi chạy ứng dụng | Dependency thiếu ở runtime hoặc bị đặt nhầm cấu hình | Xem `runtimeClasspath` và `jar tf` của archive |
| `providedRuntime` không tồn tại | Chưa áp dụng Gradle `war` plugin | Kiểm tra `plugins` và cấu hình module |
| WAR thiếu embedded Tomcat khi `java -jar` | Chuyển dependency/đóng gói sai hoặc task WAR không phải của Boot | Xem `WEB-INF/lib-provided`, chọn đúng `bootWar` |
| Có thêm `-plain.jar` / `-plain.war` | Task đóng gói thường và Boot cùng được chạy | Xem task tạo file và classifier; chọn artifact Boot khi cần `java -jar` |
| Plugin bị báo không tìm thấy | Sai plugin version/repository, lỗi mạng, Gradle Wrapper không tương thích | Kiểm tra `settings.gradle` plugin repositories, plugin portal, wrapper và lỗi resolution |
| Starter không khai báo version gây lỗi | Chưa có cơ chế BOM/dependency management phù hợp | Áp dụng `io.spring.dependency-management` hoặc platform BOM đúng phiên bản |
| `bootRun` chạy được nhưng WAR fail | Chế độ nhúng và container ngoài có khác biệt | Thử deploy WAR thật, đọc log servlet container và context path |
| Build pass nhưng endpoint 404 | Chưa có controller, sai đường dẫn/port/context path | Xem lớp `@RestController`, `@GetMapping` và URL ứng dụng thực |
| WAR deployed nhưng class xung đột | Embedded servlet container còn nằm trong `WEB-INF/lib` hoặc server/API không phù hợp | Xem `providedRuntime` và nội dung WAR |
| `compileOnly` dùng thay `providedRuntime` làm test fail | Thư viện không thuộc test runtime classpath | Dùng `providedRuntime` đúng trường hợp servlet container |
| Cùng áp dụng Boot cho module library và application | Thư viện không có `main` nhưng có task executable archive | Chỉ áp dụng Boot plugin tại module ứng dụng; giữ `java-library` ở module thư viện |

### Ví dụ kiểm tra thứ tự lỗi

Nếu `./gradlew bootWar` báo không tìm thấy task, **trước hết** xác nhận plugin `war` đã áp dụng và bạn đang đứng ở module đúng. Nếu task có nhưng build lỗi Java, đọc lỗi biên dịch/phiên bản JDK. Nếu build tạo WAR nhưng chạy `java -jar` lỗi, kiểm tra bạn có dùng đúng executable WAR không và tệp `WEB-INF/lib-provided` có phù hợp không. Nếu chạy bằng `java -jar` thành công nhưng Tomcat ngoài lỗi, chuyển sang điều tra `SpringBootServletInitializer`, Servlet API, context path và cấu hình container.

Cách phân lớp này tránh sửa plugin version vô cớ khi nguyên nhân nằm ở mã Java hoặc môi trường triển khai.

## 10. Thực hành: chứng minh tác động của từng plugin

### Bài 1 – Java JAR

Tạo một project Groovy DSL với `id 'java'`, Spring Boot plugin và cơ chế BOM. Thêm hai lớp Java của phần 4 và kiểm thử `contextLoads`. Thực hiện:

1. Chạy `./gradlew tasks --all`, ghi lại `bootRun`, `bootJar`, `jar` và `test`.
2. Chạy `./gradlew test`, giải thích test được Gradle Java plugin tạo và dùng dependency test.
3. Chạy `./gradlew bootJar`, mở `build/libs` và dùng `jar tf` tìm `BOOT-INF/classes`/`BOOT-INF/lib`.
4. Khởi động bằng `java -jar` và gọi `/hello`. Nếu thấy `-plain.jar`, so cấu trúc file đó với Boot executable JAR.

### Bài 2 – WAR và Servlet container

Trên bản sao/nhánh riêng của dự án, thay `java` bằng `war`, thêm `providedRuntime` cho servlet container, giữ lớp chính kế thừa `SpringBootServletInitializer`.

1. Chạy `./gradlew tasks --all`, ghi `bootWar`, `war`, và có hay không `bootJar`.
2. Chạy `./gradlew bootWar`, xem `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` của đúng WAR.
3. Chạy `java -jar build/libs/demo-0.0.1-SNAPSHOT.war` (đúng tên sản phẩm bạn tạo), gọi `/hello` trong chế độ nhúng.
4. Nếu có một servlet container **tương thích**, deploy WAR để gọi endpoint qua context path do container chọn. Đối chiếu sự khác nhau giữa hai cách chạy.
5. Trả lời: tại sao `id 'war'` đã có năng lực Java, tại sao cần initializer, vì sao `providedRuntime` khác `compileOnly`, và vì sao task `war` không tương đương `bootWar`?

### Bài 3 – Giải thích cấu hình

Không cần chạy thêm code, hãy trả lời từ file build và báo cáo task:

- Nếu chỉ có `id 'org.springframework.boot' version '3.3.13' apply false`, có thể mặc định dùng `bootJar` trong module đó không? Vì sao?
- Điều gì thay đổi khi `id 'war'` được áp dụng vào một project Java Spring Boot?
- `io.spring.dependency-management` có nhiệm vụ đóng gói executable JAR không? Nếu bỏ nó, phải quản lý version dependency bằng cách nào?
- Vì sao thấy `-plain.jar` không đủ kết luận build sai?
- Khi sản phẩm chạy trong container ngoài, những yêu cầu nào phải kiểm tra ngoài việc `bootWar` thành công?

**Tiêu chí đạt:** bạn nêu được chính xác **plugin nào tạo task nào**, chạy được ít nhất một bộ bài tập Java/JAR và một bản WAR trong môi trường phù hợp, kiểm tra được nội dung archive thật, đồng thời giải thích được sự khác nhau giữa executable packaging và WAR deployment.

## Tài liệu chính thức

- Spring Boot 3.3 Gradle Plugin – Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot Gradle Plugin – Reacting to Other Plugins: https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html
- Spring Boot Gradle Plugin – Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot Gradle Plugin – Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot – Traditional Deployment: https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Gradle – Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle – War Plugin: https://docs.gradle.org/current/userguide/war_plugin.html

**Ghi nhớ:** `org.springframework.boot` bổ sung tác vụ Spring Boot khi thấy plugin nền tương ứng; `java` và `war` quyết định mô hình Java/Servlet; `io.spring.dependency-management` hoặc native BOM quyết định quản lý phiên bản dependency. Hãy kiểm tra task, archive và cách chạy của chính dự án để xác nhận việc áp dụng plugin có đúng mục tiêu.
