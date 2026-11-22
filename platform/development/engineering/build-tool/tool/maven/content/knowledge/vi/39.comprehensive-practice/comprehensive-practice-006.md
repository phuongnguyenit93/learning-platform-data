# Đóng gói ứng dụng chạy độc lập và kiểm tra ngoài IDE bằng Maven

> **Build Tool Maven · Thực hành tổng hợp**  
> Bài thực hành đầu-cuối với **Maven 3.9.x, JDK 17**: thiết kế ứng dụng Java có **thư viện runtime** và **classpath resource**, viết kiểm thử JUnit 5, dùng Maven Shade Plugin 3.6.2 tạo **executable/uber-JAR**, tạo tùy chọn **ZIP distribution** bằng Maven Assembly Plugin 3.8.0, kiểm tra `META-INF/MANIFEST.MF`, kiểm entries thực trong archive, chạy từ **thư mục ngoài project** bằng Java 17 mà **không dùng IDE hoặc Maven để khởi động**, so SHA-256, thực hiện smoke test trên artifact bàn giao và điều tra lỗi. Các lệnh, tên tệp và stdout trong bài khớp với project mẫu; output Maven log và giá trị SHA-256 phụ thuộc môi trường thật.

## 1. Định nghĩa “chạy độc lập” trước khi bắt đầu

Một ứng dụng **chạy độc lập ngoài IDE** trong phạm vi bài này có nghĩa:

- Đã compile và đóng gói thành một **JAR thực thi** (`.jar`).
- JAR có **entry point** hợp lệ (`Main-Class`).
- Các class của ứng dụng, thư viện cần cho runtime và bundled resources **đã hiện diện theo đúng packaging contract**.
- Một máy khác chỉ cần **Java runtime đủ phiên bản** và đúng file artifact, không cần source project, IDE, Maven local repository hoặc Maven để khởi chạy.
- Tài liệu chạy nêu rõ command, JDK tối thiểu, input arguments, cấu hình external nếu có và cách nhận biết thành công/thất bại.

**Không đồng nghĩa “không cần cài Java”.** JAR tự chạy không phải native `.exe`; `java -jar` vẫn yêu cầu Java runtime phù hợp. Muốn phân phối cùng runtime hoặc tạo native installer, cần xem `jlink`, `jpackage` hoặc cơ chế đóng gói khác, không tự kết luận một shaded JAR mang theo JVM.

### 1.1. Kịch bản người học cần hoàn thành

```text
Source Java + resource + Maven POM
             |
       mvn clean verify
             |
       JUnit tests PASS
             |
   JAR Plugin -> thin JAR
             |
   Shade Plugin -> executable uber-JAR
             |
       target/standalone-cli-1.0.0.jar
             |
       Archive audit + smoke test
             |
       SHA-256 + CI evidence
             |
             +--> Copy JAR sang thư mục tạm -> java -jar -> PASS
             |
             +--> ZIP distribution (profile dist)
                        |
                  Giải nén ở thư mục khác
                        |
                  bin/run.sh hoặc bin/run.cmd -> PASS
```

**Tiêu chí hoàn thành quan trọng nhất:** không chỉ `BUILD SUCCESS`, mà là **chính file được bàn giao** chạy đúng khi không còn IDE classpath và không phụ thuộc `target/classes` của workspace build.

## 2. Đừng nhầm bốn loại kết quả

| Loại | Ví dụ | Chứa gì | Hợp đồng chạy |
| --- | --- | --- | --- |
| Classes output | `target/classes/` | `.class` và resources đã copy | Chỉ là output tạm; không phải JAR |
| Thin JAR | `target/standalone-cli-1.0.0.jar` trước Shade | App classes, resources, manifest; thường không có thư viện bên ngoài | Cần runtime classpath bổ sung nếu app dùng libs |
| Uber/fat/shaded JAR | `target/standalone-cli-1.0.0.jar` sau Shade của lab | App classes + Commons Lang + resources + executable manifest | `java -jar` đủ nếu chỉ phụ thuộc Java runtime |
| Distribution ZIP | `target/standalone-cli-1.0.0-dist.zip` | Final shaded JAR và scripts theo thư mục | Giải nén và chạy launcher cho OS tương ứng |

Tên `standalone-cli-1.0.0.jar` **không tự chứng minh** là shaded; người dùng phải biết mục tiêu build/profile và kiểm tra **archive bytes thật**.

Một Spring Boot executable JAR, WAR chạy trong servlet container hay JAR module JPMS có cấu trúc/command khác. Lab chọn **Java classpath application đóng gói bằng Shade** để người học thấy các bước rõ ràng.

## 3. Kiến thức nền đủ dùng

### 3.1. Maven lifecycle

Các phase liên quan:

```text
validate
    |
compile          -> biên dịch Java source chính
    |
test-compile     -> biên dịch test source
    |
test             -> Surefire chạy JUnit
    |
package          -> JAR Plugin tạo archive, Shade Plugin xử lý artifact
    |
verify           -> các kiểm tra/goal gắn ở verify; tùy profile tạo ZIP
    |
install          -> đưa GAV vào local Maven repository
    |
deploy           -> phát hành GAV vào remote Maven repository
```

`mvn clean verify` chạy **clean lifecycle trước**, rồi default lifecycle tới `verify`. Nó **không tự upload** artifact lên registry. `mvn install` khác `deploy`; cả hai **không cần** chỉ để kiểm thử JAR ở máy tạm.

### 3.2. Những đường dẫn cần phân biệt

```text
src/main/java             Java source chạy production
src/main/resources        bundled resources của ứng dụng
src/test/java             unit tests
src/test/resources        test-only resources

target/classes            main classes và main resources
target/test-classes       test classes và test resources
target/surefire-reports   JUnit XML/text evidence
target/*.jar              packaged JAR(s)
~/.m2/repository          Maven local dependency/plugin repository cache
```

**`src/test/resources` không tự đi vào main JAR.** IDE và JUnit test classpath có thể thấy file test resources, còn packaged app không có. Đây là một trong những lý do lớn nhất khiến “test xanh, deploy lỗi”.

### 3.3. `java -jar` khác `java -cp`

```bash
java -jar app.jar
```

đọc `Main-Class` từ manifest của JAR và dùng runtime classpath theo JAR/manifest layout. Theo Java launcher, **các classpath setting bên ngoài theo `-cp` không được dùng bổ sung theo cách thông thường khi chọn `-jar`**.

```bash
java -cp "app.jar:lib/*" org.example.standalone.App
```

chỉ định **main class trên command line** và cung cấp runtime libraries từ `lib/`; dùng dấu phân cách `;` trên Windows.

Một thin JAR có `Main-Class` đúng **vẫn có thể thiếu thư viện khi `java -jar`**. Shade Plugin giúp tạo JAR chứa các runtime classes cần thiết để triển khai thành một file.

### 3.4. JAR không phải nơi chứa secret

Một file trong `src/main/resources` thường được copy vào archive, dễ được xem bằng `jar tf`/ZIP tool. **Không** đóng password, token, private key hoặc production secrets vào JAR. Những bí mật cần cung cấp qua cơ chế cấu hình ngoài/secret manager được bảo vệ.

## 4. Đề bài thực hành: một ứng dụng chào người dùng

Ứng dụng có **ba đặc điểm bắt buộc**:

1. **Java entry point** ở `org.example.standalone.App`.
2. Một **runtime dependency** có thật: `org.apache.commons:commons-lang3:3.14.0`, dùng `StringUtils.upperCase`.
3. Một **resource** được đóng vào classpath: `messages/banner.properties`.

Với arguments:

```bash
java -jar standalone-cli-1.0.0.jar Maven
```

**Stdout chính xác của ứng dụng**:

```text
Standalone Demo | HELLO OUTSIDE IDE | Maven
```

Khi không có argument:

```bash
java -jar standalone-cli-1.0.0.jar
```

**Stdout chính xác**:

```text
Standalone Demo | HELLO OUTSIDE IDE | world
```

Những outputs này được xây từ `App.java` và `banner.properties` bên dưới, không phải text suy đoán từ Maven logger.

### 4.1. Cấu trúc toàn bộ project

```text
standalone-cli/
├── pom.xml
├── audit/
│   └── JarAudit.java
├── scripts/
│   ├── run.sh
│   └── run.cmd
├── src/
│   ├── assembly/
│   │   └── distribution.xml
│   ├── main/
│   │   ├── java/
│   │   │   └── org/example/standalone/App.java
│   │   └── resources/
│   │       └── messages/banner.properties
│   └── test/
│       └── java/org/example/standalone/AppTest.java
└── target/                   (Maven sinh sau build)
```

**Không đặt `audit/JarAudit.java` trong `src/main/java`.** Nó chỉ là tiện ích kiểm final JAR, không phải một phần ứng dụng được giao.

**Không đặt `scripts/run.sh` trong `src/main/resources`.** Nó thuộc ZIP distribution, không phải Java classpath resource.

## 5. POM đầy đủ: Java 17, JUnit, Shade và profile ZIP

File `pom.xml` dưới đây có thể dùng nguyên văn cho cây project trên. Không cần private repository, publisher token hoặc GPG key để build. Mạng phải cho Maven resolve dependencies/plugins từ Maven Central hoặc approved mirror.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>standalone-cli</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Standalone CLI</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>org.example.standalone.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>create-executable-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <shadedArtifactAttached>false</shadedArtifactAttached>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.example.standalone.App</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>dist</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-assembly-plugin</artifactId>
                        <version>3.8.0</version>
                        <executions>
                            <execution>
                                <id>zip-final-executable-jar</id>
                                <phase>verify</phase>
                                <goals>
                                    <goal>single</goal>
                                </goals>
                                <configuration>
                                    <descriptors>
                                        <descriptor>src/assembly/distribution.xml</descriptor>
                                    </descriptors>
                                </configuration>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
```

### 5.1. Vì sao ghim versions?

Maven plugins cũng là build inputs. Nếu mọi lần build tự resolve plugin version khác, khả năng tái hiện có thể suy giảm. POM pin các versions cần thiết trong lab; ở project thực, phải xem **support matrix và security updates** trước khi chọn/nâng version.

Mốc Java 17 được cấu hình bằng:

```xml
<maven.compiler.release>17</maven.compiler.release>
```

Điều này chọn API/classfile target theo Compiler Plugin; **không cài Java 17** cho máy người dùng. Dùng `java -version` để xác nhận runtime thật.

### 5.2. Shade chạy khi nào?

`maven-jar-plugin` được bind vào `package` theo packaging `jar`, tạo main JAR từ `target/classes`. Sau đó execution của `maven-shade-plugin` ở `package` xử lý project artifact và resolved runtime dependencies.

Trong POM lab:

```xml
<shadedArtifactAttached>false</shadedArtifactAttached>
```

đồng nghĩa shaded JAR **thay main artifact**. Vì vậy file cần chạy/bàn giao là:

```text
target/standalone-cli-1.0.0.jar
```

Các project khác có thể cấu hình `shadedArtifactAttached=true`, `shadedClassifierName`, `finalName`, `outputFile` và sinh tên khác. **Không áp filename bài lab cho mọi POM.**

### 5.3. `ManifestResourceTransformer` và `ServicesResourceTransformer`

`ManifestResourceTransformer` đặt:

```text
Main-Class: org.example.standalone.App
```

trong executable shaded JAR. `ServicesResourceTransformer` hỗ trợ gộp `META-INF/services` khi các JAR có service provider descriptors. Lab không phụ thuộc ServiceLoader trực tiếp, nhưng cấu hình minh họa cách tránh một lỗi thường gặp khi shading nhiều libraries.

**Không nghĩ Shade tự sửa mọi metadata đặc thù** (Spring, Plexus, signed JARs, module descriptor...). Ứng dụng có framework hoặc reflection phức tạp cần kiểm transformer/minimization/relocation riêng.

### 5.4. Vì sao `createDependencyReducedPom=false`?

Lab phát hành **một ứng dụng tự chạy**, không xây một thư viện cho Maven consumers. Việc không sinh dependency-reduced POM giảm file phát sinh cạnh source. Nhưng nếu một project **publish shaded library**, cần thiết kế published POM và transitive dependency semantics đúng; không copy cấu hình này mù quáng.

### 5.5. Vì sao Assembly nằm trong profile `dist` và phase `verify`?

Mục tiêu cơ bản:

```bash
mvn clean verify
```

chỉ tạo executable shaded JAR và chạy tests. Khi cần một bundle cho người dùng:

```bash
mvn -Pdist clean verify
```

profile `dist` nạp Assembly Plugin; execution được bind vào `verify`, tức **sau phase `package` đã có JAR cuối**. Descriptor được cung cấp trong `src/assembly/distribution.xml`.

Trong Java reactor có nhiều modules, thứ tự và cách gom artifacts có thể phức tạp hơn. Ví dụ ở đây là **single-module** nên đường dẫn/tên output cụ thể và rõ ràng.

## 6. Resource được đưa vào JAR: `banner.properties`

Tạo:

`src/main/resources/messages/banner.properties`

```properties
app.name=Standalone Demo
app.greeting=hello outside ide
```

Maven Resources Plugin copy resource chính vào:

```text
target/classes/messages/banner.properties
```

JAR Plugin sau đó lấy từ main output directory, và Shade giữ resource này trong final JAR ở ZIP path:

```text
messages/banner.properties
```

**Không dùng** đường dẫn `src/main/resources/messages/banner.properties` khi ứng dụng đã chạy ở thư mục ngoài project, vì source directory không được phân phối. Code phải đọc resource **từ classpath**.

### 6.1. Đường dẫn classpath khác filesystem

```java
App.class.getResourceAsStream("/messages/banner.properties");
```

dấu `/` ban đầu nghĩa là tìm từ classpath root.

Trong khi:

```java
App.class.getResourceAsStream("messages/banner.properties");
```

tìm relative với package `org.example.standalone` của `App`, dẫn tới tên tài nguyên khác. Cần đọc đúng API vì một ký tự `/` có thể giải thích lỗi “resource ở trong JAR nhưng app báo missing”.

### 6.2. Không nhầm `src/main/resources` và `src/test/resources`

Nếu file nằm trong `src/test/resources`, JUnit test classpath có thể nhìn thấy nó, khiến tests PASS, nhưng final production JAR thường **không** chứa test resources. Trong phần chẩn đoán của bài, ta sẽ chủ động tái hiện và sửa lỗi này.

## 7. `App.java`: một chương trình độc lập hoàn chỉnh

File:

`src/main/java/org/example/standalone/App.java`

```java
package org.example.standalone;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Properties;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    private static Properties loadBanner() {
        Properties properties = new Properties();

        try (InputStream stream = App.class.getResourceAsStream(
                "/messages/banner.properties")) {
            if (stream == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: messages/banner.properties");
            }
            properties.load(new InputStreamReader(
                    stream, StandardCharsets.UTF_8));
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "Cannot read banner resource", exception);
        }

        return properties;
    }

    public static String render(String target) {
        Properties properties = loadBanner();

        String appName = properties.getProperty("app.name");
        String greeting = properties.getProperty("app.greeting");
        if (appName == null || greeting == null) {
            throw new IllegalStateException(
                    "Missing app.name or app.greeting");
        }

        String recipient = target == null || target.isBlank()
                ? "world"
                : target.strip();

        return appName + " | "
                + StringUtils.upperCase(greeting, Locale.ROOT)
                + " | " + recipient;
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            System.err.println(
                    "Usage: java -jar standalone-cli-1.0.0.jar [name]");
            System.exit(2);
            return;
        }

        String recipient = args.length == 0 ? null : args[0];
        System.out.println(render(recipient));
    }
}
```

### 7.1. Những chi tiết có chủ đích

- `public static void main(String[] args)` là Java entry point thông thường.
- `StringUtils.upperCase(...)` dùng **commons-lang3** làm runtime dependency thật, để tránh một demo thuần JDK không thể chứng minh Shade đã gom thư viện.
- `Locale.ROOT` tránh uppercasing phụ thuộc locale của người chạy.
- `Properties.load(Reader)` với `InputStreamReader(..., UTF_8)` chỉ rõ encoding của resource.
- `getResourceAsStream` đọc trực tiếp từ JAR được classloader nạp, không từ project source directory.
- `String.isBlank()` và `String.strip()` phù hợp Java 17.
- Nếu resource thiếu hoặc thiếu property, chương trình **fail rõ ràng**.
- Nếu có hơn một argument, main in usage ra **stderr**, exit code `2`, không tạo stdout thành công giả.

### 7.2. Output chính xác

```bash
java -jar target/standalone-cli-1.0.0.jar Maven
```

Stdout:

```text
Standalone Demo | HELLO OUTSIDE IDE | Maven
```

```bash
java -jar target/standalone-cli-1.0.0.jar
```

Stdout:

```text
Standalone Demo | HELLO OUTSIDE IDE | world
```

Nếu truyền một argument có khoảng trắng, đặt trong dấu nháy:

```bash
java -jar target/standalone-cli-1.0.0.jar "  Maven  "
```

Output vẫn là:

```text
Standalone Demo | HELLO OUTSIDE IDE | Maven
```

Lý do: `strip()` loại leading/trailing Unicode whitespace theo Java, nhưng không loại/ghép các khoảng trắng ở giữa chuỗi.

### 7.3. Lệnh với quá nhiều arguments

```bash
java -jar target/standalone-cli-1.0.0.jar A B
```

App báo usage ra stderr:

```text
Usage: java -jar standalone-cli-1.0.0.jar [name]
```

và process exit code `2`. Chi tiết cách shell/CI hiển thị stderr thay đổi, nhưng chính Java code in đúng dòng trên.

**Không biến mọi non-zero exit thành “Maven build lỗi”.** Lỗi xảy ra trong ứng dụng đã package, cần xem arguments/runtime.

## 8. JUnit 5 kiểm logic trước đóng gói

File:

`src/test/java/org/example/standalone/AppTest.java`

```java
package org.example.standalone;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void rendersDefaultRecipient() {
        assertEquals(
                "Standalone Demo | HELLO OUTSIDE IDE | world",
                App.render(null));
    }

    @Test
    void rendersNamedRecipient() {
        assertEquals(
                "Standalone Demo | HELLO OUTSIDE IDE | Maven",
                App.render(" Maven "));
    }

    @Test
    void treatsBlankRecipientAsDefault() {
        assertEquals(
                "Standalone Demo | HELLO OUTSIDE IDE | world",
                App.render("\t  "));
    }

    @Test
    void readsResourceAndUsesRuntimeLibrary() {
        String actual = App.render("CI");
        assertTrue(actual.startsWith(
                "Standalone Demo | HELLO OUTSIDE IDE"));
        assertEquals(
                "Standalone Demo | HELLO OUTSIDE IDE | CI",
                actual);
    }
}
```

JUnit Jupiter **5.11.4** có test scope. Maven Surefire Plugin **3.6.1** nhận diện test class theo convention `*Test`.

### 8.1. Chạy tests

```bash
mvn -B -ntp clean test
```

Dòng tóm tắt dự kiến:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **kết quả kỳ vọng** từ bốn test methods, không phải log đã chạy thật trên máy. Để chứng minh, xem exit code và:

```text
target/surefire-reports/TEST-org.example.standalone.AppTest.xml
```

### 8.2. Unit tests chưa đủ cho executable JAR

JUnit chạy với classpath do Surefire/Maven cung cấp, thường gồm:

```text
target/classes
target/test-classes
compile/test dependency JARs
```

Trong khi `java -jar` chạy **packaged archive** và không được Maven tự thêm mọi local dependency JAR. Vì vậy unit tests PASS **chưa chứng minh executable shaded JAR đã đủ runtime classes**.

Bước bắt buộc tiếp theo là **smoke-test trên chính file JAR**.

## 9. Build executable JAR

Từ root project:

```bash
java -version
javac -version
mvn -version
mvn -B -ntp clean verify
```

Yêu cầu: JDK 17+, Maven 3.9.x, approved repositories/mirror có đủ plugins/dependencies. `-B` bật batch mode, `-ntp` tắt transfer progress; chúng không đổi chất lượng artifact.

### 9.1. Output kỳ vọng

```text
target/
├── classes/
│   ├── org/example/standalone/App.class
│   └── messages/banner.properties
├── test-classes/
│   └── org/example/standalone/AppTest.class
├── surefire-reports/
│   └── TEST-org.example.standalone.AppTest.xml
└── standalone-cli-1.0.0.jar
```

Còn có thể có Maven metadata, generated files và **original/unshaded JAR backup** tùy Shade Plugin. Không khẳng định đây là danh sách đầy đủ mọi file trong `target`.

### 9.2. Kiểm không phải JAR rỗng

Trên Linux/macOS:

```bash
test -s target/standalone-cli-1.0.0.jar
```

Đây là điều kiện file tồn tại và có kích thước lớn hơn 0. Chỉ thế chưa đủ; một file `.jar` sai định dạng vẫn có thể non-empty.

Trên PowerShell:

```powershell
$jar = Get-Item -LiteralPath .\target\standalone-cli-1.0.0.jar
if ($jar.Length -le 0) {
    throw "JAR file is empty"
}
```

### 9.3. Kiểm archive ZIP hợp lệ

```bash
jar tf target/standalone-cli-1.0.0.jar
```

JAR dùng ZIP layout; `jar tf` liệt kê entry names. Nó có thể báo lỗi khi archive hỏng/truncated. Tuy nhiên **liệt kê được entries không tự chứng minh ứng dụng chạy đúng**.

## 10. Kiểm manifest, app class, resource và runtime library

Một shaded JAR hợp lệ của lab cần có ít nhất:

```text
META-INF/MANIFEST.MF
org/example/standalone/App.class
messages/banner.properties
org/apache/commons/lang3/StringUtils.class
```

### 10.1. `jar tf` trên Linux/macOS

```bash
jar tf target/standalone-cli-1.0.0.jar \
    | grep -Fx "org/example/standalone/App.class"

jar tf target/standalone-cli-1.0.0.jar \
    | grep -Fx "messages/banner.properties"

jar tf target/standalone-cli-1.0.0.jar \
    | grep -Fx "org/apache/commons/lang3/StringUtils.class"
```

Mỗi lệnh nên tìm đúng một entry path. `grep -Fx` so full line, tránh nhầm `StringUtils$...class`.

### 10.2. `Main-Class`

Manifest mong đợi có:

```text
Main-Class: org.example.standalone.App
```

Dùng `unzip -p` trên môi trường có `unzip`:

```bash
unzip -p target/standalone-cli-1.0.0.jar META-INF/MANIFEST.MF
```

Trên môi trường chỉ có JDK, dùng **Java JarFile audit tool** ở mục 11 để đọc manifest bằng API chuẩn thay vì phụ thuộc `unzip`.

**Không viết:**

```text
Main-Class: org/example/standalone/App.class
```

Đó là **ZIP entry path**, không phải tên class đầy đủ.

### 10.3. Có `StringUtils.class` không có nghĩa mọi dependencies đều đúng

Trong lab chỉ gọi `StringUtils.upperCase`, và Commons Lang class xuất hiện trong archive giúp chứng minh Shade đã gom runtime dependency này. Với framework thực, còn phải kiểm:

- Reflectively loaded classes và service providers.
- `META-INF/services`/framework descriptors.
- Native libraries và OS-specific dependencies.
- Conflicting dependency versions.
- Licenses/NOTICE.
- Vulnerability scanning và artifact provenance.

Nói cách khác, bài kiểm tra entry là **cần thiết nhưng không đủ**.

## 11. `audit/JarAudit.java`: công cụ kiểm final JAR độc lập với Maven

File `audit/JarAudit.java` không nằm trong Java application classpath. Nó dùng Java 17 **single-file source launcher**, chỉ cần JDK, không cần Maven hay Commons Lang ở bước audit.

```java
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class JarAudit {
    private JarAudit() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java audit/JarAudit.java PATH_TO_JAR");
        }

        Path path = Path.of(args[0]);
        try (JarFile jar = new JarFile(path.toFile())) {
            Manifest manifest = jar.getManifest();

            String mainClass = manifest == null
                    ? "(missing)"
                    : manifest.getMainAttributes().getValue(
                            Attributes.Name.MAIN_CLASS);

            boolean appClass = jar.getJarEntry(
                    "org/example/standalone/App.class") != null;

            boolean resource = jar.getJarEntry(
                    "messages/banner.properties") != null;

            boolean commonsClass = jar.getJarEntry(
                    "org/apache/commons/lang3/StringUtils.class") != null;

            boolean pass = "org.example.standalone.App".equals(
                    mainClass) && appClass && resource && commonsClass;

            System.out.println("main-class=" + mainClass);
            System.out.println("app-class=" + appClass);
            System.out.println("resource=" + resource);
            System.out.println("commons-class=" + commonsClass);
            System.out.println("audit=" + (pass ? "PASS" : "FAIL"));

            if (!pass) {
                System.exit(3);
            }
        }
    }
}
```

### 11.1. Chạy audit

```bash
java audit/JarAudit.java target/standalone-cli-1.0.0.jar
```

**Stdout chính xác khi file đúng POM/profile của lab:**

```text
main-class=org.example.standalone.App
app-class=true
resource=true
commons-class=true
audit=PASS
```

Exit code `0`.

Nếu `Main-Class` sai, resource/class vắng hoặc Shade chưa gom Commons Lang, tool in `audit=FAIL` và exit code `3`. Điều này tạo **gate kiểm cấu trúc JAR** trong CI.

### 11.2. Giới hạn của utility

`JarAudit`:

- Kiểm JAR hợp lệ để có thể mở bằng `JarFile`.
- Kiểm manifest và **bốn điều kiện về entries**.
- Không chạy app.
- Không xác minh chữ ký GPG/JAR signing.
- Không đánh giá source code có vulnerability.
- Không chứng minh mọi dependency classes cần cho reflection đều hiện diện.
- Không kiểm bộ config external hoặc OS permission của launcher.
- Không nhận `Main-Class` khác từ project thật; muốn dùng với project khác phải sửa expected contract.

Vì vậy phải kết hợp **smoke test thực sự**.

## 12. Smoke test `java -jar` ngay sau build

```bash
java -jar target/standalone-cli-1.0.0.jar Maven
```

Stdout:

```text
Standalone Demo | HELLO OUTSIDE IDE | Maven
```

Nếu chạy không arguments:

```bash
java -jar target/standalone-cli-1.0.0.jar
```

Stdout:

```text
Standalone Demo | HELLO OUTSIDE IDE | world
```

### 12.1. Một Bash script xác nhận tự động

Từ project root trên Linux/GitHub ubuntu runner:

```bash
set -euo pipefail

JAR="target/standalone-cli-1.0.0.jar"

test -s "$JAR"
java audit/JarAudit.java "$JAR"

ACTUAL="$(java -jar "$JAR" Maven)"
test "$ACTUAL" = "Standalone Demo | HELLO OUTSIDE IDE | Maven"

echo "executable JAR smoke test: PASS"
```

Khi mọi kiểm tra đạt, dòng cuối script in:

```text
executable JAR smoke test: PASS
```

Trước dòng này utility `JarAudit` cũng đã in năm dòng status. Không coi toàn bộ script chỉ có một dòng stdout.

`set -e` khiến script dừng khi utility/JAR trả non-zero, còn `test` so chuỗi chính xác. Nếu một `java` command fail trong command substitution, behavior của shell cần kiểm kỹ; trong script này `test` trên output không khớp cũng fail, nhưng production CI nên kiểm **exit code** trực tiếp hoặc dùng cấu trúc `if ! ...` để tránh phụ thuộc shell.

### 12.2. PowerShell kiểm cả exit code lẫn stdout

```powershell
$jar = ".\target\standalone-cli-1.0.0.jar"

if (-not (Test-Path -LiteralPath $jar)) {
    throw "Missing JAR"
}

& java audit/JarAudit.java $jar
if ($LASTEXITCODE -ne 0) {
    throw "Archive audit failed"
}

$output = @(& java -jar $jar Maven)
if ($LASTEXITCODE -ne 0) {
    throw "Executable JAR failed"
}

if ($output.Count -ne 1 -or
    $output[0] -ne "Standalone Demo | HELLO OUTSIDE IDE | Maven") {
    throw "Unexpected stdout"
}

Write-Output "executable JAR smoke test: PASS"
```

Cách này phù hợp **PowerShell 5.1/7** với JDK 17+ trong `PATH`. `JarAudit` yêu cầu JDK compiler cho Java source-file mode; runtime standalone JAR về sau chỉ cần Java runtime 17+.

## 13. Bài kiểm tra quan trọng nhất: chạy ở ngoài IDE và ngoài project

Nếu chỉ chạy từ project root, app có thể vô tình đọc file nguồn, config, relative paths hoặc local libraries. Vì vậy cần tạo **thư mục tạm không nằm trong checkout** rồi copy **chính executable JAR** vào đó.

### 13.1. Linux/macOS: temporary directory

Từ root project, dùng Bash/sh có `mktemp`:

```bash
JAR_SOURCE="$PWD/target/standalone-cli-1.0.0.jar"
OUTSIDE_DIR="$(mktemp -d)"

cp "$JAR_SOURCE" "$OUTSIDE_DIR/"

(
  cd "$OUTSIDE_DIR"
  java -jar standalone-cli-1.0.0.jar Maven
)
```

**Stdout chính xác** từ app:

```text
Standalone Demo | HELLO OUTSIDE IDE | Maven
```

Không có `pom.xml`, `src/`, `target/classes` hay `.m2` được copy tới thư mục tạm. `java -jar` **không gọi Maven**, nên việc app chạy ở đây chứng minh Maven local dependency cache **không cần ở runtime cho ví dụ này**.

### 13.2. Windows PowerShell: temporary directory

```powershell
$source = (Resolve-Path -LiteralPath `
    .\target\standalone-cli-1.0.0.jar).Path

$outside = Join-Path $env:TEMP (
    "standalone-smoke-" + [guid]::NewGuid().ToString("N"))

New-Item -ItemType Directory -Path $outside | Out-Null

Copy-Item -LiteralPath $source -Destination (
    Join-Path $outside "standalone-cli-1.0.0.jar")

Push-Location $outside
try {
    & java -jar .\standalone-cli-1.0.0.jar Maven
    if ($LASTEXITCODE -ne 0) {
        throw "java -jar failed"
    }
} finally {
    Pop-Location
}
```

Stdout ứng dụng giống ví dụ Unix. Lệnh giữ thư mục tạm để bạn có thể điều tra file đã bàn giao; khi dọn, **xác minh đúng path vừa tạo** trước khi xóa để không ảnh hưởng dữ liệu khác.

### 13.3. Điều bài kiểm tra này chứng minh và không chứng minh

Nó chứng minh trong điều kiện thử:

- Main class được launcher nạp.
- Java 17 runtime có thể chạy app.
- Dependency class `StringUtils` được cung cấp bởi final JAR.
- Resource `messages/banner.properties` được tìm qua classpath.
- App không cần current working directory là project source.
- JAR không cần Maven khi khởi động.

Nó **không** chứng minh chạy trên mọi OS/JDK version/CPU architecture, không phát hiện mọi lỗi production runtime, không chứng minh container/installer config đúng, cũng không thay security scanning.

Một Java app thuần bytecode có tính portable cao, nhưng native JNI, font, timezone, locale, filesystem behavior, `ProcessBuilder` và external services vẫn có thể gây khác biệt.

## 14. Thực hành tùy chọn: đóng gói ZIP distribution

Một JAR duy nhất có thể đủ cho CI hoặc máy đã có Java runtime. Nhưng khi bàn giao cho người dùng cuối, một gói ZIP có cấu trúc rõ và launcher có thể thuận tiện hơn.

Trong POM mục 5 đã có profile:

```bash
mvn -B -ntp -Pdist clean verify
```

Để profile tạo ZIP đúng, thêm ba file:

```text
src/assembly/distribution.xml
scripts/run.sh
scripts/run.cmd
```

### 14.1. Assembly descriptor đầy đủ

`src/assembly/distribution.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0
                              https://maven.apache.org/xsd/assembly-2.2.0.xsd">
    <id>dist</id>
    <formats>
        <format>zip</format>
    </formats>
    <includeBaseDirectory>false</includeBaseDirectory>

    <fileSets>
        <fileSet>
            <directory>${project.build.directory}</directory>
            <outputDirectory>app</outputDirectory>
            <includes>
                <include>${project.build.finalName}.jar</include>
            </includes>
        </fileSet>
        <fileSet>
            <directory>${project.basedir}/scripts</directory>
            <outputDirectory>bin</outputDirectory>
            <includes>
                <include>run.sh</include>
            </includes>
            <fileMode>0755</fileMode>
        </fileSet>
        <fileSet>
            <directory>${project.basedir}/scripts</directory>
            <outputDirectory>bin</outputDirectory>
            <includes>
                <include>run.cmd</include>
            </includes>
        </fileSet>
    </fileSets>
</assembly>
```

**Giải thích:**

- `<id>dist</id>` trở thành assembly ID/classifier; output file dự kiến `target/standalone-cli-1.0.0-dist.zip`.
- `<formats><format>zip</format></formats>` sinh ZIP.
- `<includeBaseDirectory>false</includeBaseDirectory>` để ZIP root có `app/`, `bin/`.
- File JAR được lấy từ `${project.build.directory}` **sau khi Shade chạy ở `package`**.
- `<include>${project.build.finalName}.jar</include>` chọn main artifact có tên cố định từ POM hiện tại, không copy mọi `*.jar` (tránh nhầm `original-*`).
- `fileMode 0755` thể hiện quyền Unix executable cho launcher shell nếu công cụ giải nén/platform giữ mode; vẫn có thể dùng `sh run.sh` nếu execute bit không được bảo toàn.
- Không có secrets, `~/.m2/repository`, test classes hoặc source Java trong ZIP.

**Ranh giới quan trọng:** descriptor là một file XML riêng, **không nhúng nội dung này vào `<pom.xml>`**.

### 14.2. Linux/macOS launcher — `scripts/run.sh`

```sh
#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)

exec java -jar "$SCRIPT_DIR/../app/standalone-cli-1.0.0.jar" "$@"
```

Giải thích:

- `SCRIPT_DIR` tính theo **thư mục script**, không theo current working directory của user.
- Đường dẫn JAR được quote để hỗ trợ các thư mục có khoảng trắng.
- `"$@"` giữ đúng ranh giới arguments của shell.
- `exec` thay shell bằng Java process, hữu ích để forward exit code và Unix signals.
- Cần Java 17+ trong `PATH`. Script không cài Java.

**Không** dùng `java -jar app.jar` tương đối với `PWD` vì user có thể chạy script từ một thư mục hoàn toàn khác.

### 14.3. Windows launcher — `scripts/run.cmd`

```bat
@echo off
set "SCRIPT_DIR=%~dp0"
java -jar "%SCRIPT_DIR%..\app\standalone-cli-1.0.0.jar" %*
exit /b %ERRORLEVEL%
```

`%~dp0` là đường dẫn thư mục chứa `.cmd`, giúp tìm JAR đúng ngay cả khi chạy từ working directory khác. `%*` forward các command-line arguments theo ngữ nghĩa `cmd.exe`; với tên có khoảng trắng, người dùng nên quote argument lúc gọi script.

Đây là **Windows CMD script**, không phải PowerShell script. Script yêu cầu `java` có trong `PATH`; nếu không, lỗi hệ điều hành sẽ nói Java command không tìm được.

### 14.4. Build ZIP

```bash
mvn -B -ntp -Pdist clean verify
```

Khi profile và descriptor hợp lệ, các outputs mong đợi:

```text
target/standalone-cli-1.0.0.jar
target/standalone-cli-1.0.0-dist.zip
target/surefire-reports/TEST-org.example.standalone.AppTest.xml
```

Với descriptor trên, bên trong ZIP sẽ có các entries tương tự:

```text
app/standalone-cli-1.0.0.jar
bin/run.sh
bin/run.cmd
```

Archive có thể chứa directory entries `app/`, `bin/` riêng. Không cần xem những entries directory này là lỗi.

### 14.5. Tại sao không dùng Assembly `jar-with-dependencies` trong lab?

Maven Assembly Plugin có descriptor `jar-with-dependencies` có thể tạo uber-JAR cơ bản. Nhưng bài dùng **Shade Plugin cho executable JAR** vì có `ManifestResourceTransformer`, service resource mergers, relocation/filter controls, và có thể chọn main shaded artifact rõ.

Assembly Plugin được sử dụng **đúng nhiệm vụ của nó** ở đây: làm ZIP distribution từ binary final và launch scripts. Không cần hai plugins cùng tạo hai uber-JAR khác nhau rồi nhầm file triển khai.

## 15. Chạy ZIP distribution sau khi giải nén ở thư mục khác

### 15.1. Linux có `unzip`

Từ project root:

```bash
DIST_ZIP="$PWD/target/standalone-cli-1.0.0-dist.zip"
DIST_DIR="$(mktemp -d)"

unzip -q "$DIST_ZIP" -d "$DIST_DIR"
sh "$DIST_DIR/bin/run.sh" Maven
```

**Stdout từ ứng dụng**:

```text
Standalone Demo | HELLO OUTSIDE IDE | Maven
```

Bạn có thể `cd /tmp` hoặc một thư mục bất kỳ rồi gọi script bằng absolute path như trên. Vì script dùng vị trí của chính nó, hoạt động không phụ thuộc project root.

### 15.2. macOS

`unzip` thường có sẵn trong nhiều môi trường; nếu hệ thống thiếu, dùng công cụ ZIP khác. `mktemp -d` hỗ trợ trên các Unix-like platforms nhưng cú pháp/behavior có thể khác theo OS, cần thử trên host thực.

Nếu bạn không có quyền chạy trực tiếp `run.sh` do execute bit bị mất, vẫn có thể dùng:

```bash
sh /path/to/extracted/bin/run.sh Maven
```

Thay `/path/to/extracted` bằng path thực. Không cần sửa project POM để giải quyết Unix permission đơn thuần do công cụ giải nén.

### 15.3. Windows PowerShell

```powershell
$zip = (Resolve-Path -LiteralPath `
    .\target\standalone-cli-1.0.0-dist.zip).Path

$outside = Join-Path $env:TEMP (
    "standalone-dist-" + [guid]::NewGuid().ToString("N"))

Expand-Archive -LiteralPath $zip -DestinationPath $outside

Push-Location $env:TEMP
try {
    & (Join-Path $outside "bin\run.cmd") Maven
    if ($LASTEXITCODE -ne 0) {
        throw "Windows distribution launcher failed"
    }
} finally {
    Pop-Location
}
```

Lưu ý `run.cmd` nhận argument `Maven`. Lệnh deliberately đổi `PWD` sang `%TEMP%` để chứng minh launcher không phụ thuộc directory chứa POM hoặc location hiện tại. Nếu java runtime không có trong `PATH`, launcher fail rõ thay vì tìm Maven cache.

### 15.4. Đối chiếu JAR bên trong ZIP với JAR đã QA

Không chỉ kiểm script chạy. Nếu pipeline đóng ZIP **sau** thời điểm QA rồi chèn nhầm JAR, có thể chuyển một binary khác.

Sau khi giải nén trên Linux:

```bash
sha256sum target/standalone-cli-1.0.0.jar
sha256sum "$DIST_DIR/app/standalone-cli-1.0.0.jar"
```

Hai dòng có thể có **đường dẫn khác nhau**; so **64 ký tự hex digest**, không so toàn bộ text output chứa filename.

Trong PowerShell:

```powershell
$a = (Get-FileHash -Algorithm SHA256 `
    .\target\standalone-cli-1.0.0.jar).Hash

$b = (Get-FileHash -Algorithm SHA256 (
    Join-Path $outside "app\standalone-cli-1.0.0.jar")).Hash

if ($a -ne $b) {
    throw "ZIP contains a different JAR"
}
```

**Không điền một checksum “mẫu” vào tài liệu rồi xem là hash thật.** Hash của final bytes phải được tính trên artifact của chính CI run.

## 16. Kiểm tra Maven dependencies và packaging scopes

Maven dependency có scope khác nhau:

| Scope | Compile classpath | Runtime classpath | Phù hợp |
| --- | --- | --- | --- |
| `compile` | Có | Có | Commons Lang do app gọi trực tiếp |
| `runtime` | Không dùng để compile source trực tiếp | Có | JDBC driver được load động |
| `provided` | Có | Không trong Maven runtime scope chuẩn | API do container/JDK cung cấp |
| `test` | Test compile/runtime | Không cho main runtime | JUnit Jupiter |
| `system` | Phụ thuộc local file path | Không portable | Nên tránh cho CI/deploy |

POM mẫu dùng:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Không khai báo `scope`, nên mặc định là `compile` và được Shade Plugin xem là runtime dependency hợp lệ. JUnit có `test` scope; không cần copy JUnit engine vào application JAR.

### 16.1. Xem resolved dependency tree

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Kiểm tra Commons Lang 3.14.0 và JUnit test dependencies được Maven resolve từ approved repositories. Cây hiển thị **Maven model dependencies**; để chắc chắn JAR final có class thật, vẫn phải chạy `JarAudit`.

### 16.2. Vì sao `mvn install` không cần cho lab?

`mvn install` đưa artifact vào **local Maven repository** của máy build. Bài test outside IDE chỉ dùng:

```bash
java -jar standalone-cli-1.0.0.jar
```

trên JAR đã copy, nên không dựa vào local repo. Nếu JAR chỉ chạy được khi bạn đã `mvn install` một thư viện nội bộ, phải điều tra vì distribution chưa đủ runtime dependencies hoặc classpath đang phụ thuộc môi trường phát triển.

### 16.3. `provided` là lỗi phổ biến khi đóng ứng dụng standalone

Nếu biến Commons Lang thành:

```xml
<scope>provided</scope>
```

thì app vẫn compile được trong Maven nhưng runtime packaging không xem đó là dependency được cung cấp trong standalone context. Lúc chạy `java -jar`, `StringUtils` có thể vắng mặt và gây `NoClassDefFoundError`.

**Không sử dụng `provided` với thư viện cần ngay lúc khởi động một Java JAR chạy độc lập**, trừ khi runtime environment thực sự cung cấp thư viện theo contract.

## 17. Phân biệt ba lỗi chạy ngoài IDE thường gặp

### 17.1. `no main manifest attribute`

Triệu chứng:

```text
no main manifest attribute, in standalone-cli-1.0.0.jar
```

Khả năng: JAR thiếu `Main-Class`; Maven JAR Plugin/Shade Manifest transformer chưa chạy hoặc đang chọn nhầm original JAR.

Cách kiểm:

```bash
java audit/JarAudit.java target/standalone-cli-1.0.0.jar
```

Nếu `main-class=null` hoặc `(missing)`, xem `maven-shade-plugin` execution ở `package`, transformer và archive thực sự được bàn giao.

Trong code của `JarAudit`, nếu JAR có manifest nhưng **không có `Main-Class`**, Java `Manifest.getMainAttributes().getValue(...)` trả `null` và chương trình in `main-class=null` (string nối `null` theo Java). Nếu manifest không có, in `(missing)`.

### 17.2. `Could not find or load main class`

Có `Main-Class` nhưng class entry tương ứng không nằm trong archive hoặc runtime classpath không tải được. Kiểm:

```text
Main-Class: org.example.standalone.App
JAR entry:  org/example/standalone/App.class
```

**Không** viết manifest theo ZIP path `org/example/standalone/App.class`. Java cần fully qualified class name với dấu chấm.

Nếu class có trong `target/classes` nhưng không vào JAR, kiểm `maven-jar-plugin` includes/excludes, target artifact và phase. Nếu source ở sai root, Compiler Plugin có thể không tạo class.

### 17.3. `NoClassDefFoundError: StringUtils`

Ví dụ:

```text
java.lang.NoClassDefFoundError:
    org/apache/commons/lang3/StringUtils
```

Điều này thường chỉ ra runtime classpath/packaging thiếu Commons Lang. Kiểm:

```text
org/apache/commons/lang3/StringUtils.class
```

trong JAR. Nếu không có nhưng đang dùng thin JAR, cần thêm runtime library bằng `-cp`/manifest `Class-Path` hoặc tạo executable shaded JAR đúng. Nếu Shade được cấu hình nhưng vẫn thiếu, kiểm artifact selection, exclusions, scope và plugin execution.

### 17.4. Resource missing

App cố đọc:

```text
/messages/banner.properties
```

từ classpath, nếu không có sẽ báo:

```text
java.lang.IllegalStateException:
    Missing classpath resource: messages/banner.properties
```

Trong full stack trace, các line numbers/frames khác nhau; đoạn trên chỉ minh họa exception class/message.

Kiểm source:

```text
src/main/resources/messages/banner.properties
```

rồi output:

```text
target/classes/messages/banner.properties
```

và archive:

```text
messages/banner.properties
```

**Không đổi code thành `new FileInputStream("src/main/resources/...")` để chữa**, vì file source thường không có ở máy chạy độc lập.

## 18. Một thí nghiệm lỗi thực tế: unit test PASS, JAR resource FAIL

Để hiểu test/runtime classpath khác nhau, làm trên **bản copy lab**:

### 18.1. Chuyển resource sang test source root

Trên Unix:

```bash
mkdir -p src/test/resources/messages

mv src/main/resources/messages/banner.properties \
    src/test/resources/messages/banner.properties

mvn -B -ntp clean verify
```

Với Surefire test classpath, JUnit có thể tìm resource `messages/banner.properties` dưới `target/test-classes` nên **bốn tests vẫn PASS**. Nhưng executable JAR được đóng từ `target/classes` và runtime dependencies, không tự lấy test resources.

Chạy:

```bash
java audit/JarAudit.java target/standalone-cli-1.0.0.jar
```

Dòng tương ứng:

```text
resource=false
audit=FAIL
```

`JarAudit` exit code `3`. Chạy app sẽ báo thiếu classpath resource. Đây là tình huống chứng minh **unit tests xanh chưa chứng minh archive đầy đủ**.

### 18.2. Khôi phục

```bash
mv src/test/resources/messages/banner.properties \
    src/main/resources/messages/banner.properties

mvn -B -ntp clean verify
java audit/JarAudit.java target/standalone-cli-1.0.0.jar
```

Kết quả quay lại `resource=true`, `audit=PASS`.

**Vì sao dùng `clean`?** Nếu giữ `target/classes/messages/banner.properties` từ build trước rồi chỉ chạy `package`, resource cũ **có thể còn lại**, che lỗi. Clean tạo output từ source hiện tại, giúp test đáng tin hơn.

### 18.3. Windows PowerShell tương đương

```powershell
New-Item -ItemType Directory -Force `
    .\src\test\resources\messages | Out-Null

Move-Item -LiteralPath `
    .\src\main\resources\messages\banner.properties `
    -Destination .\src\test\resources\messages\

mvn -B -ntp clean verify
```

Để khôi phục:

```powershell
Move-Item -LiteralPath `
    .\src\test\resources\messages\banner.properties `
    -Destination .\src\main\resources\messages\

mvn -B -ntp clean verify
```

Các thao tác trên làm thay đổi source tree; chỉ dùng trong lab/bản sao có kiểm soát, không chạy bừa trên repo production.

## 19. Thí nghiệm lỗi khác: cố chạy thin JAR thay shaded JAR

Một POM không có Shade Plugin có thể tạo thin JAR vẫn có:

```text
Main-Class: org.example.standalone.App
org/example/standalone/App.class
messages/banner.properties
```

nhưng **không** có:

```text
org/apache/commons/lang3/StringUtils.class
```

Vì application gọi Commons Lang, chạy `java -jar thin.jar` có thể báo `NoClassDefFoundError`.

**Không chạy nhầm bản `original-*` được Shade giữ để debug.** Tên backup khác nhau theo Shade config; hãy inspect JAR chính bằng `JarAudit` thay vì chọn theo wildcard.

### 19.1. Nếu muốn phân phối thin JAR hợp lệ

Đây là **phương án thay thế**, không phải cách chạy của lab Shade:

```text
dist/
├── app.jar
└── lib/
    └── commons-lang3-3.14.0.jar
```

Linux/macOS:

```bash
java -cp "dist/app.jar:dist/lib/*" org.example.standalone.App Maven
```

Windows:

```powershell
java -cp "dist\app.jar;dist\lib\*" org.example.standalone.App Maven
```

Có thể dùng Maven Dependency Plugin `copy-dependencies` ở runtime scope để tạo `lib/`; cần đảm bảo không có nhiều versions, và mọi transitive dependencies được copy theo graph thực.

Đây là standalone **distribution gồm nhiều files**, chứ không phải một executable JAR tự chứa dependencies. Nếu dùng `java -jar` thay cho `java -cp`, cần manifest `Class-Path` đúng relative runtime layout; không đặt absolute path tới `~/.m2`.

### 19.2. Vì sao không copy toàn bộ `.m2`?

`~/.m2/repository` chứa plugin JARs, test libraries, nhiều versions, metadata và artifacts không liên quan. Copy toàn bộ vào distribution làm tăng rủi ro dependency conflict và lộ private metadata.

**Chỉ bàn giao resolved runtime dependencies được duyệt**, hoặc tạo một shaded executable JAR như lab.

## 20. Kiểm tra artifact byte-for-byte khi bàn giao

### 20.1. Tính SHA-256 sau package

Trên Linux:

```bash
sha256sum target/standalone-cli-1.0.0.jar
```

Trên macOS:

```bash
shasum -a 256 target/standalone-cli-1.0.0.jar
```

Trên Windows:

```powershell
Get-FileHash -Algorithm SHA256 `
    .\target\standalone-cli-1.0.0.jar
```

**Không có một digest cố định đúng cho mọi máy**: JDK, plugin versions, entries, timestamp, metadata và environment có thể ảnh hưởng bytes.

### 20.2. Tạo checksum record đi cùng file

Với GNU coreutils trong Bash:

```bash
(
  cd target
  sha256sum standalone-cli-1.0.0.jar \
      > standalone-cli-1.0.0.jar.sha256
)
```

Để verify sau khi copy file lẫn checksum sang một thư mục khác:

```bash
cd /path/to/downloaded/files
sha256sum -c standalone-cli-1.0.0.jar.sha256
```

Output thường:

```text
standalone-cli-1.0.0.jar: OK
```

`sha256sum -c` trả non-zero nếu bytes không khớp. Đảm bảo file `.sha256` thật sự gắn với **đúng JAR đã QA của cùng build run**, không dùng hash ở máy dev hoặc run cũ.

### 20.3. Checksum không thay chữ ký/provenance

Một attacker sửa được cả JAR và `.sha256` có thể tạo cặp tương thích. Với release quan trọng, cần expected digest lấy từ trusted CI evidence/signature/attestation, source commit, approved build environment và quản lý quyền publish.

Chữ ký cho shaded/JAR/ZIP phải tạo **sau mọi bước thay đổi artifact**, không ký JAR rồi repack nó sau đó và giả định signature vẫn hợp lệ.

### 20.4. ZIP có digest riêng

Nếu publish cả:

```text
standalone-cli-1.0.0.jar
standalone-cli-1.0.0-dist.zip
```

thì **hai files có SHA-256 khác nhau**. Giữ digest riêng cho ZIP và JAR. Hash của ZIP phản ánh toàn bộ bundle/metadata; hash của JAR phản ánh application binary bên trong.

CI consumer cần biết phải verify **artifact nào** theo contract: packaged ZIP, final JAR, hoặc cả hai.

## 21. CI workflow đề xuất: hai gates thay vì một dòng `mvn verify`

Tối thiểu có hai lớp:

1. **Build gate:** Maven compilation + JUnit tests + shade/assembly đã hoàn tất.
2. **Package gate:** kiểm **final artifact** sau build, chạy ngoài IDE/project, verify bytes, rồi mới upload/bàn giao.

### 21.1. Bash workflow logic độc lập CI provider

```bash
set -euo pipefail

mvn -B -ntp clean verify

JAR="target/standalone-cli-1.0.0.jar"
test -s "$JAR"

java audit/JarAudit.java "$JAR"

APP_OUTPUT="$(java -jar "$JAR" Maven)"
test "$APP_OUTPUT" = "Standalone Demo | HELLO OUTSIDE IDE | Maven"

sha256sum "$JAR"

echo "package gate: PASS"
```

Dòng `package gate: PASS` chỉ được in sau khi các checks trả success. CI thật còn cần capture test report và artifact location/ID.

### 21.2. Handoff giữa hai CI jobs

Mô hình:

```text
JOB A (trusted build)
  checkout exact commit
  setup JDK 17 + Maven3.9
  resolve approved dependencies
  mvn clean verify / optional -Pdist
  JUnit tests
  JarAudit + smoke test
  final JAR/ZIP digest + provenance
  upload artifact

JOB B (consumer, workspace khác)
  download artifact từ chính run A
  so SHA-256 với trusted expected value
  kiểm archive contents nếu cần
  java -jar JAR hoặc giải nén ZIP rồi chạy launcher
  deploy/promote exact approved bytes
```

**Không** để job B chạy `mvn package` lại để tạo JAR khác rồi nói đã triển khai JAR từ job A. Phải promote **chính file đã QA**, hoặc chứng minh digest equality khi rebuild bắt buộc.

### 21.3. GitHub Actions ví dụ hai jobs

Một ví dụ phù hợp với repository chứa đầy đủ files ở bài:

`.github/workflows/standalone-java.yml`

```yaml
name: Standalone Java 17 build

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: JDK 17 with Maven dependency cache
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build, test, and bundle
        run: mvn -B -ntp -Pdist clean verify

      - name: Verify packaged JAR
        run: |
          set -euo pipefail
          java audit/JarAudit.java target/standalone-cli-1.0.0.jar
          ACTUAL="$(java -jar target/standalone-cli-1.0.0.jar Maven)"
          test "$ACTUAL" = "Standalone Demo | HELLO OUTSIDE IDE | Maven"

      - name: Prepare artifact bundle
        run: |
          mkdir -p handoff
          cp target/standalone-cli-1.0.0.jar handoff/
          cp target/standalone-cli-1.0.0-dist.zip handoff/
          cp target/surefire-reports/TEST-org.example.standalone.AppTest.xml handoff/
          (cd handoff && sha256sum standalone-cli-1.0.0.jar > standalone-cli-1.0.0.jar.sha256)

      - name: Upload tested outputs
        uses: actions/upload-artifact@v4
        with:
          name: standalone-java-${{ github.run_id }}
          path: handoff/
          if-no-files-found: error
          retention-days: 14

  inspect:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: JDK 17 runtime for inspection
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Download artifact from same run
        uses: actions/download-artifact@v4
        with:
          name: standalone-java-${{ github.run_id }}
          path: handoff/

      - name: Verify handoff and execute
        run: |
          set -euo pipefail
          cd handoff
          sha256sum -c standalone-cli-1.0.0.jar.sha256
          ACTUAL="$(java -jar standalone-cli-1.0.0.jar Maven)"
          test "$ACTUAL" = "Standalone Demo | HELLO OUTSIDE IDE | Maven"
```

Giải thích:

- `cache: maven` chỉ cache **dependencies/plugins**, không thay artifact output.
- `upload-artifact` lưu đúng JAR, ZIP và JUnit XML của run hiện tại.
- `download-artifact` lấy từ cùng workflow run theo ID.
- `if-no-files-found: error` làm fail khi đường dẫn upload sai.
- Job `inspect` **không checkout source và không chạy Maven**; chỉ cần Java 17 để execute final JAR.
- `retention-days: 14` là số ngày **minh họa**, phụ thuộc repository/org retention limit và không phải kho release vĩnh viễn.
- Với production, pin GitHub Actions theo verified commit SHA, bảo vệ branches/environments và lưu trusted digest/provenance riêng khi cần chống tamper.

### 21.4. Lỗ hổng QA cần tránh trong ví dụ CI

Step `Prepare artifact bundle` mới chỉ tạo checksum cho JAR, **chưa tạo checksum riêng cho ZIP**. Nếu ZIP là chính artifact triển khai, bổ sung kiểm ZIP digest và kiểm rằng JAR bên trong ZIP khớp binary đã QA. Một artifact bundle ZIP có thể chứa JAR sai nếu packaging descriptor lỗi.

Một cải tiến:

```bash
(
  cd handoff
  sha256sum standalone-cli-1.0.0-dist.zip \
      > standalone-cli-1.0.0-dist.zip.sha256
)
```

Và ở consumer:

```bash
sha256sum -c standalone-cli-1.0.0-dist.zip.sha256
```

Đồng thời giải nén ZIP và chạy `bin/run.sh`/`run.cmd` trong môi trường ngoài checkout như các mục 15.1–15.3.

## 22. Những thứ không được “vô tình” quyết định khi chạy ngoài IDE

### 22.1. Current working directory

App đúng trong lab đọc resource bằng classpath nên không phụ thuộc `PWD`. Nhưng project thực có thể đọc:

```java
Path.of("config/app.properties");
```

đó là **filesystem path relative với working directory**, không phải resource trong JAR. Nếu cần external config, phải thiết kế command line `--config` hoặc env var, quy định default và kiểm lỗi rõ ràng.

Đừng âm thầm dựa vào IDE “Working directory = project root”.

### 22.2. Runtime Java version

Project compile `release 17` nên máy chạy phải có **Java runtime tương thích với classfile Java 17**. Nếu dùng Java 11:

```text
UnsupportedClassVersionError
```

có thể xuất hiện. Kiểm:

```bash
java -version
```

và nếu cần xem classfile:

```bash
javap -verbose -classpath standalone-cli-1.0.0.jar \
    org.example.standalone.App
```

Trên JDK17, classfile major version tương ứng **61**. Nhưng vì app còn có Commons Lang classes, phải kiểm cả dependency compatibility khi chọn JVM cũ hoặc dùng API đặc thù.

### 22.3. Console encoding/locale/timezone

Lab dùng ASCII cho output nên dễ kiểm. Với tiếng Việt, cần UTF-8 ở source/resources/terminal, kiểm `file.encoding`, logging encoding, locale và CI shell output. `project.build.sourceEncoding` điều khiển source/resources khi plugin hỗ trợ, **không thể cưỡng chế mọi terminal hiển thị Unicode đúng**.

### 22.4. `JAVA_HOME` và `PATH`

Maven có thể chạy bằng JDK A trong IDE, trong khi `java` ở terminal dùng JDK B. Kiểm:

```bash
mvn -version
java -version
```

Nếu deployment chỉ cài JRE/runtime image không có Maven, `java -jar` vẫn đúng, nhưng tool `JarAudit.java` (source file launcher) yêu cầu JDK để compile trực tiếp. Không đưa audit tool như một runtime dependency bắt buộc cho người dùng cuối.

### 22.5. JVM flags đứng ở đâu?

Đúng:

```bash
java -Xmx256m -jar standalone-cli-1.0.0.jar Maven
```

Với cú pháp `java -jar file.jar args`, các tokens **sau JAR filename** được truyền vào `String[] args` của app; nếu đặt `-Xmx256m` sau filename:

```bash
java -jar standalone-cli-1.0.0.jar -Xmx256m
```

nó là **argument cho chương trình**, không còn là heap flag JVM. Với app mẫu có một optional argument, chương trình sẽ in tên người nhận `-Xmx256m` thay vì đặt heap limit. Vì vậy scripts phải đặt JVM flags trước `-jar`.

### 22.6. Đường dẫn có khoảng trắng

Script dùng:

```sh
java -jar "$SCRIPT_DIR/../app/standalone-cli-1.0.0.jar" "$@"
```

thay vì:

```sh
java -jar $SCRIPT_DIR/../app/standalone-cli-1.0.0.jar $@
```

Đường dẫn không quote có thể bị shell tách thành nhiều arguments khi ZIP được giải nén dưới thư mục chứa spaces.

### 22.7. External services, filesystem permissions và credentials

Một ứng dụng cần database, API server, external config hoặc certificate store sẽ không trở nên độc lập về **môi trường** chỉ vì là fat JAR. Lab purposely không có dịch vụ bên ngoài để kiểm tra đúng trọng tâm packaging, rồi người học có thể mở rộng smoke test cho deployment dependencies thực tế.

## 23. Reproducibility, release và bảo mật

### 23.1. Pin dependencies/plugins và build clean

POM ghim Commons Lang, JUnit, Compiler, Shade, Jar và Assembly versions; nên build từ source commit đã review với Maven/JDK version kiểm soát. `mvn clean verify` tránh mang theo stale `target/classes` hoặc JAR từ run trước.

`project.build.outputTimestamp` hỗ trợ reproducible ZIP/JAR entry timestamps khi plugins/archivers tôn trọng property; **không đủ để đảm bảo byte-identical builds** nếu code generation, input snapshots, OS paths, ZIP ordering hoặc toolchains khác.

### 23.2. SHA-256 là integrity check, không phải malware scan

SHA-256 xác nhận bytes so với expected digest. Nó không chứng minh artifact được xây từ approved source hoặc không có lỗ hổng. Kết hợp:

```text
Git source commit
    -> trusted CI run
    -> JUnit and packaged-app smoke tests
    -> final JAR/ZIP SHA-256
    -> optional signature/provenance/SBOM
    -> approved artifact store
```

### 23.3. Scan dependency và giấy phép

Một fat JAR có code từ third-party dependencies. Trước phát hành cần tuân license, NOTICE/attribution và vulnerability policy. Shade có thể gộp/đổi archive entries; kiểm lại `META-INF/LICENSE`, `NOTICE`, service descriptors và POM provenance.

### 23.4. Ký sau khi shading/assembly

Ký input JAR rồi shade có thể làm signature metadata không còn khớp final bytes. Nếu tổ chức ký artifact, **ký final artifact** theo quy trình phù hợp; với ZIP và JAR lưu đúng digests/signatures cho từng file.

### 23.5. Không đóng production credentials vào JAR/ZIP

Không đưa:

```text
settings.xml chứa server token
private signing key
.env thực của production
application-prod.properties có password
CI secret dump
```

vào resources hoặc ZIP fileSet. Chỉ bundle **public defaults và code**; external secrets được cung cấp bởi deployment platform.

### 23.6. Tránh upload quá rộng

Một wildcard như:

```text
target/*.jar
```

có thể lấy cả original/shaded/classifier JAR. Trong lab, chọn:

```text
target/standalone-cli-1.0.0.jar
```

và nếu dùng ZIP:

```text
target/standalone-cli-1.0.0-dist.zip
```

Kiểm file tồn tại, size, entries và digest. Không upload toàn bộ Maven local repository hoặc `target/` vô điều kiện.

## 24. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| IDE chạy được, `java -jar` lỗi | IDE classpath có dependencies, JAR không | Shade/manifest/runtime libs |
| `no main manifest attribute` | Thiếu `Main-Class` | ManifestResourceTransformer/Jar Plugin config |
| `Could not find or load main class` | FQCN sai hoặc App.class không có | `jar tf`, `JarAudit`, package/source root |
| `NoClassDefFoundError: StringUtils` | Commons Lang không nằm trong runtime JAR/lib | Xem Shade execution/scope/artifact selection |
| `ClassNotFoundException` từ reflection | Dependency loaded dynamically không thấy | Runtime graph/classloader/config |
| `NoSuchMethodError` | Runtime version conflict | So Maven tree với JAR thực |
| `UnsupportedClassVersionError` | Runtime Java thấp hơn classfile | Java 17+ và JDK toolchain |
| Resource not found | Path hoặc source root sai | `src/main/resources`, `jar tf` |
| JUnit PASS, `JarAudit` FAIL | Tests có different classpath | Smoke test final JAR, clean build |
| JAR có resource nhưng app không thấy | Sai leading `/` hoặc case | `getResourceAsStream` path chính xác |
| JAR chạy ở root nhưng lỗi ở temp | Đọc path relative source/workspace | Classpath resource hoặc external config contract |
| `java -jar` nhận sai JVM flag | `-Xmx` sau filename | Chuyển JVM option trước `-jar` |
| Đường dẫn ZIP có spaces gây lỗi | Launcher không quote path | Quote `$SCRIPT_DIR`, `%~dp0` |
| Windows báo `'java' is not recognized` | Java runtime không trong PATH | Cài/cấu hình Java 17+ |
| ZIP thiếu `bin/run.sh` | Descriptor include paths sai | Check `src/assembly`, `jar tf` ZIP |
| ZIP có thin/original JAR | Assembly chạy sai thứ tự hoặc glob rộng | Bind verify sau Shade package, chọn exact file |
| `sh run.sh` lỗi file not found | Relative path script sai | Dựa vào script directory, không phải PWD |
| Không chạy được `./run.sh` | Execute bit không giữ khi unzip | `sh run.sh`, permission config |
| Shell script chạy nhưng exit code sai | Không forward Java exit code | `exec` Unix, `exit /b %ERRORLEVEL%` Windows |
| JAR thiếu framework services | Shade descriptors không merge | ServicesResourceTransformer |
| Shaded JAR lỗi signed entry digest | Signature metadata input bị invalid | Review transformers/sign final artifact |
| Shaded artifact khác GAV library POM | Dependency-reduced POM/classifier semantics | Review publishing contract |
| Một JAR rất lớn | Runtime deps/natives/resources nhiều | Audit dependency tree, scope, duplicate |
| Build không tạo JAR | Lệnh tới phase `test` chưa `package` | `mvn clean verify` |
| Tests bị skip nhưng report XML còn | Stale workspace hoặc flags | Fresh clean + enforce tests |
| Hash JAR trong ZIP khác bản QA | Repackaged/rebuilt/nhầm file | Stop release, verify exact bytes |
| `-Pdist` báo không tìm descriptor | File `src/assembly/distribution.xml` thiếu/sai path | Tạo descriptor đúng, case chính xác |
| CI job sau thiếu artifact | Chưa upload/download đúng run | CI artifact handoff, name/run ID |
| Maven cache có Commons Lang nhưng JAR thiếu | `.m2` là build input, không tự vào package | Shade/copied runtime libraries |
| Output khác khi đổi Maven/JDK | Build inputs/toolchain khác | Pin/check versions, inspect archives |
| App cần external API khi offline | Runtime service dependency chưa chuẩn bị | Network/config mocks hoặc integration env |
| Scan tool báo false PASS | Chỉ so text/output không chạy artifact thật | Smoke test exact file, exit status |

### 24.1. Runbook 10 bước

1. **Chọn exact artifact** mà deployment đang dùng và tính SHA-256.
2. Kiểm Java runtime (`java -version`) và command thực.
3. `jar tf` để biết JAR/ZIP có hợp lệ.
4. Đọc `Main-Class` bằng JarFile/manifest tool.
5. So app class entry và resource entry.
6. So runtime dependency classes với Maven graph và SHA.
7. Chạy `java -jar` từ một **directory ngoài project**.
8. Với ZIP, giải nén và chạy launcher từ working directory khác.
9. So final SHA-256 và tests/CI run evidence.
10. Nếu lỗi, sửa root cause trong POM/source/descriptor, `mvn clean verify`, rồi QA artifact mới.

Không sửa bằng cách copy cả `~/.m2`, tắt tests, chèn password vào resources hoặc chọn một JAR theo tên “nghe có vẻ đúng”.

## 25. Checklist bài thực hành

- [ ] Có JDK 17+ và Maven 3.9.x (hoặc môi trường tương thích đã kiểm).
- [ ] Tạo đúng package/path `org.example.standalone.App`.
- [ ] Main class có đúng `public static void main(String[] args)`.
- [ ] `banner.properties` nằm trong `src/main/resources/messages`.
- [ ] Commons Lang là compile/runtime dependency, không bị đặt `provided`.
- [ ] JUnit Jupiter có `test` scope, đủ bốn test methods.
- [ ] Compiler Plugin dùng Java `release=17`.
- [ ] Jar Plugin và Shade Plugin có `Main-Class` đúng.
- [ ] Shade Plugin chạy phase `package` và main artifact là shaded JAR.
- [ ] `mvn clean verify` PASS mà không skip tests.
- [ ] Surefire report từ **chính lần build** có bốn tests PASS.
- [ ] `jar tf` tìm được App.class, resource và StringUtils.class.
- [ ] `JarAudit.java` in `audit=PASS` và exit `0`.
- [ ] `java -jar target/standalone-cli-1.0.0.jar Maven` in stdout chính xác.
- [ ] Copy JAR sang thư mục tạm ngoài project, chạy được bằng Java 17+.
- [ ] Không cần IDE, Maven hoặc source directory ở runtime smoke test.
- [ ] Nếu dùng ZIP, thêm descriptor và hai launcher đúng paths.
- [ ] `mvn -Pdist clean verify` tạo final JAR và `*-dist.zip`.
- [ ] ZIP có `app/standalone-cli-1.0.0.jar`, `bin/run.sh`, `bin/run.cmd`.
- [ ] ZIP giải nén bên ngoài checkout chạy được trên OS tương ứng.
- [ ] Launcher làm việc với path có spaces và arguments.
- [ ] Hash JAR trong ZIP khớp JAR đã QA.
- [ ] SHA-256 record/CI run ID/source commit được lưu khi bàn giao.
- [ ] Không upload original JAR, test-only libs, caches hoặc secrets.
- [ ] Quyền download/retention của CI artifact được xác định.
- [ ] Release quan trọng có SBOM/license/provenance/signature policy.
- [ ] Khi nâng Java/plugin/dependency, chạy lại tests và smoke test.
- [ ] Khi build FAIL, không lấy JAR cũ từ `target` để deploy.

## 26. Câu hỏi tự kiểm tra

**1.** Vì sao `mvn test` PASS chưa chứng minh executable JAR chạy?  
**Đáp án:** Test classpath khác runtime JAR; phase `package` chưa chắc chạy.

**2.** “Chạy độc lập” trong lab có nghĩa không cần Java runtime không?  
**Đáp án:** Không. Cần Java 17+ nhưng không cần Maven/IDE để chạy packaged JAR.

**3.** Main class ở đâu?  
**Đáp án:** `org.example.standalone.App`.

**4.** Resource đặt ở đâu?  
**Đáp án:** `src/main/resources/messages/banner.properties`.

**5.** Vì sao JUnit vẫn PASS khi resource bị đặt nhầm `src/test/resources`?  
**Đáp án:** Test classpath có test resources, main JAR không tự có.

**6.** Runtime dependency nào chứng minh Shade được dùng?  
**Đáp án:** `org.apache.commons:commons-lang3:3.14.0` và class `StringUtils`.

**7.** Tại sao manifest `Main-Class` quan trọng?  
**Đáp án:** `java -jar` cần entry point từ manifest.

**8.** Manifest dùng tên class có `.class` suffix không?  
**Đáp án:** Không; dùng fully qualified Java name.

**9.** Shade Plugin tạo final uber-JAR ở phase nào?  
**Đáp án:** `package` theo execution trong POM.

**10.** Assembly Plugin làm gì trong lab?  
**Đáp án:** Tạo ZIP distribution từ shaded JAR + launcher scripts.

**11.** Vì sao Assembly bind `verify` trong profile `dist`?  
**Đáp án:** Chạy sau Shade ở `package`, nhận final JAR thay vì thin JAR.

**12.** Nếu không `-Pdist`, có ZIP không?  
**Đáp án:** Không; profile không active mặc định.

**13.** Lệnh chạy JAR ngoài IDE là gì?  
**Đáp án:** `java -jar standalone-cli-1.0.0.jar Maven`.

**14.** Stdout ứng dụng với `Maven` là gì?  
**Đáp án:** `Standalone Demo | HELLO OUTSIDE IDE | Maven`.

**15.** Không có argument thì thế nào?  
**Đáp án:** In `Standalone Demo | HELLO OUTSIDE IDE | world`.

**16.** Với hai arguments, exit code bao nhiêu?  
**Đáp án:** `2`, main in usage trên stderr.

**17.** `jar tf` dùng để làm gì?  
**Đáp án:** Liệt kê entries của final archive.

**18.** `JarAudit` kiểm những gì?  
**Đáp án:** `Main-Class`, App.class, resource, Commons Lang class.

**19.** `JarAudit` có chứng minh code không có vulnerability không?  
**Đáp án:** Không.

**20.** Vì sao phải chạy ở thư mục tạm ngoài project?  
**Đáp án:** Loại tình huống vô tình dùng source/working directory/IDE outputs.

**21.** Cần copy `.m2` sang máy chạy JAR không?  
**Đáp án:** Không cho shaded JAR đã đóng đủ runtime deps.

**22.** Thin JAR có thể chạy độc lập như một distribution không?  
**Đáp án:** Có nếu đi kèm runtime libs và launch classpath đúng.

**23.** `java -cp` khác `java -jar`?  
**Đáp án:** `-cp` cho classpath explicit và tên main class CLI; `-jar` dùng executable manifest.

**24.** Vì sao không ký JAR trước khi Shade?  
**Đáp án:** Shade thay bytes và có thể làm signature metadata không còn hợp lệ.

**25.** Vì sao SHA-256 của ZIP khác JAR?  
**Đáp án:** ZIP chứa cả bundle và metadata, không chỉ JAR.

**26.** Nếu hash JAR trong ZIP khác hash JAR đã QA, phải làm gì?  
**Đáp án:** Dừng bàn giao/triển khai, tìm nguyên nhân mismatch.

**27.** `project.build.outputTimestamp` tự làm build reproducible tuyệt đối không?  
**Đáp án:** Không; còn dependency/toolchain/plugins và archive contents.

**28.** Khi nào phải dùng `java -version` ở máy triển khai?  
**Đáp án:** Luôn khi xác minh runtime tương thích classfile Java 17.

**29.** Nếu đã có `commons-lang3` trong Maven local repository, sao JAR vẫn có thể thiếu?  
**Đáp án:** Local repo chỉ là build input cache, không tự đóng dependency vào thin JAR.

**30.** Vì sao smoke-test packaged artifact quan trọng hơn chỉ xem `BUILD SUCCESS`?  
**Đáp án:** Nó kiểm chính file cùng cách runtime sẽ dùng ngoài IDE.

## 27. Tài liệu tham khảo chính thức

1. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — `test`, `package`, `verify`, `install`, `deploy`.
2. [Apache Maven POM Reference](https://maven.apache.org/pom.html) — dependency scopes, packaging và build plugins.
3. [Maven Compiler Plugin — Setting the `--release` option](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html) — Java 17 target.
4. [Maven Surefire Plugin — Overview](https://maven.apache.org/surefire/maven-surefire-plugin/) — JUnit tests, XML reports.
5. [Maven Resources Plugin — Resource Directories](https://maven.apache.org/plugins/maven-resources-plugin/examples/resource-directory.html) — main/test resource roots.
6. [Maven JAR Plugin — Executable JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/executable-jar.html) — `Main-Class` và thin JAR.
7. [Maven Shade Plugin 3.6.2 — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html) — `ManifestResourceTransformer`.
8. [Maven Shade Plugin — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html) — service descriptors, metadata merging.
9. [Maven Shade Plugin — shade:shade](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html) — main artifact replacement, classifiers, minimization.
10. [Maven Assembly Plugin — Usage](https://maven.apache.org/plugins/maven-assembly-plugin/usage.html) — custom descriptors, `assembly:single`.
11. [Maven Assembly Plugin — Descriptor Format](https://maven.apache.org/plugins/maven-assembly-plugin/assembly.html) — `fileSets`, ZIP, file modes.
12. [Maven Assembly Plugin — assembly:single](https://maven.apache.org/plugins/maven-assembly-plugin/single-mojo.html) — lifecycle binding và output naming.
13. [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — inspect resolved graph.
14. [Java SE 17 — The `java` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — `-jar`, `-cp`, source-file mode, JVM args.
15. [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html) — `MANIFEST.MF`, classpath và archive semantics.
16. [Java SE 17 — `JarFile`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html) — manifest/ZIP entry inspection.
17. [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `getResourceAsStream`.
18. [Java SE 17 — `Properties`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) — resource decoding.
19. [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — timestamp và build inputs.
20. [GitHub Actions — Workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts) — lưu và chuyển build outputs giữa jobs.

**Kết luận:** Muốn bàn giao một ứng dụng **thực sự chạy độc lập ngoài IDE**, không dừng ở `mvn package` hay `BUILD SUCCESS`. Hãy **xây executable JAR chứa đúng app classes, runtime dependencies và resources; kiểm manifest/entries; chạy file đó từ một thư mục không có source/Maven; thử ZIP launcher nếu phân phối cho người dùng; và lưu đúng SHA-256, JUnit evidence cùng CI run**. Chỉ những bytes đã được kiểm thử/duyệt mới được chuyển tới bước triển khai.
