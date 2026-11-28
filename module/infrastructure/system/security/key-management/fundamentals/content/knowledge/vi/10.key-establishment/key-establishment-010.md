# Ephemeral key agreement (Thỏa thuận khóa tạm thời)

## 1. Ephemeral key agreement là gì?

**Ephemeral key agreement** là quá trình hai hoặc nhiều bên sử dụng **vật liệu khóa tạm thời** để cùng thiết lập một bí mật dùng cho một phiên hoặc phạm vi ngắn hạn, **mà không cần truyền bí mật phiên ở dạng rõ qua kênh liên lạc**. Trong các giao thức thông dụng, mỗi bên sinh một cặp khóa tạm thời, trao đổi **public key** và dùng private key của mình cùng public key của bên kia để tính một **shared secret**.

Trường hợp tiêu biểu là **ephemeral Diffie–Hellman**:

- **DHE**: Diffie–Hellman tạm thời trên nhóm hữu hạn phù hợp.
- **ECDHE**: Elliptic-Curve Diffie–Hellman tạm thời trên nhóm đường cong elliptic.
- **X25519**: một cơ chế thỏa thuận khóa trên Curve25519, được sử dụng rộng rãi trong các thiết kế giao thức hiện đại.

Một cách diễn giải ngắn gọn:

~~~text
Client                                    Server
------                                    ------
Sinh private ephemeral a                  Sinh private ephemeral b
Tính public ephemeral A                   Tính public ephemeral B

                A -------------------->
                  <-------------------- B

Shared secret Z = DH(a, B)                 Z = DH(b, A)
                  \                         /
                   \___ Hai giá trị khớp __/

           KDF(Z, transcript, context) -> session keys
~~~

**Điều kiện quan trọng:** Khả năng tạo cùng shared secret **không tự xác thực danh tính đối tác**. Nếu kẻ tấn công thay public key trên đường truyền, mỗi bên có thể thỏa thuận một bí mật riêng với kẻ đó. Vì vậy một triển khai an toàn cần thêm **xác thực và ràng buộc bản ghi bắt tay (transcript)**.

Trong chương **Key establishment** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề này liên kết vòng đời khóa (tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi, hủy) với mật mã bất đối xứng, chữ ký số, KMS/HSM, dẫn xuất khóa, mã hóa đối xứng, IAM và kiểm toán. Mục tiêu cuối cùng thường là tạo **khóa phiên** dùng cho một cơ chế mã hóa có xác thực như AES-GCM, không phải sử dụng raw shared secret trực tiếp như một AES key.

## 2. Những thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Key agreement** | Các bên góp thông tin để tính cùng bí mật theo giao thức | ECDH, X25519 |
| **Key transport** | Một bên tạo khóa rồi truyền nó dưới dạng được bảo vệ đến bên kia | Bọc khóa/đưa khóa qua cơ chế được chuẩn hóa |
| **Ephemeral private key** | Bí mật tạm thời dùng trong một phiên/bắt tay | Số vô hướng DH/ECDH chỉ tồn tại cho một handshake |
| **Ephemeral public key** | Giá trị công khai tương ứng, thường gửi cho đối tác | EC public point hoặc X25519 public bytes |
| **Static key** | Khóa được dùng qua nhiều phiên hoặc giao dịch | Private key ký chứng chỉ máy chủ |
| **Shared secret (Z)** | Giá trị hai bên tính được từ key agreement | Kết quả ECDH/X25519 trước KDF |
| **KDF** | Hàm dẫn xuất từ bí mật thành keying material theo ngữ cảnh | HKDF-SHA-256 |
| **Session key / traffic key** | Khóa dùng cho phiên hoặc một hướng truyền dữ liệu | AES-128-GCM key cho client → server |
| **Transcript** | Chuỗi thông điệp/thông tin liên quan quá trình bắt tay | Danh tính, thuật toán, ephemeral public keys, nonce |
| **Forward secrecy** | Tính chất bảo vệ bí mật phiên quá khứ trước việc lộ khóa xác thực dài hạn về sau, với các giả định cụ thể | TLS dùng (EC)DHE khi thiết kế và vận hành đúng |

**Không đồng nhất ephemeral key với session key.** Một cặp private/public ephemeral thường là **đầu vào của thỏa thuận khóa**; còn traffic key được dẫn xuất từ shared secret và ngữ cảnh. Một phiên có thể dùng nhiều khóa khác nhau theo từng hướng, mục đích hoặc epoch.

**Không đồng nhất ephemeral với không có quản lý khóa.** Dù tuổi thọ ngắn, những bí mật này vẫn cần sinh bằng CSPRNG đáng tin, được sử dụng đúng một phạm vi, hạn chế rò rỉ và xóa khi không còn cần thiết.

## 3. Cơ chế nền tảng: Diffie–Hellman

### 3.1. DHE trên nhóm hữu hạn

Trong mô hình Diffie–Hellman cổ điển, hai bên biết tham số nhóm công khai là **p** và **g**; client sinh bí mật **a**, server sinh bí mật **b**:

\[
A = g^a \bmod p,\qquad B = g^b \bmod p
\]

Sau khi trao đổi A và B:

\[
Z_{\text{client}} = B^a \bmod p,\qquad
Z_{\text{server}} = A^b \bmod p
\]

Hai biểu thức bằng nhau:

\[
Z = g^{ab} \bmod p.
\]

Bí mật **a**, **b** không được gửi trên mạng. Sự bảo mật dựa vào bài toán tính toán trên **nhóm được chọn đúng**, phương pháp sinh số bí mật và giao thức xác thực. Không nên tự chọn p/g hoặc nhóm nhỏ theo cảm tính; hãy dùng những nhóm và thư viện đã được chuẩn hóa.

### 3.2. ECDHE trên đường cong elliptic

Với cơ chế ECDH trên một nhóm elliptic phù hợp, ký hiệu:

\[
A=aG,\qquad B=bG
\]

Trong đó G là điểm sinh của nhóm, a và b là private scalar tạm thời. Hai bên tính:

\[
Z_{\text{client}}=aB=abG,\qquad
Z_{\text{server}}=bA=baG.
\]

Hai phía có cùng kết quả toán học. Trong triển khai thực tế, **cách mã hóa shared secret, quy tắc chấp nhận public key và xử lý lỗi** phụ thuộc vào curve/thuật toán. Không được tự coi công thức khái niệm là đủ để xây một giao thức an toàn.

### 3.3. X25519 có gì đặc biệt?

**X25519** là cơ chế Diffie–Hellman dùng Curve25519 theo các quy tắc định nghĩa riêng. Nó được thiết kế để hỗ trợ triển khai hiệu quả, tránh một số lỗi xử lý điểm so với việc tự xây phép tính EC tổng quát.

Tuy nhiên:

- Phải sử dụng **provider và thư viện hỗ trợ đúng X25519**.
- Phải xử lý public key không hợp lệ/đầu ra bất thường theo yêu cầu của giao thức và thư viện. Với X25519, **shared secret toàn byte 0 phải bị từ chối**.
- Không được nhầm **X25519** với **Ed25519**: X25519 dùng cho thỏa thuận khóa; Ed25519 dùng cho chữ ký số.
- Không được lấy private key ký Ed25519 rồi coi như private key X25519 có thể thay thế trực tiếp chỉ bằng việc đổi tên thuật toán.

## 4. Ephemeral khác static key agreement như thế nào?

| Mô hình | Khóa tham gia | Tính chất chính | Rủi ro/giới hạn |
|---|---|---|---|
| **Static–static DH** | Hai bên dùng khóa thỏa thuận dài hạn qua nhiều phiên | Có thể thiết lập bí mật chung ổn định | Nếu khóa dài hạn bị lộ, dữ liệu cũ có thể chịu ảnh hưởng tùy cách tạo traffic key |
| **Ephemeral–ephemeral DH** | Mỗi bên dùng cặp khóa tạm thời cho phiên | Hỗ trợ thiết kế forward secrecy | Nếu thiếu xác thực, dễ bị man-in-the-middle |
| **Static–ephemeral DH** | Một bên static, bên kia ephemeral | Phù hợp một số giao thức/ứng dụng | Mức forward secrecy phụ thuộc vai trò static, bí mật bị lộ và cách dùng |
| **(EC)DHE + chữ ký xác thực** | Khóa tạm thời tạo shared secret; khóa ký dài hạn xác thực handshake | Có thể kết hợp danh tính ổn định với forward secrecy | Phải kiểm tra transcript, chứng chỉ/khóa công khai và quy tắc xác thực |
| **(EC)DHE + PSK** | Bí mật chia sẻ xác thực hoặc góp vào key schedule | Một số giao thức hỗ trợ cả PSK và DHE | Rủi ro nếu PSK yếu, thiếu ràng buộc ngữ cảnh hoặc dùng sai mode |

Một **static signing key** không tự làm mất forward secrecy. Ví dụ, máy chủ có chứng chỉ với private key dùng nhiều tháng để ký các lần bắt tay, trong khi các phiên tạo bí mật qua (EC)DHE mới. Hai loại khóa có nhiệm vụ khác nhau:

- **Static signing key:** xác thực danh tính máy chủ hoặc một thông điệp bắt tay.
- **Ephemeral DH key:** tham gia thỏa thuận bí mật phiên.
- **Derived traffic key:** mã hóa/xác thực dữ liệu phiên.

Ngược lại, một hệ thống mã hóa nhiều phiên trực tiếp bằng cùng secret tĩnh sẽ có phạm vi ảnh hưởng lớn hơn nếu secret bị lộ.

## 5. Forward secrecy: lợi ích và điều kiện

**Forward secrecy** là thuộc tính giao thức giúp **nội dung những phiên trước** vẫn được bảo vệ trước việc **khóa xác thực dài hạn** bị lộ sau đó, trong mô hình đối thủ chỉ ghi lại lưu lượng quá khứ và chưa có các bí mật phiên cần thiết.

Ví dụ:

~~~text
Ngày 1:
  Client và server dùng ECDHE tạo traffic key K1.
  K1 mã hóa phiên S1.
  Hai bên bỏ ephemeral private keys khi hết nhu cầu.

Ngày 30:
  Private key chứng chỉ của server bị lộ.

Kỳ vọng trong giao thức có forward secrecy:
  Attacker có lưu ciphertext S1 cũng không suy ra K1
  chỉ từ private key xác thực dài hạn vừa lộ.
~~~

**Forward secrecy không phải cam kết mọi dữ liệu quá khứ đều an toàn bất kể sự cố nào**. Nó phụ thuộc vào các giả định:

1. Ephemeral private keys của phiên cũ **không bị lấy đi** và đã được loại bỏ trong phạm vi hệ thống có thể kiểm soát.
2. Traffic keys, shared secrets, bản rõ và các log key material của phiên cũ **không bị lộ**.
3. Giao thức thực sự dẫn xuất traffic keys từ đóng góp ephemeral phù hợp và có xác thực đúng.
4. Các thuật toán, nhóm, KDF và cài đặt không có lỗi phá vỡ giả định an toàn.
5. Bên tấn công không chủ động mạo danh thành công **ngay thời điểm handshake** do chứng chỉ/khóa xác thực đã bị chiếm quyền.

**Forward secrecy khác post-compromise security (khả năng phục hồi bảo mật sau xâm phạm).** Một hệ thống không tự lấy lại an toàn sau khi kẻ tấn công có quyền điều khiển phiên hiện tại chỉ vì nó dùng ephemeral keys. Các cơ chế như cập nhật khóa, tái xác thực hoặc giao thức ratchet có mục tiêu khác.

### 5.1. Điều gì xảy ra khi private signing key bị lộ?

Nếu private signing key của máy chủ bị lộ về sau, những phiên **ECDHE đã hoàn thành** có thể vẫn được bảo vệ như mô hình trên. Nhưng từ thời điểm bị chiếm quyền, kẻ tấn công có thể **mạo danh trong phiên mới** nếu verifier còn tin khóa cũ. Vì vậy hệ thống phải **thu hồi chứng chỉ/niềm tin, thay signing key, cập nhật verifier và xử lý token/phiên liên quan**, không chỉ dựa vào forward secrecy.

## 6. Vì sao key agreement cần xác thực?

**Diffie–Hellman trần (unauthenticated DH)** chỉ giúp hai bên tính được một bí mật chung với *bên đã trao đổi public key*. Nó không chứng minh bên đó là ai.

### 6.1. Tấn công man-in-the-middle

~~~mermaid
sequenceDiagram
    participant C as Client
    participant M as Attacker
    participant S as Server

    C->>M: Public ephemeral A
    M->>S: Public ephemeral M1 (thay A)
    S->>M: Public ephemeral B
    M->>C: Public ephemeral M2 (thay B)

    Note over C,M: Client tính Z_CM
    Note over M,S: Server tính Z_MS
    Note over M: Attacker biết cả hai shared secrets
~~~

Kẻ tấn công đứng giữa thay public key của cả hai bên, tạo hai bí mật khác nhau và có thể giải mã/chỉnh sửa/chuyển tiếp lưu lượng nếu hệ thống dùng các khóa đó mà không phát hiện.

**Kết luận:** Dùng X25519 hoặc ECDHE mạnh **không tự loại bỏ MITM**. Phải xác thực public key ephemeral, transcript hoặc danh tính theo một giao thức đã được kiểm chứng.

### 6.2. Những mô hình xác thực

- **Chữ ký số:** máy chủ ký thông tin bắt tay đã được ràng buộc, verifier kiểm tra bằng public signing key/chứng chỉ đáng tin. TLS 1.3 là ví dụ giao thức đã chuẩn hóa.
- **PSK/MAC:** hai bên có secret được cấp an toàn, dùng cơ chế xác thực transcript/key schedule phù hợp giao thức.
- **Xác thực hai chiều:** cả client và server cùng chứng minh danh tính nếu kiến trúc yêu cầu.
- **Out-of-band verification:** xác nhận fingerprint hoặc danh tính public key qua kênh đáng tin trong các giao thức được thiết kế cho mục đích này.

Không chỉ ký một ephemeral public key độc lập rồi cho rằng mọi thứ đã an toàn: các giao thức cần ràng buộc **vai trò, thuật toán, danh tính hai bên, phiên bản, public keys, nonce và nội dung transcript** để chống thay đổi ngữ cảnh và tấn công downgrade/unknown-key-share.

## 7. Transcript binding, key confirmation và chống replay

**Transcript** là chuỗi thông tin đã được trao đổi trong quá trình thiết lập khóa. Một thiết kế có thể đưa hash của transcript vào key schedule, xác thực nó bằng chữ ký/MAC và liên kết các key được dẫn xuất với phiên tương ứng.

~~~text
Protocol version  | cipher suite | role labels
Client identity   | server identity
Client ephemeral public key A
Server ephemeral public key B
Client/server random values
Other negotiated parameters
                  |
                  v
       Authenticated transcript hash
                  |
                  +--> Signature/MAC theo giao thức
                  |
                  +--> HKDF context / key schedule
                  |
                  +--> Key confirmation
~~~

Ba yêu cầu riêng biệt:

1. **Transcript binding:** khóa phiên/chứng cứ xác thực được gắn với nội dung bắt tay cụ thể, không chấp nhận tùy tiện một public key hoặc thuật toán bị thay.
2. **Key confirmation:** một hoặc cả hai bên có bằng chứng bên kia **sở hữu khóa cần thiết** theo giao thức, thường qua MAC/Finished hoặc thông điệp được xác thực.
3. **Anti-replay:** không chấp nhận phát lại yêu cầu/phiên cũ theo quy tắc giao thức. Việc chữ ký hoặc MAC hợp lệ không tự có nghĩa bản tin chưa từng được xử lý.

**Không nên tự tạo giao thức bằng cách nối chuỗi các trường không rõ độ dài.** Cần encoding, thứ tự, domain separation, phiên bản và quy tắc xác thực được định nghĩa chính xác. Tốt nhất dùng giao thức được chuẩn hóa như TLS thay vì tự xây ECDHE qua các API riêng lẻ.

## 8. Từ shared secret đến session keys: vai trò của HKDF

Đầu ra của thỏa thuận khóa thường được gọi là **shared secret Z**. Ứng dụng không nên dùng trực tiếp Z như một AES key và cũng không nên đơn giản cắt vài byte đầu rồi giả định an toàn. Một **KDF đã được chuẩn hóa** thường chuyển Z thành keying material thích hợp cho thuật toán và ngữ cảnh.

**HKDF** (*HMAC-based Key Derivation Function*) thường được mô tả qua hai bước:

\[
\operatorname{PRK} = \operatorname{HKDF\!-\!Extract}(salt,Z)
\]

\[
\operatorname{OKM} = \operatorname{HKDF\!-\!Expand}(PRK,info,L).
\]

- **Salt:** giá trị theo thiết kế của giao thức, có thể công khai. Không phải private signing key; không thay thế xác thực.
- **Info:** ngữ cảnh và mục đích của khóa, ví dụ phiên bản giao thức, transcript hash, vai trò **client→server** hoặc **server→client**.
- **L:** số byte cần dẫn xuất, phụ thuộc thuật toán/sơ đồ.
- **PRK/OKM:** những byte được dẫn xuất, cần bảo vệ theo vai trò; nên tránh lưu những bí mật không cần thiết.

~~~mermaid
flowchart TD
    A["Ephemeral DH shared secret Z"] --> E["HKDF-Extract"]
    B["Salt theo giao thức"] --> E
    E --> P["Pseudorandom key PRK"]
    P --> X["HKDF-Expand"]
    C["Transcript hash + role labels + purpose"] --> X
    X --> K1["Client-to-server traffic key"]
    X --> K2["Server-to-client traffic key"]
    X --> IV["IV / nonce-related material nếu giao thức quy định"]
~~~

**Phân tách khóa theo mục đích và hướng truyền là nguyên tắc quan trọng.** Hai chiều truyền nên dùng traffic keys, IV/sequence state và nhãn dẫn xuất khác nhau theo giao thức, tránh dùng cùng material ngoài ý muốn.

**Lưu ý:** KDF không thể "xác thực" một public key bị MITM nếu transcript và danh tính vẫn không được kiểm tra. HKDF giúp dẫn xuất và tách biệt khóa; nó **không thay thế bước xác thực handshake**.

## 9. Luồng handshake kết hợp ECDHE, chữ ký và AEAD

Một sơ đồ tổng quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server

    Note over C: Sinh ephemeral key pair c
    C->>S: ClientHello, A, supported groups
    Note over S: Sinh ephemeral key pair s
    S->>C: B, negotiated parameters
    S->>C: Certificate + signature trên transcript
    Note over C: Verify certificate, identity, signature
    Note over C,S: Tính Z bằng DH và derive traffic keys bằng KDF
    C->>S: Key confirmation / Finished
    S->>C: Key confirmation / Finished
    Note over C,S: Chuyển dữ liệu bằng AEAD theo sequence/nonce rules
    Note over C,S: Hủy giảm thiểu ephemeral secrets khi hết nhu cầu
~~~

Đây là **sơ đồ khái niệm**, không phải bản sao thứ tự chính xác của từng thông điệp TLS. Trong giao thức chuẩn, thứ tự, các giá trị được ký, xác thực Finished, key schedule và transcript đều được quy định nghiêm ngặt.

**Ví dụ TLS 1.3:** TLS thường kết hợp (EC)DHE hoặc cơ chế thiết lập khóa được hỗ trợ với xác thực máy chủ bằng chứng chỉ/chữ ký, dùng một key schedule và AEAD cho lưu lượng. Chi tiết có thể khác khi sử dụng PSK/resumption hoặc những chế độ được đàm phán; không nên suy luận forward secrecy chỉ từ việc xuất hiện tên một thuật toán trong cấu hình.

### 9.1. Sự khác nhau giữa handshake keys và application traffic keys

Nhiều giao thức sinh ra **nhiều key epoch**, chẳng hạn khóa bảo vệ handshake và khóa bảo vệ dữ liệu ứng dụng. Key material được dẫn xuất theo nhãn/role riêng để tránh dùng nhầm khóa. Khi cập nhật traffic keys, đây là **key update theo giao thức**, không nhất thiết là một lần trao đổi ephemeral DH mới.

Đừng giả định mọi traffic-key update sẽ tái tạo forward secrecy hoặc sửa được trạng thái đã bị xâm phạm; điều đó phụ thuộc giao thức và nguồn entropy mới.

## 10. Java JCA: minh họa thỏa thuận khóa X25519

**Java 17+** hỗ trợ các API X25519 thông qua những provider có triển khai phù hợp. Ví dụ sau chạy **hai bên trong cùng một tiến trình** nhằm minh họa rằng hai private keys tạm thời khác nhau có thể tạo **cùng shared secret**. Nó còn minh họa bước **HKDF-SHA-256** để dẫn xuất một session key, nhưng **không có xác thực danh tính hay mạng**, do đó **không phải giao thức an toàn sẵn dùng trong sản xuất**.

### 10.1. Mã Java

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.util.Arrays;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class EphemeralX25519Example {
    private static byte[] sharedSecret(
            java.security.PrivateKey ownPrivate,
            PublicKey peerPublic) throws Exception {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(ownPrivate);
        ka.doPhase(peerPublic, true);
        byte[] z = ka.generateSecret();

        // X25519: cần từ chối shared secret toàn zero.
        // Provider có thể đã từ chối; kiểm tra này bổ sung cho demo.
        int acc = 0;
        for (byte value : z) acc |= value & 0xff;
        if (acc == 0) {
            Arrays.fill(z, (byte) 0);
            throw new IllegalStateException("Invalid X25519 shared secret");
        }
        return z;
    }

    private static void updatePart(
            MessageDigest digest, byte[] part) {
        digest.update(ByteBuffer.allocate(4).putInt(part.length).array());
        digest.update(part);
    }

    private static byte[] transcriptHash(
            PublicKey clientPublic, PublicKey serverPublic)
            throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        updatePart(md, "demo-key-agreement/v1".getBytes(
            StandardCharsets.UTF_8));
        // Gắn vai trò theo thứ tự client trước, server sau.
        updatePart(md, clientPublic.getEncoded());
        updatePart(md, serverPublic.getEncoded());
        return md.digest();
    }

    private static byte[] hkdfExtract(
            byte[] salt, byte[] inputKeyMaterial) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(salt, "HmacSHA256"));
        return mac.doFinal(inputKeyMaterial);
    }

    private static byte[] hkdfExpand(
            byte[] prk, byte[] info, int length) throws Exception {
        final int hashLength = 32;
        if (length < 1 || length > 255 * hashLength) {
            throw new IllegalArgumentException("Invalid HKDF length");
        }

        byte[] okm = new byte[length];
        byte[] previous = new byte[0];
        int offset = 0;
        int counter = 1;

        try {
            while (offset < length) {
                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(new SecretKeySpec(prk, "HmacSHA256"));
                mac.update(previous);
                mac.update(info);
                mac.update((byte) counter);
                byte[] block = mac.doFinal();

                Arrays.fill(previous, (byte) 0);
                previous = block;

                int size = Math.min(block.length, length - offset);
                System.arraycopy(block, 0, okm, offset, size);
                offset += size;
                counter++;
            }
            return okm;
        } finally {
            Arrays.fill(previous, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        // Mỗi phía tạo cặp khóa tạm thời RIÊNG.
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("X25519");
        KeyPair client = generator.generateKeyPair();
        KeyPair server = generator.generateKeyPair();

        byte[] clientZ =
            sharedSecret(client.getPrivate(), server.getPublic());
        byte[] serverZ =
            sharedSecret(server.getPrivate(), client.getPublic());

        try {
            if (!MessageDigest.isEqual(clientZ, serverZ)) {
                throw new IllegalStateException("Key agreement mismatch");
            }

            // Transcript hash là public context, KHÔNG phải xác thực.
            byte[] context =
                transcriptHash(client.getPublic(), server.getPublic());

            byte[] clientPrk = hkdfExtract(context, clientZ);
            byte[] serverPrk = hkdfExtract(context, serverZ);

            try {
                byte[] label = "demo:client-to-server:aes-key"
                    .getBytes(StandardCharsets.UTF_8);
                byte[] clientKey = hkdfExpand(clientPrk, label, 32);
                byte[] serverKey = hkdfExpand(serverPrk, label, 32);
                try {
                    if (!MessageDigest.isEqual(clientKey, serverKey)) {
                        throw new IllegalStateException("HKDF mismatch");
                    }
                    System.out.println("X25519 + HKDF demo OK");
                } finally {
                    Arrays.fill(clientKey, (byte) 0);
                    Arrays.fill(serverKey, (byte) 0);
                }
            } finally {
                Arrays.fill(clientPrk, (byte) 0);
                Arrays.fill(serverPrk, (byte) 0);
            }
        } finally {
            Arrays.fill(clientZ, (byte) 0);
            Arrays.fill(serverZ, (byte) 0);
        }

        // Không có authentication hoặc network trong ví dụ này.
        // Không sử dụng như một giao thức truyền dữ liệu production.
    }
}
~~~

### 10.2. Giải thích các chi tiết quan trọng

1. **KeyPairGenerator("X25519")** sinh các cặp khóa; mỗi phía chỉ giữ private key của chính mình, public key có thể truyền cho phía còn lại.
2. **KeyAgreement("X25519")** thực hiện thỏa thuận khóa. Hai phía thu được cùng **Z** khi public/private keys nhất quán.
3. **Kiểm tra all-zero** là một điều kiện quan trọng khi dùng X25519; provider có thể áp quy tắc từ chối trước khi trả shared secret.
4. **Transcript hash** chứa nhãn giao thức và public keys với ranh giới độ dài. Nó chỉ **ràng buộc ngữ cảnh cho bước HKDF trong demo**, **không có chữ ký/chứng chỉ** nên kẻ MITM vẫn có thể tạo hai phiên riêng biệt.
5. **HKDF-Extract** và **HKDF-Expand** tạo một khóa demo dài 32 byte có nhãn mục đích. Một giao thức thật phải định nghĩa chính xác salt, info, vai trò, transcript, output lengths và key confirmation.
6. **MessageDigest.isEqual** được dùng để so sánh byte có độ dài đã biết trong demo; không giải quyết bảo mật giao thức.
7. **Arrays.fill** chỉ xóa các mảng byte mà chương trình nắm giữ. Java/JCA/provider có thể giữ bản sao hoặc đối tượng private key không thể xóa hoàn toàn chỉ bằng GC hoặc xóa mảng. Không nên hứa bảo đảm zeroization tuyệt đối trong JVM.

**Quan trọng:** Đoạn mã **không tạo một kết nối bảo mật**. Nó thiếu xác thực public key, chống MITM, kiểm tra toàn bộ transcript, quy tắc chống replay, nonce/sequence và chính sách xử lý lỗi. Trong ứng dụng có mạng, **ưu tiên TLS 1.3 hoặc một giao thức được chuẩn hóa và thư viện đã được kiểm chứng**, không tự gửi hai public keys rồi dùng AES-GCM.

### 10.3. Vì sao không dùng shared secret làm AES key ngay?

Raw ECDH/X25519 output cần được xử lý theo **key schedule** của giao thức, không mặc định một khóa AES thích hợp. KDF giúp tách key cho từng mục đích và ràng buộc thông số phiên, đồng thời cho phép dẫn xuất nhiều keying materials từ cùng bí mật. Khi dùng trực tiếp Z, ứng dụng dễ mắc lỗi như:

- Không tách **client→server** và **server→client**.
- Dùng cùng material cho **AES encryption** và **HMAC** nếu không có thiết kế.
- Không ràng buộc protocol version, algorithm negotiation và transcript.
- Khó cập nhật thuật toán/định dạng mà không phá tương thích hoặc bảo mật.

## 11. AEAD và nonce: ephemeral agreement chưa đủ để bảo vệ dữ liệu

Sau khi dẫn xuất session key, giao thức có thể dùng **AES-GCM** hoặc **ChaCha20-Poly1305** để bảo vệ dữ liệu. Nhưng key agreement và AEAD giải quyết **hai lớp bài toán khác nhau**.

| Giai đoạn | Mục đích | Ràng buộc chính |
|---|---|---|
| **(EC)DHE / X25519** | Tạo bí mật phiên giữa hai bên | Private ephemeral an toàn, peer public key và transcript xác thực |
| **HKDF** | Dẫn xuất traffic keys và các giá trị cần thiết | Salt/info/domain separation đúng |
| **AEAD encrypt** | Mã hóa/xác thực dữ liệu | Key, nonce/sequence, AAD, tag, giới hạn sử dụng |
| **AEAD decrypt** | Kiểm tra tag trước khi chấp nhận dữ liệu | Sai tag/AAD/nonce phải bị từ chối |
| **Replay protection** | Chặn phát lại ciphertext hợp lệ | Sequence numbers, record epochs hoặc trạng thái giao thức |

**Forward secrecy không khắc phục việc tái sử dụng AES-GCM nonce.** Một traffic key được tạo bằng ECDHE vẫn có thể bị phá bảo mật nếu nhiều record bị mã hóa dưới cùng cặp **(key, nonce)**. Giao thức phải quản lý nonce và giới hạn số record cho mỗi traffic key.

Nếu một phiên có hai hướng truyền, mỗi hướng cần key/nonce schedule được ràng buộc phù hợp. Không tái sử dụng cùng key và nonce chỉ vì thông điệp đi theo hướng ngược lại.

## 12. Vai trò của KMS/HSM trong ephemeral key agreement

**KMS/HSM** thường quản lý **khóa dài hạn** và các thao tác mật mã có quyền truy cập. Chúng có thể hỗ trợ ECDH/key agreement trong những cấu hình nhất định, nhưng không mặc định mọi KMS cung cấp API X25519/DHE.

| Thành phần | Trách nhiệm thường gặp |
|---|---|
| **Ứng dụng và giao thức** | Điều phối handshake, xác thực danh tính, transcript, key confirmation và traffic encryption |
| **OS CSPRNG / provider Java** | Sinh ephemeral private scalars an toàn trong môi trường hỗ trợ |
| **KMS/HSM** | Bảo vệ static signing key, thực hiện Sign, quản lý IAM/audit; có thể thực hiện key agreement nếu API hỗ trợ |
| **Certificate / trust store** | Gắn static public signing key với danh tính đã xác thực |
| **KDF** | Dẫn xuất traffic keys từ Z và transcript theo giao thức |
| **AEAD / record layer** | Mã hóa dữ liệu, quản lý nonce và chống sửa đổi |
| **Audit/monitoring** | Ghi thao tác dùng khóa dài hạn, thay policy, lỗi handshake và sự kiện sự cố |

Một thiết kế TLS điển hình có thể để **private signing key** trong HSM, trong khi **ephemeral DH keys** được sinh và dùng bởi thư viện TLS trong RAM ứng dụng. Điều này có thể hợp lý nếu ranh giới tin cậy và bảo vệ bộ nhớ đáp ứng chính sách.

**Giới hạn:** KMS/HSM bảo vệ khóa ký nhưng **không tự ngăn một ứng dụng bị chiếm quyền yêu cầu Sign cho handshake giả mạo**. IAM, cấp quyền, xác thực workload, hạn mức, audit và bảo vệ tầng ứng dụng vẫn cần thiết.

### 12.1. Ephemeral agreement khác envelope encryption

- **Ephemeral agreement:** các bên thiết lập bí mật phiên qua DH/ECDH và dẫn xuất traffic keys.
- **Envelope encryption:** dữ liệu lưu trữ được mã hóa bằng **DEK**, DEK được bảo vệ bằng **KEK** trong KMS/HSM.
- **Digital signature:** private signing key tạo chữ ký để xác thực một đối tượng hoặc transcript; public key dùng Verify.

Chúng có thể cùng tồn tại, nhưng không thể thay thế chức năng cho nhau. **Không tự dùng static signing key làm DEK/KEK hay sử dụng trực tiếp raw DH secret như khóa lưu trữ lâu dài**.

## 13. Vòng đời ephemeral keys và session keys

Ephemeral không có nghĩa là **không cần vòng đời**. Tuổi thọ có thể chỉ kéo dài trong handshake hoặc phiên ngắn, nhưng vẫn phải kiểm soát việc tạo, sử dụng và hủy.

~~~mermaid
flowchart LR
    A["CSPRNG sinh ephemeral pair"] --> B["Gửi public share"]
    B --> C["Xác thực transcript/peer"]
    C --> D["DH -> shared secret Z"]
    D --> E["HKDF -> traffic keys"]
    E --> F["AEAD + record nonce/sequence"]
    F --> G["Key update / kết thúc phiên"]
    G --> H["Giảm thiểu lưu giữ, xóa secrets"]
    I["Static signing key trong KMS/HSM"] --> C
~~~

| Giai đoạn | Ephemeral key / session key | Liên hệ quản lý khóa |
|---|---|---|
| **Generation** | Sinh private ephemeral bằng CSPRNG/DRBG an toàn | Nguồn entropy và provider đáng tin |
| **Provisioning** | Công bố ephemeral public share, kiểm tra nhóm/encoding | Không cần gửi private key |
| **Authentication** | Xác thực peer và transcript | Chứng chỉ, chữ ký số/PSK, trust policy |
| **Usage** | Tính Z, HKDF, dùng traffic key và nonce theo giao thức | Không log secret, phân tách role/direction |
| **Key update** | Dẫn xuất khóa mới theo giao thức khi cần | Không nhầm update với một lần DH mới |
| **Revocation/termination** | Ngừng dùng khóa phiên, chấm dứt phiên đáng ngờ | Thu hồi static identity key/token/session tùy sự cố |
| **Destruction** | Giảm thiểu lưu giữ ephemeral private, Z, traffic keys | Zeroization best-effort, không lưu bí mật vào log/backups |

### 13.1. Có nên lưu ephemeral private key để debug?

**Không.** Ghi ephemeral secrets hoặc traffic keys vào file chẩn đoán có thể làm mất tác dụng của forward secrecy. Các công cụ TLS key logging có thể hữu ích trong môi trường thử nghiệm kiểm soát chặt, nhưng **không được bật tùy tiện trong sản xuất** hoặc dùng log đó như dữ liệu vận hành thông thường.

Trong Java, việc xóa mảng byte không bảo đảm xóa hoàn toàn private key trong provider/JVM. Cần giảm thời gian sống của đối tượng, hạn chế core dump/heap dump, phân quyền chẩn đoán, loại trừ secret khỏi telemetry và sử dụng runtime có bảo đảm phù hợp khi yêu cầu rất nghiêm ngặt.

### 13.2. Session resumption và việc dùng lại bí mật

Một giao thức có thể có **resumption token/ticket/PSK** để thiết lập phiên nhanh hơn. Đây là nhánh khác so với việc dùng một cặp ephemeral DH mới mỗi lần; mức forward secrecy phụ thuộc **cách resumption phối hợp PSK và (EC)DHE**, vòng đời ticket key và giao thức.

Không được giả định mọi lần "tạo session mới" đều dùng ephemeral private key độc lập; cần xem mode thực tế mà thư viện/giao thức đã đàm phán.

## 14. Các tấn công và lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách hạn chế |
|---|---|---|
| Chỉ trao đổi public keys, không xác thực đối tác | Bị **man-in-the-middle** | Dùng giao thức có xác thực transcript/chứng chỉ/PSK |
| Không kiểm tra nhóm, point/public key đầu vào | Đầu vào không hợp lệ hoặc nguy cơ tấn công nhóm con/đường cong tùy thuật toán | Dùng provider chuẩn và kiểm tra theo giao thức |
| Không từ chối all-zero X25519 shared secret | Có thể chấp nhận shared secret không hợp lệ | Áp dụng quy tắc từ chối all-zero |
| Sinh private ephemeral bằng RNG yếu | Kẻ tấn công suy ra shared secret/traffic key | CSPRNG, provider và key generation an toàn |
| Tái dùng ephemeral private key qua quá nhiều phiên ngoài thiết kế | Mất lợi ích cô lập phiên, mở rộng phạm vi lộ | Tuân thủ chính sách và giao thức; sinh mới khi yêu cầu |
| Dùng raw DH secret trực tiếp làm AES key | Thiếu tách khóa, ngữ cảnh và key schedule | HKDF/KDF đúng đặc tả |
| Không xác thực transcript/thuật toán đàm phán | Downgrade hoặc tráo đổi ngữ cảnh | Ký/MAC transcript theo giao thức |
| Một traffic key dùng hai hướng với cùng nonce | Phá bảo mật AEAD khi nonce trùng | Direction-specific key/nonce schedule |
| Cho rằng ECDHE tự ngăn replay | Bản tin hợp lệ vẫn có thể phát lại | Sequence numbers và cơ chế giao thức |
| Ghi secrets vào log để phân tích handshake | Có thể giải mã phiên cũ, mất forward secrecy | Log metadata an toàn, hạn chế key logging |
| Không kiểm tra chứng chỉ/hostname | Bị mạo danh dù DH toán học đúng | Kiểm tra PKI, danh tính, expiry và revocation |
| Chỉ thay static signing key rồi giữ verifier cache cũ | Kẻ có khóa cũ vẫn có thể mạo danh handshake mới | Thu hồi và đồng bộ trust store/certificate/JWKS |
| Coi key update là đã tạo entropy mới | Đánh giá sai khả năng phục hồi sau compromise | Hiểu key schedule, resumption và giới hạn PCS |
| KMS/HSM có Sign nhưng IAM cho phép quá rộng | Signing oracle tạo handshake giả mạo | Kiểm tra quyền ứng dụng và chính sách Sign |
| Hủy khóa khi dữ liệu lưu trữ còn phụ thuộc | Mất dữ liệu hợp lệ | Tách vòng đời session keys và DEK/KEK |

## 15. Tình huống thực hành: hai microservice thiết lập kênh an toàn

Giả sử **Order Service** và **Payment Service** trao đổi dữ liệu nhạy cảm. Nhóm phát triển đề xuất tự gửi X25519 public keys qua HTTP, tính shared secret rồi dùng AES-GCM.

**Thiết kế ban đầu có ba vấn đề:**

1. Không xác thực public key hay danh tính dịch vụ; kẻ đứng giữa có thể thay cả hai shares.
2. Cùng một raw shared secret được cắt 32 byte làm AES key mà không có transcript binding hoặc phân tách hướng truyền.
3. Nonce AES-GCM bắt đầu từ 0 sau mỗi lần restart, trong khi ứng dụng còn giữ khóa phiên cũ.

**Giải pháp ưu tiên:** Sử dụng **TLS 1.3** với xác thực máy chủ và **mTLS** nếu cần danh tính hai chiều, để thư viện TLS đã được đánh giá xử lý (EC)DHE, transcript, HKDF, AEAD, nonce, lỗi và cập nhật khóa.

Một thiết kế quản lý khóa kèm theo:

~~~mermaid
flowchart TD
    A["Order Service"] -->|"TLS/mTLS đã xác thực"| B["Payment Service"]
    C["PKI / trust store"] --> A
    C --> B
    D["KMS/HSM: static signing key, IAM"] --> B
    A --> E["Audit: identity, handshake failures, policy"]
    B --> E
    B --> F["KMS: KEK bảo vệ DEK lưu trữ"]
    F --> G["Encrypted DEK + AES-GCM ciphertext"]
~~~

Các lớp cần phân biệt:

- **TLS/mTLS:** bảo vệ dữ liệu **trên đường truyền**, xác thực peer và sử dụng traffic keys ngắn hạn.
- **KMS/HSM:** quản lý static signing keys và KEK/DEK theo quyền, vòng đời và kiểm toán.
- **Envelope encryption:** bảo vệ dữ liệu **khi lưu trữ**, không thay thế TLS.
- **IAM/service authorization:** quyết định Order Service có được gọi endpoint thanh toán hay không, ngay cả khi chứng chỉ TLS hợp lệ.
- **Audit:** ghi danh tính và sự kiện vận hành mà không ghi private ephemeral keys hay session secrets.

Nếu Payment Service bị lộ private signing key, phải thu hồi niềm tin và thay khóa để ngăn các phiên mới bị mạo danh. Các phiên ECDHE quá khứ có thể vẫn được bảo vệ theo điều kiện forward secrecy, nhưng phải kiểm tra **khả năng lộ traffic secrets, ứng dụng, log và cấu hình phiên**.

## 16. Kiểm thử key agreement trong môi trường thực tế

| Kiểm thử | Kỳ vọng |
|---|---|
| Hai bên dùng cặp X25519 hợp lệ và trao đổi shares đúng | Tính được cùng shared secret |
| Public key bị thay trên đường truyền | Handshake được xác thực **phải từ chối** |
| Public key không thuộc nhóm/không đúng encoding hoặc đầu ra all-zero | Bị từ chối theo thuật toán và giao thức |
| Một bên thay đổi transcript sau khi ký/MAC | Xác thực handshake thất bại |
| Hai phía dùng khác algorithm/cipher suite trái policy | Từ chối hoặc đàm phán lại an toàn theo chuẩn |
| Sai server identity/hostname hoặc chứng chỉ không tin cậy | Không thiết lập phiên được xác thực |
| Chữ ký chứng chỉ máy chủ hết hạn/đã thu hồi theo policy | Bị từ chối theo chính sách tin cậy |
| Dẫn xuất client→server và server→client | Keys/labels và nonce states được phân tách đúng |
| Thay AAD hoặc authentication tag của AEAD | Không chấp nhận dữ liệu |
| Phát lại record đã nhận | Cơ chế sequence/replay của giao thức xử lý đúng |
| Chấm dứt phiên | Không còn dùng session secret để gửi dữ liệu mới |
| Bật key logging ngoài môi trường được phép | Bị phát hiện/ngăn theo chính sách |
| Thu hồi static signing key | Verifier không tiếp tục tin khóa cũ ngoài phạm vi policy |
| KMS Sign bị principal không có quyền gọi | Bị từ chối và có sự kiện audit |
| VM snapshot/restore ảnh hưởng RNG hoặc state | Cơ chế phòng ngừa/kiểm thử phát hiện rủi ro lặp secret |
| Phiên cũ được ghi lại, static signing key bị lộ sau đó | Phân tích khả năng forward secrecy dựa trên giao thức và việc giữ secret, không kết luận chỉ từ tên ECDHE |

**Đừng chứng minh bảo mật chỉ bằng việc hai shared secrets bằng nhau.** Hai bên có thể tính cùng một giá trị trong một cuộc tấn công MITM tách phiên. Kiểm thử phải bao phủ xác thực, key schedule, nonce, replay, kiểm soát quyền và tình huống lỗi.

## 17. Câu hỏi tự kiểm tra

**Câu 1. Ephemeral key agreement có phải là quá trình gửi một AES key cho đối tác không?**

**Trả lời:** Không. Các bên trao đổi thông tin công khai và dùng private key riêng để tính shared secret; sau đó dùng KDF tạo traffic keys. Không truyền raw shared secret như plaintext.

**Câu 2. Sự khác nhau giữa static signing key và ephemeral DH key là gì?**

**Trả lời:** Static signing key thường xác thực danh tính qua nhiều phiên; ephemeral DH key dùng để thỏa thuận bí mật cho một phiên. Vai trò và vòng đời khác nhau.

**Câu 3. X25519 có phải Ed25519 không?**

**Trả lời:** Không. X25519 dùng cho key agreement; Ed25519 dùng cho chữ ký số. Không thay thế khóa/thuật toán bằng cách đổi tên.

**Câu 4. Vì sao cần xác thực ephemeral public keys?**

**Trả lời:** Để chống MITM và bảo đảm shared secret được thiết lập với đúng đối tác. DH toán học không tự xác minh danh tính.

**Câu 5. Forward secrecy bảo vệ những gì?**

**Trả lời:** Theo giả định giao thức, nó giúp ngăn đối thủ giải mã phiên cũ chỉ nhờ việc chiếm được khóa xác thực dài hạn ở thời điểm sau. Nó không bảo vệ khi traffic key hoặc ephemeral private secret của phiên cũ đã bị lộ.

**Câu 6. Có thể dùng raw ECDH secret trực tiếp làm AES key không?**

**Trả lời:** Không nên. Hãy dùng key schedule/KDF chuẩn để dẫn xuất khóa đúng thuật toán, vai trò và ngữ cảnh phiên.

**Câu 7. HKDF có thay thế bước kiểm tra chứng chỉ/chữ ký không?**

**Trả lời:** Không. HKDF dẫn xuất khóa và phân tách mục đích; nó không chứng minh ephemeral public key đến từ đúng chủ thể.

**Câu 8. Tại sao cần hai traffic keys cho hai hướng?**

**Trả lời:** Để tách mục đích, role và nonce state, hạn chế việc dùng lại cùng cặp key/nonce cho những bản tin khác nhau.

**Câu 9. Khi static signing key bị lộ, các phiên ECDHE cũ chắc chắn bị giải mã không?**

**Trả lời:** Không. Trong giao thức có forward secrecy và các điều kiện bảo vệ secret phù hợp, chỉ lộ khóa xác thực dài hạn sau này không tự giải lộ khóa phiên cũ.

**Câu 10. KMS/HSM có tự bảo đảm giao thức DH không bị MITM không?**

**Trả lời:** Không. KMS/HSM có thể bảo vệ khóa ký hoặc thực hiện phép toán; giao thức vẫn phải xác thực peer, transcript và nội dung được phép ký.

**Câu 11. Nếu dùng AES-GCM với key từ ECDHE, còn cần quản lý nonce không?**

**Trả lời:** Có. AEAD yêu cầu nonce duy nhất dưới cùng traffic key theo thiết kế; forward secrecy không khắc phục lỗi nonce reuse.

**Câu 12. Vì sao không nên lưu ephemeral private keys vào log?**

**Trả lời:** Chúng có thể giúp khôi phục shared secret/traffic keys và làm mất bảo vệ của forward secrecy đối với phiên đã ghi lại.

**Câu 13. Thay traffic key bằng KDF có đồng nghĩa thực hiện key agreement mới không?**

**Trả lời:** Không nhất thiết. Key update có thể dẫn xuất từ trạng thái hiện tại mà không cần một lần trao đổi DH mới; phải xem key schedule của giao thức.

**Câu 14. Ephemeral–ephemeral DH thiếu xác thực có đủ bảo mật khi có attacker chủ động không?**

**Trả lời:** Không. Có thể bị MITM dù mỗi phía dùng private key tạm thời mạnh.

**Câu 15. Thứ gì nên dùng cho kênh liên lạc giữa microservices thay vì tự thiết kế X25519 + AES-GCM?**

**Trả lời:** Ưu tiên TLS 1.3 với xác thực đúng, mTLS khi cần, thư viện TLS đã được kiểm chứng cùng chính sách IAM và quản lý chứng chỉ.

## 18. Checklist thiết kế và ghi nhớ

Khi lựa chọn cơ chế thiết lập khóa tạm thời, hãy kiểm tra:

- **Protocol:** Có thể dùng TLS 1.3 hoặc một giao thức chuẩn sẵn có thay vì tự thiết kế không?
- **Algorithm:** DHE/ECDHE/X25519, nhóm và tham số được cho phép và được provider hỗ trợ đúng?
- **Generation:** Ephemeral private keys sinh bằng CSPRNG/DRBG phù hợp, mỗi phiên/phạm vi đúng như giao thức yêu cầu?
- **Peer authentication:** Danh tính/chứng chỉ/signing key của đối tác có được xác thực và kiểm tra thu hồi không?
- **Transcript:** Thuật toán đàm phán, vai trò, danh tính và public shares có được ràng buộc an toàn với key schedule và authentication không?
- **Public key validation:** Có kiểm tra input/encoding/group và điều kiện all-zero khi dùng X25519 không?
- **KDF:** Có HKDF/key schedule chuẩn, tách hướng, mục đích và context không? Có tránh dùng raw Z làm traffic key không?
- **Data protection:** AEAD có quản lý nonce, tag, sequence và giới hạn record đúng không?
- **Forward secrecy:** Những giả định về xóa ephemeral secrets, key logging và compromise được kiểm chứng chưa?
- **KMS/HSM:** Static signing keys, KEK/DEK, IAM và sự kiện audit có được tách đúng vai trò?
- **Lifecycle:** Khi rotate/revoke danh tính, liệu verifier, trust store, session tickets và client cache có được cập nhật không?
- **Operations:** Có kiểm thử MITM, replay, downgrade, VM restore, thất bại provider và lỗi KMS không?
- **Incident response:** Nếu private signing key hoặc traffic secrets bị lộ, có thể xác định phiên/hiện vật bị ảnh hưởng và chuyển khóa an toàn không?

**Ghi nhớ:** **Ephemeral key agreement** giúp các bên thiết lập shared secret cho một phạm vi ngắn hạn thông qua **(EC)DHE hoặc X25519**, tạo nền tảng cho **forward secrecy** khi được tích hợp đúng. Nhưng **key agreement không tự xác thực đối tác, không tự dẫn xuất traffic keys, không tự quản lý nonce và không thay thế quản lý khóa lâu dài**. Một kênh an toàn cần kết hợp **xác thực transcript và danh tính, KDF, AEAD, nguồn ngẫu nhiên đáng tin, KMS/HSM, IAM, kiểm toán, rotation/revocation và vòng đời khóa phù hợp**.
