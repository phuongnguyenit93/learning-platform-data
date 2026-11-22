# Tách cấu hình bên phát hành khỏi cấu hình bên xác minh

## 1. Vì sao phải tách hai cấu hình?

Trong một hệ thống JWT, bên phát hành (issuer) tạo token và bảo vệ nội dung bằng chữ ký hoặc cơ chế JOSE phù hợp. Bên xác minh (verifier) nhận token từ một nguồn có thể chưa đáng tin, kiểm tra chữ ký, issuer, audience, thời hạn và các điều kiện của token profile trước khi cho phép request tiếp tục.

Hai bên có trách nhiệm khác nhau:

- Issuer quyết định có phát hành token hay không, token đại diện cho ai, dành cho resource nào, có quyền gì và được bảo vệ bằng khóa nào.
- Verifier quyết định có tin token nhận được hay không, issuer nào được chấp nhận, khóa nào được dùng để xác minh, token phải có audience/claim nào và chính sách nào phải được đáp ứng.

Nếu dùng chung một cấu hình lớn cho cả hai vai trò, hệ thống dễ tạo ra những lỗi như:

- Verifier vô tình có private signing key hoặc HMAC secret không cần thiết.
- Issuer và verifier dùng thuật toán khác nhau hoặc hiểu khác nhau về token profile.
- Một thay đổi để phát hành token mới vô tình làm nới lỏng chính sách chấp nhận token ở resource server.
- Môi trường development, staging và production dùng nhầm khóa hoặc issuer.
- Verifier tin issuer, key URL hoặc thuật toán do chính token tự khai báo.
- Các API chấp nhận token quá rộng vì dùng chung audience, issuer hoặc claim policy.

Tách cấu hình giúp phân định quyền, giảm lượng bí mật được phân phối, quản lý thay đổi độc lập và kiểm thử rõ ràng hơn. Việc tách cấu hình không có nghĩa là hai bên được phép định nghĩa hai giao thức không tương thích. Chúng vẫn cần thống nhất token profile, thuật toán, issuer, audience và cách luân chuyển khóa.

Bài này áp dụng cho JWT/JOSE tổng quát, không phụ thuộc ngôn ngữ lập trình, thư viện JWT hay framework cụ thể.

## 2. Phân biệt vai trò issuer và verifier

| Trách nhiệm | Issuer / bên phát hành | Verifier / bên xác minh |
| --- | --- | --- |
| Quyết định phát hành | Xác thực requester và quyết định cấp token | Không tự phát hành token từ request đang xác minh |
| Tạo claims | Tạo sub, aud, exp, scope và claims theo profile | Kiểm tra claims đã phát hành có đáp ứng policy không |
| Bảo vệ mật mã | Ký JWS hoặc mã hóa JWE theo vai trò được giao | Xác minh chữ ký hoặc xác thực/giải mã JWE |
| Khóa | Giữ private signing key hoặc secret ký | Với chữ ký bất đối xứng, chỉ cần public verification key |
| Thuật toán | Chọn thuật toán đã được policy cho phép khi ký | Có allowlist độc lập và kiểm tra thuật toán token khai báo |
| Issuer | Đặt giá trị iss đúng danh tính issuer | So khớp iss với issuer được cấu hình tin cậy |
| Audience | Phát hành token cho recipient/resource phù hợp | Yêu cầu aud chứa chính resource server theo profile |
| Thời hạn | Đặt iat/nbf/exp theo chính sách cấp token | Kiểm tra thời gian và clock-skew leeway |
| Key rotation | Tạo và sử dụng khóa mới, công bố public key | Nạp, cache và chuyển đổi sang public key mới |
| Thu hồi | Quản lý trạng thái token/session và sự kiện thu hồi | Kiểm tra trạng thái theo cơ chế mà profile yêu cầu |

Một tiến trình có thể vừa phát hành vừa xác minh token trong một số kiến trúc, nhưng cấu hình và quyền của từng chức năng vẫn nên tách biệt. Ví dụ, một identity service có thể ký access token và cũng xác minh refresh token; điều đó không có nghĩa mọi resource server cần quyền truy cập private signing key.

## 3. Mô hình ký và xác minh bằng khóa bất đối xứng

Với JWS sử dụng chữ ký bất đối xứng như RS256, PS256 hoặc ES256:

- Issuer giữ private key và dùng nó để ký.
- Verifier nhận public key tương ứng qua một kênh phân phối được tin cậy.
- Verifier dùng public key để xác minh chữ ký.
- Việc biết public key không cho phép verifier tạo chữ ký hợp lệ mới.

~~~mermaid
flowchart LR
    subgraph Issuer["Issuer"]
        A["Claims theo profile"] --> B["Signing policy"]
        K1["Private signing key"] --> C["JWS signer"]
        B --> C
        C --> T["JWT đã ký"]
    end
    T --> R["Client / Request"]
    R --> V["Verifier"]
    K2["Public verification key"] --> V
    P["Verifier policy"] --> V
    V --> D{"Chữ ký và claims hợp lệ?"}
    D -- Có --> E["Authenticated claims"]
    D -- Không --> X["Từ chối"]
~~~

Đây là mô hình phù hợp khi nhiều resource server cần xác minh token do một issuer phát hành. Private key chỉ nằm tại issuer hoặc dịch vụ ký chuyên trách; các verifier nhận public key.

### Vì sao không phân phối private key cho verifier?

Verifier không cần private signing key để xác minh chữ ký bất đối xứng. Nếu private key bị sao chép tới nhiều API:

- Mỗi API trở thành một nơi có thể phát hành token giả.
- Một resource server bị xâm nhập có thể làm lộ khóa ký của toàn hệ thống.
- Khó xác định thành phần nào đã tạo token trái phép.
- Thu hồi và thay thế khóa trở nên phức tạp hơn.

Nguyên tắc quyền tối thiểu là chỉ cấp private signing key cho thành phần thực sự cần ký. Verifier chỉ nhận public key và metadata cần để xác minh.

### Trường hợp HMAC

Với HS256, HS384 hoặc HS512, cùng một secret được dùng để tạo và xác minh MAC. Vì vậy, mọi verifier giữ secret đều có khả năng tạo token có MAC hợp lệ.

Điều này làm thay đổi ranh giới tin cậy:

- Không thể phân phối secret cho nhiều verifier rồi coi chúng chỉ có quyền đọc/xác minh.
- Một verifier bị xâm nhập có thể trở thành nguồn phát hành token giả.
- Nếu cần nhiều verifier độc lập và muốn giới hạn quyền phát hành, chữ ký bất đối xứng thường phù hợp hơn.

HMAC vẫn có thể phù hợp trong một trust boundary nhỏ, nơi mọi bên giữ secret đều được tin cậy ngang nhau và có quy trình quản lý khóa chặt chẽ.

### Lưu ý khi dùng JWE

JWE encryption có hướng phân phối khóa khác với JWS signature. Bên gửi mã hóa plaintext bằng public key của recipient (hoặc dùng cơ chế quản lý khóa đã thỏa thuận); recipient giữ private key/secret tương ứng để giải mã và xác minh authentication tag. Vì vậy, không lấy sơ đồ private-signing-key/public-verification-key của JWS áp dụng nguyên xi cho JWE. Một hệ thống có thể vừa ký vừa mã hóa nested JWT, khi đó phải tách riêng signing key, encryption key, recipient và các policy tương ứng.

## 4. Cấu hình bên phát hành

Issuer cần một cấu hình mô tả danh tính phát hành, token profile và khả năng ký. Cấu hình này phải được quản lý tại thành phần có quyền phát hành.

Các nhóm thông tin thường có:

| Nhóm | Thuộc tính ví dụ | Mục đích |
| --- | --- | --- |
| Issuer identity | issuer | Giá trị iss được đặt vào token |
| Token profile | token_type, typ, required_claims | Xác định loại token và schema |
| Signing algorithm | signing_algorithm | Thuật toán được phép dùng khi ký |
| Signing key | signing_key_ref, active_kid | Tham chiếu private key và định danh khóa đang hoạt động |
| Recipient | allowed_audiences | Giới hạn resource/audience mà issuer có thể cấp |
| Authorization | scope_policy, claim_policy | Quyết định quyền và claims được đưa vào token |
| Lifetime | access_token_ttl, max_lifetime | Giới hạn thời gian hiệu lực |
| Rotation | next_key, activation_time | Chuẩn bị khóa mới và lịch chuyển đổi |
| Operations | signing_timeout, audit_policy | Giới hạn vận hành và ghi nhận sự kiện |

Ví dụ cấu hình khái niệm:

~~~yaml
issuer:
  issuer_id: https://identity.example
  token_profile: oauth-access-token-v1

signing:
  algorithm: PS256
  active_kid: signing-2026-02
  key_reference: kms://identity/signing/2026-02

claims:
  required:
    - iss
    - sub
    - aud
    - iat
    - exp
    - jti

policy:
  allowed_audiences:
    - https://orders.example/
    - https://payments.example/
  max_access_token_lifetime_seconds: 600
~~~

Đây là ví dụ cấu hình ứng dụng, không phải schema chuẩn của JWT hoặc của một thư viện. URI key reference chỉ là định danh tham chiếu; quyền truy cập KMS/HSM và quy trình cấp phát khóa phải được quản lý riêng.

### Issuer phải tự quyết định claims

Không sao chép claims tùy ý từ request vào token. Issuer phải xác định subject, audience, scope và thời hạn dựa trên danh tính requester cùng authorization policy.

Ví dụ, client yêu cầu aud là Payments API không có nghĩa issuer phải cấp token cho Payments API. Issuer cần kiểm tra client có được phép yêu cầu resource đó, subject có quyền tương ứng và scope có nằm trong giới hạn được cấp hay không.

Issuer không được để caller tự cung cấp:

- iss tùy ý.
- sub của một người dùng khác.
- role/admin claim mà caller không có quyền gán.
- exp xa hơn giới hạn policy.
- kid hoặc signing algorithm để điều khiển khóa ký.
- aud/resource ngoài allowlist.

### Issuer không công bố private key

Nếu dùng JWKS, issuer chỉ công bố public JWK phù hợp để verifier xác minh. Không đưa private parameters như RSA private exponent, EC private scalar hoặc symmetric secret vào JWKS công khai.

Private key nên được giữ trong KMS/HSM hoặc kho bí mật có kiểm soát truy cập. Cấu hình chỉ nên chứa key reference, không chứa private key material trong file cấu hình thông thường.

## 5. Cấu hình bên xác minh

Verifier cần một cấu hình độc lập mô tả những issuer, khóa và token profile mà resource server chấp nhận. Không lấy chính sách tin cậy từ nội dung token.

Các nhóm thông tin thường có:

| Nhóm | Thuộc tính ví dụ | Mục đích |
| --- | --- | --- |
| Trusted issuer | trusted_issuers | Danh sách issuer được chấp nhận |
| Key source | jwks_uri, pinned_keys, trust_store | Nguồn public key đã được cấu hình tin cậy |
| Algorithm policy | allowed_algorithms | Allowlist thuật toán độc lập với token |
| Audience | expected_audience | Resource server hiện tại |
| Token profile | expected_typ, required_claims | Loại token và schema được chấp nhận |
| Time policy | clock_skew, max_token_age | Quy tắc kiểm tra thời gian |
| Key policy | accepted_kty, key_use, key_ops | Ràng buộc loại khóa và mục đích |
| Resource policy | accepted_scopes, tenant_policy | Quyền cần thiết để thực hiện thao tác |
| Cache/rotation | jwks_cache_ttl, max_stale_age | Làm mới và sử dụng public key đã xác thực |
| Input limits | max_token_bytes, max_header_bytes | Giới hạn đầu vào trước khi parse |

Ví dụ cấu hình khái niệm cho Orders API:

~~~yaml
verifier:
  profile: oauth-access-token-v1
  trusted_issuers:
    - issuer: https://identity.example
      jwks_uri: https://identity.example/.well-known/jwks.json
      allowed_algorithms:
        - PS256

  expected_audience:
    - https://orders.example/

  required_claims:
    - iss
    - sub
    - aud
    - exp
    - iat

  time_policy:
    clock_skew_seconds: 60
    max_token_age_seconds: 900

  input_limits:
    max_token_bytes: 32768
    max_header_bytes: 4096
~~~

Đây cũng là ví dụ cấu hình ứng dụng. Giá trị TTL, clock skew và kích thước chỉ mang tính minh họa; phải chọn theo token profile và yêu cầu vận hành thực tế.

### Verifier phải cấu hình audience của chính nó

Orders API cần xác minh token dành cho Orders API. Nó không nên chấp nhận mọi audience mà issuer có thể phát hành.

Nếu một token có aud là Payments API, Orders API phải từ chối token đó trừ khi profile được thiết kế rõ ràng cho nhiều recipient và API có lý do hợp lệ để chấp nhận. Việc hai API cùng tin một issuer không khiến token của API này tự động hợp lệ ở API kia.

### Verifier phải cấu hình thuật toán độc lập

Header alg là dữ liệu do token mang theo và phải được coi là chưa đáng tin cho tới khi xác minh. Verifier chọn allowlist từ cấu hình của mình, sau đó kiểm tra thuật toán token khai báo có nằm trong allowlist và tương thích với loại khóa hay không.

Không:

- Chấp nhận mọi thuật toán mà thư viện hỗ trợ.
- Chọn thuật toán chỉ dựa trên alg trong token.
- Tự chuyển sang thuật toán khác khi xác minh thất bại.
- Cho phép none trong luồng access token cần xác thực.
- Dùng một khóa với nhiều thuật toán không được policy cho phép.

## 6. Cấu hình chung và cấu hình riêng

Hai bên cần chia sẻ một số thông tin giao thức, nhưng không cần chia sẻ mọi cấu hình triển khai.

| Thông tin | Cần thống nhất? | Nơi sở hữu quyết định |
| --- | --- | --- |
| Token profile và schema claims | Có | Chủ sở hữu giao thức/issuer và resource owner |
| Issuer identifier | Có | Issuer công bố; verifier cấu hình giá trị tin cậy |
| Audience/resource identifier | Có | Resource owner định nghĩa; issuer cấp; verifier kiểm tra |
| Signing algorithm | Có | Issuer chọn theo profile; verifier đặt allowlist riêng |
| Signing key và public key tương ứng | Có quan hệ mật mã | Issuer giữ private key; verifier nhận public key |
| Access token lifetime | Issuer quyết định trong giới hạn profile | Verifier có thể áp dụng giới hạn tối đa chặt hơn |
| Clock skew | Có quy ước tương thích | Mỗi verifier cấu hình leeway trong giới hạn profile |
| JWKS URI | Verifier phải biết nguồn tin cậy | Issuer công bố; verifier pin/cấu hình theo issuer |
| Cache TTL | Không cần giống hệt | Mỗi verifier vận hành theo freshness policy |
| Log format và telemetry | Không nhất thiết | Mỗi thành phần theo chuẩn vận hành nội bộ |
| KMS/HSM key reference | Không | Issuer hoặc dịch vụ ký sở hữu |
| Authorization policy cho API | Không | Resource server sở hữu policy endpoint của mình |

Điểm quan trọng là **chia sẻ hợp đồng token, không chia sẻ bí mật và quyền vượt quá nhu cầu**. Có thể lưu token profile dưới dạng tài liệu hoặc cấu hình dùng chung đã version hóa, trong khi key material, trust anchors, audience và policy vận hành được quản lý riêng.

## 7. Không để token quyết định nguồn tin cậy

Một số JOSE Header Parameters có thể tham chiếu khóa hoặc tài nguyên:

- kid chọn một khóa trong tập khóa đã biết.
- jku tham chiếu tới JWKS URI.
- x5u tham chiếu tới chứng thư hoặc chuỗi chứng thư.
- jwk hoặc x5c mang dữ liệu khóa/chứng thư trong header.

Verifier không nên lấy URL tùy ý từ token rồi tải khóa về để xác minh chính token đó. Điều này có thể dẫn đến SSRF, tin cậy sai issuer hoặc attacker tự cung cấp khóa để ký token giả.

Quy trình an toàn:

1. Chọn issuer theo cấu hình tin cậy của ứng dụng hoặc tenant.
2. Ánh xạ issuer tới JWKS URI/trust store đã được cấu hình hoặc metadata được xác thực theo discovery policy.
3. Tải key set qua kết nối được xác minh TLS, có giới hạn response và redirect.
4. Chỉ chấp nhận public key thỏa thuật toán, loại khóa và mục đích.
5. Dùng kid để tra cứu trong key set của issuer đã tin cậy.
6. Xác minh chữ ký.
7. Sau khi xác minh, so sánh claim iss với issuer dự kiến.

Không tạo JWKS URL bằng cách nối chuỗi từ iss chưa xác minh hoặc theo jku/x5u tùy ý trong header. Với nhiều issuer, dùng registry/allowlist ánh xạ issuer đã được quản trị tới key source.

## 8. Tách cấu hình theo issuer, audience và môi trường

Một verifier có thể cần chấp nhận token từ nhiều issuer. Khi đó, mỗi issuer cần một trust configuration riêng:

~~~yaml
trusted_issuers:
  - issuer: https://identity-a.example
    jwks_uri: https://identity-a.example/keys
    allowed_algorithms: [PS256]
    audiences: [https://orders.example/]

  - issuer: https://identity-b.example
    jwks_uri: https://identity-b.example/.well-known/jwks.json
    allowed_algorithms: [ES256]
    audiences: [https://partner-orders.example/]
~~~

Đây là ví dụ minh họa. Không gộp tất cả khóa của mọi issuer thành một tập không có namespace. Một kid có thể trùng giữa hai issuer; khóa chỉ có ý nghĩa trong trust context của issuer tương ứng.

### Tách môi trường

Development, staging và production nên có:

- Issuer identifier riêng hoặc trust boundary được phân biệt rõ.
- Signing key riêng.
- JWKS/trust source riêng.
- Audience/resource identifier riêng.
- Client registration và credential riêng.
- Chính sách lifetime, scope và logging phù hợp môi trường.

Không dùng private key production để ký token test. Không để verifier production tin JWKS của development chỉ vì cùng tên kid hoặc cùng thuật toán.

### Tách token profile

Access token, ID Token, refresh token, password-reset token và service assertion có mục đích khác nhau. Verifier phải chọn đúng profile cho endpoint:

- Kiểm tra typ/token type nếu profile yêu cầu.
- Kiểm tra issuer và audience.
- Kiểm tra tập claim bắt buộc và kiểu dữ liệu.
- Kiểm tra thuật toán và khóa được phép.
- Không dùng token của một loại cho endpoint nhận token loại khác.

Một thư viện có thể hỗ trợ nhiều loại JWT, nhưng endpoint không nên dùng một cấu hình xác minh chung quá rộng cho tất cả.

## 9. Key rotation giữa issuer và verifier

Tách cấu hình giúp key rotation có thể diễn ra mà không cần phân phối private key tới verifier.

Quy trình thông thường:

1. Issuer tạo key pair mới trong KMS/HSM hoặc kho khóa an toàn.
2. Issuer công bố public key mới trong JWKS với kid mới.
3. Verifier refresh JWKS, xác thực response và nạp public key mới.
4. Issuer bắt đầu ký token mới bằng private key mới.
5. Verifier tiếp tục giữ public key cũ trong khoảng overlap để xác minh token cũ còn hiệu lực.
6. Sau khi token cũ hết hạn cộng clock-skew và khoảng vận hành cần thiết, issuer gỡ public key cũ.
7. Verifier cập nhật cache và loại bỏ khóa cũ theo freshness/revocation policy.

~~~mermaid
sequenceDiagram
    participant I as Issuer
    participant J as JWKS
    participant V as Verifier
    I->>J: Publish public key K2 (kid-2)
    V->>J: Refresh trusted JWKS
    J-->>V: K1 and K2
    V->>V: Validate and cache both public keys
    I->>I: Switch signer from K1 to K2
    I->>V: Issue tokens with kid-2
    V->>V: Verify new tokens with K2
    Note over I,V: Keep K1 during token overlap
    I->>J: Remove K1 after retirement window
    V->>J: Refresh and retire K1
~~~

### Các nguyên tắc rotation

- Dùng kid duy nhất trong phạm vi issuer và key set liên quan.
- Công bố public key mới trước khi bắt đầu ký bằng khóa mới.
- Không xóa public key cũ ngay khi issuer đổi khóa nếu token cũ vẫn còn hiệu lực.
- Không giữ khóa cũ vô thời hạn; đặt retirement deadline.
- Không để verifier chấp nhận key source hoặc algorithm mới chỉ vì response JWKS có chứa chúng.
- Khi khóa bị compromise, dùng quy trình emergency revocation; không áp dụng overlap thông thường một cách máy móc.
- Nếu cache JWKS stale, giới hạn maximum stale age và xử lý unknown kid theo policy.

## 10. Quản lý cấu hình và bí mật

### Phân loại dữ liệu cấu hình

| Loại dữ liệu | Ví dụ | Cách quản lý |
| --- | --- | --- |
| Public metadata | issuer, audience, typ, JWKS URI | Configuration store có version và review |
| Signing secret/private key | HMAC secret, RSA/EC private key | KMS/HSM hoặc secret manager; không commit vào source |
| Verification key | RSA/EC public key, public JWKS | Trust store/cache được xác thực |
| Policy | allowed algorithms, required claims, scope | Version hóa, review và kiểm thử |
| Runtime state | JWKS cache, active kid, refresh status | Cache/state store có giới hạn và quan sát |
| Environment binding | production issuer, staging audience | Cấu hình tách biệt theo môi trường |

Không đặt private key trong:

- Repository hoặc file cấu hình được commit.
- Container image hoặc package dùng chung.
- Log, trace, crash dump hoặc telemetry.
- Biến môi trường có thể bị đọc rộng nếu có secret-management phù hợp hơn.
- JWKS công khai hoặc endpoint metadata.

Ưu tiên tham chiếu tới KMS/HSM để thực hiện ký mà không xuất private key material. Nếu buộc phải nạp key material vào process, giới hạn quyền đọc, bảo vệ bộ nhớ và có quy trình rotate/revoke.

### Quyền truy cập cấu hình

- Chỉ issuer/signer được phép đọc hoặc sử dụng private signing key.
- Verifier chỉ đọc public key và verifier policy.
- Người thay đổi allowed algorithms, trusted issuers hoặc audience cần quyền quản trị riêng.
- Không để ứng dụng tự sửa trust policy theo dữ liệu nhận từ request.
- Ghi audit cho thay đổi issuer, key source, key reference, algorithm allowlist và audience.

## 11. Tích hợp với thư viện JWT

Thư viện JWT thường cung cấp các API khác nhau cho việc tạo token và xác minh token. Tên lớp/hàm tùy thư viện, nhưng cách tổ chức trách nhiệm nên tương tự:

### Phía phát hành

- Tạo signer từ signing configuration.
- Nạp hoặc tham chiếu private key từ KMS/HSM.
- Cố định thuật toán và kid theo active signing key.
- Tạo claims từ authorization decision đã được kiểm tra.
- Đặt issuer, audience, thời hạn và token type theo profile.
- Ký token và chỉ trả token cho client được phép nhận.

### Phía xác minh

- Tạo verifier/decoder từ verifier configuration.
- Nạp trusted public keys từ JWKS hoặc trust store.
- Cố định allowed algorithms độc lập với header token.
- Kiểm tra issuer, audience, token type, thời gian và required claims.
- Kiểm tra kiểu dữ liệu và giới hạn token.
- Chỉ cung cấp authenticated claims cho authorization layer sau khi mọi bước xác minh thành công.

### Không dùng một factory cấu hình quá rộng

Một factory có thể tạo cả signer và verifier, nhưng nên nhận hai kiểu cấu hình khác nhau và trả về hai capability khác nhau:

~~~text
signer = createSigner(issuerSigningConfig)
verifier = createVerifier(resourceVerifierConfig)

token = signer.issue(claims)
verifiedClaims = verifier.verify(token)
~~~

Đây là mã giả độc lập thư viện. Điểm quan trọng là resource verifier không nhận private signing key chỉ vì hai chức năng được cung cấp bởi cùng một package hoặc process.

Không dùng global default hoặc auto-configuration không rõ ràng để quyết định:

- Thuật toán ký/xác minh.
- Issuer hoặc audience.
- Nguồn khóa.
- Clock skew.
- Required claims.
- Token type.

Các giá trị ảnh hưởng bảo mật cần được cấu hình rõ, có thể kiểm tra và có test xác nhận.

## 12. Những thay đổi cấu hình cần được kiểm soát

Thay đổi issuer config và verifier config có thể tạo ra tác động khác nhau:

| Thay đổi | Tác động phía issuer | Tác động phía verifier |
| --- | --- | --- |
| Đổi signing algorithm | Token mới được ký bằng thuật toán khác | Phải cho phép thuật toán mới trước khi nhận token |
| Đổi signing key/kid | Token mới dùng khóa mới | Phải có public key mới trong trust set |
| Đổi issuer | Claim iss trong token mới thay đổi | Verifier cần trust issuer mới theo quy trình |
| Đổi audience | Token mới dành cho resource khác | Verifier phải kiểm tra audience của chính nó |
| Giảm token lifetime | Token mới hết hạn sớm hơn | Verifier vẫn áp dụng exp và giới hạn tuổi tối đa |
| Thêm required claim | Issuer phải phát hành claim | Verifier chỉ bật yêu cầu khi issuer đã triển khai tương thích |
| Thu hẹp scope policy | Token mới có ít quyền hơn | Verifier vẫn kiểm tra scope cho từng thao tác |
| Gỡ một issuer | Ngừng phát hành hoặc chuyển issuer | Verifier từ chối token từ issuer đó sau thời điểm cutover |

### Thứ tự rollout

Khi thay đổi cần cả hai bên phối hợp:

1. Công bố token profile/configuration change có version.
2. Triển khai verifier tương thích trước nếu thay đổi mở rộng có kiểm soát (ví dụ thêm public key hoặc hỗ trợ algorithm mới đã được phê duyệt).
3. Kiểm tra verifier đã nạp đúng trust data và policy.
4. Chuyển issuer sang phát hành token theo profile mới.
5. Theo dõi lỗi xác minh, token cũ và token mới.
6. Sau thời gian overlap, gỡ cấu hình cũ theo kế hoạch.

Đối với thay đổi làm giảm trust, như thu hồi issuer hoặc key bị compromise, cần quy trình khẩn cấp có thể từ chối ngay thay vì chờ rollout tương thích thông thường.

## 13. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng chung một cấu hình cho signer và verifier | Verifier có thể nhận private key hoặc policy phát hành | Tách issuer signing config và resource verifier config |
| Phân phối private key cho mọi API | API bị xâm nhập có thể phát hành token giả | Chỉ issuer/signer giữ private key; verifier nhận public key |
| Dùng HMAC secret rồi coi verifier chỉ có quyền verify | Mọi verifier giữ secret đều có thể tạo MAC hợp lệ | Dùng chữ ký bất đối xứng khi cần tách quyền phát hành |
| Để verifier chấp nhận mọi thuật toán thư viện hỗ trợ | Token có thể chọn thuật toán ngoài policy | Cấu hình allowlist độc lập |
| Dùng alg trong token để chọn policy | Attacker điều khiển lựa chọn thuật toán | So khớp alg với verifier allowlist và key policy |
| Để jku/x5u từ token quyết định nguồn khóa | SSRF hoặc tin cậy khóa do attacker cung cấp | Pin JWKS URI/trust source theo issuer |
| Dùng kid như URL hoặc đường dẫn | Injection, SSRF hoặc truy cập tài nguyên tùy ý | Chỉ dùng kid để tra cứu trong key set tin cậy |
| Chấp nhận mọi issuer do token khai báo | Token từ issuer không tin cậy có thể được chấp nhận | Dùng trusted issuer registry |
| Chấp nhận mọi audience của issuer | Token dành cho API khác có thể được dùng sai nơi | Mỗi verifier cấu hình expected audience riêng |
| Dùng chung khóa giữa dev và production | Token test có thể được chấp nhận ở production | Tách key, issuer, JWKS và audience theo môi trường |
| Đổi khóa ký trước khi public key mới được phân phối | Verifier không xác minh được token mới | Publish public key trước, rồi mới switch signer |
| Gỡ public key cũ quá sớm | Token cũ còn hạn bị từ chối ngoài kế hoạch | Duy trì overlap theo lifetime và skew |
| Giữ public key cũ vô thời hạn | Token dùng khóa đã nghỉ có thể tiếp tục được chấp nhận | Đặt retirement deadline và emergency revocation |
| Dùng một verifier profile cho ID Token và access token | Token sai mục đích có thể được chấp nhận | Tách profile và endpoint validation |
| Đổi required claims không theo rollout | Issuer và verifier không tương thích | Version hóa profile và triển khai theo thứ tự |
| Cấu hình bằng global defaults không được review | Hành vi bảo mật phụ thuộc thư viện/môi trường | Khai báo policy tường minh và test cấu hình |

## 14. Bộ ca kiểm thử

Giả sử Identity Service phát hành JWT access token ký PS256; Orders API xác minh token bằng public key từ JWKS.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Issuer dùng private key đúng, verifier có public key tương ứng, claims đúng profile | **Chấp nhận** |
| Verifier chỉ có public key và không có private signing key | Vẫn xác minh được chữ ký |
| Verifier không có private signing key trong cấu hình/secret store | Điều kiện thiết kế đúng; không phải lỗi |
| Token được ký bằng private key không thuộc trusted JWKS | **Từ chối** |
| Token có alg ngoài allowlist dù thư viện hỗ trợ | **Từ chối** |
| Token có kid không tồn tại trong JWKS của issuer | **Từ chối** sau refresh theo policy |
| Token có jku trỏ tới host do attacker kiểm soát | Không tải nguồn tùy ý; **từ chối** nếu profile không cho phép |
| Token có iss không thuộc trusted issuer registry | **Từ chối** |
| Token có iss hợp lệ nhưng aud chỉ dành cho Payments API | Orders API **từ chối** |
| Token đúng chữ ký nhưng thiếu required exp hoặc typ theo profile | **Từ chối** |
| Token có lifetime vượt giới hạn verifier | **Từ chối** theo max-token-age/lifetime policy |
| JWKS response chứa private key material | Không nạp; báo lỗi nguồn khóa |
| JWKS response không hợp lệ TLS hoặc sai host | Không cập nhật trust cache |
| Public key mới được công bố trước khi issuer dùng kid mới | Verifier refresh được key mới trước cutover |
| Token cũ ký bằng key cũ trong overlap hợp lệ | Có thể **chấp nhận** nếu key và token còn trong policy |
| Key cũ đã tới retirement deadline | **Từ chối** token cần key đó |
| Development token được gửi tới production verifier | **Từ chối** do issuer/audience/key không khớp |
| Issuer config thay đổi audience nhưng verifier chưa cho phép audience mới | Không phát hành/không chấp nhận token sai profile trong giai đoạn rollout |
| Verifier config thay đổi allowed algorithms ngoài quy trình review | Pipeline/configuration test phải phát hiện |
| HMAC secret được cấp cho một verifier | Đánh giá rằng verifier có khả năng tạo MAC; không coi là verify-only boundary |

Ngoài các ca trên, cần kiểm thử cấu hình thực tế sau mỗi lần nâng cấp thư viện. Một bản nâng cấp có thể thay đổi default algorithm, cách xử lý claim hoặc hành vi key resolver; các chính sách quan trọng phải được khóa bằng cấu hình tường minh và regression tests.

## 15. Ghi nhớ

- Issuer và verifier có trách nhiệm khác nhau: issuer quyết định phát hành/ký; verifier quyết định tin/chấp nhận.
- Tách cấu hình ký khỏi cấu hình xác minh để giảm quyền và tránh verifier giữ private signing key không cần thiết.
- Với chữ ký bất đối xứng, issuer giữ private key, verifier chỉ cần public key. Với HMAC, mọi bên giữ secret đều có thể tạo MAC hợp lệ.
- Issuer tự quyết định iss, sub, aud, scope, exp và claims theo authorization policy; không để request tự điều khiển claims bảo mật.
- Verifier cấu hình trusted issuer, key source, allowed algorithms, expected audience, token profile, required claims và time policy độc lập.
- kid chỉ chọn khóa trong tập khóa đã tin cậy; không dùng jku/x5u tùy ý từ token để tạo nguồn tin cậy.
- Tách cấu hình theo issuer, audience, token type và môi trường; không trộn key set giữa các trust boundary.
- Key rotation cần công bố public key mới trước khi ký bằng khóa mới và giữ khóa cũ trong overlap có giới hạn.
- Private key và HMAC secret phải được quản lý như bí mật; public verification key có thể phân phối nhưng vẫn cần nguồn gốc tin cậy.
- Version hóa token profile, rollout verifier/issuer có kế hoạch và kiểm thử mọi thay đổi cấu hình.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS, signing input và xác minh chữ ký.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS, public key distribution và key metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JWS/JWE và định danh thuật toán.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered claims và JWT Claims Set.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, issuer/audience validation và token confusion.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile và claims của JWT access token.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata của Authorization Server và discovery.
