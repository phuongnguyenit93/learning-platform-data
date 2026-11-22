# JWT tại API gateway và tại dịch vụ xử lý tài nguyên

Trong kiến trúc nhiều dịch vụ, API gateway thường là điểm tiếp nhận request từ client, còn các resource service mới là nơi đọc hoặc thay đổi dữ liệu nghiệp vụ. Cả gateway và service đều có thể tham gia kiểm soát truy cập, nhưng chúng đứng ở những ranh giới tin cậy khác nhau. Nếu chỉ gateway xác minh JWT rồi các service phía sau tin mọi request nội bộ, một đường truy cập vòng qua gateway hoặc một service bị xâm nhập có thể làm suy yếu toàn bộ hệ thống.

Bài học thuộc chương **Ranh giới dịch vụ** của module **Security – JSON Web Token (JWT)**. Nội dung giải thích cách phân chia trách nhiệm xác minh JWT và phân quyền giữa gateway với resource server, lựa chọn chuyển tiếp token hay tạo token dành riêng cho service, bảo vệ identity context nội bộ và kiểm thử các ranh giới tin cậy. Phạm vi áp dụng cho mọi nền tảng, ngôn ngữ và framework.

## 1. Gateway và resource service đứng ở đâu?

API gateway là thành phần tiếp nhận request từ client, định tuyến tới API phù hợp và thường thực hiện các kiểm soát ở biên như TLS termination, giới hạn tốc độ, kiểm tra định dạng, xác thực sơ bộ và chính sách truy cập cấp API.

Resource service là dịch vụ sở hữu hoặc cung cấp một tài nguyên nghiệp vụ. Ví dụ:

- Billing service quản lý hóa đơn.
- Order service quản lý đơn hàng.
- Profile service quản lý hồ sơ người dùng.
- Payment service thực hiện giao dịch thanh toán.

Resource service phải bảo vệ dữ liệu và hành động mà nó trực tiếp kiểm soát. Vì vậy, service cần có cách xác định request đến từ workload nào, đại diện cho chủ thể nào và chủ thể đó có quyền trên tài nguyên cụ thể hay không.

~~~mermaid
flowchart LR
    C["Client"] -->|"Access token"| G["API Gateway"]
    G -->|"Request nội bộ"| O["Order Service"]
    G -->|"Request nội bộ"| B["Billing Service"]
    G -->|"Request nội bộ"| P["Profile Service"]
    O --> D1[("Order DB")]
    B --> D2[("Billing DB")]
    P --> D3[("Profile DB")]
    I["Authorization Server / IdP"] -. "Issuer, keys, metadata" .-> G
    I -. "Issuer, keys, metadata" .-> O
    I -. "Issuer, keys, metadata" .-> B
    I -. "Issuer, keys, metadata" .-> P
~~~

Gateway là một lớp bảo vệ hữu ích, nhưng không mặc nhiên là nơi duy nhất có trách nhiệm bảo vệ mọi tài nguyên. Nếu service có thể được gọi trực tiếp, nó phải tự xác minh credential và quyền. Nếu service chỉ chấp nhận request từ một gateway được xác thực và nhận một security context nội bộ đáng tin cậy, kiến trúc phải bảo đảm ranh giới đó bằng danh tính workload, kênh truyền và chính sách mạng.

## 2. Phân biệt xác thực token và phân quyền tài nguyên

Hai quyết định thường bị gộp nhầm:

- **Authentication / token validation:** token có hợp lệ theo issuer, chữ ký, audience, thời hạn và profile được chấp nhận không?
- **Authorization:** chủ thể hoặc workload có được phép thực hiện hành động trên tài nguyên cụ thể không?

Gateway có thể xác minh token và kiểm tra quyền gọi một route, ví dụ yêu cầu scope orders:read cho endpoint đọc đơn hàng. Tuy nhiên, gateway thường không sở hữu đầy đủ trạng thái nghiệp vụ để biết người dùng có được đọc đơn hàng số 42 hay đơn hàng đó thuộc tenant nào.

Resource service cần kiểm tra quyền ở cấp tài nguyên:

- Chủ thể có quyền đọc hoặc sửa bản ghi này không?
- Tài nguyên có thuộc tenant trong ngữ cảnh đã xác minh không?
- Đơn hàng có đang ở trạng thái cho phép hủy không?
- Người dùng có quan hệ hợp lệ với tài khoản hoặc hồ sơ này không?
- Request có vượt quá giới hạn quyền mà token được cấp không?

Một token hợp lệ chỉ chứng minh credential được chấp nhận theo profile. Nó không đồng nghĩa mọi hành động hoặc mọi ID tài nguyên đều được phép.

### 2.1. Ví dụ kiểm tra ở hai lớp

Client gửi request:

~~~http
GET /api/orders/order-42 HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
~~~

Gateway có thể kiểm tra:

1. Token có chữ ký hợp lệ và issuer nằm trong cấu hình tin cậy.
2. Audience phù hợp với API hoặc mô hình gateway được thiết kế.
3. Token chưa hết hạn và đúng loại access token.
4. Token có scope orders:read.
5. Route được phép truy cập từ client/application này.

Order service tiếp tục kiểm tra:

1. Request đến từ workload/gateway được tin cậy theo kiến trúc.
2. Identity context hoặc access token được xác minh theo hợp đồng nội bộ.
3. Subject có quyền đọc order-42.
4. Order thuộc tenant mà subject được phép truy cập.
5. Không có quy tắc nghiệp vụ nào cấm hành động.

Nếu gateway chỉ kiểm tra scope nhưng service không kiểm tra quyền trên order-42, hệ thống có thể mắc lỗi Broken Object Level Authorization (BOLA), còn thường được gọi là IDOR trong một số ngữ cảnh.

## 3. Gateway nên kiểm tra những gì?

Gateway là policy enforcement point ở biên. Các kiểm tra thường phù hợp với vị trí này gồm:

| Kiểm tra | Mục đích |
| --- | --- |
| TLS và client connection | Bảo vệ kênh truyền và xác thực endpoint theo cấu hình |
| Cấu trúc và kích thước token | Loại request sai định dạng hoặc quá lớn |
| Chữ ký/MAC và thuật toán | Chỉ nhận token được xác minh theo thuật toán cho phép |
| Issuer | Chỉ chấp nhận nguồn phát hành đã đăng ký |
| Audience hoặc resource | Tránh nhận token dành cho API khác |
| Thời hạn và thời điểm hiệu lực | Từ chối token hết hạn hoặc chưa có hiệu lực |
| Token type/profile | Phân biệt access token với ID token hoặc loại token khác |
| Scope/route policy | Kiểm soát quyền truy cập ở mức API/operation |
| Rate limit và quota | Hạn chế lạm dụng theo client, subject hoặc workload đã xác minh |
| Request size/schema | Giảm bề mặt tấn công và lỗi đầu vào |
| Audit metadata | Ghi nhận quyết định mà không lưu raw token |

Gateway không nên tự suy diễn issuer, khóa hoặc thuật toán từ dữ liệu tùy ý do token cung cấp. Cấu hình trust, allowlist thuật toán, nguồn JWKS và mapping route phải được quản trị ngoài token.

### 3.1. Gateway không thay thế xác minh ở resource service

Nếu resource service nhận trực tiếp bearer token, service phải xác minh token theo audience và profile mà service chấp nhận. Không nên coi các header như X-User, X-Role hoặc X-Authenticated-Subject do request gửi lên là bằng chứng danh tính.

Có hai mô hình chính:

1. **Token được chuyển tiếp (token passthrough):** gateway chuyển access token tới service; service tự xác minh token và quyền.
2. **Gateway kết thúc xác thực ở biên:** gateway xác minh token bên ngoài rồi tạo security context nội bộ; service chỉ tin context này khi request đến từ gateway/workload được xác thực và client không thể giả mạo đường truyền.

Mô hình thứ hai có thể phù hợp, nhưng phải thiết kế một ranh giới tin cậy rõ ràng. Chỉ xóa Authorization header rồi thêm X-User là chưa đủ.

## 4. Mô hình A: chuyển tiếp access token tới resource service

Trong mô hình token passthrough, client gửi access token đến gateway; gateway có thể xác minh sơ bộ rồi chuyển tiếp token gốc tới resource service. Service tự xác minh token và áp dụng quyền tài nguyên.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant AS as Authorization Server
    participant S as Resource Service
    C->>G: Request + Bearer access token
    G->>G: Kiểm tra token và policy ở biên
    G->>S: Forward request + access token
    S->>S: Xác minh token theo audience/profile
    S->>S: Kiểm tra quyền trên tài nguyên
    S-->>G: Kết quả nghiệp vụ
    G-->>C: Response
    Note over G,S: Service vẫn là nơi bảo vệ tài nguyên của chính nó
~~~

### 4.1. Ưu điểm

- Resource service có thể xác minh độc lập và không cần tin gateway là thành phần duy nhất kiểm tra JWT.
- Service có thể được gọi qua nhiều đường hợp lệ nếu mỗi đường đều tuân thủ cùng profile.
- Claims và scope của người dùng được giữ trong token gốc, giảm việc tự tạo identity header.
- Gateway có thể từ chối sớm request không hợp lệ để giảm tải cho service.

### 4.2. Điều kiện và giới hạn

- Audience phải cho phép resource service nhận token đó.
- Token chỉ được chuyển tới service đúng với audience và quyền đã cấp.
- Mỗi service cần quản lý issuer, khóa, thuật toán, cache JWKS và rotation theo chính sách.
- Việc nhiều service xác minh cùng token không làm token có quyền rộng hơn; mỗi service vẫn kiểm tra scope và tài nguyên của mình.
- Nếu một token có audience quá rộng, token bị lộ ở một service có thể bị sử dụng ở nhiều service khác.
- Gateway và service cần thống nhất profile, clock skew, loại token và cách xử lý lỗi.

### 4.3. Khi nào không nên forward token gốc?

Không forward token gốc chỉ vì service đích nằm trong cùng mạng nội bộ. Nếu token được cấp cho Billing API nhưng gateway gửi nó tới Payment API, Payment API phải từ chối vì audience không phù hợp.

Khi một service cần gọi service khác thay mặt người dùng, hãy dùng delegation hoặc token exchange để nhận credential dành riêng cho resource đích. Nếu request chỉ là công việc nền của service và không đại diện cho người dùng, dùng workload identity/credential của service thay vì tái sử dụng user token.

## 5. Mô hình B: gateway xác minh rồi truyền security context nội bộ

Trong mô hình này, gateway xác minh access token bên ngoài và tạo một context đã xác thực để service phía sau sử dụng. Context có thể chứa subject, issuer, client, scope, tenant và request ID theo hợp đồng nội bộ.

Mô hình chỉ an toàn nếu resource service có thể xác thực rằng context thực sự đến từ gateway đáng tin cậy và request không thể đi vòng qua gateway bằng một đường yếu hơn.

### 5.1. Luồng xử lý

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant S as Resource Service
    C->>G: Request + access JWT
    G->>G: Xác minh chữ ký, iss, aud, exp, typ, scope
    G->>G: Tạo identity context nội bộ
    G->>S: Request + context qua mTLS
    S->>S: Xác thực workload gateway
    S->>S: Kiểm tra schema và nguồn context
    S->>S: Phân quyền trên tài nguyên
    S-->>G: Kết quả
    G-->>C: Response
~~~

### 5.2. Không tin header danh tính do client tự gửi

Một request độc hại có thể tự thêm:

~~~http
X-Authenticated-User: admin
X-Authenticated-Role: superuser
X-Tenant-ID: company-7
~~~

Nếu gateway giữ nguyên các header đó và service phía sau tin chúng, client có thể giả mạo danh tính hoặc tenant.

Gateway cần:

1. Xóa hoặc ghi đè mọi header identity nội bộ có thể được client gửi từ bên ngoài.
2. Tạo context chỉ từ token đã xác minh và policy đáng tin cậy.
3. Gửi context qua kênh đã xác thực, thường là TLS/mTLS giữa gateway và service.
4. Chỉ cho phép workload gateway đã đăng ký gọi endpoint nhận context.
5. Không để service nhận cùng endpoint qua mạng công khai hoặc một đường không xác thực.

Resource service cần:

- Xác thực danh tính workload gọi đến, không chỉ kiểm tra IP hoặc tên header.
- Chỉ nhận header/context theo schema đã định nghĩa.
- Từ chối context thiếu trường bắt buộc, sai kiểu hoặc có nguồn không hợp lệ.
- Không cho phép client truy cập trực tiếp endpoint nội bộ với header giả mạo.
- Ghi nhận nguồn context và request ID để điều tra.

### 5.3. mTLS xác thực workload, không xác thực thay người dùng

mTLS có thể chứng minh kết nối đến từ workload gateway được cấp chứng chỉ phù hợp. Nó không tự chứng minh người dùng cuối có quyền đọc hóa đơn hay sửa đơn hàng.

Service vẫn cần một identity context có nguồn gốc đáng tin và phải kiểm tra quyền tài nguyên. Hai lớp trả lời hai câu hỏi khác nhau:

- mTLS/workload identity: **dịch vụ nào đang gọi tôi?**
- user/delegation context: **dịch vụ đang đại diện cho ai và trong phạm vi nào?**

Không suy ra user là admin chỉ vì request đến từ gateway.

### 5.4. Khi nào cần một assertion nội bộ có chữ ký?

Nếu context phải đi qua nhiều hop, queue hoặc miền vận hành mà mTLS không đủ để bảo vệ nguồn gốc xuyên suốt, có thể dùng một assertion nội bộ được ký, có thời hạn ngắn và audience dành riêng cho service nhận.

Assertion nội bộ cần:

- Issuer/workload phát hành được định danh và tin cậy.
- Audience xác định đúng service nhận.
- Subject và actor được phân biệt.
- Scope/permission tối thiểu cho tác vụ.
- Thời hạn ngắn, chống phát lại nếu yêu cầu.
- Khóa ký và quy trình rotation được quản lý riêng.

Không tự tạo một định dạng header bí mật hoặc token nội bộ không có schema, vòng đời và quy trình xác minh. Khi cần token đại diện user cho service đích, OAuth Token Exchange thường là lựa chọn chuẩn hóa hơn.

## 6. Mô hình C: Token Exchange hoặc delegation cho downstream service

OAuth 2.0 Token Exchange (RFC 8693) cho phép một client hoặc service đổi một security token lấy token khác phù hợp với resource, audience hoặc phạm vi quyền tiếp theo.

Ví dụ:

- Client có access token dành cho API gateway hoặc một API tổng hợp.
- Gateway/service cần gọi Billing service thay mặt user.
- Gateway/service gửi subject token tới Authorization Server theo chính sách được cấp phép.
- Authorization Server cấp token mới với audience là Billing service và scope hẹp hơn.
- Billing service xác minh token mới và kiểm tra quyền trên hóa đơn.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway / Aggregator
    participant AS as Authorization Server
    participant B as Billing Service
    C->>G: Request + token dành cho API đầu vào
    G->>AS: Token Exchange: subject token + resource/audience
    AS->>AS: Kiểm tra quyền delegation và policy
    AS-->>G: Access token dành cho Billing
    G->>B: Request + token audience=Billing
    B->>B: Xác minh token và quyền tài nguyên
    B-->>G: Kết quả
    G-->>C: Response
~~~

### 6.1. Vì sao token exchange hữu ích?

- Token downstream có audience cụ thể, giảm việc dùng nhầm token ở service khác.
- Scope có thể thu hẹp theo tác vụ.
- Authorization Server kiểm soát service nào được phép đại diện cho user.
- Có thể biểu diễn quan hệ subject/actor hoặc delegation theo profile.
- Không cần chia sẻ token đầu vào cho mọi service.

### 6.2. Phân biệt subject và actor

Trong delegation, cần phân biệt:

- **Subject:** người dùng hoặc principal mà quyền/tác vụ đang hướng tới.
- **Actor:** service/client thực hiện request thay mặt subject.

Ví dụ, subject là user-42 còn actor là order-orchestrator. Audit cần thể hiện cả hai để biết hành động được thực hiện thay mặt ai và service nào đã thực hiện.

Không thay subject bằng service identity rồi bỏ mất ngữ cảnh người dùng nếu chính sách nghiệp vụ cần biết người dùng cuối. Ngược lại, cũng không giả định mọi request service-to-service đều có user subject; tác vụ nền có thể chỉ đại diện cho workload.

### 6.3. Không biến token exchange thành quyền tùy ý

Authorization Server phải kiểm tra:

- Client/service yêu cầu exchange có được phép làm actor không.
- Subject token có hợp lệ và còn hiệu lực không.
- Resource/audience đích có được phép nhận token không.
- Scope yêu cầu có nằm trong quyền được delegation không.
- Chính sách tenant, user, client và loại grant có cho phép không.

Token exchange không phải cách để một service nâng quyền hoặc lấy token cho bất kỳ API nào.

## 7. Audience và scope phải khớp với ranh giới service

### 7.1. Audience xác định người nhận

Claim aud xác định một hoặc nhiều đối tượng nhận mà token được phát hành cho. Resource service phải kiểm tra token có audience phù hợp với chính service hoặc resource identifier đã cấu hình.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read",
  "exp": 2000000000
}
~~~

Billing service có thể chấp nhận token này nếu issuer, chữ ký, thời hạn, loại token và policy đều hợp lệ. Order service không nên chấp nhận chỉ vì token được cùng issuer ký.

### 7.2. Audience rộng làm tăng blast radius

Một token có audience bao gồm nhiều service có thể thuận tiện cho việc forward, nhưng nếu token bị lộ ở một service thì nhiều service khác có thể chấp nhận cùng credential.

Ưu tiên:

- Audience theo resource server hoặc resource set có ranh giới rõ.
- Token riêng cho downstream service khi cần delegation.
- Scope tối thiểu cho operation cụ thể.
- Không dùng audience chung kiểu “mọi API nội bộ” nếu không có lý do và kiểm soát phù hợp.

### 7.3. Scope không thay thế quyền trên object

Scope thường mô tả nhóm quyền hoặc operation mà client/token được cấp, ví dụ invoice:read. Nó không nhất thiết xác định người dùng được đọc mọi hóa đơn.

Billing service vẫn phải kiểm tra:

- Hóa đơn thuộc subject hoặc tenant nào.
- Subject có vai trò phù hợp với hóa đơn đó không.
- Hóa đơn có bị hạn chế bởi trạng thái hoặc quy tắc nghiệp vụ không.
- Có quyền đặc biệt cần xác nhận bổ sung không.

Scope là một điều kiện cần trong nhiều mô hình, không phải bằng chứng duy nhất cho phép truy cập mọi tài nguyên.

## 8. Service-to-service: phân biệt user token và workload identity

Một request từ service A tới service B có thể chạy trong hai ngữ cảnh:

1. **On behalf of a user:** service A đang thực hiện tác vụ thay mặt một người dùng đã xác thực.
2. **Workload-to-workload:** service A thực hiện công việc của chính workload, không có người dùng cuối.

Hai trường hợp không nên dùng chung một mô hình credential.

| Bối cảnh | Credential phù hợp | Thông tin cần giữ |
| --- | --- | --- |
| Service gọi thay mặt user | Token được delegation/token exchange cho service đích | Subject, actor, audience, scope |
| Background job định kỳ | Workload identity hoặc client credential theo policy | Workload principal và quyền tác vụ |
| Service gọi service khác bằng quyền riêng của nó | Access token dành cho workload/service đích | Client/workload identity, audience và scope |
| Gateway chuyển tiếp request user | Token passthrough hoặc identity context được bảo vệ | User subject và nguồn xác thực |

Không lấy access token của một user đang đăng nhập để làm credential cho mọi background job. Cũng không dùng token của service để giả định quyền của người dùng cuối.

### 8.1. Kiểm soát confused deputy

Confused deputy xảy ra khi service có quyền rộng bị caller lừa sử dụng quyền của chính service cho hành động caller không được phép.

Ví dụ: Order service có credential gọi Payment service để hoàn tiền. Người dùng chỉ có quyền xem đơn hàng nhưng gửi request khiến Order service dùng credential nội bộ để hoàn tiền.

Để tránh:

- Giữ subject/actor và ngữ cảnh delegation khi tác vụ thay mặt user.
- Kiểm tra quyền người dùng trước khi dùng quyền workload.
- Thu hẹp scope của workload credential.
- Không để client quyết định service sẽ dùng quyền nào.
- Payment service kiểm tra policy của chính nó, không tin mọi request đến từ Order service.
- Audit cả user subject lẫn workload actor.

## 9. Bảo vệ đường đi nội bộ

Ngay cả khi token được xác minh đúng, mạng nội bộ và các hop giữa service vẫn cần kiểm soát.

### 9.1. TLS/mTLS giữa các workload

- Dùng TLS cho request nội bộ mang token, identity context hoặc dữ liệu nhạy cảm.
- Cân nhắc mTLS để xác thực workload hai chiều.
- Quản lý cấp phát, rotation, thu hồi chứng chỉ và danh tính workload.
- Không coi mạng private/VPC là đủ để tin mọi request.
- Chặn đường truy cập trực tiếp không được phép tới service.

### 9.2. Network policy và service exposure

Resource service nên chỉ mở endpoint tới các caller cần thiết. Có thể dùng network policy, firewall, private endpoint hoặc service mesh để hạn chế đường đi. Nhưng kiểm soát mạng không thay thế xác minh workload hoặc authorization ở service.

Nếu gateway được xem là điểm vào duy nhất:

- Chỉ gateway/workload được phép mới truy cập endpoint nhận identity context.
- Không expose cùng endpoint đó ra Internet.
- Có kiểm thử đường gọi trực tiếp tới service.
- Có kiểm tra khi gateway bị xâm nhập; không giả định gateway luôn an toàn.

### 9.3. Không tin header chỉ vì nó đến từ mạng nội bộ

Header như X-User, X-Role, X-Tenant, X-Forwarded-User hoặc X-Authenticated-Client có thể bị giả mạo nếu service nhận request từ nguồn không đáng tin hoặc proxy không xóa header do client cung cấp.

Hãy quy định:

- Ai được phép tạo header/context.
- Hop nào được phép truyền tiếp.
- Cách xác thực workload gửi.
- Header nào phải bị xóa ở edge.
- Schema, kiểu dữ liệu và phiên bản của context.
- Cách chống replay nếu context có thể được ghi lại và phát lại.

## 10. Chọn mô hình theo kiến trúc

| Tình huống | Mô hình thường phù hợp | Điểm cần kiểm soát |
| --- | --- | --- |
| Gateway và service đều có thể nhận request trực tiếp | Token passthrough; mỗi resource service tự xác minh | Audience đúng, issuer/keys thống nhất, quyền tài nguyên tại service |
| Chỉ gateway được phép gọi service, service không nhận token ngoài | Gateway xác minh rồi truyền context nội bộ | mTLS/workload identity, header stripping, không có đường bypass |
| Một service gọi service khác thay mặt user | OAuth Token Exchange/delegation | Subject/actor, audience và scope downstream |
| Background job gọi API | Workload identity/client credential | Quyền workload tối thiểu, không giả danh user |
| Nhiều API có yêu cầu thu hồi/quyền rất khác nhau | Token riêng theo resource hoặc opaque/introspection tùy yêu cầu | Trạng thái thu hồi, cache, SLA và ranh giới audience |
| Service có dữ liệu/operation nhạy cảm | Service tự xác minh context và authorization tài nguyên | Không phụ thuộc duy nhất vào gateway route policy |

Không có một mô hình đúng cho mọi hệ thống. Chọn dựa trên khả năng truy cập trực tiếp, số lượng service, yêu cầu delegation, SLA thu hồi và mức độ độc lập của từng resource server.

## 11. Quy trình thiết kế và triển khai

1. **Vẽ trust boundaries:** xác định client, edge, gateway, service, authorization server và các hop nội bộ.
2. **Liệt kê đường truy cập:** request có thể tới resource service qua gateway, service mesh, job, admin tool hoặc endpoint nội bộ nào?
3. **Xác định resource owner:** service nào sở hữu dữ liệu và chịu trách nhiệm cuối cùng cho quyết định truy cập?
4. **Chọn mô hình token:** passthrough, internal context hay token exchange theo từng luồng.
5. **Định nghĩa audience:** mỗi token được phát hành cho resource server hoặc resource set nào?
6. **Định nghĩa scope:** scope nào cho phép gọi operation; quyền object/tenant được kiểm tra ở đâu?
7. **Định nghĩa workload trust:** service xác thực gateway/caller bằng TLS, mTLS hoặc workload identity như thế nào?
8. **Chuẩn hóa context:** nếu truyền identity context, quy định issuer, subject, actor, tenant, scope, request ID, kiểu dữ liệu và thời hạn.
9. **Chặn spoofing/bypass:** strip header bên ngoài, đóng endpoint nội bộ và giới hạn network path.
10. **Thiết kế lỗi:** xác định 401/403, lỗi token downstream, introspection timeout và hành vi khi nguồn khóa không sẵn sàng.
11. **Thiết kế audit:** ghi subject, actor, client, audience, operation và kết quả; không ghi raw token.
12. **Kiểm thử từng ranh giới:** token sai audience, gọi trực tiếp service, giả mạo header, service bị gọi từ workload không tin cậy và quyền object-level.

## 12. Tình huống thực tế

### Tình huống A — Gateway xác minh nhưng service không xác minh

Gateway kiểm tra chữ ký và scope rồi forward request. Một endpoint nội bộ của Billing service vô tình được expose qua mạng khác. Kẻ tấn công gọi trực tiếp endpoint đó với header X-Role: admin.

**Bài học:** nếu service nhận bearer token, service tự xác minh. Nếu service nhận context từ gateway, phải xác thực workload và chặn mọi đường bypass.

### Tình huống B — Token có audience của Billing nhưng được forward tới Payment

Gateway nhận token dành cho Billing API và forward nguyên token sang Payment service. Payment service xác minh chữ ký nhưng bỏ qua audience.

**Bài học:** chữ ký hợp lệ không làm token phù hợp với mọi resource. Payment phải kiểm tra audience của chính nó và từ chối token sai người nhận.

### Tình huống C — Gateway thêm header nhưng không xóa header client gửi

Client gửi X-Authenticated-User: admin. Gateway thêm một header khác hoặc giữ header cũ; service phía sau chọn giá trị không đáng tin.

**Bài học:** edge phải xóa/ghi đè header identity do client cung cấp; service chỉ nhận context từ gateway được xác thực.

### Tình huống D — Scope hợp lệ nhưng truy cập sai tenant

Token có scope invoice:read. Người dùng thay ID hóa đơn trong URL thành hóa đơn thuộc tenant khác. Gateway cho phép route vì scope hợp lệ.

**Bài học:** Billing service kiểm tra tenant và quyền trên từng hóa đơn; scope không thay thế object-level authorization.

### Tình huống E — Service dùng credential riêng để làm hành động ngoài quyền user

Order service có quyền gọi Payment API để hoàn tiền. User chỉ được xem đơn hàng nhưng khai thác endpoint khiến Order service gọi refund bằng quyền workload.

**Bài học:** giữ delegation context, kiểm tra quyền user trước khi dùng workload privilege và để Payment service tự thực thi policy.

### Tình huống F — Chia sẻ một token cho toàn bộ microservices

Issuer cấp token có audience chung cho mọi API nội bộ và scope rộng. Một service bị xâm nhập làm token bị lộ, kẻ tấn công dùng token gọi nhiều service.

**Bài học:** thu hẹp audience và scope, dùng token downstream riêng hoặc workload identity phù hợp, giới hạn blast radius.

## 13. Checklist bảo mật ranh giới service

### Gateway

- [ ] Xác minh chữ ký/MAC, issuer, audience, thời hạn và token profile.
- [ ] Chỉ chấp nhận thuật toán và issuer trong cấu hình tin cậy.
- [ ] Kiểm tra scope/route policy ở mức API.
- [ ] Không dùng claim chưa xác minh để định tuyến hoặc cấp quyền.
- [ ] Strip/overwrite header identity do client gửi.
- [ ] Không log raw token.

### Resource service

- [ ] Nếu nhận bearer token, tự xác minh theo audience/profile của service.
- [ ] Nếu nhận identity context, xác thực workload gửi và kiểm tra schema context.
- [ ] Không có đường bypass gateway không được bảo vệ.
- [ ] Kiểm tra quyền trên object, tenant và trạng thái nghiệp vụ.
- [ ] Không tin role/tenant header từ caller chưa xác thực.
- [ ] Từ chối token sai audience hoặc sai loại.

### Service-to-service

- [ ] Phân biệt user delegation và workload identity.
- [ ] Dùng token exchange khi cần token dành riêng cho downstream resource.
- [ ] Giữ subject và actor trong audit/context khi đại diện user.
- [ ] Giới hạn scope và audience của token downstream.
- [ ] Dùng TLS/mTLS và network policy phù hợp.
- [ ] Không chuyển tiếp token gốc tới service không nằm trong audience.

### Vận hành

- [ ] Có quy trình quản lý issuer/JWKS/rotation thống nhất.
- [ ] Có SLA và cơ chế thu hồi phù hợp với từng service.
- [ ] Có audit event liên kết request, subject, actor và service.
- [ ] Có kiểm thử token sai audience, spoofed headers và direct-service access.
- [ ] Có quy trình xử lý khi gateway hoặc một resource service bị xâm nhập.

## 14. Kiểm thử ranh giới gateway và resource service

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token chữ ký sai tại gateway | Gateway từ chối |
| Token sai issuer hoặc audience tại gateway | Gateway từ chối theo policy |
| Token hợp lệ tại gateway nhưng sai audience cho service đích | Service từ chối |
| Gọi trực tiếp resource service bằng token hợp lệ đúng audience | Chỉ được xử lý nếu direct access là đường được cho phép và service tự xác minh |
| Gọi trực tiếp service bằng header X-User giả mạo | Bị từ chối |
| Gateway forward token tới API không nằm trong audience | Không thực hiện forward hoặc service đích từ chối |
| Token có scope đúng nhưng user không sở hữu object | Service từ chối |
| User thuộc tenant A truy cập dữ liệu tenant B | Service từ chối |
| Workload không phải gateway gọi endpoint nhận internal context | Bị từ chối |
| Gateway gửi context thiếu subject/actor hoặc sai kiểu | Service từ chối |
| Client gửi header identity giả cùng header thật | Edge strip/overwrite; service chỉ thấy context đáng tin |
| Service gọi downstream thay mặt user mà thiếu delegation | Authorization Server hoặc downstream từ chối |
| Workload token được dùng thay user token | Không cấp quyền user nếu policy không cho phép |
| Gateway bị timeout khi gọi Authorization Server/introspection | Xử lý theo fail-closed policy và SLA đã định nghĩa |
| Raw token xuất hiện trong log của một hop | Kiểm thử thất bại; redaction phải được sửa |

## 15. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Gateway xác minh JWT có làm resource service tự động được phép tin request không? | **Không.** Service cần tự xác minh token hoặc xác thực một security context nội bộ theo ranh giới tin cậy rõ ràng. |
| Resource service có cần kiểm tra audience không nếu gateway đã kiểm tra? | Nếu service nhận token và là resource server, **có**; audience phải phù hợp với service theo profile. |
| mTLS giữa gateway và service có chứng minh người dùng cuối có quyền đọc dữ liệu không? | **Không.** mTLS xác thực workload/kênh; service vẫn cần user context và authorization tài nguyên. |
| Scope invoice:read có cho phép đọc mọi hóa đơn không? | **Không.** Service còn phải kiểm tra tenant, ownership và policy trên hóa đơn cụ thể. |
| Có nên forward token dành cho Billing sang Payment không? | **Không.** Cần token có audience phù hợp, thường qua token exchange/delegation. |
| Có nên tin X-Authenticated-User từ request bên ngoài không? | **Không.** Edge phải strip/overwrite header và service phải xác thực nguồn context. |
| Khi service gọi API thay mặt user, cần giữ thông tin nào? | Subject, actor, audience và scope/delegation phù hợp. |
| Một background job có luôn cần access token của user không? | **Không.** Thường dùng workload identity với quyền tác vụ tối thiểu. |
| Gateway có thể thay thế kiểm tra quyền object-level ở service không? | Thông thường **không**; resource owner cần kiểm tra quyền trên dữ liệu mà nó quản lý. |

## 16. Ghi nhớ

- Gateway và resource service nằm ở các ranh giới tin cậy khác nhau; gateway không mặc nhiên thay thế trách nhiệm bảo vệ tài nguyên của service.
- Nếu service nhận bearer token, service phải xác minh token theo audience và profile mà nó chấp nhận.
- Nếu gateway kết thúc xác thực và truyền identity context, phải xác thực workload, strip header giả mạo và chặn đường bypass.
- mTLS xác thực workload/kênh truyền; nó không tự chứng minh user có quyền trên tài nguyên.
- Audience giới hạn người nhận; không forward token tới service không nằm trong audience.
- Scope kiểm soát operation ở mức token; resource service vẫn phải kiểm tra object, tenant và quy tắc nghiệp vụ.
- Phân biệt user delegation với workload identity; dùng token exchange khi cần credential riêng cho downstream.
- Giữ subject và actor để audit hành động thay mặt người dùng.
- Kiểm thử direct-service access, spoofed headers, sai audience, cross-tenant và confused deputy.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8693 – OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8705 – OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Microservices Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Microservices_Security_Cheat_Sheet.html)
