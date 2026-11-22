# Chuẩn hóa kết quả xác minh và kiểu lỗi trong ứng dụng

## 1. Vì sao cần chuẩn hóa kết quả từ thư viện JWT?

Các thư viện JOSE/JWT có API và cách biểu diễn lỗi khác nhau. Một thư viện có thể trả boolean; thư viện khác trả object chứa claims; thư viện khác ném exception khi token sai, không tìm thấy khóa, JWKS timeout hoặc cấu hình verifier lỗi.

Nếu ứng dụng phụ thuộc trực tiếp vào exception của từng thư viện, cùng một tình huống có thể được xử lý khác nhau giữa các service. Lỗi vận hành có thể bị báo nhầm là token không hợp lệ, lỗi thiếu quyền có thể bị gộp với lỗi chữ ký, còn exception kỹ thuật có thể vô tình tiết lộ token hoặc cấu hình nội bộ.

**Chuẩn hóa kết quả xác minh** là tạo một hợp đồng nội bộ ổn định. Adapter chịu trách nhiệm chuyển kết quả và lỗi riêng của thư viện sang hợp đồng đó; tầng ứng dụng chỉ làm việc với các kết quả đã chuẩn hóa.

Nên tách ba lớp:

1. **Thư viện JOSE/JWT:** parse, xác minh mật mã, giải mã và kiểm tra claims.
2. **Verification adapter:** ánh xạ kết quả/exception của thư viện sang kiểu kết quả chuẩn.
3. **Application/API layer:** tạo principal, kiểm tra quyền nghiệp vụ, trả response và ghi log an toàn.

Đây là thiết kế dùng chung cho mọi ngôn ngữ và nền tảng; không phụ thuộc class hay exception cụ thể của một thư viện.

## 2. Phân biệt kết quả xác minh và quyết định phân quyền

Không nên gom mọi trường hợp vào một boolean valid/invalid. Ít nhất cần phân biệt các outcome sau:

| Outcome | Ý nghĩa | Hành vi |
| --- | --- | --- |
| **Valid** | Credential đã được xác minh và đáp ứng token profile | Tạo security context rồi tiếp tục authorization |
| **Rejected** | Credential hoặc cách gửi credential không đáp ứng điều kiện | Từ chối credential |
| **Unavailable** | Không thể hoàn thành xác minh do dependency cần thiết tạm thời không khả dụng | Không chấp nhận credential; báo lỗi dịch vụ phù hợp |
| **InternalFailure** | Lỗi cấu hình, runtime hoặc lỗi bất ngờ trong verifier | Không chấp nhận credential; cảnh báo vận hành |

Sau khi có Valid, tầng ứng dụng còn có thể đưa ra quyết định **Allowed** hoặc **Forbidden**. Forbidden là kết quả authorization: token hợp lệ nhưng chủ thể không có quyền trên hành động hoặc tài nguyên cụ thể. Nó không phải lỗi xác minh JWT.

~~~mermaid
flowchart TD
    A["Nhận credential"] --> B["Parse và xác minh JWT"]
    B --> C{"Verification outcome"}
    C -->|"Valid"| D["Tạo principal/security context"]
    C -->|"Rejected"| E["Từ chối credential"]
    C -->|"Unavailable"| F["Lỗi dịch vụ tạm thời"]
    C -->|"InternalFailure"| G["Lỗi nội bộ và cảnh báo"]
    D --> H["Authorization theo action/resource"]
    H --> I{"Được phép?"}
    I -->|"Có"| J["Tiếp tục xử lý"]
    I -->|"Không"| K["Forbidden"]
~~~

Ví dụ: token có chữ ký hợp lệ, đúng issuer/audience và còn hạn, nhưng chỉ có scope `orders:read`. Request xóa đơn hàng phải bị từ chối do thiếu quyền. Không nên ghi nhận đây là lỗi chữ ký hoặc token invalid.

## 3. Hợp đồng kết quả chuẩn ở ranh giới adapter

Một mô hình trung lập ngôn ngữ có thể dùng tagged union hoặc discriminated result:

~~~text
VerificationResult =
    Valid {
        principal,
        issuer,
        audiences,
        tokenType,
        issuedAt,
        notBefore,
        expiresAt,
        scopes,
        keyId,
        validationProfile
    }
  | Rejected {
        reasonCode
    }
  | Unavailable {
        reasonCode,
        dependency,
        retryable
    }
  | InternalFailure {
        reasonCode,
        incidentId
    }
~~~

Tên trường có thể thay đổi, nhưng ý nghĩa cần ổn định.

### Valid

Chỉ tạo Valid sau khi mọi bước bắt buộc của profile đã hoàn tất: parse, kiểm tra JOSE header, xác minh chữ ký/MAC hoặc giải mã JWE có xác thực, kiểm tra issuer, audience, thời hạn và claims theo profile.

Principal/security context chỉ chứa dữ liệu đã xác minh hoặc dữ liệu tin cậy được liên kết sau xác minh. Chỉ giữ claims cần cho quyết định tiếp theo; không chuyển toàn bộ payload nhạy cảm qua mọi tầng một cách mặc định.

### Rejected

Kết quả này cho biết credential hoặc request credential không được chấp nhận. Các reason code nội bộ có thể gồm:

- `CREDENTIAL_MISSING`
- `CREDENTIAL_MALFORMED`
- `TOKEN_MALFORMED`
- `TOKEN_PROFILE_UNSUPPORTED`
- `ALGORITHM_NOT_ALLOWED`
- `KEY_NOT_FOUND`
- `SIGNATURE_INVALID`
- `ISSUER_MISMATCH`
- `AUDIENCE_MISMATCH`
- `TOKEN_EXPIRED`
- `TOKEN_NOT_YET_VALID`
- `CLAIM_VALIDATION_FAILED`
- `TOKEN_REVOKED`

Đây là mã nội bộ của ứng dụng, không bắt buộc trùng tên exception của thư viện hoặc error code công khai của giao thức.

### Unavailable

Dùng khi không thể đưa ra quyết định do dependency hoặc trạng thái cần thiết tạm thời không khả dụng:

- `JWKS_ENDPOINT_UNAVAILABLE`
- `KEY_STORE_UNAVAILABLE`
- `INTROSPECTION_UNAVAILABLE`
- `REVOCATION_STORE_UNAVAILABLE`
- `REPLAY_STORE_UNAVAILABLE`
- `DEPENDENCY_TIMEOUT`

Không được coi JWKS timeout là chữ ký sai. Nếu không lấy được khóa và không có cache đủ tin cậy, verifier chưa có bằng chứng để kết luận chữ ký hợp lệ hay không.

Trường `retryable` phải phản ánh việc thử lại có an toàn hay không. Ví dụ, một assertion dùng một lần có thể đã ghi `jti` trước khi request timeout; gửi lại nguyên assertion có thể bị từ chối như replay. Không retry mọi lỗi theo cùng một quy tắc.

### InternalFailure

Dùng cho lỗi cấu hình, runtime hoặc lỗi bất ngờ khiến verifier không thể thực hiện đúng hợp đồng:

- `VERIFIER_MISCONFIGURED`
- `TRUST_CONFIGURATION_INVALID`
- `CRYPTO_PROVIDER_FAILURE`
- `UNEXPECTED_VERIFIER_ERROR`

Không đưa raw token, secret, private key path hoặc stack trace vào đối tượng kết quả có thể đi qua nhiều tầng. Gắn incident/correlation ID để tra cứu chi tiết trong log nội bộ có kiểm soát.

## 4. Chuẩn hóa lỗi theo từng giai đoạn xác minh

Adapter nên phân loại theo giai đoạn, bởi vì lỗi ở mỗi giai đoạn có ý nghĩa và cách xử lý khác nhau.

~~~mermaid
flowchart TD
    A["Extract credential"] --> B["Parse compact token"]
    B --> C["Check JOSE header/profile"]
    C --> D["Resolve trusted key"]
    D --> E["Verify signature / decrypt JWE"]
    E --> F["Validate claims"]
    F --> G["Build Valid result"]
    B -. "Malformed" .-> R["Rejected"]
    C -. "Disallowed" .-> R
    D -. "Key source unavailable" .-> U["Unavailable"]
    D -. "No matching trusted key" .-> R
    E -. "Signature/tag mismatch" .-> R
    E -. "Provider failure" .-> I["InternalFailure"]
    F -. "Claim violation" .-> R
~~~

### Giai đoạn 1 — Nhận credential

Đây là bước xử lý giao thức trước khi gọi thư viện:

- Không có credential: `CREDENTIAL_MISSING`.
- Bearer scheme sai cú pháp hoặc có nhiều nguồn credential xung đột: `CREDENTIAL_MALFORMED` hoặc lỗi request theo hợp đồng API.
- Token vượt giới hạn kích thước: từ chối request trước khi parse.
- Endpoint nhận credential qua nguồn không được hỗ trợ: từ chối request.

Cần phân biệt lỗi cú pháp HTTP Authorization với lỗi cấu trúc JWT. Không ghi giá trị credential khi chẩn đoán.

### Giai đoạn 2 — Parse Compact Serialization

Base64url sai, số segment không đúng, JSON không hợp lệ hoặc cấu trúc JOSE sai có thể được ánh xạ thành `TOKEN_MALFORMED`.

Không parse một phần rồi sử dụng claims trước khi xác minh hoàn tất. Không fallback sang định dạng khác ngoài profile đã định nghĩa.

### Giai đoạn 3 — Kiểm tra JOSE header và profile

Thuật toán không nằm trong allowlist, `alg: none`, `crit` không được hỗ trợ, loại token sai hoặc cấu trúc JWE không được phép có thể ánh xạ thành:

- `ALGORITHM_NOT_ALLOWED`
- `TOKEN_PROFILE_UNSUPPORTED`
- `JOSE_HEADER_INVALID`

Các giá trị `alg`, `kid`, `typ`, `jku` và `x5u` do token cung cấp phải được xử lý theo trust configuration. Không để token tự chọn thuật toán hoặc nguồn khóa tùy ý.

### Giai đoạn 4 — Tìm khóa tin cậy

Cần phân biệt:

- Không có khóa phù hợp sau khi refresh thành công từ nguồn tin cậy: `KEY_NOT_FOUND` hoặc `UNKNOWN_KEY_ID`.
- Không truy cập được JWKS/key store và không có cache đủ để xác minh: `JWKS_ENDPOINT_UNAVAILABLE` hoặc `KEY_STORE_UNAVAILABLE`.
- JWKS sai định dạng hoặc vi phạm trust configuration: `TRUST_CONFIGURATION_INVALID` hoặc lỗi phụ thuộc phù hợp.

Không được coi “không tải được khóa” là “chữ ký sai”.

### Giai đoạn 5 — Xác minh mật mã

- Chữ ký không khớp với signing input và khóa tin cậy: `SIGNATURE_INVALID`.
- MAC không khớp: `SIGNATURE_INVALID` hoặc mã riêng `MAC_INVALID`.
- JWE authentication tag không hợp lệ: `DECRYPTION_AUTHENTICATION_FAILED`.
- Crypto provider gặp lỗi runtime/cấu hình: `CRYPTO_PROVIDER_FAILURE`.

Không tiết lộ chi tiết các lỗi này cho caller không tin cậy. API có thể gộp nhiều lỗi credential thành response tổng quát để giảm khả năng dò cấu hình.

### Giai đoạn 6 — Kiểm tra claims và token profile

Sau khi xác minh mật mã, kiểm tra:

- `iss`: issuer có nằm trong trust configuration không?
- `aud`: token có dành cho resource/service hiện tại không?
- `exp` và `nbf`: token có nằm trong khoảng hiệu lực không?
- `iat`: có nằm trong giới hạn tuổi token nếu profile đặt ra không?
- `sub`: subject có đúng kiểu và có mặt khi profile yêu cầu không?
- `jti`: có bị thu hồi hoặc đã dùng nếu token yêu cầu one-time use không?
- `typ` và các claim profile: token có đúng loại access token/assertion/ID token không?
- Tenant, client hoặc delegation claims có đáp ứng policy không?

Claim thiếu hoặc sai kiểu là lỗi profile/claim, không phải lỗi chữ ký.

## 5. Bảng ánh xạ lỗi chuẩn

Bảng sau là gợi ý cho hợp đồng nội bộ. Ứng dụng có thể dùng mã chi tiết hơn, nhưng cần giữ nhất quán giữa các adapter và service.

| Giai đoạn | Tình huống | Kết quả chuẩn | Có thể thử lại? |
| --- | --- | --- | --- |
| Credential extraction | Không có token | `CREDENTIAL_MISSING` | Không; client cần gửi credential |
| Credential extraction | Bearer syntax sai | `CREDENTIAL_MALFORMED` | Không; sửa request |
| Parse | Compact token sai cấu trúc | `TOKEN_MALFORMED` | Không |
| JOSE header | Thuật toán không cho phép | `ALGORITHM_NOT_ALLOWED` | Không |
| JOSE header | Token profile không hỗ trợ | `TOKEN_PROFILE_UNSUPPORTED` | Không |
| Key resolution | Không tìm thấy KID sau refresh thành công | `KEY_NOT_FOUND` | Thường không; kiểm tra rollout/configuration |
| Key resolution | JWKS/key store timeout | `JWKS_ENDPOINT_UNAVAILABLE` | Có điều kiện, theo retry policy |
| Signature | Chữ ký không hợp lệ | `SIGNATURE_INVALID` | Không |
| JWE | Authentication tag/decryption không hợp lệ | `DECRYPTION_AUTHENTICATION_FAILED` | Không |
| Claims | Issuer sai | `ISSUER_MISMATCH` | Không |
| Claims | Audience sai | `AUDIENCE_MISMATCH` | Không |
| Claims | Token hết hạn | `TOKEN_EXPIRED` | Không; cần credential mới |
| Claims | Token chưa có hiệu lực | `TOKEN_NOT_YET_VALID` | Chờ đến thời điểm hợp lệ, không retry liên tục |
| Claims | Token bị thu hồi | `TOKEN_REVOKED` | Không; cần credential/phiên mới |
| Revocation | Kho thu hồi không khả dụng | `REVOCATION_STORE_UNAVAILABLE` | Có điều kiện; không bỏ qua kiểm tra |
| Replay | Replay store không khả dụng | `REPLAY_STORE_UNAVAILABLE` | Không chấp nhận one-time assertion khi chưa kiểm tra |
| Crypto runtime | Provider/cấu hình crypto lỗi | `CRYPTO_PROVIDER_FAILURE` | Xử lý lỗi vận hành trước |
| Authorization | Thiếu scope/permission | `INSUFFICIENT_PERMISSION` | Không, trừ khi quyền được cấp lại |
| Authorization | Không sở hữu tài nguyên | `RESOURCE_ACCESS_DENIED` | Không |

Một số lỗi thuộc tầng request hoặc authorization, không phải verifier. Giữ ranh giới này giúp telemetry và response mapping phản ánh đúng nguyên nhân.

## 6. Tách verification khỏi authorization

Sau khi verifier trả Valid, ứng dụng mới có security context đáng tin cậy để kiểm tra quyền.

Ví dụ token:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893459600
}
~~~

Request đọc đơn hàng có thể được cho phép. Request xóa đơn hàng phải bị từ chối nếu policy yêu cầu `orders:delete`.

Không biến `INSUFFICIENT_PERMISSION` thành `SIGNATURE_INVALID` hoặc `TOKEN_INVALID`. Việc đó làm metrics xác minh sai lệch, khiến client refresh token dù quyền chưa được cấp và làm mất ý nghĩa audit.

~~~text
verification = verifyCredential(request.credential)

if verification is not Valid:
    return mapVerificationFailure(verification)

decision = authorize(
    principal = verification.principal,
    action = request.action,
    resource = request.resource
)

if decision is Denied:
    return Forbidden(decision.reason)

return executeBusinessOperation()
~~~

Kết quả Valid không nên tự mang cờ `isAdmin` do ứng dụng suy diễn mà không có policy. Quyền cần được đánh giá theo claims đã xác minh và dữ liệu tài nguyên hiện tại.

## 7. Ánh xạ kết quả nội bộ sang HTTP response

Kết quả nội bộ không nên được trả nguyên vẹn cho client. API layer ánh xạ theo giao thức và hợp đồng công khai.

Với protected resource dùng Bearer token, RFC 6750 định nghĩa các error code `invalid_request`, `invalid_token` và `insufficient_scope`. Mapping phổ biến:

| Kết quả nội bộ | HTTP thường dùng | Response công khai |
| --- | ---: | --- |
| Không có credential khi endpoint yêu cầu | 401 | `WWW-Authenticate: Bearer` |
| Credential sai cú pháp | 400 hoặc 401 theo loại lỗi/hợp đồng | `invalid_request` nếu request sai định dạng |
| Token sai, hết hạn, sai issuer/audience hoặc chữ ký | 401 | `invalid_token` |
| Token hợp lệ nhưng thiếu scope | 403 | `insufficient_scope` |
| Token hợp lệ nhưng không được phép truy cập tài nguyên | 403 | Thông báo authorization tổng quát |
| JWKS/introspection/revocation dependency không khả dụng | 503 hoặc 5xx phù hợp | Lỗi dịch vụ tạm thời |
| Verifier cấu hình sai hoặc crypto provider lỗi | 500/503 theo phân loại vận hành | Lỗi máy chủ tổng quát |

Không nên dùng 401 cho mọi lỗi. Nếu hệ thống không thể xác minh vì dependency lỗi, 503 thường phản ánh đúng hơn trạng thái dịch vụ. Mã cụ thể vẫn cần theo hợp đồng API và semantics của giao thức.

Ví dụ token invalid:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
Content-Type: application/json

{
  "error": "invalid_token",
  "request_id": "req-8d21"
}
~~~

Ví dụ thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Cache-Control: no-store
Content-Type: application/json

{
  "error": "forbidden",
  "request_id": "req-8d22"
}
~~~

Ví dụ dependency không khả dụng:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 5
Cache-Control: no-store
Content-Type: application/json

{
  "error": "temporarily_unavailable",
  "request_id": "req-8d23"
}
~~~

Không trả KID nội bộ, JWKS URI, stack trace, exception class, raw token, decoded claims hoặc tên key store cho caller không tin cậy.

## 8. Adapter xử lý exception từ thư viện

Adapter là nơi duy nhất nên biết exception cụ thể của thư viện. Các tầng nghiệp vụ không nên phụ thuộc trực tiếp vào tên exception của vendor.

~~~mermaid
flowchart LR
    A["JWT / JOSE Library"] --> B["Library-specific result or exception"]
    B --> C["Verification Adapter"]
    C --> D["Normalized VerificationResult"]
    D --> E["Application Security Layer"]
    E --> F["HTTP / Message / Job Response"]
~~~

Quy tắc triển khai:

- Bắt các loại lỗi đã biết và ánh xạ có chủ đích.
- Giữ nguyên nguyên nhân kỹ thuật trong log nội bộ có kiểm soát, nhưng không chuyển exception ra ngoài.
- Không dùng catch-all để đổi mọi exception thành `TOKEN_INVALID`.
- Exception không nhận diện phải trở thành `InternalFailure` và phát cảnh báo.
- Nếu thư viện cung cấp structured error code, ưu tiên code đó thay vì parse message.
- Không phụ thuộc exception message vì nội dung có thể đổi theo version, locale hoặc provider.
- Không để exception chứa raw token đi vào logger mặc định.

Ví dụ pseudocode trung lập ngôn ngữ:

~~~text
function verifyWithAdapter(rawToken, profile):
    try:
        libraryResult = jwtLibrary.verify(rawToken, profile.trustConfig)

        if libraryResult.isValid:
            return Valid(mapVerifiedClaims(libraryResult, profile))

        return mapStructuredLibraryFailure(libraryResult.error)

    catch KnownMalformedTokenError:
        return Rejected("TOKEN_MALFORMED")

    catch KnownSignatureMismatchError:
        return Rejected("SIGNATURE_INVALID")

    catch KnownKeyStoreUnavailableError:
        return Unavailable(
            reasonCode = "KEY_STORE_UNAVAILABLE",
            retryable = true
        )

    catch KnownVerifierConfigurationError:
        return InternalFailure("VERIFIER_MISCONFIGURED")

    catch unexpected:
        logSanitizedFailure(unexpected)
        return InternalFailure("UNEXPECTED_VERIFIER_ERROR")
~~~

Đây là pseudocode mô tả ranh giới kiến trúc, không phải API của một thư viện cụ thể. Adapter thực tế phải dựa trên taxonomy exception/result mà thư viện đang dùng cung cấp.

## 9. Retry, timeout và fail-closed

Không phải mọi lỗi đều có thể thử lại. Retry sai có thể làm tăng tải, tạo request storm hoặc thay đổi semantics của token dùng một lần.

| Lỗi | Retry policy gợi ý |
| --- | --- |
| Token malformed/signature invalid | Không retry; credential không thay đổi |
| Issuer/audience mismatch | Không retry; cần token đúng profile |
| Unknown KID sau refresh thành công | Không retry liên tục; kiểm tra issuer/JWKS rollout |
| JWKS timeout | Retry có giới hạn với backoff và jitter |
| Introspection timeout | Retry có giới hạn; không chấp nhận token khi chưa có quyết định |
| Replay store unavailable | Không bỏ qua replay check cho one-time token |
| Crypto provider misconfigured | Xử lý cấu hình/runtime, không retry request liên tục |
| Token expired | Cần credential mới hoặc refresh theo giao thức |

Fail-closed nghĩa là không cho request tiếp tục khi chưa có bằng chứng xác minh đủ tin cậy. Nó không có nghĩa mọi lỗi đều phải trả 401:

- Credential sai: 401.
- Credential hợp lệ nhưng thiếu quyền: 403.
- Dependency xác minh không khả dụng: 503/5xx.
- Lỗi cấu hình nội bộ: 500/503 và cảnh báo vận hành.

Không fallback sang decode-only, bỏ qua audience, chấp nhận `alg: none`, tin claims chưa xác minh hoặc bỏ qua revocation vì JWKS/authorization service đang lỗi.

Nếu verifier phụ thuộc JWKS, introspection hoặc revocation store:

- Đặt timeout rõ ràng cho từng dependency.
- Dùng bounded retry, backoff và jitter.
- Gộp request refresh JWKS khi nhiều request gặp unknown KID cùng lúc.
- Dùng circuit breaker để tránh làm quá tải dependency đang lỗi.
- Chỉ dùng cache trong thời gian freshness đã quy định.
- Không để circuit breaker mở khiến token được chấp nhận mà không xác minh.

Khi circuit breaker mở, kết quả nên là Unavailable hoặc lỗi dịch vụ, trừ khi có policy cache/offline được thiết kế và phê duyệt trước.

## 10. Chỉ dùng claims sau khi xác minh hoàn tất

Một lỗi nghiêm trọng là parse payload, lấy `sub`, `role` hoặc `tenant` rồi dùng chúng cho authorization trước khi chữ ký được xác minh.

Luồng an toàn:

1. Parse cấu trúc token để xác định cách xử lý, nhưng chưa tin claims.
2. Chọn profile và khóa từ trust configuration.
3. Xác minh chữ ký/MAC hoặc giải mã JWE có xác thực.
4. Kiểm tra issuer, audience, thời hạn và claims profile.
5. Chỉ sau đó mới tạo principal/security context.
6. Thực hiện authorization theo action/resource.

Không log hoặc đưa claims chưa xác minh vào audit như danh tính đã xác thực. Nếu cần ghi nhận KID hoặc issuer để chẩn đoán trước verify, phải đánh dấu rõ là dữ liệu chưa tin cậy và giới hạn nội dung được ghi.

## 11. Observability: log reason code, không log credential

Chuẩn hóa kết quả cho phép metrics và audit nhất quán mà không tiết lộ token.

Ví dụ structured log:

~~~json
{
  "event": "jwt_verification",
  "request_id": "req-8d21",
  "service": "orders-api",
  "profile": "access_token",
  "outcome": "REJECTED",
  "reason_code": "AUDIENCE_MISMATCH",
  "issuer_alias": "primary-identity",
  "key_id": "signing-k2",
  "region": "region-a",
  "duration_ms": 4
}
~~~

Issuer alias, KID, subject pseudonym hoặc tenant chỉ nên được ghi khi policy dữ liệu cho phép. Không ghi raw JWT, Authorization header, Cookie, refresh token, client assertion, private key hoặc toàn bộ payload.

Metrics nên theo dõi:

- Tỷ lệ `Valid`, `Rejected`, `Unavailable` và `InternalFailure`.
- Tỷ lệ lỗi theo reason code, issuer alias, token profile và service.
- Tỷ lệ `KEY_NOT_FOUND`, signature failure và audience mismatch.
- JWKS refresh latency, timeout và cache age.
- Introspection/revocation dependency availability.
- Thời gian xác minh p50/p95/p99.
- Tỷ lệ authorization denied do thiếu scope hoặc resource policy.
- Số lỗi bất ngờ từ adapter sau khi nâng cấp thư viện.

Không dùng `sub`, token ID hoặc giá trị credential làm metric label có cardinality cao. Dùng label giới hạn hoặc pseudonymous correlation nếu cần.

## 12. Kiểm thử hợp đồng chuẩn

Khi thay thư viện JWT hoặc nâng phiên bản, cần kiểm tra adapter vẫn ánh xạ cùng một tình huống sang cùng kết quả chuẩn.

| Test case | Kết quả chuẩn mong đợi |
| --- | --- |
| JWT hợp lệ, đúng issuer/audience/profile | `Valid` |
| Không có credential | `CREDENTIAL_MISSING` |
| Compact serialization sai | `TOKEN_MALFORMED` |
| Thuật toán không nằm trong allowlist | `ALGORITHM_NOT_ALLOWED` |
| Chữ ký sai | `SIGNATURE_INVALID` |
| Không tìm thấy KID sau refresh thành công | `KEY_NOT_FOUND` |
| JWKS endpoint timeout | `Unavailable(JWKS_ENDPOINT_UNAVAILABLE)` |
| Issuer sai | `ISSUER_MISMATCH` |
| Audience sai | `AUDIENCE_MISMATCH` |
| Token hết hạn | `TOKEN_EXPIRED` |
| Token chưa tới nbf | `TOKEN_NOT_YET_VALID` |
| Token bị thu hồi | `TOKEN_REVOKED` |
| Replay store lỗi với one-time assertion | `Unavailable(REPLAY_STORE_UNAVAILABLE)` |
| Token hợp lệ nhưng thiếu scope | `Valid` rồi authorization `Forbidden` |
| Token hợp lệ nhưng không sở hữu resource | `Valid` rồi `RESOURCE_ACCESS_DENIED` |
| Crypto provider lỗi cấu hình | `InternalFailure(CRYPTO_PROVIDER_FAILURE)` |
| Exception không nhận diện | `InternalFailure(UNEXPECTED_VERIFIER_ERROR)` |

### Contract test giữa các adapter

Nếu ứng dụng hỗ trợ nhiều thư viện hoặc runtime, dùng cùng bộ test vector và kỳ vọng:

- Mỗi adapter trả cùng outcome cho cùng input.
- Reason code nội bộ không phụ thuộc tên exception vendor.
- Không adapter nào chấp nhận token mà profile cấm.
- Không adapter nào sử dụng claims trước khi xác minh xong.
- Lỗi dependency được phân biệt với credential rejection.
- Response công khai không để lộ raw token hoặc chi tiết nội bộ.
- Upgrade thư viện không âm thầm thay đổi semantics của lỗi.

Cần có test cho lỗi đồng thời, timeout, key rotation, unknown KID và cache stale; các trường hợp này thường tạo ra khác biệt giữa thư viện hoặc môi trường.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ trả boolean valid/invalid | Mất phân biệt token sai và dependency lỗi | Dùng kiểu kết quả có outcome và reason code |
| Catch mọi exception rồi trả 401 | Lỗi JWKS/configuration bị báo nhầm thành token sai | Phân loại Rejected, Unavailable và InternalFailure |
| Dùng exception message làm API response | Lộ token, claims, key path hoặc cấu hình | Map sang error code công khai ổn định |
| Dùng exception class trực tiếp trong business logic | Khóa chặt ứng dụng vào một thư viện | Chuẩn hóa tại adapter |
| Parse claims rồi authorize trước khi verify | Token giả có thể tự khai subject/role | Chỉ tạo principal sau khi xác minh hoàn tất |
| Gộp thiếu scope với invalid token | Metrics và hành vi client sai | Tách verification khỏi authorization |
| Coi JWKS timeout là signature invalid | Chẩn đoán sai và có thể gây refresh credential không cần thiết | Dùng Unavailable |
| Retry mọi exception | Request storm và replay side effects | Retry có điều kiện, bounded backoff |
| Trả reason code nội bộ ra public | Tạo oracle dò token/key/policy | Dùng response tổng quát theo giao thức |
| Log toàn bộ token để điều tra | Bearer credential bị lưu ở nhiều hệ thống | Log metadata tối thiểu, redact trước khi ghi |
| Cache kết quả xác minh vô thời hạn | Token hoặc key đã hết hạn/thu hồi vẫn được tin | TTL theo exp, key state và policy |
| Không contract-test khi đổi thư viện | Hành vi lỗi thay đổi âm thầm | Dùng bộ test vector chung cho adapter |

## 14. Checklist triển khai chuẩn hóa

**Thiết kế hợp đồng**

- Định nghĩa rõ `Valid`, `Rejected`, `Unavailable` và `InternalFailure`.
- Tách verification result khỏi authorization decision.
- Chuẩn hóa reason code nội bộ, không phụ thuộc vendor exception.
- Xác định trường nào được đưa vào principal/security context.
- Chỉ tạo context sau khi toàn bộ token profile validation hoàn tất.

**Adapter thư viện**

- Bắt và ánh xạ các lỗi đã biết theo từng giai đoạn.
- Dùng structured error code nếu thư viện hỗ trợ.
- Không parse exception message để quyết định logic nếu có lựa chọn tốt hơn.
- Không catch-all thành invalid token.
- Che raw token và claims khỏi exception/log mặc định.
- Kiểm thử adapter với test vector chung.

**API và vận hành**

- Map invalid credential, insufficient permission và dependency failure thành phản hồi phù hợp.
- Dùng 401 cho credential không hợp lệ, 403 cho thiếu quyền và 503/5xx cho dependency/service failure theo hợp đồng.
- Không tiết lộ stack trace, JWKS URI, key path hoặc token.
- Áp dụng timeout, bounded retry, backoff, jitter và circuit breaker.
- Fail closed khi chưa thể xác minh; không bỏ qua kiểm tra.
- Log reason code và correlation ID, không log credential.
- Theo dõi tỷ lệ outcome, reason code và dependency latency.
- Kiểm tra lại semantics sau mỗi lần nâng cấp hoặc thay thư viện.

**Ghi nhớ:** Chuẩn hóa kết quả giúp ứng dụng phân biệt credential hợp lệ, credential bị từ chối, thiếu quyền và lỗi vận hành. Adapter chuyển exception/result riêng của thư viện thành hợp đồng nội bộ ổn định; tầng ứng dụng chỉ dùng principal sau khi xác minh hoàn tất. Không biến mọi exception thành 401, không dùng claims chưa xác minh và không trả chi tiết nội bộ cho client. Fail closed là không chấp nhận khi chưa xác minh được; response vẫn cần phân biệt token sai với dịch vụ xác minh đang không khả dụng.

### Tài liệu chuẩn để tra cứu

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** error response invalid_request, invalid_token, insufficient_scope và HTTP status liên quan.
- **RFC 7515 — JSON Web Signature (JWS):** xác minh chữ ký và xử lý protected header.
- **RFC 7516 — JSON Web Encryption (JWE):** giải mã và xác thực nội dung JWE.
- **RFC 7519 — JSON Web Token (JWT):** registered claims và cách diễn giải token.
- **RFC 8725 — JSON Web Token Best Current Practices:** kiểm tra issuer, audience, algorithm và phân biệt token profile.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** các yêu cầu validation cho JWT access token.
- **RFC 9110 — HTTP Semantics:** semantics của HTTP status code và response.
