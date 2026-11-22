# Thu hồi access token, refresh token và authorization liên quan

## 1. Bối cảnh và mục tiêu

Trong chương **Revocation** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta tìm hiểu cách thu hồi quyền sử dụng **Access Token**, **Refresh Token** và trạng thái **OAuth2Authorization** liên quan. Kiến thức này nằm trong mục tiêu lớn hơn: **thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot**.

Giả sử người dùng Alice đăng nhập ứng dụng Portal, được cấp Access Token để gọi Orders API và Refresh Token để gia hạn phiên. Sau đó, Alice nhấn “Đăng xuất khỏi thiết bị này” hoặc phát hiện thiết bị đã mất. Hệ thống cần trả lời chính xác:

1. Access Token hiện tại còn được Orders API chấp nhận không?
2. Refresh Token có còn đổi được Access Token mới không?
3. Nếu một authorization đang chứa cả hai token, thu hồi một token có làm mất hiệu lực token còn lại không?
4. Nếu Access Token là JWT và API chỉ xác minh chữ ký offline, làm sao thực hiện thu hồi gần thời gian thực?
5. Thu hồi một phiên của Alice khác gì “đăng xuất khỏi tất cả thiết bị”?

**Mục tiêu của bài học:** hiểu RFC 7009, cấu trúc lưu trữ của Spring Authorization Server, thiết kế **phạm vi thu hồi** và **cascade policy** theo nghiệp vụ, phân biệt thu hồi tại Authorization Server với enforcement ở Resource Server, đồng thời kiểm thử các tình huống lỗi và race condition.

### 1.1. Ba khái niệm dễ nhầm

| Khái niệm | Hành động | Tác dụng chính |
| --- | --- | --- |
| **Expiration** | Token đến thời điểm hết hạn | Token không còn hợp lệ do `exp` hoặc TTL |
| **Revocation** | Chủ thể có quyền chủ động làm token mất hiệu lực | Chặn token tiếp tục được dùng, theo mức độ Resource Server quan sát được |
| **Logout / Session termination** | Kết thúc phiên ứng dụng/browser hoặc OIDC session | Không nhất thiết tự thu hồi toàn bộ OAuth2 tokens đã phát hành |

Thu hồi token không thay thế việc xác thực, quản lý session, phân quyền tại API, xóa credential khỏi thiết bị hoặc phát hiện tài khoản bị xâm nhập. Các lớp này phải phối hợp nhưng có vòng đời khác nhau.

## 2. RFC 7009 — OAuth 2.0 Token Revocation

**RFC 7009** chuẩn hóa cách một OAuth client yêu cầu Authorization Server hủy hiệu lực token. Với Spring Authorization Server, Token Revocation Endpoint mặc định thường là:

~~~text
POST /oauth2/revoke
~~~

Request dùng `application/x-www-form-urlencoded`, chứa tham số bắt buộc **token** và có thể có **token_type_hint**. Confidential client phải được xác thực theo client authentication method đã đăng ký; public client vẫn phải tuân thủ những giới hạn và chính sách nhận diện client được triển khai.

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<issued-refresh-token>&token_type_hint=refresh_token
~~~

| Tham số | Bắt buộc? | Mục đích |
| --- | --- | --- |
| `token` | Có | Chuỗi token muốn thu hồi; xem như credential nhạy cảm |
| `token_type_hint` | Không | Gợi ý loại token, thông dụng là `access_token` hoặc `refresh_token` |
| Client authentication | Tùy loại client/phương thức đã đăng ký, phải theo chính sách | Chứng minh client nào đang yêu cầu thu hồi |

**token_type_hint chỉ là gợi ý tối ưu việc tra cứu**, không phải bằng chứng token thuộc loại đó và không phải lệnh để bỏ qua token type khác. Server vẫn xác minh token thực tế, client association và policy. Không dùng một hint bất kỳ làm cách vượt qua kiểm tra quyền.

### 2.1. Phản hồi thành công và tính không tiết lộ

RFC 7009 quy định server phản hồi **HTTP 200** khi yêu cầu thu hồi hợp lệ đã được xử lý, kể cả trường hợp token không tồn tại hoặc đã hết hiệu lực:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

Phản hồi thành công thường không cần JSON body. Điều này tránh biến endpoint thành “công cụ dò xem token có thật hay không”.

**Đừng suy luận rằng HTTP 200 có nghĩa mọi Resource Server đã dừng chấp nhận token tức thì.** Nó xác nhận request được xử lý ở Authorization Server. Nếu API chỉ kiểm tra JWT offline hoặc cache introspection quá lâu, token có thể tiếp tục được chấp nhận cho đến khi cache hết hạn hay token hết `exp`.

### 2.2. Lỗi và hành vi không nên lộ thông tin

Những trường hợp có thể trả lỗi gồm request thiếu `token`, client authentication thất bại hoặc loại token không được hỗ trợ. RFC 7009 định nghĩa thêm lỗi **unsupported_token_type** khi Authorization Server không hỗ trợ thu hồi loại token được yêu cầu; các lỗi OAuth2 khác tuân theo ngữ nghĩa của giao thức.

**Không trả 404 hoặc thông điệp “token của người dùng A tồn tại”** chỉ để phân biệt token lạ với token thật. Với token không thuộc client đang gửi, server phải từ chối hoặc xử lý không tiết lộ theo chính sách, không cung cấp thông tin có thể dùng để dò token.

### 2.3. RFC 7009 nói gì về token liên quan?

RFC 7009 cho phép một request thu hồi có hiệu lực tới **token liên quan dựa trên cùng authorization grant**. Khi một **Refresh Token** bị thu hồi, Authorization Server **SHOULD** thu hồi các Access Token dựa trên cùng authorization grant nếu server có khả năng thu hồi Access Token. Khi một **Access Token** bị thu hồi, server **MAY** thu hồi Refresh Token tương ứng.

Đó là ngữ nghĩa ở cấp giao thức; **không được giả định rằng implementation mặc định của mỗi phiên bản Spring Authorization Server luôn thực hiện cùng một cascade policy**. Hãy xác minh hành vi provider đang dùng và chủ động xây chính sách nếu nghiệp vụ cần thu hồi đồng bộ toàn bộ phiên/authorization.

## 3. Luồng thu hồi trong hệ thống

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant C as Portal / OAuth Client
    participant AS as Authorization Server
    participant DB as OAuth2AuthorizationService
    participant RS as Orders Resource Server
    U->>C: Chọn đăng xuất thiết bị
    C->>AS: POST /oauth2/revoke, refresh_token
    AS->>AS: Xác thực client; kiểm tra token ownership
    AS->>DB: Tìm và cập nhật authorization/token status
    DB-->>AS: Đã lưu trạng thái thu hồi
    AS-->>C: HTTP 200
    C->>C: Xóa token khỏi storage, kết thúc local session
    C->>RS: Request bằng Access Token cũ (nếu có)
    alt RS introspection hoặc denylist đã nhận revocation
        RS-->>C: 401 invalid_token
    else RS chỉ xác minh JWT offline
        RS-->>C: Có thể tiếp tục chấp nhận đến exp
    end
~~~

Sơ đồ cố ý tách bước **cập nhật trạng thái ở Authorization Server** khỏi bước **Resource Server thực sự từ chối**. Hai việc không đồng nhất nếu hệ thống dùng self-contained JWT mà không kiểm tra revocation state.

### 3.1. Thu hồi không phải một giao dịch HTTP đồng bộ với mọi API

Authorization Server có thể lưu `invalidated=true` vào cơ sở dữ liệu, nhưng các Resource Server khác không tự biết sự thay đổi đó. Muốn đạt thời gian thu hồi rõ ràng, cần thiết kế một trong các lựa chọn: introspection, denylist, event propagation, online authorization decision hoặc giới hạn thời hạn JWT ngắn.

Không dùng câu “token đã bị thu hồi tức thì trên toàn hệ thống” khi chưa chứng minh được thời gian lan truyền và hành vi caching.

## 4. Mô hình OAuth2Authorization trong Spring Authorization Server

Spring Authorization Server lưu trạng thái authorization trong **OAuth2AuthorizationService**. Một record **OAuth2Authorization** đại diện cho một authorization/grant và có thể chứa những token hoặc metadata liên quan.

Các thành phần thường gặp:

- **id:** định danh nội bộ của authorization.
- **registeredClientId:** ID nội bộ của RegisteredClient; **khác** với client_id công khai.
- **principalName:** chủ thể được gắn với authorization.
- **authorizationGrantType:** grant tạo authorization, ví dụ authorization_code hoặc client_credentials.
- **authorizedScopes:** các quyền đã được chấp thuận.
- **attributes:** metadata dùng trong flow.
- **tokens:** Authorization Code, Access Token, Refresh Token, OIDC ID Token hoặc token của grant khác, tùy tình huống.

| Thành phần | Vai trò | Lưu ý khi thu hồi |
| --- | --- | --- |
| `OAuth2AuthorizationService` | Tìm, lưu, xóa authorization | Là nơi thay đổi trạng thái hiệu lực |
| `OAuth2Authorization` | Lưu một grant/authorization và token của grant đó | Không đồng nghĩa toàn bộ phiên đăng nhập của user |
| `OAuth2Authorization.Token` | Bao token + metadata, có thể theo dõi trạng thái invalidated | `isActive()` chịu ảnh hưởng expired/invalidated |
| `OAuth2AuthorizationService.findByToken(...)` | Tìm authorization theo giá trị token | Cần phân biệt token đã bị invalidated với token không tìm thấy |
| `OAuth2AuthorizationService.save(...)` | Lưu authorization đã cập nhật | Phải quan tâm consistency khi nhiều node |
| `OAuth2AuthorizationService.remove(...)` | Xóa authorization | Có thể chấm dứt mọi token lưu trong record theo lookup/introspection |
| `OAuth2AuthorizationConsentService` | Quản lý consent user–client | Không phải token store; thu hồi token không tự xóa consent |

### 4.1. Trạng thái token không chỉ có còn hạn/hết hạn

Một token có thể có giá trị thời gian còn hợp lệ nhưng đã bị đánh dấu **invalidated**. Khi đó `Token.isActive()` trả false mặc dù `exp` chưa đến. Ngược lại, một JWT đã hết hạn nhưng record chưa bị cleanup vẫn không được xem là active.

Khái niệm:

~~~text
Active theo OAuth2Authorization.Token:
    chưa expired
    AND chưa invalidated
    AND đáp ứng điều kiện trạng thái của token

JWT được Resource Server chấp nhận:
    chữ ký, issuer, audience, time, scope... hợp lệ
    AND revocation state nếu Resource Server kiểm tra
~~~

Hai phép kiểm tra ở các thành phần khác nhau; **không tự động đồng bộ** khi Resource Server chỉ có JWT Decoder.

### 4.2. Một authorization không phải “tất cả các thiết bị”

Người dùng Alice có thể đăng nhập Portal trên điện thoại và laptop, tạo **hai OAuth2Authorization** khác nhau. Thu hồi authorization của điện thoại không đương nhiên xóa authorization của laptop. Thu hồi toàn bộ thiết bị/tài khoản cần tìm mọi authorization liên quan bằng kho/index và policy riêng.

## 5. Pipeline Token Revocation Endpoint

Spring Authorization Server có bộ phận xử lý riêng tại Token Revocation Endpoint:

~~~mermaid
flowchart TD
    A["POST /oauth2/revoke"] --> B["OAuth2TokenRevocationEndpointFilter"]
    B --> C["Converter đọc token + token_type_hint"]
    C --> D["AuthenticationManager"]
    D --> E["OAuth2TokenRevocationAuthenticationProvider"]
    E --> F["Xác minh client đã authentication"]
    F --> G["OAuth2AuthorizationService.findByToken"]
    G --> H{"Token thuộc client hợp lệ?"}
    H -->|Không| X["OAuth2 error hoặc xử lý không lộ thông tin"]
    H -->|Có| I["Đánh dấu invalidated / cập nhật authorization"]
    I --> J["OAuth2AuthorizationService.save"]
    J --> K["HTTP 200"]
~~~

Đây là pipeline khái niệm. Converter/provider cụ thể và thứ tự kiểm tra cần đối chiếu với phiên bản Spring Authorization Server đang dùng. Filter xử lý HTTP; provider kiểm tra điều kiện OAuth2 và dùng service lưu trạng thái.

### 5.1. Endpoint mặc định và đổi đường dẫn

Mặc định, Token Revocation Endpoint sử dụng đường dẫn **/oauth2/revoke**. Trong các phiên bản Spring Authorization Server 1.x cung cấp API tương ứng, có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class RevocationEndpointSettings {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://auth.example.com")
                .tokenRevocationEndpoint("/oauth2/revoke")
                .build();
    }
}
~~~

Khi đổi endpoint, phải cập nhật metadata discovery, proxy routing và client configuration. Không tự xây một REST controller thu hồi token không dùng OAuth2 client authentication, rồi coi đó là bản thay thế an toàn cho RFC 7009.

### 5.2. Cấu hình extension point

`OAuth2AuthorizationServerConfigurer` cho phép tùy chỉnh các protocol endpoint theo API của phiên bản. Với Token Revocation Endpoint, phần tùy chỉnh thường liên quan request converter, authentication provider, success/error handler.

Không gắn các bước ảnh hưởng quyền thu hồi chỉ trong converter: converter chủ yếu xử lý cấu trúc request. **Token ownership, client binding, cascade policy, audit và quyết định revoke** thuộc provider/service có dữ liệu đã xác thực.

## 6. Phân biệt thu hồi từng loại đối tượng

| Hành động | Điều cần vô hiệu | Hiệu quả mong muốn | Những điều chưa được bảo đảm |
| --- | --- | --- | --- |
| Revoke **Access Token** | Một Access Token cụ thể | Chặn quyền truy cập API bằng token đó | Refresh Token có thể còn dùng được |
| Revoke **Refresh Token** | Một Refresh Token cụ thể | Chặn tạo Access Token mới từ refresh đó | Access Token đã cấp có thể còn được API chấp nhận |
| Revoke **cả Access + Refresh** | Cả hai token trong một authorization | Dừng quyền API và gia hạn trong phiên đó | JWT offline và cache cần phương án enforcement |
| Revoke **OAuth2Authorization** | Tất cả token/state thuộc một authorization | Chấm dứt grant theo ranh giới record | Những authorization khác của user không tự bị xóa |
| Revoke **mọi phiên user** | Tất cả authorization phù hợp + browser sessions | Đăng xuất nhiều thiết bị theo policy | Cần query/index riêng và chiến lược fan-out |
| Revoke **OAuth2AuthorizationConsent** | Consent user–client đã lưu | Có thể cần xin consent lại ở lần cấp quyền sau | Không thu hồi Access/Refresh Token đã cấp |

**Không mặc định** logout = revoke Access Token = revoke Refresh Token = delete consent. Mỗi hành động có mục tiêu và phạm vi khác nhau.

### 6.1. Access Token đơn lẻ

Thu hồi chỉ Access Token có ích khi:

- Một Access Token bị nghi lộ nhưng Refresh Token được bảo vệ riêng.
- Một downstream token được cấp cho API cần đóng ngay.
- Một chính sách muốn chặn token hiện tại nhưng cho client khởi tạo access mới thông qua flow hợp lệ.

Tuy nhiên, nếu Refresh Token vẫn active, client có thể xin một Access Token mới ngay. Để buộc đăng nhập lại, phải xem xét **thu hồi Refresh Token và/hoặc authorization**.

### 6.2. Refresh Token và nguy cơ phát lại

Thu hồi Refresh Token chặn việc cấp token mới qua chuỗi refresh đó. Nếu cùng authorization có Access Token còn hạn, cần quyết định có **cascade revoke** Access Token không. RFC 7009 khuyến nghị khi revoke Refresh Token thì cũng vô hiệu các Access Token cùng grant nếu server có khả năng.

Chính sách production dành cho logout toàn phiên hoặc nghi ngờ Refresh Token bị lộ thường chọn **thu hồi cả Refresh và Access**. Không chỉ xóa Refresh Token ở client rồi để server vẫn chấp nhận nó.

### 6.3. Toàn bộ authorization

Một OAuth2Authorization có thể chứa cả Access Token, Refresh Token và các token khác liên quan đến grant. Xóa authorization bằng `remove` hoặc đánh dấu từng token invalidated đều có thể tạo hiệu ứng không còn tìm được token qua authorization store.

Hai lựa chọn có đánh đổi:

- **Invalidate metadata và giữ record:** tiện truy vết, audit, thực thi trạng thái token, kiểm soát cleanup.
- **Remove record:** đơn giản khi chấm dứt toàn bộ authorization, nhưng mất trạng thái tại store này; phải có audit độc lập nếu cần điều tra và tránh mất thông tin sự cố.

Với Access Token JWT chỉ được API xác minh offline, cả hai lựa chọn đều **không tự cập nhật token đã ký trên máy client**. API phải có cơ chế kiểm tra trạng thái bổ sung hoặc chờ hết hạn.

## 7. Thiết kế cascade policy cho các tình huống

Chính sách không nên dựa duy nhất vào “loại token vừa được gửi” mà cần xét **sự kiện nghiệp vụ, rủi ro và phạm vi hành động đã được xác thực**.

| Sự kiện | Phạm vi thu hồi đề xuất | Lý do |
| --- | --- | --- |
| Logout một thiết bị | Access + Refresh của authorization thuộc thiết bị đó | Ngăn sử dụng và gia hạn của phiên đã chọn |
| Client chủ động thay Access Token | Một Access Token, nếu policy cho phép | Refresh Token có thể tiếp tục; không buộc đăng nhập lại |
| Người dùng phát hiện mất thiết bị | Tất cả token/authorization của thiết bị bị mất | Không để Refresh Token tiếp tục hoạt động |
| Phát hiện Refresh Token reuse | Token family/grant bị ảnh hưởng, có thể mở rộng theo risk policy | Dấu hiệu token bị đánh cắp hoặc race bất thường |
| Tài khoản bị khóa hoặc bị chiếm | Tất cả authorization của user, sessions liên quan và credential cần đổi | Chặn mọi thiết bị tiếp tục truy cập |
| Thu hồi quyền truy cập ứng dụng | Authorization liên quan tới user–client; cân nhắc xóa consent | Chặn tokens cũ và yêu cầu grant/consent mới |
| Thu hồi riêng một API downstream | Token có audience/scope đích hoặc authorization liên quan | Không làm ảnh hưởng các quyền độc lập không cần thiết |
| Client secret/certificate bị lộ | Client-wide authorizations, credentials và bound tokens tùy risk | Chứng cứ danh tính client bị xâm phạm |

Các dòng là **gợi ý thiết kế**. Cần xác định hành động nào được user tự thực hiện, hành động nào chỉ quản trị viên hoặc security service mới được phép. API thu hồi phải xác thực người gọi và không cho user chỉ định tùy tiện authorization ID của người khác.

### 7.1. Scope liên quan khác quyền được phép thu hồi

Một client đăng ký nhiều scope không có nghĩa nó được quyền thu hồi token của client khác. Token ownership và authorization association là ranh giới quan trọng. Tránh tạo API kiểu `POST /internal/revoke?clientId=...` rồi tin clientId từ request.

### 7.2. Không có thứ tự thu hồi “mặc định an toàn” cho mọi kiến trúc

Một ứng dụng muốn chấm dứt phiên cần ngăn refresh ngay, cập nhật trạng thái access, thông báo các Resource Server cần biết và xóa local credential. Các thao tác này có thể xảy ra ở các thành phần khác nhau; nên có idempotency, retry và audit để lỗi giữa chừng không để lại phiên được dùng ngoài ý muốn.

## 8. JWT, opaque token và tính hiệu lực sau khi thu hồi

Đây là điểm thường gây sai sót nhất khi triển khai revocation.

| Loại Access Token / cách xác minh | Điều xảy ra khi Authorization Server đánh dấu revoked | Thời gian Resource Server nhận biết |
| --- | --- | --- |
| Opaque Token + introspection online | `active=false` nếu trạng thái token đã bị vô hiệu | Gần thời gian thực, chịu độ trễ mạng và cache |
| JWT + API chỉ kiểm tra signature/iss/aud/exp | JWT cũ vẫn có chữ ký và thời hạn cũ | Có thể đến khi `exp`, dù DB báo invalidated |
| JWT + denylist theo `jti`/hash token | API kiểm tra token có nằm trong danh sách thu hồi | Theo tốc độ cập nhật/sync denylist |
| JWT + introspection/online authorization check | API kiểm tra trạng thái token tại AS hoặc dịch vụ chung | Gần thời gian thực nếu không cache stale |
| JWT ngắn hạn, không online state | Giảm cửa sổ token cũ còn dùng được | Tối đa gần TTL còn lại, không tức thì |

### 8.1. Vì sao thu hồi JWT không thể sửa chữ ký đã phát hành?

JWT là dữ liệu đã ký và đang nằm ở client. Spring Authorization Server có thể đánh dấu record trong `OAuth2AuthorizationService` là invalidated, nhưng không thể “sửa” token ở phía client hay thu hồi chữ ký chỉ bằng một thao tác database.

Resource Server offline thường chỉ biết:

~~~text
signature hợp lệ
AND issuer đáng tin
AND audience đúng
AND token chưa hết hạn
AND scope/authorization phù hợp
~~~

Nếu chưa có **revocation validator**, Resource Server không biết token đã bị đánh dấu invalidated trong authorization store.

### 8.2. Cấu trúc token-status enforcement

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|"Revoke / save invalidation"| DB["Authorization Store"]
    DB -->|"Introspection active=false"| RS1["Resource Server A"]
    AS -->|"Revocation event"| BUS["Event / Cache Invalidation"]
    BUS -->|"jti hoặc token hash"| RS2["Resource Server B + Denylist"]
    AS -->|"JWT ký với exp ngắn"| RS3["Resource Server C offline"]
    RS3 -->|"Chỉ biết khi exp"| END["Token hết hạn"]
~~~

Mỗi chiến lược cần một **SLO thu hồi** được đo bằng test: ví dụ revoke phải phản ánh tại các API trong một số giây/giới hạn cache xác định. Không đặt SLO khi chưa có cơ chế đáp ứng.

### 8.3. Cache introspection

Cache làm giảm latency nhưng có thể khiến `active=true` tiếp tục được dùng sau khi token bị thu hồi. Cần giới hạn TTL cache theo mức độ rủi ro, có cơ chế invalidation khi cần, không cache kết quả active lâu hơn thời hạn token và đánh giá fail-open/fail-closed khi Authorization Server tạm thời không truy cập được.

### 8.4. Denylist cho JWT

Nếu cần denylist, có thể lưu `jti` hoặc hash token (không lưu raw token) cùng expiry, issuer và audience cần thiết. Mỗi API phải kiểm tra trạng thái phù hợp, và denylist cần được chia sẻ giữa các node. Khi token hết hạn, entry có thể được dọn. Cần xử lý token thiếu `jti` theo profile và tránh false match giữa các issuer.

## 9. Refresh Token rotation, reuse và token family

### 9.1. Rotation giảm tác động khi refresh token bị đánh cắp

Với Refresh Token rotation, mỗi lần dùng Refresh Token thành công có thể nhận Refresh Token mới và Refresh Token cũ trở nên không hợp lệ. Trong Spring Authorization Server có thể cấu hình:

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
~~~

`reuseRefreshTokens(false)` giúp phát Refresh Token mới theo chính sách. Nhưng **rotation không đồng nghĩa tự động phát hiện mọi hành vi tái sử dụng Refresh Token cũ** hoặc tự revoke toàn bộ token family; cơ chế đó phụ thuộc trạng thái lịch sử được lưu và policy tùy chỉnh.

### 9.2. Phân biệt hai tình huống

**Tình huống bình thường:** client dùng Refresh Token R1, được R2; R1 không còn dùng được. Khi client gửi nhầm R1, request bị từ chối nhưng hệ thống có thể không biết đây là lỗi client hay attacker.

**Tình huống nghi ngờ lộ token:** R1 đã được đổi thành R2 nhưng lại xuất hiện từ một nguồn khác. Nếu hệ thống lưu chain/family và ràng buộc thiết bị, có thể đánh dấu reuse, thu hồi toàn bộ family và buộc xác thực lại.

Để phát hiện reuse đáng tin, cần lưu **quan hệ token family, phiên phát hành, trạng thái token cũ, thời gian và tín hiệu rủi ro**. Không giả định `OAuth2AuthorizationService.findByToken(R1, ...)` vẫn tìm được token cũ sau rotation; implementation có thể chỉ giữ token mới.

### 9.3. Race condition trong refresh

Hai node có thể đồng thời nhận R1 và đều cố đổi thành token mới. Nếu repository không hỗ trợ concurrency control phù hợp, một lần refresh có thể ghi đè trạng thái hoặc cấp nhiều token ngoài ý muốn.

Các lựa chọn:

- Dùng transaction, optimistic locking hoặc compare-and-swap cho trạng thái family.
- Bảo đảm chỉ một giao dịch consume Refresh Token được chấp nhận theo policy.
- Kiểm thử nhiều node, nhiều request đồng thời và retry khi mạng lỗi.
- Định nghĩa grace period rất thận trọng nếu nghiệp vụ cần xử lý mất response; không biến grace thành replay hợp lệ vô hạn.

**Chỉ sử dụng JDBC repository chưa tự chứng minh có tính atomicity đáp ứng chính sách chống reuse**. Cần kiểm thử với database, isolation level và phiên bản framework thực tế.

## 10. Quản lý authorization liên quan và phạm vi thu hồi

### 10.1. OAuth2Authorization ID không phải user session ID

`OAuth2Authorization.id` là khóa record của một grant. Người dùng có thể có nhiều authorization ở các client/thiết bị. `principalName` có thể đại diện user hoặc client tùy grant.

Nếu user chọn “Đăng xuất tất cả thiết bị”, ứng dụng phải tìm tất cả authorization thuộc chủ thể và tập client/thiết bị phù hợp. Interface `OAuth2AuthorizationService` mặc định hỗ trợ tìm theo ID/token, **không cung cấp sẵn một API liệt kê tất cả authorization theo principalName**. Production cần một query repository/index riêng hoặc authorization management service có kiểm soát.

### 10.2. Consent, session và ID Token là những đối tượng riêng

- `OAuth2AuthorizationConsentService` lưu consent giữa user và RegisteredClient; revoke token không mặc nhiên xóa consent.
- HTTP session / Spring Security Session của browser không tự bị xóa khi `OAuth2AuthorizationService` cập nhật token.
- OIDC ID Token có mục đích chứng thực người dùng cho OIDC Client; revoke Access Token không phải OIDC logout protocol.
- OIDC RP-Initiated Logout, Front-Channel/Back-Channel Logout và session management là các cơ chế khác, cần thiết kế tách biệt.

### 10.3. Nguyên tắc giới hạn phạm vi

| Mục tiêu | Điều kiện nhận dạng |
| --- | --- |
| Thu hồi một token | Token cụ thể + client đã xác thực, token ownership |
| Thu hồi một authorization | Authorization ID + chủ thể/tenant/client đã xác minh |
| Thu hồi một thiết bị | Device/session binding do server quản lý |
| Thu hồi toàn bộ user | User identity đáng tin + query trên các authorization liên quan |
| Thu hồi toàn bộ client bị xâm phạm | RegisteredClient internal ID + policy quản trị |

Không nhận `authorizationId`, `principalName` hoặc `clientId` từ request rồi coi những giá trị đó là bằng chứng người gọi có quyền thu hồi. Cần guard RBAC, tenant isolation, audit và cơ chế chống enumeration.

## 11. Ví dụ Java: Thu hồi đúng phạm vi authorization

Để thu hồi **cả Access Token và Refresh Token** hoặc toàn bộ authorization theo một hành động đã xác thực, ta có thể dùng `OAuth2AuthorizationService` trực tiếp từ một service nghiệp vụ đáng tin. Đoạn mã sau minh họa:

- Phân biệt yêu cầu thu hồi Access Token với thu hồi cả Access + Refresh.
- Có lựa chọn chấm dứt toàn bộ authorization.
- Chỉ xử lý record gắn với RegisteredClient ID và principal mà tầng bảo mật đã xác minh.
- Ghi trạng thái invalidated qua `OAuth2Authorization.Builder.invalidate(...)` thay vì tự sửa raw token.

### 11.1. Service xử lý revoke policy

~~~java
import java.util.Objects;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthorizationRevocationPolicyService {

    public enum Mode {
        ACCESS_ONLY,
        ACCESS_AND_REFRESH,
        ENTIRE_AUTHORIZATION
    }

    private final OAuth2AuthorizationService authorizationService;

    public AuthorizationRevocationPolicyService(
            OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    @Transactional
    public boolean revoke(
            String authorizationId,
            String trustedRegisteredClientId,
            String trustedPrincipalName,
            Mode mode) {

        OAuth2Authorization authorization =
                authorizationService.findById(authorizationId);

        if (authorization == null) {
            // Không để API công khai tiết lộ liệu ID có tồn tại hay không.
            return false;
        }

        // Các giá trị trusted... PHẢI được tầng gọi lấy từ ngữ cảnh
        // đã xác thực/ủy quyền, không phải dữ liệu request tùy ý.
        if (!Objects.equals(
                    authorization.getRegisteredClientId(),
                    trustedRegisteredClientId)
                || !Objects.equals(
                    authorization.getPrincipalName(),
                    trustedPrincipalName)) {
            throw new AccessDeniedException(
                    "Authorization revocation is not permitted");
        }

        if (mode == Mode.ENTIRE_AUTHORIZATION) {
            authorizationService.remove(authorization);
            return true;
        }

        OAuth2Authorization.Builder builder =
                OAuth2Authorization.from(authorization);

        if (authorization.getAccessToken() != null) {
            builder.invalidate(authorization.getAccessToken().getToken());
        }

        if (mode == Mode.ACCESS_AND_REFRESH
                && authorization.getRefreshToken() != null) {
            builder.invalidate(authorization.getRefreshToken().getToken());
        }

        authorizationService.save(builder.build());
        return true;
    }
}
~~~

**Đây là một service minh họa, không phải endpoint công khai để client chọn authorization tùy ý.** Ở production:

1. `authorizationId` phải đến từ phiên/thiết bị đã được xác minh hoặc một hệ thống quản trị được phân quyền, không được lấy mù từ form/URL.
2. `trustedRegisteredClientId` là **RegisteredClient ID nội bộ**, không phải `client_id` do người gọi tự khai.
3. `trustedPrincipalName` cần lấy từ principal đã xác thực hoặc đối tượng được quản trị viên ủy quyền; không để browser tự chọn người bị thu hồi.
4. Kiểm tra tenant/device ownership, RBAC, audit, rate limit, chống CSRF nếu lệnh được gửi từ phiên browser.
5. Chế độ `ENTIRE_AUTHORIZATION` xóa record, vì vậy cần audit độc lập nếu yêu cầu lưu lịch sử sự cố.
6. Nếu hệ thống có token type/grant khác, cần quyết định rõ có invalidate Authorization Code, Device Code hoặc những token liên quan trước khi đánh dấu toàn bộ authorization kết thúc. Xóa cả record chấm dứt lookup từ store nhưng không tự kết thúc session ở client.
7. `@Transactional` chỉ thực sự đem lại atomicity theo cấu hình transaction manager và repository thực tế; nó không bảo đảm đồng bộ với caches, Resource Server hoặc event bus.

### 11.2. Biến thể: Giữ record nhưng vô hiệu nhiều token

Nếu cần tiếp tục lưu authorization để audit, có thể đánh dấu các token hiện có là invalidated:

~~~java
OAuth2Authorization existing =
        authorizationService.findById(authorizationId);

if (existing == null) {
    // Xử lý theo chính sách not-found không tiết lộ thông tin.
    return;
}

// Bắt buộc kiểm tra ownership/tenant/RBAC trước đoạn này.
OAuth2Authorization.Builder builder =
        OAuth2Authorization.from(existing);

if (existing.getAccessToken() != null) {
    builder.invalidate(existing.getAccessToken().getToken());
}

if (existing.getRefreshToken() != null) {
    builder.invalidate(existing.getRefreshToken().getToken());
}

if (existing.getAuthorizationCode() != null) {
    builder.invalidate(existing.getAuthorizationCode().getToken());
}

authorizationService.save(builder.build());
~~~

Đây là **đoạn bên trong một service đã được bảo vệ**, không phải hàm Java đứng độc lập; `authorizationService` và `authorizationId` là biến từ service context. Việc invalidated Authorization Code có ý nghĩa nếu giao dịch cấp quyền chưa hoàn tất, nhưng không tự giải quyết mọi loại authorization khác. Với một policy kết thúc hoàn toàn, cần rà soát token/metadata đặc thù của OIDC, Device Authorization, Token Exchange và custom grants.

### 11.3. Khác biệt giữa invalidate và remove

| Cách làm | Record còn trong store? | Token status qua store | Audit |
| --- | --- | --- | --- |
| `builder.invalidate(token)` + `save` | Có | Token bị đánh dấu không active | Giữ lịch sử metadata, theo retention |
| `authorizationService.remove(auth)` | Không | Token không còn tìm được từ authorization store | Cần audit ở nơi khác |

Không thể khẳng định cách nào mạnh hơn nếu Resource Server không tra cứu store. Cần phối hợp với cơ chế xác minh ở API để việc thu hồi có tác dụng thực tế.

## 12. Gọi Revocation Endpoint bằng HTTP

Với confidential client có client secret và được đăng ký `CLIENT_SECRET_BASIC`, ví dụ:

~~~bash
curl -i --request POST \
  --url 'https://auth-test.example.com/oauth2/revoke' \
  --user 'portal-client:<test-client-secret>' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'token=<refresh-token-from-test-flow>' \
  --data-urlencode 'token_type_hint=refresh_token'
~~~

`--user` dùng HTTP Basic client authentication. Các chuỗi `<...>` là placeholder, không phải credential thật. Khi chạy test với token thật, cần tránh shell history, output debug, CI log và ticket chứa token/secret. Trong automation, dùng cơ chế inject credential phù hợp thay vì hard-code.

### 12.1. Thu hồi Access Token

~~~bash
curl -i --request POST \
  --url 'https://auth-test.example.com/oauth2/revoke' \
  --user 'portal-client:<test-client-secret>' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'token=<access-token-from-test-flow>' \
  --data-urlencode 'token_type_hint=access_token'
~~~

Nếu không gửi `token_type_hint`, server vẫn phải xử lý request theo khả năng tra cứu token của mình. Hint giúp tối ưu, không làm token hợp lệ hơn và không quyết định policy thu hồi token liên quan.

### 12.2. Thu hồi không có nghĩa client đã xóa credential

Sau HTTP 200, client cần:

- Xóa Access Token/Refresh Token khỏi storage của phiên hoặc thiết bị.
- Xóa hoặc cập nhật local OAuth2AuthorizedClient state nếu ứng dụng sử dụng Spring Security OAuth2 Client.
- Xóa cookie/session của ứng dụng khi mục tiêu là logout.
- Không tiếp tục scheduler tự động refresh bằng token vừa thu hồi.
- Hiển thị kết quả logout mà không lộ thông tin token.

Không đợi token hết hạn mới xóa local credential. Phía server chặn token và phía client ngừng sử dụng credential là hai trách nhiệm bổ sung.

### 12.3. Khi client không có Refresh Token

Không phải grant nào cũng phát Refresh Token. Với Client Credentials, thường chỉ có Access Token. Trong trường hợp này, một lệnh revoke Access Token chỉ chặn token hiện có nếu Resource Server quan sát được revocation; confidential client vẫn có thể dùng credential của chính mình để xin token khác.

Nếu client credential bị lộ, cần **vô hiệu hóa client, thu hồi/chuyển đổi secret/certificate/key và các token liên quan**, chứ không chỉ revoke một Access Token.

## 13. Tích hợp Resource Server để enforcement có hiệu lực

### 13.1. Opaque Token qua introspection

Resource Server dùng Token Introspection Endpoint theo **RFC 7662** có thể nhận:

~~~json
{
  "active": false
}
~~~

khi Access Token bị invalidated hoặc không còn active. Nếu đang sử dụng Spring Security Resource Server với opaque token, cơ chế introspection phù hợp giúp Resource Server nhìn thấy trạng thái được Authorization Server lưu.

Các điểm cần kiểm tra:

- Resource Server xác thực với Introspection Endpoint.
- Kết quả `active=false` dẫn tới request bị từ chối.
- Không cache `active=true` lâu hơn giới hạn revocation SLO.
- Nếu AS/introspection service không khả dụng, hành vi fail-open/fail-closed phải được policy quyết định; với endpoint nhạy cảm nên ưu tiên fail-closed.
- Token và introspection credential không được log.

### 13.2. JWT offline và denylist

Nếu Orders API chỉ dùng JWT decoder, có thể thêm validator kiểm tra `jti` hoặc token hash trong denylist. Sơ đồ:

~~~text
Authorization Server:
    revoke access token
    -> cập nhật authorization store
    -> xuất bản sự kiện revoke với issuer + token ID/hash + expiry

Resource Server:
    xác minh chữ ký/iss/aud/exp
    -> kiểm tra jti/hash nằm trong denylist không
    -> kiểm tra scope/authorization
    -> chấp nhận hoặc từ chối
~~~

**Chỉ truyền identifier an toàn**, không đưa raw Access Token vào message bus hoặc metrics. Sự kiện revocation cần có nhận dạng issuer để tránh nhầm token ID giữa các trust domain, cơ chế retry, deduplication và replay/delivery semantics rõ ràng. Với nhiều node, cache denylist phải nhất quán theo thời gian mong muốn.

### 13.3. Tùy chọn JWT ngắn hạn

Một kiến trúc không yêu cầu thu hồi Access Token tức thời có thể chọn JWT TTL ngắn, ví dụ vài phút, đồng thời revoke Refresh Token để ngăn gia hạn. Khi đó **cửa sổ rủi ro tối đa** phụ thuộc thời gian còn lại của JWT và các yếu tố như clock skew; không được mô tả là “thu hồi Access Token tức thì”.

TTL phải được chọn theo threat model và SLA, không chọn chỉ theo tiện lợi giảm load Token Endpoint.

### 13.4. Token binding không thay revocation

DPoP (`cnf.jkt`) và mTLS certificate-bound token (`cnf.x5t#S256`) hạn chế ai có thể sử dụng Access Token bị lộ. Nhưng nếu private key/certificate tương ứng cũng bị chiếm, attacker vẫn có thể trình token. **Sender constraint không thay revoke, denylist, introspection hoặc TTL**.

## 14. Logout, OpenID Connect và việc thu hồi quyền

Một OIDC Client có thể cần:

1. Xóa local login session.
2. Thực hiện logout tại OpenID Provider nếu chính sách yêu cầu.
3. Thu hồi Access Token/Refresh Token hoặc toàn bộ authorization.
4. Cập nhật trạng thái ở các API/thiết bị cần chấm dứt.
5. Nếu user thu hồi quyền ứng dụng, cân nhắc xóa `OAuth2AuthorizationConsent` để yêu cầu consent mới ở lần cấp quyền sau.

**Không lấy OIDC ID Token làm Access Token** để gửi cho Resource Server. Logout token của OIDC Back-Channel Logout cũng không phải Refresh Token để đưa vào RFC 7009 Revocation Endpoint.

### 14.1. Xóa consent không làm token hiện tại mất hiệu lực

`OAuth2AuthorizationConsentService.remove(consent)` xử lý bản ghi consent, không được xem là hành động thu hồi toàn bộ Access Token và Refresh Token đã cấp. Muốn chấm dứt quyền đang hoạt động, cần revoke authorization/token và bảo đảm Resource Server thực thi.

### 14.2. Logout một thiết bị so với tất cả thiết bị

| Yêu cầu | Phạm vi nên chọn |
| --- | --- |
| Logout từ laptop hiện tại | Authorization gắn với laptop/session hiện tại |
| Logout tất cả thiết bị | Toàn bộ authorization thuộc user theo tập client/tenant được phép |
| Thu hồi quyền của một ứng dụng | Authorizations liên quan user–client, cân nhắc consent |
| Khóa tài khoản vì rủi ro | Authorizations, sessions và các credential phụ thuộc theo runbook |

Để xác định **thiết bị**, kiến trúc cần lưu session/device correlation theo cách đáng tin. Không suy ra thiết bị chỉ từ `User-Agent` hoặc IP vì hai thông tin này có thể trùng và dễ thay đổi.

## 15. Kiểm thử Token Revocation Endpoint bằng MockMvc

### 15.1. Kiểm tra HTTP 200 và trạng thái token

Giả sử test fixture đã tạo:

- RegisteredClient confidential có `client_id=portal-client` và secret tương ứng.
- Authorization đã phát hành một Refresh Token.
- `OAuth2AuthorizationService` được inject và có record của authorization.

Ví dụ kiểm thử tích hợp rút gọn:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TokenRevocationIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired OAuth2AuthorizationService authorizationService;

    @Test
    void revokingRefreshTokenMakesItInactive() throws Exception {
        String authorizationId = obtainAuthorizationIdFromTestFlow();
        OAuth2Authorization before =
                authorizationService.findById(authorizationId);

        assertThat(before).isNotNull();
        assertThat(before.getRefreshToken()).isNotNull();
        String refreshToken = before.getRefreshToken().getToken().getTokenValue();

        mvc.perform(post("/oauth2/revoke")
                .with(httpBasic("portal-client", "test-client-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", refreshToken)
                .param("token_type_hint", "refresh_token"))
            .andExpect(status().isOk());

        OAuth2Authorization after =
                authorizationService.findById(authorizationId);
        assertThat(after).isNotNull();
        assertThat(after.getRefreshToken().isActive()).isFalse();
    }

    private String obtainAuthorizationIdFromTestFlow() {
        // Fixture: tạo một authorization bằng grant hợp lệ,
        // lưu ID từ OAuth2AuthorizationService.
        throw new UnsupportedOperationException("Implement test fixture");
    }
}
~~~

Mẫu này **không chạy độc lập**: cần spring-security-test, client secret đã encode trong RegisteredClient, SecurityFilterChain/Authorization Server beans và fixture thực. Nó kiểm tra trường hợp provider **giữ record nhưng đánh dấu token invalidated**. Nếu phiên bản hoặc custom policy **remove** record, cần điều chỉnh assertion theo hợp đồng thay vì khẳng định record luôn còn.

### 15.2. Phải kiểm thử hậu quả ngoài endpoint

Sau khi revoke Refresh Token, gọi tiếp:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<revoked-refresh-token>
~~~

Kỳ vọng Refresh Token Grant bị từ chối, thường là `invalid_grant`. Nếu dự án yêu cầu cascade, kiểm tra Access Token cùng authorization không còn active ở store và **Resource Server thực sự từ chối** theo revocation SLO.

## 16. Ma trận kiểm thử đầy đủ

| # | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Revoke Refresh Token hợp lệ với client đúng | HTTP 200; token không còn active |
| 2 | Revoke cùng token lần hai | HTTP 200, không tiết lộ sự tồn tại |
| 3 | Revoke token không tồn tại | HTTP 200 theo RFC 7009 nếu request/client hợp lệ |
| 4 | Không có tham số token | OAuth2 invalid_request |
| 5 | Client authentication sai | invalid_client hoặc lỗi xác thực phù hợp |
| 6 | Client A cố revoke token của client B | Không cho thu hồi trái phép; không lộ quyền sở hữu |
| 7 | token_type_hint sai so với token thật | Server xử lý đúng token theo dữ liệu thật; không dùng hint để bypass |
| 8 | Revoke Access Token đơn lẻ | Access Token bị invalidated; policy về Refresh Token được kiểm tra |
| 9 | Revoke Refresh Token có Access Token cùng authorization | Kiểm tra cascade theo policy đã công bố |
| 10 | Revoke toàn bộ authorization | Mọi token thuộc record bị chặn qua authorization store |
| 11 | Hai authorization của cùng user, revoke một | Authorization còn lại không bị ảnh hưởng nếu policy chỉ một thiết bị |
| 12 | Logout tất cả thiết bị | Tất cả authorization nằm trong phạm vi người dùng được thu hồi |
| 13 | Opaque token sau revoke, introspection | active=false |
| 14 | JWT offline sau revoke | Chứng minh giới hạn: API có thể nhận đến exp nếu không có revocation check |
| 15 | JWT có denylist | Resource Server từ chối trong SLO cam kết |
| 16 | Cache introspection còn dữ liệu active=true | Kiểm tra TTL/invalidation và tình huống stale |
| 17 | Refresh rotation, dùng lại token cũ | Từ chối; policy family reuse detection được kiểm tra riêng |
| 18 | Hai lần refresh đồng thời trên nhiều node | Không cấp token trái chính sách concurrency |
| 19 | AS restart ngay sau revoke | Trạng thái thu hồi vẫn có hiệu lực với storage bền vững |
| 20 | AS/storage/introspection tạm thời lỗi | Không fail-open với API có yêu cầu bảo mật cao |
| 21 | Revoke token bound DPoP/mTLS | State revocation và key binding đều được kiểm tra |
| 22 | Logout browser nhưng không revoke token | Test phát hiện token còn hoạt động, nếu policy yêu cầu revoke |
| 23 | Xóa consent nhưng không revoke token | Xác nhận đây là hai thao tác độc lập |
| 24 | Client bị vô hiệu hoặc secret bị đổi | Token/grant còn lại bị xử lý theo security incident policy |

### 16.1. Test lỗi không được tạo thông tin dò token

Với token lạ và token đã revoke, response công khai nên có hành vi khó phân biệt theo RFC 7009. Không trả trạng thái/description chứa subject, scope hoặc issuer đặc thù của token khi người gọi không đủ quyền.

### 16.2. Test multi-node và hiệu ứng cache

Trong môi trường có nhiều node:

1. Node A tiếp nhận request revocation.
2. Node B xử lý Refresh Token Grant bằng token đã revoke.
3. Node C xử lý introspection cho Access Token thuộc cùng grant.
4. Resource Server D kiểm tra JWT qua denylist/event.

Mọi thành phần phải có kết quả phù hợp policy. Trường hợp lỗi database replication, cache stale, event trễ hoặc hai request đồng thời cần có test riêng, không thể suy ra an toàn chỉ vì unit test service PASS.

### 16.3. Kiểm thử hợp đồng giữa AS và Resource Server

Một integration test giá trị nên phát hành Access Token thật từ test Authorization Server, gọi Orders API thành công, thu hồi token, rồi gọi lại Orders API. Đo thời gian từ revocation success đến lúc API từ chối. Ghi nhận đây là **measured revocation latency**, không nhầm với token TTL.

## 17. Mã lỗi và chẩn đoán sự cố

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| POST /oauth2/revoke trả 404 | Endpoint sai path hoặc SecurityFilterChain/proxy routing | Kiểm tra AuthorizationServerSettings và endpoints matcher |
| invalid_client | Client auth sai hoặc token không thuộc client | Kiểm tra registration và client association mà không log token |
| invalid_request | Thiếu token, form sai cấu trúc hoặc tham số trùng | Kiểm tra converter và request |
| HTTP 200 nhưng refresh vẫn dùng được | Store không lưu trạng thái, race, lookup sai hoặc custom provider lỗi | Đọc lại authorization và test Refresh Token Grant |
| HTTP 200 nhưng JWT vẫn gọi API được | Resource Server xác minh JWT offline | Thêm introspection/denylist hoặc giảm TTL theo policy |
| HTTP 200 nhưng opaque token còn active | Introspection cache stale hoặc authorization store không nhất quán | Kiểm tra cache TTL/cluster |
| Revoke một phiên làm mất cả nhiều phiên | Query dùng phạm vi user quá rộng hoặc xóa sai authorization | Kiểm tra device/client/session binding |
| Refresh Token cũ được chấp nhận sau rotation | Concurrency hoặc cấu hình reuseRefreshTokens | Test song song và refresh family state |
| Revoke một token nhưng refresh phát token mới | Chỉ Access Token bị revoke | Kiểm tra cascade policy |
| Lệnh revoke từ browser bị CSRF | API quản trị không bảo vệ CSRF hoặc session | Bổ sung CSRF protection và xác thực chủ thể |
| Revoke phụ thuộc admin nhưng client tự gọi được | Thiếu authorization/RBAC | Giới hạn endpoint chính sách nội bộ |
| Một node API từ chối, node khác chấp nhận | Denylist cache hoặc replication chưa đồng bộ | Kiểm tra propagation và SLO |

Không debug bằng cách chép Access/Refresh Token thật vào log hoặc hệ thống theo dõi. Dùng correlation ID, authorization ID nội bộ được bảo vệ, token fingerprint/hashing an toàn, error type và policy version.

## 18. Vận hành, quan sát và an toàn

### 18.1. Chỉ số vận hành nên theo dõi

| Chỉ số | Mục đích |
| --- | --- |
| Tỷ lệ HTTP 200/4xx/5xx ở Revocation Endpoint | Phát hiện client sai cấu hình và lỗi nội bộ |
| Revocation request count theo client/flow | Phát hiện bất thường, abuse và logout storm |
| Thời gian cập nhật authorization store | Đo latency state change |
| Thời gian từ revoke đến API từ chối | Đo revocation SLO thực tế |
| Introspection cache hit và stale window | Tối ưu độ trễ và mức an toàn |
| Refresh Token reuse attempts | Phát hiện dấu hiệu mất token/race |
| Tỷ lệ revoke tất cả thiết bị / client-wide | Phát hiện sự cố và lỗi policy |
| Đồng bộ event/denylist giữa các node | Ngăn trạng thái thu hồi không nhất quán |

Không dùng raw token, Refresh Token, client secret, số định danh nhạy cảm làm nhãn metrics. Khi phải liên kết nhiều sự kiện, dùng identifier nội bộ có quyền truy cập hạn chế và retention rõ ràng.

### 18.2. Bảo vệ Revocation Endpoint

- Bắt buộc HTTPS, không chấp nhận gửi token qua query string.
- Tuân thủ client authentication, client ownership và policy từng grant.
- Áp rate limit; không cho brute force hoặc token enumeration.
- Xử lý lỗi không tiết lộ token/user identity.
- Không log body của Revocation Request hoặc Authorization header.
- Không mở CORS cho origin tùy ý nếu không có lý do và kiểm soát cụ thể.
- Nếu có endpoint logout/revoke nội bộ dựa trên cookie, bảo vệ CSRF và session fixation.
- Phân tách quyền user revoke phiên của mình với quyền administrator revoke client/user khác.

### 18.3. Incident runbook khi Refresh Token bị lộ

Một quy trình thực tế có thể gồm:

1. Xác nhận incident và định danh authorization/thiết bị/client liên quan bằng metadata đáng tin.
2. Vô hiệu Refresh Token hiện tại và token family nếu chính sách hỗ trợ.
3. Thu hồi Access Token cùng authorization; áp dụng denylist/introspection hoặc thời hạn rủi ro đã biết.
4. Chấm dứt phiên đăng nhập bị ảnh hưởng khi cần.
5. Nếu credential client/private key bị lộ, rotate hoặc disable credential.
6. Cập nhật Resource Server về trạng thái không còn chấp nhận token theo SLO.
7. Kiểm tra audit hành vi lạ, scope/audience, refresh reuse và truy cập sau thời điểm revoke.
8. Xóa token khỏi client storage, xử lý cache và xác minh trạng thái thực tế.

Không xóa record audit trước khi lưu bằng chứng cần thiết; đồng thời tuân thủ chính sách privacy và retention. Nếu revoke thất bại giữa chừng, cần retry có kiểm soát, idempotency và cảnh báo vận hành.

## 19. Checklist triển khai production

1. **Endpoint:** /oauth2/revoke được bật và có client authentication đúng loại client.
2. **RFC 7009:** POST form-encoded, token_type_hint tùy chọn, HTTP 200 không lộ sự tồn tại token.
3. **Ownership:** token thuộc client đã xác thực; API quản trị có RBAC/tenant checks.
4. **Phạm vi revoke:** phân biệt access only, refresh+access, authorization, thiết bị, user-wide.
5. **Cascade policy:** có quyết định rõ về Refresh Token và Access Token cùng grant.
6. **Authorization store:** lưu invalidation bền vững; nhiều node nhìn thấy cùng trạng thái.
7. **JWT:** chấp nhận hạn chế của offline validation hoặc dùng denylist/online check.
8. **Opaque:** introspection trả active=false, cache không phá SLO.
9. **Rotation:** reuseRefreshTokens(false) chỉ là cấu hình rotation, không thay token-family detection.
10. **Concurrency:** kiểm thử token refresh/revoke đồng thời và xử lý transaction đúng.
11. **Sessions/consent:** logout, authorization revocation và consent removal được phân biệt.
12. **Token binding:** DPoP/mTLS không thay revocation.
13. **Privacy:** không ghi token/secret vào log; audit bằng metadata có bảo vệ.
14. **Monitoring:** đo propagation latency, lỗi, stale cache và reuse attempts.
15. **Recovery:** có quy trình xử lý incident, revoke hàng loạt và xác nhận sau revoke.
16. **Tests:** có test cả endpoint lẫn hiệu ứng ở Resource Server và nhiều node.

## 20. Bài tập và câu hỏi tự đánh giá

**Bài tập A — RFC 7009.** Một client gửi token không tồn tại tới Revocation Endpoint, nhưng client đã xác thực và request hợp lệ. Server nên trả HTTP nào? Vì sao không trả “token không tồn tại”?

**Bài tập B — Logout một thiết bị.** Alice có laptop và điện thoại, mỗi thiết bị có authorization riêng. Hãy thiết kế record/device association và lệnh chỉ thu hồi laptop mà không ảnh hưởng điện thoại.

**Bài tập C — Cascade.** Alice có Access Token A và Refresh Token R trong cùng authorization. Người dùng yêu cầu logout hoàn toàn. Hãy mô tả trạng thái cần đạt cho A và R, đồng thời xác định Resource Server phải làm gì nếu A là JWT offline.

**Bài tập D — JWT vs opaque.** Một hệ thống cần revoke phản ánh ở API trong thời gian ngắn. So sánh introspection với JWT denylist và JWT TTL ngắn về latency, availability, cache và độ phức tạp.

**Bài tập E — Refresh Token reuse.** R1 được đổi thành R2. R1 lại xuất hiện từ IP/thiết bị khác. Thiết kế family state, tín hiệu sự cố và chiến lược revoke. Giải thích tại sao chỉ bật reuseRefreshTokens(false) chưa đủ.

**Bài tập F — Authorization vs consent.** User thu hồi quyền ứng dụng và yêu cầu phải đồng ý lại ở lần sau. Những record/token nào cần xử lý? Vì sao chỉ xóa consent không đủ?

**Bài tập G — Multi-node.** Node A nhận revoke, node B nhận refresh, node C nhận introspection và Resource Server D dùng JWT denylist. Thiết kế test xác minh không có một đường đi nào tiếp tục cấp hoặc chấp nhận quyền ngoài SLO.

**Câu hỏi ôn tập:**

1. RFC 7009 yêu cầu tham số nào và token_type_hint có vai trò gì?
2. Vì sao server trả HTTP 200 cho token không tồn tại?
3. Revoke Access Token có luôn revoke Refresh Token không?
4. RFC 7009 khuyến nghị gì khi Refresh Token bị revoke?
5. `OAuth2AuthorizationService` khác `OAuth2AuthorizationConsentService` thế nào?
6. `OAuth2Authorization.Token.isActive()` có phản ánh invalidation không?
7. Vì sao JWT offline có thể vẫn gọi API thành công sau revoke tại Authorization Server?
8. Resource Server dùng introspection cần lưu ý gì khi cache active=true?
9. Vì sao một user có thể có nhiều OAuth2Authorization?
10. Token family và rotation có ý nghĩa gì khi phát hiện Refresh Token reuse?
11. `@Transactional` có tự bảo đảm các cache API nhận revoke tức thì không?
12. Thu hồi một authorization có tự logout OIDC browser session không?
13. Vì sao client_id trong request không đủ để cho phép admin revoke?
14. Những test nào chứng minh thời gian propagation thu hồi thực tế?

## 21. Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7009, Section 2 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009#section-2)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)

**Ghi nhớ:** Thu hồi token có ba lớp không thể bỏ qua: **Authorization Server cập nhật trạng thái**, **chính sách xác định những token/authorization liên quan cũng phải bị chấm dứt**, và **Resource Server thực sự từ chối các token đã thu hồi**. Revoke Refresh Token chặn việc gia hạn; revoke Access Token chỉ hữu hiệu tại API nếu API biết trạng thái đó; remove OAuth2Authorization không tự xóa browser session, consent hay mọi authorization khác của user. Luôn định nghĩa rõ phạm vi, cascade, consistency, thời gian propagation và kiểm thử từ HTTP Revocation Endpoint đến các API.
