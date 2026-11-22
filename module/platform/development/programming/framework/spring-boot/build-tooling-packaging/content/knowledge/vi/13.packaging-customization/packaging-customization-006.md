# Tạo nhiều artifact với classifier và tránh ghi đè đầu ra

Một dự án Spring Boot có thể cần **nhiều artifact từ cùng một bộ source**: JAR thông thường cho module khác sử dụng, **executable JAR** để triển khai, JAR chỉ chứa API dùng chung, source JAR để tra cứu mã nguồn, hoặc WAR cho một môi trường triển khai riêng. Nếu chỉ đổi tên file thủ công hoặc để hai tác vụ cùng ghi một đường dẫn, build có thể ghi đè kết quả, publish sai artifact hoặc khiến CI chọn nhầm JAR không chạy được.

Giải pháp cốt lõi là quản lý **classifier**, **archive name**, **task/goal sở hữu output** và **publication coordinates**. Bài này giải thích chi tiết với **Gradle và Maven trong Spring Boot**, có ví dụ **Java 17** tạo ba file khác nhau (plain, exec, api), cách phát hành artifact, lỗi va chạm tên file và quy trình kiểm tra lại nội dung của từng JAR.

Ví dụ minh họa chọn **Spring Boot 3.3.13**, Java 17 và Gradle 8.x hoặc Maven 3.9.x để bảo đảm cấu hình nhất quán; đây không phải tuyên bố về phiên bản mới nhất. Khi áp dụng vào hệ thống thực tế, ưu tiên release đang được bảo trì và kiểm tra tài liệu đúng phiên bản.

## 1. Artifact và classifier là gì?

**Artifact** là sản phẩm của quá trình build, ví dụ `artifact-demo-1.0.0.jar`, `artifact-demo-1.0.0-exec.jar`, `artifact-demo-1.0.0-api.jar` hoặc `artifact-demo-1.0.0-sources.jar`. Mỗi artifact có **loại nội dung và mục đích sử dụng**, chứ không chỉ có một tên file khác.

Trong hệ sinh thái Maven, tọa độ artifact thường được mô tả bởi:

```text
groupId : artifactId : version : extension/type : classifier (nếu có)

com.example : artifact-demo : 1.0.0 : jar : (không classifier)
com.example : artifact-demo : 1.0.0 : jar : exec
com.example : artifact-demo : 1.0.0 : jar : api
com.example : artifact-demo : 1.0.0 : jar : sources
```

`classifier` là **định danh phụ** cho một biến thể của cùng bộ `groupId/artifactId/version` và kiểu đóng gói. Nó giúp repository phân biệt file ở cùng version, ví dụ `artifact-demo-1.0.0-exec.jar` với `artifact-demo-1.0.0.jar`.

Với Gradle, thuộc tính `archiveClassifier` là một phần của **tên archive mặc định**. Nó không đồng nghĩa với việc file đã được **đưa vào Maven publication**: tạo một JAR trên disk và cấu hình publication là hai hành động khác nhau.

| Artifact | Nội dung điển hình | Người dùng chính | Có nên chạy trực tiếp? |
| --- | --- | --- | --- |
| **Plain JAR**, không classifier | Class/resource của project ở root archive | Module khác phụ thuộc vào mã ứng dụng/thư viện | Không bảo đảm: thiếu runtime dependencies/launcher |
| **Executable JAR**, classifier `exec` | Boot loader, `BOOT-INF/classes`, `BOOT-INF/lib` | Deployment, vận hành, container image | Có, bằng `java -jar` nếu cấu hình đúng |
| **API JAR**, classifier `api` | Chỉ một tập class được chọn | Consumer cần API hẹp | Thường không |
| **Sources JAR**, classifier `sources` | `.java` gốc | IDE, tra cứu và gỡ lỗi | Không |
| **Javadoc JAR**, classifier `javadoc` | Tài liệu HTML từ Javadoc | Người đọc tài liệu và IDE | Không |

**Chú ý:** classifier không tạo ra khác biệt nội dung một cách kỳ diệu. Bạn vẫn phải cấu hình **task hoặc goal tạo đúng dữ liệu**. Hai file có classifier khác nhau nhưng cùng chứa một nội dung lỗi thì vẫn là hai artifact lỗi.

## 2. Ba kiểu va chạm cần phân biệt

Có ít nhất ba tầng xung đột:

1. **Va chạm đường dẫn output trên filesystem:** hai task cùng viết `build/libs/artifact-demo-1.0.0.jar` hoặc hai goal xuất `target/artifact-demo-1.0.0.jar`. Task chạy sau có thể ghi đè file, Gradle nhận diện overlapping outputs hoặc build mất tính tái lập.
2. **Va chạm publication coordinates:** hai artifact được publish bằng **cùng group, artifactId, version, extension và classifier**. Repository không thể lưu chúng như hai biến thể khác nhau ở cùng tọa độ; một bản có thể thay thế bản kia hoặc publishing thất bại.
3. **Nhầm loại artifact:** filename không va chạm, nhưng pipeline lấy `-plain.jar` để chạy production, hoặc consumer library dùng executable JAR có class nằm trong `BOOT-INF/classes` thay vì ở classpath root.

`Classifier` hỗ trợ phân biệt tên/tọa độ, nhưng vẫn phải:
- Đảm bảo **mỗi output path có đúng một chủ sở hữu**.
- Đảm bảo **mỗi publication variant có một tọa độ duy nhất**.
- Chọn **đúng artifact** ở deploy và ở dependency declaration.
- Kiểm tra **nội dung thật** thay vì chỉ đoán từ hậu tố `-exec`/`-api`.

Sơ đồ:

```text
src/main/java + src/main/resources
                |
           compile/classes
                |
                +----> jar/normal artifact ----> artifact-demo-1.0.0.jar
                |
                +----> bootJar/repackage ------> artifact-demo-1.0.0-exec.jar
                |
                +----> filtered API Jar -------> artifact-demo-1.0.0-api.jar
                |
                +----> sourcesJar -------------> artifact-demo-1.0.0-sources.jar
                       (nếu bật)
```

Đây là sơ đồ luồng kết quả, không phải bảo đảm mọi task ở trên tự được tạo và thực thi trong bất cứ project nào. Mỗi build tool có lifecycle và cấu hình publication riêng.

## 3. Gradle tự ngăn ghi đè giữa `bootJar` và `jar` như thế nào?

Trong Spring Boot Gradle plugin 3.3, khi `bootJar` và `jar` cùng được cấu hình, **quy ước mặc định** thường là:
- `bootJar`: classifier rỗng, output `artifact-demo-1.0.0.jar`.
- `jar`: classifier `plain`, output `artifact-demo-1.0.0-plain.jar`.

Lý do: hai task **không được sản xuất cùng một file**. `bootJar` là executable archive; `jar` là plain archive. Nếu cả hai đều mặc định không classifier và cùng base name/version/directory, output có thể trùng.

Nếu muốn **plain JAR giữ tọa độ chính** (không classifier) để module khác dùng như dependency, và executable JAR mang classifier `exec`, đổi hai task cùng lúc:

```groovy
// Đặt trong build.gradle có áp dụng Java và Spring Boot Gradle plugin
tasks.named('bootJar') {
    archiveClassifier = 'exec'
}

tasks.named('jar') {
    archiveClassifier = ''
}
```

Với `project.name = 'artifact-demo'` và `version = '1.0.0'`, đầu ra dự kiến:

```text
build/libs/artifact-demo-1.0.0.jar       # plain, primary
build/libs/artifact-demo-1.0.0-exec.jar  # executable
```

**Không chỉ đổi một nửa cấu hình rồi phỏng đoán.** Ví dụ chuyển `jar.archiveClassifier` thành rỗng nhưng giữ `bootJar` cũng rỗng tạo nguy cơ **hai task cùng một path**. Nếu task có `archiveFileName` ghi đè tên tùy biến, property này có thể **vô hiệu hóa cách ghép tên mặc định với classifier**; cần đối chiếu đường dẫn cuối cùng của cả hai task.

Nếu không cần plain JAR, có thể không yêu cầu chạy task `jar` hoặc tắt nó theo chủ đích:

```groovy
tasks.named('jar') {
    enabled = false
}
```

Nhưng **không tắt máy móc** trong module vừa cần làm library dependency, publish `components.java`, hoặc thực hiện native-image workflow có thể dựa vào task `jar`. Với bài toán tạo nhiều artifact, cách phù hợp thường là **giữ cả hai với classifier khác nhau**.

## 4. Dự án mẫu: một ứng dụng, một lớp API dùng chung

Chúng ta muốn có:
1. Plain JAR chứa các class project ở root archive.
2. Executable JAR có Spring Boot launcher cùng runtime dependencies.
3. API-only JAR chỉ chứa `Greeting` trong package `com.example.artifacts.api`.

Cấu trúc:

```text
artifact-demo/
├── settings.gradle / build.gradle       (phương án Gradle)
├── pom.xml                              (phương án Maven)
└── src/main/java/com/example/artifacts/
    ├── ArtifactApplication.java
    └── api/
        └── Greeting.java
```

### 4.1. File `Greeting.java`

`src/main/java/com/example/artifacts/api/Greeting.java`:

```java
package com.example.artifacts.api;

public final class Greeting {

    private Greeting() {
    }

    public static String message() {
        return "classifier-ok";
    }
}
```

`Greeting` chỉ dùng Java chuẩn, không phụ thuộc Spring Boot. Vì vậy, đặt nó vào API-only JAR là ví dụ an toàn: consumer có thể gọi `Greeting.message()` mà không cần các class ứng dụng chưa được xuất kèm.

### 4.2. File `ArtifactApplication.java`

`src/main/java/com/example/artifacts/ArtifactApplication.java`:

```java
package com.example.artifacts;

import com.example.artifacts.api.Greeting;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ArtifactApplication implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication.run(ArtifactApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println("artifact=" + Greeting.message());
    }
}
```

Đây là Java 17 hợp lệ. `SpringApplication.run(...)` tạo ứng dụng Spring Boot dạng non-web khi chỉ có `spring-boot-starter`; `CommandLineRunner` gọi `Greeting.message()` rồi in một dòng.

Khi chạy **đúng executable JAR**, dòng do mã ví dụ in ra là:

```text
artifact=classifier-ok
```

Có thể còn log của Spring Boot; đừng coi toàn bộ stdout chỉ có một dòng trên. Vì ví dụ không có HTTP server hay tác vụ nền chạy dài, JVM thông thường kết thúc sau startup runner.

**Điểm cốt lõi về classifier:** mã Java không biết classifier của file JAR. Classifier chỉ ảnh hưởng **quá trình tạo, đặt tên, publish/chọn artifact**; cùng một class có thể xuất hiện trong plain JAR và executable JAR theo những layout khác nhau.

## 5. Gradle Groovy DSL: tạo đồng thời `plain`, `exec` và `api`

Tạo `settings.gradle`:

```groovy
rootProject.name = 'artifact-demo'
```

Tạo `build.gradle` đầy đủ:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

// Chỉ định entry point của executable archive.
springBoot {
    mainClass = 'com.example.artifacts.ArtifactApplication'
}

// Plain archive là artifact chính, không classifier.
tasks.named('jar') {
    archiveClassifier = ''
}

// Executable Spring Boot archive có classifier "exec".
tasks.named('bootJar') {
    archiveClassifier = 'exec'
}

// Artifact bổ sung: chỉ chứa các class trong package public API.
tasks.register('apiJar', Jar) {
    archiveClassifier = 'api'
    from(sourceSets.main.output) {
        include 'com/example/artifacts/api/**'
    }
}

// Đảm bảo assemble tạo cả artifact API tùy biến.
tasks.named('assemble') {
    dependsOn tasks.named('apiJar')
}
```

**Đây là cấu hình đầy đủ của một project mẫu**, không cần thêm khối `plugins` hoặc `tasks.register('apiJar')` lần thứ hai.

Ý nghĩa:
- `tasks.named('jar')` sửa task plain archive do Java plugin cung cấp. Classifier rỗng khiến plain JAR mang filename không hậu tố.
- `tasks.named('bootJar')` sửa task do Spring Boot plugin cung cấp, đặt classifier `exec` và giữ entry point đã xác định.
- `tasks.register('apiJar', Jar)` tạo task `Jar` độc lập với classifier `api`. `from(sourceSets.main.output)` lấy output sau biên dịch/đóng resource; `include` chỉ giữ đường dẫn package API đã chọn.
- `assemble.dependsOn(apiJar)` đưa artifact mới vào quy trình assemble; không giả định Gradle tự gọi mọi custom Jar task khi chỉ chạy `build`.
- Cả ba task dùng quy tắc tên theo project/version/classifier và thư mục `build/libs` khi không có override khác.

Build:

```bash
./gradlew clean assemble
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean assemble
```

Đầu ra **dự kiến**:

```text
build/libs/artifact-demo-1.0.0.jar
build/libs/artifact-demo-1.0.0-exec.jar
build/libs/artifact-demo-1.0.0-api.jar
```

**Không mặc nhiên đoán tên file khi project đã cấu hình `archiveBaseName`, `archiveVersion`, `archiveFileName` hoặc thư mục output.** Hãy kiểm tra output thực tế sau build.

Chạy executable archive:

```bash
java -jar build/libs/artifact-demo-1.0.0-exec.jar
```

Dòng từ ứng dụng:

```text
artifact=classifier-ok
```

Đừng chạy `java -jar build/libs/artifact-demo-1.0.0.jar` rồi kỳ vọng giống Boot JAR: plain JAR không có Boot launcher/nested dependencies theo mặc định.

## 6. Xem bên trong ba artifact Gradle để chứng minh chúng khác nhau

Liệt kê:

```bash
jar tf build/libs/artifact-demo-1.0.0.jar
jar tf build/libs/artifact-demo-1.0.0-exec.jar
jar tf build/libs/artifact-demo-1.0.0-api.jar
```

Các entry quan trọng cần tìm:

| Artifact | Entry mong đợi |
| --- | --- |
| Plain JAR | `com/example/artifacts/ArtifactApplication.class` và `com/example/artifacts/api/Greeting.class` ở root archive |
| Executable JAR | `BOOT-INF/classes/com/example/artifacts/ArtifactApplication.class`, `BOOT-INF/classes/com/example/artifacts/api/Greeting.class`, `BOOT-INF/lib/...`, Boot loader |
| API-only JAR | `com/example/artifacts/api/Greeting.class`; **không** có `ArtifactApplication.class`, **không** có `BOOT-INF/lib` |

Đây là **những entry dự kiến**, không phải output `jar tf` đầy đủ. Plain/API JAR vẫn có thể chứa `META-INF/MANIFEST.MF` do Java Jar task tạo.

Chạy trong Linux/macOS:

```bash
jar tf build/libs/artifact-demo-1.0.0.jar |
    grep '^com/example/artifacts/'
jar tf build/libs/artifact-demo-1.0.0-exec.jar |
    grep '^BOOT-INF/'
jar tf build/libs/artifact-demo-1.0.0-api.jar |
    grep '^com/example/artifacts/api/'
```

Nếu manifest của `-exec.jar` được đọc bằng `unzip -p`, Spring Boot executable JAR thường có:
- `Main-Class`: Boot `JarLauncher`, ví dụ `org.springframework.boot.loader.launch.JarLauncher` với Spring Boot 3.3.
- `Start-Class`: `com.example.artifacts.ArtifactApplication`.

**Không nhầm `Main-Class` của Boot loader với class main ứng dụng.** API-only JAR không cần manifest khởi động. Classifier `api` không có nghĩa module phụ thuộc tự biết class nào nên import: nội dung artifact thực tế và dependency metadata mới quyết định tính khả dụng.

## 7. Gradle Kotlin DSL tương đương

Nếu project dùng `build.gradle.kts`, không chép nguyên cú pháp Groovy. Ví dụ **file Kotlin DSL đầy đủ** dùng cùng mã Java mục 4:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}

springBoot {
    mainClass.set("com.example.artifacts.ArtifactApplication")
}

tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}

tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("exec")
}

val apiJar by tasks.registering(Jar::class) {
    archiveClassifier.set("api")
    from(sourceSets.main.get().output) {
        include("com/example/artifacts/api/**")
    }
}

tasks.named("assemble") {
    dependsOn(apiJar)
}
```

Dùng `settings.gradle.kts` với:

```kotlin
rootProject.name = "artifact-demo"
```

Kotlin DSL sử dụng property API `archiveClassifier.set(...)` và typed task `tasks.named<BootJar>("bootJar")`. `apiJar` là `TaskProvider` được Gradle liên kết vào `assemble` thông qua `dependsOn(apiJar)`.

**Tránh trộn Groovy DSL và Kotlin DSL trong cùng file.** Cách xây file và bộ ba output theo classifier vẫn tương đương ví dụ Gradle Groovy ở mục 5.

## 8. Gradle archive naming: khi nào classifier không còn bảo vệ bạn?

Gradle thường tạo tên archive theo dạng khái niệm:

```text
[archiveBaseName]-[archiveAppendix]-[archiveVersion]-[archiveClassifier].[archiveExtension]
```

Những thành phần rỗng sẽ được bỏ phù hợp với quy tắc đặt tên. Các property quan trọng:

| Property | Vai trò | Lỗi dễ gặp |
| --- | --- | --- |
| `archiveBaseName` | Tên cơ sở artifact | Hai task dùng tên giống nhau mà quên classifier |
| `archiveVersion` | Phiên bản trong tên file | Một task bị cố định version cũ |
| `archiveClassifier` | Hậu tố phân biệt biến thể | Hai task cùng để rỗng hoặc cùng `exec` |
| `archiveExtension` | Kiểu file, như `jar`, `war` | Dùng sai extension so với nội dung |
| `archiveFileName` | Ghi rõ **toàn bộ tên file** | Hai task cùng đặt `app.jar` dù classifier khác |
| `destinationDirectory` | Thư mục output | Hai task ghi cùng đường dẫn đầy đủ |

Ví dụ cấu hình **nguy hiểm**, không dùng:

```groovy
tasks.named('jar') {
    archiveClassifier = ''
    archiveFileName = 'application.jar'
}
tasks.named('bootJar') {
    archiveClassifier = 'exec'
    archiveFileName = 'application.jar' // VẪN trùng chính xác cùng output path!
}
```

**Vì sao?** `archiveFileName` đã chỉ định toàn bộ tên, nên classifier không tự chèn `-exec` nữa. Đường dẫn thực tế là `destinationDirectory + archiveFileName`. Nếu hai task cùng trỏ `build/libs/application.jar`, bạn phải sửa lại filename hoặc directory.

Ví dụ an toàn nếu cần tên cố định:

```groovy
tasks.named('jar') {
    archiveFileName = 'artifact-demo-plain.jar'
}
tasks.named('bootJar') {
    archiveFileName = 'artifact-demo-exec.jar'
}
```

Đây là **đoạn thay thế cấu hình output filename** cho project có hai task; nếu dùng đúng ví dụ mục 5 và không có yêu cầu đặc biệt, **nên ưu tiên classifier** thay vì hardcode tên. Tên hardcode cũng phải xét version và môi trường CI, kẻo bản build `1.0.1` ghi đè bản `1.0.0` khi cùng thư mục hoặc cache.

**Quy tắc review:** với mỗi task archive, tính/quan sát `archiveFile` cuối cùng. Nếu hai task hợp lệ có cùng file path, đó là một nguy cơ thực tế ngay cả khi tên task, classifier hay input khác nhau.

## 9. Maven: artifact chính và artifact được attach

Maven có khái niệm **main artifact** (thông thường là `groupId:artifactId:version:jar` không classifier) và **supplemental/attached artifacts**. Attached artifacts có thể được `install` vào local repository hoặc `deploy` lên remote repository cùng với main artifact nếu được cấu hình đúng.

Ví dụ một project:
- `com.example:artifact-demo:1.0.0:jar` → JAR chính (plain).
- `com.example:artifact-demo:1.0.0:jar:exec` → Boot executable JAR.
- `com.example:artifact-demo:1.0.0:jar:api` → API-only JAR.

Lưu ý **chỉ đặt tên file `artifact-demo-1.0.0-api.jar` trong thư mục `target` chưa đủ** để file được publish như artifact classifier `api`. Maven plugin phải **attach** artifact với classifier phù hợp. Đây là khác biệt giữa “file sinh ra khi build” và “artifact có địa chỉ để consumer resolve”.

### 9.1. Spring Boot Maven `repackage` mặc định làm gì?

Với cấu hình Spring Boot starter parent và `spring-boot-maven-plugin` thông thường, goal `repackage` lấy JAR gốc do `maven-jar-plugin` tạo và **thay thế artifact chính bằng executable archive**. Bản JAR trước khi repackage có thể được lưu thành `*.jar.original`, nhưng đừng hiểu nó là một **classifier attached artifact** đã được install/deploy.

Nếu cần **giữ plain JAR là artifact chính** và tạo Boot JAR bổ sung, đặt classifier `exec` cho goal `repackage`. Khi không có artifact `exec` khác làm nguồn, plugin sẽ lấy main JAR để repackage rồi attach kết quả `-exec.jar`.

### 9.2. Khi đã có một artifact cùng classifier

Chi tiết quan trọng của `spring-boot:repackage`: nếu bạn cấu hình `<classifier>exec</classifier>` và **một artifact classifier `exec` đã tồn tại trong quá trình build**, plugin có thể chọn **artifact `exec` đó làm source để repackage và thay thế nó**, thay vì tạo một Boot JAR bổ sung từ main JAR.

Vì vậy:
- **Không** cho `maven-jar-plugin` và `spring-boot-maven-plugin` cùng tự tạo hai output độc lập với classifier `exec` nếu không có ý định repackage artifact `exec` đã tạo.
- Đặt classifier của plain/API và executable **khác nhau**.
- Khi thật sự muốn repackage một classified artifact đã được tạo, quản lý rõ **thứ tự execution trong phase package** và verify output.

Trong Maven, **`<attach>true</attach>`** (mặc định trong plugin Spring Boot) xác định artifact repackage có được đưa vào tập install/deploy hay không. `attach=false` có thể vẫn tạo file local nhưng **không publish artifact đó**; không dùng khi consumer/deploy pipeline cần resolve theo classifier từ repository.

## 10. Maven POM đầy đủ: tạo plain, executable và API JAR

Tạo `pom.xml` ở root project, dùng hai file Java mục 4:

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
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <executions>
                    <execution>
                        <id>api-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar</goal>
                        </goals>
                        <configuration>
                            <classifier>api</classifier>
                            <includes>
                                <include>com/example/artifacts/api/**</include>
                            </includes>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <configuration>
                            <classifier>exec</classifier>
                            <attach>true</attach>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tại sao cấu hình trên tạo ba artifact?**

1. Với `<packaging>jar</packaging>`, Maven lifecycle tạo **main JAR không classifier** từ `target/classes`.
2. `maven-jar-plugin` có **execution riêng** `api-jar` trong phase `package`, classifier `api` và chỉ lấy class khớp `com/example/artifacts/api/**`. Vì classifier khác, nó tạo **attached supplemental JAR** thay vì thay default main JAR.
3. `spring-boot-maven-plugin` được khai báo với execution id `repackage` để **tùy chỉnh execution đã được starter parent cung cấp**, không tạo execution khác chạy lặp. Nó lấy main JAR và sản xuất executable `-exec.jar`; `attach=true` cho phép install/deploy cùng main artifact.
4. Hai plugin có classifier nhiệm vụ **khác nhau**: `api` không va chạm `exec`. Sắp xếp plugin làm việc trên artifact cùng phase có chủ đích, tránh tạo cùng output path.

**Nếu project không dùng Spring Boot starter parent**, cần thêm version cho Maven plugins và khai báo goal `repackage`/phase phù hợp thay vì dựa vào execution kế thừa. Chỉ import `spring-boot-dependencies` BOM **không tự quản lý plugin version hay tạo execution**.

Build:

```bash
./mvnw clean package
```

Dự kiến thấy:

```text
target/artifact-demo-1.0.0.jar
target/artifact-demo-1.0.0-exec.jar
target/artifact-demo-1.0.0-api.jar
```

Khi cài được Maven Wrapper, dùng `./mvnw`; trên Windows PowerShell dùng `.\mvnw.cmd`. Nếu không có Wrapper, dùng `mvn` với Maven/JDK phù hợp.

### 10.1. Kiểm tra từng file Maven

```bash
jar tf target/artifact-demo-1.0.0.jar
jar tf target/artifact-demo-1.0.0-api.jar
jar tf target/artifact-demo-1.0.0-exec.jar
java -jar target/artifact-demo-1.0.0-exec.jar
```

Dòng từ ứng dụng:

```text
artifact=classifier-ok
```

Plain/API JAR không mang runtime dependencies, nên không mong chúng tự chạy như executable JAR. Nếu artifact `-api.jar` không có `Greeting.class`, xem lại pattern `<include>com/example/artifacts/api/**</include>` và package/path của file Java.

### 10.2. Vì sao Maven execution id quan trọng?

`spring-boot-starter-parent` đã cấu hình execution id `repackage`. Khi muốn sửa classifier cho execution ấy, hãy dùng **chính id `repackage`**. Nếu thêm một execution mới khác id cũng gọi goal `repackage`, plugin có thể chạy hai lần ở phase `package`; điều này không có nghĩa bạn tạo được hai executable JAR hợp lệ, và còn có thể gây lỗi hoặc xử lý nhầm artifact.

Tương tự, `maven-jar-plugin` đã có goal `jar` mặc định cho packaging `jar`. Muốn một **artifact bổ sung** thì tạo execution có classifier riêng; đừng sửa goal mặc định một cách không chủ đích khiến main JAR biến mất hoặc đổi vai trò.

## 11. Dùng classifier khi các module phụ thuộc vào nhau

Trong một repository nhiều module, có thể có hai nhu cầu khác nhau:

- Module **consumer** cần gọi class API của module này như thư viện.
- Hệ thống **deploy** cần chạy nguyên ứng dụng Spring Boot.

Spring Boot executable JAR thường đặt class ứng dụng trong `BOOT-INF/classes`, không phải ở root archive như library JAR. Vì vậy **không nên chọn `-exec.jar` làm library dependency thông thường**. Dùng plain JAR hoặc artifact API phù hợp, rồi triển khai executable JAR riêng.

Ví dụ Maven consumer dùng **main plain JAR**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
</dependency>
```

Nếu consumer cần **chỉ JAR API**:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <classifier>api</classifier>
</dependency>
```

Đoạn thứ hai chỉ có ý nghĩa khi artifact `api` đã được attach/install/deploy đúng cách. Một API-only JAR **không tự động mang đầy đủ dependency transitive** hoặc hợp đồng tương thích như một module library được thiết kế riêng. Nếu class trong API JAR tham chiếu class đã bị lọc ra, consumer vẫn có thể lỗi khi runtime. Trong sản phẩm nhiều module nghiêm túc, tách **module `api` độc lập** thường dễ quản lý dependency/version hơn việc duy trì một JAR có lọc class thủ công.

Trong Gradle, cách dùng dependency/classifier cũng phải phù hợp với metadata repository và publication. Tránh suy đoán rằng chỉ đặt tên file `-api.jar` dưới `build/libs` là IDE và Gradle consumer đã tự resolve được nó.

## 12. Publish nhiều artifact: Maven và Gradle khác nhau ở điểm nào?

### 12.1. Maven install/deploy

Với POM mục 10, chạy:

```bash
./mvnw clean install
```

Khi build thành công và các artifact được attach hợp lệ, local Maven repository dự kiến có các file cho cùng version:

```text
~/.m2/repository/com/example/artifact-demo/1.0.0/
├── artifact-demo-1.0.0.pom
├── artifact-demo-1.0.0.jar
├── artifact-demo-1.0.0-exec.jar
└── artifact-demo-1.0.0-api.jar
```

Các checksum/metadata phụ thuộc công cụ và repository có thể xuất hiện thêm. `install` là **cài vào local Maven repository**, khác `deploy` lên remote repository. Muốn deploy cần cấu hình `distributionManagement` và credentials qua kênh an toàn. Đừng tự đăng/publish lên registry thật chỉ để kiểm tra bài thực hành.

Với artifact chính là plain JAR, một `<dependency>` không classifier sẽ resolve plain. Nếu không chủ đích đặt classifier cho `repackage`, executable JAR có thể **thay thế main artifact** và consumer dependency bình thường không sử dụng được theo classpath layout mong đợi.

### 12.2. Gradle: build file không đồng nghĩa publication

Chạy `./gradlew assemble` chỉ tạo file trong `build/libs`. Để publish, Gradle cần `maven-publish` hoặc plugin tương ứng, với publication khai báo đúng variants.

Ví dụ **đoạn cấu hình bổ sung cho `build.gradle` Groovy ở mục 5**, xuất plain artifact của Java component và attach executable + API variants:

```groovy
plugins {
    id 'maven-publish'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            artifact(tasks.named('bootJar')) {
                classifier = 'exec'
            }
            artifact(tasks.named('apiJar')) {
                classifier = 'api'
            }
        }
    }
}
```

**Cách dùng:** `plugins` trong Gradle phải là khối plugin ở đầu file; khi ghép vào `build.gradle` mục 5, hãy **thêm `id 'maven-publish'` vào khối `plugins` có sẵn**, rồi thêm **chỉ khối `publishing`** phía sau. Đoạn trên được trình bày thành cấu hình có ngữ cảnh, **không được chép một khối `plugins` thứ hai vào giữa file**.

`from components.java` đưa Java component chính vào publication, thông thường là plain JAR cùng dependency metadata tương ứng. Hai lệnh `artifact(tasks.named(...))` thêm artifacts từ task riêng với classifier khác nhau. Đừng publish cùng một task/biến thể hai lần dưới cùng classifier/extension; nếu metadata variant hoặc repository có quy tắc riêng, xác minh kết quả trước khi đưa vào CI.

Có thể kiểm tra **local Maven repository** bằng task publish-to-Maven-local (tên task phụ thuộc publication đã khai báo):

```bash
./gradlew publishToMavenLocal
```

**Trước khi publish lên remote**, xác nhận file output, tọa độ Maven, nội dung POM/module metadata và các artifact trong local repository; tránh đẩy artifact không chạy được hoặc overwrite một release đã công bố. Nếu dùng Gradle module metadata, các variants/capabilities được mô hình hóa riêng; đừng coi classifier là toàn bộ cơ chế variant-aware dependency management của Gradle.

### 12.3. Tên file khác không có nghĩa coordinates khác

Bạn có thể đặt `archiveFileName = 'my-custom-name.jar'` cho Gradle task, nhưng Maven repository vẫn dựa vào **groupId/artifactId/version/classifier/extension** của publication. Ngược lại, hai artifact có **tên file local khác nhau** mà được publish dưới cùng coordinates có thể đụng nhau trong registry.

Để ngăn ghi đè cần kiểm tra cả hai:
1. **Filesystem output path**: file sinh trong `build/libs` / `target`.
2. **Published identity**: tọa độ và variant metadata trong repository.

## 13. Sources JAR, Javadoc JAR và artifact phụ khác

### 13.1. Gradle

Java plugin hỗ trợ tạo source và Javadoc archives bằng:

```groovy
java {
    withSourcesJar()
    withJavadocJar()
}
```

Đây là **đoạn thêm vào khối `java`** của `build.gradle`, không chèn nguyên khối `java` thứ hai nếu muốn dễ quản lý. Gradle thường tạo:
- `artifact-demo-1.0.0-sources.jar`: mã nguồn Java.
- `artifact-demo-1.0.0-javadoc.jar`: tài liệu HTML Javadoc.

Chúng không phải Boot executable JAR. Nếu áp dụng `maven-publish` với `components.java`, source/Javadoc variants có thể được thêm vào publication theo cấu hình plugin. Trước khi xuất bản, kiểm tra artifact list để tránh việc thêm thủ công cùng classifier `sources` hoặc `javadoc` lần thứ hai.

### 13.2. Maven

Maven có `maven-source-plugin` và `maven-javadoc-plugin` để attach source/Javadoc JAR. Ví dụ riêng cho sources (đặt dưới `<build><plugins>` của `pom.xml`):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <goals>
                <goal>jar-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Goal này attach artifact classifier `sources`; không cần tự tạo file `-sources.jar` bằng copy thủ công. Nếu công ty đã quản lý plugin version qua parent, theo dõi effective POM để tránh khai báo version trùng/khác ý định. Javadoc artifact dùng plugin tương ứng khi dự án có nhu cầu phát hành tài liệu.

**Giữ classifier đúng ngữ nghĩa.** Không dùng `sources` cho executable JAR hoặc `javadoc` cho file không chứa Javadoc. Một hệ sinh thái tool/IDE có thể dựa vào các classifier chuẩn để tự tải mã nguồn hoặc tài liệu.

## 14. Nhiều `bootJar` hoặc nhiều entry point có nhất thiết cần tạo không?

Một dự án có thể có nhiều main class, nhưng **nhiều executable artifact không luôn là giải pháp phù hợp**. Nếu hai ứng dụng có dependencies, tài nguyên và lifecycle khác nhau, tách thành **hai Gradle/Maven module ứng dụng** thường dễ kiểm soát hơn.

Khi thật sự cần nhiều Boot archives, mỗi task/execution phải có:
- **Main class** rõ ràng.
- **Classpath/dependencies** phù hợp, không vô tình dùng runtime classpath của biến thể khác.
- **Classifier hoặc output file path** duy nhất.
- **Task inputs/outputs và dependency order** rõ ràng.
- **Smoke test riêng** trên từng executable artifact.

Không tạo task Gradle kiểu `Jar` thường rồi đặt classifier `exec2` và gọi đó là executable JAR; task `Jar` không tự đưa Boot loader và nested dependencies vào như `BootJar`. Cũng không sao chép một JAR đã đóng gói sang tên khác rồi gọi đó là một variant mới nếu không có khác biệt nội dung và mục đích.

Nếu muốn thay nhiều JVM options hoặc profile runtime, nhiều trường hợp chỉ cần **một executable JAR + runtime args/variables** (ví dụ `--spring.profiles.active=...`), thay vì tạo nhiều JAR có cấu hình môi trường riêng. Mỗi artifact bổ sung đều tăng công việc test, publish, bảo mật và bảo trì.

## 15. Các tình huống dễ gây ghi đè trong Maven

| Tình huống | Nguy cơ | Cách xử lý |
| --- | --- | --- |
| `spring-boot:repackage` không classifier | Thay main JAR bằng executable JAR; plain chỉ còn `.original` cục bộ | Đặt `<classifier>exec</classifier>` khi cần giữ plain chính |
| Hai execution tạo classifier `api` cùng artifact coordinates | Trùng artifact/file publish | Đặt classifier riêng hoặc chỉ giữ một execution sở hữu `api` |
| Maven Jar plugin sinh classified `exec` rồi Boot plugin cũng cấu hình `exec` | Boot plugin có thể repackage **classified source `exec`** | Chỉ làm khi đó là chủ đích; kiểm tra thứ tự và content |
| Thêm goal `repackage` dưới execution id mới khi đã dùng parent | Goal có thể chạy lặp | Tùy chỉnh execution id `repackage` sẵn có |
| `<finalName>application</finalName>` cố định | Các version/build khác nhau có cùng local filename | Tách build directories, version hóa artifact khi lưu/đẩy pipeline |
| `<attach>false</attach>` cho Boot `exec` | File local tồn tại nhưng không vào install/deploy | Dùng `attach=true` nếu artifact cần được consume từ repo |
| Chỉ copy `-api.jar` sang `target` bằng shell | Không attach Maven coordinates | Dùng plugin attach artifact đúng classifier |
| Repackage chạy trước khi main JAR được tạo | Không có source JAR/hoặc xử lý artifact cũ | Đúng phase `package`, kiểm tra thứ tự plugin executions |
| Module aggregate `<packaging>pom</packaging>` vẫn áp dụng `repackage` | Không có JAR ứng dụng để đóng gói | Chỉ bật Boot plugin ở module runnable |

**Maven có phân biệt main artifact và attached artifacts**. Không thể chỉ nhìn thấy ba file trong `target` mà khẳng định cả ba được install/deploy đúng; phải kiểm tra tọa độ sau `install` hoặc log deployment.

## 16. Các tình huống dễ gây ghi đè trong Gradle

| Tình huống | Nguy cơ | Cách xử lý |
| --- | --- | --- |
| `jar` và `bootJar` cùng classifier rỗng | Cùng path mặc định, task outputs overlap | Đặt `jar=''` và `bootJar='exec'`, hoặc ngược lại |
| Hai task khác classifier nhưng cùng `archiveFileName` | Tên đầy đủ ghi đè logic classifier | Đổi filename hoặc thư mục để output cuối cùng duy nhất |
| `destinationDirectory` cùng và base/version/classifier giống nhau | Ghi đè/khó cache, task graph không đáng tin | Tính `archiveFile` cuối cùng cho từng task |
| Custom `apiJar` được đăng ký nhưng không chạy | Không tự gắn vào `assemble` | `assemble.dependsOn(apiJar)` hoặc gọi task cụ thể |
| `jar.enabled=false` khi vẫn publish `components.java` | Thiếu plain artifact consumer cần | Giữ plain JAR và phân biệt `exec` |
| Tạo `archiveFileName='app.jar'` cho mọi version | Bản build khác version có cùng tên khi copy chung | Ghi version vào tên đích hoặc tách thư mục phiên bản |
| Publish `bootJar` cùng classifier với plain `jar` | Artifact coordinates bị trùng trong publication | Khai báo artifact classifier/variant khác nhau |
| Dùng `from(zipTree(...))` để tạo “fat JAR” thủ công | Duplicate entries, service descriptors và signatures dễ hỏng | Ưu tiên `bootJar` cho Spring Boot hoặc plugin shade được thiết kế đúng |
| CI dùng wildcard `build/libs/*.jar` | Chọn nhầm plain/API/sources artifact | Chọn tên cụ thể của executable JAR |
| Hai Gradle subprojects cùng copy artifact ra thư mục release chung với tên giống | Đè file khi tổng hợp builds | Kèm module name/version/classifier vào tên hoặc đường dẫn |

Nếu Gradle báo **overlapping outputs** hay không cache task được, đừng dùng `mustRunAfter` hoặc ép thứ tự để che xung đột. `mustRunAfter` chỉ điều chỉnh thứ tự, **không làm hai output paths khác nhau**. Nguyên tắc an toàn là **mỗi task owns một tập output khác nhau**.

## 17. Kiểm tra chính xác artifact trong CI/CD

### 17.1. Kiểm tra đủ ba file, không nhầm tên

Sau build Gradle mẫu:

```bash
./gradlew clean assemble
test -s build/libs/artifact-demo-1.0.0.jar
test -s build/libs/artifact-demo-1.0.0-exec.jar
test -s build/libs/artifact-demo-1.0.0-api.jar
```

`test -s` là tiện ích shell POSIX kiểm tra file có tồn tại và không rỗng; với PowerShell cần dùng `Test-Path` và `Get-Item`. Lệnh dành cho project đúng tên/version mẫu; khi thực tế khác hãy dùng file path được build tool báo.

### 17.2. Phân biệt layout bằng `jar tf`

```bash
jar tf build/libs/artifact-demo-1.0.0.jar |
    grep -Fx 'com/example/artifacts/api/Greeting.class'

jar tf build/libs/artifact-demo-1.0.0-api.jar |
    grep -Fx 'com/example/artifacts/api/Greeting.class'

jar tf build/libs/artifact-demo-1.0.0-exec.jar |
    grep -Fx 'BOOT-INF/classes/com/example/artifacts/ArtifactApplication.class'

jar tf build/libs/artifact-demo-1.0.0-exec.jar |
    grep -E '^BOOT-INF/lib/.*[.]jar$'
```

Cần xác minh cả **sự vắng mặt** của entry không thuộc variant. Ví dụ JAR API không nên có `com/example/artifacts/ArtifactApplication.class`. Phép tìm trên file không phải là phép chứng minh tính an toàn hoàn toàn; kiểm tra cả main class, dependency và cách chạy.

### 17.3. Chạy smoke test executable JAR

```bash
java -jar build/libs/artifact-demo-1.0.0-exec.jar
```

Dòng ứng dụng in:

```text
artifact=classifier-ok
```

Nếu mở plain/API JAR bằng `java -jar` và thấy lỗi manifest/main/dependency, đó thường là **artifact không được thiết kế để chạy**, không phải chứng cứ project code sai.

### 17.4. PowerShell kiểm tra không có wildcard gây nhầm

```powershell
$files = @(
    '.\build\libs\artifact-demo-1.0.0.jar',
    '.\build\libs\artifact-demo-1.0.0-exec.jar',
    '.\build\libs\artifact-demo-1.0.0-api.jar'
)

foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file)) {
        throw "Missing artifact: $file"
    }
    if ((Get-Item -LiteralPath $file).Length -eq 0) {
        throw "Empty artifact: $file"
    }
}
Write-Output 'Three artifacts found'
```

Đoạn này chỉ kiểm tra tên/tồn tại/kích thước; **không** xác nhận nội dung. Nên kết hợp `jar tf` và chạy đúng `-exec.jar`. Với Maven, đổi `build/libs` thành `target`. Trong pipeline, cần lưu checksum và liên kết rõ artifact nào đi đến image/deployment; đừng copy file đầu tiên khớp `*.jar`.

## 18. Reproducible builds, cache và version hóa output

Tạo ba artifact riêng chưa đủ nếu file cùng version có byte thay đổi bất thường hoặc bản release được ghi đè lặng lẽ.

- **Version là danh tính phát hành**, không chỉ là tên file. Không nên build lại nội dung khác rồi overwrite cùng release coordinate trong repository có chính sách immutable.
- **Classifier phân biệt mục đích**, không thay cho version: `exec` và `api` cùng version `1.0.0` không được dùng để phát hành hai bản code không đồng bộ.
- **Gradle task output phải không chồng lấn** để up-to-date checking, caching và parallel execution có ý nghĩa.
- **Maven attached artifact phải đúng tọa độ** và plugin execution phải có thứ tự, không chỉ dùng script rename sau build.
- **Kiểm tra archive reproducibility** khi dự án yêu cầu byte-for-byte deterministic artifacts; timestamps, file order, filtering và build metadata có thể ảnh hưởng checksum.

Nếu cần đối chiếu hai bản local bằng SHA-256:

```bash
sha256sum build/libs/artifact-demo-1.0.0.jar
sha256sum build/libs/artifact-demo-1.0.0-exec.jar
sha256sum build/libs/artifact-demo-1.0.0-api.jar
```

PowerShell dùng `Get-FileHash -Algorithm SHA256`. Ba artifact **nên có hash khác nhau** vì nội dung khác nhau; cùng một artifact giữa hai build reproducible có thể có hash trùng nếu mọi input/cấu hình đã được ổn định. Checksum xác minh bytes, không thay thế kiểm thử khả năng chạy hoặc nguồn phát hành đáng tin.

Đừng giải quyết file bị ghi đè bằng `clean` trong mọi vòng build: `clean` loại output cũ nhưng không sửa **hai task cùng sinh một file**. Hãy sửa classifier/path/task ownership trước.

## 19. Quy trình review cấu hình đóng gói khi thêm artifact mới

Khi có yêu cầu tạo thêm `-api.jar`, `-sources.jar` hay một executable khác, làm theo trình tự:

1. **Xác định người dùng artifact:** deployment, module phụ thuộc, IDE hay distribution.
2. **Xác định nội dung cần có:** app classes, runtime dependencies, tài liệu hay subset API.
3. **Chọn task/goal đúng loại:** Gradle `bootJar`/`jar`/custom `Jar`, Maven `spring-boot:repackage`/`maven-jar-plugin`/source plugin.
4. **Chọn classifier duy nhất:** `exec`, `api`, `sources`... theo ngữ nghĩa thực.
5. **Tính output paths thực:** base name, version, classifier, extension, directory, full filename overrides.
6. **Kiểm tra main vs attached/publication identities:** sẽ publish cái gì dưới coordinates nào?
7. **Tránh hai producers sở hữu một output path** hoặc publish cùng coordinates.
8. **Gắn task vào lifecycle có chủ đích:** `assemble`/`build` trong Gradle, `package`/`install` trong Maven.
9. **Build sạch một lần để đối chứng**, không dựa vào artifact cũ/cached ở thư mục output.
10. **Mở từng file bằng `jar tf`**, xác nhận đúng layout/class/resource và dependencies.
11. **Chạy `java -jar` cho executable variant**; nếu cần, thêm test riêng cho API JAR consumer.
12. **Kiểm tra publication local trước khi remote**, khớp file/coordinates và metadata.
13. **Cập nhật pipeline artifact selection** dùng tên/path cụ thể, không dùng `*.jar` mơ hồ.

### Checklist cuối bài

- [ ] Plain JAR và Boot executable JAR có **output paths khác nhau**.
- [ ] Mọi classifier được chọn có chủ đích, không trùng nhau ở cùng publication coordinates.
- [ ] Gradle `archiveFileName`/`destinationDirectory` không vô hiệu hóa classifier uniqueness.
- [ ] Maven `repackage` dùng classifier `exec` nếu muốn **giữ main JAR** cho library consumers.
- [ ] Maven `maven-jar-plugin` có execution riêng và classifier khi tạo attached API JAR.
- [ ] Không tạo execution `repackage` thứ hai vô tình khi dùng Spring Boot starter parent.
- [ ] Artifact API thực sự chỉ chứa public API cần thiết và không thiếu các class mà nó tham chiếu.
- [ ] Source/Javadoc classifier chỉ dùng cho đúng loại nội dung.
- [ ] Build lifecycle thật sự gọi các task/goal tạo đủ artifact dự kiến.
- [ ] Đã kiểm tra `jar tf`, Boot manifest, `BOOT-INF/lib` và chạy đúng `-exec.jar`.
- [ ] CI/CD lựa chọn artifact bằng path rõ ràng và gắn đúng với version/checksum.
- [ ] Đã xác minh install/deploy/publish identities, không chỉ kiểm tra có file trong `build/libs`/`target`.

**Ghi nhớ:** *Classifier giải quyết tên và định danh biến thể; task/goal quyết định nội dung; output path quyết định có ghi đè trên disk; publication coordinates quyết định có va chạm trong repository.* Với Spring Boot, **giữ plain JAR làm main artifact và đặt classifier `exec` cho executable JAR** là lựa chọn thực tế khi module vừa cung cấp thư viện vừa cần triển khai. Luôn kiểm tra bằng **build → liệt kê file → `jar tf` → chạy executable → thử resolve/publish** thay vì chỉ nhìn tên JAR.

## Tài liệu tham khảo

- [Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 Gradle Plugin — Publishing your Application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/publishing.html)
- [Spring Boot 3.3 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Apache Maven JAR Plugin — Creating an Additional Attached JAR Artifact](https://maven.apache.org/plugins/maven-jar-plugin/examples/attached-jar.html)
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Jar task and archive naming](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)