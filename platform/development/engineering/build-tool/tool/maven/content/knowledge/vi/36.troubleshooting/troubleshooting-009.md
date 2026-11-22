# Ứng dụng đóng gói thiếu lớp, thiếu tài nguyên hoặc sai manifest trong Maven

> **Build Tool Maven · Chẩn đoán lỗi**  
> Thực hành với **Maven 3.9.x, Java 17**, Maven Compiler Plugin 3.14.1, Resources Plugin 3.3.1, Surefire Plugin 3.6.1, JAR Plugin 3.5.1, Dependency Plugin 3.11.0 và Shade Plugin 3.6.2. Mục tiêu là chẩn đoán **đúng tầng lỗi** khi ứng dụng chạy trong IDE/`mvn test` nhưng JAR bàn giao không chạy: **thiếu lớp của chính dự án**, **thiếu lớp thư viện phụ thuộc**, **thiếu classpath resource**, hoặc **manifest không chỉ đúng entry point/classpath**.

## 1. Triệu chứng: `BUILD SUCCESS` nhưng JAR không chạy

Một project Maven có thể:

```bash
mvn -B clean verify
```

và báo:

```text
BUILD SUCCESS
```

Nhưng chạy:

```bash
java -jar target/my-app-1.0.0.jar
```

lại gặp các lỗi như:

```text
no main manifest attribute, in target/my-app-1.0.0.jar
```

hoặc:

```text
Error: Could not find or load main class org.example.App
```

hoặc:

```text
Exception in thread "main" java.lang.NoClassDefFoundError:
  org/apache/commons/lang3/StringUtils
```

Thậm chí ứng dụng khởi động được nhưng không tìm thấy `config.properties`, `messages/app.properties`, template, XML hoặc `META-INF/services/...`.

**Không nên chữa mọi lỗi bằng cách thêm bừa dependency hoặc copy toàn bộ `~/.m2/repository` vào thư mục triển khai.** Trước hết phải trả lời:

1. **Bạn đang chạy file nào?** Main JAR, thin JAR, shaded JAR, WAR hay JAR cũ?
2. **Entry point có đúng không?** Manifest `Main-Class` có tồn tại và trỏ tới class có `public static void main(String[] args)`?
3. **Class của ứng dụng có trong JAR không?** Entry path có đúng package?
4. **Các class của dependencies nằm ở đâu?** Có trong uber-JAR, trong `lib/` hay được container cấp?
5. **Resources có ở đúng classpath path không?** Nằm trong `src/main/resources` và đã copy vào archive chưa?
6. **Runtime thực tế có dùng đúng Java/classpath/module-path không?**
7. **Đây có phải đúng bytes artifact vừa build/QA không?**

Các câu hỏi trên xác định nguyên nhân nhanh hơn so với lặp vô hạn `mvn clean install`.

### 1.1. Phân loại lỗi nhanh

| Thông báo/biểu hiện | Vùng nghi vấn chính | Phép kiểm tra đầu tiên |
| --- | --- | --- |
| `no main manifest attribute` | Manifest thiếu `Main-Class` | Đọc `META-INF/MANIFEST.MF` của JAR |
| `Could not find or load main class` khi `java -jar` | `Main-Class` sai hoặc class không nằm trong JAR | So `Main-Class` với `jar tf` |
| `NoClassDefFoundError` của thư viện bên ngoài | Thin JAR thiếu runtime dependencies/classpath | `dependency:tree`, `jar tf`, `-cp` |
| `ClassNotFoundException` từ reflection hoặc `Class.forName` | Class/module/classloader tìm không thấy | Xem full exception và `ClassLoader` |
| `NoSuchMethodError` / `AbstractMethodError` | Runtime version conflict/binary incompatibility | In dependency versions và class load origin |
| `getResourceAsStream(...) == null` | Sai path/case hoặc resource không đóng gói | `jar tf` tìm resource entry |
| Properties/template hoạt động trong tests, lỗi khi chạy JAR | Resource nằm trong test classpath hoặc file system | So `target/classes` với `target/test-classes` |
| `Invalid or corrupt jarfile` | File sai/corrupt/truncated/không phải JAR hợp lệ | `jar tf`, checksum, tải lại từ nguồn |
| JAR chạy nhưng nội dung/cấu hình cũ | Đang chọn output cũ, resource cũ, build không sạch | `mvn clean verify`, so hash/entry |
| `UnsupportedClassVersionError` | JDK runtime thấp hơn classfile version | `java -version`, `javap -verbose` |

Bảng là **định hướng kiểm tra**, không phải kết luận tuyệt đối. Đọc **stack trace đầy đủ và chính file được bàn giao** trước khi thay POM.

## 2. Phân biệt output Maven, classpath và JAR

Một project dùng:

```xml
<packaging>jar</packaging>
```

thường có các mốc:

```text
src/main/java  --Compiler Plugin--> target/classes/*.class
src/main/resources --Resources Plugin--> target/classes/resources
src/test/java  --> target/test-classes/*.class
src/test/resources --> target/test-classes/resources
                         |
               Maven JAR Plugin
                         |
             target/my-app-1.0.0.jar
```

Default **main JAR** đóng gói từ `target/classes` cùng metadata; nó **không tự nhét mọi dependency JAR** vào trong file output.

### 2.1. Ba dạng triển khai khác nhau

| Kiểu | Bên trong file chính | Cách chạy thường gặp |
| --- | --- | --- |
| Thin JAR | Main classes/resources, manifest | `java -cp "app.jar:lib/*" package.Main` hoặc `java -jar` nếu manifest `Class-Path` trỏ đúng `lib/` |
| Uber/fat/shaded JAR | Main classes/resources và dependency classes được gom | `java -jar app.jar` khi có `Main-Class` đúng |
| Container/runtime-managed | Classes/resources, một phần dependencies do container/module path cung cấp | Command do framework/application server/module runtime quy định |

**Một JAR có `Main-Class` chưa chắc là fat JAR.** Nó có thể là thin JAR hợp lệ, nhưng `java -jar` chỉ chạy được nếu classpath runtime cung cấp đủ thư viện.

### 2.2. Vì sao IDE hoặc JUnit chạy được mà JAR lỗi?

IDE và Surefire thường lập **project runtime/test classpath** từ Maven resolved dependencies. Khi chạy qua IDE, các JAR phụ thuộc có thể được IDE thêm tự động. Với `java -jar`, Java launcher chủ yếu lấy **entry point từ manifest**, và tìm dependencies qua nội dung JAR hoặc các manifest `Class-Path` entries hợp lệ.

Do đó cùng một `App.class`:

```text
IDE run: app class + commons-lang3 từ local Maven repo  -> PASS
JUnit test: test classpath có commons-lang3             -> PASS
java -jar thin.jar: chỉ main JAR, không có dependency   -> FAIL
```

Đây không phải mâu thuẫn trong Maven. **Hai lệnh đang tạo hai runtime classpath khác nhau.**

## 3. Điều tra theo thứ tự: file → manifest → entry → dependencies → resources

Một chuỗi chẩn đoán hiệu quả:

```text
Chọn chính xác final JAR
          |
jar tf: archive hợp lệ?
          |
META-INF/MANIFEST.MF có Main-Class?
          |
Class Main-Class có entry .class?
          |
Dependencies runtime có đủ?
          |
Classpath resources có đúng path?
          |
Chạy lại bằng command deployment thực tế
          |
Kiểm tra stdout, exit code, checksum và test evidence
```

Không nên nhảy thẳng tới `mvn dependency:tree` khi lỗi thật là manifest thiếu `Main-Class`. Cũng không nên sửa manifest khi class thư viện phụ thuộc không có trong runtime classpath.

### 3.1. Xác định JAR thật

Từ project root:

```bash
mvn -B clean verify
jar tf target/my-app-1.0.0.jar
```

Thay `my-app-1.0.0.jar` bằng **đúng filename** từ log/POM. Nếu project có Maven Shade/Assembly/Spring Boot repackage, có thể có nhiều JAR:

```text
target/original-my-app-1.0.0.jar
target/my-app-1.0.0.jar
target/my-app-1.0.0-exec.jar
```

Tên trên chỉ minh họa; không mặc định mọi plugin dùng đúng naming. **Một JAR trung gian không nên được chọn làm release chỉ vì nó có đuôi `.jar`.**

### 3.2. Kiểm tra JAR bằng công cụ JDK

```bash
jar tf target/my-app-1.0.0.jar
```

Cú pháp `jar tf` là liệt kê entries trong archive. Kiểm tra:

```text
META-INF/MANIFEST.MF
org/example/App.class
messages/app.properties
```

Không có entry kỳ vọng là một dấu hiệu trực tiếp của **đóng gói thiếu file**. Có entry chưa chắc chứng minh chương trình chạy đúng; cần kiểm tra nội dung, phiên bản, ClassLoader và runtime.

## 4. Manifest: `Main-Class` và `Class-Path` là hai thuộc tính khác nhau

Theo Java JAR File Specification, manifest là file:

```text
META-INF/MANIFEST.MF
```

và có thể chứa:

```text
Manifest-Version: 1.0
Main-Class: org.example.packdiag.App
```

- **`Main-Class`** định danh class entry point theo **tên Java fully qualified**; không có `.class` suffix, không dùng dấu gạch chéo của ZIP path.
- **`Class-Path`** có thể khai báo các relative URLs của JARs/directories phụ thuộc, được resolve tương đối với JAR chứa manifest theo các điều kiện Java specification.
- **`Implementation-Version`** là metadata phiên bản nếu được cấu hình phát sinh; không thay thế `Main-Class`.
- **`Automatic-Module-Name`** phục vụ tên module khi dùng module path, không chọn executable entry point thay cho `Main-Class`.

### 4.1. Ví dụ sai và đúng

Sai:

```text
Main-Class: org/example/packdiag/App.class
```

Đúng:

```text
Main-Class: org.example.packdiag.App
```

Sai:

```text
Main-Class: App
```

khi class thực có package `org.example.packdiag`.

Sai:

```text
Main-Class: org.example.packdiag.DoesNotExist
```

nếu class đó không có trong JAR hoặc runtime classpath.

**Lưu ý:** một `Main-Class` đúng vẫn không giải quyết thiếu thư viện hoặc thiếu resource.

### 4.2. Manifest có thể bị xuống dòng vật lý

Java manifest cho phép các lines dài được gấp sang dòng continuation. Đừng parse `MANIFEST.MF` bằng quy tắc “một line text luôn chứa toàn bộ value” nếu có attributes dài.

Để đọc robust hơn, dùng:

```java
try (java.util.jar.JarFile jar = new java.util.jar.JarFile("app.jar")) {
    java.util.jar.Manifest mf = jar.getManifest();
    String mainClass = mf == null ? null
            : mf.getMainAttributes().getValue("Main-Class");
}
```

Đoạn này là **fragment minh họa**, còn một utility runnable đầy đủ được cung cấp tại mục 8.

### 4.3. `java -jar` và `java -cp`

```bash
java -jar app.jar
```

sử dụng manifest `Main-Class`. Khi dùng launcher `-jar`, tùy chọn application `-cp`/`CLASSPATH` không được dùng để bổ sung arbitrary dependency classpath cho ứng dụng như khi gọi main class trực tiếp.

Để chủ động cung cấp libraries:

```bash
java -cp "app.jar:lib/*" org.example.packdiag.App
```

trên Linux/macOS, hoặc:

```powershell
java -cp "app.jar;lib/*" org.example.packdiag.App
```

trên Windows. Khi gọi `-cp`, bạn **chọn main class trên command line**; không bắt Java dựa vào `Main-Class` của JAR để tìm entry point.

`lib/*` trong Java classpath được JVM launcher mở rộng tới `.jar`/`.JAR` trong thư mục đó; wildcard này **không có nghĩa tìm đệ quy vô hạn** và thứ tự JARs không được đảm bảo. Tránh giữ hai versions của cùng thư viện trong `lib/`.

## 5. Lab hoàn chỉnh: Java 17, resource và một compile dependency

Lab tái hiện **cả ba nhóm lỗi**:

1. Thin JAR có đúng `Main-Class` nhưng **thiếu runtime dependency trong chính file JAR**.
2. Resource đặt nhầm `src/test/resources` làm **tests PASS trong khi deployed JAR thiếu file**.
3. Manifest `Main-Class` bị thiếu/sai làm **không thể dùng `java -jar`**, dù `App.class` vẫn tồn tại.

Sau đó dùng Maven Shade Plugin để tạo executable uber-JAR khi thực sự muốn một file tự chạy.

### 5.1. Cấu trúc source

```text
packaging-diagnostics-lab/
├── pom.xml
├── audit/
│   └── ArchiveAudit.java
└── src/
    ├── main/
    │   ├── java/org/example/packdiag/App.java
    │   └── resources/messages/app.properties
    └── test/
        └── java/org/example/packdiag/AppTest.java
```

`audit/ArchiveAudit.java` là **tool kiểm chứng độc lập**, được chạy bằng Java 17 source-file launcher. Nó **không nằm trong application JAR**.

### 5.2. `pom.xml` đầy đủ, có profile tạo uber-JAR tùy chọn

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>packaging-diagnostics-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Packaging Diagnostics Lab</name>

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
                            <mainClass>org.example.packdiag.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>uber</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-shade-plugin</artifactId>
                        <version>3.6.2</version>
                        <executions>
                            <execution>
                                <id>make-executable-uber-jar</id>
                                <phase>package</phase>
                                <goals>
                                    <goal>shade</goal>
                                </goals>
                                <configuration>
                                    <createDependencyReducedPom>false</createDependencyReducedPom>
                                    <transformers>
                                        <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                            <mainClass>org.example.packdiag.App</mainClass>
                                        </transformer>
                                    </transformers>
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

**Vai trò từng phần:**

- Compiler Plugin compile Java 17 vào `target/classes`.
- Resources Plugin copy `src/main/resources/messages/app.properties` sang `target/classes/messages/app.properties`.
- Commons Lang 3.14.0 là **compile/runtime dependency**: app gọi `StringUtils.upperCase`.
- JUnit Jupiter chỉ có **test scope**, do Surefire dùng trong test classpath; không cần ở runtime của app.
- JAR Plugin tạo **thin JAR**, có `Main-Class` nhưng **không tự chứa Commons Lang**.
- Profile `uber` chỉ chạy khi dùng `-Puber`; Shade Plugin 3.6.2 gom classes từ runtime dependencies và transformer đặt `Main-Class` cho final shaded archive.
- `createDependencyReducedPom=false` giúp lab không tạo dependency-reduced POM cạnh source; đây là **lựa chọn minh họa**. Khi publish một shaded library, cần cân nhắc dependency-reduced POM/consumer semantics để tránh xung đột transitive dependencies.
- `project.build.outputTimestamp` hỗ trợ reproducible archive timestamps với plugins tương thích; không sửa runtime classpath hoặc thiếu resources.

### 5.3. `src/main/resources/messages/app.properties`

```properties
app.name=Package Diagnostics
app.greeting=hello from resource
```

Đây là **resource main**, được giữ **nguyên đường dẫn** dưới classpath root:

```text
messages/app.properties
```

Không đặt file tại:

```text
src/main/java/messages/app.properties
```

và không kỳ vọng app đọc từ một absolute filesystem path cụ thể. Với cấu hình mặc định, vị trí đúng là `src/main/resources`.

### 5.4. `src/main/java/org/example/packdiag/App.java`

```java
package org.example.packdiag;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Objects;
import java.util.Properties;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message() {
        Properties props = new Properties();

        try (InputStream input = App.class.getResourceAsStream(
                "/messages/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: messages/app.properties");
            }
            props.load(new InputStreamReader(
                    input, StandardCharsets.UTF_8));
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "Cannot read classpath resource", exception);
        }

        String name = Objects.requireNonNull(
                props.getProperty("app.name"), "Missing app.name");
        String greeting = Objects.requireNonNull(
                props.getProperty("app.greeting"), "Missing app.greeting");

        return name + " | "
                + StringUtils.upperCase(greeting, Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**Tại sao viết như vậy?**

1. `App.class.getResourceAsStream("/messages/app.properties")` dùng **absolute resource name tính từ classpath root** vì có `/` phía trước.
2. Dùng `InputStreamReader(..., UTF_8)` để đọc UTF-8; `Properties.load(InputStream)` thuần có encoding convention khác. Nội dung demo chỉ ASCII nhưng cách đọc này rõ ràng cho ứng dụng thực tế có tiếng Việt.
3. Nếu file resource thiếu, `getResourceAsStream` có thể trả `null`, và app báo **lỗi có ý nghĩa** thay vì NPE mơ hồ.
4. `StringUtils.upperCase(greeting, Locale.ROOT)` tạo dependency runtime cố ý để thực hành **thiếu lớp thư viện**.
5. `main` là entry point đúng chữ ký Java launcher cần.

### 5.5. `src/test/java/org/example/packdiag/AppTest.java`

```java
package org.example.packdiag;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void readsResourceAndDependency() {
        assertEquals("Package Diagnostics | HELLO FROM RESOURCE",
                App.message());
    }

    @Test
    void messageMentionsApplication() {
        assertTrue(App.message().startsWith("Package Diagnostics"));
    }
}
```

JUnit tests gọi `App.message()` và cần **cả Commons Lang lẫn resource**; trong test classpath Maven đã resolve compile dependencies và main resources.

### 5.6. Build mốc

Ở root project:

```bash
java -version
javac -version
mvn -version
mvn -B clean verify
```

Các files expected khi environment resolve được dependencies:

```text
target/classes/org/example/packdiag/App.class
target/classes/messages/app.properties
target/test-classes/org/example/packdiag/AppTest.class
target/surefire-reports/TEST-org.example.packdiag.AppTest.xml
target/packaging-diagnostics-lab-1.0.0.jar
```

Phần summary tests **dự kiến**:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả từ code example **khi thực thi thành công**, không phải nguyên văn toàn bộ Maven logs.

## 6. Thí nghiệm A — thin JAR đúng manifest nhưng thiếu Commons Lang

Với **không bật** profile `uber`:

```bash
mvn -B clean verify
java -jar target/packaging-diagnostics-lab-1.0.0.jar
```

Maven build và unit tests dự kiến PASS, nhưng `java -jar` **không có Commons Lang trong runtime classpath**. Lỗi dự kiến mang dạng:

```text
Exception in thread "main" java.lang.NoClassDefFoundError:
  org/apache/commons/lang3/StringUtils
```

Dòng đầu của exception và những stack-trace frames phụ thuộc JVM, nên đây **không phải cam kết từng byte của stderr**.

### 6.1. Vì sao không phải do `Main-Class`?

Manifest có:

```text
Main-Class: org.example.packdiag.App
```

và main class có entry:

```text
org/example/packdiag/App.class
```

Java đã tìm được entry point. Lỗi phát sinh **khi App gọi class của thư viện bên ngoài**.

**Thực tế cần kiểm chứng:** nếu chạy nhầm một shaded JAR cũ hoặc runtime đã có manifest Class-Path tùy chỉnh, kết quả có thể khác. Hãy dùng `mvn clean verify` ở đúng POM/profile được mô tả.

### 6.2. So các entries trong thin JAR

```bash
jar tf target/packaging-diagnostics-lab-1.0.0.jar
```

Tìm:

```text
org/example/packdiag/App.class
messages/app.properties
```

Và xác nhận **không** có class:

```text
org/apache/commons/lang3/StringUtils.class
```

Đây là điều **bình thường** với thin JAR. Maven JAR Plugin không có nhiệm vụ copy mọi transitive dependency class vào main archive.

### 6.3. Sửa bằng external runtime classpath (không cần fat JAR)

Copy dependencies cần ở runtime vào directory riêng:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
```

Theo Maven Dependency Plugin, `includeScope=runtime` gồm các dependencies thuộc **compile và runtime**, không cố copy JUnit test-scope vào runtime distribution.

Chạy packaged JAR bằng classpath explicit trên Linux/macOS:

```bash
java -cp "target/packaging-diagnostics-lab-1.0.0.jar:target/dependency/*" org.example.packdiag.App
```

Trên Windows PowerShell:

```powershell
java -cp "target\packaging-diagnostics-lab-1.0.0.jar;target\dependency\*" org.example.packdiag.App
```

**Stdout chính xác từ main program:**

```text
Package Diagnostics | HELLO FROM RESOURCE
```

Lệnh `java -cp` chỉ main class rõ ràng; nó **không** dùng `Main-Class` để chọn main. Đây là một cách phân phối hợp lệ: **thin app JAR + `lib/` đầy đủ + launch script**.

### 6.4. Thử chỉ với `target/classes`

Nếu chưa package, cũng có thể:

```bash
java -cp "target/classes:target/dependency/*" org.example.packdiag.App
```

Trên Windows, thay dấu phân cách bằng `;`. Đây là **debug classpath** của build output, **không phải bằng chứng packaged JAR đã chứa mọi file**. Khi kiểm thử bàn giao, nên chạy từ **chính final JAR** như mục 6.3.

### 6.5. Vì sao không thêm JUnit vào JAR?

JUnit Jupiter có `test` scope và không phải runtime dependency của ứng dụng. Copy mọi file từ `.m2` sẽ làm distribution phình to, đưa các versions không liên quan vào classpath và tăng rủi ro version conflict.

Điều quan trọng là **resolved runtime dependency set**, không phải toàn bộ Maven local repository.

## 7. Thí nghiệm B — Shade Plugin tạo executable uber-JAR

Khi mục tiêu deployment là **một JAR chạy trực tiếp**:

```bash
mvn -B -Puber clean verify
java -jar target/packaging-diagnostics-lab-1.0.0.jar
```

Trong POM lab, Shade Plugin 3.6.2 chạy `shade` ở phase `package`. Mặc định nó thay main project artifact bằng shaded result (không cấu hình attach classifier). Vì thế file chính sau profile có runtime classes từ Commons Lang và manifest transformer trỏ `Main-Class` vào `App`.

**Stdout chính xác:**

```text
Package Diagnostics | HELLO FROM RESOURCE
```

### 7.1. Kiểm tra shade đã thực sự chạy

```bash
jar tf target/packaging-diagnostics-lab-1.0.0.jar
```

Các entries đáng kiểm tra:

```text
org/example/packdiag/App.class
org/apache/commons/lang3/StringUtils.class
messages/app.properties
META-INF/MANIFEST.MF
```

Nếu bật relocation hoặc excludes trong project thực, class path có thể khác; **kiểm tra đúng cấu hình Shade của project đó**.

### 7.2. Thứ tự plugin và final artifact

Tại phase `package`, JAR Plugin tạo main JAR rồi Shade Plugin có thể xử lý nó để tạo shaded result. Tên output có thể khác nếu dùng `shadedArtifactAttached`, `shadedClassifierName`, finalName hoặc custom executions.

Sau shading, có thể còn file original/unshaded để debug. **Không upload nhầm original JAR chỉ vì nó có tên gần giống.**

### 7.3. Shade không giải quyết mọi thứ tự động

Maven Shade Plugin có các transformer như:

- `ManifestResourceTransformer`: tạo/sửa manifest entries.
- `ServicesResourceTransformer`: gộp service descriptors `META-INF/services` khi nhiều dependencies cung cấp cùng service interface.
- `AppendingTransformer`: nối các text resources có yêu cầu merge theo nội dung.
- Các transformers khác tùy định dạng XML/metadata.

Nếu shade nhiều thư viện cùng chứa `META-INF/services/foo.Bar`, việc copy tùy ý có thể làm một descriptor ghi đè descriptor khác hoặc mất provider registration. **Dùng `ServicesResourceTransformer` khi ứng dụng dùng ServiceLoader và cần gộp service descriptors**.

### 7.4. Ví dụ fragment thêm service merger

Trong `<configuration>` của Shade Plugin, ví dụ:

```xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <mainClass>org.example.packdiag.App</mainClass>
    </transformer>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer" />
</transformers>
```

Đây là **fragment thay thế phần transformers**, không phải POM đầy đủ cần copy nguyên văn chồng thêm. Trong lab Commons Lang không yêu cầu ServiceLoader, nên chưa bắt buộc.

### 7.5. Cẩn thận với signed dependency JARs

Shading/transforming thay đổi nội dung archive. Các signature metadata có trong dependency JARs (`META-INF/*.SF`, `.RSA`, `.DSA`) có thể không còn hợp lệ khi đổi entries. Các projects thực có signing requirements cần dùng đúng hướng dẫn Shade/signing policy, loại bỏ hoặc tạo lại những signature metadata không còn phù hợp **theo quy trình được duyệt**, và ký **final artifact** khi cần.

Không tự coi một uber-JAR là “đã xác thực” chỉ vì nó chứa signature files của dependencies trước khi shade.

## 8. Utility Java 17 đọc JAR để phân biệt bốn lỗi đầu tiên

File `audit/ArchiveAudit.java` dùng `JarFile` và `Manifest`, không chạy application, không cần thư viện thứ ba. Nó đọc **chính packaged JAR** được chỉ định.

```java
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ArchiveAudit {
    private ArchiveAudit() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java audit/ArchiveAudit.java PATH_TO_JAR");
        }

        Path jarPath = Path.of(args[0]);

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            Manifest manifest = jar.getManifest();
            String mainClass = manifest == null ? "(missing)"
                    : manifest.getMainAttributes()
                              .getValue(Attributes.Name.MAIN_CLASS);

            boolean appClass = jar.getJarEntry(
                    "org/example/packdiag/App.class") != null;
            boolean resource = jar.getJarEntry(
                    "messages/app.properties") != null;
            boolean commonsClass = jar.getJarEntry(
                    "org/apache/commons/lang3/StringUtils.class") != null;

            System.out.println("main-class=" + mainClass);
            System.out.println("app-class=" + appClass);
            System.out.println("resource=" + resource);
            System.out.println("commons-class=" + commonsClass);
        }
    }
}
```

Với **JDK 17**, có thể chạy single-file source:

```bash
java audit/ArchiveAudit.java target/packaging-diagnostics-lab-1.0.0.jar
```

### 8.1. Expected output cho thin JAR

Sau:

```bash
mvn -B clean verify
java audit/ArchiveAudit.java target/packaging-diagnostics-lab-1.0.0.jar
```

**Stdout chính xác của utility:**

```text
main-class=org.example.packdiag.App
app-class=true
resource=true
commons-class=false
```

`commons-class=false` **không phải build error** đối với thin JAR. Nó giúp giải thích vì sao cần `lib/` hoặc uber-JAR ở runtime.

### 8.2. Expected output cho shaded JAR

Sau:

```bash
mvn -B -Puber clean verify
java audit/ArchiveAudit.java target/packaging-diagnostics-lab-1.0.0.jar
```

**Stdout chính xác của utility trong lab, nếu Shade hoàn tất:**

```text
main-class=org.example.packdiag.App
app-class=true
resource=true
commons-class=true
```

Vì Commons Lang class đã được gom vào archive. Nếu đặt filters/relocation/minimizeJar trong project khác, cần điều chỉnh kỳ vọng và check đúng final packaging.

### 8.3. Vì sao utility tốt hơn đoán qua tên file?

Một file gọi là `app-all.jar` chưa chắc đủ dependencies; tên `app.jar` chưa chắc là thin JAR. `JarFile` kiểm tra **entries thật**. Khi class không tồn tại, bạn biết phải xem compiler/JAR filters, runtime dependencies hoặc đúng file output.

Nó không verify chữ ký, tính toàn vẹn checksum, logic của các transitive dependencies hoặc chạy app; đó là các bước QA khác.

## 9. Thí nghiệm C — resource đặt nhầm vào test classpath

Đây là một tình huống rất dễ gặp vì **unit tests vẫn PASS** nhưng JAR phát hành thiếu config.

### 9.1. Vị trí đúng và sai

Đúng cho main runtime:

```text
src/main/resources/messages/app.properties
```

Sai nếu app production cần file này nhưng đặt:

```text
src/test/resources/messages/app.properties
```

Maven copy test resources vào:

```text
target/test-classes/messages/app.properties
```

và main resources vào:

```text
target/classes/messages/app.properties
```

Main JAR mặc định lấy **main output**, không tự bao gồm toàn bộ `target/test-classes`.

### 9.2. Tạo lỗi trong lab Unix

**Chỉ thực hiện trong bản copy project lab**, sau baseline build:

```bash
mkdir -p src/test/resources/messages
mv src/main/resources/messages/app.properties src/test/resources/messages/app.properties
mvn -B clean verify
```

Hai JUnit tests có thể vẫn PASS bởi Surefire test classpath có test resources. Nhưng JAR cuối **không chứa**:

```text
messages/app.properties
```

Kiểm chứng:

```bash
java audit/ArchiveAudit.java target/packaging-diagnostics-lab-1.0.0.jar
```

Dòng quan trọng sẽ là:

```text
resource=false
```

Để xem lỗi runtime resource rõ hơn, cần cấp Commons Lang ngoài JAR:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
java -cp "target/packaging-diagnostics-lab-1.0.0.jar:target/dependency/*" org.example.packdiag.App
```

Runtime thiếu resource nên `App.message()` ném:

```text
java.lang.IllegalStateException:
  Missing classpath resource: messages/app.properties
```

Stack trace thực tế có dòng/frames khác. Lỗi này xảy ra **không phải vì Commons Lang vắng mặt**, mà vì resource chỉ có trong test classpath.

### 9.3. Khôi phục và xác minh

Trên Unix:

```bash
mv src/test/resources/messages/app.properties src/main/resources/messages/app.properties
mvn -B clean verify
java audit/ArchiveAudit.java target/packaging-diagnostics-lab-1.0.0.jar
```

Kỳ vọng `resource=true`.

Trên Windows PowerShell, tương đương:

```powershell
New-Item -ItemType Directory -Force -Path .\src\test\resources\messages | Out-Null
Move-Item -LiteralPath .\src\main\resources\messages\app.properties -Destination .\src\test\resources\messages\
mvn -B clean verify
```

Khôi phục:

```powershell
Move-Item -LiteralPath .\src\test\resources\messages\app.properties -Destination .\src\main\resources\messages\
mvn -B clean verify
```

**Không copy cả `src/test/resources` vào runtime JAR** để “chữa” chung; tests có thể chứa fixtures, secrets mô phỏng và dữ liệu không nên đi vào production. Chuyển đúng **resource chính** sang `src/main/resources`.

### 9.4. Vì sao luôn chạy `clean` trong thí nghiệm này?

Nếu trước đó resource từng có trong `target/classes`, rồi bạn chỉ chuyển source sang `src/test/resources` và không `clean`, bản resource cũ trong `target/classes` **có thể tồn tại** và lọt vào JAR. Kết quả sẽ che mất lỗi.

`mvn clean verify` loại đầu ra cũ rồi tái tạo, khiến bài kiểm chứng phản ánh đúng source layout. Đây cũng là lý do **CI release cần kiểm tra dữ liệu đầu ra cũ**.

## 10. Thí nghiệm D — manifest sai hoặc thiếu entry point

### 10.1. Thiếu `Main-Class`

Nếu không cấu hình `<mainClass>` cho JAR Plugin hoặc một transformer phù hợp, main JAR có thể vẫn được tạo nhưng không chạy bằng:

```bash
java -jar target/packaging-diagnostics-lab-1.0.0.jar
```

Triệu chứng điển hình:

```text
no main manifest attribute, in target/packaging-diagnostics-lab-1.0.0.jar
```

Điều này **không** chứng minh `App.class` bị thiếu. Bạn có thể chạy đúng class qua:

```bash
java -cp "target/packaging-diagnostics-lab-1.0.0.jar:target/dependency/*" org.example.packdiag.App
```

nếu class/dependencies/resources đầy đủ.

### 10.2. `Main-Class` sai tên package

Một cấu hình sai minh họa:

```xml
<manifest>
    <mainClass>org.example.packdiag.DoesNotExist</mainClass>
</manifest>
```

Maven JAR Plugin có thể chấp nhận string đó trong manifest mà **không kiểm tra class thực tồn tại**. Unit tests vẫn PASS nếu chúng chạy `App` trực tiếp.

Kiểm tra:

```bash
java audit/ArchiveAudit.java target/packaging-diagnostics-lab-1.0.0.jar
```

Nó sẽ in:

```text
main-class=org.example.packdiag.DoesNotExist
```

trong khi `app-class=true`. Khi `java -jar`, launcher không tìm thấy main class được chỉ định.

Khắc phục:

```xml
<manifest>
    <mainClass>org.example.packdiag.App</mainClass>
</manifest>
```

rồi `mvn clean verify` và inspect manifest/JAR.

### 10.3. Package name khác folder path

Java source khai báo:

```java
package org.example.packdiag;
```

thì class entry thường là:

```text
org/example/packdiag/App.class
```

Không dùng class name viết theo filesystem với dấu `/` trong `Main-Class`. Folder source có thể khác do custom source roots, nhưng **tên package của classfile** mới là thứ launcher cần.

### 10.4. `public static void main(String[] args)`

Nếu `Main-Class` chỉ tới một class có `main` không hợp lệ, ví dụ private/non-static/wrong signature, launcher vẫn có thể báo không tìm được main method phù hợp. Manifest đúng **không thay thế** việc class có Java entry point đúng.

Dạng chuẩn:

```java
public static void main(String[] args) {
    System.out.println("ready");
}
```

Đoạn trên là **fragment minh họa**, không có package/class wrapper; main đầy đủ đã có trong `App.java` mục 5.4.

### 10.5. Khi `java -cp` PASS nhưng `java -jar` FAIL

Ghi nhớ:

```text
java -cp ... org.example.packdiag.App
```

**bỏ qua yêu cầu manifest entry point**, vì main class được chỉ định trên CLI.

```text
java -jar app.jar
```

**cần manifest Main-Class** và runtime dependency resolution tương thích. Vì vậy phép so hai lệnh giúp phân biệt **entry point problem** với **bytecode/dependency problem**.

## 11. Một lỗi khác: class của chính dự án không nằm trong JAR

Ví dụ class tồn tại ở:

```text
target/classes/org/example/packdiag/App.class
```

nhưng **không có** trong:

```text
target/packaging-diagnostics-lab-1.0.0.jar
```

Lúc này hãy xem **package phase và Jar Plugin includes/excludes**, không chỉ Compiler Plugin.

### 11.1. Trường hợp Jar Plugin excludes lọc mất App.class

Một fragment cố tình sai:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.5.1</version>
    <configuration>
        <excludes>
            <exclude>org/example/packdiag/App.class</exclude>
        </excludes>
    </configuration>
</plugin>
```

Đây là **cấu hình lỗi minh họa**, không phải thay thế trực tiếp POM lab, vì nó cũng bỏ cấu hình `Main-Class` nếu bạn thay toàn bộ plugin block. Để tái hiện đúng trường hợp **manifest chỉ App nhưng archive lọc mất App**, chỉ thêm `<excludes>` vào `<configuration>` hiện có.

Khi main class bị loại khỏi JAR:

- Compile/test có thể vẫn thành công.
- `target/classes/.../App.class` tồn tại.
- `jar tf target/...jar` **không có** App.class.
- `java -jar` có thể lỗi `Could not find or load main class`.

Sửa include/exclude rồi clean/package và inspect lại file.

### 11.2. Sai source root

Nếu Java source thực tế đặt trong:

```text
src/custom/java/
```

thay vì default:

```text
src/main/java/
```

Compiler Plugin sẽ không tự coi nó là source root chỉ vì có `.java`. Cần đặt lại theo convention hoặc cấu hình Build Helper Maven Plugin/add-source đúng phase, cùng source encoding/compiler release.

Triệu chứng:

- Không thấy `.class` trong `target/classes`.
- Maven log có thể báo `No sources to compile`.
- JAR không có class.

**Không sửa manifest trước khi bảo đảm class đã được compile.**

### 11.3. `target/classes` có class nhưng JAR vẫn là bản cũ

Nếu bạn chỉ chạy:

```bash
mvn -B compile
```

rồi mở JAR từ lần `package` trước, có thể thấy class mới ở output nhưng **archive vẫn cũ**. Chạy lifecycle tới `package`/`verify` rồi kiểm tra JAR timestamp/digest/contents.

Với CI, ưu tiên clean workspace và `mvn clean verify` trước khi publish. Không upload file `target/*.jar` chỉ dựa vào sự tồn tại của tên file.

## 12. Resources: path, case, filters và encoding

Resources Plugin thường copy:

```text
src/main/resources/messages/app.properties
          |
          v
target/classes/messages/app.properties
          |
          v
JAR entry messages/app.properties
```

### 12.1. `Class.getResourceAsStream` khác `ClassLoader.getResourceAsStream`

Với `App` thuộc package `org.example.packdiag`:

```java
App.class.getResourceAsStream("/messages/app.properties");
```

tìm từ **classpath root**.

```java
App.class.getResourceAsStream("messages/app.properties");
```

tìm tương đối package của `App`, tức logic path:

```text
org/example/packdiag/messages/app.properties
```

Và:

```java
App.class.getClassLoader()
        .getResourceAsStream("messages/app.properties");
```

tìm từ classpath root **không đặt dấu `/` phía trước**.

Do đó **dấu `/` đầu resource name quan trọng**, không phải chỉ là style.

### 12.2. Case sensitivity

JAR là ZIP chứa các entry names. Nếu archive có:

```text
Messages/App.properties
```

nhưng code đọc:

```text
messages/app.properties
```

có thể không resolve được. Hãy so chính xác chữ hoa/thường và path separators `/` trong archive.

Đừng suy rằng “chạy trên Windows thành công” bảo đảm classpath resource case cũng sẽ đúng ở một Linux container.

### 12.3. `src/main/resources` khác `src/test/resources`

- Main resources đi vào `target/classes`, rồi main JAR nếu không bị loại.
- Test resources đi vào `target/test-classes`, dùng trong tests nhưng không tự đóng vào main JAR.
- Các project có resource directories tùy chỉnh phải khai báo `<build><resources>`.

Đây là nguyên nhân chính của tình huống **JUnit PASS, JAR lỗi** ở mục 9.

### 12.4. Includes/excludes có thể lọc mất `.properties`

Một fragment minh họa:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <includes>
                <include>app.xml</include>
            </includes>
        </resource>
    </resources>
</build>
```

Nếu chỉ include `app.xml` ở root, `messages/app.properties` sẽ **không được copy**. Để thêm resource không đi theo convention, hãy khai báo path/include cho đúng. Cẩn thận: một `<resources>` mới **thay đổi tập main resource roots**, không chỉ là “bổ sung mọi file”.

Trước khi thay, chạy:

```bash
mvn -B clean resources:resources
```

Lưu ý gọi prefix `resources:resources` có thể resolve plugin version theo cấu hình; nếu cần chắc chắn trong diagnostic, gọi explicit version:

```bash
mvn -B org.apache.maven.plugins:maven-resources-plugin:3.3.1:resources
```

Sau đó kiểm tra:

```text
target/classes/messages/app.properties
```

**Không gọi `resources:resources` là build JAR**: nó chỉ chạy goal copy main resources theo plugin configuration.

### 12.5. Resource filtering gây thay đổi nội dung

Một resource có thể chứa placeholder:

```properties
app.name=${project.name}
```

Nếu Maven Resources Plugin được cấu hình `<filtering>true</filtering>` cho resource set tương ứng, placeholder có thể được thay bởi Maven property.

Nếu filtering không bật, application có thể đọc nguyên chuỗi `${project.name}`. Nếu property không được định nghĩa, kết quả cũng phụ thuộc cách xử lý interpolation. **Không suy mọi `${...}` sẽ tự được thay** khi đóng JAR.

**Không bật filtering bừa cho binary files** như PNG, JPG, certificates, keystore, font hay archive. Filtering có thể làm hỏng bytes nếu không cấu hình non-filtered extensions/phân tách filtered text resources.

### 12.6. Encoding và `Properties`

`Properties.load(InputStream)` dùng format encoding quy định bởi Java Properties API; với source UTF-8 (nhất là tiếng Việt), cách rõ ràng là:

```java
try (InputStream input =
        App.class.getResourceAsStream("/messages/app.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing config");
    }
    Properties p = new Properties();
    p.load(new InputStreamReader(
            input, java.nio.charset.StandardCharsets.UTF_8));
}
```

Đây là **fragment**, không phải method đầy đủ; code trong `App.java` mục 5.4 đã dùng reader và xử lý lỗi. Đừng sửa encoding kiểu đoán khi lỗi thật là resource không tồn tại trong JAR.

### 12.7. Filesystem path không phải classpath path

Sai ý tưởng phổ biến:

```java
new java.io.FileInputStream(
        "src/main/resources/messages/app.properties");
```

có thể chạy ở project root lúc development, nhưng sau khi copy JAR sang máy khác, folder source **không tồn tại**.

Đúng với bundled resource:

```java
App.class.getResourceAsStream("/messages/app.properties");
```

Nếu file phải được thay đổi bên ngoài deployment, thiết kế **external config path** (`-Dconfig.file=...`, env/config map) rõ ràng; đừng lẫn bundled resource với external config. Khi dùng Spring Boot, framework có thứ tự config locations/profiles riêng, cần xem docs của framework.

## 13. Runtime dependency: scope, mediation và classloader

### 13.1. Maven dependency scopes ảnh hưởng package/run

| Scope | Trong compile classpath? | Trong runtime classpath? | Điểm cần nhớ |
| --- | --- | --- | --- |
| `compile` | Có | Có | Bị cần lúc chạy nếu app thực sự gọi |
| `runtime` | Không cần cho main compilation, tùy usage | Có | Ví dụ JDBC driver qua reflection |
| `provided` | Có | **Không** theo Maven runtime classpath chuẩn | Container/JDK phải cung cấp |
| `test` | Test compile/test runtime | Không trong main runtime | Ví dụ JUnit |
| `system` | Local file path, không được Maven portable resolve | Không nên dùng | Dễ lỗi khi bàn giao |

Maven `dependency:copy-dependencies -DincludeScope=runtime` lấy runtime + compile dependencies theo semantics của plugin. Cần biết artifact deployment nào dùng `provided`, bởi một standalone JAR **không có container cung cấp thư viện**.

### 13.2. `NoClassDefFoundError` vs `ClassNotFoundException`

- `ClassNotFoundException` là checked exception khi code cố tìm class theo tên, ví dụ `Class.forName("...")`, nhưng ClassLoader không tìm được.
- `NoClassDefFoundError` là linkage error khi JVM cần định nghĩa class đã được tham chiếu/biên dịch trước đó nhưng không thể load/define tại runtime; nó còn có thể xảy ra sau lỗi class initialization.
- Hai lỗi đều có thể bắt nguồn từ thiếu dependency, sai classpath, conflict/classloader hoặc lỗi initialization, **không thể chữa bằng cùng một thao tác mặc định**.

Nếu stack trace có:

```text
Caused by: java.lang.ClassNotFoundException: org.example.Driver
```

hãy đọc chuỗi `Caused by` đầy đủ: class thiếu là app class, transitive dependency, JDBC driver hay plugin/runtime container class?

### 13.3. `NoSuchMethodError` thường là xung đột version

Giả sử compile với library `api:2.0` có method `newMethod()`, runtime lại load `api:1.0`. Class có thể tồn tại nhưng method signature không khớp, gây `NoSuchMethodError`.

Chẩn đoán:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

và kiểm tra runtime `lib/` thực tế, không chỉ POM. `dependency:tree` mô tả **resolved project graph** của Maven, nhưng JARs thật trên classpath deployment có thể bị operator đổi thủ công.

`javap` có thể đọc class signatures từ JAR, ví dụ:

```bash
javap -classpath target/packaging-diagnostics-lab-1.0.0.jar org.example.packdiag.App
```

Lệnh trên không thay Maven dependency resolution; nó chỉ giúp xác định `.class` nào có trong archive và signatures.

### 13.4. Classpath wildcard có thể gây trùng version

Nếu `lib/` có:

```text
commons-lang3-3.12.0.jar
commons-lang3-3.14.0.jar
```

một `lib/*` không có thứ tự lớp bảo đảm. Bạn có thể load phiên bản ngoài mong muốn.

Không đơn giản thêm cả hai để “chắc chắn đủ class”. Hãy giữ **một resolved runtime version được duyệt**, copy từ đúng build và verify distribution.

### 13.5. Kiểm chứng nguồn class được load

Khi cần điều tra class đến từ JAR nào trên Java 17:

```bash
java -Xlog:class+load=info -cp "target/packaging-diagnostics-lab-1.0.0.jar:target/dependency/*" org.example.packdiag.App
```

Log rất dài; tìm class `org.apache.commons.lang3.StringUtils` và source location. Chạy trong môi trường phù hợp, **không công khai log chứa private paths, repository URLs hoặc dữ liệu nội bộ**.

Đây là diagnostic nâng cao, không cần cho mọi project.

## 14. Manifest `Class-Path`: cách chạy thin JAR bằng `java -jar`

Một lựa chọn khác với explicit `-cp` là để manifest liệt kê relative dependency JARs.

Một fragment JAR Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.5.1</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>org.example.packdiag.App</mainClass>
                <addClasspath>true</addClasspath>
                <classpathPrefix>lib/</classpathPrefix>
            </manifest>
        </archive>
    </configuration>
</plugin>
```

Khi Maven Archiver có runtime dependency metadata, manifest có thể chứa:

```text
Main-Class: org.example.packdiag.App
Class-Path: lib/commons-lang3-3.14.0.jar
```

**Lưu ý:** đây là **fragment cấu hình thay thế cho JAR Plugin trong POM**, không được đưa thêm vào như một plugin trùng lặp. Java JAR Specification quy định `Class-Path` entries là relative URLs theo vị trí JAR; không phải GAV Maven.

### 14.1. Layout cần nhất quán

Nếu tạo distribution:

```text
dist/
├── app.jar
└── lib/
    └── commons-lang3-3.14.0.jar
```

thì `java -jar dist/app.jar` có thể resolve `lib/commons-lang3-3.14.0.jar` thông qua manifest khi tên/path chính xác.

Đừng để manifest chỉ tới `lib/` nhưng lại copy dependencies vào `target/dependency` hoặc đặt cả ZIP distribution ở nơi khác mà không giữ cấu trúc.

### 14.2. Không nên hardcode absolute local Maven repository path vào manifest

Ví dụ manifest sai cho bản bàn giao:

```text
Class-Path: C:\Users\developer\.m2\repository\...
```

Nó phụ thuộc máy developer, không portable, và không đúng mô hình relative JAR Class-Path được Java specification khuyến nghị/giới hạn.

**Không lấy đường dẫn cache `~/.m2` làm hợp đồng runtime distribution.**

### 14.3. Khác biệt `Class-Path` với JVM `-cp`

- Manifest `Class-Path`: khai báo các dependencies tương đối với context JAR, dùng khi Java launcher/JAR classpath resolution xem xét manifest.
- JVM `-cp`: do launch script chỉ định rõ trên command line, dùng khi gọi main class trực tiếp.
- Khi dùng `java -jar`, không kỳ vọng `-cp` trên cùng invocation bổ sung classpath như khi gọi direct class.
- Khi dùng Java module path (`--module-path`), cần tư duy module resolution riêng; không gộp vô hạn `-cp` và `--module-path` để đoán.

## 15. WAR/container applications và provided dependencies

Không phải project Java nào cũng phát hành executable JAR. Với:

```xml
<packaging>war</packaging>
```

Maven WAR Plugin đóng gói web application với layout kiểu:

```text
WEB-INF/classes/
WEB-INF/lib/
WEB-INF/web.xml (khi ứng dụng/version cần)
```

`src/main/resources` thường đi vào `WEB-INF/classes` qua output classes, còn runtime dependencies được đóng vào WAR theo scope/rules của WAR plugin.

Một dependency khai báo:

```xml
<scope>provided</scope>
```

nghĩa là Maven cho phép compile nhưng **không xem đó là dependency runtime được đóng gói thông thường**. Điều này phù hợp khi application server/container thật cung cấp API/library đó.

**Sai lầm:** dùng `provided` với Commons Lang khi deploy dưới standalone Java launcher không có container, rồi hỏi vì sao `NoClassDefFoundError`.

### 15.1. Spring Boot executable archives là trường hợp riêng

Spring Boot Maven Plugin có goal repackage tạo executable JAR/WAR với cấu trúc/lifecycle riêng (ví dụ `BOOT-INF/classes`, `BOOT-INF/lib` trong Boot JAR). Manifest có thể chứa bootstrap launcher làm `Main-Class` và app entry như `Start-Class` theo Boot version.

**Đừng sửa `Main-Class` của Boot JAR thành app class mà không hiểu Boot launcher/layout.** Phải xem official Spring Boot Maven Plugin docs theo version, `jar tf` thực tế và plugin execution.

### 15.2. Multi-module Maven

Một parent reactor:

```text
parent (packaging=pom)
├── core (jar)
└── application (jar, depends on core)
```

có thể compile application thành công do reactor classpath. Nhưng khi copy riêng application thin JAR sang máy khác, `core.jar` không tự được nhúng. Chọn runtime distribution đủ modules, hoặc shade/assembly/boot packaging được cấu hình đúng.

`mvn -pl :application -am verify` có thể build upstream core module, nhưng **không** đồng nghĩa application JAR đã gộp core classes.

## 16. Diagnosing duplicate resources, service descriptors và transitive libs

Một fat JAR có thể chứa nhiều dependency JARs với:

```text
META-INF/services/javax...
META-INF/services/com.example.Service
META-INF/spring.handlers
META-INF/spring.schemas
META-INF/LICENSE
```

Nếu tất cả được unpack vào một JAR mà không merge theo rules phù hợp, có thể mất providers, metadata hoặc license notices.

Một ứng dụng dùng `ServiceLoader.load(MyService.class)` có thể:

- chạy trong IDE vì từng dependency JAR giữ descriptor riêng;
- fail sau shading nếu descriptor bị mất/ghi đè;
- report `ServiceConfigurationError` hoặc không tìm thấy implementation.

### 16.1. Cách chẩn đoán

1. Xem đúng final fat JAR bằng `jar tf`.
2. Kiểm tra `META-INF/services/...` entries còn không.
3. Xem class implementation nằm trong archive chưa.
4. Kiểm tra `ServicesResourceTransformer` hoặc framework-specific transformer.
5. Nếu có relocation, bảo đảm descriptor names/content được xử lý tương ứng.
6. Kiểm tra license/notice merging theo policy, không đơn giản xóa mọi `META-INF`.

### 16.2. Dependency minimization có thể bỏ class dùng qua reflection

Shade Plugin hỗ trợ `minimizeJar` và include/exclude filters. Một class được gọi bằng reflection (`Class.forName`) hoặc service provider có thể không hiện trong static references và bị loại nếu minimization không nhận diện.

Nếu app chỉ lỗi sau dùng `minimizeJar`, thử tắt minimization trong sandbox, kiểm tra classes thực sự được load và cấu hình include/entry points theo docs. **Không dùng minimization như một “sửa lỗi” cho archive vốn đã thiếu dependency.**

### 16.3. Conflicting transitive dependencies

Maven dependency mediation có thể chọn một version trong graph; một fat JAR còn có thể gặp duplicate class definitions khi gom nhiều inputs. Dùng:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

rồi kiểm tra runtime archive. Không xử lý `NoSuchMethodError` chỉ bằng cách đổi random version cho đến khi app chạy; phải hiểu **API binary compatibility** và chọn version được kiểm thử.

## 17. `clean` hữu ích cho chẩn đoán, nhưng không thay việc kiểm tra

Khi xóa source Java hoặc resources, file đã được compile/copy từ run trước có thể vẫn tồn tại ở `target/classes`. Một lần `mvn package` không clean có thể đóng gói lại file cũ, che sự thật source đã thiếu.

Với bài lab cần tái hiện chắc chắn:

```bash
mvn -B clean verify
```

giúp xóa build output cũ trước khi compile/resources/package. **Không** phải vì Maven luôn sai incremental; đây là bước cách ly trạng thái khi chẩn đoán.

### 17.1. Quy trình điều tra output cũ

```text
Source hiện có? 
  |
target/classes chứa class/resource?
  |
target/JAR chứa class/resource?
  |
CI uploaded file có digest trùng JAR mới?
```

Có thể xảy ra:

| Source | `target/classes` | JAR | Nhận xét |
| --- | --- | --- | --- |
| Có | Có | Có | Cần kiểm tiếp runtime dependencies/manifest |
| Có | Không | Không | Compile/resources/source root problem |
| Có | Có | Không | Jar Plugin/excludes/wrong artifact |
| Không | Có | Có | Có thể stale output từ build cũ |
| Có | Có | Có nhưng phiên bản cũ | Có thể deploy artifact từ run khác |

Không sửa code chỉ vì `target/classes` có class; phải so artifact mà job thật dùng.

### 17.2. `jar tf` không xác nhận JAR đủ dependency

Với thin JAR, vắng `org/apache/commons/lang3/StringUtils.class` là **đúng thiết kế**, miễn runtime classpath có Commons Lang đúng version. Với uber-JAR, vắng class khi code cần nó thường chỉ ra filters/dependencies/scope/shade configuration.

Bởi vậy kết luận luôn phụ thuộc **packaging contract**.

## 18. CI quality gate: kiểm thử trên chính artifact được bàn giao

Một release CI tốt không chỉ chạy unit tests từ `target/classes`; nó còn kiểm **binary artifact thực sự sẽ được triển khai**.

### 18.1. Quy trình cho thin JAR + libs

```text
Checkout exact Git commit
       |
mvn clean verify (JUnit tests)
       |
mvn dependency:copy-dependencies (runtime scope)
       |
Tạo dist/app.jar + dist/lib/*
       |
Kiểm manifest, class/resource entries
       |
Run app từ dist/app.jar + dist/lib/*
       |
Tính SHA-256, lưu tests và build evidence
       |
Upload chính distribution đã kiểm tra
       |
Job sau download + verify digest + smoke test
```

Lưu ý: với baseline lab không cấu hình manifest Class-Path, dùng launch script `java -cp ... org.example.packdiag.App`; nếu đổi sang `java -jar dist/app.jar`, phải cấu hình `addClasspath/classpathPrefix` và giữ layout đúng như mục 14.

### 18.2. Quy trình cho shaded JAR

```text
mvn -B -Puber clean verify
       |
ArchiveAudit kiểm App.class/resource/StringUtils.class
       |
java -jar target/packaging-diagnostics-lab-1.0.0.jar
       |
SHA-256 và lưu CI test evidence
       |
Upload exact JAR đã QA
       |
Deploy bằng digest đã phê duyệt
```

**Không build lại một JAR mới ở deploy job mà mặc định nó cùng bytes với JAR đã QA**. Nếu bắt buộc rebuild, cần so digest và tái lập nguồn inputs/toolchain.

### 18.3. Kiểm tra `jar tf` trong CI

Bằng Java 17 utility của lab:

```bash
java audit/ArchiveAudit.java target/packaging-diagnostics-lab-1.0.0.jar
```

Tool xuất boolean/manifest values nhưng **không tự exit nonzero** khi resource thiếu. Trong CI production, thêm assertions hoặc shell script kiểm failure conditions. Đừng chỉ chạy một lệnh in thông tin rồi coi đó là quality gate.

Một check phù hợp hơn là **smoke-test chạy chính packaged archive**:

```bash
java -jar target/packaging-diagnostics-lab-1.0.0.jar
```

với profile `uber`, và kiểm exact stdout/exit code phù hợp. Nếu thiếu resource/dependency/manifest, smoke-test sẽ fail theo thiết kế.

### 18.4. Một script Bash assert entries cho shaded artifact

Sau `mvn -Puber clean verify`:

```bash
set -euo pipefail
JAR="target/packaging-diagnostics-lab-1.0.0.jar"

jar tf "$JAR" | grep -Fxq "org/example/packdiag/App.class"
jar tf "$JAR" | grep -Fxq "messages/app.properties"
jar tf "$JAR" | grep -Fxq "org/apache/commons/lang3/StringUtils.class"

ACTUAL="$(java -jar "$JAR")"
test "$ACTUAL" = "Package Diagnostics | HELLO FROM RESOURCE"

echo "packaged artifact smoke test: PASS"
```

**Stdout duy nhất từ script nếu không có lỗi và các commands trước chỉ in trong substitution:**

```text
packaged artifact smoke test: PASS
```

`grep -Fxq` và `test` trả exit code khác 0 khi thiếu entry hoặc stdout không khớp; với `set -e`, script dừng. Script dùng Bash + `grep`; trên Windows có thể dùng PowerShell/JDK utility tương đương.

### 18.5. PowerShell smoke test

```powershell
$jar = ".\target\packaging-diagnostics-lab-1.0.0.jar"
$items = @(jar tf $jar)

if ($LASTEXITCODE -ne 0) {
    throw "Cannot read JAR"
}
foreach ($required in @(
    "org/example/packdiag/App.class",
    "messages/app.properties",
    "org/apache/commons/lang3/StringUtils.class"
)) {
    if ($items -notcontains $required) {
        throw "Missing JAR entry: $required"
    }
}

$output = @(java -jar $jar)
if ($LASTEXITCODE -ne 0) {
    throw "Executable JAR failed"
}
if ($output.Count -ne 1 -or
    $output[0] -ne "Package Diagnostics | HELLO FROM RESOURCE") {
    throw "Unexpected stdout"
}

Write-Output "packaged artifact smoke test: PASS"
```

Áp dụng **chỉ với shaded profile** trong lab, vì baseline thin JAR cố ý không chứa Commons Lang. Đây là sự khác biệt giữa “đúng theo packaging contract” và “đòi mọi JAR phải chứa cả thư viện”.

### 18.6. Đừng quên main JAR và published POM

Nếu phát hành Maven library, consumers dựa vào published POM để resolve dependencies. Với một thin library JAR, không có dependency class bên trong là bình thường; published POM/GAV vẫn phải khai báo dependencies cần thiết. Với shaded library, cần thiết kế POM/classifier/reduced dependency semantics có chủ đích.

Không đánh đồng **executable application distribution** với **library dependency artifact**.

## 19. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng cao | Kiểm tra và sửa |
| --- | --- | --- |
| `no main manifest attribute` | Chưa cấu hình `Main-Class` | JAR Plugin `<archive><manifest><mainClass>` hoặc framework launcher |
| `Could not find or load main class` | Sai `Main-Class` hoặc class bị loại | `ArchiveAudit`, `jar tf` và FQCN |
| Class có ở `target/classes`, không có trong JAR | Packaging exclude/wrong archive | JAR Plugin `<includes>/<excludes>`, file cuối |
| `No sources to compile` | Java ở sai source root | `src/main/java` hoặc add-source đúng |
| Thin JAR thiếu `StringUtils` | Runtime classpath chưa có Commons Lang | `copy-dependencies` + `-cp`, hoặc Shade |
| `NoClassDefFoundError` chỉ trong production | Runtime libs thiếu/phiên bản khác | So `lib/`, class load origins và digests |
| `ClassNotFoundException` khi reflection | Không có plugin/driver/provider class | Kiểm driver dependency/scope/classloader |
| `NoSuchMethodError` | Runtime version mismatch | So Maven tree và effective runtime classpath |
| Resource `getResourceAsStream` trả null | Resource path sai hoặc chưa copy | `jar tf`, `src/main/resources`, case |
| Test PASS nhưng resource thiếu ở JAR | File nằm `src/test/resources` | Chuyển sang main resources, clean verify |
| Resource trên filesystem chạy được, JAR lỗi | Dùng `FileInputStream("src/...")` | Bundled resource API hoặc external config rõ |
| Properties còn `${project...}` | Filtering không bật/sai property | Xem resource filtering, nội dung thực |
| Resource binary hỏng sau build | Filtering áp lên binary | Tách filtered text/binary |
| `java -cp` PASS, `java -jar` FAIL | Manifest hoặc classpath khác | So entry point và dependencies |
| `Class-Path` manifest trỏ `lib/`, không thấy JAR | Filesystem layout không khớp | Copy libs đúng relative path |
| `jar tf` không đọc được | File corrupt/sai format/tải thiếu | Check hash, lấy artifact từ nguồn đúng |
| Fat JAR chạy nhưng ServiceLoader fail | Service descriptors mất khi shade | `ServicesResourceTransformer` |
| Shade minimization loại class | Reflection/dynamic loading | Kiểm minimize filters/entry points |
| `Invalid signature file digest` sau shade | Signature metadata của input JAR không còn phù hợp | Xem signing/transforms và ký final archive |
| `UnsupportedClassVersionError` | Java runtime thấp hơn compiler release | `java -version`, `maven.compiler.release` |
| Java 17 source nhưng build Java 8 | CI/toolchain chưa đúng | Kiểm Maven `java -version`, toolchains |
| Maven package PASS nhưng app JAR cũ | Lệnh chạy sai artifact hoặc cache target | Clean verify, compare SHA/entries |
| CI deploy original jar thay shaded jar | File selection/glob sai | Chỉ upload exact final file sau smoke-test |
| WAR thiếu class under WEB-INF | WAR packaging/includes/scope sai | Inspect WAR/plugin/container |
| Spring Boot JAR có Start-Class nhưng không chạy | Sai plugin/repackage/launcher | Kiểm Boot version và actual manifest |
| Module path lỗi trong JPMS app | Module descriptor/readability thay classpath | `--module-path`, `module-info`, jdeps |
| Multi-module app thiếu core | Core là runtime dependency nhưng không được distribute | Bàn giao đủ libs hoặc shade |
| CI tests xanh nhưng `java -jar` lỗi | Tests dùng classpath khác JAR | Smoke-test packaged artifact |
| App đọc file bằng relative OS path | Working directory đổi khi deploy | Bundled classpath resource hoặc explicit config |
| Cùng GAV hai JAR khác nhau | Rebuild/artifact overwrite/output cũ | So digests, release provenance |

### 19.1. Runbook 10 bước

1. **Dừng deploy** nếu binary có lỗi hoặc sai digest.
2. Chọn đúng final artifact từ CI/repository, ghi absolute path và SHA-256.
3. Chạy `jar tf` để xác nhận archive hợp lệ và entry list.
4. Đọc manifest `Main-Class` và `Class-Path` bằng `JarFile`/tool.
5. So entry point FQCN với `.class` path trong ZIP.
6. So `src/main/resources`, `target/classes`, packaged resources.
7. So Maven dependency graph với runtime `lib/`/fat-JAR classes.
8. Chạy đúng lệnh deployment từ thư mục/runtime tương ứng.
9. Nếu artifact còn stale hoặc mơ hồ, build từ checkout sạch rồi QA lại.
10. Lưu nguyên nhân và thêm binary smoke-test/assertions vào CI.

Nếu bước 3–7 thất bại, không nên chuyển sang “chữa” lỗi bằng cách bỏ kiểm thử, copy `.m2` toàn bộ, sửa ngẫu nhiên scopes hoặc chèn absolute paths vào manifest.

## 20. Những lỗi dễ gây hiểu nhầm về mặt bảo mật

### 20.1. Thiếu class không đồng nghĩa class an toàn

Nếu chọn sai dependency version, một class có thể tồn tại nhưng chứa hành vi khác. Đừng chỉ kiểm:

```text
commons-class=true
```

rồi coi dependency đáng tin. Cần approved repositories, exact versions/digests, vulnerability policy và runtime QA.

### 20.2. Embedded resources có thể lộ secrets

Nếu `src/main/resources/config.properties` chứa password/token thật, đóng gói sẽ làm lộ chúng với người đọc JAR. **Không đóng production secrets vào JAR**. Dùng secret manager, environment config hoặc protected filesystem mount; Java classpath resource nên chứa defaults/public metadata, không phải mật khẩu.

### 20.3. Signed JAR và Shade

Nếu một JAR được ký bằng `jarsigner`, việc sửa archive sau khi ký có thể làm chữ ký không còn khớp. Shading/relocation/repackaging phải hoàn tất **trước bước ký final artifact** theo policy. Maven GPG `.asc` detached signature, Java JAR signing và provenance attestation là những cơ chế khác nhau.

### 20.4. Checksum cùng kênh không phải chứng thực nguồn gốc

Một `.sha256` đặt cạnh JAR giúp phát hiện khác bytes so với giá trị kỳ vọng; nhưng nếu attacker thay được **cả JAR lẫn checksum**, hai thứ vẫn có thể tự nhất quán. Với release quan trọng, lấy expected digest từ trusted CI record/signature/attestation.

## 21. Câu hỏi tự kiểm tra

**1.** `Main-Class` là đường dẫn ZIP hay tên Java class?  
**Đáp án:** Tên class đầy đủ, ví dụ `org.example.packdiag.App`, không có `.class`.

**2.** `java -jar` có tự thêm toàn bộ Maven dependencies vào classpath không?  
**Đáp án:** Không; chỉ dựa vào packaging/runtime layout và manifest entries phù hợp.

**3.** Một JAR có `Main-Class` nhưng thiếu Commons Lang thì lỗi thuộc loại nào?  
**Đáp án:** Thiếu runtime dependency, không nhất thiết là manifest sai.

**4.** Vì sao JUnit PASS nhưng `java -jar` thin JAR fail?  
**Đáp án:** Test classpath có compile/test dependencies; thin JAR runtime classpath có thể không có.

**5.** Khi `java -cp ... App` chạy nhưng `java -jar app.jar` fail, cần xem gì?  
**Đáp án:** Manifest `Main-Class` và cách runtime dependencies được cung cấp.

**6.** `jar tf` dùng làm gì?  
**Đáp án:** Liệt kê entries của packaged JAR.

**7.** `target/classes` có App.class chứng minh JAR có App.class chưa?  
**Đáp án:** Chưa. Cần kiểm archive sau phase package.

**8.** Main resource mặc định đặt ở đâu?  
**Đáp án:** `src/main/resources`.

**9.** Test resource mặc định đặt ở đâu?  
**Đáp án:** `src/test/resources`; không tự vào main JAR.

**10.** Vì sao resource test-scope có thể che lỗi JAR?  
**Đáp án:** Test classpath có nó, packaged main JAR lại không.

**11.** `App.class.getResourceAsStream("/messages/app.properties")` tìm từ đâu?  
**Đáp án:** Classpath root.

**12.** Bỏ dấu `/` trước name ở `Class.getResourceAsStream` sẽ như thế nào?  
**Đáp án:** Tìm tương đối với package của App.

**13.** `ClassLoader.getResourceAsStream` dùng resource name bắt đầu bằng `/` không?  
**Đáp án:** Thường dùng tên từ classpath root không có leading slash.

**14.** `StringUtils.class` có trong thin JAR mặc định của ví dụ không?  
**Đáp án:** Không; nó đến từ compile dependency JAR riêng.

**15.** `StringUtils.class` có trong shaded JAR sau `-Puber` không?  
**Đáp án:** Có trong ví dụ khi Shade hoàn tất và không filter/relocate.

**16.** Dùng command nào copy runtime dependencies vào `target/dependency`?  
**Đáp án:** Dependency Plugin `copy-dependencies` với `includeScope=runtime`.

**17.** `includeScope=runtime` có cần copy JUnit test dependencies không?  
**Đáp án:** Không theo semantics scope filter của plugin.

**18.** Một manifest `Class-Path: lib/foo.jar` tìm file ở đâu?  
**Đáp án:** Relative với containing JAR theo Java specification.

**19.** `lib/*` trong JVM classpath có tìm đệ quy mọi subfolder không?  
**Đáp án:** Không; nó chỉ expand JAR files trong chính directory ấy.

**20.** `NoClassDefFoundError` và `ClassNotFoundException` có giống hoàn toàn không?  
**Đáp án:** Không; một là linkage error, một là checked exception từ tìm class chủ động.

**21.** `NoSuchMethodError` thường gợi ý điều gì?  
**Đáp án:** Runtime binary incompatibility/version mismatch.

**22.** `Properties.load(InputStream)` và `load(Reader)` khác gì về encoding?  
**Đáp án:** `load(Reader)` dùng charset của Reader; InputStream overload có convention ISO-8859-1.

**23.** Shade Plugin có tự sửa mọi ServiceLoader resource không?  
**Đáp án:** Không; thường cần `ServicesResourceTransformer` nếu service descriptors phải merge.

**24.** Vì sao phải inspect final JAR sau Shade?  
**Đáp án:** Có thể có original/attached JAR khác, output name và filters khác.

**25.** `UnsupportedClassVersionError` thường liên quan gì?  
**Đáp án:** Classfile version cao hơn mức Java runtime hỗ trợ.

**26.** `java -cp` có dùng manifest `Main-Class` để chọn entry point không?  
**Đáp án:** Không khi bạn ghi FQCN trực tiếp.

**27.** `jar tf` PASS chứng minh app chạy đúng chưa?  
**Đáp án:** Chưa; còn dependencies, resources, manifest semantics và runtime behavior.

**28.** Một fat JAR có thể hỏng service descriptors không?  
**Đáp án:** Có nếu các providers/descriptors trùng không merge đúng.

**29.** Một Spring Boot executable JAR có manifest khác vanilla Jar Plugin không?  
**Đáp án:** Có thể; Boot launcher và `Start-Class` do Boot plugin/version quyết định.

**30.** Smoke-test quan trọng nhất cho executable JAR là gì?  
**Đáp án:** Chạy **chính final JAR đã package** trong runtime gần giống production và kiểm exit code/stdout/evidence.

**31.** Vì sao không nên copy cả `.m2` vào `lib/`?  
**Đáp án:** Vì chứa nhiều versions/plugins/tests không liên quan, có thể gây classpath conflict.

**32.** Có nên để password thật trong `src/main/resources`?  
**Đáp án:** Không; resource bị đóng gói và có thể được đọc từ JAR.

## 22. Checklist trước khi bàn giao Java artifact

- [ ] Xác định đúng file main/thin/shaded/WAR/boot JAR mà deployment cần.
- [ ] Build từ checkout phù hợp bằng `mvn clean verify` khi QA release.
- [ ] Unit tests chạy thật; kiểm Surefire XML và test count.
- [ ] Main class có trong `target/classes` rồi trong final JAR.
- [ ] Manifest có `Main-Class` đúng FQCN nếu dùng `java -jar`.
- [ ] Nếu dùng manifest `Class-Path`, tất cả relative libs/paths tồn tại.
- [ ] Dependencies runtime có đúng scopes/versions; không copy bừa test libraries.
- [ ] Phân biệt `provided` dependency và runtime do container cung cấp.
- [ ] `src/main/resources` chứa resources production cần.
- [ ] Resource paths/case và `ClassLoader` API phù hợp.
- [ ] Mọi file cấu hình bundled cần có trong packaged output.
- [ ] Không vô tình chỉ có resource ở `src/test/resources`.
- [ ] Filtering/encoding không làm hỏng properties/binary assets.
- [ ] Khi Shade, runtime classes và service descriptors được merge đúng.
- [ ] Không nhầm original JAR với final shaded artifact.
- [ ] Không bật minimization khi chưa kiểm reflection/service providers.
- [ ] Không giữ outdated `.class`/resource từ build cũ trong `target`.
- [ ] `java -jar` hoặc launch script thật được smoke-test trên final file.
- [ ] CI kiểm tra exit code, stdout hoặc health endpoint theo policy.
- [ ] Tính SHA-256 của file cuối và đối chiếu sau upload/download.
- [ ] Nếu ký artifact, ký **sau** mọi bước repackage/shade.
- [ ] Không đóng secrets/private keys vào resources.
- [ ] Có run record Git SHA, Maven GAV, JDK/toolchain và artifact digest.
- [ ] Có lỗi nào phải dừng deploy thì CI fail thay vì chỉ in warning.
- [ ] Multi-module bàn giao đủ runtime dependencies/other modules cần thiết.
- [ ] Có regression test cho nguyên nhân đóng gói thiếu file từng gặp.

## 23. Tài liệu chính thức

1. [Apache Maven JAR Plugin — Manifest Customization](https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html) — `Main-Class`, `Class-Path`, Maven Archiver.
2. [Apache Maven JAR Plugin — Executable JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/executable-jar.html) — entry point và runtime dependencies.
3. [Apache Maven JAR Plugin — jar:jar](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html) — archive includes/excludes, classes output.
4. [Apache Maven Resources Plugin — Resource Directories](https://maven.apache.org/plugins/maven-resources-plugin/examples/resource-directory.html) — mặc định `src/main/resources`, custom resource roots.
5. [Apache Maven Resources Plugin — Includes and Excludes](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html) — filters paths.
6. [Apache Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html) — property interpolation.
7. [Apache Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html) — `includeScope=runtime` và outputDirectory.
8. [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — inspect resolved dependency graph.
9. [Apache Maven Shade Plugin 3.6.2 — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html) — ManifestResourceTransformer.
10. [Apache Maven Shade Plugin — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html) — ServicesResourceTransformer và metadata.
11. [Apache Maven Shade Plugin — shade:shade](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html) — attached artifact, minimization, filters.
12. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — compile/resources/test/package/verify.
13. [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — transitive dependencies/scopes/mediation.
14. [Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — `-jar`, `-cp`, classpath wildcard.
15. [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html) — manifest, main class, `Class-Path`.
16. [Java SE 17 — JarFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html) — inspect JAR entries/manifest.
17. [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `getResourceAsStream`.
18. [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — resource lookup và class loading.
19. [Java SE 17 — Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) — load với InputStream/Reader.
20. [Apache Maven WAR Plugin — Overview](https://maven.apache.org/plugins/maven-war-plugin/) — WAR packaging cho web applications.

**Kết luận:** Đừng coi `BUILD SUCCESS` là chứng cứ ứng dụng JAR đã runnable. **Đọc archive thật**: `Main-Class` có đúng, class của chính app có trong JAR, resource path có khớp, và dependencies có đúng trong classpath/uber-JAR không. **Thin JAR không chứa thư viện là bình thường nếu phân phối đúng `lib/`**; **shaded JAR phải gom đúng runtime classes/resources**. Unit tests và IDE có classpath khác deployment, nên release luôn cần **smoke-test final artifact, kiểm đúng bytes và chặn deploy khi không đạt**.
