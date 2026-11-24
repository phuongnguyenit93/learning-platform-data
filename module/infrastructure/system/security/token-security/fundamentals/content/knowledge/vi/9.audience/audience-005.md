# Audience alias và migration

Một hệ thống phát hành access token cho API đơn hàng với claim `aud = "orders-api"`. Sau khi nâng cấp, API được đặt định danh mới là `"https://api.example.com/orders"`. Nếu Authorization Server (AS) đổi `aud` ngay lập tức nhưng Resource Server (RS) vẫn chỉ chấp nhận `orders-api`, các request hợp lệ sẽ nhận lỗi xác thực. Ngược lại, nếu để API chấp nhận mọi audience có chữ `orders`, một token dành cho API khác có thể bị dùng nhầm.

Giải pháp thường là **migration theo giai đoạn**: xác định alias được phép, cập nhật bên xác minh trước, chuyển bên phát hành sau, quan sát token cũ cho đến khi hết hiệu lực, rồi gỡ alias. Cốt lõi là giữ đúng **ranh giới tin cậy** của token trong suốt quá trình.

Bài thuộc chương **Audience** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối JWT và opaque token với access/refresh token, OAuth 2.0/OIDC, phát hành, kiểm tra claims và scope, thu hồi, lưu trữ và phòng tránh token bị đánh cắp hoặc phát lại. Trọng tâm là **audience alias và migration** — thay đổi định danh bên nhận token một cách có kiểm soát.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò `aud` và phân biệt nó với `iss`, `sub`, `client_id`, `scope` và tenant.
2. Phân biệt **định danh audience chính thức**, **alias tạm thời**, URL mạng, API version và scope.
3. Thiết kế phép kiểm audience chính xác cho JWT access token và opaque access token qua introspection.
4. Lập kế hoạch migration không gián đoạn dịch vụ theo thứ tự **Resource Server → Authorization Server → Client → loại alias cũ**.
5. Đánh giá rủi ro **token substitution**, nhận nhầm token giữa API, audience quá rộng và token có nhiều audience.
6. Xây dựng điều kiện quan sát, rollback, thu hồi và bộ test để kết thúc migration an toàn.

## 2. Audience là gì?

`aud` (*audience*) xác định **bên nhận mà token hướng tới**. Trong JWT (RFC 7519), `aud` có thể là một chuỗi hoặc một mảng các chuỗi. Bên xử lý JWT phải xác định mình có nằm trong tập audience được chỉ định hay không, theo hợp đồng token và cấu hình bảo mật.

Với OAuth 2.0:

- **Authorization Server (AS)** cấp access token, lựa chọn audience dựa trên yêu cầu hợp lệ và chính sách cấp quyền.
- **Resource Server (RS)** là API nhận access token và kiểm token có được cấp **cho API này** hay không.
- **OAuth Client** yêu cầu token rồi trình token khi gọi API; client không được tùy ý sửa `aud` của JWT đã ký.
- **OpenID Provider (OP)** trong OIDC thường phát hành ID token có `aud` là **client ID** của bên đăng nhập. ID token không được dùng làm access token của Resource Server.

Ví dụ các vai trò trong hệ thống bán hàng:

| Thuộc tính | Giá trị minh họa | Câu hỏi được trả lời |
|---|---|---|
| `iss` | `https://login.example.com` | Ai phát hành token? |
| `sub` | `user-742` | Token nói về chủ thể nào? |
| `client_id` | `shop-web` | Client nào đã yêu cầu/được gắn với token theo profile? |
| `aud` | `orders-api` | Token dành cho API nào? |
| `scope` | `orders:read` | Token được cấp phạm vi hành động nào? |
| `tenant_id`, nếu có | `tenant-beta` | Ngữ cảnh tenant nào, theo hợp đồng riêng của hệ thống? |

**Đúng issuer và chữ ký chưa đủ.** Access token từ `https://login.example.com` với `aud=payments-api` vẫn phải bị `orders-api` từ chối. Scope `orders:read` cũng không sửa được việc sai audience.

### 2.1. So khớp chuỗi phải chính xác

Audience là định danh theo hợp đồng giữa issuer và Resource Server. Không tự rút gọn hoặc chuẩn hóa:

~~~text
"orders-api"                     != "orders-api-v2"
"https://api.example.com/orders" != "https://api.example.com/orders/"
"https://API.example.com/orders" != "https://api.example.com/orders"
"api://orders"                   != "api://orders-v2"
~~~

Trong JWT, việc so sánh `aud` theo chuẩn là so khớp **case-sensitive** của từng giá trị chuỗi. Không áp dụng `startsWith`, `contains`, biểu thức chính quy rộng, so theo suffix host, đổi chữ hoa/thường hoặc bỏ dấu `/` tùy tiện. Nếu có hai cách viết được chấp nhận, khai báo **hai giá trị cụ thể trong danh sách có kiểm soát**.

Một audience có dạng URI không có nghĩa RS phải tự xử lý nó như URL điều hướng hay DNS lookup; mục đích chính là **định danh tài nguyên**, và issuer/RS phải thống nhất cách sử dụng. Thay DNS, đổi hostname vận hành hoặc đổi route URL không nhất thiết yêu cầu đổi audience.

## 3. Audience alias là gì?

**Audience alias** trong bài này là một hoặc nhiều định danh audience thay thế được hệ thống **chủ động cho phép** biểu thị cùng một Resource Server hoặc cùng một ranh giới API trong một giai đoạn chuyển đổi. Đây là **quy ước triển khai** của AS/RS, không phải một claim OAuth/JWT chuẩn tên `aud_alias`.

Ví dụ:

~~~yaml
resourceServer: orders-api
issuer: https://login.example.com
canonicalAudience: https://api.example.com/orders
temporarilyAcceptedAudiences:
  - orders-api
  - https://api.example.com/orders
migrationId: orders-audience-2026
~~~

Đây là tài liệu chính sách minh họa, **không phải cấu hình sẵn có của Spring Security**.

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Canonical audience** | Định danh audience mục tiêu mà AS sẽ phát hành khi chuyển đổi xong | `https://api.example.com/orders` |
| **Legacy audience** | Định danh AS từng cấp cho cùng Resource Server | `orders-api` |
| **Accepted audiences** | Tập chính xác các audience mà RS có thể nhận trong một khoảng thời gian | `{orders-api, https://api.example.com/orders}` |
| **Migration window** | Thời gian duy trì khả năng nhận token cũ/new token theo chính sách | Từ khi RS nhận alias mới đến khi gỡ alias cũ |
| **Rollback** | Quy trình quay về cấu hình phát hành/nhận token cũ nếu gặp lỗi | AS ngừng phát aud mới khi RS vẫn nhận cả hai |

Cần tránh **alias collision**: không dùng một chuỗi audience để chỉ hai API có ranh giới tin cậy khác nhau. Ví dụ `orders-api` và `payments-api` không được coi là alias chỉ vì đi qua cùng gateway hoặc cùng domain.

### 3.1. Alias không phải wildcard

Các cấu hình sau rất nguy hiểm:

~~~text
acceptAnyAudience = true
acceptedAudiencePrefix = "https://api.example.com/"
acceptIfContains = "orders"
acceptAnySignedTokenFromIssuer = true
~~~

Chúng có thể khiến API đơn hàng chấp nhận token dành cho một API khác từ cùng issuer. **Alias phải là tập định danh cụ thể, hữu hạn, đã thẩm định**, gắn với issuer, Resource Server và thời gian chuyển đổi.

### 3.2. Alias không tự trao quyền

Ngay cả khi token có một audience nằm trong tập được phép, API vẫn phải kiểm:

- Loại token là **access token** đúng hồ sơ, không phải ID token/refresh token.
- `iss` đúng nguồn phát hành và chữ ký/khóa tin cậy, hoặc introspection trả dữ liệu tin cậy cho opaque token.
- `exp`, `nbf` và các điều kiện thời gian hợp lệ.
- Scope/permission phù hợp hành động.
- Quyền với tài nguyên, tenant, trạng thái người dùng, client và các chính sách nghiệp vụ.

Bên nhận token **không được dùng audience alias để bỏ qua authorization**.

## 4. Những thay đổi nào thực sự cần migration audience?

| Thay đổi hệ thống | Có nhất thiết đổi `aud`? | Lưu ý |
|---|---|---|
| Đổi DNS/CDN hoặc IP của cùng API | **Không** | Audience là định danh logic; endpoint mạng có thể đổi mà audience giữ nguyên. |
| Đổi domain API nhưng giữ nguyên ranh giới quyền | **Không nhất thiết** | Giữ audience cũ thường đơn giản và an toàn hơn nếu không có yêu cầu thay đổi định danh. |
| Chuẩn hóa audience từ tên ngắn thành URI ổn định | **Có, nếu chủ động đổi hợp đồng** | Dùng alias tạm thời cùng kế hoạch loại bỏ. |
| Tách một API lớn thành orders-api và payments-api | **Cần đánh giá lại ranh giới** | Không mặc định hai API mới nhận token audience cũ; nguy cơ mở rộng quyền. |
| Gộp hai API thành một gateway | **Không tự động** | Gateway có thể định tuyến, nhưng từng backend vẫn phải giữ policy phù hợp. |
| Nâng API v1 lên v2, quyền không đổi | **Tùy hợp đồng audience** | Không bắt buộc mỗi version URL có một audience mới. |
| Đổi Authorization Server hoặc issuer | **Không phải chỉ migration audience** | Cần xử lý thay đổi `iss`, JWKS, trust và policy riêng; tuyệt đối không nhập nhằng khóa tin cậy. |
| Đổi tenant của một request | **Không** | Audience chỉ API nhận token; tenant là ranh giới authorization khác. |

**Câu hỏi cần trả lời trước khi đặt alias:** Hai audience cũ và mới có thật sự đại diện cho **cùng một Resource Server hoặc cùng một phạm vi an ninh** không? Nếu câu trả lời là không, cần phát hành token riêng hoặc thiết kế token exchange; alias chung thường không an toàn.

## 5. Mô hình tin cậy trong migration

Giả sử các thành phần:

~~~text
Authorization Server:
  issuer = https://login.example.com

Legacy audience:
  orders-api

New canonical audience:
  https://api.example.com/orders

Resource Server:
  Order Service (cùng ranh giới quyền cũ)

OAuth Clients:
  shop-web
  order-worker

Endpoint:
  GET /orders/{id} requires orders:read
~~~

Trong migration, RS có thể tạm chấp nhận:

~~~text
issuer == "https://login.example.com"
AND access_token_profile_is_valid
AND aud intersects {
    "orders-api",
    "https://api.example.com/orders"
}
AND exp/nbf is valid
AND scope and object-level permissions allow the request
~~~

Phép kiểm `aud intersects` trong ví dụ **phù hợp khi hai định danh đã được xác minh là alias của cùng resource boundary**. Không được coi “có bất kỳ audience nào trong mảng đúng” là lý do bỏ qua audience không mong muốn: một JWT đa audience có thể cần quy tắc kiểm soát chặt hơn tùy tính chất API và chính sách AS.

### 5.1. Đừng nhầm “được ký bởi cùng AS” với “được phép đi qua cùng API”

AS có thể phát hành token cho `payments-api` và `orders-api` bằng cùng signing key. Nếu Order Service bỏ kiểm `aud`, token thanh toán có thể bị dùng nhầm để gọi đơn hàng. Nguy cơ này được gọi là **token substitution** hoặc **cross-resource token replay**, tùy tình huống.

Sơ đồ đối chiếu:

~~~mermaid
flowchart LR
    AS[Authorization Server]
    AS -->|aud = orders-api| O[Orders Token]
    AS -->|aud = payments-api| P[Payments Token]
    O --> ORD[Orders Resource Server]
    P --> PAY[Payments Resource Server]
    P -. không được dùng .-> ORD
    O -. không được dùng .-> PAY
~~~

Alias chỉ được nối giữa **định danh cũ và mới của cùng ranh giới Orders**, không nối toàn bộ token có chữ ký đúng từ AS.

### 5.2. Phải gắn alias với issuer đã tin cậy

Nếu API tin nhiều Authorization Server, danh sách audience có thể khác nhau theo issuer:

~~~yaml
trustedIssuerProfiles:
  - issuer: https://login.example.com
    allowedAudiences:
      - orders-api
      - https://api.example.com/orders
  - issuer: https://login.partner.example
    allowedAudiences:
      - partner-orders-api
~~~

Đây chỉ là mẫu chính sách. Không nên dùng một tập alias toàn cục cho mọi issuer nếu định danh và quyền của mỗi nhà phát hành khác nhau. Token chỉ được đánh giá bằng profile và khóa của **issuer tương ứng**, sau đó mới đối chiếu audience/claims.

## 6. Quy trình migration không gián đoạn

Nguyên tắc thứ tự là **mở khả năng xác minh trước khi đổi cách phát hành**, sau đó gỡ tương thích cũ khi chắc chắn không còn token/client cần nó.

### Giai đoạn 0 — Kiểm kê và chốt phạm vi

Trước khi triển khai:

1. Liệt kê **tất cả Resource Server** có nhận audience cũ: API public, microservice, worker, gateway, tác vụ định kỳ và các môi trường được áp dụng.
2. Xác định **issuer** nào cấp token cũ, token profile, JWKS/introspection và các client/grant liên quan.
3. Ghi nhận access token TTL lớn nhất, clock skew cho phép, thời gian cache, cơ chế refresh và xử lý token cấp ngoại lệ.
4. Xác nhận audience mới có **cùng ranh giới bảo mật** với audience cũ. Nếu API đang bị tách quyền, cần thiết kế riêng.
5. Định nghĩa canonical audience, alias tạm, ngày ngừng cấp audience cũ và điều kiện gỡ alias. Có phương án rollback.
6. Xác nhận cách đo lượng token theo audience **không ghi token thô hoặc dữ liệu nhạy cảm**.

### Giai đoạn 1 — Triển khai verifier nhận cả audience cũ và mới

Cập nhật tất cả RS liên quan để tạm chấp nhận **hai giá trị chính xác**. Giữ nguyên issuer, chữ ký, token type, expiry, scope, quyền.

~~~text
Accepted by orders-api:
  "orders-api"                       => valid candidate
  "https://api.example.com/orders"   => valid candidate

Rejected:
  "payments-api"
  "https://api.example.com/orders-admin"
  "https://api.example.com/orders/"
  "https://api.example.com/"
  missing aud
~~~

Triển khai lần lượt qua staging/canary, đồng bộ các instance và gateway. **Không đổi AS phát token mới** trước khi mọi RS cần thiết đã nhận được audience mới; nếu không, các request sẽ đột ngột trả `401`.

### Giai đoạn 2 — Chuyển AS sang phát audience mới

Sau khi RS xác minh thành công giá trị mới:

1. Đổi mapping audience của AS từ `orders-api` sang `https://api.example.com/orders` cho resource được cấu hình.
2. Đảm bảo chỉ cấp audience mới cho **grant/client/scope hợp lệ**; client gửi giá trị tùy ý trong request không phải bằng chứng được cấp quyền.
3. Chạy canary với client được chọn, xác minh token mới được nhận bởi tất cả gateway/RS.
4. Quan sát tỷ lệ request có aud mới, lỗi `invalid_token`, audience mismatch và thời gian phát hành token cuối cùng với aud cũ.

**Mục tiêu:** từ thời điểm này, **không còn access token mới nào được phát hành với audience cũ** trong các luồng liên quan. Nếu refresh token grant tiếp tục phát access token audience cũ, migration vẫn chưa bước sang giai đoạn thu hẹp.

### Giai đoạn 3 — Đợi token cũ hết hiệu lực và xử lý client cũ

Resource Server vẫn tạm nhận cả hai audience. Cần đảm bảo mọi nguồn phát hành cũ đã ngừng, kể cả:

- Scheduled jobs, service credentials và token exchange.
- Refresh token grants, offline clients có cấu hình endpoint/resource cũ.
- Các Authorization Server instance hoặc region cấu hình không đồng bộ.
- Token sống lâu, cache introspection và clock skew.
- Resource Server chưa được triển khai/đã roll back bản cũ.

**Khoảng chờ tối thiểu không được đo chỉ bằng thời điểm triển khai AS.** Nó phụ thuộc token cũ cuối cùng được phát hành **cộng tuổi thọ tối đa còn lại, giới hạn lệch đồng hồ và các cache/chính sách liên quan**, đồng thời phải xác minh hành vi thực tế bằng telemetry.

Một refresh token có thể sống lâu hơn access token; việc này **không buộc giữ alias cũ mãi mãi** nếu AS đã chuyển tất cả lần refresh sang access token aud mới và các client tương thích. Nhưng nếu có client cũ vẫn yêu cầu token cho resource cũ và AS vẫn đáp ứng, cần sửa/gỡ đường cấp đó trước.

### Giai đoạn 4 — Ngừng chấp nhận audience cũ

Sau khi đạt điều kiện kết thúc:

- RS chỉ còn chấp nhận `https://api.example.com/orders`.
- AS từ chối hoặc chuyển đổi có kiểm soát những request chỉ đòi audience cũ, theo hợp đồng đã thống nhất.
- Gỡ cấu hình alias ở mọi instance/gateway; cập nhật tài liệu và test.
- Duy trì chỉ số phát hiện request `aud=orders-api` để biết client nào chưa migration, nhưng **không mở lại** alias không kiểm soát.

Không nên để alias tạm thành vĩnh viễn: càng nhiều giá trị được chấp nhận càng tăng bề mặt cấu hình sai và khả năng dùng nhầm token.

## 7. Sơ đồ trình tự triển khai

~~~mermaid
sequenceDiagram
    autonumber
    participant OPS as Nhóm vận hành
    participant RS as Orders Resource Server
    participant AS as Authorization Server
    participant C as OAuth Client
    OPS->>RS: Triển khai acceptedAudiences={old,new}
    RS-->>OPS: Mọi instance sẵn sàng nhận aud mới
    OPS->>AS: Chuyển phát hành sang canonical audience mới
    AS-->>OPS: Xác nhận token mới có aud mới
    C->>AS: Xin access token hợp lệ
    AS-->>C: Access token aud mới
    C->>RS: Gọi API bằng token mới
    RS-->>C: Chấp nhận nếu token + quyền hợp lệ
    Note over RS,AS: Token aud cũ còn hạn được nhận trong migration window
    OPS->>OPS: Kiểm telemetry, TTL, refresh, client/region cũ
    OPS->>RS: Gỡ legacy audience khi đã đạt điều kiện
    RS-->>OPS: Chỉ nhận canonical audience
~~~

Điểm then chốt: đây là **thay đổi hợp đồng giữa issuer và Resource Server**, không chỉ là đổi tên biến trong mã.

## 8. JWT access token: validator cần xử lý alias thế nào?

Ví dụ JWT access token trước migration:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "scope": "orders:read",
  "client_id": "shop-web",
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

Token mới, được AS phát hành sau khi đổi:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "https://api.example.com/orders",
  "scope": "orders:read",
  "client_id": "shop-web",
  "iat": 1893456000,
  "exp": 1893459600
}
~~~

Các timestamp chỉ để minh họa; khi thử thực tế phải dùng token do AS phát hành với thời gian hợp lệ.

### 8.1. Pseudocode xác minh

~~~text
function validateOrdersAccessToken(rawToken, trustedIssuer, timeNow):
    token = trustedJwtLibrary.verify(
        rawToken,
        issuer = trustedIssuer,
        trustedKeys = configuredIssuerKeys,
        allowedAlgorithms = configuredAlgorithms,
        requiredTokenProfile = "access_token",
        requiredTimeClaims = configuredTimeClaims
    )

    if token.invalid:
        reject 401

    allowedAudiences = {
        "orders-api",                      # alias tạm
        "https://api.example.com/orders"   # canonical
    }

    if token.aud is missing:
        reject 401

    if none of token.aud equals an allowed audience:
        reject 401

    if not ("orders:read" in token.scopes):
        reject 403

    if not policy.canReadOrder(token.sub, requestedOrder):
        reject 403

    accept
~~~

`token.aud` được chuẩn hóa thành danh sách chuỗi sau khi xác minh JWT; **không so khớp phần chuỗi**. Trong giai đoạn kết thúc, tập chỉ còn audience canonical.

Một thư viện JWT có thể xác minh chữ ký và thời hạn mặc định nhưng **chưa kiểm audience** nếu ứng dụng không cấu hình validator riêng. Chỉ cấu hình issuer và JWKS không đảm bảo migration an toàn.

### 8.2. Ví dụ Spring Security Resource Server

Ví dụ dưới đây minh họa phần audience validator cho JWT với issuer và JWKS **được cấu hình sẵn**. Nó giả định ứng dụng sử dụng Spring Security phù hợp và sẽ có cấu hình bảo mật endpoint, token profile và policy riêng.

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public final class AudienceMigrationDecoder {
    private AudienceMigrationDecoder() {}

    public static NimbusJwtDecoder create() {
        String issuer = "https://login.example.com";
        String jwksUri = "https://login.example.com/oauth2/jwks";

        // Chỉ dùng cho khoảng migration có kiểm soát.
        Set<String> accepted = Set.of(
            "orders-api",
            "https://api.example.com/orders"
        );

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            List<String> tokenAudiences = jwt.getAudience();
            boolean matches = tokenAudiences != null
                && tokenAudiences.stream().anyMatch(accepted::contains);

            return matches
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token",
                    "Token audience is not accepted",
                    null
                ));
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator
        ));

        return decoder;
    }
}
~~~

Giải thích giới hạn của ví dụ:

- `jwksUri` chỉ là URL minh họa, phải lấy từ cấu hình đáng tin và phù hợp issuer; cần HTTPS và quản lý key rotation.
- `JwtValidators.createDefaultWithIssuer` có nhiệm vụ xác minh các claim mặc định/issuer theo phiên bản framework; **audienceValidator** bổ sung kiểm aud chính xác.
- Không mặc định ví dụ đã giải quyết mọi yêu cầu `typ`/token purpose theo JWT access-token profile (ví dụ `at+jwt`), client/tenant/permission hoặc tất cả điều kiện thuật toán. Cần validator và cấu hình chính sách tương ứng.
- Trong production, khóa và thuật toán tin cậy, issuer, token profile, scope/authority và resource-level authorization phải được cấu hình/test riêng.
- `accepted` là tập cấu hình **có thời hạn**. Sau migration, loại `orders-api` và tiếp tục kiểm aud mới.

Nếu chỉ thay `anyMatch` bằng `jwt.getAudience().stream().anyMatch(a -> a.startsWith("https://api.example.com"))` thì đã biến allowlist chính xác thành wildcard rủi ro.

## 9. Khi token có nhiều audience

JWT cho phép `aud` là mảng:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": [
    "orders-api",
    "https://api.example.com/orders"
  ],
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

Một token có hai audience nghĩa là issuer **đang chỉ định nhiều bên nhận** theo hợp đồng. Không nên tự sửa token để thêm cả hai giá trị, và **không cần cấp token hai audience** chỉ để RS chấp nhận old/new: thông thường AS phát **một audience** tại một thời điểm, còn RS chấp nhận hai audience trong giai đoạn chuyển tiếp.

Lý do nên thận trọng với multi-audience token:

1. Nếu hai chuỗi thực sự là alias cùng Resource Server, token có thể tương thích; nhưng vẫn làm tăng nghĩa vụ kiểm soát.
2. Nếu hai audience thuộc **hai API độc lập** (`orders-api` và `payments-api`), bearer token có thể sử dụng ở cả hai; cần đánh giá kỹ nguy cơ rò token giữa tài nguyên, scope và trust boundary.
3. Không được coi `aud` là scope. Có hai audience không có nghĩa mọi hành động tại hai API đều được cho phép.
4. Nếu policy của một Resource Server yêu cầu **một audience duy nhất** để giảm token substitution, token có nhiều audience phải bị từ chối theo policy đó dù một phần tử có vẻ khớp.

**Khuyến nghị thiết kế:** trong migration đổi tên đơn thuần, để RS nhận hai tên nhưng AS ưu tiên cấp access token **chỉ với canonical audience mới**.

## 10. Opaque access token và migration audience

Không phải mọi access token là JWT. Với opaque token, Resource Server có thể dùng **OAuth 2.0 Token Introspection (RFC 7662)** hoặc lookup đáng tin cậy để nhận trạng thái và metadata.

Ví dụ phản hồi introspection trước migration:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "scope": "orders:read",
  "client_id": "shop-web",
  "exp": 1893456000
}
~~~

Sau migration, AS có thể trả `aud = "https://api.example.com/orders"` cho access token mới. RS áp dụng **cùng tập accepted audiences hữu hạn** với các thông tin đã được xác thực từ introspection.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant RS as Orders Resource Server
    participant AS as Authorization Server
    C->>RS: Bearer opaque access token
    RS->>AS: Introspection qua TLS, RS được xác thực
    AS-->>RS: active, iss, aud, scope, expiry...
    RS->>RS: Kiểm active + issuer/profile + accepted audience
    RS->>RS: Kiểm scope và quyền trên tài nguyên
    RS-->>C: 200 / 401 / 403
~~~

**`active=true` chưa đủ.** Token có thể active nhưng dành cho `payments-api` hoặc thiếu `orders:read`. Introspection có thể trả metadata khác nhau tùy AS và quyền của bên gọi; phải có hợp đồng rõ ràng về audience và loại token.

### 10.1. Cẩn thận với cache introspection

Khi migration:

- Cache có thể giữ metadata audience cũ cho token còn hiệu lực.
- Sau khi AS đổi phát hành, RS phải chấp nhận metadata cũ trong khoảng chuyển tiếp.
- Khi thu hồi token hoặc xóa alias, cache `active=true` có thể giữ trạng thái cũ nếu TTL quá dài.
- Không cho phép **cache miss hoặc AS không sẵn sàng** khiến API bỏ kiểm audience. Nếu thiếu thông tin đáng tin để quyết định, **fail closed**.

API Gateway thực hiện introspection tập trung cũng phải có phiên bản alias policy đúng. Downstream không tin header `X-Audience`, `X-User` hoặc `X-Scope` do caller bên ngoài tự gửi.

## 11. AS phát audience mới: resource indicators và client migration

Trong OAuth 2.0, client có thể cần chỉ định Resource Server mà mình muốn gọi. **RFC 8707 — Resource Indicators for OAuth 2.0** định nghĩa tham số `resource` cho một số yêu cầu cấp token.

Ví dụ yêu cầu authorize minh họa:

~~~http
GET /authorize?response_type=code&
    client_id=shop-web&
    redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
    scope=orders%3Aread&
    resource=https%3A%2F%2Fapi.example.com%2Forders&
    state=opaque-state&
    code_challenge=challenge&
    code_challenge_method=S256
Host: login.example.com
~~~

Tham số `resource` phải được AS kiểm theo đăng ký/chính sách. **Client không được quyết định `aud` của JWT bằng cách gửi một chuỗi tùy ý rồi khiến AS cấp quyền cho tài nguyên đó.** AS có thể ánh xạ `resource` sang canonical audience; không bắt buộc `resource` và `aud` phải có chuỗi giống nhau trong mọi triển khai.

Khi đổi audience:

1. Client được cập nhật để gửi resource indicator mới nếu AS dùng cơ chế này.
2. AS kiểm client được phép yêu cầu tài nguyên đích.
3. AS phát access token với audience theo mapping đã chốt.
4. RS xác minh audience được phát hành, không dựa vào tham số resource chưa được AS chấp thuận.

**Không dùng refresh token làm access token của API**. Nếu AS cho phép refresh grant yêu cầu resource cụ thể, AS vẫn phải ràng buộc audience/scope với grant và chính sách; refresh token không phải giấy phép xin access token tới bất kỳ API nào.

### 11.1. OAuth scope không thay audience

Scope `orders:read` có thể được cấp cho token có `aud=payments-api` vì issuer cấu hình sai hoặc dùng namespace quyền chung. Orders API vẫn phải từ chối token sai audience dù chuỗi scope trùng. Ngược lại, token aud đúng nhưng scope thiếu cũng phải bị từ chối.

## 12. Khi nào cần token exchange thay vì alias?

Giả sử trước đây `monolith-api` chứa cả đơn hàng và thanh toán. Sau khi tách:

~~~text
Monolith API -> Orders Service (aud=orders-api)
            -> Payments Service (aud=payments-api)
~~~

Nếu cả hai service mới chấp nhận vĩnh viễn `aud=monolith-api`, một token cũ có quyền rộng có thể tiếp tục đi qua cả hai và phá giới hạn quyền mới. **Đây là thay đổi ranh giới tài nguyên**, không đơn thuần là đổi tên.

Các hướng xử lý:

- AS cấp access token riêng cho từng Resource Server với audience và scope tối thiểu.
- Gateway/BFF yêu cầu token đúng audience cho backend tương ứng.
- Khi cần gọi B thay mặt người dùng hoặc dịch vụ, có thể dùng **OAuth 2.0 Token Exchange (RFC 8693)** nếu AS hỗ trợ và policy cho phép; token mới phải giới hạn audience/scope phù hợp.
- Giai đoạn chuyển đổi legacy token cần thời gian ngắn, điều kiện riêng, theo dõi và chặn lạm dụng quyền.

**Không mặc định** gateway có thể chuyển một bearer token audience `orders-api` vào Payments API rồi Payments API bỏ kiểm aud vì “cùng hệ thống”. Chuyển tiếp token giữa các API chỉ an toàn khi có cơ chế ủy quyền được thiết kế cho đúng resource.

## 13. Audience alias, client identity, ID token và tenant

### 13.1. ID token không nằm trong alias của API

Một ID token OIDC có thể có:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "shop-web",
  "azp": "shop-web",
  "exp": 1893453000
}
~~~

OIDC Client `shop-web` xác minh ID token theo OIDC. Orders API cần **access token** có audience của Orders API; nó không được thêm `shop-web` vào accepted audiences của Resource Server chỉ để nhận ID token. `azp` (*authorized party*) cũng không làm ID token có quyền gọi API.

### 13.2. `client_id` và `aud` khác nhau

`client_id=shop-web` nói về ứng dụng gắn với việc xin token. `aud=orders-api` nói về API nhận token. Khi migration, thay đổi audience **không buộc client ID đổi**, trừ khi có thay đổi đăng ký ứng dụng riêng.

Nếu API có client allowlist, kiểm `client_id` từ token/metadata **sau validation**, cùng issuer và chính sách. Client ID không tự chống token replay vì bearer token bị đánh cắp vẫn giữ nguyên claim đó.

### 13.3. Tenant không phải audience

Một access token cho `orders-api` có thể mang ngữ cảnh `tenant=beta` theo hợp đồng hệ thống. Audience alias chỉ giải quyết định danh **API nhận token**; API vẫn phải kiểm membership, role, tenant và quyền trên dữ liệu cụ thể. Alias `orders-api` không tự trao quyền truy cập mọi tenant.

### 13.4. JWKS rotation không đồng nghĩa audience migration

**Key rotation** thay khóa xác minh; **audience migration** thay định danh bên nhận. Hai việc có thể diễn ra độc lập. Trộn cả hai thay đổi cùng một đợt sẽ khó xác định nguyên nhân lỗi `401`. Nếu phải làm cùng nhau, cần kế hoạch kiểm thử, quan sát và rollback riêng cho issuer/khóa và audience.

## 14. Telemetry và điều kiện gỡ alias

Để biết migration đã hoàn tất, cần số liệu **không tiết lộ token**:

| Chỉ số | Mục đích |
|---|---|
| Số token AS phát theo `issuer + audience + grant/client` | Xác nhận AS ngừng cấp audience cũ, bao gồm refresh và service token. |
| Request theo audience đã **xác minh** tại RS | Theo dõi token cũ còn được sử dụng; không dựa vào payload chưa verify. |
| Tỷ lệ `401 invalid_token`, audience mismatch | Phát hiện RS chưa triển khai hoặc client yêu cầu sai resource. |
| Lỗi `403 insufficient_scope` / authorization | Phân biệt lỗi quyền với lỗi audience. |
| Tuổi thọ tối đa của token cũ | Tính thời điểm an toàn để gỡ alias. |
| Cache TTL tại gateway/RS và introspection | Tránh nhận nhầm token cũ do cache giữ quá lâu. |
| Client/region vẫn tạo request với aud cũ | Xác định nơi cần nâng cấp trước ngày ngừng hỗ trợ. |
| Phiên bản cấu hình verifier tại từng RS | Kiểm mọi instance nhận canonical audience trước khi AS chuyển cấp. |

**Không log nguyên access/refresh token** hoặc header `Authorization`. Nếu cần phân tích token, chỉ log metadata đã xác minh và được phép lưu, với chính sách bảo vệ dữ liệu phù hợp.

### 14.1. Điều kiện nên đạt trước khi xóa alias cũ

1. AS đã ngừng cấp audience cũ ở **mọi môi trường/region/luồng liên quan**.
2. Đã đi qua tuổi thọ còn lại tối đa của token cũ cộng giới hạn clock skew/cache liên quan.
3. Client, job, service và gateway hiện dùng canonical audience.
4. Không còn traffic hợp lệ với aud cũ trong khoảng quan sát đã quy định.
5. Bộ test âm tính xác minh audience cũ bị từ chối sau khi gỡ; audience khác cũng tiếp tục bị từ chối.
6. Rollback đã được xác định rõ và có bản ghi thay đổi/chủ sở hữu để xử lý nếu xuất hiện client chưa nâng cấp.

Nếu không thể chứng minh thời hạn tồn tại của một loại token, **đừng giả định nó đã hết hạn**; cần xử lý thu hồi hoặc thỏa thuận cắt chuyển có thông báo rõ.

## 15. Rollback và xử lý sự cố

### 15.1. AS vừa đổi audience, một số RS chưa nhận được

Triệu chứng: token mới có aud canonical nhưng các instance RS cũ trả `401`. Hướng xử lý:

1. Xác nhận lỗi audience mismatch qua metadata/log an toàn.
2. Roll back **việc AS phát hành** về aud cũ nếu RS vẫn nhận aud cũ, hoặc đẩy bản verifier hỗ trợ canonical tới các instance thiếu.
3. Không mở rule wildcard hoặc tắt kiểm audience để “chữa cháy”.
4. Sau khi đồng bộ RS, tái triển khai cấp token mới theo canary và quan sát.

### 15.2. Token aud cũ vẫn xuất hiện sau thời điểm dự kiến

Xác định nguồn cấp: refresh grant, service account, partner AS, worker chưa nâng cấp hay instance cũ. Nếu AS còn cấp aud cũ, **chưa bắt đầu đếm hết TTL kể từ lần cuối cấp**. Dùng telemetry tại AS và thông tin issuer/client đáng tin; không chỉ đo số request API.

### 15.3. Phát hiện token một API được dùng ở API khác

Đây là sự cố ranh giới tin cậy. Kiểm tra alias collision, cấu hình verifier, token profile, issuer và audience. Thu hẹp accepted audience về tập chính xác; nếu có token bị lạm dụng, áp dụng thu hồi và xử lý sự cố theo chính sách. **Không duy trì alias vì mục tiêu tương thích khi nó làm mất phân tách an ninh.**

### 15.4. Hệ thống bị rollback giữa chừng

Để rollback được:

- Trong giai đoạn đầu, RS có thể vẫn nhận **cả hai** audience.
- Chỉ cần đảo AS phát token về giá trị cũ khi verifier vẫn chấp nhận giá trị đó.
- Nếu đã gỡ legacy audience khỏi RS, rollback AS về phát token cũ sẽ gây lỗi `401`; phải có kế hoạch triển khai verifier tương thích trở lại, đồng thời đánh giá an ninh trước khi tái mở alias.
- Không khôi phục nguyên mọi rule cũ khi có dấu hiệu alias gây token substitution.

## 16. Ma trận test migration

Giả sử Order Service có issuer `https://login.example.com`, audience cũ `orders-api`, audience mới `https://api.example.com/orders`. Trong migration, RS nhận hai chuỗi này và endpoint đọc đơn yêu cầu `orders:read`.

| Token / request | Trong migration | Sau khi gỡ alias | Vì sao |
|---|---|---|---|
| JWT issuer/chữ ký hợp lệ, `aud=orders-api`, scope đủ, quyền đủ | Cho phép | Từ chối | Alias cũ chỉ được nhận tạm thời. |
| JWT hợp lệ, `aud=https://api.example.com/orders`, scope đủ, quyền đủ | Cho phép | Cho phép | Audience canonical. |
| JWT hợp lệ, `aud=payments-api` | Từ chối | Từ chối | Sai Resource Server. |
| JWT hợp lệ, `aud=https://api.example.com/orders-admin` | Từ chối | Từ chối | Không khớp chuỗi chính xác. |
| JWT hợp lệ, `aud=https://api.example.com/orders/` | Từ chối | Từ chối | Dấu `/` khác biệt; chưa khai báo alias. |
| JWT đúng aud nhưng chữ ký sai | Từ chối | Từ chối | Không được đọc claims chưa tin cậy. |
| JWT đúng aud nhưng `iss` của issuer khác | Từ chối | Từ chối | Cấu hình nguồn phát hành. |
| JWT đúng aud nhưng đã hết hạn | Từ chối | Từ chối | Token không còn hiệu lực. |
| JWT đúng aud nhưng chỉ có `orders:read`, gọi DELETE | Từ chối | Từ chối | Thiếu scope/quyền nghiệp vụ. |
| JWT đúng aud/scope nhưng đơn thuộc tenant khác | Từ chối | Từ chối | Object/tenant authorization. |
| ID token `aud=shop-web` từ cùng OP | Từ chối | Từ chối | Sai token purpose/audience. |
| Opaque token introspection `active=false` | Từ chối | Từ chối | Token không active. |
| Opaque token `active=true`, aud mới, đủ scope/quyền | Cho phép | Cho phép | Introspection/metadata và quyền hợp lệ. |
| Token aud cũ được refresh thành aud mới | Cho phép theo token mới | Cho phép theo token mới | Refresh token không bị đưa tới API; AS cấp lại access token. |
| Token có `aud=[orders-api,payments-api]` | Theo policy đa audience đã thẩm định | Theo policy sau gỡ alias | Tránh vô tình mở quyền giữa hai tài nguyên. |

**Kiểm tra bổ sung:** multi-instance rollout, stale cache, key rotation, clock skew, client chưa cập nhật `resource`, token exchange, rollback AS và token còn sống sau logout.

### 16.1. Kiểm thử chống chấp nhận sai chuỗi

Dùng test tự động để chứng minh implementation không chấp nhận nhầm:

~~~text
assertAccepts("orders-api")                     # chỉ trong migration
assertAccepts("https://api.example.com/orders")
assertRejects("payments-api")
assertRejects("https://api.example.com/orders/")
assertRejects("https://api.example.com/orders-admin")
assertRejects("https://api.example.com/")
assertRejects("ORDERS-API")
assertRejects("")
assertRejects(null)
~~~

Các hàm là pseudocode và **giả định các claim khác đều hợp lệ**; mục tiêu test là riêng logic audience alias. Sau migration, đổi `assertAccepts("orders-api")` thành `assertRejects("orders-api")`.

## 17. Bài thực hành: thiết kế kế hoạch migration

Đề bài: SaaS hiện dùng access token JWT có `aud=inventory-api`. Đội kỹ thuật muốn đổi canonical audience thành `https://api.example.com/inventory`. Token sống tối đa 20 phút; clock skew cho phép tối đa 60 giây. Hệ thống có ba Resource Server instance, một gateway, client web và một worker chạy theo lịch.

Hãy trả lời:

1. **Cần triển khai ở đâu trước?** Ở gateway/RS/verifier liên quan để nhận hai audience; kiểm tất cả instance trước khi AS phát token mới.
2. **Có cần đổi ngay mọi client không?** Chỉ khi client yêu cầu resource/audience theo hợp đồng có liên quan. Chuyển AS và client phải có kế hoạch phối hợp; client không tự quyết token được cấp.
3. **Sau khi AS ngừng cấp aud cũ, chờ đúng 20 phút có đủ chưa?** Chưa chắc. Cần tính từ **token cũ cuối cùng** được cấp, cộng thời gian lệch đồng hồ có thể áp dụng và cache/trạng thái; xác nhận không có đường phát token cũ.
4. **Worker còn xin token aud cũ thì sao?** Cập nhật worker hoặc mapping AS; chỉ bắt đầu cửa sổ loại alias khi nguồn cấp cũ thực sự dừng.
5. **Có thể chấp nhận `inventory-api-v2` bằng rule `startsWith("inventory-api")` không?** Không; cần danh sách alias chính xác, được xét duyệt.
6. **Nếu tương lai inventory API tách thành inventory-read và inventory-admin thì dùng lại alias cũ cho cả hai có ổn không?** Không tự động. Cần đánh giá ranh giới và cấp audience/scope/permissions riêng; khi cần dùng token exchange.

### 17.1. Bài tập phản biện thiết kế

Một đồng nghiệp đề xuất:

~~~text
if token.signatureValid && token.iss == trustedIssuer:
    if token.aud.contains("api"):
        allowRequest()
~~~

Tìm ít nhất năm vấn đề. Gợi ý:

- `contains("api")` không phải so khớp audience chính xác.
- Không kiểm `exp`/`nbf`, token purpose/profile và các claim bắt buộc.
- Không kiểm scope của endpoint.
- Không kiểm quyền tài nguyên và tenant.
- Coi token do cùng issuer cấp là đủ để dùng tại mọi API.
- Không có chính sách chấp nhận/gỡ audience alias.
- Không xử lý token bị thu hồi hoặc replay nếu hệ thống yêu cầu trạng thái bổ sung.

Hãy viết lại thành điều kiện token validation, danh sách audience hữu hạn theo issuer và bước authorization tách biệt.

## 18. Checklist thực thi

- [ ] Đã xác định **canonical audience**, **legacy alias**, issuer và Resource Server đích bằng định danh chính xác.
- [ ] Đã thẩm định hai audience thực sự chỉ cùng một ranh giới API/quyền.
- [ ] Trình xác minh JWT hoặc introspection kiểm đúng issuer, token purpose, aud, thời gian, chữ ký/trạng thái.
- [ ] Không có wildcard, prefix, suffix hoặc case-insensitive matching không được cho phép.
- [ ] Đã cập nhật verifier ở **mọi instance/gateway** trước khi AS đổi phát hành.
- [ ] AS kiểm resource indicator/client/grant và chỉ cấp audience mới theo chính sách.
- [ ] Client, service worker, refresh/token-exchange path được kiểm để không tiếp tục phát token aud cũ.
- [ ] Đã xác định max TTL, cache, clock skew và thời điểm token cũ cuối cùng được phát hành.
- [ ] Có telemetry audience theo metadata được xác minh mà không log token thô.
- [ ] Có giới hạn thời gian, chủ sở hữu, tiêu chí kết thúc và kế hoạch rollback cho alias.
- [ ] Sau migration, đã gỡ legacy audience và kiểm lại trường hợp token cũ bị từ chối.
- [ ] Có test cross-API token substitution, sai issuer, sai chữ ký, ID token, thiếu scope và sai quyền tài nguyên.
- [ ] Các rủi ro refresh token, thu hồi, bearer replay và multi-tenant authorization vẫn được xử lý độc lập.

**Ghi nhớ:** Audience alias là **ngoại lệ có kiểm soát** cho quá trình chuyển đổi định danh bên nhận access token. Để migration an toàn, Resource Server tạm chấp nhận **chính xác** tên cũ và mới sau khi đã xác nhận cùng ranh giới quyền; Authorization Server chuyển sang phát tên mới; hệ thống quan sát token cũ đến khi hết hạn và loại alias. **Không đánh đổi kiểm `aud`, scope, issuer hoặc quyền tài nguyên để đạt tương thích.**

### Tài liệu chuẩn để tra cứu

- **RFC 7519 — JSON Web Token (JWT):** `aud` và quy tắc biểu diễn audience.
- **RFC 8725 — JSON Web Token Best Current Practices:** xác minh audience, chống token substitution/confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT access token và xác minh Resource Server.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Server, Resource Server, access/refresh token và scope.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** sử dụng bearer access token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active` và metadata của opaque access token.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** tham số `resource` và chỉ định Resource Server.
- **RFC 8693 — OAuth 2.0 Token Exchange:** cấp token mới cho resource/actor khi cần.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** giới hạn audience/scope và phòng chống lạm dụng.
- **OpenID Connect Core 1.0:** đối chiếu audience của ID token với client, phân biệt với audience của access token.
