# Xây dựng cùng một ứng dụng bằng Maven và Gradle rồi đối chiếu sản phẩm

## 1. Mục tiêu thực hành

Một ứng dụng Spring Boot có thể được build bằng **Maven** hoặc **Gradle**. Cả hai đều có thể biên dịch mã Java, chạy tests, resolve dependencies và tạo executable JAR để khởi chạy bằng **java -jar**.

Bài thực hành này dùng **một bộ source code duy nhất** và tạo hai cấu hình build cho cùng một ứng dụng. Ta sẽ:

1. Khóa cùng Java, Spring Boot và dependencies.
2. Tạo cấu hình Maven POM và Gradle Kotlin DSL.
3. Build, test và đóng gói ứng dụng bằng từng công cụ.
4. So sánh dependency graph, tên file, thư mục output, manifest và nội dung JAR.
5. Chạy cả hai artifact và kiểm tra cùng một HTTP response.
6. Đối chiếu kích thước, checksum, reproducibility và build time.
7. Rút ra những khác biệt có ý nghĩa khi chọn công cụ cho dự án.

**Không đặt mục tiêu hai JAR phải có SHA-256 giống nhau.** Maven và Gradle dùng plugin, thứ tự xử lý, metadata và cách đóng gói riêng. Hai artifact có thể khác bytes nhưng vẫn có cùng ứng dụng, cùng dependency set và hành vi runtime. Ta cần kiểm tra đúng từng lớp của sản phẩm.

## 2. Ma trận phiên bản và điều kiện so sánh

Dùng một bộ phiên bản được Spring Boot 3.5.16 hỗ trợ:

| Thành phần | Phiên bản dùng trong bài | Lý do |
| --- | --- | --- |
| Java | 17 | Spring Boot 3.5.16 yêu cầu Java 17 trở lên |
| Spring Boot | 3.5.16 | Cùng dependency management và loader |
| Maven Wrapper | 3.9.9 | Cao hơn mức tối thiểu Maven 3.6.3 |
| Gradle Wrapper | 8.14.3 | Nằm trong nhánh Gradle 8.x, đáp ứng yêu cầu 8.4 trở lên |
| Gradle DSL | Kotlin DSL | Cấu hình trong build.gradle.kts |
| Packaging | Executable JAR | Cả hai artifact chạy bằng java -jar |
| Application | Spring MVC | Cùng endpoint và test |

Spring Boot 3.5.16 hỗ trợ Maven 3.6.3 trở lên và Gradle 7.6.4 trở lên trong nhánh 7.x hoặc 8.4 trở lên trong nhánh 8.x. Kiểm tra version chính xác trước khi chạy; không dựa vào Maven/Gradle cài global nếu project đã có Wrapper.

Để so sánh công bằng, giữ những yếu tố sau giống nhau:

- Cùng source files và resources.
- Cùng Java major version; tốt hơn nữa là cùng JDK vendor và patch release.
- Cùng Spring Boot version và cùng versions của dependencies.
- Cùng profile, environment variables và application arguments.
- Cùng repository, mạng và trạng thái cache khi đo thời gian.
- Cùng test suite và tiêu chí build thành công.
- Cùng loại artifact: executable JAR so với executable JAR.

Nếu Maven dùng Spring Boot 3.5.16 còn Gradle dùng 3.4.x, hoặc một bên thêm dependency khác, kết quả so sánh không còn cô lập được ảnh hưởng của build tool.

## 3. Cấu trúc dự án chung

Đặt hai file build ở cùng thư mục gốc. Source code chỉ tồn tại một lần:

~~~text
build-compare/
├── pom.xml
├── settings.gradle.kts
├── build.gradle.kts
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       ├── maven-wrapper.properties
│       └── ...
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/buildcompare/
    │   │   ├── BuildCompareApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/buildcompare/
            └── HelloControllerTest.java
~~~

Maven và Gradle đều dùng layout chuẩn **src/main/java**, **src/main/resources** và **src/test/java**. Không tạo hai bản source khác nhau để tránh trường hợp một build có code mới hơn build còn lại.

Tạo Maven Wrapper và Gradle Wrapper bằng các lệnh sau khi đã cài công cụ tương ứng lần đầu:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
~~~

Sau đó commit cả Wrapper scripts và các file cấu hình Wrapper vào repository. Người clone project có thể build mà không cần cài Maven/Gradle global, miễn là có JDK phù hợp và quyền tải distribution.

Trên Windows dùng **mvnw.cmd** và **gradlew.bat**. Trên Linux/macOS dùng **mvnw** và **gradlew**. Nếu scripts chưa có quyền execute trên Linux/macOS:

~~~bash
chmod +x mvnw gradlew
~~~

File **.gitignore** tối thiểu:

~~~gitignore
/target/
/build/
/.gradle/
~~~

Giữ lại Maven/Gradle Wrapper trong Git; chỉ bỏ qua output và cache sinh ra khi build.

## 4. Tạo một ứng dụng Spring Boot dùng chung

Ứng dụng có một endpoint GET **/hello** trả về chuỗi cố định. Cả hai build tool sẽ biên dịch đúng các file này.

### 4.1. Main class

Tệp **src/main/java/com/example/buildcompare/BuildCompareApplication.java**:

~~~java
package com.example.buildcompare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildCompareApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildCompareApplication.class, args);
    }
}
~~~

### 4.2. REST controller

Tệp **src/main/java/com/example/buildcompare/HelloController.java**:

~~~java
package com.example.buildcompare;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "build-comparison-ok";
    }
}
~~~

### 4.3. Application properties

Tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=build-compare
server.port=8080
~~~

### 4.4. Test dùng chung

Tệp **src/test/java/com/example/buildcompare/HelloControllerTest.java**:

~~~java
package com.example.buildcompare;

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
class HelloControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void helloReturnsExpectedBody() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("build-comparison-ok"));
    }
}
~~~

Test khởi tạo Spring context, gọi controller qua MockMvc và kiểm tra status/body. Nếu một build pass còn build kia fail, trước tiên kiểm tra test dependencies, JUnit Platform configuration và Java version.

## 5. Cấu hình Maven bằng pom.xml

Tệp **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>build-compare</artifactId>
    <version>1.0.0</version>
    <name>build-compare</name>
    <description>One Spring Boot application built with Maven and Gradle</description>

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

- **spring-boot-starter-parent** cung cấp dependency management và plugin management theo Spring Boot 3.5.16.
- **groupId/artifactId/version** xác định Maven project và tên artifact.
- **java.version=17** đặt Java version mà Spring Boot parent dùng cho compiler configuration.
- **spring-boot-starter-web** cung cấp Spring MVC và embedded web server.
- **spring-boot-starter-test** cung cấp JUnit Jupiter, Spring Test và MockMvc cho test scope.
- **spring-boot-maven-plugin** tạo executable archive bằng goal repackage.

Vì đang kế thừa **spring-boot-starter-parent**, execution **repackage** đã được parent cấu hình sẵn. Chỉ cần khai báo plugin là đủ. Maven chạy goal này trong phase package; khi gọi **clean verify**, lifecycle đi qua package và tạo executable JAR.

Nếu không dùng Spring Boot parent, cần khai báo version của plugin và cấu hình execution repackage rõ ràng. Import BOM **spring-boot-dependencies** chỉ quản lý dependency versions; nó không tự thay thế plugin management của starter parent.

Thuộc tính **project.build.outputTimestamp** đặt timestamp ổn định cho các archive plugin hỗ trợ. Giá trị ngày giờ trong ví dụ là mốc minh họa; dự án thật nên lấy một mốc cố định từ release/source metadata và giữ nhất quán giữa các lần build. Nó không tự bảo đảm mọi bytes của artifact đều reproducible.

## 6. Cấu hình Gradle bằng Kotlin DSL

### 6.1. settings.gradle.kts

~~~kotlin
rootProject.name = "build-compare"
~~~

Tên project giúp Gradle đặt tên archive theo cùng artifact name **build-compare**.

### 6.2. build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.testing.Test

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
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
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Giải thích:

- **java** thêm Java source sets, compile tasks, test task và JAR task.
- **org.springframework.boot** thêm Spring Boot Gradle Plugin và task như bootRun, bootJar.
- **io.spring.dependency-management** cho phép Spring Boot plugin tự import BOM tương ứng với version plugin, vì vậy dependency versions được quản lý tương tự Maven parent.
- **java.toolchain** chọn JDK 17 cho compile/test tasks; không chỉ dựa vào JAVA_HOME ngẫu nhiên của máy.
- **implementation** là dependency cần cho main runtime/compile classpath.
- **testImplementation** chỉ dùng cho test compile/runtime.
- **useJUnitPlatform()** cấu hình Gradle test task chạy JUnit 5.
- **AbstractArchiveTask** áp dụng cài đặt timestamp và thứ tự entry ổn định cho các archive tasks, gồm plain JAR và Boot JAR.

Spring Boot Gradle Plugin cũng hỗ trợ dùng Gradle native BOM bằng **platform** thay cho dependency-management plugin. Dependency-management plugin thuận tiện khi muốn dùng property-based customization của BOM; native BOM thường có lợi thế về tốc độ cấu hình/build. Trong bài này chọn dependency-management plugin để gần với trải nghiệm quản lý dependency của Maven.

Không khai báo version cho hai Spring Boot starters trong Gradle vì BOM đã quản lý chúng. Version plugin, Wrapper và Java toolchain vẫn được pin rõ ràng.

## 7. Build bằng Maven

Tại thư mục gốc:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
~~~

Trên Windows:

~~~powershell
.\\mvnw.cmd --version
.\\mvnw.cmd -B -ntp clean verify
~~~

Maven đi qua các lifecycle phases. Trong project này, các bước chính là:

| Phase | Công việc |
| --- | --- |
| validate | Kiểm tra cấu trúc project và thông tin cần thiết |
| compile | Biên dịch main Java source |
| test | Chạy unit/integration tests trong test phase |
| package | Tạo JAR và chạy Spring Boot repackage |
| verify | Chạy các checks bổ sung đã gắn vào lifecycle |

Sau khi thành công, artifact executable mặc định:

~~~text
target/build-compare-1.0.0.jar
~~~

Maven repackage thay thế main JAR bằng executable archive. Bản JAR thường trước khi repackage được đổi tên thành:

~~~text
target/build-compare-1.0.0.jar.original
~~~

File **.jar.original** là artifact trước khi Spring Boot thêm loader và nested dependencies. Nó không phải file chạy độc lập bằng java -jar trong ví dụ này.

Chạy ứng dụng trực tiếp bằng Maven:

~~~bash
./mvnw spring-boot:run
~~~

Goal **spring-boot:run** chạy ứng dụng từ project classpath, hữu ích cho phát triển. Khi cần kiểm tra artifact phát hành, vẫn phải chạy chính file JAR đã đóng gói.

## 8. Build bằng Gradle

Tại cùng thư mục gốc:

~~~bash
./gradlew --version
./gradlew clean build
~~~

Trên Windows:

~~~powershell
.\\gradlew.bat --version
.\\gradlew.bat clean build
~~~

Gradle tổ chức công việc theo task graph. Với Java và Spring Boot plugin, các task chính gồm:

| Task | Công việc |
| --- | --- |
| compileJava | Biên dịch main Java source |
| processResources | Copy resources |
| classes | Tổng hợp output của main source set |
| compileTestJava | Biên dịch test source |
| test | Chạy tests |
| jar | Tạo plain JAR |
| bootJar | Tạo executable Spring Boot JAR |
| assemble | Tổng hợp các build artifacts |
| check | Chạy các verification tasks |
| build | Phụ thuộc assemble và check |

Task **build** thực hiện tests và đóng gói. Spring Boot plugin cấu hình assemble phụ thuộc bootJar nên **clean build** sẽ tạo executable archive.

Output executable mặc định:

~~~text
build/libs/build-compare-1.0.0.jar
~~~

Gradle cũng tạo plain archive:

~~~text
build/libs/build-compare-1.0.0-plain.jar
~~~

Spring Boot Gradle plugin đặt classifier **plain** cho task jar theo mặc định để phân biệt với executable bootJar. Plain JAR chứa output ứng dụng ở layout Java thông thường, không có Boot loader và nested runtime dependencies; không dùng nó thay cho executable JAR khi triển khai.

Chạy ứng dụng trực tiếp bằng Gradle:

~~~bash
./gradlew bootRun
~~~

Task **bootRun** chạy ứng dụng từ runtime classpath của Gradle. Khi so sánh artifact đã phát hành, dùng java -jar trên output của bootJar.

## 9. Đối chiếu cấu hình Maven và Gradle

| Hạng mục | Maven | Gradle |
| --- | --- | --- |
| File build chính | pom.xml | build.gradle.kts |
| File project/root | POM coordinates | settings.gradle.kts + group/version |
| Dependency chính | dependencies | implementation |
| Dependency test | scope test | testImplementation |
| Dependency management | spring-boot-starter-parent | Spring Boot Gradle plugin + dependency-management BOM |
| Plugin Spring Boot | spring-boot-maven-plugin | org.springframework.boot |
| Compile | compile phase | compileJava task |
| Test | test phase | test task |
| Executable JAR | spring-boot:repackage | bootJar task |
| Chạy app khi phát triển | spring-boot:run | bootRun |
| Wrapper | mvnw / mvnw.cmd | gradlew / gradlew.bat |
| Output mặc định | target/ | build/ |

Maven diễn đạt quy trình qua lifecycle phases và plugin goals. Gradle mô hình hóa quy trình qua tasks và quan hệ phụ thuộc giữa các task. Cả hai đều có thể mở rộng bằng plugins, custom tasks/goals, test reports, code generation và publishing.

Không nên so sánh một lệnh **mvn package** với một lệnh **gradle build** rồi kết luận tốc độ. Maven package có thể không chạy cùng toàn bộ verification mà Gradle build chạy. Hãy chọn các lệnh có cùng mục tiêu: compile, test và tạo executable archive.

## 10. So sánh dependency graph

Hai file build đang khai báo cùng Spring Boot 3.5.16, spring-boot-starter-web, spring-boot-starter-test và Java 17. Maven lấy dependency versions từ Spring Boot parent. Gradle lấy versions từ BOM mà Spring Boot Gradle plugin import qua dependency-management plugin.

### 10.1. Xem dependency tree bằng Maven

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Lệnh này hiển thị dependencies runtime và đường đi transitive. Để xem cả test dependencies:

~~~bash
./mvnw dependency:tree
~~~

### 10.2. Xem dependency graph bằng Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Để tìm lý do một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency spring-web --configuration runtimeClasspath
~~~

### 10.3. Đọc kết quả đúng cách

So sánh:
- Cùng artifact coordinates và version.
- Cùng runtime dependencies.
- Cùng test dependencies.
- Không có dependency chỉ xuất hiện ở một build do khai báo khác.
- Không có version override ngoài dự kiến.
- Không bỏ sót dependency optional hoặc runtime-only.

Maven và Gradle có quy tắc conflict resolution và cách trình bày graph khác nhau. Nếu có version conflict hoặc override, hãy đọc **resolved version** thay vì chỉ nhìn version ghi trong file build. Với Spring Boot BOM, không tự ý override một dependency nếu chưa đánh giá tương thích.

## 11. Đối chiếu executable JAR

Đây là phần quan trọng nhất của bài. Ta cần chắc chắn đang so sánh hai executable archives, không vô tình lấy Maven executable JAR đối chiếu với Gradle plain JAR.

### 11.1. Kiểm tra file output

Linux/macOS:

~~~bash
ls -lh target/build-compare-1.0.0.jar
ls -lh build/libs/build-compare-1.0.0.jar
ls -lh build/libs/build-compare-1.0.0-plain.jar
~~~

Windows PowerShell:

~~~powershell
Get-Item target/build-compare-1.0.0.jar, build/libs/build-compare-1.0.0.jar, build/libs/build-compare-1.0.0-plain.jar |
    Select-Object Name, Length
~~~

Maven **.jar.original** và Gradle **-plain.jar** là hai artifact thường dùng để xem bản JAR trước khi Spring Boot tạo executable layout. Tuy nhiên, chúng được tạo bởi hai archive plugins khác nhau, nên cũng không mặc định giống byte-for-byte.

### 11.2. Liệt kê nội dung JAR

~~~bash
jar tf target/build-compare-1.0.0.jar
jar tf build/libs/build-compare-1.0.0.jar
~~~

Một executable Spring Boot JAR thường có các vùng:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/
BOOT-INF/classes/
BOOT-INF/lib/
BOOT-INF/classpath.idx
BOOT-INF/layers.idx
~~~

Tên metadata cụ thể phụ thuộc cấu hình. Những điểm quan trọng:

- **BOOT-INF/classes** chứa application classes và resources.
- **BOOT-INF/lib** chứa runtime dependencies dạng nested JAR.
- **spring-boot-loader** cung cấp launcher để đọc nested JARs.
- **META-INF/MANIFEST.MF** xác định Main-Class và Start-Class.
- **layers.idx** mô tả nhóm layer nếu layered archive được bật.

Nếu executable JAR không có nested dependencies hoặc loader, có thể bạn đang nhìn plain JAR hoặc build chưa chạy repackage/bootJar đúng cách.

### 11.3. Kiểm tra manifest

Dùng công cụ unzip hoặc giải nén riêng file **META-INF/MANIFEST.MF** trong từng archive.

Manifest của executable Spring Boot JAR thường có dạng:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.buildcompare.BuildCompareApplication
Spring-Boot-Version: 3.5.16
~~~

Thứ tự thuộc tính và các trường phụ có thể khác. Hai trường cần quan tâm:
- **Main-Class** là Boot launcher.
- **Start-Class** là main class của ứng dụng.

Maven repackage viết lại manifest và quản lý Main-Class/Start-Class. Gradle BootJar cũng tự tìm main class có public static void main hoặc cho phép cấu hình rõ. Nếu không tìm được main class, khai báo tường minh trong plugin/task configuration.

### 11.4. So sánh plain archives

Maven lưu bản thường dưới dạng **.jar.original** khi repackage thay thế main artifact. Gradle tạo **-plain.jar** bằng task jar.

Plain JAR thường có:

~~~text
com/example/buildcompare/BuildCompareApplication.class
com/example/buildcompare/HelloController.class
application.properties
~~~

Nó không có cấu trúc BOOT-INF/lib chứa toàn bộ dependencies và không có Boot launcher. Đừng chạy plain JAR bằng java -jar để đánh giá executable packaging.

## 12. Kiểm tra kích thước và checksum

Kích thước cho biết dung lượng file, nhưng không giải thích file chứa những gì. Hãy kết hợp size, dependency list và archive entries.

Linux/macOS:

~~~bash
du -h target/build-compare-1.0.0.jar
du -h build/libs/build-compare-1.0.0.jar
sha256sum target/build-compare-1.0.0.jar
sha256sum build/libs/build-compare-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash target/build-compare-1.0.0.jar -Algorithm SHA256
Get-FileHash build/libs/build-compare-1.0.0.jar -Algorithm SHA256
~~~

Lập bảng kết quả thực tế:

| Chỉ số | Maven | Gradle |
| --- | --- | --- |
| Executable JAR path | target/build-compare-1.0.0.jar | build/libs/build-compare-1.0.0.jar |
| File size | Ghi số đo thực tế | Ghi số đo thực tế |
| SHA-256 | Ghi digest thực tế | Ghi digest thực tế |
| Main-Class | Kiểm tra manifest | Kiểm tra manifest |
| Start-Class | Kiểm tra manifest | Kiểm tra manifest |
| Runtime dependencies | dependency:tree | runtimeClasspath |
| HTTP smoke test | PASS/FAIL | PASS/FAIL |

Không điền số đo giả định. Kích thước và digest phụ thuộc resolved dependencies, JDK, plugin versions, archive metadata và build configuration.

**Hai SHA-256 khác nhau không chứng minh ứng dụng khác hành vi.** Hash chỉ xác định bytes. Hãy xem archive entries, manifest, dependencies và runtime behavior để tìm nguyên nhân khác nhau.

## 13. Vì sao hai JAR có thể khác bytes?

Ngay cả khi source và dependencies giống nhau, Maven và Gradle có thể tạo archive khác nhau do:
- Thứ tự entries trong ZIP/JAR.
- Timestamp của entries.
- Compression level hoặc cách ghi ZIP metadata.
- Manifest attributes và thứ tự thuộc tính.
- Phiên bản Maven/Gradle archive plugin và Spring Boot plugin.
- Boot loader, classpath index, layer metadata.
- Bytecode khác nếu hai build dùng JDK patch/vendor khác nhau.
- Generated resources, build-info hoặc timestamps do project/plugin tạo.

Hãy phân biệt ba mức so sánh:

1. **Source equivalence:** hai build dùng đúng cùng source/resources.
2. **Functional equivalence:** hai executable artifacts chạy và trả cùng kết quả theo test/smoke-test.
3. **Byte-for-byte reproducibility:** cùng một build process với cùng inputs tạo đúng cùng bytes qua nhiều lần build.

Mục tiêu chính của bài là chứng minh functional equivalence và kiểm tra resolved dependencies. Byte-for-byte equality giữa hai build tools là yêu cầu cao hơn, cần chuẩn hóa sâu archive metadata và toolchain; không phải mặc định của Spring Boot.

## 14. Reproducible build cho từng công cụ

### 14.1. Maven

Spring Boot Maven Plugin hỗ trợ **outputTimestamp** và nhận giá trị mặc định từ property **project.build.outputTimestamp**.

~~~xml
<properties>
    <java.version>17</java.version>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Dùng một timestamp cố định hoặc timestamp có nguồn gốc từ commit/release metadata. Không dùng thời gian hiện tại mỗi lần build nếu muốn so sánh archive bytes giữa các lần build.

Còn phải kiểm soát Maven Wrapper, JDK, Maven plugins, dependencies, generated resources và môi trường build.

### 14.2. Gradle

Gradle archive tasks có hai thuộc tính liên quan:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Cấu hình này không giữ wall-clock timestamps của entries và sắp xếp entry order ổn định. Gradle 9 đặt các archive defaults này theo hướng reproducible; trong bài dùng Gradle 8.14.3 nên khai báo rõ để kết quả dễ kiểm soát.

Gradle cũng cần Java toolchain cố định:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Toolchain khóa Java major version; để so sánh nghiêm ngặt, hãy dùng cùng JDK vendor/patch và cùng OS/architecture. Một JDK 17 patch khác có thể tạo bytecode hoặc metadata khác.

### 14.3. Kiểm tra reproducibility

1. Build từ cùng commit ở thư mục sạch.
2. Lưu SHA-256.
3. Xóa output và build lại bằng cùng Wrapper/JDK/configuration.
4. So digest.
5. Lặp lại trên máy/runner khác nếu policy yêu cầu.
6. Nếu hash khác, so archive entries/timestamps/manifest và generated files.

Nếu so Maven với Gradle, trước hết kiểm tra functional equivalence. Muốn cùng hash giữa hai công cụ phải chuẩn hóa cả cách biên dịch và cách đóng gói; đó là một mục tiêu riêng.

## 15. Chạy hai artifact để kiểm tra hành vi

Không chạy cả hai trên cùng port cùng lúc. Chạy từng artifact, kiểm tra HTTP response rồi dừng process trước khi thử artifact còn lại.

### 15.1. Chạy JAR từ Maven

Terminal thứ nhất:

~~~bash
java -jar target/build-compare-1.0.0.jar --server.port=8081
~~~

Terminal thứ hai:

~~~bash
curl --fail --silent --show-error http://localhost:8081/hello
~~~

Body mong đợi:

~~~text
build-comparison-ok
~~~

### 15.2. Chạy JAR từ Gradle

Dừng process Maven, sau đó:

~~~bash
java -jar build/libs/build-compare-1.0.0.jar --server.port=8081
~~~

Kiểm tra:

~~~bash
curl --fail --silent --show-error http://localhost:8081/hello
~~~

Body mong đợi:

~~~text
build-comparison-ok
~~~

### 15.3. Kiểm tra trên Windows PowerShell

~~~powershell
Invoke-RestMethod http://localhost:8081/hello
~~~

Kết quả:

~~~text
build-comparison-ok
~~~

Nếu một artifact trả 200 còn artifact kia không start, kiểm tra logs, Java version, manifest, nested dependencies, server port và runtime configuration. Không chỉ dựa vào việc build task báo SUCCESSFUL.

## 16. So sánh test reports

Maven Surefire thường ghi kết quả test vào:

~~~text
target/surefire-reports/
~~~

Gradle ghi test results và HTML report vào:

~~~text
build/test-results/test/
build/reports/tests/test/index.html
~~~

So sánh tổng số tests, passed/failed/skipped, test class/method, stack trace và test runtime environment.

Nếu Gradle không chạy test, kiểm tra task graph và cấu hình JUnit Platform. Nếu Maven không chạy test, kiểm tra Surefire configuration, test naming convention và scope test dependencies.

Một build chỉ nên được coi là tương đương khi cả hai đều chạy cùng test suite và đạt cùng tiêu chí PASS.

## 17. Đối chiếu build time một cách công bằng

Gradle có incremental task execution, daemon và build cache. Maven có local repository cache cho dependencies và plugin artifacts; Maven build thông thường không giữ một daemon sống giống Gradle. Những cơ chế này khiến cold build và warm build có thể rất khác nhau.

### 17.1. Cold build

Cold build đo lần đầu trên môi trường chưa có dependencies/cache. Nó bị ảnh hưởng bởi mạng, số artifacts phải tải, Wrapper distribution download, JDK provisioning và CI runner startup.

Không dùng cold build đơn lẻ để kết luận một công cụ nhanh hơn.

### 17.2. Warm clean build

Sau khi dependencies đã được tải, chạy cùng thao tác clean build nhiều lần:

~~~bash
./mvnw -B -ntp clean verify
./gradlew clean build
~~~

Mỗi công cụ nên có một lượt warm-up. Sau đó đo ít nhất 5 lượt và lấy median. Dùng cùng máy, JDK, source commit, network và repository state.

### 17.3. Incremental build

Thay đổi một file Java nhỏ rồi build lại mà không clean. Đây là phép đo hữu ích cho vòng lặp developer, nhưng không tương đương với clean build.

Gradle có thể đánh dấu task UP-TO-DATE hoặc FROM-CACHE. Đọc task output để biết công việc nào thực sự được thực hiện. Maven cũng có thể bỏ qua một số compile work theo compiler plugin configuration, nên hãy quan sát logs thay vì giả định mọi phase đều compile toàn bộ.

### 17.4. Báo cáo kết quả

| Phép đo | Maven | Gradle |
| --- | --- | --- |
| Cold build | Đo thực tế | Đo thực tế |
| Warm clean build median | Đo 5 lượt | Đo 5 lượt |
| Incremental build median | Đo 5 lượt | Đo 5 lượt |
| Tests | Cùng test count | Cùng test count |
| Executable JAR size | Đo thực tế | Đo thực tế |
| Runtime smoke test | PASS/FAIL | PASS/FAIL |

Không có kết luận chung rằng Maven luôn chậm hơn hoặc Gradle luôn nhanh hơn. Hiệu quả phụ thuộc build graph, plugins, cache, daemon, project size, CI setup và mức độ tùy biến.

## 18. Cách đọc khác biệt dependency và packaging

| Quan sát | Có thể là bình thường? | Cách đánh giá |
| --- | --- | --- |
| Maven output ở target, Gradle ở build/libs | Có | Khác quy ước output directory |
| Maven có .jar.original, Gradle có -plain.jar | Có | Cách giữ plain archive khác nhau |
| SHA-256 khác | Có | So manifest, entries, dependencies và behavior |
| Một archive lớn hơn | Có | Kiểm tra nested libraries, metadata, compression |
| Dependency version khác | Cần điều tra | So BOM, overrides và resolved dependency graph |
| Main-Class khác | Cần điều tra | Kiểm tra Spring Boot plugin và archive type |
| Start-Class khác | Cần điều tra | Kiểm tra main class discovery/configuration |
| Một JAR thiếu BOOT-INF/lib | Không đúng với executable JAR chuẩn | Có thể đang so plain JAR |
| Một artifact không chạy được | Không đạt | Kiểm tra manifest, loader và runtime dependencies |
| Test count khác | Cần điều tra | Kiểm tra test filters, JUnit Platform và task execution |

Nếu hai runtime dependency trees không khớp, giải quyết khác biệt đó trước khi so kích thước. Một bên có thể đang đóng gói thêm optional dependency hoặc một version khác do conflict resolution.

## 19. Cấu hình thêm khi cần giữ plain JAR hoặc đổi tên

### 19.1. Maven classifier

Mặc định Maven repackage thay thế main artifact và lưu bản thường dưới đuôi **.original**. Nếu muốn publish cả JAR thường và executable JAR thành hai artifacts, đặt classifier cho executable archive:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Với starter parent, execution repackage đã có sẵn; chỉ cấu hình classifier trong execution tương ứng. Khi đó có thể cài/publish plain artifact và executable artifact riêng.

### 19.2. Gradle classifier

Gradle mặc định đặt classifier **plain** cho JAR thường. Nếu muốn đổi classifier của executable JAR, có thể cấu hình BootJar task:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveClassifier.set("exec")
}
~~~

Khi thay đổi classifier, cập nhật đường dẫn output trong script so sánh và CI. Không so nhầm file cũ còn sót lại trong build directory.

## 20. Tổ chức CI để build cùng một source bằng cả hai công cụ

Một pipeline matrix có thể chạy hai jobs độc lập từ cùng commit:

~~~text
Checkout one source commit
          |
          +-------------------------+
          |                         |
          v                         v
      Maven job                 Gradle job
          |                         |
     Maven Wrapper             Gradle Wrapper
          |                         |
      clean verify               clean build
          |                         |
     Maven executable JAR       Gradle bootJar
          |                         |
          +------------+------------+
                       |
                       v
             Compare test reports
             Compare dependency graphs
             Compare JAR layout/manifest
             Run both smoke tests
                       |
                       v
                Release decision
~~~

Các điều kiện nên giữ:
- Cùng source commit.
- Cùng JDK vendor/version.
- Wrapper distributions được pin.
- Plugin versions được pin.
- Dependency versions được quản lý bằng cùng Spring Boot BOM.
- Cùng repository/mirror và credentials policy.
- Không chia sẻ output directory giữa hai jobs.
- Lưu test reports, dependency reports, artifact size và checksum.

Nếu CI chỉ cần một build tool để phát hành, có thể giữ job còn lại như compatibility check theo lịch hoặc trước khi migrate. Không nhất thiết phải build hai lần ở mọi lần release nếu chi phí không phù hợp.

## 21. Lỗi thường gặp khi so sánh

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Maven JAR chạy, Gradle JAR không chạy | Đã lấy -plain.jar thay vì bootJar | Dùng build/libs/*-1.0.0.jar |
| Gradle không tạo executable JAR | Chỉ chạy jar task hoặc plugin không được áp dụng | Kiểm tra Spring Boot plugin và bootJar |
| Maven không có executable JAR | Chưa chạy package/repackage hoặc plugin execution bị skip | Kiểm tra starter parent/plugin configuration |
| Dependency version khác | BOM/version override không đồng nhất | So dependency tree và Gradle runtimeClasspath |
| Gradle test không chạy | Thiếu useJUnitPlatform hoặc task bị disable/filter | Kiểm tra test task và JUnit config |
| Maven test không chạy | Surefire/test naming/scope sai | Kiểm tra Surefire logs và test dependencies |
| Main class không được nhận diện | Nhiều main classes hoặc class không đúng layout | Cấu hình mainClass/Start-Class rõ ràng |
| Hash khác sau mỗi build | Timestamp/generated metadata/toolchain khác | Chuẩn hóa timestamp, archive order và JDK |
| Hai server cùng port | Artifact trước vẫn đang chạy | Dừng process trước lần test tiếp theo |
| File size tăng bất thường | Dependency thừa hoặc scope/packaging khác | So runtime dependency graph và BOOT-INF/lib |
| Build time không ổn định | Một lượt cold, một lượt warm hoặc cache khác nhau | Warm-up, đo nhiều lượt, lấy median |
| CI khác local | Wrapper/JDK/settings/profiles khác | Dùng Wrapper và pin toolchain/configuration |

## 22. Checklist hoàn thành bài thực hành

- [ ] Hai build files nằm trong cùng project root.
- [ ] Chỉ có một bộ Java source và resources.
- [ ] Cùng Spring Boot 3.5.16.
- [ ] Cùng Java 17 toolchain/runtime.
- [ ] Maven Wrapper và Gradle Wrapper đã được tạo, pin và commit.
- [ ] Maven parent quản lý dependency/plugin versions.
- [ ] Gradle dùng Spring Boot BOM tương ứng.
- [ ] Maven clean verify PASS.
- [ ] Gradle clean build PASS.
- [ ] Maven executable JAR được xác định đúng.
- [ ] Gradle bootJar được xác định đúng; không nhầm plain JAR.
- [ ] Runtime dependency graphs được đối chiếu.
- [ ] Manifest Main-Class và Start-Class được kiểm tra.
- [ ] BOOT-INF/classes và BOOT-INF/lib được kiểm tra.
- [ ] Test reports có cùng test count và kết quả.
- [ ] Cả hai JAR chạy được bằng java -jar.
- [ ] Cả hai trả HTTP body build-comparison-ok.
- [ ] Size và SHA-256 được ghi nhận từ kết quả thực tế.
- [ ] Build time được đo bằng cùng điều kiện cold/warm/incremental.
- [ ] Các khác biệt về metadata/ZIP layout được giải thích.

## 23. Bài tập tự kiểm tra

**Câu 1.** Maven và Gradle có thể dùng chung source directory không?

**Đáp án:** Có. Cả hai đều hỗ trợ Java project layout chuẩn src/main/java, src/main/resources và src/test/java. Chỉ cần đặt hai file build ở cùng project root.

**Câu 2.** Vì sao Maven dùng spring-boot:repackage còn Gradle dùng bootJar?

**Đáp án:** Maven Spring Boot plugin chạy goal repackage trên JAR/WAR được tạo ở package phase. Gradle Spring Boot plugin tạo task bootJar để tạo executable archive.

**Câu 3.** Tại sao Gradle tạo thêm file -plain.jar?

**Đáp án:** Gradle giữ task jar cho plain archive và dùng classifier plain để phân biệt với executable bootJar.

**Câu 4.** Vì sao hai executable JAR có thể chạy giống nhau nhưng SHA-256 khác?

**Đáp án:** Archive entries, timestamps, compression, manifest metadata, plugin implementations hoặc bytecode có thể khác dù runtime behavior và dependency set tương đương.

**Câu 5.** spring-boot-dependencies BOM có tự thêm starter-web vào project không?

**Đáp án:** Không. BOM quản lý version. Project vẫn phải khai báo starter-web trong dependencies hoặc implementation.

**Câu 6.** Tại sao cần so dependency tree trước khi so file size?

**Đáp án:** Nếu một artifact chứa thêm hoặc khác version runtime dependencies, chênh lệch size có thể đến từ dependency set chứ không phải build tool.

**Câu 7.** Có thể chạy hai JAR trên cùng port để so sánh không?

**Đáp án:** Không đồng thời trên cùng địa chỉ/port. Chạy lần lượt hoặc dùng hai port riêng.

**Câu 8.** Maven clean có xóa output Gradle không?

**Đáp án:** Không. Maven clean xóa target; Gradle clean xóa build. Phải clean từng build tool.

**Câu 9.** Gradle nhanh hơn Maven trong mọi dự án không?

**Đáp án:** Không. Tốc độ phụ thuộc task graph, cache, daemon, plugins, project size, CI và cách đo. Cần benchmark cùng điều kiện.

**Câu 10.** Điều gì chứng minh hai artifact tương đương về chức năng trong bài này?

**Đáp án:** Cùng source/dependencies, test suite đạt cùng kết quả và cả hai executable JAR chạy thành công, trả cùng HTTP response. Hash equality là một kiểm tra khác, không thay thế smoke test.

## 24. Kết luận

Maven và Gradle đều có thể build cùng một Spring Boot application thành executable JAR. Với Maven, Spring Boot Maven Plugin dùng **repackage** trong package lifecycle; với Gradle, Spring Boot Gradle Plugin tạo **bootJar** và Gradle build task gọi nó thông qua assemble.

Điều cần kiểm tra khi đối chiếu không chỉ là file name hay size. Hãy xác minh cùng source, Java, Spring Boot BOM, resolved dependency versions, executable archive layout, manifest, test reports và runtime HTTP behavior. Khi cần đánh giá build performance hoặc reproducibility, tách cold build, warm clean build và incremental build thành các phép đo riêng.

## 25. Tài liệu tham khảo chính thức

- Spring Boot 3.5.16 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot 3.5 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
- Spring Boot 3.5 — Gradle Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Gradle Managing Dependencies: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Gradle — Building Java & JVM Projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Task Basics: https://docs.gradle.org/current/userguide/task_basics.html
- Gradle — Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Best Practices for Reproducible Build Output: https://docs.gradle.org/current/userguide/best_practices_security.html#build-output-should-be-byte-for-byte-reproducible
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
