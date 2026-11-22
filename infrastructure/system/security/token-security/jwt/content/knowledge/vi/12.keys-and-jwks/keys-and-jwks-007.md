# Tách khóa theo môi trường, bên phát hành và mục đích token

Một hệ thống JWT có thể có nhiều môi trường, nhiều issuer, nhiều tenant và nhiều loại token. Nếu tất cả cùng dùng một khóa ký, một sự cố ở một thành phần có thể ảnh hưởng đến toàn bộ hệ thống. **Tách khóa** là cách giới hạn phạm vi tin cậy và phạm vi ảnh hưởng: mỗi khóa chỉ phục vụ một miền sử dụng được xác định rõ, với danh tính, quyền, thuật toán, endpoint JWKS và vòng đời tương ứng.

Bài này thuộc chương **Khóa và JWKS** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng cho bảo mật JWT nói chung, độc lập với ngôn ngữ lập trình, nền tảng và framework.

## 1. Mục tiêu và nguyên tắc thiết kế

Sau bài học, người đọc có thể:

1. Xác định các ranh giới cần tách: môi trường, issuer/tenant, loại token và mục đích mật mã.
2. Thiết kế ma trận ánh xạ giữa issuer, token profile, thuật toán, key resource, `kid` và JWKS.
3. Hiểu khi nào nên dùng khóa riêng biệt và khi nào một nhóm verifier có thể dùng chung public key.
4. Tổ chức quyền ký, quyền xác minh, quyền quản trị và quyền công bố JWKS theo từng miền.
5. Di chuyển an toàn từ một khóa dùng chung sang nhiều khóa có phạm vi hẹp hơn.
6. Kiểm tra rằng việc tách khóa thực sự được thực thi trong cấu hình và luồng xác minh.

**Nguyên tắc:** một khóa chỉ nên được dùng trong một phạm vi tin cậy và một mục đích đã được phê duyệt. Mức tách cần dựa trên hậu quả nếu khóa bị lộ hoặc bị lạm dụng, không chỉ dựa trên số lượng ứng dụng.

## 2. Vì sao phải tách khóa?

Giả sử production, staging, nhiều issuer và cả access token lẫn ID token cùng dùng một RSA key. Nếu private key bị lộ trong staging, attacker có thể tạo token giả mang issuer/audience của production nếu verifier production cũng tin public key đó. Nếu cùng khóa còn ký nhiều token profile, attacker có thể tìm cách dùng token của profile này tại nơi chỉ định cho profile khác.

Tách khóa giúp:

- **Giới hạn blast radius:** sự cố ở một môi trường hoặc issuer không tự động làm lộ mọi miền khác.
- **Giảm quyền sử dụng:** mỗi workload chỉ được ký bằng key resource cần thiết.
- **Tách vòng đời:** khóa của service token có thể rotate độc lập với khóa của ID token.
- **Giảm nhầm lẫn thuật toán và mục đích:** key ký không bị dùng nhầm cho mã hóa.
- **Đơn giản hóa ứng cứu:** có thể chặn một `kid`/issuer mà không làm gián đoạn mọi hệ thống.
- **Hỗ trợ kiểm toán:** biết chính xác khóa nào phục vụ loại token nào và ai được quyền gọi.

Tách khóa không thay thế xác minh issuer, audience, chữ ký và claims. Một token được ký bằng đúng khóa vẫn có thể bị dùng sai API nếu verifier không kiểm tra token profile.

## 3. Các chiều cần tách

Không có một cách chia duy nhất phù hợp mọi hệ thống. Hãy xác định ít nhất các chiều sau:

| Chiều tách | Ví dụ | Câu hỏi thiết kế |
| --- | --- | --- |
| **Môi trường** | Development, test, staging, production | Khóa test có thể tạo token được production chấp nhận không? |
| **Bên phát hành** | Identity provider A, issuer nội bộ B, tenant C | Khóa của issuer này có được verifier của issuer khác tin không? |
| **Tenant / realm** | Tenant A và tenant B trên cùng nền tảng | Một tenant có thể ký token cho tenant khác không? |
| **Mục đích token** | Access token, ID token, service token, token reset | Token của một profile có thể bị dùng ở endpoint của profile khác không? |
| **Mục đích mật mã** | Signing, verification, encryption, key agreement | Khóa ký có bị tái sử dụng cho mã hóa hoặc wrap key không? |
| **Thuật toán / key type** | RS256, PS256, ES256, EdDSA, HS256 | Khóa và thuật toán có bị ràng buộc chính xác không? |
| **Vòng đời / phiên bản** | Active, staged, verify-only, revoked | Có thể rotate hoặc thu hồi một phiên bản độc lập không? |

Các chiều này có thể kết hợp. Ví dụ một issuer production có thể có khóa riêng cho access token và ID token, trong khi issuer staging có key set riêng hoàn toàn.

## 4. Ma trận tách khóa tham khảo

Một ma trận đơn giản:

| Môi trường | Issuer | Token profile | Khóa ký | JWKS / trust scope |
| --- | --- | --- | --- | --- |
| Development | `https://dev-id.example.test/` | Access | DEV-ACCESS-A | DEV issuer only |
| Development | `https://dev-id.example.test/` | ID | DEV-ID-A | DEV issuer only |
| Staging | `https://staging-id.example.test/` | Access | STG-ACCESS-A | STAGING issuer only |
| Staging | `https://staging-id.example.test/` | ID | STG-ID-A | STAGING issuer only |
| Production | `https://id.example.test/` | Access | PROD-ACCESS-A | PRODUCTION issuer only |
| Production | `https://id.example.test/` | ID | PROD-ID-A | PRODUCTION issuer only |

Tên khóa ở đây là nhãn minh họa. Điểm quan trọng:

- Không dùng private key của development hoặc staging trong production.
- Không dùng cùng key resource chỉ vì các issuer chạy cùng phần mềm.
- Không gộp mọi public key vào một JWKS chung rồi để verifier chọn chỉ bằng `kid`.
- Có thể dùng chung một public key cho nhiều verifier **của cùng issuer và cùng profile** nếu đó là chủ đích; điều này không có nghĩa phải dùng chung khóa giữa các issuer.

## 5. Tách môi trường: development, test, staging và production

Môi trường là ranh giới bảo mật quan trọng vì quyền truy cập, dữ liệu, người vận hành và mức độ kiểm soát thường khác nhau.

### 5.1. Dùng khóa riêng cho từng môi trường

Khuyến nghị:

- Mỗi môi trường có key resource riêng và `kid` riêng.
- Dùng KMS/HSM account, project, partition hoặc namespace riêng nếu nền tảng hỗ trợ.
- Dùng workload identity và IAM policy riêng.
- Tách JWKS endpoint, issuer và trust registry.
- Tách secrets, backup, audit và quy trình break-glass.
- Khóa production chỉ được cấp cho workload production đã phê duyệt.

Không đưa private key production vào môi trường test để tạo token “giống thật”. Nếu cần kiểm thử xác minh, dùng public key production trong môi trường được kiểm soát khi policy cho phép, hoặc tốt hơn là tạo fixture/token test bằng khóa test riêng. Public key không phải bí mật, nhưng việc phân phối vẫn cần theo phạm vi và chính sách.

### 5.2. Không tin issuer staging trong production

Một verifier production không nên chấp nhận token chỉ vì chữ ký hợp lệ bằng khóa của staging. Production cần allowlist issuer riêng và audience riêng. Ví dụ:

~~~text
Production trust registry:
  issuer = https://id.example.test/
  audience = payments-api
  allowed algorithms = [RS256]
  JWKS = production JWKS URI

Staging trust registry:
  issuer = https://staging-id.example.test/
  audience = payments-staging-api
  allowed algorithms = [RS256]
  JWKS = staging JWKS URI
~~~

Ngay cả khi hai môi trường dùng cùng thuật toán và cấu trúc token, issuer và khóa phải khác nhau. Không dùng wildcard kiểu “tin mọi subdomain *.example.test” nếu không có thiết kế federation riêng được kiểm soát.

### 5.3. Dữ liệu test và khóa test

Không tạo test token bằng cách copy private key production. Nên:

- Sinh key pair test độc lập.
- Dùng claims và subject giả lập, không chứa dữ liệu người dùng production.
- Đặt thời hạn ngắn cho test token.
- Không dùng production audience hoặc issuer trong test.
- Dọn key và token test theo vòng đời môi trường.

Nếu kiểm thử tương thích với production verifier, tạo bộ kiểm thử có kiểm soát ở môi trường cách ly; không cấp quyền ký production cho test runner.

## 6. Tách theo issuer và tenant

Issuer là ranh giới nguồn gốc token. Mỗi issuer nên có key set và trust configuration riêng, kể cả khi nhiều issuer dùng chung một sản phẩm identity hoặc cùng một hostname.

### 6.1. Nhiều issuer trên cùng nền tảng

Ví dụ:

| Issuer | JWKS | Khóa |
| --- | --- | --- |
| `https://identity.example.test/realm-a` | JWKS realm A | RSA key A |
| `https://identity.example.test/realm-b` | JWKS realm B | RSA key B |

Không suy ra hai issuer dùng chung khóa chỉ vì cùng hostname. Path, realm hoặc tenant có thể tạo ra miền tin cậy khác nhau. Verifier cần:

1. Xác định issuer được phép từ cấu hình.
2. Lấy JWKS gắn với issuer đó.
3. Tra `kid` trong đúng key set.
4. Xác minh chữ ký và kiểm tra `iss` chính xác.
5. Kiểm tra audience và tenant context.

### 6.2. Có nên dùng chung một khóa cho nhiều issuer?

Mặc định nên tách. Chỉ cân nhắc dùng chung khi:

- Các issuer thuộc cùng một miền quản trị và trust boundary.
- Có lý do kiến trúc rõ ràng, chẳng hạn cùng một signing authority.
- Các verifier hiểu rằng khóa chung không làm issuer trở thành một.
- `iss`, `aud`, token profile và policy vẫn được xác minh độc lập.
- Quy trình rotate/revoke đã đánh giá ảnh hưởng đồng thời đến tất cả issuer.

Ngay cả khi public key giống nhau, `iss` vẫn phải được kiểm tra. Chữ ký hợp lệ chỉ chứng minh người nắm private key tương ứng đã ký; nó không tự xác định issuer nào trong số các issuer chia sẻ khóa đã phát hành token.

### 6.3. Tách tenant trong hệ thống multi-tenant

Nếu mỗi tenant là một issuer riêng, nên dùng key pair riêng cho từng tenant hoặc một cơ chế signing authority có phân quyền rõ ràng và ràng buộc tenant. Nếu dùng chung một key:

- Tenant có thể bị ảnh hưởng chéo khi private key hoặc signer bị lạm dụng.
- Audit khó xác định nguồn ký nếu signer không ghi nhận tenant context.
- Thu hồi một tenant có thể yêu cầu thay khóa cho tất cả tenant.

Với tenant có yêu cầu cách ly cao, dùng key resource riêng và quyền ký riêng. Với tenant số lượng rất lớn, có thể thiết kế KMS multi-tenant với policy/identity isolation; phải chứng minh tenant A không thể yêu cầu ký trong namespace B.

## 7. Tách theo mục đích token và token profile

Một issuer có thể phát hành nhiều loại JWT. Mỗi loại có mục đích, audience, claims và vòng đời khác nhau. Dùng cùng một khóa cho mọi token có thể tạo rủi ro **token substitution**: token hợp lệ ở ngữ cảnh này bị dùng nhầm ở ngữ cảnh khác.

Ví dụ các profile:

| Token profile | Người nhận dự kiến | Claims/chính sách tiêu biểu | Hướng tách |
| --- | --- | --- | --- |
| Access token | Resource server/API | `aud`, `scope`, thời hạn ngắn, issuer | Khóa/profile dành cho access token |
| ID token | OIDC client/Relying Party | `aud` là client ID, `nonce` theo luồng, claims xác thực người dùng | Policy xác minh ID token riêng; cân nhắc key riêng |
| Service token | Dịch vụ nội bộ | Audience dịch vụ, workload subject, scope hẹp | Key/issuer hoặc profile service riêng |
| Password reset token | Endpoint đặt lại mật khẩu | Subject, mục đích reset, nonce hoặc trạng thái một lần, TTL rất ngắn | Khóa riêng hoặc token purpose isolation mạnh |
| Email verification token | Endpoint xác minh email | Subject, mục đích xác minh, hạn sử dụng | Profile riêng, không chấp nhận ở API access |
| Token giao dịch nhạy cảm | Một nghiệp vụ cụ thể | Transaction ID, amount, audience, thời gian | Khóa/profile riêng khi rủi ro yêu cầu |

Đây là gợi ý kiến trúc; không phải mọi profile bắt buộc có một cặp khóa vật lý riêng. Nhưng **policy xác minh phải tách** ngay cả khi dùng chung một key pair.

### 7.1. Access token và ID token

Trong OpenID Connect, ID Token được phát hành cho client để cung cấp thông tin xác thực người dùng; access token được dùng để truy cập resource server. Hai token có thể đều là JWT nhưng không có cùng mục đích.

Verifier cần phân biệt:

- Audience: ID Token hướng đến client; access token hướng đến resource server.
- Token profile và claims bắt buộc.
- Quy tắc thời gian và luồng phát hành.
- Nơi token được phép xuất hiện.

Không chấp nhận ID Token làm access token chỉ vì chữ ký hợp lệ hoặc cùng issuer. Có thể dùng khóa riêng cho hai profile để tăng cách ly; nếu nhà cung cấp dùng chung khóa, resource server vẫn phải enforce access-token profile và audience.

### 7.2. Token một lần hoặc token có mục đích đặc biệt

JWT dùng cho reset password, xác minh email hoặc giao dịch nhạy cảm cần kiểm soát purpose rõ ràng. Nên có:

- Audience riêng hoặc endpoint-specific audience.
- Claim xác định mục đích, ví dụ `purpose`.
- TTL ngắn và kiểm tra trạng thái một lần ở server khi nghiệp vụ yêu cầu.
- Không chấp nhận token này ở middleware/API access thông thường.
- Có thể dùng key riêng nếu hậu quả của token substitution lớn.

Chỉ thêm claim `purpose` không đủ nếu verifier không bắt buộc kiểm tra claim đó. Việc tách profile phải được thực thi ở nơi xác minh.

## 8. Tách theo mục đích mật mã: signing và encryption

JWK có thể biểu diễn khóa cho nhiều thao tác JOSE. Một khóa dùng để ký không nên được tái sử dụng tùy tiện cho mã hóa, giải mã, key wrapping hoặc key agreement.

| Mục đích | Vai trò | Metadata thường liên quan |
| --- | --- | --- |
| JWS signing | Tạo chữ ký/MAC | `use=sig`, `key_ops` có `sign` |
| JWS verification | Kiểm tra chữ ký/MAC | `use=sig`, `key_ops` có `verify` |
| JWE encryption | Mã hóa nội dung hoặc quản lý khóa | `use=enc`, thao tác phù hợp với thuật toán |
| JWE decryption | Giải mã hoặc mở bọc khóa | `use=enc`, `key_ops` như `decrypt` hoặc `unwrapKey` tùy cơ chế |
| Key agreement | Thỏa thuận bí mật | Key type/curve và thuật toán ECDH/XDH tương ứng |

Với RSA, cùng họ khóa có thể hỗ trợ các thuật toán ký hoặc mã hóa khác nhau, nhưng điều đó không có nghĩa nên dùng một key pair cho cả hai. Tách key pair giúp giảm hậu quả khi một thuật toán, giao thức hoặc thành phần bị xâm phạm.

Với EC/OKP, curve và thuật toán có thể gắn với mục đích khác nhau. Không dùng khóa ECDH/XDH như khóa chữ ký chỉ vì tên curve có vẻ liên quan.

## 9. Tách khóa đối xứng và bất đối xứng

HMAC và chữ ký bất đối xứng có mô hình tin cậy khác nhau:

| Thuộc tính | HMAC | Chữ ký bất đối xứng |
| --- | --- | --- |
| Vật liệu ký | Secret dùng chung | Private key |
| Vật liệu xác minh | Cùng secret | Public key |
| Verifier có thể tự tạo token? | Có, vì nắm secret | Không, nếu chỉ có public key |
| Phân phối JWKS công khai | Không công bố `oct.k` | Có thể công bố public JWK |
| Phạm vi tin cậy | Mọi bên giữ secret đều có quyền tạo MAC | Chỉ bên có private key được quyền ký |

Nếu có nhiều verifier độc lập, chữ ký bất đối xứng thường dễ giới hạn quyền hơn. Với HMAC, không dùng một secret cho nhiều issuer hoặc môi trường; mỗi nhóm verifier được cấp secret đều phải được xem là một bên có quyền phát hành token.

Không tái sử dụng cùng byte khóa giữa HMAC và thuật toán bất đối xứng, hoặc giữa HMAC và encryption. Việc cùng biểu diễn dưới dạng Base64/JWK không làm các mục đích tương đương.

## 10. Key separation và domain separation

**Key separation** là dùng các khóa khác nhau cho các mục đích hoặc miền tin cậy khác nhau. **Domain separation** là bảo đảm cùng một primitive hoặc quy trình mật mã không thể bị hiểu nhầm giữa các ngữ cảnh bằng cách gắn nhãn/ngữ cảnh riêng vào đầu vào hoặc quá trình dẫn xuất.

Ví dụ nhãn ngữ cảnh:

~~~text
issuer = https://id.example.test/
environment = production
purpose = access-token-signing
algorithm = RS256
~~~

Những giá trị này có thể được dùng trong registry, policy, audit và quy trình quản trị để ngăn nhầm lẫn. Chúng không tự tạo ra key separation nếu tất cả vẫn trỏ đến cùng một private key và cùng quyền ký.

### 10.1. Ưu tiên khóa độc lập

Mặc định nên sinh các khóa độc lập bằng CSPRNG hoặc cơ chế sinh khóa của KMS/HSM:

- Khóa ký access token khác khóa ký ID token khi cần cách ly.
- Khóa production khác staging.
- Khóa signing khác encryption.
- Khóa issuer A khác issuer B khi các issuer là miền tin cậy riêng.

Không dùng một master private key rồi tự cắt byte để tạo RSA/EC key con. Không tự lấy private scalar hoặc RSA parameters bằng phép chia chuỗi/biến đổi tùy ý.

### 10.2. Khi nào dùng KDF?

Với một số thiết kế khóa đối xứng, có thể dùng KDF chuẩn như HKDF để dẫn xuất các subkey từ một secret gốc. Khi đó phải:

- Dùng KDF và hash được phê duyệt.
- Dùng salt và context/info riêng cho từng mục đích, issuer và môi trường.
- Đảm bảo mỗi nhãn ngữ cảnh là duy nhất, ổn định và được kiểm soát.
- Không dùng trực tiếp master secret làm HMAC/JWE key.
- Quản lý vòng đời và thu hồi master secret; khi master lộ, mọi subkey dẫn xuất có thể bị ảnh hưởng.
- Dùng thư viện/KMS hỗ trợ KDF đã được kiểm tra; không tự thiết kế thuật toán dẫn xuất.

KDF không thay thế quy trình key management và không phải cách chung để tạo private key RSA/EC/OKP từ một secret tùy ý. Với khóa bất đối xứng JWT, ưu tiên tạo key pair độc lập trong KMS/HSM.

## 11. Ma trận ánh xạ issuer, profile, thuật toán và key resource

Một registry quản trị có thể biểu diễn ràng buộc như sau:

| Environment | Issuer | Profile | Algorithm | Key resource/version | `kid` | JWKS scope |
| --- | --- | --- | --- | --- | --- | --- |
| Production | Issuer A | Access | RS256 | KMS key A / v4 | `a-access-v4` | Issuer A |
| Production | Issuer A | ID | ES256 | KMS key B / v2 | `a-id-v2` | Issuer A |
| Production | Issuer B | Service | EdDSA | HSM key C / v1 | `b-service-v1` | Issuer B |
| Staging | Issuer A | Access | RS256 | KMS key D / v3 | `stg-a-access-v3` | Staging A |

Registry này là nguồn quản trị policy, không nhất thiết là JSON JWKS. JWK chỉ chứa public parameters và metadata phù hợp; key resource ID, owner, environment và trạng thái có thể được lưu ở hệ thống quản lý khóa.

Các ràng buộc cần enforce:

- Một `kid` phải ánh xạ duy nhất đến đúng vật liệu khóa trong phạm vi issuer/JWKS.
- Key resource phải thuộc đúng environment, issuer và purpose.
- Thuật toán phải được allowlist và tương thích key type/curve.
- Signer chỉ được dùng key version active cho profile tương ứng.
- Verifier chỉ tin JWKS của issuer đã cấu hình và kiểm tra token profile.
- Không tự động dùng key của profile khác khi không tìm thấy key đúng.

## 12. Tách quyền trong KMS/HSM

Tách key resource mà IAM vẫn cho mọi workload ký bằng mọi key thì chưa tạo được isolation thực sự.

| Principal | Quyền nên có | Quyền không nên có |
| --- | --- | --- |
| Production access-token signer | Sign bằng key access production được chỉ định | Sign bằng key ID, staging hoặc encryption key |
| ID-token signer | Sign bằng key/profile ID token | Sign bằng access/service key khác nếu không được phê duyệt |
| Staging signer | Sign bằng key staging | Truy cập key production |
| JWKS publisher | Lấy public parameters và công bố public JWK | Export private key hoặc gọi sign |
| Verifier/API | Đọc JWKS public và xác minh tại chỗ | Gọi sign hoặc đọc HMAC secret không cần thiết |
| Key administrator | Tạo, rotate, disable, quản lý policy theo quy trình | Phát hành token thường ngày |
| Auditor | Đọc audit records | Sign, export private key hoặc sửa audit |

Policy cần giới hạn cả resource và operation. Nếu một service có quyền `sign` trên toàn bộ key trong account/project, việc tạo key riêng cho từng issuer không đủ ngăn service đó ký thay issuer khác.

## 13. Tách JWKS và trust configuration

Tách key chỉ có hiệu lực khi verifier biết key set thuộc issuer và profile nào.

### 13.1. Endpoint JWKS riêng

Với các issuer độc lập, thường nên công bố JWKS riêng hoặc ít nhất có endpoint/metadata mapping rõ ràng:

~~~text
Issuer A -> metadata A -> JWKS A -> keys A
Issuer B -> metadata B -> JWKS B -> keys B
Staging  -> metadata staging -> JWKS staging -> keys staging
~~~

Không gộp key của mọi issuer vào một JWKS dùng chung rồi chỉ dựa vào `kid` để phân biệt. Một JWKS có thể chứa nhiều khóa cho cùng một issuer, nhưng việc phân phối phải giữ được ranh giới nguồn gốc.

### 13.2. Nếu hạ tầng bắt buộc dùng một endpoint chung

Một endpoint chung có thể phục vụ nhiều issuer trong một nền tảng, nhưng cần ánh xạ tenant/issuer được kiểm soát:

- Mỗi issuer có identifier chính xác và policy riêng.
- Endpoint không trả private material.
- Không để caller tự chọn tenant key bằng một tham số không được xác thực.
- Verifier vẫn xác định issuer trước, sau đó chỉ chọn key thuộc issuer đó.
- Cache và audit phải giữ tenant/issuer context.

Endpoint chung là cách triển khai hạ tầng; nó không biến nhiều issuer thành một miền tin cậy duy nhất.

### 13.3. Không dùng `kid` làm định danh toàn cục

`kid` chỉ cần duy nhất trong phạm vi key set/issuer mà verifier tra cứu. Hai issuer có thể cùng có `kid="key-01"`. Cache hoặc registry nội bộ nên dùng tổ hợp như:

~~~text
environment + issuer + token profile + kid
~~~

Không chỉ cache theo `kid`, và không tìm khóa trên mọi issuer để thử chữ ký.

## 14. Quy trình di chuyển từ một khóa dùng chung sang khóa tách biệt

Hệ thống cũ có thể đang dùng một key pair cho tất cả token hoặc tất cả môi trường. Không nên thay đổi đồng loạt mà không kiểm kê verifier và token đang còn hiệu lực.

### Giai đoạn 1 — Kiểm kê

1. Liệt kê issuer, tenant, môi trường, token profile và audience.
2. Xác định key resource/version, `kid`, thuật toán và nơi private material đang được lưu.
3. Liệt kê mọi signer, verifier, JWKS consumer, cache và client offline.
4. Xác định thời hạn token tối đa, clock skew và các luồng đặc biệt.
5. Xác định ràng buộc tương thích với hệ thống bên ngoài.

### Giai đoạn 2 — Tạo key set mới

1. Tạo khóa độc lập cho từng miền cần tách.
2. Gán `kid` mới, không tái sử dụng `kid` cũ.
3. Đặt IAM/key policy riêng.
4. Tạo public JWK và kiểm tra thuật toán/curve.
5. Công bố khóa mới trong JWKS đúng issuer/profile.

### Giai đoạn 3 — Chuyển signer

1. Chuyển một issuer/profile hoặc môi trường theo từng đợt.
2. Đảm bảo verifier đã nhận public key mới.
3. Ký token mới bằng key version mới và `kid` tương ứng.
4. Theo dõi lỗi xác minh, audience/profile mismatch và các request bị từ chối.

### Giai đoạn 4 — Giai đoạn overlap

Trong thời gian chuyển tiếp, verifier có thể cần tin cả khóa cũ và mới. Tuy nhiên:

- Chỉ giữ khóa cũ trong phạm vi issuer/profile đã dùng nó.
- Không dùng key cũ làm fallback cho mọi token.
- Không tự thử khóa ở môi trường khác.
- Ghi nhận token nào còn được ký bằng key cũ.
- Đặt thời điểm kết thúc overlap dựa trên token lifetime và policy.

### Giai đoạn 5 — Ngừng khóa cũ

1. Ngừng ký bằng khóa cũ.
2. Chờ token cũ hết hạn theo cửa sổ được phê duyệt, nếu không có sự cố bảo mật.
3. Rút public key cũ khỏi JWKS hoặc chuyển trạng thái không còn tin cậy theo policy.
4. Thu hồi quyền ký, xử lý backup và destroy private material khi được phép.
5. Xóa các cấu hình dùng chung cũ và xác nhận verifier không còn phụ thuộc.

Nếu khóa cũ bị lộ, bỏ qua thời gian overlap thông thường và thực hiện thu hồi khẩn cấp.

## 15. Xử lý sự cố và giới hạn blast radius

Khi một khóa bị lộ, thiết kế tách biệt tốt cho phép giới hạn ứng cứu:

| Sự cố | Phạm vi xử lý nếu đã tách khóa |
| --- | --- |
| Khóa staging bị lộ | Thu hồi key staging, không cần thay khóa production nếu không có liên kết tin cậy khác. |
| Khóa issuer A bị lộ | Chặn `kid`/key của issuer A; issuer B tiếp tục nếu dùng miền khóa độc lập. |
| Khóa ID token bị lộ | Thu hồi profile ID token; access token có thể tiếp tục nếu dùng khóa riêng và policy riêng. |
| Khóa encryption bị lộ | Xử lý dữ liệu mã hóa và key encryption liên quan; key signing độc lập không tự động bị ảnh hưởng. |
| Workload của signer bị chiếm | Thu hồi identity và quyền sign của workload đó; đánh giá token được phát hành trong khoảng bị chiếm. |

Các bước ứng cứu:

1. Xác định key resource, version, `kid`, issuer, environment và profile.
2. Thu hồi principal hoặc quyền ký bị xâm phạm.
3. Đánh dấu key/`kid` không còn được tin tại verifier.
4. Cập nhật JWKS và cache theo cơ chế khẩn cấp.
5. Tạo khóa thay thế trong miền tin cậy sạch.
6. Đánh giá token đã phát hành; vô hiệu hóa session hoặc yêu cầu xác thực lại nếu cần.
7. Xác nhận các issuer/môi trường khác không dùng chung key hoặc quyền bị ảnh hưởng.

Nếu các miền đã dùng chung key, sự cố có thể lan rộng hơn dự kiến. Không giả định việc xóa key khỏi một endpoint đã xóa các bản sao ở cache hoặc verifier cấu hình tĩnh.

## 16. Kiểm thử rằng ranh giới tách khóa được thực thi

Không chỉ review sơ đồ. Cần kiểm thử cả trường hợp được phép và bị cấm.

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Token production ký bằng production key, đúng issuer/audience/profile | Chấp nhận nếu mọi claims và policy hợp lệ. |
| Token staging gửi đến production API | Từ chối vì issuer/audience/profile không được phép. |
| Token issuer A ký bằng key issuer B | Từ chối; không tìm key xuyên issuer. |
| ID token gửi đến resource server như access token | Từ chối theo token profile/audience. |
| Access token gửi đến OIDC client như ID token | Từ chối theo profile và audience. |
| Key encryption được dùng để xác minh JWS | Từ chối vì sai mục đích/key policy. |
| Signer access token yêu cầu ký bằng key ID token | KMS/HSM policy từ chối. |
| Staging workload gọi production key | IAM/KMS policy từ chối. |
| `kid` không tồn tại trong JWKS của issuer | Refresh có giới hạn nếu policy cho phép, sau đó từ chối. |
| Hai issuer có cùng `kid` | Mỗi issuer chỉ tra trong key set của chính mình. |
| Khóa bị thu hồi vẫn còn trong cache | Deny/revocation policy vẫn chặn khóa đó. |

Nên đưa các kiểm thử âm tính này vào kiểm thử bảo mật định kỳ và kiểm thử tích hợp giữa issuer, JWKS publisher và verifier.

## 17. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng chung private key production và staging | Lộ khóa ở staging có thể ảnh hưởng production. | Tách key resource, IAM, issuer và JWKS. |
| Một key cho mọi tenant | Sự cố một tenant ảnh hưởng các tenant khác. | Tách theo tenant hoặc dùng signer có policy isolation được kiểm chứng. |
| Một key cho access token và ID token mà không tách profile | Tăng nguy cơ token substitution. | Tách key khi phù hợp và luôn tách verifier policy/audience. |
| Dùng key ký cho JWE encryption | Lẫn mục đích và tăng hậu quả khi một cơ chế bị yếu. | Dùng key riêng cho signing và encryption. |
| Một HMAC secret cấp cho nhiều dịch vụ | Mọi verifier có thể tạo token giả. | Hạn chế consumer, tách secret hoặc dùng chữ ký bất đối xứng. |
| Chỉ đổi `kid` nhưng giữ nguyên vật liệu khóa | Metadata gây cảm giác có khóa mới trong khi key bytes không đổi. | Tạo key material mới và gắn `kid` mới. |
| Dùng `kid` toàn cục | Đụng độ giữa issuer hoặc tenant. | Định danh theo issuer/environment/profile cộng với `kid`. |
| Có key riêng nhưng IAM cho mọi service ký mọi key | Không có isolation thực tế. | Ràng buộc principal, operation và key resource trong policy. |
| Gộp mọi khóa vào một JWKS không có issuer mapping | Verifier dễ chọn nhầm key. | JWKS và trust mapping riêng theo issuer. |
| Chuyển khóa nhưng không kiểm kê verifier | Token mới bị từ chối hoặc key cũ được tin quá lâu. | Inventory consumer, pre-publish, overlap có giới hạn và retire. |

## 18. Ví dụ kiến trúc tổng hợp

Giả sử một tổ chức có production và staging; production có issuer cho người dùng và issuer cho service-to-service.

~~~mermaid
flowchart TB
    subgraph PROD["Production trust boundary"]
      P1["User issuer"] --> PK1["User signing key"]
      P2["Service issuer"] --> PK2["Service signing key"]
      PK1 --> JW1["User JWKS"]
      PK2 --> JW2["Service JWKS"]
      JW1 --> PV1["User/API verifiers"]
      JW2 --> PV2["Service verifiers"]
    end
    subgraph STG["Staging trust boundary"]
      S1["Staging issuer"] --> SK1["Staging signing key"]
      SK1 --> JW3["Staging JWKS"]
      JW3 --> SV["Staging verifiers"]
    end
    STG -. "No production trust" .-> PROD
~~~

Các ràng buộc:

- Production user issuer và service issuer có key resource, audience và profile riêng.
- Staging có issuer, key resource, workload identity và JWKS riêng.
- Production verifier không đăng ký staging issuer.
- User/API verifier chỉ chấp nhận access-token profile dành cho audience của nó.
- Service verifier chỉ chấp nhận service-token profile.
- Mỗi signer chỉ được gọi key resource tương ứng.
- JWKS publisher chỉ có quyền lấy public parameters.

Nếu một workload staging bị xâm nhập, attacker không thể dùng identity đó gọi production key; token staging cũng không được production verifier chấp nhận.

## 19. Checklist thiết kế tách khóa

**Phân vùng**

- [ ] Production, staging, test và development có key resource riêng.
- [ ] Mỗi issuer/tenant có trust mapping và phạm vi JWKS rõ.
- [ ] Access, ID, service và token đặc biệt có profile riêng.
- [ ] Signing, encryption, key wrapping và key agreement dùng khóa đúng mục đích.
- [ ] HMAC secret không được chia sẻ rộng hơn miền tin cậy cần thiết.

**Quyền và định danh**

- [ ] Workload chỉ được ký bằng key resource/version được chỉ định.
- [ ] Quyền signer, JWKS publisher, verifier và key administrator được tách.
- [ ] Key ID không tái sử dụng và gắn đúng key material/version.
- [ ] Cache và lookup có environment, issuer và profile context.

**Verifier**

- [ ] Issuer nằm trong trust registry chính xác.
- [ ] JWKS được lấy từ endpoint gắn với issuer.
- [ ] `kid`, `alg`, `kty`, `use`, `key_ops` và curve tương thích.
- [ ] Audience, token type/profile, thời hạn và claims được kiểm tra.
- [ ] Không fallback sang key của issuer, tenant hoặc môi trường khác.

**Vòng đời**

- [ ] Rotation độc lập theo từng miền khóa.
- [ ] Có overlap có giới hạn và kế hoạch retire.
- [ ] Thu hồi khẩn cấp có thể chặn key dù cache chưa hết hạn.
- [ ] Migration khỏi key dùng chung có inventory và kiểm thử âm tính.
- [ ] Audit có thể truy nguyên issuer, profile, principal và key version.

## 20. Tài liệu chuẩn tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): member `use`, `key_ops`, `kid`, `alg` và cấu trúc JWKS.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header và chữ ký JWS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán và kiểu khóa JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims `iss`, `aud`, `exp`, `nbf` và cấu trúc JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, issuer/audience validation và phòng token substitution.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)](https://www.rfc-editor.org/rfc/rfc5869): dẫn xuất subkey và sử dụng context/info khi thiết kế domain separation.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): quản lý vòng đời và phạm vi sử dụng khóa mật mã.

**Ghi nhớ:** tách khóa theo môi trường để ngăn staging ảnh hưởng production; theo issuer/tenant để giới hạn nguồn phát hành; theo token profile để giảm token substitution; và theo mục đích mật mã để tránh tái sử dụng khóa sai cách. Việc tách chỉ có hiệu lực khi key resource, IAM, `kid`, JWKS, issuer binding và verifier policy cùng thực thi một ranh giới.
