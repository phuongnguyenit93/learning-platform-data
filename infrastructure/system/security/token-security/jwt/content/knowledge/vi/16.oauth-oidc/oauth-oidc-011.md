# Token exchange và tránh chuyển tiếp token sai đối tượng nhận

## 1. Vì sao cần Token Exchange?

Trong một hệ thống có nhiều API, một dịch vụ thường nhận access token từ client rồi cần gọi tiếp một dịch vụ khác. Ví dụ, ứng dụng đặt hàng nhận token dành cho Orders API, sau đó cần gọi Payments API để xử lý thanh toán.

Nếu Orders API chuyển tiếp nguyên token ban đầu sang Payments API, token có thể không được phát hành cho Payments API. Việc chuyển tiếp token không đúng người nhận có thể dẫn đến:

- Resource server chấp nhận token vốn chỉ dành cho một API khác.
- Một token có quyền rộng bị sử dụng tại nhiều dịch vụ.
- Dịch vụ trung gian vô tình trở thành confused deputy, dùng quyền của mình thay cho quyền mà người dùng đã được cấp.
- Không phân biệt được người dùng (subject) với dịch vụ đang hành động thay mặt họ (actor).
- Token bị lộ ở nhiều thành phần hơn mức cần thiết.

OAuth 2.0 Token Exchange, được định nghĩa trong RFC 8693, cung cấp một giao thức để client gửi một token hiện có tới Authorization Server (AS) và yêu cầu một token mới phù hợp với ngữ cảnh khác. Token mới có thể được giới hạn theo resource, audience, scope, loại token và chính sách ủy quyền.

Mục tiêu là để mỗi resource server nhận đúng credential được cấp cho nó, với quyền tối thiểu cần thiết. Token exchange không tự động làm cho mọi yêu cầu trở nên an toàn: AS vẫn phải xác thực client, kiểm tra token đầu vào và quyết định có cho phép việc trao đổi hay không.

Bài này thuộc phạm vi OAuth, OpenID Connect và JWT tổng quát; không phụ thuộc Java, Spring Security hay một framework cụ thể.

## 2. Token Exchange hoạt động như thế nào?

RFC 8693 định nghĩa một OAuth grant type mở rộng có giá trị:

~~~text
urn:ietf:params:oauth:grant-type:token-exchange
~~~

Client gửi yêu cầu tới token endpoint của AS. Yêu cầu thường chứa:

| Tham số | Ý nghĩa |
| --- | --- |
| grant_type | Phải là token exchange grant type |
| subject_token | Token đại diện cho subject mà client muốn trao đổi |
| subject_token_type | Định danh loại của subject_token |
| actor_token | Token đại diện cho actor đang thực hiện việc trao đổi, nếu có |
| actor_token_type | Định danh loại actor_token; bắt buộc khi actor_token được gửi |
| resource | Resource URI mà token mới dự định dùng tại đó; có thể xuất hiện nhiều lần theo profile |
| audience | Định danh logical audience dự kiến của token mới; có thể xuất hiện nhiều lần |
| scope | Các quyền client yêu cầu cho token mới |
| requested_token_type | Loại token client muốn nhận, nếu có |

AS kiểm tra client, subject token, actor token và chính sách ủy quyền. Nếu được phép, AS phát hành token mới và trả về loại token thực tế cùng metadata liên quan.

~~~mermaid
sequenceDiagram
    participant C as Client / Service A
    participant AS as Authorization Server
    participant B as Resource Server B
    C->>AS: Token exchange request (subject_token, resource/audience, scope)
    AS->>AS: Authenticate client
    AS->>AS: Validate subject and optional actor
    AS->>AS: Authorize delegation and target resource
    AS-->>C: New access token for Resource Server B
    C->>B: Authorization: Bearer new-token
    B->>B: Validate issuer, signature, audience, expiry and scope
    B-->>C: Protected resource response
~~~

Token exchange là một giao thức cấp token. Nó không bắt buộc token đầu vào hoặc đầu ra phải là JWT; AS có thể sử dụng JWT, opaque token hoặc loại token khác theo profile. Khi token đầu ra là JWT access token, các quy tắc xác minh JWT vẫn phải được thực thi tại resource server.

## 3. Phân biệt subject_token và actor_token

Hai token này đại diện cho hai vai trò khác nhau:

- **Subject** là người dùng hoặc thực thể mà quyền/truy cập đang được đại diện.
- **Actor** là client hoặc dịch vụ đang thực hiện hành động thay mặt subject.

Ví dụ:

- Alice đăng nhập và có access token dành cho Frontend API.
- Orders Service nhận yêu cầu của Alice và cần gọi Payments API.
- Orders Service là actor; Alice là subject.
- Orders Service yêu cầu AS đổi token đầu vào thành token dành riêng cho Payments API.

Yêu cầu có thể gửi subject_token đại diện cho Alice và actor_token đại diện cho Orders Service. Actor token là tùy chọn trong giao thức; nếu gửi actor_token thì phải khai báo actor_token_type. AS quyết định dựa trên policy liệu actor đó có được phép hành động thay mặt subject hay không.

Ví dụ biểu diễn yêu cầu ở dạng form:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=<subject-access-token>
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&actor_token=<orders-service-token>
&actor_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&resource=https%3A%2F%2Fpayments.example%2F
&scope=payments.write
~~~

Đây là ví dụ minh họa; phương thức client authentication, loại token đầu vào và tham số được chấp nhận phụ thuộc cấu hình AS. Không ghi token thật vào URL, log, tài liệu hoặc ví dụ triển khai.

### Impersonation và delegation

RFC 8693 hỗ trợ các mô hình ngữ nghĩa khác nhau:

- **Impersonation:** actor được phép hành động như subject; resource server có thể nhìn thấy danh tính subject như người đang thực hiện hành động.
- **Delegation:** actor hành động thay mặt subject nhưng vẫn giữ được thông tin rằng actor là một thực thể riêng.

Trong mô hình delegation, claim act được RFC 8693 định nghĩa để biểu diễn actor trong token đầu ra; nó có thể chứa thông tin actor và chuỗi actor lồng nhau theo ngữ nghĩa của RFC. Một hệ thống có thể định nghĩa thêm claim riêng như may_act để mô tả actor tiềm năng được phép hành động thay mặt subject, nhưng đây phải là quy ước của profile/Authorization Server, không được mặc định là claim chuẩn bắt buộc của mọi triển khai. Dù dùng claim nào, thông tin đó vẫn phải nằm trong token được xác minh và được áp dụng theo policy ủy quyền.

Không được mặc định rằng việc có subject_token là đủ để bất kỳ client nào cũng được phép đại diện cho subject. AS phải kiểm tra danh tính client/actor, quan hệ ủy quyền và mục tiêu của token mới.

## 4. Audience và Resource: token mới dành cho ai?

Đây là phần cốt lõi để tránh chuyển tiếp token sai đối tượng nhận.

### Audience

Tham số audience trong token exchange yêu cầu AS phát hành token cho một logical recipient cụ thể. Với JWT access token, claim aud trong token đầu ra xác định resource server hoặc các resource server được phép nhận token theo profile.

Ví dụ:

~~~json
{
  "iss": "https://identity.example",
  "sub": "alice",
  "aud": "https://payments.example/",
  "scope": "payments.write",
  "exp": 1893453600
}
~~~

Payments API phải kiểm tra audience có chứa đúng định danh mà nó được cấu hình chấp nhận hay không. Token có chữ ký hợp lệ nhưng aud chỉ là Orders API vẫn phải bị Payments API từ chối.

### Resource

Tham số resource được định nghĩa trong RFC 8707. Nó xác định resource server bằng URI và giúp AS phát hành token phù hợp với tài nguyên được yêu cầu. Resource indicator là đầu vào cho quyết định cấp token; nó không phải bằng chứng rằng client có quyền truy cập resource đó.

AS cần kiểm tra:

- Resource URI có nằm trong danh sách resource đã đăng ký/được phép hay không.
- Client có được phép yêu cầu token cho resource đó hay không.
- Subject có quyền truy cập resource đó hay không.
- Actor có được phép gọi resource thay mặt subject hay không.
- Scope yêu cầu có phù hợp với resource và chính sách hay không.

Không tự động sao chép mọi audience hoặc resource của token đầu vào sang token đầu ra. Việc chọn recipient phải theo yêu cầu và policy của AS.

### Phân biệt audience, resource và scope

| Thành phần | Trả lời câu hỏi |
| --- | --- |
| audience | Token mới dành cho logical recipient nào? |
| resource | Client yêu cầu token dùng tại resource URI nào? |
| scope | Token mới được phép thực hiện những hành động nào? |
| subject | Quyền đang được đại diện cho ai? |
| actor/client | Thực thể nào đang yêu cầu hoặc hành động thay mặt subject? |

Audience giới hạn nơi token được chấp nhận; scope giới hạn hành động được phép. Có đúng audience không có nghĩa là có đủ quyền, và có scope phù hợp cũng không cho phép dùng token tại một audience khác.

## 5. Token forwarding và confused deputy

### Chuyển tiếp token đầu vào không đúng resource

Giả sử Frontend gửi access token dành cho Orders API. Orders API sau đó gọi Payments API và chuyển tiếp nguyên token đó.

~~~mermaid
flowchart TD
    U["Client có token aud=orders-api"] --> A["Orders API"]
    A -->|"Forward nguyên token"| B["Payments API"]
    B --> C{"aud có chứa payments-api?"}
    C -- Không --> D["Từ chối token"]
    C -- Có --> E["Tiếp tục kiểm tra scope và claims"]
~~~

Nếu Payments API kiểm tra audience đúng, token dành riêng cho Orders API sẽ bị từ chối. Nếu Payments API không kiểm tra audience, token có thể bị chấp nhận ngoài ý định ban đầu.

### Confused deputy

Confused deputy xảy ra khi một dịch vụ có quyền rộng bị người gọi lợi dụng để thực hiện hành động mà người gọi không được phép. Ví dụ, Orders API có service credential để gọi Payments API. Alice yêu cầu Orders API thực hiện một thao tác; nếu Orders API dùng service credential toàn quyền mà không kiểm tra quyền của Alice, nó có thể vô tình dùng quyền của chính mình để vượt qua giới hạn của subject.

Token exchange giúp AS tạo token downstream có thể ràng buộc đồng thời:

- Subject là Alice.
- Actor là Orders API.
- Audience/resource là Payments API.
- Scope chỉ gồm hành động đã được cho phép.
- Thời hạn ngắn và các ràng buộc bổ sung theo policy.

Resource server có thể kiểm tra subject và actor để áp dụng chính sách nghiệp vụ, ví dụ chỉ cho phép Orders Service thực hiện payment capture khi yêu cầu gắn với một order hợp lệ.

Token exchange không tự sửa một thiết kế ủy quyền sai. Nếu AS cấp token rộng hoặc không xác thực actor, confused deputy vẫn có thể xảy ra.

## 6. Không dùng ID Token như access token cho API

Trong OpenID Connect, ID Token là credential mang thông tin xác thực về end-user dành cho OIDC Client (Relying Party). Claim aud của ID Token xác định client nhận, không mặc định là resource server/API.

Vì vậy:

- Không gửi ID Token tới API như bearer access token chỉ vì nó là JWT và có chữ ký hợp lệ.
- API phải yêu cầu access token được phát hành cho chính API đó.
- Client phải kiểm tra ID Token theo quy tắc OIDC, bao gồm issuer, audience, thời hạn và các kiểm tra giao thức liên quan.
- Nếu AS hỗ trợ token exchange với ID Token làm subject_token, chỉ thực hiện khi policy và loại token được hỗ trợ cho phép; token đầu ra vẫn phải là token đúng loại và đúng audience cho API.

Một JWT hợp lệ về chữ ký không tự xác định nó là access token, ID Token hay loại token khác. Loại token, issuer, audience và profile phải được kiểm tra cùng nhau.

## 7. Quy trình token exchange an toàn tại Authorization Server

AS là nơi ra quyết định phát hành token mới. Không nên chỉ kiểm tra rằng subject_token có thể decode hoặc chữ ký hợp lệ rồi phát hành token theo mọi audience mà client yêu cầu.

Quy trình khuyến nghị:

1. **Xác thực client:** kiểm tra client authentication theo phương thức được đăng ký; ràng buộc yêu cầu với client cụ thể.
2. **Kiểm tra grant:** xác nhận client được phép dùng token exchange grant.
3. **Xác định loại token:** kiểm tra subject_token_type và actor_token_type; không đoán loại token từ hình thức chuỗi.
4. **Xác minh subject token:** kiểm tra chữ ký/introspection, issuer, audience, thời hạn, loại token và trạng thái theo policy.
5. **Xác minh actor token nếu có:** xác thực actor và quyền được đại diện; ràng buộc actor với client đang gọi theo profile.
6. **Xác định mục tiêu:** kiểm tra resource/audience có hợp lệ và được client yêu cầu trong phạm vi cho phép.
7. **Đánh giá scope:** tính giao của quyền subject, quyền actor/client, resource policy và scope được yêu cầu.
8. **Áp dụng delegation/impersonation policy:** quyết định subject/actor nào sẽ được biểu diễn trong token đầu ra.
9. **Phát hành token mới:** đặt audience/resource, scope, thời hạn, loại token và các claim cần thiết theo profile.
10. **Trả response đúng loại:** client phải kiểm tra issued_token_type, token_type, expires_in và scope thực tế.

~~~mermaid
flowchart TD
    A["Nhận token exchange request"] --> B["Authenticate client"]
    B --> C{"Client được phép dùng grant?"}
    C -- Không --> X["Từ chối"]
    C -- Có --> D["Validate subject_token và loại token"]
    D --> E{"Subject token hợp lệ?"}
    E -- Không --> X
    E -- Có --> F{"Có actor_token?"}
    F -- Có --> G["Validate actor và quan hệ ủy quyền"]
    F -- Không --> H["Áp dụng policy cho client"]
    G --> I{"Actor được phép hành động?"}
    I -- Không --> X
    I -- Có --> J["Kiểm tra resource, audience và scope"]
    H --> J
    J --> K{"Yêu cầu nằm trong quyền được phép?"}
    K -- Không --> X
    K -- Có --> L["Phát hành token mới theo target policy"]
    L --> M["Trả issued_token_type, token_type, scope và expires_in"]
~~~

### Quyền của token đầu ra

Không mặc định token mới được kế thừa toàn bộ quyền của subject_token. AS cần áp dụng chính sách để giới hạn:

- Resource/audience đích.
- Scope được cấp.
- Thời hạn token.
- Loại token.
- Subject và actor.
- Sender constraint nếu profile yêu cầu.
- Các claim nhạy cảm được phép chuyển tiếp.

Scope trong response phản ánh quyền thực tế được cấp khi AS trả trường này. Client không được giả định AS đã cấp toàn bộ scope yêu cầu; phải xử lý theo response và token được phát hành.

## 8. Ví dụ yêu cầu và phản hồi

### Yêu cầu

Ví dụ client Orders Service yêu cầu token mới cho Payments API:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=<orders-user-access-token>
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&resource=https%3A%2F%2Fpayments.example%2F
&scope=payments.write
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
~~~

Trong ví dụ này actor_token không được gửi; AS phải áp dụng policy dựa trên client đã xác thực và subject token. Nếu cần biểu diễn actor tách biệt hoặc yêu cầu bằng chứng riêng cho actor, profile có thể yêu cầu actor_token.

### Phản hồi

~~~json
{
  "access_token": "<new-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "payments.write"
}
~~~

Các trường minh họa cho thấy:

- access_token là token mới được cấp.
- issued_token_type mô tả loại token được phát hành.
- token_type mô tả cách client sử dụng token tại resource server, ví dụ Bearer.
- expires_in là thời gian sống được trả về.
- scope là scope thực tế được cấp nếu response bao gồm trường này.

Client phải sử dụng token mới cho Payments API theo đúng token type. Không dùng subject_token thay thế khi token exchange thất bại.

### Ví dụ JWT access token đầu ra

Nếu AS phát hành JWT access token theo RFC 9068, header có thể dùng typ là at+jwt và payload có thể chứa:

~~~json
{
  "iss": "https://identity.example",
  "sub": "alice",
  "aud": "https://payments.example/",
  "client_id": "orders-service",
  "scope": "payments.write",
  "iat": 1893450000,
  "exp": 1893450300,
  "jti": "issued-token-id",
  "act": {
    "sub": "orders-service"
  }
}
~~~

Đây là payload minh họa cho mô hình delegation; claim và cấu trúc thực tế phụ thuộc profile. Resource server không được tin JSON này chỉ vì decode thành công. Nó phải xác minh chữ ký, issuer, audience, thời gian, loại token và scope. Nếu profile dùng claim act, cần kiểm tra actor theo policy.

## 9. Xác minh token tại Resource Server

Token exchange chỉ có ý nghĩa nếu resource server kiểm tra đúng token được cấp cho nó. Một access token có chữ ký hợp lệ nhưng sai audience vẫn không được chấp nhận.

Resource server nên:

1. Chỉ nhận loại access token được profile quy định; không nhận ID Token hoặc subject token tùy ý.
2. Xác minh chữ ký hoặc introspection theo nguồn tin cậy; allowlist thuật toán độc lập với token.
3. Kiểm tra issuer đúng AS được cấu hình.
4. Kiểm tra audience chứa định danh chính xác của resource server.
5. Kiểm tra exp, nbf và các giới hạn thời gian.
6. Kiểm tra scope đủ cho thao tác hiện tại.
7. Kiểm tra client_id, subject và actor nếu chính sách yêu cầu.
8. Kiểm tra token type/profile; với JWT access token theo RFC 9068, xử lý typ at+jwt và các yêu cầu của profile.
9. Nếu token sender-constrained, xác minh bằng chứng sở hữu khóa theo cơ chế DPoP hoặc mTLS tương ứng.
10. Từ chối token có audience không phù hợp, kể cả khi chữ ký hợp lệ.

~~~mermaid
flowchart TD
    A["Payments API nhận access token"] --> B["Parse theo access-token profile"]
    B --> C["Verify signature / introspection"]
    C --> D{"Issuer và token type hợp lệ?"}
    D -- Không --> X["Từ chối"]
    D -- Có --> E{"aud chứa Payments API?"}
    E -- Không --> X
    E -- Có --> F{"Token còn hiệu lực?"}
    F -- Không --> X
    F -- Có --> G{"scope đủ cho thao tác?"}
    G -- Không --> X
    G -- Có --> H["Kiểm tra subject, actor và sender constraint"]
    H --> I{"Policy cho phép?"}
    I -- Không --> X
    I -- Có --> J["Thực hiện thao tác"]
~~~

### Không dùng audience như một chuỗi tùy ý

Định danh audience phải được cấu hình thống nhất giữa AS và resource server. Không dùng phép so khớp substring hoặc prefix lỏng lẻo. Ví dụ, audience https://api.example không nên được coi là khớp với https://api.example.attacker.invalid chỉ vì có cùng prefix.

Nếu aud là mảng, resource server phải kiểm tra một phần tử khớp với identifier được cấu hình. Nếu aud là string, so sánh theo quy tắc profile. Không tự chuẩn hóa URI theo cách làm hai resource khác nhau trở thành một.

## 10. Downscoping và quyền tối thiểu

Token exchange thường được dùng để tạo token có phạm vi hẹp hơn token đầu vào. Đây là downscoping.

Ví dụ:

| Thuộc tính | Token đầu vào | Token mới |
| --- | --- | --- |
| Subject | Alice | Alice |
| Actor | Client/Service A | Service A nếu profile biểu diễn delegation |
| Audience | Orders API | Payments API |
| Scope | orders.read orders.write payments.read payments.write | payments.write |
| Thời hạn | 30 phút | 5 phút |

Đây là minh họa; AS quyết định quyền thực tế. Token mới không nên có nhiều quyền hơn những gì subject, actor và policy cho phép. Nếu yêu cầu scope vượt quyền, AS có thể từ chối hoặc cấp tập quyền hẹp hơn theo quy tắc được công bố.

Không suy ra rằng mọi AS bắt buộc phải tự động downscope chỉ vì client yêu cầu scope nhỏ hơn. Client cần kiểm tra scope thực tế trong response hoặc token và resource server phải thực thi quyền được cấp.

## 11. Sender-constrained token và chuyển tiếp an toàn

Bearer token có thể được sử dụng bởi bất kỳ bên nào sở hữu token. Nếu token bị chuyển tiếp hoặc rò rỉ, bên khác có thể sử dụng nó trong thời gian token còn hiệu lực nếu đáp ứng audience và policy.

Đối với hệ thống cần giảm nguy cơ token bị đánh cắp, có thể dùng sender-constrained access token:

- **mTLS-bound access token:** token được ràng buộc với chứng thư client; resource server kiểm tra bằng chứng TLS client certificate tương ứng.
- **DPoP-bound access token:** token được ràng buộc với public key; client gửi DPoP proof và resource server xác minh proof theo RFC 9449.

Khi token được exchange, AS và profile phải xác định liệu sender constraint có được giữ, thay đổi hay tạo mới. Không sao chép claim cnf hoặc thông tin binding một cách mù quáng. Token đầu ra phải được ràng buộc với key/certificate mà client downstream thực sự sở hữu và có thể chứng minh.

Nếu Orders Service exchange token rồi gửi cho một worker khác không sở hữu khóa DPoP hoặc certificate tương ứng, worker đó không thể sử dụng token sender-constrained một cách hợp lệ. Cần thực hiện exchange cho đúng client/actor downstream hoặc thiết kế kênh ủy quyền phù hợp.

## 12. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Forward nguyên access token sang API khác | Token có thể sai audience hoặc quyền | Exchange token cho đúng resource/audience |
| Resource server không kiểm tra aud | Token dành cho API khác vẫn được chấp nhận | Kiểm tra audience chính xác tại mọi resource server |
| Dùng ID Token làm access token | Nhầm audience OIDC client với resource server | Chỉ dùng access token đúng profile |
| AS chỉ xác minh subject_token mà không xác thực client | Client bất kỳ có thể yêu cầu đổi token | Authenticate client và kiểm tra grant permission |
| Bỏ qua actor_token khi policy yêu cầu delegation | Không xác định được dịch vụ nào đang hành động | Xác minh actor và quan hệ ủy quyền |
| Tin actor_token do client gửi mà không kiểm tra | Attacker tự khai actor hoặc dùng token actor sai ngữ cảnh | Kiểm tra issuer, audience, loại token và client binding |
| Cấp token mới theo mọi resource/audience client yêu cầu | Mở rộng quyền và tạo confused deputy | Allowlist resource, audience và client-resource policy |
| Giữ nguyên mọi scope từ token đầu vào | Token downstream có quyền quá rộng | Downscope theo subject, actor, resource và policy |
| Không kiểm tra issued_token_type/token_type | Client dùng sai loại credential | Kiểm tra loại token thực tế được trả về |
| Cho rằng token exchange luôn trả JWT | Client hoặc API xử lý sai định dạng | Dựa vào issued_token_type và profile |
| Không kiểm tra act/subject khi delegation cần phân biệt | Mất thông tin ai đang hành động thay mặt ai | Áp dụng policy subject/actor rõ ràng |
| Chuyển tiếp sender-constrained token cho client không có khóa | Request downstream thất bại hoặc thiết kế binding bị phá vỡ | Exchange/bind token cho đúng client sở hữu khóa |
| Dùng token đầu vào khi exchange thất bại | Bỏ qua audience và policy của downstream | Fail closed; không fallback sang token sai đối tượng |
| Log subject_token, actor_token hoặc access_token mới | Rò rỉ bearer credential | Redact token và hạn chế log |

## 13. Bộ ca kiểm thử

Giả sử Orders Service cần gọi Payments API bằng token exchange. AS chỉ cho phép client orders-service yêu cầu resource Payments API và scope payments.write nếu Alice có quyền tương ứng.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Client được xác thực, subject token hợp lệ, resource/audience và scope được phép | **Cấp token mới** cho Payments API |
| Client không được phép dùng token exchange grant | **Từ chối** |
| subject_token hết hạn hoặc chữ ký không hợp lệ | **Từ chối** |
| subject_token có audience không được phép làm đầu vào theo policy | **Từ chối** |
| subject_token_type không được hỗ trợ | **Từ chối** |
| actor_token được gửi nhưng thiếu actor_token_type | **Từ chối request** |
| actor token hết hạn hoặc không thuộc actor/client được phép | **Từ chối** |
| Actor không được phép đại diện cho subject | **Từ chối** |
| Client yêu cầu resource ngoài allowlist | **Từ chối** |
| Client yêu cầu Payments API nhưng AS cấp token chỉ có aud=Orders API | Không được sử dụng tại Payments API; AS cần phát hành đúng recipient hoặc từ chối |
| Scope yêu cầu vượt quyền subject/actor | **Từ chối hoặc cấp scope hẹp hơn** theo policy công bố |
| Response trả scope hẹp hơn yêu cầu | Client chỉ được sử dụng scope thực tế được cấp |
| Token mới có chữ ký hợp lệ nhưng aud không chứa Payments API | Payments API **từ chối** |
| Token có aud đúng nhưng thiếu payments.write | Từ chối thao tác ghi |
| Token là ID Token có aud là OIDC client | API **từ chối** như access token |
| Token đầu vào được forward nguyên sang Payments API và aud chỉ là Orders API | Payments API **từ chối** |
| Token exchange thất bại do AS timeout | Không fallback sang token đầu vào sai audience |
| Token sender-constrained được gửi bởi client không sở hữu key/certificate | **Từ chối** bằng chứng sender |
| Token mới hết hạn hoặc chưa đến nbf | **Từ chối** |
| Token có act claim nhưng actor không được policy cho phép | **Từ chối** |

Kiểm thử cần xác nhận cả hai phía:

- AS không phát hành token cho resource/audience hoặc scope ngoài policy.
- Resource server từ chối token sai audience, sai loại, sai thời hạn hoặc sai quyền, kể cả khi chữ ký hợp lệ.

## 14. Ghi nhớ

- Token exchange theo RFC 8693 cho phép đổi một token hiện có thành token mới theo ngữ cảnh và policy của Authorization Server.
- subject_token đại diện cho subject; actor_token đại diện cho actor nếu được sử dụng. Hai vai trò không được nhập nhằng.
- audience xác định logical recipient; resource xác định resource URI; scope xác định quyền. Cả ba cần được kiểm tra riêng.
- Không forward nguyên token sang API khác nếu token không được phát hành cho API đó.
- AS phải xác thực client, subject token, actor token nếu có và quyền yêu cầu trước khi phát hành token mới.
- Token đầu ra cần được giới hạn theo resource, audience, scope, thời hạn, subject và actor.
- Resource server phải xác minh issuer, chữ ký/introspection, audience, thời gian, loại token và scope trước khi thực hiện thao tác.
- ID Token dành cho OIDC client; không mặc định dùng nó như access token cho API.
- Sender constraint như mTLS hoặc DPoP cần được duy trì/ràng buộc đúng với client downstream sở hữu khóa.
- Nếu token exchange thất bại hoặc không có token đúng audience, từ chối request; không fallback sang token sai đối tượng.

### Tài liệu chuẩn tham khảo

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): grant type, subject/actor token, token type và delegation.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): tham số resource và giới hạn token theo resource server.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token, typ và audience.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth hiện hành.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách sử dụng bearer access token và rủi ro chuyển tiếp.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained token bằng mTLS.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof-of-possession và ràng buộc token với khóa.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): vai trò ID Token, issuer, audience và xác minh OIDC.
