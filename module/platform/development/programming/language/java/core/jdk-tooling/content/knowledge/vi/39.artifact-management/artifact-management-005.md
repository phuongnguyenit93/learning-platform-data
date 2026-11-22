# Checksum artifact trong Java

**Checksum artifact** là giá trị được tính từ toàn bộ byte của một file bằng một thuật toán hash. Khi tính lại checksum sau khi tải, sao chép hoặc lưu trữ artifact, ta có thể so sánh hai giá trị để phát hiện file bị thay đổi, hỏng hoặc không đầy đủ.

Trong Java build/release, artifact có thể là JAR, WAR, ZIP, native image, distribution archive, installer, container image hoặc file được phát hành cho người dùng. Checksum thường được công bố bên cạnh artifact để người nhận kiểm tra tính toàn vẹn trước khi cài đặt hoặc triển khai.

Cần phân biệt hai mục tiêu:

- **Integrity (tính toàn vẹn):** bytes của file có giống với bytes mà checksum tham chiếu mô tả hay không?
- **Authenticity (tính xác thực):** checksum hoặc artifact có thực sự đến từ nhà phát hành đáng tin cậy hay không?

SHA-256 giúp xác nhận tính toàn vẹn khi digest tham chiếu đến từ một nguồn đáng tin cậy. Nếu kẻ tấn công có thể thay cả file và file checksum trên cùng một máy chủ không được bảo vệ, phép so sánh vẫn có thể thành công. Để xác thực nguồn gốc, cần chữ ký số hoặc một kênh phân phối checksum được bảo vệ.

## 1. Checksum và cryptographic hash là gì?

Checksum là thuật ngữ rộng cho giá trị dùng để phát hiện thay đổi dữ liệu. Một số checksum đơn giản như CRC32 phù hợp phát hiện lỗi truyền tải ngẫu nhiên, nhưng không chống được hành vi cố ý tạo dữ liệu va chạm.

Cryptographic hash function nhận đầu vào có độ dài bất kỳ và tạo digest có độ dài cố định. Thuật toán hash mật mã được thiết kế để khó tìm hai đầu vào khác nhau có cùng digest.

Một số thuật toán thường gặp:

| Thuật toán | Độ dài digest | Khuyến nghị |
|---|---:|---|
| SHA-256 | 256 bit (64 ký tự hex) | Lựa chọn mặc định tốt cho artifact hiện nay |
| SHA-384 | 384 bit (96 ký tự hex) | Dùng khi chính sách yêu cầu SHA-2 mạnh hơn |
| SHA-512 | 512 bit (128 ký tự hex) | Phù hợp khi hệ thống hỗ trợ và cần digest dài hơn |
| SHA-1 | 160 bit | Không dùng cho xác minh bảo mật mới |
| MD5 | 128 bit | Không dùng cho xác minh bảo mật |
| CRC32 | 32 bit | Phát hiện lỗi ngẫu nhiên, không chống giả mạo |

SHA-256 và SHA-512 thuộc họ SHA-2. Với phần lớn Java artifact, SHA-256 là lựa chọn phổ biến vì được hỗ trợ rộng rãi và đủ mạnh cho kiểm tra tính toàn vẹn.

Không chọn MD5 hoặc SHA-1 cho quy trình phát hành mới. Các thuật toán này có điểm yếu collision đã biết; kẻ tấn công có thể tạo hai nội dung khác nhau có cùng digest trong một số kịch bản.

Checksum không phải mã hóa. Hash không thể giải mã ngược để lấy lại file gốc, và một digest không che giấu nội dung artifact.

## 2. Hash hoạt động trên byte, không phải tên file

SHA-256 nhận một dãy byte. Tên file, phần mở rộng và đường dẫn không tham gia vào phép tính, trừ khi chúng được đưa vào nội dung cần hash.

Vì vậy:

- Đổi tên `app.jar` thành `release.jar` không làm thay đổi checksum.
- Thay một byte trong JAR gần như chắc chắn tạo digest khác.
- Thay timestamp hoặc thứ tự entry trong ZIP/JAR có thể làm checksum toàn file khác.
- Giải nén rồi nén lại archive thường tạo file bytes khác, kể cả nội dung các file bên trong giống nhau.
- Hai file có cùng nội dung byte nhưng nằm ở hai thư mục khác nhau sẽ có cùng checksum.

Checksum của một artifact là checksum của chính file được phân phối. Không hash nội dung sau khi giải nén nếu mục tiêu là xác minh file tải về có nguyên vẹn hay không.

Với thư mục chứa nhiều file, cần một manifest mô tả checksum của từng file và đường dẫn tương ứng. Không thể dùng một checksum duy nhất của thư mục nếu chưa xác định cách chuẩn hóa thứ tự file, tên file, permission và metadata.

## 3. SHA-256 và ý nghĩa của digest

SHA-256 luôn tạo ra 256 bit, thường được biểu diễn bằng 64 ký tự hexadecimal. Một digest có dạng:

```text
ba7816bf8f01cfea414140de5dae2223
b00361a396177a9cb410ff61f20015ad
```

Đây là SHA-256 của đúng ba byte ASCII abc, không có newline ở cuối.

Digest thường được viết thành một dòng:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  app.jar
```

Phần tên file là metadata theo định dạng checksum manifest; bản thân thuật toán SHA-256 chỉ hash bytes của file.

Một digest không tiết lộ nội dung file theo cách có thể đảo ngược. Tuy nhiên, với nội dung nhỏ hoặc dễ đoán, người khác có thể hash các khả năng để đối chiếu. Vì thế, không dùng checksum để lưu password; password cần password hashing scheme chuyên dụng có salt và cost factor.

## 4. Khi nào cần checksum artifact?

Checksum có giá trị trong nhiều giai đoạn của vòng đời artifact:

| Giai đoạn | Mục đích |
|---|---|
| Build | Ghi lại fingerprint của JAR/WAR/ZIP vừa tạo |
| Upload | Phát hiện file bị lỗi trong quá trình upload |
| Download | Kiểm tra file nhận được có giống file phát hành |
| Artifact repository | Xác minh artifact lưu trữ không bị thay đổi |
| CI/CD | Chặn deploy nếu checksum không khớp |
| Backup/mirror | So sánh bản sao giữa các hệ thống |
| Incident response | Xác định hai bản artifact có giống nhau hay không |
| Release audit | Lưu fingerprint gắn với version và commit |

Ví dụ, một release `orders-service-2.4.0.jar` được upload lên artifact repository. Pipeline tạo file `orders-service-2.4.0.jar.sha256`. Khi môi trường staging tải JAR, nó tính lại SHA-256 và so sánh với digest đã được công bố. Chỉ khi khớp, pipeline mới tiếp tục deploy.

Checksum không thay thế test, malware scanning, signature verification hoặc kiểm tra provenance. Nó là một bước xác minh byte identity.

## 5. Tạo checksum trên Linux

GNU Coreutils cung cấp lệnh `sha256sum`:

```sh
sha256sum app.jar
```

Output có dạng:

```text
<64-hex-character-digest>  app.jar
```

Lưu checksum vào file sidecar:

```sh
sha256sum app.jar > app.jar.sha256
```

Xác minh file:

```sh
sha256sum --check app.jar.sha256
```

Khi đúng, output thường có dạng:

```text
app.jar: OK
```

Khi file thay đổi, lệnh báo `FAILED` và trả exit code khác 0. CI nên kiểm tra exit code để dừng pipeline.

Nếu muốn manifest cho nhiều artifact:

```sh
sha256sum app.jar app-sources.jar app.zip > SHA256SUMS
sha256sum --check SHA256SUMS
```

Manifest lưu digest cùng tên file. Khi xác minh, chạy từ thư mục có các file tương ứng hoặc dùng đường dẫn tương đối nhất quán.

## 6. Tạo checksum trên macOS

macOS thường có `shasum`:

```sh
shasum -a 256 app.jar
```

Tạo sidecar:

```sh
shasum -a 256 app.jar > app.jar.sha256
```

Có thể dùng OpenSSL nếu được cài:

```sh
openssl dgst -sha256 app.jar
```

Để xác minh, tính lại checksum và so sánh với digest tham chiếu đã nhận từ nguồn tin cậy. GNU `sha256sum --check` không phải lúc nào cũng được cài sẵn trên macOS; nếu dùng manifest GNU, có thể cài GNU Coreutils hoặc dùng script xác minh phù hợp.

Không copy checksum từ terminal bằng cách bỏ khoảng trắng hoặc ký tự xuống dòng tùy tiện nếu định dạng manifest cần tên file. Với so sánh thủ công, chỉ so sánh chuỗi digest đã được trim và kiểm tra đủ 64 ký tự hex.

## 7. Tạo và xác minh checksum trên Windows

PowerShell có sẵn `Get-FileHash`:

```powershell
Get-FileHash -Path .\app.jar -Algorithm SHA256
```

Kết quả gồm:

- `Algorithm`: thuật toán hash.
- `Hash`: digest hexadecimal.
- `Path`: đường dẫn file được hash.

Lưu digest vào sidecar chỉ chứa hash:

```powershell
$hash = (Get-FileHash -Path .\app.jar -Algorithm SHA256).Hash
$hash.ToLowerInvariant() | Set-Content -Path .\app.jar.sha256 -NoNewline -Encoding ascii
```

Xác minh:

```powershell
$expected = (Get-Content .\app.jar.sha256 -Raw).Trim()
$actual = (Get-FileHash -Path .\app.jar -Algorithm SHA256).Hash

if ($actual -ne $expected) {
    throw "Checksum mismatch: app.jar"
}

Write-Output "app.jar: OK"
```

Stdout khi checksum khớp:

```text
app.jar: OK
```

PowerShell so sánh chuỗi không phân biệt hoa/thường theo mặc định. Nếu muốn kiểm tra định dạng trước khi so sánh, xác nhận digest có đúng 64 ký tự hexadecimal.

Một lựa chọn khác là `certutil`:

```cmd
certutil -hashfile app.jar SHA256
```

`Get-FileHash` thuận tiện hơn cho script PowerShell vì trả về object có thuộc tính `Hash` rõ ràng.

## 8. Ví dụ Java 17+: tính SHA-256 bằng MessageDigest

Java cung cấp `MessageDigest` trong package `java.security`. Ví dụ dưới đây tính SHA-256 của chuỗi `abc`, chuyển digest sang hexadecimal và so sánh với giá trị tham chiếu đã biết.

Tạo file `ChecksumDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public class ChecksumDemo {
    public static void main(String[] args) throws Exception {
        byte[] input = "abc".getBytes(StandardCharsets.UTF_8);

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] actualBytes = digest.digest(input);

        String actual = HexFormat.of().formatHex(actualBytes);
        String expected =
                "ba7816bf8f01cfea414140de5dae2223"
              + "b00361a396177a9cb410ff61f20015ad";

        byte[] expectedBytes = HexFormat.of().parseHex(expected);
        boolean matches = MessageDigest.isEqual(
                expectedBytes, actualBytes);

        System.out.println("sha256=" + actual);
        System.out.println("matches=" + matches);
    }
}
```

Biên dịch:

```sh
javac ChecksumDemo.java
```

Chạy:

```sh
java ChecksumDemo
```

Stdout chính xác:

```text
sha256=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
matches=true
```

`MessageDigest.getInstance("SHA-256")` lấy implementation của thuật toán từ provider được JVM cấu hình. Nếu thuật toán không có, API ném `NoSuchAlgorithmException`; SHA-256 là thuật toán được các Java platform implementations thông dụng hỗ trợ.

`HexFormat` có từ Java 17, dùng để chuyển byte array sang chuỗi hex và parse chuỗi hex trở lại. `MessageDigest.isEqual()` so sánh hai digest byte array; cách này phù hợp khi cần tránh so sánh chuỗi bằng logic dừng ngay tại byte đầu tiên khác nhau.

## 9. Hash file lớn theo streaming

Không nên dùng `Files.readAllBytes()` cho file lớn vì toàn bộ file sẽ được nạp vào RAM. Hãy đọc theo buffer và cập nhật `MessageDigest` từng phần.

Tạo file `Sha256File.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class Sha256File {
    public static String sha256(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];

        try (InputStream input = Files.newInputStream(path)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }

    public static boolean verify(Path path, String expected)
            throws IOException, NoSuchAlgorithmException {
        String normalized = expected.trim();

        if (!normalized.matches("(?i)[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                    "Expected SHA-256 must contain 64 hex characters");
        }

        byte[] expectedBytes = HexFormat.of().parseHex(normalized);
        byte[] actualBytes = HexFormat.of().parseHex(sha256(path));

        return MessageDigest.isEqual(expectedBytes, actualBytes);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java Sha256File <file> <expected-sha256>");
            System.exit(2);
        }

        Path file = Path.of(args[0]);
        String actual = sha256(file);
        boolean matches = verify(file, args[1]);

        System.out.println("sha256=" + actual);
        System.out.println("verified=" + matches);

        if (!matches) {
            System.exit(1);
        }
    }
}
```

Biên dịch:

```sh
javac Sha256File.java
```

Chạy với artifact và digest tham chiếu:

```sh
java Sha256File app.jar EXPECTED_SHA256
```

Output:

```text
sha256=<64-hex-character-digest>
verified=true
```

Thay `EXPECTED_SHA256` bằng digest thực tế lấy từ nguồn tin cậy. Nếu file sai, chương trình in `verified=false` và thoát với exit code 1. Nếu tham số digest sai định dạng, chương trình ném `IllegalArgumentException`.

Buffer 8 KiB giúp bộ nhớ sử dụng không tăng theo kích thước file. Có thể tăng buffer nếu benchmark cho thấy cần thiết; tính đúng đắn không phụ thuộc buffer size.

Tạo một `MessageDigest` riêng cho mỗi lần tính hash. Không chia sẻ cùng một instance giữa nhiều thread vì `MessageDigest` có state thay đổi theo từng lần update.

## 10. Xác minh file ngay sau khi tải xuống

Một quy trình an toàn nên xác minh file trước khi giải nén, chạy hoặc triển khai.

Ví dụ với Linux:

```sh
curl -fL -o app.jar https://downloads.example.com/app.jar
curl -fL -o app.jar.sha256 https://downloads.example.com/app.jar.sha256
sha256sum --check app.jar.sha256
```

Nếu lệnh xác minh thất bại, không deploy file đó. Kiểm tra lại URL, network, artifact version và checksum tham chiếu.

Tuy nhiên, nếu cả `app.jar` và `app.jar.sha256` đều tải từ cùng một nguồn không xác thực, kẻ tấn công kiểm soát nguồn có thể thay cả hai. Cần xác minh checksum qua kênh tin cậy độc lập hoặc xác minh chữ ký số của release metadata.

Không chạy artifact trước khi kiểm tra checksum. Nếu artifact là script, installer hoặc executable, việc chạy trước có thể thực thi nội dung đã bị thay đổi.

## 11. Integrity khác authenticity

Đây là điểm quan trọng nhất khi dùng checksum cho release.

Giả sử nhà phát hành đăng:

- `app-2.4.0.jar`
- `app-2.4.0.jar.sha256`

Người dùng tải cả hai từ cùng một máy chủ. Nếu file JAR bị thay đổi nhưng file checksum vẫn là bản cũ, kiểm tra sẽ phát hiện. Nhưng nếu kẻ tấn công thay cả JAR và checksum, phép kiểm tra có thể vẫn báo thành công.

Vì vậy:

- Checksum xác nhận bytes của artifact khớp digest tham chiếu.
- Chữ ký số xác minh metadata/artifact được ký bởi private key tương ứng.
- Trust policy xác định public key hoặc identity nào được chấp nhận.
- Provenance mô tả artifact được tạo từ source/build process nào.

Đối với release quan trọng, công bố checksum cùng chữ ký detached hoặc signed manifest. Người nhận cần xác minh chữ ký bằng public key/identity đã tin cậy từ trước.

Không coi một file checksum nằm cạnh artifact trên cùng host là bằng chứng độc lập về nguồn gốc.

## 12. Ký checksum hoặc manifest bằng chữ ký số

Một release có thể dùng GPG/OpenPGP để ký file checksum:

```sh
gpg --armor --detach-sign SHA256SUMS
```

Lệnh tạo file chữ ký detached, thường là `SHA256SUMS.asc`. Người nhận kiểm tra chữ ký:

```sh
gpg --verify SHA256SUMS.asc SHA256SUMS
```

Sau khi chữ ký hợp lệ và signer được tin cậy, kiểm tra checksum trong manifest:

```sh
sha256sum --check SHA256SUMS
```

Thứ tự xác minh rất quan trọng:

1. Xác minh chữ ký của manifest.
2. Kiểm tra danh tính/key fingerprint của signer theo trust policy.
3. Xác minh checksum của artifact.
4. Chỉ sau đó mới cài đặt hoặc deploy.

Chữ ký hợp lệ chỉ chứng minh dữ liệu được ký bởi private key tương ứng. Nếu public key không được xác thực hoặc key bị lộ, kết luận về nguồn gốc không đáng tin.

Trong hệ thống hiện đại, có thể dùng Sigstore/Cosign để ký artifact hoặc container image và xác minh certificate identity theo policy. Với CI supply chain, kết hợp signature với provenance/attestation để biết artifact được build từ commit, workflow và builder nào.

## 13. Tạo checksum manifest cho nhiều artifact

Một release thường chứa nhiều file:

```text
release/
├── app.jar
├── app-sources.jar
├── app-javadoc.jar
├── app.zip
└── SHA256SUMS
```

Trên Linux, tạo manifest:

```sh
cd release
sha256sum app.jar app-sources.jar app-javadoc.jar app.zip > SHA256SUMS
```

Kiểm tra tất cả file:

```sh
sha256sum --check SHA256SUMS
```

Manifest phải chứa tên file tương ứng và digest của từng artifact. Không đưa chính file `SHA256SUMS` vào danh sách mà nó đang hash vì sẽ tạo tham chiếu vòng.

Đối với release có thư mục con, dùng đường dẫn tương đối nhất quán. Nếu file được di chuyển, manifest có thể không tìm thấy file dù bytes không đổi. Điều này là vấn đề định vị file, không phải lỗi thuật toán hash.

Để tạo manifest ổn định, sort danh sách file theo quy tắc xác định và không dùng thứ tự filesystem ngẫu nhiên. Nếu dùng script tự viết, cần xử lý đúng khoảng trắng, newline và ký tự đặc biệt trong tên file; ưu tiên định dạng manifest có escaping đã được định nghĩa.

## 14. Tạo manifest checksum bằng Java

Java có thể tính checksum cho nhiều artifact và ghi manifest UTF-8. Ví dụ sau dùng đường dẫn tương đối, sắp xếp theo tên và ghi một dòng cho mỗi file.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;

public class ChecksumManifest {
    public static void main(String[] args) throws Exception {
        Path root = Path.of("release");
        List<Path> files;

        try (var paths = Files.list(root)) {
            files = paths
                    .filter(Files::isRegularFile)
                    .filter(path -> !path.getFileName()
                            .toString().equals("SHA256SUMS"))
                    .sorted(Comparator.comparing(
                            path -> path.getFileName().toString()))
                    .toList();
        }

        StringBuilder manifest = new StringBuilder();
        for (Path file : files) {
            String hash = Sha256File.sha256(file);
            manifest.append(hash)
                    .append("  ")
                    .append(file.getFileName())
                    .append('\n');
        }

        Files.writeString(
                root.resolve("SHA256SUMS"),
                manifest.toString(),
                StandardCharsets.UTF_8);
    }
}
```

Ví dụ này giả định class `Sha256File` ở phần trước nằm trong cùng package và được compile cùng project. Nó chỉ xử lý file trực tiếp trong thư mục `release`, không đệ quy qua thư mục con.

Đối với tên file có newline hoặc ký tự đặc biệt, định dạng `hash  filename` đơn giản cần escaping. Trong release automation thực tế, dùng manifest format chuẩn hoặc giới hạn quy tắc tên artifact để tránh ambiguity.

## 15. Kiểm tra checksum của dependency trong Gradle

Gradle Dependency Verification cho phép xác minh checksum hoặc signature của dependency đã resolve. Điều này hữu ích vì dependency cũng là artifact được tải từ repository.

Tạo verification metadata bằng SHA-256:

```sh
./gradlew --write-verification-metadata sha256 help
```

Gradle tạo hoặc cập nhật `gradle/verification-metadata.xml`. Review file này và commit cùng source code. Không tự động tin checksum mới nếu dependency được tải từ nguồn chưa được xác minh.

Có thể đặt verification mode nghiêm ngặt trong `settings.gradle.kts`:

```kotlin
dependencyVerification {
    verificationMode = VerificationMode.STRICT
}
```

Ở chế độ strict, dependency không có metadata phù hợp có thể khiến build fail. Đây là hành vi mong muốn khi tổ chức yêu cầu dependency phải được xác minh trước khi sử dụng.

Khi nâng dependency:

1. Xem dependency mới đến từ repository nào.
2. Xác minh tọa độ, version và nguồn phát hành.
3. Tạo checksum metadata.
4. Review thay đổi trong `verification-metadata.xml`.
5. Chạy build sạch và kiểm tra CI.
6. Commit lock/verification metadata cùng thay đổi dependency.

Dependency verification bảo vệ bước resolve artifact theo metadata đã tin cậy. Nó không thay thế kiểm tra license, vulnerability scan hoặc xác minh toàn bộ build provenance.

## 16. Maven và checksum dependency

Maven tải dependency/plugin từ repository theo tọa độ groupId, artifactId, version và classifier. Repository manager thường cung cấp checksum metadata đi kèm artifact; Maven có thể dùng repository checksum policy để kiểm tra dữ liệu tải về.

Để tăng độ tin cậy:

- Dùng repository manager được tổ chức kiểm soát.
- Không cho phép ghi đè release artifact đã publish.
- Hạn chế hoặc cấm SNAPSHOT trong release build.
- Cố định version plugin và dependency.
- Kiểm tra checksum/signature theo chính sách repository.
- Lưu bản dependency đã được phê duyệt trong repository mirror.
- Ghi lại dependency tree và build metadata.

Checksum `.sha1` hoặc `.md5` do repository cung cấp giúp phát hiện một số lỗi tải xuống nhưng không phải bằng chứng chống giả mạo mạnh. Với yêu cầu bảo mật cao, cần checksum SHA-256 được xác minh qua trust policy hoặc signature/provenance đáng tin cậy.

Không dùng một repository mirror tùy ý làm nguồn duy nhất của digest tham chiếu nếu chính mirror đó nằm trong threat model.

## 17. Checksum của container image và artifact registry

Container image cũng có digest. Registry thường định danh manifest/image bằng content digest như `sha256:<hex>`.

Ví dụ image được tham chiếu bằng digest:

```text
registry.example.com/team/orders-service@sha256:<image-digest>
```

Dùng digest thay tag mutable như `latest` giúp xác định chính xác image manifest được kéo về. Tuy nhiên, digest của image manifest khác checksum của một file JAR nằm bên trong image.

Với Java service đóng gói trong container, có thể kiểm tra cả hai lớp:

- SHA-256 của JAR release.
- Digest của container image được publish.

Nếu image đa kiến trúc, digest có thể trỏ tới image index/manifest list; platform-specific manifest có digest riêng. Xác định rõ digest nào đang được pin và platform nào được triển khai.

Checksum/digest không tự xác minh ai đã publish image. Kết hợp signature verification và registry identity policy khi cần xác thực nguồn gốc.

## 18. Tạo checksum trong CI/CD release pipeline

Một release pipeline có thể thực hiện các bước:

1. Checkout commit đã được review.
2. Dùng JDK, build tool và dependency đã pin.
3. Chạy test và build artifact.
4. Xác định chính xác danh sách file được phát hành.
5. Tính SHA-256 cho từng artifact.
6. Tạo manifest checksum.
7. Ký manifest hoặc artifact theo release policy.
8. Upload artifact, manifest, signature và provenance.
9. Download lại từ repository/registry để xác minh.
10. Chỉ publish/deploy sau khi mọi bước verify thành công.

Ví dụ Linux CI:

```sh
./gradlew --no-daemon clean build

mkdir -p release
cp build/libs/app.jar release/app.jar

cd release
sha256sum app.jar > SHA256SUMS
sha256sum --check SHA256SUMS
```

Nếu cần ký manifest bằng GPG:

```sh
gpg --armor --detach-sign SHA256SUMS
```

Trong production, key ký nên được quản lý bằng secret manager hoặc signing service có kiểm soát quyền. Không commit private key vào repository, không in key/token vào log và không dùng chung key cá nhân của developer cho release automation.

Nếu pipeline tạo checksum rồi upload cả artifact và checksum lên cùng storage, bước verify sau upload vẫn có giá trị để phát hiện lỗi truyền tải. Để xác thực nguồn gốc, verify thêm signature hoặc attestation bằng trust root độc lập.

## 19. So sánh checksum trước và sau khi sao chép

Checksum hữu ích để xác nhận artifact không bị thay đổi khi đi qua nhiều hệ thống:

```sh
sha256sum build/app.jar
sha256sum downloaded/app.jar
sha256sum deployed-copy/app.jar
```

Nếu ba digest giống nhau, ba file có cùng bytes với xác suất va chạm không đáng kể đối với SHA-256. Nếu khác nhau, xác định bước nào làm thay đổi artifact:

- Upload/download không hoàn tất.
- Storage proxy thay đổi hoặc làm hỏng file.
- Pipeline repackage/re-sign JAR.
- Artifact bị thay bởi version khác.
- File được nén lại hoặc sửa manifest.
- Deploy script copy nhầm path.

Không mong checksum giữ nguyên nếu một bước cố ý sửa artifact, ví dụ ký JAR sau khi build. Khi ký JAR, chữ ký và metadata được thêm vào archive, vì vậy checksum trước ký và sau ký khác nhau. Hãy xác định artifact cuối cùng được phát hành và hash đúng file đó.

## 20. Phân biệt checksum file, JAR signature và code signing

Ba cơ chế này giải quyết các câu hỏi khác nhau:

| Cơ chế | Câu hỏi được trả lời |
|---|---|
| SHA-256 checksum | File có giống digest tham chiếu không? |
| JAR signing (`jarsigner`) | Các entry được ký có toàn vẹn và chữ ký có xác minh theo certificate không? |
| Code signing / release signature | Artifact hoặc manifest có được ký bởi identity được tin cậy không? |
| Provenance/attestation | Artifact được tạo từ source, workflow và builder nào? |

Ví dụ kiểm tra chữ ký JAR:

```sh
jarsigner -verify -verbose -certs app-signed.jar
```

`jarsigner -verify` kiểm tra chữ ký entry trong JAR và tính toàn vẹn theo cơ chế JAR signing. Để tin danh tính signer, còn cần kiểm tra certificate chain, trust store, thời hạn, revocation policy và tổ chức phát hành.

Checksum của JAR đã ký vẫn hữu ích để nhận diện chính xác file phát hành. Chữ ký JAR và SHA-256 checksum bổ trợ nhau, không thay thế lẫn nhau.

## 21. Bảo vệ checksum và release metadata

Checksum chỉ đáng tin khi digest tham chiếu được bảo vệ. Một số nguyên tắc:

- Công bố checksum qua HTTPS và release channel được xác thực.
- Ký manifest hoặc artifact bằng private key được bảo vệ.
- Công bố public key/fingerprint qua kênh độc lập.
- Lưu digest trong release metadata hoặc artifact repository có quyền truy cập kiểm soát.
- Không cho phép ghi đè release version đã publish.
- Bảo vệ CI signing secret bằng secret manager hoặc workload identity.
- Hạn chế quyền upload/publish artifact.
- Lưu provenance và log để audit.
- Xác minh signature trước checksum nếu manifest được ký.
- Không đưa private key vào source, container image hoặc artifact.

Nếu người nhận lấy cả file và digest từ cùng một nguồn không đáng tin, checksum không đủ chống tấn công thay thế đồng thời. Cần xác minh signature bằng key/identity đã được tin cậy độc lập.

## 22. Lỗi thường gặp khi tạo và xác minh checksum

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Checksum khác sau khi download | File bị hỏng, download nhầm version hoặc bị thay đổi | Tải lại từ nguồn tin cậy, so sánh version và digest |
| Checksum khác giữa hai máy | Hai artifact được build khác nhau hoặc một file bị sửa | Xác định chính xác bytes và build inputs |
| `sha256sum --check` báo `FAILED` | Digest không khớp hoặc file path không đúng | Kiểm tra sidecar, tên file và nội dung artifact |
| PowerShell so sánh sai | Sidecar có newline, BOM hoặc whitespace | Dùng `Get-Content -Raw`, `Trim()` và chuẩn hóa hex |
| Java báo `NoSuchAlgorithmException` | Provider không có thuật toán yêu cầu | Dùng thuật toán được Java provider hỗ trợ; kiểm tra provider |
| Java báo digest sai dù file đúng | Hash nhầm file, đọc file đã bị thay đổi trong lúc hash hoặc parse digest sai | Hash file bất biến, kiểm tra đường dẫn và định dạng 64 hex |
| Manifest không tìm thấy file | Đường dẫn tương đối hoặc working directory khác | Chạy verify từ thư mục đúng hoặc dùng path rõ ràng |
| Checksum khớp nhưng artifact độc hại | Digest và artifact cùng bị thay thế | Xác minh signature/provenance từ trust root độc lập |
| SHA-1/MD5 được yêu cầu | Hệ thống cũ dùng thuật toán yếu | Duy trì tương thích nếu bắt buộc, bổ sung SHA-256 và kế hoạch nâng cấp |
| Checksum JAR thay đổi sau ký | JAR signature thêm entry/metadata vào archive | Hash artifact cuối cùng sau ký |
| Checksum thay đổi sau khi nén lại | ZIP entry order/timestamp/compression thay đổi | So sánh đúng file artifact; không kỳ vọng archive bytes giống nhau sau repack |
| Hash file lớn tốn RAM | Dùng `Files.readAllBytes()` | Dùng `InputStream` và `MessageDigest.update()` theo buffer |
| Digest có độ dài sai | Copy thiếu ký tự hoặc dùng nhầm thuật toán | Kiểm tra đúng 64 ký tự hex với SHA-256 |
| CI vẫn deploy dù verify fail | Pipeline không kiểm tra exit code | Cho verify step fail job và chặn bước deploy |

## 23. Runbook xác minh một Java artifact

Khi nhận một JAR/WAR/ZIP từ release:

1. Lấy artifact từ repository hoặc release URL đã được phê duyệt.
2. Lấy checksum manifest và signature tương ứng.
3. Xác minh chữ ký manifest bằng public key/identity đã tin cậy.
4. Kiểm tra manifest tham chiếu đúng tên và version artifact.
5. Tính lại SHA-256 của file tải về.
6. So sánh digest với manifest.
7. Nếu không khớp, dừng sử dụng artifact và lưu file/log để điều tra.
8. Nếu khớp, kiểm tra provenance/SBOM và chính sách bảo mật khi yêu cầu.
9. Lưu digest vào release record hoặc deployment metadata.
10. Deploy đúng file đã xác minh; không thay thế file sau bước verify.

Không dùng digest tự tính từ file vừa tải làm digest tham chiếu để “xác minh” chính file đó. Digest tham chiếu phải được lấy từ một nguồn tin cậy độc lập với file cần kiểm tra.

## 24. Checklist

- [ ] Đã hiểu checksum hash trên bytes của file.
- [ ] Đã chọn SHA-256 hoặc thuật toán được chính sách bảo mật phê duyệt.
- [ ] Không dùng MD5/SHA-1 cho xác minh bảo mật mới.
- [ ] Đã phân biệt integrity với authenticity.
- [ ] Đã tạo checksum cho đúng artifact cuối cùng được phát hành.
- [ ] Đã dùng streaming hash cho file lớn.
- [ ] Đã kiểm tra digest có đúng độ dài và định dạng hex.
- [ ] Đã tạo manifest cho release có nhiều artifact.
- [ ] Đã xác minh checksum sau download/copy trước khi deploy.
- [ ] Đã lấy digest tham chiếu từ nguồn tin cậy.
- [ ] Đã ký manifest/artifact nếu cần xác thực nguồn gốc.
- [ ] Đã bảo vệ private signing key và CI credentials.
- [ ] Đã bật Gradle dependency verification khi phù hợp.
- [ ] Đã kiểm tra Maven repository checksum policy và tính bất biến của release.
- [ ] Đã phân biệt JAR signature, checksum và provenance.
- [ ] Đã lưu digest trong release/deployment metadata.
- [ ] Đã bảo đảm pipeline dừng khi checksum verification thất bại.

## 25. Tài liệu tham khảo

- Java SE 17 API — MessageDigest: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Java SE 17 API — HexFormat: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- Gradle User Manual — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- GNU Coreutils — sha2 utilities: https://www.gnu.org/software/coreutils/manual/html_node/sha2-utilities.html
- Microsoft Learn — Get-FileHash: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/get-filehash
- Oracle JDK Tool — jarsigner: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Sigstore Documentation: https://docs.sigstore.dev/
- SLSA — Supply-chain Levels for Software Artifacts: https://slsa.dev/

Checksum là bước kiểm tra đơn giản nhưng quan trọng trong quản lý artifact. Hãy hash đúng file cuối cùng, dùng SHA-256, xác minh bằng digest lấy từ nguồn tin cậy và chặn deploy khi không khớp. Khi cần chứng minh nguồn gốc, ký manifest hoặc artifact và xác minh signer theo trust policy; checksum, chữ ký và provenance cùng tạo nên quy trình phát hành có thể kiểm tra và audit.