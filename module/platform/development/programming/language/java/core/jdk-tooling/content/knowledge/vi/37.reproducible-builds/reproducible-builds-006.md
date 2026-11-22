# Kiểm tra checksum cho artifact Java

Checksum là giá trị băm được tính từ toàn bộ byte của một file. Trong quy trình build và release Java, checksum giúp xác nhận artifact nhận được có đúng từng byte với artifact đã được tạo hoặc công bố hay không.

Với artifact như JAR, WAR, ZIP hoặc file phân phối, quy trình thường là:

1. Build artifact từ source và dependency đã được xác định.
2. Tính SHA-256 của artifact.
3. Lưu checksum cùng release metadata hoặc manifest.
4. Khi tải, copy hoặc triển khai artifact, tính lại SHA-256.
5. So sánh digest thực tế với digest kỳ vọng và làm CI thất bại nếu khác nhau.

Trong reproducible build, checksum còn giúp so sánh kết quả từ hai lần build độc lập. Nếu cùng source, toolchain và điều kiện build tạo ra byte-for-byte identical artifact, SHA-256 của hai file phải giống nhau.

## 1. Checksum là gì?

Checksum là một giá trị đại diện được tính từ nội dung file bằng một thuật toán. Với cryptographic hash như SHA-256, input có độ dài bất kỳ tạo ra digest cố định 256 bit, thường biểu diễn bằng 64 ký tự hexadecimal.

Ví dụ, nội dung file gồm đúng ba byte ASCII:

~~~text
abc
~~~

Có SHA-256:

~~~text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Chỉ cần thay đổi một byte, digest gần như chắc chắn sẽ khác hoàn toàn. Vì vậy checksum rất hữu ích để phát hiện file bị hỏng, bị thay thế hoặc không khớp với artifact đã công bố.

### Checksum xác nhận điều gì?

- File có đúng nội dung byte mà checksum kỳ vọng mô tả hay không.
- Hai artifact có giống nhau từng byte hay không.
- File tải về có bị lỗi trong quá trình truyền hoặc lưu trữ hay không.
- Hai lần build có tạo ra cùng một artifact hay không.

### Checksum không xác nhận điều gì?

Checksum không tự chứng minh ai đã tạo file. Nếu attacker thay cả artifact và file checksum được tải từ cùng một nguồn không đáng tin, hai file vẫn có thể khớp.

Muốn xác thực nguồn gốc, cần lấy checksum qua một kênh tin cậy hoặc xác minh chữ ký số/provenance. Checksum và chữ ký số giải quyết hai câu hỏi khác nhau:

- Checksum: nội dung file có khớp digest kỳ vọng không?
- Chữ ký số: digest hoặc metadata có được ký bởi một identity tin cậy không?

## 2. Chọn thuật toán hash

Các thuật toán thường gặp:

| Thuật toán | Độ dài digest | Khuyến nghị |
|---|---:|---|
| MD5 | 128 bit | Không dùng cho kiểm tra integrity có yêu cầu chống giả mạo |
| SHA-1 | 160 bit | Tránh dùng cho mục đích bảo mật |
| SHA-256 | 256 bit | Lựa chọn phổ biến cho artifact verification |
| SHA-384 | 384 bit | Có thể dùng khi policy yêu cầu |
| SHA-512 | 512 bit | Phù hợp khi hệ thống đã chuẩn hóa thuật toán này |

Với CI của ứng dụng Java, SHA-256 thường là lựa chọn đơn giản và được hỗ trợ rộng rãi bởi JDK, Linux, macOS và Windows.

Không nên dùng MD5 hoặc SHA-1 để xác minh artifact trong quy trình phát hành có yêu cầu bảo mật. Nếu một hệ thống cũ bắt buộc dùng chúng để phát hiện lỗi truyền tải, hãy giữ SHA-256 làm digest kiểm tra chính.

## 3. Tạo checksum trên Linux

GNU coreutils cung cấp lệnh sha256sum.

Tính hash cho một file:

~~~bash
sha256sum build/libs/application.jar
~~~

Tạo manifest:

~~~bash
sha256sum build/libs/application.jar > SHA256SUMS
~~~

Nội dung manifest có dạng:

~~~text
<sha256-digest>  build/libs/application.jar
~~~

Kiểm tra file theo manifest:

~~~bash
sha256sum --check SHA256SUMS
~~~

Khi đúng, output có dạng:

~~~text
build/libs/application.jar: OK
~~~

Khi file thay đổi hoặc digest không khớp, lệnh trả exit code khác 0. CI có thể dùng trực tiếp exit code này để dừng pipeline.

### Kiểm tra nhiều artifact

~~~bash
sha256sum build/libs/*.jar > SHA256SUMS
sha256sum --check SHA256SUMS
~~~

Manifest chứa một dòng cho mỗi JAR. Nếu có file không tồn tại hoặc nội dung khác digest, bước kiểm tra thất bại.

Hãy chạy lệnh kiểm tra từ thư mục mà các đường dẫn trong manifest có thể được resolve. Nếu tạo manifest với đường dẫn tương đối, cần giữ đúng working directory khi xác minh.

## 4. Tạo checksum trên macOS

macOS thường có lệnh shasum:

~~~bash
shasum -a 256 build/libs/application.jar
~~~

Tạo manifest:

~~~bash
shasum -a 256 build/libs/application.jar > SHA256SUMS
~~~

Kiểm tra:

~~~bash
shasum -a 256 -c SHA256SUMS
~~~

Output khi đúng có dạng:

~~~text
build/libs/application.jar: OK
~~~

Không nhầm shasum -a 256 với SHA-1 mặc định của một số lệnh shasum cũ. Luôn ghi rõ thuật toán 256.

## 5. Tạo checksum trên Windows

PowerShell có sẵn Get-FileHash:

~~~powershell
Get-FileHash -LiteralPath '.\build\libs\application.jar' -Algorithm SHA256
~~~

Kết quả gồm:

- Algorithm: SHA256.
- Hash: digest hexadecimal.
- Path: đường dẫn file.

Có thể dùng certutil khi cần kiểm tra thủ công:

~~~powershell
certutil -hashfile .\build\libs\application.jar SHA256
~~~

### Script PowerShell tạo và xác minh checksum

Script sau ghi digest vào file sidecar. Khi chạy ở bước publish, nó tạo checksum. Khi chạy ở bước verify, nó đọc digest đã được cung cấp từ nguồn tin cậy và so sánh với artifact hiện tại.

~~~powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$Artifact,

    [Parameter(Mandatory = $true)]
    [string]$ChecksumFile
)

if (-not (Test-Path -LiteralPath $Artifact -PathType Leaf)) {
    Write-Error "Artifact not found: $Artifact"
    exit 2
}

$actual = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()

if (-not (Test-Path -LiteralPath $ChecksumFile -PathType Leaf)) {
    $actual | Set-Content -LiteralPath $ChecksumFile -Encoding ascii -NoNewline
    Write-Output "Checksum manifest created: $ChecksumFile"
    exit 0
}

$expected = (Get-Content -LiteralPath $ChecksumFile -Raw).Trim().ToLowerInvariant()

if ($expected -notmatch '^[0-9a-f]{64}$') {
    Write-Error "Invalid SHA-256 checksum file."
    exit 2
}

if (-not [string]::Equals(
    $actual,
    $expected,
    [System.StringComparison]::Ordinal
)) {
    Write-Error "Checksum mismatch for $Artifact"
    exit 1
}

Write-Output "SHA-256: $actual"
Write-Output "Checksum OK"
exit 0
~~~

Trong pipeline thật, nên tách bước tạo checksum và bước verify. Nếu sidecar chưa tồn tại, script trên tạo file; nếu sidecar đã tồn tại, nó xác minh. Không dùng việc tạo sidecar từ chính artifact vừa tải làm bằng chứng xác thực artifact đó.

Nếu cần manifest chứa nhiều artifact, có thể lưu JSON hoặc CSV gồm đường dẫn, thuật toán và digest, rồi xác minh từng dòng trong script CI.

## 6. Ví dụ Java 17+: tính SHA-256 bằng MessageDigest

JDK cung cấp MessageDigest trong package java.security. Có thể dùng API này khi ứng dụng cần xác minh file trước khi import, triển khai hoặc xử lý.

Với file lớn, nên đọc theo buffer thay vì dùng Files.readAllBytes, vì cách đọc toàn bộ file có thể tiêu thụ nhiều heap.

### ChecksumVerifier.java

~~~java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ChecksumVerifier {
    private ChecksumVerifier() {
    }

    public static void main(String[] args) {
        if (args.length != 2 || !args[1].matches("(?i)[0-9a-f]{64}")) {
            System.err.println(
                    "Usage: ChecksumVerifier <file> <expected-sha256-hex>");
            System.exit(2);
            return;
        }

        try {
            byte[] expected = HexFormat.of().parseHex(args[1]);
            byte[] actual = sha256(Path.of(args[0]));

            System.out.println(
                    "SHA-256: " + HexFormat.of().formatHex(actual));

            if (MessageDigest.isEqual(actual, expected)) {
                System.out.println("Checksum OK");
            } else {
                System.out.println("Checksum MISMATCH");
                System.exit(1);
            }
        } catch (IOException | NoSuchAlgorithmException
                | IllegalArgumentException ex) {
            System.err.println(
                    "Checksum verification failed: " + ex.getMessage());
            System.exit(2);
        }
    }

    private static byte[] sha256(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return digest.digest();
    }
}
~~~

Giải thích:

- MessageDigest.getInstance("SHA-256") tạo bộ tính digest.
- Files.newInputStream mở file để đọc tuần tự.
- Buffer 8192 byte tránh phải nạp toàn bộ file vào RAM.
- digest.update(buffer, 0, count) cập nhật hash cho từng phần đã đọc.
- digest.digest() trả về 32 byte của SHA-256.
- HexFormat chuyển digest sang chuỗi hexadecimal.
- MessageDigest.isEqual so sánh hai mảng byte.
- Exit code 0 nghĩa checksum khớp, 1 nghĩa digest không khớp, 2 nghĩa input hoặc thao tác đọc không hợp lệ.

HexFormat có từ Java 17. Nếu project hỗ trợ Java thấp hơn, có thể chuyển byte array sang hexadecimal bằng một helper riêng hoặc thư viện đã được phê duyệt.

## 7. Chạy Java verifier với known test vector

Tạo file chứa đúng ba byte ASCII abc. Không thêm BOM, newline hoặc khoảng trắng vì bất kỳ byte bổ sung nào cũng làm digest thay đổi.

Digest SHA-256 kỳ vọng:

~~~text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Biên dịch:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/ChecksumVerifier.java
~~~

Chạy với digest đúng:

~~~bash
java -cp build/classes com.example.ChecksumVerifier artifact.txt ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

Output:

~~~text
SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
Checksum OK
~~~

Chạy với digest sai:

~~~bash
java -cp build/classes com.example.ChecksumVerifier artifact.txt 0000000000000000000000000000000000000000000000000000000000000000
~~~

Output:

~~~text
SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
Checksum MISMATCH
~~~

Lần chạy thứ hai trả exit code 1. Digest sai không được xem là cảnh báo có thể bỏ qua trong CI.

Nếu truyền checksum không đủ 64 ký tự hexadecimal, chương trình in usage và trả exit code 2.

## 8. Kiểm tra hai lần build có reproducible không

Checksum là cách nhanh để so sánh output của hai lần build độc lập.

Quy trình:

1. Checkout cùng một commit.
2. Build trong hai workspace sạch.
3. Dùng cùng JDK/toolchain, dependency và build configuration.
4. Tính SHA-256 của artifact ở mỗi workspace.
5. So sánh hai digest.
6. Nếu khác, điều tra những byte khác nhau trước khi kết luận build chưa reproducible.

Ví dụ trên Linux:

~~~bash
sha256sum build-a/application.jar
sha256sum build-b/application.jar
~~~

Có thể so sánh trực tiếp:

~~~bash
cmp build-a/application.jar build-b/application.jar
~~~

cmp trả exit code 0 khi hai file giống từng byte và khác 0 khi có khác biệt.

Trên Windows:

~~~powershell
Get-FileHash .\build-a\application.jar -Algorithm SHA256
Get-FileHash .\build-b\application.jar -Algorithm SHA256

fc.exe /b .\build-a\application.jar .\build-b\application.jar
~~~

Nếu hai digest giống nhau, hai artifact có cùng byte content với độ tin cậy thực tế rất cao. Nếu khác, checksum chỉ cho biết chúng khác nhau; cần công cụ diff để tìm nguyên nhân.

### Vì sao cùng source vẫn có thể tạo checksum khác?

Một số nguyên nhân phổ biến:

- Timestamp của file trong ZIP/JAR thay đổi.
- Thứ tự entry trong archive không ổn định.
- Build nhúng thời gian hiện tại vào manifest hoặc generated resource.
- Generated file chứa absolute path của workspace.
- Build number hoặc random identifier thay đổi.
- Locale, timezone hoặc line ending khác nhau.
- JDK, compiler, plugin hoặc dependency version khác nhau.
- Dependency được resolve từ repository thay đổi theo thời gian.
- File permission hoặc metadata archive khác nhau.
- Artifact bị ký ở các thời điểm khác nhau.

Nếu checksum khác, không nên vội kết luận source code khác. Hãy giải nén hai archive, so sánh entry, timestamp, metadata và generated file.

Có thể dùng diffoscope hoặc unzip/zipinfo để điều tra archive. Hash là bước phát hiện khác biệt; diff là bước tìm nguyên nhân.

## 9. Cấu hình build để tạo archive ổn định

Checksum chỉ giúp xác minh reproducibility sau khi build đã tạo output. Muốn hai lần build tạo cùng digest, cần loại bỏ các yếu tố không xác định.

### Maven

Các phiên bản Maven archive plugin hỗ trợ output timestamp có thể dùng property:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Giá trị phải ổn định giữa các lần build của cùng source revision. Trong dự án thực tế, có thể derive từ commit timestamp đã được chuẩn hóa thay vì dùng thời gian hiện tại.

Cần bảo đảm phiên bản plugin đóng gói hỗ trợ property này. Một property trong POM không tự làm mọi plugin hoặc generated resource trở nên deterministic.

### Gradle

Với archive task, có thể tắt việc giữ timestamp gốc của file và bật thứ tự entry reproducible.

Groovy DSL:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Kotlin DSL:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Các thiết lập này giúp ổn định metadata archive. Chúng không giải quyết mọi nguồn nondeterminism trong code generation, dependency resolution hoặc build environment.

### Chuẩn hóa môi trường build

Để so sánh có ý nghĩa, hãy cố định:

- JDK vendor và version.
- Build tool và plugin version.
- Dependency versions và repository content.
- Locale và timezone.
- Environment variables ảnh hưởng build.
- Source revision và generated inputs.
- File encoding và line endings.
- Các timestamp được nhúng vào artifact.

Có thể dùng container hoặc build image đã pin digest để giảm khác biệt môi trường. Vẫn cần so sánh output thực tế bằng checksum.

## 10. Tạo checksum manifest cho release

Sau khi build và package xong, tạo manifest cho đúng artifact sẽ được publish.

Ví dụ:

~~~bash
sha256sum application.jar application-sources.jar > SHA256SUMS
~~~

Publish cùng:

~~~text
application.jar
application-sources.jar
SHA256SUMS
~~~

Ở phía tải về:

~~~bash
sha256sum --check SHA256SUMS
~~~

Nếu release chứa nhiều file, manifest giúp xác minh tất cả artifact theo một danh sách. Không chỉnh sửa hoặc đóng gói lại artifact sau khi tạo manifest; nếu bytes thay đổi, phải tạo digest mới.

### Thời điểm tính checksum

Tính checksum sau khi artifact đã hoàn tất mọi bước biến đổi:

1. Compile.
2. Package.
3. Repackage hoặc shading nếu có.
4. Ký JAR nếu quy trình yêu cầu.
5. Tính checksum của file cuối cùng.
6. Publish artifact và checksum manifest.

Nếu tính checksum trước khi ký JAR, chữ ký sẽ làm thay đổi file và digest cũ không còn đúng với artifact được phát hành.

## 11. Tích hợp kiểm tra checksum vào CI

### GitHub Actions

Ví dụ workflow xác minh manifest đã được tạo hoặc tải từ release metadata đáng tin cậy:

~~~yaml
- name: Verify artifact checksums
  shell: bash
  run: sha256sum --check SHA256SUMS
~~~

Nếu workflow tạo artifact trong job trước, có thể tạo manifest:

~~~yaml
- name: Generate SHA-256 manifest
  shell: bash
  run: sha256sum build/libs/*.jar > SHA256SUMS
~~~

Job tiêu thụ artifact cần tải cả file và manifest, rồi chạy bước verify.

### GitLab CI

~~~yaml
stages:
  - build
  - verify

build:
  stage: build
  script:
    - ./gradlew clean build
    - sha256sum build/libs/*.jar > SHA256SUMS
  artifacts:
    paths:
      - build/libs/
      - SHA256SUMS

verify:
  stage: verify
  script:
    - sha256sum --check SHA256SUMS
~~~

### Jenkins Pipeline

~~~groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh './gradlew clean build'
                sh 'sha256sum build/libs/*.jar > SHA256SUMS'
            }
        }

        stage('Verify checksum') {
            steps {
                sh 'sha256sum --check SHA256SUMS'
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'SHA256SUMS',
                             allowEmptyArchive: true
        }
    }
}
~~~

Các ví dụ Bash giả định runner có sha256sum. Với Windows runner, dùng PowerShell Get-FileHash và script so sánh digest.

### Quy tắc cho CI gate

- Thiếu artifact: fail.
- Thiếu manifest khi cần verify: fail.
- Digest không đúng định dạng: fail.
- Digest khác nhau: fail.
- Thuật toán không đúng policy: fail.
- Không đọc được file hoặc manifest: fail.
- Chỉ pass khi toàn bộ file được xác minh thành công.

Không dùng điều kiện "command có output" để xác định pass. Hãy dựa trên exit code và kết quả so sánh digest.

## 12. Checksum và chữ ký số

Checksum không phải chữ ký số. Nếu manifest nằm cạnh artifact trên cùng một nguồn tải không đáng tin, attacker có thể thay cả hai.

Để xác thực nguồn gốc:

- Lấy checksum từ release metadata được ký.
- Xác minh chữ ký của manifest hoặc artifact.
- Dùng hệ thống provenance/attestation để xác nhận build identity và source revision.
- Bảo vệ quyền publish và quyền thay đổi release metadata.

Với JAR đã ký, có thể kiểm tra chữ ký:

~~~bash
jarsigner -verify -strict -verbose -certs application.jar
~~~

Lệnh này kiểm tra chữ ký JAR và certificate theo policy của jarsigner. Nó trả lời câu hỏi khác với SHA-256. Có thể dùng cả hai bước: xác minh digest để kiểm tra byte content theo manifest và xác minh chữ ký để kiểm tra chữ ký/certificate.

Không coi checksum lấy từ cùng một mirror bị nghi ngờ là bằng chứng độc lập về tính xác thực.

## 13. Lỗi thường gặp khi kiểm tra checksum

### Hash khác nhau dù file nhìn giống nhau

Hash tính trên byte, không tính trên nội dung hiển thị. Khác newline, encoding, BOM, whitespace, archive timestamp hoặc metadata đều làm digest khác.

### Tính checksum trước khi build hoàn tất

Nếu artifact còn bị repack, ký hoặc sửa metadata, digest cũ sẽ không còn khớp. Tính hash sau bước biến đổi cuối cùng.

### Dùng sai file hoặc sai đường dẫn

Manifest có thể trỏ tới artifact khác cùng tên. Kiểm tra working directory, path và tên artifact được publish.

### Dùng sai thuật toán

Manifest SHA-256 phải được xác minh bằng SHA-256. Không so digest MD5 hoặc SHA-1 với giá trị SHA-256.

### Chỉ so sánh checksum do cùng một nguồn không tin cậy cung cấp

Attacker có thể thay cả file và digest. Lấy expected checksum từ kênh tin cậy hoặc xác minh chữ ký.

### Dùng Files.readAllBytes cho file lớn

Cách này nạp toàn bộ file vào heap. Dùng InputStream và MessageDigest.update theo buffer để xử lý file lớn.

### Tạo test vector có thêm newline hoặc BOM

File chứa abc và file chứa abc kèm newline là hai input khác nhau. Khi kiểm thử known vector, phải kiểm soát chính xác byte được ghi.

### So sánh checksum của artifact đã ký với artifact chưa ký

Chữ ký thay đổi byte của JAR. Tính checksum sau khi hoàn tất ký và verify trên đúng artifact được phân phối.

### Coi checksum giống reproducible build

Checksum chỉ so sánh file. Reproducible build còn yêu cầu build độc lập từ cùng source/configuration tạo ra byte-identical output.

## 14. Quy trình kiểm tra checksum trong dự án Java

1. Chọn SHA-256 làm thuật toán thống nhất.
2. Xác định chính xác artifact cần bảo vệ: JAR, WAR, ZIP hoặc distribution.
3. Hoàn tất compile, package, repackage và signing.
4. Tạo manifest chứa digest của artifact cuối cùng.
5. Publish artifact và manifest theo quy trình release.
6. Ở consumer/CI, lấy expected digest từ nguồn tin cậy.
7. Tính lại SHA-256 của artifact nhận được.
8. So sánh digest và fail nếu khác.
9. Nếu kiểm tra reproducible build, build cùng commit trong workspace độc lập.
10. So sánh checksum của hai artifact và điều tra nếu khác.
11. Lưu manifest, log và build provenance làm bằng chứng.
12. Định kỳ xác minh toolchain và policy checksum.

## 15. Checklist trước khi publish

- [ ] Dùng SHA-256 hoặc thuật toán mạnh hơn theo policy.
- [ ] Đã build xong và artifact không còn bị chỉnh sửa.
- [ ] Đã tính checksum của đúng file sẽ publish.
- [ ] Manifest ghi đúng tên và đường dẫn artifact.
- [ ] Có bước verify ở phía consumer hoặc CI.
- [ ] CI fail khi checksum sai hoặc manifest thiếu.
- [ ] Known test vector đã được kiểm tra.
- [ ] File lớn được xử lý theo streaming.
- [ ] Với reproducible build, đã so sánh output của hai build độc lập.
- [ ] Timestamp và archive entry order đã được chuẩn hóa.
- [ ] Expected checksum lấy từ nguồn tin cậy.
- [ ] Chữ ký/provenance được xác minh khi cần xác thực nguồn gốc.

## 16. Lệnh cần nhớ

~~~bash
# Linux: calculate SHA-256
sha256sum build/libs/application.jar

# Linux: create and verify manifest
sha256sum build/libs/application.jar > SHA256SUMS
sha256sum --check SHA256SUMS

# macOS: calculate and verify SHA-256
shasum -a 256 build/libs/application.jar
shasum -a 256 build/libs/application.jar > SHA256SUMS
shasum -a 256 -c SHA256SUMS

# Compare two independent build outputs
sha256sum build-a/application.jar build-b/application.jar
cmp build-a/application.jar build-b/application.jar

# Windows PowerShell
Get-FileHash -LiteralPath .\build\libs\application.jar -Algorithm SHA256

# Windows command-line alternative
certutil -hashfile .\build\libs\application.jar SHA256

# Compile the Java 17 verifier
javac --release 17 -d build/classes src/com/example/ChecksumVerifier.java

# Verify an artifact using Java
java -cp build/classes com.example.ChecksumVerifier application.jar <expected-sha256-hex>

# Verify a signed JAR separately
jarsigner -verify -strict -verbose -certs application.jar
~~~

Checksum là bước kiểm tra byte content đơn giản nhưng rất quan trọng trong build và release. Dùng SHA-256, tạo manifest sau khi artifact hoàn tất, xác minh bằng exit code trong CI và lấy expected digest từ nguồn tin cậy. Khi kiểm tra reproducible build, hãy build độc lập từ cùng source revision rồi so sánh checksum; nếu khác, điều tra metadata và môi trường build thay vì chỉ đổi digest kỳ vọng.

## Tài liệu tham khảo

- [MessageDigest — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
- [HexFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html)
- [Get-FileHash — Microsoft PowerShell](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/get-filehash)
- [sha256sum — GNU Coreutils](https://www.gnu.org/software/coreutils/manual/html_node/sha2-utilities.html)
- [JAR Tool — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [jarsigner Tool — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Reproducible Builds](https://reproducible-builds.org/)
