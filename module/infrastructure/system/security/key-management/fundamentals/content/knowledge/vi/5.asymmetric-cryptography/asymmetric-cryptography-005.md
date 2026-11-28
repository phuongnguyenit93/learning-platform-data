# ECDSA (Elliptic Curve Digital Signature Algorithm)

## 1. ECDSA là gì?

**ECDSA** là thuật toán **chữ ký số dựa trên mật mã đường cong elliptic** (*Elliptic Curve Cryptography – ECC*). Nó cho phép một chủ thể dùng **private key** để ký thông điệp và cho phép bên khác dùng **public key** tương ứng để kiểm tra chữ ký.

Chữ ký ECDSA được thiết kế để hỗ trợ hai thuộc tính quan trọng:

- **Tính toàn vẹn (integrity):** thay đổi dữ liệu được ký sẽ khiến chữ ký không còn hợp lệ, với điều kiện hàm băm và việc xác minh được dùng đúng.
- **Xác thực nguồn gốc theo khóa (origin authentication):** một chữ ký hợp lệ cho biết bên tạo chữ ký có khả năng sử dụng private key tương ứng; muốn gắn chữ ký với một cá nhân hoặc dịch vụ cụ thể còn phải **xác thực danh tính chủ sở hữu public key**.

ECDSA **không mã hóa nội dung** và không tự cung cấp **tính bí mật (confidentiality)**. Người có thông điệp, chữ ký và public key vẫn đọc được nội dung nếu thông điệp không được mã hóa bằng cơ chế khác.

**Ví dụ:** Dịch vụ phát hành bản cập nhật phần mềm dùng ECDSA để ký hash của gói cập nhật hoặc một manifest quy định rõ nội dung và phiên bản. Thiết bị tải gói, kiểm tra chữ ký bằng public key đáng tin cậy, rồi mới tiến hành cài đặt. Mục đích là phát hiện gói bị sửa hoặc bị giả mạo. Để ngăn việc phát lại bản cập nhật cũ, hệ thống còn cần kiểm tra **version, thời hạn hoặc chính sách chống rollback**.

Trong chương **Mật mã bất đối xứng** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, ECDSA là ví dụ quan trọng để kết nối **cặp khóa công khai/riêng tư, chữ ký số, KMS/HSM, vòng đời khóa, xoay vòng, thu hồi, kiểm soát truy cập và kiểm toán**.

> **Phân biệt sớm:** ECDSA dùng để **sign/verify**; ECDH hoặc ECDHE dùng để **thiết lập bí mật chung**; AES-GCM dùng để **mã hóa dữ liệu có xác thực**. Cả ba có thể phối hợp trong một hệ thống nhưng không hoán đổi chức năng cho nhau.

## 2. Khóa ECDSA gồm những gì?

ECDSA hoạt động trên một nhóm điểm của đường cong elliptic với các tham số được xác định trước. Những tham số quan trọng là:

| Ký hiệu | Ý nghĩa | Tính chất |
|---|---|---|
| **G** | Điểm sinh (*base point/generator*) của nhóm dùng cho ECDSA | Công khai, thuộc thông số đường cong |
| **n** | Bậc (*order*) của điểm G | Công khai; dùng trong phép tính theo modulo n |
| **d** | **Private key**: số nguyên thuộc khoảng từ 1 đến n − 1 | Bí mật tuyệt đối |
| **Q = dG** | **Public key**: điểm trên đường cong tính từ d và G | Có thể công khai; phải được xác thực đúng chủ sở hữu |
| **z** | Giá trị được rút từ hash của thông điệp theo quy tắc ECDSA | Không phải bí mật |
| **k** | Số bí mật **riêng cho mỗi lần ký** (*per-signature nonce/ephemeral scalar*) | Rất nhạy cảm; tuyệt đối tránh lặp hoặc làm lộ |
| **(r, s)** | Hai số nguyên cấu thành chữ ký ECDSA | Được gửi cùng hoặc gắn với thông điệp |

**Private key d** thường được sinh bằng cơ chế ngẫu nhiên an toàn phù hợp với nhóm đường cong. **Public key Q** được tạo bằng phép nhân vô hướng điểm (*scalar multiplication*); suy ra d từ Q được xem là khó đối với những đường cong được chọn đúng và trong mô hình tính toán cổ điển.

~~~text
                Sinh cặp khóa ECDSA

          Thông số đường cong: G, n, ...
                         |
          private key d (1 <= d < n)
                         |
                         v
                public key Q = dG

Private key d: giữ bí mật trong miền tin cậy.
Public key Q: phân phối cùng chứng chỉ hoặc trust policy.
~~~

Cùng một chữ ký ECDSA có thể được xác minh nhiều lần; **khóa riêng** có thể ký nhiều thông điệp theo chính sách. Nhưng **k** là bí mật theo từng lần ký, không được xem là một khóa dài hạn để tái sử dụng.

### 2.1. Curve là một phần của danh tính khóa

Public key ECDSA không thể được diễn giải đúng nếu không biết tham số đường cong. Một số lựa chọn quen thuộc:

| Đường cong | Tên thường gặp | Tình huống sử dụng |
|---|---|---|
| **NIST P-256** | secp256r1, prime256v1 | ECDSA với SHA-256; các cấu hình PKI, TLS, JWS ES256 |
| **NIST P-384** | secp384r1 | ECDSA với SHA-384, hệ thống cần mức an toàn cao hơn |
| **NIST P-521** | secp521r1 | ECDSA với SHA-512 trong các cấu hình phù hợp |
| **secp256k1** | secp256k1 | Một số giao thức blockchain; hỗ trợ phụ thuộc provider và chuẩn giao thức |

Độ dài private key hoặc tọa độ điểm **không thể tự suy ra mức an toàn tương đương AES có số bit bằng nhau**. Thuật toán, tham số đường cong, hàm băm và cách triển khai đều ảnh hưởng đến mức bảo mật.

**Ed25519 cũng là chữ ký số đường cong elliptic nhưng thuộc họ EdDSA, không phải ECDSA.** Dù đều dùng ECC, không được thay tên thuật toán, public key hoặc định dạng chữ ký của chúng cho nhau.

## 3. ECDSA ký và xác minh chữ ký như thế nào?

### 3.1. Quy trình ký ở mức khái niệm

Cho thông điệp **m**, private key **d**, public key **Q = dG**, hàm băm đã chọn và các tham số đường cong:

1. Tính **hash(m)** rồi tạo giá trị **z** theo quy tắc ECDSA (bao gồm cắt bớt bit nếu thông số thuật toán yêu cầu).
2. Sinh **k** nằm trong khoảng **1 ≤ k < n**, bí mật và thích hợp cho riêng lần ký.
3. Tính điểm **R = kG**, lấy **r = x(R) mod n**; nếu r = 0 thì chọn k khác.
4. Tính **s = k⁻¹ × (z + r × d) mod n**; nếu s = 0 thì chọn k khác.
5. Kết quả chữ ký là cặp **(r, s)** và được mã hóa theo định dạng giao thức.

~~~text
             ECDSA SIGN

message m --> Hash --> z -----+
                               |
private key d -----------------+--> ECDSA --> (r, s)
                               |
nonce bí mật k cho lần ký -----+

Không đưa private key d hoặc nonce k ra chữ ký.
~~~

Các phép nhân điểm và nghịch đảo modulo phía trên dùng để **hiểu thuật toán**, không phải hướng dẫn tự xây thư viện mật mã. Ứng dụng nên sử dụng API chuẩn của Java, thư viện đã kiểm chứng hoặc dịch vụ ký trong KMS/HSM.

### 3.2. Quy trình xác minh

Bên xác minh nhận **m**, chữ ký **(r, s)** và public key **Q** đã được tin cậy:

1. Kiểm tra **r** và **s** nằm trong khoảng hợp lệ **1 ≤ r, s < n**.
2. Tính **z** từ đúng nội dung thông điệp theo cùng quy tắc băm.
3. Tính **w = s⁻¹ mod n**, **u₁ = z × w mod n**, **u₂ = r × w mod n**.
4. Tính **X = u₁G + u₂Q**; từ chối nếu kết quả là điểm vô cực.
5. Chấp nhận chữ ký nếu **x(X) mod n = r**.

~~~mermaid
flowchart LR
    M["Thông điệp m"] --> V["ECDSA verify"]
    S["Chữ ký r, s"] --> V
    P["Public key Q đã xác thực"] --> V
    V --> D{"Hợp lệ?"}
    D -->|Có| A["Kiểm tra danh tính, quyền, thời hạn, ngữ cảnh"]
    D -->|Không| R["Từ chối"]
~~~

**Verify trả về true chỉ khẳng định chữ ký hợp lệ về mặt mật mã với public key đã đưa vào**, không tự chứng minh public key thuộc đúng chủ thể, chứng chỉ còn hiệu lực, token còn thời hạn hay giao dịch được phép thực hiện. Hệ thống phải kiểm tra những điều kiện ấy ở tầng giao thức và quyền truy cập.

## 4. Điểm sống còn: nonce k của ECDSA

Trong ECDSA, chữ **nonce** chỉ **số bí mật k dùng cho mỗi lần ký**. Không nhầm nó với **nonce/IV thường được truyền kèm bản mã AES-GCM**.

| Thuộc tính | ECDSA k | AES-GCM nonce |
|---|---|---|
| Mục đích | Tham số bí mật tạm thời khi tạo chữ ký | Giá trị xác định luồng mã hóa trong AEAD |
| Có được công khai? | **Không** | Thường được công khai/lưu cùng bản mã |
| Phạm vi duy nhất | Mỗi chữ ký dùng k phù hợp, không tái sử dụng giữa các thông điệp với cùng private key | Mỗi phép mã hóa phải có nonce không trùng với cùng khóa |
| Khi rò rỉ | Có thể suy ra private key ECDSA từ chữ ký và k | Chỉ lộ nonce GCM không đồng nghĩa lộ khóa; reuse lại rất nguy hiểm |
| Biện pháp | CSPRNG an toàn hoặc thuật toán k xác định được chuẩn hóa | Nonce ngẫu nhiên được kiểm soát xác suất hoặc bộ đếm duy nhất |

### 4.1. Vì sao rò k có thể làm lộ private key?

Từ công thức ký:

\[
s = k^{-1}(z + rd) \bmod n
\]

Nếu người khác biết **k** của một chữ ký hợp lệ và biết **z, r, s**, họ có thể giải ra **d** theo đại số modulo n. Vì vậy **k phải được giữ bí mật**, dù chữ ký và thông điệp được công khai.

Nếu cùng một **k** bị tái sử dụng để ký hai thông điệp **khác nhau** với cùng private key, các phương trình chữ ký có thể làm lộ **k** và cuối cùng là private key. Đây là lỗi đặc biệt nghiêm trọng: một chữ ký sai quy trình có thể đe dọa **toàn bộ lịch sử chữ ký và quyền ký tương lai** của khóa dài hạn.

Không đưa **k** vào log, telemetry, stack trace, cơ chế cache, trình gỡ lỗi hoặc bản sao bộ nhớ không được bảo vệ. Không sinh k từ timestamp, bộ đếm đơn giản, seed cố định hoặc RNG không phù hợp cho mật mã.

### 4.2. Random k và deterministic k

Có hai hướng triển khai an toàn khi được thuật toán/chính sách cho phép:

- **Random k:** lấy từ CSPRNG đúng cách, với cách lấy mẫu tránh thiên lệch đáng kể và không lặp/không dự đoán được.
- **Deterministic k:** dẫn xuất k từ private key và hash thông điệp bằng thuật toán đã chuẩn hóa, chẳng hạn **RFC 6979**. Với cùng private key và cùng thông điệp, kết quả ký có thể có cùng k theo phương pháp này. Điều đó **không đồng nghĩa** dùng lại k cho hai thông điệp khác nhau.

Cách sinh k xác định giúp giảm phụ thuộc vào nguồn ngẫu nhiên **tại mỗi lần ký**, nhưng vẫn cần nguồn ngẫu nhiên an toàn khi tạo private key, triển khai chống kênh kề và kiểm tra đúng thuật toán. Không tự viết công thức k deterministic theo suy đoán.

**Lưu ý Java:** Khi gọi **SHA256withECDSA** qua JCA, ứng dụng thường không tự truyền k; provider chịu trách nhiệm sinh hoặc dẫn xuất k. **Không mặc định khẳng định** provider đang dùng RFC 6979 nếu chưa có tài liệu của provider. Cần đánh giá provider và HSM theo chính sách bảo mật của dự án.

### 4.3. Rủi ro kênh kề

Ngay cả khi k không bị log hay tái sử dụng, khóa vẫn có thể rò rỉ qua **side-channel** nếu triển khai tính toán phụ thuộc bí mật gây chênh lệch thời gian, bộ nhớ cache hoặc điện năng. Hệ thống bảo vệ khóa ký lâu dài nên ưu tiên **thư viện và thiết bị đã đánh giá**, cấu hình đúng, cập nhật bản vá và giới hạn ai có quyền gọi sign.

## 5. Định dạng chữ ký ECDSA: DER, P1363 và ES256

Về toán học, chữ ký là **hai số nguyên (r, s)**. Nhưng dữ liệu truyền qua API hoặc lưu trong file phải có **encoding**, và đây là nguồn lỗi tương thích phổ biến.

| Định dạng | Cách biểu diễn | Nơi thường gặp |
|---|---|---|
| **ASN.1 DER** | Một SEQUENCE chứa hai INTEGER r và s; độ dài có thể thay đổi | Nhiều API JCA ECDSA mặc định, chứng chỉ/chữ ký theo các giao thức ASN.1 |
| **IEEE P1363 / raw** | Nối hai chuỗi byte độ dài cố định biểu diễn r và s, theo kích thước đường cong | Một số API hoặc giao thức định nghĩa chữ ký raw |
| **JWS ES256** | Chữ ký raw **r ∥ s**, mỗi số được ghi đúng **32 byte big-endian**, tổng 64 byte trước base64url | JWT/JWS dùng ES256 |

**Ví dụ:** Chữ ký của **SHA256withECDSA** trong nhiều provider JCA được mã hóa dưới dạng **DER** và có thể dài hơn 64 byte. Trong khi đó, **JWS ES256** yêu cầu chuỗi 64 byte **r ∥ s** trước khi base64url-encode. Không thể lấy byte DER rồi gắn thẳng vào JWS.

Một số provider Java hỗ trợ tên thuật toán dạng **SHA256withECDSAinP1363Format**. Khả năng hỗ trợ phụ thuộc phiên bản Java và provider. Nếu phải chuyển đổi DER ↔ raw, hãy dùng thư viện đã được kiểm chứng, kiểm tra **r, s**, độ dài, dấu của INTEGER, tính chuẩn tắc của DER và các quy tắc giao thức. Không cắt byte theo vị trí cố định vì DER có thể thêm byte 0 ở đầu INTEGER để biểu diễn số dương.

### 5.1. Tính biến đổi chữ ký (signature malleability)

Với ECDSA chuẩn, cặp **(r, s)** và **(r, n − s)** có thể cùng xác minh thành công cho một thông điệp. Vì thế:

- **Chữ ký hợp lệ về mặt toán học không nhất thiết có duy nhất một chuỗi byte**.
- Một số giao thức yêu cầu dạng **low-S** để chuẩn hóa hoặc chống khả năng thay đổi định danh giao dịch.
- Bên ký và bên xác minh cần tuân thủ **chính sách của giao thức cụ thể**. Không áp đặt low-S cho mọi hệ thống ECDSA nếu chuẩn giao thức không yêu cầu hoặc xử lý khác.

Chống replay, chống rollback và xác định giao dịch duy nhất phải được xử lý rõ ràng; chữ ký số tự nó không ngăn kẻ tấn công gửi lại nguyên thông điệp đã được ký hợp lệ.

## 6. Java JCA: tạo, ký và xác minh bằng ECDSA P-256

Đoạn mã sau minh họa **ECDSA với SHA-256** và đường cong **secp256r1 (NIST P-256)** bằng Java Cryptography Architecture. Khóa được tạo trong bộ nhớ chỉ cho mục đích học thuật; mã không trình bày lưu khóa bền vững, cấp chứng chỉ hay tích hợp HSM.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

public final class EcdsaExample {

    public static void main(String[] args) throws Exception {
        // 1. Tạo cặp khóa ECDSA trên NIST P-256.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(
            new ECGenParameterSpec("secp256r1"),
            new SecureRandom()
        );
        KeyPair pair = generator.generateKeyPair();

        // 2. Chọn chính xác byte của thông điệp được ký.
        byte[] message = "order=123;amount=5000;currency=VND"
            .getBytes(StandardCharsets.UTF_8);

        // 3. Ký với private key. Provider thực hiện SHA-256
        //    và sinh/dẫn xuất nonce k theo cách triển khai của nó.
        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(pair.getPrivate(), new SecureRandom());
        signer.update(message);
        byte[] signature = signer.sign();

        // 4. Xác minh với public key tương ứng.
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        if (!verifier.verify(signature)) {
            throw new IllegalStateException("Invalid ECDSA signature");
        }

        // 5. Thay đổi thông điệp khiến xác minh thất bại.
        byte[] tampered = "order=123;amount=9000;currency=VND"
            .getBytes(StandardCharsets.UTF_8);
        Signature tamperedVerifier =
            Signature.getInstance("SHA256withECDSA");
        tamperedVerifier.initVerify(pair.getPublic());
        tamperedVerifier.update(tampered);

        if (tamperedVerifier.verify(signature)) {
            throw new IllegalStateException(
                "A modified message was incorrectly accepted"
            );
        }

        System.out.println("ECDSA sign/verify OK");
    }
}
~~~

Trong mã này:

1. **ECGenParameterSpec("secp256r1")** chọn curve. **EC** ở KeyPairGenerator chỉ loại khóa; **SHA256withECDSA** ở Signature chọn thao tác chữ ký cùng hash.
2. **Private key** dùng cho **initSign**, **public key** dùng cho **initVerify**. Không bao giờ gửi private key cho verifier.
3. **Signature.update(message)** ký **đúng dãy byte** được truyền. Các thao tác thêm khoảng trắng, đổi mã hóa Unicode, đổi thứ tự trường JSON hoặc chuẩn hóa dữ liệu có thể làm thay đổi byte và khiến chữ ký không còn khớp.
4. **SecureRandom** ở ví dụ không cho phép ứng dụng tự quản lý k; provider thực hiện các phép toán an toàn bên trong. Lựa chọn provider, tính tương thích và chính sách nonce cần được kiểm tra khi đưa vào sản xuất.
5. **Verify true** chỉ nói chữ ký toán học khớp với public key đã đưa vào. Ứng dụng thực tế cần kiểm tra **nguồn gốc và thời hạn của public key, quyền ký, key usage, dữ liệu giao dịch và chính sách chống replay**.
6. Với các provider JCA phổ biến, kết quả của **SHA256withECDSA** là **DER**; khi dùng trong JWS ES256 phải chuyển sang dạng **P1363 raw** đúng chuẩn hoặc chọn provider/API hỗ trợ trực tiếp.

Trong hệ thống thực tế, private key nên được tạo hoặc import an toàn vào **KMS/HSM** và việc ký được thực hiện qua API có quyền truy cập, thay vì để ứng dụng tùy ý xuất private key ra file.

## 7. Chọn ECDSA và hàm băm đúng mục đích

| Thuộc tính | Cặp thông dụng | Lưu ý |
|---|---|---|
| Curve | **P-256** | Thường kết hợp SHA-256 trong ECDSA, ký JWS ES256 |
| Curve | **P-384** | Thường kết hợp SHA-384 |
| Curve | **P-521** | Thường kết hợp SHA-512 |
| Hash | **SHA-256 / SHA-384 / SHA-512** | Chọn theo tiêu chuẩn giao thức và mức an toàn mong muốn |
| Signature API | **SHA256withECDSA** | Tính hash rồi ký bằng ECDSA; khác với API chỉ nhận digest đã băm |
| Protocol ID | **ES256 / ES384 / ES512** | Mỗi mã quy định tổ hợp curve, hash và định dạng chữ ký theo JWS |

Không hiểu **ES256** là "chữ ký dài 256 bit": đối với ES256, P-256 có r và s mỗi giá trị được mã hóa **32 byte**, dẫn đến chữ ký raw **64 byte** trước base64url.

**Không tự chọn SHA-1 hoặc băm yếu cho chữ ký mới.** Một bản nâng cấp thuật toán phải tương thích với hệ thống xác minh, chứng chỉ, định dạng signature và thời hạn lưu giữ chữ ký. Trong ứng dụng có chuẩn ngành hoặc pháp lý bắt buộc, tuân theo bộ tham số và thư viện được phê duyệt thay vì tự phối curve/hash.

## 8. ECDSA trong PKI, TLS, JWT/JWS và chữ ký phần mềm

### 8.1. Chứng chỉ số (PKI)

Một **chứng chỉ X.509** có thể gắn public key ECDSA với danh tính máy chủ hoặc tổ chức, do CA ký theo cơ chế tin cậy. Khi xác minh chữ ký liên quan, bên nhận phải kiểm tra:

- **Chuỗi chứng chỉ** đến trust anchor được chấp nhận.
- **Danh tính** đúng mục đích (chẳng hạn hostname hoặc định danh dịch vụ).
- **Thời hạn hiệu lực**, **key usage/extended key usage** và các ràng buộc chính sách.
- **Trạng thái thu hồi** qua cơ chế như CRL/OCSP hoặc cơ chế tin cậy tương ứng với ứng dụng.
- **Thuật toán, tham số curve, cách mã hóa chữ ký** có được cho phép hay không.

Một chữ ký ECDSA vẫn có thể verify đúng về mặt toán học khi **chứng chỉ đã hết hạn hoặc bị thu hồi**. Hệ thống cần đặt câu hỏi khác nhau: chữ ký có đúng với khóa không, khóa có được tin ở thời điểm cần thiết không, và danh tính có được phép thực hiện hành động ấy không?

### 8.2. TLS

Trong các cấu hình TLS hiện đại, khóa chứng chỉ ECDSA chủ yếu dùng để **xác thực bắt tay**, trong khi **(EC)DHE** được dùng để thiết lập khóa phiên. Vì vậy ECDSA có thể cùng tồn tại với forward secrecy mà không đóng vai trò mã hóa dữ liệu phiên.

Lộ private key ECDSA của máy chủ là sự cố nghiêm trọng về **mạo danh và tạo chữ ký mới**; nhưng không nên tự suy rằng tất cả bản ghi TLS cũ đã được bảo vệ bằng (EC)DHE sẽ bị giải mã chỉ do lộ khóa xác thực này. Cần phân tích phiên, giao thức và bí mật phiên riêng.

### 8.3. JWT/JWS

Với **JWS ES256**, hệ thống ký một đầu vào đã định nghĩa rõ từ header và payload được mã hóa, dùng ECDSA P-256 với SHA-256. Khi xác minh JWT, ngoài chữ ký, cần kiểm tra:

- Thuật toán được cấu hình **cho phép**, không tin tùy tiện giá trị header do người gửi cung cấp.
- **issuer, audience, expiration, not-before** và scope/claims ứng dụng.
- **kid** được ánh xạ tới public key đã được xác thực trong trust store hoặc JWKS đáng tin; **kid chỉ là ID**, không phải bằng chứng tin cậy.
- Cách tải JWKS và **cache** khi xoay/thu hồi khóa; hệ thống xác minh phải ngừng tin khóa cũ theo chính sách khi bị xâm phạm.

ECDSA ký JWT **không mã hóa** JWT. Nếu payload chứa thông tin bí mật, cần giới hạn nội dung hoặc dùng giải pháp bảo mật khác, chẳng hạn cơ chế mã hóa phù hợp.

### 8.4. Gói phần mềm và tài liệu

Khi ký một gói phần mềm hoặc văn bản, phải quy định rõ **đối tượng được ký**. Nếu chỉ ký một trường hash nhưng không ràng buộc version, ID nhà phát hành, tenant hay thời điểm, hệ thống có thể bị tráo đổi ngữ cảnh hoặc phát lại hiện vật cũ.

Có thể dùng **manifest có cấu trúc** chứa tên thành phần, phiên bản, hash, thuật toán và thời hạn, rồi ký **đúng dãy byte đã chuẩn hóa** của manifest. Bên xác minh phải kiểm tra cả tính hợp lệ của chữ ký và chính sách nội dung.

## 9. ECDSA và KMS/HSM: ai được sử dụng private key?

**Key Management Service (KMS)** quản lý vòng đời, phiên bản, phân quyền và các phép toán với khóa. **Hardware Security Module (HSM)** cung cấp miền phần cứng được thiết kế để giữ bí mật key material và thực hiện phép toán mật mã. Tùy dịch vụ, private key ECDSA có thể **không được phép export**; ứng dụng gửi hash hoặc thông điệp đến API **Sign** và nhận chữ ký.

~~~mermaid
flowchart TD
    U["Dịch vụ ứng dụng"] -->|Kiểm tra quyền ký nghiệp vụ| A["IAM / chính sách ứng dụng"]
    A -->|Yêu cầu Sign bằng key ID/version| K["KMS / HSM"]
    K -->|Ký bằng private key được bảo vệ| S["Chữ ký ECDSA"]
    S --> O["Thông điệp đã ký + key ID"]
    P["Public key / chứng chỉ đã xác thực"] --> V["Dịch vụ Verify"]
    O --> V
    V --> T["Kiểm tra quyền, thời hạn, nghiệp vụ, chống replay"]
~~~

**Lợi ích:**

- Hạn chế số nơi có thể truy cập **private key dạng rõ**.
- Phân quyền thao tác **sign, verify, rotate, disable, delete** riêng biệt.
- Có thể kiểm toán **danh tính gọi, key ID/version, thao tác, thời gian và kết quả**.
- Quản lý việc tạo khóa, thay phiên bản và hủy khóa theo chính sách.

**Giới hạn:** KMS/HSM không thể tự biết một yêu cầu ký **có đúng nội dung nghiệp vụ** hay không. Nếu dịch vụ có quyền Sign quá rộng bị chiếm quyền, kẻ tấn công có thể yêu cầu HSM tạo chữ ký hợp lệ mà không cần lấy private key. Do đó cần kiểm tra **ai được ký cho tác vụ gì**, phê duyệt khi cần, kiểm soát số lượt, phát hiện ký bất thường và audit.

Một số dịch vụ nhận **message** rồi tự hash; dịch vụ khác nhận **digest đã được hash**. Nếu ứng dụng hash sẵn rồi gọi API đang mong message, có thể xảy ra **double hashing**. Phải xác nhận hợp đồng API, thuật toán và định dạng chữ ký được trả về.

## 10. Vòng đời khóa ECDSA: tạo, cấp phát, dùng, xoay vòng, thu hồi và hủy

~~~mermaid
flowchart LR
    A["Sinh cặp khóa trong miền tin cậy"] --> B["Gắn danh tính, chứng chỉ và quyền"]
    B --> C["Ký và kiểm toán"]
    C --> D["Rotation / tạo cặp khóa mới"]
    D --> E["Chuyển sang ký bằng khóa mới"]
    E --> F["Ngừng ký bằng khóa cũ"]
    F --> G["Thu hồi tin cậy / vô hiệu hóa"]
    G --> H["Lưu giữ hoặc hủy có kiểm soát"]
~~~

| Giai đoạn | Việc cần làm với ECDSA | Rủi ro nếu làm sai |
|---|---|---|
| **Generation** | Chọn curve được cho phép, sinh private key bằng CSPRNG/HSM, kiểm tra public key | Khóa yếu, curve sai hoặc private key lộ từ lúc tạo |
| **Provisioning** | Phân phối public key/chứng chỉ qua kênh xác thực; gắn danh tính và mục đích | Kẻ tấn công thay public key; verifier tin nhầm chủ thể |
| **Storage** | Bảo vệ private key trong KMS/HSM hoặc kho khóa phù hợp, quản lý backup | Rò private key từ file, log, bản sao lưu hoặc máy phát triển |
| **Usage** | Giới hạn người được sign; bảo đảm k an toàn và thông điệp đúng ngữ cảnh | Mạo danh do lạm dụng quyền hoặc lỗi nonce k |
| **Rotation** | Sinh khóa mới; phát hành public key/chứng chỉ mới trước khi chuyển đường ký | Client không xác minh được chữ ký mới hoặc vẫn tin khóa cũ sai chính sách |
| **Revocation** | Disable Sign với khóa cũ, thu hồi chứng chỉ/trust và đồng bộ mọi verifier | Chữ ký giả mạo vẫn được chấp nhận tại client chưa cập nhật |
| **Destruction** | Hủy private key đúng thời điểm sau khi đánh giá lưu giữ và bằng chứng chữ ký | Mất khả năng vận hành hoặc truy xuất chứng cứ; bản sao rò rỉ vẫn tồn tại |

### 10.1. Khi xoay vòng khóa ký

Một quy trình triển khai thường gồm:

1. **Sinh cặp khóa ECDSA mới** và cấp quyền KMS/HSM theo nguyên tắc đặc quyền tối thiểu.
2. **Công bố public key/chứng chỉ mới** qua kênh tin cậy, chuẩn bị cho các verifier.
3. **Chuyển dịch vụ ký** từ key version cũ sang mới; ghi key ID/version hoặc thông tin chứng chỉ cùng hiện vật đã ký.
4. **Giảm hoặc ngừng quyền Sign** trên private key cũ; theo dõi lỗi xác minh trong giai đoạn chuyển đổi.
5. **Quyết định chính sách chữ ký lịch sử**: có tiếp tục chấp nhận chữ ký được tạo trước ngày hết hạn hoặc thu hồi không; cần timestamp/chứng cứ nào?
6. **Vô hiệu hóa, thu hồi và hủy** theo thời hạn đã phê duyệt, khi không còn phụ thuộc chính đáng.

Với chữ ký số, **thay khóa không cần ký lại mọi dữ liệu lịch sử trong mọi trường hợp**. Để xác minh một chữ ký cũ, thường cần public key/chứng chỉ thích hợp, bằng chứng tin cậy và chính sách thời điểm ký. **Không nên tùy tiện xóa mọi dấu vết public key cũ**, vì việc này có thể gây mất khả năng kiểm tra chữ ký hợp lệ trong kho lưu trữ lâu dài.

### 10.2. Khi nghi lộ private key

Nếu private key ECDSA đã bị lộ, cần:

- Ngăn gọi **Sign** tiếp bằng khóa bị ảnh hưởng tại mọi điểm thực thi.
- Thu hồi hoặc đánh dấu **không còn tin cậy** đối với chứng chỉ/public key theo cơ chế hệ thống.
- Sinh và phân phối khóa mới, đồng bộ trust store, JWKS, gateway, ứng dụng và cache.
- Điều tra chữ ký lạ, phiên/token liên quan, thời điểm bắt đầu rò rỉ, các bên đã nhận chữ ký.
- Quy định cách xử lý **chữ ký lịch sử**, bằng chứng timestamp và những dữ liệu phải ký lại hoặc đánh giá lại.
- Không coi **xóa khóa khỏi KMS** là phương án đủ nếu private key từng được export hoặc sao chép ngoài KMS.

Thu hồi trong KMS **không vô hiệu hóa** khả năng ký của một kẻ đã giữ được private key ở nơi khác. Chỉ những verifier áp dụng chính sách thu hồi và tin cậy mới từ chối chữ ký liên quan.

## 11. ECDSA, envelope encryption và bảo vệ dữ liệu

ECDSA là thuật toán ký số; nó **không trực tiếp bọc DEK hoặc mã hóa dữ liệu** trong hệ thống envelope encryption. Một kiến trúc bảo mật tổng thể có thể dùng các lớp khác nhau:

~~~text
Dữ liệu hồ sơ
   |
   +-- AES-GCM với DEK --------> ciphertext + tag + nonce
   |
   +-- KMS/HSM bảo vệ KEK -----> encrypted DEK
   |
   +-- ECDSA private key ------> chữ ký của manifest / giao dịch / metadata
                                 (khi nghiệp vụ thực sự cần chữ ký)
~~~

Những điểm kết nối:

- **AES-GCM** bảo vệ bí mật và toàn vẹn dữ liệu; **ECDSA** xác minh chữ ký và danh tính gắn với public key.
- **KEK/DEK** có vòng đời, chính sách và phép toán **wrap/unwrap/encrypt/decrypt** khác với khóa ECDSA **sign/verify**.
- Không dùng cùng một private key ECDSA như đầu vào tùy tiện để dẫn xuất khóa AES hoặc làm khóa ECDH.
- Nếu ký manifest chứa hash bản mã và phiên bản, phải quy định rõ **byte nào được ký**, cách chuẩn hóa, cách liên kết với bản ghi và điều kiện chống replay.
- Khi chuyển DEK/KEK hoặc xoay khóa ECDSA, nên **ghi nhận key ID/version riêng cho từng loại khóa**; không gộp tất cả vào một biến khóa không rõ chức năng.

Một thiết kế có KMS/HSM tốt vẫn cần **IAM, kiểm toán và chính sách dữ liệu**: kẻ có quyền ký tùy tiện có thể tạo chứng từ sai dù private key không rời HSM.

## 12. Những sai lầm thường gặp khi sử dụng ECDSA

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Tự tạo k từ timestamp, seed cố định hoặc RNG yếu | Có thể rò private key từ chữ ký | Dùng provider/HSM đáng tin, CSPRNG đúng hoặc deterministic k chuẩn hóa |
| Tái sử dụng cùng k để ký hai thông điệp khác nhau | Có thể khôi phục private key | Bảo đảm thuật toán sinh k đúng; không tự quản lý k bằng code ứng dụng |
| Để private key trong source, image hoặc log | Mất bí mật khóa và khả năng bị giả mạo chữ ký | KMS/HSM, quyền tối thiểu, hạn chế export, quản lý backup |
| Xem Verify true là chứng cứ danh tính | Kẻ tấn công đưa public key của mình rồi ký nội dung | Xác minh public key qua chứng chỉ/trust store đã tin cậy |
| Dùng nhầm đường cong hoặc định dạng signature | Không tương thích; lỗi xác minh hoặc từ chối chữ ký | Kiểm tra curve, hash, DER/P1363 và protocol ID |
| Đưa DER trực tiếp vào JWS ES256 | Sai định dạng 64 byte r ∥ s | Chuyển mã hóa đúng chuẩn hoặc dùng API hỗ trợ JWS |
| Tin header JWT tùy ý để chọn thuật toán/khóa | Bỏ qua chính sách xác minh, chọn nhầm trust key | Allowlist thuật toán và khóa theo issuer, xác thực kid/JWKS |
| Không chuẩn hóa dãy byte thông điệp | Chữ ký hợp lệ ở một dịch vụ nhưng sai ở dịch vụ khác | Định nghĩa canonical bytes, charset và thứ tự trường |
| Không kiểm tra giới hạn r, s hoặc public key hợp lệ | Tăng bề mặt lỗi xác minh/đầu vào độc hại | Dùng thư viện kiểm chứng đầy đủ và validate khóa được import |
| Bỏ qua yêu cầu low-S của giao thức | Signature malleability hoặc giao thức từ chối hiện vật | Tuân thủ quy tắc canonical signature của giao thức |
| Không chuyển trust store khi rotate | Client từ chối chữ ký mới hoặc tin khóa đã thu hồi | Phân phối public key mới, giới hạn cache, kiểm thử verifier |
| Cho phép dịch vụ gọi Sign mọi nội dung | Bị lạm dụng tạo chữ ký hợp lệ | Phân quyền theo nghiệp vụ, hạn mức và audit |
| Không bảo vệ chữ ký lịch sử khi hủy khóa | Mất khả năng kiểm tra nguồn gốc tài liệu cũ | Lưu public key/chứng cứ tin cậy và chính sách xác minh lịch sử |

## 13. Kiểm thử ECDSA trong hệ thống thực tế

Đối với một dịch vụ ký xác thực giao dịch, tối thiểu cần xác minh:

| Tình huống kiểm thử | Kết quả kỳ vọng |
|---|---|
| Ký thông điệp m với private key và verify bằng public key cùng cặp | **Thành công** |
| Thay một byte của m nhưng giữ nguyên chữ ký | **Thất bại** |
| Thay public key bằng khóa độc lập khác | **Thất bại** |
| Chữ ký DER hoặc raw sai định dạng/truncated | **Bị từ chối** |
| Curve hoặc thuật toán không được cho phép | **Bị từ chối** |
| Chữ ký toán học đúng nhưng chứng chỉ hết hạn/không thuộc chủ thể | **Bị từ chối theo trust policy** |
| Key version bị disable nhưng caller vẫn gọi Sign trong KMS | **Bị từ chối** |
| Principal không được phép gọi Sign | **Bị từ chối và được kiểm toán** |
| JWKS/trust store đã thu hồi public key cũ | **Không chấp nhận hiện vật mới theo khóa cũ theo chính sách** |
| Ký thông điệp nghiệp vụ có cấu trúc khác cách chuẩn hóa | **Không chấp nhận nhầm** |

**Không cố chứng minh k an toàn chỉ bằng việc thấy chữ ký khác nhau**. Với ECDSA có k ngẫu nhiên, hai lần ký cùng một thông điệp thường tạo chữ ký khác nhau; với deterministic k, chúng có thể tạo cùng chữ ký. Cả hai hành vi có thể hợp lệ. Muốn đánh giá bảo mật k cần xem **tài liệu và chứng nhận provider/HSM, quá trình sinh entropy, chính sách sử dụng khóa và thử nghiệm chuyên môn**.

Về kiểm toán, nên thu **định danh workload, loại thao tác, key ID/version, thời điểm, kết quả, mã lỗi và ngữ cảnh được phép**; tránh ghi **private key, k, token nhạy cảm hoặc toàn bộ bản rõ**. Nếu ghi hash thông điệp để đối chiếu, cần cân nhắc nguy cơ suy đoán thông tin từ nội dung có entropy thấp và giới hạn quyền đọc log.

## 14. Bài tập tình huống: dịch vụ ký phiếu giao dịch

Giả sử hệ thống đặt hàng sử dụng ECDSA P-256 để ký phiếu giao dịch do backend tạo. Chữ ký được kiểm tra ở service giao hàng và service kế toán.

**Thiết kế ban đầu có ba vấn đề:**

1. Private key được copy vào cả ba service để "dễ kiểm tra chữ ký".
2. Backend ký chuỗi JSON do client cung cấp mà không xác nhận số tiền và quyền của người dùng.
3. Khi thay khóa ký, service kế toán vẫn cache public key cũ vô thời hạn.

**Thiết kế cải tiến:**

1. **Chỉ backend ký** thông qua KMS/HSM có quyền Sign; hai service còn lại dùng **public key tin cậy** để Verify.
2. Backend xây dựng **payload chuẩn hóa từ dữ liệu đã được phê duyệt**, gồm mã giao dịch, người bán, số tiền, đơn vị tiền tệ, phiên bản và điều kiện thời hạn; thêm nonce giao dịch hoặc ID duy nhất nếu cần chống replay.
3. Lưu **key ID/version** và thuật toán bên cạnh chữ ký; kiểm tra chính sách được phép và ngữ cảnh nghiệp vụ tại verifier.
4. Trong đợt rotation, công bố public key mới trước khi đổi đường ký; xác minh khả năng nhận chữ ký mới ở mọi service. Khi private key cũ lộ, **thu hồi niềm tin** đối với public key cũ, loại bỏ cache và xử lý phiếu đã phát hành theo thời điểm.
5. Audit ai/yêu cầu nào được phép tạo chữ ký, khóa nào đã dùng, trạng thái phê duyệt, kết quả xác minh và sự kiện bất thường. Không đưa private key hoặc nonce k vào log.

Mô hình này tách đúng các trách nhiệm: **ứng dụng quyết định có được phép ký không; KMS/HSM thực hiện phép ký an toàn; verifier kiểm tra chữ ký cùng chính sách tin cậy và nghiệp vụ**.

## 15. Tự kiểm tra

**Câu 1. ECDSA có giữ bí mật nội dung đã ký không?**

**Trả lời:** Không. ECDSA tạo và xác minh chữ ký; muốn giữ bí mật nội dung cần cơ chế mã hóa riêng, chẳng hạn AES-GCM với quản lý DEK/KEK phù hợp.

**Câu 2. Public key có cần giữ bí mật không?**

**Trả lời:** Không. Public key có thể được công bố, nhưng **phải xác thực nguồn gốc và chủ sở hữu** để ngăn thay khóa hoặc mạo danh.

**Câu 3. Nonce k của ECDSA có thể lưu công khai bên cạnh chữ ký như nonce AES-GCM không?**

**Trả lời:** Không. k phải được giữ bí mật. Lộ k của chữ ký ECDSA có thể làm lộ private key; việc tái sử dụng k giữa các thông điệp khác nhau với cùng private key cũng cực kỳ nguy hiểm.

**Câu 4. Dùng RFC 6979 có nghĩa cùng một k được dùng cho mọi thông điệp không?**

**Trả lời:** Không. k được dẫn xuất theo **private key và hash của từng thông điệp**, theo thuật toán xác định được chuẩn hóa. Cùng thông điệp có thể cho cùng k, nhưng các thông điệp khác nhau không được làm phát sinh việc tái sử dụng k theo cách gây rò khóa.

**Câu 5. Chữ ký SHA256withECDSA của JCA có thể đưa nguyên byte vào JWT ES256 không?**

**Trả lời:** Không nhất thiết. Nhiều provider trả chữ ký DER, trong khi JWS ES256 cần 64 byte raw **r ∥ s** trước base64url. Phải chuyển đổi đúng hoặc dùng API hỗ trợ chuẩn đích.

**Câu 6. Vì sao một chữ ký ECDSA hợp lệ vẫn có thể bị hệ thống từ chối?**

**Trả lời:** Vì chứng chỉ/public key có thể không được tin, đã hết hạn/thu hồi, chủ thể không có quyền hoặc thông điệp sai ngữ cảnh nghiệp vụ, thời hạn hay chính sách chống replay.

**Câu 7. Khi khóa ký ECDSA bị lộ, chỉ rotate ở KMS đã đủ chưa?**

**Trả lời:** Chưa. Cần thu hồi quyền ký cũ, phát hành cặp khóa mới, cập nhật mọi verifier/trust store/JWKS, điều tra chữ ký đáng ngờ và đánh giá bản sao private key ngoài KMS.

**Câu 8. Ed25519 có phải là cùng thuật toán với ECDSA P-256 không?**

**Trả lời:** Không. Ed25519 thuộc EdDSA; ECDSA P-256 dùng cơ chế và định dạng chữ ký khác. Chỉ thay tên curve/algorithm trong cấu hình sẽ không tạo tương thích.

**Câu 9. Giữ private key trong HSM có ngăn mọi kiểu giả mạo chữ ký không?**

**Trả lời:** Không. Nếu ứng dụng có quyền Sign bị chiếm quyền, kẻ tấn công vẫn có thể yêu cầu HSM ký nội dung trái phép. Cần IAM, kiểm tra nghiệp vụ, hạn mức và kiểm toán.

**Câu 10. ECDSA và ECDHE phối hợp trong TLS ra sao?**

**Trả lời:** Trong các cấu hình phù hợp, ECDSA xác thực bên tham gia bằng chữ ký, còn (EC)DHE góp phần thiết lập bí mật phiên và có thể cung cấp forward secrecy. Chúng có mục đích khác nhau.

## 16. Ghi nhớ

**ECDSA** ký bằng **private key d** và xác minh bằng **public key Q** trên một đường cong elliptic được lựa chọn đúng. Kết quả toán học là cặp số **(r, s)**, nhưng ứng dụng phải xử lý đúng **hash, encoding, public-key trust, chữ ký theo byte, tình trạng chứng chỉ và chính sách nghiệp vụ**.

Trong quản lý khóa, ưu tiên ba câu hỏi cốt lõi: **private key được bảo vệ ở đâu và ai được quyền ký? Nonce bí mật k cho mỗi chữ ký được tạo an toàn ra sao? Khi xoay vòng hoặc thu hồi khóa, những hệ thống xác minh nào phải thay đổi niềm tin?** Đó là nền tảng để kết nối ECDSA với **KMS/HSM, chữ ký số, IAM, kiểm toán, vòng đời khóa và kiến trúc bảo mật sử dụng mật mã đối xứng lẫn bất đối xứng**.
