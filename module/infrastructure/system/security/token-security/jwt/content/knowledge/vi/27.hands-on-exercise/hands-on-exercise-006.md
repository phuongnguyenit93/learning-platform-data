# Thiết kế JWKS cùng quy trình xoay vòng khóa

## 1. Mục tiêu bài thực hành

Trong bài thực hành này, bạn sẽ thiết kế một hệ thống phân phối public key qua JSON Web Key Set (JWKS) và xây dựng quy trình xoay vòng khóa ký JWT có thể vận hành an toàn. Bài tập đi từ yêu cầu tin cậy, thiết kế JWK/JWKS, cấu hình verifier, cache, phát hành token, planned rotation, emergency rotation đến kiểm thử và runbook.

Tình huống sử dụng:

- Một Authorization Server phát hành JWT access token.
- Billing API và Reporting API xác minh token bằng public key.
- Authorization Server ký token bằng private key được bảo vệ.
- Các resource server lấy public key từ JWKS endpoint qua HTTPS.
- Signing key cần được thay định kỳ và có khả năng thay khẩn cấp khi bị compromise.

Bạn sẽ hoàn thành các đầu ra:

1. Sơ đồ trust relationship giữa issuer, JWKS endpoint và resource servers.
2. Key inventory cùng chính sách thuật toán, key ID và trạng thái vòng đời.
3. JWKS document chỉ công bố public key cần thiết.
4. Quy tắc xác minh JWT gắn với issuer, audience, thuật toán và key ID.
5. Kế hoạch publish-before-use và thời gian overlap khi rotation.
6. Quy trình thu hồi khẩn cấp signing key bị lộ.
7. Test matrix chứng minh token cũ/mới được xử lý đúng và token không tin cậy bị từ chối.
8. Runbook và các chỉ số vận hành để theo dõi rotation.

Phạm vi là JWT Security tổng quát, không phụ thuộc ngôn ngữ lập trình hoặc framework cụ thể. Ví dụ dùng RSA với RS256 để minh họa. Hệ thống thực tế có thể chọn thuật toán khác theo chính sách mật mã, khả năng tương thích và token profile.

## 2. Bối cảnh và yêu cầu hệ thống

### 2.1. Kiến trúc giả định

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|"Ký JWT bằng private key"| T["Client nhận access token"]
    AS -->|"Publish public keys"| J["HTTPS JWKS endpoint"]
    J -->|"Fetch và cache JWKS"| B["Billing API"]
    J -->|"Fetch và cache JWKS"| R["Reporting API"]
    T -->|"Access token"| B
    T -->|"Access token"| R
    B -->|"Verify signature + claims"| P1["Billing policy"]
    R -->|"Verify signature + claims"| P2["Reporting policy"]
~~~

Authorization Server và resource servers có vai trò khác nhau:

- Authorization Server giữ private signing key và tạo chữ ký.
- JWKS endpoint công bố public key tương ứng.
- Resource server chỉ cần public key để xác minh chữ ký bất đối xứng.
- Mỗi resource server vẫn phải kiểm tra issuer, audience, thời gian, token type và quyền truy cập.

JWKS chỉ giải quyết việc phân phối key material công khai. Nó không tự xác thực JWT, không quyết định audience và không cấp quyền.

### 2.2. Yêu cầu chức năng

Hệ thống phải:

- Phát hành JWT access token có protected header chứa alg và kid.
- Công bố public key hiện hành và key kế tiếp qua JWKS.
- Cho phép verifier xác định đúng key theo issuer và kid.
- Xác minh chữ ký bằng thuật toán nằm trong allowlist.
- Hỗ trợ token được ký bởi key cũ trong giai đoạn overlap.
- Chuyển sang key mới mà không làm gián đoạn toàn bộ API.
- Loại key cũ sau khi token tương ứng không còn cần được xác minh.
- Có quy trình khẩn cấp nếu private key bị lộ.

### 2.3. Yêu cầu bảo mật

- Private key không được xuất hiện trong JWKS công khai.
- Mỗi signing key có định danh kid ổn định, duy nhất trong phạm vi issuer và không tái sử dụng.
- Key được gắn với đúng issuer, thuật toán và mục đích.
- Không lấy JWKS URL từ JWT chưa xác minh.
- Không chọn key chỉ dựa trên kid toàn cục.
- Không chấp nhận thuật toán do token tự chọn nếu thuật toán đó ngoài allowlist.
- Không bỏ qua xác minh chữ ký khi JWKS endpoint lỗi.
- Không coi việc xóa key khỏi JWKS là thu hồi tức thì ở mọi verifier đang cache key.

## 3. Xác định trust boundary

Trước khi tạo key, hãy ghi rõ các bên nào được tin và vì sao.

### 3.1. Issuer identity

Ví dụ issuer:

~~~text
https://identity.example.test
~~~

Resource server phải cấu hình issuer này từ trust registry hoặc cấu hình được quản trị. Khi JWT được xác minh, claim iss phải khớp chính xác với issuer đã chọn.

Không dùng giá trị iss chưa xác minh để tự do tạo URL metadata hoặc JWKS. Nếu hệ thống hỗ trợ nhiều issuer, mỗi issuer cần một trust record riêng, bao gồm metadata/JWKS URL đã được xác minh và policy riêng.

### 3.2. JWKS URI

Ví dụ:

~~~text
https://identity.example.test/.well-known/jwks.json
~~~

JWKS URI được lấy từ cấu hình tin cậy hoặc metadata của đúng issuer đã được xác minh. Resource server chỉ kết nối tới endpoint được phê duyệt, qua HTTPS và kiểm tra TLS certificate/hostname.

Không chấp nhận jku hoặc x5u do JWT gửi tới như một nguồn khóa tin cậy mặc định. Một token do attacker tạo có thể đặt URL tới mạng nội bộ hoặc host do attacker kiểm soát, gây SSRF hoặc key substitution.

### 3.3. Tách môi trường

Development, staging và production phải có issuer, key set và trust configuration riêng. Không dùng chung private signing key giữa các môi trường.

Ví dụ:

| Môi trường | Issuer | Key namespace |
| --- | --- | --- |
| Development | https://id.dev.example.test | dev-signing-* |
| Staging | https://id.staging.example.test | staging-signing-* |
| Production | https://identity.example.test | prod-signing-* |

Resource server production chỉ tin issuer và key set production đã được phê duyệt.

## 4. Thiết kế key inventory

Key inventory là danh sách có thẩm quyền về các khóa, mục đích, chủ sở hữu, trạng thái và lịch vòng đời. JWKS là bản công bố public key, không thay thế inventory quản trị.

### 4.1. Trường thông tin cần quản lý

| Trường | Ý nghĩa |
| --- | --- |
| issuer | Issuer sở hữu key set. |
| kid | Key ID được đưa vào JWT header. |
| kty | Loại khóa, ví dụ RSA hoặc EC. |
| alg | Thuật toán ký được phép với key. |
| use/key_ops | Mục đích hoặc thao tác được phép của key. |
| created_at | Thời điểm tạo key. |
| publish_at | Thời điểm public key được công bố. |
| signing_start_at | Thời điểm bắt đầu ký bằng key. |
| signing_stop_at | Thời điểm ngừng ký token mới. |
| verify_until | Thời điểm kết thúc nhu cầu xác minh token cũ. |
| status | planned, published, active_signing, verify_only, retired hoặc compromised. |
| owner | Nhóm chịu trách nhiệm vận hành. |
| storage_reference | Tham chiếu tới HSM/KMS/secret store; không lưu private key trực tiếp trong inventory. |

### 4.2. Trạng thái vòng đời

| Trạng thái | Có được ký token mới? | Có được xác minh token cũ? | Có publish public key? |
| --- | --- | --- | --- |
| planned | Không | Không | Chưa |
| published | Chưa | Có thể chuẩn bị verifier | Có |
| active_signing | Có | Có | Có |
| verify_only | Không | Có | Có |
| retired | Không | Không còn cần thiết | Không |
| compromised | Tuyệt đối không | Theo emergency policy, thường phải từ chối | Thường loại khỏi JWKS và áp dụng deny propagation |

Trạng thái verify_only rất quan trọng trong planned rotation: private key không còn được dùng để ký token mới, nhưng public key vẫn cần được publish để xác minh access token đã phát hành trước đó.

### 4.3. Không tái sử dụng kid

kid là định danh key, không phải số phiên bản có thể quay vòng tùy tiện. Không tái sử dụng kid cũ cho key material mới. Nếu cùng kid được gắn với key khác nhau giữa cache và issuer, verifier có thể chọn sai key hoặc tạo hành vi không nhất quán.

Đặt kid duy nhất trong phạm vi issuer, có thể gắn với ngày/tháng hoặc mã version. Không đưa bí mật, thông tin cá nhân hoặc chi tiết nội bộ nhạy cảm vào kid.

## 5. Chọn thuật toán và tạo key pair

### 5.1. Ví dụ dùng RSA và RS256

Trong lab này, chọn:

~~~text
Key type: RSA
Signature algorithm: RS256
Illustrative modulus size: 3072 bits
Public exponent: 65537
~~~

Kích thước 3072 bit là lựa chọn minh họa theo policy lab, không phải yêu cầu phổ quát cho mọi hệ thống. RFC 7518 yêu cầu RSA key tối thiểu 2048 bit cho các thuật toán RSA JWA liên quan. Tổ chức cần áp dụng chính sách mật mã hiện hành và cân bằng mức an toàn, hiệu năng, tương thích.

### 5.2. Tạo private key trong môi trường lab

Nếu dùng OpenSSL để tạo fixture RSA cho môi trường thực hành cô lập:

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out signing-current-private.pem
openssl pkey -in signing-current-private.pem -pubout -out signing-current-public.pem
~~~

Tạo key kế tiếp bằng một lần sinh key độc lập, với tên và kid khác. Không sao chép private key hiện tại để làm key kế tiếp.

Các file trong ví dụ chỉ dùng cho lab. Production nên giữ private key trong HSM, KMS hoặc hệ thống quản lý khóa có kiểm soát truy cập, audit, backup và quy trình khôi phục phù hợp.

### 5.3. Quy tắc bảo vệ private key

- Chỉ thành phần issuer được cấp quyền ký mới có quyền sử dụng private key.
- Resource server không cần private signing key.
- Không publish private key trong JWKS.
- Không commit PEM, JWK private hoặc secret vào source control.
- Không ghi key material vào log, trace, crash dump hoặc ticket.
- Hạn chế export private key; ưu tiên thao tác ký trong HSM/KMS nếu kiến trúc hỗ trợ.
- Phân tách quyền tạo key, phê duyệt rotation và sử dụng key.
- Audit thao tác ký, rotate, disable và revoke.

### 5.4. Một key, một thuật toán và một mục đích

Gắn mỗi key với một thuật toán theo policy. Không dùng cùng key tùy tiện cho nhiều thuật toán hoặc mục đích khác nhau. Signing key và encryption key nên tách biệt.

Nếu cần chuyển từ RS256 sang PS256 hoặc ES256, tạo key phù hợp với thuật toán mới và kid mới. Không chỉ đổi giá trị alg trong header rồi tiếp tục dùng key cũ mà không đánh giá tương thích và policy.

## 6. Chuyển public key sang JWK

JWKS là JSON object có member keys chứa một mảng JSON Web Key. Mỗi JWK biểu diễn một khóa. Với RSA public key, các tham số chính là:

- kty: RSA.
- n: modulus ở dạng Base64URLUInt.
- e: public exponent ở dạng Base64URLUInt.
- kid: định danh key.
- alg: thuật toán liên quan nếu policy công bố trường này.
- use: sig nếu dùng cho chữ ký, hoặc key_ops có verify theo quy tắc JWK.

Không tự tạo JWK bằng cách cắt chuỗi PEM hoặc Base64-encode toàn bộ file. Dùng công cụ hoặc thư viện JOSE/JWK được kiểm chứng để chuyển public key thành JWK đúng chuẩn.

### 6.1. JWK public mẫu

~~~json
{
  "kty": "RSA",
  "kid": "prod-signing-2026-11-a",
  "use": "sig",
  "alg": "RS256",
  "n": "base64url-encoded-rsa-modulus",
  "e": "AQAB"
}
~~~

Các giá trị n trong ví dụ là placeholder, không phải key có thể xác minh chữ ký. e = AQAB là biểu diễn Base64URL phổ biến của số nguyên 65537.

### 6.2. Không công bố private parameters

RSA private JWK có thể chứa các tham số như d, p, q, dp, dq, qi và các tham số CRT khác. Những trường này không được xuất hiện trong JWKS công khai.

Đối với EC private JWK, không công bố tham số d. Chỉ công bố các thành phần public cần thiết theo loại khóa.

Trước khi publish, có bước kiểm tra tự động bảo đảm JWKS không chứa private key material.

### 6.3. use và key_ops

JWK có thể dùng use để mô tả mục đích, ví dụ sig; hoặc key_ops để liệt kê thao tác được phép, ví dụ verify cho public key. RFC 7517 khuyến nghị không đồng thời dùng cả use và key_ops; nếu cả hai cùng xuất hiện thì chúng phải nhất quán.

Trong lab, chọn use = sig cho JWK public để đơn giản. Nếu tổ chức dùng key_ops, hãy công bố verify và không có thao tác sign trên public JWK.

### 6.4. Kiểm tra JWK trước khi publish

Xác minh:

- JSON hợp lệ và có đúng loại member.
- kty tương thích với thuật toán.
- kid duy nhất trong key set theo policy.
- alg nằm trong allowlist nếu trường alg được công bố.
- use/key_ops đúng mục đích.
- RSA modulus và exponent hợp lệ.
- Không có private parameters.
- Không có key trùng hoặc mơ hồ.
- Public key có thể xác minh một test signature đã tạo bằng private key tương ứng.

## 7. Xây dựng JWKS document

### 7.1. JWKS với một signing key hiện hành

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "prod-signing-2026-11-a",
      "use": "sig",
      "alg": "RS256",
      "n": "current-public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

### 7.2. JWKS trong giai đoạn overlap

Khi chuẩn bị rotation, publish public key mới trước khi issuer bắt đầu ký token bằng key mới:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "prod-signing-2026-11-a",
      "use": "sig",
      "alg": "RS256",
      "n": "old-public-modulus",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "prod-signing-2027-02-b",
      "use": "sig",
      "alg": "RS256",
      "n": "new-public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Resource server có thể xác minh token cũ bằng key A và token mới bằng key B trong thời gian overlap. Cả hai public key đều phải thuộc cùng issuer đã được tin cậy và được áp dụng theo đúng algorithm policy.

### 7.3. JWKS không phải danh sách key tùy ý

Không publish:

- Key của issuer khác.
- Key thử nghiệm trong production.
- Private key material.
- Key không còn cần thiết.
- Key encryption trong endpoint chỉ phục vụ signature verification nếu profile không yêu cầu.
- Nhiều key trùng kid gây nhập nhằng.

Nếu issuer hỗ trợ nhiều mục đích key, phải xác định rõ consumer và key usage; không để resource server tự chọn key bất kỳ.

## 8. Cấu hình JWKS endpoint và metadata

### 8.1. Endpoint ổn định

Ví dụ:

~~~text
GET https://identity.example.test/.well-known/jwks.json
~~~

Endpoint phải:

- Dùng HTTPS.
- Có hostname ổn định theo issuer.
- Trả JSON JWKS theo schema.
- Không yêu cầu client gửi token người dùng để tải public key.
- Không trả private material.
- Có availability và capacity phù hợp với số verifier.
- Có cache header và cơ chế cập nhật rõ ràng.

### 8.2. Discovery metadata

Authorization Server metadata có thể công bố jwks_uri. Resource server lấy metadata qua trust bootstrap của issuer, sau đó kiểm tra issuer trong metadata khớp chính xác issuer đã cấu hình.

Không tin metadata chỉ vì nó được tải từ URL nằm trong token. Issuer và metadata endpoint phải được xác định từ trust registry hoặc quy trình onboarding đã phê duyệt.

### 8.3. HTTP cache

JWKS endpoint có thể sử dụng HTTP caching:

- Cache-Control với max-age phù hợp.
- ETag để verifier dùng conditional GET.
- Last-Modified nếu hạ tầng hỗ trợ.
- Response body ổn định khi key set không thay đổi.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/jwk-set+json
Cache-Control: public, max-age=300
ETag: "jwks-version-42"
~~~

Ví dụ trên minh họa một chính sách cache 5 phút; con số thực tế phải dựa trên khả năng phân phối key, tần suất rotation và yêu cầu incident response.

Khi JWKS không thay đổi, server có thể trả 304 Not Modified cho request conditional hợp lệ. Verifier phải cập nhật freshness theo HTTP cache semantics, không tự kéo dài stale vô hạn.

### 8.4. Cache không thay thế trust validation

Verifier chỉ cache JWKS lấy từ issuer đã được tin cậy và qua HTTPS/TLS validation. Cache key phải namespace theo issuer và JWKS URI đã xác minh, không chỉ theo kid.

Nếu cache bị lỗi, sai issuer hoặc quá hạn ngoài stale policy, không dùng key để chấp nhận token. Emergency deny/revocation cần cơ chế vượt qua cache thông thường.

## 9. Quy trình xác minh JWT bằng JWKS

Một resource server xác minh JWT theo thứ tự khái quát:

1. Endpoint xác định token profile cần nhận.
2. Chọn issuer từ trust configuration.
3. Parse compact JWT và đọc JOSE header như dữ liệu chưa tin cậy.
4. Kiểm tra alg thuộc allowlist của profile.
5. Đọc kid để chọn ứng viên trong JWKS gắn với issuer.
6. Nếu không tìm thấy kid, thực hiện một lần refresh có giới hạn theo policy.
7. Kiểm tra JWK có key type, use/key_ops và alg tương thích.
8. Xác minh chữ ký bằng public key.
9. Sau khi chữ ký hợp lệ, kiểm tra iss, aud, exp, nbf, iat và claims theo profile.
10. Kiểm tra revocation/sender binding nếu kiến trúc yêu cầu.
11. Thực hiện authorization theo scope, tenant, resource và action.

### 9.1. kid chỉ là key selector

kid không chứng minh issuer và không chứng minh chữ ký hợp lệ. Nếu kid không có trong JWKS của issuer đã chọn, từ chối sau refresh được phép. Không tìm key cùng kid trong JWKS của issuer khác.

### 9.2. Unknown-kid refresh

Một token có kid lạ có thể là token mới sau rotation hoặc token giả mạo. Verifier có thể refresh JWKS theo policy, nhưng cần:

- Single-flight để nhiều request cùng kid không tạo nhiều refresh.
- Rate limit cho refresh.
- Negative cache ngắn có kiểm soát.
- Timeout và giới hạn response size.
- Không fetch URL do token cung cấp.
- Không fallback sang key bất kỳ.

Nếu refresh thành công mà kid vẫn không tồn tại, từ chối token. Nếu endpoint không truy cập được và không có key tin cậy trong cache, từ chối vì không thể xác minh chữ ký.

### 9.3. Pseudocode xác minh

~~~text
function verifyAccessToken(token, endpointPolicy):
    issuer = endpointPolicy.trustedIssuer
    profile = endpointPolicy.tokenProfile

    header = parseUntrustedHeader(token)
    if header.alg not in profile.allowedAlgorithms:
        return REJECT

    key = jwksCache.find(
        issuer = issuer,
        kid = header.kid,
        algorithm = header.alg
    )

    if key is missing:
        refreshTrustedJwksSingleFlight(issuer)
        key = jwksCache.find(issuer, header.kid, header.alg)

    if key is missing:
        return REJECT_KEY_NOT_FOUND

    if not keyMatchesPolicy(key, profile, header.alg):
        return REJECT

    if not verifyJwsSignature(token, key, header.alg):
        return REJECT_SIGNATURE_INVALID

    claims = readVerifiedClaims(token)
    if claims.iss != issuer:
        return REJECT
    if not audienceMatches(claims.aud, endpointPolicy.expectedAudience):
        return REJECT
    if not requiredClaimsAndTimeAreValid(claims, profile):
        return REJECT

    return VERIFIED_TOKEN(claims)
~~~

Đây là pseudocode mô tả quy trình, không phải API của một thư viện cụ thể. Các kiểm tra profile đầy đủ phải tuân theo chuẩn token mà hệ thống sử dụng.

## 10. Lập kế hoạch planned key rotation

Planned rotation là thay signing key theo lịch, trong khi token cũ vẫn còn hiệu lực và các verifier vẫn phải xác minh được token hợp lệ.

### 10.1. Nguyên tắc publish-before-use

Trình tự an toàn:

~~~text
Tạo key B
   |
   v
Publish public key B vào JWKS
   |
   v
Đợi verifier có cơ hội refresh/cache key B
   |
   v
Issuer bắt đầu ký token mới bằng private key B
   |
   v
Ngừng ký token mới bằng private key A
   |
   v
Giữ public key A trong JWKS để xác minh token cũ
   |
   v
Token ký bằng A hết hạn + clock skew
   |
   v
Loại public key A khỏi JWKS và retire key
~~~

Không bắt đầu ký bằng key B trước khi public key B được publish và có đủ thời gian phân phối tới verifier. Nếu không, token mới có thể tới resource server chưa biết key B.

### 10.2. Các giai đoạn rotation

| Giai đoạn | Key A | Key B | JWKS |
| --- | --- | --- | --- |
| Stable | active_signing | planned | Chỉ A |
| Pre-publish | active_signing | published | A + B |
| Cutover | verify_only | active_signing | A + B |
| Overlap | verify_only | active_signing | A + B |
| Retire A | retired | active_signing | Chỉ B |

Giai đoạn pre-publish và overlap có mục đích khác nhau. Pre-publish cho verifier biết key mới trước khi token mới xuất hiện; overlap cho phép token ký bằng cả key cũ và key mới được xác minh.

### 10.3. Tính thời gian overlap

Thời gian giữ public key cũ phải đủ để xác minh mọi token còn hợp lệ được ký bằng key cũ.

Một cách lập kế hoạch bảo thủ:

\[
T_{overlap} \geq T_{max\_token\_lifetime}
 + T_{clock\_skew}
 + T_{distribution\_margin}
 + T_{operational\_margin}
\]

Trong đó:

- T_max_token_lifetime: thời hạn access token dài nhất được ký bằng key A.
- T_clock_skew: leeway thời gian mà verifier cho phép.
- T_distribution_margin: thời gian cần để JWKS cập nhật và verifier refresh.
- T_operational_margin: biên dự phòng cho rollout, queue và sự cố triển khai.

Đây là cách ước lượng vận hành, không phải công thức chuẩn bắt buộc. Cần tính từ thời điểm issuer ngừng ký bằng A và exp lớn nhất của token đã phát hành bằng A. Public key A chỉ được loại sau khi mọi token hợp lệ dùng A đã hết hạn theo time policy và các verifier có thể cập nhật key set.

Ví dụ giả định:

| Tham số | Giá trị |
| --- | ---: |
| Access token lifetime tối đa | 15 phút |
| Clock skew | 30 giây |
| JWKS propagation/refresh margin | 5 phút |
| Operational margin | 5 phút |
| Overlap planning tối thiểu | 25 phút 30 giây |

Trong thực tế, nếu token được phát hành ngay trước cutover có exp muộn hơn dự kiến, hãy dùng exp lớn nhất quan sát/được bảo đảm thay vì chỉ dựa vào TTL danh nghĩa. Cũng phải xét cache stale được phép và thời gian triển khai tất cả verifier.

### 10.4. Bảng lịch rotation minh họa

Giả sử key A ngừng ký lúc 10:00 UTC và token có thể sống tối đa 15 phút:

| Thời điểm | Hành động |
| --- | --- |
| 09:30 | Tạo key B và kiểm tra public/private pair. |
| 09:35 | Publish B cùng A lên JWKS. |
| 09:35–10:00 | Xác nhận các verifier có thể lấy B qua cache refresh/synthetic test. |
| 10:00 | Issuer chuyển sang ký token mới bằng B. |
| 10:00 | Đánh dấu A là verify_only; không ký token mới bằng A. |
| Sau exp lớn nhất của token A + skew và margin | Xác nhận không còn token hợp lệ cần A. |
| Sau xác nhận | Xóa A khỏi JWKS và retire private key theo retention policy. |

Thời gian cụ thể chỉ là ví dụ. Không xóa A chỉ vì đã qua một khoảng thời gian cố định nếu token lifetime thực tế hoặc clock policy dài hơn.

## 11. Triển khai rotation từng bước

### Bước 1: Kiểm kê và xác nhận trạng thái hiện tại

Ghi nhận:

- Issuer và JWKS URI.
- kid đang ký token.
- Thuật toán và key type.
- Token lifetime tối đa.
- Clock skew của các verifier.
- Cache TTL/stale policy.
- Danh sách resource server/region cần cập nhật.
- Ngày dự kiến rotation và người phê duyệt.

Xác minh key hiện tại chưa bị compromise và có thể tiếp tục dùng trong giai đoạn chuyển đổi.

### Bước 2: Tạo key mới

Tạo key pair B bằng quy trình được phê duyệt. Gán kid mới chưa từng dùng. Lưu private key vào HSM/KMS/secret store. Xuất public key và chuyển thành JWK.

Kiểm tra public key B có thể xác minh một test signature tạo bởi private key B. Không đưa private key vào JWKS hoặc artifact review.

### Bước 3: Publish public key mới

Cập nhật JWKS để chứa cả A và B. Giữ nguyên key A đang hoạt động. Kiểm tra response:

- JSON hợp lệ.
- Có cả hai kid dự kiến.
- Không có private parameters.
- Content-Type đúng.
- TLS certificate hợp lệ.
- ETag/cache headers phù hợp.

### Bước 4: Phân phối và xác nhận verifier

Dùng synthetic token ký bằng B trong môi trường kiểm soát hoặc một test endpoint để xác minh các resource server đã lấy được public key B.

Không cần phát hành token người dùng thật chỉ để kiểm tra key distribution. Theo dõi cache refresh, unknown kid và key lookup result trên từng region.

### Bước 5: Chuyển issuer sang key B

Thay signing key active tại issuer. Đảm bảo header token mới chứa kid B và alg đúng policy. Gửi test token tới từng resource server.

Không thay đồng thời issuer, audience, thuật toán và key nếu không cần thiết; thay đổi từng nhóm giúp khoanh vùng lỗi.

### Bước 6: Chuyển A sang verify_only

Issuer không ký token mới bằng A. Public key A tiếp tục ở JWKS để resource server xác minh token cũ còn hạn.

Ghi thời điểm token cuối cùng được ký bằng A và exp lớn nhất có thể phát hành. Đây là cơ sở xác định thời điểm an toàn để retire A.

### Bước 7: Kết thúc overlap

Khi mọi token ký bằng A đã hết hạn theo clock policy và margin, kiểm tra:

- Không còn token hợp lệ được phát hành bằng A.
- Không còn client hoặc issuer instance ký bằng A.
- Các verifier đã cập nhật JWKS.
- Không còn phụ thuộc rollback cần giữ A.

Sau đó loại A khỏi JWKS và retire private key theo chính sách lưu trữ/tiêu hủy.

### Bước 8: Xác minh sau rotation

Kiểm thử:

- Token mới ký bằng B được chấp nhận.
- Token cũ ký bằng A được xử lý theo thời gian còn hiệu lực.
- Token hết hạn ký bằng A bị từ chối.
- Token dùng kid không tồn tại bị từ chối.
- Token sai issuer/audience/algorithm bị từ chối.
- Không có private key material trong JWKS.

## 12. Rollback trong planned rotation

Rollback chỉ an toàn nếu key A chưa bị compromise và vẫn nằm trong trust policy.

Nếu issuer chuyển sang B nhưng phát hiện lỗi:

1. Dừng cutover nếu chưa hoàn tất.
2. Xác định lỗi nằm ở issuer signing, JWKS publication, cache hay verifier.
3. Nếu cần quay lại A, xác nhận private key A còn an toàn và được phép sử dụng.
4. Đảm bảo public key A vẫn có trong JWKS của issuer.
5. Chuyển issuer signing về A theo phê duyệt.
6. Giữ public key B trong JWKS nếu đã có token ký bằng B còn hạn.
7. Không xóa B cho đến khi token ký bằng B hết hạn theo policy.
8. Lập lịch rotation mới sau khi khắc phục nguyên nhân.

Không rollback về một private key đã bị nghi compromise. Khi key bị lộ, xử lý như emergency rotation chứ không phải rollback bình thường.

## 13. Emergency rotation khi private key bị compromise

Emergency rotation có mục tiêu ngăn key bị lộ tiếp tục được dùng để ký token giả. Nó khác planned rotation vì ưu tiên containment và có thể gây từ chối một số token hợp lệ đang còn hạn.

### 13.1. Dấu hiệu compromise

- Private key xuất hiện trong log, repository hoặc artifact công khai.
- HSM/KMS audit ghi nhận thao tác ký bất thường.
- Có token không giải thích được được ký bằng kid hiện tại.
- Secret store hoặc máy chủ issuer bị xâm nhập.
- Người không có quyền truy cập được private key.
- Signing operation tăng đột biến hoặc đến từ workload lạ.

### 13.2. Quy trình containment

1. Kích hoạt incident response và xác định kid bị ảnh hưởng.
2. Dừng mọi signing operation bằng private key bị compromise.
3. Disable hoặc revoke key trong HSM/KMS/secret store theo quy trình.
4. Tạo key pair khẩn cấp mới với kid mới.
5. Publish public key mới qua JWKS đã xác thực.
6. Phân phối emergency deny cho kid bị compromise tới mọi verifier.
7. Làm mới hoặc invalidate cache theo cơ chế khẩn cấp.
8. Thu hồi grant/session/refresh token liên quan nếu threat model yêu cầu.
9. Đánh giá access token đã phát hành bằng key bị lộ.
10. Kiểm tra log/audit để xác định token giả và phạm vi ảnh hưởng.
11. Theo dõi verifier acceptance và unknown kid/signature failure sau containment.
12. Ghi lại timeline, quyết định và bằng chứng.

### 13.3. Xóa key khỏi JWKS không đủ để thu hồi tức thì

Resource server có thể đã cache public key bị compromise. Nếu chỉ xóa key khỏi JWKS, verifier chưa refresh vẫn có thể tiếp tục xác minh chữ ký do attacker tạo bằng private key bị lộ.

Vì vậy cần một cơ chế emergency deny/invalid key có thể truyền tới verifier nhanh hơn cache TTL thông thường, ví dụ:

- Denylist kid theo issuer.
- Cache invalidation/push event có xác thực.
- Configuration update khẩn cấp.
- Restart/reload có kiểm soát nếu kiến trúc yêu cầu.
- Introspection hoặc trạng thái online cho các luồng cần thu hồi nhanh.
- Access token TTL ngắn và revoke grant/session để giới hạn ảnh hưởng.

Nếu verifier offline và không nhận được tín hiệu revoke, không thể tuyên bố key bị compromise đã bị vô hiệu hóa tức thì trên mọi nơi. Phải đo propagation và xác nhận từng verifier.

### 13.4. Ảnh hưởng tới token đã phát hành

Token hợp lệ về chữ ký trước thời điểm compromise có thể vẫn còn hạn. Token do attacker tạo sau khi lấy private key cũng có thể có chữ ký hợp lệ về mặt mật mã.

Emergency deny theo kid có thể từ chối cả token hợp lệ cũ và token giả mới cùng dùng kid đó. Đây là trade-off containment cần được chấp nhận và truyền thông trong incident.

Nếu chỉ dùng JWT offline, thu hồi tức thì theo từng token khó thực hiện nếu không có denylist, introspection hoặc một trạng thái online khác. JWKS chỉ phân phối public key; nó không phải hệ thống revocation đầy đủ.

## 14. Cache, refresh và tính nhất quán giữa nhiều verifier

### 14.1. Cache theo issuer và JWKS URI

Cache key nên gắn với issuer và nguồn JWKS đã xác minh. Không dùng kid làm khóa cache duy nhất vì nhiều issuer có thể dùng cùng kid.

### 14.2. Refresh khi unknown kid

Khi nhận kid chưa biết:

1. Kiểm tra JWKS cache hiện tại.
2. Nếu chưa tìm thấy, kiểm tra negative cache/rate limit.
3. Thực hiện một lần refresh có kiểm soát.
4. Parse và validate JWKS response.
5. Cập nhật cache atomically nếu response hợp lệ.
6. Tìm lại kid.
7. Nếu vẫn không có, từ chối.

Không để nhiều request đồng thời tạo hàng loạt JWKS fetch. Dùng single-flight hoặc cơ chế tương đương.

### 14.3. Không ghi đè cache tốt bằng response lỗi

Nếu JWKS endpoint trả 500 hoặc JSON malformed, không thay cache hợp lệ bằng một key set rỗng hoặc lỗi. Giữ cache cũ chỉ trong freshness/stale policy đã phê duyệt. Nếu policy không cho phép dùng stale key, từ chối khi không thể xác minh.

### 14.4. Đồng bộ nhiều region

Mỗi region cần quan sát:

- JWKS version/ETag đã tải.
- Cache freshness.
- Thời điểm refresh thành công cuối.
- Key ID hiện có.
- Emergency deny version.
- Verifier software/configuration version.

Không đánh dấu rotation hoàn tất chỉ vì một region đã nhận key mới. Phải có xác nhận từ tất cả verifier nằm trong phạm vi phục vụ token.

## 15. Kiểm thử JWKS và key rotation

### 15.1. Test JWK/JWKS schema

- JWKS có member keys là array.
- JWK có kty, kid và tham số public bắt buộc.
- kid duy nhất theo policy.
- alg/use/key_ops tương thích.
- Không có RSA private parameters.
- Không có EC private parameter d.
- Public key xác minh được test signature tương ứng.
- JWKS malformed hoặc duplicate kid bị từ chối theo policy.

### 15.2. Test key selection và trust

- JWT có kid hiện tại và chữ ký đúng.
- JWT có kid kế tiếp sau khi pre-publish.
- JWT có kid không tồn tại.
- Hai issuer có cùng kid nhưng key khác nhau.
- JWT có alg ngoài allowlist.
- JWK có key type hoặc use không phù hợp.
- JWT có jku/x5u trỏ tới URL không tin cậy.
- Issuer trong token không khớp trust configuration.

### 15.3. Test planned rotation

| Test | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| R-01 | JWKS chỉ có A, token ký A | Accept nếu token/claims hợp lệ. |
| R-02 | JWKS có A+B, token ký A | Accept trong overlap. |
| R-03 | JWKS có A+B, token ký B | Accept sau khi verifier nhận B. |
| R-04 | Issuer bắt đầu ký B trước khi publish B | Test phải phát hiện verifier chưa có key và rotation gate không cho cutover. |
| R-05 | Token ký A còn hạn sau cutover | Accept trong overlap nếu không có emergency deny. |
| R-06 | Token ký A đã hết hạn | Reject. |
| R-07 | A đã retire khỏi JWKS và token A hết hạn | Không còn nhu cầu xác minh A. |
| R-08 | Token dùng kid ngẫu nhiên | Reject; refresh có rate limit. |

### 15.4. Test emergency rotation

- Private key bị compromise được disable.
- Issuer không còn ký bằng kid cũ.
- Emergency deny tới mọi verifier.
- Verifier có cache cũ vẫn từ chối kid bị deny.
- Token ký bằng key mới được chấp nhận sau khi public key mới được phân phối.
- Token cũ hợp lệ nhưng dùng kid bị deny bị từ chối theo containment policy.
- JWKS outage không làm verifier bỏ qua denylist.
- Audit ghi nhận người phê duyệt, thời điểm và trạng thái propagation.

### 15.5. Test cache và dependency

- JWKS endpoint timeout.
- JWKS trả 304 Not Modified.
- JWKS ETag thay đổi sau publish key mới.
- TLS certificate endpoint sai hoặc hết hạn.
- DNS lỗi hoặc redirect ngoài allowlist.
- Cache stale quá giới hạn.
- Hai request đồng thời cùng gặp unknown kid.
- Một region refresh thành công, region khác thất bại.
- Emergency invalidation xảy ra khi verifier đang xử lý request.

### 15.6. Test không rò rỉ private key

Kiểm tra:

- Public JWKS response.
- Metadata endpoint.
- Application logs.
- Traces và metrics.
- Error reports.
- CI artifacts.
- Backup/export của key store.

Không được có private key material hoặc secret trong các nơi công khai/không được phép.

## 16. Chỉ số và cảnh báo vận hành

Rotation cần được quan sát như một thay đổi có trạng thái.

### 16.1. Metric đề xuất

~~~text
jwks_refresh_total{issuer_alias, outcome}
jwks_refresh_duration_seconds
jwks_cache_events_total{issuer_alias, result}
jwt_key_lookup_total{issuer_alias, result}
jwt_key_not_found_total{issuer_alias, profile}
jwt_signature_verifications_total{issuer_alias, outcome, algorithm}
jwt_unknown_kid_refresh_limited_total{issuer_alias}
jwt_emergency_key_deny_total{issuer_alias, outcome}
~~~

Giá trị label phải hữu hạn. Không đưa raw kid, raw token, subject hoặc issuer URL tùy ý vào metric labels.

### 16.2. Alert cần có

- JWKS refresh failure tăng.
- Key not found tăng sau khi issuer bắt đầu ký bằng key mới.
- Signature invalid tăng đột biến sau rotation.
- Verifier chưa nhận key mới trước cutover deadline.
- Cache stale vượt policy.
- Unknown-kid refresh bị rate limit tăng bất thường.
- Emergency deny propagation chưa hoàn tất.
- Public JWKS có key không mong đợi hoặc có dấu hiệu chứa private parameters.

### 16.3. Synthetic verification

Có thể phát hành test token riêng được ký bằng key mới, audience dành cho một endpoint kiểm thử và scope không có quyền nghiệp vụ. Gửi token tới các verifier/canary để xác nhận key distribution mà không dùng token production có quyền rộng.

Không dùng synthetic token có quyền truy cập dữ liệu thật.

## 17. Runbook planned rotation

### Trước rotation

1. Xác nhận issuer, key hiện tại, kid và thuật toán.
2. Tính token lifetime tối đa, clock skew, cache freshness/stale và distribution margin.
3. Tạo key mới và kiểm tra public/private pair.
4. Gán kid mới chưa từng dùng.
5. Publish public key mới vào JWKS cùng key cũ.
6. Kiểm tra response, TLS, ETag và cache header.
7. Xác nhận mọi verifier/region đã nhận key mới.
8. Chỉ phê duyệt cutover khi synthetic verification thành công.

### Trong rotation

1. Chuyển issuer sang ký bằng key mới.
2. Xác minh token mới có kid mới.
3. Xác minh resource servers chấp nhận token mới.
4. Theo dõi signature invalid, key not found và JWKS refresh.
5. Đánh dấu key cũ verify_only.
6. Ghi exp lớn nhất của token cuối cùng được ký bằng key cũ.

### Sau rotation

1. Chờ tới thời điểm hết hạn cuối cùng cộng clock skew và margin đã tính.
2. Xác nhận không còn issuer instance ký bằng key cũ.
3. Xác nhận verifier đã cập nhật JWKS.
4. Loại key cũ khỏi JWKS.
5. Retire private key theo policy.
6. Lưu audit record và kết quả kiểm thử.

## 18. Runbook emergency key compromise

1. Xác nhận phạm vi compromise và kid bị ảnh hưởng.
2. Dừng signing bằng private key bị lộ.
3. Disable key tại HSM/KMS hoặc secret store.
4. Tạo key mới với kid mới.
5. Publish public key mới và kiểm tra distribution.
6. Phát emergency deny cho kid cũ tới tất cả verifier.
7. Invalidate cache hoặc buộc refresh theo cơ chế khẩn cấp.
8. Thu hồi grant/session/refresh token theo threat model.
9. Đánh giá token đã phát hành và dữ liệu có thể đã bị truy cập.
10. Kiểm tra synthetic token mới và xác nhận token dùng kid cũ bị từ chối.
11. Theo dõi propagation, signature failures và verifier availability.
12. Ghi timeline, bằng chứng và quyết định containment.

Không chờ hết token lifetime mới xử lý key compromise. Planned overlap không áp dụng cho private key đã bị lộ.

## 19. Bài tập thực hành theo giai đoạn

Thực hiện các nhiệm vụ sau trong môi trường lab:

### Nhiệm vụ A: Thiết kế trust model

- Xác định issuer và JWKS URI.
- Xác định Billing API và Reporting API có audience nào.
- Xác định resource server nào được phép tải JWKS.
- Tách trust configuration cho dev, staging và production.
- Vẽ sơ đồ luồng ký, publish, fetch và verify.

### Nhiệm vụ B: Tạo key inventory

- Tạo key A và key B bằng hai lần sinh độc lập.
- Ghi kty, alg, kid, owner, storage reference và trạng thái.
- Xác định quyền ai được ký, ai được publish và ai được approve rotation.
- Định nghĩa thời điểm planned rotation và emergency revoke.

### Nhiệm vụ C: Tạo JWKS

- Chuyển public key A thành JWK.
- Tạo JWKS chỉ chứa A.
- Kiểm tra không có private parameters.
- Publish trên HTTPS endpoint trong lab.
- Xác minh một JWT test được ký bằng A.

### Nhiệm vụ D: Mô phỏng planned rotation

- Publish B cùng A.
- Xác nhận verifier tải B.
- Chuyển issuer sang ký bằng B.
- Xác minh token ký A và B trong overlap.
- Ghi thời điểm token cuối cùng ký bằng A.
- Tính thời điểm retire A theo exp tối đa, skew và propagation margin.
- Loại A khỏi JWKS sau khi đủ điều kiện.

### Nhiệm vụ E: Mô phỏng unknown kid

- Gửi token có kid không tồn tại.
- Quan sát một lần JWKS refresh có kiểm soát.
- Gửi nhiều request đồng thời với cùng kid lạ.
- Gửi nhiều kid ngẫu nhiên.
- Xác minh single-flight, negative cache và rate limit hoạt động.
- Xác minh mọi token không tìm được key đều bị từ chối.

### Nhiệm vụ F: Mô phỏng compromise

- Đánh dấu key A compromised.
- Ngừng ký bằng A.
- Phát emergency deny cho A.
- Xác minh verifier có cache A vẫn từ chối token dùng A.
- Phân phối key khẩn cấp B hoặc C.
- Xác minh token mới hoạt động và token dùng key bị compromise bị từ chối.
- Ghi lại ảnh hưởng tới token cũ còn hạn.

### Nhiệm vụ G: Kiểm tra vận hành

- Kiểm tra metric refresh, cache, key lookup và signature verification.
- Tạo dashboard cho từng issuer/resource alias.
- Tạo alert khi key mới chưa tới verifier trước cutover.
- Chạy runbook planned rotation.
- Chạy runbook emergency compromise.
- Kiểm tra log không chứa private key hoặc raw token.

## 20. Tiêu chí hoàn thành bài thực hành

Bài thực hành được xem là hoàn thành khi có bằng chứng cho tất cả các điều kiện:

| Tiêu chí | Bằng chứng |
| --- | --- |
| Trust model rõ | Sơ đồ issuer, JWKS endpoint và resource servers. |
| Key inventory đầy đủ | Có owner, kid, alg, trạng thái và lịch vòng đời. |
| Private key được bảo vệ | Private key nằm trong key store/HSM/KMS hoặc lab secret store có kiểm soát; không xuất hiện trong JWKS. |
| JWKS hợp lệ | JSON đúng schema, public parameters đúng và không có private material. |
| Key selection đúng | Verifier chọn key theo issuer + kid + algorithm. |
| Token verification đúng | Kiểm tra chữ ký, iss, aud, exp và token profile. |
| Publish-before-use | Key mới có trong JWKS và verifier nhận được trước khi issuer ký token mới. |
| Overlap đủ | Có phép tính dựa trên exp lớn nhất, clock skew, cache/propagation và margin. |
| Planned retirement | Key cũ chỉ bị loại sau khi không còn token hợp lệ cần xác minh. |
| Emergency containment | Key bị compromise bị disable và deny propagation được xác nhận. |
| Fail closed | Unknown kid, JWKS outage hoặc signature failure không dẫn tới ALLOW. |
| Observability | Có metric, dashboard, alert và runbook. |
| Regression tests | Token cũ/mới, wrong key, unknown kid và compromised kid có kết quả đúng. |

## 21. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Publish key mới sau khi đã ký token mới | Verifier chưa biết key mới sẽ từ chối token hợp lệ. | Publish-before-use và xác nhận propagation. |
| Xóa key cũ ngay sau cutover | Token cũ còn hạn không xác minh được. | Giữ public key cũ qua overlap tính toán rõ. |
| Giữ key cũ vô thời hạn | Mở rộng số key có thể được dùng để xác minh và khó kiểm soát vòng đời. | Đặt verify_until và retire theo policy. |
| Dùng lại kid | Cache có thể gắn kid với key material khác nhau. | Kid mới cho mỗi key mới. |
| Publish private key trong JWKS | Attacker có thể ký token giả. | Chỉ công bố public parameters và kiểm tra tự động. |
| Dùng một key cho nhiều issuer | Mở rộng trust ngoài dự kiến và gây nhầm lẫn nguồn. | Tách key theo issuer/trust domain. |
| Chọn key chỉ bằng kid | Có thể lấy key từ issuer khác. | Lookup theo issuer, kid, alg và profile. |
| Tin jku/x5u từ token | SSRF hoặc key substitution. | Chỉ dùng JWKS URI từ trust configuration. |
| JWKS timeout thì bỏ qua chữ ký | Token giả có thể được chấp nhận. | Dùng cache chỉ theo policy; nếu không có key tin cậy thì reject. |
| Coi xóa key khỏi JWKS là revoke tức thì | Verifier cache cũ vẫn có thể chấp nhận token. | Emergency deny và cache invalidation/push propagation. |
| Không tính token lifetime tối đa | Retire key quá sớm hoặc giữ overlap quá lâu. | Tính từ exp lớn nhất của token thực tế. |
| Không kiểm thử multi-region | Một region có thể chưa nhận key mới hoặc deny event. | Xác nhận từng verifier/region. |
| Dùng chung key dev và production | Credential test có thể được chấp nhận ở production. | Tách issuer, key và trust configuration. |

## 22. Checklist vận hành JWKS và rotation

Trước khi đưa thiết kế vào production, hãy xác nhận:

1. **Issuer trust:** issuer và JWKS URI đến từ trust registry/metadata đã xác minh?
2. **Transport:** JWKS được phân phối qua HTTPS và TLS được xác minh?
3. **Key inventory:** có owner, kid, thuật toán, trạng thái và thời hạn cho mỗi key?
4. **Private key:** chỉ issuer có quyền ký; resource server chỉ nhận public key?
5. **JWK schema:** kty, n, e hoặc EC parameters, kid, use/key_ops và alg hợp lệ?
6. **No private material:** JWKS và log không chứa d, p, q, dp, dq, qi hoặc EC d?
7. **Key binding:** mỗi key gắn với đúng issuer, profile và thuật toán?
8. **kid policy:** kid mới không tái sử dụng và không gây nhập nhằng?
9. **Verifier policy:** alg allowlist, issuer, audience, typ và time claims được kiểm tra?
10. **Cache:** TTL, ETag, stale policy, namespace và refresh rate limit rõ ràng?
11. **Unknown kid:** refresh single-flight/negative cache có giới hạn?
12. **Publish-before-use:** key mới được publish và verifier nhận trước cutover?
13. **Overlap:** thời gian giữ key cũ tính từ token lifetime tối đa, clock skew và propagation margin?
14. **Retirement:** key cũ chỉ bị loại sau khi token còn hạn không còn cần nó?
15. **Rollback:** có điều kiện rollback và chỉ rollback khi key cũ chưa compromise?
16. **Emergency rotation:** có disable signing, deny kid và cache invalidation/push propagation?
17. **Distributed rollout:** mọi instance/region có xác nhận key version và emergency deny?
18. **Observability:** có metric key lookup, JWKS refresh, signature failure và unknown kid?
19. **Testing:** có test planned rotation, unknown kid, cache outage và compromise?
20. **Audit:** có lưu phê duyệt, timeline, thao tác ký, publish, disable và retire?

## 23. Ghi nhớ trọng tâm

- JWKS công bố public key; private signing key phải được bảo vệ và không bao giờ xuất hiện trong JWKS.
- Verifier chọn key trong JWKS của issuer đã tin cậy theo kid, thuật toán và token profile.
- kid là key selector, không phải bằng chứng xác thực issuer hoặc chữ ký.
- Planned rotation phải publish public key mới trước khi issuer ký token bằng key mới.
- Giữ public key cũ ở trạng thái verify_only cho tới khi mọi token ký bằng nó hết hạn theo clock policy và propagation margin.
- Overlap phải tính từ token lifetime tối đa, exp lớn nhất, clock skew, cache/refresh propagation và margin triển khai.
- Không tái sử dụng kid và không dùng một key tùy tiện cho nhiều thuật toán.
- Cache JWKS phải có freshness/stale policy, namespace theo issuer và refresh có rate limit.
- Xóa key khỏi JWKS không lập tức vô hiệu hóa key đã cache; emergency compromise cần deny propagation và cache invalidation.
- JWT offline không cung cấp thu hồi tức thì nếu verifier không có trạng thái online hoặc denylist.
- Mọi verifier/region phải được xác nhận đã nhận key mới và emergency deny trước khi coi rotation hoàn tất.
- Sau khi xác minh chữ ký, resource server vẫn phải kiểm tra issuer, audience, thời gian, token profile và authorization.

**Tài liệu tham khảo kỹ thuật:** RFC 7515 (JSON Web Signature); RFC 7517 (JSON Web Key); RFC 7518 (JSON Web Algorithms); RFC 7519 (JSON Web Token); RFC 7638 (JSON Web Key Thumbprint); RFC 8414 (OAuth 2.0 Authorization Server Metadata); RFC 8725 (JSON Web Token Best Current Practices); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens). Các chuẩn này định nghĩa JOSE, JWK/JWKS, thuật toán và token profile; thời gian overlap, cache policy, emergency deny và quy trình vận hành phải được xác định theo token lifetime, kiến trúc và threat model của hệ thống.
