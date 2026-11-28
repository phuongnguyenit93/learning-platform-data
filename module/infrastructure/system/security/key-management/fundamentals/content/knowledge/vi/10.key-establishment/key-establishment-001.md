# Key establishment là gì? – Thiết lập khóa mật mã giữa các bên

**Key establishment (thiết lập khóa)** là quá trình hai hoặc nhiều bên đạt được **vật liệu khóa mật mã chung** để sử dụng trong một giao thức, chẳng hạn khóa AES-GCM để mã hóa dữ liệu phiên hoặc khóa HMAC để xác thực thông điệp. Quá trình này có thể dựa trên **truyền khóa được bảo vệ (key transport)**, **thỏa thuận khóa (key agreement)**, **cơ chế đóng gói khóa (KEM)** hoặc một giao thức phối hợp nhiều kỹ thuật.

Trong chương **Key establishment** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, đây là điểm kết nối giữa mật mã bất đối xứng, mật mã đối xứng, chữ ký số, KDF, KMS/HSM và envelope encryption. Thiết lập khóa tốt không chỉ làm hai bên có cùng một chuỗi byte, mà còn phải quản lý **ai được tham gia, khóa được dùng để làm gì, có chống giả mạo bên kia không, khóa tồn tại bao lâu và được thu hồi/hủy thế nào**.

> **Phân biệt quan trọng:** **Key establishment không đồng nghĩa với key generation**. Sinh khóa tạo vật liệu khóa; thiết lập khóa giải quyết cách các bên **cùng có được khóa phù hợp, an toàn và đúng ngữ cảnh**. Đồng thời, hai bên tính được cùng bí mật **chưa chứng minh** họ đã kết nối với đúng đối tác.

## 1. Vì sao cần key establishment?

Giả sử **Order Service** và **Billing Service** muốn trao đổi dữ liệu nhạy cảm qua một mạng không đáng tin cậy. AES-GCM mã hóa và xác thực dữ liệu rất hiệu quả, nhưng cả hai phía cần có **khóa AES phù hợp** trước khi dùng. Gửi khóa AES dạng rõ qua mạng sẽ làm mất tính bí mật của khóa; hard-code cùng một secret cho tất cả bản triển khai khiến việc thay khóa và giới hạn phạm vi sự cố trở nên khó khăn.

Một giao thức thiết lập khóa nên giải quyết các câu hỏi sau:

1. **Khóa từ đâu?** Được sinh bởi một bên, một dịch vụ quản lý khóa hay được tạo từ đóng góp của nhiều bên?
2. **Phân phối bằng cách nào?** Làm sao để người nghe lén không lấy được bí mật?
3. **Bên kia là ai?** Làm sao tránh kẻ tấn công đóng giả server/client hoặc thay public key?
4. **Khóa dùng cho phạm vi nào?** Một phiên, một tenant, một kết nối, một tệp hay một dịch vụ?
5. **Bảo vệ điều gì?** Cần khóa mã hóa, khóa MAC hay nhiều khóa độc lập theo chiều truyền và mục đích?
6. **Khi nào đổi và hủy?** Nếu khóa phiên, danh tính lâu dài hay KMS bị lộ, những dữ liệu nào bị ảnh hưởng?

Giao thức tốt phải cung cấp **tính bí mật của khóa (key secrecy)** và các thuộc tính xác thực/độ mới/chống phát lại theo nhu cầu, không chỉ “thực hiện phép toán DH thành công”.

## 2. Những cách thiết lập khóa phổ biến

### 2.1. Key transport – Truyền khóa được bảo vệ

Ở mô hình **key transport**, một phía hoặc dịch vụ được ủy quyền tạo vật liệu khóa, rồi chuyển vật liệu đó cho bên khác qua một cơ chế bảo vệ phù hợp.

Ví dụ: Alice sinh khóa AES ngẫu nhiên, dùng **public key RSA-OAEP đã xác thực** của Bob để mã hóa khóa đó. Bob giải mã bằng private key RSA của mình để lấy cùng khóa AES. Hai bên có khóa chung, nhưng **Alice là bên lựa chọn khóa**; giao thức phải bổ sung xác thực người gửi và ngữ cảnh sử dụng nếu cần.

Một ví dụ khác: **KMS** sinh **DEK**, bọc DEK bằng **KEK** rồi cho các workload đã cấp quyền lấy lại DEK qua API. Trường hợp này thường thuộc **phân phối/bảo vệ khóa được quản lý**, không phải ECDH, và cần kiểm soát ai có quyền unwrap.

### 2.2. Key agreement – Thỏa thuận khóa

Ở mô hình **key agreement**, hai bên kết hợp đóng góp bí mật của mình để tính ra một bí mật chung mà người quan sát chỉ thấy thông tin công khai khó suy ra được.

Ví dụ điển hình là **Elliptic-Curve Diffie–Hellman (ECDH)**, bao gồm **X25519**. Alice giữ private key của Alice và Bob giữ private key của Bob; sau khi trao đổi public key hợp lệ, hai bên tính được cùng kết quả ECDH.

**Điểm yếu quan trọng:** ECDH thuần **không tự xác thực public key của đối tác**. Nếu kẻ tấn công thay public key trong lúc trao đổi, họ có thể đứng giữa và thiết lập hai bí mật khác nhau với hai nạn nhân (**man-in-the-middle, MITM**).

### 2.3. KEM – Key Encapsulation Mechanism

**KEM** dùng một cặp thao tác **Encapsulate/Decapsulate**: bên gửi dùng public key hợp lệ của bên nhận để tạo **ciphertext đóng gói** và **shared secret**; bên nhận dùng private key để giải đóng gói và tái tạo shared secret tương ứng. KEM là mô hình hiện đại được sử dụng trong các giao thức lai như **HPKE** và các giải pháp chuyển đổi hậu lượng tử.

KEM **không đồng nhất với mã hóa bất kỳ chuỗi khóa tùy ý bằng public key**. Trong KEM, shared secret thường là kết quả của thuật toán đóng gói; các ràng buộc ciphertext/thuật toán và xử lý lỗi do chuẩn quy định. Tương tự, KEM **không tự chứng minh danh tính chủ public key**: giao thức cần xác thực khóa nhận và những tuyên bố về đối tác.

| Cách thiết lập | Khóa cuối được hình thành thế nào? | Ví dụ | Điều cần bảo vệ |
| --- | --- | --- | --- |
| **Key transport** | Khóa được một bên sinh rồi bảo vệ để chuyển sang bên khác. | Truyền khóa nhỏ bằng RSA-OAEP; phân phối DEK qua KMS. | Danh tính bên nhận, cơ chế bảo vệ khóa, quyền lấy khóa và nguồn gửi. |
| **Key agreement** | Các bên phối hợp bí mật riêng để tính shared secret. | ECDH P-256, X25519. | Public key đối tác, tham số/giao thức, KDF, xác thực và MITM. |
| **KEM** | Encapsulation tạo ciphertext và shared secret; decapsulation khôi phục secret. | KEM trong HPKE; ML-KEM theo giao thức hỗ trợ. | Public key đáng tin, kiểm tra ciphertext, KDF và chính sách giao thức. |
| **PSK – Pre-Shared Key** | Khóa đã được phân phối an toàn trước lúc giao tiếp. | Hệ thống đóng có PSK theo môi trường hoặc tenant. | Phương thức cấp phát, độ mới, phạm vi chia sẻ, rotate/revoke và chống phát lại. |

Một giao thức hoàn chỉnh có thể kết hợp nhiều mô hình, chẳng hạn **ECDHE + chứng chỉ/chữ ký số**, hoặc **PSK + (EC)DHE**. Đừng suy luận thuộc tính của toàn bộ kết nối chỉ từ một thuật toán đơn lẻ.

## 3. Ví dụ trực quan: X25519 key agreement

X25519 sử dụng các phép toán dựa trên Curve25519 để thực hiện thỏa thuận khóa. Ví dụ khái niệm:

- Alice sinh cặp khóa tạm thời **(a, A)**, trong đó \`a\` là private key và \`A\` là public key.
- Bob sinh cặp khóa tạm thời **(b, B)**, trong đó \`b\` là private key và \`B\` là public key.
- Hai bên trao đổi **A** và **B** qua mạng.
- Alice tính \`ECDH(a, B)\`; Bob tính \`ECDH(b, A)\`.
- Nếu thông tin đối tác hợp lệ và phép toán thành công, hai bên thu được **cùng shared secret**; sau đó dùng **KDF** để tạo khóa phục vụ mã hóa/xác thực.

~~~mermaid
sequenceDiagram
    participant A as Alice
    participant N as Mạng không tin cậy
    participant B as Bob
    Note over A: Sinh (a, A) tạm thời
    Note over B: Sinh (b, B) tạm thời
    A->>N: Public key A
    N->>B: Public key A
    B->>N: Public key B
    N->>A: Public key B
    Note over A: shared = X25519(a, B)
    Note over B: shared = X25519(b, A)
    Note over A,B: HKDF(shared, transcript, context)
    Note over A,B: Dẫn xuất khóa phiên tương ứng
~~~

**Public key không cần giữ bí mật.** Ngược lại, private key của mỗi bên và shared secret phải được bảo vệ. Việc nhận một public key từ mạng **không chứng minh nó thuộc đúng Bob hoặc Alice**.

### 3.1. Vì sao không dùng thẳng kết quả ECDH làm khóa AES?

Shared secret từ ECDH là **vật liệu khóa đầu vào**, không phải mặc định đã có mọi thuộc tính và cấu trúc cần thiết cho từng khóa ứng dụng. Giao thức nên dùng **KDF chuẩn**, thường là **HKDF**, để:

- **Extract:** biến vật liệu đầu vào cùng salt thích hợp thành **pseudorandom key (PRK)**.
- **Expand:** tạo các khóa có độ dài và mục đích rõ ràng, ví dụ khóa AES-256 cho chiều Alice → Bob và khóa riêng cho chiều Bob → Alice.
- **Ràng buộc ngữ cảnh:** dùng **protocol version, roles, thuật toán đã thương lượng, danh tính và transcript hash** ở vị trí được đặc tả để tránh dùng nhầm cùng key giữa các phiên/giao thức.

~~~text
sharedSecret = X25519(alicePrivate, bobPublic)

prk = HKDF-Extract(salt, sharedSecret)

clientToServerKey = HKDF-Expand(prk, "protocol-v1|c2s|transcriptHash", 32)
serverToClientKey = HKDF-Expand(prk, "protocol-v1|s2c|transcriptHash", 32)
~~~

Đây là **giả mã về mục đích**, không phải định dạng HKDF wire protocol được chuẩn hóa. Trong giao thức thật, các nhãn và trường cần encoding không mơ hồ, cùng những quy tắc domain separation chính xác. Salt thường **không cần bí mật** nhưng phải được xử lý theo thiết kế của giao thức; một số trường hợp HKDF cho phép salt rỗng/không được cấp và có quy tắc mặc định riêng.

**KDF không tự ngăn MITM.** Nếu Alice dùng public key của kẻ tấn công thay Bob, một HKDF hoàn hảo vẫn chỉ tạo ra khóa bí mật giữa Alice và kẻ tấn công.

### 3.2. Kiểm tra khóa và các giá trị ECDH không hợp lệ

Giao thức phải sử dụng API/provider xử lý đúng **định dạng public key, tham số đường cong và kiểm tra hợp lệ**. Với X25519, cần xử lý trường hợp **shared secret toàn byte 0** theo tiêu chí của chuẩn/giao thức và không tiếp tục dùng giá trị không hợp lệ để dẫn xuất khóa; một số provider có thể từ chối ở bước \`generateSecret()\`.

Không tự chuyển \`byte[]\` ngẫu nhiên thành public key hoặc bỏ qua lỗi kiểm tra khóa chỉ để handshake “thành công”. Tương tự, không trộn khóa X25519 với Ed25519 vì cùng liên quan Curve25519: **X25519 dành cho key agreement; Ed25519 dành cho chữ ký số**.

## 4. Xác thực đối tác và chống man-in-the-middle

Xác thực là khác biệt giữa **“đã có shared secret”** và **“đã có shared secret với đúng đối tác”**.

Giả sử kẻ tấn công Mallory chặn công khai A/B. Mallory thay public key của Bob khi gửi tới Alice bằng public key của chính mình, đồng thời thay public key của Alice khi gửi tới Bob. Khi đó có thể tồn tại:

- Khóa phiên **Alice ↔ Mallory** mà Alice nhầm là khóa với Bob.
- Khóa phiên **Mallory ↔ Bob** mà Bob nhầm là khóa với Alice.

Mallory có thể giải mã, sửa rồi mã hóa lại dữ liệu chuyển tiếp nếu không có cơ chế xác thực bổ sung. Cả Alice và Bob vẫn thấy phép tính ECDH và giải mã đối xứng hoạt động bình thường.

### 4.1. Những cách xác thực thường dùng

1. **Chứng chỉ và PKI:** verifier kiểm tra chuỗi tin cậy, danh tính server, mục đích khóa, thời hạn và trạng thái chứng chỉ theo giao thức. Ví dụ TLS 1.3 thường xác thực server bằng chứng chỉ/chữ ký trong quá trình bắt tay.
2. **Chữ ký số trên transcript:** một bên ký dữ liệu bắt tay quan trọng bằng private key danh tính đã tin cậy (ví dụ Ed25519/ECDSA/RSA-PSS), bên kia xác minh với public key được cấp phát qua kênh tin cậy.
3. **PSK đã xác thực:** dùng bí mật được chia sẻ và quản lý trước đó để xác thực hoặc liên kết quá trình bắt tay theo giao thức được chuẩn hóa.
4. **Giao thức được chứng minh/đánh giá:** dùng TLS 1.3, một giao thức Noise được cấu hình đúng hoặc HPKE với đúng mode và cơ chế xác thực khi phù hợp; không tự thiết kế handshake từ các primitive riêng lẻ.

Trong một mô hình đơn giản, server có thể ký **protocol version + danh tính + lựa chọn thuật toán + public key tạm thời của cả hai bên + các trường bắt tay cần thiết**. Client xác minh chữ ký bằng **public key danh tính server đã được tin cậy** trước khi coi handshake là được xác thực.

Nếu cần **mutual authentication**, server cũng phải xác minh danh tính client theo phương thức được lựa chọn. Chỉ có chứng chỉ server không tự chứng minh client là ai.

### 4.2. Những thuộc tính cần phân biệt

| Thuộc tính | Ý nghĩa | Không tự có chỉ vì ECDH chạy thành công |
| --- | --- | --- |
| **Key secrecy** | Người quan sát không thể tính được khóa phiên trong threat model. | Sai cấu hình hoặc private key lộ có thể phá vỡ. |
| **Peer authentication** | Biết đã thiết lập với đúng chủ thể. | ECDH thuần không xác thực đối tác. |
| **Key confirmation** | Có bằng chứng phía kia cũng có đúng khóa/secret phiên thích hợp. | Cần bước xác nhận (ví dụ finished MAC) theo giao thức. |
| **Forward secrecy** | Lộ khóa danh tính dài hạn sau này không tự giải mã được những phiên trước đó. | Cần giao thức dùng bí mật tạm thời và xóa đúng; không chỉ gắn nhãn “ephemeral”. |
| **Replay resistance** | Ngăn dùng lại thông điệp bắt tay hoặc dữ liệu cũ theo chính sách. | Cần độ mới, state/sequence/nonce và kiểm tra protocol. |
| **Downgrade resistance** | Ngăn ép hai bên dùng phiên bản/thuật toán yếu hơn. | Cần xác thực các tham số đã thương lượng. |
| **Channel/identity binding** | Khóa được gắn với đúng danh tính, vai trò, transcript và giao thức. | Cần thông tin ngữ cảnh và xác thực thích hợp. |

**Key confirmation** khác **peer authentication**: một kẻ tấn công MITM cũng có thể chứng minh rằng **họ** biết khóa mà họ tự thiết lập với nạn nhân. Vì vậy một MAC xác nhận khóa chưa đủ chứng minh danh tính người được kỳ vọng nếu không có cơ chế xác thực riêng.

### 4.3. Forward secrecy không phải khẩu hiệu

Một giao thức dùng cặp khóa **ECDHE tạm thời** có thể đạt **forward secrecy** nếu các điều kiện về thiết kế, xác thực, xóa bí mật tạm thời và lưu trữ dữ liệu phiên được đáp ứng. Khi private key danh tính dài hạn bị lộ về sau, kẻ tấn công đã ghi lại các transcript cũ thường không suy ra được những khóa phiên đã được thiết lập an toàn từ bí mật ephemeral đã hủy.

Ngược lại, nếu dùng cùng một cặp khóa DH tĩnh cho mọi phiên hoặc ghi lại shared secret/khóa phiên vào log, việc lộ bí mật tương ứng có thể làm lộ nhiều phiên. **Lộ private key tạm thời khi phiên đang diễn ra** vẫn nguy hiểm; forward secrecy không bảo đảm chống mọi dạng xâm nhập.

## 5. Thiết lập khóa trong các giao thức thực tế

### 5.1. TLS 1.3

**TLS 1.3** dùng một quá trình bắt tay đã chuẩn hóa, trong đó các bên thỏa thuận tham số, sử dụng cơ chế trao đổi khóa như **(EC)DHE** hoặc các chế độ PSK được giao thức cho phép, rồi dùng key schedule/KDF để tạo bí mật cho nhiều giai đoạn và chiều truyền. Xác thực server thường dùng **chứng chỉ và chữ ký số**; client authentication là tùy chọn theo cấu hình.

Một thư viện TLS đúng có nhiệm vụ quản lý transcript, xác nhận Finished, các khóa traffic, thứ tự thông điệp và những kiểm tra bảo mật khác. Ứng dụng **không nên tự thay handshake TLS bằng vài dòng X25519 rồi tự dùng AES-GCM**, vì dễ bỏ sót xác thực, chống downgrade, key separation hoặc replay.

**Lưu ý:** Thuộc tính của một phiên TLS 1.3 còn phụ thuộc chế độ handshake; những trường hợp như PSK-only hoặc **0-RTT early data** có điều kiện an toàn/chống replay khác so với phiên DHE thông thường. Không mặc định mọi kết nối TLS 1.3 có cùng bảo đảm đối với toàn bộ dữ liệu.

### 5.2. HPKE – Hybrid Public Key Encryption

**HPKE (RFC 9180)** phối hợp **KEM, KDF và AEAD** để bảo vệ nội dung cho bên nhận có public key phù hợp. Một bên có thể đóng gói shared secret rồi dẫn xuất khóa mã hóa theo cơ chế chuẩn.

**HPKE base mode không tự xác thực danh tính người gửi**; các mode hoặc lớp giao thức khác cung cấp thuộc tính xác thực phù hợp khi cần. Public key của người nhận vẫn phải được xác thực; việc thấy một public key trên mạng không đủ bảo đảm thuộc đúng bên mong muốn.

### 5.3. KMS và phân phối DEK

Khi nhiều ứng dụng cần truy cập cùng dữ liệu mã hóa, không nhất thiết phải chạy ECDH giữa từng cặp workload. **KMS** có thể sinh **DEK** và bảo vệ DEK dưới **KEK** qua **envelope encryption**:

~~~text
Ứng dụng A: DEK -> AES-GCM mã hóa dữ liệu
                     |
                     +-- wrapped DEK lưu cùng ciphertext
                             |
                       KMS/HSM giữ KEK
                             |
Ứng dụng B (được cấp quyền): unwrap DEK -> AES-GCM giải mã
~~~

Đây là một phương án **cấp phát và bảo vệ khóa dữ liệu**, không đồng nghĩa với thỏa thuận ECDH. Hệ thống phải cấp quyền unwrap/decrypt theo danh tính workload, tenant, key ID, mục đích sử dụng và chính sách KMS. **Non-exportable KEK** giúp giữ key material ở ranh giới KMS/HSM nhưng không ngăn người có quyền unwrap trái phép lấy được DEK trong những API trả về DEK dạng rõ.

### 5.4. PSK và khóa lâu dài

**Pre-Shared Key** có thể phù hợp ở một số môi trường có cơ chế cấp phát bí mật an toàn. Tuy nhiên, một PSK chung cho nhiều node/tenant tạo phạm vi ảnh hưởng lớn khi bị lộ. Cần thiết kế quyền, định danh, hạn dùng, rotate/revoke và tránh dùng cùng PSK cho nhiều giao thức không được phân tách miền.

Không lấy mật khẩu người dùng rồi coi trực tiếp đó là PSK entropy cao. Nếu thiết lập khóa dựa trên mật khẩu, cần sử dụng **giao thức hoặc KDF phù hợp với threat model**, có bảo vệ trước tấn công đoán mật khẩu và quy tắc xác thực rõ ràng.

## 6. Ví dụ Java 17: X25519 + HKDF + AES-GCM

Ví dụ này minh họa hai bên dùng **JCA** để sinh cặp khóa X25519, tính shared secret, dẫn xuất một khóa AES-256 bằng **HKDF-HMAC-SHA-256** rồi mã hóa/giải mã một thông điệp bằng AES-GCM.

**Giới hạn quan trọng:** Đoạn mã **không xác thực public key hoặc danh tính Alice/Bob, không cung cấp key confirmation giao thức, không chống MITM/replay và chưa triển khai key schedule hoàn chỉnh**. Nó chỉ dạy phần **key agreement + KDF**, không phải giao thức bắt tay dùng trực tiếp ở production.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class KeyEstablishmentDemo {
    // Định dạng transcript cố định, có độ dài trường để tránh nối mơ hồ.
    private static void hashField(MessageDigest hash, byte[] bytes) {
        hash.update(ByteBuffer.allocate(4).putInt(bytes.length).array());
        hash.update(bytes);
    }

    private static byte[] transcriptHash(PublicKey alice, PublicKey bob)
            throws Exception {
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        hashField(sha256, "demo-v1|X25519|Alice|Bob"
                .getBytes(StandardCharsets.UTF_8));
        hashField(sha256, alice.getEncoded());
        hashField(sha256, bob.getEncoded());
        return sha256.digest();
    }

    private static SecretKey deriveAesKey(
            PrivateKey ownPrivate, PublicKey peerPublic,
            byte[] salt, byte[] transcript) throws Exception {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ownPrivate);
        agreement.doPhase(peerPublic, true);
        byte[] sharedSecret = agreement.generateSecret();

        try {
            // HKDF-Extract(salt, sharedSecret)
            Mac extract = Mac.getInstance("HmacSHA256");
            extract.init(new SecretKeySpec(salt, "HmacSHA256"));
            byte[] prk = extract.doFinal(sharedSecret);
            try {
                // HKDF-Expand cho đúng 32 byte (= một block SHA-256).
                Mac expand = Mac.getInstance("HmacSHA256");
                expand.init(new SecretKeySpec(prk, "HmacSHA256"));
                expand.update(transcript); // info / context chung
                expand.update((byte) 0x01); // block counter của HKDF
                byte[] keyBytes = expand.doFinal();
                try {
                    return new SecretKeySpec(keyBytes, "AES");
                } finally {
                    Arrays.fill(keyBytes, (byte) 0);
                }
            } finally {
                Arrays.fill(prk, (byte) 0);
            }
        } finally {
            Arrays.fill(sharedSecret, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();

        // Salt chung của handshake: không cần bí mật, nhưng
        // trong giao thức thật cần được ràng buộc/xác thực.
        byte[] salt = new byte[32];
        new SecureRandom().nextBytes(salt);
        byte[] transcript = transcriptHash(
                alice.getPublic(), bob.getPublic());

        SecretKey keyAlice = deriveAesKey(
                alice.getPrivate(), bob.getPublic(), salt, transcript);
        SecretKey keyBob = deriveAesKey(
                bob.getPrivate(), alice.getPublic(), salt, transcript);

        // Demo một thông điệp trong một chiều. Mỗi lần encrypt cùng
        // khóa AES-GCM phải dùng nonce khác theo chính sách an toàn.
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] message = "Hoa don: 4200 VND"
                .getBytes(StandardCharsets.UTF_8);
        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, keyAlice,
                new GCMParameterSpec(128, nonce));
        encryptor.updateAAD(transcript);
        byte[] ciphertextAndTag = encryptor.doFinal(message);

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, keyBob,
                new GCMParameterSpec(128, nonce));
        decryptor.updateAAD(transcript);
        byte[] recovered = decryptor.doFinal(ciphertextAndTag);
        System.out.println(new String(recovered, StandardCharsets.UTF_8));

        // Chỉ dọn các mảng byte hiện có ở đây; không bảo đảm
        // đã xóa mọi bản sao key/secret trong JVM/provider.
        Arrays.fill(message, (byte) 0);
        Arrays.fill(recovered, (byte) 0);
        Arrays.fill(salt, (byte) 0);
    }
}
~~~

### 6.1. Cần hiểu đúng ví dụ

- **X25519** dùng **private key của một bên + public key bên kia** để tạo shared secret. Trong đoạn mã, cả hai tính được vật liệu giống nhau nếu không có người thay khóa công khai.
- **HKDF** không trực tiếp biến một username thành khóa. Nó nhận **shared secret** và context/salt đúng, rồi tạo **32 byte** cho AES-256; API mẫu chỉ triển khai **một block HKDF-Expand** và không phải HKDF tổng quát cho đầu ra bất kỳ.
- **Transcript hash** giúp gắn kết dữ liệu dẫn xuất với phiên bản/roles/public keys trong demo; **nó không xác thực danh tính** vì public key chưa được ký hay chứng thực.
- **AES-GCM** cung cấp bảo mật và kiểm tra tính toàn vẹn đối với bản mã, dùng nonce 96 bit và tag 128 bit; **không được tái dùng cùng key + nonce**.
- Một giao thức hai chiều thực tế cần **khóa riêng theo từng chiều** và quy trình quản lý nonce, key update, xác thực đối tác và key confirmation. Không sao chép mô hình **một khóa cho hai chiều** từ demo vào production.
- Không log private key, shared secret, PRK, DEK hay token phiên. Phần xóa mảng không bảo đảm mọi bản sao bí mật trong JVM đã được hủy.
- API/provider Java 17 cần hỗ trợ X25519; môi trường có chính sách mật mã khác nhau có thể có ràng buộc tương thích riêng.

### 6.2. Từ demo đến thiết kế production

Để biến mô hình trên thành một giải pháp dùng thực tế, cần bổ sung **giao thức đã chuẩn hóa** thay vì tự ghép các bước:

1. **Xác thực peer** bằng chứng chỉ/chữ ký số/PSK và nguồn trust phù hợp.
2. **Ghim thuật toán và phiên bản**, bảo vệ toàn bộ transcript quan trọng trước downgrade và cross-protocol confusion.
3. **Kiểm tra public key và secret hợp lệ**, xử lý lỗi decapsulation/agreement an toàn.
4. **Dẫn xuất nhiều khóa theo nhãn riêng biệt** bằng KDF với context được định nghĩa không mơ hồ.
5. **Key confirmation** và kiểm tra thông điệp bắt tay cuối theo giao thức.
6. **Chống replay**, thiết kế nonce/counter cho dữ liệu ứng dụng, giới hạn dữ liệu theo key và key update.
7. **Xử lý retry, đóng kết nối, lỗi xác thực, timeout** và hủy bí mật phiên khi không còn dùng.

Với lưu lượng API/service thông thường, sử dụng **TLS 1.3 được cấu hình và xác minh đúng** thường an toàn, dễ quản trị và có tính liên thông hơn tự thiết kế protocol dựa trên X25519.

## 7. Key establishment và vòng đời khóa mật mã

Không phải tất cả khóa tham gia handshake có cùng thời gian tồn tại:

| Thành phần | Vai trò | Vòng đời điển hình |
| --- | --- | --- |
| **Identity signing key** | Ký transcript/chứng chỉ hoặc chứng minh danh tính. | Dài hạn, bảo vệ bằng KMS/HSM khi phù hợp; rotate, revoke và audit. |
| **Ephemeral ECDH private key** | Đóng góp bí mật cho một phiên/handshake. | Tạo mới theo giao thức, không chia sẻ, xóa sau khi hoàn tất và hết nhu cầu. |
| **Shared secret ECDH/KEM** | Vật liệu đầu vào cho KDF. | Chỉ tồn tại đủ lâu để dẫn xuất; không lưu vào log/backup. |
| **Session traffic keys** | AES-GCM/ChaCha20-Poly1305/HMAC theo giao thức. | Ngắn hạn, tách theo chiều/purpose; key update theo quy tắc. |
| **DEK dữ liệu lâu dài** | Mã hóa bản ghi/tệp dưới dạng lưu trữ. | Có key ID/phiên bản, được bọc bằng KEK; phải giữ khi còn bản mã cần giải mã. |
| **KEK hoặc KMS key** | Wrap/unwrap DEK, quản lý truy cập. | Theo chính sách quản trị, xoay vòng và kiểm kê bản sao/backup trước hủy. |

### 7.1. Sinh và cấp phát

Khóa tạm thời, DEK, nonce, PSK và private key danh tính phải được tạo bằng **CSPRNG/KMS/HSM phù hợp**. Một key pair được sinh đúng nhưng public key bị trao đổi qua nguồn không tin cậy vẫn có thể dẫn đến MITM.

Gắn mục đích khóa (**key usage**), owner, tenant, môi trường, phiên bản và thuật toán cho đối tượng quản lý khóa. Không tự tái sử dụng private key Ed25519 làm private key X25519 hoặc dùng chung một secret cho giao thức không được phân tách miền.

### 7.2. Sử dụng và giới hạn

Thiết lập thành công không cho phép dùng key không giới hạn. AEAD như AES-GCM có **quy tắc nonce duy nhất dưới mỗi khóa** và giới hạn số lượt/dung lượng theo chế độ. Giao thức phải đặt chính sách **key update, lifetime, sequence number** và giới hạn bộ nhớ/khả năng truy cập của workload.

**KMS/HSM non-exportable** giảm rủi ro xuất key material nhưng không ngăn lạm dụng API Sign/Decrypt/Unwrap nếu chính sách quyền rộng. Audit cả hoạt động tạo khóa, ký/xác thực danh tính, phân quyền, rotate và những hành động bất thường.

### 7.3. Xoay vòng, thu hồi và hủy

- **Xoay identity key:** tạo khóa mới, cập nhật chứng chỉ/trust store, chuyển bên ký, đánh giá các phiên đang hoạt động và cửa sổ tin cậy.
- **Key update của phiên:** tạo khóa traffic mới qua key schedule của giao thức; không tự phát minh quy tắc update hoặc reset nonce.
- **Thu hồi:** ngừng tin private key/chứng chỉ/PSK bị nghi lộ, ngắt phiên hoặc yêu cầu bắt tay lại theo quy trình sự cố.
- **Hủy khóa tạm thời:** loại bỏ ephemeral private key và shared secret khi không còn cần, theo khả năng của runtime/provider.
- **Hủy KEK/DEK:** chỉ sau khi rà soát bản mã, snapshots, backup, replica và yêu cầu lưu giữ; nếu hủy nhầm có thể mất dữ liệu vĩnh viễn.

**Chỉ thay khóa danh tính không tự động bảo vệ bản mã lịch sử** nếu những session key hoặc DEK đã bị lộ. Khi một phiên bị xâm nhập, cần đánh giá những dữ liệu đã truyền/lưu và khả năng mã hóa lại hoặc thu hồi phiên thích hợp.

## 8. Ví dụ kiến trúc: kết nối hai microservice và chia sẻ DEK

Giả sử **Order Service** gọi **Billing Service** để tạo hóa đơn, đồng thời hai dịch vụ sử dụng một số bản ghi đã mã hóa trong kho lưu trữ.

**Mục tiêu A – Kênh truyền bảo mật:**

1. Hai service sử dụng **TLS 1.3** qua kết nối được cấu hình đúng.
2. Billing Service chứng minh danh tính qua chứng chỉ server và chữ ký trong handshake; nếu cần xác thực hai chiều thì áp dụng **mTLS** theo policy.
3. Giao thức thiết lập traffic keys ngắn hạn từ key schedule và thực hiện bảo vệ dữ liệu kết nối bằng AEAD.
4. Ứng dụng tiếp tục kiểm tra **workload identity, quyền tenant và nghiệp vụ**, không coi TLS là toàn bộ authorization.
5. Chứng chỉ/private key dài hạn có vòng đời riêng; khóa traffic được quản lý theo giao thức.

**Mục tiêu B – Bảo vệ dữ liệu lưu trữ:**

1. Order Service dùng **DEK** để mã hóa bản ghi bằng AES-GCM, gắn nonce và key ID/phiên bản.
2. **KMS** bảo vệ DEK dưới **KEK**, lưu wrapped DEK cùng dữ liệu.
3. Billing Service chỉ unwrap/giải mã nếu danh tính workload và chính sách tenant cho phép.
4. Khi rotate KEK, có thể **rewrap** DEK; khi DEK bị lộ, cần đánh giá **thay DEK và mã hóa lại bản mã**.
5. Nhật ký ghi actor, key ID, phiên bản, thời điểm và kết quả, nhưng không ghi DEK/KEK dạng rõ.

**Hai mục tiêu không thay thế cho nhau.** TLS bảo vệ dữ liệu **trên đường truyền**, còn envelope encryption bảo vệ dữ liệu **khi lưu** theo mô hình được thiết kế. Dùng key agreement để tạo traffic key không tự khiến DEK lưu trữ được phân quyền đúng; dùng KMS để bọc DEK cũng không tự xác thực các đối tác trên mạng.

## 9. Threat model và các lỗi thường gặp

| Sai lầm | Rủi ro | Biện pháp |
| --- | --- | --- |
| Dùng X25519/ECDH nhưng không xác thực public key | MITM thiết lập hai phiên độc lập và có thể đọc/sửa dữ liệu. | TLS/Noise/giao thức chuẩn có chứng chỉ, chữ ký hoặc PSK xác thực. |
| Dùng trực tiếp shared secret làm AES key | Thiếu key schedule, domain separation và quản lý context. | Dùng KDF chuẩn phù hợp, ví dụ HKDF trong protocol được đánh giá. |
| Tự nối chuỗi để tạo HKDF info mà không có encoding rõ | Nhầm vai trò, ngữ cảnh hoặc hai transcript khác nhau có cùng biểu diễn. | Canonical encoding, nhãn và trường độ dài theo giao thức. |
| Dùng cùng khóa traffic cho hai chiều và reset nonce | Có thể tạo reuse key + nonce trong AEAD. | Tách khóa/nonce space theo chiều và kiểm soát sequence/key update. |
| Tin tưởng key ID/kid do đối tác tự khai báo | Chọn nhầm hoặc chấp nhận khóa giả. | Trust store và danh tính đã ghim theo chính sách. |
| Không kiểm tra thuật toán được thỏa thuận | Kẻ tấn công có thể gây downgrade hoặc confusion. | Xác thực transcript, kiểm tra allowlist thuật toán và version. |
| Không kiểm tra shared secret không hợp lệ | Có thể dẫn xuất khóa từ kết quả yếu/không phù hợp. | Để provider/giao thức kiểm tra, từ chối trường hợp không hợp lệ. |
| Nhầm key confirmation với xác thực danh tính | Chấp nhận MITM có khả năng xác nhận khóa tự tạo. | Xác thực peer riêng, sau đó confirmation theo giao thức. |
| Xem mọi phiên có “ephemeral” là forward secret | Bỏ sót lưu trữ secret, chế độ handshake và xâm nhập lúc phiên hoạt động. | Đánh giá thuộc tính của toàn protocol, thực thi xóa secret. |
| Dùng PSK/password chung cho nhiều tenant | Lộ một bí mật ảnh hưởng nhiều tenant và khó thu hồi. | Tách secret theo mục đích, tenant, môi trường và vòng đời. |
| Non-exportable KMS key nhưng mở quyền unwrap rộng | Kẻ tấn công có thể lấy DEK thông qua API hợp lệ. | Least privilege, identity, encryption context và audit. |
| Rotate KEK rồi tuyên bố đã thay DEK bị lộ | Dữ liệu cũ vẫn giải mã được bằng DEK đã lộ. | Thay DEK và re-encrypt theo phạm vi ảnh hưởng. |
| Hủy private key/KEK trước khi xử lý dữ liệu phụ thuộc | Không thể khôi phục các bản mã cần giữ. | Kiểm kê phụ thuộc, backup, retention và thử restore trước hủy. |
| Chỉ test hai bên có cùng key | Không kiểm chứng MITM/replay/identity/downgrade. | Kiểm thử protocol, trust policy và các trường hợp tấn công. |

## 10. Kiểm toán và tiêu chí chấp nhận thiết kế

Một bản thiết kế key establishment có thể được rà soát theo checklist sau:

1. **Algorithm/protocol:** giao thức và các thuật toán key agreement/KEM/KDF/AEAD đã được chọn theo chính sách và tương thích nền tảng chưa?
2. **Authentication:** public key/certificate/PSK của đối tác được xác thực từ nguồn nào? Có cần xác thực hai chiều không?
3. **Context binding:** transcript có gắn thuật toán, version, vai trò, identity, key ID và ứng dụng/mục đích không?
4. **Key separation:** các khóa cho hai chiều, MAC, encryption và các chức năng khác được dẫn xuất riêng theo quy tắc nào?
5. **Freshness và replay:** mỗi phiên có dữ liệu mới nào; ai quản lý trạng thái chống phát lại và expiration?
6. **Key confirmation:** bên nhận biết phía kia có đúng khóa phiên bằng cơ chế nào?
7. **Lifetime:** khóa ephemeral, session key, identity key, DEK, KEK có thời hạn, giới hạn phép toán và quy trình xoay vòng nào?
8. **Failure handling:** xử lý public key sai, shared secret không hợp lệ, lỗi signature/Finished, hết hạn và đổi trust policy như thế nào?
9. **Key storage:** những secret nào xuất hiện trong RAM/backup/log; có hỗ trợ KMS/HSM và non-exportable hay không?
10. **Audit:** ghi key ID, actor, thao tác, algorithm, kết quả, thời gian và lỗi an toàn, nhưng **không log shared secret/private key/DEK/KEK**.
11. **Incident response:** nếu chứng chỉ, PSK, RNG, private key hoặc workload credential bị lộ, có khả năng thu hồi và thay khóa, cập nhật trust/consumer không?
12. **Recovery:** dữ liệu lưu lâu dài phụ thuộc khóa nào, có kiểm tra bản sao/khả năng giải mã trước hủy không?

Đối với triển khai liên dịch vụ, **TLS 1.3/mTLS qua thư viện tiêu chuẩn** thường là lựa chọn ưu tiên. Nếu cần giao thức mã hóa phía ứng dụng hoặc phân phối khóa tới các client không có TLS trực tiếp, chọn **giao thức được chuẩn hóa/đánh giá** và tài liệu rõ về identity, KDF, nonce, metadata và trách nhiệm vận hành.

## 11. Câu hỏi tự kiểm tra

1. **Key establishment** khác **key generation** ở mục tiêu nào?
2. **Key transport**, **key agreement** và **KEM** khác nhau về cách tạo và chuyển vật liệu khóa ra sao?
3. Vì sao **X25519/ECDH thuần** không tự ngăn man-in-the-middle?
4. Shared secret sau ECDH có nên dùng trực tiếp làm khóa AES-GCM không? Vai trò của **HKDF** là gì?
5. Một transcript hash có thể giúp ràng buộc ngữ cảnh, nhưng vì sao **không tự xác thực danh tính**?
6. **Key confirmation** khác **peer authentication** thế nào?
7. Điều kiện nào giúp một giao thức ECDHE có **forward secrecy**? Khi private key tạm thời bị lộ ngay trong phiên thì sao?
8. Vì sao khóa AES-GCM cần được tách theo chiều hoặc thiết kế không gian nonce an toàn?
9. **TLS 1.3**, **HPKE** và **KMS envelope encryption** được dùng cho những bài toán khác nhau thế nào?
10. Nếu chỉ thay KEK trong KMS khi DEK đã lộ, dữ liệu cũ có được bảo vệ lại không?
11. Khi hủy private key dùng giải mã hoặc DEK, phải kiểm tra những dữ liệu và bản sao nào?
12. Có thể chứng minh handshake an toàn chỉ bằng một unit test cho thấy hai bên tạo ra cùng 32 byte không?

**Ghi nhớ:** **Key establishment** là quá trình các bên có được vật liệu khóa chung theo một cơ chế an toàn, bao gồm **truyền khóa, thỏa thuận khóa hoặc KEM**. Một thiết kế đúng phải giải quyết đồng thời **bí mật khóa, xác thực đối tác, KDF và phân tách khóa, ngữ cảnh giao thức, chống replay, giới hạn sử dụng và vòng đời khóa**. Khi vận hành, hãy ưu tiên giao thức chuẩn, dùng **KMS/HSM cho khóa dài hạn hoặc DEK/KEK khi phù hợp**, thực thi phân quyền và kiểm toán, đồng thời có phương án xoay vòng, thu hồi và hủy không làm mất dữ liệu ngoài ý muốn.
