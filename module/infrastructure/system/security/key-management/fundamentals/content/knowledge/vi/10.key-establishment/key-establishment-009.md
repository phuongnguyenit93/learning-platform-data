# Shared secret

> **Chương:** Key establishment  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Shared secret là gì?

**Shared secret (bí mật chung)** là giá trị bí mật mà **hai hoặc nhiều bên hợp lệ cùng biết hoặc có thể độc lập tính ra**, nhưng đối thủ ngoài nhóm không thể tính được trong mô hình bảo mật của giao thức. Shared secret là nguyên liệu quan trọng để thiết lập kênh bảo mật, xác thực bằng khóa đối xứng hoặc **dẫn xuất các khóa phiên (session keys)**.

Ví dụ, ứng dụng và máy chủ thực hiện một giao thức **Diffie–Hellman (DH)**: mỗi bên giữ một private key tạm thời, trao đổi public key và độc lập tính ra cùng một bí mật. Hai bên sau đó dùng **KDF** để tạo khóa đối xứng bảo vệ dữ liệu. Người nghe lén chỉ thấy public key được trao đổi và không thể thực tế tính bí mật chung nếu các giả định mật mã vẫn đúng.

Khái niệm shared secret **không đồng nhất** với một thuật toán, một định dạng byte hay một loại khóa duy nhất:

- Trong **PSK (pre-shared key)**, shared secret có thể là một bí mật đã được hai phía cấp phát trước.
- Trong **(EC)DH**, shared secret là kết quả của một phép **thỏa thuận khóa (key agreement)**, có thể chưa phù hợp để dùng trực tiếp cho AES/HMAC.
- Trong **TLS 1.3**, bí mật (EC)DHE/PSK được đưa qua **key schedule** để dẫn xuất nhiều traffic secrets và traffic keys khác nhau.
- Trong một số hệ thống có **key transport**, một bên sinh khóa rồi truyền nó dưới dạng được bọc/mã hóa cho bên nhận; sau khi giải mã, hai bên cũng có thể chia sẻ một secret, nhưng cách thiết lập khác DH.

**Câu hỏi quan trọng không chỉ là “hai bên có cùng secret không?” mà còn là “họ có đúng secret với đúng đối tác, đúng mục đích và đúng phiên không?”** Một shared secret mạnh về mặt toán học vẫn không an toàn nếu attacker chen giữa và mỗi bên thiết lập secret riêng với attacker.

### Mục tiêu học tập

Sau bài này, bạn có thể giải thích nguồn gốc của shared secret, phân biệt PSK với DH, hiểu vì sao cần **xác thực bên đối thoại và HKDF**, nhận diện rủi ro khi chia sẻ/lưu giữ bí mật, thực hiện ví dụ X25519 trong Java 17 và liên hệ với KMS/HSM, envelope encryption, cryptoperiod, rotation và audit.

## 2. Shared secret nằm ở đâu trong hệ thống mật mã?

Một ứng dụng bảo mật thường có nhiều loại khóa/bí mật với trách nhiệm khác nhau.

| Khái niệm | Vai trò | Có phải shared secret không? |
| --- | --- | --- |
| **PSK** | Bí mật đã được hai phía cấp phát trước để xác thực/thiết lập khóa | **Có**, theo mô hình chia sẻ trước |
| **DH/ECDH shared secret** | Giá trị hai bên độc lập tính từ private key của mình và public key đối tác | **Có**, nhưng thường là **đầu vào KDF**, chưa phải khóa sử dụng trực tiếp |
| **Session/traffic key** | Khóa đối xứng bảo vệ dữ liệu của phiên hoặc từng hướng truyền | Có thể **được dẫn xuất từ** shared secret; không nhất thiết là cùng byte với secret gốc |
| **Public key** | Giá trị được phép phân phối để thỏa thuận khóa hoặc xác minh chữ ký | **Không**: public key không phải bí mật |
| **Private key tạm thời** | Bí mật riêng của từng bên trong DH/ECDH | **Không**: không chia sẻ private key với đối tác |
| **Private key ký số** | Tạo chữ ký để chứng minh danh tính theo trust policy | Không; phải thuộc quyền kiểm soát bên ký |
| **DEK** (Data Encryption Key) | Khóa dùng mã hóa dữ liệu ứng dụng/file | Có thể được bên được ủy quyền cùng sử dụng, nhưng chức năng khác key-establishment secret |
| **KEK** (Key Encryption Key) | Bọc/bảo vệ DEK, thường do KMS/HSM quản lý | Không mặc nhiên là DH shared secret |
| **Pepper/HMAC key** | Secret bổ sung cho password hashing hoặc khóa MAC | Có thể chia sẻ theo thiết kế, nhưng cần tách mục đích/phạm vi |

Không nên gọi tất cả những giá trị trên là “một key”. Nếu quản lý khóa nhầm mục đích, một dịch vụ chỉ cần mã hóa lưu lượng có thể vô tình nhận quyền dùng private key ký hoặc KEK dài hạn.

### Shared secret có phải luôn được gửi qua mạng?

**Không.** Với ECDHE, hai phía trao đổi **public key**, không gửi bí mật chung dạng rõ. Ngược lại, PSK phải được cấp phát hoặc thiết lập trước qua kênh an toàn; cơ chế vận hành đó là một phần quan trọng của thiết kế. Khi dùng key transport, một bí mật có thể được truyền dưới dạng đã mã hóa/bọc, **không phải gửi raw secret qua kênh chưa xác thực**.

## 3. Ba cách thiết lập bí mật chung

### 3.1. Pre-shared key (PSK)

**PSK** là giá trị bí mật đã tồn tại tại cả hai phía trước khi phiên mới được thiết lập, ví dụ khóa của thiết bị đã được provision an toàn hoặc một khóa cấp phát qua hạ tầng quản lý bí mật.

Ưu điểm: hai bên có thể dùng PSK trong một giao thức được thiết kế để xác thực và dẫn xuất khóa mà không cần trao đổi khóa công khai theo kiểu truyền thống trong mọi trường hợp.

Rủi ro:

- **Provisioning:** bí mật phải được đưa tới đúng thiết bị/dịch vụ bằng kênh an toàn.
- **Phạm vi ảnh hưởng:** một PSK dùng chung quá nhiều thiết bị khiến một thiết bị bị chiếm có thể ảnh hưởng cả nhóm.
- **Rotation:** bên nhận phải cập nhật cùng key version mà không làm gián đoạn bất thường.
- **Forward secrecy:** việc **chỉ dựa vào PSK** không tự mang lại forward secrecy trước việc PSK bị lộ về sau.

Với hệ thống cần nhiều tenant hoặc workload, nên ưu tiên **bí mật riêng theo đối tượng/phạm vi** thay vì một PSK hard-code cho tất cả phiên bản phần mềm.

### 3.2. Thỏa thuận khóa Diffie–Hellman

Trong **Diffie–Hellman**, hai phía đóng góp vật liệu bí mật riêng và tính ra cùng một giá trị. Họ không cần truyền nguyên dạng shared secret qua mạng.

Ví dụ minh họa DH số học trên nhóm nhân modulo (không dùng các con số nhỏ trong production):

\[
A = g^a \bmod p,\qquad B = g^b \bmod p
\]

Trong đó `a` là private exponent của Alice, `b` là private exponent của Bob, còn `A` và `B` là public values trao đổi.

\[
Z_A = B^a \bmod p,\qquad Z_B = A^b \bmod p
\]

Vì `B^a = (g^b)^a = g^{ab}` và `A^b = (g^a)^b = g^{ab}` trong nhóm phù hợp, **`Z_A = Z_B`**. Kẻ nghe lén chỉ có `A`, `B` và các tham số công khai, nhưng việc tìm `Z` được giả định khó ở nhóm/độ mạnh đúng chuẩn.

**Đây là mô hình giảng giải toán học**, không phải hướng dẫn tự triển khai DH bằng số nguyên tố nhỏ. Hệ thống thật nên sử dụng **ECDHE/X25519/X448 hoặc nhóm DH được chuẩn hóa** với thư viện được bảo trì, kiểm tra tham số và chính sách phù hợp.

### 3.3. Key transport và hybrid encryption

Trong **key transport**, một bên tạo bí mật/khóa ngẫu nhiên rồi **bọc hoặc mã hóa** cho bên kia, ví dụ bọc DEK bằng **RSA-OAEP** dưới public key của bên nhận. Sau khi bên nhận giải mã, hai bên có thể biết cùng DEK.

Đây **không phải Diffie–Hellman**: không nhất thiết cả hai phía cùng đóng góp entropy cho khóa được truyền. Với các giao thức cũ kiểu RSA key transport, việc private key giải mã dài hạn bị lộ có thể làm lộ bí mật phiên cũ đã được ghi lại. **TLS 1.3 không còn dùng RSA key transport truyền thống**, dù vẫn có thể sử dụng chứng thư RSA để xác thực chữ ký handshake.

Trong **envelope encryption**, cùng một sơ đồ có thể dùng để bọc DEK mã hóa dữ liệu lưu trữ; tuy nhiên, đừng nhầm **wrapped DEK** của một file với **ECDHE shared secret** của kết nối TLS. Hai đối tượng có vòng đời và biên tin cậy khác nhau.

| Tiêu chí | PSK | (EC)DH key agreement | Key transport |
| --- | --- | --- | --- |
| Nguồn bí mật | Cấp phát/thống nhất từ trước | Được tính từ đóng góp private key mỗi bên | Một bên sinh rồi chuyển bằng cơ chế bảo vệ |
| Có gửi raw secret qua kênh công khai? | Không được | Không cần | Không được; truyền dưới dạng bảo vệ |
| Cần xác thực bên đối thoại? | Có, qua giao thức dùng PSK đúng cách | **Có**; DH đơn thuần dễ bị MITM | Có; xác thực public key bên nhận/nguồn gửi |
| Forward secrecy | Không tự có ở PSK-only | Có thể đạt khi dùng **khóa tạm thời** và loại bỏ bí mật đúng cách | Không mặc nhiên; phụ thuộc lược đồ và kiến trúc |
| Rủi ro vận hành | Phân phối/rotate PSK | Kiểm tra key share, auth, KDF, transcript | Quản lý private key giải mã, wrapped key, retention |

## 4. ECDHE và X25519: shared secret trong một phiên hiện đại

**ECDH (Elliptic-Curve Diffie–Hellman)** là thỏa thuận khóa dựa trên đường cong elliptic. Chữ **E** trong **ECDHE** nhấn mạnh việc sử dụng **khóa tạm thời (ephemeral)**. **X25519** là một cơ chế thỏa thuận khóa elliptic-curve được dùng rộng rãi trong các giao thức hiện đại.

~~~mermaid
sequenceDiagram
    participant A as Alice
    participant B as Bob
    A->>A: Sinh private/public key tạm thời a, A
    B->>B: Sinh private/public key tạm thời b, B
    A->>B: Gửi public key A
    B->>A: Gửi public key B
    A->>A: Tính Z_A = X25519(a, B)
    B->>B: Tính Z_B = X25519(b, A)
    Note over A,B: Z_A và Z_B trùng nhau nếu thao tác hợp lệ
    A->>A: KDF(Z, transcript, context) -> traffic keys
    B->>B: KDF(Z, transcript, context) -> traffic keys
    Note over A,B: Cần xác thực danh tính và hoàn tất handshake
~~~

Ở sơ đồ này, **public key tạm thời được trao đổi công khai**, còn private key và shared secret chỉ được giữ cục bộ. Hai bên cần thống nhất đúng tham số, phiên bản giao thức, public key và quy tắc KDF. Thư viện phải xử lý các **điểm đầu vào không hợp lệ/đầu ra all-zero** theo đặc tả; với X25519, nhiều giao thức yêu cầu hoặc khuyến nghị từ chối kết quả all-zero nhằm tránh các khóa yếu/đầu vào low-order.

### Vì sao không dùng trực tiếp raw shared secret làm AES key?

**Raw DH secret không nên được coi là một AES key có độ phân phối và ngữ cảnh sử dụng phù hợp theo mặc định.** Phải đưa qua **KDF**, thường HKDF, để trích xuất vật liệu khóa và dẫn xuất các khóa cụ thể.

Lợi ích:

1. **Chuẩn hóa đầu ra** theo chiều dài khóa đích, ví dụ 32 byte cho AES-256.
2. **Tách mục đích** giữa khóa mã hóa client→server, server→client, MAC/exporter và các giai đoạn khác.
3. **Ràng buộc ngữ cảnh**: protocol version, danh tính, transcript hoặc các tham số đã xác thực.
4. **Giảm việc dùng lại cùng byte bí mật** cho nhiều thuật toán không tương thích.

Đặc biệt, kết quả X25519 **32 byte** không có nghĩa có thể bỏ KDF và tự nhận là **khóa AES-256 độc lập đạt đủ mọi điều kiện mật mã**.

## 5. Shared secret không tự xác thực đối tác

DH bảo vệ trước **người chỉ nghe lén thụ động**, nhưng **DH đơn thuần không chống MITM chủ động**.

~~~mermaid
sequenceDiagram
    participant A as Alice
    participant M as Mallory
    participant B as Bob
    A->>M: Public key A (định gửi Bob)
    M->>B: Public key M1 (giả Alice)
    B->>M: Public key B
    M->>A: Public key M2 (giả Bob)
    Note over A,M: Alice và Mallory tính Z_AM
    Note over M,B: Mallory và Bob tính Z_MB
    A->>M: Ciphertext bảo vệ bởi key từ Z_AM
    Note over M: Mallory giải mã rồi có thể sửa/gửi tiếp
    M->>B: Ciphertext bảo vệ bởi key từ Z_MB
~~~

Alice và Bob đều đã tạo ra một shared secret **đúng về mặt toán học** nhưng **không chia sẻ cùng secret với nhau**. Mallory có thể giải mã và tái mã hóa giữa hai kênh nếu không có xác thực.

### Giải pháp: authenticated key exchange (AKE)

Một **giao thức thỏa thuận khóa có xác thực** thường kết hợp:

- **Public key/chứng thư đáng tin cậy** hoặc PSK đã cấp phát đúng danh tính.
- **Chữ ký số/MAC trên dữ liệu handshake** để gắn các key share với danh tính và transcript.
- **Key confirmation** để chứng minh các bên đã tính đúng vật liệu bí mật liên quan, thường qua thông điệp xác nhận có MAC trong một số giao thức.
- **Key schedule có ngữ cảnh** để chống tráo phiên và nhầm vai trò, thuật toán hoặc đối tác.
- **Kiểm tra trạng thái, hạn dùng và chống replay** trong phạm vi yêu cầu của giao thức.

Ví dụ TLS 1.3 dùng certificate và chữ ký handshake (trong phương thức xác thực dựa trên chứng thư) cùng với các thông điệp **Finished** để ràng buộc và xác nhận handshake. Với PSK, giao thức dùng cơ chế xác thực liên quan PSK theo đúng key schedule. **Xác thực peer identity và key confirmation là các bước riêng**, dù cùng tham gia vào một handshake.

**Không tự tạo giao thức** kiểu “gửi X25519 public key rồi tự dùng AES-GCM”. Nếu thư viện chuẩn hỗ trợ TLS 1.3, SSH hoặc giao thức AKE đã được đánh giá phù hợp, hãy ưu tiên thư viện đó.

## 6. Dẫn xuất khóa từ shared secret bằng HKDF

**HKDF (HMAC-based Key Derivation Function)** theo RFC 5869 có hai bước khái niệm:

1. **Extract:** dùng HMAC kết hợp `salt` với input keying material (`IKM`, chẳng hạn raw DH shared secret) để thu được `PRK` (pseudorandom key).
2. **Expand:** từ `PRK` và `info` (ngữ cảnh) tạo đủ byte khóa cần thiết.

~~~text
IKM = raw shared secret từ X25519
salt = dữ liệu được quy định bởi giao thức / key schedule

PRK = HKDF-Extract(salt, IKM)

key_client_to_server = HKDF-Expand(PRK, "app-v1|C->S|AEAD", 32)
key_server_to_client = HKDF-Expand(PRK, "app-v1|S->C|AEAD", 32)
key_exporter         = HKDF-Expand(PRK, "app-v1|exporter", 32)
~~~

Các chuỗi `info` trên **chỉ là ví dụ để giải thích domain separation**, không phải định dạng của TLS. Hệ thống thật phải dùng **định dạng info không mơ hồ** và bind các trường cần thiết, như phiên bản giao thức, thuật toán, vai trò và **danh tính/transcript đã xác thực**, theo đặc tả. `salt` trong HKDF **không nhất thiết là dữ liệu bí mật**; với một số key schedule, nó được lấy từ các secret ở giai đoạn trước.

~~~mermaid
flowchart TD
    DH[Raw DH shared secret] --> Extract[HKDF-Extract]
    Salt[Salt theo key schedule] --> Extract
    Extract --> PRK[PRK bí mật]
    PRK --> A[HKDF-Expand: role C to S]
    PRK --> B[HKDF-Expand: role S to C]
    PRK --> C[HKDF-Expand: exporter]
    Context[Protocol/context/transcript] --> A
    Context --> B
    Context --> C
    A --> AK[Traffic key hướng C to S]
    B --> BK[Traffic key hướng S to C]
    C --> CK[Khóa mục đích riêng]
~~~

### Lưu ý khi dùng các secret đầu ra

- Khóa hai hướng **khác nhau** theo chính sách; không tái dùng một khóa và một dải nonce giữa hai hướng.
- **Không lưu/ghi log** `IKM`, `PRK` hay traffic keys.
- **Không dùng trực tiếp một key** cho cả AES-GCM, HMAC và JWT signing vì tiện.
- Giới hạn chiều dài, số khối và cách gọi HKDF theo thư viện/chuẩn; đừng tự triển khai thủ công trong production nếu có API chuyên dụng.
- Với AES-GCM/ChaCha20-Poly1305, ngoài khóa dẫn xuất đúng vẫn cần **nonce không trùng dưới cùng key** và giới hạn dữ liệu/cryptoperiod.

**PBKDF2/Argon2id không phải lựa chọn mặc định để xử lý DH shared secret.** Chúng nhằm tăng chi phí thử password entropy thấp. HKDF phù hợp cho vật liệu đầu vào đã có entropy đủ cao và yêu cầu tách nhiều khóa theo ngữ cảnh. Nếu secret bắt nguồn từ password, hãy dùng **PAKE hoặc mô hình password-based được đánh giá**, không chỉ chèn password thẳng vào HKDF rồi gọi là shared secret mạnh.

## 7. Shared secret trong TLS 1.3

TLS 1.3 là ví dụ thực tế của việc **không dùng raw DH secret trực tiếp** làm khóa phiên:

1. Client và server đàm phán phiên bản/giao thức, trao đổi key shares (ví dụ X25519) trong handshake.
2. Hai bên tính shared secret (EC)DHE khi chọn phương thức có DH.
3. **TLS key schedule** kết hợp bí mật phù hợp (có thể bao gồm PSK và/hoặc (EC)DHE) bằng HKDF theo các giai đoạn.
4. Các bí mật cho handshake và application traffic được dẫn xuất riêng; tiếp đó tạo **traffic key** và **nonce/IV context** theo chuẩn.
5. Xác thực máy chủ qua chứng thư/chữ ký hoặc cơ chế được phép, xác minh transcript và các thông điệp Finished; nếu cần mTLS, client cũng xác thực phù hợp.
6. Dữ liệu ứng dụng được mã hóa có xác thực bằng AEAD như **AES-GCM** hoặc **ChaCha20-Poly1305**, không phải raw DH.

| Thành phần TLS 1.3 | Vai trò |
| --- | --- |
| (EC)DHE key share | Đóng góp bí mật tạm thời để hai bên tính secret |
| PSK/resumption secret | Đóng góp bí mật được chia sẻ từ trước hoặc từ phiên được khôi phục |
| HKDF/key schedule | Dẫn xuất secrets, keys và ngữ cảnh theo giai đoạn/mục đích |
| Certificate + CertificateVerify | Xác thực danh tính qua chứng thư/chữ ký khi dùng phương thức này |
| Finished | Xác minh tính nhất quán và xác thực các phần handshake theo cơ chế giao thức |
| Traffic key + AEAD | Bảo vệ các bản ghi theo hướng/giai đoạn phiên |

### Forward secrecy có tự xuất hiện không?

**Forward secrecy (tính bí mật chuyển tiếp)** là mục tiêu bảo vệ phiên cũ nếu **khóa xác thực dài hạn bị lộ về sau**, khi phiên đã sử dụng **khóa tạm thời an toàn** và các bí mật cần loại bỏ đã được xử lý đúng.

- Với **ECDHE tạm thời** cùng xác thực đúng, việc lộ **private key chứng thư máy chủ về sau** không nhất thiết làm lộ các traffic keys của phiên cũ đã ghi lại.
- Với **PSK-only** không có đóng góp (EC)DHE mới, không được mặc định có cùng bảo đảm forward secrecy trước việc PSK bị lộ.
- Với **PSK + (EC)DHE**, có thể giữ được những bảo đảm về forward secrecy tương ứng với các giả định của giao thức.
- **0-RTT early data** trong TLS 1.3 có mô hình bảo mật/replay khác dữ liệu sau handshake; ứng dụng phải cân nhắc chống replay và tính idempotent của thao tác.

Forward secrecy **không cứu được phiên hiện tại nếu endpoint đã bị chiếm và attacker lấy raw shared secret, traffic key hoặc plaintext trong RAM**. Nó cũng không thay xác minh chứng thư và ủy quyền ứng dụng.

## 8. Ví dụ Java 17: hai bên tính cùng X25519 shared secret

Java 17 cung cấp **`KeyPairGenerator` và `KeyAgreement`** cho X25519 thông qua provider hỗ trợ. Ví dụ sau chứng minh hai bên độc lập tạo ra **cùng raw shared secret**, rồi minh họa cách dùng HMAC-SHA-256 thực hiện **HKDF-Extract** và một bước **HKDF-Expand** để dẫn xuất 32 byte cho mục đích riêng.

**Lưu ý:** chương trình chạy cục bộ và **không có giao thức xác thực công khai khóa của đối tác**. Vì vậy đây **không phải AKE hoàn chỉnh** và không được đưa nguyên trạng vào production để thay TLS/SSH. Ví dụ chỉ tạo khóa và kiểm tra sự tương đồng, **không gửi dữ liệu bảo mật qua mạng**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class X25519SharedSecretDemo {
    private static byte[] agree(PrivateKey self, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(self);
        ka.doPhase(peer, true);
        byte[] z = ka.generateSecret();

        // Với X25519, từ chối kết quả all-zero theo chính sách giao thức.
        int any = 0;
        for (byte b : z) {
            any |= b & 0xff;
        }
        if (any == 0) {
            Arrays.fill(z, (byte) 0);
            throw new GeneralSecurityException("Invalid X25519 shared secret");
        }
        return z;
    }

    private static byte[] hmacSha256(byte[] key, byte[] data)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(data);
    }

    // Demo tạo đúng 32 byte bằng một khối HKDF-Expand SHA-256.
    // Production: dùng thư viện HKDF chuẩn, có transcript/identity binding.
    private static byte[] derive32(byte[] ikm, byte[] salt, String context)
            throws GeneralSecurityException {
        byte[] prk = hmacSha256(salt, ikm); // HKDF-Extract
        byte[] info = context.getBytes(StandardCharsets.UTF_8);
        byte[] input = Arrays.copyOf(info, info.length + 1);
        input[info.length] = 0x01;         // HKDF-Expand block T(1)
        try {
            return hmacSha256(prk, input);
        } finally {
            Arrays.fill(prk, (byte) 0);
            Arrays.fill(input, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator kpg = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = kpg.generateKeyPair();
        KeyPair bob = kpg.generateKeyPair();

        // Demo trao đổi public key tại chỗ. Ngoài đời phải xác thực chúng.
        byte[] aliceSecret = agree(alice.getPrivate(), bob.getPublic());
        byte[] bobSecret = agree(bob.getPrivate(), alice.getPublic());
        byte[] salt = new byte[32]; // Không bí mật, nhưng phải giống hai bên.
        new SecureRandom().nextBytes(salt);

        byte[] aliceKey = null;
        byte[] bobKey = null;
        try {
            if (!MessageDigest.isEqual(aliceSecret, bobSecret)) {
                throw new IllegalStateException("Key agreement mismatch");
            }
            String info = "demo-v1|alice-to-bob|AES-256-GCM";
            aliceKey = derive32(aliceSecret, salt, info);
            bobKey = derive32(bobSecret, salt, info);
            if (!MessageDigest.isEqual(aliceKey, bobKey)) {
                throw new IllegalStateException("KDF mismatch");
            }
            System.out.println("X25519 agreement + HKDF demo: OK");
            // Không in raw shared secret hay derived key.
        } finally {
            Arrays.fill(aliceSecret, (byte) 0);
            Arrays.fill(bobSecret, (byte) 0);
            Arrays.fill(salt, (byte) 0);
            if (aliceKey != null) Arrays.fill(aliceKey, (byte) 0);
            if (bobKey != null) Arrays.fill(bobKey, (byte) 0);
        }
    }
}
~~~

### Giải thích kỹ thuật của ví dụ

**`getInstance("X25519")`** yêu cầu thuật toán thỏa thuận khóa được provider hỗ trợ. `doPhase(peerPublicKey, true)` đưa public key đối tác vào quá trình tính secret; `generateSecret()` trả raw secret cho phía hiện tại. Trong đoạn mã này, **Alice và Bob đều ở cùng chương trình**, nên public key chưa đi qua ranh giới mạng không tin cậy.

`derive32` dùng `salt` giống nhau và `context` giống nhau nên hai phía tạo cùng output 32 byte; đây chỉ là **một khối HKDF-Expand**, không phải triển khai HKDF tổng quát cho mọi `dkLen`. Việc một khóa dài 32 byte **không cho phép kết luận** nó đã được ràng buộc với đúng danh tính peer hoặc có thể tái sử dụng vô hạn. Trong production cần thêm một **handshake đã xác thực, đóng gói byte chuẩn, key schedule đã được đánh giá, key confirmation và quản lý nonce**.

Để tạo hai khóa cho hai hướng, giao thức có thể dùng **những chuỗi `info` khác nhau** cho `alice-to-bob` và `bob-to-alice`. Nếu cần mã hóa AEAD, nonce phải **không trùng dưới cùng key**. Không sử dụng cùng byte `raw secret` để ký HMAC, mã hóa AES và sinh JWT key mà không tách miền.

**Không diễn giải việc `Arrays.fill` xóa vài mảng byte là hủy hoàn toàn bí mật khỏi bộ nhớ JVM.** Runtime/provider có thể tạo bản sao vật liệu trong object nội bộ hoặc vùng native memory; ứng dụng phải hạn chế quyền, log và dump nhạy cảm, sử dụng thư viện phù hợp và xem xét HSM/KMS khi cần.

## 9. Vòng đời shared secret và quản lý khóa

Shared secret có thể tồn tại rất ngắn hoặc lâu tùy nguồn gốc:

| Giai đoạn | Bí mật từ ECDHE tạm thời | PSK chia sẻ trước |
| --- | --- | --- |
| **Tạo** | Sinh private key tạm thời và tính secret từ peer public key | Sinh/provision PSK qua CSPRNG/KMS thích hợp |
| **Cấp phát** | Chia sẻ **public key** qua handshake; không gửi raw shared secret | Provision secret tới đúng dịch vụ/thiết bị bằng kênh an toàn |
| **Lưu trữ** | Giữ tạm trong vùng nhớ của giao thức, hạn chế bản sao | KMS/HSM/secret manager/keystore phù hợp; theo dõi phiên bản |
| **Sử dụng** | KDF dẫn xuất handshake/traffic keys cho phiên | Xác thực hoặc đóng góp vào key schedule theo giao thức |
| **Rotation/rekey** | Thỏa thuận secret mới cho phiên hoặc key schedule theo chuẩn | Phân phối PSK phiên bản mới, giai đoạn chuyển đổi có kiểm soát |
| **Thu hồi** | Đóng phiên, ngừng sử dụng khóa và revoke danh tính liên quan khi cần | Vô hiệu hóa PSK bị lộ, thiết bị/ứng dụng liên quan |
| **Hủy** | Giảm thời gian lưu raw secret/private key tạm thời | Hủy/loại bỏ PSK khi không còn phụ thuộc theo chính sách |
| **Audit** | Log metadata handshake, lỗi, phiên bản và identity | Log key ID/version, đơn vị được cấp, thao tác và trạng thái |

### Cryptoperiod của shared secret

**Cryptoperiod** là khoảng thời gian khóa/bí mật được phép sử dụng cho mục đích xác định. ECDHE secret có thể chỉ dùng trong **handshake của một kết nối**, còn PSK có thể sống qua nhiều kết nối và cần lịch rotation/tái cấp phát riêng.

**Không mặc định đóng một TLS connection xóa mọi secret**: có thể vẫn có resumption PSK/ticket, cache hoặc bản sao trong RAM theo kiến trúc. Ngược lại, **không nên lưu raw ECDHE secret vĩnh viễn** trong database “để debug”. Nếu cần phục hồi dữ liệu lưu trữ, phải có **DEK/KEK và chính sách backup**; không dựa vào khả năng tái tạo shared secret của phiên TLS đã kết thúc.

## 10. KMS/HSM, envelope encryption và quyền truy cập

**KMS (Key Management Service)** quản lý khóa, chính sách IAM, rotation và audit theo API của dịch vụ. **HSM** cung cấp vùng bảo vệ phần cứng cho việc sinh, giữ và dùng khóa mật mã theo khả năng thiết bị.

Sự liên hệ với shared secret:

- KMS/HSM có thể **sinh/lưu private key ECDH** hoặc hỗ trợ key agreement trong một số sản phẩm. **Không phải mọi KMS/HSM đều có API X25519/ECDH**; phải kiểm tra khả năng và ranh giới xuất key material.
- Với TLS thông thường, **thư viện TLS** thực hiện key agreement và quản lý traffic secret trong tiến trình hoặc stack giao thức. Private key xác thực máy chủ có thể được HSM bảo vệ, nhưng **traffic secret không mặc nhiên nằm trong HSM**.
- Với **PSK**, KMS/secret store có thể hỗ trợ cấp phát, phân quyền và thay version; phải ngăn bí mật bị đưa vào config, source, log và image.
- Trong **envelope encryption**, DEK mã hóa dữ liệu lưu trữ và KEK bọc DEK. Đây là bài toán **bảo vệ khóa lưu trữ** khác với DH shared secret bảo vệ phiên truyền thông.

~~~mermaid
flowchart LR
    A[Client] -->|TLS: key agreement + traffic keys| App[Ứng dụng]
    App -->|DEK + AEAD mã hóa dữ liệu| DB[(Ciphertext)]
    App -->|Wrap/Unwrap DEK theo IAM| KMS[KMS/HSM bảo vệ KEK]
    TLS[TLS stack quản lý secret của kết nối] --> App
    Policy[IAM, audit, rotation, trust policy] --> App
    Policy --> KMS
~~~

**Không có một shared secret duy nhất bảo vệ mọi tầng.** Hệ thống có thể dùng ECDHE cho transport, DEK cho dữ liệu, KEK cho việc bọc DEK, PSK riêng cho thiết bị và private key ký cho xác thực danh tính. **Tách khóa và quyền theo mục đích** giúp giới hạn tác động khi một thành phần bị chiếm.

## 11. Các lỗi và hiểu nhầm phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Gửi raw DH shared secret qua HTTP vì “hai bên cần biết” | Lộ bí mật trên mạng | Trao đổi public key theo giao thức DH; không gửi raw secret |
| Coi public key của peer gửi tới là đáng tin | Dễ bị MITM/key substitution | PKI, chữ ký handshake, PSK binding hoặc cơ chế AKE đã kiểm chứng |
| Dùng raw X25519 output trực tiếp làm AES key | Bỏ key schedule, context và separation | Dùng HKDF/giao thức key schedule phù hợp |
| Dùng cùng shared secret cho mọi mục đích | Key confusion, mở rộng phạm vi khi lộ khóa | HKDF info/context riêng theo mục đích và vai trò |
| Dùng DH tạm thời mà bỏ xác thực | Có thể thiết lập hai secret riêng với attacker | Authenticated handshake, key confirmation và trust binding |
| Tưởng PSK-only luôn có forward secrecy | PSK lộ có thể làm lộ phiên cũ tùy giao thức | Dùng PSK-DHE/ephemeral key exchange khi yêu cầu |
| Tái sử dụng một private key ECDH tạm thời quá lâu | Giảm bảo đảm về tính tạm thời và phạm vi phiên | Sinh ephemeral key theo giao thức, loại bỏ đúng lúc |
| Dùng password yếu trực tiếp làm PSK | Dễ bị đoán offline hoặc qua giao thức không phù hợp | PSK entropy cao hoặc giao thức PAKE phù hợp |
| Bỏ qua kiểm tra public key/secret không hợp lệ | Có thể sinh secret yếu hoặc lỗi giao thức | Dùng thư viện được duy trì, kiểm tra đầu vào/đầu ra theo đặc tả |
| Reuse AES-GCM nonce cùng traffic key | Phá bảo mật AEAD | Quản lý nonce/sequence number và giới hạn sử dụng khóa |
| Log raw shared secret để debug | Mất tính bí mật phiên đã ghi lại | Chỉ log key ID, protocol version, lỗi handshake cần thiết |
| Chỉ thay chứng thư mà không xử lý PSK/ticket đã lộ | Phiên khôi phục hoặc bí mật dài hạn vẫn rủi ro | Quản lý cert, PSK, ticket key, cache và sự cố riêng |
| Coi KMS tự lưu mọi ECDHE traffic secret | Sai ranh giới tin cậy khi đánh giá sự cố | Kiểm tra TLS stack, provider và kiến trúc KMS/HSM thật |
| Không gắn shared secret với danh tính/phiên | Unknown-key-share và tráo ngữ cảnh có thể xảy ra | Bind identities, transcript và policy trong AKE/key schedule |

### Unknown-key-share và nhầm danh tính

Trong một số tình huống, hai bên có thể tính cùng vật liệu khóa nhưng **bất đồng về danh tính đối tác hoặc ngữ cảnh khóa**. Các giao thức AKE phải ràng buộc danh tính, role, transcript và mục đích để chống **unknown-key-share/key confusion**. Không chỉ kiểm tra “secret bytes giống nhau” rồi tự kết luận rằng đã xác thực đúng peer.

### Key compromise khác endpoint compromise

Việc lộ một private key xác thực dài hạn **về sau** có thể không cho phép giải mã lưu lượng ECDHE cũ khi forward secrecy được đảm bảo. Nhưng nếu attacker chiếm endpoint lúc phiên đang chạy, lấy raw secret/traffic key hoặc plaintext trước/sau khi giải mã, forward secrecy **không ngăn được sự cố đó**.

## 12. Tình huống thực tế: thiết bị IoT kết nối tới gateway

Một công ty vận hành nhiều thiết bị IoT gửi dữ liệu cảm biến tới gateway. Mỗi thiết bị cần giao tiếp bảo mật, phân quyền đúng thiết bị và có thể bị thu hồi khi mất cắp.

**Thiết kế đơn giản nhưng không an toàn:** nhúng **một PSK chung** vào firmware của toàn bộ thiết bị, rồi dùng PSK đó mã hóa mọi bản tin. Nếu một thiết bị bị trích xuất firmware, attacker có thể lấy PSK và ảnh hưởng nhiều thiết bị.

**Thiết kế an toàn hơn, tùy khả năng thiết bị:**

1. Mỗi thiết bị được **provision danh tính và vật liệu xác thực riêng**, ví dụ khóa/chứng thư thiết bị hoặc PSK riêng, qua quy trình sản xuất/onboarding an toàn.
2. Thiết bị kết nối đến gateway bằng **TLS/DTLS hoặc giao thức AKE đã được đánh giá**, xác minh danh tính gateway; gateway cũng xác thực danh tính thiết bị theo chính sách.
3. Với chế độ dùng (EC)DHE, hai phía thiết lập shared secret **tạm thời**, sau đó key schedule dẫn xuất traffic keys; raw secret và private key tạm thời không gửi trên mạng.
4. Dữ liệu được bảo vệ bằng AEAD với nonce/sequence number do giao thức quản lý; quyền của thiết bị đối với tenant và loại dữ liệu được kiểm tra **riêng**.
5. Thiết bị mất cắp bị thu hồi chứng thư/PSK, khóa quyền, cập nhật danh sách tin cậy và theo dõi các phiên đang hoạt động.
6. Gateway ghi audit **device ID, phiên bản giao thức, key/cert reference và sự kiện thất bại**, không ghi shared secret hoặc plaintext nhạy cảm.

**Khi PSK bị lộ:** nếu PSK dùng chung nhiều thiết bị, phải đánh giá và có thể rotate trên diện rộng; thiết bị offline cần quy trình cập nhật và recovery. Với PSK riêng, phạm vi sự cố thường dễ cô lập hơn. Không chỉ đổi PSK trên gateway mà bỏ qua các thiết bị chưa cập nhật.

**Khi gateway lưu lịch sử:** dữ liệu cảm biến lưu trong database có thể cần **DEK/KEK và envelope encryption** độc lập với traffic keys của phiên thiết bị. Khi một session đóng, cơ chế lưu trữ vẫn phải giải mã được dữ liệu được phép đọc, không cần tái tạo ECDHE shared secret của phiên cũ.

## 13. Checklist thiết kế và vận hành shared secret

- [ ] Đã phân biệt **PSK, DH shared secret, session key, DEK và KEK** theo vai trò và vòng đời?
- [ ] Không truyền raw secret/private key qua đường mạng chưa bảo vệ hoặc log?
- [ ] Dùng **TLS 1.3/SSH/DTLS/AKE được đánh giá** thay vì tự phát minh handshake?
- [ ] Public key của peer được xác thực qua trust anchor, chứng thư hoặc cơ chế binding phù hợp?
- [ ] Có kiểm tra input key share và từ chối output yếu/không hợp lệ theo thuật toán, thư viện?
- [ ] Raw DH secret được xử lý bằng **KDF và context separation** chứ không dùng trực tiếp đa mục đích?
- [ ] Dẫn xuất tách theo hướng truyền, giai đoạn, role và giao thức; transcript/danh tính được xác thực?
- [ ] Có **key confirmation** và kiểm tra handshake đầy đủ theo giao thức?
- [ ] Nếu cần forward secrecy, đã xác định rõ PSK-only, PSK-DHE hay ECDHE tạm thời?
- [ ] Nonce AEAD không lặp dưới cùng traffic key; có chính sách key update/rekey và cryptoperiod?
- [ ] PSK được sinh bằng CSPRNG, cấp phát riêng phù hợp và có version/rotation/revocation?
- [ ] Quyền KMS/HSM/secret store cho PSK, private key, DEK, KEK đã được tách theo mục đích?
- [ ] Có chính sách về session resumption, ticket key/cache, backup và xử lý sự cố bị lộ?
- [ ] Audit ghi metadata quan trọng mà không lưu raw DH secret, PSK, traffic keys và plaintext?
- [ ] Đã thử các tình huống MITM, key substitution, sai danh tính, key share sai, replay và failover?

## 14. Câu hỏi tự kiểm tra

**1. Shared secret có phải luôn là một khóa AES không?**  
Không. Shared secret có thể là PSK, raw DH result hoặc vật liệu bí mật khác. Với DH, thông thường phải qua KDF để tạo các khóa đối xứng đúng mục đích.

**2. Trong X25519, Alice có gửi private key hoặc raw shared secret cho Bob không?**  
Không. Hai phía trao đổi public key; mỗi bên dùng private key của mình và public key của đối tác để tính cùng secret.

**3. Vì sao hai phía tính được cùng DH secret vẫn có thể bị MITM?**  
Vì DH thuần không xác thực public key. Attacker có thể thực hiện hai cuộc thỏa thuận riêng, một với mỗi phía, rồi giải mã và chuyển tiếp dữ liệu.

**4. HKDF dùng làm gì sau ECDHE?**  
HKDF trích xuất và dẫn xuất các key/secret đúng độ dài, mục đích, vai trò và ngữ cảnh; giúp tránh sử dụng raw shared secret trực tiếp hoặc dùng lại một key cho nhiều mục đích.

**5. PSK-only có tự bảo đảm forward secrecy không?**  
Không. Nếu PSK lâu dài bị lộ, tính bí mật của phiên cũ phụ thuộc giao thức; PSK-only không mặc nhiên có forward secrecy như một phiên thỏa thuận khóa tạm thời đúng cách.

**6. TLS 1.3 có gửi raw shared secret qua mạng không?**  
Không theo đường key agreement thông thường. Các bên trao đổi key shares, tính bí mật cục bộ và dùng key schedule để tạo traffic keys.

**7. KMS/HSM có phải lưu mọi shared secret TLS mới an toàn?**  
Không. Tùy kiến trúc, thư viện TLS có thể giữ traffic secret trong tiến trình; KMS/HSM thường bảo vệ khóa dài hạn, cung cấp thao tác ký/giải mã/unwrap và quản lý quyền.

**8. Khi private key xác thực máy chủ bị lộ sau này, có thể khẳng định mọi phiên cũ đã lộ không?**  
Không. Phiên có ECDHE tạm thời, xác thực đúng và bí mật tạm thời đã bị loại bỏ có thể có forward secrecy; nhưng phiên PSK-only hoặc endpoint từng bị chiếm cần đánh giá riêng.

## Ghi nhớ

**Shared secret là bí mật mà các bên hợp lệ cùng biết hoặc độc lập tính ra, đóng vai trò đầu vào để thiết lập khóa và kênh bảo mật.** Nó có thể đến từ **PSK, (EC)DH/X25519 hoặc cơ chế key transport**; cách thiết lập quyết định nhiều thuộc tính bảo mật. Thiết kế an toàn phải **xác thực đối tác, kiểm tra key share, dẫn xuất khóa bằng HKDF hoặc key schedule được đánh giá, tách khóa theo mục đích, quản lý nonce và cryptoperiod**, đồng thời bảo vệ secret khỏi lộ lọt và có chính sách rotation/thu hồi. Sự phối hợp giữa **chữ ký số/PKI, session keys, KMS/HSM, DEK/KEK, envelope encryption, IAM và kiểm toán** mới tạo nên vòng đời khóa an toàn; việc hai bên tính được cùng một dãy byte chỉ là bước khởi đầu.
