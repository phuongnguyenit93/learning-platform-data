# 15.1 TLS kết hợp thỏa thuận khóa, chứng thư, chữ ký và mã hóa phiên

**TLS (Transport Layer Security)** bảo vệ dữ liệu giữa hai đầu kết nối bằng cách **kết hợp nhiều cơ chế mật mã, mỗi cơ chế giải quyết một vấn đề khác nhau**:

1. **Thỏa thuận khóa** (thông thường ECDHE trong TLS 1.3) để hai phía thiết lập vật liệu bí mật chung mà không gửi trực tiếp khóa phiên trên đường truyền.
2. **Chứng thư X.509 và cơ chế tin cậy (PKI)** để bên nhận xác định public key của đối tác có được gắn đúng với danh tính mong đợi hay không.
3. **Chữ ký số của handshake** để xác minh bên được chứng nhận thực sự kiểm soát private key tương ứng và ràng buộc danh tính vào nội dung thương lượng.
4. **Dẫn xuất khóa và mã hóa đối xứng xác thực (AEAD)** để trao đổi application data với tính bí mật và toàn vẹn, bằng các khóa phiên riêng theo hướng gửi/nhận.

Không cơ chế nào thay thế hoàn toàn các cơ chế còn lại. **ECDHE một mình chưa xác thực máy chủ. X.509 được parse thành công chưa có nghĩa đáng tin. Chữ ký chứng minh quyền kiểm soát khóa nhưng không trực tiếp dùng để mã hóa mỗi byte dữ liệu. AES-GCM bảo vệ record nhưng phải có khóa phiên đúng và được ràng buộc với handshake an toàn.**

Bài học dùng **TLS 1.3** làm trọng tâm và so sánh vừa đủ với **TLS 1.2** để tránh nhầm thuật toán. Tại thời điểm tài liệu này, **RFC 9846 (07/2026)** là đặc tả TLS 1.3 mới thay thế RFC 8446; một số tài liệu và JDK triển khai vẫn tham chiếu RFC 8446 lịch sử. Các khái niệm handshake, CertificateVerify, Finished, HKDF và AEAD là nền tảng cần hiểu khi đọc Java JSSE.

## 1. TLS bảo vệ điều gì?

Giả sử ứng dụng Java gửi thông tin đăng nhập và dữ liệu nghiệp vụ đến một HTTPS server. Kẻ tấn công trên mạng có thể quan sát gói tin, thay đổi dữ liệu hoặc tìm cách đóng giả server.

TLS được thiết kế để cung cấp:

| Thuộc tính | Ý nghĩa | Cơ chế chính |
| --- | --- | --- |
| **Confidentiality** (bí mật) | Người quan sát đường truyền không đọc được application plaintext. | Khóa phiên đối xứng + AEAD record encryption. |
| **Integrity** (toàn vẹn) | Bản ghi bị sửa đổi không được chấp nhận như dữ liệu hợp lệ. | AEAD authentication tag, sequence/nonce và transcript verification. |
| **Server authentication** (xác thực server) | Client kiểm chứng đang nói chuyện với server mang danh tính dự kiến. | X.509 chain/trust/hostname + signature handshake + Finished. |
| **Optional client authentication** | Server có thể yêu cầu client cung cấp chứng thư và chứng minh private key. | mTLS: client Certificate/CertificateVerify, trust policy, Finished. |
| **Forward secrecy** (trong các kiểu trao đổi khóa thích hợp) | Lộ khóa ký dài hạn sau này không tự cho phép giải mã lại các phiên ECDHE đã ghi lén trước đó. | Khóa trao đổi tạm thời, hủy private ephemeral; key schedule TLS 1.3. |

**Ranh giới:** TLS không tự giải quyết quyền truy cập ứng dụng, lỗ hổng SQL injection, tài khoản bị chiếm quyền, endpoint bị cài malware, bản ghi plaintext ở server, hay việc người dùng gửi dữ liệu nhạy cảm tới server *đúng danh tính nhưng độc hại*. TLS bảo vệ **kết nối giữa các endpoint** theo danh tính/trust policy đã được cấu hình.

Đặc biệt, “đã có ổ khóa HTTPS” chỉ có nghĩa thiết lập kết nối theo các bước xác minh của client; ứng dụng vẫn cần authorization, xử lý dữ liệu và giám sát đúng.

## 2. Bốn vai trò mật mã và nơi xuất hiện

| Thành phần | Đầu vào / đối tượng | Vai trò trong TLS 1.3 | **Không phải vai trò** |
| --- | --- | --- | --- |
| **(EC)DHE key agreement** | Ephemeral private/public key shares của hai phía | Tạo shared secret đầu vào cho key schedule. | Không xác thực hostname hoặc CA một mình. |
| **X.509 certificate & chain** | Public key của identity + chứng nhận của issuer | Giúp ràng buộc public key vào danh tính thông qua PKI. | Không trực tiếp mã hóa application data. |
| **Handshake digital signature** | Private key của bên chứng thực, handshake transcript | Chứng minh quyền kiểm soát private key và chống thay đổi ngầm trong thương lượng. | Không ký riêng từng TLS record. |
| **HKDF key schedule** | DHE shared secret, transcript context, PSK khi có | Tạo handshake/application traffic secrets và keys theo hướng, giai đoạn. | Không tự xác thực CA nếu thiếu certificate/signature/trust. |
| **AEAD symmetric cipher** | Traffic key, nonce/sequence, plaintext/AAD | Mã hóa và xác thực các TLS records. | Không tự biết identity server. |
| **Finished message** | Handshake traffic secret + transcript hash | MAC chứng minh hai phía có secret thích hợp, ràng buộc toàn vẹn handshake. | Không phải chữ ký số bằng private key của certificate. |

Nên phân biệt ba khái niệm **key** khác nhau:
- **Khóa private lâu dài** của certificate (ví dụ RSA hoặc EC/Ed25519 ký handshake): phải giữ bí mật và bảo vệ theo vòng đời chứng thư.
- **Khóa private tạm thời** trong trao đổi ECDHE: dùng để tạo shared secret cho phiên; không đồng nghĩa private key của certificate.
- **Traffic keys đối xứng** dẫn xuất từ key schedule: thực sự dùng AES-GCM hoặc ChaCha20-Poly1305 mã hóa record. Mỗi hướng/giai đoạn có vật liệu khóa thích hợp.

Đọc hiểu TLS sẽ sai ngay nếu đồng nhất public key trong chứng thư với public key được gửi qua `key_share`, hay nghĩ khóa RSA của certificate trực tiếp giải mã mọi record HTTPS.

## 3. Đường đi của handshake TLS 1.3 có chứng thư server

Sơ đồ **đơn giản hóa, theo kiểu handshake 1-RTT không có HelloRetryRequest, không resumption, không client certificate**:

~~~text
             CLIENT                                        SERVER
               |                                              |
               | ClientHello                                  |
               | - supported_versions: TLS 1.3                |
               | - supported cipher suites                    |
               | - supported_groups / key_share (ECDHE)        |
               | - signature_algorithms, SNI, ALPN...          |
               |--------------------------------------------->|
               |                                              |
               | ServerHello                                  |
               | - selected version, cipher suite, key_share   |
               |<---------------------------------------------|
               |                                              |
               |  Hai phía tính shared secret ECDHE            |
               |  và dẫn xuất handshake traffic keys           |
               |                                              |
               |     {EncryptedExtensions}                     |
               |     {Certificate (server chain)}              |
               |     {CertificateVerify (digital signature)}   |
               |     {Finished (transcript MAC)}               |
               |<---------------------------------------------|
               |  [Các message trong { } được bảo vệ bằng      |
               |   handshake traffic keys]                    |
               |                                              |
               | Client xác minh chain/identity, signature,    |
               | transcript/Finished; gửi {Finished}          |
               |--------------------------------------------->|
               |                                              |
               |     Dẫn xuất application traffic keys        |
               |                                              |
               |<==== application data: AEAD records ========>|
~~~

Điểm chính:
1. `ClientHello` công bố phiên bản, cipher suites, nhóm key agreement, key shares và các extension theo giao thức. `SNI` giúp server chọn certificate theo hostname; **SNI tự nó không xác thực hostname**.
2. `ServerHello` chọn tham số thỏa thuận. Với chứng thư server và (EC)DHE, mỗi phía có thể tính shared secret tương ứng mà không truyền raw shared secret.
3. TLS 1.3 dùng **HKDF** để dẫn xuất keys; các thông điệp chứng thực chính sau `ServerHello` được mã hóa bằng handshake traffic keys.
4. Server gửi `Certificate` và `CertificateVerify`. Client xác minh certificate chain/trust, expected identity, chữ ký trên handshake transcript và `Finished`.
5. `Finished` là MAC để xác nhận toàn vẹn handshake và key confirmation; bên client cũng gửi Finished (sau các thông điệp chứng thực của client nếu được yêu cầu).
6. Sau handshake, application data truyền dưới dạng **AEAD TLS records**, dùng traffic keys dẫn xuất từ cùng quá trình đã ràng buộc handshake.

Đây không phải mô tả mọi trường hợp TLS 1.3: có `HelloRetryRequest`, resumption qua PSK, 0-RTT, client certificate và các hoạt động sau handshake. TLS 1.3 cũng có thể dùng **PSK-only key establishment** mà không trao đổi DHE; khi đó tính chất forward secrecy khác với kiểu PSK+DHE.

**Đừng nhầm “ServerHello mã hóa từ đầu”**: `ClientHello` và `ServerHello` khởi đầu ở trạng thái chưa được mã hóa bằng traffic keys TLS; lớp mã hóa handshake được thiết lập sau các thông điệp xác lập secret cần thiết. Việc mã hóa các authentication messages trong TLS 1.3 là một khác biệt quan trọng so với mô hình thường gặp của TLS 1.2.

## 4. Thỏa thuận khóa: vì sao không gửi khóa AES qua mạng?

### 4.1. ECDHE: dùng public key tạm thời, không chuyển private key

Với ECDHE, mỗi bên sinh cặp key agreement tạm thời rồi trao đổi **public key share**:

~~~text
Client:
  private ephemeral a       public A = a*G  ---> Server

Server:
  private ephemeral b       public B = b*G  ---> Client

Client tính shared secret = ECDH(a, B)
Server tính shared secret = ECDH(b, A)

=> hai bên có cùng vật liệu bí mật
=> kẻ chỉ quan sát A và B không nên suy ra secret
~~~

Đây là mô hình giải thích ECDH cổ điển; với **X25519**, các quy tắc tính toán/mã hóa điểm có đặc thù riêng. Không dùng sơ đồ này làm hướng dẫn triển khai tự chế một giao thức key exchange.

Các nhóm được sử dụng trong TLS 1.3 gồm **X25519**, **secp256r1 (P-256)** và các nhóm khác theo hỗ trợ/tiêu chuẩn. Chọn nhóm phù hợp thông qua chính sách JSSE/protocol, không chấp nhận nhóm tùy ý do một phía áp đặt.

**Key agreement không tự xác thực peer**. Một attacker MITM có thể tạo key share của chính mình với từng đầu nếu không có cơ chế xác thực/ràng buộc transcript. Vì vậy certificate, chữ ký `CertificateVerify` và MAC `Finished` là phần **cốt lõi**, không phải trang trí thêm sau ECDHE.

### 4.2. Forward secrecy gắn với khóa tạm thời, không với nhãn “TLS” chung chung

Khi phiên dùng (EC)DHE tạm thời và secrets ephemeral được xử lý đúng, việc lộ **private key chứng thư** của server về sau không tự cung cấp bí mật đã dùng để mã hóa phiên cũ. Đây là một ý chính của **forward secrecy**.

Tuy nhiên:
- Nếu máy chủ đang bị chiếm quyền khi phiên diễn ra, attacker có thể truy cập plaintext/secret đang sống hoặc can thiệp endpoint.
- Nếu ephemeral private key/traffic secrets bị log, dump hoặc giữ lại không an toàn, forward secrecy của giao thức không tự cứu được ứng dụng.
- Resumption và chế độ PSK-only có các điều kiện riêng; không hứa mọi đường thiết lập TLS đều có cùng mức forward secrecy.
- Tính chất này **không có nghĩa** dữ liệu đã lưu vào database hoặc log ứng dụng trở nên an toàn.

TLS 1.3 **không có static RSA key transport** như một số cipher suites TLS 1.2 cũ. Một server dùng chứng thư **RSA** trong TLS 1.3 vẫn có thể dùng **X25519/ECDHE để thỏa thuận khóa**; RSA private key lúc đó dùng chứng thực/chữ ký handshake (theo signature scheme được thương lượng), không trực tiếp giải mã premaster secret như RSA key exchange lịch sử.

## 5. Ví dụ Java 17: quan sát riêng thao tác X25519

Để nhận diện phần **key agreement** trong TLS, ta thử một ví dụ Java SE 17 **không triển khai TLS**. Chương trình này chỉ chứng minh hai cặp khóa X25519 tính ra shared secret giống nhau; nó **không có chứng thư, chữ ký handshake, HKDF-Expand-Label, transcript hay AEAD records**. Không lấy kết quả 32 byte đưa thẳng vào AES để tự thiết kế “TLS rút gọn”.

**Tệp `X25519RolesDemo.java`:**

~~~java
import java.security.*;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public class X25519RolesDemo {
    static byte[] agreement(PrivateKey own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement kx = KeyAgreement.getInstance("X25519");
        kx.init(own);
        kx.doPhase(peer, true);
        return kx.generateSecret();
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator kpg = KeyPairGenerator.getInstance("X25519");
        kpg.initialize(NamedParameterSpec.X25519);

        KeyPair a = kpg.generateKeyPair();
        KeyPair b = kpg.generateKeyPair();

        byte[] fromA = agreement(a.getPrivate(), b.getPublic());
        byte[] fromB = agreement(b.getPrivate(), a.getPublic());

        System.out.println("Raw shared secret bytes: "
                + fromA.length);
        System.out.println("Agreement matches: "
                + Arrays.equals(fromA, fromB));

        Arrays.fill(fromA, (byte) 0);
        Arrays.fill(fromB, (byte) 0);
    }
}
~~~

Chạy:

~~~bash
javac X25519RolesDemo.java
java X25519RolesDemo
~~~

Đầu ra đã kiểm chứng trên Java 17 có X25519:

~~~text
Raw shared secret bytes: 32
Agreement matches: true
~~~

**Giải thích:** `getInstance("X25519")` chọn key-agreement algorithm, `NamedParameterSpec.X25519` xác định tham số key generation, `doPhase` kết hợp private key của mình với public key đối tác. Dùng `Arrays.equals` để kiểm chứng **hai bên tính cùng byte secret**; trong production không log shared secret và không tự nghĩ `Arrays.fill` bảo đảm xóa mọi bản sao của bí mật.

**Phần còn thiếu để trở thành TLS** rất lớn và bắt buộc: xác thực danh tính key share, ràng buộc transcript, HKDF theo chuẩn, kiểm tra Finished, quản lý record sequence/nonce, anti-replay, certificate trust và chống downgrade. Vì vậy **dùng JSSE để chạy TLS** thay vì ghép các JCA primitive một cách thủ công.

## 6. Chứng thư X.509: key nào được tin cậy?

### 6.1. Certificate phục vụ xác thực identity, không tạo traffic key

Trong handshake chứng thực server, bản tin `Certificate` mang chuỗi chứng thư liên quan đến danh tính server (thường leaf và intermediate). Chứng thư leaf chứa **public key cho xác thực**. Bên server giữ **private key tương ứng** để chứng minh rằng nó được phép dùng identity đó, qua `CertificateVerify`.

Tình huống ví dụ:

~~~text
Server hostname: api.example.test
Certificate leaf:
  Subject / SAN: DNS:api.example.test
  Public key: RSA (chẳng hạn)
  Issuer: Intermediate CA
  Signature: CA ký trên nội dung certificate

Client có:
  Trust store chứa root CA được tin cậy
  Chính sách PKIX và expected hostname

Client phải:
  Xây/kiểm tra certificate chain + trust anchor
  Kiểm tra validity / signature / constraints / EKU / algorithm policy
  Kiểm tra SAN/hostname api.example.test
  Xác minh CertificateVerify trên handshake transcript
~~~

Tất cả tên trên đều chỉ là **tên minh họa**, không phải một certificate thật. Điều quan trọng là **public key trong leaf certificate không nhất thiết là key share ECDHE**: một certificate RSA có thể dùng chứng thực trong khi ephemeral agreement là X25519.

### 6.2. Parse không phải trust

`CertificateFactory.getInstance("X.509")` có thể đọc DER/PEM và tạo `X509Certificate`, nhưng **parse được chỉ chứng minh cấu trúc hợp lệ**. Để xác thực TLS server cần cơ chế PKIX/trust manager và kiểm tra hostname/endpoint identity.

Phân biệt:

| Việc làm | Kết quả | Chưa được bảo đảm |
| --- | --- | --- |
| `CertificateFactory.generateCertificate(...)` | X.509 có thể parse. | CA trust, hostname, hạn, mục đích, thu hồi. |
| `cert.checkValidity()` | Thời điểm nằm trong hạn theo cert. | Chuỗi CA đáng tin, hostname đúng. |
| `cert.verify(issuerPublicKey)` | Chữ ký certificate đúng với public key được đưa vào. | Public key issuer có thuộc trust anchor đã phê duyệt không. |
| `TrustManagerFactory`/PKIX | Kiểm tra chain theo truststore/chính sách cấu hình. | Quy tắc hostname nếu ứng dụng raw socket chưa bật endpoint identification. |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Yêu cầu áp dụng kiểm tra danh tính endpoint kiểu HTTPS khi handshake bằng JSSE phù hợp. | Không thay thế việc nạp truststore đáng tin. |

Trong Java raw `SSLSocket`/`SSLEngine`, **không được giả định kiểm tra hostname mặc nhiên diễn ra giống mọi HTTPS client**. Nếu kết nối raw tới server, cần bật `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` ở client theo mục đích và phiên bản JDK. Các HTTP client cao cấp thường đã quản lý trust/hostname nhưng phải tránh tùy chỉnh làm vô hiệu kiểm tra.

### 6.3. CA signature và handshake CertificateVerify là hai chữ ký khác nhau

**Chữ ký trên chứng thư (CA signature):** CA ký nội dung `TBSCertificate` của chứng thư leaf để xác nhận các thuộc tính và public key theo chính sách CA. Client kiểm tra chuỗi tới trust anchor.

**Chữ ký `CertificateVerify` (server signature):** server dùng **private key tương ứng leaf certificate** ký dữ liệu được quy định từ handshake transcript, chứng minh nó kiểm soát private key và ràng buộc phần thương lượng đã diễn ra. Nội dung/format ký phụ thuộc TLS 1.3 signature scheme.

Nếu chỉ kiểm tra chứng thư có chữ ký CA đúng nhưng **không chứng minh peer giữ private key**, kẻ tấn công có thể phát lại certificate công khai của một server hợp lệ. CertificateVerify là một phần giúp ngăn việc này.

### 6.4. Xác thực hai chiều mTLS khác kết nối HTTPS thông thường

- **Server-auth TLS:** client xác thực server; server **chưa nhất thiết** xác thực client bằng certificate. Ứng dụng thường dùng token/session/user authentication riêng.
- **Mutual TLS (mTLS):** server yêu cầu chứng thư client và kiểm tra chain/identity/purpose; client chứng minh private key qua handshake. Điều này có thể gắn với workload identity khi được triển khai đúng.
- **mTLS không tự định nghĩa authorization**: một client có certificate hợp lệ chưa mặc nhiên có quyền đọc mọi tài nguyên. Ánh xạ identity, tenant, scope và policy vẫn là việc của ứng dụng.

Một certificate self-signed được client đưa trực tiếp vào truststore có thể phục vụ **test loopback** hoặc pinning được phê duyệt. Điều này không có nghĩa “tắt kiểm tra trust”. Trong production, trust anchor phải được cung cấp qua kênh cấu hình đáng tin, quản lý rotation và kiểm tra identity tương ứng.

## 7. Chữ ký handshake, Finished và MAC record khác nhau ra sao?

Rất dễ gộp ba khái niệm:

### 7.1. `CertificateVerify`: chữ ký bằng private key danh tính

Server ký lên transcript/giá trị được chuẩn TLS xác định, client xác minh với public key certificate. Scheme chữ ký có thể là RSA-PSS, ECDSA hoặc EdDSA tùy chính sách, certificate và thương lượng.

**Không đồng nhất thuật toán chữ ký chứng thư của CA với scheme mà server dùng ở CertificateVerify.** Chứng thư có thể do CA ký bằng một scheme; key trong leaf certificate dùng scheme khác được hỗ trợ cho handshake.

### 7.2. `Finished`: MAC bằng khóa dẫn xuất, xác nhận toàn vẹn handshake

TLS 1.3 dẫn xuất `finished_key` qua **HKDF-Expand-Label** rồi tính **HMAC trên transcript hash**. Peer kiểm tra `Finished` trước khi coi handshake hoàn thành theo quy tắc giao thức.

Finished **không phải chữ ký số**, không dùng private key certificate để ký từng lần. Nó xác nhận rằng hai bên có đúng traffic secret/nhìn thấy handshake phù hợp, qua đó giúp phát hiện thay đổi handshake hoặc key mismatch.

### 7.3. AEAD authentication tag: bảo vệ từng TLS record

Sau handshake, application records được mã hóa/xác thực bằng AEAD như AES-GCM hoặc ChaCha20-Poly1305. Tag của từng record bảo vệ nội dung và dữ liệu ràng buộc theo định dạng record của TLS.

Tag này **không phải** `CertificateVerify` hay `Finished`. Application data không cần được server RSA-sign lại mỗi packet: chi phí/khái niệm khác nhau, TLS dùng traffic keys đối xứng hiệu quả cho data path.

| Câu hỏi | `CertificateVerify` | `Finished` | AEAD tag record |
| --- | --- | --- | --- |
| Dùng key gì? | Private key chứng thư (khóa bất đối xứng). | Secret/key dẫn xuất từ key schedule (MAC). | Symmetric traffic key tương ứng hướng gửi/nhận. |
| Bảo vệ đối tượng nào? | Handshake transcript theo chuẩn. | Toàn vẹn/chủ thể của handshake context. | TLS application/handshake record tương ứng. |
| Có phải chữ ký số không? | **Có**. | **Không**, là MAC. | **Không**, là authentication tag. |
| Có xuất hiện với từng application record? | **Không**. | **Không**. | **Có**, theo AEAD record format. |

### 7.4. Vì sao cần cả CertificateVerify lẫn Finished?

CertificateVerify ràng buộc **identity được cấp chứng thư** với transcript; Finished ràng buộc **key schedule/secrets được dẫn xuất** với transcript và xác nhận key possession. Kết hợp với certificate trust, TLS chống tấn công sửa đổi thương lượng và MITM hiệu quả hơn so với chỉ dùng DH thuần.

Không được lược bỏ Finished hay kiểm tra signature chỉ vì “đã có kết nối TCP” hoặc “server certificate parse được”.

## 8. Dẫn xuất khóa phiên TLS 1.3 bằng HKDF

### 8.1. Không dùng trực tiếp shared secret thô làm AES key

Đầu ra DHE/ECDHE là một **shared secret**. TLS 1.3 sử dụng **HKDF-Extract / HKDF-Expand-Label** và transcript context để tạo nhiều bí mật/khóa có công dụng khác nhau.

Sơ đồ khái niệm (không phải mã triển khai nguyên văn toàn bộ RFC):

~~~text
       Pre-shared key / PSK (nếu có)
                    |
                    v
                early secret
                    |
       ECDHE / DHE shared secret
                    |
                    v
              handshake secret
                    |
          +---------+---------+
          |                   |
  client handshake    server handshake
    traffic secret      traffic secret
          |                   |
    handshake keys       handshake keys

       handshake transcript + key schedule
                    |
                    v
                main/master secret
                    |
          +---------+---------+
          |                   |
  client application   server application
    traffic secret       traffic secret
          |                   |
  AEAD key + IV          AEAD key + IV
          |                   |
          +---- application records ----+
~~~

Tên giai đoạn và độ dài các đầu ra phải tuân thủ RFC. **Không tự tạo một khóa duy nhất rồi dùng cả hai hướng và mọi mục đích**: TLS tách biệt secrets theo vai trò, chiều truyền, epoch và transcript. Ví dụ minh họa giúp hiểu separation, không thay thế bản mô tả đầy đủ của **RFC 9846 `7 Key Schedule**.

### 8.2. Traffic keys và IV khác “private key” của certificate

- **Private key danh tính:** tồn tại qua nhiều kết nối, dùng để chứng thực theo chính sách; có thể ở HSM.
- **Private key key_share:** ephemeral, dùng tính ECDHE secret trong một handshake.
- **Client application traffic key:** mã hóa dữ liệu từ client sang server.
- **Server application traffic key:** mã hóa dữ liệu từ server sang client.
- **Traffic IV/nonce:** thông số record encryption, cùng key và sequence quy tắc để tránh nonce reuse.

Ngay cả khi cả hai hướng dùng **AES-128-GCM**, chúng không đồng nghĩa sử dụng cùng key raw hoặc nonce sequence.

### 8.3. Cipher suite TLS 1.3 **không** đồng nghĩa tất cả thành phần mật mã

Ví dụ `TLS_AES_128_GCM_SHA256` có nghĩa:
- AEAD record cipher: **AES-128-GCM**.
- Hash dùng cho transcript/HKDF: **SHA-256**.

Nó **không mã hóa sẵn tên key agreement** và **không quy định chữ ký certificate** trong chính tên suite. Key agreement group được thương lượng qua supported groups/key_share, signature scheme qua các extension tương ứng.

So với **TLS 1.2**:
- Tên suite cũ như `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` thường chứa gợi ý **ECDHE key exchange + RSA authentication + AES-GCM**.
- Trong **TLS 1.3**, suite `TLS_AES_128_GCM_SHA256` nói về **AEAD + HKDF hash**, không phải “TLS không còn certificate”.
- Không cố dùng suite TLS 1.2 như một suite TLS 1.3 vì hai phiên bản định nghĩa cipher suite khác nhau.

Trong TLS 1.3, các suites khác thường gặp gồm `TLS_AES_256_GCM_SHA384` và `TLS_CHACHA20_POLY1305_SHA256`; chính sách lựa chọn dựa trên hỗ trợ/provider, tiêu chuẩn tổ chức và khả năng thiết bị. Đừng suy ra kiểu certificate chỉ bằng việc nhìn tên `AES_128_GCM`.

## 9. Record encryption: tại sao TLS dùng AEAD?

Sau khi có traffic keys, TLS record layer bảo vệ message bằng mã hóa đối xứng **có xác thực (AEAD)** thay vì mã hóa mà không kiểm tra toàn vẹn.

### 9.1. Khái niệm bản ghi

~~~text
Application bytes
      |
      v
TLS record layer
  - chia thành các records theo protocol
  - chọn traffic key theo hướng/giai đoạn
  - tạo nonce từ traffic IV + sequence number
  - AEAD encrypt và sinh tag
      |
      v
Encrypted record trên TCP
      |
      v
Peer: kiểm tra tag -> chấp nhận và giải mã / từ chối
~~~

Trong TLS 1.3, record layer dùng phần header/metadata thích hợp làm **AAD** và mã hóa inner content theo đặc tả. Một bit bị sửa có thể khiến kiểm tra AEAD thất bại và kết nối bị kết thúc theo quy tắc TLS.

### 9.2. Quy tắc nonce cực kỳ quan trọng

Với AES-GCM, **không được lặp (key, nonce)** trong các lần mã hóa độc lập. TLS 1.3 quản lý nonce record bằng cơ chế được chuẩn hóa dựa trên **static IV được dẫn xuất và sequence number**, cùng giới hạn/switch keys phù hợp.

Không tự lấy `GCMParameterSpec` hay `Cipher` để mã hóa lại payload sau khi đã dùng `SSLSocket`: TLS provider đã xử lý AEAD, nonce và tag. Thêm một lớp AES tùy tiện không sửa lỗi certificate trust và có thể làm phức tạp vòng đời khóa.

`SSLSocket.getInputStream()` trả **application plaintext sau khi TLS xác thực record**; `getOutputStream()` nhận application plaintext để record layer mã hóa. Không cần ứng dụng biết raw traffic keys hoặc nonce.

### 9.3. AEAD không tự chống application replay

TLS record encryption bảo vệ trình tự record trong **một kết nối** theo cơ chế protocol. Nhưng ứng dụng vẫn có thể nhận **yêu cầu HTTP hợp lệ được gửi lại** trên phiên mới, ví dụ client retry, attacker có token hợp lệ hoặc 0-RTT. Phải có idempotency keys, nonce nghiệp vụ, hạn token/transaction checks và chính sách anti-replay theo ngữ cảnh.

**TLS 1.3 0-RTT early data** là trường hợp đặc biệt có nguy cơ replay; không dùng 0-RTT cho giao dịch có side effect không thể chấp nhận lặp lại nếu chưa có biện pháp xử lý theo chuẩn và nghiệp vụ.

## 10. TLS 1.3 so với TLS 1.2: những khác biệt quyết định

| Khía cạnh | TLS 1.2 | TLS 1.3 |
| --- | --- | --- |
| Key establishment | Có nhiều nhóm cipher suites, bao gồm RSA key transport lịch sử và ECDHE; an toàn phụ thuộc lựa chọn. | Handshake certificate thông dụng dùng (EC)DHE, không có static RSA key transport; hỗ trợ PSK modes. |
| Danh tính / chữ ký | Chứng thư, chữ ký/authentication theo luồng handshake và suite cụ thể. | `Certificate` + `CertificateVerify` gắn identity và transcript trong handshake certificate-based. |
| Cipher suite name | Thường biểu thị key exchange, authentication, bulk cipher, hash. | Định nghĩa **AEAD + HKDF hash**; key_share và signature scheme thương lượng tách biệt. |
| Dẫn xuất key | TLS 1.2 PRF/secret model riêng. | **HKDF key schedule** phân tách early/handshake/application secrets. |
| Bảo vệ handshake | Một số thông điệp handshake về chứng thư truyền trước khi bật encryption. | Phần lớn thông điệp handshake **sau ServerHello** được bảo vệ bằng handshake traffic keys. |
| Record protection | Có thể là AEAD hoặc cơ chế cũ tùy suite được phép. | Dựa trên **AEAD**. |
| Resumption / 0-RTT | Có session resumption; không có cơ chế 0-RTT TLS 1.3. | PSK/tickets và có thể 0-RTT với yêu cầu an toàn replay riêng. |
| Forward secrecy | Chỉ khi key exchange/cấu hình phù hợp (ví dụ ECDHE). | Certificate-based (EC)DHE thông dụng có forward secrecy, PSK-only cần đánh giá riêng. |

Không hiểu nhầm “TLS 1.2 luôn mất an toàn” hoặc “TLS 1.3 luôn an toàn bất chấp cấu hình”. Chính sách TLS 1.2 còn phụ thuộc cipher suite, patch level và ràng buộc triển khai; ưu tiên TLS 1.3 khi hai phía và yêu cầu tổ chức hỗ trợ.

Các phiên bản cũ như SSLv3, TLS 1.0/1.1 không phải lựa chọn cho thiết kế kết nối mới. Kiểm tra protocol list/cipher suites theo JDK thực tế thay vì hard-code fallback sang phiên bản yếu để vượt lỗi handshake.

## 11. Java dùng gì để chạy TLS? JSSE chứ không tự ráp JCA primitive

Java SE cung cấp **Java Secure Socket Extension (JSSE)** qua `javax.net.ssl`. JSSE tích hợp handshake, certificate processing, key exchange, signature verification, key schedule, record encryption và đóng kết nối.

| Thành phần Java | Nhiệm vụ |
| --- | --- |
| `SSLContext` | Cấu hình TLS provider, key managers, trust managers, `SecureRandom`. |
| `SSLSocket` / `SSLServerSocket` | Kết nối socket TCP được bảo vệ bởi TLS. |
| `SSLEngine` | TLS engine tách khỏi transport, dùng cho NIO/reactor/non-blocking. |
| `KeyManagerFactory` | Lấy key managers từ keystore/provider, giúp server chọn chứng thư/private key. |
| `TrustManagerFactory` | Lấy trust managers từ truststore để đánh giá peer certificates. |
| `SSLParameters` | Protocols, cipher suites, endpoint identification, yêu cầu client auth, SNI/ALPN liên quan. |
| `SSLSession` | Metadata của kết nối TLS đã negotiated: protocol, cipher suite, peer certificates và thông tin session. |
| `HttpsURLConnection` / `java.net.http.HttpClient` | HTTP/HTTPS APIs thường thực hiện TLS và identity checks khi cấu hình mặc định đúng. |
| `KeyStore` | Abstraction lưu key/cert/trust material; không nhất thiết đồng nghĩa HSM hay PKIX validator. |

**Điểm thiết kế:** Đối với HTTPS bình thường, ưu tiên `java.net.http.HttpClient` hoặc framework HTTP đáng tin được cập nhật, không tự viết raw TLS socket nếu không có nhu cầu đặc biệt. Với raw sockets, ứng dụng phải tự đảm bảo endpoint identification và cấu hình trust manager; **không tự cài `X509TrustManager` trả về rỗng và “trust all”**.

### 11.1. “SSLContext” không có nghĩa đang dùng SSLv3

Tên lớp `SSLContext`, `SSLSocket` có từ lịch sử API; chúng dùng được TLS hiện đại. `SSLContext.getInstance("TLS")` cho biết engine phục vụ TLS, còn protocol phiên thực được chọn thông qua supported/enabled protocols và thương lượng. Đừng coi từ “SSL” trong tên class là bằng chứng dùng giao thức SSL cũ.

### 11.2. Không cần ứng dụng tự gọi `Signature.verify` để xác minh server certificate

JSSE thực hiện các bước liên quan qua trust manager, certificate path processing và TLS handshake theo policy. Nếu ứng dụng parse certificate thủ công hoặc lấy `getPeerCertificates()`, điều đó không thay thế kiểm tra identity/chain trong handshake.

Với raw socket client, nên sử dụng:

~~~java
SSLParameters parameters = sslSocket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
sslSocket.setSSLParameters(parameters);
sslSocket.startHandshake();
~~~

Đây là mảnh minh họa; `sslSocket` là đối tượng đã tạo từ `SSLSocketFactory` phù hợp. Không dùng `setEndpointIdentificationAlgorithm(null)` để “tạm thời bỏ lỗi certificate”, vì đó là cách vô hiệu lớp kiểm tra danh tính quan trọng.

### 11.3. Tránh “trust-all” và “hostname verifier always true”

Những mã nguy hiểm:
- `X509TrustManager.checkServerTrusted(...)` có body rỗng.
- `HostnameVerifier.verify(...)` luôn trả `true`.
- `SSLContext.init(..., new TrustManager[]{trustAll}, ...)` để vượt lỗi `PKIX path building failed`.
- Bắt `SSLHandshakeException` rồi kết nối lại bằng HTTP plaintext hoặc TLS phiên bản yếu mà không có chính sách.
- Đưa một certificate từ kết nối chưa xác thực vào truststore và coi nó là “tin cậy” chỉ vì đã thấy trong response.

Sửa đúng là **cấu hình CA trust/chain, SAN hostname, certificate expiry, algorithm constraints và provider phù hợp**. Trong môi trường doanh nghiệp có CA nội bộ, trust anchor phải được phân phối từ kênh tin cậy và quản lý rotation.

## 12. Java 17+: demo handshake TLS 1.3 qua loopback có xác thực server

Ví dụ này đi qua **JSSE thực sự** thay vì chỉ chạy ECDHE/AES rời rạc. Server và client đều chạy trong một tiến trình Java, kết nối qua loopback TCP. Server dùng certificate trong PKCS#12 keystore, client chỉ tin certificate được nhập vào **truststore test riêng**, đồng thời **bật kiểm tra endpoint identity "HTTPS"**.

Cách này có mục tiêu học tập:
- **Key agreement, handshake signature, key derivation và record AES-GCM** được JSSE xử lý nội bộ.
- **Certificate + truststore + hostname verification** thực sự được áp dụng.
- Có thể quan sát `SSLSession` protocol và cipher suite, trao đổi dữ liệu `ping`/`pong` thành công.
- Không cần lộ raw private key, ECDHE secret hoặc traffic key.
- **Đây là demo local, không phải cách quản lý CA/credential production.**

### 12.1. Tạo certificate/key và truststore test bằng `keytool`

Chạy ở **thư mục thử nghiệm riêng**, chỉ dùng trên máy local, không commit các file test này. Các lệnh `keytool` dưới đây chạy với JDK 17+. `changeit` là **mật khẩu công khai của demo**, tuyệt đối không phải mật khẩu dùng cho keystore production.

~~~bash
# 1. Tạo RSA private key + chứng thư tự ký chỉ cho localhost.
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 2 \
  -storetype PKCS12 -keystore server.p12 \
  -storepass changeit -keypass changeit -noprompt

# 2. Xuất public certificate, không xuất private key.
keytool -exportcert -rfc -alias localhost -keystore server.p12 \
  -storepass changeit -file server.crt

# 3. Đưa certificate đó vào truststore CHỈ DÀNH CHO DEMO.
keytool -importcert -alias localhost -file server.crt \
  -keystore trust.p12 -storetype PKCS12 \
  -storepass changeit -noprompt
~~~

Dấu `\` cuối dòng là kiểu nối dòng của **Bash**; với PowerShell/CMD trên Windows, nhập các lệnh thành từng **dòng đơn, không có `\`**. Các bước đã được kiểm chứng trên Windows PowerShell với cùng các tham số chính.

Tạo certificate với `SAN=dns:localhost,ip:127.0.0.1` vì client kết nối loopback. `CN=localhost` một mình không phải cách chuẩn để bỏ qua SAN hostname check. Trên máy khác, hãy cung cấp SAN đúng danh tính thực, certificate CA cấp/chứng thực đúng chính sách và truststore phù hợp.

**Không commit** `server.p12`, `trust.p12` hay private key sinh ra. Khi demo xong, xóa các file test theo chính sách. Import certificate tự ký là thao tác **trust có chủ đích** trong môi trường lab; không nhập certificate lạ từ Internet vào truststore production.

### 12.2. Chương trình `Tls13LoopbackDemo.java`

Chương trình yêu cầu biến môi trường `TLS_DEMO_PASS` chứa password của **keystore test** và hai đường dẫn PKCS#12 đã tạo. Không có private key hay mật khẩu production trong code.

~~~java
import java.io.*;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class Tls13LoopbackDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Expected server and trust store paths");
        }

        String str = System.getenv("TLS_DEMO_PASS");
        if (str == null) {
            throw new IllegalStateException("Missing TLS_DEMO_PASS");
        }
        char[] pass = str.toCharArray();
        try {
            KeyStore ks = KeyStore.getInstance("PKCS12");
            try (InputStream in = new FileInputStream(args[0])) {
                ks.load(in, pass);
            }
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(ks, pass);

            SSLContext server = SSLContext.getInstance("TLS");
            server.init(kmf.getKeyManagers(), null, new SecureRandom());

            KeyStore ts = KeyStore.getInstance("PKCS12");
            try (InputStream in = new FileInputStream(args[1])) {
                ts.load(in, pass);
            }
            TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());
            tmf.init(ts);

            SSLContext client = SSLContext.getInstance("TLS");
            client.init(null, tmf.getTrustManagers(), new SecureRandom());

            try (SSLServerSocket listener = (SSLServerSocket)
                    server.getServerSocketFactory().createServerSocket(
                            0, 10, InetAddress.getLoopbackAddress())) {

                listener.setEnabledProtocols(new String[]{"TLSv1.3"});
                listener.setEnabledCipherSuites(
                        new String[]{"TLS_AES_128_GCM_SHA256"});

                ExecutorService pool = Executors.newSingleThreadExecutor();
                try {
                    Future<String> task = pool.submit(() -> {
                        try (SSLSocket s = (SSLSocket) listener.accept()) {
                            s.setEnabledProtocols(new String[]{"TLSv1.3"});
                            s.setEnabledCipherSuites(
                                    new String[]{"TLS_AES_128_GCM_SHA256"});
                            s.setSoTimeout(10000);
                            s.startHandshake();

                            String request = new String(
                                    s.getInputStream().readNBytes(4),
                                    StandardCharsets.US_ASCII);
                            s.getOutputStream().write(
                                    "pong".getBytes(StandardCharsets.US_ASCII));
                            s.getOutputStream().flush();
                            return request;
                        }
                    });

                    try (SSLSocket s = (SSLSocket)
                            client.getSocketFactory().createSocket(
                                    InetAddress.getLoopbackAddress(),
                                    listener.getLocalPort())) {

                        SSLParameters p = s.getSSLParameters();
                        p.setProtocols(new String[]{"TLSv1.3"});
                        p.setCipherSuites(
                                new String[]{"TLS_AES_128_GCM_SHA256"});
                        p.setEndpointIdentificationAlgorithm("HTTPS");
                        s.setSSLParameters(p);
                        s.setSoTimeout(10000);
                        s.startHandshake();

                        SSLSession session = s.getSession();
                        s.getOutputStream().write(
                                "ping".getBytes(StandardCharsets.US_ASCII));
                        s.getOutputStream().flush();

                        System.out.println(
                                "Protocol: " + session.getProtocol());
                        System.out.println(
                                "Cipher suite: " + session.getCipherSuite());
                        System.out.println("Server authenticated: "
                                + (session.getPeerCertificates().length > 0));
                        System.out.println("Client received: " + new String(
                                s.getInputStream().readNBytes(4),
                                StandardCharsets.US_ASCII));
                    }

                    System.out.println("Server received: "
                            + task.get(10, TimeUnit.SECONDS));
                } finally {
                    pool.shutdownNow();
                }
            }
        } finally {
            Arrays.fill(pass, '\0');
        }
    }
}
~~~

### 12.3. Biên dịch/chạy và stdout

Với **Bash**:

~~~bash
export TLS_DEMO_PASS=changeit
javac Tls13LoopbackDemo.java
java Tls13LoopbackDemo server.p12 trust.p12
~~~

Với **Windows PowerShell**:

~~~powershell
$env:TLS_DEMO_PASS = "changeit"
javac Tls13LoopbackDemo.java
java Tls13LoopbackDemo server.p12 trust.p12
Remove-Item Env:TLS_DEMO_PASS
~~~

Chỉ dùng mật khẩu `changeit` vì đây là lab có secret **vô giá trị ngoài demo**. Không đưa mật khẩu production lên command line, stdout, code hoặc repository. Trong production, tích hợp secret delivery theo workload identity/secret manager và keystore/HSM policy.

Đầu ra đã kiểm chứng bằng JDK 17 với JSSE hỗ trợ TLS 1.3 và AES-128-GCM, certificate/keytool test đúng hướng dẫn:

~~~text
Protocol: TLSv1.3
Cipher suite: TLS_AES_128_GCM_SHA256
Server authenticated: true
Client received: pong
Server received: ping
~~~

**Khi môi trường không hỗ trợ TLS 1.3 hoặc cipher suite được khóa cứng trong demo**, handshake sẽ thất bại. Đây là điều cần xử lý bằng cấu hình/chính sách được hỗ trợ, không fallback im lặng sang SSL/TLS yếu. Tùy provider, thông báo exception và cách quản lý truststore có thể khác.

### 12.4. Phân tích chính xác các thành phần TLS

**Server side:**
- `KeyStore("PKCS12")` nạp certificate và private key **dùng để chứng thực server**; `KeyManagerFactory` cung cấp key material cho JSSE.
- `SSLContext.init(kmf.getKeyManagers(), null, ...)` để server có thể trình certificate và chứng minh private key.
- `SSLServerSocket` chấp nhận TLS connection. Các tham số TLS 1.3 và AEAD suite được yêu cầu rõ ràng ở listener và socket.
- Demo **không bật client certificate authentication**. Đừng nhầm đây là mTLS; server chỉ biết client đã hoàn thành handshake, **chưa được xác thực bằng chứng thư client**.

**Client side:**
- `TrustManagerFactory.init(ts)` cấu hình **truststore riêng có certificate demo**; server certificate sẽ được kiểm tra theo tin cậy đã cấu hình.
- `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` giúp kiểm tra expected peer identity. SAN phải đúng host/IP kết nối.
- `SSLSession.getProtocol()` và `getCipherSuite()` chỉ trả metadata đã thương lượng, **không tiết lộ raw secret**.
- `session.getPeerCertificates().length > 0` ở đây dùng để minh họa server đã đưa certificate. Nó **không phải toàn bộ phép chứng minh trust** nếu dùng riêng lẻ; đảm bảo quan trọng đến từ handshake JSSE với trust manager + hostname verification cấu hình đúng, và việc `startHandshake()` hoàn tất mà không bị exception.

**Đường dữ liệu:**
- Chuỗi `ping`/`pong` được ứng dụng ghi/đọc dưới dạng plaintext ở `InputStream`/`OutputStream`.
- JSSE thực thi ECDHE, ký/verify handshake, Finished, HKDF, AEAD records, nonce/tag phía dưới. Ứng dụng không tự gọi `Cipher.getInstance("AES/GCM/NoPadding")` cho dữ liệu trong `SSLSocket`.
- Mã hóa chỉ bảo vệ **transport giữa hai đầu**. Nếu server ghi `ping` ra log hoặc chuyển plaintext qua kết nối khác không mã hóa, TLS của kết nối ban đầu không ngăn sự rò rỉ sau đó.

**Giới hạn demo:**
- Certificate chỉ có hiệu lực 2 ngày và tự ký; không dùng để phục vụ domain thật.
- Demo truststore pin trực tiếp certificate tự ký. Trong production cần một PKI/trust model và rotation đúng.
- TLS record cipher suite được **khóa cứng để tạo stdout dễ kiểm chứng**, không có nghĩa mọi hệ thống production phải bắt buộc dùng duy nhất `TLS_AES_128_GCM_SHA256`.
- Chương trình không có HTTP parser, timeout tổng thể, certificate rotation, cancellation đầy đủ hoặc thiết kế server tải cao. Nó là lab TLS thật, không phải HTTP server production.

## 13. Khi chứng thư, chữ ký, khóa và mã hóa cùng tạo nên “server authentication”

Xét hai trường hợp có cùng ECDHE và AES-GCM:

### 13.1. Có ECDHE + AES-GCM nhưng không xác thực server

~~~text
Client --key_share--> attacker --key_share--> real server
Client <--attacker share-- attacker <--server share--

Client và attacker có một secret A.
Attacker và real server có một secret B.
Attacker giải mã/sửa/mã hóa lại traffic giữa hai bên.
~~~

ECDHE bảo vệ secret trước người **chỉ quan sát thụ động**, nhưng không chặn MITM nếu không xác thực key exchange. Chữ ký trên handshake của server, certificate chain/trust và Finished ngăn kẻ chỉ có key share tự nhận là server được cấp chứng thư.

### 13.2. Certificate đúng nhưng hostname verification bị tắt

Client đã tin CA A, nhưng attacker có một chứng thư hợp lệ từ CA A cho **domain khác**. Nếu client chỉ kiểm tra “cert được CA tin” mà không kiểm tra SAN/expected hostname, kết nối có thể được chấp nhận sai danh tính.

**Bài học:** “public key được một CA tin cậy ký” chưa đủ; phải gắn với **định danh endpoint đang gọi**, mục đích sử dụng và ràng buộc giao thức.

### 13.3. Certificate parse đúng nhưng private key không khớp

Server đưa certificate leaf có public key RSA X nhưng private key của server lại thuộc RSA Y. Chữ ký `CertificateVerify` không thể xác minh với public key X, nên handshake không được chấp nhận. Đây là ví dụ lý do cần **proof of possession** của private key trong handshake.

### 13.4. Certificate và signature hợp lệ, nhưng Finished sai

Kể cả một số phép xác minh certificate/signature thành công, nếu `Finished` không khớp transcript/key material, phải **abort**, không chuyển sang application data “để thử”. Finished kiểm tra sự phù hợp của secret và handshake context.

### 13.5. Handshake hợp lệ, application tag sai

Một record AES-GCM bị sửa trên đường truyền sẽ không qua AEAD integrity check, gây lỗi kết nối theo TLS protocol. Không được trả plaintext chưa xác thực cho ứng dụng hoặc bỏ qua lỗi rồi xử lý record như hợp lệ.

## 14. Các lỗi TLS thường gặp trong Java JSSE

| Triệu chứng / ngoại lệ | Nguyên nhân khả dĩ | Điều cần kiểm tra |
| --- | --- | --- |
| `SSLHandshakeException`, đôi khi chứa `PKIX path building failed` | Server chain không xây được đến trust anchor được tin. | Truststore, missing intermediate, CA chính thức, certificate policy; không trust-all. |
| `SSLHandshakeException` do hostname mismatch | SAN không có host/IP đích hoặc endpoint identity không khớp. | URL/hostname thực, SAN, SNI, certificate rotation; không bỏ kiểm tra tên. |
| `CertificateExpiredException` (thường là cause) | Certificate ngoài hạn thời gian hiệu lực. | Đồng hồ, NotBefore/NotAfter, kế hoạch gia hạn. |
| `SSLHandshakeException` / `SSLProtocolException` | Hai bên không hỗ trợ protocol/cipher suite/key share/signature scheme tương thích. | TLS 1.3 support, cấu hình JDK/provider, thuật toán bị disabled, log negotiation đã sanitize. |
| `SSLException` khi đọc/ghi | AEAD/tag/record xử lý lỗi, peer đóng lỗi hoặc protocol/transport gặp vấn đề. | Ngữ cảnh kết nối, có thể là lỗi mạng, dữ liệu hỏng; không suy từ message duy nhất. |
| `SocketTimeoutException` | Timeout mạng/handshake/đọc theo socket policy. | Network connectivity, timeout và tải server; không mặc định là cert hỏng. |
| `UnrecoverableKeyException` / `KeyStoreException` | Keystore không đọc được private key, password sai hoặc alias/key config không đúng. | KeyManagerFactory, PKCS12/JKS/provider, key alias, mật khẩu từ secret manager. |
| `SSLHandshakeException` khi bật mTLS | Server yêu cầu cert client nhưng client thiếu cert hoặc không được tin. | Client key managers, certificate/key usage, truststore server, yêu cầu client auth. |
| Kết nối thành công với `TLSv1.2` trong khi kỳ vọng `TLSv1.3` | Enabled protocols không như dự định hoặc peer không hỗ trợ. | `SSLSession.getProtocol()`, config, hệ thống trung gian và policy. |
| Hoàn tất TLS nhưng HTTP 401/403 | TLS có thể đúng, nhưng user/token/authorization sai. | Authentication/authorization ứng dụng **khác** TLS handshake. |

**Đừng xác định nguyên nhân chỉ từ tên `SSLHandshakeException`.** Một exception tổng quát có thể bọc lỗi certificate, thuật toán, ciphers, key material hoặc protocol. Cần xem cause chain/trust manager/provider một cách có kiểm soát, không in private key, token hoặc toàn bộ handshake secrets ra log.

### 14.1. Debug bằng thuộc tính JDK nhưng phải bảo vệ log

Ở môi trường lab có thể bật debug JSSE, ví dụ:

~~~bash
java -Djavax.net.debug=ssl,handshake Tls13LoopbackDemo server.p12 trust.p12
~~~

**Không khuyến khích dùng debug này trong production hoặc đính kèm nguyên log công khai**. Handshake log có thể bao gồm hostname, certificate, key IDs, thông số nội bộ và metadata nhạy cảm; ở một số chế độ debug khác còn có dữ liệu cần bảo vệ nghiêm ngặt. Dùng cấu hình log ngắn hạn, hạn chế ACL/retention và sanitize trước khi chia sẻ.

### 14.2. SNI và ALPN không phải chữ ký

- **SNI (Server Name Indication)**: client cho server biết hostname mong muốn để server chọn certificate/virtual host; đây không phải bằng chứng certificate hợp lệ.
- **ALPN (Application-Layer Protocol Negotiation)**: hai phía thương lượng giao thức ứng dụng, ví dụ `h2` hoặc `http/1.1`. Nó **không tạo ra key exchange riêng** thay TLS, và không tự cấp quyền truy cập.
- Nếu server chọn certificate không khớp SNI/expected host, JSSE client vẫn phải kiểm tra hostname/trust theo policy.

## 15. Session resumption, PSK và 0-RTT: không phải lúc nào cũng trình certificate mới

TLS 1.3 có thể tiếp tục kết nối dựa trên **session ticket/resumption PSK**. Trong các kiểu này, một handshake được nối lại có thể **không gửi Certificate/CertificateVerify mới**, vì xác thực được kế thừa/ràng buộc thông qua trạng thái PSK/session theo thiết kế giao thức.

Điểm cần phân biệt:

| Cơ chế | Vai trò | Rủi ro cần quản lý |
| --- | --- | --- |
| **Full handshake, certificate authentication** | Xác thực server qua chain/certificate signature và thiết lập secret mới. | Chain/hostname, signature scheme, key share/trust. |
| **PSK resumption** | Tiếp tục liên kết dựa trên secret đã tạo từ kết nối/handshake trước. | Ticket key lifecycle, scope của PSK, identity binding, expiry. |
| **PSK + DHE** | Kết hợp resumption PSK với ephemeral key share. | Cấu hình đúng để hưởng forward secrecy theo mô hình. |
| **PSK-only** | Có thể không có DHE mới ở chế độ cho phép. | Không giả định có forward secrecy giống full DHE. |
| **0-RTT early data** | Cho phép gửi một số application data sớm trong resumption phù hợp. | Có **nguy cơ replay**, không phù hợp thao tác không idempotent nếu chưa chống replay. |

**Không phát biểu “TLS luôn gửi chứng thư trong mọi handshake”**. Câu đúng là: **TLS certificate-based full handshake** sử dụng certificate và chứng minh private key; handshake PSK có logic xác thực khác. Phải hiểu cấu hình và session state của hệ thống khi chẩn đoán packet capture không thấy certificate.

### Chống replay là việc cả TLS deployment và ứng dụng phải quan tâm

Một POST `/transfer-money` gửi như 0-RTT có thể mang side effects nguy hiểm nếu bị phát lại. Ngay cả khi bản ghi được mã hóa, **mã hóa không tự chứng minh một yêu cầu là duy nhất**. Triển khai cần chính sách vô hiệu 0-RTT cho mutation nhạy cảm hoặc anti-replay/idempotency đáng tin cậy, bao gồm xử lý nhiều instance và retry.

## 16. Thiết kế triển khai thực tế: kiểm soát lớp nào?

| Lớp | Câu hỏi phải trả lời | Kiểm soát khuyến nghị |
| --- | --- | --- |
| **Key generation/certificate lifecycle** | Private key certificate được tạo/lưu/rotate ở đâu? | PKI phù hợp, HSM/KMS khi cần, ownership, expiration alerts, kiểm tra chain. |
| **Trust anchors** | CA nào được phép xác thực server/client? | Truststore được phân phối qua kênh tin cậy, hạn chế custom roots. |
| **Endpoint identity** | Client dự kiến gặp hostname/service nào? | HTTPS endpoint identification, SAN match, không trust-all. |
| **Key agreement** | Group/size/version được phép là gì? | TLS 1.3, JDK/provider được hỗ trợ, chính sách disabled algorithms. |
| **Signature schemes** | Bên dùng cert có thể chứng thực bằng thuật toán được phép không? | RSA-PSS/ECDSA/EdDSA theo certificate/provider/security policy. |
| **Key schedule/records** | Ai xử lý HKDF, nonce, AEAD tag, replay record? | Dùng JSSE/TLS library đáng tin, không tự tái tạo TLS primitive. |
| **Application authentication** | Client/user nào có quyền sử dụng tài nguyên? | Token/mTLS identity mapping, authorization, tenant checks. |
| **Resumption/0-RTT** | Có side effects không? | Quản lý tickets/PSK, anti-replay, hạn chế 0-RTT theo nghiệp vụ. |
| **Telemetry** | Có xác minh TLS đang dùng gì mà không lộ secret không? | Ghi protocol, cipher suite, certificate/key ID được phép; không log raw secrets. |
| **Incident response** | Khi private key/server cert bị lộ hoặc CA bị distrust thì sao? | Revoke/rotate, cập nhật trust material, monitor, kiểm tra exposure. |

Trong Java microservice, thiết kế bảo mật tốt là dùng **HTTP client/server framework đã cấu hình TLS** thay vì để mỗi team viết cách tính X25519/HKDF/GCM riêng. Chỉ khi xây dựng thư viện mật mã nền tảng mới cần tiếp cận wire protocol cực sâu; ngay cả khi đó vẫn nên dựa trên triển khai được kiểm toán.

## 17. Những hiểu lầm phổ biến

| Hiểu lầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “TLS dùng RSA để mã hóa tất cả dữ liệu HTTPS.” | TLS 1.3 dùng **AEAD symmetric keys** cho records, không dùng RSA encrypt payload. | Certificate RSA có thể ký handshake; X25519/ECDHE thỏa thuận secret; AES-GCM bảo vệ data. |
| “ECDHE tự xác thực server.” | Attacker có thể thỏa thuận DH riêng với từng phía. | Cần certificate/trust, CertificateVerify và Finished. |
| “Đã có X.509 certificate là server đáng tin.” | Certificate parse được vẫn có thể self-signed/unknown CA/hostname mismatch. | Kiểm tra chain, trusted root, SAN, EKU/constraints. |
| “Public key của certificate chính là key_share.” | Identity key và ephemeral agreement key có công dụng khác nhau. | Phân biệt private key ký lâu dài, ephemeral key exchange và traffic key. |
| “CertificateVerify và Finished đều là chữ ký RSA.” | Finished là MAC dựa trên key schedule, không phải chữ ký bất đối xứng. | CertificateVerify ký transcript, Finished xác nhận transcript/keys. |
| “SHA256 trong `TLS_AES_128_GCM_SHA256` nghĩa là server dùng SHA256withRSA.” | SHA256 ở đây là hash cho HKDF/transcript. | Authentication signature được thương lượng riêng. |
| “Mỗi TLS record được ký bằng private key certificate.” | Record layer dùng AEAD symmetric key và tag. | Chữ ký handshake tạo xác thực ban đầu, AEAD xử lý dữ liệu phiên. |
| “TLS mã hóa nên có thể tắt hostname verification.” | Không còn chắc chắn server đúng danh tính, dễ bị MITM. | Bật endpoint identification và trust đúng. |
| “Self-signed certificate không bao giờ dùng được.” | Nó có thể dùng trong lab hoặc pinning/trust model có kiểm soát. | Chỉ tin thông qua kênh cấu hình đáng tin, không bỏ kiểm tra danh tính. |
| “`SSLContext` nghĩa là SSLv3.” | Tên lớp mang tính lịch sử. | Chọn TLS 1.3 qua provider và enabled protocols. |
| “TLS 1.3 không cần chứng thư ở mọi trường hợp.” | Phát biểu thiếu ngữ cảnh, PSK handshake có thể không gửi cert. | Certificate-based full handshake có cert; PSK/resumption có quy tắc riêng. |
| “Cứ `verify()` một chữ ký bất kỳ là đủ chống MITM.” | Phải xác minh đúng transcript, public key đã được trust, identity và Finished. | Dùng JSSE thực hiện protocol, không tự nối các JCA calls. |
| “TLS 1.3 cipher suite định nghĩa luôn X25519 và RSA.” | Suite TLS 1.3 chỉ mô tả AEAD + hash. | Group key_share và signature schemes được thương lượng riêng. |
| “AES-GCM tự chống mọi replay HTTP.” | AEAD record integrity khác anti-replay nghiệp vụ/0-RTT. | Thêm cơ chế idempotency, request nonce và anti-replay khi cần. |
| “Socket handshake xong thì mọi lệnh đều được phép.” | TLS xác thực endpoint chưa xác thực quyền người dùng/endpoint authorization. | Thực hiện kiểm tra authorization độc lập. |

## 18. Tình huống tự kiểm tra

**Câu 1.** Một server dùng certificate RSA-2048 nhưng phiên thương lượng `TLS_AES_128_GCM_SHA256` và `X25519`. Khóa RSA đang mã hóa dữ liệu ứng dụng hay không?

**Đáp án:** Không. Trong TLS 1.3 certificate-based handshake, khóa RSA có thể dùng chữ ký chứng thực, X25519 dùng trao đổi secret tạm thời, còn AES-128-GCM dùng traffic keys đối xứng cho records.

**Câu 2.** Client và server tự xây ECDHE riêng và tính cùng shared secret. Đã ngăn MITM chưa?

**Đáp án:** Chưa. Chưa có bằng chứng identity hay ràng buộc transcript vào public key đáng tin. Cần toàn bộ handshake TLS xác thực.

**Câu 3.** `CertificateFactory` đọc thành công certificate PEM của server, và `cert.checkValidity()` không báo lỗi. Có thể bỏ `TrustManagerFactory` và hostname check không?

**Đáp án:** Không. Parse và validity chỉ là điều kiện cục bộ; cần chain/trust, issuer/signature, usage và SAN/expected hostname.

**Câu 4.** Vì sao TLS 1.3 cần cả `CertificateVerify` và `Finished`?

**Đáp án:** CertificateVerify chứng minh private key tương ứng danh tính đã được chứng nhận ký handshake context; Finished là MAC dựa trên traffic secret để xác nhận key/transcript integrity. Chúng bảo vệ các thuộc tính khác nhau.

**Câu 5.** Một record bị đổi một byte; AES-GCM vẫn giải mã được plaintext rồi app mới báo lỗi có đúng không?

**Đáp án:** Không được chấp nhận plaintext chưa xác thực. AEAD tag phải được kiểm tra theo TLS; bản ghi hỏng bị từ chối, thường làm kết nối thất bại.

**Câu 6.** Cipher suite `TLS_AES_256_GCM_SHA384` có bắt buộc certificate RSA-4096 hay group P-384 không?

**Đáp án:** Không. Suite quy định AEAD và HKDF/transcript hash; certificate signature scheme và key agreement group được thương lượng theo cơ chế riêng.

**Câu 7.** Trong demo Java, vì sao client có `trust.p12` riêng nhưng vẫn cần `setEndpointIdentificationAlgorithm("HTTPS")`?

**Đáp án:** Truststore quyết định public key/CA nào có thể tin; hostname check bảo đảm certificate thực sự dành cho endpoint đang kết nối. Hai kiểm tra bổ sung nhau.

**Câu 8.** Khi private key certificate dài hạn bị lộ sau khi một phiên ECDHE đã kết thúc, có chắc attacker giải mã được packet capture cũ không?

**Đáp án:** Không tự động. ECDHE với ephemeral key/traffic secret được bảo vệ và xóa đúng giúp forward secrecy. Tuy nhiên nếu lộ traffic secrets/endpoint memory/log khi phiên chạy thì vẫn có nguy cơ.

**Câu 9.** Vì sao không tự lấy output `KeyAgreement.generateSecret()` làm AES key rồi gọi GCM cho socket?

**Đáp án:** TLS đòi HKDF key schedule, transcript binding, nonce/sequence, handshake authentication, Finished, record framing và policy khác. Tự ghép thiếu các thành phần này có thể làm hệ thống dễ MITM/nonce reuse/record confusion.

**Câu 10.** Trong resumption TLS 1.3 không thấy `Certificate` mới trên packet trace. Có phải MITM đã xóa chứng thư?

**Đáp án:** Chưa thể kết luận. PSK resumption có thể không gửi certificate mới; phải phân tích handshake mode, ticket/PSK binding và trust của phiên gốc.

**Câu 11.** API HTTP nhận POST 0-RTT được mã hóa hoàn toàn bằng TLS 1.3. Có thể bỏ anti-replay nghiệp vụ không?

**Đáp án:** Không. 0-RTT có replay risk; cần policy hạn chế các thao tác có side effect và idempotency/anti-replay phù hợp.

**Câu 12.** Java hiển thị `SSLSession.getCipherSuite()` là `TLS_AES_128_GCM_SHA256`. Có chắc server certificate đã được hostname check không?

**Đáp án:** Không chỉ từ cipher suite. Cần xác minh trust manager và endpoint identification đã được bật/thi hành cho kết nối theo policy; cipher suite chỉ mô tả bảo vệ record/hash.

## 19. Checklist khi cấu hình TLS trong ứng dụng Java

- [ ] Ưu tiên **TLS 1.3** khi khả thi; chỉ hỗ trợ TLS 1.2 nếu cần tương thích và được security policy cho phép.
- [ ] Kiểm tra đúng provider/JDK hỗ trợ protocol, cipher suites, groups và signature schemes.
- [ ] Certificate server có **SAN hostname/IP**, hợp lệ thời gian, key usage/EKU và chain tới trust anchor đúng.
- [ ] **Không sử dụng trust-all** hoặc hostname verifier luôn trả true.
- [ ] Raw `SSLSocket` client có endpoint identification thích hợp; HTTP client framework không bị tùy chỉnh làm mất hostname check.
- [ ] Truststore/keystore/private key được cấp và bảo vệ ngoài source/repo, có rotation và giám sát hết hạn.
- [ ] Phân biệt long-term identity key, ephemeral agreement key và symmetric traffic keys.
- [ ] Không tự lập trình TLS wire protocol, HKDF record keys, AES-GCM nonce hay Finished verification.
- [ ] Nếu dùng mTLS, có client certificate policy và identity-to-authorization mapping rõ ràng.
- [ ] Kiểm soát PSK tickets/resumption/0-RTT; từ chối side-effecting early data khi chưa có anti-replay phù hợp.
- [ ] Log **protocol, cipher suite, peer identity đã chuẩn hóa, error code** theo quyền, không log private key/traffic secrets/plaintext nhạy cảm.
- [ ] Có kiểm thử lỗi certificate, hostname mismatch, không chung cipher suite, disabled protocol, stale truststore và key rotation.
- [ ] Kiểm tra cả đầu ra cuối cùng của reverse proxy/load balancer: TLS có thể terminate ở proxy, kết nối proxy -> backend cần bảo vệ riêng theo threat model.
- [ ] Sau TLS, ứng dụng vẫn thực hiện authentication, authorization và validation dữ liệu như bình thường.

## 20. Tài liệu chính thức

1. [RFC 9846 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc9846.html) (07/2026): đặc tả hiện hành thay thế RFC 8446; handshake, key agreement, `CertificateVerify`, `Finished`, HKDF/traffic key schedule và AEAD records.
2. [RFC 8446 — TLS 1.3 (2018)](https://www.rfc-editor.org/rfc/rfc8446.html): tài liệu lịch sử vẫn thường được viện dẫn trong JDK/docs; đã được RFC 9846 thay thế.
3. [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525.html): xác định/xác minh danh tính server/service trong TLS.
4. [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869.html): cơ sở HKDF-Extract và HKDF-Expand.
5. [Oracle Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): `SSLSocket`, `SSLEngine`, trust, hostname verification, TLS 1.3 và các lưu ý triển khai.
6. [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): TLS engine và cách cấu hình key/trust managers.
7. [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): enabled protocols, cipher suites, endpoint identification.
8. [Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): TLS over TCP sockets, `startHandshake` và streams.
9. [Java SE 17 — SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): xem protocol, cipher suite và peer certificates.
10. [Java SE 17 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html) và [KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): cơ chế cung cấp trust và identity key material cho JSSE.
11. [Java SE 17 — KeyAgreement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): API minh họa X25519, **không thay thế TLS**.
12. [Oracle keytool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): tạo cặp khóa test, xuất/import public certificate và quản lý keystore.
