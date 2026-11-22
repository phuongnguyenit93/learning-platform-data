# Cảnh báo bất thường về kid, issuer và tỷ lệ lỗi

## 1. Vì sao cần theo dõi bất thường khi xác minh JWT?

Trong hệ thống dùng JWT, phần lớn request hợp lệ có thể đi qua bước xác minh mà không cần can thiệp của vận hành. Tuy nhiên, những thay đổi bất thường về `kid`, `iss`, tỷ lệ chữ ký sai, audience mismatch hoặc lỗi truy cập JWKS có thể báo hiệu:

- Một đợt xoay vòng khóa chưa được phân phối đồng đều.
- Issuer hoặc cấu hình trust bị thay đổi sai.
- Client đang gửi nhầm loại token hoặc token dành cho API khác.
- Một endpoint JWKS, key store hoặc dịch vụ introspection gặp sự cố.
- Attacker đang thử token giả, dò `kid`, giả mạo issuer hoặc tạo request khiến verifier refresh khóa liên tục.
- Một signing key bị lộ hoặc token được phát hành ngoài quy trình dự kiến.

Nếu chỉ theo dõi tổng số HTTP 401, đội vận hành khó phân biệt token không hợp lệ với sự cố dependency, lỗi triển khai hoặc một cuộc tấn công. Cần quan sát kết quả xác minh theo từng nguyên nhân, issuer đã cấu hình, service, token profile và region.

**Mục tiêu:** phát hiện sớm thay đổi bất thường, phân biệt lỗi credential với lỗi hạ tầng và cung cấp đủ bằng chứng để điều tra mà không ghi hoặc phát tán raw JWT.

## 2. Hiểu đúng kid và iss trước khi tạo cảnh báo

### kid là gợi ý chọn khóa, không phải bằng chứng tin cậy

`kid` (Key ID) thường xuất hiện trong JOSE header để giúp verifier chọn JWK phù hợp trong một tập khóa đã được cấu hình tin cậy. Nó không tự xác minh chữ ký và không chứng minh token được phát hành bởi issuer đáng tin.

Một `kid` có thể không tồn tại, bị lặp trong các issuer khác nhau hoặc do attacker tự đặt trong token giả. Vì vậy:

- Phạm vi tra cứu khóa cần gắn với issuer/trust configuration, không chỉ dựa trên chuỗi `kid`.
- Không dùng `kid` từ token để truy cập URL hoặc key store tùy ý.
- Không tự động tải JWKS từ một địa chỉ do token cung cấp nếu địa chỉ đó chưa được trust configuration cho phép.
- Không tạo metric label tự do từ mọi giá trị `kid`; attacker có thể tạo vô số giá trị khác nhau và làm bùng nổ cardinality.

Trong telemetry, nên theo dõi `kid` đã biết theo alias hoặc key version đã đăng ký. Với `kid` không nhận diện, dùng nhóm `unknown` và có thể ghi fingerprint đã giới hạn trong log bảo mật nếu thật sự cần điều tra.

### iss là claim phải được xác minh

`iss` xác định issuer tự khai trong payload. Trước khi token được xác minh, giá trị này vẫn là dữ liệu không tin cậy.

Một hệ thống có thể dùng giá trị `iss` để chọn một profile trong danh sách issuer được cấu hình sẵn, nhưng phải giới hạn lựa chọn trong allowlist và sau đó xác minh chữ ký cùng issuer theo profile đó. Không dùng `iss` chưa xác minh để tự động discovery hoặc gọi metadata/JWKS tại một host tùy ý.

Cần phân biệt:

- **Unconfigured issuer:** issuer không nằm trong trust configuration.
- **Issuer mismatch:** chữ ký có thể hợp lệ theo một khóa nhưng claim `iss` không khớp issuer được kỳ vọng.
- **Issuer dependency unavailable:** nguồn metadata/JWKS của issuer đã tin cậy tạm thời không truy cập được.
- **Issuer configuration changed:** cấu hình issuer được thay đổi có chủ đích qua quy trình quản trị.

Các tình huống này có ý nghĩa vận hành khác nhau và không nên gộp vào một cảnh báo “JWT invalid”.

## 3. Xây dựng taxonomy kết quả xác minh để quan sát

Metrics và cảnh báo chỉ có ý nghĩa khi mọi verifier phân loại lỗi nhất quán. Một taxonomy cơ bản:

| Outcome / reason | Ý nghĩa | Diễn giải vận hành |
| --- | --- | --- |
| `VALID` | Token đáp ứng profile và xác minh thành công | Request có thể chuyển sang authorization |
| `TOKEN_MALFORMED` | Compact serialization, Base64url hoặc JSON sai | Client lỗi, token bị cắt hoặc dữ liệu thử nghiệm/tấn công |
| `ALGORITHM_NOT_ALLOWED` | Thuật toán không nằm trong policy | Token sai profile hoặc hoạt động dò thuật toán |
| `KEY_NOT_FOUND` | Không có khóa phù hợp sau khi truy vấn nguồn tin cậy thành công | Sai `kid`, rollout khóa chưa đồng bộ hoặc token giả |
| `JWKS_UNAVAILABLE` | Không thể truy cập nguồn khóa và không có cache đủ để xác minh | Sự cố dependency |
| `SIGNATURE_INVALID` | Chữ ký/MAC không hợp lệ theo khóa đã chọn | Token bị sửa, ký bằng khóa khác hoặc cấu hình issuer sai |
| `ISSUER_MISMATCH` | Claim issuer không khớp profile tin cậy | Token bị gửi nhầm hoặc cấu hình sai |
| `UNTRUSTED_ISSUER` | Issuer không được cấu hình tin cậy | Token ngoài hệ thống hoặc thử giả mạo issuer |
| `AUDIENCE_MISMATCH` | Token không dành cho resource hiện tại | Gọi nhầm API hoặc token substitution |
| `TOKEN_EXPIRED` | `exp` đã qua theo clock policy | Client giữ token cũ, clock lệch hoặc replay token cũ |
| `TOKEN_REVOKED` | Trạng thái token/session cho biết đã bị thu hồi | Logout, incident response hoặc reuse detection |
| `REVOCATION_UNAVAILABLE` | Không kiểm tra được trạng thái thu hồi bắt buộc | Dependency lỗi; không thể kết luận token còn active |
| `INTERNAL_FAILURE` | Lỗi cấu hình hoặc runtime của verifier | Lỗi triển khai hoặc thành phần mật mã |

`INSUFFICIENT_PERMISSION` và `RESOURCE_ACCESS_DENIED` thuộc authorization sau khi token đã hợp lệ. Theo dõi chúng riêng để tránh làm sai tỷ lệ lỗi xác minh.

Một request không có credential cũng cần được đếm riêng nếu endpoint yêu cầu xác thực; đừng trộn nó vào tỷ lệ token signature failure.

## 4. Những metric cơ bản cần có

Metric nên mô tả số lần xác minh, kết quả, dependency và độ trễ. Ví dụ tên trung lập:

~~~text
jwt_verification_total{
    outcome,
    reason_code,
    issuer_alias,
    token_profile,
    service,
    region
}

jwt_jwks_refresh_total{
    result,
    issuer_alias,
    region
}

jwt_unknown_kid_total{
    issuer_alias,
    service,
    region
}

jwt_verification_duration_seconds
jwt_jwks_cache_age_seconds
jwt_jwks_refresh_failure_total
jwt_revocation_lookup_total
jwt_revocation_lookup_duration_seconds
~~~

Các label như `issuer_alias`, `service`, `region`, `token_profile`, `outcome` và `reason_code` nên đến từ danh mục được kiểm soát. Không dùng raw token, subject, arbitrary `iss` hoặc mọi `kid` do caller gửi làm label.

### Tách số lượng và tỷ lệ

Chỉ nhìn tỷ lệ có thể gây hiểu nhầm khi traffic thấp. Chỉ nhìn số lượng tuyệt đối cũng có thể gây báo động khi lưu lượng tăng theo giờ cao điểm.

Theo dõi đồng thời:

- Tổng số credential được gửi tới verifier.
- Số và tỷ lệ `VALID`.
- Số và tỷ lệ `REJECTED` theo reason code.
- Số `UNAVAILABLE` hoặc `INTERNAL_FAILURE`.
- Số request không có credential.
- Tổng request đến endpoint để hiểu mẫu số và lưu lượng.

Ví dụ công thức:

~~~text
invalidTokenRate =
    rejectedCredentialCount / credentialAttemptCount

unknownKidRate =
    unknownKidCount / credentialAttemptCount

jwksFailureRate =
    failedJwksRefreshCount / jwksRefreshAttemptCount

verificationAvailability =
    (validCount + rejectedCount) / credentialAttemptCount
~~~

`verificationAvailability` ở đây đo khả năng verifier đưa ra kết luận, dù kết luận là chấp nhận hay từ chối. Nó không phải tỷ lệ request thành công của API. `UNAVAILABLE` và lỗi nội bộ làm giảm khả năng đưa ra kết luận; token sai vẫn có thể được xử lý bình thường bằng một kết quả `REJECTED`.

Không đưa authorization denied vào tử số `invalidTokenRate`.

## 5. Phát hiện bất thường về kid

Các tín hiệu hữu ích gồm:

- Tăng đột ngột số token có `kid` không tồn tại.
- Số lượng `kid` duy nhất tăng nhanh bất thường.
- Tỷ lệ unknown `kid` tăng ở một issuer hoặc region cụ thể.
- JWKS refresh được kích hoạt liên tục do unknown `kid`.
- Một `kid` đã bị thu hồi vẫn xuất hiện trong request.
- Verifier bắt đầu từ chối `kid` mới ngay sau một đợt key rotation.
- Các service có cache JWKS khác nhau cho cùng issuer.

### Phân biệt rotation bình thường với hoạt động bất thường

Trong rotation có kế hoạch, thường thấy public JWK mới được công bố trước khi issuer bắt đầu ký token bằng khóa mới. Sau cutover, verifier có thể nhận token với `kid` mới; nếu cache đã được cập nhật, xác minh vẫn thành công.

Nếu issuer bắt đầu dùng khóa mới trước khi JWKS lan truyền, `KEY_NOT_FOUND` có thể tăng trong thời gian ngắn. Đây là tín hiệu rollout chưa đồng bộ. Ngược lại, một lượng lớn `kid` ngẫu nhiên khác nhau, đặc biệt khi đi kèm refresh storm, có thể là hoạt động gây tải hoặc dò tìm.

| Quan sát | Khả năng cần điều tra |
| --- | --- |
| Một `kid` mới xuất hiện cùng thời điểm thay đổi key đã lên lịch | Rotation hoặc rollout |
| Unknown `kid` tăng trên một region nhưng region khác bình thường | Cache/JWKS propagation không đồng đều |
| Nhiều `kid` duy nhất, phần lớn chỉ xuất hiện một lần | Token giả hoặc hoạt động dò `kid` |
| Unknown `kid` tăng cùng JWKS timeout | Dependency hoặc mạng có vấn đề |
| `kid` đã bị revoked vẫn xuất hiện và chữ ký xác minh được bằng cache cũ | Revocation propagation chưa hoàn tất |
| Một `kid` hợp lệ đột nhiên có signature failure diện rộng | Sai key material, issuer ký sai hoặc dữ liệu token bị thay đổi |

### Bảo vệ JWKS refresh khỏi request storm

Nếu mỗi token với `kid` chưa biết đều kích hoạt một lần tải JWKS, attacker có thể tạo nhiều `kid` ngẫu nhiên để ép verifier gọi endpoint khóa liên tục.

Các biện pháp vận hành:

- Gộp các refresh đồng thời cho cùng issuer bằng single-flight/coalescing.
- Rate limit refresh theo issuer và verifier.
- Dùng negative cache ngắn cho `kid` không tìm thấy sau khi đã refresh thành công.
- Đặt timeout, backoff và jitter cho JWKS fetch.
- Không refresh vô hạn chỉ vì mỗi request gửi một `kid` mới.
- Giữ cache hợp lệ theo policy khi dependency lỗi; không coi cache stale vô thời hạn là đáng tin.
- Phân biệt `KEY_NOT_FOUND` sau refresh thành công với `JWKS_UNAVAILABLE`.

Negative cache phải ngắn và có giới hạn để không chặn khóa mới vừa được công bố. Khi có rotation khẩn cấp hoặc event invalidation đáng tin cậy, cần cơ chế xóa negative cache.

## 6. Phát hiện bất thường về issuer

Các mẫu bất thường có thể gồm:

- Issuer ngoài allowlist tăng đột ngột.
- Một client vốn chỉ dùng issuer A bắt đầu gửi token khai issuer B.
- Claim `iss` không khớp issuer được chọn từ trust configuration.
- Một issuer hợp lệ đột nhiên có nhiều `KEY_NOT_FOUND` hoặc `SIGNATURE_INVALID`.
- Metadata/JWKS endpoint của một issuer được tin cậy không truy cập được.
- Request đến sai service nhưng mang token có issuer hợp lệ và audience không phù hợp.

### Không tự động tin issuer mới

Nếu thấy issuer lạ, không thêm nó vào allowlist chỉ để giảm tỷ lệ lỗi. Cần xác minh nguồn phát hành, môi trường, audience, metadata, JWKS URI và quy trình quản trị trust trước khi thay đổi cấu hình.

Đặc biệt, không xây dựng URL lấy khóa bằng cách nối trực tiếp `iss` chưa xác minh. Điều này có thể biến verifier thành thành phần gửi request đến host do attacker kiểm soát, tạo rủi ro SSRF hoặc trust arbitrary issuer.

### Phân nhóm issuer để quan sát

Metrics nên dùng alias nội bộ như `primary-idp`, `partner-idp-a`, `workforce-idp` thay cho URL tùy ý. Issuer không nhận diện được gom vào nhóm `unconfigured`; giá trị gốc chỉ được lưu trong log bảo mật sau khi giới hạn độ dài, escape và redaction phù hợp.

Điều này giúp tránh cardinality bùng nổ khi attacker gửi vô số giá trị `iss` khác nhau.

## 7. Theo dõi tỷ lệ lỗi xác minh đúng cách

Tỷ lệ lỗi cần được chia theo reason code và ngữ cảnh. Một biểu đồ tổng `JWT failures` không cho biết lỗi đến từ credential, key distribution hay dependency.

### Các tỷ lệ quan trọng

| Metric/rate | Tử số | Mẫu số | Điều cần phát hiện |
| --- | --- | --- | --- |
| Malformed rate | `TOKEN_MALFORMED` | Credential attempts | Client bug, token truncation hoặc input abuse |
| Signature failure rate | `SIGNATURE_INVALID` | Attempts cần xác minh chữ ký | Token bị sửa, sai key hoặc issuer misconfiguration |
| Unknown KID rate | `KEY_NOT_FOUND` | Credential attempts theo issuer | Rotation/cache drift hoặc probing |
| Untrusted issuer rate | `UNTRUSTED_ISSUER` | Credential attempts | Token từ nguồn không được phép hoặc issuer spoofing |
| Audience mismatch rate | `AUDIENCE_MISMATCH` | Credential attempts | Routing/token profile sai |
| Expired rate | `TOKEN_EXPIRED` | Credential attempts | Token cũ, client refresh lỗi hoặc clock skew |
| JWKS fetch failure rate | JWKS refresh failures | JWKS refresh attempts | Dependency/network failure |
| Verification unavailable rate | `UNAVAILABLE` | Credential attempts | Verifier không thể đưa ra quyết định |
| Internal failure rate | `INTERNAL_FAILURE` | Credential attempts | Lỗi cấu hình hoặc runtime |

Mẫu số cần nhất quán. Ví dụ, `signatureFailureRate` chỉ nên dùng các request đã đến bước xác minh chữ ký; không chia cho toàn bộ HTTP request nếu nhiều request không mang JWT.

### Phân tích theo chiều

Khi có spike, phân nhóm theo:

- Service/API nhận token.
- Issuer alias và token profile.
- Region, availability zone hoặc verifier pool.
- Client application đã được nhận diện.
- Key set version và thời điểm rotation.
- Phiên bản ứng dụng/verifier và thời điểm deploy.
- Kết quả JWKS refresh/cache.
- Loại request hoặc route, ở mức không làm lộ dữ liệu.

Tránh label có cardinality cao như raw `sub`, raw token, arbitrary `kid`, arbitrary issuer URL hoặc full URL có query string.

## 8. Thiết kế ngưỡng cảnh báo và baseline

Không có một ngưỡng phần trăm đúng cho mọi hệ thống. Một API nội bộ có client cố định có thể có tỷ lệ malformed gần bằng không; một public endpoint nhận nhiều token sai có thể có tỷ lệ reject cao theo hoạt động bình thường.

Nên kết hợp ba kiểu điều kiện:

1. **Absolute volume:** số lỗi tối thiểu trong cửa sổ quan sát.
2. **Relative rate:** tỷ lệ lỗi so với tổng credential attempts.
3. **Baseline deviation:** mức tăng so với hành vi lịch sử cùng service/issuer/region và khung thời gian tương tự.

Ví dụ điều kiện minh họa:

~~~text
alert when:
    unknownKidCount_5m >= minimumVolume
and unknownKidRate_5m > configuredRateThreshold
and rate remains elevated for 2 consecutive windows
~~~

Với JWKS dependency:

~~~text
alert when:
    jwksRefreshFailureRate_5m > dependencyFailureThreshold
or jwksCacheAge > maximumAllowedCacheAge
~~~

Các ngưỡng chỉ là ví dụ logic; phải hiệu chỉnh bằng dữ liệu thực tế. Ở lưu lượng thấp, có thể cần absolute count hoặc gom cửa sổ dài hơn. Ở lưu lượng cao, một tỷ lệ nhỏ vẫn có thể tương ứng với số lượng lớn request đáng ngờ.

### Phân cấp mức độ cảnh báo

| Mức | Ví dụ tín hiệu | Hành động |
| --- | --- | --- |
| **Info** | Một số ít token malformed, nằm trong baseline | Lưu metric/log, không cần đánh thức on-call |
| **Warning** | Unknown KID hoặc signature failure tăng tại một client/service | Kiểm tra rollout, client và key cache |
| **High** | Nhiều issuer lạ, unknown KID tăng diện rộng hoặc JWKS refresh storm | Điều tra security/availability ngay |
| **Critical** | Khóa bị compromise, revoked KID vẫn được chấp nhận hoặc nhiều vùng không áp dụng emergency revocation | Kích hoạt incident response và containment |

Không phát cảnh báo critical chỉ dựa vào một `kid` lạ đơn lẻ. Cần kết hợp tín hiệu, mức độ ảnh hưởng và bằng chứng key status.

## 9. Kết hợp các tín hiệu để phân biệt nguyên nhân

Một tín hiệu đơn lẻ hiếm khi đủ để kết luận. Dùng tương quan giữa verifier outcome, key distribution, deployment và dependency.

| Mẫu tín hiệu | Nguyên nhân có thể | Hướng xác minh |
| --- | --- | --- |
| `KEY_NOT_FOUND` tăng ngay sau key rotation, JWKS fetch thành công | Issuer cutover sớm hoặc cache chưa cập nhật | So sánh key set version, `kid` publish time và issuer signing time |
| `KEY_NOT_FOUND` tăng cùng JWKS timeout | Endpoint JWKS, DNS, TLS hoặc network lỗi | Kiểm tra dependency health, cache age và region |
| Nhiều unknown `kid` duy nhất, refresh bị rate limit | Probing hoặc input abuse | Kiểm tra nguồn request, volume và phân bố fingerprint |
| `SIGNATURE_INVALID` tăng nhưng KID vẫn được tìm thấy | Issuer dùng sai private key, token bị sửa hoặc verifier lấy sai key | Kiểm tra signing deployment, key version và test token |
| `ISSUER_MISMATCH` tăng trên một service | Token được gửi nhầm môi trường hoặc issuer config drift | Kiểm tra route, client config và trust profile |
| `UNTRUSTED_ISSUER` tăng nhưng các issuer đã cấu hình vẫn khỏe | Token ngoài hệ thống hoặc probing | Kiểm tra client/source pattern, không tự thêm issuer |
| `AUDIENCE_MISMATCH` tăng sau thay đổi gateway route | Token dành cho resource khác hoặc route mapping sai | Kiểm tra audience contract và service routing |
| `TOKEN_EXPIRED` tăng ở một region | Clock drift hoặc client dùng cache token cũ | Kiểm tra time sync, refresh behavior và clock skew |
| `REVOCATION_UNAVAILABLE` tăng nhưng signature success bình thường | Revocation store/introspection lỗi | Kiểm tra dependency; không bỏ qua revocation |
| `INTERNAL_FAILURE` tăng sau deploy verifier | Regression hoặc cấu hình không tương thích | Rollback/disable change theo runbook |

Các khả năng trong bảng là giả thuyết điều tra, không phải kết luận tự động.

## 10. Dashboard vận hành nên hiển thị gì?

Một dashboard hữu ích nên giúp người trực ca trả lời nhanh:

- Bao nhiêu credential được gửi tới verifier?
- Tỷ lệ Valid, Rejected, Unavailable và InternalFailure đang thay đổi thế nào?
- Reason code nào tăng mạnh nhất?
- Issuer alias hoặc service nào bị ảnh hưởng?
- Có một `kid` mới do rotation hay hàng loạt `kid` không nhận diện?
- JWKS cache của từng region đang ở tuổi bao nhiêu?
- JWKS refresh thành công hay thất bại?
- Spike bắt đầu cùng thời điểm deploy, key rotation hay incident khác không?
- Có region nào đưa ra quyết định khác biệt so với các region còn lại?

Các panel gợi ý:

1. Credential attempts và verification outcomes theo thời gian.
2. Reject rate theo reason code.
3. Unknown KID count/rate và số lượng KID duy nhất theo cửa sổ.
4. JWKS refresh count, failure rate và cache age theo issuer/region.
5. Issuer allowlist mismatch và audience mismatch theo service.
6. Verification latency p50/p95/p99.
7. Dependency availability của JWKS, introspection và revocation store.
8. Key rotation timeline, configuration version và deployment markers.

Không hiển thị raw JWT hoặc toàn bộ claims trong dashboard. Dashboard phải tuân theo cùng chính sách phân quyền và retention như log bảo mật.

## 11. An toàn dữ liệu trong metrics, logs và traces

Telemetry có thể trở thành một kho credential nếu cấu hình ghi toàn bộ header hoặc payload.

Không ghi:

- Raw JWT/JWE hoặc Authorization header.
- Refresh token, client assertion hoặc DPoP proof.
- Private key, shared secret hoặc plaintext sau giải mã.
- Toàn bộ claims, email hoặc subject nếu không có nhu cầu được phê duyệt.
- URL có token trong query string.
- Giá trị `iss` hoặc `kid` chưa giới hạn trực tiếp thành metric label.

Thông tin có thể ghi theo policy:

- Request/correlation ID.
- Outcome và reason code chuẩn hóa.
- Issuer alias đã cấu hình.
- KID đã biết hoặc key version; unknown KID có thể được fingerprint có giới hạn.
- Service, region, token profile và thời gian xử lý.
- JWKS cache age và kết quả refresh.

Dữ liệu từ JOSE header/payload trước khi xác minh phải được coi là untrusted input. Nếu ghi một phần để điều tra, giới hạn độ dài, escape ký tự điều khiển, tránh log injection và đánh dấu rõ dữ liệu chưa xác minh.

Metrics labels cần có cardinality hữu hạn. Dùng bucket `unknown` hoặc nhóm theo reason code thay vì tạo một time series cho mỗi `kid`/issuer attacker gửi.

## 12. Runbook khi cảnh báo bất thường

Một runbook nên hướng dẫn điều tra theo thứ tự, tránh xoay khóa hoặc thay trust configuration vội vàng khi chưa xác định nguyên nhân.

### Bước 1 — Xác định phạm vi

- Alert ảnh hưởng một service, một issuer hay toàn hệ thống?
- Một region hay nhiều region?
- Chỉ một client hay nhiều client?
- Spike bắt đầu lúc nào và kéo dài bao lâu?
- Outcome nào tăng: Rejected, Unavailable hay InternalFailure?

### Bước 2 — Phân loại reason code

- `KEY_NOT_FOUND`: kiểm tra key rotation, JWKS cache và unknown KID.
- `SIGNATURE_INVALID`: kiểm tra signing key, issuer deployment và token corruption.
- `UNTRUSTED_ISSUER`/`ISSUER_MISMATCH`: kiểm tra client/environment và trust configuration.
- `JWKS_UNAVAILABLE`: kiểm tra endpoint, DNS, TLS, network và cache age.
- `TOKEN_EXPIRED`: kiểm tra clock, token lifetime và client refresh.
- `INTERNAL_FAILURE`: kiểm tra deploy, crypto provider và verifier configuration.

### Bước 3 — Tương quan với thay đổi

- Có rotation hoặc key revocation gần đây không?
- Có thay đổi issuer metadata, JWKS URI hoặc trust allowlist không?
- Có deploy gateway, verifier hoặc client không?
- Có sự cố DNS, TLS, network, broker hoặc secret store không?
- Có policy rollout hoặc thay đổi audience không?

### Bước 4 — Khoanh vùng và containment

Nếu có bằng chứng probing hoặc abuse, dùng rate limit/WAF policy và giới hạn JWKS refresh theo runbook. Nếu nghi khóa compromise, dùng quy trình emergency key revocation và xác nhận mọi verifier đã áp dụng trạng thái revoked. Không thêm issuer mới hoặc chấp nhận KID lạ chỉ để làm giảm alert.

### Bước 5 — Xác nhận phục hồi

- Tỷ lệ lỗi trở về baseline.
- JWKS cache và key set version nhất quán theo policy.
- Không còn refresh storm.
- Mọi region đã nhận và áp dụng trạng thái khóa/policy mới.
- Không còn verifier InternalFailure hoặc dependency outage.
- Lưu incident timeline và nguyên nhân gốc mà không lưu credential.

## 13. Cảnh báo đa vùng và khác biệt giữa verifier

Trong multi-region, một issuer có thể được phục vụ bởi nhiều gateway và verifier với cache JWKS riêng. Cần so sánh kết quả giữa vùng:

- `KEY_NOT_FOUND` chỉ tăng tại một vùng có thể là cache propagation.
- `SIGNATURE_INVALID` tăng đồng loạt có thể là issuer signing sai hoặc key material sai.
- `JWKS_UNAVAILABLE` chỉ tại một vùng có thể là DNS, route hoặc TLS issue cục bộ.
- `TOKEN_EXPIRED` chỉ tại một vùng có thể liên quan clock drift.
- Revoked KID vẫn được chấp nhận ở một vùng là tín hiệu nghiêm trọng về invalidation.

Dashboard cần hiển thị `last_successful_refresh`, cache age, key set version và thời điểm áp dụng revocation theo region. Khi có emergency revocation, theo dõi **applied state**, không chỉ thời điểm control plane publish sự kiện.

Không nên cho region tiếp tục chấp nhận token dùng khóa đã bị xác nhận compromise chỉ để duy trì availability. Failure policy phải theo risk tier và runbook incident.

## 14. Kiểm thử hệ thống cảnh báo

Alert cần được kiểm tra như một phần của hệ thống bảo mật, không chỉ xác nhận dashboard có biểu đồ.

| Kịch bản kiểm thử | Tín hiệu mong đợi |
| --- | --- |
| Rotation bình thường với pre-published key | KID mới xuất hiện nhưng không tạo spike reject kéo dài |
| Issuer dùng key mới trước khi JWKS lan truyền | `KEY_NOT_FOUND` tăng và alert chỉ ra rollout/cache issue |
| Gửi nhiều token với KID ngẫu nhiên | Unknown KID tăng; JWKS refresh vẫn bị giới hạn |
| JWKS endpoint timeout | `JWKS_UNAVAILABLE` và dependency alert tăng, không bị tính nhầm thành signature invalid |
| Token có issuer ngoài allowlist | `UNTRUSTED_ISSUER` tăng; không phát sinh outbound fetch tới issuer tùy ý |
| Token sai chữ ký nhưng KID tồn tại | `SIGNATURE_INVALID` tăng |
| Audience sai sau route change | `AUDIENCE_MISMATCH` tăng ở service liên quan |
| Clock lệch ở một region | Expiry/not-before anomaly được phát hiện tại region đó |
| Key compromise và emergency revoke | Revoked KID bị từ chối ở mọi verifier; alert còn mở đến khi applied |
| Attacker tạo nhiều issuer/KID duy nhất | Cardinality không tăng vô hạn; label vẫn ở nhóm hữu hạn |
| Traffic tăng theo giờ cao điểm nhưng error ratio ổn định | Không phát cảnh báo giả chỉ vì absolute count tăng |
| Dependency outage làm verifier unavailable | Alert availability riêng; không gộp vào invalid-token rate |

Nên kiểm thử cả cảnh báo mở, cập nhật và tự đóng; kiểm tra người trực nhận được thông tin đủ để hành động; kiểm tra suppression không che mất cảnh báo critical.

## 15. Các lỗi thường gặp khi xây dựng alert

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cảnh báo chỉ dựa vào tổng HTTP 401 | Không phân biệt token sai với lỗi dependency hoặc authorization | Dùng outcome/reason code riêng |
| Gộp JWKS timeout vào signature failure | Che khuất outage và dẫn tới xử lý sai | Phân biệt `UNAVAILABLE` với `REJECTED` |
| Dùng raw `kid` hoặc `iss` làm metric label | Cardinality tăng vô hạn và có thể gây DoS telemetry | Dùng alias/nhóm unknown và giới hạn dimension |
| Tự động fetch JWKS từ issuer trong token | Có thể SSRF hoặc tin issuer tùy ý | Chỉ dùng trust configuration allowlist |
| Alert mọi unknown KID như critical | False positive trong rotation và test | Kết hợp volume, rate, baseline và change window |
| Chỉ theo dõi tỷ lệ, bỏ qua số lượng | Traffic thấp tạo spike giả hoặc traffic lớn bị đánh giá thấp | Kết hợp count, ratio và baseline |
| Chỉ theo dõi số lượng tuyệt đối | Giờ cao điểm tạo alert noise | Chuẩn hóa theo credential attempts |
| Không phân biệt issuer alias với issuer lạ | Khó phát hiện trust drift và issuer spoofing | Nhóm issuer đã cấu hình và `unconfigured` riêng |
| Không theo dõi từng region | Một vùng stale có thể bị che bởi trung bình toàn hệ thống | Dashboard và alert theo region |
| Log raw token để điều tra | Credential bị lộ qua telemetry | Log metadata tối thiểu và redaction trước khi ghi |
| Tắt alert trong lúc rotation | Có thể bỏ lỡ key compromise hoặc rollout lỗi | Dùng maintenance window có phạm vi và vẫn giữ critical signals |
| Không có runbook | On-call không biết kiểm tra cache, key hay dependency | Gắn bước điều tra và owner vào alert |

## 16. Checklist thiết kế cảnh báo

**Telemetry**

- Có outcome và reason code chuẩn hóa ở mọi verifier.
- Đếm riêng credential attempts, missing credential, rejected, unavailable và internal failure.
- Theo dõi `KEY_NOT_FOUND`, `SIGNATURE_INVALID`, `UNTRUSTED_ISSUER`, `ISSUER_MISMATCH`, `AUDIENCE_MISMATCH` và `TOKEN_EXPIRED`.
- Theo dõi JWKS refresh, cache age, timeout và key set version.
- Theo dõi metrics theo service, issuer alias, token profile và region.

**An toàn và cardinality**

- Không dùng raw JWT, subject, arbitrary issuer hoặc arbitrary KID làm metric label.
- Nhóm unknown issuer/KID vào dimension hữu hạn.
- Rate limit và coalesce JWKS refresh khi KID chưa biết.
- Không tự động lấy khóa từ URL do token cung cấp.
- Redact token/claims trước khi ghi log, trace hoặc error report.
- Escape và giới hạn dữ liệu untrusted trong log.

**Alert và vận hành**

- Kết hợp absolute volume, error ratio và baseline deviation.
- Đặt ngưỡng riêng theo service/issuer/region và risk tier.
- Phân biệt credential rejection với dependency outage và internal failure.
- Tương quan alert với key rotation, deployment và policy changes.
- Có runbook cho unknown KID spike, issuer anomaly, signature failure và JWKS outage.
- Xác nhận applied state trên mọi region sau emergency revocation.
- Kiểm thử alert với rotation bình thường, abuse, outage, clock drift và cardinality attack.

**Ghi nhớ:** `kid` và `iss` là dữ liệu đầu vào cần được xử lý theo trust configuration; chúng không phải bằng chứng tin cậy. Theo dõi chúng cùng reason code, JWKS refresh, cache age và tỷ lệ lỗi giúp phân biệt rotation chưa đồng bộ, cấu hình sai, dependency outage và hoạt động dò token. Hãy dùng alias và dimension có cardinality hữu hạn, không log raw JWT, kết hợp count/rate/baseline và duy trì runbook để cảnh báo dẫn đến hành động chính xác.

### Tài liệu chuẩn để tra cứu

- **RFC 7517 — JSON Web Key (JWK):** thuộc tính JWK, JWKS và ý nghĩa của `kid`.
- **RFC 7519 — JSON Web Token (JWT):** claim `iss` và các registered claims.
- **RFC 8725 — JSON Web Token Best Current Practices:** kiểm tra issuer, audience, thuật toán và nguồn khóa tin cậy.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** validation profile cho JWT access token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ token và giảm rủi ro trong OAuth.
