# Signature verification

> **Chương:** Chữ ký số  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Signature verification là gì?

**Signature verification (xác minh chữ ký số)** là quá trình kiểm tra một **chữ ký số** có hợp lệ đối với **đúng thông điệp và đúng public key** theo thuật toán, tham số đã quy định hay không. Trong mật mã bất đối xứng, bên ký tạo chữ ký bằng **private key**, còn bên xác minh dùng **public key** tương ứng.

Ví dụ, một hệ thống nhận hóa đơn điện tử kèm chữ ký RSA-PSS. Hệ thống cần kiểm tra: nội dung hóa đơn có còn đúng byte đã ký không, chữ ký có hợp lệ dưới public key tương ứng không, public key đó có thực sự thuộc đơn vị phát hành được chấp nhận không, và đơn vị đó có quyền phát hành loại hóa đơn này không.

Điều quan trọng nhất: **chữ ký hợp lệ về mặt toán học không tự chứng minh danh tính, quyền nghiệp vụ, thời điểm ký hay tính bí mật của dữ liệu**. Signature verification trong hệ thống thực phải là **chuỗi kiểm tra nhiều lớp**, không chỉ một lời gọi `verify(signature)`.

~~~text
                         Thông điệp gốc
                              |
                              v
   Public key đúng ----> Verify(algorithm, params, message, signature)
                              |
                   true / false về mặt mật mã
                              |
             Kiểm tra binding key -> danh tính
                              |
           Kiểm tra thời hạn, thu hồi, chính sách
                              |
             Kiểm tra quyền nghiệp vụ, ngữ cảnh
                              |
                 Chấp nhận hoặc từ chối
~~~

### Mục tiêu học tập

- Hiểu chính xác đầu vào/đầu ra của phép xác minh chữ ký.
- Phân biệt **tính hợp lệ mật mã**, **niềm tin vào khóa/danh tính** và **quyền nghiệp vụ**.
- Biết cách xác minh chữ ký RSA-PSS, ECDSA và Ed25519 bằng thư viện phù hợp.
- Tránh các lỗi định dạng dữ liệu, chọn thuật toán, chọn khóa và kiểm tra chứng thư.
- Kết nối signature verification với KMS/HSM, phân phối public key, cryptoperiod, rotation, thu hồi và kiểm toán.

## 2. Chữ ký số chứng minh được điều gì?

Một lược đồ chữ ký số chuẩn thường có ba thao tác: sinh khóa, ký và xác minh.

~~~text
(publicKey, privateKey) = KeyGen()
signature = Sign(privateKey, message)
valid = Verify(publicKey, message, signature)
~~~

Nếu `valid = true`, kết luận trực tiếp là: **chữ ký tương ứng với thông điệp và public key đã cung cấp, theo lược đồ và tham số đã thực thi**. Để đi xa hơn, ứng dụng phải có bằng chứng về nguồn gốc public key.

| Khẳng định | `Verify = true` có đủ không? | Điều kiện bổ sung |
| --- | --- | --- |
| Thông điệp khớp chữ ký dưới public key đã chọn | **Có, theo giả định an toàn của lược đồ** | Thuật toán được phép, thông số đúng, triển khai an toàn |
| Thông điệp không bị sửa so với nội dung đã ký | Có đối với **đúng byte/phạm vi đã ký** | Không bỏ sót trường và không thay đổi cách mã hóa byte |
| Người ký đúng là tổ chức A | **Không** | Xác thực ràng buộc giữa public key và tổ chức A |
| Tổ chức A có quyền thực hiện giao dịch | **Không** | Kiểm tra chính sách nghiệp vụ và ủy quyền |
| Chữ ký được tạo đúng vào ngày được khai báo | **Không** | Bằng chứng thời gian đáng tin cậy nếu cần |
| Thông điệp không bị đọc trộm | **Không** | Mã hóa riêng (TLS, AES-GCM, ChaCha20-Poly1305...) |
| Thông điệp không bị gửi lại | **Không** | Nonce, sequence number, transaction ID và chống replay |
| Chữ ký chắc chắn có hiệu lực pháp lý | **Không** | Chính sách, quy định áp dụng, quy trình danh tính và bằng chứng |

**Phân biệt với HMAC:** HMAC dùng một secret key chung cho các bên tạo và kiểm tra MAC. Chữ ký số dùng private key để ký và public key để xác minh, nên có thể phân phối khả năng xác minh rộng hơn mà không trao quyền ký. Tuy nhiên, giá trị chứng cứ hay tính không thể chối bỏ trên thực tế vẫn phụ thuộc kiểm soát private key, định danh và hệ thống chứng cứ.

## 3. Các bước của một quy trình xác minh an toàn

### 3.1. Xác định đúng nội dung được ký

Thông điệp đi vào hàm xác minh là **một chuỗi byte cụ thể**, không phải khái niệm nội dung “tương đương”. Ví dụ, hai JSON có cùng dữ liệu nhưng khác thứ tự trường hoặc khoảng trắng có thể tạo chữ ký khác:

~~~json
{"orderId":"O-42","amount":500}
~~~

~~~json
{"amount":500,"orderId":"O-42"}
~~~

Nếu ký trên JSON, hệ thống phải thống nhất **quy tắc canonicalization/serialization** (cách encode Unicode, số, thứ tự trường, escape, loại trường, schema/version), hoặc ký trực tiếp **đúng byte payload** mà hai bên lưu và truyền.

Đối với tài liệu PDF, XML, JSON Web Signature (JWS) hay các định dạng đóng gói khác, cần tuân thủ **quy tắc xác định phạm vi dữ liệu được ký của chính định dạng đó**. Không tự chuẩn hóa thông điệp tùy ý sau khi nhận vì có thể làm mất tương thích hoặc bỏ qua phần dữ liệu đáng lẽ phải được ký.

### 3.2. Xác định thuật toán và tham số được phép

Một bản tin có thể kèm tên thuật toán để bên nhận biết cách xác minh, nhưng **giá trị do bên ngoài gửi không được phép tự quyết định chính sách bảo mật**. Phải có danh sách thuật toán được phê duyệt theo loại đối tượng, issuer và phiên bản giao thức.

Ví dụ:

- **Ed25519:** dùng lược đồ Ed25519 nguyên bản, không tự băm SHA-256 trước rồi gọi Ed25519 như thể cùng một thông điệp.
- **RSA-PSS:** thống nhất hash, MGF1 hash, salt length và các tham số phù hợp.
- **ECDSA:** thống nhất đường cong, hàm băm và định dạng chữ ký (ASN.1 DER hoặc dạng `r || s` cố định theo giao thức).
- **JWS/JWT:** phải phân biệt `RS256`, `PS256`, `ES256` và `EdDSA`; không coi chúng là tên gọi hoán đổi.

Tránh **algorithm confusion** (đánh tráo thuật toán), **downgrade** (hạ cấp sang chế độ yếu) và việc chấp nhận `alg=none` ở chỗ bắt buộc có chữ ký.

### 3.3. Chọn public key từ nguồn tin cậy

Khóa được chọn phải thuộc **đúng issuer, subject, tenant, mục đích và phiên bản**. Key ID như `kid` chỉ là **bộ chọn**, không phải bằng chứng tin cậy. Nếu ứng dụng nhận `kid` từ một token rồi tải khóa từ bất kỳ URL nào do token chỉ định, attacker có thể chuyển hệ thống sang khóa của chính họ.

Một số nguồn public key hợp lệ khi đã xác thực:

| Nguồn | Cách hình thành niềm tin |
| --- | --- |
| **Chứng thư X.509 / PKI** | Xác minh chain tới trust anchor được phê duyệt, danh tính và chính sách |
| **JWKS của issuer** | Issuer/JWKS URL được cấu hình trước, tải qua kênh HTTPS đã xác thực và có chính sách cache |
| **Key registry nội bộ** | Kiểm soát người đăng ký/thay khóa, ràng buộc service/tenant và lịch sử audit |
| **Fingerprint/pinning** | Fingerprint hoặc SPKI pin được cấp qua kênh tin cậy độc lập |
| **SSH host key/host certificate** | Tin theo chính sách TOFU có xác minh bổ sung, hoặc CA SSH đã tin cậy |

**Public key không cần giữ bí mật; ràng buộc public key với danh tính phải được xác thực.** Chỉ vì khóa xuất hiện trong cùng request với chữ ký không có nghĩa được phép dùng khóa đó để tin danh tính được tuyên bố.

### 3.4. Thực hiện phép xác minh mật mã

Thư viện nhận đúng public key, thông điệp, chữ ký và tham số rồi trả kết quả. Nếu sai, **từ chối** thay vì thử nhiều thuật toán/khóa không được phép hoặc bỏ qua ngoại lệ.

Với đa số API, **ký trước rồi xác minh bằng cùng một cặp khóa tự tạo** chỉ là kiểm tra thuật toán hoạt động, **không kiểm tra độ tin cậy của khóa**. Bài toán trust cần được giải quyết riêng.

### 3.5. Kiểm tra niềm tin, chính sách và quyền nghiệp vụ

Ngay cả khi chữ ký hợp lệ, cần kiểm tra:

1. Public key có thuộc về **đúng chủ thể** và đúng trust domain không?
2. Khóa/chứng thư có được phép dùng cho **mục đích ký** tại thời điểm và ngữ cảnh liên quan không?
3. Chứng thư có hợp lệ theo chính sách về **đường dẫn tin cậy, thời hạn, key usage, EKU, trạng thái thu hồi** không?
4. Nội dung đã ký có bao phủ **ID giao dịch, tenant, số tiền, đối tượng, phiên bản định dạng và mục đích** cần ràng buộc không?
5. Người ký có **quyền nghiệp vụ** thực hiện hành động đó không?
6. Bản tin có bị **phát lại, hết hạn, sai thứ tự hoặc xử lý hai lần** không?

**Chỉ chấp nhận sau khi tất cả kiểm tra bắt buộc đều đạt.**

~~~mermaid
flowchart TD
    A[Nhận message + signature + key ID] --> B[Kiểm tra định dạng và giới hạn kích thước]
    B --> C[Xác định thuật toán trong allowlist]
    C --> D[Chọn public key từ trust domain được cấu hình]
    D --> E{Binding danh tính/khóa hợp lệ?}
    E -->|Không| X[Từ chối và ghi audit]
    E -->|Có| F[Verify trên đúng byte nội dung]
    F --> G{Chữ ký hợp lệ?}
    G -->|Không| X
    G -->|Có| H[Kiểm tra PKI, hiệu lực, thu hồi, thời điểm]
    H --> I{Đạt chính sách tin cậy?}
    I -->|Không| X
    I -->|Có| J[Kiểm tra quyền, ngữ cảnh, replay]
    J --> K{Được phép thực hiện?}
    K -->|Không| X
    K -->|Có| Y[Chấp nhận và ghi audit]
~~~

Sơ đồ phân tách logic để dễ học; trong triển khai thực, những kiểm tra tin cậy có thể diễn ra trước phép toán chữ ký. Điều quan trọng là không bỏ lớp nào và không thực hiện hành động nghiệp vụ trước khi chuỗi kiểm tra hoàn tất.

## 4. Các thuật toán thường dùng trong signature verification

| Lược đồ | Khóa và đặc điểm | Kiểm tra triển khai quan trọng |
| --- | --- | --- |
| **Ed25519** | Thuộc họ EdDSA, hiệu quả, chữ ký cố định 64 byte trong dạng chuẩn | Dùng đúng lược đồ và byte thông điệp; không tự thêm tiền xử lý không tương thích |
| **ECDSA** | Dựa trên đường cong elliptic (ví dụ P-256); chữ ký có hai số `r`, `s` | Đúng curve/hash, đúng định dạng DER hoặc P1363, quy tắc encoding của giao thức |
| **RSA-PSS** | Lược đồ RSA với encoding xác suất, thường dùng hash SHA-256 trở lên theo chính sách | Đúng hash, MGF1, salt length; đúng RSA public key |
| **RSA PKCS#1 v1.5 signature** | Lược đồ RSA ký truyền thống, còn gặp trong hệ thống cũ | Chỉ cho phép khi chính sách/giao thức hỗ trợ, không nhầm với RSA PKCS#1 v1.5 encryption |

Lựa chọn thuật toán cần dựa trên **tiêu chuẩn của hệ thống, yêu cầu tương thích, mức an toàn, chính sách sử dụng khóa và tuổi thọ dữ liệu**. Không so sánh chỉ bằng số bit của public key; RSA và đường cong elliptic có mức an toàn khác nhau ở cùng kích thước byte.

### 4.1. RSA-PSS

Với RSA-PSS, bên ký và bên nhận cần thống nhất **thuật toán băm, MGF1 hash, độ dài salt và trailer field** theo giao thức. Ví dụ `SHA-256 / MGF1-SHA-256 / saltLength=32` có thể là cấu hình xác định, nhưng không được mặc định mọi thư viện chọn đúng cấu hình khi chỉ gọi tên chung `RSASSA-PSS`.

**RSA-PSS dùng để ký và xác minh, không dùng để mã hóa.** RSA-OAEP phục vụ mã hóa/bọc khóa nhỏ; trộn hai mục đích hoặc cố “giải mã chữ ký để lấy hash” là cách thiết kế sai.

### 4.2. ECDSA

ECDSA yêu cầu một public key trên đường cong phù hợp và chữ ký gồm hai giá trị toán học `r`, `s`. Các thư viện JCA thường nhận chữ ký ECDSA theo **ASN.1 DER** đối với `SHA256withECDSA`; còn JWS `ES256` biểu diễn `r || s` ở dạng cố định, vì vậy **không được lấy Base64url của JWS rồi truyền thẳng cho API DER mà không chuyển đổi đúng định dạng**.

Một số hệ sinh thái còn quy định chuẩn hóa **low-S** để giảm biểu diễn tương đương hoặc khả năng malleability của chữ ký ECDSA. Điều đó là yêu cầu **theo giao thức**, không thể áp đặt tùy tiện lên mọi chữ ký lịch sử.

### 4.3. Ed25519

Ed25519 có API ký/xác minh đơn giản, chữ ký chuẩn **64 byte**, public key chuẩn **32 byte**. Trong Java, `Signature.getInstance("Ed25519")` thực hiện lược đồ chuẩn trên byte được cung cấp. **Ed25519 và Ed25519ph** là biến thể khác nhau; không tự băm thông điệp ở ứng dụng rồi giả định tương đương Ed25519ph.

Nếu hệ thống dùng chứng thư X.509 chứa khóa Ed25519, cần đảm bảo **khả năng xử lý thuật toán của trust stack/PKI**, chứ không chỉ kiểm tra được chữ ký trên dữ liệu.

## 5. Định dạng dữ liệu đã ký: lỗi khó phát hiện nhất

Để xác minh, bên nhận phải tái tạo chính xác **byte input** mà bên ký dùng. Có ba cách thực tế:

1. **Ký trực tiếp payload đã serialize** và truyền/lưu đúng nguyên vẹn byte payload đó.
2. **Canonicalize trước khi ký** theo một chuẩn được cả hai bên hiểu rõ.
3. **Dùng giao thức chữ ký đóng gói** (JWS, XMLDSig, CMS/PKCS#7, COSE...) và thư viện chuyên dụng tuân thủ quy tắc của giao thức.

Không chỉ ký một phần thông điệp tùy tiện. Ví dụ API thanh toán có dữ liệu:

~~~json
{
  "tenantId": "tenant-42",
  "orderId": "order-1001",
  "amountMinor": 50000,
  "currency": "VND",
  "schemaVersion": 2
}
~~~

Nếu chỉ ký `orderId` và `amountMinor` mà không ràng buộc `tenantId`, `currency`, `schemaVersion` theo yêu cầu nghiệp vụ, kẻ tấn công có thể thử tái sử dụng chữ ký trong **ngữ cảnh khác** dù các byte được ký không đổi.

Nên dùng:

- **Domain separation:** gắn tên giao thức/mục đích (ví dụ `PAYMENT_APPROVAL_V2`) vào dữ liệu được ký bằng encoding không mơ hồ.
- **Canonical serialization:** rõ kiểu dữ liệu, độ dài, byte order, Unicode, cách biểu diễn số, thứ tự trường và phiên bản.
- **Binding giao dịch:** bao phủ tenant, đối tượng, hành động, số tiền, thời điểm/hạn hiệu lực hoặc nonce nếu cần.
- **Chống replay:** kiểm tra ID duy nhất đã xử lý, hạn thời gian và tính đúng thứ tự ở tầng ứng dụng.

**Không dùng một chữ ký hợp lệ cho hai ý nghĩa khác nhau** chỉ vì hai nơi cùng dùng một public key.

## 6. PKI: xác minh chữ ký khác xác minh chứng thư

Khi sử dụng chứng thư X.509, **xác minh chữ ký trên tài liệu** và **xác minh chứng thư** là hai việc khác nhau:

- **Document signature verification:** kiểm tra thông điệp có chữ ký hợp lệ theo public key của người ký không.
- **Certificate/path validation:** kiểm tra chứng thư có thuộc chuỗi tin cậy đến một CA/trust anchor được phê duyệt, danh tính đúng, thời hạn và mục đích đúng, cùng các kiểm tra trạng thái thu hồi được yêu cầu không.

~~~mermaid
flowchart LR
    Root[Trust anchor đã cấu hình] --> Intermediate[CA trung gian]
    Intermediate --> Leaf[Chứng thư người ký]
    Leaf --> Pub[Public key của người ký]
    Pub --> Verify[Verify chữ ký trên đúng byte dữ liệu]
    Rules[Chain, identity, KU/EKU, validity, revocation, policy] --> Trust[Quyết định tin cậy]
    Leaf --> Trust
    Verify --> Result{Chấp nhận?}
    Trust --> Result
    Result -->|Đạt cả hai| OK[Tiếp tục kiểm tra nghiệp vụ]
    Result -->|Bất kỳ lỗi nào| Reject[Từ chối]
~~~

**Chứng thư tự ký** chỉ đáng tin khi public key/trust anchor đã được cài đặt và xác minh bằng quy trình an toàn. Chứng thư do bất kỳ người nào tạo ra rồi tự ký không đủ chứng minh danh tính.

### 6.1. Key Usage và Extended Key Usage

Một chứng thư có thể mang ràng buộc về **key usage** (ví dụ digitalSignature) hoặc **Extended Key Usage** cho những mục đích cụ thể. Hệ thống không nên dùng public key chỉ vì phép toán chữ ký hợp lệ nếu chứng thư không được phát hành cho mục đích đó theo chính sách.

### 6.2. Thu hồi chứng thư và trạng thái hiện hành

**CRL** và **OCSP** là những cơ chế phổ biến để kiểm tra chứng thư bị thu hồi; khả năng, chính sách xử lý lỗi mạng và chế độ fail-open/fail-closed tùy môi trường. Trong hệ thống nhạy cảm, phải xác định rõ **khi không kiểm tra được revocation thì có chấp nhận không**; không tự cho rằng thư viện TLS hay JCA đã bật đầy đủ kiểm tra thu hồi cho mọi trường hợp.

**Key compromise** có thể khiến chữ ký được tạo bởi người không được phép. Việc chỉ làm phép toán Verify với public key cũ không phát hiện được ai đang nắm private key.

### 6.3. Chữ ký lịch sử và dấu thời gian đáng tin

Ngày hết hạn chứng thư hôm nay **không mặc nhiên làm mọi chữ ký tạo trước đó vô hiệu**. Để kiểm tra hồ sơ được lưu nhiều năm, cần đánh giá:

- Chữ ký có hợp lệ theo khóa và thuật toán tại thời điểm liên quan không?
- Có **dấu thời gian từ nguồn đáng tin cậy** hoặc bằng chứng thời gian phù hợp không? Một trường `signedAt` do chính người ký khai báo **không đủ**.
- Tình trạng chứng thư và việc thu hồi tại thời điểm cần kiểm tra được xác định bằng bằng chứng nào?
- Có cần lưu **chuỗi chứng thư, thông tin OCSP/CRL, timestamp token và chính sách xác minh lịch sử** hay không?
- Thuật toán đã suy yếu theo thời gian và có cần gia hạn bằng chứng/lưu trữ theo tiêu chuẩn áp dụng không?

Việc xác minh dài hạn cần một **quy trình lưu bằng chứng (long-term validation)** phù hợp định dạng và chính sách, không chỉ gọi Verify rồi lưu một cờ `true` vĩnh viễn.

## 7. Ví dụ Java 17: xác minh Ed25519

Java 17 hỗ trợ Ed25519 thông qua JCA với provider phù hợp. Ví dụ dưới đây **tạo cặp khóa và chữ ký trong cùng chương trình để dễ học**, sau đó kiểm tra chữ ký đúng, thông điệp đã sửa và public key sai.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;

public class SignatureVerificationDemo {
    static byte[] signForDemo(KeyPair keyPair, byte[] message)
            throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keyPair.getPrivate());
        signer.update(message);
        return signer.sign();
    }

    static boolean verifyEd25519(
            PublicKey trustedPublicKey, byte[] message, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedPublicKey);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        // Chỉ là cặp khóa thử nghiệm; production phải lấy public key
        // qua PKI/registry/trust store được phê duyệt.
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair signerKeyPair = generator.generateKeyPair();
        KeyPair unrelatedKeyPair = generator.generateKeyPair();

        byte[] message = "PAYMENT_APPROVAL_V2|tenant-42|order-1001|50000"
                .getBytes(StandardCharsets.UTF_8);
        byte[] signature = signForDemo(signerKeyPair, message);

        boolean valid = verifyEd25519(
                signerKeyPair.getPublic(), message, signature);
        if (!valid) {
            throw new AssertionError("Valid signature rejected");
        }

        byte[] tampered = "PAYMENT_APPROVAL_V2|tenant-42|order-1001|90000"
                .getBytes(StandardCharsets.UTF_8);
        if (verifyEd25519(
                signerKeyPair.getPublic(), tampered, signature)) {
            throw new AssertionError("Modified message accepted");
        }

        if (verifyEd25519(
                unrelatedKeyPair.getPublic(), message, signature)) {
            throw new AssertionError("Unrelated public key accepted");
        }

        System.out.println("Ed25519 signature checks passed");
    }
}
~~~

**Giới hạn quan trọng:** việc sinh cặp khóa ngay trong chương trình **không phải cách tạo niềm tin ở production**. Nếu ứng dụng nhận cả message, signature và public key từ cùng một request không đáng tin rồi chỉ kiểm tra `verify = true`, kẻ tấn công có thể tự tạo tất cả ba thành phần. Public key phải được **ràng buộc với issuer/danh tính được tin cậy trước khi chấp nhận chữ ký**.

### 7.1. Biến thể với RSA-PSS

Khi hệ thống yêu cầu RSA-PSS, hãy cấu hình tham số xác minh rõ ràng theo giao thức. Ví dụ đoạn hàm sau minh họa **SHA-256 với MGF1-SHA-256 và salt 32 byte**:

~~~java
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public class RsaPssVerification {
    static boolean verify(
            PublicKey trustedRsaPublicKey, byte[] message, byte[] signature)
            throws Exception {
        PSSParameterSpec params = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                32, PSSParameterSpec.TRAILER_FIELD_BC);

        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(params);
        verifier.initVerify(trustedRsaPublicKey);
        verifier.update(message);
        return verifier.verify(signature);
    }
}
~~~

Đây là cấu hình **minh họa**; phía ký và phía xác minh phải thống nhất chính xác những tham số đã được chuẩn giao thức hoặc hồ sơ hệ thống quy định. Không dùng RSA-OAEP để xác minh chữ ký và không tự thực hiện phép lũy thừa RSA nguyên thủy.

### 7.2. Kiểm tra thêm ngoài Java `Signature.verify`

Lớp `java.security.Signature` **chỉ xác minh mật mã**. Để chấp nhận giao dịch thực tế, cần kết hợp các thành phần như `CertPathValidator`/PKIX với trust anchor đã chọn, thư viện JWS/CMS/XMLDSig phù hợp định dạng, kho public key tin cậy, xác minh claims và chính sách nghiệp vụ. Không tự viết toàn bộ PKI validator chỉ từ `X509Certificate.verify`, bởi lời gọi đó **chưa đủ** cho path validation, hostname/identity, key usage và revocation.

## 8. Signature verification với JWT/JWS và hệ thống phân tán

Với **JSON Web Signature (JWS)**, dữ liệu được ký theo quy tắc encoding của JWS. JWT có thể mang chữ ký JWS. Đối với JWS dạng compact phổ biến:

~~~text
BASE64URL(protectedHeader) . BASE64URL(payload) . BASE64URL(signature)

Signing input thường là:
BASE64URL(protectedHeader) + "." + BASE64URL(payload)
~~~

Không được mặc định rằng verifier chỉ cần lấy JSON payload đã parse rồi serialize lại để xác minh: chữ ký thường bao phủ **các segment đã encode chính xác** theo đặc tả. Các biến thể JWS khác có quy tắc encoding riêng; hãy dùng thư viện JOSE được duy trì.

### Các lớp kiểm tra với JWT

1. **Chỉ cho phép thuật toán cần thiết:** ví dụ issuer A chỉ ký bằng `RS256` hoặc `PS256` theo cấu hình; không nhận tùy ý mọi `alg`.
2. **Chọn khóa trong đúng tập khóa của issuer A:** `kid` chỉ là selector. Không tải khóa từ URL do token tự cung cấp nếu URL không nằm trong cấu hình tin cậy.
3. **Kiểm tra chữ ký:** qua thư viện JWS/JWT phù hợp với thuật toán và định dạng chữ ký.
4. **Kiểm tra claim:** `iss`, `aud`, `exp`, `nbf` và `sub`/scope/tenant theo chính sách.
5. **Kiểm tra quyền nghiệp vụ:** token được xác minh không có nghĩa chủ thể được phép truy cập mọi bản ghi.
6. **Giới hạn cache/refresh JWKS:** đảm bảo luồng rotation và lỗi mạng không tạo bypass hoặc DoS qua các `kid` giả.

~~~mermaid
sequenceDiagram
    participant Iss as Issuer
    participant Key as KMS/HSM hoặc keystore ký
    participant Registry as JWKS / registry tin cậy
    participant API as API verifier
    Iss->>Key: Sign(token claims đã encode)
    Key-->>Iss: Signature + key ID
    Iss-->>API: JWT/JWS
    API->>Registry: Lấy public key đúng issuer/kid
    Registry-->>API: Tập khóa và trạng thái
    API->>API: Verify JWS + kiểm tra iss/aud/exp
    API->>API: Kiểm tra scope, tenant, replay nếu cần
    API-->>Iss: Chấp nhận hoặc từ chối
~~~

Trong mô hình này, **KMS/HSM quản lý private key dùng để ký**, còn phía xác minh có thể dùng **public key công khai** lấy từ registry đã được xác thực. Không cần cấp quyền `Sign` hoặc xuất private key cho verifier.

## 9. Key management cho quá trình xác minh

Việc xác minh chữ ký tưởng như “chỉ dùng khóa công khai” nhưng vẫn phụ thuộc toàn bộ vòng đời key management:

| Giai đoạn | Tác động đến bên xác minh |
| --- | --- |
| **Generation** | Cặp khóa phải được sinh an toàn, thuật toán và độ dài đúng chính sách |
| **Provisioning** | Public key/chain phải được phân phối qua nguồn có danh tính và quyền publish rõ ràng |
| **Storage** | Verifier lưu/cache public key, trust anchor và policy chống sửa trái phép; signer bảo vệ private key |
| **Use** | Kiểm tra đúng mục đích ký, thuật toán, thông điệp và quyền nghiệp vụ |
| **Rotation** | Nhận public key mới trước hoặc cùng lúc signer chuyển khóa; không gây đứt gãy xác minh |
| **Retire/revoke** | Ngừng tin khóa bị lộ hoặc không còn được phép theo chính sách; xử lý cache và token đã phát hành |
| **Destruction/retention** | Private key ký có thể được hủy khi không còn cần ký; public key và bằng chứng lịch sử có thể cần giữ lâu hơn |
| **Audit** | Lưu key ID, issuer, thuật toán, kết quả, lý do từ chối và request ID, không log bí mật |

### 9.1. Cryptoperiod của chữ ký

Private key có thể chỉ được phép **tạo chữ ký mới** trong một khoảng xác định, trong khi public key vẫn được dùng **xác minh các chữ ký lịch sử** sau đó. Hai khoảng không đồng nhất; phải xét việc chứng minh **thời điểm ký** và **trạng thái khóa tại thời điểm liên quan** theo chính sách.

Việc giữ public key để xác minh hồ sơ cũ **không đồng nghĩa tiếp tục chấp nhận chữ ký mới được tạo bằng private key đã nghỉ hưu**. Nếu không có bằng chứng thời gian đáng tin, phân biệt chữ ký cũ hợp lệ với chữ ký giả mạo mới có thể khó hoặc không thể chỉ dựa trên chữ ký toán học.

### 9.2. Rotation và xử lý sự cố private key

Quy trình bình thường:

1. Sinh khóa mới và thiết lập mục đích/quyền trong KMS/HSM.
2. Công bố public key mới qua PKI/JWKS/key registry đã được xác thực.
3. Cho verifier cập nhật tập khóa tin cậy theo lịch và chính sách cache.
4. Chuyển signer sang private key mới; đính kèm key ID/version tương ứng.
5. Giữ hoặc lưu bằng chứng public key cũ để kiểm tra dữ liệu lịch sử trong phạm vi được phép; rút khỏi tập xác minh giao dịch mới khi hết hạn.

Nếu **private key bị lộ**, không đợi lịch: phải đánh giá chữ ký có nguy cơ giả mạo, vô hiệu hóa quyền ký, thu hồi binding/chứng thư phù hợp, chuyển khóa và xử lý các giao dịch liên quan. **Thay key ID hoặc xóa khóa khỏi JWKS không đảm bảo mọi verifier cache đã ngừng tin ngay lập tức.** Cần thông báo, làm mới cache bắt buộc hoặc rút ngắn thời hạn token theo kiến trúc.

### 9.3. Audit và quyền truy cập

Phía signer cần ghi được **ai/cái gì gọi `Sign`**, trên loại dữ liệu nào, bằng khóa nào, kết quả và chính sách cấp quyền. Phía verifier nên ghi **issuer, key ID, thuật toán, policy version, request ID, verdict và mã lỗi tổng quát**. Tránh đưa toàn bộ thông điệp nhạy cảm, access token, private key hay DEK vào log. Không để một chữ ký hợp lệ lấn át kiểm tra quyền thực hiện nghiệp vụ.

## 10. Tình huống thực tế: xác minh hóa đơn điện tử

Một nền tảng thương mại nhận hóa đơn từ nhiều đối tác. Mỗi đối tác có private key ký được bảo vệ bằng KMS/HSM hoặc thiết bị/keystore phù hợp, còn nền tảng nhận lưu public key và chính sách tin cậy theo từng đối tác.

**Luồng nhận và xác minh:**

1. Tầng tiếp nhận xác định đối tác dự kiến từ kênh và metadata đã được xác thực, **không chỉ từ tên người ký trong payload**.
2. Hệ thống đọc tài liệu ở đúng định dạng đã ký; xác định chính xác phần byte được bao phủ bởi chữ ký.
3. Hệ thống chọn public key/chứng thư từ registry tin cậy theo đối tác, key ID và mục đích ký.
4. Thư viện xác minh chữ ký bằng RSA-PSS, ECDSA hoặc Ed25519 theo lược đồ đã phê duyệt.
5. Nếu dùng PKI, hệ thống kiểm tra chứng thư/chain, thời hạn, key usage và thông tin thu hồi theo chính sách; nếu là hồ sơ lịch sử, xét bằng chứng thời gian đáng tin.
6. Tầng nghiệp vụ xác nhận đối tác có quyền phát hành hóa đơn, mã đơn hàng và số tiền phù hợp, hóa đơn chưa được xử lý trước đó.
7. Hệ thống lưu kết quả, version policy, public key/cert reference và chứng cứ phục vụ truy vết.

**Nếu chữ ký hợp lệ nhưng số tiền khác hợp đồng:** vẫn **từ chối nghiệp vụ**. Chữ ký chỉ chứng minh bản tin được ký bằng khóa tương ứng, không làm giao dịch trái chính sách trở nên hợp lệ.

**Nếu chữ ký sai do bên gửi đổi cách serialize JSON:** phải sửa quy ước định dạng/ký của hai bên, **không bỏ qua Verify** để xử lý tiếp.

**Nếu đối tác vừa rotation:** verifier cần dùng đúng public key phiên bản mới và tiếp tục xử lý hóa đơn cũ theo chính sách đã định; không tùy tiện tin public key do một hóa đơn lạ đính kèm.

**Nếu private key đối tác bị lộ:** tổ chức phải đánh giá thời gian ảnh hưởng, xử lý thu hồi và thông báo thay đổi tin cậy, rà soát hóa đơn bất thường và quyết định cách xử lý lịch sử dựa trên bằng chứng thời gian. Một cờ `signatureValid = true` được tính lại sau sự cố không đủ để chứng minh hóa đơn có thực sự được đối tác phát hành trước thời điểm lộ khóa.

## 11. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Chấp nhận public key gửi kèm thông điệp để xác minh chính nó | Kẻ tấn công tự tạo khóa và chữ ký hợp lệ giả danh | Chọn khóa từ PKI/JWKS/registry đã tin cậy |
| Kiểm tra Verify thành công rồi bỏ qua quyền nghiệp vụ | Chấp nhận hành động được ký nhưng không được phép | Tách kiểm tra chữ ký, danh tính và authorization |
| Ký JSON một kiểu, xác minh JSON serialize lại kiểu khác | Lỗi chữ ký hoặc bỏ sót trường | Dùng byte nguyên gốc, canonicalization hoặc JWS/CMS chuẩn |
| Cho header/token tự chọn bất kỳ thuật toán nào | Algorithm confusion hoặc chấp nhận thuật toán yếu | Allowlist theo issuer và mục đích |
| Nhầm định dạng ECDSA DER và JWS P1363 | Chữ ký đúng nhưng xác minh thất bại; lỗi xử lý format | Chuyển đổi đúng chuẩn qua thư viện giao thức |
| Dùng SHA-256 digest làm thông điệp đưa vào API đã tự hash | Double hashing hoặc xác minh khác nội dung đã ký | Hiểu rõ hợp đồng API ký/xác minh và encoding |
| Chỉ kiểm tra X.509Certificate.verify mà bỏ PKIX | Không xác minh đầy đủ trust chain, danh tính, thời hạn, thu hồi | Dùng path validation/policy phù hợp |
| Không lưu bằng chứng thời gian cho chữ ký cần xác minh lâu dài | Khó chứng minh chữ ký có trước lúc khóa bị lộ/thu hồi | Lưu trusted timestamp và chứng cứ theo chính sách |
| Tin trường signedAt do người gửi tự ghi | Có thể giả mạo ngày ký | Dùng bằng chứng thời gian độc lập khi cần |
| Coi chữ ký hợp lệ là chống replay | Giao dịch hợp lệ có thể được gửi lại | Kiểm tra transaction ID, nonce, sequence/expiry |
| Rotation nhưng verifier cache chỉ biết khóa cũ | Từ chối giao dịch mới; gián đoạn hệ thống | Công bố trước, refresh JWKS/registry, kiểm thử |
| Private key bị lộ nhưng vẫn tin chữ ký mới vô hạn | Có thể chấp nhận chữ ký do attacker tạo | Thu hồi/đổi binding, xử lý token/cache, điều tra |
| Ghi toàn bộ payload nhạy cảm hoặc token vào audit | Mở rộng phạm vi lộ dữ liệu | Chỉ log metadata cần thiết, kiểm soát truy cập audit |

## 12. Checklist triển khai an toàn

- [ ] Đã xác định **đúng thông điệp và phạm vi byte** được ký, kể cả version và ngữ cảnh?
- [ ] Có danh sách thuật toán/lược đồ và tham số được phép theo issuer/mục đích?
- [ ] Public key lấy từ **trust domain đã xác thực**, không tin khóa do dữ liệu chưa kiểm chứng tự chỉ định?
- [ ] Key ID/`kid` được dùng như selector trong đúng issuer/tenant, không làm bằng chứng danh tính?
- [ ] Dùng thư viện chữ ký được duy trì, không tự cài đặt RSA/ECDSA/EdDSA?
- [ ] Có kiểm tra đường dẫn chứng thư, danh tính, key usage/EKU, hiệu lực và thu hồi theo chính sách khi dùng PKI?
- [ ] Đã phân biệt kiểm tra chữ ký trên tài liệu với xác minh chứng thư và kiểm tra quyền nghiệp vụ?
- [ ] Có chống phát lại, trùng giao dịch hoặc thông điệp hết hạn khi ứng dụng cần?
- [ ] Nếu cần xác minh lâu dài, có timestamp đáng tin, chuỗi chứng thư và bằng chứng trạng thái phù hợp?
- [ ] Có kế hoạch rotation signer key, công bố public key mới và cập nhật cache verifier?
- [ ] Có quy trình xử lý private key bị lộ và phân biệt chữ ký mới với chứng cứ lịch sử?
- [ ] KMS/HSM cấp quyền ký tối thiểu; verifier không được cấp private key hoặc quyền `Sign` không cần thiết?
- [ ] Audit ghi được key ID, thuật toán, verdict, policy version, request ID nhưng không làm lộ bí mật?
- [ ] Đã thử các trường hợp sửa message, sửa chữ ký, khóa sai, thuật toán sai, cert hết hạn/thu hồi và replay?

## 13. Câu hỏi tự kiểm tra

**1. Khi `Signature.verify` trả true, có thể kết luận người ký đúng là công ty A không?**  
Không. Điều đó chỉ nói chữ ký hợp lệ đối với public key đã cung cấp theo thuật toán/byte dữ liệu. Phải xác thực public key thuộc về công ty A và có mục đích dùng phù hợp.

**2. Vì sao hai JSON có cùng dữ liệu nhưng khác thứ tự trường có thể làm chữ ký không khớp?**  
Vì chữ ký thường áp dụng trên **byte cụ thể**, không tự hiểu hai biểu diễn JSON là cùng ngữ nghĩa. Cần thống nhất serialization/canonicalization hoặc ký đúng byte được truyền.

**3. RSA-PSS và RSA-OAEP có cùng mục đích không?**  
Không. RSA-PSS dùng ký/xác minh, RSA-OAEP dùng mã hóa/giải mã dữ liệu nhỏ hoặc bọc khóa.

**4. Vì sao không được chọn public key theo một URL do JWT tự chỉ định?**  
Vì kẻ tấn công có thể điều khiển URL để verifier lấy khóa giả. Public key phải đến từ tập khóa của issuer đã được cấu hình và xác thực.

**5. Chữ ký số có chống replay không?**  
Không tự động. Chữ ký hợp lệ trên cùng một thông điệp vẫn hợp lệ khi bị phát lại; ứng dụng phải kiểm tra ID, thời gian, nonce hoặc trạng thái giao dịch.

**6. Chứng thư hết hạn hôm nay có nghĩa mọi chữ ký tạo năm trước đều không hợp lệ?**  
Không mặc nhiên. Việc xác minh lịch sử tùy thuộc bằng chứng thời điểm ký, trạng thái chứng thư tại thời điểm liên quan và chính sách chấp nhận.

**7. Vì sao bên xác minh thường không cần quyền `Sign` trong KMS?**  
Vì xác minh sử dụng public key, còn `Sign` sử dụng private key. Tách quyền giúp hạn chế khả năng giả mạo chữ ký nếu verifier bị chiếm.

**8. Có thể coi một hóa đơn có chữ ký hợp lệ là đã được duyệt thanh toán không?**  
Không. Chữ ký chỉ là một bằng chứng về toàn vẹn/nguồn ký. Quyền ký, giá trị giao dịch, đối tác và quy trình duyệt vẫn phải kiểm tra độc lập.

## Ghi nhớ

**Signature verification là xác minh chữ ký số đối với đúng byte thông điệp bằng public key, thuật toán và tham số phù hợp; đó mới là lớp kiểm tra mật mã.** Để chấp nhận một giao dịch, hệ thống còn phải **xác thực nguồn gốc public key, kiểm tra chứng thư/trạng thái khóa, xác minh ngữ cảnh và quyền nghiệp vụ, chống replay** và quản lý bằng chứng lịch sử khi cần. Thiết kế vững chắc kết nối **mật mã bất đối xứng, chữ ký số, KMS/HSM, vòng đời private key, public key distribution, cryptoperiod, rotation, thu hồi, kiểm soát truy cập và audit**. Không thuật toán ký mạnh nào có thể bù cho một public key bị tin sai chủ thể hoặc một quy trình phê duyệt bị bỏ qua.
