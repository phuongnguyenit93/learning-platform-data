# Phân biệt build thành công lặp lại với artifact giống từng byte trong Maven

## 1. Câu hỏi nền tảng: hai lần BUILD SUCCESS có đồng nghĩa reproducible?

Bạn checkout cùng một dự án Java rồi chạy hai lần:

~~~bash
mvn clean verify
mvn clean verify
~~~

Cả hai lần đều kết thúc:

~~~text
BUILD SUCCESS
~~~

Bạn có thể kết luận rằng **các Maven goals đã được thực thi thành công trong hai invocation**, nhưng **chưa thể kết luận hai file JAR được tạo giống nhau từng byte**.

Để thấy sự khác biệt, hình dung:

~~~text
Lượt A:
  Maven status = BUILD SUCCESS
  Artifact     = target/repro-byte-demo-1.0.0.jar
  SHA-256      = H_A

Lượt B:
  Maven status = BUILD SUCCESS
  Artifact     = target/repro-byte-demo-1.0.0.jar
  SHA-256      = H_B
~~~

Nếu `H_A != H_B`, hai JAR chắc chắn **khác bytes**, dù cả hai đều compile thành công, JUnit tests pass và chương trình in cùng kết quả. Chỉ một timestamp được nhúng vào ZIP entry hoặc JAR manifest cũng đủ gây chênh lệch.

Ngược lại, `H_A = H_B` là bằng chứng mạnh rằng **hai files được đo** có cùng bytes (có thể đối chiếu trực tiếp bằng binary comparator). Nhưng nếu cả hai build dùng chung machine, working directory, JDK, cache và môi trường, bạn **chưa chứng minh** một bên thứ ba có thể tái tạo giống bytes ở môi trường khác.

Do đó, có ba mức độ phải phân biệt:

1. **Build thành công lặp lại** (*repeatable success*): các invocation Maven chạy thành công, trả exit `0` và các checks đã cấu hình pass.
2. **Artifact giống từng byte trong phép thử** (*byte-identical artifacts*): bạn thực sự giữ hai output và xác minh bằng SHA-256 hoặc phép so sánh bytes.
3. **Build tái lập độc lập** (*independently reproducible build*): một bên khác dùng cùng source code, build instructions và build environment đã định có thể tạo cùng các artifacts giống từng byte.

Định nghĩa chính thức của Apache Maven nhấn mạnh việc tái tạo **bit-by-bit identical copies of all specified artifacts** từ cùng source, environment và instructions. Bằng chứng mạnh hơn một cặp log BUILD SUCCESS là cần thiết.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

- Phân biệt build success, deterministic build, byte identity và reproducibility độc lập.
- Hiểu tại sao JAR/ZIP có thể khác bytes dù source và output chương trình có vẻ không đổi.
- Biết cách kiểm soát timestamp bằng `project.build.outputTimestamp` và `SOURCE_DATE_EPOCH`.
- Ghim Maven plugins/JDK/dependencies để giảm đầu vào không ổn định.
- Tạo dự án Maven 3.9.x/Java17/JUnit5 hoàn chỉnh, build/run được.
- Chạy hai clean builds và kiểm tra JAR bằng `sha256sum`, `cmp`, PowerShell `Get-FileHash` hoặc CMD `fc /b`.
- Biết khác biệt giữa hai lần trong cùng workspace và hai lần tại những checkout/runners độc lập.
- Biết dùng Maven Artifact Plugin `artifact:check-buildplan` và `artifact:compare` để chẩn đoán.
- Thiết kế quality gate CI thất bại khi Maven không pass hoặc artifact hashes khác.
- Nhận diện rủi ro từ timestamp, manifest, file ordering, resource filtering, generated code, line endings, absolute paths, JDK và mutable dependencies.

Bài sử dụng Maven **3.9.x**, JDK **17+**, Maven Compiler Plugin **3.14.1**, Resources Plugin **3.3.1**, Surefire **3.5.4**, JAR Plugin **3.4.2**, Clean Plugin **3.3.2** và JUnit Jupiter **5.11.4**. Đây là các versions ghim cho ví dụ, không phải khẳng định bản mới nhất.

---

## 2. Build success xác minh cái gì?

Trong Maven default lifecycle, `verify` bao gồm các phase trước nó như `compile`, `test` và `package`:

~~~text
validate
   |
   v
compile
   |
   v
test
   |
   v
package
   |
   v
verify
   |
   v
install
   |
   v
deploy
~~~

Với POM có compiler, Surefire và JAR Plugin:

~~~bash
mvn clean verify
~~~

thường sẽ biên dịch Java source, thực thi tests, tạo JAR và chạy những checks bind tới verify.

Nhưng Maven mặc định **không tự tính và so SHA-256 của JAR ở hai invocation**. Việc tests pass cũng không kiểm tra metadata thời gian bên trong archive.

### 2.1. Success là trạng thái của process

Ở góc nhìn CI, một command Maven trả code `0` thường được coi là thành công. Điều đó phụ thuộc vào:

- Các Maven phases/goals thực sự được gọi.
- Tests có bị skip bởi `-DskipTests` hoặc cấu hình khác không.
- Plugin có ignore failures không.
- Reactor có dùng `-fn` khiến status có thể bằng `0` dù module thất bại không.
- CI shell có giữ đúng exit code Maven hay đã bị `echo`/`tee` che mất.

Nếu chỉ muốn chứng minh bài tập sau đây, mỗi lượt cần **Maven build thực sự thành công** và có JAR mới từ invocation đó. Nếu một lượt fail, không so với JAR cũ và không báo reproducibility pass.

### 2.2. Những cách nhầm lẫn phổ biến

| Quan sát | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Hai lượt Maven BUILD SUCCESS | Build pass trong hai invocation | Artifact giống bytes |
| Cùng tên JAR | Artifact có cùng tên đường dẫn | Nội dung giống nhau |
| Cùng kích thước | File sizes bằng nhau | Từng byte bằng nhau |
| JAR liệt kê cùng class names | Cấu trúc logic gần giống nhau | Metadata/manifest/compressed bytes giống nhau |
| Chương trình in cùng stdout | Một behavior đã quan sát giống nhau | File JAR giống bytes |
| Hai SHA-256 giống nhau | Hai mẫu file có hash trùng; bằng chứng rất mạnh | Bên thứ ba đã rebuild độc lập |
| Hai JAR có `cmp` exit 0 | Hai mẫu giống từng byte | Chúng an toàn hoặc đúng chức năng |

**Kết luận phần này:** trạng thái Maven và trạng thái artifact là **hai trục kiểm chứng khác nhau**.

---

## 3. Deterministic output và reproducibility

Một build **deterministic** là build mà với cùng bộ input đã xác định, thuật toán tạo cùng output bytes.

Bạn có thể hình dung:

~~~text
JAR bytes = F(
    source tree,
    POM + profiles,
    Maven + plugins,
    dependency artifact bytes,
    compiler/JDK,
    environment variables,
    archive metadata,
    OS/filesystem behavior
)
~~~

Đây là công thức khái niệm, không phải Maven API. Nó giúp nhớ rằng source code chỉ là **một phần đầu vào**.

Nếu function `F` lại đọc thời gian hiện tại, random UUID hoặc user home path mà bạn không lưu trong input contract, hai lần build có thể cho output khác. Vì thế cần kiểm soát hoặc loại bỏ các nguồn nondeterminism.

### 3.1. Reproducibility cần xác định phạm vi

Một project có thể phát hành:

~~~text
main JAR
sources JAR
javadoc JAR
distribution ZIP
POM
detached signature
SBOM
container image
~~~

Không được tuyên bố “toàn bộ release reproducible” nếu mới so **main JAR**. Cần xác định chính xác artifacts phải giống bytes và cách đo từng loại. Một file signature có thể được tạo với timestamp hoặc nonce khác, ngay cả khi unsigned JAR giống nhau.

### 3.2. Rebuild độc lập khác cache equality

Nếu hai CI jobs chỉ download cùng một JAR từ cùng registry, hashes chắc chắn có thể trùng mà **không có lượt nào biên dịch từ source**. Điều đó chứng minh việc copy artifact nhất quán, không phải reproducible build.

Muốn chứng minh tái lập độc lập, phải có:

1. Source snapshot/commit đã định.
2. Build instructions và environment đủ rõ.
3. Hai lượt build thực sự biên dịch/đóng gói.
4. Một bên chạy ở setup độc lập đủ để phát hiện path/user/OS/toolchain leaks.
5. So sánh bytes của toàn bộ specified artifacts.
6. Lưu evidence/source identity, không chỉ một dòng green trong UI.

---

## 4. Vì sao JAR là nguồn nondeterminism phổ biến?

JAR là ZIP archive. Nó chứa Java class files, resources và metadata. Trong demo:

~~~text
repro-byte-demo-1.0.0.jar
  META-INF/
  META-INF/MANIFEST.MF
  META-INF/maven/vn.example/repro-byte-demo/pom.xml
  META-INF/maven/vn.example/repro-byte-demo/pom.properties
  release.properties
  vn/example/repro/App.class
~~~

Danh sách là cấu trúc mong đợi của một JAR thông thường; thứ tự hiển thị có thể khác nhau theo tooling.

Những thứ có thể làm bytes khác:

- Timestamp của ZIP entries.
- Thứ tự ghi entries vào ZIP central directory.
- Thuật toán hoặc tham số compression khác.
- Manifest có `Built-By`, `Build-Time` hoặc host-specific metadata.
- File permissions/extra fields/platform attributes.
- Sinh resource chứa epoch hiện tại, hostname, absolute path hoặc random UUID.
- Annotation processor sinh class/tên method trong thứ tự không ổn định.
- Generated POM metadata hoặc source/Javadoc files khác.
- Line endings/encoding khi dùng resource filtering.
- JDK compiler versions khác nhau tạo class files khác.

Không phải mọi phiên bản Maven/JAR Plugin đều mắc tất cả vấn đề này. Đây là **danh mục nguyên nhân cần điều tra** khi hashes không match.

### 4.1. Tại sao xem unzip -l chưa đủ?

~~~bash
unzip -l target/repro-byte-demo-1.0.0.jar
~~~

Lệnh cho xem entry names, sizes, timestamps nếu có `unzip`, nhưng không so toàn bộ compressed bytes. Hai archives có cùng entry list vẫn có thể khác manifest content hoặc ZIP extra fields.

### 4.2. Tại sao cùng stdout chưa đủ?

Một JAR có manifest timestamp khác vẫn có thể chạy:

~~~text
Maven BUILD / training
~~~

giống hệt JAR khác. Behavior equality trong một test case không phải byte equality.

---

## 5. project.build.outputTimestamp

Apache Maven hướng dẫn khai property trong POM:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Những Maven packaging plugins có hỗ trợ sẽ dùng nó để chọn timestamp **ổn định** cho archive entries thay vì thời điểm tạo file lúc chạy.

Giá trị phổ biến:

- ISO 8601 timestamp có timezone, ví dụ `2024-01-01T00:00:00Z`.
- Một số giây nguyên Unix epoch, ví dụ `1704067200` tương ứng thời điểm trên.

### 5.1. Tác dụng thực tế

Nếu plugin đóng gói JAR A lúc 10:31 và JAR B lúc 10:38, ZIP entries có thể có timestamps khác khi không chuẩn hóa. Nếu plugin áp dụng cùng `project.build.outputTimestamp`, phần timestamp metadata đó ổn định.

### 5.2. Giới hạn phải ghi nhớ

Property này **không tự sửa** code generator kiểu:

~~~java
String buildTime = java.time.Instant.now().toString();
String generatedId = java.util.UUID.randomUUID().toString();
String workstation = System.getProperty("user.name");
~~~

Nếu một plugin ghi các giá trị này vào file đóng gói, bytes vẫn có thể khác. Những dòng Java trên chỉ là **trích đoạn minh họa**, không thuộc chương trình runnable của bài.

### 5.3. Phải kiểm tra từng plugin

JAR Plugin, Source Plugin, WAR Plugin, Shade, Assembly, Javadoc và các plugin bên thứ ba có lịch sử hỗ trợ reproducible mode khác nhau. Không được suy ra tất cả tự dùng `project.build.outputTimestamp` từ việc một plugin đã hỗ trợ nó.

Maven hướng dẫn chạy:

~~~bash
mvn artifact:check-buildplan
~~~

Goal từ Maven Artifact Plugin giúp phát hiện một số plugin versions có vấn đề reproducibility **đã biết**. Nó không chứng minh mọi custom code generator đều deterministic hoặc toàn bộ artifact bytes đã match.

### 5.4. Maven 3 so với Maven 4

Bài này dùng Maven 3.9.x nên **khai property rõ**. Maven 4 có những thay đổi về default reproducible mode ở các phiên bản mới; không nên dựa vào những thay đổi ấy khi dự án đang chạy Maven 3, và không nên hứa plugin custom luôn có support.

---

## 6. SOURCE_DATE_EPOCH: timestamp có nguồn gốc ổn định

`SOURCE_DATE_EPOCH` là một chuẩn dùng số giây nguyên kể từ Unix epoch để biểu diễn thời điểm **gắn với source**, thường lấy từ commit/changelog, thay vì thời điểm build thực tế.

Trong Bash tại một Git checkout đầy đủ:

~~~bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
printf '%s\n' "$SOURCE_DATE_EPOCH"
~~~

Lệnh in số giây phụ thuộc commit, không có stdout cố định cho mọi repository.

Maven POM có thể dùng giá trị môi trường:

~~~xml
<properties>
    <project.build.outputTimestamp>${env.SOURCE_DATE_EPOCH}</project.build.outputTimestamp>
</properties>
~~~

Nhưng cần nhớ:

1. Cả hai build phải có `SOURCE_DATE_EPOCH` cùng giá trị, lấy từ cùng source revision.
2. Không để môi trường thứ hai thiếu biến và chấp nhận kết quả mặc định ngoài ý muốn.
3. Plugin đang tạo artifact phải hiểu Unix epoch seconds hoặc có configuration tương thích.
4. Với shallow clone, xác nhận commit timestamp và Git metadata đủ cho workflow.
5. Không dùng `date +%s` như timestamp của mỗi invocation nếu cần tái lập bytes giữa nhiều thời điểm.

Ví dụ runnable ở dưới sử dụng ISO timestamp cố định trong POM để đơn giản và không bắt buộc Git. Với release thật, team nên chọn timestamp do release workflow xác định từ source, không đặt một mốc giả bất biến cho mọi release mãi mãi.

### 6.1. SOURCE_DATE_EPOCH không tự chi phối mọi plugin

Một số phiên bản Maven archive tooling có fallback từ environment, nhưng không phải mọi plugin cũ đều tự đọc biến này. Với Maven 3.9.x, nên cấu hình `project.build.outputTimestamp` rõ và kiểm thử trên phiên bản plugin thật.

### 6.2. Vì sao không chọn epoch 0 trong mọi ZIP?

Một số ZIP tooling có giới hạn mốc timestamp/độ phân giải theo định dạng DOS time. Một mốc hợp lệ như 2024 trong demo tránh vấn đề clamp với archive timestamps quá cũ. Không giả định Java `jar`, Maven JAR Plugin và ZIP tool khác luôn tạo byte-identical archives dù cùng timestamp.

---

## 7. Dự án Maven/Java 17 runnable

Tạo đúng bốn file:

~~~text
repro-byte-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/repro/App.java
    │   └── resources/release.properties
    └── test/java/vn/example/repro/AppTest.java
~~~

Bạn cần Maven 3.9.x, JDK17+ với compiler và khả năng resolve JUnit/plugins lần đầu (qua mạng hoặc local Maven repository hợp lệ).

### 7.1. pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>repro-byte-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.repro.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là POM đầy đủ, không phải một snippet. Ghi chú:

- `project.build.outputTimestamp` giúp JAR Plugin có hỗ trợ cố định archive entry timestamp.
- `maven.compiler.release=17` là bytecode/API target cho Java17.
- `project.build.sourceEncoding=UTF-8` giảm sai lệch mã hóa source.
- Các plugins quan trọng trong default lifecycle đều có version cụ thể.
- JUnit Jupiter ở `test` scope nên không cần khi chạy ứng dụng main.
- `Main-Class` trong manifest cho phép chạy `java -jar`.
- Không có plugin tự tạo random build identifier hoặc nhúng timestamp vào resource.
- Ví dụ không tạo sources.jar/javadoc.jar; chỉ so main JAR trong các bước tiếp theo.

### 7.2. src/main/java/vn/example/repro/App.java

~~~java
package vn.example.repro;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String greeting() {
        return "Maven BUILD";
    }

    public static String channel() {
        Properties properties = new Properties();
        try (InputStream input =
                     App.class.getResourceAsStream("/release.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing release.properties");
            }
            properties.load(input);
            return properties.getProperty("channel");
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    public static void main(String[] args) {
        System.out.println(greeting() + " / " + channel());
    }
}
~~~

Class dùng chỉ Java standard library. Không lấy thời gian hoặc random để ảnh hưởng dữ liệu đóng gói. `Properties.load(InputStream)` đọc properties format của Java; ví dụ dùng ASCII key/value nên không cần chuyển đổi ký tự tiếng Việt.

### 7.3. src/main/resources/release.properties

~~~properties
channel=training
~~~

Resources Plugin copy file vào classpath. Không bật dynamic filtering cho file này trong ví dụ.

### 7.4. src/test/java/vn/example/repro/AppTest.java

~~~java
package vn.example.repro;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void greetingIsStable() {
        assertEquals("Maven BUILD", App.greeting());
    }

    @Test
    void channelComesFromPackagedResource() {
        assertEquals("training", App.channel());
    }
}
~~~

Có đúng hai `@Test`. Chúng kiểm tra chức năng và resource loading, **không phải phép thử SHA-256**.

### 7.5. Chạy baseline

Tại root project:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Khi toolchain và repository phù hợp, dự kiến:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là số liệu kỳ vọng từ ví dụ, không phải log đã được chạy trên máy người đọc.

Sau khi build thành công:

~~~bash
java -jar target/repro-byte-demo-1.0.0.jar
~~~

Stdout của chương trình **chính xác**:

~~~text
Maven BUILD / training
~~~

Maven `verify` không tự in dòng này; nó xuất hiện khi thực sự chạy main class bằng `java -jar`. Đây là một smoke test behavior riêng, không thay byte equality check.

---

## 8. Kiểm chứng tại chỗ: hai clean builds và hai file JAR

Từ root `repro-byte-demo` trong Bash/Linux:

~~~bash
mkdir -p checks

mvn -B -ntp clean verify
cp target/repro-byte-demo-1.0.0.jar checks/first.jar

mvn -B -ntp clean verify
cp target/repro-byte-demo-1.0.0.jar checks/second.jar
~~~

`checks` nằm ngoài `target` nên lần `mvn clean` sau không xóa bản sao trước.

### 8.1. Điều kiện tiên quyết quan trọng

Hai Maven invocations **đều phải pass**. Nếu lượt thứ hai fail, file `target/...jar` có thể không tồn tại hoặc có thể là output cũ nếu workflow không sạch; không sử dụng nó như artifact “lần thứ hai đã thành công”.

Dùng script với `set -e` hoặc kiểm tra status sau mỗi Maven command. Nếu một lệnh `cp` fail, cũng không được báo byte equality pass.

### 8.2. SHA-256 trên Linux

~~~bash
sha256sum checks/first.jar checks/second.jar
~~~

Hai giá trị hash sẽ bằng nhau nếu bytes match. **Không bịa ra hash cố định** trong bài, vì nó phải lấy từ file thật trên môi trường người học.

Trên macOS:

~~~bash
shasum -a 256 checks/first.jar checks/second.jar
~~~

### 8.3. So sánh từng byte

~~~bash
cmp -s checks/first.jar checks/second.jar
status=$?
printf 'compare_exit=%s\n' "$status"
~~~

`cmp -s` thường trả:

- `0` nếu files giống bytes.
- `1` nếu khác bytes.
- `2` nếu có lỗi đọc, file thiếu hoặc lỗi I/O khác.

Khi hai build pass và file hợp lệ, với POM/source môi trường kiểm soát tốt, **kỳ vọng**:

~~~text
compare_exit=0
~~~

Nhưng đây là kết quả dự đoán **phải đo thật**, không phải câu khẳng định mọi Maven/JDK/máy chắc chắn luôn như vậy. Nếu output khác, chuyển sang mục troubleshooting thay vì thay hash hay bỏ qua lỗi.

### 8.4. Script gate hoàn chỉnh cho Bash

~~~bash
#!/usr/bin/env bash
set -euo pipefail

mkdir -p checks

mvn -B -ntp clean verify
cp target/repro-byte-demo-1.0.0.jar checks/first.jar

mvn -B -ntp clean verify
cp target/repro-byte-demo-1.0.0.jar checks/second.jar

sha256sum checks/first.jar checks/second.jar
cmp checks/first.jar checks/second.jar

printf 'BYTE_IDENTICAL\n'
~~~

Nếu Maven, copy hoặc `cmp` thất bại, `set -e` dừng script và không in `BYTE_IDENTICAL`. Nếu mọi bước pass và files giống nhau, stdout cuối của script là:

~~~text
BYTE_IDENTICAL
~~~

Maven vẫn in nhiều log trước dòng đó; chỉ nói dòng **cuối của script** có giá trị trên, không coi đó là toàn bộ stdout.

**Giới hạn của bài 8:** hai lượt cùng workspace và cùng máy là local reproducibility check, **không phải** independent rebuild.

---

## 9. Kiểm tra bằng PowerShell và Windows CMD

### 9.1. PowerShell: SHA-256 hai file

~~~powershell
New-Item -ItemType Directory -Force checks | Out-Null

mvn -B -ntp clean verify
if ($LASTEXITCODE -ne 0) { throw "First Maven build failed" }
Copy-Item "target/repro-byte-demo-1.0.0.jar" "checks/first.jar"

mvn -B -ntp clean verify
if ($LASTEXITCODE -ne 0) { throw "Second Maven build failed" }
Copy-Item "target/repro-byte-demo-1.0.0.jar" "checks/second.jar"

$first = (Get-FileHash "checks/first.jar" -Algorithm SHA256).Hash
$second = (Get-FileHash "checks/second.jar" -Algorithm SHA256).Hash

Write-Output "first=$first"
Write-Output "second=$second"

if ($first -cne $second) {
    throw "Artifact SHA-256 mismatch"
}
Write-Output "BYTE_IDENTICAL"
~~~

PowerShell `Get-FileHash` tạo SHA-256 của file; so hai chuỗi hash trùng là bằng chứng thực hành mạnh về byte equality. Trong pipeline yêu cầu binary comparer chính xác, bổ sung công cụ so byte phù hợp.

### 9.2. Windows CMD: hash và so binary

~~~bat
certutil -hashfile checks\first.jar SHA256
certutil -hashfile checks\second.jar SHA256
fc /b checks\first.jar checks\second.jar
echo compare_exit=%ERRORLEVEL%
~~~

`fc /b` so file binary. Cần bảo đảm bạn đã tạo `checks/first.jar` và `checks/second.jar` từ **hai Maven invocations đã pass**. Output của `certutil`/`fc` có thể tùy ngôn ngữ Windows, không ghi một bản stdout cố định.

Khi viết script CMD có nhiều lệnh trong block ngoặc, `%ERRORLEVEL%` có thể được expand sớm. Đọc code đúng lúc hoặc dùng delayed expansion thích hợp, không để `echo` che status Maven.

### 9.3. Khác nhau giữa lệnh các shell

`sha256sum` thường không có sẵn trong Windows CMD; `Get-FileHash` là PowerShell cmdlet; `fc /b` là công cụ Windows. Lỗi “command not found” không chứng minh JAR khác bytes — chỉ cần dùng đúng công cụ hệ điều hành.

---

## 10. Hai source trees sạch nhưng vẫn ở cùng máy

Giả sử bốn file ví dụ đã được commit trong một Git repository. Trên Linux/macOS, tạo hai checkout chỉ gồm source committed tại HEAD:

~~~bash
A="$(mktemp -d)"
B="$(mktemp -d)"

git archive --format=tar HEAD | tar -xf - -C "$A"
git archive --format=tar HEAD | tar -xf - -C "$B"

(
  cd "$A"
  mvn -B -ntp clean verify
)

(
  cd "$B"
  mvn -B -ntp clean verify
)

sha256sum \
  "$A/target/repro-byte-demo-1.0.0.jar" \
  "$B/target/repro-byte-demo-1.0.0.jar"

cmp \
  "$A/target/repro-byte-demo-1.0.0.jar" \
  "$B/target/repro-byte-demo-1.0.0.jar"
~~~

Đây là **ví dụ Bash**, yêu cầu Git, tar và các files đã được commit. `git archive HEAD` không chứa những thay đổi chưa commit hoặc file untracked. Nếu một Maven command fail, dừng trước khi so hashes; khi chuyển thành CI script dùng `set -euo pipefail`.

### 10.1. Nó cải thiện điều gì?

Hai directories khác nhau có thể phơi bày generator vô tình nhúng `project.basedir` hay absolute path vào artifact. Tuy nhiên hai build vẫn chạy cùng OS/JDK/Maven và thường dùng chung `~/.m2`, nên mức chứng minh **mạnh hơn hai lần cùng directory nhưng chưa độc lập hoàn toàn**.

### 10.2. Independent rebuild thực sự cần thêm gì?

Một cách tiếp cận:

- Chạy trong hai runners/containers hoặc máy khác nhau do các bên độc lập quản lý.
- Cố định cùng commit/tree, toolchain image digest và lệnh build.
- Xác minh cả hai thật sự rebuild, không copy artifact có sẵn từ registry.
- Kiểm soát repository dependencies/plugins và ghi checksums.
- Tạo hashes cho **tất cả artifacts trong phạm vi**.
- Lưu environment evidence để kiểm toán được.

Nếu chỉ kiểm chứng trên Linux với JDK17, không tuyên bố artifacts chắc chắn giống bytes khi build trên Windows hoặc JDK21; đó là phạm vi **chưa được đo**.

---

## 11. Phản ví dụ: hai BUILD SUCCESS nhưng hash khác

Dùng **bản sao** của project, thêm một manifest entry có thời gian thay đổi theo invocation. Trong `maven-jar-plugin` đã có `<archive>`, thêm:

~~~xml
<manifestEntries>
    <Build-Time>${maven.build.timestamp}</Build-Time>
</manifestEntries>
~~~

Maven cung cấp `maven.build.timestamp` dưới dạng một property liên quan build session. Khi được đưa vào `META-INF/MANIFEST.MF`, giá trị có thể khác giữa hai invocation thực hiện ở các thời điểm đủ cách biệt.

**Cần thử đúng cách:**

1. Sửa POM **một lần**, giữ nguyên POM này trong cả hai lượt.
2. Build sạch và sao lưu JAR A.
3. Chạy lại sau khoảng thời gian đủ để timestamp đổi; sao lưu JAR B.
4. So hashes và binary compare.
5. Mở manifests của A/B; nếu `Build-Time` khác, bạn đã tìm được nguồn nondeterminism.

Không được so JAR **trước khi sửa POM** với JAR **sau khi sửa POM** rồi nói “cùng source mà không tái lập”: đầu vào POM đã thay đổi, như vậy là phép so sánh không hợp lệ.

### 11.1. Vì sao outputTimestamp không sửa được?

`project.build.outputTimestamp` giúp chuẩn hóa **archive entry metadata timestamp**. Nó không tự rewrite một custom manifest field `Build-Time` được tính từ `maven.build.timestamp`. Hai JAR có thể cùng ZIP entry dates nhưng nội dung manifest khác.

Main method của cả hai vẫn có thể in:

~~~text
Maven BUILD / training
~~~

Tức là success và functional behavior có thể giống, còn bytes khác.

### 11.2. Một nguồn khác: code generator

Một generator viết dữ liệu kiểu:

~~~java
String buildTime = java.time.Instant.now().toString();
String generatedId = java.util.UUID.randomUUID().toString();
~~~

vào file `target/classes/build-data.properties` trước khi đóng gói cũng làm output khác mỗi run. Đoạn Java này là **minh họa nguyên nhân**, không phải chương trình chạy độc lập; project thực tế cần định nghĩa đường dẫn và cơ chế ghi file.

Quan trọng: gọi `Instant.now()` ở **runtime của ứng dụng** không tự làm JAR khác bytes. Chỉ khi thời điểm được nhúng vào **output build** mới gây vấn đề này.

---

## 12. Điều tra sự khác biệt ở cấp JAR

Nếu `cmp` trả khác nhau, không thay hash bằng tay hoặc thêm `|| true` để CI xanh.

Bắt đầu với:

~~~bash
jar tf checks/first.jar
jar tf checks/second.jar
~~~

Nếu hệ thống có `unzip`:

~~~bash
unzip -l checks/first.jar
unzip -l checks/second.jar

unzip -p checks/first.jar META-INF/MANIFEST.MF
unzip -p checks/second.jar META-INF/MANIFEST.MF
~~~

Kiểm tra:

- ZIP entry names và ordering.
- Timestamps của archive entries.
- Manifest entries: Main-Class, Built-By, Build-Time, Class-Path...
- Resource bytes và filtered properties.
- Maven `pom.properties`, descriptors và generated metadata.
- `App.class` binary khác do JDK/compiler/generator.

`jar tf` và `unzip -l` không so toàn bộ bytes; chúng chỉ hỗ trợ khoanh vùng.

### 12.1. Dùng diffoscope

Nếu đã cài `diffoscope`:

~~~bash
diffoscope checks/first.jar checks/second.jar
~~~

Diffoscope là **công cụ ngoài Maven/JDK**, có thể phân rã các archive để mô tả differences. Nếu không cài, bài vẫn thực hành được bằng hashes, `cmp` và `jar`/`unzip`.

### 12.2. Nếu class files khác?

Đọc log compiler version/options, kiểm tra Java compiler JDK, annotation processors, generated sources, source charset và mối liên hệ với absolute path. Nếu build chạy JDK17 và JDK21, dù dùng cùng `--release 17` vẫn không được mặc định class bytes sẽ giống.

### 12.3. Nếu manifest giống mà hashes khác?

Khảo sát ZIP metadata, entry order, compression format/parameters, generated resource và attached artifacts. Không khẳng định JAR "không tái lập vì timestamp" nếu timestamp đã ổn định; cần điều tra evidence thật.

---

## 13. Maven Artifact Plugin: kiểm tra build plan và so sánh

Apache Maven có hướng dẫn:

~~~bash
mvn artifact:check-buildplan
~~~

Goal này kiểm tra build plan để tìm các plugin có vấn đề reproducibility **đã biết**, giúp đề xuất nâng cấp hoặc xem xét cấu hình. Nó không tự tính equal hashes giữa hai JAR.

### 13.1. Dùng local artifact làm reference

Quy trình Maven hướng dẫn:

~~~bash
mvn clean install
mvn clean verify artifact:compare
~~~

Ý tưởng:

- Invocation thứ nhất build và install artifact vào local Maven repository làm reference.
- Invocation thứ hai rebuild qua verify, rồi plugin goal `artifact:compare` so output với reference.
- Plugin có thể tạo file báo cáo so sánh, tùy version và config.

Đây là phép thử **local reference**, vẫn chưa loại username, current directory và hidden environment leaks. Thực sự muốn nói bên thứ ba reproducible thì phải rebuild ở setup khác.

### 13.2. Kiểm tra plugin goal version

`artifact:compare` là goal của Maven Artifact Plugin, không phải core Maven phase. Trong build production nên pin phiên bản plugin được hỗ trợ và xem `mvn artifact:help`/goal documentation. Một số phiên bản Plugin có `artifact:buildinfo`, `artifact:describe-build-output`; documentation mới có thể đánh dấu buildinfo là deprecated. Đừng nhầm các goals với `maven-jar-plugin`.

### 13.3. So với staging artifacts

Trong release candidate verification, một bên có thể rebuild rồi so với reference ở staging repository bằng `artifact:compare` và URL reference được cấp quyền. Bài này **không cần đăng artifacts lên remote repository**, và không yêu cầu secrets để thực hành.

---

## 14. Dependencies và plugins phải ổn định

Cùng POM string chưa chắc dependency input bytes ổn định mãi mãi.

### 14.1. Dynamic versions và version ranges

Snippet sau là **ví dụ không nên dùng cho release yêu cầu reproducible**:

~~~xml
<version>[1.0,2.0)</version>
~~~

Một repository có artifact mới nằm trong range có thể khiến Maven resolve version khác ở lần build sau. Source code không đổi nhưng classpath hoặc fat JAR đã đổi.

Trong release tái lập, ưu tiên pinned versions, dependencyManagement/BOM được kiểm soát và lưu dependency graph/checksums.

### 14.2. SNAPSHOT mutable

`1.0.0-SNAPSHOT` có thể được publish nhiều lần với nội dung khác. Hai local Maven repositories có thể lưu hai SNAPSHOT bytes khác nhau dưới một tọa độ logic. Cùng version string **không đủ chứng minh** cùng dependency bytes.

### 14.3. Plugin version drift

Nếu một plugin chưa được pin, Maven/parent POM/build setup có thể chọn version khác; plugin mới cũng có thể đổi JAR metadata/compression. Ghim cả Compiler/Resources/JAR/Source/Assembly/Shade cùng những plugins nào thực sự tạo output.

### 14.4. Offline không đồng nghĩa reproducible

~~~bash
mvn -o clean verify
~~~

Offline mode dùng local cache, không chứng minh cache ở máy A và B có cùng dependency bytes. Nếu cần so độc lập, ghi checksum/provenance hoặc dùng repository artifacts bất biến.

### 14.5. JDK và compiler

Mặc dù `maven.compiler.release=17`, JDK17 và JDK21 có thể tạo class bytes khác. Java release target nói về compatibility target, **không phải hợp đồng binary-identical output qua mọi compiler/JDK major**.

---

## 15. OS, file order, encoding và đường dẫn

Nhiều lỗi chỉ xuất hiện khi so Linux với Windows hoặc khi đổi checkout directory:

- LF vs CRLF trong resource files.
- Source encoding/default charset.
- Local timezone/locale trong resource filtering.
- Thứ tự file được filesystem trả về.
- File permission/ZIP extra metadata.
- Generated Java source có absolute path.
- Compiler flags/annotation processors khác.
- CPU architecture và native libraries.
- Build cache hoặc temp directory cũ.
- Parallel builds không kiểm soát thứ tự sinh file.

### 15.1. Định nghĩa input và giới hạn phạm vi kiểm thử

Nếu bạn kiểm reproducibility “giữa Linux runners chạy JDK17”, đó là một tuyên bố rõ. Đừng mở rộng thành “mọi OS/JDK” khi chưa đo.

### 15.2. Normalization có lựa chọn

- Khai UTF-8 source/resources khi cần.
- Dùng Git attributes cho text line endings.
- Đặt stable output timestamp.
- Tránh ghi current time/random/user/path vào build outputs.
- Chọn plugin hỗ trợ deterministic ordering.
- Ghi rõ JDK/Maven/plugins và platform.
- Không áp dụng text normalization lên binary files.

### 15.3. SOURCE_DATE_EPOCH là đầu vào kiểm soát

Khi cần derive từ Git:

~~~bash
git log -1 --format=%ct
~~~

Chỉ dùng timestamp ấy khi checkout có metadata đúng và toàn bộ pipeline truyền cùng giá trị. Nếu runner A dùng HEAD khác runner B, khác hash không chứng minh tool nondeterministic vì **source/input thực chất đã khác**.

---

## 16. Chữ ký số, provenance và security

Ba phép kiểm chứng:

| Phép kiểm | Trả lời điều gì? | Không thay thế điều gì? |
| --- | --- | --- |
| Maven tests | Các tests đã cấu hình pass | Byte identity |
| SHA-256/cmp | Hai file đã đo có cùng bytes | Tính đúng/an toàn/source identity |
| Rebuild độc lập | Source+environment+instructions có thể tạo lại bytes | Code review/security scan |
| Chữ ký số | Xác nhận theo trust model của signer | Tính tái lập từ source |
| SBOM/scanning | Phân tích components/rủi ro/policy | Binary comparison |

Chữ ký hoặc attestation có thể chứa timestamp/nonce; nếu yêu cầu chữ ký cũng byte-identical, phải nêu rõ và thiết kế riêng. Không tự loại signature ra khỏi release scope chỉ để đạt tiêu chí khi policy yêu cầu ký.

Một bản binary có thể được tái tạo hoàn hảo nhưng vẫn chứa lỗ hổng hoặc bug. Reproducibility **tăng khả năng kiểm chứng supply chain**, không thay thế test/security review.

---

## 17. Pipeline CI kiểm reproducibility có thể tổ chức như sau

~~~text
Checkout exact commit
       |
       +--> Build A ở runner/workspace 1
       |        |
       |        +--> artifacts A + SHA-256
       |
       +--> Build B ở runner/workspace 2
                |
                +--> artifacts B + SHA-256
                        |
                        v
              Compare exact artifact set
                        |
          +-------------+-------------+
          |                           |
      MISMATCH                     MATCH
          |                           |
          v                           v
      CI FAIL                  Reproducibility evidence
      Save diff                (vẫn phải test/security)
~~~

Một quality gate nghiêm túc nên kiểm:

1. Hai jobs dùng cùng commit tree.
2. Cùng build instructions, selected profiles và release identity.
3. JDK/Maven/plugin/dependency identities được lưu.
4. Mỗi job thực sự build, không chỉ copy binary từ repository.
5. Process exit và test reports đều đạt.
6. So đúng artifact filenames/GAV/classifier/extension.
7. Hash hoặc binary mismatch khiến CI **nonzero**.
8. Sau pass vẫn cần các security, policy và release checks khác.

### 17.1. Bash gate không nuốt lỗi

Sai:

~~~bash
cmp checks/first.jar checks/second.jar || true
echo "PASS"
~~~

`|| true` che mismatch. Đúng:

~~~bash
if cmp -s checks/first.jar checks/second.jar; then
    echo "BYTE_IDENTICAL"
else
    echo "BYTE_MISMATCH"
    exit 1
fi
~~~

Với production script, có thể tách riêng status 1 (different files) và 2 (I/O error), nhưng cả hai đều **không được pass gate**.

### 17.2. Không dùng -fn hoặc skipTests làm giấy chứng nhận release

~~~bash
mvn -fn -DskipTests package
~~~

là command **không phù hợp** để chứng minh tất cả required tests pass. `-fn` có thể che project failures ở exit code, còn `-DskipTests` bỏ thực thi tests. Nếu cần riêng reproducibility stage, hãy gọi đúng phạm vi kiểm và vẫn có test gate độc lập; không gọi đó là tổng chất lượng build.

---

## 18. Phân biệt các Maven phases và phép so sánh bytes

| Command | Đầu ra chính | Tự so artifact với lần trước? |
| --- | --- | --- |
| `mvn clean` | Xóa `target` theo Clean Plugin | Không |
| `mvn package` | Tạo package/JAR | Không |
| `mvn verify` | Chạy tới verify và các checks bind | Không |
| `mvn install` | Install vào local Maven repo | Không |
| `mvn deploy` | Publish remote Maven repo | Không |
| `mvn clean verify artifact:compare` | Plugin goal so với reference cấu hình | Có đối chiếu |
| `sha256sum`/`cmp` | So hai files cụ thể | Có |

### 18.1. Vì sao clean chưa đủ?

`mvn clean` thường xóa `target`, nhưng không xóa `~/.m2/repository`, build caches khác hoặc generated files nằm ngoài target. Nếu custom plugin dùng trạng thái ở đó, clean build vẫn có thể phụ thuộc cache. Reproducibility yêu cầu bạn biết và kiểm soát các inputs này.

### 18.2. Vì sao install có thể ảnh hưởng thử nghiệm?

`mvn install` ghi reference artifact vào local repository. Nếu chạy `artifact:compare`, hiểu nó đang so với cái gì. Nếu local repo đã có artifact cũ cùng GAV, bạn có thể vô tình so với sai reference. Đọc logs, file timestamps và artifacts thực thay vì chỉ nhìn tên phiên bản.

### 18.3. Remote deploy không chứng minh reproducibility

`mvn deploy` tải artifact lên remote repo; nó không tự rebuild ở một môi trường khác hoặc tính hash equality với một release candidate reference. Repository còn có metadata/checksums/signatures riêng; phân biệt artifact content với toàn bộ trạng thái repository.

---

## 19. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm chứng |
| --- | --- | --- |
| Hai BUILD SUCCESS nhưng SHA khác | Metadata hoặc content nondeterministic | SHA/cmp, diffoscope |
| ZIP timestamps khác | outputTimestamp thiếu/plugin chưa hỗ trợ | Xem JAR Plugin, effective POM |
| Manifest Build-Time khác | Nhúng build-session timestamp | Inspect META-INF/MANIFEST.MF |
| Main JAR match nhưng sources JAR khác | Source Plugin hoặc source timestamps | So riêng sources JAR |
| .class khác | Compiler JDK hoặc codegen thay đổi | So toolchain/bytecode |
| release.properties khác | Filtering/env/newline thay đổi | So resource bytes và configuration |
| JAR giống tên/size nhưng cmp khác | Metadata/file bytes khác | Không dùng size làm bằng chứng |
| Hash match tại chỗ nhưng khác ở CI | Path/user/OS/locale/toolchain leak | Build ở checkout khác và runner khác |
| SNAPSHOT resolution khác | Repo metadata/artifact mutable | Pin/check dependency checksums |
| Build thứ hai fail | Environment hoặc tests fail | Sửa lỗi build, không dùng artifact cũ |
| artifact:check-buildplan sạch nhưng SHA khác | Custom generator hoặc issue chưa biết | Inspect ZIP/diffoscope |
| ZIP entry order khác | Filesystem ordering/plugin behavior | Xem plugin reproducible support |
| SHA khác nhưng chương trình chạy như cũ | Metadata đổi, functional behavior vẫn ổn | Phân biệt behavior/bytes |
| SOURCE_DATE_EPOCH không có ở runner | Variable chưa được cấp | Cấu hình CI bắt buộc và assert value |
| Windows CRLF khác Linux LF | Checkout/newline normalization | Dùng .gitattributes phù hợp |
| JDK17 và JDK21 tạo class khác | Compiler version khác | Pin compiler JDK cho phép thử |
| CI in BYTE_IDENTICAL dù mismatch | Script `|| true` hoặc status mất | Kiểm tra exit code thực |
| Hash bằng nhưng không rebuild | Dùng cùng cached binary | Xác minh compile/package logs |
| Reproducible nhưng có lỗ hổng | Reproducibility không phải security scan | Thêm code/dependency review |

### 19.1. Quy trình debug tám bước

1. So đúng source commit, POM/profile và các artifact identities.
2. Chắc chắn mỗi Maven invocation pass và tạo output mới.
3. Tính SHA-256; kiểm tra binary equality.
4. Inspect ZIP entries và manifest.
5. Nếu metadata giống, so resources/classes.
6. Kiểm tra plugin versions, compiler JDK và dependencies.
7. Dùng `artifact:check-buildplan`/diffoscope để tìm nguồn nondeterminism.
8. Sửa nguồn và rebuild lại **hai phía** để lập evidence mới.

---

## 20. Các bài tập thực hành

### Bài A — Định nghĩa

Hai lần `mvn clean verify` đều pass nhưng không lưu JAR lượt đầu. Bạn biết điều gì và còn thiếu bằng chứng gì để nói byte-identical?

### Bài B — Chạy Java 17

Tạo bốn files của mục 7, chạy Maven build rồi `java -jar target/repro-byte-demo-1.0.0.jar`. Xác nhận 2 JUnit tests PASS, stdout chính xác `Maven BUILD / training`.

### Bài C — So hai JAR tại chỗ

Chạy script mục 8. Tính `sha256sum`/`cmp`. Vì sao một phép thử cùng workspace chưa chứng minh bên khác có thể tái tạo?

### Bài D — PowerShell

Dùng `Get-FileHash` cho `first.jar`/`second.jar`. Nếu build thứ hai thất bại, có được dùng cached JAR để thông báo equal hash không?

### Bài E — Manifest bất ổn

Trong bản sao project, thêm `<Build-Time>${maven.build.timestamp}</Build-Time>` vào `<archive>`. Từ cùng POM đã sửa, chạy hai invocation cách nhau đủ thời gian. Inspect manifest và hashes. Vì sao outputTimestamp không sửa tùy biến manifest content?

### Bài F — Hai source trees

Dùng `git archive HEAD` vào hai temp directories. Điều gì xảy ra với files chưa commit? Phép thử này loại được leak loại nào, còn leak nào vẫn ẩn?

### Bài G — Plugin version

Dùng `mvn artifact:check-buildplan`. Nếu goal này không phát hiện vấn đề, có được bỏ so bytes không? Vì sao?

### Bài H — Reference compare

Chạy `mvn clean install`, rồi `mvn clean verify artifact:compare`. Cặp build này tham chiếu artifact nào? Tại sao chưa đủ chứng minh independent rebuild?

### Bài I — Dependency SNAPSHOT

POM vẫn trỏ `1.0.0-SNAPSHOT` nhưng repository publish lại artifact. Vì sao source version string không đổi mà JAR byte hash có thể đổi?

### Bài J — JDK release

Cùng project dùng `--release 17`, build một lần bằng JDK17 và lần khác bằng JDK21. Có cam kết classfile bytes giống không? Cần kiểm chứng thế nào?

### Bài K — Không phải correctness

Hai JAR byte-identical nhưng cùng chứa bug. Điều gì đã được chứng minh và chưa được chứng minh?

### Bài L — Attached artifacts

Release có main JAR, sources.jar, javadoc.jar, distribution.zip. Nếu chỉ main JAR byte-identical, team có thể tuyên bố toàn bộ release reproducible không?

### Bài M — CI gate

Viết script trả exit nonzero khi Maven build fail hoặc hashes khác, lưu logs/commit/JDK và báo đúng phạm vi “two-run local check” hoặc “independent rebuild”.

### Bài N — SOURCE_DATE_EPOCH

Dùng `git log -1 --format=%ct` để tạo cùng giá trị trên hai runners. Nếu runner B không cấp biến hoặc checkout HEAD khác, khác biệt đó là tool nondeterminism hay input mismatch?

### Bài O — Security

Vì sao reproducible build và SHA equality không thay code review, signing/provenance, SBOM và security scans?

---

## 21. Checklist cho một build Maven cần tái lập

- [ ] Đã nêu chính xác artifact set phải giống byte.
- [ ] Source tree/commit được cố định, không còn untracked inputs ảnh hưởng build.
- [ ] POM/plugins/dependencies có versions được kiểm soát.
- [ ] JDK/Maven/toolchain và selected profiles được ghi lại.
- [ ] `project.build.outputTimestamp` có giá trị ổn định, plugin đóng gói hỗ trợ nó.
- [ ] Nếu dùng `SOURCE_DATE_EPOCH`, giá trị hợp lệ và giống nhau giữa runners.
- [ ] Không nhúng now/random/username/absolute paths vào output.
- [ ] Encoding/newline/order/OS assumptions được kiểm soát.
- [ ] Hai lượt build thật sự chạy từ source và đều pass.
- [ ] JUnit tests đã chạy, không bị `-DskipTests` che.
- [ ] Giữ riêng bản sao JAR A và B trước khi clean lượt tiếp theo.
- [ ] SHA-256/binary comparison thực sự được kiểm tra, mismatch khiến CI fail.
- [ ] Có kiểm tra hai checkout khác nhau; khi tuyên bố độc lập có runner/setup độc lập.
- [ ] Đã kiểm tra artifacts kèm classifier (sources/Javadoc/ZIP) nếu thuộc release scope.
- [ ] Nếu mismatch, lưu diffoscope/report và điều tra plugin/generator.
- [ ] Không nhầm reproducibility với việc artifact an toàn hoặc chạy đúng.
- [ ] Lưu source identity, build environment và hashes như release evidence.

**Kết luận:** `BUILD SUCCESS` lặp lại là bằng chứng rằng Maven đã hoàn thành các bước được cấu hình, **không phải** bằng chứng file JAR giống từng byte. Muốn kiểm chứng artifact byte-identical, phải lưu hai file thực và so bằng SHA-256/`cmp`. Muốn tuyên bố reproducible build theo nghĩa độc lập, phải tái dựng từ cùng source/instructions/environment ở setup khác và so **tất cả specified artifacts**. Maven hỗ trợ chuẩn hóa archive timestamps qua `project.build.outputTimestamp`, nhưng việc loại bỏ nondeterminism và kiểm tra bytes vẫn là trách nhiệm của quy trình build và CI.

## 22. Tài liệu chính thức và công cụ tham khảo

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): định nghĩa, `project.build.outputTimestamp`, `artifact:check-buildplan`, `artifact:compare` và giới hạn của local test.
- [Maven JAR Plugin — jar:jar](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html): `outputTimestamp` và JAR configuration.
- [Maven Source Plugin — source:jar](https://maven.apache.org/plugins/maven-source-plugin/jar-mojo.html): `outputTimestamp` cho sources JAR.
- [Maven Artifact Plugin — Plugin Goals](https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html): kiểm tra build plan, compare và build output metadata.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): package/verify/install/deploy.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): version resolution.
- [SOURCE_DATE_EPOCH Specification](https://reproducible-builds.org/specs/source-date-epoch/): epoch seconds ổn định từ source.
- [Reproducible Builds — Timestamps](https://reproducible-builds.org/docs/timestamps/): nondeterminism vì timestamps.
- [Reproducible Builds — SOURCE_DATE_EPOCH](https://reproducible-builds.org/docs/source-date-epoch/): cách cung cấp timestamp cho build tools.
- [diffoscope](https://diffoscope.org/): so sánh các archive binaries khi hashes khác.
