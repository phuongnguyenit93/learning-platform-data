# DHKEM và chuẩn bị cặp khóa tương thích

Trong Java 21, API `javax.crypto.KEM` cung cấp cơ chế đóng gói khóa (Key Encapsulation Mechanism). Với DHKEM, bên gửi dùng **public key của bên nhận** để tạo một shared secret và một thông điệp encapsulation; bên nhận dùng **private key tương ứng** cùng thông điệp đó để khôi phục đúng shared secret.

Điểm quyết định khả năng tương thích là hai bên phải thống nhất cùng nhóm Diffie-Hellman và cùng biến thể DHKEM. Ví dụ, public key X25519 phải đi với private key X25519; public key EC trên `secp256r1` phải đi với private key EC trên chính `secp256r1`. Không thể ghép tùy ý các key pair chỉ vì chúng đều là khóa bất đối xứng.

## 1. DHKEM làm gì?

DHKEM là KEM dựa trên Diffie-Hellman, được định nghĩa trong RFC 9180. Nó biến một phép trao đổi Diffie-Hellman thành một cơ chế tạo shared secret và encapsulation message.

Luồng cơ bản:

~~~text
BÊN NHẬN                                      BÊN GỬI
Tạo key pair tĩnh
(privateR, publicR)
      |
      +---- công bố publicR -------------------->
                                                 |
                                      Nhận publicR đã xác thực
                                                 |
                                      Tạo ephemeral key pair
                                      (privateE, publicE)
                                                 |
                                      DH(privateE, publicR)
                                                 |
                                      KDF của DHKEM
                                                 |
                                      sharedSecret + enc
                                                 |
      <------------- enc ------------------------+
      |
Dùng privateR và enc
để tính DH(privateR, publicE)
      |
Dùng cùng KDF và context
      |
sharedSecret giống bên gửi
~~~

Trong base mode:

- Bên nhận tạo và giữ key pair lâu dài: `privateR` và `publicR`.
- Bên gửi nhận public key của bên nhận.
- Khi gọi `encapsulate()`, implementation tạo ephemeral key pair mới cho lần encapsulation đó.
- Bên gửi giữ shared secret; thông điệp encapsulation `enc` được gửi cho bên nhận.
- Bên nhận dùng private key của chính mình và `enc` để tạo lại shared secret.

Private key của bên nhận và shared secret không được gửi qua mạng. Bên gửi cũng không cần tự tạo rồi truyền một private key ephemeral; DHKEM tạo ephemeral key pair bên trong quá trình encapsulation.

DHKEM chỉ tạo shared secret và encapsulation message. Nó chưa tự mã hóa payload ứng dụng. Trong HPKE, DHKEM kết hợp với KDF và AEAD để tạo luồng mã hóa/giải mã hoàn chỉnh.

## 2. Những nhóm DHKEM được RFC 9180 định nghĩa

RFC 9180 định nghĩa các biến thể DHKEM sau:

| Nhóm DH | KDF bên trong DHKEM | KEM ID | Kích thước enc |
|---|---|---:|---:|
| X25519 | HKDF-SHA256 | 0x0020 | 32 byte |
| X448 | HKDF-SHA512 | 0x0021 | 56 byte |
| P-256 (secp256r1) | HKDF-SHA256 | 0x0010 | 65 byte |
| P-384 (secp384r1) | HKDF-SHA384 | 0x0011 | 97 byte |
| P-521 (secp521r1) | HKDF-SHA512 | 0x0012 | 133 byte |

KEM ID xác định chính xác biến thể DHKEM trong giao thức HPKE. Độ dài enc là kích thước biểu diễn public key ephemeral theo quy tắc của nhóm, không phải kích thước của một khóa công khai X.509 hoàn chỉnh.

Trong Oracle JDK 21, tài liệu provider của SunJCE ghi nhận DHKEM chấp nhận:

- Khóa EC trên các đường cong secp256r1, secp384r1 và secp521r1.
- Khóa XDH trên Curve25519 và Curve448, tương ứng với các lựa chọn Java X25519 và X448.

Khi triển khai trên JDK hoặc security provider khác, hãy kiểm tra danh sách thuật toán và key type mà provider thực tế hỗ trợ. Tên chuẩn DHKEM không có nghĩa mọi provider đều phải hỗ trợ mọi nhóm.

## 3. Tạo key pair X25519 trong Java 21

X25519 là lựa chọn gọn cho ví dụ Java 21. Bên nhận tạo key pair bằng KeyPairGenerator:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

KeyPairGenerator keyPairGenerator =
    KeyPairGenerator.getInstance("X25519");

KeyPair recipientKeyPair = keyPairGenerator.generateKeyPair();

var recipientPublicKey = recipientKeyPair.getPublic();
var recipientPrivateKey = recipientKeyPair.getPrivate();
~~~

recipientPublicKey được công bố cho bên gửi qua một kênh đã xác thực. recipientPrivateKey được giữ bí mật ở bên nhận.

Không tạo public key và private key độc lập rồi ghép chúng lại. Hãy lấy cả hai từ cùng một KeyPair hoặc nạp đúng một cặp đã được tạo và lưu trữ cùng nhau.

## 4. Tạo key pair EC tương thích

Nếu giao thức yêu cầu đường cong NIST P-256, hãy tạo khóa EC với named curve chính xác:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.spec.ECGenParameterSpec;

KeyPairGenerator keyPairGenerator =
    KeyPairGenerator.getInstance("EC");

keyPairGenerator.initialize(
    new ECGenParameterSpec("secp256r1")
);

KeyPair recipientKeyPair = keyPairGenerator.generateKeyPair();
~~~

Đối với các nhóm EC còn lại mà Oracle JDK 21 SunJCE hỗ trợ, dùng đúng tên đường cong:

~~~java
keyPairGenerator.initialize(new ECGenParameterSpec("secp384r1"));
// Nếu chọn P-521, dùng "secp521r1" thay cho "secp384r1" ở trên.
~~~

Không chỉ kiểm tra getAlgorithm() trả về EC: P-256, P-384 và P-521 đều có thể có tên thuật toán tổng quát là EC, nhưng tham số đường cong khác nhau. Hai bên phải dùng cùng named curve.

## 5. Ghép key pair với DHKEM

Bảng dưới đây gợi ý cách tạo key pair cho các nhóm được Oracle JDK 21 SunJCE hỗ trợ:

| Nhóm DHKEM | KeyPairGenerator | Tham số |
|---|---|---|
| X25519 | KeyPairGenerator.getInstance("X25519") | Không cần khởi tạo thêm |
| X448 | KeyPairGenerator.getInstance("X448") | Không cần khởi tạo thêm |
| P-256 | KeyPairGenerator.getInstance("EC") | ECGenParameterSpec("secp256r1") |
| P-384 | KeyPairGenerator.getInstance("EC") | ECGenParameterSpec("secp384r1") |
| P-521 | KeyPairGenerator.getInstance("EC") | ECGenParameterSpec("secp521r1") |

Các cặp sau không tương thích:

- Public key X25519 với private key X448.
- Public key P-256 với private key P-384.
- Public key EC với private key X25519.
- Khóa chữ ký Ed25519 với DHKEM X25519.

Đặc biệt, Ed25519 và X25519 có tên gần giống nhưng mục đích khác nhau. Ed25519 dùng cho chữ ký số; X25519 dùng cho trao đổi khóa Diffie-Hellman. Không dùng thay thế cho nhau hoặc tự chuyển đổi key nếu không có một quy trình chuyển đổi được chuẩn hóa và yêu cầu rõ ràng.

RSA cũng không phải key type cho DHKEM. DHKEM cần một key pair thuộc nhóm Diffie-Hellman mà provider hỗ trợ.

## 6. Encapsulate và decapsulate với KEM API

Java 21 có javax.crypto.KEM. Ví dụ sau dùng X25519 ở bên nhận và thực hiện một vòng encapsulation/decapsulation:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

// Bên nhận tạo key pair X25519.
KeyPairGenerator keyPairGenerator =
    KeyPairGenerator.getInstance("X25519");

KeyPair recipientKeyPair = keyPairGenerator.generateKeyPair();

// Bên gửi encapsulate bằng public key của bên nhận.
KEM senderKem = KEM.getInstance("DHKEM");

KEM.Encapsulated encapsulated = senderKem
    .newEncapsulator(recipientKeyPair.getPublic())
    .encapsulate();

SecretKey senderSecret = encapsulated.key();
byte[] enc = encapsulated.encapsulation();

// Gửi enc cho bên nhận qua giao thức ứng dụng.
// Không gửi senderSecret.

// Bên nhận decapsulate bằng private key tương ứng.
KEM receiverKem = KEM.getInstance("DHKEM");

SecretKey receiverSecret = receiverKem
    .newDecapsulator(recipientKeyPair.getPrivate())
    .decapsulate(enc);

// Chỉ để kiểm tra ví dụ: hai bên phải thu được cùng shared secret.
if (!MessageDigest.isEqual(
        senderSecret.getEncoded(),
        receiverSecret.getEncoded())) {
    throw new IllegalStateException("DHKEM shared secret không khớp");
}
~~~

Trong ví dụ:

- newEncapsulator nhận public key của bên nhận.
- encapsulate() tạo shared secret và enc.
- encapsulated.key() trả về shared secret dưới dạng SecretKey.
- encapsulated.encapsulation() trả về byte array chứa thông điệp encapsulation.
- newDecapsulator nhận private key của bên nhận.
- decapsulate(enc) khôi phục shared secret tương ứng.

Mỗi lần gọi encapsulate() tạo một shared secret và encapsulation message mới. Không tái sử dụng enc cũ như thể đó là một lần trao đổi khóa mới.

Ví dụ kiểm tra bằng getEncoded() phù hợp với key có thể export trong môi trường demo. Trong môi trường HSM hoặc provider tạo key không export được, không giả định getEncoded() luôn trả byte array; hãy dùng key object theo API mà provider hỗ trợ.

## 7. Shared secret không phải encapsulation message

Hai giá trị trả về có vai trò khác nhau:

| Giá trị | Ý nghĩa | Có gửi cho bên nhận? |
|---|---|---|
| encapsulated.key() | Shared secret do bên gửi tạo | Không |
| encapsulated.encapsulation() | Thông điệp encapsulation, mang biểu diễn public key ephemeral | Có |
| Ciphertext của ứng dụng | Dữ liệu đã được mã hóa bằng khóa đối xứng sau khi thiết lập | Có, nếu ứng dụng mã hóa payload |

Không gửi shared secret hoặc private key qua mạng. Bên nhận chỉ cần enc, private key tương ứng và thông tin suite mà giao thức đã thống nhất.

Cũng không nhầm enc với recipientPublicKey.getEncoded():

- PublicKey.getEncoded() thường trả public key theo định dạng X.509 SubjectPublicKeyInfo.
- enc là biểu diễn public key ephemeral theo quy tắc serialization của DHKEM.
- Với EC, RFC 9180 dùng biểu diễn điểm elliptic curve không nén cho encapsulation.
- Với X25519/X448, encapsulation dùng chuỗi byte public key có độ dài cố định.

Vì vậy, không tự lấy X.509 bytes của public key bên nhận rồi coi đó là enc.

## 8. KDF và AEAD: DHKEM chưa phải toàn bộ HPKE

DHKEM tạo shared secret. Theo Java 21 KEM API, shared secret trả về thường được dùng làm input keying material cho một KDF.

HPKE theo RFC 9180 kết hợp ba thành phần:

1. **KEM:** tạo shared secret và encapsulation message.
2. **KDF:** dẫn xuất key và nonce theo suite/context.
3. **AEAD:** mã hóa và xác thực payload.

Do đó, chỉ gọi KEM.getInstance("DHKEM") chưa triển khai đầy đủ HPKE. Nếu hệ thống cần tương thích RFC 9180, hai bên phải thống nhất KEM, KDF, AEAD, mode và context; hãy dùng một triển khai HPKE đã được kiểm thử thay vì tự ghép các bước mật mã thành giao thức riêng.

Java 21 cung cấp KEM API, nhưng không có API HPKE hoàn chỉnh trong javax.crypto.KEM. KEM API cũng không tự xác thực danh tính của bên gửi hoặc bảo đảm public key nhận được thực sự thuộc về đúng máy chủ.

## 9. Xác thực public key và bảo vệ private key

DHKEM base mode giả định bên gửi đã có public key đúng của bên nhận. Nếu kẻ tấn công thay public key của bên nhận bằng public key của họ, bên gửi có thể encapsulate với khóa của kẻ tấn công.

Vì vậy, public key cần được xác thực trước khi dùng, ví dụ thông qua:

- Chứng thư X.509 và quy trình kiểm tra certificate chain/hostname phù hợp.
- Một kho public key có xác thực và phân quyền.
- Public key fingerprint được ghim (pinning) theo chính sách cập nhật/rotation.
- Một kênh phân phối khóa đã được bảo vệ bằng xác thực.

Private key của bên nhận phải được bảo vệ bằng cơ chế quản lý khóa phù hợp, chẳng hạn PKCS#12 có mật khẩu mạnh, hệ thống quản lý bí mật hoặc HSM. Không ghi private key hay shared secret vào log, không nhúng private key trong source code và không gửi private key cùng public key.

Khi lưu hoặc trao đổi key qua định dạng chuẩn:

- Public key thường được mã hóa theo X.509 SubjectPublicKeyInfo.
- Private key dạng exportable thường dùng PKCS#8.
- Nếu key nằm trong HSM hoặc provider không cho export, giữ key dưới dạng handle/key object của provider.
- Lưu metadata nhận diện key, thuật toán và named curve để chọn đúng private key khi decapsulate.

## 10. Chọn đúng key pair khi có nhiều recipient key

Một hệ thống có thể có nhiều recipient key vì rotation, nhiều tenant hoặc nhiều thiết bị. Khi đó, thông điệp ứng dụng nên mang đủ metadata để bên nhận tìm đúng private key:

~~~text
protocolVersion
kemId / group
recipientKeyId
encapsulation (enc)
ciphertext
~~~

enc không tự cho biết ứng dụng muốn chọn private key nào trong kho khóa của nó. recipientKeyId giúp định tuyến tới đúng key pair; kemId hoặc thông tin suite giúp xác định đúng nhóm và biến thể.

Khi thay key:

1. Tạo key pair mới trên nhóm đã thống nhất.
2. Công bố public key mới kèm key ID và thông tin suite.
3. Bên gửi bắt đầu encapsulate cho key ID mới sau khi xác thực.
4. Bên nhận giữ private key cũ trong thời gian cần giải mã dữ liệu còn hiệu lực.
5. Hết thời hạn tương thích thì thu hồi hoặc xóa private key cũ theo chính sách lưu trữ.

Không xóa private key cũ trước khi xác định các ciphertext đang lưu hoặc các phiên đang hoạt động còn cần nó.

## 11. Lỗi tương thích thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| NoSuchAlgorithmException khi lấy DHKEM | Provider đang dùng không triển khai DHKEM | Kiểm tra JDK/provider và danh sách KEM hỗ trợ |
| InvalidKeyException khi tạo encapsulator | Public key sai loại, sai nhóm hoặc không hợp lệ | Kiểm tra key algorithm và named curve |
| Decapsulation thất bại | Dùng private key không khớp, sai enc hoặc sai suite | Kiểm tra key ID, nhóm DHKEM và dữ liệu truyền nhận |
| Hai bên không tạo cùng secret | Hai bên dùng key pair hoặc biến thể khác nhau | Kiểm tra nhóm, provider và đường truyền encapsulation |
| Không giải mã được ciphertext | Đang dùng KEM như thể nó là HPKE đầy đủ hoặc hai bên lệch KDF/AEAD/context | Thống nhất toàn bộ HPKE suite và dùng implementation HPKE tương thích |

Với KEM.getInstance("DHKEM"), provider được chọn dựa trên key và tham số đưa vào newEncapsulator/newDecapsulator. Nếu không chỉ định provider, encapsulator và decapsulator thậm chí có thể được cung cấp bởi các provider khác nhau. Có thể kiểm tra providerName() trên cả hai đối tượng khi chẩn đoán khác biệt môi trường. Ứng dụng thông thường nên dùng cơ chế chọn provider mặc định thay vì hard-code SunJCE, để không khóa ứng dụng vào một provider cụ thể.

## 12. DHKEM và yêu cầu hậu lượng tử

DHKEM dựa trên Diffie-Hellman với nhóm EC hoặc XDH. Đây là mật mã khóa công khai cổ điển, không phải KEM hậu lượng tử.

Java 21 chuẩn hóa KEM API và Oracle JDK 21 cung cấp DHKEM trong SunJCE. ML-KEM theo FIPS 203 được bổ sung thành implementation tích hợp trong JDK 24 qua JEP 496. Nếu hệ thống có yêu cầu chống tấn công lượng tử, không được xem DHKEM là giải pháp hậu lượng tử; hãy đánh giá ML-KEM hoặc thiết kế hybrid phù hợp với JDK/provider thực tế và yêu cầu interoperability.

## 13. Checklist chuẩn bị cặp khóa tương thích

- [ ] Chọn trước nhóm DHKEM mà cả hai đầu và provider đều hỗ trợ.
- [ ] Tạo key pair bằng KeyPairGenerator tương ứng: X25519/X448 hoặc EC với named curve đã thống nhất.
- [ ] Dùng public key của bên nhận cho newEncapsulator.
- [ ] Dùng private key tương ứng của bên nhận cho newDecapsulator.
- [ ] Không ghép public key và private key thuộc hai nhóm khác nhau.
- [ ] Không dùng RSA hoặc Ed25519/Ed448 làm key pair DHKEM.
- [ ] Xác thực public key trước khi gửi dữ liệu bí mật.
- [ ] Bảo vệ private key và không truyền shared secret qua mạng.
- [ ] Gửi enc cùng key ID và metadata suite cần thiết.
- [ ] Phân biệt KEM với toàn bộ HPKE; thống nhất KDF và AEAD nếu mã hóa payload.
- [ ] Kiểm tra provider/curve trên đúng JDK sẽ triển khai.
- [ ] Nếu có yêu cầu hậu lượng tử, đánh giá ML-KEM/hybrid thay vì coi DHKEM là quantum-safe.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Java SE 21 API — KEM.Encapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html)
- [Java SE 21 API — KEM.Decapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html)
- [Java SE 21 API — KEM.Encapsulated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html)
- [Oracle JDK 21 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html)
- [Java SE 21 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html)
- [RFC 9180 — Hybrid Public Key Encryption, Section 4.1 and Section 7.1](https://www.rfc-editor.org/rfc/rfc9180.html)
- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
- [JEP 496 — Quantum-Resistant Module-Lattice-Based Key Encapsulation Mechanism](https://openjdk.org/jeps/496)

