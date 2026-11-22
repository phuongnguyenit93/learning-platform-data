# Tái hiện lỗi đóng gói phổ biến rồi tìm nguyên nhân bằng log và nội dung archive

## Mục tiêu

Một ứng dụng Spring Boot có thể compile và unit test thành công nhưng artifact đem triển khai vẫn không chạy. Các nguyên nhân thường gặp gồm chọn nhầm plain JAR, bỏ sót runtime dependency, cấu hình sai main class, loại resource khỏi archive, Maven không chạy bước repackage hoặc Docker copy nhầm file build cũ.

Bài thực hành này tạo một ứng dụng nhỏ có endpoint HTTP, cố ý gây ra từng lỗi, sau đó dùng log, manifest, danh sách entry và dependency archive để tìm nguyên nhân. Mỗi lab đều có ba phần: tái hiện, thu thập bằng chứng và sửa lỗi.

Môi trường lab:

- Java 17 trở lên.
- Spring Boot Gradle plugin 3.3.13.
- Gradle Wrapper 8.x hoặc Gradle 7.5 trở lên phù hợp với Boot 3.3.13.
- JDK tools: java, javac và jar.
- Windows PowerShell hoặc Linux/macOS shell.
- Có thể dùng Maven 3.6.3 trở lên cho phần Maven.

Các version trên là baseline cho lab, không phải khuyến nghị dùng release cũ cho production. Khi áp dụng vào dự án thật, kiểm tra system requirements và migration guide của release đang được hỗ trợ.

Sau bài này, bạn có thể phân biệt plain JAR, executable Boot JAR và WAR; tái hiện lỗi do sai archive, thiếu dependency runtime, sai Start-Class và thiếu resource; dùng jar tf, manifest, BOOT-INF/lib, BOOT-INF/classes và class-loading log để định vị lỗi; kiểm tra Maven repackage và Docker copy đúng artifact.

---

## 1. Mô hình đóng gói cần hiểu trước

### 1.1 Từ source code đến artifact chạy được

~~~text
src/main/java + src/main/resources
                |
                v
         Compile / processResources
                |
                v
       classes + processed resources
                |
                v
       Resolve runtime dependencies
                |
                v
         Packaging task
          /           \
         v             v
     plain JAR     Boot executable JAR
         |             |
         v             v
  classes/resources  Boot loader
  at archive root    BOOT-INF/classes
  no nested libs     BOOT-INF/lib/*.jar
         |             |
         v             v
  java -cp with     java -jar app.jar
  dependencies
~~~

Compile thành công chỉ chứng minh compiler tìm thấy các type cần thiết trên compile classpath. Nó không chứng minh dependency có mặt trong runtime package. Tương tự, task tạo file JAR thành công không chứng minh đó là executable JAR mà môi trường triển khai cần.

### 1.2 Plain JAR và Boot executable JAR khác nhau

Với Spring Boot Gradle plugin và Java plugin:

- Task jar tạo JAR Java thông thường từ class và resource của project.
- Task bootJar tạo executable Spring Boot JAR, gồm Boot loader và runtime dependencies dưới dạng nested JAR.
- Khi hai task cùng được cấu hình, Gradle Boot plugin mặc định đặt classifier plain cho archive do task jar tạo để phân biệt hai file.
- Task assemble được cấu hình phụ thuộc bootJar; do đó build thường cũng tạo executable archive.

Plain JAR hữu ích khi publish library hoặc khi một runtime khác cung cấp dependencies. Nó không phải artifact thay thế tương đương cho executable Boot JAR.

### 1.3 Cấu trúc bên trong executable JAR

~~~text
packaging-lab.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/packaging/PackagingLabApplication.class
    │   ├── com/example/packaging/GreetingService.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-web-*.jar
    │   ├── spring-core-*.jar
    │   └── commons-lang3-*.jar
    ├── classpath.idx
    └── layers.idx
~~~

Hai vị trí quan trọng:

- BOOT-INF/classes chứa application classes và resources.
- BOOT-INF/lib chứa runtime dependency JARs.

META-INF/MANIFEST.MF chỉ ra launcher và application main class. classpath.idx có thể ghi thứ tự nested libraries; layers.idx mô tả các lớp archive phục vụ image/layer tooling.

### 1.4 Vì sao Java không tự load nested JAR?

Java classpath chuẩn tìm class trong thư mục hoặc JAR được liệt kê trực tiếp. Nó không tự mở các file JAR nằm bên trong một JAR khác. Spring Boot dùng launcher riêng để thiết lập classloader hiểu cấu trúc nested archive.

Vì vậy, đây là cách chạy executable Boot JAR:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

Lệnh dưới đây không tương đương:

~~~bash
java -cp build/libs/packaging-lab-1.0.0.jar com.example.packaging.PackagingLabApplication
~~~

Nó không tự thêm các JAR nằm trong BOOT-INF/lib vào classpath. Nếu chạy theo cách thứ hai, application có thể thiếu Spring classes hoặc dependency khác.

---

## 2. Tạo project lab có thể chạy được

### 2.1 Cấu trúc thư mục

Tạo project packaging-lab:

~~~text
packaging-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
└── src/
    └── main/
        ├── java/com/example/packaging/
        │   ├── PackagingLabApplication.java
        │   ├── GreetingService.java
        │   └── GreetingController.java
        └── resources/
            ├── application.properties
            └── lab/build-info.txt
~~~

Dùng Gradle Wrapper của project. Nếu tạo mới bằng Gradle, sinh wrapper một lần bằng Gradle đã cài rồi commit các file wrapper theo quy định của repository.

### 2.2 settings.gradle

~~~groovy
rootProject.name = 'packaging-lab'
~~~

Tên project tham gia vào tên archive mặc định.

### 2.3 build.gradle hoàn chỉnh

Ví dụ dùng Gradle native BOM support:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.commons:commons-lang3:3.14.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.packaging.PackagingLabApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

BOM quản lý version các dependency thuộc Spring Boot release train. Commons Lang được khai báo version tường minh trong ví dụ. implementation khiến dependency có mặt trên compile và runtime classpath, vì source code dùng class của thư viện này.

Boot Gradle plugin tạo task bootJar khi Java plugin được apply. Nếu dự án đã có chiến lược dependency management riêng, hãy giữ nhất quán với chiến lược của project; phần lab chỉ cần một cách quản lý version hoạt động rõ ràng.

### 2.4 Main application

File src/main/java/com/example/packaging/PackagingLabApplication.java:

~~~java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PackagingLabApplication.class, args);
    }
}
~~~

Đây là entry point của ứng dụng. Fully-qualified class name phải khớp package và tên class thực tế.

### 2.5 Service dùng một runtime dependency

File src/main/java/com/example/packaging/GreetingService.java:

~~~java
package com.example.packaging;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        String normalized = StringUtils.trimToNull(name);
        if (normalized == null) {
            normalized = "guest";
        }
        return "Hello, " + normalized + "!";
    }
}
~~~

StringUtils là class thuộc Commons Lang. Lab sẽ cố ý đổi dependency này từ implementation sang compileOnly để tạo lỗi runtime có thể tái hiện.

### 2.6 REST controller và resource

File src/main/java/com/example/packaging/GreetingController.java:

~~~java
package com.example.packaging;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(defaultValue = "Linh") String name) {
        return greetingService.greet(name);
    }

    @GetMapping("/build-info")
    public String buildInfo() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("lab/build-info.txt");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            ).trim();
        }
    }
}
~~~

File src/main/resources/application.properties:

~~~properties
server.port=8080
spring.application.name=packaging-lab
~~~

File src/main/resources/lab/build-info.txt:

~~~text
artifact=packaging-lab
~~~

Endpoint /api/build-info giúp kiểm tra resource có thật sự được đóng gói vào artifact hay không.

### 2.7 Build và chạy bản chuẩn

Linux/macOS:

~~~bash
./gradlew clean check bootJar
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean check bootJar
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

Khi ứng dụng khởi động thành công, log Spring Boot có dòng tương tự:

~~~text
:: Spring Boot :: (v3.3.13)
Started PackagingLabApplication in ... seconds
~~~

Thời gian startup và các log phụ thuộc môi trường nên không cố định.

Mở terminal khác và gọi endpoint:

~~~bash
curl "http://localhost:8080/api/greeting?name=Linh"
~~~

Response body:

~~~text
Hello, Linh!
~~~

Kiểm tra resource:

~~~bash
curl http://localhost:8080/api/build-info
~~~

Response body:

~~~text
artifact=packaging-lab
~~~

PowerShell có thể dùng:

~~~powershell
Invoke-RestMethod "http://localhost:8080/api/greeting?name=Linh"
Invoke-RestMethod "http://localhost:8080/api/build-info"
~~~

Dừng ứng dụng bằng Ctrl+C trước khi chạy các lab tiếp theo trên cùng port.

---

## 3. Bộ công cụ kiểm tra archive

### 3.1 Liệt kê entry

jar tf đọc danh sách entry trong JAR mà không cần giải nén:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar
~~~

Lọc các entry quan trọng trên Linux/macOS:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep -E 'META-INF/MANIFEST.MF|BOOT-INF/classes|BOOT-INF/lib'
~~~

Windows PowerShell:

~~~powershell
jar tf build/libs/packaging-lab-1.0.0.jar |
    Select-String 'META-INF/MANIFEST.MF|BOOT-INF/classes|BOOT-INF/lib'
~~~

Tìm application class:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'PackagingLabApplication.class'
~~~

Một executable Boot JAR có entry tương ứng dưới BOOT-INF/classes/com/example/packaging. Plain JAR thường đặt class ở root theo package path, ví dụ com/example/packaging/PackagingLabApplication.class.

### 3.2 Đọc manifest

Manifest nằm tại META-INF/MANIFEST.MF. Trên Linux/macOS có thể dùng:

~~~bash
unzip -p build/libs/packaging-lab-1.0.0.jar META-INF/MANIFEST.MF
~~~

Cách portable bằng JDK:

~~~bash
mkdir manifest-check
cd manifest-check
jar xf ../build/libs/packaging-lab-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

PowerShell đọc file sau khi giải nén:

~~~powershell
Get-Content META-INF/MANIFEST.MF
~~~

Manifest của executable Boot JAR thường có hai vai trò:

- Main-Class trỏ tới Spring Boot launcher.
- Start-Class trỏ tới class ứng dụng có method public static void main(String[]).

Tên launcher có thể thay đổi giữa các dòng Spring Boot. Hãy kiểm tra manifest của đúng artifact thay vì copy launcher class từ bài hướng dẫn khác.

### 3.3 Kiểm tra dependency được đóng gói

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/lib/'
~~~

Tìm Commons Lang:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/lib/commons-lang3'
~~~

Nếu outer JAR có nested entry BOOT-INF/lib/commons-lang3-3.14.0.jar, điều đó chứng minh file dependency được đóng gói. Để kiểm tra class bên trong nested JAR, cần trích xuất nested JAR rồi chạy jar tf trên file đó; jar tf outer archive không tự liệt kê nội dung bên trong từng nested JAR.

### 3.4 Kiểm tra checksum và file được triển khai

Linux/macOS:

~~~bash
sha256sum build/libs/packaging-lab-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash build/libs/packaging-lab-1.0.0.jar -Algorithm SHA256
~~~

Ghi lại checksum của artifact đã test. Sau khi copy vào Docker context, staging hoặc release folder, tính lại hash để xác nhận file không bị thay bằng artifact cũ hoặc file khác.

---

## 4. Lab 1 — Chọn nhầm plain JAR thay vì bootJar

### 4.1 Tái hiện

Build cả hai task:

~~~bash
./gradlew clean bootJar jar
~~~

Trong build/libs thường có hai file:

~~~text
packaging-lab-1.0.0.jar
packaging-lab-1.0.0-plain.jar
~~~

Tên thực tế phụ thuộc project name, version và classifier đã cấu hình. Theo convention mặc định của Spring Boot Gradle plugin, executable archive được tạo bởi bootJar; archive do jar tạo có classifier plain.

Cố ý chạy plain JAR:

~~~bash
java -jar build/libs/packaging-lab-1.0.0-plain.jar
~~~

Thông thường Java báo không có main manifest attribute hoặc không thể khởi chạy archive theo dạng executable. Plain JAR cũng không chứa Boot loader và toàn bộ runtime dependencies.

### 4.2 Thu thập bằng chứng

So sánh hai archive:

~~~bash
jar tf build/libs/packaging-lab-1.0.0-plain.jar
jar tf build/libs/packaging-lab-1.0.0.jar
~~~

Ở plain JAR, application class thường nằm ở root package path. Ở Boot JAR, application class nằm dưới BOOT-INF/classes và có các nested dependencies dưới BOOT-INF/lib.

Đọc manifest của cả hai. Manifest của Boot JAR có launcher và Start-Class phù hợp. Plain JAR có thể không có Main-Class cần thiết để chạy bằng java -jar.

### 4.3 Sửa lỗi

Chạy đúng file:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

Nếu pipeline cần một tên file ổn định, hãy cấu hình output/copy rõ ràng thay vì dùng wildcard có thể match cả plain và executable archive.

Ví dụ Docker build stage nên copy đúng artifact:

~~~dockerfile
COPY --from=build /workspace/build/libs/packaging-lab-1.0.0.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Không dùng wildcard cho thư mục có thể chứa cả plain JAR và executable JAR. Wildcard nhiều file cũng có thể làm Docker copy fail hoặc chọn sai nguồn tùy cách dùng.

### 4.4 Kết luận

Lỗi không nằm ở source code hoặc dependency resolution. Pipeline đã chọn sai loại artifact. Bằng chứng là classifier, archive layout, manifest và sự vắng mặt của Boot loader/nested libraries.

---

## 5. Lab 2 — Thiếu runtime dependency do dùng compileOnly

### 5.1 Tái hiện

Trong build.gradle, đổi:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.14.0'
~~~

thành:

~~~groovy
compileOnly 'org.apache.commons:commons-lang3:3.14.0'
~~~

compileOnly cho phép compiler nhìn thấy Commons Lang, nhưng dependency này không tự xuất hiện trong runtime classpath thông thường của ứng dụng. Code vẫn compile vì GreetingService có thể resolve StringUtils lúc compile.

Build lại:

~~~bash
./gradlew clean bootJar
~~~

Kiểm tra archive:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/lib/commons-lang3'
~~~

Không thấy nested JAR Commons Lang là bằng chứng dependency đã bị loại khỏi executable package.

Khởi động app có thể vẫn thành công vì class được tham chiếu trong method của service chỉ được resolve khi endpoint gọi method đó. Gọi:

~~~bash
curl "http://localhost:8080/api/greeting?name=Linh"
~~~

Khi request đi vào GreetingService.greet, JVM cần org.apache.commons.lang3.StringUtils và có thể ném NoClassDefFoundError. Log thường có cause hoặc message nhắc tới class này.

### 5.2 Tìm nguyên nhân bằng dependency graph

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

So sánh hai graph. Commons Lang có mặt ở compile classpath nhưng không có trong runtime classpath.

Có thể truy vấn cụ thể:

~~~bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

Nếu module không xuất hiện trong runtime graph, kiểm tra configuration và exclusions của dependency.

### 5.3 Sửa lỗi

Vì source code trực tiếp import và gọi Commons Lang ở runtime, dùng:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.14.0'
~~~

Nếu dependency là API mà module Java library cần expose cho compile classpath của consumer, cân nhắc api trong plugin java-library. Với application thông thường, implementation là lựa chọn phù hợp.

runtimeOnly chỉ phù hợp khi ứng dụng không cần type đó để compile nhưng cần thư viện khi chạy, ví dụ JDBC driver được load bởi framework. Không thay compileOnly bằng runtimeOnly nếu source code đang import class đó.

### 5.4 Biến thể Maven

Maven dependency scope provided hoặc test có thể khiến dependency không được đóng gói như runtime dependency của executable JAR. Kiểm tra dependency:tree -Dscope=runtime và cấu hình plugin packaging.

### 5.5 Kết luận

Compile success không chứng minh runtime package đủ dependency. Bằng chứng cần có là so sánh compile/runtime graph và xác nhận nested JAR tương ứng có hoặc không có trong BOOT-INF/lib.

---

## 6. Lab 3 — Sai Start-Class trong manifest

### 6.1 Tái hiện

Trong build.gradle, thêm cấu hình cố ý sai:

~~~groovy
tasks.named('bootJar') {
    manifest {
        attributes 'Start-Class': 'com.example.missing.BrokenApplication'
    }
}
~~~

Build:

~~~bash
./gradlew clean bootJar
~~~

Boot JAR vẫn có thể được tạo vì Start-Class là metadata do người cấu hình cung cấp. Khi chạy:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

launcher sẽ cố tải class không tồn tại. Log có thể báo ClassNotFoundException hoặc lỗi không tìm thấy main class, tùy launcher và phiên bản.

### 6.2 Tìm lỗi trong manifest và archive

Đọc manifest:

~~~bash
unzip -p build/libs/packaging-lab-1.0.0.jar META-INF/MANIFEST.MF
~~~

Tìm application class:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'PackagingLabApplication.class'
~~~

Bằng chứng sẽ cho thấy:

- Start-Class chỉ tới com.example.missing.BrokenApplication.
- Archive thực tế chứa com/example/packaging/PackagingLabApplication.class dưới BOOT-INF/classes.

Như vậy application class đã được compile và package; manifest trỏ nhầm entry point.

### 6.3 Sửa lỗi

Xóa override sai hoặc cấu hình đúng:

~~~groovy
springBoot {
    mainClass = 'com.example.packaging.PackagingLabApplication'
}
~~~

Không cấu hình đồng thời nhiều nơi với các giá trị khác nhau nếu không cần. Nếu dùng Kotlin, tên JVM main class có thể có hậu tố Kt, ví dụ ApplicationKt; hãy kiểm tra class file compiler tạo ra.

Build sạch và kiểm tra lại:

~~~bash
./gradlew clean bootJar
java -jar build/libs/packaging-lab-1.0.0.jar
~~~

### 6.4 Maven tương đương

Spring Boot Maven plugin quản lý Main-Class và Start-Class khi chạy goal repackage. Nếu cần đổi main class, cấu hình mainClass trên Spring Boot Maven plugin thay vì sửa manifest bằng plugin JAR thông thường.

### 6.5 Kết luận

Khi application class có trong archive nhưng launcher báo không tìm thấy main class, kiểm tra Start-Class trước khi sửa source set hoặc thêm dependency.

---

## 7. Lab 4 — Resource bị loại khỏi archive

### 7.1 Tái hiện

Trong build.gradle, thêm cấu hình cố ý loại resource:

~~~groovy
tasks.named('processResources') {
    exclude 'lab/**'
}
~~~

Build lại:

~~~bash
./gradlew clean bootJar
~~~

Kiểm tra:

~~~bash
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/classes/lab/build-info.txt'
~~~

Entry không còn trong archive. App vẫn có thể khởi động, nhưng request tới /api/build-info sẽ thất bại vì ClassPathResource không tìm được file.

### 7.2 Đọc lỗi và tìm nguyên nhân

Log có thể chứa FileNotFoundException hoặc exception được bọc từ thao tác mở resource. Đừng vội thêm thư viện; resource này thuộc source set của ứng dụng, không phải dependency JAR.

Kiểm tra file gốc:

~~~text
src/main/resources/lab/build-info.txt
~~~

Kiểm tra cấu hình processResources, sourceSets.main.resources và các exclude/include pattern. Một pattern rộng có thể loại resource cần thiết mà không làm compile thất bại.

### 7.3 Sửa lỗi

Xóa exclude không cần thiết:

~~~groovy
tasks.named('processResources') {
    // Giữ cấu hình mặc định để processResources copy src/main/resources.
}
~~~

Hoặc giới hạn exclude theo đúng file không cần đóng gói, tránh loại cả thư mục.

Build lại và xác minh:

~~~bash
./gradlew clean bootJar
jar tf build/libs/packaging-lab-1.0.0.jar |
  grep 'BOOT-INF/classes/lab/build-info.txt'
~~~

Chạy app và gọi endpoint. Body kỳ vọng:

~~~text
artifact=packaging-lab
~~~

### 7.4 Resource thường bị bỏ sót

- application.properties hoặc application.yml.
- File template, schema, SQL migration và static assets.
- META-INF/services/* cho ServiceLoader.
- Certificate/truststore được đóng gói theo thiết kế.
- File cấu hình được đọc qua classpath.
- Resource được generate ở task riêng nhưng task đó chưa nối vào processResources.

Khi resource do code generation tạo, cần khai báo output directory và task dependency rõ ràng để nó xuất hiện trong processed resources.

---

## 8. Lab 5 — Maven build JAR nhưng quên repackage

### 8.1 BOM không tự tạo executable archive

Một project có thể import spring-boot-dependencies để quản version dependency nhưng chưa cấu hình spring-boot-maven-plugin. Khi chạy:

~~~bash
./mvnw clean package
~~~

Maven vẫn có thể tạo JAR Java thông thường. Archive không có Boot loader và nested dependencies; java -jar có thể báo không có main manifest hoặc không chạy được như executable Boot JAR.

### 8.2 Cấu hình plugin và repackage goal

Nếu dùng corporate parent và chỉ import BOM, cấu hình plugin riêng:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.3.13</spring-boot.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

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
            <version>3.3.13</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Nếu dự án kế thừa spring-boot-starter-parent, parent đã cấu hình execution repackage; trong trường hợp đó thường chỉ cần khai báo plugin để kích hoạt plugin theo cấu hình parent.

### 8.3 Chạy đúng lifecycle

~~~bash
./mvnw clean package
~~~

Hoặc nếu cần gọi goal trực tiếp, phải bao gồm phase package:

~~~bash
./mvnw package spring-boot:repackage
~~~

Goal repackage hoạt động trên JAR/WAR được tạo từ phase package; gọi riêng goal mà chưa tạo source archive không phải quy trình đúng.

### 8.4 Kiểm tra kết quả

~~~bash
jar tf target/orders-service-1.0.0.jar
~~~

Executable archive cần có Boot loader, BOOT-INF/classes và BOOT-INF/lib. Kiểm tra manifest và chạy:

~~~bash
java -jar target/orders-service-1.0.0.jar
~~~

### 8.5 Kết luận

Maven BOM quản dependency versions. Spring Boot Maven plugin cùng repackage tạo executable archive. Một project có BOM đúng nhưng thiếu plugin execution vẫn có thể tạo plain JAR.

---

## 9. Lab 6 — Docker copy nhầm artifact hoặc file build cũ

### 9.1 Dockerfile sai do wildcard

Ví dụ dễ gây nhầm:

~~~dockerfile
COPY --from=build /workspace/build/libs/*.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Nếu thư mục output chứa cả executable và plain JAR, wildcard không thể hiện rõ file nào được chọn. Nếu có nhiều file match, Docker có thể từ chối copy hoặc hành vi copy không như mong muốn.

### 9.2 Copy chính xác artifact

Ví dụ multi-stage:

~~~dockerfile
FROM gradle:8-jdk17 AS build
WORKDIR /workspace
COPY . .
RUN gradle clean bootJar --no-daemon

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/packaging-lab-1.0.0.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là mẫu lab. Trong project thực tế, tên file có thể phụ thuộc project name/version; có thể dùng Gradle task riêng để copy executable artifact vào đường dẫn cố định, sau đó Docker copy đúng file đó.

Không copy file có classifier plain cho container chạy standalone.

### 9.3 Artifact cũ trong thư mục deploy

Một pipeline có thể build đúng JAR nhưng Docker stage hoặc release step lại copy artifact từ thư mục cache cũ. Cách điều tra:

1. Ghi build number, commit SHA và version vào build metadata.
2. Chạy clean trước khi tạo artifact release.
3. Liệt kê output directory và kiểm tra timestamp.
4. Tính SHA-256 trước và sau khi copy.
5. Kiểm tra Docker build context và đường dẫn COPY.
6. Ghi image digest sau khi build.
7. Promote đúng image digest đã chạy smoke test.

Tên file giống nhau không chứng minh nội dung giống nhau. Checksum và build metadata giúp xác nhận đúng artifact.

### 9.4 Kiểm tra bên trong image

Sau khi build image, có thể chạy container để kiểm tra file được copy:

~~~bash
docker run --rm --entrypoint sh packaging-lab:local -c "ls -l /app && sha256sum /app/app.jar"
~~~

Lệnh shell trong image phụ thuộc base image; một số image tối giản không có sh hoặc sha256sum. Nếu không có, kiểm tra file qua build stage hoặc dùng diagnostic image phù hợp.

---

## 10. Đọc log để khoanh vùng packaging failure

### 10.1 Log khi Java không chạy được archive

| Log/message | Hướng kiểm tra đầu tiên |
| --- | --- |
| no main manifest attribute | Đang chạy plain JAR hoặc manifest thiếu Main-Class |
| ClassNotFoundException cho application main class | Start-Class sai hoặc class không có trong archive |
| NoClassDefFoundError cho library | Runtime dependency thiếu hoặc classloader không nhìn thấy JAR |
| FileNotFoundException cho resource | Resource chưa được process/package hoặc tên path sai |
| UnsupportedClassVersionError | JRE chạy thấp hơn bytecode target |
| App chạy nhưng API trả 404 | Controller không được scan, route khác, profile/config khác hoặc artifact cũ |
| App chạy nhưng config không đúng | application.properties/yml thiếu, sai profile hoặc resource precedence |

Message chỉ là điểm bắt đầu. Cần đối chiếu với archive thực tế để phân biệt nguyên nhân.

### 10.2 Bật log Spring Boot

Có thể chạy với debug mode:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar --debug
~~~

--debug giúp in condition evaluation report để hiểu auto-configuration nào được áp dụng hoặc không áp dụng. Nó không tự sửa thiếu class, resource hay sai manifest.

Tăng log level có mục tiêu:

~~~bash
java -jar build/libs/packaging-lab-1.0.0.jar --logging.level.org.springframework=DEBUG
~~~

Không bật DEBUG cho toàn bộ package trong production lâu dài nếu log volume và dữ liệu nhạy cảm chưa được kiểm soát.

### 10.3 Gradle build log

Khi task không tạo file hoặc file không đúng:

~~~bash
./gradlew clean bootJar --info --stacktrace
~~~

Xem task bootJar có được thực thi không, processResources có chạy không, runtime configuration có resolve dependency không, task có bị skip/up-to-date do input/output sai không và output path/classifier thực tế là gì.

--info và --stacktrace giúp tìm nguyên nhân build. Chúng không thay cho kiểm tra nội dung archive.

### 10.4 Class-loading log của JVM

Khi nghi class được nạp từ JAR/version khác:

~~~bash
java -Xlog:class+load=info -jar build/libs/packaging-lab-1.0.0.jar
~~~

Lọc một class trên Linux/macOS:

~~~bash
java -Xlog:class+load=info -jar build/libs/packaging-lab-1.0.0.jar 2>&1 |
  grep 'org.apache.commons.lang3.StringUtils'
~~~

PowerShell:

~~~powershell
java -Xlog:class+load=info -jar build/libs/packaging-lab-1.0.0.jar 2>&1 |
    Select-String 'org.apache.commons.lang3.StringUtils'
~~~

Class-loading log cho biết class nào được nạp và source/location mà JVM ghi nhận. Nó hữu ích khi duplicate JAR hoặc classpath order làm runtime nạp bản không mong muốn.

### 10.5 Bảo vệ thông tin trong log

Không đưa password, token, secret, private repository credentials hoặc toàn bộ environment vào incident report. Khi dùng Maven debug hoặc Gradle diagnostic, review log trước khi chia sẻ ra ngoài nhóm có quyền truy cập.

---

## 11. Các lỗi archive nâng cao

### 11.1 Custom JAR task không lấy runtime dependencies

Một task Gradle tự tạo bằng Jar thường chỉ đóng gói source set output nếu không cấu hình thêm runtime dependencies. Đừng đổi tên task JAR thường thành bootJar rồi giả định nó có Boot loader.

Nếu mục tiêu là executable Spring Boot archive, dùng task BootJar do plugin cung cấp. Nếu mục tiêu là uber JAR theo định dạng khác, phải cấu hình và kiểm thử công cụ đóng gói tương ứng, bao gồm merge service descriptors và metadata.

### 11.2 Shaded/uber JAR làm mất service descriptor

Một số thư viện dùng Java SPI thông qua file META-INF/services. Khi dùng shading plugin để gộp classes từ nhiều JAR vào một archive, các file service descriptor có thể bị ghi đè thay vì merge.

Triệu chứng có thể là provider không được tìm thấy hoặc ServiceConfigurationError. Kiểm tra:

~~~bash
jar tf app.jar | grep 'META-INF/services'
~~~

Nếu dùng Shadow/Shade, cấu hình transformer/merge service files theo tài liệu plugin. Spring Boot executable JAR giữ dependency dưới dạng nested JAR, nên cơ chế xử lý khác với việc flatten mọi class vào một uber JAR.

### 11.3 Duplicate class trong nhiều dependency

Hai artifact khác tọa độ có thể chứa cùng fully-qualified class. Dependency resolution không phải lúc nào cũng báo conflict vì GAV khác nhau.

Dùng dependencies hoặc dependency:tree để hiểu graph; jar tf trên các JAR nghi ngờ để tìm class trùng; -Xlog:class+load=info để biết class runtime được nạp từ đâu; dependencyInsight để tìm module version selection.

Không kết luận dependency graph sạch nghĩa là không có duplicate class.

### 11.4 Nested JAR bị công cụ ngoài làm hỏng

Spring Boot launcher cần truy cập nested JAR theo định dạng archive được hỗ trợ. Nếu một script unzip rồi zip lại executable JAR, hoặc công cụ ký/repack nén lại entry theo cách không tương thích, nested library có thể không đọc được.

Với Boot executable JAR, nested JAR entries trong outer archive cần được lưu theo phương thức ZIP STORED để launcher có thể truy cập nội dung theo vị trí. Nội dung bên trong nested JAR vẫn có thể nén bình thường.

Không dùng zip/repack tool tùy tiện sau bước bootJar. Nếu cần ký hoặc biến đổi archive, dùng công cụ tương thích và chạy smoke test trên file cuối cùng sau biến đổi.

### 11.5 Classpath index và khác biệt giữa bootRun với java -jar

BOOT-INF/classpath.idx có thể chỉ định thứ tự các nested JAR. Spring Boot dùng index này khi chạy archive bằng java -jar; nó không được dùng khi chạy từ IDE hoặc qua Gradle bootRun.

Nếu cùng source chạy khác nhau giữa bootRun và java -jar, hãy so sánh runtime dependency graph, BOOT-INF/classpath.idx, duplicate class/version, thứ tự JAR được nạp, manifest và launcher.

Đừng xóa classpath index trước khi hiểu dependency order mà nó đang mô tả.

### 11.6 developmentOnly không mặc định được đưa vào production archive

Spring Boot Gradle plugin loại dependency trong configuration developmentOnly khỏi executable archive theo mặc định. Đây là chủ đích để công cụ phát triển như DevTools không bị đưa vào production.

Nếu ứng dụng thật sự cần một thư viện khi chạy production, không đặt nó nhầm vào developmentOnly. Chọn configuration phù hợp và xác minh nested libraries.

### 11.7 WAR và provided dependencies

Executable WAR có cấu trúc khác:

~~~text
app.war
├── META-INF/MANIFEST.MF
└── WEB-INF/
    ├── classes/
    ├── lib/
    └── lib-provided/
~~~

Dependencies cần cho embedded container nhưng được cung cấp khi deploy lên servlet container ngoài có thể được đặt ở WEB-INF/lib-provided theo cách cấu hình Spring Boot. Đọc kỹ sự khác nhau giữa providedRuntime và compileOnly; hai configuration không tương đương trong mọi trường hợp.

---

## 12. Quy trình điều tra từ triệu chứng đến nguyên nhân

Dùng quy trình này khi nhận được artifact không chạy:

1. **Ghi lại file thực sự được chạy.** Lấy đường dẫn đầy đủ, tên, kích thước, timestamp và SHA-256.
2. **Xác định loại archive.** Plain JAR, executable Boot JAR, executable WAR hay archive tùy chỉnh.
3. **Đọc manifest.** Kiểm tra Main-Class, Start-Class và các thuộc tính liên quan.
4. **Liệt kê archive entries.** Tìm application class, resources, Boot loader, BOOT-INF/lib hoặc WEB-INF/lib.
5. **Đối chiếu dependency graph.** So sánh compile/runtime graph và kiểm tra scope/exclusions.
6. **Đọc exception đầu tiên.** Phân biệt lỗi launcher, missing class, missing resource, class version hoặc application configuration.
7. **Bật log đúng mục tiêu.** Gradle --info/--stacktrace, Spring Boot --debug hoặc JVM class-loading log.
8. **Tái hiện với đúng command.** Dùng cùng Java version, artifact, environment và launch command như deployment.
9. **Sửa nguyên nhân nhỏ nhất.** Chỉnh task, scope, mainClass, resource include hoặc pipeline path theo bằng chứng.
10. **Build sạch và kiểm tra file cuối.** Chạy lại smoke test trên artifact/container sau mọi bước copy, ký hoặc repack.

~~~text
java -jar fails
      |
      v
Read first error + manifest
      |
      +-- no Main-Class / wrong launcher --> wrong archive or manifest
      |
      +-- wrong Start-Class -------------> mainClass configuration
      |
      +-- NoClassDefFoundError ----------> runtime dependency / nested JAR
      |
      +-- FileNotFoundException ---------> resource processing / archive entry
      |
      +-- UnsupportedClassVersionError --> JDK runtime vs bytecode target
      |
      +-- app starts, wrong behavior ----> config/profile/stale artifact
      |
      v
Inspect archive + resolved graph + exact deployed file
      |
      v
Fix, clean build, verify final artifact
~~~

---

## 13. Ma trận triệu chứng và bằng chứng

| Triệu chứng | Bằng chứng trong archive/log | Nguyên nhân thường gặp | Sửa |
| --- | --- | --- | --- |
| no main manifest attribute | Manifest thiếu entry point | Plain JAR hoặc chưa repackage | Chọn bootJar hoặc cấu hình Maven repackage |
| Boot launcher không tìm thấy app class | Start-Class không khớp entry class | Sai mainClass/manifest | Cấu hình FQCN đúng |
| NoClassDefFoundError | Dependency không có trong BOOT-INF/lib | compileOnly, provided hoặc exclusion | Sửa runtime scope |
| FileNotFoundException | Resource không có trong BOOT-INF/classes | processResources exclude/sourceSet sai | Sửa resource processing |
| App start được nhưng endpoint 404 | Controller/class hoặc route không có trong artifact | Source set, component scan, stale JAR | Kiểm tra class, package scan và checksum |
| App chạy local, lỗi trong container | Archive hoặc JRE trong image khác local | Copy nhầm file, base image khác | So hash, kiểm tra image và launch command |
| ServiceConfigurationError | META-INF/services thiếu provider | Shading ghi đè service descriptor | Merge service files |
| Class/version không mong muốn | Class-load log trỏ JAR khác dự kiến | Duplicate class hoặc classpath order | Loại duplicate và align dependencies |
| Nested JAR không mở được | Archive bị repack/compress lại | ZIP entry method không phù hợp | Tạo lại bằng Boot plugin và tránh repack tùy tiện |
| UnsupportedClassVersionError | Class file version cao hơn JRE | Build JDK mới, runtime JRE cũ | Đồng bộ Java toolchain và runtime |
| WAR thiếu embedded server | WEB-INF/lib-provided hoặc provided scope sai | Cấu hình WAR/container không phù hợp | Chọn đúng providedRuntime/deployment model |

---

## 14. Checklist kiểm tra artifact trước khi phát hành

### 14.1 Build

- [ ] Dùng Gradle/Maven Wrapper đã được review.
- [ ] Build từ trạng thái source sạch.
- [ ] Unit/integration tests pass.
- [ ] Đúng task tạo executable archive được chạy.
- [ ] Không có task custom ghi đè output archive ngoài dự kiến.

### 14.2 Archive

- [ ] Đã xác định rõ plain hay executable archive.
- [ ] Manifest có launcher và Start-Class đúng.
- [ ] Application classes nằm trong BOOT-INF/classes hoặc WEB-INF/classes phù hợp.
- [ ] Runtime dependencies có trong BOOT-INF/lib hoặc WEB-INF/lib.
- [ ] Resources quan trọng có trong archive.
- [ ] Service descriptors và metadata không bị mất.
- [ ] Archive không bị công cụ ngoài làm hỏng sau khi build.

### 14.3 Runtime

- [ ] Chạy đúng file bằng java -jar.
- [ ] Dùng đúng Java runtime version.
- [ ] Smoke test endpoint/health check thành công.
- [ ] Kiểm tra config/profile và resource load.
- [ ] Không dựa riêng vào bootRun hoặc IDE run configuration.

### 14.4 Release pipeline

- [ ] Docker copy đúng artifact path, không wildcard mơ hồ.
- [ ] SHA-256 trước/sau copy được đối chiếu khi cần.
- [ ] Container smoke test chạy trên image cuối cùng.
- [ ] Image digest được ghi lại.
- [ ] Promote đúng image đã test.
- [ ] Log release ghi commit, version, artifact và checksum.

---

## 15. Bài thực hành tổng hợp

### A. Plain JAR và executable JAR

1. Chạy ./gradlew clean bootJar jar.
2. Liệt kê file trong build/libs.
3. Chạy plain JAR bằng java -jar và ghi lại lỗi.
4. Chạy executable Boot JAR.
5. So sánh manifest và entry layout.
6. Giải thích vì sao plain JAR vẫn hữu ích khi publish library.

### B. Thiếu dependency runtime

1. Đổi Commons Lang từ implementation sang compileOnly.
2. Chạy clean bootJar.
3. Xác nhận Commons Lang không có trong BOOT-INF/lib.
4. Khởi động app và gọi endpoint greeting.
5. Ghi exception đầu tiên và class bị thiếu.
6. So sánh compileClasspath với runtimeClasspath.
7. Đổi lại implementation, build và chạy endpoint thành công.

### C. Sai main class

1. Override Start-Class thành class không tồn tại.
2. Build executable JAR.
3. Đọc manifest.
4. Tìm application class thật trong archive.
5. Sửa mainClass/Start-Class.
6. Build lại và chạy java -jar.

### D. Resource bị loại

1. Thêm exclude lab/** vào processResources.
2. Build JAR.
3. Kiểm tra resource entry.
4. Gọi endpoint /api/build-info.
5. Xem stack trace và tìm nguyên nhân.
6. Bỏ exclude, build lại và xác nhận response body.

### E. Maven repackage

1. Tạo Maven project dùng BOM import riêng.
2. Build JAR khi chưa có plugin execution.
3. Kiểm tra archive và thử java -jar.
4. Thêm spring-boot-maven-plugin với goal repackage.
5. Chạy clean package.
6. Kiểm tra Boot loader, BOOT-INF và manifest.
7. Giải thích khác biệt khi dùng starter parent.

### F. Docker artifact selection

1. Build cả plain và Boot JAR.
2. Viết Dockerfile cố ý dùng wildcard.
3. Xác định file được copy và kiểm tra hash.
4. Sửa Dockerfile để copy chính xác executable artifact.
5. Build image và chạy container smoke test.
6. Ghi image digest và checksum artifact.

### G. Incident report

Dùng mẫu:

~~~text
Project:
Commit/build number:
JDK build:
JDK runtime:
Gradle/Maven version:
Packaging task:
Expected artifact:
Actual artifact path:
Artifact size:
SHA-256:
Archive type:
Main-Class:
Start-Class:
Application class entry:
Required resource entries:
Runtime dependency entries:
Launch command:
First exception/message:
Relevant build log:
Root cause:
Code/build/pipeline change:
Clean build result:
java -jar result:
Container smoke-test result:
Image digest:
Remaining issue:
~~~

Phân biệt giả thuyết và bằng chứng. Không ghi “đã sửa” chỉ vì task build pass; cần chạy đúng artifact cuối cùng và xác minh hành vi cần thiết.

---

## 16. Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — Packaging Executable Archives (Gradle): https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Spring Boot 3.3 — Developing Your First Application, Creating an Executable JAR: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Boot — Nested JARs and archive layout: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Boot 3.3 — Efficient Deployments and extracting executable JAR: https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html
- Spring Boot — Maven Plugin, Packaging Executable Archives and repackage: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Gradle — Building Java & JVM Projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- Oracle JDK 17 — jar command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Oracle JDK 17 — java launcher and options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Docker — Dockerfile COPY reference: https://docs.docker.com/reference/dockerfile/#copy

**Ghi nhớ:** Đóng gói thành công không chỉ là có file JAR. Hãy xác định đúng loại archive, đọc manifest, xác minh application class/resource và runtime dependencies bên trong, rồi chạy đúng file bằng đúng Java command. Khi lỗi xảy ra, kết hợp stack trace với jar tf, dependency graph, class-loading log và checksum để tìm nguyên nhân trước khi sửa.
