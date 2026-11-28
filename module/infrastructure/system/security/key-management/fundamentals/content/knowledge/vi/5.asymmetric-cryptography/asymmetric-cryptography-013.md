# Public key distribution

> **Chương:** Mật mã bất đối xứng  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Public key distribution là gì?

**Public key distribution (phân phối khóa công khai)** là quá trình đưa **public key** của một chủ thể đến đúng bên cần sử dụng, đồng thời cung cấp căn cứ đáng tin cậy để bên nhận xác định **khóa đó thực sự thuộc về chủ thể được tuyên bố**. Chủ thể có thể là người dùng, máy chủ HTTPS, dịch vụ nội bộ, thiết bị IoT hoặc tổ chức ký tài liệu.

Mật mã bất đối xứng sử dụng **cặp khóa công khai và khóa riêng (public/private key)**. Public key có thể được công bố rộng rãi, còn private key phải được bảo vệ nghiêm ngặt. Tuy nhiên, **không cần giữ bí mật public key không có nghĩa có thể tin mọi public key nhận được qua mạng**.

Giả sử Alice muốn gửi thông tin mật cho Bob. Nếu Alice tải một public key được ghi là "của Bob" từ nguồn không đáng tin rồi mã hóa dữ liệu, kẻ tấn công có thể đã thay khóa đó bằng public key của chính mình. Alice sẽ tạo bản mã hợp lệ nhưng **mã hóa cho sai người**. Tương tự, khi kiểm tra chữ ký số, nếu ứng dụng tùy ý chấp nhận public key do người gửi thông điệp cung cấp, kẻ tấn công có thể tạo cặp khóa riêng và chữ ký của mình rồi giả mạo danh tính người khác.

Vì vậy, mục tiêu thiết kế gồm hai việc **khác nhau**:

1. **Phân phối giá trị khóa:** bên nhận lấy được đúng dữ liệu public key và những tham số thuật toán liên quan.
2. **Xác thực ràng buộc danh tính–khóa (key-to-identity binding):** bên nhận có bằng chứng để tin public key đó thuộc về chủ thể cần liên lạc, phù hợp mục đích và chính sách sử dụng khóa.

Một đường truyền mã hóa bằng TLS giúp bảo vệ việc tải public key **từ endpoint đã được xác thực**. Nó không tự chứng minh rằng nội dung khóa được endpoint đó công bố thực sự thuộc về một người dùng, tenant hoặc dịch vụ khác. Cần xác định ranh giới trách nhiệm của **nguồn phát hành khóa**.

## 2. Phân biệt công khai, xác thực và ủy quyền

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Confidentiality (bí mật)** | Có phải giấu byte public key không? | Thường **không**; public key được thiết kế để chia sẻ |
| **Integrity (toàn vẹn)** | Khóa có bị sửa trên đường nhận không? | Kiểm tra chữ ký trên chứng thư, sử dụng HTTPS xác thực |
| **Authenticity (xác thực nguồn gốc)** | Khóa có thực sự thuộc về đúng chủ thể không? | Kiểm tra chứng thư TLS có hostname phù hợp |
| **Authorization (ủy quyền)** | Chủ thể sử dụng khóa có được phép thực hiện nghiệp vụ này không? | Chữ ký hợp lệ nhưng người ký vẫn không được phép duyệt khoản chi |
| **Freshness (tính hiện hành)** | Đây có phải khóa đã bị thay, thu hồi hoặc không còn dùng cho mục đích này không? | JWKS được cập nhật sau rotation; chứng thư bị thu hồi |
| **Availability (sẵn sàng)** | Hệ thống lấy đúng khóa khi cần, kể cả khi có sự cố không? | Cache có kiểm soát và cơ chế chuyển đổi key version |

**Một chữ ký kiểm tra thành công chỉ chứng minh tính hợp lệ đối với public key đã dùng để kiểm tra**. Để kết luận "Bob ký", hệ thống còn phải xác thực ràng buộc public key với Bob và xét quyền nghiệp vụ của Bob.

### Public key, fingerprint, certificate và key ID

| Thành phần | Ý nghĩa | Điều không được suy luận |
| --- | --- | --- |
| **Public key** | Vật liệu mật mã để xác minh chữ ký, mã hóa cho bên nhận hoặc thực hiện tác vụ bất đối xứng | Không tự chứa bằng chứng danh tính đáng tin |
| **Key fingerprint** | Giá trị băm của một biểu diễn khóa xác định (thường SHA-256 của SPKI) | Fingerprint do **cùng nguồn không tin cậy** cung cấp không làm khóa trở nên đáng tin |
| **X.509 certificate** | Tài liệu ký số liên kết public key với định danh/thông tin thuộc tính và thời hạn | Không được tin chỉ vì file có định dạng X.509 |
| **Trust anchor** | Điểm tin cậy được cài sẵn/cấp phát an toàn, ví dụ CA gốc hoặc khóa được pin | Không thể lấy trust anchor tùy ý từ đối tượng đang cần xác minh |
| **Key ID / version / `kid`** | Nhãn giúp chọn khóa trong tập khóa | Nhãn do bên ngoài đưa vào **không** phải chứng cứ xác thực khóa |

Khi tạo fingerprint, phải thống nhất **đối tượng được băm và định dạng chuẩn hóa**. SHA-256 trên toàn bộ chứng thư DER sẽ khác SHA-256 trên **SubjectPublicKeyInfo (SPKI)** của public key trong cùng chứng thư. Hai kiểu pin có hành vi khác nhau khi chứng thư được phát hành lại nhưng giữ nguyên cặp khóa.

## 3. Mối đe dọa chính: thay thế public key

Một kẻ tấn công đứng giữa (man-in-the-middle, MITM) có thể chặn hoặc sửa kênh phân phối khóa nếu kênh chưa được bảo vệ hoặc nguồn khóa chưa được xác thực.

~~~mermaid
sequenceDiagram
    participant A as Alice
    participant M as Kẻ tấn công
    participant B as Bob
    A->>M: Yêu cầu public key của Bob
    M-->>A: Public key của M, ghi nhãn Bob
    A->>M: Mã hóa bí mật bằng public key của M
    Note over M: M giải mã bằng private key của M
    M->>B: Có thể chuyển tiếp, sửa hoặc chặn dữ liệu
~~~

Nếu không có bước kiểm tra ràng buộc giữa Bob và public key, phép mã hóa RSA-OAEP hoặc một cơ chế mã hóa bất đối xứng mạnh **vẫn có thể hoạt động đúng về mặt toán học nhưng bảo vệ sai người nhận**.

Trong trường hợp chữ ký số, kịch bản tương tự là kẻ tấn công phát tán một public key của mình và tự xưng thuộc tổ chức hợp lệ. Người kiểm tra nhận thấy chữ ký "valid" dưới khóa giả, rồi nhầm đó là chữ ký của tổ chức. **Vấn đề nằm ở việc phân phối và tin cậy public key**, không nhất thiết ở thuật toán RSA-PSS, ECDSA hay Ed25519.

Các rủi ro liên quan gồm:

- **Key substitution:** thay public key thật bằng khóa giả.
- **Stale key:** ứng dụng dùng một khóa đã ngừng tin cậy, bị thu hồi hoặc quá hạn chính sách.
- **Key confusion:** dùng nhầm khóa của môi trường, tenant, mục đích hoặc thuật toán khác.
- **Unauthorized enrollment:** kẻ tấn công đăng ký khóa mới vào tài khoản/danh tính người khác.
- **Trust-store compromise:** chèn một CA hoặc public key giả vào danh sách nguồn tin cậy.
- **Rollback:** buộc ứng dụng quay lại danh sách khóa hoặc chính sách tin cậy cũ.

Mỗi cơ chế phân phối cần xác định cách chống những rủi ro đó và cách xử lý khi một bằng chứng tin cậy không còn hợp lệ.

## 4. Các mô hình phân phối public key phổ biến

| Mô hình | Cách xác thực nguồn gốc | Phù hợp khi | Điểm cần chú ý |
| --- | --- | --- | --- |
| **PKI / chứng thư X.509** | CA ký chứng thư; bên nhận kiểm tra đường dẫn tin cậy và danh tính | HTTPS, mTLS, danh tính máy chủ/dịch vụ | Trust anchor, SAN, thời hạn, key usage, thu hồi |
| **Fingerprint xác nhận ngoài băng** | So sánh fingerprint qua kênh độc lập đáng tin cậy | Trao đổi khóa trực tiếp, hệ thống nhỏ, onboarding thiết bị | Kênh xác nhận phải thực sự độc lập và tin cậy |
| **Key pinning** | Ứng dụng lưu public key/SPKI được phép trước đó | Một số ứng dụng/thiết bị kiểm soát môi trường triển khai | Rotation và khôi phục nếu pin mất hiệu lực |
| **TOFU (Trust On First Use)** | Ghi nhận khóa lần đầu, cảnh báo nếu khóa thay đổi | Host key SSH trong một số quy trình | Lần kết nối đầu tiên vẫn có rủi ro MITM |
| **JWKS / key directory** | Lấy tập public key từ endpoint đã xác thực và được cấu hình tin cậy | Xác minh JWT/OIDC, dịch vụ ký nội bộ | Không tin URL/`kid` do token tự chỉ định; xử lý cache/rotation |
| **Signed key directory / key transparency** | Danh sách khóa và thay đổi được ký hoặc ghi vào nhật ký có thể kiểm tra | Nền tảng nhắn tin, hệ sinh thái nhiều danh tính | Chính sách phát hiện thay khóa, giám sát và truy vết |
| **DNSSEC/DANE (khi triển khai đúng)** | DNSSEC tạo chuỗi xác thực cho dữ liệu DNS/TLSA | Môi trường có hạ tầng và client hỗ trợ | Không coi DNS không có DNSSEC là nguồn khóa đã xác thực |

**Không có một cách phân phối phù hợp cho mọi hệ thống.** Chọn mô hình theo số lượng chủ thể, mức độ tự động hóa, yêu cầu thu hồi, năng lực client và ranh giới tin cậy.

## 5. PKI và chứng thư X.509: mô hình phổ biến cho máy chủ

Với PKI (Public Key Infrastructure), **Certificate Authority (CA)** phát hành chứng thư X.509 để xác nhận mối liên kết giữa public key và danh tính/thuộc tính. Client có sẵn tập **trust anchor** (ví dụ CA gốc được hệ điều hành/JDK tin cậy), nhờ đó có thể xác minh một chuỗi chứng thư từ máy chủ đến CA đáng tin.

~~~mermaid
flowchart TD
    Root[CA gốc trong trust store] -->|Xác minh chữ ký chứng thư| Intermediate[CA trung gian]
    Intermediate -->|Xác minh chữ ký chứng thư| Leaf[Chứng thư của dịch vụ]
    Leaf --> Pub[Public key của dịch vụ]
    Leaf --> SAN[Định danh DNS trong Subject Alternative Name]
    Policy[Thời hạn, key usage, EKU, thuật toán, thu hồi] --> Decision{Có tin cậy không?}
    Pub --> Decision
    SAN --> Decision
    Root --> Decision
    Decision -->|Đạt| Accept[Chấp nhận public key cho mục đích phù hợp]
    Decision -->|Không đạt| Reject[Từ chối kết nối / xác minh]
~~~

### 5.1. Những kiểm tra quan trọng

Client HTTPS/mTLS phù hợp cần xử lý theo chính sách:

1. **Đường dẫn chứng thư (certificate path):** chữ ký các chứng thư trong chuỗi hợp lệ, dẫn tới một trust anchor được phê duyệt.
2. **Danh tính đúng:** hostname truy cập khớp với DNS name thích hợp trong **Subject Alternative Name (SAN)**; không chỉ kiểm tra public key hay tên hiển thị trong chứng thư.
3. **Thời hạn và thuật toán:** chứng thư có hiệu lực, thuật toán/chính sách khóa đáp ứng yêu cầu.
4. **Mục đích sử dụng:** key usage và Extended Key Usage (EKU) phù hợp, chẳng hạn xác thực máy chủ hoặc client.
5. **Trạng thái thu hồi khi áp dụng:** CRL, OCSP, OCSP stapling hoặc cơ chế của hệ sinh thái được sử dụng theo cấu hình/chính sách.
6. **Chính sách ứng dụng:** danh tính đã xác thực có được phép truy cập đúng dịch vụ/tài nguyên không?

**Chữ ký trên chứng thư chỉ có ý nghĩa nếu đường dẫn tin cậy được kiểm tra đúng.** Có thể tạo chứng thư tự ký bằng bất kỳ cặp khóa nào; việc chứng thư "tự xác minh chữ ký của nó" không biến chủ thể thành đáng tin.

### 5.2. Vai trò của Certificate Transparency (CT)

**Certificate Transparency** là cơ chế ghi nhận và giám sát chứng thư trong các nhật ký có thể kiểm tra, hữu ích để phát hiện chứng thư TLS công khai được cấp sai hoặc bất thường. CT **bổ sung khả năng quan sát**, không thay thế việc client kiểm tra trust chain, hostname, thời hạn và chính sách tin cậy. Mức độ bắt buộc CT phụ thuộc hệ sinh thái client/chứng thư.

### 5.3. Cần tách khóa xác thực khỏi khóa phiên

Trong TLS 1.3, public key trong chứng thư máy chủ thường được dùng để **xác thực chữ ký của máy chủ trong handshake**. Các **traffic key đối xứng** bảo vệ dữ liệu kết nối được dẫn xuất từ key schedule, thường có đóng góp của (EC)DHE tạm thời. Không được kết luận rằng "HTTPS dùng RSA public key để mã hóa tất cả nội dung HTTP".

**Phân phối public key** xác định máy chủ nào đang được tin cậy; **thiết lập khóa phiên** tạo khóa bảo vệ lưu lượng; **ủy quyền ứng dụng** quyết định người dùng hoặc service có được truy cập dữ liệu không. Ba lớp phải cùng đúng.

## 6. Phân phối qua fingerprint, pinning và TOFU

### 6.1. Fingerprint qua kênh ngoài băng

Trong mạng nhỏ hoặc onboarding thiết bị, hai bên có thể trao đổi public key qua mạng thông thường rồi **so sánh fingerprint SHA-256 qua một kênh đáng tin độc lập**: ví dụ quy trình cấu hình tại chỗ, mã QR đã được xác thực nguồn gốc hoặc một kênh quản trị được bảo vệ.

~~~text
Bên A nhận public key K từ kênh phân phối.
Tính f = SHA-256(SPKI(K)).
So sánh f với fingerprint đã nhận qua kênh tin cậy độc lập.
Chỉ chấp nhận K khi hai giá trị khớp và đúng danh tính/mục đích.
~~~

Nếu website không đáng tin vừa đăng public key vừa đăng fingerprint kèm theo, so sánh hai giá trị trên website đó **không chứng minh được điều gì về nguồn gốc**: kẻ tấn công có thể sửa cả hai.

### 6.2. Key pinning

**Pinning** nghĩa là phần mềm có một hoặc nhiều giá trị public key/SPKI được phê duyệt trước, và từ chối kết nối hoặc khóa không khớp. Pinning có thể hợp lý trong hệ thống mà tổ chức kiểm soát việc phân phối cấu hình và có kế hoạch chuyển đổi.

Rủi ro vận hành lớn nhất là **rotation**: nếu server thay khóa nhưng client chưa nhận pin mới theo kênh tin cậy, kết nối có thể bị chặn hàng loạt. Cần quy trình cập nhật pin, khoảng chồng lấn, recovery và kiểm thử. Pinning tự triển khai cho ứng dụng đại trà dễ tạo sự cố nếu không có khả năng cập nhật tin cậy; với HTTPS thông thường, **kiểm tra PKI/hostname chuẩn của nền tảng thường là điểm khởi đầu phù hợp**.

### 6.3. TOFU trong SSH

Khi SSH client kết nối tới máy chủ lần đầu, nó có thể ghi nhớ **host public key** vào `known_hosts`. Lần sau, nếu host key đổi, client cảnh báo. Đây là **Trust On First Use**:

- Giúp phát hiện **thay khóa bất thường sau lần tin cậy đầu**.
- Không bảo vệ hoàn toàn khỏi MITM **ngay lần kết nối đầu tiên**.
- Cần xác nhận fingerprint ngoài băng hoặc triển khai **SSH host certificates** với CA được tin cậy khi yêu cầu an toàn cao.

Không xóa cảnh báo host key mismatch một cách tự động chỉ để kết nối tiếp tục. Có thể là rotation hợp lệ, nhưng cũng có thể là máy chủ giả mạo.

## 7. JWKS, JWT và public key của dịch vụ ký

Các hệ thống OAuth 2.0/OIDC hoặc dịch vụ ký JWT thường công bố tập public key dưới dạng **JSON Web Key Set (JWKS)** để bên nhận xác minh chữ ký token. Một public JWK có thể chứa các trường như `kty`, `kid`, `use`, `alg` và các tham số khóa; ví dụ các tham số public RSA là `n` và `e`.

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "issuer-signing-v3",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là **minh họa định dạng**, không phải public key có thể sử dụng. Các thuật toán JWT có cách xác minh riêng (ví dụ RS256 dùng RSASSA-PKCS1-v1_5 với SHA-256; PS256 dùng RSA-PSS với SHA-256), nên không được tự thay thế tùy ý.

### Trình tự xác minh đáng tin cậy

1. **Cấu hình trước issuer và địa chỉ JWKS được phép:** lấy metadata qua kênh HTTPS đã xác thực, từ issuer được phê duyệt.
2. **Lấy và cache JWKS:** tôn trọng chính sách cache, giới hạn kích thước/độ trễ, làm mới khi rotation theo quy trình.
3. **Đọc `kid` như bộ chọn:** chỉ tra trong **tập khóa của issuer đã tin cậy**, không dùng `kid` hoặc `jku` từ token làm URL bất kỳ để tải khóa.
4. **Cố định thuật toán được phép:** kiểm tra loại khóa, `alg`, mục đích `use`/`key_ops` phù hợp; chống **algorithm confusion**, không chấp nhận `alg=none` khi yêu cầu chữ ký.
5. **Xác minh chữ ký và claims:** kiểm tra `iss`, `aud`, `exp`, `nbf` và các claim ứng dụng liên quan theo chính sách; xác minh chữ ký hợp lệ không tự cấp mọi quyền.

**Không chấp nhận public key do token không tin cậy tự nhúng vào** để kiểm tra chính chữ ký của token. Nếu một token có thể tùy ý chỉ đến nguồn khóa của kẻ tấn công, hệ thống đã đánh mất ranh giới tin cậy của issuer.

### Rotation JWKS

Thông thường issuer có thể công bố **khóa mới trước khi bắt đầu ký bằng khóa đó**, để verifier tải và cache; tiếp theo issuer chuyển sang ký bằng khóa mới, rồi giữ public key cũ đủ lâu cho token hợp lệ còn tồn tại. Khi khóa bị lộ, chính sách thu hồi có thể đòi hỏi rút ngắn cửa sổ chấp nhận và vô hiệu hóa token liên quan.

Không được bỏ qua lỗi xác thực JWT chỉ vì `kid` chưa có trong cache; hệ thống nên refresh từ **nguồn JWKS được tin cậy** theo chính sách, rồi từ chối nếu vẫn không tìm thấy khóa hợp lệ. Cache và JWKS endpoint phải tránh tạo tình trạng truy vấn không giới hạn khi attacker gửi nhiều `kid` giả.

## 8. Quy trình phân phối khóa công khai giữa các dịch vụ

Ví dụ, dịch vụ **Billing** ký hóa đơn bằng private key và dịch vụ **Archive** cần public key để xác minh. Trong cùng doanh nghiệp, có thể thiết kế một **key registry** hoặc PKI nội bộ.

~~~mermaid
sequenceDiagram
    participant Admin as Nhóm quản lý khóa
    participant KMS as KMS/HSM
    participant Registry as Key registry đã xác thực
    participant Billing as Billing
    participant Archive as Archive
    Admin->>KMS: Sinh/cấp phát cặp khóa ký
    KMS-->>Admin: Key ID + public key/chứng thư
    Admin->>Registry: Công bố binding service + key + version
    Billing->>KMS: Sign(document) theo quyền
    KMS-->>Billing: Signature + key ID
    Billing->>Archive: Document + signature + key ID
    Archive->>Registry: Lấy public key theo issuer/key ID qua kênh tin cậy
    Registry-->>Archive: Public key và metadata
    Archive->>Archive: Xác minh binding, thuật toán, chính sách, chữ ký
~~~

**Key ID không đủ để tin khóa.** Registry phải xác thực người/cơ chế đăng ký khóa, phân quyền publish/revoke và chứng minh nguồn gốc bản ghi. Archive phải chỉ lấy khóa từ registry đã được phê duyệt và bảo đảm danh tính dịch vụ ký được đối chiếu với dữ liệu cần xác minh.

### Những metadata nên quản lý

| Trường | Ý nghĩa |
| --- | --- |
| `owner` / `subject` | Danh tính người, máy chủ, workload hoặc tenant sở hữu khóa |
| `keyId` / `version` | Định danh và phiên bản; không phải nguồn tin cậy tự thân |
| `algorithm` / `parameters` | RSA-PSS, ECDSA, Ed25519, RSA-OAEP… và tham số bắt buộc |
| `purpose` | `SIGN`, `VERIFY`, `ENCRYPT`, `KEY_AGREEMENT`... |
| `publicKey` / `certificateChain` | Vật liệu công khai theo định dạng thống nhất |
| `fingerprint` | Giá trị đối chiếu theo hàm băm và định dạng đã quy định |
| `issuedAt`, `notBefore`, `notAfter` | Mốc phát hành và giới hạn sử dụng theo chính sách |
| `status` / `revocationReason` | Active, retired, revoked hoặc trạng thái tương đương |
| `issuer` / `trustPolicy` | Nguồn phát hành và cơ chế xác thực binding |
| `auditMetadata` | Danh tính công bố, phê duyệt, lịch thay đổi và request ID |

Một registry an toàn cần kiểm soát cập nhật chống sửa trái phép, chặn đăng ký khóa cho chủ thể không sở hữu và lưu lịch sử phục vụ kiểm toán. Không nhất thiết phải giữ private key trong registry: **private key nên nằm ở KMS/HSM/keystore được bảo vệ**, còn registry phân phối public key và metadata.

## 9. Ví dụ Java 17: kiểm tra public key máy chủ và SPKI fingerprint

Ví dụ sau dùng **`HttpClient` của Java 17** kết nối HTTPS với cấu hình xác thực TLS mặc định của JDK. Sau khi handshake thành công, nó đọc **public key trong leaf certificate**, tính SHA-256 trên biểu diễn SPKI và so sánh với fingerprint được cấp **từ một kênh onboarding độc lập đáng tin**.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.MessageDigest;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.HexFormat;
import javax.net.ssl.SSLSession;

public class PublicKeyDistributionDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Provide a pre-approved SHA-256 SPKI fingerprint in hex");
        }

        // Fingerprint phải đến từ kênh đáng tin, không sao chép
        // trực tiếp từ trang vừa được kiểm tra.
        byte[] expectedSpkiHash = HexFormat.of().parseHex(
                args[0].replace(":", ""));
        if (expectedSpkiHash.length != 32) {
            throw new IllegalArgumentException("SHA-256 must be 32 bytes");
        }

        HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .GET()
                .build();

        // TLS mặc định của JDK xác minh trust chain/hostname
        // theo chính sách và trust store của runtime.
        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());
        SSLSession tls = response.sslSession()
                .orElseThrow(() ->
                    new IllegalStateException("Missing TLS session"));

        Certificate[] peerChain = tls.getPeerCertificates();
        X509Certificate leaf = (X509Certificate) peerChain[0];
        byte[] spki = leaf.getPublicKey().getEncoded();
        byte[] actualSpkiHash = MessageDigest.getInstance("SHA-256")
                .digest(spki);

        if (!MessageDigest.isEqual(expectedSpkiHash, actualSpkiHash)) {
            throw new SecurityException("Untrusted public key: pin mismatch");
        }
        System.out.println("TLS and pre-approved public key matched");
    }
}
~~~

Code này minh họa **phân phối public key dùng xác thực TLS và pin được phê duyệt**; nó không phải một bộ kiểm tra PKI tùy chỉnh. Trong ví dụ, `example.com` là endpoint minh họa, còn fingerprint phải được cung cấp thật qua quy trình đáng tin cậy. Nếu máy chủ cấp lại chứng thư với cặp khóa mới, pin phải được cập nhật theo quy trình rotation; việc mismatch phải được điều tra.

**Lưu ý quan trọng:**

1. **Không tắt hostname verification hoặc trust validation** của JDK để làm ví dụ "chạy được". Không cài `TrustManager` chấp nhận mọi chứng thư.
2. **SPKI pin khác certificate pin:** SPKI pin giữ nguyên nếu chứng thư mới chứa cùng public key; certificate fingerprint đổi khi chứng thư được cấp lại.
3. **Pin cần cơ chế thay thế an toàn.** Một pin cứng duy nhất có thể gây gián đoạn khi rotation; ứng dụng thường nên bắt đầu bằng PKI chuẩn và chỉ thêm pinning khi có yêu cầu cụ thể.
4. **TLS server public key không mặc nhiên là application signing key.** Nếu cần xác minh chữ ký hóa đơn hoặc JWT, phải tải khóa chuyên dùng qua registry/JWKS đã được xác thực và kiểm tra binding của issuer, không tự lấy public key của leaf TLS certificate để xác minh chữ ký nghiệp vụ.
5. **Không coi một HTTP response thành công là đủ quyền nghiệp vụ.** Public key đã xác thực chỉ phục vụ những mục đích được phép trong policy.
6. **Không xác thực khóa bằng fingerprint do chính kẻ gửi khóa cung cấp.** Fingerprint có ý nghĩa khi điểm tin cậy đã tồn tại độc lập.

## 10. Public key distribution trong vòng đời key management

Phân phối public key không dừng lại sau lần công bố đầu tiên. Nó liên quan trực tiếp đến **tạo khóa, cấp phát, sử dụng, xoay vòng, thu hồi, hủy và kiểm toán**.

### 10.1. Tạo và cấp phát

Hệ thống sinh cặp khóa bằng thư viện an toàn hoặc KMS/HSM thích hợp, thiết lập chủ sở hữu và mục đích. Chỉ public key và các metadata phù hợp được xuất cho bên kiểm tra hoặc bên gửi. **Private key phải được bảo vệ và cấp quyền sử dụng riêng**, không gửi kèm public key "cho tiện".

Quy trình onboarding cần xác minh **ai có quyền đăng ký một khóa cho danh tính nào**, có bước phê duyệt hay bằng chứng sở hữu khóa (proof of possession) theo yêu cầu hay không. Bằng chứng sở hữu private key có thể giúp chứng minh bên đăng ký thật sự kiểm soát cặp khóa, nhưng **không tự chứng minh danh tính** nếu chưa có quy trình xác thực chủ thể.

### 10.2. Rotation và chuyển đổi

Khi chuyển từ `key-v1` sang `key-v2`, một trình tự thường dùng:

1. Sinh cặp khóa mới trong vùng bảo vệ phù hợp và kiểm tra chính sách.
2. **Công bố public key mới qua kênh tin cậy trước** khi bắt đầu ký/mã hóa bằng khóa mới, nếu mô hình ứng dụng cho phép.
3. Cho verifier/client tiếp nhận và cache public key mới trong khoảng chồng lấn đã kiểm soát.
4. Chuyển các thao tác ký/mã hóa mới sang phiên bản mới; lưu key ID/version kèm chữ ký hoặc ciphertext.
5. Giữ public key cũ để xác minh hồ sơ lịch sử hoặc token còn hợp lệ theo chính sách; nếu là khóa giải mã, lập kế hoạch giữ **private key cũ có kiểm soát** hoặc di chuyển dữ liệu.
6. Gỡ khóa cũ khỏi tập chấp nhận **khi các phụ thuộc và chính sách cho phép**; ghi lại quyết định, thời điểm và người phê duyệt.

**Không đánh đồng "bỏ public key khỏi JWKS" với "đã hủy private key".** Đó là hai hành động khác nhau: một bên làm verifier ngừng công nhận chữ ký, bên kia liên quan tới vật liệu bí mật và khả năng ký/giải mã.

### 10.3. Thu hồi và xử lý khóa bị lộ

Nếu **private key ký số bị lộ**, mọi người có bản sao private key có thể tạo chữ ký như chủ sở hữu. Cần thu hồi hoặc cập nhật tin cậy đối với public key/chứng thư tương ứng, thay private key và điều tra chữ ký giả có thể xảy ra. Cơ chế thu hồi cụ thể phụ thuộc PKI, JWKS, SSH CA hoặc registry nội bộ; xóa một file public key tại một máy không đảm bảo mọi client đã ngừng tin.

Nếu **private key giải mã bị lộ**, kẻ tấn công có thể giải mã bản mã được tạo cho public key đó nếu có ciphertext; thay public key chỉ bảo vệ **dữ liệu mới** khỏi tiếp tục dùng khóa cũ. Phải đánh giá bản mã đã được thu thập, DEK/wrapped DEK và nhu cầu re-encrypt.

Nếu **chỉ public key bị phát tán rộng** trong khi vốn được phép công khai, đó **không phải sự cố rò rỉ private key**. Rủi ro thực sự thường nằm ở **public key bị thay hoặc được gắn sai danh tính**.

### 10.4. Cryptoperiod và xác minh lịch sử

Một cặp khóa có thể ngừng được phép **ký mới hoặc mã hóa mới**, nhưng public key vẫn cần thiết để kiểm tra chữ ký cũ; việc xác minh lịch sử còn phụ thuộc thời điểm ký, tình trạng chứng thư, bằng chứng thời gian và chính sách tin cậy. Với khóa giải mã, chỉ giữ public key **không đủ** để đọc ciphertext cũ: cần private key tương ứng hoặc đã chuyển dữ liệu sang cơ chế mới.

Vì vậy, chính sách retention phải xét riêng **thời gian bảo vệ mới**, **thời gian xử lý dữ liệu cũ** và **thời gian lưu chứng cứ về khóa/cert**.

## 11. Ví dụ thực tế: phân phối khóa ký hóa đơn điện tử

Một nền tảng hóa đơn có dịch vụ **Issuer** ký bằng RSA-PSS hoặc thuật toán chữ ký được phê duyệt; dịch vụ **Verifier** thuộc đối tác cần xác minh các hóa đơn đã nhận.

**Khi đăng ký issuer:**

- Tổ chức xác minh quyền sở hữu danh tính của issuer; private key được tạo/lưu trong KMS/HSM hoặc khu vực phù hợp.
- Public key/chứng thư được công bố vào registry đã xác thực, có issuer ID, key ID, mục đích `VERIFY`, thuật toán, thời hạn và lịch sử thay đổi.
- Verifier được cấu hình tin cậy registry/CA qua kênh độc lập; không tự tin public key đính kèm một hóa đơn nếu nguồn phát hành chưa được xác minh.

**Khi nhận hóa đơn:** verifier lấy đúng public key theo issuer và phiên bản đã được ràng buộc, kiểm tra trạng thái/chính sách phù hợp, xác minh chữ ký trên **đúng byte nội dung đã chuẩn hóa**, rồi mới xử lý quy tắc nghiệp vụ. Hóa đơn có chữ ký hợp lệ vẫn có thể bị từ chối nếu người ký không được phép phát hành loại hóa đơn đó.

**Khi rotation:** issuer công bố khóa mới sớm, dịch vụ kiểm tra cập nhật cache, hóa đơn mới dùng khóa mới, còn hồ sơ cũ có thể tiếp tục được xác minh theo chính sách lịch sử. Việc xóa khóa cũ khỏi tập phát hành mới không tự xóa nghĩa vụ kiểm tra hóa đơn đã lập.

**Khi phát hiện một private key giả mạo hoặc bị lộ:** registry thu hồi binding có vấn đề, phát thông báo đến các bên kiểm tra, lưu bằng chứng audit và đánh giá hóa đơn/chữ ký liên quan. Nếu chỉ thay đường dẫn tải public key mà không xử lý cache/trust của client, đối tác có thể tiếp tục chấp nhận khóa cũ.

Tình huống cho thấy **phân phối khóa công khai là một phần của quản lý danh tính và niềm tin**, liên kết chặt chẽ với **chữ ký số, KMS/HSM, kiểm soát truy cập, cryptoperiod, rotation và kiểm toán**.

## 12. Các lỗi triển khai thường gặp

| Sai sót | Vì sao nguy hiểm? | Cách xử lý |
| --- | --- | --- |
| Tin public key chỉ vì file tải về được | MITM có thể thay khóa trước khi mã hóa/xác minh | Xác thực nguồn gốc bằng PKI, pin hoặc kênh tin cậy khác |
| Tin fingerprint nằm cạnh public key cùng trang không đáng tin | Kẻ tấn công sửa được cả khóa và fingerprint | Đối chiếu fingerprint qua nguồn tin cậy độc lập |
| Kiểm tra chữ ký chứng thư nhưng bỏ trust chain/hostname | Có thể chấp nhận chứng thư tự ký hoặc đúng CA nhưng sai máy chủ | Dùng TLS/PKIX chuẩn, kiểm tra danh tính và policy |
| Bỏ qua cảnh báo SSH host key thay đổi | Có thể là MITM hoặc máy chủ bị thay trái phép | Xác minh thay đổi qua quy trình quản trị |
| JWT được phép tự chỉ định URL JWKS hoặc public key để xác minh | Dễ chọn khóa kẻ tấn công kiểm soát, thậm chí phát sinh SSRF | Cố định issuer/JWKS được phép, xác thực TLS và thuật toán |
| Tin `kid` là bằng chứng sở hữu khóa | Dễ dùng nhầm khóa của tenant/issuer khác | `kid` chỉ là bộ chọn trong trust domain đã xác nhận |
| Rotation khóa mà không có giai đoạn chồng lấn | Client chưa kịp lấy khóa mới, xác minh thất bại | Công bố trước, quản lý cache và thời gian chuyển đổi |
| Giữ key cũ đáng tin vô hạn | Kẻ tấn công có thêm thời gian lạm dụng khóa bị lộ | Chính sách hiệu lực/thu hồi, giới hạn retention và kiểm tra lịch sử |
| Xóa public key/chứng thư cũ trước khi lưu bằng chứng | Không thể xác minh hồ sơ lịch sử theo yêu cầu | Lưu chứng cứ tin cậy có kiểm soát và chính sách xác minh cũ |
| Coi TLS chứng minh mọi dữ liệu JWKS hợp lệ | HTTPS xác thực máy chủ, nhưng nguồn vẫn có thể publish key sai chủ thể | Kiểm soát quyền publish, audit registry, xác nhận issuer |
| Ghi public key đầy đủ vào log không kiểm soát | Không lộ bí mật khóa nhưng tăng dữ liệu, khả năng truy vết sai và làm rối vận hành | Log key ID/fingerprint cần thiết, theo chính sách dữ liệu |
| Coi người kiểm tra có public key là đã được ủy quyền nghiệp vụ | Một chữ ký hợp lệ vẫn có thể vi phạm quyền hoặc chính sách | Kiểm tra authorization độc lập |

## 13. Checklist thiết kế và vận hành

- [ ] Đã xác định **public key này thuộc về ai** và ai có quyền công bố/thay thế binding?
- [ ] Đã chọn cơ chế tin cậy rõ ràng: PKI, pin/fingerprint ngoài băng, SSH CA/TOFU hay registry/JWKS?
- [ ] Client kiểm tra **đúng danh tính, thuật toán, mục đích, thời hạn và trạng thái** khóa/chứng thư?
- [ ] Trust anchor được phân phối và cập nhật qua **kênh đã xác thực**, không nhận tùy ý từ request?
- [ ] Không tự tắt kiểm tra chứng thư, hostname, SSH host key hoặc chữ ký registry?
- [ ] Với JWT, `kid` chỉ chọn khóa trong issuer tin cậy, `alg` nằm trong allowlist, các claims được kiểm tra?
- [ ] Metadata chứa `keyId`, version, issuer/subject, algorithm, purpose, thời gian và trạng thái khi cần?
- [ ] Private key được bảo vệ riêng bằng KMS/HSM/keystore và cấp quyền `Sign`/`Decrypt` tối thiểu?
- [ ] Rotation có bước công bố khóa mới, cập nhật cache/client và duy trì khóa cũ theo cửa sổ hợp lệ?
- [ ] Có quy trình thu hồi, thông báo sự cố, xóa quyền tin cậy và xử lý cache khi private key bị lộ?
- [ ] Đã xét dữ liệu được mã hóa cho khóa cũ và các chữ ký lịch sử cần xác minh?
- [ ] Audit ghi ai đăng ký/thay/thu hồi khóa, ai sử dụng private key, khi nào và kết quả gì?
- [ ] Có kiểm thử trường hợp MITM, khóa sai hostname/tenant, cert hết hạn, `kid` không tồn tại và pin mismatch?

## 14. Câu hỏi tự kiểm tra

**1. Public key vốn công khai thì tại sao phải bảo vệ khi phân phối?**  
Vì điều cần bảo vệ là **tính toàn vẹn và nguồn gốc**. Nếu kẻ tấn công tráo khóa, dữ liệu có thể bị mã hóa cho sai người hoặc chữ ký giả bị coi là đúng.

**2. Fingerprint SHA-256 lấy trên cùng trang chứa khóa có đủ xác thực danh tính không?**  
Không. Cần fingerprint hoặc binding được đưa qua một nguồn tin cậy độc lập; nếu không, attacker có thể thay cả hai.

**3. Chứng thư X.509 tự ký có thể dùng trong hệ thống nội bộ không?**  
Có thể khi public key/trust anchor được cấp phát và pin theo quy trình đáng tin. Nhưng **tự ký** không tạo ra niềm tin tự động; client vẫn cần cấu hình trust và xác thực danh tính đúng cách.

**4. Vì sao `kid` trong JWT không đủ để quyết định khóa đáng tin?**  
Vì `kid` là nhãn có thể bị người tạo token điều khiển. Chỉ sử dụng nó để chọn khóa trong tập JWKS của issuer đã được cấu hình và xác thực.

**5. Khi dịch vụ ký thay private key, có thể xóa mọi public key cũ ngay không?**  
Không mặc nhiên. Token còn hạn và chữ ký lịch sử có thể vẫn cần khóa cũ để kiểm tra theo chính sách. Tuy nhiên, nếu khóa bị lộ, có thể phải thu hồi và xử lý ngoại lệ sớm.

**6. Nếu private key giải mã bị lộ, chỉ công bố public key mới có giải quyết dữ liệu cũ không?**  
Không. Các ciphertext/wrapped DEK cũ mà attacker đã thu thập có thể vẫn bị giải mã. Cần đánh giá phạm vi và thay khóa/mã hóa lại khi cần.

**7. TLS bảo đảm public key của bên thứ ba bên trong response luôn đáng tin chứ?**  
Không. TLS xác thực endpoint và bảo vệ đường truyền, nhưng endpoint vẫn phải được ủy quyền công bố binding của bên thứ ba và có chính sách kiểm toán phù hợp.

## Ghi nhớ

**Public key distribution là quá trình phân phối public key kèm bằng chứng đáng tin rằng khóa thuộc đúng chủ thể và được dùng đúng mục đích.** Khóa có thể công khai nhưng **binding giữa danh tính và khóa phải được xác thực**. Các cơ chế như **PKI/X.509, trust anchor, fingerprint ngoài băng, pinning, SSH TOFU/host certificates và JWKS** giải quyết nhu cầu ở những bối cảnh khác nhau. Để vận hành an toàn, phải phối hợp phân phối public key với **bảo vệ private key trong KMS/HSM**, chính sách ít quyền nhất, rotation, thu hồi, cryptoperiod, quản lý phiên bản, kiểm toán và xác minh quyền nghiệp vụ. Thuật toán RSA hay ECC mạnh không bù đắp được việc ứng dụng tin nhầm public key của kẻ tấn công.
