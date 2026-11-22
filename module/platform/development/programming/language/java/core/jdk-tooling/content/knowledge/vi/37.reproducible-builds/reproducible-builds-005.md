# Ổn định thứ tự file trong Java build

**Ổn định file order** là bảo đảm các file được phát hiện, xử lý và ghi vào artifact theo một thứ tự xác định giữa các lần build. Đây là một phần của **reproducible build**: cùng source, dependency và môi trường build phải tạo ra output giống nhau, lý tưởng là byte-for-byte.

Một JAR có thể chứa đúng cùng class và resource nhưng vẫn có SHA-256 khác nếu thứ tự ZIP entries, timestamp hoặc metadata thay đổi. Vì vậy, chỉ giữ nội dung file giống nhau là chưa đủ. Cần kiểm soát thứ tự duyệt thư mục, cách sắp xếp path, thứ tự resource được sinh, archive timestamps, manifest và phiên bản công cụ.

## 1. Stable file order và reproducible build

Hai khái niệm liên quan nhưng không giống nhau:

- **Stable file order:** cùng một tập file được xử lý và ghi vào archive theo cùng thứ tự.
- **Reproducible build:** cùng input và build environment được kiểm soát tạo ra artifact giống hệt từng byte.

Stable file order giải quyết một nguồn nondeterminism. Reproducible build còn cần kiểm soát timestamp, manifest, compiler, dependency, generated files, compression, permissions và metadata khác.

Ví dụ hai JAR có cùng các entry:

~~~text
META-INF/MANIFEST.MF
com/acme/Main.class
config/app.properties
images/logo.png
~~~

Nếu lần build thứ nhất ghi theo thứ tự alphabet, lần thứ hai ghi theo thứ tự filesystem, byte sequence của ZIP archive có thể khác dù nội dung từng file giống nhau. Checksum của hai JAR vì thế khác nhau.

Ổn định thứ tự giúp build cache hoạt động tốt, giảm diff nhiễu, xác minh binary phát hành từ source và tái lập quy trình signing/release. Apache Maven mô tả reproducible build là quá trình tạo đường đi có thể xác minh từ source tới binary; thứ tự output và timestamp phải được kiểm soát. [Apache Maven: Reproducible/Verifiable Builds](https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=293046971)

## 2. Vì sao thứ tự file có thể thay đổi?

Không nên giả định filesystem trả về file theo alphabet hoặc theo thứ tự tạo file.

Các API và cách làm dễ gây nondeterminism:

~~~java
File[] files = directory.listFiles();
~~~

~~~java
try (var paths = Files.list(directory)) {
    paths.forEach(System.out::println);
}
~~~

~~~java
for (String name : hashSet) {
    process(name);
}
~~~

Các nguồn vấn đề:

- Filesystem có thể trả directory entries theo thứ tự khác nhau.
- Windows, Linux và macOS có cách lưu trữ/thăm dò directory khác nhau.
- File được tạo, xóa hoặc rename theo thứ tự khác có thể làm traversal thay đổi.
- Files.walk() không cam kết thứ tự encounter ổn định giữa các filesystem.
- HashMap và HashSet không định nghĩa thứ tự duyệt theo hợp đồng API.
- Nhiều task chạy song song có thể hoàn tất theo thứ tự khác nhau.
- Generated source hoặc resource có thể được ghi theo thứ tự collection nội bộ.
- Glob expansion của shell có thể chịu ảnh hưởng của shell và locale.

Gradle ghi rõ thứ tự directory iteration có thể khác theo OS và filesystem. Apache Maven cũng liệt kê thứ tự entry ZIP/JAR phụ thuộc filesystem là một nguồn build không tái lập. [Gradle: Reproducible Archives](https://docs.gradle.org/current/userguide/best_practices_security.html) [Apache Maven: Sources of unreproducible output](https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=293046971)

**Quy tắc:** nếu thứ tự đầu vào ảnh hưởng tới artifact, hãy tự xác định thứ tự bằng một comparator rõ ràng trước khi xử lý.

## 3. Chuẩn hóa đường dẫn trước khi sắp xếp

Một thứ tự ổn định cần một cách biểu diễn path ổn định.

### Dùng relative path

Không sắp xếp theo absolute path vì đường dẫn chứa thông tin riêng của máy. Thay vào đó, dùng path tương đối với root:

~~~text
src/Main.java
src/resources/config/app.properties
src/resources/images/logo.png
~~~

### Chuẩn hóa separator

Windows dùng dấu backslash, trong khi ZIP/JAR entry path dùng dấu slash. Khi tạo archive entry, dùng:

~~~text
com/acme/Main.class
config/app.properties
images/logo.png
~~~

Dùng path tương đối và chuẩn hóa separator trước khi sort.

### Chọn comparator độc lập locale

Không dùng Collator dựa trên locale mặc định nếu muốn kết quả giống nhau giữa máy có locale khác nhau.

Trong Java, String.compareTo() cho thứ tự từ điển theo giá trị UTF-16 và không phụ thuộc locale. Đây là một lựa chọn rõ ràng cho tên archive entry đã chuẩn hóa.

Nếu nhiều ngôn ngữ hoặc công cụ khác nhau cùng tạo archive, hãy định nghĩa một quy tắc chung cho encoding, Unicode normalization và comparator. Có thể chuẩn hóa tên thành Unicode NFC trước khi sort; đồng thời phát hiện và từ chối hai path trở thành trùng nhau sau chuẩn hóa.

### Quy tắc cho case và path collision

Một số filesystem phân biệt chữ hoa/chữ thường, một số filesystem mặc định không phân biệt. Các tên Config/app.properties và config/app.properties có thể cùng tồn tại trên filesystem này nhưng xung đột trên filesystem khác.

Nếu artifact được phân phối đa nền tảng:

- Chọn quy tắc case-sensitive hoặc case-insensitive rõ ràng.
- Phát hiện tên trùng sau khi áp dụng quy tắc đó.
- Không âm thầm để file nào được ghi sau cùng quyết định nội dung.
- Dùng duplicate policy rõ ràng: fail, merge có quy tắc hoặc chọn một nguồn đã được khai báo.

## 4. Sắp xếp file bằng Java 17+

Ví dụ sau nhận một thư mục root, duyệt tất cả file thường, chuyển path thành dạng tương đối dùng dấu slash, rồi sắp xếp theo String natural order.

Tạo file **StableFileOrderDemo.java**:

~~~java
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public final class StableFileOrderDemo {
    private static String archivePath(Path relativePath) {
        return relativePath.toString()
                .replace(File.separatorChar, '/');
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0])
                .toAbsolutePath()
                .normalize();

        List<Path> ordered;

        try (Stream<Path> paths = Files.walk(root)) {
            ordered = paths
                    .filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(path ->
                            archivePath(root.relativize(path))))
                    .toList();
        }

        for (Path file : ordered) {
            System.out.println(
                    archivePath(root.relativize(file)));
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 StableFileOrderDemo.java
~~~

Chạy với thư mục chứa các file:

~~~bash
java StableFileOrderDemo classes
~~~

Ví dụ thư mục có zeta.txt, alpha.txt, middle.txt, nested/omega.txt và nested/beta.txt. Stdout chính xác:

~~~text
alpha.txt
middle.txt
nested/beta.txt
nested/omega.txt
zeta.txt
~~~

Điểm quan trọng:

1. Files.walk() chỉ thu thập file; không giả định thứ tự duyệt của nó.
2. root.relativize() loại bỏ absolute path.
3. archivePath() chuẩn hóa separator.
4. sorted() áp dụng comparator rõ ràng trước khi xử lý.
5. Các file được xử lý theo cùng một thứ tự khi relative path giống nhau.

Ví dụ này chỉ in danh sách để minh họa. Trong một archiver hoặc build task, hãy dùng chính danh sách đã sort làm thứ tự đầu vào.

### Xử lý symbolic link

Hãy xác định rõ có đưa symbolic link vào archive hay không. Files.walk() mặc định không theo directory symlink, nhưng các API kiểm tra file có thể follow file symlink tùy tùy chọn. Với artifact cần tái lập và an toàn, có thể bỏ qua hoặc từ chối symlink thay vì để kết quả phụ thuộc filesystem đích.

## 5. Thứ tự entry trong JAR và ZIP

JAR dựa trên định dạng ZIP. Archive có local file headers, dữ liệu entry và central directory chứa metadata các entry.

Thứ tự entry có thể ảnh hưởng tới toàn bộ byte sequence của archive. Ngay cả khi file contents không đổi, các yếu tố sau cũng làm JAR khác nhau:

- Entry order.
- Entry timestamps.
- Directory entries.
- Manifest attributes và thứ tự attributes.
- Compression method và compressed bytes.
- Extra fields trong ZIP.
- Metadata do archiver hoặc plugin thêm vào.

Với các entry có tên duy nhất, thay đổi thứ tự thường không làm thay đổi nội dung class/resource mà ứng dụng đọc. Tuy nhiên, checksum và signature của artifact có thể thay đổi.

Duplicate entry là trường hợp khác: cùng một tên xuất hiện nhiều lần có thể tạo hành vi khó đoán giữa các công cụ. Hãy fail build hoặc định nghĩa quy tắc merge rõ ràng.

### Kiểm tra thứ tự trong JAR

Dùng:

~~~bash
jar --list --file app.jar
~~~

Lệnh này hiển thị thứ tự entry trong archive. Có thể dùng jar --verbose --list --file app.jar để xem thêm thông tin entry.

Đừng chỉ so sánh danh sách tên đã sort sau khi giải nén; hãy kiểm tra thứ tự entry thực tế trong archive nếu mục tiêu là reproducible output.

## 6. Cố định timestamp khi đóng gói

Thứ tự ổn định chưa đủ nếu mỗi lần build ghi timestamp hiện tại vào ZIP/JAR.

JDK jar tool có tùy chọn --date để gán một timestamp cố định cho các entry khi tạo archive:

~~~bash
jar --create --file app.jar --date=2024-01-01T00:00:00Z -C classes alpha.txt -C classes middle.txt -C classes nested/beta.txt -C classes nested/omega.txt -C classes zeta.txt
~~~

Danh sách file trong ví dụ được truyền theo thứ tự đã sort. Với dự án lớn, tạo danh sách relative path bằng script hoặc build task rồi truyền danh sách đó cho archiver.

Xem timestamp entry:

~~~bash
jar --verbose --list --file app.jar
~~~

Lưu ý:

- --date cố định timestamp của archive entries; nó không tự giải quyết mọi nguồn nondeterminism.
- Chọn một timestamp cố định hoặc timestamp gắn với source revision, không lấy thời gian build hiện tại.
- ZIP có giới hạn về phạm vi và độ phân giải timestamp; giá trị được lưu có thể được làm tròn theo format.
- Dùng cùng JDK và cùng phiên bản công cụ đóng gói khi cần byte-for-byte reproducibility.
- Nếu dùng plugin tạo JAR, ưu tiên cấu hình reproducible archive được plugin hỗ trợ.

Oracle mô tả --date là tùy chọn gán timestamp cho các entry khi tạo hoặc cập nhật JAR. [Oracle JDK 24: jar command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)

## 7. Cấu hình Maven để tạo JAR ổn định

Maven JAR Plugin hỗ trợ reproducible output timestamp từ phiên bản 3.2.0. Plugin cũng xử lý thứ tự entry để hỗ trợ reproducible JAR. [Maven JAR Plugin: outputTimestamp](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html) [MJAR-263: reproducible entry order and timestamp](https://issues.apache.org/jira/browse/MJAR-263)

Trong pom.xml, khai báo timestamp ổn định và pin plugin version:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</build>
~~~

Maven JAR Plugin đọc project.build.outputTimestamp để đặt timestamp archive. Plugin version 3.2.0 trở lên có hỗ trợ này; ví dụ dùng 3.4.2.

Build:

~~~bash
mvn clean package
~~~

Kiểm tra:

~~~bash
jar --list --file target/app-1.0.0.jar
~~~

Với project nhiều module, quản lý phiên bản plugin ở parent POM/pluginManagement để các module dùng cùng cấu hình.

### Chọn timestamp từ source revision

Một giá trị cố định trong POM là cách dễ hiểu để minh họa. Trong dự án phát hành thường xuyên, có thể dùng timestamp của commit source làm output timestamp, miễn cùng một source revision luôn nhận cùng giá trị.

Maven JAR Plugin chấp nhận timestamp dạng ISO-8601 hoặc số nguyên là giây từ Unix epoch. Không dùng maven.build.timestamp theo thời gian hiện tại vì mỗi lần build sẽ tạo giá trị khác.

### Maven không chỉ có JAR Plugin

Nếu build tạo thêm source JAR, test JAR, WAR, ZIP, assembly hoặc shaded JAR, hãy kiểm tra plugin tương ứng. Cấu hình reproducible cho maven-jar-plugin không tự động bảo đảm mọi plugin bên thứ ba đều tạo output ổn định.## 8. Cấu hình Gradle để ổn định archive order

Gradle cung cấp hai thuộc tính quan trọng trong AbstractArchiveTask:

- reproducibleFileOrder: yêu cầu duyệt file theo thứ tự tái lập.
- preserveFileTimestamps: quyết định có giữ timestamp gốc của file trong archive hay không.

Với Gradle 9.0 trở lên, mặc định archive tasks đã dùng reproducibleFileOrder = true và preserveFileTimestamps = false. Nếu dự án còn hỗ trợ Gradle cũ, hãy cấu hình rõ ràng. [Gradle AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html) [Gradle Best Practices: Reproducible Archives](https://docs.gradle.org/current/userguide/best_practices_security.html)

### Groovy DSL

Trong build.gradle:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    reproducibleFileOrder = true
    preserveFileTimestamps = false
}
~~~

### Kotlin DSL

Trong build.gradle.kts:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}
~~~

Cấu hình này áp dụng cho các archive task như Jar, Zip, War và Tar.

Build:

~~~bash
./gradlew clean build
~~~

Kiểm tra JAR:

~~~bash
jar --list --file build/libs/app-1.0.0.jar
~~~

### Xử lý duplicate entry

Nếu nhiều source directory hoặc dependency đóng góp cùng một archive path, cần có duplicate strategy rõ ràng.

Có thể yêu cầu build fail khi có duplicate:

~~~groovy
tasks.withType(AbstractArchiveTask).configureEach {
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

Với service descriptor cần merge, hãy dùng một bước merge có quy tắc và sort provider names nếu thứ tự provider không mang ý nghĩa ưu tiên. Nếu thứ tự có ý nghĩa runtime, khai báo priority rõ ràng thay vì dựa vào thứ tự duyệt file.

## 9. Ổn định generated resources và service descriptors

File order không chỉ xuất hiện ở bước đóng gói. Nhiều plugin hoặc annotation processor tạo resource trước khi JAR được tạo.

Các ví dụ thường gặp:

- META-INF/services.
- File cấu hình được ghép từ nhiều nguồn.
- Resource index hoặc asset manifest.
- File properties được sinh từ Map.
- Danh sách migration hoặc plugin.
- Generated source file.
- Danh sách class hoặc package được phát hiện bằng scan.

### Service provider file

Một service descriptor có thể chứa:

~~~text
com.acme.json.JsonFormatter
com.acme.xml.XmlFormatter
com.acme.text.TextFormatter
~~~

Nếu build thu thập provider bằng HashSet, thứ tự ghi file có thể thay đổi. Nếu thứ tự không có ý nghĩa ưu tiên, hãy sort provider class names trước khi ghi.

Nếu runtime chọn provider theo thứ tự phát hiện, không được tùy tiện sort để che giấu thiết kế thiếu rõ ràng. Hãy xác định thứ tự ưu tiên bằng cấu hình hoặc metadata riêng.

### Merge resource

Khi nhiều module cùng cung cấp một resource path:

- Xác định file nào được ưu tiên.
- Hoặc merge theo một thuật toán xác định.
- Sort source files trước khi merge.
- Chuẩn hóa line ending và encoding.
- Phát hiện duplicate entry.
- Không để thứ tự hoàn tất của parallel task quyết định nội dung cuối.

### Generated code

Annotation processor hoặc code generator có thể duyệt Map, Set hoặc filesystem. Hãy sắp xếp đầu vào và output trước khi sinh source. Nếu output có timestamp, absolute path, random identifier hoặc build machine name, hãy loại bỏ hoặc chuẩn hóa chúng.

## 10. Các nguồn nondeterminism khác ngoài file order

Ổn định archive order mới là một phần của reproducible build.

| Nguồn | Ví dụ | Cách kiểm soát |
|---|---|---|
| Timestamp | ZIP entry, MANIFEST, pom.properties | Fixed output timestamp |
| File order | Directory traversal | Reproducible archive order |
| Manifest | Built-By, Build-Jdk, attribute order | Chuẩn hóa manifest và pin toolchain |
| Compiler | JDK vendor/version khác nhau | Pin JDK/toolchain |
| Generated source | HashMap iteration, current time | Sort input và bỏ dữ liệu biến động |
| Environment | Locale, timezone, user, absolute path | Chuẩn hóa môi trường |
| Dependency | Version hoặc artifact thay đổi | Lock/pin dependency |
| Compression | Deflater hoặc archiver version | Pin build tool và plugin |
| File permissions | Umask hoặc filesystem | Cấu hình permissions rõ ràng |
| Line endings | CRLF và LF | Quy định encoding/line ending |
| Randomness | UUID hoặc random build ID | Dùng seed xác định hoặc loại bỏ |
| Native tool | Compiler/linker khác phiên bản | Pin toolchain và target platform |

Apache Maven liệt kê cả timestamp, username, thứ tự manifest, thứ tự ZIP/JAR entries, JDK version, Maven version và line endings là những nguồn có thể làm artifact thay đổi. [Apache Maven: Reproducible/Verifiable Builds](https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=293046971)

### Pin JDK và build tool

Dù class file target giống nhau, compiler version khác nhau có thể tạo bytecode khác. Vì vậy, reproducible build cần pin JDK vendor/version và Maven/Gradle/plugin versions.

Với Gradle, dùng Java toolchain để chọn JDK compile. Với Maven, pin compiler plugin và release. Ghi lại OS/architecture nếu build có native code hoặc runtime image.

### Không ghi thời gian hiện tại vào artifact

Tránh các nội dung như:

~~~text
Built-At: 2026-11-10T21:00:00
Built-By: developer-name
Machine: workstation-01
~~~

nếu các giá trị này không phải metadata cần thiết của artifact. Nếu cần build provenance, lưu nó trong một attestation hoặc metadata tách biệt có quy tắc tái lập.

## 11. Xác minh hai lần build có giống nhau

Một bài kiểm tra reproducibility đơn giản:

1. Chọn một commit hoặc source snapshot.
2. Build sạch lần thứ nhất.
3. Lưu artifact và SHA-256.
4. Build sạch lần thứ hai với cùng cấu hình.
5. So sánh SHA-256.
6. Nếu hash khác, so sánh archive entry list và metadata.
7. Dùng diffoscope hoặc công cụ tương tự để tìm khác biệt.

### Maven

~~~bash
mvn clean package
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\app-1.0.0.jar -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum target/app-1.0.0.jar
~~~

Sau đó chạy clean package lần nữa và so sánh hash.

### Gradle

~~~bash
./gradlew clean jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\build\libs\app-1.0.0.jar -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum build/libs/app-1.0.0.jar
~~~

### So sánh entry order

~~~bash
jar --list --file app.jar
~~~

Có thể lưu output của lệnh và so sánh hai danh sách. Nếu list giống nhau nhưng hash khác, tiếp tục kiểm tra timestamps, manifest, compression, extra fields và nội dung entry.

### Khi checksum khác

Dùng diffoscope nếu có:

~~~bash
diffoscope before.jar after.jar
~~~

Hoặc giải nén hai archive vào hai thư mục riêng, rồi so sánh:

- Tên và thứ tự entry.
- Nội dung từng file.
- Timestamp.
- Manifest.
- pom.properties.
- ZIP extra fields.
- File permissions và metadata.
- Các file generated.

Không kết luận reproducibility chỉ từ việc ứng dụng chạy giống nhau. Chạy đúng chức năng là correctness; byte-for-byte equality là một yêu cầu khác.

## 12. Lab Java 17+: sắp xếp file theo relative path

Tạo thư mục mẫu:

~~~text
classes/
├── zeta.txt
├── alpha.txt
├── middle.txt
└── nested/
    ├── omega.txt
    └── beta.txt
~~~

Dùng chương trình StableFileOrderDemo ở mục 4 để in danh sách file đã sort.

Biên dịch:

~~~bash
javac --release 17 StableFileOrderDemo.java
~~~

Chạy:

~~~bash
java StableFileOrderDemo classes
~~~

Stdout:

~~~text
alpha.txt
middle.txt
nested/beta.txt
nested/omega.txt
zeta.txt
~~~

Thử tạo lại các file theo thứ tự khác, thay đổi thời gian modified của file và chạy lại. Output vẫn giống nhau vì thứ tự được xác định từ normalized relative path.

### Lab Maven: build hai lần

POM tối thiểu:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>repro-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Build lần một:

~~~bash
mvn clean package
~~~

Lưu SHA-256, thay đổi thứ tự tạo các resource files nhưng giữ nguyên nội dung, rồi build lần hai:

~~~bash
mvn clean package
~~~

So sánh SHA-256 của hai JAR. Nếu cùng JDK, plugin và source contents, output cần giống nhau với cấu hình reproducible phù hợp.

### Lab Gradle: build hai lần

Trong build.gradle:

~~~groovy
plugins {
    id 'java'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(AbstractArchiveTask).configureEach {
    reproducibleFileOrder = true
    preserveFileTimestamps = false
}
~~~

Build lần một:

~~~bash
./gradlew clean jar
~~~

Lưu SHA-256, thay đổi thứ tự tạo resource files nhưng giữ nguyên nội dung, rồi chạy:

~~~bash
./gradlew clean jar
~~~

So sánh hash. Nếu artifact khác, dùng jar --list và diffoscope để tìm nguồn biến động.

## 13. Kết quả kiểm tra trên môi trường thực hành

Trên OpenJDK 24.0.2, Maven 3.9.12 và Gradle 9.2.1, đã chạy thử hai project nhỏ.

- Maven dùng maven-jar-plugin 3.4.2 và outputTimestamp cố định. Hai lần build sau khi đảo thứ tự tạo resource files có SHA-256 giống nhau.
- Gradle dùng reproducibleFileOrder = true và preserveFileTimestamps = false. Hai lần build có SHA-256 giống nhau.
- jar --list cho thấy archive entries được ghi vào JAR.
- Java sorting demo biên dịch bằng javac --release 17 và in relative paths theo alphabet.
- Cả Maven và Gradle JAR đều chạy được và in REPRODUCIBLE.

SHA-256 cụ thể chỉ có ý nghĩa với đúng source, toolchain và cấu hình của lần chạy đó. Khi thực hành, hãy tính hash của artifact do chính bạn build.

## 14. Troubleshooting

### Hash thay đổi nhưng file contents giống nhau

Kiểm tra entry order, timestamps, manifest, pom.properties, ZIP extra fields và compression metadata. Dùng diffoscope hoặc giải nén archive để so sánh.

### Entry order thay đổi giữa Windows và Linux

Không dùng thứ tự Files.walk(), listFiles() hoặc shell glob làm thứ tự đóng gói. Chuẩn hóa relative path và sort bằng comparator rõ ràng hoặc bật reproducibleFileOrder của build tool.

### Gradle archive vẫn khác nhau

Kiểm tra tất cả archive tasks, bao gồm task tùy chỉnh và plugin bên thứ ba. Xác nhận preserveFileTimestamps=false và reproducibleFileOrder=true. Kiểm tra generated files và duplicate strategy.

### Maven JAR vẫn khác nhau

Kiểm tra maven-jar-plugin có phiên bản từ 3.2.0 trở lên và project.build.outputTimestamp có giá trị ổn định. Kiểm tra plugin tạo source JAR, shaded JAR, manifest, assembly hoặc generated metadata.

### Resource file trùng tên

Đặt duplicate policy rõ ràng. Với build cần an toàn, fail ngay khi có duplicate ngoài ý muốn. Nếu cần merge, sort nguồn đầu vào và định nghĩa thứ tự merge.

### Service provider được phát hiện theo thứ tự khác

Không dùng HashSet hoặc directory traversal trực tiếp. Sort provider list nếu thứ tự không mang ý nghĩa ưu tiên. Nếu có priority, lưu priority thành cấu hình rõ ràng.

### Build local ổn định nhưng CI khác

So sánh JDK, Maven/Gradle, plugin versions, locale, timezone, environment variables, OS, architecture, file permissions và dependency resolution. Pin toolchain và build dependencies.

### JAR chạy được nhưng hash không giống

Hai artifact có thể tương đương về chức năng nhưng không reproducible. Tách kiểm tra correctness khỏi kiểm tra byte-for-byte equality.

## 15. Quy trình ổn định file order trong CI

1. Pin JDK vendor/version và Maven/Gradle version.
2. Khóa dependency và plugin versions.
3. Chuẩn hóa relative path và encoding.
4. Sort các file được phát hiện bằng comparator cố định.
5. Xử lý duplicate entry theo policy rõ ràng.
6. Sắp xếp generated resource và descriptor nếu thứ tự không mang ý nghĩa ưu tiên.
7. Cố định archive timestamps.
8. Dùng reproducible archive options của Maven/Gradle.
9. Tránh metadata phụ thuộc username, hostname, thời gian hiện tại hoặc absolute path.
10. Chạy clean build trong hai workspace độc lập.
11. So sánh SHA-256 của artifact.
12. Nếu hash khác, kiểm tra entry list và dùng diffoscope.
13. Lưu build environment, source revision và checksum.
14. Chỉ phát hành artifact sau khi correctness và reproducibility checks đạt yêu cầu.

## 16. Checklist ổn định file order

- Không dựa vào thứ tự trả về của Files.list(), Files.walk() hoặc File.listFiles().
- Không dựa vào thứ tự duyệt HashMap/HashSet.
- Dùng relative path thay cho absolute path.
- Chuẩn hóa separator thành / khi tạo archive entry.
- Dùng comparator không phụ thuộc locale.
- Xác định Unicode normalization và case policy nếu cần build đa nền tảng.
- Phát hiện path collision sau chuẩn hóa.
- Đặt duplicate entry policy rõ ràng.
- Sort generated sources, resources và service descriptors.
- Cố định timestamp trong ZIP/JAR.
- Dùng Maven JAR Plugin từ 3.2.0 trở lên và outputTimestamp ổn định.
- Với Gradle, bật reproducibleFileOrder và tắt preserveFileTimestamps.
- Pin JDK, build tool, plugin và dependency versions.
- Kiểm tra manifest và generated metadata.
- So sánh SHA-256 sau hai clean builds.
- Dùng jar --list để kiểm tra archive entry order.
- Dùng diffoscope khi hash khác.
- Phân biệt correctness với byte-for-byte reproducibility.

## 17. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Stable file order | Thứ tự xử lý file xác định giữa các lần build |
| Reproducible build | Build cùng input tạo artifact byte-for-byte giống nhau |
| Nondeterminism | Kết quả phụ thuộc yếu tố không được kiểm soát |
| Relative path | Đường dẫn tương đối với một root |
| Archive entry | Một file hoặc directory được lưu trong ZIP/JAR |
| Central directory | Bảng metadata entry trong ZIP archive |
| Timestamp normalization | Đặt timestamp archive theo giá trị cố định |
| File traversal | Duyệt cây thư mục để tìm file |
| Duplicate entry | Nhiều nguồn ghi cùng archive path |
| Manifest | Metadata của JAR trong META-INF/MANIFEST.MF |
| outputTimestamp | Timestamp tái lập cho archive do Maven JAR Plugin tạo |
| reproducibleFileOrder | Gradle property kiểm soát thứ tự file trong archive |
| preserveFileTimestamps | Gradle property giữ hoặc loại timestamp gốc |
| SOURCE_DATE_EPOCH | Quy ước timestamp đầu vào cho reproducible builds |
| SHA-256 | Hash dùng so sánh chính xác nội dung artifact |
| diffoscope | Công cụ phân tích khác biệt sâu giữa hai artifact |

Ổn định file order bắt đầu bằng việc chuẩn hóa relative path và sort rõ ràng trước khi đóng gói. Maven và Gradle đã có cơ chế hỗ trợ archive tái lập; hãy cấu hình timestamp, pin toolchain, kiểm soát generated resources và xác minh bằng SHA-256. Chỉ khi cả thứ tự file và metadata được kiểm soát, cùng source mới có thể tạo ra artifact giống hệt qua nhiều lần build.

## Tài liệu tham khảo

- Apache Maven — Reproducible/Verifiable Builds: https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=293046971
- Apache Maven — Maven JAR Plugin: https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html
- Apache Maven — MJAR-263: https://issues.apache.org/jira/browse/MJAR-263
- Gradle — Best Practices for Security and Reproducible Builds: https://docs.gradle.org/current/userguide/best_practices_security.html
- Gradle — AbstractArchiveTask: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html
- Oracle JDK 24 — The jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- OpenJDK — Reproducible Builds: https://reproducible-builds.org/