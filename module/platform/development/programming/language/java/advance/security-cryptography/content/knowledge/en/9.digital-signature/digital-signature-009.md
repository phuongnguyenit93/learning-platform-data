# 9.9 Giới hạn của verify thành công khi khóa công khai chưa được gắn với danh tính tin cậy

## Mục tiêu học tập

Sau bài này, bạn sẽ giải thích chính xác ý nghĩa của `Signature.verify(...) == true` trong Java; nhận ra vì sao **chữ ký hợp lệ về mặt toán học chưa đồng nghĩa dữ liệu đến từ người/tổ chức mong đợi**; phân biệt **khóa công khai**, **danh tính**, **chứng chỉ**, **chuỗi tin cậy** và **quyền được phép thực hiện hành động**; mô phỏng lỗi tin vào public key do đối thủ tự gửi; và xây dựng thứ tự xác thực đúng cho thông điệp, API, file cập nhật hoặc JWT.

Bài thuộc **9. Chữ ký số** của Java Advance – security-cryptography. Trọng tâm không phải cách tự triển khai Ed25519/RSA/ECDSA, mà là **giới hạn của bước verify** và cách **ràng buộc khóa xác minh với danh tính tin cậy**. Ví dụ có mã Java 17 chạy độc lập; phần liên quan chứng chỉ/PKIX giải thích các bước kiểm tra ở mức hệ thống, không giả vờ rằng một phương thức `verify` có thể thay thế chúng.

## 1. `verify == true` thực sự nói lên điều gì?

Chữ ký số thường được mô tả qua bốn thành phần:

- `M`: **chính xác dãy byte** thông điệp được ký, không phải “nội dung nhìn có vẻ giống nhau”.
- `S`: dãy byte chữ ký.
- `PK`: public key dùng để kiểm tra chữ ký, ứng với một private key bí mật.
- `algorithm/parameters`: scheme như `Ed25519`, `SHA256withECDSA`, hoặc `RSASSA-PSS` kèm tham số PSS phù hợp.

Phép xác minh có thể ký hiệu:

```text
Verify(algorithm, publicKey, messageBytes, signatureBytes) = true/false
```

Với giả định thuật toán/implementation an toàn và khóa bí mật được bảo vệ, **`true` cho biết chữ ký phù hợp với `PK` và `M` dưới scheme đã chọn**. Nó không tự suy ra rằng `PK` thuộc về “ngân hàng A”, “nhà phát hành phần mềm B”, “tài khoản C” hay “server example.com”.

Hai câu hỏi phải tách biệt:

1. **Cryptographic verification:** “Chữ ký này có hợp lệ cho thông điệp này, theo khóa công khai đang dùng không?”
2. **Identity/trust binding:** “Khóa công khai đó có thực sự được cấp phép đại diện cho đúng bên mà ứng dụng đang tin tưởng, trong đúng vai trò và ngữ cảnh không?”

Chỉ trả lời “có” câu 1 **chưa hoàn thành** câu 2.

Thêm hai tầng nữa thường cần để đưa ra quyết định chấp nhận:

3. **Authorization:** “Bên đã xác thực có được phép thực hiện *hành động này* với *đối tượng này* không?”
4. **Freshness/protocol context:** “Thông điệp có đúng người nhận, mục đích, phiên bản, thời hạn và chưa bị phát lại không?”

Chữ ký hợp lệ không đồng nghĩa “an toàn để thực thi”. Các khái niệm này phải được kiểm tra **kết hợp** trong một policy cụ thể.

### Ví dụ đối chiếu kết luận đúng/sai

| Hiện tượng | Kết luận có căn cứ | Kết luận chưa có căn cứ |
| --- | --- | --- |
| `Signature.verify(signature)` trả `true` | Chữ ký phù hợp byte thông điệp và public key đã cung cấp | “Thông điệp chắc chắn do Alice gửi” |
| Public key nằm trong payload cùng chữ ký | Key tồn tại dưới dạng bytes có thể parse được | Key đó được Alice/CA/đơn vị phát hành phê duyệt |
| Chứng chỉ tự ký `cert.verify(cert.getPublicKey())` thành công | Chữ ký tự ký của certificate hợp lệ theo public key trong chính certificate | Chứng chỉ được một trust anchor của tổ chức tin cậy |
| Chuỗi chứng chỉ được chấp nhận theo một tập trust anchors | Có liên kết chữ ký và ràng buộc đường dẫn phù hợp chính sách kiểm tra được áp dụng | Chứng chỉ nhất thiết thuộc **đúng hostname/tenant/role** ứng dụng mong đợi |
| Chữ ký file update hợp lệ theo key đã pin | Bytes file khớp key update được pin | File chưa bị rollback, phiên bản mới hơn hoặc hành động cài đặt luôn được cho phép |

## 2. Lỗ hổng kinh điển: cho phép người gửi tự chọn khóa verify

Giả sử một API nhận dữ liệu có hình dạng:

```json
{
  "sender": "trusted-publisher",
  "message": "publish-version-42",
  "publicKey": "<public-key-do-nguoi-gui-cung-cap>",
  "signature": "<signature-do-nguoi-gui-cung-cap>"
}
```

Trong cấu trúc minh họa này, `publicKey`, `sender` và `signature` **đều do client điều khiển**. Nếu server thực hiện:

```text
publicKey = parse(request.publicKey)
verified  = Verify(publicKey, request.message, request.signature)
if (verified) accept(request.sender, request.message)
```

thì việc gọi `Verify` có thể đúng về mật mã nhưng quy tắc **chấp nhận** lại sai:

1. Người tấn công sinh cặp khóa mới của chính họ.
2. Họ ký bất kỳ thông điệp họ muốn bằng private key của mình.
3. Họ gửi chữ ký, public key của mình và tự nhận `sender = "trusted-publisher"`.
4. Bên nhận parse khóa do họ cung cấp, gọi `verify` và nhận `true`.
5. Ứng dụng **nhầm khóa của attacker thành khóa của nhà phát hành**.

Không hề cần phá Ed25519, RSA hay ECDSA. Điểm bị phá nằm ở **việc xác định public key được tin cậy**, không phải trong phép kiểm tra chữ ký.

**Quy tắc cốt lõi:** Public key có thể được chuyển qua mạng, nhưng **nguồn và quyền sử dụng** của public key phải được xác thực bằng một kênh/quy trình tin cậy độc lập. Trường `sender` chỉ là **claim** chưa được chứng minh. Trong một giao thức đúng, public key dùng để xác minh phải đến từ trust store đã provision, certificate chain đã được xác minh và gắn đúng identity, hoặc một cơ chế ràng buộc tương đương.

### Ba tình huống khác nhau

- **Key đã tin cậy, chữ ký không hợp lệ:** từ chối vì phép `verify` không đạt.
- **Chữ ký hợp lệ, key chưa đáng tin hoặc gắn sai danh tính:** **vẫn phải từ chối** dù `verify` đạt.
- **Chữ ký hợp lệ, key đáng tin, nhưng yêu cầu ngoài quyền hoặc đã hết hạn:** **vẫn phải từ chối** bởi policy/authorization/freshness không đạt.

Một hệ thống phải đạt **tất cả điều kiện bắt buộc** trước khi coi một thông điệp là hợp lệ ở tầng nghiệp vụ.

## 3. Ví dụ Java 17 chạy được: verify đúng, danh tính giả vẫn bị chặn

Chương trình sau sử dụng **Ed25519** chỉ để minh họa (vấn đề áp dụng tương tự cho chữ ký RSA-PSS/ECDSA). Nó sinh hai cặp khóa độc lập:

- `trusted`: cặp khóa đại diện cho một **danh tính đã được ứng dụng tin cậy từ trước** trong mô phỏng.
- `attacker`: cặp khóa do người tấn công kiểm soát.
- `trustedPin`: SHA-256 fingerprint của **SubjectPublicKeyInfo (SPKI) DER** của public key trusted. Ở ví dụ tự chứa, pin được tạo tại thời điểm khởi tạo để biểu diễn một trust anchor đã có; **đây chưa phải quy trình phân phối niềm tin thật**.
- `verifyWithPinnedKey`: chỉ chấp nhận chữ ký khi public key ứng viên khớp pin đã chọn **và** verify chữ ký thành công.

Tạo tệp **`SignatureIdentityDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;

public final class SignatureIdentityDemo {
    private static final String SIGNATURE_ALGORITHM = "Ed25519";

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance(SIGNATURE_ALGORITHM);
        KeyPair trusted = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();

        byte[] message = "transfer=100&to=alice"
                .getBytes(StandardCharsets.UTF_8);
        byte[] changedMessage = "transfer=900&to=alice"
                .getBytes(StandardCharsets.UTF_8);

        byte[] trustedSignature = sign(trusted, message);
        byte[] attackerSignature = sign(attacker, message);

        KeyFactory factory =
                KeyFactory.getInstance(SIGNATURE_ALGORITHM);
        PublicKey trustedFromSpki = factory.generatePublic(
                new X509EncodedKeySpec(trusted.getPublic().getEncoded()));
        PublicKey attackerFromSpki = factory.generatePublic(
                new X509EncodedKeySpec(attacker.getPublic().getEncoded()));
        byte[] trustedPin = spkiSha256(trustedFromSpki);

        System.out.println("Trusted signature verifies: "
                + verify(trustedFromSpki, message, trustedSignature));
        System.out.println("Attacker signature with attacker key verifies: "
                + verify(attackerFromSpki, message, attackerSignature));
        System.out.println("Attacker signature with trusted key verifies: "
                + verify(trustedFromSpki, message, attackerSignature));
        System.out.println("Attacker key matches trusted pin: "
                + MessageDigest.isEqual(trustedPin,
                        spkiSha256(attackerFromSpki)));
        System.out.println("Policy accepts attacker message: "
                + verifyWithPinnedKey(attackerFromSpki, trustedPin,
                        message, attackerSignature));
        System.out.println("Policy accepts trusted message: "
                + verifyWithPinnedKey(trustedFromSpki, trustedPin,
                        message, trustedSignature));
        System.out.println("Policy accepts changed message: "
                + verifyWithPinnedKey(trustedFromSpki, trustedPin,
                        changedMessage, trustedSignature));
        System.out.println("Replay cryptographic verification succeeds: "
                + verify(trustedFromSpki, message, trustedSignature));
    }

    private static byte[] sign(KeyPair pair, byte[] message)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance(SIGNATURE_ALGORITHM);
        signer.initSign(pair.getPrivate());
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(PublicKey publicKey, byte[] message,
                                  byte[] signatureBytes)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(SIGNATURE_ALGORITHM);
        verifier.initVerify(publicKey);
        verifier.update(message);
        return verifier.verify(signatureBytes);
    }

    private static byte[] spkiSha256(PublicKey publicKey)
            throws GeneralSecurityException {
        byte[] spki = publicKey.getEncoded();
        if (spki == null) {
            throw new GeneralSecurityException(
                    "This public key cannot be exported as SPKI");
        }
        return MessageDigest.getInstance("SHA-256").digest(spki);
    }

    private static boolean verifyWithPinnedKey(
            PublicKey candidate, byte[] trustedPin,
            byte[] message, byte[] signatureBytes)
            throws GeneralSecurityException {
        if (!MessageDigest.isEqual(trustedPin, spkiSha256(candidate))) {
            return false;
        }
        return verify(candidate, message, signatureBytes);
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên có triển khai Ed25519:

```bash
javac --release 17 SignatureIdentityDemo.java
java SignatureIdentityDemo
```

**Stdout thực tế đã kiểm thử** (giá trị khóa/chữ ký được sinh ngẫu nhiên nhưng chương trình chỉ in kết quả boolean):

```text
Trusted signature verifies: true
Attacker signature with attacker key verifies: true
Attacker signature with trusted key verifies: false
Attacker key matches trusted pin: false
Policy accepts attacker message: false
Policy accepts trusted message: true
Policy accepts changed message: false
Replay cryptographic verification succeeds: true
```

**Giải thích từng kết quả:**

1. `Trusted signature verifies: true`: chữ ký tạo bằng private key trusted phù hợp public key trusted đã import lại từ SPKI.
2. `Attacker signature with attacker key verifies: true`: **đây là điểm nguy hiểm** nếu ứng dụng cho client tự gửi public key rồi coi `true` là danh tính đã được tin. Kết quả này hoàn toàn đúng về mật mã nhưng không xác thực người gửi là trusted publisher.
3. `Attacker signature with trusted key verifies: false`: chữ ký attacker không khớp public key đã tin cậy; việc lựa chọn đúng key làm thay đổi quyết định.
4. `Attacker key matches trusted pin: false` và `Policy accepts attacker message: false`: kiểm tra ràng buộc key trước khi chấp nhận chữ ký loại được key giả.
5. `Policy accepts trusted message: true`: cả key lẫn chữ ký phù hợp với trust record trong ví dụ.
6. `Policy accepts changed message: false`: chữ ký cho `transfer=100` không hợp lệ đối với nội dung đã đổi thành `transfer=900`.
7. `Replay cryptographic verification succeeds: true`: gửi lại nguyên thông điệp/chữ ký hợp lệ vẫn qua phép `verify`. Chữ ký **không tự chống phát lại**.

**Phân biệt mô phỏng và hệ thống thật:** `trustedPin` của demo được tính từ một public key **mới sinh ngay trong tiến trình**, nên **không chứng minh key này thật sự thuộc về một tổ chức bên ngoài**. Trong production, pin hoặc public key đáng tin phải được **cung cấp từ trước qua kênh được xác thực** (ví dụ ứng dụng phát hành có khóa hardcoded theo quy trình kiểm soát release, trust store đã kiểm duyệt, cấu hình có xác thực). Không được tính pin lần đầu từ chính `candidate` mà request chưa tin cậy mang đến rồi lập tức dùng pin đó để chấp nhận request: làm vậy quay lại đúng lỗ hổng ban đầu.

`getEncoded()` thường trả **SPKI DER** cho public key phần mềm; code minh họa có kiểm tra `null` vì không phải mọi key/provider đều cho xuất encoding. Hash SHA-256 của SPKI **không phải chứng chỉ X.509**, cũng không tự tạo niềm tin. `MessageDigest.isEqual` giúp so byte của hai fingerprint, nhưng bài toán chính là **nguồn gốc của fingerprint trusted**, không phải phép so sánh byte.

## 4. Ràng buộc khóa công khai với danh tính tin cậy

Một key binding được tin tưởng có thể mô tả bằng bộ:

```text
(expectedIdentity, allowedPurpose, trustedPublicKey,
 algorithmPolicy, validity/rotationPolicy, provenance)
```

Ví dụ một ứng dụng cập nhật phần mềm phải biết trước **khóa nào được phép ký bản cập nhật**, cho **sản phẩm nào**, có hiệu lực ở **giai đoạn nào**, và **ai có quyền thay đổi key registry**. Lưu một public key mà không kèm identity/purpose dễ dẫn đến nhầm các nhà phát hành hoặc môi trường staging/production.

### Các cách thiết lập niềm tin

| Cơ chế | Niềm tin ban đầu đến từ đâu? | Khi nào phù hợp? | Rủi ro vận hành cần xử lý |
| --- | --- | --- | --- |
| **Public-key pinning** | SPKI bytes/fingerprint được provision qua kênh đã tin cậy | Ứng dụng đóng, bản cập nhật có một số publisher xác định | Rotation, khóa dự phòng, thu hồi, sửa phần mềm nếu pin cũ lỗi |
| **Trust store/allowlist** | Danh sách key/identity đã phê duyệt và có kiểm soát thay đổi | Hệ thống nội bộ, nhiều publisher/tenant | Phân tách quyền quản trị, trùng key ID, hết hạn policy, xóa key cũ |
| **PKI / X.509** | CA/trust anchors được tin cậy trước, rồi kiểm tra đường dẫn chứng chỉ và tên/role | TLS, mTLS, cấp chứng chỉ tổ chức, máy chủ/người dùng | Thu hồi, thay đổi CA, hostname/SAN, EKU/KeyUsage, chính sách path |
| **TOFU (trust on first use)** | Public key thấy lần đầu được ghi nhớ khi chưa có kênh chứng thực khác | Một số workflow SSH/peer-to-peer theo chính sách | Lần đầu có thể bị MITM; phải cảnh báo khi key thay đổi và xác minh ngoài băng |
| **Khóa công bố qua kênh xác thực** | Endpoint/metadata đã gắn với issuer được tin, bảo vệ bằng HTTPS/TLS, policy hoặc chữ ký tin cậy khác | JWKS/JWT, hệ thống federation | Không lấy URL từ payload tùy ý, ràng buộc issuer/tenant/kid và caching |

Không có một cơ chế universal tốt nhất: lựa chọn phụ thuộc số lượng bên ký, chính sách danh tính, quy mô rotation, chuẩn giao thức và mô hình đe dọa. **Mọi cơ chế đều phải có điểm bắt đầu của niềm tin**. Nếu đối thủ kiểm soát đồng thời payload, signature, public key và “danh sách pin”, kiểm tra mật mã không thể tự khôi phục đúng danh tính.

### Key pinning: pin cái gì?

Có ít nhất hai khái niệm dễ lẫn:

- **SPKI pin:** SHA-256 trên byte DER `SubjectPublicKeyInfo` của public key, tức liên kết với **public key** và thuật toán liên quan.
- **Certificate fingerprint:** SHA-256 trên **toàn bộ certificate DER**; đổi/chứng chỉ mới có thể đổi fingerprint kể cả khi public key giữ nguyên.

Cả hai giá trị đều có thể hiển thị dưới dạng hex/Base64; chỉ nhìn vào chuỗi hash **không phân biệt được** chúng. Nếu thiết kế dùng SPKI pin, phải nói rõ source bytes là `publicKey.getEncoded()` ở định dạng SPKI, chứ không phải `certificate.getEncoded()`. Pin **không** là secret, nhưng tính đúng đắn/kênh provision của pin phải được bảo vệ.

Với trust store nhiều khóa, nên lookup theo **expected identity** và **key ID** hợp lệ rồi verify bằng key được tìm thấy. Trường `kid` đến từ request có thể được dùng như **gợi ý tìm kiếm trong allowlist**, không được xem như “bằng chứng khóa đã tin cậy” hay dùng tùy ý để tải khóa từ một URL do người gửi chỉ định.

## 5. Chứng chỉ X.509: chứng minh đường dẫn tin cậy khác với chứng minh danh tính

Certificate có thể mang public key, subject, Subject Alternative Name (SAN), thời hạn, issuer, Key Usage, Extended Key Usage và chữ ký của issuer. Nhưng chỉ parse certificate hoặc gọi `certificate.verify(issuerPublicKey)` là **chưa đủ**.

### Những bước cần có khi dựa vào PKI

1. **Chọn trust anchor phù hợp** từ trust store đã tin cậy. Không chấp nhận một CA root chỉ vì nó tự ký hợp lệ. “Trusted root” là quyết định phân phối tin cậy từ trước.
2. **Xác minh đường dẫn chứng chỉ** (issuer→subject, chữ ký, Basic Constraints, path length, thời hạn, policy, thuật toán/độ mạnh khóa và các ràng buộc path theo tiêu chuẩn). Java hỗ trợ `CertPathValidator.getInstance("PKIX")` và `PKIXParameters` có trust anchors do ứng dụng cấu hình.
3. **Kiểm tra đúng danh tính ứng dụng mong đợi**, không chỉ “bất kỳ certificate nào của một CA đáng tin”. Với HTTPS/TLS server, kiểm tra hostname trong SAN theo quy tắc endpoint identification; với client mTLS, ánh xạ certificate identity đến tài khoản/service được cấp quyền.
4. **Kiểm tra mục đích/role và chính sách khóa**: KeyUsage, ExtendedKeyUsage (EKU), tên service, tenant hoặc namespace, certificate policy và hạn chế tổ chức. Certificate được phép dùng để ký server TLS **không đương nhiên** có quyền ký bản cập nhật sản phẩm hoặc hóa đơn.
5. **Xem xét hiệu lực và revocation**: notBefore/notAfter, CRL/OCSP hay cơ chế revoke khác theo cấu hình/độ tin cậy cần thiết. Không giả định một phép `CertPathValidator.validate(...)` luôn đã làm revocation đúng trong mọi môi trường; policy/provider và nguồn dữ liệu ảnh hưởng bước này.
6. **Verify chữ ký của thông điệp bằng public key của đúng end-entity certificate**, đúng scheme và byte đầu vào, sau khi xác định key phù hợp identity/usage. Thành công ở bước này mới kết hợp được **chữ ký hợp lệ** với **một danh tính được chấp nhận theo policy**.

**Điểm thường bị bỏ sót:** Xác minh PKIX path **không tự động bảo đảm hostname hoặc subject identity khớp đối tượng bạn muốn**. Path validation chứng minh một cấu trúc tin cậy được kiểm tra; kiểm tra tên chủ thể là quyết định **phụ thuộc ngữ cảnh ứng dụng**. Một certificate hợp lệ cho `service-b.example` không thể được dùng thay cho `service-a.example` chỉ vì cùng được CA cấp.

Đối với HTTPS, nên dùng TLS/JSSE đã cấu hình kiểm tra certificate chain **và endpoint identity** theo đúng giao thức; tránh tự xây trust manager luôn chấp nhận certificate. Trong Java, chỉ thêm certificate vào `KeyStore` mà không có logic kiểm tra danh tính/ủy quyền thích hợp cho use case riêng cũng chưa đủ.

### Tự ký không có nghĩa đáng tin hoặc không đáng tin tuyệt đối

Một certificate tự ký có thể được **tin cậy có chủ ý** khi public key/fingerprint đã được cài đặt an toàn làm trust anchor cho một hệ thống giới hạn. Ngược lại, certificate tự ký do người tấn công gửi đến có thể vượt qua `cert.verify(cert.getPublicKey())`, vì họ có cả private key và certificate của mình. **Điều khác biệt là nguồn phân phối/trust anchor được phê duyệt**, không phải việc self-signed hay CA-signed như một nhãn đơn lẻ.

## 6. `Signature` trong Java không kiểm tra trust store

Các bước cốt lõi khi verify chữ ký Ed25519/RSA/ECDSA bằng JCA tương tự:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(candidatePublicKey);
verifier.update(exactMessageBytes);
boolean cryptographicallyValid = verifier.verify(signatureBytes);
```

Đây là **đoạn minh họa**, không phải chương trình độc lập: cần import `java.security.Signature`, có `candidatePublicKey`/`exactMessageBytes`/`signatureBytes` phù hợp và xử lý checked exceptions. Không có tham số “Alice”, “đúng tenant” hay “domain đáng tin” trong API này.

Lưu ý:

- `Signature.initVerify(PublicKey)` kiểm tra một số điều kiện của **loại khóa và provider**, không chứng minh danh tính. `Signature.initVerify(Certificate)` cũng **không thay thế** quy trình PKIX/path/identity validation; API có thể kiểm tra hạn chế KeyUsage nhất định, nhưng không tự biến certificate chưa tin cậy thành tin cậy.
- `Signature.verify(...)` có thể trả `false` hoặc ném `SignatureException` khi chữ ký/format có vấn đề tùy thuật toán/provider. Đừng coi mọi lỗi thành “công ty X gian lận”; coi input là không hợp lệ và báo lỗi phù hợp.
- `RSA-PSS` phải thống nhất hash, MGF1, salt length và các tham số. `ECDSA` cần đúng curve và format signature (ví dụ DER hoặc IEEE P1363 tùy giao thức). `Ed25519` là một scheme chữ ký cụ thể; không chọn algorithm chỉ theo độ dài signature hoặc trường do attacker đề xuất.
- `KeyFactory.getInstance("Ed25519").generatePublic(new X509EncodedKeySpec(bytes))` chỉ kiểm tra/decode **dữ liệu khóa**, không kiểm tra nguồn cung cấp dữ liệu đó.
- Việc `getInstance` thành công chỉ chứng tỏ provider có engine; không liên quan đến danh sách khóa/danh tính đáng tin của ứng dụng.

Nếu dùng `X509EncodedKeySpec` hoặc certificate public key load từ file/HTTP, câu hỏi đầu tiên vẫn phải là **file/HTTP response đó đến từ đâu và có được xác thực không?**.

## 7. Thứ tự xác minh đúng cho một thông điệp ký số

Dưới đây là luồng khái niệm cho **thông điệp được gửi kèm chữ ký**. Tên trường chỉ là ví dụ, không phải một định dạng giao thức chuẩn có thể copy nguyên vào production:

```text
Input:
  claimedIssuer, keyId, algorithm, payload, signature, context
       |
       v
[Kiểm tra giới hạn kích thước, encoding, schema, phiên bản]
       |
       v
[Xác định expectedIssuer/expectedRole từ ngữ cảnh tin cậy]
       |
       v
[Tra trusted key registry / validate certificate path + identity]
       |
       +-- khóa không tin cậy/sai role/sai issuer --> REJECT
       |
       v
[Chỉ cho phép algorithm/params đã quy định trong policy]
       |
       v
[Chuẩn hóa/đối chiếu chính xác bytes được ký + context]
       |
       v
[Signature.verify bằng public key đã được chấp nhận]
       |
       +-- false/exception ------------------------> REJECT
       |
       v
[Kiểm tra expiry, nonce/replay, audience, action authorization]
       |
       +-- policy không đạt -----------------------> REJECT
       |
       v
                 ACCEPT
```

Các bước có thể được triển khai ở thứ tự kỹ thuật khác nhau nhằm tối ưu hiệu suất hoặc hạn chế thông tin lộ ra, nhưng **quyết định ACCEPT phải phụ thuộc đầy đủ vào cả trust binding, cryptographic verification và policy**. Không nên thực thi tác dụng phụ trước khi những điều kiện bắt buộc đã đạt.

### Expected identity phải đến từ đâu?

Ví dụ một dịch vụ chỉ nhận cập nhật từ publisher A: `expectedIssuer="publisher-A"` phải đến từ **cấu hình/chính sách đã được phê duyệt** hoặc ngữ cảnh xác thực độc lập, **không được lấy nguyên từ claim `sender` rồi tin ngay**.

Nếu một hệ thống hỗ trợ nhiều publisher, registry có thể ánh xạ:

```text
publisher-A / signing-v3  -> trusted public key A, allowed for product X
publisher-B / signing-v7  -> trusted public key B, allowed for product Y
```

Khi request mang `keyId=signing-v7`, server chỉ dùng nó tra cứu trong **registry tin cậy** rồi kiểm tra claimed issuer/purpose khớp bản ghi. Server không chấp nhận URL tùy ý từ request để tải một key mới và cho rằng đó là key của publisher A. Khi quay vòng key, có quy trình quản trị xác thực, giai đoạn overlap và thu hồi rõ ràng.

### Khóa không tự cấp quyền

Một người ký có thể thực sự là một service đã tin cậy nhưng chỉ được quyền **gửi báo cáo**, không được quyền **phê duyệt chuyển tiền**. Chữ ký hợp lệ xác nhận nguồn theo key binding; authorization phải được thực thi độc lập dựa trên action, resource, tenant, amount, scope hoặc role.

## 8. Với JWT/JWS và metadata khóa: những cạm bẫy tương tự

Giao thức như JSON Web Signature (JWS) hoặc JSON Web Token (JWT) thường có trường `alg`, `kid`, `iss`, `aud` và chữ ký. Đây là use case hay gặp lỗi **“chữ ký pass nhưng identity không hợp lệ”**:

- `kid` chỉ là **key selection hint**; không chứng minh key thuộc về đúng issuer. Chỉ lookup key thuộc **tập khóa của issuer đã cấu hình tin cậy**.
- `alg` là thông tin trong dữ liệu do người gửi kiểm soát; triển khai phải áp dụng **allowlist algorithm** và gắn thuật toán với loại key/chính sách. Không để token ép chuyển sang thuật toán không an toàn, tắt chữ ký, dùng shared secret sai mục đích hoặc gây algorithm confusion.
- `jku`/`x5u` hoặc địa chỉ JWKS từ token **không được** trở thành URL tùy ý để tải và tin khóa. Nếu cần JWKS, lấy từ endpoint của issuer đã được thiết lập tin cậy và bảo vệ bởi cấu hình, xác thực TLS, giới hạn chuyển hướng/địa chỉ và cache/rotation hợp lý.
- Sau khi chữ ký hợp lệ, vẫn phải kiểm tra **issuer (`iss`)**, **audience (`aud`)**, thời gian (`exp`, `nbf`), subject/tenant, scope và policy của hệ thống. Một token ký hợp lệ bởi **issuer B** không thể tự động được nhận như token của **issuer A**.
- JSON canonicalization, detached payload và encoding base64url có thể ảnh hưởng byte ký. Nên dùng thư viện JOSE/JWT đã kiểm thử, không tự build/parse JWS bằng chuỗi ghép thủ công.

Một ví dụ nhỏ: server cấu hình chấp nhận token từ issuer `https://id.example.org` nhưng client gửi token hợp lệ được ký bằng khóa do một issuer khác cấp. Nếu server tra JWKS không giới hạn theo issuer mà client gợi ý, token có thể `verify == true`; dù vậy **ứng dụng vẫn phải từ chối** vì issuer/key binding không đúng.

## 9. Chữ ký hợp lệ vẫn không bảo vệ mọi ngữ cảnh

### 9.1 Replay

Đã thấy trong chương trình: `verify` của cùng thông điệp và chữ ký lặp lại vẫn `true`. Nếu một lệnh thanh toán đã ký được gửi lại, thuật toán chữ ký không biết nó là giao dịch cũ.

Để chống replay khi cần, giao thức phải đưa **transaction ID, sequence number, timestamp, nonce hoặc expiration** vào **những byte được ký**, sau đó kiểm tra trạng thái đã sử dụng/cửa sổ thời gian tại bên nhận. Chỉ thêm timestamp vào payload nhưng không đưa nó vào phần được ký sẽ không tạo ràng buộc bảo mật.

### 9.2 Cross-protocol / cross-tenant

Một chữ ký cho thông điệp “approve 100” có thể bị dùng sai chỗ nếu thiếu ràng buộc bên nhận, hệ thống, tenant hoặc mục đích. Giao thức nên ký bản tin có **domain separation** rõ ràng, ví dụ bao gồm phiên bản, loại hành động, audience, tenant, canonical resource ID và toàn bộ trường quan trọng.

Đừng tái sử dụng một key cho nhiều protocol không liên quan rồi giả định chữ ký của protocol A không thể được dùng trong protocol B. Phân tách key theo purpose hoặc ràng buộc purpose chặt trong signed data, với các quy tắc verification rõ ràng.

### 9.3 Dữ liệu “trông giống nhau” không phải cùng byte

`Signature.update(byte[])` xử lý **byte**, không hiểu text/JSON. Các chuỗi có UTF-8 khác, newline `\n`/`\r\n`, BOM, thứ tự trường JSON, Unicode normalization hoặc spacing khác nhau dẫn đến thông điệp ký khác. Khi một bên ký raw bytes còn bên khác verify JSON được serialize lại, có thể fail dù “nội dung” nhìn như nhau.

Nếu cần ký dữ liệu cấu trúc, định nghĩa encoding **không mơ hồ** hoặc dùng chuẩn canonicalization của protocol. Cũng cần chống parser differential: hai chương trình không được có cách hiểu khác nhau về cùng bytes có chữ ký hợp lệ.

### 9.4 Khóa bị lộ hoặc signer bị xâm phạm

Chữ ký hợp lệ không tự chứng minh private key vẫn độc quyền thuộc về chủ sở hữu hợp pháp. Nếu private key bị đánh cắp hoặc một signer bị chiếm quyền, attacker có thể tạo chữ ký hợp lệ bằng **đúng trusted public key**. Cần chính sách phát hiện, thu hồi, rotation, audit, HSM/KMS, giới hạn quyền signer và xác định phạm vi sự cố. Chữ ký số cũng **không mã hóa nội dung**; người quan sát vẫn có thể đọc nội dung đã ký nếu dữ liệu được gửi ở dạng plaintext.

## 10. Đưa bước xác thực danh tính vào hệ thống Java

### 10.1 Trusted key registry nội bộ

Với một số ít publisher/thiết bị, thiết lập registry bằng cấu hình được quản lý, ví dụ `issuer -> keyId -> publicKey + allowedPurposes + algorithmPolicy`. Key material phải được provision ngoài băng, bằng đường dẫn được chứng thực, artifact cài đặt đáng tin hoặc thay đổi quản trị được xác nhận. Sau đó:

- Xác định **expected issuer** từ policy/ngữ cảnh.
- Chỉ chấp nhận public key được ánh xạ cho issuer đó; có thể dùng fingerprint SPKI để phát hiện thay thế.
- Chỉ `Signature.verify` với key trong registry.
- Kiểm tra thời hạn, key rotation, trạng thái revoked và authorization.
- Lập audit log về key ID, issuer đã được chọn, version, kết quả; không ghi private key hoặc dữ liệu nhạy cảm không cần thiết.

Nếu key registry bị thay đổi bởi chính request cần verify, đây không còn là registry đáng tin.

### 10.2 PKIX và TLS

Java hỗ trợ `CertificateFactory`, `CertPathValidator`/`CertPathBuilder`, `PKIXParameters`, `TrustAnchor` và `KeyStore`. Với TLS, nên ưu tiên JSSE/`SSLContext` cùng trust manager và **endpoint identification** đã cấu hình đúng; với mTLS cần map certificate identity của client tới đúng tài khoản và role sau khi xác nhận chain.

Để tránh ngộ nhận, đoạn sau chỉ minh họa việc **khởi tạo engine**, không thực hiện xác minh đầy đủ:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
// Cần CertPath/PKIXParameters/trust anchors được chuẩn bị đáng tin
// và kiểm tra danh tính, mục đích, trạng thái theo use case.
```

Không suy diễn rằng việc gọi `validator.validate(...)` với bất kỳ trust anchor do client gửi vào sẽ có giá trị. Quan trọng nhất là **trust anchors do ứng dụng lựa chọn trước**, cùng policy đúng use case. Kiểm tra hostname/SAN không phải mặc định của việc gọi trực tiếp `Signature.verify(...)` hoặc `CertPathValidator.validate(...)`.

### 10.3 Xử lý lỗi an toàn

- `Signature.verify == false`: chữ ký không hợp lệ cho key/message đã chọn; từ chối.
- `SignatureException`/`InvalidKeyException`/`NoSuchAlgorithmException`: kiểm tra định dạng/algorithm/provider/key policy; từ chối input không hợp lệ hoặc xử lý lỗi cấu hình. Không “thử từng key bất kỳ cho đến khi có key trả true” rồi chấp nhận danh tính do request tự khai.
- `CertificateException`, `CertPathValidatorException`: xem lại trust path/constraints, không tắt kiểm tra chain để “chạy được”.
- Thông báo public nên tránh tiết lộ quá chi tiết trạng thái key, certificate hoặc hệ thống nội bộ khi không cần. Các log nội bộ cần có correlation ID, key ID, kết quả bước **trust**, kết quả bước **signature** và lý do authorization, với dữ liệu được kiểm soát.

## 11. Bảng quyết định khi verify đã thành công

| Trường hợp | `verify` | Trust binding | Policy/freshness | Chấp nhận? |
| --- | --- | --- | --- | --- |
| Alice ký; key Alice đã provision và đúng purpose; request hợp lệ | `true` | Đạt | Đạt | **Có** |
| Mallory ký bằng khóa riêng rồi gửi kèm public key tự chọn | `true` với key Mallory | **Không đạt** | Không cần xét | **Không** |
| Alice ký nhưng verifier dùng key Bob | `false` | Dù Bob có tin cậy cũng sai đối tượng | Không cần xét | **Không** |
| File được ký bởi publisher đáng tin nhưng signature bị thay | `false` | Đạt | Không cần xét | **Không** |
| Chữ ký đúng nhưng yêu cầu đã hết hạn/nonce trùng | `true` | Đạt | **Không đạt** | **Không** |
| Certificate chain hợp lệ nhưng hostname/scope sai | Có thể `true` | **Không đúng expected identity** | Không cần xét | **Không** |
| Đúng key và thông điệp nhưng signer chỉ có role đọc, request yêu cầu xóa | `true` | Đạt | **Không có quyền** | **Không** |
| Khóa trusted đã bị thu hồi sau sự cố | Có thể `true` | Trust policy hiện tại từ chối key | Không cần xét | **Không** |

**Mô hình tư duy cần nhớ:** `valid signature != trusted signer != authorized operation`. Bước verify là **một điều kiện cần trong nhiều hệ thống**, không phải điều kiện đủ để đưa ra quyết định chấp nhận.

## 12. Checklist trước khi đưa chữ ký số vào production

- [ ] Danh tính/issuer được kỳ vọng xác định từ cấu hình hoặc ngữ cảnh xác thực độc lập, **không tự tin claim người gửi**.
- [ ] Public key đến từ trust store/PKIX/pin đã được provision qua kênh tin cậy; không lấy key tùy ý trong payload rồi chấp nhận.
- [ ] Mỗi key có `keyId`, issuer, purpose, thuật toán được cho phép, policy rotation/revocation và ranh giới tenant.
- [ ] Nếu dùng certificate: kiểm tra path tới trust anchor, validity, constraints, purpose, SAN/endpoint identity, revocation theo policy.
- [ ] `Signature.verify` dùng đúng scheme/parameters, đúng public key và **đúng dãy byte đã ký**.
- [ ] Nếu dữ liệu qua format cấu trúc, encoding/canonicalization là quy tắc của protocol và được kiểm thử hai chiều.
- [ ] Claims như audience, expiration, nonce/sequence, signed context và quyền hành động được kiểm tra **ngoài** chữ ký.
- [ ] Trường `alg`/`kid` của token chỉ được dùng trong allowlist/trusted key namespace; không tự tải key từ URL tùy ý.
- [ ] Không thực thi thao tác có tác dụng phụ trước khi hoàn tất trust + verify + policy.
- [ ] Có test cho chữ ký đúng, chữ ký bị sửa, message bị sửa, key bị thay, issuer sai, replay, key revoked và authorization sai.

## 13. Bài luyện tập

1. Giải thích vì sao dòng `Attacker signature with attacker key verifies: true` trong `SignatureIdentityDemo` không phải lỗi của Ed25519.
2. Xóa bước kiểm tra pin khỏi `verifyWithPinnedKey`. Điều gì xảy ra nếu một request tự gửi cả `attackerFromSpki` lẫn `attackerSignature`? Việc sửa code có “tạo ra lỗ hổng” hay chỉ làm lộ lỗi trust binding vốn đã tồn tại?
3. Nếu một public key X.509/SPKI được tải từ một URL trên Internet, những bằng chứng bổ sung nào cần có để tin nó thuộc đúng publisher? Một hash SHA-256 do chính URL đó trả về có đủ không?
4. Một certificate tự ký có thể đi qua phép `cert.verify(cert.getPublicKey())`; hãy giải thích vì sao điều này chưa chứng minh nó được công ty tin cậy.
5. Mô tả các bước bắt buộc để xác thực một server TLS: từ trust anchors, chain, validity/purpose đến **hostname SAN**. Bước nào không nằm trong `Signature.verify`?
6. Thiết kế hệ thống cập nhật phần mềm dùng key rotation. Nếu keyId cũ bị revoke sau khi bị lộ, ứng dụng phải xử lý file có chữ ký toán học còn hợp lệ thế nào?
7. Thiết kế một signed transfer request có tenant, amount, payee, unique transaction ID, timestamp và audience; chỉ rõ trường nào phải nằm trong byte được ký, và kiểm tra replay/authorization được thực hiện ở đâu.
8. Trong JWT multi-tenant, vì sao kiểm tra chữ ký đúng với một JWKS của issuer B **không đủ** để nhận token như issuer A? Hãy đề xuất một registry ánh xạ issuer → allowlisted JWKS keys và algorithm policy.

## Tài liệu tham khảo

- [Java SE 17 — `Signature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `initVerify`, `update`, `verify` và ngoại lệ, kể cả overload nhận `Certificate`.
- [Java SE 17 — `KeyFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyFactory.html): parse khóa bằng `X509EncodedKeySpec` (chỉ giải mã format, không xác thực danh tính).
- [Java SE 17 — `X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): định dạng SubjectPublicKeyInfo của public key.
- [Java SE 17 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html), [`PKIXParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): xác minh certification path tới trust anchors do ứng dụng chọn.
- [Java SE 17 — `X509Certificate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): SAN, KeyUsage, EKU, validity và chữ ký certificate.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): PKIX path validation và các ràng buộc chứng chỉ.
- [RFC 8032 — EdDSA](https://www.rfc-editor.org/rfc/rfc8032): thuật toán Ed25519.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515) và [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `alg`, `kid`, `iss`, `aud` và xác minh nội dung token.
