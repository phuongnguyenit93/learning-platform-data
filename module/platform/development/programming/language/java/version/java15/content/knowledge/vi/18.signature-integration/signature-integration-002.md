# Phân phối public key và xác thực nguồn khóa trong tích hợp chữ ký số Java 15+

## Mục tiêu

Khi tích hợp chữ ký số, một lỗi thiết kế nghiêm trọng là **nhận public key từ chính thông điệp chưa được xác thực**, rồi dùng public key đó để gọi `Signature.verify(...)`. Attacker có thể tự tạo cặp khóa của mình, ký dữ liệu giả và gửi cả chữ ký lẫn khóa. Phép toán chữ ký vẫn hợp lệ — nhưng **không có bằng chứng khóa đó thuộc người ký mà hệ thống muốn tin cậy**.

Bài học này tập trung vào hai khâu riêng biệt:

1. **Phân phối public key:** bên nhận được dữ liệu khóa qua một biểu diễn như SPKI/Base64, chứng chỉ X.509 hoặc một kho khóa.
2. **Xác thực nguồn khóa:** bên nhận ràng buộc khóa với **issuer/danh tính/mục đích** qua một trust anchor hoặc kênh đáng tin, trước khi chấp nhận kết quả chữ ký.

Bạn sẽ học cách sử dụng `KeyFactory`, `X509EncodedKeySpec`, `MessageDigest`, `Signature`, cách dùng fingerprint SHA-256 và các mô hình PKIX/keyset. Ví dụ biên dịch bằng **JDK 17+**, dùng thuật toán **Ed25519** được hỗ trợ chính thức từ Java 15. Toàn bộ hướng dẫn sử dụng API và kiến thức vẫn áp dụng cho các JDK hiện đại, không dựa vào phương pháp cryptography lỗi thời/legacy.

## 1. Xác minh chữ ký khác với xác thực public key

Giả sử server nhận JSON:

```json
{
  "message": "order:42:approved",
  "publicKeySpki": "BASE64...",
  "signature": "BASE64..."
}
```

Nếu code chỉ giải mã `publicKeySpki` rồi thực hiện:

```java
// Trích đoạn minh họa: candidate, bytes, sig đã có.
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(candidate);
verifier.update(bytes);
boolean valid = verifier.verify(sig);
```

thì `valid=true` chỉ khẳng định rằng **sig phù hợp với bytes và candidate**. Nó không khẳng định `candidate` thuộc nhà phát hành A, đối tác B hoặc đúng tenant.

Attacker có thể:

1. Sinh cặp khóa Ed25519 hoàn toàn hợp lệ.
2. Tạo dữ liệu `"order:42:approved"` giả hoặc nội dung khác.
3. Ký bằng **private key attacker**.
4. Gửi **public key attacker** cùng dữ liệu và chữ ký.

Nếu bên nhận dùng khóa do attacker gửi mà không có bước trust, `verify` có thể trả `true`. Đây là **key-substitution attack** / thiếu ràng buộc danh tính, không phải lỗi trong thuật toán Ed25519.

Quy trình an toàn phải là:

```text
Nhận thông điệp, chữ ký và key ID / chứng chỉ / SPKI
            |
            v
Kiểm tra encoding, kích thước, format, thuật toán allowlist
            |
            v
Xác định expected issuer, tenant, purpose từ nghiệp vụ
            |
            v
Tìm khóa ứng viên trong registry / chứng chỉ
            |
            v
XÁC THỰC NGUỒN KHÓA với trust anchor độc lập
        |                           |
      FAIL                         PASS
        |                           |
        v                           v
     TỪ CHỐI           initVerify(publicKey)
                                  |
                                  v
                            update(bytes)
                                  |
                                  v
                            verify(sig)
                              |        |
                          false/lỗi   true
                              |        |
                              v        v
                           TỪ CHỐI  Kiểm tra freshness,
                                    replay, quyền rồi chấp nhận
```

Chỉ xem là **thành công** khi cả trust policy, chữ ký và yêu cầu nghiệp vụ đều đạt.

## 2. Các biểu diễn public key thường gặp

### 2.1. SPKI/DER

`PublicKey.getEncoded()` của khóa xuất được thường trả cấu trúc **SubjectPublicKeyInfo (SPKI)** theo X.509, mã hóa ASN.1 DER. SPKI chứa định danh thuật toán và dữ liệu public key; **không phải chứng chỉ X.509**.

Ví dụ để truyền khóa Ed25519 dưới dạng Base64:

```java
String encoded = java.util.Base64.getEncoder()
        .encodeToString(publicKey.getEncoded());
```

Bên nhận giải mã và tạo đối tượng `PublicKey`:

```java
byte[] spki = java.util.Base64.getDecoder().decode(encoded);
PublicKey key = java.security.KeyFactory.getInstance("Ed25519")
        .generatePublic(new java.security.spec.X509EncodedKeySpec(spki));
```

Các đoạn trên là **mã minh họa trong phương thức**, giả định đã khai báo `publicKey`, `encoded` và import `PublicKey` phù hợp. Chúng **chỉ giải mã và parse khóa**, chưa chứng minh khóa đáng tin.

| API | Công việc thực hiện | Không tự làm |
| --- | --- | --- |
| `Base64.Decoder.decode` | Chuyển chuỗi Base64 thành bytes | Xác thực người gửi |
| `X509EncodedKeySpec` | Biểu diễn SPKI bytes để `KeyFactory` xử lý | Kiểm tra certificate chain |
| `KeyFactory.generatePublic` | Chấp nhận khóa đúng format/thuật toán | Liên kết khóa với issuer |
| `PublicKey.getEncoded` | Xuất encoding được hỗ trợ | Bảo đảm mọi khóa HSM/KMS export được |
| `Signature.verify` | Kiểm tra toán học chữ ký trên message/key | Xác nhận nguồn public key |

Một số khóa được quản lý bởi thiết bị/hệ thống chuyên biệt có thể không hỗ trợ xuất encoded key. Chương trình bên dưới dùng khóa sinh trong JDK nên có SPKI xuất được.

### 2.2. Public key khác private key và certificate

**Private key** dùng ký và phải được bảo vệ; **public key** có thể công khai, nhưng **bản ghi ai sở hữu hoặc được phép sử dụng nó** phải được bảo vệ khỏi giả mạo.

`X509EncodedKeySpec` có chữ `X509` trong tên nhưng chỉ biểu diễn **public key SPKI**, không có issuer, subject, validity hay chữ ký của CA. Một **X.509 certificate** mới có các trường, extension và chữ ký issuer để có thể kiểm tra trong một đường tin cậy PKIX.

Chỉ đọc chứng chỉ bằng `CertificateFactory.getInstance("X.509")` hoặc gọi `cert.getPublicKey()` **không có nghĩa đã xác minh nguồn khóa**.

## 3. Ba cơ chế xác thực nguồn khóa hiện đại

### 3.1. Public key hoặc SHA-256 fingerprint được provision độc lập

Trong một hệ thống ít người ký cố định, ứng dụng có thể lưu **public key đã được phê duyệt** hoặc fingerprint từ quy trình cấu hình bảo mật ngoài băng (*out-of-band*). Ví dụ đội vận hành kiểm tra khóa của nhà phát hành A qua kênh tin cậy rồi đưa vào registry có quyền ghi hạn chế.

Từ đó, mỗi request mới chỉ được chấp nhận nếu public key ứng viên **khớp với nguồn khóa đã tin cậy**; attacker gửi khóa khác sẽ bị loại ngay cả khi chữ ký của attacker toán học hợp lệ.

Ưu điểm: rõ ràng, không cần xác minh chuỗi CA tại mỗi request nếu chính sách dùng pin. Nhược điểm: cần kế hoạch **key rotation**, phục hồi khi mất khóa, cập nhật pin và thu hồi khẩn cấp.

**Cấm vòng lặp tin cậy:** không tính `expectedPin` từ chính `receivedKey` của request chưa xác thực rồi xem đối chiếu là bằng chứng. So sánh một khóa với chính nó luôn qua.

### 3.2. Chứng chỉ X.509 và PKIX

Trong PKI, khóa ký có thể nằm trong một chứng chỉ được phát hành qua một chuỗi chứng chỉ. Bên nhận cần:

- Trust anchor (CA root hoặc tổ chức phát hành được tin cậy theo chính sách) **được quản lý trước**.
- Cert path được kiểm tra bằng **PKIX** về chữ ký issuer, constraints, thời gian và chính sách.
- Ràng buộc subject/SAN hoặc danh tính ứng dụng với **expected issuer**; không chỉ tin vì chứng chỉ có thể tạo được đối tượng Java.
- Kiểm tra key usage/extended key usage, mục đích dùng khóa, tình trạng thu hồi theo chính sách và thuật toán được phép.
- Sau khi đã xác thực certificate, dùng public key của nó để verify chữ ký message.

API Java tương ứng: `X509Certificate`, `CertPathValidator.getInstance("PKIX")`, `PKIXParameters`, `TrustAnchor`, `PKIXRevocationChecker`. Với kết nối TLS, JSSE và trust manager xử lý đường tin cậy; còn cần kiểm tra đúng danh tính endpoint như hostname.

**Đừng đánh đồng chứng chỉ TLS của website với quyền ký mọi tài liệu nghiệp vụ.** Một CA đáng tin để cấp chứng chỉ server không tự cấp quyền cho mọi certificate của CA đó ký đơn hàng. Danh tính và mục đích cần policy rõ.

### 3.3. Keyset/JWKS hoặc manifest được xác thực

Hệ thống nhiều khóa thường công bố registry chứa `key ID (kid)`, thuật toán, issuer, trạng thái và material public key. Có thể tải keyset từ endpoint **HTTPS đã xác thực và gắn cố định với issuer tin cậy**, hoặc dùng **manifest có chữ ký** của một khóa gốc đã tin cậy.

Để tránh thay khóa trái phép hoặc replay danh sách cũ, metadata nên có version, thời hạn, trạng thái thu hồi, chữ ký và cơ chế chống rollback.

Những lỗi phổ biến:

- Tin `kid` như bằng chứng quyền ký. Thực tế `kid` chỉ là **nhãn tra khóa** trong registry đáng tin, không phải chữ ký.
- Cho payload quyết định thuật toán `alg` theo ý nó; phải dùng **allowlist theo issuer/loại message**.
- Tải public key từ bất kỳ URL `jku`/`x5u` do request cung cấp. Điều này mở đường tới giả mạo nguồn khóa và SSRF; chỉ dùng endpoint đã cấu hình/allowlist và xác thực.
- Dùng một khóa vừa nằm trong manifest vừa tự ký manifest mà không có **trust anchor độc lập**. Làm vậy chưa giải quyết nguồn khóa từ đâu.

## 4. Fingerprint SHA-256 của SPKI

Một cách ràng buộc nguồn khóa là lưu fingerprint:

```text
SPKI pin = SHA-256( DER-encoded SubjectPublicKeyInfo )
```

Trong Java:

```java
byte[] digest = java.security.MessageDigest.getInstance("SHA-256")
        .digest(publicKey.getEncoded());
```

Đây là **32 byte** có thể biểu diễn dưới dạng hex hoặc Base64 để lưu cấu hình. Việc chọn cách biểu diễn không thay đổi nội dung hash. Tại bên nhận, tính digest trên SPKI chuẩn và so với digest đã được provision:

```java
byte[] receivedDigest = MessageDigest.getInstance("SHA-256")
        .digest(receivedKey.getEncoded());
boolean trusted = MessageDigest.isEqual(expectedPin, receivedDigest);
```

Hai trích đoạn chỉ có ý nghĩa khi `expectedPin` **đến từ nguồn tin cậy độc lập**. `MessageDigest.isEqual` so sánh mảng bytes, nhưng không tự tạo ra trust.

**Phân biệt:** fingerprint SPKI là SHA-256 của **public key encoding**; fingerprint chứng chỉ là SHA-256 của **toàn bộ DER certificate**. Chúng khác nhau. Nếu nhà phát hành đổi chứng chỉ nhưng **giữ cùng public key**, certificate fingerprint đổi còn SPKI pin có thể không đổi. Hai phía phải đồng ý đang pin thứ gì.

Pinning tạo ràng buộc mạnh với khóa đã được chấp thuận nhưng có **rủi ro vận hành** khi khóa hết hạn, đổi nhà cung cấp, bị lộ hoặc bị mất. Với ứng dụng HTTPS thông thường, ưu tiên kiểm tra TLS/PKIX đúng chuẩn; chỉ dùng pinning khi có yêu cầu đã phân tích cùng kế hoạch rotate và recovery.

## 5. Chương trình Java hoàn chỉnh: chứng minh key substitution

Tệp `PublicKeyTrustDemo.java` dưới đây dùng Ed25519, SPKI, Base64 và fingerprint SHA-256. Publisher và verifier nằm cùng một process để bài chạy độc lập; bước tạo `trustedPin` từ public key publisher **mô phỏng** việc verifier đã được provision đáng tin cậy từ trước.

**Cảnh báo:** Trong production, **không** tính expected fingerprint bằng cách lấy key đến từ request, và không để attacker thay cấu hình pin. Ứng dụng thực phải nhận trust anchor từ kênh xác thực, cấu hình được bảo vệ, PKI hoặc key manifest có chữ ký đã được kiểm chứng.

Chương trình mô phỏng attacker tạo khóa và ký message giả. Kết quả `attackerMathValid=PASS` là bằng chứng nguy cơ: chữ ký giả xác minh đúng với khóa attacker nhưng **bị từ chối vì không khớp trust anchor của publisher**.

### 5.1. Toàn bộ mã nguồn

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public final class PublicKeyTrustDemo {
    private static void check(String label, boolean success) {
        if (!success) {
            throw new AssertionError(label + " FAILED");
        }
        System.out.println(label + "=PASS");
    }

    private static byte[] sha256(byte[] bytes) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(bytes);
    }

    private static byte[] sign(PrivateKey key, byte[] data) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key);
        signer.update(data);
        return signer.sign();
    }

    private static boolean verify(
            PublicKey key, byte[] data, byte[] signature) throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    private static boolean verifyIfTrusted(
            byte[] expectedPin,
            PublicKey candidate,
            byte[] data,
            byte[] signature) throws Exception {
        // In production, expectedPin must come from an authenticated channel.
        byte[] actualPin = sha256(candidate.getEncoded());
        if (!MessageDigest.isEqual(expectedPin, actualPin)) {
            return false;
        }
        return verify(candidate, data, signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair publisher = generator.generateKeyPair();
        byte[] message = "catalog:v1:42".getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(publisher.getPrivate(), message);

        // Simulation: a pin has ALREADY been received securely and trusted.
        byte[] trustedPin = sha256(publisher.getPublic().getEncoded());

        // In-band data may carry a SPKI public key and the signature.
        String spkiBase64 = Base64.getEncoder()
                .encodeToString(publisher.getPublic().getEncoded());
        byte[] decodedSpki = Base64.getDecoder().decode(spkiBase64);
        PublicKey received = KeyFactory.getInstance("Ed25519")
                .generatePublic(new X509EncodedKeySpec(decodedSpki));

        check("spkiRoundTrip",
                Arrays.equals(received.getEncoded(),
                        publisher.getPublic().getEncoded()));
        check("pinMatches",
                MessageDigest.isEqual(trustedPin,
                        sha256(received.getEncoded())));
        check("trustedSignature",
                verifyIfTrusted(trustedPin, received, message, signature));

        byte[] changedMessage = "catalog:v1:43"
                .getBytes(StandardCharsets.UTF_8);
        check("tamperRejected",
                !verifyIfTrusted(trustedPin, received,
                        changedMessage, signature));

        KeyPair attacker = generator.generateKeyPair();
        byte[] fakeMessage = "catalog:v1:999"
                .getBytes(StandardCharsets.UTF_8);
        byte[] fakeSignature = sign(attacker.getPrivate(), fakeMessage);

        // Math works with attacker-supplied key; identity is NOT proved.
        check("attackerMathValid",
                verify(attacker.getPublic(), fakeMessage, fakeSignature));
        check("attackerPinMismatch",
                !MessageDigest.isEqual(trustedPin,
                        sha256(attacker.getPublic().getEncoded())));
        check("attackerNotTrusted",
                !verifyIfTrusted(trustedPin, attacker.getPublic(),
                        fakeMessage, fakeSignature));

        check("wrongPublicKeyRejected",
                !verify(attacker.getPublic(), message, signature));
        check("signatureLength", signature.length == 64);

        boolean invalidSpkiRejected = false;
        try {
            KeyFactory.getInstance("Ed25519")
                    .generatePublic(new X509EncodedKeySpec(new byte[]{1, 2, 3}));
        } catch (InvalidKeySpecException expected) {
            invalidSpkiRejected = true;
        }
        check("invalidSpkiRejected", invalidSpkiRejected);

        boolean invalidBase64Rejected = false;
        try {
            Base64.getDecoder().decode("not base64!!!");
        } catch (IllegalArgumentException expected) {
            invalidBase64Rejected = true;
        }
        check("invalidBase64Rejected", invalidBase64Rejected);
    }
}
```

### 5.2. Biên dịch, chạy và stdout

Trong thư mục chứa tệp, dùng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 PublicKeyTrustDemo.java
java PublicKeyTrustDemo
```

**Stdout chính xác:**

```text
spkiRoundTrip=PASS
pinMatches=PASS
trustedSignature=PASS
tamperRejected=PASS
attackerMathValid=PASS
attackerPinMismatch=PASS
attackerNotTrusted=PASS
wrongPublicKeyRejected=PASS
signatureLength=PASS
invalidSpkiRejected=PASS
invalidBase64Rejected=PASS
```

### 5.3. Giải thích các ca quan trọng

- `spkiRoundTrip=PASS`: SPKI của public key Ed25519 được mã hóa Base64, giải mã và tạo lại qua `KeyFactory` mà không làm mất dữ liệu key.
- `pinMatches=PASS`: SHA-256 SPKI của khóa nhận khớp expected pin mô phỏng từ giai đoạn enrollment đã tin cậy.
- `trustedSignature=PASS`: chỉ sau khi khớp pin mới gọi `verify`, và chữ ký của publisher được chấp nhận.
- `tamperRejected=PASS`: publisher đã ký `"catalog:v1:42"`, nên chữ ký không còn hợp lệ với `"catalog:v1:43"`.
- `attackerMathValid=PASS`: attacker tự ký một dữ liệu giả bằng private key của mình và chữ ký **vẫn đúng toán học** khi xác minh bằng public key attacker.
- `attackerPinMismatch=PASS`: khóa attacker khác khóa publisher đã provision.
- `attackerNotTrusted=PASS`: luồng tích hợp trust trước khi verify **từ chối attacker**, dù signature của attacker đúng với key của attacker.
- `wrongPublicKeyRejected=PASS`: chữ ký thật của publisher không khớp với khóa công khai attacker.
- `signatureLength=PASS`: chữ ký Ed25519 luôn có 64 byte.
- `invalidSpkiRejected=PASS`: DER/SPKI sai format bị `KeyFactory` từ chối bằng `InvalidKeySpecException`.
- `invalidBase64Rejected=PASS`: chuỗi Base64 sai cú pháp bị từ chối trước bước parse key.

Private key được tạo tạm thời mỗi lần chạy. **Không** dùng kỹ thuật lấy pin trong cùng process như bằng chứng bảo mật cho request từ mạng. Điểm an toàn phụ thuộc **nguồn của expectedPin**, chứ không phải sức mạnh của `SHA-256` khi so sánh một giá trị không được tin cậy.

## 6. Quy trình tích hợp vào hệ thống thực

Một dịch vụ xác minh thông điệp có thể áp dụng thứ tự sau:

1. **Xác định issuer/tenant mong đợi** từ endpoint, access policy hoặc ngữ cảnh đã xác thực; không mặc định tin trường issuer nằm trong payload.
2. **Chọn thuật toán bằng policy**, chẳng hạn `Ed25519` cho issuer tương ứng. Không để header yêu cầu thuật toán ngoài allowlist, kể cả `none`.
3. **Tìm public key được phép** theo issuer + `kid` trong registry đã xác thực. `kid` chỉ là gợi ý tra khóa, không là chứng minh danh tính.
4. Nếu key đi kèm chứng chỉ, **xác thực certificate path và quyền sử dụng** trước khi dùng `getPublicKey()`. Nếu key đi kèm SPKI, so fingerprint với pin đã provision an toàn hoặc chứng thực bằng trust policy tương đương.
5. Kiểm tra tình trạng key: `active`, chưa bị thu hồi, đúng purpose, còn trong thời gian được phép ký, đúng tenant.
6. Kiểm tra bytes của payload: format, giới hạn kích thước, charset/serialization/canonicalization, version schema.
7. Dùng `Signature.initVerify → update → verify`; chỉ chấp nhận kết quả `true` khi các điều kiện trust đã đạt.
8. Kiểm tra anti-replay/freshness (nonce, sequence, thời hạn, audience) đã được gắn vào phần dữ liệu có chữ ký.
9. **Fail closed**: mọi lỗi parse, decode, key mismatch, `SignatureException`, lỗi PKIX hoặc `verify=false` đều không cho phép xử lý giao dịch như đã xác thực.

Chỉ kiểm tra chữ ký toán học với một khóa hợp lệ về định dạng **không bảo đảm** khóa được cấp đúng quyền để duyệt đơn hàng, chuyển tiền, phát hành artifact hoặc xác nhận danh tính.

### Ví dụ metadata registry (chỉ minh họa)

```json
{
  "issuer": "vendor-A",
  "kid": "ed25519-2026-01",
  "algorithm": "Ed25519",
  "spkiSha256": "BASE64_OF_TRUSTED_DIGEST",
  "status": "ACTIVE",
  "purpose": "order-approval",
  "notBefore": "2026-01-01T00:00:00Z",
  "notAfter": "2027-01-01T00:00:00Z"
}
```

Đây là **mô hình dữ liệu giả định**, không phải schema chuẩn cho mọi giao thức. Registry chỉ đáng tin khi **quá trình tạo/cập nhật nó được xác thực, kiểm soát quyền và audit**. Nếu attacker sửa được cả mapping `issuer → pin`, mọi phép so sánh sau đó đều có nguy cơ chấp nhận khóa giả.

## 7. Phân phối qua HTTPS có đủ không?

HTTPS cung cấp tính toàn vẹn và xác thực **endpoint TLS** theo chính sách trust và hostname verification. Nó có thể là một kênh hữu ích để lấy public key của issuer, nhưng cần làm rõ:

- Endpoint URL/domain phải **được cấu hình hoặc phát hiện qua nguồn tin cậy** phù hợp với issuer; không cho payload không tin cậy tự chọn URL khóa.
- Phải dùng TLS certificate validation và hostname verification; **không cài TrustManager chấp nhận mọi chứng chỉ** hoặc tắt kiểm tra hostname.
- Xác thực endpoint phân phối **không tự đồng nghĩa** mọi khóa trong response được phép ký mọi loại tài liệu. Cần mapping identity/purpose.
- Cần giới hạn redirects, kích thước dữ liệu, timeout, cache, keyset version và phương pháp chống rollback.
- Nếu quy trình yêu cầu độ bảo đảm cao, có thể bổ sung chữ ký của một trust anchor trên manifest khóa.

Java có API `java.net.http.HttpClient` cho HTTPS; cách dùng cụ thể phụ thuộc trust store và cơ chế xác thực endpoint trong sản phẩm. Ví dụ chạy độc lập phía trên không tạo HTTP request để tránh nhầm rằng một URL tùy ý tự mang lại niềm tin.

**Lưu ý vận hành:** SPKI pinning trong TLS khác với pin fingerprint của **application signing key**. Chúng có thể liên quan nhưng thuộc các chính sách khác nhau. Không nên coi một certificate TLS hợp lệ là giấy phép ký mọi payload nghiệp vụ.

## 8. Key rotation, thu hồi và chống rollback

Một hệ thống có cơ chế nguồn khóa tốt phải có kế hoạch khi khóa hết hạn, bị mất, bị lộ hoặc cần thay thuật toán.

### 8.1. Thay khóa có kiểm soát

1. Tạo cặp khóa mới, bảo vệ private key trong giải pháp quản lý khóa phù hợp (keystore/KMS/HSM theo chính sách).
2. Đăng ký public key mới vào registry đáng tin, gắn `kid` mới, issuer, purpose và mốc hiệu lực.
3. Phân phối metadata khóa mới **qua kênh được xác thực**. Nếu dùng pinning, hỗ trợ giai đoạn chuyển đổi có giới hạn hoặc quy trình recovery đã định trước.
4. Sau khi verifier đã biết khóa mới, chuyển bên ký sang khóa đó.
5. Ngừng chấp nhận khóa cũ theo chính sách, trừ khi có quy tắc riêng cho xác minh **chữ ký lịch sử**.
6. Khi nghi ngờ private key lộ, thực hiện **thu hồi khẩn cấp** và không tiếp tục chấp nhận request mới ký bằng khóa đó.

Cẩn thận với bản keyset cũ nhưng chữ ký manifest vẫn đúng: attacker có thể replay keyset đã hết hiệu lực và **khôi phục khóa bị thu hồi**. Metadata cần version/sequence hoặc monotonic epoch, expiry và cơ chế từ chối rollback; các trường này phải được bảo vệ trong phần manifest có chữ ký.

### 8.2. Chữ ký tài liệu cũ và request mới

Xác minh chữ ký trên tài liệu lưu trữ nhiều năm có thể cần giữ public key/chứng chỉ cũ và bằng chứng thời điểm ký. Nhưng điều đó khác với việc **cho phép một khóa đã bị thu hồi ký giao dịch mới**. Phải phân biệt policy “historical verification” với “current authorization”.

**Đừng chỉ dựa vào `Signature.verify == true` để quyết định quyền theo thời gian**: API chữ ký không biết trạng thái active/revoked hay quy tắc của ứng dụng.

## 9. Ràng buộc chữ ký với ngữ cảnh và chống replay

Ngay cả khi public key **đúng và được tin cậy**, attacker vẫn có thể phát lại nguyên văn một request trước đó cùng chữ ký. Chữ ký không tự đảm bảo request là mới.

Tùy giao thức, các trường sau nên nằm trong phần dữ liệu **được ký**:

- Issuer/tenant, audience và mục đích sử dụng.
- Payload nghiệp vụ và version schema.
- Timestamp, expiry window, nonce/request ID hoặc sequence number.
- Những tham số nhạy cảm như amount, recipient, permission scope.
- Thông tin context cần để tránh cùng chữ ký được dùng ở giao thức khác (domain separation).

Server cần lưu/kiểm tra nonce hoặc sequence theo policy để **ngăn replay**. Nếu thời hạn/nonce được truyền ngoài dữ liệu ký mà không có bảo vệ khác, attacker có thể tự sửa nó.

Với JSON, hai đoạn có cấu trúc giống nhau nhưng thứ tự field/whitespace khác có thể mang **bytes khác nhau**. Java `Signature` xác minh trên **đúng bytes mà bạn đưa vào `update`**, không canonicalize JSON. Hãy thống nhất raw bytes hay chuẩn canonicalization, charset và newline.

## 10. Kiểm thử các trường hợp phải từ chối

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Đúng issuer, đúng key đã xác thực và chữ ký hợp lệ | Chấp nhận nếu policy/freshness cũng đạt |
| Message bị sửa sau khi ký | Từ chối vì chữ ký không hợp lệ |
| Attacker tự ký bằng private key của mình, cung cấp public key tương ứng | `verify` với key attacker **có thể true**, nhưng **trust check phải từ chối** |
| Base64 của public key sai cú pháp | `IllegalArgumentException` từ decoder, từ chối |
| SPKI hỏng hoặc sai thuật toán | `InvalidKeySpecException`/lỗi parse, từ chối |
| Key ID không có trong registry | Từ chối, không tự tải endpoint chưa tin cậy |
| Issuer hoặc tenant không khớp quyền khóa | Từ chối dù chữ ký toán học đúng |
| Khóa hết hạn hoặc bị thu hồi | Từ chối request mới |
| Keyset có chữ ký nhưng là phiên bản cũ đã bị rollback | Từ chối theo anti-rollback policy |
| Header yêu cầu thuật toán khác policy | Từ chối, không algorithm downgrade |
| Request đã xử lý trước đó được phát lại nguyên văn | Từ chối theo nonce/sequence/time window |
| Chứng chỉ X.509 parse được nhưng chain không có trust anchor hợp lệ | Từ chối, parse không phải PKIX validation |

### Đừng quên đường lỗi

Đối với Java, cần xử lý:

- `IllegalArgumentException` khi Base64 sai hoặc dữ liệu request có offset/độ dài không hợp lệ.
- `InvalidKeySpecException` khi SPKI không tạo được khóa theo thuật toán yêu cầu.
- `InvalidKeyException` khi thuật toán chữ ký không nhận khóa.
- `SignatureException` khi trạng thái hoặc chữ ký không được engine xử lý bình thường.
- `NoSuchAlgorithmException` nếu thuật toán/provider không sẵn có.
- `CertPathValidatorException` hoặc lỗi PKIX/JSSE khi chain/trust không hợp lệ.

**Không được** biến bất cứ exception nào thành xác thực thành công. Một hệ thống có thể trả lỗi bên ngoài thống nhất để tránh lộ thông tin, trong khi log nội bộ vẫn phân biệt `UNTRUSTED_KEY`, `BAD_FORMAT`, `INVALID_SIGNATURE`, `EXPIRED_OR_REVOKED_KEY` và `SYSTEM_ERROR`.

## 11. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tin ngay public key đính kèm request | Kẻ tấn công tự ký hợp lệ bằng khóa của mình | Xác thực nguồn khóa độc lập với payload |
| Tính `expectedPin` từ chính khóa nhận | So sánh luôn đúng | Lưu pin/key đã phê duyệt từ nguồn an toàn |
| Nhầm SPKI với chứng chỉ X.509 | Tưởng `KeyFactory` đã xác minh CA | Dùng PKIX hoặc pinning đúng policy |
| Chỉ gọi `certificate.checkValidity()` | Không kiểm tra chain, issuer và purpose | Xác thực đầy đủ cert path/danh tính |
| Cho phép tải `jku` tự do từ request | SSRF/key substitution | Allowlist nguồn, ràng buộc issuer |
| Tin `kid` như chữ ký hoặc mật khẩu | Kẻ tấn công ghi được `kid` bất kỳ | `kid` chỉ lookup vào registry đã tin |
| Tin `alg` do attacker chọn | Rủi ro algorithm confusion/downgrade | Algorithm allowlist cố định theo issuer |
| Tắt hostname validation hoặc dùng accept-all TrustManager | Mất xác thực TLS | Sử dụng JSSE/trust store chuẩn |
| Pin một khóa không có backup/rotation | Khóa đổi gây mất kết nối | Quy trình thay pin và phục hồi có kiểm soát |
| Không chặn keyset rollback | Khóa đã thu hồi có thể tái xuất hiện | Version/expiry/monotonic state được bảo vệ |
| Không kiểm tra tenant/purpose | Chữ ký của bên A bị dùng cho bên B | Ràng buộc issuer, scope, purpose với khóa |
| Không kiểm tra chống replay | Request cũ ký đúng được dùng nhiều lần | Nonce/sequence/expiry trong message ký |
| So sánh SPKI pin với hash cả chứng chỉ | Hai fingerprint không cùng đối tượng | Thống nhất SPKI DER hoặc certificate DER |
| In private key ra log | Lộ quyền ký | Bảo vệ private key, không log secret |
| Cho rằng SHA-256 pin tự tạo ra nguồn tin cậy | Fingerprint chỉ băm bytes | Nguồn expected pin mới là trust anchor |
| Chỉ nhìn `verify == true` rồi cấp quyền | Thiếu identity, key status, replay policy | Thực hiện full trust + signature + policy |

## 12. Bài tập và đáp án

**Bài 1.** Một server nhận public key, message và chữ ký từ request; `Signature.verify(...)` trả true. Server đã chứng minh đây là message của đối tác A chưa?

**Đáp án:** Chưa. Server mới chứng minh chữ ký khớp với key **được request cung cấp**. Phải kiểm tra key thuộc A qua nguồn tin cậy.

**Bài 2.** Có thể dùng `X509EncodedKeySpec` thành công để kết luận khóa đã được CA cấp và xác thực không?

**Đáp án:** Không. SPKI chỉ biểu diễn public key. Certificate chain và trust anchor là khái niệm khác.

**Bài 3.** Vì sao cách tính `expectedPin = SHA256(receivedKey.getEncoded())` ngay khi nhận request rồi so với chính received key là sai?

**Đáp án:** Vì attacker kiểm soát cả candidate lẫn “expected”, khiến kết quả luôn khớp. Expected pin phải đến từ một quá trình provision độc lập đáng tin.

**Bài 4.** `kid` có chứng minh danh tính người ký không? Nếu `kid` không có trong registry, có nên tải URL `jku` tùy ý từ request không?

**Đáp án:** `kid` không phải bằng chứng danh tính, chỉ giúp chọn khóa từ registry. Không tải tùy ý vì rủi ro nguồn khóa giả và SSRF.

**Bài 5.** Khi private key cũ bị lộ nhưng chữ ký bằng nó vẫn verify true, có nên chấp nhận request mới?

**Đáp án:** Không. Phép toán không kiểm tra trạng thái thu hồi; phải áp dụng chính sách key revocation/validity.

**Bài 6.** Một giao dịch đã được xác minh thành công hôm qua. Ngày nay attacker gửi lại nguyên vẹn chữ ký và bytes. Điều gì còn thiếu?

**Đáp án:** Chống replay bằng nonce/sequence, timestamp/expiry, audience và dữ liệu signed context được kiểm tra ở server.

## Ghi nhớ

**Public key công khai nhưng nguồn của nó phải xác thực.** Định dạng SPKI/Base64, chứng chỉ X.509 hay danh sách JWKS chỉ là phương tiện phân phối. Một khóa được coi là đáng tin khi nó được ràng buộc với issuer/tenant/purpose bởi trust anchor độc lập, thông qua provision an toàn, PKIX hoặc metadata có chữ ký hợp lệ. Chỉ sau đó Java mới dùng `Signature.initVerify → update → verify` để kiểm tra bytes. Kết quả `true` của chữ ký **không** thay thế xác thực nguồn khóa, hạn sử dụng, trạng thái thu hồi và chống replay.

### Tài liệu còn áp dụng

- [Java SE 17 — PublicKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/PublicKey.html)
- [Java SE 17 — X509EncodedKeySpec / SubjectPublicKeyInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html)
- [Java SE 17 — KeyFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyFactory.html)
- [Java SE 17 — Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [Java SE 17 — MessageDigest và isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
- [Java SE 17 — CertPathValidator (PKIX)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [Oracle Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html)
- [OpenJDK JEP 339 — EdDSA từ Java 15](https://openjdk.org/jeps/339)
