# 23.7. Serialization, TTL và dọn dữ liệu token hết hạn

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, việc nhận được access token chỉ là bước đầu. Ứng dụng còn phải quản lý **cách lưu và khôi phục dữ liệu token (serialization)**, **thời hạn lưu (TTL — Time To Live)** và **quy tắc xóa dữ liệu cũ** mà không làm mất refresh token vẫn còn giá trị.

Một lỗi điển hình là đặt TTL của toàn bộ `OAuth2AuthorizedClient` bằng thời gian sống của access token. Nếu access token A1 hết hạn sau 10 phút nhưng refresh token R1 còn có thể dùng trong nhiều ngày, xóa authorized client ở phút thứ 10 sẽ làm mất cả R1. Ứng dụng không thể refresh token và có thể buộc người dùng thực hiện Authorization Code flow mới.

Chiều ngược lại cũng nguy hiểm: lưu mọi phiên và token vô hạn làm tăng rủi ro lộ credential, chiếm dung lượng, tạo dữ liệu không còn dùng được và phức tạp hóa yêu cầu privacy/retention.

Sau bài, bạn có thể:

- Phân biệt `OAuth2AuthorizedClient`, `SecurityContext`, OIDC principal và Authorization Request đang chờ callback.
- Giải thích cách serialize trạng thái khi dùng HttpSession, Spring Session Redis hoặc database.
- Hiểu rủi ro của Java serialization, JSON polymorphic deserialization và serialized object graph khi nâng phiên bản Spring Security.
- Phân biệt access token expiry, refresh token expiry, session idle timeout, data retention và TTL của cache key.
- Thiết kế cleanup không xóa authorized client chỉ vì access token hết hạn khi refresh token còn dùng được.
- Tổ chức Redis TTL, custom JDBC schema và scheduled cleanup batch có giới hạn.
- Giảm race giữa refresh token rotation và job dọn dữ liệu.
- Hiểu logout, account switching, token revocation và cleanup ở từng loại storage.
- Dùng `Clock` và integration tests để kiểm thử expiry/serialization mà không phải chờ thời gian thật.
- Quan sát cleanup bằng metrics/logs không chứa token raw.

## 1. Bối cảnh: Portal lưu nhiều loại trạng thái

Giả sử **Employee Portal** sử dụng Spring Security OAuth2 Login với OpenID Provider (OP), sau đó gọi **Orders API** qua access token.

~~~text
Browser
  └── Session cookie

Employee Portal
  ├── SecurityContext
  │   └── Authentication / OidcUser
  ├── OAuth2AuthorizedClient(corporate, Alice)
  │   ├── Access token A1
  │   └── Refresh token R1 (nếu AS cấp)
  └── Authorization Request đang chờ callback
      ├── state
      ├── PKCE code_verifier
      └── OIDC nonce khi áp dụng

OpenID Provider / Authorization Server
  └── SSO session, grant/consent, token policy

Orders API / Resource Server
  └── Kiểm tra access token và quyền nghiệp vụ
~~~

Đây là các loại trạng thái có **mục đích và thời hạn khác nhau**. Chúng không được tự động xóa hoặc gia hạn chỉ bằng một đồng hồ chung.

### 1.1. Bảng phân biệt

| Dữ liệu | Mục đích | Thời hạn do đâu quyết định? |
|---|---|---|
| Access token | Gọi Resource Server | Authorization Server và token metadata |
| Refresh token | Xin access token mới | Authorization Server và chính sách rotation/revocation |
| `OAuth2AuthorizedClient` | Gắn token với registration/principal | Thiết kế repository/service và retention của client |
| `SecurityContext` / Authentication | Xác định user đang đăng nhập Portal | Cơ chế session/security của ứng dụng |
| HttpSession/WebSession | Trạng thái theo browser session | Idle timeout, absolute lifetime nếu cấu hình |
| OP SSO session | Hỗ trợ SSO/reauthentication | Chính sách của OP |
| `OAuth2AuthorizationRequest` | Correlation trong Authorization Code flow | Timeout của authorization transaction |
| Stored claims của OIDC principal | Phục vụ authentication/authorization | Session và data-minimization policy |

**Token hết hạn không có nghĩa phiên đăng nhập đã hết**, và session còn sống không bảo đảm access token đang hợp lệ.

### 1.2. Dòng thời gian minh họa

~~~text
09:00  Alice đăng nhập OIDC.
       Access token A1 sống 10 phút.
       Refresh token R1 có thể còn hợp lệ nhiều ngày.
       HttpSession idle timeout 30 phút.

09:08  Portal gọi Orders API bằng A1.
09:10  A1 hết hạn.
09:11  Portal có thể dùng R1 để xin A2 nếu AS chấp nhận.
09:25  Session vẫn có thể tồn tại khi user tiếp tục hoạt động.
09:45  Session có thể hết hạn vì idle timeout.
10:00  AS vẫn có thể cho phép R1 dùng tiếp theo policy của nó.
~~~

Các số liệu chỉ là ví dụ. Tùy nơi lưu authorized client, session hết hạn có thể đồng thời làm mất bản ghi R1 của Portal dù AS chưa thu hồi R1.

## 2. Những đối tượng nào thực sự cần serialize?

### 2.1. `OAuth2AuthorizedClient`

Object này gắn một `ClientRegistration` với tên principal, access token và optional refresh token.

~~~text
OAuth2AuthorizedClient
  clientRegistration = corporate
  principalName = alice
  accessToken
    tokenValue = A1
    tokenType = Bearer
    issuedAt = ...
    expiresAt = ...
    scopes = [...]
  refreshToken (nếu được cấp)
    tokenValue = R1
    issuedAt = ...
    expiresAt = có thể null
~~~

Token value là **credential nhạy cảm**. Một bản snapshot JSON hoặc Java-serialized có thể chứa giá trị đủ để attacker cố dùng lại token nếu không có biện pháp sender-constrained phù hợp.

### 2.2. `SecurityContext` và principal OIDC

Sau OIDC Login, `SecurityContext` có thể chứa Authentication như `OAuth2AuthenticationToken`, với principal `OidcUser` và các claims như issuer, subject, email, groups hoặc roles.

Đây là trạng thái **xác thực người dùng tại Portal**, không đồng nhất với access token lưu trong `OAuth2AuthorizedClient` để gọi API.

Custom principal, authority hoặc authentication details có thể chứa class không hỗ trợ serialization. Phải xem **toàn bộ object graph thật**, không chỉ class framework ở ngoài cùng.

### 2.3. `OAuth2AuthorizationRequest`

Trước callback Authorization Code, client cần dữ liệu correlation như `state`, PKCE verifier và nonce OIDC khi áp dụng.

~~~text
Bắt đầu OAuth2 Login
  -> Tạo OAuth2AuthorizationRequest
  -> Lưu state/PKCE/nonce liên quan
  -> Redirect browser tới OP
  -> Callback
  -> Đọc request tương ứng và đối chiếu
  -> Token exchange
~~~

Nếu TTL của authorization request quá ngắn, browser quay về callback có thể bị lỗi missing/invalid state dù OP xác thực thành công.

Nếu giữ dữ liệu correlation quá lâu, các state/verifier nhạy cảm không cần thiết tồn tại kéo dài.

**Authorization Request repository trước callback khác Authorized Client repository sau token exchange.**

### 2.4. Không serialize nhiều hơn cần thiết

Một ứng dụng có thể không cần lưu toàn bộ ID token, raw UserInfo JSON hoặc mọi claim vào một custom token store.

Nên xác định rõ:

- Token nào bắt buộc lưu để gọi API?
- Claim nào cần giữ cho session Authentication?
- Trường nào chỉ dùng trong một request?
- Trường nào thuộc dữ liệu cá nhân cần retention/cleanup riêng?

Thiết kế tối thiểu giúp giảm lượng credential có thể bị lộ từ session dump, Redis backup hoặc database snapshot.

## 3. Repository và service lưu token trong Spring Security

### 3.1. Servlet: `OAuth2AuthorizedClientRepository`

Interface dành cho HTTP Servlet request/response, có những implementation như `HttpSessionOAuth2AuthorizedClientRepository`.

Nếu lưu authorized client trong HttpSession:

~~~text
HttpSession của Alice
  └── OAuth2AuthorizedClient(corporate)
      ├── A1
      └── R1
~~~

Khi session bị invalidate hoặc hết hạn, dữ liệu session-backed có thể bị xóa. Đây có thể là policy đúng cho web application không cần sử dụng token khi user rời phiên.

### 3.2. Service: `OAuth2AuthorizedClientService`

Service lưu/đọc/xóa authorized client theo registration ID và principal name, không bắt buộc có HttpServletRequest.

Có thể sử dụng:

- `InMemoryOAuth2AuthorizedClientService`.
- `JdbcOAuth2AuthorizedClientService`.
- Implementation custom với Redis, JDBC hoặc một storage khác.

`AuthenticatedPrincipalOAuth2AuthorizedClientRepository` có thể phối hợp service cho authenticated principal và một repository khác cho anonymous, tùy cách wiring.

**Record lưu ngoài session có thể tồn tại sau logout**, trừ khi ứng dụng chủ động cleanup.

### 3.3. WebFlux/Reactive

WebFlux có `ServerOAuth2AuthorizedClientRepository`, `ReactiveOAuth2AuthorizedClientService` và các manager reactive.

`WebSession` của WebFlux khác `HttpSession` của Servlet. Khi dùng Spring Session Redis, cần kiểm tra serializer và repository thực tế của stack đang chạy.

### 3.4. Chọn storage theo nhu cầu

| Storage | Điểm mạnh | Rủi ro cần kiểm soát |
|---|---|---|
| In-memory | Đơn giản cho demo/test | Mất sau restart; không share giữa nodes |
| HttpSession | Phù hợp vòng đời phiên browser | Session timeout có thể làm mất refresh token |
| Spring Session Redis | Session dùng chung nhiều instances | Serializer, Redis TTL, backup và quyền truy cập |
| JDBC service | Dữ liệu bền vững qua restart | Cần cleanup, encryption, concurrency |
| Custom Redis authorized client store | TTL/lookup nhanh | TTL sai có thể xóa R1; eviction khác expiry |
| Custom encrypted DB | Schema/retention/versioning rõ | Phải tự xử lý crypto, migration và lock |

Không có một lựa chọn phù hợp cho mọi hệ thống. Quyết định còn phụ thuộc việc token cần tồn tại **ngoài browser session** hay không.

## 4. Serialization là gì trong bài toán token?

Serialization biến object thành bytes, JSON hoặc fields có thể ghi vào store; deserialization tái dựng trạng thái cần sử dụng.

~~~mermaid
flowchart TD
    A["OAuth2AuthorizedClient / Session state"] --> B["Serialization / DTO mapping"]
    B --> C["Ciphertext / bytes / JSON / columns"]
    C --> D["Redis / Database / Session store"]
    D --> E["Load + decryption + deserialization"]
    E --> F["Authorized client / SecurityContext"]
    F --> G["AuthorizedClientManager / API request"]
~~~

Các rủi ro:

1. **Confidentiality:** token raw bị lộ từ Redis/database/backup/log.
2. **Integrity:** payload bị sửa, ghép sai registration/principal.
3. **Compatibility:** nâng version Spring Security khiến object cũ không đọc được.
4. **Availability:** serialization lỗi khiến login/session/token retrieval thất bại.
5. **Performance:** payload lớn làm tăng memory, network traffic và CPU.

## 5. Java native serialization

Một số session storage có thể sử dụng Java serialization cho session attributes.

Với object graph phức tạp như `SecurityContext` chứa custom principal/authorities, khả năng serialization phụ thuộc mọi nested object cần lưu.

### 5.1. Các vấn đề thường gặp

- `NotSerializableException` khi một custom object không implement Serializable.
- `InvalidClassException` khi class/serialVersionUID thay đổi.
- Tên class/package khác sau khi nâng thư viện.
- Payload bytes khó đọc hoặc migrate giữa nhiều service.
- Rủi ro Java deserialization từ nguồn bị attacker điều khiển.
- Payload chứa claims/token nhạy cảm không thể được coi là dữ liệu thông thường.

**Không deserialize bytes không tin cậy bằng Java native serialization.** Nếu phải dùng, giới hạn class/serializer, bảo vệ storage, bảo đảm integrity và kiểm thử compatibility.

### 5.2. Không mặc định framework object là schema dài hạn

Ngay cả khi nhiều đối tượng Spring Security hỗ trợ Serializable, việc dùng object graph framework như format lưu token lâu dài vẫn có nguy cơ khi rolling deployment hoặc thay major version.

Custom token store có thể ổn định hơn khi dùng **DTO explicit** và versioned schema.

## 6. JSON serialization và rủi ro polymorphic typing

JSON dễ quan sát schema, nhưng **không tự bảo vệ credential**.

Ví dụ không nên lưu:

~~~json
{
  "registrationId": "corporate",
  "principalName": "alice",
  "accessToken": "ACCESS_TOKEN_RAW",
  "refreshToken": "REFRESH_TOKEN_RAW"
}
~~~

Nếu file/Redis snapshot bị đọc, token đã lộ.

### 6.1. JSON mapper cần schema an toàn

Cẩn trọng với:

- Default typing cho phép payload chỉ định class tùy ý.
- Polymorphic deserialization của custom Authentication.
- Mixin hoặc Jackson module không đúng phiên bản Spring Security.
- `Instant`, token type, scopes, enum hoặc nested values không round-trip được.
- Field optional bị chuyển thành `null` và vô tình xóa refresh token khi cập nhật.

Nếu dùng Jackson cho Spring Security types, hãy sử dụng integration/mixins đúng phiên bản và hạn chế class được phép. Không bật permissive deserialization toàn cục để sửa nhanh một session không đọc được.

### 6.2. DTO explicit dễ migration hơn

Một DTO do ứng dụng sở hữu có thể thay đổi có kiểm soát theo version, thay vì phụ thuộc class name bên trong framework.

Ví dụ minh họa:

~~~java
import java.time.Instant;
import java.util.Set;

public record StoredAuthorizedClientV1(
        int schemaVersion,
        String registrationId,
        String principalKey,
        String accessTokenCiphertext,
        String accessTokenType,
        Instant accessTokenIssuedAt,
        Instant accessTokenExpiresAt,
        Set<String> scopes,
        String refreshTokenCiphertext,
        Instant refreshTokenIssuedAt,
        Instant refreshTokenExpiresAt,
        Instant lastUsedAt,
        long recordVersion) {
}
~~~

Đây là DTO cho **custom storage**, không phải schema API bắt buộc của Spring Security.

Ý nghĩa:

| Field | Mục đích |
|---|---|
| `schemaVersion` | Đọc và migrate payload sau nâng cấp |
| `registrationId` | Chọn client registration |
| `principalKey` | Gắn token với đúng user/service |
| `accessTokenCiphertext` | Token đã mã hóa để lưu |
| `accessTokenExpiresAt` | Biết thời điểm access token hết hạn |
| `refreshTokenCiphertext` | Credential dùng refresh nếu có |
| `refreshTokenExpiresAt` | Có thể null nếu AS không cung cấp |
| `lastUsedAt` | Retention theo inactivity khi được thiết kế |
| `recordVersion` | Optimistic concurrency khi rotation/cleanup |

### 6.3. Không tin metadata client từ payload

Khi tái tạo authorized client từ custom DTO, nên lấy `ClientRegistration` hiện hành từ `ClientRegistrationRepository` đáng tin cậy.

Không cho một payload tự thay issuer, token endpoint hoặc client authentication method chỉ vì thông tin đó từng được serialized.

## 7. Encryption và integrity cho token store

Access token và refresh token là credentials. Với custom store, có thể mã hóa token fields bằng AEAD (chẳng hạn AES-GCM) hoặc dịch vụ mã hóa được tổ chức phê duyệt.

~~~text
Token raw
  -> AEAD encrypt với key hiện hành
  -> ciphertext + nonce + key identifier
  -> database/Redis

Khi cần dùng:
  -> load record đúng principal
  -> verify/decrypt
  -> đưa token cho HTTP client đúng Resource Server
~~~

Cần lưu ý:

- Không reuse nonce không an toàn với cùng key.
- Quản lý encryption key qua KMS/secret manager khi phù hợp.
- Có kế hoạch key rotation và decrypt dữ liệu cũ.
- Có thể bind associated data với registration, principal/tenant để hạn chế thay ciphertext giữa records.
- Hạn chế nơi token xuất hiện dưới dạng plaintext.
- Kiểm soát truy cập DB, Redis, backup và logs.

**Disk encryption đơn thuần không thay thế application-level access control**; người có quyền query DB có thể vẫn đọc dữ liệu mà ứng dụng đã lưu plaintext.

### 7.1. Backup chứa credentials

Một Redis RDB/AOF snapshot hoặc database backup có thể giữ R1 ngay cả sau khi record online đã bị cleanup.

Cần retention, encryption, access control và quy trình xóa/thu hồi theo policy. Không coi xóa key Redis là bằng chứng token đã biến mất khỏi mọi backup.

### 7.2. Không log serialized objects

Tránh:

~~~java
logger.info("authorizedClient={}", authorizedClient);
logger.info("sessionAttributes={}", sessionAttributes);
~~~

Object `toString()` hoặc debug serializer có thể vô tình bao gồm token, claims hoặc cookie. Chỉ log metadata đã kiểm soát.

## 8. Access token expiry khác TTL của bản ghi

Access token có metadata:

~~~java
var accessToken = authorizedClient.getAccessToken();

Instant issuedAt = accessToken.getIssuedAt();
Instant expiresAt = accessToken.getExpiresAt();
~~~

`expiresAt` mô tả **thời điểm access token hết hạn**, không phải thời điểm phải xóa toàn bộ `OAuth2AuthorizedClient`.

### 8.1. Clock skew

Manager/provider có thể coi access token sắp hết hạn là cần refresh sớm theo khoảng lệch đồng hồ.

Token còn vài giây có thể hết hạn trước khi đến Orders API, vì vậy không chỉ kiểm tra `now < expiresAt` rồi kết luận chắc chắn API chấp nhận token.

### 8.2. Access token chưa hết hạn vẫn có thể bị từ chối

Một access token có thể bị revoke hoặc có sai audience/issuer/scope. Resource Server vẫn phải xác minh token và quyền nghiệp vụ.

Cleanup ở phía client không phải cơ chế xác minh token ở API.

### 8.3. Grant khác nhau có behavior khác nhau

- `authorization_code`: có thể nhận refresh token tùy chính sách AS.
- `refresh_token`: dùng refresh token đã có để xin token mới.
- `client_credentials`: thường xin token mới bằng client authentication khi token trước hết hạn, không nhất thiết có refresh token.

Một record expired của service client_credentials có thể được xóa để xin token mới, nhưng cần xét manager/provider và tần suất request thực tế.

## 9. Refresh token expiry có thể không biết

Một `OAuth2RefreshToken` có thể có thời điểm phát hành và expiry khi được cung cấp. Tuy nhiên, OAuth 2.0 token response không bắt buộc cung cấp một trường expiry refresh token phổ quát trong mọi tình huống.

Có thể gặp:

~~~text
access_token.expiresAt = 2026-11-16T10:00:00Z
refresh_token.issuedAt = 2026-11-16T09:50:00Z
refresh_token.expiresAt = null
~~~

**`null` không có nghĩa refresh token vô hạn hoặc đã hết hạn.** Nó có nghĩa ứng dụng không có thông tin expiry chính xác trong object đang giữ.

AS vẫn có thể áp:

- Absolute expiry.
- Inactivity timeout.
- Revocation.
- Consent withdrawal.
- Client disable.
- Refresh token rotation.
- Reuse detection.
- Quy tắc ràng buộc với session/tenant/client.

### 9.1. Metadata riêng của AS

Một số AS có custom field cho refresh expiry. Nếu sử dụng:

1. Đọc đúng contract của AS.
2. Xác định đơn vị giây/mili giây hoặc timestamp tuyệt đối.
3. Kiểm tra trường có thể vắng mặt.
4. Không áp logic của một provider cho mọi provider khác.
5. Tránh tự suy ra expiry bằng cách decode refresh token opaque.

### 9.2. Retention khi không biết refresh expiry

Ứng dụng có thể đặt chính sách như “xóa record sau 30 ngày không sử dụng”, nhưng đó là **data-retention policy**, không phải kết luận R1 đã hết hạn.

Chấp nhận hệ quả: user có thể cần authorize lại dù AS trước đó vẫn chấp nhận refresh token.

## 10. Session TTL độc lập với token TTL

Ví dụ minh họa:

| Thành phần | Thời hạn giả định | Điều gì xảy ra khi hết? |
|---|---|---|
| Access token A1 | 10 phút | API từ chối token expired |
| Refresh token R1 | Theo AS, có thể nhiều ngày | AS từ chối refresh khi không còn hợp lệ |
| Portal HttpSession idle timeout | 30 phút | Session có thể bị invalidate |
| OP SSO session | Theo OP | OP có thể yêu cầu login lại |
| Pending authorization request | Vài phút | Callback không còn dữ liệu correlation |
| DB authorized client retention | Theo policy app | Record có thể bị xóa, dù AS chưa revoke |

### 10.1. Session-backed authorized client

Nếu token được lưu trong HttpSession, session mất có thể làm mất token record. Điều đó hợp lý nếu ứng dụng chỉ cần gọi API khi user còn phiên browser.

Nếu cần một scheduled job gọi API thay user sau khi browser đóng, storage theo phiên không đủ; phải thiết kế offline access/consent, service storage và chính sách bảo mật riêng.

### 10.2. Session idle timeout khác absolute session lifetime

Idle timeout là thời gian không hoạt động. Absolute lifetime (nếu ứng dụng triển khai) giới hạn thời gian tối đa kể từ login.

Không coi việc refresh access token là bằng chứng user vừa xác thực lại. Authentication freshness/step-up cần OIDC request/claim và policy riêng.

### 10.3. OP session khác Portal session

Portal logout hoặc session timeout không tự đảm bảo OP SSO đã kết thúc. Ngược lại, OP session hết hạn không tự xóa mọi authorized client record ở Portal.

## 11. Quy tắc cleanup: không xóa quá sớm

Câu hỏi quan trọng khi xóa một authorized client record:

**Record này còn có thể dùng để gọi API hoặc làm mới access token hợp lệ không?**

| Access token | Refresh token | Quyết định thông thường |
|---|---|---|
| Còn hạn | Không có | Giữ nếu còn cần |
| Còn hạn | Có | Giữ |
| Hết hạn | Không có | Có thể xóa sau grace/retention |
| Hết hạn | Có, còn hiệu lực | **Giữ để refresh** |
| Hết hạn | Có, expiry chưa biết | **Không xóa chỉ vì access token expired** |
| Hết hạn | Có, known expiry đã qua | Có thể xóa |
| Còn hạn | Refresh token expired | Có thể giữ access token đến khi nó hết hạn |
| Bất kỳ | Revocation/disconnect được xác nhận | Cleanup theo policy |
| Bất kỳ | User account bị xóa hoặc không còn được phép | Cleanup theo chính sách tài khoản/privacy |

### 11.1. Anti-pattern: TTL bằng access token expiry

Nếu A1 có expiry 10 phút và R1 còn dùng được nhiều ngày:

~~~text
Redis key:
  authorized-client:corporate:alice
TTL:
  600 seconds

Value:
  accessToken=A1
  refreshToken=R1
~~~

Khi Redis xóa key sau 10 phút, client mất **cả A1 và R1**.

Với policy muốn giữ R1 để refresh, đây là thiết kế sai.

### 11.2. Không dùng query xóa mọi expired access token

Tránh:

~~~sql
DELETE FROM oauth2_authorized_client_store
WHERE access_expires_at < NOW();
~~~

Nó xóa cả record có refresh token vẫn có giá trị.

### 11.3. Grace period

Nếu muốn xóa unrefreshable records, có thể dùng cutoff:

~~~text
cutoff = now - 5 phút
~~~

Điều đó trì hoãn cleanup để giảm race với request đang chạy. Nó **không kéo dài hiệu lực access token tại AS**.

### 11.4. Nếu refresh expiry không biết

Không xem null là expired. Nếu không có chính sách inactivity/maximum retention được quyết định rõ, cleanup chỉ dựa access expiry sẽ phá vỡ refresh flow.

## 12. State machine cho token và cleanup

~~~mermaid
flowchart TD
    A["Authorized client record"] --> B{"Access token còn usable?"}
    B -->|Có| C["Giữ để sử dụng phù hợp"]
    B -->|Không| D{"Có refresh token?"}
    D -->|Không| E["Ứng viên cleanup theo policy"]
    D -->|Có| F{"Refresh token chắc chắn hết hiệu lực?"}
    F -->|Chưa biết / còn dùng được| G["Giữ để manager thử refresh"]
    F -->|Có bằng chứng expired/revoked| H["Ứng viên cleanup"]
    G --> I{"Refresh thành công?"}
    I -->|Có| J["Lưu A2 và R1/R2 tương ứng"]
    I -->|Không| K["Failure handling; không retry mù"]
    E --> L["Cleanup sau grace/retention"]
    H --> L
~~~

Đây là policy client-side. Token có thực sự được AS/RS chấp nhận hay không vẫn phải kiểm tra qua giao thức và chính sách tương ứng.

## 13. Ví dụ Java: policy nhận diện record hết hạn không thể refresh

Giả sử có `StoredAuthorizedClientV1` ở trên:

~~~java
import java.time.Instant;

public final class AuthorizedClientCleanupPolicy {

    private AuthorizedClientCleanupPolicy() {}

    public static boolean mayDeleteExpiredUnrefreshable(
            StoredAuthorizedClientV1 client,
            Instant cutoff) {

        if (client.accessTokenExpiresAt().isAfter(cutoff)) {
            return false;
        }

        if (client.refreshTokenCiphertext() == null) {
            return true;
        }

        return client.refreshTokenExpiresAt() != null
                && !client.refreshTokenExpiresAt().isAfter(cutoff);
    }
}
~~~

Giải thích:

1. Access token còn sau cutoff: không xóa theo policy này.
2. Access token đã hết hạn, không có refresh token: có thể xóa.
3. Có refresh token nhưng expiry không biết: không xóa chỉ vì access expiry.
4. Refresh token có known expiry và đã qua cutoff: có thể xóa nếu access token cũng đã quá cutoff.

**Đây là logic custom storage**, không phải phương thức mặc định trong Spring Security.

Nó chưa bao gồm user disconnect, revocation, maximum retention hoặc logic migration khi registration đổi issuer/client ID.

## 14. Custom JDBC schema và cleanup

Một custom storage có thể thiết kế bảng riêng:

~~~sql
CREATE TABLE oauth2_authorized_client_store (
    id                  BIGSERIAL PRIMARY KEY,
    registration_id     VARCHAR(100) NOT NULL,
    principal_key       VARCHAR(255) NOT NULL,
    access_token_ct     BYTEA NOT NULL,
    access_expires_at   TIMESTAMPTZ NOT NULL,
    refresh_token_ct    BYTEA,
    refresh_expires_at  TIMESTAMPTZ,
    last_used_at        TIMESTAMPTZ,
    record_version      BIGINT NOT NULL DEFAULT 0,
    UNIQUE (registration_id, principal_key)
);
~~~

Đây là **DDL minh họa cho PostgreSQL/custom store**. Không coi nó là schema có sẵn của `JdbcOAuth2AuthorizedClientService`.

### 14.1. Cleanup không xóa refresh token còn dùng được

Một query minh họa:

~~~sql
DELETE FROM oauth2_authorized_client_store
WHERE access_expires_at < :cutoff
  AND (
       refresh_token_ct IS NULL
       OR (
           refresh_expires_at IS NOT NULL
           AND refresh_expires_at < :cutoff
       )
  );
~~~

Nếu `refresh_token_ct` có dữ liệu nhưng `refresh_expires_at` là NULL, query không xóa record chỉ theo access expiry.

Nếu muốn áp maximum record age/inactivity, đó phải là điều kiện **được định nghĩa riêng**, có thể khiến user cần authorize lại.

### 14.2. Batch cleanup tránh tải lớn

Ví dụ PostgreSQL:

~~~sql
WITH candidates AS (
    SELECT id
    FROM oauth2_authorized_client_store
    WHERE access_expires_at < :cutoff
      AND (
          refresh_token_ct IS NULL
          OR (
              refresh_expires_at IS NOT NULL
              AND refresh_expires_at < :cutoff
          )
      )
    ORDER BY access_expires_at, id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
DELETE FROM oauth2_authorized_client_store t
USING candidates c
WHERE t.id = c.id;
~~~

Đây là SQL custom, chạy trong transaction phù hợp; các placeholder `:cutoff`, `:batch_size` cần cơ chế bind như `NamedParameterJdbcTemplate`.

### 14.3. Index phục vụ cleanup

~~~sql
CREATE INDEX idx_oauth_client_access_exp
ON oauth2_authorized_client_store (access_expires_at);
~~~

Cần kiểm tra query plan, số record, tần suất refresh/update và ảnh hưởng của index tới hiệu năng ghi.

### 14.4. Không áp trực tiếp lên schema mặc định

`JdbcOAuth2AuthorizedClientService` có schema và cách lưu token riêng của Spring Security. Nếu muốn cleanup trực tiếp bằng SQL, trước tiên phải xem DDL thực tế và cách service map dữ liệu. Không giả định schema mặc định có `refresh_expires_at` như custom table ví dụ.

## 15. Scheduled cleanup job

Spring `@Scheduled` có thể dùng để dọn record theo lịch, nhưng cleanup policy là trách nhiệm do ứng dụng thiết kế, không phải lời hứa tự động của authorized client service.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class AuthorizedClientCleanupJob {

    private final AuthorizedClientCleanupRepository repository;
    private final Clock clock;

    public AuthorizedClientCleanupJob(
            AuthorizedClientCleanupRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Scheduled(
            fixedDelayString =
                    "${security.oauth2.cleanup.delay-ms:900000}")
    public void cleanup() {
        Instant cutoff = Instant.now(clock)
                .minus(Duration.ofMinutes(5));

        int deleted = repository.deleteExpiredUnrefreshable(
                cutoff, 500);

        // Chỉ ghi metric đếm, không log token.
        recordCleanupMetric(deleted);
    }

    private void recordCleanupMetric(int deleted) {
        // Kết nối hệ thống metrics của ứng dụng.
    }
}
~~~

Contract của repository custom:

~~~java
import java.time.Instant;

public interface AuthorizedClientCleanupRepository {
    int deleteExpiredUnrefreshable(Instant cutoff, int maxRows);
}
~~~

Cấu hình đồng hồ:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Các ví dụ chỉ thể hiện kiến trúc; `deleteExpiredUnrefreshable` phải được hiện thực bằng SQL/Redis operations phù hợp và transaction an toàn.

### 15.1. Khi chạy nhiều instances

Nếu có ba Portal instances, một `@Scheduled` trên mỗi node có thể chạy ba job.

Cần cân nhắc distributed lock, leader election, job service riêng, hoặc batch query dùng row locks/`SKIP LOCKED` khi phù hợp.

Không mặc định scheduling trong Spring chạy một lần duy nhất trên toàn cluster.

### 15.2. Giới hạn khối lượng

Cleanup nên:

- Xóa từng batch.
- Có giới hạn thời gian/tải.
- Không giữ transaction quá lâu.
- Ghi metric rows deleted và backlog.
- Có cảnh báo khi số record xóa tăng bất thường.
- Không chạy vòng lặp xóa vô hạn trên request thread.
- Không ghi raw token trong log của job.

## 16. Redis TTL và eviction

Redis có TTL tự động cho keys, nhưng TTL phải theo **vòng đời record**, không nhất thiết theo expiry của access token.

### 16.1. Key có R1 đang dùng được

~~~text
SET authorized-client:corporate:alice encrypted-value EX 600
~~~

Nếu key chứa A1/R1 và R1 còn có thể refresh sau 600 giây, lệnh này có thể khiến R1 bị mất quá sớm.

### 16.2. TTL theo session

Với Spring Session Redis, key session thường được quản lý theo vòng đời session. Điều này thích hợp nếu dữ liệu token chỉ cần tồn tại khi browser session còn hợp lệ.

Nhưng nếu cần offline/background access, token store nên được thiết kế ngoài session và có policy riêng.

### 16.3. TTL khi biết refresh expiry

Nếu AS cung cấp expiry đáng tin cậy cho refresh token, record TTL có thể xét:

- Refresh expiry.
- Access expiry nếu vẫn còn muộn hơn.
- Grace period.
- Data-retention policy.
- Clock skew.
- Rotation cập nhật token và expiry mới.

Không tự động kéo TTL dài vô hạn sau mọi lần gọi đọc record nếu retention policy quy định absolute maximum age.

### 16.4. Refresh expiry không biết

Có thể dùng inactivity retention hoặc maximum retention được phê duyệt, nhưng không giả định R1 đã hết hạn chỉ vì expiry không có.

Nên mô tả rõ rằng xóa record theo retention có thể buộc user cấp quyền lại.

### 16.5. Eviction khác expiry

Ngay cả khi TTL còn dài, Redis có thể loại bỏ key do memory policy. Cần đánh giá eviction policy, persistence, replication, backup và failover nếu token store phải bền vững.

Không mặc định Redis cache là durable token repository cho mọi nghiệp vụ.

## 17. Refresh token rotation và race với cleanup

Giả sử record hiện tại A1/R1, AS dùng refresh token rotation:

~~~text
Request A: load A1/R1
Request B: load A1/R1

A: refresh(R1) -> A2/R2
B: refresh(R1) -> invalid_grant hoặc reuse detection
~~~

Nếu request B ghi lại A1/R1 sau khi A đã lưu A2/R2, hệ thống mất refresh token mới.

### 17.1. Cleanup đua với refresh

~~~text
Cleanup: tìm A1/R1 dựa trên snapshot cũ
Request A: refresh R1 -> lưu A2/R2
Cleanup: xóa record dù đã được cập nhật
~~~

Cần đảm bảo điều kiện delete được kiểm tra lại khi thực thi transaction, không chỉ dựa trên snapshot cũ.

### 17.2. Optimistic locking

Với custom table có `record_version`:

~~~sql
UPDATE oauth2_authorized_client_store
SET
    access_token_ct = :access_ct,
    access_expires_at = :access_expires_at,
    refresh_token_ct = :refresh_ct,
    refresh_expires_at = :refresh_expires_at,
    record_version = record_version + 1
WHERE id = :id
  AND record_version = :expected_version;
~~~

Nếu update được 0 row, có thể record đã bị thay đổi; cần reload và quyết định bước tiếp theo.

Không retry token endpoint bằng refresh token cũ vô hạn, đặc biệt khi AS đã rotate token.

### 17.3. Khi response không có refresh token mới

Nếu refresh response thành công chỉ có A2, không cấp R2, provider Spring Security thông thường giữ R1 đang lưu.

Không ghi `null` từ response đè lên R1. Ngược lại, khi AS cấp R2, phải lưu R2 và bỏ R1 theo rotation.

### 17.4. Chưa đủ nếu chỉ dùng TTL

TTL không bảo vệ atomicity khi nhiều request refresh cùng một record. Cần thiết kế concurrency độc lập với expiry policy.

## 18. Vai trò của `OAuth2AuthorizedClientManager`

Manager điều phối provider và authorized client storage.

Các ví dụ:

- `DefaultOAuth2AuthorizedClientManager` trong Servlet request.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` cho service/background ngoài Servlet request.
- `DefaultReactiveOAuth2AuthorizedClientManager` trong WebFlux request.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` cho reactive background/service.

### 18.1. Manager không phải scheduler dọn record

Khi A1 hết hạn và R1 tồn tại, manager/provider có thể dùng R1 để xin A2. Nếu cleanup job đã xóa record A1/R1, manager không còn token để refresh.

### 18.2. Failure handler và `invalid_grant`

Khi AS từ chối refresh token bằng `invalid_grant`, một số manager/handler của Spring Security có cơ chế remove authorized client trong các tình huống cụ thể.

Hành vi chi tiết phụ thuộc implementation và cấu hình. Không tự coi mọi lỗi mạng là revocation, và không retry vô hạn refresh token đã bị AS từ chối.

### 18.3. 401/403 từ Resource Server không phải expiry cleanup

API có thể trả 401 do token sai audience/issuer hoặc bị revoke. 403 thường do thiếu scope/quyền nghiệp vụ.

Không xóa toàn bộ session/token store chỉ vì một HTTP error chưa được phân loại.

## 19. Logout, disconnect và đổi tài khoản

### 19.1. Logout local

Nếu authorized client sống trong HttpSession, invalidate session thường làm mất record đó. Nếu token sống trong `OAuth2AuthorizedClientService` bên ngoài session, logout không tự bảo đảm xóa record.

### 19.2. Local delete khác token revocation

`removeAuthorizedClient` xóa dữ liệu phía ứng dụng, không tự gọi AS revocation endpoint.

Nếu người dùng disconnect provider, có thể cần:

- Xóa local authorized client.
- Thu hồi token tại AS nếu hỗ trợ và policy yêu cầu.
- Xử lý session/cookie.
- Xóa liên kết tài khoản.
- Đánh giá cache/backup và retention.

### 19.3. Account switching

Alice logout, Bob login trong cùng browser. Nếu store còn token Alice mà controller dùng nhầm cho Bob, đây là lỗi token ownership.

Cần bind token với đúng registration/principal, cleanup khi đổi account và kiểm tra user identity đã được OIDC xác minh.

### 19.4. Multi-issuer và tenant

OIDC `sub` chỉ có tính duy nhất trong phạm vi `iss`. Hai OP có thể phát cùng `sub` cho hai người khác nhau.

Khi thiết kế `principalKey`, nên dùng identity nội bộ đáng tin cậy ánh xạ với `iss` + `sub` và tenant nếu cần. Không dùng email tự khai báo làm khóa toàn hệ thống.

## 20. Serialization khi nâng phiên bản Spring Security

Một distributed session store có thể chứa Authentication/Principal được serialize bằng class của version cũ.

Khi nâng Spring Security hoặc ứng dụng:

- Class/package có thể đổi.
- JSON mixin/module có thể đổi.
- `serialVersionUID` có thể không tương thích.
- Custom principal có field mới.
- Serialized payload có thể không deserialize được.

### 20.1. Rolling deployment

Nếu Portal A chạy version cũ và Portal B chạy version mới, cả hai có thể đọc/ghi cùng Redis session. Nếu serializer/schema không tương thích, user có thể gặp lỗi theo node nhận request.

Trước rollout:

1. Xác định serializer production.
2. Thử round-trip với dữ liệu thực tế đã được thay thế credential bằng token giả.
3. Thử đọc payload version cũ ở code version mới.
4. Thử mixed-version khi dùng rolling deployment.
5. Có migration hoặc session drain strategy.
6. Không log raw serialized payload khi xảy ra lỗi.

### 20.2. Không sửa lỗi deserialization bằng default typing mở rộng

Nếu Jackson không biết cách tạo một `Authentication`, không nên bật unrestricted polymorphic typing để mọi class trong payload được instantiate.

Thay bằng mapper/module/mixin được kiểm soát và đúng version hoặc chuyển sang schema explicit.

### 20.3. Khi schema cũ thiếu refresh expiry

Nếu trước đây AS không cấp refresh expiry, sau migration có thể vẫn có `refreshExpiresAt == null`.

Không tự điền `now` hay access expiry để lấp trường mới; làm như vậy có thể khiến cleanup xóa refresh token còn hợp lệ.

## 21. Metrics, logging và auditing

Cleanup cần được quan sát, nhưng không được làm lộ token.

Những chỉ số minh họa:

~~~text
oauth2_authorized_client_records_total
oauth2_authorized_client_cleanup_deleted_total
oauth2_authorized_client_cleanup_backlog
oauth2_authorized_client_deserialization_failures_total
oauth2_authorized_client_refresh_invalid_grant_total
oauth2_authorized_client_store_bytes
oauth2_authorized_client_cleanup_duration_seconds
~~~

Không đưa access token, refresh token, JWT assertion, ID token hoặc raw session ID vào metric label.

### 21.1. Audit event

Ví dụ:

~~~text
event=AUTHORIZED_CLIENT_REMOVED
reason=EXPIRED_UNREFRESHABLE
registrationId=corporate
recordReference=opaque-id
deletedCount=1
timestamp=...
~~~

Tránh:

~~~text
access_token=eyJ...
refresh_token=...
session_cookie=...
serialized_client=...
~~~

### 21.2. Dấu hiệu bất thường

- Record count tăng mãi.
- Cleanup backlog tăng.
- Deserialize failures tăng sau deploy.
- User phải login lại đúng thời điểm access token expired.
- `invalid_grant` tăng khi refresh song song.
- Nhiều node có authorized client khác nhau.
- Redis eviction khiến mất token sớm.
- Cleanup job xóa quá nhiều record ngay sau deployment.

## 22. Kiểm thử TTL và serialization

### 22.1. Ma trận expiry

| Test case | Kỳ vọng |
|---|---|
| A1 còn hạn, không có R1 | Giữ |
| A1 hết hạn, không có R1 | Có thể dọn sau grace |
| A1 hết hạn, R1 còn hạn | **Giữ** |
| A1 hết hạn, R1 có expiry null | **Không xóa chỉ theo access expiry** |
| A1 hết hạn, R1 known expiry đã qua | Có thể dọn |
| A1 còn hạn, R1 known expiry đã qua | Không xóa access token usable chỉ bằng rule này |
| Refresh thành công A1/R1 → A2/R2 | Persist A2/R2 |
| Refresh response A2 không cấp R2 | Giữ R1 theo provider semantics |
| Cleanup chạy đồng thời refresh | Không xóa record mới |
| User disconnect | Cleanup theo policy |
| Redis key bị evict | Xử lý mất authorized client theo contract |

### 22.2. Dùng `Clock` thay vì ngủ thật

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-16T10:00:00Z"),
        ZoneOffset.UTC);
~~~

Inject `Clock` vào policy/job giúp test expiry ổn định, không phụ thuộc `Thread.sleep(...)`.

### 22.3. Test serialization round-trip

1. Tạo authorized client và Authentication bằng token giả.
2. Serialize qua serializer production.
3. Deserialize lại.
4. Kiểm tra registration, principal, scopes, token type và timestamps.
5. Kiểm tra refresh token vẫn còn đúng.
6. Thử payload thiếu optional fields.
7. Thử payload schema cũ.
8. Thử custom principal/authorities nếu lưu trong session.
9. Kiểm tra lỗi không log credential.

### 22.4. Integration test cleanup/refresh race

Dựng storage test, hai request refresh và một cleanup job. Sau race, đảm bảo record được bảo toàn nếu đã có A2/R2, không bị job dọn snapshot cũ xóa nhầm.

Không dùng token production hoặc cố phát lại refresh token thật trong môi trường chạy AS thật chỉ để thử reuse detection.

## 23. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| User login lại sau đúng 10 phút | TTL toàn record theo access token | Redis TTL và storage policy |
| A1 expired nhưng không refresh | R1 đã bị cleanup | Repository/service và job |
| Refresh được một lần rồi thất bại | Không lưu R2 hoặc mất R1 | Rotation, success handler |
| Token còn ở DB sau logout | Store ngoài session | Cleanup/logout policy |
| Session Redis deserialize lỗi sau nâng cấp | Class/serializer mismatch | Schema/version/mixin |
| Node A có token, B không | In-memory store hoặc session không share | Backing store |
| DB tăng record mãi | Thiếu retention/cleanup | Job, indexes, policy |
| Cleanup xóa A2/R2 mới | Race, stale snapshot | Transaction/CAS |
| `invalid_grant` tăng | Rotation reuse, expiry, revocation | Concurrency và AS policy |
| Refresh expiry là null | AS không cấp metadata | Không coi null là expired |
| Redis key biến mất trước TTL | Eviction/flush/failover | Redis policy/durability |
| API trả 401 | Issuer, audience, expiry, revocation | Resource Server validation |
| API trả 403 | Scope/quyền nghiệp vụ | Không mặc định refresh |
| Token xuất hiện trong logs | Serializer/debug header dump | Redact và xử lý credential |

## 24. Tình huống thực hành

### A. TTL quá ngắn

A1 sống 10 phút, R1 còn dùng được 14 ngày. Redis key chứa A1/R1 có TTL 600 giây.

**Kết luận:** nếu ứng dụng cần refresh sau 10 phút, TTL đang xóa R1 quá sớm. Đặt retention theo lifecycle có chủ đích.

### B. Session timeout nhưng AS chưa revoke

Portal dùng `HttpSessionOAuth2AuthorizedClientRepository`. Session hết sau 30 phút không hoạt động.

**Kết luận:** dữ liệu session có thể mất dù AS chưa thu hồi R1. Đây là hệ quả storage policy, không phải token expiry cùng nghĩa.

### C. JDBC không có cleanup

Bảng authorized client có nhiều record của user cũ. Một số có refresh token không biết expiry.

**Kết luận:** cần retention/inactivity policy và cleanup batch; không xóa mọi record chỉ theo access expiry.

### D. Refresh/cleanup đồng thời

Request refresh lưu A2/R2 trong khi cleanup đọc bản A1/R1 cũ.

**Kết luận:** dùng transaction, conditional deletion hoặc record version để tránh xóa token mới.

### E. Nâng thư viện và lỗi session

Spring Security mới không đọc được serialized custom principal từ node cũ.

**Kết luận:** cần compatibility test, migration hoặc session drain strategy. Không bật deserialization permissive.

### F. User disconnect

Alice yêu cầu ngắt kết nối OP, nhưng DB vẫn giữ R1.

**Kết luận:** xóa local record, xem xét AS revocation và retention của backups/caches theo chính sách.

### G. Refresh token không có expiry

R1 có `expiresAt == null`.

**Kết luận:** không tự coi R1 hết hạn. Nếu cần giới hạn lưu giữ, dùng retention policy riêng và chấp nhận user có thể authorize lại.

### H. Token bị lộ trong session dump

Debug log ghi toàn bộ `OAuth2AuthorizedClient`.

**Kết luận:** dừng log credential, xác định phạm vi ảnh hưởng, xử lý token theo quy trình bảo mật và thêm kiểm thử redaction.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Access token `expiresAt` có phải thời điểm phải xóa toàn bộ `OAuth2AuthorizedClient` không?

**Trả lời:** Không. Refresh token có thể còn giá trị để xin access token mới.

**Câu 2.** `OAuth2RefreshToken.getExpiresAt() == null` có nghĩa token sống mãi không?

**Trả lời:** Không. Client có thể chưa biết expiry; AS vẫn có chính sách expiry/revocation.

**Câu 3.** TTL của HttpSession và access token có giống nhau không?

**Trả lời:** Không. Một bên là vòng đời phiên của ứng dụng, bên kia là thời hạn token.

**Câu 4.** Vì sao TTL Redis bằng access token lifetime có thể gây lỗi?

**Trả lời:** Key chứa cả access và refresh token; Redis có thể xóa luôn refresh token còn dùng được.

**Câu 5.** `JdbcOAuth2AuthorizedClientService` có mặc định triển khai mọi retention policy của dự án không?

**Trả lời:** Không nên giả định. Cần kiểm tra implementation/schema và thiết kế cleanup phù hợp.

**Câu 6.** Serialization thành JSON có tự mã hóa token không?

**Trả lời:** Không. JSON chứa token raw vẫn là dữ liệu bí mật ở dạng plaintext.

**Câu 7.** Vì sao không nên serialize object graph Spring Security như schema dài hạn không thay đổi?

**Trả lời:** Class, field, serializer và version có thể thay đổi, gây incompatibility khi nâng cấp/rolling deployment.

**Câu 8.** Nếu cleanup đua với refresh token rotation thì sao?

**Trả lời:** Job có thể xóa A2/R2 mới nếu dùng snapshot cũ. Cần transaction/versioning.

**Câu 9.** Xóa local authorized client có revoke token ở AS không?

**Trả lời:** Không tự động. Revocation là thao tác riêng.

**Câu 10.** Redis eviction có giống TTL hết hạn không?

**Trả lời:** Không. Eviction có thể làm mất key vì memory policy trước expiry.

**Câu 11.** Vì sao nên inject `Clock`?

**Trả lời:** Test expiry/grace ổn định, không phụ thuộc đồng hồ thật hoặc sleep.

**Câu 12.** Có nên log raw access token để chẩn đoán cleanup không?

**Trả lời:** Không. Dùng registration ID, record reference và error category đã kiểm soát.

**Câu 13.** API trả 403 có chứng minh TTL của token store sai không?

**Trả lời:** Không. 403 thường liên quan scope/authority/quyền nghiệp vụ.

**Câu 14.** User logout nhưng authorized client còn trong service store, điều đó có thể xảy ra không?

**Trả lời:** Có. Storage ngoài session có thể cần cleanup riêng.

## Ghi nhớ

- **Serialization** quyết định cách token, Authentication và session được lưu/khôi phục. Payload có thể chứa credentials và claims nhạy cảm; cần schema rõ, bảo mật, versioning và deserialization an toàn.
- **Access token expiry, refresh token expiry, session TTL và data retention là các khái niệm khác nhau.** Không gộp vào một đồng hồ TTL duy nhất.
- **Không xóa toàn bộ authorized client chỉ vì access token hết hạn nếu refresh token còn có thể dùng.** Đây là quy tắc quan trọng nhất của cleanup.
- **Refresh token expiry chưa biết không có nghĩa expired hoặc immortal.** Chính sách giữ record cần được định nghĩa có chủ đích.
- **Redis TTL, JDBC cleanup và HttpSession/WebSession lifecycle phải theo loại storage và use case**, không giả định framework tự dọn mọi record.
- **Refresh token rotation có thể race với cleanup**, cần transaction, compare-and-swap hoặc conditional deletion để tránh mất token mới.
- **Logout/local delete không đồng nghĩa AS revocation.** Cần xem session, service store, cache và backup.
- **Không log raw token, serialized session hoặc credential**, kể cả trong metrics/tracing/debug.
- **Dùng Clock và integration tests** kiểm tra expiry, serialization migration và concurrent cleanup/refresh trước khi áp dụng ở production.
