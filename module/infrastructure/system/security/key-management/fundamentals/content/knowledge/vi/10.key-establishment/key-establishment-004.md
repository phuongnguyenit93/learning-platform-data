# Diffie-Hellman — Thiết lập khóa chung qua kênh không tin cậy

## 1. Diffie-Hellman là gì?

**Diffie-Hellman (DH)** là một họ cơ chế **thỏa thuận khóa (key agreement)**: hai bên trao đổi thông tin công khai qua mạng rồi mỗi bên dùng **khóa bí mật riêng** để tính ra **cùng một bí mật chung (shared secret)**. Bên nghe lén chỉ quan sát các giá trị công khai sẽ khó khôi phục bí mật đó nếu bài toán toán học, tham số và cách triển khai đủ an toàn.

Hãy hình dung dịch vụ Java **Client A** và **Server B** muốn thiết lập một khóa mã hóa phiên, nhưng không muốn gửi khóa đối xứng dạng rõ trên mạng. A sinh một cặp khóa DH tạm thời, B cũng sinh một cặp khóa; hai bên trao đổi **public key**, rồi dùng **private key của mình + public key của bên kia** để tính shared secret. Sau đó, một **Key Derivation Function (KDF)** tạo ra khóa đối xứng dùng cho các thao tác như AES-GCM.

DH thuộc chương **Key establishment** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, liên hệ trực tiếp với mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, quyền sử dụng khóa, kiểm toán và vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**.

**Ba điểm phải nhớ ngay từ đầu:**

1. **DH không tự mã hóa dữ liệu ứng dụng.** Kết quả của DH là vật liệu bí mật để dẫn xuất các khóa phiên; sau đó ứng dụng hoặc giao thức dùng AEAD như AES-GCM để bảo vệ dữ liệu.
2. **DH thuần túy không tự xác thực đối tác.** Một kẻ tấn công ở giữa có thể thay public key và tạo hai bí mật chung riêng biệt, một với A và một với B.
3. **Không nên dùng trực tiếp raw shared secret làm khóa AES.** Hãy dùng KDF theo giao thức được thẩm định, có tách mục đích và ràng buộc ngữ cảnh.

## 2. Nguyên lý toán học của Diffie-Hellman cổ điển

Trong dạng **Finite-Field Diffie-Hellman (FFDH)**, hai bên thống nhất tham số công khai gồm một số nguyên tố lớn **p** và phần tử sinh **g** thuộc nhóm thích hợp. Hai bên chọn bí mật ngẫu nhiên:

- A chọn **a** làm private exponent, tính public value **A = g^a mod p**.
- B chọn **b** làm private exponent, tính public value **B = g^b mod p**.
- A nhận B và tính **K_A = B^a mod p**.
- B nhận A và tính **K_B = A^b mod p**.

Vì:

\[
K_A = (g^b)^a \bmod p = g^{ab} \bmod p
\]

\[
K_B = (g^a)^b \bmod p = g^{ab} \bmod p
\]

nên **K_A = K_B**, mặc dù a và b không được truyền qua mạng. Tính bảo mật dựa trên độ khó của những bài toán toán học liên quan trong nhóm được chọn, cùng cách sinh exponent và xác minh public value.

### 2.1. Ví dụ số nhỏ để hiểu phép tính

**Ví dụ chỉ để minh họa, tuyệt đối không dùng trong hệ thống thật:**

| Thành phần | Bên A | Bên B |
| --- | --- | --- |
| Tham số chung | p = 23, g = 5 | p = 23, g = 5 |
| Bí mật | a = 6 | b = 15 |
| Giá trị công khai | A = 5⁶ mod 23 = **8** | B = 5¹⁵ mod 23 = **19** |
| Nhận từ đối tác | B = 19 | A = 8 |
| Bí mật chung | 19⁶ mod 23 = **2** | 8¹⁵ mod 23 = **2** |

Khi **p = 23**, kẻ tấn công có thể dễ dàng thử các giá trị và suy ra bí mật. Trong sản phẩm thực tế, không tự chọn p/g nhỏ hay tự tạo nhóm; phải dùng **nhóm mạnh, thông số được phê duyệt và thư viện đã được kiểm chứng**, kèm kiểm tra public value phù hợp.

### 2.2. Sơ đồ luồng trao đổi

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant N as Kênh mạng không tin cậy
    participant B as Server B
    Note over A: Sinh private a và public A
    Note over B: Sinh private b và public B
    A->>N: Gửi public A
    N->>B: Chuyển public A
    B->>N: Gửi public B
    N->>A: Chuyển public B
    Note over A: shared = DH(a, B)
    Note over B: shared = DH(b, A)
    Note over A,B: HKDF + transcript + nhãn mục đích để tạo khóa phiên
~~~

Sơ đồ mới chỉ là **key agreement**. Kênh chưa xác thực danh tính, vì vậy chưa đủ để chống tấn công thay public key.

## 3. Các biến thể: FFDH, ECDH và X25519

| Cơ chế | Dùng cấu trúc toán học nào? | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **FFDH / DHE** | Nhóm nhân modulo số nguyên tố lớn | Nhóm FFDHE được chuẩn hóa | Kiểm tra nhóm, public value và độ mạnh bảo mật; tránh tham số yếu |
| **ECDH / ECDHE** | Điểm trên đường cong elliptic | P-256, P-384 | Phải dùng đúng đường cong, kiểm tra khóa công khai theo yêu cầu và tránh trộn nhóm |
| **X25519** | Phép trao đổi khóa dựa trên Curve25519 theo đặc tả X25519 | Khóa công khai/đầu vào public 32 byte | Được hỗ trợ rộng; cần từ chối shared secret toàn số 0 và xác thực danh tính đối tác qua giao thức |
| **X448** | Phép trao đổi khóa theo X448 | Giá trị public 56 byte | Độ mạnh/chi phí khác X25519; kiểm tra tính tương thích |

**ECDH** nói về phép thỏa thuận khóa trên đường cong elliptic, trong khi **ECDHE** nhấn mạnh việc dùng **khóa tạm thời (ephemeral)**. Tương tự, **DHE** nói về FFDH với ephemeral key. Khi viết “DH” mà không mô tả loại khóa, người đọc chưa biết liệu hệ thống có forward secrecy hay không.

X25519 có độ mạnh bảo mật **cổ điển khoảng 128 bit**, dù tham số và public key thường được biểu diễn bằng 32 byte. Không so trực tiếp số byte của X25519 với độ dài khóa AES-256, RSA-3072 hoặc kích thước chữ ký số.

### 3.1. DH khác RSA public key encryption như thế nào?

Với RSA-OAEP trong một thiết kế mã hóa lai, bên gửi có thể **mã hóa DEK bằng public key RSA của người nhận**, rồi người nhận giải mã bằng private key. Với DH, **hai bên cùng đóng góp bí mật** để tạo shared secret; không có thao tác “A mã hóa shared secret rồi gửi nguyên nó cho B”.

| Tiêu chí | DH/ECDH key agreement | RSA-OAEP bảo vệ DEK |
| --- | --- | --- |
| Đầu ra chính | Shared secret giữa hai bên, sau đó qua KDF | Khôi phục DEK/bí mật đã được bên gửi mã hóa |
| Ai đóng góp bí mật? | Mỗi bên có private input (tùy giao thức) | Bên gửi tạo bí mật, bên nhận có private RSA để giải mã |
| Xác thực đối tác | Phải bổ sung bằng giao thức/chứng chỉ/chữ ký/PSK thích hợp | Cũng cần xác thực public RSA key của người nhận |
| Forward secrecy | Có thể đạt khi dùng ephemeral DH và thiết kế xác thực đúng | Mã hóa cho private RSA dài hạn không tự cung cấp forward secrecy |

Một cơ chế **KEM (Key Encapsulation Mechanism)** cũng có thể thiết lập bí mật chung cho mã hóa lai. Không coi mọi KEM là DH; ví dụ **ML-KEM** là một cơ chế hậu lượng tử với giả định toán học khác. Cần dựa trên giao thức và tiêu chuẩn thích hợp, không tự thay nguyên hàm DH bằng một API KEM mà bỏ qua KDF, xác thực hay key confirmation.

## 4. Lỗ hổng lớn nhất: Diffie-Hellman không tự chống MITM

**Man-in-the-middle (MITM)** là tình huống kẻ tấn công M đứng giữa A và B, chặn/thay public value. A không có cách biết giá trị nhận được là của B nếu không có cơ chế xác thực.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant M as Kẻ tấn công M
    participant B as Server B
    A->>M: Public key A, định gửi B
    M->>B: Public key M1, giả là A
    B->>M: Public key B
    M->>A: Public key M2, giả là B
    Note over A,M: Shared secret riêng A–M
    Note over M,B: Shared secret riêng M–B
    A->>M: Dữ liệu mã hóa theo khóa A–M
    Note over M: Có thể đọc/sửa rồi mã hóa lại
    M->>B: Dữ liệu mã hóa theo khóa M–B
~~~

**Phép toán DH ở từng cặp vẫn đúng**, nhưng A và B không thực sự chia sẻ cùng một khóa do đối thủ đã thay thông tin công khai.

### 4.1. Xác thực đối tác bằng cách nào?

Tùy giao thức, các giải pháp có thể là:

- **Chứng chỉ X.509 và chữ ký số:** Đối tác chứng minh quyền sở hữu private signing key gắn với danh tính được tin cậy; chữ ký hoặc cơ chế xác thực ràng buộc vào thông tin bắt tay DH.
- **Pre-shared key (PSK):** Hai bên có sẵn bí mật xác thực được cấp phát an toàn, dùng trong một giao thức key agreement hỗ trợ PSK.
- **Static public key đã xác thực hoặc pinning:** Public key dài hạn được cấp phát qua nguồn tin cậy, sau đó giao thức ràng buộc khóa đó với phần bắt tay.
- **Giao thức xác thực đã chuẩn hóa:** Ví dụ TLS 1.3, các cấu hình SSH hoặc giao thức dựa trên Noise/HPKE theo mục đích; mỗi giao thức có cách xác minh danh tính và ràng buộc khóa riêng.

**Chỉ truyền public key trong TLS** đến một endpoint bất kỳ không tự chứng minh đúng chủ thể ứng dụng. Cần xác định đúng hostname/identity, trust anchor hoặc chính sách xác thực tương đương. Ngược lại, chữ ký số kiểm tra hợp lệ dưới một public key do chính message cung cấp cũng chưa tạo được niềm tin về danh tính.

### 4.2. Transcript binding và unknown-key-share

Ngoài xác thực khóa, giao thức cần ràng buộc **toàn bộ ngữ cảnh bắt tay** với khóa phiên: phiên bản giao thức, thuật toán/nhóm được thương lượng, public key của hai bên, vai trò client/server, định danh hoặc bằng chứng xác thực và các giá trị fresh được chỉ định.

Nếu không, một bên có thể tính được khóa chung nhưng **hiểu sai mình đang chia sẻ khóa với ai** (unknown-key-share) hoặc chấp nhận thuật toán yếu hơn mong muốn (downgrade). Các giao thức được thiết kế đúng thường đưa **transcript hash** vào quá trình dẫn xuất/xác thực và có thông điệp hoàn tất (Finished/key confirmation) theo đặc tả.

**Không tự thiết kế một giao thức authenticated DH chỉ bằng cách nối chuỗi tùy ý rồi SHA-256.** Hãy ưu tiên giao thức đã được thẩm định, bởi trình tự thông điệp, phản xạ vai trò, xác thực danh tính, kiểm tra public key và chống replay đều ảnh hưởng đến an toàn.

## 5. Tại sao phải dùng KDF sau DH?

Raw shared secret từ **KeyAgreement** là vật liệu khóa trung gian, **không phải khóa ứng dụng đã được quy định**. Cần một **KDF** như HKDF để trích xuất và dẫn xuất khóa có độ dài, vai trò và mục đích phù hợp.

~~~text
rawSharedSecret = DH(ownPrivateKey, peerPublicKey)

transcriptHash = Hash(
    protocolVersion || negotiatedAlgorithm ||
    identities || clientPublic || serverPublic || handshakeContext
)

prk = HKDF-Extract(salt, rawSharedSecret)
clientToServerKey = HKDF-Expand(
    prk, "protocol/v1/client-to-server" || transcriptHash, 32
)
serverToClientKey = HKDF-Expand(
    prk, "protocol/v1/server-to-client" || transcriptHash, 32
)

// Định dạng minh họa: dùng đặc tả giao thức thật khi triển khai.
~~~

### 5.1. Các mục tiêu của KDF

1. **Chuyển shared secret thành các khóa có độ dài được phép:** Ví dụ tạo khóa AES-256 32 byte; không mặc định 32 byte public key X25519 đồng nghĩa raw secret là “AES-256 key”.
2. **Tách miền sử dụng (domain separation):** Khóa mã hóa client → server phải khác khóa server → client; khóa AEAD và khóa cho mục đích khác không được vô tình trùng.
3. **Ràng buộc phiên và giao thức:** Transcript hash, nhãn phiên bản và định danh giúp ngăn trộn khóa giữa các thuật toán, phiên, mục đích hoặc đối tác.
4. **Crypto agility:** Khi nâng thuật toán hoặc phiên bản, định dạng handshake/KDF ghi rõ thông số và kế hoạch chuyển đổi.

**HKDF không tạo thêm entropy không có sẵn trong nguồn.** Nếu private exponent yếu, bị lặp, khóa đối tác không hợp lệ hoặc đối thủ kiểm soát một đầu vào làm DH không an toàn, một bước dẫn xuất hợp lệ **không thể tự khắc phục mọi rủi ro**.

### 5.2. Salt, info và context không giống private key

Trong HKDF, **salt thường không cần bí mật**; **info** là nhãn/ngữ cảnh cho dẫn xuất. Chúng có thể chứa thông số công khai và giá trị phiên. Điều quan trọng là các bên thống nhất byte chính xác và không để đối thủ thay đổi ngữ cảnh đã được xác thực.

Không sử dụng một cách tùy tiện cùng một shared secret cho mọi loại khóa, hoặc dùng trực tiếp **SHA-256(rawSecret)** rồi kết luận đã xây được một giao thức key establishment hoàn chỉnh.

## 6. Ephemeral DH và forward secrecy

**Ephemeral key** là cặp khóa được tạo cho một phiên hoặc handshake theo chính sách. Khi phiên kết thúc, hệ thống ngừng sử dụng và cố gắng loại bỏ vật liệu bí mật tạm thời.

**Forward secrecy (FS)** là tính chất mà việc lộ **khóa xác thực dài hạn** về sau **không tự cho phép** giải mã các phiên đã ghi lại trước đó, trong những giả định và mô hình đe dọa của giao thức. DHE/ECDHE tạm thời cùng cơ chế xác thực đúng có thể đem lại tính chất này.

Ví dụ:

- Ngày 1, client và server lập phiên ECDHE tạm thời, xác thực server bằng chứng chỉ/chữ ký; kẻ tấn công ghi lại gói mạng.
- Ngày 30, private signing key dài hạn của server bị lộ.
- Nếu giao thức đạt forward secrecy, attacker **không thể chỉ nhờ private signing key ngày 30** mà suy ra khóa phiên ngày 1 từ transcript đã ghi lại.

**FS không bảo vệ** trước việc lộ trực tiếp session key, raw DH secret còn lưu trong log/dump, mất an toàn endpoint trong phiên, RNG yếu, hoặc một tấn công MITM đang diễn ra khi kẻ tấn công có khả năng xác thực như server.

### 6.1. Static DH và Ephemeral DH

| Thiết kế | Đặc tính | Rủi ro / điều kiện |
| --- | --- | --- |
| **Static–static DH** | Cả hai bên có cặp khóa lâu dài | Nếu private key lộ, nhiều shared secret cũ có thể bị suy ra từ các public key ghi lại; không tự có FS |
| **Ephemeral–static DH** | Một bên dùng ephemeral, bên kia giữ static | Thuộc tính phụ thuộc giao thức và mục tiêu xác thực; lộ static private key có thể ảnh hưởng các phiên cũ |
| **Ephemeral–ephemeral DH (DHE/ECDHE)** | Hai bên dùng private key tạm thời | Có thể đạt FS khi giao thức xác thực đúng, khóa tạm thời không bị lưu/lộ và đáp ứng các giả định |

**TLS 1.3** là ví dụ giao thức hiện đại dùng trao đổi khóa tạm thời trong các chế độ bắt tay thích hợp, đồng thời có cơ chế xác thực và dẫn xuất khóa phiên rõ ràng. Không nên tái hiện một phần TLS bằng thư viện DH và tự thêm một chữ ký rồi xem tương đương TLS.

## 7. An toàn tham số và kiểm tra public key của đối tác

Đối với bất kỳ họ DH nào, **public key có định dạng hợp lệ không đồng nghĩa public key thuộc đúng đối tác**. Có hai lớp kiểm tra khác nhau:

1. **Tính hợp lệ toán học:** Giá trị có thuộc nhóm/đường cong phù hợp, không gây shared secret nguy hiểm, không thuộc lớp yếu bị cấm theo đặc tả?
2. **Tính xác thực danh tính:** Public key có thật sự được trao đổi bởi bên dự kiến trong handshake có xác thực không?

### 7.1. FFDH: nhóm và public value

Với FFDH, cần chọn nhóm đã được chuẩn hóa, kiểm tra công khai theo đặc tả (giới hạn giá trị, thành viên nhóm/subgroup khi cần) và sử dụng private exponent ngẫu nhiên đủ mạnh. Các nhóm p/g nhỏ, tùy ý hoặc do bên tấn công chỉ định có thể dẫn đến **small-subgroup attack**, downgrade hoặc tấn công khôi phục bí mật.

Không chỉ kiểm tra public value khác 0 rồi chấp nhận. Phải dùng cơ chế và bộ tham số được thư viện/giao thức hỗ trợ đúng, không tự triển khai phép modular exponentiation phục vụ production nếu không có đánh giá chuyên môn.

### 7.2. ECDH: kiểm tra điểm trên đường cong

Với ECDH trên đường cong Weierstrass như P-256, cần kiểm tra kiểu/nhóm, tọa độ điểm, điểm vô cực, phương trình đường cong và những điều kiện bổ sung theo đặc tả. Một thư viện mã hóa an toàn phải xử lý các kiểm tra cần thiết; ứng dụng cần chọn đúng curve và không cho đối thủ đưa một curve tùy ý.

**Không dùng khóa ECDSA/Ed25519 để thay thế X25519 tùy tiện.** Khóa ký và khóa thỏa thuận có mục đích khác nhau; nếu giao thức dùng cùng một vật liệu khóa ở nhiều mục đích, phải có phân tích an toàn riêng và quy tắc chuyển đổi chuẩn.

### 7.3. X25519: xử lý kết quả shared secret toàn số 0

**X25519** chấp nhận đầu vào public 32 byte theo quy tắc riêng. Một số giá trị public đặc biệt có thể dẫn đến **shared secret toàn byte 0**. Các bên cần **từ chối kết quả đó**; một số provider Java đã phát hiện và báo lỗi, nhưng ứng dụng vẫn nên xác nhận hành vi của API/provider và tránh dùng secret toàn 0 làm đầu vào HKDF.

Việc giải mã public key từ SPKI, JWK hay raw bytes chỉ kiểm tra định dạng/cấu trúc ở một mức độ; nó **không xác thực danh tính đối tác** và không thay thế chứng chỉ/chữ ký/PSK ở giao thức.

## 8. Ví dụ Java: X25519 KeyAgreement và HKDF

JDK hiện đại hỗ trợ **X25519** thông qua JCA/JCE (kiểm tra phiên bản và provider thực tế; ví dụ hướng tới Java 17+). Đoạn code dưới đây:

- Sinh **hai cặp ephemeral X25519** cho hai phía.
- Trao đổi public key dưới dạng **SubjectPublicKeyInfo (SPKI)** để mô phỏng truyền qua mạng.
- Dùng **KeyAgreement** tính shared secret và kiểm tra hai bên cho cùng kết quả.
- Dẫn xuất khóa AES-256 bằng **HKDF-SHA-256** với nhãn ngữ cảnh và transcript mô phỏng.
- Mã hóa/giải mã một thông điệp bằng **AES-GCM**.

**Lưu ý nghiêm trọng:** Ví dụ cố ý **không triển khai xác thực public key**; nó giải thích phép DH và KDF, **không phải giao thức trao đổi khóa an toàn để triển khai trực tiếp**. Trong production, ưu tiên **TLS 1.3 hoặc giao thức đã được thẩm định**, có xác thực đối tác và ràng buộc transcript đầy đủ.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class DiffieHellmanDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final byte[] LABEL =
            "dh-demo:v1:aes-256-gcm".getBytes(StandardCharsets.UTF_8);

    private DiffieHellmanDemo() {}

    static KeyPair ephemeralX25519() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        return generator.generateKeyPair();
    }

    static byte[] sharedSecret(PrivateKey ownPrivate, PublicKey peerPublic)
            throws Exception {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ownPrivate);
        agreement.doPhase(peerPublic, true);
        byte[] secret = agreement.generateSecret();

        // Một số provider tự từ chối đầu ra all-zero.
        // Kiểm tra ở đây để không chấp nhận nếu provider trả về all-zero.
        int accumulator = 0;
        for (byte value : secret) {
            accumulator |= (value & 0xff);
        }
        if (accumulator == 0) {
            Arrays.fill(secret, (byte) 0);
            throw new SecurityException("Invalid X25519 shared secret");
        }
        return secret;
    }

    // HKDF-SHA-256 cho đầu ra 32 byte (1 block expand).
    // Mã này chỉ để minh họa. Hệ thống thật dùng HKDF của giao thức/thư viện
    // đã được kiểm chứng và transcript được xác thực đúng cách.
    static byte[] deriveKey(
            byte[] secret, byte[] clientSpki, byte[] serverSpki
    ) throws Exception {
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        sha256.update("dh-demo:transcript:v1"
                .getBytes(StandardCharsets.UTF_8));
        sha256.update(ByteBuffer.allocate(4).putInt(clientSpki.length).array());
        sha256.update(clientSpki);
        sha256.update(ByteBuffer.allocate(4).putInt(serverSpki.length).array());
        sha256.update(serverSpki);
        byte[] publicTranscriptHash = sha256.digest();

        // HKDF-Extract: PRK = HMAC(salt, IKM).
        Mac extract = Mac.getInstance("HmacSHA256");
        extract.init(new SecretKeySpec(publicTranscriptHash, "HmacSHA256"));
        byte[] prk = extract.doFinal(secret);

        // HKDF-Expand: T(1) = HMAC(PRK, info || 0x01).
        try {
            Mac expand = Mac.getInstance("HmacSHA256");
            expand.init(new SecretKeySpec(prk, "HmacSHA256"));
            expand.update(LABEL);
            expand.update((byte) 0x01);
            return expand.doFinal(); // 32 byte = khóa AES-256.
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPair client = ephemeralX25519();
        KeyPair server = ephemeralX25519();

        // Chỉ trao đổi public key; private key không rời khỏi phía sở hữu.
        byte[] clientSpki = client.getPublic().getEncoded();
        byte[] serverSpki = server.getPublic().getEncoded();

        // Việc parse SPKI KHÔNG xác thực người gửi public key.
        PublicKey serverKeyReceived = KeyFactory.getInstance("X25519")
                .generatePublic(new X509EncodedKeySpec(serverSpki));
        PublicKey clientKeyReceived = KeyFactory.getInstance("X25519")
                .generatePublic(new X509EncodedKeySpec(clientSpki));

        byte[] clientShared = sharedSecret(
                client.getPrivate(), serverKeyReceived);
        byte[] serverShared = sharedSecret(
                server.getPrivate(), clientKeyReceived);
        System.out.println("Shared secret matches: " +
                MessageDigest.isEqual(clientShared, serverShared));

        byte[] clientKeyBytes = deriveKey(
                clientShared, clientSpki, serverSpki);
        byte[] serverKeyBytes = deriveKey(
                serverShared, clientSpki, serverSpki);

        try {
            System.out.println("Derived key matches: " +
                    MessageDigest.isEqual(clientKeyBytes, serverKeyBytes));

            byte[] nonce = new byte[12];
            RNG.nextBytes(nonce);
            byte[] aad = "client-to-server|demo-session"
                    .getBytes(StandardCharsets.UTF_8);
            byte[] plaintext = "Xin chao qua kenh DH"
                    .getBytes(StandardCharsets.UTF_8);

            Cipher enc = Cipher.getInstance("AES/GCM/NoPadding");
            enc.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(clientKeyBytes, "AES"),
                    new GCMParameterSpec(128, nonce));
            enc.updateAAD(aad);
            byte[] ciphertextWithTag = enc.doFinal(plaintext);

            Cipher dec = Cipher.getInstance("AES/GCM/NoPadding");
            dec.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(serverKeyBytes, "AES"),
                    new GCMParameterSpec(128, nonce));
            dec.updateAAD(aad);
            byte[] recovered = dec.doFinal(ciphertextWithTag);
            System.out.println(new String(
                    recovered, StandardCharsets.UTF_8));
        } finally {
            Arrays.fill(clientKeyBytes, (byte) 0);
            Arrays.fill(serverKeyBytes, (byte) 0);
            Arrays.fill(clientShared, (byte) 0);
            Arrays.fill(serverShared, (byte) 0);
        }
    }
}
~~~

**Kết quả dự kiến (giá trị khóa được sinh mới, không in khóa):**

~~~text
Shared secret matches: true
Derived key matches: true
Xin chao qua kenh DH
~~~

### 8.1. Phân tích code và những giới hạn

1. **KeyPairGenerator X25519** tạo cặp khóa; hai cặp được tạo mới cho minh họa một phiên. Không được dùng **java.util.Random** hoặc thời gian hệ thống làm private exponent.
2. **KeyAgreement.doPhase** kết hợp private key của mình với public key đối tác. Hai bên tạo ra raw secret có cùng giá trị khi các public key hợp lệ và không bị thay.
3. **X509EncodedKeySpec** chỉ biểu diễn SPKI public key; việc parse không chứng minh nó thuộc đúng client/server. Trong một hệ thống thật, phải xác thực peer và transcript **trước khi coi khóa phiên là đáng tin**.
4. **deriveKey** minh họa HKDF-Extract và một block HKDF-Expand cho 32 byte. Transcript hash được xây từ thông số công khai **có thứ tự client/server**; đây chỉ là ví dụ định dạng. Giao thức thực cần transcript đầy đủ đã xác thực, có thể có salt và nhiều nhãn khóa khác nhau.
5. **AES-GCM nonce** 12 byte là tham số mã hóa sau DH, không phải private DH exponent; nonce phải không tái sử dụng dưới cùng khóa AES. Trong giao thức hai chiều, dẫn xuất **khóa và nonce sequence riêng cho từng hướng**, không lấy một key chung rồi tự gửi hai chiều vô hạn.
6. Code minh họa chỉ xóa được một số **byte array** do ứng dụng kiểm soát. JVM/provider có thể giữ bản sao khác; việc xóa raw secret không đảm bảo xóa mọi giá trị trung gian hoặc private key.
7. Ví dụ không có chứng chỉ/chữ ký/PSK, kiểm tra danh tính, chống replay, key confirmation, key rotation hoàn chỉnh, kiểm soát quyền hoặc cơ chế giao thức bảo vệ lỗi. **Không dùng đoạn code này thay TLS**.

### 8.2. Vì sao không lưu hoặc gửi raw DH secret?

Raw shared secret là bí mật có thể dùng để dẫn xuất mọi khóa con nếu context được biết. Ghi nó vào log, trả qua API hoặc lưu vào database giống như làm lộ vật liệu khóa. Trong chương trình thực, không log raw secret, private key hoặc key bytes; chỉ ghi **key ID, session ID, thuật toán, peer identity đã xác thực, kết quả và mã lỗi không nhạy cảm**.

## 9. Diffie-Hellman trong TLS 1.3 và hệ thống Java

Trong những chế độ phù hợp, **TLS 1.3** sử dụng (EC)DHE để thiết lập bí mật phiên, đồng thời thực hiện **xác thực và dẫn xuất khóa theo handshake**. Ứng dụng Java dùng **SSLSocket, SSLEngine, HTTPS client/server hoặc framework TLS** nên để thư viện TLS thực hiện các bước đó.

Một luồng khái niệm:

~~~mermaid
flowchart TD
    C["Java client bắt đầu kết nối"] --> NEG["Thương lượng nhóm và thuật toán theo TLS"]
    NEG --> EPH["Trao đổi public (EC)DHE tạm thời"]
    EPH --> AUTH["Xác thực server/client theo cấu hình TLS<br/>chứng chỉ, PSK hoặc cơ chế tương ứng"]
    AUTH --> KDF["Transcript-bound key schedule<br/>dẫn xuất traffic keys"]
    KDF --> AEAD["AEAD bảo vệ dữ liệu ứng dụng"]
    AEAD --> ROT["Đóng phiên / cập nhật khóa theo giao thức"]
~~~

**Các điểm ứng dụng Java cần cấu hình đúng:**

- **Hostname verification và truststore:** Không vô hiệu hóa kiểm tra chứng chỉ chỉ để kết nối thành công trong thử nghiệm.
- **Danh sách protocol/cipher suite/nhóm được hỗ trợ:** Dựa trên chính sách và provider, tránh kích hoạt giao thức cũ không được cho phép.
- **Xác thực hai chiều khi cần:** Nếu service-to-service yêu cầu định danh cả hai bên, có thể dùng **mTLS** hoặc cơ chế tương đương.
- **Quyền nghiệp vụ:** TLS xác thực endpoint và mã hóa đường truyền; sau đó API vẫn cần kiểm tra người dùng, tenant, scope và quyền thao tác.
- **Phiên và chống replay:** Tuân thủ chính sách giao thức và lưu ý các tính chất đặc biệt của dữ liệu gửi sớm **0-RTT**, nếu sử dụng.

Không cần ứng dụng tự gọi **KeyAgreement** để thiết lập traffic key của TLS; thao tác DH thuộc trách nhiệm của **thư viện triển khai TLS**.

## 10. Diffie-Hellman và quản lý khóa qua KMS/HSM

**KMS/HSM** có thể bảo vệ private key dài hạn, chứng chỉ hoặc thao tác chữ ký dùng để xác thực handshake. Một số thiết bị/provider còn hỗ trợ **ECDH, KDF hoặc private key non-exportable**; nhưng **không mặc định mọi API KMS đều hỗ trợ DH hoặc trả raw shared secret**.

### 10.1. Phân biệt các lớp khóa

| Vật liệu khóa | Vai trò | Vòng đời/điều kiện bảo vệ |
| --- | --- | --- |
| **Long-term signing key** | Xác thực handshake bằng chữ ký/chứng chỉ | Bảo vệ nghiêm ngặt, hạn chế Sign, quản lý chứng chỉ và rotation |
| **Ephemeral DH private key** | Đóng góp vào shared secret của một phiên | Sinh mới, không truyền qua mạng, giảm thời gian tồn tại, không tái sử dụng trái giao thức |
| **DH shared secret** | Đầu vào cho KDF | Không log/không lưu dạng rõ; xử lý trong ranh giới cần thiết |
| **Traffic keys** | Mã hóa/xác thực dữ liệu phiên bằng AEAD | Dẫn xuất theo hướng/phiên, quản lý nonce và giới hạn sử dụng |
| **DEK** | Mã hóa dữ liệu lưu trữ | Có thể là khóa riêng được sinh bởi KMS, được wrap bằng KEK |
| **KEK/root key** | Bảo vệ khóa con hoặc DEK trong hệ phân cấp | Có thể nằm trong HSM/KMS, tách quyền và phiên bản |

**DH shared secret không tự động là KEK hoặc DEK của hệ thống lưu trữ.** Một giao thức có thể dẫn xuất một khóa để wrap DEK, nhưng phải có đặc tả về KDF, key usage, quyền và định dạng envelope. Với dữ liệu **at rest**, thông thường hệ thống quản lý DEK/KEK bằng KMS/HSM; với **in transit**, TLS sử dụng traffic keys dẫn xuất từ handshake.

### 10.2. Envelope encryption và DH có thể kết hợp thế nào?

Giả sử hai bên cần chuyển một **DEK** dùng để mã hóa tệp:

1. Hai bên thực hiện **authenticated key agreement** theo một giao thức được thẩm định.
2. KDF tạo ra khóa bọc/mã hóa riêng cho mục đích **chuyển DEK** trong phiên.
3. DEK được bảo vệ bằng AEAD/key wrapping thích hợp; dữ liệu tệp được mã hóa với DEK của nó.
4. Bên nhận xác minh thông tin người gửi, ngữ cảnh, tag và quyền trước khi chấp nhận DEK.
5. Khi cần lưu lâu dài, DEK có thể được **rewrap dưới KEK của bên nhận trong KMS/HSM** theo policy.

Đây là mô hình khái niệm; khi triển khai, ưu tiên **TLS + KMS envelope encryption, HPKE hoặc giao thức được chuẩn hóa phù hợp** thay vì tự tạo một hệ trao đổi khóa.

### 10.3. Phân quyền và kiểm toán

Đối với private key dài hạn hoặc HSM:

- Tách quyền **Sign/Verify, DeriveKey, Decrypt, Rotate, Delete và Export** theo tính năng thực tế của dịch vụ.
- Chỉ các workload và danh tính được phép mới thực hiện thao tác nhạy cảm.
- Log **key ID, phiên bản, chủ thể gọi, peer đã xác thực, thời điểm, hành động, kết quả**; không log private key, raw shared secret, traffic key hoặc plaintext.
- Cảnh báo tăng đột biến yêu cầu ký/thiết lập khóa, thay chính sách, chứng chỉ mới bất thường hoặc lỗi xác thực bắt tay liên tiếp.

**Non-exportable private key** giảm nguy cơ lấy trực tiếp key bytes, nhưng workload bị chiếm quyền vẫn có thể **lạm dụng API Sign/Derive** đã được cấp. Vì thế, bảo vệ danh tính ứng dụng và chính sách truy cập là bắt buộc.

## 11. Vòng đời khóa Diffie-Hellman và xử lý sự cố

| Giai đoạn | Điều cần kiểm soát | Ví dụ lỗi |
| --- | --- | --- |
| **Tạo** | Chọn nhóm/curve và provider đáng tin cậy; sinh private exponent bằng CSPRNG | Random yếu, nhóm quá nhỏ, tham số tự chọn |
| **Cấp phát / trao đổi** | Chỉ công bố public key; xác thực đối tác và thông số handshake | Tin public key do MITM thay thế |
| **Lưu trữ** | Bảo vệ private key dài hạn, metadata/certificate; ephemeral key chỉ tồn tại cần thiết | Ghi raw secret/private key vào log, dump hoặc backup |
| **Sử dụng** | Kiểm tra peer key, áp dụng KDF/transcript, tách khóa hướng, nonce AEAD | Dùng raw secret trực tiếp làm khóa hoặc không xác thực peer |
| **Xoay vòng / tái lập phiên** | Tạo ephemeral key mới theo phiên, rotation key/chứng chỉ dài hạn có kế hoạch | Dùng lại ephemeral private key hoặc vô hiệu hóa cert mới chưa phân phối |
| **Thu hồi** | Thu hồi trust với khóa/chứng chỉ bị lộ; xử lý phiên/các client còn lưu cache | Nghĩ chỉ xóa key trong một máy đã đủ |
| **Hủy** | Ngừng dùng và xóa vật liệu phiên khi không còn cần; giữ bằng chứng audit không bí mật | Hủy nhầm private key cần thiết cho đường tương thích hoặc lưu secret quá lâu |

### 11.1. Lộ khóa dài hạn và lộ khóa tạm thời khác nhau

- **Lộ private signing key dài hạn:** Kẻ tấn công có thể giả mạo danh tính trong các handshake mới nếu chưa bị thu hồi. Với giao thức có **ephemeral DH và FS đúng**, việc chỉ lộ signing key không tự giải mã các phiên cũ đã ghi lại.
- **Lộ ephemeral DH private key:** Có thể khiến phiên liên quan bị nguy hiểm, nhất là khi đối thủ có các public value cần thiết. Cần xử lý phiên và dữ liệu liên quan; thay signing key dài hạn chưa chắc giải quyết đúng vấn đề.
- **Lộ traffic key hoặc raw shared secret:** Có thể làm lộ dữ liệu phiên; cần kiểm tra phạm vi, dừng/thiết lập lại phiên, khắc phục nguồn lộ và điều tra.

**Forward secrecy không phải phép xóa lịch sử.** Plaintext đã bị sao chép trong thời gian endpoint bị kiểm soát không được “thu hồi” khi phiên kết thúc.

### 11.2. Nếu public key bị thay thế hoặc kiểm tra peer thất bại

Khi phát hiện một handshake có dấu hiệu MITM hoặc lỗi xác thực:

1. **Không dùng khóa phiên** từ handshake đáng ngờ để xử lý dữ liệu nhạy cảm.
2. Ghi nhận peer identity, phiên bản giao thức, key ID/chứng chỉ liên quan và mã lỗi phù hợp, không log bí mật.
3. Kiểm tra chuỗi tin cậy, chứng chỉ, PSK, policy, clock và kênh phân phối key; không tắt verification để “xử lý nhanh”.
4. Điều tra các phiên trước đó có cùng cấu hình lỗi; thay khóa/cert hoặc cập nhật truststore khi có bằng chứng xâm phạm.
5. Bổ sung kiểm thử fail-closed, rollback/downgrade và giả mạo public key trong quy trình phát hành.

## 12. Tình huống thực tế: Java microservices cần giao tiếp an toàn

Giả sử hệ thống có dịch vụ **Orders** gọi **Payments**, dùng Java và chạy nhiều instance. Yêu cầu là chống nghe lén/sửa dữ liệu trên mạng, xác minh đúng dịch vụ nhận và giảm thiệt hại nếu một khóa định danh dài hạn bị lộ trong tương lai.

**Thiết kế khuyến nghị ở mức kiến trúc:**

1. Dùng **TLS 1.3** qua framework hỗ trợ, với chính sách chứng chỉ và cipher suite phù hợp.
2. Nếu phải xác thực cả Orders và Payments, sử dụng **mTLS** với danh tính dịch vụ đã được xác minh.
3. Để thư viện TLS thiết lập traffic keys bằng (EC)DHE/PSK theo giao thức; không dùng một AES key hardcode chung cho mọi kết nối.
4. Bảo vệ private key xác thực bằng key store/HSM/KMS thích hợp; kiểm soát rotation và cách phát chứng chỉ.
5. Kiểm tra quyền của Orders đối với API Payments ở tầng ứng dụng; TLS không tự quyết định một đơn hàng có được hoàn tiền không.
6. Nếu cần mã hóa nội dung thanh toán **at rest**, dùng DEK/KEK và envelope encryption riêng; không lấy traffic key TLS lưu thành key dài hạn.
7. Log handshake failures, peer identity, cert version và sự kiện đổi khóa; không log raw DH secret hay payment plaintext.

**Các phép kiểm thử quan trọng:**

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Client nhận chứng chỉ của dịch vụ không đúng danh tính | Handshake hoặc bước xác thực danh tính thất bại |
| Kẻ trung gian thay public key DH | Bước xác thực handshake bị từ chối theo giao thức |
| Private signing key server bị lộ sau khi một phiên FS đã kết thúc | Không mặc định giải mã được bản ghi mạng của phiên trước chỉ từ private signing key |
| Hai instance cùng tạo handshake | Có ephemeral key/traffic key tương ứng từng phiên, không dùng lại trạng thái trái giao thức |
| Khóa phiên/nonce bị lộ hoặc tái sử dụng | Hệ thống ứng phó theo phạm vi phiên, xác thực và chính sách rotation |
| User của tenant A gọi dữ liệu tenant B | Bị từ chối bởi kiểm soát quyền nghiệp vụ dù TLS hợp lệ |
| KMS/HSM/truststore gặp lỗi | Fail closed, không tự động bỏ xác thực hoặc dùng khóa mặc định |

## 13. Những nhầm lẫn phổ biến về Diffie-Hellman

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “DH mã hóa dữ liệu giống AES.” | DH tạo shared secret, không phải mã hóa payload | Dẫn xuất traffic key rồi dùng AEAD hoặc giao thức hoàn chỉnh |
| “Shared secret giống nhau là đã xác thực server.” | MITM có thể tạo bí mật riêng với mỗi bên | Phải xác thực public key/handshake và ràng buộc transcript |
| “Public key là công khai nên có thể tin key bất kỳ.” | Kẻ tấn công thay public key được | Kiểm tra trust anchor, danh tính, chữ ký/PSK hoặc pinning |
| “Raw DH secret dài 32 byte là AES-256 key.” | Kích thước byte không thay được KDF và domain separation | Dùng HKDF/key schedule theo giao thức |
| “ECDH và ECDSA làm cùng một việc.” | ECDH thỏa thuận khóa, ECDSA ký số | Dùng đúng primitive và key usage |
| “Dùng ephemeral DH thì chắc chắn có forward secrecy.” | Còn phụ thuộc xác thực, bảo vệ/xóa ephemeral key và giao thức | Đánh giá tính chất FS của toàn bộ protocol |
| “X25519 SPKI parse thành công là key thuộc đúng peer.” | Parser không xác minh danh tính | Kết hợp peer authentication, kiểm tra đầu ra all-zero và trust |
| “Key dài hơn sửa được lỗi MITM.” | MITM đánh vào xác thực, không phải dò vét cạn | Dùng authenticated key establishment |
| “KMS giữ private signing key thì app không thể bị lạm dụng.” | App vẫn có quyền gọi Sign/Derive theo policy | Least privilege, IAM, giám sát và audit |
| “Dùng chung một traffic key cho hai chiều mãi mãi.” | Dễ trộn ngữ cảnh/nonce và vượt giới hạn | KDF tách chiều, nonce sequence và rotation theo giao thức |
| “TLS xác thực kết nối nên không cần phân quyền API.” | Kết nối đúng chưa chứng minh quyền đối với tài nguyên | Kiểm tra authorization ở ứng dụng |
| “ML-KEM chỉ là một loại DH mới.” | Giả định toán học và API khác DH | Chọn KEM/giao thức theo tiêu chuẩn và chính sách hậu lượng tử |

## 14. Checklist đánh giá DH/key establishment

Trước khi triển khai hoặc review một thiết kế:

1. **Mục tiêu:** Cần thiết lập khóa phiên, wrap DEK hay ký số? Đã chọn đúng primitive chưa?
2. **Giao thức:** Có dùng TLS/HPKE hoặc authenticated key establishment được thẩm định thay vì tự thiết kế handshake?
3. **Nhóm/curve:** FFDHE, P-256, X25519 hay nhóm nào? Có đủ độ mạnh, được hỗ trợ và phù hợp chính sách?
4. **Nguồn sinh:** Ephemeral private keys có được sinh bằng CSPRNG/provider tin cậy và không tái sử dụng trái thiết kế?
5. **Peer validation:** Có kiểm tra public value/point, loại khóa, nhóm, X25519 all-zero và định dạng không?
6. **Xác thực danh tính:** Chứng chỉ/chữ ký/PSK/pinning có ràng buộc đúng peer, key usage và trust anchor không?
7. **Transcript:** Thuật toán, phiên bản, key shares, danh tính và role có được ràng buộc chống downgrade, reflection và unknown-key-share không?
8. **KDF:** Có dùng HKDF/key schedule được chuẩn hóa, với salt/info/context và tách khóa hai chiều, mục đích khác nhau?
9. **AEAD:** Có quản lý nonce, tag, AAD, key usage limits và từ chối plaintext khi xác thực thất bại?
10. **Vòng đời:** Long-term signing key, ephemeral private, raw secret và traffic keys được lưu giữ/xóa/rotate theo đúng mục đích?
11. **KMS/HSM:** Nếu dùng HSM hoặc KMS, API có thật sự hỗ trợ thao tác cần thiết, các quyền được giới hạn và audit đầy đủ?
12. **Ứng phó sự cố:** Có thể xử lý MITM, lộ private key, lộ traffic key, thu hồi chứng chỉ và khôi phục mà không vô hiệu hóa xác thực?
13. **Kiểm thử:** Đã thử khóa sai, chứng chỉ sai, handshake downgrade, provider lỗi, replay và nhiều instance đồng thời?

## 15. Ghi nhớ

- **Diffie-Hellman** cho phép hai bên tạo **shared secret** từ private key của mình và public key đối tác, mà không gửi shared secret dạng rõ qua mạng.
- Có **FFDH, ECDH, X25519/X448** với các tham số, kiểm tra khóa và độ mạnh khác nhau. Không tự chọn nhóm yếu hoặc trộn public key giữa các thuật toán.
- **DH thuần túy không xác thực danh tính.** Phải dùng authenticated key establishment; nếu không, kẻ trung gian có thể thay public key.
- **Raw DH secret cần qua KDF**, thường là HKDF/key schedule, có phân tách mục đích, hướng truyền và ràng buộc transcript.
- **Ephemeral DH** kết hợp đúng với xác thực có thể mang lại **forward secrecy**, nhưng không bảo vệ trước việc lộ session key hoặc endpoint trong phiên.
- Trong Java, **KeyAgreement/X25519** minh họa nguyên lý; ứng dụng production nên ưu tiên **TLS 1.3 và giao thức đã được thẩm định**, thay vì tự xây handshake.
- **KMS/HSM, DEK/KEK, kiểm soát truy cập, kiểm toán và quy trình tạo–cấp phát–lưu trữ–sử dụng–xoay vòng–thu hồi–hủy** vẫn cần thiết để vận hành hệ thống bảo vệ khóa an toàn.

Một thiết kế Diffie-Hellman chỉ hoàn chỉnh khi trả lời được: **“Tôi đang chia sẻ khóa với đúng ai?”, “Shared secret được biến thành những khóa nào và ràng buộc với phiên ra sao?”, “Nếu một khóa hoặc endpoint bị xâm phạm, những phiên và dữ liệu nào bị ảnh hưởng?”** Ba câu hỏi này nối phép toán thỏa thuận khóa với bảo mật thực tế của hệ thống.
