# Đính kèm mã nguồn bằng Maven Source Plugin

## 1. Tại sao một thư viện Java cần source JAR?

Một dự án Java thường sinh ra JAR chứa các file `.class`. Khi dự án khác dùng JAR đó như dependency, JVM chạy bytecode nhưng người lập trình sẽ khó đọc phần triển khai nếu không có mã nguồn. Một **sources JAR** cho phép IDE tải đúng mã `.java` tương ứng với binary dependency, xem implementation, đặt breakpoint và đối chiếu stack trace.

Trong nhóm **JAR và manifest**, cần phân biệt hai artifact:

- **Binary JAR** từ Maven JAR Plugin: thường chứa `.class`, resources và `META-INF/MANIFEST.MF`.
- **Sources JAR** từ Maven Source Plugin: chứa các source files mà plugin tập hợp từ source roots và một số metadata/resources theo cấu hình; thường có tên kết thúc bằng `-sources.jar`.

Ví dụ Maven project có:

```text
groupId    = dev.course
artifactId = source-attach-demo
version    = 1.0.0-SNAPSHOT
packaging  = jar
```

Nếu cấu hình Source Plugin phù hợp, sau `mvn clean package` bạn sẽ thấy:

```text
target/source-attach-demo-1.0.0-SNAPSHOT.jar
target/source-attach-demo-1.0.0-SNAPSHOT-sources.jar
```

Hai tệp có cùng tọa độ gốc nhưng **source JAR có classifier `sources`**. Mặc định Source Plugin 3.4.0 sử dụng `<attach>true</attach>`, để Maven có thể xử lý source JAR như một **attached artifact** trong những phase tiếp theo.

Mục đích của bài là tạo cả hai artifact, kiểm tra nội dung và hiểu vì sao một source JAR đã được tạo **chưa chắc đã được attach** nếu người viết POM tắt attachment.

## 2. Source Plugin không thay thế JAR Plugin hoặc Javadoc Plugin

| Artifact | Ví dụ tệp | Thành phần thường có | Công cụ |
| --- | --- | --- | --- |
| Binary JAR | `demo-1.0.jar` | `.class`, manifest, resources | `maven-jar-plugin` |
| Sources JAR | `demo-1.0-sources.jar` | Source `.java` và mục liên quan | `maven-source-plugin` |
| Javadoc JAR | `demo-1.0-javadoc.jar` | HTML tài liệu API | `maven-javadoc-plugin` |
| Compiled test JAR | `demo-1.0-tests.jar` | Test `.class` | `maven-jar-plugin:test-jar` |
| Test sources JAR | `demo-1.0-test-sources.jar` | Test `.java` | `maven-source-plugin:test-jar-no-fork` |

**Sources JAR không phải executable JAR.** Không dùng `java -jar ...-sources.jar` với hy vọng JVM tự dịch các file Java bên trong. JVM thông thường cần bytecode và runtime classpath phù hợp. Source JAR cũng không phải một công cụ giải mã bytecode thành source gốc: nó đóng gói các file mã nguồn mà project có tại thời điểm build.

IDE có thể tự liên kết bản `sources` với binary artifact dựa trên groupId/artifactId/version/classifier; consumer **không nên thêm sources JAR vào runtime dependencies** để việc mở code hoạt động.

## 3. “Tạo source JAR” và “attach source JAR” là hai thao tác

Maven có một **primary artifact** và có thể có nhiều **attached artifacts**.

Ví dụ:

```text
Primary artifact
  groupId    = dev.course
  artifactId = source-attach-demo
  version    = 1.0.0-SNAPSHOT
  type       = jar
  classifier = (không có)

Attached sources artifact
  groupId    = dev.course
  artifactId = source-attach-demo
  version    = 1.0.0-SNAPSHOT
  type       = jar
  classifier = sources
```

Lúc Source Plugin chạy:

1. Nó tìm các source roots và đóng gói source files thành archive trong thư mục build.
2. Khi `attach=true`, nó đăng ký archive như một attached artifact thuộc Maven project.
3. Các phase `install`/`deploy` và plugin phù hợp sau đó có thể mang theo artifact đính kèm này.

Nếu `attach=false`, plugin vẫn có thể tạo tệp sources JAR ở `target/`, nhưng **không đăng ký nó như attachment**. Do đó, chỉ dùng `jar tf` để xác nhận file tồn tại là **chưa đủ** để kết luận Maven đã cài/xuất bản nó.

Không “attach” bằng cách copy sources JAR vào bên trong binary JAR. Maven quản lý hai artifact độc lập, liên hệ với nhau qua tọa độ.

## 4. Các goal của Maven Source Plugin

Maven Source Plugin 3.4.0 có những goal đáng biết:

| Goal | Vai trò | Đặc điểm |
| --- | --- | --- |
| `source:jar` | Tạo sources JAR cho mã chính | Có cơ chế **fork** lifecycle tới `generate-sources` trước khi chạy |
| `source:jar-no-fork` | Tạo sources JAR cho mã chính | **Không fork** lifecycle; phù hợp để bind vào build |
| `source:test-jar` | Tạo JAR mã nguồn test | Dành cho test sources, có cơ chế fork |
| `source:test-jar-no-fork` | Tạo JAR mã nguồn test | Không fork; phù hợp để bind khi cần test sources |
| `source:aggregate` | Tổng hợp nguồn từ các modules | Dành cho use case aggregator, không thay mặc định mỗi module sources JAR |

Điểm quan trọng là phân biệt `jar` và `jar-no-fork`:

- Goal `jar` phù hợp khi người dùng chủ động gọi từ CLI và muốn plugin đảm bảo các công việc ở `generate-sources` được thực hiện trước.
- Goal **`jar-no-fork`** không sinh ra một vòng lifecycle riêng, nên **nên dùng trong POM khi bind vào `package` hoặc `verify`**.
- Nếu đã cấu hình Source Plugin tự chạy ở package, không nên gọi thêm một lần goal tạo source cùng classifier trong một lifecycle mà không hiểu cơ chế attachment; có thể xảy ra lỗi attach trùng.

**Theo tài liệu Maven Source Plugin, goal `jar-no-fork` có default phase `package`.** Bài thực hành vẫn ghi phase rõ ràng để không phụ thuộc vào người học nhớ default này.

## 5. Cấu hình tối thiểu để attach mã nguồn

Đặt đoạn sau trong `<build><plugins>` của POM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.4.0</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <phase>package</phase>
            <goals>
                <goal>jar-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn plugin**, không phải POM hoàn chỉnh.

- `groupId`, `artifactId`, `version` xác định plugin.
- `execution id=attach-sources` là tên một lần chạy được Maven ghi vào log; nó **không phải classifier**.
- `phase=package` đưa goal vào lifecycle trước `install` và `deploy`.
- `goal=jar-no-fork` dùng source roots sẵn có mà không fork vòng build khác.
- Classifier mặc định là `sources`; `attach` mặc định là `true`, nên không bắt buộc phải khai báo hai thẻ này.

Nếu muốn tường minh, có thể thêm vào cùng phần tử `<plugin>`:

```xml
<configuration>
    <attach>true</attach>
    <classifier>sources</classifier>
</configuration>
```

**Không tạo một `<plugin>` thứ hai chỉ để chứa cấu hình này.** Với project mẫu bên dưới, ta ghi `attach=true` rõ ràng và giữ default classifier.

## 6. Gắn tại package hay verify?

Cả hai phase đều nằm trước `install` trong default lifecycle. Khác biệt là thời điểm tạo file:

| Binding | `mvn clean package` | `mvn clean verify` | `mvn clean install` |
| --- | --- | --- | --- |
| `<phase>package</phase>` | Có sources JAR | Có | Có và có thể install |
| `<phase>verify</phase>` | Chưa tạo nguồn từ execution này | Có sources JAR | Có và có thể install |

Trang Usage của Source Plugin có ví dụ attach tại phase `verify`. Với bài này, dùng **package** để quan sát binary JAR và source JAR ngay sau một lệnh build ngắn.

Nếu bạn chỉ đặt Source Plugin vào `build/plugins` mà **không có execution**, Maven không tự chạy `source:jar-no-fork` chỉ bởi packaging là `jar`. Default lifecycle tạo binary JAR nhờ JAR Plugin, nhưng **không tự attach sources**.

## 7. Dự án Java 17 thực hành đầy đủ

Ta tạo một Maven project có mã chính, mã test và Source Plugin. Nội dung runnable từ đầu, không giả định tệp ở bài học khác.

### 7.1. Cấu trúc

```text
source-attach-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/course/
    │       ├── Greeter.java
    │       └── App.java
    └── test/
        └── java/dev/course/
            └── GreeterTest.java
```

Yêu cầu: JDK 17+, Maven 3.9.x hoặc phiên bản tương thích, network hoặc cache có sẵn các plugin/dependencies. Các phiên bản đã được ghim để phục vụ bài thực hành, **không phải phiên bản mới nhất được khẳng định cho mọi thời điểm**.

### 7.2. pom.xml hoàn chỉnh

Tạo `source-attach-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>source-attach-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
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
                <version>3.4.1</version>
            </plugin>

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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <attach>true</attach>
                </configuration>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

POM hoàn chỉnh này có các vai trò:

1. Compiler Plugin cùng `maven.compiler.release=17` chọn Java Platform mục tiêu.
2. `project.build.sourceEncoding=UTF-8` giúp compiler đọc đúng file có tiếng Việt.
3. JUnit Jupiter scope `test` và Surefire Plugin chạy kiểm thử ở phase `test`.
4. JAR Plugin đóng binary JAR từ mã đã compile.
5. Source Plugin `jar-no-fork` chạy ở phase `package`, tạo và attach source JAR.

### 7.3. Source code Greeter.java

Tạo `src/main/java/dev/course/Greeter.java`:

```java
package dev.course;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên không được để trống");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Lớp `Greeter` không dùng thư viện bên ngoài JDK. `String.isBlank` và `String.strip` có trong Java 17, nên code biên dịch được theo release 17.

### 7.4. Source code App.java

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet(" Lan "));
    }
}
```

Stdout **do ứng dụng tạo** khi chạy đúng:

```text
Xin chào, Lan!
```

### 7.5. JUnit tests

Tạo `src/test/java/dev/course/GreeterTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreeterTest {
    @Test
    void normalizesName() {
        assertEquals("Xin chào, Lan!", Greeter.greet(" Lan "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeter.greet("   "));
    }

    @Test
    void rejectsNullName() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeter.greet(null));
    }
}
```

Surefire chạy **3 unit tests**. Source Plugin được cấu hình với `jar-no-fork` cho **main sources**, nên `GreeterTest.java` không tự trở thành nội dung của **main sources JAR**. Muốn kèm mã nguồn test, phải dùng `test-jar-no-fork` riêng.

## 8. Build và xác minh hai file JAR

Tại thư mục `source-attach-demo`, chạy:

```bash
mvn -version
mvn clean package
```

Kết quả mong đợi khi JDK/Maven và repository hợp lệ:

- Maven compile được `Greeter.java` và `App.java`.
- Surefire chạy 3 JUnit tests, tất cả pass.
- JAR Plugin tạo binary JAR.
- Source Plugin chạy execution `attach-sources` và tạo sources JAR.
- Maven in `BUILD SUCCESS`.

Một số đường dẫn cần tìm:

```text
target/classes/dev/course/Greeter.class
target/classes/dev/course/App.class
target/test-classes/dev/course/GreeterTest.class
target/source-attach-demo-1.0.0-SNAPSHOT.jar
target/source-attach-demo-1.0.0-SNAPSHOT-sources.jar
target/surefire-reports/
```

Log minh họa có thể chứa:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
... maven-source-plugin:3.4.0:jar-no-fork (attach-sources) ...
BUILD SUCCESS
```

Các dòng trên là **kết quả đại diện**, không phải nguyên văn toàn bộ log.

### 8.1. Quan sát nội dung bằng jar tf

JDK có công cụ `jar`, chạy được trên Bash/zsh và PowerShell:

```bash
jar tf target/source-attach-demo-1.0.0-SNAPSHOT.jar
jar tf target/source-attach-demo-1.0.0-SNAPSHOT-sources.jar
```

Trong binary JAR, tìm:

```text
dev/course/Greeter.class
dev/course/App.class
```

Trong sources JAR, tìm:

```text
dev/course/Greeter.java
dev/course/App.java
```

Đây là những entries cần quan sát, **không phải output đầy đủ**, vì còn có thể có `META-INF/MANIFEST.MF`, Maven descriptors và các thư mục trong archive.

Điểm phân biệt chính là `.class` thuộc binary JAR còn `.java` thuộc source JAR. Chỉ nhìn hai tên file mà không kiểm tra contents có thể bỏ sót vấn đề đóng gói.

### 8.2. Chạy ứng dụng

Vì mã chính chỉ dùng Java Standard Library, chạy:

```bash
java -cp target/classes dev.course.App
```

Stdout **chính xác**:

```text
Xin chào, Lan!
```

Không dùng `java -jar ...-sources.jar` để chạy chương trình. POM ví dụ cũng chưa cấu hình `Main-Class` trong binary JAR, nên lệnh thử đúng là `java -cp target/classes ...`.

### 8.3. Xác minh mã nguồn vẫn là văn bản Unicode

Bạn có thể giải nén sources JAR bằng công cụ ZIP/JAR, sau đó mở `dev/course/Greeter.java` bằng editor UTF-8. Bản mã nguồn được đóng gói phải vẫn có chuỗi `"Xin chào, "` và `"Tên không được để trống"`.

Source Plugin không “dịch” `.java` thành `.class` khi tạo sources JAR. Nó đóng gói file source, còn Compiler Plugin tạo bytecode trong bước compile riêng.

## 9. Đính kèm và cài vào Maven local repository

`mvn clean package` tạo hai tệp dưới `target/`, nhưng **chưa cài chúng vào local repository**. Để cài primary artifact và những artifacts đã attach:

```bash
mvn clean install
```

Phần Source Plugin đã chạy ở `package` trước khi Maven tới `install`, vì vậy Install Plugin có thể cài cả binary JAR và sources JAR.

Với local repository mặc định, một số file bạn cần tìm:

```text
~/.m2/repository/dev/course/source-attach-demo/1.0.0-SNAPSHOT/
    source-attach-demo-1.0.0-SNAPSHOT.jar
    source-attach-demo-1.0.0-SNAPSHOT-sources.jar
    source-attach-demo-1.0.0-SNAPSHOT.pom
    metadata khác của Maven
```

Nếu settings hoặc CLI đặt `maven.repo.local` riêng, thư mục thực tế có thể khác. Không giả định máy nào cũng dùng `~/.m2/repository`.

### 9.1. Dùng local repository riêng để thực hành

Bash/zsh:

```bash
mvn clean install "-Dmaven.repo.local=$PWD/.maven-repo-lab"
```

PowerShell:

```powershell
$repo = Join-Path (Get-Location).Path ".maven-repo-lab"
mvn clean install "-Dmaven.repo.local=$repo"
```

Kiểm tra sau khi cài thành công tại:

```text
.maven-repo-lab/dev/course/source-attach-demo/1.0.0-SNAPSHOT/
```

Lưu ý: việc dùng một local repository **trống** có thể khiến Maven tải lại JUnit và plugins trong pha online. Đưa cache này vào `.gitignore`:

```gitignore
target/
.maven-repo-lab/
```

Đây là nội dung file `.gitignore` chứ không phải lệnh terminal. Không commit Maven local repository hoặc artifacts tạm vào Git để “giải quyết” dependency.

### 9.2. Khi nào IDE tải nguồn?

Một consumer bình thường khai báo dependency ở POM **không có classifier**:

```xml
<dependency>
    <groupId>dev.course</groupId>
    <artifactId>source-attach-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```

Khi IDE biết Maven repository chứa cả binary và sources artifact, chức năng **Download Sources / Attach Sources** có thể tìm classifier `sources` của cùng groupId/artifactId/version.

Nếu người học dùng `.maven-repo-lab` khác với kho mà IDE đang đọc, IDE có thể chưa nhìn thấy sources. Khi đó cần cấu hình repository tương ứng, không tự thêm sources JAR vào runtime classpath của chương trình.

Để hiểu classifier, một dependency XML như sau chỉ **minh họa cách yêu cầu sources artifact**, không nên dùng để thay dependency binary bình thường:

```xml
<dependency>
    <groupId>dev.course</groupId>
    <artifactId>source-attach-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <classifier>sources</classifier>
    <type>jar</type>
</dependency>
```

Dependency có classifier `sources` mang mã nguồn, không cung cấp bytecode cho chương trình tiêu thụ trong build Java thông thường.

## 10. Deploy source JAR lên repository từ xa

Khi đã có attached artifact, Maven Deploy Plugin có thể publish cùng POM, binary JAR và các attached artifacts lên một remote repository được cấu hình và được phép.

Điều kiện:

- Repository releases/snapshots được cấu hình phù hợp trong `distributionManagement` hoặc quy trình deployment.
- Credentials được quản lý qua Maven settings/secret store; không hard-code mật khẩu trong POM.
- CI có quyền publish và đã hoàn tất kiểm tra source archive trước khi phát hành.
- Version artifact nguồn và binary tương ứng, không đổi nguồn của một release sau khi publish.

Một ví dụ **chỉ minh họa cú pháp, không phải server có thật**:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/releases</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

**Không chạy `mvn deploy` vào repository thật chỉ để làm bài tập**. Deploy là thao tác tạo/cập nhật artifacts cho người khác sử dụng và phải đi qua quy trình phát hành được cấp quyền.

Không nhầm `mvn install` (cài vào máy hiện tại) với `mvn deploy` (đẩy artifact tới repository từ xa). Cả hai cần source archive được attach đúng, nhưng nơi lưu và quyền tác động rất khác nhau.

## 11. Các tham số của jar-no-fork

Theo tài liệu Maven Source Plugin 3.4.0:

| Tham số | Mặc định | Tác dụng |
| --- | --- | --- |
| `attach` | `true` | Đính kèm archive vào project |
| `classifier` | `sources` | Classifier dùng phân biệt sources artifact |
| `outputDirectory` | `${project.build.directory}` | Thư mục chứa archive đầu ra |
| `finalName` | `${project.build.finalName}` | Phần tên tệp output trước hậu tố `-sources` |
| `excludeResources` | `false` | Có bỏ resources khỏi source archive hay không |
| `includePom` | `false` | Có yêu cầu gói thêm POM qua tham số này hay không |
| `includes` / `excludes` | Không tùy chỉnh | Patterns lọc file trong archive |
| `skipSource` | `false` | Bỏ qua tạo source archive khi được bật |
| `forceCreation` | `false` | Có ép tạo lại archive không |
| `outputTimestamp` | `${project.build.outputTimestamp}` | Timestamp cho entries, hỗ trợ reproducibility |

### 11.1. attach=false không giống skipSource=true

Hai lựa chọn này rất dễ nhầm:

- `attach=false`: mục tiêu **không gắn** archive đã tạo vào project; file vẫn có thể tồn tại trong output.
- `skipSource=true`: goal **bỏ qua việc tạo sources archive** theo policy.
- `excludeResources=true`: vẫn tạo source archive nhưng có thể bỏ resources khỏi nội dung.
- `classifier` tùy chỉnh: đổi identity của artifact; nếu consumer/IDE kỳ vọng `sources` mà plugin đặt tên khác, việc tự tải sources có thể không hoạt động.

Đoạn minh họa cấu hình không attach:

```xml
<configuration>
    <attach>false</attach>
</configuration>
```

Chỉ thay **cấu hình của Source Plugin** trong POM chính rồi thử nghiệm. Sau đó khôi phục `attach=true`; không giữ `attach=false` trong một pipeline phát hành vốn yêu cầu source attachment.

### 11.2. Resources và POM metadata

Mặc định `excludeResources=false`, nên resources có thể được đưa vào source archive tùy cấu trúc project và cấu hình plugin. Nếu có ảnh/video lớn không cần thiết, có thể dùng:

```xml
<configuration>
    <excludeResources>true</excludeResources>
</configuration>
```

Đây là đoạn **thay thế/bổ sung** dưới Source Plugin, không phải thiết lập của Maven Resources Plugin. Việc loại resources khỏi **source JAR** không có nghĩa binary JAR sẽ mất resources.

Mặc định `includePom=false`, nhưng từ Source Plugin 3.x, sources JAR có thể vẫn chứa Maven descriptor trong `META-INF/maven/...`. Vì vậy không nên khẳng định sources JAR chỉ chứa `.java`, cũng không coi sự xuất hiện của một file POM trong descriptor là bằng chứng `includePom=true`.

### 11.3. Đổi finalName và classifier

Ví dụ:

```xml
<configuration>
    <finalName>custom-source-file</finalName>
    <classifier>sources</classifier>
</configuration>
```

Tên file dưới `target/` có thể thành `custom-source-file-sources.jar`, nhưng **tọa độ Maven để install/deploy vẫn dựa trên project GAV và classifier**. Đổi filename không đổi groupId/artifactId/version.

Không đổi classifier `sources` thành tên tùy ý nếu bạn muốn IDE hoặc build tooling tiêu chuẩn tìm nguồn theo convention. Classifier là một phần quan trọng của identity khi phân giải artifact.

### 11.4. Đường dẫn lọc và bảo mật

Ví dụ cấu hình lọc file:

```xml
<configuration>
    <excludes>
        <exclude>**/internal/**</exclude>
    </excludes>
</configuration>
```

Đây là ví dụ về **pattern**, không phải biện pháp bảo mật chắc chắn. Một tên tệp không được đưa vào sources JAR vẫn có thể tồn tại trong Git hoặc trong binary artifact dưới dạng chuỗi/metadata. Trước khi công khai source archive, cần review nội dung source, licenses, secrets và thông tin nội bộ.

## 12. Đính kèm source test khi có nhu cầu

Main sources và test sources thuộc hai source roots khác nhau. Goal `jar-no-fork` đóng gói main sources; để tạo thêm **test source JAR**, dùng `test-jar-no-fork`.

Thay phần `<executions>` trong Source Plugin bằng:

```xml
<executions>
    <execution>
        <id>attach-main-sources</id>
        <phase>package</phase>
        <goals>
            <goal>jar-no-fork</goal>
        </goals>
    </execution>
    <execution>
        <id>attach-test-sources</id>
        <phase>package</phase>
        <goals>
            <goal>test-jar-no-fork</goal>
        </goals>
    </execution>
</executions>
```

Đây là **cấu hình thay thế**, không được thêm lặp execution nguồn chính nếu đã có một execution khác cùng classifier.

Kết quả thường có thêm:

```text
target/source-attach-demo-1.0.0-SNAPSHOT-test-sources.jar
```

Khi xem bằng `jar tf`, có thể tìm `dev/course/GreeterTest.java`.

**Không nhầm:**

- Maven Source Plugin `test-jar-no-fork` tạo test sources JAR, classifier thường là `test-sources`.
- Maven JAR Plugin `jar:test-jar` tạo compiled test classes JAR, classifier thường là `tests`.
- Một archive chứa test sources **không tự tải JUnit, không tự chạy test**, và không nên được đưa vào production runtime.

Một tổ chức có thể không muốn phát hành test fixtures hoặc nguồn test nội bộ; không phải project nào cũng nên attach test sources.

## 13. Khi dùng jar và khi dùng jar-no-fork

Tài liệu Source Plugin khuyến nghị goal `jar-no-fork` cho **binding vào lifecycle** vì nó không fork một vòng build mới.

Với một project chưa có execution attach sources, lệnh gọi trực tiếp có thể là:

```bash
mvn org.apache.maven.plugins:maven-source-plugin:3.4.0:jar
```

Goal `jar` có cơ chế fork tới `generate-sources`. Khi bind nó vào `package`, một phần source generation có thể chạy lặp hoặc tạo tác dụng phụ, nhất là dự án có code generators.

Nếu đã cấu hình POM runnable ở mục 7, hãy dùng:

```bash
mvn clean package
```

Không thêm `source:jar` trực tiếp vào cùng lượt build trừ khi hiểu rõ classifier/attachment sẽ được xử lý ra sao.

Goal `jar-no-fork` gọi từ CLI một mình **không bảo đảm** các source generation goals ở lifecycle đã chạy; đó là lý do nên gọi một phase như `package` khi project có generated code.

## 14. Generated sources và compileSourceRoots

Một số dự án sinh Java code từ OpenAPI, protobuf, JAXB hoặc annotation processors:

```text
generate-sources
    -> target/generated-sources/...
    -> plugin đăng ký source root (khi phù hợp)
    -> compile
    -> package: source:jar-no-fork
```

Có ba điều kiện cần kiểm tra:

1. Generator chạy **trước** phase đóng source archive.
2. Thư mục generated sources được đăng ký/nhìn thấy trong source roots mà Source Plugin sử dụng, khi plugin yêu cầu.
3. File generated code tồn tại trước khi goal source chạy.

**Không mặc định mọi file dưới `target/generated-sources` sẽ có trong sources JAR.** Một generator có thể chỉ tạo file mà chưa đăng ký nó làm Maven source root. Dùng `mvn clean package` rồi `jar tf ...-sources.jar` để kiểm chứng.

Nếu generated sources thiếu, kiểm tra generator hoặc Maven Build Helper Plugin và thứ tự phases. Không đổi bừa từ `jar-no-fork` sang `jar` để “kích hoạt” generate; đó có thể gây hai vòng generation.

## 15. Dự án multi-module và aggregate sources

Giả sử reactor:

```text
parent/
├── pom.xml            (packaging=pom)
├── api/
│   └── pom.xml        (packaging=jar)
└── service/
    └── pom.xml        (packaging=jar)
```

Thông thường mỗi module nên có source attachment riêng:

```text
api-1.0.0.jar
api-1.0.0-sources.jar
service-1.0.0.jar
service-1.0.0-sources.jar
```

Source Plugin có goal `source:aggregate` để tập hợp nguồn của nhiều modules cho nhu cầu distribution riêng. **Archive tổng hợp không tự thay source attachment cho từng dependency module**. IDE thường tìm sources theo tọa độ của từng module.

Ở POM cha:

- `pluginManagement` giúp quản lý Source Plugin version/configuration.
- `build/plugins` có thể cung cấp execution được kế thừa theo Maven model.
- Module con có thể cần khai báo plugin thực tế nếu parent chỉ có pluginManagement.
- Project aggregator `packaging=pom` không có source có thể không cần source archive; nên tránh ép mọi module chạy cùng goal mà không review.

Khi không rõ module nào đang attach sources, dùng `mvn help:effective-pom` trên module đó và đọc log phase `package`.

## 16. Profile chỉ attach sources khi phát hành

Một tổ chức có thể chỉ publish source JAR khi release. Khi đó có thể chuyển cấu hình Source Plugin sang profile:

```xml
<profiles>
    <profile>
        <id>release-sources</id>
        <build>
            <plugins>
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
            </plugins>
        </build>
    </profile>
</profiles>
```

**Đây là cấu hình thay thế** cho execution luôn chạy trong POM mẫu; không thêm cả hai mà chưa hiểu việc merge/execution ID. Để bật profile và đi tới phase verify:

```bash
mvn -Prelease-sources clean verify
```

Nếu profile không active, Source Plugin từ đoạn profile **không chạy**. Nếu chỉ chạy `package` nhưng goal bind ở `verify`, nó **chưa được gọi**. Khi phát hành, pipeline cần chọn phase/profile đúng và đảm bảo nguồn được attach trước install/deploy.

## 17. Reproducibility, licenses và dữ liệu nhạy cảm

Source JAR được phát hành có thể tiết lộ code và comments mà tác giả không muốn công khai. Đừng coi Source Plugin là công cụ kiểm soát quyền truy cập.

Trước khi publish:

- Kiểm tra entries của source archive bằng `jar tf`.
- Đảm bảo không có secrets, tokens, credentials, tài liệu nội bộ hoặc dữ liệu người dùng trong mã nguồn/resources.
- Kiểm tra license/NOTICE và nghĩa vụ phân phối mã nguồn nếu có.
- Đảm bảo version source JAR khớp với binary JAR, và generated sources khớp commit/release.
- Không thay nội dung một release artifact sau khi đã publish; dùng version mới khi cần sửa.

Source Plugin có tham số `outputTimestamp` để hỗ trợ việc tạo archive tái lập:

```xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Đây là ví dụ định dạng, không có nghĩa mọi build phải dùng ngày này. Một timestamp cố định **chưa đủ để bảo đảm bit-for-bit reproducibility** nếu generated content, thứ tự entries hoặc môi trường thay đổi.

Đừng chèn source code vào fat JAR chỉ vì muốn người tiêu thụ đọc nguồn. Source attachment và runtime packaging là hai nhu cầu độc lập.

## 18. Lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `mvn package` không tạo sources JAR | Chưa bind goal, profile chưa active hoặc bind ở `verify` | Kiểm tra execution/phase và active profiles |
| Có file `-sources.jar` nhưng không xuất hiện sau install | `attach=false` hoặc repo khác | Kiểm tra tham số attach, local repo thực và log |
| Source archive thiếu `.java` | Source roots rỗng/sai hoặc đang build module khác | Xem source roots và `jar tf` |
| Dùng `source:jar` làm generation chạy lại | Goal có fork lifecycle | Ưu tiên `jar-no-fork` trong execution |
| Lỗi duplicate attached artifact | Hai goals/executions cùng classifier | Bỏ attachment trùng, giữ một execution rõ |
| IDE không thể download sources | Chưa install/deploy, khác GAV/classifier hoặc repo | Xem tọa độ binary và attachment |
| Source JAR chứa resource quá lớn | Default `excludeResources=false` | Bật `excludeResources=true` nếu phù hợp |
| `GreeterTest.java` không ở main source archive | Chỉ chạy `jar-no-fork` | Dùng `test-jar-no-fork` khi thật sự cần |
| Build tạo archive với tên khác | Có `finalName` hoặc outputDirectory tùy chỉnh | Kiểm tra POM và log |
| Sources JAR không có generated Java | Generator chưa chạy/đăng ký source root | Kiểm tra generate-sources, build helper và archive |
| `packaging=pom` module không tạo nguồn | Module aggregator không có source | Không ép tạo source archive cho module rỗng |
| `mvn deploy` thất bại | Remote repository/credential/policy sai | Kiểm tra distributionManagement, settings, quyền |
| Source và binary khác version | Build inputs hoặc release process không nhất quán | Ghim version, kiểm tra commit và pipeline |
| Build pass nhưng không có file POM ở root source archive | `includePom=false` mặc định | Phân biệt includePom với Maven descriptor |
| Source bị hiển thị sai dấu | File source/editor không đồng bộ UTF-8 | Kiểm tra byte nguồn và encoding |
| Tạo test source JAR nhưng không có test class | Test source không phải compiled tests | Dùng Maven JAR Plugin test-jar nếu cần .class |

Một cách chẩn đoán đáng tin:

```bash
mvn -version
mvn help:effective-pom
mvn help:active-profiles
mvn clean package
jar tf target/source-attach-demo-1.0.0-SNAPSHOT-sources.jar
```

Nếu cần chi tiết execution ID, dùng `mvn -X clean package`, nhưng kiểm tra log trước khi chia sẻ vì có thể chứa đường dẫn và thông tin môi trường nội bộ.

## 19. Checklist khi hoàn tất

1. Source Plugin đúng version và được kích hoạt tại `build/plugins`.
2. Execution `jar-no-fork` bind đúng phase cần chạy.
3. `attach=true`; không có execution trùng classifier `sources`.
4. `mvn clean package` báo 3 unit tests PASS và tạo cả binary lẫn sources JAR trong ví dụ.
5. `jar tf` của binary JAR thấy `Greeter.class` và `App.class`.
6. `jar tf` của sources JAR thấy `Greeter.java` và `App.java`.
7. Không hiểu nhầm test source, source JAR, Javadoc và compiled test classes.
8. `mvn clean install` cài cả binary/sources vào đúng local repository.
9. Nếu dùng CI/release profile, đúng phase và profile đã được kích hoạt.
10. Generated sources/resources có hoặc không theo đúng chủ đích.
11. Source archive không chứa dữ liệu bí mật, có license phù hợp.
12. Không tự deploy lên remote repository khi chưa được cấp quyền.

## 20. Bài tập tự kiểm tra

1. Vì sao source JAR không phải binary JAR và không thể dùng nó để chạy JVM bình thường?
2. Hãy viết một execution Source Plugin chạy `jar-no-fork` tại phase `package` và giải thích từng thẻ.
3. Version 3.4.0 của Source Plugin mặc định `classifier` và `attach` là gì?
4. Nếu `attach=false`, tệp source archive có thể tồn tại ở đâu? Vì sao nó không tự được install như attachment?
5. Tạo dự án `source-attach-demo`, chạy `mvn clean package` và chỉ ra hai JAR.
6. Dùng `jar tf` để tìm `Greeter.java` trong archive nguồn và `Greeter.class` trong binary.
7. Chạy `java -cp target/classes dev.course.App` và ghi stdout chính xác.
8. Chạy `mvn clean install` và xác minh classifier `sources` trong local repository.
9. Chuyển execution sang phase `verify`. Khi nào `-sources.jar` được tạo?
10. Vì sao `jar-no-fork` phù hợp lifecycle hơn goal `jar` có fork?
11. Thử thêm execution nguồn thứ hai cùng classifier. Điều gì có thể xảy ra?
12. Tạo test sources archive bằng `test-jar-no-fork`; so sánh với Maven JAR Plugin `test-jar`.
13. Nếu IDE không thể attach sources, cần kiểm tra groupId/artifactId/version/classifier và kho nào?
14. Vì sao parent `pluginManagement` không tự tạo source archive cho mọi module?
15. Nếu generated code nằm ở `target/generated-sources` nhưng thiếu trong source JAR, bạn kiểm tra những phase/source roots nào?
16. Nếu một resource chứa secret và default Source Plugin có `excludeResources=false`, bạn sẽ review rủi ro công khai như thế nào?
17. Source Plugin có thể tạo Javadoc JAR trực tiếp không? Công cụ nào làm việc đó?
18. Khi nào nên dùng một release profile để attach sources thay vì luôn chạy ở package?
19. Nếu đổi `finalName`, tọa độ GAV có thay không? Classifier có vai trò gì?
20. Vì sao `outputTimestamp` chỉ là một phần của reproducible build?

## 21. Tóm tắt

**Maven Source Plugin** tạo archive mã nguồn của project; để phân phối đúng cùng binary JAR, hãy **bind `jar-no-fork` vào phase thích hợp và giữ `attach=true`**. Plugin mặc định tạo classifier `sources`, vì vậy IDE và repository tooling có thể liên kết bản mã nguồn với dependency binary cùng version.

Trong ví dụ Java 17, `mvn clean package` tạo binary JAR và sources JAR; `mvn clean install` cài các artifacts vào local repository; ba JUnit tests xác minh mã hoạt động, và `jar tf` cho biết archive nào chứa `.java` hay `.class`. Với dự án nhiều module, generated code, release profiles hoặc requirements bảo mật, hãy kiểm chứng source roots, execution bindings và nội dung archive thực tế thay vì chỉ nhìn `BUILD SUCCESS`.

## 22. Tham khảo

- [Maven Source Plugin — Introduction](https://maven.apache.org/plugins/maven-source-plugin/)
- [Maven Source Plugin — Usage](https://maven.apache.org/plugins/maven-source-plugin/usage.html)
- [Maven Source Plugin 3.4.0 — jar-no-fork](https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html)
- [Maven Source Plugin 3.4.0 — jar](https://maven.apache.org/plugins/maven-source-plugin/jar-mojo.html)
- [Maven Source Plugin 3.4.0 — test-jar-no-fork](https://maven.apache.org/plugins/maven-source-plugin/test-jar-no-fork-mojo.html)
- [Maven Source Plugin — Configuration](https://maven.apache.org/plugins/maven-source-plugin/examples/configureplugin.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/)
- [Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
