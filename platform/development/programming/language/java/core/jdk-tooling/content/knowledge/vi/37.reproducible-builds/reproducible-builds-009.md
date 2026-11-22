# So sánh output trong Reproducible Build

## 1. Mục tiêu

Trong reproducible build, cùng source code và cùng đầu vào được kiểm soát phải tạo artifact byte-for-byte giống nhau, kể cả khi build ở thời điểm hoặc thư mục khác nhau.

So sánh output giúp xác nhận build có thể tái lập, phát hiện timestamp hoặc đường dẫn máy local lọt vào artifact, điều tra checksum khác nhau giữa CI agents và kiểm chứng artifact được phát hành.

Một checksum giống nhau là bằng chứng thực tế rất mạnh rằng hai file có cùng byte. Nếu checksum khác nhau, cần tìm vùng khác biệt trước khi kết luận chương trình đã đổi hành vi.

## 2. Bốn mức độ so sánh

| Mức | Câu hỏi | Công cụ |
|---|---|---|
| Byte-for-byte | Hai file có cùng byte không? | SHA-256, cmp, fc /b |
| Cấu trúc archive | Hai JAR có cùng entry và metadata không? | jar, unzip, zipinfo, diffoscope |
| Nội dung từng entry | Class, resource hoặc manifest nào khác? | Hash, javap, diff |
| Hành vi | Hai artifact có chạy giống nhau không? | Test, stdout, integration test |

Byte-for-byte equality là mục tiêu mạnh nhất. Semantic comparison hữu ích khi hash khác nhau, ví dụ hai JAR chứa cùng class nhưng khác timestamp ZIP. Hai chương trình in cùng stdout trong một test nhỏ vẫn có thể khác hành vi trên input khác.

## 3. Kiểm soát đầu vào

Trước khi so sánh, xác nhận hai lần build dùng cùng commit, Gradle Wrapper, JDK/compiler toolchain, dependency và plugin versions, build arguments, generated sources, resource và profile build. Ghi nhận OS, architecture, locale, timezone và encoding nếu build phụ thuộc môi trường.

Nếu hai lần build dùng JDK khác nhau, compiler có thể phát ra bytecode khác dù --release giống nhau. --release 17 kiểm soát language/API target và bytecode version, nhưng không buộc hai compiler build khác nhau tạo cùng byte.

```bash
./gradlew --version
./gradlew clean jar
```

Trên Windows:

```powershell
./gradlew.bat --version
./gradlew.bat clean jar
```

Ghi lại version và checksum artifact. Đừng so sánh build dùng Wrapper với Gradle global không được pin version.

## 4. So sánh SHA-256

SHA-256 tạo fingerprint cố định từ byte của file. Một byte thay đổi sẽ làm hash thay đổi với xác suất áp đảo.

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 ./build-a/build/libs/app.jar
Get-FileHash -Algorithm SHA256 ./build-b/build/libs/app.jar

$hashA = (Get-FileHash -Algorithm SHA256 ./build-a/build/libs/app.jar).Hash
$hashB = (Get-FileHash -Algorithm SHA256 ./build-b/build/libs/app.jar).Hash

if ($hashA -eq $hashB) {
    "BYTE-FOR-BYTE MATCH"
} else {
    "OUTPUTS DIFFER"
}
```

Linux/macOS:

```bash
sha256sum build-a/build/libs/app.jar
sha256sum build-b/build/libs/app.jar
```

Không so sánh SHA-1 với SHA-256 hoặc hash của hai artifact khác nhau. Hash xác nhận tính toàn vẹn của bytes; nó không chứng minh ai đã tạo artifact hoặc nguồn phát hành có đáng tin cậy hay không.

## 5. So sánh byte trực tiếp

Windows:

```powershell
fc /b ./build-a/build/libs/app.jar ./build-b/build/libs/app.jar
```

Linux/macOS:

```bash
cmp build-a/build/libs/app.jar build-b/build/libs/app.jar
```

cmp trả exit code 0 khi file giống nhau. Không dùng diff văn bản thông thường cho JAR, class hoặc ZIP vì đây là file nhị phân.

## 6. So sánh cấu trúc JAR

JAR dựa trên ZIP. Khi checksum khác, kiểm tra danh sách entry:

```bash
jar --list --file build-a/build/libs/app.jar
jar --list --file build-b/build/libs/app.jar
jar --list --verbose --file build-a/build/libs/app.jar
unzip -l build-a/build/libs/app.jar
unzip -t build-a/build/libs/app.jar
zipinfo -v build-a/build/libs/app.jar
```

So sánh tên và số lượng entry, thứ tự, timestamp, compression method, kích thước nén, permission, manifest, META-INF và ZIP extra fields.

jar --validate chủ yếu kiểm tra tính nhất quán của multi-release JAR; không phải công cụ diff tổng quát. Dùng unzip -t để kiểm tra CRC của ZIP.

## 7. Giải nén và so sánh entry

```bash
mkdir -p compare/a compare/b
(cd compare/a && jar --extract --file ../../build-a/build/libs/app.jar)
(cd compare/b && jar --extract --file ../../build-b/build/libs/app.jar)
```

So sánh danh sách đường dẫn tương đối, sau đó so sánh hash từng file. Timestamp file sau giải nén có thể bỏ qua nếu mục tiêu chỉ là so sánh nội dung entry; timestamp bên trong archive vẫn ảnh hưởng byte JAR.

Ví dụ tạo manifest hash từng file bằng PowerShell:

```powershell
$root = (Resolve-Path ./compare/a).Path

Get-ChildItem -LiteralPath $root -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($root.Length).TrimStart([char]92, [char]47)
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
        "$hash  $relative"
    } | Set-Content ./compare/a.sha256
```

Lặp lại cho thư mục compare/b, rồi dùng Compare-Object hoặc diff để tìm entry khác. Danh sách hash này giúp phân biệt entry bị thêm/xóa với entry có nội dung thay đổi.

## 8. So sánh class bằng javap

```bash
javap -classpath build-a/build/libs/app.jar -c -p demo.Main
javap -classpath build-b/build/libs/app.jar -c -p demo.Main
javap -classpath build-a/build/libs/app.jar -v -p demo.Main
```

javap -c hiển thị bytecode; javap -v bổ sung constant pool, annotations, source file, line number và debug attributes. Disassembly giống nhau không đảm bảo class file giống byte-for-byte; hash file .class mới xác nhận bytes chính xác.

## 9. So sánh resource

Kiểm tra encoding, UTF-8 BOM, line ending LF/CRLF, khoảng trắng, thứ tự key, timestamp, build number, absolute path, hostname, locale và timezone.

Chỉ normalize line ending, whitespace hoặc thứ tự key nếu khác biệt đó không mang ý nghĩa. Không normalize artifact trước khi tính checksum. Giữ hash file gốc và ghi rõ quy tắc khi tạo bản sao semantic comparison.

## 10. Dùng diffoscope

diffoscope phân tích khác biệt giữa hai file hoặc thư mục, nhận diện archive và binary rồi trình bày khác biệt ở các lớp bên trong.

```bash
diffoscope build-a/build/libs/app.jar build-b/build/libs/app.jar
```

Công cụ có thể chỉ ra entry ZIP khác timestamp, manifest khác, resource thay đổi, class metadata khác hoặc nested JAR khác. Nếu không cài diffoscope, dùng jar, unzip, javap, hash từng entry và diff.

## 11. Những nguồn không xác định thường gặp

Hai lần build cùng source vẫn có thể tạo output khác do:

| Nguồn | Ví dụ | Hướng xử lý |
|---|---|---|
| Timestamp | Thời gian file trong JAR | Không preserve file timestamps |
| Thứ tự file | Filesystem trả entry theo thứ tự khác | Dùng reproducible file order |
| JDK/compiler | JDK patch phát ra class khác | Pin Java toolchain |
| Gradle/plugin | Task hoặc archive format thay đổi | Dùng Wrapper và pin plugin |
| Dependency | Version động hoặc SNAPSHOT thay đổi | Dependency locking |
| Build path | Absolute path lọt vào resource | Relative path hoặc remap |
| Locale/timezone | Ngày và số được format khác | Đặt locale/timezone rõ ràng |
| Encoding | Default charset khác nhau | Khai báo UTF-8 |
| Randomness | UUID hoặc random seed | Dùng seed ổn định |
| Permission | Mode file trong archive | Permission policy cố định |
| Environment | Build number hoặc branch name | Khai báo input có kiểm soát |
| Parallel generation | Thứ tự output phụ thuộc race | Generator deterministic |

Đặc biệt kiểm tra task sinh build metadata. Chèn new Date(), Instant.now(), hostname hoặc absolute path vào resource sẽ làm artifact thay đổi ở mỗi lần build dù source không đổi.

## 12. Cấu hình Gradle để archive tái lập

Gradle 9.0 trở lên mặc định tạo archive có thứ tự entry ổn định, timestamp cố định và permission ổn định. Hai thuộc tính quan trọng của AbstractArchiveTask là:

- preserveFileTimestamps = false: không lấy timestamp file nguồn đưa vào archive.
- reproducibleFileOrder = true: duyệt file theo thứ tự ổn định, độc lập filesystem.

Groovy DSL:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Kotlin DSL:

```kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Cấu hình tường minh hữu ích khi dự án hỗ trợ Gradle cũ hơn hoặc muốn thể hiện rõ chính sách build. Với Gradle 9+, các giá trị này đã là mặc định nếu không bị ghi đè.

## 13. Pin JDK và dependency

Khai báo Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Toolchain giúp Gradle chọn compiler JDK theo version đã khai báo, thay vì dùng JDK bất kỳ trong JAVA_HOME. options.release = 17 giới hạn API và bytecode target, nhưng không thay thế việc pin compiler khi cần reproducibility ở mức byte.

Dependency locking giữ version đã resolve:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Tạo hoặc cập nhật lock state:

```bash
./gradlew build --write-locks
```

Dependency verification xác nhận artifact dependency tải về có đúng checksum hoặc chữ ký đã tin cậy:

```bash
./gradlew --write-verification-metadata sha256
```

Review gradle/verification-metadata.xml trước khi commit. Locking cố định phiên bản được chọn; verification kiểm tra bytes của artifact nhận được. Hai cơ chế giải quyết hai vấn đề khác nhau.

## 14. So sánh output ở hai thư mục

Build cùng source trong hai workspace độc lập giúp phát hiện đường dẫn tuyệt đối, timestamp và trạng thái local lọt vào artifact.

Ví dụ PowerShell:

```powershell
$source = "C:/work/compare-demo"
$a = "C:/work/build-a"
$b = "C:/work/build-b"

Copy-Item -LiteralPath $source -Destination $a -Recurse
Copy-Item -LiteralPath $source -Destination $b -Recurse

Get-ChildItem -LiteralPath $b -Recurse -File |
    ForEach-Object {
        $_.LastWriteTimeUtc = [DateTime]::UtcNow.AddDays(-20)
    }

Push-Location $a
./gradlew.bat --no-daemon --offline clean jar
Pop-Location

Push-Location $b
./gradlew.bat --no-daemon --offline clean jar
Pop-Location

$jarA = Join-Path $a "build/libs/compare-demo-1.0.0.jar"
$jarB = Join-Path $b "build/libs/compare-demo-1.0.0.jar"

$hashA = (Get-FileHash -Algorithm SHA256 $jarA).Hash
$hashB = (Get-FileHash -Algorithm SHA256 $jarB).Hash

Write-Output $hashA
Write-Output $hashB
Write-Output ($hashA -eq $hashB)
```

Hai workspace có đường dẫn và timestamp file nguồn khác nhau. Nếu toolchain và input giống nhau, hai JAR vẫn phải có cùng SHA-256.

--offline yêu cầu Gradle dùng dependency/plugin đã có trong cache; nó không thay thế dependency locking hoặc verification. Nếu thiếu dependency, tải trước trong môi trường tin cậy hoặc bỏ --offline nhưng giữ nguyên repository và version đã kiểm soát.

## 15. Ví dụ hoàn chỉnh: tạo JAR và so sánh hai lần build

Cấu trúc dự án:

```text
compare-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── Main.java
        └── resources/
            └── app.properties
```

File settings.gradle:

```groovy
rootProject.name = 'compare-demo'
```

File build.gradle:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}

tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Main-Class': 'demo.Main',
            'Implementation-Version': project.version
        )
    }
}
```

File src/main/java/demo/Main.java:

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class Main {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("missing app.properties");
            }
            properties.load(input);
        }

        System.out.println(
                "build-output=" + properties.getProperty("message"));
    }
}
```

File src/main/resources/app.properties:

```properties
message=stable
```

Build hai bản sao trong hai thư mục khác nhau. Khi build hoàn tất, chạy:

```powershell
java -jar $jarA
java -jar $jarB
```

Cả hai phải in:

```text
build-output=stable
```

Trong một lần kiểm thử trên Gradle 9.2.1 và OpenJDK Zulu 24.0.2, project Java 17 release được build từ hai thư mục khác nhau, với timestamp source cách nhau 20 ngày. Kết quả:

```text
BUILD_A_SHA256=3504E0FDE71D7E5D8670EB430F259F7553F18E33108D79E4777F4CE6E5A289B9
BUILD_B_SHA256=3504E0FDE71D7E5D8670EB430F259F7553F18E33108D79E4777F4CE6E5A289B9
HASH_MATCH=True
ENTRY_LIST_MATCH=True
JAVAP_MATCH=True
RUN_OUTPUT_MATCH=True
RUN_OUTPUT=build-output=stable
```

Sau đó đổi resource ở workspace B thành:

```properties
message=changed
```

Build lại B. Hash thay đổi thành:

```text
CHANGED_SHA256=33E93388B2E199AC15649887528DB4F322F8C2D5C212D1955E50C57959CEE706
HASH_DIFFERENT_AFTER_RESOURCE_CHANGE=True
CHANGED_OUTPUT=build-output=changed
OUTPUT_DIFFERENT=True
```

Hai hash cụ thể ở trên là kết quả của một lần chạy trên môi trường đã nêu; máy khác hoặc compiler khác có thể tạo hash khác. Điều cần kiểm tra là hai build cùng input có hash bằng nhau, còn khi resource thực sự đổi thì hash và output của ứng dụng thay đổi.

## 16. Phân biệt khác biệt do metadata với khác biệt do code

Khi hash không khớp, đừng vội kết luận source code sai. Hãy điều tra theo thứ tự:

1. So sánh danh sách entry để xem có file thêm hoặc mất.
2. So sánh timestamp, thứ tự entry, permission và ZIP metadata.
3. So sánh manifest và generated resources.
4. Hash từng entry để tìm file có nội dung khác.
5. Dùng javap -c -v với class khác nhau.
6. Kiểm tra compiler version, dependency và plugin.
7. Kiểm tra đường dẫn, locale, timezone, encoding và environment variables.
8. Chạy diffoscope nếu cần phân tích nhiều lớp archive.
9. Chạy test trên cả hai artifact để xác định khác biệt hành vi.

| Kết quả quan sát | Diễn giải ban đầu |
|---|---|
| Hash giống | Artifact giống byte-for-byte |
| Hash khác, entry list giống | Có thể khác metadata hoặc nội dung entry |
| Chỉ timestamp entry khác | Archive chưa tái lập; byte JAR vẫn khác |
| Manifest khác | Build metadata hoặc cấu hình manifest không ổn định |
| Chỉ resource khác | Kiểm tra generator, encoding, environment và input |
| Class byte khác, javap giống | Có thể khác debug/constant pool/attribute chưa hiển thị |
| Bytecode khác | Kiểm tra compiler, source, annotation processor và compiler flags |
| Artifact giống nhưng runtime output khác | Kiểm tra runtime JDK, environment, external services và dữ liệu |

Một khác biệt metadata vẫn là lỗi reproducibility nếu yêu cầu là byte-for-byte. Tuy nhiên, nó có thể không phải regression về chức năng. Báo cáo cần nêu rõ loại khác biệt thay vì gộp tất cả thành “build bị lỗi”.

## 17. So sánh kết quả test và runtime output

Artifact giống byte không tự bảo đảm ứng dụng hoạt động đúng. Sau khi xác nhận hash, vẫn cần chạy test và kiểm tra runtime theo yêu cầu.

Có thể so sánh unit test, integration test, stdout/stderr trên cùng input, exit code, file được sinh, API response, database migration và performance metrics.

Với output văn bản:

```powershell
java -jar $jarA *> ./compare/a-output.txt
java -jar $jarB *> ./compare/b-output.txt

Compare-Object (Get-Content ./compare/a-output.txt) (Get-Content ./compare/b-output.txt)
```

Đảm bảo hai lần chạy dùng cùng input, working directory, timezone, locale, environment và external service state. Nếu output có request ID, timestamp hoặc random value, cần quyết định đó là dữ liệu có ý nghĩa hay noise trước khi chuẩn hóa.

Không xóa những trường biến động chỉ để làm test xanh nếu chúng là một phần của hợp đồng output. Hãy ghi rõ trường nào được phép khác và vì sao.

## 18. JAR đã ký và artifact có metadata thời gian

Chữ ký JAR phụ thuộc vào nội dung archive và metadata chữ ký. Nếu thay đổi bất kỳ entry nào sau khi ký, chữ ký có thể không còn hợp lệ.

Timestamp trong chữ ký, certificate hoặc quy trình signing có thể khiến hai file đã ký khác nhau dù JAR chưa ký giống hệt. Vì vậy:

1. So sánh JAR chưa ký để xác nhận reproducible packaging.
2. Kiểm tra signing configuration và timestamp authority.
3. Xác minh chữ ký độc lập trên artifact phát hành.
4. Không sửa archive sau khi ký.
5. Ghi riêng checksum của artifact unsigned và signed.

Kiểm tra chữ ký:

```bash
jarsigner -verify -verbose -certs build/libs/app.jar
```

Hash giống nhau không thay thế xác minh chữ ký. Hash cho biết bytes có khớp một fingerprint đã biết hay không; chữ ký giúp xác minh artifact được ký bởi khóa tương ứng và nội dung chưa bị sửa sau khi ký.

## 19. Tự động hóa so sánh trong CI

CI có thể chạy hai build sạch từ cùng commit trong workspace độc lập, sau đó so sánh SHA-256. Nếu hash khác, lưu artifact và log để điều tra.

Một pipeline tối thiểu nên:

1. Checkout cùng commit vào hai workspace sạch.
2. Dùng cùng Gradle Wrapper và JDK toolchain.
3. Khóa dependency và xác minh dependency artifacts.
4. Build với cùng arguments.
5. Tính SHA-256 của artifact.
6. Fail bước reproducibility nếu hash khác.
7. Lưu cả hai artifact, hash, Gradle/JDK version và build logs.
8. Khi khác biệt, tạo báo cáo entry-level hoặc diffoscope.

Không dùng cùng thư mục output cho hai build song song vì chúng có thể ghi đè artifact của nhau. Mỗi build cần workspace và output path độc lập.

Với artifact phát hành, sử dụng môi trường CI sạch và đáng tin cậy. Caching hữu ích cho build thông thường khi được cấu hình đúng; phép thử reproducibility nên chủ động loại trừ trạng thái cũ có thể làm kết quả không rõ nguồn gốc.

## 20. Checklist khi hai output không giống nhau

- [ ] Hai lần build có cùng commit và cùng source contents không?
- [ ] Gradle Wrapper và plugin versions có giống nhau không?
- [ ] JDK vendor, version và compiler toolchain có giống nhau không?
- [ ] Dependency đã khóa version và được verify chưa?
- [ ] Timestamp và thứ tự archive entry có ổn định không?
- [ ] Manifest có build time, hostname hoặc build number không?
- [ ] Generated resources có dùng random, clock hoặc absolute path không?
- [ ] Encoding và line ending có thống nhất không?
- [ ] File permission và archive metadata có khác không?
- [ ] Có task nào đọc environment variables hoặc filesystem order không?
- [ ] Hash từng entry và disassembly đã được so sánh chưa?
- [ ] Hai artifact đã được chạy với cùng input và môi trường chưa?

## 21. Tổng kết

So sánh output là bước xác nhận rằng cùng đầu vào build tạo ra cùng artifact, đồng thời giúp tìm nguyên nhân khi kết quả khác nhau.

Những điểm cần nhớ:

- Dùng SHA-256 để kiểm tra nhanh byte-for-byte equality.
- Dùng cmp hoặc fc /b khi cần so sánh byte trực tiếp.
- Dùng jar --list, unzip, hash từng entry và javap để phân tích cấu trúc.
- Dùng diffoscope khi cần giải thích khác biệt nhị phân phức tạp.
- Phân biệt khác biệt metadata, nội dung class/resource và hành vi runtime.
- Giữ timestamp và thứ tự archive ổn định; Gradle 9+ đã mặc định reproducible archive.
- Pin Gradle, JDK, plugin và dependency; kiểm soát locale, timezone, encoding, đường dẫn và generated files.
- So sánh hai build trong workspace độc lập để phát hiện dữ liệu phụ thuộc máy.
- Giữ nguyên hash artifact gốc; chỉ normalize bản sao khi thực hiện semantic comparison.
- Xác minh chữ ký riêng; checksum không chứng minh nguồn gốc hoặc danh tính người phát hành.

**Tài liệu tham khảo chính thức:**

- [Gradle — Best Practices for Security: Build Output Should Be Byte-for-Byte Reproducible](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Gradle — Working With Files: Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle DSL — Jar](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [Gradle DSL — AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Oracle Java SE 24 — The jar Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Oracle Java SE 24 — The javap Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javap.html)
- [Oracle Java SE 24 — JAR File Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
