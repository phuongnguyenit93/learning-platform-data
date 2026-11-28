# Authenticated key agreement – Thỏa thuận khóa có xác thực

**Authenticated Key Agreement (AKE)** là một giao thức cho phép hai hoặc nhiều bên **thiết lập vật liệu khóa chung và xác thực đối tác theo mô hình tin cậy đã chọn**. Thay vì chỉ bảo đảm hai bên tính được cùng một bí mật như ở Diffie–Hellman thuần, AKE còn phải ràng buộc khóa với **danh tính đối tác, vai trò, thông số giao thức và phiên bắt tay**. Một giao thức AKE được thiết kế đúng giúp giảm nguy cơ **man-in-the-middle (MITM)**, giả mạo danh tính, tráo khóa và nhiều kiểu sử dụng sai khóa.

Bài thuộc chương **Key establishment** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Chủ đề kết nối mật mã bất đối xứng (ECDH/X25519, chữ ký số), mật mã đối xứng (AES-GCM), KDF/HKDF, KMS/HSM, envelope encryption, phân quyền và kiểm toán. Để xây dựng hệ thống an toàn, cần xem AKE trong toàn bộ vòng đời khóa: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**, không chỉ dừng ở phép tính toán học.

> **Điểm cốt lõi:** ECDH/X25519 tạo shared secret, nhưng **không tự chứng minh public key thuộc đúng người cần liên lạc**. AKE bổ sung cơ chế xác thực để bên tham gia có thể tin rằng khóa được thiết lập với đối tác được mong đợi. **Key confirmation** và **peer authentication** cũng là hai thuộc tính khác nhau.

## 1. Vấn đề của key agreement không xác thực

Giả sử Alice muốn giao tiếp bí mật với Bob qua mạng. Hai bên sinh cặp khóa X25519 tạm thời:

1. Alice gửi public key A cho Bob.
2. Bob gửi public key B cho Alice.
3. Alice tính shared secret từ private key của Alice và B.
4. Bob tính shared secret từ private key của Bob và A.
5. Sau KDF, hai bên có thể tạo khóa AES để mã hóa dữ liệu.

Nếu không có kẻ can thiệp, hai bên sẽ tạo cùng một bí mật. Tuy nhiên, **public key A và B thường đi qua một kênh chưa được tin cậy**. Kẻ tấn công Mallory có thể thay B bằng public key M1 gửi cho Alice, và thay A bằng M2 gửi cho Bob.

Kết quả: Alice thiết lập khóa với Mallory nhưng tưởng là Bob; Bob thiết lập khóa với Mallory nhưng tưởng là Alice. Mallory có thể giải mã thông điệp từ Alice, sửa đổi, rồi mã hóa lại cho Bob. Mỗi phiên giả vẫn có thể dùng AES-GCM đúng và xác thực tag thành công.

~~~mermaid
sequenceDiagram
    participant Alice
    participant Mallory as Mallory (MITM)
    participant Bob
    Alice->>Mallory: Public key A (định gửi Bob)
    Mallory->>Bob: Public key M2 (giả làm Alice)
    Bob->>Mallory: Public key B (định gửi Alice)
    Mallory->>Alice: Public key M1 (giả làm Bob)
    Note over Alice,Mallory: Shared key K_AM
    Note over Mallory,Bob: Shared key K_MB
    Alice->>Mallory: Ciphertext dưới K_AM
    Note over Mallory: Giải mã, đọc/sửa dữ liệu
    Mallory->>Bob: Mã hóa lại dưới K_MB
~~~

**Điều còn thiếu không phải thuật toán mã hóa mạnh hơn**, mà là một cách xác thực **public key của đối tác** và gắn kết kết quả thỏa thuận với đúng phiên, đúng danh tính.

## 2. Định nghĩa và các thuộc tính của AKE

Có nhiều mô hình AKE; không phải giao thức nào cũng cung cấp mọi thuộc tính ở mức giống nhau. Khi đánh giá, cần ghi rõ yêu cầu và giả định về khóa dài hạn, thiết bị, danh tính và kẻ tấn công.

| Thuộc tính | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **Key secrecy** | Bên ngoài không tính được khóa phiên trong mô hình an toàn đã giả định. | Phụ thuộc tính an toàn của key agreement/KEM, KDF, nguồn ngẫu nhiên và bảo vệ khóa. |
| **Peer authentication** | Bên tham gia có bằng chứng về danh tính của đối tác theo trust policy. | Chứng chỉ, public key ghim sẵn hoặc PSK phải được cấp phát đúng. |
| **Key agreement/binding** | Các bên hợp lệ liên kết một khóa với cùng phiên và thông số thỏa thuận. | Tránh nhầm vai trò, danh tính hoặc phiên. |
| **Key confirmation** | Có bằng chứng rằng đối tác sở hữu khóa/bí mật phiên tương ứng. | Không đồng nghĩa chứng minh danh tính nếu khóa được thiết lập với kẻ MITM. |
| **Forward secrecy** | Lộ khóa danh tính dài hạn về sau không tự giải mã được các phiên đã hoàn tất. | Cần giao thức ephemeral đúng và xóa bí mật phiên; không mặc định có với static DH hoặc PSK-only. |
| **Replay resistance** | Ngăn tái sử dụng handshake hoặc dữ liệu cũ theo chính sách. | Cần độ mới, nonce/sequence và kiểm tra trạng thái giao thức. |
| **Downgrade resistance** | Ngăn kẻ tấn công ép dùng phiên bản hoặc thuật toán yếu. | Tham số thương lượng phải được ràng buộc/xác thực. |
| **Key separation** | Khóa dùng cho từng chiều và mục đích được dẫn xuất độc lập. | Tránh reuse một key giữa mã hóa, MAC và các vai trò khác nhau. |

**Thành công của phép xác minh chữ ký chưa tự cho phép truy cập nghiệp vụ.** Danh tính server được xác thực bằng chứng chỉ không có nghĩa client có quyền đọc mọi đơn hàng. Authorization, tenant isolation và kiểm toán phải hoạt động ở lớp phù hợp.

### 2.1. Xác thực một chiều và hai chiều

- **Server-authenticated AKE:** client xác thực server; server có thể chưa xác thực danh tính client bằng mật mã bắt tay. TLS dùng phổ biến theo mô hình này.
- **Mutually authenticated AKE:** cả hai bên đều xác thực danh tính đối tác. Một cách triển khai quen thuộc là **mTLS**, trong đó server yêu cầu và xác minh chứng chỉ client.
- **PSK-authenticated AKE:** xác thực dựa trên bí mật chia sẻ đã được cấp phát an toàn; có thể kết hợp ephemeral DH để bổ sung thuộc tính an toàn theo giao thức.
- **Password-authenticated key exchange (PAKE):** xác thực bằng mật khẩu theo một giao thức chống các kiểu tấn công đoán mật khẩu thích hợp; không phải chỉ lấy mật khẩu làm khóa AES hoặc PSK thô.

**Mutual authentication không tự có** chỉ vì cả hai cùng tính được shared secret. Phải xác định ai đang xác thực ai và ràng buộc danh tính nào với khóa.

## 3. Các thành phần mật mã thường gặp

Một AKE dựa trên ECDHE có thể kết hợp các thành phần:

1. **ECDH/X25519 hoặc KEM:** đóng góp shared secret mà người nghe lén không thể tính được theo giả định an toàn.
2. **Khóa danh tính dài hạn:** private key ký số hoặc PSK, được quản lý theo một mô hình tin cậy.
3. **Chữ ký số / MAC xác thực:** chứng minh quyền sở hữu khóa danh tính và bảo vệ các thông điệp bắt tay.
4. **Transcript:** biểu diễn được chuẩn hóa của thông điệp và các lựa chọn giao thức, gồm public key tạm thời, vai trò, phiên bản, thuật toán, nonce và thông tin quan trọng.
5. **KDF/key schedule:** dẫn xuất traffic keys và confirmation keys từ shared secret, transcript và các đầu vào theo chuẩn.
6. **Key confirmation:** bước kiểm tra phía kia thực sự có vật liệu khóa đúng, chẳng hạn một MAC Finished được tính với khóa dẫn xuất riêng.
7. **AEAD:** bảo vệ dữ liệu sau handshake, ví dụ AES-GCM hoặc ChaCha20-Poly1305, với nonce và key usage policy phù hợp.

~~~mermaid
flowchart TD
    A["Client và server trao đổi ephemeral public keys"] --> B["Tạo shared secret qua ECDHE/KEM"]
    ID["Khóa danh tính/chứng chỉ/PSK đáng tin"] --> AUTH["Xác thực peer và dữ liệu handshake"]
    A --> TRANSCRIPT["Transcript + thuật toán + vai trò + nonces"]
    TRANSCRIPT --> AUTH
    AUTH --> CHECK{"Chấp nhận danh tính và transcript?"}
    CHECK -->|Không| REJECT["Từ chối handshake"]
    CHECK -->|Có| KDF["KDF: secret + transcript/context"]
    B --> KDF
    KDF --> KEY1["Client → Server traffic key"]
    KDF --> KEY2["Server → Client traffic key"]
    KDF --> FIN["Key confirmation / Finished theo giao thức"]
    FIN --> READY["Chỉ sau xác minh thành công mới sử dụng kênh"]
~~~

**Thứ tự và ý nghĩa thực tế** phụ thuộc giao thức. Ví dụ trong TLS 1.3, các bí mật bắt tay được dẫn xuất trước một số bước xác thực để bảo vệ thông điệp tiếp theo; không được lấy sơ đồ khái niệm này làm đặc tả thứ tự TLS.

### 3.1. Authentication bằng chữ ký số

Với khóa danh tính như **Ed25519, ECDSA hoặc RSA-PSS**, bên ký có thể chứng minh quyền sở hữu private key bằng chữ ký trên dữ liệu bắt tay đã được chuẩn hóa. Bên nhận xác minh chữ ký bằng public key **đã liên kết với danh tính mong đợi** qua chứng chỉ, trust store hoặc cơ chế pinning được quản lý.

Cần ký đúng **bản transcript và ngữ cảnh bắt tay**, không chỉ ký một public key đơn lẻ mà bỏ qua algorithm, role hoặc người nhận. Nếu không, chữ ký có thể bị dùng nhầm ở một phiên hoặc giao thức khác.

Ví dụ, chữ ký server có thể bao phủ thông tin phiên bản giao thức, public key tạm thời của cả hai bên, danh tính server, các thuật toán thương lượng và giá trị nonce. Trong giao thức thật phải dùng format và domain separation theo chuẩn.

### 3.2. Authentication bằng PSK

PSK là khóa bí mật đã được phân phối an toàn trước handshake. Một giao thức có thể dùng PSK để xác thực transcript bằng MAC hoặc làm đầu vào cho key schedule. Nếu dùng **cùng PSK cho nhiều workload hoặc tenant**, một bên có thể giả mạo những bên khác trong cùng nhóm chia sẻ.

PSK phải được sinh từ nguồn đủ entropy, lưu trong kho bí mật/KMS/HSM khi phù hợp, có key ID, phạm vi owner/tenant, hạn dùng và chính sách rotate/revoke. **Mật khẩu người dùng yếu không phải PSK entropy cao**; nếu cần xác thực dựa trên mật khẩu, sử dụng PAKE được chuẩn hóa thay vì tự chuyển mật khẩu thành PSK.

### 3.3. Xác thực không thay thế KDF

ECDH tạo ra **vật liệu bí mật đầu vào**, không phải nhiều khóa độc lập cho mọi mục đích. AKE thường sử dụng **HKDF** hoặc một KDF được giao thức quy định để tạo:

- Khóa mã hóa chiều **client → server**.
- Khóa mã hóa chiều **server → client**.
- Khóa xác nhận phiên hoặc key confirmation theo giao thức.
- Khóa cho các giai đoạn handshake, application data và key update nếu giao thức yêu cầu.

Các khóa phải được **domain separated** bằng nhãn và ngữ cảnh đã định nghĩa rõ. Không dùng một khóa AES-GCM cho hai chiều rồi mỗi bên tự khởi tạo nonce counter từ 0: đây có thể gây **tái sử dụng cùng key + nonce**.

## 4. Transcript binding và chống tráo danh tính

Một giao thức AKE an toàn phải xác định **những dữ liệu nào được xác thực**. Chỉ ký shared secret hoặc chỉ kiểm tra một MAC không có ngữ cảnh có thể bỏ sót việc ai tin đang nói chuyện với ai.

### 4.1. Transcript nên ràng buộc những gì?

| Trường | Vì sao cần ràng buộc? |
| --- | --- |
| Protocol name / version | Ngăn dùng lại chữ ký hoặc khóa ở giao thức/phiên bản khác. |
| Danh sách và kết quả chọn thuật toán | Giảm rủi ro downgrade và algorithm confusion. |
| Client/server roles | Không nhầm chiều truyền và danh tính khi phản chiếu thông điệp. |
| Ephemeral public keys | Ngăn tráo khóa DH được dùng để tạo shared secret. |
| Identity và đối tượng nhận dự kiến | Tránh dùng khóa với bên khác hoặc tenant khác. |
| Nonce/challenge của hai phía | Hỗ trợ tính mới của phiên và phân biệt handshake. |
| Thông số KDF / key schedule | Ngăn diễn giải hai tập bí mật khác nhau như cùng giao thức. |
| Context ứng dụng có ảnh hưởng quyền | Gắn session với service, channel, tenant hoặc mục đích theo chính sách. |

Dữ liệu cần có **canonical encoding**: cùng một ý nghĩa phải có một cách chuyển sang bytes đã định nghĩa, hoặc hai bên dùng đúng bytes truyền trên dây. Với dữ liệu gồm nhiều trường có độ dài thay đổi, nên dùng mã hóa có **prefix độ dài** hoặc một định dạng nhị phân có cấu trúc. Tự nối chuỗi với dấu phân cách có thể tạo hai tập trường khác nhau nhưng cùng bytes.

### 4.2. Unknown Key-Share (UKS)

**Unknown Key-Share** là tình huống các bên có thể chia sẻ **cùng khóa**, nhưng một hoặc nhiều bên **hiểu sai danh tính đối tác** của khóa đó. Vì vậy một phép kiểm tra “hai bên đều tính được 32 byte giống nhau” không chứng minh được rằng danh tính đã được gắn đúng.

Phòng vệ gồm việc ràng buộc **danh tính, vai trò, transcript và thông số giao thức** với xác thực peer và key schedule. Cần phân biệt UKS với MITM thông thường: kẻ tấn công có thể gây nhầm danh tính ngay cả khi không biết shared secret trong một số giao thức lỗi.

### 4.3. Key-Compromise Impersonation (KCI)

**KCI (key-compromise impersonation)** nói đến khả năng kẻ tấn công, sau khi lấy được **khóa dài hạn của một bên**, có thể mạo danh **một đối tác khác trước chính bên bị lộ khóa**, thay vì chỉ mạo danh bên bị lộ khóa với người khác. Khả năng chống KCI là một thuộc tính cần phân tích trong một số mô hình AKE, đặc biệt với giao thức dùng **static DH** hoặc kết hợp khóa tĩnh và khóa tạm thời.

Không khẳng định một giao thức chống KCI chỉ vì dùng X25519 hoặc vì có key confirmation. Tính chất này phụ thuộc thiết kế giao thức, vai trò và mô hình khóa bị xâm nhập.

## 5. Explicit key confirmation khác xác thực danh tính

**Peer authentication** trả lời: “Tôi có căn cứ để tin đối tác là chủ thể nào?”. **Key confirmation** trả lời: “Tôi có bằng chứng bên kia cũng nắm bí mật phiên đúng hay không?”.

Một giao thức có thể cung cấp **implicit key authentication** theo nghĩa chỉ bên được kỳ vọng mới có khả năng tạo khóa phù hợp, nhưng chưa có bằng chứng rằng bên đó đã thực sự hoàn tất tính khóa. **Explicit key confirmation** thêm bước phản hồi mật mã để xác nhận quyền sở hữu khóa.

Ví dụ khái niệm với hai khóa xác nhận riêng:

~~~text
clientFinishedKey = HKDF-Expand(handshakeSecret, "client-finished|context", 32)
serverFinishedKey = HKDF-Expand(handshakeSecret, "server-finished|context", 32)

clientProof = HMAC(clientFinishedKey, transcriptHash)
serverProof = HMAC(serverFinishedKey, transcriptHash)
~~~

Bên nhận kiểm tra tag theo **trạng thái bắt tay và vai trò** đã được quy định; giá trị context/nhãn thực tế phải theo chuẩn của giao thức. Không dùng chung khóa xác nhận với khóa mã hóa traffic nếu giao thức không cho phép.

**Một Mallory trong mô hình MITM cũng có thể tạo Finished MAC hợp lệ cho phiên của Mallory.** Do đó key confirmation **không thay thế** việc xác thực danh tính và nguồn public key.

## 6. Authenticated key agreement trong TLS 1.3 và các giao thức thực tế

### 6.1. TLS 1.3

**TLS 1.3** là một ví dụ quan trọng của key establishment có xác thực:

1. Client và server thương lượng phiên bản, thuật toán và nhóm trao đổi khóa theo giao thức.
2. Các bên có thể dùng **(EC)DHE tạm thời**, chẳng hạn X25519, để tạo shared secret.
3. Key schedule dẫn xuất các bí mật handshake và traffic theo transcript.
4. Server thường cung cấp **chứng chỉ và chữ ký CertificateVerify** để xác thực danh tính server với client.
5. Thông điệp **Finished** giúp xác nhận trạng thái bắt tay/khóa và toàn vẹn transcript theo quy tắc giao thức.
6. Nếu cần **mutual authentication**, server yêu cầu chứng chỉ và xác minh client theo cấu hình; chỉ có chứng chỉ server **không phải mTLS**.

TLS 1.3 cũng hỗ trợ một số chế độ **PSK/resumption**. Với PSK-only, 0-RTT hoặc early data, thuộc tính forward secrecy và chống replay **có các điều kiện khác** so với handshake ECDHE đầy đủ. Không xem mọi bản ghi TLS 1.3 đều có cùng mức bảo vệ trước replay.

**Lựa chọn thực tế:** Dùng thư viện TLS 1.3 được duy trì và cấu hình đúng, kiểm tra hostname/định danh, trust anchor, certificate policy, cipher suite và trạng thái chứng chỉ. **Không tự thay TLS bằng vài phép X25519 + Ed25519 + AES-GCM viết tay** chỉ vì demo cho ra cùng khóa.

### 6.2. Noise, SIGMA và HPKE

- **Noise Protocol Framework** mô tả các mẫu handshake kết hợp khóa tĩnh/tạm thời với cơ chế xác thực khác nhau; ví dụ một số pattern như **IK** hoặc **XX** có thuộc tính và yêu cầu biết public key đối tác khác nhau. Chọn đúng pattern và cơ chế ràng buộc danh tính là thiết yếu.
- **SIGMA** là một họ thiết kế giao thức dựa trên Diffie–Hellman, chữ ký và MAC trong các mô hình cụ thể, thường được nhắc khi học các nguyên tắc xác thực và binding.
- **HPKE (RFC 9180)** kết hợp KEM, KDF và AEAD để bảo vệ dữ liệu cho một public key; các mode có mức xác thực khác nhau. **HPKE base mode không tự xác thực danh tính bên gửi** và public key bên nhận vẫn phải được xác thực. Không gọi mọi thao tác HPKE là mutually authenticated AKE.
- **PAKE** được thiết kế cho các trường hợp một bên hoặc nhiều bên xác thực dựa trên mật khẩu; cần dùng giao thức được đánh giá, không tự biến PBKDF2 + ECDH thành PAKE.

Tên giao thức chỉ có ý nghĩa khi xem đầy đủ **mode, trạng thái, trust model, điều kiện triển khai và chuẩn phiên bản**. Một tổ hợp thuật toán riêng lẻ không tạo ra mọi thuộc tính của AKE.

## 7. Ví dụ Java 17: X25519 + Ed25519 xác thực hai phía

Đoạn mã **minh họa giáo dục** cho mô hình **mutually authenticated key agreement** trong **một tiến trình**. Client và server có hai cặp khóa **Ed25519 danh tính** được coi là đã đăng ký trong trust store. Mỗi phía sinh một **key pair X25519 tạm thời**, trao đổi public key và nonce, ký transcript theo vai trò, kiểm tra chữ ký với public key danh tính tin cậy, tính shared secret rồi dùng HKDF để dẫn xuất các khóa.

**Giới hạn:** Đây **không phải giao thức production**, dù mỗi phép mật mã riêng dùng API chuẩn. Bản demo chưa cài đặt state machine qua mạng, chống replay toàn phần, cơ chế chứng chỉ, quản lý phiên, key update, các điều kiện lỗi giao thức hoặc chứng minh bảo mật toàn bộ AKE.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class AuthenticatedKeyAgreementDemo {
    // Mã hóa các trường bằng prefix độ dài, không nối strings mơ hồ.
    private static byte[] transcript(byte[] clientNonce, byte[] serverNonce,
                                     PublicKey clientEphemeral,
                                     PublicKey serverEphemeral,
                                     PublicKey clientIdentity,
                                     PublicKey serverIdentity) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        for (byte[] field : new byte[][] {
                "AKE-DEMO-v1|X25519|Ed25519|HKDF-SHA256"
                        .getBytes(StandardCharsets.UTF_8),
                "client".getBytes(StandardCharsets.UTF_8),
                "server".getBytes(StandardCharsets.UTF_8),
                clientNonce, serverNonce,
                clientEphemeral.getEncoded(), serverEphemeral.getEncoded(),
                clientIdentity.getEncoded(), serverIdentity.getEncoded()
        }) {
            out.writeInt(field.length);
            out.write(field);
        }
        out.flush();
        return buffer.toByteArray();
    }

    private static byte[] roleInput(String role, byte[] transcript) {
        byte[] label = ("AKE-DEMO-v1/signature/" + role)
                .getBytes(StandardCharsets.UTF_8);
        byte[] data = new byte[4 + label.length + transcript.length];
        data[0] = (byte) (label.length >>> 24);
        data[1] = (byte) (label.length >>> 16);
        data[2] = (byte) (label.length >>> 8);
        data[3] = (byte) label.length;
        System.arraycopy(label, 0, data, 4, label.length);
        System.arraycopy(transcript, 0, data, 4 + label.length,
                transcript.length);
        return data;
    }

    private static byte[] sign(PrivateKey privateKey, String role,
                               byte[] transcript) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(roleInput(role, transcript));
        return signer.sign();
    }

    private static boolean verify(PublicKey trustedPublic, String role,
                                  byte[] transcript, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedPublic);
        verifier.update(roleInput(role, transcript));
        return verifier.verify(signature);
    }

    private static byte[] x25519(PrivateKey ownPrivate, PublicKey peerPublic)
            throws Exception {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(ownPrivate);
        ka.doPhase(peerPublic, true);
        byte[] secret = ka.generateSecret();
        // Từ chối shared secret toàn zero theo yêu cầu kiểm tra X25519.
        int nonzero = 0;
        for (byte b : secret) nonzero |= b;
        if (nonzero == 0) {
            Arrays.fill(secret, (byte) 0);
            throw new SecurityException("Invalid X25519 shared secret");
        }
        return secret;
    }

    private static byte[] hkdf32(byte[] sharedSecret, byte[] transcriptHash,
                                 String purpose) throws Exception {
        // HKDF-Extract: salt công khai là transcriptHash (32 byte).
        Mac extract = Mac.getInstance("HmacSHA256");
        extract.init(new SecretKeySpec(transcriptHash, "HmacSHA256"));
        byte[] prk = extract.doFinal(sharedSecret);
        try {
            // HKDF-Expand một block: T(1)=HMAC(PRK, info || 0x01).
            Mac expand = Mac.getInstance("HmacSHA256");
            expand.init(new SecretKeySpec(prk, "HmacSHA256"));
            expand.update(("AKE-DEMO-v1/" + purpose)
                    .getBytes(StandardCharsets.UTF_8));
            expand.update(transcriptHash);
            expand.update((byte) 1);
            return expand.doFinal(); // 32 byte với HMAC-SHA-256.
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    private static byte[] hmac(byte[] key, byte[] transcriptHash)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(transcriptHash);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator signing = KeyPairGenerator.getInstance("Ed25519");
        KeyPair clientIdentity = signing.generateKeyPair();
        KeyPair serverIdentity = signing.generateKeyPair();

        // Trong thực tế: các public key danh tính phải được trust/pin trước.
        PublicKey trustedServer = serverIdentity.getPublic();
        PublicKey trustedClient = clientIdentity.getPublic();

        KeyPairGenerator agreement = KeyPairGenerator.getInstance("X25519");
        KeyPair clientEphemeral = agreement.generateKeyPair();
        KeyPair serverEphemeral = agreement.generateKeyPair();
        SecureRandom rng = new SecureRandom();
        byte[] clientNonce = new byte[32], serverNonce = new byte[32];
        rng.nextBytes(clientNonce);
        rng.nextBytes(serverNonce);

        byte[] handshake = transcript(
                clientNonce, serverNonce,
                clientEphemeral.getPublic(), serverEphemeral.getPublic(),
                clientIdentity.getPublic(), serverIdentity.getPublic());

        // Mỗi bên ký cùng transcript với domain/role khác nhau.
        byte[] serverSignature = sign(
                serverIdentity.getPrivate(), "server", handshake);
        byte[] clientSignature = sign(
                clientIdentity.getPrivate(), "client", handshake);

        // Kiểm tra danh tính theo public keys đã tin cậy.
        if (!verify(trustedServer, "server", handshake, serverSignature)
                || !verify(trustedClient, "client", handshake,
                           clientSignature)) {
            throw new SecurityException("Peer authentication failed");
        }

        byte[] clientSecret = x25519(
                clientEphemeral.getPrivate(), serverEphemeral.getPublic());
        byte[] serverSecret = x25519(
                serverEphemeral.getPrivate(), clientEphemeral.getPublic());
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(handshake);
        try {
            // Hai phía có cùng key cho một mục đích xác định.
            byte[] c2sClient = hkdf32(clientSecret, hash, "client-to-server");
            byte[] c2sServer = hkdf32(serverSecret, hash, "client-to-server");
            byte[] finClient = hkdf32(clientSecret, hash, "client-finished");
            byte[] finServer = hkdf32(serverSecret, hash, "client-finished");
            try {
                if (!MessageDigest.isEqual(c2sClient, c2sServer)) {
                    throw new SecurityException("Derived keys differ");
                }
                // Minh họa explicit key confirmation từ client tới server.
                byte[] clientFinished = hmac(finClient, hash);
                boolean confirmed = MessageDigest.isEqual(
                        clientFinished, hmac(finServer, hash));
                System.out.println("Mutually signed transcript: true");
                System.out.println("Client key confirmed: " + confirmed);
                // Chiều server->client cần confirmation và key riêng tương ứng.
                Arrays.fill(clientFinished, (byte) 0);
            } finally {
                Arrays.fill(c2sClient, (byte) 0);
                Arrays.fill(c2sServer, (byte) 0);
                Arrays.fill(finClient, (byte) 0);
                Arrays.fill(finServer, (byte) 0);
            }
        } finally {
            Arrays.fill(clientSecret, (byte) 0);
            Arrays.fill(serverSecret, (byte) 0);
            Arrays.fill(hash, (byte) 0);
            Arrays.fill(clientNonce, (byte) 0);
            Arrays.fill(serverNonce, (byte) 0);
        }
    }
}
~~~

### 7.1. Phân tích tính đúng và giới hạn

- **X25519** tạo shared secret, không tự xác thực danh tính. Demo dùng **Ed25519** ký trên transcript có định danh giao thức, hai nonce, public keys danh tính và ephemeral public keys.
- Chữ ký của **server** và **client** có **role label riêng**, giúp ngăn nhầm lẫn chữ ký giữa hai vai trò trong phạm vi mô hình demo.
- Hai public key danh tính được “tin cậy” chỉ vì cùng được tạo trong một tiến trình demo. **Đó không phải quy trình phân phối khóa tin cậy**. Production phải sử dụng chứng chỉ/mTLS, trust store hoặc một cơ chế đăng ký danh tính được kiểm soát.
- **HKDF-Extract/Expand** dùng shared secret và transcript hash, sinh khóa có nhãn riêng. Hàm minh họa chỉ hỗ trợ đúng **32 byte đầu ra** một block, không phải HKDF tổng quát.
- Code xác minh **client Finished** dưới khóa riêng, nhưng không triển khai đầy đủ thông điệp Finished phía server, handshake state, early-data/replay, key update, kiểm soát trình tự hay thông báo lỗi giao thức; vì vậy **không được dùng làm AKE thực tế**.
- Byte arrays được xóa ở vài điểm; việc này **không bảo đảm xóa toàn bộ bản sao secret trong JVM/provider**. Khóa riêng của hai identity và cặp ephemeral cũng chỉ có vòng đời trong tiến trình demo, không có bảo đảm zeroization.
- **Không mã hóa dữ liệu ứng dụng trong demo**. Một AKE hoàn chỉnh còn cần dẫn xuất traffic keys hai chiều và sử dụng AEAD đúng nonce/counter, có giới hạn dung lượng theo key.

### 7.2. Vì sao không nên tự triển khai AKE ở production?

Mật mã nguyên thủy mạnh không đủ chứng minh toàn bộ giao thức an toàn. Các lỗi thường ẩn trong **trình tự handshake, lỗi thông điệp, giao thức mạng bất đồng bộ, retry, giao thức nhiều phiên song song, đồng bộ thời gian, chính sách xác thực và đường khôi phục**. Một AKE “có chữ ký và Finished MAC” vẫn có thể bị tấn công nếu bytes ký không đầy đủ hoặc verifier chấp nhận identity sai.

Với ứng dụng Java triển khai microservice, nên ưu tiên **TLS 1.3/mTLS** từ thư viện/runtime được hỗ trợ, kiểm tra hostname/định danh server, trust anchor, client certificate policy và authorization. Chỉ thiết kế giao thức AKE riêng khi có yêu cầu đặc biệt và năng lực đánh giá/proof thích hợp.

## 8. Vòng đời khóa của Authenticated Key Agreement

Trong AKE, nhiều loại khóa cùng tồn tại nhưng có **mục đích và thời hạn khác nhau**:

| Loại khóa/bí mật | Vai trò | Quản lý vòng đời |
| --- | --- | --- |
| **Identity private key** | Ký hoặc xác thực danh tính trong handshake. | Sinh CSPRNG/KMS-HSM; gắn owner, key ID, usage, hạn dùng; rotate/revoke, kiểm toán quyền Sign. |
| **Identity public key / certificate** | Cho verifier xác thực chữ ký và peer. | Phân phối tin cậy; kiểm tra tên, thuật toán, chứng chỉ/trust và thay phiên bản. |
| **Ephemeral ECDH private key** | Đóng góp bí mật cho một phiên. | Sinh riêng theo chính sách; không ghi log/backup; xóa sau khi đủ điều kiện kết thúc phiên. |
| **Shared secret/KEM secret** | Đầu vào cho KDF. | Chỉ giữ trong bộ nhớ cần thiết; từ chối giá trị không hợp lệ và dọn khi xong. |
| **Handshake/confirmation keys** | Xác nhận phiên và xác thực transcript. | Dẫn xuất theo purpose; không dùng như DEK lưu trữ; dọn khi không cần. |
| **Traffic keys** | AEAD/MAC bảo vệ dữ liệu trên kênh. | Tách theo chiều, giới hạn nonce/dữ liệu theo key, key update theo protocol. |
| **PSK/ticket secrets** | Khôi phục/xác thực phiên theo mode cho phép. | Giới hạn phát hành, thời hạn, replay policy, rotate/revoke và phân vùng môi trường. |
| **DEK/KEK lưu trữ** | Bảo vệ dữ liệu tại rest qua envelope encryption. | Có key ID/phiên bản, KMS ACL và backup/rewrap; không nhầm với traffic key. |

### 8.1. Sinh và cấp phát

- Khóa danh tính và ephemeral key pair phải được sinh từ **CSPRNG hoặc dịch vụ quản lý khóa đáng tin**; seed đoán được có thể làm lộ private key.
- Cấp phát **chứng chỉ, public key, PSK và quyền KMS** theo danh tính workload/tenant, không dùng khóa staging làm identity production.
- Xác định **key usage**: Ed25519 dùng ký số, X25519 dùng thỏa thuận khóa; không dùng chung private key/seed giữa những mục đích không được chuẩn cho phép.

### 8.2. Sử dụng và giám sát

- Theo dõi sự kiện handshake lỗi, thay đổi chứng chỉ, algorithm negotiation và dấu hiệu public key không tin cậy.
- AEAD như **AES-GCM** cần nonce **không trùng theo khóa** và giới hạn số lần/dung lượng mã hóa; key update không được reset nonce trên **cùng khóa**.
- Không gửi shared secret, ephemeral private key, traffic key hoặc private key danh tính vào log, tracing hay crash report. Audit chỉ giữ metadata cần thiết.

### 8.3. Xoay vòng, thu hồi và hủy

- **Rotate identity key:** cấp phát public key/chứng chỉ mới cho verifier trước khi chuyển signer; xử lý những phiên hiện tại và cache trust.
- **Revoke identity hoặc PSK bị lộ:** chặn việc thiết lập phiên mới, đánh giá cần đóng phiên cũ, thu hồi token/ticket và điều tra các handshake khả nghi.
- **Destroy ephemeral secret:** dọn theo phạm vi/khoảng đời phiên; không giữ trong backup hoặc dump nếu tránh được.
- **Destroy storage DEK/KEK:** không được suy từ việc kết thúc phiên AKE rằng khóa mã hóa dữ liệu lưu trữ cũng có thể xóa. Phải kiểm kê ciphertext, wrapped DEK, replica và backup.

**Forward secrecy** chỉ nói về ảnh hưởng của sự cố khóa dài hạn đối với một số phiên đã hoàn tất theo mô hình cụ thể; nó **không thay thế** phản ứng khi traffic key hiện tại hoặc thiết bị endpoint bị xâm nhập.

## 9. KMS/HSM, envelope encryption và phân quyền

**KMS (Key Management Service)** quản lý key usage, chính sách và nhật ký. **HSM (Hardware Security Module)** có thể bảo vệ private key danh tính và thực hiện ký trong ranh giới phần cứng. Một giải pháp AKE có thể sử dụng KMS/HSM cho **khóa ký dài hạn**, nhưng không có nghĩa mọi ephemeral ECDH private key bắt buộc được tạo trong HSM; điều đó phụ thuộc giao thức, hiệu năng và threat model.

~~~text
                      KMS / HSM
                   Identity signing key
                            |
                            v
TLS 1.3 / mTLS / AKE ---- Xác thực đối tác
        |
        +---- Ephemeral DH/KDF -> Session traffic keys
        |                             |
        |                             +-- AES-GCM bảo vệ dữ liệu trên đường truyền
        |
        +---- Ứng dụng được xác thực -> Kiểm tra quyền truy cập
                                      |
                                      v
                                  KMS unwrap DEK
                                      |
                                      v
                              AES-GCM bảo vệ dữ liệu lưu trữ
~~~

**AKE giải quyết thiết lập khóa và danh tính ở kênh truyền**, còn **envelope encryption** sử dụng DEK/KEK để quản lý khóa cho dữ liệu lưu trữ. Hai mô hình bổ sung nhau; không dùng traffic key của phiên như một DEK lâu dài cho database, và không coi có quyền unwrap DEK là chứng minh đã xác thực mọi peer trên mạng.

Ngay cả private key **non-exportable** trong HSM vẫn có thể bị lạm dụng nếu một workload có quyền gọi API **Sign** không bị kiểm soát. Phân quyền nên bao gồm workload identity, mục đích, key ID, môi trường, giới hạn thao tác, điều kiện phê duyệt nếu phù hợp và ghi audit.

## 10. Tình huống thực tế: Mutual TLS giữa hai dịch vụ

Giả sử **Order Service** trao đổi đơn hàng với **Billing Service** và tổ chức yêu cầu **mTLS** để xác thực hai workload.

**Mục tiêu:** bảo vệ dữ liệu qua mạng, xác minh đúng service identity, tránh giả mạo endpoint; sau đó kiểm tra quyền đọc/ghi đơn hàng theo tenant.

**Quy trình thiết kế:**

1. Mỗi service có private key/certificate danh tính riêng được cấp qua hệ thống PKI hoặc identity provider đáng tin; certificate gắn với service identity.
2. Client Order Service kết nối Billing Service và kiểm tra server certificate, chuỗi tin cậy, tên dịch vụ và chính sách usage.
3. Billing Service yêu cầu client certificate, kiểm tra chứng chỉ Order Service và áp chính sách chỉ workload phù hợp mới được kết nối.
4. TLS 1.3 dùng key schedule/handshake để thiết lập khóa traffic theo giao thức, bao gồm các bước xác thực và Finished thích hợp.
5. Ứng dụng kiểm tra **Order Service được phép thao tác trên tenant/order ID nào**, tách biệt với việc chứng chỉ hợp lệ.
6. Nếu Billing Service cần đọc bản ghi đã mã hóa, ứng dụng dùng KMS unwrap **DEK** theo quyền phù hợp; AKE không thay thế quyền dữ liệu.
7. Khi certificate sắp hết hạn, phát hành/cấp phát khóa mới trước; cập nhật trust và triển khai chuyển tiếp có giám sát.
8. Audit các lỗi handshake, danh tính peer, policy decision, phiên bản chứng chỉ và hành động dùng KMS, nhưng không ghi session key hay private key.

**Tấn công A – cert đúng nhưng không được phép:** Một service cùng tổ chức có chứng chỉ hợp lệ muốn đọc đơn hàng tenant khác. mTLS chỉ xác thực service; authorization phải từ chối dữ liệu ngoài phạm vi.

**Tấn công B – server certificate giả:** Kẻ tấn công tạo chứng chỉ tự ký ghi tên Billing Service. Nếu client tắt kiểm tra trust hoặc hostname, có thể kết nối với endpoint giả dù TLS vẫn mã hóa traffic. Cần **kiểm tra trust anchor và identity**.

**Tấn công C – khóa xác thực bị lộ:** Kẻ có quyền ký hoặc private key client có thể mạo danh Order Service trong phạm vi chính sách. Phải thu hồi danh tính/khóa, cập nhật consumer trust và đánh giá phiên đã bị ảnh hưởng.

**Tấn công D – khóa lưu trữ lộ:** Nếu DEK trong database bị lộ, việc thiết lập AKE/mTLS tốt không bảo vệ lại ciphertext cũ. Cần thay DEK và đánh giá re-encrypt theo quy trình sự cố.

## 11. Các lỗi thường gặp khi thiết kế AKE

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Chạy ECDH rồi tự tuyên bố đã xác thực | MITM có thể thay public key và đọc dữ liệu. | Xác thực peer bằng chứng chỉ/chữ ký/PSK/PAKE theo giao thức chuẩn. |
| Tin public key lấy trực tiếp từ cùng thông điệp chưa xác thực | Chữ ký của kẻ giả vẫn Verify hợp lệ dưới khóa họ tự đưa. | Trust store/PKI/pinning và kiểm tra đúng danh tính kỳ vọng. |
| Chỉ ký một public key tạm thời, bỏ qua vai trò và thuật toán | Dễ bị tái sử dụng chữ ký sai phiên/giao thức hoặc nhầm vai trò. | Ký/xác thực transcript đầy đủ, domain separation và canonical encoding. |
| Chỉ so sánh hai shared secrets | Không kiểm tra đúng người, thời hạn, replay, downgrade hay key confirmation. | Kiểm thử trạng thái và toàn bộ protocol/security properties. |
| Dùng HKDF nhưng không đưa context vào key schedule | Có thể reuse khóa giữa nhiều chức năng hoặc phiên. | Key labels riêng, transcript hash và role/context binding. |
| Dùng cùng AES-GCM key cho hai chiều và trùng nonce | Mất bảo mật dữ liệu và xác thực AEAD. | Khóa/nonce space riêng từng chiều, kiểm soát counter/key update. |
| Tưởng Finished MAC tự xác thực đối tác | Kẻ MITM cũng có thể xác nhận khóa do họ thiết lập. | Xác thực identity riêng trước khi tin đối tác. |
| Chấp nhận thuật toán, key ID, cert URL từ input không tin cậy | Algorithm confusion, trust substitution, downgrade. | Allowlist và nguồn trust độc lập được quản lý. |
| Coi PSK từ mật khẩu yếu tương đương khóa ngẫu nhiên | Dễ bị dò nếu không có giao thức chống đoán mật khẩu. | PAKE chuẩn hoặc PSK entropy cao được cấp phát an toàn. |
| Không kiểm tra public key/secret không hợp lệ | Dẫn xuất từ vật liệu sai, kết quả yếu hoặc khó phát hiện lỗi. | Dùng provider/protocol kiểm tra hợp lệ và fail closed. |
| Ghi secret phiên/ephemeral key vào log | Có thể phá forward secrecy và lộ traffic. | Không log key material; hạn chế dump/backup nhạy cảm. |
| Dùng TLS nhưng tắt hostname/cert verification | Vẫn có thể liên lạc với endpoint giả. | Cấu hình verifier đúng trust anchor và service identity. |
| Coi chứng chỉ client hợp lệ là quyền đọc tất cả tenant | Lỗ hổng phân quyền chéo tenant. | Kiểm tra authorization ở tầng nghiệp vụ. |
| Tin rằng mTLS/TLS tự mã hóa database | Dữ liệu lưu trữ vẫn cần DEK/KEK và chính sách riêng. | Envelope encryption và KMS ACL khi phù hợp. |
| Xoay KEK rồi bỏ qua DEK đã lộ | Ciphertext cũ vẫn mở được bằng DEK lộ. | Đánh giá rotate DEK và re-encrypt. |
| Xóa identity key/DEK trước khi xét phụ thuộc | Gián đoạn hoặc không khôi phục được dữ liệu. | Kiểm kê phiên, chứng chỉ, bản mã/backup và retention. |

## 12. Checklist đánh giá một thiết kế AKE

Trước khi chấp nhận một kiến trúc thiết lập khóa có xác thực, hãy trả lời:

1. **Threat model:** có kẻ nghe lén, MITM, replay, giả mạo identity, compromise endpoint hay KMS credential không?
2. **Authentication scope:** ai xác thực ai? Một chiều hay hai chiều? Danh tính nào được gắn với public key?
3. **Trust anchor:** public key/chứng chỉ/PSK đến từ nguồn nào và được quản lý/thu hồi như thế nào?
4. **Protocol:** sử dụng TLS 1.3, Noise, PAKE hoặc một chuẩn phù hợp nào? Mode được chọn có đáp ứng tính chất cần thiết không?
5. **Algorithm agility:** phiên bản và thuật toán có allowlist và chống downgrade không?
6. **Transcript:** đã ràng buộc tất cả ephemeral keys, identity, role, algorithm, nonce và context quan trọng chưa?
7. **KDF:** có dùng KDF chuẩn, dẫn xuất khóa độc lập theo chiều và mục đích không?
8. **Key confirmation:** có cần Finished/proof chứng minh peer đã hoàn tất nắm khóa chưa?
9. **Key lifetime:** ephemeral keys, identity keys và session keys có được cấp phát/xóa/rotate đúng không?
10. **Replay/key usage:** handshake freshness, session tickets, 0-RTT và AES-GCM nonce/counter đã được kiểm soát chưa?
11. **Failure handling:** khi lỗi chữ ký, chứng chỉ, transcript, shared secret hoặc key confirmation, có từ chối toàn bộ handshake không?
12. **Authorization:** peer đã xác thực có thật sự được phép làm hành động thuộc tenant/object đó không?
13. **Audit:** ai đã cấp khóa, thay chính sách trust, gọi Sign, sử dụng KMS và xử lý sự cố? Có tránh log secret không?
14. **Recovery:** khi private key/PSK lộ, có thể cập nhật trust, đóng phiên, thay khóa và xử lý dữ liệu phụ thuộc mà không mất dữ liệu ngoài ý muốn không?

## 13. Câu hỏi tự kiểm tra

1. **Authenticated key agreement** bổ sung điều gì so với X25519/ECDH thuần?
2. Làm sao Mallory thực hiện MITM khi hai phía chỉ trao đổi public key không xác thực?
3. **Peer authentication** và **explicit key confirmation** khác nhau ở mục tiêu gì?
4. Vì sao chữ ký trên một public key chưa chắc đủ nếu không ràng buộc transcript, thuật toán và role?
5. **Unknown Key-Share (UKS)** là gì và vì sao hai bên cùng key vẫn có thể sai danh tính?
6. **KCI** cần được phân tích trong loại giao thức nào? Vì sao chỉ dùng X25519 không thể tự khẳng định chống KCI?
7. Muốn có **forward secrecy**, khóa ephemeral cần được tạo, dùng và xóa thế nào?
8. Vì sao cần traffic keys riêng cho client→server và server→client?
9. TLS 1.3 chỉ xác thực server khi nào, và khi nào cần **mTLS**?
10. Vì sao một API HSM ký bằng private key non-exportable vẫn có nguy cơ bị lạm dụng?
11. **HPKE base mode** có xác thực người gửi không? Public key của bên nhận cần được bảo vệ ra sao?
12. Khi mTLS thành công, ứng dụng có cần kiểm tra quyền tenant không?
13. AKE có thay thế envelope encryption cho dữ liệu lưu trữ không?
14. Nếu private key danh tính bị lộ, cần đánh giá những phiên, chứng chỉ và workload nào?

**Ghi nhớ:** **Authenticated key agreement** kết hợp việc tạo **shared secret** với **xác thực đúng đối tác và ràng buộc phiên/giao thức**. Tính an toàn đến từ cả **trust anchor, transcript, chữ ký hoặc PSK, KDF, key confirmation, quản lý nonce và key lifetime**, không chỉ từ một phép ECDH. Trong hệ thống thực tế, ưu tiên giao thức đã chuẩn hóa như **TLS 1.3/mTLS** và thực hiện nghiêm việc **quản lý khóa KMS/HSM, phân quyền, xoay vòng, thu hồi, hủy và kiểm toán**.
