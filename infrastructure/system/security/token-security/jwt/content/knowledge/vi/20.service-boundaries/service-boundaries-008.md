# Nhiều bên phát hành và ánh xạ cấu hình theo danh sách tin cậy

Một API có thể nhận access token từ nhiều Identity Provider (IdP) hoặc Authorization Server, chẳng hạn hệ thống nhân sự nội bộ, nhà cung cấp danh tính doanh nghiệp và đối tác liên kết. Việc hỗ trợ nhiều issuer không có nghĩa là chấp nhận bất kỳ JWT nào có chữ ký hợp lệ. Mỗi issuer là một miền tin cậy riêng: hệ thống phải biết trước issuer nào được chấp nhận, khóa nào thuộc issuer đó, thuật toán nào được phép, token dành cho resource nào và claims của issuer được ánh xạ ra sao.

Bài học thuộc chương **Ranh giới dịch vụ** của module **Security – JSON Web Token (JWT)**. Nội dung tập trung vào thiết kế allowlist issuer, ánh xạ cấu hình tin cậy, lựa chọn JWKS an toàn, xác minh issuer/audience/token profile và chuẩn hóa claims từ nhiều nhà phát hành. Phạm vi áp dụng cho mọi nền tảng, ngôn ngữ và framework.

## 1. Vì sao một hệ thống cần hỗ trợ nhiều issuer?

Một tổ chức có thể dùng nhiều nguồn danh tính:

- IdP nội bộ cho nhân viên.
- IdP của công ty mẹ cho SSO.
- Nhà cung cấp danh tính của khách hàng doanh nghiệp.
- Authorization Server riêng cho một sản phẩm hoặc miền nghiệp vụ.
- Đối tác phát hành token cho một API tích hợp.
- Nhiều môi trường hoặc vùng triển khai có issuer khác nhau.

Resource server có thể cần chấp nhận token từ nhiều nguồn, nhưng phải giữ được ranh giới giữa các nguồn đó. Hai token có cùng subject hoặc cùng kid không có nghĩa chúng cùng một danh tính hay cùng một khóa.

Ví dụ, API nhận token từ hai issuer:

~~~text
Issuer A: https://login.corp.example
Issuer B: https://identity.partner.example
~~~

Cả hai issuer đều có thể phát hành JWT với claim sub là user-42. Đây không mặc nhiên là cùng một người. Trong JWT, subject cần được hiểu trong ngữ cảnh issuer; định danh an toàn thường là cặp (iss, sub).

### 1.1. Rủi ro khi chỉ kiểm tra chữ ký

Một JWT có chữ ký hợp lệ vẫn có thể không phù hợp với API:

- Được ký bởi issuer không nằm trong danh sách tin cậy.
- Dành cho một audience khác.
- Là ID Token nhưng bị sử dụng như access token.
- Dùng thuật toán không được profile của issuer cho phép.
- Có claims đúng cú pháp nhưng mang ý nghĩa khác với schema mà API mong đợi.
- Có subject trùng chuỗi với người dùng khác từ một issuer khác.

Chữ ký chỉ chứng minh dữ liệu khớp với khóa xác minh tương ứng. Hệ thống vẫn phải xác định khóa đó thuộc issuer nào và issuer đó có được phép cấp token cho API hay không.

## 2. Mỗi issuer là một miền cấu hình tin cậy riêng

Không nên có một cấu hình chung kiểu “mọi token đều dùng cùng JWKS, cùng thuật toán và cùng mapping claims”. Thay vào đó, tạo một trust profile riêng cho từng issuer được phép.

Một trust profile thường cần các thông tin:

| Thành phần | Vai trò |
| --- | --- |
| Issuer identifier | Định danh chính xác nguồn phát hành |
| Discovery/JWKS configuration | Vị trí metadata và tập khóa được tin cậy |
| Allowed algorithms | Danh sách thuật toán được phép cho issuer |
| Audience/resource | API hoặc resource mà token được phép gọi |
| Token profile/type | Phân biệt access token, ID token và loại token khác |
| Required claims | Các claim bắt buộc và kiểu dữ liệu |
| Claim mapping | Ánh xạ claim riêng của issuer sang mô hình nội bộ |
| Subject namespace | Cách định danh subject không va chạm giữa issuer |
| Tenant mapping | Cách xác định tenant và kiểm tra membership |
| Client/workload policy | Client nào được phép phát hành hoặc sử dụng token |
| Key rotation policy | Cache, refresh, rollover và xử lý khóa bị lộ |
| Revocation policy | Introspection, denylist, session state hoặc TTL |

Trust profile phải đến từ cấu hình được quản trị bởi hệ thống, ví dụ cấu hình triển khai, registry nội bộ có kiểm soát hoặc kho cấu hình được ký/kiểm duyệt. Không để người gửi request tự tạo một issuer mới bằng cách đưa URL tùy ý vào token.

### 2.1. Ví dụ danh sách issuer được tin cậy

~~~yaml
trusted_issuers:
  - id: corporate
    issuer: https://login.corp.example
    discovery_url: https://login.corp.example/.well-known/openid-configuration
    audiences:
      - https://billing-api.example
    allowed_algorithms:
      - RS256
    token_profile: oauth_access_token
    required_claims:
      - iss
      - sub
      - aud
      - exp
    claim_mapping: corporate_v1

  - id: partner
    issuer: https://identity.partner.example
    discovery_url: https://identity.partner.example/.well-known/openid-configuration
    audiences:
      - https://billing-api.example
    allowed_algorithms:
      - ES256
    token_profile: oauth_access_token
    required_claims:
      - iss
      - sub
      - aud
      - exp
      - tenant
    claim_mapping: partner_v2
~~~

Đây là cấu hình minh họa, không phải cú pháp bắt buộc của OIDC. Các giá trị issuer, discovery URL, audience, thuật toán và mapping phải được xác nhận với từng nhà phát hành và profile thực tế. Cấu hình phải được bảo vệ khỏi thay đổi trái phép và có audit.

### 2.2. Không suy ra trust từ tên miền gần giống

Không dùng quy tắc lỏng như:

- Issuer bắt đầu bằng một chuỗi domain.
- Hostname có chứa tên công ty.
- Chỉ kiểm tra cùng registrable domain.
- Chấp nhận mọi subdomain của một domain.
- Bỏ dấu slash cuối hoặc tự chuẩn hóa URL rồi coi hai issuer là một.

Issuer identifier là định danh theo profile. Hãy so khớp đúng giá trị đã cấu hình theo quy tắc so sánh của giao thức; không tự biến các issuer khác nhau thành tương đương. Nếu tổ chức muốn thay đổi issuer URL, cần quy trình migration có chủ đích và cập nhật trust profile.

## 3. Chọn issuer an toàn khi token chưa được xác minh

Resource server thường cần chọn cấu hình và khóa trước khi xác minh chữ ký. Claim iss nằm trong payload JWT, nhưng payload chưa được xác minh ở thời điểm đọc ban đầu. Vì vậy, giá trị iss chỉ được dùng như **gợi ý tra cứu** tới một trust profile đã có sẵn.

Quy trình an toàn:

1. Parse cấu trúc token bằng parser nghiêm ngặt và giới hạn kích thước đầu vào.
2. Đọc giá trị iss chưa xác minh như dữ liệu không tin cậy.
3. Tra cứu iss bằng phép so khớp chính xác trong allowlist issuer đã cấu hình.
4. Nếu không có issuer phù hợp, từ chối token.
5. Lấy thuật toán, JWKS/discovery và audience từ trust profile tương ứng.
6. Chọn khóa trong tập khóa đã gắn với issuer đó.
7. Xác minh chữ ký.
8. Sau khi xác minh thành công, kiểm tra lại iss trong payload phải khớp chính xác issuer của trust profile.
9. Kiểm tra audience, token type, thời hạn, claims và mapping theo profile đó.

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Parse cấu trúc với giới hạn đầu vào"]
    B --> C["Đọc iss chưa xác minh"]
    C --> D{"iss có trong trusted issuer registry?"}
    D -- "Không" --> X["Từ chối"]
    D -- "Có" --> E["Nạp trust profile của issuer"]
    E --> F["Chọn key trong JWKS đã tin cậy của issuer"]
    F --> G["Xác minh chữ ký với thuật toán allowlist"]
    G --> H{"Chữ ký hợp lệ?"}
    H -- "Không" --> X
    H -- "Có" --> I{"iss đã xác minh khớp profile?"}
    I -- "Không" --> X
    I -- "Có" --> J["Kiểm tra aud, typ, thời gian và schema"]
    J --> K["Ánh xạ claims theo profile issuer"]
    K --> L["Tạo security context nội bộ"]
~~~

### 3.1. Không dùng iss chưa xác minh để tải URL tùy ý

Một sai lầm nghiêm trọng là đọc iss, jku hoặc x5u từ token rồi gửi HTTP request tới URL đó để lấy khóa hoặc metadata. Kẻ tấn công có thể đưa URL trỏ tới:

- Máy chủ do họ kiểm soát.
- Địa chỉ nội bộ hoặc metadata service.
- Endpoint localhost hoặc private network.
- URL chuyển hướng sang một đích khác.
- Dịch vụ chậm hoặc phản hồi dữ liệu quá lớn để gây cạn tài nguyên.

Đây có thể trở thành Server-Side Request Forgery (SSRF), key substitution hoặc trust injection.

Không fetch discovery/JWKS từ URL tùy ý lấy trong token. URL phải đến từ trust profile đã được quản trị hoặc metadata discovery được xác minh theo issuer đã cấu hình. Nếu profile hỗ trợ tham số jku/x5u, chỉ chấp nhận theo một chính sách pinning/allowlist cụ thể; lựa chọn an toàn mặc định là không dùng chúng để thay nguồn khóa tin cậy.

### 3.2. OIDC Discovery phải được ràng buộc với issuer đã cấu hình

OpenID Connect Discovery có thể cung cấp metadata như issuer, authorization endpoint, token endpoint và jwks_uri. Khi dùng discovery:

- Bắt đầu từ issuer URL đã được quản trị và tin cậy.
- Tải metadata qua HTTPS với xác minh chứng chỉ.
- Xác nhận trường issuer trong metadata khớp chính xác issuer mong đợi.
- Chỉ dùng jwks_uri được chấp nhận từ metadata đã xác minh.
- Kiểm soát redirect, DNS/network egress, kích thước và timeout.
- Cache metadata/JWKS theo chính sách và có quy trình refresh.

Không coi một document discovery hợp lệ về cú pháp là nguồn tin cậy nếu nó không được ràng buộc với issuer mà tổ chức đã phê duyệt.

## 4. Phân vùng JWKS và lựa chọn khóa

Mỗi issuer có thể công bố một JWKS riêng. Khi xác minh token từ nhiều issuer, khóa phải được phân vùng theo issuer, không chỉ theo kid.

### 4.1. kid không phải định danh toàn cục

Header kid chỉ là key identifier trong ngữ cảnh nguồn khóa phù hợp. Hai issuer có thể cùng dùng kid là key-2026-01 nhưng public key hoàn toàn khác nhau.

Ví dụ:

| Issuer | kid | Khóa |
| --- | --- | --- |
| Corporate | key-2026-01 | Public key A |
| Partner | key-2026-01 | Public key B |

Không được tìm khóa trong một JWKS tổng hợp không phân biệt issuer rồi chọn khóa đầu tiên có kid khớp. Cache key nên bao gồm ít nhất issuer và kid; việc chọn khóa phải giới hạn trong JWKS của trust profile đã chọn.

### 4.2. Kiểm tra thuộc tính JWK

Khi chọn JWK, cần kiểm tra các thuộc tính liên quan:

- kty: loại khóa phù hợp với thuật toán.
- use: nếu có, phải phù hợp với mục đích ký/xác minh.
- key_ops: nếu có, phải cho phép verify.
- alg: nếu có, phải tương thích với thuật toán được profile cho phép.
- kid: định danh khóa trong tập khóa của issuer.
- Kích thước khóa và tham số: đáp ứng yêu cầu mật mã hiện hành.

Không chỉ dựa vào kid. Không dùng khóa mã hóa để xác minh chữ ký hoặc ngược lại. Không chấp nhận khóa yếu, tham số sai hoặc JWK không phù hợp với thuật toán.

### 4.3. Thuật toán phải được cấu hình ngoài token

Header alg do người gửi cung cấp và chưa đáng tin trước khi xác minh. Mỗi trust profile phải có allowlist thuật toán độc lập:

| Trust profile | Allowed algorithms minh họa |
| --- | --- |
| Corporate | RS256 |
| Partner | ES256 |

Không tự động chấp nhận mọi thuật toán mà thư viện hỗ trợ. Tránh thuật toán none, tránh nhầm lẫn giữa thuật toán MAC và chữ ký bất đối xứng, và không cho header token quyết định một thuật toán ngoài allowlist.

Nếu dùng HMAC, mọi bên có secret xác minh cũng có khả năng tạo MAC hợp lệ. Trong hệ thống có nhiều resource server hoặc nhiều miền vận hành, chữ ký bất đối xứng thường giúp giới hạn quyền phát hành vào issuer giữ private key.

### 4.4. Không fallback sang khóa của issuer khác

Nếu chữ ký không hợp lệ với JWKS của issuer được chọn, từ chối token. Không thử lần lượt khóa của tất cả issuer cho tới khi một khóa xác minh thành công.

Fallback như vậy làm mất ranh giới issuer: token có thể được xác minh bằng khóa của một issuer nhưng được diễn giải theo policy của issuer khác. Không thay đổi issuer profile chỉ vì một khóa khác tình cờ xác minh được chữ ký.

## 5. Quản lý JWKS cache và key rotation cho nhiều issuer

Mỗi issuer có chu kỳ rotation, cache header và độ sẵn sàng khác nhau. Không dùng một cache không phân biệt issuer hoặc một TTL duy nhất nếu các nhà phát hành có chính sách khác nhau.

### 5.1. Cache theo issuer

Cache nên gắn với issuer/trust profile:

~~~text
cache_key = (issuer_identifier, jwks_uri, key_id)
~~~

Cache entry có thể lưu:

- JWKS đã tải và thời điểm tải.
- HTTP cache metadata theo chính sách.
- Key fingerprint và thuộc tính JWK.
- Trạng thái refresh đang diễn ra.
- Lần refresh gần nhất và giới hạn tần suất.

Không cache khóa chỉ theo kid vì kid có thể trùng giữa issuer.

### 5.2. Xử lý unknown kid

Khi token có kid chưa thấy:

1. Chỉ refresh JWKS của issuer đã chọn.
2. Giới hạn số lần refresh để tránh attacker gửi nhiều kid ngẫu nhiên gây request storm.
3. Đồng bộ refresh giữa các request để tránh nhiều lần tải cùng lúc.
4. Nếu key vẫn không tồn tại sau refresh, từ chối token.
5. Không thử JWKS URL hoặc issuer khác.

Không nên giữ khóa cũ vô thời hạn chỉ vì endpoint JWKS đang lỗi. Chính sách stale-key phải cân bằng availability và khả năng thu hồi khóa bị xâm phạm; với sự cố compromise, cần cơ chế khẩn cấp để ngừng tin khóa.

### 5.3. Rotation bình thường

Một quy trình rollover phổ biến:

1. Issuer công bố public key mới trong JWKS.
2. Resource server refresh JWKS và nhận biết key mới.
3. Issuer bắt đầu ký token bằng private key mới.
4. Issuer tiếp tục giữ public key cũ trong JWKS đủ lâu cho token đã phát hành và cache.
5. Sau khi token cũ hết hiệu lực và thời gian chuyển tiếp kết thúc, issuer gỡ public key cũ.

Thời gian giữ khóa cũ phải tính TTL access token, clock skew, cache JWKS và độ trễ triển khai. Các issuer có thể có lịch khác nhau.

### 5.4. Khi khóa bị compromise

Rotation bình thường khác xử lý khẩn cấp:

- Đánh dấu khóa bị compromise và ngừng chấp nhận ngay theo incident policy.
- Cập nhật trust profile/JWKS cache và phát tín hiệu refresh khẩn cấp.
- Không tiếp tục stale-cache khóa bị nghi ngờ.
- Đánh giá token được ký trong khoảng thời gian bị ảnh hưởng.
- Thu hồi token/grant hoặc yêu cầu đăng nhập lại nếu cần.
- Kiểm tra các resource server đã nhận cập nhật hay chưa.

Không chỉ chờ TTL cache hết nếu có bằng chứng khóa đã bị lộ.

## 6. Audience, token type và profile phải gắn với từng issuer

Issuer tin cậy không có nghĩa mọi token từ issuer đó đều dùng được cho mọi API.

### 6.1. Audience phải khớp resource server

Mỗi trust profile cần khai báo audience/resource mà API chấp nhận. Resource server kiểm tra aud sau khi chữ ký được xác minh.

Ví dụ:

~~~json
{
  "iss": "https://login.corp.example",
  "sub": "employee-42",
  "aud": "https://billing-api.example",
  "scope": "invoice:read",
  "exp": 2000000000
}
~~~

Token được phát hành cho Billing API không nên được chấp nhận tại Payment API chỉ vì hai API cùng tin issuer.

Nếu một issuer phát hành token cho nhiều resource, hãy xác định audience allowlist theo từng service. Không dùng một audience wildcard rộng cho toàn bộ hệ thống nếu không có mô hình bảo vệ rõ ràng.

### 6.2. Phân biệt access token và ID Token

OIDC ID Token được phát hành để client xác nhận kết quả đăng nhập và thông tin xác thực người dùng. Access token được phát hành để gọi resource server. Hai loại token có mục đích và quy tắc xác minh khác nhau.

Resource server không được chấp nhận ID Token chỉ vì:

- Token có chữ ký hợp lệ.
- Issuer là IdP quen thuộc.
- Token có claim sub và email.
- Token chưa hết hạn.

Hãy xác định token profile, audience và loại token. Với JWT access token theo RFC 9068, profile sử dụng typ là at+jwt trong JOSE header theo quy định của profile. Chỉ áp dụng profile này khi issuer và resource server đã thống nhất hỗ trợ.

Không dùng chung một validator dễ dãi cho ID Token, access token, logout token và token nội bộ.

### 6.3. Client identity và user identity

Các claim có thể biểu diễn các principal khác nhau:

- sub: subject của token, có thể là người dùng hoặc workload tùy grant/profile.
- client_id: ứng dụng/client mà token được cấp cho hoặc gắn với.
- azp: authorized party trong một số ngữ cảnh OIDC.
- actor/delegation claim: service thực hiện hành động thay mặt subject.

Không tự suy ra sub luôn là người dùng cuối. Mỗi issuer profile cần quy định token đại diện user, client hay workload và mapping tương ứng.

## 7. Ánh xạ claims từ nhiều issuer về mô hình nội bộ

Các issuer có thể dùng tên claim và ngữ nghĩa khác nhau. Một nguồn dùng groups, nguồn khác dùng roles, nguồn thứ ba dùng một URI claim. Resource service nên có một mô hình nội bộ thống nhất, nhưng mapping phải tường minh và theo từng issuer.

### 7.1. Ví dụ hai issuer có schema khác nhau

Issuer Corporate:

~~~json
{
  "iss": "https://login.corp.example",
  "sub": "employee-42",
  "groups": ["finance-readers"],
  "tenant": "corp-vn"
}
~~~

Issuer Partner:

~~~json
{
  "iss": "https://identity.partner.example",
  "sub": "p-8842",
  "roles": ["billing_viewer"],
  "org_id": "partner-17"
}
~~~

Hai payload không thể được diễn giải bằng một mapping chung tùy tiện. Hệ thống cần quy định:

| Khái niệm nội bộ | Corporate mapping | Partner mapping |
| --- | --- | --- |
| External subject | sub | sub |
| Tenant source | tenant | org_id |
| Group/role source | groups | roles |
| Issuer namespace | corporate | partner |
| Canonical permission | finance.invoice.read | billing.invoice.read |

Mapping cần chuyển đổi giá trị đã được xác minh, không tự nâng quyền chỉ vì tên group/role nghe có vẻ đặc quyền.

### 7.2. Dùng canonical security context

Sau khi xác minh token và áp dụng mapping của issuer, hệ thống có thể tạo một context nội bộ:

~~~json
{
  "principal": {
    "issuer_id": "corporate",
    "issuer": "https://login.corp.example",
    "subject": "employee-42"
  },
  "actor": {
    "type": "user",
    "client_id": "finance-portal"
  },
  "tenant": "corp-vn",
  "permissions": [
    "finance.invoice.read"
  ],
  "authentication_context": {
    "token_profile": "oauth_access_token",
    "validated": true
  }
}
~~~

Đây là cấu trúc nội bộ minh họa, không phải JWT chuẩn. Chỉ tạo context sau khi token đã được xác minh và schema/mapping hợp lệ. Không nhận context này trực tiếp từ client.

### 7.3. Subject phải được namespace theo issuer

Không dùng sub đơn lẻ làm khóa tài khoản toàn cục khi có nhiều issuer.

Ví dụ:

| Issuer | sub | External principal key |
| --- | --- | --- |
| Corporate | user-42 | (corporate, user-42) |
| Partner | user-42 | (partner, user-42) |

Hai principal trên là hai định danh riêng cho tới khi có quy trình liên kết tài khoản đã xác minh.

Không tự động hợp nhất tài khoản chỉ vì:

- Email giống nhau.
- Tên hiển thị giống nhau.
- sub giống nhau.
- Hai issuer cùng trả về một trường employee_id chưa được xác thực nguồn.

Account linking cần chứng minh quyền kiểm soát cả hai danh tính hoặc được quản trị viên phê duyệt theo quy trình tin cậy. Email chỉ nên dùng theo policy cụ thể; nếu dựa vào email, phải xét issuer, trạng thái verified và khả năng thay đổi/được tái sử dụng.

### 7.4. Tenant không đồng nghĩa với issuer

Một issuer có thể phát hành token cho nhiều tenant; một tenant cũng có thể sử dụng nhiều issuer. Không suy ra tenant chỉ từ hostname issuer nếu mô hình thực tế không bảo đảm quan hệ một-một.

Tenant mapping cần:

- Claim source được định nghĩa theo issuer profile.
- Kiểm tra kiểu, miền giá trị và trạng thái tenant.
- Kiểm tra subject/client có thuộc tenant đó không.
- Không cho client tự override tenant bằng header hoặc request parameter.
- Xác định hành vi khi token thiếu tenant hoặc có tenant không được ánh xạ.

## 8. Ánh xạ role, group và scope mà không nâng quyền

Tên claim và giá trị claim từ nhiều IdP không có ngữ nghĩa đồng nhất. Ví dụ group admin ở một IdP có thể chỉ là nhóm quản trị danh bạ, không phải quyền quản trị Billing API.

### 8.1. Mapping phải là allowlist

Ví dụ:

~~~yaml
claim_mappings:
  corporate_v1:
    source_claim: groups
    value_mapping:
      finance-readers:
        - finance.invoice.read
      finance-approvers:
        - finance.invoice.read
        - finance.invoice.approve

  partner_v2:
    source_claim: roles
    value_mapping:
      billing_viewer:
        - finance.invoice.read
      billing_operator:
        - finance.invoice.read
        - finance.invoice.update
~~~

Mapping trên chỉ minh họa. Giá trị không có trong allowlist nên bị bỏ qua hoặc khiến token bị từ chối tùy policy; không tự chuyển mọi group lạ thành role cùng tên.

### 8.2. Không hợp nhất quyền theo kiểu permissive union

Nếu token có nhiều claim như groups, roles, permissions và scope, không tự động cộng tất cả quyền từ mọi claim. Điều đó có thể làm quyền tăng ngoài dự kiến.

Hãy xác định:

- Claim nào là nguồn quyền có thẩm quyền cho issuer đó.
- Scope là quyền OAuth cấp cho client hay quyền nghiệp vụ của subject.
- Group nào được ánh xạ sang canonical permission.
- Quy tắc khi hai claim mâu thuẫn.
- Quyền nào cần tra cứu lại từ policy engine hoặc dữ liệu nghiệp vụ.

Không dùng claim không được hiểu để cấp quyền. Unknown role/group không nên mặc định có quyền hoặc được ánh xạ sang role gần giống.

### 8.3. Scope không thay thế kiểm tra tài nguyên

Ngay cả khi mapping tạo canonical permission invoice.read, resource service vẫn phải kiểm tra quyền trên từng invoice, tenant và trạng thái nghiệp vụ. Một permission cấp API không mặc nhiên cho phép đọc mọi bản ghi.

## 9. Cấu hình trust registry phải được bảo vệ

Danh sách issuer tin cậy là một phần của security boundary. Nếu kẻ tấn công có thể thêm issuer hoặc thay JWKS URL, họ có thể khiến resource server tin token do họ phát hành.

### 9.1. Kiểm soát thay đổi cấu hình

- Chỉ nhóm/role quản trị được phép thay đổi trust profile.
- Dùng review/approval cho thay đổi issuer, discovery URL, JWKS URI, thuật toán và claim mapping.
- Lưu lịch sử thay đổi và người thực hiện.
- Phân biệt cấu hình production, staging và development.
- Không cho cấu hình test issuer đi vào production.
- Bảo vệ secret/credential dùng để gọi metadata endpoint nếu có.
- Có khả năng rollback cấu hình tin cậy về phiên bản trước.

### 9.2. Discovery/JWKS endpoint và SSRF

Khi tải metadata/JWKS:

- Chỉ dùng HTTPS và xác minh chứng chỉ.
- Giới hạn hostname/endpoint theo trust profile.
- Kiểm soát DNS resolution và network egress để tránh truy cập địa chỉ nội bộ không được phép.
- Giới hạn redirect, timeout, response size và content type.
- Không chấp nhận URL từ untrusted header hoặc claim.
- Kiểm tra issuer trong metadata khớp issuer đã cấu hình.
- Không cho JWKS document chứa key tùy ý thay đổi thuật toán được cho phép.

### 9.3. Không trộn môi trường

Issuer staging và production phải có trust profile, audience và khóa riêng. Token phát hành từ staging không được chấp nhận ở production chỉ vì cùng tên sub hoặc cùng thuật toán.

Không dùng chung signing key giữa môi trường. Nếu một khóa staging bị lộ, blast radius không được lan sang production.

## 10. Quy trình xác minh token nhiều issuer

Một validator nhiều issuer có thể được tổ chức theo các bước sau:

1. **Giới hạn đầu vào:** kiểm tra kích thước, số segment, encoding và giới hạn parser.
2. **Parse untrusted envelope:** đọc header và payload cần thiết cho routing, nhưng chưa tin bất kỳ claim nào.
3. **Resolve issuer:** tra iss bằng exact match trong trusted issuer registry.
4. **Load issuer profile:** lấy algorithm allowlist, discovery/JWKS, audience, token type và schema.
5. **Select key:** tìm kid trong JWKS thuộc đúng issuer; kiểm tra kty/use/key_ops/alg.
6. **Verify signature:** xác minh bằng thuật toán đã cấu hình; không fallback issuer/key.
7. **Confirm issuer:** so sánh iss đã xác minh với issuer của profile.
8. **Validate token profile:** kiểm tra typ, access-token profile, aud, exp, nbf, iat và các claim bắt buộc.
9. **Validate schema:** kiểm tra kiểu, duplicate names, miền giá trị và các claim quan hệ.
10. **Map claims:** áp dụng mapping riêng của issuer; tạo canonical principal, tenant, actor và permission.
11. **Authorize resource:** kiểm tra quyền trên operation, object và tenant.
12. **Audit:** ghi issuer ID, subject namespace, client, audience, mapping version và kết quả; không ghi raw token.

### 10.1. Pseudocode trung lập ngôn ngữ

~~~text
function validate_multi_issuer_token(token):
    enforce_input_limits(token)

    untrusted = parse_untrusted_jwt_envelope_strictly(token)
    issuer_hint = untrusted.payload.iss

    profile = trusted_issuer_registry.find_exact(issuer_hint)
    if profile is missing:
        reject("untrusted_issuer")

    require(untrusted.header.alg in profile.allowed_algorithms)

    jwks = load_jwks_from_trusted_profile(profile)
    key = jwks.find_compatible_key(
        kid = untrusted.header.kid,
        alg = untrusted.header.alg,
        use = "sig"
    )
    if key is missing:
        refresh_jwks_with_rate_limit(profile)
        key = jwks.find_compatible_key(...)

    require(key exists)
    require(verify_signature(token, key, profile.allowed_algorithms))

    claims = parse_verified_payload_strictly(token)
    require(claims.iss == profile.issuer)
    require(audience_matches(claims.aud, profile.audiences))
    require(token_type_matches(claims, untrusted.header, profile))
    validate_claim_schema(claims, profile.required_claims, profile.schema)

    principal = map_identity(claims, profile.claim_mapping)
    require(principal is valid)

    return authorize_resource(principal)
~~~

Đây là pseudocode mô tả luồng, không phải triển khai thư viện hoàn chỉnh. Trong thực tế cần xử lý đúng từng token profile, JWS/JWE, parser JSON, cache và lỗi mạng. Giá trị iss chưa xác minh chỉ dùng để tìm profile đã có sẵn; nó không được dùng để tải URL tùy ý hoặc quyết định quyền.

## 11. Lỗi và hành vi fail-closed

Trong xác minh nhiều issuer, một lỗi cấu hình hoặc lỗi mạng không nên khiến hệ thống tự chuyển sang một issuer khác hay nới lỏng kiểm tra.

| Tình huống | Hành vi an toàn |
| --- | --- |
| Issuer không nằm trong registry | Từ chối |
| Issuer chỉ khác chữ hoa/thường hoặc URL normalization | Từ chối nếu không khớp định danh theo profile |
| Discovery metadata issuer không khớp | Từ chối profile/refresh |
| JWKS URL ngoài allowlist | Không fetch |
| kid không tồn tại sau refresh có giới hạn | Từ chối |
| Chữ ký không hợp lệ | Từ chối; không thử key của issuer khác |
| alg không nằm trong allowlist | Từ chối |
| aud không phù hợp | Từ chối |
| ID Token được gửi tới API access token | Từ chối |
| Claim mapping không biết role/group | Không cấp quyền từ giá trị đó; từ chối nếu claim bắt buộc |
| Claim tenant không ánh xạ được | Từ chối truy cập |
| Discovery/JWKS timeout | Không tin key mới chưa xác minh; áp dụng stale-key policy đã định nghĩa |
| Cấu hình issuer bị thay đổi bất thường | Dừng chấp nhận thay đổi, cảnh báo và rollback theo incident process |

Fail-closed không nhất thiết có nghĩa toàn bộ hệ thống phải ngừng hoạt động khi một issuer không khả dụng. Hệ thống có thể tiếp tục xử lý token của issuer khác nếu trust profile của issuer đó còn hợp lệ. Không được dùng lỗi của issuer A làm lý do nới lỏng kiểm tra issuer B.

## 12. Nhiều issuer và quản lý danh tính người dùng

### 12.1. Định danh principal bằng issuer và subject

Khóa định danh ngoài nên bao gồm issuer namespace:

~~~text
principal_key = (issuer_id, subject)
~~~

Không dùng email hoặc sub đơn lẻ làm khóa toàn cục nếu nhiều issuer có thể phát hành các giá trị trùng.

### 12.2. Account linking phải là hành động có xác minh

Khi người dùng muốn liên kết tài khoản Corporate với Partner:

1. Người dùng đã xác thực với tài khoản hiện tại.
2. Hệ thống yêu cầu xác thực riêng với issuer thứ hai.
3. Xác minh cả hai danh tính theo trust profile tương ứng.
4. Kiểm tra chính sách liên kết, tenant và quyền.
5. Yêu cầu xác nhận rõ ràng hoặc phê duyệt quản trị khi cần.
6. Lưu mapping giữa hai principal với audit trail.
7. Có cơ chế hủy liên kết và xử lý khi một issuer bị thu hồi trust.

Không tự động liên kết chỉ vì hai token có cùng email. Email có thể thay đổi, chưa verified, được tái sử dụng hoặc có quy tắc uniqueness khác nhau giữa nhà cung cấp.

### 12.3. Issuer bị ngừng tin cậy

Nếu tổ chức ngừng tin một issuer:

- Vô hiệu hóa trust profile hoặc chuyển trạng thái sang disabled.
- Ngừng chấp nhận token mới từ issuer đó.
- Xử lý cache validator và JWKS để không tiếp tục xác minh token ngoài policy.
- Thu hồi/đánh giá session, grant và token đã phát hành theo mức độ sự cố.
- Xử lý account linking phụ thuộc issuer đó.
- Kiểm tra audit để xác định principal hoặc tenant bị ảnh hưởng.

Không xóa lịch sử issuer khỏi audit vì cần giữ khả năng điều tra các quyết định trước đó.

## 13. Tình huống thực tế

### Tình huống A — Hai issuer có cùng sub

Corporate và Partner đều phát hành sub=user-42. Ứng dụng dùng sub làm khóa tài khoản và vô tình gộp hai người dùng thành một.

**Bài học:** định danh principal bằng cặp issuer và subject; account linking cần quy trình xác minh riêng.

### Tình huống B — kid trùng giữa hai JWKS

Hai issuer cùng dùng kid=key-01. Validator tìm trong một cache toàn cục và lấy public key của issuer sai.

**Bài học:** phân vùng JWKS/cache theo issuer; không fallback sang key của issuer khác.

### Tình huống C — Token tự chỉ định JWKS URL

API đọc jku trong JOSE header rồi tải khóa từ URL do token cung cấp. Kẻ tấn công kiểm soát URL và phát hành token bằng khóa riêng của họ.

**Bài học:** JWKS/discovery phải được gắn với trust profile đã quản trị; không fetch URL tùy ý từ token.

### Tình huống D — Issuer hợp lệ nhưng audience sai

Billing API tin Corporate issuer. Một ID Token hoặc access token dành cho HR API được gửi tới Billing API và chữ ký hợp lệ.

**Bài học:** trust issuer không đồng nghĩa chấp nhận mọi token của issuer; phải kiểm tra audience và token profile.

### Tình huống E — Group admin được ánh xạ thành quyền quản trị API

Partner gửi roles=[admin]. Mapping chung tự động chuyển admin thành system.admin dù role đó chỉ có nghĩa quản trị danh bạ ở Partner.

**Bài học:** mapping role/group theo từng issuer và allowlist giá trị; không dùng tên role có vẻ giống nhau làm ngữ nghĩa tương đương.

### Tình huống F — Issuer đổi JWKS URI

Một thay đổi discovery làm jwks_uri trỏ tới endpoint khác. Validator tự động chấp nhận mà không kiểm tra metadata/issuer và quy trình thay đổi.

**Bài học:** discovery phải gắn với issuer đã cấu hình; thay đổi endpoint khóa là thay đổi trust boundary cần kiểm soát và audit.

### Tình huống G — Issuer staging được thêm nhầm vào production

Trust registry production chứa issuer staging. Token thử nghiệm được ký hợp lệ và gọi API production.

**Bài học:** tách cấu hình, khóa, audience và registry giữa các môi trường; kiểm tra deployment policy.

## 14. Checklist cấu hình nhiều issuer

### Trust registry

- [ ] Mỗi issuer được đăng ký rõ ràng và có owner.
- [ ] Issuer identifier được so khớp chính xác theo profile.
- [ ] Không chấp nhận issuer tự khai báo ngoài allowlist.
- [ ] Discovery URL/JWKS URI đến từ cấu hình được quản trị.
- [ ] Discovery metadata issuer khớp issuer đã cấu hình.
- [ ] Cấu hình production/staging/development được tách biệt.
- [ ] Thay đổi trust profile có review, audit và rollback.

### Key và thuật toán

- [ ] JWKS và cache được phân vùng theo issuer.
- [ ] kid chỉ được tìm trong JWKS của issuer đã chọn.
- [ ] Kiểm tra kty, use, key_ops, alg và chất lượng khóa.
- [ ] Algorithm allowlist được cấu hình riêng cho issuer.
- [ ] Không chấp nhận none hoặc algorithm confusion.
- [ ] Không fallback sang khóa của issuer khác.
- [ ] Unknown kid refresh có rate limit và single-flight.
- [ ] Có quy trình rotation bình thường và xử lý compromise khẩn cấp.

### Token profile và claims

- [ ] Kiểm tra issuer sau khi xác minh chữ ký.
- [ ] Audience/resource khớp API đích.
- [ ] Phân biệt access token, ID Token, logout token và token nội bộ.
- [ ] Kiểm tra exp, nbf, iat và các claim bắt buộc.
- [ ] Schema claims được định nghĩa theo từng issuer.
- [ ] Subject được namespace theo issuer.
- [ ] Tenant mapping được xác minh, không lấy tùy ý từ request.
- [ ] Role/group/scope mapping dùng allowlist, không nâng quyền ngầm.

### Vận hành và kiểm thử

- [ ] Không fetch jku/x5u hoặc discovery URL tùy ý từ token.
- [ ] Chống SSRF khi tải metadata/JWKS.
- [ ] Có timeout, response-size limit và redirect policy.
- [ ] Có metrics theo issuer mà không ghi raw token.
- [ ] Có quy trình disable issuer và xử lý token/session liên quan.
- [ ] Có test cross-issuer, same-sub, same-kid, wrong-audience và wrong-type.
- [ ] Có test mapping claims, tenant isolation và account linking.

## 15. Kiểm thử bảo mật nhiều issuer

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token từ issuer nằm trong allowlist, chữ ký và profile hợp lệ | Được tiếp tục kiểm tra quyền |
| Token có issuer không được đăng ký | Từ chối |
| Issuer chỉ khác chữ hoa/thường hoặc cách chuẩn hóa URL | Từ chối nếu không khớp issuer identifier đã cấu hình |
| Hai issuer có cùng kid | Mỗi token chỉ tra khóa trong JWKS của issuer tương ứng |
| Token issuer A ký bằng khóa issuer B | Từ chối; không fallback |
| Token có jku trỏ tới host attacker | Không thực hiện fetch |
| Discovery metadata trả issuer khác giá trị cấu hình | Từ chối metadata |
| Unknown kid liên tục được gửi | Refresh bị rate limit; token không hợp lệ bị từ chối |
| alg không nằm trong allowlist của issuer | Từ chối |
| Token hợp lệ nhưng aud sai | Từ chối |
| ID Token được dùng như access token | Từ chối |
| Hai issuer phát hành cùng sub | Tạo hai principal riêng |
| Claim group không nằm trong mapping allowlist | Không cấp permission |
| Tenant claim không ánh xạ hoặc không thuộc subject | Từ chối |
| Issuer bị disable | Token từ issuer đó bị từ chối theo policy |
| JWKS rotation bình thường | Key mới được nhận; key cũ được giữ theo thời gian chuyển tiếp |
| Key bị compromise | Khóa bị chặn theo incident policy, không tiếp tục stale-cache |
| Cấu hình staging bị đưa vào production | Deployment/policy check phát hiện và từ chối |

## 16. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Chữ ký hợp lệ có đủ để chấp nhận JWT từ một issuer bất kỳ không? | **Không.** Issuer phải nằm trong trust registry và token phải khớp profile của resource server. |
| Có thể dùng iss chưa xác minh để chọn trust profile không? | **Có, nhưng chỉ làm lookup chính xác trong allowlist đã cấu hình.** Không dùng nó để fetch URL tùy ý hoặc cấp quyền. |
| Hai issuer có thể cùng dùng kid không? | **Có.** kid chỉ có ý nghĩa trong JWKS/ngữ cảnh issuer tương ứng. |
| Có nên thử khóa của tất cả issuer nếu chữ ký không hợp lệ? | **Không.** Không fallback sang miền khóa khác. |
| Token có thể tự chỉ định jku để API tải public key không? | **Không theo mặc định an toàn.** Nguồn khóa phải được gắn với trust profile đã quản trị. |
| Issuer nằm trong allowlist có nghĩa mọi token của issuer đều hợp lệ cho API? | **Không.** Cần kiểm tra audience, loại token, thời hạn, thuật toán và schema. |
| ID Token có thể dùng thay access token để gọi API không? | **Không.** Hai loại token có mục đích và profile khác nhau. |
| Có thể dùng sub đơn lẻ làm định danh toàn cục giữa nhiều issuer không? | **Không.** Dùng issuer namespace cùng subject. |
| Có nên ánh xạ mọi group tên admin thành system.admin? | **Không.** Mapping phải tường minh theo issuer và allowlist giá trị. |
| Tenant có luôn suy ra được từ issuer không? | **Không.** Một issuer có thể phục vụ nhiều tenant; cần claim/policy mapping rõ ràng. |

## 17. Ghi nhớ

- Mỗi issuer là một miền tin cậy riêng với trust profile, JWKS, thuật toán, audience, token profile và claim mapping riêng.
- Giá trị iss chưa xác minh chỉ được dùng để tra cứu chính xác trong allowlist; sau khi xác minh chữ ký phải kiểm tra iss khớp profile.
- Không fetch discovery/JWKS từ URL tùy ý trong token; kiểm soát SSRF và xác minh metadata issuer.
- kid không phải định danh toàn cục; phân vùng khóa và cache theo issuer, không fallback sang khóa của issuer khác.
- Thuật toán phải nằm trong allowlist cấu hình ngoài token; không để alg tự quyết định chính sách xác minh.
- Trust issuer không đồng nghĩa chấp nhận mọi token: audience, token type, thời hạn và schema đều phải hợp lệ.
- Định danh principal bằng issuer và subject; không tự gộp tài khoản theo sub hoặc email.
- Ánh xạ group, role, scope và tenant theo từng issuer bằng allowlist; không nâng quyền ngầm.
- Bảo vệ trust registry như một phần của security boundary; thay đổi issuer/JWKS/mapping phải có review, audit và rollback.
- Kiểm thử cross-issuer, same-kid, same-sub, wrong-audience, key rotation, SSRF và claim mapping trước khi đưa vào production.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 – JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 8414 – OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP API Security Top 10](https://owasp.org/API-Security/)
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
