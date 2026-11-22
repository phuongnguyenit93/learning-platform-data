# Bộ nhớ đệm kết quả xác minh và ràng buộc thời hạn, thu hồi

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Hiệu năng và vận hành. Bài viết trình bày cách thiết kế cache cho hệ thống xác minh JWT nói chung, độc lập với ngôn ngữ lập trình, nền tảng và framework.

## 1. Mục tiêu và bài toán cần giải quyết

Xác minh JWT có thể tiêu tốn CPU cho parse, kiểm tra chữ ký, giải mã hoặc tra cứu khóa. Khi lưu lượng lớn, một token được gửi lặp lại có thể khiến hệ thống thực hiện cùng một số phép tính nhiều lần. Bộ nhớ đệm (cache) có thể giảm chi phí đó bằng cách lưu kết quả đã xác minh và tái sử dụng trong một khoảng thời gian có giới hạn.

Tuy nhiên, token có thời hạn, khóa có thể được xoay hoặc thu hồi, quyền có thể thay đổi và một token có thể bị thu hồi trước khi hết hạn. Nếu cache giữ kết quả chấp nhận quá lâu, hệ thống tiếp tục chấp nhận credential đã hết hạn, đã bị thu hồi hoặc được ký bằng khóa không còn đáng tin.

Thiết kế cần đạt đồng thời các mục tiêu:

- giảm số lần thực hiện phép xác minh mật mã tốn kém;
- giữ nguyên quy tắc issuer, audience, token profile và thuật toán;
- không chấp nhận token sau thời điểm hiệu lực kết thúc;
- giới hạn độ trễ áp dụng thu hồi theo một SLA có thể đo được;
- phản ứng đúng khi khóa, policy hoặc cấu hình issuer thay đổi;
- tránh cache poisoning, cross-tenant leakage và cache stampede;
- duy trì hành vi an toàn khi cache hoặc kho trạng thái không sẵn sàng.

Cache chỉ là một tối ưu hóa của quá trình xác minh. Nó không được trở thành nguồn tin cậy độc lập và không được làm thay đổi semantics của token profile.

## 2. Phân biệt các lớp cache

Không phải mọi dữ liệu liên quan JWT đều nên dùng chung một cache. Mỗi lớp có dữ liệu, khóa định danh, thời hạn và quy tắc vô hiệu hóa khác nhau.

| Lớp cache | Dữ liệu được lưu | Mục đích | Rủi ro chính |
| --- | --- | --- | --- |
| JWKS/key cache | JWK, certificate hoặc public key đã lấy từ nguồn tin cậy | Tránh tải key set liên tục | Dùng khóa đã bị loại bỏ hoặc cache nhầm issuer |
| Signature verification cache | Kết quả chữ ký hợp lệ cùng thông tin khóa/thuật toán | Tránh tính lại chữ ký cho cùng token | Bỏ qua key revocation hoặc policy mới |
| Full token validation cache | Kết quả xác minh profile và claims | Tránh lặp cả chuỗi validation | Chấp nhận token quá hạn hoặc đã bị thu hồi |
| Revocation-state cache | Trạng thái revoked/not-revoked theo token hoặc grant | Giảm truy vấn kho thu hồi | Trạng thái not-revoked bị cũ |
| Authorization decision cache | Quyết định allow/deny cho subject, action và resource | Giảm chi phí policy evaluation | Quyền hoặc trạng thái resource thay đổi |
| Negative cache | Kết quả từ chối có thể tái sử dụng | Giảm xử lý lặp token sai hoặc unknown key | Bị lợi dụng để chiếm bộ nhớ hoặc gây từ chối nhầm |

**JWKS cache không phải verification-result cache.** JWKS cache lưu public key; verification cache lưu kết quả một token cụ thể đã được xác minh bằng một khóa cụ thể. Một khóa có thể xác minh nhiều token, còn một token chỉ có một signing input và một chữ ký cụ thể.

**Verification cache không phải authorization cache.** Token có thể hợp lệ về mật mã nhưng user đã bị khóa, quyền trên resource đã thay đổi hoặc policy hiện tại không còn cho phép hành động. Nên tách kết quả xác minh credential khỏi quyết định authorization.

## 3. Những bất biến bảo mật cache phải giữ

Trước khi chọn công nghệ hoặc TTL, định nghĩa các bất biến:

1. Cache hit chỉ được trả về cho đúng token, đúng issuer, đúng token profile và đúng ngữ cảnh xác minh.
2. Một kết quả xác minh chỉ có giá trị với thuật toán, khóa và policy đã tạo ra kết quả đó.
3. Không cache thành công nếu chữ ký, claims, audience hoặc profile chưa được kiểm tra đầy đủ theo tầng cache đang triển khai.
4. Thời hạn cache không được kéo dài thời điểm token còn được chấp nhận.
5. Trạng thái thu hồi phải được cập nhật trong giới hạn độ trễ đã cam kết.
6. Khi key trust hoặc validation policy thay đổi, kết quả cache cũ phải bị vô hiệu hóa hoặc trở nên không thể tra cứu.
7. Không dùng dữ liệu do token cung cấp làm namespace hoặc cache key có thể gây injection.
8. Cache không sẵn sàng không được biến thành lý do chấp nhận token chưa xác minh.
9. Không ghi raw token hoặc secret vào log, metric, trace hay tên cache key.
10. Cache phải có giới hạn dung lượng, TTL và cơ chế chống request làm cạn tài nguyên.

Một cache hit phải có cùng kết quả bảo mật với việc chạy lại validator tại thời điểm hiện tại, trong phạm vi SLA về trạng thái động đã được định nghĩa.

## 4. Xác định chính xác thứ được cache

### 4.1. Cache kết quả chữ ký

Lớp này chỉ ghi nhận rằng signing input và chữ ký của token đã được xác minh bằng một public key/secret cụ thể theo thuật toán cụ thể.

Khi cache hit, hệ thống vẫn phải thực hiện các kiểm tra còn lại như:

- issuer và audience theo endpoint;
- token type/profile;
- `exp`, `nbf`, `iat` và giới hạn tuổi token;
- các claim bắt buộc và kiểu dữ liệu;
- trạng thái thu hồi;
- sender constraint hoặc request binding nếu profile yêu cầu;
- authorization theo policy hiện tại.

Lợi ích là giảm phép tính chữ ký, nhưng validator vẫn giữ trách nhiệm kiểm tra claims và trạng thái hiện thời.

### 4.2. Cache kết quả xác minh đầy đủ

Lớp này có thể lưu một kết quả đã xác minh gồm claims đã chuẩn hóa, issuer, audience, profile, thuật toán, key thumbprint, thời điểm xác minh và deadline cache.

Cần bảo đảm các kiểm tra phụ thuộc thời gian hoặc trạng thái động được chạy lại khi cache hit, hoặc entry bị hết hạn/invalidate trước khi các điều kiện đó thay đổi.

Ví dụ, nếu entry lưu kết quả `not_revoked`, TTL của entry phải nằm trong giới hạn độ mới của dữ liệu thu hồi. Nếu policy có thể thay đổi ngay lập tức, cache key cần chứa policy version hoặc hệ thống phải phát sự kiện invalidation.

Với proof hoặc assertion có semantics dùng một lần, không cache trạng thái “đã chấp nhận” theo cách bỏ qua thao tác tiêu thụ. Ví dụ, DPoP proof có thể cần kiểm tra `jti` chống replay, nonce server và binding `htm`/`htu`/`ath` trên từng request. Có thể tái sử dụng kết quả tính chữ ký mật mã, nhưng mỗi lần dùng vẫn phải kiểm tra ngữ cảnh request và tiêu thụ trạng thái one-time. Cùng một proof được gửi lần thứ hai phải bị từ chối theo replay policy, kể cả khi chữ ký của nó đang có cache hit.

### 4.3. Cache quyết định authorization

Quyết định allow/deny thường phụ thuộc nhiều hơn token: subject, client, tenant, resource, action, trạng thái tài khoản, quan hệ sở hữu và policy version.

Nếu cache authorization, key cần phản ánh đủ ngữ cảnh, ví dụ:

- subject reference;
- client/actor;
- tenant;
- resource ID hoặc resource version;
- action;
- policy version;
- các thuộc tính môi trường ảnh hưởng quyết định.

Không dùng một cache entry “user đã xác thực” để suy ra mọi hành động của user đều được phép. Xác thực token và cấp quyền là hai quyết định riêng.

## 5. Thiết kế cache key không làm lộ token

Không dùng raw JWT làm cache key hiển thị trong hệ thống cache phân tán. Cache key có thể xuất hiện trong dashboard, trace, dump, thống kê hoặc công cụ quản trị.

Một cách tạo fingerprint là HMAC trên đúng bytes của token:

~~~text
tokenFingerprint = HMAC-SHA-256(
    cacheFingerprintKey,
    exactSerializedToken
)
~~~

Sau đó tạo cache key có namespace:

~~~text
cacheKey = (
    cacheSchemaVersion,
    issuerId,
    tokenProfileId,
    expectedAudience,
    verifierPolicyVersion,
    issuerConfigVersion,
    tokenFingerprint
)
~~~

Các thành phần này có vai trò:

- `issuerId`: ngăn dùng kết quả của issuer A cho issuer B;
- `tokenProfileId`: tách access token, ID Token, assertion và proof;
- `expectedAudience`: ngăn dùng kết quả đã xác minh cho resource khác;
- `verifierPolicyVersion`: vô hiệu hóa entry khi allowlist hoặc quy tắc validation đổi;
- `issuerConfigVersion`: gắn entry với phiên bản trust configuration/JWKS policy;
- `tokenFingerprint`: định danh chính xác serialized token.

HMAC fingerprint key phải được quản lý như secret riêng, không tái sử dụng signing key hoặc encryption key. Khi xoay fingerprint key, cache namespace thay đổi hoặc cache được xóa có kiểm soát.

Không chỉ hash payload hoặc `jti` để đại diện token. Hai JWT có cùng claims nhưng chữ ký, header, issuer hoặc key khác nhau không nhất thiết có cùng semantics. Fingerprint của toàn bộ serialized token giúp phân biệt các bytes thực sự được xác minh.

Không dùng `kid` một mình làm cache key. `kid` không đảm bảo duy nhất giữa issuer, có thể được tái sử dụng sau rotation và không định danh đầy đủ key material. Khi cần gắn cache với khóa, lưu thêm thumbprint hoặc key version đã xác minh.

## 6. Ràng buộc TTL với thời hạn JWT

### 6.1. Thời điểm chấp nhận cuối cùng

Claim `exp` là thời điểm sau đó JWT không còn được chấp nhận. Nếu validator áp dụng clock-skew leeway, phải xác định rõ thời điểm kết thúc hiệu lực theo policy.

Gọi:

- `now`: thời điểm xác minh hiện tại;
- `exp`: thời điểm hết hạn từ token;
- `L`: clock-skew leeway được policy cho phép;
- `Tmax`: TTL cache tối đa.

Nếu policy cho phép leeway sau `exp`, deadline chấp nhận tối đa là:

\[
D_{exp} = exp + L
\]

Thời hạn cache cơ bản:

\[
TTL_{exp} = \max(0,\ \min(T_{max}, D_{exp} - now))
\]

Cách tính này bảo đảm cache entry không sống lâu hơn cửa sổ mà validator có thể chấp nhận token theo chính sách thời gian đã chọn.

Nếu hệ thống không áp dụng leeway, đặt `L = 0`. Không tự tăng leeway để bù cho đồng hồ không đồng bộ.

### 6.2. Không cache token đã gần hết hạn quá lâu

Ví dụ:

- thời gian hiện tại: 12:00:00;
- `exp`: 12:00:20;
- leeway: 0;
- TTL cache tối đa: 60 giây.

TTL thực tế không thể là 60 giây; nó chỉ còn 20 giây. Token phải bị từ chối từ thời điểm hết hạn, kể cả khi cache entry chưa được dọn vật lý.

Một cách triển khai an toàn là đặt TTL của entry không vượt quá deadline chấp nhận. Một cách khác là cache lâu hơn nhưng **bắt buộc kiểm tra lại `exp` trên mọi cache hit**; cách thứ hai phức tạp hơn và không được bỏ qua bước kiểm tra thời gian.

### 6.3. Ràng buộc với tuổi tối đa theo iat

Một số profile đặt giới hạn tuổi token/proof dựa trên `iat`, ngoài `exp`. Nếu token chỉ được chấp nhận trong tối đa `A` giây kể từ lúc phát hành, deadline tuổi tối đa là:

\[
D_{age} = iat + A + L
\]

Khi đó:

\[
D_{token} = \min(exp + L,\ iat + A + L)
\]

Nếu profile yêu cầu `iat` và giới hạn tuổi, cache không được làm token tồn tại lâu hơn deadline này. Mỗi profile có thể có `A` khác nhau; không dùng một giới hạn chung cho mọi loại JWT.

### 6.4. TTL bằng không hoặc âm

Nếu `exp` đã qua hoặc deadline tuổi tối đa đã qua, không tạo positive cache entry. Trả kết quả hết hạn theo validator.

Không làm tròn TTL lên một giây nếu điều đó khiến entry sống vượt deadline. Khi chuyển giây sang millisecond hoặc đơn vị TTL của cache, làm tròn theo hướng không kéo dài thời gian chấp nhận.

## 7. Ràng buộc với nbf, iat và clock skew

`nbf` xác định thời điểm trước đó token chưa được chấp nhận. `iat` là thời điểm phát hành và có thể được dùng để giới hạn tuổi hoặc phát hiện token phát hành trong tương lai.

Khi cache kết quả:

- không tạo positive entry trước khi token thực sự đạt điều kiện `nbf`;
- trên cache hit, kiểm tra lại thời gian hiện tại nếu entry có thể được dùng qua ranh giới `nbf`, `exp` hoặc max-age;
- áp dụng cùng một leeway policy ở mọi node;
- không chấp nhận `iat` nằm trong tương lai vượt ngưỡng;
- không để một node có đồng hồ chậm chấp nhận token lâu hơn node khác ngoài policy.

JWT NumericDate thường dựa trên thời gian UTC. Hệ thống cần đồng bộ thời gian giữa issuer, verifier và các node cache. Cache TTL nên dùng bộ đếm thời gian monotonic cho thời lượng trong tiến trình, còn kiểm tra claim vẫn dựa trên clock UTC đã đồng bộ.

Nếu thời gian hệ thống nhảy lùi hoặc nguồn clock lỗi, không dùng cache để che lỗi. Phát cảnh báo, áp dụng policy thời gian an toàn và tránh kéo dài deadline chấp nhận.

## 8. Ràng buộc TTL với trạng thái thu hồi

JWT không tự có một cơ chế thu hồi tức thời. Một JWT đã ký có thể tiếp tục vượt qua kiểm tra chữ ký đến khi hết hạn, trừ khi hệ thống có thêm trạng thái hoặc cơ chế chặn.

Các mô hình thường gặp:

| Mô hình | Cách hoạt động | Đặc điểm |
| --- | --- | --- |
| Short-lived token | Access token sống ngắn | Giới hạn cửa sổ tồn tại sau khi bị lộ/thu hồi |
| Denylist theo `jti` | Ghi nhận token cụ thể đã bị thu hồi | Cần tra cứu và namespace theo issuer |
| Denylist theo fingerprint | Ghi nhận fingerprint token bị thu hồi | Hữu ích khi token không có `jti` đáng tin cậy |
| Grant/session version | So sánh version trong token với trạng thái hiện tại | Có thể thu hồi nhiều token cùng grant/session |
| Introspection | Hỏi authorization server về trạng thái token | Có trạng thái tập trung nhưng phát sinh network dependency |
| Signing key revocation | Ngừng tin một key hoặc key version | Ảnh hưởng tất cả token được ký bằng key đó |
| Account/client disable | Kiểm tra trạng thái chủ thể hoặc client | Có thể yêu cầu truy vấn trạng thái động |

Nếu hệ thống không kiểm tra denylist, introspection, grant version hoặc trạng thái khóa, không được tuyên bố rằng JWT có thể bị thu hồi tức thời. Trong trường hợp đó, giới hạn thực tế thường là thời hạn token và các biện pháp chặn ở tầng khác.

## 9. Phân biệt cache trạng thái revoked và not-revoked

Hai kết quả có rủi ro khác nhau:

**Đã thu hồi (revoked):** cache kết quả từ chối thường an toàn để giữ tới khi token hết hạn hoặc trạng thái được cập nhật lại. Nếu giữ lâu hơn cần thiết, tác động chủ yếu là từ chối một token đã được cấp lại hợp lệ do nhầm lẫn; do đó phải namespace và version chính xác.

**Chưa thu hồi (not revoked):** đây là kết quả âm tính của truy vấn thu hồi. Nếu cache kết quả này quá lâu, token đã bị thu hồi có thể tiếp tục được chấp nhận.

Ví dụ, revocation store ghi token bị thu hồi lúc 12:00:00. Resource server vẫn giữ cache `not_revoked` đến 12:05:00. Nếu không có invalidation, hệ thống có thể chấp nhận token thêm gần 5 phút.

Vì vậy, với kết quả `not_revoked`, đặt:

\[
D_{revocation} = checkedAt + T_{revocationCacheMax}
\]

`T_revocationCacheMax` phải nhỏ hơn hoặc bằng độ trễ thu hồi tối đa mà hệ thống cam kết, sau khi tính cả propagation và invalidation delay.

Không cache lỗi truy vấn revocation store thành `not_revoked`. Timeout, connection failure hoặc response không hợp lệ là trạng thái **unknown**, không phải bằng chứng token chưa bị thu hồi.

## 10. Xác định thời hạn cache cuối cùng

Một positive cache entry chỉ nên tồn tại đến thời điểm sớm nhất trong các deadline có liên quan.

Ví dụ:

- `D_exp`: thời điểm hết cửa sổ chấp nhận của token;
- `D_age`: thời điểm vượt max token age nếu profile có quy định;
- `D_rev`: thời điểm kết quả not-revoked cần được làm mới;
- `D_key`: thời điểm key/trust material phải được xem xét lại theo policy;
- `D_policy`: thời điểm policy/configuration hiện tại hết hiệu lực;
- `D_max`: giới hạn TTL vận hành.

Deadline cuối:

\[
D_{cache} = \min(D_{exp}, D_{age}, D_{rev}, D_{key}, D_{policy}, D_{max})
\]

TTL còn lại:

\[
TTL = \max(0,\ D_{cache} - now)
\]

Chỉ đưa vào phép tính các deadline thực sự áp dụng. Nếu profile không có max-age, bỏ `D_age`. Nếu không có trạng thái thu hồi trực tuyến, đừng tự tạo `D_rev`; thay vào đó tài liệu hóa rằng khả năng thu hồi bị giới hạn bởi TTL token hoặc key policy.

Nếu cache hit vẫn kiểm tra lại một điều kiện, có thể không cần giới hạn entry bởi deadline của chính điều kiện đó; tuy nhiên không được bỏ qua các deadline trạng thái mà entry đang đại diện.

## 11. Thu hồi theo jti, fingerprint và grant

### 11.1. Denylist theo jti

Nếu token profile cung cấp `jti` và issuer bảo đảm tính duy nhất trong phạm vi thích hợp, có thể tạo revocation key:

~~~text
revocationKey = namespace(
    issuerId,
    tokenProfileId,
    jti
)
~~~

Không dùng `jti` đơn lẻ trên toàn hệ thống. Hai issuer có thể sinh cùng giá trị; cùng một issuer có thể có nhiều profile hoặc namespace khác nhau.

Denylist entry thường cần tồn tại tới hết cửa sổ token có thể được chấp nhận. Không xóa entry ngay tại `exp` nếu verifier còn áp dụng leeway. Nếu token bị thu hồi trước `exp`, entry phải được giữ đủ lâu để mọi verifier từ chối token đó.

### 11.2. Denylist theo token fingerprint

Nếu token không có `jti`, hoặc `jti` không đủ tin cậy, có thể dùng HMAC fingerprint của serialized token. Cách này định danh đúng token bytes mà không lưu raw credential trong kho thu hồi.

Cần quản lý HMAC key version. Khi xoay key, hệ thống phải có chiến lược tra cứu tương thích cho entry cũ trong thời gian còn hiệu lực hoặc chủ động migrate/invalidate theo kế hoạch.

### 11.3. Grant hoặc session version

Một token có thể mang claim như session/grant version. Resource server so sánh version đó với trạng thái hiện tại của grant/session.

Khi revoke grant hoặc logout toàn bộ session, tăng version hoặc đánh dấu grant revoked. Các token mang version cũ bị từ chối.

Cache kết quả version phải có TTL phù hợp với revocation SLA. Nếu cache version cũ 10 phút, việc tăng version ở authorization server chưa chắc có hiệu lực ngay tại resource server.

## 12. Cache invalidation khi thu hồi

Có ba cách thường được kết hợp:

**TTL ngắn:** bảo đảm trạng thái cũ tự hết hạn trong giới hạn đã chọn. Cách này đơn giản nhưng tạo độ trễ thu hồi tối đa gần bằng TTL.

**Push invalidation:** revocation service phát sự kiện khi token/grant/session bị thu hồi. Các node xóa entry liên quan. Cần xử lý mất kết nối, sự kiện trùng, sai thứ tự và node vừa khởi động.

**Versioned namespace:** cache key chứa revocation epoch, grant version hoặc policy version. Khi version tăng, entry cũ không còn được tra cứu dù chưa bị xóa vật lý.

Mô hình vận hành tốt thường dùng push invalidation để giảm độ trễ và TTL làm giới hạn an toàn khi event bị mất. Versioned namespace giúp tránh phải quét toàn bộ cache.

Sự kiện invalidation nên có:

- issuer và profile namespace;
- token `jti` hoặc grant/session reference đã giả danh hóa;
- version/sequence number;
- thời điểm phát sinh;
- reason code;
- phạm vi ảnh hưởng.

Không đưa raw JWT vào sự kiện. Consumer phải xử lý idempotent và bỏ qua event cũ hơn version hiện tại.

## 13. Key rotation và thu hồi signing key

Cache kết quả xác minh có thể giữ một token là hợp lệ ngay cả sau khi khóa ký bị loại khỏi JWKS. Đây là lý do phải ràng buộc entry với key identity và trust configuration.

Một entry nên lưu:

- issuer ID;
- `kid` đã chọn;
- key thumbprint hoặc key version;
- thuật toán;
- JWKS/configuration version;
- thời điểm key được xác minh;
- deadline hoặc policy cho key trust.

`kid` chỉ là nhãn chọn khóa, không đủ để nhận diện key material. Nếu cùng `kid` được tái sử dụng với khóa khác, cache cũ có thể gây nhầm lẫn. Hãy dùng thumbprint hoặc version của public key đã xác minh.

Khi rotation bình thường:

1. Issuer công bố key mới trong JWKS.
2. Verifier tải key set và cập nhật version.
3. Token mới được ký bằng key mới.
4. Trong giai đoạn overlap, token dùng key cũ vẫn được chấp nhận theo policy.
5. Khi key cũ bị loại và hết thời gian chuyển tiếp, invalidation hoặc version change làm cache entry cũ không còn hợp lệ.

Khi key compromise:

- đánh dấu key thumbprint/version bị thu hồi;
- phát invalidation tới mọi node/region;
- không chờ TTL JWKS thông thường nếu sự cố cần xử lý khẩn cấp;
- từ chối token ký bằng key bị compromise;
- kiểm tra các cache và downstream decision cache có liên quan;
- theo dõi thời gian từ lúc phát lệnh revoke tới lần từ chối thực tế cuối cùng.

Nếu cache verification không thể bị invalidated khẩn cấp, TTL của nó chính là một phần của cửa sổ ảnh hưởng khi signing key bị lộ.

## 14. Version hóa policy và cấu hình verifier

Kết quả cache có thể trở nên sai khi policy đổi dù token và chữ ký không đổi.

Các thay đổi có thể ảnh hưởng:

- allowlist thuật toán;
- issuer allowlist;
- expected audience;
- token profile hoặc `typ`;
- claim bắt buộc;
- clock skew và max token age;
- key size/curve policy;
- quy tắc sender constraint;
- revocation policy;
- tenant/resource mapping.

Gắn `verifierPolicyVersion` vào cache key. Khi policy thay đổi, tăng version hoặc tạo namespace mới. Không chỉ dựa vào việc đợi TTL cũ hết hạn nếu thay đổi là một yêu cầu bảo mật khẩn cấp.

Cần có quy trình rollout version nhất quán giữa các node. Nếu một số node dùng version mới và số khác vẫn dùng version cũ, kết quả có thể khác nhau theo node. Theo dõi version đang chạy và có thể loại node chưa cập nhật khỏi traffic nhạy cảm.

## 15. Negative caching và bảo vệ khỏi cache poisoning

### 15.1. Cache token không hợp lệ

Có thể cache một số kết quả từ chối xác định, ví dụ:

- cấu trúc token sai;
- chữ ký không hợp lệ;
- thuật toán bị policy cấm;
- `kid` không tồn tại sau lần refresh JWKS có kiểm soát;
- token profile không được endpoint hỗ trợ.

TTL nên ngắn và dung lượng phải giới hạn. Attacker có thể gửi vô số token ngẫu nhiên để làm đầy negative cache.

Không cache một lỗi hạ tầng tạm thời như thể token chắc chắn không hợp lệ. Ví dụ JWKS endpoint timeout là `verification_dependency_unavailable`, không phải `invalid_signature`. Khi dependency hoạt động lại, validator phải có cơ hội thử lại.

### 15.2. Cache unknown kid

Unknown `kid` có thể kích hoạt refresh JWKS. Nếu mỗi request với `kid` khác nhau đều gọi JWKS endpoint, attacker có thể gây refresh storm.

Biện pháp:

- single-flight refresh theo issuer;
- rate limit số lần refresh;
- negative cache unknown `kid` trong khoảng ngắn;
- giới hạn số `kid` và độ dài header;
- không fetch URL do token cung cấp;
- sau khi JWKS refresh thành công, kiểm tra lại key;
- nếu vẫn không có, từ chối token.

Negative cache phải được invalidated khi JWKS version đổi, để key mới vừa được công bố không bị từ chối kéo dài.

### 15.3. Không cache trạng thái unknown thành valid

Nếu revocation service, JWKS endpoint hoặc policy service không phản hồi, kết quả là unknown. Không chuyển unknown thành `not_revoked`, `trusted_key` hoặc `valid_token` chỉ để tăng availability.

Chính sách xử lý lỗi phải được quyết định theo rủi ro của endpoint. Với thao tác nhạy cảm, fail closed thường là lựa chọn cần thiết khi không thể xác minh trạng thái bắt buộc.

## 16. Cache phân tán, nhất quán và nhiều vùng

Trong hệ thống nhiều node, cache local có thể khiến mỗi node có một trạng thái khác nhau. Ví dụ node A nhận sự kiện revoke và xóa entry, nhưng node B chưa nhận được sự kiện và vẫn trả cache hit.

Các câu hỏi phải trả lời:

- revocation state có consistency model nào?
- invalidation event được retry và replay ra sao?
- node mới khởi động lấy version hiện tại bằng cách nào?
- cache local có được dùng khi distributed cache mất kết nối không?
- multi-region có thể chấp nhận stale state tối đa bao lâu?
- event cũ hoặc đến sai thứ tự có thể làm trạng thái quay lùi không?

Dùng sequence/version đơn điệu để ngăn event cũ ghi đè trạng thái mới. Khi node mất kết nối quá thời hạn cho phép, nó phải làm mới trạng thái trước khi tiếp tục chấp nhận token ở endpoint yêu cầu thu hồi gần thời gian thực.

Không coi eventual consistency là đủ cho mọi use case. Nếu nghiệp vụ yêu cầu thu hồi gần như tức thời, cần kho trạng thái có consistency phù hợp hoặc introspection trực tuyến; cache phải có cơ chế invalidation và giới hạn stale rõ ràng.

## 17. Cache outage và lựa chọn fail-open/fail-closed

Phân biệt cache kết quả xác minh với kho trạng thái bảo mật:

| Thành phần lỗi | Cách xử lý có thể cân nhắc |
| --- | --- |
| Verification cache không sẵn sàng | Bỏ qua cache và xác minh mật mã trực tiếp bằng khóa tin cậy |
| JWKS cache không sẵn sàng nhưng key set còn trong cache hợp lệ | Dùng stale key chỉ trong giới hạn policy được phê duyệt |
| Không có khóa tin cậy và JWKS endpoint lỗi | Không thể xác minh chữ ký; từ chối hoặc trả lỗi dependency |
| Revocation store lỗi | Không coi token là chưa thu hồi; fail closed với endpoint yêu cầu trạng thái này |
| Invalidation bus lỗi | Giới hạn thời gian dùng cache stale; đồng bộ lại version trước khi tiếp tục |
| Authorization cache lỗi | Tính lại policy nếu có đủ dữ liệu; không tự động allow |
| Policy/configuration service lỗi | Dùng cấu hình đã version hóa trong thời hạn an toàn hoặc từ chối theo policy |

Verification cache chỉ bỏ qua phép tính đã có kết quả. Nếu cache miss và hệ thống có thể xác minh trực tiếp bằng key đã tin cậy, hãy làm như vậy.

Nếu cache là nơi duy nhất lưu revocation state hoặc grant version, cache outage có ý nghĩa bảo mật khác. Không áp dụng một quy tắc fail-open chung cho tất cả các loại cache.

## 18. Dung lượng, eviction và chống cache stampede

Cache cần giới hạn:

- số entry tổng và theo issuer/tenant;
- kích thước claims/metadata mỗi entry;
- tổng bộ nhớ;
- TTL tối đa;
- số lần refresh JWKS đồng thời;
- số request đang chờ cùng một key;
- tốc độ tạo negative entry.

Dùng LRU/LFU hoặc policy eviction phù hợp, nhưng eviction không được làm suy yếu kiểm tra. Khi entry bị eviction, hệ thống phải xác minh lại token hoặc truy vấn trạng thái cần thiết.

Để chống cache stampede:

- single-flight: nhiều request cùng token chỉ tạo một lần xác minh/refresh đồng thời;
- request coalescing theo issuer hoặc key;
- jitter giảm TTL theo hướng hết hạn sớm, không bao giờ kéo dài deadline;
- giới hạn concurrency và timeout;
- circuit breaker cho dependency bên ngoài;
- stale-while-revalidate chỉ khi policy cho phép và không áp dụng cho trạng thái thu hồi nhạy cảm mà không có giới hạn stale.

Không dùng stale-while-revalidate để tiếp tục chấp nhận token đã bị revoke nếu SLA yêu cầu thu hồi tức thời.

## 19. Quan sát hiệu năng và độ trễ thu hồi

Metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `jwt_verify_cache_hit_total` | Số cache hit cho kết quả xác minh |
| `jwt_verify_cache_miss_total` | Số cache miss |
| `jwt_verify_duration_seconds` | Thời gian xác minh khi miss |
| `jwt_verify_cache_entry_ttl_seconds` | TTL còn lại hoặc bucket TTL |
| `jwt_revocation_lookup_duration_seconds` | Chi phí kiểm tra trạng thái thu hồi |
| `jwt_revocation_cache_hit_total` | Hit của revocation state cache |
| `jwt_revocation_invalidation_delay_seconds` | Độ trễ từ revoke event tới invalidation |
| `jwt_key_cache_version` | Phiên bản key set đang dùng |
| `jwt_unknown_kid_refresh_total` | Số lần refresh do unknown key |
| `jwt_cache_eviction_total` | Số entry bị eviction |
| `jwt_cache_dependency_error_total` | Lỗi dependency của cache/store |

Không dùng raw token, token fingerprint, `jti`, email hoặc subject làm metric label. Dùng label có cardinality thấp như issuer alias, profile, algorithm, result class và region.

Đo độ trễ thu hồi đầu-cuối:

\[
RevocationDelay = t_{lastAcceptedAfterRevoke} - t_{revokeRequested}
\]

Mục tiêu là giá trị này không vượt SLA đã định. Theo dõi p50/p95/p99 và giá trị lớn nhất; trung bình có thể che giấu một node hoặc region bị stale lâu.

Cần phân biệt cache hit ratio cao với hệ thống an toàn. Hit ratio cao không có ý nghĩa nếu cache giữ kết quả chấp nhận quá lâu hoặc invalidation không hoạt động.

## 20. Mã giả tạo và sử dụng positive validation cache

~~~text
function validateJwt(request, token):
    profile = endpointPolicy.expectedProfile
    issuer = selectTrustedIssuerCandidate(token, endpointPolicy.trustedIssuers)

    require issuer exists
    header = parseBoundedProtectedHeader(token)
    require header.alg in endpointPolicy.allowedAlgorithms(profile)

    fingerprint = HMAC_SHA256(cacheFingerprintKey, exactBytes(token))

    cacheKey = buildKey(
        issuer.id,
        profile.id,
        endpointPolicy.expectedAudience,
        endpointPolicy.policyVersion,
        issuer.configurationVersion,
        fingerprint
    )

    entry = verificationCache.get(cacheKey)

    if entry exists:
        require entry.keyThumbprint is currently trusted
        require entry.policyVersion == endpointPolicy.policyVersion
        require timeClaimsStillValid(entry.claims, currentUtcTime)
        require revocationStateFreshOrRechecked(entry, request)
        return verifiedClaims(entry.claims)

    key = trustedKeyResolver.resolve(issuer, header.kid, header.alg)
    claims = verifySignatureAndValidateFullProfile(token, key, profile)

    revocation = checkRevocation(claims, issuer, profile)
    require revocation == NOT_REVOKED

    deadline = min(
        effectiveTokenExpiry(claims, profile),
        maxTokenAgeDeadline(claims, profile),
        revocationFreshUntil(revocation),
        keyTrustDeadline(key, issuer),
        policyValidityDeadline(endpointPolicy),
        currentUtcTime + endpointPolicy.maxVerificationCacheTtl
    )

    ttl = deadline - currentUtcTime
    if ttl > 0:
        verificationCache.put(
            cacheKey,
            value = verifiedClaimsAndProvenance(claims, key, policy),
            ttl = ttl
        )

    return verifiedClaims(claims)
~~~

Đây là pseudocode minh họa. Các hàm thời gian, revocation, issuer selection và key trust phải tuân thủ đúng profile. Nếu cache hit không kiểm tra lại trạng thái thu hồi, entry phải có deadline được giới hạn theo độ mới tối đa của trạng thái `not_revoked` và phải được invalidated khi có sự kiện revoke.

Không trả `ACCEPT` chỉ vì entry tồn tại. Phải kiểm tra phiên bản policy, trust material và mọi điều kiện động mà entry không bảo đảm.

## 21. Sơ đồ luồng xác minh có cache

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Parse giới hạn kích thước và chọn profile"]
    B --> C["Chọn issuer từ trust configuration"]
    C --> D["Tạo fingerprint HMAC và cache key"]
    D --> E{"Verification cache hit?"}
    E -- "Có" --> F["Kiểm tra policy/key version và time claims"]
    F --> G["Kiểm tra revocation freshness hoặc tra cứu lại"]
    G --> H{"Mọi điều kiện còn hợp lệ?"}
    H -- "Có" --> I["Trả verified claims"]
    H -- "Không" --> J["Xóa entry và chạy validation đầy đủ"]
    E -- "Không" --> J
    J --> K["Lấy key từ JWKS tin cậy"]
    K --> L["Verify chữ ký và token profile"]
    L --> M["Kiểm tra revocation"]
    M --> N{"Hợp lệ và chưa revoke?"}
    N -- "Không" --> O["Từ chối"]
    N -- "Có" --> P["Tính deadline cache tối đa"]
    P --> Q["Lưu entry nếu TTL dương"]
    Q --> I
~~~

Cache hit bỏ qua công việc đã được chứng minh còn hiệu lực; các kiểm tra phụ thuộc thời gian, trust version và trạng thái thu hồi vẫn phải được bảo đảm.

## 22. Ví dụ tính TTL và độ trễ thu hồi

Giả sử:

- `now` = 10:00:00;
- `exp` = 10:05:00;
- clock skew leeway = 10 giây;
- max verification cache TTL = 60 giây;
- revocation status vừa được kiểm tra tại 10:00:00;
- max age của kết quả `not_revoked` = 15 giây;
- key trust và policy còn hiệu lực lâu hơn.

Khi đó:

- deadline token theo policy = 10:05:10;
- deadline cache tối đa = 10:01:00;
- deadline revocation freshness = 10:00:15.

Deadline cuối cùng là 10:00:15, vì đây là điều kiện hết hạn sớm nhất. TTL thực tế là 15 giây.

Nếu token bị thu hồi lúc 10:00:07 và invalidation event bị mất, cache `not_revoked` có thể vẫn được dùng tới 10:00:15. Độ trễ tối đa trong ví dụ là 8 giây kể từ lúc revoke. Nếu hệ thống cần độ trễ dưới 1 giây, TTL 15 giây không đáp ứng SLA; cần invalidation đáng tin cậy hơn hoặc kiểm tra trạng thái trực tuyến.

Ví dụ cho thấy TTL phải được suy ra từ yêu cầu thu hồi và thời hạn token, không chọn chỉ dựa trên hit ratio.

## 23. Kiểm thử cache và ràng buộc thời hạn/thu hồi

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Positive cache | Token hợp lệ được xác minh lần đầu, request lặp lại | Cache hit, kết quả vẫn đúng profile |
| Cache isolation | Cùng token gọi endpoint có audience khác | Không tái sử dụng entry sai audience |
| Profile isolation | ID Token được gửi tới endpoint access token | Không dùng cache entry của ID Token |
| One-time proof | DPoP proof giống hệt được gửi lần thứ hai khi signature cache hit | Replay bị từ chối; cache không bỏ qua `jti`/nonce consume |
| Issuer isolation | Hai issuer có cùng `kid` | Không dùng chéo cache/key |
| Policy version | Allowlist hoặc claim policy thay đổi | Entry version cũ không còn được dùng |
| Expiry | Cache entry gần `exp` | TTL không vượt deadline chấp nhận |
| Expiry boundary | Request tại/sau thời điểm hết hạn | Từ chối theo quy tắc thời gian |
| Max age | `iat` vượt tuổi tối đa | Từ chối dù cache entry cũ còn tồn tại |
| Nbf | Token chưa tới `nbf` | Không tạo positive entry |
| Revocation | Token bị revoke khi cache `not_revoked` còn sống | Invalidation hoặc TTL buộc từ chối trong SLA |
| Grant revoke | Grant version tăng | Token mang version cũ bị từ chối |
| Key revoke | Key thumbprint bị thu hồi | Cache entry ký bằng key đó bị vô hiệu hóa |
| Key rotation | Key cũ/mới trong overlap | Chấp nhận đúng giai đoạn policy |
| Unknown kid | Nhiều request với `kid` lạ | Refresh JWKS có rate limit/single-flight |
| Revocation outage | Kho thu hồi timeout | Không biến trạng thái unknown thành not-revoked |
| Cache outage | Verification cache ngừng hoạt động | Xác minh trực tiếp nếu dependencies tin cậy còn sẵn sàng |
| Distributed invalidation | Node A nhận revoke, node B bị mất event | B làm mới version trong giới hạn stale |
| Out-of-order event | Event version cũ đến sau event mới | Không làm trạng thái quay lùi |
| Cache poisoning | Token/context khác tạo cache key tương tự theo input | Namespace/fingerprint ngăn dùng chéo |
| Capacity | Attacker gửi nhiều token ngẫu nhiên | Cache bounded, không cạn bộ nhớ |
| Logging | Cache miss/hit và error | Không log raw token hoặc secret |

Nên kiểm thử với fixed clock và kho revocation giả lập có thể điều khiển thời điểm revoke, event delivery, timeout và replication lag. Kiểm thử nhiều node/region để đo độ trễ thực tế, không chỉ kiểm tra unit test của cache adapter.

## 24. Quy trình xử lý sự cố cache chấp nhận token đã revoke

Khi phát hiện token bị revoke nhưng vẫn được chấp nhận:

1. Xác định thời điểm revoke được ghi nhận tại nguồn.
2. Tìm node/region cuối cùng đã chấp nhận token sau thời điểm đó.
3. Xác định cache layer gây stale: verification result, revocation state, JWKS hay authorization decision.
4. Kiểm tra TTL entry, key namespace, policy version và invalidation event.
5. Xóa hoặc tăng version namespace bị ảnh hưởng; không chỉ xóa một dashboard metric.
6. Nếu signing key bị compromise, vô hiệu hóa key thumbprint và cache entry liên quan trên toàn hệ thống.
7. Kiểm tra các side effect đã được thực hiện bằng token trong cửa sổ stale.
8. Đo revocation delay đầu-cuối và so với SLA.
9. Khắc phục event loss, stale replica, cache TTL hoặc failure policy.
10. Thêm regression test cho đúng đường đi đã gây sự cố.

Không chỉ tăng tần suất xóa cache mà không xác định nguyên nhân. Nếu key namespace hoặc issuer binding sai, xóa cache tạm thời không sửa được lỗi gốc.

## 25. Những sai lầm thiết kế thường gặp

- Cache kết quả `valid=true` vô thời hạn.
- Dùng TTL cố định dài hơn thời gian còn lại của token.
- Không áp dụng max token age dựa trên `iat`.
- Cache `not_revoked` quá lâu so với revocation SLA.
- Coi timeout revocation store là trạng thái chưa thu hồi.
- Không invalidate cache khi revoke grant hoặc signing key.
- Chỉ dùng `kid` làm định danh khóa.
- Dùng cùng cache entry cho issuer, audience hoặc profile khác nhau.
- Gộp token validation và authorization decision.
- Cho cache local từng node có trạng thái khác nhau không giới hạn.
- Dùng stale-while-revalidate cho trạng thái thu hồi nhạy cảm.
- Cache lỗi hạ tầng như lỗi token vĩnh viễn.
- Để unknown `kid` gây JWKS refresh storm.
- Không giới hạn negative cache và dung lượng tổng.
- Dùng raw JWT làm cache key hoặc metric label.
- Không version hóa policy/configuration.
- Tin rằng JWT có thể revoke tức thời dù không có trạng thái thu hồi bổ sung.

## 26. Checklist triển khai

**Phạm vi cache:**

- [ ] Tách JWKS cache, signature cache, full validation cache, revocation cache và authorization cache.
- [ ] Xác định rõ kiểm tra nào được bỏ qua khi cache hit và kiểm tra nào phải chạy lại.
- [ ] Cache key có issuer, profile, audience, policy/config version và token fingerprint.
- [ ] Token fingerprint dùng HMAC key riêng; raw token không xuất hiện trong key/log/metric.

**Thời hạn:**

- [ ] TTL không vượt deadline `exp` cộng leeway được phép.
- [ ] Có giới hạn max token age dựa trên `iat` khi profile yêu cầu.
- [ ] `nbf`, `iat`, `exp` và clock skew được kiểm tra nhất quán.
- [ ] TTL tính theo deadline sớm nhất, không làm tròn kéo dài hiệu lực.
- [ ] Clock được đồng bộ giữa issuer, verifier và cache nodes.

**Thu hồi và khóa:**

- [ ] Có mô hình revoke rõ: `jti`, fingerprint, grant/session version, introspection hoặc key revoke.
- [ ] Cache `not_revoked` bị giới hạn theo revocation SLA.
- [ ] Không coi dependency error là `not_revoked`.
- [ ] Có push invalidation, TTL fallback hoặc versioned namespace.
- [ ] Key rotation/revocation làm cache entry cũ không còn hợp lệ.
- [ ] Cache được namespace theo issuer và key thumbprint/version.

**Phân tán và vận hành:**

- [ ] Có consistency/freshness policy cho nhiều node và region.
- [ ] Có single-flight, rate limit và negative cache cho unknown `kid`.
- [ ] Cache có giới hạn dung lượng và chống cache stampede.
- [ ] Fail-open/fail-closed được định nghĩa riêng cho từng dependency.
- [ ] Metric đo hit ratio và revocation delay mà không chứa credential.
- [ ] Có test fixed clock, revoke event loss, out-of-order event và cache outage.
- [ ] Có runbook xử lý token bị chấp nhận sau revoke.

## 27. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered claims `exp`, `nbf`, `iat`, `iss`, `aud` và `jti`.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và quản lý khóa công khai.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT theo profile, issuer, audience và thuật toán.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token tại authorization server.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): truy vấn trạng thái active của token.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token và các claim liên quan.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ vòng đời token và giảm rủi ro bảo mật OAuth.

**Ghi nhớ:** Cache có thể giảm chi phí xác minh nhưng không được kéo dài quyền sử dụng token. Hãy namespace entry theo issuer, profile, audience, key và policy; giới hạn TTL bởi thời hạn token cùng độ mới của trạng thái thu hồi; invalidate khi grant, key hoặc policy thay đổi; và đo độ trễ từ lúc revoke tới lần chấp nhận cuối cùng. Cache hit chỉ là cách tái sử dụng kết quả đã xác minh trong giới hạn tin cậy đã định nghĩa.

