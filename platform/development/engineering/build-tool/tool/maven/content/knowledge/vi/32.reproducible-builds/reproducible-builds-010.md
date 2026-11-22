# Giới hạn của việc chỉ so sánh hai lần build trên cùng một máy

## 1. Một kết quả SHA-256 trùng nhau chứng minh được điều gì?

Giả sử bạn chạy hai lần `mvn clean package` trong cùng directory trên laptop, copy mỗi JAR sang tên khác, rồi so SHA-256 và nhận cùng digest. Điều đó là một tín hiệu **tốt**: hai lần build cụ thể tạo ra bytes trùng nhau. Nhưng kết luận đúng chỉ là **local repeatability PASS** (có khả năng lặp lại trong điều kiện hiện tại), **không phải** một tuyên bố rằng người khác có thể tái lập artifact độc lập từ source.

Theo hướng dẫn chính thức của Apache Maven, reproducible build nghĩa là với **cùng source, build environment và build instructions**, một bên độc lập có thể dựng được **bit-for-bit identical** binary. Tài liệu Maven cảnh báo rằng bài thử `mvn clean install` rồi `mvn clean verify artifact:compare` trên cùng máy **không chứng minh** third-party reproducibility: username, working directory và các environment leaks vẫn có thể được nhúng vào binary mà hai phép build không phát hiện.

### Điều cần phân biệt

~~~text
Chạy 1: /home/dev/project, user dev, Maven cache A -> app.jar A
Chạy 2: /home/dev/project, user dev, Maven cache A -> app.jar B
SHA256(A) == SHA256(B)
              |
              v
LOCAL REPEATABILITY: PASS
INDEPENDENT REPRODUCIBILITY: CHƯA KIỂM

Chạy 3: /work/clean/project, user ci, Maven cache B -> app.jar C
SHA256(C) ? SHA256(artifact đã publish)
              |
              v
Evidence mạnh hơn về khả năng tái lập độc lập
~~~

Hai lần build local có thể phát hiện timestamps thay đổi giữa lần này/lần sau, random identifiers hoặc thứ tự output biến động. Chúng **không** có khả năng phát hiện thứ được giữ cố định qua cả hai lần: absolute checkout path, home directory, user, Maven settings, local cache, compiler version, installed fonts, OS locale hoặc một toolchain bị can thiệp.

### Mục tiêu sau bài

1. Phân biệt repeatable, deterministic, reproducible, hermetic, verifiable và secure build.
2. Biết kết quả nào là bằng chứng thực sự và kết quả nào chỉ là local smoke test.
3. Hiểu môi trường build, đường dẫn, username, timezone, locale, cache, JDK, Maven plugins và metadata có thể tác động đến JAR.
4. Dùng `project.build.outputTimestamp` đúng phạm vi nhưng không coi đó là toàn bộ giải pháp.
5. Chạy project Java 17 + Maven hoàn chỉnh cố tình nhúng `project.basedir` vào resource.
6. Quan sát same-directory PASS, different-directory FAIL rồi sửa nguyên nhân.
7. Dùng Java 17 SHA-256 comparator có exit code rõ ràng.
8. Áp dụng `artifact:check-buildplan`, `artifact:compare`, `jar tf`, diffoscope và independent build.
9. Thiết kế CI matrix, cache isolation, artifact-reference comparison và release evidence.
10. Không nhầm tính tái lập của artifact với nguồn gốc/độ an toàn của phần mềm.

## 2. Thuật ngữ: vì sao “giống nhau” có nhiều mức

### 2.1. Repeatability (lặp lại)

Cùng operator thực thi cùng recipe trong môi trường gần như không đổi, kết quả có thể byte-identical. Hai lần chạy local trong cùng directory thường kiểm mức này. Mức này hữu ích, dễ thực hiện và nên là bước đầu.

### 2.2. Determinism (tính xác định)

Nếu toàn bộ input có ý nghĩa được giữ nguyên, thuật toán/build steps tạo cùng output. Một build có thể deterministic **trên một máy** nhưng vẫn nhúng absolute path; vì path là một input ẩn, build từ một directory khác có output khác. Đừng đánh đồng deterministic dưới một bộ input hẹp với khả năng người ngoài xây lại artifact.

### 2.3. Reproducibility (tái lập)

Bên độc lập có thể sử dụng source, build instructions và môi trường **đã được định nghĩa** để dựng lại cùng artifact bytes. Mức độ độc lập quan trọng: khác checkout, khác user, local Maven cache riêng, runner/host độc lập, có thể khác tổ chức kiểm chứng.

Không bắt buộc mọi JDK/OS bất kỳ đều tạo cùng bytes. Nếu contract yêu cầu JDK 17 trên Linux và native classifier riêng cho Windows, phép so phải theo đúng output target. Tuy nhiên các yếu tố môi trường **không được quy định là input cần thiết** — ví dụ username/checkout directory — nên được cố gắng loại ra hoặc ít nhất được document minh bạch.

### 2.4. Hermeticity (cô lập đầu vào)

Build hạn chế truy cập vào các input ngoài khai báo: không đọc bí mật từ `user.home`, không tải dependencies mutable tùy ý hoặc dùng môi trường bất định. Hermetic build giúp reproducibility nhưng không tự đảm bảo timestamp/race/order được ổn định.

### 2.5. Verifiable release

Một bên khác lấy **binary đã công bố thực tế** cùng source và build recipe rồi rebuild, so được đúng files. Đây là mục tiêu mạnh hơn hai lần build trước khi upload. Nếu staging JAR được QA nhưng release repository chứa JAR khác, bài so local/local không phát hiện.

### 2.6. Secure/authentic release

SHA-256 giống nhau không chứng minh người ký là chủ sở hữu, toolchain không bị can thiệp, code không có lỗ hổng hoặc dependency không chứa malware. Một compiler bị tấn công có thể tạo cùng output xấu trong cả hai run trên một host. Reproducibility chỉ là **một phần** của supply-chain assurance, không thay signatures, SBOM, trusted provenance và security review.

## 3. Vì sao hai lần cùng máy có thể tạo false confidence?

| Input hoặc điều kiện | Đường đi vào artifact | Cùng máy, cùng directory | Thử mạnh hơn |
| --- | --- | --- | --- |
| `project.basedir` | Filtered resource, manifest, source generator | Path giữ nguyên, hash có thể trùng | Checkout ở directory B |
| `user.name`, `user.home` | Generated metadata/config, debug symbols | User/home không đổi | Build bằng OS user khác |
| Maven local repo `~/.m2` | Cached dependencies, plugins, metadata | Cùng file binaries | Cache mới, verified downloads |
| JDK vendor/build | `javac` bytecode/Javadoc/tooling | Cùng compiler | Cố định recipe rồi thử vendor/patch theo contract |
| Maven version | Plugin resolution/defaults, lifecycle | Cùng distribution | Pin Wrapper và xác nhận version |
| Timezone | Generated time strings, formatted dates | Cùng `TZ` | So UTC và non-UTC có kiểm soát |
| Locale / encoding | Sorting, character bytes, generated docs | Cùng settings | Thay locale; pin UTF-8 |
| OS/filesystem | CRLF vs LF, path separators, permissions | Cùng host | Clean clone Windows/Linux nếu support |
| File iteration order | ZIP order, generated indices | Thứ tự có thể ổn định | Clean checkout và filesystem khác |
| Current clock | ZIP entries, build timestamps | Có thể được cố định bởi plugin | Kiểm timestamp/resolution |
| Environment variables | `BUILD_NUMBER`, branch, hostname | Giữ nguyên giữa runs | Inject values khác có chủ đích |
| SNAPSHOT/version range | Dynamic artifacts | Cache che sự thay đổi | Repository sạch, pin versions |
| Dirty workspace | `target` files, untracked generated content | Cả hai dùng state tương tự | Fresh Git clone, `git status` |
| Parallelism/races | Nondeterministic file order | Có thể không thay trong hai runs | Nhiều clean runners |
| Compromised toolchain | Compiler/plugin bị sửa | Cả hai dùng tool xấu | Trusted independent builder |

Đây là **nguồn rủi ro có điều kiện**, không có nghĩa mọi Java project tự động bị tất cả lỗi. Ví dụ Java class thường không lưu absolute path chỉ vì chạy `javac`, nhưng một custom annotation processor, JAR manifest generator hoặc Maven resource filtering có thể chèn đường dẫn vào byte output.

### 3.1. Hai lần cùng máy không thay đổi hidden inputs

Nếu generator nhúng đường dẫn `C:\Users\dev\repo` vào resource, hai lần build trong directory ấy sinh cùng chuỗi. Nếu repository được clone vào `D:\agents\run42\repo`, chuỗi đổi. Hai hashes local bằng nhau là kết quả hoàn toàn nhất quán với **một build chưa portable/reproducible**.

### 3.2. `mvn clean` không reset môi trường

`clean` thường xóa `target` và files được Maven Clean Plugin cấu hình, **không** xóa local Maven repo, user settings, env vars, system clock, compiler installation, caches của tool ngoài `target` hoặc files custom plugin ghi ngoài build directory. Hai `clean package` không phải hai máy độc lập.

### 3.3. Same output không đồng nghĩa same source provenance

Nếu cả hai run dựa vào cùng local checkout đã bị sửa hoặc cùng plugin bị cài đè, chúng vẫn có thể khớp. Release verification cần source commit/tag cụ thể, dependency/plugin binary integrity, trusted repository và đối chiếu bytes của **published artifact**.

## 4. Hash toàn JAR và cách đọc kết quả

JAR là ZIP-based archive. SHA-256 là checksum của **toàn byte stream**, bao gồm entries, entry timestamps, headers, central directory, manifest, resources, compiled classes và metadata.

Có thể tính trên Linux:

~~~bash
sha256sum target/my-lib-1.0.0.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 target/my-lib-1.0.0.jar
~~~

Nếu SHA-256 bằng nhau, với giả thiết thuật toán an toàn, hai files có xác suất rất cao byte-identical. Điều này **không** đảm bảo:

- Published POM cũng giống.
- Main JAR bạn vừa so là file publisher đã upload.
- Source/Javadoc/classifier artifacts giống.
- Chữ ký GPG/PGP và trust chain hợp lệ.
- Source/inputs đúng như công bố.
- Một codebase không có bug/vulnerability.
- Có người độc lập tái tạo được file.

Ngược lại, SHA-256 khác có thể do **chỉ timestamp của ZIP entry**, nhưng điều đó vẫn là **bit-for-bit mismatch**. Bạn có thể kiểm semantic equivalence riêng, song không được đổi một tiêu chuẩn reproducible bytes thành “vẫn chạy được” mà gọi PASS.

### 4.1. Những nơi trong JAR dễ phát sinh khác biệt

- `META-INF/MANIFEST.MF` với Build-Jdk, custom build time hoặc implementation version.
- `META-INF/maven/.../pom.properties` và `pom.xml`.
- `git.properties`, `build-info.properties` hoặc filtered templates.
- Java classes được sinh bởi annotation processor.
- Resources từ `src/main/resources` / source generators.
- ZIP entry timestamps, order, permissions, compression settings.
- Shaded/uber JAR hoặc Spring Boot repackaged archive.

`jar tf file.jar` chỉ liệt kê paths; khi mismatch, cần trích xuất/so bytes nội dung và archive metadata để tìm nguyên nhân thực.

## 5. Maven hỗ trợ reproducible builds như thế nào?

### 5.1. `project.build.outputTimestamp`

Trong POM:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Các Maven archiving plugins hiện đại như Maven JAR Plugin sử dụng property này để cố định timestamps trên ZIP entries. Property có thể nhận ISO 8601 timestamp hoặc epoch-seconds theo goal/plugin. Đây là bước quan trọng để một JAR không khác nhau chỉ vì chạy vào phút khác.

Tài liệu Maven hiện hành cho biết với Maven 3.10+ và Maven 4, reproducible mode được hỗ trợ/mặc định theo những thay đổi mới; **dù dùng version nào, vẫn phải xét plugin thực tế và output**, không giả định Maven tự sửa mọi generator.

Cố định ZIP timestamps **không** tự:
- xóa `project.basedir` trong filtered resource;
- thay `System.currentTimeMillis()` hoặc `Instant.now()` trong code generator;
- pin SNAPSHOT dependencies/version ranges;
- kiểm soát random UUIDs;
- ổn định file order từ custom plugins;
- bảo đảm Java 17 và Java 21 compiler cho bytecode giống;
- kiểm tra published artifact có khớp local không.

### 5.2. `SOURCE_DATE_EPOCH` có ích nhưng không phải phép màu

`SOURCE_DATE_EPOCH` là quy ước hệ sinh thái reproducible builds để xác định timestamp từ source/release thay vì wall clock. Trong Maven, cần đọc tài liệu **plugin đang dùng** xem nó nhận qua `project.build.outputTimestamp` hay một property khác. Đừng tự giả định core Maven hoặc mọi Maven plugin đều tự đọc và chuẩn hóa toàn bộ timestamps/resource content từ env var.

### 5.3. Maven Artifact Plugin: kiểm build plan

Lệnh được tài liệu Maven đề xuất:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
~~~

Goal `artifact:check-buildplan` kiểm tra plugins trong execution plan có **known reproducibility issues** dựa trên cơ sở dữ liệu/plugin rules. Nó có thể cảnh báo một plugin version không phù hợp. Nhưng nó **không biết** business logic của resource template có cố tình chứa absolute path hay không. Không báo reproducibility PASS chỉ vì check-buildplan PASS.

### 5.4. Maven Artifact Plugin: compare

Workflow local từ tài liệu Maven:

~~~bash
mvn -B -ntp clean install
mvn -B -ntp clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
~~~

`artifact:compare` so current build output với reference đã `install` hoặc remote repository, báo diff và tạo `.buildcompare`. Đây là local baseline test tốt, nhưng Apache Maven cảnh báo rõ: cùng username/current directory vẫn có thể che giấu environment leaks.

Tùy use case, goal có `-Dreference.repo=...` với repo ID/URL/`id::url` để tham chiếu repository staging/remote. Khi kiểm remote, phải chắc file tham chiếu đúng **release candidate/published artifact** chứ không phải một bản local đã bị cài đè.

### 5.5. buildinfo, describe-build-output và diffoscope

`maven-artifact-plugin` cung cấp `artifact:describe-build-output` và `artifact:buildinfo`; trang plugin hiện hành đánh dấu `buildinfo` deprecated/internal format, ưu tiên `describe-build-output` hoặc `compare` theo nhu cầu. Nếu có mismatch, dùng `diffoscope` (công cụ riêng, không đi kèm JDK/Maven) để phân tích ZIP, manifests, class bytes và resource differences.

~~~bash
diffoscope --html difference-report.html jar-a.jar jar-b.jar
~~~

Công cụ không thay thế bước hiểu **input nào** dẫn tới khác biệt và sửa ngay tại plugin/source sinh output.

## 6. Lab runnable Java 17: same path PASS, different path FAIL

Thí nghiệm này **cố ý** chèn absolute checkout path vào một text resource bằng Maven Resources Plugin `filtering=true`. Hai lần cùng path sẽ có thể tạo JAR giống nhau; clone project tới path khác sẽ chèn một chuỗi khác, dù code Java và `outputTimestamp` không đổi.

### 6.1. Cấu trúc

~~~text
repro-local/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/dev/repro/ReproApp.java
│   │   └── resources-filtered/build-origin.txt
│   └── test/
│       └── java/dev/repro/ReproAppTest.java
└── tools/
    └── CompareArchives.java
~~~

Cần JDK 17+, Maven 3.9.x, Maven Central hoặc mirror có thể tải plugins và JUnit. Không cần repository manager, database, Docker hoặc tài khoản phát hành. Các output ghi là **kỳ vọng khi chạy đúng lab**, không phải kết quả đã thực thi trên máy người đọc.

### 6.2. POM đầy đủ

Tạo `repro-local/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>repro-local</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
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
        <resources>
            <resource>
                <directory>src/main/resources-filtered</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build-origin.txt</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các versions pin để giảm biến động toolchain. `project.build.outputTimestamp` được cố định. `resources` chỉ filter một **text file**; không filter binary/JAR/PNG vì filtering có thể làm hỏng bytes. **Điểm gây non-reproducibility được cố tình đặt ở file `build-origin.txt`**, không phải trong Java code.

### 6.3. Java application

Tạo `src/main/java/dev/repro/ReproApp.java`:

~~~java
package dev.repro;

public final class ReproApp {
    private ReproApp() {
    }

    public static String message() {
        return "REPRO LAB OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

### 6.4. JUnit 5 tests

Tạo `src/test/java/dev/repro/ReproAppTest.java`:

~~~java
package dev.repro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class ReproAppTest {

    @Test
    void messageIsStable() {
        assertEquals("REPRO LAB OK", ReproApp.message());
    }

    @Test
    void resourceIsPackaged() throws IOException {
        try (InputStream in = ReproApp.class
                .getResourceAsStream("/build-origin.txt")) {
            assertNotNull(in);
            String content = new String(in.readAllBytes(),
                    StandardCharsets.UTF_8);
            assertTrue(content.startsWith("checkout="));
        }
    }
}
~~~

Tests chỉ chứng minh code và resource tồn tại. Chúng không so **nội dung bytes của hai JAR khác checkout**. Vì vậy JUnit có thể PASS cả khi build chưa reproducible.

### 6.5. Resource có input ẩn

Tạo `src/main/resources-filtered/build-origin.txt`:

~~~properties
checkout=${project.basedir}
~~~

Maven Resources Plugin thay placeholder `${project.basedir}` thành absolute basedir khi filtering. Ví dụ nếu source ở `/home/alice/projects/repro-local`, bên trong JAR có:

~~~text
checkout=/home/alice/projects/repro-local
~~~

Nếu copy sang `/workspace/ci/repro-local-alt`:

~~~text
checkout=/workspace/ci/repro-local-alt
~~~

**Đây là đường dẫn minh họa**; output thật dùng path môi trường của người chạy. Trên Windows có thể là đường kiểu `C:\Users\alice\project`. Hai JAR khác vì text resource, **dù classes, POM và ZIP timestamps đã cố định**.

### 6.6. Build ứng dụng và kiểm tra JAR

Từ `repro-local`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean package
java -cp target/classes dev.repro.ReproApp
jar tf target/repro-local-1.0.0.jar
~~~

Maven test log dự kiến:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Stdout riêng của `ReproApp`:

~~~text
REPRO LAB OK
~~~

Các entries cần tìm trong JAR:

~~~text
dev/repro/ReproApp.class
build-origin.txt
META-INF/MANIFEST.MF
META-INF/maven/dev.example/repro-local/pom.xml
~~~

Danh sách trên không nhất thiết là toàn bộ archive; plugin có thể thêm directory entries và Maven metadata.

## 7. Tool Java 17: SHA-256 toàn file, báo chính xác kết quả

Tạo `tools/CompareArchives.java`:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

public final class CompareArchives {
    private CompareArchives() {
    }

    private static byte[] hash(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(path)) {
            byte[] buf = new byte[8192];
            int read;
            while ((read = in.read(buf)) != -1) {
                md.update(buf, 0, read);
            }
        }
        return md.digest();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: CompareArchives <jar-a> <jar-b>");
            System.exit(2);
        }

        byte[] a = hash(Path.of(args[0]));
        byte[] b = hash(Path.of(args[1]));
        boolean same = Arrays.equals(a, b);

        System.out.println("A_SHA256="
                + HexFormat.of().formatHex(a));
        System.out.println("B_SHA256="
                + HexFormat.of().formatHex(b));
        System.out.println("IDENTICAL=" + same);

        if (!same) {
            System.exit(3);
        }
    }
}
~~~

Tool chỉ dùng JDK 17. Dùng streaming hash, không nạp toàn JAR vào RAM. Hai dòng SHA-256 có 64 hex chars thay đổi theo **bytes thực tế**; không được bịa literal digest. Kết luận cuối luôn là `IDENTICAL=true` hoặc `IDENTICAL=false`; exit code `3` khi mismatch để CI nhận biết failure có chủ đích.

### 7.1. Thử cùng directory hai lần

Trong `repro-local` trên Linux/macOS:

~~~bash
mvn -B -ntp clean package
cp target/repro-local-1.0.0.jar ../run-a.jar

mvn -B -ntp clean package
cp target/repro-local-1.0.0.jar ../run-b.jar

javac -d tools/classes tools/CompareArchives.java
java -cp tools/classes CompareArchives ../run-a.jar ../run-b.jar
~~~

Khi toolchain/plugins tạo output ổn định, dòng cuối **dự kiến**:

~~~text
IDENTICAL=true
~~~

Giá trị `checkout=...` trong JAR A và B **giống nhau** vì bạn chưa đổi directory. Đây là **false confidence nếu kết luận third-party reproducibility**; thực tế vẫn tồn tại absolute path leak.

Windows PowerShell có thể dùng `Copy-Item` thay `cp`; so tool với `java -cp "tools\classes" CompareArchives "..\run-a.jar" "..\run-b.jar"`. Không để hai snapshots trong `target` vì lần `mvn clean` tiếp theo có thể xóa chúng.

### 7.2. Thử directory khác nhưng source giống

Từ **thư mục cha** chứa `repro-local`, tạo directory `repro-local-alt`:

~~~bash
cp -R repro-local repro-local-alt
(cd repro-local-alt && mvn -B -ntp clean package)

java -cp repro-local/tools/classes CompareArchives \
  repro-local/target/repro-local-1.0.0.jar \
  repro-local-alt/target/repro-local-1.0.0.jar
~~~

Lưu ý `repro-local-alt` phải là directory **chưa tồn tại** để không copy lồng hay overwrite project có sẵn. `clean` trong bản copy loại build outputs cũ. Nếu project nằm trong Git, phương án tốt hơn là dùng **hai clean clones cùng commit** tại hai paths.

Dòng cuối **dự kiến**:

~~~text
IDENTICAL=false
~~~

Java comparator sẽ exit `3`. Đây là failure theo thiết kế: Maven resource filtering nhúng hai absolute paths khác nhau.

Windows PowerShell, từ thư mục cha:

~~~powershell
Copy-Item -LiteralPath repro-local -Destination repro-local-alt -Recurse
Push-Location repro-local-alt
mvn -B -ntp clean package
Pop-Location
java -cp "repro-local\tools\classes" CompareArchives "repro-local\target\repro-local-1.0.0.jar" "repro-local-alt\target\repro-local-1.0.0.jar"
~~~

Không xóa dữ liệu đang làm việc chỉ để làm thí nghiệm; dùng project copy/clean checkout chuyên dụng.

### 7.3. Kiểm tra root cause chứ không đoán

Trên POSIX, từ directory cha:

~~~bash
mkdir -p inspect-a inspect-b
(cd inspect-a && jar xf ../repro-local/target/repro-local-1.0.0.jar build-origin.txt)
(cd inspect-b && jar xf ../repro-local-alt/target/repro-local-1.0.0.jar build-origin.txt)
diff -u inspect-a/build-origin.txt inspect-b/build-origin.txt
~~~

Bạn sẽ thấy `checkout=/.../repro-local` khác `checkout=/.../repro-local-alt`. Còn `ReproApp.class` thường giống. Không cần sửa Java logic; phải xử lý resource filtering.

### 7.4. Sửa để không nhúng absolute path

Trong **cả hai** checkout, thay nội dung `build-origin.txt` bằng **cùng** một text ổn định:

~~~properties
checkout=normalized
~~~

Sau đó chạy `mvn -B -ntp clean package` ở cả hai directories và dùng comparator. Khi các inputs khác giữ nguyên (cùng JDK/Maven/plugins/OS và source), dòng cuối **dự kiến**:

~~~text
IDENTICAL=true
~~~

Điều này cho thấy bạn đã loại một input ẩn và thử được **path independence**. Tuy nhiên đừng nâng kết luận thành “reproducible everywhere”: vẫn cần thử user, cache, host và published binary.

### 7.5. Khi application cần đường dẫn thực

Thay vì nhúng absolute build path vào release JAR, thường nên:
- Đọc runtime path từ environment/config ở lúc chạy.
- Dùng relative path hoặc logical resource name.
- Nếu debug symbol/code generator bắt buộc path, dùng option **của chính tool đó** để chuẩn hóa hoặc document path canonical trong build contract.
- Ghi build provenance vào attestation riêng thay vì binary runtime.
- Cẩn thận: cờ compiler C/C++ như `-fdebug-prefix-map` không phải cờ tự động hợp lệ cho `javac`.

## 8. Tại sao cần cache độc lập và môi trường được định nghĩa?

### 8.1. Maven local repository có thể che dữ liệu mutable

Cùng `~/.m2/repository` có thể giữ một version SNAPSHOT hoặc artifact được tải trong quá khứ. Hai runs dùng cùng cached bytes nên khớp. Runner khác có thể resolve một snapshot mới, dependency range mới hoặc metadata repository khác.

Thử clean cache tại một checkout độc lập:

~~~bash
mvn -B -ntp -Dmaven.repo.local=./.m2-isolated clean verify
~~~

Maven repo này nằm trong workspace và ban đầu cần có quyền tải dependencies/plugins. Nhưng một lần clean repo **không giải quyết** dependency version drift nếu POM dùng SNAPSHOT/version ranges. Cần quản lý artifact versions và hashes, parent/BOM, `settings.xml`/mirrors và plugin resolution.

### 8.2. Những inputs cần cố định hoặc ghi nhận

Một release rebuild recipe tốt nêu:

| Thông tin | Cần ghi nhận |
| --- | --- |
| Source | Commit SHA/tag và dirty/clean state |
| Maven | Maven Wrapper/distribution version |
| Java | JDK distribution, version, `java -version` |
| Plugins | Effective plugin versions, lifecycle goals |
| Dependencies | Resolved coordinates, repositories, integrity |
| Build command | Profiles, properties, flags, test configuration |
| Platform | OS, architecture nếu artifact phụ thuộc |
| Locale/TZ | `LANG`, timezone hoặc giá trị được định nghĩa |
| Workspace | Checkout path variation test và path sanitization |
| Maven cache | Reuse/isolated cache, downloaded artifacts |
| Artifact | GAV, JAR/POM/source/Javadoc hashes |
| Provenance | Build job, builder identity, environment document |

**Không ghi password/token/private key** vào tài liệu công khai. Nếu metadata có username/checkout path, redact khi gửi issue công khai nhưng vẫn giữ bằng chứng nội bộ theo access policy.

### 8.3. Docker image cùng digest có đủ chưa?

Container có ích vì định nghĩa base image, JDK, Maven và packages. Nhưng hai runs dùng **cùng image và shared cache/volume mount/checkout path** vẫn có thể bỏ sót input ẩn. Image pinned by digest tốt hơn tag `latest`, nhưng vẫn cần kiểm registry integrity, dependency sources và independent runner. Nếu cùng một image bị compromise, cả hai kết quả có thể cùng bị compromise.

### 8.4. OS/JDK differences: kỳ vọng phải phù hợp contract

Maven docs lưu ý Windows và Unix có thể sinh newline khác, major JDK version có thể ảnh hưởng bytecode. Một Java-only library có thể đặt mục tiêu cross-OS byte equality; một artifact có native files cần separate classifiers. Hãy nói rõ chính xác điều gì phải giống (main JAR, POM, ZIP metadata, native classifier) và môi trường nào thuộc phạm vi.

Đừng coi một mismatch có chủ đích giữa native Linux và Windows classifiers là failure không giải thích được; cũng đừng loại toàn bộ cross-OS tests khi bạn quảng cáo portability.

## 9. Ma trận kiểm chứng nhiều lớp

| Lượt | Source | Directory | User/Host | Local Maven repo | Toolchain | Mục tiêu |
| --- | --- | --- | --- | --- | --- | --- |
| A | Commit X | `/work/a` | Host A, user A | cache A | JDK/Maven baseline | Reference |
| B | Commit X | `/work/a` | Host A, user A | cache A | Giống A | Local repeatability |
| C | Commit X | `/tmp/checkout-b` | Host A, user A | cache A | Giống A | Build path leak |
| D | Commit X | `/opt/ci/c` | Host B, user B | isolated cache | Pin theo recipe | Independent rebuild |
| E | Commit X | `/workspace/d` | Host C/runner C | clean cache | Pin theo recipe | Hạ tầng độc lập |
| F | Commit X | Khác | Host D | isolated cache | OS/JDK variant nếu contract yêu cầu | Portability |
| G | Commit X | Khác | Independent verifier | verified fetched deps | Recipe công bố | So với release artifact thật |

A/B chỉ là first-pass. C phát hiện lab path leak. D/E là evidence mạnh hơn. F mở rộng variability boundary khi có mục tiêu phù hợp. G là mức cần cho tuyên bố “bên ngoài có thể rebuild binary đã phát hành”.

### 9.1. Thay đổi từng factor khi chẩn đoán

Nếu bạn đồng thời đổi JDK 17 → 21, Linux → Windows, locale, timezone và checkout path, mismatch rất khó xác định nguyên nhân. Hãy tạo baseline, biến một yếu tố tại một thời điểm, rồi làm full matrix khi đã có các constraints.

### 9.2. Không đánh đồng CI runners với independence

Hai jobs có tên khác nhưng dùng cùng host, cùng shared `~/.m2`, cùng workspace mount và cùng container image chưa chắc là hai môi trường độc lập. Đảm bảo path, user/cache/host phù hợp với mục tiêu thử nghiệm, không chỉ đổi job label.

### 9.3. Cân đối chi phí

Không cần mỗi PR chạy trên mười OS. Thực tế có thể dùng:
- PR: local repeatability và `check-buildplan`.
- Merge: clean path/cached dependency checks.
- Release candidate: independent host/user/cache rebuild và compare với candidate.
- Public release: consumer-side/download verification, independent reproducibility report.

## 10. Debug khi hai JAR khác bytes

Quy trình có thứ tự giúp tránh sửa nhầm:

1. Xác nhận hai builds dùng **cùng source commit** và không có dirty/untracked inputs.
2. In toolchain versions (`mvn -version` và `java -version`) rồi đối chiếu profiles.
3. So GAV và effective dependency/plugin versions.
4. Kiểm `project.build.outputTimestamp` và plugin packaging behaviors.
5. So whole JAR SHA-256, sizes, ZIP entry lists.
6. Giải nén vào **hai inspection directories riêng** rồi so từng file.
7. Khi `.class` khác, xem `javap -v` và compiler/annotation processors.
8. Khi text resource khác, xem filtering, encoding, line endings, `project.basedir`, user/home, generated times.
9. Khi ZIP contents bằng nhưng hashes khác, xem entry timestamp, order, permissions, compression.
10. Dùng diffoscope nếu cần; tìm đúng plugin/generator tạo mismatch.
11. Sửa nguồn gây khác biệt, clean rebuild, thử path/user/host/cache độc lập.
12. Kiểm binary/POM/attachments từ **release repository**, không chỉ local outputs.

### 10.1. Lệnh hữu ích

~~~bash
jar tf jar-a.jar
jar tf jar-b.jar
javap -v -classpath jar-a.jar dev.repro.ReproApp
javap -v -classpath jar-b.jar dev.repro.ReproApp
~~~

`jar tf` liệt kê paths, không in toàn bộ ZIP metadata; dùng tools phù hợp để xem entry timestamps/permissions. `javap -v` xem classfile attributes/bytecode, không so toàn JAR. `diffoscope` hỗ trợ phân tích sâu hơn nhưng không có sẵn trong JDK/Maven.

### 10.2. Các lỗi phổ biến

**“Hai SHA-256 giống nên source đã được ký.”** Sai: digest khác digital signature. Xác minh key/signature và trust riêng.

**“Đã `mvn clean` nên các inputs sạch.”** Sai: local repo, environment và custom external outputs còn.

**“`outputTimestamp` đủ để mọi binary reproducible.”** Sai: chỉ một nhóm timestamps, không xóa hidden inputs.

**“Maven `artifact:compare` PASS là bên thứ ba cũng rebuild được.”** Sai: official docs nói test local có thể bỏ sót username/path leaks.

**“Test xanh ở hai checkouts nghĩa JAR giống.”** Sai: tests chỉ xác minh logic đã được test, không so bytes.

**“Java main in cùng output thì JAR bit-for-bit giống.”** Sai: resources/manifest/ZIP metadata có thể khác.

**“Hai Docker jobs là independent.”** Chưa chắc nếu dùng shared cache, same mount và compromised toolchain.

**“File JAR tên và GAV giống nghĩa bytes giống.”** Sai: cần checksum of published file và release repository policy.

**“Compiled target Java 17 đảm bảo vendor JDK khác cho bytecode giống.”** Sai: `--release 17` không pin compiler implementation.

**“SNAPSHOT version pin tên là pin bytes.”** Sai: SNAPSHOT có thể thay đổi; cần resolve artifact timestamp/digest theo policy.

**“Dùng `compare.ignore` với file khác là giải quyết non-reproducibility.”** Sai nếu file vẫn là một phần của release. Chỉ ignore theo hợp đồng đã ghi rõ và đừng báo toàn artifact byte-equal.

**“Reproducible = an toàn.”** Sai: lỗ hổng/supply-chain trust cần kiểm riêng.

### 10.3. Reproducible Central và published artifact

Maven hướng dẫn Reproducible Central là nơi phát triển việc độc lập rebuild artifacts từ Maven Central. Kiểm tra **released artifact** và build recipe tạo thành bằng chứng mạnh hơn local/local, vì tránh trường hợp binary do publisher upload không trùng file mà developer đã test.

Nếu cần so remote reference bằng `maven-artifact-plugin`, tài liệu `compare` cho phép `-Dreference.repo=URL`; đích phải là kho thật được phép, không nhét credentials vào URL hoặc logs.

## 11. Timestamps, source archives và metadata

### 11.1. Ngày build và ngày source

Một file generated lúc `Instant.now()` hoặc chứa `BUILD_TIMESTAMP` runtime có thể làm output đổi giữa runs. Nếu phải ghi thời gian từ source revision, chọn timestamp cố định từ commit/release recipe; nếu provenance cần thời gian thực sự, hãy cân nhắc tách thành signed attestation, không bắt runtime JAR chứa build wall-clock time.

### 11.2. Metadata có tính riêng tư

Absolute paths như `/home/alice/secret-project`, Windows usernames hoặc CI mount paths lọt vào JAR có thể làm lộ cấu trúc máy build. Local repeatability PASS không bắt lỗi vì string vẫn như cũ. Trước public release, inspect binary/resources và lọc secrets/path nội bộ theo policy.

### 11.3. Sources, Javadoc, POM và classifiers

Ngay cả khi main JAR reproducible, `-sources.jar` có thể chứa generated files với timestamp; `-javadoc.jar` có thể phụ thuộc JDK/Javadoc version/locale; POM có CI-friendly placeholder chưa được giải; native classifiers khác nhau theo target. Đặt phạm vi reproducibility trên **tập artifacts thực sự được consumer nhận**, không chỉ chọn file thuận tiện nhất.

### 11.4. Multi-module reactor

Nếu module `api` và `impl` build cùng reactor, `impl` có thể resolve `api` từ reactor thay vì public artifact. Test consumer ngoài reactor với isolated repository để đánh giá POM/GAV đúng. Khi so full release, kiểm cả child modules và phiên bản transitive internal dependencies.

## 12. Checklist kiểm chứng trước khi công bố

- [ ] Có exact source commit/tag, clean tree và documented build command.
- [ ] Maven distribution/Wrapper, JDK distribution, plugin versions được pin.
- [ ] Parent/BOM/dependency coordinates và repository identities được ghi nhận.
- [ ] `project.build.outputTimestamp` đã cấu hình hoặc plugin reproducible mode đã xác nhận.
- [ ] Local repeatability test chạy clean hai lần và so JAR toàn bytes.
- [ ] Checkout ở path khác đã build và so bytes.
- [ ] User/home/hostname/path-specific content đã được rà.
- [ ] Isolated Maven repo/cache test đã chạy.
- [ ] Host/runner độc lập và không chia sẻ workspace.
- [ ] OS/JDK/locale/timezone variation theo support contract đã được xem xét.
- [ ] Không có generated current-time/random output không kiểm soát.
- [ ] JAR ZIP entries, manifest, resources, source archives và POM đã kiểm.
- [ ] `check-buildplan` được sử dụng như nguồn cảnh báo, không là toàn bộ chứng minh.
- [ ] `artifact:compare` hoặc tương đương so với reference chính xác.
- [ ] Published/release artifact được tải lại và so với independent rebuild.
- [ ] Hashes, signatures, provenance và security gates được xử lý riêng.
- [ ] Báo cáo có PASS/FAIL/NOT_RUN theo từng gate, không suy diễn vượt evidence.

## 13. Bài tập và đáp án

**1.** Hai lần `mvn clean package` tại một directory cho SHA-256 giống nhau. Đã có third-party reproducibility chưa?

**Đáp án:** Chưa. Đã có local repeatability; cần external/independent rebuild và published binary comparison.

**2.** Tại sao resource `checkout=${project.basedir}` khiến same-directory PASS nhưng khác path FAIL?

**Đáp án:** Cùng directory thay placeholder bằng cùng chuỗi; khác directory nhúng absolute path khác vào JAR.

**3.** `outputTimestamp` có sửa giá trị `project.basedir` trong filtered resource không?

**Đáp án:** Không, archive entry timestamp không điều khiển resource text.

**4.** JUnit tests của lab PASS ở hai directories có chứng minh JAR byte-equal không?

**Đáp án:** Không. Test chỉ kiểm message và resource tồn tại.

**5.** `mvn clean` có dọn `~/.m2/repository` không?

**Đáp án:** Không, Maven local repository/cache vẫn được giữ trừ khi bạn dùng repo riêng hoặc thao tác khác.

**6.** Maven `artifact:compare` local PASS có giới hạn gì?

**Đáp án:** Username/current path/cache có thể không đổi; Apache Maven nói phải rebuild ở môi trường khác để chứng minh mạnh hơn.

**7.** Nên thay JDK, OS, timezone và path cùng lúc khi debug không?

**Đáp án:** Không. Biến từng factor để xác định nguyên nhân, sau đó thử matrix đầy đủ.

**8.** Nếu published JAR khác candidate, hai local builds PASS có cứu được kết luận release không?

**Đáp án:** Không. Phải so đúng file người dùng tải, xem publisher/staging và provenance.

**9.** SHA-256 của hai files bằng nhau có chứng minh code không malware không?

**Đáp án:** Không. Digest là evidence về bytes, không phải bảo đảm security.

**10.** `-Dmaven.compiler.release=17` có bảo đảm JDK 21 và JDK 17 tạo cùng bytes không?

**Đáp án:** Không, `--release` giới hạn API/classfile target chứ không pin javac implementation.

**11.** Vì sao chỉ so main JAR có thể bỏ sót consumer failure?

**Đáp án:** POM/parent/BOM, sources/Javadoc và các classifiers có thể khác hoặc không hợp lệ.

**12.** Bài lab sau khi đổi `checkout=normalized` ở cả hai directory cho hash giống. Đã chứng minh mọi OS/JDK chưa?

**Đáp án:** Chưa, mới kiểm path independence với toolchain đang dùng.

**13.** Docker image pinned digest có đủ độc lập chưa?

**Đáp án:** Không nếu shared caches, volumes, paths hoặc supply-chain compromised; cần verify môi trường và published reference.

**14.** Khi không có independent verifier, báo cáo đúng là gì?

**Đáp án:** Liệt kê local PASS, checkout variation PASS/FAIL, remote comparison NOT_RUN; không khẳng định independent reproducibility.

**15.** Nếu mismatch chỉ vì timestamp ZIP, có thể gọi bitwise reproducible không?

**Đáp án:** Không; toàn archive bytes khác. Cần sửa timestamp hoặc xác định tiêu chí khác và đặt tên kết quả đúng.

## 14. Tài liệu tham khảo chính thức

1. [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): định nghĩa và giới hạn của local comparison; `outputTimestamp`.
2. [Apache Maven Artifact Plugin — check-buildplan](https://maven.apache.org/plugins/maven-artifact-plugin/check-buildplan-mojo.html): kiểm tra plugins có known issues.
3. [Apache Maven Artifact Plugin — compare](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html): so current output với local/remote reference.
4. [Apache Maven Artifact Plugin — Plugin Details](https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html): `describe-build-output` và `buildinfo`.
5. [Apache Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html): `${...}` placeholder interpolation.
6. [Apache Maven JAR Plugin — jar:jar](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html): archive timestamps.
7. [Reproducible Builds — Build Path](https://reproducible-builds.org/docs/build-path/): absolute paths trong artifacts.
8. [Reproducible Builds — Environment Variations](https://reproducible-builds.org/docs/env-variations/): timezone, locale, OS, timestamps.
9. [Reproducible Builds — Troubleshooting](https://reproducible-builds.org/docs/reproducibility-troubleshooting/): diffoscope và variance diagnosis.
10. [Reproducible Builds — Documentation](https://reproducible-builds.org/docs/): source-date-epoch, reproducible build process, verification.
11. [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): clean, package, verify, install và deploy.
