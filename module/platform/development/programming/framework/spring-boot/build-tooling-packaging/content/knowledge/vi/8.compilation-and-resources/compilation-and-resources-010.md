# Kiểm tra mã nguồn sinh và tài nguyên đã biên dịch trong thư mục đầu ra

## 1. Vì sao phải kiểm tra thư mục đầu ra của bản dựng?

Một ứng dụng Spring Boot có thể có Java source hợp lệ, build báo thành công nhưng khi chạy vẫn không tìm được resource, cấu hình đã lọc sai hoặc thiếu implementation do annotation processor sinh. Chỉ nhìn vào **src/main/java** và **src/main/resources** không đủ để trả lời chương trình thực sự nhận được gì sau khi biên dịch và đóng gói.

Bản dựng của Maven/Gradle tạo nhiều **loại đầu ra khác nhau**. Kiểm tra đúng thư mục giúp phân biệt:

1. **Mã nguồn viết tay**: tệp Java đang được quản lý trong repository.
2. **Mã nguồn sinh (generated source)**: tệp Java do annotation processor, code generator hoặc plugin build tạo ra.
3. **Bytecode đã biên dịch**: tệp **.class** mà JVM sử dụng, có thể đến từ source viết tay hoặc source sinh.
4. **Resources đã xử lý**: tệp properties, YAML, JSON, template, service descriptors, v.v. được copy hoặc biến đổi trong build.
5. **Artifact cuối cùng**: plain JAR, executable Spring Boot JAR/WAR hoặc image chứa các đầu ra đã chọn.
6. **Báo cáo và cache build**: kết quả test, trạng thái incremental compilation, metadata hoặc file trung gian; chúng không mặc nhiên là nội dung được deploy.

**Mục tiêu bài học:** xác định vị trí mặc định của từng loại trong Maven và Gradle; sử dụng lệnh build, công cụ tìm file, **javap**, **jar tf** và một ví dụ annotation processing để kiểm tra nội dung thực; giải thích vì sao file có ở build directory nhưng vẫn có thể không xuất hiện trong JAR.

Bài thực hành dùng **Java 17**, Spring Boot **3.5.16** và MapStruct **1.6.3** làm ví dụ kỹ thuật có version cụ thể. Spring Boot 3.5.16 là bản cuối của nhánh 3.5 được hỗ trợ OSS theo thông báo phát hành; dự án production mới cần chọn nhánh đang được bảo trì và đối chiếu Java/Gradle/Maven compatibility hiện hành. Đường dẫn và cơ chế kiểm tra ở đây áp dụng rộng hơn cho các nhánh build Java thông thường.

## 2. Bản đồ một pipeline: từ source đến artifact

~~~text
src/main/java/                     (mã nguồn ứng dụng)
       |
       | compiler + annotation processors
       v
generated *.java ------------------------------+
       |                                       |
       +----> javac ---------------------------+----> compiled *.class
                                                    |
src/main/resources/ -- copy / filtering ------------+----> processed resources
                                                    |
                                  runtime dependencies
                                                    |
                                                    v
                                       plain JAR / Spring Boot JAR
                                                    |
                                                    v
                                          JVM / container runtime
~~~

Điểm mấu chốt: **mã sinh .java, bytecode .class và resource đều là những đối tượng khác nhau**. Một số generator không tạo Java source mà tạo code trong ngôn ngữ khác, tệp metadata hoặc bytecode trực tiếp. Đường dẫn bên dưới là mặc định của các Java plugin/Compiler plugin phổ biến, **không phải quy luật áp dụng cho mọi plugin**. Nếu project custom outputDirectory, layout.buildDirectory, source sets hoặc code generator, phải xem cấu hình hiệu lực của project.

## 3. Bảng tra nhanh đầu ra Maven và Gradle

| Thành phần | Maven (đường dẫn thông thường) | Gradle Java plugin (đường dẫn thông thường) |
| --- | --- | --- |
| Java source viết tay | src/main/java | src/main/java |
| Main resources ban đầu | src/main/resources | src/main/resources |
| Java generated do annotation processor | target/generated-sources/annotations | build/generated/sources/annotationProcessor/java/main |
| .class của mã chính (kể cả nhiều lớp sinh) | target/classes | build/classes/java/main |
| Resources chính sau copy/filter | target/classes | build/resources/main |
| Test .class | target/test-classes | build/classes/java/test |
| Test resources sau copy | target/test-classes | build/resources/test |
| Java generated từ test annotation processors | target/generated-test-sources/test-annotations (tùy compiler/plugin) | build/generated/sources/annotationProcessor/java/test |
| JAR được đóng gói | target/<artifactId>-<version>.jar | build/libs/<projectName>-<version>.jar |
| Báo cáo test | target/surefire-reports | build/reports/tests/test và build/test-results/test |

Trong Maven, cả main **class** lẫn main **resources** thường chung thư mục **target/classes**. Trong Gradle, Java plugin thường đặt hai nhóm ở **build/classes/java/main** và **build/resources/main**, sau đó tập hợp chúng vào output source set/classpath và archive.

**Không mong đợi mọi thư mục luôn tồn tại.** Nếu project không có annotation processor tạo file, thư mục generated sources có thể trống hoặc không được tạo. Nếu chỉ chạy compile main, thư mục test class hoặc report test chưa chắc tồn tại. Một dự án Kotlin/Groovy, nhiều module hoặc customized build sẽ có thêm đường dẫn như **build/classes/kotlin/main**, **build/generated/...** riêng của plugin.

## 4. Xác định root output và tác vụ trước khi xem file

### 4.1. Với Maven

Một project Maven thông thường dùng **project.build.directory = target**. Các đường dẫn bên dưới được xây từ biến này; chúng có thể được cấu hình lại trong pom.xml hoặc parent. Quan sát giá trị hiệu lực:

~~~bash
./mvnw --version
./mvnw help:evaluate -Dexpression=project.build.directory -q -DforceStdout
./mvnw help:evaluate -Dexpression=project.build.outputDirectory -q -DforceStdout
./mvnw help:evaluate -Dexpression=project.build.testOutputDirectory -q -DforceStdout
~~~

Đối với một project chưa đổi build layout, các giá trị logic lần lượt chỉ về **target**, **target/classes** và **target/test-classes** dưới project root. Maven Help Plugin có thể phải được tải về repository/cache khi chạy lần đầu.

Maven phase/goal liên quan:
- **process-resources**: xử lý/copy resource chính.
- **compile**: chạy trình biên dịch chính; processor có thể tạo .java và javac sinh .class.
- **process-test-resources** và **test-compile**: chuẩn bị test resources và test bytecode.
- **test**: thực hiện các test qua plugin đã được cấu hình.
- **package**: tạo JAR/WAR; với Spring Boot Maven Plugin đã bind **repackage**, archive có định dạng Boot executable.

Đối với project kế thừa **spring-boot-starter-parent** và khai báo Spring Boot Maven Plugin, thông thường **./mvnw package** sẽ đi qua compile/resources/test và đóng gói Boot JAR. Đừng coi việc thấy **target/classes** là bằng chứng goal **repackage** đã chạy.

### 4.2. Với Gradle

Với Gradle Java plugin, root output mặc định là **build/** của project tương ứng. Các task thường gặp:

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew compileJava
./gradlew processResources
./gradlew classes
./gradlew test
./gradlew bootJar
~~~

**compileJava** sinh main .class và chạy annotation processors. **processResources** xử lý/copy main resources. **classes** là lifecycle task phụ thuộc vào compileJava và processResources. **test** chuẩn bị/chạy test; **bootJar** do Spring Boot Gradle Plugin tạo khi áp dụng cùng Java plugin. Một task **UP-TO-DATE** hoặc **FROM-CACHE** vẫn có thể có output hợp lệ từ lần build trước; đừng suy luận từ việc task không chạy actions trong lần gọi này rằng file không tồn tại.

Tài liệu Java plugin công bố output main mặc định:
- **build/classes/java/main** đối với compiled classes;
- **build/resources/main** đối với processed resources;
- **build/generated/sources/annotationProcessor/java/main** đối với Java source do annotation processors sinh.

Khi cần biết cấu hình **thực** trong project có bị override hay không, hãy kiểm tra các SourceSet outputs và JavaCompile task options trong build script. Không hardcode các đường dẫn trên thành câu trả lời cho mọi build đa ngôn ngữ hoặc custom source set.

## 5. Bài thực hành: tạo một class Java sinh thật bằng MapStruct

Annotation processing là ví dụ điển hình để hiểu **generated source**. Ở đây dùng **MapStruct**, trình tạo Java mapping code tại **compile time**. Với một interface mang annotation **@Mapper**, MapStruct sinh Java implementation có tên thường là **GreetingMapperImpl**; trình biên dịch sau đó sinh **GreetingMapperImpl.class**. Cả hai có thể được kiểm tra độc lập.

Các tệp source dưới đây dùng chung cho lựa chọn **Maven hoặc Gradle**. Chỉ chọn **một** hệ build cho một project khi thực hành. Đầu ra dự kiến có thể khác nếu plugin/processor version hoặc output directories thay đổi.

### 5.1. Cấu trúc source

~~~text
inspect-output/
├── pom.xml                       (lựa chọn Maven)
│   hoặc build.gradle             (lựa chọn Gradle)
├── settings.gradle               (nếu dùng Gradle)
├── mvnw, mvnw.cmd, .mvn/...      (Wrapper Maven, nếu dùng Maven)
├── gradlew, gradlew.bat, gradle/wrapper/... (Wrapper Gradle, nếu dùng Gradle)
└── src/
    ├── main/
    │   ├── java/com/example/inspect/
    │   │   ├── InspectOutputApplication.java
    │   │   ├── InspectController.java
    │   │   ├── GreetingSource.java
    │   │   ├── GreetingDto.java
    │   │   └── GreetingMapper.java
    │   └── resources/demo.properties
    └── test/
        └── java/com/example/inspect/InspectControllerTests.java
~~~

Các tệp Wrapper phải được tạo bằng Spring Initializr/Maven Wrapper/Gradle Wrapper theo công cụ được chọn; chúng không xuất hiện chỉ vì viết **pom.xml** hay **build.gradle**. Dùng Maven 3.x hoặc Gradle 8.14 tương thích với Spring Boot 3.5.16, và cấu hình JDK 17 cho ví dụ.

### 5.2. Model đầu vào

Tệp **src/main/java/com/example/inspect/GreetingSource.java**:

~~~java
package com.example.inspect;

public class GreetingSource {
    private String message;

    public GreetingSource() {}

    public GreetingSource(String message) {
        this.message = message;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
~~~

### 5.3. DTO đầu ra

Tệp **src/main/java/com/example/inspect/GreetingDto.java**:

~~~java
package com.example.inspect;

public class GreetingDto {
    private String text;

    public String getText() {
        return text;
    }

    public void setText(String text) {
        this.text = text;
    }
}
~~~

### 5.4. Interface khai báo mapping

Tệp **src/main/java/com/example/inspect/GreetingMapper.java**:

~~~java
package com.example.inspect;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper
public interface GreetingMapper {
    @Mapping(source = "message", target = "text")
    GreetingDto toDto(GreetingSource source);
}
~~~

Đây là interface Java **viết tay** và được commit vào source control. MapStruct annotation processor nhận biết **@Mapper**, sinh class implementation tương ứng; do đó ứng dụng không phải tự viết **GreetingMapperImpl.java**. Nếu annotation processor chưa được khai báo hoặc compiler không chạy processing, lớp implementation có thể không tồn tại dù interface **GreetingMapper.class** được tạo thành công.

### 5.5. Spring Boot application class

Tệp **src/main/java/com/example/inspect/InspectOutputApplication.java**:

~~~java
package com.example.inspect;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InspectOutputApplication {
    public static void main(String[] args) {
        SpringApplication.run(InspectOutputApplication.class, args);
    }
}
~~~

### 5.6. Controller dùng cả mã sinh và resource

Tệp **src/main/java/com/example/inspect/InspectController.java**:

~~~java
package com.example.inspect;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

import org.mapstruct.factory.Mappers;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InspectController {
    private final GreetingMapper mapper =
            Mappers.getMapper(GreetingMapper.class);

    @GetMapping("/inspect")
    public String inspect() throws IOException {
        GreetingDto dto =
                mapper.toDto(new GreetingSource("generated-ok"));

        Properties properties = new Properties();
        try (InputStream input =
                     InspectController.class.getResourceAsStream(
                             "/demo.properties")) {
            if (input == null) {
                throw new IOException("demo.properties not found");
            }
            properties.load(input);
        }

        return dto.getText() + " / "
                + properties.getProperty("label", "missing");
    }
}
~~~

Lời gọi **Mappers.getMapper(GreetingMapper.class)** tìm implementation do processor sinh. **getResourceAsStream("/demo.properties")** tìm tài nguyên từ **runtime classpath**, không đọc trực tiếp từ **src/main/resources**. Khi chạy JAR, resource phải tồn tại bên trong artifact, chứ không nhất thiết còn source directory trên máy triển khai.

### 5.7. Resource đơn giản để kiểm tra byte-for-byte

Tệp **src/main/resources/demo.properties**:

~~~properties
label=resource-ok
~~~

Đối với file này, Maven/Gradle chỉ cần copy nguyên nội dung vào output. Dùng dòng không dấu giúp kết quả hiển thị ổn định giữa các môi trường; khi dùng Unicode trong Java properties, cần kiểm tra encoding và cơ chế nạp resource phù hợp.

### 5.8. Test xác nhận có mapper implementation và resource

Tệp **src/test/java/com/example/inspect/InspectControllerTests.java**:

~~~java
package com.example.inspect;

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
class InspectControllerTests {
    @Autowired
    private MockMvc mvc;

    @Test
    void generatedMapperAndResourceAreAvailable() throws Exception {
        mvc.perform(get("/inspect"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "generated-ok / resource-ok"));
    }
}
~~~

Test này kiểm tra hai đầu ra quan trọng có thể sử dụng **trên classpath trong ứng dụng chạy**. Nó khác việc chỉ nhìn thấy file trên ổ đĩa: một file tồn tại trong thư mục build chưa chắc đã được đóng vào artifact hoặc được nạp bằng classloader đúng.

## 6. Lựa chọn Maven: cấu hình annotation processor và build

Tạo **pom.xml** ở project root:

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
    <artifactId>inspect-output</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <mapstruct.version>1.6.3</mapstruct.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.mapstruct</groupId>
            <artifactId>mapstruct</artifactId>
            <version>${mapstruct.version}</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.mapstruct</groupId>
                            <artifactId>mapstruct-processor</artifactId>
                            <version>${mapstruct.version}</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao có hai MapStruct artifacts?** Thư viện **org.mapstruct:mapstruct** chứa annotation/API và runtime factory; **mapstruct-processor** là công cụ tạo implementation khi compiler chạy. Đặt processor trong **annotationProcessorPaths** tách nó khỏi dependencies runtime thông thường. Với JDK mới, không nên trông chờ classpath scanning ngầm sẽ tự chạy annotation processing; cấu hình processor tường minh giúp build có thể kiểm chứng.

### 6.1. Chạy các phase để tạo output theo từng bước

~~~bash
./mvnw --version
./mvnw clean compile
~~~

Sau **compile** thành công, các thành phần dự kiến:

~~~text
target/
├── generated-sources/
│   └── annotations/com/example/inspect/
│       └── GreetingMapperImpl.java
└── classes/
    ├── com/example/inspect/
    │   ├── InspectOutputApplication.class
    │   ├── InspectController.class
    │   ├── GreetingSource.class
    │   ├── GreetingDto.class
    │   ├── GreetingMapper.class
    │   └── GreetingMapperImpl.class
    └── demo.properties
~~~

Đây là **cây đường dẫn dự kiến**, không phải ảnh chụp output của máy nào. Maven Compiler Plugin công bố **generatedSourcesDirectory** mặc định là **target/generated-sources/annotations**; output class mặc định là **target/classes**. Maven Resources Plugin thực hiện main resource copy ở **process-resources**, một phase diễn ra trước compile.

Sau đó chạy build có test và packaging:

~~~bash
./mvnw clean verify
~~~

Với POM ở trên, có thể thấy thêm **target/test-classes**, **target/surefire-reports** và **target/inspect-output-1.0.0.jar**. **repackage** đã được Spring Boot parent chuẩn bị và Maven Plugin được khai báo, nên JAR thành executable archive. Nếu build chưa vượt qua test, không được tự kết luận JAR đã sinh.

### 6.2. Xem generated Java source

Trên Linux/macOS:

~~~bash
find target/generated-sources/annotations -type f -name '*MapperImpl.java'
cat target/generated-sources/annotations/com/example/inspect/GreetingMapperImpl.java
~~~

Trên PowerShell/Windows:

~~~powershell
Get-ChildItem -Path .\target\generated-sources\annotations -Recurse -Filter '*MapperImpl.java'
Get-Content .\target\generated-sources\annotations\com\example\inspect\GreetingMapperImpl.java
~~~

Trong Java được sinh, tìm method **toDto** và phép ánh xạ **source.getMessage() → dto.setText(...)** hoặc logic tương đương. Source do generator viết có thể có import, annotation, comment, timestamp hoặc coding style khác; **không hardcode toàn bộ generated file làm output bắt buộc**. Tên class chính **GreetingMapperImpl** tương ứng quy ước MapStruct trong ví dụ.

### 6.3. Xem compiled class và resource

~~~bash
find target/classes -type f -name '*.class'
cat target/classes/demo.properties
javap -classpath target/classes -public com.example.inspect.GreetingMapperImpl
~~~

Dùng **javap** để xem chữ ký bytecode class do processor sinh. **javap** không hiển thị Java source gốc nguyên văn; muốn xem bytecode instructions thì thêm **-c**. Không dùng tên đường dẫn **GreetingMapperImpl.java** để thay thế việc xác nhận **GreetingMapperImpl.class** đã được tạo.

Trên Windows PowerShell:

~~~powershell
Get-ChildItem .\target\classes -Recurse -Filter '*.class'
Get-Content .\target\classes\demo.properties
javap -classpath .\target\classes -public com.example.inspect.GreetingMapperImpl
~~~

Output đọc resource phải có dòng:

~~~properties
label=resource-ok
~~~

Nếu chỉ thấy resource ở **src/main/resources** mà không ở **target/classes**, hãy kiểm tra phase **process-resources**, các resource excludes/includes, filtering và đường dẫn trong **effective POM**.

## 7. Lựa chọn Gradle: cấu hình annotation processor và build

Chỉ dùng phần này nếu chọn Gradle. Tạo **settings.gradle**:

~~~groovy
rootProject.name = 'inspect-output'
~~~

Tạo **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'

    implementation 'org.mapstruct:mapstruct:1.6.3'
    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

- Spring Boot plugin cung cấp **bootJar** khi kết hợp Java plugin.
- Spring dependency-management plugin áp dụng Spring Boot BOM tương ứng; không cần ghi version cho starter đã được quản lý.
- **implementation mapstruct** cung cấp annotation và factory API; **annotationProcessor mapstruct-processor** cung cấp generator khi compile.
- **annotationProcessor** không phải runtime dependency của ứng dụng; output implementation Java/.class mới là thứ được nạp lúc chạy.
- **toolchain Java 17** chọn JDK compiler phù hợp; nó không tự đổi Java runtime của server.

### 7.1. Xây từng phần và xem output

~~~bash
./gradlew --version
./gradlew clean classes
~~~

Task **classes** kéo theo **compileJava** và **processResources**. Sau khi thành công:

~~~text
build/
├── generated/
│   └── sources/
│       └── annotationProcessor/java/main/com/example/inspect/
│           └── GreetingMapperImpl.java
├── classes/
│   └── java/main/com/example/inspect/
│       ├── InspectOutputApplication.class
│       ├── InspectController.class
│       ├── GreetingSource.class
│       ├── GreetingDto.class
│       ├── GreetingMapper.class
│       └── GreetingMapperImpl.class
└── resources/
    └── main/
        └── demo.properties
~~~

Đây là **đường dẫn Java plugin mặc định**, không phải tên folder do Spring Boot ép bắt buộc. Khi dùng Gradle Kotlin plugin, nhiều output nằm dưới **build/classes/kotlin/main**; khi custom compiler options hoặc buildDir, đường dẫn có thể khác.

Tiếp tục:

~~~bash
./gradlew clean test bootJar
~~~

Khi test/bootJar thành công, có thêm:
- **build/classes/java/test** — bytecode test;
- **build/test-results/test** — kết quả test máy đọc;
- **build/reports/tests/test** — báo cáo test HTML;
- **build/libs/inspect-output-1.0.0.jar** — executable Boot JAR theo tên mặc định.

**Lưu ý:** Nếu run **./gradlew clean classes**, sẽ chưa có test report và chưa chắc có JAR. Còn **./gradlew clean test bootJar** tạo các phần tương ứng theo task dependencies. Gradle có cache và incremental mechanism; không nên chạy **clean** cho mọi build thường ngày vì nó bỏ lợi ích của incremental outputs. Ở đây clean giúp quan sát output của một lượt build xác định.

### 7.2. Xem đúng generated source và compiled resource

Linux/macOS:

~~~bash
find build/generated/sources/annotationProcessor/java/main -type f -name '*MapperImpl.java'
cat build/generated/sources/annotationProcessor/java/main/com/example/inspect/GreetingMapperImpl.java

find build/classes/java/main -type f -name '*.class'
javap -classpath build/classes/java/main -public com.example.inspect.GreetingMapperImpl

cat build/resources/main/demo.properties
~~~

PowerShell/Windows:

~~~powershell
Get-ChildItem .\build\generated\sources\annotationProcessor\java\main -Recurse -Filter '*MapperImpl.java'
Get-Content .\build\generated\sources\annotationProcessor\java\main\com\example\inspect\GreetingMapperImpl.java
Get-ChildItem .\build\classes\java\main -Recurse -Filter '*.class'
Get-Content .\build\resources\main\demo.properties
javap -classpath .\build\classes\java\main -public com.example.inspect.GreetingMapperImpl
~~~

Với Gradle, **build/resources/main/demo.properties** là nơi main resources đã được xử lý trong source set output. Đừng tìm file ở **build/classes/java/main/demo.properties** rồi vội kết luận resource bị bỏ qua: compiled classes và processed resources thường nằm trong **hai output directories riêng biệt**.

## 8. Phân biệt ba mức kiểm tra: nguồn sinh, class, artifact

Để chứng minh một thành phần đã đi hết pipeline, kiểm tra theo thứ tự:

| Câu hỏi | Minh chứng | Ví dụ MapStruct |
| --- | --- | --- |
| Processor có chạy không? | Java source được sinh dưới generated-sources | GreetingMapperImpl.java |
| Java source có được compile không? | Bytecode xuất hiện ở output classes | GreetingMapperImpl.class |
| Resource có được copy/transform không? | Tệp nằm trong output resources | demo.properties |
| Archive có đóng chúng vào không? | Liệt kê entry trong JAR/WAR cuối cùng | BOOT-INF/classes/.../GreetingMapperImpl.class |
| Runtime có tìm thấy và sử dụng chúng không? | Integration test hoặc chạy JAR | GET /inspect trả chuỗi đúng |

Đặc biệt, **generated Java source không nhất thiết được đưa nguyên dưới dạng .java vào Spring Boot JAR**. Bình thường, JAR mang **compiled .class**. Nếu bạn chỉ thấy **GreetingMapperImpl.class** trong archive mà không thấy **GreetingMapperImpl.java**, đó là hành vi đóng gói thông thường, không phải thiếu mã sinh.

**Còn một lớp ý nghĩa khác:** compiler có thể tạo **.class** mà không bao giờ có một generated **.java** trên ổ đĩa (ví dụ một số compiler/bytecode transformer). Ngược lại, một generator có thể tạo Java source nhưng source đó không được đưa vào compilation source set nếu tasks/dependencies không được nối đúng. Vì vậy cần phân biệt loại generator trước khi chọn đường dẫn để kiểm tra.

## 9. Kiểm tra executable Spring Boot JAR

Sau khi package/bootJar, dùng **jar** tool có trong JDK:

~~~bash
jar tf target/inspect-output-1.0.0.jar
~~~

Hoặc với Gradle:

~~~bash
jar tf build/libs/inspect-output-1.0.0.jar
~~~

Tìm các entry đại diện (đường dẫn JAR dùng dấu **/** ở mọi hệ điều hành):

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/inspect/InspectOutputApplication.class
BOOT-INF/classes/com/example/inspect/InspectController.class
BOOT-INF/classes/com/example/inspect/GreetingMapper.class
BOOT-INF/classes/com/example/inspect/GreetingMapperImpl.class
BOOT-INF/classes/demo.properties
BOOT-INF/lib/mapstruct-1.6.3.jar
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Đây là **các entry cần tìm**, không phải danh sách đầy đủ hay lời hứa về thứ tự, vì Boot loader/libs/metadata thay đổi theo phiên bản và cấu hình. Spring Boot executable JAR thường để ứng dụng ở **BOOT-INF/classes**, dependencies runtime ở **BOOT-INF/lib**; launcher được chỉ trong manifest để hỗ trợ nested JARs.

### 9.1. Xem manifest thay vì chỉ dựa vào tên file

Trong môi trường có JDK **jar**:

~~~bash
jar xf target/inspect-output-1.0.0.jar META-INF/MANIFEST.MF
~~~

Lệnh **jar xf** sẽ **giải nén entry vào working directory**, vì vậy chỉ chạy trong **thư mục tạm/sandbox** khi cần kiểm tra manifest; không nên chạy vô ý tại project root rồi lẫn file giải nén vào source. Trên PowerShell, có thể dùng **jar tf** để xác nhận entry, hoặc công cụ ZIP viewer phù hợp để xem manifest mà không giải nén toàn bộ archive.

Một executable JAR Spring Boot thường có:
- **Main-Class** là launcher của Spring Boot;
- **Start-Class** là main application class (trong ví dụ **com.example.inspect.InspectOutputApplication**).

Đừng mặc định **Main-Class** phải trỏ trực tiếp tới class ứng dụng trong Spring Boot executable JAR; Spring Boot launcher chịu trách nhiệm nạp các nested libraries.

### 9.2. Xác nhận artifact chạy thật

Maven:

~~~bash
java -jar target/inspect-output-1.0.0.jar
~~~

Gradle:

~~~bash
java -jar build/libs/inspect-output-1.0.0.jar
~~~

Ở terminal thứ hai, khi Spring Boot đã startup thành công và cổng mặc định 8080 chưa được đổi:

~~~bash
curl http://localhost:8080/inspect
~~~

**Response body mong đợi chính xác**:

~~~text
generated-ok / resource-ok
~~~

Điều này xác nhận mã MapStruct đã sinh/được compile, resource đã có mặt và controller thực sự đọc chúng thông qua runtime classloader. Nếu **/inspect** trả lỗi, trước hết xem log khởi động, exception, profile/port và classpath; hiện diện của file ở source directory không đủ chứng minh runtime đọc được.

## 10. Phân biệt compile resources với resource filtering

**Copy resources** và **filter resources** là hai thao tác khác nhau:

- **Copy:** chuyển nội dung từ **src/main/resources** sang output resources mà không đổi giá trị.
- **Filtering/expansion:** thay token bằng giá trị tại thời điểm build; tệp trong output có thể khác source.

Trong ví dụ, **demo.properties** chỉ được copy. Nếu muốn xác minh filtering, hãy làm rõ bên nào thay token: Maven Resources Plugin, Gradle processResources hay Spring Environment tại **runtime**.

### 10.1. Maven filtering với Spring Boot parent

Với project kế thừa **spring-boot-starter-parent**, Spring Boot chuẩn bị resource filtering cho production application config và dùng token dạng **@...@** để tránh đụng placeholder **${...}** của Spring.

Ví dụ, thêm dòng sau vào **src/main/resources/application.properties** của project Maven:

~~~properties
app.build.version=@project.version@
app.runtime.flag=${RUNTIME_FLAG:off}
~~~

Sau:

~~~bash
./mvnw process-resources
~~~

Kiểm tra **target/classes/application.properties**. Với POM ví dụ version 1.0.0, nội dung logic của file sau build sẽ là:

~~~properties
app.build.version=1.0.0
app.runtime.flag=${RUNTIME_FLAG:off}
~~~

**@project.version@** đã được Maven thay ở build time; **${RUNTIME_FLAG:off}** được để Spring xử lý ở runtime. Tránh tự bật filtering sai delimiter cho mọi file, hoặc lọc binary assets như PNG/JAR/chứng chỉ có nguy cơ làm hỏng nội dung. Với source config chứa secrets theo môi trường, không nên nhúng secrets vào artifact trong bước filtering.

**Chú ý:** Spring Boot parent thường lọc production config; không nên mặc định mọi file trong **src/test/resources** hoặc mọi loại resource sẽ tự được lọc. Nếu project đã thay đổi parent hoặc resource plugin settings, kiểm tra **help:effective-pom** và output thực.

### 10.2. Gradle filtering cần được cấu hình có chủ đích

Gradle **processResources** mặc định copy resources; nó **không tự suy đoán** rằng **@project.version@** phải được thay như Spring Boot Maven parent. Nếu cần build metadata, dùng riêng file nguồn **src/main/resources/build-metadata.properties**:

~~~properties
app.build.version=@VERSION@
~~~

Và thêm task configuration này vào **build.gradle** (Groovy DSL):

~~~groovy
tasks.named('processResources') {
    inputs.property('appVersion', project.version.toString())

    filesMatching('build-metadata.properties') {
        filter { line ->
            line.replace('@VERSION@', project.version.toString())
        }
    }
}
~~~

Đoạn này thay **@VERSION@** bằng version của project khi **processResources** copy file. Sau **./gradlew processResources**, đọc **build/resources/main/build-metadata.properties**: với **version = '1.0.0'**, dòng dự kiến là **app.build.version=1.0.0**.

Đây là **cấu hình bổ sung cho dự án Gradle**, không phải một build.gradle hoàn chỉnh riêng. Nó chỉ nhắm vào một file text, có khai báo input phụ thuộc version để Gradle nhận biết thay đổi. Trong thực tế, có thể dùng **expand** hoặc resource filtering theo template syntax tùy yêu cầu, nhưng phải chú ý xung đột với Spring placeholders **${...}**. Giữ Spring runtime config tách biệt khỏi dữ liệu build-time khi có thể.

### 10.3. Đọc output đã xử lý, không đoán từ source

Trường hợp dễ hiểu nhầm:

~~~text
src/main/resources/application.properties: app.build.version=@project.version@
target/classes/application.properties:    app.build.version=1.0.0
~~~

Tệp nguồn vẫn chứa token; đó là chủ ý. **Output** mới phản ánh nội dung đã được Maven xử lý. Với Gradle, output nằm ở **build/resources/main** chứ không cùng chỗ với Java .class. Sau đó cần kiểm tra thêm **BOOT-INF/classes/application.properties** hoặc **BOOT-INF/classes/build-metadata.properties** trong JAR nếu file này phải được đóng gói.

## 11. Khi không thấy generated Java source: kiểm tra annotation processing

### 11.1. Phải có generator đúng scope

**Gradle:** MapStruct processor nằm trong **annotationProcessor**, không chỉ **implementation**. Hãy xem configuration:

~~~bash
./gradlew dependencies --configuration annotationProcessor
./gradlew compileJava --info
~~~

**Maven:** processor được khai báo trong **maven-compiler-plugin / annotationProcessorPaths** theo ví dụ. Kiểm tra effective POM và compile logs:

~~~bash
./mvnw help:effective-pom
./mvnw compile
~~~

**MapStruct 1.6.3** được dùng để minh họa; nếu dùng Lombok, Immutables, Hibernate metamodel hoặc OpenAPI generator, class/path/task cần kiểm tra sẽ khác. Không thấy generated source khi ứng dụng chỉ dùng **@SpringBootApplication** là bình thường: **annotation Spring không tự động đồng nghĩa có Java source được sinh ra**.

### 11.2. Kiểm tra package, class name và source set

Nếu interface nằm ở **com.example.inspect.GreetingMapper**, implementation theo MapStruct mặc định là **com.example.inspect.GreetingMapperImpl**. Tên package quyết định đường dẫn folder trên ổ đĩa. Đừng tìm dưới đường dẫn theo **Gradle project.group** hay **Maven groupId** rồi kết luận class không tồn tại: chúng không tự đổi Java package.

Với test annotation processors, Gradle dùng **testAnnotationProcessor** và output Java generated cho **test** source set (thường dưới **build/generated/sources/annotationProcessor/java/test**). Maven cũng có đường generated test source tương ứng qua test compiler. Nếu chỉ cấu hình processor cho **main**, source test có annotation cần processor riêng có thể không được xử lý.

### 11.3. Đừng ghi generated sources bằng tay

**build/** và **target/** thường bị bỏ khỏi version control và được tái tạo. Việc sửa trực tiếp **GreetingMapperImpl.java** trong output chỉ sửa bản được sinh cho phiên build hiện tại; lần compile/clean sau có thể ghi đè. Muốn đổi code generator output, sửa **interface/annotation/source model**, version hoặc processor options, rồi build lại.

Nếu generator chạy một task riêng (OpenAPI/GraphQL/protobuf), cấu hình output và nối task đó với source set/compile task là trách nhiệm của build script. Một generated file ở **build/generated/** nhưng không được compile sẽ không tạo .class và chưa chắc đi vào JAR.

## 12. Khi có .class nhưng không có .java sinh

Có thể xảy ra nhiều trường hợp:

1. Class đến trực tiếp từ **Java source viết tay**; không có generated .java tương ứng là bình thường.
2. Compiler tạo **inner class, anonymous class hoặc synthetic class** (ví dụ **Outer$Inner.class**) từ một source; không bắt buộc có một .java cho mỗi .class.
3. Công cụ bytecode enhancement/weaving hoặc plugin sinh bytecode trực tiếp.
4. IDE/build cache hoặc một lượt build trước để lại .class; khi cần xác minh lại, build sạch trong thư mục/module đúng.
5. **MapStruct implementation .class** có nhưng .java không ở đường dẫn mặc định do source-generation output được đổi.

Muốn biết một class được biên dịch từ đâu, xem source declaration, compiler task input, generated output, log compiler, và nếu cần dùng **javap -v** để quan sát metadata của class file. Metadata **SourceFile** (nếu có) gợi ý tên source nhưng không chứng minh nơi file nguồn nằm trên ổ đĩa hay đoạn code đã được generate ở thời điểm nào.

## 13. Khi resources không có trong JAR hoặc runtime không tìm thấy

Kiểm tra theo từng lớp:

1. **Source:** file thật sự nằm dưới **src/main/resources** hay source set/resource directory đã cấu hình?
2. **Process:** Maven **process-resources** hoặc Gradle **processResources** có chạy thành công, có filters/includes/excludes không?
3. **Output:** trong Maven xem **target/classes**; Gradle xem **build/resources/main**.
4. **Packaging:** **jar tf** xác nhận entry trong **BOOT-INF/classes** của đúng executable JAR.
5. **Runtime lookup:** code gọi **getResourceAsStream("name")** tương đối với package hay **getResourceAsStream("/name")** từ classpath root? Spring Environment có tự đọc file này không?
6. **Config override:** Spring profile và external config có ghi đè giá trị sau khi startup không?

Ví dụ với **demo.properties** ở root resources, đường dẫn classpath thực tế là **/demo.properties**. Nếu đổi thành **src/main/resources/config/demo.properties**, đường dẫn đúng trong Java phải là **/config/demo.properties**. Các file **application.properties** và **application.yml** có quy tắc nạp riêng của Spring Boot; một file tự đặt tên **demo.properties** không tự trở thành Spring property source trừ khi bạn nạp hoặc cấu hình nó.

Một lỗi khác: có file trên classpath nhưng dùng **new File("src/main/resources/demo.properties")** ở runtime. Cách này chỉ tình cờ chạy khi current working directory trỏ về project source; khi deploy JAR, thư mục src có thể không tồn tại. Dùng **ClassLoader.getResourceAsStream**, Spring **Resource**, hoặc cơ chế Spring configuration thích hợp cho tài nguyên trong JAR.

## 14. Đừng nhầm output directory của test với main

Trong Maven:

~~~text
target/classes/            # main classes và main resources
target/test-classes/       # compiled test classes và test resources
target/surefire-reports/   # báo cáo unit test theo Surefire
~~~

Trong Gradle:

~~~text
build/classes/java/main/   # main Java bytecode
build/classes/java/test/   # test Java bytecode
build/resources/main/      # main resources
build/resources/test/      # test resources
build/reports/tests/test/  # HTML test reports
build/test-results/test/   # test results cho công cụ đọc
~~~

**Test resources và test-only dependencies không mặc nhiên được đóng vào production Spring Boot executable JAR**. Vì vậy nếu code ứng dụng chạy được khi test nhưng lỗi sau deploy, có thể project đang đặt một file cấu hình hoặc dependency trong **src/test/resources**, **testImplementation** hay test classpath. Chuyển chúng sang main runtime scope khi thật sự là yêu cầu production, đồng thời tránh đưa secrets/tệp test nhạy cảm vào artifact.

Một bài test PASS cũng có thể che khác biệt giữa **testRuntimeClasspath** và Boot JAR runtime. Kiểm tra **artifact cuối cùng** bằng jar tool rồi chạy **java -jar** là bước cần thiết khi nghi lỗi packaging.

## 15. File sinh bởi plugin khác: phải tra chính task sinh ra nó

Ngoài annotation processors, dự án Spring Boot có thể dùng:

| Công cụ/cơ chế | Ví dụ output | Cách kiểm tra phù hợp |
| --- | --- | --- |
| **MapStruct** | Java implementation mapper | Generated .java, compiled .class, classpath |
| **Lombok** | AST/bytecode được javac biến đổi, thường không có Lombok-generated .java cho getter | **javap** với compiled class, annotationProcessor config |
| **OpenAPI Generator** | Client/server Java source theo template | Output folder do generate task/plugin cấu hình và source set |
| **Protobuf/gRPC** | Java source và các service stubs | Build plugin task output, compiled classes và dependencies |
| **JPA static metamodel** | Các lớp *_ hoặc source do annotation processor sinh | generated-sources và compiled classes |
| **Spring Boot build info** | **META-INF/build-info.properties** do goal/task buildInfo khi được cấu hình | Task/goal **build-info / bootBuildInfo**, processed resources/JAR |
| **Generated resources** | JSON, service metadata, config files | Task outputs, resources source set, JAR entries |

**Vị trí tùy plugin và phiên bản**, không cứ mọi file sinh đều xuất hiện trong **target/generated-sources/annotations** hoặc **build/generated/sources/annotationProcessor/java/main**. Ví dụ Lombok thường làm compiler sinh getter/setter trong class bytecode/AST, nên việc tìm **UserLombokGenerated.java** là sai phương pháp. Cần xác định **công cụ nào** đã tạo ra file hoặc bytecode cần kiểm tra.

Trong Spring Boot, goal **spring-boot:build-info** (Maven) hoặc task **bootBuildInfo** (Gradle) có thể tạo resource **META-INF/build-info.properties** chứa metadata của bản dựng, nếu project kích hoạt nó. Việc chỉ có Spring Boot plugin **không chứng minh** build info file luôn được tạo. Hãy kiểm tra config/task trước khi coi thiếu file là lỗi.

## 16. Debug khi đường dẫn hoặc kết quả không như mong đợi

| Hiện tượng | Câu hỏi chẩn đoán | Hành động cụ thể |
| --- | --- | --- |
| Không thấy **target/generated-sources/annotations** | Có annotation processor sinh Java thật không? Compiler đã chạy chưa? | Xem annotationProcessorPaths, **./mvnw compile**, compiler logs |
| Không thấy **build/generated/sources/annotationProcessor/java/main** | Processor nằm ở annotationProcessor hay chỉ implementation? | **./gradlew dependencies --configuration annotationProcessor**, compileJava --info |
| Có **GreetingMapperImpl.java** nhưng không có .class | Generated source có được compile? Có lỗi javac hoặc outputDir đổi? | Xem compile logs, **javap**, generated source set configuration |
| Có **.class** nhưng không thấy Java source sinh | Class có phải do javac tạo trực tiếp, inner/synthetic class hoặc generator chỉ sinh bytecode? | **javap -v**, xem plugin/processor behavior |
| Maven thiếu resource trong **target/classes** | Đã chạy process-resources? File bị exclude? | **./mvnw process-resources**, effective POM |
| Gradle thiếu resource trong **build/resources/main** | Đã chạy processResources? Có filesMatching/exclude? | **./gradlew processResources --info**, sourceSets |
| Resource có ở output nhưng không ở **BOOT-INF/classes** | Có đóng đúng JAR không? Boot archive khác plain JAR? | **jar tf**, kiểm tra bootJar/repackage và tên file |
| Có class trong build nhưng **ClassNotFoundException** | Class có trong runtime artifact/classpath? Dependency scope nào? | **jar tf**, Gradle runtimeClasspath/Maven dependency tree |
| **NoClassDefFoundError** với MapStruct implementation | Processor có sinh/compile? JAR có impl? | Kiểm tra generated .java, .class và BOOT-INF/classes |
| File bị lọc sai, token @...@ còn nguyên | Filtering có bật đúng file/delimiter và ở phase nào? | Đọc output resource, Maven effective POM hoặc Gradle processResources |
| Test thấy resource nhưng production không thấy | File chỉ nằm trong test resources? | Đối chiếu test vs main output, JAR entries |
| Không có JAR sau **classes/compile** | Đã chạy package/bootJar chưa? | Maven package hoặc Gradle bootJar sau khi test |
| Xem file ở root module nhưng build thực thi submodule | Build output của module nào? | Maven -pl hoặc Gradle :module:task, module-specific target/build |
| Generated file còn từ lần build cũ | Output là file mới hay cũ? Build cache/incremental? | Quan sát timestamp và task outcomes; clean build để xác minh khi cần |
| Chạy JAR lỗi nhưng chạy IDE tốt | IDE classpath khác archive? Runtime config/port? | So sánh JAR entries, java -jar và log thực tế |

**Nguyên tắc debug:** khoanh vùng nơi thông tin biến mất: **source → generated source → compiled class/resource → packaged artifact → runtime classpath**. Chọn lệnh kiểm tra đúng mắt xích đó. Nếu file đã có ở build output, đừng lập tức thêm dependency khác; trước tiên kiểm tra packaging và classpath.

## 17. Cẩn thận với build cache, file stale và thao tác xóa

**Maven target/** và **Gradle build/** thường là output có thể tái tạo; phần lớn dự án bỏ qua chúng trong Git. Khi debug lỗi kỳ lạ, **clean** có thể giúp loại file còn sót của một build trước:

~~~bash
./mvnw clean verify
~~~

Hoặc:

~~~bash
./gradlew clean test bootJar
~~~

Tuy nhiên, **clean xóa output của project**; chỉ thực hiện ở môi trường/dev workspace mà bạn được phép xóa. Với build bình thường, tránh clean mặc định để tận dụng incremental compilation/caching. Khi nhiều build chạy cùng workspace, output có thể thay đổi ngay trong lúc đang inspect; nên xem log/build id và dùng một bản dựng xác định.

**Không chỉnh sửa thủ công compiled classes, generated Java hoặc resources bên trong target/build để “sửa lỗi” lâu dài**. Thay đổi ấy mất khi build lại. Sửa source, build script, processor configuration hoặc resource template ở nguồn rồi xây artifact mới. Không commit secrets, tệp chứa credentials, report chứa thông tin nhạy cảm hoặc outputs không cần thiết.

Trong một multi-module build, mỗi module thường có **target/** hoặc **build/** riêng. Đừng chỉ tìm ở thư mục root rồi kết luận không có output; trước tiên xác định module đã thực hiện compilation/task.

## 18. Bài tập tự kiểm tra

### Câu 1. Không tìm thấy GreetingMapperImpl.java sau Maven compile. Điều đó chứng minh gì?

**Trả lời:** Chưa đủ kết luận. Có thể processor không được khai báo/chạy, build chưa tới compile, không có annotated mapper hợp lệ, đường generated source đã được đổi hoặc đã phát sinh lỗi compiler. Kiểm tra **annotationProcessorPaths**, log compile và **project.build.directory**. Với cấu hình demo, file dự kiến dưới **target/generated-sources/annotations/com/example/inspect/**.

### Câu 2. Vì sao Gradle có GreetingMapperImpl.class trong build/classes/java/main nhưng không có ở build/resources/main?

**Trả lời:** Đúng theo vai trò của hai output directory. **build/classes/java/main** chứa Java bytecode; **build/resources/main** chứa resource đã copy/xử lý. Không yêu cầu Java .class xuất hiện ở thư mục resources.

### Câu 3. Vì sao Spring Boot JAR có GreetingMapperImpl.class nhưng không có GreetingMapperImpl.java?

**Trả lời:** Archive runtime thường đóng gói bytecode chứ không cần Java source. Trong cấu trúc Boot executable JAR, compiled application classes ở **BOOT-INF/classes**; generated source .java tồn tại trong build workspace cho mục đích kiểm tra/debug.

### Câu 4. Sau Maven process-resources, application.properties vẫn còn token ${RUNTIME_FLAG:off} — có phải lọc lỗi không?

**Trả lời:** Không nếu đó là placeholder của Spring tại runtime. Spring Boot Maven parent dùng **@...@** cho Maven filtering để tránh xung đột. Chỉ token **@project.version@** được thay từ POM trong ví dụ.

### Câu 5. Resource ở src/test/resources và test chạy tốt. Có thể chắc chắn resource ấy có trong Boot JAR không?

**Trả lời:** Không. Test resources thường được copy vào **target/test-classes** hoặc **build/resources/test**, không tự đi vào production JAR. Nếu code runtime cần resource, đặt nó ở main resources/cấu hình packaging phù hợp và kiểm tra bằng **jar tf**.

### Câu 6. Khi nào việc kiểm tra mã nguồn sinh nên chuyển sang kiểm tra bytecode?

**Trả lời:** Khi processor chỉ biến đổi AST/bytecode (như Lombok), khi source file không có 1:1 với class, hoặc khi cần xác nhận compiler đã tạo class. **javap** cho chữ ký/bytecode, nhưng không chứng minh file .java nào đã được commit hoặc generate nếu thiếu thông tin nguồn.

## 19. Checklist hoàn tất kiểm tra đầu ra

- [ ] Xác định đúng project/module, Maven/Gradle version, JDK và task/phase đã chạy.
- [ ] Phân biệt **src/main/java**, **generated *.java**, **compiled *.class**, **processed resources** và **archive**.
- [ ] Maven: kiểm tra **target/generated-sources/annotations**, **target/classes**, **target/test-classes** theo phase.
- [ ] Gradle: kiểm tra **build/generated/sources/annotationProcessor/java/main**, **build/classes/java/main**, **build/resources/main** theo source set.
- [ ] Với annotation processor, xác nhận cả processor dependency/scope, generated source và compiled implementation.
- [ ] Đọc output resource sau filtering, không chỉ đọc template trong src/main/resources.
- [ ] Kiểm tra **BOOT-INF/classes** và **BOOT-INF/lib** trong **JAR thực sự được deploy**.
- [ ] Xác nhận class/resource có thể được nạp bằng classloader khi chạy **java -jar**.
- [ ] Không chỉnh trực tiếp generated outputs; sửa nguồn/cấu hình rồi build lại.
- [ ] Khi output thay đổi bất thường, phân biệt file cũ, cache/incremental build và source set/module được chọn.

**Kết luận:** Kiểm tra thư mục đầu ra là cách quan sát hành trình thực của mã và tài nguyên: **Java source → Java generated → bytecode**, song song với **resource processing**, rồi kết hợp vào **executable archive**. Khi biết từng công đoạn xuất file ở đâu, bạn có thể giải thích một lỗi Spring Boot bằng bằng chứng của build thay vì suy đoán từ IDE hoặc POM/build.gradle.

## Tài liệu tham khảo chính thức

- Gradle Java Plugin — Tasks và SourceSet Output: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Building Java & JVM Projects (Managing resources): https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — CompileOptions.generatedSourceOutputDirectory: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html
- Gradle — Working with Files: https://docs.gradle.org/current/userguide/working_with_files.html
- Apache Maven Compiler Plugin — compile goal/generatedSourcesDirectory: https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html
- Apache Maven Resources Plugin — Usage: https://maven.apache.org/plugins/maven-resources-plugin/usage.html
- Apache Maven — Filtering Resources: https://maven.apache.org/guides/mini/guide-filtering-resources.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Spring Boot — Nested JARs: https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html
- Spring Boot — Maven Plugin/Using the Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot — Properties and Configuration (Build-time expansion): https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- MapStruct — Installation: https://mapstruct.org/documentation/installation/
- MapStruct 1.6.3 — Reference Guide: https://mapstruct.org/documentation/1.6/reference/html/
