# Lỗi biên dịch do thiếu thư viện hoặc cấu hình JDK trong Maven

## 1. Mục tiêu và phạm vi chẩn đoán

Một lệnh Maven như `mvn clean compile` có thể thất bại với các thông báo rất khác nhau:

- `package org.apache.commons.lang3 does not exist`;
- `cannot find symbol: class StringUtils`;
- `Could not resolve dependencies for project ...`;
- `invalid target release: 17` hoặc `release version 17 not supported`;
- `records are not supported in -source 11`;
- `No compiler is provided in this environment`;
- lỗi phát sinh ở `testCompile` vì thiếu JUnit/Mockito hoặc test dependency sai scope.

Các thông báo này **không cùng một nguyên nhân**. Một lỗi có thể đến từ Maven không tải được artifact, class không có trên **compile classpath**, JDK chạy Maven không đủ mới, Java source/release không tương thích, annotation processor không hoạt động, hoặc IDE/CI đang sử dụng một Maven profile khác.

Mục tiêu bài học là biết **đọc đúng giai đoạn lỗi, thu thập bằng chứng, sửa nguyên nhân nhỏ nhất và kiểm chứng lại**. Bài tập có một project Java 17 + Maven 3.x + Commons Lang + JUnit Jupiter 5 thực sự biên dịch và chạy được. Các tình huống sai được mô phỏng riêng, không biến một POM hỏng thành cấu hình chính.

Quy trình ngắn:

1. Xác định Maven dừng ở **resolve dependency/plugin**, `compile`, `testCompile`, `test` hay `package`.
2. Kiểm Maven/JDK thật sự bằng `mvn -version`, không chỉ `java -version`.
3. Xem dòng lỗi **đầu tiên có ý nghĩa** trong compiler hoặc resolver log.
4. Đọc effective POM, dependency tree, scopes và active profiles.
5. Xác nhận Java source nằm ở đúng module/source root và import đúng package.
6. Sửa cấu hình dependency hoặc compiler/JDK, không xóa cache hay thêm flags tùy tiện.
7. Chạy `clean verify` với cùng toolchain trong IDE, terminal và CI để chứng minh đã sửa.

**Không có một lệnh `mvn clean` nào tự chữa mọi lỗi biên dịch.** `clean` chỉ dọn build output; nó không cài JDK, không bổ sung một dependency chưa khai báo và không sửa POM.

## 2. Phân loại lỗi theo thời điểm Maven thất bại

| Dấu hiệu trong log | Giai đoạn | Nhóm nguyên nhân ưu tiên |
| --- | --- | --- |
| `Non-resolvable parent POM` | Xây model/effective POM | Parent không tồn tại hoặc repository/settings sai |
| `Could not resolve dependencies` | Resolve project classpath | GAV/version/repository/mirror/offline/quyền |
| `Plugin ... could not be resolved` | Resolve build plugin | Plugin GAV, pluginRepositories, mirror, network |
| `package ... does not exist` | `compiler:compile` hoặc `testCompile` | Thiếu thư viện trên đúng classpath, import/source sai |
| `cannot find symbol` | Java compiler | Sai class/method/import, version API, generated source |
| `release version 17 not supported` | Java compiler | JDK javac được dùng thấp hơn release yêu cầu |
| `invalid target release: 17` | Java compiler | Compiler/JDK/config target không hỗ trợ 17 |
| `records are not supported in -source 11` | Java compiler | Source/release 11 nhưng code dùng feature mới |
| `No compiler is provided` | Compiler invocation | Có thể chạy bằng môi trường Java thiếu JDK compiler |
| JUnit import lỗi ở `testCompile` | Compile test sources | Thiếu JUnit test dependency hoặc test source root sai |
| `NoClassDefFoundError` khi chạy | Test/runtime | Thiếu runtime classpath hoặc binary conflict; **không nhất thiết là compile error** |
| `UnsupportedClassVersionError` khi chạy | JVM class loading | Bytecode mới hơn JVM runtime |

Maven có thể in nhiều `[ERROR]` liên tiếp. **Nguyên nhân gốc** thường ở thông báo đầu tiên cho biết artifact/phase/class cụ thể. Dòng cuối `BUILD FAILURE` chỉ là kết luận; không đủ để sửa lỗi.

### 2.1. Tách Maven resolver error và Java compiler error

Ví dụ 1 — Maven chưa tải được JAR:

```text
Could not resolve dependencies for project ...
Could not find artifact org.example:missing-lib:jar:1.0.0
```

Đây là lỗi **artifact resolution**. Java compiler chưa có đủ classpath để thực hiện công việc. Cần kiểm GAV, repository và quyền; chỉ sửa import Java thường không giúp.

Ví dụ 2 — Maven chạy được compiler nhưng Java không nhìn thấy class:

```text
[ERROR] package org.apache.commons.lang3 does not exist
[ERROR] cannot find symbol
[ERROR]   symbol: variable StringUtils
```

Đây là lỗi **Java compilation**. Kiểm dependency khai báo đúng module, scope, exclusions, classpath và import; không mặc định kết luận Maven Central đang hỏng.

Ví dụ 3 — JDK không đáp ứng release:

```text
[ERROR] error: release version 17 not supported
```

Đây là dấu hiệu **compiler/JDK không hỗ trợ target**. Thêm Commons Lang không sửa được.

Những đoạn trên là **dạng thông báo minh họa**, không phải stdout cố định của mọi Maven/Compiler Plugin/JDK version.

## 3. Bằng chứng tối thiểu trước khi thay đổi POM

Từ **đúng thư mục có `pom.xml`**, chạy:

```bash
java -version
javac -version
mvn -version
mvn -B -ntp clean compile
```

Quan sát riêng:

- `java -version`: executable `java` mà shell tìm được.
- `javac -version`: executable compiler mà shell tìm được.
- **`mvn -version`**: Maven version, Java version và Java home của JVM **chạy Maven**.
- `mvn clean compile`: phase và plugin thực sự báo lỗi; cần giữ log phần đầu có `Caused by`/compiler diagnostics.

Nếu dự án có Maven Wrapper (`mvnw`, `mvnw.cmd`), ưu tiên:

```bash
./mvnw -version
./mvnw -B -ntp clean compile
```

Windows PowerShell:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean compile
```

Wrapper giúp cố định **Maven distribution** nhưng **không tự cài JDK 17**, cũng không bảo đảm IDE đang dùng cùng JDK, `settings.xml` và profiles.

### 3.1. Không suy đoán từ IDE Project SDK

IDE có thể có bốn JDK khác nhau: project SDK, JDK dùng importer, JDK chạy Maven Runner, JDK chạy native JUnit/application. Một editor tô màu code Java 17 thành công **không chứng minh** Maven Runner dùng `javac` đủ mới.

Khi Maven fail mà IDE build project được, hãy chạy **cùng Maven goal** từ IDE Maven tool window và terminal, rồi so `mvn -version`, settings/profile và effective POM.

## 4. Hiểu compile classpath và test classpath

Maven phân loại dependency bằng scope. Điều này quyết định class có được Java compiler nhìn thấy trong **main sources** và **test sources** hay không.

| Scope | `src/main/java` compile | `src/test/java` compile | Runtime của ứng dụng |
| --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có |
| `provided` | Có | Có | Không có mặc định; container/JDK phải cung cấp |
| `runtime` | Không dùng ở main compile | Có thể có trên test classpath | Có |
| `test` | **Không** | Có | Không có trong runtime production mặc định |
| `system` | Có theo file path | Có | Theo file path cục bộ; không khuyến khích |
| `import` | Không phải project classpath scope | Không | Chỉ áp dụng BOM trong `dependencyManagement` |

Một nguyên nhân rất hay gặp:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
    <scope>test</scope>
</dependency>
```

Nếu `src/main/java` import `org.apache.commons.lang3.StringUtils`, cấu hình này **sai**, vì `test` scope chỉ phục vụ test classpath. Sửa bằng cách bỏ `<scope>test</scope>` hoặc dùng `<scope>compile</scope>` khi code main thực sự cần library.

**Không thêm một dependency trực tiếp vào `src/main/java` rồi đặt test scope chỉ để vượt qua IDE.** Phải chọn scope theo nơi class được dùng.

### 4.1. Dependency management không tự đưa JAR vào classpath

Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đoạn này **chỉ quản lý version/scope metadata**. Nó không thêm Commons Lang vào dependency graph nếu không có dependency được khai báo hoặc kéo bắc cầu. Để dùng `StringUtils` trực tiếp, cần:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
```

Đoạn rút gọn trên chỉ hợp lệ nếu version được quản lý đúng từ `dependencyManagement`/BOM. Với POM độc lập không có management, phải khai báo `<version>3.14.0</version>`.

## 5. Dự án mẫu Java 17 hoàn chỉnh

Chúng ta sẽ xây một project **đang hoạt động đúng** trước, rồi dùng nó để hiểu các lỗi do thiếu thư viện hoặc JDK.

Cấu trúc:

```text
maven-compile-diagnosis/
├── pom.xml
└── src/
    ├── main/java/dev/diagnose/
    │   ├── Purchase.java
    │   ├── LabelService.java
    │   └── App.java
    └── test/java/dev/diagnose/
        └── LabelServiceTest.java
```

Điều kiện:

- **JDK 17+** có `javac`; ví dụ soạn với JDK 17.
- **Maven 3.9.x** hoặc Maven 3 tương thích plugin được pin.
- Có truy cập Maven repository/mirror để tải Commons Lang, JUnit và build plugins (hoặc local cache đã đầy đủ).
- Lệnh thực thi tại thư mục project root; không thêm module ngoài hoặc source file bí mật.

### 5.1. POM hoàn chỉnh

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.diagnose</groupId>
    <artifactId>maven-compile-diagnosis</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:

1. `maven.compiler.release=17` yêu cầu Compiler Plugin biên dịch theo Java SE release 17, cả ngôn ngữ, class-file target và các Java API được phép.
2. `commons-lang3` dùng ở **main source**, nên có compile scope mặc định.
3. `junit-jupiter` chỉ dùng ở **test source**, có test scope và không thuộc production runtime của app.
4. Surefire 3.2.5 nhận diện JUnit Jupiter 5 tests trong project mẫu.
5. `failIfNoTests=true` giúp phát hiện trường hợp test naming/config làm số test bằng 0.
6. Versions plugin được pin để IDE/CI không ngầm chọn đời plugin khác.
7. Không cần `<repositories>` nếu Maven Central/mirror đã đủ; đừng thêm repo URL vô danh để “fix” lỗi khi chưa chẩn đoán.

Các phiên bản phục vụ ví dụ tái lập, **không khẳng định là mới nhất** hoặc đã đáp ứng mọi security policy.

## 6. Purchase.java: record Java 17

Tệp `src/main/java/dev/diagnose/Purchase.java`:

```java
package dev.diagnose;

public record Purchase(String sku, long cents) {

    public Purchase {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku required");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("negative cents");
        }
    }
}
```

Đây là **Java record**, sử dụng tính năng đã chính thức có từ Java 16. `maven.compiler.release=17` cho phép compiler xử lý cú pháp record.

Khi ép compiler về Java 11 trong một phép thử độc lập, nó phải báo lỗi vì record không thuộc Java 11. Điều này giúp phân biệt **lỗi ngôn ngữ/JDK** với **lỗi thiếu dependency Commons Lang**.

`Purchase` là data carrier có hai components (`String sku`, `long cents`) và compact canonical constructor có validation. Những class khác có thể dùng accessor tự sinh `sku()` và `cents()`.

## 7. LabelService.java: mã thực sự dùng thư viện ngoài

Tệp `src/main/java/dev/diagnose/LabelService.java`:

```java
package dev.diagnose;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class LabelService {
    private LabelService() {
    }

    public static String label(Purchase purchase) {
        String sku = StringUtils.upperCase(
                StringUtils.trimToEmpty(purchase.sku()),
                Locale.ROOT);
        return "SKU " + sku + " = "
                + purchase.cents() + " cents";
    }
}
```

`StringUtils.trimToEmpty` và `StringUtils.upperCase(String,Locale)` là API của **Apache Commons Lang**, không nằm trong JDK. Nếu thiếu Commons Lang trong **compile classpath**, compiler sẽ không resolve được import:

```text
package org.apache.commons.lang3 does not exist
```

Ngược lại, `Locale` nằm trong `java.util` của JDK. **Không khai báo Maven dependency cho `java.util.Locale`**.

Lệnh Maven `compile` biên dịch Java code, gồm `Purchase` và `LabelService`; Maven tự xây project classpath từ dependencies ở POM.

## 8. App.java và kết quả mong đợi

Tệp `src/main/java/dev/diagnose/App.java`:

```java
package dev.diagnose;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        Purchase purchase = new Purchase("  tea  ", 2500);
        System.out.println(
                "MAVEN OK | " + LabelService.label(purchase));
    }
}
```

Với Commons Lang trong runtime classpath, stdout **của riêng Java application**:

```text
MAVEN OK | SKU TEA = 2500 cents
```

`App` không cần JUnit. Nó chỉ cần các class đã biên dịch của project và Commons Lang ở runtime. Nếu chạy bằng `java -cp target/classes ...` mà không đưa Commons Lang vào classpath, Java có thể ném `NoClassDefFoundError` **tại runtime** dù Maven compile đã thành công.

### 8.1. Chạy đúng classpath bằng Maven Exec Plugin

Sau `mvn clean verify`, có thể dùng goal đã pin, không cần sửa POM:

```bash
mvn -B org.codehaus.mojo:exec-maven-plugin:3.3.0:java \
  -Dexec.mainClass=dev.diagnose.App \
  -Dexec.classpathScope=runtime
```

Trên PowerShell, dùng một dòng dễ copy:

```powershell
mvn -B org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=dev.diagnose.App -Dexec.classpathScope=runtime
```

Exec Maven Plugin dùng Maven-resolved project runtime classpath, gồm Commons Lang. Console có thể có `[INFO]` từ Maven; dòng `MAVEN OK | ...` mới là stdout mà chương trình in. Nếu goal cần tải plugin lần đầu, Maven vẫn cần repository/mirror hoạt động.

Nếu muốn chạy bằng `java` thuần, phải đưa cả `target/classes` và Commons Lang JAR đúng path vào classpath (dấu phân cách `:` trên Linux/macOS, `;` trên Windows); không mặc định coi main JAR của Maven là fat JAR.

## 9. JUnit Jupiter 5: kiểm chứng chương trình và test scope

Tệp `src/test/java/dev/diagnose/LabelServiceTest.java`:

```java
package dev.diagnose;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class LabelServiceTest {

    @Test
    void formatsSku() {
        assertEquals("SKU TEA = 2500 cents",
                LabelService.label(new Purchase("  tea  ", 2500)));
    }

    @Test
    void acceptsZeroCents() {
        assertEquals("SKU BOOK = 0 cents",
                LabelService.label(new Purchase("book", 0)));
    }

    @Test
    void rejectsBlankSku() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new Purchase(" ", 100));
        assertEquals("sku required", error.getMessage());
    }

    @Test
    void rejectsNegativeCents() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new Purchase("tea", -1));
        assertEquals("negative cents", error.getMessage());
    }
}
```

Đây là **4 test methods**, kỳ vọng `Tests run: 4`, failures 0, errors 0, skipped 0. Phương thức `assertThrows` dùng test dependency JUnit ở `src/test/java`; nó không cần được thêm vào compile dependencies của production code.

Lệnh chạy đầy đủ:

```bash
mvn -B -ntp clean verify
```

Các file dự kiến:

```text
target/classes/dev/diagnose/Purchase.class
target/classes/dev/diagnose/LabelService.class
target/classes/dev/diagnose/App.class
target/test-classes/dev/diagnose/LabelServiceTest.class
target/surefire-reports/TEST-dev.diagnose.LabelServiceTest.xml
target/maven-compile-diagnosis-1.0.0.jar
```

Đây là **các đường dẫn kỳ vọng** cho project mẫu, không phải xác nhận build đã chạy trên một máy cụ thể. Nội dung `target` có thể còn những file metadata/plugin output khác.

## 10. Hướng dẫn chạy và chẩn đoán theo thứ tự

Trong project root:

```bash
mvn -version
mvn -B -ntp clean compile
mvn -B -ntp test
mvn -B -ntp verify
```

Ý nghĩa:

- `clean compile`: kiểm main sources và compile classpath trước.
- `test`: biên dịch test sources (`testCompile`) và chạy test bằng Surefire.
- `verify`: chạy lifecycle tới verify, gồm package nếu cấu hình mặc định.
- `mvn -version`: xác nhận Maven/JDK thực sự, đặc biệt khi JDK khác giữa IDE/terminal.

Nếu main compile fail, **đừng vội debug JUnit**: phase chưa đến testCompile. Nếu `compile` pass nhưng `testCompile` fail với `org.junit.jupiter.api`, tập trung test dependency/scope.

Nếu không biết Maven POM nào đang được chạy, xác nhận current directory hoặc chỉ rõ:

```bash
mvn -B -f /path/to/project/pom.xml clean compile
```

`/path/to/project/pom.xml` là path minh họa; dùng path thật, không giữ nguyên. Một build đa module có thể lỗi chỉ trong module cụ thể — xem Maven Reactor Summary và dòng `[ERROR]` kèm module name.

## 11. Trường hợp lỗi A: không khai báo dependency Commons Lang

Giả sử POM được sửa nhầm, **bỏ dependency** sau:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Khi chạy:

```bash
mvn -B -ntp clean compile
```

Java compiler có thể báo các thông điệp như:

```text
[ERROR] package org.apache.commons.lang3 does not exist
[ERROR] cannot find symbol
[ERROR]   symbol: variable StringUtils
```

**Chẩn đoán:** `LabelService.java` import một class bên ngoài JDK; POM chưa đưa đúng artifact vào compile classpath. Maven không tự đoán dependency từ tên package.

**Cách sửa:** khôi phục đoạn dependency Commons Lang trong `<dependencies>` đúng module, scope compile (hoặc không ghi scope), version từ POM/BOM hợp lệ. Chạy lại `mvn clean compile`, sau đó `mvn verify`.

Đừng copy JAR vào `src/main/java`, đừng đặt `systemPath` tuyệt đối và đừng vô hiệu compiler warnings để che lỗi.

### 11.1. Có dependency nhưng scope sai

Một POM sai khác:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
    <scope>runtime</scope>
</dependency>
```

`runtime` **không dùng ở main compile classpath**, dù library có thể có lúc chạy. Vì `LabelService` import StringUtils ngay tại compile time, phải dùng compile scope.

Nếu dependency chỉ được dùng thông qua reflection/runtime lookup mà source không import trực tiếp, `runtime` có thể hợp lý; phải dựa vào cách mã thật sử dụng artifact, không áp một scope cho tất cả tình huống.

### 11.2. `test` scope cho production code cũng sai

```xml
<scope>test</scope>
```

đưa dependency vào test compilation/execution nhưng **không vào main compile**. Vì thế bạn có thể thấy `testCompile` classpath chứa Commons Lang nhưng `compile` vẫn fail; lỗi không mâu thuẫn.

## 12. Trường hợp lỗi B: dependency có GAV/version sai hoặc không tải được

Nếu POM khai báo một tọa độ không tồn tại:

```xml
<dependency>
    <groupId>org.example.invalid</groupId>
    <artifactId>not-existing-library</artifactId>
    <version>9.9.9</version>
</dependency>
```

Maven có thể fail ở **dependency resolution** trước khi Java compiler chạy. Đây là fragment dùng để **mô phỏng lỗi trên bản thực hành riêng**, không thêm vào POM hoàn chỉnh.

Cần điều tra:

1. `groupId`, `artifactId`, `version`, `type`, `classifier` có đúng với artifact thực không?
2. Artifact thực có ở repository được cấu hình hay không?
3. Maven đang dùng mirror/proxy/repository nào từ `settings.xml`?
4. Repository yêu cầu credentials hoặc quyền truy cập?
5. Build có chạy `-o` (offline) khi cache chưa có artifact?
6. Maven có lưu cache về failed resolution và thông báo chưa retry theo update interval?
7. Artifact là release hay SNAPSHOT; remote repository có bật policy tương ứng?
8. Parent POM/BOM của dependency có resolve được hay không?

**`mvn clean` không làm remote artifact tự tồn tại.** Cũng không nên xóa toàn bộ `~/.m2` khi một tọa độ sai. Sửa GAV/repository trước, rồi dùng policy refresh có kiểm soát nếu lỗi chỉ là cached failed resolution.

### 12.1. Khác nhau giữa lỗi plugin và lỗi project dependency

Ví dụ lỗi:

```text
Plugin org.apache.maven.plugins:maven-compiler-plugin:...
could not be resolved
```

Đây là lỗi tải **Maven plugin**, không phải thiếu `<dependency>` Commons Lang. Plugins được khai báo trong `<build><plugins>` và sử dụng plugin repositories theo settings/POM. Thêm Compiler Plugin vào `<dependencies>` là **sai mô hình**.

Phân biệt rõ:

- `<dependencies>`: classpath của Java project.
- `<build><plugins>`: goals của Maven lifecycle, như compile/test/package.
- `<repositories>`: nơi lấy project dependencies.
- `<pluginRepositories>`: nơi lấy Maven plugins.
- `settings.xml` mirrors/servers/proxies có thể tác động đến cả hai theo cấu hình.

## 13. Dùng dependency:tree để tìm classpath thực tế

Lệnh với plugin version cố định:

```bash
mvn -B -ntp \
  org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Trên PowerShell một dòng:

```powershell
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Kết quả rút gọn dự kiến:

```text
dev.diagnose:maven-compile-diagnosis:jar:1.0.0
+- org.apache.commons:commons-lang3:jar:3.14.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.10.2:test
   ... JUnit transitive test artifacts ...
```

Đây là **sơ đồ tóm tắt**, không phải stdout nguyên văn. Quan sát scope và version thực sự được chọn. Với JUnit còn có nhiều transitive artifacts được plugin liệt kê.

Để lọc Commons Lang:

```bash
mvn -B -ntp \
  org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree \
  -Dincludes=org.apache.commons:commons-lang3
```

Nếu dependency bị omit/override, đọc full tree và effective POM, đặc biệt parent/BOM và active profiles. Maven có **nearest-wins** dependency mediation cho các xung đột transitive theo quy tắc của nó; cùng depth có thể phụ thuộc thứ tự khai báo. Version trong một import BOM/`dependencyManagement` có thể quản lý dependencies mà project resolve.

**Không khai báo dependency vào module A rồi mặc định module B sẽ tự có nó.** Trong Reactor, các modules có POM và dependency graph riêng; các quản lý từ parent chỉ tác động khi child thực sự kế thừa đúng POM.

### 13.1. Direct và transitive dependencies

Nếu source project **trực tiếp** import class từ artifact C nhưng C chỉ được kéo qua artifact B, build có thể đang “ăn may” dựa trên transitive dependency. Khi B đổi dependency graph, C biến mất và code bỗng fail. Maven khuyến cáo khai báo **trực tiếp** các libraries mà source dùng trực tiếp để giảm rủi ro.

### 13.2. Exclusion, optional và dependency management

Một dependency có thể không có trên classpath vì:

- `<exclusions>` loại artifact bắc cầu.
- Upstream khai báo `<optional>true</optional>`.
- `<dependencyManagement>` chọn version khác.
- Parent/BOM import version hoặc scope theo policy.
- Profile A thêm dependency nhưng profile B không.
- Project dùng `runtime` hoặc `test` scope sai so với main compile.

Không sửa các vấn đề này bằng cách thêm nhiều version của cùng JAR vào POM; xác định **tại sao effective graph không chứa artifact cần dùng**.

## 14. Dùng Help Plugin xem effective POM và active profiles

Các lệnh:

```bash
mvn -B org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn -B org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
```

Với project nhiều profiles:

```bash
mvn -B -Pdev \
  org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Dòng `-Pdev` chỉ minh họa khi project **thực sự có** profile tên `dev`; project mẫu ở phần 5 không có profile này nên không cần bật nó.

`effective-pom` cho thấy model sau inheritance, profile activation và plugin/dependency management được áp dụng. `active-profiles` cho biết profile nào đang được Maven kích hoạt trong lần gọi đó.

Kiểm thêm:

- Có nhiều `maven-compiler-plugin` declarations/executions làm cấu hình release mâu thuẫn không?
- Compiler `release`, `source`, `target` sau profile/inheritance là gì?
- Commons Lang nằm trong `<dependencies>` của đúng module không, hay chỉ trong `<dependencyManagement>`?
- Repository profile được bật trên IDE nhưng không bật trong CI?
- Parent/BOM version mà consumer/build đang dùng có được deploy không?

`help:effective-pom` **không thay dependency:tree**: một bên là project model hiệu lực, bên kia là graph dependencies đã resolve.

## 15. Cấu hình JDK: ba thứ không được nhầm

### 15.1. JVM chạy Maven

`mvn -version` in Java version và Java home của JVM chạy Maven. Maven có thể dùng `JAVA_HOME` khác executable `java` tìm được trên PATH. Vì thế `java -version` báo 17 **không bảo đảm** Maven đang chạy dưới JDK 17.

Trên Unix:

```bash
echo "$JAVA_HOME"
java -version
javac -version
mvn -version
```

PowerShell:

```powershell
$env:JAVA_HOME
java -version
javac -version
mvn -version
```

Đừng sửa `JAVA_HOME` toàn hệ thống tùy tiện nếu đang chia sẻ máy. Chọn đúng JDK cho shell/IDE/CI job theo chính sách.

### 15.2. JDK compiler thực sự

Khi không cấu hình Toolchains hoặc forked compiler khác, Maven Compiler Plugin thường dùng compiler từ JDK Maven chạy. Nhưng khi có Toolchains, `jdkToolchain`, `fork`, `executable` hoặc IDE compiler riêng, JDK được chọn để compile **có thể khác**.

Do đó, ở một dự án lớn cần xem compiler plugin logs và Toolchains configuration, không chỉ suy từ `mvn -version`.

### 15.3. JVM chạy application và tests

Bytecode Java 17 không chạy dưới JVM 11; lỗi có thể xuất hiện khi load class dù build trên JDK 17 thành công. Surefire có thể fork JVM hoặc dùng Toolchain khác; IDE native JUnit runner có thể chọn JRE riêng.

**Lỗi `UnsupportedClassVersionError` là runtime/class-loading mismatch**, không nên nhầm với lỗi `package ... does not exist` lúc compile.

## 16. `maven.compiler.release`, source và target

Trong POM mẫu:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Đối với javac JDK 9+, `--release 17` áp dụng các quy tắc Java 17: cú pháp ngôn ngữ, bytecode target và **các Java SE API của release đó**. Đây là lựa chọn tốt hơn chỉ đặt `source`/`target` khi muốn xây một artifact tương thích Java version xác định.

Hai properties cũ:

```xml
<maven.compiler.source>17</maven.compiler.source>
<maven.compiler.target>17</maven.compiler.target>
```

quản lý language level và bytecode target, nhưng **không bảo đảm** code không vô tình dùng Java library API xuất hiện ở JDK mới hơn nếu compilation diễn ra trên JDK mới. Với Maven Compiler Plugin 3.13.0 trong ví dụ, nên ưu tiên `maven.compiler.release`.

### 16.1. JDK quá cũ so với `--release`

Nếu Maven dùng javac JDK 11 nhưng cấu hình yêu cầu release 17, compiler không thể tạo Java 17 theo yêu cầu. Có thể nhận thông báo:

```text
release version 17 not supported
```

Cách sửa là dùng **JDK 17+ phù hợp** (hoặc toolchain 17 hợp lệ), không tự hạ `release` về 11 chỉ để build xanh nếu source/artifact contract yêu cầu Java 17.

### 16.2. Source yêu cầu tính năng ngôn ngữ mới hơn release

Project mẫu có Java `record`. Nếu **thử trên bản copy** với release 11:

```bash
mvn -B -ntp -Dmaven.compiler.release=11 clean compile
```

có thể gặp diagnostics kiểu:

```text
records are not supported in -source 11
```

Lệnh này là **negative test có chủ đích**; phải khôi phục release 17 sau đó. Thông báo chính xác tùy javac/plugin version, nhưng record không hợp lệ dưới Java 11 là nguyên tắc cố định.

### 16.3. Hạ `release` không tương đương hạ JDK

Đặt `release=11` trên JDK 17 có thể biên dịch **source chỉ dùng Java 11 language/API**, nhưng không làm Maven JVM biến thành JDK 11. Nếu project thực sự dùng Java records, phải sửa source về cấu trúc tương thích 11 hoặc giữ requirement 17.

## 17. No compiler provided: phân biệt JRE và JDK

Lỗi điển hình:

```text
No compiler is provided in this environment.
Perhaps you are running on a JRE rather than a JDK?
```

Thường liên quan môi trường chạy Maven **không có Java compiler** theo cách plugin đang tìm kiếm. Với các JDK hiện đại, cần dùng đầy đủ **JDK**, không phải runtime-only distribution thiếu compiler.

Các bước:

1. Chạy `mvn -version` để xem Java home mà Maven đang dùng.
2. Kiểm installation đó có `javac`/module `jdk.compiler` thích hợp.
3. Kiểm `JAVA_HOME`, Maven runner JRE trong IDE và Maven Toolchains.
4. Nếu dự án dùng compiler fork/executable, kiểm đường dẫn compiler được chỉ định.
5. Chạy lại `clean compile`.

**Không nhầm:** có executable `javac` trên PATH không có nghĩa Maven đã sử dụng nó. Nếu `JAVA_HOME` trỏ một runtime khác, Maven có thể chạy ở JVM thiếu compiler.

## 18. Maven Toolchains khi JDK chạy Maven khác JDK compile

Trong tổ chức, Maven có thể bắt buộc chạy trên JDK mới theo plugin requirements nhưng project cần compile bằng một JDK khác. Apache Maven Toolchains cho phép chọn **JDK được các plugin có hỗ trợ toolchain sử dụng**, độc lập với JVM chạy Maven.

Một cấu hình plugin **minh họa**, thêm vào `<build><plugins>` của POM nếu dự án có nhu cầu:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Trong `${user.home}/.m2/toolchains.xml` của máy build, một entry tương ứng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/absolute/path/to/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

`/absolute/path/to/jdk-17` **phải thay bằng đường dẫn JDK thực** trên máy, không copy nguyên. Trên Windows đường dẫn có dạng ổ đĩa/path Windows thích hợp. Maven không tải JDK 17 chỉ vì có toolchains.xml.

Đặc điểm:

- Compiler Plugin là toolchain-aware.
- Các plugin khác như Surefire có support JDK toolchain theo version và cấu hình.
- **`requireJavaVersion` của Enforcer** nếu dùng thường kiểm JVM chạy Maven, không tự coi selected compiler Toolchain là Maven JVM.
- JDK toolchain version `17` và version cụ thể `17.0.x` không phải luôn khớp khi yêu cầu chuỗi đơn; version range `[17,18)` có thể bao phủ cả.
- `toolchains.xml` thường mang absolute path theo máy và không nên commit đường dẫn cá nhân lên Git.
- `mvn -version` cho biết Maven JVM, **không nhất thiết là JDK mà Toolchains chọn cho compiler**.

### 18.1. Nếu vẫn thấy `release version 17 not supported`

Kiểm Toolchains Plugin có thực sự thực thi trước compiler không; JDK path hợp lệ không; Compiler Plugin đang dùng selected toolchain hay có cấu hình `jdkToolchain`/`executable` riêng override không. Không đoán rằng chỉ cần thêm XML fragment thì Maven chắc chắn chuyển `javac`.

## 19. Lỗi testCompile: thiếu JUnit, Mockito hoặc test source root sai

Project mẫu đặt JUnit 5 dưới:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.2</version>
    <scope>test</scope>
</dependency>
```

`src/test/java/dev/diagnose/LabelServiceTest.java` import:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
```

Nếu dependency JUnit bị bỏ hoặc sai version, lỗi có thể chỉ xuất hiện ở **`maven-compiler-plugin:testCompile`**, trong khi main `compile` hoàn toàn thành công:

```text
package org.junit.jupiter.api does not exist
cannot find symbol: class Test
```

Cách sửa là khai báo JUnit ở **test scope** đúng module. Không thêm `junit-jupiter` vào compile scope chỉ để testCompile pass nếu production code không cần nó.

### 19.1. `testCompile` và `test` không phải một bước

Maven đi qua:

```text
compile -> test-compile -> test
```

`testCompile` biên dịch test sources; Surefire `test` chạy test classes. Nếu import JUnit không resolve, Surefire chưa chạy test. `Tests run: 0` trong một log cũ không chứng minh test code mới đã chạy.

### 19.2. Hai loại cờ bỏ qua tests

- `-DskipTests`: thường **bỏ chạy tests** nhưng vẫn biên dịch test sources; nếu test code import lỗi, build vẫn có thể fail ở `testCompile`.
- `-Dmaven.test.skip=true`: bỏ **test compilation và execution** trong các plugin hỗ trợ; có thể che lỗi testCompile thay vì sửa.

Không dùng hai cờ này làm giải pháp lâu dài cho lỗi thiếu JUnit. Để xác nhận triệt để, chạy `mvn -B clean verify` **không bỏ test** và kiểm Surefire XML mới.

## 20. Sai package/import, class API khác version và source roots

Không phải mọi `cannot find symbol` đều do thiếu JAR.

### 20.1. Sai tên package/class

Source Java phải có package và đường dẫn hợp lý. Ví dụ:

```java
package dev.diagnose;
```

trong tệp:

```text
src/main/java/dev/diagnose/LabelService.java
```

Tên class `LabelService` đúng cả kiểu chữ hoa/thường. Import `org.apache.commons.lang.StringUtils` **sai** đối với Commons Lang 3; tên đúng là:

```java
import org.apache.commons.lang3.StringUtils;
```

Nếu package path sai trên máy Windows không phân biệt chữ hoa/thường, Linux CI có thể phát hiện lỗi vì filesystem case-sensitive.

### 20.2. Dùng method không có trong artifact version được resolve

Một thông báo:

```text
cannot find symbol: method someNewMethod(...)
```

có thể xảy ra dù class đã được import và JAR có mặt, vì **version thực tế thiếu method/overload**. Kiểm dependency tree và Java API documentation cho **artifact version đã chọn**, không chỉ version mà developer nghĩ đang dùng.

### 20.3. Source không được Maven compile

Default source roots:

```text
src/main/java/
src/test/java/
```

Nếu source đặt trong `source/` hoặc folder tự tạo, Maven có thể không đưa vào main compilation trừ khi POM cấu hình thêm source root hợp lệ. Một class `Helper.java` được IDE đánh dấu source root nhưng Maven CLI không biết có thể dẫn đến `cannot find symbol` từ CLI.

Giải pháp: đưa file vào layout chuẩn hoặc khai báo source roots bằng plugin được tổ chức phê duyệt; không copy các class vào `target/classes` thủ công.

### 20.4. Multi-module classpath

Một project Reactor:

```text
parent/
├── pom.xml
├── contract-api/pom.xml
└── order-service/pom.xml
```

Nếu `order-service` dùng class từ `contract-api`, cần có `<dependency>` đúng GAV/version của `contract-api` trong POM của service. `<modules>` chỉ quyết định **Reactor aggregation**, không tự thêm artifact của module A vào compile classpath module B.

Để build module cùng những project mà nó phụ thuộc trong Reactor, từ root:

```bash
mvn -B -pl :order-service -am clean verify
```

Đây là lệnh **minh họa cho một Reactor có module `order-service`**, không áp dụng cho POM đơn module của bài thực hành. Nếu bạn chỉ chạy module service bên ngoài Reactor, artifact `contract-api` phải có ở repository hoặc được install/deploy phù hợp.

## 21. Annotation processors và generated sources: class bị thiếu dù dependency có

Các công cụ như Lombok, MapStruct, QueryDSL hoặc JPA metamodel processors có thể **tạo Java source hoặc methods trong lúc compile**. Nếu compiler không chạy annotation processor:

- Annotation types có thể compile được nhưng generated class/method không xuất hiện.
- Maven CLI và IDE có thể khác cơ chế annotation processing.
- Plugin/compiler/JDK upgrade có thể thay processor discovery policy.
- `-proc:none` làm annotation processing bị vô hiệu theo cấu hình hỗ trợ.

Không thể chữa mọi lỗi `cannot find symbol` từ generated source chỉ bằng thêm thư viện vào classpath.

### 21.1. Phân biệt annotation API và processor implementation

Ví dụ một processor tạo `OrderMapperImpl` khi compile. Cần:

1. Annotation API/class processor cần thiết đúng phiên bản.
2. Processor **được kích hoạt** theo Maven Compiler Plugin configuration.
3. Generated source được tạo trong build directories do plugin quản lý.
4. Module đang build chứa interface/annotations đầu vào.
5. Compiler/JDK version tương thích processor.

Với Maven 3 và Maven Compiler Plugin 3.x, có thể cấu hình `annotationProcessorPaths` khi cần chỉ định processors. Một XML **skeleton** minh họa:

```xml
<configuration>
    <annotationProcessorPaths>
        <path>
            <groupId>org.example</groupId>
            <artifactId>example-processor</artifactId>
            <version>1.0.0</version>
        </path>
    </annotationProcessorPaths>
</configuration>
```

Những tọa độ `org.example:example-processor:1.0.0` chỉ là **cú pháp minh họa**, không khẳng định artifact này tồn tại. Không chèn vào POM runnable.

### 21.2. Lưu ý JDK 23+

Trong các JDK hiện đại, **default annotation processor discovery** được siết chặt; với JDK 23 trở lên không nên mặc định processors trên classpath sẽ được chạy tự động. Nên khai báo processor rõ ràng và theo hướng dẫn phiên bản Maven Compiler Plugin/JDK tương ứng.

Bài thực hành chính dùng **JDK 17** và **không cần annotation processor**, nên không có bước tạo source ngầm. Khi nâng JDK/plugin cho dự án thật, cần kiểm documented processor configuration thay vì bật discovery không kiểm soát.

## 22. Module system, javax/jakarta và JDK APIs đã thay đổi

Không nên coi các lỗi sau là cùng loại “thiếu dependency Commons Lang”.

### 22.1. `java.*` API thuộc JDK

Những class chuẩn như `java.util.List`, `java.time.LocalDate`, `java.io.InputStream` nằm trong Java SE modules. Không thêm Maven dependencies chỉ để dùng các API chuẩn này.

Nếu compiler không tìm thấy `java.util` hoặc báo vấn đề bootclasspath/system modules, kiểm JDK installation, compiler flags và module options — không tìm “java-util.jar”.

### 22.2. Java EE / javax chuyển sang Jakarta hoặc dependency bên ngoài JDK

Một số Java EE technologies từng được cung cấp với JDK cũ không còn nằm trong JDK 11+. Namespace Jakarta EE ở các bản mới cũng đổi từ `javax.*` sang `jakarta.*` cho nhiều APIs. Cần xác định **API generation**, dependency GAV, server/container, source imports và version framework phù hợp.

Ví dụ `javax.servlet.*` trong một dự án dùng API `jakarta.servlet.*` không chỉ là thiếu “jar servlet” chung chung; phải chọn đúng thế hệ và package. Đừng thêm cùng lúc các API container với scopes tùy tiện mà không đánh giá conflicts.

### 22.3. Java Platform Module System (JPMS)

Nếu `module-info.java` có mặt và compiler báo module không đọc được hoặc package không exported, hãy kiểm:

- `requires`/`exports` của module.
- Dependency có module name/module path hợp lệ không?
- Compiler Plugin dùng classpath hay module path trong cấu hình hiện tại?
- `--release` và JDK modules có phù hợp không?

`--add-exports`/`--add-opens` có phạm vi chuyên biệt và có thể giảm encapsulation; **không phải cách sửa mặc định** cho một import thiếu thư viện. `--add-opens` chủ yếu liên quan runtime reflective access, không giải quyết mọi compiler error.

## 23. Mismatch giữa IDE, terminal và CI

| Hạng mục | Terminal | IDE Maven Runner | CI |
| --- | --- | --- | --- |
| Maven | PATH hoặc Wrapper | Bundled/Wrapper/custom | Provisioned/Wrapper |
| JDK chạy Maven | `JAVA_HOME`/launcher | Runner JRE | CI toolchain |
| Compiler JDK | Maven JDK/toolchains | Maven runner/toolchains | Toolchain/runner |
| User settings | `~/.m2/settings.xml` hoặc `-s` | Settings file override | Secret-injected settings |
| Profiles | `-P`, activation | Checkbox/runner config | CI flags/env |
| Local repository | `~/.m2/repository` | IDE override | CI workspace cache |
| Test mechanism | Maven Surefire | Native JUnit hoặc Maven | Maven Surefire |
| POM/module | Root `pom.xml`/`-f` | Imported module | CI working directory |

Để kiểm cùng lỗi, chạy **cùng Maven goal và flags** từ IDE Maven Runner/terminal/CI:

```bash
mvn -B -ntp clean verify
```

Nếu IDE native build thành công nhưng Maven fail, không coi hai cơ chế đó là cùng một kiểm thử. Kiểm Maven home, JDK for importer/runner, settings.xml, active profile và Reload Maven Project trước khi xóa caches.

### 23.1. PATH/JAVA_HOME trên Windows

PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
Get-Command mvn
mvn -version
```

Đường dẫn `java` trên PATH có thể khác `JAVA_HOME`. Nếu có nhiều JDK, hãy đặt **JDK đã được duyệt** cho Maven Runner/shell và đóng mở IDE process phù hợp để environment mới được nhận.

### 23.2. PATH/JAVA_HOME trên Unix

```bash
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
command -v mvn
mvn -version
```

Nếu Maven Wrapper tồn tại, kiểm thêm `./mvnw -version`. Dùng `javac -version` để đối chiếu compiler trên PATH, nhưng nhớ rằng Maven Toolchains có thể chọn compiler JDK **khác**.

## 24. Một quy trình chẩn đoán có thể áp dụng ngay

**Bước 1 — chép lỗi thật:** ghi module, phase, tên file `.java`, dòng/column và thông điệp đầu tiên. Đừng chỉ chép dòng `BUILD FAILURE`.

**Bước 2 — phân loại:** resolver lỗi? Compiler báo thiếu package? `release` không hỗ trợ? Test source import thiếu? Runtime linkage?

**Bước 3 — khoanh module:** nếu Maven Reactor, nhìn Reactor Summary và dùng `-pl/-am` đúng khi cần, không tự đổi toàn bộ parent POM.

**Bước 4 — kiểm JDK và Maven:** `mvn -version`, `java -version`, `javac -version`, Toolchains/IDE Runner.

**Bước 5 — xem model và dependencies:** `help:effective-pom`, `help:active-profiles`, `dependency:tree` của **đúng module**.

**Bước 6 — kiểm source:** package/import/case sensitivity, API version, src/main/java và src/test/java, generated source/annotation processing.

**Bước 7 — sửa ít nhất:** đúng dependency GAV/scope, đúng Java release/JDK hoặc toolchain, đúng package/method; đừng trộn thêm “sửa” khác không liên quan.

**Bước 8 — chạy lại:**

```bash
mvn -B -ntp clean compile
mvn -B -ntp clean verify
```

Lệnh thứ nhất chỉ xác nhận main compile; lệnh thứ hai mới xác nhận test compile, Surefire tests và packaging theo lifecycle project.

**Bước 9 — xác minh:** `TEST-*.xml` mới, version dependencies, class/resource có trong JAR; kiểm IDE và CI với cùng parameters.

**Bước 10 — ghi nguyên nhân:** ví dụ “`commons-lang3` từng ở test scope trong module `app`; đã đổi compile scope và `clean verify` chạy 4 tests thành công”. Ghi evidence cụ thể, không dùng “Maven lỗi bí ẩn”.

## 25. Negative tests có kiểm soát cho dự án mẫu

Không thực hiện trên release branch đang dùng. Với một **bản copy riêng** của project, lần lượt thử từng tình huống và khôi phục POM nguồn sau mỗi thử nghiệm.

### 25.1. Bỏ Commons Lang khỏi `<dependencies>`

Giữ import trong `LabelService.java`; chạy:

```bash
mvn -B -ntp clean compile
```

Kỳ vọng compiler báo thiếu `org.apache.commons.lang3` hoặc không resolve `StringUtils`. Đây là lỗi **classpath**.

### 25.2. Đổi Commons Lang sang test scope

Giữ dependency nhưng thêm `<scope>test</scope>`; chạy `clean compile`. Kỳ vọng main compile fail vì class không có ở compile classpath. Khôi phục scope compile trước khi chạy lại.

### 25.3. Bỏ JUnit test dependency

Giữ main Commons Lang đúng; bỏ JUnit test dependency, chạy:

```bash
mvn -B -ntp clean test
```

Kỳ vọng `compile` main pass nhưng `testCompile` fail ở import `org.junit.jupiter.api`. Đây là **test compile classpath** lỗi, không phải lỗi JDK 17.

### 25.4. Ép Java release 11

Trên JDK 17 hỗ trợ release 11, dùng bản sao:

```bash
mvn -B -ntp -Dmaven.compiler.release=11 clean compile
```

Kỳ vọng báo Java `record` không hợp lệ ở language level 11. Đây là **source/release compatibility**. Khôi phục 17 và build lại.

### 25.5. Chọn JDK 11 để build source Java 17

Trong một CI job/terminal **được cấu hình riêng với JDK 11**, lệnh `mvn -version` sẽ cho thấy JVM Java 11. Khi POM yêu cầu release 17, lỗi có thể là `release version 17 not supported`. Không đổi biến môi trường trên máy người khác hoặc cài JDK không được duyệt chỉ để thử lỗi.

### 25.6. Thêm artifact không tồn tại

Trong một bản sao, khai báo dependency với GAV giả như `org.example.invalid:not-existing-library:9.9.9`. Maven có thể fail ở dependency resolution, không phải `package ... does not exist`. Khôi phục POM gốc sau thử nghiệm.

### 25.7. Xóa import nhưng vẫn gọi StringUtils

Nếu chỉ xóa `import org.apache.commons.lang3.StringUtils;` trong Java source mà vẫn dùng tên ngắn `StringUtils`, compiler sẽ báo `cannot find symbol` ngay cả khi dependency vẫn đúng. Đây là lỗi source/import, không phải thiếu JAR.

**Mỗi bài thử chỉ thay một biến** và sau đó khôi phục baseline để có thể quy nguyên nhân.

## 26. Vì sao không nên dùng “giải pháp nhanh” sai

| Cách làm thường gặp | Vấn đề | Cách đúng |
| --- | --- | --- |
| Copy JAR thủ công vào `src/main/java` | Không biến nó thành Maven dependency hợp lệ | Khai báo GAV/scope trong POM |
| Dùng `systemPath` tới ổ đĩa cá nhân | Không portable, phá CI và metadata transitive | Repository Maven hợp lệ |
| Bỏ JUnit bằng `maven.test.skip` | Che lỗi testCompile, không QA được | Sửa test dependency |
| Tắt compiler check | Che lỗi source/release | Chọn JDK/release phù hợp |
| Hạ target để build pass | Có thể phá API/bytecode contract | Giữ compatibility requirement |
| Thêm vô số repository URLs | Mở rủi ro supply-chain/nguồn không tin cậy | Kiểm mirror/settings có quyền |
| Xóa toàn bộ `.m2/repository` | Làm chậm/hỏng dự án khác, mất installed artifacts | Khoanh tọa độ/cache cụ thể khi có bằng chứng |
| Nâng mọi dependency lên latest | Dễ tạo API break và security uncertainty | Chọn version theo compatibility tests |
| Trộn JUnit 4/JUnit 5 imports | Class/test provider không nhất quán | Dùng API/provider đúng thế hệ |
| Chỉ chạy IDE native test | Có thể không chạy Maven lifecycle | Xác minh bằng Maven verify |
| Đổi `JAVA_HOME` nhưng không restart IDE | Runner vẫn dùng JDK cũ | Xác nhận Maven Runner JRE thực |
| Đổi `source`/`target` tùy tiện | Không kiểm API availability như release | Dùng `maven.compiler.release` phù hợp |
| Sửa `module-info.java` bằng `--add-opens` bừa | Không giải quyết classpath thiếu, giảm encapsulation | Chẩn đoán module requires/exports |
| Khai báo plugin trong dependencies | Sai loại artifact/classpath | Đặt plugin dưới `<build><plugins>` |
| Bỏ parent/BOM khi resolve lỗi | Có thể làm mất toàn bộ version management | Sửa repository/parent publication |

## 27. Checklist trước khi chốt đã sửa lỗi

- [ ] Đã xác định chính xác module, phase/goal và thông báo lỗi gốc?
- [ ] Đã phân biệt resolver failure với Java compiler diagnostics?
- [ ] Maven binary/JDK từ `mvn -version` được ghi nhận?
- [ ] JDK compiler/Toolchains/IDE runner được xác nhận khi có override?
- [ ] `maven.compiler.release` phù hợp với Java features và target runtime?
- [ ] `src/main/java` dùng đúng compile/provided dependencies?
- [ ] `src/test/java` có JUnit/Mockito dependencies ở test scope phù hợp?
- [ ] Dependencies dùng trực tiếp đã được khai báo trực tiếp, không dựa ngẫu nhiên vào transitive?
- [ ] Parent/BOM/dependencyManagement và active profiles đã được đối chiếu?
- [ ] `dependency:tree` hiển thị đúng artifact version/scope và không bị exclusion ngoài ý muốn?
- [ ] POM plugin configurations không lẫn project dependencies?
- [ ] Source package/import/case sensitivity/Java API versions đúng?
- [ ] Source roots và module dependencies đúng trong Maven, không chỉ trong IDE?
- [ ] Nếu cần generated source, annotation processor thực sự chạy trên compiler/JDK hiện dùng?
- [ ] Không sửa bằng cách tắt test, thêm systemPath hay xóa toàn bộ cache?
- [ ] `mvn -B -ntp clean compile` thành công?
- [ ] `mvn -B -ntp clean verify` chạy đủ **4 JUnit tests** của demo và package thành công?
- [ ] Có Surefire `TEST-dev.diagnose.LabelServiceTest.xml` mới, failures/errors/skipped bằng 0?
- [ ] Runtime smoke `App` in đúng `MAVEN OK | SKU TEA = 2500 cents`?
- [ ] IDE Maven Runner, terminal và CI có cùng JDK/Maven/settings/profile theo build policy?
- [ ] Đã ghi nguyên nhân và cách sửa trong báo cáo kỹ thuật, không chỉ chụp dòng BUILD SUCCESS?

**Kết luận:** khi Maven báo lỗi biên dịch, hãy **xác định lỗi thuộc dependency resolution, main/test compile classpath, source/API hay JDK/`--release`** trước. Cần `mvn -version`, Compiler Plugin release, dependency scopes, `dependency:tree`, effective POM và đúng module/source root. Với Java 17, dùng JDK compiler đủ mới hoặc Maven Toolchains phù hợp; với thư viện ngoài, khai báo đúng GAV/scope ở nơi dùng thật. Sau khi sửa, chỉ kết luận hoàn tất khi `clean verify` và bài kiểm thử/chạy thử của ứng dụng đã đạt trên môi trường mục tiêu.

### Tài liệu chính thức để kiểm chứng

- [Apache Maven Compiler Plugin — Setting the --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven Compiler Plugin — Setting source and target](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html)
- [Apache Maven Compiler Plugin — compile Goal Parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Surefire Plugin — JUnit Platform Example](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [MojoHaus Exec Maven Plugin — exec:java](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
