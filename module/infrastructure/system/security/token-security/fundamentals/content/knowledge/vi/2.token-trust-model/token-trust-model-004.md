# Resource server tin cậy key hoặc introspection endpoint nào?

## 1. Vấn đề cốt lõi: tin cậy một nguồn phát hành, không tin cậy chuỗi token

Trong OAuth 2.0, **resource server** là API giữ tài nguyên được bảo vệ, ví dụ `orders-api`. Client gửi một **access token** để yêu cầu truy cập API. Token có thể ở dạng JWT tự chứa các claims hoặc là chuỗi **opaque** mà API không tự giải nghĩa. Trong cả hai trường hợp, câu hỏi bảo mật đầu tiên là:

> **Ai được phép khẳng định token này hợp lệ và dành cho API của tôi?**

Resource server phải có **cấu hình tin cậy được thiết lập trước**: authorization server (AS) nào được phép phát hành access token cho API, issuer nào được chấp nhận, khóa công khai/JWKS nào thuộc issuer đó, hoặc endpoint introspection nào là nguồn trả lời có thẩm quyền. Cấu hình này đến từ triển khai, hợp đồng giữa các hệ thống hoặc cơ chế khám phá metadata đã được kiểm chứng; không lấy từ địa chỉ do client tự đưa trong request.

Hai cách xác minh phổ biến:

| Access token | Nguồn mà resource server tin cậy | Cách xác minh |
| --- | --- | --- |
| **JWT ký số** | Issuer đã cho phép và bộ **public key/JWKS** được issuer đó công bố | Kiểm tra chữ ký **tại API**, rồi kiểm tra `iss`, `aud`, thời gian, loại token và quyền |
| **Opaque token** | **Introspection endpoint** đã cấu hình của AS có thẩm quyền | Gửi token đến endpoint qua kết nối được bảo vệ, xác thực chính resource server, dùng phản hồi `active` cùng các ràng buộc tài nguyên/quyền |

Một JWT có chữ ký đúng từ *một* khóa bất kỳ chưa đủ đáng tin. Một phản hồi `active: true` từ *một* URL bất kỳ cũng chưa đủ đáng tin. **Danh tính và quyền hạn của nguồn xác minh** là mắt xích quyết định.

### Mục tiêu sau bài học

- Xác định được issuer, JWKS và introspection endpoint mà resource server được phép tin.
- Phân biệt xác minh chữ ký JWT với xác minh trạng thái token qua introspection.
- Giải thích được vì sao `kid`, `alg`, `iss`, `jku` hay `x5u` trong token không tự tạo ra quyền tin cậy.
- Thiết kế kiểm tra audience, scope, thời hạn, thu hồi token và phân quyền nghiệp vụ cho một API thực tế.

## 2. Sơ đồ ranh giới tin cậy

~~~mermaid
flowchart TB
    C["Client gửi access token"] --> RS["Resource server: orders-api"]
    CONF["Cấu hình tin cậy do đội triển khai quản lý"] --> RS
    RS --> MODE{"Hình thức xác minh"}
    MODE -->|"JWT đã ký"| JWKS["JWKS của issuer được phép"]
    JWKS --> LOCAL["Kiểm tra chữ ký + claims tại API"]
    MODE -->|"Opaque token"| INTRO["Introspection endpoint được phép"]
    INTRO --> REMOTE["Kiểm tra active + claims/ràng buộc tại API"]
    LOCAL --> POLICY["Kiểm tra scope và quyền trên tài nguyên"]
    REMOTE --> POLICY
    POLICY --> DECISION{"Cho phép truy cập?"}
    DECISION -->|"Đủ điều kiện"| YES["Trả tài nguyên"]
    DECISION -->|"Thiếu điều kiện"| NO["Từ chối"]
~~~

Luồng trên có **hai lớp quyết định**:

1. **Authentication/token validation**: token có xuất phát từ nguồn được tin cậy, còn hiệu lực, dành cho `orders-api` và thực sự là access token không?
2. **Authorization**: token có scope/role cần thiết và chủ thể có quyền thao tác trên đơn hàng cụ thể không?

Chữ ký hợp lệ hoặc `active: true` chỉ giúp vượt qua một phần lớp thứ nhất; chúng không tự cấp quyền đọc mọi đơn hàng.

## 3. Nguồn tin cậy ban đầu đến từ đâu?

Giả sử hệ thống có:

- API: `orders-api`.
- Authorization server được phê duyệt: `https://auth.example.test`.
- Issuer kỳ vọng: `https://auth.example.test`.
- JWKS URI của issuer: `https://auth.example.test/oauth2/jwks`.
- Introspection URI của issuer: `https://auth.example.test/oauth2/introspect`.
- Audience mà API chấp nhận: `orders-api`.

Các địa chỉ trên là **ví dụ cấu hình**, không phải địa chỉ mặc định của OAuth. AS thực tế có thể dùng endpoint khác. Resource server biết các giá trị này từ cấu hình tin cậy hoặc metadata đã kiểm chứng, chẳng hạn tài liệu khám phá OpenID Connect/OAuth Authorization Server Metadata. Khi sử dụng discovery, cần xác minh trường `issuer` trong metadata trùng chính xác với issuer dự kiến, rồi mới chấp nhận `jwks_uri` do metadata đó công bố.

**Chuỗi tin cậy hợp lệ:**

1. Đội vận hành cấu hình một issuer được chấp nhận, hoặc một danh sách issuer rõ ràng cho nhiều tenant.
2. Resource server truy cập metadata/JWKS hoặc introspection endpoint của issuer đó qua HTTPS, với kiểm tra chứng chỉ TLS phù hợp.
3. Resource server chỉ xác minh token và chấp nhận claims theo **chính sách của API**.

**Chuỗi tin cậy sai:**

1. Client gửi JWT có header `jku: https://evil.example/keys.json`.
2. Resource server tải khóa từ URL này và thấy chữ ký hợp lệ.
3. Resource server chấp nhận token dù chưa từng tin issuer kiểm soát URL trên.

Ở trường hợp sai, kẻ tấn công có thể tự tạo khóa và ký token của chính mình. Việc xác minh chữ ký về mặt toán học vẫn thành công, nhưng **không chứng minh quyền phát hành**. Nguyên tắc chung: **token là dữ liệu đầu vào không đáng tin cho tới khi được xác minh đầy đủ**.

## 4. Nhánh JWT: Resource server tin khóa nào?

### 4.1. Khóa đáng tin là khóa gắn với issuer được phép

JWT ký số thường có ba phần `header.payload.signature`. Header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "prod-key-2026-11",
  "typ": "at+jwt"
}
~~~

`kid` chỉ là **mã định danh để chọn khóa** trong tập khóa đã tin cậy. Nó không phải chứng chỉ, cũng không phải bằng chứng issuer hợp lệ. Hai issuer độc lập có thể dùng cùng một `kid`; bộ nhớ đệm khóa phải được phân vùng theo issuer hoặc trust configuration.

Với chữ ký bất đối xứng như RSA/ECDSA, AS giữ **private key** để ký; resource server nhận **public key** từ JWKS để kiểm tra. Không chia sẻ private key cho API. Nếu dùng HMAC/khóa đối xứng, bên xác minh cũng giữ bí mật có khả năng ký token; điều đó mở rộng phạm vi bên có thể phát hành token, nên mô hình này đòi hỏi thỏa thuận tin cậy chặt chẽ hơn và ít phù hợp với nhiều resource server độc lập.

Một JWK có thể mang `kty`, `kid`, `use`, `alg` và tham số khóa như `n`, `e` cho RSA. Các trường này dùng để chọn/diễn giải khóa **trong JWKS đã tin cậy**, không dùng để mở rộng danh sách issuer.

### 4.2. Chuỗi kiểm tra JWT an toàn

1. **Xác định chính sách của API**: issuer nào được phép, audience nào hợp lệ, loại access token và thuật toán ký nào được chấp nhận. Với đa tenant, có thể dùng `iss` chưa xác minh làm *gợi ý tra danh sách issuer đã được cho phép*, nhưng tuyệt đối không lấy giá trị đó để truy cập tùy ý một máy chủ mới.
2. **Lấy khóa từ nguồn cố định/được kiểm chứng**: `jwks_uri` thuộc issuer đã tin cậy; kết nối HTTPS hợp lệ. Không tự động theo URL `jku`/`x5u` trong token.
3. **Kiểm tra header trong giới hạn chính sách**: `alg` phải nằm trong danh sách cho phép; không chấp nhận `none` hoặc đánh tráo RS256/HS256. `kid` chỉ được tìm trong tập khóa đúng issuer và đúng thuật toán/loại khóa.
4. **Xác minh chữ ký bằng thư viện bảo mật đáng tin**. Không tự xây thuật toán JWT. Nếu không tìm được khóa phù hợp, có thể làm mới JWKS theo chính sách giới hạn tần suất; vẫn phải từ chối token nếu không xác minh được.
5. **Kiểm tra claims**: `iss` khớp issuer; `aud` chứa `orders-api`; `exp` chưa hết hạn; `nbf` không ở tương lai; áp dụng giới hạn đồng hồ lệch nhỏ và kiểm tra `iat`/tuổi token nếu hệ thống yêu cầu. Kiểm tra `typ`/token profile khi áp dụng (ví dụ JWT access token theo RFC 9068).
6. **Kiểm tra đúng mục đích**: API chỉ nhận **access token** phù hợp; không dùng ID token dành cho client OIDC hoặc refresh token để gọi API.
7. **Kiểm tra quyền**: scope, role, tenant, chủ sở hữu tài nguyên, quy tắc nghiệp vụ. Scope trong token là dữ liệu được AS xác nhận, không tự thay thế kiểm tra quyền đối với bản ghi.

Không thể kết luận một JWT **chưa bị thu hồi** chỉ từ chữ ký, `exp` và các claims. JWT được xác minh ngoại tuyến có thể tiếp tục hợp lệ tới lúc hết hạn nếu không có cơ chế thu hồi hoặc kiểm tra trạng thái bổ sung.

### 4.3. Khác biệt giữa `iss`, `aud`, `kid` và `scope`

| Trường | Câu hỏi nó giải quyết | Quy tắc sử dụng |
| --- | --- | --- |
| `iss` (issuer) | Ai tuyên bố đã phát hành token? | Phải khớp **issuer trong cấu hình tin cậy** sau xác minh |
| `aud` (audience) | Token dành cho API/dịch vụ nào? | Phải chứa định danh tài nguyên mà API chấp nhận |
| `kid` (key ID) | Chọn public key nào trong JWKS của issuer? | Chỉ dùng để tra khóa trong tập khóa đã tin |
| `alg` | Thuật toán chữ ký nào? | Phải khớp allowlist và loại khóa, không để token tự quyết định chính sách |
| `exp`, `nbf`, `iat` | Token hợp lệ vào khoảng thời gian nào? | Kiểm tra hết hạn, chưa có hiệu lực và giới hạn tuổi theo chính sách |
| `scope` hoặc `scp` | Những quyền API nào được ủy quyền? | Chuẩn hóa theo hợp đồng issuer, sau đó kiểm tra quyền theo endpoint |
| `sub`, `client_id` | Chủ thể và client nào liên quan? | Dùng đúng ngữ nghĩa của token và tiếp tục áp dụng phân quyền nghiệp vụ |

Ví dụ: Một ID token OIDC có chữ ký đúng của `https://auth.example.test` nhưng `aud = web-client` **không hợp lệ cho** `orders-api`. Ngay cả access token có `aud = billing-api` và `scope = orders.read` cũng không được dùng tại `orders-api`, vì audience không khớp.

### 4.4. Xoay vòng khóa (key rotation) và cache

AS có thể công bố đồng thời khóa cũ và mới trên JWKS trong giai đoạn chuyển đổi. Resource server nên cache JWKS có kiểm soát, làm mới khi đến hạn và có thể làm mới khi gặp `kid` lạ, nhưng phải giới hạn tần suất làm mới để tránh bị lợi dụng gây quá tải.

Quy trình triển khai thường là: **công bố public key mới → cho resource server cơ hội đồng bộ → bắt đầu ký bằng private key mới → chờ token ký bằng khóa cũ hết hạn → loại khóa cũ**. Thu hồi khẩn cấp khóa bị lộ có thể yêu cầu loại khóa nhanh hơn và từ chối token cũ; đây là lựa chọn bảo mật có thể ảnh hưởng tính sẵn sàng.

JWKS cache không biến khóa tùy ý thành đáng tin. Khi JWKS không truy cập được, resource server chỉ có thể xác minh bằng khóa đã cache còn phù hợp với chính sách; nếu không đủ cơ sở xác minh, phải **từ chối xác thực**.

## 5. Nhánh opaque: Resource server tin introspection endpoint nào?

Opaque access token là chuỗi mà resource server **không có hợp đồng để tự diễn giải**. Nó có thể trông giống chuỗi ngẫu nhiên hoặc thậm chí có dấu chấm, nhưng hình thức không quyết định cách xác minh. Theo hợp đồng triển khai, resource server gửi token đến **introspection endpoint của AS có thẩm quyền** (RFC 7662).

Endpoint này phải được cấu hình sẵn hoặc lấy từ metadata của issuer đã tin cậy. Resource server dùng HTTPS và thường **xác thực chính mình** bằng thông tin xác thực riêng như client credentials hoặc một phương thức được AS hỗ trợ. Client gửi bearer token cho API **không được chọn endpoint introspection**, cũng không được cung cấp thông tin xác thực thay cho resource server.

Ví dụ minh họa yêu cầu:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <thong-tin-xac-thuc-cua-resource-server>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
~~~

AS có thể trả về:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "client_id": "web-frontend",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "token_type": "Bearer",
  "exp": 1795403600
}
~~~

Đây là **ví dụ** về phản hồi; theo RFC 7662, `active` là trường cốt lõi, còn nhiều trường khác là tùy chọn theo AS và chính sách truy cập. Nếu AS không cung cấp `aud`, resource server vẫn phải có **hợp đồng bảo đảm token được phát hành/được xác nhận cho đúng tài nguyên**; không được suy ra rằng mọi token `active: true` đều dùng được trên mọi API.

Quy trình kiểm tra:

1. Chỉ gọi **endpoint cố định của AS được phép** qua TLS và xác thực resource server đúng cấu hình.
2. Nếu phản hồi `active: false`, hoặc token không được AS công nhận cho API này, từ chối.
3. Nếu `active: true`, tiếp tục kiểm tra issuer, audience/resource binding, thời hạn, loại token, scope, chủ thể và chính sách phân quyền theo dữ liệu AS trả về và hợp đồng tích hợp.
4. Nếu introspection endpoint lỗi, timeout hoặc không xác thực được phản hồi, **không chuyển sang cho phép truy cập**. Chọn mã lỗi vận hành phù hợp và quan sát sự cố, nhưng vẫn fail closed.

**Lưu ý:** `active: true` là phát biểu về trạng thái token trong ngữ cảnh mà AS nhận biết, không phải quyết định cuối cùng rằng người dùng có quyền đọc đơn hàng 123.

### 5.1. Cache introspection và thu hồi token

Gọi introspection mỗi request giúp resource server nhìn thấy thay đổi trạng thái nhanh hơn nhưng tạo thêm độ trễ và phụ thuộc vào AS. Cache phản hồi có thể giảm tải, song tạo một **cửa sổ token bị thu hồi vẫn được chấp nhận** cho đến khi cache hết hiệu lực.

Chính sách cache nên cân nhắc độ nhạy endpoint, thời hạn token và yêu cầu thu hồi; TTL không được kéo dài vượt quá `exp` khi có trường đó. Không cache vô thời hạn phản hồi `active: true`. Với token bị đánh cắp hoặc quyền vừa bị rút, khác biệt giữa cache vài giây và vài phút có thể ảnh hưởng trực tiếp tới thiệt hại.

Opaque token **không mặc nhiên bảo đảm thu hồi tức thì**: điều này còn phụ thuộc khả năng AS đánh dấu inactive, tần suất introspection và chính sách cache.

## 6. So sánh và lựa chọn theo yêu cầu hệ thống

| Tiêu chí | JWT xác minh bằng JWKS | Opaque xác minh bằng introspection |
| --- | --- | --- |
| Kiểm tra mỗi request | Thường có thể thực hiện cục bộ | Thường cần gọi AS, trừ khi có cache |
| Phụ thuộc AS khi API đang chạy | Chủ yếu khi lấy/làm mới JWKS | Cao hơn khi cần introspection trực tiếp |
| Thu hồi trước `exp` | Cần cơ chế bổ sung như denylist, introspection hoặc token sống ngắn | AS có thể trả `active: false`; độ trễ phụ thuộc cache |
| Claims người cầm token có thể đọc | Payload JWT thường đọc được, dù đã ký | Nội dung token không nhất thiết lộ claims |
| Độ phức tạp bảo vệ nguồn tin cậy | Issuer, metadata, JWKS, thuật toán, rotation | Endpoint, xác thực resource server, timeout/cache |
| Kiểm tra audience và quyền | API tự kiểm tra claims đã xác minh | API kiểm tra dữ liệu introspection và chính sách AS |

Không có lựa chọn đúng cho mọi dịch vụ. API nội bộ cần độ trễ thấp và chấp nhận token sống ngắn có thể dùng JWT; API đòi hỏi xác minh trạng thái thường xuyên có thể ưu tiên introspection. Một AS cũng có thể phát hành JWT mà resource server vẫn chọn introspect nếu hợp đồng hệ thống hỗ trợ; **định dạng token** và **phương thức xác minh** là hai quyết định cần phân biệt.

## 7. Áp dụng với Java và Spring Security

Các ví dụ dưới đây minh họa cách ràng buộc resource server vào nguồn đã tin cậy. Tùy phiên bản Spring Boot/Spring Security, tên API cấu hình nâng cao có thể thay đổi; cần đối chiếu tài liệu của phiên bản đang dùng trước khi triển khai.

### 7.1. JWT: issuer và audience được quản lý bởi API

Khi AS cung cấp metadata discovery chuẩn, Spring Boot có thể khởi tạo decoder theo issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Thiết lập `issuer-uri` định vị một nguồn tin cậy cụ thể và cho phép framework khám phá JWKS, kiểm tra issuer và các điều kiện thời gian chuẩn. **Audience vẫn phải được ràng buộc cho API**; đừng giả định rằng chỉ cấu hình issuer đã đủ để chặn token cấp cho dịch vụ khác.

Ví dụ dùng decoder riêng, chỉ tin JWKS cố định, giới hạn RS256 và thêm audience validator:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String trustedIssuer = "https://auth.example.test";
    String trustedJwks = "https://auth.example.test/oauth2/jwks";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(trustedJwks)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(trustedIssuer);

    OAuth2TokenValidator<Jwt> correctAudience = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Sai audience", null));
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(standard, correctAudience));
    return decoder;
}
~~~

Đoạn mã là phần phương thức bean trong lớp `@Configuration`; cần import các lớp tương ứng từ Spring Security. Với JWT access token profile RFC 9068 hoặc quy ước `typ`/`token_use` của nhà cung cấp, cần **thêm kiểm tra loại token phù hợp**, không xem ví dụ validator này là cấu hình hoàn chỉnh cho mọi issuer. Chỉ cho phép các thuật toán và profile được hợp đồng với AS xác định.

Sau khi token hợp lệ, endpoint vẫn kiểm tra quyền:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll());
    http.oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

Ứng dụng phải kiểm tra thêm: tài khoản trong `sub` có được đọc/sửa **đúng đơn hàng này** không? Cấu hình `SCOPE_orders.read` chỉ là một cổng kiểm tra, không thay thế quyền sở hữu hoặc chính sách đa tenant.

### 7.2. Opaque: cấu hình introspection với danh tính riêng của API

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: <gia-tri-lay-tu-secret-manager>
~~~

Trong triển khai thực, lấy secret từ biến môi trường hoặc secret manager, không commit giá trị thật vào repository. Một `SecurityFilterChain` dùng `oauth2ResourceServer(oauth -> oauth.opaqueToken(Customizer.withDefaults()))` sẽ sử dụng introspection cho request bearer token theo cấu hình. Nếu cần ràng buộc `aud`, issuer, tenant hay chuẩn hóa scope theo chính sách riêng, bổ sung kiểm tra bằng extension point phù hợp của Spring Security.

Thông tin `client-id`/`client-secret` trong ví dụ là **danh tính của resource server khi gọi introspection**. Nó không phải danh tính của người dùng đăng nhập, không thay thế access token từ client và không nên dùng chung giữa mọi API nếu có thể phân quyền riêng theo từng resource server.

## 8. Nhiều issuer, nhiều tenant: một lỗi tin cậy hay gặp

Giả sử API phục vụ tenant A và B, mỗi tenant có AS khác nhau:

| Tenant | Trusted issuer | Trusted JWKS/introspection |
| --- | --- | --- |
| A | `https://login-a.example.test` | Endpoint được quản trị/phê duyệt cho A |
| B | `https://login-b.example.test` | Endpoint được quản trị/phê duyệt cho B |

Resource server cần danh sách cho phép hoặc bộ ánh xạ được quản trị: **issuer → key source/endpoint → audience/quy tắc tenant**. Trường `iss` chưa xác minh chỉ có thể giúp chọn **một entry đã tồn tại**. Sau đó phải xác minh đúng chữ ký/endpoint, issuer, audience và tenant. Không tạo một entry mới chỉ vì token tự khai một `iss` lạ.

Các sai sót cần tránh:

- Dùng `kid` làm khóa tra cứu toàn cục, khiến khóa của A bị dùng nhầm cho token của B.
- Cho phép mọi issuer thuộc một domain mà không xác minh danh tính issuer chính xác.
- Chấp nhận token của tenant B trên tài nguyên tenant A vì cùng có scope `orders.read`.
- Dùng một introspection endpoint chung mà không xác nhận nó có thẩm quyền với token và tài nguyên đang yêu cầu.

Nếu API chỉ tin một issuer, cấu hình cố định đơn giản thường an toàn hơn cơ chế chọn issuer động. Nếu hệ thống thật sự đa tenant, cần kiểm thử rõ trường hợp token issuer/tenant bị tráo.

## 9. Tình huống tấn công và cách resource server phản ứng

| Tình huống | Điểm kiểm tra quyết định | Hành vi an toàn |
| --- | --- | --- |
| Kẻ tấn công tự ký JWT và đặt `jku` dẫn đến JWKS của mình | Nguồn khóa phải được issuer tin cậy công bố | Không tải JWKS theo URL trong token; từ chối |
| JWT có `alg = none` hoặc cố đánh tráo HS256/RS256 | Danh sách thuật toán và loại khóa được cấu hình | Từ chối trước khi chấp nhận chữ ký |
| JWT đúng chữ ký, issuer đúng nhưng `aud = billing-api` | Audience binding | Từ chối tại `orders-api` |
| ID token dùng để gọi API | Token profile, audience, purpose | Từ chối dù chữ ký hợp lệ |
| Opaque token có `active = false` | Trạng thái tại AS | Từ chối |
| Opaque token `active = true` nhưng không có quyền `orders.read` | Scope và chính sách endpoint | Từ chối đọc đơn hàng |
| Introspection timeout | Nguồn trạng thái không khả dụng | Không tự cho phép; trả lỗi vận hành phù hợp |
| JWT bị đánh cắp nhưng chưa hết hạn | Chữ ký không thể phát hiện người cầm token là kẻ trộm | Giảm TTL, giới hạn audience/scope, cân nhắc revocation hoặc token ràng buộc người gửi |
| Khóa ký cũ bị lộ | Vòng đời khóa và token | Xoay/thu hồi khóa, đánh giá ảnh hưởng đến token đã cấp |
| Token của tenant khác có scope giống nhau | Issuer/tenant/resource ownership | Từ chối truy cập chéo tenant |

Trong giao thức HTTP Bearer, token thiếu/không hợp lệ thường dẫn tới **401** và header `WWW-Authenticate` thích hợp; token hợp lệ nhưng thiếu scope thường dẫn tới **403**. Sự cố hạ tầng introspection cần được phân biệt với kết luận token vô hiệu để dễ giám sát; trong mọi trường hợp, sự cố không được biến thành quyền truy cập mặc định.

### Chống token bị đánh cắp hoặc phát lại

Access token dạng **bearer** có thể bị bất kỳ bên nào sở hữu chuỗi token sử dụng trong phạm vi hiệu lực. Resource server nên bắt buộc HTTPS, không ghi token đầy đủ vào log, kiểm soát nơi token được lưu, dùng token sống ngắn, scope/audience hẹp và theo dõi truy cập bất thường.

Với hệ thống rủi ro cao, có thể dùng **sender-constrained tokens** như DPoP (RFC 9449) hoặc mutual TLS (RFC 8705), nếu AS, client và resource server cùng hỗ trợ. Khi đó API phải xác minh bằng chứng ràng buộc token với khóa/chứng chỉ của bên gửi, không chỉ kiểm tra token. `jti`, phát hiện phát lại và denylist có thể hỗ trợ từng kịch bản, nhưng không nên mặc định rằng có `jti` là tự chống replay.

## 10. Checklist triển khai và câu hỏi tự kiểm tra

Trước khi mở một endpoint bảo vệ bằng OAuth 2.0, hãy kiểm tra:

1. **Trust bootstrap:** Đã xác định chính xác AS/issuer nào được phép phát hành access token cho API chưa? Metadata, JWKS hoặc introspection có xuất phát từ nguồn đó không?
2. **JWT:** Đã giới hạn thuật toán, xác minh chữ ký, kiểm tra `iss`, `aud`, `exp`, `nbf` và token profile chưa? Có từ chối khóa/URL do token tự chỉ định không?
3. **Opaque:** API có xác thực khi gọi đúng introspection endpoint qua HTTPS không? Có xử lý `active: false`, thiếu audience/resource binding và timeout theo hướng từ chối không?
4. **Authorization:** Endpoint có kiểm tra scope và quyền trên từng bản ghi/tenant không? Có phân biệt ID token, access token và refresh token không?
5. **Vận hành:** Đã có kế hoạch key rotation, cache JWKS/introspection, thu hồi khẩn cấp, theo dõi lỗi và giảm thiểu token bị đánh cắp chưa?

**Tự trả lời:** (a) Nếu JWT có chữ ký hợp lệ bằng khóa tải từ `jku` tùy ý, resource server có nên chấp nhận không? (b) Nếu introspection trả `active: true`, liệu điều đó tự cho phép đọc mọi đơn hàng? (c) Nếu JWT của issuer A có `aud` dành cho API B, API A có nhận không?

**Đáp án:** (a) Không: chưa chứng minh khóa thuộc issuer đã được tin. (b) Không: phải kiểm tra token dành cho resource nào, scope và quyền nghiệp vụ. (c) Không: audience không khớp, dù chữ ký và issuer có thể hợp lệ.

## Tài liệu chuẩn để đọc thêm

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò authorization server, client và resource server.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): gửi bearer token và mã lỗi.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` và metadata introspection.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): mô hình khóa và claims.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata của issuer.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): tránh lỗ hổng thuật toán, khóa và nhầm ngữ cảnh JWT.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và kiểm tra token đúng mục đích.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705), [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): token ràng buộc với bên gửi.

**Điểm cần ghi nhớ:** Resource server tin **issuer và nguồn xác minh đã được phê duyệt**. JWT được kiểm tra bằng key/JWKS thuộc issuer đó; opaque token được kiểm tra tại introspection endpoint có thẩm quyền. Sau khi xác minh tính hợp lệ, resource server vẫn phải độc lập kiểm tra audience, scope và quyền truy cập tài nguyên.
