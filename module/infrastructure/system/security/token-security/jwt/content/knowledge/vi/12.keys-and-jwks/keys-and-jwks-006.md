# Bảo vệ khóa ký bằng kho bí mật, KMS hoặc HSM

Khóa ký JWT là tài sản bảo mật cốt lõi của bên phát hành. Nếu private key hoặc HMAC secret bị lộ, attacker có thể tạo token giả được các verifier tin cậy khóa đó chấp nhận. Vì vậy, việc lưu khóa trong file cấu hình hoặc biến môi trường thường không đủ cho hệ thống production. Cần thiết kế nơi lưu trữ, quyền sử dụng, thao tác ký, kiểm toán, sao lưu, luân chuyển và thu hồi khóa thành một quy trình thống nhất.

Bài này thuộc chương **Khóa và JWKS** của module **Security - JSON Web Token (JWT)**. Nội dung tập trung vào kho bí mật (Secrets Manager/Vault), dịch vụ quản lý khóa (KMS) và mô-đun bảo mật phần cứng (HSM), áp dụng cho hệ thống bảo mật nói chung, độc lập ngôn ngữ lập trình và framework.

## 1. Mục tiêu và ranh giới bảo vệ

Sau bài học, người đọc có thể:

1. Phân biệt vai trò của secret manager, KMS và HSM.
2. Chọn mô hình lưu và sử dụng khóa phù hợp với HMAC, RSA, EC hoặc OKP.
3. Thiết kế dịch vụ ký JWT không cần đưa private key ra khỏi KMS/HSM.
4. Giới hạn quyền ký, quản trị khóa, export, rotate và delete.
5. Xây dựng audit, backup, disaster recovery và quy trình ứng cứu khi khóa bị xâm phạm.
6. Nhận diện lỗi tích hợp JOSE như ký sai signing input, hash hai lần hoặc sai định dạng chữ ký ECDSA.

Mục tiêu bảo vệ không chỉ là **giữ byte khóa khỏi bị đọc**. Hệ thống còn phải ngăn danh tính không được phép gọi thao tác ký, ngăn thay đổi cấu hình thuật toán, phát hiện việc sử dụng bất thường và bảo đảm verifier nhận diện đúng phiên bản public key đang dùng.

## 2. Vì sao khóa ký JWT cần được bảo vệ đặc biệt?

Với JWS, issuer ký trên signing input được tạo từ protected header và payload. Bên xác minh dùng khóa tương ứng để kiểm tra chữ ký. Nếu khóa ký bị lộ:

- Attacker có thể tạo JWT với issuer, subject, audience, scope, role hoặc claims khác tùy ý.
- Token giả có thể vượt qua kiểm tra chữ ký ở mọi verifier còn tin public key/secret tương ứng.
- Nếu dùng HMAC, bất kỳ bên nào có secret để xác minh cũng có khả năng tạo MAC hợp lệ.
- Nếu private key được dùng chung cho nhiều issuer, tenant hoặc môi trường, sự cố có thể lan rộng trên toàn bộ các miền đó.
- Việc chỉ đổi mật khẩu tài khoản hoặc thu hồi một JWT cụ thể không khắc phục được private key đã bị lộ.

Mức độ ảnh hưởng phụ thuộc vào **phạm vi tin cậy của khóa**. Một khóa chỉ ký token nội bộ có audience hẹp sẽ có phạm vi ảnh hưởng khác khóa ký token dùng bởi hàng trăm API. Vì vậy, nên giới hạn khóa theo issuer, môi trường, mục đích và nhóm token phù hợp.

## 3. Phân biệt Secrets Manager/Vault, KMS và HSM

Ba khái niệm thường được dùng cùng nhau nhưng giải quyết các lớp khác nhau.

| Thành phần | Vai trò chính | Cách ứng dụng sử dụng | Giới hạn cần hiểu |
| --- | --- | --- | --- |
| **Secrets Manager / Vault** | Lưu trữ, phân phối và kiểm soát truy cập secret như API credential, mật khẩu, token, certificate hoặc đôi khi private key. | Lấy secret qua API/agent sau khi danh tính workload được xác thực; một số sản phẩm hỗ trợ ký hoặc tích hợp KMS/HSM. | Nếu ứng dụng đọc được secret dạng rõ, secret có thể xuất hiện trong bộ nhớ hoặc bị lấy khi tiến trình bị xâm nhập. Không phải mọi vault đều cung cấp thao tác ký không export. |
| **KMS (Key Management Service)** | Quản lý vòng đời và chính sách sử dụng khóa; cung cấp API mã hóa, giải mã, ký, xác minh, wrap hoặc unwrap tùy sản phẩm. | Gọi thao tác mật mã qua API bằng danh tính workload được cấp quyền. | Khả năng, loại khóa, thuật toán, export và bảo đảm phần cứng khác nhau giữa nhà cung cấp. |
| **HSM (Hardware Security Module)** | Tạo và thực hiện thao tác mật mã trong ranh giới phần cứng được bảo vệ; kiểm soát truy cập và vật liệu khóa theo thiết kế thiết bị. | Thông qua API, thư viện, giao thức hoặc KMS đứng trước HSM. | HSM không tự giải quyết issuer binding, JWT claims, quyền ứng dụng, rotation toàn hệ thống hay bảo mật dịch vụ gọi nó. |

Một KMS có thể được hỗ trợ bởi HSM ở lớp bên dưới. Vì vậy, KMS và HSM không nhất thiết là hai lựa chọn loại trừ nhau: KMS thường cung cấp giao diện quản trị/API, còn HSM cung cấp ranh giới thực thi và bảo vệ vật liệu khóa.

**Vault không đồng nghĩa HSM.** Một sản phẩm vault có thể lưu secret đã mã hóa trong database và giải mã khi cấp cho ứng dụng; một HSM có thể giữ private key không export và thực hiện ký bên trong phần cứng. Một số hệ thống kết hợp cả hai.

## 4. Chọn mô hình theo loại khóa

| Loại khóa JWT | Nhu cầu bảo vệ | Mô hình thường phù hợp |
| --- | --- | --- |
| HMAC (HS256, HS384, HS512) | Một secret dùng chung cho cả ký và xác minh. | Secrets Manager/Vault hoặc KMS hỗ trợ HMAC; giới hạn chặt số bên được cấp secret hoặc dùng API MAC trong KMS để không export. |
| RSA (RS256, PS256, ...) | Private key ký; public key phân phối để xác minh. | Asymmetric KMS key hoặc HSM non-exportable; công bố public JWK từ thành phần public. |
| EC (ES256, ES384, ES512) | Private scalar ký; public point xác minh. | KMS/HSM hỗ trợ đúng curve và thuật toán; kiểm tra định dạng chữ ký trả về. |
| OKP/EdDSA | Private key ký; public key xác minh. | KMS/HSM hoặc vault chuyên dụng có hỗ trợ chính xác curve/algorithm; không giả định mọi dịch vụ hỗ trợ Ed25519. |

Với chữ ký bất đối xứng, các verifier chỉ cần public key. Không phân phối private key cho từng API chỉ để họ xác minh JWT. Với HMAC, mọi verifier phải có secret hoặc có quyền gọi dịch vụ xác minh MAC; mỗi bên nắm secret có khả năng tạo token, vì vậy ranh giới tin cậy phải chặt hơn.

## 5. Kiến trúc khuyến nghị: ứng dụng gọi dịch vụ ký, private key không rời KMS/HSM

Một mô hình điển hình:

~~~mermaid
flowchart LR
    A["Ứng dụng phát hành token"] -->|"Yêu cầu ký / signing input"| B["JWT signing component"]
    B -->|"Workload identity + key version"| C["KMS API"]
    C --> D["HSM boundary"]
    D -->|"Signature"| C
    C --> B
    B -->|"JWT compact"| A
    E["Public JWK exporter"] -->|"Public parameters"| F["JWKS endpoint"]
    D -. "Public key / metadata" .-> E
    F --> G["JWT verifiers"]
~~~

Trong mô hình này:

- Private key được tạo hoặc nhập vào KMS/HSM theo chính sách, và có thể được đánh dấu không export.
- Ứng dụng xác thực bằng workload identity hoặc service identity; không nhúng access key tĩnh vào source code.
- Signing component dựng đúng JWS signing input và yêu cầu KMS/HSM ký bằng **phiên bản khóa cụ thể**.
- KMS/HSM trả về chữ ký; ứng dụng ghép compact JWT và đặt key ID tương ứng với đúng key version đã ký.
- Thành phần công bố JWKS chỉ xuất public parameters, không có private material.

Nếu dùng một signing service riêng, các ứng dụng nghiệp vụ có thể gửi yêu cầu phát hành token theo contract. Signing service chịu trách nhiệm kiểm tra caller, claims được phép, issuer/profile, audience, TTL và khóa active trước khi ký. Việc này giúp tập trung policy, nhưng chính signing service trở thành thành phần nhạy cảm cần bảo vệ và giám sát tương xứng.

## 6. Sinh khóa và đưa khóa vào kho

### 6.1. Ưu tiên sinh khóa bên trong KMS/HSM

Nếu nền tảng hỗ trợ, sinh private key ngay trong ranh giới bảo vệ:

1. Chọn loại khóa, kích thước/curve và thuật toán phù hợp policy.
2. Yêu cầu KMS/HSM tạo key object mới.
3. Đặt thuộc tính key usage và thuật toán được phép ngay khi tạo.
4. Gán định danh phiên bản và key ID duy nhất cho issuer.
5. Lấy public parameters để tạo JWK công khai.
6. Kiểm tra public key và thực hiện phép ký/xác minh thử trước khi kích hoạt.

Sinh khóa bên trong giúp private material không cần đi qua ứng dụng hoặc file tạm. Tuy nhiên, phải xác minh sản phẩm có thực sự tạo khóa trong HSM hay chỉ tạo ở dịch vụ rồi import vào thiết bị.

### 6.2. Import khóa có sẵn

Đôi khi phải nhập khóa từ HSM khác, hệ thống cũ hoặc quy trình migration. Khi đó:

- Chỉ dùng quy trình import được KMS/HSM hỗ trợ, với cơ chế bảo vệ khóa khi truyền như key wrapping hoặc secure key import.
- Xác minh nguồn, fingerprint/public parameters, loại khóa và quyền sở hữu trước khi import.
- Giới hạn người hoặc service được phép thực hiện import.
- Không lưu private key dạng rõ trong thư mục tạm, artifact, log hoặc clipboard.
- Kiểm tra key policy, usage và exportability sau import.
- Có kế hoạch hủy hoặc thu hồi bản khóa nguồn sau khi migration hoàn tất và đã xác minh.

Không coi Base64, PEM hoặc JSON JWK là cơ chế bảo vệ. Chúng chỉ là định dạng biểu diễn.

### 6.3. Gán định danh và metadata

Mỗi key version nên có metadata quản trị, ví dụ:

| Metadata | Ví dụ | Mục đích |
| --- | --- | --- |
| Key resource ID | kms://jwt-prod/issuer-a/signing-key/versions/7 | Tham chiếu chính xác đến key version. |
| Key ID | issuer-a-sign-2026-07 | Định danh public JWK và header JWT. |
| Issuer | https://id.example.test/issuer-a | Ràng buộc khóa với bên phát hành. |
| Algorithm | RS256 | Giới hạn thuật toán được dùng. |
| Purpose | JWT JWS signing | Tách mục đích khỏi encryption hoặc signing khác. |
| Environment | production | Không dùng lẫn khóa test/staging/prod. |
| State | staged, active, verify-only, revoked, destroyed | Theo dõi vòng đời. |
| Owner / approver | Team hoặc service owner | Trách nhiệm vận hành và phê duyệt. |

Metadata này có thể nằm trong registry quản trị; không cần nhồi tất cả vào JWK. Tránh đưa thông tin nhạy cảm vào key ID hoặc public metadata.

## 7. Lưu private key trong Vault hay dùng KMS/HSM signing API?

Hai cách có ranh giới rủi ro khác nhau.

### 7.1. Ứng dụng lấy private key từ Vault

~~~mermaid
flowchart LR
    A["Ứng dụng"] -->|"Authenticate"| V["Secrets Manager / Vault"]
    V -->|"Private key / secret bytes"| A
    A -->|"Ký trong process"| A
~~~

Ưu điểm:

- Tích hợp đơn giản với thư viện JOSE có sẵn.
- Ứng dụng có thể ký offline hoặc khi KMS không khả dụng, nếu key đã được cấp.
- Vault có thể quản lý version, lease, access policy và audit tùy sản phẩm.

Rủi ro:

- Private key/secret xuất hiện trong bộ nhớ ứng dụng.
- Process bị xâm nhập có thể đọc khóa hoặc lạm dụng khóa để ký.
- Dump bộ nhớ, crash dump, debug, log hoặc telemetry có thể vô tình chứa vật liệu bí mật.
- Thu hồi secret ở Vault không xóa ngay các bản sao đã được ứng dụng cache hoặc tải xuống.

Nếu dùng cách này, cần bảo vệ runtime, giới hạn thời gian secret tồn tại, tránh ghi dump nhạy cảm, giới hạn quyền truy cập bộ nhớ và có cơ chế rotate/revoke tất cả bản sao.

### 7.2. Ứng dụng gọi KMS/HSM để ký

~~~mermaid
flowchart LR
    A["Ứng dụng / signer"] -->|"Sign request"| K["KMS API"]
    K --> H["HSM giữ private key"]
    H -->|"Signature only"| K
    K -->|"Signature"| A
~~~

Ưu điểm:

- Private key có thể không export khỏi ranh giới KMS/HSM.
- Quyền được cấp theo key resource, version, operation, principal và policy.
- Thao tác ký có thể được audit tập trung.
- Verifier chỉ cần public JWK; không cần cấp private key cho nhiều dịch vụ.

Rủi ro và chi phí:

- Signing phụ thuộc mạng và availability của KMS/HSM.
- Có latency, quota, giới hạn kích thước dữ liệu và chi phí theo request.
- KMS có thể hỗ trợ một tập thuật toán/curve nhất định.
- Cần tích hợp đúng kiểu dữ liệu đầu vào/đầu ra của API ký.
- Một service identity bị chiếm quyền nhưng có quyền ký vẫn có thể bị lạm dụng dù private key không export được.

Với khóa ký JWT production có phạm vi ảnh hưởng lớn, mô hình KMS/HSM signing API thường giảm rủi ro lộ private material hơn việc cấp private key dạng rõ cho nhiều ứng dụng.

## 8. HSM: ranh giới phần cứng và quản trị

HSM cung cấp môi trường phần cứng chuyên dụng để sinh, lưu và thực hiện phép toán mật mã. Tùy loại thiết bị và chứng nhận, HSM có thể bảo vệ key object, kiểm soát truy cập, audit, backup và phân quyền quản trị.

### 8.1. Những gì HSM giúp bảo vệ

- Private key được sinh trong thiết bị và không export ở dạng rõ nếu key policy cấm.
- Thao tác ký được thực hiện bên trong ranh giới thiết bị.
- Quyền quản trị hoặc khôi phục có thể yêu cầu nhiều người cùng tham gia.
- Key object có thể gắn thuộc tính usage, algorithm và exportability.
- Một số HSM hỗ trợ phân vùng, cluster, replication và backup được bảo vệ.

### 8.2. Những gì HSM không tự giải quyết

- Không xác định issuer nào được ứng dụng tin.
- Không tự kiểm tra JWT issuer, audience, expiration, not-before hoặc token profile.
- Không ngăn ứng dụng được cấp quyền ký tạo claims trái chính sách.
- Không bảo vệ hoàn toàn khỏi việc service identity hợp lệ bị đánh cắp.
- Không tự triển khai JWKS rotation đồng bộ đến tất cả verifier.
- Không bảo đảm quy trình backup/restore hoặc multi-region được cấu hình đúng.

HSM là một lớp bảo vệ khóa. Quyền truy cập, quy trình vận hành, ứng dụng gọi HSM và trust policy của JWT vẫn phải được thiết kế riêng.

### 8.3. Phân quyền quản trị HSM

Với triển khai yêu cầu kiểm soát cao, tách vai trò:

- **Security/key administrator:** quản lý partition, key policy và quyền quản trị.
- **Key custodian:** tham gia quy trình tạo, khôi phục hoặc kích hoạt theo chính sách.
- **Application operator:** vận hành dịch vụ ký nhưng không có quyền thay đổi policy hoặc export key.
- **Auditor:** đọc audit records nhưng không có quyền ký hoặc quản trị khóa.

Một số hệ thống dùng cơ chế quorum hoặc M-of-N để thao tác nhạy cảm. Ví dụ, cần hai trong ba custodian cùng phê duyệt một hành động khôi phục. Số lượng và quy trình phải theo threat model; không sao chép con số mẫu thành yêu cầu chung.

## 9. Quyền truy cập: ai được ký, ai được quản trị?

Không nên cấp quyền chỉ dựa trên việc ứng dụng chạy trong cùng mạng hoặc cùng tài khoản máy chủ. Dùng danh tính workload riêng và quyền tối thiểu.

### 9.1. Phân tách các quyền

| Quyền | Đối tượng thường được cấp | Lưu ý |
| --- | --- | --- |
| sign | Signing service hoặc workload phát hành token | Chỉ trên key version và thuật toán cần thiết. |
| verify | Có thể không cần KMS nếu public key được phân phối; nếu dùng KMS thì chỉ cấp khi cần | Với asymmetric key, verifier thường dùng public JWK tại chỗ. |
| getPublicKey / export public | Thành phần tạo JWKS | Chỉ lấy public material. |
| createKey | Key administrator hoặc automation được phê duyệt | Tách khỏi quyền ký hằng ngày. |
| importKey | Quy trình migration/key custodian | Cần kiểm soát nguồn và key wrapping. |
| rotate / change alias | Quy trình quản trị khóa | Có thể ảnh hưởng token mới và key ID. |
| disable / revoke | Incident responder hoặc administrator được chỉ định | Cần quy trình khẩn cấp có audit. |
| delete / destroy | Vai trò đặc quyền, có phê duyệt | Có thể không thể khôi phục; cần xác minh retention và backup. |
| setPolicy / manage IAM | Security administrator | Không cấp cho ứng dụng phát hành token. |

### 9.2. Dùng workload identity

Signing service nên xác thực với KMS bằng danh tính workload được cấp tự động, chẳng hạn workload identity, managed identity, service account hoặc cơ chế federation tương đương. Tránh nhúng access key dài hạn trong source code hoặc file cấu hình.

Ràng buộc policy có thể bao gồm:

- Principal cụ thể được phép gọi sign.
- Chỉ resource/key version của issuer tương ứng.
- Chỉ thao tác ký, không có quyền export private material.
- Chỉ thuật toán được phê duyệt.
- Điều kiện môi trường, account/project, network hoặc attestation nếu nền tảng hỗ trợ.
- Tách quyền deploy ứng dụng khỏi quyền thay đổi key policy.

### 9.3. Phân tách nhiệm vụ và break-glass

Một người phát triển dịch vụ không nên đồng thời có quyền âm thầm tạo khóa production, cấp quyền ký cho chính mình, thay endpoint JWKS và xóa audit log. Các hành động đặc quyền nên có phê duyệt độc lập, ghi nhận đầy đủ và được rà soát định kỳ.

Break-glass là quyền khẩn cấp có giới hạn thời gian và phạm vi, dùng khi quy trình bình thường không đáp ứng sự cố. Cần xác thực mạnh, lý do, phê duyệt nếu khả thi, cảnh báo tức thời và review sau sự kiện.

## 10. Dịch vụ ký JWT và quản lý phiên bản khóa

Một signer an toàn cần gắn **key version thực sự thực hiện phép ký** với key ID đưa vào JWT header.

Quy trình khái niệm:

1. Xác định issuer và token profile từ cấu hình/caller đã xác thực.
2. Kiểm tra claims được phép, audience, TTL, scope và giới hạn nghiệp vụ.
3. Lấy key version active từ registry hoặc KMS alias theo quy trình nhất quán.
4. Dựng protected header với algorithm, type và key ID của đúng version.
5. Tạo JWS signing input theo chuẩn compact serialization.
6. Gọi KMS/HSM ký bằng **đúng key version đã chọn**.
7. Mã hóa chữ ký theo quy tắc JOSE và tạo JWT compact.
8. Ghi audit metadata không chứa token/secret nhạy cảm.

### 10.1. Tránh race condition khi alias đổi

Một alias như jwt-signing-active có thể được chuyển từ key version A sang B trong lúc nhiều request đang ký. Nếu ứng dụng lấy key ID từ alias ở một thời điểm nhưng KMS thực hiện ký bằng alias sau khi alias đổi, JWT có thể chứa key ID A nhưng chữ ký bằng B.

Giải pháp là resolve alias thành **resource ID/version bất biến** một lần cho mỗi lần ký; dùng chính version đó cho cả thao tác ký và key ID. Không tra alias hai lần ở hai thời điểm khác nhau.

### 10.2. Ví dụ contract cho signing service

Yêu cầu nội bộ minh họa:

~~~json
{
  "issuerProfile": "customer-access",
  "subject": "account-482",
  "audience": ["orders-api"],
  "scopes": ["orders.read"],
  "expiresInSeconds": 600
}
~~~

Signer không nên nhận một JWT hoàn chỉnh từ caller rồi ký mù. Nó cần tự áp dụng policy, chọn claims được phép và kiểm tra quyền của caller. Nếu cho caller gửi issuer, audience, key ID, algorithm, expiration tùy ý, dịch vụ ký có thể trở thành oracle tạo token đặc quyền.

Response nên chỉ trả JWT hoặc kết quả cần thiết. Không trả private key, key bytes hoặc quyền quản trị KMS cho caller.

## 11. Tích hợp thuật toán JOSE với API ký của KMS/HSM

Đây là nơi nhiều triển khai lỗi dù đã bảo vệ khóa tốt. API ký của KMS/HSM và JWS có thể yêu cầu biểu diễn đầu vào/đầu ra khác nhau.

### 11.1. Ký đúng JWS signing input

Với JWS compact, dữ liệu được ký là:

~~~text
BASE64URL(UTF8(protected-header))
    + "."
    + BASE64URL(payload)
~~~

Không ký riêng payload JSON, không ký chuỗi JWT đã có chữ ký, và không parse/serialize lại header/payload trước khi tạo signing input. Một byte khác cũng làm chữ ký khác.

### 11.2. API nhận message hay digest?

Một số API KMS/HSM nhận message bytes và tự băm theo thuật toán được chọn; một số API nhận digest đã tính trước; một số yêu cầu chỉ định rõ chế độ prehashed. Phải đọc contract của sản phẩm:

- Nếu API tự hash, gửi signing input gốc và chọn đúng thuật toán/hash.
- Nếu API yêu cầu digest, tính đúng digest một lần và đánh dấu đúng chế độ prehashed.
- Không gửi digest vào API lại hash lần nữa nếu mục tiêu là JWS chuẩn.
- Không chọn thuật toán chỉ từ request của caller; signer phải dùng policy.

Ví dụ RS256 là RSASSA-PKCS1-v1_5 với SHA-256. PS256 là RSA-PSS với SHA-256 và tham số PSS theo JWA, bao gồm độ dài salt tương ứng quy định. Chỉ chọn một thuật toán RSA chung chung mà không cấu hình padding/hash đúng là chưa đủ.

### 11.3. Định dạng ECDSA: DER và JOSE khác nhau

Nhiều API mật mã trả chữ ký ECDSA ở dạng ASN.1 DER gồm hai INTEGER r và s. JWS ES256/ES384/ES512 yêu cầu chữ ký dạng nối cố định độ dài:

~~~text
I2OSP(r, n) || I2OSP(s, n)
~~~

Trong đó n là độ dài octet của mỗi thành phần theo curve (ví dụ 32 byte với P-256, 48 byte với P-384, 66 byte với P-521). Nếu API trả DER, lớp tích hợp JOSE phải chuyển đổi đúng DER sang fixed-width R || S; khi xác minh cũng cần hiểu đúng định dạng mà thư viện/API mong đợi.

Không chỉ Base64url-encode chuỗi DER rồi gắn thẳng vào compact JWT. Chữ ký đó không theo định dạng ECDSA JWS chuẩn.

### 11.4. EdDSA và khả năng hỗ trợ

Không phải KMS/HSM nào cũng hỗ trợ Ed25519/EdDSA. Trước khi chọn, kiểm tra:

- Curve và thuật toán chính xác được hỗ trợ.
- API ký nhận message hay prehash; EdDSA thuần không được tùy tiện thay bằng quy trình hash trước.
- Định dạng chữ ký trả về có phù hợp JOSE không.
- Public key có thể xuất dưới dạng JWK OKP đúng curve và tham số.

Không mô phỏng EdDSA bằng một thuật toán khác hoặc chuyển đổi khóa tùy tiện chỉ để phù hợp API.

### 11.5. Dùng thư viện JOSE làm lớp chuẩn hóa

Ưu tiên thư viện JOSE/JWT đã được duy trì, có adapter/provider chính thức cho KMS/HSM nếu có. Nếu cần custom signer, giới hạn lớp đó ở việc chuyển đổi đúng message/digest/signature format; không tự hiện thực thuật toán RSA, ECDSA hoặc EdDSA.

## 12. Public JWK và JWKS từ KMS/HSM

KMS/HSM giữ private key; verifier cần public key. Thành phần công bố JWKS nên:

1. Lấy public parameters từ key version cụ thể.
2. Chuyển sang JWK đúng kiểu khóa và tham số.
3. Gán key ID trùng với version dùng để ký.
4. Công bố metadata phù hợp như use=sig và algorithm nếu policy yêu cầu.
5. Không export private members như RSA d, EC/OKP d hoặc symmetric k.
6. Công bố khóa mới trước khi signer bắt đầu dùng version mới.
7. Giữ public key cũ trong thời gian verifier còn cần xác minh token cũ.

Với RSA, public JWK thường có kiểu khóa, modulus và exponent. Với EC, có kiểu khóa, curve và tọa độ x/y. Với OKP, có kiểu khóa, curve và public key x. Không có public counterpart cho HMAC secret; không công bố JWK oct chứa secret trong JWKS công khai.

Nếu KMS alias đổi version, JWKS cần công bố public key của version mới và key ID mới. Không cập nhật alias rồi giả định verifier có thể tự suy ra public key mới.

## 13. Rotation khi dùng KMS/HSM

Rotation có thể bao gồm tạo version mới trong cùng logical key resource hoặc tạo key resource hoàn toàn mới. Cách làm tùy nền tảng; điều quan trọng là key ID và public JWK phải xác định đúng vật liệu khóa.

Quy trình tham khảo:

1. Tạo key version B với thuật toán/usage policy chính xác.
2. Lấy public parameters và tạo JWK B với key ID mới.
3. Công bố B trong JWKS cùng A.
4. Chờ các verifier làm mới JWKS; theo dõi lỗi và cache.
5. Chuyển signer sang version B; mỗi signing operation resolve version cụ thể.
6. Giữ public A ở trạng thái verify-only cho token A còn hạn.
7. Sau cửa sổ chuyển tiếp, rút A khỏi JWKS và cấm sử dụng A để ký.
8. Disable/destroy private A theo retention, backup và phê duyệt.

Mốc tham khảo để giữ khóa cũ:

~~~text
T_remove_old >= T_stop_signing_old
                 + max_token_lifetime
                 + allowed_clock_skew
                 + operational_buffer
~~~

Phải tính thêm cache, consumer offline và token profile đặc biệt. Khi khóa bị xâm phạm, thực hiện thu hồi khẩn cấp thay vì chờ hết cửa sổ rotation bình thường.

### 13.1. Rotation HMAC

Với HMAC, mọi verifier có secret đều có khả năng tạo token. Nếu dùng KMS MAC API để không export secret, verifier có thể phải gọi dịch vụ xác minh MAC hoặc dùng một kiến trúc khác; không giả định rằng public JWKS có thể giải quyết việc phân phối HMAC.

Nếu secret được cấp cho nhiều dịch vụ:

- Phân phối version mới qua secret manager có quyền riêng cho từng consumer.
- Dùng key ID mới và ánh xạ đúng version.
- Cho phép verify bằng cả A và B trong giai đoạn chuyển tiếp nếu policy cho phép.
- Ngừng cấp phát và xóa bản sao A sau khi không còn token hợp lệ.
- Kiểm kê các cache/bản sao đã được tải về trước khi kết thúc rotation.

## 14. Audit và giám sát sử dụng khóa

Audit trail cần trả lời được: **ai đã gọi thao tác nào, trên key version nào, khi nào, từ workload nào và kết quả ra sao?**

Các sự kiện nên theo dõi:

- Tạo, import, export public key, disable, enable, rotate và destroy.
- Thay đổi IAM, key policy, alias, network access và cấu hình audit.
- Số lượng và tần suất sign request theo workload, issuer, key version.
- Thao tác ký ngoài giờ, tăng đột biến, thất bại liên tục hoặc gọi từ danh tính lạ.
- Lỗi vượt quota, lỗi thuật toán, lỗi key state và sự kiện truy cập bị từ chối.
- Thay đổi metadata/JWKS và thời điểm verifier nhận version mới.

Không ghi private key, secret, raw signing input nhạy cảm hoặc toàn bộ JWT nếu không cần thiết. Có thể log key ID, issuer profile, principal, request ID, algorithm, key version, timestamp và kết quả. Nếu log chứa subject hoặc claims, áp dụng chính sách dữ liệu cá nhân phù hợp.

Audit log nên được bảo vệ khỏi sửa/xóa bởi chính principal có quyền ký. Gửi bản sao đến hệ thống log/security monitoring độc lập nếu kiến trúc hỗ trợ.

## 15. Backup, khôi phục và tính sẵn sàng

Không phải mọi key đều cần export backup. Với HSM/KMS non-exportable, backup/replication thường được thực hiện bằng cơ chế được nhà cung cấp hỗ trợ và bảo vệ trong ranh giới tin cậy.

### 15.1. Xác định yêu cầu khôi phục

Trước khi triển khai, trả lời:

- Nếu region hoặc HSM cluster mất, issuer có thể tiếp tục ký bằng cùng key version không?
- Public key tương ứng có còn được verifier tin và có thể xác minh token cũ không?
- Có thể khôi phục key object từ backup hay phải chuyển sang key mới?
- Quy trình khôi phục cần quorum/custodian nào?
- Nếu không thể khôi phục, hệ thống có thể chuyển sang key mới và buộc người dùng xác thực lại không?

### 15.2. Backup và replication

- Chỉ dùng cơ chế backup/replication được KMS/HSM hỗ trợ.
- Bảo vệ backup bằng wrapping/encryption và quyền khôi phục riêng.
- Tách quyền tạo backup, đọc backup và restore.
- Kiểm soát bản sao ở region, account hoặc thiết bị dự phòng.
- Không copy private key dạng rõ vào object storage hoặc file share để dự phòng.
- Kiểm kê và hủy backup khi hết retention theo policy.

### 15.3. Kiểm thử disaster recovery

Một kế hoạch DR chỉ đáng tin khi đã diễn tập. Kiểm thử trong môi trường phù hợp:

1. Mất kết nối KMS/HSM chính.
2. Chuyển sang replica/region dự phòng.
3. Khôi phục key object hoặc kích hoạt key version thay thế.
4. Xác minh signing service dùng đúng key ID.
5. Xác minh JWKS được cập nhật và verifier nhận khóa mới.
6. Đo thời gian phục hồi và kiểm tra audit.

Không thực hiện thử nghiệm restore hoặc delete trên key production đang phục vụ nếu chưa có quy trình và phê duyệt tương ứng.

## 16. Ứng cứu khi khóa hoặc KMS/HSM bị xâm phạm

Sự cố có thể là lộ private key, đánh cắp workload credential có quyền ký, chiếm quyền quản trị KMS, thay đổi policy, hoặc xâm phạm endpoint JWKS.

Playbook khái quát:

1. **Phân loại:** xác định key ID/version, issuer, thuật toán, tenant, môi trường và khoảng thời gian bị ảnh hưởng.
2. **Ngăn hành vi tiếp diễn:** thu hồi workload credential, disable quyền ký hoặc key version, cô lập principal/endpoint bị xâm phạm.
3. **Ngăn verifier tin khóa:** phát tín hiệu thu hồi, chặn key ID, làm mới cache và cập nhật JWKS/policy khẩn.
4. **Thay khóa:** tạo key mới trong ranh giới tin cậy sạch, công bố public JWK, chuyển signer và kiểm tra token mới.
5. **Xử lý token:** từ chối token ký bằng khóa bị lộ theo chính sách; có thể cần vô hiệu hóa phiên và yêu cầu xác thực lại.
6. **Điều tra:** bảo toàn audit, xác định đường truy cập, kiểm tra backup, key export, IAM và các thay đổi cấu hình.
7. **Khôi phục:** cấp lại workload identity, thu hẹp policy, kiểm thử verifier và theo dõi tái diễn.
8. **Hậu kiểm:** ghi nhận phạm vi ảnh hưởng, quyết định thông báo và cải thiện kiểm soát.

Phân biệt hai sự cố:

- **Private key bị lộ:** attacker có thể ký ngoài hệ thống; phải ngừng tin cậy public key tương ứng.
- **Workload identity có quyền ký bị đánh cắp:** private key có thể vẫn an toàn và không export, nhưng attacker có thể gọi KMS để ký. Cần thu hồi identity/quyền gọi, kiểm tra audit và đánh giá token đã tạo trong khoảng bị chiếm.

Non-exportable key giảm rủi ro đánh cắp vật liệu nhưng không ngăn được lạm dụng API ký bởi principal bị chiếm quyền.

## 17. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Commit private key hoặc HMAC secret vào Git | Lộ qua lịch sử, fork, artifact và cache. | Secret manager/KMS/HSM; nếu đã lộ, rotate/revoke ngay cả khi xóa commit. |
| Đưa private key vào biến môi trường rồi để process giữ lâu | Có thể lộ qua dump, debug, process inspection hoặc log. | Ưu tiên non-exportable key và signing API; nếu buộc phải tải secret, giảm thời gian tồn tại và bảo vệ runtime. |
| Cấp quyền quản trị KMS cho ứng dụng | Ứng dụng bị chiếm có thể thay policy, tạo hoặc xóa khóa. | Tách quyền sign và quyền quản trị. |
| Một key dùng cho nhiều issuer/tenant | Sự cố một miền ảnh hưởng các miền khác. | Tách key theo issuer, môi trường và purpose phù hợp. |
| Cho verifier giữ HMAC secret rộng rãi | Mỗi verifier có thể tạo token giả. | Cân nhắc chữ ký bất đối xứng hoặc xác minh MAC qua dịch vụ chuyên trách. |
| Dùng alias mà không khóa version cho từng lần ký | Header key ID có thể không khớp key version thực tế. | Resolve version một lần và dùng nhất quán. |
| KMS ký digest sai chế độ | Chữ ký không tương thích JWS hoặc hash hai lần. | Kiểm tra API nhận message/digest và thuật toán cụ thể. |
| Đưa ECDSA DER vào JWS nguyên trạng | Chữ ký không đúng định dạng JOSE fixed-width R || S. | Chuyển đổi bằng adapter/thư viện JOSE đáng tin cậy. |
| Không audit sign operation | Khó phát hiện token bất thường và truy nguyên sự cố. | Audit theo principal, key version, algorithm và kết quả. |
| Xóa khóa mà chưa kiểm tra backup/retention | Khóa có thể vẫn khôi phục được hoặc mất khả năng xác minh cần thiết. | Quy trình retire/destroy và kiểm kê bản sao. |
| Tin rằng HSM loại bỏ mọi rủi ro | Principal hợp lệ bị chiếm vẫn có thể lạm dụng thao tác ký. | Bảo vệ workload identity, policy, rate limit và giám sát. |

## 18. Ví dụ thiết kế tham khảo cho issuer production

Giả sử một issuer phát hành access token RS256 cho một số API.

**Quản trị khóa**

- Một asymmetric RSA key được tạo trong KMS/HSM.
- Private key không export.
- Key policy chỉ cho phép signing service gọi thao tác ký bằng version active.
- Key administrator có quyền tạo/rotate nhưng không có quyền phát hành token hằng ngày.
- Auditor có quyền đọc audit records nhưng không có quyền ký.

**Phát hành token**

- Ứng dụng nghiệp vụ gửi yêu cầu phát hành với subject, audience và scope.
- Signing service xác thực workload identity của caller và kiểm tra policy.
- Signer resolve key version cụ thể, lấy key ID tương ứng và dựng protected header.
- Signer tạo JWS signing input và gọi KMS/HSM bằng thuật toán RS256.
- Signer ghép chữ ký thành compact JWT và trả token.

**Phân phối khóa**

- Public exporter lấy modulus và exponent của key version.
- Tạo public JWK có kiểu khóa RSA, key ID, mục đích chữ ký và algorithm RS256.
- JWKS endpoint công bố public key mới trước khi signer chuyển sang version mới.
- Verifier lấy JWKS từ issuer đã tin cậy, xác minh chữ ký và claims.

**Rotation**

- Tạo version B và công bố public JWK B bên cạnh A.
- Chờ verifier cập nhật cache.
- Resolve signer sang B; mỗi request dùng version B và key ID B nhất quán.
- Giữ public A cho token A còn hiệu lực.
- Sau thời hạn chấp nhận, rút A khỏi JWKS, disable quyền ký và destroy private A theo policy.

Thiết kế này giúp nhiều API xác minh token bằng public key mà không cần được cấp private key hoặc quyền ký.

## 19. Checklist review kho bí mật, KMS và HSM

**Thiết kế khóa**

- [ ] Loại khóa, thuật toán, kích thước/curve và purpose phù hợp.
- [ ] Khóa được sinh trong KMS/HSM khi có thể; import có quy trình bảo vệ.
- [ ] Mỗi issuer, tenant, môi trường và mục đích có phạm vi khóa rõ.
- [ ] Key ID gắn với đúng key version và không tái sử dụng.

**Bảo vệ và quyền**

- [ ] Private key/secret không nằm trong repository, artifact hoặc log.
- [ ] Ưu tiên non-exportable key nếu dùng asymmetric KMS/HSM signing.
- [ ] Workload identity được dùng thay credential tĩnh.
- [ ] Ứng dụng chỉ có quyền sign trên key/version cần thiết.
- [ ] Quyền create/import/export/rotate/destroy và quản trị IAM được tách riêng.
- [ ] Có break-glass và phân tách nhiệm vụ cho hành động đặc quyền.

**Tích hợp JWT/JOSE**

- [ ] Ký đúng JWS signing input gốc.
- [ ] API KMS nhận message hay digest đã được xác định rõ.
- [ ] RSA padding/hash và ECDSA/EdDSA algorithm khớp JWA.
- [ ] ECDSA DER được chuyển đúng sang JOSE R || S khi cần.
- [ ] Key ID trong header trùng key version thực sự đã ký.
- [ ] Public JWKS chỉ có public material.

**Vận hành**

- [ ] Có audit và cảnh báo sign operation bất thường.
- [ ] Có backup/replication và quy trình DR đã diễn tập.
- [ ] Rotation có pre-publish, overlap và retire rõ ràng.
- [ ] Có quy trình thu hồi key và workload identity khẩn cấp.
- [ ] Có kiểm kê backup, cache và consumer khi destroy key.

## 20. Tài liệu chuẩn tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): biểu diễn public/private key và JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JWS/JWE, RSA, ECDSA và HMAC.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): signing input và định dạng chữ ký JWS.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): yêu cầu xác minh JWT an toàn và giới hạn thuật toán.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): nguyên tắc quản lý vòng đời khóa mật mã.
- [NIST Cryptographic Key Management](https://csrc.nist.gov/projects/key-management): tài liệu và hướng dẫn quản lý khóa của NIST.
- [FIPS 140-3 — Security Requirements for Cryptographic Modules](https://csrc.nist.gov/pubs/fips/140/3/final): yêu cầu bảo mật cho mô-đun mật mã khi hệ thống cần đánh giá theo chuẩn này.

**Ghi nhớ:** Vault giúp quản lý và cấp phát secret; KMS cung cấp quản trị và API thao tác khóa; HSM tạo ranh giới phần cứng bảo vệ vật liệu khóa. Với JWT production, hãy giới hạn principal được ký, giữ private key trong KMS/HSM khi có thể, gắn key ID với đúng key version, audit mọi thao tác nhạy cảm và diễn tập rotation/DR/thu hồi. Khóa không export vẫn có thể bị lạm dụng qua API ký nếu workload identity bị chiếm, vì vậy bảo vệ quyền sử dụng quan trọng không kém bảo vệ byte khóa.
