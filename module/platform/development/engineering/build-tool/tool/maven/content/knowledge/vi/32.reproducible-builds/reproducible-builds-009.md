# Truy vết đầu vào đến artifact bằng checksum và thông tin phiên bản trong Maven

## 1. Mục tiêu: chứng minh một JAR được tạo từ những đầu vào nào

Trong dự án Java sử dụng Maven, một bản build có thể tạo file `target/app-1.0.0.jar`, nhưng tên file đó **không trả lời đầy đủ** các câu hỏi quan trọng: mã nguồn ở commit nào, parent/BOM và dependencies nào được resolve, Maven/JDK/plugin versions nào đã chạy, profile nào được kích hoạt, file JAR cuối có đúng bytes như file đã kiểm thử và công bố hay không.

**Truy vết đầu vào đến artifact** (*build traceability*) nghĩa là có một tập bằng chứng liên kết:

1. **Nguồn:** repository + Git commit SHA + trạng thái working tree + nguồn sinh code nếu có.
2. **Cấu hình và công cụ:** POM/effective POM, plugins, parent/BOM, profiles, Maven distribution, JDK/toolchains và môi trường build quan trọng.
3. **Dependencies:** những GAV/classifier/type thực sự được resolve, nguồn repository và phiên bản đã chọn.
4. **Đầu ra:** artifact GAV, file bytes, SHA-256, attached artifacts, packaging, manifest và metadata version.
5. **Xác minh:** tests/QA đã chạy trên đúng source và artifact nào; ai/phần mềm nào thực hiện; evidence có đáng tin và có thể kiểm chứng độc lập hay không.

Chủ đề này nằm trong **Build tái lập**. Vì vậy cần phân biệt ba khái niệm:

- **Checksum:** dấu vân tay tính từ **bytes của một file**. Hai file có SHA-256 giống nhau (theo giả định hash an toàn) là bằng chứng mạnh rằng bytes giống nhau.
- **Reproducible build:** từ cùng source, build instructions và các điều kiện môi trường được xác định, có thể tạo lại **artifact giống nhau từng byte**.
- **Provenance/attestation:** bản mô tả có nguồn gốc đáng tin cho biết **ai/công cụ nào, ở đâu, từ input nào đã tạo ra digest nào**. Một checksum đứng riêng không xác thực người tạo hay source.

**Kết luận ngay từ đầu:** **GAV không phải checksum; checksum không phải Git commit; và cùng checksum chưa tự chứng minh artifact đáng tin nếu người kiểm chứng không có một nguồn digest/reference đáng tin.**

## 2. Bản đồ chuỗi bằng chứng từ source đến artifact

~~~text
Git repository + immutable commit SHA
                    |
                    v
           POM + parent/BOM + profiles
                    |
                    v
        Resolved dependencies + plugins
                    |
                    v
        Maven version + JDK + toolchain
                    |
                    v
         clean -> compile -> test -> package
                    |
                    +---- Test reports / quality gates
                    |
                    v
          target/traceable-build-demo-1.0.0.jar
                    |
                    +---- Embedded GAV/version metadata
                    |
                    +---- SHA-256 of exact JAR bytes
                    |
                    +---- CI build record / provenance
                    |
                    v
         Artifact repository (read back and verify)
~~~

Một bản release có thể dùng **Git tag** để gắn tên thân thiện cho commit. Tuy nhiên tag cần được xác minh nó **trỏ tới SHA nào**, không chỉ dựa vào tên `v1.0.0`.

**Cùng một GAV có thể tồn tại những bytes khác nhau nếu repository cho overwrite hoặc publisher vi phạm immutable release policy.** Vì vậy sau publish phải so SHA-256 của file tải lại với digest đã được ghi từ artifact được kiểm thử.

## 3. Năm lớp định danh không nên trộn lẫn

| Thuộc tính | Ví dụ | Trả lời câu hỏi nào? | Không chứng minh điều gì? |
| --- | --- | --- | --- |
| **GAV** | `vn.example.trace:traceable-build-demo:1.0.0` | Artifact nào trong hệ sinh thái Maven? | Không bảo đảm đúng bytes/source. |
| **Git SHA** | SHA đầy đủ của một commit được duyệt | Source revision nào được chọn? | Không tự mô tả toàn bộ dependencies/điều kiện build. |
| **SHA-256 của JAR** | 64 ký tự hex tính từ file thực | Những bytes nào được tạo/tải? | Không tự chứng minh nguồn, người ký, tính an toàn. |
| **Build environment/version record** | Maven, JDK, profiles, plugins, build runner | Với cấu hình/công cụ nào đã build? | Không thay kiểm chứng bytes. |
| **Provenance có xác thực** | Attestation gắn source/input và artifact digest | Ai/công cụ nào tuyên bố đã build digest này từ đầu vào nào? | Chỉ đáng tin theo trust policy và cơ chế ký/xác minh. |

Ví dụ hai nhóm cùng đưa `traceable-build-demo-1.0.0.jar` lên một kho tự quản, nhưng một nhóm đổi bytecode và giữ nguyên filename. **Tên không phân biệt được**, SHA-256 phân biệt được. Tuy nhiên nếu bên tấn công có thể đổi **cả JAR lẫn file `.sha256`** trên một website không tin cậy, việc so hai giá trị này không đủ để xác thực nguồn.

## 4. Những đầu vào cần chốt trước khi nói đến reproducibility

Một sơ đồ input theo thứ tự từ dễ nhìn thấy đến dễ bị bỏ sót:

| Nhóm đầu vào | Ví dụ | Có thể đổi bytes không? |
| --- | --- | --- |
| Source tracked | `src/main/java`, `src/main/resources`, `pom.xml` | Có. |
| Generated sources | OpenAPI/protobuf/annotation processor output | Có, kể cả khi Git không đổi. |
| Parent/BOM | `parent.version`, imported BOM version | Có, vì đổi plugin/dependency graph. |
| Resolved dependencies | `groupId:artifactId:version:type:classifier`, repository | Có nếu classpath/metadata thay đổi. |
| Plugin versions | Compiler, Resources, Jar, Shade, Assembly, Javadoc | Có. |
| JDK/toolchains | JDK vendor/version, javac options, `release` level | Có. |
| Maven/runtime | Maven version, plugins và extensions | Có trong một số trường hợp. |
| Profiles/flags | `-Pprod`, `-DskipTests`, filtering properties | Có. |
| Environment | Locale, timezone, OS, line endings, charset, filesystem | Có nếu plugin không chuẩn hóa. |
| Thời điểm | `Instant.now()`, manifest timestamp, ZIP timestamps | Có nếu nhúng wall-clock. |
| Repository state | Mutable SNAPSHOT hoặc release bị redeploy | Có, dù POM giữ nguyên. |
| CI variables | Build number, branch name, credentials, secrets | Có nếu được nhúng vào artifact; secret leakage là rủi ro lớn. |

**Tập đầu vào phải mô tả thực tế**, không chỉ `pom.xml`. Maven không có một lockfile chuẩn tích hợp tự động khóa toàn bộ graph giống một số hệ sinh thái khác. Nếu muốn kiểm soát nghiêm ngặt, cần ghi resolved dependency tree hoặc SBOM, dùng repository policy chống overwrite và kiểm tra cả transitive dependencies.

Không ghi secrets trong provenance public; các environment variables có thể được mô tả bằng **tên, policy hoặc digest an toàn** thay vì giá trị bí mật.

## 5. Checksum: tính đúng từ file và biết giới hạn

**SHA-256** là hàm băm mật mã tạo digest 256 bit, thường được hiển thị bằng **64 ký tự hex**. Nó không mã hóa nội dung và không cần private key.

Với một file JAR đã tạo thật:

**Linux/macOS:**

~~~bash
shasum -a 256 target/traceable-build-demo-1.0.0.jar
~~~

Hoặc trên môi trường Linux có `sha256sum`:

~~~bash
sha256sum target/traceable-build-demo-1.0.0.jar
~~~

**Windows PowerShell:**

~~~powershell
Get-FileHash target\traceable-build-demo-1.0.0.jar -Algorithm SHA256
~~~

Những lệnh trên **không có một chuỗi output hash cố định để chép từ tài liệu**: digest phải được tính trên file thật, sau build. Đừng dùng hash của source ZIP để thay hash của JAR, và đừng lấy hash thư mục thay cho hash artifact nếu công cụ không có một cách chuẩn hóa nội dung thư mục.

### `sha256sum` và `shasum` có kết quả khác nhau không?

Nếu cả hai dùng SHA-256 trên cùng file bytes, digest phải bằng nhau. **Cách trình bày output** có thể khác (tên file, chữ hoa/chữ thường, dấu `*`, dòng cuối), nhưng digest 256 bit tương ứng là cùng giá trị.

### Hash phải tính vào lúc nào?

1. **Sau** khi tất cả plugin đã hoàn tất packaging/transform/sign.
2. Trên **đúng artifact** sẽ lưu/publish, không phải JAR cũ ở `target`.
3. Trước khi upload, ghi digest vào evidence.
4. Sau khi download lại từ kho, tính digest lần nữa rồi đối chiếu.
5. Với nhiều classifiers (`sources`, `javadoc`, `all`, `dist`) hoặc POM artifacts, **mỗi file có digest riêng**.

**Không tự nhúng SHA-256 cuối cùng của chính JAR vào bên trong JAR đó**: sẽ tạo **vòng phụ thuộc tự tham chiếu** vì thay digest được nhúng làm thay bytes, từ đó đổi digest. Lưu digest của artifact cuối **bên ngoài** file, ví dụ CI artifact manifest hoặc attestation.

## 6. `project.build.outputTimestamp` và reproducible archives

ZIP/JAR lưu metadata về archive entries, thường gồm timestamps. Nếu cùng class files nhưng mỗi lần đóng JAR sử dụng thời điểm hiện tại, **SHA-256 toàn JAR có thể khác**.

Maven hỗ trợ property:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Với Maven Jar Plugin và các archive plugins tương thích, property này được dùng làm **timestamp cố định cho entries**. Giá trị có thể là thời gian ISO-8601 có timezone hoặc giây epoch kiểu `SOURCE_DATE_EPOCH` theo tài liệu plugin.

**Không coi đây là công tắc thần kỳ cho mọi plugin.** Nó không tự sửa nguồn chứa `new Date()`, class generator gắn timestamp, random UUID, map iteration nondeterminism, thông tin username/working directory hoặc dữ liệu mạng thay đổi theo thời gian.

### Chọn timestamp nào?

- Có thể chọn **một giá trị ổn định được định nghĩa trong POM** để dạy cơ chế, như bài mẫu.
- Với release thật, policy có thể chọn **thời điểm commit/release** dưới dạng value ổn định được truyền vào cùng bản build.
- Không chọn `now()` mỗi lần build nếu mục tiêu là bit-for-bit reproducibility.
- Nếu dùng `SOURCE_DATE_EPOCH`, đảm bảo toolchain/plugins thực sự sử dụng và truyền **cùng giá trị** ở các môi trường.

**Maven 3/4 và các plugin versions thay đổi theo thời gian**, nên kiểm tra effective configuration và khả năng hỗ trợ của đúng plugin version thay vì suy từ tên Maven.

## 7. Dự án demo: Java 17, GAV bên trong artifact, JAR timestamp cố định

Ta xây một dự án **một module**, không có dependency runtime ngoài JDK:

~~~text
traceable-build-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/trace/TraceApp.java
    │   └── resources/build-info.properties
    └── test/
        └── java/vn/example/trace/TraceAppTest.java
~~~

Bài học chốt Maven Compiler Plugin, Resources Plugin, Jar Plugin, Surefire và Artifact Plugin. Metadata phiên bản được filter từ POM vào `build-info.properties`; chương trình đọc chính file này từ classpath của JAR. **Source commit SHA không được nhúng trong JAR demo** — nó được gắn trong evidence bên ngoài để tránh dùng một giá trị biến động theo môi trường mà không kiểm soát.

Điều kiện thực hành: Maven 3.9+, JDK 17+, repository đáng tin truy cập được các plugin và JUnit đã chỉ định. Tài liệu mô tả expected output dựa trên mã; nó không khẳng định đã build trực tiếp trong workspace của người học.

### 7.1. `pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.trace</groupId>
    <artifactId>traceable-build-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Traceable Build Demo</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build-info.properties</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
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
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.trace.TraceApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-artifact-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích:**

1. GAV cố định là `vn.example.trace:traceable-build-demo:1.0.0`.
2. `maven.compiler.release=17` quy định Java language/API target; Maven vẫn phải chạy bằng JDK thích hợp.
3. `project.build.sourceEncoding=UTF-8` giúp compiler/resource handling không phụ thuộc default charset.
4. `project.build.outputTimestamp` ổn định metadata của JAR entries nhờ plugin hỗ trợ.
5. Resources Plugin chỉ filter **một file properties được định danh rõ** với delimiter `@`; không filter bừa file nhị phân.
6. Jar Plugin cấu hình Main-Class để chạy bằng `java -jar`.
7. JUnit Jupiter được dùng ở scope `test`, không thêm library runtime vào JAR.
8. Artifact Plugin được pin nhưng **không bind goal compare vào lifecycle**; người học gọi nó có chủ đích sau khi đã có reference artifact.
9. Ví dụ không cấu hình `distributionManagement`, nên các lệnh `verify` không có remote publish target; không cần và không được chạy `mvn deploy` để thử reproducibility.

**Về version plugin:** các con số phục vụ một baseline có thể kiểm tra; chúng **không được tuyên bố là bản mới nhất**. Để áp dụng production phải kiểm tra plugin requirements và chính sách versions của tổ chức.

## 8. Resource `src/main/resources/build-info.properties`

~~~properties
groupId=@project.groupId@
artifactId=@project.artifactId@
version=@project.version@
~~~

Maven Resources Plugin thay ba tokens lấy từ effective project model. Với POM ví dụ, file được package vào JAR phải có:

~~~properties
groupId=vn.example.trace
artifactId=traceable-build-demo
version=1.0.0
~~~

**Cần phân biệt đầu ra phiên bản với đầu vào nguồn:** metadata này nói JAR tự khai báo GAV nào, **không tự chứng minh Git SHA**. Một người có thể sửa POM và rebuild nhưng vẫn ghi version `1.0.0`. Đó là lý do còn cần digest và provenance độc lập.

File properties dùng values ASCII trong demo, nên `Properties.load(InputStream)` tương thích mà không có khó khăn chuyển mã tiếng Việt. Nếu muốn lưu Unicode phức tạp, cần thiết kế encoding/loader nhất quán.

**Không thêm `build.time=@maven.build.timestamp@` hoặc timestamp hiện tại vào file này nếu muốn hai bản build tại các thời điểm khác nhau có cùng bytes.** Một giá trị động như CI run ID cũng làm thay toàn JAR khi được filter vào nội dung.

## 9. Java 17 đọc metadata ngay trong JAR

Tạo `src/main/java/vn/example/trace/TraceApp.java`:

~~~java
package vn.example.trace;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class TraceApp {
    private TraceApp() {
    }

    private static Properties loadInfo() throws IOException {
        Properties info = new Properties();
        try (InputStream input =
                TraceApp.class.getResourceAsStream("/build-info.properties")) {
            if (input == null) {
                throw new IOException("Missing build-info.properties");
            }
            info.load(input);
        }
        return info;
    }

    public static String identity() throws IOException {
        Properties info = loadInfo();
        String groupId = info.getProperty("groupId");
        String artifactId = info.getProperty("artifactId");
        String version = info.getProperty("version");

        if (groupId == null || artifactId == null || version == null
                || groupId.isBlank() || artifactId.isBlank()
                || version.isBlank() || version.contains("@")) {
            throw new IllegalStateException(
                    "Unresolved artifact identity");
        }
        return groupId + ":" + artifactId + ":" + version;
    }

    public static String describe() throws IOException {
        return "ARTIFACT: " + identity();
    }

    public static void main(String[] args) throws IOException {
        System.out.println(describe());
    }
}
~~~

Class chỉ dùng Java standard library. `loadInfo()` giải phóng InputStream, kiểm tra resource tồn tại. Chuỗi GAV được dựng từ **bytes thực trong JAR/classpath**, không lấy version từ command-line parameter hay Git working directory.

**Giới hạn:** thông tin này vẫn là một tự khai báo từ producer. Khi cần attestation đáng tin, chính hệ thống CI phải đối chiếu GAV đó với POM đã build, Git SHA và digest của file cuối.

## 10. Unit test cho version metadata

Tạo `src/test/java/vn/example/trace/TraceAppTest.java`:

~~~java
package vn.example.trace;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TraceAppTest {
    @Test
    void metadataIsResolvedAndConsistent() throws Exception {
        String identity = TraceApp.identity();

        assertTrue(identity.matches(
                "vn\\.example\\.trace:traceable-build-demo:"
                + "\\d+\\.\\d+\\.\\d+(?:-SNAPSHOT)?"));
        assertFalse(identity.contains("@"));
        assertEquals("ARTIFACT: " + identity,
                TraceApp.describe());
    }
}
~~~

Test đảm bảo:

- Đúng group/artifact identity theo thiết kế demo.
- Version là chuỗi semantic-like `x.y.z` hoặc bản SNAPSHOT đúng pattern.
- Resource tokens đã được filter; không có ký hiệu `@` chưa resolve trong identity.
- Dòng mô tả sử dụng đúng GAV metadata.

**Không hardcode version `1.0.0` trong test nếu mục tiêu là tái sử dụng tests cho bản phát hành sau.** POM của ví dụ hiện tại chọn version đó để minh họa một GAV cụ thể, nhưng test vẫn chấp nhận version khác phù hợp policy.

Đây là một **unit test metadata**, không chứng minh toàn bộ JAR reproducible. Kiểm chứng SHA-256 và independent rebuild là bước riêng.

## 11. Build lần đầu và stdout đáng tin

Trong thư mục root `traceable-build-demo`:

~~~bash
mvn --version
mvn -B -ntp clean verify
java -jar target/traceable-build-demo-1.0.0.jar
~~~

Khi POM, Java files và resource được tạo đúng, stdout **chính xác của riêng lệnh `java -jar` cuối cùng**:

~~~text
ARTIFACT: vn.example.trace:traceable-build-demo:1.0.0
~~~

Maven output có thể khác nhau theo plugin version, cache và môi trường; không phải một transcript cố định. Với POM ví dụ, Surefire chạy một unit test method.

Các file chính thường gồm:

~~~text
target/classes/vn/example/trace/TraceApp.class
target/classes/build-info.properties
target/traceable-build-demo-1.0.0.jar
target/surefire-reports/...
~~~

Dấu `...` ở đây nghĩa là tên các file báo cáo thay đổi theo plugin, không phải file literal cần tồn tại. **`mvn clean verify` không phải remote deploy**.

## 12. Xác nhận metadata bên trong JAR

Liệt kê nội dung JAR:

~~~bash
jar tf target/traceable-build-demo-1.0.0.jar
~~~

Các entries cần tìm:

~~~text
META-INF/MANIFEST.MF
vn/example/trace/TraceApp.class
build-info.properties
~~~

Maven Jar Plugin có thể thêm những entries như `META-INF/maven/.../pom.xml` và `pom.properties`; hãy kiểm tra thực tế, đừng đoán từ một ví dụ cũ.

Chạy `java -jar` kiểm tra cả manifest `Main-Class` và resource lookup. Nếu chỉ chạy:

~~~bash
java -cp target/classes vn.example.trace.TraceApp
~~~

thì mới kiểm tra compiled classes/resources **trước packaging**, chưa chứng minh JAR có đủ files hoặc manifest đúng.

### Kiểm tra phiên bản bằng Maven Help Plugin

~~~bash
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
~~~

Với POM nguồn ví dụ, output mong đợi từ Help Plugin khi chạy thành công:

~~~text
1.0.0
~~~

**Không lấy riêng output Help Plugin làm bằng chứng JAR tương ứng được build từ POM hiện tại**: file ở `target/` có thể là artifact cũ. Dùng `clean verify`, chạy JAR thực tế, rồi hash file vừa sinh.

## 13. Thử hai build trong cùng working directory — Linux/macOS

Đây là **kiểm thử sơ bộ**, giúp phát hiện thay đổi bytes giữa hai lần build từ cùng source trong cùng điều kiện.

~~~bash
mvn -B -ntp clean verify
cp target/traceable-build-demo-1.0.0.jar ../traceable-reference.jar

mvn -B -ntp clean verify
shasum -a 256 ../traceable-reference.jar target/traceable-build-demo-1.0.0.jar
~~~

Hai dòng `shasum` phải in **cùng digest** nếu bytes giống nhau. Để kiểm chứng và in kết quả không phụ thuộc digest cụ thể:

~~~bash
if cmp -s ../traceable-reference.jar target/traceable-build-demo-1.0.0.jar; then
  printf 'MATCH\n'
else
  printf 'DIFFER\n'
fi
~~~

Nếu hai file giống từng byte, **stdout chính xác của `if` block** là:

~~~text
MATCH
~~~

Nếu khác bytes, stdout là:

~~~text
DIFFER
~~~

**Lưu ý:** File reference được lưu ngoài `target/` vì `mvn clean` sẽ xóa `target/` trước build thứ hai. Tên reference cố định ở thư mục cha chỉ thích hợp cho một sandbox bài học; trên CI dùng artifact store/thư mục riêng được quản lý, không ghi đè dữ liệu người khác.

**Đừng copy file reference ngay sau lần build thứ hai** — điều đó so file với chính nó, cho `MATCH` giả.

## 14. Thử hai build trong PowerShell

Windows PowerShell:

~~~powershell
mvn -B -ntp clean verify
Copy-Item target\traceable-build-demo-1.0.0.jar ..\traceable-reference.jar

mvn -B -ntp clean verify
$reference = (Get-FileHash ..\traceable-reference.jar -Algorithm SHA256).Hash
$current = (Get-FileHash target\traceable-build-demo-1.0.0.jar -Algorithm SHA256).Hash
if ($reference -eq $current) { 'MATCH' } else { 'DIFFER' }
~~~

Nếu cả hai SHA-256 giống nhau, output của lệnh cuối là `MATCH`. Phải **dừng nếu một lệnh Maven thất bại**; chạy các dòng PowerShell nối tiếp không mặc nhiên có shell `set -e` như Bash, nên trong automation hãy kiểm tra `$LASTEXITCODE` sau mỗi Maven invocation.

**Cần so SHA-256 của file thực, không phải chỉ so tên file hoặc số bytes.** Hai JAR có thể cùng size nhưng nội dung khác; SHA-256 sẽ phát hiện khác biệt với xác suất va chạm thực tế cực thấp trong điều kiện thông thường.

## 15. Local repeatability khác independent reproducibility

Hai lần build trong **cùng working directory**, sử dụng cùng `.m2` cache, JDK và environment có thể trùng bytes. Đó là dấu hiệu tốt nhưng **chưa đủ** để khẳng định người khác có thể tái tạo release.

Để thử độc lập nghiêm túc:

1. Chốt **Git commit SHA** của source được duyệt.
2. Hai builders tạo **checkout mới** từ cùng commit, không chia sẻ generated `target/`.
3. Dùng Maven/JDK/plugin/toolchain versions theo policy (có thể chạy hai OS để kiểm tra tính portable nếu sản phẩm yêu cầu).
4. Resolve dependencies từ repositories được kiểm soát; không dùng artifacts chưa publish chỉ có ở `.m2` cá nhân.
5. Chạy cùng profiles/flags và cùng `project.build.outputTimestamp`.
6. Build chính xác tập artifacts đã định, kể cả classifiers nếu được phát hành.
7. Tính SHA-256 riêng ở mỗi environment.
8. So digests và, nếu khác, điều tra *tại entry/file nào*.
9. Ghi lại builder identity, môi trường, dependencies và kết quả vào provenance/evidence.

**Định nghĩa reproducible chỉ áp dụng cho những artifacts và điều kiện build được chỉ rõ.** Nếu project phát hành JAR và nguồn Javadoc JAR nhưng mới so hash của JAR chính, chưa được tuyên bố toàn release reproducible.

### Đừng bỏ qua môi trường

Cùng SHA Git nhưng JDK vendor/version, locale, timezone, line endings, file permissions hoặc Maven plugin behavior khác nhau vẫn có thể tạo bytes khác. Reproducibility engineering là **giảm hoặc cố định các đầu vào biến động**, không chỉ lặp lại một lệnh.

## 16. Maven Artifact Plugin: `check-buildplan` và `compare`

Apache Maven có **Maven Artifact Plugin** hỗ trợ kiểm tra reproducible builds.

### Kiểm tra plugin buildplan

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-artifact-plugin:3.6.1:check-buildplan
~~~

Goal `artifact:check-buildplan` kiểm tra buildplan xem những plugins đang dùng có **vấn đề reproducible builds đã biết** không. Nó hữu ích để **phát hiện rủi ro sớm**, nhưng không tự chứng minh mọi output sẽ trùng byte.

### So build mới với artifact tham chiếu đã install

Trên **sandbox**, với cùng version `1.0.0`:

~~~bash
mvn -B -ntp clean install
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.6.1:compare
~~~

- Bước đầu tạo và **cài reference artifacts vào local Maven repository**; không deploy remote.
- Bước hai tạo output mới và gọi `artifact:compare`, so với reference đã có thể resolve, thường từ local repository trước.
- Plugin ghi thông tin so sánh vào file dạng `.buildcompare` và có thể trả BUILD FAILURE nếu có khác biệt, theo cấu hình `compare.fail`.
- Nếu **không có reference artifact**, repository resolution, version hoặc packaging khác, kết quả có thể là lỗi tìm reference chứ không phải JAR nondeterministic.

**Lưu ý:** goal `artifact:compare` có cơ chế dùng reference repo; để so một release đã publish, tham số `-Dreference.repo` có thể trỏ tới repository được cho phép, nhưng không dùng một URL production thiếu kiểm soát để thử. Không coi kết quả so sánh local là bằng chứng *independent* reproducibility.

### Các goal khác

- **`artifact:describe-build-output`** mô tả build output (experimental theo tài liệu plugin).
- **`artifact:buildinfo`** ghi build metadata nhưng ở các bản mới được xem là định dạng nội bộ/không phải giải pháp attestation universal; cần đọc cảnh báo version plugin.
- **`artifact:compare`** kiểm tra output khác biệt, không tự ký kết luận provenance hoặc upload artifact.

Đừng nhầm Maven Artifact Plugin với Maven Deploy Plugin, Dependency Plugin hoặc Maven Jar Plugin: mỗi plugin giải quyết một bước khác.

## 17. Đối chiếu đầu vào hiệu lực với POM nguồn

Một POM có thể kế thừa parent, import BOM, kích hoạt profile và dùng pluginManagement. Vì vậy danh sách `<dependency>` nhìn thấy ở root **không luôn là resolved graph cuối**.

Xem Maven/JDK:

~~~bash
mvn --version
java -version
~~~

Xem effective POM của bản build:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
~~~

Xem dependency graph:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Đọc:

~~~text
project/groupId
project/artifactId
project/version
project/parent
project/properties
project/dependencyManagement
project/dependencies
project/build/plugins
project/build/pluginManagement
project/profiles
~~~

**`dependencyManagement` không tự tạo dependency runtime.** Nếu chỉ ghi version trong managed catalog, nó chưa có nghĩa JAR cần runtime dependency đó. Ngược lại, một transitive dependency có thể thật sự ảnh hưởng compilation/runtime dù không hiện trực tiếp dưới `<dependencies>` của module nguồn.

### Pin version và repository identity

- Pin direct dependency/plugin/BOM/parent versions phù hợp chính sách.
- Với dependency có snapshot hoặc repository cho overwrite, cần xem **actual artifact checksums** được tải.
- Một GAV với release version cố định không chống được một repository manager bị cấu hình cho phép ghi đè.
- Maven settings mirrors có thể làm hai người resolve từ hai backend khác nhau dù POM giống nhau.
- Đánh dấu repository URL/ID và policy trong build evidence; không lưu auth tokens.

Để kiểm tra source của một phụ thuộc đặc biệt, xem `dependency:tree`, effective POM và logs resolver ở mức phù hợp, tránh đăng debug logs có URLs/headers nhạy cảm.

## 18. Git commit và working tree: đầu vào có thực sự bất biến?

Trong một Git checkout:

~~~bash
git rev-parse --verify HEAD
git status --porcelain=v1 --untracked-files=all
git remote -v
~~~

- `git rev-parse HEAD` cho biết commit SHA mà HEAD trỏ tới.
- `git status --porcelain...` trả rỗng khi không có thay đổi tracked/untracked thông thường; **ignored files** vẫn có thể tồn tại.
- `git remote -v` giúp xem repository identity, nhưng URL có thể là mirror/fork nên cần so với repository đã được phê duyệt.

**Một JAR build từ dirty working tree không được mô tả trung thực chỉ bằng `git rev-parse HEAD`** vì có những thay đổi source chưa commit chưa phản ánh trong SHA. Khi CI release yêu cầu provenance chính xác, nên dùng checkout sạch từ immutable commit và xác minh dirty status trước build.

Trong một build có generated source, cần ghi rõ **generator version và input schema/files**. Nếu generated file không được commit, hãy xem nó là **derived input** của compiler và cần reproducibility của bước generate.

### Git tag

Tag `v1.0.0` là tên trỏ tới một Git object/revision. Cần kiểm tra tag trỏ đến SHA nào:

~~~bash
git rev-list -n 1 v1.0.0
~~~

Đừng suy source commit từ tag name, artifact file name hay changelog. Signed tag và protected tag policy giúp chống thay đổi không được phép; vẫn cần kiểm tra trust chain.

## 19. Gắn Git SHA vào JAR: lợi ích và rủi ro

Nhiều dự án muốn `java -jar app.jar --version` in commit SHA bên cạnh GAV. Điều này có ích cho vận hành **nếu Git SHA được cung cấp từ đúng source revision ổn định**.

Tuy nhiên:
- Nếu một plugin lấy `git describe --dirty` hoặc branch name, build từ dirty tree hoặc trên detached HEAD có thể nhúng giá trị khác.
- Nếu lấy CI run ID hoặc **wall-clock timestamp**, hai bản build từ cùng commit có thể ra **hash JAR khác**.
- Nếu plugin lấy short SHA, có rủi ro ambiguous khi repository phát triển lớn; bản ghi provenance ngoài nên dùng **full SHA**.
- Nếu embedded revision bị thay bằng một giá trị do build user nhập mà không đối chiếu Git HEAD, nó chỉ là một **tự khai báo có thể giả**.

**Thiết kế khuyến nghị cho ví dụ:** JAR chứa GAV/version tĩnh; build CI ghi Git SHA + digest ở **external manifest/attestation**. Nếu sản phẩm cần in SHA từ runtime, có thể thêm `git-commit-id` plugin hoặc resource filtering dựa trên một revision xác thực, nhưng phải có tests bảo đảm cùng commit cho cùng bytes và kiểm tra dirty build policy.

Không nên bỏ toàn bộ metadata version khỏi sản phẩm chỉ để hash trùng; hãy **đưa metadata cần thiết vào JAR theo cách ổn định** và đưa các dữ liệu động về build evidence bên ngoài.

## 20. Mẫu bảng truy vết từ source tới artifact

Một bản ghi release evidence có thể chứa:

| Trường | Ý nghĩa | Nguồn |
| --- | --- | --- |
| Repository | Định danh source Git được phép | VCS/CI config. |
| Source revision | Full Git commit SHA | Git checkout đã xác minh. |
| Working tree state | Clean hoặc exceptions đã duyệt | `git status` trên checkout. |
| Artifact GAV | Group, artifact, version | Effective Maven project model. |
| Main artifact path | JAR/WAR được build và test | Maven lifecycle output. |
| SHA-256 | Digest file artifact cuối | Hash tính sau `verify/package`. |
| Maven version | Version thực thi build | `mvn --version`. |
| JDK/toolchain | Vendor/version/compiler target | CI image, Java/Maven diagnostics. |
| Build invocation | Goals, profiles, approved flags | CI build record. |
| Dependency inputs | Resolved graph/SBOM/lock evidence | Maven Dependency Plugin/SBOM generator. |
| Plugin/parent/BOM inputs | Versions và active effective config | POM/effective POM. |
| Tests/quality gates | Tên suite, số tests, pass/fail, artifact checks | Surefire/Failsafe/CI. |
| Builder identity | Trusted CI workflow/runner | CI identity/attestation. |
| Distribution location | Repository URL/coordinate | Release manifest/repository audit. |

**Không phải trường nào cũng phải nhúng vào artifact.** Một file chứng cứ bên ngoài cho phép chứa nhiều thông tin biến động theo CI job (job ID, build time, reviewer) mà **không phá tính reproducible của JAR**.

Với thông tin nhạy cảm như private repository URL, access token, đường dẫn máy cá nhân, phải phân loại quyền xem; provenance public nên loại bỏ các secrets/đường dẫn không được phép công khai.

## 21. Artifact manifest ngoại vi và chữ ký

Một file release manifest **dạng tài liệu**, không phải POM/plugin config runnable, có thể theo schema:

~~~text
source.repository      = Git repository do tổ chức kiểm soát
source.revision        = SHA đầy đủ của commit đã duyệt
source.clean           = true
build.mavenVersion     = Version thực lấy từ Maven
build.javaVersion      = Version thực lấy từ JDK
build.profileSet       = Profile và flags của build
artifact.gav           = vn.example.trace:traceable-build-demo:1.0.0
artifact.filename      = traceable-build-demo-1.0.0.jar
artifact.sha256        = Digest SHA-256 được tính từ file thực
verification           = Kết quả test và rebuild so sánh đã thực hiện
~~~

Đây là **sơ đồ các trường cần thu thập**, không phải release manifest đã được ký. Khi xuất bản thật, công cụ CI sẽ ghi **giá trị có thực và kiểu dữ liệu/schema cố định**, rồi nếu cần tạo **attestation có chữ ký** theo hệ thống tin cậy của tổ chức.

### Checksum khác digital signature

- SHA-256 giúp kiểm tra bytes không đổi so với digest tham chiếu.
- **Chữ ký số** giúp xác nhận một chủ thể nắm private key/identity đã ký đúng đối tượng, nếu cơ chế xác minh và trust policy đúng.
- Một signed attestation có thể gắn subject digest với source revision, builder identity và build instructions.
- Signature không tự đảm bảo code không có lỗ hổng; người ký tin cậy không đồng nghĩa dependency graph an toàn.
- Nếu attacker đổi cả artifact và checksum trên cùng một host chưa được tin cậy, so checksum đơn thuần không chặn giả mạo.

Khi cần supply-chain provenance mạnh hơn, xem **SLSA/in-toto/Sigstore hoặc framework attestation phù hợp**, nhưng phải áp dụng workflow/certificate/identity policy đúng; Maven không tự sinh một chứng thực đáng tin chỉ nhờ đặt `project.build.outputTimestamp`.

## 22. Kiểm chứng sau khi upload: đừng chỉ tin BUILD SUCCESS

Một release có thể build, hash và upload thành công theo log nhưng vẫn ở **sai repository, sai GAV hoặc bị thay file**. Một bước xác minh cần:

1. Lấy GAV và file digest từ **evidence của artifact đã kiểm thử**.
2. Xác minh `<distributionManagement>` và repository ID/URL đã được phê duyệt.
3. Kiểm tra artifact chính, POM và các attached artifacts cần phát hành.
4. Download artifact lại bằng một consumer/test runner có quyền từ repository dự kiến.
5. Tính SHA-256 của **file tải lại**, so với digest ban đầu.
6. Kiểm tra embedded version, manifest hoặc smoke test artifact.
7. Đối chiếu source tag/SHA, CI run ID và, nếu dùng, chữ ký provenance.
8. Không publish lại cùng GAV immutable chỉ vì muốn sửa file bị lỗi; theo policy phát hành version mới hoặc quarantine.

**`mvn install` không chứng minh remote repository nhận artifact** vì chỉ ghi local `.m2`. Và khi thử remote download, đừng để local Maven cache cũ che giấu một artifact thực tế không tồn tại ở remote. Có thể dùng local repository test riêng nếu policy cho phép.

### Chụp hash trước hay sau ký?

Nếu ký được **gắn ngoài** dưới dạng file `.asc`/attestation, hash JAR đã build thường không đổi; file chữ ký có digest/định danh riêng. Nếu có plugin **sửa chính JAR sau khi ký/đóng gói** thì digest trước đó không còn là digest artifact cuối. Luôn tính checksum **sau plugin cuối cùng đã biến đổi bytes của file cần phát hành**.

## 23. Vì sao hai JAR khác SHA-256 dù source không đổi?

Một số nguyên nhân hay gặp:

| Dấu hiệu | Nguyên nhân | Cách chẩn đoán |
| --- | --- | --- |
| Chỉ timestamps trong ZIP entries khác | Jar/Assembly plugin không cố định outputTimestamp. | Dùng `project.build.outputTimestamp`, kiểm tra plugin version hỗ trợ. |
| `MANIFEST.MF` khác | Tool/JDK version, manifest entries động. | So manifests, bỏ build-clock fields không cần thiết. |
| `.class` khác | JDK/compiler flags, annotation processors, source paths. | Pin JDK/toolchain/compiler plugin, xem class diff. |
| `pom.properties` khác | Plugin behavior, encoding/newlines/version metadata. | So entry và plugin version; tránh sửa tay JAR. |
| Generated sources khác | Codegen plugin timestamp/random IDs. | Pin generator, nhập cùng source schemas và seed. |
| Service/resource order khác | Nondeterministic iteration hoặc merge order. | Xác định plugin tạo file, chuẩn hóa sort order. |
| Shaded JAR khác | Archive input order, dependency contents, relocation plugin. | So extracted entries; cố định dependency graph và shade plugin. |
| JavaDoc/sources JAR khác | Javadoc tool/version/time/footer. | Dùng plugin reproducible settings, kiểm tra đúng JDK. |
| Resources khác | `@buildTime@`, CI run number, hostname. | Đưa metadata động ra external manifest. |
| Thư mục path/username bị nhúng | Plugin log/metadata chứa absolute paths. | Khóa/chuẩn hóa path hoặc sửa plugin; build độc lập để phát hiện. |
| SNAPSHOT đổi bytes | Repository artifact mutable hoặc resolution policy. | Chuyển sang stable releases, đối chiếu hashes. |
| Zip bytes khác nhưng extracted files giống | Timestamps, entry order, permissions hoặc ZIP extra fields. | Dùng archive diff, `diffoscope`, plugin reproducibility support. |

**Không giải quyết bằng cách bỏ check hash.** Khi hash không khớp, trước hết tìm **thành phần nào khác nhau**. Mở hai JAR bằng công cụ so archive entries; khi cần dùng `diffoscope` để xác định chính xác biến thiên.

### Cẩn trọng với so file đã giải nén

Hai JAR có thể chứa những files cùng nội dung nhưng thứ tự entries/timestamps/ZIP metadata khác nhau, làm checksum toàn JAR khác. Nếu mục tiêu là **artifact bit-for-bit** tái lập, **hash toàn file phải khớp**; không được thay bằng “sau giải nén thì code trông giống”.

## 24. Maven Artifact Plugin và `diffoscope`: quy trình điều tra

Nếu chạy:

~~~bash
mvn -B -ntp clean install
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.6.1:compare
~~~

và plugin phát hiện khác biệt, hãy:

1. Xác định reference artifact có đúng version, classifier và repository không.
2. Xác nhận hai lần build dùng cùng source commit/working tree.
3. So `project.build.outputTimestamp` và active Maven profiles.
4. So Maven/JDK/toolchain/plugins và resolved dependencies.
5. Dùng output `.buildcompare` để biết file nào khác.
6. Với JAR/ZIP, so `MANIFEST.MF`, properties, class files, metadata.
7. Dùng `diffoscope` nếu có môi trường phù hợp để thấy chỗ bytes khác.
8. Sửa nguyên nhân trong plugin/input, **không chỉnh tay artifact đã build**.
9. Lặp kiểm chứng trên checkout sạch; sau đó chạy independent rebuild.

**Goal `artifact:compare` không phải bằng chứng release đã ký hoặc đã được phê duyệt**. Nó là một phép so sánh kỹ thuật.

## 25. Version, SNAPSHOT và tính bất biến của repository

Một artifact snapshot như:

~~~text
vn.example.trace:traceable-build-demo:1.1.0-SNAPSHOT
~~~

có thể được publish lại nhiều lần theo timestamp/build number của snapshot repository. Hai lần resolve cùng logical SNAPSHOT version có thể nhận **hai file bytes khác nhau**. Điều đó không mặc nhiên là lỗi; nó là một thuộc tính của workflow snapshot.

Với release:

~~~text
vn.example.trace:traceable-build-demo:1.0.0
~~~

tổ chức thường cần **immutable GAV**: một version gắn với tập bytes xác định. Nếu phát hiện lỗi, phát hành `1.0.1`/version mới thay vì ghi đè `1.0.0`.

### Reproducibility của release vs SNAPSHOT

- Release version/commit/tag nên bất biến.
- Plugin/dependency versions nên cố định và resolve từ repository đáng tin.
- Snapshot dependencies làm khó việc tái tạo build nhiều ngày sau nếu metadata/snapshot bytes đã đổi.
- Chỉ so SHA của JAR cuối không cho thấy một dependency snapshot đã bị thay nếu code không ảnh hưởng output trong lần đó.
- Nếu dùng snapshot nội bộ cho development, lưu build input digest và không quảng cáo nó như bằng chứng reproducibility release lâu dài.

**Maven Central hoặc private repository URLs là nơi lưu artifact, không phải thứ tự động xác nhận provenance.** Cần chính sách publish, checksum, metadata, signatures và independent verification theo mức bảo đảm mong muốn.

## 26. Multi-module: không gom mọi artifact thành một hash vô danh

Với Maven Reactor:

~~~text
parent/                    packaging pom
├── pom.xml                groupId=vn.example.trace
├── api/pom.xml            jar
├── service/pom.xml        jar, depends on api
└── cli/pom.xml            jar, depends on service
~~~

Một lần `mvn verify` có thể tạo:

~~~text
parent/pom.xml
parent/api/target/api-1.0.0.jar
parent/service/target/service-1.0.0.jar
parent/cli/target/cli-1.0.0.jar
~~~

Đây là **cây minh họa**, không phải file của demo runnable. Mỗi module cần ít nhất:

- GAV riêng.
- Artifact path/classifier/type.
- SHA-256 của từng file thực tế.
- Parent/BOM và selected dependency graph.
- Build/test status.
- Source commit chung hoặc riêng theo kiến trúc repository.
- Quan hệ actual dependencies để hiểu propagation.

`<modules>` chỉ xác định projects trong aggregator; nó **không tự khai báo dependency graph**. Một module chỉ có managed entry ở `dependencyManagement` chưa chắc cần dependency đó.

### Attached artifacts

Nếu Maven Source/Javadoc/Shade/Assembly Plugins tạo attached artifacts, checksum từng file **riêng biệt**. `service-1.0.0.jar`, `service-1.0.0-sources.jar`, `service-1.0.0-all.jar` và distribution ZIP là những bytes khác nhau, không thể dùng chung một checksum.

**Maven Deploy Plugin chỉ upload main/attached artifacts**, không tự đăng mọi file bất kỳ trong `target`. Bản release evidence phải khớp đúng tập file thật sự đã publish.

## 27. Provenance trong CI: hai lớp chứng minh

Một pipeline đáng tin nên tách **kiểm chứng kỹ thuật** và **chứng thực nguồn**:

~~~text
Checkout immutable Git SHA
          |
          +-- Verify repository origin, clean state
          |
          v
Pin Maven/JDK / resolve dependencies
          |
          v
Run mvn -B -ntp clean verify
          |
          +-- Surefire/Failsafe/security gates
          |
          v
Inspect JAR + embedded GAV
          |
          v
Compute SHA-256 of final artifact
          |
          +-- Compare with independent rebuild
          |
          v
Write build record: Git SHA + GAV + digest + toolchain
          |
          v
Sign/attest record using approved CI identity
          |
          v
Stage/promote or publish exact artifact bytes
          |
          v
Download and compare SHA-256
~~~

CI system cần bảo vệ **builder identity và secrets**. Không đưa credentials release vào untrusted pull request jobs, vì POM/plugin executions có thể thực thi code với quyền runner. Nên tách read-only build/test jobs khỏi publish/sign jobs và gắn approval với protected commit/tag.

### Gate nào nên làm fail pipeline?

- Git HEAD không khớp approved SHA hoặc workspace dirty ngoài policy.
- Maven/JDK/required profiles không đúng release policy.
- Dependency/plugin source không được duyệt hoặc SNAPSHOT trái policy.
- Unit/integration tests, static/security/license gates fail.
- Artifact thiếu manifest/metadata hoặc embedded version khác GAV.
- So checksum với reference đã duyệt không khớp mà không có giải thích.
- Independent rebuild không tái tạo được artifact **khi tổ chức yêu cầu** bit-for-bit reproducibility.
- Artifact tải về sau publish không trùng digest đã ký.
- Không tạo/verify được attestation hoặc chữ ký theo release policy.

**Không đánh dấu thành công chỉ vì build job có exit code 0** nếu nó bỏ qua tests, sai artifact path hoặc không được cấp quyền publish.

## 28. Anti-pattern truy vết đầu vào

**1. “JAR có tên đúng là artifact đúng.”** Filename/GAV không bảo đảm bytes; cần checksum.

**2. “SHA-256 tự chứng minh Git commit.”** Hash không thể tự nói source revision nào tạo ra file; cần provenance liên kết.

**3. “Đưa timestamp build vào JAR để audit.”** Đưa wall-clock vào JAR làm hash thay đổi theo lần build. Nên lưu timestamp job trong evidence ngoài JAR, hoặc dùng giá trị ổn định được kiểm soát.

**4. “Build lại trên cùng laptop trùng hash nên chắc chắn reproducible.”** Chỉ là local repeatability; phải thử môi trường độc lập để chứng minh mạnh hơn.

**5. “Chỉ cần `project.build.outputTimestamp`.”** Plugins/generators/resources khác vẫn có thể nondeterministic.

**6. “Cùng Git SHA là đủ.”** Dirty working tree, generated files, mutable dependencies và khác JDK có thể làm bytes khác.

**7. “Ghi một hash cho cả release.”** Mỗi main/attached artifact có checksum riêng.

**8. “So file tải bằng checksum tải từ cùng trang không tin cậy là an toàn tuyệt đối.”** Attacker có thể sửa cả hai; cần nguồn digest tin cậy/chữ ký.

**9. “Hash được tính trước Shade/Assembly/plugin cuối.”** Nếu bytes biến đổi sau đó thì hash cũ không còn đúng cho artifact cuối.

**10. “`mvn install` đã xác minh remote.”** Install chỉ ghi local repo; cần download/so digest ở remote được duyệt.

**11. “Để `.m2`/target cache cũ là vô hại.”** Cache có thể che missing dependencies và artifact bytes đã đổi; độc lập build nên có cơ chế kiểm soát cache.

**12. “Thêm Git SHA short bằng CLI tùy ý vào JAR.”** Nếu không đối chiếu actual HEAD, metadata có thể sai và làm mất reproducibility.

## 29. Câu hỏi tự kiểm tra và bài thực hành

**Bài 1 — phân biệt định danh.** Nêu khác nhau giữa GAV, Git SHA và checksum. Nếu JAR giữ GAV nhưng bytes thay đổi, thứ gì sẽ phát hiện thay đổi?

**Bài 2 — tạo demo.** Tạo `pom.xml`, `build-info.properties`, `TraceApp.java`, `TraceAppTest.java`. Chạy `mvn -B -ntp clean verify`; xác nhận unit test pass và JAR có Main-Class.

**Bài 3 — phiên bản runtime.** Chạy `java -jar target/traceable-build-demo-1.0.0.jar`. Stdout cần là **ARTIFACT: vn.example.trace:traceable-build-demo:1.0.0**. Chứng minh dòng này lấy từ resource trong JAR, không từ Git directory.

**Bài 4 — so checksum.** Hai lần `clean verify` trong sandbox, giữ reference ngoài `target`. So SHA-256; giải thích vì sao không được copy reference sau lần build cuối.

**Bài 5 — tác động của timestamp.** Trong một bản sao bài tập, bỏ `project.build.outputTimestamp` rồi build hai lần. **Quan sát kết quả thực**; không khẳng định luôn khác vì Maven/plugin versions có thể có behavior reproducible mặc định.

**Bài 6 — metadata động.** Thêm một resource chứa current wall-clock time, build hai lần và so SHA. Phân tích vì sao thay đổi không thuộc source commit vẫn đổi bytes.

**Bài 7 — artifact:compare.** Dùng `mvn clean install`, sau đó `mvn clean verify ...:compare`. Xác định reference được chọn và xem `.buildcompare` nếu có khác biệt.

**Bài 8 — độc lập môi trường.** Dùng hai checkout sạch ở cùng Git SHA nhưng build directory khác; chạy cùng Maven/JDK/profiles và so digest. Ghi các môi trường chưa được kiểm soát.

**Bài 9 — input inventory.** Dùng `help:effective-pom`, dependency tree, `mvn --version` và Git SHA để viết một build record. Phân biệt “input được khai báo” với “artifact bytes đã xác nhận”.

**Bài 10 — release verification.** Thiết kế CI lưu GAV/SHA256, ký attestation, upload artifact và download kiểm tra lại. Nếu hash không khớp, pipeline cần dừng ở gate nào?

## 30. Checklist truy vết một bản Maven artifact

1. Source repository và full Git commit SHA đã được duyệt.
2. Working tree sạch hoặc những sai khác được giải thích và ghi lại.
3. POM root/parent/module versions khớp release plan.
4. GAV/version metadata trong JAR khớp effective POM.
5. Plugins, parent/BOM và resolved dependencies được ghi nhận.
6. Maven/JDK/toolchain versions có thể tái tạo.
7. Profiles/flags và generated source inputs được kiểm soát.
8. Runtime dependencies và licenses/security risks được đánh giá.
9. `project.build.outputTimestamp`/archive plugin behavior được kiểm chứng.
10. Không nhúng wall-clock hoặc CI runtime secrets vào JAR.
11. `mvn clean verify` từ checkout sạch thành công.
12. Tests thực sự được khám phá/chạy, không có skip ngoài policy.
13. JAR/WAR chính và attached artifacts đúng type/classifier.
14. Manifest/resources/metadata hợp lệ và runtime smoke test pass.
15. SHA-256 tính trên từng file sau bước cuối làm đổi bytes.
16. Digest được lưu **bên ngoài** artifact và gắn với commit/build record.
17. So rebuild trong cùng môi trường được thực hiện nếu cần.
18. Independent rebuild được thực hiện khi release policy yêu cầu.
19. Build evidence/provenance có access control và chữ ký theo trust model.
20. File tải về từ repository trùng digest reference đã được duyệt.
21. Không dùng một immutable GAV để publish bytes khác.
22. Có audit trail để từ artifact digest tìm ngược commit, dependencies, toolchain và CI run.

### Tổng kết

**Truy vết một Maven artifact cần kết hợp định danh, tính toàn vẹn và nguồn gốc.** GAV/metadata cho biết artifact tự nhận là phiên bản nào; Git SHA nhận diện source revision; SHA-256 nhận diện **bytes của artifact cuối**; effective POM, resolved dependencies, Maven/JDK và flags mô tả môi trường tạo ra; build record/attestation đáng tin gắn các thông tin này với nhau.

**Build tái lập** đòi cùng inputs được xác định có thể tạo **output bit-for-bit giống nhau**. `project.build.outputTimestamp` giúp kiểm soát archive timestamps, còn `artifact:check-buildplan`, `artifact:compare` và công cụ so khác biệt giúp phát hiện nondeterminism. So hash trong một workspace chỉ là bước đầu; independent rebuild và so download từ repository đáng tin mới cho bằng chứng mạnh hơn. **Checksum không phải chữ ký và không tự xác thực source** — bảo vệ supply chain cần provenance, signer identity và chính sách phát hành.

### Tài liệu chính thức và định nghĩa

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven Artifact Plugin — Plugin Goals](https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html)
- [Apache Maven Artifact Plugin — artifact:compare](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html)
- [Apache Maven Artifact Plugin — Reproducibility Diagnosis](https://maven.apache.org/plugins/maven-artifact-plugin/reproducible.html)
- [Apache Maven JAR Plugin — jar:jar outputTimestamp](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Reproducible Builds — Definition](https://reproducible-builds.org/docs/definition/)
- [SLSA — Supply-chain Levels for Software Artifacts](https://slsa.dev/spec/)
- [in-toto — Supply Chain Attestations](https://in-toto.io/)
