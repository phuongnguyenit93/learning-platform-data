# 10.5. Xác thực đối tác để tránh đánh tráo khóa trong quá trình thỏa thuận

**Thỏa thuận khóa (key agreement)** cho phép hai phía tạo ra bí mật chung qua một kênh truyền có thể bị quan sát. Nhưng có một điều kiện rất dễ quên: **hai phía cần biết mình thực sự đang thỏa thuận với ai**. Nếu kẻ tấn công có thể thay khóa công khai được trao đổi trong quá trình bắt tay, Diffie–Hellman/ECDH/X25519 đơn thuần **không ngăn được tấn công người đứng giữa (Man-in-the-Middle, MITM)**.

Một kẻ đứng giữa có thể tự tạo hai phiên thỏa thuận khóa: một phiên với Alice và một phiên với Bob. Alice tưởng đã tạo khóa với Bob; Bob tưởng đã tạo khóa với Alice; thực tế cả hai đang chia sẻ hai khóa riêng biệt với kẻ tấn công. Ngay cả khi mỗi phía dùng AES-GCM đúng chuẩn để bảo vệ dữ liệu, kẻ đứng giữa vẫn có thể giải mã rồi mã hóa lại, bởi hắn có khóa hợp lệ cho **hai phiên giả** đó.

**Giải pháp không phải là làm khóa DH dài hơn hoặc thêm hash cho khóa trao đổi.** Cần **xác thực khóa công khai và danh tính đối tác**, ràng buộc bằng chứng xác thực vào **đúng phiên bắt tay, đúng vai trò, đúng thuật toán và đúng các public key tạm thời**, rồi chỉ cho phép dùng khóa phiên sau khi việc xác minh đạt yêu cầu.

## 1. Mục tiêu bài học

Sau khi học xong, bạn có thể:

- Mô tả vì sao DH/ECDH/X25519 không xác thực danh tính chỉ nhờ phép tính bí mật chung.
- Phân biệt **agreement**, **authentication**, **authorization**, **key confirmation** và **key wrapping**.
- Vẽ lại tấn công MITM thay thế public key, biết chính xác vì sao mỗi bên vẫn tính được một shared secret nhưng không có kênh an toàn Alice–Bob.
- Xây dựng các bước xác thực đối tác bằng chữ ký số gắn với identity, certificate/PKI, public-key pinning hoặc khóa PSK đã phân phối an toàn.
- Xác định những byte cần gắn vào **handshake transcript**: protocol version, cipher suite/KDF, role, identity, ephemeral public keys, nonce và context.
- Viết và chạy một minh họa Java 17+ kết hợp **X25519 + Ed25519 + HKDF-SHA256** với khóa công khai danh tính được tin cậy từ trước.
- Kiểm thử thay public key, giả mạo người ký, đổi tên đối tác và tái sử dụng chữ ký từ phiên cũ; hiểu giới hạn của demo so với TLS 1.3.
- Nhận diện các sai sót liên quan đến certificate validation, TOFU, key substitution, replay, downgrade, UKS và xác minh quyền truy cập.

## 2. Ba câu hỏi riêng biệt về khóa

Trong thực tế, từ “xác thực khóa” đôi khi gom nhiều việc khác nhau. Nên tách thành ba câu:

**Câu hỏi A — có tạo được cùng bí mật không?**  
Nếu Alice giữ private key tạm thời `a` và Bob giữ private key tạm thời `b`, phép X25519 cho phép:

\[
Z_A = X25519(a, B_{\text{ephemeral}})
\]

\[
Z_B = X25519(b, A_{\text{ephemeral}})
\]

Với hai cặp khóa hợp lệ và các giá trị public key tương ứng được trao đổi nguyên vẹn, hai bí mật `Z_A` và `Z_B` bằng nhau. Đây là **khả năng thỏa thuận khóa**, chưa cho biết public key thật sự đến từ ai.

**Câu hỏi B — người đứng sau khóa công khai là ai?**  
Alice cần biết `B_ephemeral` có thuộc **đúng phiên thỏa thuận với Bob** không. Để biết điều đó, Alice phải có một bằng chứng gắn `B_ephemeral` với **định danh Bob mà Alice đang kỳ vọng**, dựa trên một nền tảng tin cậy như khóa ký đã pin, certificate đã kiểm tra, PSK được cấp phát đúng chủ thể hoặc một quy trình xác thực out-of-band.

**Câu hỏi C — khóa được dùng cho mục đích nào?**  
Sau khi hai phía tạo shared secret và xác thực transcript, thường cần KDF (ví dụ HKDF) để lấy key dùng cho ứng dụng và, khi cần, các key/nonce riêng theo hướng. Sau đó server vẫn phải kiểm tra **quyền truy cập** của principal, không chỉ kiểm tra rằng client biết một khóa.

Một phiên có thể qua A nhưng thất bại B (MITM), hoặc qua A và B nhưng thất bại C (khách hàng đã xác thực nhưng không được phép thao tác tài khoản khác).

## 3. Diffie–Hellman không xác thực: tấn công đánh tráo khóa

Giả sử Alice và Bob muốn thiết lập kênh bảo mật qua mạng mà Mallory có thể đọc, chặn và sửa gói tin.

### 3.1. Trường hợp chỉ nghe lén, không sửa dữ liệu

```text
Alice                                             Bob
------                                            ------
Sinh (aPriv, aPub)                               Sinh (bPriv, bPub)
        |                                             |
        +------------- aPub ------------------------->|
        |<------------ bPub --------------------------+
        |                                             |
Z_A = X25519(aPriv, bPub)             Z_B = X25519(bPriv, aPub)
        |                                             |
        +-------- HKDF -> session key -----------------+
```

Nếu attacker chỉ **quan sát** hai public key mà không biết private key, X25519 được thiết kế để khiến việc tính shared secret trở nên khó. Đây là tính chất nền tảng của Diffie–Hellman.

**Nhưng Mallory không nhất thiết chỉ nghe lén.** Nếu đường truyền không xác thực, Mallory có thể thay cả hai public key.

### 3.2. Tấn công MITM bằng hai phiên DH

```text
  Alice                         Mallory                         Bob
  -----                         -------                         ---
  aPub -----------> [chặn]       mPub1 ------------->         Bob
  Alice <----------- mPub2       [chặn] <------------- bPub

 Alice tính:                        Mallory tính:
 X25519(aPriv, mPub2)               X25519(mPriv2, aPub)
                   -> Z_AM = Z_MA

                                  Mallory tính:                 Bob tính:
                                  X25519(mPriv1, bPub)          X25519(bPriv, mPub1)
                                         Z_MB = Z_BM <-
```

Kết quả:
- Alice có **một shared secret với Mallory**, không phải Bob.
- Bob có **một shared secret khác với Mallory**, không phải Alice.
- Mallory biết cả hai secrets, có thể tạo traffic keys cho cả hai chiều và làm trung gian decrypt/modify/reencrypt.
- Không có phép toán X25519 nào tự cảnh báo rằng tên đối tác mà giao diện hiển thị không trùng với chủ thể tạo ra public key.

Đây là lý do phát biểu “dùng ECDH nên dữ liệu đã an toàn trước MITM” **không đúng nếu thiếu peer authentication**.

### 3.3. Vì sao hash public key cũng chưa đủ?

Ví dụ Alice nhận `bPub` rồi tính `SHA-256(bPub)` và thấy một fingerprint. Fingerprint chỉ tóm tắt các byte của key Alice **đã nhận**. Nếu attacker thay `bPub` bằng `mPub`, Alice cũng có thể tính một fingerprint hoàn toàn hợp lệ của `mPub`.

Fingerprint chỉ giúp khi Alice **so sánh với một fingerprint đáng tin đã có từ trước**, nhận bằng kênh xác thực độc lập. Gửi public key và fingerprint của chính nó trong **cùng một gói không xác thực** không giải quyết việc đánh tráo.

Đổi X25519 sang curve khác, dùng RSA nhiều bit hơn hay chuyển SHA-256 sang SHA-512 cũng không sửa được gốc lỗi: **không có chứng cứ ràng buộc khóa vào đúng đối tác**.

## 4. Xác thực đối tác thực sự nghĩa là gì?

Đối với Alice muốn giao tiếp với Bob, có ít nhất bốn thành phần:

1. **Expected identity:** Alice biết trước mình muốn gặp ai, ví dụ `bob@example.internal`, một tên dịch vụ, tenant + service ID hoặc hostname `api.example.com`.
2. **Trusted authentication key:** Alice có cách lấy **khóa xác minh danh tính Bob từ nguồn đáng tin**, không chỉ từ gói tin Mallory kiểm soát.
3. **Proof of possession:** Bob tạo một bằng chứng mà chỉ chủ thể giữ private key/PSK được cấp phép mới tạo hợp lệ, như chữ ký số trên transcript bắt tay.
4. **Session binding:** bằng chứng này gắn **đúng phiên** và các tham số liên quan, đặc biệt các ephemeral public keys, roles, nonce, protocol version và thuật toán đã chọn.

Nếu chứng cứ chỉ là “Bob biết một private key nào đó”, vẫn thiếu việc chứng minh đó là **private key thuộc đúng Bob**. Nếu certificate hợp lệ cho một domain khác nhưng Alice không kiểm tra hostname, đối thủ có thể trình ra certificate của domain họ sở hữu và vẫn vượt qua kiểm tra chain. Nếu chữ ký chỉ ký một chuỗi tĩnh như `"I am Bob"`, attacker có thể phát lại chữ ký ở phiên khác.

**Định danh phải đến từ ý định của bên kiểm tra**, không được chấp nhận chỉ vì phía bên kia tự khai trong payload.

### 4.1. Xác thực server và xác thực hai chiều

- **Server authentication:** client xác minh server; server có thể chưa xác minh danh tính client ở handshake và sẽ dùng một bước khác (token, tài khoản, OAuth, client certificate...) sau đó.
- **Mutual authentication:** cả hai phía đều chứng minh danh tính bằng cơ chế thích hợp, ví dụ mTLS hoặc hai chữ ký trên một authenticated handshake.
- **Authorization:** sau khi danh tính đã được chứng minh, hệ thống xét chủ thể đó có được gọi API, xem resource, dùng tenant hoặc thực hiện operation cụ thể không.

Vì vậy, **authenticated key agreement không đồng nghĩa với cho phép truy cập mọi dữ liệu**.

## 5. Một handshake cần ký hoặc MAC những byte nào?

Các protocol hoàn chỉnh thường xây dựng một **handshake transcript**: chuỗi byte biểu diễn có thứ tự các thông điệp và tham số đã trao đổi. Chữ ký/MAC/Finished được tính trên một digest hoặc cấu trúc rõ ràng liên quan đến transcript này.

Một mô hình cho bài học:

```text
transcript_v1 =
    protocolId
    || suiteId
    || "initiator" || aliceExpectedIdentity
    || "responder" || bobExpectedIdentity
    || aliceNonce
    || bobNonce
    || aliceX25519EphemeralPublic
    || bobX25519EphemeralPublic
```

Các ký hiệu `||` chỉ **ghép theo định dạng đã quy định**. Phải có encoding không nhập nhằng, như length-prefix hoặc một chuẩn serialization xác định. Không đơn giản nối string tự do.

Bên Alice xác minh rằng Bob đã ký **chính xác transcript của phiên Alice đang tham gia** bằng khóa xác thực tin cậy của Bob. Tương tự, Bob xác minh bằng chứng Alice nếu cần mutual authentication.

### 5.1. Ý nghĩa của từng thành phần

| Thành phần | Nếu không ràng buộc thì sao? |
| --- | --- |
| Protocol name/version | Chữ ký/khóa có thể bị đưa sang ngữ cảnh khác hoặc hiểu bằng parser khác |
| Cipher suite và KDF | Có nguy cơ negotiation confusion hoặc downgrade xuống thuật toán yếu |
| Initiator/responder roles | Có thể gây lỗi reflection/role confusion khi dùng cùng dữ liệu ở hai chiều |
| Expected peer identity | Có thể gán cùng khóa phiên cho hai danh tính khác nhau (unknown key-share) |
| Cả hai ephemeral public keys | Attacker thay một key mà chữ ký không phát hiện |
| Nonce/challenge mới của phiên | Chữ ký/bản tin phiên trước có thể bị phát lại |
| Cấu trúc thông điệp có độ dài rõ ràng | Cặp trường khác nhau có thể tạo cùng byte input |
| Application context/tenant | Khóa phiên có thể bị dùng nhầm sang dịch vụ, tenant hoặc operation khác |

Cần phân biệt **điều hai bên ký/verify** với **điều hai bên hiển thị trên màn hình**. Nếu UI ghi `Bob` nhưng transcript và verifier đang dùng khóa của `Mallory`, việc ký đúng một transcript không đúng identity vẫn không đem lại peer authentication mong muốn.

### 5.2. Ký public key thôi có đủ không?

Ký mỗi `bEphemeralPublic` có thể chứng minh bên giữ private signing key nào đó đã từng ký public key ấy, **nhưng chưa đủ ràng buộc**:
- Alice và nonce của Alice có thuộc phiên cụ thể không?
- Chữ ký dành cho client/server role nào?
- Bob có biết đang kết nối với Alice chứ không phải Mallory không?
- Hai bên có cùng protocol version và thuật toán không?

Thiết kế vững hơn là **ký transcript đã được xác định rõ**, hoặc dùng một protocol chuẩn có cách tạo và xác minh handshake authentication riêng. Không tự phát minh “ký một vài field là đủ” mà thiếu mô hình an ninh.

### 5.3. Freshness và replay

Một challenge/nonce mới được đưa vào transcript giúp chữ ký phiên cũ **không còn khớp transcript của phiên mới**, miễn cả hai bên thực sự kiểm tra đúng challenge vừa sinh. Nhưng việc có nonce trong bản tin không tự động cấm replay toàn bộ một request ở tầng ứng dụng.

Ứng dụng thực tế còn có thể cần:
- Sequence numbers hoặc unique record nonces cho AEAD;
- Replay cache, expiry và idempotency cho lệnh nhạy cảm;
- Session identifiers gắn với principal, scope, deadline và resource;
- Quy tắc chấp nhận lại handshake/resumption theo protocol cụ thể.

Không suy ra “có signature hợp lệ” nghĩa là “giao dịch chắc chắn mới và chưa từng thực thi”.

## 6. Những cơ chế xác thực khóa công khai phổ biến

### 6.1. Certificate và PKI

Bên gửi có thể trình một certificate chứa public key và subject/SAN; certificate này được một CA hoặc chuỗi trung gian ký. Bên nhận dùng trust anchors đã cấu hình để kiểm tra đường tin cậy.

Với một kết nối HTTPS/TLS, phía client cần kiểm tra **ít nhất theo chính sách triển khai**:
1. Certificate path có thể xây dựng tới trust anchor được phép.
2. Các chữ ký, hiệu lực thời gian, algorithm/key strength và constraints phù hợp.
3. **Danh tính server kỳ vọng khớp SAN/hostname** theo chuẩn ứng dụng; không lấy `CN` hay string từ server làm chứng cứ thay thế hostname validation.
4. Key usage và extended key usage phù hợp với mục đích server authentication nếu được áp dụng.
5. Chính sách revocation/CT/enterprise trust và các ràng buộc khác khi hệ thống yêu cầu.
6. Bắt tay chứng minh server đang giữ khóa bí mật tương ứng và transcript không bị sửa, theo chính protocol.

**Chain valid ≠ correct peer identity.** Một certificate hợp lệ của `attacker.example` không được chấp nhận khi client định kết nối `api.company.example`.

Đừng bật chế độ **trust-all certificates**, “insecure hostname verifier”, hoặc chấp nhận mọi self-signed certificate trong production để xử lý lỗi chứng thư.

### 6.2. Public-key pinning và khóa ký cấu hình trước

Nếu hai dịch vụ nội bộ đã phân phối khóa công khai xác thực qua kênh tin cậy, bên nhận có thể **pin** key hoặc fingerprint/SPKI hash theo chính sách.

Quy tắc:
- Khóa tin cậy được lấy từ một cấu hình/chính sách đã xác thực, **không** từ chính bản tin bên kia đang muốn được xác minh.
- Pin được so sánh trước khi chấp nhận chữ ký, theo identity và key usage đúng.
- Cần chiến lược dự phòng/rotation và xử lý compromise; pin sai hoặc hết hạn có thể gây outage.
- Với SPKI pin, phải thống nhất encoding/fingerprint format và chống nhầm lẫn với fingerprint của raw key encoding khác.

Pinning là lựa chọn phụ thuộc deployment, không mặc định tốt hơn PKI cho mọi hệ thống. Trên ứng dụng quy mô lớn, quản lý vòng đời pin sai có thể gây mất kết nối hàng loạt.

### 6.3. Trust on First Use (TOFU)

Mô hình TOFU ghi nhớ public key nhìn thấy ở **lần kết nối đầu tiên**, rồi cảnh báo nếu nó thay đổi. Nó có ích trong một số workflow như SSH khi người dùng/nhân viên xác minh fingerprint qua kênh phụ.

Giới hạn rất quan trọng: nếu attacker đang MITM **ngay lần đầu**, ứng dụng có thể pin nhầm khóa attacker. TOFU **không tương đương** với việc đã kiểm tra certificate/identity từ một nguồn tin cậy. Nếu public key thay đổi sau này, không tự chấp nhận key mới mà không có quy trình rotation/xác thực.

### 6.4. PSK, password-authenticated key exchange và kênh độc lập

Khi hai phía đã có **pre-shared key (PSK) đủ mạnh và được phân phối bí mật, đúng danh tính**, một protocol có thể dùng MAC/handshake binder để xác thực phiên. Phải ràng buộc PSK identity, transcript, cipher suite và quyền vào context; không lấy PSK từ dữ liệu do đối thủ tự khai.

Với password do con người nhớ, **không tự biến nó thành PSK** bằng `SHA-256(password)` rồi dùng như MAC key trong một handshake tự chế: có thể mở cửa tấn công từ điển/offline. Khi cần xác thực dựa trên password trong trao đổi khóa, nên dùng một **PAKE** (ví dụ một giao thức đã chuẩn hóa và triển khai được thẩm định) thay vì DH + password hash tự ghép.

Với thiết bị hai bên có thể so sánh một số xác minh ngắn hoặc quét QR trực tiếp, cơ chế **out-of-band authenticated comparison** cũng có thể ràng buộc public keys, nếu giao thức thiết kế đúng và kênh so sánh thực sự đáng tin.

## 7. Khóa phiên phải được dẫn xuất từ shared secret và transcript

Sau khi xác thực đối tác và thống nhất ephemeral public keys, X25519 tạo một shared secret. Không dùng trực tiếp raw X25519 bytes làm **key AES-GCM và nonce** theo quy tắc tự nghĩ.

Thường dùng KDF có context:

\[
Z = X25519(\text{own ephemeral private},\ \text{peer ephemeral public})
\]

\[
PRK = HKDF\text{-}Extract(\text{salt}, Z)
\]

\[
K_{app} = HKDF\text{-}Expand(PRK,\ \text{info},\ L)
\]

- `salt` của HKDF là input **không bắt buộc bí mật**, có thể liên quan tới transcript hash theo thiết kế protocol.
- `info` nên tách protocol/version, mục đích khóa và hướng dùng: ví dụ `client-to-server key` và `server-to-client key` là hai mục đích khác nhau.
- `L` là số byte output cần lấy, ví dụ **32** cho AES-256 key.
- Transcript hash giúp hai phía ràng buộc key derivation vào cùng handshake, nhưng **bản thân HKDF không chứng minh peer identity**: phải verify chữ ký/MAC và nguồn khóa xác thực trước khi sử dụng key.

Trong bài minh họa Java ở dưới, ta dùng `salt = SHA-256(transcript)` và một chuỗi `info` cố định cho **một key demo**, nhằm dễ kiểm tra hai phía tính giống nhau. **Ứng dụng hai chiều thực tế** cần tách key/nonce/traffic secret cho từng hướng và quản lý sequence numbers chống nonce reuse.

### 7.1. Key confirmation không đồng nghĩa identity proof

Sau khi derive key, hai phía có thể trao đổi một **confirmation MAC/Finished** chứng minh đối tác giữ secret phù hợp với transcript và lịch trình key.

Ví dụ khái niệm:

```text
confirmAlice = HMAC(K_confirm_A, "alice-finished" || transcriptHash)
confirmBob   = HMAC(K_confirm_B, "bob-finished"   || transcriptHash)
```

Bên nhận kiểm tra tag tương ứng trước khi cho ứng dụng gửi dữ liệu. Với protocol có xác thực tích hợp, một phần chứng cứ Finished/record integrity giúp phát hiện bất đồng secret hoặc transcript.

Nhưng nếu Mallory đã tạo **hai phiên DH giả** mà không xác thực identity, hắn cũng biết khóa confirmation cho hai phiên và có thể tạo hai MAC hợp lệ. **Key confirmation chỉ có giá trị đúng khi được kết hợp với việc xác thực đối tác và context của phiên.**

Trong ví dụ Java, ta so sánh HMAC tính ở hai phía **trong cùng một process** để minh họa khả năng đồng nhất key. Đó chưa phải một **wire-level key confirmation exchange** đầy đủ.

## 8. Java 17+: X25519 + Ed25519 + transcript binding

Dưới đây là một ví dụ **tự chạy được** bằng JDK 17+, có chủ đích phân biệt hai loại khóa:

- **X25519 ephemeral key pairs:** dùng riêng cho key agreement từng phiên.
- **Ed25519 identity key pairs:** dùng riêng để ký và xác minh transcript. Public keys dùng kiểm tra được giả lập **đã phân phối qua kênh xác thực/pin từ trước**.
- **Transcript encoding:** ghi từng trường bằng 4-byte length prefix (big-endian), giữ thứ tự cố định, tránh nhập nhằng chuỗi.
- **HKDF-SHA256:** minh họa bước Extract/Expand của RFC 5869 cho output 32 byte.
- **Kiểm thử tấn công:** thay ephemeral public key, đổi expected identity, ký bằng khóa impostor, dùng lại chữ ký trên challenge mới.

Tệp đầy đủ: `AuthenticatedKexDemo.java`.

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
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

public class AuthenticatedKexDemo {
    static final SecureRandom RNG = new SecureRandom();

    static byte[] random(int n) {
        byte[] data = new byte[n];
        RNG.nextBytes(data);
        return data;
    }

    // Framing: 4-byte length prefix followed by exactly that many bytes.
    static void field(DataOutputStream out, String value) throws IOException {
        field(out, value.getBytes(StandardCharsets.UTF_8));
    }

    static void field(DataOutputStream out, byte[] value) throws IOException {
        out.writeInt(value.length);
        out.write(value);
    }

    static byte[] transcript(
            String initiator, String responder,
            byte[] aliceNonce, byte[] bobNonce,
            PublicKey aliceEphemeral, PublicKey bobEphemeral
    ) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            field(out, "auth-kex-demo:v1");
            field(out, "X25519+Ed25519+HKDF-SHA256");
            field(out, "initiator");
            field(out, initiator);
            field(out, "responder");
            field(out, responder);
            field(out, aliceNonce);
            field(out, bobNonce);
            // Java public key encoding: X.509 SubjectPublicKeyInfo format.
            field(out, aliceEphemeral.getEncoded());
            field(out, bobEphemeral.getEncoded());
        }
        return buffer.toByteArray();
    }

    static byte[] sign(PrivateKey key, byte[] message)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initSign(key, RNG);
        s.update(message);
        return s.sign();
    }

    static boolean verify(PublicKey trustedKey, byte[] message, byte[] signature)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initVerify(trustedKey);
        s.update(message);
        return s.verify(signature);
    }

    static byte[] agree(PrivateKey own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(own);
        ka.doPhase(peer, true);
        return ka.generateSecret();
    }

    static byte[] hmac(byte[] key, byte[] message)
            throws GeneralSecurityException {
        Mac h = Mac.getInstance("HmacSHA256");
        h.init(new SecretKeySpec(key, "HmacSHA256"));
        return h.doFinal(message);
    }

    static byte[] applicationKey(byte[] sharedSecret, byte[] transcript)
            throws GeneralSecurityException {
        // RFC 5869 HKDF-Extract(salt, IKM) and first Expand block.
        byte[] salt = MessageDigest.getInstance("SHA-256").digest(transcript);
        byte[] prk = hmac(salt, sharedSecret);

        byte[] info = "auth-kex-demo:v1|app-key"
                .getBytes(StandardCharsets.UTF_8);
        byte[] input = Arrays.copyOf(info, info.length + 1);
        input[input.length - 1] = 1; // HKDF block counter 0x01

        try {
            return hmac(prk, input); // First full 32-byte HKDF-Expand block.
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        // DEMO ONLY: Identity public keys are treated as pre-authenticated.
        // Real applications get them from validated certificates or trusted pins.
        KeyPairGenerator identity = KeyPairGenerator.getInstance("Ed25519");
        KeyPair aliceIdentity = identity.generateKeyPair();
        KeyPair bobIdentity = identity.generateKeyPair();
        PublicKey pinnedAliceKey = aliceIdentity.getPublic();
        PublicKey pinnedBobKey = bobIdentity.getPublic();

        KeyPairGenerator ephemeral = KeyPairGenerator.getInstance("X25519");
        KeyPair a = ephemeral.generateKeyPair();
        KeyPair b = ephemeral.generateKeyPair();
        byte[] aNonce = random(16);
        byte[] bNonce = random(16);

        byte[] t = transcript(
                "alice", "bob",
                aNonce, bNonce,
                a.getPublic(), b.getPublic()
        );

        byte[] aliceSignature = sign(aliceIdentity.getPrivate(), t);
        byte[] bobSignature = sign(bobIdentity.getPrivate(), t);

        boolean aliceTrustedBob = verify(pinnedBobKey, t, bobSignature);
        boolean bobTrustedAlice = verify(pinnedAliceKey, t, aliceSignature);

        System.out.println("Alice verifies Bob: " + aliceTrustedBob);
        System.out.println("Bob verifies Alice: " + bobTrustedAlice);
        if (!aliceTrustedBob || !bobTrustedAlice) {
            throw new GeneralSecurityException("Unauthenticated peer");
        }

        byte[] aliceShared = agree(a.getPrivate(), b.getPublic());
        byte[] bobShared = agree(b.getPrivate(), a.getPublic());
        byte[] aliceKey = applicationKey(aliceShared, t);
        byte[] bobKey = applicationKey(bobShared, t);

        System.out.println("Derived keys equal: "
                + MessageDigest.isEqual(aliceKey, bobKey));

        // Mallory changes Bob's ephemeral X25519 public key in transit.
        KeyPair maliciousEphemeral = ephemeral.generateKeyPair();
        byte[] substituted = transcript(
                "alice", "bob", aNonce, bNonce,
                a.getPublic(), maliciousEphemeral.getPublic()
        );
        System.out.println("Substituted X25519 key accepted: "
                + verify(pinnedBobKey, substituted, bobSignature));

        // Even with the original signature, changing the expected peer ID fails.
        byte[] wrongIdentity = transcript(
                "alice", "mallory", aNonce, bNonce,
                a.getPublic(), b.getPublic()
        );
        System.out.println("Changed peer identity accepted: "
                + verify(pinnedBobKey, wrongIdentity, bobSignature));

        // Impostor may sign the correct bytes, but does not hold Bob's key.
        KeyPair imposter = identity.generateKeyPair();
        System.out.println("Impostor signature accepted: "
                + verify(
                    pinnedBobKey, t,
                    sign(imposter.getPrivate(), t)
                ));

        // Bob's old signature is invalid over a new session challenge.
        byte[] fresh = transcript(
                "alice", "bob", random(16), bNonce,
                a.getPublic(), b.getPublic()
        );
        System.out.println("Replayed old response accepted: "
                + verify(pinnedBobKey, fresh, bobSignature));

        // Local demonstration only, not a real network Finished exchange.
        byte[] confirmA = hmac(
                aliceKey,
                "auth-kex-demo:v1|confirm:alice".getBytes(StandardCharsets.UTF_8)
        );
        byte[] confirmB = hmac(
                bobKey,
                "auth-kex-demo:v1|confirm:alice".getBytes(StandardCharsets.UTF_8)
        );
        System.out.println("Key confirmation valid: "
                + MessageDigest.isEqual(confirmA, confirmB));

        Arrays.fill(aliceShared, (byte) 0);
        Arrays.fill(bobShared, (byte) 0);
        Arrays.fill(aliceKey, (byte) 0);
        Arrays.fill(bobKey, (byte) 0);
    }
}
```

Biên dịch và chạy:

```bash
javac AuthenticatedKexDemo.java
java AuthenticatedKexDemo
```

Kết quả stdout đã được kiểm tra với các API Java 17 tương thích:

```text
Alice verifies Bob: true
Bob verifies Alice: true
Derived keys equal: true
Substituted X25519 key accepted: false
Changed peer identity accepted: false
Impostor signature accepted: false
Replayed old response accepted: false
Key confirmation valid: true
```

### 8.1. Vì sao thay X25519 public key bị phát hiện?

Bob ký transcript `t` chứa **cả** `aPub` và `bPub`. Khi Mallory thay `bPub` bằng `mPub` trên đường gửi cho Alice, Alice tái tạo `substituted` từ key mình thấy và thử xác minh chữ ký cũ của Bob:

```java
verify(pinnedBobKey, substituted, bobSignature)
```

Kết quả là `false` vì bytes đã ký không còn giống transcript Alice đang xác minh. Mallory không có Ed25519 private signing key đã được gắn tin cậy với định danh Bob để tạo lại chữ ký hợp lệ cho transcript mới.

Nếu Mallory thay **aPub** ở chiều Alice → Bob, Bob cũng cần tạo/kiểm tra transcript từ đúng giá trị nhận được và Alice phải xác minh transcript của phiên mình đang tham gia. Khi transcript hai phía khác nhau, cơ chế ký/chứng thực và confirmation đúng thiết kế sẽ làm handshake thất bại.

**Chú ý:** chữ ký hợp lệ có ý nghĩa chỉ vì `pinnedBobKey` đã được giả định tin cậy và ràng buộc vào identity Bob. Nếu chương trình nhận `pinnedBobKey` từ chính gói tin do Mallory gửi rồi không kiểm tra, Mallory chỉ việc thay luôn key và tự ký: vẫn MITM.

### 8.2. Vì sao đổi peer identity bị phát hiện?

Transcript không chỉ chứa key, mà còn chứa chuỗi identity **theo đúng role**. Trong demo, Alice có ý định giao tiếp với `bob`, nên thử xác minh chữ ký Bob trên transcript ghi `mallory` ở vị trí responder phải bị từ chối.

Trong production, identity phải được lấy từ **cấu hình hoặc kết quả resolve tin cậy của ứng dụng**, không được dùng trường `responder` do bên kia tự khai làm “expected identity”. Bảo đảm này quan trọng để tránh **unknown key-share (UKS)**: một phía tin rằng mình chia sẻ key với danh tính khác mặc dù các bí mật mật mã có thể khớp.

### 8.3. Vì sao chữ ký impostor bị từ chối?

Mallory có thể tạo Ed25519 key pair hợp lệ và ký transcript hợp lệ. Nhưng **bất kỳ key pair đúng thuật toán nào** không đồng nghĩa với key của Bob. Alice phải verify bằng `pinnedBobKey`, không verify bằng public key Mallory đính kèm trong cùng thông điệp.

Đây là chỗ PKI hoặc pinning giải quyết vấn đề **thuộc tính khóa gắn với danh tính**, còn Ed25519 Signature giải quyết việc **người ký có giữ private key hay không**.

### 8.4. Giới hạn của demo — không dùng như production handshake

Ví dụ minh họa một số nguyên tắc cốt lõi, **không phải một wire protocol hoàn chỉnh đã được chứng minh an toàn**:

- Tất cả key pairs được sinh và trao trong **một process**, nên không mô tả network framing, key distribution thực tế, trust anchor hay quá trình certificate validation.
- `pinnedAliceKey` và `pinnedBobKey` chỉ được gán từ các key vừa tạo; demo **giả định** bước tin cậy đã xảy ra. Không dùng pattern này để “học khóa” từ network rồi xem là đã authenticated.
- Không mô tả trạng thái handshake, retransmission, timeout, key update, retranscript negotiation hoặc xử lý cùng lúc nhiều phiên.
- Chưa verify untrusted X25519 public key bytes sau parse từ network; cần cơ chế decode/validate theo provider và chuẩn curve, từ chối malformed/low-order/all-zero secret nếu ứng dụng/provider chưa xử lý đầy đủ.
- Transcript demo dùng `getEncoded()` của Java public key; một implementation khác có thể dùng raw 32-byte X25519 keys. **Phải chỉ định một wire encoding duy nhất** và kiểm thử chéo, không ghép các encoding khác nhau.
- Code không triển khai đầy đủ bảo vệ replay, bảo vệ identity trong hệ thống nhiều tenant, authorization hoặc certificate revocation.
- Hai chiều traffic hiện dùng một output `app-key` demo. Protocol sản xuất phải dẫn xuất **khóa gửi/nhận tách biệt**, nonce/sequence numbers riêng, record framing, AEAD authentication và limits.
- Local `confirmA`/`confirmB` chỉ so sánh hai kết quả trong cùng chương trình; muốn key confirmation qua mạng phải thực sự **gửi, xác minh MAC/Finished có role/ transcript đúng**, không chỉ in `true`.
- Việc gọi `Arrays.fill(...)` làm giảm thời gian giữ các mảng tự sở hữu, nhưng không bảo đảm private key và mọi bản sao trung gian trong JVM/provider bị xóa ngay.
- Không tự thiết kế protocol mã hóa lai/mTLS thay cho TLS 1.3 hoặc một protocol được kiểm toán khi chỉ cần một kênh giao tiếp thông thường.

## 9. TLS 1.3 là ví dụ thực tế của authenticated key agreement

Đối với giao tiếp HTTPS hoặc dịch vụ nội bộ, **TLS 1.3** là lựa chọn chuẩn thay vì tự lắp X25519 + Ed25519 + HKDF rồi gửi dữ liệu. Một handshake TLS 1.3 ở chế độ xác thực server bằng certificate (mô tả khái niệm) gồm:

```text
Client                                              Server
------                                              ------
ClientHello
  supported versions, cipher suites,
  key_share (ECDHE), random    --------------------->
                                 <------------------ ServerHello
                                                      selected suite, key_share
                      [Hai bên dẫn xuất handshake traffic secrets]
                                 <------------------ EncryptedExtensions
                                 <------------------ Certificate
                                 <------------------ CertificateVerify
                                 <------------------ Finished
Client:
  validate certificate chain + expected DNS name
  verify CertificateVerify over TLS handshake transcript
  verify Finished + transcript integrity
  if all pass -> send Finished  -------------------->
                     [Application traffic keys bound to handshake]
Client/Server exchange authenticated encrypted application records
```

Điểm quan trọng:
- **Key share ECDHE** tạo shared secret, **không** xác thực identity riêng nó.
- **Certificate** cung cấp public key danh tính của server được ràng buộc theo PKI; client phải xác minh chain và **hostname đã kỳ vọng**.
- **CertificateVerify** chứng minh private signing key phù hợp với certificate và ký một cấu trúc liên quan handshake transcript, với context do TLS 1.3 định nghĩa.
- **Finished** là MAC xác thực transcript với khóa được dẫn xuất từ handshake secrets; phát hiện bất đồng/đổi handshake và bảo đảm key confirmation theo thiết kế TLS.
- **HKDF** và key schedule tạo traffic secrets cho từng giai đoạn và chiều, không dùng raw DH secret trực tiếp làm một khóa AES duy nhất.
- **mTLS** bổ sung xác thực certificate/client proof nếu ứng dụng yêu cầu; server authentication không có nghĩa client đã được cấp quyền API.
- TLS 1.3 có thêm các chế độ PSK, resumption, HelloRetryRequest và nhiều quy tắc khác; sơ đồ trên chỉ minh họa **certificate-based full handshake** phổ biến, không thay thế RFC.

### 9.1. Điều client thật phải kiểm tra

Giả sử client kết nối `https://payments.example.com`. Một certificate CA-signed cho `files.example.com` không nên được chấp nhận chỉ vì cùng một tổ chức hoặc cùng CA. Client có một **expected reference identity** là `payments.example.com`, phải so sánh certificate identity theo quy tắc phù hợp.

Trong Java, ưu tiên HTTP/TLS client chuẩn (như `java.net.http.HttpClient` hoặc cấu hình TLS provider đã kiểm tra) và các trust manager mặc định/được cấu hình đúng, thay vì tự cài:

```java
// Anti-pattern (KHÔNG dùng):
// TrustManager that accepts every certificate
// HostnameVerifier that always returns true
```

Không dùng các anti-pattern này để khắc phục lỗi môi trường development. Hãy thêm CA tin cậy đúng cách, bảo đảm server trình đúng certificate, hostname và certificate chain; không đánh đổi xác thực peer để “kết nối cho chạy”.

### 9.2. Server chỉ chứng minh khóa của mình, vậy client là ai?

TLS server authentication chứng minh client đang kết nối tới một server có identity đúng theo PKI. Nó **không tự** chứng minh user hoặc client application có quyền gọi API. Sau handshake, ứng dụng vẫn cần xác thực token/session/client cert hoặc cơ chế khác, rồi áp authorization tới resource.

Mô hình mTLS có thể giúp ràng buộc **workload identity** với certificate phía client, nhưng authorization vẫn phải xác minh certificate identity có quyền thực hiện đúng hành động/tenant. Đừng dùng một boolean “TLS connected” làm điều kiện đủ cho mọi quyền.

## 10. Ràng buộc identity và key tránh những tấn công nào?

### 10.1. Key substitution / classic MITM

Đối thủ thay ephemeral public key; nếu transcript được ký và verify với trusted identity key, thay thế đó bị phát hiện. Nếu không có authentication, hai phía tạo shared secrets với attacker.

### 10.2. Unknown key-share (UKS)

Một cấu hình hoặc protocol có thể khiến Alice tin khóa phiên thuộc Bob trong khi Bob tin mình đang giao tiếp với Mallory; hoặc nhiều key được ánh xạ vào sai identity. Điều này nguy hiểm dù attacker không trực tiếp biết shared secret.

Phòng tránh bằng:
- Ký/xác thực cả hai identities và roles;
- Kiểm tra peer identity **được kỳ vọng** thay vì identity tự khai;
- Ràng buộc transcript/traffic keys với protocol và endpoints;
- Kiểm tra mapping key → principal/tenant và quyền.

### 10.3. Downgrade/cipher-suite confusion

Nếu thuật toán do đối thủ thay đổi ngoài phạm vi đã được xác thực, hai bên có thể rơi vào thuật toán yếu hoặc hiểu nhầm bản tin. Ký/bind selected suite, version, KDF, curve và cipher options; reject không nằm trong allowlist. Không tự thử “nhiều thuật toán tới khi một signature pass”.

### 10.4. Replay và identity của phiên

Chữ ký trên một transcript cũ không còn hợp lệ khi một bên tạo nonce/ephemeral key mới và xây transcript mới. Nhưng không đủ để nói mọi tác vụ sẽ chống replay: ứng dụng vẫn cần anti-replay cho request và AEAD record nonces/sequence numbers theo giao thức.

### 10.5. Key compromise impersonation (KCI)

Trong một số protocol, lộ long-term authentication key của Alice có thể ảnh hưởng tới nhiều tính chất khác nhau, không chỉ quyền giả làm Alice với người khác. Phân tích KCI đòi hỏi xét chính xác cấu trúc authenticated key exchange, ai bị lộ khóa và ai đang cố impersonate ai.

Không tự tuyên bố một mẫu “DH + chữ ký” là chống mọi dạng KCI hoặc chống tất cả lộ khóa; nên chọn giao thức có phân tích bảo mật phù hợp threat model.

### 10.6. Forward secrecy

Nếu mỗi phiên dùng **ephemeral X25519 key pairs mới** và các khóa tạm thời được xóa đúng lúc, lộ **long-term identity signing key** về sau không tự đưa attacker về các shared secrets cũ từ bản ghi công khai, theo giả định an ninh của scheme và protocol. Đây là một thành phần của **forward secrecy**.

Tuy nhiên, nếu một bản ghi session key, ephemeral private key hoặc plaintext từng bị lộ trước đó, chữ ký không thể làm dữ liệu ấy “chưa từng lộ”. Mô hình forward secrecy đầy đủ cần một protocol được thiết kế và chứng minh phù hợp; đừng suy ra chỉ từ việc mỗi lần gọi `KeyPairGenerator` đều tạo key mới.

### 10.7. Invalid curve / malformed public keys

Khi nhận X25519 public key từ network, không mặc định mọi dãy byte đều là public key an toàn. Phải dùng decoder/provider và key agreement implementation phù hợp chuẩn, xử lý input malformed, kiểm tra kết quả shared secret không thuộc trường hợp cấm (ví dụ all-zero theo hướng dẫn X25519) và từ chối lỗi.

**Không tự thiết kế** bước chuyển/giải mã public key hoặc bỏ qua ngoại lệ provider để “đồng ý khóa bằng mọi giá”.

## 11. Liên hệ với key wrapping

Chủ đề cha của bài học là **thỏa thuận và bọc khóa**. Hai cơ chế liên quan nhưng không đồng nhất:

- **Key agreement:** hai phía đóng góp khóa tạm thời, cùng tính shared secret (X25519/ECDH), sau đó HKDF dẫn xuất traffic keys. Cần xác thực ephemeral keys/peer identity để chống MITM.
- **Key wrapping/transport:** một bên tạo khóa đối xứng (CEK/DEK), rồi bảo vệ khóa đó để bên nhận khôi phục, ví dụ RSA-OAEP với public key người nhận hoặc KEM/AEAD key wrap phù hợp. Cần xác thực **khóa công khai người nhận** để tránh wrap CEK cho kẻ tấn công.

Nếu attacker thay public key của người nhận trong scheme wrap, sender có thể mã hóa CEK cho attacker; ở key agreement, attacker có thể tạo hai shared secrets giả. **Gốc vấn đề chung là thiếu authenticated binding giữa public key và đúng đối tác**.

Trong các framework như HPKE, đã có những cấu hình bảo mật và cách xác thực khác nhau (base/auth/PSK tùy profile). Không được gọi mọi hình thức mã hóa bằng public key là “đã xác thực đối tác”; hãy đọc đúng mode và mô hình chứng thực mà scheme cung cấp.

## 12. Các lỗi phổ biến và cách sửa

| Lỗi/nhận định | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| “X25519 cho cùng secret thì đã biết đó là Bob” | Attacker có thể tạo hai phiên với Alice/Bob | Verify trusted identity key và transcript |
| “Public key có fingerprint, vậy đã an toàn” | Fingerprint của key attacker cũng hợp lệ | So sánh với fingerprint/key từ kênh tin cậy |
| “Gửi certificate rồi không cần kiểm tra hostname” | Cert của host khác vẫn có chain hợp lệ | Kiểm tra expected DNS/application identity |
| “Accept all certificates để không bị SSL lỗi” | Tắt peer authentication, mở MITM | Cấu hình CA/PKI đúng |
| “Ký mỗi public key là đủ cho mọi handshake” | Không bind role, nonce, suite, partner | Ký/chứng thực toàn transcript theo spec |
| “Chữ ký hợp lệ với key gửi kèm chứng minh key thuộc Bob” | Attacker tự sinh cả signing key và signature | Trusted key được provision độc lập |
| “Nonce có thể giữ nguyên qua nhiều phiên” | Tạo cơ hội replay/nhầm phiên | Fresh nonce/ephemeral và kiểm tra state |
| “HKDF(sharedSecret) tự chống MITM” | Mallory có hai DH secrets riêng | Xác thực trước và bind transcript/KDF |
| “MAC Finished nghĩa là client là Alice” | MITM không xác thực cũng tính MAC cho phiên của hắn | Finished + identity authentication + binding |
| “TLS encryption bật là đủ, hostname verification không quan trọng” | Kênh có thể kết thúc tại endpoint sai | Full TLS certificate & name validation |
| “Sau khi handshake đúng thì mọi API đều được phép” | Authentication không thay authorization | Map identity tới quyền và resource |
| “Đổi thuật toán tới khi verify được” | Downgrade, protocol confusion | Version/cipher allowlist, fail closed |
| “TOFU là PKI đáng tin ngay từ lần đầu” | Lần đầu vẫn có thể bị MITM | Verify initial fingerprint out-of-band nếu cần |
| “Private identity signing key lộ không sao vì có ECDHE” | Attacker có thể giả identity trong phiên tương lai | Bảo vệ/rotate/revoke signing key |
| “Xóa Java byte[] là đủ để bảo đảm tất cả key đã biến mất” | JVM/provider có thể giữ bản copy | Memory hygiene, scope, KMS/HSM theo threat model |
| “Ciphertext AEAD có tag nên cũng biết người gửi là Bob” | Ai biết khóa hoặc public key có thể tạo message hợp lệ tùy scheme | Kiểm tra principal/sender authentication riêng |

## 13. Các bước kiểm thử một authenticated handshake

### 13.1. Positive tests

1. Alice mong gặp Bob; trusted Bob identity key đúng. Bob mong gặp Alice; trusted Alice key đúng.
2. Hai phía ghi transcript theo cùng version, encoding, roles, identities, nonces và ephemeral public keys.
3. Cả hai chứng cứ ký/MAC xác minh thành công với **keys được pin/cert validate đúng**.
4. Shared secret và traffic keys dẫn xuất đúng; record AEAD với mỗi hướng có nonce/sequence hợp lệ.
5. Application kiểm tra quyền của principal trước khi xử lý request.

### 13.2. Negative tests

| Ca thử | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Thay `bEphemeralPublic` | Mallory chèn một X25519 key khác | Chữ ký/transcript check fail |
| Thay `aEphemeralPublic` | Mallory sửa key phía initiator | Phiên Alice/Bob không thể thống nhất authenticated transcript |
| Sai trusted identity key | Verify bằng key Mallory thay vì Bob nhưng chính sách trông đợi Bob | Không chấp nhận identity Bob |
| Chữ ký impostor | Mallory dùng Ed25519 private key của mình ký | Verify bằng trusted Bob key thất bại |
| Sai tên đối tác | `bob` bị thay thành `mallory` | Identity/transcript binding thất bại |
| Sai role | Initiator/responder bị đảo | Fail theo transcript/signature rule |
| Sai version/suite | Chuyển X25519/HKDF profile sang thuật toán khác | Fail, không downgrade |
| Chữ ký từ phiên cũ | Nonce/challenge mới với signature cũ | Fail |
| Public key malformed/weak | Untrusted bytes, parser/curve input bất thường | Fail closed, không ra khóa phiên |
| Cert hợp lệ nhưng sai SAN | Server cert thuộc host khác | Hostname verification fail |
| Cert chain không được tin cậy | Self-signed unknown CA | Reject nếu không có trust policy phù hợp |
| Cert hết hạn/bị thu hồi | Không đạt certificate policy | Reject theo validation policy |
| Finished sai | Shared secrets hoặc transcript khác nhau | Reject trước app data |
| Replayed business request | Handshake đã xác thực nhưng lệnh bị gửi lại | Replay/idempotency policy xử lý |
| Unauthorized resource | Client đã xác thực nhưng không có quyền tenant/resource | Reject authorization |

Trong test automation, không chỉ assert “hai phía cùng derive một key” mà phải assert **đúng expected peer identity** và **các thay đổi attack-controlled bị từ chối**.

### 13.3. Debug interop khi hai bên không thể xác thực

Trình tự kiểm tra hợp lý:

1. Confirm protocol version, suite và handshake state tương đương.
2. Confirm **expected peer identity** và nguồn cấp trusted identity public key/certificate.
3. So sánh canonical transcript bytes hoặc transcript hash từ **fixture không nhạy cảm**; kiểm tra thứ tự trường, encoding public key, UTF-8, role, nonce và length prefix.
4. Nếu transcript khớp mà verify signature fail, kiểm tra signature algorithm/key format, certificate identity key, byte encoding của signature và policy.
5. Nếu chữ ký đúng mà session keys khác, kiểm tra đúng cặp ephemeral public/private keys, X25519 provider, HKDF extract salt/info và transcript hash.
6. Nếu key bằng nhau nhưng record fail, kiểm tra AEAD AAD, sequence/nonce management và traffic-key direction.
7. Nếu crypto pass nhưng API bị từ chối, kiểm tra policy authorization, principal mapping, tenant/resource và replay.

**Không log private keys, raw shared secrets, traffic keys hoặc production plaintext** để debug. Nếu cần trace, ưu tiên IDs phiên, thuật toán, độ dài key, trạng thái policy và transcript hash được quản lý theo quy định dữ liệu nhạy cảm.

## 14. Checklist triển khai trước production

### Client/Initiator

- [ ] Expected server identity được xác định bởi endpoint/application configuration đáng tin.
- [ ] Trusted public key của server được xác thực bằng certificate/path/name validation hoặc pin đã provision đúng.
- [ ] Server chứng minh private key tương ứng trên **đúng transcript** của phiên, bao gồm client nonce, server nonce, cả hai key shares, suite và roles.
- [ ] Không chấp nhận đổi key/cert/hostname một cách im lặng hay “trust all” khi có lỗi.
- [ ] Derive traffic keys từ authenticated handshake theo key schedule chuẩn và tách hướng.
- [ ] Không gửi dữ liệu nhạy cảm trước khi hoàn thành các bước handshake được yêu cầu.

### Server/Responder

- [ ] Key/certificate dùng xác thực server có vòng đời an toàn, lưu trong Keystore/KMS/HSM nếu phù hợp.
- [ ] Key shares/identities client được parse và validate đúng tiêu chuẩn, giới hạn kích thước/DoS.
- [ ] Nếu cần client authentication, xác minh client certificate/signature/PSK tương ứng với principal đã cấp.
- [ ] Chỉ map client identity tới tenant/role/resource sau khi chứng thực và kiểm tra chính sách.
- [ ] Chống replay và quản lý session/key update, sequence numbers và nonce theo protocol.

### Cả hai phía

- [ ] Không tự ghép DH+hash+AES rồi gọi là secure channel nếu chưa có formal authenticated key exchange design.
- [ ] Protocol/version, suite, roles, identity, transcript và encoding được định nghĩa, kiểm thử chéo.
- [ ] Có negative tests: MITM key replacement, wrong identity, wrong signer, replay, downgrade, malformed key, wrong Finished.
- [ ] Có chính sách certificate/key rotation, revocation, compromise response và audit.
- [ ] Có giới hạn số phiên, timeout, payload/key lengths, error behavior, resource consumption.
- [ ] Đảm bảo authentication không bị nhầm với authorization hoặc end-to-end identity across proxies.

## 15. Bài tập tự kiểm tra

**Câu 1.** Alice và Bob chạy X25519 thành công, nhưng public key trao đổi qua HTTP không có xác thực. Kẻ tấn công có thể nghe lén dữ liệu sau khi cả hai bật AES-GCM không?

**Đáp án:** Có thể khi attacker chủ động MITM bằng cách thay public keys và tạo hai phiên khóa riêng. Hắn có keys cho cả hai phiên nên có thể giải mã và mã hóa lại mà không phá X25519/AES-GCM.

**Câu 2.** Bên gửi gửi `bPub` và `SHA-256(bPub)` trong cùng gói. Alice có chắc `bPub` thuộc Bob không?

**Đáp án:** Không. Kẻ tấn công thay cả hai. Fingerprint phải được so với giá trị tin cậy từ trước hoặc xác minh qua một kênh xác thực độc lập.

**Câu 3.** Bob ký `bPub` nhưng không đưa `aPub` và client nonce vào bằng chứng. Vấn đề tiềm ẩn?

**Đáp án:** Bằng chứng không gắn đủ vào phiên cụ thể và public key của Alice, có thể gây replay/misbinding/unknown-key-share trong thiết kế thiếu ràng buộc. Nên ký transcript có cả hai key shares, identities, roles, suite và freshness.

**Câu 4.** TLS server đưa certificate hợp lệ CA nhưng cho hostname khác. Client có nên tiếp tục?

**Đáp án:** Không; certificate chain valid chưa chứng minh **đúng expected hostname**. Cần kiểm tra SAN/reference identity cùng certificate policy.

**Câu 5.** Nếu Mallory tự sinh Ed25519 key và ký đúng transcript của Bob thì có qua verify không?

**Đáp án:** Không khi Alice verify bằng **trusted Bob public key**. Nếu Alice lại dùng public key Mallory gửi kèm làm trust source, thiết kế đã sai và có thể bị MITM.

**Câu 6.** Vì sao cùng một shared secret không chứng minh hai bên muốn giao tiếp với cùng identity?

**Đáp án:** Secret chứng minh phép key agreement phù hợp, không chứng minh name/key binding. Phải ràng buộc expected identities và roles trong authenticated transcript và trusted-key mapping.

**Câu 7.** Key confirmation MAC đúng có chứng minh ngay rằng người đối diện là Bob không?

**Đáp án:** Không nếu chưa có peer authentication. MITM có thể tính confirmation MAC cho hai phiên DH do hắn lập. Confirmation chỉ có ý nghĩa trong ngữ cảnh xác thực đúng.

**Câu 8.** Khóa ký Ed25519 dài hạn của Bob bị lộ hôm nay. Điều gì xảy ra với phiên mới và phiên cũ?

**Đáp án:** Attacker có thể giả identity Bob trong handshake tương lai cho đến khi khóa được thu hồi/đổi; tính bí mật dữ liệu cũ phụ thuộc protocol, ephemeral private-key lifecycle, traffic keys và các secret có bị lộ hay không. Ephemeral DH đúng thiết kế có thể góp phần cho forward secrecy, nhưng không được hứa hẹn tuyệt đối chỉ dựa vào một chi tiết.

**Câu 9.** TOFU an toàn trước MITM ngay lần kết nối đầu tiên không?

**Đáp án:** Không. Nếu attacker xuất hiện lúc đầu, ứng dụng có thể lưu nhầm key attacker. Cần xác minh fingerprint qua kênh phụ khi mô hình an ninh yêu cầu.

**Câu 10.** Trong Java 17, `KeyAgreement.getInstance("X25519")` tạo shared secret; còn `Signature.getInstance("Ed25519")` phục vụ gì?

**Đáp án:** X25519 tạo shared secret qua hai key shares; Ed25519 ký và xác minh transcript để ràng buộc handshake vào trusted identity signing key. Hai thuật toán có nhiệm vụ khác nhau, không thay thế nhau.

**Câu 11.** Có cần thêm authorization sau khi mTLS đã chứng minh client certificate không?

**Đáp án:** Có. Chứng minh identity không cấp tự động mọi quyền; server vẫn phải map principal tới policy cho từng tenant/operation.

**Câu 12.** Khi cần bảo vệ CEK gửi cho Bob bằng RSA-OAEP thay vì key agreement, có cần xác thực public key Bob không?

**Đáp án:** Có. Nếu attacker thay public key Bob bằng key của mình, CEK có thể bị mã hóa cho attacker. Mô hình khác nhưng cùng vấn đề key–identity binding.

## 16. Sơ đồ ghi nhớ

```text
KEY AGREEMENT ALONE:
 Alice --- aPub --> [Mallory swaps] --- mPub --> Bob
 Alice <-- mPub --- [Mallory swaps] <-- bPub --- Bob
     |                      |                     |
  secret A-M          two shared secrets        secret M-B
     |                      |                     |
  encrypted channel <---- attacker ----> encrypted channel
  (not to Bob)           can decrypt            (not to Alice)

AUTHENTICATED KEY AGREEMENT:
 Alice <-> exchanged ephemeral public keys <-> Bob
   |                                              |
   |-- expected identity "bob"                    |-- expected identity "alice"
   |-- trusted Bob signing key                    |-- trusted Alice signing key
   |                                              |
   +---- same canonical transcript:
          version, suite, roles, identities,
          nonces, aPub, bPub
                    |
             Sign/verify transcript
                    |
             Reject substituted key
                    |
            X25519 + HKDF transcript-bound
                    |
          Direction-separated traffic keys
                    |
          Finished/key confirmation + AEAD
                    |
          Authenticate principal + authorize action
```

**Điểm quan trọng nhất:** *Thỏa thuận được cùng một khóa không nói lên rằng khóa đó thuộc đúng đối tác*. Muốn chống đánh tráo public key, phía kiểm tra phải có một **gốc tin cậy về danh tính/khóa**, xác minh **bằng chứng trên đúng transcript phiên hiện tại**, rồi dẫn xuất/sử dụng khóa phiên theo protocol được chuẩn hóa. Với kết nối ứng dụng thực tế, ưu tiên **TLS 1.3/mTLS được cấu hình xác thực certificate và hostname đúng cách** thay cho một handshake tự chế.

### Tài liệu tham khảo

- RFC 7748 — *Elliptic Curves for Security* (X25519): https://www.rfc-editor.org/rfc/rfc7748
- RFC 8032 — *Edwards-Curve Digital Signature Algorithm (EdDSA)* (Ed25519): https://www.rfc-editor.org/rfc/rfc8032
- RFC 5869 — *HMAC-based Extract-and-Expand Key Derivation Function (HKDF)*: https://www.rfc-editor.org/rfc/rfc5869
- RFC 8446 — *The Transport Layer Security (TLS) Protocol Version 1.3*: https://www.rfc-editor.org/rfc/rfc8446
- RFC 5280 — *Internet X.509 Public Key Infrastructure Certificate and CRL Profile*: https://www.rfc-editor.org/rfc/rfc5280
- NIST SP 800-56A Rev. 3 — *Pair-Wise Key-Establishment Schemes Using Discrete Logarithm Cryptography*: https://csrc.nist.gov/pubs/sp/800/56/a/r3/final
- Java SE 17 API, `KeyAgreement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html
- Java SE 17 API, `Signature`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- Java SE 17 API, `KeyPairGenerator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html
- Java SE 17 API, `Mac`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html
