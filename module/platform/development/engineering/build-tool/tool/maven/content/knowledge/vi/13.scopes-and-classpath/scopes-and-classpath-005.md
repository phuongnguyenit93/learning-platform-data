# Maven scope test và sự tách biệt phụ thuộc dành cho kiểm thử

## 1. Mục tiêu: chỉ mang thư viện kiểm thử tới nơi cần kiểm thử

Trong dự án Java, có những thư viện tham gia trực tiếp vào chức năng ứng dụng, ví dụ Commons Lang, JDBC driver hoặc HTTP client. Cũng có những thư viện chỉ cần để **biên dịch và chạy mã kiểm thử**: JUnit Jupiter, AssertJ, Mockito và những công cụ tạo dữ liệu thử. Maven hỗ trợ phân biệt chúng qua **dependency scope**.

Khi khai báo một dependency với `<scope>test</scope>`, bạn đang nói với Maven rằng thư viện này phục vụ **mã kiểm thử**, không phải mã ứng dụng thông thường. Điều đó giúp:

- Mã chính không vô tình dựa vào API của JUnit/Mockito khi biên dịch.
- Thư viện chỉ dành cho test không tự trở thành dependency runtime của artifact được xuất bản theo cơ chế Maven thông thường.
- Test có đủ công cụ để kiểm tra mã chính, còn quá trình đóng gói mặc định không cho mã test và thư viện test vào JAR ứng dụng.
- Người bảo trì hiểu ranh giới giữa **production code** và **test code** chỉ từ POM và cấu trúc thư mục.

**Điểm cốt lõi:** scope không có nghĩa Maven “không tải” dependency. Maven vẫn tải thư viện test khi cần biên dịch hoặc chạy test; nó **chỉ giới hạn classpath và quan hệ phụ thuộc** theo lifecycle và cách tiêu thụ artifact.

```text
pom.xml
  |
  +-- commons-lang3    [compile, mac dinh]
  +-- junit-jupiter    [test]
  +-- assertj-core     [test]
  |
  +--------------------+-----------------------+
  |                    |                       |
  v                    v                       v
main compile         test compile           test execution
  |                    |                       |
src/main/java      src/test/java         JUnit/Surefire
  |                    |                       |
commons-lang3     main classes + test   main + test classes
                  dependencies           + test dependencies
  |
  v
package jar (mac dinh)
  -> class/resource cua main
  -> khong dong kem JUnit, AssertJ hoac test classes
```

Sơ đồ là mô hình khái niệm của Maven với packaging `jar` chuẩn, không phải sơ đồ nội bộ cho mọi plugin. Các plugin như Shade/Assembly hoặc cấu hình test JAR chuyên biệt có thể làm đầu ra khác đi; cần xét cấu hình thực tế.

## 2. Maven có những classpath nào?

**Classpath** là tập những thư mục và JAR mà công cụ biên dịch hoặc JVM nhìn thấy trong một thao tác cụ thể. Maven quản lý các tập này thay vì yêu cầu bạn ghép bằng tay.

| Ngữ cảnh | Thường chứa | Dùng khi |
| --- | --- | --- |
| Main compile classpath | Mã/libraries cần biên dịch mã chính, gồm scope `compile` và `provided` thích hợp | `mvn compile` |
| Main runtime classpath | Mã chính và các thư viện thuộc phạm vi `compile`, `runtime` | Chạy ứng dụng qua công cụ biết dependency |
| Test compile classpath | Mã chính, mã test và dependency phục vụ biên dịch test, gồm `test` | `mvn test-compile` |
| Test runtime classpath | Lớp đã biên dịch của mã chính, mã test và các dependency cần test, gồm `test` | `mvn test` khi plugin test được cấu hình |
| Plugin classpath | Plugin Maven và dependency riêng của plugin | Khi Maven chạy compiler, Surefire, Failsafe... |

Để nhớ nhanh:

- `src/main/java` → mã sản phẩm, biên dịch vào `target/classes`.
- `src/test/java` → mã kiểm thử, biên dịch vào `target/test-classes`.
- `src/main/resources` → tài nguyên dùng cho ứng dụng, thường được sao chép vào `target/classes`.
- `src/test/resources` → tài nguyên chỉ dành cho test, thường vào `target/test-classes`.
- `target/*.jar` do Jar Plugin tạo theo chuẩn thường chứa **các lớp/tài nguyên main**, không chứa nội dung `target/test-classes`.

**Không nhầm “test classpath nhìn thấy main code” với “main code nhìn thấy test code”.** Test cần sử dụng lớp sản phẩm để kiểm tra, nhưng mã sản phẩm không nên import API chỉ có trong thư mục kiểm thử.

## 3. Khai báo scope test trong pom.xml

Một dependency chỉ dành cho test:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

Đoạn XML này phải nằm trong `<project><dependencies>...</dependencies></project>` của POM hoặc một khu vực dependency hợp lệ khác tùy mục đích. Ý nghĩa từng trường:

- `groupId`: nhóm phát hành artifact.
- `artifactId`: tên artifact.
- `version`: version cụ thể, có thể được quản lý ở `dependencyManagement` thay vì viết tại đây.
- `scope`: ở đây là `test`, giới hạn artifact đối với việc compile/run mã test và tác động tới truyền dependency.

Nếu không ghi `scope` thì mặc định là `compile`, **không phải test**. Việc để JUnit ở `compile` thường khiến các consumer của thư viện của bạn có thêm dependency không cần thiết.

Một dự án có thể có nhiều dependency test:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.17.0</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.assertj</groupId>
        <artifactId>assertj-core</artifactId>
        <version>3.26.3</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Trong bảng trên, Commons Lang thuộc `compile` mặc định vì mã chính cần nó. JUnit cung cấp API/engine kiểm thử và AssertJ cung cấp fluent assertions, nên cả hai chỉ cần cho test.

### Bảng scope để đối chiếu

| Scope | Main compile | Main runtime thông thường | Test compile/runtime | Mục đích điển hình |
| --- | --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có | API mà mã sản phẩm trực tiếp import |
| `provided` | Có | Không đưa vào runtime dependency classpath mặc định của Maven | Có | API do container/host cung cấp |
| `runtime` | Không trực tiếp | Có | Có | Implementation/driver chỉ cần lúc chạy |
| `test` | Không | Không | Có | JUnit, AssertJ, Mockito, fixture test |
| `system` | Gần với `provided`, qua file local | Không được Maven quản lý để phân phối | Tùy classpath | Không khuyến nghị |
| `import` | Không phải scope classpath thường | Không | Không | Nhập BOM kiểu `pom` trong `dependencyManagement` |

Bảng phản ánh cách xử lý dependency tiêu chuẩn của Maven, không phải khẳng định mọi đóng gói/plugin tùy biến tạo classpath y hệt. Đặc biệt, runtime của servlet container có thể cung cấp thư viện `provided`; còn `scope=test` không bao giờ là cách cấu hình API container cho ứng dụng production.

## 4. Ví dụ runnable: Java 17, Commons Lang, JUnit Jupiter và AssertJ

Để quan sát ranh giới, ta làm một ứng dụng Java nhỏ mà **mã chính chỉ import thư viện compile**, trong khi **mã test import JUnit và AssertJ**.

Cấu trúc:

```text
test-scope-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/example/
    │       ├── NameFormatter.java
    │       └── App.java
    └── test/
        └── java/dev/example/
            └── NameFormatterTest.java
```

### 4.1. POM hoàn chỉnh

Tạo `pom.xml` ở thư mục `test-scope-demo`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>test-scope-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- Main code uses Commons Lang -->
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>

        <!-- Only test code needs JUnit -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>

        <!-- Only test code needs AssertJ -->
        <dependency>
            <groupId>org.assertj</groupId>
            <artifactId>assertj-core</artifactId>
            <version>3.26.3</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ở đây `dependencies` (các thư viện dự án cần) **khác** `build/plugins` (các công cụ Maven dùng để biên dịch, test, chạy ví dụ). Surefire Plugin là công cụ chạy test; nó không thay thế việc khai báo JUnit Jupiter trong `dependencies`. Maven và plugin có cơ chế phân giải dependency riêng cho plugin, nhưng những artifact ấy không tự xuất hiện trên classpath ứng dụng.

### 4.2. Mã chính không import framework kiểm thử

Tạo `src/main/java/dev/example/NameFormatter.java`:

```java
package dev.example;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class NameFormatter {
    private NameFormatter() {
    }

    public static String displayName(String input) {
        if (StringUtils.isBlank(input)) {
            return "Khách";
        }
        String normalized = input.strip().toLowerCase(Locale.ROOT);
        return StringUtils.capitalize(normalized);
    }
}
```

Tạo `src/main/java/dev/example/App.java`:

```java
package dev.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(
                "Xin chào, " + NameFormatter.displayName("  mAVeN  ") + "!");
    }
}
```

Mã chính chỉ dùng API Java 17 và `org.apache.commons.lang3.StringUtils` từ Commons Lang. Không import `org.junit.jupiter.api.*` hoặc `org.assertj.core.api.*` ở lớp main. Điều này giữ logic ứng dụng tách khỏi công cụ test.

### 4.3. Mã test sử dụng dependency test

Tạo `src/test/java/dev/example/NameFormatterTest.java`:

```java
package dev.example;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class NameFormatterTest {
    @Test
    void normalizesDisplayName() {
        assertThat(NameFormatter.displayName("  mAVeN  "))
                .isEqualTo("Maven");
    }

    @Test
    void usesFallbackForBlankInput() {
        assertThat(NameFormatter.displayName("   "))
                .isEqualTo("Khách");
    }

    @Test
    void usesFallbackForNullInput() {
        assertThat(NameFormatter.displayName(null))
                .isEqualTo("Khách");
    }
}
```

Trong tệp trên, `@Test` đến từ JUnit Jupiter và `assertThat` đến từ AssertJ. Cả hai nằm ở `scope=test` nên Maven cho mã test dùng chúng khi `test-compile`, nhưng không làm mã chính phụ thuộc vào chúng.

Ba phép thử độc lập, không gọi mạng hoặc tài nguyên ngoài. Chúng kiểm tra chuẩn hóa tên, xử lý chuỗi trắng và xử lý `null`. Hàm `StringUtils.isBlank(null)` trả về `true`; vì thế ví dụ không gây `NullPointerException` khi nhận `null`.

### 4.4. Build, test, chạy chương trình

Điều kiện: Maven 3.9.x hoặc bản tương thích, JDK 17+, terminal đứng tại `test-scope-demo`.

```bash
mvn -version
mvn clean verify
mvn -q -Dexec.mainClass=dev.example.App exec:java
```

- `mvn -version` cho biết Maven/JDK thật đang dùng.
- `mvn clean verify` chạy biên dịch chính, test, ba kiểm thử JUnit, đóng gói JAR rồi các bước verify đã cấu hình.
- Lệnh `exec:java` chạy `App.main` với classpath runtime do Maven giải quyết, gồm Commons Lang; phần lớn thư viện `scope=test` không có trong classpath runtime mặc định này.

**Stdout do chương trình Java in ra chính xác là:**

```text
Xin chào, Maven!
```

Trong lần thực thi thành công, Surefire báo **3 tests** đạt (phần trình bày log tùy phiên bản). Bạn có thể kiểm tra:

```text
target/classes/dev/example/NameFormatter.class
target/classes/dev/example/App.class
target/test-classes/dev/example/NameFormatterTest.class
target/surefire-reports/
target/test-scope-demo-1.0.0-SNAPSHOT.jar
```

Nếu lần đầu dùng các dependencies/plugins, Maven phải tải artifact phù hợp về local repository; quá trình ấy yêu cầu kết nối/repository hợp lệ. Lệnh `mvn -q` có thể vẫn in cảnh báo từ môi trường; dòng stdout trong ví dụ là phần do mã `App` tạo.

**Tại sao không chạy `java -cp target/classes dev.example.App` ngay?** Bởi khi gọi JVM trực tiếp, classpath `target/classes` không chứa Commons Lang bên ngoài. Có thể xuất hiện `NoClassDefFoundError` vì thiếu `StringUtils`. Lệnh `exec:java` giúp minh họa Maven đưa đúng runtime dependencies vào classpath; lỗi khi tự ghép classpath không chứng minh scope Maven sai.

## 5. Quan sát sự tách biệt qua các phase

Hãy so sánh những lệnh sau:

```bash
mvn clean compile
mvn test-compile
mvn test
mvn package
```

### Khi chỉ `compile`

Maven biên dịch các lớp trong `src/main/java` thành `target/classes`. Những import của mã chính phải được giải quyết bằng API Java và dependencies nằm ở **main compile classpath**. JUnit/AssertJ scope `test` không giúp mã chính compile.

Để thấy ranh giới, **đây là đoạn mã cố ý sai** nếu đặt trong `src/main/java`:

```java
// Vi du SAI khi JUnit chi duoc khai bao scope test:
import org.junit.jupiter.api.Test;

public class WrongMainClass {
    @Test
    void shouldNotLiveInMainSource() {
    }
}
```

Nó không phải chương trình độc lập cần chạy; mã được chú thích là phản ví dụ. Nếu package/path phù hợp, Java compiler vẫn không tìm được `org.junit.jupiter.api.Test` khi main compile, vì JUnit không nằm trên compile classpath. Chuyển test sang `src/test/java` thay vì nâng JUnit thành scope `compile` chỉ để sửa lỗi.

### Khi `test-compile`

Maven biên dịch `src/test/java` vào `target/test-classes`. Ở giai đoạn này nó cần class main, commons-lang3, JUnit và AssertJ. Test classes được compile thành công vì test classpath có scope `test`.

### Khi `test`

Maven đi qua các bước trước, sau đó Surefire Plugin tìm test phù hợp và chạy chúng. Test runtime classpath thường bao gồm `target/test-classes`, `target/classes` và project dependencies cần cho test. Các JUnit provider/engine liên quan được phân giải phù hợp qua Surefire/JUnit Platform.

### Khi `package`

Jar Plugin đóng gói các lớp và resources của **mã chính** vào JAR thông thường. Các file `NameFormatterTest.class` hay JUnit/AssertJ JAR không được đóng gói bên trong JAR chính theo cấu hình mẫu. Lệnh `package` **vẫn chạy test trước khi đóng gói** trong default lifecycle trừ khi có cấu hình bỏ qua hoặc thay đổi phase.

## 6. Kiểm tra nội dung JAR và dependency tree

Đừng chỉ nhìn POM rồi giả định phạm vi đã đúng; kiểm tra cả graph phụ thuộc và artifact tạo ra.

```bash
mvn dependency:tree
jar tf target/test-scope-demo-1.0.0-SNAPSHOT.jar
```

Trong `dependency:tree`, bạn sẽ thấy các dependency trực tiếp với scope, ví dụ cấu trúc thường gặp:

```text
dev.example:test-scope-demo:jar:1.0.0-SNAPSHOT
+- org.apache.commons:commons-lang3:jar:3.17.0:compile
+- org.junit.jupiter:junit-jupiter:jar:5.11.4:test
\\- org.assertj:assertj-core:jar:3.26.3:test
```

**Đây là bản rút gọn minh họa của cây**, không phải log đầy đủ: JUnit Jupiter và AssertJ có thể kéo theo những transitive dependencies, Maven sẽ hiển thị thêm theo metadata thực tế. Các ký tự nhánh và thứ tự hiển thị cũng có thể khác.

Khi đọc JAR với `jar tf` (công cụ đi cùng JDK), bạn nên tìm thấy:

```text
dev/example/App.class
dev/example/NameFormatter.class
META-INF/MANIFEST.MF
```

Thường có thêm `META-INF/maven/...` hoặc các metadata khác tùy plugin. Với POM bài tập, bạn **không nên tìm thấy** `dev/example/NameFormatterTest.class`, `org/junit/jupiter/api/Test.class` hay `org/assertj/core/api/Assertions.class` bên trong JAR chính.

Điều đó minh họa hai ý riêng:

1. **Test sources** được loại khỏi JAR chính theo layout/packaging mặc định.
2. **Dependency JARs** không tự được Jar Plugin nhúng vào JAR chính. Ngay cả Commons Lang scope `compile` cũng thường nằm ngoài JAR; chương trình runtime cần classpath phù hợp hoặc plugin đóng gói đặc biệt.

Vì vậy, “không thấy JUnit trong JAR” **chưa phải bằng chứng duy nhất** rằng JUnit scope `test`: trong JAR Maven thông thường, cả Commons Lang scope `compile` cũng không bị nhúng. Hãy kết hợp xem scope trong dependency tree và classpath thực tế.

## 7. Dependency bắc cầu của thư viện test

Khi khai báo:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

Maven có thể cần thêm các artifact bắc cầu (transitive), ví dụ JUnit Jupiter API/Engine hoặc JUnit Platform liên quan, tùy metadata POM của phiên bản đó. Tương tự, AssertJ có thể cần dependency hỗ trợ kỹ thuật bên dưới.

**Nguyên tắc:** những dependency phục vụ thư viện test có thể xuất hiện trên **test classpath** của dự án đang chạy test, nhưng không vì vậy mà tự trở thành dependency cần thiết của người tiêu thụ artifact production.

Nếu một dự án khác khai báo JAR của bạn với scope `compile`, nó thông thường **không nhận JUnit/AssertJ từ những dependency có scope `test` trong POM của bạn**. Đây là khác biệt lớn giữa `test` và `compile` trong cơ chế dependency transitivity.

```text
Dự án consumer
  |
  +-- test-scope-demo (compile)
        |
        +-- commons-lang3 (compile; có thể truyền)
        +-- junit-jupiter (test; không truyền theo đường compile)
        +-- assertj-core  (test; không truyền theo đường compile)
```

Đừng khẳng định một artifact không thể xuất hiện ở consumer chỉ vì nhánh này có scope test: consumer có thể khai báo cùng thư viện trực tiếp hoặc nhận nó qua **nhánh khác**. Khi nghi ngờ, chạy `mvn dependency:tree` ở chính dự án consumer.

### Optional không thay thế test scope

`<optional>true</optional>` thường dùng để báo với **consumer** không tự nhận một phụ thuộc bắc cầu; thư viện đang khai báo nó vẫn có thể dùng dependency đó trong main code. Trong khi đó `scope=test` quyết định dependency cần cho **giai đoạn test**. Hai khái niệm giải quyết hai nhu cầu khác nhau, không nên dùng `optional` thay `test`.

## 8. JUnit, AssertJ, Mockito: tách trách nhiệm

Các thư viện liên quan tới kiểm thử thường có vai trò khác nhau:

| Công cụ | Vai trò | Scope thường dùng |
| --- | --- | --- |
| JUnit Jupiter API/Engine | Khai báo và thực thi test trên JUnit Platform | `test` |
| AssertJ | Assertions dễ đọc (`assertThat`) | `test` |
| Mockito | Tạo mock/stub và xác minh tương tác | `test` |
| Testcontainers | Tạo môi trường tích hợp tạm thời (ví dụ database container) | `test` |
| Maven Surefire Plugin | Chạy unit test ở phase `test` | Khai báo ở `build/plugins` |
| Maven Failsafe Plugin | Chạy kiểm thử tích hợp theo các goal/phase được cấu hình | Khai báo ở `build/plugins` |

**Không nhầm Maven plugin với dependency test.** JUnit là dependency mà mã test import; Surefire là plugin Maven điều phối việc chạy test. Chỉ có Surefire mà không có JUnit engine/provider phù hợp thì không đảm bảo JUnit Jupiter tests được tìm thấy và chạy.

Tương tự, thêm Mockito vào `<dependencies>` với `scope=test` **không tự tạo test**; phải có mã kiểm thử sử dụng các API Mockito và một test runner thích hợp.

Các công cụ chạy unit test thường không cần xuất hiện trong artifact runtime. Nhưng ngoại lệ có thể có trong một sản phẩm chuyên cung cấp test tooling cho bên khác; khi đó kiến trúc artifact và scope phải được thiết kế có chủ đích, không chỉ dựa trên quy tắc chung.

## 9. Surefire và Failsafe: hai kiểu kiểm thử, cùng nguyên tắc classpath

**Maven Surefire Plugin** thường thực thi unit test ở phase `test`. **Maven Failsafe Plugin** thường được cấu hình để chạy integration test ở phase `integration-test` và xác minh kết quả ở `verify`.

Các lệnh thường gặp:

```bash
mvn test
mvn verify
```

Trong ví dụ POM ở trên, Surefire được khai báo, còn Failsafe **không được khai báo**. Vì thế chỉ gọi `mvn verify` **không tự động tạo bộ integration test của Failsafe**. Để chạy integration test theo Failsafe, bạn cần thêm plugin/executions và chuẩn bị nguồn lực liên quan.

Ví dụ **đoạn plugin cấu hình Failsafe**, đặt bên trong `<build><plugins>` của POM (không phải file POM độc lập):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Với cấu hình đúng, Maven liên kết các goal Failsafe vào phase phù hợp. Những test mang tên `*IT.java` hoặc `*ITCase.java` thường được Failsafe nhận diện theo quy ước, còn Surefire thường dùng tên `*Test.java`, `Test*.java` hoặc `*Tests.java`.

**Phạm vi test của dependencies vẫn hữu ích cho integration tests**, vì mã kiểm thử tích hợp cũng không phải dependency runtime của ứng dụng. Nhưng việc dùng test classpath không đồng nghĩa mọi integration test đều có thể chạy chỉ với unit-test JVM: database, container, service hoặc cấu hình hệ thống có thể cần được khởi tạo và dọn dẹp đúng vòng đời.

### Vì sao Failsafe có goal verify?

Failsafe được thiết kế để không làm hỏng một chuỗi teardown quan trọng bằng cách dừng quá sớm ở bước `integration-test`; goal `verify` đánh giá kết quả kiểm thử tích hợp sau các bước liên quan. Đó là lý do nên gọi `mvn verify` thay vì coi chạy riêng một goal integration-test là hoàn thành toàn bộ chất lượng build.

## 10. Khi “skip tests” thay đổi những gì?

Một nhóm thường cần phân biệt **không chạy test**, **không biên dịch test**, và **không giải quyết phụ thuộc test**. Chúng không phải một lựa chọn duy nhất.

| Tùy chọn | Tác dụng thường gặp | Điều không nên suy luận |
| --- | --- | --- |
| `mvn -DskipTests package` | Yêu cầu Surefire bỏ **thực thi** test; thường vẫn biên dịch mã test | Không có nghĩa test source và test dependencies không được xử lý |
| `mvn -Dmaven.test.skip=true package` | Bỏ qua biên dịch và chạy test với Compiler/Surefire/Failsafe tương thích | Không tự bảo đảm một artifact đã được kiểm chứng chất lượng |
| `mvn -Dtest=NameFormatterTest test` | Chạy test phù hợp tên/mẫu qua Surefire | Không tự chọn integration test của Failsafe |
| `mvn -DskipITs verify` | Bỏ qua integration test nếu Failsafe có cấu hình phù hợp | Không tương đương skip toàn bộ unit tests |

Ví dụ dùng các lệnh sau để quan sát:

```bash
mvn clean test
mvn -DskipTests clean package
mvn -Dmaven.test.skip=true clean package
mvn -Dtest=NameFormatterTest test
```

Trong quy trình CI chính, không nên mặc định bỏ test để tạo báo cáo `BUILD SUCCESS`. Một bản build không chạy kiểm thử không chứng minh test đã pass.

**Lưu ý:** Maven plugins có cách nhận property riêng. Các tùy chọn skip phía trên mô tả hành vi của bộ Maven Compiler/Surefire/Failsafe theo cấu hình thông dụng, không phải mọi plugin kiểm thử tự viết đều có cùng semantics.

## 11. Tách biệt test resource và test data

Không chỉ JAR, Maven còn tách cả tài nguyên:

```text
src/main/resources/config.properties
    -> target/classes/config.properties

src/test/resources/fixture.json
    -> target/test-classes/fixture.json
```

Dữ liệu fixture nên đặt ở `src/test/resources` để test tìm thấy, ví dụ bằng `NameFormatterTest.class.getResourceAsStream("/fixture.json")`. Mã chính ở `src/main/java` không nên phụ thuộc vào fixture chỉ tồn tại trên test classpath.

Khi Jar Plugin đóng gói JAR chính theo mặc định, tài nguyên trong `target/test-classes` **không nằm trong JAR**. Không để password/token thật trong test fixtures; ngay cả khi chúng không được đóng gói vào artifact runtime, chúng vẫn có thể bị commit vào repository hoặc in trong CI log.

### Test fixtures dùng chung giữa modules

Nếu nhiều module cần cùng dữ liệu hoặc helper kiểm thử, cân nhắc:

1. Một **module test-support** xuất bản artifact JAR thông thường và được các module khác khai báo với `<scope>test</scope>`.
2. Dùng `test-jar` đã được plugin và quy trình build cấu hình để attach/publish, với classifier/type phù hợp; chỉ dùng khi cần và hiểu giới hạn phân phối/phụ thuộc.

Không giả định các file ở `src/test/java` của module A tự xuất hiện trong module B. Muốn chia sẻ, phải có artifact hoặc cách cấp nguồn cho test rõ ràng.

## 12. dependencyManagement và BOM không tự thêm thư viện test

Trong dự án nhiều module, nên quản lý version test framework tập trung để tránh mỗi module dùng một version JUnit khác nhau.

Ví dụ **đoạn trong POM cha**:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Trong module con, khi effective POM đã nhập BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Như vậy BOM cung cấp version của artifact JUnit phù hợp, nhưng **không tự thêm `junit-jupiter`** vào module chỉ vì đã import BOM. Module vẫn phải khai báo dependency thực sự cần. `import` ở đây là một scope đặc biệt chỉ áp dụng trong `dependencyManagement` đối với artifact kiểu `pom`, không phải lựa chọn thay `test`.

Nếu module chỉ đặt `junit-jupiter` ở `dependencyManagement` mà không khai báo trong `dependencies`, các test import JUnit có thể không compile vì thư viện chưa được thêm vào classpath. Đây là lỗi khá thường gặp khi chuyển dự án sang parent POM hoặc BOM.

## 13. Xem classpath và kiểm chứng sự tách biệt

Hãy dùng kết hợp nhiều bằng chứng thay vì chỉ kiểm tra một file JAR.

### 13.1. Xem hiệu lực của POM và scope

```bash
mvn help:effective-pom
mvn dependency:tree
```

`help:effective-pom` cho biết model sau kế thừa/profile/dependencyManagement. `dependency:tree` cho biết graph thực tế với scope và những dependency bắc cầu. Hai lệnh này hữu ích nếu thư viện xuất hiện trong test nhưng thiếu ở runtime, hoặc JUnit vô tình có scope `compile`.

### 13.2. Chạy từng phase và so sánh

```bash
mvn clean compile
mvn test-compile
mvn test
```

Sau `compile`, main classes sẽ có trong `target/classes`. Sau `test-compile`, test classes sẽ có trong `target/test-classes`. Khi chạy `test`, Surefire đưa test code và libraries phù hợp vào môi trường chạy kiểm thử.

Không lấy việc `mvn test` pass làm bằng chứng tất cả dependencies của ứng dụng runtime đã được đóng vào JAR, vì Maven thường cấp các JAR đó qua classpath riêng. Cần kiểm tra đúng chế độ phân phối ứng dụng.

### 13.3. Nếu muốn xem runtime classpath

Dùng Maven Dependency Plugin hoặc một goal chạy ứng dụng được cấu hình tương ứng, thay vì tự nối tất cả JAR trong local repository vào classpath. Ví dụ từ bài thực hành:

```bash
mvn -q -Dexec.mainClass=dev.example.App exec:java
```

Exec Maven Plugin thường dùng runtime classpath theo mặc định và chạy được Commons Lang. Lệnh này không yêu cầu đưa AssertJ hay JUnit vào runtime; nếu plugin được thay cấu hình để dùng test classpath, kết quả phạm vi sẽ khác.

Nếu chạy thử một test class trực tiếp bằng `java -cp target/test-classes ...`, bạn cũng sẽ thiếu test framework và main classes trong classpath; đó không phải cách Maven Surefire được thiết kế để sử dụng.

## 14. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| `package org.junit.jupiter.api does not exist` trong `src/main/java` | Đã import JUnit ở mã chính trong khi scope là `test` | Chuyển logic test sang `src/test/java`; không nâng scope chỉ để che lỗi |
| `package org.assertj.core.api does not exist` khi compile test | Chưa khai báo AssertJ hoặc đặt sai scope/POM | Kiểm tra dependency, repository và `mvn test-compile` |
| Không chạy test dù có class test | Surefire/engine hoặc quy ước tên test không phù hợp | Kiểm tra tên file, test engine, plugin version và báo cáo |
| `mvn test` pass nhưng `java -cp target/classes ...` lỗi | Chạy JVM không có runtime dependency JAR | Chạy với classpath runtime đúng, chẳng hạn `exec:java` |
| Test framework lọt vào dependency của consumer | Khai báo JUnit với scope `compile`, hoặc một nhánh khác mang vào | Đổi về `test` nếu chỉ test; kiểm tra dependency tree ở consumer |
| `mvn -DskipTests package` vẫn compile test | `skipTests` thường chỉ bỏ thực thi test | Hiểu khác `maven.test.skip`; không dùng để chứng minh test pass |
| BOM có JUnit nhưng test không compile | `dependencyManagement` không tự thêm dependency | Thêm `junit-jupiter` vào `dependencies` với `scope=test` |
| Failsafe không chạy IT khi gọi `verify` | Chưa cấu hình Failsafe executions hoặc tên test không khớp | Thêm plugin/executions vào POM và đúng tên test |
| Dữ liệu test xuất hiện trong artifact sản phẩm | Resource hoặc plugin packaging được cấu hình sai vị trí | Đặt fixture ở `src/test/resources`, kiểm tra `jar tf` |
| Test chạy qua IDE nhưng thất bại CI | IDE tự thêm JAR, JDK/test engine khác với Maven hoặc thiếu dependency | Ưu tiên build CLI sạch, ghim versions, xem effective POM |
| Consumer không thấy test helper của module khác | `src/test/java` không tự xuất bản | Tạo test-support module hoặc test JAR phù hợp |
| Cây phụ thuộc có JUnit dù POM của mình không khai báo | Nhánh khác đưa JUnit vào theo scope nào đó | Kiểm tra graph với `dependency:tree` thay vì đoán |

Khi gặp lỗi, xác định lỗi thuộc **mã chính**, **mã test**, **plugin test**, **repository** hay **runtime classpath** rồi sửa đúng tầng. Đừng sửa bằng cách chuyển tất cả thư viện thành `compile`; điều đó phá mất ý nghĩa tách biệt scope.

## 15. Quy trình thiết kế và review dependency test

Một checklist ngắn trước khi merge thay đổi POM:

1. **Phân loại thư viện**: code trong `src/main/java` có import thư viện không? Nếu có, xem xét `compile`/`provided`/`runtime` theo nhu cầu thực tế; nếu chỉ `src/test/java` sử dụng, ưu tiên `test`.
2. **Ghim version có chủ đích**: đặt trực tiếp trong POM hoặc quản lý qua dependencyManagement/BOM. Không dựa vào version ngẫu nhiên trên máy.
3. **Ghim các plugin quan trọng**: Maven Compiler/Surefire/Failsafe theo nhu cầu; kiểm tra engine JUnit Platform và tên test.
4. **Thử từ build sạch**: `mvn clean verify`; xác nhận số test đúng, không bị bỏ qua vì cấu hình skip.
5. **Xem dependency tree**: phát hiện transitive dependencies, version conflict và library không nên có ở runtime.
6. **Xem artifact đóng gói**: `jar tf ...`; tránh đưa test fixtures hoặc class test vào JAR main.
7. **Thử cách ứng dụng thực sự chạy**: Maven exec/plugin, container hoặc classpath sản phẩm, để biết thư viện runtime có đầy đủ không.
8. **Theo dõi bảo mật và giấy phép**: công cụ test ít hiện diện trong runtime nhưng vẫn là phần mềm bên thứ ba có thể tác động tới CI, supply chain và khả năng tái lập.

Khi publish một thư viện dùng chung, cần kiểm tra POM được xuất bản: consumer không nên bị buộc kéo JUnit/AssertJ vào production chỉ vì bạn dùng chúng để kiểm thử.

## 16. Bài tập thực hành và câu hỏi kiểm tra

1. Với POM ví dụ, hãy liệt kê Commons Lang, JUnit Jupiter và AssertJ thuộc scope nào. Giải thích vì sao tên của hai dependency test không xuất hiện trong mã chính.
2. Chạy `mvn clean verify`. Kiểm tra có đúng 3 test được chạy không; tìm thư mục `target/test-classes` và `target/surefire-reports`.
3. Dùng `mvn dependency:tree` để quan sát các dependency test bắc cầu. Tại sao chúng có mặt ở môi trường test nhưng không tự truyền đến consumer của artifact production?
4. Dùng `jar tf target/test-scope-demo-1.0.0-SNAPSHOT.jar`: có `NameFormatterTest.class`, JUnit API hoặc AssertJ API không? Tại sao điều đó một mình chưa chứng minh scope của Commons Lang?
5. Trong nhánh thử nghiệm, cố ý import `org.junit.jupiter.api.Test` trong `src/main/java`. Dự đoán lỗi và giải thích vì sao không nên sửa bằng cách bỏ `<scope>test</scope>`.
6. Dùng lệnh `mvn -DskipTests clean package`, quan sát test execution và test-compile. Phân biệt việc build thành công với kiểm thử đã pass.
7. Trong POM cha, đưa JUnit BOM vào `dependencyManagement` rồi khai báo `junit-jupiter` scope test trong module. Tại sao BOM không tự tạo dependency nếu module không khai báo?
8. Nếu viết một integration test sử dụng JDBC driver và Testcontainers, hãy phân loại các dependency cần ở main runtime, test runtime và Failsafe; lưu ý không cần một môi trường database thực để giải thích phân loại.
9. Một module có test helper cần chia sẻ cho ba module khác. Hãy đề xuất kiến trúc test-support thay vì giả định các module được nhìn trực tiếp thư mục `src/test/java` của nhau.
10. Viết câu trả lời ngắn cho hai câu hỏi: “`test` scope có nghĩa thư viện không bao giờ được tải về không?” và “`mvn package` có luôn bỏ qua việc chạy test không?”. Cả hai câu trả lời đều là **không**.

## 17. Tóm tắt và nguồn tham khảo

**Tóm tắt:** `scope=test` nói rằng một dependency dành cho việc biên dịch và thực thi kiểm thử, không phải dependency runtime thông thường của ứng dụng. Phạm vi ấy bảo vệ ranh giới giữa `src/main` và `src/test`, hạn chế việc truyền JUnit/AssertJ cho consumer và giữ graph phụ thuộc dễ quản lý. Nhưng classpath, test runner và cách đóng gói là ba lớp khác nhau: kiểm chứng bằng `mvn clean verify`, `mvn dependency:tree` và `jar tf`, không chỉ nhìn tên dependency.

Tài liệu chính thức:

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
