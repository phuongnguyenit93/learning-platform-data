# Phân biệt kiểm tra tính toàn vẹn, chữ ký và mức độ tin cậy của nhà phát hành

Trong kiến trúc Java runtime-extensibility, plugin có thể được tải từ kho artifact, mirror, Internet hoặc thư mục do đối tác cung cấp. Việc một file **plugin.jar tải về thành công**, thậm chí một file **có chữ ký mật mã hợp lệ**, chưa đủ căn cứ để host nạp class và thực thi. Host cần phân biệt ba câu hỏi:

1. **Tính toàn vẹn (integrity):** Byte của JAR có trùng với artifact được phê duyệt, tính theo một nguồn đối chiếu độc lập và đáng tin, hay đã bị sửa?
2. **Chữ ký số (digital signature):** File hoặc release metadata có chữ ký hợp lệ với khóa công khai xác định hay không? Khóa riêng tương ứng đã được dùng để ký dữ liệu trong phạm vi chữ ký chưa?
3. **Mức độ tin cậy và quyền phát hành (publisher trust/authorization):** Khóa, chứng chỉ hoặc danh tính đã kiểm tra ấy có thực sự thuộc nhóm publisher được **host** cho phép phát hành đúng plugin này không?

**Một chữ ký hợp lệ với một khóa lạ vẫn là chữ ký hợp lệ, nhưng không tạo ra niềm tin đối với nhà phát hành.** Một SHA-256 khớp với giá trị vừa tải từ cùng nguồn không đáng tin có thể không giúp chống việc đánh tráo. Ngay cả artifact của vendor được phép, được ký đúng, vẫn có thể chứa lỗi hoặc mã có hành vi nguy hiểm; xác thực artifact **không phải sandbox thực thi**.

Bài học tập trung vào ranh giới tin cậy giữa Java host và plugin bên ngoài. Ta tìm hiểu SHA-256, Ed25519, pinning, X.509, cơ chế signed JAR bằng jarsigner, tải và kiểm tra trước ClassLoader/ServiceLoader, cùng một ví dụ Java 17+ chạy được.

## 1. Mô hình ba tầng: integrity → signature → authorization

| Tầng | Thao tác | Nếu thành công, có thể nói gì? | Chưa thể khẳng định |
| --- | --- | --- | --- |
| **Integrity** | Tính SHA-256 của artifact và đối chiếu với digest mong đợi đã được bảo vệ | Byte đang nhận khớp với bản đã định danh bằng digest | Bản đó do ai phát hành hoặc có an toàn không |
| **Signature** | Kiểm tra chữ ký trên đúng dữ liệu bằng public key tương ứng | Dữ liệu chưa bị thay đổi trong phạm vi chữ ký và chữ ký hợp lệ với khóa kiểm tra | Public key có thuộc publisher đã được phép không |
| **Publisher trust** | Kiểm tra trusted key/certificate, identity, phạm vi plugin ID/version và chính sách thu hồi | Chủ thể đã xác thực được quyền cung cấp release ấy theo policy của host | Code sẽ không gây hại sau khi chạy |

Ví dụ:

- File JAR bị thay sau khi được ký, còn signature cũ: chữ ký sẽ không khớp dữ liệu. Đây là **SIGNATURE_INVALID**.
- Kẻ tấn công tự sinh keypair, ký JAR của họ và phát luôn public key: phép toán Signature.verify có thể trả true, nhưng **SIGNER_NOT_TRUSTED**.
- Nhà phát hành A được phép ký plugin A nhưng cố phân phối plugin ID của B: danh tính A có thể xác thực hợp lệ, song **PUBLISHER_NOT_AUTHORIZED** cho plugin B.
- Publisher được phép ký một bản có lỗ hổng: cả ba tầng có thể đạt, nhưng cần chính sách review, cập nhật, giới hạn quyền và thu hồi bản phát hành.

Không nên dồn mọi kết quả vào một Boolean tên isValid không có giải thích. Một verifier thực tế thường cần phân biệt kết quả **hashMismatch**, **signatureInvalid**, **unknownSigner**, **certificateInvalid**, **releaseNotAllowed** và **verified**. Những tên này là ví dụ về thiết kế ứng dụng, không phải enum của JDK.

## 2. Phân tích mối đe dọa ở biên plugin

Một luồng nạp plugin thường như sau:

~~~text
Publisher / repository / CDN
             |
             | download JAR + metadata / signature
             v
      Untrusted staging area
             |
             | integrity, signature, signer trust,
             | authorization, dependency digests
             v
    Verified immutable artifact
             |
             | create ClassLoader / ModuleLayer
             v
      ServiceLoader / instantiate
             |
             | prepare / activate
             v
          Runtime plugin
~~~

Những điểm tấn công khác nhau:

1. **Sửa file trên đường truyền hoặc kho:** checksum đáng tin cậy và chữ ký phát hiện sự khác biệt với release được chấp nhận.
2. **Thay cả file và checksum:** nếu hai thứ đều đến từ một nơi chưa được bảo vệ, kẻ tấn công có thể tạo checksum mới. Cần chuỗi tin cậy cho **giá trị checksum được kỳ vọng**.
3. **Mạo danh publisher:** chữ ký với khóa tự tạo vẫn xác minh thành công. Cần trust anchor, khóa đã pin hoặc certificate chain cộng publisher policy.
4. **Dùng chứng chỉ đúng nhưng sai phạm vi:** nhà phát hành có thể có quyền ký sản phẩm này, không có quyền ký plugin ID khác.
5. **Thay file sau khi xác minh:** kẻ tấn công thay JAR ở đường dẫn cũ trước khi ClassLoader đọc, gây lỗi time-of-check/time-of-use.
6. **Mã xấu vẫn được ký bởi khóa được tin:** key có thể bị lộ, vendor có thể sai sót hoặc cố tình phát hành mã nguy hiểm. Signature không hạn chế file, network, CPU, thread hoặc native library khi plugin chạy.

Điểm quyết định: **đừng dùng class initialization, constructor hoặc ServiceLoader provider instance để xác minh độ tin cậy của JAR chưa được kiểm tra**. Những bước này đã có thể thực thi mã. Đầu tiên nên xác thực artifact ở dạng byte, không thực thi.

## 3. Integrity: đối chiếu SHA-256 có nguồn tham chiếu tin cậy

SHA-256 chuyển byte thành một digest dài 256 bit. Để kiểm tra plugin tải về, host tính digest của **đúng byte file** và so với digest được hệ thống tin cậy. Nếu file khác, digest sẽ khác trừ những trường hợp va chạm mật mã cực kỳ khó xảy ra đối với SHA-256.

### 3.1. Một checksum từ cùng nguồn không đủ làm bằng chứng

Giả sử endpoint không tin cậy trả về cùng lúc:

~~~text
analytics.jar
analytics.jar.sha256
~~~

Nếu endpoint bị kiểm soát, đối thủ có thể thay cả JAR và .sha256. Lệnh tính SHA-256 vẫn thấy “khớp”, nhưng **không có điểm neo tin cậy độc lập**. Giải pháp gồm: digest lấy từ signed release manifest đã xác minh, digest do quản trị viên phê duyệt, hoặc kho dữ liệu được bảo vệ bởi quy trình thay đổi riêng.

Hash của một artifact do người gửi tự cung cấp vẫn hữu ích để phát hiện lỗi truyền tải, nhưng **không phải bằng chứng về danh tính nhà phát hành**.

### 3.2. Cần hash đúng byte, không hash tên file

Với SHA-256 trên JAR:

- Dùng byte nguyên bản của artifact. Không chuẩn hóa newline, giải nén rồi nén lại, sửa ZIP timestamp hoặc sắp xếp entry trước khi tính hash toàn file.
- Hash phải ràng buộc đúng plugin ID/version/artifact mà host định dùng; đừng chấp nhận một digest hợp lệ của **release khác**.
- Java cung cấp MessageDigest.getInstance("SHA-256") và MessageDigest.isEqual để đối chiếu digest dạng byte.
- Với file lớn, nên đọc theo stream, giới hạn kích thước tải và chỉ đưa dữ liệu đã xác minh vào kho artifact bất biến.
- ZIP CRC-32 giúp phát hiện hỏng dữ liệu ngẫu nhiên, nhưng **CRC-32 không được thiết kế để chống đối thủ chủ động**.
- Nếu mismatch, fail closed; không tự đổi digest expected thành digest mới quan sát được.

Đoạn minh họa đặt trong method có jarPath và trustedDigest (byte[]) đã tồn tại:

~~~java
byte[] content = java.nio.file.Files.readAllBytes(jarPath);
byte[] currentDigest = java.security.MessageDigest
        .getInstance("SHA-256").digest(content);
boolean intact = java.security.MessageDigest.isEqual(
        trustedDigest, currentDigest);
~~~

Đây **không phải class Java độc lập**; nó mô tả phép kiểm tra. Files.readAllBytes chỉ hợp lý với artifact đã được giới hạn kích thước. Trong production, có thể hash tuần tự theo stream để tránh đọc toàn JAR vào heap.

### 3.3. SHA-256 không có thông tin người ký

SHA-256 chỉ cho một dấu vân tay dữ liệu, không chứa chứng chỉ, private key hay danh tính. Bất kỳ ai có file cũng có thể tính SHA-256 của nó. Khi digest được bảo vệ bằng chữ ký của trusted publisher, chính **chữ ký lên manifest** mới giúp gắn digest với nguồn phát hành, không phải bản thân hàm hash.

Đừng xem việc hai lần tải có cùng checksum là bằng chứng không có mã độc. Nếu cả hai lần đều nhận đúng một bản đã bị đưa vào kho từ trước, giá trị vẫn trùng.

## 4. Digital signature: xác minh phép ký, không tự cấp quyền cho signer

Khi ký số, signer dùng **private key** để tạo chữ ký cho một byte sequence; verifier dùng **public key** để kiểm tra.

~~~text
Publisher:
  bytes(JAR) + private key → sign → signature

Host:
  bytes(JAR) + signature + public key → verify → true / false
~~~

Đối với Ed25519 (có trong API mật mã của JDK 17), Java dùng KeyPairGenerator.getInstance("Ed25519") và Signature.getInstance("Ed25519"). Nếu JAR đổi byte sau khi ký nhưng giữ signature cũ, phép verify phải từ chối.

**Giới hạn của kết quả true:** verify chứng minh signature hợp lệ với public key đã dùng để kiểm tra, nhưng **không tự chứng minh public key là của vendor mà host cho phép**. Nếu host nhận cả public key và JAR từ một request chưa đáng tin, đối thủ hoàn toàn có thể tạo keypair của họ, ký file và đưa public key của họ. Verify vẫn true.

Để tiến thêm một bước, cần xác thực public key bằng:

- **Key pinning:** host được cấp trước public key hoặc fingerprint của signer cho phép, từ cấu hình quản trị đáng tin cậy.
- **X.509/certificate validation:** kiểm tra chuỗi chứng chỉ tới trust anchor được chấp nhận, thời gian hiệu lực, mục đích sử dụng, revocation và danh tính phù hợp.
- **Signed release metadata:** một manifest được ký ràng buộc plugin ID, version, artifact digest và signer identity.

Không lấy “key trusted” từ metadata chưa xác minh trong **chính JAR đang được đánh giá**. Một trust anchor do đối thủ tự đề xuất không bảo đảm điều gì.

### 4.1. Ký cái gì thì bảo vệ cái đó

Chữ ký chỉ bảo vệ **phạm vi dữ liệu đã ký**. Nếu signature bao phủ plugin.jar nhưng file plugin-permissions.json ở bên cạnh không được ký, host không thể suy ra permission metadata cũng không bị sửa.

Hai mô hình phổ biến:

1. **Detached whole-artifact signature:** chữ ký tách rời bao phủ byte toàn bộ JAR; thay đổi bất kỳ byte nào trong archive sẽ làm chữ ký trên toàn file thất bại.
2. **Signed release manifest:** chữ ký bao phủ manifest gồm digest của JAR, các dependency, config quan trọng và metadata. Host xác minh manifest rồi lần lượt xác minh digest của từng artifact.

Cơ chế **JAR signing tích hợp với jarsigner** khác hai mô hình trên ở chi tiết về manifest, signature file và các entry được ký. Không được nhầm việc ký những entry được liệt kê với ký nguyên byte container ZIP.

### 4.2. Key possession khác danh tính và sự an toàn

Một publisher lạ vẫn có thể tạo **chữ ký hợp lệ bằng khóa của chính họ**. Đây không phải “phá” mật mã. Ngược lại, một attacker đánh cắp private key của publisher tin cậy cũng có thể tạo chữ ký toán học hợp lệ. Vì vậy:

- Verification xác nhận đặc tính mật mã của byte sequence và khóa.
- Publisher trust quyết định khóa/cert thuộc danh sách được chấp nhận.
- Authorization quyết định signer đó được publish plugin ID/capability nào.
- Security review, sandbox và giám sát xử lý các vấn đề **hành vi code**, nằm ngoài bản thân signature.

## 5. Publisher trust: từ khóa được nhận diện tới quyền phát hành

Một host có thể có nhiều vendor. Nên duy trì policy tách rời artifact, ví dụ:

~~~text
TrustedPublisherPolicy
  publisherId: vendor-alpha
  publicKeyFingerprint: giá trị lấy từ quy trình cấp khóa đáng tin
  permittedPluginIds: com.example.analytics, com.example.reports
  permittedCapabilities: read:catalog
  minimumAllowedVersion: phiên bản theo policy
  revokedVersions: danh sách version bị thu hồi
  enabled: true
~~~

Khối trên là **sơ đồ policy**, không phải file cấu hình có thể chạy ngay. Trong triển khai thật, khóa/fingerprint và danh sách quyền phải được lấy từ hệ quản trị đã xác thực, không từ chính plugin tự khai.

Chuỗi xác thực có thể là:

~~~text
received JAR + signature
          |
          v
cryptographic signature valid?
          |
          v
signing key/certificate recognized?
          |
          v
publisher authorized for requested plugin ID/version?
          |
          v
all release artifacts and capabilities approved?
          |
          v
may proceed to controlled loading
~~~

Nếu một trong những bước bắt buộc thất bại, không nên tiếp tục class-load. Với certificate chain, “một CA đã ký certificate này” chỉ hỗ trợ xác thực chủ thể theo trust policy; nó **không** tự cấp quyền phát hành mọi plugin. Một chủ thể có chứng chỉ code-signing hợp lệ vẫn có thể không thuộc đối tác của hệ thống.

### 5.1. Bản đồ quyết định

| Tình huống | Hash theo nguồn đáng tin | Signature | Publisher policy | Quyết định |
| --- | --- | --- | --- | --- |
| Đúng release được phê duyệt | Khớp | Hợp lệ | Được phép | Cho phép chuyển sang bước nạp |
| JAR bị sửa sau ký | Không khớp | Không hợp lệ với signature cũ | Không cần xét tiếp | Từ chối |
| JAR do khóa lạ ký | Không nhất thiết có digest approved | Hợp lệ với khóa lạ | Không được phép | Từ chối |
| Vendor A ký plugin ID của B | Có thể khớp metadata do A công bố | Hợp lệ với A | A không được phép phát hành B | Từ chối |
| Release cũ có lỗ hổng, bị revoke | Có thể khớp | Có thể hợp lệ | Release bị từ chối | Từ chối |
| Release hợp lệ nhưng plugin có bug | Khớp | Hợp lệ | Có thể được phép | Vẫn cần kiểm soát runtime |

Một policy tốt không chỉ lưu danh sách “khóa có chữ ký đúng”, mà còn có **phạm vi và thời điểm**: publisher nào, plugin ID nào, version nào, quyền nào, ngày hiệu lực và trạng thái thu hồi.

## 6. Ví dụ Java 17 chạy được: SHA-256, Ed25519 và pinned signer

Ví dụ tự tạo **hai JAR dạng byte thật** bằng JarOutputStream, sinh **hai cặp khóa Ed25519**, ký và kiểm tra:

- **original:** archive chứa plugin-v1, ký bằng trusted private key.
- **modified:** archive chứa plugin-v2, khác byte bản đã được kiểm tra.
- **unknown:** một bên không được chấp nhận tự ký archive modified bằng private key của mình. Chữ ký của họ vẫn hợp lệ nếu dùng chính public key của họ.
- **approved:** phép kiểm tra giả lập của host yêu cầu **khóa signer khớp pinned public key** và signature hợp lệ trên byte JAR.

Ví dụ **không ký JAR theo định dạng jarsigner**, mà dùng detached Ed25519 signature bao phủ byte của toàn JAR. Mục tiêu là minh bạch hóa ba loại kiểm tra, không phải thực hiện X.509/PKIX hoặc logic ký JAR entry.

**Quan trọng:** ví dụ sinh trusted keypair trong bộ nhớ để chạy độc lập, nên nó chỉ mô phỏng key pinning. Với sản phẩm thật, signer private key phải ở phía nhà phát hành; host nhận trusted public key trước đó qua provisioning độc lập và không tự tạo khóa “trusted” từ artifact lạ.

### 6.1. File PluginTrustDemo.java

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;

public final class PluginTrustDemo {
    private static byte[] jarBytes(String content) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (JarOutputStream jar = new JarOutputStream(buffer)) {
            JarEntry entry = new JarEntry("plugin.txt");
            entry.setTime(0L);
            jar.putNextEntry(entry);
            jar.write(content.getBytes(StandardCharsets.UTF_8));
            jar.closeEntry();
        }
        return buffer.toByteArray();
    }

    private static byte[] digest(byte[] content) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(content);
    }

    private static byte[] sign(byte[] content, PrivateKey key)
            throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key);
        signer.update(content);
        return signer.sign();
    }

    private static boolean verify(byte[] content, byte[] signature,
                                  PublicKey key) throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(content);
        return verifier.verify(signature);
    }

    private static boolean approved(byte[] content, byte[] signature,
                                    PublicKey claimedKey,
                                    PublicKey pinnedKey) throws Exception {
        boolean knownKey = MessageDigest.isEqual(
                claimedKey.getEncoded(), pinnedKey.getEncoded());
        return knownKey && verify(content, signature, pinnedKey);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair trusted = generator.generateKeyPair();
        KeyPair unknown = generator.generateKeyPair();

        byte[] original = jarBytes("plugin-v1");
        byte[] modified = jarBytes("plugin-v2");
        byte[] approvedDigest = digest(original);
        byte[] trustedSignature = sign(original, trusted.getPrivate());
        byte[] unknownSignature = sign(modified, unknown.getPrivate());

        System.out.println("hash.original=" +
                MessageDigest.isEqual(approvedDigest, digest(original)));
        System.out.println("hash.modified=" +
                MessageDigest.isEqual(approvedDigest, digest(modified)));
        System.out.println("signature.original=" +
                verify(original, trustedSignature, trusted.getPublic()));
        System.out.println("signature.modified=" +
                verify(modified, trustedSignature, trusted.getPublic()));
        System.out.println("signature.unknownOwnKey=" +
                verify(modified, unknownSignature, unknown.getPublic()));
        System.out.println("publisher.unknownTrusted=" +
                MessageDigest.isEqual(unknown.getPublic().getEncoded(),
                        trusted.getPublic().getEncoded()));
        System.out.println("policy.original=" +
                approved(original, trustedSignature,
                        trusted.getPublic(), trusted.getPublic()));
        System.out.println("policy.modified=" +
                approved(modified, trustedSignature,
                        trusted.getPublic(), trusted.getPublic()));
        System.out.println("policy.unknown=" +
                approved(modified, unknownSignature,
                        unknown.getPublic(), trusted.getPublic()));
    }
}
~~~

Code dùng KeyPairGenerator, MessageDigest và Signature từ java.base của JDK 17, không cần dependency bên ngoài. JarOutputStream thực sự tạo archive; entry plugin.txt chứa dữ liệu mô phỏng, nên ta không nạp mã chưa được xác minh.

### 6.2. Biên dịch, chạy và stdout chính xác

Trong thư mục có **PluginTrustDemo.java**, dùng JDK 17 hoặc mới hơn:

~~~powershell
javac --release 17 -encoding UTF-8 PluginTrustDemo.java
java PluginTrustDemo
~~~

Lệnh tương đương trên Linux/macOS khi có javac/java. Chương trình không ghi private key ra đĩa.

**Stdout được kiểm chứng bằng biên dịch/chạy thực tế:**

~~~text
hash.original=true
hash.modified=false
signature.original=true
signature.modified=false
signature.unknownOwnKey=true
publisher.unknownTrusted=false
policy.original=true
policy.modified=false
policy.unknown=false
~~~

### 6.3. Phân tích từng kết quả

- **hash.original=true:** digest hiện tại của original trùng digest được tính trước từ original.
- **hash.modified=false:** modified chứa plugin-v2, không còn khớp digest của plugin-v1.
- **signature.original=true:** byte original khớp chữ ký tạo bởi trusted private key.
- **signature.modified=false:** byte modified không tương ứng với chữ ký gốc.
- **signature.unknownOwnKey=true:** một người lạ hoàn toàn có thể tạo chữ ký hợp lệ bằng khóa riêng của họ. **Không phải giả mạo chữ ký trusted**.
- **publisher.unknownTrusted=false:** public key unknown không phải pinned key của host.
- **policy.original=true:** pinned key trùng signer key và signature đúng.
- **policy.modified=false:** chữ ký gốc không còn hợp lệ sau khi byte JAR bị thay.
- **policy.unknown=false:** chữ ký của unknown đúng với key unknown, nhưng chưa đạt bước trust.

Code chỉ dùng hai khóa do ví dụ tự tạo và một pin giả lập. Trong hệ thống thật, approved còn phải ràng buộc đúng **plugin ID**, **publisher identity**, **release policy**, **dependency set**, thời gian/thu hồi chứng chỉ nếu dùng X.509 và snapshot artifact được nạp. Không xem hàm này là một product-ready verifier.

## 7. Phân biệt detached signature với ký JAR bằng jarsigner

**Detached signature** như ở mục 6 ký một byte sequence rõ ràng, ví dụ toàn bộ file plugin.jar. Thay đổi bất kỳ byte nào trong phạm vi đã ký khiến signature không còn phù hợp.

Ngược lại, **signed JAR của Java** theo JAR File Specification dùng cấu trúc trong META-INF:

~~~text
META-INF/MANIFEST.MF
META-INF/<SIGNER>.SF
META-INF/<SIGNER>.RSA hoặc block chữ ký tương ứng
~~~

<SIGNER> ở đây chỉ là **ký hiệu tên file được công cụ tạo**, không phải tên thật. Tùy thuật toán/tooling, signature block có thể dùng các tên khác, như .DSA hoặc .EC.

Theo mô hình JAR signing:

1. MANIFEST.MF có digest của các JAR entry liên quan.
2. File .SF chứa digest của manifest hoặc phần manifest liên quan.
3. Signature block xác nhận chữ ký mật mã của file .SF.
4. Verifier dùng chuỗi này để kiểm tra những **entry được ký** đã bị thay hay chưa.

Đây là xác minh theo **entry và metadata được ký**, không đơn giản là ký mọi byte ZIP theo một hàm Signature.update(allBytes). Nếu một entry mới được thêm vào sau khi ký mà nó không nằm trong tập entry được chữ ký ban đầu bao phủ, chữ ký trên các entry cũ có thể vẫn xác minh thành công. Vì thế, cần chính sách **unsigned entry** rõ ràng.

### 7.1. Lệnh jarsigner để kiểm tra

Khi đã có một JAR được ký thật, dùng:

~~~powershell
jarsigner -verify -verbose -certs -strict plugin.jar
~~~

- **-verify** kiểm tra chữ ký.
- **-verbose** liệt kê thêm trạng thái entry.
- **-certs** hiển thị thông tin chứng chỉ.
- **-strict** yêu cầu xử lý nghiêm các cảnh báo nặng, có thể làm exit code khác 0 khi chain không được xác thực, certificate self-signed, unsigned entry hoặc thuật toán bị từ chối.

Không có stdout cố định cho lệnh này: kết quả phụ thuộc JAR, signer, truststore, certificate chain, timestamp và JDK đang chạy. **Chỉ thấy “jar verified” hoặc chỉ thấy file .SF không có nghĩa publisher đã được host chấp nhận.**

Lệnh jarsigner có thể kiểm tra chữ ký bằng certificate được mang bên trong JAR. Nếu certificate đó **tự ký** hoặc chain không được trust theo policy, việc ký hợp lệ về mặt mật mã không tự chứng minh nguồn tin cậy. Khi dùng keystore/truststore cụ thể, còn phải xác nhận alias/signer tương ứng với **đúng publisher được phép**.

### 7.2. Kiểm tra theo Java JarFile API

JarFile có chế độ xác minh đối với JAR đã ký. Nhưng **mở JAR hoặc liệt kê entry không chứng minh đã xác minh nội dung tất cả entry**. Cơ chế xác minh digest thường diễn ra khi entry data thực sự được đọc; để đánh giá signer metadata cho entry, cần bảo đảm dữ liệu entry đã được tiêu thụ và kiểm tra.

Trước khi dùng signer của một entry làm quyết định, host cần phân biệt:

- Entry có CodeSigner/certificate tương ứng với chính sách.
- Entry không có signer, dù JAR có một số entry khác đã ký.
- Entry có signer hợp lệ nhưng signer đó không được host cấp quyền.
- Entry hỏng hoặc digest mismatch trong lúc đọc.
- Dependency hoặc file config nằm **ngoài JAR** không thuộc chữ ký của JAR.

Việc đọc và xác minh entry không thay thế đường kiểm tra **PKIX trust**, whitelist hoặc plugin authorization riêng của host. Nếu hệ thống yêu cầu toàn bộ class/resource đều được ký, phải kiểm tra **coverage trên những entry được thực sự sử dụng**, không chỉ sự hiện diện của metadata chữ ký.

### 7.3. Không đánh đồng JAR signing với JAR có thể tin cậy tuyệt đối

Một JAR được signed đúng vẫn có thể do bất cứ cá nhân nào ký bằng keypair của họ. Một JAR có signer được công nhận vẫn có thể là bản phát hành chứa mã độc, backdoor hoặc bug. Một entry mới chưa được ký cũng không trở thành đáng tin chỉ vì JAR vẫn giữ signature block của entry cũ.

Cách chính xác là xác minh **chữ ký** trước, xác thực **signer/trust anchor**, kiểm tra **phạm vi ký và release policy**, sau đó mới quyết định có cấp quyền nạp hay không.

## 8. X.509, PKIX và code-signing certificate: các bước khác chữ ký

Nếu bên phát hành dùng chứng chỉ X.509, cần nhiều kiểm tra bổ sung so với Signature.verify:

| Kiểm tra | Mục tiêu | Nếu thiếu |
| --- | --- | --- |
| Chữ ký dữ liệu | Chữ ký thật sự hợp lệ trên dữ liệu được bảo vệ | Có thể chấp nhận file bị thay |
| Chain validation | Certificate dẫn đến trust anchor được phép | Tin certificate tự ký từ người lạ |
| Validity | Chứng chỉ hợp lệ theo chính sách thời gian | Chấp nhận chứng chỉ hết hạn hoặc chưa có hiệu lực |
| Revocation | Chứng chỉ/khóa không bị thu hồi theo policy | Tin khóa đã bị vô hiệu hóa |
| KeyUsage / ExtendedKeyUsage | Certificate phù hợp mục đích ký mã nếu policy yêu cầu | Dùng sai loại certificate |
| Identity binding | Danh tính được xác nhận tương ứng đúng vendor | Đánh tráo Subject/CN tự khai |
| Publisher authorization | Vendor được cấp quyền phát hành đúng plugin ID/capability | Một cert hợp lệ được dùng để ký mọi plugin |

**Tên Subject/CN trên certificate không đủ** để xác thực nhà phát hành. Xác minh chữ ký bằng public key lấy ra từ certificate cũng không đủ: phải kiểm tra certificate chain/trust anchor và chính sách danh tính.

Việc kiểm tra thu hồi có thể cần CRL, OCSP hoặc nguồn trạng thái khóa riêng; không phải mọi lời gọi verify đều tự làm điều đó. Khi thông tin revocation không thể lấy được, ứng dụng phải định nghĩa hành vi fail-closed/fail-open một cách có chủ ý, theo yêu cầu bảo mật.

**Trusted timestamp** có thể giúp xem xét thời điểm ký so với thời gian hiệu lực của chứng chỉ, nhưng timestamp không tự hợp thức hóa chữ ký sai hoặc một publisher không được phép. Timestamp authority và thông tin liên quan cũng cần được xác thực.

**Truststore** không tương đương danh sách plugin publisher. Ngay cả một chứng chỉ có chain tin cậy theo PKIX cũng chưa chắc được cấp quyền phát hành com.example.analytics. Host vẫn phải liên hệ danh tính signer với **plugin ID**, version và quy tắc phát hành.

## 9. Bảo vệ metadata và dependency ngoài JAR

Một plugin package có thể có cấu trúc:

~~~text
release/
  manifest.json
  manifest.sig
  plugin.jar
  lib/dependency-a.jar
  lib/dependency-b.jar
  config/plugin.properties
~~~

Chỉ ký plugin.jar trong khi host tự động tải dependency từ một URL không kiểm soát sẽ để hở ranh giới. Một bản phát hành có thể ràng buộc:

- Plugin ID và version.
- Publisher identity, signing key ID/chain.
- SHA-256 của plugin.jar.
- SHA-256 của từng dependency JAR.
- SHA-256 của resource/config ảnh hưởng đến cách plugin chạy.
- Chính sách capability / minimum version / revoke.
- Thời gian hoặc metadata build/provenance nếu cần.

Sau khi xác minh chữ ký của manifest từ publisher được phép, host tính SHA-256 của **từng file** rồi so sánh. Mọi file có thể thay đổi hành vi khi nạp hoặc kích hoạt đều cần được bao phủ bởi policy phù hợp.

Một cấu trúc manifest minh họa, **không phải artifact đã ký thật**:

~~~json
{
  "pluginId": "com.example.analytics",
  "version": "2.4.1",
  "publisherId": "vendor-alpha",
  "artifacts": [
    {"path": "plugin.jar", "digestAlgorithm": "SHA-256"},
    {"path": "lib/dependency-a.jar", "digestAlgorithm": "SHA-256"}
  ]
}
~~~

Ở đây không có giá trị digest thật, nên JSON chỉ thể hiện trường metadata cần thiết; **không dùng nó để xác minh production**. Manifest thật phải chứa digest hợp lệ, được ký trên biểu diễn byte đã được quy định rõ (đảm bảo nhất quán canonicalization), và host phải kiểm tra cả chữ ký của manifest lẫn từng artifact.

Ngoài chữ ký/digest, việc giải nén ZIP/JAR cần kiểm soát traversal, symlink, entry trùng tên và các giới hạn kích thước. Chữ ký hợp lệ không tự biến thao tác extract thành an toàn.

## 10. Thứ tự xác minh trước ClassLoader và ServiceLoader

Khuyến nghị cho plugin manager:

1. **Tải về staging:** chưa nạp class; chặn file quá lớn, tên/path không hợp lệ và trộn lẫn request.
2. **Lấy release record từ nguồn đáng tin:** xác định plugin ID/version và danh tính publisher được kỳ vọng theo policy host.
3. **Kiểm SHA-256:** đối chiếu đúng byte của artifact với digest được bảo vệ; thất bại thì dừng.
4. **Xác minh chữ ký:** dùng đúng thuật toán, đúng dữ liệu và signer key đã được kiểm tra.
5. **Kiểm signer trust:** pin, certificate chain, revocation/timestamp/validity theo môi trường.
6. **Kiểm authorization:** publisher được phép ký đúng plugin ID/version/capability? Artifact/dependency nào bị thu hồi?
7. **Cố định byte đã xác minh:** đưa snapshot vào vùng immutable hoặc content-addressed path.
8. **Chỉ sau đó tạo loader/module layer và provider:** duyệt SPI, gọi constructor, prepare/activate theo vòng đời plugin.
9. **Theo dõi trong runtime:** audit, giới hạn quyền và cơ chế vô hiệu hóa plugin khi có security advisory.

Nếu không xác minh được một điều kiện bắt buộc, **fail closed** thay vì “thử nạp xem có chạy không”.

### 10.1. Tránh time-of-check/time-of-use (TOCTOU)

Một thứ tự nguy hiểm:

~~~text
verify /tmp/plugin.jar
         |
         | process khác ghi đè file
         v
new URLClassLoader(/tmp/plugin.jar)
         |
         v
execute altered plugin
~~~

Ngay cả khi phép verify ban đầu hoàn hảo, hệ thống có thể thực thi **file khác** nếu đường dẫn sau đó bị thay. Biện pháp giảm rủi ro:

- Staging directory có quyền truy cập chặt, không cho tác nhân chưa được phép ghi đè.
- Snapshot byte được kiểm tra và xuất bản thành artifact bất biến.
- Sử dụng content-addressed storage hoặc tên lưu gắn digest có bảo vệ chống thay đổi.
- Tạo loader từ **chính artifact được xác minh** và kiểm tra dependency riêng.
- Không tự động dùng lại một path có thể bị sửa giữa lượt kiểm tra và lượt load.

Đừng xem một **tên file giống hệt** là bằng chứng file đó vẫn chứa byte đã kiểm.

### 10.2. ClassLoader không là sandbox và có thể khởi chạy mã khi nạp

Việc phân loader giúp tách namespace class/dependency, không tự giới hạn quyền file/network hoặc hoạt động của code. Constructor, class static initialization, provider factory hoặc ServiceLoader.Provider.get() có thể thực thi mã. Bởi vậy, không nên dựa trên **lời tự khai từ một instance plugin chưa tin cậy** để quyết định plugin đó có được tin hay không.

Sau khi artifact đã được chấp nhận, host vẫn phải quản lý quyền của plugin, tài nguyên, timeout, vòng đời stop/close và cách dỡ bỏ tham chiếu khi reload.

## 11. HTTPS và provenance là các lớp hỗ trợ, không thay thế ba phép kiểm tra

HTTPS bảo vệ kết nối tới endpoint đang được xác thực, nhưng không giải quyết trường hợp chính kho artifact bị chiếm quyền, file bị upload nhầm hoặc quyền quản trị kho bị lạm dụng. Chữ ký release cho phép kiểm tra nguồn phát hành độc lập với đường truyền.

Một **SBOM** cho biết danh sách thành phần được khai báo; nó không tự xác thực danh tính publisher hay chứng minh các thành phần không có lỗ hổng. Một build provenance/attestation có chữ ký có thể làm rõ pipeline sản xuất artifact, nhưng signature của provenance cũng cần được xác minh với danh tính/niềm tin đúng và ràng buộc đúng byte artifact đang triển khai.

Không quy các bằng chứng này thành “artifact an toàn tuyệt đối”. Chúng giúp kiểm soát chuỗi cung ứng, review và điều tra sự cố nhưng vẫn cần chính sách về runtime capability.

## 12. Quản lý khóa, thu hồi và chống downgrade

### 12.1. Key rotation

Một thiết kế pinning tốt phải có quy trình đổi khóa:

1. Tạo khóa mới tại môi trường đáng tin, bảo vệ private key (KMS/HSM hoặc quy trình tương đương).
2. Công bố public key mới qua kênh quản trị được xác thực; không tin key vừa đến từ JAR chưa kiểm tra.
3. Quy định thời gian hiệu lực và phạm vi release được ký với khóa cũ/mới.
4. Audit các thay đổi truststore/policy, tránh cập nhật pin âm thầm.
5. Thu hồi khóa cũ khi hết hiệu lực hoặc có sự cố; không chấp nhận chữ ký cũ cho release bị cấm theo policy.

### 12.2. Chữ ký đúng không phát hiện private key bị đánh cắp

Nếu attacker có private key thực sự của vendor, họ có thể tạo chữ ký hợp lệ với **chính pinned public key**. Phép toán verify không thể phân biệt người ký hợp pháp với người dùng khóa bị đánh cắp. Khi có sự cố, phải có chính sách revocation/release approval độc lập, giám sát hệ thống ký, kiểm soát quyền phát hành, quy trình đóng băng và thu hồi plugin.

Chữ ký có timestamp đáng tin hỗ trợ đánh giá thời điểm ký theo policy, nhưng không tự loại bỏ yêu cầu phản ứng sự cố.

### 12.3. Rollback và version

Một bản cũ có thể vẫn được ký đúng nhưng chứa lỗ hổng. Hệ thống cần minimum accepted version, danh sách release bị thu hồi, hoặc sự phê duyệt rõ ràng cho rollback. Không dùng so sánh chuỗi thuần túy để quyết định thứ tự version nếu semantic version không được chuẩn hóa; nên dùng parser/version policy nhất quán.

Nếu một artifact bị thu hồi sau khi đã được nạp, hệ thống còn cần xử lý **đang chạy**: ngừng routing, dừng plugin, đóng tài nguyên, giải phóng loader khi có thể và cập nhật audit. Chỉ từ chối tải lần sau có thể chưa đủ.

## 13. Các ngộ nhận phổ biến

| Ngộ nhận | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| “SHA-256 khớp với .sha256 cùng URL, vậy chắc chắn an toàn.” | Kẻ tấn công có thể thay cả hai | Bảo vệ hash expected bằng signed manifest/kênh tin cậy |
| “Chữ ký đúng nghĩa là nhà phát hành đáng tin.” | Người lạ cũng tự ký với khóa của họ được | Pin key hoặc xác thực certificate chain + policy |
| “Subject/CN đúng tên vendor thì hợp lệ.” | Tên trong cert chưa đủ chứng minh chain/identity | PKIX validation, kiểm trust anchor và identity |
| “jarsigner báo verified là đủ để nạp.” | Nó không tự biết publisher được cấp quyền cho plugin ID nào | Kiểm signer trust và release authorization |
| “Có file META-INF/*.SF nghĩa là mọi entry đã được ký.” | Signature file có thể hỏng; một số entry có thể unsigned | Kiểm signature và signer coverage |
| “Mọi signer có CA-trusted cert đều được publish plugin.” | Tin CA khác quyền phát hành trong hệ thống | Map identity → plugin ID/version/capability |
| “Certificate chưa hết hạn thì chắc chưa bị thu hồi.” | Expiration và revocation là hai trạng thái riêng | Kiểm revocation theo policy |
| “ClassLoader riêng làm mã không đáng tin trở nên an toàn.” | Plugin vẫn có thể dùng quyền của tiến trình host | Least privilege, process isolation khi cần |
| “Kiểm xong rồi nạp lại cùng path là đúng byte.” | File có thể bị đổi sau kiểm tra | Immutable snapshot hoặc path bất biến |
| “Artifact được ký nên không thể chứa lỗ hổng.” | Chữ ký không phân tích logic code | Review, scanning, monitoring và revocation |

## 14. Test suite cho plugin verifier

Cần thử cả trường hợp đạt và không đạt:

| Test | Kỳ vọng |
| --- | --- |
| Artifact đúng, signer được phê duyệt, version hợp lệ | ACCEPT sau tất cả điều kiện |
| Thay byte trong JAR, giữ chữ ký cũ | HASH_MISMATCH hoặc SIGNATURE_INVALID |
| Thay signature bằng dữ liệu ngẫu nhiên | SIGNATURE_INVALID |
| Ký JAR khác bằng một keypair mới | Signature có thể hợp lệ với key mới nhưng REJECT signer |
| Cùng vendor ký nhầm plugin ID không được phép | PUBLISHER_NOT_AUTHORIZED |
| Certificate self-signed không được pin | REJECT signer |
| Certificate bị revoke/hết hạn theo policy | REJECT theo quy tắc hiệu lực |
| Entry mới không được ký trong JAR có chữ ký entry cũ | REJECT nếu policy yêu cầu coverage đầy đủ |
| Dependency JAR đổi byte so với signed release manifest | REJECT vì digest khác |
| Release version cũ đã bị rút | REJECT ngay cả khi signature cũ còn hợp lệ |
| File bị đổi giữa verify và load | Không được nạp nội dung mới |
| Lỗi mạng, lỗi đọc, khóa không tìm thấy, thông tin trust không rõ | FAIL CLOSED khi điều kiện bắt buộc chưa thể xác minh |
| Artifact có signature đúng nhưng yêu cầu capability vượt quyền | Từ chối cấp quyền hoặc nạp theo policy |

Thông tin hữu ích cho audit: plugin ID/version, expected signer identity, fingerprint, SHA-256 thực tế, thời điểm, kết quả kiểm tra từng tầng và quyết định cuối cùng. Không log private key hay nguyên văn các dữ liệu nhạy cảm của plugin.

## 15. Checklist chấp nhận plugin trước khi thực thi

1. **Integrity:** digest hiện tại có khớp bản được duyệt từ nguồn đáng tin không?
2. **Signature:** có xác minh chữ ký trên đúng byte và phạm vi artifact cần bảo vệ không?
3. **Signer identity:** key/certificate có được nhận diện qua pin hoặc chain đã kiểm chứng không?
4. **Publisher authorization:** signer ấy có quyền ký đúng plugin ID, version và capability này không?
5. **Certificate policy:** thời gian, revocation, key usage, timestamp và thuật toán có đạt không?
6. **Release metadata:** dependency, cấu hình, resource thực thi có được bao phủ bởi signed manifest hoặc cơ chế tương đương không?
7. **Anti-rollback:** release có bị cấm, thu hồi hoặc dưới minimum version không?
8. **TOCTOU:** loader có dùng chính những byte đã xác minh không?
9. **Lifecycle:** chỉ sau khi chấp nhận mới tạo/khởi tạo provider, prepare, activate và publish readiness?
10. **Runtime defense:** có giới hạn tài nguyên/quyền, giám sát, dừng và thu hồi plugin khi cần không?

Với các kết quả chưa xác minh, phải dùng trạng thái **UNKNOWN/NOT_CHECKED** thay vì mặc định xem là true. Một hàm chỉ trả isSignatureValid không thể đại diện cho toàn bộ verdict của plugin host.

## 16. Câu hỏi tự kiểm tra

**Một file có hash SHA-256 giống checksum tải từ cùng một endpoint chưa đáng tin đã đủ chưa?** Chưa. Cần bảo vệ digest mong đợi bằng một nguồn tin cậy độc lập.

**Tại sao chữ ký của attacker có thể trả true?** Vì họ ký bằng private key của chính họ và đưa đúng public key tương ứng. Verification là phép kiểm tra mật mã; publisher trust cần bước khác.

**Cần xác thực điều gì sau khi biết cert signer có chain tin cậy?** Cần kiểm đúng danh tính, quyền publish plugin ID/capability, trạng thái thu hồi/version và phạm vi artifact được ký.

**Nếu signed JAR có một entry mới chưa ký thì sao?** Chữ ký của các entry cũ có thể vẫn hợp lệ; host phải có policy xử lý unsigned entry, không suy ra toàn archive đã được chứng thực.

**Vì sao phải kiểm tra trước ServiceLoader.Provider.get()?** Vì lời gọi ấy có thể tạo instance và thực thi constructor/static initializer của provider.

**Chữ ký hợp lệ có chứng minh plugin không thể truy cập network hay file host không?** Không. Điều đó thuộc policy/cô lập runtime, không thuộc chữ ký số.

### Tài liệu chuẩn

- Oracle Java SE 17, **MessageDigest**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Oracle Java SE 17, **Signature**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- Oracle Java SE 17, **KeyPairGenerator**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html
- Oracle Java SE 17, **JarFile** và verifying entries: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Oracle, **JAR File Specification**: https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html
- Oracle, **jarsigner Command**, verify/strict/certificates: https://docs.oracle.com/en/java/javase/22/docs/specs/man/jarsigner.html
- Oracle Java SE 17, **CertPathValidator**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html
- Oracle Java SE 17, **PKIXParameters**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html

**Kết luận:** **Integrity** trả lời “đúng byte release đã chấp nhận chưa?”; **digital signature** trả lời “chữ ký có đúng với khóa ký trên dữ liệu đã ký không?”; **publisher trust** trả lời “khóa/danh tính đó có được host cho phép phát hành đúng plugin không?”. Cả ba phải kết nối thành một chuỗi tin cậy **trước khi plugin được nạp hoặc kích hoạt**. Sau khi chấp nhận vẫn cần kiểm soát quyền và vòng đời, vì chữ ký xác thực nguồn gốc chứ không bảo đảm hành vi code.
