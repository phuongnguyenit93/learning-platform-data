# Xác minh checksum và chữ ký theo khả năng của từng công cụ

Trong chuỗi cung ứng phần mềm, một file JAR, dependency hoặc container image có thể bị thay thế trong quá trình tải xuống, lưu trữ, build hay phát hành. Hai cơ chế thường dùng để phát hiện việc đó là **checksum (mã băm)** và **chữ ký số**.

Chúng trả lời hai câu hỏi khác nhau:

- **Checksum:** nội dung file nhận được có khớp với digest kỳ vọng đã được tin cậy không?
- **Chữ ký số:** dữ liệu có được ký bằng private key tương ứng với public key mà ta tin là của nhà phát hành không?

SHA-256 khớp với expected digest xác nhận **tính toàn vẹn so với giá trị kỳ vọng**. Nó không tự chứng minh ai tạo file. Chữ ký hợp lệ chứng minh dữ liệu được ký bằng khóa riêng tương ứng; để kết luận đó là publisher mong đợi, cần xác minh **fingerprint và danh tính khóa** qua kênh đáng tin cậy.

| Công cụ | Đối tượng | Khả năng chính |
| --- | --- | --- |
| sha256sum, PowerShell Get-FileHash, Java MessageDigest | File bất kỳ | Tính hash và so với checksum tin cậy |
| Gradle Dependency Verification | Dependencies, plugins, metadata được Gradle resolve | Checksum và PGP signature theo metadata đã duyệt |
| Maven Resolver | Artifacts tải từ Maven repository | Kiểm tra checksum sidecar theo repository policy |
| Maven GPG Plugin / GnuPG | Artifacts Maven phát hành | Tạo và xác minh detached OpenPGP signatures |
| JDK jarsigner / keytool | Java JAR/ZIP | Xác minh entry signatures và chứng thư người ký |
| Sigstore Cosign | OCI container images và blobs | Xác minh chữ ký gắn với digest, key hoặc OIDC identity |

Bài này dùng Java 17 và ví dụ Gradle/Maven để giải thích cách từng công cụ hoạt động. Không nhúng private key, password hoặc checksum giả vào source code.

## 1. Checksum, hash và chữ ký số

### 1.1. Hash là dấu vân tay của bytes

Hàm băm mật mã nhận dữ liệu có độ dài bất kỳ và trả về digest có độ dài cố định. SHA-256 tạo digest 256 bit, thường biểu diễn thành 64 ký tự hex:

~~~text
artifact.jar --SHA-256--> 64-character hexadecimal digest
~~~

Chỉ cần một byte của file thay đổi, digest cũng thay đổi với xác suất áp đảo. Hash hữu ích để phát hiện file hỏng hoặc file khác với bản đã ghi nhận.

| Thuật toán | Độ dài digest | Nhận xét |
| --- | --- | --- |
| MD5 | 128 bit | Không dùng để chống đối thủ |
| SHA-1 | 160 bit | Đã có tấn công va chạm thực tế; tránh dùng cho bảo mật mới |
| SHA-256 | 256 bit | Lựa chọn phổ biến cho integrity |
| SHA-512 | 512 bit | Lựa chọn mạnh, digest dài hơn |

**Hash không phải mã hóa.** SHA-256 thông thường không dùng private key. Bất kỳ ai có file đều có thể tính digest.

### 1.2. Vì sao checksum không tự chứng minh nguồn gốc?

Giả sử bạn tải hai file từ cùng một máy chủ:

~~~text
app.jar
app.jar.sha256
~~~

Nếu máy chủ hoặc tài khoản phát hành bị xâm nhập, attacker có thể thay cả JAR lẫn checksum. Hai file vẫn khớp nhưng artifact có thể độc hại.

Vì vậy, expected checksum cần đến từ **nguồn độc lập đã xác thực**: release manifest được ký, repository được bảo vệ, CI release record có quyền truy cập được kiểm soát hoặc kênh chính thức của publisher. Tải artifact và checksum từ cùng một nguồn không tin cậy không tạo xác thực độc lập.

### 1.3. Chữ ký số bổ sung xác thực người ký

Publisher dùng **private key** để ký artifact hoặc digest/metadata. Consumer dùng public key tương ứng để xác minh:

~~~text
Publisher:
  artifact bytes -> hash -> private key -> digital signature

Consumer:
  artifact + signature
       |
  trusted public key / certificate
       |
  verify signature + signer identity
       |
     PASS / FAIL
~~~

Chữ ký số bảo vệ dữ liệu được ký khỏi thay đổi mà không bị phát hiện. Tuy nhiên, chữ ký toán học hợp lệ chưa đủ chứng minh signer là publisher mong đợi. Cần xác minh fingerprint/key identity, certificate chain, issuer, thời hạn và trạng thái thu hồi khi áp dụng.

### 1.4. Khi nào dùng cả hai?

| Cách kiểm tra | Integrity | Xác thực publisher |
| --- | --- | --- |
| SHA-256 so với expected digest tin cậy | Có | Không tự có |
| Checksum lấy từ cùng nguồn không tin cậy với file | Chỉ phát hiện lỗi ngẫu nhiên; không chống thay thế đồng thời | Không |
| Signature với key đã xác thực | Có | Có, trong phạm vi trust policy |
| Signature hợp lệ nhưng key chưa được xác minh | Có | Chưa đủ |
| SHA-256 + signature + key fingerprint tin cậy | Có | Có cơ sở mạnh hơn |

Gradle cũng phân biệt checksum để xác minh integrity và signature để xác minh provenance. Có thể kết hợp cả hai; nếu dependency không được ký thì checksum đã xác minh là fallback. [Gradle: Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html).

## 2. Xác minh checksum bằng công cụ hệ điều hành

### Linux

~~~bash
sha256sum app.jar
~~~

Lệnh in digest và tên file. So sánh digest với giá trị lấy từ release record đã xác thực.

Nếu sidecar có định dạng GNU coreutils:

~~~bash
sha256sum --check app.jar.sha256
~~~

Không phải repository checksum sidecar nào cũng chứa cả filename theo định dạng sha256sum --check mong đợi. Nếu sidecar chỉ chứa chuỗi hex, hãy đọc digest và so sánh theo cách phù hợp.

### macOS

~~~bash
shasum -a 256 app.jar
~~~

### Windows PowerShell

~~~powershell
Get-FileHash -Algorithm SHA256 .\app.jar
~~~

Kết quả có trường Hash và Algorithm. So sánh Hash với checksum nhận từ nguồn tin cậy. Không lấy hash vừa tính rồi tự coi đó là expected value của publisher.

Đoạn kiểm tra PowerShell:

~~~powershell
$expected = $env:EXPECTED_SHA256
$actual = (Get-FileHash -Algorithm SHA256 .\app.jar).Hash

if ($actual -eq $expected) {
    'RESULT=PASS'
} else {
    'RESULT=FAIL'
    exit 1
}
~~~

Biến EXPECTED_SHA256 phải do CI/release process cấp từ manifest đã xác thực. Nếu biến trống hoặc sai định dạng, pipeline nên fail sớm.

### Khi checksum mismatch

1. Dừng sử dụng artifact và không đưa vào deploy.
2. Xác minh đã tải đúng file/version/platform chưa.
3. Kiểm tra nguồn expected checksum và quá trình truyền file.
4. Kiểm tra repository mirror/cache, proxy hoặc artifact bị thay thế.
5. Tải lại từ nguồn xác thực hoặc yêu cầu publisher điều tra.
6. Chỉ cập nhật expected checksum sau khi có xác nhận độc lập và review.

**Không tự tạo checksum mới rồi ghi đè expected value để làm build xanh.** Làm vậy có thể biến cảnh báo supply-chain thành việc chấp nhận artifact bị thay thế.

## 3. Java 17: kiểm tra SHA-256 bằng MessageDigest

Java standard library có java.security.MessageDigest. Chương trình sau nhận đường dẫn file và expected SHA-256, rồi in RESULT=PASS hoặc RESULT=FAIL.

### File Sha256Verifier.java

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class Sha256Verifier {

    private Sha256Verifier() {
    }

    public static void main(String[] args)
            throws IOException, NoSuchAlgorithmException {

        if (args.length != 2 || !args[1].matches("[0-9a-fA-F]{64}")) {
            System.err.println(
                    "Usage: java Sha256Verifier <file> <expected-sha256>");
            System.exit(2);
            return;
        }

        byte[] expected = HexFormat.of().parseHex(args[1]);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        byte[] actual = digest.digest();

        if (MessageDigest.isEqual(expected, actual)) {
            System.out.println("RESULT=PASS");
        } else {
            System.out.println("RESULT=FAIL");
            System.exit(1);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Sha256Verifier.java
java Sha256Verifier app.jar "$EXPECTED_SHA256"
~~~

EXPECTED_SHA256 phải được cung cấp từ release manifest đã xác thực. Nếu file khớp, stdout chính xác:

~~~text
RESULT=PASS
~~~

Nếu file không khớp:

~~~text
RESULT=FAIL
~~~

Chương trình thoát mã 1 khi mismatch, mã 2 khi tham số sai và mã 0 khi pass. Nó đọc file theo stream, không cần nạp toàn bộ artifact vào RAM; MessageDigest.isEqual so sánh hai byte arrays. Expected checksum vẫn phải được xác thực từ nguồn tin cậy trước khi truyền vào chương trình.

Không tự thiết kế hàm hash. Dùng thuật toán chuẩn và implementation của JDK/công cụ đã được kiểm chứng.

## 4. Gradle Dependency Verification

Gradle có cơ chế **Dependency Verification**. Khi project có file:

~~~text
gradle/verification-metadata.xml
~~~

Gradle tự động dùng metadata này để kiểm tra artifacts và metadata được dependency management engine resolve. Phạm vi bao gồm:

- External JAR/ZIP dependencies.
- POM, Ivy descriptors và Gradle Module Metadata.
- Plugins của project và settings.
- Artifacts resolve qua dependency resolution APIs.

Cơ chế này không kiểm tra mọi file trên máy. Theo tài liệu Gradle, changing dependencies như SNAPSHOT và artifacts được build locally trong chính project không thuộc phạm vi xác minh dependency này. [Gradle dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 4.1. Tạo metadata bằng SHA-256

Từ root project:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Gradle resolve các configurations, tính SHA-256 và tạo/cập nhật gradle/verification-metadata.xml.

Để tạo cả checksum và PGP signatures:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

Gradle hỗ trợ MD5, SHA-1, SHA-256 và SHA-512, nhưng SHA-256/SHA-512 là lựa chọn an toàn hơn cho xác minh hiện đại. Gradle chỉ hỗ trợ signature verification với PGP signature dạng ASCII-armored .asc được publish trên remote repositories. Không phải artifact nào cũng có signature. [Gradle checksum and signature verification](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 4.2. Ví dụ entry trong verification metadata

Một entry có dạng:

~~~xml
<component group="com.google.guava"
           name="failureaccess"
           version="1.0.3">
    <artifact name="failureaccess-1.0.3.jar">
        <pgp value="BDB5FA4FE719D787FB3D3197F6D4A1D411E9D1AE"/>
        <sha256 value="cbfc3906b19b8f55dd7cfd6dfe0aa4532e834250d7f080bd8d211a3e246b59cb"/>
    </artifact>
</component>
~~~

Đây là ví dụ cấu trúc từ tài liệu Gradle. Trong project thực, các giá trị phải khớp đúng dependency/version và key đã xác minh; không copy entry mẫu này để xác minh artifact khác.

Phần cấu hình có thể bật signature verification:

~~~xml
<configuration>
    <verify-metadata>true</verify-metadata>
    <verify-signatures>true</verify-signatures>
</configuration>
~~~

Khi verify-signatures bật, Gradle tìm PGP signature tương ứng và xác minh với trusted keys. Nếu artifact không có signature, checksum đã khai báo có thể được dùng làm fallback. Metadata phải chứa đủ thông tin cho các artifacts thực sự được resolve.

### 4.3. Trusted key phải được xác minh độc lập

Gradle lưu trusted public keys trong verification metadata/keyring. Khi thêm khóa:

- Dùng **full 40-character fingerprint** cho PGP key/trusted-key entries, không chỉ short key ID.
- Xác minh fingerprint trên website chính thức của publisher hoặc qua kênh độc lập.
- Ghi nguồn và lý do tin cậy trong metadata nếu phù hợp.
- Kiểm tra key rotation và thông báo thu hồi.
- Không tự động tin một key chỉ vì nó được tải từ keyserver.

Một chữ ký có thể hợp lệ về mặt toán học nhưng được tạo bởi key của attacker. Trust policy mới quyết định key đó có đại diện publisher mong đợi không. [Gradle trusted keys](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 4.4. Bootstrap cần review

write-verification-metadata ghi nhận thông tin từ artifacts mà Gradle đang resolve. Nếu repository hoặc cache đã bị compromise trước lần bootstrap, Gradle có thể ghi checksum/signature metadata của artifact độc hại vào baseline.

Sau bootstrap:

1. Review diff verification-metadata.xml và keyring.
2. Xác minh checksum từ nguồn độc lập khi có thể.
3. Đối chiếu trusted key fingerprint với nguồn chính thức.
4. Kiểm tra entries có origin="Generated by Gradle"; chúng chưa có nghĩa đã được xác minh độc lập.
5. Cập nhật origin/ghi chú tin cậy sau khi review.
6. Commit metadata vào version control để developer và CI dùng chung baseline.

**Bootstrap tạo baseline thuận tiện, không tự chứng minh mọi dependency đang an toàn.** [Gradle bootstrapping guidance](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 4.5. Khi verification failure

Khi checksum không khớp hoặc signature không được tin cậy:

- Không xóa entry lỗi chỉ để build chạy tiếp.
- Xác định artifact coordinates, repository URL, file name và expected metadata.
- Xác minh checksum/key trên nguồn chính thức.
- Điều tra mirror/cache/local repository nếu cùng artifact tải về có bytes khác.
- Nếu publisher xoay khóa, xác minh fingerprint mới và review như một security change.
- Chỉ cập nhật metadata sau khi xác nhận artifact mới đúng.

Gradle tạo report chi tiết về verification failures. Muốn console verbose, cấu hình:

~~~properties
org.gradle.dependency.verification.console=verbose
~~~

Metadata áp dụng trên toàn build, gồm root và subprojects. Khi dependency/plugin version đổi, phải cập nhật metadata có review; không giả định Gradle tự biết entry cũ hết hạn.

## 5. Maven: checksum policy và chữ ký PGP/GPG

Maven có hai khả năng khác nhau:

1. **Maven Resolver checksum policy:** kiểm tra checksum sidecar khi tải artifact từ repository.
2. **GPG/PGP signatures:** publisher ký artifact/POM; consumer xác minh signature và danh tính public key bằng quy trình phù hợp.

Maven checksum policy không thay cho PGP signer verification.

### 5.1. Đặt checksum policy thành fail

Maven repository policy hỗ trợ:

| Giá trị | Hành vi |
| --- | --- |
| fail | Dừng resolution khi checksum sai hoặc thiếu |
| warn | Cảnh báo khi checksum sai hoặc thiếu |
| ignore | Bỏ qua kiểm tra checksum |

Tài liệu Maven hiện tại ghi default là warn với Maven 3 và fail với Maven 4 trở lên. Vì hành vi phụ thuộc Maven version, project cần enforcement rõ nên cấu hình tường minh fail. [Maven settings checksumPolicy](https://maven.apache.org/settings.html).

Đoạn cấu hình bên trong một repository:

~~~xml
<releases>
    <enabled>true</enabled>
    <checksumPolicy>fail</checksumPolicy>
</releases>
<snapshots>
    <enabled>false</enabled>
    <checksumPolicy>fail</checksumPolicy>
</snapshots>
~~~

Đây là snippet cho repository releases. Nếu dùng snapshot repository, bật snapshots và áp policy tương ứng. Có thể cấu hình tương tự trong pluginRepository để kiểm tra plugin artifacts.

Checksum policy kiểm tra checksum do repository cung cấp. Nếu attacker có thể thay cả artifact và sidecar checksum trong cùng repository, cơ chế này không xác thực publisher độc lập; cần chữ ký số hoặc trust channel khác.

### 5.2. Yêu cầu checksum và signature khi publish Maven Central

Theo yêu cầu publish hiện hành của Sonatype Central:

- Files được upload phải có checksum sidecar hợp lệ; .md5 và .sha1 được yêu cầu, còn .sha256 và .sha512 được hỗ trợ.
- Files được upload phải có GPG/PGP detached signature .asc tương ứng.
- Signature/checksum files cần đi cùng artifact, POM và các files được phát hành theo yêu cầu.

Đây là **yêu cầu tương thích xuất bản của Central**, không có nghĩa MD5/SHA-1 là thuật toán nên chọn cho bảo mật mới. Khi kiểm soát integrity nội bộ, ưu tiên SHA-256/SHA-512 và chữ ký/key identity mạnh. Kiểm tra policy Central mới nhất tại thời điểm phát hành. [Sonatype Central publishing requirements](https://central.sonatype.org/publish/requirements/).

### 5.3. Ký artifacts bằng Maven GPG Plugin

Apache Maven GPG Plugin có goal gpg:sign để ký project artifact, POM và attached artifacts bằng GnuPG. Goal này mặc định gắn với phase verify trong plugin docs. [Maven GPG Plugin sign goal](https://maven.apache.org/plugins/maven-gpg-plugin/sign-mojo.html).

Ví dụ cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-gpg-plugin</artifactId>
    <version>3.2.8</version>
    <configuration>
        <bestPractices>true</bestPractices>
    </configuration>
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
~~~

Version 3.2.8 là ví dụ theo tài liệu plugin hiện tại; project cần chọn version phù hợp Maven/JDK và policy đã kiểm tra. bestPractices giúp plugin thực thi thực hành bảo vệ thông tin xác thực.

Chạy:

~~~bash
mvn verify
~~~

Plugin gọi GnuPG để ký artifacts/POM/attached artifacts theo execution. Private key không được lưu trong repository, POM hoặc file build công khai.

### 5.4. Bảo vệ passphrase và private key

Maven GPG Plugin khuyến nghị dùng gpg-agent/pinentry hoặc cơ chế secret environment cho môi trường non-interactive, tùy cấu hình plugin/GnuPG. Tránh:

- Viết passphrase trực tiếp vào POM.
- Truyền password plaintext trên command line.
- Commit private key vào Git.
- In secret vào Maven/CI logs.

Dùng key được bảo vệ bằng hardware token, HSM, secret manager hoặc signing service nếu tổ chức hỗ trợ. Chỉ release job có quyền ký mới được truy cập private key. [Maven GPG Plugin security practices](https://maven.apache.org/plugins/maven-gpg-plugin/).

### 5.5. Xác minh detached signature bằng GnuPG

Giả sử publisher cung cấp:

~~~text
app-1.2.3.jar
app-1.2.3.jar.asc
~~~

Consumer chạy:

~~~bash
gpg --verify app-1.2.3.jar.asc app-1.2.3.jar
~~~

GnuPG kiểm tra signature file với artifact bytes. Nhưng cần xác minh thêm:

- Signature có hợp lệ không?
- Fingerprint public key có đúng key publisher đã công bố không?
- Key có hết hạn, bị revoke hoặc đã xoay không?
- Identity trong key có được xác minh độc lập không?

Xem fingerprint:

~~~bash
gpg --fingerprint
~~~

So sánh **full fingerprint** với thông tin publisher công bố qua kênh xác thực. Thông báo Good signature chỉ cho biết chữ ký hợp lệ theo key đang dùng; nó không tự chứng minh key đó thuộc đúng publisher.

### 5.6. Sidecar checksum và PGP signature

~~~text
artifact.jar
artifact.jar.sha256  -> checksum (integrity against trusted value)
artifact.jar.asc     -> detached PGP signature (signer + integrity)
~~~

Nếu chỉ có .sha256, expected digest cần lấy từ nguồn tin cậy. Nếu có .asc, cần trusted public key/fingerprint. Khi có cả hai, xác minh song song để tăng độ chắc chắn.

## 6. JDK jarsigner và keytool: ký và xác minh Java JAR

JDK cung cấp:

- jarsigner: ký và xác minh JAR/ZIP.
- keytool: tạo/quản lý keystore, key pairs và certificate entries; in fingerprint chứng thư.

JAR signature thường được lưu trong META-INF, gồm signature file .SF và signature block .RSA, .DSA hoặc .EC tùy key/algorithm. Verification kiểm tra chữ ký và digest của những entries đã ký. Oracle JDK 17 docs cũng mô tả cảnh báo khi có entries chưa ký hoặc certificate chain có vấn đề. [JDK 17 jarsigner documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html).

### 6.1. Tạo khóa demo

Chỉ để thử nghiệm trên máy học tập, tạo key pair và self-signed certificate:

~~~bash
keytool -genkeypair -alias demo-signer -keyalg RSA -keysize 3072 -validity 3650 -keystore demo-signing.p12 -storetype PKCS12 -dname "CN=Demo Signer, O=Example"
~~~

Keytool yêu cầu password theo tương tác. Đây là **khóa demo tự ký**, không đại diện danh tính publisher thực tế và không được dùng làm production signing key. Không đưa file demo-signing.p12 vào repository.

Production private key cần được quản lý bằng quy trình bảo mật, phân quyền, backup, rotation và audit phù hợp.

### 6.2. Ký JAR

~~~bash
jarsigner -keystore demo-signing.p12 -storetype PKCS12 -signedjar app-signed.jar app.jar demo-signer
~~~

Lệnh tạo app-signed.jar từ app.jar. Dùng output riêng để giữ bản gốc; nếu không chỉ định signedjar, jarsigner có thể cập nhật file đầu vào theo hành vi mặc định.

Không truyền password trong command line; để tool hỏi hoặc sử dụng cơ chế bảo vệ phù hợp.

### 6.3. Xác minh signature

~~~bash
jarsigner -verify -verbose -certs app-signed.jar
~~~

Khi chữ ký và entries đã ký hợp lệ, output thường có thông báo jar verified. Đọc toàn bộ warning, không chỉ dòng cuối.

Trong CI, có thể yêu cầu severe warnings làm lệnh thất bại:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

strict khiến severe warnings được phản ánh qua exit code. Với demo self-signed, cảnh báo self-signed/untrusted là điều có thể gặp; nó không chứng minh publisher identity đã được xác thực. Release thật cần certificate chain và trust policy phù hợp.

### 6.4. Xem signer certificate và fingerprint

~~~bash
keytool -printcert -jarfile app-signed.jar
~~~

Lệnh in thông tin chứng thư trong signed JAR, gồm fingerprint SHA-256. So sánh fingerprint với giá trị publisher công bố qua một kênh độc lập. Oracle khuyến nghị kiểm tra fingerprint với người gửi hoặc nguồn public key an toàn trước khi tin/import certificate. [JDK 17 keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html).

**Không tự động tin certificate chỉ vì nó được nhúng trong JAR.** Attacker có thể ký bằng key của họ và nhúng certificate của họ. Việc so fingerprint ngoài băng mới giúp xác định key có thuộc publisher mong đợi không.

### 6.5. Giới hạn của JAR signature

- Không chứng minh code không có vulnerability.
- Không chứng minh signer đã review source code.
- Không thay thế dependency scanning.
- Không bảo vệ entries được thêm sau khi ký nếu chúng không được ký.
- Không bảo đảm certificate chain được tin cậy nếu thiếu trust anchors.
- Không thay thế provenance hoặc checksum từ nguồn tin cậy khác.

Ký **sau khi hoàn tất đóng gói**. Nếu sửa, repack hoặc thêm nội dung sau khi ký, phải ký lại và kiểm tra lại. Cảnh báo unsigned entries cần được điều tra vì các entries đó không được integrity-protect bởi signature tương ứng.

## 7. Sigstore Cosign: xác minh chữ ký OCI container image

JAR signature không phải cơ chế chuyên biệt cho OCI images. Với container images, công cụ phổ biến là **Cosign** trong hệ sinh thái Sigstore.

OCI image được tham chiếu bằng tag hoặc digest:

~~~text
registry.example.com/team/orders-api:1.2.3
registry.example.com/team/orders-api@sha256:...
~~~

Tag dễ đọc nhưng có thể được gắn lại theo policy registry. Digest là content-addressed reference trỏ tới nội dung cụ thể. Khi cần xác minh một bản triển khai, lấy digest từ release/registry record đã tin cậy rồi verify chính reference đó.

**Digest tự nó không chứng minh ai phát hành image.** Nếu attacker thay image và cả digest mà hệ thống nhận, vẫn cần signature/identity trust để xác thực publisher.

### 7.1. Xác minh bằng public key

Khi publisher phát hành public key đã được xác minh:

~~~bash
cosign verify --key cosign.pub "$IMAGE_REF"
~~~

IMAGE_REF phải chứa image reference theo digest lấy từ release record/registry tin cậy, dạng registry/repository@sha256:... . Public key cosign.pub phải được phân phối/xác thực qua trust channel độc lập.

Cosign signature payload gắn với image digest; lệnh verify kiểm tra signature và digest claim theo mặc định với payload Cosign tiêu chuẩn. [Sigstore Cosign verification](https://docs.sigstore.dev/cosign/verifying/verify/).

### 7.2. Keyless verification với OIDC identity

Trong CI hỗ trợ OpenID Connect, Cosign có thể tạo chữ ký keyless gắn với certificate identity do OIDC issuer cấp. Consumer cần xác minh identity mong đợi và OIDC issuer mong đợi:

~~~bash
cosign verify "$IMAGE_REF" --certificate-identity="$EXPECTED_IDENTITY" --certificate-oidc-issuer="$EXPECTED_ISSUER"
~~~

EXPECTED_IDENTITY và EXPECTED_ISSUER phải lấy từ release policy đã xác thực, chẳng hạn identity của release workflow và issuer của hệ thống CI. Không dùng wildcard rộng nếu policy cần giới hạn một repository/workflow cụ thể.

Cosign hỗ trợ xác minh bằng key truyền thống hoặc keyless identity; cả hai cách đều cần trust policy rõ ràng. [Cosign keyless verification](https://docs.sigstore.dev/cosign/verifying/verify/).

### 7.3. Quy trình ký image trong CI

1. Build image.
2. Push image vào registry được phép.
3. Lấy digest của image đã push.
4. Ký đúng digest bằng signing key hoặc OIDC identity của release workflow.
5. Verify signature/identity/digest trước khi deploy.
6. Lưu digest và verification result vào release record.

Không chỉ ký một tag rồi bỏ qua digest mà pipeline thực sự deploy. Tag có thể được cập nhật sau thời điểm ký; digest là định danh nội dung cần được ràng buộc.

### 7.4. Signature không thay thế attestation và vulnerability scan

Cosign image signature xác minh signature theo trust policy và image digest. Nó không tự chứng minh source code đã được review, build dùng đúng source commit, build process không bị compromise hoặc image không có CVE.

Để kiểm chứng quy trình build, có thể dùng provenance/SLSA attestations và xác minh theo policy riêng. Để kiểm tra CVE, dùng SBOM và vulnerability scanner. Ba lớp trả lời các câu hỏi khác nhau: **ai ký**, **được build từ đâu/bằng quy trình nào**, và **có thành phần dễ tổn thương nào**.

## 8. So sánh công cụ theo loại artifact

| Nhu cầu | Công cụ | Công cụ làm được | Giới hạn |
| --- | --- | --- | --- |
| Kiểm tra file JAR tải xuống | SHA-256 utility | So bytes với digest kỳ vọng | Không xác thực signer nếu chỉ có checksum |
| Tự động kiểm tra Gradle dependencies | Dependency Verification | Verify checksum/signature theo metadata | Không bao phủ local build outputs và changing dependencies |
| Kiểm tra checksum Maven repository | Maven Resolver | Fail/warn/ignore khi sidecar thiếu/sai | Không thay PGP signer verification |
| Ký Maven release | Maven GPG Plugin | Ký artifact/POM/attached artifacts | Consumer vẫn cần xác minh key/fingerprint |
| Xác minh Java signed JAR | jarsigner / keytool | Verify entries/signature/certificate | Phải kiểm tra certificate trust và unsigned entries |
| Xác minh OCI image | Cosign | Verify signature gắn với digest, key hoặc OIDC identity | Không thay vulnerability/provenance checks |

Chọn công cụ theo câu hỏi:

- **“File có bị thay đổi không?”** → SHA-256 từ nguồn tin cậy.
- **“Dependency Gradle có đúng bản đã duyệt không?”** → Gradle verification metadata.
- **“Maven repository có checksum hợp lệ không?”** → Maven checksum policy; nếu cần signer, verify PGP riêng.
- **“Ai đã ký JAR này?”** → jarsigner + certificate fingerprint/trust chain.
- **“Image đang deploy có chữ ký của release workflow không?”** → Cosign với digest và identity/issuer.
- **“Image được build từ source commit nào?”** → provenance attestation, không chỉ image signature.

## 9. Chuỗi kiểm tra mẫu cho Spring Boot release

Giả sử release pipeline tạo ra:

~~~text
orders-api-1.2.3.jar
orders-api-1.2.3.jar.sha256
orders-api-1.2.3.jar.asc
orders-api:1.2.3
~~~

Một quy trình có thể tổ chức:

1. **Xác minh artifact file:** tính SHA-256 bằng hệ điều hành hoặc Sha256Verifier, so với release manifest đã xác thực. Nếu mismatch, dừng.
2. **Xác minh chữ ký file:** nếu có .asc, dùng GPG verify và so fingerprint public key với publisher's official fingerprint. Nếu JAR dùng Java code signing certificate, dùng jarsigner -verify -strict và keytool -printcert.
3. **Xác minh dependency baseline:** chạy Gradle build với gradle/verification-metadata.xml đã được review/commit. CI fail nếu checksum/signature của dependency/plugin khác baseline.
4. **Build và kiểm tra image:** lấy digest sau khi push, verify Cosign signature bằng public key hoặc expected OIDC identity/issuer. Dùng digest reference để deploy.
5. **Lưu release provenance:** giữ source commit, Gradle/Maven version, JDK/toolchain, artifact SHA-256, JAR signer fingerprint, OCI image digest, Cosign identity/issuer, verification result và CI run.

Các trường provenance phải lấy từ hệ thống release thật, không tự điền dữ liệu giả. Một release có thể dùng một số lớp xác minh hoặc tất cả, tùy loại artifact và policy.

## 10. Quản lý khóa, fingerprint và vòng đời chứng thư

### 10.1. Public key phải đến từ nguồn đáng tin

Có thể tải public key từ keyserver hoặc registry, nhưng nơi lưu public key không tự xác nhận identity. So sánh full fingerprint với website chính thức, release documentation, kênh hỗ trợ đã xác thực hoặc trust store do tổ chức quản lý.

Không chỉ dựa vào tên người ký trong GPG, email trong certificate, short key ID, public key được tải cùng artifact từ mirror chưa được tin hoặc dòng Good signature mà không kiểm tra fingerprint.

### 10.2. Key rotation

Khi publisher thay key:

1. Xác nhận thông báo key rotation qua kênh chính thức.
2. Xác minh fingerprint key mới.
3. Xác định thời điểm bắt đầu/kết thúc chấp nhận key cũ.
4. Cập nhật Gradle verification metadata, GPG keyring, certificate trust hoặc Cosign policy.
5. Review thay đổi và chạy build/verify trên CI.
6. Loại key cũ theo lịch sau khi không còn release cần xác minh bằng key đó.

Nếu key bị compromise/revoke, xử lý theo incident policy thay vì coi mọi signature lịch sử đều tự động an toàn.

### 10.3. Certificate expiry và timestamp

Với JAR signing dùng X.509 certificates, kiểm tra validity period, chain, key usage, algorithm và timestamp. Một JAR có thể được ký khi certificate còn hiệu lực và có trusted timestamp, nhưng phải đọc warnings và policy của runtime/JDK. jarsigner -strict giúp biến severe warnings thành lỗi trong automation.

### 10.4. Bảo vệ private key

- Chỉ signing job có quyền ký.
- Dùng HSM/KMS hoặc signing service khi khả thi.
- Dùng secret manager/agent, không commit private keys.
- Hạn chế log và shell history chứa credentials.
- Audit ai ký, lúc nào và artifact digest nào.
- Có kế hoạch rotation/revocation và backup an toàn.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| SHA-256 khác expected | Sai version, lỗi truyền tải, mirror khác hoặc file bị thay | Dừng dùng; xác minh nguồn, path và release manifest |
| Hash khớp nhưng artifact độc hại | Expected checksum lấy từ cùng nguồn bị compromise | Xác minh chữ ký và lấy checksum từ kênh độc lập |
| Gradle checksum verification failed | Artifact khác baseline hoặc repository/cache có vấn đề | Kiểm tra coordinates, file, repository và review metadata |
| Gradle untrusted PGP key | Key mới, thiếu keyring hoặc attacker key | Xác minh full fingerprint qua publisher trước khi thêm |
| Nhiều Generated by Gradle origins | Artifact không ký hoặc signature/key chưa được xác minh | Review từng entry, đối chiếu official checksum/signature |
| Maven chỉ cảnh báo checksum mismatch | Checksum policy đang là warn | Cấu hình fail và điều tra sidecar |
| Maven tải artifact nhưng không kiểm tra PGP | Checksum policy không thực hiện PGP verification | Verify .asc bằng GnuPG hoặc tool chuyên dụng |
| GPG báo Good signature nhưng signer lạ | Signature đúng theo key hiện tại, nhưng key chưa được xác thực | So full fingerprint và identity qua nguồn chính thức |
| jarsigner báo verified nhưng có warning | Self-signed/expired certificate, chain lỗi hoặc unsigned entries | Đọc warnings, dùng strict, kiểm tra cert/entries |
| JAR signature fail sau build | File bị sửa/repack sau khi ký | Ký sau packaging cuối và kiểm tra lại |
| keytool in certificate nhưng không biết tin không | Certificate nằm trong JAR không có nghĩa trusted | So fingerprint ngoài băng, kiểm tra chain/issuer |
| Cosign không tìm signature | Image chưa ký, sai repo/digest hoặc registry không có signature | Kiểm tra release flow và image reference |
| Cosign identity/issuer mismatch | OIDC certificate không thuộc identity/issuer được policy chấp nhận | Kiểm tra expected identity/issuer; không nới policy tùy tiện |
| Image tag giống nhưng digest khác | Tag bị retag hoặc image rebuild | Verify/deploy theo digest, điều tra provenance |
| Signature hợp lệ nhưng image có CVE | Chữ ký không phải vulnerability scan | Scan SBOM, cập nhật dependencies/base |
| CI pass nhưng máy developer fail | Khác trust store, JDK/GPG/Cosign version hoặc keyring | Chuẩn hóa toolchain và verification metadata |
| Build pass khi cache còn, fail máy mới | Local cache che thiếu metadata/checksum/signature | Test clean environment và lưu trust metadata trong VCS |

### Quy tắc xử lý mismatch

**Không tự thêm checksum/key mới chỉ để bỏ qua lỗi.** Verification failure là sự kiện cần điều tra. Nếu publisher đổi artifact/version hoặc signing key, xác minh nguồn, lý do và thời điểm rồi mới cập nhật baseline có review.

## 12. Checklist theo từng công cụ

### Checksum file

- [ ] Dùng SHA-256 hoặc SHA-512.
- [ ] Expected digest đến từ release record/nguồn đã xác thực.
- [ ] Đúng artifact path/version/platform.
- [ ] Fail pipeline khi mismatch.
- [ ] Không tự ghi đè expected digest khi gặp lỗi.

### Gradle Dependency Verification

- [ ] Có gradle/verification-metadata.xml trong repository.
- [ ] Đã generate baseline cho configurations/plugins cần thiết.
- [ ] Review checksum entries.
- [ ] Xác minh trusted PGP fingerprints đầy đủ.
- [ ] Bật signature verification khi có signature và trust key phù hợp.
- [ ] Commit metadata/keyring vào version control.
- [ ] Có quy trình cập nhật khi dependency/plugin version đổi.
- [ ] Nhớ changing dependencies/local build outputs không thuộc phạm vi cơ chế này.

### Maven

- [ ] Repository checksum policy đặt fail khi cần enforcement.
- [ ] Không nhầm checksum policy với PGP signature verification.
- [ ] Release có .asc signature theo policy publish.
- [ ] Public key fingerprint được xác minh độc lập.
- [ ] Private key/passphrase được quản lý bằng agent/secret manager.
- [ ] Kiểm tra checksum/signature requirements mới nhất của repository đích.

### Java JAR

- [ ] Ký sau khi hoàn tất mọi thao tác sửa/repackaging.
- [ ] jarsigner -verify -strict chạy trong release validation.
- [ ] Không có unsigned entries ngoài ý muốn.
- [ ] Certificate chain, validity, algorithm và timestamp được kiểm tra.
- [ ] Fingerprint signer khớp nguồn tin cậy.

### OCI image

- [ ] Dùng image digest để xác định nội dung cần deploy.
- [ ] Cosign signature gắn với digest đó.
- [ ] Xác minh public key hoặc OIDC identity/issuer đúng policy.
- [ ] Kiểm tra provenance attestation nếu cần xác minh build process.
- [ ] Scan SBOM/vulnerability riêng.
- [ ] Lưu digest và verification result vào release record.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** SHA-256 khớp có chứng minh file do đúng publisher phát hành không?

**Trả lời:** Không. Nó chứng minh bytes khớp expected digest. Danh tính publisher cần signature và trusted key/identity.

**Câu 2.** Vì sao tải file và checksum từ cùng nguồn bị compromise là chưa đủ?

**Trả lời:** Attacker có thể thay cả hai. Cần checksum từ nguồn độc lập đã xác thực hoặc chữ ký gắn với key/identity đáng tin.

**Câu 3.** Gradle Dependency Verification lưu baseline ở đâu?

**Trả lời:** gradle/verification-metadata.xml trong project root; metadata được áp dụng cho build khi file tồn tại.

**Câu 4.** write-verification-metadata sha256,pgp có tự bảo đảm mọi dependency an toàn không?

**Trả lời:** Không. Nó bootstrap metadata từ artifacts đang resolve. Cần review checksum và trusted key fingerprints độc lập.

**Câu 5.** Maven checksumPolicy=fail có xác minh GPG signer không?

**Trả lời:** Không. Nó enforce checksum sidecar; PGP detached signature phải được xác minh riêng.

**Câu 6.** jarsigner -verify pass có chứng minh certificate thuộc đúng công ty không?

**Trả lời:** Chưa. Cần kiểm tra chain và so SHA-256 fingerprint với thông tin publisher công bố qua kênh tin cậy.

**Câu 7.** Vì sao nên dùng jarsigner -strict trong CI?

**Trả lời:** Vì một số severe warnings có thể được in nhưng không trở thành non-zero exit code nếu không bật strict; CI cần fail theo security policy.

**Câu 8.** OCI image digest và Cosign signature khác nhau thế nào?

**Trả lời:** Digest nhận diện nội dung image; signature xác thực signer và ràng buộc với digest. Digest một mình không chứng minh ai phát hành.

**Câu 9.** Cosign signature pass có chứng minh image không có CVE không?

**Trả lời:** Không. Cần SBOM/vulnerability scanning và remediation riêng.

**Câu 10.** Khi Gradle báo untrusted PGP key, có nên thêm key ID trong error vào trusted metadata ngay không?

**Trả lời:** Không. Xác minh full fingerprint qua nguồn publisher độc lập trước, rồi review việc thêm key.

## 14. Tài liệu chính thức

- Gradle — [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum, PGP signatures, trusted keys, bootstrap và metadata file.
- Apache Maven — [Settings Reference](https://maven.apache.org/settings.html): checksumPolicy ignore/warn/fail.
- Apache Maven — [Maven GPG Plugin](https://maven.apache.org/plugins/maven-gpg-plugin/): ký artifacts và POM bằng GnuPG.
- Apache Maven — [gpg:sign goal](https://maven.apache.org/plugins/maven-gpg-plugin/sign-mojo.html): phase/goal và best practices.
- Sonatype Central — [Publishing Requirements](https://central.sonatype.org/publish/requirements/): checksum files và GPG/PGP signatures.
- Oracle JDK 17 — [jarsigner Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html): ký/xác minh JAR, certificate chain, warnings và strict mode.
- Oracle JDK 17 — [keytool Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): fingerprint, certificate và keystore.
- Sigstore — [Cosign Signature Verification](https://docs.sigstore.dev/cosign/verifying/verify/): verify image signatures, digest claims và OIDC identity/issuer.

**Ghi nhớ:** Checksum trả lời **“bytes có khớp giá trị kỳ vọng không?”**; chữ ký trả lời **“ai đã ký dữ liệu này và key đó có được tin cậy không?”**. Gradle, Maven, JDK và Cosign hỗ trợ các lớp xác minh khác nhau. Một release đáng tin cần expected checksum/key identity có nguồn gốc rõ ràng, verification tự động trong CI, xử lý mismatch nghiêm túc và lưu digest/provenance để truy xuất lại.
