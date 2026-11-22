# Vì sao có thư viện khi biên dịch nhưng thiếu lúc chạy trong Maven?

## 1. Hiện tượng: compile thành công nhưng chương trình không chạy

Trong một dự án Java dùng Maven, bạn có thể gặp tình huống:

- `mvn compile` hoặc `mvn clean package` báo `BUILD SUCCESS`.
- IDE không gạch đỏ những dòng `import` của thư viện bên thứ ba.
- Kiểm thử có thể vẫn chạy và đạt.
- Nhưng khi gọi chương trình trên terminal hoặc đưa JAR sang một môi trường khác, JVM báo lỗi liên quan đến lớp của thư viện:

```text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Vì sao cùng một dự án lại “có thư viện khi biên dịch nhưng thiếu lúc chạy”?

**Biên dịch và thực thi dùng những classpath có mục đích khác nhau.** Maven có thể tải được JAR và đưa nó vào classpath của Java compiler, nhưng điều đó không có nghĩa JAR sẽ tự được nhúng vào artifact hoặc xuất hiện trên classpath của JVM lúc chạy.

Có ít nhất hai nguyên nhân cơ bản cần phân biệt:

1. **Cách khởi chạy/đóng gói thiếu thư viện runtime:** dependency được khai báo `compile` đúng, nhưng bạn chỉ chạy `java -cp target/classes ...` hoặc chuyển một JAR “mỏng” (thin JAR) sang máy khác mà không kèm những JAR bên ngoài.
2. **Phạm vi dependency không có ở runtime:** chẳng hạn `scope=provided` cho phép mã chính compile vì giả định môi trường chạy như application server/container sẽ cung cấp API/thư viện, nhưng khi chạy độc lập môi trường đó không có.

Các nguyên nhân khác gồm `scope=test` bị dùng sai, exclusion hoặc dependency bắc cầu bị thay đổi, version khác giữa build/runtime, classloader riêng của container, và cấu hình packaging/launch script.

**Quy tắc chẩn đoán:** trước khi sửa version hay scope, hãy xác định **lớp nào đang thiếu**, **classpath nào đã dùng khi compile**, **classpath nào được JVM dùng khi chạy**, và **artifact nào được đưa tới môi trường đích**.

## 2. Compile classpath khác runtime classpath như thế nào?

**Classpath** là tập đường dẫn thư mục và JAR dùng để tìm các lớp Java. Với Maven, cùng một POM có thể sinh ra các classpath khác nhau:

| Ngữ cảnh | Mục đích | Những dependency thường thấy |
| --- | --- | --- |
| Main compile classpath | Compiler giải quyết import của `src/main/java` | `compile`, `provided`, `system` |
| Main runtime classpath | JVM chạy chương trình chính | `compile` và `runtime` |
| Test compile classpath | Biên dịch `src/test/java` | Mã chính, các dependency cần cho test, kể cả `test` và `provided` phù hợp |
| Test runtime classpath | Chạy JUnit/test tools | Lớp chính, lớp test và dependencies cần để chạy test |
| Plugin classpath | Chạy goal của Maven plugin | Dependency riêng của plugin, không đồng nghĩa dependency của ứng dụng |

Bảng mô tả cách xử lý thông thường của Maven 3.x. Từng plugin, application server hoặc cách đóng gói có thể thay đổi chi tiết classloader. Quan trọng nhất là **main compile**, **main runtime** và **test** không phải cùng một tập.

Luồng điển hình:

```text
pom.xml
  |
  +-- dependency A: compile
  +-- dependency B: provided
  +-- dependency C: runtime
  +-- dependency D: test
  |
  +--> mvn compile
  |       target/classes
  |       classpath: A + B (+ system nếu có)
  |
  +--> mvn test
  |       target/test-classes
  |       classpath của test: A + B + C + D theo Maven
  |
  +--> mvn package
  |       target/app.jar
  |       JAR thường: lớp/tài nguyên chính của app,
  |       không tự nhúng JAR của A, B, C, D
  |
  +--> chạy app bằng classpath runtime đầy đủ
          A + C được cung cấp, B không tự có,
          D không dành cho runtime sản phẩm
```

**Hai loại “thiếu thư viện” khác nhau**:

- Maven đã chọn A là dependency runtime, nhưng cách bạn gọi `java` không đưa A vào classpath → lỗi **khởi chạy/phân phối**.
- Bạn khai báo B là `provided` nhưng JVM runtime thực tế không cung cấp B → lỗi **lựa chọn scope hoặc giả định môi trường**.

## 3. Hiểu ý nghĩa các Maven scope

Dependency có dạng:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
    <scope>compile</scope>
</dependency>
```

Đây là đoạn con của `<dependencies>` trong POM. Nếu bỏ hoàn toàn `<scope>`, mặc định Maven dùng `compile`.

| Scope | Có khi compile mã chính? | Có trong runtime classpath Maven thông thường? | Ý nghĩa |
| --- | --- | --- | --- |
| `compile` | Có | Có | Thư viện cần cả khi viết và chạy mã sản phẩm |
| `provided` | Có | Không được Maven tự đưa vào runtime | Môi trường đích phải cung cấp |
| `runtime` | Không trực tiếp | Có | Chỉ cần lúc chạy, ví dụ một implementation/driver |
| `test` | Không | Không | Chỉ biên dịch/chạy mã kiểm thử |
| `system` | Có bằng file JAR tại đường dẫn máy | Không được quản lý như runtime dependency thông thường | Cũ, khó tái lập, nên tránh |
| `import` | Không | Không | Chỉ nhập BOM kiểu `pom` trong `dependencyManagement` |

Trong những scope đó, **`provided` là ví dụ kinh điển** của tình huống *compile có mà runtime thiếu*. Nhưng **`compile` không bảo đảm một lệnh `java` độc lập có classpath đúng**. Maven có thể biết đường dẫn JAR mà JVM tự gọi bằng `java -cp ...` thì không.

### Trường hợp runtime có dùng để sửa lỗi không?

`runtime` được dùng khi mã chính không cần import lớp thư viện trong lúc biên dịch mà JVM cần implementation khi chạy; ví dụ một JDBC driver được nạp qua cơ chế dịch vụ và ứng dụng chỉ compile với `java.sql`. Nếu mã nguồn chính import trực tiếp `org.apache.commons.lang3.StringUtils`, chuyển Commons Lang sang `runtime` sẽ làm **compile thất bại**, không phải giải quyết vấn đề.

Với API do server cung cấp, `provided` có thể đúng; nhưng nếu ứng dụng được phân phối như một chương trình Java độc lập, thông thường bạn cần `compile` hoặc cách cung cấp thư viện lúc chạy được chứng minh rõ ràng.

## 4. Ví dụ thực hành hoàn chỉnh: dependency compile nhưng JVM trực tiếp không thấy

Ta dùng Java 17, Apache Commons Lang và JUnit Jupiter để tái hiện tình huống một cách có kiểm soát. Không cần server, container hay dịch vụ ngoài.

Cấu trúc dự án:

```text
runtime-classpath-lab/
├── pom.xml
└── src/
    ├── main/java/dev/example/
    │   ├── GreetingService.java
    │   └── App.java
    └── test/java/dev/example/
        └── GreetingServiceTest.java
```

### 4.1. POM đầy đủ

Tệp `runtime-classpath-lab/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>runtime-classpath-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- Code chính import lớp của Commons Lang -->
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>

        <!-- Chỉ dùng JUnit trong mã kiểm thử -->
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

Một số điều cần đọc đúng:

- Commons Lang có scope **`compile` mặc định**, nên Maven đưa nó vào main compile classpath và cả runtime classpath do Maven xây dựng.
- JUnit Jupiter có scope `test`, chỉ phục vụ các bài kiểm thử.
- Compiler Plugin cấu hình Java 17; Surefire chạy JUnit 5; Exec Maven Plugin cho phép chạy chương trình với classpath dependency mà Maven xác định.
- Đây là **JAR thông thường**, không có cấu hình Shade/Assembly để nhúng các JAR bên ngoài.

### 4.2. Mã sản phẩm gọi Commons Lang

Tạo `src/main/java/dev/example/GreetingService.java`:

```java
package dev.example;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class GreetingService {
    private GreetingService() {
    }

    public static String greet(String name) {
        if (StringUtils.isBlank(name)) {
            return "Xin chào, khách!";
        }
        String clean = name.strip().toLowerCase(Locale.ROOT);
        return "Xin chào, " + StringUtils.capitalize(clean) + "!";
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
        System.out.println(GreetingService.greet("  mAVeN  "));
    }
}
```

Chương trình sử dụng `StringUtils.isBlank` và `StringUtils.capitalize`, là các API của thư viện `commons-lang3`. JVM cần tìm thấy lớp `org.apache.commons.lang3.StringUtils` khi đường chạy đi đến các lệnh này.

### 4.3. Kiểm thử JUnit

Tạo `src/test/java/dev/example/GreetingServiceTest.java`:

```java
package dev.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {
    @Test
    void normalizesName() {
        assertEquals("Xin chào, Maven!",
                GreetingService.greet("  mAVeN  "));
    }

    @Test
    void blankNameUsesFallback() {
        assertEquals("Xin chào, khách!",
                GreetingService.greet("   "));
    }

    @Test
    void nullNameUsesFallback() {
        assertEquals("Xin chào, khách!",
                GreetingService.greet(null));
    }
}
```

Ba test chứng minh mã nguồn chính hoạt động khi JUnit/Surefire dùng classpath test đầy đủ. `StringUtils.isBlank(null)` trả về `true`, nên ca null không gây lỗi truy cập `name.strip()`.

### 4.4. Bước một: compile và test đều thành công

Từ thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -version
mvn clean verify
```

Khi tải dependencies/plugins được và không có lỗi, Maven biên dịch, thực thi **3 test JUnit** và tạo các tệp điển hình:

```text
target/classes/dev/example/App.class
target/classes/dev/example/GreetingService.class
target/test-classes/dev/example/GreetingServiceTest.class
target/surefire-reports/
target/runtime-classpath-lab-1.0.0-SNAPSHOT.jar
```

Maven có JAR Commons Lang trong local repository, thường ở đường dẫn:

```text
~/.m2/repository/org/apache/commons/commons-lang3/3.17.0/commons-lang3-3.17.0.jar
```

Nhưng **đừng cho rằng đường dẫn thực trên mọi máy đúng như trên**: một số dự án đặt `localRepository` trong settings, hoặc dùng `-Dmaven.repo.local`. Đường dẫn mẫu chỉ minh họa.

### 4.5. Bước hai: cố ý chạy sai classpath

Chạy lệnh sau:

```bash
java -cp target/classes dev.example.App
```

Ở đây `-cp target/classes` chỉ đưa **lớp của dự án** vào classpath JVM; không có Commons Lang. Vì `GreetingService.greet` thực sự gọi `StringUtils`, JVM sẽ không giải quyết được lớp này và chương trình kết thúc lỗi. Dấu hiệu thường gặp trên stderr:

```text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Chi tiết stack trace, dòng `Caused by` và tiền tố thông báo phụ thuộc JDK/JVM; ta **không coi toàn bộ stderr là một chuỗi cố định**. Đây là lỗi dự kiến trong bài thực hành, không phải bằng chứng POM khai báo sai.

**Phân tích:** Compiler tìm thấy Commons Lang trong compile classpath, còn lệnh `java` ở trên chỉ dùng `target/classes`. Hai classpath được cấu hình **khác nhau**, nên kết quả khác nhau dù không sửa một dòng mã nguồn.

### 4.6. Bước ba: chạy đúng qua Maven Exec Plugin

Chạy:

```bash
mvn -q -Dexec.mainClass=dev.example.App exec:java
```

Goal `exec:java` sử dụng runtime classpath của dự án theo cấu hình mặc định; nó đưa dependency `commons-lang3` scope `compile` vào môi trường chạy. **Stdout do ứng dụng tạo** là chính xác:

```text
Xin chào, Maven!
```

Có thể vẫn có log hoặc cảnh báo của Maven/launcher ngoài dòng stdout ứng dụng, tùy phiên bản và môi trường. Điểm quan sát là **cùng bytecode Java**, nhưng lần thứ hai classpath có thêm thư viện runtime.

### 4.7. Rút ra từ thí nghiệm đầu tiên

Đừng đổi Commons Lang từ `compile` sang `provided` hoặc thêm nó vào scope `test` để chữa lỗi này: **scope trong POM ban đầu đã đúng**. Điều cần sửa là phương thức khởi chạy hoặc cách phân phối thư viện.

So sánh:

| Cách gọi | Commons Lang ở runtime classpath? | Kết quả |
| --- | --- | --- |
| `mvn clean verify` | Có khi Maven chạy test; compiler cũng có thư viện | Biên dịch/test thành công |
| `java -cp target/classes dev.example.App` | Không | Có thể `NoClassDefFoundError` khi gọi `StringUtils` |
| `mvn -q -Dexec.mainClass=dev.example.App exec:java` | Có theo runtime classpath Maven | In `Xin chào, Maven!` |

## 5. Ví dụ thứ hai: scope provided cho phép compile nhưng runtime thiếu

`provided` thường dùng khi thư viện hoặc API sẽ được **môi trường runtime bên ngoài cung cấp**, chẳng hạn Servlet API trong một servlet container phù hợp. Maven đưa dependency vào compile/test classpath để mã Java biên dịch, nhưng **không tự đưa nó vào runtime classpath của dự án**.

Có thể tự tái hiện bằng chính dự án ở mục 4, không cần server:

1. Tạm thời đổi khai báo Commons Lang trong POM thành:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
    <scope>provided</scope>
</dependency>
```

2. Chạy lại:

```bash
mvn clean verify
```

Kết quả **vẫn có thể thành công, và với dự án bài thực hành phải có 3 test đạt**, bởi mã chính được compile với Commons Lang, và test classpath của Maven vẫn có dependency `provided`. Đây là một ví dụ điển hình khiến người học tưởng “test pass thì runtime chắc chắn đầy đủ”.

3. Chạy:

```bash
mvn -q -Dexec.mainClass=dev.example.App exec:java
```

Lúc này Exec Maven Plugin mặc định dùng **runtime classpath**, vốn không bao gồm dependency `provided`. Mã gọi `StringUtils` sẽ thất bại khi không có thư viện đó ở classloader runtime. Lỗi thường thuộc nhóm `NoClassDefFoundError`, và Maven có thể bọc lỗi bằng thông báo của Exec Plugin.

4. **Khôi phục scope `compile` (hoặc bỏ thẻ `<scope>`)** trong POM sau thí nghiệm, rồi chạy:

```bash
mvn clean verify
mvn -q -Dexec.mainClass=dev.example.App exec:java
```

Ứng dụng lại in:

```text
Xin chào, Maven!
```

Vậy `provided` **không phải phiên bản nhẹ hơn của `compile`**. Nó là một cam kết kỹ thuật: *hệ thống chạy chương trình sẽ cung cấp dependency này*. Nếu cam kết không đúng, lớp tồn tại lúc biên dịch nhưng vắng lúc chạy.

### 5.1. Khi nào provided là lựa chọn chính xác?

Một ứng dụng đóng gói WAR và chạy trên servlet container có thể dùng một Servlet API do container cung cấp, với scope `provided`. Khi đó việc không nhúng API vào WAR có thể đúng thiết kế, vì container đã cài đặt API ở runtime.

Tuy nhiên cần kiểm tra:

- Container thật sự cung cấp thư viện/API cần dùng không?
- Version API mà mã biên dịch có tương thích runtime container không?
- Application server có classloader riêng, ảnh hưởng gì tới thư viện không?
- Ứng dụng chạy trực tiếp bằng `java -jar`, trên IDE, hay trong container đã cấu hình?

Không nên dùng `provided` cho thư viện ứng dụng cần nhưng môi trường đích **không có**. Với thư viện bên thứ ba như Commons Lang trong chương trình command-line độc lập, mặc định `compile` thường phù hợp hơn.

## 6. JAR do Maven tạo có chứa dependencies hay không?

Với POM chuẩn `<packaging>jar</packaging>`, Jar Plugin thường đóng gói **các lớp và tài nguyên ở `target/classes`**, không tự gộp JAR của tất cả dependencies vào sản phẩm.

Quan sát:

```bash
jar tf target/runtime-classpath-lab-1.0.0-SNAPSHOT.jar
```

Với dự án mẫu, danh sách sẽ có những đường dẫn như:

```text
META-INF/MANIFEST.MF
dev/example/GreetingService.class
dev/example/App.class
```

Có thể có thêm `META-INF/maven/...` và metadata khác tùy plugin. Nhưng sẽ **không có** lớp `org/apache/commons/lang3/StringUtils.class` trong JAR thông thường. Không chứa `StringUtils.class` **không đồng nghĩa Maven chưa tải commons-lang3**.

Khái niệm thường dùng:

- **Thin JAR (JAR mỏng):** chứa code/resources của dự án, các thư viện khác cần được cung cấp riêng qua classpath.
- **Uber/Fat JAR:** đóng nhiều dependencies vào một artifact hoặc cấu trúc đóng gói chuyên biệt. Cần cấu hình plugin, xử lý các xung đột tài nguyên/metadata/service loader và có thể chịu ràng buộc giấy phép.

Một ví dụ với Maven Shade Plugin là cấu hình `maven-shade-plugin` trong POM để tạo artifact chứa các dependencies thích hợp. Nhưng chỉ thêm `<packaging>jar</packaging>` **không tạo fat JAR**. Không phải mọi thư viện đều có thể “nhét vào JAR” mà không cần xem xét cách tải class/resource và giấy phép.

### 6.1. Vì sao `java -jar` có thể lỗi theo cách khác?

`java -jar target/runtime-classpath-lab-1.0.0-SNAPSHOT.jar` có thể lỗi ngay vì JAR **không có `Main-Class` trong manifest**. Đây là một lỗi cấu hình điểm vào khác với thiếu dependency.

Ngay cả khi thêm `Main-Class: dev.example.App`, điều đó **không tự đóng Commons Lang vào JAR**. JVM dùng cơ chế classpath/manifest được cấu hình cho chế độ chạy JAR; chỉ biết điểm vào chưa đủ để tìm lớp bên ngoài.

Với bài mẫu, `exec:java` là cách đơn giản, không cần thay manifest, để chứng minh classpath do Maven phân giải hoạt động.

## 7. Sửa vấn đề classpath khi cần chạy JVM trực tiếp

Có ba chiến lược phổ biến:

1. Dùng công cụ chạy biết dependency graph như Maven Exec Plugin trong lúc phát triển.
2. Phân phối JAR chính cùng thư mục `lib/` chứa các runtime dependencies, rồi khai báo classpath đúng trong script chạy hoặc manifest khi phù hợp.
3. Cấu hình một hình thức packaging có dependencies như Shade/Assembly hoặc cách đóng gói của framework, kiểm tra artifact và cơ chế khởi chạy trên môi trường đích.

### 7.1. Xây dựng runtime classpath bằng Maven Dependency Plugin

Maven Dependency Plugin có goal `build-classpath` để tạo chuỗi classpath từ các project dependencies. Với dự án mẫu, có thể chạy sau khi `mvn clean verify`:

```bash
mvn dependency:build-classpath -Dmdep.outputFile=target/dependency-classpath.txt -DincludeScope=runtime
```

Khi dùng phiên bản Dependency Plugin hỗ trợ tham số `includeScope` tương ứng, mục đích là chỉ chọn tập dependency dành cho runtime (bao gồm các dependency `compile` phù hợp). Nếu môi trường có cách cấu hình plugin khác, đối chiếu tài liệu goal đang dùng; tránh đoán rằng mọi phiên bản plugin nhận mọi cờ giống nhau. Đường dẫn trong file là đường dẫn thực tới JAR trong local repository của máy.

Trên Linux/macOS với Bash hoặc zsh, sau khi kiểm tra file được tạo:

```bash
java -cp "target/classes:$(cat target/dependency-classpath.txt)" dev.example.App
```

Trên Windows PowerShell, dấu phân tách classpath là dấu chấm phẩy thay vì dấu hai chấm. Ví dụ:

```powershell
$dependencies = (Get-Content -Raw target/dependency-classpath.txt).Trim()
java -cp "target/classes;$dependencies" dev.example.App
```

Cả hai ví dụ đều giả định file `dependency-classpath.txt` chứa những đường dẫn đầy đủ và hợp lệ cho hệ điều hành đang dùng. Không copy file classpath sinh trên Windows sang Linux rồi chạy nguyên xi vì ký tự phân tách/đường dẫn khác nhau.

**Tại sao cách này thành công?** Thay vì chỉ có `target/classes`, classpath JVM còn chứa JAR Commons Lang mà dự án cần ở runtime. Scope `provided` (nếu bạn cố tình chuyển sang nó) vẫn không được tự đưa vào runtime classpath; điều đó đúng với ý nghĩa của provided.

### 7.2. Tránh ghép toàn bộ local repository

Không dùng một lệnh wildcard đệ quy giả định mọi JAR trong `~/.m2/repository` đều thuộc ứng dụng. Local repository có cả plugin, dependency test, nhiều version và thư viện của những dự án khác. Đưa tất cả lên classpath có thể che giấu xung đột version hoặc khiến chương trình chạy được trên máy mình nhưng không thể tái lập nơi khác.

Maven phải giải quyết dependency graph hiệu lực của **đúng dự án**, rồi runtime chỉ dùng các artifact liên quan.

## 8. Phân biệt NoClassDefFoundError, ClassNotFoundException và NoSuchMethodError

Một thông điệp lỗi giúp định hướng chẩn đoán:

| Lỗi | Ý nghĩa điển hình | Cách kiểm tra |
| --- | --- | --- |
| `NoClassDefFoundError` | JVM cần một lớp khi giải quyết/liên kết mã nhưng không tìm/khởi tạo được định nghĩa lớp phù hợp | Tìm tên class trong lỗi và runtime classpath; xem `Caused by` |
| `ClassNotFoundException` | Code/API tải lớp theo tên (ví dụ `Class.forName`) nhưng classloader không tìm thấy | Kiểm tra tên lớp, driver/provider và classloader |
| `NoSuchMethodError` | Lớp được tìm thấy nhưng signature method mong đợi không có ở bản runtime | So sánh version compile/runtime và dependency mediation |
| `NoSuchFieldError` | Field được code biên dịch nhắc tới không có trong định nghĩa lớp runtime | Kiểm tra JAR/version thực tế |
| `UnsupportedClassVersionError` | Bytecode được biên dịch cho Java mới hơn JVM chạy | So sánh `java -version` với mục tiêu compiler |
| `ExceptionInInitializerError` | Khởi tạo static class thất bại | Đọc nguyên nhân gốc; không tự quy hết về thiếu JAR |

Không phải mọi `NoClassDefFoundError` đều đơn giản là “không tìm thấy file JAR”. Lớp có thể được tải qua classloader khác, bị lỗi khi khởi tạo tĩnh, hoặc thiếu một dependency gián tiếp của lớp đó. Stack trace và nguyên nhân sâu hơn (`Caused by`) mới giúp phân biệt.

### 8.1. Minh họa ClassNotFoundException

Đoạn Java sau **chỉ minh họa một API**, không nằm trong chương trình thực hành chính:

```java
try {
    Class.forName("org.apache.commons.lang3.StringUtils");
} catch (ClassNotFoundException ex) {
    System.err.println("Runtime không tìm thấy lớp theo tên");
}
```

Khi code gọi `Class.forName` với tên lớp không có trên classpath/classloader, API có thể ném `ClassNotFoundException`. Ngược lại, khi bytecode của một class khác tham chiếu trực tiếp lớp không còn ở runtime, `NoClassDefFoundError` là lỗi điển hình.

### 8.2. Class có mà method thiếu

Nếu build dùng `commons-lang3` version X nhưng runtime chọn một JAR khác với API không tương thích, classloader có thể tìm thấy `StringUtils.class` nhưng khi gọi method mới sẽ gây `NoSuchMethodError`. Thêm thư viện ngẫu nhiên vào runtime classpath không chắc chữa đúng lỗi; cần biết JAR nào thực tế được nạp.

## 9. Transitive dependencies: phụ thuộc bắc cầu có thể thiếu

Giả sử POM ứng dụng có dependency trực tiếp A, còn A phụ thuộc B:

```text
Ứng dụng
  └── A (compile)
       └── B (compile)
```

Maven bình thường có thể đưa B vào graph dependency runtime. Nhưng kết quả có thể thay đổi nếu:

- B được A khai báo ở scope không truyền sang consumer theo quy tắc Maven.
- B là dependency `optional` ở thư viện A, nên consumer không tự nhận B.
- Ứng dụng hoặc một dependency khai báo `<exclusions>` khiến B bị loại khỏi một nhánh graph.
- Nhiều nhánh yêu cầu B với version khác nhau; Maven dùng luật mediation để chọn một version.
- B tồn tại lúc compile trên IDE do cấu hình riêng nhưng không nằm trong runtime artifact/classpath cuối.

Ví dụ exclusion trong POM (đây là **đoạn minh họa cú pháp**, các tọa độ `com.example` không phải thư viện phải tải):

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>client-a</artifactId>
    <version>1.2.3</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>helper-b</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion áp dụng theo cạnh phụ thuộc, không mặc định cấm artifact ở mọi nhánh. Khi loại một JAR mà thư viện A vẫn dùng lúc chạy, ứng dụng có thể thất bại mặc dù POM hợp lệ và code chính đã compile.

Cách tìm:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn help:effective-pom
```

Quan sát scope, version, các nhánh bắc cầu và phần quản lý version từ POM cha/BOM. Đừng cho rằng Maven “luôn chọn version mới nhất”; quy tắc lựa chọn phụ thuộc vào độ gần trong dependency graph và những khai báo quản lý version phù hợp.

## 10. Vì sao test pass nhưng production vẫn lỗi?

Test runtime classpath được thiết kế để phục vụ test, nên có thể bao gồm:

- Các dependency compile/runtime của mã sản phẩm.
- Các dependency `test` của JUnit, Mockito, AssertJ.
- Một số dependency `provided` cần cho quá trình compile/test.
- Các lớp test ở `target/test-classes`.

Trong khi đó, môi trường production chỉ có những thứ **được đưa tới nơi chạy thực tế**. Vì thế:

1. Một dependency `provided` có thể có trong test runtime nhưng vắng ở runtime của ứng dụng độc lập.
2. IDE có thể tự bổ sung JAR từ cấu hình launch/test, trong khi Dockerfile hoặc script production quên đưa JAR vào.
3. JAR Maven thông thường không tự chứa các dependency dù tests chạy với classpath Maven đầy đủ.
4. Các lớp trợ giúp trong `src/test/java` hoặc tài nguyên `src/test/resources` không được đóng gói vào JAR chính theo mặc định.
5. CI có thể dùng JDK hoặc version dependency khác máy local, dẫn tới lỗi linkage khi chạy.

Bài kiểm tra đúng phải bao gồm cả **build/test** và **cách khởi chạy sản phẩm cuối cùng**. Chỉ kiểm tra `BUILD SUCCESS` ở phase `package` chưa đủ để chứng minh runtime closure (tập đầy đủ thư viện cần để chạy) đã được phân phối.

## 11. Container, ứng dụng web và classloader

Một nguyên nhân khó hơn xuất hiện khi cùng một artifact chạy trong các môi trường khác nhau:

- Servlet container/app server thường có thư viện và classloader riêng. Một API được cung cấp bởi container có thể sử dụng `provided`.
- Ứng dụng Spring Boot có plugin repackaging tạo executable JAR có cấu trúc và launcher riêng; không thể suy luận nội dung như Maven JAR chuẩn.
- Maven Shade/Assembly có thể nhúng dependencies, nhưng cách merge tài nguyên/service definitions và xung đột tên lớp có thể làm runtime khác build.
- Java Module System (JPMS) phân biệt classpath và module path; lỗi truy cập module hoặc thiếu module cũng có thể gây triệu chứng tương tự.

**Không sửa đồng loạt tất cả dependency thành `compile`** khi container có xung đột. Đôi khi cách giải là dùng đúng API version mà server cung cấp, thay đổi cấu hình classloader, hoặc tránh đóng hai bản thư viện không tương thích cùng lúc.

Với một ứng dụng Java chạy độc lập, giả định an toàn hơn là **chính quy trình đóng gói/triển khai của ứng dụng phải đưa đến runtime tất cả các dependencies cần thiết**.

## 12. Quy trình chẩn đoán từng bước

Khi gặp lỗi “compile có nhưng chạy thiếu”, đi theo trình tự:

### Bước 1: chụp đúng lỗi và cách gọi chương trình

Ghi lại:

- Tên lớp/method được báo thiếu.
- Dòng lệnh chạy thực tế: `java -cp`, `java -jar`, `mvn exec:java`, Docker ENTRYPOINT hay lệnh của application server.
- JDK, working directory và toàn bộ nguồn cung cấp classpath.
- Chuỗi `Caused by` đầy đủ nhưng **xóa bí mật** trước khi gửi log.

Một lỗi `no main manifest attribute` khác với thiếu thư viện; `UnsupportedClassVersionError` khác với không tìm thấy lớp.

### Bước 2: xem Maven đã phân giải dependency chưa

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
```

Xem tọa độ, version và scope đúng của thư viện chứa lớp bị báo thiếu. Nếu `mvn compile` đã thành công, có thể compiler đã có JAR này, nhưng vẫn cần biết đường dẫn nào Maven chọn.

### Bước 3: kiểm tra scope có hợp với môi trường chạy không

- Mã chính import thư viện và cần nó trong chương trình độc lập → thường `compile`.
- Mã chính không import driver nhưng cần implementation runtime → có thể `runtime`.
- Server/container đã có API phù hợp → có thể `provided`, nhưng cần xác nhận runtime thực tế.
- JUnit/Mockito chỉ dùng trong test → `test`.

Nếu thư viện ở `provided` mà bạn không có server cung cấp, đây là lỗi phạm vi hoặc thiết kế phân phối.

### Bước 4: kiểm tra nội dung artifact và thư mục đích

```bash
mvn clean package
jar tf target/runtime-classpath-lab-1.0.0-SNAPSHOT.jar
```

Đừng chỉ thấy JAR chính rồi mặc định nó đã chứa các JAR bên ngoài. Nếu ứng dụng cần fat JAR, phải có cấu hình plugin và xác minh artifact được tạo.

### Bước 5: thử chạy bằng classpath do Maven cung cấp

```bash
mvn -q -Dexec.mainClass=dev.example.App exec:java
```

Nếu Maven Exec chạy được còn `java -cp target/classes` thất bại, khác biệt nằm ở classpath khởi chạy. Nếu cả hai đều thất bại, kiểm tra scope `provided`, graph dependency, classloader và version thực tế.

### Bước 6: xác minh trên môi trường sạch

Dùng máy/CI/container có JDK được yêu cầu, repository có thể truy cập và dữ liệu đầu vào đã kiểm soát. Chạy đúng script/phương thức dự định dùng khi triển khai. Đừng dựa vào JAR hoặc biến môi trường chỉ tồn tại trên máy lập trình viên.

### Bước 7: sửa đúng tầng và chạy lại

- **Scope sai** → sửa POM, xem xét compatiblity/runtime server.
- **Script JVM thiếu classpath** → cung cấp runtime libraries qua classpath hoặc packaging phù hợp.
- **Dependency bắc cầu thiếu** → khai báo rõ dependency, sửa exclusion/optional khi hợp lý.
- **Version không tương thích** → khóa/align dependency versions, kiểm tra graph và JAR runtime.
- **Runtime không đủ Java version** → dùng JVM phù hợp hoặc compile với target được hỗ trợ.

Cuối cùng, chạy `mvn clean verify` **và** thử khởi chạy artifact theo đường triển khai thật.

## 13. Bảng lỗi thường gặp và hướng xử lý

| Triệu chứng | Chẩn đoán ưu tiên | Việc nên làm |
| --- | --- | --- |
| `mvn compile` thành công, `java -cp target/classes ...` lỗi `NoClassDefFoundError` | JVM không có thư viện bên ngoài | Dùng runtime classpath đúng hoặc đóng gói phù hợp |
| `mvn verify` pass, `mvn exec:java` thiếu thư viện | Dependency `provided`, runtime scope/classpath plugin hoặc classloader khác | Xem scope trong dependency tree, kiểm tra runtime thực |
| `java -jar` báo `no main manifest attribute` | JAR không khai báo `Main-Class` | Cấu hình manifest/launcher, sau đó vẫn kiểm tra dependencies |
| `java -jar` có Main-Class nhưng vẫn thiếu lớp | Chỉ khai báo entry point, chưa kèm runtime libraries | Thiết kế packaging/classpath thực tế |
| Test chạy trên IDE nhưng lỗi khi deploy | IDE dùng classpath khác script/container | So sánh launcher, scope và JAR phân phối |
| `ClassNotFoundException` với tên JDBC driver | Driver thiếu trên runtime classpath hoặc sai tên | Kiểm tra artifact driver scope `runtime` hoặc `compile` phù hợp |
| `NoSuchMethodError` | JAR runtime khác API khi compile | Dùng dependency tree, kiểm tra version/JAR đang được nạp |
| `UnsupportedClassVersionError` | Runtime JDK quá cũ | Dùng JDK đúng hoặc thay compiler release khi code/API cho phép |
| `NoClassDefFoundError` sau lỗi static init | Lớp đã khởi tạo thất bại | Xem nguyên nhân gốc trong stack trace |
| Commons Lang khai báo `provided` nhưng chạy CLI độc lập | Không có runtime nào cung cấp Commons Lang | Đổi về `compile` và dùng classpath đúng |
| Thiếu test classes trong JAR chính | Packaging Java mặc định không đóng test classes | Không lấy test class làm runtime contract; tạo artifact chuyên biệt nếu cần |
| Build khác nhau giữa local/CI | Cấu hình Maven/JDK/settings/cache khác | Cố định version, kiểm tra effective POM và quy trình chạy |

**Không nên:**
- Chép ngẫu nhiên JAR vào nhiều thư mục để “thử may”.
- Đặt tất cả libraries thành `provided` nhằm giảm kích thước JAR.
- Sửa chỉ để IDE chạy được, bỏ qua runtime CI/production.
- Vô hiệu hóa kiểm thử hoặc ép build success khi artifact thực tế vẫn không chạy.
- Commit nguyên toàn bộ `~/.m2/repository` vào Git như một cách quản lý classpath.

## 14. Bài tập thực hành

1. Dùng dự án `runtime-classpath-lab` chạy `mvn clean verify`, tìm `App.class`, `GreetingService.class`, báo cáo 3 test và JAR sản phẩm.
2. Chạy `java -cp target/classes dev.example.App`, ghi lại tên lớp thiếu. Tại sao compiler đã tìm thấy lớp đó nhưng JVM lại không?
3. Chạy `mvn -q -Dexec.mainClass=dev.example.App exec:java`. Chứng minh ứng dụng in `Xin chào, Maven!` và nêu điều thay đổi giữa hai cách gọi.
4. Kiểm tra `jar tf target/runtime-classpath-lab-1.0.0-SNAPSHOT.jar`; tìm Commons Lang bên trong. Vì sao không thấy `StringUtils.class` không có nghĩa Maven khai báo sai dependency?
5. Đổi Commons Lang sang `<scope>provided</scope>`, chạy `mvn clean verify` và thử `exec:java`. Giải thích vì sao test pass còn runtime có thể thiếu thư viện. Sau đó khôi phục scope.
6. So sánh `provided` với `runtime` và `test`. Scope nào hợp với một JDBC implementation chỉ được nạp lúc runtime? Scope nào hợp với JUnit?
7. Dùng Maven Dependency Plugin tạo classpath runtime rồi chạy `java -cp` đúng theo hệ điều hành. Vì sao dùng classpath từ local repository của chính dự án tốt hơn quét mọi JAR dưới `~/.m2/repository`?
8. Tạo tình huống một dependency bắc cầu B bị loại bằng `<exclusions>`. Khi nào dự án có thể vẫn compile mà chạy thiếu B? Nếu một nhánh khác đưa B vào thì exclusion có ngăn toàn bộ B không?
9. Phân biệt ba thông báo `NoClassDefFoundError`, `ClassNotFoundException` và `NoSuchMethodError` bằng tên lớp/method xuất hiện trong stack trace và hướng kiểm tra tương ứng.
10. Nêu một cách phân phối ứng dụng Java có dependencies để máy khác chạy được mà không phải biết local repository Maven trên máy lập trình viên.

## 15. Tóm tắt

Một thư viện “có khi compile, thiếu lúc chạy” **không mâu thuẫn với Maven**. Compile classpath và runtime classpath được xây dựng cho hai nhiệm vụ khác nhau, còn sản phẩm `jar` Maven chuẩn thường chỉ chứa lớp/tài nguyên của chính dự án. Vì vậy phải phân biệt rõ:

- Dependency thực sự ở scope gì trong **effective POM**?
- Maven đã phân giải nó vào **classpath nào**?
- Runtime thực tế sử dụng **lệnh chạy, JDK và classloader nào**?
- Artifact và những JAR đi kèm đã được **phân phối đầy đủ** chưa?

Đối với Java command-line độc lập, thử `mvn exec:java` để kiểm chứng runtime classpath của Maven, sau đó thiết kế launcher hoặc artifact phù hợp với môi trường đích. Đối với application server, kiểm chứng rằng các API `provided` thực sự có mặt ở container. Với lỗi version, xem dependency graph và runtime JAR, không chỉ tăng version trong POM rồi hy vọng.

## 16. Tài liệu chính thức

- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven — Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)
- [Maven Exec Plugin — java goal](https://www.mojohaus.org/exec-maven-plugin/java-mojo.html)
- [Maven Dependency Plugin — build-classpath goal](https://maven.apache.org/plugins/maven-dependency-plugin/build-classpath-mojo.html)
- [Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/)
- [Maven Shade Plugin](https://maven.apache.org/plugins/maven-shade-plugin/)
- [Java API — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [Java API — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html)
