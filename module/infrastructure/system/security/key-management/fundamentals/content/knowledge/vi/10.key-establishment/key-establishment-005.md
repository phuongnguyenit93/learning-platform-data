# ECDH — Thỏa thuận khóa trên đường cong elliptic

## 1. ECDH là gì?

**ECDH (Elliptic-Curve Diffie–Hellman)** là một cơ chế **thỏa thuận khóa** (*key agreement*) sử dụng mật mã đường cong elliptic. Hai bên có thể cùng tính ra một **bí mật chung (shared secret)**, mặc dù họ chỉ trao đổi các giá trị **public key** trên đường truyền và không phải gửi trực tiếp private key hoặc shared secret cho nhau.

ECDH là một thành phần quan trọng của **key establishment** — quá trình giúp các bên thiết lập vật liệu khóa dùng để bảo vệ liên lạc. Trong hệ thống thực, kết quả ECDH thường đi qua **KDF (Key Derivation Function)** để tạo các khóa đối xứng, ví dụ khóa dùng cho **AES-GCM** hoặc **ChaCha20-Poly1305**.

Ví dụ: một ứng dụng Java cần kết nối đến dịch vụ khác qua HTTPS. Trong một cơ chế TLS có sử dụng ECDHE, client và server đóng góp các cặp khóa thỏa thuận tạm thời để thiết lập bí mật phiên, từ đó giao thức dẫn xuất khóa bảo vệ lưu lượng. Server còn phải **xác thực** với client; chỉ trao đổi khóa ECDH thuần túy **không tự ngăn tấn công man-in-the-middle (MITM)**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, việc học ECDH không chỉ dừng ở phép toán. Cần kết nối nó với **vòng đời khóa**, mật mã bất đối xứng/đối xứng, chữ ký số, KMS/HSM, envelope encryption, phân quyền sử dụng khóa và kiểm toán.

> **Ý chính:** ECDH giúp tạo **shared secret**; nó **không tự xác thực danh tính đối tác**, **không trực tiếp mã hóa dữ liệu ứng dụng** và kết quả thỏa thuận **không nên được dùng thẳng làm khóa AES khi giao thức yêu cầu KDF**.

### Mục tiêu sau bài học

Người học có thể:

1. Diễn giải vì sao hai bên tính được cùng shared secret từ private/public key khác nhau.
2. Phân biệt **ECDH**, **ECDHE**, **X25519**, **ECDSA**, **key transport** và **session key**.
3. Dùng **KDF/HKDF** sau ECDH và hiểu yêu cầu xác thực khóa công khai.
4. Phát hiện các lỗi triển khai phổ biến: MITM, tái sử dụng khóa tạm, public key không hợp lệ, nhầm curve và lộ shared secret.
5. Thiết kế cách quản lý ECDH key theo vòng đời, quyền tối thiểu và chính sách KMS/HSM.

## 2. Thuật ngữ và thành phần cần biết

| Thuật ngữ | Vai trò trong ECDH | Điều cần nhớ |
| --- | --- | --- |
| **Elliptic curve (EC)** | Cấu trúc toán học dùng làm nền cho nhóm mật mã | Phải chọn curve và tham số chuẩn, không tự tạo |
| **Base point G** | Điểm sinh công khai trên nhóm được chọn | Cùng curve/nhóm với các khóa |
| **Private agreement key d** | Giá trị bí mật do một bên giữ | Không truyền qua mạng, không ghi log |
| **Public agreement key Q** | Điểm công khai được tính từ private key | Dùng để trao đổi; **phải xác thực đúng đối tác** |
| **ECDH shared secret Z** | Kết quả trung gian hai bên tính được | Không coi là khóa ứng dụng đã hoàn chỉnh |
| **KDF/HKDF** | Dẫn xuất một hoặc nhiều khóa từ Z và ngữ cảnh | Tách khóa theo hướng truyền, mục đích, phiên |
| **Key confirmation** | Bằng chứng một bên tính được đúng khóa phiên theo giao thức | Không đồng nhất với xác thực danh tính nếu giao thức thiếu ràng buộc |
| **Ephemeral key pair** | Cặp khóa thỏa thuận sinh cho phiên/handshake rồi hủy | Hỗ trợ forward secrecy trong giao thức thích hợp |
| **Static key pair** | Cặp khóa thỏa thuận dùng trong nhiều phiên | Phạm vi ảnh hưởng có thể lớn khi private key bị lộ |
| **Authenticated key exchange (AKE)** | Giao thức vừa thiết lập khóa vừa xác thực các bên/phiên | TLS 1.3 là ví dụ giao thức chuẩn có cấu trúc đầy đủ |
| **Cryptoperiod** | Khoảng thời gian key được phép dùng theo chính sách | Khác nhau rõ rệt giữa static và ephemeral keys |

**Public key không phải bí mật**, nhưng việc nó là public **không có nghĩa bất cứ public key nào nhận qua mạng cũng đáng tin**. Chính **ràng buộc giữa public key, danh tính và phiên** quyết định bạn đang thiết lập khóa với đúng bên hay với một kẻ chen giữa.

### So sánh với thuật ngữ quản lý khóa khác

- **ECDH private/public key** là cặp khóa dùng cho **thỏa thuận**.
- **Shared secret Z** là đầu ra trung gian từ phép thỏa thuận.
- **Session/traffic key** thường là khóa đối xứng được **dẫn xuất** từ Z qua lịch dẫn xuất khóa của giao thức.
- **DEK** là khóa dữ liệu, ví dụ AES-GCM để mã hóa bản ghi.
- **KEK** là khóa bảo vệ các khóa khác qua cơ chế **wrap/unwrap**.
- **Signing key** dùng cho chữ ký số; nó có thể được dùng để **xác thực** quá trình bắt tay ECDH nhưng không vì thế trở thành agreement key.

## 3. Nguyên lý toán học: vì sao hai bên có cùng bí mật?

ECDH dựa trên phép nhân vô hướng của điểm đường cong elliptic (*elliptic-curve scalar multiplication*). Với một nhóm elliptic-curve được chuẩn hóa và có điểm sinh công khai **G**, mỗi bên chọn một số bí mật hợp lệ:

- Bên **Alice** chọn private scalar **d_A**, tính public key **Q_A = d_A · G**.
- Bên **Bob** chọn private scalar **d_B**, tính public key **Q_B = d_B · G**.
- Alice nhận Q_B và tính **S_A = d_A · Q_B**.
- Bob nhận Q_A và tính **S_B = d_B · Q_A**.

Vì tính kết hợp của phép nhân vô hướng, hai kết quả bằng nhau:

~~~text
Q_A = d_A · G
Q_B = d_B · G

S_A = d_A · Q_B
    = d_A · (d_B · G)
    = (d_A · d_B) · G

S_B = d_B · Q_A
    = d_B · (d_A · G)
    = (d_B · d_A) · G

=> S_A = S_B
~~~

**S_A/S_B** là cùng một điểm trên nhóm đường cong khi các tham số và public key hợp lệ. Các giao thức ECDH dùng quy tắc lấy/biểu diễn vật liệu từ kết quả đó (chẳng hạn tọa độ x theo cơ chế được chuẩn hóa) để tạo **Z**, rồi đưa Z vào KDF.

Người nghe lén có thể biết **G, Q_A, Q_B**. Để tính shared secret chỉ từ các public key này trong mô hình mật mã cổ điển, kẻ tấn công phải giải bài toán khó tương ứng với nhóm và tham số được chọn, hoặc tìm được lỗi triển khai, khóa bị lộ hay lỗ hổng giao thức.

### Không nhầm “không gửi Z” với “được xác thực”

Nếu Alice nhận public key của kẻ tấn công thay cho Q_B, Alice vẫn tính ra một shared secret. Nhưng đó là bí mật với **kẻ tấn công**, không phải Bob. ECDH chỉ cung cấp một **phép thỏa thuận mật mã**; tính xác thực phải được cung cấp bởi giao thức xung quanh.

### Vì sao không tự triển khai phép toán đường cong?

Mật mã EC có nhiều yêu cầu ngoài công thức cơ bản: chọn nhóm an toàn, giới hạn private scalar, kiểm tra public key thuộc đường cong/nhóm phù hợp, xử lý điểm vô cực và các điểm bất thường, tính toán tránh rò rỉ qua timing/side channel, kiểm soát lỗi và cách mã hóa byte. Không dùng code toán học minh họa để tạo khóa production. Hãy dùng **JCA/JCE**, thư viện mật mã được thẩm định hoặc API HSM/KMS hỗ trợ thuật toán.

## 4. ECDH, ECDHE, X25519 và ECDSA khác nhau như thế nào?

| Tên | Bản chất | Mục đích | Lưu ý |
| --- | --- | --- | --- |
| **ECDH** | Họ cơ chế Diffie–Hellman trên đường cong elliptic | Tính shared secret | Có thể dùng key tĩnh hoặc tạm tùy giao thức |
| **ECDHE** | ECDH dùng **ephemeral** key pair | Thiết lập secret tạm, hỗ trợ forward secrecy | Vẫn cần xác thực đối tác |
| **ECDH P-256/P-384** | ECDH trên các curve được chuẩn hóa thuộc họ Weierstrass | Thỏa thuận khóa | Thường dùng trong JCA với `EC` và `ECDH` |
| **X25519** | Hàm thỏa thuận khóa dựa trên Curve25519, có quy tắc scalar/point riêng | Thỏa thuận khóa | Dùng API `X25519` phù hợp, không hoán đổi bừa với ECDH P-256 |
| **ECDSA** | Thuật toán chữ ký số trên đường cong elliptic | **Ký và xác minh chữ ký** | Không phải phép key agreement |
| **Ed25519** | Thuật toán chữ ký EdDSA | **Ký và xác minh chữ ký** | Không phải X25519 dù liên quan họ đường cong |
| **RSA-OAEP** | Thuật toán mã hóa khóa công khai | Có thể dùng trong **key transport** | Khác mô hình hai bên cùng tính secret bằng DH |

**ECDHE** là cách gọi nổi bật trong nhiều giao thức: chữ “E” cuối nhấn mạnh private agreement key **tạm thời**. Việc dùng ephemeral keys thích hợp và hủy bí mật sau phiên là một thành phần giúp đạt **forward secrecy**, nhưng không tự động tạo ra tính năng này nếu giao thức, xác thực hoặc lưu trữ khóa sai.

### Có nên dùng cùng cặp khóa EC để ký ECDSA và chạy ECDH?

Thông thường **không nên**. Một cặp khóa có thể thuộc loại cấu trúc EC tương tự nhưng **key usage, miền tin cậy và mục tiêu bảo mật khác nhau**. Tách khóa ký và khóa thỏa thuận giúp giới hạn phạm vi ảnh hưởng, tránh lỗi cross-protocol và đơn giản hóa kiểm toán. Chứng thư/kho khóa phải quy định đúng mục đích; thư viện/API phải cho phép thuật toán tương ứng.

### X25519 có phải là ECDH không?

X25519 thuộc họ **elliptic-curve Diffie–Hellman key agreement** về mặt mục đích và nguyên lý, nhưng định nghĩa cụ thể của **phép toán X25519** khác API ECDH P-256. Không được đổi tên curve hoặc chuyển private key của thuật toán này sang thuật toán kia tùy tiện. Với X25519, giao thức và thư viện còn phải xử lý đúng các kết quả bất thường, bao gồm **all-zero shared secret** khi đặc tả yêu cầu.

## 5. Luồng trao đổi khóa ECDH từ góc nhìn giao thức

~~~mermaid
sequenceDiagram
    participant A as Alice / Client
    participant B as Bob / Server
    A->>A: Sinh cặp ephemeral d_A, Q_A
    B->>B: Sinh cặp ephemeral d_B, Q_B
    A->>B: Gửi Q_A và tham số đề xuất
    B->>A: Gửi Q_B và bằng chứng xác thực
    Note over A,B: Kiểm tra danh tính, thuật toán, phiên và transcript
    A->>A: Z_A = ECDH(d_A, Q_B)
    B->>B: Z_B = ECDH(d_B, Q_A)
    Note over A,B: Z_A = Z_B nếu dùng đúng cặp khóa
    A->>A: KDF(Z_A, transcript, context) -> keys
    B->>B: KDF(Z_B, transcript, context) -> keys
    A->>B: Finished/key confirmation theo giao thức
    B->>A: Finished/key confirmation theo giao thức
    Note over A,B: Bảo vệ dữ liệu bằng AEAD; xóa khóa tạm khi hết cần
~~~

Đây là **sơ đồ khái niệm**, không phải các thông điệp wire-format chính xác của TLS 1.3. Thứ tự xác thực, KDF và thông điệp xác nhận khóa phụ thuộc giao thức cụ thể.

### Các bước cần có trong thiết kế thực tế

1. **Thống nhất thuật toán và nhóm:** Không để đối thủ can thiệp để hạ cấp curve, phiên bản hoặc suite mật mã mà hai bên không phát hiện.
2. **Sinh cặp khóa ECDH:** Dùng CSPRNG/DRBG đủ entropy và provider mật mã tin cậy.
3. **Trao đổi public key:** Gửi trong định dạng giao thức được kiểm soát, kiểm tra group/curve đúng kỳ vọng.
4. **Xác thực public key và transcript:** Xác minh danh tính bên kia qua chứng thư + chữ ký, PSK hoặc cơ chế AKE chuẩn. Không tin public key chỉ vì nhận được qua TLS chưa được xác thực/qua socket thông thường.
5. **Tính shared secret Z:** Mỗi bên dùng private key của mình và public key hợp lệ của peer.
6. **Dẫn xuất khóa:** Dùng KDF với ngữ cảnh phù hợp; tách khóa theo hướng truyền, mục đích và phiên.
7. **Xác nhận và bảo vệ lưu lượng:** Dùng thông điệp kết thúc bắt tay có kiểm tra toàn vẹn; mã hóa ứng dụng bằng AEAD với nonce/counter đúng.
8. **Kết thúc vòng đời:** Xóa private key tạm, Z và khóa phiên theo chính sách; không ghi chúng vào log.

**Không tự lắp ghép** các thành phần ECDH + AES thành một giao thức production nếu có thể sử dụng TLS 1.3, Noise hoặc một giao thức chuẩn phù hợp đã được phân tích bảo mật.

## 6. Vì sao ECDH đơn thuần bị tấn công man-in-the-middle?

Giả sử Alice muốn tạo khóa với Bob nhưng không kiểm tra public key được nhận. Kẻ tấn công Mallory thay khóa công khai hai chiều:

~~~text
Alice                                   Mallory                                  Bob
private d_A                             private d_M1, d_M2                        private d_B

Q_A ------------------------------->   Q_A
                                        Q_M1 ------------------------------->    Bob

Alice <-----------------------------   Q_M2
                                        <------------------------------- Q_B      Bob

Alice tính Z_AM = ECDH(d_A, Q_M2)
Bob   tính Z_MB = ECDH(d_B, Q_M1)
Mallory tính được cả Z_AM và Z_MB bằng private keys của mình.
~~~

Alice và Bob đều có thể cảm nhận rằng một phiên “đã thiết lập khóa thành công”. Tuy nhiên, thực tế là **hai phiên riêng** giữa Alice–Mallory và Mallory–Bob. Mallory có thể giải mã và tái mã hóa lưu lượng giữa hai phía nếu không có xác thực bổ sung.

**Mitigation quan trọng nhất** là dùng **authenticated key exchange**:

- Xác minh chứng thư máy chủ với trust anchor được chấp nhận, hostname/identity phù hợp và thuật toán/chính sách đúng.
- Kiểm tra chữ ký của peer trên thông điệp bắt tay hoặc transcript mà giao thức quy định.
- Dùng PSK đã phân phối an toàn hoặc một cơ chế xác thực chuẩn nếu không dùng PKI.
- Ràng buộc **danh tính, public keys, thuật toán điều đình, roles và transcript** vào quá trình xác thực/dẫn xuất khóa theo đặc tả.
- Thực hiện **key confirmation** để phát hiện phiên không cùng khóa, kết hợp bảo vệ bắt tay trước các chỉnh sửa/tráo ngữ cảnh.

**KDF hoặc AES-GCM không tự khắc phục MITM.** Mallory cũng có thể dùng cùng KDF và AES-GCM để kết thúc hai phiên mã hóa khác nhau. Nguyên nhân nằm ở chỗ **khóa công khai không được xác thực**, không phải do AES hoặc phép ECDH không hoạt động.

## 7. Từ shared secret Z tới traffic keys: vai trò của KDF

### 7.1. Không dùng raw ECDH secret trực tiếp khi chưa qua quy trình dẫn xuất

Raw ECDH secret là **vật liệu trung gian** có biểu diễn và phân bố phụ thuộc cơ chế thỏa thuận. Nó chưa thể hiện đầy đủ ý nghĩa của khóa cần dùng: bên nào gửi, bên nào nhận, dùng AES-GCM hay HMAC, phiên nào và phiên bản giao thức nào.

Một **KDF chuẩn** giúp:

- Trích xuất vật liệu khóa từ Z theo mô hình áp dụng.
- Sinh khóa có độ dài được yêu cầu, ví dụ **32 byte** cho AES-256.
- Phân tách khóa dùng cho **client → server** và **server → client**.
- Phân tách khóa theo **mục đích**: encryption, authentication, exporter, resumption, wrapping nếu giao thức định nghĩa.
- Ràng buộc kết quả với transcript/bối cảnh như danh tính đã xác thực, phiên bản, curve, thuật toán và vai trò.

### 7.2. HKDF theo cách hiểu khái niệm

Một KDF được sử dụng rộng rãi là **HKDF (HMAC-based Key Derivation Function)**, với hai giai đoạn:

~~~text
PRK = HKDF-Extract(salt, Z)

clientWriteKey = HKDF-Expand(
    PRK,
    info = encode(protocolId, sessionContext, "client-to-server", "AES-256-GCM"),
    L = 32
)

serverWriteKey = HKDF-Expand(
    PRK,
    info = encode(protocolId, sessionContext, "server-to-client", "AES-256-GCM"),
    L = 32
)
~~~

Với HKDF-SHA-256, **Extract** dùng HMAC-SHA-256 tạo PRK; **Expand** sinh key material có độ dài yêu cầu (tối đa theo giới hạn của thuật toán). `salt` và `info` thường **không phải bí mật**, nhưng phải được xác định nhất quán giữa các bên và gắn với **giao thức đã được thiết kế đúng**.

Dùng `encode(...)` phải có **cách mã hóa các trường không mơ hồ**. Không nối các chuỗi có độ dài biến đổi mà không delimiter/length-prefix vì hai bộ trường khác nhau có thể tạo cùng chuỗi byte. Nếu giao thức cho phép đàm phán thuật toán, transcript phải bảo vệ tính toàn vẹn và chống downgrade.

### 7.3. KDF khác password hashing

**HKDF** thích hợp dẫn xuất từ vật liệu bí mật như kết quả ECDH có bảo đảm bảo mật phù hợp. Nó **không phải phương pháp làm chậm đoán mật khẩu** từ một password ít entropy. Với password do người dùng đặt, nên dùng **Argon2id, scrypt hoặc PBKDF2** theo chính sách để bảo vệ verifier hoặc dẫn xuất password-based KEK, với salt và cấu hình chi phí phù hợp.

Không dùng `SHA256(Z)` tùy tiện thay cho toàn bộ lịch dẫn xuất khóa nếu giao thức có yêu cầu HKDF/định danh ngữ cảnh rõ ràng; không tự sáng tạo KDF cho production.

## 8. Ví dụ Java 11+: ECDH P-256 và HKDF-SHA-256

Mã dưới đây minh họa **hai bên tạo cặp khóa ECDH P-256 tạm thời, tính ra cùng shared secret, dẫn xuất một khóa AES-256 qua HKDF-SHA-256**, rồi dùng khóa đó để mã hóa/giải mã một thông điệp AES-GCM.

Để giảm sự phức tạp, cả hai bên được mô phỏng **trong cùng một JVM**. Đây **không phải một giao thức truyền thông an toàn**: chương trình **không thực hiện xác thực public key**, không có PKI hay signed transcript, chống replay, điều đình thuật toán hoặc bảo đảm forward secrecy hoàn chỉnh của một giao thức mạng.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class EcdhP256Demo {
    private static final SecureRandom RNG = new SecureRandom();

    static KeyPair generateEphemeralEcKeyPair()
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"), RNG);
        return generator.generateKeyPair();
    }

    static byte[] agree(PrivateKey privateKey, PublicKey peerPublic)
            throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("ECDH");
        agreement.init(privateKey);
        agreement.doPhase(peerPublic, true);
        return agreement.generateSecret();
    }

    static byte[] sha256(byte[]... inputs)
            throws GeneralSecurityException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        for (byte[] input : inputs) {
            digest.update(input);
        }
        return digest.digest();
    }

    // Bản minh họa HKDF-SHA-256 sinh đúng một block 32 byte:
    // PRK = HMAC(salt, Z), OKM = HMAC(PRK, info || 0x01).
    static byte[] hkdf32(byte[] z, byte[] salt, byte[] info)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance("HmacSHA256");
        hmac.init(new SecretKeySpec(salt, "HmacSHA256"));
        byte[] prk = hmac.doFinal(z);
        try {
            hmac.init(new SecretKeySpec(prk, "HmacSHA256"));
            hmac.update(info);
            hmac.update((byte) 1);
            return hmac.doFinal(); // 32 byte SHA-256 output
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPair alice = generateEphemeralEcKeyPair();
        KeyPair bob = generateEphemeralEcKeyPair();

        // Thực tế: public keys phải được giải mã/kiểm tra
        // và XÁC THỰC qua một giao thức đúng.
        byte[] za = agree(alice.getPrivate(), bob.getPublic());
        byte[] zb = agree(bob.getPrivate(), alice.getPublic());

        System.out.println("Same ECDH secret: "
                + MessageDigest.isEqual(za, zb));

        byte[] protocol = "ecdh-p256-demo/v1"
                .getBytes(StandardCharsets.UTF_8);
        // Salt công khai minh họa có thứ tự cố định (Alice rồi Bob).
        byte[] salt = sha256(
                protocol,
                alice.getPublic().getEncoded(),
                bob.getPublic().getEncoded());

        byte[] info = "AES-256-GCM|Alice-to-Bob"
                .getBytes(StandardCharsets.UTF_8);

        byte[] ka = hkdf32(za, salt, info);
        byte[] kb = hkdf32(zb, salt, info);
        System.out.println("Same derived AES key: "
                + MessageDigest.isEqual(ka, kb));

        // Chỉ một chiều truyền; hệ thống thực dẫn xuất
        // khóa khác cho chiều Bob-to-Alice.
        byte[] iv = new byte[12]; // 96-bit GCM nonce
        RNG.nextBytes(iv);
        byte[] aad = "session-demo|msg-1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Xin chao qua ECDH!"
                .getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(
                Cipher.ENCRYPT_MODE,
                new SecretKeySpec(ka, "AES"),
                new GCMParameterSpec(128, iv));
        encrypt.updateAAD(aad);
        byte[] ciphertextAndTag = encrypt.doFinal(plaintext);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(
                Cipher.DECRYPT_MODE,
                new SecretKeySpec(kb, "AES"),
                new GCMParameterSpec(128, iv));
        decrypt.updateAAD(aad);
        byte[] restored = decrypt.doFinal(ciphertextAndTag);

        System.out.println("Restored plaintext: "
                + new String(restored, StandardCharsets.UTF_8));

        // Xóa các bản sao byte[] do ứng dụng quản lý: best effort.
        Arrays.fill(za, (byte) 0);
        Arrays.fill(zb, (byte) 0);
        Arrays.fill(ka, (byte) 0);
        Arrays.fill(kb, (byte) 0);
    }
}
~~~

### Kết quả dự kiến

~~~text
Same ECDH secret: true
Same derived AES key: true
Restored plaintext: Xin chao qua ECDH!
~~~

### Vì sao từng bước cần thiết?

1. **`ECGenParameterSpec("secp256r1")`:** chọn curve P-256 được hỗ trợ trong nhiều môi trường JCA. Không dùng nhóm EC tự đặt.
2. **`KeyAgreement("ECDH")`:** tính Z bằng private key của mình và public key bên kia. Trong hệ thống thực, **provider phải bảo đảm kiểm tra hợp lệ public key/curve**, còn giao thức phải **xác thực danh tính bên kia**.
3. **`salt`:** ví dụ lấy hash của nhãn giao thức và **hai public key theo thứ tự cố định**. Điều này tạo ngữ cảnh chung cho demo, **không thay thế authenticated handshake transcript** hay certificate validation.
4. **`info`:** tách mục đích và hướng truyền. Trong production, phải lấy context từ **giao thức chuẩn** và xác thực transcript, không tự tạo định dạng chỉ dựa trên vài chuỗi.
5. **`hkdf32`:** cách cài minh họa HKDF-Extract + một block Expand 32 byte; khi ứng dụng cần nhiều output hoặc thuật toán khác, dùng thư viện KDF chuẩn và kiểm tra giới hạn chiều dài.
6. **AES-GCM:** được dùng **sau** ECDH/HKDF để mã hóa dữ liệu. IV 12 byte được tạo mới; với **cùng key** tuyệt đối không thực hiện thêm một lần Encrypt độc lập bằng IV đó. Nếu có nhiều thông điệp, cần kế hoạch nonce và giới hạn số bản mã mỗi key.
7. **AAD và tag:** đảm bảo ngữ cảnh thông điệp được xác thực. Giải mã với AAD sai hoặc ciphertext/tag bị sửa phải thất bại; không bỏ qua `AEADBadTagException`.
8. **Xóa bộ nhớ:** `Arrays.fill` chỉ là biện pháp *best effort*. `SecretKeySpec`, provider và JVM có thể giữ bản sao vật liệu bí mật không thể xóa tuyệt đối từ đoạn mã này.

**Không áp dụng đoạn mã này trực tiếp cho giao tiếp mạng production.** Mã thiếu phần chống MITM, cấp và xác minh chứng thư, key confirmation/anti-replay, quản lý phiên và kiểm tra thông điệp. Trong ứng dụng Java thực tế, ưu tiên **TLS 1.3** đã được triển khai và duy trì.

## 9. Public key validation và những lỗi triển khai khó thấy

### 9.1. Key agreement key phải đúng curve/nhóm

Mỗi phép ECDH có các tham số nhóm cụ thể. Public key gửi tới một phiên ECDH P-256 phải phù hợp P-256 và có biểu diễn hợp lệ theo giao thức. Không thể cho peer tùy ý thay curve hoặc gửi điểm thuộc curve khác mà vẫn tin rằng JCA sẽ luôn tự phát hiện mọi lỗi trong mọi provider.

Một hệ thống cần đánh giá các nguy cơ:

- **Invalid-curve attack:** Public key không hợp lệ có thể ảnh hưởng tính an toàn nếu thư viện không kiểm tra đúng.
- **Small-subgroup/low-order issues:** Các giá trị public key nằm trong nhóm nhỏ hoặc điểm đặc biệt có thể dẫn đến shared secret có cấu trúc dễ đoán ở những cơ chế không xử lý đúng.
- **Point at infinity:** Không được chấp nhận như public key thỏa thuận hợp lệ trong các ngữ cảnh không cho phép.
- **Curve mismatch:** Cặp khóa hai bên không ở cùng miền tham số được thỏa thuận.
- **Malformed serialization:** Dữ liệu public key ASN.1/X.509 hoặc encoding khác bị lỗi, cắt ngắn hay gắn thuật toán OID sai.
- **Side-channel:** Thời gian phản hồi, lỗi và truy cập bộ nhớ có thể tiết lộ thông tin nếu phép toán không được triển khai an toàn.

**Không tự viết hàm kiểm tra điểm toán học nếu thư viện chuẩn đã cung cấp đúng cơ chế**. Phải kiểm tra khả năng validation của **provider/phiên bản** và đặc tả giao thức; không đồng nhất **parse được public key** với **đã xác thực danh tính peer**.

### 9.2. X25519 có một nhóm yêu cầu riêng

X25519 định nghĩa thao tác Montgomery-ladder và xử lý scalar/point theo đặc tả riêng. Nhiều thư viện hỗ trợ X25519 để đơn giản hóa những nguy cơ thao tác EC thường gặp, nhưng **không miễn cho ứng dụng khỏi mọi kiểm tra**. Đặc biệt, cần xử lý đúng **kết quả shared secret toàn byte 0** theo yêu cầu thuật toán/giao thức, để tránh sử dụng một secret dễ đoán làm đầu vào KDF.

Không mặc định P-256 ECDH và X25519 có cùng API, định dạng khóa hoặc cách mã hóa shared secret. Phải dùng thuật toán, tham số, kiểm tra lỗi và KDF đúng với **suite đã đàm phán**.

### 9.3. Đồng nhất encoding và mục đích

Nếu hai bên tạo KDF `info` bằng chuỗi ghép mơ hồ, họ có thể không cùng hiểu vai trò/danh tính, hoặc tạo ra khóa bị dùng nhầm mục đích. Dùng **canonical encoding** và phân tách miền sử dụng (*domain separation*). Với certificate-based authentication, danh tính trong chứng thư cần được kiểm tra với **định danh đích mong đợi**, không chỉ kiểm tra một chữ ký khớp public key bất kỳ.

## 10. Forward secrecy: lợi ích và các điều kiện bắt buộc

**Forward secrecy** là thuộc tính bảo vệ các phiên đã hoàn tất trước việc **lộ khóa xác thực dài hạn về sau**, trong những điều kiện giao thức và vận hành phù hợp. ECDHE thường là thành phần quan trọng để có thuộc tính này.

| Thiết kế | Đặc điểm | Khả năng forward secrecy |
| --- | --- | --- |
| **Static ECDH cả hai bên** | Cặp agreement key dài hạn được tái sử dụng | Không tự có forward secrecy; lộ private key dài hạn có thể ảnh hưởng nhiều phiên |
| **Ephemeral ECDH (ECDHE)** | Cặp agreement key tạm theo phiên/handshake | Có thể hỗ trợ forward secrecy nếu xác thực đúng và bí mật tạm được hủy |
| **ECDHE + ký xác thực transcript** | Khóa ký dài hạn dùng để xác thực public ECDHE tạm | Trong giao thức chuẩn, lộ khóa ký **về sau** không tự động làm lộ Z của phiên cũ |
| **ECDHE nhưng log private scalar/Z** | Giá trị tạm bị lưu lâu dài | Làm suy yếu hoặc mất lợi ích forward secrecy đối với phiên liên quan |
| **Static key bị lộ trước/lúc bắt tay** | Đối thủ có thể mạo danh bên bị lộ | Forward secrecy không bảo vệ các phiên bị MITM hoặc compromise trong lúc diễn ra |

### Lộ khóa nào thì tác động ra sao?

- **Lộ signing key dài hạn sau phiên:** Với giao thức ECDHE đã xác thực đúng và bí mật phiên thực sự bị xóa, không mặc nhiên giải mã được lưu lượng ECDHE cũ chỉ từ signing key.
- **Lộ private ECDHE tạm của một phiên:** Có thể ảnh hưởng shared secret và khóa phiên **của phiên đó**, đặc biệt nếu kẻ tấn công thu thập được public key/ciphertext liên quan.
- **Lộ session/traffic key:** Bản thân phiên hoặc dữ liệu dùng khóa đó có thể bị lộ; forward secrecy không “khôi phục” được.
- **Lộ static agreement key:** Tùy giao thức, có thể gây ảnh hưởng phiên đã ghi lại, bên tham gia hoặc các bản ghi sử dụng khóa; cần phân tích cụ thể.

**Xóa ephemeral key** không chỉ là gọi GC trong Java. Hạn chế ghi vào log, heap dump, bản sao lưu, snapshot container, telemetry và các dữ liệu gỡ lỗi. Thư viện/OS/HSM có những cơ chế và giới hạn khác nhau; cần đánh giá nơi private scalar và Z được xử lý trong thực tế.

## 11. ECDH trong TLS 1.3 và ứng dụng Java

Trong các kết nối HTTPS hiện đại, **TLS 1.3** có thể sử dụng nhóm ECDHE như P-256 hoặc X25519 trong phần thiết lập bí mật. Hệ thống TLS bổ sung các thành phần mà ECDH nguyên thủy không có:

- Đàm phán phiên bản, thuật toán, nhóm thỏa thuận khóa và key share theo các quy tắc chống hạ cấp.
- **Xác thực đối tác** bằng chứng thư/chữ ký hoặc PSK theo chế độ bắt tay.
- **Transcript hash và HKDF key schedule** ràng buộc bí mật vào chuỗi thông điệp bắt tay.
- Thông điệp **Finished** kiểm tra tính nhất quán khóa và toàn vẹn bắt tay.
- Tách **traffic secrets/keys** theo chiều truyền và giai đoạn phiên.
- Cơ chế bảo vệ bản ghi AEAD, nonce và cập nhật khóa theo giao thức.

### Lưu ý: TLS 1.3 không đồng nghĩa “mọi cấu hình đều dùng ECDHE”

TLS 1.3 có các chế độ **PSK-only** và **PSK kết hợp (EC)DHE**, bên cạnh bắt tay dựa trên chứng thư. Các bảo đảm forward secrecy và xác thực phụ thuộc **chế độ thực tế**. Không nên chỉ xem tên phiên bản TLS rồi kết luận phiên đó luôn dùng một nhóm ECDHE cụ thể hoặc có cùng mô hình xác thực.

### Ứng dụng Java nên làm gì?

Ở tầng ứng dụng, dùng **HTTPS client/server thư viện chuẩn**, cấu hình trust store và **hostname verification**, chọn chính sách TLS an toàn và quản lý certificate/private authentication key đúng cách. Với ứng dụng nội bộ có yêu cầu mạnh, cân nhắc **mTLS** với chứng thư client. Không tự đóng gói luồng ECDH thủ công vào HTTP rồi bỏ qua xác thực danh tính, nonce AEAD và bảo vệ transcript.

Ví dụ một team sử dụng `java.net.http.HttpClient` nên để TLS stack xử lý ECDH, chữ ký xác thực, HKDF và traffic key; ứng dụng vẫn chịu trách nhiệm **kiểm soát chứng thư tin cậy, bí mật cấu hình, kiểm toán và quyền ứng dụng**.

## 12. Quản lý vòng đời ECDH key: static so với ephemeral

Không phải mọi ECDH private key đều nên được lưu như khóa tài khoản dài hạn. Phân loại theo **đời sống và mục đích**:

| Giai đoạn | Ephemeral ECDH key | Static ECDH key | Kiểm soát trọng tâm |
| --- | --- | --- | --- |
| **Thiết kế** | Xác định handshake/phiên và yêu cầu xóa | Định danh thiết bị/đối tác, cryptoperiod | Owner, protocol, nhóm, bảo đảm bí mật |
| **Tạo** | Sinh cho phiên bằng CSPRNG | Sinh tại vùng bảo vệ được phê duyệt | DRBG đủ entropy, nhóm chuẩn |
| **Cấp phát** | Public key gửi theo bắt tay | Public key/chứng thư phân phối tin cậy | Xác thực đối tác và ràng buộc key usage |
| **Lưu trữ** | Chủ yếu trong bộ nhớ/handle ngắn hạn | Keystore, HSM/KMS nếu hỗ trợ | Không xuất hoặc lưu private key thừa |
| **Sử dụng** | Derive Z, sau đó KDF và xác nhận phiên | Thực hiện đúng key agreement protocol | IAM, peer-key validation, transcript |
| **Xoay vòng** | Sinh key pair tạm mới cho handshake mới | Thay cặp theo cryptoperiod/sự cố | Phân phối public key mới và chuyển đổi |
| **Thu hồi** | Kết thúc phiên/chặn dùng lại | Thu hồi chứng thư/grant, ngăn thỏa thuận mới | Điều tra phiên liên quan |
| **Hủy** | Xóa khi hết cần; không backup không có lý do | Hủy sau khi hết phụ thuộc/retention | Nhật ký hủy và xử lý replica/backup |

### Key state không hoàn toàn trùng trạng thái KMS

Các khái niệm **Pre-activation, Active, Suspended, Deactivated, Compromised, Destroyed** mô tả vòng đời quản lý khóa. Một KMS có thể sử dụng tên **Enabled, Disabled, Pending deletion** với ngữ nghĩa riêng. Không mặc định việc disable resource trong KMS đã xóa toàn bộ bản sao key material hoặc làm vô hiệu hóa những shared secret đã được dẫn xuất trước đó.

**Thu hồi chứng thư** (nếu sử dụng PKI), **vô hiệu hóa quyền ECDH**, **thay private key**, và **hủy key material** là các hoạt động khác nhau cần phối hợp.

## 13. ECDH trong KMS/HSM và envelope encryption

### 13.1. HSM/KMS có giúp bảo vệ private agreement key không?

Một số **HSM**, token PKCS#11 và dịch vụ quản lý khóa hỗ trợ sinh cặp EC và thực hiện **ECDH/DeriveKey** trong vùng bảo vệ, hạn chế private key rời mô-đun. Tuy nhiên, **không phải mọi cloud KMS đều hỗ trợ ECDH** hoặc X25519; nhiều sản phẩm chỉ cho Encrypt/Decrypt, Sign/Verify hoặc Wrap/Unwrap với các loại khóa nhất định.

Cần kiểm tra:

1. **Thuật toán/curve được hỗ trợ:** P-256, P-384, X25519 và các cơ chế derive cụ thể.
2. **Cách nhập peer public key:** định dạng, curve validation, khả năng từ chối điểm bất thường.
3. **Đầu ra phép derive:** API trả **raw shared secret**, **derived key** hay **non-exportable key handle**?
4. **Chính sách IAM:** Ai được phép `DeriveKey`, tạo cặp khóa, sửa policy, export hoặc hủy?
5. **Crypto boundary:** Private key nằm ở đâu? Shared secret và derived key có đi vào bộ nhớ ứng dụng không?
6. **Audit/DR:** Có log key ID, caller và operation mà không lộ Z? Có HA/replication và quy trình thay thế khóa không?

**Private key không xuất được** giảm rủi ro mất vật liệu khóa, nhưng **không thay thế xác thực peer**: HSM thực hiện phép toán với public key được yêu cầu; nếu ứng dụng cung cấp public key của kẻ tấn công, HSM có thể vẫn tạo shared secret với kẻ tấn công.

### 13.2. ECDH có thay thế KEK/DEK của envelope encryption không?

**Không tự động.** Envelope encryption thông dụng sử dụng **DEK đối xứng** để mã hóa dữ liệu và **KEK** trong KMS để bọc DEK. ECDH có thể được dùng ở **kênh truyền** để thiết lập khóa phiên khi hai dịch vụ giao tiếp. Trong một giao thức chuyển khóa cụ thể, ECDH + KDF cũng có thể giúp hai bên thiết lập **key-encryption key** dùng bảo vệ một DEK cần truyền, nhưng đó là **giao thức riêng có xác thực và đóng gói khóa rõ ràng**.

~~~mermaid
flowchart TD
    A[Dịch vụ A] -->|ECDH key agreement theo giao thức đã xác thực| C[Shared secret Z]
    B[Dịch vụ B] -->|ECDH key agreement theo giao thức đã xác thực| C
    C --> K[HKDF / key schedule]
    K --> T[Traffic keys đối xứng cho kênh truyền]
    T --> M[Bảo vệ lưu lượng API bằng AEAD]
    D[DEK cho dữ liệu lưu trữ] --> E[Mã hóa record bằng AES-GCM]
    F[KEK trong KMS/HSM] --> W[Wrap / Unwrap DEK]
    W --> D
~~~

Hai nhánh có **mục đích, lifecycle và IAM khác nhau**. Không coi KMS bảo vệ KEK là bằng chứng rằng private ECDH key/handshake đã an toàn, cũng không coi TLS dùng ECDH là đủ bảo vệ dữ liệu khi lưu ở database.

### 13.3. Vai trò và phân quyền

| Vai trò | Trách nhiệm | Điều không nên mặc định |
| --- | --- | --- |
| **Key owner** | Phê duyệt mục đích ECDH, loại static/ephemeral, curve, cryptoperiod và quyền peer | Không mặc nhiên có private key hoặc quyền derive |
| **Key custodian** | Tạo/cấu hình HSM/KMS/keystore, phân quyền, rotate, revoke/hủy theo chính sách | Không tự dùng `DeriveKey` trái phê duyệt |
| **Key user / ứng dụng** | Thực hiện agreement và KDF theo giao thức trên key ID được phép | Không sửa key policy, export hoặc tạo khóa tùy ý |
| **Security reviewer** | Xem xét tính xác thực, curve, forward secrecy, mô hình lộ bí mật | Không cần nhận raw shared secret |
| **Auditor** | Kiểm tra IAM, thời điểm, key version, phép toán, trạng thái và sự cố | Không cần quyền sử dụng private key |

Ghi log **key ID/version, principal, thuật toán, curve, thời điểm, loại operation, kết quả và correlation ID** theo chính sách. **Không ghi private scalar, Z, PRK/OKM hay traffic keys**. Có thể dùng dấu vết giao thức không chứa bí mật để phục vụ điều tra.

## 14. Những sai lầm phổ biến và biện pháp phòng ngừa

| Sai lầm | Hậu quả có thể xảy ra | Biện pháp |
| --- | --- | --- |
| Trao đổi public ECDH key qua mạng nhưng không xác thực | MITM tạo hai shared secret riêng | Dùng authenticated key exchange như TLS 1.3 với cấu hình xác thực đúng |
| Tin rằng cùng Z đồng nghĩa đúng danh tính | Bị tráo peer hoặc nhầm phiên | Ràng buộc identity, transcript, roles và kiểm tra chứng thư/chữ ký |
| Dùng Z trực tiếp làm session key không có KDF/context | Thiếu phân tách mục đích và kiểm soát biểu diễn | KDF chuẩn, tách key theo chiều/mục đích/phiên |
| Dùng cùng private ECDH key cho mọi phiên khi cần forward secrecy | Lộ key ảnh hưởng rộng, khó có FS | Tạo ephemeral key đúng vòng đời, xóa bí mật sau phiên |
| Sinh d_A/d_B bằng PRNG yếu hoặc seed dự đoán được | Khóa riêng và shared secret có thể đoán | CSPRNG/DRBG, API mật mã chuẩn, KMS/HSM khi hỗ trợ |
| Không kiểm tra public key/curve | Invalid-curve, low-order/subgroup, lỗi giải mã | Dùng provider được đánh giá; kiểm tra theo suite và đặc tả |
| Dùng key X25519 như EC P-256 hoặc ngược lại | Sai thuật toán/định dạng, lỗi bảo mật/tương thích | Chọn suite rõ ràng, API và encoding tương ứng |
| Không xử lý shared secret bất thường theo X25519 | Có thể dùng giá trị dễ đoán | Từ chối all-zero output theo đặc tả/giao thức |
| Dùng lại một traffic key và nonce GCM cho nhiều lần Encrypt | Keystream lặp, rủi ro xác thực/bí mật | Nonce không lặp trên cùng key, quản lý counter và giới hạn mã hóa |
| Tự ghép ECDH + AES rồi gọi là TLS | Thiếu xác thực, chống replay, downgrade và key confirmation | Dùng giao thức AKE chuẩn đã được phân tích |
| Lưu ephemeral private scalar/Z vào log hoặc backup | Phá kỳ vọng forward secrecy | Giảm lưu bí mật, xóa best effort và bảo vệ runtime |
| Dùng một cặp EC cho ECDSA và ECDH không có chính sách | Tăng tác động compromise và lỗi key usage | Tách key pairs/mục đích |
| Tin rằng KMS bất kỳ đều có API ECDH | Thiết kế không chạy được hoặc buộc xuất key | Kiểm tra tính năng KMS/HSM và phương án khi không hỗ trợ |
| Thu hồi chứng thư nhưng không cập nhật trust store bên nhận | Đối tác còn tin key cũ | Phân phối trạng thái tin cậy, xoay cặp khóa, điều tra |
| Coi key đã disable là mọi phiên cũ đều bí mật | Shared secret/traffic keys trước đó vẫn có thể tồn tại | Đánh giá phạm vi sự cố và tài liệu lịch sử |

## 15. Sự cố ECDH: phân tích và phản ứng

Giả sử một thiết bị IoT dùng **static ECDH key** để thiết lập bí mật với server. Đội bảo mật phát hiện private key này đã bị xuất ra khỏi thiết bị. Phương án ứng cứu phải xét cả **khả năng mạo danh phiên mới** và **ảnh hưởng tới các phiên đã thu thập**.

### Các bước xử lý

1. **Cô lập:** Chặn thiết bị/key ID bị nghi compromise khỏi việc tạo phiên mới, giữ log không chứa bí mật.
2. **Xác định phạm vi:** Thiết bị nào cùng dùng key pair, peer nào tin public key đó, giao thức là static–static, static–ephemeral hay ECDHE?
3. **Đánh giá phiên cũ:** Có lưu ciphertext/handshake không? Private key nào bị lộ? Có forward secrecy thực tế và đã xóa ephemeral secrets không?
4. **Thay key pair:** Sinh private/public key mới bằng nguồn ngẫu nhiên đáng tin, phân phối public key/chứng thư mới qua kênh xác thực.
5. **Cập nhật trust và quyền:** Thu hồi chứng thư/grant phù hợp, loại public key cũ khỏi trust store hoặc allowlist, sửa policy KMS/HSM.
6. **Tái thiết lập phiên:** Chặn sử dụng các shared secret cũ theo chính sách; tạo session keys mới và kiểm thử xác thực hai chiều.
7. **Rà soát dữ liệu:** Nếu phát hiện phiên/bản mã có thể giải mã, đánh giá phạm vi lộ dữ liệu và nghĩa vụ ứng phó.
8. **Hậu kiểm:** Sửa nguyên nhân rò rỉ, cải thiện key inventory, audit, cryptoperiod, quyền export, bảo vệ thiết bị và quy trình xóa khóa.

**Không chỉ đổi alias trong KMS rồi tuyên bố đã sửa sự cố.** Một private key đã bị đánh cắp vẫn nằm trong tay đối thủ. Cần thay key material thực tế, cập nhật mọi đối tác còn tin public key cũ và kiểm tra trạng thái những phiên liên quan.

### Khi chứng thư xác thực bị lộ nhưng ephemeral ECDH vẫn an toàn

Nếu private signing key dùng xác thực handshake bị lộ **sau khi một phiên ECDHE hoàn tất**, điều này có thể cho phép giả mạo các phiên mới tới khi trust được cập nhật, nhưng **không mặc nhiên** giúp giải mã các phiên ECDHE cũ nếu giao thức đảm bảo forward secrecy và ephemeral secrets đã được hủy. Phải phân biệt rõ **private authentication key** và **private agreement key**, thay vì dùng một khái niệm chung “khóa TLS bị lộ”.

## 16. Checklist triển khai ECDH trong production

1. **Mục đích:** Hệ thống dùng ECDH để thiết lập shared secret cho phiên, hay có nhu cầu key transport/wrapping khác? Kết quả Z được dẫn xuất thành loại khóa nào?
2. **Giao thức:** Có ưu tiên TLS 1.3 hoặc authenticated key exchange đã được đánh giá? Nếu không, dự án có đặc tả, phân tích bảo mật và kiểm thử độc lập?
3. **Thuật toán/curve:** Curve P-256/P-384/X25519 có được các bên và provider hỗ trợ, đúng độ dài và encoding? Có chống downgrade?
4. **Randomness:** Private scalar được sinh bằng CSPRNG/DRBG tin cậy, không dùng seed dễ đoán hoặc cặp khóa cố định trá hình?
5. **Public key:** Có validation theo nhóm và xác thực danh tính peer, không chỉ parse được bytes? Các điểm bất thường bị từ chối đúng quy tắc?
6. **MITM:** Transcript, public key, vai trò và peer identity có được xác thực/ràng buộc bởi chữ ký/chứng thư/PSK phù hợp?
7. **KDF:** Shared secret đi qua HKDF/KDF chuẩn; tách khóa theo chiều truyền, mục đích, thuật toán, phiên và ngữ cảnh?
8. **AEAD:** Traffic key dùng với nonce/IV đúng quy tắc; dữ liệu và AAD/tag được kiểm tra; có giới hạn số lần mã hóa mỗi khóa?
9. **Forward secrecy:** Nếu yêu cầu FS, ECDHE private key có được sinh theo phiên, không tái sử dụng quá mức và được hủy khi hết cần?
10. **Vòng đời:** Có owner/custodian, key ID/version, trạng thái, cryptoperiod, rotation, revocation và hủy với static agreement keys?
11. **KMS/HSM:** Sản phẩm hỗ trợ đúng thuật toán `DeriveKey` và cách bảo vệ đầu ra? Có giới hạn quyền sử dụng, export và policy độc lập?
12. **Kiểm toán:** Log key ID, thao tác, danh tính, thuật toán, trạng thái, phê duyệt mà không lộ private key/shared secret/traffic key?
13. **Sự cố:** Có runbook cho MITM, khóa bị lộ, public key sai, lỗi RNG, lỗi nonce hoặc compromise KMS/HSM và phương án thông báo đối tác?
14. **Tương thích:** Phiên bản giao thức, KDF, encoding, nhóm đường cong, handling lỗi và phương án nâng cấp có được kiểm thử giữa hai bên?
15. **Dài hạn:** Với dữ liệu cần bí mật trong nhiều năm, có kế hoạch đánh giá rủi ro **harvest-now, decrypt-later** và chuyển đổi/hybrid key establishment theo tiêu chuẩn được chấp nhận không?

### Ghi nhớ

**ECDH** dùng private/public key trên đường cong elliptic để hai bên **tính ra một shared secret mà không truyền trực tiếp bí mật đó**. Nhưng ECDH **không tự xác thực danh tính**, **không tự có forward secrecy** nếu dùng static keys, và **không thay thế KDF hay AEAD**. Thiết kế an toàn cần **xác thực peer và transcript**, chọn curve/provider chuẩn, sinh private key bằng CSPRNG, **dẫn xuất khóa theo ngữ cảnh qua HKDF**, quản lý nonce đúng cách và áp dụng vòng đời khóa phù hợp. Với hệ thống thực, **TLS 1.3 hoặc một giao thức AKE được đánh giá** thường là lựa chọn tốt hơn tự viết ECDH handshake. Khi kết hợp cùng **KMS/HSM, chữ ký số, DEK/KEK trong envelope encryption, kiểm soát truy cập, xoay vòng, thu hồi, hủy và kiểm toán**, ECDH trở thành một thành phần hữu ích trong kiến trúc quản lý khóa mật mã an toàn.
