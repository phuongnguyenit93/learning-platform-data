# Tách danh tính người dùng khỏi danh tính dịch vụ

## 1. Vì sao phải tách hai loại danh tính?

Trong hệ thống có nhiều API và dịch vụ, một request thường đi qua nhiều thành phần. Ví dụ, người dùng Alice gọi Orders API; Orders API cần gọi Inventory API để kiểm tra tồn kho rồi gọi Payments API để thanh toán. Khi request đi qua các ranh giới dịch vụ, hệ thống phải trả lời hai câu hỏi riêng:

- **Ai là người dùng hoặc chủ thể mà hành động đang đại diện?**
- **Dịch vụ hoặc workload nào đang thực hiện request tới dịch vụ tiếp theo?**

Hai danh tính này liên quan với nhau nhưng không giống nhau. Alice là subject của hành động nghiệp vụ; Orders Service là service/client đang gọi Inventory hoặc Payments. Nếu gộp chúng thành một danh tính, hệ thống dễ gặp các vấn đề:

- Không phân biệt được quyền của người dùng với quyền vận hành của dịch vụ.
- Dịch vụ có quyền rộng vô tình dùng quyền của mình thay cho người dùng (confused deputy).
- Audit log chỉ ghi một tên, không biết ai yêu cầu và thành phần nào thực hiện.
- Token của một dịch vụ bị chuyển tiếp sang API không phải recipient dự kiến.
- Quyền của người dùng bị nâng lên theo quyền rộng của service account.
- Một service credential bị dùng để giả lập danh tính người dùng.

JWT có thể mang nhiều thông tin về subject, client, actor và recipient. Nhưng tên claim và ý nghĩa của chúng phải theo profile/giao thức. Không được mặc định rằng mọi JWT có cùng cách biểu diễn user và service.

Bài học này thuộc phạm vi bảo mật JWT/OAuth và ranh giới dịch vụ tổng quát, không phụ thuộc Java, Spring Security hay framework triển khai.

## 2. Phân biệt các khái niệm danh tính

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| User / resource owner | Người dùng nào đang được đại diện? | Alice |
| Subject (sub) | Token đang nói về chủ thể nào? | Alice trong token delegated; client trong một số token client credentials |
| OAuth client (client_id) | Phần mềm/client nào đã yêu cầu hoặc nhận token? | orders-service |
| Service/workload identity | Workload đang chạy và kết nối tới dịch vụ là workload nào? | spiffe://example.org/prod/orders hoặc danh tính workload được quản lý |
| Actor (act) | Thực thể nào đang hành động thay mặt subject trong delegation? | Orders Service |
| Audience (aud) | Token được phát hành cho resource server nào? | Payments API |
| Scope/permission | Token cho phép thực hiện hành động nào? | payments.write |

### User identity

User identity đại diện cho người dùng cuối hoặc principal mà hành động nghiệp vụ tác động tới. Nó thường được xác định bằng claim sub trong access token dành cho user. sub phải được hiểu trong namespace của issuer; cùng một chuỗi subject từ hai issuer khác nhau không nhất thiết là cùng một người.

User identity không tự cho biết dịch vụ nào đang gọi API. Nếu một request đi qua Orders Service, resource server có thể cần biết cả Alice và Orders Service.

### OAuth client identity

client_id nhận diện OAuth client đã được đăng ký với Authorization Server. Trong hệ thống service-to-service, OAuth client thường tương ứng với một ứng dụng hoặc workload logic như orders-service.

Tuy nhiên, client_id không nhất thiết nhận diện một process, container hoặc instance duy nhất. Nhiều replica của cùng một dịch vụ có thể dùng chung client registration. Nếu cần nhận diện workload cụ thể, có thể dùng cơ chế workload identity hoặc chứng thư riêng theo kiến trúc.

### Service/workload identity

Service identity đại diện cho workload đang chạy, ví dụ một service trong môi trường production. Danh tính này có thể được xác thực bằng:

- OAuth client authentication, chẳng hạn private_key_jwt hoặc client certificate.
- Mutual TLS (mTLS) với chứng thư client được cấp cho workload.
- Workload identity do nền tảng hạ tầng cấp và xác minh.
- Một cơ chế service account được quản trị tập trung.

Service identity trả lời "workload nào đang kết nối?". Nó không tự chứng minh rằng người dùng cuối có quyền thực hiện thao tác đang yêu cầu.

### Actor identity

Trong mô hình delegation, actor là thực thể thực hiện hành động thay mặt subject. RFC 8693 định nghĩa claim act để biểu diễn actor trong token được phát hành qua Token Exchange. Actor có thể là một dịch vụ hoặc một client khác.

Không phải mọi token đều cần claim act. Nếu service gọi API bằng quyền của chính nó, không có user delegation thì token có thể chỉ đại diện cho client/service theo profile client credentials.

## 3. sub, client_id, act và aud không thay thế nhau

Các claim thường xuất hiện trong access token có ngữ nghĩa khác nhau:

| Claim | Ý nghĩa thường dùng | Không nên suy diễn |
| --- | --- | --- |
| sub | Subject của token theo issuer/profile | Không luôn luôn là user cuối |
| client_id | OAuth client đã yêu cầu token | Không nhất thiết là một instance duy nhất |
| act | Actor đang hành động thay mặt subject theo RFC 8693 | Không phải bằng chứng tự thân rằng actor được phép |
| aud | Resource server hoặc audience được phép nhận token | Không biểu diễn người dùng hay caller |
| scope | Quyền được cấp cho token theo profile | Không tự chứng minh user/actor có quyền nghiệp vụ |
| iss | Issuer phát hành token | Không phải subject hoặc client |
| azp | Authorized party trong một số ngữ cảnh OpenID Connect, đặc biệt ID Token | Không phải claim service identity phổ quát cho mọi access token |

### sub không phải lúc nào cũng là user

Với JWT access token theo RFC 9068:

- sub xác định subject của token.
- Với token được cấp bằng client credentials grant, sub phải là client_id của client theo profile này.
- Với luồng đại diện người dùng, sub thường là định danh người dùng.

Do đó, resource server không được chỉ nhìn thấy sub rồi mặc định đó là user. Nó phải biết token profile/grant context hoặc áp dụng quy ước issuer đã công bố.

### Ví dụ token delegated

Một access token có thể biểu diễn Alice là subject, Orders Service là client và actor:

~~~json
{
  "iss": "https://identity.example",
  "sub": "alice",
  "client_id": "orders-service",
  "aud": "https://payments.example/",
  "scope": "payments.write",
  "act": {
    "sub": "orders-service"
  },
  "iat": 1893450000,
  "exp": 1893450300
}
~~~

Đây là ví dụ profile JWT access token có delegation. Cấu trúc thực tế phụ thuộc Authorization Server và profile. Resource server phải xác minh chữ ký, issuer, audience, thời hạn và quyền trước khi tin bất kỳ claim nào.

### Ví dụ token client credentials

Khi Orders Service gọi Inventory API bằng quyền của chính dịch vụ, token có thể biểu diễn client làm subject:

~~~json
{
  "iss": "https://identity.example",
  "sub": "orders-service",
  "client_id": "orders-service",
  "aud": "https://inventory.example/",
  "scope": "inventory.read",
  "iat": 1893450000,
  "exp": 1893450300
}
~~~

Token này không khẳng định Alice đang thực hiện request. Nếu Inventory API cần biết user nào khởi tạo thao tác, một service-only token như trên không đủ; cần một mô hình delegation được xác thực.

## 4. Hai mô hình gọi dịch vụ: service acts as itself và on-behalf-of

### Dịch vụ hành động bằng quyền của chính nó

Client Credentials grant phù hợp khi một service cần truy cập resource bằng quyền được cấp cho chính OAuth client/service đó, không đại diện cho user cụ thể.

Ví dụ:

- Inventory Service định kỳ đồng bộ dữ liệu kho.
- Billing Service đọc cấu hình thanh toán của hệ thống.
- Monitoring Service truy vấn metrics mà nó được phép xem.

Trong mô hình này:

- Service phải xác thực với Authorization Server.
- AS kiểm tra client, grant và quyền đã đăng ký.
- Token mới có audience đúng resource server và scope tối thiểu.
- Resource server xác minh token như machine-to-machine credential.
- Không tự tạo sub giả đại diện cho một người dùng.

### Dịch vụ hành động thay mặt người dùng

Nếu Alice yêu cầu xem hoặc sửa dữ liệu của chính mình qua Orders Service, downstream API có thể cần biết Alice là subject và Orders Service là actor.

Mô hình on-behalf-of/delegation cần:

- Token đầu vào đã xác thực đại diện cho Alice.
- Orders Service được xác thực như client/actor.
- AS kiểm tra Orders Service có được phép hành động thay mặt Alice hay không.
- Token đầu ra giới hạn theo audience, scope và thời hạn cần thiết.
- Downstream resource server kiểm tra cả subject lẫn actor nếu nghiệp vụ yêu cầu.

Không phải mọi hệ thống đều triển khai cùng một OAuth extension cho on-behalf-of. RFC 8693 Token Exchange cung cấp cơ chế chuẩn hóa với subject_token và actor tùy chọn; các profile khác có thể định nghĩa quy trình tương đương.

### So sánh

| Tiêu chí | Client Credentials / service-only | Delegated / on-behalf-of |
| --- | --- | --- |
| Subject | Client/service theo token profile | User hoặc principal được đại diện |
| Actor | Không nhất thiết có actor riêng; client chính là principal của token | Service/client đang hành động thay mặt subject |
| Nguồn quyền | Quyền được cấp cho service/client | Quyền của subject kết hợp quyền và phạm vi delegation của actor |
| Dùng khi | Tác vụ hệ thống không gắn với user cụ thể | Request có ngữ cảnh user cần giữ qua ranh giới dịch vụ |
| Rủi ro chính | Service account có quyền quá rộng | Actor vượt quyền delegation hoặc nhầm subject/actor |

## 5. Vì sao không nên gộp user và service thành một tài khoản?

Một cách triển khai sai thường gặp là tạo một user giả như system-user rồi gán mọi request của service vào user đó. Cách này làm mất thông tin ai đã yêu cầu hành động và dễ tạo quyền quá rộng.

Ví dụ, Orders Service có quyền gọi Payments API để tạo giao dịch. Nếu mọi request được gán sub=system-user và có role administrator, Payments API không thể phân biệt:

- Alice đang thanh toán đơn hàng của cô ấy.
- Bob đang thanh toán đơn hàng của Bob.
- Một tác vụ nền do Orders Service khởi tạo.
- Một request bị khai thác để sử dụng quyền service ngoài ý định.

Hậu quả:

- Authorization khó kiểm tra ownership theo user.
- Audit trail không thể quy trách nhiệm đúng.
- Service credential trở thành con đường vượt qua quyền user.
- Quyền bị lan truyền giữa các API.

Thay vì gộp danh tính, hãy giữ riêng subject và caller/actor, rồi định nghĩa rõ quan hệ ủy quyền giữa chúng.

## 6. Token propagation qua nhiều service

Khi một request đi qua nhiều dịch vụ, không nên mặc định chuyển tiếp cùng một access token tới mọi downstream API.

~~~mermaid
flowchart LR
    U["Alice / Browser"] -->|"Token aud=orders"| O["Orders API"]
    O -->|"Token aud=inventory"| I["Inventory API"]
    O -->|"Token aud=payments"| P["Payments API"]
~~~

Orders API có thể nhận token dành cho chính nó. Khi cần gọi Inventory hoặc Payments, nó cần credential phù hợp với resource đích:

- Nếu hành động hoàn toàn thuộc quyền service, dùng client credentials token có audience và scope phù hợp.
- Nếu hành động phải giữ ngữ cảnh Alice, dùng token exchange/delegation để phát hành token cho downstream với subject Alice và actor Orders Service.
- Nếu downstream chỉ cần một phần quyền, downscope token theo nguyên tắc quyền tối thiểu.
- Không forward token có audience chỉ dành cho Orders API sang Payments API.

Token exchange giúp thay đổi audience và quyền theo ranh giới dịch vụ mà vẫn giữ được thông tin subject/actor cần thiết. AS phải xác thực client và subject token trước khi phát hành token mới.

### Không truyền toàn bộ claims một cách mù quáng

Khi tạo token downstream, không sao chép mọi claim từ token đầu vào. Cần chọn các claim thật sự cần thiết:

- Giữ subject nếu downstream cần quyết định theo user.
- Giữ actor/delegation context nếu downstream cần kiểm tra dịch vụ đang hành động.
- Đặt audience đúng downstream resource.
- Cấp scope vừa đủ cho thao tác.
- Giữ các claim về tenant, transaction hoặc authorization context chỉ khi chúng có định nghĩa và nguồn tin cậy rõ ràng.
- Không chuyển tiếp thông tin xác thực nhạy cảm hoặc claim không liên quan.

## 7. Xác thực service identity

Service identity cần được xác thực độc lập với user identity. Một số cơ chế phổ biến:

### OAuth client authentication

Service có thể xác thực với token endpoint bằng phương thức client authentication được AS hỗ trợ và đăng ký, ví dụ:

- Client secret qua kênh TLS trong trường hợp phù hợp; secret phải được quản lý và xoay vòng an toàn.
- private_key_jwt, trong đó client ký assertion bằng private key đã đăng ký.
- mTLS client authentication bằng chứng thư client.

Không dùng một client secret dùng chung cho mọi dịch vụ nếu có thể cấp credential riêng theo service. Credential cần có vòng đời, quyền và khả năng thu hồi riêng.

### Mutual TLS và workload identity

mTLS cho phép hai bên xác thực chứng thư trong quá trình thiết lập TLS. Chứng thư client có thể gắn với danh tính service/workload. Cần kiểm tra chain, danh tính, thời hạn, key usage và policy cấp phát chứng thư.

Trong hạ tầng có workload identity, mỗi workload có thể nhận một danh tính riêng từ control plane hoặc identity provider. Resource server hoặc gateway xác minh danh tính đó qua trust domain và policy. Không coi tên pod, hostname hoặc header do caller tự gửi là bằng chứng workload identity.

### Xác thực ở transport không thay thế authorization

mTLS thành công chứng minh peer có quyền sử dụng chứng thư được tin cậy trong kết nối. Nó không tự chứng minh:

- User có quyền xem dữ liệu.
- Service được phép gọi mọi endpoint.
- Request thuộc đúng tenant.
- Scope nghiệp vụ đủ cho thao tác.

Resource server vẫn phải áp dụng authorization dựa trên token claims và policy.

## 8. Quy tắc authorization kết hợp user và service

Trong mô hình delegation, một thao tác chỉ nên được chấp nhận khi các điều kiện liên quan đều đạt:

1. Token được phát hành bởi issuer tin cậy và chữ ký hợp lệ.
2. Audience khớp resource server.
3. Subject là user/principal hợp lệ và còn hoạt động.
4. Actor/client là service được phép gọi API.
5. Actor được phép hành động thay mặt subject cho loại thao tác này.
6. Scope của token bao gồm quyền cần thiết.
7. User có quyền nghiệp vụ trên resource cụ thể (ownership/tenant/relationship).
8. Service không vượt quá phạm vi delegation được cấp.

Ví dụ:

~~~text
allow =
    token.signature_valid
    AND token.iss == trusted_issuer
    AND resource_api in token.aud
    AND token.sub == resource.owner_user_id
    AND token.act.sub == "orders-service"
    AND "payments.write" in token.scope
    AND orders_service_is_allowed_to_delegate
    AND transaction_is_in_user_context
~~~

Đây là policy minh họa. Không phải mọi API đều cần kiểm tra ownership theo cùng cách; nhưng quyền user, quyền service và quyền trên resource cần được phân biệt.

### Tránh confused deputy

Service có quyền gọi downstream không được tự động dùng quyền đó cho mọi request của user. Trước khi gọi downstream, service phải xác định:

- Request đến từ user nào?
- User có quyền thực hiện hành động ở API nguồn không?
- Service có quyền thực hiện hành động downstream không?
- User có được ủy quyền cho service thực hiện hành động downstream không?
- Token gửi downstream có audience/scope/subject/actor đúng không?

Nếu chỉ service có quyền mà user không có quyền, không được dùng service credential để vượt qua giới hạn user, trừ khi đây là một tác vụ hệ thống độc lập đã được policy cho phép.

## 9. Thiết kế token và claim theo từng luồng

### Token service-only

~~~json
{
  "iss": "https://identity.example",
  "sub": "inventory-sync-service",
  "client_id": "inventory-sync-service",
  "aud": "https://inventory.example/",
  "scope": "inventory.sync",
  "iat": 1893450000,
  "exp": 1893450300
}
~~~

Token này đại diện cho service/client theo profile. Không gắn sub thành Alice nếu không có user delegation thực sự.

### Token delegated

~~~json
{
  "iss": "https://identity.example",
  "sub": "alice",
  "client_id": "orders-service",
  "act": {
    "sub": "orders-service"
  },
  "aud": "https://payments.example/",
  "scope": "payments.write",
  "iat": 1893450000,
  "exp": 1893450300
}
~~~

Token này thể hiện subject Alice và actor Orders Service theo profile hỗ trợ delegation. Resource server phải xác minh claim và policy trước khi xử lý.

### Không nhầm azp với act

Trong OpenID Connect, azp là authorized party claim được sử dụng trong một số ngữ cảnh ID Token để nhận diện bên được token phát hành/được phép sử dụng token. act trong RFC 8693 biểu diễn actor trong delegation. Chúng có ngữ nghĩa và phạm vi khác nhau; không thay thế cho nhau.

Với JWT access token, hãy dùng claim và profile được AS công bố (ví dụ client_id theo RFC 9068 và act khi dùng RFC 8693). Không tự suy ra service identity từ azp nếu access-token profile không quy định.

## 10. Audit và truy vết qua ranh giới dịch vụ

Audit log cần giữ được cả user và service identity để trả lời:

- Ai khởi tạo hành động?
- Dịch vụ nào đã nhận và xử lý request?
- Dịch vụ nào gọi downstream?
- Token được phát hành cho audience nào?
- Quyền/scope nào được sử dụng?
- Hành động được thực hiện thay mặt subject hay bằng quyền riêng của service?

Một log event có thể chứa:

~~~json
{
  "event": "payment.capture",
  "subject_id": "alice",
  "actor_client_id": "orders-service",
  "workload_id": "spiffe://example.org/prod/orders",
  "resource": "payments-api",
  "audience": "https://payments.example/",
  "scope": ["payments.write"],
  "correlation_id": "req-81a2",
  "decision": "allow"
}
~~~

Đây là cấu trúc audit minh họa, không phải claim JWT chuẩn. Không ghi raw access token, refresh token, client secret hoặc private key vào log. Có thể ghi token ID/fingerprint an toàn theo chính sách để điều tra mà không làm lộ credential.

Correlation ID giúp nối request qua nhiều service nhưng không phải bằng chứng xác thực. Không tin correlation ID do caller tùy ý gửi nếu nó được dùng làm định danh bảo mật.

## 11. Ranh giới tin cậy và các quy tắc vận hành

### Mỗi service có identity và quyền riêng

- Cấp client registration/credential riêng theo service hoặc workload boundary.
- Chỉ cấp scope cần thiết cho công việc của service.
- Tách credential production, staging và development.
- Xoay vòng và thu hồi credential độc lập.
- Không chia sẻ private key hoặc client secret giữa các service không cùng trust boundary.

### Mỗi API xác minh recipient và caller

- Xác minh issuer và chữ ký hoặc introspection.
- Kiểm tra audience đúng API.
- Xác định token thuộc service-only hay delegated profile.
- Kiểm tra subject, client/actor và scope theo profile.
- Không tin các header như X-User, X-Service-Name hoặc X-Roles do request bên ngoài tự gửi, trừ khi chúng được gateway tin cậy xóa/ghi đè và truyền qua một kênh đã xác thực.

### Gateway không thay thế kiểm tra tại service

API gateway có thể xác thực token ở lớp biên, nhưng downstream service vẫn cần hiểu trust boundary của request. Nếu service có thể được gọi trực tiếp hoặc qua nhiều đường mạng, cần xác minh token hoặc nhận một assertion nội bộ được bảo vệ và ràng buộc đúng nguồn.

Không mặc định rằng request đến từ mạng nội bộ là đáng tin. Mạng nội bộ có thể có workload bị xâm nhập, misconfiguration hoặc đường gọi ngoài dự kiến.

## 12. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng một service account chung cho nhiều dịch vụ | Khó thu hồi riêng, audit không rõ và quyền bị chia sẻ | Identity/credential riêng theo service boundary |
| Gán mọi request vào một user giả như system-user | Mất subject thật và khó kiểm tra ownership | Giữ subject user riêng; biểu diễn actor/service riêng |
| Coi sub luôn là user | Hiểu sai token client credentials | Diễn giải theo issuer và token profile; RFC 9068 quy định sub là client_id trong client credentials |
| Coi client_id là workload instance duy nhất | Không phân biệt được nhiều replica hoặc môi trường | Dùng workload identity riêng nếu cần nhận diện instance |
| Dùng service credential toàn quyền cho mọi request user | Confused deputy và privilege escalation | Kết hợp quyền user, actor delegation và scope downstream |
| Forward nguyên user token tới mọi API | Sai audience, lộ token rộng và vi phạm ranh giới | Token exchange hoặc credential đúng recipient |
| Dùng client credentials token rồi tự thêm user claim | Tạo danh tính user không có bằng chứng | Dùng delegated flow được AS xác thực |
| Chỉ kiểm tra scope, bỏ qua subject/actor | Service có thể dùng scope thay user ngoài ý muốn | Kiểm tra cả principal, actor và quyền trên resource |
| Tin header X-User/X-Service từ caller | Caller có thể giả mạo danh tính | Xác thực token/workload; chỉ tin metadata từ hop đã xác thực |
| Coi mTLS thành công là đủ authorization | Service hợp lệ có thể gọi API ngoài quyền | Kiểm tra audience, scope và policy nghiệp vụ |
| Nhầm azp với act | Nhầm authorized party OIDC với actor delegation | Dùng đúng claim theo profile |
| Không log riêng subject và actor | Không truy vết được ai yêu cầu và service nào thực hiện | Audit cả user, client/actor, workload và resource |
| Dùng access token sai audience vì "cùng hệ thống" | Token bị chấp nhận ngoài mục tiêu phát hành | Audience validation chính xác tại từng resource server |

## 13. Bộ ca kiểm thử

Giả sử Alice gọi Orders API; Orders Service cần gọi Payments API. AS hỗ trợ access token JWT theo RFC 9068 và delegation theo RFC 8693.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Service gọi Inventory bằng client credentials token đúng audience/scope | **Chấp nhận** nếu service policy cho phép |
| Client credentials token có sub=orders-service, API coi đó là Alice | **Từ chối**; token không đại diện user |
| Delegated token có sub=alice, client_id=orders-service, actor hợp lệ và audience Payments API | **Chấp nhận** nếu scope và policy nghiệp vụ đạt |
| Delegated token có actor là service không được phép | **Từ chối** |
| User Alice không có quyền trên order nhưng Orders Service có quyền service rộng | **Từ chối** theo user/resource policy |
| Token có chữ ký hợp lệ nhưng aud chỉ là Orders API gửi tới Payments API | **Từ chối** |
| Token có scope=payments.read dùng cho thao tác capture | **Từ chối** |
| Client tự gửi header X-User: admin để thay subject | **Bỏ qua/từ chối metadata không tin cậy** |
| Service credential của staging được dùng ở production | **Từ chối** theo trust boundary |
| mTLS certificate hợp lệ nhưng service không có scope yêu cầu | **Từ chối** |
| Token có azp nhưng không có actor claim theo profile delegation | Không suy diễn azp thành actor; xử lý theo profile |
| AS token exchange thành công nhưng cấp scope rộng hơn policy | **Không được phát hành**; test phát hiện lỗi authorization |
| Token delegated có subject và actor đúng nhưng sai tenant/resource ownership | **Từ chối** |
| Request đi qua gateway hợp lệ nhưng gọi trực tiếp downstream với token sai audience | Downstream **từ chối** |
| Audit event ghi cả subject, actor/client và resource | Có thể truy vết đúng luồng; không chứa raw token |

## 14. Ghi nhớ

- User identity và service identity trả lời hai câu hỏi khác nhau; không gộp chúng thành một user giả.
- sub là subject theo issuer/profile, không phải lúc nào cũng là user cuối. Với JWT access token theo RFC 9068, trong client credentials grant, sub là client_id.
- client_id nhận diện OAuth client; nó không nhất thiết nhận diện một workload instance duy nhất.
- Workload identity xác thực service đang kết nối; nó không tự cấp quyền nghiệp vụ cho user.
- act theo RFC 8693 biểu diễn actor trong delegation; azp của OpenID Connect có ngữ nghĩa khác.
- Client credentials phù hợp khi service hành động bằng quyền của chính nó; delegated/on-behalf-of phù hợp khi cần giữ subject và actor qua ranh giới dịch vụ.
- Mỗi token phải có audience đúng resource server và scope tối thiểu.
- Không forward token sai audience; dùng token exchange hoặc credential phù hợp cho downstream.
- Authorization cần kết hợp subject, actor/service, scope và quyền trên resource; chỉ có service permission không đồng nghĩa user được phép.
- mTLS/OAuth client authentication xác thực service; resource server vẫn phải kiểm tra authorization.
- Audit cần ghi riêng subject, actor/client, workload và resource nhưng không ghi raw credential.

### Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, mục 4.4](https://www.rfc-editor.org/rfc/rfc6749): Client Credentials Grant cho client truy cập bằng quyền của chính nó.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject token, actor token, delegation và claim act.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claim sub, client_id, audience và profile JWT access token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): xác thực client bằng mTLS và ràng buộc access token với certificate.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth, giới hạn token và bảo vệ credential.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): danh tính end-user, ID Token và claim azp.
