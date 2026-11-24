# Token audience — Ràng buộc token với đúng bên nhận

> **Chương:** Token authentication  
> **Chủ đề:** Token audience  
> **Phạm vi:** Security Authentication Fundamentals — xác thực token, phân biệt issuer/subject/client/resource, giới hạn token theo API nhận, chống token substitution và confused deputy trong hệ thống nhiều dịch vụ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **audience (aud)** là ai hoặc dịch vụ nào được phép nhận và sử dụng token.
2. Phân biệt các claim iss, sub, aud, client_id, scope và azp trong ngữ cảnh JWT/OAuth 2.0/OpenID Connect.
3. Thiết kế resource server kiểm tra audience cùng chữ ký, issuer, thời hạn, loại token và quyền.
4. Nhận diện token substitution, confused deputy, cross-service token reuse và lỗi nhầm ID token với access token.
5. Thiết kế audience riêng cho từng API hoặc resource, xử lý gateway/microservice và tránh mở rộng phạm vi token ngoài ý định.
6. Xây dựng bộ kiểm thử chứng minh token dành cho API A không thể được dùng để gọi API B.

## 1. Token audience là gì?

**Audience** (đối tượng nhận) cho biết token được phát hành để một hoặc nhiều bên nhận cụ thể sử dụng. Trong JWT, claim chuẩn **aud** biểu diễn người nhận dự kiến của token. Resource server cần xác minh rằng chính nó nằm trong audience được phép trước khi chấp nhận token.

Ví dụ, một hệ thống có hai API:

- **orders-api** xử lý đơn hàng;
- **payments-api** xử lý thanh toán.

Một access token được cấp để gọi orders-api không nên được chấp nhận tại payments-api chỉ vì chữ ký JWT hợp lệ và token chưa hết hạn. Nếu token chỉ định audience là orders-api, thì payments-api phải từ chối.

**Audience giới hạn nơi token có thể được dùng.** Nó là một phần của ranh giới tin cậy và giúp giảm nguy cơ một token bị lấy cắp hoặc bị chuyển nhầm sang dịch vụ khác.

### Vì sao cần audience?

Không có kiểm tra audience, một resource server có thể chấp nhận token được phát hành cho một ứng dụng hoặc API khác. Điều này tạo ra những rủi ro như:

- Dùng ID token của ứng dụng web để gọi API;
- Dùng access token dành cho API A tại API B;
- Dùng token của môi trường staging tại production;
- Chuyển token của tenant hoặc resource khác sang dịch vụ không có quyền nhận;
- Khiến một service có đặc quyền sử dụng token của client khác.

Một chữ ký hợp lệ chỉ chứng minh token được ký bởi một khóa tương ứng và nội dung chưa bị sửa sau khi ký. Nó **không chứng minh token dành cho API đang nhận request**.

## 2. Phân biệt các claim và khái niệm liên quan

Các claim thường xuất hiện gần nhau nhưng mang ý nghĩa khác nhau:

| Claim/khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **iss — issuer** | Ai phát hành token? | https://identity.example.com |
| **sub — subject** | Token nói về chủ thể nào? | user-42 hoặc service principal |
| **aud — audience** | Token được phát hành cho bên nhận nào? | https://orders-api.example.com |
| **client_id** | OAuth client nào yêu cầu token? | warehouse-web |
| **azp — authorized party** | Client nào được chỉ định là bên được ủy quyền trong ngữ cảnh OIDC liên quan? | warehouse-web |
| **scope** | Client/subject được yêu cầu hoặc cấp quyền gì? | orders.read |
| **exp** | Token hết hạn lúc nào? | Unix timestamp |
| **nbf** | Token chưa được chấp nhận trước thời điểm nào? | Unix timestamp |
| **iat** | Token được phát hành lúc nào? | Unix timestamp |

Đừng dùng một claim thay cho claim khác. client_id không phải audience; một client có thể yêu cầu token cho nhiều resource. scope mô tả quyền, nhưng không xác định đầy đủ API nào được nhận token. sub nhận diện subject, không cho biết API nào có quyền sử dụng token.

### Ví dụ JWT access token minh họa

`````````json
{
  "iss": "https://identity.example.com",
  "sub": "service-inventory-sync",
  "aud": "https://orders-api.example.com",
  "client_id": "inventory-worker",
  "scope": "orders.read",
  "iat": 1795323600,
  "exp": 1795324500
}
`````````

Payload trên chỉ là ví dụ để minh họa ngữ nghĩa. Không được chấp nhận token chỉ bằng cách decode JSON. Resource server phải xác minh chữ ký và áp dụng các quy tắc token phù hợp.

## 3. aud trong JWT: một hoặc nhiều audience

Theo cấu trúc JWT, aud có thể là:

- Một chuỗi định danh audience;
- Một mảng chuỗi định danh audience.

Ví dụ:

`````````json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": "https://orders-api.example.com"
}
`````````

Hoặc:

`````````json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": [
    "https://orders-api.example.com",
    "https://reports-api.example.com"
  ]
}
`````````

Resource server cần kiểm tra audience của chính nó có xuất hiện trong tập audience được chấp nhận theo policy hay không. Việc so khớp cần theo định danh được cấu hình chính xác; không dùng so khớp chuỗi con, wildcard tùy tiện hoặc kiểm tra kiểu “có chứa chữ api”.

### Có nên cấp nhiều audience trong một token?

Chỉ nên cấp nhiều audience khi token thực sự được thiết kế để một tập resource server cùng nhận và chính sách cho phép điều đó. Nếu token có thể gọi cả orders và reports, một bản sao token bị lộ có thể mở rộng phạm vi tác động sang cả hai dịch vụ.

Trong nhiều kiến trúc, **một token cho một resource server hoặc một resource set được xác định rõ** dễ giới hạn quyền và điều tra hơn. Không nên đưa mọi API vào aud chỉ để tránh phải xin token mới.

## 4. Resource server phải kiểm tra audience như thế nào?

Một resource server không nên chỉ kiểm tra “JWT có chữ ký hợp lệ”. Nó cần xác minh tối thiểu:

1. Token có định dạng và loại được API chấp nhận;
2. Chữ ký hợp lệ bằng khóa tin cậy từ issuer được cấu hình;
3. iss đúng issuer mà API tin cậy;
4. aud bao gồm chính resource server/API hiện tại;
5. exp, nbf và các giới hạn thời gian được đáp ứng;
6. Subject/client và scope phù hợp với endpoint;
7. Trạng thái token/account/credential không bị thu hồi theo cơ chế của hệ thống;
8. Các claim bắt buộc theo profile token đang sử dụng có mặt và đúng kiểu.

### Trình tự xác minh gợi ý

`````````mermaid
flowchart TD
    A["Nhận bearer token"] --> B["Kiểm tra định dạng và loại token"]
    B --> C{"Chữ ký hợp lệ?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D{"Issuer được tin cậy?"}
    D -- "Không" --> X
    D -- "Có" --> E{"Audience có chứa API hiện tại?"}
    E -- "Không" --> X
    E -- "Có" --> F{"Thời hạn và trạng thái hợp lệ?"}
    F -- "Không" --> X
    F -- "Có" --> G{"Scope / subject / tenant đủ quyền?"}
    G -- "Không" --> X
    G -- "Có" --> H["Cho phép bước authorization tiếp theo"]
`````````

Thứ tự triển khai nội bộ có thể khác, nhưng không được bỏ một điều kiện bắt buộc. Các kiểm tra nên được thực hiện bằng thư viện JWT/OAuth/OIDC đáng tin cậy, không tự viết bộ xác minh chữ ký hoặc thuật toán xử lý token.

### Pseudocode

`````````
validateAccessToken(token, currentApi):
    claims = verifySignatureAndDecodeWithTrustedIssuerKeys(token)
    require(claims.iss in currentApi.trustedIssuers)
    require(currentApi.identifier in normalizeAudience(claims.aud))
    require(tokenTypeIsAccepted(token, currentApi.policy))
    require(not expired(claims.exp))
    require(not beforeNotBeforeTime(claims.nbf))
    require(subjectAndClientAreAllowed(claims, currentApi))
    require(requiredScopesPresent(claims.scope, currentApi.endpoint))
    require(accountAndCredentialStateAllows(claims.sub))
    return AUTHENTICATED_PRINCIPAL(claims.sub, claims.client_id)
`````````

Đây là mã giả mô tả các lớp kiểm tra, không phải thư viện triển khai. normalizeAudience phải xử lý đúng kiểu chuỗi hoặc mảng theo chuẩn và policy; không tự biến audience thành wildcard hoặc so khớp gần đúng.

## 5. Token substitution và confused deputy

**Token substitution** xảy ra khi một token hợp lệ trong ngữ cảnh này bị đưa vào ngữ cảnh khác và được chấp nhận sai. Một nguyên nhân phổ biến là resource server không kiểm tra audience hoặc chấp nhận quá nhiều loại token.

**Confused deputy** xảy ra khi một dịch vụ có quyền cao bị đánh lừa sử dụng credential hoặc quyền của nó thay cho chủ thể không có quyền. Token audience quá rộng hoặc không được kiểm tra có thể tạo điều kiện cho lỗi này.

### Ví dụ: ID token bị dùng như access token

OIDC ID token được phát hành để client biết sự kiện xác thực của người dùng. Access token được phát hành để truy cập resource server. Nếu một API nhận ID token chỉ vì token đó có chữ ký đúng, API có thể nhầm token dành cho client với token dành cho chính API.

Ví dụ:

1. web-client nhận ID token có audience là web-client.
2. Frontend gửi ID token tới payments-api.
3. payments-api chỉ kiểm tra chữ ký và exp, không kiểm tra aud hoặc token type.
4. API chấp nhận token và xử lý request.

Đây là lỗi thiết kế. payments-api phải yêu cầu access token được phát hành cho chính nó và kiểm tra profile/claim của access token theo chính sách.

### Ví dụ: token dành cho API A bị chuyển sang API B

- orders-api nhận token có aud=orders-api;
- Attacker sao chép token và gửi tới admin-api;
- admin-api xác minh cùng issuer và chữ ký nhưng không kiểm tra audience;
- Token bị chấp nhận ngoài mục đích ban đầu.

Kiểm tra aud chính xác giúp ngăn việc chuyển token giữa các resource server không được chỉ định.

## 6. Audience và OAuth 2.0 resource server

OAuth 2.0 phân biệt **client**, **authorization server** và **resource server**:

- Client yêu cầu quyền truy cập;
- Authorization server xác minh grant/chủ thể và phát access token;
- Resource server nhận token và thực thi quyền.

Client không nên tự quyết định audience chỉ bằng cách gửi một chuỗi bất kỳ rồi mong authorization server chấp nhận. Authorization server phải kiểm tra resource/audience có được phép theo client, grant, user, tenant và policy hay không.

### Resource Indicators

OAuth có cơ chế **Resource Indicators (RFC 8707)** cho phép client chỉ định resource mà access token được yêu cầu sử dụng. Authorization server có thể dùng thông tin resource để phát token được ràng buộc với resource tương ứng, tùy hỗ trợ và policy triển khai.

Ví dụ khái quát:

`````````http
POST /oauth/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=inventory-worker&
client_secret=[redacted]&
resource=https%3A%2F%2Forders-api.example.com&
scope=orders.read
`````````

Đây là ví dụ dạng minh họa; cách xác thực client và tham số thực tế phụ thuộc grant, client type và cấu hình authorization server. Client không được tự gán audience trong token đã phát hành; **authorization server là bên quyết định claim và resource server là bên kiểm tra**.

### Một token cho nhiều resource

Nếu client cần gọi nhiều API, có thể:

- Xin access token riêng cho từng resource;
- Dùng một API gateway/resource facade được xác định làm audience duy nhất rồi gateway định tuyến nội bộ theo policy;
- Dùng token có nhiều audience nếu hệ thống hỗ trợ và đã đánh giá rõ blast radius.

Không nên phát một token audience rộng cho mọi microservice chỉ để giảm số lần gọi token endpoint. Việc này làm yếu ranh giới giữa các dịch vụ và khiến token bị lộ có phạm vi sử dụng lớn hơn.

## 7. Audience trong OpenID Connect

OIDC sử dụng ID token để truyền thông tin về sự kiện xác thực tới client. Trong ID token:

- iss xác định OpenID Provider;
- sub là định danh ổn định của người dùng trong phạm vi issuer;
- aud xác định client ID hoặc các client được phép nhận ID token;
- azp có thể xác định authorized party trong các trường hợp liên quan, đặc biệt khi audience có nhiều giá trị hoặc theo quy tắc OIDC.

Client phải kiểm tra ID token theo OIDC, bao gồm issuer, audience, thời hạn, chữ ký và nonce khi được sử dụng trong luồng tương ứng. Khi nhiều audience xuất hiện, client cần áp dụng quy tắc azp theo đặc tả OIDC.

**ID token không phải access token.** ID token chứng minh thông tin xác thực dành cho client OIDC; access token được dùng để gọi resource server. Không chuyển ID token tới API như thể nó là bearer token có audience phù hợp.

### Ví dụ phân biệt

`````````json
{
  "id_token": {
    "iss": "https://identity.example.com",
    "sub": "user-42",
    "aud": "warehouse-web",
    "nonce": "n-0S6_WzA2Mj"
  },
  "access_token": {
    "iss": "https://identity.example.com",
    "sub": "user-42",
    "aud": "https://orders-api.example.com",
    "scope": "orders.read"
  }
}
`````````

Hai payload chỉ để minh họa vai trò. Token thực tế cần được xác minh theo profile và giao thức phát hành; không thể kết luận an toàn chỉ từ tên trường hoặc ví dụ JSON.

## 8. Audience và token type: tránh cross-JWT confusion

Một hệ thống có thể sử dụng nhiều loại JWT:

- OIDC ID token;
- OAuth access token;
- JWT dùng nội bộ giữa các service;
- JWT reset password hoặc email verification;
- JWT cho session hoặc transaction approval.

Nếu các token này dùng cùng khóa ký và resource server chỉ kiểm tra chữ ký, một loại token có thể bị dùng nhầm trong ngữ cảnh khác. Đây là dạng **cross-JWT confusion**.

### Biện pháp phân biệt

1. **Audience riêng:** mỗi loại token gắn với recipient đúng.
2. **Issuer/purpose rõ:** không dùng cùng một issuer/purpose mơ hồ cho mọi luồng nếu có thể tách.
3. **Explicit token type:** kiểm tra typ hoặc profile token theo chuẩn đang sử dụng; không chỉ dựa vào header tùy ý.
4. **Claim profile riêng:** mỗi loại token có bộ claim bắt buộc và quy tắc kiểm tra riêng.
5. **Key separation khi phù hợp:** dùng khóa hoặc cấu hình tin cậy riêng cho token có mục đích khác nhau.
6. **Endpoint separation:** API login, recovery và resource API không dùng chung logic chấp nhận token một cách thiếu phân biệt.

Ví dụ, token đặt lại mật khẩu chỉ nên được chấp nhận tại endpoint recovery, có audience và purpose phù hợp, thời hạn ngắn, một lần và gắn đúng tài khoản. Không để token đó gọi API đọc dữ liệu chỉ vì chữ ký hợp lệ.

## 9. Audience trong kiến trúc API gateway và microservices

Trong hệ thống microservices, cần quyết định rõ token được xác minh ở gateway, từng resource server hay cả hai.

### Mô hình gateway

- Client nhận token có audience là API gateway.
- Gateway xác minh issuer, audience, thời hạn và scope.
- Gateway định tuyến tới service phía sau theo policy.
- Service có thể nhận danh tính đã được gateway xác minh qua một kênh nội bộ tin cậy hoặc tiếp tục xác minh token.

Nếu service tin header như X-User-Id trong request Internet mà không xác minh gateway đã xóa/ghi đè header và bảo vệ kênh nội bộ, attacker có thể giả mạo principal.

### Mô hình token riêng từng service

- Client hoặc gateway yêu cầu token dành riêng cho orders-api;
- Token được phát hành với aud=orders-api;
- orders-api tự xác minh token và scope;
- Token không được tái sử dụng tại payments-api.

Mô hình này tạo ranh giới rõ nhưng có thể tăng số lần lấy token hoặc yêu cầu token exchange giữa các dịch vụ.

### Token exchange

Trong một số kiến trúc, service A cần gọi service B thay mặt user. Thay vì chuyển tiếp token có audience dành cho A, hệ thống có thể dùng **token exchange** để nhận token mới có audience dành cho B và scope giới hạn. Service B xác minh token mới như token được phát hành cho chính nó.

Token exchange không tự bảo đảm an toàn nếu authorization server cấp token quá rộng hoặc không xác minh subject/actor. Cần ràng buộc:

- Subject (người dùng hoặc workload được đại diện);
- Actor/client thực hiện exchange;
- Resource/audience đích;
- Scope được phép chuyển tiếp;
- Delegation policy và thời hạn;
- Audit liên kết token gốc với token được trao đổi mà không lưu token thô.

## 10. Multi-tenant và audience

Audience xác định resource server, nhưng **không tự xác định tenant mà principal được phép truy cập**. Một API đa tenant thường cần kiểm tra thêm tenant context và quyền trên tài nguyên.

Ví dụ token có:

`````````json
{
  "iss": "https://identity.example.com",
  "sub": "service-reporting",
  "aud": "https://reports-api.example.com",
  "scope": "reports.read",
  "tenant_id": "tenant-42"
}
`````````

tenant_id chỉ có ý nghĩa nếu issuer đưa claim đó vào token theo policy đáng tin và resource server kiểm tra nó với resource thực tế. Không tin tenant ID do client thêm vào request hoặc claim tự khai không được xác minh.

### Các điều kiện kiểm tra

- Audience đúng API;
- Subject/client được phép hoạt động trong tenant;
- Tenant claim có nguồn đáng tin và đúng phạm vi;
- Resource thuộc tenant tương ứng;
- Scope đủ cho hành động;
- Account/service principal còn active;
- Quyền không bị thu hồi theo chính sách hiện tại.

Một token có audience đúng reports-api nhưng tenant sai vẫn phải bị từ chối. Audience là điều kiện cần, không thay thế authorization theo tenant.

## 11. Audience và token revocation

Audience giới hạn nơi token được dùng, nhưng không tự thu hồi token. Nếu token bị đánh cắp, attacker vẫn có thể sử dụng nó tại resource server được chỉ định cho tới khi token hết hạn hoặc bị cơ chế thu hồi chặn.

Các chiến lược có thể kết hợp:

| Cơ chế | Vai trò | Giới hạn |
| --- | --- | --- |
| Access token TTL ngắn | Giảm thời gian token bị lạm dụng | Không chặn tức thời |
| Opaque token + introspection | Resource server hỏi trạng thái active và metadata | Phụ thuộc mạng và availability của authorization server |
| JWT denylist/revocation event | Chặn token cụ thể hoặc subject/key bị revoke | Cần propagation và quản lý cache |
| Account/session version | So token với phiên bản hiện hành | Cần kiểm tra version ở điểm thực thi |
| Sender-constrained token | Ràng buộc token với khóa/chủ thể client khi giao thức hỗ trợ | Tăng độ phức tạp quản lý khóa và client |

Audience vẫn phải được kiểm tra ngay cả khi dùng introspection hoặc sender-constrained token. Mỗi cơ chế giải quyết một phần khác nhau của rủi ro.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra chữ ký và exp | Token dành cho API khác vẫn được chấp nhận | Kiểm tra aud chính xác |
| Dùng cùng audience cho mọi API | Một token có thể di chuyển giữa nhiều resource | Audience theo resource hoặc resource set được định nghĩa |
| Chấp nhận ID token như access token | Nhầm token dành cho client với token dành cho API | Phân biệt token type/profile và audience |
| Dùng client_id thay aud | Xác minh nhầm client gọi token thành resource nhận token | Kiểm tra từng claim đúng ngữ nghĩa |
| So khớp audience bằng substring | Audience độc hại có thể vượt kiểm tra lỏng | So khớp chính xác theo policy |
| Tin aud do client gửi ngoài token | Attacker tự khai recipient | Chỉ tin claim trong token đã xác minh chữ ký |
| Token audience đúng nhưng không kiểm tra scope | Principal gọi hành động vượt quyền | Authorization riêng theo endpoint/resource |
| Gateway kiểm tra rồi tin header từ Internet | Có thể giả mạo identity header | Xóa/ghi đè header, bảo vệ hop nội bộ và xác minh nguồn |
| Chuyển tiếp token A tới service B | Token substitution/confused deputy | Token exchange hoặc token audience riêng |
| Token recovery dùng được ở API dữ liệu | Cross-JWT confusion | Purpose/audience/type riêng và endpoint riêng |
| Audience rộng để giảm số lần xin token | Tăng blast radius khi token bị lộ | Chỉ cấp resource cần thiết |

## 13. Tình huống thiết kế: token dùng chung cho orders và payments

Một nền tảng thương mại điện tử có:

- web-store là OAuth client;
- orders-api đọc và cập nhật đơn hàng;
- payments-api hoàn tiền;
- identity-provider phát access token.

Ban đầu, authorization server cấp token với audience commerce-platform, và cả hai API đều chấp nhận audience đó. Token có scope orders.read và payments.refund.

Một token bị lấy từ browser log. Attacker có thể dùng token gọi cả hai API trong thời gian token còn hiệu lực.

### Phân tích

1. Audience quá rộng: token được nhiều resource server nhận.
2. Scope kết hợp cả đọc đơn hàng và hoàn tiền, làm tăng phạm vi tác động.
3. Token lưu trong browser log tạo nguy cơ rò rỉ bearer credential.
4. Nếu payments API không yêu cầu step-up hoặc xác nhận giao dịch riêng, attacker có thể lạm dụng quyền hoàn tiền.

### Thiết kế lại

1. Authorization server phát access token riêng cho orders-api với scope orders.read hoặc quyền cần thiết.
2. Khi cần hoàn tiền, client yêu cầu token dành cho payments-api với scope phù hợp và policy step-up.
3. payments-api kiểm tra iss, aud, token type, exp, subject/client, scope và trạng thái account.
4. API kiểm tra quyền trên từng giao dịch và giới hạn tenant; không dựa vào scope đơn lẻ.
5. Với luồng service-to-service, dùng token exchange hoặc client credentials theo đúng principal/actor/resource.
6. Thu hồi token hoặc session khi phát hiện compromise; giám sát request sau mốc revoke.
7. Redact token khỏi log, tracing và browser telemetry.

### Kết quả mong đợi

- Token orders không gọi được payments;
- Token payments không tự động có quyền gọi orders;
- Token đúng audience nhưng sai scope vẫn bị từ chối;
- Token đúng audience/scope nhưng account disabled vẫn bị chặn;
- Token ID hoặc recovery không thể dùng thay access token;
- Mọi quyết định được audit bằng request ID, subject/client và key ID, không ghi token thô.

## 14. Bộ kiểm thử chấp nhận cho audience

| Trường hợp | Đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| **Audience đúng** | Access token có aud đúng API | Tiếp tục kiểm tra các điều kiện còn lại |
| **Audience sai** | Token dành cho API A gọi API B | Từ chối |
| **Audience thiếu** | JWT không có aud trong profile yêu cầu | Từ chối |
| **Audience mảng** | aud là mảng có chứa chính xác API hiện tại | Chấp nhận điều kiện audience nếu policy cho phép |
| **Substring trick** | aud chứa chuỗi gần giống nhưng không trùng | Từ chối |
| **Issuer sai** | Chữ ký có vẻ hợp lệ nhưng issuer không được tin | Từ chối |
| **ID token substitution** | ID token gửi tới resource API | Từ chối |
| **Token type sai** | JWT recovery/session gửi tới API dữ liệu | Từ chối |
| **Scope thiếu** | Audience đúng nhưng scope không đủ | 403 hoặc từ chối theo policy |
| **Client sai** | Client không được phép yêu cầu resource | Authorization server không cấp token hoặc API từ chối |
| **Tenant sai** | Audience đúng nhưng tenant không khớp resource | Từ chối |
| **Token hết hạn** | exp đã qua | Từ chối |
| **Token chưa hiệu lực** | nbf nằm trong tương lai | Từ chối |
| **Token revoked** | Token/subject bị thu hồi | Từ chối theo cơ chế revocation |
| **Token exchange** | Token A được exchange sang audience B với scope được phép | B nhận token mới đúng audience; token A không tự dùng tại B |
| **Gateway header spoofing** | Client tự gửi X-User-Id hoặc identity header | Gateway xóa/ghi đè; backend không tin giá trị client |
| **Multi-audience token** | Token có nhiều audience | Chỉ chấp nhận nếu resource và policy cho phép rõ ràng |

Các bài kiểm thử cần chạy trực tiếp tại resource server, không chỉ kiểm tra token endpoint hoặc giao diện frontend.

## 15. Audit và giám sát token audience

Khi điều tra token bị dùng sai, cần biết token được phát cho resource nào và API nào đã nhận nó. Log nên ghi metadata đã xác minh:

| Trường | Mục đích |
| --- | --- |
| iss hoặc issuer ID | Xác định nguồn phát hành |
| sub/principal reference | Chủ thể được token đại diện |
| client_id/authorized party | Client yêu cầu hoặc sử dụng token |
| aud đã chuẩn hóa | Resource nhận được chỉ định |
| Token type/profile | Phân biệt access token, ID token và token nghiệp vụ |
| Scope/authorization result | Quyền được yêu cầu và quyết định |
| jti hoặc token reference | Liên kết token nếu có và nếu policy cho phép |
| Request ID/trace ID | Nối log giữa gateway và resource server |
| Resource server ID | API thực tế nhận token |
| Reason code | Sai issuer, audience, scope, expiry, revoke hoặc type |

Không ghi token thô, Authorization header hoặc private key. Nếu dùng jti, cần cân nhắc quyền riêng tư và retention; không phải mọi hệ thống đều cần ghi toàn bộ claim.

### Chỉ số vận hành

- **Audience mismatch rate:** số request bị từ chối do audience không khớp / tổng request có token trong phạm vi đo.
- **Cross-resource token rejection:** số lần token được gửi tới resource không nằm trong audience.
- **Wrong token type rejection:** số lần ID token/recovery token hoặc JWT sai profile bị gửi tới resource API.
- **Multi-audience token inventory:** số token/profile có nhiều audience và các resource liên quan.
- **Token exchange success/failure:** theo dõi việc cấp token đích và lỗi policy.
- **Post-revocation accepted request:** số request vẫn được chấp nhận sau mốc revoke có hiệu lực.

Tỷ lệ audience mismatch cao có thể do client cấu hình sai, token exchange lỗi hoặc hành vi dò quét. Cần đối chiếu deployment và nguồn request trước khi kết luận tấn công.

## 16. Checklist triển khai

- **Resource identity:** Mỗi API có định danh audience rõ ràng, ổn định và không trùng mơ hồ?
- **Issuer:** Resource server chỉ tin issuer được cấu hình và kiểm tra đúng khóa?
- **Audience:** Có xác minh aud chính xác, xử lý đúng chuỗi/mảng và không dùng wildcard tùy tiện?
- **Token type:** Có phân biệt access token, ID token, recovery token và token nội bộ?
- **Claims:** sub, client_id, azp, scope, exp, nbf được diễn giải đúng ngữ nghĩa?
- **Authorization:** Audience đúng có được kiểm tra tiếp bằng scope, role, tenant và quyền trên resource?
- **OAuth/OIDC:** Authorization server quyết định resource; client không tự sửa claim; RP kiểm tra ID token theo OIDC?
- **Microservices:** Token được giới hạn theo API; token exchange/delegation có policy và audit?
- **Revocation:** Có cơ chế chặn token bị lộ, disable account và key bị compromise?
- **Gateway:** Identity header từ client bị loại bỏ/ghi đè; hop nội bộ được xác thực và phân quyền?
- **Audit:** Có issuer, subject/client, audience, resource server, reason code và request ID mà không lưu token thô?
- **Testing:** Đã kiểm tra audience sai, thiếu, mảng, substring, ID token substitution, tenant mismatch và token exchange?

### Câu hỏi tự kiểm tra

1. aud khác client_id ở điểm nào?
2. Vì sao token có chữ ký hợp lệ vẫn có thể không được API hiện tại chấp nhận?
3. Một ID token có aud là web client có thể được gửi tới resource API không? Vì sao?
4. Khi nào một token có nhiều audience làm tăng blast radius?
5. Vì sao scope không thay thế aud?
6. Token exchange giúp gì khi service A gọi service B thay mặt user?
7. Audience đúng nhưng tenant claim sai thì API phải xử lý thế nào?
8. Những trường nào cần có trong audit để điều tra token substitution mà không lưu bearer token?

## Kết luận

**Audience ràng buộc token với đúng resource server hoặc nhóm resource được phép nhận token.** Resource server phải kiểm tra aud cùng issuer, chữ ký, token type, thời hạn, subject/client, scope và trạng thái hiện hành. Việc kiểm tra audience ngăn token dành cho API này bị chuyển sang API khác, giảm nguy cơ ID token substitution và confused deputy. Trong hệ thống OAuth/OIDC, microservices và multi-tenant, audience cần được thiết kế rõ từ authorization server tới từng điểm thực thi; quyền trên tenant và tài nguyên vẫn phải được kiểm tra riêng. Một token chỉ nên có phạm vi nhận và quyền đủ cho mục đích của nó, để khi bị lộ, phạm vi tác động được giới hạn.
