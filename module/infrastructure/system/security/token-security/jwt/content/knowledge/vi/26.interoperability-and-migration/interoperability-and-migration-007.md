# Thay issuer, audience hoặc loại token với các bên sử dụng đang hoạt động

## 1. Vì sao thay đổi token contract là một cuộc di trú hệ thống?

Một hệ thống JWT thường có nhiều issuer, API gateway, resource server, ứng dụng web/mobile, service nội bộ, đối tác tích hợp và worker xử lý nền. Mỗi thành phần có thể phát hành, nhận, cache hoặc xác minh token theo một hợp đồng đã tồn tại nhiều năm.

Khi thay issuer, audience hoặc loại token, chỉ sửa cấu hình ở authorization server là chưa đủ. Trong một khoảng thời gian, hệ thống có thể đồng thời tồn tại token mới do issuer mới phát hành và token cũ vẫn còn hạn, resource identifier mới và identifier cũ, access token theo profile mới và token theo profile cũ, consumer đã nâng cấp và consumer chưa thể cập nhật ngay, cùng cache JWKS/discovery/introspection ở nhiều phiên bản.

Nếu di trú thiếu kế hoạch, kết quả có thể là outage diện rộng, xác thực nhầm loại token, từ chối người dùng hợp lệ hoặc mở rộng trust để tạm thời tương thích rồi quên thu hẹp lại.

Bài này trình bày cách thay đổi **issuer**, **audience** hoặc **token type/profile** khi các bên sử dụng đang hoạt động. Mục tiêu là giữ dịch vụ liên tục trong khi vẫn duy trì ranh giới tin cậy, khả năng thu hồi và kiểm soát quyền. Nội dung áp dụng chung cho OAuth 2.0, OpenID Connect, JWT/JWS và hệ thống phân tán; không phụ thuộc Java hay framework.

## 2. Phân biệt ba thay đổi thường bị gộp chung

### 2.1. Thay issuer

Issuer (iss) xác định thực thể phát hành token. Resource server dùng issuer để chọn trust configuration, khóa xác minh, metadata, policy và đôi khi cả namespace subject.

Thay issuer có thể xảy ra khi di chuyển identity provider, hợp nhất authorization server, thay domain hoặc issuer identifier, chuyển sang nhà cung cấp identity khác, hoặc tách issuer theo môi trường/tenant/miền bảo mật.

Issuer là định danh trong hợp đồng token. Thay hostname, URL hoặc dấu slash cuối có thể tạo issuer khác về mặt so sánh chính xác. Không tự chuẩn hóa chuỗi issuer theo suy đoán.

### 2.2. Thay audience

Audience (aud) xác định recipient mà token hướng tới. Với access token, audience thường đại diện API/resource server hoặc resource identifier.

Thay audience có thể xảy ra khi đổi tên/canonicalize resource URI, chia một API thành nhiều resource server, di chuyển API sang domain mới, thay audience alias bằng định danh resource chuẩn hoặc tách quyền giữa các dịch vụ trước đây dùng chung audience.

Audience là ranh giới người nhận. Nếu resource server chấp nhận audience quá rộng, token có thể bị sử dụng ở nơi không được dự định.

### 2.3. Thay token type hoặc profile

Token type/profile xác định token đại diện điều gì và phải được xác minh theo quy tắc nào. Những thay đổi thường gặp:

- Chuyển từ JWT access token tùy biến sang profile JWT access token theo RFC 9068.
- Bổ sung hoặc thay đổi JOSE header typ.
- Chuẩn hóa claims như client_id, scope, jti, iss, aud.
- Phân biệt access token, ID Token và refresh token.
- Chuyển từ JWT sang opaque access token.
- Thay custom claim token_use bằng profile chuẩn hoặc ngược lại.

Một token có chữ ký hợp lệ chưa chắc là đúng loại token cho endpoint. Resource server phải kiểm tra token profile và mục đích sử dụng.

### 2.4. Ba thay đổi độc lập nhưng có thể diễn ra cùng lúc

| Thuộc tính | Câu hỏi | Kiểm tra chính |
| --- | --- | --- |
| iss | Ai phát hành token? | Exact issuer trust, discovery, JWKS |
| aud | Token dành cho resource nào? | Audience match theo resource |
| Token type/profile | Token này là loại credential nào? | typ, claims bắt buộc, endpoint context, validation rules |

Thay một thuộc tính không tự động làm hai thuộc tính còn lại thay đổi. Kế hoạch di trú cần ghi rõ từng chiều thay đổi, consumer chịu ảnh hưởng và thời điểm bắt đầu/kết thúc.

## 3. Nguyên tắc bất biến trong suốt quá trình di trú

### 3.1. Không làm yếu xác minh để giữ tương thích

Không bỏ kiểm tra issuer, chấp nhận mọi audience hoặc wildcard rộng, chấp nhận bất kỳ token có chữ ký hợp lệ, dùng ID Token thay access token, bỏ qua token type/profile, tải JWKS từ URL tùy ý trong token, hoặc giữ trust cũ vô thời hạn vì còn consumer chưa nâng cấp.

Compatibility phải có danh sách issuer, audience và profile được phép, thời hạn, consumer cụ thể và tiêu chí gỡ bỏ.

### 3.2. Không sửa claims của token đã ký

Không thay iss, aud, typ hoặc claims bên trong JWT đã ký rồi tiếp tục dùng chữ ký cũ. Chữ ký bảo vệ header/payload; mọi thay đổi nội dung làm chữ ký không còn hợp lệ.

Nếu cần token mới với issuer, audience hoặc profile khác, hãy để issuer tin cậy phát hành token mới, hoặc dùng cơ chế token exchange/ủy quyền được thiết kế rõ ràng.

### 3.3. Không nhầm tương thích với tin cậy

Consumer có thể hỗ trợ hai phiên bản contract trong một khoảng thời gian, nhưng phải xác minh từng phiên bản theo trust policy riêng. Parse được token không đồng nghĩa được phép chấp nhận token.

### 3.4. Giữ nguyên least privilege

Trong thời gian di trú, không thêm audience chỉ để tránh lỗi consumer chưa cập nhật, không cấp scope lớn hơn cho token cũ, không dùng chung signing key hoặc client credential cho nhiều trust domain nếu làm mờ nguồn phát hành, không kéo dài token lifetime chỉ để có thêm thời gian di trú và không để consumer cũ tiếp tục nhận quyền mà contract mới đã loại bỏ.

### 3.5. Có thời điểm kết thúc

Mỗi compatibility window phải có ngày bắt đầu, ngày kết thúc dự kiến, điều kiện gia hạn có phê duyệt, metric chứng minh consumer đã chuyển đổi, người chịu trách nhiệm consumer còn sót và hành động sau khi hết hạn.

Không có end date thì giai đoạn tạm thời dễ trở thành cấu hình vĩnh viễn.

## 4. Lập inventory trước khi thay đổi

### 4.1. Liệt kê tất cả issuer và consumer

Trước khi sửa token contract, lập danh sách:

- Authorization server/issuer hiện tại và issuer dự kiến.
- JWKS URI và discovery metadata.
- API gateway, reverse proxy và resource server.
- Web app, mobile app, desktop client.
- Đối tác bên ngoài.
- Worker, scheduler, queue consumer và batch job.
- Hệ thống analytics, audit hoặc gateway policy có đọc claims.
- Cache, introspection service và token exchange client.

Không chỉ tìm nơi gọi API. Consumer có thể nằm trong job ít chạy, thiết bị offline, ứng dụng cũ hoặc đối tác chỉ gửi request theo chu kỳ.

### 4.2. Tạo consumer contract matrix

| Consumer | Issuer hiện tại | Audience hiện tại | Token profile | Khả năng nâng cấp | Owner |
| --- | --- | --- | --- | --- | --- |
| Web application | issuer-A | web-api | legacy access JWT | Triển khai nhanh | Web team |
| Mobile app | issuer-A | mobile-api | legacy access JWT | Phụ thuộc phát hành app | Mobile team |
| Order service | issuer-A | orders-api | legacy access JWT | Triển khai độc lập | Order team |
| Partner gateway | issuer-A | partner-api | custom JWT | Cần phối hợp đối tác | Partner owner |
| Background worker | issuer-A | jobs-api | legacy access JWT | Có thể triển khai theo lịch | Platform team |

Đây là ví dụ. Inventory thực tế phải được xác minh bằng cấu hình, traffic, log đã redact, repository và xác nhận từ owner. Không suy ra rằng không có traffic nghĩa là không còn consumer.

### 4.3. Thu thập token contract hiện tại

Ghi nhận issuer exact string, audience exact values và kiểu dữ liệu (string hay array), JOSE header alg/kid/typ/cty, claims bắt buộc và custom claims, quy tắc sub/tenant/scope/role, token lifetime, refresh policy và revocation behavior, JWKS cache/refresh policy, quy tắc lỗi HTTP/OAuth, clock skew và yêu cầu đồng bộ thời gian.

Không thu thập hoặc lưu raw bearer token trong tài liệu inventory. Dùng token fixture đã tạo riêng hoặc claims đã redact.

### 4.4. Xác định dependency ẩn

Consumer có thể phụ thuộc vào chi tiết ngoài contract chính thức:

- So sánh issuer bằng chuỗi hard-code.
- Đọc aud theo giả định luôn là string.
- Giả định sub luôn là email.
- Giả định role là array hoặc string cụ thể.
- Dùng custom claim token_use.
- Chỉ chấp nhận một PEM label hoặc một thuật toán.
- Cache metadata/JWKS lâu hơn dự kiến.
- Dùng ID Token như bearer token vì trước đây issuer phát hành cùng audience.

Di trú cần kiểm thử những hành vi thực tế này, sau đó chuẩn hóa contract.

## 5. Thiết kế token contract đích

### 5.1. Định nghĩa bằng tài liệu và test vector

Trước khi phát hành token mới, tạo contract có version hoặc profile ID rõ ràng. Ví dụ:

~~~yaml
profile: access-token-v2
issuer: https://identity.example.net/
audience:
  - https://api.example.net/orders
typ: at+jwt
required_claims:
  - iss
  - sub
  - aud
  - exp
  - iat
  - jti
  - client_id
  - scope
algorithms:
  - ES256
~~~

Đây là ví dụ tài liệu contract, không phải cấu hình dùng trực tiếp cho mọi hệ thống. Các claim và thuật toán phải phù hợp RFC/profile, threat model và năng lực consumer.

### 5.2. Chọn issuer identifier ổn định

Issuer mới cần exact identifier được công bố trước, HTTPS và domain thuộc quyền kiểm soát của tổ chức, metadata/discovery nhất quán, JWKS URI có trust chain rõ ràng, chính sách key rotation/incident response và quy tắc subject migration/account linking.

Không đổi issuer theo từng lần triển khai hoặc hostname tạm thời. Nếu domain phải thay đổi, xem đó là migration có kế hoạch với thời gian overlap và trust removal rõ ràng.

### 5.3. Chọn audience theo resource boundary

Audience mới phải phản ánh resource nhận token. Ưu tiên identifier ổn định, duy nhất và có ý nghĩa theo contract.

Tránh audience chung chung như api, internal, backend nếu nhiều resource có quyền và trust boundary khác nhau. Không thêm audience mới vào token chỉ vì consumer cũ cần tiếp tục hoạt động; cân nhắc token exchange hoặc phát hành token riêng theo resource.

### 5.4. Định nghĩa token type/profile

Với JWT access token theo RFC 9068, JOSE header typ dùng giá trị at+jwt; resource server phải xác minh token theo profile access token và các claims bắt buộc.

Phân biệt:

- **Access token**: credential gửi tới resource server để truy cập resource.
- **ID Token**: assertion trong OpenID Connect dành cho client, mô tả authentication event và subject; audience thường là client ID.
- **Refresh token**: credential dùng tại token endpoint để yêu cầu access token mới; không gửi tới resource server.
- **Logout/session token hoặc assertion riêng**: chỉ dùng theo contract chuyên biệt.

Không chấp nhận ID Token làm access token chỉ vì cả hai đều là JWT và cùng có sub.

### 5.5. Claims và subject mapping

Nếu issuer mới dùng subject identifier khác, cần xác định có giữ nguyên sub hay tạo identifier mới, subject unique trong phạm vi issuer nào, có cần account-linking table không, consumer có dùng sub làm database key không, dữ liệu audit lịch sử liên kết subject cũ/mới ra sao và có nguy cơ gán nhầm subject mới cho tài khoản cũ không.

Không giả định sub giống nhau giữa hai issuer. Subject thường chỉ có ý nghĩa trong namespace của issuer; cặp (iss, sub) mới là định danh đáng tin cậy hơn cho nhiều hệ thống.

## 6. Thay issuer khi consumer vẫn đang hoạt động

### 6.1. Vì sao đổi issuer không chỉ là đổi URL

Resource server thường dùng iss để chọn cấu hình xác minh. Nếu issuer đổi, có thể đồng thời thay discovery metadata/JWKS URI, signing key/kid, namespace của sub, chính sách token lifetime, claims/token profile và cơ chế revocation/introspection.

Consumer cũ có thể hard-code issuer cũ hoặc chỉ có một issuer trong allowlist.

### 6.2. Hai issuer trong giai đoạn chuyển tiếp

Một consumer có thể tạm thời tin cả issuer cũ và mới nếu cả hai được cấu hình rõ ràng:

~~~text
Trusted issuer set during migration:
  issuer-A:
    jwks = trusted JWKS A
    profile = access-token-v1
    audience = orders-api

  issuer-B:
    jwks = trusted JWKS B
    profile = access-token-v2
    audience = https://api.example.net/orders
~~~

Khi nhận token, verifier xác định issuer theo exact value, chọn đúng trust configuration, xác minh bằng key của issuer đó và áp dụng profile tương ứng.

Không thử key của issuer A nếu token khai issuer B rồi chữ ký thất bại. Không dùng cùng một cache JWKS chỉ dựa trên kid.

### 6.3. Staged issuer migration

Trình tự khuyến nghị:

1. **Chuẩn bị issuer mới**: hoàn tất domain, metadata, JWKS, key management, monitoring và policy.
2. **Công bố trust config**: triển khai cấu hình issuer mới cho consumer, nhưng chưa buộc mọi traffic chuyển ngay.
3. **Kiểm thử token mới**: phát hành fixture và xác minh ở mọi loại consumer.
4. **Triển khai consumer hỗ trợ hai issuer**: chỉ hai issuer cụ thể, profile/audience tương ứng và end date rõ ràng.
5. **Canary phát hành token mới**: chuyển một nhóm client hoặc traffic nhỏ sang issuer mới.
6. **Quan sát**: theo dõi success rate, issuer mismatch, unknown kid, invalid audience và lỗi authorization.
7. **Mở rộng phát hành**: chuyển dần client và service sang issuer mới.
8. **Drain token cũ**: ngừng phát hành token mới từ issuer cũ; chờ token cũ hết hạn hoặc revoke theo policy.
9. **Gỡ trust cũ**: chỉ sau khi mọi consumer đã chuyển và không còn token cũ hợp lệ cần được chấp nhận.
10. **Xác nhận decommission**: kiểm tra traffic, scheduled job, partner và cache trước khi đóng issuer cũ.

### 6.4. Không re-sign token cũ bằng issuer mới một cách âm thầm

Issuer mới không nên chỉ lấy claims từ token cũ rồi ký lại mà không xác minh nguồn, quyền và subject mapping. Nếu cần chuyển đổi token, dùng token exchange hoặc một migration service có policy:

- Xác minh token nguồn đầy đủ.
- Kiểm tra issuer/audience/profile nguồn.
- Xác minh client được phép exchange.
- Xác định subject mapping đáng tin.
- Giảm scope theo resource đích.
- Phát hành token mới với issuer/audience/profile đích.
- Ghi audit quan hệ giữa token nguồn và token mới mà không lưu raw token.

Token exchange theo RFC 8693 là một lựa chọn khi mô hình OAuth và authorization server hỗ trợ.

### 6.5. Subject migration và account linking

Nếu issuer mới cấp sub khác, không ánh xạ bằng email đơn thuần nếu email có thể đổi, tái sử dụng hoặc không được xác minh đồng nhất.

Dùng một quy trình liên kết danh tính có bằng chứng: identifier cũ trong namespace issuer cũ, identifier mới trong namespace issuer mới, account-linking record được bảo vệ, bằng chứng kiểm soát cả hai identity hoặc quy trình quản trị đã phê duyệt, audit ai/luồng nào tạo liên kết và quy trình xử lý collision/duplicate/account recovery.

Không tự động gộp hai tài khoản chỉ vì sub, email hoặc display name trùng nhau.

## 7. Thay audience khi resource server vẫn đang phục vụ traffic

### 7.1. Audience phải được xác minh chính xác

JWT aud có thể là một string hoặc một array of strings. Verifier phải xử lý theo chuẩn và policy:

- Token audience string phải khớp resource identifier được cấu hình.
- Nếu là array, resource server phải nằm trong tập audience được phép.
- Không chấp nhận audience rỗng hoặc thiếu nếu profile yêu cầu.
- Không so khớp bằng substring, prefix hoặc wildcard không có policy.
- Không coi audience của gateway là audience của mọi downstream service.

### 7.2. Audience migration có thể mở rộng hoặc thu hẹp quyền nhận

Ví dụ:

~~~text
Old:
  aud = "api"

Target:
  aud = "https://api.example.net/orders"
~~~

Nếu trước đây nhiều service cùng chấp nhận api, thay đổi này là cơ hội tách trust boundary. Không giữ audience chung vô thời hạn vì consumer cũ chưa sửa cấu hình.

### 7.3. Cách chuyển tiếp

**Phương án A — Consumer hỗ trợ old/new audience có giới hạn.** Trong thời gian chuyển đổi, resource server chấp nhận chính xác audience cũ và audience mới theo issuer/profile được phép. Có end date và metric phân biệt từng audience.

**Phương án B — Issuer phát hành token riêng theo audience.** Client/service nhận token dành cho resource cụ thể. Cách này giảm blast radius và phù hợp khi resource có quyền khác nhau.

**Phương án C — Token exchange.** Upstream đổi token nguồn thành token có audience đích. Authorization server kiểm tra client, subject, actor và quyền trước khi phát hành.

**Phương án D — Resource alias có thời hạn.** Chỉ dùng khi alias có semantics rõ ràng và mỗi resource xác minh alias thuộc chính nó. Không tạo alias chung khiến nhiều API cùng nhận token.

### 7.4. Cẩn trọng với multi-audience token

Một token có aud=[old-api,new-api] có thể giúp tương thích trong thời gian ngắn, nhưng mọi recipient trong danh sách đều có thể nhận token đó.

Trước khi dùng, xác nhận cả hai resource thuộc cùng trust boundary, scope phù hợp cho cả hai, nơi token bị lộ có thể bị phát lại, thời gian kết thúc và không dùng multi-audience để che giấu việc resource đang bị tách.

Nếu hai API có quyền khác nhau, phát hành token riêng thường an toàn hơn.

### 7.5. Không sửa aud trong token đã phát hành

Không thêm audience vào payload token cũ hoặc thay audience trong gateway. Nếu token được cấp cho audience cũ, resource mới phải từ chối nó trừ khi một contract migration được thiết kế trước và issuer phát hành token mới phù hợp.

## 8. Thay token type hoặc profile

### 8.1. Vì sao chỉ kiểm tra chữ ký là chưa đủ?

Một ID Token có thể được ký bởi issuer đáng tin và có chữ ký hợp lệ. Nhưng nó được phát hành cho OIDC client, không phải mặc nhiên dành cho API. Nếu API chỉ kiểm tra chữ ký và sub, ID Token có thể bị sử dụng nhầm làm access token.

Resource server phải kiểm tra issuer/audience, token type/profile, claims bắt buộc, thời gian/token status, scope/permission và sender constraint nếu áp dụng.

### 8.2. Chuẩn hóa JWT access token profile

RFC 9068 định nghĩa JWT Profile cho OAuth 2.0 Access Tokens. Với profile này, protected header typ dùng at+jwt; các claim như iss, sub, aud, exp, iat, jti, client_id và scope/authorization data được xử lý theo quy tắc profile.

Khi chuyển từ custom JWT sang RFC 9068:

1. Liệt kê claims custom đang được consumer sử dụng.
2. Mapping chúng sang registered/standard claims nếu semantics thực sự tương đương.
3. Không đổi tên claim mà không đổi semantics và validation.
4. Cập nhật consumer để xác minh typ và profile.
5. Giữ một adapter cho profile cũ trong compatibility window.
6. Phát hành token mới với profile đích.
7. Đo lượng token cũ còn được sử dụng.
8. Gỡ adapter cũ sau khi token cũ hết hạn và consumer đã chuyển.

### 8.3. typ không thay thế mọi kiểm tra

typ là một tín hiệu profile trong JOSE header. Verifier vẫn cần xác minh issuer, audience, chữ ký, thuật toán, claims bắt buộc và token context.

Không chấp nhận mọi token chỉ vì typ=at+jwt. Không coi typ do token tự khai là bằng chứng độc lập; nó chỉ có ý nghĩa sau khi toàn bộ token được xác minh theo trust configuration.

### 8.4. Phân biệt ID Token và Access Token

| Thuộc tính | OIDC ID Token | OAuth Access Token |
| --- | --- | --- |
| Mục đích | Client xác minh kết quả authentication | Resource server kiểm soát truy cập API |
| Audience | Thường là client ID | Resource/API đích |
| Consumer chính | OIDC client | Resource server |
| Claims | Authentication context như auth_time, nonce khi áp dụng | Authorization context như scope/permission |
| Gửi tới API | Không mặc định | Có |
| Validation | Theo OpenID Connect Core | Theo OAuth access-token profile |

Không chuyển ID Token thành access token chỉ bằng cách thêm scope hoặc đổi header typ.

### 8.5. Custom token_use hoặc token_type claim

Một hệ thống có thể dùng claim riêng như token_use=access hoặc token_type=refresh. Nếu đang di trú, định nghĩa chính xác giá trị và semantics, chỉ chấp nhận claim trong issuer/profile đã xác thực, tránh để custom claim mâu thuẫn với JOSE typ, từ chối token có profile không khớp endpoint và đặt thời hạn kết thúc cho legacy claim.

Không dùng tên claim giống chuẩn nhưng gán semantics khác.

### 8.6. Chuyển JWT sang opaque access token

Opaque token không tự chứa claims có thể đọc cục bộ. Resource server thường cần introspection hoặc cơ chế tra cứu trạng thái.

Di trú cần hỗ trợ parser/validator theo token format được contract xác định, chọn đúng validation path theo endpoint/client/issuer policy, cấu hình introspection endpoint và client authentication, xác định cache TTL và hành vi khi introspection unavailable, bảo vệ introspection response và không log token, có kế hoạch revoke/timeout/availability.

Không đoán token là JWT hay opaque bằng cách thử parser rồi fallback rộng. Dùng cấu hình client/resource hoặc token profile đã biết. Nếu token không khớp format được phép, reject.

## 9. Kết hợp nhiều thay đổi mà không tạo khoảng mơ hồ

### 9.1. Lập ma trận nguồn-đích

Nếu cùng lúc thay issuer, audience và profile, xác định rõ các tổ hợp được phép:

| Issuer | Audience | Profile | Trạng thái |
| --- | --- | --- | --- |
| issuer-A | orders-api | legacy-v1 | Chỉ chấp nhận trong thời gian drain |
| issuer-B | orders-api | legacy-v1 | Không chấp nhận nếu chưa có migration contract |
| issuer-A | new-orders-uri | access-v2 | Không chấp nhận nếu chưa được phát hành/kiểm thử |
| issuer-B | new-orders-uri | access-v2 | Target contract |

Không tạo ma trận chấp nhận kiểu issuer A hoặc B, audience cũ hoặc mới, profile bất kỳ. Mỗi tổ hợp phải có lý do và validation rules riêng.

### 9.2. Ưu tiên tách migration dimension

Nếu khả thi, thay từng chiều theo giai đoạn:

1. Chuẩn hóa consumer validation và inventory.
2. Chuyển token profile trong khi issuer/audience giữ nguyên.
3. Chuyển audience theo resource.
4. Chuyển issuer.
5. Gỡ các contract cũ.

Thứ tự có thể thay đổi theo dependency, nhưng tránh thay ba chiều trong cùng một lần nếu không có test matrix đầy đủ. Tách dimension giúp xác định nguyên nhân khi có lỗi.

### 9.3. Nếu bắt buộc thay đồng thời

Khi có yêu cầu deadline hoặc nhà cung cấp mới buộc thay đồng thời, định nghĩa rõ từng tuple issuer/audience/profile, cấu hình từng tuple như một trust profile độc lập, tạo test vector cho mọi tuple được phép, triển khai consumer trước issuer, dùng canary và rollback theo tuple, theo dõi traffic riêng cho từng tuple và không cho phép tổ hợp chưa được định nghĩa.

## 10. Rollout theo giai đoạn

### 10.1. Giai đoạn 0 — Khám phá và baseline

Thu thập consumer inventory, traffic baseline, error rate, token lifetime, cache age và owner. Định nghĩa mục tiêu, end date, rollback trigger và security invariants.

### 10.2. Giai đoạn 1 — Chuẩn bị issuer và contract mới

Issuer mới phải sẵn sàng trước khi consumer chuyển: metadata/JWKS truy cập được, TLS/domain hợp lệ, signing key được quản lý an toàn, token profile và claims được tài liệu hóa, audience resource được xác định, revocation/incident response hoạt động và test vector được phát hành cho consumer.

### 10.3. Giai đoạn 2 — Consumer hỗ trợ contract mới

Triển khai verifier mới trước. Trong giai đoạn tương thích, consumer chỉ chấp nhận old/new tuple được liệt kê. Kiểm thử bằng token fixture và staging issuer.

Consumer cần có telemetry để phân biệt token cũ và token mới nhưng không log raw token.

### 10.4. Giai đoạn 3 — Canary issuance

Chuyển một nhóm client, tenant hoặc traffic nhỏ sang token mới. Giữ tỷ lệ canary đủ nhỏ để rollback được nhưng đủ lớn để kiểm tra consumer đa dạng.

Theo dõi issuer mismatch, invalid audience, wrong token type/profile, signature/key lookup failure, introspection/JWKS dependency failure, authorization denied sau authentication và tỷ lệ refresh/token exchange.

### 10.5. Giai đoạn 4 — Mở rộng

Chỉ mở rộng khi consumer trọng yếu đã xác minh token mới, không có lỗi bảo mật hoặc tăng 401/403 bất thường, JWKS/discovery propagation ổn định, partner/mobile rollout có tiến độ xác nhận và rollback path đã được thử.

Mở rộng theo nhóm consumer, không chuyển tất cả cùng lúc nếu dependency không đồng đều.

### 10.6. Giai đoạn 5 — Drain token cũ

Ngừng phát hành token mới theo contract cũ. Token cũ còn hiệu lực có thể được chấp nhận tới exp nếu policy cho phép và chưa bị revoke.

Thời gian drain phải tính maximum access token lifetime, clock skew, refresh token lifetime và khả năng mint access token mới, client retry/backoff, job/queue có thể giữ token, mobile/partner có thể hoạt động offline và cache/propagation delay.

Refresh token là một điểm đặc biệt: nếu vẫn có thể dùng refresh token cũ để nhận access token theo issuer/profile cũ, việc ngừng access token issuance chưa hoàn tất. Cần revoke/retire refresh family hoặc buộc refresh flow chuyển sang issuer/profile mới theo kế hoạch.

### 10.7. Giai đoạn 6 — Decommission

Chỉ gỡ issuer/audience/profile cũ sau khi không còn token cũ hợp lệ cần được chấp nhận, không còn consumer active dùng contract cũ, không còn refresh session có thể phát hành token cũ, partner đã xác nhận chuyển đổi hoặc integration cũ đã bị disable, background job/queue đã được xử lý, metric/audit không còn hoạt động legacy trong cửa sổ quan sát đã định và runbook/cấu hình đã xóa trust cũ.

Không chỉ dựa vào việc traffic 24 giờ qua bằng 0 nếu token lifetime hoặc lịch job dài hơn 24 giờ.

## 11. Rollback an toàn

### 11.1. Rollback consumer và rollback issuer khác nhau

Nếu consumer mới gặp lỗi, có thể rollback phiên bản consumer nhưng phải bảo đảm phiên bản cũ không nhận token mới. Nếu issuer đã bắt đầu phát hành token mới, rollback consumer đơn thuần có thể gây outage.

Rollback plan phải xác định có thể quay lại phát hành token cũ không, key cũ còn an toàn và được giữ không, consumer cũ còn trust issuer cũ không, token mới đã phát hành còn hiệu lực bao lâu, có cần revoke token/session mới không và audience/profile mới có bị disable ngay hay drain.

### 11.2. Không rollback bằng cách mở rộng trust vô hạn

Khi gặp lỗi, không tạm thời chấp nhận mọi issuer/audience hoặc bỏ validation. Dùng rollback tuple đã kiểm thử, giới hạn consumer/traffic và có end date.

### 11.3. Khi issuer cũ đã decommission

Nếu issuer cũ đã bị tắt hoặc private key đã hủy, rollback có thể không còn khả thi. Trước decommission, phải quyết định thời điểm irreversibility và có phương án khôi phục bằng issuer mới.

Không giữ private key cũ sống vô thời hạn chỉ để có thể rollback; cân bằng khả năng phục hồi với rủi ro key compromise.

## 12. Consumer hoạt động lâu dài và không thể cập nhật ngay

### 12.1. Mobile application

Mobile app có thể không được cập nhật ngay vì người dùng chưa cài bản mới, store review/rollout theo phần trăm, thiết bị cũ không còn được hỗ trợ hoặc app có thể offline nhiều ngày.

Thiết kế minimum supported version/deadline, remote configuration có xác thực nếu cần điều khiển rollout, không để token cũ sống lâu chỉ để hỗ trợ app cũ, có upgrade/re-auth flow rõ ràng, sau deadline reject client/profile cũ theo policy và theo dõi version client mà không đưa dữ liệu nhạy cảm vào token.

### 12.2. Partner integration

Đối tác có thể có chu kỳ triển khai và phê duyệt riêng. Cần cung cấp contract mới và test vectors, JWKS/discovery endpoint, ngày bắt đầu nhận token mới, ngày ngừng nhận token cũ, hướng dẫn error handling, kênh liên hệ sự cố và sandbox.

Không để partner tự chọn issuer hoặc audience tùy ý. Mỗi partner/client cần trust profile và quyền cụ thể.

### 12.3. Background worker và queue

Worker có thể xử lý message cũ sau khi API đã chuyển issuer. Không lưu bearer token dài hạn trong message để worker dùng lại.

Worker nên xác thực workload identity, đọc business context tối thiểu, lấy credential mới theo audience/profile hiện hành, dùng delegation assertion đã được bảo vệ nếu cần giữ subject, đánh giá lại quyền ở thời điểm thực thi theo policy và xử lý message hết hạn/contract version cũ.

Dead-letter queue và retry topic phải có retention và migration plan; không replay payload cũ mà bỏ qua authorization hiện tại.

### 12.4. Consumer không thể nâng cấp

Nếu consumer không thể hỗ trợ contract mới, các lựa chọn là adapter/gateway migration có scope hẹp và end date, token exchange tại boundary được tin cậy, phiên bản API riêng có deadline decommission, hoặc disable integration và yêu cầu nâng cấp.

Adapter không được biến token cũ thành quyền rộng hơn. Nó phải xác minh token nguồn, kiểm tra client/resource, tạo token mới có scope tối thiểu và audit chuyển đổi.

## 13. JWKS, discovery và cache trong quá trình đổi issuer

### 13.1. Pre-publish metadata

Trước khi phát hành token từ issuer mới, xác nhận discovery metadata đúng issuer exact string, jwks_uri trỏ đúng endpoint thuộc trust domain, TLS certificate và DNS hợp lệ, JWKS có public key tương ứng kid sẽ dùng, cache/CDN có thể lấy dữ liệu mới và không có private key material trong JWKS.

### 13.2. Key overlap không thay thế issuer overlap

Hai issuer có thể dùng key material giống nhau nhưng vẫn là hai trust identity khác nhau. Ngược lại, một issuer có thể rotation nhiều key. Không suy ra issuer chỉ từ kid hoặc key thumbprint.

Issuer selection phải diễn ra theo trust configuration; key selection diễn ra trong namespace issuer tương ứng.

### 13.3. Cache cũ và unknown kid

Consumer có thể nhận token issuer mới nhưng JWKS cache chưa có key mới. Cần refresh có kiểm soát khi unknown kid, single-flight, timeout, rate limit và fail-closed. Không dùng JWKS URI từ token chưa xác minh.

### 13.4. Cache metadata không được tồn tại lâu hơn migration policy

Discovery/JWKS cache TTL ảnh hưởng tốc độ chuyển đổi và decommission. Đặt giới hạn stale, có invalidation path và theo dõi cache age. Trong emergency issuer/key compromise, stale-if-error không được tiếp tục tin key đã bị thu hồi.

## 14. Quy tắc xử lý lỗi

### 14.1. Phân biệt authentication và dependency failure

| Tình huống | Kết quả xác minh | Cách biểu diễn thường gặp |
| --- | --- | --- |
| Issuer không nằm trong trust allowlist | Token không được tin | 401 invalid_token |
| Issuer được tin nhưng chữ ký sai | Token không hợp lệ | 401 invalid_token |
| Audience không khớp resource | Token không dành cho API | 401 invalid_token |
| Token type/profile không đúng | Sai loại credential | 401 invalid_token |
| JWKS không truy cập được và không có key dùng được | Không thể xác minh | 503 hoặc lỗi dependency theo contract |
| Token hợp lệ nhưng thiếu scope | Đã xác thực, không đủ quyền | 403 insufficient_scope hoặc policy error |
| Introspection endpoint lỗi | Không xác định trạng thái opaque token | Fail closed, dependency unavailable |

Mã HTTP/OAuth cụ thể phải theo API contract và RFC áp dụng. Điều quan trọng là không chuyển dependency failure thành allow.

### 14.2. Không tiết lộ thông tin trust nội bộ

Response client không nên chứa JWKS URI nội bộ, hostname/network topology, chi tiết key identifier nhạy cảm, stack trace, raw token hoặc claims nhạy cảm.

Ghi log server với mã lỗi và correlation ID đã redact.

## 15. Pseudocode xác minh trong migration window

### 15.1. Chọn trust profile theo issuer exact

~~~text
function authenticateAccessToken(token, resource):
    header = parseProtectedHeaderWithLimits(token)
    untrustedClaims = parseClaimsWithoutTrust(token)

    issuer = untrustedClaims.iss
    profile = trustRegistry.findExactIssuer(issuer)

    if profile is absent:
        return INVALID_TOKEN

    if resource not in profile.allowedResources:
        return INVALID_TOKEN

    require header.alg in profile.allowedAlgorithms
    require header.typ matches profile.expectedTokenType

    keySet = jwksProvider.getForTrustedIssuer(profile)
    key = selectUniqueKey(keySet, header.kid, header.alg)

    if key is absent:
        keySet = jwksProvider.refreshOnce(profile)
        key = selectUniqueKey(keySet, header.kid, header.alg)

    if key is absent:
        return INVALID_TOKEN_OR_DEPENDENCY_FAILURE

    require verifyJwsSignature(token, key, header.alg)
    claims = parseVerifiedClaims(token)

    require claims.iss == profile.issuer
    require resource in claims.aud
    require claims.exp is valid
    require claims.nbf is valid when present
    require validateProfileClaims(claims, profile)
    require validateAuthorization(claims, resource)

    return AUTHENTICATED
~~~

Đoạn mã là pseudocode minh họa. Việc parse iss trước chữ ký chỉ dùng để chọn trong registry đã cấu hình; mọi quyết định tin cậy phải chờ chữ ký và claims được xác minh. Không dùng issuer chưa xác minh để tạo cấu hình hoặc thực hiện network fetch tùy ý.

### 15.2. Không dùng fallback token type

~~~text
function validateEndpointCredential(token, endpoint):
    expected = endpoint.allowedTokenProfiles
    tokenProfile = identifyProfileFromTrustedConfiguration(token)

    if tokenProfile not in expected:
        return REJECT

    return validateUsingExactProfile(token, tokenProfile)
~~~

Không thử lần lượt ID Token validator, access-token validator, refresh-token validator rồi chấp nhận validator nào thành công. Endpoint phải biết loại credential được phép.

## 16. Ma trận kiểm thử issuer migration

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| IS-01 | Token issuer cũ, consumer còn trong migration window | Chấp nhận nếu tuple cũ vẫn được phép và token hợp lệ |
| IS-02 | Token issuer mới, consumer đã hỗ trợ | Chấp nhận theo JWKS/profile mới |
| IS-03 | Issuer lạ không nằm trong registry | Reject |
| IS-04 | Issuer A nhưng dùng key của issuer B | Reject |
| IS-05 | iss khác một dấu slash hoặc hostname | Reject nếu exact issuer không khớp |
| IS-06 | Issuer mới chưa có JWKS key tương ứng | Fail closed; dependency/unknown-key path |
| IS-07 | Subject cũ và mới được mapping sai | Test phát hiện account collision |
| IS-08 | Issuer cũ đã hết migration window | Reject token cũ |
| IS-09 | Refresh token cũ tiếp tục mint token cũ | Phát hiện và chặn theo retirement policy |
| IS-10 | Token exchange từ issuer cũ sang mới | Chỉ cấp nếu subject, client, resource và scope được phép |

## 17. Ma trận kiểm thử audience migration

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| AU-01 | Audience mới khớp resource | Accept nếu các kiểm tra khác hợp lệ |
| AU-02 | Chỉ có audience cũ trong thời gian tương thích | Accept chỉ khi resource được cấu hình cho tuple cũ |
| AU-03 | Audience không khớp | Reject |
| AU-04 | Audience là array có resource hiện tại | Accept theo profile và policy |
| AU-05 | Audience array chứa nhiều resource không cùng trust boundary | Reject hoặc không phát hành theo policy |
| AU-06 | Audience có prefix giống resource nhưng không exact match | Reject |
| AU-07 | Token audience gateway gửi trực tiếp tới downstream | Reject nếu downstream không phải audience |
| AU-08 | Token cũ được sửa aud mà không ký lại | Chữ ký fail |
| AU-09 | Token mới có audience mới nhưng scope cũ quá rộng | Reject authorization |
| AU-10 | Hết migration window nhưng audience cũ vẫn được dùng | Reject và cảnh báo consumer còn sót |

## 18. Ma trận kiểm thử token type/profile migration

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| TP-01 | Access token profile mới với typ đúng | Accept nếu claims và signature hợp lệ |
| TP-02 | ID Token gửi tới resource server | Reject |
| TP-03 | Refresh token gửi tới API | Reject |
| TP-04 | Token có chữ ký hợp lệ nhưng typ sai | Reject |
| TP-05 | Token thiếu claim bắt buộc của profile mới | Reject |
| TP-06 | Custom legacy profile trong migration window | Chỉ accept theo cấu hình legacy cụ thể |
| TP-07 | Legacy profile sau deadline | Reject |
| TP-08 | JWT access token chuyển sang opaque | Dùng đúng introspection path |
| TP-09 | Opaque token bị gửi tới endpoint chỉ chấp nhận JWT | Reject |
| TP-10 | Introspection unavailable | Fail closed, không coi token là active |
| TP-11 | Token có custom token_use mâu thuẫn typ | Reject |
| TP-12 | ID Token có aud là client ID nhưng API mong resource URI | Reject |

## 19. Ma trận rollout, rollback và consumer còn hoạt động

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| RO-01 | Consumer mới triển khai trước issuer mới | Vẫn xử lý contract cũ, sẵn sàng nhận contract mới |
| RO-02 | Canary issuer mới | Chỉ nhóm được chọn nhận token mới |
| RO-03 | Tăng tỷ lệ canary khi lỗi vượt ngưỡng | Rollout dừng và kích hoạt rollback đã định |
| RO-04 | Rollback consumer sau khi token mới đã phát hành | Consumer cũ không nhận token mới; issuer/traffic được điều phối theo rollback plan |
| RO-05 | Mobile app cũ còn hoạt động | Có minimum version/deadline hoặc compatibility path hữu hạn |
| RO-06 | Partner chưa chuyển đổi | Theo dõi owner/deadline; không mở trust toàn cục |
| RO-07 | Worker xử lý message cũ | Lấy credential hiện hành và kiểm tra authorization |
| RO-08 | Refresh token cũ còn khả năng mint legacy token | Revoke/retire hoặc migrate refresh family |
| RO-09 | Traffic legacy bằng 0 nhưng token cũ chưa hết hạn | Chưa decommission chỉ dựa trên traffic |
| RO-10 | Hết compatibility window | Gỡ trust cũ và xác minh request cũ bị reject |

## 20. Quan sát và tiêu chí hoàn tất

### 20.1. Metrics

Theo dõi request count theo issuer/profile/audience đã chuẩn hóa, tỷ lệ authentication success/failure theo từng tuple, issuer mismatch/unknown issuer, invalid audience, wrong token type/profile, unknown kid/JWKS refresh/cache age, introspection success/failure/latency, refresh token grant theo client/issuer, token exchange success/failure theo target resource, authorization denied sau authentication và traffic của consumer/client version cũ.

Không dùng raw token, email, subject hoặc kid tùy ý làm metric label không giới hạn. Điều này có thể gây rò rỉ dữ liệu hoặc cardinality explosion.

### 20.2. Log và audit

Có thể ghi issuer đã chuẩn hóa, profile ID, audience/resource ID, client ID đã được xác minh, kết quả validation, nhóm lỗi và correlation ID.

Không ghi raw bearer token, refresh token, private key, toàn bộ claims cá nhân hoặc secret. Log cần có access control và retention policy.

### 20.3. Tiêu chí dừng rollout

Tạm dừng mở rộng nếu authentication failure tăng vượt ngưỡng, consumer trọng yếu không xác minh được token mới, có token bị chấp nhận sai issuer/audience/type, JWKS/discovery/introspection không ổn định, subject mapping gây collision/truy cập nhầm tài khoản, refresh token cũ tiếp tục phát hành token ngoài dự kiến hoặc không thể rollback theo kế hoạch.

### 20.4. Tiêu chí decommission

Chỉ kết thúc khi không còn issuance theo contract cũ, không còn refresh session có thể tạo token cũ, consumer active đã chuyển hoặc bị disable, partner/mobile/worker đã được xử lý, token cũ đã hết hạn hoặc bị revoke theo policy, legacy tuple bị reject ở mọi resource server, cấu hình cũ/trust anchor/secret không còn được sử dụng và audit/runbook phản ánh trạng thái cuối.

## 21. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Hậu quả | Cách xử lý |
| --- | --- | --- | --- |
| Đổi issuer chỉ ở issuer server | Quên consumer | API từ chối token mới | Consumer-first rollout và trust registry |
| Chấp nhận mọi issuer | Muốn tương thích nhanh | Token từ issuer lạ được tin | Exact allowlist và deadline |
| Gộp JWKS cache giữa issuer | Chỉ dùng kid để lookup | Chọn nhầm key | Namespace theo issuer |
| Sửa iss trong token cũ | Nghĩ claims có thể rewrite | Chữ ký không hợp lệ | Phát hành token mới hoặc exchange |
| Thêm audience chung | Tránh lỗi consumer | Mở rộng recipient và blast radius | Audience riêng theo resource |
| Chấp nhận substring audience | So sánh tiện lợi | Resource không dự định có thể nhận token | Exact matching |
| Dùng ID Token gọi API | Nhầm JWT với access token | Sai token semantics | Validate đúng token profile |
| Bỏ qua typ | Chỉ xác minh signature | Token sai loại được chấp nhận | Kiểm tra profile và endpoint context |
| Cho refresh token cũ tồn tại mãi | Chỉ drain access token | Legacy issuance tiếp tục | Retire/revoke refresh family |
| Không tính mobile/partner | Chỉ nhìn deployment nội bộ | Consumer cũ gây outage muộn | Inventory và deadline |
| Rollback bằng trust rộng | Thiếu rollback design | Security downgrade | Rollback theo tuple đã kiểm thử |
| Decommission khi traffic thấp | Bỏ qua token/job dài hạn | Consumer cũ hỏng hoặc trust bị gỡ quá sớm | Xét max lifetime, job cadence và owner |
| Mapping subject bằng email | Giả định email bất biến | Account collision | Account-linking có bằng chứng |
| Chuyển đồng thời mọi dimension | Không tách nguyên nhân | Khó debug và rollback | Staged migration hoặc tuple matrix |

## 22. Checklist di trú

### 22.1. Inventory và contract

- [ ] Đã liệt kê issuer, consumer, resource server và partner.
- [ ] Đã ghi nhận issuer exact string, audience, token type/profile và claims.
- [ ] Đã xác định consumer có hard-code claim hoặc issuer không.
- [ ] Đã xác định maximum token/refresh lifetime và cache TTL.
- [ ] Đã có owner cho mọi consumer còn hoạt động.
- [ ] Đã có target contract và test vectors.

### 22.2. Trust và validation

- [ ] Issuer mới nằm trong trust registry rõ ràng.
- [ ] JWKS/discovery endpoint được cấu hình tin cậy.
- [ ] Cache key được namespace theo issuer.
- [ ] Audience được so khớp theo resource.
- [ ] Token type/profile được kiểm tra.
- [ ] ID Token và refresh token không được dùng làm access token.
- [ ] Không có fallback validation rộng.
- [ ] Subject mapping/account linking được kiểm soát.

### 22.3. Rollout

- [ ] Consumer được triển khai trước khi phát hành token mới.
- [ ] Compatibility window có ngày kết thúc.
- [ ] Canary có metric và rollback trigger.
- [ ] Mobile, partner, worker và queue được tính đến.
- [ ] Refresh token cũ không tiếp tục mint legacy token ngoài kế hoạch.
- [ ] Rollback đã được thử trong môi trường đại diện.

### 22.4. Decommission

- [ ] Legacy issuance đã dừng.
- [ ] Token cũ hết hạn hoặc đã revoke.
- [ ] Không còn consumer active dùng contract cũ.
- [ ] Legacy tuple bị reject.
- [ ] JWKS/discovery/trust config cũ được gỡ đúng thời điểm.
- [ ] Secrets và key cũ được xử lý theo key lifecycle.
- [ ] Audit, dashboard và runbook đã cập nhật.

## 23. Câu hỏi tự kiểm tra

1. Issuer, audience và token type/profile khác nhau như thế nào?
2. Vì sao thay issuer có thể ảnh hưởng đến namespace của subject?
3. Tại sao không thể sửa iss hoặc aud trong JWT đã ký?
4. Vì sao resource server cần trust registry cho nhiều issuer?
5. Khi nào có thể chấp nhận old/new audience trong migration window?
6. Vì sao multi-audience token có thể làm tăng blast radius?
7. ID Token khác access token ở audience và consumer như thế nào?
8. RFC 9068 sử dụng typ nào cho JWT access token?
9. Vì sao không nên thử nhiều validator rồi chấp nhận validator nào thành công?
10. Token exchange giúp migration issuer/audience ra sao?
11. Vì sao refresh token cần được tính trong giai đoạn drain?
12. Cần xử lý mobile app và partner chậm nâng cấp như thế nào?
13. Rollback consumer sau khi issuer đã phát hành token mới có rủi ro gì?
14. Những điều kiện nào phải đạt trước khi decommission issuer cũ?

## 24. Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), claims iss, sub, aud, exp và cấu trúc JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), issuer/audience validation, token substitution và phân tách loại JWT.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068), profile access token và JOSE typ=at+jwt.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414), metadata và jwks_uri.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707), resource/audience trong yêu cầu cấp token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693), chuyển đổi token theo subject, actor và resource đích.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662), kiểm tra trạng thái opaque access token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009), thu hồi access token và refresh token.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), token endpoint, access token và refresh token.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750), cách sử dụng bearer access token và lỗi xác thực.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html), ID Token, audience/client và validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), bảo vệ OAuth flows và token handling.
