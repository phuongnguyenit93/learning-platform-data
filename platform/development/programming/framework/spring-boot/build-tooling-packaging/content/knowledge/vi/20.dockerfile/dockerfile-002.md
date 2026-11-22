# Phân biệt image JDK dùng để build và image JRE dùng để chạy

## Mục tiêu học tập

Khi đưa ứng dụng Spring Boot lên Docker, một lựa chọn rất quan trọng là **image nào dùng để biên dịch** và **image nào thực sự đi vào môi trường production**. Nhiều người mới học đặt luôn Maven, Gradle, JDK, source code và executable JAR vào một image duy nhất, rồi chạy `java -jar`. Cách đó có thể chạy được nhưng thường đưa vào image phát hành những thành phần không còn cần thiết.

Docker **multi-stage build** giải quyết việc này bằng cách tách các giai đoạn:

- **Giai đoạn build:** dùng image chứa **JDK** và công cụ build/Wrapper để biên dịch Java, chạy test, resolve dependencies và tạo Spring Boot executable JAR/WAR.
- **Giai đoạn runtime:** dùng image chứa **JRE** (hoặc Java runtime được xây dựng phù hợp) để **chạy artifact đã được build**, không cần mang theo `javac`, Maven, Gradle, source code hay bộ test.
- **Chuyển giao:** `COPY --from=build` lấy đúng file executable JAR từ giai đoạn build sang giai đoạn runtime; chỉ các file được copy/chủ động cài ở runtime mới xuất hiện trong filesystem cuối.

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **JVM, JRE, JDK**; hiểu vì sao Java runtime sau Java 9 không nhất thiết có thư mục `jre/` như các JDK cũ.
2. Đọc đúng các tag Docker `eclipse-temurin:17-jdk-jammy` và `eclipse-temurin:17-jre-jammy`; biết chọn **Java major version** và hệ điều hành/kiến trúc tương thích.
3. Viết **Dockerfile multi-stage** để build Spring Boot bằng Maven Wrapper hoặc Gradle Wrapper với JDK, sau đó chạy executable JAR bằng JRE.
4. Biết cách tránh copy nhầm `-plain.jar`, `.jar.original`, source code, `.m2`, `.gradle` hoặc secret vào image production.
5. Dùng lệnh `docker build`, `docker run`, `docker image inspect`, `java -version`, `javac -version` và HTTP smoke test để chứng minh hai stage có vai trò khác nhau.
6. Tối ưu build context/cache, chạy với user không phải root, kiểm tra base image digest, CVE, CA certificates, filesystem permissions và resource limits.
7. Nhận diện các **trường hợp ngoại lệ** mà JRE tối giản chưa đủ: ứng dụng dùng Java compiler API, `jlink`/`jdeps`, các module Java bị cắt bỏ hoặc công cụ chẩn đoán chỉ có trong JDK.
8. Phân biệt phương án build **bên trong Docker** với phương án **build ở CI rồi dùng Dockerfile runtime-only**, và hiểu các giải pháp khác như buildpacks hoặc custom `jlink` runtime.

**Bối cảnh ví dụ:** Spring Boot **3.3.13**, Java **17**, một image **Eclipse Temurin JDK 17** cho build và **Eclipse Temurin JRE 17** cho runtime. Hai tag `17-jdk-jammy`/`17-jre-jammy` tồn tại trong Docker Official Image Eclipse Temurin tại thời điểm đối chiếu. Chúng là tag **có thể được cập nhật**; để khóa byte base image trong pipeline release, dùng digest theo chính sách của tổ chức. Ví dụ dùng shell/Linux Docker; Windows PowerShell có biến thể ở phần sau.

---

## 1. Từ Java source đến process Spring Boot

Trước tiên hãy nhìn quy trình **không có Docker**:

```text
src/main/java/*.java
       |
       v
  javac / JavaCompiler                <-- công cụ trong JDK
       |
       v
    *.class
       |
       v
 Maven/Gradle + Spring Boot plugin   <-- đóng executable JAR
       |
       v
  container-demo-0.0.1-SNAPSHOT.jar
       |
       v
 java -jar file.jar                   <-- cần Java runtime + dependency của app
       |
       v
 Spring Boot ApplicationContext
       |
       v
 HTTP GET /hello
```

Ở bước tạo `.class`, Java compiler cần được cung cấp. Ở bước `java -jar`, phần lớn ứng dụng Spring Boot chuẩn **không cần tiếp tục biên dịch source code**.

### 1.1 JVM, JRE và JDK: khác nhiệm vụ

| Thành phần | Chức năng chính | Được cần ở bước nào? |
| --- | --- | --- |
| **JVM** | Chạy Java bytecode, classloading, garbage collection, JIT, thread handling. | Runtime; cũng được dùng khi chạy công cụ Java. |
| **JRE** | JVM + Java standard libraries/modules + các thành phần hỗ trợ chạy ứng dụng Java. | Chạy `java -jar`. |
| **JDK** | Java runtime **cộng công cụ phát triển**, ví dụ `javac`, `jar`, `jlink`, `jdeps` và những tiện ích khác tùy bản phân phối. | Compile/test/package/build image; cũng **có thể** chạy ứng dụng. |
| **Maven/Gradle** | Build orchestration: dependency resolution, compilation, test, packaging. | Thường dùng trong stage build, **không bắt buộc** ở runtime. |
| **Spring Boot executable JAR** | App classes/resources + Boot launcher + các runtime dependency JAR được plugin đóng gói. | File được runtime JRE chạy. |

**JDK không phải thứ "chỉ compile và không chạy được".** JDK bao gồm runtime và hoàn toàn có thể chạy `java -jar`. Chọn JRE cho final image là **quyết định giảm thành phần không cần thiết**, không phải một yêu cầu bắt buộc của Java.

**JRE không phải chỉ là JVM trần.** JVM cần Java platform classes/modules và các thư viện native để chạy chương trình. Một runtime "quá nhỏ" bị cắt module cần thiết có thể lỗi dù vẫn có file `java`.

### 1.2 Java 9+ và tên gọi "JRE"

Trong Java 8, nhiều người quen phân biệt `JDK/bin` và `JDK/jre/bin`. Từ Java 9 và cơ chế Java Platform Module System, không nên giả định bản JDK hiện đại vẫn có một thư mục `jre/` lồng bên trong. Một image JRE hiện đại có thể chứa Java runtime ở `/opt/java/openjdk` và nhiều module chuẩn, nhưng **không có bộ công cụ phát triển hoàn chỉnh**.

Vì vậy hãy kiểm tra **lệnh thực tế** thay vì suy theo tên thư mục:

```bash
# Image build
docker run --rm --entrypoint java eclipse-temurin:17-jdk-jammy -version
docker run --rm --entrypoint javac eclipse-temurin:17-jdk-jammy -version

# Image runtime
docker run --rm --entrypoint java eclipse-temurin:17-jre-jammy -version
```

Kết quả kỳ vọng là cả hai có `java` và JDK có `javac`. **Không cần cố chạy `javac` trong JRE để kiểm tra**, vì thiếu executable sẽ báo lỗi ngay từ runtime; phần 11 có lệnh shell kiểm tra sự vắng mặt an toàn hơn.

### 1.3 Spring Boot executable JAR không phải bộ biên dịch

Trong Spring Boot 3.3, executable JAR thường chứa:

```text
container-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/classes/com/example/container/ContainerApplication.class
├── BOOT-INF/lib/spring-boot-...jar
├── BOOT-INF/lib/spring-webmvc-...jar
├── BOOT-INF/lib/tomcat-embed-...jar
└── org/springframework/boot/loader/...
```

Đây là **cấu trúc minh họa**, tên dependency và phiên bản được build tool chọn. Khi gọi `java -jar`, Boot launcher khởi chạy ứng dụng và hỗ trợ load các nested JAR. JRE **không cần giải nén rồi biên dịch lại** tất cả `BOOT-INF/classes` để chạy.

JIT compiler của JVM có thể tối ưu machine code **trong lúc chương trình đang chạy**. Đó là cơ chế runtime **khác với `javac`**, không làm kết luận "JRE dùng cho runtime" trở nên sai.

## 2. Vì sao nên tách image build khỏi runtime?

### 2.1 Hệ quả của một image JDK cho mọi giai đoạn

Ví dụ đơn giản nhưng chưa tối ưu:

```dockerfile
FROM eclipse-temurin:17-jdk-jammy

WORKDIR /workspace
COPY . .
RUN ./mvnw clean package
ENTRYPOINT ["java", "-jar", "/workspace/target/container-demo-0.0.1-SNAPSHOT.jar"]
```

Đây là **phản ví dụ**, không phải Dockerfile production được khuyến nghị. Nó còn giả định `mvnw` đã có executable bit và `.mvn` được copy đúng. Một image kiểu này có thể chứa:

- JDK với compiler và những công cụ development không cần ở runtime.
- Project source code, test fixtures, build scripts và các file trong build context.
- Caches Maven/Gradle và dependency metadata tích lũy trong các layer.
- Tooling hoặc file nhạy cảm vô tình đi theo `COPY . .`.
- Một filesystem lớn hơn và phạm vi cần quét lỗ hổng rộng hơn, tùy các lớp OS và packages thực tế.

**Không tự động kết luận image JDK chứa lỗ hổng bảo mật** hoặc JRE luôn an toàn hơn. Cả JDK lẫn JRE có thể có CVE; OS packages, tuổi base image, dependency của app và chính sách patch mới quyết định. Multi-stage chỉ giúp **giảm phần không cần thiết** trong runtime image và có thể cải thiện quản trị rủi ro.

### 2.2 Multi-stage: giữ quá trình build, bỏ công cụ build khỏi final

```text
                 Dockerfile
                     |
        +------------+------------------+
        |                               |
        v                               v
Stage "build"                     Stage "runtime"
JDK 17                             JRE 17
Maven/Gradle Wrapper               Không cần Wrapper
src/ và test/                      Không cần source
dependency cache                   Không cần build cache
javac, tests, packaging            Chỉ Java launcher + app.jar
        |                               ^
        v                               |
  /out/app.jar -------- COPY --from=build
                                        |
                                        v
                                Container production
                                java -jar /app/app.jar
```

Một Dockerfile có thể chứa nhiều `FROM`. Mỗi `FROM` bắt đầu **một stage** với base filesystem riêng. Trong Docker build thông thường, **final stage** là image được gắn tag; các layer trước đó có thể được BuildKit giữ trong **build cache**, nhưng không trở thành các layer filesystem của final image trừ khi bạn cố tình copy hoặc tham chiếu chúng.

**Nhớ:** secret có thể vẫn bị rò vào build log/cache/remote build infrastructure nếu dùng sai cách, dù không xuất hiện trong final image. Multi-stage **không thay thế** secret management.

### 2.3 Bảng so sánh thực dụng

| Câu hỏi | Build stage dùng JDK | Runtime stage dùng JRE |
| --- | --- | --- |
| Có `java`? | Có | Có |
| Có `javac`? | Có | Thông thường không |
| Có Maven/Gradle? | Do bạn cung cấp qua Wrapper hoặc base image | Thông thường không cần |
| Có source/test? | Có để build và test | Không cần copy |
| Có `jar`/`jlink`/`jdeps`? | Thường có ở JDK | Không nên mặc định có |
| Có thể chạy Spring Boot app? | Có | Có, nếu Java/runtime phù hợp |
| Có thể biên dịch Java source? | Có | Không phải mục tiêu chuẩn |
| Có thể chạy JUnit/Gradle tests? | Có nếu setup phù hợp | Không cần trong production |
| Mục tiêu tối ưu | Build đúng và nhanh, có công cụ chẩn đoán | Ít thành phần và quyền hạn, cập nhật dễ |
| Có bảo đảm an toàn tuyệt đối? | Không | Không |

## 3. Điều kiện tương thích: chọn đúng Java major version

Java bytecode có **class file version**. Một ứng dụng được build cho Java 17 sử dụng class file **major 61**; Java runtime thấp hơn có thể báo `UnsupportedClassVersionError`. Ngược lại, JRE mới hơn thường chạy được bytecode cũ trong phạm vi tương thích Java/platform, nhưng vẫn có thể có thay đổi API, mô-đun, thư viện hoặc runtime behavior.

Ví dụ cùng dòng version:

```dockerfile
# Compiler/toolchain cho ứng dụng Java 17
FROM eclipse-temurin:17-jdk-jammy AS build

# Runtime Java 17 cùng dòng bản phân phối
FROM eclipse-temurin:17-jre-jammy AS runtime
```

Đây là lựa chọn đơn giản và ít bất ngờ cho project Spring Boot 3.3.13 có Java toolchain 17.

**Không tự ghép** `21-jdk` với `17-jre` rồi mặc định an toàn. JDK 21 có thể được cấu hình `--release 17` hoặc Gradle toolchain Java 17 để tạo bytecode phù hợp, nhưng nếu code dùng API Java 21 hoặc compiler target sai, JRE 17 vẫn lỗi. Ghi rõ Java compiler target/`maven.compiler.release`/`java.toolchain` và kiểm chứng runtime thật.

### 3.1 Kiểm tra version trong image

```bash
docker run --rm --entrypoint java \
  eclipse-temurin:17-jdk-jammy -version

docker run --rm --entrypoint java \
  eclipse-temurin:17-jre-jammy -version
```

Đầu ra **không được cố định nguyên văn**: minor/security patch và build number của Temurin có thể đổi khi tag cập nhật. Điều cần so là **major Java version 17** và version/build đã được chấp thuận.

### 3.2 Khác biệt Linux distribution và native dependencies

Tag `-jammy` chỉ Ubuntu 22.04 "Jammy" ở nền image, không phải phần Java version. Hai image có cùng Java 17 nhưng dựa trên Ubuntu, Alpine/musl hoặc một base distroless khác có thể khác:

- libc: **glibc** vs **musl**.
- CA certificate store và cách cập nhật trust certificates.
- Timezone/locale/font packages.
- Native libraries, JNI, `java.library.path`.
- Shell/debug tools có hay không.
- Hệ thống user/group, filesystem, đường dẫn.

Với thư viện dùng JNI/native như một số driver, OCR, graphics hoặc Netty native transport, không được suy rằng "Java major giống nhau là chắc chắn chạy". Phải test image runtime thật trên đúng CPU architecture/OS.

### 3.3 CPU architecture

Docker Official Images có thể hỗ trợ nhiều architecture như `linux/amd64` và `linux/arm64`, nhưng **không phải mọi tag** đều hỗ trợ mọi nền tảng. Kiểm tra trước khi build multi-arch hoặc chạy trên ARM:

```bash
docker buildx imagetools inspect eclipse-temurin:17-jdk-jammy
docker buildx imagetools inspect eclipse-temurin:17-jre-jammy
```

Đây là lệnh dùng Buildx plugin. Kết quả platform có thể thay đổi theo tag/registry; không tự giả định máy ARM sẽ chạy native layer x86_64 hoặc app có native dependency tự tương thích.

## 4. Project Spring Boot Java 17+ dùng cho thực hành

Để bài học có tiêu chí kiểm chứng rõ, ta dùng một ứng dụng web nhỏ trả chuỗi cố định, cùng project có thể build bằng **Maven hoặc Gradle**. Khi thực hành, chọn **một hệ build**; không trộn cả hai Dockerfile lên một cây dự án rồi đoán output.

### 4.1 Cấu trúc

```text
container-demo/
├── src/
│   ├── main/java/com/example/container/ContainerApplication.java
│   └── test/java/com/example/container/ContainerApplicationTests.java
├── pom.xml                        (nếu dùng Maven)
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...               (nếu dùng Maven Wrapper)
├── settings.gradle                (nếu dùng Gradle)
├── build.gradle                   (nếu dùng Gradle)
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...             (nếu dùng Gradle Wrapper)
├── Dockerfile.maven               (lựa chọn Maven)
├── Dockerfile.gradle              (lựa chọn Gradle)
└── .dockerignore
```

File `mvnw`/`gradlew` và thư mục Wrapper phải được sinh từ công cụ/nguồn đáng tin. **Không tạo Wrapper chỉ bằng file shell tự viết** rồi bỏ qua Maven/Gradle distribution checksum và wrapper JAR cần thiết.

### 4.2 Java code thực sự có thể biên dịch trong Spring Boot project

`src/main/java/com/example/container/ContainerApplication.java`:

```java
package com.example.container;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ContainerApplication {

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "Hello from Spring Boot";
    }

    public static void main(String[] args) {
        SpringApplication.run(ContainerApplication.class, args);
    }
}
```

Lớp này vừa là main configuration vừa đăng ký REST endpoint `GET /hello`. Đây là Java 17+ hợp lệ **trong project có `spring-boot-starter-web`**. Không gọi `javac ContainerApplication.java` đơn lẻ nếu không cấu hình Spring Boot classpath.

### 4.3 HTTP integration test

`src/test/java/com/example/container/ContainerApplicationTests.java`:

```java
package com.example.container;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ContainerApplicationTests {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void helloEndpointReturnsText() {
        String body = rest.getForObject("/hello", String.class);
        assertEquals("Hello from Spring Boot", body);
    }
}
```

Test dùng embedded Tomcat ở random port trong môi trường build/test. Nó giúp bảo đảm ứng dụng hoạt động cơ bản **trước khi tạo runtime image**. **Test JVM trong build stage khác với runtime image final**; còn cần smoke test sau `docker run`.

### 4.4 POM Maven hoàn chỉnh

Tệp `pom.xml`:

```xml
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
    <artifactId>container-demo</artifactId>
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

Dùng `spring-boot-starter-parent` nên Spring Boot Maven Plugin `repackage` được nối đúng vào lifecycle khi plugin được khai báo. Sau `./mvnw clean package`, app mẫu có **executable JAR chính** ở `target/container-demo-0.0.1-SNAPSHOT.jar`; Maven có thể lưu archive trước repackage thành `.jar.original`.

### 4.5 Gradle Groovy DSL hoàn chỉnh

`settings.gradle`:

```groovy
rootProject.name = 'container-demo'
```

`build.gradle`:

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
        languageVersion = JavaLanguageVersion.of(17)
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

Sau `./gradlew clean build`, một executable Spring Boot JAR thường ở `build/libs/container-demo-0.0.1-SNAPSHOT.jar`. Nếu `jar` task cũng chạy, file `container-demo-0.0.1-SNAPSHOT-plain.jar` có thể cùng tồn tại. **Plain JAR không thay cho Boot JAR trong `java -jar`** khi thiếu Boot launcher và nested runtime dependencies.

## 5. Dockerfile Maven multi-stage: JDK build, JRE chạy

Tạo file `Dockerfile.maven` (Linux containers):

```dockerfile
# syntax=docker/dockerfile:1

# ----- STAGE 1: Build application using a JDK -----
FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /workspace

# Copy Maven Wrapper and POM first for dependency-layer caching.
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./

RUN chmod +x mvnw && ./mvnw -B -ntp dependency:go-offline

# App source changes more often than POM/dependencies.
COPY src/ src/

# Compile, execute tests, and create the executable Spring Boot JAR.
RUN ./mvnw -B -ntp clean package \
    && test -f target/container-demo-0.0.1-SNAPSHOT.jar \
    && cp target/container-demo-0.0.1-SNAPSHOT.jar /tmp/app.jar

# ----- STAGE 2: Run application using a JRE -----
FROM eclipse-temurin:17-jre-jammy AS runtime
WORKDIR /app

# This example uses Ubuntu-based Temurin images with useradd/groupadd.
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M appuser

COPY --from=build --chown=10001:10001 /tmp/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

### 5.1 Đọc từng phần Dockerfile Maven

- `FROM eclipse-temurin:17-jdk-jammy AS build`: tạo stage mang tên `build`, sử dụng JDK 17 để chạy Maven Wrapper, Java compiler và tests.
- `WORKDIR /workspace`: chọn working directory cố định; mọi `COPY`/`RUN` tương đối tiếp theo dùng nó.
- `COPY .mvn/ .mvn/` và `COPY mvnw pom.xml ./`: đưa Maven Wrapper files và POM vào stage build. Chúng **không** được copy sang stage runtime.
- `RUN chmod +x mvnw`: bảo đảm script có quyền chạy trong Linux image. Nếu file `mvnw` có CRLF sai, phải sửa line endings trong repository, không coi `chmod` là cách sửa newline.
- `dependency:go-offline`: cố gắng tải trước plugin/dependency thường dùng để tận dụng cache layer khi source đổi. Không bảo đảm toàn bộ plugin/test provider ở mọi project đều đã được preload; bước `package` vẫn có thể cần mạng hoặc artifact chưa có.
- `COPY src/ src/`: chép source chính và test vào build stage; đổi Java code sẽ invalidate các bước phía sau mà thường giữ được layer dependencies trước đó.
- `./mvnw ... clean package`: build và **chạy tests theo lifecycle mặc định**. Ví dụ **không** thêm `-DskipTests`.
- `test -f ...jar`: fail fast nếu tên file khác kỳ vọng hoặc `repackage` chưa tạo archive chính.
- `cp ... /tmp/app.jar`: chuẩn hóa đường chuyển giao để stage final không phụ thuộc tên version động của file.
- `FROM eclipse-temurin:17-jre-jammy AS runtime`: bắt đầu filesystem **mới** chỉ có base JRE và những gì khai báo sau đó.
- `groupadd/useradd`: tạo user UID 10001 để không chạy Java process bằng root.
- `COPY --from=build --chown=10001:10001`: chép **duy nhất executable JAR đã kiểm tra đường dẫn** sang runtime.
- `USER 10001:10001`: những instruction/runtime tiếp theo thực thi với quyền này nếu không có override.
- `EXPOSE 8080`: mô tả cổng mà app dự kiến lắng nghe; **không tự publish port lên host**.
- `ENTRYPOINT ["java","-jar",...]`: dùng exec form để chạy Java process, hỗ trợ signal handling thuận lợi hơn so với wrapper shell không cần thiết.

Đây là một **Dockerfile đầy đủ** cho Maven project mẫu với Wrapper đã tồn tại, nguồn đúng đường dẫn và có Docker daemon/BuildKit + mạng tải dependency. Docker **không** được giả định có thể build nếu Maven repository nội bộ cần credential chưa được cung cấp.

### 5.2 Build image Maven

Từ root của Maven project:

```bash
docker build -f Dockerfile.maven -t container-demo:maven .
```

Dấu `.` cuối là **build context**. Docker chỉ copy những file trong context mà `.dockerignore` cho phép. Nếu đặt Dockerfile ngoài root hoặc build context không có `pom.xml`/`src/`/`mvnw`, `COPY` sẽ thất bại; sửa path hoặc context đúng, không copy tùy tiện toàn disk.

### 5.3 Chạy smoke test trên JRE image

```bash
docker run --rm -d \
  --name container-demo-maven-test \
  -p 18080:8080 \
  container-demo:maven

# Khi ứng dụng đã khởi động:
curl --fail --silent --show-error http://localhost:18080/hello

# Xem log nếu ứng dụng không đáp ứng:
docker logs container-demo-maven-test

# Kết thúc container thử nghiệm:
docker stop container-demo-maven-test
```

Khi server sẵn sàng, body kỳ vọng của HTTP response là:

```text
Hello from Spring Boot
```

Đây là **output do method Java trả về theo mã ví dụ**, không phải log của một lần thực chạy. Vì container được tạo với `--rm`, sau `docker stop` Docker sẽ tự xóa container đó. Nếu đổi tên/port/container ID, sửa các lệnh tương ứng.

Nếu cổng host 18080 đã được dùng, đổi **vế trước** trong `-p 18080:8080`, ví dụ `18081:8080`; vế sau phải khớp cổng Spring Boot thực sự lắng nghe trong container.

### 5.4 Vì sao final image không có Maven cache hoặc source?

`COPY --from=build /tmp/app.jar /app/app.jar` chép **một file**. Nó không copy `/workspace/src`, `/workspace/.mvn`, `/root/.m2` hay `/tmp` của stage build theo kiểu tự động. Các files đó có thể còn trong build cache của Docker trên máy builder/CI, nhưng **không phải filesystem của final stage**.

Tuy nhiên, nếu bạn vô tình viết `COPY --from=build /workspace /app` thì source và build scripts lại đi vào final image. Multi-stage không tự bảo vệ khỏi một lệnh COPY quá rộng; review đường dẫn là bắt buộc.

## 6. Dockerfile Gradle multi-stage: cách tương đương

Tạo `Dockerfile.gradle` cho **Gradle project mẫu**:

```dockerfile
# syntax=docker/dockerfile:1

FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /workspace

# Include the wrapper distribution definition and build scripts.
COPY gradle/ gradle/
COPY gradlew settings.gradle build.gradle ./
RUN chmod +x gradlew

# Resolve dependencies before copying frequently changing app sources.
RUN ./gradlew --no-daemon dependencies --configuration runtimeClasspath

COPY src/ src/

# build runs checks/tests and creates executable Boot JAR.
RUN ./gradlew --no-daemon clean build \
    && test -f build/libs/container-demo-0.0.1-SNAPSHOT.jar \
    && cp build/libs/container-demo-0.0.1-SNAPSHOT.jar /tmp/app.jar

FROM eclipse-temurin:17-jre-jammy AS runtime
WORKDIR /app

RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M appuser

COPY --from=build --chown=10001:10001 /tmp/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

### 6.1 Sự khác nhau với Maven stage

- `gradle/` chứa Gradle Wrapper JAR và `gradle-wrapper.properties`; `gradlew` là script wrapper. **Đừng loại thư mục `gradle/` bằng `.dockerignore`**, nếu không Wrapper không khởi động được.
- `RUN ./gradlew --no-daemon dependencies --configuration runtimeClasspath` là một bước preload/đọc graph có thể hỗ trợ layer cache; nó **không bảo đảm** tất cả test/plugin dependency đã tải. Lượt `build` có thể còn cần network.
- `./gradlew --no-daemon clean build` chạy compile, test, assemble; Spring Boot Gradle plugin kết nối `bootJar` với build lifecycle phù hợp. Nếu chỉ chạy `bootJar`, **không** mặc định chạy toàn bộ tests; vì vậy ví dụ dùng `build`.
- Gradle có thể tạo cả `container-demo-...jar` và `container-demo-...-plain.jar`. Lệnh `test -f` + `cp` chọn **đúng tên không classifier** của Boot JAR mẫu; không dùng `COPY .../*.jar` khi có nhiều file.
- `--no-daemon` yêu cầu không duy trì một Gradle daemon sống lâu trong build container; chi tiết Gradle có thể fork một single-use daemon trong một số trường hợp toolchain/JVM args, nhưng nó được dọn sau lệnh.
- Stage runtime giống Maven: **JRE 17, app.jar và user 10001**, không cần Gradle trong final image.

Build và chạy:

```bash
docker build -f Dockerfile.gradle -t container-demo:gradle .

docker run --rm -d \
  --name container-demo-gradle-test \
  -p 18081:8080 \
  container-demo:gradle

curl --fail --silent --show-error http://localhost:18081/hello

docker stop container-demo-gradle-test
```

**Lệnh `curl` có thể thất bại nếu chạy quá sớm.** Đợi ứng dụng ready bằng polling giới hạn thời gian/health check và xem `docker logs` khi lỗi; không dùng một `sleep 2` cố định làm bằng chứng startup thành công.

### 6.2 Nếu project dùng Gradle Kotlin DSL

Dockerfile ở trên sao chép `settings.gradle`/`build.gradle`; với Kotlin DSL, điều chỉnh:

```dockerfile
COPY gradlew settings.gradle.kts build.gradle.kts ./
```

và build script phải là `.kts` tương ứng. Nếu project có `gradle.properties`, version catalog `gradle/libs.versions.toml`, `buildSrc`, included builds hoặc source generation scripts, phải copy các inputs đó vào stage build đúng vị trí trước khi chạy task. Không dùng Dockerfile tối giản để giả định một monorepo phức tạp chỉ có `src` và một build file.

### 6.3 Nếu project có nhiều module Gradle

Ví dụ ứng dụng nằm ở `:app`. Task/đường artifact có thể là:

```bash
./gradlew :app:build
```

```text
app/build/libs/app-0.0.1-SNAPSHOT.jar
```

Các tên là minh họa, không phải đường dẫn chắc chắn của mọi project. Dockerfile phải:

1. Copy `settings.gradle` và các subprojects/build scripts được sử dụng.
2. Chạy `:app:build` hoặc graph phù hợp.
3. Xác định Boot executable JAR của **module app**, không chọn nhầm plain/library JAR của `:core`.
4. Copy đúng output vào `/tmp/app.jar` trước runtime stage.

Không dùng `find . -name '*.jar' | head -1` làm cơ chế chọn artifact release.

## 7. `.dockerignore` và build context: tăng tốc, tránh mang nhầm dữ liệu

Một file `.dockerignore` phù hợp project mẫu:

```dockerignore
.git/
.gitignore
.idea/
.vscode/
*.iml

target/
build/
.gradle/
out/
logs/
*.log

.env
.env.*
*.pem
*.key
**/secrets/
**/credentials/

node_modules/
.DS_Store
Thumbs.db
```

Tùy dự án, bổ sung rules tương ứng với các file nhạy cảm/thư mục generated khác. **Không** ghi `gradle/` (Gradle Wrapper), `.mvn/`, `pom.xml`, `build.gradle`, `settings.gradle` hoặc `src/` vào ignore nếu Dockerfile cần copy chúng.

### 7.1 Đừng nhầm `.gradle/` với `gradle/`

- `.gradle/`: thường chứa local project caches, execution history; không cần copy từ host.
- `gradle/`: thường chứa Wrapper JAR/properties và có thể có version catalog, **bắt buộc** để chạy Gradle Wrapper trong Docker nếu project dùng cấu trúc đó.

Tương tự:

- `.mvn/` chứa cấu hình Maven Wrapper (và có thể extensions/config), cần copy khi dùng `mvnw`.
- `~/.m2/repository` là dependency cache của máy build; thông thường không nên copy toàn bộ từ host vào Docker image.

### 7.2 Không cho secret đi vào build context

`.dockerignore` giảm rủi ro, nhưng **không phải secret manager**:

- Không commit secret trong source.
- Không truyền production credentials qua `ARG`/`ENV` của Dockerfile rồi coi chúng vô hình.
- Với repository Maven private hoặc dependency proxy cần token, dùng **BuildKit secret mounts** theo chính sách, không đưa password vào Docker build command line hoặc layer.
- Không in token trong logs.
- Bảo vệ cache của builder/CI, đặc biệt nếu có remote cache.
- Đừng copy cả `~/.ssh` hoặc home directory vào build context.

Nếu source chứa secrets, việc chỉ bỏ chúng khỏi final JRE stage không đủ để bảo đảm chúng không xuất hiện trong build cache/logs.

### 7.3 Điều kiện của runtime-only Dockerfile khác multi-stage

Nếu bạn **build JAR trên host/CI trước**, Dockerfile chỉ cần copy artifact đã sinh. Khi đó `.dockerignore` **không được bỏ qua đường dẫn artifact** mà Dockerfile cần. Ví dụ, một Dockerfile copy `release/app.jar` cần thư mục `release/` trong context; đừng ignore nó vì copy từ host sẽ thất bại.

Trong Dockerfile multi-stage của phần 5–6, có thể ignore `target/` và `build/` trên host vì artifact được **tạo bên trong build stage**.

## 8. Một lựa chọn khác: CI build JAR rồi runtime-only Dockerfile

Không phải lúc nào Docker cũng phải compile Java. Một pipeline có thể:

1. Dùng runner có JDK + Maven/Gradle để compile/test.
2. Xuất bản một **executable Spring Boot JAR đã kiểm tra**.
3. Stage Docker image chỉ copy artifact này vào JRE image.

Ví dụ Dockerfile `Dockerfile.runtime`:

```dockerfile
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app

RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M appuser

COPY --chown=10001:10001 release/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Đây là Dockerfile **runtime-only**, không có stage JDK. Trước `docker build`, pipeline phải đặt **đúng JAR đã build/test** vào `release/app.jar` trong build context. Nếu chưa có file, Docker build sẽ fail tại `COPY` — đó là kiểm tra hữu ích, không phải lỗi cần giải quyết bằng cách copy một JAR bất kỳ.

Build:

```bash
# Sau khi CI đã build, kiểm chứng và stage release/app.jar:
docker build -f Dockerfile.runtime -t container-demo:runtime-only .
```

So sánh:

| Phương án | Build Java xảy ra ở đâu? | Final image có JDK? | Ưu điểm | Điểm cần quản lý |
| --- | --- | --- | --- | --- |
| Docker multi-stage | Stage JDK bên trong Docker build | Không, chỉ JRE nếu cấu hình đúng | Quy trình đóng gói tập trung, dễ tái hiện trên Docker host | Cache/build secrets, Docker context, thời gian build |
| CI build trước + runtime-only | Runner/agent có JDK | Không | Phân tách test và image packaging rõ ràng, tái sử dụng artifact đã kiểm tra | Phải chứng minh file stage là artifact đã QA |
| Single-stage JDK | Trong final image | Có | Đơn giản cho lab/dev hoặc runtime cần JDK | Image có compiler/caches/source nếu copy rộng |
| Buildpacks | Buildpack lifecycle/builder | Thông thường launch image chỉ runtime phù hợp | Plugin có thể tạo image tối ưu và layered | Phải hiểu buildpack builder/run image, toolchain và cấu hình |

**Chọn dựa trên mục tiêu:** multi-stage là mặc định tốt cho nhiều Dockerfile, nhưng runtime-only vẫn hợp lý nếu CI đã có bước build/test có kiểm soát và dùng artifact identity/checksum.

## 9. Kiểm chứng thực sự: image JDK và JRE có gì?

### 9.1 So lệnh `java` và `javac` theo từng base image

```bash
# Cả hai image có Java runtime.
docker run --rm --entrypoint java eclipse-temurin:17-jdk-jammy -version
docker run --rm --entrypoint java eclipse-temurin:17-jre-jammy -version

# JDK image có Java compiler.
docker run --rm --entrypoint javac eclipse-temurin:17-jdk-jammy -version
```

Trên các image Ubuntu/Jammy minh họa có shell, có thể kiểm tra compiler trong JRE bằng:

```bash
docker run --rm --entrypoint sh eclipse-temurin:17-jre-jammy \
  -c 'if command -v javac >/dev/null 2>&1; then echo "javac found"; else echo "javac absent"; fi'
```

Với tag JRE đúng vai trò, stdout **kỳ vọng** của riêng script kiểm tra là:

```text
javac absent
```

Đây là **kết quả có điều kiện**, không phải số liệu đã chạy thực tế ở container hiện tại. Với runtime khác, có thể có compiler hoặc không có shell; khi đó cách kiểm tra phải thay đổi.

### 9.2 Kiểm tra final image được tạo từ Dockerfile

```bash
docker image inspect container-demo:maven --format '{{.Config.User}}'
docker image inspect container-demo:maven --format '{{.Config.Entrypoint}}'
docker image inspect container-demo:maven --format '{{.Architecture}}'
docker image history container-demo:maven
```

Theo Dockerfile Maven của bài, field `Config.User` dự kiến là `10001:10001`; `Entrypoint` dự kiến là `[java -jar /app/app.jar]` ở biểu diễn của Docker template. Cú pháp format/đầu ra hiển thị có thể khác theo CLI version.

**`docker image history` chỉ nói về layers của final image được tag**, không tự liệt kê toàn bộ filesystem của intermediate build stage. Muốn audit sâu, dùng image inspection/SBOM/security scanner được tổ chức phê duyệt.

### 9.3 Kiểm tra final stage không có `javac`, Maven hoặc Gradle

```bash
docker run --rm --entrypoint sh container-demo:maven \
  -c 'command -v java; command -v javac || true; command -v mvn || true; command -v gradle || true'
```

Với Ubuntu JRE runtime image, `java` phải được tìm thấy; `javac`/`mvn`/`gradle` thông thường không có. Lệnh này **chỉ kiểm tra PATH**, không chứng minh toàn bộ filesystem tuyệt đối không chứa mọi file liên quan. Nếu muốn kiểm tra cụ thể hơn, đánh giá image packages/SBOM thay vì suy rộng từ `command -v`.

Không dùng các lệnh `sh` tương tự với một image distroless không có shell; hãy dùng debug image/sidecar hoặc inspect qua công cụ bên ngoài.

### 9.4 So kích thước image nhưng không đưa số giả

```bash
docker image ls eclipse-temurin
docker image ls container-demo
docker image inspect eclipse-temurin:17-jdk-jammy --format '{{.Size}}'
docker image inspect eclipse-temurin:17-jre-jammy --format '{{.Size}}'
```

**Không khẳng định số MB cố định**: base image, OS flavor, architecture và thời điểm patch thay đổi kích thước. Thông thường JRE image cùng family/flavor sẽ nhỏ hơn JDK, nhưng không phải định luật với mọi image/vendor.

Nhìn image size không đủ để kết luận **startup performance, memory footprint hay bảo mật**. JRE/JDK dùng JVM cùng dòng có thể sử dụng CPU/heap tương tự cho app; muốn kết luận hiệu năng phải đo process thực trong điều kiện so sánh hợp lệ.

## 10. Vì sao `EXPOSE 8080` chưa làm HTTP truy cập được?

Trong Dockerfile, `EXPOSE` khai báo một cổng ứng dụng dự kiến dùng. Nó là metadata/documentation; **không mở cổng host**.

Chạy ứng dụng:

```bash
docker run --rm -d \
  --name container-demo-port-test \
  -p 18080:8080 \
  container-demo:maven
```

- `18080` là **host port**.
- `8080` là **container port**, Spring Boot embedded Tomcat mặc định lắng nghe.
- `curl http://localhost:18080/hello` từ host trỏ qua port mapping.
- Nếu Spring Boot được cấu hình `server.port=9090`, phải đổi vế container của `-p` thành `9090`.
- Nếu app bind `server.address=127.0.0.1` **bên trong container**, traffic từ Docker port publishing có thể không tới được. Thông thường server cần bind trên interface phù hợp (`0.0.0.0`) để nhận kết nối ngoài container.

Chạy trong terminal khác:

```bash
curl --fail --silent --show-error http://localhost:18080/hello
docker logs container-demo-port-test
docker stop container-demo-port-test
```

**Không có sự khác biệt về HTTP endpoint do dùng JDK hay JRE**, nếu runtime có đủ Java modules, native libs và cùng app configuration. Sự khác biệt là **công cụ hiện diện trong image**, không phải việc controller `@GetMapping` có hoạt động hay không.

## 11. Bảo mật runtime: non-root, base image, secrets và quyền ghi

### 11.1 Chạy Java bằng user không phải root

Dockerfile ví dụ đặt:

```dockerfile
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M appuser

COPY --from=build --chown=10001:10001 /tmp/app.jar /app/app.jar
USER 10001:10001
```

Mục đích là giới hạn quyền của Java process. Mặc định Docker container **không phải một sandbox bảo mật tuyệt đối**; non-root giúp giảm rủi ro khi app bị khai thác hoặc có bug ghi filesystem.

Cần hiểu:

- UID/GID bên trong image có thể liên quan quyền trên mounted volume từ host.
- Thư mục `/app` thường được tạo bởi root; trong ví dụ, file JAR thuộc UID 10001 và có quyền đọc, nhưng app chưa có quyền ghi tùy ý vào `/app`.
- Nếu ứng dụng ghi file upload/log/cache vào `/app`, phải tạo writable directory và cấp quyền có chủ đích hoặc mount volume theo chính sách.
- Nếu dùng port đặc quyền nhỏ hơn 1024, một non-root process có thể cần cấu hình quyền/capabilities đặc biệt; dùng 8080 giúp đơn giản hơn.
- Không bỏ `USER` rồi chuyển runtime thành root chỉ để sửa một lỗi filesystem; sửa quyền đúng đường dẫn cần ghi.

### 11.2 Secret không đi vào image build arguments

Không viết:

```dockerfile
# Ví dụ không an toàn, KHÔNG dùng:
ARG DB_PASSWORD
ENV DB_PASSWORD=hardcoded-password
```

Secrets có thể xuất hiện trong build metadata/layers/logs, image inspect hoặc environment của container nếu quản lý sai. Thay vào đó dùng secret manager của môi trường triển khai; khi cần credential trong **build stage** để tải Maven dependencies private, dùng BuildKit secret mount hoặc cơ chế đã được chấp thuận.

Spring Boot đọc environment variables/runtime configuration theo cơ chế externalized configuration. Nhưng **đặt một password vào `docker run -e ...` cũng không tự là secret manager an toàn**: trên máy/CI có người được quyền inspect process/container, giá trị có thể bị lộ. Với production, sử dụng secret injection chuyên dụng theo tổ chức.

### 11.3 Cập nhật base image

Tag như `17-jre-jammy` có thể được publisher cập nhật khi có patch. Do đó:

- Pin một **digest** khi cần reproducibility/audit chặt.
- Cập nhật digest định kỳ qua quy trình review và kiểm thử, tránh giữ mãi CVE đã được vá.
- Quét base image, application dependencies và final image.
- Không tự tin rằng image "nhỏ" đồng nghĩa "không có CVE".
- Không chỉ xem version Java; OS libraries cũng có CVEs.
- Đảm bảo provenance của registry và multi-architecture manifest theo chính sách.

Ví dụ cú pháp pin digest (điền digest **thật** do registry/CI kiểm chứng):

```dockerfile
# Cú pháp minh họa: không dùng chuỗi placeholder như digest thật.
FROM eclipse-temurin:17-jre-jammy@sha256:<verified-image-digest>
```

Đây là **mẫu cú pháp**, không phải Dockerfile có thể build nguyên văn. Nếu muốn runnable trong ví dụ thì dùng tag đã cho; production có thể thay bằng digest đã xác thực.

### 11.4 Read-only filesystem

Một runtime container có thể chạy với read-only root filesystem nếu ứng dụng và thư viện không cần ghi ngoài những mount được phép. Ví dụ cách thử **trên máy lab**:

```bash
docker run --rm -d \
  --name container-demo-readonly \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 18082:8080 \
  container-demo:maven
```

Một số Spring Boot embedded servers, logging libraries, TLS hoặc app components có thể cần ghi temporary files; `--tmpfs /tmp` cung cấp khu vực ghi tạm. Nhưng có thể có yêu cầu khác không phù hợp `noexec` hoặc kích thước 64 MiB. **Không coi mẫu này là chính sách bắt buộc**; kiểm tra app thật, sửa mount/capabilities/temporary directory theo nhu cầu.

### 11.5 Runtime image phải có CA/locale/timezone cần thiết

JRE image khác nhau về:

- CA truststore và khả năng xử lý custom corporate CA.
- TLS provider/cipher suites.
- Locale, timezone dữ liệu và font rendering.
- Native libraries, JNI và file permissions.
- DNS resolver/runtime network stack.

Nếu app gọi HTTPS bên ngoài và gặp `SSLHandshakeException` vì CA nội bộ chưa tin cậy, không khắc phục bằng cách vô hiệu hóa certificate validation. Cần đưa CA certificate vào **truststore/runtime image theo phương pháp vendor hướng dẫn**, hoặc mount/khai báo truststore hợp lệ.

Một JRE image tối giản có thể bỏ shell/curl; healthcheck cần dùng **công cụ tồn tại trong runtime** hoặc external orchestrator probe. Không thêm đầy đủ build tools trở lại image chỉ để chạy `curl` health check nếu có cách nhẹ/an toàn hơn.

## 12. Thay JDK bằng JRE có làm app chạy chậm hơn không?

Không thể kết luận hiệu năng chỉ từ chữ JDK/JRE.

- Cùng dòng Temurin Java 17 có thể dùng JVM rất giống nhau. JIT, GC và bytecode execution vẫn có.
- JRE image thường ít công cụ nên **kích thước download và footprint image** có thể giảm.
- **Heap/RSS/CPU** phụ thuộc application, JVM flags, container limits, GC, thread count, workload và native libs, không chỉ tên tag.
- Startup time còn bị ảnh hưởng bởi class loading, số Spring beans, disk/network, image layer cache và warm-up; phải benchmark thực tế.
- JRE không tự làm ứng dụng "kém bảo mật" hoặc "an toàn tuyệt đối"; patch management mới quan trọng.

### 12.1 Điều chỉnh memory theo giới hạn container

Java 17 có cơ chế container awareness phù hợp với cgroup trong các môi trường được hỗ trợ. Có thể điều chỉnh heap percentage qua JVM flags nếu app cần:

```bash
docker run --rm -d \
  --name container-demo-memory \
  --memory 512m \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65.0" \
  -p 18083:8080 \
  container-demo:maven
```

`JAVA_TOOL_OPTIONS` được Java launcher đọc và có thể được JVM in ra log. Không phải mọi ứng dụng nên dùng 65%: native memory, Metaspace, thread stacks, direct buffers và GC overhead vẫn cần không gian. Nếu container `OOMKilled`, kiểm tra cgroup memory, JVM native memory và ứng dụng trước khi tăng heap theo cảm tính.

Cũng cần phân biệt **Docker image size** với **container memory usage**: giảm JDK tools trong filesystem không trực tiếp giảm heap do Spring sử dụng.

## 13. Kiểm soát artifact: không lấy nhầm plain JAR hay WAR

### 13.1 Maven `.jar.original`

Với Spring Boot Maven `repackage` mặc định:

```text
target/container-demo-0.0.1-SNAPSHOT.jar
target/container-demo-0.0.1-SNAPSHOT.jar.original
```

File `.jar` chính là executable Boot JAR nếu goal `repackage` đã chạy, `.jar.original` là archive ban đầu được sao lưu. Chọn file `.jar.original` để đưa vào runtime JRE có thể làm `java -jar` thiếu launcher/runtime classpath.

Nếu POM tùy chỉnh classifier như `exec`, file executable có thể là `...-exec.jar`, còn file `.jar` không classifier là plain. Dockerfile phải đổi `cp` sang **tên đúng** và kiểm tra manifest/layout.

### 13.2 Gradle `-plain.jar`

Với Spring Boot Gradle plugin:

```text
build/libs/container-demo-0.0.1-SNAPSHOT.jar
build/libs/container-demo-0.0.1-SNAPSHOT-plain.jar
```

Task `bootJar` tạo executable Spring Boot JAR; task `jar` tạo JAR thường theo naming convention `plain`. Vì vậy:

```dockerfile
# DỄ GÂY NHẦM khi có nhiều artifact:
COPY build/libs/*.jar /app/app.jar
```

là một ví dụ **không nên dùng**. Nếu wildcard khớp hơn một JAR, `COPY` tới một đường dẫn file đích có thể fail hoặc hoạt động không như ý; cũng có pipeline khác tự "chọn file đầu tiên" rồi đưa nhầm plain JAR.

Chọn rõ output của `bootJar`, hoặc cấu hình task copy ra `release/app.jar` sau khi kiểm tra ZIP:

```bash
jar tf build/libs/container-demo-0.0.1-SNAPSHOT.jar
```

Dấu hiệu của executable Boot JAR là `BOOT-INF/classes`, `BOOT-INF/lib` và Boot launcher; JRE chỉ chạy được khi artifact có entrypoint/dependencies và runtime phù hợp.

### 13.3 JAR vs WAR

Nếu dự án đóng **executable WAR** bằng `bootWar`, `java -jar app.war` cũng có thể chạy trên JRE khi WAR chứa embedded servlet runtime ở `WEB-INF/lib-provided` và Boot WarLauncher. Nhưng plain WAR deploy vào external Tomcat là mô hình khác; chạy trong JRE image bằng `java -jar` không phải mặc định.

Ví dụ này **dùng executable JAR**, không copy `.war` rồi giả định có cùng Spring Boot loader/layout. Nếu yêu cầu external Tomcat, một architecture phổ biến là **Tomcat runtime image + WAR deploy**; đó không phải "JRE thuần với java -jar" trừ khi dùng executable WAR cố ý.

### 13.4 Luồng QA artifact

```text
JDK builder:
  source + Wrapper -> test -> bootJar/repackage
                         |
                         v
                  verify JAR path
                         |
                         v
                    /tmp/app.jar
                         |
                   COPY --from=build
                         |
                         v
JRE runtime:
                  /app/app.jar
                         |
                    java -jar
                         |
                  HTTP smoke test
```

Chỉ cần **một bước nhận dạng artifact rõ ràng** để tránh các lỗi chọn file; không cần nhét cả source repository vào image cuối chỉ để debug loại JAR.

## 14. Docker cache và thời gian build

### 14.1 Thứ tự `COPY` giúp reuse dependency layers

Trong Dockerfile Maven:

```dockerfile
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -B -ntp dependency:go-offline

COPY src/ src/
RUN ./mvnw -B -ntp clean package
```

Khi chỉ sửa Java source, các bước trước `COPY src` có cơ hội reuse cache. Nếu ngay từ đầu dùng `COPY . .` thì thay một source nhỏ có thể invalidate layer resolve dependencies theo cách không cần thiết.

Trong Gradle tương tự: copy Wrapper/build scripts trước source, preload graph rồi mới copy source. Nhưng hãy nhớ: Gradle/Maven plugins/dependencies vẫn có thể cần tải thêm vào lượt compile/test; "go-offline" hoặc `dependencies` không phải lời hứa offline tuyệt đối.

### 14.2 BuildKit cache mounts (tùy chọn)

Trong builder stage sử dụng BuildKit Dockerfile syntax, có thể mount cache Maven hoặc Gradle để tránh tải lại dependency trên những build mà instruction cache không hit:

```dockerfile
# syntax=docker/dockerfile:1

# Trích đoạn thay RUN trong Maven builder:
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp clean package
```

Gradle:

```dockerfile
# syntax=docker/dockerfile:1

# Trích đoạn thay RUN trong Gradle builder:
RUN --mount=type=cache,target=/root/.gradle \
    ./gradlew --no-daemon clean build
```

Các đoạn này **không phải Dockerfile độc lập**; đặt ở builder stage sau `COPY` và `chmod` đúng cách. `--mount=type=cache` dùng khi Docker BuildKit hỗ trợ, target phải trỏ tới đúng cache directory của user chạy build.

Cache mounts **không trở thành layer filesystem của final image**. Nhưng cache vẫn nằm trên máy builder/CI, có thể chứa artifact/repository metadata và cần kiểm soát quyền, retention, trust. Không đưa secret vào cache dưới dạng file plaintext rồi coi multi-stage đã xử lý an toàn.

### 14.3 Vì sao `RUN clean` không đồng nghĩa "không cache"?

`./mvnw clean package` hoặc `./gradlew clean build` xóa output thư mục project trong build stage rồi build lại. Docker layer cache có thể reuse instruction nếu input không đổi, và BuildKit cache mount vẫn giữ dependency downloads nếu được cấu hình.

**Có hai loại cache khác nhau:**

- **Docker layer cache** ở cấp Dockerfile instruction.
- **Build tool caches** (Gradle dependency cache, task build cache hoặc Maven artifact repository) bên trong builder/cache mount.

Không trộn `bootJar UP-TO-DATE` của Gradle với Docker layer cache hit; đó là hai hệ thống cache riêng. Để đo hiệu năng, ghi rõ build mode, `--no-cache`, BuildKit cache mounts và dependency fetch trước khi so số giây.

### 14.4 Ưu tiên correctness, không bỏ tests để nhanh

Một số ví dụ internet dùng:

```bash
./mvnw package -DskipTests
./gradlew bootJar
```

Hai lệnh này **không tương đương** với chạy bộ test trước release. Maven `-DskipTests` bỏ qua thực thi test; `bootJar` không bắt buộc kéo `test` vào graph. Nếu CI pipeline đã có một bước test riêng đáng tin, có thể tách stage build/package theo chính sách; nếu không, dùng `mvn package` hoặc `gradlew build` như ví dụ bài.

Đừng so sánh "Docker build JRE nhanh hơn vì đã skip tests" rồi kết luận performance do JRE: việc JRE thay JDK chỉ ảnh hưởng **runtime stage**, không tự làm compiler/test chạy nhanh hơn.

## 15. Trường hợp JRE là chưa đủ

Dùng JRE làm runtime là lựa chọn hợp lý cho nhiều Spring Boot apps thông thường, nhưng không phải mọi ứng dụng Java đều chạy được với runtime bị thu gọn.

### 15.1 Ứng dụng biên dịch code khi đang chạy

Một số hệ thống tạo/biên dịch Java source động, xây DSL bằng Java compiler API, dùng `ToolProvider.getSystemJavaCompiler()` hoặc khởi chạy `javac` lúc runtime. Một runtime JRE không có `jdk.compiler` hoặc `javac` có thể thất bại.

Không nên "thêm javac bằng cách copy một file binary" vì compiler còn cần modules/libraries khác. Giải pháp là:

1. Xác nhận có thật sự cần runtime code compilation hay có thể chuyển sang build stage.
2. Nếu cần, dùng JDK runtime image hoặc custom runtime có các module/compiler được kiểm chứng.
3. Test tính năng đó trong **final image**, không chỉ ở máy developer.

**Ngoại lệ:** một thư viện có compiler riêng như Janino có thể biên dịch một dạng Java expression mà không dùng `javac`; vì vậy không kết luận tất cả "dynamic code" đều bắt buộc JDK, hãy xem implementation thực.

### 15.2 Công cụ `jar`, `jlink`, `jdeps` và debug

Các lệnh như `jlink` để tạo custom runtime, `jdeps` để phân tích module dependencies và `javac` để compile thường chỉ có trong **JDK**.

- **Tạo custom JRE bằng `jlink`:** thực hiện trong **JDK builder** rồi copy runtime được tạo vào một final image phù hợp, không mong `jlink` có sẵn trong JRE.
- **Phân tích bytecode/JAR:** có thể thực hiện tại CI hoặc build stage, không phải trong production.
- **Điều tra bằng debugger/profiler:** một số công cụ JDK như `jcmd`, `jstack`, `jmap` có thể vắng trong runtime JRE; dùng diagnostic image/sidecar hoặc image debug riêng theo quy trình.
- **Troubleshooting:** không phải lý do mặc định để ship toàn bộ toolchain vào mọi production container.

### 15.3 Custom runtime quá nhỏ thiếu Java modules

Nếu dùng `jlink` để cắt Java modules, một app có thể thiếu `java.naming`, `java.sql`, `java.management`, `java.xml`, `jdk.crypto.ec` hoặc module khác tùy dependency. Spring Boot và thư viện reflection/proxy/SSL/JDBC có thể cần module không hiển nhiên từ static analysis.

Một custom JRE phải được **test bằng app thật**, không chỉ kiểm tra `java -version`. Nếu startup/runtime feature thiếu module, đó có thể là vấn đề custom runtime, không phải Spring Boot build plugin.

### 15.4 Native image không phải JRE image

Spring Boot có thể được build thành **native executable** bằng GraalVM/Native Build Tools. Khi đó runtime image có thể **không cần JVM/JRE** nếu native executable và native libraries đã được chuẩn bị đúng. Đây là một pipeline **khác** với executable Boot JAR chạy bằng `java -jar`.

Không sao chép Dockerfile JRE của bài để chạy một file native binary rồi kết luận JRE cần thiết. Cũng không dùng GraalVM builder/JDK image để chạy native app trong production nếu kiến trúc tối ưu cho phép một runtime khác.

## 16. So sánh với Cloud Native Buildpacks và layered JAR

### 16.1 Buildpacks

Spring Boot hỗ trợ tạo OCI container image bằng Maven/Gradle build plugin kết hợp **Cloud Native Buildpacks**:

```bash
# Maven project có cấu hình/plugin phù hợp
./mvnw spring-boot:build-image

# Gradle project có Spring Boot plugin
./gradlew bootBuildImage
```

Tên image, Docker daemon và builder/run image thực tế phụ thuộc cấu hình. Buildpacks tự tổ chức giai đoạn build/launch bằng các components của builder, không yêu cầu người dùng viết Dockerfile JDK/JRE giống hệt ví dụ.

Điểm liên quan tới bài: dù dùng Dockerfile thủ công hay buildpacks, mục tiêu vẫn là **chỉ đưa những thành phần runtime cần thiết** vào image chạy app. Không suy rằng Buildpacks có image runtime chứa JDK chỉ vì nó sử dụng builder có công cụ build.

### 16.2 Spring Boot layered executable JAR

Spring Boot 3.3 hỗ trợ `BOOT-INF/layers.idx` và trích xuất nội dung thành các layer như:

```text
dependencies/
spring-boot-loader/
snapshot-dependencies/
application/
```

Các layer tách phần dependency thay đổi ít khỏi application classes thường thay đổi nhiều, giúp Docker layer caching khi đóng image. **Layered JAR là một tối ưu khác với việc dùng JDK vs JRE**:

- JDK vs JRE quyết định **Java runtime/tooling** trong các stages.
- Spring Boot layers quyết định **cách phân tách nội dung ứng dụng** trong image runtime.
- Có thể kết hợp cả hai: builder JDK tạo Boot JAR; một stage JRE/Java runtime có thể trích lớp hoặc được copy những lớp đã extract.
- Với Boot 3.3.13, tài liệu Dockerfiles dùng **`java -Djarmode=tools -jar app.jar extract`**; các bản Boot cũ dùng tên mode `layertools`, đừng trộn lệnh của phiên bản khác.

Đây là phần nâng cao; **Dockerfile Maven/Gradle hai-stage ở trên hoàn toàn hợp lệ mà không cần extraction**. Chỉ triển khai layer extraction khi đã xác minh Spring Boot plugin/loader đang tạo archive tương thích.

### 16.3 Vấn đề launch script

Một số Spring Boot executable archives có thể được cấu hình nhúng **fully executable launch script** để chạy như Unix service. Tài liệu Spring Boot cảnh báo chế độ layer extraction `tools` không tương thích với fully executable archive có launch script ở đầu. Nếu dùng Dockerfile layered, cần tắt launch script hoặc đổi phương án.

Không có lý do bật launch script chỉ để dùng `java -jar` trong Dockerfile của bài: `ENTRYPOINT ["java","-jar",...]` đã trực tiếp gọi Java runtime.

## 17. CI/CD: kiểm chứng image final chứ không chỉ builder

Một pipeline nên có các gate sau:

| Gate | Kiểm tra gì? | Vì sao cần? |
| --- | --- | --- |
| Java build/test | `mvn package`/`gradlew build` thành công | App class và tests được kiểm tra. |
| Executable artifact | Đúng Boot JAR, không phải `plain`/`original` | Runtime JRE có thể `java -jar`. |
| Image build | Docker multi-stage build thành công | Artifact được copy từ builder sang JRE stage. |
| Java runtime | `java -version` trong final image, đúng major/platform | Tránh `UnsupportedClassVersionError`. |
| Tooling absence | Không có `javac`/Maven/Gradle nếu không được yêu cầu | Xác minh stage runtime tối giản. |
| Non-root | `Config.User` và container process UID mong đợi | Giảm quyền mặc định. |
| Smoke test | HTTP `GET /hello` trả 200 và đúng body | Chứng minh app khởi động trong **JRE final image**. |
| Image scan | CVEs, dependencies/SBOM, base image policy | JRE nhỏ hơn không đồng nghĩa an toàn. |
| Provenance | Image digest, artifact hash, CI build metadata | Deploy đúng thứ đã test. |
| Runtime permissions | File/config/temp dirs writable/readable theo thiết kế | Non-root không làm app crash khi ghi tệp. |

### 17.1 Ví dụ Bash smoke test có kiểm tra HTTP body

Giả sử `container-demo:maven` đã được build. Script sau chỉ dùng cho **môi trường lab** có Docker, curl, cổng 18084 rảnh; cần tự bổ sung cleanup chính sách CI nếu nhiều job chạy song song:

```bash
#!/usr/bin/env bash
set -euo pipefail

image="container-demo:maven"
name="container-demo-ci-test"
url="http://localhost:18084/hello"

docker run --rm -d \
    --name "$name" \
    -p 18084:8080 \
    "$image" >/dev/null

cleanup() {
    docker stop "$name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

response=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    response="$(curl --fail --silent --show-error \
        --connect-timeout 2 --max-time 3 "$url" 2>/dev/null || true)"
    if [[ "$response" == "Hello from Spring Boot" ]]; then
        echo "PASS: JRE runtime image serves /hello"
        exit 0
    fi
    sleep 2
done

docker logs "$name" || true
echo "FAIL: HTTP smoke test did not become ready" >&2
exit 1
```

Khi container đã sẵn sàng và endpoint trả đúng body, **dòng script dự kiến in**:

```text
PASS: JRE runtime image serves /hello
```

Đây là stdout **có điều kiện**, không phải log đã được chạy trong môi trường người học. Nếu lỗi startup/port/container image, script sẽ fail; cần xem `docker logs`. Trong CI song song, nên dùng tên container và host port được cấp riêng cho từng job để không va chạm.

### 17.2 Kiểm tra identity của artifact và image

Có thể lấy image ID/digest theo Docker CLI:

```bash
docker image inspect container-demo:maven --format '{{.Id}}'
docker image inspect container-demo:maven --format '{{.Config.User}}'
docker image inspect container-demo:maven --format '{{.Architecture}}'
```

Nếu push image lên registry, digest của manifest **sau push** là căn cứ xác định image từ registry mà production nên pull theo chính sách. Không nên dùng mỗi tag `:latest`/`:maven` làm định danh duy nhất; tag có thể bị gán lại.

Trong multi-stage Dockerfile, các artifacts ở build stage không được tự xuất bản độc lập. Chỉ export final image sau gate và lưu log build/test cần thiết. Nếu deploy stage **rebuild** lại từ source và tag cùng tên, đó có thể không phải image đã được scan/test; hãy dùng cùng digest khi promote.

### 17.3 Security không đồng nghĩa chỉ quét final base

Cần đánh giá:

- Final image OS packages/JRE runtime.
- Application `BOOT-INF/lib` dependency JAR và CVEs tương ứng.
- Supply-chain của Maven/Gradle plugins, wrapper distribution và download sources.
- Builder stage và pipeline credentials vì nó có quyền đọc source/secret.
- Image signing/provenance và quy trình cập nhật patches.

Multi-stage tách build toolchain khỏi final runtime nhưng không khiến pipeline builder miễn nhiễm supply-chain attacks.

## 18. Windows PowerShell và người học dùng Windows

Docker Desktop có thể chạy **Linux containers** trên Windows; Dockerfile `eclipse-temurin:17-...-jammy` là image Linux. **Không** trộn với Windows container runtime nếu Docker daemon đang ở Windows containers mode hoặc OS/arch không hỗ trợ.

Build Maven image:

```powershell
docker build -f Dockerfile.maven -t container-demo:maven .
```

Build Gradle image (trên project Gradle tương ứng):

```powershell
docker build -f Dockerfile.gradle -t container-demo:gradle .
```

Chạy:

```powershell
docker run --rm -d --name container-demo-win-test -p 18080:8080 container-demo:maven
(Invoke-WebRequest -Uri "http://localhost:18080/hello").Content
docker logs container-demo-win-test
docker stop container-demo-win-test
```

Kết quả `.Content` kỳ vọng là chuỗi `Hello from Spring Boot` nếu ứng dụng chạy. Đừng đặt lệnh PowerShell `.\mvnw.cmd` hoặc `.\gradlew.bat` **bên trong Linux Dockerfile**: build stage Linux cần `./mvnw` và `./gradlew`. Ngoài Docker, Windows developer có thể dùng các Wrapper `.cmd`/`.bat` cho local compile/test.

Kiểm tra Java version:

```powershell
docker run --rm --entrypoint java eclipse-temurin:17-jre-jammy -version
docker image inspect container-demo:maven
```

Nếu `COPY mvnw` vào Linux image rồi báo `/bin/sh^M: bad interpreter`, kiểm tra Git line endings và đưa `mvnw`/`gradlew` về LF. Không thay việc đó bằng chạy Windows batch script trong Linux container.

## 19. Các lỗi thường gặp và phương pháp sửa

| Triệu chứng | Nguyên nhân đáng kiểm tra | Bằng chứng và hướng sửa |
| --- | --- | --- |
| Docker `COPY mvnw`/`COPY gradlew` báo file not found | Sai build context hoặc `.dockerignore` loại Wrapper | Chạy `docker build` từ root đúng, kiểm tra context và tên tệp |
| `./mvnw: Permission denied` | Script không executable trong Linux image | `RUN chmod +x mvnw`, sửa Git file mode nếu cần |
| `/bin/sh^M: bad interpreter` | Wrapper có CRLF trong Linux image | Sửa EOL thành LF của `mvnw`/`gradlew` |
| Maven/Gradle tải dependency rất lâu mỗi build | Cache layer invalidated, repo chậm, thiếu BuildKit cache | Copy build scripts trước source, xem cache mounts và network |
| Maven `dependency:go-offline` vẫn cần mạng ở `package` | Goal không preload mọi plugin/artifact hoặc dependency bị thay đổi | Đọc lỗi artifact cụ thể, không giả định offline tuyệt đối |
| Gradle `dependencies` không đủ để build offline | Test/plugin/annotationProcessor configuration khác | Prewarm thêm configuration phù hợp hoặc cho build mạng có kiểm soát |
| JDK builder báo `Unsupported class file major version` | Gradle/Maven/plugin/compiler chạy sai Java version | Xem `java -version` của builder, Wrapper/plugin compatibility |
| JRE runtime báo `UnsupportedClassVersionError` | Bytecode được compile cho Java mới hơn runtime | Đồng bộ toolchain/release và JRE major, build lại |
| `no main manifest attribute` hoặc thiếu Boot loader | Copy nhầm plain JAR hoặc Maven chưa repackage | Kiểm tra `jar tf`/manifest của artifact nguồn |
| Gradle COPY wildcard nhiều JAR vào file đích | Có cả `-plain.jar` và Boot JAR | Chọn chính xác output `bootJar` |
| Maven copy `.jar.original` | Đó là archive trước repackage | Chọn executable JAR đúng tên/plugin config |
| Builder có `javac` nhưng runtime không | **Đúng thiết kế** multi-stage JDK→JRE | Chỉ là lỗi nếu ứng dụng thật sự cần compile lúc runtime |
| Runtime báo không có `mvn`/`gradle` | Công cụ build không được copy sang final image | Đúng nếu production chỉ chạy `java -jar` |
| `java -jar` lỗi `NoClassDefFoundError` | Artifact thiếu runtime dependencies hoặc custom Java modules thiếu | Kiểm tra `BOOT-INF/lib`, dependency graph, JRE modules |
| App cần `ToolProvider.getSystemJavaCompiler` và gặp lỗi | JRE không có compiler module/tool | Cần JDK runtime/custom runtime phù hợp hoặc chuyển compile vào builder |
| `exec /app/start.sh: not found` trong image JRE tối giản | Shell/script không có hoặc CRLF, sai shebang | Dùng exec-form `ENTRYPOINT ["java",...]` hoặc base có shell hợp lệ |
| Container khởi động rồi tự thoát | Spring startup failure, port conflict, missing env/secret | `docker logs`, exit code, health/HTTP probe |
| HTTP 404 ở `localhost:18080/hello` | Port mapping/spring context path/controller mapping sai | Xem `-p`, `server.servlet.context-path`, route và logs |
| HTTP connection refused | Server chưa ready, sai bind address/port hoặc container đã thoát | `docker ps`/`docker logs` và polling với timeout |
| Image chạy root dù Dockerfile có user | User set ở stage khác hoặc bị override khi chạy | `docker image inspect Config.User`/runtime UID |
| `Permission denied` khi ghi `/app` | Non-root không được cấp quyền volume/dir | Cấp quyền cụ thể, mount writable dir, không chạy root bừa |
| TLS `PKIX path building failed` | Thiếu CA hoặc truststore khác giữa images | Cài CA đúng cách, không disable TLS verification |
| App lỗi JNI/native library | Base OS libc/architecture hoặc native package không tương thích | Kiểm tra platform, OS flavor, required .so/JNI |
| Image nhỏ nhưng nhiều CVE | OS package/JRE chưa vá hoặc dependency trong JAR lỗi | Scan và cập nhật digest/tag, app dependency review |
| Docker build `exec format error` trên ARM/x86 | Image hoặc native binary architecture khác | Kiểm tra `--platform` và manifest list, dùng image tương thích |
| Image final vẫn chứa build artifacts | `COPY --from=build /workspace ...` quá rộng | Chỉ copy đúng executable JAR/required runtime files |
| Đổi source nhưng image chạy code cũ | Docker cache, stage copy artifact cũ hoặc deploy nhầm tag | Xác minh SHA/image ID, build logs và artifact thật |
| App web test pass khi build nhưng JRE runtime fail | Test chỉ chạy trên JDK builder | Bắt buộc smoke test **final JRE image** |
| Image startup chậm | Warm-up/JIT, I/O, dependencies, CPU/memory limits | Đo runtime thật; đừng mặc định lỗi do JRE |
| Docker daemon không build được image Jammy trên Windows | Đang dùng Windows containers mode | Chuyển sang Linux containers hoặc dùng base tương thích OS |
| Custom `jlink` runtime lỗi module | Java modules thiếu | Kiểm tra `jdeps`, test tính năng thực, thêm modules cần thiết |
| Docker `HEALTHCHECK curl` không chạy | Runtime image thiếu curl/shell | Dùng external HTTP probe hoặc cài công cụ có chủ đích |
| Image tag thay đổi không báo | Tag mutable được publisher cập nhật | Pin digest, quản lý cập nhật/signed provenance |
| Tests bị bỏ qua trong Docker builder | Dùng Maven `-DskipTests` hay chỉ `gradlew bootJar` | Chạy CI tests riêng hoặc `mvn package`/`gradlew build` có test |

### Quy trình chẩn đoán theo bằng chứng

1. **Build stage:** dùng đúng image JDK, Wrapper hợp lệ, Java/toolchain version? Lỗi xảy ra trước hay sau `COPY src`?
2. **Artifact:** executable JAR có thật? Có Boot loader, `BOOT-INF/classes` và `BOOT-INF/lib`? Filename chính xác?
3. **COPY boundary:** final image có `/app/app.jar`, đúng byte file từ builder? Có copy dư source/cache?
4. **Runtime:** `java -version` trong JRE image đúng major và platform? Có modules, CA, native libs cần?
5. **Process:** user ID, entrypoint, filesystem permissions, environment và memory limit đúng?
6. **Network:** cổng Spring Boot lắng nghe, port mapping và HTTP endpoint đúng? App đã ready?
7. **Supply chain:** image digest, vulnerability scan và dependency/JAR provenance đã qua gate?

**Đừng sửa đồng thời Dockerfile, Java version, POM và image tag khi chưa biết lỗi thuộc tầng nào.** Thay đổi một yếu tố trong môi trường lab để đối chiếu, rồi đưa fix đã kiểm chứng vào pipeline.

## 20. Bài thực hành từ cơ bản đến nâng cao

### A. Xác định thành phần JDK/JRE

1. Pull/run `eclipse-temurin:17-jdk-jammy` và `17-jre-jammy`.
2. Gọi `java -version` trên cả hai, `javac -version` trên JDK.
3. Kiểm tra JRE có `javac` trên PATH không bằng shell command có điều kiện.
4. Ghi OS/architecture của image và giải thích ý nghĩa của `17`, `jdk`, `jre`, `jammy`.
5. Trả lời: vì sao JDK vẫn có thể chạy app mà JRE không được dùng để compile source chuẩn?

### B. Maven multi-stage

1. Tạo project `container-demo` theo POM/Java/test ở phần 4.
2. Dùng Maven Wrapper phù hợp và `Dockerfile.maven` ở phần 5.
3. Build image `container-demo:maven`.
4. Xem build log và xác nhận Maven tests chạy (không dùng `-DskipTests`).
5. Run container ở host port 18080, GET `/hello`, kiểm tra body `Hello from Spring Boot`.
6. Vào final image bằng lệnh `--entrypoint sh` của ví dụ, kiểm tra thiếu `mvn`/`javac`.
7. Giải thích vì sao Maven dependency caches ở builder không cần copy sang runtime image.

### C. Gradle multi-stage

1. Tạo project Gradle tương đương, có `settings.gradle`/`build.gradle` và Wrapper.
2. Build bằng `Dockerfile.gradle`, xác minh executable Boot JAR không phải `-plain.jar`.
3. Run container và thử `GET /hello`.
4. Thêm một Java method vô hại, build lại image để quan sát các layer Docker được reuse.
5. Trả lời: `./gradlew bootJar` khác `./gradlew build` ở điểm nào liên quan test?
6. Thử đổi `build.gradle` hoặc dependency version trên nhánh lab, ghi lý do layer dependency cache bị invalidated.

### D. Prebuilt JAR và runtime-only

1. Trên CI/local JDK, build/test project trước.
2. Copy executable artifact đã xác minh vào `release/app.jar` trong build context.
3. Dùng `Dockerfile.runtime` và bảo đảm `.dockerignore` không loại file `release/app.jar`.
4. Build image runtime-only, gọi `GET /hello` và so output với multi-stage.
5. Trả lời: cách nào dễ bảo đảm **chính cùng artifact** từ test stage được deploy nếu pipeline dùng digest?

### E. Bảo mật và quyền

1. Inspect `Config.User` của final image: phải thấy UID/GID theo Dockerfile.
2. Trong lab, thử `--read-only --tmpfs /tmp`, kiểm tra app hoạt động hoặc ghi log lỗi.
3. Giải thích vì sao không nên đưa secret vào `ARG`/`ENV` của Dockerfile.
4. Kiểm tra base image digest, CVE scan và lịch cập nhật.
5. Phân biệt giảm số packages và bảo đảm không có lỗ hổng.

### F. Thay đổi Java/runtime và phát hiện lỗi sớm

1. Ghi Java major của compiler và runtime base image.
2. Trên nhánh lab, đổi compiler target sang Java mới hơn runtime (không deploy production), quan sát `UnsupportedClassVersionError` có thể xảy ra.
3. Hoàn nguyên thành JDK/JRE cùng Java 17.
4. Giải thích vì sao Java 17 runtime không chạy bytecode target 21 mà chỉ đổi Docker tag không sửa compiler target.
5. Nếu dùng JNI/TLS, chỉ ra thêm những yếu tố ngoài Java major cần kiểm tra.

### G. Khảo sát image thực tế

Tạo một báo cáo có cấu trúc:

```text
Project name:
Build system: Maven / Gradle
Build image ref:
Runtime image ref:
Java major/toolchain target:
OS distribution/architecture:
Dockerfile path:
Build command:
Did tests run? Evidence:
Executable JAR path before copy:
Source task: bootJar / spring-boot:repackage
Final /app/app.jar exists:
Final user UID/GID:
java -version in final:
javac present in final?:
mvn/gradle present in final?:
Host port mapping:
HTTP /hello status:
HTTP /hello body:
Image digest after push:
Findings and next action:
```

**Đây là mẫu để điền giá trị đã đo**, không phải một báo cáo PASS có sẵn. Nếu không có Docker daemon, có thể hoàn thành phân tích Dockerfile và dependency graph nhưng phải ghi rõ **chưa thực thi image và HTTP smoke test**.

### H. Phân tích một Dockerfile không tối ưu

Cho Dockerfile sau:

```dockerfile
FROM eclipse-temurin:17-jdk-jammy
WORKDIR /code
COPY . .
RUN ./gradlew bootJar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/code/build/libs/container-demo-0.0.1-SNAPSHOT-plain.jar"]
```

Yêu cầu:

1. Chỉ ra vấn đề của **single-stage JDK**, `COPY . .` và không có `.dockerignore`.
2. Phân biệt `bootJar` với `build`/`test`.
3. Giải thích tại sao `-plain.jar` có thể khiến `java -jar` fail.
4. Viết lại bằng **JDK builder + JRE runtime**; chỉ copy Boot executable artifact.
5. Thêm user không phải root và kiểm tra port mapping.
6. Đưa ra ít nhất hai bằng chứng: compiler có ở builder, không cần ở runtime và HTTP endpoint của JRE image hoạt động.

**Tiêu chí đạt:** không chỉ thuộc tên `jdk`/`jre`; phải lý giải được **compiler thuộc build**, **Java runtime thuộc final**, biết **giới hạn của multi-stage**, biết chọn đúng Spring Boot executable artifact và có smoke test thật trên final JRE image.

## 21. Tài liệu chính thức

- Docker Docs — Multi-stage builds, `FROM ... AS` và `COPY --from`: https://docs.docker.com/build/building/multi-stage/
- Docker Docs — Dockerfile reference, `FROM`/`COPY`/`USER`/`EXPOSE`/`ENTRYPOINT`: https://docs.docker.com/reference/dockerfile/
- Docker Docs — Build best practices, layer caching và pin image digest: https://docs.docker.com/build/building/best-practices/
- Docker Docs — BuildKit cache mounts: https://docs.docker.com/build/cache/optimize/
- Docker Docs — `.dockerignore` và build context: https://docs.docker.com/build/building/context/#dockerignore-files
- Docker Official Image — Eclipse Temurin, JDK/JRE tags và lưu ý custom Java runtime: https://hub.docker.com/_/eclipse-temurin
- Eclipse Adoptium — Temurin containers: https://adoptium.net/installation/containers/
- Spring Boot 3.3.13 — Dockerfiles và layered JAR (`jarmode=tools`): https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html
- Spring Boot 3.3 — Gradle Plugin Packaging Executable Archives (`bootJar`): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Maven Plugin Packaging Executable Archives (`repackage`): https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Cloud Native Buildpacks: https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/cloud-native-buildpacks.html
- Oracle/OpenJDK — Java Platform Module System và `jlink`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html

**Kết luận:** image **JDK** là môi trường có Java compiler và công cụ phát triển để **build/test/package**; image **JRE** cung cấp Java runtime cần để **chạy** executable Spring Boot JAR. Docker multi-stage dùng `FROM ... AS build` và `COPY --from=build` để giữ hai trách nhiệm tách biệt. Dùng JRE final image giúp tránh mang toolchain/source/caches vào sản phẩm, nhưng **không thay thế kiểm tra tương thích Java/native modules, bảo mật, quyền truy cập, artifact identity và HTTP smoke test**. Thành công chỉ được chứng minh khi **đúng executable JAR** được build bằng JDK và **thực sự khởi động, đáp ứng request trên final JRE image**.
