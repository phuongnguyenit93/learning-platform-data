# Đặt password hoặc secret vào access token

> **Chương:** Lỗi thường gặp  
> **Phạm vi:** Bảo vệ access token trong OAuth 2.0/OIDC; tránh đưa password, client secret, API key, private key hoặc credential của hệ thống khác vào token.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao access token là credential để truy cập API, không phải nơi lưu password hoặc secret.
2. Nhận diện dữ liệu nhạy cảm bị nhúng trong JWT payload, header, custom claim hoặc metadata của opaque token.
3. Phân biệt claim phục vụ authorization như scope/role với credential có thể đăng nhập hoặc ký/xác thực.
4. Thay thế việc truyền secret bằng scope, audience, workload identity, Secret Manager, token exchange hoặc cơ chế xác thực phù hợp.
5. Xây dựng biện pháp xử lý khi secret đã bị phát hành trong token: thu hồi, rotate, giới hạn ảnh hưởng, rà soát log/cache và ngăn tái diễn.

## 1. Access token là credential, không phải credential container

Access token là thông tin xác thực mà client trình cho resource server để truy cập tài nguyên được ủy quyền. Với bearer token, bên nào nắm được token thường có thể sử dụng token trong phạm vi quyền và thời hạn của nó. Vì vậy, bản thân access token đã là một credential nhạy cảm.

**Không đưa password hoặc secret có khả năng xác thực/ký vào access token.** Token chỉ nên chứa những thuộc tính tối thiểu resource server cần để xác minh nguồn phát hành, xác định audience, kiểm tra thời hạn và thực thi quyền đã cấp.

Các giá trị sau là credential hoặc secret cần bảo vệ:

- Password người dùng, mật khẩu tài khoản dịch vụ và password quản trị.
- OAuth client secret, API key, access key/secret key của cloud provider.
- Private signing key, private TLS key, SSH private key và seed dùng tạo khóa.
- Database password, message broker credential, webhook signing secret.
- Refresh token hoặc credential dài hạn của hệ thống khác.
- Session secret, recovery code, OTP seed và các giá trị có thể dùng để chiếm quyền tài khoản.

Một access token không trở thành an toàn chỉ vì nó được ký. Chữ ký bảo vệ tính toàn vẹn và xác thực nguồn phát hành theo khóa tin cậy; chữ ký không che giấu nội dung và không ngăn người có token sử dụng bearer credential.

### Token có thể đi qua nhiều nơi

~~~mermaid
flowchart LR
    A["Authorization Server"] -->|"Access token"| C["Client / Browser"]
    C -->|"Authorization: Bearer"| G["API Gateway"]
    G --> S["Resource Server"]
    S --> L["Logs / Traces / APM"]
    C --> B["Browser storage / crash report"]
    G --> P["Proxy / diagnostic capture"]
    S --> K["Cache / queue / audit"]
~~~

Nếu token chứa password, mọi nơi có thể quan sát hoặc lưu token trở thành một điểm rò rỉ password. Ngay cả khi các hệ thống downstream không cố ý đọc claim, token có thể xuất hiện trong log debug, trace, crash dump, reverse proxy, support bundle hoặc công cụ phân tích.

## 2. Vì sao nhúng secret vào JWT nguy hiểm?

JWT thường được dùng dưới dạng JWS gồm header, payload và chữ ký. Header và payload được Base64URL-encode; encoding không phải mã hóa. Bất kỳ bên nào có token đều có thể giải mã payload để đọc claim mà không cần khóa ký.

Ví dụ token sai:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders.read",
  "password": "<user-password>",
  "client_secret": "<oauth-client-secret>",
  "database_password": "<database-password>",
  "exp": 1900000900
}
~~~

Đây là thiết kế sai dù token có chữ ký hợp lệ. Client, browser extension, proxy, log collector hoặc người vận hành có thể đọc các claim này nếu họ lấy được token. Kẻ tấn công có thể trích secret rồi dùng trực tiếp với dịch vụ khác, kể cả sau khi access token đã hết hạn nếu secret gốc vẫn còn hiệu lực.

### Những rủi ro chính

1. **Lộ credential ngoài audience dự kiến:** access token dành cho Orders API có thể bị chuyển qua gateway, telemetry hoặc client; password/API key trong payload bị phơi bày cho các thành phần không cần biết.
2. **Tăng blast radius:** token bị đánh cắp có thể giúp truy cập API theo scope, đồng thời làm lộ credential cho database, cloud hoặc hệ thống khác.
3. **Sai vòng đời:** access token thường ngắn hạn, còn password hoặc API key có thể tồn tại lâu hơn. Hết hạn token không tự động vô hiệu hóa secret đã bị sao chép.
4. **Khó thu hồi triệt để:** thu hồi JWT hoặc session không xóa bản sao password đã xuất hiện trong log, cache, trace, backup hay ticket hỗ trợ.
5. **Vi phạm nguyên tắc least privilege:** một API chỉ cần biết người gọi có quyền đọc đơn hàng nhưng lại được nhận credential có thể truy cập một hệ thống khác.
6. **Tạo đường replay:** người có token có thể trích secret rồi sử dụng ngoài flow OAuth dự kiến; việc rotate token không chắc đã chặn được credential bị trích.
7. **Rủi ro tuân thủ và lưu trữ:** password/secret có thể bị sao chép vào hệ thống telemetry hoặc backup với quyền truy cập, thời hạn lưu và vị trí lưu không phù hợp.

### Chữ ký không phải mã hóa

| Cơ chế | Bảo vệ điều gì? | Có che giấu secret trong payload không? |
| --- | --- | --- |
| Base64URL | Biểu diễn dữ liệu | Không |
| JWS signature | Tính toàn vẹn và nguồn ký theo khóa tin cậy | Không |
| JWE encryption | Mã hóa nội dung cho bên nhận phù hợp | Có thể che payload với bên không có khóa giải mã, nhưng không làm việc nhúng password trở thành thiết kế tốt |
| Opaque token | Không công khai cấu trúc token cho client | Không bảo đảm secret an toàn ở authorization server, introspection, log hoặc nơi lưu token |

Ngay cả khi dùng JWE, credential vẫn bị nhân bản qua một hệ thống token có vòng đời, audience, quyền truy cập và cơ chế lưu trữ khác với hệ thống quản lý secret. Mã hóa có thể giảm khả năng đọc trái phép ở một số chặng, nhưng không sửa được sai mục đích, sai vòng đời hay blast radius.

## 3. Phân biệt secret với claim phục vụ authorization

Không phải mọi claim đều là secret. Access token thường cần mang thông tin giúp resource server ra quyết định. Cần phân biệt dữ liệu mô tả quyền với credential có thể được dùng để xác thực hoặc ký.

| Dữ liệu | Mục đích | Có nên đưa vào access token? |
| --- | --- | --- |
| `iss` | Xác định issuer | Có, để resource server kiểm tra |
| `sub` | Định danh chủ thể trong phạm vi issuer | Khi API cần nhận diện chủ thể; dùng định danh phù hợp |
| `aud` | Xác định resource server nhận token | Có |
| `exp`, `nbf`, `iat` | Giới hạn thời gian token | Có khi theo profile token |
| `scope` | Quyền thao tác được cấp | Có, giới hạn đúng API và mục đích |
| Role/permission | Thuộc tính phân quyền | Có thể có nếu cần, tránh quyền quá rộng |
| `tenant_id` | Tenant context đã được xác minh | Có thể có nếu API cần và issuer cấp theo membership đáng tin |
| Email/tên/số điện thoại | Thông tin cá nhân | Chỉ khi audience thật sự cần; ưu tiên giảm thiểu |
| Password/client secret/API key | Credential có thể xác thực | Không |
| Private key hoặc signing seed | Bí mật dùng ký/xác thực | Không |
| Refresh token của hệ thống khác | Credential cấp quyền lâu dài | Không |
| Database password/cloud secret | Credential hạ tầng | Không |

Scope `orders.read` biểu thị quyền đọc đơn hàng; nó không phải password. Resource server kiểm tra scope rồi áp dụng authorization trên tài nguyên và tenant. Đừng thay scope bằng cách gửi password tới từng API để mỗi API tự đăng nhập thay người dùng.

Một claim như `role=admin` cũng không phải secret theo nghĩa mật mã, nhưng có thể là thông tin nhạy cảm về quyền. Chỉ phát hành role khi API cần, giới hạn audience và thời gian token, đồng thời kiểm tra tenant/resource boundary. Không biến token thành hồ sơ người dùng hoặc kho thông tin nội bộ.

### Access token tốt nên tối thiểu

Ví dụ payload minh họa cho Orders API:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "pairwise-user-42",
  "aud": "orders-api",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-7",
  "iat": 1900000000,
  "exp": 1900000900
}
~~~

Các claim trên chỉ được phát hành sau khi authorization server xác minh chủ thể, client, membership và quyền. Không nên copy trực tiếp tenant ID hoặc role do client tự gửi vào token.

Resource server vẫn phải xác minh chữ ký, issuer, audience, thời gian và các claim bắt buộc. Sau đó nó kiểm tra scope, quyền trên tài nguyên và tenant boundary. Token hợp lệ không đồng nghĩa người gọi có quyền trên mọi object.

## 4. Các tình huống thường dẫn đến lỗi

### 4.1. Đưa password người dùng vào access token

Lý do thường gặp: một microservice cần gọi dịch vụ cũ chỉ hỗ trợ đăng nhập bằng username/password, nên đội phát triển thêm password vào JWT để service downstream lấy ra.

Hậu quả: mọi thành phần có token có thể đọc hoặc chuyển tiếp password; service downstream có thể log hoặc lưu credential; password có thể được dùng ngoài phạm vi API ban đầu.

Cách sửa: xác thực người dùng tại Authorization Server/Identity Provider. Các API nhận access token và kiểm tra scope/audience. Nếu cần gọi hệ thống cũ, dùng backend integration có credential riêng được giữ trong Secret Manager, hoặc thiết kế cơ chế ủy quyền/token exchange phù hợp. Không truyền password người dùng giữa các microservice.

### 4.2. Đưa OAuth client secret vào token

Lý do thường gặp: muốn resource server biết client secret để xác minh client gọi API.

Hậu quả: client secret bị phân phối tới resource server và mọi nơi nhận access token. Client secret có thể cho phép kẻ tấn công giả mạo client tại token endpoint hoặc truy cập tài nguyên theo quyền của client.

Cách sửa: client xác thực với Authorization Server tại token endpoint bằng phương thức được hỗ trợ và cấu hình an toàn. Resource server xác minh access token, audience, scope và các claim cần thiết; nó không cần biết client secret. Với client phù hợp, cân nhắc phương thức xác thực mạnh hơn như private_key_jwt hoặc mTLS theo kiến trúc và khả năng hỗ trợ.

### 4.3. Đưa API key của bên thứ ba vào token

Lý do thường gặp: một service cần gọi payment, email, storage hoặc API của đối tác và muốn token mang theo API key.

Hậu quả: credential của nhà cung cấp bị chia sẻ với client hoặc các service không cần dùng; một lần lộ token có thể làm lộ quyền trên hệ thống bên ngoài.

Cách sửa: giữ API key trong Secret Manager/Vault tại service thực hiện tích hợp. Resource server xác minh quyền người dùng hoặc service; backend gọi nhà cung cấp bằng credential riêng. Nếu cần ủy quyền cho hành động cụ thể, truyền một quyền hoặc reference được kiểm soát, không truyền secret.

### 4.4. Đưa database password hoặc cloud secret vào token

Đây là dấu hiệu trộn lẫn authentication/authorization với quản lý cấu hình hạ tầng. API không cần biết password database để quyết định người dùng có quyền đọc đơn hàng. Kết nối database phải dùng identity/credential của workload và được quản lý ngoài access token.

### 4.5. Đưa refresh token vào access token hoặc claim custom

Refresh token có thể cấp access token mới và thường có vòng đời dài hơn. Nếu nhúng refresh token của issuer hoặc hệ thống khác vào access token, một lần rò rỉ access token có thể kéo dài khả năng truy cập sau khi access token hết hạn. Refresh token phải được giữ trong đúng client/authorization server và được bảo vệ theo chính sách rotation, reuse detection, revocation và storage.

### 4.6. Mã hóa token rồi cho rằng đã giải quyết

JWE có thể giới hạn bên đọc payload, nhưng resource server/client có quyền giải mã vẫn nhận được secret. Nếu secret không cần cho API, việc mã hóa chỉ che giấu vấn đề khỏi các bên trung gian và làm tăng độ phức tạp key management. Hãy loại bỏ secret khỏi token trước, rồi mới chọn cơ chế ký/mã hóa phù hợp với yêu cầu bảo mật còn lại.

## 5. Thay thế bằng thiết kế đúng

Chọn giải pháp theo mục đích thực tế. Không có một loại token hoặc secret store nào thay thế mọi trường hợp.

| Nhu cầu | Thiết kế phù hợp |
| --- | --- |
| Xác thực người dùng | Authorization Server/IdP xác thực password; API nhận access token |
| Kiểm tra quyền API | Scope, audience, role/permission tối thiểu và authorization theo resource |
| Service gọi service | Workload identity, client credentials hoặc cơ chế ủy quyền phù hợp; token có audience và scope riêng |
| Gọi API bên thứ ba bằng API key | Backend giữ key trong Secret Manager/Vault; client không nhận key |
| Kết nối database | Workload identity hoặc credential được quản lý riêng, cấp quyền tối thiểu và rotation |
| Cần gọi API thay mặt người dùng | Token exchange/on-behalf-of theo hỗ trợ của authorization server; giới hạn audience và scope |
| Cần kiểm tra trạng thái token | Introspection hoặc policy/revocation mechanism; không nhúng credential khác |
| Cần chuyển một secret cho bên nhận cụ thể | Secret delivery channel riêng, xác thực bên nhận, giới hạn thời gian/lượt dùng và audit |

### 5.1. Password được xử lý ở đâu?

Password người dùng chỉ nên được gửi tới endpoint xác thực được thiết kế để nhận password qua TLS, theo flow được phép và chính sách bảo mật. Authorization Server xác minh password dựa trên verifier đã lưu; hệ thống không cần phát lại password cho resource server.

Password lưu trữ phải được bảo vệ bằng password hashing chuyên dụng, có salt riêng và tham số phù hợp (ví dụ Argon2id theo hướng dẫn hiện hành). Không lưu password dạng plaintext hoặc mã hóa thuận nghịch để service khác lấy ra. Nếu hệ thống cũ yêu cầu password gốc ở mọi request, cần thiết kế migration để loại bỏ phụ thuộc đó thay vì nhân bản password qua token.

### 5.2. OAuth client secret

Client secret dùng để client xác thực với Authorization Server tại token endpoint. Nó phải nằm trong cấu hình/secret store của backend confidential client, được cấp quyền đọc tối thiểu và rotate theo chính sách. Không đặt client secret trong:

- Access token hoặc ID token.
- JavaScript bundle, mobile app package hoặc source code public.
- URL/query string, log, telemetry hay error message.
- Config file được commit vào repository hoặc artifact chia sẻ rộng.

Public client như SPA/mobile app không thể giữ một secret tĩnh an toàn. Dùng Authorization Code Flow với PKCE theo hướng dẫn OAuth/OIDC hiện hành, không nhúng client secret vào ứng dụng hoặc token để giả lập confidential client.

### 5.3. API key và credential hạ tầng

Backend gọi nhà cung cấp bên ngoài bằng API key được lấy từ Secret Manager. Chỉ service cần tích hợp mới được cấp quyền đọc secret. Ưu tiên workload identity/short-lived credential khi nhà cung cấp hỗ trợ, giới hạn scope/permission của key, đặt hạn sử dụng và rotation. Không gửi API key qua queue hoặc access token để worker khác tự lấy.

### 5.4. Token exchange và ủy quyền downstream

Khi service A nhận access token dành cho A nhưng cần gọi service B, không chuyển token có audience sai hoặc đưa credential hệ thống B vào claim. Có thể dùng token exchange/on-behalf-of nếu Authorization Server hỗ trợ:

~~~text
Client -> Orders API:
  access token (aud=orders-api, scope=orders.read)

Orders API -> Authorization Server:
  token exchange request for downstream audience=billing-api

Authorization Server -> Orders API:
  short-lived token (aud=billing-api, scope=billing.charge)

Orders API -> Billing API:
  downstream access token
~~~

Flow minh họa này cần cấu hình trust, client authentication, subject/actor semantics, audience và scope đúng theo profile được hỗ trợ. Token exchange tạo token có quyền giới hạn cho downstream; nó không phải cách chuyển password hoặc client secret.

### 5.5. Dùng Secret Manager/Vault

Một secret store phù hợp cần:

- Mã hóa khi lưu và truyền, quản lý key mã hóa an toàn.
- Phân quyền theo workload/service và secret cụ thể.
- Audit lần đọc, thay đổi và rotation.
- Hỗ trợ versioning/rotation và quy trình thu hồi.
- Cấp credential ngắn hạn hoặc dynamic secret khi có thể.
- Không ghi secret vào log, metric, trace, crash dump hay image/container layer.
- Có quy trình backup/restore và kiểm soát truy cập tương ứng với mức nhạy cảm.

Access token có thể mang scope hoặc một định danh tham chiếu không nhạy cảm tới một policy/secret configuration nếu kiến trúc thật sự cần. Reference không được là bearer secret thay thế; server phải kiểm tra quyền và không cho client đổi reference để đọc secret tùy ý.

## 6. Ví dụ code: phát hành token không chứa secret

Ví dụ Java/Spring minh họa cách tạo claim quyền cần thiết. Giả định các thông tin subject, audience, scope và tenant đã được xác minh từ nguồn tin cậy:

~~~java
JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer("https://identity.example.com")
        .subject(pairwiseSubject)
        .audience(List.of("orders-api"))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(600))
        .claim("scope", "orders.read")
        .claim("tenant_id", verifiedTenantId.toString())
        .build();

JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256).build();

String accessToken = jwtEncoder.encode(
        JwtEncoderParameters.from(header, claims)
).getTokenValue();
~~~

Ví dụ cố ý không có `password`, `client_secret`, `api_key`, `private_key` hoặc database credential. Biến `pairwiseSubject` và `verifiedTenantId` phải đến từ quy trình xác thực/membership đã kiểm tra; không copy trực tiếp dữ liệu client gửi.

Resource server chỉ cần public key/JWKS của issuer đã cấu hình để xác minh chữ ký, cùng các validator issuer, audience, thời gian và profile token. Nó không cần private signing key của issuer và không cần client secret để đọc token.

### Ví dụ kiểm tra claim không chứa trường cấm

Có thể viết test trên token payload được giải mã trong môi trường kiểm thử:

~~~java
@Test
void accessTokenDoesNotContainCredentialClaims() {
    Jwt jwt = jwtDecoder.decode(issueTestAccessToken());

    assertThat(jwt.getClaims())
            .doesNotContainKeys(
                    "password",
                    "client_secret",
                    "api_key",
                    "private_key",
                    "database_password",
                    "refresh_token"
            );
}
~~~

Đây là test regression bổ sung, không thay thế việc rà soát mọi đường phát hành token. Nếu hệ thống có nhiều loại token hoặc nhiều issuer, cần test theo từng profile/audience. Danh sách trường cấm cần khớp schema nội bộ và có thể mở rộng theo credential thực tế.

## 7. Phòng ngừa lộ secret trong toàn bộ vòng đời token

Ngay cả khi đã bỏ secret khỏi payload, access token vẫn là bearer credential và có thể bị lộ. Cần bảo vệ token và secret ở từng chặng:

| Vị trí | Kiểm soát |
| --- | --- |
| Authorization Server | Chỉ phát hành claim cần thiết; không log password/client secret; bảo vệ signing key |
| Client/browser | Lưu token theo mô hình phù hợp; hạn chế XSS; không đưa token vào URL hoặc analytics |
| API gateway/proxy | Redact Authorization header; không ghi request header đầy đủ |
| Resource server | Không log token/claims nhạy cảm; kiểm tra issuer, audience, expiry, scope |
| Queue/event | Không nhúng token/secret vào message; dùng workload identity hoặc reference có kiểm soát |
| Cache | Không cache secret/token ở key hoặc value không bảo vệ; TTL và access control phù hợp |
| APM/trace | Mask Authorization, cookie và payload nhạy cảm; tránh span attribute chứa credential |
| Secret Manager | Phân quyền, audit, rotation và versioning |
| CI/CD | Dùng secret injection an toàn; không in biến môi trường hoặc secret trong build log |
| Backup/support bundle | Mã hóa, giới hạn truy cập, retention và quy trình xóa |

Access token nên có TTL phù hợp với mức rủi ro và được giới hạn audience/scope. DPoP hoặc mTLS sender-constrained access token có thể giảm nguy cơ token bị replay bởi bên khác trong một số kiến trúc, nhưng không cho phép đưa password hoặc API key vào token. Sender constraint bảo vệ việc sử dụng token; nó không biến token thành secret vault.

Refresh token cần rotation/reuse detection theo chính sách, lưu ở nơi phù hợp với loại client và thu hồi khi có dấu hiệu compromise. Không copy refresh token vào access token, log hoặc message bus.

## 8. Nếu password hoặc secret đã bị phát hành trong token

Xử lý như một sự cố credential exposure, không chỉ là lỗi schema JWT. Việc xóa claim khỏi phiên bản token mới không thu hồi các bản sao cũ đã bị lưu.

### Quy trình ứng phó

1. **Ngăn phát hành mới:** sửa issuer/token builder để loại bỏ claim chứa secret; triển khai sau khi kiểm tra các client/resource server liên quan.
2. **Xác định loại secret:** password người dùng, client secret, API key, private key, database credential hay refresh token. Mỗi loại có chủ sở hữu và quy trình rotation khác nhau.
3. **Đánh giá phạm vi lộ:** issuer, audience, client, resource server, log, proxy, trace, cache, queue, crash report, support bundle và backup.
4. **Rotate hoặc revoke secret:** đổi password/credential bị lộ, thu hồi client secret/API key cũ, thay khóa ký nếu private key bị lộ; phối hợp chủ sở hữu hệ thống liên quan.
5. **Thu hồi token/session:** revoke refresh token/session và áp dụng cơ chế thu hồi access token phù hợp. Lưu ý JWT đã phát hành có thể còn hiệu lực đến khi hết hạn nếu resource server không kiểm tra trạng thái thu hồi.
6. **Xóa/giới hạn bản sao:** xử lý log, cache, event, ticket, export và backup theo chính sách retention/incident; không xóa bằng cách phá vỡ bằng chứng cần bảo toàn.
7. **Theo dõi lạm dụng:** rà soát truy cập bất thường vào hệ thống mà secret có thể mở khóa, trong phạm vi audit được phép.
8. **Ngăn tái diễn:** thêm denylist claim, schema validation, automated tests, code review rule và kiểm soát log redaction.

Nếu private signing key bị lộ, thay khóa ký và cập nhật JWKS theo quy trình key compromise. Nếu chỉ lộ password người dùng, đổi password và đánh giá credential reuse ở các dịch vụ liên quan theo chính sách; không mặc định thu hồi signing key nếu nó không bị ảnh hưởng.

### Bảng phản ứng theo loại credential

| Loại dữ liệu bị lộ | Hành động chính |
| --- | --- |
| Password người dùng | Reset/đổi password qua flow an toàn; kiểm tra reuse/risk; thu hồi session theo chính sách |
| OAuth client secret | Revoke/rotate client secret; rà soát client authentication và token đã cấp |
| API key nhà cung cấp | Revoke key cũ, tạo key giới hạn quyền, kiểm tra audit phía nhà cung cấp |
| Database password | Rotate credential, rà soát kết nối và quyền DB, dùng secret store |
| Cloud access key | Disable/rotate key, rà soát hoạt động IAM và tài nguyên bị truy cập |
| Private signing key | Dừng ký bằng khóa bị lộ, thay key, cập nhật JWKS/trust, đánh giá token đã phát hành |
| Refresh token | Revoke token family/session, xử lý reuse và cấp lại theo flow đăng nhập |
| Webhook signing secret | Rotate secret, xác minh request, xem xét replay và các webhook đã nhận |

Không gửi secret đang bị lộ qua ticket/chat để “xác nhận”. Trao đổi bằng mã sự cố và reference tới secret record có quyền truy cập kiểm soát.

## 9. Bộ ca kiểm thử và kiểm soát phòng ngừa

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| SEC-AT-01 | Access token có claim `password` | Token issuance test thất bại |
| SEC-AT-02 | Access token có `client_secret` hoặc `api_key` | Token issuance test thất bại |
| SEC-AT-03 | Token có private key/database password | Schema/policy chặn phát hành |
| SEC-AT-04 | Token payload được decode trong test | Không có credential hoặc PII không cần thiết |
| SEC-AT-05 | Token có scope và audience đúng | Resource server xử lý theo quyền đã cấp |
| SEC-AT-06 | Client cố gửi password trong custom header để downstream đọc | API không chuyển tiếp hoặc log credential |
| SEC-AT-07 | Authorization header đi qua gateway/APM | Log/trace đã redact token |
| SEC-AT-08 | Client secret được dùng tại token endpoint | Không xuất hiện trong access token |
| SEC-AT-09 | API key bên thứ ba được backend lấy từ secret store | Client và token không nhận API key |
| SEC-AT-10 | Secret được rotate | Service dùng version mới; credential cũ bị vô hiệu theo kế hoạch |
| SEC-AT-11 | Token cũ có secret đã bị phát hành | Incident process revoke/rotate và rà soát bản sao |
| SEC-AT-12 | Token exchange cho downstream API | Token mới có audience/scope giới hạn, không mang secret gốc |

Nên bổ sung static scan hoặc policy test trên schema claim, kiểm tra log redaction và rà soát mọi token profile. Kiểm thử không chỉ tìm đúng tên `password`; hãy tìm cả các alias như `pwd`, `secret`, `apiKey`, `privateKey`, `credential`, `connectionString` và tên trường nội bộ có thể chứa secret. Không dựa hoàn toàn vào tên field vì secret có thể bị giấu trong claim tùy ý.

## 10. Bài tập thực hành

**Tình huống:** Một nhóm phát triển thêm custom claim `legacy_password` vào access token để Orders API gọi hệ thống cũ. Token được ký RS256, hết hạn sau 10 phút và chỉ có audience `orders-api`. Nhóm cho rằng chữ ký và TTL ngắn đã đủ an toàn.

1. Nêu ít nhất bốn lý do thiết kế này vẫn nguy hiểm.
2. Nếu hệ thống cũ cần xác thực bằng password, đề xuất kiến trúc thay thế.
3. Nếu claim thực tế là `client_secret` của một confidential client, credential đó phải được sử dụng ở đâu?
4. Nếu nhóm đổi sang JWE, những rủi ro nào vẫn còn?
5. Secret đã được phát hành trong token production một tuần; hãy lập các hành động ứng phó theo thứ tự ưu tiên.

**Gợi ý đáp án:**

1. JWS không mã hóa payload; client/gateway/log có thể đọc token; password sống lâu hơn access token; token leak làm lộ cả API credential và password; secret bị copy vào backup/log không được xóa khi token hết hạn.
2. Xác thực người dùng tại IdP; Orders API dùng access token với scope/audience; backend integration gọi hệ thống cũ bằng workload identity hoặc credential riêng trong Secret Manager. Tốt hơn là nâng cấp hệ thống cũ để hỗ trợ token/ủy quyền.
3. Client secret chỉ dùng để confidential client xác thực với Authorization Server tại token endpoint bằng phương thức được cấu hình; resource server không cần nhận nó.
4. Bên có khóa giải mã vẫn đọc được secret; secret vẫn bị nhân bản, sai vòng đời, sai audience/mục đích, có thể xuất hiện trong log sau giải mã và cần rotation riêng.
5. Dừng phát hành claim mới, xác định loại secret và phạm vi, rotate/revoke secret, revoke session/token phù hợp, rà soát log/cache/queue/backup và hoạt động sử dụng credential, sau đó thêm test/policy ngăn tái diễn.

## Ghi nhớ

- Access token tự nó là credential; không dùng nó làm kho password hoặc secret.
- JWS ký payload nhưng không mã hóa payload; Base64URL không phải cơ chế bảo mật nội dung.
- Opaque token cũng không làm secret an toàn nếu secret bị lưu trong introspection, log hoặc nơi quản lý token.
- Scope, audience, role và tenant context mô tả quyền; password, client secret, API key và private key là credential phải giữ riêng.
- Dùng Authorization Server để xác thực, Secret Manager/Vault để quản lý secret và token exchange/workload identity cho lời gọi downstream phù hợp.
- Khi secret đã xuất hiện trong token, phải rotate/revoke credential, xử lý token/session và rà soát các bản sao đã phát tán.
- Kiểm soát claim schema, log redaction, telemetry, CI/CD và test regression để ngăn lỗi quay lại.

### Tài liệu tham khảo

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
