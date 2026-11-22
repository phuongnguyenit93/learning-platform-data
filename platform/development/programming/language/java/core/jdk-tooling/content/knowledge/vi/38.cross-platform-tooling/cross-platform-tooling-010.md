# Kiểm thử đa nền tảng cho Java

## 1. Mục tiêu kiểm thử

Kiểm thử đa nền tảng (cross-platform testing) xác nhận ứng dụng Java, build script và công cụ hoạt động đúng trên các hệ điều hành, JDK và filesystem mà sản phẩm hỗ trợ.

Java có bytecode portable, nhưng môi trường chạy vẫn có khác biệt:

- Windows, Linux và macOS dùng quy tắc path, shell, quyền file và process khác nhau.
- Filesystem có thể phân biệt chữ hoa/chữ thường hoặc không.
- Line ending có thể là LF hoặc CRLF.
- POSIX permissions, symbolic link và file locking phụ thuộc hệ điều hành/filesystem.
- Default locale, timezone, charset và environment variables có thể khác.
- Executable, working directory và cách quote command có thể khác.
- JDK vendor, phiên bản JDK và kiến trúc CPU có thể ảnh hưởng compiler, runtime và native integration.

Mục tiêu là chạy cùng test suite trên các môi trường đại diện, đồng thời nhận diện đúng những khác biệt có chủ đích của nền tảng. Không bắt các giá trị hệ thống giống nhau: dấu phân cách thư mục, chẳng hạn, khác nhau giữa Windows và Unix-like systems.

## 2. Xây dựng ma trận môi trường

Một ma trận kiểm thử thường gồm ba trục:

| Trục | Ví dụ | Rủi ro cần phát hiện |
|---|---|---|
| OS | Windows, Ubuntu/Linux, macOS | Path, shell, filesystem, process, permissions. |
| JDK | 17, 21, 25 | API, compiler, runtime behavior, deprecation. |
| Architecture | x64, ARM64 | Native library, JNI, binary compatibility. |

Ma trận khởi đầu phù hợp với một ứng dụng Java 17+:

- Windows, Ubuntu và macOS.
- JDK 17, 21 và 25.
- Compile source với --release 17 nếu Java 17 là baseline.
- Chạy unit test trên từng JDK được chọn.
- Chạy integration test riêng cho database, network, native code hoặc service bên ngoài.

JDK dùng để chạy test và Java release mà source hướng tới là hai thông tin khác nhau. JDK 25 có thể compile source với --release 17 và chạy test trên JDK 25. Nếu cần bảo đảm tương thích runtime Java 17, vẫn phải có job thực sự chạy bằng JDK 17.

Không nhất thiết chạy mọi tổ hợp cho mỗi pull request. Có thể dùng ma trận đầy đủ cho release/nightly và một tập nhỏ cho pull request.

## 3. Portability test và platform-specific test

Portability test kiểm tra hành vi qua API chuẩn, không phụ thuộc một hệ điều hành cụ thể. Ví dụ tạo thư mục bằng Files.createDirectories, ghi UTF-8 và đọc lại nội dung.

Platform-specific test kiểm tra hành vi chỉ có trên một nền tảng hoặc filesystem, ví dụ POSIX permissions hoặc symbolic link.

Các nguyên tắc:

- Assert kết quả nghiệp vụ phải giống nhau.
- Kiểm tra capability của filesystem trước khi dùng tính năng tùy chọn.
- Dùng JUnit assumptions để skip test chỉ khi capability thực sự không có.
- Ghi rõ test nào được skip và lý do.
- Không skip test chỉ vì code đang lỗi trên một nền tảng.

Không nên khẳng định filesystem luôn phân biệt hoa/thường. Hãy tạo file rồi kiểm tra tên viết thường có trỏ tới cùng file hay không. Đây là đặc tính môi trường, không phải điều kiện pass/fail cố định.

## 4. Path và file separator

Không ghép đường dẫn bằng cách nối chuỗi với dấu slash hoặc backslash:

~~~java
String path = root + "\\reports\\result.txt";
~~~

Cách này dễ lỗi trên Linux/macOS và khi path chứa khoảng trắng hoặc Unicode. Dùng Path, Paths và Files:

~~~java
Path report = Path.of("build")
        .resolve("reports")
        .resolve("result.txt");

Files.createDirectories(report.getParent());
Files.writeString(report, "build completed", StandardCharsets.UTF_8);
~~~

Path.resolve tự sử dụng quy tắc của filesystem hiện tại. Với Java 17+, Path.of là API phù hợp để tạo path từ các thành phần.

Không hard-code dấu phân cách thư mục, dấu phân cách classpath, home directory của một user hoặc đường dẫn tuyệt đối chỉ tồn tại trên máy developer. Dùng File.pathSeparator khi cần tạo classpath. Lấy thư mục tạm qua Files.createTempDirectory hoặc JUnit @TempDir.

## 5. Tên file và case sensitivity

Windows thường dùng filesystem không phân biệt hoa/thường theo mặc định; Linux thường phân biệt; macOS phụ thuộc filesystem và cấu hình volume. Hai file Config.properties và config.properties có thể là hai file riêng ở một môi trường nhưng xung đột ở môi trường khác.

Các nguyên tắc:

- Giữ đúng chữ hoa/chữ thường giữa tên file, resource và import.
- Không tạo hai file chỉ khác nhau về case.
- Tránh tên dành riêng của Windows như CON, NUL, PRN, AUX, COM1 và LPT1.
- Tránh tên kết thúc bằng dấu chấm hoặc khoảng trắng khi cần hỗ trợ Windows.
- Tránh ký tự không hợp lệ trong tên file Windows như <, >, :, dấu nháy kép, slash, backslash, |, ? và *.
- Không giả định mọi filesystem hỗ trợ cùng độ dài path hoặc quy tắc Unicode normalization.

Có thể phát hiện case sensitivity bằng phép thử trong thư mục tạm:

~~~java
Path upper = tempDir.resolve("CaseProbe.txt");
Path lower = tempDir.resolve("caseprobe.txt");
Files.writeString(upper, "probe", StandardCharsets.UTF_8);

boolean caseSensitive = !Files.exists(lower);
System.out.println("filesystem.caseSensitive=" + caseSensitive);
~~~

Không assert kết quả luôn true hoặc luôn false. Ghi nhận kết quả để chẩn đoán và thiết kế tên file an toàn.

## 6. Encoding và Unicode

Đừng phụ thuộc default charset khi đọc/ghi file. Default charset có thể khác theo JDK và môi trường. Từ JDK 18, UTF-8 là default charset theo JEP 400, nhưng dự án vẫn nên chỉ định encoding rõ ràng để tương thích với JDK 17 và công cụ ngoài JVM.

Dùng:

~~~java
Files.writeString(path, text, StandardCharsets.UTF_8);
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

Trong Maven:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Trong Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Kiểm thử với nội dung Unicode thực tế, ví dụ tiếng Việt có dấu, CJK hoặc emoji nếu ứng dụng hỗ trợ. Không chỉ kiểm tra ASCII vì lỗi encoding thường không xuất hiện với ASCII.

Với protocol hoặc file format, tuân theo encoding của format đó. Không tự động chuyển mọi nội dung sang UTF-8 nếu chuẩn đầu vào quy định encoding khác.

## 7. Line ending và Git

Các line ending phổ biến:

| Dạng | Ký tự | Thường gặp |
|---|---|---|
| LF | \n | Linux và macOS hiện đại |
| CRLF | \r\n | Windows |
| CR | \r | Một số file/format cũ |

Khi tạo file text cho hệ điều hành hiện tại, có thể dùng System.lineSeparator(). Khi đọc file đến từ nhiều hệ điều hành, String.lines() hoặc BufferedReader.readLine() xử lý các line terminator phổ biến:

~~~java
List<String> lines = Files.readString(path, StandardCharsets.UTF_8)
        .lines()
        .toList();
~~~

Nếu cần bảo toàn byte chính xác, ví dụ file chữ ký hoặc fixture binary, không chuẩn hóa line ending. Chỉ normalize khi format và nghiệp vụ cho phép.

Dùng .gitattributes để thống nhất line ending trong repository:

~~~gitattributes
* text=auto
*.java text eol=lf
*.gradle text eol=lf
*.xml text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.sh text eol=lf
gradlew text eol=lf
*.bat text eol=crlf
mvnw text eol=lf
mvnw.cmd text eol=crlf
~~~

Không dùng core.autocrlf toàn cục như cách sửa lỗi cho mọi project. Quy tắc line ending nên được ghi rõ trong repository.

## 8. Locale, timezone và định dạng ngày/số

Kết quả format có thể thay đổi theo locale mặc định. Dấu thập phân, tên tháng và thứ tự ngày/tháng khác nhau giữa các khu vực.

Nếu format dữ liệu máy đọc, hãy chỉ định locale:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.ROOT);
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withZone(ZoneOffset.UTC);
~~~

Nếu xử lý thời điểm, lưu Instant hoặc epoch và chuyển sang timezone cụ thể ở biên giao tiếp. Đừng dựa vào timezone mặc định của máy CI.

Ví dụ:

~~~java
String date = DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withZone(ZoneOffset.UTC)
        .format(Instant.parse("2025-03-08T23:30:00-05:00"));
~~~

Kết quả chính xác:

~~~text
2025-03-09
~~~

Nếu test thay đổi default locale/timezone, phải khôi phục giá trị ban đầu trong finally để không ảnh hưởng test khác.

## 9. Gọi process mà không phụ thuộc shell

Tránh ghép command thành chuỗi rồi chuyển cho shell:

~~~java
Runtime.getRuntime().exec("cmd /c java -version");
~~~

cmd, PowerShell, Bash và Zsh có quy tắc quote/escape khác nhau. Một command hoạt động trên Windows có thể không chạy trên Linux/macOS.

Dùng ProcessBuilder với từng argument riêng:

~~~java
boolean windows = System.getProperty("os.name")
        .toLowerCase(Locale.ROOT).contains("win");

Path java = Path.of(System.getProperty("java.home"), "bin",
        windows ? "java.exe" : "java");

Process process = new ProcessBuilder(java.toString(), "-version")
        .redirectErrorStream(true)
        .start();
~~~

Thêm timeout và kiểm tra exit code:

~~~java
if (!process.waitFor(10, TimeUnit.SECONDS)) {
    process.destroyForcibly();
    throw new IllegalStateException("Child process timed out");
}

String output = new String(process.getInputStream().readAllBytes(),
        StandardCharsets.UTF_8);

if (process.exitValue() != 0) {
    throw new IllegalStateException(output);
}
~~~

Không giả định executable luôn có hậu tố .exe, luôn nằm trong PATH hoặc có thể gọi qua shell. Lấy đường dẫn từ java.home khi cần chạy cùng JDK đang test.

Khi gọi tool bên ngoài, truyền argument list, đặt working directory rõ ràng, kiểm tra exit code và tránh command phụ thuộc shell nếu không thực sự cần shell.

## 10. Environment variables và system properties

Environment variable có quy tắc khác nhau giữa hệ điều hành. Windows thường không phân biệt case trong tên biến môi trường; Unix-like systems phân biệt. Không tạo hai biến chỉ khác chữ hoa/thường.

Một số system property hữu ích khi chẩn đoán:

| Property | Ý nghĩa |
|---|---|
| os.name | Tên hệ điều hành. |
| os.arch | Kiến trúc CPU. |
| os.version | Phiên bản hệ điều hành. |
| java.version | Phiên bản Java runtime. |
| java.vendor | Nhà cung cấp JDK. |
| java.home | Thư mục runtime Java. |
| file.separator | Dấu phân cách thư mục. |
| path.separator | Dấu phân cách danh sách path. |
| line.separator | Line separator mặc định. |
| user.dir | Working directory hiện tại. |
| user.home | Home directory của user. |
| file.encoding | Encoding mặc định của runtime. |

Dùng Locale.ROOT khi chuẩn hóa os.name:

~~~java
String os = System.getProperty("os.name").toLowerCase(Locale.ROOT);
boolean windows = os.contains("win");
boolean mac = os.contains("mac");
boolean linux = os.contains("linux");
~~~

Chỉ dùng OS detection khi thực sự phải chọn executable hoặc hành vi đặc thù. Với filesystem, network và process, ưu tiên kiểm tra capability thực tế hơn là suy luận từ os.name.

Không log secret từ environment variables trong CI. Chỉ in property cần thiết, không in token, credential hoặc private path không liên quan.

## 11. Filesystem capabilities: permissions và symbolic links

Không phải filesystem nào cũng hỗ trợ cùng file attribute view. POSIX permissions thường có trên Linux/macOS, nhưng Windows có mô hình quyền khác.

Kiểm tra trước khi dùng:

~~~java
FileStore store = Files.getFileStore(tempDir);
boolean supportsPosix = store.supportsFileAttributeView("posix");
~~~

Nếu không hỗ trợ, test POSIX-specific có thể được skip bằng JUnit assumption:

~~~java
assumeTrue(store.supportsFileAttributeView("posix"),
        "This filesystem does not expose POSIX permissions");
~~~

Symbolic link cũng có thể bị hạn chế bởi quyền user hoặc policy của Windows. Khi test symlink:

- Thử tạo link trong thư mục tạm.
- Chỉ skip nếu hệ điều hành/filesystem thực sự không cho phép.
- Nếu tạo được link, assert link trỏ đúng target và nội dung đọc được.
- Không bỏ qua lỗi đọc/ghi target sau khi link đã tạo thành công.

File locking, rename, delete file đang mở và permission inheritance cũng có thể khác. Test các capability này theo contract ứng dụng, không giả định mọi filesystem có semantics giống nhau.

## 12. Temporary directory và test isolation

Không dùng chung thư mục test cố định cho nhiều test hoặc process. Điều đó gây race condition khi CI chạy test song song.

JUnit 5 cung cấp @TempDir:

~~~java
class FileTest {
    @TempDir
    Path tempDir;

    @Test
    void writesAFile() throws Exception {
        Path file = tempDir.resolve("result.txt");
        Files.writeString(file, "hello", StandardCharsets.UTF_8);

        assertEquals("hello",
                Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

JUnit quản lý lifecycle của thư mục tạm. Mỗi test có vùng riêng, giảm phụ thuộc working directory và giúp dọn dẹp sau khi chạy.

Nếu test cần dữ liệu dùng chung, tạo fixture bất biến hoặc tạo bản sao trong temp directory riêng. Không để test phụ thuộc thứ tự chạy.

## 13. Network, port và timing

Không hard-code port như 8080 trong integration test nếu có thể dùng port động:

~~~java
try (ServerSocket server = new ServerSocket(0)) {
    int port = server.getLocalPort();
    // Khởi chạy client kiểm thử với port vừa được cấp.
}
~~~

Port 0 yêu cầu hệ điều hành cấp một port còn trống. Đóng socket khi hoàn tất.

Các lưu ý:

- Không dùng Thread.sleep để đồng bộ test nếu có cơ chế chờ condition.
- Đặt timeout hợp lý cho process, socket và asynchronous operation.
- Đọc/đóng stream của child process để tránh deadlock.
- Không giả định tốc độ disk hoặc network giữa các runner giống nhau.
- Retry chỉ với lỗi tạm thời đã xác định; retry không được che giấu lỗi logic.
- Không phụ thuộc DNS hoặc dịch vụ public trong unit test.

Integration test dùng database hoặc service nên chạy service container hoặc service riêng trong CI, pin version và chờ health check thay vì chờ một khoảng thời gian cố định.

## 14. Java test suite đa nền tảng với JUnit 5

Một test suite nên bao phủ các rủi ro phổ biến bằng API chuẩn. Ví dụ dưới đây chạy trên Java 17+ và không yêu cầu native library.

Lớp tiện ích src/main/java/com/example/PortablePaths.java:

~~~java
package com.example;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class PortablePaths {
    private PortablePaths() {
    }

    public static Path reportFile(Path root) {
        return root.resolve("dữ liệu").resolve("reports").resolve("result.txt");
    }

    public static String stableDate(Instant instant) {
        return DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withZone(ZoneOffset.UTC)
                .format(instant);
    }

    public static void writeUtf8(Path file, String content) throws Exception {
        Files.createDirectories(file.getParent());
        Files.writeString(file, content, StandardCharsets.UTF_8);
    }
}
~~~

Test src/test/java/com/example/CrossPlatformTest.java:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class CrossPlatformTest {
    @TempDir
    Path tempDir;

    @Test
    void buildsPathsWithoutHardCodedSeparatorsAndSupportsUnicode() throws Exception {
        Path file = PortablePaths.reportFile(tempDir.resolve("folder with spaces"));
        PortablePaths.writeUtf8(file, "Xin chào, đa nền tảng");

        assertTrue(Files.isRegularFile(file));
        assertEquals("Xin chào, đa nền tảng",
                Files.readString(file, StandardCharsets.UTF_8));
        assertTrue(file.toString().contains("folder with spaces"));
    }

    @Test
    void readsCommonLineEndingsWithoutAssumingThePlatformSeparator() throws Exception {
        Path file = tempDir.resolve("line-endings.txt");
        Files.writeString(file, "first\r\nsecond\nthird\r", StandardCharsets.UTF_8);

        List<String> lines = Files.readString(file, StandardCharsets.UTF_8)
                .lines()
                .toList();

        assertEquals(List.of("first", "second", "third"), lines);
    }

    @Test
    void formatsDatesWithAnExplicitLocaleAndTimeZone() {
        assertEquals("2025-03-09",
                PortablePaths.stableDate(
                        Instant.parse("2025-03-08T23:30:00-05:00")));
    }

    @Test
    void launchesJavaWithoutInvokingAnOperatingSystemShell() throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path java = Path.of(System.getProperty("java.home"), "bin",
                windows ? "java.exe" : "java");

        assertTrue(Files.isRegularFile(java), "Java executable should exist: " + java);

        Process process = new ProcessBuilder(java.toString(), "-version")
                .redirectErrorStream(true)
                .start();

        if (!process.waitFor(10, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            fail("Child JVM did not finish within 10 seconds");
        }

        String output = new String(process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8);
        assertEquals(0, process.exitValue(), output);
        assertTrue(output.toLowerCase(Locale.ROOT).contains("version"), output);
    }

    @Test
    void detectsFilesystemCaseSensitivityInsteadOfAssumingIt() throws Exception {
        Path upper = tempDir.resolve("CaseProbe.txt");
        Path lower = tempDir.resolve("caseprobe.txt");
        Files.writeString(upper, "probe", StandardCharsets.UTF_8);

        assertTrue(Files.exists(upper));
        boolean caseSensitive = !Files.exists(lower);
        System.out.println("filesystem.caseSensitive=" + caseSensitive);
    }

    @Test
    void reportsPlatformDetailsForDiagnostics() throws Exception {
        FileStore store = Files.getFileStore(tempDir);
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("file.separator=" + File.separator);
        System.out.println("path.separator=" + System.getProperty("path.separator"));
        System.out.println("line.separator=" + System.lineSeparator()
                .replace("\r", "\\r").replace("\n", "\\n"));
        System.out.println("default.charset="
                + java.nio.charset.Charset.defaultCharset());
        System.out.println("filesystem.posix="
                + store.supportsFileAttributeView("posix"));
    }

    @Test
    void checksPosixPermissionsOnlyWhenTheFilesystemSupportsThem() throws Exception {
        FileStore store = Files.getFileStore(tempDir);
        assumeTrue(store.supportsFileAttributeView("posix"),
                "This filesystem does not expose POSIX permissions");

        Path file = tempDir.resolve("permissions.txt");
        Files.writeString(file, "permission probe", StandardCharsets.UTF_8);
        Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(file);
        assertTrue(permissions.contains(PosixFilePermission.OWNER_READ));
    }

    @Test
    void followsSymbolicLinksWhenThePlatformAllowsCreation() throws Exception {
        Path target = tempDir.resolve("target.txt");
        Path link = tempDir.resolve("target-link.txt");
        Files.writeString(target, "linked content", StandardCharsets.UTF_8);

        try {
            Files.createSymbolicLink(link, target.getFileName());
        } catch (UnsupportedOperationException | java.io.IOException
                 | SecurityException ex) {
            assumeTrue(false, "Symbolic link creation is unavailable: " + ex);
        }

        assertTrue(Files.isSymbolicLink(link));
        assertEquals("linked content", Files.readString(link, StandardCharsets.UTF_8));
    }
}
~~~

Bộ test kiểm tra path có khoảng trắng và Unicode, UTF-8, line ending, locale/timezone, process execution, case sensitivity, POSIX capability và symbolic link.

Hai test POSIX/symlink được skip có điều kiện nếu filesystem hoặc quyền user không hỗ trợ. Khi chạy trên Linux/macOS, các test đó có thể chạy bình thường.

## 15. Cấu hình Gradle cho JUnit 5

Ví dụ build.gradle:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.12.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
~~~

Chạy local:

~~~bash
./gradlew clean test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

Dùng Gradle Wrapper và commit gradlew, gradlew.bat, cùng gradle/wrapper/ vào repository. Có thể tạo wrapper bằng:

~~~bash
gradle wrapper --gradle-version 9.2.1
~~~

Wrapper giúp mọi runner dùng cùng Gradle version. JDK được chọn riêng qua CI matrix; options.release = 17 giữ source/API target nhất quán.

## 16. Cấu hình Maven cho JUnit 5

Ví dụ các phần chính trong pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <junit.version>5.12.2</junit.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.12.2</version>
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
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

Surefire 3.5.2 chạy JUnit Platform tests.

Chạy local:

~~~bash
./mvnw -B clean verify
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd -B clean verify
~~~

Dùng Maven Wrapper và commit mvnw, mvnw.cmd, cùng .mvn/wrapper/ để thống nhất Maven version.

## 17. CI matrix với GitHub Actions

Ma trận OS × JDK có thể chạy cùng test suite trên Windows, Ubuntu và macOS.

Ví dụ .github/workflows/cross-platform.yml cho Gradle Wrapper:

~~~yaml
name: Cross-platform Java tests

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  test:
    name: ${{ matrix.os }} / Java ${{ matrix.java }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        java: ['17', '21', '25']

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: gradle

      - name: Run tests (Linux and macOS)
        if: runner.os != 'Windows'
        run: ./gradlew --no-daemon clean test

      - name: Run tests (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: .\gradlew.bat --no-daemon clean test

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-reports-${{ matrix.os }}-java-${{ matrix.java }}
          path: build/reports/tests/test/
          if-no-files-found: ignore
~~~

Ma trận trên tạo chín job: ba OS nhân ba JDK. fail-fast: false giúp các job còn lại tiếp tục để có báo cáo đầy đủ khi một tổ hợp thất bại.

Nếu dùng Maven, đổi cache thành maven và chạy ./mvnw -B clean verify trên Linux/macOS; trên Windows chạy .\mvnw.cmd -B clean verify.

Không dùng lệnh shell đặc thù của một OS trong step dùng chung cho mọi runner. Tách step theo runner.os khi cú pháp command thực sự khác nhau.

## 18. Kiểm tra trên nhiều JDK

OS matrix và JDK matrix trả lời hai câu hỏi khác nhau:

- OS matrix phát hiện khác biệt filesystem, process, path, permission và native binary.
- JDK matrix phát hiện thay đổi compiler, runtime API, garbage collector, TLS, default behavior và deprecation.

Nếu project hỗ trợ Java 17 trở lên:

1. Compile bằng --release 17.
2. Chạy unit test trên JDK 17 để xác nhận baseline.
3. Chạy trên JDK 21 và JDK 25 để phát hiện thay đổi runtime.
4. Ghi lại java.version, java.vendor và os.arch trong CI report.
5. Test native/JNI dependency trên đúng OS và architecture mà sản phẩm phân phối.

Không chỉ đổi JAVA_HOME rồi cho rằng mọi bước build đã dùng JDK mới. Kiểm tra version mà Maven/Gradle daemon thực sự sử dụng; cấu hình toolchain nếu cần compiler JDK khác runtime của build tool.

## 19. Phân loại test và chọn nơi chạy

| Loại test | Ví dụ | Nơi chạy |
|---|---|---|
| Unit test | Path helper, parser, date formatting | Mọi OS/JDK trong matrix chính. |
| Filesystem integration | Permission, symlink, file lock | OS/filesystem hỗ trợ capability. |
| Process integration | Chạy executable ngoài | OS tương ứng. |
| Network integration | HTTP client/server, socket | Matrix chính hoặc service job riêng. |
| Database integration | JDBC driver, migration | Service container/version matrix. |
| Native/JNI test | Load native library | Đúng OS và CPU architecture. |
| Packaging test | JAR, ZIP, installer | Mọi nền tảng phân phối artifact. |
| End-to-end test | Cài đặt và chạy ứng dụng | Release pipeline hoặc nightly. |

Unit test nên nhanh và độc lập. Integration test có thể dùng service container hoặc test environment được pin version. End-to-end test nên chạy ít thường xuyên hơn nếu tốn thời gian, nhưng phải bao phủ đúng nền tảng phát hành.

Docker container trên Windows/macOS thường chạy Linux container; kết quả đó không thay thế test native Windows/macOS.

## 20. Chẩn đoán lỗi chỉ xuất hiện trên một OS

Khi một job thất bại, lưu các thông tin sau:

~~~text
os.name
os.version
os.arch
java.version
java.vendor
java.home
file.separator
path.separator
line.separator
file.encoding
user.dir
user.home
default locale
default time zone
filesystem capability
~~~

Sau đó so sánh với job pass:

1. Xác định test đầu tiên thất bại, không chỉ nhìn lỗi tổng cuối cùng.
2. Kiểm tra path và chữ hoa/thường của file.
3. Kiểm tra encoding và line ending của input.
4. Kiểm tra quyền đọc/ghi/execute và symbolic link.
5. Kiểm tra executable, argument list và working directory của process.
6. Kiểm tra timezone/locale và giá trị mặc định.
7. Kiểm tra JDK vendor/version và dependency native.
8. Tái tạo lỗi trong môi trường cùng OS/JDK trước khi thay đổi code.

Đừng sửa bằng cách thêm sleep hoặc skip test trên OS bị lỗi nếu chưa xác định nguyên nhân. Ghi log capability và dữ liệu môi trường giúp tái hiện lỗi chính xác hơn.

## 21. Lỗi thường gặp khi kiểm thử đa nền tảng

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test pass trên Windows, fail trên Linux | Path viết cứng dấu backslash hoặc file name sai case. | Dùng Path.resolve và kiểm tra case của resource. |
| File có ký tự tiếng Việt bị lỗi | Dùng default charset hoặc encoding không thống nhất. | Chỉ định UTF-8 khi đọc/ghi và cấu hình compiler. |
| Parser đọc thiếu dòng | Giả định chỉ có CRLF hoặc chỉ có LF. | Dùng String.lines()/BufferedReader hoặc parser đúng format. |
| Date/number output khác | Locale/timezone mặc định khác. | Dùng Locale.ROOT, ZoneOffset.UTC hoặc locale nghiệp vụ rõ ràng. |
| Child process không chạy | Gọi shell/executable theo cú pháp OS khác. | Dùng ProcessBuilder argument list và xác định executable đúng. |
| AccessDeniedException | Quyền file, file đang mở hoặc filesystem policy. | Kiểm tra capability và đóng resource đúng lúc. |
| Symlink test fail trên Windows | Thiếu quyền hoặc Developer Mode. | Capability-check và skip đúng test symlink khi không được hỗ trợ. |
| POSIX permission test fail | Filesystem không hỗ trợ POSIX attribute view. | Kiểm tra supportsFileAttributeView("posix"). |
| Test chập chờn trên CI | Dùng shared temp file, port cố định hoặc sleep. | Dùng @TempDir, port 0, timeout và condition-based wait. |
| Build khác nhau giữa JDK | JDK/toolchain không được pin hoặc compile target khác. | Pin JDK matrix và đặt --release. |
| Maven/Gradle dùng sai JDK | Build daemon chạy bằng JDK khác JAVA_HOME dự kiến. | In build JVM version và cấu hình toolchain. |
| Test bị skip quá nhiều | Assumption quá rộng hoặc che lỗi thật. | Chỉ skip khi capability không hỗ trợ và ghi rõ lý do. |
| Native library không load | Thiếu binary đúng OS/architecture hoặc sai library path. | Build/package native binary cho từng nền tảng. |
| Git checkout đổi line ending | Chưa có .gitattributes. | Khai báo eol policy trong repository. |

## 22. Quy trình triển khai kiểm thử đa nền tảng

1. Xác định OS, JDK và architecture mà ứng dụng cam kết hỗ trợ.
2. Chọn một JDK baseline và đặt --release tương ứng.
3. Chuẩn hóa source encoding và line ending bằng UTF-8 cùng .gitattributes.
4. Loại bỏ hard-coded path, shell command và environment assumption.
5. Dùng JUnit @TempDir để cách ly file của từng test.
6. Dùng capability checks cho POSIX permissions, symlink và filesystem-specific behavior.
7. Tạo CI matrix cho Windows, Ubuntu, macOS và các JDK được hỗ trợ.
8. Lưu test report riêng theo từng OS/JDK.
9. Chạy integration test cho database, network, packaging và native library khi phù hợp.
10. Điều tra failure theo log môi trường, không skip lỗi chưa hiểu.
11. Chạy lại release matrix trước khi phát hành.
12. Giữ wrapper, toolchain, dependency và build plugin ở phiên bản xác định.

## 23. Kết quả lab đã kiểm chứng

Bộ test mẫu ở trên đã chạy trên Windows 11 bằng Gradle 9.2.1 và JUnit 5.12.2 với ba JDK đã cài:

| JDK | Kết quả |
|---|---|
| Amazon Corretto 17.0.15 | BUILD SUCCESSFUL |
| Microsoft OpenJDK 21.0.9 | BUILD SUCCESSFUL |
| OpenJDK 25.0.1 | BUILD SUCCESSFUL |

Mỗi lần chạy có sáu test pass và hai test skip. Hai test được skip có lý do cụ thể trên môi trường Windows hiện tại: filesystem không cung cấp POSIX permission view và user hiện tại không có quyền tạo symbolic link. Các test còn lại xác nhận path có Unicode/khoảng trắng, UTF-8, line ending hỗn hợp, UTC/locale cố định, child JVM process và case sensitivity detection.

Đây là kết quả kiểm thử thực tế trên Windows với ba JDK. Workflow matrix ở trên là cấu hình để tiếp tục chạy cùng bộ test trên Ubuntu và macOS trong CI; cần xem kết quả của các runner đó trước khi kết luận toàn bộ ma trận đã pass.

## 24. Tài liệu tham khảo

- [Java NIO File API — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/package-summary.html)
- [ProcessBuilder — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html)
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [GitHub Actions Matrix Builds](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs)
- [Git Attributes and Line Endings](https://git-scm.com/docs/gitattributes)

Kiểm thử đa nền tảng hiệu quả khi cùng một test suite chạy trên các OS/JDK được hỗ trợ, còn test đặc thù chỉ chạy khi capability tương ứng tồn tại. Dùng API Java chuẩn cho path, encoding, process và filesystem; pin build tool/JDK; lưu report theo từng runner để lỗi chỉ xuất hiện trên một nền tảng có thể được tái hiện và sửa đúng nguyên nhân.
