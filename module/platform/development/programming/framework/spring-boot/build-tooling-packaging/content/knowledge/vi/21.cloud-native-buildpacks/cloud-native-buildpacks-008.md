# Chọn phiên bản JVM trong buildpack và kiểm tra tương thích với mã đã biên dịch

## 1. Mục tiêu

Với **Cloud Native Buildpacks (CNB)**, Spring Boot có thể tạo OCI image mà không cần người học tự viết Dockerfile. Gradle task `bootBuildImage` và Maven goal `spring-boot:build-image` gọi một builder chứa các buildpacks, ví dụ Paketo Java Buildpacks. Buildpacks phát hiện ứng dụng, chọn runtime Java, tạo các layers và export application image.

Cần tách hai giá trị:

- **Java compile target**: phiên bản Java của class files sinh ra bởi `javac` hoặc compiler khác. Ví dụ Java 17 tương ứng class-file major version **61**.
- **JVM của container**: runtime Java do buildpack chọn và đóng góp vào application image. Với Paketo, `BP_JVM_VERSION=17` yêu cầu dòng Java 17 khi **build image**, không phải khi chạy image đã có.

Quy tắc: runtime JVM phải hiểu class-file versions của các classes sẽ được tải, đồng thời phải đáp ứng Java version tối thiểu mà Spring Boot và dependencies yêu cầu. Image được tạo thành công **chưa chứng minh** ứng dụng chạy đúng với những tính năng chỉ tải thư viện khi có request.

Mục tiêu sau bài học:

1. Hiểu builder, buildpacks, build-time JDK, launch-time JRE, run image và app image.
2. Cấu hình Java 17 với Gradle Groovy/Kotlin DSL, Maven và Paketo `BP_JVM_VERSION`.
3. Kiểm bytecode bằng `javap -verbose` và hiểu Java 11/17/21 có major version lần lượt **55/61/65**.
4. Chạy ví dụ Spring Boot Java 17 và đọc JVM version **thực sự chạy trong container**.
5. Kiểm SBOM của image, không suy luận bản patch từ tên builder.
6. Chẩn đoán `UnsupportedClassVersionError` và phân biệt với `NoSuchMethodError`, thiếu native libraries hay lỗi image build.
7. Chọn cách sửa: compile về target thấp hơn một cách hợp lệ hoặc nâng JVM của image có kiểm thử.

**Mốc ví dụ:** Spring Boot 3.3.13, Java 17. Đây là phiên bản mẫu cố định, không phải tuyên bố bản mới nhất của bất kỳ phần mềm nào. Default JVM của Paketo và khả năng cung cấp bản patch thay đổi tùy builder và buildpack cụ thể.

## 2. Buildpacks mang JVM vào image thế nào?

~~~text
Spring Boot source / executable JAR
               │
               ▼
Spring Boot bootBuildImage / build-image
               │
               ▼
CNB Builder
  ├─ lifecycle và buildpacks
  ├─ detect Java application
  ├─ phân tích build-time configuration
  ├─ chọn JDK/JRE version theo buildpack policy
  ├─ tạo application + launch layers
  └─ export OCI image
               │
               ▼
Final application image
  ├─ run-image OS base
  ├─ JVM/JRE launch layer
  ├─ application + dependency layers
  └─ CNB launcher/process metadata
               │
               ▼
docker run / Kubernetes
~~~

**Builder** là image môi trường build có lifecycle và buildpacks. **Run image** cung cấp OS userspace, không nhất thiết tự chứa Java. Buildpacks có thể thêm JVM launch layer. **Application image** là sản phẩm cuối mang runtime và mã ứng dụng.

Paketo Java buildpacks thường dùng JDK trong build phase khi cần biên dịch và JRE trong runtime phase; `BP_JVM_TYPE=JRE` là default phổ biến. Nếu cần JDK ở runtime, `BP_JVM_TYPE=JDK` có thể được JVM provider hỗ trợ, nhưng không nên mang compiler vào production chỉ để dùng `javap`.

Có hai luồng:

- **Đóng image từ JAR đã build**: Spring Boot plugin chuẩn bị executable JAR/WAR. Bytecode đã được compile trước khi buildpack chọn JVM. Đổi `BP_JVM_VERSION` **không biên dịch lại class files**.
- **Đóng image từ source**: Pack CLI có thể chuyển cả Maven/Gradle project cho buildpacks, và buildpack chạy compiler bên trong builder. Trong trường hợp này, JVM build phase và cấu hình `--release` cũng phải phù hợp.

Bài học sử dụng luồng **JAR đã compile** để so sánh trực tiếp bytecode ↔ launch JVM.

## 3. Class-file major version và tính tương thích

Theo Java Virtual Machine Specification, mỗi `.class` có `major_version`. Một JVM không thể tải class có major version cao hơn mức nó hỗ trợ.

| Java SE | Major | Ví dụ kết luận |
| --- | ---: | --- |
| 8 | 52 | Java 8 class có thể được JVM 17 nạp nếu APIs phù hợp |
| 11 | 55 | Java 11 không nạp được class Java 17 |
| 17 | 61 | Mốc tối thiểu của Spring Boot 3.3 |
| 18 | 62 | JVM 17 không nạp được |
| 19 | 63 | JVM 17 không nạp được |
| 20 | 64 | JVM 17 không nạp được |
| 21 | 65 | JVM 17 không nạp được class Java 21 |
| 22 | 66 | Cần JVM hỗ trợ format Java 22 |
| 23 | 67 | Cần JVM hỗ trợ format Java 23 |

Ví dụ Java 21 bytecode (major 65) chạy trên Java 17 (chỉ hỗ trợ đến major 61) có thể báo:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
  (class file version 65.0), this version of the Java Runtime only
  recognizes class file versions up to 61.0
~~~

Thông điệp class name/dấu câu tùy JVM, nhưng cặp **65.0 và 61.0** có giá trị chẩn đoán. Không có JVM flag an toàn để ép Java 17 chấp nhận Java 21 class.

Java mới hơn có thể chạy class cũ hơn về **class-file format**. Tuy nhiên, Java module/reflection, TLS/crypto, native JNI, garbage collector flags hoặc các thư viện có thể thay đổi hành vi. Theo tài liệu System Requirements của **Spring Boot 3.3.13**, ứng dụng Spring Boot dòng này cần tối thiểu **Java 17** và công bố compatibility tới **Java 23**. Không dùng Java 11 chỉ vì main class cố target 11: dependency Spring Boot 3.3 cũng cần JVM 17+.

**Đừng chỉ xem main class:** executable Boot JAR chứa các thư viện tại `BOOT-INF/lib`. Một dependency có class major 65 có thể chỉ phát sinh lỗi khi một tính năng kích hoạt việc load class. Cần kiểm runtime classpath và integration tests.

## 4. `BP_JVM_VERSION` chọn JVM ở build time

Với **Paketo Java buildpacks**, đặt:

~~~text
BP_JVM_VERSION=17
~~~

để yêu cầu Java major 17 khi tạo image. Paketo chấp nhận major như `17` hoặc `17.*` và chọn một patch phù hợp trong những JVM distributions buildpack hỗ trợ. Không đoán trước exact patch chỉ từ biến này.

| Giá trị | Tác dụng | Không có tác dụng |
| --- | --- | --- |
| `BP_JVM_VERSION=17` | Yêu cầu JVM major 17 ở build time | Không chuyển Java 21 bytecode về Java 17 |
| `BP_JVM_VERSION=21` | Yêu cầu JVM major 21 | Không tự nâng compiler target của archive đã có |
| `BP_JVM_TYPE=JRE` | Chọn JRE launch layer nếu provider hỗ trợ | Không thay đổi `javac --release` |
| `BP_JVM_TYPE=JDK` | Chọn JDK launch layer khi cần | Không sửa lỗi dependency API mismatch |
| `JAVA_TOOL_OPTIONS` | JVM options lúc chạy | Không cài Java major khác |
| `BPL_*` | Các Paketo runtime options | Không thay bytecode |
| `BPE_*` | Tùy chỉnh launch environment khi build | Không phải compiler version selector |
| `JAVA_HOME` trên host | Java của process host khi được sử dụng | Không bảo đảm JVM trong CNB image giống host |

Một hiểu lầm rất phổ biến:

~~~bash
docker run -e BP_JVM_VERSION=21 local/jvm-demo:0.1.0
~~~

**không** biến image đã build Java 17 thành Java 21. `BP_JVM_VERSION` được đọc **khi build image**; phải cấu hình ở Gradle/Maven/Pack rồi build lại.

**Default Java major có thể thay đổi:** đừng tin câu “Paketo luôn chọn Java 17” hoặc “builder:latest luôn chọn 21”. Spring Boot plugin có inference theo compile target trong default builder nhưng custom builder vẫn có thể khác. Cấu hình rõ, đọc logs, kiểm SBOM và runtime.

Nếu buildpack báo không tìm thấy JVM phù hợp, kiểm builder/buildpack JVM provider, CPU architecture, OS stack, JDK/JRE availability, proxy/network và registry. Không tự đổi source code trước khi biết vấn đề là **không thể cung cấp Java distribution**.

## 5. Spring Boot plugin có thể suy ra target Java

Spring Boot **3.3 Gradle Plugin** tài liệu hóa rằng `bootBuildImage` phát hiện Java target compatibility qua `JavaPlugin.targetCompatibility` và khi dùng default Paketo builder sẽ chỉ thị buildpacks cài Java tương ứng. Spring Boot **3.3 Maven Plugin** phát hiện từ compiler plugin configuration hoặc `maven.compiler.target`.

Inference là thuận tiện nhưng không thay cho QA:

- Java compiler task có thể đặt `options.release` khác với một target property.
- Module ứng dụng và một module thư viện có thể target khác nhau.
- Transitive dependency được biên dịch bằng Java mới hơn.
- Builder custom có JVM provider hoặc defaults khác.
- `BP_JVM_VERSION` đã được người dùng override trực tiếp.
- Gradle daemon chạy JDK khác JDK thực sự dùng compile.

Vì vậy ví dụ dùng **cả** `--release 17` và `BP_JVM_VERSION=17`; dù inference default làm được, cấu hình tường minh giúp giải thích và kiểm tra.

| Compile target | Image JVM | Kết luận |
| --- | --- | --- |
| Java 17, major 61 | 17 | Phù hợp version, cần smoke/integration tests |
| Java 17, major 61 | 21 | Có thể chạy bytecode 17; kiểm compatibility đầy đủ |
| Java 21, major 65 | 17 | Không phù hợp; có thể fail trong image build hoặc lúc load class |
| Spring Boot 3.3 + major 61 | 11 | Không hỗ trợ, Spring Boot 3.3 yêu cầu Java 17 tối thiểu |
| Main class major 61, dependency class major 65 | 17 | Có nguy cơ lỗi khi load dependency đó |

Một builder có thể bắt mismatch ngay khi build, hoặc image vẫn được tạo rồi runtime fail. Không khẳng định mọi lỗi đều xảy ra ở đúng một giai đoạn.

## 6. Project Java 17 để kiểm chính JVM runtime

Project `jvm-compat-demo` chứa REST API đơn giản:

~~~text
jvm-compat-demo/
├── settings.gradle             # nếu dùng Groovy DSL
├── build.gradle
│   hoặc settings.gradle.kts    # nếu dùng Kotlin DSL
│   hoặc build.gradle.kts
├── gradlew                     # Gradle wrapper phải được tạo/provision
├── gradle/wrapper/
└── src/
    ├── main/java/com/example/cnb/
    │   ├── JvmCompatApplication.java
    │   └── VersionController.java
    └── test/java/com/example/cnb/
        └── VersionControllerTest.java
~~~

**Main class** — `src/main/java/com/example/cnb/JvmCompatApplication.java`:

~~~java
package com.example.cnb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JvmCompatApplication {

    public static void main(String[] args) {
        SpringApplication.run(JvmCompatApplication.class, args);
    }
}
~~~

**Controller** — `src/main/java/com/example/cnb/VersionController.java`:

~~~java
package com.example.cnb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {

    @GetMapping("/hello")
    public String hello() {
        return "hello-from-java";
    }

    @GetMapping("/runtime-major")
    public String runtimeMajor() {
        return Integer.toString(Runtime.version().feature());
    }

    @GetMapping("/runtime-version")
    public String runtimeVersion() {
        return System.getProperty("java.version");
    }
}
~~~

`Runtime.version().feature()` là API Java SE 9+ và lấy **major version của JVM đang chạy request**, không đọc build.gradle hoặc biến môi trường trên laptop.

Khi ứng dụng chạy trong image Java 17, body của `GET /runtime-major` phải là:

~~~text
17
~~~

`/runtime-version` trả patch version thật như chuỗi Java system property; không hardcode bản patch cố định khi chưa kiểm image.

**JUnit test** — `src/test/java/com/example/cnb/VersionControllerTest.java`:

~~~java
package com.example.cnb;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VersionControllerTest {

    @Test
    void helloIsStable() {
        VersionController controller = new VersionController();
        assertEquals("hello-from-java", controller.hello());
    }

    @Test
    void supportedJvmForBoot33() {
        VersionController controller = new VersionController();
        int major = Integer.parseInt(controller.runtimeMajor());
        assertTrue(major >= 17);
    }
}
~~~

Test này chạy trong JVM của **test task**, **không** đo Java runtime của container. Image runtime phải được smoke-test riêng. Trong môi trường production, có thể giới hạn quyền truy cập endpoint thông tin JVM hoặc thay bằng internal metrics/logging.

## 7. Gradle Groovy DSL: compile 17 và buildpack JVM 17

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'jvm-compat-demo'
~~~

Tệp `build.gradle` đầy đủ:

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

tasks.withType(JavaCompile).configureEach {
    options.release = 17
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

tasks.named('bootBuildImage') {
    imageName = 'local/jvm-compat-demo:0.1.0'
    environment['BP_JVM_VERSION'] = '17'
}
~~~

Giải thích:

- `java.toolchain.languageVersion` chọn compiler/test Java toolchain.
- `options.release=17` áp dụng `javac --release 17`, giới hạn Java APIs và class-file target về major 61.
- `bootBuildImage.environment` đặt **build-time environment của builder**, để Paketo chọn launch JVM Java 17.
- `imageName` chỉ định local Docker image tag để kiểm tra, không tự publish registry.
- `spring-boot-starter-web` cung cấp embedded server, test dependency cho JUnit 5.

Lệnh từ project có Gradle wrapper hợp lệ:

~~~bash
./gradlew --version
./gradlew clean test bootJar
./gradlew bootBuildImage
~~~

Docker daemon/context phải hoạt động, network có thể tải builder/run images, JVM distributions và dependencies. Trên Windows PowerShell dùng `.\gradlew.bat`. Build script không tự sinh Gradle wrapper.

Theo docs Spring Boot 3.3, có thể đặt environment cho một invocation trên CLI:

~~~bash
./gradlew bootBuildImage --environment BP_JVM_VERSION=17
~~~

Đừng nhầm với chạy:

~~~bash
./gradlew compileJava --environment BP_JVM_VERSION=17
~~~

Lệnh sau không phải cách cấu hình compiler target và không có ý nghĩa cho task compileJava. Muốn đổi bytecode target, sửa toolchain/`options.release` đúng task.

**Custom builder fragment**, chỉ dành cho tổ chức đã có images thực tế:

~~~groovy
tasks.named('bootBuildImage') {
    builder = 'registry.example/builder/java:approved'
    runImage = 'registry.example/run/base:approved'
}
~~~

`registry.example` là placeholder minh họa; không phải registry đã được xác minh. Không chọn run image không tương thích CNB stack/ABI chỉ để giảm kích thước.

## 8. Gradle Kotlin DSL: cú pháp tương đương

Tệp `settings.gradle.kts`:

~~~kotlin
rootProject.name = "jvm-compat-demo"
~~~

Tệp `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

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

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
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

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("local/jvm-compat-demo:0.1.0")
    environment.put("BP_JVM_VERSION", "17")
}
~~~

`BootBuildImage` là type do Spring Boot Gradle Plugin cung cấp. `environment` là `MapProperty<String,String>` nên Kotlin dùng `environment.put`; đây là cú pháp Spring Boot 3.3 đã tài liệu hóa. `options.release.set(17)` là typed property của Gradle JavaCompile.

**Chỉ chọn Groovy hoặc Kotlin DSL** cho một project, dùng cùng các Java source/test ở mục 6 và cùng lệnh Gradle. Kotlin DSL không bắt buộc ứng dụng chính viết Kotlin.

Nếu project thực sự dùng Kotlin application source hoặc một module được biên dịch bằng Kotlin, phải kiểm thêm Kotlin compiler `jvmTarget`; `JavaCompile.options.release` không tự bảo đảm Kotlin classes cũng target Java 17.

## 9. Maven: maven.compiler.release và build-image

Một project Maven **thay thế Gradle** có thể dùng cùng Java sources ở mục 6 và POM đầy đủ:

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
    <artifactId>jvm-compat-demo</artifactId>
    <version>0.1.0</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
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
                <configuration>
                    <image>
                        <name>local/jvm-compat-demo:0.1.0</name>
                        <env>
                            <BP_JVM_VERSION>17</BP_JVM_VERSION>
                        </env>
                    </image>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`java.version` và `maven.compiler.release` là compiler/build settings. `BP_JVM_VERSION` trong `spring-boot-maven-plugin/image/env` là buildpack setting. Không đưa nó vào dependencies hoặc coi nó là `JAVA_HOME`.

Build:

~~~bash
mvn -version
mvn clean verify
mvn spring-boot:build-image
~~~

Theo Spring Boot 3.3 docs, `build-image` phù hợp CLI và fork lifecycle để đảm bảo package xảy ra; `build-image-no-fork` dùng khi bind vào execution trong lifecycle nhằm tránh chạy lặp lifecycle. Đừng tự cấu hình hai goals có khả năng double-build mà không hiểu plugin execution.

Kiểm effective POM và compiled classes:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn clean compile
javap -verbose -classpath target/classes com.example.cnb.JvmCompatApplication
~~~

Kỳ vọng thấy `major version: 61` khi compiler release 17 áp dụng đúng. Maven Compiler Plugin cần JDK đủ hỗ trợ `--release 17`. Nếu Maven chạy dưới JDK 11 và không có toolchain JDK mới, compile release 17 thất bại dù image builder có Java 17 — đó là **lỗi compile toolchain**, không phải lựa chọn launch JVM.

Nếu dùng Maven wrapper, đảm bảo wrapper đã được provision; lệnh `./mvnw` trên Unix hoặc `.\mvnw.cmd` trên Windows, tùy project.

## 10. Toolchain, release, sourceCompatibility và JAVA_HOME

Có thể tồn tại nhiều JVM trong một build:

| Nơi đo | Ý nghĩa |
| --- | --- |
| `./gradlew --version` | Java mà Gradle daemon/launcher đang chạy |
| `mvn -version` | Java đang chạy Maven |
| Gradle `java.toolchain` | JDK của các Java tasks |
| `options.release` / `maven.compiler.release` | Java language/API/bytecode target |
| `sourceCompatibility` | Language level của source |
| `targetCompatibility` | Bytecode target nhưng không giới hạn API đủ chặt |
| `BP_JVM_VERSION` | JVM buildpack sẽ chọn khi dựng OCI image |
| `Runtime.version().feature()` | Java major của process thực sự chạy application |

Ví dụ Gradle được khuyến nghị:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`--release` ràng buộc compiler vào public APIs của Java release đó, không chỉ syntax/bytecode target. Nếu compile bằng JDK 21 và chỉ đặt `targetCompatibility=17`, source đôi khi vẫn tham chiếu API chỉ tồn tại ở JDK 21; khi chạy Java 17 có thể `NoSuchMethodError` hoặc missing class/API. `--release 17` giảm rủi ro bằng cách kiểm tra APIs lúc compile.

Một cấu hình nâng cao có thể dùng toolchain JDK 21 nhưng `options.release=17` để tạo major 61; khi đó Java 21 language features/API mới không thể được sử dụng dưới contract release 17. Ngược lại, toolchain 17 không compile được `--release 21`.

Không dùng global `JAVA_HOME` hoặc `System.getenv("JAVA_HOME")` để tự suy ra JVM trong Paketo image. Host JDK, build compiler và launch JRE có nhiệm vụ khác nhau.

## 11. Kiểm bytecode trước khi tạo image

### 11.1. Gradle

~~~bash
./gradlew clean compileJava
javap -verbose -classpath build/classes/java/main com.example.cnb.JvmCompatApplication
javap -verbose -classpath build/classes/java/main com.example.cnb.VersionController
~~~

Trong output tìm:

~~~text
major version: 61
~~~

Trên Windows PowerShell:

~~~powershell
javap -verbose -classpath build/classes/java/main com.example.cnb.JvmCompatApplication |
    Select-String "major version"
~~~

### 11.2. Maven

~~~bash
mvn clean compile
javap -verbose -classpath target/classes com.example.cnb.JvmCompatApplication
~~~

Cũng phải có major 61 nếu target 17 đang có hiệu lực. Nếu project multi-module thì đổi `-classpath` theo module tương ứng, ví dụ `api/target/classes`.

### 11.3. Kiểm executable Boot archive

Gradle:

~~~bash
./gradlew bootJar
jar tf build/libs/jvm-compat-demo-0.1.0.jar
~~~

Bạn cần tìm entries:

~~~text
BOOT-INF/classes/com/example/cnb/JvmCompatApplication.class
BOOT-INF/classes/com/example/cnb/VersionController.class
BOOT-INF/lib/
~~~

`jar tf` chỉ liệt kê archive entries, **không in class-file major**. Đọc `javap` trên build classes, hoặc giải nén archive vào thư mục tách biệt an toàn để kiểm class. Nếu file có launch script đứng đầu (fully executable JAR), một số `jar` tools có thể không đọc/giải nén đúng; tạo standard JAR cho inspection.

### 11.4. Kiểm dependency class files

Một main class major 61 **không chứng minh mọi runtime dependency đều major 61 hoặc thấp hơn**. Nếu một transitive library mang class Java 21/major 65, lỗi có thể chỉ xuất hiện khi request kích hoạt thư viện đó.

Đọc runtimeClasspath/dependency tree và supported Java matrix của dependencies. Dùng bytecode scanner phù hợp để kiểm các runtime libraries quan trọng. Lưu ý **multi-release JAR** có thể chứa version-specific classes tại `META-INF/versions`; không kết luận mọi class major 65 bên trong một multi-release JAR đều được Java 17 nạp. Phải hiểu lựa chọn entry ở runtime hoặc kiểm bằng integration tests.

## 12. Kiểm JVM thực sự nằm trong image

Sau khi tạo image bằng Gradle hoặc Maven:

~~~bash
docker image ls local/jvm-compat-demo
docker image inspect local/jvm-compat-demo:0.1.0
~~~

`docker image inspect` cho biết metadata/architecture/config/labels; không có bảo đảm mọi builder đều ghi một field cố định tên `java.version`.

Chạy image:

~~~bash
docker run --rm -p 18080:8080 local/jvm-compat-demo:0.1.0
~~~

Trong terminal khác:

~~~bash
curl -fsS http://localhost:18080/hello
curl -fsS http://localhost:18080/runtime-major
curl -fsS http://localhost:18080/runtime-version
~~~

Hai bodies đầu **lần lượt** là:

~~~text
hello-from-java
17
~~~

Nếu buildpack thực sự chọn Java 17. Đây là hai HTTP requests riêng, không phải một response. `/runtime-version` chứa patch version thực, không nên hardcode giá trị 17.0.x trước khi chạy image.

Nếu major trả 21 dù compiled application major 61, đó không nhất thiết là Java exception: Java 21 thường nạp được class Java 17. Nhưng nếu release policy yêu cầu đúng Java 17, image chưa đúng policy. Nếu runtime trả 11 thì có mismatch nghiêm trọng đối với Spring Boot 3.3.

### 12.1. Kiểm SBOM

Paketo buildpacks tạo Software Bill of Materials cho JVM/JRE và các dependencies. Với Pack CLI đã cài:

~~~bash
pack sbom download local/jvm-compat-demo:0.1.0
~~~

Đọc các SBOM files để xác định exact JRE version, vendor, checksum, packages và architecture. Định dạng/thư mục download phụ thuộc Pack CLI/SBOM format; dùng:

~~~bash
pack sbom download --help
~~~

`pack inspect-image local/jvm-compat-demo:0.1.0` giúp đọc builder/run-image/buildpacks/process metadata, nhưng không thay thế actual JRE version trong SBOM và kiểm runtime.

### 12.2. Đừng bắt runtime JRE có javac hoặc javap

Paketo default thường dùng JRE launch layer; nó có thể không mang compiler hoặc `javap`. Thiếu `javac` trong runtime image không phải lỗi. Kiểm bytecode trên build machine/JDK, còn image JVM major qua endpoint/sbom. Không đổi `BP_JVM_TYPE=JDK` chỉ để dùng một công cụ debug không cần thiết ở production.

### 12.3. Chạy ở đúng deployment digest

CI có thể xây image tag `local/jvm-compat-demo:0.1.0` nhưng production đã pull tag khác. Để chốt QA phải đối chiếu image digest của bản publish/deployed, không chỉ kết quả local. Quản lý SBOM, digest và approved builder/run-image inputs theo chính sách của tổ chức.

## 13. Thí nghiệm cố tình tạo `UnsupportedClassVersionError`

Dùng một file Java SE hoàn chỉnh riêng `VersionProbe.java`, không liên quan Spring Boot:

~~~java
public final class VersionProbe {

    public static void main(String[] args) {
        System.out.println("CLASS_OK");
    }
}
~~~

**Thí nghiệm A, JDK 17:**

~~~bash
javac --release 17 VersionProbe.java
javap -verbose VersionProbe
java VersionProbe
~~~

Kỳ vọng `major version: 61` từ `javap` và stdout khi chạy:

~~~text
CLASS_OK
~~~

**Thí nghiệm B, có JDK 21 và runtime Java 17 riêng:**

~~~bash
javac --release 21 VersionProbe.java
javap -verbose VersionProbe
/path/to/java17/bin/java VersionProbe
~~~

Kỳ vọng `major version: 65` và Java 17 **từ chối class** với `UnsupportedClassVersionError`. Đường dẫn `/path/to/java17` là **placeholder phải thay bằng JRE 17 thật**. Nếu `java` của PATH vẫn là JDK 21, chương trình có thể chạy và thí nghiệm không chứng minh lỗi.

Không in `CLASS_OK` ở lần chạy sai: main class không được nạp. Đây là thử nghiệm để hiểu phiên bản bytecode, không nên cố tình đưa major 65 vào production image Java 17.

**Sửa theo một trong hai hướng:**

1. Compile lại bằng `--release 17` sau khi source/APIs đã tương thích với Java 17; giữ Paketo JVM 17.
2. Nếu ứng dụng thật cần Java 21, nâng compiler target và `BP_JVM_VERSION` lên 21, kiểm Spring Boot/dependency support, build lại image mới và chạy đủ tests.

Đừng sử dụng `--add-opens` hay xóa Gradle caches như một giải pháp cho class-file major cao hơn JVM.

## 14. Khi JVM cao hơn bytecode

Kịch bản:

~~~text
Application compiled target 17 → class major 61
BP_JVM_VERSION=21 → runtime major 21
JVM đọc class-file major 61 thành công
~~~

Chưa đủ để tuyên bố ứng dụng hoàn toàn tương thích. Cần đánh giá framework version, JDK APIs, reflection/modules, serialization/TLS, native libraries, runtime JVM flags, JFR/profiler và các dependency agents. Đây là **runtime platform upgrade**, không phải chỉ chỉnh một con số.

Quy trình nâng an toàn:

1. Đọc compatibility matrix của Spring Boot và libraries đang dùng.
2. Kiểm builder/JVM provider cung cấp Java 21 trên OS/architecture đích.
3. Build tag/digest mới, không ghi đè release artifact chưa QA.
4. Chạy unit, integration, contract và smoke tests; kiểm security scanning.
5. Đọc SBOM JRE patch/vendor và endpoint runtime major/version.
6. Lưu provenance/digest, có rollback plan.

Nếu chỉ đổi `BP_JVM_VERSION` từ 17 sang 21 trên project `--release 17`, application bytecode vẫn major 61. Nếu muốn dùng language features/Java 21 APIs, đó là **thay đổi compile target riêng** cần tương thích source và dependencies.

## 15. Phân biệt BP_, BPL_, BPE_ và JAVA_TOOL_OPTIONS

| Biến | Vai trò phổ biến |
| --- | --- |
| `BP_JVM_VERSION` | Chọn JVM trong quá trình tạo image |
| `BP_JVM_TYPE` | Chọn JDK hoặc JRE launch layer |
| `BP_JVM_JLINK_ENABLED` | Tạo JRE rút gọn với jlink khi buildpack hỗ trợ |
| `BPL_*` | Runtime features/diagnostics do Paketo buildpack xử lý |
| `BPE_*` | Thiết lập thay đổi launch environment từ build time |
| `JAVA_TOOL_OPTIONS` | Flags cho JVM process khi chạy |
| `SPRING_PROFILES_ACTIVE` | Spring Boot profile, không phải Java version |

Ví dụ runtime flag (không thay Java version):

~~~bash
docker run --rm \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70.0" \
  -p 18080:8080 \
  local/jvm-compat-demo:0.1.0
~~~

Paketo có thể đã tạo `JAVA_TOOL_OPTIONS` mặc định. Override toàn bộ từ Docker CLI có thể loại mất settings cần thiết; đọc buildpack/runtime docs và test trước khi dùng.

Ví dụ Gradle **fragment tùy chọn** minh họa cách thêm launch env flags:

~~~groovy
tasks.named('bootBuildImage') {
    environment['BPE_DELIM_JAVA_TOOL_OPTIONS'] = ' '
    environment['BPE_APPEND_JAVA_TOOL_OPTIONS'] =
        '-XX:+HeapDumpOnOutOfMemoryError'
}
~~~

Không áp dụng fragment này để sửa `UnsupportedClassVersionError`. Heap dump có thể chứa dữ liệu nhạy cảm, cần policy storage/permissions.

## 16. Các lỗi và chẩn đoán thực hành

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedClassVersionError 65.0 / 61.0` | Java 21 bytecode trên Java 17 JVM | Compile `--release 17` hoặc image JVM 21 và test |
| `UnsupportedClassVersionError 61.0 / 55.0` | Spring Boot Java 17 trên Java 11 | Spring Boot 3.3 yêu cầu Java 17+, thay runtime |
| Buildpack không có JVM 17 | JVM provider/builder/stack/arch không đáp ứng | Xem buildpack metadata, approved builder/mirror |
| `docker run -e BP_JVM_VERSION=21` không đổi JVM | Đặt build-time variable ở runtime | Build lại image với đúng BP_JVM_VERSION |
| Host `java -version` là 21, image là 17 | Host/launch JVM độc lập | Đó có thể đúng; kiểm runtime trong image |
| Gradle `bootBuildImage` không tồn tại | Spring Boot/Java plugin chưa apply ở module | Xem `./gradlew tasks --all`, plugin/module paths |
| Maven `build-image` thất bại | Maven goal, Docker engine, builder/network lỗi | Xem logs và effective POM |
| `javap` app class 61, dependency class 65 | Transitive/generated class Java 21 | Xem runtimeClasspath và stack trace class name |
| `NoSuchMethodError` hoặc missing JDK API | Compile không giới hạn API, binary dependency mismatch | Dùng `--release`, kiểm library versions |
| `NoClassDefFoundError` nhưng major đúng | Thiếu dependency hoặc class initialization lỗi | Kiểm Boot JAR/stack trace; không tự đổi JVM |
| `UnsatisfiedLinkError` | Native ABI/OS/arch/loader không khớp | Kiểm run image/native library và platform |
| Image major 17 nhưng patch JRE khác dự kiến | Buildpack/JVM vendor update | Đọc SBOM, pin approved inputs |
| Pack CLI thiếu hoặc không thấy SBOM | Pack version/image/registry/context | Xem `pack --version`, `pack sbom download --help` |
| Container chạy nhưng không gọi được endpoint | Port mapping/server config sai | Xem logs, `-p` và `server.port` |
| CI test Java 21 nhưng image chạy Java 17 | Test toolchain không đúng môi trường release | Thêm image-level tests và align policy |

**Chẩn đoán theo thứ tự:** ghi class name + stack trace → xác định bytecode major của class lỗi → đo runtime major thực tế → đối chiếu compile target → kiểm buildpack version/provider → kiểm dependencies → build và chạy lại image mới. Không xóa mọi caches chỉ vì một class major mismatch.

### 16.1. Vì sao một endpoint chạy không chứng minh mọi thư viện tương thích?

Java lazy-loading cho phép một số classes được nạp muộn. Ví dụ ứng dụng start bình thường, `/hello` trả HTTP 200, nhưng một thư viện ở chức năng báo cáo dùng major 65 và chỉ được load ở request `/report`. Cần integration tests cho những đường sử dụng chính, đặc biệt codegen, plugins, agents, JNI và transitive dependencies.

### 16.2. Multi-release JAR

Một số JAR có classes ở `META-INF/versions/9`, `META-INF/versions/17` hoặc `META-INF/versions/21`. JVM chọn version-specific entry phù hợp theo quy tắc multi-release JAR. Vì vậy không kết luận “mọi JAR chứa một class major 65 đều chắc chắn lỗi trên Java 17” nếu class đó chỉ nằm trong version-specific entry cho Java 21. Cần scanner có nhận thức multi-release hoặc runtime tests.

### 16.3. Native image khác JVM image

GraalVM native-image buildpacks tạo native executable; không có JVM class loader đọc `.class` khi application chạy theo cùng cơ chế. Nếu chuyển sang native image, phải nghiên cứu GraalVM/native toolchain và buildpack riêng, không áp đặt toàn bộ ma trận JVM runtime như đối với Java application image.

## 17. Quy trình CI/CD kiểm cả compile target và runtime image

Có thể tổ chức gates theo các bước:

1. **Lock inputs:** Gradle wrapper/Maven, Spring Boot plugin, approved JDK toolchain, dependencies, builder/run-image version/digest.
2. **Compile/test:** Gradle `clean test bootJar` hoặc Maven `clean verify`.
3. **Bytecode check:** `javap -verbose` trên main class và các generated/dependency classes quan trọng; Java 17 phải cho major 61.
4. **CNB build:** `bootBuildImage`/`spring-boot:build-image` với `BP_JVM_VERSION` rõ ràng.
5. **Image metadata:** ghi image tag/digest, architecture, buildpacks, selected JVM provider.
6. **Runtime smoke test:** chạy image, kiểm HTTP response và runtime major bằng endpoint/metrics.
7. **SBOM:** lưu JRE vendor, patch và vulnerability scan results.
8. **Integration/security tests:** kiểm functionality, native libs, Java modules, security policies và môi trường Kubernetes/registry.
9. **Publish/deploy:** chỉ khi QA đủ, publish image và xác nhận **chính digest đó** chạy tại môi trường đích.

Ví dụ Gradle:

~~~bash
./gradlew clean test bootJar
javap -verbose -classpath build/classes/java/main com.example.cnb.JvmCompatApplication
./gradlew bootBuildImage
docker image inspect local/jvm-compat-demo:0.1.0
~~~

Sau đó chạy container và test từ terminal khác:

~~~bash
docker run --rm -p 18080:8080 local/jvm-compat-demo:0.1.0
~~~

~~~bash
curl -fsS http://localhost:18080/hello
curl -fsS http://localhost:18080/runtime-major
~~~

Để CI chạy không tương tác, có thể chạy container detached, readiness probe với timeout, log collection và cleanup riêng theo policy. Đừng tạo test “build image xanh” rồi bỏ qua runtime smoke test.

Những chứng cứ **chưa đủ nếu đứng riêng**: chỉ thấy `mvn package BUILD SUCCESS`; chỉ thấy `BP_JVM_VERSION=17` trong config; chỉ có `major version: 61` ở main class; chỉ thấy Docker image tồn tại; chỉ gọi `/hello` mà chưa kiểm runtime Java/dependencies.

## 18. Bài tập có đáp án

### Bài 1: Nhận diện major version

**Đề:** `javap` ghi `major version: 65`. Đó là target Java nào? JVM 17 có chạy được không?

**Đáp án:** Java 21. JVM 17 không thể nạp class major 65; cần target thấp hơn hoặc runtime cao hơn, có kiểm thử.

### Bài 2: Spring Boot 3.3 minimum version

**Đề:** application main class target 11 nhưng dependency Spring Boot 3.3.13. Có thể chạy toàn app trên JVM 11?

**Đáp án:** không. Spring Boot 3.3.13 yêu cầu Java 17 tối thiểu.

### Bài 3: Cấu hình Gradle Groovy

**Đáp án:**

~~~groovy
tasks.named('bootBuildImage') {
    environment['BP_JVM_VERSION'] = '17'
}
~~~

Chỉ là fragment cho project đã apply Spring Boot và Java plugins.

### Bài 4: Cấu hình Gradle Kotlin

**Đáp án:**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    environment.put("BP_JVM_VERSION", "17")
}
~~~

### Bài 5: Maven

**Đáp án:**

~~~xml
<configuration>
    <image>
        <env>
            <BP_JVM_VERSION>17</BP_JVM_VERSION>
        </env>
    </image>
</configuration>
~~~

Đây là một plugin configuration fragment, không thay Maven compiler release.

### Bài 6: Host Java 21, image Java 17

**Đề:** `java -version` trên laptop là 21, `/runtime-major` trả 17. Có lỗi không?

**Đáp án:** không nhất thiết. Build tool JVM và container JVM là hai môi trường độc lập; quan trọng runtime khớp policy và bytecode.

### Bài 7: Đổi environment quá muộn

**Đề:** image Java 17 đã build; dùng `docker run -e BP_JVM_VERSION=21`. Runtime có đổi thành 21?

**Đáp án:** không. Cần đặt BP_JVM_VERSION khi build image và tạo image mới.

### Bài 8: Main class đúng, dependency sai

**Đề:** main class major 61, transitive library có class major 65 và runtime là Java 17. Lỗi có thể chỉ xuất hiện khi gọi một chức năng không?

**Đáp án:** có. JVM có thể chỉ load class major 65 khi chức năng đó được sử dụng; thêm integration tests và kiểm đúng dependency.

### Bài 9: Compiler release khác target

**Đề:** dùng JDK 21 để compile `targetCompatibility=17` nhưng source dùng JDK 21 API. Vì sao runtime 17 có thể lỗi?

**Đáp án:** -target giới hạn bytecode, không giới hạn Java platform APIs đầy đủ. Dùng `javac --release 17` qua Gradle/Maven.

### Bài 10: Kiểm exact JVM patch

**Đề:** `BP_JVM_VERSION=17` có bảo đảm image dùng một patch JRE 17.0.x cố định?

**Đáp án:** không. Đọc SBOM và runtime version, kiểm approved builder/JVM provider/digests và chính sách cập nhật patches.

## 19. Checklist trước phát hành

- [ ] Framework version được xác minh hỗ trợ JVM đã chọn; Spring Boot 3.3.13 cần Java 17+.
- [ ] Gradle/Maven/JDK build compiler có version phù hợp, không phụ thuộc host JDK ngẫu nhiên.
- [ ] Compiler target được khóa bằng `--release`/toolchain hoặc Maven compiler release.
- [ ] `javap -verbose` xác nhận compiled class major đúng contract.
- [ ] Các runtime/transitive/generated classes quan trọng được kiểm compatibility.
- [ ] `BP_JVM_VERSION` được đặt ở build-time environment của đúng builder, không chỉ docker run.
- [ ] Buildpack/JVM provider/run image hỗ trợ version, OS/CPU architecture và vendor cần thiết.
- [ ] Image build thành công, tag/digest rõ; không nhầm image cũ.
- [ ] Container được launch thật và runtime major được đọc từ process trong image.
- [ ] SBOM cho thấy exact JRE vendor, patch version và dependencies.
- [ ] Runtime flags/native dependencies/modules/agents được kiểm bằng integration tests.
- [ ] Nếu Java major thay đổi, có regression/performance/security tests và rollback.
- [ ] CI/deployment lưu provenance và kiểm digest thực được triển khai.
- [ ] Không coi một mình build success, class major hoặc buildpack env là đủ chứng minh runtime compatibility.

**Kết luận:** `BP_JVM_VERSION` quyết định **JVM mà Paketo cung cấp cho image**, còn toolchain và `--release` quyết định **class files được compiler tạo ra**. Với Spring Boot 3.3 Java 17, cách kiểm soát rõ nhất là compile `--release 17`, xác minh major **61**, tạo image với `BP_JVM_VERSION=17`, kiểm SBOM và chạy image thật để xác nhận JVM major **17**. Nếu có mismatch, sửa đúng tầng biên dịch hoặc tầng runtime, rồi kiểm tra lại toàn bộ image/dependencies.

## 20. Nguồn chính thức

- Spring Boot 3.3.13 Gradle Plugin — Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html
- Spring Boot 3.3.13 Maven Plugin — Packaging OCI Images: https://docs.spring.io/spring-boot/3.3/maven-plugin/build-image.html
- Spring Boot 3.3.13 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Paketo Java Buildpacks — JVM Version Selection: https://paketo.io/docs/howto/java/
- Paketo Buildpacks — Configuration: https://paketo.io/docs/howto/configuration/
- Paketo — Software Bill of Materials: https://paketo.io/docs/howto/sbom/
- Cloud Native Buildpacks — Pack SBOM CLI: https://buildpacks.io/docs/for-platform-operators/how-to/integrate-ci/pack/cli/pack_sbom/
- Gradle — Toolchains và Java release: https://docs.gradle.org/current/userguide/toolchains.html
- Java Virtual Machine Specification — Class File Format: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- Java SE 17 — javap reference: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

Hãy kiểm lại tài liệu theo **phiên bản Spring Boot plugin, builder, JVM provider và Java runtime thực tế**; tên buildpack hoặc default Java version có thể thay đổi khi nâng cấp.
