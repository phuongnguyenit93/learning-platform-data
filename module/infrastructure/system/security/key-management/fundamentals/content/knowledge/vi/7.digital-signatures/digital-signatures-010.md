# Lưu trữ public verification key — Bảo vệ khóa công khai dùng để xác minh chữ ký số

## 1. Public verification key là gì?

**Public verification key** là **khóa công khai được dùng để xác minh chữ ký số** tương ứng với một khóa riêng (private signing key). Một bên tạo chữ ký bằng khóa riêng, các bên khác dùng khóa công khai đúng cặp để kiểm tra chữ ký trên **chính xác dữ liệu đã được ký**.

Điểm đặc biệt: **public verification key không phải bí mật**. Tuy nhiên, hệ thống cần bảo đảm khóa **đúng nguồn gốc, đúng người ký, không bị đánh tráo và còn được phép sử dụng**. Nếu kẻ tấn công thay khóa công khai trong kho xác minh bằng khóa của họ, họ có thể ký dữ liệu giả bằng private key của mình rồi khiến ứng dụng chấp nhận như dữ liệu từ người ký hợp lệ.

Ví dụ, nền tảng cập nhật phần mềm nhận một gói ứng dụng cùng chữ ký số của nhà phát hành. Máy khách giữ public verification key đã được xác thực và chỉ cài đặt gói khi chữ ký hợp lệ dưới **khóa nhà phát hành đã tin cậy**. Nếu máy khách tải một public key bất kỳ từ cùng nơi cung cấp gói mà không xác thực khóa, kẻ tấn công có thể thay cả gói, chữ ký và khóa để vượt qua kiểm tra.

Trong chương **Chữ ký số** của học phần **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, lưu trữ khóa công khai là một mắt xích của vòng đời khóa: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Nội dung liên hệ mật mã bất đối xứng, chữ ký số, mô hình tin cậy, KMS/HSM, kiểm soát truy cập và kiểm toán để thiết kế hệ thống xác minh chữ ký an toàn.

> **Nguyên tắc:** Có thể công bố public key rộng rãi, nhưng không được tin một public key chỉ vì nó đọc được, có định dạng hợp lệ hoặc đi kèm một chữ ký xác minh thành công. Phải có **căn cứ tin cậy độc lập** liên kết khóa đó với danh tính và mục đích của người ký.

## 2. Phân biệt khóa xác minh, khóa ký và các khóa khác

| Thành phần | Vai trò | Yêu cầu bảo mật chính |
| --- | --- | --- |
| **Private signing key** | Tạo chữ ký số | Bí mật tuyệt đối, giới hạn quyền Sign, bảo vệ trong KMS/HSM khi phù hợp |
| **Public verification key** | Kiểm tra chữ ký được tạo bởi private key tương ứng | Không cần bí mật; cần bảo đảm tính toàn vẹn, tính xác thực, liên kết danh tính và trạng thái tin cậy |
| **Public encryption key** | Mã hóa/đóng gói bí mật cho người nhận trong sơ đồ được hỗ trợ | Phải xác thực đúng người nhận, nhưng công dụng khác khóa xác minh chữ ký |
| **DEK** | Mã hóa dữ liệu bằng thuật toán đối xứng, ví dụ AES-GCM | Phải bí mật; thường được wrap khi lưu trữ |
| **KEK** | Bảo vệ hoặc wrap các khóa khác | Kiểm soát quyền Wrap/Unwrap, có thể quản lý qua KMS/HSM |
| **MAC key** | Tạo/kiểm tra mã xác thực thông điệp như HMAC | Bí mật chung giữa các bên được phép; không có đặc tính xác minh công khai như chữ ký số |

Khi dùng chữ ký số, phép kiểm tra khái niệm là:

~~~text
signature = Sign(privateSigningKey, messageBytes, signingParameters)

valid = Verify(
    trustedPublicVerificationKey,
    messageBytes,
    signature,
    verificationParameters
)
~~~

Kết quả **valid = true** chỉ có giá trị nghiệp vụ khi **trustedPublicVerificationKey** đã được liên kết với đúng người ký và được cho phép với loại thông điệp đó. Một chữ ký hợp lệ dưới khóa công khai bất kỳ **không chứng minh** người ký đúng danh tính.

Không gọi chữ ký số là “mã hóa bằng private key”: chữ ký và mã hóa là các primitive khác nhau, có thuật toán, định dạng và mục tiêu bảo mật riêng. Public verification key được dùng cho **Verify**, không dùng để giải mã dữ liệu bí mật.

## 3. Mục tiêu bảo mật khi lưu public verification key

### 3.1. Tính xác thực (authenticity)

Hệ thống phải biết **khóa thuộc về ai**, tổ chức hay ứng dụng nào được quyền tạo chữ ký, và khóa đó được cấp phát qua quy trình tin cậy nào.

Ví dụ, khóa xác minh chữ ký của dịch vụ A cần gắn với danh tính **service-A/production** thay vì chỉ ghi “RSA public key”. Nếu chỉ gắn một khóa tùy ý với tên A, mọi kết quả Verify về sau đều có thể bị hiểu sai.

### 3.2. Tính toàn vẹn (integrity)

Các byte của khóa, định danh khóa và metadata quan trọng không được thay đổi trái phép. Cần bảo vệ cả:

- Vật liệu public key và định dạng của nó;
- **Key ID (kid), phiên bản, thuật toán, mục đích (Verify), danh tính người ký**;
- Thông tin hiệu lực, thu hồi, chính sách chấp nhận và đường dẫn tới nguồn cung cấp khóa.

Đây là lý do public key tuy không bí mật nhưng **không nên cho mọi tài khoản sửa** trong cơ sở dữ liệu, kho cấu hình hoặc key registry.

### 3.3. Tính sẵn sàng và khả năng xác minh lại

Hệ thống cần truy xuất được đúng khóa công khai khi kiểm tra chữ ký hiện tại và trong các tình huống nghiệp vụ cần **xác minh chữ ký lịch sử**. Mất khóa công khai, certificate chain hoặc metadata phiên bản có thể khiến dữ liệu đã ký khó được xác minh, dù chữ ký và tài liệu vẫn tồn tại.

Tùy chính sách, cần duy trì bản sao khóa công khai, chứng chỉ, chuỗi tin cậy, trạng thái thu hồi và bằng chứng thời gian cho các giao dịch cần lưu trữ lâu dài.

### 3.4. Kiểm soát quyền và truy vết

Nên tách quyền **đọc khóa để Verify** khỏi quyền **đăng ký, thay thế, đánh dấu tin cậy, thu hồi hoặc xóa khóa**. Ghi nhận ai thay đổi ánh xạ danh tính–khóa và thời điểm thay đổi; đây thường là sự kiện rủi ro cao hơn một lần đọc public key.

Khóa công khai không đòi hỏi bảo mật nội dung như private key, nhưng thông tin về tenant, tổ chức, quan hệ đối tác hoặc sơ đồ hạ tầng đi cùng metadata vẫn có thể cần phân quyền xem theo chính sách.

## 4. Nguồn tin cậy quyết định cách lưu khóa

“Lưu khóa công khai” không chỉ là ghi một file PEM. Cần làm rõ **vì sao file đó được tin**.

| Mô hình tin cậy | Khóa được lấy từ đâu? | Điều phải xác thực |
| --- | --- | --- |
| **Provisioning trực tiếp** | Khóa được quản trị viên hoặc pipeline đáng tin cậy đưa vào cấu hình | Quy trình phê duyệt, dấu vân tay/fingerprint, nguồn cấp, quyền sửa và lịch sử phiên bản |
| **Key pinning** | Ứng dụng lưu fingerprint hoặc public key đã xác minh từ trước | Tham chiếu pin đến từ nguồn tin cậy độc lập; có kế hoạch thay pin khi xoay vòng |
| **PKI / X.509** | Chứng chỉ chứa public key, có thể đi kèm chuỗi CA | Trust anchor, chữ ký chuỗi, danh tính, Key Usage, thời hạn và trạng thái thu hồi theo chính sách |
| **JWKS được quản lý** | Tập JSON Web Key công bố bởi nhà phát hành token | Endpoint và issuer được cấu hình tin cậy, TLS, key ID, thuật toán, vòng đời và quyền thay đổi JWKS |
| **Trust anchor phần cứng** | Public key hoặc hash khóa được ghi vào phần cứng / vùng boot đáng tin cậy | Chuỗi khởi động tin cậy, cơ chế cập nhật khóa và chống rollback theo kiến trúc thiết bị |

**Không có mô hình nào an toàn chỉ vì định dạng đẹp hoặc đường dẫn có chữ “trusted”.** Cần quản lý nguồn gốc khóa ở lúc **đăng ký ban đầu (bootstrap trust)** và mỗi lần cập nhật.

### 4.1. Lưu khóa trực tiếp trong cấu hình hoặc cơ sở dữ liệu

Phương án này thường phù hợp khi số người ký ít và quan hệ tin cậy ổn định, ví dụ một ứng dụng Java chỉ nhận file ký bởi một nhà cung cấp đã biết.

Cần có bước **xác minh out-of-band** (qua kênh độc lập đáng tin cậy) hoặc quy trình phát hành được phê duyệt trước khi lưu khóa. Sau khi đăng ký, lưu kèm danh tính người ký, key ID, phiên bản, thuật toán được phép, mục đích sử dụng và fingerprint.

Kho lưu trữ phải có quyền ghi hạn chế, lịch sử thay đổi, sao lưu và khả năng phát hiện sửa trái phép. Đặt public key trong Git có thể phù hợp khi repository, quy trình review và pipeline triển khai được bảo vệ; **chỉ commit vào Git không tự chứng minh khóa đúng chủ thể**.

### 4.2. Lưu chứng chỉ X.509 và chuỗi tin cậy

Trong PKI, một **chứng chỉ X.509** chứa public key cùng thông tin danh tính, hiệu lực, mục đích sử dụng và chữ ký CA. Ứng dụng cần xác minh chứng chỉ theo **trust anchor** tin cậy và các chính sách áp dụng.

Các bước thường gồm:

1. Khởi tạo **truststore** chứa root CA hoặc trust anchor được phê duyệt, được phân phối và cập nhật an toàn.
2. Kiểm tra chứng chỉ liên quan và chữ ký trong chuỗi CA, độ dài/thuật toán được phép, ràng buộc CA, hiệu lực và đường đi tin cậy.
3. Ràng buộc **danh tính người ký** với subject/SAN hoặc identifier theo mô hình chứng chỉ ứng dụng; không mặc định chỉ có chứng chỉ hợp lệ là có quyền ký mọi loại tài liệu.
4. Kiểm tra **Key Usage** thích hợp (ví dụ digitalSignature) và **Extended Key Usage** nếu ứng dụng/chính sách yêu cầu.
5. Xử lý **CRL/OCSP** hoặc bằng chứng thu hồi theo chính sách và mô hình online/offline; không coi “chữ ký chứng chỉ CA hợp lệ” là đủ trong mọi trường hợp.

**Chứng chỉ tự ký** (self-signed) không tự trở thành đáng tin. Độ tin cậy đến từ việc trust anchor được chấp nhận theo quy trình phù hợp.

### 4.3. Công bố khóa qua JWKS

Trong hệ thống OAuth/OIDC hoặc JWT có chữ ký, nhà phát hành (issuer) có thể công bố public verification key qua **JWKS (JSON Web Key Set)**. Ứng dụng xác minh có thể tải JWKS từ một endpoint **đã cấu hình tin cậy** và giữ cache.

Việc chỉ tìm thấy **kid** trong một JWKS không đủ để chấp nhận chữ ký. Phải xác định **đúng issuer**, chính sách thuật toán, đúng key type và phạm vi token, rồi kiểm tra các claim nghiệp vụ liên quan.

Không tự động truy cập URL do một token chưa xác thực cung cấp trong các trường như **jku** hoặc **x5u**. Đây có thể là đường dẫn do kẻ tấn công kiểm soát, dẫn đến **key substitution**, SSRF hoặc nhầm miền tin cậy.

## 5. Các định dạng và metadata cần lưu

### 5.1. SPKI/DER, PEM, chứng chỉ và JWK khác nhau thế nào?

| Định dạng | Nội dung điển hình | Khi nào dùng? |
| --- | --- | --- |
| **SubjectPublicKeyInfo (SPKI) ở DER** | Cấu trúc ASN.1 mã hóa thuật toán và public key | Lưu/trao đổi public key, phù hợp với **X509EncodedKeySpec** trong Java |
| **PEM PUBLIC KEY** | SPKI/DER được Base64 và bọc bằng dòng BEGIN/END PUBLIC KEY | File cấu hình hoặc trao đổi public key dạng văn bản |
| **X.509 certificate (DER/PEM)** | Chứng chỉ chứa SPKI, danh tính và chữ ký CA | Mô hình PKI, xác thực chuỗi chứng chỉ và chính sách danh tính |
| **JWK / JWKS** | Biểu diễn public key bằng JSON theo kiểu RSA, EC hoặc OKP; JWKS là tập các JWK | API, token có chữ ký, tích hợp OAuth/OIDC |
| **Fingerprint (SHA-256 của SPKI/DER)** | Giá trị băm cố định của byte SPKI đã được xác thực | Pinning/đối chiếu đúng khóa, hỗ trợ quản trị và phát hiện thay thế |

Đặc biệt, **X509EncodedKeySpec không nhận nguyên một chứng chỉ X.509**. Tên lớp “X509” dễ gây nhầm: dữ liệu nó nhận là **SPKI public key encoding**; khi có chứng chỉ, cần parse/kiểm tra chứng chỉ trước rồi trích public key.

Ví dụ cấu trúc PEM chứa public key (chỉ là mẫu định dạng, không phải khóa hợp lệ):

~~~text
-----BEGIN PUBLIC KEY-----
<Base64 của SubjectPublicKeyInfo DER>
-----END PUBLIC KEY-----
~~~

Với RSA JWK, khóa công khai thường gồm **kty = RSA**, **n** (modulus) và **e** (public exponent). Với EC JWK là **kty = EC**, **crv**, **x**, **y**; với Ed25519 thường là **kty = OKP**, **crv = Ed25519**, **x**. **Không được vô tình công bố các thành phần private key** như **d** hoặc các tham số private RSA trong JWKS.

Các trường metadata như **alg**, **use**, **key_ops**, **kid**, **x5c** có thể có trong JWK. Chúng giúp biểu diễn ý định sử dụng, nhưng việc xuất hiện trong JSON **không tự cấp quyền tin cậy** cho khóa. Nếu dùng **x5c**, cần kiểm tra chứng chỉ và bảo đảm public key trong chứng chỉ khớp với vật liệu JWK.

### 5.2. Metadata tối thiểu cho một key registry

Một bản ghi khóa xác minh có thể chứa:

| Trường | Ví dụ | Tại sao cần? |
| --- | --- | --- |
| **keyId / kid** | signer-prod-2026-02 | Chọn đúng khóa trong tập khóa, đặc biệt khi xoay vòng |
| **owner / signerId** | service-invoice-prod | Ràng buộc khóa với chủ thể được phép ký |
| **purpose** | verify-invoice | Ngăn khóa của mục đích khác được chấp nhận |
| **algorithm / parameters** | RSASSA-PSS, SHA-256, MGF1 SHA-256, salt 32 | Không tự lấy thuật toán từ payload chưa tin cậy |
| **publicKeyEncoding** | SPKI DER / PEM / JWK | Parse và kiểm tra theo đúng định dạng |
| **fingerprint** | SHA-256(SPKI DER) | Kiểm tra tính nhất quán và quản lý thay đổi |
| **trustSource** | PKI chain / pinned config / trusted JWKS issuer | Chứng minh nguồn gốc của khóa |
| **activatedAt, retiredAt, status** | active / verify-only / revoked | Quản lý thời điểm cho phép ký mới hoặc chỉ xác minh cũ |
| **policyVersion / audit references** | policy-v4 | Truy vết quyết định cấp phát, thay quyền và thu hồi |

**Key ID không phải bí mật và không phải bằng chứng tin cậy.** Hai hệ thống hoặc hai issuer có thể sử dụng cùng một **kid**. Không nên dùng mỗi kid để tìm khóa trong một kho toàn cục rồi bỏ qua owner, issuer, tenant và mục đích.

### 5.3. Nên lưu bao nhiêu bản sao?

Vì public verification key không bí mật, việc sao lưu hoặc phân phối nhiều bản sao **có thể hỗ trợ sẵn sàng**. Nhưng bản sao vẫn cần bảo vệ tính toàn vẹn và xác thực nguồn: một cache bị thay khóa cũng nguy hiểm như kho dữ liệu gốc bị sửa.

Đối với chữ ký cần kiểm tra nhiều năm sau, có thể cần giữ **khóa công khai cũ, chứng chỉ, chuỗi xác minh, bằng chứng thời gian và trạng thái thu hồi tại thời điểm ký** theo chính sách lưu trữ dài hạn, thay vì chỉ lưu key “đang active”.

## 6. Kiến trúc lưu trữ và xác minh an toàn

~~~mermaid
flowchart TD
    SRC["Nguồn cấp khóa đáng tin cậy<br/>PKI / quản trị / JWKS của issuer"]
    REG["Kho public verification key<br/>keyId + signer + thuật toán + trạng thái"]
    AUD["Audit log<br/>cấp phát, sửa, thu hồi, truy xuất"]
    MSG["Thông điệp + chữ ký + keyId"]
    VER["Dịch vụ xác minh Java"]
    POLICY["Chính sách tin cậy<br/>issuer, tenant, purpose, version"]
    DEC{"Verify hợp lệ<br/>và người ký được phép?"}
    OK["Chấp nhận và xử lý nghiệp vụ"]
    REJ["Từ chối, ghi nhận lý do phù hợp"]
    SRC -->|"Đăng ký / cập nhật đã xác thực"| REG
    REG -->|"Thay đổi có kiểm soát"| AUD
    MSG --> VER
    REG --> VER
    POLICY --> VER
    VER --> DEC
    DEC -->|"Có"| OK
    DEC -->|"Không"| REJ
~~~

Luồng an toàn nên diễn ra như sau:

1. **Bootstrap trust:** Quản trị viên, pipeline được kiểm soát hoặc dịch vụ PKI xác thực nguồn public verification key trước khi đưa vào kho.
2. **Bảo vệ đăng ký khóa:** Chỉ vai trò được phép mới có thể tạo/thay/tháo khóa và thay trạng thái tin cậy; thao tác quan trọng nên có kiểm toán, phê duyệt và lịch sử phiên bản.
3. **Chọn đúng khóa:** Từ đối tượng và ngữ cảnh đã xác thực, xác định tập khóa được phép. Key ID từ thông điệp chỉ là **gợi ý chọn trong tập này**.
4. **Ràng buộc thuật toán:** Xác minh bằng thuật toán và tham số được cấu hình an toàn cho khóa; không tin tùy ý vào giá trị **alg** do bên gửi cung cấp.
5. **Xác minh chữ ký:** Kiểm tra chữ ký trên **đúng byte** mà giao thức quy định, không tự sửa nội dung sau khi ký hay áp dụng canonicalization khác người gửi.
6. **Kiểm tra quyền nghiệp vụ:** Chữ ký đúng chỉ chứng minh một khóa trong tập tin cậy đã ký; vẫn phải kiểm tra người ký có quyền phát hành loại lệnh/tài liệu đó hay không.
7. **Lưu vết:** Ghi fingerprint/keyId/owner, thời điểm, quyết định và chính sách; hạn chế ghi nội dung nhạy cảm trong log.

Hệ thống có thể dùng **KMS/HSM** để lưu và sử dụng private signing key, trong khi public verification key nằm ở kho cấu hình hoặc registry có kiểm soát. **Không bắt buộc phải cất public key vào HSM chỉ để giữ bí mật**. Giá trị chính của HSM nằm ở bảo vệ private key và thao tác Sign; một số hệ thống cũng cung cấp Verify qua HSM, nhưng vẫn phải giải quyết vấn đề nguồn tin cậy của public key.

## 7. Thực hành Java: lưu SPKI public key và xác minh RSA-PSS

Ví dụ sau minh họa cách ứng dụng Java:

- Đọc public verification key **SPKI/DER** đã được cấp phát qua kênh tin cậy.
- Đối chiếu **SHA-256 fingerprint** với giá trị kỳ vọng được bảo vệ độc lập.
- Parse khóa RSA và xác minh chữ ký **RSASSA-PSS/SHA-256**, với tham số PSS cố định theo chính sách.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.security.spec.X509EncodedKeySpec;

public final class TrustedSignatureVerifier {
    private static final PSSParameterSpec PSS_SHA256 =
            new PSSParameterSpec(
                    "SHA-256",
                    "MGF1",
                    MGF1ParameterSpec.SHA256,
                    32, // Salt length 32 byte.
                    1   // Trailer field.
            );

    private TrustedSignatureVerifier() {}

    public static PublicKey loadPinnedRsaPublicKey(
            Path spkiDerPath,
            byte[] expectedSha256OfSpki
    ) throws Exception {
        if (expectedSha256OfSpki == null ||
                expectedSha256OfSpki.length != 32) {
            throw new IllegalArgumentException(
                    "Expected SHA-256 fingerprint must be 32 bytes");
        }

        byte[] spkiDer = Files.readAllBytes(spkiDerPath);
        if (spkiDer.length == 0 || spkiDer.length > 16_384) {
            throw new SecurityException("Invalid SPKI file length");
        }

        byte[] actualHash = MessageDigest.getInstance("SHA-256")
                .digest(spkiDer);
        if (!MessageDigest.isEqual(actualHash, expectedSha256OfSpki)) {
            throw new SecurityException("Public key fingerprint mismatch");
        }

        // X509EncodedKeySpec nhận SubjectPublicKeyInfo DER,
        // không nhận một chứng chỉ X.509 đầy đủ.
        X509EncodedKeySpec keySpec = new X509EncodedKeySpec(spkiDer);
        return KeyFactory.getInstance("RSA").generatePublic(keySpec);
    }

    public static boolean verifyRsaPss(
            PublicKey trustedPublicKey,
            byte[] message,
            byte[] signatureBytes
    ) throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.initVerify(trustedPublicKey);
        verifier.setParameter(PSS_SHA256);
        verifier.update(message);
        return verifier.verify(signatureBytes);
    }
}
~~~

Ví dụ sử dụng **theo luồng khái niệm**:

~~~text
expectedFingerprint = đọc từ cấu hình triển khai đã được xác thực
trustedKey = loadPinnedRsaPublicKey(
    đường dẫn SPKI DER,
    expectedFingerprint
)

message = đúng byte payload mà giao thức quy định
signatureBytes = chữ ký đã giải mã từ định dạng truyền tải

if verifyRsaPss(trustedKey, message, signatureBytes)
   và signer có quyền thực hiện hành động này
   và version/keyId/status hợp lệ:
    xử lý thông điệp
else:
    từ chối
~~~

**Ý nghĩa của bước fingerprint:** Nếu kẻ tấn công chỉ thay **file SPKI DER** nhưng không thay được **expectedFingerprint** được cấp phát độc lập, hệ thống phát hiện sai lệch. Nếu cả file lẫn fingerprint nằm trong cùng một kho không được bảo vệ và kẻ tấn công sửa được cả hai, phép so sánh **không mang lại căn cứ tin cậy**. Việc xác minh danh tính người ký vẫn phải xuất phát từ quy trình provisioning hoặc PKI đúng.

**Lưu ý triển khai:**

- Đây là ví dụ xác minh khóa **RSA** được cấu hình cho **RSASSA-PSS/SHA-256**; với ECDSA hoặc Ed25519 phải dùng API, định dạng và chính sách khác phù hợp.
- Tham số PSS, thuật toán và độ dài khóa cần phù hợp với cặp khóa thực tế, thư viện và giao thức của hai bên. Chỉ đặt một thuật toán là chưa đủ nếu hệ thống không có chính sách chấp nhận người ký.
- Không cấp public key dựa vào dữ liệu **đi kèm chữ ký** mà chưa xác thực nguồn. Tránh tải khóa mới theo URL do message chưa đáng tin cậy tự chỉ định.
- Đối với chứng chỉ X.509, phải **xác minh chuỗi chứng chỉ và ràng buộc danh tính** bằng PKI trước khi trích public key. Đọc **certificate.getPublicKey()** từ một chứng chỉ tự cung cấp **không tự làm khóa trở nên tin cậy**.
- Với dữ liệu JSON/XML, hai bên phải thống nhất canonicalization hoặc xác minh đúng **raw bytes** theo giao thức; chữ ký đúng có thể thất bại nếu bên nhận tự thay đổi biểu diễn.

### 7.1. Chọn kho public key trong Java

| Cách lưu | Ưu điểm | Điều cần kiểm soát |
| --- | --- | --- |
| File SPKI PEM/DER trong cấu hình ứng dụng | Đơn giản, dễ triển khai với ít người ký | Quyền sửa file, checksum/fingerprint tin cậy, release và rotation |
| Java truststore (PKCS#12 hoặc JKS) | Phù hợp các trust anchor/chứng chỉ cần quản lý trong hệ sinh thái Java | Quyền sửa kho, phân phối trust anchor, cập nhật chứng chỉ và kiểm tra PKI |
| Key registry qua database | Quản lý nhiều signer, key ID/version, audit tập trung | Quyền ghi, trạng thái, tenant isolation, bảo vệ trước sửa bản ghi hoặc rollback |
| JWKS cache | Thuận tiện để xác minh JWT/OIDC nhiều key và xoay vòng | Issuer/endpoint cố định, refresh, TTL, xử lý key không tìm thấy và chống key confusion |

Không nên mặc định truststore chứa chứng chỉ public key đồng nghĩa private key cũng nằm ở đó. **Truststore** chủ yếu lưu các thành phần tin cậy cho Verify; **keystore** có thể chứa private key phục vụ Sign và cần mức bảo vệ bí mật cao hơn.

## 8. JWKS và JWT: kiểm tra khóa trong hệ thống nhiều dịch vụ

Với JWT có chữ ký, một luồng xác minh đúng thường là:

~~~mermaid
sequenceDiagram
    participant API as API Java
    participant Config as Cấu hình issuer tin cậy
    participant JWKS as JWKS endpoint được phép
    participant Cache as Cache khóa đã xác minh nguồn
    API->>Config: Lấy issuer, alg và JWKS URL theo policy
    API->>Cache: Tìm key theo issuer + kid + kty + alg
    alt Key chưa có hoặc cần refresh
        API->>JWKS: Tải từ endpoint đã cấu hình qua TLS
        JWKS-->>API: Danh sách JWK
        API->>Cache: Parse, kiểm tra giới hạn và cập nhật có kiểm soát
    end
    Cache-->>API: Candidate public key
    Note over API: Kiểm tra signature và claim iss, aud, exp, nbf,...
    API->>API: Kiểm tra quyền của subject / scope / tenant
~~~

### 8.1. Các quy tắc cần giữ

1. **Trust theo issuer:** Chỉ chấp nhận token từ issuer đã được cấu hình hoặc phát hiện bằng quy trình đáng tin cậy; key từ issuer khác không được dùng để xác minh token này.
2. **Trust theo thuật toán:** Danh sách thuật toán được phép phải đến từ chính sách máy chủ. Không cho JWT header tự quyết định dùng **none**, đổi từ bất đối xứng sang HMAC hay đổi cách giải mã key một cách không kiểm soát.
3. **Kid là nhãn, không là quyền:** Tìm key theo **issuer + kid + loại khóa + mục đích**, không chỉ kid. Kiểm tra key trùng kid hoặc dữ liệu mâu thuẫn theo chính sách.
4. **URL JWKS cố định:** Không lấy địa chỉ JWKS từ **jku/x5u** không tin cậy của token rồi tự tải. Nếu thực sự hỗ trợ các tham chiếu này, cần allowlist và xác thực nghiêm ngặt theo thiết kế.
5. **Kiểm tra claims:** Chữ ký hợp lệ chỉ là một bước. Với JWT, thường cần kiểm tra **iss, aud, exp, nbf** và các ràng buộc thời gian, nonce/token type, scope hay tenant theo ngữ cảnh.
6. **Chống chuyển ngữ cảnh:** Không dùng cùng một tập khóa tin cậy cho mọi token mà bỏ qua mục đích: ID token, access token, token reset mật khẩu và sự kiện đăng nhập có chính sách khác nhau.
7. **Cache và giới hạn nguồn:** Xác định TTL, timeout, kích thước JWKS, số lượng khóa, refresh khi gặp kid chưa biết và cách xử lý lỗi nguồn. Giới hạn refresh để tránh biến token giả thành tấn công làm cạn tài nguyên.

Khi JWKS endpoint tạm thời không truy cập được, một hệ thống có thể tiếp tục dùng **last-known-good keys** đã xác thực nguồn trong giới hạn cache/chính sách được phê duyệt. Không được tự động tin một khóa mới, tắt kiểm tra chữ ký hoặc chấp nhận thuật toán bất kỳ để duy trì availability.

## 9. Xoay vòng, thu hồi và lưu khóa xác minh cũ

### 9.1. Phân biệt vòng đời của private signing key và public verification key

Trong cặp khóa chữ ký số, **private key** có thể được đưa về trạng thái không còn ký mới, trong khi **public key tương ứng vẫn cần thiết** để xác minh các chữ ký đã phát hành trước đó. Nhưng mức độ có thể chấp nhận chữ ký cũ sau khi khóa bị thu hồi phụ thuộc **thời điểm ký, lý do thu hồi, bằng chứng thời gian và chính sách nghiệp vụ/PKI**.

| Trạng thái | Private signing key | Public verification key |
| --- | --- | --- |
| **Active** | Được phép Sign theo chính sách | Được Verify cho mục đích và thời gian áp dụng |
| **Retiring** | Ngừng ký mới sau mốc chuyển đổi | Vẫn có thể cần để kiểm tra message trong cửa sổ chuyển tiếp |
| **Verify-only / historical** | Không còn dùng Sign | Có thể lưu để xác minh chữ ký lịch sử nếu chính sách cho phép |
| **Revoked / compromised** | Phải chặn quyền ký và ứng phó sự cố | Cần ghi lý do, thời điểm ảnh hưởng và áp dụng quy tắc xử lý chữ ký liên quan |
| **Destroyed / retired metadata** | Xóa private key theo chính sách | Public key hoặc chứng chỉ/bằng chứng có thể vẫn được lưu để phục vụ kiểm toán dài hạn |

### 9.2. Quy trình rotation theo giai đoạn

Ví dụ dịch vụ phát hành tài liệu đang ký bằng **private key v1**, muốn chuyển sang **v2**:

1. Sinh cặp khóa mới bằng cơ chế đáng tin cậy; private key v2 được bảo vệ, thường trong KMS/HSM. Xác định thuật toán, key ID và chính sách Verify.
2. Công bố **public key v2** qua nguồn được xác thực (registry, chứng chỉ hoặc JWKS); ghi nhận fingerprint, người sở hữu, phạm vi và thời điểm kích hoạt.
3. Phân phối/refresh cache của bên Verify và kiểm thử toàn bộ luồng trước khi chuyển sang ký v2.
4. Tại mốc chuyển đổi, dừng tạo chữ ký mới bằng v1 và bắt đầu ký bằng v2.
5. Bên Verify chỉ chấp nhận v1/v2 theo key ID, loại chữ ký, thời gian và trạng thái đã được quy định. Theo dõi tỷ lệ xác minh lỗi và các bên chưa cập nhật.
6. Duy trì public key v1 hoặc chứng cứ liên quan nếu cần kiểm tra tài liệu cũ; ngừng chấp nhận v1 cho giao dịch mới theo lịch.
7. Vô hiệu hóa/hủy private key v1 khi nghĩa vụ lưu trữ/khôi phục cho phép; log đầy đủ thay đổi và xác minh lại kết quả.

**Public key không cần bí mật khi “hủy”**, nhưng việc xóa nó khỏi mọi kho có thể làm mất khả năng chứng minh chữ ký lịch sử. Trước khi xóa, cần kiểm tra chính sách lưu giữ và nghĩa vụ kiểm toán.

### 9.3. Khi khóa ký bị nghi xâm phạm

Nếu **private signing key v1 bị lộ**, đối thủ có thể tạo chữ ký giả với v1. Chỉ công bố public key v2 **không làm mất hiệu lực chữ ký giả đã được tạo** và không giải quyết hết các bản sao private key v1.

Quy trình ứng phó thường gồm: thu hồi hoặc chặn v1, phát hành/chuyển sang khóa mới, cập nhật bộ xác minh, kiểm tra các chữ ký trong khoảng ảnh hưởng, rà soát nguồn lộ và bản ghi kiểm toán, đồng thời áp dụng quy trình xử lý chứng chỉ/khóa bị xâm phạm theo chính sách.

Với các chữ ký cũ có giá trị pháp lý hoặc cần kiểm chứng nhiều năm, phải xem xét **bằng chứng thời gian ký và trạng thái chứng chỉ tại thời điểm ký**, không suy luận đơn giản rằng thu hồi hôm nay làm mọi chữ ký quá khứ luôn vô hiệu hoặc luôn hợp lệ.

## 10. Những rủi ro thường gặp khi lưu public verification key

| Tình huống | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Lưu khóa trong database cho phép mọi dịch vụ cập nhật | Đối thủ thay khóa của signer để xác minh chữ ký giả | Giới hạn quyền ghi, phê duyệt, audit và đối chiếu nguồn |
| Tải public key từ đường dẫn do message chưa xác thực chỉ định | Key substitution, SSRF hoặc chuyển miền tin cậy | Endpoint cố định/allowlist và xác minh nguồn |
| Kiểm tra chữ ký với public key đính kèm message mà không có trust anchor | Kẻ giả mạo tạo cặp khóa riêng và tự ký | Xác minh danh tính/key fingerprint qua nguồn đáng tin cậy |
| Chỉ chọn theo kid mà bỏ qua issuer/tenant | Có thể dùng khóa của một issuer/tenant để kiểm tra dữ liệu của bên khác | Ràng buộc issuer + key ID + thuật toán + mục đích |
| Tin vào alg do token tự khai báo | Dễ xuất hiện algorithm confusion, cấu hình yếu | Dùng allowlist thuật toán được cấu hình ở máy chủ |
| Lấy public key từ chứng chỉ tự ký rồi chấp nhận ngay | Bất kỳ ai có thể tạo self-signed certificate | Xây chuỗi tin cậy từ trust anchor đã phê duyệt |
| Không kiểm tra hạn sử dụng/trạng thái thu hồi | Tin khóa hoặc chứng chỉ đã hết thời hạn được phép | Chính sách hiệu lực/thu hồi, kiểm chứng theo thời điểm liên quan |
| Xóa public key cũ ngay khi xoay vòng | Tài liệu cũ không kiểm tra được | Giữ khóa, chứng chỉ và bằng chứng cần thiết theo retention |
| Cache JWKS quá lâu hoặc cache không phân vùng | Chấp nhận key đã bị thu hồi, lẫn issuer | TTL, invalidation, refresh và phân vùng theo issuer |
| Xem chữ ký hợp lệ như đủ quyền nghiệp vụ | Một signer có thể ký thông điệp ngoài phạm vi cho phép | Kiểm tra quyền signer–resource–action sau Verify |
| Không ràng buộc byte được ký | Thay serialization gây lỗi hoặc nhầm nội dung | Quy định canonicalization/raw bytes và định dạng giao thức rõ ràng |
| Không ghi log thay đổi key registry | Khó phát hiện đánh tráo khóa và truy vết sự cố | Audit các sự kiện đăng ký, thay, thu hồi, quyền và fingerprint |

## 11. Tình huống thiết kế: xác minh chữ ký gói cập nhật phần mềm

Một công ty có dịch vụ **phát hành bản cập nhật** dùng private signing key được giữ trong HSM. Khách hàng tải gói cập nhật cùng chữ ký, dùng public verification key đã lưu để quyết định có cài đặt hay không.

**Yêu cầu thiết kế:**

1. Ứng dụng khách được cài sẵn **trust anchor hoặc public key fingerprint** qua quy trình phát hành đáng tin cậy, được bảo vệ khỏi thay đổi trái phép.
2. Gói cập nhật đi kèm thông tin **phiên bản, sản phẩm, kênh phát hành, hash nội dung và key ID**; tất cả thông tin quyết định cài đặt cần nằm trong nội dung được ký hoặc được ràng buộc an toàn.
3. Client kiểm tra chữ ký bằng public key thuộc **nhà phát hành được phép cho sản phẩm đó**, không chỉ kiểm tra có thể Verify dưới bất kỳ key nào.
4. Cần chống **rollback**: một gói cập nhật cũ có chữ ký hợp lệ vẫn có thể không được phép cài đặt nếu nó thấp hơn phiên bản bảo mật tối thiểu. Kiểm tra số phiên bản hoặc mức rollback floor bằng trạng thái đáng tin cậy.
5. Khi chuyển signer key v1 → v2, client phải có cơ chế **nhận và xác thực thông tin khóa mới** trước khi v1 bị ngừng tin cậy. Có thể cần gói chuyển đổi được ký theo chính sách và đường phục hồi khi khóa bị thu hồi.
6. Log theo dõi keyId, fingerprint, phiên bản gói, kết quả Verify và chính sách; không cần lưu private key tại client.

**Phân tích tình huống:**

| Kiểm tra | Nếu bỏ qua sẽ xảy ra điều gì? |
| --- | --- |
| Public key lấy từ nguồn tin cậy | Kẻ tấn công thay gói, chữ ký và public key cùng lúc |
| Chữ ký bao phủ version/product/channel | Gói hợp lệ có thể bị chuyển sang kênh, sản phẩm hoặc ngữ cảnh khác |
| Kiểm tra rollback | Phiên bản có lỗ hổng nhưng chữ ký vẫn đúng có thể được cài lại |
| Key version và kế hoạch rotation | Client cũ không xác minh được bản cập nhật ký bằng khóa mới |
| Chính sách thu hồi và bản ghi kiểm toán | Không biết client nào còn tin khóa đã bị xâm phạm |

Đây cũng là bài học cho hệ thống phát hành hóa đơn, ký báo cáo, xác minh JWT, webhook có chữ ký bất đối xứng và phần mềm nội bộ: **khóa công khai phải được lưu với bằng chứng nguồn gốc và chính sách sử dụng**, vì tính hợp lệ toán học của chữ ký chỉ là một phần quyết định tin cậy.

## 12. Checklist kiểm tra thiết kế lưu trữ public verification key

1. **Danh tính:** Public key thuộc signer nào, tenant nào, môi trường nào, được phép ký loại nội dung nào?
2. **Bootstrap trust:** Lần đầu ứng dụng nhận public key qua kênh hoặc chứng chỉ đáng tin cậy nào?
3. **Định dạng:** SPKI DER, PEM, chứng chỉ X.509 hay JWK/JWKS? Parser có giới hạn đầu vào và nhận đúng cấu trúc không?
4. **Metadata:** Có key ID, thuật toán/tham số, fingerprint, source, mục đích, owner, version, trạng thái và mốc thời gian phù hợp?
5. **Toàn vẹn:** Ai có thể đăng ký hoặc sửa ánh xạ signer–key? Có review, audit và phát hiện thay đổi trái phép?
6. **Chính sách Verify:** Bộ xác minh có chỉ dùng thuật toán/key type trong allowlist, xác thực issuer/danh tính và đúng byte đã ký không?
7. **PKI:** Nếu dùng chứng chỉ, có kiểm tra trust anchor, chuỗi, Key Usage, hiệu lực, danh tính và trạng thái thu hồi theo yêu cầu không?
8. **JWKS:** Có khóa cấu hình issuer/endpoint và giới hạn cache/refresh, tránh tin URL do token chưa xác thực chỉ định?
9. **Quyền nghiệp vụ:** Sau Verify thành công, có kiểm tra signer có quyền phát hành thông điệp hoặc tài liệu đó không?
10. **Rotation:** Đã có kế hoạch phát khóa mới, giai đoạn chồng lấn, xác minh khóa cũ cho lịch sử và quy trình ngừng tin cậy?
11. **Khôi phục:** Có sao lưu bản ghi khóa, certificate chain và bằng chứng thời gian cho các chữ ký cần xác minh lâu dài?
12. **Sự cố:** Nếu private key bị lộ hoặc registry bị đánh tráo, có thể thu hồi, điều tra, cập nhật cache/clients và xử lý chữ ký bị ảnh hưởng?

## 13. Ghi nhớ

- **Public verification key có thể công khai nhưng phải xác thực được nguồn gốc và không bị đánh tráo.** Bảo mật của kho khóa tập trung vào **tính xác thực, toàn vẹn, sẵn sàng và kiểm soát thay đổi**.
- **Public key và private signing key có mức bảo vệ khác nhau:** private key phải giữ bí mật và giới hạn Sign; public key cần được phân phối đúng danh tính và mục đích để Verify.
- **PEM, SPKI/DER, X.509 và JWKS là các dạng biểu diễn/cấp phát khác nhau.** Một khóa đúng định dạng chưa chắc đã được tin cậy.
- **Key ID hoặc fingerprint chỉ có ý nghĩa khi ràng buộc với nguồn tin cậy.** Xác minh chữ ký dưới một khóa do đối thủ tự cung cấp không chứng minh nguồn gốc thông điệp.
- **KMS/HSM, phân quyền, kiểm toán và vòng đời khóa** giúp hệ thống tạo, phân phối, lưu, sử dụng, xoay vòng, thu hồi và hủy khóa có kiểm soát.
- **Luôn tính đến chữ ký lịch sử:** Khi private signing key dừng hoạt động, public verification key và chứng cứ liên quan vẫn có thể cần được lưu theo chính sách.

Trước mỗi quyết định chấp nhận chữ ký, hãy trả lời ba câu hỏi: **“Khóa xác minh này đến từ đâu?”, “Nó được tin cậy để xác minh loại nội dung nào?”, “Nó còn hợp lệ theo chính sách và thời điểm liên quan không?”** Trả lời đúng ba câu hỏi đó mới biến phép Verify từ một kiểm tra toán học thành một quyết định bảo mật có căn cứ.
