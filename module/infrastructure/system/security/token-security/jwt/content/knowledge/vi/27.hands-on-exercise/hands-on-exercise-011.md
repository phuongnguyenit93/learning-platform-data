# Rà soát một cấu hình JWT bằng hợp đồng, mô hình đe dọa và bộ kiểm thử

## 1. Mục tiêu bài thực hành

Bài thực hành mô phỏng một cuộc rà soát bảo mật trước khi đưa API sử dụng JWT vào production. Người học nhận một cấu hình verifier có chủ ý chứa nhiều lỗi, một bối cảnh hệ thống và các yêu cầu nghiệp vụ. Nhiệm vụ là xác định hợp đồng token, lập mô hình đe dọa, tìm lỗi trong cấu hình, đề xuất cấu hình mục tiêu và xây dựng bộ kiểm thử chứng minh các quyết định bảo mật.

Bài tập thuộc module **Security - JSON Web Token (JWT)** và sử dụng kiến thức JWT, JOSE, OAuth 2.0, issuer, audience, signing key, claims, token profile, key rotation và authorization. Các bước được mô tả độc lập với ngôn ngữ lập trình hoặc framework.

Sau khi hoàn thành, người học có thể:

- Chuyển yêu cầu nghiệp vụ thành token validation contract rõ ràng.
- Xác định tài sản, trust boundary, actor và đường tấn công liên quan đến JWT.
- Phát hiện lỗi cấu hình về thuật toán, issuer, audience, thời hạn, loại token và nguồn khóa.
- Phân biệt xác minh mật mã với authorization.
- Đề xuất cấu hình verifier theo allowlist và trust configuration.
- Thiết kế test matrix gồm positive, negative, boundary, rotation và dependency-failure cases.
- Đưa ra kế hoạch rollout, quan sát và rollback có thể kiểm chứng.

**Thời lượng gợi ý:** 90–150 phút. Có thể chia thành một buổi phân tích nhóm và một buổi triển khai kiểm thử.

## 2. Bối cảnh hệ thống

Example Shop có một Authorization Server phát hành JWT access token cho các API. Orders API nhận yêu cầu đọc và cập nhật đơn hàng. API Gateway chuyển tiếp request đến Orders API, nhưng Orders API vẫn phải tự xác minh token theo trust configuration của mình.

Các thành phần:

- **Authorization Server (AS):** xác thực client/người dùng, phát hành access token và công bố public signing keys qua JWKS.
- **API Gateway:** định tuyến request và có thể áp dụng rate limit; không phải nơi duy nhất thực thi xác minh token.
- **Orders API:** xác minh access token, tạo principal và thực hiện authorization theo tenant, scope và quyền sở hữu đơn hàng.
- **JWKS endpoint:** cung cấp tập public JWK của issuer đã được cấu hình tin cậy.
- **Monitoring platform:** nhận metrics, logs và alerts từ verifier.

### Luồng request mong đợi

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant O as Orders API
    participant J as Trusted JWKS
    C->>G: Request + Bearer access token
    G->>O: Forward request
    O->>O: Parse token under fixed profile
    O->>J: Resolve key from configured issuer JWKS
    J-->>O: Public JWK set
    O->>O: Verify signature and claims
    O->>O: Build verified principal
    O->>O: Authorize action and resource
    O-->>C: Business response or protocol error
~~~

### Yêu cầu nghiệp vụ

| Hành động | Scope cần có | Ràng buộc bổ sung |
| --- | --- | --- |
| Xem đơn hàng | `orders:read` | Chủ thể thuộc tenant sở hữu đơn hàng hoặc có quyền hỗ trợ được cấp riêng |
| Cập nhật đơn hàng | `orders:update` | Chỉ cập nhật trường được phép; kiểm tra tenant và ownership |
| Hủy đơn hàng | `orders:cancel` | Phải có scope tương ứng và đơn hàng ở trạng thái cho phép hủy |

Token chỉ được dùng cho Orders API. Token dành cho Payments API hoặc token dùng để đăng nhập client không được chấp nhận tại endpoint này.

### Trust configuration đã được phê duyệt

Bài tập sử dụng hợp đồng mục tiêu sau làm căn cứ đánh giá:

| Thuộc tính | Giá trị mục tiêu |
| --- | --- |
| Issuer | `https://identity.example` |
| Audience | `orders-api` |
| Token profile | OAuth 2.0 JWT access token theo profile được chọn |
| Serialization | Compact JWS signed access token; không nhận JWE/nested JWT tại endpoint này |
| Signing algorithm | `RS256` trong môi trường bài tập; allowlist cố định |
| Key source | JWKS URI cấu hình sẵn: `https://identity.example/.well-known/jwks.json` |
| Key selection | `kid` chọn key trong JWKS tin cậy của issuer này |
| Token type | Explicit access-token type theo profile, ví dụ `at+jwt` khi áp dụng RFC 9068 |
| Required claims | Tuân thủ profile đã chọn; bài tập giả định `iss`, `sub`, `aud`, `exp`, `iat`, `jti` và `client_id` |
| Lifetime | Tối đa 10 phút theo policy nội bộ |
| Clock skew | Tối đa 60 giây theo policy nội bộ |
| Authorization | Dựa trên claims đã xác minh, scope và dữ liệu tenant/resource phía server |
| Logging | Không ghi raw token, Authorization header hoặc toàn bộ claims |

Giá trị algorithm, lifetime, skew và endpoint là policy minh họa cho bài tập, không phải cấu hình bắt buộc cho mọi JWT deployment. Nếu tổ chức chọn profile RFC 9068, cần đối chiếu chính xác normative requirements của profile thay vì chỉ dựa vào bảng tóm tắt này.

## 3. Đề bài: cấu hình hiện tại cần được rà soát

Nhóm vận hành nhận được cấu hình giả lập dưới đây. Cấu hình được viết theo dạng pseudoconfiguration trung lập nền tảng; tên trường mô tả ý định, không phải cú pháp của một thư viện cụ thể.

~~~yaml
jwt_verifier:
  enabled: true

  accepted_algorithms:
    - RS256
    - HS256
    - none

  issuer:
    source: token.payload.iss
    validation: optional

  audience:
    validation: disabled

  signature:
    validation: enabled
    key_source:
      priority:
        - token.header.jku
        - token.header.x5u
        - local_key_cache
      allow_unknown_kid: true

  claims:
    exp:
      required: false
      validation: disabled
    nbf:
      validation: disabled
    iat:
      validation: disabled
    typ:
      validation: ignored

  parsing:
    accept_jws: true
    accept_jwe: true
    accept_nested_jwt: true
    ignore_unknown_critical_headers: true
    duplicate_json_members: last_value_wins

  authorization:
    roles_source: decoded_payload_before_signature_validation
    missing_scope: allow

  jwks:
    refresh_on_unknown_kid: always
    timeout_ms: 30000
    cache_stale_forever: true

  errors:
    all_failures_http_status: 401
    include_exception_message: true

  logging:
    include_authorization_header: true
    include_decoded_claims: true
~~~

**Quy tắc bài tập:** xem cấu hình trên là đầu vào cần đánh giá. Không chạy nó trên production và không dùng token, private key hoặc credential thật trong các bài thử.

## 4. W1 — Xác định hợp đồng token trước khi sửa cấu hình

Không bắt đầu bằng cách đổi từng dòng cấu hình. Trước hết hãy viết token contract để xác định chính xác verifier cần chấp nhận điều gì.

### Nhiệm vụ 1: lập contract

Điền bảng sau bằng giá trị đã cho trong bối cảnh. Nếu một điều kiện chưa được xác định, ghi rõ câu hỏi cần hỏi chủ sở hữu hệ thống thay vì tự đoán.

| Hạng mục | Quyết định cần ghi |
| --- | --- |
| Issuer trust | Issuer chính xác nào được tin cậy? Có hỗ trợ nhiều issuer không? |
| Audience | Resource/API nào được phép nhận token? |
| Token type/profile | Access token, ID Token, assertion hay proof JWT? |
| Serialization | JWS, JWE hay nested JWT? Endpoint có hỗ trợ loại nào? |
| Algorithm | Allowlist gồm thuật toán nào? |
| Key source | JWKS/key store nào đã được cấu hình tin cậy? |
| Key selection | Dùng KID ra sao và xử lý unknown KID thế nào? |
| Required claims | Claim nào bắt buộc và đúng kiểu dữ liệu nào? |
| Time policy | Kiểm tra exp, nbf, iat và clock skew ra sao? |
| Authorization | Scope/permission và tenant/resource được đánh giá thế nào? |
| Replay/revocation | Profile có yêu cầu kiểm tra jti, revocation hoặc sender constraint không? |
| Error mapping | Token sai, thiếu quyền và dependency outage được biểu diễn thế nào? |
| Observability | Những metadata nào được phép log/đếm? |

### Nhiệm vụ 2: xác định thứ tự xử lý

Sắp xếp luồng theo thứ tự an toàn:

1. Nhận credential và kiểm tra kích thước/cú pháp request.
2. Parse cấu trúc token theo đúng serialization đã cấu hình.
3. Kiểm tra JOSE header và profile.
4. Chọn khóa trong nguồn tin cậy.
5. Xác minh chữ ký.
6. Kiểm tra issuer, audience, thời gian và required claims.
7. Tạo principal từ claims đã xác minh.
8. Kiểm tra scope, tenant, ownership và business policy.
9. Thực hiện nghiệp vụ.
10. Ghi telemetry an toàn.

Giải thích tại sao bước tạo principal và authorization không được diễn ra trước khi chữ ký và claims validation hoàn tất.

## 5. W2 — Lập mô hình đe dọa

Mô hình đe dọa tập trung vào cách attacker có thể khiến verifier tin token sai, lấy khóa từ nguồn không tin cậy, vượt quyền hoặc làm hệ thống mất khả dụng.

### Tài sản cần bảo vệ

- Signing private key của Authorization Server.
- Public key trust configuration và JWKS cache.
- Access token và refresh token.
- Danh tính subject, client và tenant.
- Dữ liệu đơn hàng và quyền cập nhật/hủy.
- Trạng thái revocation/replay nếu profile yêu cầu.
- Audit log, telemetry và thông tin cấu hình nội bộ.

### Trust boundaries

~~~mermaid
flowchart LR
    A["Untrusted client"] -->|"Bearer token"| B["Gateway"]
    B -->|"Request"| C["Orders API verifier"]
    C -->|"Configured HTTPS only"| D["Trusted JWKS endpoint"]
    C --> E["Verified principal"]
    E --> F["Authorization policy"]
    F --> G["Orders data"]
    C --> H["Restricted telemetry"]
    X["Untrusted token header/payload"] -. "Must not control trust" .-> C
~~~

### Nhiệm vụ 3: tạo threat register

Với mỗi threat, ghi asset, attack path, điều kiện khai thác, impact, likelihood, severity, control và test chứng minh.

| Threat ID | Tình huống cần phân tích | Câu hỏi gợi ý |
| --- | --- | --- |
| T-01 | Algorithm confusion hoặc thuật toán không được phép | Attacker có thể thay alg hoặc khiến verifier dùng sai loại key không? |
| T-02 | Unsigned token / alg none | Verifier có chấp nhận token không có chữ ký không? |
| T-03 | Issuer spoofing | Issuer do token tự khai có thể tự trở thành trusted issuer không? |
| T-04 | Audience substitution | Token hợp lệ cho API khác có thể truy cập Orders API không? |
| T-05 | Key source injection / SSRF | Header jku hoặc x5u có thể khiến server gọi host attacker kiểm soát không? |
| T-06 | Unknown KID abuse | Nhiều KID ngẫu nhiên có ép verifier tải JWKS liên tục không? |
| T-07 | Expired/future token | Token hết hạn hoặc chưa có hiệu lực có bị chấp nhận không? |
| T-08 | Token type confusion | ID Token, access token và proof JWT có bị dùng thay thế nhau không? |
| T-09 | Claims trust before signature | Role/scope từ payload chưa xác minh có được dùng để cấp quyền không? |
| T-10 | Dependency outage | JWKS outage có khiến verifier fail open hoặc gây lỗi dây chuyền không? |
| T-11 | Sensitive logging | Token/header/claims có thể rò rỉ vào log hoặc trace không? |
| T-12 | Parser ambiguity | Duplicate JSON member hoặc critical header không hỗ trợ có được xử lý nhất quán không? |

### Đánh giá rủi ro

Dùng thang điểm nội bộ nhất quán, ví dụ:

- Likelihood: 1 (khó xảy ra) đến 5 (dễ xảy ra).
- Impact: 1 (thấp) đến 5 (rất nghiêm trọng).
- Risk score = Likelihood × Impact.

Risk score giúp ưu tiên công việc, không thay thế judgment. Một lỗi có thể được xếp Critical theo policy dù điểm số trung bình thấp nếu nó cho phép bỏ qua xác minh chữ ký hoặc tin nguồn khóa tùy ý.

## 6. W3 — Phân tích lỗi trong cấu hình hiện tại

Đọc từng nhóm cấu hình và ghi finding. Mỗi finding nên có: vị trí, mô tả, tác động, mức độ, khuyến nghị và test case.

### Nhiệm vụ 4: review theo nhóm

| Nhóm | Dấu hiệu trong cấu hình | Điều cần xác minh |
| --- | --- | --- |
| Algorithm | Có RS256, HS256 và none | Có thể ép verifier dùng thuật toán hoặc loại key sai không? |
| Issuer | Lấy issuer từ payload và validation optional | Trust anchor có bị điều khiển bởi token không? |
| Audience | Validation disabled | Token dành cho resource khác có được nhận không? |
| Key source | Ưu tiên jku/x5u từ token | Có trust arbitrary URL hoặc SSRF không? |
| KID | allow_unknown_kid | Unknown key có bị chấp nhận hoặc làm phát sinh lookup không giới hạn? |
| Time claims | exp không bắt buộc, exp/nbf/iat không validate | Token hết hạn, tương lai hoặc quá cũ có được nhận không? |
| Token type | typ ignored | Có thể nhầm access token với ID Token/proof JWT không? |
| Serialization | Nhận JWS/JWE/nested không phân biệt | Endpoint có chấp nhận cấu trúc ngoài profile không? |
| Critical headers | Ignore unknown critical headers | Consumer có bỏ qua extension mà không hiểu semantics không? |
| JSON parser | Last duplicate value wins nhưng chưa mô tả semantics parser | Có bảo đảm chọn lexically last member hoặc reject duplicate nhất quán ở mọi thành phần không? |
| Authorization | Đọc roles trước verify; thiếu scope allow | Token giả có thể tự cấp quyền không? |
| JWKS operations | Refresh always, timeout 30 giây, cache stale forever | Có refresh storm, latency cao hoặc tin khóa stale vô thời hạn không? |
| Error handling | Mọi lỗi 401, message lộ ra ngoài | Dependency outage và token rejection có bị gộp không? |
| Logging | Ghi Authorization header và decoded claims | Bearer credential/PII có bị lộ không? |

### Phân loại mức độ

Dùng severity nhất quán:

- **Critical:** có thể chấp nhận token không xác minh, bỏ qua trust anchor hoặc cấp quyền trái phép trên diện rộng.
- **High:** có thể vượt audience/issuer/profile, dùng khóa không tin cậy hoặc gây rò rỉ credential nghiêm trọng.
- **Medium:** có thể gây outage, sai hành vi theo thời gian, parser disagreement hoặc làm yếu khả năng phát hiện.
- **Low:** thiếu telemetry hoặc tài liệu, gây khó điều tra nhưng chưa trực tiếp làm sai quyết định xác minh.

Không xếp mức độ chỉ dựa vào tên trường. Cần nêu attack path và impact trong bối cảnh Orders API.

## 7. W4 — Đề xuất cấu hình verifier mục tiêu

Sau khi hoàn tất threat register, viết cấu hình mục tiêu. Cấu hình dưới đây là pseudoconfiguration minh họa; nó không phải cú pháp của một thư viện cụ thể.

~~~yaml
jwt_verifier:
  enabled: true

  profile:
    name: orders-api-access-token
    accepted_serialization:
      - compact_jws
    token_type:
      required: true
      accepted:
        - at+jwt

  trust:
    issuer: https://identity.example
    audience:
      required: true
      required_member: orders-api

  algorithms:
    allowlist:
      - RS256
    reject_unlisted: true

  keys:
    source:
      type: configured_jwks
      uri: https://identity.example/.well-known/jwks.json
      issuer_binding: https://identity.example
    selection:
      kid_required: true
      match_key_type: RSA
      match_use: sig_when_present
      match_algorithm: RS256
      reject_ambiguous_match: true
    unknown_kid:
      refresh_once_per_coalesced_window: true
      negative_cache: bounded_short_ttl
      reject_if_still_unknown: true

  claims:
    require:
      - iss
      - sub
      - aud
      - exp
      - iat
      - jti
      - client_id
    validate_issuer: exact
    require_audience_member: orders-api
    validate_exp: true
    validate_nbf_when_present: true
    validate_iat: true
    maximum_future_iat_skew_seconds: 60
    maximum_lifetime_seconds: 600
    clock_skew_seconds: 60

  parsing:
    reject_unknown_critical_headers: true
    reject_duplicate_json_members: true
    reject_unconfigured_serialization: true
    never_trust_unverified_claims: true

  authorization:
    require_verified_principal: true
    missing_scope: deny
    enforce_tenant_boundary: true
    enforce_resource_ownership: true

  jwks:
    connect_timeout_ms: 1000
    request_timeout_ms: 3000
    bounded_retry: true
    cache_max_age_seconds: configured_policy
    never_use_expired_cache_without_explicit_policy: true

  errors:
    invalid_credential: 401
    insufficient_permission: 403
    dependency_unavailable: 503
    internal_failure: 500
    expose_internal_exception: false

  logging:
    include_raw_token: false
    include_authorization_header: false
    include_full_claims: false
    include_reason_code: true
    include_request_id: true
~~~

### Nhiệm vụ 5: giải thích từng quyết định

Không chỉ chép cấu hình. Với mỗi mục, giải thích:

- Nó ngăn threat nào trong threat register?
- Yêu cầu nào đến từ token profile/RFC?
- Yêu cầu nào là local policy của Example Shop?
- Nếu dependency không khả dụng thì outcome nào được trả?
- Điều gì phải được kiểm thử để chứng minh cấu hình hoạt động?

### Các điểm cần đánh giá kỹ

**Algorithm allowlist:** RS256 là lựa chọn giả định của bài tập. Trong hệ thống khác, tổ chức có thể chọn thuật toán khác đã được phê duyệt. Nguyên tắc là verifier dùng allowlist cố định theo issuer/profile, kiểm tra loại khóa tương thích và không lấy quyết định thuật toán từ token một cách tự do.

**Issuer và audience:** issuer phải khớp trust configuration đã cấu hình. Claim aud phải chứa audience identifier chính xác §orders-api§ theo quy tắc xử lý string/array của profile; không dùng substring hoặc so khớp lỏng. Nếu profile cho phép nhiều audience, áp dụng policy về các recipient bổ sung đã được định nghĩa. Nếu có nhiều issuer, mỗi issuer cần profile và nguồn khóa được liên kết rõ ràng.

**KID và JWKS:** KID chỉ chọn khóa bên trong JWKS của issuer tin cậy. Không dùng jku/x5u trong token để tự quyết định nơi tải khóa. Unknown KID sau một lần refresh có kiểm soát phải bị từ chối; không tạo vòng lặp tải JWKS.

**Time validation:** exp phải có và được kiểm tra. nbf nếu có phải được kiểm tra. iat cần được kiểm tra theo profile và local policy: không nằm quá xa trong tương lai, exp phải sau iat và hiệu số exp trừ iat không vượt maximum lifetime. Không mặc định rằng mọi profile đều bắt buộc cùng một giới hạn tuổi.

**Token type:** nếu dùng RFC 9068, đối chiếu yêu cầu typ chính xác của profile. Ví dụ at+jwt trong cấu hình là type cho access token theo profile đó. Không dùng cùng validator cho ID Token, DPoP proof hoặc JWT assertion có semantics khác.

**Authorization:** chỉ principal được tạo sau xác minh đầy đủ mới được dùng. Scope không thay thế tenant/ownership check. Thiếu scope phải deny.

**JWKS outage:** fail closed về quyết định xác minh. Nếu không có khóa phù hợp từ cache còn hợp lệ theo policy và không thể lấy JWKS, biểu diễn dependency unavailable; không chấp nhận token dựa trên payload đã decode.

## 8. W5 — Xây dựng bộ kiểm thử bảo mật

Bộ kiểm thử phải chứng minh cả trường hợp chấp nhận lẫn từ chối. Dùng test key riêng, token fixture giả lập và clock có thể điều khiển. Không dùng production token hoặc private key.

### Test matrix: positive và negative cases

| ID | Input/thay đổi | Kết quả mong đợi |
| --- | --- | --- |
| V-01 | JWS hợp lệ, đúng issuer/audience/type/algorithm/claims | Accept |
| V-02 | Token ký bằng public key hiện hành trong trusted JWKS | Accept |
| N-01 | Chữ ký bị sửa | Reject: invalid signature |
| N-02 | alg là none | Reject |
| N-03 | Thuật toán ngoài allowlist | Reject |
| N-04 | Cố dùng HS256 với public RSA key hoặc key type sai | Reject |
| N-05 | Issuer không nằm trong trust configuration | Reject |
| N-06 | Issuer claim khác issuer được cấu hình | Reject |
| N-07 | Audience chỉ chứa payments-api | Reject |
| N-08 | Token thiếu exp | Reject |
| N-09 | Token đã hết hạn ngoài clock skew | Reject |
| N-10 | Token chưa tới nbf ngoài clock skew | Reject |
| N-11 | Token có lifetime vượt maximum policy | Reject |
| N-12 | Token type là ID Token hoặc proof JWT | Reject |
| N-13 | Unknown KID sau refresh thành công | Reject |
| N-14 | Header jku trỏ tới host attacker | Không fetch URL đó; Reject nếu profile cấm header |
| N-15 | Header x5u trỏ tới địa chỉ nội bộ | Không fetch URL đó |
| N-16 | Unknown critical JOSE header | Reject |
| N-17 | Duplicate JSON member names | Reject theo parser policy |
| N-18 | JWE/nested JWT tại endpoint chỉ nhận compact JWS | Reject |
| N-19 | Scope thiếu | Authentication Valid; authorization Denied |
| N-20 | Scope đúng nhưng tenant khác | Deny |
| N-21 | Scope đúng nhưng subject không sở hữu đơn hàng | Deny |
| N-22 | Payload chứa role admin nhưng chữ ký sai | Reject; role không được dùng |

### Test matrix: rotation, cache và dependency

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| K-01 | Khóa mới được publish trước khi issuer bắt đầu ký | Token với KID mới được xác minh sau refresh/cache update |
| K-02 | Issuer cutover sang KID mới khi key đã có trong JWKS cache | Accept |
| K-03 | Khóa cũ và mới cùng tồn tại trong giai đoạn overlap | Cả hai được xử lý theo rotation policy |
| K-04 | Khóa cũ bị retire sau thời gian overlap | Token ký bằng khóa đã retire bị từ chối theo policy |
| K-05 | KID không biết, JWKS refresh thành công nhưng vẫn không có key | Reject, không refresh liên tục |
| K-06 | JWKS timeout và không có cache hợp lệ | Unavailable/503; không fail open |
| K-07 | JWKS timeout nhưng có cached key còn hợp lệ theo policy | Xử lý theo cache policy đã công bố |
| K-08 | Nhiều request đồng thời mang unknown KID | Refresh được coalesce/rate-limit |
| K-09 | JWKS trả JSON/key sai cấu trúc hoặc key type không phù hợp | Reject key set hoặc Internal/Dependency failure theo phân loại |
| K-10 | Một region cache stale, region khác đã nhận key mới | Alert propagation; hành vi theo max cache age và rollout policy |
| K-11 | Emergency revoke một KID | Mọi verifier áp dụng revoked state trước khi tiếp tục tin khóa |
| K-12 | Clock của verifier lệch | Boundary tests xác nhận clock skew và alert |

### Nhiệm vụ 6: định nghĩa assertion cho mỗi test

Mỗi test phải kiểm tra nhiều hơn HTTP status. Ví dụ, với token có audience sai:

- Verifier trả reason code `AUDIENCE_MISMATCH`.
- Không tạo authenticated principal.
- Không chạy business handler.
- Không phát sinh side effect trên Orders data.
- Log không chứa raw token.
- Metric tăng đúng reason code.

Với JWKS timeout:

- Kết quả là dependency unavailable khi không có cache hợp lệ.
- Không ghi nhận `SIGNATURE_INVALID`.
- Không gọi refresh vô hạn.
- Không sử dụng claims chưa xác minh.
- Có request/correlation ID để tra cứu.

## 9. W6 — Kiểm thử authorization sau xác minh

Một token hợp lệ vẫn có thể không được phép thực hiện thao tác. Hãy dùng principal đã xác minh và dữ liệu đơn hàng giả lập:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read orders:update",
  "tenant_id": "tenant-17",
  "exp": 1893459600
}
~~~

Dữ liệu thử nghiệm:

| Order | Tenant | Owner |
| --- | --- | --- |
| O-100 | tenant-17 | user-123 |
| O-101 | tenant-17 | user-456 |
| O-200 | tenant-99 | user-123 |

### Nhiệm vụ 7: quyết định quyền

| Request | Kết quả cần quyết định | Lý do |
| --- | --- | --- |
| user-123 đọc O-100 | Allow | Scope read, đúng tenant và owner |
| user-123 cập nhật O-100 | Allow nếu trường được cập nhật hợp lệ | Scope update, đúng tenant/owner |
| user-123 hủy O-100 | Deny | Thiếu scope cancel |
| user-123 đọc O-101 | Deny theo ownership policy | Cùng tenant nhưng khác owner |
| user-123 đọc O-200 | Deny | Khác tenant |
| Token chỉ có orders:read cập nhật O-100 | Deny | Thiếu scope update |
| Token có scope đầy đủ nhưng issuer sai | Reject authentication | Token không thuộc trust profile |

Giải thích vì sao không nên trả cùng một reason code cho invalid signature và insufficient scope. Nêu cách ánh xạ phù hợp sang HTTP response theo giao thức và hợp đồng API.

## 10. W7 — Phân loại lỗi và response contract

Xác định response contract cho các kết quả:

| Kết quả nội bộ | Response gợi ý | Thông tin công khai |
| --- | --- | --- |
| Credential thiếu hoặc token invalid | 401 | Bearer challenge phù hợp, thông báo tổng quát |
| Request credential sai cú pháp | 400 hoặc response theo protocol contract | invalid_request nếu áp dụng RFC 6750 |
| Token hợp lệ nhưng thiếu scope | 403 | insufficient_scope khi phù hợp |
| Token hợp lệ nhưng vi phạm ownership/tenant policy | 403 hoặc 404 theo anti-enumeration policy | Không tiết lộ tài nguyên ngoài quyền |
| JWKS unavailable và không có cache hợp lệ | 503 | temporarily_unavailable hoặc lỗi dịch vụ tổng quát |
| Verifier misconfigured/crypto runtime failure | 500/503 theo phân loại | Không lộ exception nội bộ |

Không nhất thiết public response phải tiết lộ chi tiết KID, issuer mismatch hoặc chữ ký sai. Reason code chi tiết dùng trong metrics/log nội bộ; public error cần tuân theo giao thức và giảm khả năng dò token.

### Nhiệm vụ 8: viết response examples

Viết ít nhất ba response minh họa:

1. Invalid access token.
2. Insufficient scope.
3. JWKS dependency unavailable.

Mỗi response cần có request ID, cache policy phù hợp và không chứa token, decoded claims hoặc stack trace. Nếu dùng Bearer token, tham chiếu error semantics của RFC 6750.

## 11. W8 — Kế hoạch triển khai và vận hành

Một cấu hình tốt vẫn có thể thất bại nếu rollout không đồng bộ hoặc không có telemetry.

### Kế hoạch rollout

1. Đóng băng token contract và xác định owner của issuer/profile.
2. Tạo test keys, test JWKS và test token fixtures.
3. Triển khai verifier mới ở môi trường test/staging.
4. Chạy toàn bộ positive/negative/rotation/dependency test matrix.
5. Chạy canary với traffic kiểm thử hoặc shadow validation không tạo side effect.
6. So sánh reason codes và authorization decisions giữa verifier cũ/mới.
7. Triển khai dần theo service/region.
8. Theo dõi lỗi, latency, JWKS cache age và unknown KID.
9. Hoàn tất cutover và giữ rollback window có giới hạn.
10. Loại bỏ cấu hình yếu và legacy validation path sau khi xác nhận không còn consumer cần chúng.

Shadow validation không được tạo ra quyền truy cập hoặc side effect; kết quả shadow chỉ phục vụ so sánh và quan sát.

### Metrics tối thiểu

- Tổng verification attempts theo issuer alias, profile, service và region.
- Tỷ lệ VALID, REJECTED, UNAVAILABLE, INTERNAL_FAILURE.
- Reason code như SIGNATURE_INVALID, ISSUER_MISMATCH, AUDIENCE_MISMATCH, KEY_NOT_FOUND, TOKEN_EXPIRED.
- JWKS refresh count, success/failure, latency và cache age.
- Số unknown KID và số lượng KID duy nhất theo cửa sổ.
- Verification latency p50/p95/p99.
- Authorization denied theo scope, tenant và ownership policy ở dimension đã kiểm soát.

Không dùng raw JWT, subject, token ID hoặc arbitrary KID/issuer làm metric label có cardinality cao.

### Runbook tối thiểu

- Khi signature failure tăng: xác minh signing key, KID, issuer rollout và key set version.
- Khi unknown KID tăng: kiểm tra rotation timeline, JWKS cache, propagation và khả năng probing; không tự động mở rộng trust.
- Khi JWKS unavailable: kiểm tra DNS/TLS/network/endpoint, cache age và dependency health; fail closed khi không có key hợp lệ.
- Khi issuer mismatch tăng: kiểm tra client/environment routing và trust profile; không thêm issuer chưa xác minh.
- Khi authorization denied tăng: kiểm tra scope mapping, tenant context, ownership data và thay đổi policy; không hạ validation để giảm lỗi.
- Khi token lộ trong log: kích hoạt incident handling, hạn chế quyền truy cập log, xác định credential exposure và revoke/rotate theo phạm vi phù hợp.

## 12. W9 — Bài nộp và tiêu chí đánh giá

### Các sản phẩm phải nộp

Người học hoàn thành bài bằng một bộ artifact có thể review:

1. **Token contract:** issuer, audience, profile/type, serialization, algorithm, key source, required claims, time policy và error mapping.
2. **Threat register:** tối thiểu 8 threat, có attack path, impact, severity và control.
3. **Configuration findings:** tối thiểu 10 finding, mỗi finding có vị trí, bằng chứng, severity và khuyến nghị.
4. **Target verifier configuration:** pseudoconfiguration đã sửa và giải thích từng policy.
5. **Test matrix:** tối thiểu 20 test case, có positive, negative, authorization, rotation và dependency failure.
6. **Rollout plan:** readiness gates, canary, monitoring, rollback và điều kiện loại bỏ cấu hình cũ.
7. **Review summary:** quyết định Go/No-Go và các điều kiện còn mở.

### Rubric chấm điểm

| Hạng mục | Điểm |
| --- | ---: |
| Token contract đầy đủ, không mâu thuẫn | 15 |
| Threat model xác định đúng trust boundary và attack path | 15 |
| Phát hiện và ưu tiên lỗi cấu hình | 20 |
| Target configuration có kiểm soát trust và algorithm | 15 |
| Test matrix có assertion kiểm tra cả side effect | 20 |
| Rollout, observability và rollback | 10 |
| Báo cáo rõ ràng, truy nguyên được requirement | 5 |
| **Tổng** | **100** |

### Điều kiện không đạt dù tổng điểm cao

Bài không đạt nếu còn một trong các lỗi nghiêm trọng sau:

- Chấp nhận alg none hoặc thuật toán ngoài allowlist.
- Không xác minh issuer hoặc audience.
- Cho phép token header quyết định nguồn khóa tùy ý.
- Dùng claims chưa xác minh để tạo principal hoặc authorization.
- Fail open khi không thể xác minh chữ ký/khóa.
- Bỏ qua expiration hoặc token type mà profile yêu cầu.
- Dùng scope mà không kiểm tra tenant/resource boundary theo nghiệp vụ.

## 13. Đáp án tham khảo và các finding kỳ vọng

Phần này giúp người học tự đối chiếu sau khi hoàn thành. Mức severity cuối cùng cần xét threat model và môi trường cụ thể.

| Finding | Severity gợi ý | Vì sao nguy hiểm | Khắc phục |
| --- | --- | --- | --- |
| Cho phép alg none | Critical | Có thể chấp nhận token không có chữ ký nếu verifier xử lý sai | Loại bỏ; allowlist thuật toán |
| Trộn HS256 và RS256 không có key separation | Critical | Có nguy cơ algorithm/key confusion nếu resolver dùng sai key material | Một policy algorithm rõ; kiểm tra key type và use |
| Issuer lấy từ unverified payload và optional | Critical | Token có thể tự khai issuer để chọn trust context | Exact issuer allowlist/configuration |
| Không kiểm tra audience | High | Token cho API khác có thể được dùng tại Orders API | Audience bắt buộc và exact match theo profile |
| jku/x5u từ token quyết định key source | Critical | SSRF và trust arbitrary key source | Chỉ dùng JWKS URI đã cấu hình; không fetch URL do token điều khiển |
| Cho phép unknown KID | High | Không bảo đảm token có khóa tin cậy; có thể làm phát sinh lookup abuse | Refresh có kiểm soát, rồi reject nếu không tìm thấy |
| Không kiểm tra exp | High | Token có thể được dùng sau thời hạn | Bắt buộc và validate exp |
| Bỏ qua nbf/iat | Medium–High | Token tương lai hoặc quá cũ có thể được nhận | Validate theo profile và policy |
| Bỏ qua typ | High | Token type confusion giữa access token, ID Token hoặc proof JWT | Explicit token profile/type validation |
| Nhận mọi serialization | High | Consumer có thể chấp nhận cấu trúc ngoài hợp đồng | Chỉ nhận serialization đã cấu hình |
| Ignore unknown critical headers | High | Bỏ qua semantics extension mà sender yêu cầu xử lý | Reject critical parameter không hỗ trợ |
| Duplicate member semantics không rõ hoặc không nhất quán | Medium–High | Các thành phần có thể diễn giải cùng token khác nhau; quy tắc lexically last của chuẩn có thể bị triển khai sai | Reject duplicate member như local policy chặt hơn, hoặc thực thi đúng quy tắc parser được tiêu chuẩn cho phép và nhất quán ở mọi thành phần |
| Dùng roles trước verify | Critical | Token giả có thể tự khai quyền | Chỉ tạo principal sau verify đầy đủ |
| Missing scope allow | Critical/High | Thiếu bằng chứng quyền nhưng vẫn cho phép hành động | Deny by default |
| JWKS refresh mỗi unknown KID | Medium–High | Có thể gây request storm/DoS dependency | Single-flight, rate limit, negative cache có TTL |
| Timeout 30 giây | Medium | Tăng latency và giữ tài nguyên khi dependency chậm | Timeout ngắn có ngân sách theo SLO |
| Cache stale vô thời hạn | High | Có thể tiếp tục tin khóa đã retire/revoke | Max stale age và emergency invalidation |
| Mọi lỗi trả 401 | Medium | Che giấu dependency outage, gây retry/refresh không đúng | Phân biệt rejected, unavailable và internal failure |
| Exception message public | High | Có thể lộ nội bộ, key path hoặc chi tiết parser | Response tổng quát; chi tiết chỉ trong log bảo vệ |
| Log Authorization header/claims | Critical/High | Bearer token và PII có thể bị lộ qua telemetry | Redact; log reason code và request ID |

### Ví dụ target decision

Với cấu hình mục tiêu:

- Token có chữ ký hợp lệ, issuer/audience/type/claims hợp lệ: tạo verified principal.
- Token hợp lệ nhưng thiếu scope: xác minh thành công, authorization bị deny.
- Token có chữ ký sai: reject, không tạo principal.
- KID không tồn tại sau refresh có kiểm soát: reject.
- JWKS không khả dụng và không có cache hợp lệ: unavailable, không chấp nhận token.
- Token có issuer lạ: reject mà không gọi URL do token cung cấp.
- Token chứa role admin trong payload nhưng chữ ký sai: role bị bỏ qua hoàn toàn.

## 14. Câu hỏi phản biện sau bài thực hành

1. Vì sao một JWT có chữ ký hợp lệ vẫn có thể không được Orders API chấp nhận?
2. Tại sao KID không phải bằng chứng về danh tính issuer?
3. Điều gì khác nhau giữa KEY_NOT_FOUND và JWKS_UNAVAILABLE?
4. Nếu issuer mới được cấu hình nhưng consumer chưa cập nhật, rollout nên dừng ở đâu?
5. Khi nào một cached JWKS có thể được dùng trong lúc endpoint timeout? Ai quyết định max stale age?
6. Vì sao exp và iat không thể thay thế nhau?
7. Vì sao scope đúng vẫn chưa đủ để cho phép truy cập một đơn hàng?
8. Nếu shadow validation cho kết quả khác production verifier, cần thu thập bằng chứng gì trước khi cutover?
9. Vì sao response 503 trong dependency outage có thể chính xác hơn 401?
10. Khi nào nên dùng introspection hoặc trạng thái revocation bổ sung thay vì chỉ dựa vào JWT tự chứa?

## 15. Checklist kết thúc bài

Trước khi kết luận cấu hình đã sẵn sàng:

- Token contract gắn rõ issuer, audience, profile, serialization và algorithm.
- Key source được cấu hình ngoài token; KID chỉ chọn trong tập khóa tin cậy.
- Signature, issuer, audience, type và time claims được validate theo profile.
- Claims chỉ được dùng sau khi token được xác minh hoàn tất.
- Authorization deny by default và kiểm tra scope, tenant, ownership.
- Unknown KID, JWKS outage, cache stale và key rotation có semantics rõ.
- Parser xử lý critical headers và duplicate members nhất quán.
- Public errors không lộ chi tiết nội bộ; logs không chứa credential.
- Test matrix bao phủ positive, negative, boundary, rotation, dependency và authorization.
- Rollout có canary, readiness gate, telemetry và rollback.
- Không còn Critical/High finding chưa được xử lý hoặc có ngoại lệ được owner phê duyệt rõ ràng.

**Kết quả mong đợi:** người học không chỉ nói cấu hình “có vẻ an toàn”, mà có thể chứng minh vì sao token được chấp nhận hoặc từ chối, threat nào đã được kiểm soát, test nào xác nhận hành vi và bằng chứng nào cho phép đưa cấu hình vào production.

### Tài liệu tham khảo

- **RFC 7515 — JSON Web Signature (JWS):** cấu trúc và xác minh chữ ký.
- **RFC 7517 — JSON Web Key (JWK):** biểu diễn khóa và JWKS.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán JOSE.
- **RFC 7519 — JSON Web Token (JWT):** claims và cấu trúc JWT.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** truyền bearer token và error response.
- **RFC 8725 — JSON Web Token Best Current Practices:** các yêu cầu và khuyến nghị bảo mật JWT.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** profile access token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** hướng dẫn bảo mật OAuth hiện hành.
