# Principal propagation

> **Chương:** Authorization boundary  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Truyền tải danh tính người dùng, service và ngữ cảnh ủy quyền qua nhiều thành phần, giữ đúng nguồn gốc, phạm vi quyền, tenant và khả năng kiểm toán.

## 1. Principal propagation là gì?

**Principal propagation (truyền tải principal)** là cách một hệ thống chuyển tiếp thông tin về chủ thể đã được xác thực và quyền hành động của họ qua các ranh giới dịch vụ. Khi request đi qua API gateway, backend, service nghiệp vụ và hệ thống dữ liệu, mỗi thành phần cần biết ai là chủ thể, service nào đang trực tiếp gọi, hành động được ủy quyền trong phạm vi nào và danh tính đó được xác minh ra sao.

Ví dụ, Alice đăng nhập vào cổng quản lý đơn hàng. Gateway xác thực access token của Alice rồi chuyển request tới Order Service. Order Service cần gọi Billing Service để tạo khoản thanh toán. Billing cần hiểu thao tác được thực hiện thay mặt Alice, đồng thời biết Order Service là service trực tiếp gọi. Nếu Billing chỉ nhìn thấy API key dùng chung của Order Service, nó có thể mất thông tin về người khởi tạo; nếu Order Service tự gửi header X-User: alice mà Billing tin ngay, attacker có thể giả mạo principal.

Principal propagation giải quyết câu hỏi: làm sao giữ đúng ngữ cảnh danh tính và ủy quyền khi request đi qua nhiều thành phần? Nó không có nghĩa là chuyển tiếp mật khẩu hoặc sao chép mọi credential của người dùng sang tất cả backend. Mỗi hop cần xác minh nguồn, audience, quyền và mục đích phù hợp.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt principal, subject, actor, client và service identity.
- Mô tả cách danh tính được truyền qua gateway, service-to-service và hàng đợi bất đồng bộ.
- Chọn giữa forwarding token, token exchange và identity assertion.
- Giữ ngữ nghĩa delegation và tránh nhầm với impersonation.
- Xác minh token theo issuer, audience, thời hạn, chữ ký và quyền.
- Ngăn giả mạo identity header, confused deputy và lỗi tenant isolation.
- Thiết kế authorization, audit, privacy và kiểm thử cho từng hop.

## 2. Principal, subject, actor và service identity

Hệ thống phân tán cần phân biệt người có quyền được yêu cầu thực hiện và thành phần trực tiếp gửi request.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Principal** | Danh tính dùng làm chủ thể trong quyết định bảo mật | Alice, service order-api, workload invoice-worker |
| **Subject** | Danh tính mà hành động hoặc quyền đang được xét áp dụng cho | Alice trong yêu cầu xem đơn hàng |
| **Actor** | Chủ thể hoặc thành phần trực tiếp thực hiện hành động ở một hop | Order Service gọi Billing thay mặt Alice |
| **Client** | Ứng dụng hoặc bên yêu cầu token/đăng nhập | Web app, mobile app, backend client |
| **Service identity** | Danh tính riêng của workload/service khi giao tiếp máy-với-máy | workload order-api trong môi trường production |
| **Delegator** | Chủ thể trao hoặc ủy quyền quyền hành động | Alice cho phép ứng dụng truy cập lịch |
| **Delegate** | Bên nhận quyền thực hiện trong phạm vi được ủy quyền | Ứng dụng lịch hoặc service được cấp quyền |

Một request có thể mang nhiều lớp danh tính. Trong ví dụ Alice tạo thanh toán, subject có thể là Alice, actor trực tiếp là Order Service, client khởi tạo là web application, còn Billing Service là resource server. Không gộp các lớp này thành một trường user mơ hồ.

### Vì sao cần giữ actor và subject?

Nếu Billing chỉ ghi “Alice tạo giao dịch”, audit không thể phân biệt Alice gọi trực tiếp hay Order Service tự động tạo giao dịch theo workflow. Nếu chỉ ghi “Order Service tạo giao dịch”, điều tra viên không biết hành động bắt nguồn từ yêu cầu của người dùng nào.

Một audit event hữu ích có thể lưu:

- Subject: người dùng hoặc workload mà hành động áp dụng.
- Actor: service hoặc người trực tiếp thực hiện hop hiện tại.
- Delegation context: quyền được trao, nguồn cấp và giới hạn.
- Client/request context: ứng dụng, session hoặc correlation ID.
- Resource, action, tenant và kết quả authorization.

## 3. Principal propagation trong kiến trúc nhiều service

Trong một hệ thống phân tán, danh tính có thể đi qua nhiều hop:

~~~mermaid
flowchart LR
    U["Alice / User"] --> C["Web or Mobile Client"]
    C --> G["API Gateway"]
    G --> O["Order Service"]
    O --> B["Billing Service"]
    O --> N["Notification Service"]
    B --> D["Payment Provider Adapter"]
    O --> Q["Message Queue"]
    Q --> W["Background Worker"]
    O -. "Context theo hop" .-> B
    Q -. "Context được bảo vệ" .-> W
~~~

Ở mỗi ranh giới, thành phần nhận phải xác định:

1. Ai đã xác thực request đến?
2. Service nào đang trực tiếp gọi?
3. Principal gốc có được giữ nguyên không?
4. Quyền nào được ủy quyền cho hop hiện tại?
5. Token/assertion có được phát hành cho đúng audience không?
6. Tenant và resource có khớp ngữ cảnh không?
7. Có thể kiểm toán nguồn gốc và chuỗi delegation không?

Không giả định mọi service có cùng mức tin cậy chỉ vì chúng nằm trong cùng VPC, cluster hoặc mạng nội bộ. Một service có thể bị compromise; credential nội bộ có thể bị đánh cắp; request có thể đến từ workload sai.

## 4. Các mô hình truyền tải principal

Không có một cơ chế duy nhất phù hợp mọi kiến trúc. Ba mô hình thường gặp là forwarding token, token exchange và identity assertion có bảo vệ.

### Forwarding access token

Gateway hoặc service chuyển tiếp access token ban đầu tới service kế tiếp. Mô hình này đơn giản khi token được phát hành cho đúng API hoặc một tập audience được thiết kế rõ ràng.

Giới hạn:

- Token có thể có audience không phù hợp với service nhận.
- Token có thể chứa quyền rộng hơn mức hop cần.
- Nhiều service cùng nhận một bearer token làm tăng phạm vi ảnh hưởng nếu một service bị compromise.
- Token có thể bị log, cache hoặc lộ qua lỗi xử lý.

Chỉ forwarding khi issuer, audience, scope và trust model cho phép. Không chuyển tiếp token chỉ vì nó đang có sẵn trong request.

### Token exchange / delegated token

Service dùng token đầu vào và danh tính service của chính nó để yêu cầu authorization server cấp token mới cho downstream service. Token mới có thể giới hạn audience, scope, lifetime và ngữ nghĩa delegation.

Ví dụ, Order Service nhận token dành cho orders-api, rồi đổi token theo chính sách để nhận token dành cho billing-api với quyền payment:create thay mặt Alice. Billing xác minh token mới, thấy subject Alice và actor Order Service, sau đó tự quyết định có cho phép tạo khoản thanh toán không.

OAuth Token Exchange (RFC 8693) là một mô hình chuẩn có thể dùng khi authorization server và các bên hỗ trợ. Cấu hình claim và semantics cụ thể phải tuân theo profile triển khai; không tự thêm claim tùy ý rồi mặc định resource server hiểu giống nhau.

### Identity assertion hoặc signed context

Gateway/identity service có thể phát hành assertion đã ký, chứa principal và thuộc tính cần thiết cho backend. Assertion phải có issuer, audience, thời hạn, chống replay và schema được các bên thống nhất. Nó không được là JSON do gateway gửi qua header mà service nhận tin mù quáng.

Signed context cần quản lý khóa, xoay vòng, thu hồi và phân quyền phát hành. Nếu có thể dùng token chuẩn đã được xác minh, nên tránh phát minh giao thức assertion riêng.

## 5. Forwarding token đúng cách

Nếu kiến trúc cho phép forwarding access token, cần kiểm tra:

- Token được phát hành bởi issuer được tin cậy.
- Token dành cho API/service nhận, hoặc profile cho phép nhiều audience rõ ràng.
- Scope/permission đủ cho hành động nhưng không rộng quá mức.
- Token chưa hết hạn và không nằm ngoài nbf nếu claim đó được sử dụng.
- Chữ ký được xác minh bằng thuật toán cho phép và key phù hợp.
- Client/service gọi có quyền chuyển tiếp token theo chính sách.
- Token không bị đưa vào URL, log, tracing tag hoặc message không bảo vệ.

### Không chuyển tiếp ID token như access token

ID token trong OpenID Connect được phát hành cho client để mô tả kết quả xác thực người dùng trong ngữ cảnh đăng nhập. Nó không mặc nhiên là credential để gọi API. Backend cần access token có audience và quyền phù hợp với resource server.

### Opaque token và introspection

Access token có thể là JWT tự chứa hoặc opaque token. Với opaque token, resource server thường cần introspection qua authorization server hoặc cơ chế kiểm tra trạng thái đã thỏa thuận. Không giả định token là JWT chỉ vì chuỗi có dấu chấm; cũng không giải mã JWT rồi tin claims trước khi xác minh chữ ký.

## 6. Token exchange và delegation

Token exchange giúp cấp token phù hợp cho downstream service thay vì gửi một token rộng qua mọi hop.

~~~mermaid
sequenceDiagram
    participant U as Alice
    participant G as API Gateway
    participant O as Order Service
    participant AS as Authorization Server
    participant B as Billing Service
    U->>G: Request + access token cho orders-api
    G->>G: Xác minh token đầu vào
    G->>O: Request + context đã xác minh
    O->>AS: Token exchange + service authentication
    AS->>AS: Kiểm tra subject, actor, audience và policy
    AS-->>O: Token giới hạn cho billing-api
    O->>B: Create payment + delegated token
    B->>B: Xác minh token và authorization
    B-->>O: Kết quả
    O-->>U: Kết quả nghiệp vụ
~~~

### Token downstream nên giới hạn

- **Audience:** chỉ service nhận dự kiến.
- **Scope/permissions:** chỉ hành động cần thiết.
- **Lifetime:** đủ ngắn cho công việc, có xét thời gian xử lý.
- **Subject:** principal mà hành động được thực hiện thay mặt.
- **Actor/delegation:** service hoặc client đang sử dụng quyền đó.
- **Tenant/resource context:** giới hạn đúng tổ chức và đối tượng.

Token exchange không tự động làm request an toàn. Authorization server phải xác minh caller được phép đổi token; resource server phải xác minh token mới; service phải tránh yêu cầu scope rộng chỉ để tiện triển khai.

### Delegation không phải impersonation

**Delegation** giữ lại việc hành động được thực hiện thay mặt subject, đồng thời ghi nhận delegate/actor. **Impersonation** thường khiến hệ thống xử lý request như thể actor chính là subject, có thể làm mất thông tin về bên thực hiện. Impersonation chỉ nên dùng trong tình huống được thiết kế, phê duyệt và audit rõ ràng.

Ví dụ, support agent mở hồ sơ khách hàng theo quyền hỗ trợ. Audit nên ghi agent là actor và khách hàng là subject/resource context. Không ghi mọi hành động như thể khách hàng tự thực hiện.

## 7. Service-to-service identity

Mỗi service cần có danh tính riêng để resource server biết caller trực tiếp là workload nào. Có thể dùng:

- OAuth client credentials hoặc workload identity.
- mTLS với chứng chỉ client do CA tin cậy cấp.
- SPIFFE/SPIRE hoặc cơ chế workload identity tương đương.
- Credential ngắn hạn do nền tảng cấp phát.

Không dùng một API key chung cho tất cả backend nếu có thể cấp danh tính riêng theo workload. Khi một service bị compromise, danh tính riêng và quyền tối thiểu giúp giới hạn phạm vi ảnh hưởng.

### Hai lớp xác thực trong một request

Một request delegated có thể cần chứng minh cả:

1. **Service identity:** Order Service là caller trực tiếp và được phép gọi Billing.
2. **User/delegated identity:** hành động đang được thực hiện thay mặt Alice trong phạm vi được ủy quyền.

Service authentication và user delegation giải quyết hai câu hỏi khác nhau. mTLS xác thực kết nối/workload theo trust model, nhưng không tự chứng minh Alice đã yêu cầu thanh toán. Ngược lại, user access token không nhất thiết chứng minh workload trực tiếp là service được phép gọi.

## 8. Identity headers và ranh giới tin cậy

Một số hệ thống dùng header như X-Authenticated-User, X-Principal, X-Tenant-ID hoặc X-Forwarded-Client-Cert để truyền ngữ cảnh. Header là dữ liệu do bên gửi cung cấp; bản thân tên header không tạo ra độ tin cậy.

### Rủi ro giả mạo header

Nếu API Gateway nhận request Internet có sẵn X-Authenticated-User: admin rồi chuyển nguyên header tới backend, attacker có thể tự khai danh tính. Backend sẽ tin sai nếu không xác minh nguồn.

### Quy tắc bảo vệ

1. Edge gateway xóa hoặc ghi đè mọi identity header do client gửi.
2. Chỉ gateway/service đã xác thực mới được tạo identity context.
3. Backend chỉ nhận request qua network path hoặc mTLS identity được phép.
4. Nếu dùng signed assertion, backend xác minh chữ ký, issuer, audience, expiry và nonce/context.
5. Không dùng header tự khai làm căn cứ duy nhất cho authorization.
6. Có quy tắc rõ cho proxy chain và header forwarding; không tin mọi hop.

### Ví dụ ranh giới

~~~text
Internet client
  X-Authenticated-User: administrator   <- không tin
        |
        v
Trusted API Gateway
  - remove incoming identity headers
  - validate access token
  - create trusted downstream context
        |
        v
Backend service
  - accept only authenticated gateway/service
  - validate delegated token or signed assertion
  - authorize the requested action
~~~

Ngay cả khi gateway đáng tin, backend vẫn cần kiểm tra token/assertion và quyền cho tài nguyên của nó. Không để gateway trở thành nơi duy nhất quyết định mọi authorization nếu backend có ngữ cảnh nghiệp vụ riêng.

## 9. Claims và ngữ cảnh cần giữ

Không phải service nào cũng cần toàn bộ profile người dùng. Principal context nên tối thiểu nhưng đủ để authorization và audit.

| Thành phần | Ý nghĩa | Lưu ý |
|---|---|---|
| iss | Issuer phát hành token/assertion | So khớp allowlist issuer |
| sub | Subject được token đại diện | Xác định theo namespace/issuer; không giả định là email |
| aud | Audience dự kiến | Resource server phải kiểm tra đúng audience |
| exp / nbf / iat | Thời hạn và thời điểm token | Xử lý clock skew theo policy giới hạn |
| scope / permissions | Quyền được cấp | Kiểm tra quyền cho action/resource cụ thể |
| client_id / azp | Client được cấp token hoặc bên được ủy quyền | Ngữ nghĩa phụ thuộc profile |
| act / actor context | Thông tin actor trong một số mô hình delegation | Chỉ dùng khi issuer/profile định nghĩa và xác minh |
| tenant_id | Phạm vi tenant | Phải gắn với principal và resource theo policy |
| jti / token ID | Định danh token | Có thể hỗ trợ audit hoặc chống replay theo thiết kế |
| acr / amr | Ngữ cảnh/method xác thực nếu được phát hành | Không suy diễn mức bảo đảm ngoài định nghĩa |

Claims không có cùng ý nghĩa ở mọi hệ thống. Dùng schema và profile đã thống nhất; không lấy một trường tên role hoặc tenant từ token bất kỳ rồi tin nó mà không xác minh issuer và chính sách.

### Tránh dùng email làm định danh ổn định

Email có thể đổi, tái cấp hoặc được chia sẻ. Dùng subject identifier ổn định theo issuer/tenant hoặc internal immutable ID. Khi map external subject sang internal principal, cần kiểm soát liên kết danh tính và xử lý trường hợp một subject bị unlink/relink.

## 10. Authorization ở từng hop

Principal propagation không có nghĩa gateway đã cho phép thì mọi service phía sau đều phải thực hiện. Mỗi service chịu trách nhiệm authorization cho tài nguyên và hành động mà nó kiểm soát.

Ví dụ:

- Gateway xác minh access token và quyền gọi API tổng quát.
- Order Service kiểm tra Alice có quyền xem hoặc tạo đơn trong tenant của mình.
- Billing Service kiểm tra token có audience của Billing, scope tạo thanh toán và đơn hàng thuộc đúng tenant.
- Payment adapter kiểm tra service identity và giới hạn giao tiếp với nhà cung cấp.

### Kiểm tra cả subject và actor

Một service có thể được phép gọi Billing nhưng không có quyền thực hiện mọi giao dịch thay mặt mọi user. Billing cần kiểm tra:

- Subject có được phép hành động trên resource không?
- Actor/service có được phép thực hiện hành động này không?
- Delegation có bao gồm action cụ thể không?
- Resource có thuộc tenant của subject không?
- Có điều kiện bổ sung như step-up, approval hoặc transaction limit không?

### Ngăn confused deputy

Confused deputy xảy ra khi service có quyền cao bị lợi dụng để thực hiện hành động cho caller không đủ quyền. Ví dụ, Export Service có quyền đọc mọi tenant; attacker gửi request với tenant_id tự chọn và service dùng quyền rộng của chính nó để lấy dữ liệu.

Phòng vệ:

- Ràng buộc subject, tenant và resource trong authorization.
- Không để caller tự quyết định tenant/resource chỉ qua header không tin cậy.
- Dùng token audience/scope và delegation context phù hợp.
- Giới hạn quyền service theo workload và nhiệm vụ.
- Kiểm tra quyền ở service sở hữu dữ liệu, không chỉ ở gateway.
- Audit cả subject lẫn actor.

## 11. Tenant isolation và liên kết principal

Trong hệ thống multi-tenant, cùng một người có thể là thành viên của nhiều tenant với vai trò khác nhau. Principal propagation phải giữ tenant context có nguồn đáng tin và không để một request chuyển tenant bằng cách sửa header.

### Quy tắc

- Tenant phải được xác định từ token/identity mapping hoặc membership đã xác minh.
- Kiểm tra principal có membership và quyền trong tenant đang yêu cầu.
- Ràng buộc resource với tenant ở database/service layer.
- Không tin X-Tenant-ID do client tự gửi nếu chưa được xác minh.
- Token downstream chỉ mang tenant cần thiết cho hop hiện tại.
- Audit ghi tenant context để điều tra truy cập chéo.

Một user có quyền admin ở Tenant A không mặc nhiên là admin ở Tenant B. Không dùng role global nếu quyền thực tế phụ thuộc tenant.

### External identity mapping

Khi token từ một identity provider được map sang internal user, khóa liên kết nên bao gồm issuer và subject ổn định. Chỉ dùng email để tự động hợp nhất tài khoản có thể dẫn đến account linking takeover nếu email thay đổi hoặc được tái cấp.

## 12. Principal propagation qua hàng đợi và công việc bất đồng bộ

Request đồng bộ thường có thể giữ token trong thời gian ngắn. Với queue/job chạy sau vài phút hoặc vài giờ, token ban đầu có thể hết hạn, bị thu hồi hoặc không còn phù hợp.

### Không lưu bearer token dài hạn vào message

Một message không nên chứa access token thô chỉ để worker dùng lại sau này. Message có thể được lưu lâu, replay, sao chép vào dead-letter queue hoặc truy cập bởi nhiều thành phần vận hành.

Thay vào đó, message có thể chứa:

- Job ID và correlation ID.
- Subject reference đã xác minh.
- Actor/service khởi tạo.
- Tenant và resource reference cần thiết.
- Hành động được yêu cầu và delegation/policy reference.
- Thời điểm tạo, expiry hoặc deadline.
- Chữ ký hoặc cơ chế integrity/authentication của producer.

Worker dùng service identity của chính nó để xác thực với downstream và lấy token ngắn hạn khi thực thi. Nếu cần tiếp tục quyền thay mặt user, worker phải kiểm tra delegation còn hợp lệ theo policy, hoặc dùng authorization grant/job context đã được cấp có thời hạn và phạm vi rõ.

### Quyết định authorization tại thời điểm thực thi

Một job được xếp hàng lúc user còn quyền có thể chạy sau khi user bị offboard hoặc quyền đã bị thu hồi. Với hành động nhạy cảm, worker nên kiểm tra lại quyền hoặc trạng thái delegation tại thời điểm thực thi. Không mặc định quyền lúc enqueue còn hiệu lực vô thời hạn.

### Chống replay và message tampering

- Xác thực producer của message.
- Dùng message ID/idempotency key.
- Ràng buộc message với queue/topic và consumer dự kiến.
- Có timestamp/expiry và chính sách xử lý message cũ.
- Bảo vệ integrity bằng broker ACL, chữ ký hoặc cơ chế phù hợp.
- Không cho phép sửa subject/tenant/action mà không bị phát hiện.

## 13. Context propagation và tracing

Distributed tracing thường truyền trace ID, span ID, baggage hoặc metadata qua các service. Đây là công cụ quan sát vận hành, không mặc nhiên là nguồn danh tính đáng tin.

### Không đặt credential trong trace context

Không đưa access token, refresh token, cookie, recovery code hoặc raw identity assertion vào:

- Trace baggage.
- Span attributes.
- Log message.
- Error report.
- Metrics label.
- URL hoặc query string.

Trace ID chỉ liên kết các sự kiện; nó không chứng minh người dùng nào đã được xác thực. Nếu cần liên kết audit với trace, dùng principal reference đã chuẩn hóa và được phép ghi nhận, không dùng secret.

### Phân biệt correlation với trust

Một traceparent hoặc correlation ID có thể do client gửi. Hệ thống có thể tạo ID nội bộ mới ở ranh giới tin cậy và lưu liên kết với ID ngoài nếu cần. Không dùng correlation ID do client cung cấp để quyết định quyền hoặc xác định principal.

## 14. Lỗi thường gặp khi truyền principal

| Lỗi | Hậu quả | Cách phòng vệ |
|---|---|---|
| Tin X-User/X-Role từ client | Giả mạo principal hoặc nâng quyền | Strip header, xác thực nguồn, dùng token/assertion đã ký |
| Forward token sai audience | Token bị dùng ở service không dự kiến | Token exchange hoặc cấp audience đúng |
| Chuyển tiếp ID token tới API | Nhầm token đăng nhập với token truy cập API | Dùng access token đúng resource |
| Dùng một service account cho mọi workload | Khó quy trách nhiệm, phạm vi compromise rộng | Workload identity riêng và quyền tối thiểu |
| Mất actor trong delegation | Audit không biết service nào thực hiện | Giữ actor/delegation context |
| Gộp actor thành subject | Che giấu impersonation hoặc hành động tự động | Ghi cả subject và actor |
| Tin tenant từ request body/header | Cross-tenant access | Xác minh membership và resource ownership |
| Token sống quá lâu | Tăng cửa sổ lạm dụng khi bị lộ | Lifetime ngắn, revocation/introspection phù hợp |
| Ghi token vào log/tracing | Lộ bearer credential | Redaction, allowlist field và kiểm thử log |
| Queue lưu token thô | Token có thể bị replay lâu sau | Job context tối thiểu, worker identity và token ngắn hạn |
| Gateway quyết định mọi quyền | Backend bị confused deputy | Authorization ở service sở hữu resource |
| Fail-open khi identity service lỗi | Request không xác minh vẫn được thực hiện | Fail closed cho hành động bảo vệ; fallback có giới hạn |

## 15. Ví dụ thiết kế: Order Service gọi Billing thay mặt Alice

**Bối cảnh:** Alice đăng nhập vào ứng dụng đặt hàng và yêu cầu thanh toán đơn hàng ORD-184. Order Service cần gọi Billing Service. Billing phải biết request đến từ Order Service, được thực hiện thay mặt Alice và thuộc Tenant A.

### Luồng đề xuất

1. Gateway xác minh access token đầu vào: issuer, chữ ký/introspection, audience, expiry và quyền gọi Order API.
2. Gateway chuyển request tới Order Service qua kênh service-to-service đã xác thực.
3. Order Service kiểm tra Alice có quyền trên ORD-184 và đơn hàng thuộc Tenant A.
4. Order Service xác thực service identity của chính nó với authorization server.
5. Order Service thực hiện token exchange theo policy để lấy token audience billing-api, scope giới hạn cho hành động tạo payment và subject Alice.
6. Token/delegation context giữ thông tin actor là Order Service theo profile đã thống nhất.
7. Billing Service xác minh token, service caller, audience, scope, expiry, subject, actor và tenant.
8. Billing kiểm tra đơn hàng, số tiền, trạng thái và giới hạn nghiệp vụ của chính nó.
9. Billing ghi audit với subject Alice, actor Order Service, resource ORD-184, tenant và kết quả.
10. Order Service trả kết quả cho ứng dụng.

### Điều gì xảy ra nếu Alice mất quyền giữa chừng?

Với request đồng bộ ngắn, policy có thể dựa trên token/delegation đã cấp và thời hạn của nó. Với giao dịch trì hoãn hoặc có giá trị cao, Billing hoặc workflow cần kiểm tra lại trạng thái quyền/delegation tại thời điểm thực thi. Cần xác định rõ thời điểm quyết định quyền và chính sách thu hồi.

### Điều gì xảy ra nếu Order Service bị compromise?

Attacker có thể dùng service identity của Order Service trong phạm vi quyền được cấp. Giảm tác động bằng:

- Giới hạn scope token exchange và audience.
- Giới hạn service identity theo workload/environment.
- Ràng buộc delegation với subject, resource và action khi profile hỗ trợ.
- Giám sát số lượng và loại giao dịch.
- Dùng approval/transaction limit cho hành động nhạy cảm.
- Thu hồi credential/service grant và điều tra token đã phát hành.

## 16. Ví dụ payload context

Ví dụ dưới đây chỉ minh họa ngữ nghĩa của context đã được xác thực. Trong triển khai thật, không tin JSON tự gửi qua mạng nếu nó không được bảo vệ bằng token/assertion hoặc kênh service đã xác thực.

~~~json
{
  "subject": {
    "issuer": "https://identity.example.org",
    "id": "user-7f31"
  },
  "actor": {
    "type": "service",
    "id": "order-api"
  },
  "tenant": "tenant-a",
  "action": "payment.create",
  "resource": "order:ORD-184",
  "audience": "billing-api",
  "issued_at": "2026-11-22T08:30:00Z",
  "expires_at": "2026-11-22T08:35:00Z",
  "correlation_id": "req-9b20"
}
~~~

Các giá trị là ví dụ giả lập. correlation_id chỉ dùng liên kết sự kiện; nó không phải credential. Nếu context được ký, verifier phải kiểm tra chữ ký, issuer, audience, expiry và tính toàn vẹn. Nếu dùng token exchange, schema token phải theo profile của authorization server.

## 17. Kiểm thử principal propagation

Kiểm thử trong môi trường được phép với principal, token và service identity giả lập:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Client gửi X-Authenticated-User: admin | Gateway xóa/ghi đè; backend không tin giá trị client |
| Token có issuer không được tin cậy | Bị từ chối |
| Token có audience của Order API gửi tới Billing | Billing từ chối nếu audience không phù hợp |
| ID token được gửi làm access token | API từ chối theo profile |
| Token hết hạn hoặc chưa đến nbf | Bị từ chối theo clock policy |
| Token chữ ký sai hoặc thuật toán ngoài allowlist | Bị từ chối |
| Token thiếu scope cần thiết | Authorization từ chối |
| Service identity không được phép gọi Billing | Kết nối/request bị từ chối |
| Token exchange yêu cầu scope rộng hơn policy | Authorization server từ chối hoặc giới hạn scope |
| Actor bị mất trong delegation | Audit phát hiện thiếu context; không gán sai hành động cho subject |
| Subject không có quyền trên resource | Service sở hữu resource từ chối |
| Tenant header bị sửa | Backend xác minh membership/resource; không truy cập chéo tenant |
| Queue message bị sửa subject/action | Integrity verification thất bại |
| Message được replay | Idempotency/expiry ngăn thực thi lặp |
| User bị offboard trước khi job chạy | Worker kiểm tra lại quyền theo policy |
| Token xuất hiện trong log/trace | Secret scanning/redaction phát hiện và ngăn lộ |
| Authorization server không khả dụng | Hành động được bảo vệ không fail-open |
| Một service bị compromise | Quyền workload và token scope giới hạn blast radius |
| Token bị revoke nhưng cache còn hiệu lực | Kiểm tra cache/introspection và thời gian lan truyền thu hồi |
| Impersonation được yêu cầu | Chỉ cho phép theo policy, có actor, lý do và audit |

### Chỉ số vận hành

- Tỷ lệ request downstream dùng token đúng audience.
- Số lần token exchange bị từ chối do scope/audience/delegation.
- Số request bị chặn do identity header giả mạo.
- Tỷ lệ service có workload identity riêng.
- Số lần authorization thất bại do tenant mismatch.
- Thời gian thu hồi token/grant lan tới resource server.
- Số sự kiện thiếu subject/actor hoặc audit context.
- Số secret bị phát hiện trong log, trace hoặc message queue.

## 18. Checklist thiết kế principal propagation

- [ ] Phân biệt principal, subject, actor, client và service identity.
- [ ] Giữ được nguồn gốc delegation và không nhầm actor với subject.
- [ ] Chọn forwarding, token exchange hoặc signed assertion theo trust model.
- [ ] Không chuyển tiếp ID token như access token.
- [ ] Mỗi downstream token có audience, scope và lifetime phù hợp.
- [ ] Token/assertion được xác minh issuer, chữ ký, expiry và profile.
- [ ] Mỗi workload có service identity riêng và quyền tối thiểu.
- [ ] Không tin identity header do client tự gửi.
- [ ] Gateway xóa header giả mạo trước khi tạo context tin cậy.
- [ ] Service sở hữu resource tự kiểm tra authorization ở từng hop.
- [ ] Tenant context được xác minh từ membership và resource ownership.
- [ ] Không dùng email hoặc correlation ID làm principal identifier duy nhất.
- [ ] Queue message không chứa bearer token dài hạn.
- [ ] Async worker kiểm tra delegation/quyền tại thời điểm thực thi khi cần.
- [ ] Có chống replay, idempotency và integrity cho message/context.
- [ ] Không ghi token, cookie hoặc recovery secret vào log/tracing.
- [ ] Có audit subject, actor, tenant, action, resource và kết quả.
- [ ] Có fallback an toàn khi issuer/introspection/identity service lỗi.
- [ ] Kiểm thử confused deputy, spoofing, cross-tenant và token audience.

## Ghi nhớ

Principal propagation giữ ngữ cảnh danh tính và ủy quyền khi request đi qua nhiều service. Cần phân biệt subject được hành động thay mặt với actor/service trực tiếp thực hiện; giữ delegation context; và xác minh token/assertion theo issuer, audience, thời hạn, scope cùng trust model.

Không tin identity header do client tự gửi, không dùng ID token thay access token, không chuyển bearer token dài hạn vào queue và không để gateway thay thế authorization tại service sở hữu resource. Mỗi hop cần service identity riêng, quyền tối thiểu, tenant isolation và audit có thể truy vết.
