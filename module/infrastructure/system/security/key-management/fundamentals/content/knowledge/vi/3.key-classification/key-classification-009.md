# Key agreement key — Khóa dùng để thỏa thuận khóa chung

## 1. Key agreement key là gì?

**Key agreement key** là khóa mật mã được sử dụng trong một **cơ chế thỏa thuận khóa** (*key agreement*): hai hoặc nhiều bên cùng tham gia tính ra bí mật chung, trong khi **không cần gửi trực tiếp bí mật chung đó qua đường truyền**. Trong phạm vi bài này, ta tập trung vào thỏa thuận khóa giữa hai bên bằng mật mã bất đối xứng, như **Diffie–Hellman (DH)**, **Elliptic-Curve Diffie–Hellman (ECDH)** và **X25519**.

Đây là một loại khóa quan trọng trong chương **Phân loại key** của quản lý khóa mật mã. Cách phân loại dựa trên **mục đích sử dụng**: khóa này tham gia thiết lập bí mật chung, khác với khóa dùng để ký số, mã hóa dữ liệu trực tiếp hoặc bọc một khóa dữ liệu đã tồn tại. Trong một giao thức hoàn chỉnh, bí mật chung thường được đưa qua **hàm dẫn xuất khóa (KDF)** để tạo khóa đối xứng dùng cho AES-GCM, ChaCha20-Poly1305 hoặc khóa bảo vệ dữ liệu khác.

Ví dụ, trình duyệt và máy chủ cần thiết lập kênh HTTPS. Thay vì máy chủ chọn một khóa AES rồi gửi cho trình duyệt, hai bên có thể dùng cơ chế thỏa thuận khóa tạm thời để cùng tính ra một bí mật, sau đó dẫn xuất các khóa bảo vệ phiên truyền. **TLS 1.3** sử dụng các cơ chế trao đổi khóa như (EC)DHE và kết hợp chúng với xác thực, lịch dẫn xuất khóa và kiểm tra toàn vẹn thông điệp bắt tay.

> **Ý chính:** Key agreement key thường là **khóa riêng và khóa công khai tham gia thỏa thuận khóa**. Bí mật chung được tạo ra qua phép toán thỏa thuận là **kết quả trung gian**, không nên mặc nhiên coi đó là khóa AES sẵn dùng. Phải xét thêm xác thực đối tác, KDF, ngữ cảnh giao thức và vòng đời khóa.

### Một giao thức thỏa thuận khóa cần giải quyết ba bài toán

1. **Bí mật:** Hai bên hợp lệ có thể tính bí mật chung mà người chỉ nghe lén các giá trị công khai khó suy ra.
2. **Xác thực đối tác:** Hai bên có đủ bằng chứng rằng khóa công khai mình nhận thực sự thuộc về đối tác dự kiến, hoặc đã được ràng buộc đúng với phiên và danh tính; nếu thiếu bước này, giao thức có thể bị tấn công *man-in-the-middle*.
3. **Tạo khóa cho từng mục đích:** Bí mật chung được dẫn xuất thành khóa mã hóa, khóa xác thực hoặc các khóa theo hướng truyền khác nhau với ngữ cảnh thích hợp.

**Chỉ thực hiện DH/ECDH không tự động giải quyết cả ba bài toán.** Nó chủ yếu đóng góp cho việc tạo bí mật chung; các thuộc tính còn lại đến từ thiết kế giao thức hoàn chỉnh.

## 2. Các thuật ngữ cần nắm

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Private agreement key** | Giá trị bí mật mà một bên giữ riêng để tính kết quả thỏa thuận | Khóa riêng X25519 của client |
| **Public agreement key** | Giá trị công khai tương ứng được gửi cho bên còn lại | Khóa công khai X25519 của client |
| **Key pair** | Cặp khóa riêng/công khai thuộc cùng một thuật toán thỏa thuận | Cặp khóa ECDH |
| **Key establishment** | Tên chung cho các cơ chế giúp các bên có khóa sử dụng chung | Key agreement hoặc key transport |
| **Key agreement** | Các bên đóng góp vào quá trình tính bí mật chung theo một giao thức | ECDHE trong bắt tay TLS |
| **Shared secret (Z)** | Kết quả bí mật trung gian do hai bên tính ra | Giá trị trả về từ X25519 |
| **KDF / HKDF** | Cơ chế dẫn xuất một hay nhiều khóa có mục đích rõ ràng từ vật liệu đầu vào | HKDF-SHA-256 với transcript của phiên |
| **Ephemeral key** | Khóa tạm thời tạo cho một phiên hoặc một đợt bắt tay, thường bị xóa sau khi dùng | Cặp X25519 mới cho một phiên |
| **Static key** | Khóa có thời gian sử dụng dài hơn, tồn tại qua nhiều phiên | Khóa ECDH dài hạn của một thiết bị |
| **Key confirmation** | Bằng chứng một bên đã tính ra đúng khóa phiên dự kiến | Kiểm tra xác thực thông điệp kết thúc bắt tay |
| **Forward secrecy** | Mức bảo vệ các phiên cũ nếu khóa xác thực dài hạn bị lộ về sau, với điều kiện giao thức và vận hành phù hợp | TLS 1.3 với (EC)DHE và xóa bí mật phiên |

Phân biệt **key agreement key** với **session key**: cặp khóa bất đối xứng dùng để thỏa thuận là *đầu vào của quá trình thiết lập khóa*; session key thường là **khóa đối xứng được dẫn xuất** sau bước thỏa thuận. Cũng cần phân biệt **key agreement key** với **key-encryption key (KEK)**: KEK thường dùng để bọc/giải bọc khóa dữ liệu (DEK), còn agreement key giúp các bên thiết lập bí mật từ đó có thể tạo ra một KEK hoặc khóa phiên.

### Ai có thể biết loại vật liệu nào?

| Vật liệu | Bên A | Bên B | Người nghe lén |
| --- | --- | --- | --- |
| Private key của A | Phải giữ bí mật | Không nhận được | Không biết |
| Public key của A | Biết | Có thể nhận | Có thể quan sát |
| Private key của B | Không biết | Phải giữ bí mật | Không biết |
| Public key của B | Có thể nhận | Biết | Có thể quan sát |
| Shared secret Z | Tính được | Tính được | Không thể tính được khi giả định an toàn của thuật toán được đáp ứng |
| Khóa đối xứng dẫn xuất | Tính được theo vai trò/chính sách | Tính được theo vai trò/chính sách | Không thể tính được nếu Z vẫn bí mật và KDF đúng |

Đây là mô hình khái niệm của một **phiên thỏa thuận khóa không bị xâm phạm**. Nếu kẻ tấn công thay khóa công khai hoặc lấy được private key phù hợp, kết luận bảo mật có thể thay đổi.

## 3. Cơ chế hoạt động: từ public key đến shared secret

### 3.1. Trực giác Diffie–Hellman

Trong DH hữu hạn trường, hai bên sử dụng tham số nhóm công khai, gồm phần tử sinh **g** và mô-đun **p**. A chọn bí mật **a**, B chọn bí mật **b**:

- A gửi giá trị công khai **A = g^a mod p**.
- B gửi giá trị công khai **B = g^b mod p**.
- A tính **Z = B^a mod p**.
- B tính **Z = A^b mod p**.

Kết quả hai phía bằng nhau vì **(g^b)^a = (g^a)^b = g^(ab)** trong nhóm thích hợp. Người nghe lén thấy A, B và các tham số công khai nhưng không dễ suy ra Z nếu bài toán toán học tương ứng đủ khó, tham số và cách sử dụng được chọn đúng.

Công thức trên chỉ nhằm minh họa. **Không dùng số nguyên nhỏ, nhóm tự thiết kế hoặc trực tiếp triển khai DH bằng phép lũy thừa mẫu để bảo vệ hệ thống thật.** Cần dùng nhóm chuẩn, thư viện được kiểm tra và các bước xác thực/kiểm tra hợp lệ do giao thức quy định.

### 3.2. ECDH và X25519

**ECDH** áp dụng ý tưởng trên nhóm điểm đường cong elliptic. Nếu A có số bí mật **dA** và B có **dB**, với điểm sinh công khai **G**:

- A công bố **QA = dA · G**; B công bố **QB = dB · G**.
- A tính **dA · QB**; B tính **dB · QA**.
- Hai phép toán thu được cùng một điểm khi tuân thủ điều kiện của nhóm.

Từ kết quả ECDH, giao thức thực hiện bước xử lý và dẫn xuất khóa phù hợp, thay vì đưa thẳng điểm đường cong vào thuật toán mã hóa.

**X25519** là hàm thỏa thuận khóa dựa trên Curve25519 với cách biểu diễn và quy tắc xử lý riêng. X25519 được hỗ trợ trong nhiều giao thức hiện đại và có thư viện chuẩn trên các nền tảng phổ biến. X25519 không phải thuật toán ký số: **Ed25519** là một thuật toán chữ ký số khác; không nên xem hai loại khóa là hoán đổi tùy tiện dù chúng có liên quan về họ đường cong.

Một yêu cầu triển khai quan trọng của X25519 là xử lý đúng kết quả shared secret **toàn byte 0 (all-zero)** và các trường hợp public key bất thường theo tài liệu của thư viện/giao thức. Với các biến thể ECDH khác, việc kiểm tra điểm công khai thuộc đường cong, đúng nhóm và hợp lệ là rất quan trọng; ưu tiên dùng API mật mã chuẩn thay vì tự xác thực toán học.

### 3.3. Chuỗi hoạt động của một phiên thỏa thuận khóa

~~~mermaid
sequenceDiagram
    participant A as Bên A / Client
    participant B as Bên B / Server
    A->>A: Tạo cặp khóa agreement tạm thời (a, QA)
    B->>B: Tạo cặp khóa agreement tạm thời (b, QB)
    A->>B: Gửi QA và thông tin giao thức
    B->>A: Gửi QB và bằng chứng xác thực phù hợp
    Note over A,B: Kiểm tra danh tính, tham số và ràng buộc transcript
    A->>A: Tính ZA = Agreement(a, QB)
    B->>B: Tính ZB = Agreement(b, QA)
    Note over A,B: ZA = ZB nếu hai bên dùng đúng khóa và tham số
    A->>A: KDF(Z, transcript, context) -> khóa theo vai trò
    B->>B: KDF(Z, transcript, context) -> khóa theo vai trò
    A->>B: Xác nhận bắt tay có bảo vệ
    B->>A: Xác nhận bắt tay có bảo vệ
    Note over A,B: Dùng khóa phiên để bảo vệ dữ liệu; xóa bí mật tạm thời
~~~

**Xác thực khóa công khai là điểm quyết định.** Nếu A nhận nhầm public key do kẻ tấn công đưa vào, A vẫn có thể tính được một shared secret, nhưng shared secret đó là với kẻ tấn công chứ không phải B. Việc hai bên có cùng Z chỉ chứng minh họ đã dùng các đầu vào tương ứng; **không tự chứng minh danh tính của đối tác**.

## 4. Key agreement khác key transport, encryption và digital signature ra sao?

| Loại/mục đích | Vai trò chính | Cơ chế/ví dụ | Khác biệt cần nhớ |
| --- | --- | --- | --- |
| **Key agreement key** | Cùng tạo bí mật chung | DH, ECDH, X25519 | Các bên tham gia tính Z theo giao thức |
| **Key transport key** | Bảo vệ việc chuyển một khóa do bên khác tạo | RSA-OAEP trong mô hình phù hợp | Khóa được tạo ở một phía rồi được vận chuyển có bảo vệ |
| **Data encryption key (DEK)** | Mã hóa dữ liệu thực tế | AES-GCM, ChaCha20-Poly1305 | Thường là khóa đối xứng dùng sau khi thiết lập khóa |
| **Key-encryption key (KEK)** | Bọc và giải bọc khóa khác | Key wrap hoặc KMS wrap/unwrap | Bảo vệ DEK hay khóa khác; không đồng nghĩa agreement key |
| **Signing key** | Tạo chữ ký số | ECDSA, Ed25519, RSA-PSS | Đảm bảo tính xác thực/toàn vẹn và hỗ trợ bằng chứng chữ ký theo giao thức |
| **Verification key** | Kiểm tra chữ ký | Public key ECDSA/Ed25519 | Để xác minh, thường có thể chia sẻ |
| **Authentication credential/key** | Chứng minh danh tính theo giao thức | Chứng thư, chữ ký, khóa xác thực | Có thể giúp xác thực public agreement key nhưng không thay chức năng thỏa thuận |

Một số thiết kế sử dụng cùng một cặp khóa cho nhiều chức năng, nhưng **tách khóa theo mục đích** thường giúp giảm tác động khi bị lộ và tránh những lỗi do dùng chung vật liệu khóa qua nhiều giao thức. Không giả định rằng khóa có thể ký cũng phù hợp để dùng ECDH hoặc ngược lại: **loại thuật toán, cách sinh khóa, ràng buộc chứng thư và API** phải cho phép đúng mục đích.

Ví dụ, trong TLS 1.3, chứng thư của máy chủ có thể dùng để **xác thực** phía máy chủ, còn cặp khóa (EC)DHE tạm thời được dùng để **thỏa thuận bí mật phiên**. Hai việc phối hợp với nhau nhưng không phải một.

## 5. Từ shared secret đến khóa đối xứng bằng KDF

### 5.1. Vì sao không dùng thẳng Z làm khóa AES?

Kết quả thỏa thuận **Z** là vật liệu bí mật đầu vào. Cách biểu diễn, độ dài và ngữ cảnh bảo mật của Z phụ thuộc thuật toán thỏa thuận khóa. Cần một **KDF** để:

1. Trích xuất và chuẩn hóa vật liệu khóa đầu vào theo thiết kế của KDF.
2. Dẫn xuất khóa có độ dài cần dùng, ví dụ 256 bit cho AES-256.
3. Tách khóa theo **hướng truyền** (A → B và B → A), **mục đích** (mã hóa, xác thực, bọc khóa) hoặc **phiên giao thức**.
4. Ràng buộc kết quả với thông tin của phiên: định danh giao thức/phiên bản, danh tính đã xác thực, transcript bắt tay, thuật toán và vai trò các bên khi giao thức yêu cầu.

Một lựa chọn phổ biến là **HKDF**, gồm hai bước khái niệm:

~~~text
PRK = HKDF-Extract(salt, Z)
K_A_to_B = HKDF-Expand(PRK, info="protocol|v1|A-to-B|AEAD", L=32)
K_B_to_A = HKDF-Expand(PRK, info="protocol|v1|B-to-A|AEAD", L=32)
~~~

Ở đây **salt không phải mật khẩu bí mật**; salt có thể công khai, nhưng cách tạo/chia sẻ và lựa chọn giá trị phải phù hợp đặc tả giao thức. Thông tin **info** dùng phân tách mục đích và nên gắn với ngữ cảnh phiên theo thiết kế. Hai bên phải dùng **cùng quy tắc mã hóa các trường**; tránh nối chuỗi không có cấu trúc làm nảy sinh cách hiểu mơ hồ.

**HKDF không thay thế xác thực đối tác.** Nếu kẻ tấn công có thể thay public key, KDF vẫn có thể sinh ra khóa “hợp lệ” giữa nạn nhân và kẻ tấn công. Tương tự, KDF không tự xử lý replay, chống hạ cấp thuật toán hoặc quản lý nonce của AEAD.

### 5.2. Tách khóa theo hướng và theo công dụng

Không nên sử dụng cùng một khóa dẫn xuất để mã hóa cả hai hướng truyền nếu giao thức cần nonce riêng và bộ đếm độc lập. Một thiết kế rõ ràng có thể dẫn xuất:

- **traffic_key_client_to_server** để bảo vệ dữ liệu chiều client → server;
- **traffic_key_server_to_client** để bảo vệ dữ liệu chiều server → client;
- **exporter_key**, **resumption_secret** hoặc khóa riêng cho một mục đích khác nếu giao thức định nghĩa.

Nếu dùng **AES-GCM** hoặc **ChaCha20-Poly1305**, vẫn cần đảm bảo quy tắc **nonce không được lặp với cùng khóa**. Việc thỏa thuận một shared secret an toàn **không làm việc tái sử dụng nonce trở nên an toàn**. Thiết kế xác thực và chống phát lại phải được giải quyết ở tầng giao thức.

## 6. Ví dụ Java: thỏa thuận bí mật bằng X25519

Đoạn minh họa sau dùng **Java 11+** và API chuẩn JCA/JCE. Hai phía nằm trong cùng một chương trình để dễ thấy rằng chúng tính ra cùng Z. Sau đó chương trình dùng một bước **HKDF-Extract và HKDF-Expand một block với HMAC-SHA-256** để lấy khóa 32 byte cho chiều A → B.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.InvalidKeyException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class KeyAgreementDemo {
    // Tính shared secret; trong giao thức thực phải xác thực public key đối tác.
    static byte[] agree(PrivateKey ownPrivate, PublicKey peerPublic)
            throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ownPrivate);
        agreement.doPhase(peerPublic, true);
        byte[] z = agreement.generateSecret();

        int nonZero = 0;
        for (byte value : z) {
            nonZero |= value & 0xff;
        }
        if (nonZero == 0) {
            Arrays.fill(z, (byte) 0);
            throw new InvalidKeyException("Invalid all-zero shared secret");
        }
        return z;
    }

    // HKDF-SHA-256 cho output dài đúng 32 byte (một block Expand).
    static byte[] hkdf32(byte[] z, byte[] salt, byte[] info)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance("HmacSHA256");
        hmac.init(new SecretKeySpec(salt, "HmacSHA256"));
        byte[] prk = hmac.doFinal(z); // Extract
        try {
            hmac.init(new SecretKeySpec(prk, "HmacSHA256"));
            hmac.update(info);
            hmac.update((byte) 1);
            return hmac.doFinal();   // Expand: T(1), 32 byte
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("X25519");
        gen.initialize(NamedParameterSpec.X25519);

        KeyPair alice = gen.generateKeyPair(); // khóa tạm của A
        KeyPair bob = gen.generateKeyPair();   // khóa tạm của B

        byte[] za = agree(alice.getPrivate(), bob.getPublic());
        byte[] zb = agree(bob.getPrivate(), alice.getPublic());

        // Salt công khai: hash khóa công khai theo thứ tự A rồi B.
        // Giao thức thực cần transcript được mã hóa rõ ràng, có xác thực.
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        sha256.update(alice.getPublic().getEncoded());
        sha256.update(bob.getPublic().getEncoded());
        byte[] salt = sha256.digest();

        byte[] info = "demo/v1|AES-256-GCM|A-to-B"
                .getBytes(StandardCharsets.UTF_8);
        byte[] keyA = hkdf32(za, salt, info);
        byte[] keyB = hkdf32(zb, salt, info);

        System.out.println("Cung shared secret: "
                + MessageDigest.isEqual(za, zb));
        System.out.println("Cung khoa phien: "
                + MessageDigest.isEqual(keyA, keyB));

        // Best effort: xóa bản sao byte[] do mã nguồn kiểm soát.
        Arrays.fill(za, (byte) 0);
        Arrays.fill(zb, (byte) 0);
        Arrays.fill(keyA, (byte) 0);
        Arrays.fill(keyB, (byte) 0);
    }
}
~~~

**Kết quả kỳ vọng:** chương trình in **true** cho cả hai phép so sánh. Nó không in shared secret hoặc session key, tránh tạo thói quen ghi vật liệu bí mật ra log.

**Ranh giới của ví dụ:** đây là một bài minh họa phép thỏa thuận và dẫn xuất khóa, **chưa phải giao thức truyền thông an toàn hoàn chỉnh**. Trong mạng thật, hai public key phải được **xác thực và ràng buộc vào phiên** (ví dụ thông qua một giao thức được chuẩn hóa như TLS), transcript và thuật toán đàm phán phải được bảo vệ, thông điệp phải chống phát lại, nonce AEAD phải quản lý đúng, và khóa tạm phải có vòng đời rõ ràng. Việc xóa mảng byte trong JVM chỉ là **best effort**; các bản sao bên trong provider/runtime có thể không được xóa hoàn toàn bằng cách đó. Thư viện và môi trường thực thi phải hỗ trợ X25519; không được tự thay bằng thuật toán khác chỉ vì API báo không hỗ trợ.

Trong ví dụ, hai phía trực tiếp trao public key tại chỗ; **nó không mô phỏng việc xác thực public key qua mạng**. Với hệ thống sản xuất, ưu tiên dùng thư viện giao thức như **TLS 1.3** thay vì tự ghép các bước mật mã thành một giao thức mới.

## 7. Static, ephemeral và forward secrecy

Key agreement key có thể được phân theo **thời gian tồn tại** và **mục đích**:

| Hình thức | Cách sử dụng | Lợi ích | Rủi ro/chú ý |
| --- | --- | --- | --- |
| **Static–static DH/ECDH** | Hai bên dùng cặp khóa dài hạn | Dễ xác định danh tính theo khóa đã phân phối, một số hệ thống thiết bị dùng được | Lộ khóa dài hạn có thể ảnh hưởng nhiều phiên; không tự có forward secrecy |
| **Ephemeral–ephemeral (DHE/ECDHE)** | Mỗi bên tạo khóa tạm cho phiên | Hỗ trợ forward secrecy khi giao thức xác thực đúng và bí mật tạm được xóa | Cần xác thực public key tạm, xử lý chống MITM và replay |
| **Static–ephemeral** | Một phía dùng khóa dài hạn, phía kia tạo khóa tạm | Có thể hợp với giao thức cụ thể, giúp một bên có định danh ổn định | Thuộc tính bảo mật phụ thuộc toàn bộ giao thức; không mặc định có forward secrecy |
| **Hybrid/đa thành phần** | Kết hợp nhiều shared secret theo KDF chuẩn hóa | Có thể đáp ứng yêu cầu chuyển đổi thuật toán hoặc nâng mức bảo vệ | Cần đặc tả kết hợp, transcript và kiểm tra lỗi đúng; không ghép tùy tiện |

### Forward secrecy thực sự yêu cầu gì?

**Forward secrecy** nhằm bảo vệ bí mật của những phiên trước đó ngay cả khi **khóa xác thực dài hạn** về sau bị lộ. Cơ chế ECDHE với private key **tạm thời, độc lập theo phiên** là thành phần quan trọng, nhưng không đủ nếu ứng dụng lưu bí mật tạm lâu dài hoặc giao thức không xác thực đúng. Muốn có thuộc tính này, cần:

- Dùng cơ chế thỏa thuận khóa tạm thời trong **giao thức đã được phân tích bảo mật**.
- Xác thực đúng đối tác, public key trao đổi và toàn bộ thông tin điều đình quan trọng.
- Không tái sử dụng vô hạn private key tạm; hạn chế lưu shared secret và khóa phiên, hủy khi hết cần.
- Hạn chế ghi bí mật ra log, crash dump, telemetry, bộ nhớ không được bảo vệ hoặc bản sao lưu.

Nếu **khóa phiên của chính phiên đó** bị lộ, forward secrecy không khôi phục được tính bí mật của phiên ấy. Nếu **private agreement key tạm** đã bị lấy cắp trong lúc phiên đang diễn ra, dữ liệu phiên tương ứng cũng có thể bị ảnh hưởng. Forward secrecy thường phát biểu về sự cố **lộ khóa dài hạn về sau**, chứ không phải bảo vệ trước mọi cách đánh cắp khóa.

## 8. Quản lý vòng đời key agreement key

Một key agreement key cần có **key owner**, **key custodian**, mục đích, phạm vi tin cậy và trạng thái vòng đời giống các loại khóa quan trọng khác. Tuy nhiên, chính sách phụ thuộc đáng kể vào việc khóa là **static** hay **ephemeral**.

| Giai đoạn | Key agreement key tạm thời | Key agreement key dài hạn | Kiểm soát chính |
| --- | --- | --- | --- |
| **Tạo** | Sinh riêng cho phiên bằng bộ tạo số ngẫu nhiên mật mã phù hợp | Sinh theo kế hoạch trong vùng bảo vệ được chấp thuận | Không dùng seed dễ đoán; thuật toán/nhóm chuẩn |
| **Cấp phát công khai** | Chuyển public key qua thông điệp bắt tay | Phân phối public key/chứng thư theo chính sách | Xác thực nguồn, ràng buộc phiên và thuật toán |
| **Lưu trữ private key** | Giữ trong bộ nhớ hoặc môi trường an toàn trong thời gian ngắn | KMS/HSM/keystore hoặc cơ chế bảo vệ khóa dài hạn phù hợp | Không đưa private key vào log, repository hoặc cấu hình công khai |
| **Sử dụng** | Tính shared secret rồi dẫn xuất khóa phiên | Tham gia giao thức đã xét yêu cầu tái sử dụng | Xác thực và kiểm tra public key đối tác; giới hạn mục đích |
| **Xoay vòng** | Tạo cặp mới cho phiên/lần bắt tay mới | Thay cặp theo cryptoperiod hoặc sự cố | Tương thích protocol, phân phối public key mới |
| **Ngừng dùng/thu hồi** | Kết thúc phiên, ngăn sử dụng lại | Chặn sử dụng mới; cập nhật chứng thư/danh sách tin cậy nếu áp dụng | Cập nhật trust store và các bên phụ thuộc |
| **Hủy** | Xóa private key tạm và shared secret khi hết dùng | Hủy key material sau khi hết phụ thuộc/retention | Lưu metadata và log kiểm toán thích hợp, không giữ bí mật thừa |

Với thỏa thuận khóa dùng để tạo **khóa phiên**, không nên lưu private agreement key tạm vào cơ sở dữ liệu để “có thể bắt tay lại”. Nếu cần khôi phục phiên hay kết nối, hãy dùng cơ chế được giao thức hỗ trợ. Với khóa dài hạn, việc hủy private key trước khi hoàn tất thay thế có thể làm thiết bị hoặc đối tác không thể thiết lập phiên mới.

### Key state trong thực tế

- **Pre-activation:** Khóa đã tạo nhưng đang chờ kiểm tra/cấp quyền/chứng thư.
- **Active:** Khóa được phép tham gia các phiên thỏa thuận được quy định.
- **Suspended:** Tạm đình chỉ sử dụng khi điều tra hoặc bảo trì.
- **Deactivated:** Ngừng tham gia thỏa thuận khóa mới; có thể cần giữ vật liệu cho nghĩa vụ khác của hệ thống nếu được chính sách cho phép.
- **Compromised:** Private key có thể đã lộ hoặc độ tin cậy không còn bảo đảm; cần đánh giá phạm vi các phiên ảnh hưởng, thay khóa và điều tra.
- **Destroyed:** Vật liệu khóa đã bị hủy theo cơ chế được áp dụng.

Không nên đồng nhất các thuật ngữ trên với **Enabled/Disabled/Deleted** của từng KMS. Có nền tảng chặn toàn bộ phép toán khi **Disabled**. Việc giữ key material “đề phòng phục hồi” cũng có thể phá vỡ kỳ vọng về forward secrecy nếu đó là private key tạm.

### Khi key agreement key bị lộ

Nếu private key tạm của một phiên bị lộ, cần đánh giá **phiên tương ứng**, thời gian tồn tại bí mật phiên và khả năng giải mã lưu lượng đã thu thập. Nếu private key dài hạn bị lộ, phạm vi có thể rộng hơn, nhất là ở các giao thức dùng **static agreement**. Với giao thức dùng khóa ký dài hạn để xác thực phiên ECDHE, việc lộ khóa ký về sau **không tự động cho phép giải mã các phiên ECDHE cũ** nếu điều kiện forward secrecy được đáp ứng, nhưng kẻ tấn công vẫn có thể giả mạo các phiên mới cho đến khi chứng thư/quyền tin cậy được thu hồi và thay thế.

**Thu hồi chứng thư** (nếu có) và **vô hiệu hóa private key** là các việc khác nhau. Một chứng thư không còn đáng tin không tự hủy vật liệu private key, và hủy private key không tự đảm bảo tất cả bên đối tác cập nhật trạng thái chứng thư.

## 9. Key agreement key trong KMS/HSM và kiểm soát truy cập

Không phải mọi sản phẩm **KMS** đều hỗ trợ DH, ECDH hoặc X25519 dưới dạng API quản lý agreement key. Nhiều KMS tập trung vào tạo, mã hóa/giải mã hoặc bọc/giải bọc **khóa đối xứng**. Một số **HSM**, mô-đun mật mã hoặc keystore chuyên dụng hỗ trợ phép thỏa thuận khóa mà vẫn giữ private key bên trong vùng bảo vệ. **Phải kiểm tra khả năng hỗ trợ cụ thể** về thuật toán, tham số, cách sinh khóa, xuất khóa, phép derive, kiểm tra peer key và tiêu chuẩn tuân thủ trước khi thiết kế.

Khi KMS/HSM hoặc thư viện bảo mật cho phép quản lý agreement key, nên cân nhắc:

1. **Không xuất private key** nếu nghiệp vụ không yêu cầu. Thực hiện phép derive bên trong HSM khi API cho phép.
2. **Giới hạn mục đích sử dụng:** private agreement key không mặc nhiên có quyền ký số, giải mã bản mã hoặc xuất vật liệu; ràng buộc algorithm/key usage.
3. **Giới hạn danh tính được phép:** chỉ dịch vụ cần thỏa thuận khóa mới được gọi phép toán tương ứng; admin không tự động có quyền sử dụng private key.
4. **Xác thực public key đối tác:** HSM giữ bí mật private key nhưng **không tự xác minh danh tính peer**, trừ khi giao thức/chính sách cụ thể bổ sung bước này.
5. **Cân nhắc kết quả trả về:** Có API trả ra shared secret hoặc derived key cho caller, có API chỉ tạo **key handle** không xuất. Ranh giới bảo vệ phụ thuộc đường dữ liệu thực tế.
6. **Ghi nhật ký có chọn lọc:** Lưu định danh khóa, phiên bản, người gọi, thuật toán, kết quả và thời điểm; **không ghi private key, shared secret hay session key dạng rõ**.
7. **Kiểm toán thao tác quản trị:** Theo dõi tạo/xóa khóa, sửa grant/policy, thay alias, vô hiệu hóa key và thay đổi quyền; đánh giá đường leo thang đặc quyền.

### Phân công trách nhiệm

| Vai trò | Quyết định hoặc thao tác | Giới hạn cần bảo vệ |
| --- | --- | --- |
| **Key owner** | Phê duyệt mục đích agreement key, kiểu static/ephemeral, cryptoperiod, đối tác tin cậy và chính sách xoay vòng | Không mặc nhiên nắm private key hoặc tự cấp quyền dùng |
| **Key custodian** | Tạo/cấu hình bảo vệ khóa, quản lý quyền, thay thế/hủy và kiểm toán theo chính sách | Không tự cấp quyền derive trái phép hoặc đọc bí mật phiên |
| **Key user (dịch vụ)** | Thực hiện phép thỏa thuận và KDF cần thiết theo giao thức được cấp phép | Không tự sửa policy, xuất private key hoặc bỏ qua xác thực peer |
| **Security reviewer / auditor** | Kiểm tra thuật toán, chứng cứ phê duyệt, ràng buộc quyền và lịch sử sử dụng | Quyền xem phù hợp; không cần quyền sử dụng private key |

**Đừng nhầm key agreement key với khóa mã hóa dữ liệu lưu trữ.** Trong ứng dụng dùng **envelope encryption**, dữ liệu thường được mã hóa bằng DEK, còn KMS giữ **KEK** để bọc DEK. Key agreement key có thể được dùng ở **kênh truyền giữa hai bên** để thiết lập khóa bảo vệ thông điệp hoặc để thiết lập một khóa bọc chung theo giao thức riêng. Không có yêu cầu mặc định rằng DEK/KEK của mọi hệ thống envelope encryption phải được tạo bằng ECDH.

## 10. Các rủi ro đặc trưng và cách phòng tránh

| Lỗi thiết kế/triển khai | Hệ quả có thể xảy ra | Cách phòng tránh |
| --- | --- | --- |
| Chỉ gửi public key DH/ECDH qua mạng, không xác thực | Kẻ tấn công thay public key, lập hai shared secret riêng, đọc/sửa luồng dữ liệu | Dùng giao thức có **authenticated key exchange** như TLS 1.3 với xác thực thích hợp |
| Dùng trực tiếp Z làm AES key | Sai cách xử lý hoặc thiếu ràng buộc mục đích/ngữ cảnh | KDF chuẩn, phân tách key theo vai trò, hướng truyền và mục đích |
| Tự chọn nhóm DH/đường cong hoặc bỏ qua kiểm tra peer key | Có thể suy yếu độ an toàn, gặp điểm/nhóm không hợp lệ hoặc shared secret bất thường | Dùng nhóm tiêu chuẩn và thư viện tin cậy; xử lý all-zero, validation theo thuật toán |
| Tái sử dụng private key tạm quá lâu | Tăng phạm vi sự cố và có thể làm giảm thuộc tính forward secrecy | Tạo khóa tạm đúng chu kỳ, xóa bí mật phiên khi hết cần |
| Dùng chung private agreement key cho giao thức không liên quan | Tăng tác động sự cố; có thể tạo lỗi cross-protocol | Phân tách key theo mục đích, giao thức, môi trường và danh tính |
| Không gắn KDF với transcript, phiên bản và vai trò | Nguy cơ nhầm ngữ cảnh, đồng khóa ngoài ý muốn, hạ cấp hoặc phản xạ trong giao thức thiết kế sai | Dùng protocol chuẩn, transcript binding, định danh và nhãn dẫn xuất rõ ràng |
| Không bảo vệ nonce/counter sau khi đã thỏa thuận khóa | Lặp nonce AEAD gây mất an toàn dù shared secret mạnh | Thiết kế nonce theo đặc tả giao thức, tách key theo chiều và quản lý bộ đếm |
| Ghi Z hoặc khóa phiên ra log | Tiết lộ vật liệu bí mật qua hệ thống quan sát/backup | Chỉ ghi metadata và event; giới hạn dump, log, telemetry |
| Coi việc giữ private key trong HSM là đủ | MITM, cấp quyền sai hoặc giả mạo ứng dụng vẫn có thể diễn ra | Bảo vệ toàn bộ xác thực giao thức, IAM, key policy và audit |
| Chỉ đổi public key/alias khi private key đã bị lộ | Vật liệu bị lộ vẫn còn và các đối tác có thể tiếp tục tin cậy sai | Thay cả key pair, cập nhật trust/PKI, vô hiệu hóa quyền và điều tra |
| Cho rằng agreement key nào cũng có forward secrecy | Lộ static private key có thể ảnh hưởng các phiên cũ tùy giao thức | Phân tích mô hình static/ephemeral, xóa bí mật, kiểm tra cam kết bảo mật của giao thức |

### Tấn công man-in-the-middle minh họa

Giả sử A định thỏa thuận khóa với B. Kẻ tấn công M đứng giữa và thay public key trong cả hai chiều:

~~~text
A  -- public_A -->  M  -- public_M1 -->  B
A  <-- public_M2 -- M <-- public_B  -- B

A tinh secret(A, M2)
B tinh secret(B, M1)
M co the tinh hai secret tu hai private key cua M.
~~~

Nếu A và B không có cơ chế xác thực, họ có thể tin rằng đang trao đổi riêng với nhau trong khi M giải mã và mã hóa lại lưu lượng qua hai phiên riêng. Đây là lý do **authenticated key exchange** phải kết hợp thỏa thuận khóa với chữ ký, chứng thư, PSK hoặc cơ chế xác thực thích hợp được đặc tả trong giao thức.

### Còn nguy cơ từ mật mã hậu lượng tử?

Các thuật toán DH/ECDH/X25519 hiện sử dụng là **thỏa thuận khóa mật mã khóa công khai truyền thống**. Trong mô hình đối thủ có máy tính lượng tử đủ mạnh trong tương lai, chúng có thể chịu rủi ro từ thuật toán lượng tử liên quan đến bài toán logarit rời rạc. Nếu hệ thống cần giữ bí mật trong thời gian rất dài, chủ hệ thống phải xem xét lộ trình **thiết lập khóa hậu lượng tử** hoặc cơ chế lai đã được tiêu chuẩn hóa và hỗ trợ bởi giao thức/nền tảng. Không tự ghép hai shared secret hay tự gắn nhãn “post-quantum” nếu không có thiết kế và triển khai được đánh giá.

## 11. Tình huống thực tế: dịch vụ Java kết nối một API qua HTTPS

Giả sử **inventory-service** (Java) gọi **billing-api** qua HTTPS để lấy hóa đơn. Mục tiêu là bảo vệ dữ liệu khi truyền, xác thực máy chủ và có thể xác thực cả phía client theo chính sách doanh nghiệp.

**Phương án nên ưu tiên:** dùng thư viện HTTP/TLS chuẩn của Java, cấu hình **TLS 1.3**, trust store, kiểm tra hostname, chứng thư và tùy chọn mTLS nếu cần. TLS chịu trách nhiệm điều đình thuật toán, xác thực handshake, key agreement, KDF và khóa bảo vệ kênh.

~~~mermaid
flowchart TD
    A[inventory-service] -->|Kết nối TLS 1.3| B[billing-api]
    A --> C[Đóng góp khóa agreement tạm thời]
    B --> D[Đóng góp khóa agreement tạm thời]
    C --> E[Bí mật chung qua ECDHE/X25519]
    D --> E
    E --> F[Key schedule / KDF theo TLS]
    F --> G[Khóa đối xứng bảo vệ lưu lượng]
    H[Chứng thư, xác thực và transcript] --> F
    G --> I[Kênh ứng dụng đã bảo vệ]
~~~

Trong thiết kế này:

- **Key agreement key**: cặp khóa (EC)DHE/X25519 tạm thời trong handshake.
- **Authentication key/chứng thư**: xác thực đối tác trong TLS; có thể là RSA, ECDSA hoặc thuật toán chữ ký được hỗ trợ, tùy cấu hình.
- **Traffic key**: khóa đối xứng do lịch dẫn xuất khóa TLS tạo ra, dùng để mã hóa/xác thực bản ghi TLS.
- **KEK/DEK ở tầng lưu trữ**: nếu dữ liệu hóa đơn vẫn được mã hóa trong database bằng envelope encryption, đây là **những khóa khác** với khóa của phiên TLS.

Khi một phiên TLS kết thúc, không cần đưa private agreement key tạm vào KMS để giữ vô thời hạn. Khi chứng thư máy chủ cần thay, nhóm vận hành quản lý vòng đời **khóa xác thực dài hạn và chứng thư**; đó là luồng quản trị liên quan nhưng khác với việc liên tục sinh key agreement key tạm cho các kết nối.

Nếu đội ngũ muốn tự xây một API “trả public key rồi gửi bản mã”, phải tự giải quyết xác thực, KDF, chống phát lại, nonce, thay khóa, xử lý lỗi và quản lý phiên. Đây là phạm vi dễ mắc lỗi; một giao thức chuẩn được duy trì và kiểm thử giúp giảm đáng kể rủi ro.

## 12. Checklist tự đánh giá key agreement key

Trước khi triển khai một cơ chế thỏa thuận khóa trong sản xuất, hãy trả lời:

1. **Mục đích:** Đây thực sự là thỏa thuận khóa hay chỉ là gửi một khóa do một bên tạo? Public/private key nào tham gia và shared secret dùng để dẫn xuất khóa gì?
2. **Thuật toán:** Đang dùng nhóm DH/ECDH/X25519 nào? Thư viện có kiểm tra đầu vào, từ chối shared secret all-zero và xử lý lỗi nhất quán không?
3. **Xác thực:** Public key đối tác được xác thực bằng cơ chế nào? Có chống MITM, downgrade và ràng buộc với danh tính/phiên không?
4. **KDF:** Z có đi qua KDF phù hợp, tách mục đích/hướng truyền, gắn với transcript và ngữ cảnh giao thức không?
5. **Khóa tạm:** Mỗi phiên có tạo key pair tạm đúng yêu cầu và hủy shared secret/private key đúng thời điểm không? Có kỳ vọng forward secrecy được kiểm chứng không?
6. **Bảo vệ private key:** Khóa dài hạn có được bảo vệ bằng keystore/KMS/HSM phù hợp, hạn chế xuất và cấp quyền tối thiểu không?
7. **Quyền và kiểm toán:** Có key owner/custodian, chính sách sử dụng, lịch thay khóa và log thay đổi trạng thái/quyền không? Log có loại trừ vật liệu bí mật không?
8. **Rủi ro sự cố:** Nếu private key, danh tính dịch vụ hoặc chứng thư bị lộ, có phương án cô lập, cập nhật trust store, thay khóa và xác định phiên bị ảnh hưởng không?
9. **Tính tương thích:** Đối tác và sản phẩm KMS/HSM có thật sự hỗ trợ phép toán, tham số, định dạng public key và xử lý lỗi dự kiến không?
10. **An toàn ứng dụng:** Khóa dẫn xuất dùng với AEAD có nonce/counter đúng quy tắc, chống replay và xử lý lỗi giải mã an toàn không?

### Ghi nhớ

**Key agreement key** là khóa tham gia **thiết lập bí mật chung** giữa các bên, thường là cặp private/public key DH, ECDH hoặc X25519. **Shared secret không phải khóa ứng dụng hoàn chỉnh**: cần KDF, phân tách mục đích và xác thực đúng đối tác. Để thiết kế hệ thống quản lý khóa an toàn, phải kết nối thỏa thuận khóa với **mật mã đối xứng, bất đối xứng, chữ ký số/chứng thư, KMS/HSM, kiểm soát truy cập, vòng đời rotation–thu hồi–hủy và kiểm toán**. Đặc biệt, tính an toàn không đến chỉ từ thuật toán mạnh, mà còn từ **giao thức đã được kiểm chứng và cách vận hành khóa trong thực tế**.
