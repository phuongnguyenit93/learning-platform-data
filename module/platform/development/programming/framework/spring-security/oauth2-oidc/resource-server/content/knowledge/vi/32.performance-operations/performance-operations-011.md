# Diễn tập nhà phát hành ngừng hoạt động và xác định phụ thuộc còn cần thiết

Một OAuth 2.0 Resource Server cần biết Authorization Server nào đã phát hành token và dùng cách nào để xác minh token. Khi nhà phát hành ngừng hoạt động, tác động phụ thuộc vào loại access token và cách Resource Server được cấu hình:

- **JWT access token** có thể được xác minh cục bộ bằng chữ ký và public key đã tải từ JWKS. Khi key còn trong cache, một outage ngắn của metadata/JWKS server không nhất thiết làm request hiện tại thất bại.
- **Opaque access token** thường cần gọi introspection endpoint để biết token có còn active hay không. Nếu endpoint không truy cập được và không có cache được thiết kế rõ ràng, Resource Server không thể xác minh token và phải từ chối request được bảo vệ.
- **Discovery metadata** thường là phụ thuộc lúc khởi tạo hoặc bootstrap decoder khi dùng `issuer-uri` theo cách discovery. Nó không phải một request bắt buộc cho từng JWT.
- **Token endpoint, authorization endpoint, UserInfo và logout endpoint** thường không nằm trên đường xác minh access token của Resource Server. Chúng có thể cần cho các vai trò khác của hệ thống, nhưng không nên mặc định coi chúng là runtime dependency của Resource Server.

Bài này hướng dẫn diễn tập outage có kiểm soát, quan sát hành vi thật của ứng dụng và phân loại phụ thuộc theo vòng đời. Mục tiêu là biết service có thể tiếp tục phục vụ trường hợp nào, trường hợp nào phải fail closed, và cần cấu hình gì để khởi động/hoạt động an toàn khi identity provider không sẵn sàng.

> **Nguyên tắc vận hành:** Không bỏ qua xác minh token khi nhà phát hành lỗi. JWT có thể tiếp tục được xác minh bằng key tin cậy đã cache; opaque token chỉ được chấp nhận nếu introspection hoặc cache hợp lệ xác nhận trạng thái. Nếu không còn bằng chứng xác thực đủ tin cậy, từ chối request.

## 1. Xác định nhà phát hành và các phụ thuộc

Trước khi tắt một dịch vụ trong diễn tập, cần lập bản đồ các phụ thuộc của Resource Server. Một hệ thống thường có nhiều endpoint cùng thuộc một IdP, nhưng không phải endpoint nào cũng nằm trên request path.

### 1.1. Các endpoint identity thường gặp

| Endpoint | Mục đích | Resource Server có cần trực tiếp không? |
| --- | --- | --- |
| OIDC Provider Configuration | Discovery metadata, công bố issuer và `jwks_uri` | Cần nếu dùng discovery để tìm JWKS; không cần cho từng request JWT |
| OAuth Authorization Server Metadata | Metadata theo RFC 8414 | Tương tự: cần nếu dùng discovery path tương ứng |
| JWKS endpoint | Cung cấp public keys xác minh chữ ký JWT | Cần khi tải/refresh signing keys; không nhất thiết cho từng request nếu key đã cache |
| Token introspection endpoint | Kiểm tra trạng thái opaque token | Thường cần cho mỗi request, trừ khi có cache introspection được thiết kế rõ |
| Token endpoint | Cấp access token cho OAuth2 Client | Không phải phụ thuộc mặc định của Resource Server JWT/opaque |
| Authorization endpoint | Đăng nhập/consent/authorization code | Không phải phụ thuộc mặc định của Resource Server |
| UserInfo endpoint | Lấy thông tin profile OIDC | Không cần để xác minh access token thông thường |
| Revocation endpoint | Client yêu cầu thu hồi token | Không phải endpoint Resource Server gọi để xác minh từng request |
| End-session/logout endpoint | Kết thúc phiên OIDC | Không nằm trên đường xác minh access token thông thường |

Điểm cần phân biệt là **Resource Server xác minh token đã được cấp**, còn OAuth2 Client hoặc OIDC relying party có thể cần những endpoint khác để xin token, đăng nhập hoặc lấy profile.

### 1.2. Phụ thuộc theo từng giai đoạn

| Giai đoạn | JWT Resource Server | Opaque-token Resource Server |
| --- | --- | --- |
| Application startup | Có thể cần discovery metadata nếu cấu hình `issuer-uri` và decoder thực hiện discovery khi khởi tạo; có thể tránh discovery bằng `jwk-set-uri` trực tiếp | Cần cấu hình introspection URI và client authentication; thường không cần gọi endpoint chỉ để tạo introspector |
| Lần xác minh JWT đầu tiên | Cần public key phù hợp; có thể fetch JWKS | Cần introspection endpoint trả `active=true` |
| Request tiếp theo | Signature/issuer/time/audience thường kiểm tra cục bộ bằng key đã tải | Thường gọi introspection lại, trừ khi có cache |
| Gặp `kid` chưa biết | Có thể cần refresh JWKS để tìm key mới | Không áp dụng |
| Key rotation | Cần JWKS mới và overlap key | Không áp dụng theo cách ký JWT |
| Revocation | Thường không được biết ngay nếu token còn hạn và không có denylist/introspection bổ sung | Có thể được phản ánh ở lần introspection tiếp theo, tùy cache |
| Nhà phát hành ngừng hoạt động | Token có key đã cache có thể vẫn dùng được cho đến khi hết hạn hoặc cần key mới | Request mới thường thất bại nếu không thể introspect và không có cache hợp lệ |

### 1.3. Những phụ thuộc nền tảng vẫn còn cần thiết

Ngay cả khi IdP không truy cập được, Resource Server vẫn phụ thuộc vào:

- Cấu hình issuer, audience, JWKS/introspection URI và trust policy đúng.
- DNS, network route và TLS trust khi cần kết nối đến endpoint identity.
- Đồng hồ hệ thống đồng bộ để kiểm tra `exp`, `nbf`, `iat` và clock skew.
- Cache key/token có lifecycle và giới hạn rõ ràng.
- Khả năng phục vụ HTTP request, thread pool, connection pool và logging/metrics.
- Quyền truy cập tài nguyên nghiệp vụ và các dependency downstream khác.

Không nên gộp tất cả thành một trạng thái “IdP down”. Ví dụ, metadata endpoint lỗi trong khi JWKS cache còn hiệu lực là một trạng thái khác với introspection endpoint lỗi cho mọi opaque token.

## 2. Mô hình xác minh JWT khi nhà phát hành offline

JWT access token chứa header và claims được ký. Resource Server xác minh chữ ký bằng public key của issuer, rồi kiểm tra issuer, audience, thời hạn và các validator theo contract.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant Cache as JWKS cache
    participant AS as Identity Provider

    C->>RS: Bearer JWT
    RS->>Cache: Tìm key theo kid
    alt Key còn trong cache
        Cache-->>RS: Public key đã tin cậy
        RS->>RS: Verify signature + iss/aud/exp
        RS-->>C: Xử lý request
    else Key chưa có / cần refresh
        RS->>AS: GET JWKS
        alt Identity Provider online
            AS-->>RS: JWK Set mới
            RS->>RS: Verify signature + claims
            RS-->>C: Xử lý request nếu hợp lệ
        else Identity Provider offline
            AS--xRS: Timeout / connection error
            RS-->>C: Authentication failure
        end
    end
~~~

### 2.1. Issuer validation là kiểm tra cục bộ

Validator issuer so sánh claim `iss` trong JWT với issuer tin cậy đã cấu hình. Khi đã có JWT và public key, phép so sánh này không cần gọi lại issuer endpoint.

Ví dụ:

~~~java
OAuth2TokenValidator<Jwt> issuerValidator =
        new JwtIssuerValidator(
            "https://identity.example.test/realms/shop");
~~~

Validator này không chứng minh nhà phát hành đang online; nó xác minh token tuyên bố được phát hành bởi đúng issuer đã cấu hình. Chữ ký vẫn phải hợp lệ với key tin cậy.

### 2.2. Audience và thời hạn vẫn phải được kiểm tra

Outage không làm thay đổi contract của token. Resource Server vẫn phải kiểm tra:

- `aud` chứa resource server hiện tại.
- `exp` chưa qua thời hạn, có xét clock skew cấu hình.
- `nbf` đã đến thời điểm có hiệu lực.
- Signature đúng với key tin cậy.
- Scope/authority đủ cho endpoint.
- Token profile và claim bắt buộc phù hợp policy.

Không được bỏ validator issuer/audience hoặc kéo dài thời hạn chỉ vì IdP tạm thời không sẵn sàng.

### 2.3. Khi nào JWKS endpoint thực sự được gọi?

Resource Server không cần fetch JWKS cho mọi request. Decoder thường dùng JWK Set đã tải/cached để chọn key theo `kid`. Việc fetch/refresh có thể xảy ra khi:

- Decoder cần tải key set lần đầu.
- Token mang `kid` mà key set hiện tại không có.
- Cache hết hạn hoặc cơ chế refresh yêu cầu tải lại.
- Ứng dụng tạo decoder/context mới.

Chi tiết cache và refresh phụ thuộc phiên bản Spring Security, Nimbus JOSE và cache được cấu hình. Khi diễn tập, quan sát request thực tế đến JWKS endpoint thay vì suy luận từ số request API.

### 2.4. Token đã ký bằng key cũ vẫn có thể hợp lệ

Nếu JWKS cache đang giữ public key A và token được ký bằng private key A, Resource Server có thể tiếp tục xác minh token trong lúc JWKS server offline. Điều này chỉ đúng khi:

- Cache còn giữ key A.
- Token chưa hết hạn và các claims khác vẫn hợp lệ.
- Policy cho phép tiếp tục dùng key đã tải.
- Không có yêu cầu thu hồi tức thời hoặc denylist online.

Đây là availability trade-off có chủ đích của JWT. Nó không phải cơ chế revocation tức thời.

### 2.5. Token có `kid` mới khi JWKS offline

Nếu Authorization Server đã bắt đầu ký token bằng key B nhưng Resource Server chỉ có key A, decoder cần tìm key B. Khi JWKS endpoint offline, decoder không có cơ sở để tin key B và phải từ chối token đó.

Không chấp nhận token chỉ vì:

- Claims nhìn có vẻ hợp lệ.
- `iss` đúng.
- `sub` tồn tại.
- Một key khác cùng issuer đang được cache.

Key selection và signature verification là bắt buộc. Không fallback sang “bất kỳ public key nào” hoặc tắt kiểm tra chữ ký.

## 3. Mô hình opaque token khi nhà phát hành offline

Opaque token không cung cấp một bộ claims có chữ ký để Resource Server tự xác minh như JWT. Resource Server gọi introspection endpoint và dựa vào response của Authorization Server.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant AS as Introspection endpoint

    C->>RS: Bearer opaque-token
    RS->>AS: POST /introspect
    alt AS trả active=true
        AS-->>RS: active + scope + claims
        RS->>RS: Tạo Authentication và authorize
        RS-->>C: Xử lý request nếu đủ quyền
    else AS trả active=false
        AS-->>RS: active=false
        RS-->>C: 401 Unauthorized
    else AS offline
        AS--xRS: Timeout / connection error
        RS-->>C: Không xác minh được token
    end
~~~

### 3.1. Không thể xác minh opaque token chỉ từ token string

Nếu introspection endpoint không trả lời, Resource Server không biết token còn active, đã bị thu hồi, hết hạn hay thuộc resource nào. Vì vậy, mặc định an toàn là fail closed: request protected không được authenticate.

Một cache introspection có thể giảm dependency trực tiếp, nhưng tạo ra khoảng thời gian mà Resource Server tiếp tục tin kết quả cũ sau khi token bị thu hồi. TTL phải được chọn theo yêu cầu revocation và threat model.

### 3.2. Cache introspection là quyết định bảo mật

Nếu cache response `active=true` trong 60 giây, một token bị thu hồi ngay sau khi cache được tạo có thể vẫn được chấp nhận trong phần còn lại của TTL. TTL càng dài:

- Availability khi IdP offline càng tốt.
- Số lần introspection càng thấp.
- Thời gian phản ánh revocation càng chậm.

Không bật cache tùy tiện để “fix outage”. Ghi rõ TTL, key cache, claims được lưu, eviction policy và cách xử lý token inactive. Không cache theo chuỗi token chưa được bảo vệ trong log/metrics.

### 3.3. Không dùng JWT cache policy cho opaque token

JWKS cache lưu public keys dùng để xác minh chữ ký; introspection cache lưu kết quả trạng thái/quyền của token. Hai loại cache có ý nghĩa và rủi ro khác nhau:

| Thuộc tính | JWKS cache | Introspection cache |
| --- | --- | --- |
| Dữ liệu | Public JWK Set | Token status và claims |
| Key tra cứu | JWKS URI/issuer | Token identity hoặc secure hash |
| Dùng để | Verify chữ ký | Quyết định token còn active |
| Rủi ro khi stale | Không có key mới hoặc còn giữ key cũ | Token revoked vẫn được coi active |
| Refresh trigger | TTL, `kid` chưa biết, cache policy | TTL, request, explicit invalidation |

## 4. Cấu hình để giảm phụ thuộc discovery lúc startup

Với JWT Resource Server, cấu hình `issuer-uri` giúp Spring Security xác định issuer và discovery metadata để tìm JWKS URI. Trong một số cách khởi tạo/context, discovery có thể diễn ra khi decoder bean được tạo, khiến ứng dụng phụ thuộc metadata endpoint lúc startup.

Nếu muốn Resource Server biết JWKS URI trực tiếp và không cần discovery metadata để tìm key, có thể cấu hình cả issuer và JWK Set URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/shop
          jwk-set-uri: https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

Với cấu hình này:

- `jwk-set-uri` chỉ rõ nơi tải JWK Set.
- `issuer-uri` vẫn cung cấp issuer để validate claim `iss`.
- Decoder không cần discovery metadata chỉ để tìm JWKS URI.
- Lần cần key mà cache chưa có vẫn cần truy cập JWKS endpoint.

Đây là cách giảm một phụ thuộc bootstrap, không biến JWT Resource Server thành hệ thống không cần identity provider trong mọi tình huống.

### 4.1. Direct JWKS URI không bỏ qua signature verification

Không được nhầm việc cấu hình URI trực tiếp với việc tin token mà không xác minh. Decoder vẫn cần tải public JWK từ URI đã tin cậy, chọn key phù hợp với JOSE header/`kid`, xác minh chữ ký và thuật toán được cho phép, rồi chạy issuer/time/audience/custom validators.

Không lấy `jwk-set-uri` từ request parameter, JWT payload hoặc một nguồn do caller điều khiển.

### 4.2. Phân biệt startup và first authenticated request

Tùy cách tạo decoder và framework lifecycle, HTTP fetch metadata/JWKS có thể xảy ra ở thời điểm khởi tạo hoặc lần decode đầu tiên. Test cần ghi nhận chính xác:

- Ứng dụng có bind port và khởi động khi metadata server offline không?
- Context có khởi tạo thành công khi JWKS server offline không?
- Request protected đầu tiên với key chưa cache trả kết quả gì?
- Request sau khi key đã cache có tiếp tục được xác minh khi JWKS server offline không?

Không chỉ assert `ApplicationContext` startup thành công rồi kết luận Resource Server sẵn sàng xác thực mọi token. Startup, readiness và khả năng xác minh token là ba điều kiện khác nhau.

## 5. Diễn tập outage theo từng giai đoạn

Một diễn tập có giá trị phải thay đổi đúng dependency, tạo ra request có kiểm soát và ghi nhận kết quả. Không chỉ dừng IdP rồi quan sát dashboard chung.

### 5.1. Chuẩn bị trước khi diễn tập

Ghi lại:

- Loại token đang dùng: JWT hay opaque.
- Issuer, audience, JWKS URI hoặc introspection URI.
- Cách tạo decoder/introspector và thời điểm remote call xảy ra.
- JWKS/introspection cache implementation, TTL và eviction.
- Token lifetime, clock skew và key rotation schedule.
- HTTP connect/read timeout, retry policy và circuit breaker.
- Liveness/readiness policy và cách load balancer loại instance.
- Baseline latency, error rate, request rate và số lần gọi IdP.

Chuẩn bị token fixture riêng:

| Fixture | Mục đích |
| --- | --- |
| JWT-A | Ký bằng key A đã publish và đã được Resource Server tải |
| JWT-B | Ký bằng key B, dùng để kiểm tra unknown `kid`/rotation |
| JWT-expired | Xác minh token hết hạn vẫn bị từ chối |
| JWT-wrong-audience | Xác minh audience validation không bị bỏ |
| Opaque-active | Introspection trả active |
| Opaque-revoked | Introspection trả inactive |
| Opaque-unknown | Token không có trong registry của test IdP |

Không dùng token production hoặc tài khoản người dùng thật để diễn tập.

### 5.2. Scenario A — Metadata endpoint offline trước startup

Mục tiêu: xác định ứng dụng có cần metadata discovery để tạo decoder hay không.

Các bước:

1. Chặn metadata endpoint của test IdP.
2. Khởi động ứng dụng với cấu hình hiện tại.
3. Ghi nhận Spring ApplicationContext có khởi tạo thành công không.
4. Nếu context không lên, thử cấu hình JWKS URI trực tiếp cùng issuer validation.
5. Khởi động lại với metadata vẫn offline.
6. Ghi nhận app startup, readiness và request protected đầu tiên.

Kết quả cần phân loại:

| Cấu hình | Kết quả mong đợi cần xác minh |
| --- | --- |
| `issuer-uri` dùng discovery | Startup/decoder initialization có thể cần metadata tùy cách khởi tạo |
| `issuer-uri` + `jwk-set-uri` | Có thể bỏ discovery để tìm JWKS; lần fetch key vẫn cần JWKS endpoint |
| `jwk-set-uri` trực tiếp, issuer validator riêng | Không cần metadata discovery; vẫn cần key và issuer validation |

Đừng biến kết quả của một version/framework configuration thành quy luật cho mọi ứng dụng. Test đúng dependency versions và bean lifecycle đang chạy.

### 5.3. Scenario B — JWKS offline sau khi key đã được tải

Mục tiêu: xác định Resource Server có thể tiếp tục xác minh JWT bằng cached key.

Các bước:

1. Cho metadata/JWKS endpoint hoạt động.
2. Gửi JWT-A để buộc decoder tải key A.
3. Xác nhận request thành công và JWKS request đã xảy ra.
4. Chặn JWKS endpoint, giữ metadata endpoint ở trạng thái offline hoặc không liên quan.
5. Gửi lại JWT-A nhiều lần trong khoảng thời gian ngắn.
6. Quan sát success rate, latency và số lần JWKS refresh.
7. Gửi JWT-expired và JWT-wrong-audience để xác nhận validator vẫn hoạt động.

Kỳ vọng: nếu decoder vẫn có key A hợp lệ trong cache và token còn hạn, JWT-A có thể tiếp tục được chấp nhận. Token hết hạn/audience sai vẫn bị từ chối. Outage không được làm yếu validator.

### 5.4. Scenario C — JWKS offline khi gặp key mới

Mục tiêu: xác định service xử lý an toàn khi IdP rotation trong lúc JWKS không truy cập được.

Các bước:

1. Resource Server chỉ tải public key A.
2. Test IdP bắt đầu ký JWT-B bằng key B, `kid=B`.
3. Chặn JWKS endpoint trước khi Resource Server tải B.
4. Gửi JWT-B.
5. Ghi nhận decoder có thử refresh JWKS và request bị từ chối hay không.
6. Mở lại JWKS với key A + B.
7. Gửi lại JWT-B sau khi decoder đã có thể tải key mới.

Kỳ vọng: JWT-B không được chấp nhận khi Resource Server chưa có key B tin cậy. Sau khi JWKS sẵn sàng và decoder tải được B, token có thể được xác minh nếu claims hợp lệ.

### 5.5. Scenario D — Introspection endpoint offline

Mục tiêu: xác định tác động của IdP đối với opaque-token traffic.

Các bước:

1. Xác nhận Opaque-active được chấp nhận khi introspection server online.
2. Chặn introspection endpoint.
3. Gửi lại Opaque-active.
4. Gửi Opaque-revoked và Opaque-unknown.
5. Quan sát timeout, status code, latency và số lần introspection.
6. Mở lại endpoint, xác nhận traffic phục hồi.

Không có cache: request protected cần introspection thường thất bại khi endpoint offline. Có cache: kết quả phụ thuộc entry còn TTL hay không. Phải đo và ghi rõ stale window, không chỉ ghi “opaque token vẫn chạy”.

### 5.6. Scenario E — IdP outage kéo dài hơn access token lifetime

Mục tiêu: xác định thời điểm traffic JWT bắt đầu thất bại tự nhiên.

1. Nạp key A vào JWKS cache.
2. Tắt metadata/JWKS endpoint.
3. Gửi JWT-A liên tục cho đến khi token hết hạn.
4. Xác nhận token hết hạn bị từ chối dù signature còn hợp lệ.
5. Không kéo dài `exp`, clock skew hoặc bỏ timestamp validator.
6. Mở lại IdP và kiểm tra service phục hồi.

JWT offline verification không cho phép token sống lâu hơn `exp`. Nếu outage dài hơn token lifetime, client không lấy được token mới và request cuối cùng sẽ bị từ chối.

### 5.7. Scenario F — Restart Resource Server trong lúc IdP offline

Mục tiêu: phân biệt availability của instance đang chạy với instance mới khởi động.

1. Cho Resource Server tải key A.
2. Chặn metadata/JWKS.
3. Restart một instance.
4. Gửi JWT-A đến instance cũ và instance mới.
5. So sánh behavior.

Instance cũ có thể vẫn giữ JWKS cache trong memory; instance mới thường không có cache đó và có thể không xác minh được token nếu cần tải key khi IdP offline. Nếu cache được lưu bền vững, cần test tính toàn vẹn, freshness và lifecycle của cache đó. Không giả định restart là trong suốt.

### 5.8. Scenario G — Khôi phục sau outage

1. Khôi phục metadata/JWKS/introspection endpoint.
2. Kiểm tra DNS/TLS và health check.
3. Gửi token hợp lệ bằng key hiện hành.
4. Kiểm tra unknown `kid` có thể trigger JWKS refresh.
5. Gửi opaque token active để xác nhận introspection hoạt động.
6. Quan sát retry/circuit breaker chuyển về trạng thái bình thường.
7. Xác nhận không còn backlog hoặc thread bị giữ bởi timeout dài.

Không chỉ xác nhận endpoint IdP đã trả HTTP 200; cần xác nhận Resource Server thực sự sử dụng được dependency và phục vụ request hợp lệ.

## 6. Bảng kết quả mong đợi khi IdP offline

| Trường hợp | JWT, key đã cache | JWT, key chưa biết | Opaque, không cache | Opaque, cache active còn TTL |
| --- | --- | --- | --- | --- |
| IdP metadata offline | Có thể pass | Không có tác động nếu JWKS URI đã biết và key còn cache | Introspection vẫn phụ thuộc endpoint riêng | Phụ thuộc introspection cache |
| JWKS offline | Có thể pass đến khi cache/TTL policy yêu cầu refresh | Fail closed | Không liên quan trực tiếp | Không liên quan trực tiếp |
| Introspection offline | Không liên quan trực tiếp | Không liên quan trực tiếp | Fail closed | Có thể pass trong TTL |
| Token hết hạn | Fail | Fail | Introspection nên trả inactive | Cache entry không được cho phép vượt exp |
| Issuer sai | Fail local validator | Fail local validator | Fail nếu contract wrapper kiểm tra issuer | Cache không được bypass policy |
| Audience sai | Fail local validator | Fail local validator | Fail nếu contract yêu cầu audience validation | Cache không được bypass policy |
| Signing key bị loại bỏ | Cached key có thể còn được dùng theo cache policy | Không thể lấy key mới khi offline | Không liên quan | Không liên quan |

Các ô “có thể pass” không phải cam kết mặc định của mọi implementation. Cần xác minh cache behavior và policy thực tế của ứng dụng.

## 7. Timeout, retry và circuit breaker

Khi IdP offline, lỗi nguy hiểm về vận hành không chỉ là 401. Một HTTP call treo lâu có thể giữ servlet threads, connection pool và request slots, khiến service suy giảm dù phần xử lý JWT local vẫn hoạt động.

### 7.1. Đặt timeout hữu hạn cho remote identity calls

Tách timeout theo loại dependency:

| Dependency | Loại call | Điều cần tối ưu |
| --- | --- | --- |
| Metadata discovery | GET, thường bootstrap | Startup có giới hạn và báo lỗi rõ |
| JWKS fetch/refresh | GET, khi cần key | Không giữ request quá lâu khi key chưa có |
| Introspection | POST trên request path | Latency thấp, timeout ngắn và bounded |
| Health probe IdP | GET/HEAD hoặc probe chuyên dụng | Không tạo tải lớn, không làm liveness phụ thuộc IdP |

Connect timeout giới hạn thời gian thiết lập kết nối; read/response timeout giới hạn thời gian chờ dữ liệu. Cần xem cả DNS resolution, TLS handshake và connection pool acquisition vì chúng cũng có thể làm request chậm.

Ví dụ chính sách minh họa:

~~~text
connect timeout: 500 ms
response timeout: 1.5 s
max attempts: 1 hoặc 2 cho transient failure
overall protected request budget: 2 s
~~~

Đây không phải giá trị mặc định cho mọi hệ thống. Chọn theo latency budget và SLA. Không đặt timeout của introspection dài hơn thời gian client/load balancer chờ response.

### 7.2. Retry chỉ cho lỗi transient

Retry có thể hữu ích cho một GET JWKS bị reset kết nối hoặc trả 503 tạm thời. Tuy nhiên, retry không sửa được:

- `invalid_token` hoặc token inactive.
- `invalid_client` do credential sai.
- `invalid_scope`/policy denial.
- Audience/issuer mismatch.
- Key không tồn tại trên JWKS.

Không retry vô hạn và không retry đồng bộ nhiều lần trên mỗi request. Nếu 1.000 request đồng thời cùng cần key mới, retry không có jitter có thể tạo một đợt traffic dồn vào IdP khi nó vừa hồi phục.

### 7.3. Single-flight cho JWKS refresh

Khi nhiều request đồng thời gặp `kid` chưa biết, decoder/cache nên tránh để mọi request cùng tải JWKS. Kiểm tra thư viện và cache implementation có coalesce refresh hay không. Nếu không, cân nhắc một lớp refresh có single-flight hoặc rate limit.

Không dùng một public key khác làm fallback chỉ để giảm refresh. Nếu key mới chưa được tải, token cần key đó chưa thể xác minh.

### 7.4. Circuit breaker cho introspection

Circuit breaker có thể ngừng gọi một introspection endpoint đang lỗi liên tục, giúp bảo vệ thread/connection pool và giảm tải cho IdP khi hồi phục. Khi circuit open:

- Không có cache entry hợp lệ: từ chối protected request.
- Có cache active còn TTL: chỉ dùng theo policy cache đã công bố.
- Cache entry hết TTL: không biến kết quả cũ thành active.
- Circuit half-open: cho một lượng probe nhỏ kiểm tra phục hồi.

Circuit breaker không phải cơ chế chấp nhận mọi token trong outage. Nó chỉ kiểm soát cách dependency được gọi và cách lỗi được trả về.

### 7.5. Circuit breaker cho JWKS

JWKS fetch thường ít xảy ra hơn introspection. Có thể dùng timeout, bounded retry và cache; circuit breaker có thể hữu ích khi unknown kid hoặc cache refresh tạo nhiều request lỗi. Tuy nhiên, khi key cần thiết chưa được tải, không có fallback hợp lệ để xác minh signature.

Không mở circuit breaker theo cách khiến decoder chấp nhận token với key không rõ nguồn gốc. Hành vi đúng là fail closed cho token cần key chưa có.

### 7.6. Backoff và jitter

Nếu có retry cho metadata/JWKS/introspection transient errors:

- Dùng exponential backoff với giới hạn tối đa.
- Thêm jitter để các instance không retry cùng thời điểm.
- Giới hạn tổng thời gian retry trong request/startup budget.
- Không retry lỗi 4xx mang tính policy/credential.
- Có metric cho retry count và circuit state.

Khi IdP hồi phục, tránh để toàn bộ instances cùng refresh JWKS hoặc health-check dồn dập.

## 8. Readiness, liveness và trạng thái degraded

Một trong những quyết định vận hành quan trọng là IdP outage có nên làm instance bị loại khỏi load balancer hay không.

### 8.1. Liveness không nên phụ thuộc trực tiếp vào IdP

Liveness trả lời: **process có còn sống và có thể tự tiến triển không?** Nếu IdP offline nhưng JVM, servlet container và application threads vẫn khỏe, liveness thường nên tiếp tục pass.

Nếu liveness gọi IdP và fail khi IdP outage, orchestrator có thể restart tất cả instances liên tục. Điều này làm mất cache JWKS đang còn hữu ích, tăng áp lực startup và khiến recovery khó hơn.

### 8.2. Readiness phụ thuộc khả năng phục vụ theo contract

Readiness trả lời: **instance có nên nhận traffic mới không?** Không có một đáp án chung cho mọi loại token:

- JWT Resource Server đã có key cache có thể tiếp tục phục vụ request hợp lệ dù JWKS endpoint offline.
- JWT Resource Server mới khởi động, chưa có key và không tải được JWKS có thể chưa xác minh được protected traffic.
- Opaque Resource Server không cache và introspection offline có thể không phục vụ được protected traffic.
- Endpoint public/health có thể vẫn hoạt động trong khi protected endpoint degraded.

Có thể dùng một trạng thái dependency riêng hoặc health group để quan sát IdP. Nếu readiness chuyển sang DOWN, cân nhắc tác động load balancer: loại hết instance có thể làm toàn hệ thống không còn phục vụ endpoint public và request JWT vẫn có thể xác minh local.

### 8.3. Không để readiness tạo restart loop

Phân biệt:

- **Liveness:** process có khỏe không; không phụ thuộc IdP.
- **Readiness:** instance có thể nhận loại traffic nào; policy cần phản ánh behavior thực.
- **Dependency health:** metadata/JWKS/introspection có đang truy cập được không.
- **Functional probe:** token test hoặc request nội bộ có thể xác minh theo đúng policy không.

Không dùng một health check duy nhất để biểu diễn tất cả. Nếu cần đánh dấu degraded, hãy expose thông tin rõ và quyết định route traffic theo khả năng thật, không restart process chỉ vì dependency ngoài ứng dụng tạm thời lỗi.

### 8.4. Probe không nên gây token traffic thật

Health check không nên tạo access token production mới hoặc gọi introspection liên tục bằng token người dùng. Dùng endpoint health riêng, probe có rate limit, hoặc metrics từ các request thực tế. Nếu probe kiểm tra JWKS, cần tính đến cache và tải lên IdP.

## 9. Xác định dependency nào còn cần thiết

Sau diễn tập, lập bảng kết quả dựa trên quan sát. Mỗi dependency nên được gán một trong các nhóm:

1. **Bootstrap dependency:** cần để cấu hình/khởi tạo decoder hoặc application context.
2. **On-demand runtime dependency:** chỉ cần khi cache miss, unknown key hoặc refresh.
3. **Per-request dependency:** nằm trên request path như introspection không cache.
4. **Optional/other-role dependency:** cần cho OAuth2 Client, login, UserInfo hoặc logout nhưng không cần để Resource Server xác minh token.
5. **Infrastructure dependency:** DNS, TLS, clock, network, cache/storage.

### 9.1. Ma trận dependency

| Dependency | JWT với issuer discovery | JWT với direct JWKS URI | Opaque token |
| --- | --- | --- | --- |
| OIDC/OAuth metadata | Bootstrap/discovery nếu dùng | Không cần để tìm JWKS | Không cần cho introspection nếu URI cấu hình trực tiếp |
| JWKS | Cần khi tải/refresh key | Cần khi tải/refresh key | Không dùng |
| Introspection | Không dùng trong flow JWT thuần | Không dùng trong flow JWT thuần | Cần trên request path nếu không cache |
| Token endpoint | Không cần cho validation | Không cần cho validation | Không cần cho validation |
| Authorization endpoint | Không cần cho validation | Không cần cho validation | Không cần cho validation |
| UserInfo | Chỉ nếu ứng dụng gọi để lấy profile | Chỉ nếu ứng dụng gọi để lấy profile | Chỉ nếu ứng dụng gọi riêng |
| Revocation endpoint | Không tự động được Resource Server gọi | Không tự động được Resource Server gọi | Không tự động thay cho introspection |
| Clock/NTP | Cần | Cần | Cần nếu response claims có exp hoặc policy dùng time |
| DNS/TLS/network | Cần khi remote fetch | Cần khi remote fetch | Cần cho introspection |

### 9.2. Cách xác định dependency thật bằng quan sát

Không dựa vào tên property hoặc tài liệu chung. Dùng một lần diễn tập để ghi nhận:

- Outbound HTTP requests theo host/path/method.
- Thời điểm request xảy ra: startup, first token, refresh hay mọi request.
- Cache hit/miss và TTL còn lại.
- Request latency và error class.
- Số lượng connection/thread đang chờ dependency.
- Behavior khi dependency offline và khi dependency hồi phục.

Có thể instrument HTTP client, MockWebServer/WireMock request recorder hoặc tracing span. Không ghi access token, client secret hoặc Authorization header vào trace.

### 9.3. Câu hỏi quyết định dependency còn cần thiết

Với từng endpoint, hỏi:

- Nếu endpoint offline khi process khởi động, application context có lên không?
- Nếu endpoint offline sau khi key đã cache, request JWT hợp lệ có còn chạy không?
- Nếu cache hết TTL hoặc key mới xuất hiện, service xử lý thế nào?
- Endpoint có được gọi trên mọi request hay chỉ khi cache miss?
- Endpoint đó phục vụ Resource Server hay một vai trò khác của ứng dụng?
- Có thể cấu hình URI trực tiếp mà vẫn giữ issuer validation không?
- Có yêu cầu revocation tức thời khiến cache/stale use không được phép không?

Kết quả phải được ghi thành dependency map, ví dụ:

~~~text
JWT validation:
  metadata: bootstrap only (or not used with direct JWKS URI)
  JWKS: on cache miss / refresh
  issuer/audience/time: local validation
  token endpoint: not required

Opaque validation:
  introspection: per request unless bounded cache is enabled
  token endpoint: not required for validation
  metadata: not required when introspection URI is configured directly
~~~

## 10. Metrics và logging cho outage drill

Một diễn tập chỉ hữu ích nếu có thể phân biệt authentication failure với dependency failure. HTTP 401 đơn lẻ không đủ để biết token sai hay IdP không truy cập được.

### 10.1. Metrics cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| `resource_server_authentication_success_total` | Số lần authentication thành công |
| `resource_server_authentication_failure_total` | Số lần authentication thất bại, phân loại theo error type |
| `jwks_fetch_total` | Số lần tải/refresh JWK Set |
| `jwks_fetch_duration` | Thời gian fetch JWKS |
| `jwks_cache_hit_total` / `jwks_cache_miss_total` | Hiệu quả cache key |
| `jwks_unknown_kid_total` | Token đến với key ID chưa biết |
| `introspection_request_total` | Số request introspection |
| `introspection_duration` | Latency introspection |
| `introspection_failure_total` | Lỗi transport/protocol/client auth |
| `introspection_inactive_total` | AS xác nhận token inactive |
| `introspection_cache_hit_total` | Cache hit nếu ứng dụng có introspection cache |
| `identity_dependency_circuit_state` | Trạng thái circuit breaker |
| `identity_dependency_timeout_total` | Số timeout theo dependency |

Tên metric trên là tên gợi ý cho instrumentation của ứng dụng; không phải tất cả đều là metric mặc định Spring Security cung cấp. Có thể phát metric bằng Micrometer interceptor, observation convention hoặc wrapper quanh decoder/introspector.

### 10.2. Phân loại error

Nên phân biệt ít nhất:

- Invalid signature hoặc không tìm được key.
- Issuer/audience/time/token-profile validation failure.
- Opaque token inactive.
- Introspection endpoint timeout/5xx.
- JWKS/metadata fetch timeout/5xx.
- Client authentication failure tới introspection endpoint.
- Local authorization denial do thiếu scope/role.

Không đưa token value, subject nhạy cảm, client secret hoặc Authorization header vào metric tag. Tag phải có cardinality thấp; không gắn token, user ID hoặc request ID làm label.

### 10.3. Logging và tracing

Log có thể ghi dependency name và endpoint path đã cấu hình, HTTP status/error category, elapsed time và retry count, cache hit/miss, decoder/introspector state, correlation ID hoặc trace ID.

Không log raw JWT/opaque token, Authorization header, introspection request body chứa token, client secret, private key hoặc Basic Authorization value.

Khi trace outbound identity request, redact header/body ở instrumentation layer. Test outage không được tạo log chứa token fixture thật.

## 11. Runbook khi nhà phát hành ngừng hoạt động

Runbook nên đưa operator từ triệu chứng đến hành động có thể kiểm chứng. Trình tự gợi ý:

### Bước 1 — Xác định dependency đang lỗi

Kiểm tra metadata, JWKS và introspection riêng biệt. Xác định endpoint nào timeout/5xx/connection refused và thời điểm bắt đầu.

### Bước 2 — Xác định loại token và đường xác minh

- JWT: Resource Server có cached key cho `kid` hiện tại không?
- Opaque: introspection có đang được gọi trên mỗi request không? Có cache không?
- Có ứng dụng nào vừa là Resource Server vừa là OAuth2 Client và đang phụ thuộc token endpoint cho outbound call riêng không?

### Bước 3 — Kiểm tra token còn hợp lệ không

Xác nhận signature, issuer, audience, `exp`, `nbf`, scope và key trust. Không mở rộng clock skew hoặc thay đổi validator trong lúc outage để làm request pass.

### Bước 4 — Đánh giá phạm vi ảnh hưởng

Phân biệt instance cũ đã tải JWKS và instance mới chưa tải key; JWT key đã cache và JWT có `kid` mới; opaque token có cache active còn TTL và token không có cache; endpoint public không cần authentication và protected endpoint; Resource Server validation với OAuth2 Client outbound flows.

### Bước 5 — Bảo vệ service

- Giữ timeout hữu hạn.
- Giới hạn retry và bật circuit breaker theo policy.
- Không restart toàn bộ instance chỉ vì IdP outage.
- Không bỏ authentication/authorization.
- Giữ cache trong lifecycle đã thiết kế; không xóa cache key đang hữu ích nếu chưa có lý do.

### Bước 6 — Phục hồi dependency

Khôi phục DNS/network/TLS hoặc IdP endpoint. Kiểm tra metadata/JWKS/introspection trả đúng contract. Gửi một token test hợp lệ và xác nhận Resource Server phục hồi.

### Bước 7 — Xác nhận hệ thống ổn định

Theo dõi error rate, latency, JWKS refresh, introspection calls, circuit state và thread/connection pool. Đảm bảo retry storm không xuất hiện sau khi IdP hồi phục.

## 12. Phạm vi và giới hạn của degraded mode

Degraded mode phải được định nghĩa trước. Không nên quyết định tại thời điểm outage bằng một fallback chung.

### 12.1. JWT với key đã cache

Degraded mode có thể tiếp tục xác minh token bằng key đã tin cậy, nhưng vẫn phải:

- Xác minh signature.
- Kiểm tra issuer/audience/time.
- Kiểm tra scope/role và business authorization.
- Từ chối token cần key chưa có.
- Từ chối token hết hạn.

Nếu hệ thống cần revocation gần thời gian thực, JWT local validation có thể không đáp ứng yêu cầu đó nếu không có denylist/introspection bổ sung. Đây là quyết định kiến trúc cần đưa vào threat model.

### 12.2. Opaque token với cache

Nếu cache introspection được phép:

- TTL phải bounded và ngắn theo yêu cầu revocation.
- Không sử dụng entry hết TTL trong outage.
- Cache key phải không làm lộ token.
- Inactive response phải được xử lý nhất quán.
- Có cách invalidation khi nhận thông tin revocation nếu hệ thống hỗ trợ.

Nếu không có cache hợp lệ, introspection outage làm protected request thất bại. Không tạo fallback authenticated principal từ token string.

### 12.3. Không fallback từ delegated identity sang service identity

Một ứng dụng vừa là Resource Server vừa là OAuth2 Client có thể gọi downstream bằng Client Credentials. Nhưng nếu inbound user token không xác minh được, không tự chuyển sang service token để thực hiện thao tác thay user.

Service token đại diện ứng dụng, không đại diện người dùng. Dùng nó để hoàn tất hành động của user trong outage có thể vượt qua authorization boundary và tạo confused-deputy behavior.

### 12.4. Không hạ chuẩn bảo mật để giữ availability

Các fallback không được phép:

- Bỏ signature validation.
- Chấp nhận issuer/audience bất kỳ.
- Chấp nhận JWT có `kid` không tìm thấy.
- Bỏ timestamp validation.
- Coi introspection timeout là `active=true`.
- Dùng token hết hạn vì IdP không cấp token mới.
- Nâng scope/role hoặc chuyển sang service token rộng quyền.
- Dùng metadata/JWKS URL do caller cung cấp.

## 13. Tiêu chí thành công của outage drill

Một diễn tập được coi là hoàn tất khi có bằng chứng cho từng câu hỏi:

| Câu hỏi | Bằng chứng |
| --- | --- |
| Metadata có phải startup dependency không? | Startup trace/log và outbound request record khi metadata offline |
| JWT key đã cache có hoạt động khi JWKS offline không? | JWT hợp lệ pass, expired/wrong-audience vẫn fail, JWKS call count |
| JWT key mới xử lý ra sao khi JWKS offline? | Token unknown `kid` bị từ chối; sau khi JWKS phục hồi token hợp lệ được chấp nhận |
| Opaque token xử lý ra sao khi introspection offline? | Active/inactive fixture, cache hit/miss và response code |
| Restart ảnh hưởng cache thế nào? | So sánh instance cũ/mới trong cùng outage |
| Timeout có bảo vệ thread/connection pool không? | Latency, active threads, pending connections và timeout metrics |
| Readiness/liveness có phản ứng đúng không? | Probe result và hành vi orchestrator/load balancer |
| Recovery có tránh retry storm không? | Retry rate, circuit state, JWKS/introspection request volume |
| Dependency nào thật sự cần thiết? | Dependency map theo bootstrap/on-demand/per-request/optional |

Không ghi “outage drill passed” nếu chỉ có một request trả 200. Cần test cả token hợp lệ, token không hợp lệ, token hết hạn, key mới và introspection failure.

## 14. Tình huống thực hành

**A.** Metadata endpoint offline nhưng JWT-A đã được xác minh trước đó và public key còn trong cache. Có thể tiếp tục xử lý request không?

Có thể, nếu decoder vẫn có key tin cậy, token chưa hết hạn và mọi validator vẫn chạy. Metadata không cần được gọi lại cho từng JWT.

**B.** JWKS offline và JWT-B mang `kid` chưa từng được tải. Có thể thử verify bằng key A không?

Không. Key A không xác minh chữ ký của token B trừ khi token thực sự được ký bằng private key tương ứng. Không tìm được key tin cậy thì fail closed.

**C.** Opaque token introspection timeout. Có thể giả định token vẫn active vì request trước thành công không?

Chỉ khi một cache introspection được thiết kế rõ cho phép sử dụng kết quả active còn TTL. Không có cache hợp lệ thì phải từ chối.

**D.** Ứng dụng khởi động lại trong outage và mất JWKS memory cache. Vì sao instance mới fail trong khi instance cũ vẫn pass?

Instance cũ giữ public key đã tải; instance mới cần fetch key nhưng JWKS endpoint offline. Đây là khác biệt lifecycle/cache, không phải lỗi validator.

**E.** Token còn hạn nhưng key bị xóa khỏi JWKS. Resource Server đã cache key cũ có cần từ chối ngay không?

Phụ thuộc cache refresh/rotation policy và yêu cầu revocation. JWKS rotation thông thường cần overlap window; nếu cần thu hồi key khẩn cấp, phải có policy và cơ chế phân phối thay đổi phù hợp. Không giả định mọi instance nhận cập nhật đồng thời.

**F.** Liveness probe gọi metadata endpoint và fail khi IdP down, khiến orchestrator restart tất cả instances. Có nên giữ cách này?

Không nên. Liveness thường kiểm tra process nội bộ. Dependency health nên được quan sát riêng; restart loop có thể xóa cache key đang còn hữu ích và làm outage nặng hơn.

**G.** Circuit breaker mở cho introspection. Có nên trả 200 để giữ availability?

Không. Nếu không có cache active còn TTL theo policy, protected request không thể được authenticate. Circuit breaker chỉ ngăn gọi dependency liên tục.

**H.** IdP đã hồi phục nhưng traffic vẫn fail do circuit breaker. Cần kiểm tra gì?

Kiểm tra half-open probe, reset/transition policy, DNS/TLS, client authentication và response contract. Xác nhận circuit đóng lại sau khi dependency phục hồi.

**I.** Resource Server JWT có cần token endpoint hoạt động để xác minh access token không?

Không. Token endpoint cấp token cho client. JWT Resource Server xác minh bằng public key và claims; JWKS/metadata có thể là dependency riêng.

**J.** Có thể dùng service Client Credentials token để hoàn thành request của user khi inbound token không xác minh được không?

Không. Service token mang danh tính ứng dụng, không phải user delegation. Không được dùng nó để vượt qua authorization của người dùng.

## 15. Checklist vận hành

### Trước diễn tập

- [ ] Chốt scope, môi trường, thời gian và người điều phối.
- [ ] Có rollback/abort condition và cách khôi phục dependency.
- [ ] Dùng token, key và tài khoản test riêng.
- [ ] Ghi lại token lifetime, issuer, audience, JWKS/introspection URI.
- [ ] Ghi lại cache, timeout, retry, circuit breaker và probe policy.
- [ ] Baseline metrics/traces đã sẵn sàng.

### Trong diễn tập

- [ ] Chặn từng dependency riêng biệt: metadata, JWKS, introspection.
- [ ] Kiểm tra startup và first authenticated request.
- [ ] Kiểm tra JWT cached key, unknown `kid`, expired và wrong audience.
- [ ] Kiểm tra opaque active/inactive và introspection timeout.
- [ ] Kiểm tra restart instance trong outage.
- [ ] Theo dõi liveness/readiness, threads, connections, latency và error rate.
- [ ] Không bỏ validator hoặc bật fallback không an toàn.

### Sau diễn tập

- [ ] Khôi phục IdP và xác nhận Resource Server phục hồi.
- [ ] Xác nhận không có retry storm hoặc backlog.
- [ ] Lập dependency map theo bootstrap/on-demand/per-request/optional.
- [ ] Ghi rõ degraded-mode behavior và stale/cache window.
- [ ] Ghi lại điểm cần thay đổi cấu hình, alert, runbook hoặc architecture.
- [ ] Chạy lại scenario sau khi thay đổi để xác nhận kết quả.

---

## Kết luận

Diễn tập nhà phát hành ngừng hoạt động giúp xác định Resource Server phụ thuộc vào metadata, JWKS và introspection ở thời điểm nào. Với JWT, issuer/audience/time validation là local checks; public key đã cache có thể giúp service tiếp tục xác minh token khi metadata/JWKS endpoint tạm thời offline. Token có `kid` mới hoặc instance chưa có key vẫn cần JWKS. Với opaque token, introspection thường nằm trên request path; khi endpoint offline, protected request cần fail closed trừ khi có cache active được giới hạn TTL và chấp nhận rõ revocation delay.

Để vận hành an toàn, cần timeout hữu hạn, retry có backoff/jitter, circuit breaker không bypass authentication, liveness độc lập với IdP và readiness phản ánh đúng khả năng phục vụ. Sau diễn tập, phân loại mỗi endpoint thành bootstrap, on-demand runtime, per-request, optional theo vai trò khác hoặc infrastructure dependency. Bằng chứng từ request traces, cache metrics, startup behavior và restart test sẽ cho biết dependency nào còn cần thiết và degraded mode nào có thể chấp nhận.

## Tài liệu tham khảo

1. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
2. [Spring Security — Minimal Dependencies for JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html#oauth2resourceserver-jwt-minimaldependencies)
3. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
4. [Spring Boot — Actuator Endpoints and Health Groups](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
5. [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html)
6. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html)
7. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
8. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html)
9. [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
