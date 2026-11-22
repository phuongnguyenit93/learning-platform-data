# Tạo JAR thực thi bằng Gradle bootJar

## 1. Mục tiêu của bài

Khi xây dựng ứng dụng Spring Boot bằng Gradle, bạn thường muốn nhận được **một tệp JAR có thể khởi động bằng lệnh `java -jar`** trên máy không cần cài Gradle. Task `bootJar` của Spring Boot Gradle Plugin phục vụ mục tiêu đó: nó đóng gói classes, resources, runtime dependencies và Spring Boot loader vào một executable archive.

Bài học hướng dẫn từ cấu hình tới kiểm chứng, tập trung vào các câu hỏi:

- `bootJar` xuất hiện khi nào, thuộc plugin nào và khác task Gradle `jar` ở đâu?
- Task lấy source output và dependency classpath nào để tạo executable JAR?
- Vì sao `./gradlew bootJar`, `./gradlew assemble`, `./gradlew build` và `./gradlew bootRun` có tác dụng khác nhau?
- Tạo một project Spring Boot chạy được bằng **Groovy DSL** hoặc **Kotlin DSL**, thực thi `bootJar` và chạy sản phẩm như thế nào?
- Nhận diện đúng file trong `build/libs`, cấu trúc `BOOT-INF`, manifest, main class và layered JAR ra sao?
- Cấu hình tên JAR, classifier, main class, phụ thuộc runtime và launch script như thế nào mà không làm sai sản phẩm?
- Chẩn đoán những lỗi thường gặp, đặc biệt khi dự án nhiều module hoặc CI/CD đang lấy nhầm plain JAR.

**Phạm vi:** Java 17 và Spring Boot Gradle Plugin 3.3.13 làm ví dụ nhất quán; đây là phiên bản minh họa, **không phải khẳng định bản Spring Boot mới nhất**. Với dự án thật, sử dụng version và Gradle wrapper đã được nhóm xác nhận, đồng thời đọc tài liệu tương ứng phiên bản đó.

## 2. `bootJar` là gì, và vì sao cần nó?

Java JAR thông thường có thể chứa các file `.class` và `META-INF/MANIFEST.MF`; nhưng một JAR chứa application classes **không mặc nhiên chứa toàn bộ runtime libraries**. Spring Boot web app cần nhiều thư viện như Spring Framework, logging, JSON mapper và embedded web server. Nếu JAR chỉ có mã của project, `java -jar` rất dễ thất bại vì thiếu dependency hoặc không có main manifest phù hợp.

`bootJar` là task có kiểu `org.springframework.boot.gradle.tasks.bundling.BootJar`, do **Spring Boot Gradle Plugin** cung cấp. Khi ứng dụng có Spring Boot plugin và Java plugin, task này mặc định tạo một executable JAR chứa:

- Classes đã biên dịch từ main source set.
- Resources của main source set.
- Các runtime JAR dependencies cần thiết.
- Spring Boot loader để nạp nested JAR dependencies và gọi main class ứng dụng.
- Metadata trong manifest; theo cấu hình Spring Boot 3.3, archive thường có thông tin về application main class và layer.

`bootJar` không phải task Java `jar` đổi tên: nó tạo **kiểu archive có cấu trúc dành cho Spring Boot**. Khác với nhiều “shaded JAR” là giải nén và trộn classes của thư viện thành một flat namespace, Boot executable JAR thường **giữ thư viện ở dạng nested JAR** bên trong `BOOT-INF/lib`.

### 2.1. Điều kiện để Gradle tạo task `bootJar`

Spring Boot Gradle Plugin phản ứng với Java plugin. Với cấu hình:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}
~~~

Gradle cung cấp source set `main`, task compile/resource và task `jar`; Spring Boot plugin tạo thêm `bootJar` và nối nó vào vòng đời `assemble`. Nếu chỉ apply Spring Boot plugin mà không có plugin Java/JVM thích hợp, **không được tự suy ra** rằng project có sẵn `bootJar`.

Không nhất thiết phải có web starter: executable JAR cũng có thể là CLI, batch application hoặc consumer chạy nền, miễn ứng dụng có main class và dependencies phù hợp.

### 2.2. Khác biệt với Maven `repackage`

Maven thường dùng goal `spring-boot:repackage` xử lý **JAR/WAR cơ sở đã được plugin đóng gói chuẩn tạo ra** trong lifecycle `package`. Gradle `bootJar` là task tạo executable archive trực tiếp từ classes/resources/runtime classpath theo task graph Gradle. Không có quy trình mặc định “Maven repackage rồi Gradle bootJar”; dự án chọn build tool được repo và CI sử dụng.

## 3. `bootJar` trong Gradle task graph

Hãy phân biệt task tạo file với lifecycle task và task chạy ứng dụng.

~~~text
Java plugin + Spring Boot Gradle Plugin
                  |
                  +--> compileJava / processResources
                  |       |
                  |       +--> classes + runtimeClasspath
                  |                    |
                  |                    +--> bootJar
                  |
                  +--> jar           (plain JAR)
                  |
                  +--> assemble     (phụ thuộc output của các archive tasks)
                  |       |
                  |       +--> bootJar
                  |
                  +--> check        (các kiểm tra; thường gồm test)
                          |
build ---------------------+---- assemble
~~~

Sơ đồ chỉ trình bày quan hệ quan trọng. Gradle có thể lên lịch additional tasks tùy plugin và configuration; thứ tự chính xác phải được kiểm tra qua task graph.

| Lệnh | Kết quả theo cấu hình chuẩn |
| --- | --- |
| `./gradlew bootJar` | Tạo executable Boot JAR và chạy các task là dependency cần thiết cho nó; **không mặc nhiên chạy JUnit tests** |
| `./gradlew jar` | Tạo plain JAR qua Java plugin; không tự thay thế `bootJar` |
| `./gradlew assemble` | Xây các archive gắn vào assemble, trong đó có `bootJar`; có thể có cả plain JAR |
| `./gradlew build` | Theo Java lifecycle, phụ thuộc `assemble` và `check`, nên thường đóng gói và chạy tests |
| `./gradlew test` | Chạy test task; không tự tạo executable JAR |
| `./gradlew bootRun` | Chạy ứng dụng qua Gradle với main runtime classpath; không phải bước phát hành archive |
| `./gradlew bootBuildImage` | Xây OCI container image theo Cloud Native Buildpacks; đây là task khác `bootJar` |

**Quan trọng khi QA:** `bootJar` thành công không phải bằng chứng các test đã pass. Trong CI, nếu điều kiện phát hành yêu cầu tests, hãy chạy `build`/`check` hoặc workflow được cấu hình để kiểm tra trước khi publish.

### 3.1. Xem task graph, không chỉ đoán từ tên

~~~bash
./gradlew tasks --all
./gradlew bootJar --dry-run
./gradlew assemble --dry-run
./gradlew build --dry-run
~~~

`--dry-run` chỉ cho thấy task được lên lịch; **nó không tạo JAR mới và không thực thi test actions**. Sau khi xem graph, cần chạy build thật để xác nhận output. Tùy Gradle version/build cache, task có thể hiển thị `UP-TO-DATE` hoặc `FROM-CACHE`; trạng thái đó khác với việc một task action vừa chạy.

## 4. Chuẩn bị project Spring Boot có thể chạy được

Chúng ta tạo một project `bootjar-demo` nhỏ với endpoint `GET /artifact` trả chuỗi `bootjar-ready`. Cùng một mã Java sẽ dùng được với Gradle Groovy DSL hoặc Kotlin DSL; **chỉ chọn một dạng DSL cho một bản project**.

Cấu trúc:

~~~text
bootjar-demo/
├── settings.gradle            # nếu dùng Groovy DSL
├── build.gradle               # nếu dùng Groovy DSL
│   hoặc settings.gradle.kts   # nếu dùng Kotlin DSL
│   hoặc build.gradle.kts      # nếu dùng Kotlin DSL
├── src/
│   ├── main/
│   │   ├── java/com/example/packaging/
│   │   │   ├── PackagingApplication.java
│   │   │   └── ArtifactController.java
│   │   └── resources/         # có thể trống
│   └── test/
│       └── java/com/example/packaging/
│           └── ArtifactControllerTest.java
└── build/                     # Gradle tự sinh khi build
~~~

Nếu được tạo bởi Spring Initializr, project có thể còn file `gradlew`, `gradlew.bat`, `gradle/wrapper/...` và các cấu hình khác. **Wrapper không tự được sinh chỉ vì bạn tạo `build.gradle`**. Chỉ dùng `./gradlew` khi wrapper tồn tại; nếu chưa có, tạo wrapper theo quy trình nhóm hoặc dùng `gradle` cài sẵn với version tương thích.

## 5. Cấu hình hoàn chỉnh bằng Groovy DSL

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'bootjar-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

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

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích:

- `java` tạo Java source sets và các task `compileJava`, `processResources`, `classes`, `jar`, `test`, `assemble` và `build`.
- `org.springframework.boot` bổ sung các task liên quan Spring Boot, trong đó có `bootJar` và `bootRun` khi đã có Java plugin.
- `io.spring.dependency-management` giúp Spring Boot tự import BOM phiên bản tương ứng, nhờ đó có thể bỏ `<version>` tương đương trên các starter được BOM quản lý.
- `group` và `version` cùng `rootProject.name` góp phần hình thành archive base name/version; với ví dụ này default executable artifact thường là `bootjar-demo-0.1.0.jar`.
- Java toolchain yêu cầu Java 17 cho tasks tương ứng; JDK phù hợp phải có sẵn hoặc có cơ chế provision được Gradle cấu hình.
- `mavenCentral()` là nơi Gradle giải quyết application dependencies, không tự thay thế configuration của plugin repositories.
- `testImplementation` chỉ dành cho test classpath; không cần đưa Spring Boot Test vào production executable JAR.
- `useJUnitPlatform()` cho Gradle biết phải chạy tests trên JUnit Platform.

**Đây là file build có thể dùng trực tiếp**, không phải một khối fragment. Nó yêu cầu Gradle version/JDK/plugin repositories tương thích và khả năng tải dependencies. Nếu môi trường offline hoặc corporate mirror không truy cập Maven Central, build cần chỉnh repositories theo chính sách nhưng phần cú pháp vẫn hợp lệ.

## 6. Cấu hình Kotlin DSL tương đương

Nếu project dùng Kotlin DSL thì **thay** hai file Groovy bằng cặp dưới đây. Không chồng cả hai build files rồi mặc định chúng có tác dụng cộng dồn.

Tệp `settings.gradle.kts`:

~~~kotlin
rootProject.name = "bootjar-demo"
~~~

Tệp `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Trong Kotlin DSL, `languageVersion` là Gradle property có thể cấu hình bằng `set`; `tasks.named<Test>("test")` làm rõ kiểu task để truy cập `useJUnitPlatform()`. Dùng `build.gradle.kts` không có nghĩa Java code bắt buộc phải viết bằng Kotlin. **Cùng source Java ở mục kế tiếp hoạt động với cả hai DSL.**

## 7. Java source và test để kiểm tra file thực thi

### 7.1. Main class duy nhất của ứng dụng

Tạo `src/main/java/com/example/packaging/PackagingApplication.java`:

~~~java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
~~~

Vì dự án này chỉ có **một** class `public static void main(String[])` trong main output, plugin thường phát hiện main class tự động. Spring Boot chạy application context với component scan từ package `com.example.packaging`.

### 7.2. Endpoint kiểm chứng kết quả chạy

Tạo `src/main/java/com/example/packaging/ArtifactController.java`:

~~~java
package com.example.packaging;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArtifactController {

    @GetMapping("/artifact")
    public String artifact() {
        return "bootjar-ready";
    }
}
~~~

Source này cần `spring-boot-starter-web` để có Spring MVC annotations và embedded server. Không có dependency web thì `GetMapping`/`RestController` không nằm trên compile classpath.

### 7.3. Test JUnit độc lập với task `bootJar`

Tạo `src/test/java/com/example/packaging/ArtifactControllerTest.java`:

~~~java
package com.example.packaging;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ArtifactControllerTest {

    @Test
    void returnsExpectedText() {
        ArtifactController controller = new ArtifactController();
        assertEquals("bootjar-ready", controller.artifact());
    }
}
~~~

Test này không cần Spring context vì chỉ gọi method Java thuần. Nó minh họa chức năng của task `test`: JUnit chạy assertion và trả status thành công/thất bại.

Task `bootJar` không cần thực thi `ArtifactControllerTest` để tạo executable JAR. Test code nằm ở test output và thường **không được đóng** vào release JAR. Chạy tests bằng `./gradlew test` hoặc `./gradlew build` theo policy build.

## 8. Chạy `bootJar` từ đầu tới cuối

Mở terminal tại project root, nơi có build script và settings file đúng DSL.

### 8.1. Kiểm tra môi trường

~~~bash
java -version
./gradlew --version
./gradlew tasks --all
~~~

Dùng `.\gradlew.bat` trên Windows PowerShell, hoặc dùng lệnh `gradle` khi không có wrapper nhưng đã cài Gradle tương thích. `./gradlew --version` cho biết Gradle distribution và JVM đang chạy Gradle; toolchain dùng compile có thể khác JVM daemon. Nếu cấu hình Java toolchain 17 mà không tìm được JDK 17 phù hợp, hãy kiểm tra `./gradlew javaToolchains`.

Tìm task `bootJar` ở module ứng dụng trong output `tasks --all`. Nếu không có, kiểm tra Java plugin và Spring Boot plugin đã áp dụng cho đúng project chưa.

### 8.2. Đóng gói JAR từ project sạch

~~~bash
./gradlew clean bootJar
~~~

Chuỗi thực hiện về mặt khái niệm:

~~~text
clean
   ↓
compileJava + processResources
   ↓
classes
   ↓
resolve runtimeClasspath
   ↓
bootJar
   ↓
build/libs/bootjar-demo-0.1.0.jar
~~~

Gradle thực thi task dựa trên dependency graph và up-to-date checks; thứ tự chi tiết có thể thay đổi theo cấu hình. `clean` thường xóa thư mục build, giúp tránh nhầm file cũ.

Lệnh `./gradlew clean bootJar` **không yêu cầu task `test`**, nên một build có thể tạo executable JAR dù unit test chưa chạy. Để kiểm tra test trước khi phát hành:

~~~bash
./gradlew clean build
~~~

Theo Java plugin lifecycle mặc định, `build` thường yêu cầu cả `assemble` và `check`; `check` thường phụ thuộc `test`. Nếu tổ chức tùy biến hoặc disable test task, cần xem task graph và log để biết điều kiện thực tế.

### 8.3. Chạy file kết quả

Trong cấu hình minh họa chưa đổi archive name/classifier, file thường ở:

~~~text
build/libs/bootjar-demo-0.1.0.jar
~~~

Chạy:

~~~bash
java -jar build/libs/bootjar-demo-0.1.0.jar --server.port=18080
~~~

Trong terminal khác:

~~~bash
curl -fsS http://localhost:18080/artifact
~~~

Body HTTP dự kiến là:

~~~text
bootjar-ready
~~~

Đây là **body** từ controller, không phải toàn bộ log của Spring Boot hoặc Gradle. `curl` có thể không hiển thị newline do controller trả một chuỗi không có newline. Nếu cổng 18080 đã dùng, chọn cổng khác và điều chỉnh request. Dừng ứng dụng bằng Ctrl+C.

Máy chạy file JAR cần **Java runtime tương thích** (với ví dụ là Java 17+ phù hợp với dependencies), network/OS/resources và application configuration cần thiết. Máy đó không cần cài Gradle để chạy archive đã được build.

### 8.4. Những gì có thể kết luận từ kết quả?

- `bootJar` thành công: plugin đã tạo một archive theo cấu hình task.
- `jar tf` thấy cấu trúc Boot và runtime dependencies: chứng cứ về layout đóng gói.
- `java -jar` startup thành công: xác nhận JVM đọc được launcher và application main class trong môi trường hiện tại.
- HTTP `/artifact` trả đúng body: xác nhận đường ứng dụng tối thiểu hoạt động.
- `./gradlew test` pass: chứng cứ bài test đã khai báo chạy thành công.

**Không nên suy một kết luận thay cho tất cả kết luận còn lại.** Một archive có thể tạo thành công nhưng runtime khởi động thất bại do environment/config; một test có thể pass nhưng artifact được publish lại là plain JAR.

## 9. Kiểm tra nội dung executable JAR

### 9.1. Vì sao `BOOT-INF` quan trọng?

Với executable Spring Boot JAR trong 3.3, cấu trúc tiêu biểu:

~~~text
META-INF/
  MANIFEST.MF
BOOT-INF/
  classes/
    com/example/packaging/PackagingApplication.class
    com/example/packaging/ArtifactController.class
  lib/
    spring-boot-3.3.13.jar
    spring-context-....jar
    ... các runtime dependencies khác ...
  layers.idx                  # metadata layers theo cấu hình chuẩn
org/springframework/boot/loader/
  launch/JarLauncher.class
  ... Boot loader classes ...
~~~

Đây là sơ đồ rút gọn; tên/số lượng JAR trong `BOOT-INF/lib` phụ thuộc dependency graph thực tế. Nếu ứng dụng dùng custom Boot loader hoặc thay đổi layer configuration, archive có thể có chi tiết khác.

**Classes của ứng dụng** nằm ở `BOOT-INF/classes`, còn **nested JAR dependencies** nằm ở `BOOT-INF/lib`. Boot loader biết cách tạo classpath lúc runtime để gọi main class; không cần giải nén tất cả JAR con theo cách thông thường trước khi khởi động.

### 9.2. Dùng JDK `jar` để xem các entry

~~~bash
jar tf build/libs/bootjar-demo-0.1.0.jar
~~~

Trong danh sách dài, tìm:

~~~text
BOOT-INF/classes/com/example/packaging/PackagingApplication.class
BOOT-INF/classes/com/example/packaging/ArtifactController.class
BOOT-INF/lib/
org/springframework/boot/loader/launch/JarLauncher.class
META-INF/MANIFEST.MF
~~~

Nếu JAR chỉ có vài class của project ở package gốc và không có `BOOT-INF/lib`, hãy kiểm tra bạn có đang mở **plain JAR** thay vì Boot executable archive không. Không chỉ nhìn số byte hay đuôi file để phân biệt.

Để xem manifest trên Linux/macOS với `unzip` có sẵn:

~~~bash
unzip -p build/libs/bootjar-demo-0.1.0.jar META-INF/MANIFEST.MF
~~~

Nếu máy không có `unzip`, có thể giải nén vào **một thư mục tạm** bằng công cụ ZIP/JAR rồi mở `META-INF/MANIFEST.MF`; đừng chạy `jar xf` ngay trong project root nếu không muốn làm rơi nhiều file không theo dõi vào workspace.

Manifest của executable Spring Boot 3.3 JAR thông thường chứa những thuộc tính tương tự:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.packaging.PackagingApplication
~~~

`Main-Class` là launcher của Spring Boot; `Start-Class` là class có main method của ứng dụng. Tên Boot launcher ở **các phiên bản khác** có thể thay đổi; ví dụ `org.springframework.boot.loader.JarLauncher` thuộc các dòng cũ, không nên sao chép cứng cho 3.3. Nếu bạn tùy chỉnh launcher, cũng phải đối chiếu theo lựa chọn đã cấu hình.

### 9.3. `jar` không phải `bootJar`

Với Java plugin và Spring Boot 3.3, Gradle thường có hai task:

- `jar` tạo **plain JAR**, chứa application classes/resources theo chuẩn Java plugin.
- `bootJar` tạo **executable Spring Boot JAR**, chứa Boot loader và các runtime dependencies theo layout Boot.

Để cho phép đồng thời tồn tại hai archive, Spring Boot plugin đặt `plain` làm **convention classifier** của task `jar`. Sau khi `./gradlew assemble` hoặc `./gradlew build`, có thể thấy:

~~~text
build/libs/
├── bootjar-demo-0.1.0.jar           # bootJar: executable
└── bootjar-demo-0.1.0-plain.jar     # jar: plain
~~~

**Lưu ý khi kiểm tra:** gọi riêng `./gradlew bootJar` không có nghĩa chắc chắn Gradle vừa tạo `-plain.jar`; plain file có thể đến từ một lần build trước hoặc từ task graph tùy chỉnh. Muốn biết task nào chạy trong lượt này, đọc build log và task graph.

Một plain JAR có thể là sản phẩm đúng khi module là thư viện dùng lại, nhưng thông thường nó **không phải** tệp chạy được bằng `java -jar` với đủ Spring Boot dependencies. CI/CD không nên lấy file đầu tiên khớp `build/libs/*.jar` rồi giả định đó là executable archive.

## 10. Tùy chỉnh `bootJar` bằng Groovy DSL và Kotlin DSL

Các đoạn ở mục này là **fragments bổ sung** vào `build.gradle` hoặc `build.gradle.kts`, không phải build scripts độc lập. Với Kotlin DSL cần import kiểu task để gọi các property đặc thù. Nếu áp dụng nhiều fragment cùng thay `archiveFileName` hoặc `mainClass`, chỉ giữ một chính sách đặt tên/entrypoint có hiệu lực.

### 10.1. Đặt tên file JAR tường minh

**Groovy — bổ sung vào `build.gradle`:**

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'app-service.jar'
}
~~~

**Kotlin — thêm import ở đầu `build.gradle.kts`:**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("app-service.jar")
}
~~~

Dòng `archiveFileName` quyết định output filename của task này, không đổi group/version của project trong dependency metadata. Với fragment này, chạy:

~~~bash
./gradlew bootJar
java -jar build/libs/app-service.jar
~~~

Không tiếp tục hardcode `build/libs/bootjar-demo-0.1.0.jar` khi task đã đổi file name. Trong CI, ưu tiên tham chiếu task output có chủ đích hoặc đường dẫn đã được kiểm soát thay vì glob mơ hồ.

### 10.2. Đặt main class khi auto-detection không đủ

Với ví dụ có một entrypoint, `bootJar` thường tự tìm `PackagingApplication`. Trong project có nhiều `public static void main(String[])`, plugin có thể cần cấu hình tường minh.

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.packaging.PackagingApplication'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    mainClass.set("com.example.packaging.PackagingApplication")
}
~~~

Điều này cấu hình application main class mà executable JAR sẽ gọi. Tên phải đúng package và tên Java class thực tế; không dùng đường dẫn file `src/main/java/...` làm mainClass.

Spring Boot Gradle Plugin cũng hỗ trợ cấu hình main class ở extension cấp project:

**Groovy:**

~~~groovy
springBoot {
    mainClass = 'com.example.packaging.PackagingApplication'
}
~~~

**Kotlin:**

~~~kotlin
springBoot {
    mainClass.set("com.example.packaging.PackagingApplication")
}
~~~

Đây là **lựa chọn thay thế**, không cần dùng cả hai nơi với giá trị khác nhau. Khi có Gradle Application plugin, còn có `application.mainClass`; quan trọng là tránh nhiều nguồn cấu hình mâu thuẫn.

### 10.3. Đổi classifier của executable JAR

Đôi khi team muốn plain JAR giữ tên mặc định và Boot JAR có hậu tố `-boot.jar`. Nếu có nhu cầu publish cả hai, phải đảm bảo **tên output khác nhau**.

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}
tasks.named('jar') {
    archiveClassifier = ''
}
~~~

**Kotlin:**

~~~kotlin
import org.gradle.jvm.tasks.Jar

tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("boot")
}
tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}
~~~

Với project/version ở ví dụ và không chỉnh archiveFileName, output có thể là:

~~~text
bootjar-demo-0.1.0.jar           # plain jar
bootjar-demo-0.1.0-boot.jar      # bootJar executable
~~~

Lúc này **file không classifier không còn là executable**. Đây là một lý do quan trọng để phân biệt artifact theo task đã tạo, không chỉ theo tên.

Nếu trước đó đã đặt `archiveFileName='app-service.jar'`, tên tùy chỉnh có thể ghi đè cách ghép classifier; hãy chọn một chính sách rõ ràng thay vì sao chép cả hai fragment cùng lúc.

### 10.4. Tắt task plain JAR khi thực sự không cần

**Groovy:**

~~~groovy
tasks.named('jar') {
    enabled = false
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<org.gradle.jvm.tasks.Jar>("jar") {
    enabled = false
}
~~~

Tùy chọn này chỉ disable task `jar`; không thay đổi định nghĩa `bootJar`. Tuy nhiên **không nên disable `jar` một cách mặc định** khi module còn phải publish plain library artifact hoặc quy trình native image cần task `jar`. Tài liệu Spring Boot 3.3 đặc biệt lưu ý không tắt task `jar` khi tạo native images.

Khi cần cả plain JAR và executable JAR, giữ cả hai task và quản lý classifier/publishing minh bạch.

### 10.5. Tùy chỉnh thư mục output

`BootJar` kế thừa khả năng archive task của Gradle, trong đó có `destinationDirectory`. Ví dụ (fragment bổ sung):

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    destinationDirectory = layout.buildDirectory.dir('release-artifacts')
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    destinationDirectory.set(layout.buildDirectory.dir("release-artifacts"))
}
~~~

Sau khi thay output directory, không tìm file ở `build/libs` theo thói quen nữa; file nằm ở `build/release-artifacts` trong cấu hình minh họa. Chú ý task downstream, CI upload, image build hoặc publication cần tham chiếu output mới. Tránh đặt output ngay trong source tree.

## 11. Dependency classpath của `bootJar`

### 11.1. `bootJar` lấy những gì từ project?

Mặc định, `bootJar` dùng **runtime classpath của main source set**. Hiểu đơn giản:

~~~text
main classes/resources
       +
runtime libraries trên main.runtimeClasspath
       +
Spring Boot loader
       =
executable Boot JAR
~~~

Runtime classpath chịu ảnh hưởng của `implementation`, `runtimeOnly`, project dependencies, Gradle resolution và một số configuration đặc thù Spring Boot. Không có quy tắc “mọi dependency khai báo trong build.gradle đều vào JAR”.

| Configuration | Thường được đưa vào executable Boot JAR? | Giải thích |
| --- | --- | --- |
| `implementation` | Có, theo resolved runtime graph | Thư viện main compile/runtime |
| `runtimeOnly` | Có | Thư viện cần lúc chạy |
| `compileOnly` | Không theo mặc định | Chỉ dùng để compile; runtime kỳ vọng nguồn khác hoặc không cần |
| `testImplementation` | Không | Dành cho test source set |
| `testRuntimeOnly` | Không | Dành cho test runtime |
| `developmentOnly` | Mặc định loại khỏi Boot archive | Dành cho môi trường development theo Spring Boot plugin |

Nếu ứng dụng cần JDBC driver runtime nhưng đặt nhầm dependency ở `testImplementation`, `./gradlew test` có thể pass trong khi executable JAR không tìm thấy driver. Đưa dependency cần thiết vào đúng runtime scope; không copy tay JAR bên ngoài vào archive để che dấu lỗi resolution.

### 11.2. Ví dụ thêm thư viện runtimeOnly

**Groovy:**

~~~groovy
dependencies {
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

**Kotlin:**

~~~kotlin
dependencies {
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Đây là fragment nếu ứng dụng **thực sự** dùng PostgreSQL; không cần cho endpoint `/artifact` ở ví dụ cơ bản. Với Spring Boot BOM, version tương thích của driver thường được quản lý. Muốn chắc chắn thư viện nằm trong production runtime graph, dùng `dependencies --configuration runtimeClasspath` hoặc `dependencyInsight`, rồi kiểm tra `BOOT-INF/lib` trong file JAR.

### 11.3. Phụ thuộc developmentOnly

Một số dự án có:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

`spring-boot-devtools` hỗ trợ phát triển; Spring Boot plugin mặc định loại những dependencies trong configuration `developmentOnly` khỏi executable archive. Nếu cần DevTools lúc `bootRun` thì cấu hình theo môi trường phát triển; **không đưa development-only libraries vào release JAR theo thói quen**.

Nếu cố tình muốn thay đổi classpath của task `bootJar`, Spring Boot Plugin cho phép cấu hình thêm classpath; nhưng đó là lựa chọn nâng cao, cần kiểm thử và review kỹ vì có thể khiến artifact mang thư viện không mong muốn. Không sửa classpath chỉ để tránh hiểu dependency scopes.

## 12. Layered JAR: ý nghĩa và giới hạn

Spring Boot 3.3 hỗ trợ layered executable JAR để các lớp có mức độ thay đổi khác nhau được xử lý/cached hiệu quả hơn khi xây container image. **Layered JAR vẫn là một executable JAR**: classes và nested libraries vẫn dùng bố cục `BOOT-INF/classes`, `BOOT-INF/lib`, chỉ thêm metadata mô tả layers.

Các layer mặc định thường gồm:

| Layer | Nội dung điển hình | Tần suất thay đổi tương đối |
| --- | --- | --- |
| `dependencies` | Non-project dependencies không có SNAPSHOT version | Thường ít đổi |
| `spring-boot-loader` | Spring Boot loader classes | Ít đổi theo release |
| `snapshot-dependencies` | Non-project SNAPSHOT dependencies | Có thể đổi thường xuyên |
| `application` | Classes, resources và project dependencies | Đổi thường xuyên khi phát triển |

Thông tin layer lưu trong `BOOT-INF/layers.idx` theo cấu hình chuẩn. **Layer không phải container image tự động được tạo**; để tạo OCI image có task/ công cụ khác, ví dụ `bootBuildImage` hoặc Dockerfile phù hợp.

Trong Spring Boot 3.3, layered JAR có thể bao gồm `spring-boot-jarmode-tools` để hỗ trợ thao tác với layer; cần tra đúng tài liệu vì tên/tham số tools giữa các dòng Boot có thay đổi.

### 12.1. Tắt layer metadata khi thật sự có yêu cầu

**Groovy fragment:**

~~~groovy
tasks.named('bootJar') {
    layered {
        enabled = false
    }
}
~~~

**Kotlin fragment:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(false)
    }
}
~~~

Tùy chọn này thay đổi tổ chức metadata layer; nó không có nghĩa bỏ runtime dependencies hoặc biến Boot JAR thành plain JAR. Với Spring Boot 3.3, việc disable layering **không mặc nhiên đồng nghĩa loại bỏ jarmode tools**; nếu phải bỏ tools do chính sách artifact, cấu hình riêng qua `includeTools` theo đúng phiên bản.

Không tắt layers chỉ vì không hiểu `layers.idx`; nếu tổ chức sử dụng container caching, việc tắt có thể làm mất lợi ích.

### 12.2. Khi nào cần tùy chỉnh layers?

Các trường hợp nâng cao:

- Ứng dụng gồm nhiều project dependencies có chu kỳ thay đổi khác nhau.
- Container image build pipeline cần tách module/thư viện để tối ưu caching.
- Build logic của tổ chức định nghĩa lớp application/config/resources riêng.

Trước khi chỉnh custom layers, hiểu quy tắc `intoLayer`, `include`/`exclude` và `layerOrder`; thứ tự này có ý nghĩa đối với caching. Không tự di chuyển file tùy tiện trong `BOOT-INF` vì Boot loader có yêu cầu về layout archive.

## 13. JAR chạy bằng `java -jar` và JAR “fully executable” không phải một khái niệm

**Thông thường:** một executable Spring Boot JAR được tạo bởi `bootJar` chạy bằng:

~~~bash
java -jar build/libs/bootjar-demo-0.1.0.jar
~~~

**Fully executable JAR** là biến thể bổ sung **launch script ở đầu tệp** để có thể chạy trực tiếp như script trên một số hệ Unix/Linux:

~~~bash
./build/libs/bootjar-demo-0.1.0.jar
~~~

Để bật launch script theo Spring Boot 3.3:

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    launchScript()
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    launchScript()
}
~~~

Dòng `launchScript()` là **tùy chọn nâng cao**, không bắt buộc để `java -jar` hoạt động. Cấu hình fully executable có thể khiến một số công cụ ZIP/JAR không giải nén được như archive ZIP chuẩn; tài liệu Spring Boot nêu thí dụ `jar -xf` có thể hoạt động không như mong đợi khi có script ở đầu. Chỉ bật nếu môi trường triển khai thực sự cần chạy file trực tiếp như script/service.

Trong CI container hóa thông thường, dùng `java -jar` hoặc build image theo chính sách tổ chức thường ít gây bất ngờ hơn. Lưu ý quyền thực thi (chmod) và cơ chế shell chỉ có ý nghĩa trên hệ hỗ trợ tương ứng; đừng hướng dẫn Windows chạy trực tiếp Linux launch script.

## 14. Dự án nhiều module và nguyên tắc chọn nơi dùng `bootJar`

Ví dụ:

~~~text
workspace/
├── settings.gradle(.kts)
├── shared-model/
│   └── build.gradle(.kts)       # module thư viện
├── persistence/
│   └── build.gradle(.kts)       # module thư viện
└── api-service/
    └── build.gradle(.kts)       # Spring Boot application
~~~

Cách tổ chức thường gặp:

- `shared-model` và `persistence` dùng Gradle `java-library`, tạo **plain JAR** cho module khác tiêu thụ.
- `api-service` apply Spring Boot plugin và Java plugin, có main class, tạo **executable JAR** qua `:api-service:bootJar`.
- Root aggregator có thể quản lý plugin version/build conventions nhưng không nhất thiết apply Spring Boot plugin cho mọi subproject.
- Project dependency đưa thư viện của các subproject vào `api-service` runtime classpath khi được khai báo bằng Gradle `implementation(project(":shared-model"))` hoặc tương đương.

Gọi task đúng module:

~~~bash
./gradlew :api-service:bootJar
./gradlew :api-service:build
~~~

**Tên `api-service` chỉ là ví dụ**; chỉ chạy khi project thực tế có module này trong settings. Tên file output, package/classpath và source roots phụ thuộc module.

Nếu áp dụng Spring Boot plugin đại trà lên thư viện không có main class, task `bootJar` có thể báo lỗi không tìm được entrypoint hoặc tạo artifact không phù hợp để publish như một reusable library. Giữ ranh giới trách nhiệm giữa library và executable application.

## 15. Kiểm chứng task và artifact trong CI/CD

Một pipeline phát hành đáng tin cần phân biệt **build artifact**, **validation** và **publication**:

1. Xác nhận JDK/Gradle wrapper từ repo.
2. Chạy các bước validation theo policy (thường `./gradlew clean build`).
3. Kiểm tra `bootJar` có xuất hiện và thành công trong task graph.
4. Xác định **chính xác output của task `bootJar`**, không lấy bừa một file JAR trong `build/libs`.
5. Kiểm tra archive layout/manifest và khi phù hợp smoke-test startup.
6. Chỉ sau khi có artifact đã xác minh, mới publish vào artifact repository, image build hay deployment system theo quyền được cấp.

`bootJar` **không tự động upload file lên Maven repository, deploy tới server hoặc build Docker image**. Những bước đó cần Gradle publishing/task riêng, CI workflow hoặc nền tảng triển khai.

Một chuỗi lệnh local minh họa:

~~~bash
./gradlew clean build
jar tf build/libs/bootjar-demo-0.1.0.jar
java -jar build/libs/bootjar-demo-0.1.0.jar --server.port=18080
~~~

Lệnh thứ ba sẽ giữ process chạy (với ứng dụng web); vì thế smoke test HTTP cần thực hiện ở terminal/process khác và có dọn dẹp/timeout phù hợp. Đừng dùng script CI chạy lệnh thứ ba trực tiếp rồi mong pipeline tự đi tiếp nếu không có quản lý process.

Nếu công việc yêu cầu artifact checksum, SBOM, signing, vulnerability scanning hoặc provenance, phải bổ sung những kiểm tra đó theo quy trình tổ chức; một executable JAR chạy được không tự chứng minh dependency an toàn hay đã được duyệt để phát hành.

## 16. Chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra đúng |
| --- | --- | --- |
| `Task 'bootJar' not found` | Spring Boot plugin/Java plugin chưa apply tại module đang chạy, hoặc task path sai | Xem `plugins`, `./gradlew projects` và `tasks --all` trong đúng module |
| `Main class name has not been configured` hoặc lỗi không tìm thấy main | Không có `public static void main(String[])` trong main source set, hoặc có nhiều ứng viên | Kiểm tra source/package, cấu hình `mainClass` tường minh |
| `bootJar` ra file nhưng `java -jar` báo no main manifest | Có thể đang chạy plain JAR hoặc manifest/task sai | Xác định file output của `bootJar`, xem `META-INF/MANIFEST.MF` |
| `ClassNotFoundException` khi chạy archive | Thiếu runtime dependency, file sai hoặc classpath bị tùy chỉnh | Xem `runtimeClasspath`, `BOOT-INF/lib` và build log |
| Test pass, executable JAR thiếu JDBC driver | Driver chỉ nằm trong `testImplementation`/`compileOnly` | Kiểm tra `runtimeOnly` và Gradle dependency resolution |
| Có `-plain.jar` nên không biết file nào deploy | Cả `jar` và `bootJar` tồn tại, classifier khác | Xem task outputs/manifest; không chọn theo glob đầu tiên |
| `./gradlew bootJar` pass nhưng tests chưa chạy | Task packaging không mặc nhiên phụ thuộc task `test` | Chạy `build`/`test` và xem task graph |
| `./gradlew build` không có executable JAR mới | `bootJar` bị disabled, cấu hình `assemble` đã đổi hoặc module sai | `--dry-run`, task log, kiểm tra outputDirectory/cache |
| JAR có tên khác tutorial | Project name/version/classifier/archiveFileName bị đổi | Kiểm tra settings, archive task properties, `build/libs` |
| `bootJar` lỗi khi dependency không tải được | Offline, repository/mirror/proxy sai hoặc BOM version conflict | Kiểm tra repositories, `dependencies`, `dependencyInsight`, Gradle diagnostics |
| Máy A chạy được, máy B lỗi Java version | Runtime JDK thấp hơn bytecode/dependencies | `java -version` trên máy chạy, so với Java toolchain |
| Module thư viện không có main nhưng `bootJar` báo lỗi | Áp dụng Boot plugin cho library không cần executable | Chỉ apply Spring Boot plugin tại module application |
| File được publish không chạy được | Pipeline publish `jar` plain output, không phải `bootJar` | Kiểm tra task publication/artifact classifier/manifest |
| `jar tf` không giải nén được fully executable JAR | Có embedded launch script | Dùng công cụ/format được tài liệu hỗ trợ hoặc không bật launch script |
| Docker image build không nhận layers như mong đợi | Metadata layers/tools hoặc image workflow bị tùy chỉnh | Xem Boot 3.3 packaging config, `bootBuildImage`/Dockerfile tương ứng |
| JAR chạy nhưng HTTP endpoint không phản hồi | Port/profile/config/environment, controller mapping hoặc startup error | Xem Spring Boot log và `curl` URL chính xác; đây không nhất thiết là lỗi `bootJar` |

Không nên sửa bằng cách xóa dependency tùy tiện, tắt test, hardcode `Main-Class` theo một phiên bản Boot khác hoặc chép toàn bộ `build/libs` sang máy phát hành. Bắt đầu từ **log task**, **runtimeClasspath**, **artifact output** và **runtime stack trace**.

## 17. Công cụ điều tra có giá trị

### 17.1. Chứng minh plugin và task tồn tại

~~~bash
./gradlew --version
./gradlew projects
./gradlew tasks --all
./gradlew bootJar --dry-run
~~~

`projects` xác định project path; `tasks --all` hiển thị tasks; `--dry-run` xem kế hoạch thực thi. Không dùng `--dry-run` như bằng chứng JAR mới được tạo.

### 17.2. Chứng minh dependency runtime

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

`dependencies` cho dependency graph; `dependencyInsight` cho biết tại sao version được chọn trong configuration. Với multi-project, thêm task path đúng subproject, ví dụ `:api-service:dependencies` cùng `--configuration runtimeClasspath`.

Dependency trong graph chưa đủ chứng minh thư viện được đưa vào file cuối nếu `bootJar` bị custom classpath/excludes; khi có cấu hình nâng cao, phải đối chiếu archive thực tế.

### 17.3. Chứng minh archive layout

~~~bash
./gradlew clean bootJar
jar tf build/libs/bootjar-demo-0.1.0.jar
~~~

Sau khi xác minh manifest và Boot layout, chạy `java -jar` với JVM phù hợp và kiểm tra behavior. Thứ tự điều tra tốt là **build task → output archive → runtime**, thay vì chỉ sửa application code khi process không startup.

## 18. Bài tập thực hành có đáp án

### Bài 1 — Đóng gói tối thiểu

**Yêu cầu:** dùng một trong hai build scripts ở mục 5–6 cùng ba Java source files ở mục 7. Chạy `./gradlew clean bootJar` và `java -jar build/libs/bootjar-demo-0.1.0.jar --server.port=18080`, sau đó gọi `/artifact`.

**Kết quả mong đợi:** body `bootjar-ready`. Bạn phải giải thích được class nào là entrypoint, task nào tạo archive và file nào cần triển khai.

### Bài 2 — Phân biệt plain và executable

**Yêu cầu:** chạy `./gradlew clean assemble`; quan sát `build/libs`. Dùng `jar tf` và manifest để phân biệt `bootjar-demo-0.1.0.jar` với `bootjar-demo-0.1.0-plain.jar`.

**Đáp án:** Theo convention Spring Boot Gradle Plugin 3.3, `bootJar` tạo file không classifier và `jar` tạo `-plain.jar`. Boot executable thường có `BOOT-INF/classes`/`BOOT-INF/lib` và Boot launcher. Nếu build có custom classifier, phải theo output thực tế, không theo suffix cố định.

### Bài 3 — Kiểm thử có nằm trong `bootJar`?

**Yêu cầu:** chạy `./gradlew clean bootJar --dry-run` và `./gradlew clean build --dry-run`, giải thích vì sao một lượt có hoặc không có `test` trong graph. Sau đó chạy `./gradlew clean build` để xác nhận test thực thi thật.

**Đáp án:** `bootJar` tạo executable artifact và chạy dependencies cho packaging; nó không đương nhiên phụ thuộc JUnit `test`. Java lifecycle `build` thường gồm `assemble` và `check`, mà `check` thường kéo `test`. `--dry-run` chỉ chứng minh task được schedule, không chạy test actions.

### Bài 4 — Đặt tên và classifier

**Yêu cầu:** đổi tên executable thành `service.jar` với `archiveFileName`. Chạy `bootJar` rồi khởi động bằng lệnh phù hợp.

**Đáp án:** Sau đổi tên, đường dẫn runtime là `build/libs/service.jar` nếu chưa đổi destinationDirectory. Không dùng lại tên file `bootjar-demo-0.1.0.jar` trong tài liệu phát hành.

**Câu hỏi mở rộng:** nếu đổi classifier của `bootJar` thành `boot` và đưa `jar` classifier về rỗng, file nào là executable?

**Đáp án:** Output của `bootJar` mang hậu tố `-boot.jar` mới là executable. File không hậu tố classifier lúc này có thể là plain JAR.

### Bài 5 — Main class có nhiều ứng viên

**Tình huống:** main source set có `PackagingApplication` và `ToolApplication` đều khai báo `public static void main(String[])`; `bootJar` báo không chọn được main class.

**Đáp án:** Chọn main tường minh bằng `tasks.named<BootJar>("bootJar") { mainClass.set("com.example.packaging.PackagingApplication") }` trong Kotlin DSL hoặc cú pháp Groovy tương ứng. Không tự xóa main class còn lại nếu tool đó thực sự cần trong codebase.

### Bài 6 — Release sạch

**Yêu cầu:** kiểm tra Boot JAR chứa `ArtifactController.class` nhưng không chứa `ArtifactControllerTest.class`. Nếu test class có trong artifact, điều tra những phần build nào có thể đưa test output vào main packaging.

**Đáp án:** Theo cấu hình Java plugin thông thường, `bootJar` dùng main output/runtimeClasspath và loại test source/output. Nếu test classes lọt vào, kiểm tra sourceSets, `bootJar.classpath`, custom `from(...)`/`copy` logic và artifact đã được chọn.

### Bài 7 — Kiểm tra hiểu đúng lớp

**Câu hỏi:** Có nên tắt `layered` để sửa một lỗi thiếu main class không?

**Đáp án:** Không. Layer metadata phục vụ tổ chức nội dung cho image caching, không quyết định ứng dụng có main method hay không. Lỗi main class cần xử lý ở source set và cấu hình `mainClass`/plugin, không bằng cách thay `layered`.

## 19. Checklist trước khi phát hành

- [ ] Đúng module ứng dụng có Spring Boot Gradle Plugin và Java plugin.
- [ ] Java main class là hợp lệ, đúng package; nếu nhiều ứng viên, đã cấu hình `mainClass`.
- [ ] Gradle wrapper/JDK phù hợp; dependency repositories resolve được.
- [ ] Runtime dependencies được khai báo đúng scope, không dựa vào test-only dependencies.
- [ ] Bước kiểm thử cần thiết đã chạy và pass; không coi `bootJar` tự là test suite.
- [ ] Task `bootJar` chạy thành công; output filename/classifier được xác định rõ.
- [ ] File phát hành có Boot loader, `BOOT-INF/classes`, `BOOT-INF/lib` và manifest đúng.
- [ ] `java -jar` khởi động được trong môi trường kiểm tra, endpoint/luồng quan trọng hoạt động.
- [ ] Plain JAR (nếu có) và executable JAR không bị lẫn trong publish pipeline.
- [ ] Không vô tình đóng test fixtures, development-only dependencies hoặc secrets vào production JAR.
- [ ] Thay đổi `archiveFileName`, directory, layers hoặc launchScript đã được CI/ops cập nhật tương ứng.

**Tiêu chí hoàn thành bài:** từ một Spring Boot project Java, bạn tự tạo được executable JAR bằng Gradle `bootJar`, giải thích đúng task graph và sự khác biệt so với `jar`, chứng minh được nội dung/manifest, chạy bằng `java -jar` và biết xử lý các lỗi cấu hình phổ biến.

## 20. Tài liệu chính thức để đối chiếu

- Spring Boot 3.3.13 — Packaging Executable Archives với Gradle (`bootJar`, plain/classifier, main class, layers, launch script): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3.13 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot 3.3.13 — Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3 — First Application / Gradle executable JAR: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Gradle Java Plugin (`jar`, `test`, `assemble`, `build` và source sets): https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html

Khi dự án đổi Spring Boot Plugin hoặc Gradle wrapper, đối chiếu tài liệu của **đúng phiên bản** trước khi sao chép các lệnh và các thuộc tính đặc thù. Mục tiêu không phải chỉ làm xuất hiện một file `.jar`, mà là tạo **đúng executable archive từ đúng module, có đúng runtime dependencies, đã được kiểm thử và có thể khởi chạy**.
