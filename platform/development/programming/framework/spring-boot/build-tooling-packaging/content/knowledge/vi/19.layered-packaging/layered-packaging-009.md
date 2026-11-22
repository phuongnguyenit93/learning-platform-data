# Kiểm chứng thay đổi mã ứng dụng hoặc dependency tác động đến những lớp nào

## 1. Đề bài và kết quả cần chứng minh

Spring Boot hỗ trợ **layered executable JAR**: ngoài mã ứng dụng và các thư viện runtime, archive có thêm chỉ mục chỉ rõ nhóm file nào thuộc lớp nào. Khi container image được tạo bằng cách **trích và sao chép riêng từng lớp**, Docker/OCI builder có cơ hội tái sử dụng các lớp ít thay đổi, thay vì tải lại toàn bộ ứng dụng mỗi lần sửa một method Java.

Câu hỏi chính của bài không phải “`jar` có build thành công chưa?” mà là:

- Nếu **chỉ đổi Java class hoặc resource của ứng dụng**, lớp `application` có đổi trong khi các external libraries được giữ nguyên không?
- Nếu **nâng một external release dependency**, `dependencies` có đổi? Những file metadata nào khác có thể đổi theo?
- Khi sửa **local module dependency** hoặc external `SNAPSHOT`, nội dung được phân lớp như thế nào?
- Sự khác biệt trong **logical Spring Boot layers** có thật sự tương ứng với Docker image cache hits không?
- Làm sao dùng **hai bản build có kiểm soát**, `layers.idx`, extraction và **SHA-256 theo từng file** để trả lời bằng chứng thay vì suy đoán?

Bài viết dùng **Spring Boot 3.3.13 và Java 17**, Maven hoặc Gradle. Đây là bộ phiên bản minh họa, không phải khẳng định phiên bản mới nhất. Các kết quả “kỳ vọng” là điều người học phải tự chạy để kiểm chứng; không tuyên bố đã chạy build, Docker hay Java code trên máy người học.

## 2. Ba cấp độ “lớp” không được đánh đồng

### 2.1. Cấu trúc bên trong executable JAR

Một Spring Boot executable JAR thường gồm:

~~~text
layer-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/launch/JarLauncher.class
├── org/springframework/boot/loader/... (các loader classes khác)
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/layer/LayerDemoApplication.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-<version>.jar
    │   ├── commons-lang3-<version>.jar
    │   └── ... (các thư viện runtime)
    └── layers.idx
~~~

`BOOT-INF/classes` là mã/resource chính của ứng dụng, `BOOT-INF/lib` chứa các nested dependency JAR, còn Spring Boot Loader tại root giúp JVM nạp đúng runtime classpath khi gọi `java -jar`. `layers.idx` là **metadata về phân lớp**, không phải executable Java code.

### 2.2. Bốn logical layers mặc định của Spring Boot 3.3.13

| Layer | Thành phần điển hình | Khi nào có thể thay đổi? |
| --- | --- | --- |
| `dependencies` | External release dependencies có version không chứa `SNAPSHOT`. | Nâng/thêm/bỏ Spring Framework, Jackson, Commons Lang, driver release, v.v. |
| `spring-boot-loader` | Các class Spring Boot Loader để khởi động archive. | Đổi Spring Boot loader/plugin version hoặc layout liên quan. |
| `snapshot-dependencies` | External non-project SNAPSHOT dependencies. | Thêm/bớt/nâng/cập nhật snapshot artifacts. |
| `application` | Classes/resources của app, metadata và local project/module dependencies theo mặc định. | Sửa mã app, resource, build metadata hoặc module nội bộ. |

**Thứ tự mặc định:** `dependencies` → `spring-boot-loader` → `snapshot-dependencies` → `application`. Ý tưởng là nội dung ít đổi được đặt trước để tăng khả năng tận dụng cache. Một lớp có thể **rỗng**, nhất là `snapshot-dependencies` khi không có external SNAPSHOT.

Điểm tinh tế: một **local module JAR** vẫn có thể nằm ở `BOOT-INF/lib/core.jar` nhưng được gán vào logical layer `application`, **không** phải `dependencies`. Vị trí file trong ZIP và layer membership là hai khái niệm riêng.

### 2.3. Docker/OCI image layers

`BOOT-INF/layers.idx` **không tự tạo** OCI layers. Nếu Dockerfile chỉ làm:

~~~dockerfile
FROM eclipse-temurin:17-jre
COPY target/layer-demo-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

thì Dockerfile có **một bước COPY nguyên outer JAR**. Khi một class thay đổi, outer JAR cũng khác; Docker không tự nhìn `layers.idx` để tách các thư viện đang nằm trong ZIP.

Muốn sử dụng logical layers, cần dùng công cụ extraction (ví dụ Spring Boot jarmode tools) hoặc buildpacks hỗ trợ layering, rồi theo dõi cache **của image builder thực tế**.

**Không kết luận** “logical dependencies layer không đổi” đồng nghĩa “Docker chắc chắn cache hit mọi image layer còn lại”: cache keys còn phụ thuộc **parent layer**, Dockerfile instructions, build context, base image, build args và builder implementation.

## 3. `BOOT-INF/layers.idx` chứa thông tin gì?

`layers.idx` là danh sách lớp và đường dẫn được gán vào mỗi lớp, theo thứ tự sử dụng khi xây image. Ví dụ **minh họa**, không phải bản chụp của một JAR đã build:

~~~yaml
- "dependencies":
  - "BOOT-INF/lib/commons-lang3-3.14.0.jar"
  - "BOOT-INF/lib/spring-webmvc-6.x.y.jar"
- "spring-boot-loader":
  - "org/springframework/boot/loader/launch/JarLauncher.class"
- "snapshot-dependencies":
  - "BOOT-INF/lib/some-lib-1.0-SNAPSHOT.jar"
- "application":
  - "META-INF/MANIFEST.MF"
  - "BOOT-INF/classes/"
~~~

Index thật có thể dùng directory prefixes hoặc liệt kê các entries chi tiết theo plugin. Tập library và selected versions thay đổi tùy project. Không copy một ví dụ `6.x.y` hoặc `1.0-SNAPSHOT` làm filename thật.

Các ý nghĩa cần phân biệt:

- `layers.idx`: file nào **được gán vào lớp logic nào**.
- `classpath.idx` (nếu có): metadata **thứ tự classpath** dành cho launcher trong điều kiện áp dụng.
- `MANIFEST.MF`: `Main-Class` (thường là `JarLauncher`) và `Start-Class` (main Java application).
- `jar tf`: liệt kê entries trong outer JAR, **không mở tiếp nội dung của nested JAR**.
- `Dockerfile COPY`: chỉ khi có extraction/copy đúng mới biến grouping thành các bước container layer hữu ích.

### 3.1. Mặc định Maven và Gradle có một khác biệt quan trọng

**Maven Plugin:** phân loại **module dependencies thuộc current reactor/build** vào `application`. Một module chỉ được resolve từ Maven local repository dù GAV giống hệt, nhưng **không** tham gia current build, có thể bị xem như regular dependency.

**Gradle Plugin:** project dependencies (`implementation project(':core')`) vào `application`; **non-project dependencies** release vào `dependencies`, còn non-project SNAPSHOT vào `snapshot-dependencies`.

Do đó, không chỉ nhìn tên JAR có `SNAPSHOT` rồi quyết định layer. Hãy đọc index của **đúng artifact, đúng chế độ build**.

## 4. Thiết kế một thử nghiệm kiểm soát biến

Để chứng minh nguyên nhân, ta cần ba bản:

| Bản | Java source | Commons Lang dependency | Mục đích |
| --- | --- | --- | --- |
| **A – baseline** | Endpoint trả `v1:Layered boot`. | `3.14.0`. | Mốc để so. |
| **B – code-only** | Chỉ sửa `v1:` thành `v2:`. | Giữ `3.14.0`. | Tách ảnh hưởng thay mã ứng dụng. |
| **C – dependency-only** | **Quay về code v1 như A**. | Nâng từ `3.14.0` lên `3.15.0` (nếu repository/policy cho phép). | Tách ảnh hưởng thay external release dependency. |

Các phép so đúng là **A→B** và **A→C**. So B→C sẽ trộn hai thay đổi (code bị quay lại và dependency nâng), không chứng minh riêng nguyên nhân.

### 4.1. Ma trận giả thuyết ban đầu

| Phép thử | `dependencies` | `spring-boot-loader` | `snapshot-dependencies` | `application` |
| --- | --- | --- | --- | --- |
| A→B, chỉ Java app đổi | Dự kiến giữ nguyên. | Dự kiến giữ nguyên. | Dự kiến giữ nguyên/rỗng. | **Dự kiến thay đổi.** |
| A→C, nâng external release dependency | **Dự kiến thay đổi.** | Thường giữ nguyên khi plugin version giữ nguyên. | Thường giữ nguyên. | **Có thể** thay đổi do archive metadata/layer index. |
| Chỉ sửa `src/main/resources` | Thường không đổi. | Thường không đổi. | Thường không đổi. | Dự kiến thay đổi. |
| Chỉ sửa test source | Thường không đổi. | Thường không đổi. | Thường không đổi. | Thường không đổi nếu test output không vào artifact. |
| Thay local module `core` | Có thể không đổi. | Có thể không đổi. | Có thể không đổi. | Có thể đổi do module JAR nằm trong `application`. |
| Nâng Boot plugin/BOM | Có thể đổi. | Có thể đổi. | Có thể đổi. | Có thể đổi. |

**Lưu ý quan trọng:** không viết assertion cứng rằng “nâng dependency chỉ được làm đổi lớp dependencies”; `layers.idx`, manifest, generated build-info hoặc classpath-related metadata cũng có thể làm thay đổi layer khác. File-level diff mới là bằng chứng.

### 4.2. Điều kiện công bằng

Giữa các bản A/B/C giữ nguyên:

1. JDK vendor/version và Maven/Gradle Wrapper.
2. Spring Boot plugin version, compiler flags, resource filtering, package config (trừ dependency được thay có chủ ý).
3. Repository selection, OS/architecture, biến môi trường ảnh hưởng build.
4. Không có external SNAPSHOT bị publish lại hoặc dynamic version âm thầm đổi.
5. Không tự động inject build timestamp/random UUID vào resource/manifest.
6. Test thực chạy, package thực tạo đúng executable JAR.
7. Không dùng cùng một thư mục extraction cho hai bản.
8. Không dùng wildcard chọn nhầm `*-plain.jar`, `*.jar.original`.
9. Chụp binary A/B/C ra file riêng **trước khi lần build tiếp theo ghi đè output**.
10. Ghi resolved dependency tree để giải thích bất kỳ khác biệt nào ngoài kỳ vọng.

## 5. Java 17 application minh họa, cùng source cho Maven/Gradle

Cây file chung:

~~~text
layer-demo/
  pom.xml                  # Chọn Maven
  # hoặc settings.gradle và build.gradle nếu chọn Gradle
  src/main/java/com/example/layer/LayerDemoApplication.java
  src/main/resources/application.properties
  src/test/java/com/example/layer/LayerDemoApplicationTest.java
  captures/                # chụp A/B/C, không thuộc source release
  LayerDelta.java          # chương trình so layer độc lập, ở mục 11
~~~

### 5.1. Main application hoàn chỉnh

`src/main/java/com/example/layer/LayerDemoApplication.java`:

~~~java
package com.example.layer;

import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LayerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayerDemoApplication.class, args);
    }

    @GetMapping("/layer")
    public String layer() {
        return "v1:" + StringUtils.capitalize("layered boot");
    }
}
~~~

`StringUtils.capitalize("layered boot")` trả `Layered boot`, nên HTTP body bản A dự kiến là `v1:Layered boot`. Endpoint **thực sự sử dụng external Commons Lang**; điều này giúp phát hiện runtime JAR thiếu dependency, không chỉ kiểm tra startup.

Bản B chỉ sửa **method body**:

~~~java
return "v2:" + StringUtils.capitalize("layered boot");
~~~

Đây là mảnh thay đổi, không phải file Java độc lập. Nếu dùng B, cũng cập nhật test assertion `v1:Layered boot` thành `v2:Layered boot`.

### 5.2. Resource chính

`src/main/resources/application.properties`:

~~~properties
spring.application.name=layer-demo
server.port=8080
~~~

File này thường ở `BOOT-INF/classes/application.properties` và thuộc `application` layer. Khi muốn thử **resource-only**, sửa nó **sau khi** đã hoàn thành thí nghiệm code-only/dependency-only.

### 5.3. JUnit 5 + MockMvc test hoàn chỉnh

`src/test/java/com/example/layer/LayerDemoApplicationTest.java`:

~~~java
package com.example.layer;

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
class LayerDemoApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void layerEndpointReflectsCurrentCode() throws Exception {
        mvc.perform(get("/layer"))
           .andExpect(status().isOk())
           .andExpect(content().string("v1:Layered boot"));
    }
}
~~~

Đây là test dùng **Spring test context/MockMvc**, không mở cổng HTTP thật. Nó cần `spring-boot-starter-test`. `java -jar` smoke test ở bước sau mới kiểm chứng runtime của artifact đã đóng.

## 6. Maven POM đầy đủ và layered archive mặc định

`pom.xml`:

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
    <artifactId>layer-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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

**Tại sao file này tạo layered JAR?**

- `spring-boot-starter-parent` quản lý compatible dependency/plugin defaults và execution `repackage` khi Boot Maven Plugin được khai báo.
- `spring-boot-maven-plugin` 3.3.13 mặc định hỗ trợ layers và ghi `BOOT-INF/layers.idx` khi đóng executable JAR.
- External release `commons-lang3` thường được xếp vào `dependencies`; kiểm tra **selected version** trong `dependency:tree` và index thực tế.
- `project.build.outputTimestamp` làm ZIP entry timestamps ổn định hơn trong các plugin hỗ trợ reproducible build; vẫn không thay thế kiểm soát generated input.
- `spring-boot-starter-test` có scope `test`, không vào executable runtime JAR mặc định.
- Nếu corporate parent chỉ import BOM, phải tự khai báo version/binding của Boot plugin; BOM không tự chạy `repackage`.

Lệnh Maven (dự án đã có Maven Wrapper):

~~~bash
./mvnw -version
./mvnw clean verify
./mvnw dependency:tree
jar tf target/layer-demo-0.0.1-SNAPSHOT.jar
~~~

Không chọn `*.jar.original` do `repackage` giữ lại; đó có thể là plain JAR. Xác minh test report tại `target/surefire-reports`, không chỉ đọc dòng `BUILD SUCCESS`.

## 7. Gradle Groovy DSL đầy đủ và `bootJar`

Dùng **cùng Java files** nhưng chọn Gradle thay Maven.

`settings.gradle`:

~~~groovy
rootProject.name = 'layer-demo'
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
    implementation 'org.apache.commons:commons-lang3:3.14.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Giải thích:**

- Java plugin tạo source sets/test; Boot plugin tạo executable `bootJar` và mặc định layered archive.
- `io.spring.dependency-management` hỗ trợ Spring Boot dependency management.
- `AbstractArchiveTask` giảm nhiễu ZIP metadata (timestamps/order) để so sánh. Đây là Groovy DSL, không phải Kotlin DSL.
- Test libraries ở test configuration, không được đưa vào executable runtime JAR thông thường.
- Nếu có thêm `*-plain.jar` do Gradle `jar` tạo, chọn **đúng output `bootJar`** để kiểm chứng.
- Toolchain Java 17 chỉ có tác dụng khi môi trường cung cấp JDK tương thích hoặc provisioning phù hợp; Wrapper Gradle cũng cần tương thích.

Lệnh:

~~~bash
./gradlew --version
./gradlew clean build
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
jar tf build/libs/layer-demo-0.0.1-SNAPSHOT.jar
~~~

Kết quả của `dependencyInsight` quan trọng: nếu graph/version constraints vẫn giữ version cũ, việc sửa version declaration chưa chắc tạo thay đổi dependency layer.

## 8. Baseline A: kiểm chứng index và tạo snapshot tách biệt

### 8.1. Kiểm tra `BOOT-INF/layers.idx`

Với Maven:

~~~bash
jar tf target/layer-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/layers.idx$'
unzip -p target/layer-demo-0.0.1-SNAPSHOT.jar BOOT-INF/layers.idx
~~~

Với Gradle:

~~~bash
jar tf build/libs/layer-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/layers.idx$'
unzip -p build/libs/layer-demo-0.0.1-SNAPSHOT.jar BOOT-INF/layers.idx
~~~

`grep`/`unzip` cần có trong môi trường Bash/macOS/Linux. Windows PowerShell có thể dùng `jar tf ... | Select-String 'layers.idx'`; nếu không có `unzip`, dùng JDK `jar xf` trong **thư mục inspection riêng**.

Nếu không có `BOOT-INF/layers.idx`, kiểm tra đúng Boot executable JAR và có vô tình đặt `<layers><enabled>false</enabled></layers>` (Maven) hoặc `layered { enabled = false }` (Gradle) không. **Không tự thêm metadata giả vào archive**.

### 8.2. `jarmode=tools` của Spring Boot 3.3

Với layered archive bình thường, Spring Boot 3.3.13 thêm `spring-boot-jarmode-tools` và hỗ trợ:

~~~bash
java -Djarmode=tools -jar target/layer-demo-0.0.1-SNAPSHOT.jar help
java -Djarmode=tools -jar target/layer-demo-0.0.1-SNAPSHOT.jar list-layers
~~~

Gradle dùng path `build/libs/...jar` tương ứng. Đây là **`tools` mode**, không sao chép `-Djarmode=layertools` từ các hướng dẫn Spring Boot cũ mà không kiểm tra version.

**Ngoại lệ:** `jarmode=tools` không dùng được với **fully executable archive đã prepend launch script**. Nếu project bật Gradle `launchScript()` hoặc Maven `executable`, tạo một executable archive tiêu chuẩn không có script để dùng tools mode. Nếu dự án tắt `includeTools`/jarmode tools, hãy dùng công cụ inspection khác theo tài liệu version.

### 8.3. Chụp A, extract ra thư mục riêng

Maven:

~~~bash
mkdir -p captures
./mvnw clean verify
cp target/layer-demo-0.0.1-SNAPSHOT.jar captures/A.jar

java -Djarmode=tools -jar captures/A.jar list-layers
java -Djarmode=tools -jar captures/A.jar \
  extract --layers --destination captures/A-layers
~~~

Gradle thay phần build/copy:

~~~bash
mkdir -p captures
./gradlew clean build
cp build/libs/layer-demo-0.0.1-SNAPSHOT.jar captures/A.jar

java -Djarmode=tools -jar captures/A.jar list-layers
java -Djarmode=tools -jar captures/A.jar \
  extract --layers --destination captures/A-layers
~~~

**Kỳ vọng:** thư mục `captures/A-layers` có nội dung của các nhóm `dependencies`, `spring-boot-loader`, `snapshot-dependencies` (có thể rỗng) và `application`. Không tái sử dụng cùng destination khi extract B/C. `java -Djarmode=tools -jar ... extract --layers --destination ...` là lệnh hỗ trợ extraction của Boot 3.3.

## 9. Bản B: thay **chỉ mã ứng dụng**

Giữ POM/Gradle build scripts và dependency versions như A. Sửa Java method:

~~~java
// Bản B, thay đúng nội dung return trong layer()
return "v2:" + StringUtils.capitalize("layered boot");
~~~

Cập nhật test expectation thành `v2:Layered boot`, vì test `src/test` không được đóng trong runtime archive theo mặc định. Không sửa application.properties, plugin version, resource generation hoặc các dependencies khác.

Maven:

~~~bash
./mvnw clean verify
cp target/layer-demo-0.0.1-SNAPSHOT.jar captures/B.jar
java -Djarmode=tools -jar captures/B.jar \
  extract --layers --destination captures/B-layers
~~~

Hoặc Gradle:

~~~bash
./gradlew clean build
cp build/libs/layer-demo-0.0.1-SNAPSHOT.jar captures/B.jar
java -Djarmode=tools -jar captures/B.jar \
  extract --layers --destination captures/B-layers
~~~

**Dự đoán:** `BOOT-INF/classes/com/example/layer/LayerDemoApplication.class` đổi, nên `application` đổi. Ba lớp còn lại **dự kiến** không đổi nếu toàn bộ input khác giữ nguyên. Không coi đây là kết quả thực tế cho tới khi chạy so sánh file-level ở mục 11.

### 9.1. Runtime smoke cho B

~~~bash
java -jar captures/B.jar --server.port=18085
~~~

Sau khi server ready, terminal thứ hai:

~~~bash
curl -i http://localhost:18085/layer
~~~

**Kỳ vọng** HTTP 200 và body `v2:Layered boot`. Dừng app bằng Ctrl+C trước khi chạy A/C ở cùng port. Việc test qua `java -jar` quan trọng vì chỉ build/test không chứng minh executable artifact đã đóng đúng.

## 10. Bản C: nâng **chỉ external release dependency**

Trước khi nâng dependency, **khôi phục production source/test từ A**: `"v1:"` và expected `v1:Layered boot`. Không so B→C để suy ra tác động riêng của dependency, vì hai bản khác nhau cả code lẫn version.

Trong Maven POM sửa một khai báo thành:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.15.0</version>
</dependency>
~~~

Trong Gradle Groovy DSL sửa thành:

~~~groovy
implementation 'org.apache.commons:commons-lang3:3.15.0'
~~~

Đây là **các mảnh thay thế** cho khai báo đã có ở mục 6/7, không phải POM/Groovy file độc lập. Nếu version này không được approved repository cho phép, chọn một release version thực sự có thể resolve, nêu rõ version đó và sử dụng cùng nguyên tắc.

Maven:

~~~bash
./mvnw clean verify
./mvnw dependency:tree
cp target/layer-demo-0.0.1-SNAPSHOT.jar captures/C.jar
java -Djarmode=tools -jar captures/C.jar \
  extract --layers --destination captures/C-layers
~~~

Hoặc Gradle:

~~~bash
./gradlew clean build
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
cp build/libs/layer-demo-0.0.1-SNAPSHOT.jar captures/C.jar
java -Djarmode=tools -jar captures/C.jar \
  extract --layers --destination captures/C-layers
~~~

**Dự đoán:** nếu selected version thực sự đổi từ 3.14.0 sang 3.15.0, các entries `BOOT-INF/lib/commons-lang3-...jar` trong `dependencies` thay đổi. `spring-boot-loader` thường ổn định vì Boot plugin version không đổi. `application` **có thể** đổi do regenerated `layers.idx`/manifest/build metadata, dù Java production class không đổi.

**Điều kiện cần:** xác minh selected version qua `dependency:tree` (Maven) hoặc `dependencyInsight` (Gradle) và liệt kê `BOOT-INF/lib` của file C. Requested version trong build script **không tự chứng minh** archive đã dùng version đó nếu có BOM/constraints/conflicts.

## 11. Công cụ Java 17: so SHA-256 từng file ở từng lớp

So hash của **outer JAR** chỉ nói “archive khác”. Ta cần biết **file nào, ở layer nào**, nên trích A/B/C rồi chạy một chương trình Java độc lập.

`LayerDelta.java`, **biên dịch với Java 17 không cần Spring classpath**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

public final class LayerDelta {
    private static final List<String> LAYERS = List.of(
            "dependencies", "spring-boot-loader",
            "snapshot-dependencies", "application"
    );

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java LayerDelta <before-dir> <after-dir>");
            System.exit(2);
        }

        Path before = Path.of(args[0]).toAbsolutePath().normalize();
        Path after = Path.of(args[1]).toAbsolutePath().normalize();
        if (!Files.isDirectory(before) || !Files.isDirectory(after)) {
            throw new IllegalArgumentException(
                    "Both paths must be extracted layer directories");
        }

        for (String layer : LAYERS) {
            SortedMap<String, String> oldFiles = files(before.resolve(layer));
            SortedMap<String, String> newFiles = files(after.resolve(layer));
            SortedSet<String> all = new TreeSet<>(oldFiles.keySet());
            all.addAll(newFiles.keySet());

            List<String> changed = new ArrayList<>();
            for (String name : all) {
                if (!oldFiles.containsKey(name)) {
                    changed.add("+ " + name);
                } else if (!newFiles.containsKey(name)) {
                    changed.add("- " + name);
                } else if (!Objects.equals(oldFiles.get(name), newFiles.get(name))) {
                    changed.add("~ " + name);
                }
            }

            System.out.printf("%s: %s (old=%d, new=%d, changed=%d)%n",
                    layer,
                    changed.isEmpty() ? "UNCHANGED" : "CHANGED",
                    oldFiles.size(), newFiles.size(), changed.size());
            changed.stream().limit(12)
                    .forEach(s -> System.out.println("  " + s));
            if (changed.size() > 12) {
                System.out.println("  ... more changes omitted");
            }
        }
    }

    private static SortedMap<String, String> files(Path root)
            throws Exception {
        SortedMap<String, String> result = new TreeMap<>();
        if (!Files.isDirectory(root)) {
            return result;
        }

        try (Stream<Path> stream = Files.walk(root)) {
            for (Path file : stream.filter(Files::isRegularFile).toList()) {
                String relative = root.relativize(file)
                        .toString().replace('\\', '/');
                MessageDigest sha = MessageDigest.getInstance("SHA-256");

                try (InputStream input = Files.newInputStream(file)) {
                    byte[] buffer = new byte[8192];
                    int n;
                    while ((n = input.read(buffer)) != -1) {
                        if (n > 0) {
                            sha.update(buffer, 0, n);
                        }
                    }
                }

                result.put(relative, HexFormat.of().formatHex(sha.digest()));
            }
        }
        return result;
    }
}
~~~

**Cơ chế:** program lấy **đường dẫn tương đối bên trong mỗi layer**, tính SHA-256 từ bytes của file và phân loại: `+` là file mới; `-` là file biến mất; `~` là cùng path nhưng nội dung đổi. Nó không so timestamp của file sau extraction, nên giảm nhiễu giữa thư mục A/B/C.

Vì `Path.of`, `Stream.toList` và `HexFormat` đều có trên Java 17, source này chạy được độc lập với Maven/Gradle project. Nên thực thi trong thư mục local đáng tin và chỉ extract archives đã được kiểm tra nguồn.

Build tool audit và thực thi:

~~~bash
javac LayerDelta.java

# Chỉ đổi mã ứng dụng:
java LayerDelta captures/A-layers captures/B-layers

# Chỉ nâng dependency:
java LayerDelta captures/A-layers captures/C-layers
~~~

Mẫu kỳ vọng **A→B** (số file và paths thực phải lấy từ kết quả chạy):

~~~text
dependencies: UNCHANGED (old=..., new=..., changed=0)
spring-boot-loader: UNCHANGED (old=..., new=..., changed=0)
snapshot-dependencies: UNCHANGED (old=0, new=0, changed=0)
application: CHANGED (old=..., new=..., changed=...)
  ~ BOOT-INF/classes/com/example/layer/LayerDemoApplication.class
~~~

Mẫu kỳ vọng **A→C**: có `dependencies: CHANGED`, đường dẫn Commons Lang release cũ bị xóa và JAR mới được thêm. **Không ép application phải UNCHANGED**; nếu có metadata khác, báo cáo đúng những file đã đổi.

### 11.1. Giới hạn công cụ

- Chỉ xử lý **bốn layer mặc định**. Nếu custom layers tạo `company-dependencies`, phải thêm tên layer và kiểm tra `layers.idx` thực trước khi chạy.
- Không đo Docker image digests/cache hits; layer extractor file contents không đồng nghĩa image builder chắc chắn cache.
- Không xác minh chữ ký cryptographic hay CVE; SHA-256 ở đây so A/B, không so với trust baseline của publisher.
- Không kiểm tra runtime/business correctness; phải chạy `java -jar` hoặc job smoke riêng.
- Nếu extraction directory chứa file cũ do extract đè, diff có thể sai; luôn dùng đường dẫn **mới, độc lập**.
- Không theo dõi symbolic links hoặc special files như regular files; dùng archives tin cậy và môi trường cách ly khi cần.
- Nếu file chỉ thay bytecode vì JDK/compiler khác, kết quả báo **đúng là có thay đổi**, nhưng nguyên nhân có thể không phải business logic.

## 12. Cách diễn giải kết quả A→B và A→C

### 12.1. A→B: `application` là tác động mong đợi

Một thay đổi method body của `LayerDemoApplication` phải làm classfile thay, nên `application` layer thường `CHANGED`. Các external release dependencies và Boot Loader giữ nguyên khi build inputs không đổi.

Nếu `dependencies` cũng đổi:

1. Xem `dependency:tree` hoặc `dependencyInsight` để xác định selected version có khác không.
2. Đọc `BOOT-INF/layers.idx` để xem file còn cùng ownership không.
3. So nested JAR hash/path qua `LayerDelta`: thêm, mất, hay cùng tên khác bytes?
4. Xem có external SNAPSHOT/changing dependency hoặc repository mirror rewrite không.
5. So plugin/BOM/JDK/build profile/resource generation giữa A và B.
6. Đối chiếu chính xác captures: có nhầm file vừa bị build lại hay dùng sai path không?

### 12.2. A→C: external dependency đổi không có nghĩa mọi class đổi

Đổi Commons Lang từ một release version sang release khác thường làm `dependencies` đổi. `LayerDelta` có thể in:

~~~text
dependencies: CHANGED (...)
  - BOOT-INF/lib/commons-lang3-3.14.0.jar
  + BOOT-INF/lib/commons-lang3-3.15.0.jar
~~~

Đó là mẫu diễn giải, không phải stdout chắc chắn của project nếu selected versions khác. Một metadata/index có thể khiến `application` đổi **dù `LayerDemoApplication.class` giống byte-for-byte**. Hãy tách câu trả lời: “business classes có đổi không?” và “logical application layer contents có đổi không?”.

### 12.3. Test-only và resource-only

- **Sửa test source/test resources:** không được đưa vào Boot executable archive theo cấu hình bình thường. Nếu JAR/layers đổi, điều tra plugin task custom, generated metadata hoặc các input không được kiểm soát.
- **Sửa `src/main/resources`:** được copy vào `BOOT-INF/classes`; thường làm `application` đổi. Kiểm tra resource filtering/processResources trước khi kết luận file thật được đóng đúng.
- **Bật profile khác ở runtime:** không tự làm JAR/layer contents đổi. Nhưng nếu build script chủ động filter profile-specific resource vào archive, đây là một thay đổi build content và phải được mô tả riêng.

## 13. Multi-module và SNAPSHOT: hai trường hợp cần nhớ

### 13.1. Gradle project dependency

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

Gradle Boot Plugin thường xếp **project dependencies** vào `application`. JAR `core-...jar` vẫn là một nested file trong `BOOT-INF/lib`, nhưng logical owner là `application`. Vì vậy **sửa source của `core`** có thể làm `application` thay dù app classes không đổi.

### 13.2. Maven local module dependency

Maven Boot Plugin xem local module tham gia **current reactor build** như ứng viên của `application` layer. Nếu app chỉ lấy artifact `core` từ local Maven repository mà không build core như module hiện tại, plugin có thể phân loại `core` thành regular dependency. Hãy dùng đúng quy trình reactor của CI để dự đoán layer membership.

### 13.3. External SNAPSHOT

Một external JAR `some-lib-1.0-SNAPSHOT.jar` thường vào `snapshot-dependencies` theo default. Nhưng một **Gradle project dependency** có version `SNAPSHOT` vẫn thuộc `application` do project relationship. Tương tự một Maven module nội bộ của reactor có thể vào `application`.

Lockfile chỉ giữ tọa độ version, không chứng minh bytes của một mutable SNAPSHOT không bị thay. Với release reproducibility nên dùng immutable artifacts, approved repositories và verification/provenance policy tương ứng.

### 13.4. Nâng Spring Boot version là một thí nghiệm **nhiều biến**

Nâng Boot plugin/BOM có thể đồng thời thay `spring-boot-loader`, thư viện Spring/embedded server trong `dependencies`, jarmode tools, manifest/index và có thể cả application output. Không đặt quy tắc “nâng Spring Boot chỉ làm đổi loader”. Đọc diff thực và release notes.

## 14. Dockerfile sử dụng Spring Boot jarmode tools

Spring Boot 3.3 có `spring-boot-jarmode-tools`. Một Dockerfile nhiều giai đoạn có thể trích và copy từng layer để xây image:

~~~dockerfile
FROM eclipse-temurin:17-jre AS extractor
WORKDIR /builder

ARG JAR_FILE=target/layer-demo-0.0.1-SNAPSHOT.jar
COPY ${JAR_FILE} application.jar

RUN java -Djarmode=tools -jar application.jar \
    extract --layers --destination extracted

FROM eclipse-temurin:17-jre
WORKDIR /application

COPY --from=extractor /builder/extracted/dependencies/ ./
COPY --from=extractor /builder/extracted/spring-boot-loader/ ./
COPY --from=extractor /builder/extracted/snapshot-dependencies/ ./
COPY --from=extractor /builder/extracted/application/ ./

ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

**Điều cần hiểu:**

- Stage extractor gọi `jarmode=tools` từ chính **executable JAR** đã build. Nếu project tắt jarmode tools hoặc bật fully executable launch script, cách này có thể không áp dụng.
- Stage cuối **không copy nguyên outer executable JAR**; nó dùng extracted layout do tools chuẩn bị, trong đó `application.jar` và các paths khác đã được tổ chức để khởi chạy. Đây là mẫu có trong tài liệu Spring Boot 3.3.
- Mỗi `COPY --from=extractor` là một Dockerfile step riêng. Copy dependencies trước, application sau để tăng khả năng cache.
- Docker base image `eclipse-temurin:17-jre` chỉ là ví dụ; sản phẩm thật phải dùng base image/tag/digest đã được tổ chức phê duyệt.
- Nếu custom layers có lớp mới, phải thêm `COPY` tương ứng và kiểm tra path/ENTRYPOINT. Không bỏ file vì lớp mới chưa có trong Dockerfile.
- Không đưa secrets vào Dockerfile, build args hoặc application resources để “tối ưu cache”.
- Không tuyên bố cache hit chỉ từ layer index. Docker cache còn phụ thuộc build context, parent layers, Dockerfile, BuildKit settings và registry.

Ví dụ build Docker cho Maven artifact:

~~~bash
docker build --progress=plain -t layer-demo:a .
~~~

Với Gradle artifact:

~~~bash
docker build --progress=plain \
  --build-arg JAR_FILE=build/libs/layer-demo-0.0.1-SNAPSHOT.jar \
  -t layer-demo:a .
~~~

Đây là lệnh cho môi trường Docker được phép. Để so A/B, bảo đảm mỗi lần build context chứa đúng artifact A hoặc B ở path đã khai báo và giữ base image, Dockerfile và builder settings giống nhau. Ghi logs của **từng `COPY` step**, không đoán hiệu quả cache từ timestamp.

### 14.1. Logical layers và OCI layers có thể khác nhau dù nội dung giống

Một bước `COPY` của Docker có thể không cache hit vì parent layer đổi, dù bytes nó copy giống nhau; một builder khác có thể tái sử dụng content-addressed blobs. Kiểm tra `docker build --progress=plain` và image manifest/digest thực để đánh giá.

Nếu Dockerfile chỉ `COPY app.jar`, một thay đổi nhỏ ở app sẽ khiến input của bước ấy thay. Trong trường hợp đó Spring Boot `layers.idx` **không được dùng để chia các Dockerfile steps**, vì vậy không thể suy cache optimization chỉ dựa trên việc JAR có index.

## 15. Khi nào cần tùy biến layers?

Default layering thường đã hợp lý. Chỉ cần custom khi có nhóm dependency có tần suất cập nhật khác, đo được cache behavior hoặc chính sách phát hành cần chia thêm layer.

### 15.1. Maven custom `layers.xml`

Spring Boot Maven Plugin có thể tham chiếu file riêng trong plugin `<configuration>`:

~~~xml
<configuration>
    <layers>
        <enabled>true</enabled>
        <configuration>src/layers/layers.xml</configuration>
    </layers>
</configuration>
~~~

File `src/layers/layers.xml` ví dụ (dùng trong Maven 3.3):

~~~xml
<layers xmlns="http://www.springframework.org/schema/boot/layers"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.springframework.org/schema/boot/layers
          https://www.springframework.org/schema/boot/layers/layers-3.3.xsd">
    <application>
        <into layer="spring-boot-loader">
            <include>org/springframework/boot/loader/**</include>
        </into>
        <into layer="application"/>
    </application>
    <dependencies>
        <into layer="application">
            <includeModuleDependencies/>
        </into>
        <into layer="snapshot-dependencies">
            <include>*:*:*SNAPSHOT</include>
        </into>
        <into layer="company-dependencies">
            <include>com.example:*</include>
        </into>
        <into layer="dependencies"/>
    </dependencies>
    <layerOrder>
        <layer>dependencies</layer>
        <layer>spring-boot-loader</layer>
        <layer>snapshot-dependencies</layer>
        <layer>company-dependencies</layer>
        <layer>application</layer>
    </layerOrder>
</layers>
~~~

Các `<into>` rules được đánh giá theo **thứ tự xuất hiện**. Local module dependencies đã bị `includeModuleDependencies` nhận trước sẽ không tự chuyển sang `company-dependencies`. `layerOrder` phải liệt kê đầy đủ các tên đã dùng, nhưng thứ tự **đánh giá include rules** khác thứ tự **ghi layers**.

### 15.2. Gradle custom layer DSL

Mảnh Groovy `build.gradle`:

~~~groovy
tasks.named('bootJar') {
    layered {
        application {
            intoLayer('spring-boot-loader') {
                include 'org/springframework/boot/loader/**'
            }
            intoLayer('application')
        }
        dependencies {
            intoLayer('application') {
                includeProjectDependencies()
            }
            intoLayer('snapshot-dependencies') {
                include '*:*:*SNAPSHOT'
            }
            intoLayer('company-dependencies') {
                include 'com.example:*'
            }
            intoLayer('dependencies')
        }
        layerOrder = [
            'dependencies',
            'spring-boot-loader',
            'snapshot-dependencies',
            'company-dependencies',
            'application'
        ]
    }
}
~~~

Khi có `company-dependencies`, **cập nhật LayerDelta.java** để audit cả lớp này và Dockerfile để `COPY` lớp mới. Nếu không, báo cáo có thể bỏ sót file dù build/JAR hoạt động đúng.

Đừng sửa layers.xml/Gradle DSL **trong cùng lần** kiểm chứng code-only hoặc dependency-only vì nó tạo một biến mới: file có thể chuyển lớp dù bytes không đổi.

## 16. Sai lệch thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Bước kiểm chứng đúng |
| --- | --- | --- |
| `BOOT-INF/layers.idx` không có. | Plain JAR, layers disabled, plugin/config sai. | Xem `jar tf`, `repackage`/`bootJar` và file output thật. |
| `java -Djarmode=tools` không chạy. | Thiếu tools dependency, launch script, dùng sai Boot version. | Xem `help`, manifest, cấu hình executable/includeTools. |
| Sửa Java app nhưng `dependencies` CHANGED. | Dynamic/SNAPSHOT dependency, repository rewrite, selected graph đổi hoặc capture sai. | Diff resolved graph, nested JAR path/hash và source của artifact. |
| Nâng Commons Lang nhưng `dependencies` không đổi. | Selected version không đổi do constraints/lockfile, package cũ. | `dependencyInsight`/`dependency:tree`, `BOOT-INF/lib`, `layers.idx`. |
| App code không đổi nhưng `application` CHANGED. | Build-info timestamp, manifest, layer index, generated resource. | Xem tên file `~`/`+`/`-` từ LayerDelta, so inputs. |
| Core project JAR đổi nhưng `dependencies` không đổi. | Local project/module được gán `application`. | Đọc layer index và build relationship. |
| SNAPSHOT đổi nhưng không thấy `snapshot-dependencies`. | Đó là local project/module hoặc custom layers. | Kiểm tra graph và index. |
| Chỉ thay unit test nhưng packaged JAR đổi. | Test output bị copy vào main, generated metadata hoặc build không tái lập. | So `BOOT-INF/classes`, resource processing, archive timestamps. |
| Docker không có cache hit khi app đổi. | Copy nguyên JAR, parent layer khác, context/base/builder đổi. | Đọc Dockerfile, logs `--progress=plain` và image digest. |
| Java audit không báo lớp custom. | Danh sách `LAYERS` chỉ gồm bốn mặc định. | Mở `list-layers`, bổ sung tên custom. |
| Extraction A/B cho kết quả kỳ lạ. | Dùng chung destination hoặc extract đè file cũ. | Tạo dirs mới, xác định đúng A/B artifact, chạy lại với input tách biệt. |
| Image chạy fail dù nguyên JAR chạy. | Thiếu `COPY` một lớp, sai path/launcher/JDK. | Xem extracted tree, Dockerfile và runtime container logs. |
| Hash outer JAR đổi dù content logic ít khác. | ZIP timestamps/order, metadata hoặc generated resources. | So per-file digests từ extracted layers thay vì chỉ JAR hash. |
| `application.properties` có secret trong image. | Layering không loại secret, chỉ nhóm files. | Không commit secrets; scan/rotate theo chính sách. |
| Build dùng `*-plain.jar`. | Gradle tạo nhiều artifacts/classifiers. | Chọn output `bootJar` và kiểm tra Boot Loader/layers.idx. |

### 16.1. Thứ tự điều tra nên áp dụng

1. **Đúng file executable JAR chưa?** Manifest và `BOOT-INF` xác nhận.
2. **Index có thật không?** Đọc `BOOT-INF/layers.idx`.
3. **Dependency selected version có đổi?** Maven tree/Gradle insight.
4. **Tools mode đã extract đúng artifact vào directory sạch?**
5. **SHA-256 theo file** chỉ ra lớp nào, file nào thay?
6. **Generated metadata/timestamps** có tạo nhiễu?
7. **Runtime** `java -jar` và HTTP/job smoke còn đạt?
8. **OCI image** có dùng extraction và cache không? Lấy log thật.
9. Có rủi ro **vulnerability/license/secrets** do dependency/resource đổi không?

Không tự xóa file trong ZIP, tắt test hoặc đổi layer order chỉ để có một báo cáo CHANGED/UNCHANGED “đẹp”.

## 17. Bài thực hành cuối và tiêu chí đạt

### Bài A — baseline A

1. Tạo Java 17 Spring Boot project ở mục 5 và POM/Gradle build ở mục 6/7.
2. Chạy tests thật, xác nhận test report có bài `layerEndpointReflectsCurrentCode`.
3. Build executable JAR; kiểm tra `BOOT-INF/classes`, `BOOT-INF/lib` và `BOOT-INF/layers.idx`.
4. Dùng jarmode tools `list-layers`, extract A vào `captures/A-layers`.
5. Lưu A.jar và selected dependency graph.
6. Chạy `java -jar captures/A.jar --server.port=18085`, gọi `/layer`; kỳ vọng HTTP 200/`v1:Layered boot`.

### Bài B — code-only B

1. Chỉ đổi Java return prefix `v1` thành `v2` và sửa test assertion cho khớp.
2. Build cùng toolchain/config, giữ dependency version.
3. Chụp B.jar, extract vào `captures/B-layers`.
4. Chạy `java LayerDelta captures/A-layers captures/B-layers`.
5. Nộp danh sách lớp changed/unchanged và file-level evidence.
6. HTTP smoke B phải trả `v2:Layered boot`.

### Bài C — dependency-only C

1. Quay Java source/test về A.
2. Chỉ nâng Commons Lang từ `3.14.0` lên `3.15.0` hoặc release approved khác.
3. Kiểm tra resolved graph, test, capture C.jar và extract riêng.
4. Chạy `java LayerDelta captures/A-layers captures/C-layers`.
5. Xác minh nested Commons Lang JAR và `layers.idx` thực.
6. Báo mọi metadata/application layer changes nếu có, không giấu để khớp dự đoán.

### Bài D — resource-only, project module và Docker

1. Chỉ sửa `application.properties` và kiểm tra impact `application`.
2. Nếu có multi-project, thử sửa `core`; xem local dependency thuộc layer nào.
3. Nếu dùng external SNAPSHOT, giải thích vì sao thay SNAPSHOT có thể thuộc `snapshot-dependencies`, nhưng không đưa changing artifact chưa kiểm soát vào release.
4. Nếu có Docker, build image A/B cùng Dockerfile & base image, lưu `--progress=plain` logs và cache evidence.
5. So logical file-level differences với OCI cache results, nêu rõ các điều kiện gây cache miss.

### Checklist đánh giá

- [ ] Giải thích được `BOOT-INF/layers.idx` khác `BOOT-INF/lib` và Docker image layer.
- [ ] Kể đúng bốn default layers và thứ tự.
- [ ] Hiểu local Maven modules/Gradle project dependencies thường nằm `application`.
- [ ] Phân biệt external release với external SNAPSHOT.
- [ ] Có Maven `repackage` hoặc Gradle `bootJar`, JDK/Wrapper được kiểm soát.
- [ ] Biết đọc index bằng `unzip -p` hoặc `jar xf`.
- [ ] Dùng đúng `java -Djarmode=tools -jar ... list-layers/extract` cho Boot 3.3.
- [ ] Chụp A/B/C và extract ra ba dirs riêng, không overwrite.
- [ ] So files bằng path tương đối + SHA-256; không chỉ hash toàn JAR.
- [ ] Biết code-only dự kiến đổi `application`, dependency-only thường đổi `dependencies` nhưng metadata có thể làm lớp khác đổi.
- [ ] Biết test-only changes không mặc nhiên vào runtime archive.
- [ ] Chạy `java -jar` và HTTP smoke để xác minh artifact vẫn hoạt động.
- [ ] Không suy “có layers.idx” đồng nghĩa “Docker đã cache bốn layers”.
- [ ] Biết multi-stage Dockerfile COPY tách layers và đọc cache logs.
- [ ] Biết tại sao JDK, plugin, timestamp và generated inputs gây nhiễu.
- [ ] Nếu custom layers, cập nhật auditor/Dockerfile/QA theo index thật.
- [ ] Không đưa credentials vào JAR/image, biết rằng layering không bảo vệ secret.

**Tiêu chí hoàn thành:** người học nộp ba artifacts A/B/C, ba extracted directories, `layers.idx` và output `LayerDelta` cho A→B/A→C, dependency reports, kết quả test JUnit, `java -jar` HTTP smoke. Phần kết luận nêu **lớp nào, file nào thực sự thay, tại sao**, và phân biệt điều đó với Docker cache thực tế. Nếu không có Docker, ghi rõ “OCI cache chưa được kiểm chứng” thay vì tự kết luận cache hit.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Maven Plugin: Layered Jar or War](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3.13 — Gradle Plugin: Packaging Layered Jar or War](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3.13 — Efficient Container Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/efficient-images.html)
- [Spring Boot 3.3.13 — Dockerfiles and Jarmode Tools](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Gradle — Building Java/JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Docker — Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker — Build Cache](https://docs.docker.com/build/cache/)

**Ghi nhớ:** hãy **đọc layer index → tạo A/B/C có kiểm soát → extract → so file-level SHA-256 → kiểm chứng packaged runtime → đo Docker cache khi cần**. Không suy tác động của một lần sửa code hay dependency chỉ từ hash của toàn JAR hoặc một dòng `BUILD SUCCESS`.