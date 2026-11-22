# Chuyển tiếp token gốc và đổi sang token dành riêng cho dịch vụ đích

> **Chương:** Ranh giới dịch vụ  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung áp dụng cho kiến trúc OAuth 2.0 và hệ thống nhiều dịch vụ nói chung, độc lập với ngôn ngữ lập trình hoặc framework.

## 1. Bài toán khi một dịch vụ gọi dịch vụ khác

Một request thường đi qua nhiều dịch vụ trước khi hoàn thành. Ví dụ, người dùng gọi Orders API; Orders API cần gọi Inventory API để giữ hàng, rồi gọi Billing API để tạo khoản thanh toán.

Token mà người dùng gửi đến Orders API được phát hành cho một mục đích và một tập tài nguyên nhất định. Khi Orders API gọi Inventory API, hệ thống phải quyết định credential nào được gửi sang dịch vụ đích.

Có hai cách chính:

- **Chuyển tiếp token gốc (token forwarding):** gửi nguyên access token nhận được từ request ban đầu đến dịch vụ tiếp theo.
- **Đổi token (token exchange):** gửi token gốc và danh tính dịch vụ đang thực hiện lời gọi đến authorization server; authorization server xác minh quyền ủy quyền rồi cấp một token mới phù hợp với dịch vụ đích.

Hai cách này không tương đương. Token forwarding giữ nguyên issuer, audience, scope, thời hạn và ràng buộc người gửi của token ban đầu. Token exchange tạo một credential mới theo chính sách của authorization server, có thể giới hạn audience, scope, thời hạn và ghi nhận actor đang thay mặt subject.

Ví dụ:

~~~mermaid
flowchart LR
    U["Client / User"] -->|"Token U: aud=orders-api"| A["Orders API"]
    A -->|"Forward token U?"| B["Inventory API"]
    A -->|"Exchange subject token"| AS["Authorization Server"]
    AS -->|"Token B: aud=inventory-api"| A
    A -->|"Token B"| B
~~~

Nếu token ban đầu chỉ dành cho Orders API, Inventory API phải từ chối token đó. Orders API không được sửa claim `aud` trong JWT rồi gửi tiếp, vì chữ ký không còn hợp lệ. Nếu Inventory API cần một credential riêng, phải lấy token được phát hành hợp lệ cho Inventory API.

## 2. Phân biệt token forwarding và token exchange

| Tiêu chí | Chuyển tiếp token gốc | Đổi token cho dịch vụ đích |
|---|---|---|
| Token gửi đến dịch vụ đích | Chính token nhận từ request trước | Token mới do authorization server cấp |
| Issuer | Giữ nguyên | Có thể giữ nguyên hoặc đổi theo trust domain |
| Audience | Giữ nguyên | Được yêu cầu theo resource/audience của dịch vụ đích |
| Scope/quyền | Giữ nguyên toàn bộ scope của token gốc | Authorization server có thể cấp tập quyền hẹp hơn theo policy |
| Subject | Giữ nguyên | Thường giữ subject của token nguồn nếu cần hành động thay mặt người dùng |
| Actor | Không tự thể hiện dịch vụ trung gian nếu token không có cơ chế ghi nhận | Có thể ghi nhận actor bằng claim `act` trong JWT theo RFC 8693 |
| Thời hạn | Giữ nguyên thời hạn còn lại | Authorization server cấp thời hạn theo policy; nên đủ ngắn cho tác vụ |
| Phụ thuộc authorization server | Không cần gọi lại ở mỗi hop | Cần gọi token endpoint khi exchange, có thể dùng cache có kiểm soát |
| Ranh giới tin cậy | Dịch vụ đích phải tin token gốc và issuer của nó | Authorization server xác minh và phát hành token cho ngữ cảnh đích |
| Rủi ro chính | Lộ token gốc, audience quá rộng, quyền vượt nhu cầu dịch vụ đích | Exchange policy sai, cấp token quá quyền hoặc không xác thực actor |

Token exchange là một giao thức chuẩn hóa trong OAuth 2.0, được định nghĩa bởi [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html). Authorization server đóng vai trò Security Token Service (STS): xác minh token đầu vào và phát hành security token phù hợp với tài nguyên hoặc ngữ cảnh mới.

**Không phải mọi lời gọi nội bộ đều bắt buộc phải exchange.** Chuyển tiếp token gốc có thể chấp nhận nếu token đã được phát hành cho đúng dịch vụ đích, quyền đủ hẹp, trust contract cho phép chuyển tiếp và ràng buộc sender vẫn được đáp ứng. Khi các điều kiện đó không có, token exchange hoặc credential dành riêng cho workload là lựa chọn phù hợp hơn.

## 3. Vì sao không nên chuyển tiếp mọi token?

### 3.1. Audience không khớp với dịch vụ đích

Giả sử token người dùng có:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-482",
  "aud": "https://orders.example.test",
  "scope": "orders:create orders:read",
  "exp": 1800000300
}
~~~

Token này dành cho Orders API. Khi Orders API chuyển nguyên token sang Inventory API:

- Inventory API thấy audience không phải của mình.
- Inventory API phải từ chối token theo chính sách audience restriction.
- Nếu Inventory API bỏ qua kiểm tra audience để lời gọi chạy được, nó chấp nhận credential được phát hành cho một resource server khác.

Đây là lỗi ranh giới dịch vụ. Audience restriction giúp ngăn token bị dùng lại tại một resource server ngoài dự kiến. RFC 9700 §2.3 khuyến nghị access token chỉ dành cho một resource server cụ thể hoặc một tập nhỏ resource server; resource server phải kiểm tra token có được dành cho chính nó hay không và từ chối nếu audience không khớp.

### 3.2. Quyền của token gốc rộng hơn nhu cầu downstream

Token ban đầu có thể chứa quyền:

~~~text
orders:create orders:read orders:cancel inventory:read inventory:reserve billing:charge
~~~

Inventory API chỉ cần `inventory:reserve`. Nếu Orders API chuyển tiếp token rộng đó, Inventory API có thể nhận nhiều quyền hơn cần thiết cho tác vụ.

Ngay cả khi audience hợp lệ, scope quá rộng vẫn làm tăng tác động nếu token bị lộ hoặc dịch vụ downstream bị xâm nhập.

Token exchange cho phép yêu cầu scope phù hợp với dịch vụ đích. Authorization server phải tự đánh giá và quyết định scope được cấp; nó không được mù quáng chấp nhận mọi scope mà dịch vụ gọi yêu cầu.

### 3.3. Token người dùng bị lan truyền qua nhiều dịch vụ

Nếu một token gốc được chuyển qua nhiều hop:

~~~text
Client -> API Gateway -> Orders -> Inventory -> Warehouse
~~~

mỗi dịch vụ có thể nhìn thấy và lưu giữ cùng một bearer token. Một dịch vụ bị xâm nhập hoặc log bị lộ có thể làm lộ credential dùng được ở những nơi khác nếu audience và scope của token đủ rộng.

Token exchange tạo token theo từng ranh giới dịch vụ. Điều này không loại bỏ mọi rủi ro, nhưng giúp giới hạn nơi token mới có thể được sử dụng và quyền mà nó đại diện.

### 3.4. Không biết dịch vụ nào đang thực hiện hành động

Token chỉ có subject người dùng có thể không cho downstream biết lời gọi thực tế đến từ Orders, Gateway hay một dịch vụ khác.

Trong mô hình delegation, cần phân biệt:

- **Subject:** người dùng hoặc chủ thể mà hành động được thực hiện thay mặt.
- **Actor:** dịch vụ hoặc client đang thực hiện lời gọi.
- **Audience:** dịch vụ được phép nhận và sử dụng token.
- **Scope:** hành động được phép trong phạm vi resource.

Token exchange có thể giữ subject và ghi nhận actor để downstream áp dụng policy và audit phù hợp.

## 4. Khi nào có thể chuyển tiếp token gốc?

Chuyển tiếp nguyên token có thể là lựa chọn hợp lý nếu tất cả điều kiện sau được đáp ứng:

1. **Audience đã bao gồm dịch vụ đích.** Token được authorization server phát hành rõ ràng cho dịch vụ đích hoặc một tập nhỏ tài nguyên có thỏa thuận chung.
2. **Scope đủ hẹp.** Token chỉ chứa quyền cần thiết cho tác vụ downstream.
3. **Dịch vụ đích tin issuer.** Downstream có trust configuration và xác minh chữ ký/introspection đúng profile.
4. **Hợp đồng cho phép forwarding.** Dịch vụ trung gian được quyền chuyển token đến resource server đó.
5. **Sender constraint tương thích.** Nếu token gắn với mTLS hoặc DPoP, dịch vụ đang gửi request phải nắm giữ khóa/chứng thư được ràng buộc để tạo proof; resource server đích phải kiểm tra proof đó.
6. **Không có yêu cầu ghi nhận actor mới.** Hoặc hệ thống có cơ chế khác đủ tin cậy để lưu danh tính dịch vụ gọi.
7. **Token không bị mở rộng phạm vi qua hop.** Không gửi token đến dịch vụ ngoài tập audience hoặc trust boundary đã xác định.

Ví dụ, một API gateway chỉ định tuyến request đến đúng resource server và token đã được cấp cho resource server đó. Gateway không thay đổi subject, quyền hay ngữ cảnh ủy quyền; forwarding có thể được cho phép theo hợp đồng.

Ngược lại, nếu token chỉ dành cho gateway, dịch vụ phía sau không được chấp nhận token đó chỉ vì gateway đã xác minh thành công.

### 4.1. Nhiều audience không phải cách giải quyết mặc định

Một token có thể được cấp cho nhiều audience. Tuy nhiên, mỗi audience bổ sung làm tăng số resource server có thể sử dụng cùng credential.

RFC 9700 khuyến nghị audience càng cụ thể càng tốt; nếu không thể giới hạn một resource server thì chỉ nên dùng một tập nhỏ. Không thêm tất cả dịch vụ nội bộ vào `aud` chỉ để tránh triển khai token exchange.

### 4.2. Sender-constrained token có thể không forward được

Token có thể được ràng buộc với chứng thư mTLS hoặc khóa DPoP. Khi đó, token không chỉ yêu cầu người gửi sở hữu chuỗi token mà còn phải chứng minh quyền sở hữu khóa tương ứng.

Nếu token được ràng buộc với key của client ban đầu mà Orders API không nắm giữ, Orders không thể tùy ý forward token rồi dùng key khác để gọi Inventory API. Service gửi request phải chứng minh quyền sở hữu đúng key đã bind; nếu không thể, authorization server cần cấp token mới phù hợp với actor/key của service trung gian theo policy.

Không loại bỏ hoặc bỏ qua claim `cnf` và không biến sender-constrained token thành bearer token bằng cách copy chuỗi token.

## 5. Khi nào nên đổi token cho dịch vụ đích?

Token exchange thường phù hợp khi:

- Token gốc có audience dành cho dịch vụ hiện tại, không dành cho downstream.
- Downstream cần một tập scope khác hoặc hẹp hơn.
- Dịch vụ trung gian cần hành động thay mặt người dùng và phải ghi nhận danh tính actor.
- Các dịch vụ thuộc trust domain hoặc policy khác nhau.
- Muốn giới hạn thời hạn và loại token theo từng resource server.
- Muốn downstream chỉ chấp nhận token được authorization server cấp riêng cho nó.
- Một service nhận access token rồi gọi backend service theo mô hình được mô tả trong RFC 8693 §2.3.

Nếu dịch vụ chỉ cần xác thực chính workload của nó và không cần hành động thay mặt người dùng, hãy cân nhắc client credentials hoặc workload identity. Không tạo subject người dùng giả chỉ để dùng token exchange.

### 5.1. Ma trận quyết định

| Tình huống | Hướng xử lý thường phù hợp |
|---|---|
| Token đã có `aud` là dịch vụ đích, scope hẹp và forwarding được policy cho phép | Có thể forward token gốc |
| Token chỉ có `aud` của dịch vụ hiện tại | Exchange token cho dịch vụ đích |
| Downstream cần quyền ít hơn token gốc | Exchange với scope hẹp hơn |
| Downstream cần biết service nào đang thay mặt user | Exchange theo delegation và ghi actor |
| Downstream chỉ cần danh tính workload, không cần user context | Client credentials/workload token |
| Token gốc bị ràng buộc với key mà service trung gian không nắm giữ | Exchange để cấp token phù hợp với sender/key của service trung gian, nếu policy hỗ trợ |
| Downstream thuộc trust domain khác | Exchange qua authorization server/trust bridge được hai bên tin cậy |
| Token gốc là ID Token | Không dùng như access token; lấy access token phù hợp cho resource server |

## 6. OAuth 2.0 Token Exchange theo RFC 8693

RFC 8693 mở rộng OAuth 2.0 bằng grant type:

~~~text
urn:ietf:params:oauth:grant-type:token-exchange
~~~

Một resource server có thể đóng vai trò OAuth client khi gọi token endpoint để đổi access token nhận từ request thành token phù hợp với backend service.

### 6.1. Các tham số quan trọng

| Tham số | Ý nghĩa |
|---|---|
| `grant_type` | Bắt buộc; xác định đây là yêu cầu token exchange. |
| `subject_token` | Bắt buộc; token đại diện cho chủ thể mà quyền được yêu cầu thay mặt. |
| `subject_token_type` | Bắt buộc; định danh loại token được gửi trong `subject_token`. |
| `actor_token` | Tùy chọn; token đại diện cho actor đang thực hiện hành động thay mặt subject. |
| `actor_token_type` | Bắt buộc nếu có `actor_token`; xác định loại actor token. |
| `audience` | Tùy chọn; tên logic của dịch vụ đích mà token mới sẽ được sử dụng. |
| `resource` | Tùy chọn; URI xác định resource server hoặc tài nguyên đích. |
| `scope` | Tùy chọn; quyền mong muốn trong ngữ cảnh resource/audience đích. |
| `requested_token_type` | Tùy chọn; loại security token mà client yêu cầu authorization server phát hành. |

Authorization server xác minh token nguồn và actor token nếu có, xác thực client gọi token endpoint theo policy, rồi quyết định có cho phép exchange hay không. Nếu token đầu vào không hợp lệ hoặc không được policy chấp nhận, server phải từ chối. Nếu resource/audience đích không được hỗ trợ, RFC 8693 định nghĩa lỗi `invalid_target`.

### 6.2. subject_token và actor_token khác nhau

Ví dụ người dùng A gọi Orders API, sau đó Orders API cần gọi Inventory API:

- `subject_token`: access token của người dùng A, thể hiện quyền mà A đã cấp.
- `actor_token`: credential thể hiện Orders service đang thực hiện lời gọi.
- Client authentication: chứng minh chính Orders service đang gọi token endpoint.

Không nhầm `actor_token` với `subject_token`:

| Thành phần | Trả lời câu hỏi |
|---|---|
| `subject_token` | Hành động này được thực hiện thay mặt ai? |
| `actor_token` | Chủ thể/dịch vụ nào đang hành động? |
| Client authentication | Ai đang gọi token endpoint và có được phép exchange không? |
| `audience`/`resource` | Token mới được dùng ở đâu? |
| `scope` | Token mới được phép làm gì? |

`actor_token` là tùy chọn theo RFC 8693. Nếu deployment không gửi actor token, authorization server vẫn phải có policy xác định client nào được exchange và trong vai trò nào. Không suy ra actor hợp lệ chỉ từ việc một service có thể gửi `subject_token`.

Danh tính actor phải đủ rõ để phân biệt các service hoặc principal khác nhau. Trong một số hệ thống, chỉ `sub` chưa đủ duy nhất; kết hợp `iss` và `sub` có thể cần thiết để định danh actor.

### 6.3. Delegation và impersonation

RFC 8693 phân biệt hai ngữ nghĩa:

- **Delegation:** service A giữ danh tính riêng của nó và hành động thay mặt user B. Token có thể thể hiện cả subject B và actor A.
- **Impersonation:** A được cấp token thể hiện như B trong ngữ cảnh quyền được ủy quyền; bên nhận token có thể không thấy danh tính actor theo cùng cách như delegation.

Với kiến trúc nhiều dịch vụ cần audit rõ dịch vụ nào đã thực hiện hành động, delegation thường giúp giữ ranh giới danh tính tốt hơn. Quyết định cuối cùng phụ thuộc policy và trust model.

Trong JWT theo RFC 8693, `act` ghi nhận actor hiện tại của token; `may_act` có thể biểu thị principal nào được phép trở thành actor. `may_act` là thông tin phục vụ quyết định ủy quyền của authorization server, không có nghĩa actor đã thực sự thực hiện hành động. Không nhầm quyền được phép ủy quyền với danh tính actor hiện tại.

## 7. Ví dụ luồng token exchange cho dịch vụ đích

Giả sử:

- User gọi Orders API.
- Token nguồn dành cho Orders API.
- Orders API cần gọi Inventory API để giữ hàng.
- Inventory API chỉ cần quyền `inventory:reserve`.
- Authorization server cho phép Orders service hành động thay mặt user trong phạm vi này.

~~~mermaid
sequenceDiagram
    participant U as User Client
    participant O as Orders API
    participant AS as Authorization Server
    participant I as Inventory API

    U->>O: Request + access token for Orders
    O->>O: Validate token, subject, audience, scope
    O->>AS: Token exchange: subject_token + actor identity + audience=Inventory
    AS->>AS: Authenticate Orders service
    AS->>AS: Validate subject token and delegation policy
    AS->>AS: Apply Inventory audience and minimal scope
    AS-->>O: New access token for Inventory
    O->>I: Request + new Inventory token
    I->>I: Validate issuer, audience, expiry and scope
    I-->>O: Inventory result
    O-->>U: Orders response
~~~

### 7.1. Request minh họa

Request dưới đây là ví dụ khái niệm. Client authentication được thể hiện bằng placeholder; token thật không được ghi vào log hoặc tài liệu:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Authorization: <client-authentication-for-orders-service>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=<user-access-token>
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&actor_token=<orders-service-identity-token>
&actor_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=https%3A%2F%2Finventory.example.test
&scope=inventory%3Areserve
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
~~~

Một số deployment dùng `resource` là URI của Inventory API thay cho hoặc cùng với `audience` theo contract. Không gửi một giá trị tùy ý do request bên ngoài kiểm soát; Orders service phải chọn resource/audience từ cấu hình hoặc mapping tin cậy.

### 7.2. Response minh họa

~~~json
{
  "access_token": "<new-token-for-inventory>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 120,
  "scope": "inventory:reserve"
}
~~~

`access_token` trong response mang token mới. `issued_token_type` cho biết loại biểu diễn của security token được cấp; `token_type` cho biết cách client sử dụng token, ví dụ `Bearer`. Hai trường này có ý nghĩa khác nhau.

Token mới có thể là JWT hoặc opaque token. Access token là ý nghĩa ủy quyền; JWT là định dạng token. Không phải mọi access token đều là JWT và không phải mọi JWT đều là access token.

### 7.3. Claims của token mới

Nếu authorization server phát hành JWT access token, payload có thể có dạng:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-482",
  "aud": "https://inventory.example.test",
  "client_id": "orders-service",
  "scope": "inventory:reserve",
  "act": {
    "sub": "orders-service"
  },
  "iat": 1800000000,
  "exp": 1800000120
}
~~~

Đây là ví dụ minh họa, không phải bộ claim bắt buộc cho mọi deployment.

- `sub` tiếp tục đại diện cho người dùng.
- `aud` xác định Inventory API là resource server dự kiến.
- `scope` chỉ giữ quyền cần cho thao tác giữ hàng.
- `client_id` định danh client đã yêu cầu token theo profile.
- `act` thể hiện Orders service là actor hiện tại trong mô hình delegation.

Nếu không cần delegation hoặc actor tracking, token có thể không chứa `act`; policy của authorization server quyết định. Không tự thêm claim `act` ở phía Orders API vì claim này phải đến từ nguồn phát hành được tin cậy.

## 8. Authorization server phải kiểm tra gì?

Token exchange không tự động thu hẹp quyền. Nếu authorization server chấp nhận mọi yêu cầu và phát hành token với scope tùy ý, exchange chỉ tạo thêm một đường để biến token bị đánh cắp thành credential khác.

Authorization server nên kiểm tra:

1. **Client authentication:** xác thực Orders service bằng phương thức đã cấu hình; không cho client không xác định tùy ý đổi token.
2. **Subject token:** xác minh chữ ký hoặc trạng thái token, issuer, audience, thời hạn, loại token và policy áp dụng.
3. **Actor token:** nếu có, xác minh token và danh tính actor theo trust configuration.
4. **Quyền delegation:** client/actor có được phép hành động thay mặt subject này không? Nếu token có `may_act`, có thể dùng claim đó như một tín hiệu policy sau khi token nguồn đã được xác minh.
5. **Target resource:** `audience` hoặc `resource` có nằm trong danh sách resource được phép cho client và subject không?
6. **Scope:** scope yêu cầu có nằm trong quyền subject đã được cấp và quyền actor được phép sử dụng không?
7. **Thời hạn:** token mới có lifetime phù hợp với tác vụ và policy không?
8. **Token type:** loại token được phát hành có đúng loại downstream mong đợi không?
9. **Thông tin tối thiểu:** chỉ đưa claims cần thiết cho dịch vụ đích; không sao chép toàn bộ dữ liệu cá nhân hoặc quyền của token gốc.

Authorization server không nên cấp token rộng hơn chỉ vì Orders service yêu cầu. Scope của token mới phải chịu sự chi phối của quyền subject, quyền actor, resource đích và policy hệ thống.

### 8.1. Không tin audience/resource do caller tự khai báo

Tham số `audience` hoặc `resource` trong request là yêu cầu của client, không phải bằng chứng client có quyền truy cập resource đó.

Authorization server cần mapping giá trị này đến resource đã đăng ký và kiểm tra client có quyền exchange sang resource đó hay không. RFC 8707 định nghĩa `resource` parameter để client chỉ rõ protected resource dự kiến; authorization server nên giới hạn audience của access token theo resource được yêu cầu.

### 8.2. Không để token exchange trở thành confused deputy

Confused deputy xảy ra khi dịch vụ có quyền mạnh dùng quyền của mình theo yêu cầu của một caller không được phép.

Ví dụ:

- User không có quyền gọi Billing API.
- User gửi request đến Orders API, kèm subject token hợp lệ.
- Orders API có quyền exchange token sang Billing API.
- Nếu Orders API chỉ kiểm tra subject token hợp lệ mà không kiểm tra policy, nó có thể xin token Billing thay mặt user và vô tình nâng quyền.

Cần kiểm tra đồng thời subject, actor/client, target resource và hành động được yêu cầu. Token exchange không biến một service thành đại diện toàn quyền của mọi user.

## 9. Dịch vụ đích phải xác minh token mới

Inventory API không được tin token chỉ vì Orders API nói rằng token đã được exchange thành công. Nó phải tự xác minh credential nhận được theo profile của mình.

Các kiểm tra thường gồm:

| Kiểm tra | Câu hỏi |
|---|---|
| Issuer (`iss`) | Token được phát hành bởi authorization server mà Inventory API tin cậy? |
| Signature hoặc introspection | Token có hợp lệ và chưa bị thu hồi theo cơ chế được sử dụng? |
| Audience (`aud`) | Token có dành cho Inventory API không? |
| Expiration (`exp`) và `nbf` | Token đang trong khoảng thời gian hợp lệ? |
| Token type (`typ`/profile) | Đây có phải loại access token được endpoint chấp nhận? |
| Scope | Có quyền `inventory:reserve` hoặc quyền tương đương? |
| Subject (`sub`) | User được đại diện có được phép thực hiện thao tác trên đối tượng cụ thể? |
| Actor (`act`) | Orders service có được phép thực hiện hành động thay mặt user theo policy không? |
| Sender constraint (`cnf`) | Request có cung cấp proof-of-possession nếu token bị ràng buộc khóa? |

Audience phải được kiểm tra cho mọi request. Token dành cho Orders API không trở thành token dành cho Inventory API chỉ vì cùng issuer ký hoặc vì hai service nằm trong một private network.

Sau khi xác minh token, Inventory API vẫn phải thực hiện authorization theo tài nguyên cụ thể. Ví dụ, `inventory:reserve` không có nghĩa user được giữ mọi sản phẩm trong mọi kho.

## 10. Delegation chain qua nhiều dịch vụ

Trong hệ thống nhiều hop, một service có thể nhận token từ service trước, rồi exchange sang token dành cho service tiếp theo.

Ví dụ:

~~~text
Client -> Orders -> Inventory -> Warehouse
~~~

- Client nhận token cho Orders.
- Orders exchange sang token cho Inventory.
- Inventory tiếp tục exchange sang token cho Warehouse nếu cần user context và policy cho phép.
- Mỗi token mới có audience phù hợp với resource server tiếp theo.

RFC 8693 định nghĩa claim `act` để thể hiện actor hiện tại và cho phép lồng `act` để lưu lịch sử delegation.

Ví dụ token dành cho Warehouse:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-482",
  "aud": "https://warehouse.example.test",
  "scope": "warehouse:pick",
  "act": {
    "sub": "inventory-service",
    "act": {
      "sub": "orders-service"
    }
  }
}
~~~

Trong ví dụ:

- Actor ngoài cùng là Inventory service, tức actor hiện tại.
- Actor lồng bên trong là Orders service, một actor trước đó trong chuỗi.
- Subject vẫn là user-482.

Theo RFC 8693 §4.1, khi áp dụng access control, consumer chỉ xem xét top-level claims và actor hiện tại trong `act`; các actor lồng trước đó mang tính thông tin lịch sử, không dùng thay thế actor hiện tại trong quyết định authorization.

Không tạo delegation chain vô hạn. Hệ thống nên giới hạn số hop, thời hạn token, scope và tập service được phép exchange. Nếu chuỗi quá dài hoặc actor không được tin cậy, authorization server phải từ chối exchange.

## 11. Token exchange khác refresh token và client credentials

Ba cơ chế có mục đích khác nhau:

| Cơ chế | Mục đích | Subject/user context |
|---|---|---|
| Refresh token | Xin access token mới trong cùng authorization grant/session theo policy | Thường duy trì ngữ cảnh user/client đã cấp |
| Token exchange | Chuyển một security token sang token phù hợp với target resource, actor hoặc trust context khác | Có thể giữ subject và thể hiện actor/delegation |
| Client credentials | Client lấy access token để hành động với tư cách chính client | Không đại diện user trừ khi có cơ chế delegation riêng |

Token exchange không phải refresh token rotation. Việc exchange subject token không mặc nhiên làm subject token cũ mất hiệu lực; RFC 8693 nêu rằng token exchange không ảnh hưởng hiệu lực token đầu vào trừ khi loại token hoặc policy có quy tắc one-time-use riêng.

RFC 8693 cũng nêu refresh token thường không được cấp khi đổi một temporary credential sang credential tạm thời khác cho context mới. Nếu deployment cấp refresh token từ token exchange, điều kiện phải được mô tả rõ và kiểm soát chặt.

### 11.1. Không dùng ID Token làm access token

ID Token được phát hành để client nhận thông tin xác thực người dùng trong OpenID Connect. Nó không mặc nhiên là access token dành cho resource server.

Nếu service cần gọi API, hãy dùng access token đúng audience/resource. Không gửi ID Token đến Inventory API rồi mong API coi nó là quyền truy cập.

## 12. Bảo vệ token trong quá trình exchange và forwarding

Token exchange làm phát sinh một request mới chứa subject token và có thể chứa actor token. Đây là dữ liệu nhạy cảm.

- Chỉ gọi token endpoint qua TLS.
- Xác thực client exchange bằng cơ chế mạnh phù hợp, chẳng hạn private key JWT hoặc mTLS theo policy.
- Không ghi request body token exchange, `subject_token`, `actor_token` hoặc client secret vào log/APM.
- Không đưa token vào query string.
- Chỉ gửi subject/actor token đến authorization server được tin cậy.
- Giới hạn service nào có quyền gọi token exchange và resource nào service đó được yêu cầu.
- Cache token mới theo issuer, audience, scope, actor và sender constraint; không dùng cache key chỉ theo subject.
- Không chia sẻ token dành cho Inventory API sang Billing API.
- Không lưu token mới lâu hơn cần thiết và không trả token downstream cho client ban đầu nếu không có lý do.

Nếu token exchange thất bại do `invalid_target`, không tự động retry với audience rộng hơn. Nếu subject token hoặc actor token không hợp lệ, không bỏ actor validation để exchange lại.

## 13. Mã giả: chọn forwarding hoặc exchange

Mã giả sau mô tả quyết định ở service trung gian. Các hàm là biểu diễn khái niệm, không phải API của một thư viện cụ thể.

~~~text
function obtain_downstream_credential(inbound_token, target, action, policy):
    claims = validate_inbound_token(inbound_token, policy.inbound_profile)

    require(target in policy.allowed_downstream_resources)

    if (
        target in validated_audiences(claims.aud)
        and policy.allows_forwarding
        and scope_allows(claims.scope, target, action)
        and sender_constraint_can_be_satisfied(claims.cnf, target)
        and policy.trust_contract_allows_original_issuer
    ):
        return inbound_token

    actor_identity = authenticate_this_service(policy.service_identity)

    exchanged = token_exchange(
        subject_token = inbound_token,
        subject_token_type = policy.subject_token_type,
        actor_token = actor_identity.token,
        actor_token_type = actor_identity.token_type,
        audience = target.logical_audience,
        resource = target.resource_uri,
        scope = minimum_scope_for(target, action),
        requested_token_type = policy.downstream_token_type
    )

    downstream_claims = validate_issued_token(
        exchanged.access_token,
        expected_issuer = policy.exchange_issuer,
        expected_audience = target.audience,
        required_scope = minimum_scope_for(target, action)
    )

    return exchanged.access_token
~~~

Trong triển khai thực tế:

- Không lấy target từ URL tùy ý do caller gửi; dùng registry/configuration của service.
- `validated_audiences()` chỉ đọc từ token đã được xác minh.
- Việc forwarding phải xét sender constraint, actor semantics và contract, không chỉ so sánh chuỗi `aud`.
- Authorization server phải tự xác minh lại subject/actor token và quyết định scope/resource được cấp.
- Nếu service không có user context, dùng workload/client credential thay vì tạo `subject_token` giả.
- Không tự sửa claims của token gốc để biến nó thành token dành cho downstream.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Forward token có audience của service hiện tại đến service khác. | Downstream phải từ chối; nếu bỏ kiểm tra aud sẽ phá ranh giới resource. | Exchange token dành riêng cho downstream. |
| Thêm mọi service vào `aud` để tránh exchange. | Một token có thể bị replay ở nhiều resource server. | Audience cụ thể hoặc tập nhỏ theo RFC 9700. |
| Giữ toàn bộ scope của token gốc khi exchange. | Token mới vẫn có quyền vượt nhu cầu service đích. | Yêu cầu scope tối thiểu và để AS áp dụng policy. |
| Tin `audience`/`resource` do caller bên ngoài tự cung cấp. | Service có thể bị lợi dụng để xin token cho resource khác. | Dùng mapping resource allowlist và policy của AS. |
| Không xác thực client tại token endpoint. | Người có subject token bị lộ có thể thử đổi nó thành token khác. | Client authentication và kiểm tra quyền exchange. |
| Bỏ qua actor identity. | Khó phân biệt hành động của user với hành động của service thay mặt user. | Dùng delegation semantics và `act` khi cần. |
| Nhầm delegation với impersonation. | Audit và policy có thể gán sai chủ thể thực hiện. | Chọn semantics rõ ràng và ghi nhận actor. |
| Forward sender-constrained token mà không có proof phù hợp. | Downstream không thể xác minh sender binding hoặc service cố tình bỏ qua nó. | Exchange token có sender constraint phù hợp với actor/đích. |
| Dùng ID Token để gọi API. | Nhầm mục đích token và có thể chấp nhận token sai audience/type. | Dùng access token dành cho resource server. |
| Nghĩ token exchange tự thu hẹp scope. | AS có thể phát hành token quá quyền nếu policy sai. | Kiểm tra scope/actor/resource tại AS và downstream. |
| Exchange qua từng hop không giới hạn. | Tăng latency, dependency và delegation chain phức tạp. | Giới hạn hop, cache đúng ngữ cảnh và thiết kế service boundary. |
| Log subject_token hoặc actor_token ở token endpoint. | Rò rỉ credential gốc và credential của service. | Redact body, header và trace attributes. |
| Dùng một token cache key chỉ theo user. | Token của resource/actor khác nhau có thể bị dùng nhầm. | Cache theo issuer, audience, scope, actor, sender binding và thời hạn. |

## 15. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
|---|---|
| Token gốc có `aud` đúng dịch vụ đích, scope đủ hẹp và forwarding được policy cho phép. | Có thể chuyển tiếp token gốc. |
| Token gốc chỉ có audience của service hiện tại. | Downstream từ chối token; service trung gian exchange token mới. |
| Token gốc có nhiều audience ngoài tập cho phép. | Từ chối theo profile hoặc policy; không coi nhiều audience là quyền mặc định. |
| Token exchange yêu cầu audience không được đăng ký. | Authorization server từ chối, thường dùng `invalid_target` theo RFC 8693. |
| Client exchange không được xác thực hoặc không có quyền delegation. | Từ chối exchange. |
| Subject token hết hạn hoặc sai issuer. | Authorization server từ chối. |
| Actor token sai chữ ký hoặc không được tin cậy. | Authorization server từ chối. |
| Actor hợp lệ nhưng không được phép hành động thay mặt subject. | Từ chối delegation. |
| Scope yêu cầu rộng hơn quyền subject hoặc policy cho phép. | Không cấp scope vượt quyền; từ chối nếu request không thể đáp ứng. |
| Token mới có `aud` không phải dịch vụ đích. | Downstream từ chối. |
| Token mới có scope không đủ cho hành động. | Downstream từ chối authorization. |
| Token exchange trả opaque access token. | Client sử dụng theo hợp đồng; không giả định mọi access token là JWT. |
| Token là ID Token thay vì access token. | Resource server từ chối theo token profile. |
| Token bị ràng buộc mTLS/DPoP nhưng request thiếu proof. | Từ chối. |
| Dịch vụ B exchange tiếp sang C. | Token mới dành cho C; actor/delegation chain được thể hiện và kiểm tra theo policy. |
| Token exchange request body bị logger capture. | Test redaction phát hiện và ngăn lưu subject/actor token. |
| Token cache có cùng subject nhưng khác audience hoặc actor. | Không dùng nhầm token giữa các resource/actor. |
| Authorization server không khả dụng. | Service xử lý theo availability policy; không fallback bằng cách forward token sai audience. |

## 16. Checklist thiết kế ranh giới dịch vụ

- [ ] Đã xác định rõ service nào là client, subject và resource server ở từng hop.
- [ ] Mỗi resource server xác minh `aud` của chính nó trên mọi request.
- [ ] Token gốc chỉ được forward khi audience, scope, trust contract và sender constraint cho phép.
- [ ] Không sửa claims hoặc chữ ký của token gốc để đổi audience.
- [ ] Đã xác định khi nào cần RFC 8693 Token Exchange.
- [ ] Authorization server xác thực client, subject token và actor token nếu có.
- [ ] `audience`/`resource` được chọn từ registry hoặc allowlist tin cậy.
- [ ] Scope token mới là quyền tối thiểu cho dịch vụ đích.
- [ ] Token mới có thời hạn phù hợp và loại token đúng profile.
- [ ] Delegation và impersonation có semantics rõ ràng.
- [ ] `act` được sử dụng khi cần thể hiện actor và được downstream kiểm tra theo policy.
- [ ] Không dùng ID Token làm access token.
- [ ] Token exchange body, Authorization header và cache được bảo vệ khỏi log.
- [ ] Cache key phân biệt issuer, audience, scope, actor và sender binding.
- [ ] Có test cho sai audience, scope quá rộng, actor không hợp lệ, token reuse và sender constraint.
- [ ] Có policy rõ ràng khi authorization server/token endpoint không khả dụng.

## 17. Câu hỏi tự kiểm tra

1. Token forwarding và token exchange khác nhau ở những thuộc tính nào?
2. Vì sao Orders API không được gửi token chỉ dành cho Orders sang Inventory API?
3. Khi nào forwarding token gốc có thể được chấp nhận?
4. Vì sao một token có nhiều audience có thể làm tăng blast radius?
5. `subject_token` và `actor_token` biểu diễn hai vai trò nào?
6. `audience`, `resource` và `scope` khác nhau như thế nào?
7. Token exchange có tự động thu hẹp quyền của token mới không?
8. Delegation khác impersonation ở điểm nào?
9. Claim `act` giúp downstream nhận biết điều gì?
10. Vì sao client authentication ở token endpoint quan trọng?
11. Token exchange khác refresh token và client credentials như thế nào?
12. Vì sao ID Token không nên được dùng như access token?
13. Downstream cần xác minh những claim và proof nào trước khi xử lý request?
14. Nếu token gốc bị ràng buộc với DPoP key của client ban đầu, service trung gian cần xử lý thế nào?

## 18. Tài liệu tham khảo

- [RFC 8693 – OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): giao thức exchange, `subject_token`, `actor_token`, `audience`, `resource`, `scope`, delegation, impersonation, `act` và `may_act` (§1–§5).
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): giới hạn privilege, audience restriction, sender-constrained token và chống replay (§2.2–§2.3, §4.9–§4.10).
- [RFC 8707 – Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html): tham số `resource` để chỉ rõ protected resource và giới hạn audience.
- [RFC 9068 – JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): profile JWT access token và kiểm tra token tại resource server.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): cách gửi bearer access token và rủi ro sử dụng token ngoài resource dự kiến.
- [RFC 9449 – OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): sender-constrained token và proof-of-possession bằng khóa của client.
