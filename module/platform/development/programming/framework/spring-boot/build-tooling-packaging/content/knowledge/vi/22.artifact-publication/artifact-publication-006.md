# Phát hành sources, Javadoc và metadata phụ thuộc phù hợp

Một thư viện Java được phát hành tốt cần nhiều hơn một file JAR chứa bytecode. Người dùng cần **sources JAR** để IDE mở mã nguồn khi debug, **Javadoc JAR** để tra cứu API ngay trong IDE, và **dependency metadata** chính xác để Maven/Gradle tự chọn đúng thư viện transitive, version và classpath. Nếu chỉ upload JAR mà thiếu POM hoặc khai báo sai dependencies, consumer có thể tải được artifact nhưng build lỗi, thiếu class lúc runtime hoặc phải tự khai báo thêm thư viện mà đáng lẽ publication phải mô tả.

Bài này hướng dẫn phát hành một Java library bằng **Maven và Gradle**, tạo và gắn hai artifact **-sources.jar** và **-javadoc.jar**, mô tả dependencies trong **Maven POM** và **Gradle Module Metadata (.module)**, cấu hình repository/credentials, publish nội bộ và chuẩn bị cho Maven Central. Ví dụ dùng **Java 17**, thư viện **greeting-core** và Spring Boot ecosystem làm bối cảnh. Phần code build là Java library độc lập để minh họa publication; một executable Spring Boot application cần được đóng gói theo quy tắc riêng ở phần 22.

## 1. Một publication hoàn chỉnh gồm những gì?

Giả sử tọa độ thư viện là:

```text
com.example.training:greeting-core:1.0.0
```

Một Maven-compatible repository thường lưu các thành phần:

```text
com/example/training/greeting-core/1.0.0/
├── greeting-core-1.0.0.jar
├── greeting-core-1.0.0.pom
├── greeting-core-1.0.0-sources.jar
├── greeting-core-1.0.0-javadoc.jar
├── greeting-core-1.0.0.jar.sha256
├── greeting-core-1.0.0.pom.sha256
├── greeting-core-1.0.0-sources.jar.sha256
└── greeting-core-1.0.0-javadoc.jar.sha256
```

Nếu publication được tạo bởi Gradle, repository có thể có thêm:

```text
greeting-core-1.0.0.module
```

Với Maven Central, release còn cần checksum và chữ ký GPG/PGP theo yêu cầu Portal; các file signature thường có đuôi .asc. Một repository nội bộ có thể áp dụng chính sách khác, nhưng vẫn nên lưu checksum, metadata và nguồn build rõ ràng.

| Thành phần | Chứa gì? | Người dùng hưởng lợi |
| --- | --- | --- |
| **Main JAR** | Class đã biên dịch và resource runtime | Compiler/JVM nạp thư viện |
| **POM** | GAV, dependencies, scopes, license, SCM và metadata Maven | Maven và Gradle khi đọc Maven metadata |
| **Sources JAR** | Mã nguồn Java/resource tương ứng với main artifact | IDE mở source, debugger và code navigation |
| **Javadoc JAR** | HTML API documentation được sinh từ Javadoc comments | IDE hiển thị mô tả API, người dùng tra cứu |
| **Gradle Module Metadata** | Variants, attributes, capabilities, dependencies và artifacts | Gradle chọn compile/runtime variant phù hợp |
| **Checksums** | Giá trị hash của artifact/metadata | Kiểm tra file tải về có đúng bytes |
| **PGP signature** | Chữ ký số gắn với file đã phát hành | Xác minh publisher/key và tính toàn vẹn |

**Ba nhóm có mục đích khác nhau:** main JAR là nội dung thực thi/biên dịch, sources/Javadoc là tài liệu đi kèm, còn POM/.module là metadata để build tool hiểu module. Sources và Javadoc không thay thế POM và cũng không phải dependency runtime.

## 2. Phân biệt classifier sources, javadoc và dependency

Maven artifact được định danh bởi tọa độ:

```text
groupId:artifactId:version[:classifier]@extension
```

Ví dụ:

| Artifact | Coordinate minh họa | Ý nghĩa |
| --- | --- | --- |
| Main library | com.example.training:greeting-core:1.0.0 | Artifact mặc định, thường là JAR bytecode |
| Sources | com.example.training:greeting-core:jar:sources:1.0.0 | JAR chứa source code |
| Javadoc | com.example.training:greeting-core:jar:javadoc:1.0.0 | JAR chứa HTML Javadoc |

Trong đường dẫn repository, classifier được nối vào tên file sau version:

```text
greeting-core-1.0.0.jar
greeting-core-1.0.0-sources.jar
greeting-core-1.0.0-javadoc.jar
```

**Classifier không tạo ra một module/version độc lập.** Cả ba file cùng thuộc com.example.training:greeting-core:1.0.0. Khi consumer khai báo dependency bình thường, build tool lấy main artifact và dependency metadata. IDE có thể tự tìm classifier sources/javadoc theo convention hoặc người dùng yêu cầu tải riêng.

Không khai báo sources/Javadoc như dependency runtime:

```xml
<!-- Không làm như thế trong dependencies của ứng dụng consumer. -->
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
    <classifier>sources</classifier>
</dependency>
```

Đoạn trên yêu cầu Maven đưa source archive vào dependency classpath như một artifact được khai báo; đó không phải cách cấu hình IDE source attachment thông thường. Dùng tính năng download sources/Javadoc của IDE hoặc plugin/tooling thích hợp.

## 3. Sources JAR: phải khớp với đúng binary release

Sources JAR đóng gói mã nguồn của **main source set** ứng với binary JAR đã phát hành. Người dùng cần source đúng phiên bản để:
- Đọc logic khi IDE điều hướng vào class thư viện.
- Đặt breakpoint và xem code trong debugger.
- So sánh implementation với API contract.
- Điều tra lỗi mà không phải đoán code từ bytecode.

Các nguyên tắc:
1. Sources phải thuộc **cùng commit, cùng GAV và cùng release** với main JAR.
2. Không lấy source từ branch mới hơn rồi gắn vào artifact version cũ.
3. Không đưa secret, file môi trường, key, private config, generated output nhạy cảm hoặc file build không liên quan vào archive.
4. Nếu thư viện dùng generated source, kiểm tra source đó đã được đưa vào source set trước khi tạo archive.
5. Không nhầm main sources với test sources. Test sources chỉ nên phát hành thành classifier riêng khi consumer thật sự cần.
6. Nếu có module-info.java, generated annotations hoặc multi-release source layout, kiểm tra nội dung archive để bảo đảm người dùng nhận đúng cấu trúc.

Sources JAR không chứa bytecode để JVM chạy; nó là artifact phục vụ developer tools. Một file source JAR tồn tại nhưng chứa thư mục rỗng hoặc source không đúng commit vẫn là publication kém chất lượng.

## 4. Javadoc JAR: mô tả contract của public API

Javadoc JAR là archive chứa HTML do Javadoc tool tạo từ comment/tag của source code. Nó nên giúp người dùng hiểu:
- Class/interface dùng để làm gì.
- Constructor cần những điều kiện gì.
- Tham số có ý nghĩa và giới hạn nào.
- Giá trị trả về có semantics gì.
- Exception nào có thể được ném.
- Thread-safety, lifecycle, nullability hoặc side effects khi có liên quan.
- Từ phiên bản nào API xuất hiện hoặc thay đổi (@since, @deprecated, @see).

Ví dụ comment có ích:

```java
/**
 * Creates a greeting service backed by the supplied logger.
 *
 * @param logger logger used to record greeting operations
 * @throws NullPointerException if {@code logger} is {@code null}
 * @since 1.0
 */
public GreetingService(Logger logger) {
    this.logger = Objects.requireNonNull(logger, "logger");
}

/**
 * Creates a greeting for a non-blank name.
 *
 * @param name person's display name
 * @return greeting text ending with an exclamation mark
 * @throws NullPointerException if {@code name} is {@code null}
 * @throws IllegalArgumentException if {@code name} is blank
 * @since 1.0
 */
public String greet(String name) {
    // implementation
}
```

**Javadoc mô tả contract, không chỉ lặp lại tên method.** Comment “Returns a string” không giúp consumer hiểu format, normalization, exceptions hay tác dụng phụ. Với API công khai, hãy ưu tiên viết docs cho package/class/public constructor/public method và dùng tags chính xác.

Javadoc archive không phải một website đã publish riêng. IDE có thể đọc HTML trong JAR; nếu muốn hosting documentation site, đó là một deliverable khác, thường được triển khai qua website/site pipeline.

## 5. Dependency metadata: vì sao chỉ upload JAR là chưa đủ?

Giả sử greeting-core dùng SLF4J và Jackson. Consumer khai báo duy nhất:

```xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
</dependency>
```

Build tool cần biết thư viện này phụ thuộc vào những module nào, version nào, ở classpath nào. Nếu metadata bị thiếu hoặc sai:
- Compile có thể fail vì public method dùng type không có trên compile classpath.
- Runtime có thể gặp NoClassDefFoundError.
- Dependency tree có thể chứa hai version xung đột.
- Consumer phải khai báo thủ công dependencies nội bộ.
- IDE có thể hiểu sai variant hoặc Java compatibility.

**Metadata chính xác là một phần của public contract.** Khi phát hành, không chỉ upload file JAR; phải mô tả đúng dependency graph và các thành phần API/runtime mà thư viện yêu cầu.

## 6. Maven POM và Gradle Module Metadata khác nhau thế nào?

| Định dạng | Công cụ hiểu chính | Mô tả |
| --- | --- | --- |
| **Maven POM (.pom)** | Maven; Gradle cũng có thể đọc | GAV, dependencies, scopes, optional/exclusions, dependency management và thông tin project |
| **Gradle Module Metadata (.module)** | Gradle | Mô hình module theo variants, attributes, capabilities, artifacts và dependencies cho từng variant |
| **Repository maven-metadata.xml** | Maven repository clients | Metadata cấp repository/module để liệt kê version hoặc snapshot timestamp/build number |

Không nhầm ba file:
- POM là descriptor của **một version project** và dependency graph của nó.
- Gradle .module là descriptor giàu thông tin hơn cho component/variants.
- maven-metadata.xml là metadata do repository quản lý để hỗ trợ version listing/snapshot resolution; không thay POM và không phải file khai báo dependency trực tiếp của project.

Gradle Module Metadata hỗ trợ các thông tin mà POM không biểu diễn đầy đủ, chẳng hạn rich version constraints, dependency constraints, capabilities và variant-aware resolution. Khi Gradle publish lên Maven-compatible repository, .module được lưu **bên cạnh** POM; Gradle consumers có thể đọc .module, còn Maven consumers tiếp tục dùng POM. Không tự xóa POM chỉ vì project được build bằng Gradle.

## 7. Dependency scope quyết định metadata consumer nhận được gì

### 7.1. Maven scopes

| Scope | Có trên compile classpath của thư viện? | Consumer nhận dependency transitively? | Mục đích thường gặp |
| --- | --- | --- | --- |
| compile | Có | Có | Dependency cần để compile và thường cần ở runtime |
| provided | Có, và test | Không theo transitivity thông thường | Container/JDK/runtime environment sẽ cung cấp |
| runtime | Không trên main compile; có trên runtime/test | Có trên runtime classpath | Dependency chỉ cần lúc chạy |
| test | Chỉ test | Không | JUnit, Mockito, test utilities |
| system | Có qua path local | Không theo cách quản lý repository thông thường | Tránh dùng cho library publication |

Nếu bỏ scope, Maven mặc định compile. test dependencies không nên xuất hiện như dependency runtime của consumer. provided thường dùng khi môi trường chạy cung cấp dependency; nếu consumer không có môi trường đó thì library có thể fail khi chạy.

Maven không có cấu hình api/implementation giống Gradle Java Library Plugin. Các compile dependencies thường được mô tả trong POM và có thể được consumer nhìn thấy transitive. Nếu cần che implementation dependencies, phải thiết kế module/packaging và scopes cẩn thận; không đổi compile thành runtime một cách máy móc khi source của thư viện vẫn cần dependency đó để compile.

### 7.2. Gradle api và implementation

Khi dùng java-library:
- api: dependency được expose trên compile classpath của consumer vì public API của library phụ thuộc vào type đó.
- implementation: dependency cần để build/runtime implementation, nhưng không nên lộ lên consumer compile classpath.
- compileOnly: cần compile nhưng không được cung cấp như runtime dependency mặc định; chỉ dùng khi consumer/runtime cung cấp.
- runtimeOnly: cần lúc chạy, không cần compile.
- testImplementation: chỉ dành cho test.

**Quy tắc quan trọng:** nếu public method signature của library dùng class từ một dependency, consumer cần thấy dependency đó khi compile. Khi ấy Gradle thường phải dùng api. Nếu dependency chỉ được dùng trong private implementation, chọn implementation.

Đừng chọn implementation chỉ để làm POM ngắn hơn nếu public API vẫn expose type của thư viện đó; consumer có thể compile fail dù library tự build thành công.

## 8. Project Java 17 mẫu: thư viện greeting-core

Dùng cùng Java source cho cả Maven và Gradle. Cấu trúc:

```text
greeting-core/
├── pom.xml                         # Phương án Maven
├── settings.gradle                 # Phương án Gradle
├── build.gradle                    # Phương án Gradle
└── src/
    ├── main/java/com/example/greeting/
    │   └── GreetingService.java
    └── test/java/com/example/greeting/
        └── GreetingServiceTest.java
```

groupId và package Java không bắt buộc giống nhau, nhưng dùng quy ước nhất quán giúp tìm kiếm và quản lý module dễ hơn.

### 8.1. Main library class

Tạo src/main/java/com/example/greeting/GreetingService.java:

```java
package com.example.greeting;

import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;

/**
 * Creates greeting messages and records each successful operation.
 *
 * <p>The logger is supplied by the consuming application so that the library
 * does not select a logging implementation on the consumer's behalf.
 *
 * @since 1.0
 */
public final class GreetingService {

    private final Logger logger;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * Creates a service backed by the supplied logger.
     *
     * @param logger logger used to record greeting operations
     * @throws NullPointerException if {@code logger} is {@code null}
     * @since 1.0
     */
    public GreetingService(Logger logger) {
        this.logger = Objects.requireNonNull(logger, "logger");
    }

    /**
     * Creates a greeting for a non-blank name.
     *
     * @param name person's display name
     * @return greeting text ending with an exclamation mark
     * @throws NullPointerException if {@code name} is {@code null}
     * @throws IllegalArgumentException if {@code name} is blank
     * @since 1.0
     */
    public String greet(String name) {
        String normalized = Objects.requireNonNull(name, "name").trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        String result = "Hello, " + normalized + "!";
        logger.info("Created greeting for {}", normalized);
        return result;
    }

    String toAuditJson(String name) {
        try {
            return objectMapper.writeValueAsString(
                    Map.of("message", greet(name)));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Could not create audit JSON", ex);
        }
    }
}
```

SLF4J Logger xuất hiện trong **public constructor**, vì vậy nó thuộc API của thư viện. Jackson chỉ được dùng trong package-private implementation method; người dùng library không cần gọi trực tiếp ObjectMapper để sử dụng public API. Đây là cơ sở để Gradle sample khai báo SLF4J bằng api và Jackson bằng implementation.

### 8.2. Unit test

Tạo src/test/java/com/example/greeting/GreetingServiceTest.java:

```java
package com.example.greeting;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class GreetingServiceTest {

    private final GreetingService service = new GreetingService(
            LoggerFactory.getLogger(GreetingServiceTest.class));

    @Test
    void trimsNameAndCreatesGreeting() {
        assertEquals("Hello, Lan!", service.greet("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet("   "));
    }
}
```

Test này không cần Spring ApplicationContext. Nếu dùng SLF4J API mà chưa có logging provider, runtime test có thể in cảnh báo provider; điều đó không làm thay đổi assertion của test. Trong ứng dụng thật, consumer chọn logging backend tương thích, ví dụ Logback hoặc Log4j2.

## 9. Maven POM đầy đủ: metadata và dependencies

Tạo pom.xml:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Greeting Core</name>
    <description>Reusable Java greeting library for publication examples.</description>
    <url>https://example.invalid/greeting-core</url>

    <licenses>
        <license>
            <name>The Apache License, Version 2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
            <distribution>repo</distribution>
        </license>
    </licenses>

    <developers>
        <developer>
            <id>example-team</id>
            <name>Example Engineering Team</name>
            <organization>Example Organization</organization>
            <organizationUrl>https://example.invalid</organizationUrl>
        </developer>
    </developers>

    <scm>
        <connection>scm:git:https://example.invalid/example/greeting-core.git</connection>
        <developerConnection>scm:git:ssh://git@example.invalid/example/greeting-core.git</developerConnection>
        <url>https://example.invalid/example/greeting-core</url>
    </scm>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.2</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.4.0</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.11.3</version>
                <executions>
                    <execution>
                        <id>attach-javadocs</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Các URL example.invalid và nhóm com.example.training là **giá trị minh họa**. Khi phát hành thật, thay chúng bằng namespace đã được tổ chức sở hữu, URL project, license, SCM và thông tin developer có thật. Không gửi metadata giả lên Maven Central.

POM khai báo:
- groupId:artifactId:version là danh tính module.
- name, description, url, licenses, developers, scm giúp người dùng hiểu nguồn gốc và quyền sử dụng.
- dependencies mô tả dependency graph của library.
- scope=test giữ JUnit ngoài runtime dependency graph của consumer.
- maven.compiler.release=17 cố định Java API/bytecode target của ví dụ.
- Source/Javadoc plugins tạo classifier artifacts và gắn chúng vào publication.

**POM là một phần sản phẩm.** Đừng chỉ sửa README mà quên cập nhật POM khi đổi dependencies, license, version hoặc SCM.

## 10. Maven Source Plugin: tạo -sources.jar

Plugin maven-source-plugin đóng gói main sources và gắn artifact với classifier sources. Goal jar-no-fork phù hợp khi bind vào lifecycle vì nó không fork lại build phase.

Đoạn cấu hình đã có trong POM mục 9:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.4.0</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <phase>verify</phase>
            <goals>
                <goal>jar-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Sau mvn verify, file dự kiến:

```text
target/greeting-core-1.0.0-sources.jar
```

Có thể gọi thủ công:

```bash
./mvnw source:jar
```

Nhưng release pipeline nên gắn execution vào lifecycle để install/deploy cùng đưa sources archive lên repository. Đừng tạo source JAR bằng cách nén thủ công một thư mục bất kỳ; plugin cần dùng đúng source roots và generated sources của project.

Nếu muốn phát hành test sources, Maven Source Plugin có test-jar/test-jar-no-fork, classifier thường là test-sources. Chỉ phát hành khi consumer thật sự có use case, chẳng hạn chia sẻ test fixtures; không mặc định public hóa toàn bộ test code.

## 11. Maven Javadoc Plugin: tạo -javadoc.jar

maven-javadoc-plugin dùng Javadoc tool của JDK để sinh HTML rồi đóng gói thành JAR classifier javadoc.

Đoạn cấu hình trong POM mục 9:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.3</version>
    <executions>
        <execution>
            <id>attach-javadocs</id>
            <phase>verify</phase>
            <goals>
                <goal>jar</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Artifact dự kiến:

```text
target/greeting-core-1.0.0-javadoc.jar
```

Chạy goal riêng để điều tra:

```bash
./mvnw javadoc:javadoc
./mvnw javadoc:jar
```

javadoc:javadoc sinh output HTML vào thư mục Javadoc output; javadoc:jar tạo archive để phát hành. Trong multi-module Maven project, javadoc:aggregate hoặc javadoc:aggregate-jar có thể tạo tài liệu tổng hợp; cần xác minh mỗi artifact publish vẫn có đúng classifier theo chính sách repository.

### 11.1. Javadoc lỗi thì xử lý ở source/API

Các nguyên nhân thường gặp:
- Public type/method có Javadoc tag sai hoặc thiếu nội dung cần thiết.
- @param, @return, @throws không khớp signature.
- JDK dùng để chạy Javadoc không tương thích với source/annotation processors.
- Classpath/module path thiếu dependency cần thiết.
- Generated source chưa có ở thời điểm chạy goal.
- External links tới tài liệu API bị chặn hoặc không truy cập được.

Ưu tiên sửa comment, dependency, source generation và JDK/toolchain. Không tắt toàn bộ doclint chỉ để release pass nếu chưa hiểu warning/error; Javadoc là tài liệu public API nên cần kiểm soát chất lượng.

## 12. Maven: build và kiểm tra ba artifact

Chạy từ root greeting-core:

```bash
./mvnw clean verify
```

Nếu không có Maven Wrapper, dùng Maven cài đặt tương thích:

```bash
mvn clean verify
```

Sau khi thành công, kiểm tra:

```bash
ls -lh target/greeting-core-1.0.0.jar
ls -lh target/greeting-core-1.0.0-sources.jar
ls -lh target/greeting-core-1.0.0-javadoc.jar
jar tf target/greeting-core-1.0.0-sources.jar
jar tf target/greeting-core-1.0.0-javadoc.jar
```

Trên Windows PowerShell, có thể dùng:

```powershell
Get-ChildItem .\target\greeting-core-1.0.0*.jar
jar tf .\target\greeting-core-1.0.0-sources.jar
jar tf .\target\greeting-core-1.0.0-javadoc.jar
```

Kỳ vọng:
- Main JAR có class com/example/greeting/GreetingService.class.
- Sources JAR có com/example/greeting/GreetingService.java.
- Javadoc JAR có index.html và package/class documentation tương ứng.

jar tf chỉ xác minh archive có entries; muốn kiểm tra nội dung docs, giải nén vào thư mục tạm và mở HTML. Kiểm tra thêm JAR không vô tình chứa target/, .git/, secret hoặc output nội bộ không liên quan.

## 13. Maven install và deploy khác nhau

| Lệnh | Đích | Mục tiêu |
| --- | --- | --- |
| mvn package | target/ | Compile, test theo lifecycle và tạo JAR |
| mvn verify | target/ | Chạy thêm kiểm tra và tạo sources/Javadoc theo executions |
| mvn install | Local Maven repository, thường ~/.m2/repository | Dùng artifact trên máy hiện tại |
| mvn deploy | Remote repository được cấu hình | Publish artifact/POM/classifiers để máy khác tiêu thụ |

Thử local:

```bash
./mvnw clean install
```

Sau đó artifact được cài vào local Maven repository cùng POM và attached artifacts. Consumer project trên cùng máy có thể khai báo dependency GAV mà không cần push lên server.

**install không phải deploy.** Một developer khác hoặc CI runner khác không tự có artifact trong local repository của bạn. Muốn chia sẻ qua tổ chức, cần remote repository như Nexus/Artifactory hoặc dịch vụ Maven-compatible.

## 14. Maven distributionManagement và credentials cho repository nội bộ

Trong POM, cấu hình đích deploy (thay bằng URL thật của công ty):

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Company Maven Releases</name>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Company Maven Snapshots</name>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

- repository là đích cho release version.
- snapshotRepository là đích cho version kết thúc bằng -SNAPSHOT.
- id là khóa để Maven tìm credentials tương ứng trong settings.xml.
- URL trên dùng domain .invalid, **không thể deploy thật**; thay bằng repository nội bộ được cấp quyền.

Credentials đặt trong ~/.m2/settings.xml hoặc secret configuration của CI, không commit vào POM:

```xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

id phải khớp chính xác với từng repository trong distributionManagement. `MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` được cấp từ secret store/CI dưới dạng environment variables; Maven settings nội suy chúng qua `${env.NAME}`. Với máy local, dùng encrypted Maven password hoặc cơ chế quản lý credential phù hợp. Không ghi user token/password trong Git, POM hoặc log build.

Sau khi URL/credentials được cấu hình thật:

```bash
./mvnw clean deploy
```

Maven chạy các phase trước deploy, tạo và upload main JAR, POM cùng sources/Javadoc classifiers đã attach. Kiểm tra file trên repository sau deploy; một dòng BUILD SUCCESS không thay thế việc xác minh repository nhận đủ artifacts.

## 15. Maven Central: yêu cầu release khác repository nội bộ

Tính đến luồng Central Publisher Portal hiện hành:
- Release version không được kết thúc bằng -SNAPSHOT.
- Với artifact packaging khác pom, cần main JAR cùng -sources.jar và -javadoc.jar.
- POM cần GAV chính xác, project name, description, URL, license, developer và SCM metadata.
- Các file phát hành cần checksum và chữ ký GPG/PGP theo yêu cầu Portal.
- Release đã public không thể tùy tiện ghi đè bằng một bộ bytes khác; chọn version cẩn thận.

**Đừng giả định cấu hình distributionManagement + Maven Deploy Plugin kiểu OSSRH cũ vẫn publish trực tiếp lên Central.** OSSRH legacy đã kết thúc ngày 30-06-2025. Central Portal có luồng Maven plugin riêng central-publishing-maven-plugin; version plugin phải theo hướng dẫn Portal đang áp dụng.

Ví dụ cấu hình Central Publisher Maven Plugin:

```xml
<plugin>
    <groupId>org.sonatype.central</groupId>
    <artifactId>central-publishing-maven-plugin</artifactId>
    <version>0.12.0</version>
    <extensions>true</extensions>
    <configuration>
        <publishingServerId>central</publishingServerId>
        <autoPublish>false</autoPublish>
    </configuration>
</plugin>
```

Thêm server id central vào settings.xml với **user token của Central Portal**. Cấu hình GPG signing để mỗi artifact cần thiết có chữ ký; Central plugin tạo checksums theo cấu hình mặc định. Plugin Portal không tự viết Javadoc, không tự tạo source JAR và không tự điền toàn bộ metadata POM cho bạn.

Với autoPublish=false, quá trình upload/validation có thể hoàn tất nhưng vẫn cần thao tác publish trong Central Portal. Chỉ bật tự động publish sau khi CI đã kiểm tra đúng tọa độ, artifacts, signatures và release policy.

## 16. Gradle: bật source và Javadoc variants bằng Java Library Plugin

Gradle có cơ chế tích hợp cho hai archive này. Khi dùng java-library:

```groovy
plugins {
    id 'java-library'
}

java {
    withSourcesJar()
    withJavadocJar()
}
```

Hai lời gọi:
- Tạo task sourcesJar và variant sourcesElements.
- Tạo task javadocJar và variant javadocElements.
- Khi kết hợp maven-publish, các archive được đưa vào publication từ components.java.

Không cần tự viết hai task ZIP/JAR nếu không có yêu cầu layout đặc biệt. Task do Java plugin tạo biết source sets và Javadoc task của project.

Kiểm tra task:

```bash
./gradlew tasks --all
./gradlew sourcesJar javadocJar
```

Với Gradle Wrapper trên Windows:

```powershell
.\gradlew.bat sourcesJar javadocJar
```

Nếu build chỉ áp dụng plugin java thay vì java-library, source/Javadoc archive vẫn có thể được tạo; java-library còn cung cấp api/implementation semantics phù hợp cho reusable library.

## 17. Gradle maven-publish: publication đầy đủ

Cấu hình Groovy DSL minh họa:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.training'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
    withJavadocJar()
}

repositories {
    mavenCentral()
}

dependencies {
    api 'org.slf4j:slf4j-api:2.0.16'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.18.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Greeting Core'
                description = 'Reusable Java greeting library.'
                url = 'https://example.invalid/greeting-core'
                licenses {
                    license {
                        name = 'The Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                    }
                }
                developers {
                    developer {
                        id = 'example-team'
                        name = 'Example Engineering Team'
                    }
                }
                scm {
                    connection = 'scm:git:https://example.invalid/example/greeting-core.git'
                    developerConnection = 'scm:git:ssh://git@example.invalid/example/greeting-core.git'
                    url = 'https://example.invalid/example/greeting-core'
                }
            }
        }
    }
    repositories {
        maven {
            name = 'localBuild'
            url = layout.buildDirectory.dir('repo')
        }
    }
}
```

Các URL và team identity vẫn là ví dụ. Thay bằng dữ liệu thật trước khi public release.

from components.java là bước quan trọng: nó lấy component model do Java Library Plugin cung cấp, bao gồm main JAR, dependencies/variants và các artifacts nguồn/Javadoc đã được khai báo. Nếu chỉ publish một file JAR thủ công, metadata có thể thiếu dependencies hoặc variants.

## 18. Gradle Kotlin DSL

Nếu dùng build.gradle.kts:

```kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example.training"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
    withSourcesJar()
    withJavadocJar()
}

repositories {
    mavenCentral()
}

dependencies {
    api("org.slf4j:slf4j-api:2.0.16")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.18.2")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            pom {
                name.set("Greeting Core")
                description.set("Reusable Java greeting library.")
                url.set("https://example.invalid/greeting-core")
            }
        }
    }
    repositories {
        maven {
            name = "localBuild"
            url = uri(layout.buildDirectory.dir("repo"))
        }
    }
}
```

Đây là phương án Kotlin DSL thay thế Groovy. Dùng typed create<MavenPublication>, from(components["java"]) và Property.set; không trộn cú pháp Groovy vào Kotlin.

## 19. Gradle publish và kiểm tra local repository

Chạy:

```bash
./gradlew clean test publish
```

Hoặc task publication cụ thể:

```bash
./gradlew publishMavenJavaPublicationToLocalBuildRepository
```

Repository demo dự kiến có:

```text
build/repo/com/example/training/greeting-core/1.0.0/
├── greeting-core-1.0.0.jar
├── greeting-core-1.0.0.pom
├── greeting-core-1.0.0.module
├── greeting-core-1.0.0-sources.jar
└── greeting-core-1.0.0-javadoc.jar
```

Có thể publish vào ~/.m2/repository bằng:

```bash
./gradlew publishToMavenLocal
```

mavenLocal() phù hợp thử nghiệm trên máy developer; không nên là nguồn dependency mặc định của CI vì local content có thể khác giữa các máy.

## 20. Gradle remote repository và credentials

Cấu hình repository nội bộ:

```groovy
publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.invalid/repository/maven-releases')
            credentials(PasswordCredentials)
        }
    }
}
```

Gradle lấy credentials theo repository name: internalUsername và internalPassword trong user-level ~/.gradle/gradle.properties hoặc secret injection của CI. Không commit token. Có thể tách release và snapshot repository theo version; host example.invalid là placeholder cần thay bằng URL thật.

## 21. Gradle Module Metadata và variants

Từ Gradle 6.0, maven-publish có thể phát hành Gradle Module Metadata bên cạnh POM. Java library thường có:
- apiElements cho compile-time consumers.
- runtimeElements cho runtime consumers.

Metadata có thể mô tả org.gradle.usage, org.gradle.category, org.gradle.libraryelements, org.gradle.jvm.version, capabilities, constraints và variant-specific dependencies.

Gradle consumer có thể dùng .module để chọn variant phù hợp; Maven consumer dùng POM. Không sửa .module thủ công: điều chỉnh component, attributes, api/implementation và toolchain trong build script rồi để Gradle tạo metadata.

## 22. Dependency metadata phải phản ánh public contract

Trong sample, SLF4J nằm trong public constructor nên Gradle api. Jackson chỉ phục vụ implementation nên Gradle implementation. JUnit chỉ phục vụ test nên testImplementation.

Maven không có api/implementation. Compile dependencies thường được công bố transitive. Maven optional=true có nghĩa consumer không tự nhận dependency đó; chỉ dùng khi feature thực sự optional. Nếu library luôn cần Jackson runtime nhưng đánh optional, consumer có thể gặp NoClassDefFoundError.

Exclusions chỉ dùng khi biết chính xác transitive dependency nào cần loại; loại nhầm có thể làm consumer thiếu class runtime.

## 23. Spring Boot executable JAR và reusable library JAR

Spring Boot repackage tạo executable archive có layout BOOT-INF/classes và BOOT-INF/lib để chạy bằng java -jar. Đây không phải JAR phù hợp để làm dependency Java thông thường vì class application nằm dưới BOOT-INF/classes thay vì root classpath.

**Library module nên publish regular/thin JAR** từ Java Library Plugin hoặc Maven JAR lifecycle. Nếu một Maven module cần cả main library JAR và executable archive, có thể attach executable bằng classifier exec trong execution repackage:

```xml
<executions>
    <execution>
        <id>repackage</id>
        <configuration>
            <classifier>exec</classifier>
        </configuration>
    </execution>
</executions>
```

Nếu starter parent đã tạo execution repackage, hãy cấu hình đúng execution đó thay vì tạo execution trùng. Với Gradle, tách module library và Boot application thường rõ ràng hơn.

## 24. Multi-module publication

Trong Maven multi-module:
- Root aggregator thường packaging=pom.
- Mỗi publishable child module cần POM, main JAR, sources và Javadoc.
- Quản lý plugin version ở parent nhưng áp dụng executions đúng module.
- Có thể dùng javadoc:aggregate-jar cho tài liệu tổng hợp, nhưng vẫn xác minh classifier cho từng artifact theo policy.

Trong Gradle multi-project:
- Áp dụng java-library và maven-publish trên từng library module.
- Cấu hình withSourcesJar/withJavadocJar trên component cần publish.
- Publication lấy đúng components.java.
- Chạy task path như :greeting-core:publish.
- Không publish aggregator hoặc convention plugin như library nếu không có module artifact phù hợp.

## 25. Kiểm tra metadata và archives sau khi publish

Maven:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree
jar tf target/greeting-core-1.0.0-sources.jar
jar tf target/greeting-core-1.0.0-javadoc.jar
```

Gradle:

```bash
./gradlew outgoingVariants
./gradlew dependencies
```

Kiểm tra POM có đúng GAV, dependencies, scope, license, SCM; .module có đúng api/runtime variants và attributes; main JAR có class đã biên dịch; sources JAR có Java source cùng commit; Javadoc JAR có HTML API. Test dependencies không được thành runtime dependency của consumer. Không để secret, .git, build output hoặc file nội bộ không liên quan lọt vào archive.

## 26. Consumer smoke test

Publication chỉ thực sự tốt khi một project khác resolve được bằng GAV.

Maven consumer khai báo dependency:

```xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
</dependency>
```

Sau khi library đã mvn install hoặc deploy, chạy dependency:tree và mvn test. Consumer không khai báo classifier sources/javadoc.

Gradle consumer:

```groovy
repositories {
    maven {
        url = uri('../greeting-core/build/repo')
    }
    mavenCentral()
}

dependencies {
    implementation 'com.example.training:greeting-core:1.0.0'
}
```

Kiểm tra compile/runtime graph:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration compileClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Mong đợi SLF4J có ở compile classpath, Jackson ở runtime graph, JUnit không bị kéo vào runtime của consumer. Consumer test phát hiện metadata sai tốt hơn việc chỉ chạy tests trong project library.

## 27. Maven Central: requirements và Gradle limitation hiện hành

Maven Central yêu cầu release version không kết thúc bằng -SNAPSHOT; main artifact, POM, sources JAR, Javadoc JAR, metadata POM, checksums và chữ ký GPG/PGP. POM cần GAV, name, description, URL, license, developer và SCM.

Maven Central hiện dùng Central Publisher Portal và central-publishing-maven-plugin. Plugin tạo checksums nhưng không tự tạo tất cả sources/Javadoc/signatures/metadata. OSSRH legacy đã kết thúc ngày 30-06-2025. Upload/validation thành công không đồng nghĩa đã public nếu Portal yêu cầu thao tác publish thủ công.

**Gradle có một điểm khác:** tài liệu Sonatype hiện nêu chưa có Gradle plugin chính thức để publish trực tiếp tới Central Publisher Portal. maven-publish vẫn phù hợp cho Nexus/Artifactory/internal Maven repositories và sinh POM/.module, nhưng muốn publish Central phải chọn phương án Portal phù hợp như community plugin đã đánh giá, JReleaser, upload bundle/API hoặc OSSRH Staging API compatibility. Không coi task publish mặc định là đã publish lên Central.

## 28. Signing và checksums

Checksum giúp phát hiện file khác bytes; GPG/PGP signature gắn file với private key tương ứng; SBOM/provenance bổ sung thông tin thành phần và quy trình build. Chúng có vai trò khác nhau.

Gradle Signing Plugin có thể ký publication:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
    id 'signing'
}

signing {
    sign publishing.publications.mavenJava
}
```

Đây là đoạn bổ sung vào build script đã tạo publication mavenJava. Key material phải được cung cấp qua secret manager/CI, không hardcode private key hoặc passphrase. Kiểm tra signatures của main JAR, POM, sources JAR, Javadoc JAR và metadata theo yêu cầu repository.

## 29. Versioning và provenance

- 1.0.0-SNAPSHOT: build phát triển, repository snapshot có thể thay đổi.
- 1.0.0: release bất biến sau khi public.
- 1.1.0: thêm tính năng tương thích theo policy.
- 2.0.0: breaking API nếu áp dụng SemVer.

Không để main JAR lấy từ commit A, sources JAR từ commit B, Javadoc từ code C và POM mô tả dependencies của version D. Một release là **một bộ artifacts có cùng provenance**. Lưu commit ID, build ID, checksums và release manifest để điều tra lỗi.

## 30. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Repository chỉ có main JAR | Plugin chưa chạy hoặc artifact không attach | Bind source:jar-no-fork và javadoc:jar |
| Sources không khớp binary | Khác commit | Build lại cùng commit/version |
| Javadoc JAR thiếu package | Source roots/generated sources không được nhận diện | Kiểm tra source sets và lifecycle |
| Javadoc fail | Doclint/tag/JDK/classpath | Sửa API docs và toolchain |
| Test dependencies bị publish | Scope/configuration sai | Maven test hoặc Gradle testImplementation |
| Consumer thiếu type public API | Dependency bị scope runtime/implementation | Maven scope đúng hoặc Gradle api |
| NoClassDefFoundError | Thiếu runtime dependency hoặc optional sai | Kiểm tra dependency graph |
| .module có nhưng Maven không dùng | Maven chỉ hiểu POM | Kiểm tra POM mapping |
| Maven POM thiếu dependencies | Upload JAR riêng hoặc POM sai | Publish POM chính xác |
| Sources/Javadoc classifier trùng | Plugin attach lặp | Loại execution duplicate |
| Central từ chối release | Thiếu docs, metadata, checksum/signature | Xem Portal validation |
| Dùng deploy endpoint OSSRH cũ | OSSRH đã kết thúc | Chuyển sang Central Portal |
| Gradle publish xong nhưng Central không có | Publish tới repository khác | Cấu hình Central Portal riêng |
| 401/403 | Credential/id/namespace sai | Kiểm tra settings.xml hoặc Gradle properties |
| Release không overwrite được | Repository immutable | Tạo version mới |
| Boot fat JAR không load như dependency | Class nằm dưới BOOT-INF/classes | Publish thin JAR; executable classifier riêng |

## 31. Checklist trước khi publish

- [ ] GAV/version/packaging đúng.
- [ ] Main JAR chứa đúng class/resource.
- [ ] Sources JAR cùng commit với main JAR.
- [ ] Javadoc JAR có HTML cho public API.
- [ ] POM mô tả đúng dependencies/scopes/optional/exclusions.
- [ ] Gradle api chỉ cho dependency được expose qua public API.
- [ ] Gradle implementation cho dependency nội bộ.
- [ ] Test-only dependencies không thành runtime dependencies.
- [ ] POM có name/description/URL/license/developer/SCM thật.
- [ ] Gradle dùng from components.java, withSourcesJar và withJavadocJar.
- [ ] Multi-module artifacts có classifiers đúng.
- [ ] Không publish executable Boot fat JAR làm main library dependency.
- [ ] Consumer project resolve được GAV và compile/runtime graph.
- [ ] Checksums/signatures đúng policy.
- [ ] Credentials ngoài source code, quyền tối thiểu.
- [ ] Central Portal flow được kiểm tra riêng.
- [ ] Release artifacts/provenance được lưu để audit/rollback.

**Ghi nhớ:** Main JAR là bytecode, **sources/Javadoc JAR** giúp developer hiểu và debug API, còn **POM/Gradle .module** quyết định consumer resolve dependency graph/variants thế nào. Hãy tạo tất cả từ cùng source commit, kiểm tra bằng consumer project, xác minh metadata/signatures/checksums rồi mới publish.

## Tài liệu tham khảo chính thức

- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Source Plugin — Usage](https://maven.apache.org/plugins/maven-source-plugin/usage.html)
- [Apache Maven Source Plugin — jar-no-fork](https://maven.apache.org/components/plugins/maven-source-plugin/jar-no-fork-mojo.html)
- [Apache Maven Javadoc Plugin 3.11.3](https://maven.apache.org/plugins-archives/maven-javadoc-plugin-3.11.3/plugin-info.html)
- [Apache Maven — Deployment Transports and Credentials](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)
- [Gradle — Supported Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html)
- [Gradle — Repository Credentials](https://docs.gradle.org/current/userguide/supported_repository_protocols.html)
- [Spring Boot — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Sonatype Central — Publishing Requirements](https://central.sonatype.org/publish/requirements/)
- [Sonatype Central — Publishing with Maven](https://central.sonatype.org/publish/publish-portal-maven/)
- [Sonatype Central — Publishing with Gradle](https://central.sonatype.org/publish/publish-portal-gradle/)
- [Sonatype Central — OSSRH Sunset](https://central.sonatype.org/publish/publish-gradle/)