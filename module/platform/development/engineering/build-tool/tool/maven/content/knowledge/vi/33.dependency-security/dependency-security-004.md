# Kiểm tra checksum và ý nghĩa khác nhau của toàn vẹn với xác thực trong Maven

## 1. Tình huống mở đầu

Một dự án Java khai báo dependency Maven và tải JAR từ repository. Maven so checksum của file vừa nhận với checksum mà repository cung cấp, thấy trùng nhau và tiếp tục build. Vậy có thể kết luận dependency ấy an toàn, do đúng maintainer phát hành và chưa bị tấn công không?

**Không.** Kết quả checksum khớp, trong phạm vi phép kiểm đang dùng, chỉ cho thấy **bytes nhận được khớp giá trị checksum kỳ vọng**. Nếu cả artifact lẫn checksum đều đến từ một nguồn có thể bị sửa, người kiểm chưa chứng minh được danh tính hoặc tính hợp pháp của nguồn phát hành.

Hãy phân biệt ba câu hỏi:

1. **Integrity — Tính toàn vẹn:** Bytes hiện tại có khớp bản tham chiếu không?
2. **Authenticity — Tính xác thực:** Bản tham chiếu/bytes thực sự đến từ nguồn hoặc người ký được chấp nhận không?
3. **Security/quality — An toàn và chất lượng:** Artifact chính chủ đó có chứa CVE, mã nguy hiểm, lỗi logic hoặc vi phạm license/policy không?

Một phép băm SHA-256 có thể hỗ trợ câu hỏi thứ nhất, nhưng không tự trả lời câu hỏi thứ hai và thứ ba. Một chữ ký số kèm public key đã được xác minh có thể cung cấp bằng chứng mạnh hơn về nguồn ký, nhưng ngay cả chữ ký hợp lệ cũng **không tự chứng minh code không có lỗi bảo mật**.

Bài này nằm trong nhóm **An toàn phụ thuộc — Build Tool Maven**, tập trung vào **checksum của Maven artifacts, expected checksums, chính sách Resolver, trusted checksums và chữ ký số**. Ví dụ dùng **Maven 3.9.x, Java 17+, JUnit 5** với một project chạy được để người học tự kiểm thử thay đổi một byte.

### Mục tiêu học tập

Sau bài này, bạn sẽ:
- Hiểu checksum/hash hoạt động ở mức bytes, không phải ở mức tên file.
- Phân biệt tính toàn vẹn, xác thực, provenance và security scanning.
- Đọc đường dẫn `.sha1`/`.md5`/`.sha256` cạnh artifact và hiểu SHA-256 của dữ liệu demo.
- Hiểu `checksumPolicy` có các chế độ `fail`, `warn`, `ignore`; biết Maven CLI `-C` và `-c`.
- Phân biệt remote checksum ở repository với trusted checksum nhận từ kênh khác.
- Hiểu vì sao **SHA-1/MD5** còn xuất hiện ở Maven repositories nhưng không đủ là bằng chứng mật mã chống đối thủ chủ động.
- Biết cơ chế `.asc`, chữ ký GPG và việc xác thực public key fingerprint.
- Tự viết chương trình Java 17 xác minh SHA-256, có unit tests và mã thoát khi mismatch.
- Chẩn đoán checksum mismatch, cache hỏng, mirror sai, SNAPSHOT hoặc artifact bị ghi đè.
- Tổ chức một CI quality gate kết hợp checksum, source identity và phân tích lỗ hổng.

## 2. Checksum, hash và kiểm tra tính toàn vẹn

### 2.1. Cơ chế checksum

Một hàm hash nhận bytes, tạo digest:

```text
artifact.jar bytes ------ hash algorithm ------> calculated digest
                                                    |
                                                    v
                                        compare with expected digest
                                                    |
                                             MATCH / MISMATCH
```

Đối với SHA-256, digest dài **256 bit**, thường hiển thị thành **64 ký tự hex**. Nếu hai files có cùng bytes, SHA-256 của chúng bằng nhau. Nếu một byte bị thay đổi, digest thường thay đổi rất mạnh (hiệu ứng avalanche).

**Cẩn thận:**
- Tên file giống nhau không có nghĩa bytes giống nhau.
- Checksum không mang thông tin **ai tạo file**, **ai phê duyệt file** hoặc **file được tải từ repo nào**.
- Hash không kiểm thử mã Java, không chạy unit tests và không quét CVE.
- Nếu expected digest đến từ một nguồn không đáng tin, kết quả MATCH không chứng minh an toàn nguồn gốc.

### 2.2. Expected checksum và calculated checksum

Maven Artifact Resolver sử dụng hai giá trị:
- **Calculated checksum:** Maven tính từ các bytes đã tải hoặc bytes file được mở lại khi có cơ chế post-processing.
- **Expected checksum:** Maven lấy từ repository, HTTP header, file checksum sidecar hoặc một nguồn expected checksum được cung cấp riêng.

So sánh hai giá trị làm phát hiện lỗi truyền tải/tamper **khi expected checksum vẫn là một mốc đáng tin trong mô hình đe dọa đã đặt ra**. Nếu người tấn công thay đổi được cả mốc đó, phép so khớp không đủ.

### 2.3. Bảng phân biệt tính toàn vẹn và xác thực

| Phương pháp | Xác minh được | Chưa tự xác minh được |
| --- | --- | --- |
| SHA-256(file) so với digest tự tính trước | Bytes khớp một digest | Digest có được duyệt độc lập không |
| File `.sha1` tải cùng repository | Bytes khớp checksum từ repository | Repository/publisher có đáng tin không |
| Expected digest được cấp bởi security team qua kênh độc lập | Bytes khớp bản đã được phê duyệt | Tên người ký nếu manifest không có danh tính |
| `gpg --verify` với public key đã xác thực | Người nắm private key tương ứng đã ký nội dung đó | Code không có CVE hoặc maintainer không bị compromise |
| HTTPS/TLS | Kết nối đến host xác thực được và được bảo vệ khi truyền | Artifact ở server là artifact đúng maintainer |
| SCA/SBOM/license scan | Các thuộc tính rủi ro/pháp lý được công cụ phân tích | Bytes mới tải khớp bản được review nếu không có pin/hash |

Vì vậy **integrity, authenticity và security** là ba lớp bổ sung, không phải ba tên khác nhau của cùng một chức năng.

### 2.4. Minh họa actor thay cả artifact lẫn checksum

Trạng thái bình thường:

```text
my-lib-1.2.0.jar      : original bytes
my-lib-1.2.0.jar.sha1 : SHA-1(original bytes)
```

Nếu một actor có quyền ghi repository thay JAR và checksum cùng lúc:

```text
my-lib-1.2.0.jar      : modified bytes
my-lib-1.2.0.jar.sha1 : SHA-1(modified bytes)
```

Khi Maven tính checksum từ modified bytes rồi so với sidecar đã được thay, **hai giá trị vẫn trùng**. Actor không cần phá SHA-1 bằng collision attack; họ chỉ cần quyền sửa **reference digest**. Kịch bản này giải thích tại sao một checksum mạnh hơn không tự khắc phục việc thiếu gốc tin cậy.

## 3. SHA-1, MD5, SHA-256 và SHA-512 trong hệ sinh thái Maven

### 3.1. Vì sao Maven repositories vẫn có .sha1 và .md5?

Trong repository theo layout Maven, ta thường thấy:

```text
org/example/my-lib/1.2.0/
    my-lib-1.2.0.pom
    my-lib-1.2.0.jar
    my-lib-1.2.0.jar.sha1
    my-lib-1.2.0.jar.md5
    my-lib-1.2.0.pom.sha1
    my-lib-1.2.0.pom.md5
```

Đây là **minh họa**; không phải mọi repository đều cung cấp đủ từng file. Repository manager có thể gửi checksum qua HTTP response headers và Resolver không cần request file `.sha1` riêng.

Maven Resolver tài liệu hóa checksum truyền thống như một lớp **transport integrity**: phát hiện lỗi data trên đường truyền/lưu trữ, không dùng làm phương thức xác thực nhà phát hành. Vì vậy bạn vẫn thấy SHA-1/MD5 trong hệ sinh thái cũ.

### 3.2. Đặc tính thuật toán

| Thuật toán | Digest size | Khuyến nghị cho bài toán |
| --- | ---: | --- |
| MD5 | 128 bit | Chỉ legacy transport/error detection; không làm proof chống tamper |
| SHA-1 | 160 bit | Legacy Maven checksum; không coi là collision-resistant đủ cho nhiều use case bảo mật |
| SHA-256 | 256 bit | Phù hợp làm trusted content digest khi reference được bảo vệ |
| SHA-512 | 512 bit | Cũng phù hợp làm trusted content digest khi reference được bảo vệ |

MD5/SHA-1 có vấn đề đã biết về collision resistance. Dù vậy, **bản chất không đáng tin của checksum đi cùng file không chỉ do yếu thuật toán**: ngay cả SHA-256 cũng có thể bị actor cập nhật hợp lệ theo bytes giả nếu cả hai nguồn đều bị kiểm soát.

### 3.3. Central repository và publisher policy

Theo hướng dẫn Sonatype Central hiện hành, files triển khai có `.md5` và `.sha1` checksum theo yêu cầu xuất bản, còn `.sha256`/`.sha512` được hỗ trợ. Một số công cụ publisher tạo nhiều checksum algorithms mặc định.

**Không suy ra có `.sha256` nghĩa là phát hành đã được xác thực.** Sonatype còn yêu cầu metadata/chữ ký theo quy trình publish. Độc lập với checksums, Maven Central có chính sách **release immutability**: artifact đã public không được thay bằng bytes mới cùng version.

## 4. Maven Resolver lấy expected checksums ở đâu?

### 4.1. Remote External

Repository đặt checksum ngay bên artifact, ví dụ:

```text
https://repo.maven.apache.org/maven2/.../library-1.2.0.jar
https://repo.maven.apache.org/maven2/.../library-1.2.0.jar.sha1
```

Resolver có thể GET checksum file riêng. Đây là kiểu **remote external**.

### 4.2. Remote Included

Một repository manager có thể gửi checksum trong HTTP headers của response chứa artifact, ví dụ `x-checksum-sha1` hoặc `x-checksum-md5`. Đây là kiểu **remote included**. Không cần có một request HTTP độc lập tới `.sha1` file.

**Cả Remote External và Remote Included đều dựa vào cùng nguồn remote**. Chúng không tự giải quyết trường hợp repository đã bị chiếm quyền.

### 4.3. Provided

Maven Resolver hỗ trợ **provided checksums** qua API/extension, cho phép một caller hoặc trusted checksum provider cấp expected digest độc lập. Resolver mới có `TrustedChecksumsSource` và post-processing để kiểm lại artifacts, kể cả khi không có transport request.

Đây là cơ chế **phụ thuộc phiên bản Resolver và cấu hình thực tế**. Đừng mặc định một dự án Maven 3.9 tự bật trusted checksums chỉ vì có file `sha256sum.txt` trong repository.

### 4.4. Metadata cũng có vai trò

Maven Resolver không chỉ tải JAR mà còn tải POM, `maven-metadata.xml`, plugin metadata, snapshot metadata và các file liên quan. Lỗi checksum ở **POM hoặc metadata** có thể làm dependency resolution thất bại trước cả khi Java compiler được gọi.

Khi debug, ghi lại:
- GAV, extension/classifier;
- URL/repository ID đã thực sự dùng;
- file cụ thể JAR, POM hay metadata;
- checksum algorithm;
- Maven và Resolver versions;
- policy được áp dụng.

Đừng mở ngay JAR rồi kết luận nó hỏng nếu log đang nói về `maven-metadata.xml`.

## 5. checksumPolicy: fail, warn, ignore

### 5.1. Ba mức phản ứng

`checksumPolicy` là chính sách repository khi checksum bị thiếu hoặc không khớp:

| Giá trị | Hành vi mong đợi |
| --- | --- |
| `fail` | Chặn resolution/build khi điều kiện checksum không đạt |
| `warn` | Báo cảnh báo; build có thể tiếp tục |
| `ignore` | Bỏ qua hiện diện/xác minh checksum theo cấu hình |

API Maven Resolver `RepositoryPolicy` mô tả `fail` yêu cầu expected checksum hợp lệ, `warn` ghi warning nếu mismatch/absent và `ignore` không kiểm. Theo Maven Settings APIs, Maven 3 thường mặc định `warn`, còn Maven 4 thường mặc định `fail`; **hãy kiểm đúng version/settings/CLI** vì tổ chức có thể override.

Không sử dụng `ignore` cho toàn bộ repository như “cách sửa” khi remote checksum lỗi, vì điều đó xóa lớp phát hiện lỗi quan trọng.

### 5.2. Maven CLI -C và -c

Với Maven 3.9:

```bash
mvn -B -C clean verify
```

hoặc:

```bash
mvn -B --strict-checksums clean verify
```

`-C` yêu cầu kiểm checksum nghiêm ngặt trên quá trình resolution thích hợp; checksum sai làm build fail thay vì chỉ cảnh báo.

Chế độ nới lỏng:

```bash
mvn -B -c clean verify
```

tương đương `--lax-checksums`; dùng để debug legacy repository sau khi hiểu rủi ro, không mặc định cho CI phát hành.

**Ba giới hạn quan trọng của -C:**
1. Nó **không tự kiểm tra mọi dependency đã cache** ở local Maven repository trước đây.
2. Nó **không tự xác minh GPG signature** của mỗi dependency.
3. Nếu remote repository phục vụ cả artifact lẫn expected checksum bị thay đổi nhất quán, strict checksum vẫn có thể PASS.

### 5.3. Cấu hình ở repositories trong POM

```xml
<repositories>
    <repository>
        <id>central</id>
        <url>https://repo.maven.apache.org/maven2</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
```

Đoạn này là **fragment POM**, không phải POM đầy đủ và không xuất hiện trong project Java lab ở mục 7. Nó cho thấy chính sách **fail** với release artifacts trong repository được khai báo.

Với Maven corporate mirror (Nexus/Artifactory), repository thực tế có thể được chuyển hướng qua `settings.xml`. **Không đảm bảo fragment POM luôn tác động đúng remote cuối cùng** nếu mirror/settings/profiles cung cấp policy khác; phải đọc Maven logs, effective settings và mirror mapping.

### 5.4. Plugin repository khác dependency repository

Nếu tổ chức tách nguồn plugins khỏi dependencies, cần quan tâm `pluginRepositories`:

```xml
<pluginRepositories>
    <pluginRepository>
        <id>central-plugins</id>
        <url>https://repo.maven.apache.org/maven2</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </pluginRepository>
</pluginRepositories>
```

Build plugins như Compiler/Surefire cũng là artifacts Maven tải về. **Quy định nghiêm ngặt cho dependencies mà bỏ qua plugin sources có thể tạo lỗ hổng trong build process.**

### 5.5. settings.xml và CI

Maven 3 đọc settings user tại `~/.m2/settings.xml` và global settings tương ứng trong thư mục cài Maven. CI có thể dùng file được phê duyệt:

```bash
mvn -s ci-settings.xml -B -C clean verify
```

`ci-settings.xml` có thể định nghĩa mirrors/repositories/policies và Maven server IDs. Không đặt credentials vào POM hoặc lưu token nguyên văn trong lệnh CLI/logs. Cần xem mirror `mirrorOf=*` có đưa mọi request qua proxy nội bộ không.

## 6. Tính toàn vẹn không phải tính xác thực: ba mô hình đe dọa

### 6.1. Lỗi truyền tải vô ý

Repository chứa file gốc và checksum gốc. Một byte bị hỏng khi truyền/lưu; calculated digest khác expected digest.

```text
Expected: H(original)
Actual:   H(corrupted)
Result:   MISMATCH
```

Đây là tình huống checksum được thiết kế để bắt tốt.

### 6.2. Actor kiểm soát artifact và checksum

Một actor thay artifact và tạo checksum mới:

```text
Expected: H(modified)
Actual:   H(modified)
Result:   MATCH
```

Mọi phép so sánh SHA-256 đều có thể hợp lệ, nhưng origin chưa được chứng minh. Giải pháp gồm **trusted checksum manifest** bảo vệ độc lập hoặc **signature** với khóa đã được kiểm, cộng access control và audit.

### 6.3. Phát hành chính chủ nhưng có lỗi bảo mật

Maintainer hợp lệ ký một release có CVE. SHA-256 khớp, signature hợp lệ; artifact vẫn không an toàn cho ứng dụng. Cần SCA, update policy, dependency allowlist/denylist và kiểm thử. Không thể dùng một hash để thay vulnerability scanning.

## 7. Project Java 17/JUnit 5: kiểm SHA-256 thật

Thực hành sau chỉ thay file **trong thư mục demo**, không ghi/chỉnh JAR trong `~/.m2/repository` và không tấn công repository ngoài. Tạo binary file chứa chính xác ba bytes ASCII `abc` rồi so với một SHA-256 test vector đã biết.

SHA-256 của bytes `abc` (không newline) là:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

### 7.1. Cấu trúc file

```text
checksum-integrity-lab/
├── pom.xml
├── artifact.bin
├── trusted.sha256
└── src/
    ├── main/java/com/example/checksum/ChecksumVerifier.java
    └── test/java/com/example/checksum/ChecksumVerifierTest.java
```

`artifact.bin` và `trusted.sha256` sẽ được tạo theo OS. Trong demo, trusted.sha256 chỉ là **tên file minh họa**; tính tin cậy thật yêu cầu checksum reference do một nguồn độc lập được phê duyệt tạo/phân phối.

### 7.2. pom.xml hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>checksum-integrity-lab</artifactId>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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
        </plugins>
    </build>
</project>
```

Bộ POM ghim JUnit Jupiter 5.11.4, Compiler 3.13.0, Surefire 3.5.2 và JAR Plugin 3.4.2. `maven.compiler.release=17` giúp compile theo Java 17. Không cần external database/API; tests sử dụng `@TempDir`.

### 7.3. ChecksumVerifier.java

Đường dẫn: `src/main/java/com/example/checksum/ChecksumVerifier.java`.

```java
package com.example.checksum;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ChecksumVerifier {

    private ChecksumVerifier() {
    }

    public static String sha256(Path file)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int n;

            while ((n = input.read(buffer)) != -1) {
                if (n > 0) {
                    digest.update(buffer, 0, n);
                }
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }

    public static String expectedDigest(Path checksumFile)
            throws IOException {
        String expected = Files.readString(
                checksumFile, StandardCharsets.UTF_8).strip();

        if (!expected.matches("[0-9a-fA-F]{64}")) {
            throw new IllegalArgumentException(
                    "Expected SHA-256 must be 64 hex characters");
        }

        return expected;
    }

    public static boolean matches(Path file, Path checksumFile)
            throws IOException, NoSuchAlgorithmException {
        return sha256(file).equalsIgnoreCase(
                expectedDigest(checksumFile));
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: ChecksumVerifier <artifact-file> <checksum-file>");
            System.exit(64);
        }

        String calculated = sha256(Path.of(args[0]));
        String expected = expectedDigest(Path.of(args[1]));

        System.out.println("SHA-256: " + calculated);

        if (calculated.equalsIgnoreCase(expected)) {
            System.out.println("Integrity: MATCH");
        } else {
            System.out.println("Integrity: MISMATCH");
            System.exit(2);
        }
    }
}
```

**Tính runnable và cơ chế:**
- `MessageDigest.getInstance("SHA-256")` tính checksum bằng Java Cryptography Architecture.
- `Files.newInputStream` đọc **bytes gốc**, không giải mã binary thành text.
- `HexFormat` thuộc Java 17, trả digest lowercase hex.
- `Files.readString(..., UTF_8).strip()` chấp nhận newline cuối trong file checksum.
- Regex `[0-9a-fA-F]{64}` từ chối manifest sai định dạng.
- `equalsIgnoreCase` chấp nhận hex uppercase/lowercase.
- Khi mismatch, Java process trả **exit code 2** để CI nhận failure.
- Chương trình **không tải remote artifacts** và không can thiệp Maven Resolver: nó là ví dụ thuật toán kiểm file ở tầng ứng dụng.

### 7.4. ChecksumVerifierTest.java

Đường dẫn: `src/test/java/com/example/checksum/ChecksumVerifierTest.java`.

```java
package com.example.checksum;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class ChecksumVerifierTest {

    private static final String ABC_SHA256 =
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    @Test
    void acceptsExpectedChecksum(@TempDir Path dir) throws Exception {
        Path binary = dir.resolve("artifact.bin");
        Path checksum = dir.resolve("trusted.sha256");

        Files.writeString(binary, "abc", StandardCharsets.UTF_8);
        Files.writeString(checksum, ABC_SHA256, StandardCharsets.UTF_8);

        assertEquals(ABC_SHA256, ChecksumVerifier.sha256(binary));
        assertTrue(ChecksumVerifier.matches(binary, checksum));
    }

    @Test
    void detectsModifiedBytes(@TempDir Path dir) throws Exception {
        Path binary = dir.resolve("artifact.bin");
        Path checksum = dir.resolve("trusted.sha256");

        Files.writeString(binary, "abd", StandardCharsets.UTF_8);
        Files.writeString(checksum, ABC_SHA256, StandardCharsets.UTF_8);

        assertFalse(ChecksumVerifier.matches(binary, checksum));
    }

    @Test
    void refusesMalformedDigest(@TempDir Path dir) throws Exception {
        Path binary = dir.resolve("artifact.bin");
        Path checksum = dir.resolve("trusted.sha256");

        Files.writeString(binary, "abc", StandardCharsets.UTF_8);
        Files.writeString(checksum, "invalid-checksum",
                StandardCharsets.UTF_8);

        assertThrows(IllegalArgumentException.class,
                () -> ChecksumVerifier.matches(binary, checksum));
    }
}
```

Ba JUnit Jupiter tests sử dụng temporary directory riêng do JUnit quản lý. Test 1 bảo đảm SHA-256 `abc` chính xác, test 2 chứng minh một byte thay đổi gây mismatch, test 3 kiểm manifest format bị từ chối. Không cần mạng để thực thi test logic, nhưng Maven có thể cần tải JUnit/plugins lần đầu.

### 7.5. Linux/macOS: tạo fixture không có newline

Chạy trong root `checksum-integrity-lab`:

```bash
printf 'abc' > artifact.bin
printf '%s\n' 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad' > trusted.sha256

mvn -B -ntp clean verify
java -cp target/classes com.example.checksum.ChecksumVerifier artifact.bin trusted.sha256
```

**Rất quan trọng:** `printf 'abc'` tạo đúng 3 bytes ASCII, **không thêm newline**. `echo abc` thường thêm một ký tự xuống dòng nên SHA-256 khác.

Tóm tắt Maven test output kỳ vọng:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **bản tóm tắt**, Maven thực sẽ in thêm logs tùy version.

**Stdout chính xác của Java verifier với bytes abc:**

```text
SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
Integrity: MATCH
```

### 7.6. Windows PowerShell

```powershell
[System.IO.File]::WriteAllBytes(
    "artifact.bin",
    [System.Text.Encoding]::ASCII.GetBytes("abc")
)

$expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

[System.IO.File]::WriteAllText(
    "trusted.sha256",
    $expected + [Environment]::NewLine,
    [System.Text.Encoding]::ASCII
)

mvn -B -ntp clean verify
java -cp target/classes com.example.checksum.ChecksumVerifier artifact.bin trusted.sha256
```

`WriteAllBytes` bảo đảm không thêm BOM hoặc newline cho binary file. Không dùng `Set-Content` mặc định để tạo dữ liệu binary demo nếu bạn chưa kiểm encoding/version PowerShell. Kết quả Java verifier trùng Linux/macOS.

### 7.7. Kiểm bằng công cụ hash của hệ điều hành

Linux (GNU):

```bash
sha256sum artifact.bin
```

Với đúng `abc`, stdout:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  artifact.bin
```

macOS:

```bash
shasum -a 256 artifact.bin
```

Windows:

```powershell
Get-FileHash -Algorithm SHA256 -Path artifact.bin
```

PowerShell hiển thị digest trong trường `Hash`, thường ở dạng uppercase; layout của bảng tùy phiên bản.

**Không nhầm format:** file `trusted.sha256` của demo chỉ chứa **64 hex digits**. GNU `sha256sum -c` yêu cầu **manifest hash + tên file**, ví dụ `<64-hex>  artifact.bin`. Vì vậy đừng dùng `sha256sum -c trusted.sha256` rồi kết luận thuật toán SHA-256 sai do thiếu filename.

## 8. Thí nghiệm mismatch và giới hạn của checksum

### 8.1. Sửa đúng một byte

Sau khi baseline PASS, đổi artifact từ `abc` thành `abd`.

Linux/macOS:

```bash
printf 'abd' > artifact.bin
java -cp target/classes com.example.checksum.ChecksumVerifier artifact.bin trusted.sha256
echo $?
```

Windows PowerShell:

```powershell
[System.IO.File]::WriteAllBytes(
    "artifact.bin",
    [System.Text.Encoding]::ASCII.GetBytes("abd")
)

java -cp target/classes com.example.checksum.ChecksumVerifier artifact.bin trusted.sha256
$LASTEXITCODE
```

Kỳ vọng:
- Digest in ra **khác** SHA-256 `abc`.
- Dòng trạng thái là **`Integrity: MISMATCH`**.
- Exit code là **2**.

Đừng ghi một digest giả cho `abd`; chương trình tự tính digest thật. Đây là **thử nghiệm trên file demo**, không sửa dependency thực tế.

Khôi phục:

```bash
printf 'abc' > artifact.bin
```

Nếu manifest vẫn giữ SHA-256 gốc, chương trình trở lại `Integrity: MATCH`.

### 8.2. Khi actor có quyền sửa cả artifact và expected checksum

Giả sử một actor sửa `artifact.bin` rồi thay `trusted.sha256` bằng **digest mới của artifact đã sửa**. Khi ấy verifier có thể báo `Integrity: MATCH`.

Điều đó là **đúng theo logic code**, vì mục tiêu code chỉ so hai giá trị. Sai lầm thuộc **trust model**: file gọi là “trusted” không hề được bảo vệ khỏi actor ấy. Trong dự án thật, expected digest phải được đưa qua một kênh độc lập như:
- Manifest SHA-256 được review, ký và lưu trong source repository có quyền quản lý riêng;
- Build provenance/attestation từ một CI pipeline đã được cấp quyền, có kiểm chữ ký;
- Trusted checksum registry/approved artifact manifest của tổ chức;
- Public-key signature với maintainer key đã kiểm fingerprint qua kênh khác.

**Không phải cứ chuyển từ SHA-1 sang SHA-256 là tự có authenticity.** Dù thuật toán mạnh, gốc expected hash vẫn phải đáng tin.

## 9. Chữ ký số và việc xác thực publisher

### 9.1. Chữ ký số là gì?

Quy trình khái quát:

```text
Publisher private key
        |
        v
Sign artifact / digest
        |
        v
Detached signature (.asc)
        |
        v
Consumer verifies with public key
        |
        v
VALID signature AND key identity trusted?
```

Bằng chứng chữ ký hợp lệ xác nhận người nắm private key tương ứng đã ký bytes được kiểm. Muốn kết luận người đó là **publisher hợp pháp**, consumer cần xác minh public key identity/trust chain/fingerprint, key rotation và revocation. Nếu chỉ tải một public key từ cùng website bị compromise rồi cho rằng khóa đó chính chủ, bạn chưa đóng trust gap.

### 9.2. Maven GPG Plugin dành cho nhà phát hành

Maven GPG Plugin có goal `gpg:sign` để ký POM, JAR và attached artifacts. Fragment dành cho publisher:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-gpg-plugin</artifactId>
    <version>3.2.8</version>
    <executions>
        <execution>
            <id>sign-artifacts</id>
            <phase>verify</phase>
            <goals>
                <goal>sign</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

**Đây không thuộc POM runnable ở mục 7**, vì nó cần private key và GnuPG/signer đã cấu hình. Không đưa private key/password vào POM hoặc log. Goal `gpg:sign` **tạo** chữ ký khi đóng gói/phát hành; nó **không tự làm Maven consumer verify mọi dependency**. Bật `-C` cũng không kích hoạt việc verify signatures.

### 9.3. Kiểm một chữ ký GPG có sẵn

Khi có artifact và detached signature thật:

```text
library-1.2.0.jar
library-1.2.0.jar.asc
```

và public key đã được nhập sau khi fingerprint được xác minh độc lập:

```bash
gpg --verify library-1.2.0.jar.asc library-1.2.0.jar
```

Đây là lệnh minh họa **không runnable nếu không có files/keys thực**. Kết quả “Good signature” chỉ chứng minh chữ ký hợp với khóa đang dùng; phải kiểm:
1. Fingerprint đúng identity/phát hành được duyệt chưa?
2. Khóa có expired/revoked/compromised không?
3. Artifact version và publisher namespace có khớp approval không?
4. Signature/trusted key có thực sự độc lập khỏi repository bị kiểm soát không?
5. Dù signer đúng, SCA/scan có cảnh báo vulnerabilities không?

Không gọi `gpg --verify` thành cơ chế tự động của Maven Resolver nếu bạn chưa cấu hình một bước kiểm như vậy trong pipeline.

### 9.4. TLS giúp gì?

HTTPS/TLS bảo vệ kết nối tới endpoint với certificate được kiểm, giúp ngăn nhiều kiểu sửa đổi bởi attacker trên mạng. Tuy nhiên server đã bị compromise, publisher credential bị lộ hoặc mirror sai vẫn có thể trả artifact độc hại **qua TLS hoàn toàn hợp lệ**.

Vì vậy nên dùng **TLS + repository access control + strict integrity + independent trusted checksums/signatures + vulnerability scan**, thay vì chọn một công cụ duy nhất.

## 10. Trusted Checksums trong Maven Resolver

Các phiên bản Maven Artifact Resolver mới có cơ chế `TrustedChecksumsSource`, cho phép lấy expected digests từ một nguồn khác transport.

### 10.1. Vì sao nó quan trọng?

Thông thường:
- Artifact và checksum header/sidecar đều từ remote repository.
- Hash khớp nhưng không chống được actor đổi cả hai.
- Local cache có thể chứa artifact từ lần chạy cũ hoặc bị actor khác sửa.

Trusted checksum mechanism đưa **expected checksum từ kênh đã được duyệt** vào quá trình xác minh, có thể qua post-processor để kiểm cả artifact đã resolve không có HTTP request mới.

### 10.2. Hai kiểu lưu trusted checksums

Theo tài liệu Resolver:
- **Summary file source:** các dòng có format tương thích GNU coreutils `sha256sum`, gồm digest và đường dẫn tương đối trong local repository. Mỗi file summary gắn một algorithm.
- **Sparse directory source:** cấu trúc thư mục song song layout Maven local repository, có thể dùng origin-aware keys để phân biệt repository nguồn.

Những APIs và properties cấu hình **khác nhau theo Resolver/Maven version**; không tự khẳng định chúng đã bật trong Maven 3.9. Cần tham khảo đúng docs runtime, triển khai và test với mẫu build riêng.

### 10.3. Trusted checksum khác remote checksum

| Đặc tính | Remote checksum | Trusted checksum |
| --- | --- | --- |
| Expected value đến từ đâu | Remote repo/HTTP header/sidecar | Nguồn độc lập đã được duyệt |
| Phát hiện transfer corruption | Có | Có |
| Phát hiện repo bị thay cả artifact và sidecar | Không đủ | Có thể nếu trusted manifest bất biến với attacker |
| Xác minh publisher identity | Không | Không tự động nếu thiếu signature/identity chain |
| Có thể phát hiện local cache bị sửa | Không được bảo đảm | Có thể nếu post-processing được cấu hình |
| Cần quy trình cập nhật | Repo quản lý | Security/release pipeline quản lý |

Không tự động cập nhật trusted manifest bằng checksum vừa tải trong cùng CI verify job. Làm như vậy sẽ vô hiệu hóa kiểm duyệt khi nguồn tải đã bị sửa.

### 10.4. Khi cập nhật dependency

Ví dụ nâng `lib:1.2.3` lên `lib:1.2.4`:
1. Review thay đổi version và mục đích nâng.
2. Tải artifact ở pipeline duyệt có quyền phù hợp.
3. Kiểm publisher identity/chữ ký và security/license policies.
4. Ghi digest vào trusted manifest có review/chữ ký riêng.
5. Commit hoặc publish manifest qua kênh tin cậy.
6. CI tiêu thụ manifest; mismatch phải fail và điều tra.
7. Lưu lịch sử GAV → hash → provenance → approver.

Trusted digest giúp kiểm **bytes đúng bản đã được phê duyệt**, nhưng nếu không có identity/signing metadata, nó không tự trả lời **ai là người phát hành**.

## 11. Local repository và giới hạn của -C

### 11.1. Cache Maven ở đâu?

Maven thường lưu artifacts/plugins trong `~/.m2/repository`. Nó có thể chứa:
- JAR/POM đã tải từ repository/mirror.
- Plugin artifacts và dependencies của plugin.
- SNAPSHOTs và metadata.
- Artifacts đã `mvn install` từ source local.
- Artifact được cached trước khi policy checksum được nâng lên `fail`.

Vì vậy việc `mvn -C clean verify` PASS trên máy dev **không chứng minh Maven đã băm lại toàn bộ thư mục .m2**. Không có network request mới thì cơ chế transport checksum có thể không kích hoạt cho artifact cache-hit.

### 11.2. Dùng local repository cách ly để điều tra

Nếu cần tái tạo một lần tải dependency, dùng repository tạm riêng:

```bash
mvn -B -C -Dmaven.repo.local=./.m2-isolated clean verify
```

Lệnh tách cache demo khỏi `~/.m2/repository` thường dùng. Nó có thể tải lại JUnit/plugins khi network/repository cho phép. Điều này kiểm rõ hơn hành vi checksum **khi tải**, không tự chứng minh publisher identity.

Đừng xóa nguyên `~/.m2` rồi “hy vọng hết lỗi”. Xóa cache thường làm mất evidence, tăng tải network và có thể phá offline build. Với cache hỏng, chỉ xử lý artifact cụ thể sau khi đã ghi lại log, GAV, origin và nguyên nhân.

### 11.3. SNAPSHOT và -U

`mvn -U` yêu cầu cập nhật snapshot/metadata phù hợp; nhưng nó:
- không xác thực publisher;
- không bảo đảm một SNAPSHOT mutable vẫn chứa bytes cũ;
- không sửa repository phục vụ sai checksum;
- không thay thế version pinning và BOM/dependencyManagement;
- không đảm bảo all-dependency cache checks.

Release artifacts nên có immutable versions, còn SNAPSHOTs thường có chính sách cập nhật khác. Khi một release GAV bị overwrite ở private repository, cache của các CI jobs có thể trở nên không nhất quán dù checksums khớp với bản từng tải.

## 12. Tổ chức CI cho an toàn phụ thuộc

### 12.1. Một pipeline nhiều lớp

```text
Approved Git commit + dependency version policy
             |
             v
Maven Wrapper/JDK/CI image + approved mirrors
             |
             v
mvn -B -ntp -C clean verify
             |
             v
Trusted checksum / GPG signature verification
             |
             v
SCA + license + SBOM + provenance review
             |
             v
Artifact build/release approval
```

Lệnh:

```bash
mvn -B -ntp -C clean verify
```

giúp fail sớm ở các checksum checks của Maven Resolver khi tải dependency/plugins. Nhưng muốn tin cậy chuỗi cung ứng cần thêm:
- registry origin allowlist;
- repository publish permissions/audit;
- trusted checksums hoặc signature check cho artifacts quan trọng;
- kiểm dependency tree, transitive deps và plugin repositories;
- vulnerability scanning và cách cập nhật patches;
- release artifacts immutable;
- CI job ghi Maven/JDK, settings source, commit SHA và manifest checksum.

### 12.2. Vì sao không chỉ chạy sha256sum?

Nếu một pipeline:

```text
download artifact.jar
download artifact.jar.sha256 from the same untrusted host
compare
```

thì chỉ là remote integrity, dù dùng SHA-256. Nó chưa độc lập về trust. Với risk cao, expected hash phải nằm trong một source được duyệt trước khi download, hoặc signature phải được verify với trusted publisher key.

### 12.3. Xử lý dependency confusion

Một GAV có thể bị resolve từ sai repository do `settings.xml`, mirror `mirrorOf`, pluginRepositories hoặc các POM transitive. Checksum khớp với **artifact ở nguồn sai** cũng không làm nó đúng với library mà tổ chức dự định dùng. Hãy quản trị source origin, namespace allowlist, quyền nội bộ và provenance, đồng thời pin versions cụ thể.

### 12.4. Release artifact đã public

Sonatype Central quy định components đã public **immutable**, không cho chỉnh/xóa/redeploy bytes khác vào cùng release version. Nếu đã có lỗi bảo mật hoặc bug, publish **version mới** và thông báo consumers. Checksum sẽ giúp người dùng phát hiện bytes khác với reference, nhưng chính sách bất biến và publisher verification làm nền cho reproducibility.

## 13. Troubleshooting: khi Maven báo checksum mismatch

### 13.1. Các bước an toàn

1. Dừng deploy/release của artifact liên quan.
2. Ghi Maven version, JDK, full GAV/classifier, repo/mirror ID, file JAR/POM/metadata, timestamp.
3. Phân biệt **checksum mismatch** với **checksum missing**, HTTP 401/403, TLS error hoặc artifact not found.
4. Xem policy đang là `fail`, `warn` hay `ignore`; có `-C`/`-c` trong CI không?
5. Kiểm URL thật qua settings/mirrors; đừng chỉ nhìn POM.
6. Với lỗi repository, kiểm replication/proxy caching, upstream file và checksum sidecar/header.
7. Chạy trong local repository cách ly nếu cần kiểm một lần tải mới.
8. Không dùng skip/ignore để bỏ qua checksum mà chưa review.
9. Nếu artifact có bytes khác bản đã published, kiểm publisher/audit logs và trusted manifest.
10. Chỉ chấp nhận lại sau khi nguyên nhân đã được xác minh; lưu evidence.

### 13.2. Bảng lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `Checksum validation failed` | Artifact khác remote digest | Dừng, kiểm repo/mirror/artifact |
| Thiếu checksum trong strict mode | Repo không cung cấp expected hash | Sửa upstream/repository policy |
| Maven chỉ WARN checksum | Chính sách `warn`/`-c` | Xem rủi ro, nâng strict gate |
| Maven dùng bytes sai nhưng checksum MATCH | Repo bị đổi cả file và expected digest | Dùng trusted manifest/signature độc lập |
| Build local PASS, CI FAIL | Cache/mirror/version/settings khác | So môi trường và resolved origin |
| `-C` không bắt file cache bị sửa | Không rehash toàn local repo mặc định | Trusted checksums post-processor/audit |
| Java verifier khác `sha256sum` | Newline/encoding khác `abc` | Tạo file đúng 3 bytes bằng printf |
| `sha256sum -c trusted.sha256` lỗi format | Chỉ có 64 hex, không có filename | Tạo manifest đúng format hoặc dùng Java verifier |
| `gpg --verify` báo BAD signature | Signature không khớp artifact/key | Không dùng artifact, điều tra |
| GPG báo Good signature với key chưa tin | Key fingerprint chưa xác minh | Xác thực identity qua kênh độc lập |
| HTTP certificate/TLS failure | Proxy/CA/hostname sai | Sửa TLS, không disable verification |
| Plugin tải lỗi còn JAR thì ổn | pluginRepositories khác repositories | Kiểm plugin repositories/mirrors |
| SNAPSHOT metadata khác giữa CI jobs | Cập nhật theo snapshot policy | So timestamp/update policy, pin release khi cần |
| `-U` không sửa mismatch | Upstream reference không đồng bộ | Điều tra nguồn, không retry mù |
| Repo cho overwrite cùng GAV | Bytes thay đổi theo thời gian | Chính sách immutable releases |
| Chữ ký hợp lệ nhưng library có CVE | Integrity/authenticity ≠ security | SCA và patch policy |

### 13.3. -X có giúp ích không?

`mvn -X` bật debug chi tiết về resolution, repositories và plugin execution. Log debug có thể chứa repository URLs, file paths và một số thông tin nhạy cảm; cần lọc trước khi chia sẻ công khai. Không dùng raw debug log làm bằng chứng duy nhất nếu không có bản ghi repository state.

## 14. Các ngộ nhận phổ biến

**“Checksum khớp nghĩa là đúng publisher.”** Sai: hash không mang danh tính.

**“Dùng SHA-256 thì không cần trust source.”** Sai: expected digest có thể đã bị thay cùng artifact.

**“Maven -C kiểm mọi file .m2 và chữ ký số.”** Sai: strict checksum không đồng nghĩa full-cache audit hoặc GPG verification.

**“HTTPS bảo đảm artifact không độc hại.”** Sai: TLS xác thực connection endpoint, không kiểm source code.

**“MD5/SHA-1 trong repo là bằng chứng cryptographic security.”** Sai: chúng thường dùng cho transport integrity lịch sử.

**“Good signature luôn nghĩa là khóa thuộc nhà phát hành hợp pháp.”** Sai nếu chưa xác thực fingerprint và key trust.

**“Không còn checksum warning là không có CVE.”** Sai: vulnerability scanning là bài toán khác.

**“Checksum mismatch thì xóa .m2 hoặc bật ignore.”** Sai: phải điều tra upstream, cache, policy và dữ liệu đã published.

**“Version giống nhau thì bytes giống nhau ở mọi repo.”** Không được bảo đảm khi có private repositories cho overwrite hoặc resolution nhầm nguồn.

## 15. Câu hỏi tự đánh giá

**1.** Artifact và `.sha1` cùng được phục vụ từ một mirror, checksum khớp. Đã xác thực maintainer chưa? **Chưa.**

**2.** File thay một byte, expected digest vẫn nguyên. Chế độ `fail` nên phản ứng thế nào? **Chặn resolution/build.**

**3.** Attacker thay cả JAR và SHA-256 sidecar. Mismatch có tất yếu xuất hiện không? **Không.**

**4.** `mvn -C` để làm gì? **Bật strict checksum check** khi Maven Resolver thực hiện kiểm tương ứng, không thay chữ ký.

**5.** `checksumPolicy=warn` có luôn làm build dừng? **Không**, có thể tiếp tục dù warning.

**6.** SHA-256 của ba bytes ASCII `abc` là gì? **ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad**.

**7.** Vì sao `echo abc` có thể sai test vector? **Vì thêm newline**, làm bytes khác.

**8.** Đổi file `abc` thành `abd` mà giữ manifest cũ: Java verifier báo gì? **Integrity: MISMATCH**, exit code **2**.

**9.** Vì sao `sha256sum -c trusted.sha256` không hoạt động với fixture demo? Vì file chỉ chứa hex, không có filename theo format GNU manifest.

**10.** GPG signature hợp lệ nhưng key chưa được xác minh identity, đã có publisher authenticity chưa? **Chưa đủ.**

**11.** `mvn -C` PASS trên cache-hit chứng minh cache không bị ai sửa? **Không được bảo đảm.**

**12.** Có expected SHA-256 từ trusted manifest riêng tốt hơn vì sao? Vì đối thủ sửa repository **không mặc nhiên sửa được expected digest**.

**13.** Maven tải Compiler Plugin từ pluginRepository nào? Phải kiểm settings/pluginRepositories và mirror; **không kết luận chỉ từ dependency repositories**.

**14.** Artifact có chữ ký chính chủ nhưng CVE: dùng bước nào? **SCA/patch assessment** và kiểm security policy riêng.

**15.** Maven Central đã public một release JAR có bug: nên overwrite cùng version không? **Không**, phát hành version mới.

## 16. Checklist áp dụng vào dự án thực tế

- [ ] Phân biệt tính toàn vẹn, tính xác thực và an toàn của dependency.
- [ ] Ghi rõ Maven/Resolver version trong CI, không đoán default checksum policy.
- [ ] Dùng `-C`/`checksumPolicy=fail` khi policy yêu cầu strict transport integrity.
- [ ] Kiểm repositories, pluginRepositories và mirror mapping thực.
- [ ] Không âm thầm chuyển `fail` sang `ignore` chỉ để build xanh.
- [ ] Với chống sửa có chủ đích, có trusted digest độc lập hoặc signature verification.
- [ ] Dùng SHA-256/SHA-512 cho trusted manifests thay vì tin SHA-1/MD5 là proof bảo mật.
- [ ] Nếu dùng GPG, kiểm đúng public key fingerprint và key lifecycle.
- [ ] Không nghĩ Maven GPG Plugin tự verify dependencies của consumer.
- [ ] Bảo vệ TLS/CA và repository publisher permissions.
- [ ] Kiểm local cache trust boundary; không cho rằng `mvn -C` quét lại mọi artifact.
- [ ] Quản trị dependency versions, nguồn origin và transitive dependencies.
- [ ] Có SCA/SBOM/license policies riêng với checksums.
- [ ] Không dùng SNAPSHOT mutable làm release artifact khi không phù hợp.
- [ ] Không xóa cache lớn hoặc bỏ checksum gate khi chưa xác định root cause.
- [ ] Duy trì release versions bất biến và có audit trail.
- [ ] Review checksum manifest như một dữ liệu chính sách, không tự cập nhật trong verify job.
- [ ] Với CI, kiểm bytes, source, tests và release approvals, không chỉ BUILD SUCCESS.

**Kết luận:** Checksum trong Maven bảo vệ **tính toàn vẹn của nội dung so với expected digest**; đây là công cụ quan trọng để phát hiện lỗi truyền tải hoặc file không khớp. Nhưng **tính xác thực của publisher** cần một gốc tin cậy khác: signature/key identity, trusted checksum manifest độc lập, provenance và repository governance. Cả hai cũng chưa đủ để bảo đảm code không có CVE. Hãy dùng checksum strict đúng mục đích, bảo vệ expected digest và kết hợp các lớp kiểm soát supply chain.

### Tài liệu chính thức

- [Apache Maven — Settings Reference (checksumPolicy)](https://maven.apache.org/settings.html)
- [Maven Artifact Resolver — Expected Checksums](https://maven.apache.org/resolver/expected-checksums.html)
- [Maven Artifact Resolver — Checksums](https://maven.apache.org/resolver-archives/resolver-2.0.24/about-checksums.html)
- [Maven Artifact Resolver — RepositoryPolicy](https://maven.apache.org/resolver/apidocs/org/eclipse/aether/repository/RepositoryPolicy.html)
- [Maven 3.9 CLI Reference — strict/lax checksums](https://maven.apache.org/ref/3.9.7/maven-embedder/cli.html)
- [Maven GPG Plugin — gpg:sign](https://maven.apache.org/plugins/maven-gpg-plugin/sign-mojo.html)
- [Sonatype Central — Requirements: Checksums](https://central.sonatype.org/publish/requirements/)
- [Sonatype Central — Immutability](https://central.sonatype.org/publish/requirements/immutability/)
